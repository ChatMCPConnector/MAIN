#!/usr/bin/env bash
# quota.sh: Fragt die aktuellen Antigravity-Kontingente & Restlimits live bei Google ab.
set -euo pipefail

CREDS_FILE="$HOME/.config/antigravity-oauth-proxy/oauth_creds.json"

if [ ! -f "$CREDS_FILE" ]; then
  echo "FEHLER: Keine Antigravity-Credentials unter $CREDS_FILE gefunden."
  exit 1
fi

TOKEN="$(jq -r .access_token "$CREDS_FILE")"

RESPONSE="$(curl -s -X POST https://daily-cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "User-Agent: antigravity/cli/1.1.13 (aidev_client; os_type=linux; arch=amd64; cl=964361259; auth_method=consumer)" \
  -d '{"project": "aicode-consumers"}' 2>/dev/null)"

if ! echo "$RESPONSE" | jq -e '.models' >/dev/null 2>&1; then
  echo "Antwort von Google ungültig oder Token abgelaufen:"
  echo "$RESPONSE" | jq . 2>/dev/null || echo "$RESPONSE"
  exit 1
fi

echo "========================================================================="
echo "                  GOOGLE ANTIGRAVITY QUOTA & LIMITS"
echo "========================================================================="

python3 -c '
import json, sys
from datetime import datetime, timezone

data = json.load(sys.stdin)
models = data.get("models", {})

seen = {}
for model_id, info in models.items():
    quota = info.get("quotaInfo")
    if not quota:
        continue
    rem_frac = quota.get("remainingFraction")
    reset = quota.get("resetTime")
    
    key = None
    if "3.8-flash" in model_id:
        key = "Gemini 3.8 Flash"
    elif "3.1-pro" in model_id or "pro-agent" in model_id:
        key = "Gemini 3.1 Pro"
    elif "3.5-flash" in model_id:
        key = "Gemini 3.5 Flash"
    elif "claude-sonnet" in model_id:
        key = "Claude Sonnet 4.6"
    elif "claude-opus" in model_id:
        key = "Claude Opus 4.6"
    elif "gpt-oss" in model_id:
        key = "GPT-OSS 120B"

    if key and key not in seen:
        pct = round(rem_frac * 100, 1) if rem_frac is not None else 100.0
        time_str = "—"
        if reset:
            try:
                dt = datetime.fromisoformat(reset.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                diff = dt - now
                hours = int(diff.total_seconds() // 3600)
                minutes = int((diff.total_seconds() % 3600) // 60)
                time_str = f"in {hours}h {minutes}m"
            except Exception:
                time_str = reset
        seen[key] = (pct, time_str)

col_mod = "Modell"
col_rem = "Verbleibend"
col_res = "Reset-Zeit"
print(f"  {col_mod:<20} | {col_rem:<18} | {col_res}")
print("  " + "-" * 67)
for name, (pct, rtime) in sorted(seen.items()):
    bar_len = int(pct / 10)
    bar = "█" * bar_len + "░" * (10 - bar_len)
    print(f"  {name:<20} | {pct:>5.1f}% [{bar}] | {rtime}")
print("=========================================================================")
' <<< "$RESPONSE"
