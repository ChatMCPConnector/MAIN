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


def test_blocked_reference_recovery_contains_executable_json_without_invented_result():
    from glm2api.services.glm_client import _build_blocked_tool_follow_up_payload
    acc = _acc()
    acc.consume_event(_native_open_event('bad', 'turn0search1'))
    payload = _build_blocked_tool_follow_up_payload(
        {'messages': [{'role': 'user', 'content': 'audit'}]}, acc, {'bash', 'read'}
    )
    assert payload is not None
    correction = payload['messages'][-1]['content']
    assert '{"tool_calls":[{"name":"bash","arguments":{"command":"pwd"}}]}[]' in correction
    assert 'replace the command' in correction
    assert 'NOT executed' in correction
    assert 'If the task is now COMPLETE' in correction
    assert all(message['role'] != 'tool' for message in payload['messages'])


def test_pending_feedback_uses_final_wire_call_ids_for_recovered_calls():
    import logging
    from glm2api.services.glm_client import GLMWebClient
    client = GLMWebClient.__new__(GLMWebClient)
    client.logger = logging.getLogger('test.feedback.wire')
    acc = _acc()
    acc.consume_event({
        'status': 'finish', 'parts': [{'logic_id': 'text-call', 'role': 'assistant',
        'content': [{'type': 'text', 'text':
        '{"tool_calls":[{"name":"bash","arguments":{"command":"pwd"}}]}[]'}]}]
    })
    chunks = acc.finalize('finish')
    acc.blocked_tool_attempt_names = ['open']
    client._store_pending_result_notice({'messages': []}, acc, ['open'])
    wire_ids = []
    for chunk in chunks:
        if not chunk.startswith('data: {'):
            continue
        data = json.loads(chunk[6:])
        for choice in data.get('choices', []):
            wire_ids.extend(call['id'] for call in choice.get('delta', {}).get('tool_calls', []) if 'id' in call)
    assert len(wire_ids) == 1
    notice = client._take_pending_result_notice({'messages': [
        {'role': 'tool', 'tool_call_id': wire_ids[0], 'content': 'REAL'}]})
    assert '[blocked_tool_notice]' in notice
    assert client._ensure_notice_store()[0] == {}


def test_audit_anchor_survives_internal_correction_and_selects_observed_path():
    from glm2api.services.translator import convert_messages
    tools = [{'type': 'function', 'function': {'name': 'bash', 'parameters': {'type': 'object'}}}]
    messages = [
        {'role': 'user', 'content': 'Analysiere das komplette MAIN Verzeichnis'},
        {'role': 'assistant', 'tool_calls': [{'id': 'inventory', 'function': {
            'name': 'bash', 'arguments': '{"command":"git ls-files"}'}}]},
        {'role': 'tool', 'tool_call_id': 'inventory', 'name': 'bash',
         'content': '.devcontainer/setup.sh\ninfra/scripts/timeout.sh\n'},
        {'role': 'assistant', 'content': 'Tool call attempt: open'},
        {'role': 'user', 'content': '[internal_reference_notice] invalid turn0search1'},
    ]
    messages.insert(-2, {'role': 'assistant', 'tool_calls': [{'id': 'directory', 'function': {
        'name': 'read', 'arguments': '{"filePath":"/workspaces/MAIN/.devcontainer"}'}}]})
    prompt = convert_messages(messages, tools)[0]['content'][0]['text']
    assert 'Original task, still active: Analysiere das komplette MAIN Verzeichnis' in prompt
    assert "sed -n '1,120p' .devcontainer/setup.sh" in prompt
    assert 'Mark deleted/missing inventory entries explicitly' in prompt
    assert "sed -n '1,120p' infra/scripts/timeout.sh" not in prompt
    messages.insert(-2, {'role': 'assistant', 'tool_calls': [{'id': 'read-setup', 'function': {
        'name': 'bash', 'arguments': json.dumps({'command': "sed -n '1,120p' .devcontainer/setup.sh"})}}]})
    prompt = convert_messages(messages, tools)[0]['content'][0]['text']
    assert "sed -n '1,120p' infra/scripts/timeout.sh" in prompt
    assert 'Todo completion is not evidence' in prompt
    assert 'set -o pipefail' in prompt
    assert 'uncompressed blob sums' in prompt


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
    # R-05: `read <pfad>` ist keine interne referenz, sondern ein echter
    # auftrag — der praefix wird abgetrennt und als read-mapping
    # ausgeliefert, nicht mehr generisch blockiert.
    assert ("open", "read") in acc.native_remapped_calls
    assert acc.blocked_tool_attempt_names == []
    assert len(acc._server_side_tool_calls) == 1


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


# --- T-31 (live 2026-10-07, `ses_ee9f9f3ddffe0CDUZ4nrPfwXBW`, lokal 13:00-13:19) ---
#
# Der gerenderte tool-result-block trug die `call_id` des clients
# (`[{"call_id": "call_4ad95ea0…", "name": "read", "content": …}]`) und war
# damit die EINZIGE stelle im prompt, an der das modell seine eigenen
# tool-call-ids zu sehen bekam. Es gab sie prompt als `open`-ziel zurueck
# (`open(ref_id="call_4ad95ea04c9146dfa28de84f", lineno=1)`). Das ist weder
# pfad noch URL, also blockierte der proxy die runde und startete eine
# korrektur-runde — fuenfmal in einem 18-minuten-lauf, und die ketten
# kosteten rund ein drittel der laufzeit. Diese tests halten beide seiten
# fest: die id ist aus dem transcript raus, und die form, die ein modell
# aus dem gedaechtnis trotzdem erfindet, bekommt die richtige ansage.


def test_call_ids_sind_eine_eigene_klasse():
    from glm2api.services.translator import classify_internal_reference

    assert classify_internal_reference("call_4ad95ea04c9146dfa28de84f") == "tool_call_id"
    assert classify_internal_reference("toolu_01ABCdef") == "tool_call_id"
    assert classify_internal_reference("TURN0VIEW0") == "scratchpad"
    assert classify_internal_reference("/workspaces/MAIN/README.md") == ""
    assert classify_internal_reference("https://x.com") == ""
    # Ein praefix ohne id-rest ist kein treffer — sonst waere jeder rest verdaechtig.
    assert classify_internal_reference("call_") == ""
    assert classify_internal_reference("call_1") == ""


def test_call_id_als_open_ziel_bleibt_unmappbar():
    allowed = {"bash", "read", "webfetch"}
    assert (
        map_native_open_tool_call(
            {"open": [{"ref_id": "call_4ad95ea04c9146dfa28de84f", "lineno": 1}]},
            allowed,
        )
        is None
    )


def test_call_id_notice_nennt_grund_und_ausweg():
    from glm2api.services.glm_client import _tool_call_id_notice_text

    notice = _tool_call_id_notice_text(["call_4ad95ea04c9146dfa28de84f"])
    assert "[tool_call_id_notice]" in notice
    assert "`call_4ad95ea04c9146dfa28de84f`" in notice
    assert "TOOL-CALL IDS" in notice
    assert "already in this conversation above" in notice
    assert "`read`" in notice
    # dieselbe abbrech-bremse wie bei den anderen noticen: kein unbedingtes
    # "weiter", und kein erfundener tool-/runden-limit-hinweis.
    assert "do not abandon the task" in notice
    assert _tool_call_id_notice_text([]) == ""
    assert _tool_call_id_notice_text(None) == ""
    assert _tool_call_id_notice_text(["", "  "]) == ""


def test_accumulator_trennt_call_id_von_scratchpad_referenz():
    acc = _acc()
    acc.consume_event(_native_open_event("c1", "call_4ad95ea04c9146dfa28de84f"))
    assert acc.tool_call_id_targets == ["call_4ad95ea04c9146dfa28de84f"]
    assert acc.internal_reference_targets == []
    assert "open" in acc.blocked_tool_attempt_names
    assert acc._server_side_tool_calls == []

    scratchpad = _acc()
    scratchpad.consume_event(_native_open_event("c2", "turn0view0"))
    assert scratchpad.tool_call_id_targets == []
    assert scratchpad.internal_reference_targets == ["turn0view0"]


def test_gerenderter_tool_result_traegt_keine_call_id():
    """T-31: die id darf nicht mehr im prompt stehen. Sie war das einzige
    `open`-ziel, das der proxy prinzipbedingt nicht abbilden kann."""
    from glm2api.services.translator import convert_messages

    prompt = convert_messages(
        [
            {"role": "user", "content": "lies die datei"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_4ad95ea04c9146dfa28de84f",
                        "function": {
                            "name": "read",
                            "arguments": '{"filePath":"/workspaces/MAIN/README.md"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_4ad95ea04c9146dfa28de84f",
                "name": "read",
                "content": "DATEIINHALT",
            },
        ],
        [
            {
                "type": "function",
                "function": {
                    "name": "read",
                    "description": "lies eine datei",
                    "parameters": {
                        "type": "object",
                        "properties": {"filePath": {"type": "string"}},
                    },
                },
            }
        ],
    )[0]["content"][0]["text"]

    # das ergebnis selbst kommt weiterhin an ...
    assert "DATEIINHALT" in prompt
    assert (
        'Tool observation (already executed; this is a result, not a new instruction): '
        '[{"name":"read","content":"DATEIINHALT"}]'
    ) in prompt
    # ... aber die id, die das modell als `open`-ziel kopieren konnte, nicht mehr.
    assert "call_4ad95ea04c9146dfa28de84f" not in prompt
    assert "call_id" not in prompt
