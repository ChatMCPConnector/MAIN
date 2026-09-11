package app

import (
	"strings"
	"testing"
)

// Criterion: when the prompt exceeds the per-request cap, **error explicitly** —
// never silently modify content.
//
// When over-length, the upstream silently truncates from the **tail** without error,
// and the latest message is assembled last, so what gets eaten is exactly what the
// user just asked — the model sees only the system preamble up front, replies with a
// generic opener, answering nothing and calling no tools. Observed in practice: users
// of two different clients fell into this, both mistaking it for "the model got dumber".
//
// Silently dropping history ourselves is equally wrong: that's still silently losing
// data, just in a different place. The client believes the whole thing went out while
// the model has forgotten things. Reporting context_length_exceeded is a signal
// OpenAI-compatible clients recognize; agentic clients compress their context and
// retry on their own.

func withBudget(t *testing.T, n int) { // n = byte budget
	t.Helper()
	old := rtCfg()
	next := old
	next.MaxPromptBytes = n
	rtMu.Lock()
	rtVal = next
	rtMu.Unlock()
	t.Cleanup(func() {
		rtMu.Lock()
		rtVal = old
		rtMu.Unlock()
	})
}

func longConversation(turns int) []map[string]interface{} {
	msgs := []map[string]interface{}{
		{"role": "system", "content": "你是一个 helpful assistant。"},
	}
	for i := 0; i < turns; i++ {
		msgs = append(msgs,
			map[string]interface{}{"role": "user", "content": strings.Repeat("历史填充内容。", 20)},
			map[string]interface{}{"role": "assistant", "content": "Noted."})
	}
	return append(msgs, map[string]interface{}{"role": "user", "content": "读取一下 task.md"})
}

func TestPromptOverLimitErrors(t *testing.T) {
	withBudget(t, 20000) // bytes

	prompt, _ := messagesToPrompt(longConversation(200), nil, nil)
	if len(prompt) <= 20000 {
		t.Fatalf("the test case itself is not over budget (%d bytes)", len(prompt))
	}
	// the error must explain why it was rejected, otherwise users just blame us
	noCookie := error(&PromptTooLongError{Bytes: len(prompt), Budget: 20000})
	for _, want := range []string{"truncates", "latest message", "not tokens"} {
		if !strings.Contains(noCookie.Error(), want) {
			t.Errorf("error message is missing %q: %v", want, noCookie)
		}
	}
	// without a cookie this isn't a dead end: tell the user importing one enables the attachment path
	for _, want := range []string{"Cookie pool", "attachment"} {
		if !strings.Contains(noCookie.Error(), want) {
			t.Errorf("without a cookie it should hint at importing one, missing %q: %v", want, noCookie)
		}
	}
	// over limit despite a cookie = the attachment path couldn't rescue it either, so stop telling people to import a cookie
	withCookie := error(&PromptTooLongError{Bytes: len(prompt), Budget: 20000, HasCookie: true})
	if strings.Contains(withCookie.Error(), "Cookie pool") {
		t.Error("hints at importing a cookie even though one is already configured")
	}
	if !strings.Contains(withCookie.Error(), "Shorten") {
		t.Error("with a cookie it should hint at shortening the content")
	}
}

// Under the limit, not a single character may change — including no "part of the history omitted"-style injection.
func TestPromptUnderLimitUntouched(t *testing.T) {
	withBudget(t, 10000000)
	msgs := longConversation(3)

	got, _ := messagesToPrompt(msgs, nil, nil)
	if want := buildPrompt(msgs, nil, nil); got != want {
		t.Error("the prompt was changed despite being under the limit")
	}
	if !strings.Contains(got, "读取一下 task.md") {
		t.Error("the latest question is not in the prompt")
	}
}

// 0 = check disabled, reverting to legacy behavior (send verbatim; the upstream truncates the tail).
func TestPromptLimitDisabled(t *testing.T) {
	withBudget(t, 0)
	msgs := longConversation(200)

	got, _ := messagesToPrompt(msgs, nil, nil)
	if len(got) < 20000 {
		t.Error("there must be no truncation once the check is disabled")
	}
}

// The cap applies to the **whole prompt**, tool definitions included — agentic
// clients' tool schemas are often larger than the conversation itself; leaving them
// out means no defense at all.
func TestPromptLimitCountsToolDefs(t *testing.T) {
	withBudget(t, 5000)
	tools := []map[string]interface{}{{"type": "function", "function": map[string]interface{}{
		"name": "read_file", "description": strings.Repeat("一个很长的工具描述。", 300),
		"parameters": map[string]interface{}{"type": "object"}}}}
	msgs := []map[string]interface{}{{"role": "user", "content": "你好"}}

	if p, _ := messagesToPrompt(msgs, tools, nil); len(p) <= 5000 {
		t.Errorf("tool definitions should push the prompt above 5000 bytes, actually %d", len(p))
	}
}
