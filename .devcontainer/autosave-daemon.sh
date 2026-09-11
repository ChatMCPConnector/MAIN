#!/usr/bin/env bash
# autosave-daemon.sh: committet und pusht alle offenen Änderungen alle 30 Minuten.
#
# Sichert den Arbeitsstand automatisch, damit bei Codespace-Idle-Shutdown
# nichts verloren geht -- egal welcher Agent gerade parallel arbeitet.
#
# - Nutzt save.sh für die eigentliche Commit+Push-Logik
# - Lockfile verhindert Doppelstart
# - Log unter /tmp/opencode/autosave.log
# - Wird von start-on-boot.sh und setup.sh als Hintergrund-Daemon gestartet
set -u
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK=/tmp/opencode/autosave-daemon.lock
LOG=/tmp/opencode/autosave.log
INTERVAL=1800  # 30 Minuten in Sekunden

mkdir -p /tmp/opencode

# Nur eine Instanz
if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then
  exit 0  # läuft schon
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

echo "$(date '+%Y-%m-%d %H:%M:%S') [autosave] Daemon gestartet (PID $$, Intervall ${INTERVAL}s)" >> "$LOG"

while true; do
  sleep "$INTERVAL"

  # Nur speichern, wenn es tatsächlich uncommittete oder ungepushte Änderungen gibt
  cd "$REPO_ROOT" || continue

  has_changes=0

  # Uncommittete Änderungen (staged + unstaged + untracked)?
  if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null || [ -n "$(git ls-files --others --exclude-standard 2>/dev/null)" ]; then
    has_changes=1
  fi

  # Ungepushte Commits?
  if [ "$has_changes" -eq 0 ]; then
    unpushed="$(git log --oneline origin/main..HEAD 2>/dev/null)"
    if [ -n "$unpushed" ]; then
      has_changes=1
    fi
  fi

  if [ "$has_changes" -eq 0 ]; then
    echo "$(date '+%H:%M:%S') [autosave] Keine Änderungen — übersprungen." >> "$LOG"
    continue
  fi

  echo "$(date '+%H:%M:%S') [autosave] Änderungen erkannt, starte save..." >> "$LOG"

  # save.sh aufrufen (add -A, commit, pull --rebase, push)
  if bash "$REPO_ROOT/infra/scripts/save.sh" "autosave $(date -u +%Y-%m-%dT%H:%MZ)" >> "$LOG" 2>&1; then
    echo "$(date '+%H:%M:%S') [autosave] Erfolgreich gespeichert." >> "$LOG"
  else
    echo "$(date '+%H:%M:%S') [autosave] WARNUNG: save.sh fehlgeschlagen (exit $?)." >> "$LOG"
  fi
done
