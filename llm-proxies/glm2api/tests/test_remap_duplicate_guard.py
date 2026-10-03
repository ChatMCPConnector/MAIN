"""R-01: ein REMAPPTER call (`open` -> `read`) wird schon nach der ERSTEN
Kopie gebremst.

Live-Befund 2026-10-03 (session `ses_efe6cd83bffeb3mKDe1pJ7qDBj`,
`glm2api_output.log`): das Modell feuerte dreimal denselben nativen `open`
auf `test_translator.py` (offset 2440):

    13:57:23  Mapped native open tool call to read args={'filePath': …/test_translator.py'}
    13:57:29  Dropped native open call: not mappable …

Der loop-guard (`_MAX_IDENTICAL_NATIVE_CALLS = 2`) liess ZWEI davon durch —
der client sah zwei identische `read`-calls mit eigenen ids und fuehrte
beide aus. Bei einem ECHTEN wiederholungsversuch (ein `read` nach einem
fehler) ist die grenze 2 gewollt; bei einem remap gibt es diesen fall
nicht: der erste call lief bereits als `read`, jede identische kopie ist
per konstruktion ein doppel-exec.

Diese Tests halten fest:
  - drei identische remappte `open`-calls ergeben GENAU EINE client-ausfuehrung,
  - die beiden verworfenen kopien werden gezaehlt (loop_guard_dropped_count),
  - echte, NICHT remappte wiederholungen bleiben bei der grenze 2
    (kein rueckbau von T-04),
  - zwei VERSCHIEDENE remappte ziele kollabieren nicht.
"""

import json

from glm2api.services.translator import GLMEventAccumulator


def _open_event(call_id: str, file_path: str, offset: int | None = None, limit: int | None = None):
    """Ein nativer `open`-call (dict-form), wie chatglm.cn ihn sendet."""
    arguments: dict[str, object] = {"ref_id": file_path}
    if offset is not None:
        arguments["lineno"] = offset
    if limit is not None:
        arguments["limit"] = limit
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
                            "name": "open",
                            "arguments": json.dumps({"open": [arguments]}),
                        },
                    }
                ],
            }
        ],
    }


def _acc():
    return GLMEventAccumulator(model="glm-5.3", allowed_tool_names={"read", "webfetch"})


def test_drei_identische_remappte_open_calls_ergeben_eine_ausfuehrung():
    acc = _acc()
    acc.consume_event(_open_event("o1", "/workspaces/MAIN/x.py", offset=2440, limit=60))
    acc.consume_event(_open_event("o2", "/workspaces/MAIN/x.py", offset=2440, limit=60))
    acc.consume_event(_open_event("o3", "/workspaces/MAIN/x.py", offset=2440, limit=60))

    assert len(acc._server_side_tool_calls) == 1, (
        "ein remappter call darf nur EINE client-ausfuehrung ergeben"
    )
    assert acc._server_side_tool_calls[0]["function"]["name"] == "read"
    assert acc.loop_guard_dropped_count == 2
    assert acc.loop_guard_dropped_tools == ["open"], (
        "die notice nennt den NATIVEN namen, nicht das mapping-ziel"
    )


def test_zwei_identische_remappte_calls_ergeben_schon_eine_ausfuehrung():
    """Die grenze ist 1, nicht 2 — der zweite identische remap ist bereits
    ein doppel-exec."""
    acc = _acc()
    acc.consume_event(_open_event("o1", "/workspaces/MAIN/y.py"))
    acc.consume_event(_open_event("o2", "/workspaces/MAIN/y.py"))

    assert len(acc._server_side_tool_calls) == 1
    assert acc.loop_guard_dropped_count == 1


def test_echte_wiederholung_bleibt_bei_grenze_zwei():
    """T-04 darf nicht zurueckgebaut werden: ein NICHT remappter `read` mit
    eigener id ist ein bewusster aufruf und bleibt bis zwei erlaubt."""
    acc = _acc()

    def read_event(call_id: str):
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
                                "arguments": json.dumps({"filePath": "/workspaces/MAIN/z.py"}),
                            },
                        }
                    ],
                }
            ],
        }

    acc.consume_event(read_event("r1"))
    acc.consume_event(read_event("r2"))
    acc.consume_event(read_event("r3"))

    assert len(acc._server_side_tool_calls) == 2, (
        "nicht-remappte wiederholungen bleiben bei der grenze 2"
    )
    assert acc.loop_guard_dropped_count == 1


def test_verschiedene_remappte_ziele_kollabieren_nicht():
    acc = _acc()
    acc.consume_event(_open_event("o1", "/workspaces/MAIN/a.py"))
    acc.consume_event(_open_event("o2", "/workspaces/MAIN/b.py"))

    assert len(acc._server_side_tool_calls) == 2
    assert acc.loop_guard_dropped_count == 0


def test_echter_retry_nach_fehler_mit_korrigiertem_ziel_laeuft_durch():
    """Der eigentliche Retry-Fall bleibt intakt: die grenze 1 greift pro
    SIGNATUR. Ein korrigierter pfad ist eine neue signatur und passiert den
    guard — nur die blinde identische wiederholung wird gebremst.

    Das ist der real beobachtete verlauf: `open` auf einen falschen pfad,
    negative rueckmeldung, dann `open` auf den korrigierten pfad."""
    from glm2api.services.glm_client import _seed_loop_guard_counts

    first = _acc()
    first.consume_event(_open_event("o1", "/workspaces/MAIN/gibtsnicht.md"))
    scope = dict(first._server_side_signature_counts)

    corrected = _acc()
    _seed_loop_guard_counts(corrected, scope)
    corrected.consume_event(_open_event("o2", "/workspaces/MAIN/existiert.md"))

    assert len(corrected._server_side_tool_calls) == 1, "korrigiertes ziel muss durch"
    assert corrected.loop_guard_dropped_count == 0


def test_textprotokoll_mit_variierender_schluesselreihenfolge_teilt_den_zaehler():
    """R-02: der text-pfad baute seine signatur ohne `sort_keys`, der native
    pfad mit. Zwei identische argumente in anderer schluesselreihenfolge
    galten damit als VERSCHIEDEN und der zaehler startete je call bei null.
    Live 2026-10-03 (`ses_efe6cd83…`): zweimal `read` auf
    `test_translator.py` (offset 2440), einmal als `{filePath,offset,limit}`,
    einmal als `{limit,offset,filePath}` — `tool_calls=2`, null drops.

    Kanonisch ist das dieselbe signatur; ab der dritten kopie greift der
    guard (T-04 laesst bewusst zwei zu)."""
    acc = _acc()
    variants = [
        {"filePath": "/workspaces/MAIN/t.py", "offset": 2440, "limit": 60},
        {"limit": 60, "offset": 2440, "filePath": "/workspaces/MAIN/t.py"},
        {"offset": 2440, "filePath": "/workspaces/MAIN/t.py", "limit": 60},
    ]
    for index, arguments in enumerate(variants):
        acc.consume_event(
            {
                "status": "finish",
                "parts": [
                    {
                        "logic_id": f"t{index}",
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(
                                    {"tool_calls": [{"name": "read", "arguments": arguments}]}
                                )
                                + "[]",
                            }
                        ],
                    }
                ],
            }
        )
    acc.finalize("finish")
    calls = acc.build_response()["choices"][0]["message"].get("tool_calls") or []

    assert len(calls) == 2, "drei identische (nur anders geordnete) reads -> grenze 2"
    assert acc.loop_guard_dropped_count == 1, (
        "ohne kanonische signatur startet der zaehler je call bei null (0 drops)"
    )


def test_remappter_call_in_listenform_wird_ebenfalls_nach_der_ersten_kopie_gebremst():
    """Die listen-form von `tool_calls` muss dieselbe grenze sehen."""
    acc = _acc()

    def list_event(call_id: str):
        return {
            "status": "init",
            "parts": [
                {
                    "logic_id": f"l{call_id}",
                    "content": [
                        {
                            "type": "tool_calls",
                            "tool_calls": [
                                {
                                    "id": call_id,
                                    "name": "open",
                                    "arguments": json.dumps(
                                        {"open": [{"ref_id": "/workspaces/MAIN/c.py"}]}
                                    ),
                                }
                            ],
                        }
                    ],
                }
            ],
        }

    acc.consume_event(list_event("o1"))
    acc.consume_event(list_event("o2"))

    assert len(acc._server_side_tool_calls) == 1
    assert acc.loop_guard_dropped_count == 1
