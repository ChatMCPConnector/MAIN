#!/usr/bin/env bash
set -euo pipefail

DIR="/workspaces/glm2api/repo"
LOG="/tmp/opencode/glm2api.log"
UV="/home/vscode/.local/bin/uv"
HOST="127.0.0.1"
PORT="8001"

if ss -tln | grep -q ":${PORT} "; then
    echo "Läuft bereits auf Port ${PORT}."
else
    echo "Starte glm2api..."
    (cd "${DIR}" && setsid nohup "${UV}" run main.py >> "${LOG}" 2>&1 &)
fi

for i in $(seq 1 30); do
    if curl -sf -m 2 "http://${HOST}:${PORT}/health" >/dev/null 2>&1; then
        echo "OK: /health antwortet."
        exit 0
    fi
    sleep 1
done

echo "FEHLER: /health nicht erreichbar. Log:"
tail -n 20 "${LOG}"
exit 1
