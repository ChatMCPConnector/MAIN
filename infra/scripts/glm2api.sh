#!/bin/bash

set -e

GLM2API_DIR="/workspaces/MAIN/llm-proxies/glm2api"
PID_FILE="$GLM2API_DIR/glm2api.pid"
LOG_DIR="$GLM2API_DIR/log"
OUTPUT_LOG="$LOG_DIR/glm2api_output.log"
PORT=8001

usage() {
  echo "Verwendung: $0 {status|restart}"
  echo ""
  echo "  status   - Status des glm2api-Servers prüfen"
  echo "  restart  - glm2api-Server neu starten"
  exit 1
}

check_status() {
  echo "=== glm2api Server Status ==="
  
  # Prozess prüfen
  if pgrep -f "python.*glm2api" > /dev/null; then
    echo "✓ Prozess läuft (PID: $(pgrep -f 'python.*glm2api'))"
  else
    echo "✗ Prozess läuft nicht"
  fi
  
  # Health-Endpoint prüfen
  echo ""
  echo "Health-Endpoint (http://127.0.0.1:$PORT/health):"
  if curl -s -f http://127.0.0.1:$PORT/health > /dev/null 2>&1; then
    echo "✓ Server erreichbar"
    curl -s http://127.0.0.1:$PORT/health | jq . 2>/dev/null || curl -s http://127.0.0.1:$PORT/health
  else
    echo "✗ Server nicht erreichbar"
  fi
  
  echo ""
  echo "Endpunkt-Prüfung (http://127.0.0.1:$PORT/v1/models):"
  if curl -s -f http://127.0.0.1:$PORT/v1/models > /dev/null 2>&1; then
    MODEL_COUNT=$(curl -s http://127.0.0.1:$PORT/v1/models | jq -r '.data | length' 2>/dev/null || echo "?")
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
  
  # Stoppen
  if pgrep -f "python.*glm2api" > /dev/null; then
    echo "Stoppe laufenden Prozess..."
    pkill -f "python.*glm2api"
    sleep 2
  fi
  
  # Prüfen ob noch läuft
  if pgrep -f "python.*glm2api" > /dev/null; then
    echo "Fehler: Prozess konnte nicht gestoppt werden"
    exit 1
  fi
  echo "✓ Prozess gestoppt"
  
  # Log-Verzeichnis erstellen falls nicht vorhanden
  mkdir -p "$LOG_DIR"
  
  # Starten
  echo "Starte Server..."
  cd "$GLM2API_DIR"
  nohup python main.py > "$OUTPUT_LOG" 2>&1 &
  NEW_PID=$!
  echo "✓ Server gestartet (PID: $NEW_PID)"
  
  # Warten und Status prüfen
  echo ""
  echo "Warte auf Start..."
  sleep 3
  
  if pgrep -f "python.*glm2api" > /dev/null; then
    echo "✓ Prozess läuft"
  else
    echo "✗ Prozess läuft nicht - siehe Logfile: $OUTPUT_LOG"
    exit 1
  fi
  
  if curl -s -f http://127.0.0.1:$PORT/health > /dev/null 2>&1; then
    echo "✓ Server erreichbar"
  else
    echo "⚠ Server noch nicht erreichbar - siehe Logfile"
  fi
  
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
