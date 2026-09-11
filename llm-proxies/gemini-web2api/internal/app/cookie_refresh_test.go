package app

import (
	"strings"
	"testing"
)

// The server refreshes SIDCC / __Secure-1PSIDCC / __Secure-3PSIDCC on nearly every
// response; the client must accept them and send them back. Keeping stale values gets
// the session judged expired — observed in practice: accounts die within an hour or two.
func TestMergeSetCookie(t *testing.T) {
	base := "SID=a; SAPISID=b; SIDCC=old1; __Secure-1PSIDCC=old2; __Secure-1PSID=c"

	got := mergeSetCookie(base, []string{
		"SIDCC=new1; expires=Sat, 07 Aug 2027 00:00:00 GMT; path=/; secure",
		"__Secure-1PSIDCC=new2; path=/; secure; httponly",
	})
	for _, want := range []string{"SIDCC=new1", "__Secure-1PSIDCC=new2"} {
		if !strings.Contains(got, want) {
			t.Errorf("没刷新 %q: %s", want, got)
		}
	}
	// items not re-issued must be preserved verbatim — dropping one shaves a piece off the login state
	for _, want := range []string{"SID=a", "SAPISID=b", "__Secure-1PSID=c"} {
		if !strings.Contains(got, want) {
			t.Errorf("丢了 %q: %s", want, got)
		}
	}
	if strings.Contains(got, "old1") || strings.Contains(got, "old2") {
		t.Errorf("旧值没被替换掉: %s", got)
	}
}

// New keys appearing in the response must be appended, not lost.
func TestMergeSetCookieAddsNew(t *testing.T) {
	got := mergeSetCookie("SID=a", []string{"__Secure-3PSIDCC=fresh; path=/"})
	if !strings.Contains(got, "SID=a") || !strings.Contains(got, "__Secure-3PSIDCC=fresh") {
		t.Errorf("新键没追加: %s", got)
	}
}

// Deletion directives (empty value + 1970 expiry) must not be written in as new values, otherwise an intact cookie gets wiped.
func TestMergeSetCookieIgnoresDeletion(t *testing.T) {
	got := mergeSetCookie("SID=a; SIDCC=keepme",
		[]string{"SIDCC=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/"})
	if !strings.Contains(got, "SIDCC=keepme") {
		t.Errorf("删除指令把值清掉了: %s", got)
	}
}

// Without Set-Cookie, return as-is — otherwise every request reorders the cookie
// string, and content-based comparisons (poolHasCookie / --cookie-file dedup) misjudge it as changed.
func TestMergeSetCookieNoop(t *testing.T) {
	base := "SID=a; SAPISID=b"
	if got := mergeSetCookie(base, nil); got != base {
		t.Errorf("空输入却改了串: %q", got)
	}
	if got := mergeSetCookie(base, []string{"garbage-without-equals"}); got != base {
		t.Errorf("无法解析的 Set-Cookie 却改了串: %q", got)
	}
}

// Values containing '=' (base64 padding) must not be split apart.
func TestMergeSetCookieKeepsEquals(t *testing.T) {
	got := mergeSetCookie("SID=a", []string{"SIDCC=AB==; path=/"})
	if !strings.Contains(got, "SIDCC=AB==") {
		t.Errorf("值里的等号被切坏: %s", got)
	}
}
