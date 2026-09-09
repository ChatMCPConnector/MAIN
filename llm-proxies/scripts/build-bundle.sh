#!/usr/bin/env bash
# build-bundle.sh: glm2api-Bundle (Zip) bauen — reproduzierbar aus llm-proxies/.
#
#   ./llm-proxies/scripts/build-bundle.sh          # baut glm2api-bundle.zip nach llm-proxies/dist/
#
# Quelle des Bundles: llm-proxies/glm2api (Code, kanonischer Source — kein
# Patch-Artefakt mehr), llm-proxies/glm2api.env (Config),
# work/docs/reverse-engineering (Doku). Kein Klon, keine externen Quellen.
#
# Determinismus (N-2): alle gestagten Dateien bekommen einen festen Zeitstempel
# (SOURCE_DATE_EPOCH oder Default 0), damit inhaltlich identische Builds
# byte-identische ZIPs liefern (zusammen mit zip -X).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_DIR="$REPO_ROOT/llm-proxies/glm2api"
ENV_SRC="$REPO_ROOT/llm-proxies/glm2api.env"
DIST="$REPO_ROOT/llm-proxies/dist"
STAGE="$DIST/glm2api-bundle"
ZIP="$DIST/glm2api-bundle.zip"

[ -d "$APP_DIR/src" ] || { echo "FEHLER: $APP_DIR fehlt."; exit 1; }
[ -f "$ENV_SRC" ] || { echo "FEHLER: $ENV_SRC fehlt."; exit 1; }

# 1) Stage frisch aufbauen
rm -rf "$STAGE"
mkdir -p "$STAGE/app" "$STAGE/scripts" "$STAGE/docs"

# 2) App-Code (nur Source, keine Runtime-Artefakte); tests/ komplett via cp -r
cp -r "$APP_DIR/src" "$APP_DIR/tests" "$STAGE/app/"
find "$STAGE" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find "$STAGE" -name '*.egg-info' -type d -exec rm -rf {} + 2>/dev/null || true
find "$STAGE" -name '.pytest_cache' -type d -exec rm -rf {} + 2>/dev/null || true
for f in main.py pyproject.toml uv.lock README.md structure.md LICENSE .env.example .python-version .gitignore; do
  cp "$APP_DIR/$f" "$STAGE/app/"
done
cp "$ENV_SRC" "$STAGE/app/glm2api.env"

# 3) Skripte (portable Versionen mit relativen Pfaden)
cp "$REPO_ROOT/llm-proxies/scripts/bundle/install.sh" "$STAGE/scripts/"
cp "$REPO_ROOT/llm-proxies/scripts/bundle/start.sh" "$STAGE/scripts/"

# 4) Doku
cp "$REPO_ROOT/work/docs/reverse-engineering/chatglm-reasoning-modes.md" "$STAGE/docs/" 2>/dev/null || true
cp "$REPO_ROOT/llm-proxies/scripts/bundle/README.md" "$STAGE/README.md"

chmod +x "$STAGE/scripts/"*.sh

# 5) Deterministisch: feste Zeitstempel auf alle Stage-Einträge (N-2), dann Zip
EPOCH="${SOURCE_DATE_EPOCH:-0}"
find "$STAGE" -exec touch -d "@$EPOCH" {} +
rm -f "$ZIP"
(cd "$DIST" && zip -r -X -q glm2api-bundle.zip glm2api-bundle)

echo "Fertig: $ZIP"
unzip -l "$ZIP" | tail -3
