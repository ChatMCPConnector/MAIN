#!/usr/bin/env bash
# opencode-server.sh: Verwaltet den zentralen opencode-Server (Port 4096).
# Erlaubt beliebig viele parallele Terminals/Tabs, ohne dass Sessions sich terminieren.
set -euo pipefail

HOST="127.0.0.1"
PORT="4096"
HEALTH_URL="http://${HOST}:${PORT}/"
LOGFILE="/tmp/opencode/opencode-serve.log"
PIDFILE="/tmp/opencode/opencode-serve.pid"

mkdir -p /tmp/opencode

case "${1:-status}" in
  start)
    if ss -tln | grep -q ":${PORT} "; then
      if curl -sf -m 2 "${HEALTH_URL}" >/dev/null 2>&1; then
        echo "[opencode-server] Läuft bereits auf Port ${PORT}."
        exit 0
      fi
      echo "[opencode-server] WARN: Port ${PORT} belegt, aber Server antwortet nicht."
    fi

    echo "[opencode-server] Starte zentralen Server auf Port ${PORT}..."
    (cd /workspaces/MAIN && setsid nohup opencode serve --port "${PORT}" --hostname "${HOST}" >> "${LOGFILE}" 2>&1 & echo $! > "${PIDFILE}")

    for i in $(seq 1 20); do
      if curl -sf -m 2 "${HEALTH_URL}" >/dev/null 2>&1; then
        echo "[opencode-server] OK: Läuft auf Port ${PORT}."
        exit 0
      fi
      sleep 1
    done

    echo "[opencode-server] FEHLER: Server nicht erreichbar. Log:"
    tail -n 20 "${LOGFILE}" 2>/dev/null || true
    exit 1
    ;;

  stop)
    if [ -f "${PIDFILE}" ]; then
      PID="$(cat "${PIDFILE}")"
      echo "[opencode-server] Stoppe PID ${PID}..."
      kill "${PID}" 2>/dev/null || true
      rm -f "${PIDFILE}"
    fi
    pkill -f "opencode serve" 2>/dev/null || true
    echo "[opencode-server] Gestoppt."
    ;;

  status)
    if curl -sf -m 2 "${HEALTH_URL}" >/dev/null 2>&1; then
      echo "[opencode-server] Aktiv auf http://${HOST}:${PORT}/"
    else
      echo "[opencode-server] Nicht aktiv."
      exit 1
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
