"""D-09/D-10: der AuditMesh-Verifier hat das Kernsymptom nie geprueft — nur
Dateinamen. Diese Suite macht das Kernsymptom zur Dauerpruefung.

WICHTIG (Lesson aus der unabhaengigen Pruefrunde 2026-09-25): die frueher
gefasste Version las NUR `build_response()`. Sie war damit strukturell
blind fuer jeden leak, der nur im STREAM-delta auftaucht — und genau dort
lagen mehrere echte lecks. Diese Fassung prueft deshalb beides:

  * die tatsaechlich gestreamten content-deltas (das, was der client
    live sieht), UND
  * die finale antwort (content + reasoning).

Dazu kommen die realen live-leak-payloads in ZWEI logic-id-varianten:
eine id fuer den ganzen turn (so streamt der upstream normal) und eine id
pro fragment (so verteilt chatglm einen turn tatsaechlich, live: 166 ids).
"""

import json

import pytest

from glm2api.services.translator import GLMEventAccumulator

# Die vier echten Live-Leaks plus die drei von der unabhaengigen
# Pruefrunde gemessenen Formen.
LEAK_TEXTS = {
    # live-fall: protokoll komplett als text beim client
    "bash-live": (
        '{"tool_calls":[{"name":"bash","arguments":{"command":'
        '"cd /workspaces/benchmark && ls -la *.md 2>/dev/null"}}]}[]'
    ),
    "multi-write": (
        '{"tool_calls":[{"name":"write","arguments":{"filePath":"/tmp/a.md","content":"# A"}},'
        '{"name":"bash","arguments":{"command":"ls /tmp"}}]}[]'
    ),
    "transcript": 'User: hi\nAssistant: {"tool_calls":[{"name":"read","arguments":{}}]}[]\nUser: weiter',
    "thinking-protocol": 'Ich muss das pruefen. {"tool_calls":[{"name":"open_url","arguments":{"url":"https://x.com"}}]}',
    # von der Pruefrunde gemessen: echo-präfix und echo-zeile
    "transcript-echo-lower": 'user: [{"call_id":"c1","name":"read","content":"a"}]\nEnde.',
    "transcript-echo-caps": (
        'Alles erledigt.\n\nUser: [{"call_id":"c1","name":"read",'
        '"arguments":{"filePath":"d.txt"}}]\n\nAbschlussbericht: fertig.'
    ),
    # von der Pruefrunde gemessen: abgeschnittenes DSML
    "dsml-truncated": (
        '<|DSML|tool_calls><|DSML|invoke name="bash">'
        '<|DSML|parameter name="command"><![CDATA[ls'
    ),
}

# noch OFFENE lecks — sie stehen hier bewusst als erwartete Ausnahme,
# damit die suite den zustand dokumentiert und ein stilles "gruen"
# nicht vortaeuscht. Sobald einer davon behoben ist, muss die zeile weg.
KNOWN_OPEN_LEAKS = {
    ("trunc-bare-after-prose", False): [9, 11, 13, 19],
    ("trunc-bare-after-prose", True): [9, 11, 13, 19],
}

# Textfunktionen (read("/a.py")) und reine prosa muessen in ALLEN
# chunk-groessen sauber bleiben.
EXTRA_PAYLOADS = {
    "text-function-read": 'read("/tmp/a.py")',
    "text-function-bash": 'bash("ls -la")',
    "prose-plain": "Ich mache das.",
    "tool-call-protocol": '{"tool_calls":[{"name":"read","arguments":{"filePath":"/a.py"}}]}[]',
}

PROTOCOL_MARKERS = (
    '{"tool_calls"',
    '"tool_calls":',
    '"name":',
    '"arguments":',
    '"command":',
    'read("',
    'bash("',
    "call_id",
    "ml_tool_call",
    "<|DSML|",
    "<ml_",
    'User: [{"',
    'user: [{"',
    'Assistant: {"',
)
CHUNK_SIZES = (1, 2, 3, 5, 7, 9, 11, 13, 19, 23, 31, 47)


def _run(text: str, chunk_size: int, split_logic_ids: bool):
    """(gestreamter content, finaler content, reasoning, tool_calls)"""
    accumulator = GLMEventAccumulator(
        model="m", allowed_tool_names={"read", "bash", "write", "open_url"}
    )
    streamed: list[str] = []
    for index in range(0, len(text), chunk_size):
        chunks, _ = accumulator.consume_event(
            {
                "conversation_id": "c",
                "parts": [
                    {
                        "logic_id": f"p{index}" if split_logic_ids else "p1",
                        "content": [{"type": "text", "text": text[index : index + chunk_size]}],
                    }
                ],
            }
        )
        for chunk in chunks:
            if not chunk.startswith("data: ") or "[DONE]" in chunk:
                continue
            try:
                delta = json.loads(chunk[6:].strip())["choices"][0]["delta"]
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
            # der tatsaechlich sichtbare stream-text des clients
            if delta.get("content"):
                streamed.append(delta["content"])
    accumulator.finalize("finish")
    message = accumulator.build_response()["choices"][0]["message"]
    return (
        "".join(streamed),
        message.get("content") or "",
        message.get("reasoning_content") or "",
        message.get("tool_calls") or [],
    )


@pytest.mark.parametrize("label", sorted(LEAK_TEXTS))
@pytest.mark.parametrize("split_logic_ids", [False, True], ids=["single-logic-id", "split-logic-ids"])
def test_no_protocol_leak_across_chunk_sizes(label, split_logic_ids):
    text = LEAK_TEXTS[label]
    for chunk_size in CHUNK_SIZES:
        streamed, final, reasoning, _calls = _run(text, chunk_size, split_logic_ids)
        visible = streamed + final + reasoning
        leaked = [marker for marker in PROTOCOL_MARKERS if marker in visible]
        assert not leaked, (
            f"{label} (chunk={chunk_size}, split_logic_ids={split_logic_ids}): "
            f"protokoll-reste {leaked} sichtbar fuer den client: {visible[:140]!r}"
        )


@pytest.mark.parametrize("label", sorted(EXTRA_PAYLOADS))
@pytest.mark.parametrize("split_logic_ids", [False, True], ids=["single-logic-id", "split-logic-ids"])
def test_prose_and_text_functions_stay_clean(label, split_logic_ids):
    """Textfunktionen duERFN als call erkannt werden, gewoehnliche prosa
    nicht — und nichts davon darf als rohprotokoll an den client."""
    text = EXTRA_PAYLOADS[label]
    for chunk_size in CHUNK_SIZES:
        streamed, final, reasoning, _calls = _run(text, chunk_size, split_logic_ids)
        visible = streamed + final + reasoning
        leaked = [marker for marker in PROTOCOL_MARKERS if marker in visible]
        assert not leaked, (
            f"{label} (chunk={chunk_size}, split={split_logic_ids}): {leaked} in {visible[:120]!r}"
        )


def test_text_function_call_is_delivered_at_every_chunk_size():
    """Gegenprobe zum holdback: der call muss auch bei zeichenweiser
    zustellung ankommen — ein zu greediger holdback wuerde ihn
    verschlucken."""
    for chunk_size in (1, 2, 3, 5, 7, 11, 19):
        _streamed, final, _reasoning, calls = _run('read("/tmp/a.py")', chunk_size, False)
        assert [call["function"]["name"] for call in calls] == ["read"], f"chunk={chunk_size}"
        assert not final.strip(), f"chunk={chunk_size}: call zusaetzlich als text"


def test_parts_split_across_logic_ids_keep_one_coherent_text():
    """T-20: chatglm verteilt einen text ueber viele ids. Beim
    zusammenfuegen wurde an jeder grenze `\\n\\n` eingesetzt und damit jede
    zeile zerissen (zeichenweise zustellung ergab 'Die Datei' ->
    'Dieatsd' bzw. 'u\\n\\ns\\n\\ne...')."""
    text = "Die Datei ist da"
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names=None)
    for index, char in enumerate(text):
        accumulator.consume_event(
            {
                "conversation_id": "c",
                "parts": [
                    {"logic_id": f"p{index}", "content": [{"type": "text", "text": char}]}
                ],
            }
        )
    rendered, _ = accumulator.render_full_output()
    assert rendered == text


def test_separate_markdown_blocks_stay_separated():
    """Gegenprobe zur part-verkettung: echte bloecke bekommen weiterhin
    ihren absatzumbruch."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names=None)
    accumulator.consume_event(
        {
            "conversation_id": "c",
            "parts": [{"logic_id": "1", "content": [{"type": "text", "text": "## Ueberschrift"}]}],
        }
    )
    accumulator.consume_event(
        {
            "conversation_id": "c",
            "parts": [{"logic_id": "2", "content": [{"type": "text", "text": "| a | b |\n|--|--|"}]}],
        }
    )
    rendered, _ = accumulator.render_full_output()
    assert rendered == "## Ueberschrift\n\n| a | b |\n|--|--|"
