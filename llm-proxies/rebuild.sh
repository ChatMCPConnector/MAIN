#!/usr/bin/env bash
# llm-proxies/rebuild.sh: glm2api-Hauptproxy (chatglm.cn guest-pool) in einem
# frischen Codespace wiederherstellen. Idempotent.
#
#   ./llm-proxies/rebuild.sh          # klonen + patchen
#
# Hintergrund: glm2api hat den 2-Wege-Agenten-Benchmark klar gewonnen
# (2/2 Tasks vollautonom in je 1 Run, 0 Abbrüche) — hellogml (Guest-Token-
# Erschöpfung bei Lang-Runs) und chat2api (Markup-Fragilität) wurden entfernt.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PATCH_DIR="$REPO_ROOT/llm-proxies/patches"
WS="/workspaces"
LOG_DIR="/tmp/opencode"
mkdir -p "$LOG_DIR"

name="glm2api"
url="https://github.com/XxxXTeam/glm2api.git"
dir="$WS/glm2api/repo"
patch="glm2api.patch"

echo "==> [$name]"

# 1) Klon (falls fehlend)
if [ -d "$dir/.git" ]; then
  echo "    Klon vorhanden: $dir"
else
  echo "    Klone $url -> $dir"
  mkdir -p "$(dirname "$dir")"
  git clone --depth 1 "$url" "$dir" 2>&1 | sed 's/^/      /' || { echo "    FEHLER: Klon fehlgeschlagen"; exit 1; }
fi

# 2) Patch anwenden (idempotent)
if [ ! -f "$PATCH_DIR/$patch" ]; then
  echo "    WARN: Patch $patch fehlt — Repo bleibt unpatched"
  exit 0
fi
if git -C "$dir" apply --check --reverse "$PATCH_DIR/$patch" 2>/dev/null; then
  echo "    Bereits gepatcht (OK)"
elif git -C "$dir" apply --check "$PATCH_DIR/$patch" 2>/dev/null; then
  git -C "$dir" apply "$PATCH_DIR/$patch" \
    && echo "    Patch angewendet ($patch)" \
    || { echo "    FEHLER: Patch fehlgeschlagen"; exit 1; }
else
  echo "    WARN: Patch passt nicht auf aktuellen Stand (Upstream geändert?). Manuell:"
  echo "      git -C $dir apply --3way $PATCH_DIR/$patch"
fi

# 3) .env installieren (Port 8001, Guest-Mode, Delete-Conversations aus —
#    secret-frei, liegt im Repo). Vorhandene .env wird nicht überschrieben.
if [ -f "$REPO_ROOT/llm-proxies/glm2api.env" ]; then
  if [ ! -f "$dir/.env" ]; then
    cp "$REPO_ROOT/llm-proxies/glm2api.env" "$dir/.env"
    echo "    .env installiert (Port 8001, Guest-Mode aktiv)."
  else
    echo "    .env vorhanden (bleibt unangetastet)."
  fi
else
  echo "    WARN: llm-proxies/glm2api.env fehlt — Proxy startet mit Defaults (Port 8000, Guest aus!)"
fi

# 4) Python-Runtime + venv via uv (pyproject verlangt Python >=3.14; uv lädt
#    die gemanagte Version + Deps on-demand — hier explizit vorbereiten, damit
#    der spätere Start schnell ist). Fehlendes uv wird installiert.
UV_BIN="$(command -v uv || echo "$HOME/.local/bin/uv")"
if [ ! -x "$UV_BIN" ]; then
  echo "    uv fehlt — installiere..."
  curl -LsSf https://astral.sh/uv/install.sh | sh || { echo "    FEHLER: uv-Install gescheitert"; exit 1; }
  UV_BIN="$HOME/.local/bin/uv"
fi
if [ ! -d "$dir/.venv" ]; then
  (cd "$dir" && "$UV_BIN" sync 2>&1 | tail -2 | sed 's/^/      /') \
    && echo "    Python-venv + Deps via uv sync vorbereitet." \
    || { echo "    FEHLER: uv sync — Proxy startet später trotzdem (uv run lädt on-demand)"; }
else
  echo "    .venv vorhanden."
fi

# 5) start.sh ins /workspaces-Root legen (uv run lädt Deps on-demand)
if [ -f "$REPO_ROOT/llm-proxies/scripts/start-$name.sh" ]; then
  mkdir -p "$WS/$name"
  cp "$REPO_ROOT/llm-proxies/scripts/start-$name.sh" "$WS/$name/start.sh"
  chmod +x "$WS/$name/start.sh"
  echo "==> start.sh für $name aktualisiert"
fi

echo ""
echo "Fertig. Starten mit: /workspaces/glm2api/start.sh  (Log: $LOG_DIR/glm2api.log)"
