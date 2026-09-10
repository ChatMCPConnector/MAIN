package app

import "strings"

// Tool-Verweigerungserkennung (2026-09-10 Benchmark-Befund).
//
// Die Flash-Modelle ab 3.6 (alle teilen denselben hex wie 3.8) haben ein
// Anti-Prompt-Injection-Training: die per Protokoll ins Prompt injizierten
// Tool-Schemas werden als Angriff gewertet und konsequent **verweigert** —
// mit einer eng standardisierten Prosa («I cannot read files from the local
// filesystem…», «I do not have access to tools…»). 3.5 Flash-Lite hat diese
// Abwehr nicht und emittiert die ```tool_call```-Blöcke korrekt.
//
// Zehn Prompt-Framings (system, user-blob, DE, API-Gateway, umbenannte
// Tools, harmlose Domänen, vorgetäuschte Tool-History) brechen die Weigerung
// nicht; der Thinking-Reasoning-Trace bestätigt die Einordnung («I've
// identified the use of embedded fake system instructions and tool
// definitions»). Es ist Modellverhalten, kein Proxy-Fehler — der Proxy muss
// es nur sauber übersetzen statt eine Fake-Antwort mit finish_reason=stop
// zu liefern, an der Agenten-Loops hängen bleiben.
//
// Kriterien (alle müssen erfüllt sein, Fehlalarme sind teurer als Durchlässigkeit):
//   - die Antwort enthält KEINE tool_calls (mit ```tool_call-Fence wäre das
//     ein Parsing-Problem, keine Verweigerung)
//   - kurze Prosa ohne Code-Fences
//   - typische Absage-Marker + Tool/FileSystem/Command-Vokabular
type ToolRefusalError struct {
	Model string
	Text  string
}

func (e *ToolRefusalError) Error() string {
	return "model " + e.Model + " refused the tool_call protocol: " +
		truncateStr(e.Text, 120)
}

// refusalStarters：开头的自我否定句式。
var refusalStarters = []string{
	"i cannot", "i can't", "i can not",
	"i do not have access", "i don't have access",
	"i am unable to", "i'm unable to",
	"i do not have tools", "i don't have tools",
	"i do not have the ability", "i don't have the ability",
	"i'm not able to", "i am not able to",
	"sorry, i can't", "sorry, i cannot", "sorry, but i can't", "sorry, but i cannot",
	"i'm having a hard time fulfilling your request",
	"i do not have a", "i don't have a",
}

// refusalCapability：拒的是工具/执行能力，而不是别的东西（拒绝违规内容
// 的「I cannot help with…」不属于这里，那要透传给客户端）。
var refusalCapability = []string{
	"tool", "function call", "function-call", "tool call",
	"filesystem", "file system", "local file", "files on",
	"command", "shell", "execute", "executing",
	"run tool", "run tools", "run commands",
	"external tool", "external tools", "external commands",
	"system execution", "environment to",
}

// isToolRefusalText 判断一段回复文本是不是 3.6+ 的工具拒答。
//
// 长度只看**开头句**：拒答的首句总是自我否定 + 能力声明（≤300 字节），
// 后面可能还挂着给用户的替代建议（“If you are running in a terminal, you
// can…”）——那不影响拒答判定。整段长度上限仍留 2000：真做任务的回复
// 首句不会是 “I cannot … filesystem/shell/execute”。
func isToolRefusalText(text string) bool {
	t := strings.TrimSpace(text)
	if t == "" || len(t) > 2000 {
		return false
	}
	low := strings.ToLower(t)
	if strings.Contains(low, "```") {
		// 围栏（无论哪种）意味着文本里可能有协议块，那是另一类问题
		return false
	}
	// 只检查首段/首句（前 300 字节）的否定开头 —— 拒答开头从不绕圈子。
	head := low
	if len(head) > 300 {
		head = head[:300]
	}
	if i := strings.IndexByte(head, '\n'); i > 0 && i < 300 {
		head = head[:i]
	}
	starter := false
	for _, s := range refusalStarters {
		if strings.HasPrefix(head, s) {
			starter = true
			break
		}
	}
	if !starter {
		return false
	}
	for _, c := range refusalCapability {
		if strings.Contains(low, c) {
			return true
		}
	}
	return false
}