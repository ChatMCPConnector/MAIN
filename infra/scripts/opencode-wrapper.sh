#!/usr/bin/env bash
# opencode system wrapper: sorgt dafür, dass jeder Aufruf automatisch
# an den zentralen opencode-Server (Port 4096) andockt.
# Dadurch terminieren sich parallele Terminals NIEMALS gegenseitig.
set -u

REAL_OPENCODE="/home/vscode/.opencode/bin/opencode-bin"
SERVER_URL="http://127.0.0.1:4096"
REPO="/workspaces/MAIN"

# Letzte Verteidigungslinie: fehlt eine per {file:...} referenzierte Key-Datei,
# startet opencode nicht ("Configuration is invalid ... bad file reference").
# ensure ist idempotent und nur ein paar Dateitests — billig genug für jeden Aufruf.
KEYS="$REPO/infra/scripts/keys.sh"
if [ -x "$KEYS" ]; then
  bash "$KEYS" ensure --quiet >/dev/null 2>&1 || true
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
