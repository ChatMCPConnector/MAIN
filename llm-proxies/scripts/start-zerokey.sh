#!/usr/bin/env bash
# Startet ZeroKey aus dem MAIN-Repo (kein Klon, kein fremdes Verzeichnis nötig).
# Code liegt in llm-proxies/zerokey/ — kanonisch, siehe infrastructure.md.
#
# Aufruf: node server.js <provider> <username> <session-name>
# Der ChatGPT-Login (Cookies + Sentinel-Token) liegt in temp/users.json und ist
# GITIGNORIERT: Runtime, kein Quelltext. Fehlt die Datei, startet der Proxy
# nicht sinnvoll — siehe infrastructure.md, Abschnitt "ZeroKey".
set -euo pipefail
# temp/users.json (ChatGPT-Cookies) wird zur Laufzeit von der Node-App selbst
# atomar neu geschrieben — dann zaehlt deren umask, nicht das einmalige
# `chmod 600` unten. umask hier vererbt sich auf den node-Prozess.
umask 077

APP_DIR="/workspaces/MAIN/llm-proxies/zerokey"
LOG="/tmp/opencode/zerokey.log"
PIDFILE="/tmp/opencode/zerokey.pid"
HOST="127.0.0.1"
PORT="7250"
MODELS_URL="http://${HOST}:${PORT}/v1/models"

mkdir -p /tmp/opencode "$(dirname "$LOG")"

if [ ! -d "$APP_DIR" ]; then
    echo "FEHLER: $APP_DIR existiert nicht."
    exit 1
fi

# Abhängigkeiten (nur beim ersten Mal / nach Änderungen an pnpm-lock.yaml)
if [ ! -d "$APP_DIR/node_modules" ]; then
    echo "Installiere ZeroKey-Abhängigkeiten (einmalig, Playwright lädt Chromium)..."
    (cd "$APP_DIR" && pnpm install --frozen-lockfile) || {
        echo "FEHLER: pnpm install fehlgeschlagen."
        exit 1
    }
fi

# Credentials: aus dem Secret-Bundle, falls der Unlock sie bereitgestellt hat.
SECRETS_FILE="${HOME}/.config/landscape/zerokey-users.json"
if [ ! -f "$APP_DIR/temp/users.json" ] && [ -f "$SECRETS_FILE" ]; then
    mkdir -p "$APP_DIR/temp"
    cp "$SECRETS_FILE" "$APP_DIR/temp/users.json"
    chmod 600 "$APP_DIR/temp/users.json"
    echo "ChatGPT-Credentials aus $SECRETS_FILE übernommen."
fi

if [ ! -f "$APP_DIR/temp/users.json" ]; then
    echo "FEHLER: $APP_DIR/temp/users.json fehlt — ohne ChatGPT-Cookies"
    echo "startet ZeroKey nicht. Siehe infrastructure.md, Abschnitt \"ZeroKey\"."
    exit 1
fi

# Beendet einen PID und wartet, bis er wirklich weg ist — mit Notbremse.
# Ein blosses `kill; sleep 1` ist unzuverlaessig: der Prozess haelt den Port
# noch, wenn der neue Start ihn prueft, und der neue Server scheitert dann an
# "Adresse bereits belegt". Live beobachtet am 2026-09-30.
stop_pid() {
    local pid="$1" i
    [ -n "$pid" ] || return 0
    kill -0 "$pid" 2>/dev/null || return 0
    kill "$pid" 2>/dev/null || true
    for i in $(seq 1 20); do            # max 10s auf SIGTERM
        kill -0 "$pid" 2>/dev/null || return 0
        sleep 0.5
    done
    echo "WARN: PID $pid reagiert nicht auf SIGTERM — SIGKILL."
    kill -9 "$pid" 2>/dev/null || true
    for i in $(seq 1 10); do            # max 5s danach
        kill -0 "$pid" 2>/dev/null || return 0
        sleep 0.5
    done
    echo "FEHLER: PID $pid laesst sich nicht beenden."
    return 1
}

# Läuft er schon? Dann nur prüfen, nicht doppelt starten.
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null; then
    if curl -sf -m 3 "$MODELS_URL" >/dev/null 2>&1; then
        echo "ZeroKey läuft bereits (PID $(cat "$PIDFILE"), Port ${PORT})."
        exit 0
    fi
    echo "WARN: PID $(cat "$PIDFILE") lebt, antwortet aber nicht — beende ihn."
    stop_pid "$(cat "$PIDFILE")" || exit 1
    rm -f "$PIDFILE"
fi

# Port-Belegung prüfen: ist es UNSER Proxy oder ein fremder Prozess?
if ss -tln 2>/dev/null | grep -q ":${PORT} "; then
    if curl -sf -m 2 "$MODELS_URL" >/dev/null 2>&1; then
        echo "Läuft bereits auf Port ${PORT} (/v1/models OK)."
        exit 0
    fi
    echo "FEHLER: Port ${PORT} ist belegt, aber ${MODELS_URL} antwortet nicht"
    echo "korrekt — vermutlich ein fremder Prozess. ZeroKey NICHT gestartet."
    echo "Belegung prüfen: ss -tlnp | grep :${PORT}"
    exit 1
fi

echo "Starte ZeroKey (aus $APP_DIR)..."
# Wichtig: der GANZE Subshell-Body wird umgeleitet, nicht nur `node`. Ein
# `node ... >> "$LOG" 2>&1 &` allein lässt die aufrufende Subshell die
# stdout-Pipe des Aufrufers erben — bei `start-zerokey.sh | tail` wartet tail
# dann ewig auf EOF, während der Proxy längst läuft.
(
    cd "$APP_DIR" || exit 1
    setsid nohup node server.js chatgpt main MAIN </dev/null >>"$LOG" 2>&1 &
) >/dev/null 2>&1
disown -a 2>/dev/null || true
sleep 1
PID="$(pgrep -f "node server.js chatgpt main MAIN" | head -1 || true)"
[ -n "$PID" ] && echo "$PID" > "$PIDFILE"

for i in $(seq 1 30); do
    if curl -sf -m 2 "$MODELS_URL" >/dev/null 2>&1; then
        echo "OK: ZeroKey antwortet auf ${HOST}:${PORT} (PID $(cat "$PIDFILE" 2>/dev/null || echo '?'))."
        exit 0
    fi
    sleep 1
done

echo "FEHLER: ${MODELS_URL} nach 30s nicht erreichbar. Log:"
tail -n 20 "$LOG"
exit 1
