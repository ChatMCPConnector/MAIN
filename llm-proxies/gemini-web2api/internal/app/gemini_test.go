package app

import (
	"fmt"
	"strings"
	"sync"
	"testing"
)

// Verify that each model name resolves to the correct hex id and header value.
func TestModelHeader(t *testing.T) {
	withPoolCookie(t) // make 3.1 Pro selectable, see TestProHiddenWithoutCookie

	cases := []struct{ name, wantHex string }{
		{"gemini-3.6-flash", hexFlash36},
		{"gemini-3.5-flash-lite", hexFlashLite},
		{"gemini-3.1-pro", hexPro31},
	}
	for _, c := range cases {
		name, mc, err := resolveModel(c.name)
		if err != nil {
			t.Fatalf("%s: %v", c.name, err)
		}
		if mc.HexID != c.wantHex {
			t.Errorf("%s: hex=%s want %s", c.name, mc.HexID, c.wantHex)
		}
		h := buildGeminiHeaders("", "", mc.HexID)
		got := h["x-goog-ext-525001261-jspb"]
		want := `[1,null,null,null,"` + c.wantHex + `"]`
		if got != want {
			t.Errorf("%s: header=%s want %s", c.name, got, want)
		}
		t.Logf("%-32s -> mode=%d header=%s", name, mc.Mode, got)
	}

	// @think=N is a legacy fake parameter: strip it and ignore, no error and no routing change
	name, mc, err := resolveModel("gemini-3.6-flash@think=2")
	if err != nil || name != "gemini-3.6-flash" || mc.HexID != hexFlash36 {
		t.Errorf("@think suffix should be ignored, got name=%s hex=%s err=%v", name, mc.HexID, err)
	}
	// unknown models must still error, no silent fallback
	if _, _, err := resolveModel("no-such-model"); err == nil {
		t.Error("unknown model should error")
	}
	// removed legacy aliases must explicitly error, not silently fall back to 3.6 Flash
	for _, gone := range []string{"gemini-3.5-flash", "gemini-3.5-flash-thinking",
		"gemini-3.5-flash-thinking-lite", "gemini-auto", "gemini-flash-lite"} {
		if _, _, err := resolveModel(gone); err == nil {
			t.Errorf("removed alias %s should error", gone)
		}
	}
	// the invariant guarded here is "no fake models may appear": thinking versions reuse
	// the same hex, so count **deduplicated hexes**, not entries. The server list (otAQ7b)
	hexes := map[string]bool{}
	for _, m := range Models {
		hexes[m.HexID] = true
	}
	if len(hexes) != 4 {
		t.Errorf("only 4 real model hexes should exist, got %d", len(hexes))
	}
	// and conversely: every real hex should have a thinking version
	for _, base := range []string{hexFlash36, hexFlashLite, hexPro31, hexFlash38} {
		found := false
		for _, m := range Models {
			if m.HexID == base && m.Thinking {
				found = true
			}
		}
		if !found {
			t.Errorf("hex %s lacks a thinking variant", base)
		}
	}
}

// A real "rejected" response from a packet capture: only an end frame, no content
// frame (216 bytes). Note the end frame carries BardErrorInfo[1096], but end frames
// present or not".
const rejectedRaw = ")]}'\n\n122\n" +
	`[["wrb.fr",null,null,null,null,[13,null,[["type.googleapis.com/assistant.boq.bard.application.BardErrorInfo",[1096]]]]]]` +
	"\n56\n" + `[["di",192],["af.httprm",191,"8196459853603899163",2]]` +
	"\n25\n" + `[["e",4,null,null,216]]` + "\n"

// A normal response: content frame present, [39] is the model hex id, [42] the
const okRaw = ")]}'\n\n900\n" +
	`[["wrb.fr",null,"[null,[\"c_x\",\"r_y\"],null,null,[[\"rc_z\",[\"banana\"],null,null,null,null,null,null,[2],\"en\"]],null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,\"fbb127bbb056c959\",null,null,\"3.6 Flash\",true]"]]` +
	"\n122\n" +
	`[["wrb.fr",null,null,null,null,[13,null,[["type.googleapis.com/assistant.boq.bard.application.BardErrorInfo",[1096]]]]]]` + "\n"

func TestEmptyFrameDetection(t *testing.T) {
	if got := extractResponseText(rejectedRaw); got != "" {
		t.Errorf("rejected response should parse to empty text, got %q", got)
	}
	if got := extractResponseText(okRaw); got != "banana" {
		t.Errorf("normal response should parse to banana, got %q", got)
	}
}

// usage must match the requests table's accounting (both use tiktoken), never
func TestUsageUsesTokenizer(t *testing.T) {
	initTokenizer()
	// pick a sample where tiktoken and chars/4 clearly differ, otherwise the
	prompt := "请详细解释注意力机制的计算过程，并说明多头注意力为什么有效。"
	text := "自注意力通过查询、键、值三组投影计算token之间的相关性权重。"

	if tokenizerOK && countTokens(prompt) == len(prompt)/4 {
		t.Skipf("sample has no discriminative power (tiktoken and chars/4 both %d), pick another sample", countTokens(prompt))
	}

	u := buildUsage(prompt, text, false)
	if u["prompt_tokens"] != countTokens(prompt) || u["completion_tokens"] != countTokens(text) {
		t.Errorf("chat usage did not go through countTokens: %v", u)
	}
	if u["total_tokens"] != u["prompt_tokens"]+u["completion_tokens"] {
		t.Errorf("total is not the sum of both: %v", u)
	}
	if tokenizerOK && u["prompt_tokens"] == len(prompt)/4 {
		t.Errorf("prompt_tokens landed on chars/4, still the old implementation: %v", u)
	}

	r := buildUsage(prompt, text, true)
	if r["input_tokens"] != countTokens(prompt) || r["output_tokens"] != countTokens(text) {
		t.Errorf("responses usage did not go through countTokens: %v", r)
	}
	if _, ok := r["prompt_tokens"]; ok {
		t.Error("responses API must not contain a prompt_tokens field")
	}
}

func TestToolChoice(t *testing.T) {
	for _, c := range []struct {
		in         interface{}
		mode, name string
	}{
		{nil, "auto", ""},
		{"auto", "auto", ""},
		{"none", "none", ""},
		{"required", "required", ""},
		{map[string]interface{}{"type": "function",
			"function": map[string]interface{}{"name": "get_weather"}}, "required", "get_weather"},
		{"garbage", "auto", ""},
	} {
		m, n := parseToolChoice(c.in)
		if m != c.mode || n != c.name {
			t.Errorf("%v -> (%s,%s) want (%s,%s)", c.in, m, n, c.mode, c.name)
		}
	}

	tools := []map[string]interface{}{
		{"type": "function", "function": map[string]interface{}{"name": "get_weather"}},
		{"type": "function", "function": map[string]interface{}{"name": "send_email"}},
	}
	msgs := []map[string]interface{}{{"role": "user", "content": "hi"}}

	// none: tool definitions never enter the prompt at all
	if p := mustPrompt(t, msgs, tools, "none"); strings.Contains(p, "get_weather") {
		t.Errorf("tool_choice=none must not inject tool definitions: %s", p)
	}
	// required: the forcing wording must appear
	p := mustPrompt(t, msgs, tools, "required")
	if !strings.Contains(p, "MUST call one of the tools") {
		t.Errorf("tool_choice=required is missing the forcing instruction: %s", p)
	}
	// named function: keep only that function and call it out by name
	p = mustPrompt(t, msgs, tools, map[string]interface{}{"type": "function",
		"function": map[string]interface{}{"name": "get_weather"}})
	if !strings.Contains(p, `MUST call the tool "get_weather"`) {
		t.Errorf("named function is missing the forcing instruction: %s", p)
	}
	if strings.Contains(p, "send_email") {
		t.Errorf("named function must not include other tools: %s", p)
	}
	// auto: keep the original permissive wording
	if p := mustPrompt(t, msgs, tools, "auto"); !strings.Contains(p, "when needed") {
		t.Errorf("auto should keep the permissive wording: %s", p)
	}
}

// Core streaming invariant: all deltas concatenated must equal the final text
func TestDeltaTrackerAccumulates(t *testing.T) {
	// the upstream sends the accumulated full text per frame, growing frame by frame
	frames := []string{
		"Transformer",
		"Transformer 的核心",
		"Transformer 的核心是自注意力",
		"Transformer 的核心是自注意力机制。",
	}
	d := &deltaTracker{}
	var got string
	for _, f := range frames {
		got += d.Push(f)
	}
	want := cleanGeminiText(frames[len(frames)-1])
	if got != want {
		t.Errorf("delta concatenation=%q want %q", got, want)
	}
	if d.emitted != want {
		t.Errorf("emitted=%q want %q", d.emitted, want)
	}

		// a repeated frame must not be emitted again
	if extra := d.Push(frames[len(frames)-1]); extra != "" {
		t.Errorf("a repeated frame must not produce a delta, got %q", extra)
	}
		// a shorter frame (out-of-order arrival) isn't emitted either
	if extra := d.Push("Transformer"); extra != "" {
		t.Errorf("a shorter frame must not produce a delta, got %q", extra)
	}
		// when the prefix doesn't match, skip; emitted stays unchanged
	before := d.emitted
	if extra := d.Push("完全不同的一段文本，比原来的还要长很多很多很多很多"); extra != "" {
		t.Errorf("a non-prefix frame must not produce a delta, got %q", extra)
	}
	if d.emitted != before {
		t.Errorf("a non-prefix frame must not change emitted")
	}

	// remainingText fills in the tail the tracker skipped
	full := want + "补充的尾巴"
	if r := remainingText(full, &StreamResult{Emitted: d.emitted}); r != "补充的尾巴" {
		t.Errorf("remainingText=%q want %q", r, "补充的尾巴")
	}
	// non-true-streaming (empty Emitted) should return the full text
	if r := remainingText(full, &StreamResult{}); r != full {
		t.Errorf("empty Emitted should return the full text")
	}
	// when the prefix doesn't match, don't re-send, to avoid duplication
	if r := remainingText("另一段内容", &StreamResult{Emitted: d.emitted}); r != "" {
		t.Errorf("prefix mismatch must not re-send, got %q", r)
	}
}

// The server silently downgrades (an anonymous 3.1 Pro request actually returns
// 3.5 Flash-Lite); that's undetectable from the request name alone, so the
func TestExtractUpstreamModel(t *testing.T) {
	if got := extractUpstreamModel(okRaw); got != "3.6 Flash" {
		t.Errorf("normal response should yield '3.6 Flash', got %q", got)
	}
	// model names with an "扩展" (extended) suffix must be extracted whole, not truncated at the space
	downgraded := `[["wrb.fr",null,"[null,[\"c_x\",\"r_y\"],null,null,[[\"rc_z\",[\"hi\"]]],null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,\"fbb127bbb056c959\",null,null,\"3.6 Flash 扩展\",true]"]]`
	if got := extractUpstreamModel(downgraded); got != "3.6 Flash 扩展" {
		t.Errorf("should yield '3.6 Flash 扩展', got %q", got)
	}
	// rejected responses carry no model name; no guessing allowed
	if got := extractUpstreamModel(rejectedRaw); got != "" {
		t.Errorf("rejected response should return empty, got %q", got)
	}
}

// Without a cookie configured, 3.1 Pro is invariably silently downgraded to
// Flash-Lite, so we'd rather not expose it at all: the client gets a clear error
// (With a valid cookie it genuinely works, see the availableModels comment.)
func TestProHiddenWithoutCookie(t *testing.T) {
	// the cookie pool is empty at this point (TestMain provides a fresh temp DB)
	if _, ok := availableModels()["gemini-3.1-pro"]; ok {
		t.Error("3.1 Pro must not be exposed without a cookie")
	}
	// inner[80] (extended thinking) only takes effect when logged in; sent
	// anonymously the server silently ignores it, so thinking versions can't be
	for name, m := range availableModels() {
		if m.Thinking {
			t.Errorf("thinking variants must not be exposed without a cookie: %s", name)
		}
	}
	if len(availableModels()) != 2 {
		t.Errorf("only 2 models should remain without a cookie, got %d", len(availableModels()))
	}
	_, _, err := resolveModel("gemini-3.1-pro")
	if err == nil {
		t.Fatal("selecting 3.1 Pro without a cookie should error")
	}
	// the error message must explain why and what to do, not just "unknown model"
	if !strings.Contains(err.Error(), "cookie") ||
		!strings.Contains(err.Error(), "downgraded") ||
		!strings.Contains(err.Error(), "admin panel") {
		t.Errorf("error message does not explain the cause and the fix: %v", err)
	}

	withPoolCookie(t)
	if _, ok := availableModels()["gemini-3.1-pro"]; !ok {
		t.Error("3.1 Pro should be exposed with a cookie configured")
	}
	if _, _, err := resolveModel("gemini-3.1-pro"); err != nil {
		t.Errorf("should not error with a cookie configured: %v", err)
	}
	for _, n := range []string{"gemini-3.6-flash-thinking", "gemini-3.5-flash-lite-thinking",
		"gemini-3.1-pro-thinking"} {
		if _, ok := availableModels()[n]; !ok {
			t.Errorf("%s should be exposed with a cookie configured", n)
		}
	}
	// a model that truly doesn't exist is still "unknown model"; the cookie hint must not mask it
	if _, _, err := resolveModel("no-such-model"); err == nil ||
		!strings.Contains(err.Error(), "unknown model") {
		t.Errorf("unknown model should report unknown model, got %v", err)
	}
}

// modelNeedsLogin is the single shared criterion for "which models to exclude
// without a cookie" and "whether anon-first (#20) should occupy an account",
func TestModelNeedsLogin(t *testing.T) {
	anon := map[string]bool{"gemini-3.6-flash": true, "gemini-3.5-flash-lite": true}
	for name, mc := range Models {
		want := !anon[name]
		if got := modelNeedsLogin(mc); got != want {
			t.Errorf("%s: modelNeedsLogin=%v want %v", name, got, want)
		}
	}
	// must match availableModels' exclusion criteria: what's exposed without a cookie
	for name := range availableModels() {
		if modelNeedsLogin(Models[name]) {
			t.Errorf("%s is exposed by availableModels but judged as needing login; the two criteria disagree", name)
		}
	}
}

// health derivation for cookieAcctView (#18 panel red marking): fail_count>0 is
// always red (including dead accounts auto-disabled), manually disabled with no
func TestCookieHealthView(t *testing.T) {
	cases := []struct {
		a    CookieAccount
		want string
	}{
		{CookieAccount{Status: "enabled", FailCount: 0, LastOkAt: 100}, "ok"},
		{CookieAccount{Status: "enabled", FailCount: 3, LastOkAt: 100}, "dead"},
		{CookieAccount{Status: "disabled", FailCount: 5, LastOkAt: 100}, "dead"},
		{CookieAccount{Status: "disabled", FailCount: 0}, "disabled"},
		{CookieAccount{Status: "enabled", FailCount: 0, LastOkAt: 0}, "unknown"},
	}
	for _, c := range cases {
		if got := cookieAcctView(c.a)["health"]; got != c.want {
			t.Errorf("status=%s fail=%d ok=%d: health=%v want %s",
				c.a.Status, c.a.FailCount, c.a.LastOkAt, got, c.want)
		}
	}
}

// pickCookieAccount's SELECT+UPDATE must be atomic: N accounts picked by N
// concurrent requests, each must get a distinct account. Without locking, two
// (running with -race exposes this more easily.)
func TestPickCookieConcurrentDistinct(t *testing.T) {
	const n = 8
	for i := 0; i < n; i++ {
		id, err := accountAdd("conc", fmt.Sprintf("SAPISID=d%d; SID=x", i), "")
		if err != nil {
			t.Fatalf("failed to insert account: %v", err)
		}
		t.Cleanup(func() { _ = accountDelete(id) })
	}

	got := make([]int64, n)
	var wg sync.WaitGroup
	start := make(chan struct{})
	for i := 0; i < n; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			<-start
			if a, ok := pickCookieAccount(); ok {
				got[idx] = a.ID
			}
		}(i)
	}
		close(start) // make all goroutines rush the pick simultaneously
	wg.Wait()

	seen := map[int64]int{}
	for _, id := range got {
		seen[id]++
	}
	for id, c := range seen {
		if c > 1 {
			t.Errorf("account #%d was picked %d times concurrently; picking is not serialized", id, c)
		}
	}
}

// Account-picking criterion for anon-first (#20): with the switch off, always
// false (legacy behavior); with it on, only plain-text, non-thinking, toolless,
func TestAnonFirstEligible(t *testing.T) {
	set := func(on bool) { rtMu.Lock(); rtVal.AnonFirst = on; rtMu.Unlock() }
	defer set(false)

	plain := Models["gemini-3.6-flash"]
	pro := Models["gemini-3.1-pro"]
	img := Models["gemini-image"]
	think := Models["gemini-3.6-flash-thinking"]

	set(false)
	if anonFirstEligible(plain, false) {
		t.Error("with the switch off it must always be false (use an account when the pool has one)")
	}

	set(true)
	if !anonFirstEligible(plain, false) {
		t.Error("on + plain text without attachments should go anonymous")
	}
	if anonFirstEligible(plain, true) {
		t.Error("attachments must pick an account (anonymous references are rejected upstream with 1100)")
	}
	if anonFirstEligible(pro, false) {
		t.Error("3.1 Pro needs login, cannot go anonymous")
	}
	if anonFirstEligible(img, false) {
		t.Error("image generation needs login, cannot go anonymous")
	}
	if anonFirstEligible(think, false) {
		t.Error("extended thinking needs login, cannot go anonymous")
	}
}

// Error classification must follow "what to do upon seeing it", especially
// separating "transient upstream rejection" from "egress blocked" — the former
func TestClassifyError(t *testing.T) {
	for _, c := range []struct{ in, want string }{
		{"", ""},
		{"upstream returned no content frame (raw 381 bytes)", "upstream_rejected"},
		{"direct IP slot full: rpm limit reached (configure proxies to scale)", "rate_limited_local"},
		{"all proxy slots full: rph limit reached", "rate_limited_local"},
		{"upstream HTTP 302: <HTML><HEAD><meta ...", "blocked_sorry"},
		{"upstream HTTP 429: too many requests", "upstream_429"},
		{"upstream HTTP 500: internal", "upstream_http_error"},
		{"unknown model: gemini-9", "bad_request"},
		{"image input not supported: ...", "bad_request"},
		{"dial tcp 1.2.3.4:10000: connectex: connection refused", "network"},
		{"remote error: tls: handshake failure", "network"},
	} {
		if got := classifyError(c.in); got != c.want {
			t.Errorf("classifyError(%q) = %q, want %q", c.in, got, c.want)
		}
	}
}

// mustPrompt is a test convenience wrapper: messagesToPrompt now returns an error
func mustPrompt(t *testing.T, msgs []map[string]interface{}, tools []map[string]interface{},
	toolChoice interface{}) string {
	t.Helper()
	p, _ := messagesToPrompt(msgs, tools, toolChoice)
	return p
}
