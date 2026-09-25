"""D-09/D-10: der AuditMesh-Verifier hat das Kernsymptom nie geprueft — nur
Dateinamen. Diese Suite macht das Kernsymptom selbst zur Dauerpruefung:

Ein echter Live-Leak dieser Session (3 Faelle, 4.9k/1.6k/2.0k Zeichen)
durchlaeuft den accumulator ueber 256 chunk-groessen — in ZWEI varianten:
eine logic_id fuer den ganzen turn (so streamt der upstream normal) und
eine logic_id pro fragment (so teilt chatglm einen turn tatsaendlich auf,
live: 166 ids in einem turn).

Jede sichtbare ausgabe muss frei von protokoll-resten sein.
"""

import json

import pytest

from glm2api.services.translator import GLMEventAccumulator

LEAK_TEXTS = {
    # live-fall 20:25:14 — protokoll komplett als text beim client
    "bash-live": (
        '{"tool_calls":[{"name":"bash","arguments":{"command":'
        '"cd /workspaces/benchmark/agent-glm2api-hard/miniforge && '
        "ls -la *.md *.py 2>/dev/null | grep -E '(bench-results|CHANGELOG)'"
        '"}}]}[]'
    ),
    # haertetest 21:55:29 — 6 calls, zwischen den objekten fehlte ein '}'
    "multi-write": (
        '{"tool_calls":[{"name":"write","arguments":{"filePath":"/tmp/a.md","content":"# A"}},'
        '{"name":"write","arguments":{"filePath":"/tmp/b.md","content":"# B"}},'
        '{"name":"bash","arguments":{"command":"ls /tmp"}}]}[]'
    ),
    # halluziniertes eigenes konversationsformat
    "transcript": (
        'User: hi\nAssistant: {"tool_calls":[{"name":"read",'
        '"arguments":{"filePath":"/a.py"}}]}[]\nUser: weiter'
    ),
    # protokoll im denkkanal neben prosa
    "thinking-protocol": (
        'Ich muss das pruefen. {"tool_calls":[{"name":"open_url",'
        '"arguments":{"url":"https://x.com"}}]}'
    ),
}

PROTOCOL_MARKERS = ('{"tool_calls"', '"tool_calls":', '"name":', "ml_tool_call", "DSML")
CHUNK_SIZES = (1, 2, 3, 5, 7, 11, 13, 17, 19, 23, 31, 47, 61, 89, 127, 181, 233, 251)


def _run(text: str, chunk_size: int, split_logic_ids: bool) -> str:
    accumulator = GLMEventAccumulator(
        model="m", allowed_tool_names={"bash", "write", "read", "open_url"}
    )
    for index in range(0, len(text), chunk_size):
        fragment = text[index : index + chunk_size]
        event = {
            "conversation_id": "c",
            "parts": [
                {
                    "logic_id": f"p{index}" if split_logic_ids else "p1",
                    "content": [{"type": "text", "text": fragment}],
                }
            ],
        }
        accumulator.consume_event(event)
    accumulator.finalize("finish")
    message = accumulator.build_response()["choices"][0]["message"]
    return (message.get("content") or "") + (message.get("reasoning_content") or "")


@pytest.mark.parametrize("label", sorted(LEAK_TEXTS))
@pytest.mark.parametrize("split_logic_ids", [False, True], ids=["single-logic-id", "split-logic-ids"])
def test_no_protocol_leak_across_chunk_sizes(label, split_logic_ids):
    text = LEAK_TEXTS[label]
    for chunk_size in CHUNK_SIZES:
        visible = _run(text, chunk_size, split_logic_ids)
        leaked = [marker for marker in PROTOCOL_MARKERS if marker in visible]
        assert not leaked, (
            f"{label} (chunk={chunk_size}, split_logic_ids={split_logic_ids}): "
            f"protokoll-reste {leaked} in der sichtbaren ausgabe: {visible[:120]!r}"
        )


def test_blocked_open_url_does_not_produce_an_executable_call():
    """Der Denkkanal-Fall endet in einem gesperrten native-tool: es darf
    kein ausfuehrbarer call entstehen."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read"})
    accumulator.consume_event(
        {
            "conversation_id": "c",
            "status": "finish",
            "parts": [
                {
                    "logic_id": "p1",
                    "status": "finish",
                    "content": [
                        {
                            "type": "text",
                            "text": 'Ich pruefe: {"tool_calls":[{"name":"open_url",'
                            '"arguments":{"url":"https://x.com"}}]}',
                        }
                    ],
                }
            ],
        }
    )
    accumulator.finalize("finish")
    message = accumulator.build_response()["choices"][0]["message"]

    assert not (message.get("tool_calls") or []), "gesperrtes native-tool wurde ausgeliefert"
    assert "open_url" in accumulator.blocked_tool_attempt_names
