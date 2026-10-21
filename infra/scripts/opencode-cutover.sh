#!/usr/bin/env bash
# opencode-cutover.sh: Sicherer Cutover und Rollback zwischen OpenCode v1 und v2.
#
# WICHTIG: Niemals innerhalb einer aktiven OpenCode-Session aufrufen, da das
# Stoppen des v1-Servers (Port 4096) die eigene laufende Sitzung beenden würde.
# In einem normalen VS-Code-Terminal ausfuehren!
#
# Aufruf:
#   ./infra/scripts/opencode-cutover.sh status    # Aktuellen Zustand anzeigen
#   ./infra/scripts/opencode-cutover.sh v2        # Codespace auf v2.1.2 heben
#   ./infra/scripts/opencode-cutover.sh rollback  # Zurueck auf v1.18.32
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DB_PATH="$HOME/.local/share/opencode/opencode.db"
BACKUP_PATH="$HOME/.local/share/opencode/opencode.db.pre-v2-backup"
BIN_DIR="$HOME/.opencode/bin"

is_inside_active_opencode_session() {
  local cur=$$
  while [ "$cur" -gt 1 ]; do
    local cmd
    cmd="$(ps -o args= -p "$cur" 2>/dev/null || true)"
    if echo "$cmd" | grep -qE "opencode(-bin)? (serve|attach)"; then
      return 0
    fi
    cur="$(ps -o ppid= -p "$cur" 2>/dev/null | tr -d ' ' || true)"
    [ -z "$cur" ] && break
  done
  return 1
}

installed_version() {
  local bin="$BIN_DIR/opencode-bin"
  [ -x "$bin" ] || bin="$(command -v opencode 2>/dev/null || true)"
  [ -x "$bin" ] || { echo "nicht installiert"; return 0; }
  "$bin" --version 2>/dev/null | sed -nE 's/.*v?([0-9]+\.[0-9]+\.[0-9]+).*/\1/p' | head -1
}

cmd_status() {
  local cur_v; cur_v="$(installed_version)"
  echo "=== OpenCode Cutover Status ==="
  echo "Installierte Version : ${cur_v:-unbekannt}"
  if ss -tln | grep -q ":4096 "; then
    echo "v1-Server (Port 4096): AKTIV (PID: $(pgrep -f "opencode-bin serve" | tr '\n' ' '))"
  else
    echo "v1-Server (Port 4096): nicht aktiv"
  fi
  if [ -f "$BACKUP_PATH" ]; then
    echo "DB-Sicherung         : VORHANDEN ($(du -h "$BACKUP_PATH" | cut -f1))"
  else
    echo "DB-Sicherung         : FEHLT ($BACKUP_PATH)"
  fi
  if [ -f "$HOME/.config/opencode/cli.json" ]; then
    echo "v2 CLI-Config        : INSTALLIERT (~/.config/opencode/cli.json)"
  else
    echo "v2 CLI-Config        : FEHLT"
  fi
  if is_inside_active_opencode_session; then
    echo "Ausfuehrungsumgebung : WARNUNG — laeuft innerhalb einer aktiven OpenCode-Session!"
  else
    echo "Ausfuehrungsumgebung : OK (separates Terminal)"
  fi
}

cmd_v2() {
  local force="${1:-}"
  if [ "$force" != "--force" ] && is_inside_active_opencode_session; then
    echo "ABBRUCH: Du fuehrst diesen Befehl innerhalb einer aktiven OpenCode-Session aus!" >&2
    echo "Wenn der v1-Server gestoppt wird, bricht diese Session sofort ab." >&2
    echo "Bitte oeffne ein normales VS-Code-Terminal (nicht opencode) und fuehre aus:" >&2
    echo "  ./infra/scripts/opencode-cutover.sh v2" >&2
    echo "(Oder mit --force erzwingen, falls du den Session-Abbruch bewusst in Kauf nimmst)" >&2
    exit 1
  fi

  echo "==> 1. Aktive Datenbank sichern..."
  if [ -f "$DB_PATH" ]; then
    mkdir -p "$(dirname "$BACKUP_PATH")"
    sqlite3 "$DB_PATH" ".backup '$BACKUP_PATH'"
    echo "    Sicherung erstellt: $BACKUP_PATH ($(du -h "$BACKUP_PATH" | cut -f1))"
  else
    echo "    Keine opencode.db vorhanden — ueberspringe Sicherung."
  fi

  echo "==> 2. v1-Server auf Port 4096 stoppen..."
  bash "$REPO_ROOT/infra/scripts/opencode-server.sh" stop || true

  echo "==> 3. OpenCode v2.1.2 installieren..."
  curl -fsSL https://opencode.ai/v2/install | bash -s -- --version 2.1.2

  echo "==> 4. Multi-Client Wrapper aktivieren..."
  if [ -f "$BIN_DIR/opencode" ] && [ ! -f "$BIN_DIR/opencode-bin" ]; then
    mv "$BIN_DIR/opencode" "$BIN_DIR/opencode-bin"
  elif [ -f "$BIN_DIR/opencode" ]; then
    # Existiert beides, Installer ueberschreibt `opencode` mit neuem Binary
    mv "$BIN_DIR/opencode" "$BIN_DIR/opencode-bin"
  fi
  cp "$REPO_ROOT/infra/scripts/opencode-wrapper.sh" "$BIN_DIR/opencode"
  chmod +x "$BIN_DIR/opencode"

  echo "==> 5. v2 CLI-Config installieren..."
  mkdir -p "$HOME/.config/opencode"
  install -m 644 "$REPO_ROOT/config/opencode-cli.json" "$HOME/.config/opencode/cli.json"

  echo "==> 6. Verifikation..."
  local new_v; new_v="$(installed_version)"
  echo "    Installiert: $new_v"
  if [ "$new_v" != "2.1.2" ]; then
    echo "    FEHLER: Erwartet 2.1.2, gefunden $new_v" >&2
    exit 1
  fi

  echo ""
  echo "ERFOLG: OpenCode v2.1.2 ist aktiv."
  echo "Starte die TUI jetzt einfach mit 'opencode'."
}

cmd_rollback() {
  echo "==> 1. v1.18.32 installieren..."
  curl -fsSL https://opencode.ai/install | bash -s -- --version 1.18.32
  if [ -f "$BIN_DIR/opencode" ]; then
    mv "$BIN_DIR/opencode" "$BIN_DIR/opencode-bin"
  fi
  cp "$REPO_ROOT/infra/scripts/opencode-wrapper.sh" "$BIN_DIR/opencode"
  chmod +x "$BIN_DIR/opencode"

  echo "==> 2. v1-Server auf Port 4096 starten..."
  bash "$REPO_ROOT/infra/scripts/opencode-server.sh" start

  echo "==> 3. Verifikation..."
  local new_v; new_v="$(installed_version)"
  echo "    Installiert: $new_v"
  curl -fsS -m 5 http://127.0.0.1:4096/ >/dev/null && echo "    Port 4096 antwortet OK."

  echo ""
  echo "ROLLBACK ABGESCHLOSSEN: OpenCode v1.18.32 laeuft wieder."
}

case "${1:-status}" in
  status)   cmd_status ;;
  v2)       shift; cmd_v2 "$@" ;;
  rollback) cmd_rollback ;;
  *)
    echo "Usage: $0 {status|v2|rollback}"
    exit 1
    ;;
esac
