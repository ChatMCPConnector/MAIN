#!/usr/bin/env bash
# Startet ZeroKey aus dem MAIN-Repo (kein Klon, kein fremdes Verzeichnis nötig).
# Code liegt in llm-proxies/zerokey/ — kanonisch, siehe infrastructure.md.
#
# Aufruf: node server.js <provider> <username> <session-name>
# Optional: --restart beendet einen laufenden Proxy und startet ihn neu.
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

# --restart: beende den laufenden Proxy und starte ihn neu.
RESTART=0
case "${1:-}" in
    --restart) RESTART=1 ;;
    "") ;;
    *)
        echo "Aufruf: start-zerokey.sh [--restart]" >&2
        exit 2
        ;;
esac

# Läuft er schon? Dann nur prüfen, nicht doppelt starten — die Sperre ist
# Absicht. Sie verweigerte aber auch den Neustart eines *gesunden* Prozesses,
# der genau dann neu geladen werden musste (2026-10-02: Code-Fix im Speicher,
# Betrieb musste angeschrieben werden). Deshalb der zweite Weg, statt die
# Sperre aufzuweichen: ohne Flag ist das Verhalten unverändert.
#
# Unter --restart wird nicht die PID-Datei geglaubt, sondern das Prozessmuster:
# nach einem Codespace-Neustart kann die Datei verwaist sein, während der Proxy
# läuft. Und es werden ALLE passenden Instanzen beendet, nicht nur eine — sonst
# bleibt eine alte stehen und bindet nach dem Start den Port, während die
# PID-Datei auf einen Prozess zeigt, der nichts tut. (Live belegt 2026-10-02:
# nach einem Neustart liefen zwei Instanzen, die PID-Datei zeigte auf die
# verwaiste, der Port gehörte der anderen. Ursache im Absatz weiter unten.)
if [ "$RESTART" -eq 1 ]; then
    for pid in $(pgrep -f "node server.js chatgpt main MAIN" || true); do
        echo "Neustart angefordert — beende PID ${pid} (Port ${PORT} wird neu gebunden)."
        stop_pid "$pid" || exit 1
    done
    rm -f "$PIDFILE"
    RUNNING=""
elif [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null; then
    RUNNING="$(cat "$PIDFILE")"
else
    RUNNING=""
fi

if [ -n "$RUNNING" ]; then
    if [ "$RESTART" -eq 0 ] && curl -sf -m 3 "$MODELS_URL" >/dev/null 2>&1; then
        echo "ZeroKey läuft bereits (PID ${RUNNING}, Port ${PORT})."
        exit 0
    fi
    if [ "$RESTART" -eq 1 ]; then
        echo "Neustart angefordert — beende PID ${RUNNING} (Port ${PORT} wird neu gebunden)."
    else
        echo "WARN: PID ${RUNNING} lebt, antwortet aber nicht — beende ihn."
    fi
    stop_pid "$RUNNING" || exit 1
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
# `tail -1`, nicht `head -1`: pgrep sortiert aufsteigend, und der gerade
# gestartete Prozess hat die höchste PID. Mit `head -1` landete im PID-File der
# älteste Prozess im System — beim ersten Start (nur einer) zufällig richtig,
# sobald eine alte Instanz zurückblieb zuverlässig falsch.
PID="$(pgrep -f "node server.js chatgpt main MAIN" | tail -1 || true)"
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
