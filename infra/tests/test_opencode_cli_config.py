"""Paritaet zwischen v1 `.opencode/tui.json` und v2 `config/opencode-cli.json`.

Die Keybind-Namen sind zwischen beiden Generationen umbenannt. Dieser Test
verhindert, dass eine Seite geaendert wird und die andere still zurueckbleibt.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TUI_V1 = ROOT / ".opencode/tui.json"
CLI_V2 = ROOT / "config/opencode-cli.json"

KEYBIND_MAP = {
    "messages_page_up": "session.page.up",
    "messages_page_down": "session.page.down",
    "messages_half_page_up": "session.half.page.up",
    "messages_half_page_down": "session.half.page.down",
    "messages_line_up": "session.line.up",
    "messages_line_down": "session.line.down",
    "history_previous": "prompt.history.previous",
    "history_next": "prompt.history.next",
    "variant_cycle": "variant.cycle",
    "input_move_up": "input.move.up",
    "input_move_down": "input.move.down",
    "session_parent": "session.parent",
}


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def test_v2_cli_config_has_expected_shape() -> None:
    cli = load(CLI_V2)
    assert cli["$schema"] == "https://opencode.ai/v2/cli.json"
    assert cli["mouse"] is False
    assert cli["prompt"]["image_preview"] is True
    assert cli["session"]["image_preview"] is True
    assert set(cli["keybinds"]) == set(KEYBIND_MAP.values())


def test_keybinds_match_v1_tui_config() -> None:
    tui = load(TUI_V1)
    cli = load(CLI_V2)
    assert tui["mouse"] == cli["mouse"]
    for old_name, new_name in KEYBIND_MAP.items():
        assert tui["keybinds"][old_name] == cli["keybinds"][new_name], old_name
