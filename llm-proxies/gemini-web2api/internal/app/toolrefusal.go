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

// refusalStarters: self-negating sentence patterns at the start.
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

// refusalCapability: the refusal targets tool/execution capability, not something else
// ("I cannot help with…" refusals of disallowed content don't belong here; those get
// passed through to the client).
var refusalCapability = []string{
	"tool", "function call", "function-call", "tool call",
	"filesystem", "file system", "local file", "files on",
	"command", "shell", "execute", "executing",
	"run tool", "run tools", "run commands",
	"external tool", "external tools", "external commands",
	"system execution", "environment to",
}

// isToolRefusalText decides whether a reply text is a 3.6+ tool refusal.
//
// Length only looks at the **opening sentence**: a refusal's first sentence is always
// self-negation + a capability statement (≤300 bytes). What follows may still hang a
// fallback suggestion for the user ("If you are running in a terminal, you can…") —
// that doesn't affect the refusal verdict. The overall length cap stays at 2000: a
// reply that actually does the task never opens with "I cannot … filesystem/shell/execute".
func isToolRefusalText(text string) bool {
	t := strings.TrimSpace(text)
	if t == "" || len(t) > 8000 {
		return false
	}
	low := strings.ToLower(t)
	// only exclude the **protocol fence** (```tool_call): that means the model is genuinely
	// attempting the protocol (a parsing-layer issue, not a refusal). Other fences (observed
	// in practice: 3.6+ refusals often carry a ```bash "do it yourself" appendix!) get no
	// exemption — the self-negating opening sentence is the criterion.
	if strings.Contains(low, "```tool_call") {
		return false
	}
	// only check the first paragraph/sentence (first 300 bytes) for the negating opener — refusals never beat around the bush.
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