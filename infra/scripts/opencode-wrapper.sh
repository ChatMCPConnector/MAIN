#!/usr/bin/env bash
# opencode system wrapper: v1-Aufrufe docken automatisch an den zentralen
# Server (Port 4096) an, damit parallele Terminals sich niemals gegenseitig
# terminieren. v2 wird unveraendert durchgereicht (Managed Service, kein attach).
set -u

REAL_OPENCODE="${OPENCODE_BIN:-/home/vscode/.opencode/bin/opencode-bin}"
SERVER_URL="http://127.0.0.1:4096"
REPO="/workspaces/MAIN"

# v2 hat kein `attach` mehr und startet seinen Managed Service selbst. Der
# Wrapper darf dort nichts umleiten; v1 behaelt den Multi-Client-Pfad unten.
# Das `--version`-Format unterscheidet sich: v1 = "1.18.32", v2 = "opencode v2.1.2".
VERSION_LINE="$("$REAL_OPENCODE" --version 2>/dev/null | head -n 1 || true)"
VERSION_MAJOR="$(printf '%s\n' "$VERSION_LINE" | sed -nE 's/.*v?([0-9]+)\.[0-9]+\..*/\1/p')"
if [ -n "$VERSION_MAJOR" ] && [ "$VERSION_MAJOR" -ge 2 ]; then
  exec "$REAL_OPENCODE" "$@"
fi

# Nicht-TUI Befehle direkt durchreichen
case "${1:-}" in
  serve|attach|models|stats|export|import|completion|agent|upgrade|uninstall|db|mcp|plugin|providers|debug|github|pr|run)
    exec "$REAL_OPENCODE" "$@"
    ;;
esac

# Wenn der zentrale Server auf Port 4096 läuft: sauber per Client-Attach verbinden
if curl -sf -m 2 "$SERVER_URL/" >/dev/null 2>&1; then
  exec "$REAL_OPENCODE" attach "$SERVER_URL" "$@"
fi

# Server läuft noch nicht: versuchen zu starten
if [ -x "$REPO/infra/scripts/opencode-server.sh" ]; then
  "$REPO/infra/scripts/opencode-server.sh" start >/dev/null 2>&1 || true
  if curl -sf -m 3 "$SERVER_URL/" >/dev/null 2>&1; then
    exec "$REAL_OPENCODE" attach "$SERVER_URL" "$@"
  fi
fi

# Fallback auf Standard-Ausführung
exec "$REAL_OPENCODE" "$@"
