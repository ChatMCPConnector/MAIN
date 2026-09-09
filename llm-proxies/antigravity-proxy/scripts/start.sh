#!/usr/bin/env bash
# start.sh: Startet antigravity-oauth-proxy (Port 9878) analog zu start-glm2api.sh.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDFILE="$DIR/antigravity-proxy.pid"
LOGFILE="/tmp/opencode/antigravity-proxy.log"
HOST="127.0.0.1"
PORT="9878"
HEALTH_URL="http://${HOST}:${PORT}/v1/models"

mkdir -p /tmp/opencode

if ss -tln | grep -q ":${PORT} "; then
  if curl -sf -m 2 "${HEALTH_URL}" >/dev/null 2>&1; then
    echo "[antigravity-proxy] Läuft bereits auf Port ${PORT} (/v1/models OK)."
    exit 0
  fi
  echo "[antigravity-proxy] WARN: Port ${PORT} belegt, aber ${HEALTH_URL} antwortet nicht."
fi

echo "[antigravity-proxy] Starte antigravity-oauth-proxy auf Port ${PORT}..."
(cd "$DIR" && ADMIN_API_KEY="antigravity-secret-6fe2eaa404e1c91bfa0fec01e74ddcc1" \
  setsid nohup ./antigravity-oauth-proxy --port "${PORT}" \
  >> "${LOGFILE}" 2>&1 & echo $! > "${PIDFILE}")

for i in $(seq 1 30); do
  if curl -sf -m 2 "${HEALTH_URL}" >/dev/null 2>&1; then
    echo "[antigravity-proxy] OK: Antwortet auf Port ${PORT}."
    exit 0
  fi
  sleep 1
done

echo "[antigravity-proxy] FEHLER: Port ${PORT} nicht erreichbar. Log:"
tail -n 20 "${LOGFILE}" 2>/dev/null || true
exit 1
