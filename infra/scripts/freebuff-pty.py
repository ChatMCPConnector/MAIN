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

Deshalb der **Read-Zaehler** statt eines pauschalen Umschreibens:

* **einzelnes** `up`/`down` in einem Read (Tastatur) -> unveraendert an die
  App, **sofort, ohne Verzoegerung**. Sie bewegt die Auswahl im Slash-Menue.
* **>=2 gleiche** in einem Read (Mausrad) -> PageUp/PageDown, der Chat scrollt.
* `burst_until` ueberbrueckt den Fall, dass ein Rad-Schwung ueber mehrere Reads
  geht: nach einer erkannten Geste zaehlt auch ein einzelner Pfeil im naechsten
  Read als Geste, solange die Pause kuerzer als ~120 ms ist.

Kein Pending, kein Hold, kein Timeout, kein Flush. Der einzelne Tastendruck
kommt **sofort** durch — das war der Bug im alten Code, der das Slash-Menue
blockiert hat (25 ms Zurueckhalten war offenbar genug, damit freebuffs TUI den
Pfeil nicht sah).
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
# Tastenwiederholungs-Takt (Browser ~33 ms ab 500 ms Haltezeit). Wird nur fuer
# burst_until-Berechnung genutzt (gap*4 = 100 ms, min 120 ms).
DEFAULT_WHEEL_GAP_MS = 25.0


def new_arrow_state():
    """Je Eingangssequenz: letzter Zeitpunkt + Ende der Burst-Phase."""
    return {seq: {"last_seen": 0.0, "burst_until": 0.0} for seq in ARROW_PAGE}


def _page(seq, now, last_page, debounce):
    """PageUp/PageDown fuer ein Rad-Ereignis, optional ratenbegrenzt."""
    if debounce > 0 and now - last_page[seq] < debounce:
        return b""
    last_page[seq] = now
    return ARROW_PAGE[seq]


def rewrite_arrows(data, carry=b"", now=0.0, state=None, gap=0.025, debounce=0.0,
                   last_page=None, always=False):
    """Pfeiltasten sofort nativ, Rad-Gesten werden PageUp/PageDown.

    **Hybrid-Erkennung** — kein Delay, kein Pending:

      1. **Im selben Read >=2 gleiche Pfeile:** Mausrad liefert viele Events in
         einem read(). Alle werden sofort zu PageUp/PageDown.
      2. **Ueber Reads hinweg:** Erster Pfeil geht sofort nativ durch, aber
         wir merken den Zeitpunkt (`last_seen`). Kommt der naechste gleiche
         Pfeil innerhalb `gap` Sekunden, wechseln wir in den Geste-Modus
         (`burst_until`) und senden PageUp/PageDown.
      3. **Einzelner Pfeil (keine Wiederholung in gap):** Nativ, sofort, null
         Verzoegerung. Genau das braucht das Slash-Menue.
      4. `links`/`rechts` werden nie angefasst (nicht in `ARROW_PAGE`).

    **Preis:** Das allererste Rad-Event pro Schwung geht als nativer Pfeil
    durch (history-up). Ab dem zweiten Event (< gap spaeter) kommen alle als
    PageUp/PageDown. Bei einem typischen Schwung mit 10-30 Events ist das
    unmerklich.

    `always=True` schickt jeden Pfeil als Seite (FREEBUFF_ARROW_PAGE=1).

    Gibt (neue_daten, rest, state, last_page) zurueck.
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
        return bytes(out), carry, state, last_page

    # --- Zaehlen, welche Pfeile wie oft in diesem Read vorkommen ---
    matches = sorted(
        (m for seq in ARROW_PAGE for m in re.finditer(re.escape(seq), data)),
        key=lambda m: m.start(),
    )
    # Zaehler je Sequenz (nur in DIESEM Read).
    count = {}
    for m in matches:
        seq = m.group()
        count[seq] = count.get(seq, 0) + 1

    pos = 0
    for match in matches:
        if match.start() < pos:
            continue
        seq = match.group()
        out += data[pos:match.start()]
        pos = match.end()

        st = state[seq]

        # Geste? Drei Wege:
        # (a) burst_until noch aktiv (mitten im Rad-Schwung)
        # (b) >=2 gleiche im selben Read (Rad liefert viele auf einmal)
        # (c) letzter gleicher Pfeil < gap Sekunden her (Rad ueber Reads)
        in_burst = st["burst_until"] > now
        multi_in_read = count.get(seq, 0) >= 2
        rapid_repeat = (now - st["last_seen"]) < gap and st["last_seen"] > 0

        if in_burst or multi_in_read or rapid_repeat:
            # Geste: PageUp/PageDown, burst verlaengern
            st["burst_until"] = now + max(gap * 4, 0.12)
            out += _page(seq, now, last_page, debounce)
        else:
            # Einzelner Tastendruck: sofort nativ
            out += seq

        st["last_seen"] = now

    out += data[pos:]
    return bytes(out), carry, state, last_page


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
    debug(f"arrow_page={arrow_page} always_page={always_page} gap={gap}s debounce={debounce}s")
    try:
        while True:
            if resize_requested:
                resize_requested = False
                set_window_size(master, *window_size(0))

            watch = [master] + ([0] if stdin_open else [])
            try:
                ready, _, _ = select.select(watch, [], [], 1.0)
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
                        data, carry, arrow_state, last_page = rewrite_arrows(
                            data, carry, time.monotonic(), arrow_state, gap,
                            debounce, last_page, always=always_page)
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
