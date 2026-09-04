#!/usr/bin/env bash
# Landschaft-Setup: läuft automatisch bei jedem neuen Codespace (postCreateCommand).
# Idempotent: kann beliebig oft laufen, überschreibt keine Secrets (auth.json, .env).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> [landscape] Systempakete..."
sudo apt-get update -qq
sudo apt-get install -y -qq curl wget git jq unzip zip nano vim htop tree build-essential python3 python3-pip python3-venv ca-certificates gnupg > /dev/null
sudo rm -rf /var/lib/apt/lists/*

echo "==> [landscape] opencode installieren (falls fehlt)..."
if ! command -v opencode >/dev/null 2>&1 && [ ! -x "$HOME/.opencode/bin/opencode" ]; then
  curl -fsSL https://opencode.ai/install | bash
else
  echo "    opencode schon vorhanden."
fi
export PATH="$HOME/.opencode/bin:$PATH"

echo "==> [landscape] opencode-Config wiederherstellen (ohne Secrets zu überschreiben)..."
mkdir -p "$HOME/.config/opencode/commands" "$HOME/.config/opencode/plugins"
# opencode.json nur kopieren wenn noch keine existiert (lokale Änderungen behalten Vorrang)
if [ ! -f "$HOME/.config/opencode/opencode.json" ] && [ -f "$REPO_ROOT/config/opencode/opencode.json" ]; then
  cp "$REPO_ROOT/config/opencode/opencode.json" "$HOME/.config/opencode/opencode.json"
  echo "    opencode.json wiederhergestellt."
fi
# Plugins & Commands: fehlende Dateien ergänzen, existierende nicht anfassen
for f in "$REPO_ROOT"/config/opencode/plugins/*; do
  [ -e "$f" ] || continue
  bn="$(basename "$f")"
  [ -f "$HOME/.config/opencode/plugins/$bn" ] || cp "$f" "$HOME/.config/opencode/plugins/$bn"
done
for f in "$REPO_ROOT"/config/opencode/commands/*; do
  [ -e "$f" ] || continue
  bn="$(basename "$f")"
  [ -f "$HOME/.config/opencode/commands/$bn" ] || cp "$f" "$HOME/.config/opencode/commands/$bn"
done

echo "==> [landscape] Shell-Aliase verlinken..."
MARKER="# MAIN-landscape"
for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
  [ -f "$rc" ] || touch "$rc"
  if ! grep -qF "$MARKER" "$rc" 2>/dev/null; then
    {
      echo ""
      echo "$MARKER (nicht editieren, Quelle: $REPO_ROOT/dotfiles/aliases.sh)"
      echo "[ -f \"$REPO_ROOT/dotfiles/aliases.sh\" ] && source \"$REPO_ROOT/dotfiles/aliases.sh\""
    } >> "$rc"
    echo "    verlinkt in $rc"
  fi
done

echo "==> [landscape] Git-Auth verdrahten (für Agent-Push)..."
# Wenn LANDSCAPE_PAT als Codespaces-Secret oder Env gesetzt ist: automatisch einrichten.
# Das ist der Einmal-pro-Account-Schritt, danach kann der Agent immer selbst pushen.
if [ -n "${LANDSCAPE_PAT:-${GITHUB_PAT:-${GH_TOKEN:-}}}" ]; then
  bash "$REPO_ROOT/scripts/auth.sh" setup >/dev/null 2>&1 || echo "    WARN: Auth-Setup fehlgeschlagen."
else
  echo "    kein Token gefunden. Einmalig: ./scripts/auth.sh setup  (oder LANDSCAPE_PAT als Codespaces-Secret setzen)"
fi

echo "==> [landscape] .env prüfen..."
if [ ! -f "$REPO_ROOT/.env" ] && [ -f "$REPO_ROOT/.env.example" ]; then
  echo "    HINWEIS: $REPO_ROOT/.env fehlt. Bei Bedarf anlegen: cp .env.example .env"
fi

echo "==> [landscape] Fertig. Weiter mit: ./scripts/save.sh status"
