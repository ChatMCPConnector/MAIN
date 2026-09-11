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
		t.Skip("未设 GW2A_UPLOAD_PROBE")
	}
	text := "PANTE-UPLOAD-PROBE\n" + strings.Repeat("这是一段用于验证上传链路的文本。\n", 50)
	ref, err := uploadBytes("", proxy, []byte(text), "context.txt")
	if err != nil {
		t.Fatalf("上传失败: %v", err)
	}
	t.Logf("上传成功，引用路径 = %s", ref)
	if !strings.HasPrefix(ref, "/") {
		t.Errorf("引用路径形状不对: %q", ref)
	}
}
