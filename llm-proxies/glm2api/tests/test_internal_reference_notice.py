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


# --- F-01 (live 2026-10-03, `ses_efd637390…`): "nach dem fazit einfach weiter" ---
#
# Die noticen sagten bis dahin UNBEDINGT "continue; do not stop". Live schrieb
# das modell bei 16:37:17 ein komplettes fazit ("Die Analyse ist
# abgeschlossen — hier die vollstaendige Auswertung") und rief um 16:38:59 IM
# SELBEN turn weitere tools. Die anweisung war also selbst der ausloeser.


def test_blocked_notice_ist_konditional_und_erlaubt_prosa_abschluss():
    from glm2api.services.glm_client import _blocked_notice_text

    notice = _blocked_notice_text(["open"])
    assert "If the task is NOT yet complete" in notice
    assert "If the task IS already complete" in notice
    assert "final answer as normal prose" in notice
    # das alte, unbedingte "do not stop" darf es nicht mehr geben.
    assert "do not stop" not in notice


def test_internal_reference_notice_erlaubt_prosa_abschluss():
    notice = _internal_reference_notice_text(["turn0bash1"])
    assert "If the task IS already complete" in notice
    assert "stop and answer in prose" in notice
    assert "Do not stop" not in notice


def test_finishing_regel_steht_in_beiden_prompt_bausteinen():
    from glm2api.utils.tool_protocol import TOOL_DISCIPLINE_RECAP, TOOL_FORMAT_REMINDER

    for block in (TOOL_DISCIPLINE_RECAP, TOOL_FORMAT_REMINDER):
        assert "NO tool call" in block, block[:60]
        assert "summarize and then continue" in block, block[:60]


def test_build_tool_call_instructions_hat_finishing_abschnitt():
    from glm2api.utils.tool_protocol import build_tool_call_instructions

    text = build_tool_call_instructions(["read", "bash"])
    assert "## Finishing" in text
    assert "WITHOUT any tool call" in text
    assert "never re-run tools just to look busy" in text


# --- R-03 gegenprobe am konkreten live-pfad --------------------------------


def test_pfad_schreibvarianten_teilen_die_signatur():
    """Live 16:38:12/16:38:14: `read /workspaces/MAIN/README.md` und
    `read //workspaces/MAIN/README.md` wurden beide ausgefuehrt. Die
    kanonische signatur muss identisch sein, damit der guard greift."""
    from glm2api.services.translator import _canonicalize_arguments_for_signature

    a = _canonicalize_arguments_for_signature({"filePath": "/workspaces/MAIN/README.md"})
    b = _canonicalize_arguments_for_signature({"filePath": "//workspaces/MAIN/README.md"})
    c = _canonicalize_arguments_for_signature({"filePath": "workspaces/MAIN/README.md"})
    assert a == b == c
    # gegenprobe: ein wirklich anderer pfad bleibt verschieden.
    d = _canonicalize_arguments_for_signature({"filePath": "/workspaces/MAIN/Makefile"})
    assert d != a
