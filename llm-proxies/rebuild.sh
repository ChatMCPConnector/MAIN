#!/usr/bin/env bash
# llm-proxies/rebuild.sh: glm2api-Hauptproxy LAUFFÄHIG machen.
# Der Proxy-Code liegt IM REPO (llm-proxies/glm2api/, inkl. aller Patches) —
# kein Klon von GitHub mehr nötig. rebuild.sh macht nur noch: .env bereitstellen
# + Python-venv via uv sync. Idempotent.
#
#   ./llm-proxies/rebuild.sh          # .env + venv vorbereiten
#   ./llm-proxies/rebuild.sh --start  # ... und direkt starten
#
# Hintergrund: glm2api hat den 3-Wege-Agenten-Benchmark klar gewonnen
# (2/2 Tasks vollautonom in je 1 Run, 0 Abbrüche) — hellogml (Guest-Token-
# Erschöpfung bei Lang-Runs) und chat2api (Markup-Fragilität) wurden entfernt.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$REPO_ROOT/llm-proxies/glm2api"
ENV_SRC="$REPO_ROOT/llm-proxies/glm2api.env"

if [ ! -d "$APP_DIR/src" ]; then
  echo "FEHLER: $APP_DIR fehlt (Code muss im Repo liegen)."; exit 1
fi

# 1) .env bereitstellen (Port 8001, Guest-Mode — secret-frei, liegt im Repo
#    als glm2api.env; im App-Verzeichnis heißt sie .env und ist gitignored)
if [ ! -f "$APP_DIR/.env" ] && [ -f "$ENV_SRC" ]; then
  cp "$ENV_SRC" "$APP_DIR/.env"
  echo "    .env installiert (Port 8001, Guest-Mode aktiv)."
elif [ -f "$APP_DIR/.env" ]; then
  echo "    .env vorhanden."
else
  echo "    WARN: $ENV_SRC fehlt — Proxy startet mit Defaults (Port 8000, Guest aus!)"
fi

# 2) Runtime-Artefakte (gitignored)
mkdir -p "$APP_DIR/log"

# 3) Python-Runtime + venv via uv (pyproject verlangt Python >=3.14; uv lädt
#    die gemanagte Version selbst). Fehlendes uv wird installiert.
UV_BIN="$(command -v uv || echo "$HOME/.local/bin/uv")"
if [ ! -x "$UV_BIN" ]; then
  echo "    uv fehlt — installiere..."
  curl -LsSf https://astral.sh/uv/install.sh | sh || { echo "    FEHLER: uv-Install gescheitert"; exit 1; }
  UV_BIN="$HOME/.local/bin/uv"
fi
if [ ! -d "$APP_DIR/.venv" ]; then
  (cd "$APP_DIR" && "$UV_BIN" sync 2>&1 | tail -2 | sed 's/^/      /') \
    && echo "    Python-venv + Deps via uv sync vorbereitet." \
    || { echo "    FEHLER: uv sync"; exit 1; }
else
  echo "    .venv vorhanden."
fi

echo "Fertig. Starten mit: $REPO_ROOT/llm-proxies/scripts/start-glm2api.sh"

# 4) Optional direkt starten
if [ "${1:-}" = "--start" ]; then
  bash "$REPO_ROOT/llm-proxies/scripts/start-glm2api.sh"
fi
