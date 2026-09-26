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
DEBOUNCE_SECONDS=8
PAUSE_FILE=/tmp/opencode/config-watchdog.pause

mkdir -p /tmp/opencode

# Nur eine Instanz
if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then
  exit 0
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT
trap '' HUP  # SIGHUP ignorieren

echo "$(date '+%H:%M:%S') [config-watchdog] Gestartet (PID $$), überwache $CONFIG (Debounce: ${DEBOUNCE_SECONDS}s, Busy-Guard aktiv)" >> "$LOG"

safe_restart() {
  # 1. Debounce: kurz warten, falls mehrere Writes kommen (Editor save etc.)
  sleep "$DEBOUNCE_SECONDS"

  # 2. Pause-Lockfile prüfen (Agent oder Nutzer hat Watchdog pausiert)
  while [ -f "$PAUSE_FILE" ]; do
    echo "$(date '+%H:%M:%S') [config-watchdog] Pausiert durch $PAUSE_FILE — warte..." >> "$LOG"
    sleep 3
  done

  # 3. Prüfen ob der Server überhaupt läuft — wenn nicht, Restart unnötig
  if ! curl -sf -m 2 http://127.0.0.1:4096/ >/dev/null 2>&1; then
    echo "$(date '+%H:%M:%S') [config-watchdog] Config geändert, aber Server nicht aktiv — skip." >> "$LOG"
    return 0
  fi

  # 4. Busy-Guard: Niemals restarten solange eine Session aktiv arbeitet
  local max_wait=300
  local waited=0
  local check_url="http://127.0.0.1:4096/session/status"

  while [ $waited -lt $max_wait ]; do
    local status
    status="$(curl -sf -m 2 "$check_url" 2>/dev/null || echo "{}")"
    if echo "$status" | grep -q '"busy"'; then
      echo "$(date '+%H:%M:%S') [config-watchdog] Session aktiv ('busy') — warte vor Restart (${waited}s)..." >> "$LOG"
      sleep 3
      waited=$((waited + 3))
    else
      # Session ist idle — 3s Puffer damit Response-Stream sicher beendet ist
      sleep 3
      status="$(curl -sf -m 2 "$check_url" 2>/dev/null || echo "{}")"
      if ! echo "$status" | grep -q '"busy"'; then
        break
      fi
    fi
  done

  echo "$(date '+%H:%M:%S') [config-watchdog] opencode.json geändert & Server idle — restarte opencode-server..." >> "$LOG"
  bash "$REPO_ROOT/infra/scripts/opencode-server.sh" restart >> "$LOG" 2>&1 || true
  echo "$(date '+%H:%M:%S') [config-watchdog] Restart abgeschlossen." >> "$LOG"
}

# Fallback: Falls inotifywait nicht installiert ist, Polling (alle 10s md5sum)
if ! command -v inotifywait >/dev/null 2>&1; then
  echo "$(date '+%H:%M:%S') [config-watchdog] WARN: inotifywait fehlt, Fallback auf Polling (10s)" >> "$LOG"
  LAST_HASH="$(md5sum "$CONFIG" 2>/dev/null | cut -d' ' -f1)"
  while true; do
    sleep 10
    CURRENT_HASH="$(md5sum "$CONFIG" 2>/dev/null | cut -d' ' -f1)"
    if [ "$CURRENT_HASH" != "$LAST_HASH" ]; then
      echo "$(date '+%H:%M:%S') [config-watchdog] Config geändert (Polling)..." >> "$LOG"
      safe_restart
      CURRENT_HASH="$(md5sum "$CONFIG" 2>/dev/null | cut -d' ' -f1)"
      LAST_HASH="$CURRENT_HASH"
    fi
  done
fi

# Hauptpfad: inotifywait
# inotifywait überwacht das VERZEICHNIS, nicht die Datei: jeder Write in
# .opencode/ (tui.json, package-lock.json, neue agent/*.md) löst ein Event aus.
# Deshalb NACH dem Event den Inhalts-Hash vergleichen — sonst restartet der
# Watchdog den opencode-Server für Änderungen, die opencode.json gar nicht
# betreffen (8s Debounce + Restart, kann laufende Sessions stören).
config_hash() { md5sum "$CONFIG" 2>/dev/null | cut -d' ' -f1; }
LAST_HASH="$(config_hash)"

while true; do
  # -e close_write: feuert wenn die Datei fertig geschrieben wurde
  # -e moved_to: feuert wenn eine neue Datei auf den Pfad verschoben wird (atomarer Write)
  inotifywait -qq -e close_write -e moved_to "$(dirname "$CONFIG")" 2>/dev/null || {
    # inotifywait kann bei Verzeichnis-Löschung/Neuanlage fehlschlagen
    echo "$(date '+%H:%M:%S') [config-watchdog] inotifywait beendet, warte 10s und starte neu..." >> "$LOG"
    sleep 10
    continue
  }

  # Nur reagieren wenn opencode.json wirklich existiert UND sich der Inhalt
  # gegenüber dem letzten bekannten Hash geändert hat.
  if [ ! -f "$CONFIG" ]; then
    continue
  fi
  CURRENT_HASH="$(config_hash)"
  if [ "$CURRENT_HASH" = "$LAST_HASH" ]; then
    continue
  fi
  LAST_HASH="$CURRENT_HASH"

  safe_restart
done
