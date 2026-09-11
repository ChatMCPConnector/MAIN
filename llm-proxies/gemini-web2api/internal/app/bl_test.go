package app

import "testing"

// cfb2h is scraped from the upstream page's HTML — external input going straight
// into a URL. Shape validation guards against "page structure changed, the regex
// grabbed something else" — a bad scrape should keep using the pinned value from
// config, not assemble a request with a garbage string.
func TestBLValueShape(t *testing.T) {
	good := []string{
		"boq_assistant-bard-web-server_20260805.16_p0", // current value observed in practice
		"boq_assistant-bard-web-server_20260525.09_p0", // our pinned value
		"boq_assistant-bard-web-server_20260802.16_p12",
	}
	for _, s := range good {
		if !blValueRe.MatchString(s) {
			t.Errorf("should pass but was rejected: %q", s)
		}
	}

	bad := []string{
		"",
		"boq_assistant-bard-web-server", // missing version segment
		"boq_assistant-bard-web-server_2026080.16_p0",    // 7-digit date
		"boq_assistant-bard-web-server_20260805.163_p0",  // 3-digit minor version
		"boq_assistant-bard-web-server_20260805.16_p",    // no digits after p
		"boq_assistant-other-server_20260805.16_p0",      // different service name
		"boq_assistant-bard-web-server_20260805.16_p0&x", // trailing URL parameter
		"../../etc/passwd",
	}
	for _, s := range bad {
		if blValueRe.MatchString(s) {
			t.Errorf("should be rejected but passed: %q", s)
		}
	}
}

// cfb2hRe must extract the value precisely from the big inline-JSON blob of a real page.
func TestCfb2hExtract(t *testing.T) {
	page := `...,"cfb2h":"boq_assistant-bard-web-server_20260805.16_p0","fJfDgd":"x",...`
	m := cfb2hRe.FindStringSubmatch(page)
	if m == nil {
		t.Fatal("no cfb2h match")
	}
	if want := "boq_assistant-bard-web-server_20260805.16_p0"; m[1] != want {
		t.Errorf("got %q, want %q", m[1], want)
	}
}
