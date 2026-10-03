"""B-02 (live 2026-10-03, `ses_efd86ec2…`): glm-5.3 nennt als `open`-ziel
seine EIGENEN scratchpad-/web-search-referenzen (`turn0bash1`, `turn0view0`,
`turn0search1`, `turnbash0`, `turn4fetch0`). Die sind weder pfad noch URL;
hinter ihnen liegt hier nichts. Vorher fielen sie unter dieselbe generische
meldung wie ein echter fehlaufruf, und das modell wiederholte sie bis zum
abbruch. Diese tests halten die eigene kategorie und die eigene notice fest.
"""

import json

from glm2api.services.glm_client import _internal_reference_notice_text
from glm2api.services.translator import (
    GLMEventAccumulator,
    extract_native_open_target,
    is_internal_reference_target,
    map_native_open_tool_call,
)

TARGET = "/workspaces/MAIN/glm2api"


# --- Erkennung ------------------------------------------------------------


def test_turn_referenzen_werden_erkannt():
    for target in (
        "turn0bash1",
        "turn0view0",
        "turn0search1",
        "turnbash0",
        "turn4fetch0",
        "turn0read1",
        "TURN0FILE0",
    ):
        assert is_internal_reference_target(target), target


def test_echte_pfade_und_urls_sind_keine_internen_referenzen():
    for target in (
        "/workspaces/MAIN/README.md",
        "file:///workspaces/MAIN/glm2api",
        "https://developer.mozilla.org/en-US/docs/Web/API",
        "workspaces/MAIN",
        "turn",  # ohne suffix: kein treffer
        "turnaround.md",
        "read /workspaces/MAIN/x",
        "",
    ):
        assert not is_internal_reference_target(target), target


def test_extract_target_aus_beiden_formen():
    assert extract_native_open_target({"open": [{"ref_id": "turn0bash1"}]}) == "turn0bash1"
    assert extract_native_open_target({"ref_id": "turn0search0"}) == "turn0search0"
    assert extract_native_open_target({"url": "https://x.com"}) == "https://x.com"
    assert extract_native_open_target("kein json") == ""
    assert extract_native_open_target({"open": []}) == ""


def test_internes_ziel_bleibt_unmappbar():
    allowed = {"bash", "read", "webfetch"}
    assert map_native_open_tool_call({"open": [{"ref_id": "turn0bash1"}]}, allowed) is None
    # gegenprobe: file:// und pfad mappen weiterhin.
    assert map_native_open_tool_call(
        {"open": [{"ref_id": "file:///workspaces/MAIN/glm2api"}]}, allowed
    ) == ("read", {"filePath": "/workspaces/MAIN/glm2api"})


# --- Notice ---------------------------------------------------------------


def test_notice_nennt_die_referenz_und_den_ausweg():
    notice = _internal_reference_notice_text(["turn0bash1", "turn0view0"])
    assert "[internal_reference_notice]" in notice
    assert "`turn0bash1`" in notice
    assert "`turn0view0`" in notice
    assert "scratchpad" in notice
    assert "`read`" in notice
    assert "Never call these ids again" in notice


def test_notice_leer_ohne_ziele():
    assert _internal_reference_notice_text([]) == ""
    assert _internal_reference_notice_text(None) == ""
    assert _internal_reference_notice_text(["", "  "]) == ""


def test_notice_dedupliziert_und_deckelt():
    notice = _internal_reference_notice_text(
        ["turn0bash1", "turn0bash1"] + [f"turn0bash{i}" for i in range(2, 12)]
    )
    assert notice.count("`turn0bash1`") == 1
    assert "(+5 more)" in notice


# --- Ende-zu-Ende ueber den Accumulator -----------------------------------


def _acc():
    return GLMEventAccumulator(
        model="glm-5.3", allowed_tool_names={"bash", "read", "webfetch"}
    )


def _native_open_event(call_id: str, target: str):
    return {
        "status": "init",
        "parts": [
            {
                "id": f"p{call_id}",
                "logic_id": f"l{call_id}",
                "role": "assistant",
                "status": "finish",
                "content": [
                    {
                        "type": "tool_calls",
                        "tool_calls": {
                            "id": call_id,
                            "name": "open",
                            "arguments": json.dumps({"open": [{"ref_id": target, "lineno": 1}]}),
                        },
                    }
                ],
            }
        ],
    }


def test_accumulator_merkt_die_referenz_und_blockiert_den_call():
    acc = _acc()
    acc.consume_event(_native_open_event("c1", "turn0bash1"))
    assert acc.internal_reference_targets == ["turn0bash1"]
    assert "open" in acc.blocked_tool_attempt_names
    # kein ausfuehrbarer call entstanden.
    assert acc._server_side_tool_calls == []


def test_accumulator_merkt_keine_echte_fehlform_als_referenz():
    acc = _acc()
    acc.consume_event(_native_open_event("c1", "read /workspaces/MAIN/x"))
    assert acc.internal_reference_targets == []
    # der echte fehlaufruf bleibt trotzdem blockiert.
    assert "open" in acc.blocked_tool_attempt_names
