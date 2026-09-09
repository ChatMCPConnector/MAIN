#!/usr/bin/env bash
# smoke-test.sh: Live-Smoke-Test gegen den laufenden glm2api-Proxy (Port 8001).
# Deckt die offenen Testlücken aus glm-api-audit.md ab, soweit ohne externen
# Aufwand verifizierbar: alle drei API-Formate + Tool-Call-Roundtrip (2 Turns).
# Voraussetzung: Proxy laeuft (start-glm2api.sh / watchdog).
# Verwendung: ./llm-proxies/scripts/smoke-test.sh
set -u
BASE="http://127.0.0.1:8001"
MODEL="${SMOKE_MODEL:-glm-4.7-flash}"
fail=0

check() { # name, bedingung(0=ok)
  if [ "$2" -eq 0 ]; then echo "OK   $1"; else echo "FAIL $1"; fail=1; fi
}

# 1) Health
curl -sf -m 3 "$BASE/health" >/dev/null; check "health" $?

# 2) Models
n=$(curl -sf -m 5 "$BASE/v1/models" | python3 -c "import json,sys; print(len(json.load(sys.stdin).get('data',[])))" 2>/dev/null)
[ -n "$n" ] && [ "$n" -gt 10 ]; check "models ($n geliefert)" $?

# 3) OpenAI chat (non-stream) + streaming
curl -sf -m 90 "$BASE/v1/chat/completions" -H "Content-Type: application/json" \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Antworte nur mit: ok\"}],\"max_tokens\":20}" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if 'ok' in d['choices'][0]['message']['content'].lower() else 1)"; check "openai chat" $?
curl -sf -m 90 -N "$BASE/v1/chat/completions" -H "Content-Type: application/json" \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Antworte nur mit: ok\"}],\"stream\":true,\"max_tokens\":20}" \
  | grep -q "\[DONE\]"; check "openai chat (stream)" $?

# 4) Anthropic
curl -sf -m 90 "$BASE/v1/messages" -H "Content-Type: application/json" -H "anthropic-version: 2023-06-01" \
  -d "{\"model\":\"$MODEL\",\"max_tokens\":30,\"messages\":[{\"role\":\"user\",\"content\":\"Antworte nur mit: ok\"}]}" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if 'ok' in d['content'][0]['text'].lower() else 1)"; check "anthropic messages" $?

# 5) Responses
curl -sf -m 90 "$BASE/v1/responses" -H "Content-Type: application/json" \
  -d "{\"model\":\"$MODEL\",\"input\":\"Antworte nur mit: ok\"}" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('status')=='completed' else 1)"; check "responses" $?

# 6) Tool-Call Roundtrip Turn 1 (Modell muss Tool-Call emittieren)
tc=$(curl -sf -m 120 "$BASE/v1/chat/completions" -H "Content-Type: application/json" -d '{
  "model": "'"$MODEL"'",
  "messages": [{"role": "user", "content": "Benutze das Tool get_time mit timezone Europe/Berlin"}],
  "tools": [{"type": "function", "function": {"name": "get_time", "description": "Gibt aktuelle Uhrzeit fuer eine Zeitzone", "parameters": {"type": "object", "properties": {"timezone": {"type": "string"}}, "required": ["timezone"]}}}]
}' 2>/dev/null)
call_id=$(echo "$tc" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['choices'][0]['message']['tool_calls'][0]['id'])" 2>/dev/null)
call_args=$(echo "$tc" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['choices'][0]['message']['tool_calls'][0]['function']['arguments'])" 2>/dev/null)
[ -n "$call_id" ]; check "tool-call emittiert" $?

# 7) Tool-Result Roundtrip Turn 2 (Modell verarbeitet Tool-Output)
python3 - "$call_id" "$call_args" <<'PYEOF' > /tmp/opencode/smoke_body.json
import json, sys
call_id, call_args = sys.argv[1], sys.argv[2]
body = {
  "model": "glm-4.7-flash",
  "messages": [
    {"role": "user", "content": "Benutze das Tool get_time mit timezone Europe/Berlin"},
    {"role": "assistant", "tool_calls": [{"id": call_id, "type": "function", "function": {"name": "get_time", "arguments": call_args}}]},
    {"role": "tool", "tool_call_id": call_id, "content": "15:23 Uhr MESZ"}
  ],
  "tools": [{"type": "function", "function": {"name": "get_time", "description": "Gibt aktuelle Uhrzeit", "parameters": {"type": "object", "properties": {"timezone": {"type": "string"}}}}}]
}
print(json.dumps(body))
PYEOF
curl -sf -m 120 "$BASE/v1/chat/completions" -H "Content-Type: application/json" \
  -d @/tmp/opencode/smoke_body.json \
  | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if '15:23' in (d['choices'][0]['message'].get('content') or '') else 1)"; check "tool-result verarbeitet" $?

echo ""
if [ "$fail" -eq 0 ]; then echo "SMOKE-TEST: ALLE OK"; else echo "SMOKE-TEST: FEHLER"; exit 1; fi
