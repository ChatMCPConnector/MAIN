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

**Pfeiltasten und Mausrad:**
Das Mausrad kommt im Terminal (wenn Maus-Reporting aus ist) als Up/Down-Pfeile
an (`ESC[A`/`ESC[B`). In freebuff wird dieser Tastenbefehl bei leerem Prompt
durch den Patch `patch_arrow_scroll` in `infra/scripts/freebuff_patch.py`
direkt im Binary auf `onScrollUp` / `onScrollDown` umgeleitet (wie in opencode:
`messages_half_page_up: up`).

Dieser Filter fasst Pfeiltasten deshalb per Default **gar nicht** an: sie gehen
100% nativ mit 0 ms Latenz an das Kind durch, und der Wheel-Umhang sitzt im
Binary-Patch. Genau dieser Patch wird bei **jedem Start** von freebuff
verifiziert und notfalls neu gesetzt (`freebuff_patch.py --ensure` aus dem
Wrapper) — weil der npm-Launcher das native Binary bei jedem Update ersetzt und
es damit mitloescht. Details und Bedienung: `freebuff_patch.py`.

Menues (`/history`, Slash-Menue `/...`, Model-Picker) fangen die Pfeiltasten
vor dieser Aktion ab und bleiben damit **vollstaendig nativ bedienbar**.

**Wort-Navigation und Wort-Loeschung:**
Freebuff (opentui) unterstuetzt intern Alt/Option+Links/Rechts (word-backward/forward)
und Ctrl+W (delete-word-backward). Standard-Terminals (insb. xterm.js / VS Code)
senden bei Strg+Links ESC[1;5D, bei Strg+Rechts ESC[1;5C und bei Strg+Backspace \x08.
Der Filter uebersetzt diese Sequenzen transparent:
  * Strg + Links (ESC[1;5D, ESC[5D)   -> Alt + Links (ESC[1;3D)  [Wort zurueck]
  * Strg + Rechts (ESC[1;5C, ESC[5C)  -> Alt + Rechts (ESC[1;3C) [Wort vor]
  * Strg + Backspace (\x08, CSI u)    -> Ctrl+W (\x17)           [Wort loeschen]
  * Strg + Delete (ESC[3;5~)          -> Alt + Delete (ESC[3;3~) [Wort vorwaerts loeschen]

Schalter: `FREEBUFF_ARROW_PAGE=1` = Pauschal-Umleitung aller Pfeile auf
PageUp/PageDown (nur fuer Diagnose/Notausgang). Default: nativ (`off`).

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


CONTROL_RE = re.compile(
    rb"\x1b\[[0-9;?]*[ -/]*[@-~]"
    rb"|\x1b[\]P][^\x07\x1b]*[\x07\x1b\x5c]"
    rb"|[\x00-\x1f\x7f]"
)


def summarize(data):
    """Nur Steuer-/Esc-Sequenzen fuer die Diagnose, NIEMALS getippten Text.

    Der Log soll beweisen, welche Taste angekommen ist — nicht den Inhalt
    speichern. Alles Druckbare wird deshalb zu Laengenangaben zusammengefasst.
    """
    parts = []
    pos = 0
    for m in CONTROL_RE.finditer(data):
        if m.start() > pos:
            parts.append(f"<{m.start() - pos}B text>")
        chunk = m.group()
        if chunk in (b"\r", b"\n"):
            parts.append("ENTER")
        elif chunk == b"\x08":
            parts.append("BS")
        elif chunk == b"\x17":
            parts.append("CTRL+W")
        elif chunk == b"\x7f":
            parts.append("DEL")
        else:
            parts.append(chunk.decode("latin1", "replace").replace("\x1b", "ESC"))
        pos = m.end()
    if pos < len(data):
        parts.append(f"<{len(data) - pos}B text>")
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


# Pfeil rechts/links bleiben bei einfacher Pfeil-Navigation unangetastet;
# nur hoch/runter werden fuer PageUp/Down geprueft.
ARROW_PAGE = {
    b"\x1b[A": b"\x1b[5~",   # up    -> PageUp
    b"\x1b[B": b"\x1b[6~",   # down  -> PageDown
    b"\x1bOA": b"\x1b[5~",   # up    (SS3, Application-Modus)
    b"\x1bOB": b"\x1b[6~",   # down  (SS3)
}

# Wort-Navigation und Wort-Loeschung (Strg+Links / Strg+Rechts / Strg+Backspace):
# Freebuff (opentui) unterstuetzt intern Alt/Option+Links/Rechts (word-backward/forward)
# und Ctrl+W / Alt+Backspace (delete-word-backward).
# Terminals (insb. xterm.js / VS Code) senden bei Strg+Links ESC[1;5D,
# bei Strg+Rechts ESC[1;5C und bei Strg+Backspace \x08 (ASCII BS).
WORD_KEYS = {
    # Strg + Pfeil links -> Option/Alt + Links (freebuff: word-backward)
    b"\x1b[1;5D": b"\x1b[1;3D",
    b"\x1b[5D": b"\x1b[1;3D",
    b"\x1b[1;6D": b"\x1b[1;3D",
    # Strg + Pfeil rechts -> Option/Alt + Rechts (freebuff: word-forward)
    b"\x1b[1;5C": b"\x1b[1;3C",
    b"\x1b[5C": b"\x1b[1;3C",
    b"\x1b[1;6C": b"\x1b[1;3C",
    # Strg + Backspace -> Ctrl+W (\x17, freebuff: delete-word-backward)
    b"\x08": b"\x17",
    b"\x1b[127;5u": b"\x17",
    b"\x1b[27;5;127~": b"\x17",
    b"\x1b[27;5;8~": b"\x17",
    b"\x1b[8;5~": b"\x17",
    b"\x1b\x08": b"\x17",
    # Strg + Delete -> Option + Delete (freebuff: delete-word-forward)
    b"\x1b[3;5~": b"\x1b[3;3~",
}

WORD_KEY_RE = re.compile(
    rb"|".join(re.escape(k) for k in sorted(WORD_KEYS, key=len, reverse=True))
)


def rewrite_word_keys(data):
    """Uebersetzt Strg+Links/Rechts und Strg+Backspace in opentui-kompatible Sequenzen."""
    if not data:
        return data
    return WORD_KEY_RE.sub(lambda m: WORD_KEYS[m.group()], data)


# Eine Escape-Sequenz darf ueber zwei Reads zerrissen werden; das letzte
# unvollstaendige Praefix wird zurueckgehalten und mit dem naechsten Read
# zusammengesetzt.
_full_seqs = list(ARROW_PAGE.keys()) + list(WORD_KEYS.keys())
_prefixes = set()
for _seq in _full_seqs:
    for _i in range(1, len(_seq)):
        _prefixes.add(_seq[:_i])
PARTIAL_PREFIXES = tuple(sorted(_prefixes, key=len, reverse=True))

# Default 25 ms: Reserve-Konstante fuer timing-basierte Steuerung.
DEFAULT_WHEEL_GAP_MS = 25.0

ESC_SEQ_RE = re.compile(
    rb"\x1b\[[0-9;?]*[ -/]*[@-~]"
    rb"|\x1bO[@-~]"
    rb"|\x1b[\]P][^\x07\x1b]*[\x07\x1b\x5c]"
    rb"|\x1b[ -/]*[@-~]"
)


# Modale Screens (/history, /chats, /model)
HISTORY_MODAL_OPEN_PATTERNS = (
    b"Select a chat to resume",
    b"Search chats...",
    b"choose model",
)

# Agenten-Fragen (ask_user) mit 1 bis N Fragen
# Box-Titel " Some questions for you ", Schliessen-Knopf "Close ✕",
# unexpandierte Folgefragen "(click to answer)", Custom-Option oder Mehrfachauswahl.
# Bewusst OHNE unqualifiziertes "Enter select" oder "↑↓ navigate" — diese Strings gibt Freebuff
# auch im Model-Picker (/model), Slash-Menue und Footer aus; ein Match wuerde
# question_modal dauerhaft einrasten lassen, weil Enter es nicht schliesst.
QUESTION_MODAL_OPEN_PATTERNS = (
    b"questions for you",
    b"Close \xe2\x9c\x95",
    b"(click to answer)",
    b"Type your own answer",
    b"Select multiple options",
    b"Type your answer...",
)

# Abschluss aller Fragen (qVA in freebuff)
QUESTION_MODAL_CLOSE_PATTERNS = (
    b"Your answer:",
    b"Your answers:",
    b"You skipped the",
    b"User answered:",
    b"User skipped",
)


def track_input(data, text="", history_modal=False, question_modal=False):
    """Verfolgt den Inhalt der aktuellen freebuff-Eingabezeile und Modal-Status.

    1. Slash-Menue: Eingabe beginnt mit '/'
    2. History/Model-Screens: Enter/Escape schliesst
    3. Agenten-Fragen (1..N Fragen): Enter schliesst NICHT (wechselt zur naechsten Frage),
       erst QUESTION_MODAL_CLOSE_PATTERNS oder Escape/Ctrl+C schliessen die Fragen.
    """
    buf = bytearray(text.encode("utf-8", "replace") if text else b"")
    clean = ESC_SEQ_RE.sub(b"", data)
    for byte in clean:
        if byte in (0x0D, 0x0A):  # Enter
            current = buf.decode("utf-8", "replace").strip()
            if current in ("/history", "/chats", "/model"):
                history_modal = True
            else:
                history_modal = False
            # WICHTIG: question_modal wird durch Enter NICHT geschlossen!
            # Bei Multi-Fragen springt Enter von Frage 1 zu Frage 2, 3...
            # question_modal schliesst erst wenn freebuff QUESTION_MODAL_CLOSE_PATTERNS
            # ausgibt oder der Nutzer Escape/Ctrl+C drueckt.
            buf = bytearray()
        elif byte in (0x03, 0x15):  # Ctrl+C oder Ctrl+U
            buf = bytearray()
            history_modal = False
            question_modal = False
        elif byte == 0x1B:  # Bare Escape
            if buf and buf[0:1] == b"/":
                buf = bytearray()
            history_modal = False
            question_modal = False
        elif byte in (0x7F, 0x08):  # Backspace
            if buf:
                del buf[-1]
        elif byte == 0x17:  # Ctrl+W / Ctrl+Backspace (Wort loeschen)
            s = bool(buf and buf[-1:] in b" \t\r\n")
            while buf and (buf[-1:] in b" \t\r\n") == s:
                del buf[-1]
        elif byte >= 0x20:
            buf.append(byte)
        if len(buf) > 512:
            del buf[:-512]
    return buf.decode("utf-8", "replace"), history_modal, question_modal


def new_arrow_state():
    """Dummy-State fuer Rueckwaertskompatibilitaet."""
    return {seq: {"burst_until": 0.0} for seq in ARROW_PAGE}


def _page(seq, now, last_page, debounce):
    """PageUp/PageDown fuer ein Rad-Ereignis, optional ratenbegrenzt."""
    if debounce > 0 and now - last_page[seq] < debounce:
        return b""
    last_page[seq] = now
    return ARROW_PAGE[seq]


def rewrite_arrows(data, carry=b"", now=0.0, state=None, gap=0.025, debounce=0.0,
                   last_page=None, always=False, text="", history_modal=False,
                   question_modal=False):
    """Pfeiltasten im Chat -> IMMER PageUp/PageDown (1:1 Replikation).

    In Menues ('/...', /history, /model, Agenten-Fragen 1..N) -> NATIV (0 ms Latenz).

    Grund:
      * Im Chatfenster (egal ob leer oder waehrend man tippt) muessen
        Pfeiltasten 1:1 zu PageUp/PageDown werden: nur PageUp/Down scrollt
        das Unterhaltungsfenster in freebuff auch bei befuellter Eingabezeile,
        und beruehrt NIE den Schreibbanner.
      * In Menues (Slash-Menue '/', /history, Agenten-Fragen 1..N) muessen Pfeiltasten
        nativ bleiben, damit die Auswahl mit Pfeil hoch/runter bedienbar ist.
    """
    data = carry + data
    carry = b""
    for pref in sorted(PARTIAL_PREFIXES, key=len, reverse=True):
        if data.endswith(pref) and data != pref:
            carry = data[-len(pref):]
            data = data[: -len(pref):]
            break
    data = rewrite_word_keys(data)
    if state is None:
        state = new_arrow_state()
    if last_page is None:
        last_page = dict.fromkeys(ARROW_PAGE, -1e9)

    out = bytearray()
    if always:
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
        t, hm, qm = track_input(data, text, history_modal, question_modal)
        return bytes(out), carry, state, last_page, t, hm, qm

    matches = sorted(
        (m for seq in ARROW_PAGE for m in re.finditer(re.escape(seq), data)),
        key=lambda m: m.start(),
    )

    pos = 0
    for match in matches:
        if match.start() < pos:
            continue
        seq = match.group()
        before = data[pos:match.start()]
        text, history_modal, question_modal = track_input(before, text, history_modal, question_modal)
        out += before
        pos = match.end()

        in_menu = text.startswith("/") or history_modal or question_modal
        if in_menu:
            # Menues (/history, Slash-Menue, Model-Picker, Agenten-Fragen 1..N): Pfeile nativ
            out += seq
        else:
            # Unterhaltung scrollen: IMMER PageUp/PageDown (1:1 Replikation)
            out += _page(seq, now, last_page, debounce)

    remaining = data[pos:]
    text, history_modal, question_modal = track_input(remaining, text, history_modal, question_modal)
    out += remaining
    return bytes(out), carry, state, last_page, text, history_modal, question_modal


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
    # Pfeil-Umschreibung ist per Default AN:
    # 1. Im Chatfenster (egal ob leer oder waehrend man tippt) -> PageUp/Down.
    #    Damit scrollt das Mausrad IMMER das Unterhaltungsfenster und bewegt
    #    nie den Schreibbanner (1:1 Replikation von PageUp/PageDown).
    # 2. In Menues (Slash-Menue '/', /history Screen) -> NATIV.
    #    Damit lassen sich Menues und History mit Pfeiltasten bedienen.
    mode = os.environ.get("FREEBUFF_ARROW_PAGE", "auto")
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
    master_carry = b""
    text = ""
    history_modal = False
    question_modal = False
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
                chunk = master_carry + data
                if any(pat in chunk for pat in HISTORY_MODAL_OPEN_PATTERNS):
                    history_modal = True
                    master_carry = b""
                elif any(pat in chunk for pat in QUESTION_MODAL_OPEN_PATTERNS):
                    question_modal = True
                    master_carry = b""
                elif any(pat in chunk for pat in QUESTION_MODAL_CLOSE_PATTERNS):
                    question_modal = False
                    master_carry = b""
                else:
                    master_carry = data[-32:]
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
                        data, carry, arrow_state, last_page, text, history_modal, question_modal = rewrite_arrows(
                            data, carry, time.monotonic(), arrow_state, gap,
                            debounce, last_page, always=always_page, text=text,
                            history_modal=history_modal, question_modal=question_modal)
                    else:
                        data = carry + data
                        carry = b""
                        for pref in sorted(PARTIAL_PREFIXES, key=len, reverse=True):
                            if data.endswith(pref) and data != pref:
                                carry = data[-len(pref):]
                                data = data[: -len(pref):]
                                break
                        data = rewrite_word_keys(data)
                        text, history_modal, question_modal = track_input(
                            data, text, history_modal, question_modal)
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
