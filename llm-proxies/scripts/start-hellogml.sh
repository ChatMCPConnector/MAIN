#!/bin/bash
# HelloGML Startskript: Startet den GLM-Proxy-Worker als Background-Dienst
# Repo: /workspaces/hellogml/repo
# Port: 8787 | Log: /tmp/opencode/hellogml.log

PORT=8787
ADMIN_KEY="changeme"
BASE_URL="http://127.0.0.1:${PORT}"
REPO_DIR="/workspaces/hellogml/repo"
LOGFILE="/tmp/opencode/hellogml.log"
API_KEY="sk-test-local-1"

mkdir -p /tmp/opencode

# 1) Prüfen, ob der Worker bereits läuft
if ss -tln | grep -q ":${PORT} "; then
  echo "[OK] Worker läuft bereits auf Port ${PORT} — kein Neustart."
else
  echo "[..] Worker läuft nicht — starte wrangler dev im Hintergrund..."
  cd "${REPO_DIR}" || { echo "[FEHLER] Repo-Verzeichnis nicht gefunden: ${REPO_DIR}"; exit 1; }
  setsid nohup npx wrangler dev --port ${PORT} --local >> "${LOGFILE}" 2>&1 &
  disown || true
  echo "[..] Warte auf HTTP 200 auf ${BASE_URL}/ ..."
fi

# 2) Warten bis der Worker per HTTP erreichbar ist (max. 60s)
for i in $(seq 1 60); do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" -m 2 "${BASE_URL}/" 2>/dev/null)
  if [ "${CODE}" = "200" ]; then
    echo "[OK] Worker erreichbar auf ${BASE_URL}/ (HTTP ${CODE})"
    break
  fi
  if [ "${i}" = "60" ]; then
    echo "[FEHLER] Worker nach 60s nicht erreichbar (letzter Code: ${CODE}). Siehe ${LOGFILE}"
    exit 1
  fi
  sleep 1
done

# 3) API-Key sicherstellen (falls KV-State verloren ging)
APIKEYS=$(curl -s -m 10 "${BASE_URL}/admin/apikey" -H "X-Admin-Key: ${ADMIN_KEY}" 2>/dev/null)
if echo "${APIKEYS}" | grep -q "${API_KEY}"; then
  echo "[OK] API-Key ${API_KEY} existiert bereits."
else
  echo "[..] Lege API-Key ${API_KEY} neu an..."
  RES=$(curl -s -m 10 -X POST "${BASE_URL}/admin/apikey" -H "X-Admin-Key: ${ADMIN_KEY}" -H "Content-Type: application/json" -d "{\"api_key\":\"${API_KEY}\"}" 2>/dev/null)
  echo "    -> ${RES}"
fi

# 4) Guest-Token-Pool befüllen (auto-fill/run)
echo "[..] Prüfe/Befülle Guest-Token-Pool (auto-fill)..."
POOL=$(curl -s -m 60 -X POST "${BASE_URL}/admin/auto-fill/run" -H "X-Admin-Key: ${ADMIN_KEY}" 2>/dev/null)
echo "${POOL}"
AFTER=$(echo "${POOL}" | grep -o '"after_count":[0-9]*' | head -1 | cut -d: -f2)
if [ -n "${AFTER}" ] && [ "${AFTER}" -gt 0 ]; then
  echo "[OK] Token-Pool gefüllt: ${AFTER} Token verfügbar."
else
  echo "[WARN] Token-Pool konnte nicht verifiziert/befüllt werden — Antwort siehe oben."
fi

# 5) Status
echo ""
echo "=== STATUS ==="
echo "Worker:     ${BASE_URL} (Port ${PORT})"
echo "Admin-Key:  ${ADMIN_KEY}"
echo "API-Key:    ${API_KEY}"
echo "Token-Pool: ${AFTER:-unbekannt} Token"
echo "Log:        ${LOGFILE}"
