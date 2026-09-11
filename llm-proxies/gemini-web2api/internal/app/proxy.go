package app

import (
	"encoding/json"
	"errors"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

type Proxy struct {
	ID        int64  `json:"id"`
	Name      string `json:"name"`
	URL       string `json:"url"`
	Enabled   bool   `json:"enabled"`
	Weight    int    `json:"weight"`
	FailCount int    `json:"fail_count"`
	LastUsed  int64  `json:"last_used"`
	LastError string `json:"last_error"`
	CreatedAt int64  `json:"created_at"`
}

var (
	proxyMu     sync.RWMutex
	proxyCache  []Proxy
	proxyCursor uint64
)

// loadProxies refreshes the in-memory proxy list from the DB.
//
// If the read fails halfway, **keep the previous pool** — never overwrite
// with a partial result. The old code had two silent failure points: Scan
// error with continue (quietly dropping a proxy), and rows.Err() not checked
// at all (a broken iteration treated as a normal finish). Both could make
// proxyCache shorter or even empty, while acquireSlot uses
// len(proxyCache)==0 to decide "no proxy pool configured", so **an empty
// pool fell back to direct connection** — the deployer's real IP was exposed
// to the upstream, with only occasional direct-connection requests showing
// in the logs.
//
// This path runs on every request (called as soon as recordProxyResult
// finishes), and under WAL mode rows.Next() can perfectly well return
// SQLITE_BUSY during a concurrent UPDATE — that's where the "occasional"
// comes from.
func loadProxies() {
	rows, err := getDB().Query(`SELECT id, name, url, enabled, weight, fail_count,
        COALESCE(last_used,0), COALESCE(last_error,''), created_at FROM proxies ORDER BY id`)
	if err != nil {
		logf("[proxy] read failed, keeping the previous proxy pool: %v", err)
		return
	}
	defer rows.Close()
	var list []Proxy
	for rows.Next() {
		var p Proxy
		var enabled int
		if err := rows.Scan(&p.ID, &p.Name, &p.URL, &enabled, &p.Weight, &p.FailCount,
			&p.LastUsed, &p.LastError, &p.CreatedAt); err != nil {
			logf("[proxy] a row failed to scan, keeping the previous proxy pool: %v", err)
			return
		}
		p.Enabled = enabled == 1
		list = append(list, p)
	}
	if err := rows.Err(); err != nil {
		logf("[proxy] iteration aborted, keeping the previous proxy pool: %v", err)
		return
	}
	proxyMu.Lock()
	proxyCache = list
	proxyMu.Unlock()
}

// After this many consecutive failures the proxy is circuit-broken; it goes
// back into the pool once the cooldown has elapsed.
const proxyFailThreshold = 5

// proxyUsable decides whether this proxy can be used right now.
//
// Circuit-breaking is not permanent removal: egresses blocked by Google
// recover automatically after a measured 106-121 minutes, but the old code
// only checked fail_count<5 — once exceeded, the proxy could never be picked
// again and would never get a success to reset fail_count to zero — the only
// way out was a manual reset in the panel. The cooldown counts from
// last_used (i.e. the last attempt); if it fails again after being put back,
// the timer restarts.
//
// cooldownMin<=0 disables the cooldown and reverts to the old behavior of
// "circuit-broken = permanently removed".
func proxyUsable(p Proxy, now int64, cooldownMin int) bool {
	if !p.Enabled {
		return false
	}
	if p.FailCount < proxyFailThreshold {
		return true
	}
	if cooldownMin <= 0 {
		return false
	}
	return now-p.LastUsed >= int64(cooldownMin)*60
}

// kv keys recording migration/seeding state.
const (
	kvLegacyProxyDone = "legacy_static_proxy_migrated"
	kvSeededProxyID   = "seeded_proxy_id"
	kvSeededProxyURL  = "seeded_proxy_url"
)

// seedProxiesFromConfig merges the startup flag and the legacy "static
// proxy" into the proxy pool.
//
// Proxies used to have two entry points: the proxy pool, and a separate
// static proxy text field on the "Settings" page (used only when the pool
// was empty). The latter was not a "simple version" but a **crippled
// version** — it went down the picked.ID=0 path, so it shared the same
// rate-limit slot as direct connections, recordProxyResult was never called,
// and there was no failure counting, no circuit-breaking, no cooldown, and
// no visible status in the panel. One entry in the pool is strictly better
// in every respect.
//
// Now the request path only knows the pool; this function moves the values
// from the old entry point into it.
func seedProxiesFromConfig() {
	migrateLegacyStaticProxy()
	syncSeededProxy()
}

// migrateLegacyStaticProxy moves the legacy static proxy from kv into the
// pool, once.
//
// Two survival rules, both aimed at the premise "the user's DB is already
// running":
//
//  1. **Mark done only after successful insertion into the pool**; on
//     failure leave everything as-is and retry next time. The old
//     validateRuntimeConfig did zero validation on this field, so users may
//     well have stored a scheme-less value like `1.2.3.4:8080`, which
//     proxyCreate would reject — clearing the value before inserting would
//     make the proxy vanish into thin air after upgrade, sending all traffic
//     to direct connection only to be blocked by the upstream.
//  2. Use a **dedicated migration marker** instead of rewriting the
//     runtime_config JSON. Touching existing data one less time is one less
//     chance of corrupting another field; and as a bonus, rolling back to
//     the old version keeps the static proxy intact, behavior unchanged.
func migrateLegacyStaticProxy() {
	if kvGet(kvLegacyProxyDone) == "1" {
		return
	}
	v := strings.TrimSpace(legacyStaticProxy())
	if v == "" {
		_ = kvSet(kvLegacyProxyDone, "1") // there was none to begin with; mark it done so we don't re-parse on every startup
		return
	}
	if !poolHasProxyURL(v) {
		if _, err := proxyCreate("legacy static proxy", v, 1); err != nil {
			logf("[proxy] failed to migrate the settings-page static proxy into the pool, original value kept, will retry next startup: %v", err)
			return
		}
		logf("[proxy] settings-page static proxy migrated into the proxy pool")
	}
	_ = kvSet(kvLegacyProxyDone, "1")
}

// legacyStaticProxy read-only fetches the legacy runtime_config.proxy from
// kv. RuntimeConfig no longer has this field, so the raw JSON is all we can
// look at.
func legacyStaticProxy() string {
	raw := kvGet(runtimeConfigKey)
	if raw == "" {
		return ""
	}
	var m map[string]interface{}
	if err := json.Unmarshal([]byte(raw), &m); err != nil {
		return ""
	}
	v, _ := m["proxy"].(string)
	return v
}

// syncSeededProxy keeps one pool entry tracking --proxy / config.json.
//
// The startup flag is **declarative**: when the value changes, the same
// entry is updated rather than another one added. A dedup-by-URL approach
// cannot prevent this — if the user swaps the proxy in their compose file,
// the old entry stays in the pool, still enabled, still taking traffic, a
// zombie egress nobody knows is still in use.
//
// When the value is unchanged, **the pool is left completely untouched**:
// any edits, deletions or disabling of that entry the user does in the
// panel are authoritative.
func syncSeededProxy() {
	url := strings.TrimSpace(cfg.Proxy)
	prev := kvGet(kvSeededProxyURL)
	if url == prev {
		return
	}
	dropSeededProxy(prev)
	if url == "" {
		_ = kvSet(kvSeededProxyURL, "")
		_ = kvSet(kvSeededProxyID, "")
		logf("[proxy] --proxy removed from the startup flags, its pool record withdrawn along with it")
		return
	}
	if poolHasProxyURL(url) {
		// The user already added the same egress themselves in the panel;
		// don't create a duplicate, just record it
		_ = kvSet(kvSeededProxyURL, url)
		_ = kvSet(kvSeededProxyID, "")
		return
	}
	id, err := proxyCreate("startup flag", url, 1)
	if err != nil {
		logf("[proxy] failed to add --proxy to the pool: %v", err)
		return // URL not recorded; next startup will retry
	}
	_ = kvSet(kvSeededProxyURL, url)
	_ = kvSet(kvSeededProxyID, strconv.FormatInt(id, 10))
	logf("[proxy] --proxy / config.json proxy added to the proxy pool")
}

// dropSeededProxy removes the entry previously created by the startup flag.
// It deletes only if that entry **still has the URL we created it with** — if
// the user changed it to a different egress in the panel, they have taken
// over the entry, and it must not be collaterally deleted by a startup-flag
// change.
func dropSeededProxy(prevURL string) {
	idStr := kvGet(kvSeededProxyID)
	if idStr == "" || prevURL == "" {
		return
	}
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil || id <= 0 {
		return
	}
	proxyMu.RLock()
	var found *Proxy
	for i := range proxyCache {
		if proxyCache[i].ID == id {
			p := proxyCache[i]
			found = &p
			break
		}
	}
	proxyMu.RUnlock()
	if found == nil || found.URL != prevURL {
		return
	}
	if err := proxyDelete(id); err != nil {
		logf("[proxy] failed to withdraw the old startup-flag proxy: %v", err)
	}
}

// poolHasProxyURL reports whether the pool contains this URL.
func poolHasProxyURL(url string) bool {
	proxyMu.RLock()
	defer proxyMu.RUnlock()
	for _, p := range proxyCache {
		if p.URL == url {
			return true
		}
	}
	return false
}

// pickProxyWithCapacity finds a usable proxy (enabled + not circuit-broken
// or past cooldown) whose rate limit isn't saturated.
// Returns (proxy, ok). When all proxies are unusable or saturated, ok=false.
//
// Difference from the old pickProxy: it asks trySlotAcquire whether the
// slot has capacity; the caller must pair the acquired slot with
// slotRelease(proxy.ID).
func pickProxyWithCapacity() (Proxy, bool) { return pickProxyPreferring(0) }

// pickProxyPreferring prefers the preferID egress; only round-robins to
// others when it is unusable or has no capacity.
//
// Why stick: if the cookie pool and the proxy pool rotate independently, the
// same Google account jumps back and forth across dozens of egress IPs —
// exactly the signature of a shared account in Google's eyes. When sticking
// isn't possible, switching egress is preferred over queueing: availability
// first.
func pickProxyPreferring(preferID int64) (Proxy, bool) {
	proxyMu.RLock()
	defer proxyMu.RUnlock()
	if len(proxyCache) == 0 {
		return Proxy{}, false
	}
	now := time.Now().Unix()
	cooldown := rtCfg().ProxyCooldownMin
	var pool []Proxy
	for _, p := range proxyCache {
		if proxyUsable(p, now, cooldown) {
			pool = append(pool, p)
		}
	}
	if len(pool) == 0 {
		return Proxy{}, false
	}
	if preferID > 0 {
		for _, p := range pool {
			if p.ID == preferID {
				if ok, _ := trySlotAcquire(p.ID); ok {
					return p, true
				}
				break // the pinned one is saturated; fall through to normal round-robin
			}
		}
	}
	// Starting from the round-robin start point, find the first slot with capacity
	start := atomic.AddUint64(&proxyCursor, 1) - 1
	for i := 0; i < len(pool); i++ {
		p := pool[(int(start)+i)%len(pool)]
		if ok, _ := trySlotAcquire(p.ID); ok {
			return p, true
		}
	}
	return Proxy{}, false
}

// recordProxyResult writes back the result of one request and updates the
// matching in-memory entry.
//
// Only the in-memory entry is changed, not the whole table re-read: this
// function is called on every request, and a re-read is a full-table SELECT
// right after it itself issued an UPDATE — under high concurrency it is
// precisely this read/write pair colliding on WAL that produces
// SQLITE_BUSY, i.e. the trigger condition for the proxy pool being read
// empty and requests falling back to direct connection.
//
// The cost is that the in-memory FailCount++ and the DB's fail_count+1 are
// counted separately; another process modifying the DB directly would let
// the two drift. This process owns the DB, and a restart reloads from the
// DB, so it's acceptable.
func recordProxyResult(id int64, success bool, errStr string) {
	if id == 0 {
		return
	}
	now := time.Now().Unix()
	if success {
		_, _ = getDB().Exec(`UPDATE proxies SET fail_count=0, last_used=?, last_error='' WHERE id=?`, now, id)
	} else {
		_, _ = getDB().Exec(`UPDATE proxies SET fail_count=fail_count+1, last_used=?, last_error=? WHERE id=?`,
			now, errStr, id)
	}
	proxyMu.Lock()
	for i := range proxyCache {
		if proxyCache[i].ID != id {
			continue
		}
		proxyCache[i].LastUsed = now
		if success {
			proxyCache[i].FailCount = 0
			proxyCache[i].LastError = ""
		} else {
			proxyCache[i].FailCount++
			proxyCache[i].LastError = errStr
		}
		break
	}
	proxyMu.Unlock()
}

// CRUD ───────────────────────────────────────────────────────────────────────

func proxyCreate(name, url string, weight int) (int64, error) {
	if name == "" || url == "" {
		return 0, errors.New("name and url required")
	}
	if err := validateProxyURL(url); err != nil {
		return 0, err
	}
	if weight <= 0 {
		weight = 1
	}
	id, err := insertID(`INSERT INTO proxies(name, url, enabled, weight, created_at)
        VALUES (?,?,?,?,?)`, name, url, 1, weight, time.Now().Unix())
	if err != nil {
		return 0, err
	}
	loadProxies()
	return id, nil
}

// validateProxyURL validates the proxy URL scheme.
// Supports http / https / socks5 / socks5h.
//
// The scheme is compared case-insensitively: URL schemes are case-
// insensitive by definition and url.Parse lowercases them anyway, so
// HTTP:// worked fine on the unvalidated static-proxy path in 4.0.0. A
// case-sensitive check would reject such values on upgrade — the user
// changed nothing, yet the proxy stops working.
func validateProxyURL(s string) error {
	low := strings.ToLower(s)
	for _, p := range []string{"http://", "https://", "socks5://", "socks5h://"} {
		if strings.HasPrefix(low, p) {
			return nil
		}
	}
	return errors.New("proxy URL must start with http:// / https:// / socks5:// / socks5h://")
}

func proxyUpdate(id int64, name, url string, enabled *bool, weight *int) error {
	q := `UPDATE proxies SET `
	args := []interface{}{}
	parts := []string{}
	if name != "" {
		parts = append(parts, "name=?")
		args = append(args, name)
	}
	if url != "" {
		parts = append(parts, "url=?")
		args = append(args, url)
	}
	if enabled != nil {
		v := 0
		if *enabled {
			v = 1
		}
		parts = append(parts, "enabled=?")
		args = append(args, v)
	}
	if weight != nil {
		parts = append(parts, "weight=?")
		args = append(args, *weight)
	}
	if len(parts) == 0 {
		return nil
	}
	q += joinComma(parts) + " WHERE id=?"
	args = append(args, id)
	_, err := getDB().Exec(q, args...)
	if err == nil {
		loadProxies()
	}
	return err
}

func proxyDelete(id int64) error {
	_, err := getDB().Exec(`DELETE FROM proxies WHERE id=?`, id)
	if err == nil {
		loadProxies()
	}
	return err
}

func proxyResetFailures(id int64) error {
	_, err := getDB().Exec(`UPDATE proxies SET fail_count=0, last_error='' WHERE id=?`, id)
	if err == nil {
		loadProxies()
	}
	return err
}

func listProxies() []Proxy {
	proxyMu.RLock()
	defer proxyMu.RUnlock()
	out := make([]Proxy, len(proxyCache))
	copy(out, proxyCache)
	return out
}

func joinComma(parts []string) string {
	out := ""
	for i, p := range parts {
		if i > 0 {
			out += ", "
		}
		out += p
	}
	return out
}

// proxyNameByID finds the proxy name by id; returns an empty string when
// not found (0 = not yet bound / direct connection).
func proxyNameByID(id int64) string {
	if id <= 0 {
		return ""
	}
	proxyMu.RLock()
	defer proxyMu.RUnlock()
	for _, p := range proxyCache {
		if p.ID == id {
			return p.Name
		}
	}
	return ""
}

// proxyUsableByID reports whether this egress is still usable (exists +
// enabled + not circuit-broken or past cooldown). Used to check whether an
// account's bound egress is still valid; rebinding should happen only when
// it isn't.
func proxyUsableByID(id int64) bool {
	if id <= 0 {
		return false
	}
	proxyMu.RLock()
	defer proxyMu.RUnlock()
	now := time.Now().Unix()
	cooldown := rtCfg().ProxyCooldownMin
	for _, p := range proxyCache {
		if p.ID == id {
			return proxyUsable(p, now, cooldown)
		}
	}
	return false
}

// proxyURLByID fetches the proxy URL by id; returns an empty string when
// not found (direct connection).
func proxyURLByID(id int64) string {
	if id <= 0 {
		return ""
	}
	proxyMu.RLock()
	defer proxyMu.RUnlock()
	for _, p := range proxyCache {
		if p.ID == id {
			return p.URL
		}
	}
	return ""
}
