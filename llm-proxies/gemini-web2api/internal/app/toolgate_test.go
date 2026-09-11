package app

import (
	"strings"
	"testing"
)

// feed pushes the whole text through the gate with a given chunking and returns what
// actually reaches the client. The chunking must be arbitrary: where upstream frame
// boundaries fall is entirely out of our control, and the gate's result must not differ.
func feed(t *testing.T, chunks []string) string {
	t.Helper()
	var got strings.Builder
	g := newToolFenceGate(func(s string) { got.WriteString(s) })
	for _, c := range chunks {
		g.Push(c)
	}
	if got.String() != g.Sent() {
		t.Fatalf("Sent() 和实际发出的对不上: %q vs %q", g.Sent(), got.String())
	}
	return got.String()
}

// Feeding byte-by-byte is the harshest chunking: every character is a new frame, so half fences are bound to hit frame boundaries.
func chars(s string) []string {
	var out []string
	for _, r := range s {
		out = append(out, string(r))
	}
	return out
}

func TestToolFenceGate(t *testing.T) {
	cases := []struct {
		name string
		full string
		want string
	}{
		{"没有围栏就原样发", "你好，今天天气不错。", "你好，今天天气不错。"},
		{
			"围栏前后的正文都要发，围栏本身扣住",
			"让我查一下。\n```tool_call\n{\"name\": \"get_weather\", \"arguments\": {}}\n```\n查完了。",
			"让我查一下。\n\n查完了。",
		},
		{
			"整段都是围栏则一个字都不发",
			"```tool_call\n{\"name\": \"f\", \"arguments\": {}}\n```",
			"",
		},
		{
			"连着两个围栏",
			"a\n```tool_call\n{\"name\":\"f\"}\n```\nb\n```tool_call\n{\"name\":\"g\"}\n```\nc",
			"a\n\nb\n\nc",
		},
		{
			// ordinary code blocks are not tool_call and must not be held back
			"普通代码块照常发",
			"看这段：\n```python\nprint(1)\n```\n就这样。",
			"看这段：\n```python\nprint(1)\n```\n就这样。",
		},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			// all three chunkings must yield the same result
			if got := feed(t, []string{c.full}); got != c.want {
				t.Errorf("整段喂: 得到 %q，期望 %q", got, c.want)
			}
			if got := feed(t, chars(c.full)); got != c.want {
				t.Errorf("逐字符喂: 得到 %q，期望 %q", got, c.want)
			}
			mid := len(c.full) / 2
			for mid < len(c.full) && !isRuneStart(c.full[mid]) {
				mid++
			}
			if got := feed(t, []string{c.full[:mid], c.full[mid:]}); got != c.want {
				t.Errorf("对半喂: 得到 %q，期望 %q", got, c.want)
			}
		})
	}
}

func isRuneStart(b byte) bool { return b&0xC0 != 0x80 }

// What the gate emits + the final text from parseToolCalls must reassemble into the
// same content — the criterion for streaming and non-streaming consistency.
func TestToolFenceGateMatchesParse(t *testing.T) {
	full := "让我查一下。\n```tool_call\n{\"name\": \"get_weather\", \"arguments\": {\"city\": \"London\"}}\n```\n查完了。"

	streamed := feed(t, chars(full))
	final, calls := parseToolCalls(full)

	if len(calls) != 1 || calls[0].Function.Name != "get_weather" {
		t.Fatalf("工具调用没解析出来: %+v", calls)
	}
	// what streaming emits may carry extra leading/trailing whitespace (parseToolCalls TrimSpaces at the end).
	if strings.TrimSpace(streamed) != final {
		t.Errorf("流式发出 %q，最终文本 %q", strings.TrimSpace(streamed), final)
	}
}

// An unclosed fence: the gate holds it back; remainingOf restores it at the end, so the client loses nothing.
func TestToolFenceGateUnclosed(t *testing.T) {
	full := "开始了。\n```tool_call\n{\"name\": \"f\""
	streamed := feed(t, chars(full))
	if streamed != "开始了。\n" {
		t.Fatalf("扣住的部分不对: %q", streamed)
	}
	// parseToolCalls leaves unclosed fences alone, keeping them verbatim in the text
	final, calls := parseToolCalls(full)
	if len(calls) != 0 {
		t.Fatalf("未闭合围栏不该解析出工具调用: %+v", calls)
	}
	if rest := remainingOf(final, streamed); rest == "" {
		t.Error("收尾补发算出来是空的，扣住的内容会丢")
	}
}

func TestPartialPrefixLen(t *testing.T) {
	m := toolFenceOpen // "```tool_call"
	for _, c := range []struct {
		s    string
		want int
	}{
		{"abc", 0},
		{"abc`", 1},
		{"abc``", 2},
		{"abc```", 3},
		{"abc```tool_c", 9},
		{"", 0},
		{"中文`", 1}, // the split point must land on ASCII, never splitting a multi-byte character
		{"中文", 0},
	} {
		if got := partialPrefixLen(c.s, m); got != c.want {
			t.Errorf("partialPrefixLen(%q) = %d，期望 %d", c.s, got, c.want)
		}
	}
}
