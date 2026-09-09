#!/usr/bin/env bash
# stop.sh: Stoppt antigravity-oauth-proxy
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDFILE="$DIR/antigravity-proxy.pid"

if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE")"
  echo "[antigravity-proxy] Stoppe PID $PID..."
  kill "$PID" 2>/dev/null || true
  rm -f "$PIDFILE"
fi

pkill -f "antigravity-oauth-proxy" 2>/dev/null || true
echo "[antigravity-proxy] Gestoppt."
