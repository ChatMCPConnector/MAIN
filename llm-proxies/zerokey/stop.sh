#!/usr/bin/env bash
set -euo pipefail

PIDFILE="/tmp/opencode/zerokey.pid"

if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID" 2>/dev/null || true
    echo "ZeroKey gestoppt (PID $PID)."
  fi
  rm -f "$PIDFILE"
fi

pkill -f "node server.js chatgpt main MAIN" 2>/dev/null || true
echo "ZeroKey gestoppt."
