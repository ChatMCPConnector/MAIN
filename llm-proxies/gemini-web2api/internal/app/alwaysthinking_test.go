package app

import "testing"

// 2026-09-11 user directive: Gemini-Web models always run with extended thinking.
// applyAlwaysThinking promotes the plain version to the same-hex thinking version when logged in.
func TestApplyAlwaysThinking(t *testing.T) {
	lite := Models["gemini-3.5-flash-lite"]
	liteThink := Models["gemini-3.5-flash-lite-thinking"]

	// logged in: promoted
	got := applyAlwaysThinking("gemini-3.5-flash-lite", lite, true)
	if !got.Thinking {
		t.Errorf("Login-State: Thinking=false, erwartet true (always-thinking)")
	}
	if got.HexID != liteThink.HexID || got.Mode != liteThink.Mode {
		t.Errorf("Promotion weicht von thinking-Variante ab (Hex/Mode)")
	}

	// anonymous: not promoted (the server ignores inner[80]=2)
	got = applyAlwaysThinking("gemini-3.5-flash-lite", lite, false)
	if got.Thinking {
		t.Errorf("Anonym: Thinking=true, erwartet false (Upstream ignoriert es)")
	}

	// -thinking directly: stays as-is
	got = applyAlwaysThinking("gemini-3.5-flash-lite-thinking", liteThink, true)
	if !got.Thinking {
		t.Errorf("-thinking direkt: Thinking=false")
	}

	// 3.8-flash: promoted (assuming a paid account, same logic)
	got = applyAlwaysThinking("gemini-3.8-flash", Models["gemini-3.8-flash"], true)
	if !got.Thinking {
		t.Errorf("gemini-3.8-flash mit Login: Thinking=false, erwartet true")
	}

	// media models are not promoted (their output doesn't go through the reasoning chain)
	img := Models["gemini-image"]
	got = applyAlwaysThinking("gemini-image", img, true)
	if got.Thinking {
		t.Errorf("gemini-image: Medien-Modell darf nicht auf Thinking gehoben werden")
	}
}

// resolveModel integration: a plain request with a pool cookie gets the
// thinking config (the model name stays unchanged for the client).
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