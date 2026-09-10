package app

import "testing"

// 2026-09-11 Fix 1 (Agent-Loop-Support): Kandidaten-Fingerprints.
// Szenario aus dem Session-Sequenz-Benchmark:
//   Request 1: user "read /etc/hostname"            → antwortet assistant(null, tool_calls)
//   Request 2: + assistant(tool_calls) + tool(result) + user  → muss DIESELBE Konversation treffen
//
// Der Proxy kennt beim Speichern den Tool-Result-Inhalt nicht (der entsteht
// clientseitig) — daher der degrade-Kandidat: History ohne trailing tool-Nachrichten.
// Achtung beim Setup: convChildKey wird auf die Request-History OHNE die neue
// Antwort aufgerufen (genau wie in callGeminiConv).
func TestParentKeyCandidatesAgentLoop(t *testing.T) {
	convStore = map[string]*convState{}
	// Request 1: nur die user-Nachricht; unsere Antwort ist reiner Tool-Call
	// (text = "" nach parseToolCalls).
	req1 := []map[string]interface{}{
		{"role": "user", "content": "Read /etc/hostname."},
	}
	convPut(convChildKey(req1, ""), &convState{cid: "c_1", turn: 1})

	// Request 2: Client hat assistant(null, tool_calls) + tool(result) ergänzt.
	next := append(append([]map[string]interface{}{}, req1...),
		map[string]interface{}{"role": "assistant", "content": nil, "tool_calls": []interface{}{
			map[string]interface{}{"id": "call_1", "function": map[string]interface{}{
				"name": "read_file", "arguments": `{"path":"/etc/hostname"}`}}}},
		map[string]interface{}{"role": "tool", "tool_call_id": "call_1",
			"name": "read_file", "content": "benchmark-box-01"},
		map[string]interface{}{"role": "user", "content": "Summarize the hostname."})

	conv, key := convGetByParentKey(next)
	if conv == nil {
		t.Fatalf("Agent-Loop-Fortsetzung wurde nicht erkannt (hitKey leer)")
	}
	if key == "" {
		t.Fatalf("hitKey fehlt")
	}
	if conv.cid != "c_1" {
		t.Errorf("falsche Konversation getroffen: cid=%s", conv.cid)
	}
}

// Klassischer Chat-Verlauf (Text antwort) — muss durch den exakten Kandidaten
// weiterhin funktionieren.
func TestParentKeyCandidatesPlainChat(t *testing.T) {
	convStore = map[string]*convState{}
	req1 := []map[string]interface{}{
		{"role": "user", "content": "Was ist Paris?"},
	}
	convPut(convChildKey(req1, "Die Hauptstadt Frankreichs."), &convState{cid: "c_2", turn: 1})

	next := append(append([]map[string]interface{}{}, req1...),
		map[string]interface{}{"role": "assistant", "content": "Die Hauptstadt Frankreichs."},
		map[string]interface{}{"role": "user", "content": "Und Lyon?"})
	conv, _ := convGetByParentKey(next)
	if conv == nil || conv.cid != "c_2" {
		t.Fatalf("Plain-Chat-Fortsetzung nicht erkannt (conv=%v)", conv)
	}
}

// stripTrailingToolMsgs: nur trailing tool, dazwischenliegende bleiben.
func TestStripTrailingToolMsgs(t *testing.T) {
	msgs := []map[string]interface{}{
		{"role": "user", "content": "u"},
		{"role": "assistant", "content": nil},
		{"role": "tool", "content": "r1"},
		{"role": "assistant", "content": "ok"},
		{"role": "tool", "content": "r2"},
		{"role": "tool", "content": "r3"},
	}
	got := stripTrailingToolMsgs(msgs)
	if len(got) != 4 || getStr(got[3], "role") != "assistant" {
		t.Errorf("stripTrailingToolMsgs: len=%d, last=%v", len(got), got[len(got)-1])
	}
	// ohne trailing tool: unangetastet
	same := stripTrailingToolMsgs(msgs[:4])
	if len(same) != 4 {
		t.Errorf("kein trailing tool: sollte unangetastet bleiben")
	}
}