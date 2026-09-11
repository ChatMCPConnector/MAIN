#!/usr/bin/env bash
# quota.sh: Fragt die aktuellen Antigravity-Kontingente & Restlimits live bei Google ab (5h-Sprint & Wochen-Limit).
set -euo pipefail

CREDS_FILE="$HOME/.config/antigravity-oauth-proxy/oauth_creds.json"

if [ ! -f "$CREDS_FILE" ]; then
  echo "FEHLER: Keine Antigravity-Credentials unter $CREDS_FILE gefunden."
  exit 1
fi

TOKEN="$(jq -r .access_token "$CREDS_FILE")"
UA="antigravity/cli/1.1.13 (aidev_client; os_type=linux; arch=amd64; cl=964361259; auth_method=consumer)"

# Primär: retrieveUserQuotaSummary (liefert 5h-Sprint UND Wochen-Limit getrennt)
RESPONSE="$(curl -s -X POST https://daily-cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "User-Agent: $UA" \
  -d '{"project": "aicode-consumers"}' 2>/dev/null || true)"

# Fallback auf fetchAvailableModels falls retrieveUserQuotaSummary nicht antwortet
if ! echo "$RESPONSE" | jq -e '.groups' >/dev/null 2>&1; then
  RESPONSE="$(curl -s -X POST https://daily-cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -H "User-Agent: $UA" \
    -d '{"project": "aicode-consumers"}' 2>/dev/null || true)"
fi

if ! echo "$RESPONSE" | jq -e '(.groups // .models)' >/dev/null 2>&1; then
  echo "Antwort von Google ungültig oder Token abgelaufen:"
  echo "$RESPONSE" | jq . 2>/dev/null || echo "$RESPONSE"
  exit 1
fi

python3 -c '
import json, sys, os, sqlite3
from datetime import datetime, timezone

data = json.load(sys.stdin)

def format_time(reset_str):
    if not reset_str:
        return "Bereit"
    try:
        dt = datetime.fromisoformat(reset_str.replace("Z", "+00:00"))
        sec = int((dt - datetime.now(timezone.utc)).total_seconds())
        if sec <= 0:
            return "Bereit"
        days = sec // 86400
        hours = (sec % 86400) // 3600
        mins = (sec % 3600) // 60
        if days > 0:
            return f"in {days}d {hours:02d}h"
        elif hours > 0:
            return f"in {hours}h {mins:02d}m"
        else:
            return f"in {mins}m"
    except Exception:
        return reset_str

def make_bar(pct):
    bar_len = min(10, max(0, int(round(pct / 10))))
    return "█" * bar_len + "░" * (10 - bar_len)

def get_status(pct_sprint, pct_week):
    lowest = min(pct_sprint, pct_week)
    if lowest <= 0.01:
        return "Gesperrt"
    elif lowest < 25.0:
        return "Knapp"
    else:
        return "Aktiv"

indent = "   "
line_w = 96
title = "GOOGLE ANTIGRAVITY LIVE QUOTA & STATUS"

print()
print(indent + "=" * line_w)
print(indent + title.center(line_w))
print(indent + "=" * line_w)
hdr_group = "Modell-Gruppe"
hdr_sprint = "5-Stunden Sprint"
hdr_week = "Wochen-Limit"
hdr_status = "Status"
print(f"{indent}  {hdr_group:<24} | {hdr_sprint:<30} | {hdr_week:<30} | {hdr_status}")
print(indent + "-" * line_w)

if "groups" in data:
    for g in data.get("groups", []):
        name = g.get("displayName", "Unbekannt")
        sprint_b = None
        weekly_b = None
        for b in g.get("buckets", []):
            w = b.get("window", "")
            bid = b.get("bucketId", "")
            if "5h" in w or "5h" in bid:
                sprint_b = b
            elif "week" in w or "week" in bid:
                weekly_b = b

        def parse_bucket(b):
            if not b:
                return 100.0, "—"
            frac = b.get("remainingFraction", 1.0)
            pct = round(frac * 100, 1)
            t = format_time(b.get("resetTime"))
            bar = make_bar(pct)
            return pct, f"{pct:>5.1f}% [{bar}] ({t})"

        s_pct, s_disp = parse_bucket(sprint_b)
        w_pct, w_disp = parse_bucket(weekly_b)
        status = get_status(s_pct, w_pct)
        print(f"{indent}  {name:<24} | {s_disp:<30} | {w_disp:<30} | {status}")
else:
    # Fallback für flaches fetchAvailableModels
    models = data.get("models", {})
    fallback_pools = [
        {"name": "Gemini Models", "keys": ["gemini-3.8-flash-high", "gemini-pro-agent"]},
        {"name": "Claude and GPT models", "keys": ["claude-opus-4-6-thinking", "claude-sonnet-4-6", "gpt-oss-120b-medium"]}
    ]
    for p in fallback_pools:
        name = p["name"]
        q = None
        for k in p["keys"]:
            q = models.get(k, {}).get("quotaInfo")
            if q: break
        if q:
            frac = q.get("remainingFraction", 1.0)
            pct = round(frac * 100, 1)
            t = format_time(q.get("resetTime"))
            bar = make_bar(pct)
            disp = f"{pct:>5.1f}% [{bar}] ({t})"
            bg_msg = "(im Hintergrund aktiv)"
            if "d " in t:
                print(f"{indent}  {name:<24} | {bg_msg:<30} | {disp:<30} | {get_status(100, pct)}")
            else:
                print(f"{indent}  {name:<24} | {disp:<30} | {bg_msg:<30} | {get_status(pct, 100)}")

print(indent + "=" * line_w)

# Lokalen Opencode-Tokenverbrauch ermitteln
db_path = os.path.expanduser("~/.local/share/opencode/opencode.db")
if os.path.exists(db_path):
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT data FROM message")
        c_tokens = 0
        g_tokens = 0
        for (m_data,) in c.fetchall():
            if not m_data: continue
            d = json.loads(m_data)
            mid = (d.get("modelID") or "").lower()
            t = d.get("tokens", {})
            tin = t.get("input", 0)
            tout = t.get("output", 0)
            if "claude" in mid or "opus" in mid or "sonnet" in mid or "gpt-oss" in mid:
                c_tokens += tin + tout
            elif "gemini" in mid:
                g_tokens += tin + tout
        c_str = f"{c_tokens/1_000_000:.2f}M" if c_tokens >= 100_000 else f"{c_tokens:,}"
        g_str = f"{g_tokens/1_000_000:.2f}M" if g_tokens >= 100_000 else f"{g_tokens:,}"
        print(f"{indent}  Lokaler Token-Verbrauch: Claude & GPT {c_str} Tokens | Gemini {g_str} Tokens")
    except Exception:
        pass

print(f"{indent}  Hinweis: 5h-Sprint federt Lastspitzen ab. Wochenlimit ist das fixe Kontingent.")
print()
' <<< "$RESPONSE"
