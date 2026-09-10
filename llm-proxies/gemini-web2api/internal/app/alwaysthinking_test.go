package app

import "testing"

// 2026-09-11 用户指令：Gemini-Web 模型永远带扩展思考跑。
// applyAlwaysThinking 在有登录态时把 plain 版提升成同 hex 的 thinking 版。
func TestApplyAlwaysThinking(t *testing.T) {
	lite := Models["gemini-3.5-flash-lite"]
	liteThink := Models["gemini-3.5-flash-lite-thinking"]

	// 有登录态：提升
	got := applyAlwaysThinking("gemini-3.5-flash-lite", lite, true)
	if !got.Thinking {
		t.Errorf("Login-State: Thinking=false, erwartet true (always-thinking)")
	}
	if got.HexID != liteThink.HexID || got.Mode != liteThink.Mode {
		t.Errorf("Promotion weicht von thinking-Variante ab (Hex/Mode)")
	}

	// 匿名：不提升（服务端忽略 inner[80]=2）
	got = applyAlwaysThinking("gemini-3.5-flash-lite", lite, false)
	if got.Thinking {
		t.Errorf("Anonym: Thinking=true, erwartet false (Upstream ignoriert es)")
	}

	// -thinking direkt：bleibt
	got = applyAlwaysThinking("gemini-3.5-flash-lite-thinking", liteThink, true)
	if !got.Thinking {
		t.Errorf("-thinking direkt: Thinking=false")
	}

	// 3.8-flash：提升 (Paid-Account vorausgesetzt, gleiche Logik)
	got = applyAlwaysThinking("gemini-3.8-flash", Models["gemini-3.8-flash"], true)
	if !got.Thinking {
		t.Errorf("gemini-3.8-flash mit Login: Thinking=false, erwartet true")
	}

	// 媒体模型不提升（产物不走思考链）
	img := Models["gemini-image"]
	got = applyAlwaysThinking("gemini-image", img, true)
	if got.Thinking {
		t.Errorf("gemini-image: Medien-Modell darf nicht auf Thinking gehoben werden")
	}
}

// resolveModel-Integration：plain-Anfrage mit Pool-Cookie bekommt die
// Thinking-Config（Modellname bleibt für den Client unverändert）。
func TestResolveModelPromotesWithCookie(t *testing.T) {
	if !hasCookie() {
		t.Skip("kein Cookie im Pool — Thinking-Promotion braucht Login-State")
	}
	name, mc, err := resolveModel("gemini-3.5-flash-lite")
	if err != nil {
		t.Fatalf("resolveModel: %v", err)
	}
	if name != "gemini-3.5-flash-lite" {
		t.Errorf("Client-Modellname wurde geändert: %s", name)
	}
	if !mc.Thinking {
		t.Errorf("resolveModel: Thinking=false trotz Cookie im Pool")
	}
}