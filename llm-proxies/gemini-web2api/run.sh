#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDFILE="$DIR/gemini-web2api.pid"
LOGFILE="$DIR/gemini.log"

case "$1" in
  start)
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      echo "gemini-web2api-go is already running (PID: $(cat "$PIDFILE"))"
      exit 0
    fi
    echo "Starting gemini-web2api-go on port 8083..."
    cd "$DIR"
    mkdir -p "$DIR/data"
    ./gemini-web2api-go --port 8083 --admin-token gemini-admin-secret-2026 --api-key sk-gemini-pro-local-2026 </dev/null > "$LOGFILE" 2>&1 &
    PID=$!
    echo $PID > "$PIDFILE"
    sleep 1
    if kill -0 $PID 2>/dev/null; then
      echo "Started successfully (PID: $PID)"
    else
      echo "Failed to start. Check $LOGFILE"
      exit 1
    fi
    ;;
  stop)
    if [ -f "$PIDFILE" ]; then
      PID="$(cat "$PIDFILE")"
      echo "Stopping gemini-web2api-go (PID: $PID)..."
      kill "$PID" 2>/dev/null || true
      rm -f "$PIDFILE"
      echo "Stopped"
    else
      pkill -f "gemini-web2api-go" 2>/dev/null || true
      echo "Stopped any running instance"
    fi
    ;;
  status)
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      echo "Running (PID: $(cat "$PIDFILE"))"
      curl -s http://127.0.0.1:8083/ || true
    else
      echo "Not running"
    fi
    ;;
  restart)
    $0 stop
    sleep 1
    $0 start
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status}"
    exit 1
    ;;
esac
