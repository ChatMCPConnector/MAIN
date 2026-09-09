#!/usr/bin/env bash
# start-gemini-web2api.sh: Startet gemini-web2api (Port 8083).
# Idempotent: läuft er schon auf Port 8083, macht das Skript nichts.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDFILE="$DIR/gemini-web2api.pid"
LOGFILE="$DIR/gemini.log"

if ss -tln | grep -q ":8083 "; then
  echo "[gemini-web2api] Port 8083 belegt — Proxy läuft bereits."
  exit 0
fi

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "[gemini-web2api] Läuft bereits mit PID $(cat "$PIDFILE")."
  exit 0
fi

cd "$DIR"
mkdir -p "$DIR/data"

COOKIE_ARG=""
if [ -f "/workspaces/MAIN/.secrets/gemini-web-cookie.txt" ]; then
  COOKIE_ARG="--cookie-file /workspaces/MAIN/.secrets/gemini-web-cookie.txt"
fi

echo "[gemini-web2api] Starte gemini-web2api-go auf Port 8083..."
./gemini-web2api-go \
  --port 8083 \
  --db "$DIR/data/gemini.db" \
  --admin-token gemini-admin-secret-2026 \
  --api-key sk-gemini-pro-local-2026 \
  $COOKIE_ARG \
  </dev/null >> "$LOGFILE" 2>&1 &

PID=$!
echo "$PID" > "$PIDFILE"
sleep 1

if kill -0 "$PID" 2>/dev/null; then
  echo "[gemini-web2api] Erfolgreich gestartet (PID: $PID)."
else
  echo "[gemini-web2api] FEHLER beim Start. Siehe $LOGFILE"
  exit 1
fi
