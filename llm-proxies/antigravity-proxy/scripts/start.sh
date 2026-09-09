#!/usr/bin/env bash
# start.sh: Startet antigravity-oauth-proxy auf Port 9878
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDFILE="$DIR/antigravity-proxy.pid"
LOGFILE="$DIR/antigravity-proxy.log"

if ss -tln | grep -q ":9878 "; then
  echo "[antigravity-proxy] Port 9878 belegt — Proxy läuft bereits."
  exit 0
fi

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "[antigravity-proxy] Läuft bereits mit PID $(cat "$PIDFILE")."
  exit 0
fi

cd "$DIR"

echo "[antigravity-proxy] Starte antigravity-oauth-proxy auf Port 9878..."
ADMIN_API_KEY="antigravity-secret-6fe2eaa404e1c91bfa0fec01e74ddcc1" \
./antigravity-oauth-proxy --port 9878 </dev/null >> "$LOGFILE" 2>&1 &

PID=$!
echo "$PID" > "$PIDFILE"
sleep 1

if kill -0 "$PID" 2>/dev/null; then
  echo "[antigravity-proxy] Erfolgreich gestartet (PID: $PID)."
else
  echo "[antigravity-proxy] FEHLER beim Start. Siehe $LOGFILE"
  exit 1
fi
