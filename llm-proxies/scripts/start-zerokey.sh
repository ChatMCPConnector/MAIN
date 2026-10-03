#!/usr/bin/env bash
# Startet ZeroKey aus dem MAIN-Repo (kein Klon, kein fremdes Verzeichnis nötig).
# Code liegt in llm-proxies/zerokey/ — kanonisch, siehe infrastructure.md.
#
# Aufruf: node server.js <provider> <username> <session-name>
# ZeroKey bedient EINEN Provider pro Prozess (server.js:50 liest den Provider aus
# argv[2]). Fuer einen zweiten Provider laeuft deshalb eine zweite Instanz mit
# eigenem Port — nicht ein zweites Startskript (Anti-Drift, AGENTS.md 7).
#
#   start-zerokey.sh                        # ChatGPT auf 7250 (Default, unveraendert)
#   start-zerokey.sh --provider deepseek --port 7300
#   start-zerokey.sh --provider deepseek --port 7300 --restart
#
# Optional: --restart beendet einen laufenden Proxy und startet ihn neu.
# Der Login (Cookies + Token) liegt in temp/users.json und ist GITIGNORIERT:
# Runtime, kein Quelltext. Fehlt die Datei, startet der Proxy nicht sinnvoll
# — siehe infrastructure.md, Abschnitt "ZeroKey".
set -euo pipefail
# temp/users.json (Session-Cookies) wird zur Laufzeit von der Node-App selbst
# atomar neu geschrieben — dann zaehlt deren umask, nicht das einmalige
# `chmod 600` unten. umask hier vererbt sich auf den node-Prozess.
umask 077

APP_DIR="/workspaces/MAIN/llm-proxies/zerokey"
HOST="127.0.0.1"

# Defaults = die bisherige ChatGPT-Instanz. Alles per Flag ueberschreibbar.
PROVIDER="chatgpt"
ZKEY_USER="main"
ZKEY_SESSION="MAIN"
PORT="7250"
RESTART=0

while [ $# -gt 0 ]; do
    case "$1" in
        --provider) PROVIDER="${2:?--provider braucht einen Wert}"; shift 2 ;;
        --user)     ZKEY_USER="${2:?--user braucht einen Wert}"; shift 2 ;;
        --session)  ZKEY_SESSION="${2:?--session braucht einen Wert}"; shift 2 ;;
        --port)     PORT="${2:?--port braucht einen Wert}"; shift 2 ;;
        --restart)  RESTART=1; shift ;;
        -h|--help)
            sed -n '2,20p' "$0"; exit 0 ;;
        *) echo "Unbekanntes Argument: $1 (siehe --help)" >&2; exit 2 ;;
    esac
done

# PID-Datei und Log pro Instanz: sonst überschreiben sich ChatGPT und DeepSeek
# gegenseitig die PID und das Log, und ein --restart killt die falsche Instanz.
LOG="/tmp/opencode/zerokey-${PROVIDER}.log"
PIDFILE="/tmp/opencode/zerokey-${PROVIDER}.pid"
MODELS_URL="http://${HOST}:${PORT}/v1/models"

# Prozessmuster für pgrep/kill. Enthält provider+user+session, damit --restart
# gezielt die EIGENE Instanz trifft (live belegt 2026-10-02: die alte Form war
# vollstaendig hartverdrahtet und traf damit zwangslaeufig die ChatGPT-Instanz).
PROC_PATTERN="node server.js ${PROVIDER} ${ZKEY_USER} ${ZKEY_SESSION}"

# Der DeepSeek-Provider fährt per Default einen *headed* Chromium
# (providers/deepseek/browser-transport.js:102) und stirbt ohne X-Server:
#   "Missing X server or $DISPLAY … The platform failed to initialize."
# (live belegt 2026-10-03). Der Codespace hat keinen — Xvfb wird hier sichergestellt,
# damit JEDER Aufrufer (setup.sh, Watchdog, Hand) sie bekommt und nicht nur der,
# der es einmal von Hand gemacht hat. Display :120 ist die MAIN-Konvention
# (browser-start.sh, Firefox/noVNC). Reverse: DISPLAY ist überschreibbar,
# ZK_DISPLAY wählt das Xvfb-Display.
ZK_DISPLAY="${ZK_DISPLAY:-:120}"

ensure_x_display() {
    [ -n "${DISPLAY:-}" ] && return 0
    if ! command -v Xvfb >/dev/null 2>&1; then
        echo "FEHLER: Provider '$PROVIDER' braucht einen Browser, aber weder DISPLAY noch Xvfb sind da." >&2
        echo "       Xvfb installieren oder DEEPSEEK_TRANSPORT=api setzen (ohne Browser, mit PoW-Löser)." >&2
        return 1
    fi
    mkdir -p /workspaces/MAIN/.runtime/log
    setsid nohup Xvfb "$ZK_DISPLAY" -screen 0 1280x800x24 \
        </dev/null >/workspaces/MAIN/.runtime/log/xvfb.log 2>&1 &
    disown $! 2>/dev/null || true
    for _ in $(seq 1 50); do
        [ -S "/tmp/.X11-unix/X${ZK_DISPLAY#:}" ] && break
        sleep 0.2
    done
    if [ ! -S "/tmp/.X11-unix/X${ZK_DISPLAY#:}" ]; then
        echo "FEHLER: Xvfb auf $ZK_DISPLAY wurde nicht bereit (Log: .runtime/log/xvfb.log)" >&2
        return 1
    fi
    export DISPLAY="$ZK_DISPLAY"
    echo "Xvfb auf $ZK_DISPLAY gestartet (DISPLAY für Provider '$PROVIDER')."
}

# MAIN (2026-10-03): DeepSeek laeuft im Default auf dem DIRECT-FETCH-Transport
# ('api'), nicht mehr im Browser-Transport. Grund ist ein Fehlverhalten, das
# live gemessen wurde: `browser-transport.js` bekommt `parentMessageId`, tut
# ihn aber nichts an (`chatCompletion(chatSessionId, prompt, _parentMessageId,
# …)` — der Parameter heisst absichtlich unbenutzt). Die Seite sendet deshalb
# ihren veralteten Parent, DeepSeek legt pro Turn einen neuen Zweig an, und in
# der Web-Uebersicht erscheint **ein eigener Chat pro Turn**. A/B-Beleg:
#   api-Transport      3 Turns -> 1 Conversation, Akkumulator 867 -> 2534
#   browser-Transport  3 Turns -> 3 Conversations (D1, D2, D3), message_id
#                      immer 2, parentMessageId klemmt bei 2
# Der api-Transport erhaelt den Faden (message_id 2 -> 4 -> 6, bei gesetzter
# parent_message_id) und braucht **keinen Browser**: kein Xvfb, kein headed
# Chromium, kein 16-MB-Profil.
#
# 'browser' bleibt erzwingbar (ZK_BROWSER_TRANSPORT=1 oder
# DEEPSEEK_TRANSPORT=browser in der Umgebung) — dann greift ensure_x_display
# wie bisher. Der Default ist hier gesetzt, weil ZeroKeys eigener Default
# 'browser' ist; die Abweichung ist in infrastructure.md dokumentiert.
deepseek_transport() {
    if [ -n "${DEEPSEEK_TRANSPORT:-}" ]; then
        printf '%s' "${DEEPSEEK_TRANSPORT}" | tr '[:upper:]' '[:lower:]'
    elif [ "${ZK_BROWSER_TRANSPORT:-0}" = "1" ]; then
        printf 'browser'
    else
        printf 'api'
    fi
}

export DEEPSEEK_TRANSPORT
case "$PROVIDER" in
    deepseek)
        DEEPSEEK_TRANSPORT="$(deepseek_transport)"
        export DEEPSEEK_TRANSPORT
        if [ "$DEEPSEEK_TRANSPORT" != "api" ]; then
            ensure_x_display || exit 1
        fi
        ;;
esac

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
    echo "ZeroKey-Credentials aus $SECRETS_FILE übernommen."
fi

if [ ! -f "$APP_DIR/temp/users.json" ]; then
    echo "FEHLER: $APP_DIR/temp/users.json fehlt — ohne Session-Cookies"
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

# --restart: beende den laufenden Proxy und starte ihn neu. Geparst wird oben
# zusammen mit --provider/--port.

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
    for pid in $(pgrep -f "$PROC_PATTERN" || true); do
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

echo "Starte ZeroKey ($PROVIDER/$ZKEY_USER/$ZKEY_SESSION, aus $APP_DIR)..."
# PORT muss als ENV beim node-Prozess ankommen: config/constants.js liest
# `process.env.PORT`, eine Shell-Variable sieht er nicht. Ohne das startet
# ZeroKey auf dem Default 7250 bzw. weicht auf 7251 aus, während das Skript
# weiter auf dem gewünschten Port pollt. (Live belegt 2026-10-03.)
export PORT
# Wichtig: der GANZE Subshell-Body wird umgeleitet, nicht nur `node`. Ein
# `node ... >> "$LOG" 2>&1 &` allein lässt die aufrufende Subshell die
# stdout-Pipe des Aufrufers erben — bei `start-zerokey.sh | tail` wartet tail
# dann ewig auf EOF, während der Proxy längst läuft.
(
    cd "$APP_DIR" || exit 1
    setsid nohup node server.js "$PROVIDER" "$ZKEY_USER" "$ZKEY_SESSION" </dev/null >>"$LOG" 2>&1 &
) >/dev/null 2>&1
disown -a 2>/dev/null || true
sleep 1
# `tail -1`, nicht `head -1`: pgrep sortiert aufsteigend, und der gerade
# gestartete Prozess hat die höchste PID. Mit `head -1` landete im PID-File der
# älteste Prozess im System — beim ersten Start (nur einer) zufällig richtig,
# sobald eine alte Instanz zurückblieb zuverlässig falsch.
PID="$(pgrep -f "$PROC_PATTERN" | tail -1 || true)"
[ -n "$PID" ] && echo "$PID" > "$PIDFILE"

for i in $(seq 1 30); do
    if curl -sf -m 2 "$MODELS_URL" >/dev/null 2>&1; then
        echo "OK: ZeroKey ($PROVIDER) antwortet auf ${HOST}:${PORT} (PID $(cat "$PIDFILE" 2>/dev/null || echo '?'))."
        exit 0
    fi
    sleep 1
done

echo "FEHLER: ${MODELS_URL} nach 30s nicht erreichbar. Log:"
tail -n 20 "$LOG"
exit 1
