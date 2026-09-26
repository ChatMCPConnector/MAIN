#!/usr/bin/env bash
# freebuff-install.sh: Installiert die Freebuff CLI (werbefinanzierter, kostenloser
# Coding-Agent von CodebuffAI) nach $HOME/.local/share/freebuff.
# Kanonisch: FREEBUFF_VERSION unten pinnen + dieses Skript ist der einzige Weg.
# setup.sh ruft es bei jedem neuen Codespace automatisch auf (idempotent).
#
# Modell bewusst wie opencode: Das Repo VERWALTET die Installation, die Dateien
# liegen in $HOME (ephemeral) und werden bei jedem neuen Codespace neu gebaut.
# Deshalb nichts unter /workspaces — das war ein verworfener Zwischenstand, in
# dem das Binary zwischen /workspaces und $HOME hin- und herkopiert wurde.
#
# $HOME ist ephemer, das native Binary (136 MB) legt der npm-Launcher selbst
# dorthin: ~/.config/manicode/freebuff (launcher.js:
# path.join(os.homedir(), '.config', 'manicode') — kein Env-Override, also
# nicht um konfigurierbar). Folgen:
#  * Jeder neue Codespace lädt das Binary neu (~30 s, sichtbarer Progress-Output).
#    Das ist derselbe Preis wie bei opencode und wird in Kauf genommen.
#  * Der Launcher zieht IMMER das neueste veroeffentlichte Binary selbst nach,
#    unabhaengig von der npm-Pin (live belegt: npm-Pin 0.0.203 -> Launcher holte
#    0.0.204) und legt dabei `.freebuff-<version>-*.tar.gz.part` +
#    `.freebuff-download-temp-*` in $HOME/.config/manicode ab. Die Reste werden
#    hier aufgeraeumt, sonst fressen sie bei jedem Start Platte.
#
# Login: kommt NICHT von hier. ~/.config/manicode/credentials.json wird ueber
# infra/scripts/secrets.sh aus config/secrets.enc wiederhergestellt — deshalb
# steht der Aufruf in setup.sh bewusst NACH dem Secrets-Schritt.
# Ist dort kein Login hinterlegt: `freebuff login` (Browser-URL, geht nicht headless).
set -euo pipefail

# Muss zu `npm view freebuff version` passen, sonst zieht der Launcher sofort ein
# neueres Binary und schreibt beim Start die .part-Reste.
FREEBUFF_VERSION="0.0.204"
readonly APP_DIR="$HOME/.local/share/freebuff"
readonly WRAPPER="$HOME/.local/bin/freebuff"
readonly NATIVE_DIR="$HOME/.config/manicode"
# Pfad wird in den Wrapper eingebacken: setup.sh ruft nur dieses Skript auf, der
# Wrapper muss den Filter also ohne Repo-Umgebung finden.
readonly REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

installed_version() {
  [ -f "${APP_DIR}/node_modules/freebuff/package.json" ] || return 1
  sed -nE 's/.*"version"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' \
    "${APP_DIR}/node_modules/freebuff/package.json" | head -1
}

write_wrapper() {
  mkdir -p "$HOME/.local/bin"
  # Fest verdrahtet auf $HOME/.local/share/freebuff — steht hier im Klartext,
  # weil das Repo diesen Pfad nicht zur Laufzeit uebergibt (setup.sh ruft nur
  # das Skript auf).
  cat > "$WRAPPER" <<WRAPPER_EOF
#!/usr/bin/env bash
# Wird von infra/scripts/freebuff-install.sh erzeugt — nicht editieren.
set -euo pipefail
launcher="$APP_DIR/node_modules/freebuff/index.js"
pty_filter="${REPO_ROOT}/infra/scripts/freebuff-pty.py"
if [ ! -f "\$launcher" ]; then
  echo "freebuff: npm-Paket fehlt (\$launcher) — Installation unvollstaendig." >&2
  echo "  Reparieren: bash ./infra/scripts/freebuff-install.sh   (im MAIN-Repo)" >&2
  exit 127
fi
# Freebuff (opentui) schaltet Mouse-Reporting ein und killt damit die native
# Textauswahl des Terminals. Einen Config-Kniff gibt es nicht (weder
# settings.json noch Flag noch Env), also laeuft das TUI durch
# freebuff-pty.py, das nur die Maus-Sequenzen aus dem Output entfernt —
# derselbe Effekt wie opencodes 'mouse: false'. Bypass zum Debuggen:
# FREEBUFF_NO_PTY_FILTER=1 freebuff
if [ -t 0 ] && [ -t 1 ] && [ "\${FREEBUFF_NO_PTY_FILTER:-0}" != "1" ] \\
   && command -v python3 >/dev/null 2>&1 && [ -f "\$pty_filter" ]; then
  # Standardmaessig protokolliert der Filter, welche Esc-Sequenzen das Kind
  # liest. Das beantwortet die Frage "kommt die Keybinding-Taste ueberhaupt an"
  # ohne weiteres Raten. Getippter Text wird NICHT protokolliert (nur Laenge).
  # Abschalten: FREEBUFF_PTY_DEBUG=off
  export FREEBUFF_PTY_DEBUG="\${FREEBUFF_PTY_DEBUG:-/tmp/opencode/freebuff-keys.log}"
  exec python3 "\$pty_filter" -- node "\$launcher" "\$@"
fi
exec node "\$launcher" "\$@"
WRAPPER_EOF
  chmod +x "$WRAPPER"
}

# Reste abgebrochener Auto-Update-Downloads entfernen.
cleanup_partial_downloads() {
  [ -d "$NATIVE_DIR" ] || return 0
  rm -rf "${NATIVE_DIR}"/.freebuff-*.tar.gz.part "${NATIVE_DIR}"/.freebuff-download-temp-* 2>/dev/null || true
}

# --- Ab hier Idempotenz-Guard ---------------------------------------------------
# write_wrapper laeuft auch im "schon da"-Fall: der Wrapper haelt Repo-Pfade
# (pty-Filter) und wird bei jedem Build neu erzeugt, sonst driftet er still
# weiter, wenn sich der Repo-Pfad aendert.
if [ -x "$WRAPPER" ] && [ "$(installed_version || true)" = "$FREEBUFF_VERSION" ] && [ -s "${NATIVE_DIR}/freebuff" ]; then
  write_wrapper
  cleanup_partial_downloads
  echo "[freebuff] v${FREEBUFF_VERSION} bereits installiert (${APP_DIR}); Wrapper: ${WRAPPER}"
  exit 0
fi

echo "[freebuff] Installiere v${FREEBUFF_VERSION} nach ${APP_DIR}..."
mkdir -p "$APP_DIR"
if [ ! -f "${APP_DIR}/package.json" ]; then
  (cd "$APP_DIR" && npm init -y >/dev/null)
fi
# Kein Lockfile-Drift: die Version ist gepinnt, das Lockfile wird nur bei der
# Neuinstallation geschrieben (liegt in $HOME, ist damit ephemer).
(cd "$APP_DIR" && npm install --no-audit --no-fund --loglevel=error "freebuff@${FREEBUFF_VERSION}")
write_wrapper

# Erststart holt das native Binary (~136 MB) nach ~/.config/manicode. Timeout,
# damit ein haengender Netz-Dialog den Codespace-Build nicht blockiert.
cleanup_partial_downloads
if [ ! -s "${NATIVE_DIR}/freebuff" ]; then
  echo "[freebuff] Lade natives Binary (einmalig pro Codespace, ~136 MB)..."
  timeout 600 "$WRAPPER" --version >/dev/null 2>&1 || true
fi
cleanup_partial_downloads

if [ -s "${NATIVE_DIR}/credentials.json" ]; then
  echo "[freebuff] Login aus Secrets-Bundle vorhanden."
else
  echo "[freebuff] KEIN Login: einmalig 'freebuff login' (Browser-URL), dann ./infra/scripts/secrets.sh lock"
fi
echo "[freebuff] OK v${FREEBUFF_VERSION}. Start: cd <projekt> && freebuff"
