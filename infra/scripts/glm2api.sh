#!/bin/bash
# infra/scripts/glm2api.sh: Betriebsskript für den glm2api-Proxy (status/restart).
# Gehärtet: PID-Datei-basiertes Stoppen (kein globales pkill -f), Start-Health-
# Check, Fallback-Stop nur mit Pfad-Anker über /proc/<pid>/cwd.
set -uo pipefail

GLM2API_DIR="/workspaces/MAIN/llm-proxies/glm2api"
PID_FILE="$GLM2API_DIR/glm2api.pid"
LOG_DIR="$GLM2API_DIR/log"
OUTPUT_LOG="$LOG_DIR/glm2api_output.log"
HOST="127.0.0.1"
PORT=8001
HEALTH_URL="http://$HOST:$PORT/health"

usage() {
  echo "Verwendung: $0 {status|restart}"
  echo ""
  echo "  status   - Status des glm2api-Servers prüfen"
  echo "  restart  - glm2api-Server neu starten"
  exit 1
}

# Liefert die PIDs aller Prozesse, die main.py ausführen UND deren
# Arbeitsverzeichnis (via /proc/<pid>/cwd) GLM2API_DIR ist — schützt fremde
# main.py-Prozesse aus anderen Checkouts/Anwendungen.
managed_pids() {
  local pid cwd
  for proc in /proc/[0-9]*; do
    pid="${proc#/proc/}"
    [ -r "$proc/cmdline" ] || continue
    case "$(tr '\0' ' ' < "$proc/cmdline")" in
      *main.py*)
        cwd="$(readlink "$proc/cwd" 2>/dev/null)" || continue
        [ "$cwd" = "$GLM2API_DIR" ] && echo "$pid"
        ;;
    esac
  done
}

# Prüft, ob die PID-Datei existiert und der darin verzeichnete Prozess
# noch mit main.py im GLM2API_DIR läuft; gibt die validierte PID aus.
pid_file_pid() {
  local pid cwd
  [ -f "$PID_FILE" ] || return 1
  pid="$(cat "$PID_FILE" 2>/dev/null)" || return 1
  [ -n "$pid" ] && [ -d "/proc/$pid" ] || return 1
  case "$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)" in
    *main.py*) ;;
    *) return 1 ;;
  esac
  cwd="$(readlink "/proc/$pid/cwd" 2>/dev/null)" || return 1
  [ "$cwd" = "$GLM2API_DIR" ] || return 1
  echo "$pid"
}

health_ok() {
  curl -sf -m 2 "$HEALTH_URL" >/dev/null 2>&1
}

stop_server() {
  local pid pids
  # Weg 1: gezielt über PID-Datei (nur diese eine PID)
  if pid="$(pid_file_pid)"; then
    echo "Stoppe PID $pid (aus PID-Datei)..."
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 20); do
      [ -d "/proc/$pid" ] || break
      sleep 0.5
    done
    if [ -d "/proc/$pid" ]; then
      echo "  Prozess reagiert nicht auf TERM — sende KILL."
      kill -9 "$pid" 2>/dev/null || true
      sleep 1
    fi
  else
    # Weg 2 (Fallback): Muster-Suche MIT Pfad-Anker (/proc/<pid>/cwd)
    pids="$(managed_pids)"
    if [ -n "$pids" ]; then
      for pid in $pids; do
        echo "Stoppe PID $pid (main.py in $GLM2API_DIR)..."
        kill "$pid" 2>/dev/null || true
      done
      sleep 2
    else
      echo "Kein laufender glm2api-Prozess gefunden (weiter zum Start)."
    fi
  fi
  rm -f "$PID_FILE"

  pids="$(managed_pids)"
  if [ -n "$pids" ]; then
    echo "Fehler: Prozess(e) $pids konnten nicht gestoppt werden"
    exit 1
  fi
  echo "✓ Prozess gestoppt"
}

start_server() {
  mkdir -p "$LOG_DIR"
  cd "$GLM2API_DIR" || exit 1
  nohup python3 main.py >> "$OUTPUT_LOG" 2>&1 &
  local pid=$!
  # PID atomar in Datei schreiben (gleiche Partition → rename ist atomar)
  printf '%s\n' "$pid" > "$PID_FILE.tmp" && mv -f "$PID_FILE.tmp" "$PID_FILE"
  echo "✓ Server gestartet (PID: $pid)"

  echo "Warte auf Start..."
  for _ in $(seq 1 30); do
    if health_ok; then
      echo "✓ Server erreichbar ($HEALTH_URL)"
      return 0
    fi
    [ -d "/proc/$pid" ] || { echo "✗ Prozess gestorben - siehe Logfile: $OUTPUT_LOG"; return 1; }
    sleep 1
  done
  echo "⚠ Server noch nicht erreichbar - siehe Logfile: $OUTPUT_LOG"
  return 0
}

check_status() {
  local pid pids
  echo "=== glm2api Server Status ==="

  # Prozess prüfen (Pfad-angepielter Match via /proc/<pid>/cwd)
  pids="$(managed_pids)"
  if [ -n "$pids" ]; then
    echo "✓ Prozess läuft (PID: $(echo $pids | tr '\n' ' '))"
  else
    echo "✗ Prozess läuft nicht"
  fi
  if pid="$(pid_file_pid)"; then
    echo "✓ PID-Datei konsistent (PID: $pid)"
  else
    echo "ℹ Keine gültige PID-Datei ($PID_FILE)"
  fi

  # Health-Endpoint prüfen
  echo ""
  echo "Health-Endpoint ($HEALTH_URL):"
  if health_ok; then
    echo "✓ Server erreichbar"
    curl -s -m 2 "$HEALTH_URL"
    echo
  else
    echo "✗ Server nicht erreichbar"
  fi

  echo ""
  echo "Endpunkt-Prüfung (http://$HOST:$PORT/v1/models):"
  if curl -sf -m 2 "http://$HOST:$PORT/v1/models" > /dev/null 2>&1; then
    MODEL_COUNT=$(curl -s -m 2 "http://$HOST:$PORT/v1/models" | jq -r '.data | length' 2>/dev/null || echo "?")
    echo "✓ Models-Endpunkt erreichbar ($MODEL_COUNT Modelle)"
  else
    echo "✗ Models-Endpunkt nicht erreichbar"
  fi

  echo ""
  echo "=== Letzte Logs (letzte 10 Zeilen) ==="
  if [ -f "$OUTPUT_LOG" ]; then
    tail -10 "$OUTPUT_LOG"
  else
    echo "Kein Logfile gefunden: $OUTPUT_LOG"
  fi
}

restart_server() {
  echo "=== glm2api Server neu starten ==="
  stop_server
  echo ""
  echo "Starte Server..."
  start_server
  echo ""
  echo "Neustart abgeschlossen"
}

# Main
case "${1:-}" in
  status)
    check_status
    ;;
  restart)
    restart_server
    ;;
  *)
    usage
    ;;
esac
