"""R-03 + R-04: zwei sauberkeits-lücken aus der live-session
`ses_efdcfe5a1ffe3CFJuk1jxNF7W9` ("MAIN-Ordner vollständig analysieren",
2026-10-03).

R-03 — pfad-schreibvarianten umgingen den loop-guard:
    Der guard bildete seine signatur aus den ROHEN argumenten; die
    pfad-normalisierung (`normalize_file_path`) lief erst spaeter in
    `sanitize_tool_calls`, also NACH dem zaehler. `/x/f` und `//x/f` waren
    damit zwei verschiedene signaturen, der zaehler startete je call bei
    null und dieselbe datei wurde zweimal ausgeliefert. Live:

        16:38:12  Mapped native open tool call to read args={'filePath': '/workspaces/MAIN/README.md'}
        16:38:14  Mapped native open tool call to read args={'filePath': '//workspaces/MAIN/README.md'}

    Der client sah zwei `read`-parts auf dieselbe datei, beide `completed`.

R-04 — der `[]`-terminator in der gerenderten History erzeugte einen
    Phantom-User-Turn:
    Die assistant-history wurde als `{"tool_calls":…}[]` gerendert. Im
    naechsten Step las das Modell genau dieses `]` als eigene nutzereingabe
    (`].`) und antwortete auf einen input, den es nie gab ("Das sieht nach
    einem versehentlichen Input aus (`].`)."). Die session hatte genau EINE
    echte user-message, aber acht steps.
"""

import json

from glm2api.services.translator import (
    GLMEventAccumulator,
    convert_messages,
    extract_history_tool_call_signatures,
)
from glm2api.utils.tool_protocol import serialize_tool_call_block


def _acc():
    return GLMEventAccumulator(model="glm-5.3", allowed_tool_names={"read", "webfetch"})


def _read_event(call_id: str, file_path: str):
    return {
        "status": "init",
        "parts": [
            {
                "logic_id": f"l{call_id}",
                "content": [
                    {
                        "type": "tool_calls",
                        "tool_calls": {
                            "id": call_id,
                            "name": "read",
                            "arguments": json.dumps({"filePath": file_path}),
                        },
                    }
                ],
            }
        ],
    }


def test_doppelter_slash_teilt_den_zaehler_mit_einfachem_slash():
    """R-03: `/x/f` und `//x/f` sind derselbe zielpfad und teilen den
    zaehler. Vor dem fix startete jede schreibvariante bei null, sodass
    beliebig viele varianten durchgingen (live: zwei README-reads).

    Die grenze selbst bleibt 2 (T-04) — der beweis ist der DRITTE call:
    ohne geteilten zaehler waere auch er durchgegangen."""
    acc = _acc()
    acc.consume_event(_read_event("r1", "/workspaces/MAIN/README.md"))
    acc.consume_event(_read_event("r2", "//workspaces/MAIN/README.md"))
    acc.consume_event(_read_event("r3", "//workspaces/MAIN/README.md"))

    assert len(acc._server_side_tool_calls) == 2, (
        "die schreibvarianten muessen denselben zaehler teilen"
    )
    assert acc.loop_guard_dropped_count == 1


def test_punkt_segment_teilt_den_zaehler():
    """R-03: `./`-segmente sind derselbe pfad und teilen den zaehler."""
    acc = _acc()
    acc.consume_event(_read_event("r1", "/workspaces/MAIN/README.md"))
    acc.consume_event(_read_event("r2", "/workspaces/MAIN/./README.md"))
    acc.consume_event(_read_event("r3", "/workspaces/MAIN/./README.md"))

    assert len(acc._server_side_tool_calls) == 2
    assert acc.loop_guard_dropped_count == 1


def test_verschiedene_pfade_bleiben_verschieden():
    """R-03 darf nicht ueber-normalisieren: zwei ECHTE verschiedene pfade
    bleiben zwei ausfuehrungen."""
    acc = _acc()
    acc.consume_event(_read_event("r1", "/workspaces/MAIN/a.py"))
    acc.consume_event(_read_event("r2", "/workspaces/MAIN/b.py"))

    assert len(acc._server_side_tool_calls) == 2
    assert acc.loop_guard_dropped_count == 0


def test_history_signatur_normalisiert_den_pfad():
    """R-03: der echo-filter (history) muss dieselbe kanonische signatur
    bauen, sonst findet er eine historische schreibvariante nicht wieder."""
    history = [
        {
            "role": "assistant",
            "tool_calls": [
                {"function": {"name": "read", "arguments": json.dumps({"filePath": "//workspaces/MAIN/README.md"})}}
            ],
        }
    ]
    signatures = extract_history_tool_call_signatures(history)
    assert signatures == {
        'read:{"filePath":"/workspaces/MAIN/README.md"}'
    }, "die history-signatur muss den pfad normalisieren"


def test_serialize_tool_call_block_terminator_opt_out():
    """R-04: der `[]`-terminator ist eine AUSGABE-anweisung. In der History
    muss er weglassbar sein; ohne flag bleibt er (rueckwaerts-kompatibel)."""
    with_terminator = serialize_tool_call_block("read", {"filePath": "/a.py"})
    without_terminator = serialize_tool_call_block(
        "read", {"filePath": "/a.py"}, include_terminator=False
    )

    assert with_terminator.endswith("[]")
    assert not without_terminator.endswith("[]")
    assert without_terminator == with_terminator[: -len("[]")]


def test_convert_messages_rendert_history_ohne_terminator():
    """R-04: die gerenderte assistant-history darf nicht mit `[]` enden —
    genau das las das modell als eigenen user-turn `].`."""
    messages = [
        {"role": "user", "content": "analysiere den MAIN ordner"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "read", "arguments": json.dumps({"filePath": "/workspaces/MAIN/README.md"})},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "name": "read", "content": "inhalt"},
    ]
    read_tool = {
        "type": "function",
        "function": {
            "name": "read",
            "description": "read a file",
            "parameters": {"type": "object", "properties": {"filePath": {"type": "string"}}},
        },
    }
    converted = convert_messages(messages, tools=[read_tool])
    transcript = converted[0]["content"][0]["text"]

    assert "README.md" in transcript, "der call muss gerendert sein"
    # Nur die HISTORY-Zeile pruefen: der Schema-Prompt traegt den `[]`-Terminator
    # als AUSGABE-anweisung und muss ihn behalten.
    history_line = next(
        line
        for line in transcript.splitlines()
        if "README.md" in line and line.startswith("Assistant:")
    )
    assert not history_line.rstrip().endswith("[]"), (
        "der `[]`-terminator darf nicht in der gerenderten history stehen"
    )
    # Die Ausgabe-anweisung selbst bleibt erhalten.
    assert "immediately []." in transcript
