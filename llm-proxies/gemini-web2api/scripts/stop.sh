#!/usr/bin/env bash
# stop-gemini-web2api.sh: Beendet gemini-web2api sauber.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDFILE="$DIR/gemini-web2api.pid"

if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE")"
  echo "[gemini-web2api] Stoppe PID $PID..."
  kill "$PID" 2>/dev/null || true
  rm -f "$PIDFILE"
fi

pkill -f "gemini-web2api-go" 2>/dev/null || true
echo "[gemini-web2api] Gestoppt."
