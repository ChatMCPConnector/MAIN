#!/usr/bin/env bash
# freebuff-install.sh: Installiert die Freebuff CLI (werbefinanzierter, kostenloser
# Coding-Agent von CodebuffAI) nach $HOME/.local/share/freebuff.
# Kanonisch: dieses Skript ist der einzige Weg (keine Versions-Pin, s.u.).
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
#    `.freebuff-download-temp-*` in $HOME/.config/manicode ab. Die Reste raeumt
#    freebuff_patch.py auf (beim Patchen und bei jedem Start), sonst fressen sie
#    bei jedem Start Platte — live am 2026-10-02: drei Reste mit je 133 MB.
#
# BYTE-PATCHES: nicht hier, sondern in infra/scripts/freebuff_patch.py. Das
# Skript hier installiert und ruft den Patcher auf; die Patch-Logik selbst
# (Scroll-Schrittweite, Mausrad-Scroll, Wortgrenzen, Entf in /history), ihre
# Update-Festigkeit und die Begruendung stehen dort — bewusst an genau einer
# Stelle. Weil der Launcher das Binary jederzeit ungefragt ersetzen kann, laeuft
# der Patcher zusaetzlich **bei jedem Start** aus dem Wrapper (write_wrapper),
# nicht nur hier beim Build.
#
# Maus: AUS, immer, ueber den pty-Filter. Es gibt genau eine Betriebsart.
# Begruendung und Beleg im Wrapper-Kommentar.
#
# Login: kommt NICHT von hier. ~/.config/manicode/credentials.json wird ueber
# infra/scripts/secrets.sh aus config/secrets.enc wiederhergestellt — deshalb
# steht der Aufruf in setup.sh bewusst NACH dem Secrets-Schritt.
# Ist dort kein Login hinterlegt: `freebuff login` (Browser-URL, geht nicht headless).
set -euo pipefail

# Muss zu `npm view freebuff version` passen, sonst zieht der Launcher sofort ein
# neueres Binary und schreibt beim Start die .part-Reste.
# KEINE gepinnte Version (Nutzerentscheidung 2026-09-27): freebuff aktualisiert
# sich so schnell, dass ein Pin ständig veraltet und die Abhaengigkeit nur
# aergerlich macht. Installiert wird immer `latest`; ueber den Takt entscheidet
# `setup.sh` (einmal je Codespace). Der Launcher zieht das native Binary ohnehin
# selbst nach — ein Pin koennte das ohnehin nicht verhindern.
FREEBUFF_SCROLL_STEP_VERSION="latest"
FREEBUFF_SCROLL_STEP="${FREEBUFF_SCROLL_STEP:-0.5}"   # 0.5 = wie opencode
readonly APP_DIR="$HOME/.local/share/freebuff"
readonly WRAPPER="$HOME/.local/bin/freebuff"
readonly NATIVE_DIR="$HOME/.config/manicode"
# Pfad wird in den Wrapper eingebacken: setup.sh ruft nur dieses Skript auf, der
# Wrapper muss den Filter also ohne Repo-Umgebung finden.
readonly REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly PATCHER="${REPO_ROOT}/infra/scripts/freebuff_patch.py"

# Patches anwenden, Reste abgebrochener Downloads raeumen. Exit 1 des Patchers
# (Struktur-Drift) darf das Skript nicht abbrechen: freebuff laeuft auch ohne
# Patch, nur eben mit totem Mausrad und wirkungslosem Entf. Der Patcher meldet
# selbst und legt sein Ergebnis in $NATIVE_DIR/freebuff-patch.status ab.
run_patcher() {
  if [ ! -f "$PATCHER" ]; then
    echo "[freebuff] WARN: $PATCHER fehlt — Byte-Patches (Mausrad, Entf in /history) nicht angewandt"
    return 0
  fi
  local rc=0
  python3 "$PATCHER" --native-dir "$NATIVE_DIR" \
    --scroll-step "$FREEBUFF_SCROLL_STEP" "$@" || rc=$?
  case "$rc" in
    0) : ;;
    1) echo "[freebuff] WARN: ein Byte-Patch passt nicht mehr (Struktur geaendert) — Status: ${NATIVE_DIR}/freebuff-patch.status" ;;
    *) echo "[freebuff] WARN: Patcher Exit ${rc} (Binary fehlt/kaputt) — Status: ${NATIVE_DIR}/freebuff-patch.status" ;;
  esac
  return 0
}

installed_version() {
  [ -f "${APP_DIR}/node_modules/freebuff/package.json" ] || return 1
  sed -nE 's/.*"version"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' \
    "${APP_DIR}/node_modules/freebuff/package.json" | head -1
}

# Ohne Pin heisst "installiert": das Paket ist die aktuellste veroeffentlichte
# Version. `npm view` kostet ~200 ms und wird nur beim Build ausgefuehrt.
is_latest_installed() {
  local have want
  have="$(installed_version || true)"
  [ -n "$have" ] || return 1
  want="$(npm view freebuff version 2>/dev/null || true)"
  [ -n "$want" ] || return 1
  [ "$have" = "$want" ]
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
patcher="${REPO_ROOT}/infra/scripts/freebuff_patch.py"
if [ ! -f "\$launcher" ]; then
  echo "freebuff: npm-Paket fehlt (\$launcher) — Installation unvollstaendig." >&2
  echo "  Reparieren: bash ./infra/scripts/freebuff-install.sh   (im MAIN-Repo)" >&2
  exit 127
fi
# Patches VOR dem Start nachziehen. Grund: der npm-Launcher ersetzt das native
# Binary bei jedem Update ungefragt (deferUpdatesUntilExit), und die Patches
# liegen als Bytes in genau dieser Datei — ein Update loescht sie alle. Live
# belegt 2026-10-02 (0.2.11): Mausrad und Entf in /history tot, bis zum
# naechsten Codespace-Build. Die Option --ensure vergleicht eine Stamp-Datei
# (Groesse+mtime+Formatversion) mit dem Binary und patcht nur bei Aenderung:
# Normalfall ein stat() (~0.1 s), nach einem Update einmalig ein Durchlauf.
# Rueckgabe 1 = ein Patch passt nicht mehr (Struktur-Drift). Dann startet
# freebuff trotzdem — mit einer Warnung, die der Zustand-Datei zu entnehmen ist.
if [ -f "\$patcher" ] && command -v python3 >/dev/null 2>&1; then
  if ! patch_out="\$(python3 "\$patcher" --ensure 2>&1)"; then
    echo "freebuff: Byte-Patches unvollstaendig — Mausrad/Entf koennen ausfallen." >&2
    printf 'freebuff: %s\n' "\$patch_out" >&2
    echo "freebuff: Status: ~/.config/manicode/freebuff-patch.status" >&2
  fi
fi
# EIN Modus, Filter immer an: Maus aus heisst, das Terminal kann auswaehlen — damit
#   * Strg+C kopiert die Auswahl (xterm.js kopiert nur MIT Auswahl; ohne
#     Auswahl geht Strg+C als ^C an die App = Interrupt), und
#   * Strg+V fuegt ein (freebuff schaltet Bracketed Paste frei, live geprueft:
#     ESC[200~textESC[201~ landet in der Eingabe), und
#   * das Mausrad kommt als up/down an; das freebuff-Binary mappt history-up/down
#     intern per Patch direkt auf onScrollUp/Down (opencode-Prinzip).
#     Damit scrollt das Rad die Unterhaltung, und Pfeiltasten in Menues
#     (/history, Slash-Menue, Model-Picker) bleiben 100% nativ bedienbar; und
#   * Strg+Links/Rechts springt ueber Woerter (Uebersetzung auf Alt+Links/Rechts),
#     Strg+Backspace loescht ganze Woerter (Uebersetzung auf Ctrl+W).
# Preis dieser Konfiguration: freebuff bekommt keine Mausklicks, also
# sind Output-Bloecke (5/10 Zeilen) nicht per Klick aufklappbar. Der volle
# Output liegt trotzdem in der Zwischenablage: /copy (Alias copy-chat) legt den
# GESAMTEN Chat hinein, /export schreibt ihn als Datei.
# Notausgang nur fuer Fehlersuche: FREEBUFF_NO_PTY_FILTER=1
if [ -t 0 ] && [ -t 1 ] && [ "\${FREEBUFF_NO_PTY_FILTER:-0}" != "1" ] \\
   && command -v python3 >/dev/null 2>&1 && [ -f "\$pty_filter" ]; then
  # Der Filter protokolliert, welche Esc-Sequenzen das Kind liest — damit sind
  # Tastatur-Fragen in Sekunden beantwortet statt im Binary zu suchen. Getippter
  # Text wird NICHT protokolliert (nur Byte-Laenge). Abschalten:
  # FREEBUFF_PTY_DEBUG=off
  export FREEBUFF_PTY_DEBUG="\${FREEBUFF_PTY_DEBUG:-/tmp/opencode/freebuff-keys.log}"
  exec python3 "\$pty_filter" -- node "\$launcher" "\$@"
fi
exec node "\$launcher" "\$@"
WRAPPER_EOF
  chmod +x "$WRAPPER"
  # Der Wrapper entsteht in einem *unquotierten* Heredoc ($REPO_ROOT/$APP_DIR
  # werden beim Schreiben expandiert). Dabei wurde einmal ein Backtick-Kommentar
  # als Command-Substitution ausgefuehrt (`--ensure: command not found`) und
  # die Kommentarzeile leise zerstoert. `bash -n` faengt das, bevor freebuff
  # beim naechsten Start an einem kaputten Wrapper scheitert.
  bash -n "$WRAPPER" || {
    echo "[freebuff] FEHLER: erzeugter Wrapper hat einen Syntaxfehler — $WRAPPER"
    return 1
  }
}

# --- Ab hier Idempotenz-Guard ---------------------------------------------------
# write_wrapper laeuft auch im "schon da"-Fall: der Wrapper haelt Repo-Pfade
# (pty-Filter) und wird bei jedem Build neu erzeugt, sonst driftet er still
# weiter, wenn sich der Repo-Pfad aendert.
if [ -x "$WRAPPER" ] && is_latest_installed && [ -s "${NATIVE_DIR}/freebuff" ]; then
  write_wrapper
  # Auch im "schon da"-Fall patchen: ein Auto-Update hat das Binary ersetzt, dann
  # sind die Patches weg. Der Patcher raeumt zugleich alte Download-Reste ab.
  run_patcher --force
  echo "[freebuff] v$(installed_version) (aktuellste) bereits installiert (${APP_DIR}); Wrapper: ${WRAPPER}"
  exit 0
fi

echo "[freebuff] Installiere freebuff@latest nach ${APP_DIR}..."
mkdir -p "$APP_DIR"
if [ ! -f "${APP_DIR}/package.json" ]; then
  (cd "$APP_DIR" && npm init -y >/dev/null)
fi
# Kein Lockfile-Drift: die Version ist gepinnt, das Lockfile wird nur bei der
# Neuinstallation geschrieben (liegt in $HOME, ist damit ephemer).
(cd "$APP_DIR" && npm install --no-audit --no-fund --loglevel=error "freebuff@${FREEBUFF_SCROLL_STEP_VERSION}")
write_wrapper

# Erststart holt das native Binary (~136 MB) nach ~/.config/manicode. Timeout,
# damit ein haengender Netz-Dialog den Codespace-Build nicht blockiert.
if [ ! -s "${NATIVE_DIR}/freebuff" ]; then
  echo "[freebuff] Lade natives Binary (einmalig pro Codespace, ~136 MB)..."
  timeout 600 "$WRAPPER" --version >/dev/null 2>&1 || true
fi
run_patcher --force

if [ -s "${NATIVE_DIR}/credentials.json" ]; then
  echo "[freebuff] Login aus Secrets-Bundle vorhanden."
else
  echo "[freebuff] KEIN Login: einmalig 'freebuff login' (Browser-URL), dann ./infra/scripts/secrets.sh lock"
fi
echo "[freebuff] OK v$(installed_version). Start: cd <projekt> && freebuff"
