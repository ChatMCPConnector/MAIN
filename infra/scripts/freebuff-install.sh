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
# Scroll-Schrittweite: freebuff springt hartcodiert 80 % des Viewports pro
# `scroll-up` (`fOA=0.8` im Bundle, genau ein Vorkommen, keine Config, kein Flag,
# keine Env). opencode regelt das per Keybind (`messages_half_page_up: up` =
# halbe Seite), freebuff hat keine Keybind-Config — deshalb wird hier die
# Konstante im Vendor-Binary gepatcht. Fuenf Zeilen, gleiche Laenge, damit
# nichts verschoben wird. Der Launcher prueft nur die sha256 des ARCHIVS vor dem
# Entpacken, das entpackte Binary nicht mehr (launcher.js) — der Patch bleibt
# also erhalten und wird nicht bemerkt. Wird beim Auto-Update ein neues Binary
# geladen, patcht das naechste setup.sh erneut.
FREEBUFF_SCROLL_STEP="${FREEBUFF_SCROLL_STEP:-0.5}"   # 0.5 = wie opencode
#
# Maus: Default ist AUS (freebuff laeuft direkt, der pty-Filter nur per
# FREEBUFF_PTY_FILTER=1). Begruendung und Beleg im Wrapper-Kommentar.
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
# Default: KEIN Filter, freebuff laeuft direkt. freebuff 0.1.0 ist
# maus-first, und das ist belegt, nicht vermutet:
#   * Output-Bloecke (wAH, maxVisibleLines 5/10) klappen nur per Klick auf
#     (onClick togglet expanded) — es gibt keine Tasten-Action dafuer.
#   * opentui vergibt Fokus per Klick ("while(L){if(L.focusable){L.focus();
#     break}L=L.parent}"), und nur ein FOKUSSIERTER ScrollBox uebersetzt
#     pageup/up ueberhaupt in scrollBy (0,5 bzw. 0,2 Viewport). freebuff setzt
#     nirgends focusable und fokussiert nur die Eingabe — Fokus im Block
#     entsteht also ausschliesslich per Klick.
# Der pty-Filter entfernt genau diese Klicks und macht Output-Bloecke damit
# unbenutzbar (5/10 Zeilen, kein Aufklappen, kein Scrollen). Deshalb ist er
# nicht mehr Default.
# Kopieren kostet dabei nichts: freebuff kopiert beim Ziehen selbst, und
# /copy legt den GESAMTEN Chat inkl. vollstaendigem Output in die
# Zwischenablage. Was entfaellt, ist nur die native Terminal-Auswahl waehrend
# freebuff laeuft — in anderen Tabs und Sheets bleibt sie erhalten.
# Wer sie im TUI braucht: FREEBUFF_PTY_FILTER=1
if [ -t 0 ] && [ -t 1 ] && [ "\${FREEBUFF_PTY_FILTER:-0}" = "1" ] \
   && [ "\${FREEBUFF_NO_PTY_FILTER:-0}" != "1" ] \
   && command -v python3 >/dev/null 2>&1 && [ -f "\$pty_filter" ]; then
  # Der Filter protokolliert dann, welche Esc-Sequenzen das Kind liest, damit
  # sich Tastatur-Fragen in Sekunden beantworten lassen. Getippter Text wird
  # NICHT protokolliert (nur Byte-Laenge). Abschalten: FREEBUFF_PTY_DEBUG=off
  export FREEBUFF_PTY_DEBUG="\${FREEBUFF_PTY_DEBUG:-/tmp/opencode/freebuff-keys.log}"
  exec python3 "\$pty_filter" -- node "\$launcher" "\$@"
fi
exec node "\$launcher" "\$@"
WRAPPER_EOF
  chmod +x "$WRAPPER"
}

# Konstante fOA=0.8 -> FREEBUFF_SCROLL_STEP patchen. Sicherheitsregeln:
# nur bei GENAU einem Treffer, nur bei gleicher Laenge, Backup des Originals,
# und das Ergebnis wird verifiziert (siehe verify_after_patch).
patch_scroll_step() {
  local bin="${NATIVE_DIR}/freebuff"
  local want="${FREEBUFF_SCROLL_STEP}"
  [ -f "$bin" ] || return 0
  # Ein laufendes Executable laesst sich unter Linux nicht ueberschreiben
  # (ETXTBSY). Solange eine Session laeuft, wird der Patch uebersprungen und
  # beim naechsten Lauf ohne Session nachgeholt — genau der Fall nach einem
  # Auto-Update, den der Idempotenz-Pfad ohnehin abdeckt.
  if pgrep -f "$bin" >/dev/null 2>&1; then
    echo "[freebuff] Session laeuft -> Scroll-Patch erst nach deren Ende (Rad bleibt bis dahin bei 80 %)"
    return 0
  fi
  case "$want" in
    0.[0-9]) : ;;
    *) echo "[freebuff] FREEBUFF_SCROLL_STEP='${want}' ignoriert (muss 0.x sein)"; want=0.5 ;;
  esac
  if ! command -v python3 >/dev/null 2>&1; then
    echo "[freebuff] WARN: kein python3 -> Scroll-Patch uebersprungen (Rad bleibt bei 80 %)"
    return 0
  fi
  python3 - "$bin" "$want" "${NATIVE_DIR}/freebuff.orig" <<'PYEOF'
import shutil, sys
path, want, backup = sys.argv[1], sys.argv[2], sys.argv[3]
old, new = b"fOA=0.8", b"fOA=" + want.encode()
if len(old) != len(new):
    print("  Laengendifferenz -> nicht gepatcht"); sys.exit(0)
data = open(path, "rb").read()
n = data.count(old)
if n == 0:
    print("  " + ("bereits gepatcht" if data.count(new) else
                  "Muster nicht gefunden (Upstream umbenannt) -> unangetastet"))
    sys.exit(0)
if n != 1:
    print(f"  {n} Treffer -> Abbruch, unangetastet"); sys.exit(0)
if not __import__("os").path.exists(backup):
    shutil.copy2(path, backup)
try:
    open(path, "wb").write(data.replace(old, new))
except OSError as exc:
    # Z. B. ETXTBSY, wenn zwischen Pruefung und Schreiben eine Session startet.
    print(f"  nicht geschrieben: {exc}"); sys.exit(0)
print(f"  gepatcht: 0.8 -> {want} (Backup: {backup})")
PYEOF
}

# Nach dem Patch pruefen, ob das Binary noch startet; sonst Backup zurueck.
verify_after_patch() {
  local bin="${NATIVE_DIR}/freebuff"
  [ -f "$bin" ] || return 0
  timeout 60 "$bin" --version >/dev/null 2>&1 && return 0
  if [ -f "${NATIVE_DIR}/freebuff.orig" ]; then
    echo "[freebuff] WARN: Binary startet nach Patch nicht -> Backup wird zurueckgespielt"
    cp -f "${NATIVE_DIR}/freebuff.orig" "$bin"; chmod +x "$bin"
  fi
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
  # Auch im "schon da"-Fall: ein Auto-Update hat das Binary ersetzt, dann ist der
  # Patch weg und muss neu drauf.
  patch_scroll_step
  verify_after_patch
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
patch_scroll_step
verify_after_patch

if [ -s "${NATIVE_DIR}/credentials.json" ]; then
  echo "[freebuff] Login aus Secrets-Bundle vorhanden."
else
  echo "[freebuff] KEIN Login: einmalig 'freebuff login' (Browser-URL), dann ./infra/scripts/secrets.sh lock"
fi
echo "[freebuff] OK v${FREEBUFF_VERSION}. Start: cd <projekt> && freebuff"
