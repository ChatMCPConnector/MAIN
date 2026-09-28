#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDFILE="/tmp/opencode/zerokey.pid"
LOGFILE="/tmp/opencode/zerokey.log"
mkdir -p /tmp/opencode

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null; then
  echo "ZeroKey läuft bereits (PID $(cat "$PIDFILE"))."
  exit 0
fi

cd "$DIR"
setsid nohup node server.js chatgpt main MAIN </dev/null >> "$LOGFILE" 2>&1 &
PID=$!
echo "$PID" > "$PIDFILE"
disown "$PID" 2>/dev/null || true

# Warten bis Server bereit ist (max 10s)
for i in $(seq 1 20); do
  if curl -sf -m 1 http://127.0.0.1:7250/v1/models >/dev/null 2>&1; then
    echo "ZeroKey erfolgreich im Hintergrund gestartet (PID $PID, Port 7250)."
    exit 0
  fi
  sleep 0.5
done

echo "ZeroKey gestartet (PID $PID), Port 7250 noch nicht bereit — Logs in $LOGFILE prüfen."
