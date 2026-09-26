#!/usr/bin/env bash
# gdrive-backup.sh: Repo-Sicherung nach Google Drive als git-bundle (komplette History,
# aller Branches/Refs) — unabhängig von GitHub. Szenario: Account-Bann / Repo-Sperrung.
#
# Rotation (2-Generationen-Schema, immer eine intakte Kopie auf Drive):
#   1. altes MAIN.backup.bundle löschen (remote)
#   2. aktuelles MAIN.bundle -> MAIN.backup.bundle umbenennen (remote move, kein Download nötig)
#   3. frisches Bundle bauen + hochladen als MAIN.bundle
#   4. verifizieren (remote MD5 == lokal MD5)
# Bricht Schritt 3/4 ab, bleibt das Backup aus Schritt 2 intakt stehen.
#
# Wiederherstellung (ohne GitHub):
#   ./infra/scripts/gdrive-backup.sh restore /tmp/opencode/restored
#   -> klont aus MAIN.backup.bundle (Fallback MAIN.bundle) nach /tmp/opencode/restored
#
# Auth: rclone-Remote "gdrive" (Google Drive OAuth, Refresh-Token).
# Config liegt unter ~/.config/rclone/rclone.conf (rclone-Standardpfad; aus
# Secrets-Bundle via secrets.sh). BEWUSST NICHT ~/.config/landscape/ — dort
# werden refresh_tokens von einem Sanitizer aus Dateien entfernt.
#
#   ./infra/scripts/gdrive-backup.sh backup    # Default: sichern
#   ./infra/scripts/gdrive-backup.sh status    # Remote-Stand zeigen
#   ./infra/scripts/gdrive-backup.sh restore [target-dir]
set -uo pipefail
cd "$(dirname "$0")/../.."

readonly RCLONE_CONF="$HOME/.config/rclone/rclone.conf"
readonly REMOTE="gdrive"
readonly REMOTE_DIR="${REMOTE}:MAIN-backup"
readonly CURRENT="${REMOTE_DIR}/MAIN.bundle"     # neueste Sicherung
readonly BACKUP="${REMOTE_DIR}/MAIN.backup.bundle" # vorherige Generation
readonly STATE_FILE=".runtime/gdrive-backup.last"
readonly BUNDLE_LOCAL=".runtime/MAIN.bundle"

# --- Drosselung ---------------------------------------------------------
# Das Bundle enthält die KOMPLETTE Historie (aktuell ~111 MB). Es ändert sich
# bei jedem Commit, also greift ein reiner Inhalts-Vergleich nicht: jeder
# 30-Minuten-Autosave mit Änderungen würde erneut 111 MB hochladen
# (gemessen: ~22 s, ~5 MB/s). Das ist für den Schutzzweck völlig überdimensioniert
# — es geht um Account-Bann/Repo-Löschung, nicht um Sekundentakt.
# Deshalb zeitbasiert drosseln: GitHub-Push bleibt bei jedem Save, das
# Drive-Backup höchstens alle MIN_INTERVAL_MINUTEN.
# Override: GDrive_MIN_INTERVAL_MINUTEN=0 (immer) oder "backup --force".
readonly DEFAULT_MIN_INTERVAL_MINUTES=360   # 6 h
min_interval() {
  local v="${GDrive_MIN_INTERVAL_MINUTES:-$DEFAULT_MIN_INTERVAL_MINUTES}"
  case "$v" in (*[!0-9]*|"") echo "$DEFAULT_MIN_INTERVAL_MINUTES" ;; (*) echo "$v" ;; esac
}

runc() {  # rclone mit Config-Pfad + Fehlertoleranz
  RCLONE_CONFIG="$RCLONE_CONF" rclone "$@"
}

require_auth() {
  if [ ! -f "$RCLONE_CONF" ]; then
    echo "[gdrive] Kein rclone-Conf ($RCLONE_CONF) — Google-Drive-Backup übersprungen."
    echo "[gdrive] Einmalig einrichten: siehe infrastructure.md (gdrive-backup Abschnitt)."
    return 1
  fi
  # Ohne rclone-Binary war "Remote fehlt" die Meldung für zwei verschiedene
  # Fehlerbilder. Erst das Binary prüfen, dann den Remote.
  if ! command -v rclone >/dev/null 2>&1; then
    echo "[gdrive] rclone nicht installiert — Backup übersprungen."
    echo "[gdrive] Installieren: ./infra/scripts/rclone-install.sh"
    return 1
  fi
  rclone listremotes 2>/dev/null | grep -qx "${REMOTE}:" || {
    echo "[gdrive] Remote '${REMOTE}' fehlt in $RCLONE_CONF."
    return 1
  }
}

cmd_backup() {
  local force=0
  [ "${1:-}" = "--force" ] && force=1
  require_auth || exit 0  # save.sh-Hook darf Push nie gefährden
  local head; head="$(git rev-parse HEAD 2>/dev/null)" || { echo "[gdrive] Kein Git-Repo?"; exit 1; }

  # Skip wenn kein neuer Commit seit letztem Backup UND Remote-Stand vorhanden
  if [ "$force" -eq 0 ] && [ -f "$STATE_FILE" ] && [ "$(cat "$STATE_FILE")" = "$head" ]; then
    if runc lsjson "$CURRENT" >/dev/null 2>&1; then
      echo "[gdrive] Kein neuer Commit seit letztem Backup — übersprungen."
      exit 0
    fi
  fi

  # Zeit-Drosselung: nach einem erfolgreichen Backup nicht erneut hochladen,
  # auch wenn Commits dazugekommen sind. GitHub hat sie bereits.
  if [ "$force" -eq 0 ] && [ -f "$STATE_FILE" ]; then
    local last_epoch now elapsed limit remaining
    last_epoch="$(stat -c %Y "$STATE_FILE" 2>/dev/null || echo 0)"
    now="$(date +%s)"
    elapsed=$((now - last_epoch))
    limit=$(( $(min_interval) * 60 ))
    if [ "$limit" -gt 0 ] && [ "$elapsed" -lt "$limit" ]; then
      remaining=$(( (limit - elapsed + 59) / 60 ))
      echo "[gdrive] Drosselung: letztes Backup vor $((elapsed / 60)) min, frühestens in ${remaining} min wieder."
      echo "[gdrive] Erzwingen: ./infra/scripts/gdrive-backup.sh backup --force"
      exit 0
    fi
  fi

  mkdir -p .runtime
  echo "[gdrive] Baue git-bundle (alle Refs + History)..."
  rm -f "$BUNDLE_LOCAL"
  git bundle create "$BUNDLE_LOCAL" --all >/dev/null 2>&1 || { echo "[gdrive] FEHLER: bundle create."; exit 1; }
  git bundle verify "$BUNDLE_LOCAL" >/dev/null 2>&1 || { echo "[gdrive] FEHLER: Bundle invalid."; exit 1; }
  local local_md5; local_md5="$(md5sum "$BUNDLE_LOCAL" | cut -d' ' -f1)"
  echo "[gdrive] Bundle OK: $(du -h "$BUNDLE_LOCAL" | cut -f1), md5 ${local_md5:0:12}…"

  # --- Rotation (remote, Reihenfolge = Sicherheit) ---
  echo "[gdrive] Rotation: altes backup löschen, current -> backup..."
  runc delete "$BACKUP" --ignore-not-found 2>/dev/null
  runc moveto "$CURRENT" "$REMOTE:MAIN-backup/MAIN.backup.bundle" 2>/dev/null \
    || echo "[gdrive] Hinweis: noch kein vorhandenes current (Erst-Backup)."

  echo "[gdrive] Upload $BUNDLE_LOCAL -> $CURRENT..."
  runc copy "$BUNDLE_LOCAL" "$REMOTE_DIR" --drive-chunk-size 32M 2>&1 | grep -v '^$' \
    || { echo "[gdrive] FEHLER: Upload — altes Backup bleibt unberührt."; exit 1; }

  # --- Verifikation: remote MD5 gegen lokal ---
  local remote_md5; remote_md5="$(runc lsjson "$REMOTE_DIR/MAIN.bundle" 2>/dev/null | grep -o '"Hash": *"[a-f0-9]*"' | head -1 | grep -o '[a-f0-9]\{32\}')"
  if [ -n "$remote_md5" ] && [ "$remote_md5" != "$local_md5" ]; then
    echo "[gdrive] FEHLER: MD5-Mismatch nach Upload (remote ${remote_md5:0:12}…). Altes Backup bleibt."
    exit 1
  fi
  echo "$head" > "$STATE_FILE"
  # Restore-Anleitung immer mit auffrischen (überlebt so auch ohne GitHub auf Drive)
  runc copyto infra/docs/RESTORE.md "$REMOTE_DIR/RESTORE.md" 2>/dev/null \
    || echo "[gdrive] Hinweis: RESTORE.md nicht gefunden (infra/docs/RESTORE.md)."
  echo "[gdrive] OK: Drive-Stand = $CURRENT (verifiziert), Backup-Generation = MAIN.backup.bundle"
  rm -f "$BUNDLE_LOCAL"
}

cmd_status() {
  require_auth || exit 1
  echo "[gdrive] Remote: $REMOTE_DIR"
  runc lsl "$REMOTE_DIR" 2>/dev/null || echo "(leer oder kein Zugriff)"
  if [ -f "$STATE_FILE" ]; then
    echo "[gdrive] Letztes Backup von Commit: $(cat "$STATE_FILE")"
    local last_epoch elapsed limit
    last_epoch="$(stat -c %Y "$STATE_FILE" 2>/dev/null || echo 0)"
    elapsed=$(( $(date +%s) - last_epoch ))
    limit=$(( $(min_interval) * 60 ))
    if [ "$limit" -gt 0 ] && [ "$elapsed" -lt "$limit" ]; then
      echo "[gdrive] Drosselung aktiv: vor $((elapsed / 60)) min, kein Upload vor $(( (limit - elapsed + 59) / 60 )) min."
    fi
  fi
}

cmd_restore() {
  require_auth || exit 1
  local target="${1:-/tmp/opencode/MAIN-restored}"
  local dl="/tmp/opencode/MAIN.restore.bundle"
  mkdir -p "$(dirname "$dl")"
  echo "[gdrive] Lade Backup-Generation..."
  runc copyto "$BACKUP" "$dl" 2>/dev/null \
    || runc copyto "$CURRENT" "$dl" 2>/dev/null \
    || { echo "[gdrive] FEHLER: Download."; exit 1; }
  git clone "$dl" "$target" || exit 1
  echo "[gdrive] OK: Repo wiederhergestellt -> $target"
}

case "${1:-backup}" in
  backup)  cmd_backup "${2:-}" ;;
  status)  cmd_status ;;
  restore) shift; cmd_restore "${1:-}" ;;
  *) echo "Usage: $0 {backup [--force]|status|restore [target-dir]}"; exit 1 ;;
esac