package app

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"regexp"
	"strings"
)

// randHex returns n random hex chars. Equivalent to Python's
// `uuid.uuid4().hex[:n]` — produces a pure hex string of length n.
//
// Note: Go's `uuid.NewString()` returns the dashed 8-4-4-4-12 format,
// so naive slicing like `uuid.NewString()[:12]` would yield 11 hex + 1 dash.
// We sidestep that by drawing fresh random bytes.
func randHex(n int) string {
	b := make([]byte, (n+1)/2)
	_, _ = rand.Read(b)
	return hex.EncodeToString(b)[:n]
}

type ToolCall struct {
	ID       string           `json:"id"`
	Type     string           `json:"type"`
	Function ToolCallFunction `json:"function"`
}

type ToolCallFunction struct {
	Name      string `json:"name"`
	Arguments string `json:"arguments"`
}

// messagesToPrompt converts OpenAI messages[] (+ optional tools[]) to a single
// prompt string for Gemini. Tool schemas are embedded as a system instruction
// telling the model to emit ```tool_call``` blocks.
//
// toolChoice is OpenAI's tool_choice field ("none"/"auto"/"required" or
// {"type":"function","function":{"name":...}}). The upstream has no
// protocol-level tool calling, so the constraint has to be written into the
// instruction. "required" is especially necessary: measured in practice,
// Gemini answers questions it can handle itself (like weather lookups)
// directly without calling a tool; without forcing, no tool_call is produced.
// Returns (assembled prompt, latest user message).
//
// The over-length check is not done here — with a cookie attached, an
// oversized prompt is converted into a text attachment, and whether that is
// possible can only be known after the account and egress (proxy) have been
// picked, so the check lives in streamGenerate. The latest message is
// returned separately so it can be inlined when converting to an attachment,
// sparing the model from having to dig through the file for the question.
func messagesToPrompt(messages []map[string]interface{}, tools []map[string]interface{},
	toolChoice interface{}) (string, string) {
	return buildPrompt(messages, tools, toolChoice), latestUserMessage(messages)
}

// latestUserMessage returns the body of the last user message, or an empty
// string if there is none.
func latestUserMessage(messages []map[string]interface{}) string {
	for i := len(messages) - 1; i >= 0; i-- {
		role := getStr(messages[i], "role")
		if role == "user" || role == "" {
			if c := strings.TrimSpace(contentToString(messages[i]["content"])); c != "" {
				return c
			}
		}
	}
	return ""
}

// toolsReminderBlock builds the compact re-anchor for multi-turn continuation
// turns: the format rule + the full tool definitions.
//
// Why the tool definitions must be resent too: the upstream's context window
// is limited, and the multi-turn server-side history pushes the first turn's
// tool definitions out (measured in practice, around turn 9 the model starts
// answering "I don't have filesystem tools" — it remembers it must emit the
// fence, but can no longer see which tools exist). So every turn carries the
// schema: a few hundred bytes to keep tool discipline from slipping.
func toolsReminderBlock(tools []map[string]interface{}) string {
	if len(tools) == 0 {
		return ""
	}
	var defs []map[string]interface{}
	for _, tool := range tools {
		fn := tool
		if t, ok := tool["type"].(string); ok && t == "function" {
			if f, ok := tool["function"].(map[string]interface{}); ok {
				fn = f
			}
		}
		defs = append(defs, map[string]interface{}{
			"name":        getStr(fn, "name"),
			"description": getStr(fn, "description"),
			"parameters":  fn["parameters"],
		})
	}
	defsJSON, _ := json.MarshalIndent(defs, "", "  ")
	return "[System instruction — highest priority]: Remember: to run a command or " +
		"read a file you MUST output a ```tool_call``` block — this is the ONLY " +
		"execution channel. A ```bash/```python code block is NOT executed. Reply with " +
		"exactly ONE ```tool_call``` block and nothing else. " +
		"If (and only if) the request is fully accomplished and needs no tool, " +
		"reply with a short final answer instead.\n\n" +
		"Available tools (still active in this session):\n" + string(defsJSON)
}

func buildPrompt(messages []map[string]interface{}, tools []map[string]interface{},
	toolChoice interface{}) string {
	var parts []string

	toolsInjected := false
	mode, forced := parseToolChoice(toolChoice)
	if len(tools) > 0 && mode != "none" {
		var defs []map[string]interface{}
		for _, tool := range tools {
			fn := tool
			if t, ok := tool["type"].(string); ok && t == "function" {
				if f, ok := tool["function"].(map[string]interface{}); ok {
					fn = f
				}
			}
			name := getStr(fn, "name")
if forced != "" && name != forced {
			continue // a function name was specified; the rest stays out of the prompt
		}
			defs = append(defs, map[string]interface{}{
				"name":        name,
				"description": getStr(fn, "description"),
				"parameters":  fn["parameters"],
			})
		}
		if len(defs) > 0 {
			defsJSON, _ := json.MarshalIndent(defs, "", "  ")
			rule := "Only use tool_call blocks when needed."
			switch {
			case forced != "":
				rule = fmt.Sprintf(
					"You MUST call the tool %q. Reply with the tool_call block and nothing "+
						"else — do not answer the question yourself, even if you know the answer.",
					forced)
			case mode == "required":
				rule = "You MUST call one of the tools above. Reply with the tool_call block " +
					"and nothing else — do not answer the question yourself, even if you " +
					"know the answer."
			}
			parts = append(parts, fmt.Sprintf(
				"[System instruction]: You have access to tools. "+
					"To call a tool, respond with:\n"+
					"```tool_call\n{\"name\": \"func_name\", \"arguments\": {...}}\n```\n"+
					"%s\n\n"+
					"Available tools:\n%s", rule, string(defsJSON),
			))
			toolsInjected = true
		}
	}

	for _, msg := range messages {
		role := getStr(msg, "role")
		content := contentToString(msg["content"])

		switch role {
		case "system":
			parts = append(parts, "[System instruction]: "+content)
		case "assistant":
			if tcs, ok := msg["tool_calls"].([]interface{}); ok && len(tcs) > 0 {
				var tcStrs []string
				for _, tc := range tcs {
					tcMap, ok := tc.(map[string]interface{})
					if !ok {
						continue
					}
					fn, _ := tcMap["function"].(map[string]interface{})
					name := getStr(fn, "name")
					args := getStr(fn, "arguments")
					if args == "" {
						args = "{}"
					}
					tcStrs = append(tcStrs, fmt.Sprintf(
						"```tool_call\n{\"name\": \"%s\", \"arguments\": %s}\n```",
						name, args,
					))
				}
				parts = append(parts, "[Assistant]: "+content+"\n"+strings.Join(tcStrs, "\n"))
			} else {
				parts = append(parts, "[Assistant]: "+content)
			}
		case "tool":
			parts = append(parts, formatToolResult(getStr(msg, "name"), content))
		default:
			if content != "" {
				parts = append(parts, content)
			}
		}
	}

	// The tool format instruction goes first, but developer prompts from agentic
	// clients (Codex/rikkahub etc.) easily run 40KB and carry their own wording
	// like "emit function calls" from native tool frameworks, burying the format
	// instruction at the top when squeezed in between — the model then either
	// answers "I have no tools" or answers off-topic (the "reads but replies
	// garbage" users reported).
	// Evidence: replaying a real 42KB Codex prompt as-is, the model said "cannot
	// access the local filesystem" and emitted no fence; appending the reminder
	// at the end of the same prompt made it emit ```tool_call``` immediately.
	// So the format is re-anchored once more at the end, stating explicitly
	// "there is no other tool channel", to override the client's native framing.
	// Two further data points (weak model anon 3.6 Flash, multi-command task,
	// 4 runs each):
	//  ① format instruction only, no example: 0/4 hits, all degenerated into
	//     writing ```powershell code blocks to show the user;
	//  ② with one concrete example of "user asks X → the correct reply is this
	//     tool_call block": 3-4/4 hits.
	// So a behavioral few-shot is required. The example uses a neutral tool
	// name (run_command); measured in practice the model still used the real
	// tool name (shell_command), copying the fake name 0/4 — the example
	// teaches the "action", not the name, so there is no need to generate the
	// schema dynamically per client.
	if toolsInjected {
		parts = append(parts,
			"[System instruction — highest priority]: To run a command or read a file you MUST "+
				"output a ```tool_call``` block — this is the ONLY execution channel. A "+
				"```powershell/```bash/```cmd/```python code block is NOT executed, it is only shown "+
				"to the user; never use one to run anything, and never claim you lack tools.\n"+
				"Act, do not explain: when the request needs a tool, your reply is ONE ```tool_call``` "+
				"block and nothing else — do not list the commands you 'would' run, do not output more "+
				"than one tool_call, do not add prose. If several steps are needed, do the FIRST one "+
				"now; you will be called again with its result to continue.\n"+
				"Know when to STOP: once a tool result shows a step succeeded (for example it exited "+
				"with code 0, even with no printed output), that step is DONE — do not run it again and "+
				"do not retry the same thing a different way. When the whole request is accomplished, "+
				"stop calling tools and reply with a short final answer instead of another tool_call.\n"+
				"Example of a correct turn — user asks \"list the files here and tell me the size of "+
				"README.md\", you reply with exactly one block and nothing else:\n"+
				"```tool_call\n{\"name\": \"run_command\", \"arguments\": {\"command\": \"ls -la\"}}\n```\n"+
				"(In your block use one of the real tool names listed above with its own arguments.) "+
				"When the request needs a tool, emit the tool_call block now.")
	}

	var nonEmpty []string
	for _, p := range parts {
		if p != "" {
			nonEmpty = append(nonEmpty, p)
		}
	}
	return strings.Join(nonEmpty, "\n\n")
}

func contentToString(content interface{}) string {
	switch v := content.(type) {
	case string:
		return v
	case []interface{}:
		var bits []string
		for _, c := range v {
			cm, ok := c.(map[string]interface{})
			if !ok {
				continue
			}
			t := getStr(cm, "type")
			if t == "text" || t == "input_text" {
				bits = append(bits, getStr(cm, "text"))
			}
		}
		return strings.Join(bits, " ")
	default:
		return ""
	}
}

func getStr(m map[string]interface{}, k string) string {
	if m == nil {
		return ""
	}
	if s, ok := m[k].(string); ok {
		return s
	}
	return ""
}

// exitCodeRe digs the exit code out of a tool result. Codex's shell result is
// a wrapper text containing "Process exited with code N".
var exitCodeRe = regexp.MustCompile(`(?i)exit(?:ed with|\s*code)?\s*(?:code\s*)?(\d+)`)

// formatToolResult renders a tool result into the prompt; the key is making
	// weak models recognize "success".
	//
	// Why rewrite it: a successful result from an agentic client (Codex) looks
	// like this —
	//
	//	Chunk ID: 0cdbf0\nWall time: 0.07s\nProcess exited with code 0\nOriginal token count: 0\nOutput:\n
	//
	// Commands like file writes/setting values have no stdout, so "Output:" is
	// followed by nothing. Weak models (anon 3.6 Flash) take "no output" as
	// "didn't work" and retry with a different formulation over and over —
	// measured in practice, the task "write hello to a.txt" saw 26 command
	// variants in one run without converging after 90s, while the file was
	// actually written correctly the first time. The exit 0 was right there in
	// the result, but buried under noise like Chunk ID / Wall time / token
	// count, and nothing told it "no output is normal". Here it is compressed
	// into one clean success/failure signal, explicitly stating that no output
	// is normal and that it must not rerun.
	//
	// Adding only the stop instruction (the "Know when to STOP" sentence in the
	// reminder) did not help in practice (26→27 commands); only together with
	// this clean signal does it suppress the loop.
func formatToolResult(name, raw string) string {
	label := "Tool result"
	if name != "" {
		label = "Tool result for " + name
	}
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return fmt.Sprintf("[%s]: ✅ 完成，无输出（正常，动作已生效，不要重复执行）。", label)
	}
	// Codex-style wrapper: the real stdout follows the trailing "Output:".
	out := trimmed
	if i := strings.LastIndex(trimmed, "Output:"); i >= 0 {
		out = strings.TrimSpace(trimmed[i+len("Output:"):])
	}
	if m := exitCodeRe.FindStringSubmatch(trimmed); m != nil {
		if m[1] == "0" {
			if out == "" {
				return fmt.Sprintf("[%s]: ✅ 命令成功（exit 0），无文本输出——这对写文件/设值类命令是正常的，动作已完成，不要再跑同一条命令。", label)
			}
			return fmt.Sprintf("[%s]: ✅ 命令成功（exit 0）。输出：\n%s", label, out)
		}
		return fmt.Sprintf("[%s]: ❌ 命令失败（exit %s）。输出：\n%s", label, m[1], out)
	}
	return fmt.Sprintf("[%s]: %s", label, raw)
}

const (
	toolFenceOpen  = "```tool_call"
	toolFenceClose = "```"
)

// toolFenceGate lets requests with tools stream for real.
	//
	// Problem: the upstream has no protocol-level tool calling; we make the
	// model emit ```tool_call``` fences, and a fence needs the complete text
	// to parse. Forwarding as it streams would push the raw fence text to the
	// client — the client would see a markdown code block, not tool_calls. So
	// this path used to degrade into receive-then-send.
	//
	// Solution: only send the parts that are **certainly not part of a
	// fence**. Everything inside a fence is held back and converted into
	// tool_calls by parseToolCalls at the end. The tricky part is that the
	// tail may hold half of an opening fence (e.g. only two backticks, or cut
	// off at "tool_c") — that part must also be held back for the next frame —
	// otherwise it gets sent first, and only the next frame reveals it was
	// the start of a fence, while what was already sent cannot be taken back.
	//
	// Sent() is the text **actually sent to the client**, not the same as
	// deltaTracker's emitted (the latter includes raw fence text). When
	// flushing the tail at the end, comparison must use this, or the prefix
	// won't line up and the tail gets lost.
type toolFenceGate struct {
	emit    func(string)
	buf     string // tail not yet fully classified
	sent    strings.Builder
	inFence bool
}

func newToolFenceGate(emit func(string)) *toolFenceGate {
	return &toolFenceGate{emit: emit}
}

// Sent returns all text actually sent to the client so far.
func (g *toolFenceGate) Sent() string {
	if g == nil {
		return ""
	}
	return g.sent.String()
}

func (g *toolFenceGate) send(s string) {
	if s == "" {
		return
	}
	g.sent.WriteString(s)
	g.emit(s)
}

// Push ingests a chunk of incremental text and immediately sends out the
// parts that are certainly not inside a fence.
func (g *toolFenceGate) Push(delta string) {
	g.buf += delta
	for {
		if g.inFence {
			j := strings.Index(g.buf, toolFenceClose)
			if j < 0 {
				return // fence not closed yet; hold the whole segment
			}
			g.buf = g.buf[j+len(toolFenceClose):]
			g.inFence = false
			continue
		}
		if i := strings.Index(g.buf, toolFenceOpen); i >= 0 {
			g.send(g.buf[:i])
			g.buf = g.buf[i+len(toolFenceOpen):]
			g.inFence = true
			continue
		}
		keep := partialPrefixLen(g.buf, toolFenceOpen)
		g.send(g.buf[:len(g.buf)-keep])
		g.buf = g.buf[len(g.buf)-keep:]
		return
	}
}

// partialPrefixLen returns how many trailing bytes of s are a prefix of
	// marker (excluding a full match).
	//
	// marker is all ASCII, so any matched suffix is necessarily all ASCII too
	// and the cut point never lands in the middle of a multi-byte character —
	// UTF-8 continuation bytes are >=0x80 and never equal any byte in marker.
func partialPrefixLen(s, marker string) int {
	max := len(marker) - 1
	if len(s) < max {
		max = len(s)
	}
	for k := max; k > 0; k-- {
		if strings.HasPrefix(marker, s[len(s)-k:]) {
			return k
		}
	}
	return 0
}

// Relaxed: fences are not required to have surrounding newlines — the model
// sometimes emits ```tool_call\n{...}\n```, sometimes ```tool_call {...}```
// or even all on one line. The old regex insisted on \n…\n; when the format
// varied, parsing missed the block, and a missed block sent the entire
// ```tool_call``` fence to the client as body text = the "reads but replies
// garbage" users saw. Here we only recognize the fence and let JSON parsing
// handle the content as a fallback (non-fence content contains no ```, and
// the non-greedy match stops at the first closing fence).
var toolCallRe = regexp.MustCompile("(?s)```tool_call(.*?)```")

// parseToolCalls extracts ```tool_call``` blocks. Returns clean text + tool_calls.
func parseToolCalls(text string) (string, []ToolCall) {
	var toolCalls []ToolCall
	for _, match := range toolCallRe.FindAllStringSubmatch(text, -1) {
		if len(match) < 2 {
			continue
		}
		var data struct {
			Name      string                 `json:"name"`
			Arguments map[string]interface{} `json:"arguments"`
		}
		if err := json.Unmarshal([]byte(strings.TrimSpace(match[1])), &data); err != nil {
			continue
		}
		argsJSON, _ := json.Marshal(data.Arguments)
		toolCalls = append(toolCalls, ToolCall{
			ID:   "call_" + randHex(8),
			Type: "function",
			Function: ToolCallFunction{
				Name:      data.Name,
				Arguments: string(argsJSON),
			},
		})
	}
	clean := toolCallRe.ReplaceAllString(text, "")
	return strings.TrimSpace(clean), toolCalls
}

// parseToolChoice parses OpenAI's tool_choice.
	// Returns (mode, forcedName): mode ∈ {"auto","none","required"};
	// a non-empty forcedName means the client named a specific function.
func parseToolChoice(tc interface{}) (string, string) {
	switch v := tc.(type) {
	case string:
		switch v {
		case "none", "required", "auto":
			return v, ""
		}
	case map[string]interface{}:
		// {"type":"function","function":{"name":"..."}}
		if f, ok := v["function"].(map[string]interface{}); ok {
			if n := getStr(f, "name"); n != "" {
				return "required", n
			}
		}
	}
	return "auto", ""
}

// PromptTooLongError signals that the prompt exceeded the per-request cap.
	//
	// Why an error instead of truncating ourselves: when over the limit the
	// upstream **silently truncates from the tail** without an error, and the
	// latest message is assembled at the end, so what gets eaten is exactly
	// what the user just asked — the model only sees the system preamble
	// above and replies with a generic opener, neither answering nor calling
	// a tool.
	//
	// Nor do we drop history ourselves: that would still be silently losing
	// data, just in a different place. The client believes the whole thing was
	// sent, while the model has forgotten things; answers are subtly wrong
	// with nobody the wiser. Reporting context_length_exceeded is a signal
	// OpenAI-compatible clients recognize; agentic clients respond by
	// compressing the context themselves and retrying — much smarter than us
	// blindly dropping the oldest chunks.
	//
	// **Why judge by bytes, not tokens**: with Chinese and English aligned to
	// the same byte count on a static IP, measured in practice both hit the
	// wall at exactly the same position — about 129,950 bytes passed 3/3 each,
	// 135,990 bytes 1/3 each, 141,920 bytes 1/3 each; meanwhile tiktoken
	// counts for the same batch of requests differed by 1.9x (English 24,273
	// vs Chinese 46,591). With a token-based threshold, the same number would
	// be too loose for English and would strangle Chinese at about a third of
	// the real capacity.
	//
	// This also rules out "the wall is at the transport layer": the prompt
	// entering f.req must first be JSON'd then urlencoded — each Chinese byte
	// becomes %XX (3x expansion) while English passes through nearly as-is;
	// their on-the-wire sizes differ by nearly 3x yet both hit the same wall,
	// so what is counted is the prompt content's bytes, not the request body
	// size.
	//
	// Actually sustaining long context requires a different route: converting
	// the content into a file attachment. But that needs a logged-in state
	// (anonymous can upload, yet referencing it in the conversation is
	// rejected by the server with 1100), so for now only an error can be
	// reported.
type PromptTooLongError struct {
	Bytes, Budget int
	HasCookie     bool // over the limit even with a cookie; the attachment route couldn't save it either
}

func (e *PromptTooLongError) Error() string {
	base := fmt.Sprintf(
		"prompt is %d bytes, over the %d-byte per-request limit of the Gemini web "+
			"protocol (the limit is on UTF-8 bytes, not tokens). The upstream silently "+
			"truncates from the end, which would drop your latest message and produce an "+
			"unrelated answer, so this request is rejected instead.",
		e.Bytes, e.Budget)
	if !e.HasCookie {
		// Without a cookie this is not a dead end: import one and the
		// attachment route opens up, largely removing the length limit.
		// Omitting this sentence, users would just assume "this project
		// can't handle long context".
		return base + " Add a Google account cookie in the admin panel (Cookie pool) — " +
			"with one configured, oversized conversations are uploaded as a text " +
			"attachment instead and this limit largely goes away."
	}
	return base + " Shorten the conversation, the system prompt, or the tool definitions."
}
