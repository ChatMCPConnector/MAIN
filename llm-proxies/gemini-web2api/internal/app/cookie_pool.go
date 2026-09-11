package app

import (
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

// CookieAccount is one row in the cookie pool: one signed-in Google account.
type CookieAccount struct {
	ID         int64  `json:"id"`
	Label      string `json:"label"`
	Cookie     string `json:"cookie"` // full string; the API layer masks it before returning
	Status     string `json:"status"`
	Note       string `json:"note"`
	CreatedAt  int64  `json:"created_at"`
	LastUsedAt int64  `json:"last_used_at"`
	LastOkAt   int64  `json:"last_ok_at"`
	LastError  string `json:"last_error"`
	FailCount  int64  `json:"fail_count"`
	ProxyID    int64  `json:"proxy_id"` // bound egress, 0 = not bound yet
}

// splitCookiePairs splits "k=v; k=v" into key/value pairs.
//
// Split on ";" and TrimSpace each segment, not on "; ": strings copied from DevTools don't necessarily carry the space, and splitting on "; " treats "SID=a;SAPISID=b" as a
// single key — extractSAPISID then finds nothing, no Authorization header is sent, the request is treated as anonymous by upstream, and the user never knows.
// single key — extractSAPISID then finds nothing, no Authorization header is sent, the request is treated as anonymous by upstream, and the user never knows.
//
// Values may contain "=" (base64 padding), so split at the first equals sign only.
func splitCookiePairs(cookie string) [][2]string {
	var out [][2]string
	for _, p := range strings.Split(cookie, ";") {
		p = strings.TrimSpace(p)
		if i := strings.Index(p, "="); i > 0 {
			out = append(out, [2]string{p[:i], p[i+1:]})
		}
	}
	return out
}

// cookieValue returns the value of the named cookie from a full cookie string, or an empty string if absent.
func cookieValue(cookie, name string) string {
	for _, kv := range splitCookiePairs(cookie) {
		if kv[0] == name {
			return kv[1]
		}
	}
	return ""
}

// extractSAPISID returns the SAPISID value from a full cookie string, or an empty string if absent.
func extractSAPISID(cookie string) string {
	return cookieValue(cookie, "SAPISID")
}

// cookieSubset keeps only the named entries, preserving the original order. When refreshing
// 1PSIDTS the whole string must not be sent: measured, extra Chrome DBSC / other-host cookies make RotateCookies return 401.
func cookieSubset(cookie string, names []string) string {
	want := make(map[string]bool, len(names))
	for _, n := range names {
		want[n] = true
	}
	var parts []string
	seen := map[string]bool{}
	for _, kv := range splitCookiePairs(cookie) {
		if !want[kv[0]] || kv[1] == "" || seen[kv[0]] {
			continue
		}
		seen[kv[0]] = true
		parts = append(parts, kv[0]+"="+kv[1])
	}
	return strings.Join(parts, "; ")
}

// cookieNames returns all cookie names present in the cookie string (order preserved), for UI display.
func cookieNames(cookie string) []string {
	var names []string
	for _, kv := range splitCookiePairs(cookie) {
		names = append(names, kv[0])
	}
	return names
}

// accountAdd inserts one entry into the pool. The cookie must yield a non-empty SAPISID.
// This is the path for manual adds from the panel/API, where the user sees the error immediately, so rejecting here is right.
//
// The criterion is **whether a value can be extracted**, not "does the string mention SAPISID": the
// latter would admit an unfilled per-field template (key names present, values all empty) into
// the pool, stored as a whole JSON blob, doomed to fail every time its turn comes.
func accountAdd(label, cookie, note string) (int64, error) {
	c, ok := normalizeCookie(cookie, "手工添加的 cookie")
	if !ok {
		return 0, fmt.Errorf("cookie 解析失败：既不是 \"k=v; k=v\" 串，也不是可识别的 JSON")
	}
	if extractSAPISID(c) == "" {
		return 0, fmt.Errorf("cookie 里没有 SAPISID，多半没复制全（需要 gemini.google.com 下的完整 cookie，至少含 SID / HSID / SSID / APISID / SAPISID / __Secure-1PSID）")
	}
	return accountInsert(label, c, note)
}

// accountAdopt is for importing existing configuration at startup: **no SAPISID check**.
//
// The criterion is "the upgrade must not change the availability of the user's existing config".
// A cookie missing SAPISID used to be sent as the Cookie header as-is (only the SAPISIDHASH
// authorization header couldn't be computed); whether it works is the upstream's call — it must
// not be blocked by our newly added validation on upgrade, silently dropping the user back to
func accountAdopt(label, cookie, note string) (int64, error) {
	cookie, ok := normalizeCookie(cookie, label)
	if !ok {
		return 0, fmt.Errorf("cookie 解析失败")
	}
	if extractSAPISID(cookie) == "" {
		logf("[cookie] %s 里没有 SAPISID，算不出 SAPISIDHASH 授权头，可能只当匿名处理；"+
			"先按原样导入，请到面板核对", label)
	}
	return accountInsert(label, cookie, note)
}

func accountInsert(label, cookie, note string) (int64, error) {
	cookie = strings.TrimSpace(cookie)
	if cookie == "" {
		return 0, fmt.Errorf("cookie 不能为空")
	}
	return insertID(
		`INSERT INTO accounts(label, cookie, status, note, created_at) VALUES (?,?,?,?,?)`,
		strings.TrimSpace(label), cookie, "enabled", strings.TrimSpace(note), time.Now().Unix())
}

// accountList returns all accounts in the pool, ordered by id ascending.
func accountList() []CookieAccount {
	rows, err := getDB().Query(
		`SELECT id, label, cookie, status, note, created_at, last_used_at, last_ok_at, last_error, fail_count, proxy_id
		 FROM accounts ORDER BY id`)
	if err != nil {
		return nil
	}
	defer rows.Close()
	var out []CookieAccount
	for rows.Next() {
		var a CookieAccount
		if err := rows.Scan(&a.ID, &a.Label, &a.Cookie, &a.Status, &a.Note,
			&a.CreatedAt, &a.LastUsedAt, &a.LastOkAt, &a.LastError, &a.FailCount, &a.ProxyID); err != nil {
			continue
		}
		out = append(out, a)
	}
	return out
}

// accountByID fetches one row by id; returns nil if absent.
//
// Rotation writes the new cookie back to the DB; afterwards requests must use **the copy in
// the DB** — the CookieAccount in hand is a pre-rotation snapshot, and continuing with it throws away the just-refreshed value.
func accountByID(id int64) *CookieAccount {
	var a CookieAccount
	err := getDB().QueryRow(
		`SELECT id, label, cookie, status, note, created_at, last_used_at, last_ok_at, last_error, fail_count, proxy_id
		 FROM accounts WHERE id=?`, id).
		Scan(&a.ID, &a.Label, &a.Cookie, &a.Status, &a.Note,
			&a.CreatedAt, &a.LastUsedAt, &a.LastOkAt, &a.LastError, &a.FailCount, &a.ProxyID)
	if err != nil {
		return nil
	}
	return &a
}

// accountDelete deletes one entry.
func accountDelete(id int64) error {
	_, err := getDB().Exec(`DELETE FROM accounts WHERE id=?`, id)
	return err
}

// accountSetStatus changes the status (enabled / disabled).
func accountSetStatus(id int64, status string) error {
	if status != "enabled" && status != "disabled" {
		return fmt.Errorf("非法状态 %q", status)
	}
	_, err := getDB().Exec(`UPDATE accounts SET status=? WHERE id=?`, status, id)
	return err
}

// accountUpdateMeta changes label / note (leaves the cookie itself alone).
func accountUpdateMeta(id int64, label, note string) error {
	_, err := getDB().Exec(`UPDATE accounts SET label=?, note=? WHERE id=?`,
		strings.TrimSpace(label), strings.TrimSpace(note), id)
	return err
}

// accountCount returns (total, enabled count).
func accountCount() (int, int) {
	var total, enabled int
	_ = getDB().QueryRow(`SELECT COUNT(*), SUM(CASE WHEN status='enabled' THEN 1 ELSE 0 END) FROM accounts`).
		Scan(&total, &enabled)
	return total, enabled
}

// kv keys recording migration/seeding state.
const (
	kvLegacyCookieDone = "legacy_single_cookie_migrated"
	kvSeededCookieID   = "seeded_cookie_id"
	kvSeededCookieVal  = "seeded_cookie_value"
)

// seedCookiesFromConfig merges startup arguments and the legacy single cookie into the cookie pool.
//
// Cookies originally had two entry points too: the cookie pool, and the single-cookie input on the
// Settings page used only when the pool is empty (value stored in kv's google_cookie, or from
// --cookie-file). Same defect as the static proxy — the single-cookie path returns account ID 0,
// and markAccountResult returns immediately on id<=0, so **not one word of health is written**: fail_count stays 0, last_ok_at stays empty, and no rotation ever happens.
//
//   - kv's google_cookie: migrated once, marked "done" with a separate flag, original value untouched
//   - cfg.CookieFile (--cookie-file): follows declaratively; when the content changes, the same record is replaced
func seedCookiesFromConfig() {
	migrateLegacyCookie()
	syncSeededCookieFile()
}

// migrateLegacyCookie moves the legacy single cookie from kv into the pool, once.
// Three safety rules: use accountAdopt without SAPISID validation (the old path didn't validate —
// an upgrade must not change availability), only mark done after a successful insert, and never touch the original kv value (rollback to an older version still works).
func migrateLegacyCookie() {
	if kvGet(kvLegacyCookieDone) == "1" {
		return
	}
	raw := strings.TrimSpace(kvGet("google_cookie"))
	if raw == "" {
		_ = kvSet(kvLegacyCookieDone, "1")
		return
	}
	cookie, ok := normalizeCookie(raw, "「设置」页的单 cookie")
	if !ok {
		return
	}
	if !poolHasCookie(cookie) {
		if _, err := accountAdopt("原单 cookie", cookie, "从「设置」页迁入"); err != nil {
			logf("[cookie] 「设置」页的单 cookie 迁入池子失败，原值保留、下次启动重试: %v", err)
			return
		}
		logf("[cookie] 「设置」页的单 cookie 已迁入 cookie 池")
	}
	_ = kvSet(kvLegacyCookieDone, "1")
}

// syncSeededCookieFile keeps one pool record tracking --cookie-file.
//
// Same approach as --proxy: when the file content changes, retire the old record and create a new
// one, rather than adding another. Deduping by content doesn't stop this — deployments that
// rotate cookie.txt regularly would pile dead cookies into the pool, still enabled, still in
// rotation, so every Nth request is doomed to fail. When the content is unchanged, the pool isn't touched at all; adds/deletes/disables from the panel take precedence.
func syncSeededCookieFile() {
	var cur string
	if cfg.CookieFile != "" {
		data, err := os.ReadFile(cfg.CookieFile)
		if err != nil {
			// If unreadable, treat it as never configured: better to keep the current state than to
			// yank the cookie the user is using just because the container lost a volume.
			logf("[cookie] 读不了 --cookie-file %s，池子保持不变: %v", cfg.CookieFile, err)
			return
		}
		cur = strings.TrimSpace(string(data))
	}
	if cur != "" {
		if c, ok := normalizeCookie(cur, "--cookie-file"); ok {
			cur = c
		} else {
			return
		}
	}

	prev := kvGet(kvSeededCookieVal)
	if cur == prev {
		return
	}
	dropSeededCookie(prev)
	if cur == "" {
		_ = kvSet(kvSeededCookieVal, "")
		_ = kvSet(kvSeededCookieID, "")
		logf("[cookie] --cookie-file 已移除，对应的池子记录一并撤下")
		return
	}
	if poolHasCookie(cur) {
		_ = kvSet(kvSeededCookieVal, cur)
		_ = kvSet(kvSeededCookieID, "")
		return
	}
	id, err := accountAdopt("cookie-file", cur, "来自 --cookie-file")
	if err != nil {
		logf("[cookie] --cookie-file 入池失败: %v", err)
		return
	}
	_ = kvSet(kvSeededCookieVal, cur)
	_ = kvSet(kvSeededCookieID, strconv.FormatInt(id, 10))
	logf("[cookie] --cookie-file 的 cookie 已加入 cookie 池")
}

// dropSeededCookie retires the record last created by --cookie-file.
// Only deleted when the content is still the one we wrote — if the user edited it in the panel, they've taken it over.
func dropSeededCookie(prevCookie string) {
	idStr := kvGet(kvSeededCookieID)
	if idStr == "" || prevCookie == "" {
		return
	}
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil || id <= 0 {
		return
	}
	for _, a := range accountList() {
		if a.ID == id {
			if a.Cookie == prevCookie {
				if err := accountDelete(id); err != nil {
					logf("[cookie] 撤下旧的 --cookie-file 记录失败: %v", err)
				}
			}
			return
		}
	}
}

// The cookies listed by the panel's per-field mode, and also the fixed order when assembling the string.
// The order must be deterministic: if the same cookie assembles into two strings with different key orders, dedup by content stops working.
var cookieTemplateOrder = []string{
	"SID", "HSID", "SSID", "APISID", "SAPISID", "__Secure-1PSID", "__Secure-1PSIDTS",
}

// normalizeCookie normalizes various input shapes into the bare "k=v; k=v" string the pool wants.
//
// Accepts three shapes:
//   - bare string, returned as-is
//   - the old single-cookie path's {"cookie":"k=v; k=v","sapisid":"..."}
//   - the panel's per-field mode's {"SID":"a","SAPISID":"b",...}
//
// Without normalization a whole JSON blob would land in the pool; SAPISID extraction and every subsequent request would be wrong.
func normalizeCookie(raw, who string) (string, bool) {
	raw = strings.TrimSpace(raw)
	if !strings.HasPrefix(raw, "{") {
		return raw, true
	}
	var m map[string]interface{}
	if err := json.Unmarshal([]byte(raw), &m); err != nil {
		logf("[cookie] %s 是 JSON 但解析失败，跳过: %v", who, err)
		return "", false
	}
	if c, ok := m["cookie"].(string); ok && strings.TrimSpace(c) != "" {
		return strings.TrimSpace(c), true
	}

	str := func(k string) string {
		s, _ := m[k].(string)
		return strings.TrimSpace(s)
	}
	var parts []string
	inTemplate := map[string]bool{}
	for _, k := range cookieTemplateOrder {
		inTemplate[k] = true
		if v := str(k); v != "" {
			parts = append(parts, k+"="+v)
		}
	}
	// Extra fields the user copied from DevTools must not be lost; append them after the template fields, sorted by name
	var extra []string
	for k := range m {
		if !inTemplate[k] && k != "sapisid" && str(k) != "" {
			extra = append(extra, k)
		}
	}
	sort.Strings(extra)
	for _, k := range extra {
		parts = append(parts, k+"="+str(k))
	}
	if len(parts) == 0 {
		logf("[cookie] %s 是 JSON 但一项非空值都没有，跳过", who)
		return "", false
	}
	return strings.Join(parts, "; "), true
}

func poolHasCookie(cookie string) bool {
	for _, a := range accountList() {
		if a.Cookie == cookie {
			return true
		}
	}
	return false
}

// pickMu turns "SELECT the least-recently-used account + UPDATE its last_used_at" into an atomic
// operation. Without the lock, two concurrent requests SELECT the same "least recently used"
// account, each UPDATE it, and both use it at the same instant — rotation becomes pointless
// (known defect recorded in CLAUDE.md). One in-process lock is enough — the rate limiter,
// rotation scheduling, and the proxy pool are all in-process state; this reverse proxy is
// single-instance by nature, so there is no cross-process account picking, and no need for cross-dialect transactions/row locks (sqlite has no FOR UPDATE, mysql no RETURNING — that path is all dialect branches). Picking is one very fast SELECT+UPDATE; serialized contention is negligible.
var pickMu sync.Mutex

// pickCookieAccount picks an enabled account from the pool, least-recently-used first,
// and immediately records last_used_at as now (someone else's turn next). Empty pool returns (nil,false).
func pickCookieAccount() (*CookieAccount, bool) {
	return pickCookieAccountExcept(nil)
}

// pickCookieAccountExcept is the same, but skips accounts already tried this request.
//
// Why it exists: one dead cookie must not fail the whole request. With 2 accounts in the pool
// and 1 bad, rotation sends about half of all requests into the bad one — the symptom is a
// "mysteriously low success rate", and every failure looks like an upstream problem.
func pickCookieAccountExcept(skip map[int64]bool) (*CookieAccount, bool) {
	pickMu.Lock()
	defer pickMu.Unlock()
	// Healthy accounts sort first; equally healthy ones rotate by least-recently-used.
	//
	// Without this ordering, bad accounts rotate on equal footing with good ones; a picked bad
	// account has no bound egress, so the egress is chosen "no preference"; by the time the
	// switch reaches a good account, the egress is already fixed — so the bad account drags the good account's egress stickiness off course. Measured with 1 good / 2 bad: the egress split 50/50 across two proxies.
	rows, err := getDB().Query(
		`SELECT id, label, cookie, status, note, created_at, last_used_at, last_ok_at, last_error, fail_count, proxy_id
		 FROM accounts WHERE status='enabled' ORDER BY fail_count ASC, last_used_at ASC, id ASC`)
	if err != nil {
		return nil, false
	}
	defer rows.Close()
	for rows.Next() {
		var a CookieAccount
		if err := rows.Scan(&a.ID, &a.Label, &a.Cookie, &a.Status, &a.Note,
			&a.CreatedAt, &a.LastUsedAt, &a.LastOkAt, &a.LastError, &a.FailCount, &a.ProxyID); err != nil {
			continue
		}
		if skip[a.ID] {
			continue
		}
		_, _ = getDB().Exec(`UPDATE accounts SET last_used_at=? WHERE id=?`, time.Now().Unix(), a.ID)
		return &a, true
	}
	return nil, false
}

// markCookieByStatus writes back cookie health based on the upstream response.
//
// Only clear authentication failures (401/403) count as the cookie's fault. Network errors,
// proxy failures, and 302 → sorry (IP blocked by Google) are all excluded — measured,
// residential-proxy egress degradation runs up to 75%; counting those into fail_count turns it into proxy noise, and good cookies get wrongly flagged as "most failed".
//
// A statusCode of 0 means no response was ever obtained (network-layer failure).
func markCookieByStatus(id int64, statusCode int, errStr string) {
	switch {
	case statusCode == 200:
		markAccountResult(id, true, "")
	case statusCode == 401 || statusCode == 403:
		markAccountResult(id, false, errStr)
	default:
		// In all other cases the fault is not the cookie's; leave its health alone
	}
}

// markAccountResult writes the result back after a request: success resets fail_count and
// records last_ok_at; failure increments fail_count and records last_error.
//
// Note the semantics of last_ok_at: "a request using this cookie once succeeded" — **not
// "the cookie is still valid"**: after expiry Gemini doesn't error, it just treats you as
// anonymous, and plain-text requests still get 200. To truly validate, the cheapest criterion is
// requesting gemini-3.1-pro: with a valid cookie the server reports "3.1 Pro" with a reasoning
// chain; when dead, it silently downgrades to 3.5 Flash-Lite. (xsrf.go also judges the cookie dead on the spot when the page contains no SNlM0e while fetching the token.)
func markAccountResult(id int64, ok bool, errStr string) {
	if id <= 0 {
		return
	}
	if ok {
		_, _ = getDB().Exec(
			`UPDATE accounts SET last_ok_at=?, fail_count=0, last_error='' WHERE id=?`,
			time.Now().Unix(), id)
		return
	}
	_, _ = getDB().Exec(
		`UPDATE accounts SET fail_count=fail_count+1, last_error=? WHERE id=?`,
		truncate(errStr, 200), id)
	autoDisableIfDead(id)
}

// maxCookieAuthFailures is how many consecutive auth failures disable an account.
//
// Only 401/403 increments fail_count (see markCookieByStatus); network errors and Google blocks
// don't count, so 3 in a row basically means the cookie is truly gone. 3, not 1: an occasional
// XSRF page hiccup also lands on this path, and disabling on one hit would be a false kill.
const maxCookieAuthFailures = 3

// autoDisableIfDead disables an account once its consecutive failures max out.
//
// Why auto-disable: picking sorts by `ORDER BY fail_count ASC` — bad accounts sort last, but
// **when only bad ones remain, they still get picked**, so every request has to try one before
// erroring. And fail_count only resets on success, so a dead account never heals on its own — every request pays one XSRF round trip for it.
//
// Disable, don't delete: cookies are user-imported data and the judgment can be wrong (e.g.
// a repeatedly blocked egress can also look like an auth failure); leave it visible in the panel for the user to decide.
func autoDisableIfDead(id int64) {
	var fails int64
	var status string
	err := getDB().QueryRow(`SELECT fail_count, status FROM accounts WHERE id=?`, id).
		Scan(&fails, &status)
	if err != nil || status != "enabled" || fails < maxCookieAuthFailures {
		return
	}
	if _, err := getDB().Exec(
		`UPDATE accounts SET status='disabled' WHERE id=? AND status='enabled'`, id); err == nil {
		logf("[cookie] 账号 #%d 连续 %d 次鉴权失败，已自动停用", id, fails)
	}
}

// CookieCheck is the result of one cookie validity check.
type CookieCheck struct {
	OK        bool   `json:"ok"`
	Detail    string `json:"detail"`
	ProxyName string `json:"proxy_name"`
	TookMs    int64  `json:"took_ms"`
}

// checkAccountCookie reports whether a cookie still has a signed-in state.
//
// The criterion is whether the /app page contains SNlM0e: when a cookie is dead Gemini doesn't
// error, it just treats you as anonymous, and plain-text requests still get 200 — so "request
// succeeded" cannot be the validity criterion. No SNlM0e on this page means the server didn't recognize the signed-in state.
//
// Only fetches the page; sends no conversation and consumes no generation quota.
func checkAccountCookie(a CookieAccount) CookieCheck {
	t0 := time.Now()
	picked, ok, err := acquireSlot(a.ProxyID)
	if !ok {
		return CookieCheck{Detail: "拿不到出口：" + err.Error()}
	}
	defer releaseSlot(picked.ID)
	proxyURL := picked.URL
	name := picked.Name
	if name == "" {
		name = "直连"
	}

	// Invalidate the cache first — otherwise a stale conclusion from minutes ago makes the check pointless
	invalidateXSRF(a.Cookie)
	_, err = getXSRF(a.Cookie, proxyURL)
	took := time.Since(t0).Milliseconds()
	if err != nil {
		markAccountResult(a.ID, false, err.Error())
		return CookieCheck{Detail: explainCookieFailure(err), ProxyName: name, TookMs: took}
	}
	markAccountResult(a.ID, true, "")
	detail := "登录态有效"
	if extractSAPISID(a.Cookie) == "" {
		detail += "，但缺 SAPISID（算不出授权头，部分接口会被当匿名）"
	}
	return CookieCheck{OK: true, Detail: detail, ProxyName: name, TookMs: took}
}

// explainCookieFailure translates low-level errors into conclusions ops can understand.
func explainCookieFailure(err error) string {
	msg := err.Error()
	switch {
	case strings.Contains(msg, "no SNlM0e"):
		return "cookie 已失效：页面能打开但没有登录态，请求会被当匿名处理"
	case strings.Contains(msg, "HTTP 302"):
		return "cookie 无效：被重定向到登录页"
	case strings.Contains(msg, "HTTP 429"), strings.Contains(msg, "sorry"):
		return "出口被上游限流，换个代理再试（不是 cookie 的问题）"
	default:
		return "检测失败：" + msg
	}
}

// bindAccountProxy remembers which egress this account used, preferring the same next time.
func bindAccountProxy(accountID, proxyID int64) {
	if accountID <= 0 {
		return
	}
	_, _ = getDB().Exec(`UPDATE accounts SET proxy_id=? WHERE id=?`, proxyID, accountID)
}

// accountDisplayName is the account name shown in the panel/records; falls back to #id without a label.
func accountDisplayName(a *CookieAccount) string {
	if a.Label != "" {
		return a.Label
	}
	return fmt.Sprintf("#%d", a.ID)
}

// mergeSetCookie merges the response's Set-Cookie values into the existing cookie string.
//
// Nearly every server response refreshes SIDCC / __Secure-1PSIDCC / __Secure-3PSIDCC (468
// refreshes from batchexecute alone in a 2-hour capture), which the browser stores and sends
// back. A client that keeps sending stale values is judged an expired session — measured, accounts die within one to two hours without merging.
//
// Original order preserved, new keys appended: cookie order itself carries no semantics, but
// keeping it stable stops content-based comparisons like poolHasCookie from seeing a new value every time.
func mergeSetCookie(cookie string, setCookie []string) string {
	if len(setCookie) == 0 {
		return cookie
	}
	updates := map[string]string{}
	for _, sc := range setCookie {
		first := strings.TrimSpace(strings.SplitN(sc, ";", 2)[0])
		i := strings.Index(first, "=")
		if i <= 0 {
			continue
		}
		name, val := first[:i], first[i+1:]
		// A delete directive (expiry in the past + empty value) must not be written as a new value
		if val == "" && strings.Contains(strings.ToLower(sc), "expires=thu, 01 jan 1970") {
			continue
		}
		updates[name] = val
	}
	if len(updates) == 0 {
		return cookie
	}
	var parts []string
	seen := map[string]bool{}
	for _, kv := range splitCookiePairs(cookie) {
		seen[kv[0]] = true
		if v, ok := updates[kv[0]]; ok {
			parts = append(parts, kv[0]+"="+v)
			continue
		}
		parts = append(parts, kv[0]+"="+kv[1])
	}
	for name, val := range updates {
		if !seen[name] {
			parts = append(parts, name+"="+val)
		}
	}
	return strings.Join(parts, "; ")
}

// cookieIdentity returns the entries that identify "which account this is".
//
// SAPISID computes the authorization header and __Secure-1PSID is the session primary key;
// neither changes on refresh (0 changes in a 2-hour capture; only the *SIDCC and *SIDTS
// families do). So if they changed, the cookie is no longer the same account.
func cookieIdentity(cookie string) string {
	var sapisid, psid string
	for _, kv := range splitCookiePairs(cookie) {
		switch kv[0] {
		case "SAPISID":
			sapisid = kv[1]
		case "__Secure-1PSID":
			psid = kv[1]
		}
	}
	return sapisid + "|" + psid
}

// updateAccountCookie writes the refreshed cookie back to the account.
//
// Identity is compared before writing: when merging Set-Cookie, the upstream could in theory
// swap the whole session (e.g. the response carries another account's SID); accepting it
// wholesale writes account A's credentials into account B's row. Afterwards the row still
// shows the old label while actually sending someone else's session — **completely silent**. On an identity mismatch, don't write; better to waste this refresh.
func updateAccountCookie(id int64, cookie string) {
	if id <= 0 || cookie == "" {
		return
	}
	var cur string
	if err := getDB().QueryRow(`SELECT cookie FROM accounts WHERE id=?`, id).Scan(&cur); err == nil {
		if got, want := cookieIdentity(cookie), cookieIdentity(cur); got != want {
			logf("[cookie] 账号 #%d 的刷新结果身份对不上，已丢弃不写回", id)
			return
		}
	}
	_, _ = getDB().Exec(`UPDATE accounts SET cookie=? WHERE id=?`, cookie, id)
}
