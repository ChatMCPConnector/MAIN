#!/usr/bin/env bash
# Landschaft-Setup: läuft automatisch bei jedem neuen Codespace (postCreateCommand).
# Idempotent: kann beliebig oft laufen, überschreibt keine Secrets (auth.json, .env).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> [landscape] Systempakete..."
sudo apt-get update -qq
sudo apt-get install -y -qq curl wget git jq unzip zip nano vim htop tree sqlite3 build-essential python3 python3-pip python3-venv ca-certificates gnupg nodejs npm xvfb x11vnc novnc websockify > /dev/null
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
      echo "$MARKER (nicht editieren, Quelle: $REPO_ROOT/infra/scripts/aliases.sh)"
      echo "[ -f \"$REPO_ROOT/infra/scripts/aliases.sh\" ] && source \"$REPO_ROOT/infra/scripts/aliases.sh\""
    } >> "$rc"
    echo "    verlinkt in $rc"
  fi
done

echo "==> [landscape] Secrets entsperren (falls Bundle + Passphrase da)..."
if [ -f "$REPO_ROOT/config/secrets.enc" ] && { [ -n "${LANDSCAPE_PASSPHRASE:-}" ] || [ -f "$REPO_ROOT/config/passphrase" ]; }; then
  bash "$REPO_ROOT/infr./infra/scripts/secrets.sh" unlock >/dev/null 2>&1 && echo "    Secrets automatisch wiederhergestellt." || echo "    WARN: Auto-Unlock fehlgeschlagen (falsche Passphrase?)."
elif [ -f "$REPO_ROOT/config/secrets.enc" ]; then
  echo "    Bundle vorhanden, keine Passphrase. Entsperren mit: ./infra/scripts/secrets.sh unlock"
fi

echo "==> [landscape] .env prüfen..."
if [ ! -f "$REPO_ROOT/.env" ] && [ -f "$REPO_ROOT/.env.example" ]; then
  echo "    HINWEIS: $REPO_ROOT/.env fehlt. Bei Bedarf anlegen: cp .env.example .env"
fi

echo "==> [landscape] Git-Auth verdrahten (für Agent-Push)..."
# Wenn LANDSCAPE_PAT als Codespaces-Secret oder Env gesetzt ist: automatisch einrichten.
# Das ist der Einmal-pro-Account-Schritt, danach kann der Agent immer selbst pushen.
if [ -n "${LANDSCAPE_PAT:-${GITHUB_PAT:-${GH_TOKEN:-}}}" ]; then
  bash "$REPO_ROOT/infr./infra/scripts/auth.sh" setup >/dev/null 2>&1 || echo "    WARN: Auth-Setup fehlgeschlagen."
else
  echo "    kein Token gefunden. Einmalig: ./infra/scripts/auth.sh setup  (oder LANDSCAPE_PAT als Codespaces-Secret setzen)"
fi

echo "==> [landscape] Browser-Runtime prüfen..."
if [ -f "$REPO_ROOT/infra/browser/package.json" ] && [ ! -d "$REPO_ROOT/.runtime/ms-playwright" ]; then
  if command -v npm >/dev/null 2>&1; then
    bash "$REPO_ROOT/infr./infra/scripts/browser-install.sh" >/dev/null 2>&1 \
      && echo "    Chromium-Runtime installiert." \
      || echo "    WARN: Browser-Install fehlgeschlagen, manuell: ./infra/scripts/browser-install.sh"
  else
    echo "    SKIP: npm fehlt, manuell nachholen: ./infra/scripts/browser-install.sh"
  fi
else
  echo "    Browser-Runtime vorhanden."
fi

echo "==> [landscape] Sessions-MCP prüfen (opencode-sessions)..."
# MCP-Server für Session-Verwaltung; DB-Pfad ist pro Codespace identisch (~/.local/share/opencode/opencode.db).
# Falls das Repo nicht unter /workspaces/MAIN liegt, passt setup.sh den Pfad in der opencode-Config an.
if [ -f "$REPO_ROOT/infra/mcp/opencode-sessions-mcp.js" ]; then
  NODE_BIN="$(command -v node || true)"
  MCP_LINE="  \"mcp\": {\"opencode-sessions\": {\"type\": \"local\", \"command\": [\"${NODE_BIN:-node}\", \"$REPO_ROOT/infra/mcp/opencode-sessions-mcp.js\"], \"enabled\": true, \"environment\": {}}},"
  for CFG in "$REPO_ROOT/.opencode/opencode.json" "$HOME/.config/opencode/opencode.json"; do
    mkdir -p "$(dirname "$CFG")"
    if [ ! -f "$CFG" ]; then
      printf '{\n  "$schema": "https://opencode.ai/config.json",\n%s\n  "permission": "allow"\n}\n' "$MCP_LINE" > "$CFG"
    elif ! grep -q '"opencode-sessions"' "$CFG"; then
      python3 - "$CFG" "$MCP_LINE" <<'PYEOF' 2>/dev/null || sed -i '1a\
'"$MCP_LINE" "$CFG"
import json, sys
cfg_path, mcp_line = sys.argv[1], sys.argv[2]
with open(cfg_path) as f:
    first = f.readline()
    rest = f.read()
with open(cfg_path, "w") as f:
    f.write(first + mcp_line + "\n" + rest)
PYEOF
    fi
  done
  echo "    opencode-sessions MCP registriert (in opencode-Config)."
else
  echo "    SKIP: infra/mcp/opencode-sessions-mcp.js fehlt."
fi

echo "==> [landscape] Proxies + Benchmark (flüchtige Anteile)..."
# Die GLM-Proxy-Klones (/workspaces/{glm2api,hellogml,chat2api}) und das
# ChaosShop-Benchmark (/workspaces/benchmark) sind NICHT im Codespace-Volume
# persistent. Patches + Startskripte + Templates liegen hier im Repo.
# Rebuild nur auf Wunsch (dauert Minuten wegen Klones/Builds):
if [ "${LANDSCAPE_REBUILD_LLM_PROXIES:-}" = "1" ]; then
  bash "$REPO_ROOT/llm-proxies/rebuild.sh" && echo "    Proxies rekonstruiert."
else
  echo "    SKIP: Rebuild optional. Bei Bedarf: ./llm-proxies/rebuild.sh  (oder LANDSCAPE_REBUILD_LLM_PROXIES=1)"
fi
if [ -d "$REPO_ROOT/work/benchmark/template" ] && [ ! -d /workspaces/benchmark ]; then
  bash "$REPO_ROOT/work/benchmark/rebuild.sh" >/dev/null 2>&1 \
    && echo "    Benchmark-Kopien aus Template wiederhergestellt." \
    || echo "    WARN: Benchmark-Rebuild fehlgeschlagen, manuell: ./work/benchmark/rebuild.sh"
fi

echo "==> [landscape] Fertig. Weiter mit: ./infra/scripts/save.sh status"
