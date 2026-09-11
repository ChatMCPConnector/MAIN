package app

import (
	"strings"
	"testing"
	"time"
)

// readBody's end-marker detection: the classic [["e",… frame and the new [{"37":[0]}] tail frame.
func TestIsStreamEndLine(t *testing.T) {
	cases := []struct {
		line string
		want bool
	}{
		{`[["e",4,null,null,216]]`, true},
		{`[["e",4,null,null,138]]`, true},
		{`[["wrb.fr",null,"[{\"37\":[0]}]"]]`, true},
		{`[["wrb.fr",null,"[null,[\"c_x\",\"r_y\"],null,null,[[\"rc_z\",[\"hi\"]]]]"]]`, false},
		{`[["di",192],["af.httprm",191,"8196459853603899163",2]]`, false},
		{")]} '", false},
		{"", false},
		{`[["wrb.fr",null,"[null,null,null,null,null,[13,null,[["type.googleapis.com/assistant.boq.bard.application.BardErrorInfo",[1096]]]]]]"]`, false},
	}
	for _, c := range cases {
		if got := isStreamEndLine(c.line); got != c.want {
			t.Errorf("isStreamEndLine(%s) = %v, want %v", c.line, got, c.want)
		}
	}
}

// Half-open connection scenario: after content frames + end tail frame there's no
// EOF — readBody must actively wrap up after the grace period and return what it
// read (without error).
func TestReadBodyHalfOpenTerminates(t *testing.T) {
	r := strings.NewReader(")]}'\n\n123\n" +
		`[["wrb.fr",null,"[null,[\"c_x\",\"r_y\"],null,null,[[\"rc_z\",[\"Hello!\"]]]]"]]` + "\n" +
		"36\n" + `[["wrb.fr",null,"[{\"37\":[0]}]"]]` + "\n")
	// Reader hat kein EOF-Problem, aber der Test verifiziert trotzdem: nach dem
	// End-Marker kehrt readBody nach streamEndGrace (+Puffer) zurück.
	t0 := time.Now()
	raw, _, err := readBody(r, func(string) {}, t0)
	if err != nil {
		t.Fatalf("readBody sollte bei End-Marker ohne Fehler zurückkehren: %v", err)
	}
	if !strings.Contains(string(raw), "Hello!") {
		t.Errorf("Inhalt fehlt: %d bytes", len(raw))
	}
	if !strings.Contains(string(raw), `\"37\":[0]`) {
		t.Errorf("End-Marker fehlt im gelesenen Body")
	}
}

// Content frames without an end marker + immediate EOF: normal behavior is kept.
func TestReadBodyNormalEOF(t *testing.T) {
	r := strings.NewReader("line1\nline2\n")
	raw, ttfb, err := readBody(r, nil, time.Now())
	if err != nil {
		t.Fatalf("normales EOF darf kein Fehler sein: %v", err)
	}
	if string(raw) != "line1\nline2\n" {
		t.Errorf("raw = %q", string(raw))
	}
	if ttfb < 0 {
		t.Errorf("ttfb sollte gesetzt sein, got %d", ttfb)
	}
}

// onLine-Callback: jede Zeile wird einmal geliefert.
func TestReadBodyOnLine(t *testing.T) {
	r := strings.NewReader("a\nb\nc\n")
	var lines []string
	_, _, err := readBody(r, func(s string) { lines = append(lines, s) }, time.Now())
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if len(lines) != 3 || lines[0] != "a" || lines[2] != "c" {
		t.Errorf("lines = %v", lines)
	}
}