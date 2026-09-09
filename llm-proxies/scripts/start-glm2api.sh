#!/usr/bin/env bash
# Startet glm2api aus dem MAIN-Repo (kein Klon mehr nötig).
# Code liegt in llm-proxies/glm2api/, .env kommt aus
# llm-proxies/glm2api.env (gitignored → wird hierher kopiert falls neu).
set -euo pipefail

APP_DIR="/workspaces/MAIN/llm-proxies/glm2api"
ENV_SRC="/workspaces/MAIN/llm-proxies/glm2api.env"
LOG="/tmp/opencode/glm2api.log"
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
HOST="127.0.0.1"
PORT="8001"
HEALTH_URL="http://${HOST}:${PORT}/health"

# .env bereitstellen (nie committet, secret-frei aber betriebskritisch)
if [ ! -f "$APP_DIR/.env" ] && [ -f "$ENV_SRC" ]; then
  cp "$ENV_SRC" "$APP_DIR/.env"
fi

# Runtime-Artefakte, die nicht im Git landen dürfen
mkdir -p "$APP_DIR/log"

if ss -tln | grep -q ":${PORT} "; then
    # Port belegt: prüfen, ob ES unser Proxy ist (Health-Endpunkt).
    # Antwortet /health korrekt → OK, läuft schon. Fremde Belegung → Fehler.
    if curl -sf -m 2 "${HEALTH_URL}" >/dev/null 2>&1 \
        && [ "$(curl -s -m 2 "${HEALTH_URL}" | jq -r '.status' 2>/dev/null)" = "ok" ]; then
        echo "Läuft bereits auf Port ${PORT} (/health OK)."
        exit 0
    fi
    echo "FEHLER: Port ${PORT} ist belegt, aber ${HEALTH_URL} antwortet nicht"
    echo "korrekt — vermutlich ein fremder Prozess. glm2api NICHT gestartet."
    echo "Belegung prüfen: ss -tlnp | grep :${PORT}"
    exit 1
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
