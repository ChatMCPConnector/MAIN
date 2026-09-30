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
if [ ! -f "\$launcher" ]; then
  echo "freebuff: npm-Paket fehlt (\$launcher) — Installation unvollstaendig." >&2
  echo "  Reparieren: bash ./infra/scripts/freebuff-install.sh   (im MAIN-Repo)" >&2
  exit 127
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
}

# Konstante fOA=0.8 -> FREEBUFF_SCROLL_STEP patchen. Sicherheitsregeln:
# nur bei GENAU einem Treffer, nur bei gleicher Laenge, Backup des Originals,
# und das Ergebnis wird verifiziert (siehe verify_after_patch).
patch_scroll_step() {
  local bin="${NATIVE_DIR}/freebuff"
  local want="${FREEBUFF_SCROLL_STEP}"
  [ -f "$bin" ] || return 0
  case "$want" in
    0.[0-9]) : ;;
    *) echo "[freebuff] FREEBUFF_SCROLL_STEP='${want}' ignoriert (muss 0.x sein)"; want=0.5 ;;
  esac
  if ! command -v python3 >/dev/null 2>&1; then
    echo "[freebuff] WARN: kein python3 -> Scroll-Patch uebersprungen (Rad springt in 0.8-Seiten)"
    return 0
  fi
  python3 - "$bin" "$want" "${NATIVE_DIR}/freebuff.orig" <<'PYEOF'
"""Schrittweite des Seitenscrolls per Mustersuche patchen.

Der Faktor ist im Bundle eine Variable, die an BEIDEN Scrollrichtungen sitzt:

    X = P.viewport.height,  v = Math.floor(X * <VAR>),  ...

0.0.204 hiess sie `fOA`, 0.1.0 `$hA`. Der namensbasierte Patch (`fOA=0.8`) war
dadurch beim ersten Update tot — deshalb jetzt **Mustersuche statt Namenssuche**,
damit ein Rename nichts killt:

  1. Use-Stelle: `Math.floor(<A>*<VAR>)` im Kontext von `viewport.height`.
  2. Definition: `<VAR>=<0.x>` — genau eine Stelle, sonst unangetastet.
  3. Diese eine Zahl ersetzen, gleiche Laenge (0.8 -> 0.5).

Bricht die Struktur kuenftig ab, meldet das Skript "Struktur nicht erkannt"
und laesst das Binary unangetastet — nie still falsch.
"""
import os, re, shutil, sys

path, want, backup = sys.argv[1], sys.argv[2], sys.argv[3]
data = open(path, "rb").read()

use = re.compile(rb"Math\.floor\(([A-Za-z0-9_$]{1,4})\*([A-Za-z0-9_$]{1,6})\)")
cands = {m.group(2) for m in use.finditer(data)
         if b"viewport.height" in data[max(0, m.start() - 200):m.start() + 200]}
if not cands:
    print("  Struktur nicht erkannt (kein Math.floor(X*VAR) neben viewport.height) -> unangetastet")
    sys.exit(0)

targets = []
for var in cands:
    for m in re.finditer(re.escape(var) + rb"=(0\.[0-9]+)(?![0-9A-Za-z_$])", data):
        targets.append((m.start(1), m.group(1)))
if len(targets) != 1:
    names = sorted(c.decode() for c in cands)
    print(f"  {len(targets)} Definitionsstellen fuer {names} -> unangetastet (statt zu raten)")
    sys.exit(0)

off, old = targets[0]
if old.decode() == want:
    print(f"  Schrittweite bereits {want}")
    sys.exit(0)
new = want.encode()
if len(new) != len(old):
    print("  Laengendifferenz -> unangetastet")
    sys.exit(0)
if not os.path.exists(backup):
    shutil.copy2(path, backup)
out = bytearray(data)
out[off:off + len(old)] = new
tmp = path + ".patched"
with open(tmp, "wb") as f:
    f.write(bytes(out))
os.chmod(tmp, 0o755)
os.replace(tmp, path)
print(f"  Schrittweite {old.decode()} -> {want} (Backup: {backup})")
PYEOF
}

# Pfeiltasten bei leerem Prompt: von history-up/down auf onScrollUp/Down umhaengen.
# Damit scrollt das Mausrad (das als Up/Down-Pfeile ankommt) die Unterhaltung,
# genau wie in opencode (messages_half_page_up: up). Menues (/history, Slash-Menue,
# Model-Picker) fangen die Pfeile DAVOR ab und bleiben voll bedienbar.
patch_arrow_scroll() {
  local bin="${NATIVE_DIR}/freebuff"
  [ -f "$bin" ] || return 0
  if ! command -v python3 >/dev/null 2>&1; then
    echo "[freebuff] WARN: kein python3 -> Pfeil-Scroll-Patch uebersprungen"
    return 0
  fi
  python3 - "$bin" <<'PYEOF'
import os, sys

path = sys.argv[1]
data = open(path, "rb").read()
orig = b'case"history-up":return A.onHistoryUp(),!0;case"history-down":return A.onHistoryDown(),!0;'
repl = b'case"history-up":return(A.onScrollUp(),!0);case"history-down":return(A.onScrollDown(),!0);'

if repl in data:
    print("  Pfeil-Scroll-Patch: bereits gepatcht (onScrollUp/Down)")
    sys.exit(0)

if data.count(orig) != 1:
    print(f"  Pfeil-Scroll-Patch: {data.count(orig)} Treffer fuer Muster -> unangetastet")
    sys.exit(0)

assert len(orig) == len(repl), "Laengendifferenz"
out = data.replace(orig, repl, 1)
assert len(out) == len(data), "Dateigroesse darf sich nicht aendern"

tmp = path + ".patched"
with open(tmp, "wb") as f:
    f.write(out)
os.chmod(tmp, 0o755)
os.replace(tmp, path)
print("  Pfeil-Scroll-Patch: erfolgreich (history-up/down -> onScrollUp/Down)")
PYEOF
}

# Wortgrenzen-Patch: LGA und _GA so anpassen, dass Wortsprünge und Wortlöschen
# an Zeilenumbrüchen (und Leerzeilen) sauber anhalten, statt über Zeilengrenzen
# hinweg das vorherige Wort mitzufressen.
patch_word_boundary() {
  local bin="${NATIVE_DIR}/freebuff"
  [ -f "$bin" ] || return 0
  if ! command -v python3 >/dev/null 2>&1; then
    echo "[freebuff] WARN: kein python3 -> Wortgrenzen-Patch uebersprungen"
    return 0
  fi
  python3 - "$bin" <<'PYEOF'
import os, sys

path = sys.argv[1]
data = open(path, "rb").read()
orig = b'function LGA(H,A){let $=Math.max(0,Math.min(A,H.length));while($>0&&/\\s/.test(H[$-1]))$--;while($>0&&!/\\s/.test(H[$-1]))$--;return $}function _GA(H,A){let $=Math.max(0,Math.min(A,H.length));while($<H.length&&!/\\s/.test(H[$]))$++;while($<H.length&&/\\s/.test(H[$]))$++;return $}'
repl = b'function LGA(H,A){let $=Math.max(0,Math.min(A,H.length)),s=$>0&&/\\s/.test(H[$-1]);while($>0&&s===/\\s/.test(H[$-1]))$--;return $;    }function _GA(H,A){let $=Math.max(0,Math.min(A,H.length)),s=$<H.length&&/\\s/.test(H[$]);while($<H.length&&s===/\\s/.test(H[$]))$++;return $;    }'

if repl in data:
    print("  Wortgrenzen-Patch: bereits gepatcht")
    sys.exit(0)

if data.count(orig) != 1:
    print(f"  Wortgrenzen-Patch: {data.count(orig)} Treffer fuer Muster -> unangetastet")
    sys.exit(0)

assert len(orig) == len(repl), "Laengendifferenz"
out = data.replace(orig, repl, 1)
assert len(out) == len(data), "Dateigroesse darf sich nicht aendern"

tmp = path + ".patched"
with open(tmp, "wb") as f:
    f.write(out)
os.chmod(tmp, 0o755)
os.replace(tmp, path)
print("  Wortgrenzen-Patch: erfolgreich (saubere Zeilen-/Wortgrenzen bei Strg+Links/Rechts und Backspace)")
PYEOF
}

# History-Delete-Patch: Ermoeglicht das Loeschen von Chats in /history ueber die Tastatur
# (Delete, Ctrl+D, Ctrl+X), da Freebuff von Haus aus nur Mausklick [x] anbietet,
# die Maus im Terminal aber bewusst deaktiviert ist.
patch_history_delete() {
  local bin="${NATIVE_DIR}/freebuff"
  [ -f "$bin" ] || return 0
  if ! command -v python3 >/dev/null 2>&1; then
    echo "[freebuff] WARN: kein python3 -> History-Delete-Patch uebersprungen"
    return 0
  fi
  python3 - "$bin" <<'PYEOF'
import os, re, sys

path = sys.argv[1]
data = open(path, "rb").read()

if b'k==="delete"' in data and b"Del / Ctrl+D to remove" in data:
    print("  History-Delete-Patch: bereits gepatcht")
    sys.exit(0)

pattern = re.compile(
    rb'(?P<fn>[a-zA-Z0-9_$]+)=(?P<react>[a-zA-Z0-9_$]+)\.useCallback\(\((?P<key>[a-zA-Z0-9_$]+)\)=>\{'
    rb'if\((?P=key)\.name==="escape"\)\{if\((?P<query>[a-zA-Z0-9_$]+)\.length>0\)(?P<setQuery>[a-zA-Z0-9_$]+)\(""\);else (?P<cancel>[a-zA-Z0-9_$]+)\(\);return!0\}'
    rb'if\((?P=key)\.name==="up"\)return (?P<setIndex>[a-zA-Z0-9_$]+)\(\(([a-zA-Z0-9_$]+)\)=>Math\.max\(0,[a-zA-Z0-9_$]+-1\)\),!0;'
    rb'if\((?P=key)\.name==="down"\)\{let [a-zA-Z0-9_$]+=Math\.min\((?P<items>[a-zA-Z0-9_$]+)\.length,(?P<consts>[a-zA-Z0-9_$]+)\.MAX_RENDERED_CHATS\)-1;return (?P=setIndex)\(\([a-zA-Z0-9_$]+\)=>Math\.min\([a-zA-Z0-9_$]+,[a-zA-Z0-9_$]+\+1\)\),!0\}'
    rb'let (?P<rightVar>[a-zA-Z0-9_$]+)=(?P=key)\.name==="right"&&!(?P=key)\.ctrl&&!(?P=key)\.meta&&!(?P=key)\.option&&!(?P=key)\.shift;'
    rb'if\((?P<isEnter>[a-zA-Z0-9_$]+)\((?P=key)\)\|\|(?P=rightVar)\)\{let [a-zA-Z0-9_$]+=(?P=items)\[(?P<index>[a-zA-Z0-9_$]+)\];if\([a-zA-Z0-9_$]+\)(?P<openChat>[a-zA-Z0-9_$]+)\([a-zA-Z0-9_$]+\.id\);return!0\}'
    rb'if\((?P=key)\.name==="c"&&(?P=key)\.ctrl\)return (?P=cancel)\(\),!0;'
    rb'return!1\},\[(?P=query),(?P=setQuery),(?P=setIndex),(?P=items),(?P=index),(?P=openChat),(?P=cancel)\]\)'
)

before_pattern = re.compile(
    rb'(?P<action>[a-zA-Z0-9_$]+)=(?P<react>[a-zA-Z0-9_$]+)\.useCallback\(\(([a-zA-Z0-9_$]+)\)=>\{(?P<fn>[a-zA-Z0-9_$]+)\([a-zA-Z0-9_$]+\.id\)\},\[(?P=fn)\]\),'
)

match = pattern.search(data)
if not match:
    print("  History-Delete-Patch: Muster nicht gefunden -> unangetastet")
    sys.exit(0)

m_before = list(before_pattern.finditer(data[max(0, match.start()-150):match.start()]))
if len(m_before) < 2:
    print("  History-Delete-Patch: Delete-Action nicht gefunden -> unangetastet")
    sys.exit(0)

deleteAction = m_before[1].group('action').decode('latin1')
g = {k: v.decode('latin1') for k, v in match.groupdict().items()}
g['deleteAction'] = deleteAction
orig = match.group()

base_repl = (
    f"{g['fn']}={g['react']}.useCallback(({g['key']})=>"
    f"{{let k={g['key']}.name,s={g['items']}[{g['index']}];"
    f"if(k===\"escape\")return {g['query']}?{g['setQuery']}(\"\"):{g['cancel']}(),!0;"
    f"if(k===\"up\")return {g['setIndex']}(s=>Math.max(0,s-1)),!0;"
    f"if(k===\"down\")return {g['setIndex']}(s=>Math.min(Math.min({g['items']}.length,{g['consts']}.MAX_RENDERED_CHATS)-1,s+1)),!0;"
    f"if(s&&(k===\"delete\"||{g['key']}.ctrl&&(k===\"d\"||k===\"x\")))return {g['deleteAction']}(s),!0;"
    f"if({g['isEnter']}({g['key']})||k===\"right\"&&!{g['key']}.meta&&!{g['key']}.option&&!{g['key']}.shift)return s&&{g['openChat']}(s.id),!0;"
    f"if({g['key']}.ctrl&&k===\"c\")return {g['cancel']}(),!0;"
    f"return!1"
)
suffix = f"}},[{g['query']},{g['setQuery']},{g['setIndex']},{g['items']},{g['index']},{g['openChat']},{g['cancel']}])"

pad = len(orig) - (len(base_repl) + len(suffix))
if pad < 0:
    print("  History-Delete-Patch: Code laenger als Original -> unangetastet")
    sys.exit(0)

repl = (base_repl + (" " * pad) + suffix).encode('latin1')
assert len(repl) == len(orig), "Laengendifferenz"

out = bytearray(data)
out[match.start():match.end()] = repl

footer_orig = b"Click [\\xD7] to remove"
footer_repl = b"Del / Ctrl+D to remove"
if out.count(footer_orig) == 1:
    f_idx = out.find(footer_orig)
    out[f_idx:f_idx+len(footer_orig)] = footer_repl

assert len(out) == len(data), "Dateigroesse darf sich nicht aendern"

tmp = path + ".patched"
with open(tmp, "wb") as f:
    f.write(bytes(out))
os.chmod(tmp, 0o755)
os.replace(tmp, path)
print("  History-Delete-Patch: erfolgreich (Delete/Ctrl+D/Ctrl+X loescht Session)")
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
if [ -x "$WRAPPER" ] && is_latest_installed && [ -s "${NATIVE_DIR}/freebuff" ]; then
  write_wrapper
  cleanup_partial_downloads
  # Auch im "schon da"-Fall: ein Auto-Update hat das Binary ersetzt, dann ist der
  # Patch weg und muss neu drauf.
  patch_scroll_step
  patch_arrow_scroll
  patch_word_boundary
  patch_history_delete
  verify_after_patch
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
cleanup_partial_downloads
if [ ! -s "${NATIVE_DIR}/freebuff" ]; then
  echo "[freebuff] Lade natives Binary (einmalig pro Codespace, ~136 MB)..."
  timeout 600 "$WRAPPER" --version >/dev/null 2>&1 || true
fi
cleanup_partial_downloads
patch_scroll_step
patch_arrow_scroll
patch_word_boundary
patch_history_delete
verify_after_patch

if [ -s "${NATIVE_DIR}/credentials.json" ]; then
  echo "[freebuff] Login aus Secrets-Bundle vorhanden."
else
  echo "[freebuff] KEIN Login: einmalig 'freebuff login' (Browser-URL), dann ./infra/scripts/secrets.sh lock"
fi
echo "[freebuff] OK v$(installed_version). Start: cd <projekt> && freebuff"
