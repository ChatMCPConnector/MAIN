package app

import (
	"os"
	"strings"
	"testing"
)

// A connectivity probe against the real upstream; runs only when GW2A_UPLOAD_PROBE=<proxyURL> is set.
// Regular go test skips it — uploads need a page token and a real egress, which the
// closed environment of unit tests can't provide.
func TestUploadProbe(t *testing.T) {
	proxy := os.Getenv("GW2A_UPLOAD_PROBE")
	if proxy == "" {
		t.Skip("GW2A_UPLOAD_PROBE not set")
	}
	text := "PANTE-UPLOAD-PROBE\n" + strings.Repeat("这是一段用于验证上传链路的文本。\n", 50)
	ref, err := uploadBytes("", proxy, []byte(text), "context.txt")
	if err != nil {
		t.Fatalf("upload failed: %v", err)
	}
	t.Logf("upload succeeded, reference path = %s", ref)
	if !strings.HasPrefix(ref, "/") {
		t.Errorf("reference path has the wrong shape: %q", ref)
	}
}
