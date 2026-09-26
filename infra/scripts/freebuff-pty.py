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

Entfernt wird ausschliesslich Mause-Reporting:
    ESC [ ? <1000|1001|1002|1003|1005|1006|1015|1016> (h|l)
Bewusst BEIBEHALTEN, weil davon die Bedienung abhaengt:
    ?1004 Fokus-Reporting, ?2004 bracketed Paste (sonst kein Pasten),
    ?1049 Alternate Screen, ?9001/ Kitty-Keys, ?1016PIXEL nur ohne h/l.
Eingaben (inkl. Antworten auf Cursor-Position-Abfragen wie CSI 6n) gehen
unveraendert zum Kind; SIGWINCH wird auf den pty durchgereicht.

Nutzung: freebuff-pty.py -- <programm> [args...]
Exit-Code = Exit-Code des Kindes.
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
import tty

# Nur Maus Modi. 1004 (Fokus) und 2004 (bracketed Paste) fehlen bewusst.
MOUSE_MODES = rb"(?:1000|1001|1002|1003|1005|1006|1015|1016)"
MOUSE_RE = re.compile(rb"\x1b\[\?" + MOUSE_MODES + rb"[hl]")


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

    out = sys.stdout.buffer
    stdin_open = True
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
                out.write(MOUSE_RE.sub(b"", data))
                out.flush()

            if 0 in ready:
                try:
                    data = os.read(0, 65536)
                except OSError:
                    stdin_open = False
                    data = b""
                if data:
                    try:
                        os.write(master, data)
                    except OSError:
                        stdin_open = False
                else:
                    # EOF auf stdin (z.B. `freebuff < /dev/null`): Kind soll das
                    # sehen, aber wir lesen nicht weiter.
                    stdin_open = False
    finally:
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
