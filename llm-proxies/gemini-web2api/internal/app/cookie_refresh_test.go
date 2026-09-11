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
			t.Errorf("did not refresh %q: %s", want, got)
		}
	}
	// items not re-issued must be preserved verbatim — dropping one shaves a piece off the login state
	for _, want := range []string{"SID=a", "SAPISID=b", "__Secure-1PSID=c"} {
		if !strings.Contains(got, want) {
			t.Errorf("lost %q: %s", want, got)
		}
	}
	if strings.Contains(got, "old1") || strings.Contains(got, "old2") {
		t.Errorf("old value was not replaced: %s", got)
	}
}

// New keys appearing in the response must be appended, not lost.
func TestMergeSetCookieAddsNew(t *testing.T) {
	got := mergeSetCookie("SID=a", []string{"__Secure-3PSIDCC=fresh; path=/"})
	if !strings.Contains(got, "SID=a") || !strings.Contains(got, "__Secure-3PSIDCC=fresh") {
		t.Errorf("new key not appended: %s", got)
	}
}

// Deletion directives (empty value + 1970 expiry) must not be written in as new values, otherwise an intact cookie gets wiped.
func TestMergeSetCookieIgnoresDeletion(t *testing.T) {
	got := mergeSetCookie("SID=a; SIDCC=keepme",
		[]string{"SIDCC=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/"})
	if !strings.Contains(got, "SIDCC=keepme") {
		t.Errorf("a delete directive cleared the value: %s", got)
	}
}

// Without Set-Cookie, return as-is — otherwise every request reorders the cookie
// string, and content-based comparisons (poolHasCookie / --cookie-file dedup) misjudge it as changed.
func TestMergeSetCookieNoop(t *testing.T) {
	base := "SID=a; SAPISID=b"
	if got := mergeSetCookie(base, nil); got != base {
		t.Errorf("empty input changed the string: %q", got)
	}
	if got := mergeSetCookie(base, []string{"garbage-without-equals"}); got != base {
		t.Errorf("an unparseable Set-Cookie changed the string: %q", got)
	}
}

// Values containing '=' (base64 padding) must not be split apart.
func TestMergeSetCookieKeepsEquals(t *testing.T) {
	got := mergeSetCookie("SID=a", []string{"SIDCC=AB==; path=/"})
	if !strings.Contains(got, "SIDCC=AB==") {
		t.Errorf("the equals sign in the value got cut: %s", got)
	}
}
