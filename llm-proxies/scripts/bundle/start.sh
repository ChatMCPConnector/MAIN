#!/usr/bin/env bash
# start.sh: glm2api aus dem Bundle starten (portabel, ohne MAIN-Repo-Pfade).
# Default Port 8001 (aus app/.env); via GLM_PORT/GLM_HOST überschreibbar.
set -euo pipefail
BUNDLE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$BUNDLE_ROOT/app"
LOG="/tmp/glm2api.log"
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
HOST="${GLM_HOST:-127.0.0.1}"
PORT="${GLM_PORT:-8001}"

if [ ! -d "$APP_DIR/.venv" ]; then
  echo "Kein venv — führe zuerst $BUNDLE_ROOT/scripts/install.sh aus."
  exit 1
fi

if [ ! -f "$APP_DIR/.env" ] && [ -f "$APP_DIR/glm2api.env" ]; then
  cp "$APP_DIR/glm2api.env" "$APP_DIR/.env"
fi
mkdir -p "$APP_DIR/log"

if ss -tln 2>/dev/null | grep -q ":${PORT} "; then
    echo "Läuft bereits auf Port ${PORT}."
    exit 0
fi

echo "Starte glm2api (aus $APP_DIR)..."
(cd "$APP_DIR" && setsid nohup "$UV" run main.py >> "${LOG}" 2>&1 &)

for i in $(seq 1 60); do
    if curl -sf -m 2 "http://${HOST}:${PORT}/health" >/dev/null 2>&1; then
        echo "OK: /health antwortet auf ${HOST}:${PORT}."
        exit 0
    fi
    sleep 1
done

echo "FEHLER: /health nicht erreichbar. Log:"
tail -n 20 "${LOG}"
exit 1
