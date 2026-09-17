#!/usr/bin/env bash
# config-watchdog.sh: Überwacht opencode.json per inotify und restartet den
# opencode-Server automatisch, wenn sich die Config ändert (neue Modelle etc.).
#
# Wird von start-on-boot.sh und setup.sh als Hintergrund-Daemon gestartet.
# Lockfile-gesichert, Log unter /tmp/opencode/config-watchdog.log.
set -u
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOCK=/tmp/opencode/config-watchdog.lock
LOG=/tmp/opencode/config-watchdog.log
CONFIG="$REPO_ROOT/.opencode/opencode.json"
DEBOUNCE_SECONDS=3

mkdir -p /tmp/opencode

# Nur eine Instanz
if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then
  exit 0
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT
trap '' HUP  # SIGHUP ignorieren

echo "$(date '+%H:%M:%S') [config-watchdog] Gestartet (PID $$), überwache $CONFIG" >> "$LOG"

# Fallback: Falls inotifywait nicht installiert ist, Polling (alle 10s md5sum)
if ! command -v inotifywait >/dev/null 2>&1; then
  echo "$(date '+%H:%M:%S') [config-watchdog] WARN: inotifywait fehlt, Fallback auf Polling (10s)" >> "$LOG"
  LAST_HASH="$(md5sum "$CONFIG" 2>/dev/null | cut -d' ' -f1)"
  while true; do
    sleep 10
    CURRENT_HASH="$(md5sum "$CONFIG" 2>/dev/null | cut -d' ' -f1)"
    if [ "$CURRENT_HASH" != "$LAST_HASH" ]; then
      echo "$(date '+%H:%M:%S') [config-watchdog] Config geändert (Polling), restarte opencode-server..." >> "$LOG"
      sleep "$DEBOUNCE_SECONDS"
      # Nochmal lesen (Debounce: falls mehrere Writes hintereinander)
      CURRENT_HASH="$(md5sum "$CONFIG" 2>/dev/null | cut -d' ' -f1)"
      bash "$REPO_ROOT/infra/scripts/opencode-server.sh" restart >> "$LOG" 2>&1 || true
      LAST_HASH="$CURRENT_HASH"
    fi
  done
fi

# Hauptpfad: inotifywait
while true; do
  # -e close_write: feuert wenn die Datei fertig geschrieben wurde
  # -e moved_to: feuert wenn eine neue Datei an den Pfad verschoben wird (atomarer Write)
  inotifywait -qq -e close_write -e moved_to "$(dirname "$CONFIG")" 2>/dev/null || {
    # inotifywait kann bei Verzeichnis-Löschung/Neuanlage fehlschlagen
    echo "$(date '+%H:%M:%S') [config-watchdog] inotifywait beendet, warte 10s und starte neu..." >> "$LOG"
    sleep 10
    continue
  }

  # Nur reagieren wenn sich tatsächlich opencode.json geändert hat
  # (inotifywait auf das Verzeichnis feuert auch bei anderen Dateien)
  if [ ! -f "$CONFIG" ]; then
    continue
  fi

  # Debounce: kurz warten, falls mehrere Writes kommen (Editor save etc.)
  sleep "$DEBOUNCE_SECONDS"

  # Prüfen ob der Server überhaupt läuft — wenn nicht, Restart unnötig
  # (der normale Watchdog kümmert sich ums Hochfahren)
  if ! curl -sf -m 2 http://127.0.0.1:4096/ >/dev/null 2>&1; then
    echo "$(date '+%H:%M:%S') [config-watchdog] Config geändert, aber Server nicht aktiv — skip (proxy-watchdog startet ihn)." >> "$LOG"
    continue
  fi

  echo "$(date '+%H:%M:%S') [config-watchdog] opencode.json geändert — restarte opencode-server..." >> "$LOG"
  bash "$REPO_ROOT/infra/scripts/opencode-server.sh" restart >> "$LOG" 2>&1 || true
  echo "$(date '+%H:%M:%S') [config-watchdog] Restart abgeschlossen." >> "$LOG"
done
