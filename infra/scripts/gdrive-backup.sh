#!/usr/bin/env bash
# gdrive-backup.sh: Repo-Sicherung nach Google Drive als git-bundle (komplette History,
# aller Branches/Refs) — unabhängig von GitHub. Szenario: Account-Bann / Repo-Sperrung.
#
# Reihenfolge (fail-safe, 2026-09-26 umgebaut):
#   1. frisches Bundle bauen, als MAIN.new.bundle hochladen und per MD5 verifizieren
#   2. ERST DANN rotieren: MAIN.bundle -> MAIN.backup.bundle, MAIN.new.bundle -> MAIN.bundle
#   3. current nach der Rotation noch einmal verifizieren
# Vorher war es: backup löschen -> current -> backup -> hochladen. Bricht der Move
# ab, ist die letzte Kopie weg — das ist am 2026-09-26 real passiert: MAIN.bundle
# existierte nicht mehr auf Drive, während das Skript "OK (verifiziert)" meldete.
# Zwei Fehler machten das unsichtbar (siehe remote_exists und den Upload-Block).
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
readonly STAGED="${REMOTE_DIR}/MAIN.new.bundle"   # Upload, vor der Rotation verifiziert
readonly STATE_FILE=".runtime/gdrive-backup.last"
readonly BUNDLE_STAGE=".runtime/MAIN.new.bundle"

runc() {  # rclone mit Config-Pfad + Fehlertoleranz
  RCLONE_CONFIG="$RCLONE_CONF" rclone "$@"
}

# ACHTUNG: `rclone lsjson <pfad>` liefert für eine NICHT existierende Datei `[]` mit
# Exit 0. Ein reiner Exit-Code-Check ist damit als Existenznachweis unbrauchbar —
# genau das ließ am 2026-09-26 ein fehlendes MAIN.bundle als "verifiziert" durchgehen.
# `lsjson` ohne --hash liefert außerdem gar kein Hash-Feld, die alte "MD5-Verifikation"
# verglich also meistens nichts. Deshalb: --hash, JSON-Muster statt Exitcode.
#
# ACHTUNG 2: rclone gibt JSON **kompakt** aus ("IsDir":false, kein Leerzeichen).
# Alle Muster hier sind deshalb whitespace-tolerant — ein Muster mit genau einem
# Leerzeichen lieferte am 2026-09-26 ein Falsch-Negativ und meldete einen
# erfolgreichen Rename als fehlgeschlagen.
#
# rclone-Rückgabe ist außerdem unzuverlässig (moveto hat am 2026-09-26 erfolgreich
# gearbeitet und trotzdem nonzero geliefert). Deshalb wird jede Mutation über den
# resultierenden Zustand geprüft, nicht über den Exitcode.
rj() { runc lsjson --hash "$1" 2>/dev/null; }

remote_exists() {
  local j; j="$(rj "$1")" || return 1
  printf '%s' "$j" | grep -q '"IsDir":[[:space:]]*false'
}

remote_size() {
  rj "$1" | grep -o '"Size":[[:space:]]*[0-9]*' | head -1 | grep -o '[0-9]*$'
}

remote_md5() {
  rj "$1" | grep -o '"md5":[[:space:]]*"[a-f0-9]*"' | head -1 | grep -o '[a-f0-9]\{32\}'
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
  require_auth || exit 0  # save.sh-Hook darf Push nie gefährden
  # Lock: der Autosave-Daemon feuert alle 30 Min ungefragt, dazu kommt jeder
  # manuelle 'gdrive backup'. Ohne Lock teilen sich zwei Läufe dieselbe Datei
  # (.runtime/MAIN.new.bundle) — das 'rm -f' am Ende des einen löscht die Datei,
  # die der andere gerade hochlädt. Live passiert am 2026-09-26 17:18:
  # "Failed to calculate src hash: open .runtime/MAIN.bundle: no such file".
  local lock="/tmp/opencode/gdrive-backup.lock"
  mkdir -p "$(dirname "$lock")"
  exec 9>"$lock" || true
  if command -v flock >/dev/null 2>&1; then
    if ! flock -n 9; then
      echo "[gdrive] Ein Backup läuft bereits (Lock $lock) — dieser Lauf übersprungen."
      exit 0
    fi
  fi
  local head force=0
  head="$(git rev-parse HEAD 2>/dev/null)" || { echo "[gdrive] Kein Git-Repo?"; exit 1; }
  [ "${1:-}" = "--force" ] && force=1

  # Skip nur wenn: kein neuer Commit UND beide Generationen wirklich da sind.
  # Nur current zu prüfen hätte nach einer unterbrochenen Rotation verhindert, dass
  # die fehlende Backup-Generation je wiederhergestellt wird (2026-09-26).
  if [ "$force" -eq 0 ] && [ -f "$STATE_FILE" ] && [ "$(cat "$STATE_FILE")" = "$head" ] \
     && remote_exists "$CURRENT" && remote_exists "$BACKUP"; then
    echo "[gdrive] Kein neuer Commit seit letztem Backup — übersprungen."
    exit 0
  fi
  if [ "$force" -eq 1 ]; then echo "[gdrive] --force: Backup unabhängig vom Commit-Stand."; fi

  mkdir -p .runtime
  echo "[gdrive] Baue git-bundle (alle Refs + History)..."
  rm -f "$BUNDLE_STAGE"
  git bundle create "$BUNDLE_STAGE" --all >/dev/null 2>&1 || { echo "[gdrive] FEHLER: bundle create."; exit 1; }
  git bundle verify "$BUNDLE_STAGE" >/dev/null 2>&1 || { echo "[gdrive] FEHLER: Bundle invalid."; exit 1; }
  local local_md5; local_md5="$(md5sum "$BUNDLE_STAGE" | cut -d' ' -f1)"
  echo "[gdrive] Bundle OK: $(du -h "$BUNDLE_STAGE" | cut -f1), md5 ${local_md5:0:12}…"

  # --- 1) Upload als MAIN.new.bundle und verifizieren --------------------------
  # Bewusst VOR der Rotation: die bestehenden Generationen werden erst angefasst,
  # wenn eine geprüfte neue Kopie auf Drive liegt. Bricht der Upload ab, bleibt
  # der alte current unangetastet.
  #
  # Zwei Fallen, die hier jeweils bewusst umgangen sind:
  #  (a) `rclone copy <lokal> <Ziel>` legt bei nicht existierendem Ziel ein
  #      VERZEICHNIS an und schreibt die Datei hinein (MAIN.new.bundle/MAIN.bundle).
  #      Deshalb wird in das Verzeichnis $REMOTE_DIR kopiert, nicht auf einen Dateinamen.
  #  (b) `rclone … | grep` gibt den Exitcode von grep zurück — ein fehlgeschlagener
  #      Upload bliebe unsichtbar. Deshalb Ausgabe in eine Variable, Code separat.
  echo "[gdrive] Upload -> MAIN.new.bundle (verifiziere vor der Rotation)..."
  local up_out up_rc
  up_out="$(runc copy "$BUNDLE_STAGE" "$REMOTE_DIR" --drive-chunk-size 32M 2>&1)"
  up_rc=$?
  printf '%s\n' "$up_out" | grep -v '^$' || true
  if [ "$up_rc" -ne 0 ]; then
    echo "[gdrive] FEHLER: Upload fehlgeschlagen (rclone exit $up_rc) — bestehende Generationen unangetastet."
    exit 1
  fi
  # Endgültige Prüfung: existiert die Datei (nicht das Verzeichnis) und stimmt die
  # Größe? Der Hash wird zusätzlich geprüft, aber mit Toleranz: Drive kann ihn
  # asynchron liefern, und die alte Prüfung hat ihn nie bekommen (kein --hash).
  local local_size; local_size="$(stat -c %s "$BUNDLE_STAGE")"
  local st_size st_md5
  st_size="$(remote_size "$STAGED")"
  st_md5="$(remote_md5 "$STAGED")"
  if [ -z "$st_size" ] || [ "$st_size" != "$local_size" ]; then
    echo "[gdrive] FEHLER: MAIN.new.bundle nicht lesbar oder Größe falsch (remote ${st_size:-'?'} vs lokal $local_size) — bestehende Generationen unangetastet."
    exit 1
  fi
  if [ -n "$st_md5" ] && [ "$st_md5" != "$local_md5" ]; then
    echo "[gdrive] FEHLER: MD5-Mismatch (remote ${st_md5:0:12}… vs lokal ${local_md5:0:12}…) — bestehende Generationen unangetastet."
    runc delete "$STAGED" >/dev/null 2>&1 || true
    exit 1
  fi
  [ -n "$st_md5" ] && echo "[gdrive] Upload verifiziert: Größe $st_size + MD5 ${st_md5:0:12}…"
  [ -z "$st_md5" ] && echo "[gdrive] Upload verifiziert: Größe $st_size (Drive lieferte noch keinen MD5 — nur Größe geprüft)"

  # --- 2) Rotation: erst jetzt die alten Generationen anfassen -----------------
  # Jeder Schritt wird über den Zustand geprüft, nicht über den Exitcode.
  echo "[gdrive] Rotation: backup löschen, current -> backup, new -> current..."
  runc delete "$BACKUP" >/dev/null 2>&1 || true
  if remote_exists "$CURRENT"; then
    runc moveto "$CURRENT" "$BACKUP" >/dev/null 2>&1 || true
    if remote_exists "$BACKUP"; then
      echo "[gdrive]   current -> backup ok"
    else
      echo "[gdrive]   FEHLER: current -> backup nicht bestätigt. MAIN.new.bundle liegt geprüft auf Drive, Current unangetastet — Abbruch."
      exit 1
    fi
  else
    echo "[gdrive]   (kein current vorhanden — erste Generation)"
  fi
  runc moveto "$STAGED" "$CURRENT" >/dev/null 2>&1 || true
  if ! remote_exists "$CURRENT"; then
    echo "[gdrive] FEHLER: new -> current nicht bestätigt. MAIN.new.bundle liegt zur manuellen Rettung auf Drive."
    exit 1
  fi

  # --- 3) Endprüfung: current muss existieren UND zur lokalen Bundle passen -----
  # Fail-closed: ein fehlender current ist ein Fehler, kein Erfolg. Genau dieser
  # Fall wurde vorher als "OK (verifiziert)" gemeldet.
  local final_size final_md5
  final_size="$(remote_size "$CURRENT")"
  final_md5="$(remote_md5 "$CURRENT")"
  if [ -z "$final_size" ] || [ "$final_size" != "$local_size" ]; then
    echo "[gdrive] FEHLER: current nach Rotation nicht lesbar oder Größe falsch (${final_size:-FEHLT} vs $local_size). Backup-Generation steht."
    exit 1
  fi
  if [ -n "$final_md5" ] && [ "$final_md5" != "$local_md5" ]; then
    echo "[gdrive] FEHLER: current-MD5 weicht ab (${final_md5:0:12}… vs ${local_md5:0:12}…). Backup-Generation steht."
    exit 1
  fi
  echo "$head" > "$STATE_FILE"
  # Restore-Anleitung immer mit auffrischen (überlebt so auch ohne GitHub auf Drive)
  runc copyto infra/docs/RESTORE.md "$REMOTE_DIR/RESTORE.md" >/dev/null 2>&1 \
    || echo "[gdrive] Hinweis: RESTORE.md nicht gefunden (infra/docs/RESTORE.md)."
  echo "[gdrive] OK: current verifiziert (${final_size} Bytes${final_md5:+, MD5 ${final_md5:0:12}…}), Backup-Generation = MAIN.backup.bundle"
  rm -f "$BUNDLE_STAGE"
}

cmd_status() {
  require_auth || exit 1
  echo "[gdrive] Remote: $REMOTE_DIR"
  runc lsl "$REMOTE_DIR" 2>/dev/null || echo "(leer oder kein Zugriff)"
  if [ -f "$STATE_FILE" ]; then echo "[gdrive] Letztes Backup von Commit: $(cat "$STATE_FILE")"; fi
  # Fehlende Generationen sichtbar machen — der Status soll den Zustand melden,
  # nicht nur Dateinamen auflisten.
  if remote_exists "$CURRENT"; then
    echo "[gdrive] current: vorhanden ($(remote_size "$CURRENT") Bytes)"
  else
    echo "[gdrive] WARNUNG: current (MAIN.bundle) FEHLT — nur die Backup-Generation steht."
    echo "[gdrive]          Fix: ./infra/scripts/gdrive-backup.sh backup"
  fi
  if remote_exists "$BACKUP"; then
    echo "[gdrive] backup: vorhanden ($(remote_size "$BACKUP") Bytes)"
  else
    echo "[gdrive] WARNUNG: Backup-Generation (MAIN.backup.bundle) FEHLT — nur eine Kopie."
    echo "[gdrive]          Fix: ./infra/scripts/gdrive-backup.sh backup --force"
  fi
  if remote_exists "$STAGED"; then
    echo "[gdrive] WARNUNG: MAIN.new.bundle liegt noch herum (Rotation unterbrochen?) — manuell prüfen."
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
  backup)  shift; cmd_backup "${1:-}" ;;
  status)  cmd_status ;;
  restore) shift; cmd_restore "${1:-}" ;;
  *) echo "Usage: $0 {backup|status|restore [target-dir]}"; exit 1 ;;
esac