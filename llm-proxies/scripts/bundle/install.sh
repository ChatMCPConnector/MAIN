#!/usr/bin/env bash
# install.sh: Abhängigkeiten des glm2api-Bundle in einer frischen Umgebung vorbereiten.
# Idempotent. Benötigt: bash, curl (nur falls uv fehlt). Python 3.14 wird von uv gemanagt.
set -euo pipefail
BUNDLE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$BUNDLE_ROOT/app"

UV_BIN="$(command -v uv || echo "$HOME/.local/bin/uv")"
if [ ! -x "$UV_BIN" ]; then
  echo "uv fehlt — installiere..."
  curl -LsSf https://astral.sh/uv/install.sh | sh || { echo "FEHLER: uv-Install gescheitert"; exit 1; }
  UV_BIN="$HOME/.local/bin/uv"
fi

# .env bereitstellen (Port 8001, Guest-Mode; Quelle: glm2api.env im Bundle)
if [ ! -f "$APP_DIR/.env" ] && [ -f "$APP_DIR/glm2api.env" ]; then
  cp "$APP_DIR/glm2api.env" "$APP_DIR/.env"
  echo "    .env installiert (Port 8001, Guest-Mode aktiv)."
fi

mkdir -p "$APP_DIR/log"

(cd "$APP_DIR" && "$UV_BIN" sync) && echo "Fertig. Starten mit: $BUNDLE_ROOT/scripts/start.sh"
