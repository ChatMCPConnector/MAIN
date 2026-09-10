#!/usr/bin/env bash
# start.sh: Startet gemini-web2api (Default-Port 8083).
#
# Port-Strategie (2026-09-10): fester Default bleibt der Normalfall — Clients
# (opencode.json, Benchmark-Skripte) referenzieren http://127.0.0.1:8083 hart,
# ein dynamischer Grund-Port würde sie brechen. Aber neue Codespaces können den
# Port zufällig belegt haben (Dev-Container-Autostarts, Vorläufer-Prozesse).
# Deshalb: ENV-GEMINI_WEB2API_PORT überschreibt den Default; ist der Ziel-Port
# von einem Fremdprozess belegt und antwortet nicht auf unseren Health-Check,
# suchen wir den nächsten freien Port (PORT+1..PORT+10) und schreiben ihn nach
# $DIR/port — Consumer können die Datei lesen statt 8083 hart zu coden.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDFILE="$DIR/gemini-web2api.pid"
PORTFILE="$DIR/port"
LOGFILE="/tmp/opencode/gemini-web2api.log"
HOST="127.0.0.1"
PORT="${GEMINI_WEB2API_PORT:-8083}"

mkdir -p /tmp/opencode
mkdir -p "$DIR/data"

port_listens() { ss -tln | grep -q ":${1} "; }
# Health-Check mit Signatur: Root liefert {"models":[...]} — ein fremder
# HTTP-Server (z.B. python http.server, Dev-App) antwortet auf / zwar 200,
# aber ohne dieses Feld. Nur die echte Signatur gilt als "wir laufen schon".
port_healthy() {
  curl -sf -m 2 "http://"${HOST}":"${1}"/" 2>/dev/null | grep -q '"models"'
}

# Bereits laufende eigene Instanz: nichts tun.
if port_listens "$PORT" && port_healthy "$PORT"; then
  echo "[gemini-web2api] Läuft bereits auf Port ${PORT} (/ OK)."
  echo "$PORT" > "$PORTFILE"
  exit 0
fi

# Belegt, aber nicht unser Health-Endpoint → Fremdprozess → Fallback-Port.
if port_listens "$PORT"; then
  echo "[gemini-web2api] WARN: Port ${PORT} von Fremdprozess belegt — suche Ausweichport..."
  FOUND=""
  for CAND in $(seq "$((PORT + 1))" "$((PORT + 10))"); do
    if ! port_listens "$CAND"; then FOUND="$CAND"; break; fi
  done
  if [ -z "$FOUND" ]; then
    echo "[gemini-web2api] FEHLER: Ports ${PORT}..$((PORT+10)) alle belegt." >&2
    exit 1
  fi
  echo "[gemini-web2api] Ausweichport ${FOUND} (Standard ${PORT} belegt; Clients via $PORTFILE oder GEMINI_WEB2API_PORT=${FOUND} umstellen)."
  PORT="$FOUND"
fi

COOKIE_ARG=""
if [ -f "/workspaces/MAIN/.secrets/gemini-web-cookie.txt" ]; then
  COOKIE_ARG="--cookie-file /workspaces/MAIN/.secrets/gemini-web-cookie.txt"
fi

echo "[gemini-web2api] Starte gemini-web2api-go auf Port ${PORT}..."
cd "$DIR"
nohup ./gemini-web2api-go \
  --port "${PORT}" \
  --db "$DIR/data/gemini.db" \
  --admin-token gemini-admin-secret-2026 \
  --api-key sk-gemini-pro-local-2026 \
  $COOKIE_ARG \
  </dev/null >> "${LOGFILE}" 2>&1 &
SERVER_PID=$!
disown "$SERVER_PID" 2>/dev/null || true
echo "$SERVER_PID" > "${PIDFILE}"
echo "$PORT" > "$PORTFILE"

for i in $(seq 1 30); do
  if port_healthy "$PORT"; then
    echo "[gemini-web2api] OK: Antwortet auf Port ${PORT}."
    exit 0
  fi
  sleep 1
done

echo "[gemini-web2api] FEHLER: Port ${PORT} nicht erreichbar. Log:"
tail -n 20 "${LOGFILE}" 2>/dev/null || true
exit 1