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

python3 -c '
import json, sys
from datetime import datetime, timezone

data = json.load(sys.stdin)
models = data.get("models", {})

pools = [
    {
        "name": "Claude",
        "models_desc": "Opus 4.6, Sonnet 4.6",
        "keys": ["claude-opus-4-6-thinking", "claude-sonnet-4-6"]
    },
    {
        "name": "Gemini",
        "models_desc": "3.8 Flash, 3.1 Pro, 3.5 Lite",
        "keys": ["gemini-3.8-flash-high", "gemini-3.1-pro-high", "gemini-3.5-flash-lite"]
    }
]

hdr_pool = "Pool / Provider"
hdr_quota = "Verbleibend"
hdr_reset = "Nächster Reset"
hdr_status = "Wochen- & Sprint-Status"

print("=" * 102)
print("                                 GOOGLE ANTIGRAVITY QUOTA & STATUS")
print("=" * 102)
print(f"  {hdr_pool:<38} | {hdr_quota:<20} | {hdr_reset:<16} | {hdr_status}")
print("  " + "-" * 98)

for p in pools:
    rem_frac = None
    reset = None
    for k in p["keys"]:
        info = models.get(k, {})
        q = info.get("quotaInfo")
        if q:
            rem_frac = q.get("remainingFraction")
            reset = q.get("resetTime")
            break
            
    is_reset_active = False
    is_weekly_lockout = False
    time_str = "—"
    if reset:
        try:
            dt = datetime.fromisoformat(reset.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            diff = dt - now
            sec = int(diff.total_seconds())
            if sec > 0:
                is_reset_active = True
                days = sec // 86400
                hours = (sec % 86400) // 3600
                mins = (sec % 3600) // 60
                if days > 0:
                    is_weekly_lockout = True
                    time_str = f"in {days}d {hours}h"
                else:
                    time_str = f"in {hours}h {mins}m"
        except Exception:
            time_str = reset

    if is_reset_active and (rem_frac is None or rem_frac <= 0.01):
        pct = 0.0
    elif rem_frac is not None:
        pct = round(rem_frac * 100, 1)
    else:
        pct = 100.0

    bar_len = int(pct / 10)
    bar = "█" * bar_len + "░" * (10 - bar_len)
    quota_display = f"{pct:>5.1f}% [{bar}]"

    if is_weekly_lockout:
        status_text = "GESPERRT: Wochenlimit erreicht"
    elif pct == 0.0:
        status_text = "5h-Sprint leer (Cooldown aktiv)"
    else:
        status_text = "Aktiv (5h-Sprint verfügbar)"

    p_name = p["name"]
    p_desc = p["models_desc"]
    pool_title = f"{p_name} ({p_desc})"
    print(f"  {pool_title:<38} | {quota_display:<20} | {time_str:<16} | {status_text}")

print("=" * 102)
print("  So funktioniert Googles Quota-System:")
print("  1. Shared Quota: Alle Modelle eines Providers (Claude bzw. Gemini) teilen sich den Pool.")
print("  2. 5h-Sprint: Zeigt den aktuellen Füllstand. Erneuert sich alle 5 Stunden.")
print("  3. Wochen-Cap: Ist das Wochenlimit erreicht, stoppt der 5h-Refill und der Timer springt")
print("     auf mehrere Tage um (z. B. in 4 Tagen). Aktuell: Beide Wochenkontingente sind frei!")
print("=" * 102)
' <<< "$RESPONSE"
