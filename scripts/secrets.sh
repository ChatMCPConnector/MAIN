#!/usr/bin/env bash
# secrets.sh: deine Secrets (PAT, opencode-Login, .env) verschlüsselt im Git mitschleppen.
# Sinn: beide Accounts sind deine -> ein Bundle, eine Passphrase, null Aufwand pro Codespace.
# Sicherheit: Repo ist PUBLIC -> die Datei config/secrets.enc kann jeder sehen, aber ohne
# deine Passphrase ist sie nutzlos. Starke, einmalige Passphrase wählen. Bei Verdacht: PAT
# auf GitHub revoken, .env-Keys rotieren, neu locken.
#
#   ./scripts/secrets.sh lock     # packt ein (Passphrase-Abfrage, unsichtbar). DANACH sagst du dem Agent "push".
#   ./scripts/secrets.sh unlock   # packt aus (automatisch wenn LANDSCAPE_PASSPHRASE gesetzt, sonst Abfrage)
#   ./scripts/secrets.sh status   # zeigt was drin ist (ohne Passphrase, ohne Inhalte)
#
# Vollautomatisch: LANDSCAPE_PASSPHRASE als Codespaces-Secret pro Account hinterlegen ->
# jeder neue Codespace entsperrt sich beim Start von selbst (siehe setup.sh).
# WICHTIG: Die Passphrase tippst DU im Terminal ein. Nie in den Chat schreiben.
set -euo pipefail
cd "$(dirname "$0")/.."
BUNDLE="config/secrets.enc"
MANIFEST="config/secrets.manifest"

get_passphrase() {
  if [ -n "${LANDSCAPE_PASSPHRASE:-}" ]; then return 0; fi
  read -rsp "Secrets-Passphrase: " LANDSCAPE_PASSPHRASE
  echo ""
  [ -n "${LANDSCAPE_PASSPHRASE:-}" ] || { echo "Abgebrochen: keine Passphrase."; exit 1; }
  export LANDSCAPE_PASSPHRASE
}

cmd_lock() {
  local stage; stage="$(mktemp -d)"
  trap "rm -rf '$stage'" EXIT
  local found=0
  mkdir -p "$stage/files"
  [ -f "$HOME/.config/landscape/pat" ] && { cp "$HOME/.config/landscape/pat" "$stage/files/pat"; found=1; }
  [ -f "$HOME/.local/share/opencode/auth.json" ] && { cp "$HOME/.local/share/opencode/auth.json" "$stage/files/opencode-auth.json"; found=1; }
  [ -f ".env" ] && { cp ".env" "$stage/files/env"; found=1; }
  [ "$found" -eq 1 ] || { echo "Nichts zu sichern (kein PAT, kein opencode-Login, kein .env)."; exit 1; }
  get_passphrase
  tar -czf "$stage/bundle.tgz" -C "$stage/files" .
  openssl enc -aes-256-cbc -pbkdf2 -pass env:LANDSCAPE_PASSPHRASE -in "$stage/bundle.tgz" -out "$BUNDLE"
  tar -tzf "$stage/bundle.tgz" | sort > "$MANIFEST"
  unset LANDSCAPE_PASSPHRASE
  echo "Verschlüsselt -> $BUNDLE"
  cat "$MANIFEST"
  echo "Fertig. Sag dem Agent 'push', damit es ins Git kommt."
}

cmd_unlock() {
  [ -f "$BUNDLE" ] || { echo "Kein Bundle ($BUNDLE fehlt)."; exit 1; }
  local noninteractive=0
  [ -n "${LANDSCAPE_PASSPHRASE:-}" ] && noninteractive=1
  get_passphrase
  local stage; stage="$(mktemp -d)"
  trap "rm -rf '$stage'" EXIT
  if ! openssl enc -d -aes-256-cbc -pbkdf2 -pass env:LANDSCAPE_PASSPHRASE -in "$BUNDLE" -out "$stage/bundle.tgz" 2>/dev/null; then
    unset LANDSCAPE_PASSPHRASE
    echo "FEHLER: falsche Passphrase oder Bundle kaputt."
    exit 1
  fi
  mkdir -p "$stage/files" && tar -xzf "$stage/bundle.tgz" -C "$stage/files"
  # Bestehendes nie überschreiben (lokale Secrets behalten Vorrang)
  if [ -f "$stage/files/pat" ] && [ ! -f "$HOME/.config/landscape/pat" ]; then
    mkdir -p "$HOME/.config/landscape" && cp "$stage/files/pat" "$HOME/.config/landscape/pat" && chmod 600 "$HOME/.config/landscape/pat"
    ./scripts/auth.sh setup "$(cat "$HOME/.config/landscape/pat")" >/dev/null 2>&1 || true
    echo "    PAT wiederhergestellt + Git/gh verdrahtet."
  fi
  if [ -f "$stage/files/opencode-auth.json" ] && [ ! -f "$HOME/.local/share/opencode/auth.json" ]; then
    mkdir -p "$HOME/.local/share/opencode" && cp "$stage/files/opencode-auth.json" "$HOME/.local/share/opencode/auth.json" && chmod 600 "$HOME/.local/share/opencode/auth.json"
    echo "    opencode-Login wiederhergestellt."
  fi
  if [ -f "$stage/files/env" ] && [ ! -f ".env" ]; then
    cp "$stage/files/env" ".env" && chmod 600 ".env"
    echo "    .env wiederhergestellt."
  fi
  [ "$noninteractive" -eq 0 ] && unset LANDSCAPE_PASSPHRASE
  echo "Unlock fertig."
}

cmd_status() {
  if [ -f "$BUNDLE" ]; then
    echo "Bundle: $BUNDLE ($(wc -c < "$BUNDLE" | tr -d ' ') Bytes, verschlüsselt)"
    [ -f "$MANIFEST" ] && { echo "Inhalt:"; sed 's/^/  /' "$MANIFEST"; }
  else
    echo "Kein Bundle vorhanden. Mit './scripts/secrets.sh lock' erstellen."
  fi
}

case "${1:-status}" in
  lock) cmd_lock ;;
  unlock) cmd_unlock ;;
  status) cmd_status ;;
  *) echo "Usage: $0 {lock|unlock|status}"; exit 1 ;;
esac
