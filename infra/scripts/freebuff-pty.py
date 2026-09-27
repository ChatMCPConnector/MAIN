#!/usr/bin/env python3
"""freebuff-pty.py: pty-Relay, das Maus-Tracking aus dem TUI-Output entfernt.

Problem: Freebuff (opentui) schaltet beim Start Mouse-Reporting ein
(CSI ? 1000/1002/1003/1006/1015/1016 h). Danach behandelt das Terminal
Mausereignisse als App-Eingaben — die native Textauswahl ist tot: nichts
markieren, nichts kopieren. Bei opencode ist das per Config gelöst
(`.opencode/tui.json`: `mouse: false`); Freebuff hat **keinen** solchen Kniff:
weder `settings.json`-Key, noch CLI-Flag, noch Env-Variable (am Binary 0.0.204
verifiziert — opentui kennt `useMouse`, Default `true`, Freebuff setzt es nicht).
Deshalb dieser Filter: das Programm läuft auf einem pty, wir geben seinen Output
an das echte Terminal weiter — nur ohne die Maus-Sequenzen. Der Terminal steht
damit im selben Zustand wie bei opencode mit `mouse: false`.

**Pfeiltasten und Mausrad kommen als dieselben Bytes an — der Unterschied ist
der Takt.** Nach dem Abschalten des Maus-Reportings schickt xterm.js das Rad als
`up`/`down` (`ESC[A`/`ESC[B`) an die App, und die Tastatur schickt bei
Tastendruck genau dieselben Bytes. Belegt im Key-Log (`/tmp/opencode/
freebuff-keys.log`, 13:20:17): ein Radschwung kam als **dutzende** Ereignisse
innerhalb einer Sekunde, ein Tastendruck als **einzelnes** Ereignis. Ohne diese
Trennung ist eine der beiden Bedienungen tot: ohne Umschreiben scrollt das Rad
nichts, mit Umschreiben bedienen die Pfeile das Slash-Menue nicht mehr
(Nutzerbefund mit Screenshot, 2026-09-27).

Deshalb der **Burst-Test** statt eines pauschalen Umschreibens:

* **einzelnes** `up`/`down` (Tastatur) -> unveraendert an die App, sie bewegt
  die Auswahl im Slash-Befahl-Menue,
* **Serie** gleicher Richtung innerhalb `FREEBUFF_WHEEL_GAP_MS` (Default 25 ms,
  das Mausrad) -> PageUp/PageDown, der Chat scrollt.

Das einzelne Ereignis wird dafuer hoechstens 25 ms zurueckgehalten — die
Latenz ist nicht spuerbar, und sie ist der ganze Preis der Trennung. 25 ms
liegen sicher unter dem Tastenwiederholungs-Takt (Browser ~33 ms ab 500 ms
Haltezeit) und sicher ueber dem Abstand zweier Rad-Ereignisse (sub-ms, im selben
Read). `FREEBUFF_WHEEL_GAP_MS` stellt den Wert, falls ein Setup anders taktet.
Nur die exakten Cursor-Sequenzen ohne Modifikator werden je Richtung geprueft;
`shift+up` (`ESC[1;2A`) und `ctrl+up` (`ESC[1;5A`) sind nie beteiligt und
werden nie verzoegert. Schalter: `FREEBUFF_ARROW_PAGE=1` = alte Pauschal-Umleitung
(alle Pfeile -> Seite), `FREEBUFF_NO_ARROW_PAGE=1` = gar keine Umschreibung
(Rad und Pfeile nativ, Menuesscrollen geht nicht).

Entfernt wird ausschliesslich Mause-Reporting:
    ESC [ ? <1000|1001|1002|1003|1005|1006|1015|1016> (h|l)
Bewusst BEIBEHALTEN, weil davon die Bedienung abhaengt:
    ?1004 Fokus-Reporting, ?2004 bracketed Paste (sonst kein Pasten),
    ?1049 Alternate Screen, ?9001/ Kitty-Keys, ?1016PIXEL nur ohne h/l.
Eingaben (inkl. Antworten auf Cursor-Position-Abfragen wie CSI 6n) gehen
unveraendert zum Kind; SIGWINCH wird auf den pty durchgereicht.

Nutzung: freebuff-pty.py -- <programm> [args...]
Exit-Code = Exit-Code des Kindes.

DEBUG: FREEBUFF_PTY_DEBUG=/pfad/debug.log schreibt mit, welche Steuer- und
Esc-Sequenzen vom Kind gelesen werden (das ist die Wirkung einer VS-Code-
Keybinding) und welche Maus-Sequenzen der Filter entfernt hat (Beweis, dass er im
Pfad ist). **Getippter Text wird bewusst nicht protokolliert**, nur seine
Byte-Laenge (`<12B text>`) — der Log ist eine Diagnose, kein Mitschnitt.
"""
import errno
import fcntl
import os
import pty
import re
import select
import signal
import struct
import sys
import termios
import time
import tty

# Nur Maus Modi. 1004 (Fokus) und 2004 (bracketed Paste) fehlen bewusst.
MOUSE_MODES = rb"(?:1000|1001|1002|1003|1005|1006|1015|1016)"
MOUSE_RE = re.compile(rb"\x1b\[\?" + MOUSE_MODES + rb"[hl]")


# "off"/"0"/leer = kein Log. Ohne diese Pruefung wuerde ein "off" als Dateiname
# im Arbeitsverzeichnis landen statt abzuschalten.
DEBUG_LOG = os.environ.get("FREEBUFF_PTY_DEBUG") or ""
if DEBUG_LOG.lower() in ("off", "0", "none", "false"):
    DEBUG_LOG = ""


def summarize(data):
    """Nur Steuer-/Esc-Sequenzen fuer die Diagnose, NIEMALS getippten Text.

    Der Log soll beweisen, welche Taste angekommen ist — nicht den Inhalt
    speichern. Alles Druckbare wird deshalb zu Laengenangaben zusammengefasst.
    """
    parts, buf = [], bytearray()
    for chunk in re.findall(rb"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[\]P][^\x07\x1b]*[\x07\x1b\\]|[\x00-\x1f\x7f]", data):
        if buf:
            parts.append(f"<{len(buf)}B text>")
            buf = bytearray()
        parts.append(chunk.decode("latin1").replace("\x1b", "ESC"))
    if buf:
        parts.append(f"<{len(buf)}B text>")
    return " ".join(parts) if parts else f"<{len(data)}B>"


def debug(msg):
    """Messkanal fuer die Keybinding-Frage: schreibt optional eine Zeile."""
    if not DEBUG_LOG:
        return
    try:
        with open(DEBUG_LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except OSError:
        pass


# Pfeil rechts/links bleiben unangetastet; nur hoch/runter werden geprueft.
ARROW_PAGE = {
    b"\x1b[A": b"\x1b[5~",   # up    -> PageUp
    b"\x1b[B": b"\x1b[6~",   # down  -> PageDown
    b"\x1bOA": b"\x1b[5~",   # up    (SS3, Application-Modus)
    b"\x1bOB": b"\x1b[6~",   # down  (SS3)
}
# Ein Escape-Sequenz darf ueber zwei Reads zerrissen werden; das letzte
# unvollstaendige Praefix wird zurueckgehalten und mit dem naechsten Read
# zusammengesetzt. Sonst wuerde ein geteilter Pfeil durchrutschen.
PARTIAL_PREFIXES = (b"\x1b", b"\x1b[", b"\x1bO")

# Default 25 ms: ueber dem Abstand zweier Rad-Ereignisse (sub-ms), unter dem
# Tastenwiederholungs-Takt (Browser ~33 ms ab 500 ms Haltezeit). Haelt man den
# Pfeil gedrueckt, bleibt die Wiederholung damit im Einzelfall-Modus.
DEFAULT_WHEEL_GAP_MS = 25.0


def new_arrow_state():
    """Je Eingangssequenz: wartendes Einzel-Ereignis + Ende der Burst-Phase."""
    return {seq: {"pending": None, "deadline": 0.0, "burst_until": 0.0} for seq in ARROW_PAGE}


def _page(seq, now, last_page, debounce):
    """PageUp/PageDown fuer ein Rad-Ereignis, optional ratenbegrenzt."""
    if debounce > 0 and now - last_page[seq] < debounce:
        return b""
    last_page[seq] = now
    return ARROW_PAGE[seq]


def flush_pending(state, now):
    """Wartende Einzel-Ereignisse ausgeben, deren Fenster abgelaufen ist.

    Ohne das wuerde ein einzelner Tastendruck (der nie wieder ein Read
    ausloest) nie beim Kind ankommen.
    """
    out = bytearray()
    for st in state.values():
        if st["pending"] is not None and now >= st["deadline"]:
            out += st["pending"]
            st["pending"] = None
    return bytes(out)


def pending_timeout(state, now, cap=1.0):
    """Sekunden bis zum naechsten faelligen Fenster, sonst `cap`."""
    waits = [st["deadline"] - now for st in state.values() if st["pending"] is not None]
    return max(0.0, min([cap] + waits))


# --- Eingabe-Zustand --------------------------------------------------------
# Ein einzelner Rad-Klick ist byte- und taktgleich zu einem einzelnen
# Tastendruck (im Key-Log belegt: Geste ~30 Ereignisse/s, Tastendruck 1). Der
# Filter kann die beiden nicht unterscheiden — ausser ueber den Zustand der
# Eingabe, den er selbst aus den Tastatur-Bytes mitzaehlt:
#   * Eingabe LEER  -> ein Pfeil wuerde bei freebuff `history-up` ausloesen, also
#     die Prompt-Historie zurueckrollen. Genau das soll das Rad nie. Also wird
#     der Pfeil sofort zur Seite (PageUp/PageDown) — ohne Burst-Fenster, also
#     auch ohne 25 ms Verzoegerung.
#   * Eingabe NICHT leer -> der Pfeil bleibt nativ: das Slash-Menue geht nur bei
#     getipptem "/" auf, und im Text sollen die Pfeile den Cursor bewegen.
# Der Preis, den der Nutzer akzeptiert hat: auf leerer Eingabe holt `up` nicht
# mehr die letzte Nachricht — dafuer gibt es `/history`.
ESC_SEQ_RE = re.compile(
    rb"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[\]P][^\x07\x1b]*(?:\x07|\x1b\\)"
    rb"|\x1b[()][0-9A-B]|\x1b[=>78]"
)


def track_input(data, typed):
    """Zeichen in der Eingabe, grob aus den weitergereichten Tastatur-Bytes.

    Escape-Sequenzen werden entfernt (der Text zwischen Bracketed-Paste-Markern
    zaehlt mit, die Marker selbst nicht), Enter setzt zurueck, Backspace zieht
    ab, Ctrl+U leert die Zeile. Mehrbyte-UTF-8 wird ueber die Fortsetzungsbytes
    (0x80-0xBF) auf ein Zeichen normalisiert.

    Wichtig: `0x7f`/`0x08` sind Backspace und **keine** druckbaren Zeichen — der
    erste Wurf behandelte sie als `>= 0x20` und zaehlte sie, sodass ein
    Backspace die Eingabe *laenger* machte. Der Test "Backspace zieht ab" hat
    das gefangen.
    """
    for byte in ESC_SEQ_RE.sub(b"", data):
        if byte in (0x0D, 0x0A):          # Enter: abgeschickt
            typed = 0
        elif byte == 0x15:                # Ctrl+U: Zeile loeschen
            typed = 0
        elif byte in (0x7F, 0x08):        # Backspace (xterm sendet 0x7f)
            typed = max(0, typed - 1)
        elif 0x80 <= byte <= 0xBF:        # UTF-8-Fortsetzung: kein neues Zeichen
            continue
        elif byte >= 0x20:                # druckbar (Backspace 0x7f ist abgefangen)
            typed += 1
    return typed


def rewrite_arrows(data, carry=b"", now=0.0, state=None, gap=0.025, debounce=0.0,
                   last_page=None, always=False, typed=0):
    """Rad-Burst -> PageUp/PageDown, einzelne Pfeiltaste bleibt nativ.

    Mausrad und Pfeiltaste erzeugen dieselben Bytes; unterschieden werden sie
    am Takt (Burst = Rad, Einzelereignis = Tastatur, siehe Modul-Docstring).
    Das erste Ereignis einer Serie wird dafuer hoechstens `gap` Sekunden
    zurueckgehalten: kommt bis dahin nichts Gleiches, geht es nativ an die App
    (Slash-Menue), kommt es, sind es Rad-Ereignisse und beide werden zu
    PageUp/PageDown.

    `debounce` (Sekunden, Default 0) begrenzt optional nur die Page-Ausgabe —
    es ist eine Ratenbegrenzung des Rads, keine Erkennung. `last_page` merkt
    sich je Richtung den Zeitpunkt der zuletzt gesendeten Seite; verworfene
    Ereignisse werden trotzdem konsumiert, sonst rueutscht der rohe Pfeil an
    der App vorbei.

    `always=True` schaltet den Burst-Test ab und schickt **jeden** Pfeil als
    Seite (Modus `FREEBUFF_ARROW_PAGE=1`, das alte Verhalten).

    `typed` ist die Zahl der Zeichen in der freebuff-Eingabe (siehe
    `track_input`) **vor** diesem Chunk, und wird hier pro Position im Chunk
    fortgeschrieben: bei `typed == 0` (Eingabe leer) geht jeder Pfeil sofort
    als Seite raus, denn ein Pfeil wuerde sonst `history-up` ausloesen und die
    Prompt-Historie zurueckrollen — das darf das Rad nie. Ist die Eingabe
    **nicht** leer, gilt der Burst-Test wie beschrieben, damit das Slash-Menue
    bedienbar bleibt.

    **Pro Position, nicht pro Chunk:** Tippen und Pfeil koennen im selben Read
    ankommen (schnelles Tippen, Paste gefolgt von Pfeil, trager Terminal).
    Wuerde der Zustand nur einmal je Chunk ausgewertet, kaeme ein Pfeil im
    selben Chunk wie das getipptes `/ne` als Seiten-Sprung an — der Test
    "Slash-Menue im selben Read" hat genau das gefangen.

    Gibt (neue_daten, rest, state, last_page, typed) zurueck.
    """
    data = carry + data
    carry = b""
    for pref in sorted(PARTIAL_PREFIXES, key=len, reverse=True):
        if data.endswith(pref) and data != pref:
            carry = data[-len(pref):]
            data = data[: -len(pref):]
            break
    if state is None:
        state = new_arrow_state()
    if last_page is None:
        last_page = dict.fromkeys(ARROW_PAGE, -1e9)

    out = bytearray()
    if always:
        # Alte Pauschal-Umleitung: jedes up/down wird Seite, ohne Fenster.
        pos = 0
        for match in sorted(
            (m for seq in ARROW_PAGE for m in re.finditer(re.escape(seq), data)),
            key=lambda m: m.start(),
        ):
            if match.start() < pos:
                continue
            seq = match.group()
            out += data[pos:match.start()]
            pos = match.end()
            out += _page(seq, now, last_page, debounce)
        out += data[pos:]
        return bytes(out), carry, state, last_page, track_input(data, typed)

    pos = 0
    for match in sorted(
        (m for seq in ARROW_PAGE for m in re.finditer(re.escape(seq), data)),
        key=lambda m: m.start(),
    ):
        if match.start() < pos:      # bereits von einer anderen Sequenz konsumiert
            continue
        seq = match.group()
        # Kontext bis zu diesem Pfeil: alles davor im selben Chunk mitzaehlen.
        typed = track_input(data[pos:match.start()], typed)
        out += data[pos:match.start()]
        pos = match.end()             # in JEDEM Fall konsumieren
        st = state[seq]
        if typed == 0:
            # Eingabe leer: Pfeil sofort zur Seite, ohne Fenster. Auch ein noch
            # wartendes Einzelereignis wird Seite, nicht nativ — sonst roellt
            # es beim Leeren der Eingabe doch noch die Historie zurueck.
            for other, ost in state.items():
                if ost["pending"] is not None:
                    out += _page(other, now, last_page, debounce)
                    ost["pending"] = None
                    ost["burst_until"] = 0.0
            out += _page(seq, now, last_page, debounce)
        elif st["burst_until"] > now:
            # Mitten im Rad-Schwung: sofort als Seite, ohne Fenster.
            out += _page(seq, now, last_page, debounce)
        elif st["pending"] is not None and now < st["deadline"]:
            # Zweites gleichgerichtetes Ereignis im Fenster -> Geste = Rad.
            # Beide Ereignisse zaehlen: das wartende (es war das erste der
            # Geste) und das aktuelle. Eins davon zu verschlucken hiesse, dass
            # jeder Rad-Schwung eine Zeile weniger scrollt.
            st["burst_until"] = now + max(gap * 4, 0.12)
            out += _page(seq, now, last_page, debounce)
            st["pending"] = None
            out += _page(seq, now, last_page, debounce)
        else:
            # Fenster vorbei: ein Althertum wartet noch, den nativ durchlassen.
            out += flush_pending(state, now)
            st["pending"] = seq
            st["deadline"] = now + gap
    typed = track_input(data[pos:], typed)
    out += data[pos:]
    out += flush_pending(state, now)
    return bytes(out), carry, state, last_page, typed


def window_size(fd):
    """(rows, cols) des Terminals hinter fd; Default 24x80."""
    try:
        packed = fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\0" * 8)
        rows, cols = struct.unpack("HHHH", packed)[:2]
        return (rows or 24, cols or 80)
    except OSError:
        return 24, 80


def set_window_size(fd, rows, cols):
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    except OSError:
        pass


def main(argv):
    argv = argv[1:]
    if argv and argv[0] == "--":
        argv = argv[1:]
    if not argv:
        print("Aufruf: freebuff-pty.py -- <programm> [args...]", file=sys.stderr)
        return 2

    saved = None
    if os.isatty(0):
        try:
            saved = termios.tcgetattr(0)
            # Roh wie ein TUI es erwartet: kein Echo, kein Zeilenpuffer, kein
            # Signal-Zeichen (Ctrl+C muss als ^C an das Kind gehen).
            tty.setraw(0, termios.TCSANOW)
        except termios.error:
            saved = None

    try:
        pid, master = pty.fork()
    except OSError as exc:
        restore(saved)
        print(f"freebuff-pty: pty.fork() fehlgeschlagen: {exc}", file=sys.stderr)
        return 1

    if pid == 0:
        # Kind: leitet die bisherigen Argumente durch. pty.fork() hat slave
        # schon als stdin/stdout/stderr und als kontrollierendes Terminal.
        try:
            os.execvp(argv[0], argv)
        except OSError as exc:
            os.write(2, f"freebuff-pty: {argv[0]}: {exc}\n".encode())
        os._exit(127)

    # Eltern: Fenstergroesse uebernehmen, Resize verdrahten.
    set_window_size(master, *window_size(0))
    resize_requested = False

    def on_winch(_signum, _frame):
        nonlocal resize_requested
        resize_requested = True

    try:
        signal.signal(signal.SIGWINCH, on_winch)
    except (OSError, ValueError):
        pass

    debug(f"start argv={argv} pty={master}")
    out = sys.stdout.buffer
    stdin_open = True
    # Drei Betriebsarten (2026-09-27), weil Mausrad und Pfeiltaste dieselben
    # Bytes erzeugen und nur am Takt zu unterscheiden sind:
    #   Default            Burst-Test: Rad -> Seite, einzelne Pfeiltaste nativ
    #   ARROW_PAGE=1       alte Pauschal-Umleitung: jeder Pfeil -> Seite
    #   NO_ARROW_PAGE=1    gar nicht umschreiben (Rad scrollt dann nichts)
    mode = os.environ.get("FREEBUFF_ARROW_PAGE", "burst")
    if os.environ.get("FREEBUFF_NO_ARROW_PAGE", "0") == "1":
        mode = "off"
    arrow_page = mode != "off"
    always_page = mode == "1"
    try:
        gap = max(0.0, float(os.environ.get("FREEBUFF_WHEEL_GAP_MS", DEFAULT_WHEEL_GAP_MS))) / 1000.0
    except ValueError:
        gap = DEFAULT_WHEEL_GAP_MS / 1000.0
    # Default 0 = KEINE Drosselung. Der Nutzerwunsch lautete ausdruecklich
    # „0 ms, aber weniger Zeilen pro Schritt“ — die Drosselung war der falsche
    # Hebel (sie begrenzt die Rate, nicht die Schrittweite) und ist per
    # FREEBUFF_WHEEL_DEBOUNCE_MS weiterhin stellbar, falls jemand sie braucht.
    try:
        debounce = max(0.0, float(os.environ.get("FREEBUFF_WHEEL_DEBOUNCE_MS", "0")) / 1000.0)
    except ValueError:
        debounce = 0.0
    carry = b""
    arrow_state = new_arrow_state()
    last_page = dict.fromkeys(ARROW_PAGE, -1e9)
    typed = 0   # Zeichen in der freebuff-Eingabe, aus den Tastatur-Bytes gezaehlt
    debug(f"arrow_page={arrow_page} always_page={always_page} gap={gap}s debounce={debounce}s")
    try:
        while True:
            if resize_requested:
                resize_requested = False
                set_window_size(master, *window_size(0))

            watch = [master] + ([0] if stdin_open else [])
            # Select-Darf nicht laenger warten als das Burst-Fenster, sonst
            # bliebe ein einzelner Tastendruck bis zum naechsten Event liegen.
            timeout = pending_timeout(arrow_state, time.monotonic()) if arrow_page and not always_page else 1.0
            try:
                ready, _, _ = select.select(watch, [], [], timeout)
            except InterruptedError:
                continue
            except OSError as exc:
                if exc.errno == errno.EINTR:
                    continue
                raise

            if master in ready:
                try:
                    data = os.read(master, 65536)
                except OSError as exc:
                    # EIO: Kind ist weg (Linux meldet das so beim letzten Read).
                    if exc.errno == errno.EIO:
                        break
                    if exc.errno == errno.EINTR:
                        continue
                    break
                if not data:
                    break
                stripped = MOUSE_RE.findall(data)
                if stripped:
                    debug(f" Maus entfernt: {[m.decode('latin1') for m in stripped]}")
                out.write(MOUSE_RE.sub(b"", data))
                out.flush()

            if 0 in ready:
                try:
                    data = os.read(0, 65536)
                except OSError:
                    stdin_open = False
                    data = b""
                if data:
                    # Das ist die Sicht auf die Tastatur-Kette: was hier landet,
                    # hat das Kind als Tastendruck gelesen.
                    if arrow_page:
                        data, carry, arrow_state, last_page, typed = rewrite_arrows(
                            data, carry, time.monotonic(), arrow_state, gap,
                            debounce, last_page, always=always_page, typed=typed)
                    else:
                        typed = track_input(data, typed)
                    if not data:
                        continue
                    debug(f" -> {summarize(data)}")
                    try:
                        os.write(master, data)
                    except OSError:
                        stdin_open = False
                else:
                    # EOF auf stdin (z.B. `freebuff < /dev/null`): Kind soll das
                    # sehen, aber wir lesen nicht weiter.
                    stdin_open = False

            if arrow_page and not always_page and typed > 0:
                # Wartenden Einzelpfeil ausgeben, auch wenn kein Read kam. Bei
                # leerer Eingabe gibt es nichts auszugeben: dort wird ein Pfeil
                # sofort zur Seite und es wartet nie etwas.
                data = flush_pending(arrow_state, time.monotonic())
                if data:
                    debug(f" -> {summarize(data)} (Fenster abgelaufen)")
                    try:
                        os.write(master, data)
                    except OSError:
                        stdin_open = False
    finally:
        # Rest einer ueber zwei Reads zerrissenen Sequenz noch abgeben.
        if carry:
            try:
                os.write(master, carry)
            except OSError:
                pass
        try:
            os.close(master)
        except OSError:
            pass
        restore(saved)

    _, status = os.waitpid(pid, 0)
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    if os.WIFSIGNALED(status):
        # 128 + Signal, wie es eine Shell meldet.
        return 128 + os.WTERMSIG(status)
    return 1


def restore(saved):
    if saved is not None:
        try:
            termios.tcsetattr(0, termios.TCSADRAIN, saved)
        except termios.error:
            pass


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except KeyboardInterrupt:
        sys.exit(130)
