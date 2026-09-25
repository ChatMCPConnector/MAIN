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


# --- D-01, D-04, D-05, D-08: die tests selbst pruefen das kernsymptom ---


@pytest.mark.parametrize("chunk_size", [1, 3, 7, 13, 29])
def test_d01_deferral_never_leaks_the_raw_tool_prefix(chunk_size):
    """D-01: der alte deferral-test behauptete nur `assert 'tool' in
    combined` — und `tool` stand bereits im protocol des erlaubten
    aufrufs. Die behauptung konnte nicht fehlschlagen. Geprueft wird
    jetzt der ROHE praefix am sichtbaren stream."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"bash"})
    text = '{"tool'
    chunks, _ = accumulator.consume_event({
        "conversation_id": "c",
        "parts": [{"logic_id": "p1", "content": [{"type": "text", "text": text[:chunk_size]}]}],
    })
    visible = "".join(
        json.loads(chunk[6:])["choices"][0]["delta"].get("content", "")
        for chunk in chunks
        if chunk.startswith("data: ") and "[DONE]" not in chunk
    )
    assert '{"tool' not in visible
    accumulator.finalize("finish")
    message = accumulator.build_response()["choices"][0]["message"]
    assert '{"tool' not in (message.get("content") or "")


@pytest.mark.parametrize("chunk_size", [1, 2, 3, 5, 7, 9, 11, 13])
def test_d04_echo_marker_survives_early_chunk_splits(chunk_size):
    """D-04: der vermeintliche boundary-test lieferte den marker als
    kompletten anfangs-chunk. Fruehe teilungen mitten in `U`/`Us` waren
    ungeprueft — genau dort entstehen die leaks."""
    text = 'User: [{"tool_calls":[{"name":"bash","arguments":{"command":"ls"}}]}[]\n'
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"bash"})
    streamed: list[str] = []
    for index in range(0, len(text), chunk_size):
        chunks, _ = accumulator.consume_event({
            "conversation_id": "c",
            "parts": [{"logic_id": f"p{index}", "content": [{"type": "text", "text": text[index : index + chunk_size]}]}],
        })
        for chunk in chunks:
            if not chunk.startswith("data: ") or "[DONE]" in chunk:
                continue
            try:
                delta = json.loads(chunk[6:].strip())["choices"][0]["delta"]
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
            if delta.get("content"):
                streamed.append(delta["content"])
    accumulator.finalize("finish")
    message = accumulator.build_response()["choices"][0]["message"]
    visible = "".join(streamed) + (message.get("content") or "")

    for marker in ('User: [{"', 'user: [{"', 'Assistant: {"'):
        assert marker not in visible, f"{marker} bei chunk={chunk_size}"


@pytest.mark.parametrize("chunk_size", [1, 3, 7, 13, 29])
def test_d05_mixed_allowed_and_blocked_across_chunk_sizes(chunk_size):
    """D-05: gemischte turns (gueltiger call neben blockiertem) waren
    ungetestet — genau der pfad, auf dem C-11 den gueltigen call verlor."""
    text = (
        '{"tool_calls":[{"name":"read","arguments":{"filePath":"/tmp/a"}}]}[]'
        '{"tool_calls":[{"name":"open_url","arguments":{"url":"https://x"}}]}[]'
    )
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read", "bash"})
    for index in range(0, len(text), chunk_size):
        accumulator.consume_event({
            "conversation_id": "c",
            "parts": [{"logic_id": "p1", "content": [{"type": "text", "text": text[index : index + chunk_size]}]}],
        })
    accumulator.finalize("finish")
    message = accumulator.build_response()["choices"][0]["message"]

    names = [call["function"]["name"] for call in (message.get("tool_calls") or [])]
    assert names == ["read"], f"gueltiger call geht verloren bei chunk={chunk_size}: {names}"


@pytest.mark.parametrize("build", ["stream", "non-stream"])
def test_d08_blocked_attempt_is_never_a_successful_answer(build):
    """D-08: die tests schrieben den blockierten versuch als normale
    erfolgreiche antwort fest. Der vertrag ist inzwischen: sichtbarer
    hinweis JA, aber `finish_reason=error` — ein agent darf daraus keinen
    vollstaendigen tool-turn ableiten."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"bash"})
    accumulator.consume_event({
        "conversation_id": "c",
        "status": "finish",
        "parts": [{"logic_id": "p1", "content": [
            {"type": "text", "text": '{"tool_calls":[{"name":"open_url","arguments":{"url":"https://x"}}]}[]'},
        ]}],
    })
    if build == "stream":
        accumulator.finalize("finish")
    choice = accumulator.build_response("finish")["choices"][0]

    assert not choice["message"].get("tool_calls")
    assert "unavailable tool" in (choice["message"].get("content") or "")
    # Der turn endet mit `stop`, NICHT mit `error`: als `error` wertete der
    # echte client das als stream-fehler und wiederholte ihn mit 5-minuten-
    # backoff endlos (agentenlauf 2026-09-26). Der gesperrte aufruf ist eine
    # vollstaendige antwort ("dieses werkzeug gibt es nicht") — der
    # sichtbare hinweis verhindert die falsche behauptung, der turn ist
    # damit regulaer beendet.
    assert choice["finish_reason"] == "stop"


@pytest.mark.parametrize("chunk_size", sorted(CHUNK_SIZES))
@pytest.mark.parametrize("split_logic_ids", [False, True], ids=["single-logic-id", "split-logic-ids"])
def test_truncated_call_after_prose_never_reaches_the_client(chunk_size, split_logic_ids):
    """`trunc-bare-after-prose` war als bewusst offen dokumentiert (4 von
    12 chunk-groessen). Mit dem D-01-Fix ist es 0 von 12.

    Der gefaehrliche fall ist nicht der fehlende `[]`-terminator — die
    argument-daten sind dann vollstaendig und der call ist verstaendlich.
    Gefaehrlich sind ABGESCHNITTENE ARGUMENTE: der client wuerde einen
    call mit halbem pfad oder halbem befehl ausfuehren. Genau das wird
    jetzt verweigert, die prosa bleibt sichtbar."""
    prose = "Hier ist die Antwort fuer dich. "
    truncated = '{"tool_calls":[{"name":"bash","arguments":{"command":"ls -'
    text = prose + truncated

    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"bash"})
    streamed: list[str] = []
    for index in range(0, len(text), chunk_size):
        chunks, _ = accumulator.consume_event({
            "conversation_id": "c",
            "parts": [{
                "logic_id": f"p{index}" if split_logic_ids else "p1",
                "content": [{"type": "text", "text": text[index : index + chunk_size]}],
            }],
        })
        for chunk in chunks:
            if not chunk.startswith("data: ") or "[DONE]" in chunk:
                continue
            try:
                delta = json.loads(chunk[6:].strip())["choices"][0]["delta"]
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
            if delta.get("content"):
                streamed.append(delta["content"])
    accumulator.finalize("finish")
    choice = accumulator.build_response()["choices"][0]
    message = choice["message"]
    visible = "".join(streamed) + (message.get("content") or "")

    assert not message.get("tool_calls"), "ein abgeschnittener aufruf darf NICHT ausgeliefert werden"
    assert choice["finish_reason"] == "error"
    # die prosa ist eine echte antwort und bleibt erhalten
    assert "Hier ist die Antwort fuer dich." in visible
    for marker in ('{"tool_calls"', '"name":', '"command":'):
        assert marker not in visible, f"rohes protokoll im sichtbaren text: {marker}"


def test_missing_terminator_alone_still_yields_the_call():
    """Gegenprobe zur scharzen regel: fehlt NUR der `[]`-terminator,
    sind die argument-daten vollstaendig. Das ist kein beschnittener
    aufruf, sondern ein vollstaendiger ohne markierung — er wird
    zu Recht ausgeliefert. Zu aggressives abschneiden wuerde hier
    echte aufrufe zerstoeren."""
    prose = "Hier ist die Antwort fuer dich. "
    text = prose + '{"tool_calls":[{"name":"bash","arguments":{"command":"ls"}}]}'

    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"bash"})
    for index in range(0, len(text), 7):
        accumulator.consume_event({
            "conversation_id": "c",
            "parts": [{"logic_id": "p1", "content": [{"type": "text", "text": text[index : index + 7]}]}],
        })
    accumulator.finalize("finish")
    message = accumulator.build_response()["choices"][0]["message"]

    assert [call["function"]["name"] for call in (message.get("tool_calls") or [])] == ["bash"]
