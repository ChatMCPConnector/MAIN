package app

import (
	"os"
	"path/filepath"
	"testing"
)

// TestMain points the DB at a temp directory before running tests.
//
// hasCookie() now only looks at the cookie pool, i.e. queries the DB; without taking
// over cfg.DBPath, getDB() would open the real ./data/gemini.db and tests would
// read/write production data.
func TestMain(m *testing.M) {
	dir, err := os.MkdirTemp("", "gw2a-test-")
	if err != nil {
		panic(err)
	}
	cfg.DBPath = filepath.Join(dir, "test.db")
	code := m.Run()
	_ = os.RemoveAll(dir)
	os.Exit(code)
}

// withPoolCookie inserts a test account into the cookie pool, auto-deleted afterwards.
// Replaces the old cookieRuntime.Store — that single-cookie path has been removed.
func withPoolCookie(t *testing.T) {
	t.Helper()
	id, err := accountAdd("test", "SAPISID=dummy; SID=x", "")
	if err != nil {
		t.Fatalf("插测试 cookie 失败: %v", err)
	}
	t.Cleanup(func() { _ = accountDelete(id) })
}
