#!/usr/bin/env bash
# freebuff-install.sh: installiert die Freebuff CLI (werbefinanzierter, kostenloser
# Coding-Agent von CodebuffAI) unter /workspaces/freebuff.
#
# Warum nicht `npm i -g freebuff`: der Nutzer wollte die Installation unter
# /workspaces, also liegt das komplette npm-Projekt in /workspaces/freebuff und
# ~/.local/bin/freebuff ist nur ein dünner Wrapper darauf. /workspaces ist
# persistent, ~/.config/manicode (das native 130-MB-Binary, vom Launcher selbst
# dorthin geladen) ist es nicht — deshalb wird das Binary zusätzlich unter
# /workspaces/freebuff/bin gecacht, damit ein Codespace-Rebuild es nicht neu
# lädt. Ein Aufruf von `freebuff` stellt den Cache dann wieder her.
#
# Kanonisch: FREEBUFF_VERSION unten pinnen + dieses Skript ist der einzige Weg.
# setup.sh ruft es bei jedem neuen Codespace automatisch auf.
set -euo pipefail

readonly FREEBUFF_VERSION="0.0.203"
readonly APP_DIR="/workspaces/freebuff"
readonly BIN_DIR="${APP_DIR}/bin"
readonly WRAPPER="$HOME/.local/bin/freebuff"
readonly NATIVE_DIR="$HOME/.config/manicode"

# Bereits installiert? (Wrapper + npm-Paket mit gepinnter Version)
if [ -x "$WRAPPER" ] && [ -f "${APP_DIR}/node_modules/freebuff/package.json" ] \
   && grep -q "\"version\": \"${FREEBUFF_VERSION}\"" "${APP_DIR}/node_modules/freebuff/package.json" 2>/dev/null; then
  echo "[freebuff] v${FREEBUFF_VERSION} bereits installiert (${APP_DIR}), Wrapper: ${WRAPPER}"
  exit 0
fi

echo "[freebuff] Installiere v${FREEBUFF_VERSION} nach ${APP_DIR}..."
mkdir -p "$APP_DIR" "$BIN_DIR"
if [ ! -f "${APP_DIR}/package.json" ]; then
  (cd "$APP_DIR" && npm init -y >/dev/null)
fi
(cd "$APP_DIR" && npm install --no-audit --no-fund --loglevel=error "freebuff@${FREEBUFF_VERSION}")

# Wrapper: stellt das native Binary aus dem /workspaces-Cache wieder her, damit
# kein 130-MB-Download pro Container nötig ist, und startet dann den Launcher.
mkdir -p "$HOME/.local/bin"
cat > "$WRAPPER" <<'WRAPPER_EOF'
#!/usr/bin/env bash
# Wird von infra/scripts/freebuff-install.sh erzeugt — nicht editieren.
set -euo pipefail
app_dir="/workspaces/freebuff"
native_dir="$HOME/.config/manicode"
mkdir -p "$native_dir"
if [ ! -x "${native_dir}/freebuff" ] && [ -x "${app_dir}/bin/freebuff" ]; then
  cp -f "${app_dir}/bin/freebuff" "${native_dir}/freebuff"
  [ -f "${app_dir}/bin/tree-sitter.wasm" ] && cp -f "${app_dir}/bin/tree-sitter.wasm" "${native_dir}/tree-sitter.wasm"
  [ -f "${app_dir}/bin/freebuff-metadata.json" ] && cp -f "${app_dir}/bin/freebuff-metadata.json" "${native_dir}/freebuff-metadata.json"
fi
exec node "${app_dir}/node_modules/freebuff/index.js" "$@"
WRAPPER_EOF
chmod +x "$WRAPPER"

# Erststart holt das native Binary nach ~/.config/manicode — einmalig hier
# auslösen und dann nach /workspaces cachen (ReBUILD-fest).
if [ ! -x "${NATIVE_DIR}/freebuff" ]; then
  echo "[freebuff] Lade natives Binary (einmalig, ~130 MB)..."
  "$WRAPPER" --version >/dev/null 2>&1 || true
fi
for f in freebuff tree-sitter.wasm freebuff-metadata.json; do
  [ -f "${native_dir}/${f}" ] && cp -f "${native_dir}/${f}" "${BIN_DIR}/${f}" || true
done

echo "[freebuff] OK: $(cd "$APP_DIR" && node -e "process.stdout.write(require('./node_modules/freebuff/package.json').version)")"
echo "[freebuff] Start: cd <projekt> && freebuff   (erstmalig Account-Login nötig)"
