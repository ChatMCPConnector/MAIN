package app

import (
	"os"
	"testing"
)

// Uses a real captured web-search response to verify grounding sources get parsed.
func TestExtractGrounding(t *testing.T) {
	raw, err := os.ReadFile("testdata/search_raw.txt")
	if err != nil {
		t.Skipf("no testdata/search_raw.txt, skipping: %v", err)
	}
	sources := extractGrounding(string(raw))
	if len(sources) == 0 {
		t.Fatal("this response should have web search sources, but none were parsed")
	}
	for i, s := range sources {
		if s.URL == "" {
			t.Errorf("source %d has an empty URL", i)
		}
		if idx := len(s.URL); idx > 0 && contains(s.URL, "#:~:text=") {
			t.Errorf("source %d's URL still carries the #:~:text= fragment: %s", i, s.URL)
		}
		t.Logf("source %d: %s | %s", i, s.Title, s.URL)
	}
}

func contains(s, sub string) bool {
	return len(s) >= len(sub) && (indexOf(s, sub) >= 0)
}

func indexOf(s, sub string) int {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return i
		}
	}
	return -1
}
