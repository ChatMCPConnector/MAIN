package app

import (
	"os"
	"path/filepath"
	"testing"
)

// This group tests **what happens when an already-running DB is upgraded**: all
// criteria revolve around one thing: a user's existing proxies / cookies must never
// vanish or silently get duplicated during the upgrade.

func resetSeedState(t *testing.T) {
	t.Helper()
	clean := func() {
		for _, a := range accountList() {
			_ = accountDelete(a.ID)
		}
		for _, p := range listProxies() {
			_ = proxyDelete(p.ID)
		}
		for _, k := range []string{
			"google_cookie", runtimeConfigKey,
			kvLegacyCookieDone, kvSeededCookieID, kvSeededCookieVal,
			kvLegacyProxyDone, kvSeededProxyID, kvSeededProxyURL,
		} {
			_ = kvSet(k, "")
		}
		cfg.CookieFile = ""
		cfg.Proxy = ""
	}
	clean()
	t.Cleanup(clean)
}

// ── One-time migration of legacy values ─────────────────────────────────

func TestMigrateLegacyCookie(t *testing.T) {
	resetSeedState(t)
	const raw = "SAPISID=legacy; SID=y"
	mustKV(t, "google_cookie", raw)

	seedCookiesFromConfig()

	list := accountList()
	if len(list) != 1 || list[0].Cookie != raw {
		t.Fatalf("not migrated into the pool: %+v", list)
	}
	// the original value is kept: rolling back to the old version leaves that single cookie still working, behavior unchanged
	if kvGet("google_cookie") != raw {
		t.Errorf("the original kv value must not be touched")
	}

	// after the user deletes it from the pool, a restart must not resurrect it
	_ = accountDelete(list[0].ID)
	seedCookiesFromConfig()
	if n := len(accountList()); n != 0 {
		t.Errorf("resurrected after deletion; the pool still has %d entries", n)
	}
}

// A cookie lacking SAPISID must still be accepted: the old version sent it verbatim as the
// Cookie header, and whether it works is up to the upstream. An upgrade must not silently
// revert the user's account to anonymous just because we added a new validation.
func TestMigrateLegacyCookieWithoutSAPISID(t *testing.T) {
	resetSeedState(t)
	const raw = "SID=only; HSID=x; __Secure-1PSID=z"
	mustKV(t, "google_cookie", raw)

	seedCookiesFromConfig()

	list := accountList()
	if len(list) != 1 || list[0].Cookie != raw {
		t.Fatalf("blocked just for missing SAPISID; users would become anonymous after upgrading: %+v", list)
	}
	if !hasCookie() {
		t.Error("the pool has accounts but hasCookie is false")
	}
	// but manually adding the same value via the panel must still be blocked — the user sees the error right there
	if _, err := accountAdd("手工", raw, ""); err == nil {
		t.Error("manual panel adds must not accept a cookie lacking SAPISID")
	}
}

// A failed migration must **not** be marked done, otherwise the user's cookie never gets another chance to enter the pool.
func TestMigrateLegacyCookieBadValueKeepsRetrying(t *testing.T) {
	resetSeedState(t)
	// JSON form but no cookie field extractable: normalizeCookie judges it failed
	mustKV(t, "google_cookie", `{"sapisid":"x"}`)

	seedCookiesFromConfig()

	if n := len(accountList()); n != 0 {
		t.Fatalf("must not enter the pool, actually %d entries", n)
	}
	if kvGet(kvLegacyCookieDone) == "1" {
		t.Error("migration marked done despite failing to enter the pool; the user's cookie never gets another chance")
	}
	if kvGet("google_cookie") == "" {
		t.Error("original value cleared despite failing to enter the pool, i.e. outright data loss")
	}
}

// scheme is case-insensitive: url.Parse lowercases the scheme, so the uppercase form worked
// on the 4.0.0 unvalidated static-proxy path and must not be blocked during upgrade.
func TestProxySchemeCaseInsensitive(t *testing.T) {
	resetSeedState(t)
	mustKV(t, runtimeConfigKey, `{"proxy":"HTTP://1.2.3.4:8080"}`)

	seedProxiesFromConfig()

	list := listProxies()
	if len(list) != 1 || list[0].URL != "HTTP://1.2.3.4:8080" {
		t.Fatalf("uppercase scheme blocked; the user's proxy stops working after upgrade: %+v", list)
	}
}

// A value missing its scheme is indeed rejected by proxyCreate; this ensures rejection
// doesn't lose the original value or mark the migration done.
//
// Unlike the cookie path (where validation was relaxed): a bare host:port value never
// actually worked on 4.0.0 — url.Parse errors on it directly (first path segment in URL
// cannot contain colon), the proxy stays nil, and requests go direct. So rejecting it
// isn't a functional regression; no relaxation needed.
func TestMigrateLegacyProxyRejectedKeepsRetrying(t *testing.T) {
	resetSeedState(t)
	mustKV(t, runtimeConfigKey, `{"proxy":"1.2.3.4:8080","per_ip_rph":80}`)

	seedProxiesFromConfig()

	if n := len(listProxies()); n != 0 {
		t.Fatalf("a value missing its scheme must not enter the pool, actually %d entries", n)
	}
	if kvGet(kvLegacyProxyDone) == "1" {
		t.Error("migration marked done despite failing to enter the pool")
	}
	// the original runtime_config must not be touched at all: it holds other fields too
	if got := kvGet(runtimeConfigKey); got != `{"proxy":"1.2.3.4:8080","per_ip_rph":80}` {
		t.Errorf("runtime_config was rewritten: %s", got)
	}
}

func TestMigrateLegacyProxyOK(t *testing.T) {
	resetSeedState(t)
	mustKV(t, runtimeConfigKey, `{"proxy":"http://u:p@1.2.3.4:8080","per_ip_rph":80}`)

	seedProxiesFromConfig()

	list := listProxies()
	if len(list) != 1 || list[0].URL != "http://u:p@1.2.3.4:8080" {
		t.Fatalf("not migrated into the pool: %+v", list)
	}
	// migration doesn't rewrite runtime_config — one less write to existing data means one less risk of corrupting other fields
	if got := kvGet(runtimeConfigKey); got != `{"proxy":"http://u:p@1.2.3.4:8080","per_ip_rph":80}` {
		t.Errorf("runtime_config was rewritten: %s", got)
	}
	// idempotent: a second startup must not add another entry
	seedProxiesFromConfig()
	if n := len(listProxies()); n != 1 {
		t.Errorf("a second startup added another entry; the pool has %d", n)
	}
}

// ── Declarative following of startup parameters ────────────────────────

// Changing --proxy in compose should **replace** that entry, not add another. With accumulation,
// the old egress would stay in the pool, still enabled and still taking traffic — a zombie egress.
func TestSeededProxyReplacedOnChange(t *testing.T) {
	resetSeedState(t)
	cfg.Proxy = "http://old:1080"
	seedProxiesFromConfig()
	if list := listProxies(); len(list) != 1 || list[0].URL != "http://old:1080" {
		t.Fatalf("first seeding is wrong: %+v", list)
	}

	cfg.Proxy = "http://new:1080" // user changed compose and restarted
	seedProxiesFromConfig()

	list := listProxies()
	if len(list) != 1 {
		t.Fatalf("should be replaced with 1 entry, actually %d: %+v", len(list), list)
	}
	if list[0].URL != "http://new:1080" {
		t.Errorf("changed to %s, want http://new:1080", list[0].URL)
	}

	// parameter removed entirely → the entry we created gets withdrawn too
	cfg.Proxy = ""
	seedProxiesFromConfig()
	if n := len(listProxies()); n != 0 {
		t.Errorf("should be withdrawn after removing --proxy; the pool still has %d entries", n)
	}
}

// When the parameter is unchanged, don't touch the pool at all: if the user disabled/deleted the entry in the panel, that decision stands.
func TestSeededProxyRespectsPanelEdits(t *testing.T) {
	resetSeedState(t)
	cfg.Proxy = "http://seed:1080"
	seedProxiesFromConfig()
	id := listProxies()[0].ID

	no := false
	if err := proxyUpdate(id, "", "", &no, nil); err != nil { // user disabled it in the panel
		t.Fatal(err)
	}
	seedProxiesFromConfig() // restart

	list := listProxies()
	if len(list) != 1 {
		t.Fatalf("the pool must not be touched, actually %d entries", len(list))
	}
	if list[0].Enabled {
		t.Error("a record the user disabled was re-enabled")
	}
}

// When the user has already added the same egress in the panel, seeding must not create a duplicate entry.
func TestSeededProxySkipsExistingURL(t *testing.T) {
	resetSeedState(t)
	if _, err := proxyCreate("手工加的", "http://same:1080", 1); err != nil {
		t.Fatal(err)
	}
	cfg.Proxy = "http://same:1080"
	seedProxiesFromConfig()
	if n := len(listProxies()); n != 1 {
		t.Errorf("the same URL created %d entries", n)
	}
}

// --cookie-file rotation: replace the same entry, never accumulate. A pile of dead cookies still
// enabled and still in rotation means one doomed request every N.
func TestSeededCookieFileRotates(t *testing.T) {
	resetSeedState(t)
	path := filepath.Join(t.TempDir(), "cookie.txt")
	write := func(s string) {
		if err := os.WriteFile(path, []byte(s), 0o600); err != nil {
			t.Fatal(err)
		}
	}
	cfg.CookieFile = path

	write("  SAPISID=first; SID=z\n")
	seedCookiesFromConfig()
	seedCookiesFromConfig() // a second startup with unchanged content
	list := accountList()
	if len(list) != 1 {
		t.Fatalf("unchanged content must not be re-inserted, actually %d entries", len(list))
	}
	if list[0].Cookie != "SAPISID=first; SID=z" {
		t.Errorf("leading/trailing whitespace not stripped: %q", list[0].Cookie)
	}

	write("SAPISID=rotated; SID=z")
	seedCookiesFromConfig()
	list = accountList()
	if len(list) != 1 {
		t.Fatalf("should still be 1 entry after rotation, actually %d: %+v", len(list), list)
	}
	if list[0].Cookie != "SAPISID=rotated; SID=z" {
		t.Errorf("not switched to the new one: %q", list[0].Cookie)
	}
}

// When the file can't be read (e.g. a volume missing from the container), keep the current state — don't withdraw a cookie that's actively in use.
func TestSeededCookieFileMissingKeepsPool(t *testing.T) {
	resetSeedState(t)
	dir := t.TempDir()
	path := filepath.Join(dir, "cookie.txt")
	if err := os.WriteFile(path, []byte("SAPISID=live; SID=z"), 0o600); err != nil {
		t.Fatal(err)
	}
	cfg.CookieFile = path
	seedCookiesFromConfig()
	if len(accountList()) != 1 {
		t.Fatal("precondition not met")
	}

	_ = os.Remove(path) // volume not mounted
	seedCookiesFromConfig()

	if n := len(accountList()); n != 1 {
		t.Errorf("the cookie was withdrawn just because the file is unreadable; the pool has %d left", n)
	}
}

// The legacy single-cookie path accepted JSON form; before entering the pool it must be normalized
// into a bare cookie string, otherwise the pool stores a whole JSON blob and SAPISID extraction
// and subsequent requests all break.
func TestMigrateLegacyCookieJSONForm(t *testing.T) {
	resetSeedState(t)
	mustKV(t, "google_cookie", `{"cookie":"SAPISID=fromjson; SID=w","sapisid":"fromjson"}`)

	seedCookiesFromConfig()

	list := accountList()
	if len(list) != 1 {
		t.Fatalf("should have 1 entry, actually %d", len(list))
	}
	if list[0].Cookie != "SAPISID=fromjson; SID=w" {
		t.Errorf("JSON was not normalized: %q", list[0].Cookie)
	}
	if got := extractSAPISID(list[0].Cookie); got != "fromjson" {
		t.Errorf("SAPISID not extractable after entering the pool: %q", got)
	}
}

// Fresh deployment: no legacy config at all, no accounts or proxies must be created out of thin air.
func TestSeedNoop(t *testing.T) {
	resetSeedState(t)
	seedCookiesFromConfig()
	seedProxiesFromConfig()
	if n := len(accountList()); n != 0 {
		t.Errorf("no new account should be created, actually %d entries", n)
	}
	if n := len(listProxies()); n != 0 {
		t.Errorf("no new proxy should be created, actually %d entries", n)
	}
	if hasCookie() {
		t.Error("hasCookie should be false when the pool is empty")
	}
}

func mustKV(t *testing.T, k, v string) {
	t.Helper()
	if err := kvSet(k, v); err != nil {
		t.Fatal(err)
	}
}
