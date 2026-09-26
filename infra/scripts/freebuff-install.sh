#!/usr/bin/env bash
# freebuff-install.sh: Installiert die Freebuff CLI (werbefinanzierter, kostenloser
# Coding-Agent von CodebuffAI) als npm-Projekt nach /workspaces/freebuff.
# Kanonisch: FREEBUFF_VERSION unten pinnen + dieses Skript ist der einzige Weg.
# setup.sh ruft es bei jedem neuen Codespace automatisch auf (idempotent).
#
# Warum nicht `npm i -g freebuff`:
#  1. gewuenscht ist eine Installation unter /workspaces, nicht global.
#  2. Der npm-Launcher legt sein natives Binary (136 MB) HART nach
#     ~/.config/manicode/freebuff (launcher.js:
#     path.join(os.homedir(), '.config', 'manicode') — kein Env-Override).
#     $HOME ist im Codespace ephemer: nach jedem Rebuild laedt der Launcher das
#     Binary neu (48 MB Download, ~30 s, sichtbarer Progress-Output).
#     Loesung: Binary zusaetzlich nach /workspaces/freebuff/bin/ cachen
#     (persistent, ueberlebt Rebuilds); der Wrapper ~/.local/bin/freebuff
#     kopiert es bei Bedarf zurueck, bevor er den Launcher startet. Ohne Cache
#     ~30 s, mit Cache 4-9 s bis `freebuff --version` (live gemessen).
#     Es muessen ALLE drei Dateien mit: freebuff, tree-sitter.wasm (Sprachparser
#     laeuft sonst kaputt) und freebuff-metadata.json (Versionspruefung).
#
# Login: kommt NICHT von hier. ~/.config/manicode/credentials.json wird ueber
# infra/scripts/secrets.sh aus config/secrets.enc wiederhergestellt — deshalb
# steht der Aufruf in setup.sh bewusst NACH dem Secrets-Schritt.
# Ist dort kein Login hinterlegt: `freebuff login` (Browser-URL, geht nicht headless).
set -euo pipefail

# Der npm-Launcher laedt beim Start das NEUESTE veroeffentlichte native Binary
# selbst nach (live belegt: npm-Pin 0.0.203, Launcher zog 0.0.204) und legt
# dabei `.freebuff-<version>-*.tar.gz.part` + `.freebuff-download-temp-*` in
# $NATIVE_DIR ab. Beides wird hier aufgeraeumt, sonst fressen die Reste bei
# jedem Codespace-Neustart Platte.
FREEBUFF_VERSION="0.0.204"
readonly APP_DIR="/workspaces/freebuff"
readonly BIN_DIR="${APP_DIR}/bin"
readonly WRAPPER="$HOME/.local/bin/freebuff"
readonly NATIVE_DIR="$HOME/.config/manicode"

installed_version() {
  [ -f "${APP_DIR}/node_modules/freebuff/package.json" ] || return 1
  sed -nE 's/.*"version"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' \
    "${APP_DIR}/node_modules/freebuff/package.json" | head -1
}

# --- Binaries, die der Launcher in die Native-Dir erwartet ---------------------
NATIVE_FILES=(freebuff tree-sitter.wasm freebuff-metadata.json)

write_wrapper() {
  mkdir -p "$HOME/.local/bin"
  cat > "$WRAPPER" <<'WRAPPER_EOF'
#!/usr/bin/env bash
# Wird von infra/scripts/freebuff-install.sh erzeugt — nicht editieren.
set -euo pipefail
app_dir="/workspaces/freebuff"
native_dir="$HOME/.config/manicode"
launcher="${app_dir}/node_modules/freebuff/index.js"

if [ ! -f "$launcher" ]; then
  echo "freebuff: npm-Paket fehlt unter ${app_dir} — Installation unvollstaendig." >&2
  echo "  Reparieren: bash ./infra/scripts/freebuff-install.sh   (im MAIN-Repo)" >&2
  exit 127
fi

# Binary aus dem persistenten /workspaces-Cache zurueckholen (Rebuild-Fall).
mkdir -p "$native_dir"
for f in freebuff tree-sitter.wasm freebuff-metadata.json; do
  if [ ! -s "${native_dir}/${f}" ] && [ -s "${app_dir}/bin/${f}" ]; then
    cp -f "${app_dir}/bin/${f}" "${native_dir}/${f}"
  fi
done
chmod +x "${native_dir}/freebuff" 2>/dev/null || true

exec node "$launcher" "$@"
WRAPPER_EOF
  chmod +x "$WRAPPER"
}

cache_native_files() {
  local f
  mkdir -p "$BIN_DIR"
  for f in "${NATIVE_FILES[@]}"; do
    [ -s "${NATIVE_DIR}/${f}" ] && cp -f "${NATIVE_DIR}/${f}" "${BIN_DIR}/${f}" || true
  done
  chmod +x "${BIN_DIR}/freebuff" 2>/dev/null || true
}

# Reste abgebrochener Auto-Update-Downloads entfernen (siehe FREEBUFF_VERSION-Notiz).
cleanup_partial_downloads() {
  [ -d "$NATIVE_DIR" ] || return 0
  rm -rf "${NATIVE_DIR}"/.freebuff-*.tar.gz.part "${NATIVE_DIR}"/.freebuff-download-temp-* 2>/dev/null || true
}

# --- Ab hier Idempotenz-Guard ---------------------------------------------------
if [ -x "$WRAPPER" ] && [ "$(installed_version || true)" = "$FREEBUFF_VERSION" ]; then
  cleanup_partial_downloads
  cache_native_files
  echo "[freebuff] v${FREEBUFF_VERSION} bereits installiert (${APP_DIR}); Wrapper: ${WRAPPER}"
  exit 0
fi

echo "[freebuff] Installiere v${FREEBUFF_VERSION} nach ${APP_DIR}..."
mkdir -p "$APP_DIR" "$BIN_DIR"
if [ ! -f "${APP_DIR}/package.json" ]; then
  (cd "$APP_DIR" && npm init -y >/dev/null)
fi
# Kein Lockfile-Drift: die Version ist gepinnt, das Lockfile wird nur bei der
# Neuinstallation geschrieben und dann mitgeschrieben (package-lock.json).
(cd "$APP_DIR" && npm install --no-audit --no-fund --loglevel=error "freebuff@${FREEBUFF_VERSION}")
write_wrapper

# Erststart holt das native Binary (~130 MB Download) nach ~/.config/manicode —
# einmalig hier ausloesen und dann nach /workspaces cachen, damit Rebuilds es
# nicht erneut laden. Timeout, damit ein haengender Netz-Dialog den
# Codespace-Build nicht blockiert.
cleanup_partial_downloads
if [ ! -s "${NATIVE_DIR}/freebuff" ]; then
  echo "[freebuff] Lade natives Binary (einmalig, ~130 MB)..."
  timeout 600 "$WRAPPER" --version >/dev/null 2>&1 || true
fi
# Auto-Update-Reste vom Erststart einsammeln, bevor der Cache geschrieben wird:
# sonst cache das 136-MB-Binary und wirft die (dann nutzlose) 0.0.203-Version.
cleanup_partial_downloads
cache_native_files

if [ -s "${NATIVE_DIR}/credentials.json" ]; then
  echo "[freebuff] Login aus Secrets-Bundle vorhanden."
else
  echo "[freebuff] KEIN Login: einmalig 'freebuff login' (Browser-URL), dann ./infra/scripts/secrets.sh lock"
fi
echo "[freebuff] OK v${FREEBUFF_VERSION}. Start: cd <projekt> && freebuff"
