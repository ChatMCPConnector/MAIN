#!/usr/bin/env bash
# start.sh: Startet gemini-web2api (Port 8083) analog zu start-glm2api.sh.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDFILE="$DIR/gemini-web2api.pid"
LOGFILE="/tmp/opencode/gemini-web2api.log"
HOST="127.0.0.1"
PORT="8083"
HEALTH_URL="http://${HOST}:${PORT}/"

mkdir -p /tmp/opencode
mkdir -p "$DIR/data"

if ss -tln | grep -q ":${PORT} "; then
  if curl -sf -m 2 "${HEALTH_URL}" >/dev/null 2>&1; then
    echo "[gemini-web2api] Läuft bereits auf Port ${PORT} (/ OK)."
    exit 0
  fi
  echo "[gemini-web2api] WARN: Port ${PORT} belegt, aber ${HEALTH_URL} antwortet nicht."
fi

COOKIE_ARG=""
if [ -f "/workspaces/MAIN/.secrets/gemini-web-cookie.txt" ]; then
  COOKIE_ARG="--cookie-file /workspaces/MAIN/.secrets/gemini-web-cookie.txt"
fi

echo "[gemini-web2api] Starte gemini-web2api-go auf Port ${PORT}..."
(cd "$DIR" && setsid nohup ./gemini-web2api-go \
  --port "${PORT}" \
  --db "$DIR/data/gemini.db" \
  --admin-token gemini-admin-secret-2026 \
  --api-key sk-gemini-pro-local-2026 \
  $COOKIE_ARG \
  >> "${LOGFILE}" 2>&1 & echo $! > "${PIDFILE}")

for i in $(seq 1 30); do
  if curl -sf -m 2 "${HEALTH_URL}" >/dev/null 2>&1; then
    echo "[gemini-web2api] OK: Antwortet auf Port ${PORT}."
    exit 0
  fi
  sleep 1
done

echo "[gemini-web2api] FEHLER: Port ${PORT} nicht erreichbar. Log:"
tail -n 20 "${LOGFILE}" 2>/dev/null || true
exit 1
