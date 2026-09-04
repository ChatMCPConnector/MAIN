#!/usr/bin/env bash
# Landschaft-Setup: läuft automatisch bei jedem neuen Codespace (postCreateCommand).
# Idempotent: kann beliebig oft laufen, überschreibt keine Secrets (auth.json, .env).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> [landscape] Systempakete..."
sudo apt-get update -qq
sudo apt-get install -y -qq curl wget git jq unzip zip nano vim htop tree sqlite3 build-essential python3 python3-pip python3-venv ca-certificates gnupg > /dev/null
sudo rm -rf /var/lib/apt/lists/*

echo "==> [landscape] opencode installieren (falls fehlt)..."
if ! command -v opencode >/dev/null 2>&1 && [ ! -x "$HOME/.opencode/bin/opencode" ]; then
  curl -fsSL https://opencode.ai/install | bash
else
  echo "    opencode schon vorhanden."
fi
export PATH="$HOME/.opencode/bin:$PATH"

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

echo "==> [landscape] tmux einrichten (Mausrad=Bild-auf/runter in TUIs)..."
sudo apt-get install -y -qq tmux >/dev/null 2>&1 || true
mkdir -p "$HOME/.config/tmux"
[ -f "$HOME/.config/tmux/tmux.conf" ] || cp "$REPO_ROOT/dotfiles/tmux.conf" "$HOME/.config/tmux/tmux.conf"
echo "    tmux.conf installiert. TUIs künftig starten mit: tmux opencode"

echo "==> [landscape] Secrets entsperren (falls Bundle + Passphrase da)..."
if [ -f "$REPO_ROOT/config/secrets.enc" ] && [ -n "${LANDSCAPE_PASSPHRASE:-}" ]; then
  bash "$REPO_ROOT/scripts/secrets.sh" unlock >/dev/null 2>&1 && echo "    Secrets automatisch wiederhergestellt." || echo "    WARN: Auto-Unlock fehlgeschlagen (falsche Passphrase?)."
elif [ -f "$REPO_ROOT/config/secrets.enc" ]; then
  echo "    Bundle vorhanden, keine Passphrase. Entsperren mit: ./scripts/secrets.sh unlock"
fi

echo "==> [landscape] .env prüfen..."
if [ ! -f "$REPO_ROOT/.env" ] && [ -f "$REPO_ROOT/.env.example" ]; then
  echo "    HINWEIS: $REPO_ROOT/.env fehlt. Bei Bedarf anlegen: cp .env.example .env"
fi

echo "==> [landscape] Git-Auth verdrahten (für Agent-Push)..."
# Wenn LANDSCAPE_PAT als Codespaces-Secret oder Env gesetzt ist: automatisch einrichten.
# Das ist der Einmal-pro-Account-Schritt, danach kann der Agent immer selbst pushen.
if [ -n "${LANDSCAPE_PAT:-${GITHUB_PAT:-${GH_TOKEN:-}}}" ]; then
  bash "$REPO_ROOT/scripts/auth.sh" setup >/dev/null 2>&1 || echo "    WARN: Auth-Setup fehlgeschlagen."
else
  echo "    kein Token gefunden. Einmalig: ./scripts/auth.sh setup  (oder LANDSCAPE_PAT als Codespaces-Secret setzen)"
fi

echo "==> [landscape] Fertig. Weiter mit: ./scripts/save.sh status"
