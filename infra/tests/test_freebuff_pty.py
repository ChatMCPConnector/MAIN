"""Tests fuer infra/scripts/freebuff-pty.py (PTY-Filter & Keybinding-Relay).

Verifiziert:
  1. Modale Erkennung: Model-Picker und Menues duerfen NICHT question_modal ausloesen.
  2. question_modal oeffnet nur bei echten Fragen und schliesst bei Abschluss.
  3. Pfeiltasten-Umschreibung (PageUp/PageDown im Chat, nativ in Menues).
  4. Wort-Navigation (Ctrl+Links/Rechts, Ctrl+Backspace/Delete).
"""

import importlib.util
import pathlib

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "freebuff-pty.py"


def _load():
    spec = importlib.util.spec_from_file_location("freebuff_pty", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pty = _load()


def test_model_picker_does_not_trigger_question_modal():
    footer = b"\xe2\x86\x91\xe2\x86\x93 choose model \xc2\xb7 Tab reasoning \xc2\xb7 Enter select \xc2\xb7 Esc cancel"
    assert any(pat in footer for pat in pty.HISTORY_MODAL_OPEN_PATTERNS)
    assert not any(pat in footer for pat in pty.QUESTION_MODAL_OPEN_PATTERNS)


def test_slash_menu_footer_does_not_trigger_question_modal():
    footer = b"\xe2\x86\x91\xe2\x86\x93 navigate \xe2\x80\xa2 Enter select"
    assert not any(pat in footer for pat in pty.QUESTION_MODAL_OPEN_PATTERNS)


def test_question_modal_open_patterns():
    for text in [
        b" Some questions for you ",
        b"Close \xe2\x9c\x95",
        b"(click to answer)",
        b"Type your own answer",
        b"Select multiple options",
        b"Type your answer...",
    ]:
        assert any(pat in text for pat in pty.QUESTION_MODAL_OPEN_PATTERNS)


def test_question_modal_close_patterns():
    for text in [
        b"Your answer: Option 1",
        b"Your answers: Option A, Option B",
        b"You skipped the question.",
        b"User answered: Yes",
        b"User skipped question",
    ]:
        assert any(pat in text for pat in pty.QUESTION_MODAL_CLOSE_PATTERNS)


def test_track_input_history_and_model_modal():
    # Slash modal
    text, hm, qm = pty.track_input(b"/model\r")
    assert text == ""
    assert hm is True
    assert qm is False

    # Enter inside modal closes history_modal
    text, hm, qm = pty.track_input(b"\r", history_modal=hm, question_modal=qm)
    assert hm is False
    assert qm is False


def test_track_input_escape_and_ctrl_c():
    _, hm, qm = pty.track_input(b"\x1b", history_modal=True, question_modal=True)
    assert hm is False
    assert qm is False

    _, hm, qm = pty.track_input(b"\x03", history_modal=True, question_modal=True)
    assert hm is False
    assert qm is False


def test_rewrite_arrows_chat_mode():
    # Im normalen Chat (auch mit getipptem Text): Up/Down -> PageUp/PageDown
    data, _, _, _, _, _, _ = pty.rewrite_arrows(b"\x1b[A\x1b[B", text="schreibe code")
    assert data == b"\x1b[5~\x1b[6~"


def test_rewrite_arrows_in_menu():
    # Im Slash-Menue (text beginnt mit /): Pfeile bleiben nativ
    data, _, _, _, _, _, _ = pty.rewrite_arrows(b"\x1b[A\x1b[B", text="/")
    assert data == b"\x1b[A\x1b[B"

    # In history modal: Pfeile bleiben nativ
    data, _, _, _, _, _, _ = pty.rewrite_arrows(b"\x1b[A\x1b[B", history_modal=True)
    assert data == b"\x1b[A\x1b[B"

    # In question modal: Pfeile bleiben nativ
    data, _, _, _, _, _, _ = pty.rewrite_arrows(b"\x1b[A\x1b[B", question_modal=True)
    assert data == b"\x1b[A\x1b[B"


def test_rewrite_word_keys():
    assert pty.rewrite_word_keys(b"\x1b[1;5D") == b"\x1b[1;3D"  # Ctrl+Left -> Alt+Left
    assert pty.rewrite_word_keys(b"\x1b[1;5C") == b"\x1b[1;3C"  # Ctrl+Right -> Alt+Right
    assert pty.rewrite_word_keys(b"\x08") == b"\x17"            # Ctrl+Backspace -> Ctrl+W
    assert pty.rewrite_word_keys(b"\x1b[3;5~") == b"\x1b[3;3~"  # Ctrl+Delete -> Alt+Delete
