"""T-25: verworfene Tool-Calls muessen fuer das Modell sichtbar sein.

Historischer Live-Fall 2026-09-26 (`ses_f21fbf23…`): das modell rief 10x in
EINEM turn `open` mit identischem ziel `/workspaces/MAIN/glm2api`. Der proxy
mappt `open` auf `read` (translator.map_native_open_tool_call), der loop
guard ließ 2 durch und verwarf 8. Die damalige Version gab dazu keine
Rueckmeldung; das modell schloss auf ein nicht existentes Limit ("Tool-Limit
(8/8 Runden) erreicht"), brach ab und verlangte einen Neustart. Der Guard
liefert inzwischen eine sichtbare Notice; die Tests darunter schützen sowohl
das Verwerfen als auch die Rueckmeldung.

Diese tests halten fest:
  - der guard verwirft weiter (doppelt ausgefuehrt wird nicht),
  - aber jeder verworfene call wird fuer das modell SICHTBAR,
  - die notice nennt den nativen namen (`open`), nicht den gemappten
    (`read`) — sonst sucht das modell den fehler im falschen werkzeug,
  - und sie widerspricht der limit-narrative ausdruecklich.
"""

import json
from types import SimpleNamespace

from glm2api.services.glm_client import GLMWebClient, _loop_guard_notice_text
from glm2api.services.translator import GLMEventAccumulator

TARGET = "/workspaces/MAIN/glm2api"


def _native_open_event(call_id: str, target: str = TARGET):
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


def _native_open_list_event(call_id: str, target: str = TARGET):
    event = _native_open_event(call_id, target)
    event["parts"][0]["content"][0]["tool_calls"] = [
        event["parts"][0]["content"][0]["tool_calls"]
    ]
    return event


def _text_read_event(count: int, target: str = TARGET):
    protocol = {
        "tool_calls": [
            {"name": "read", "arguments": {"filePath": target}}
            for _ in range(count)
        ]
    }
    return {
        "status": "finish",
        "parts": [
            {
                "logic_id": "text_calls",
                "content": [{"type": "text", "text": json.dumps(protocol) + "[]"}],
            }
        ],
    }


def _feed(acc, count: int, target: str = TARGET, tag: str = "c"):
    for index in range(count):
        acc.consume_event(_native_open_event(f"call_{tag}{index}", target))


def _acc():
    return GLMEventAccumulator(model="glm-5.3", allowed_tool_names={"bash", "read", "webfetch"})


# --- Guard-Verhalten (unveraendert) ---------------------------------------


def test_loop_guard_liefert_nur_zwei_und_zaehlt_die_drops():
    acc = _acc()
    _feed(acc, 10)

    assert len(acc._server_side_tool_calls) == 2, "zwei identische calls sind erlaubt"
    assert acc.loop_guard_dropped_count == 8
    assert acc.blocked_tool_attempt_names == [], "der guard ist KEIN blocked-tool-fall"


def test_loop_guard_haelt_auch_native_tool_calls_listenform_auf_zwei():
    acc = _acc()
    for index in range(10):
        acc.consume_event(_native_open_list_event(f"call_list{index}"))

    assert len(acc._server_side_tool_calls) == 2
    assert acc.loop_guard_dropped_count == 8
    assert acc.loop_guard_dropped_tools == ["open"]


def test_loop_guard_gilt_ueber_dict_und_listenform_gemeinsam():
    acc = _acc()
    _feed(acc, 1, tag="dict")
    for index in range(9):
        acc.consume_event(_native_open_list_event(f"call_list{index}"))

    assert len(acc._server_side_tool_calls) == 2
    assert acc.loop_guard_dropped_count == 8


def test_loop_guard_begrenzt_identische_textprotokoll_calls():
    acc = _acc()
    acc.consume_event(_text_read_event(10))
    acc.finalize("finish")
    message = acc.build_response()["choices"][0]["message"]

    assert len(message.get("tool_calls") or []) == 2
    assert acc.loop_guard_dropped_count == 8
    assert acc.loop_guard_dropped_tools == ["read"]


def test_zwei_absichtlich_gleiche_text_calls_bleiben_erlaubt():
    acc = _acc()
    acc.consume_event(_text_read_event(2))
    acc.finalize("finish")
    message = acc.build_response()["choices"][0]["message"]

    assert len(message.get("tool_calls") or []) == 2
    assert acc.loop_guard_dropped_count == 0


def test_unterschiedliche_ziele_werfen_den_guard_nicht_aus():
    """Der guard gilt pro signatur. Zwei verschiedene pfade sind zwei
    echte aufrufe — sonst wuerde er legitime arbeit kappen."""
    acc = _acc()
    _feed(acc, 3, target="/workspaces/MAIN/a.md", tag="a")
    _feed(acc, 3, target="/workspaces/MAIN/b.md", tag="b")

    assert len(acc._server_side_tool_calls) == 4
    assert acc.loop_guard_dropped_count == 2


def test_ohne_drops_bleibt_der_zaehler_null():
    acc = _acc()
    _feed(acc, 2)
    assert acc.loop_guard_dropped_count == 0


# --- Notice ---------------------------------------------------------------


def test_notice_nennt_den_nativen_namen_nicht_den_gemappten():
    text = _loop_guard_notice_text(8, ["open"])
    assert "open" in text
    # `read` ist der gemappte name — ihn zu nennen wuerde das modell auf
    # das falsche werkzeug schicken (live-fall: 'read funktioniert nicht').
    assert "identical open call" in text


def test_notice_widerspricht_der_limit_narrative():
    text = _loop_guard_notice_text(8, ["open"]).lower()
    assert "no tool limit" in text
    assert "round limit" in text
    assert "fix the" in text and "instead of repeating" in text


def test_notice_nennt_die_anzahl():
    assert "8 identical" in _loop_guard_notice_text(8, ["open"])


def test_ohne_drops_keine_notice():
    assert _loop_guard_notice_text(0, []) == ""
    assert _loop_guard_notice_text(-1, ["open"]) == ""


def test_notice_ohne_toolnamen_bleibt_lesbar():
    text = _loop_guard_notice_text(3, [])
    assert "3 identical" in text
    assert "loop guard" in text


class _LoopGuardConfig:
    glm_stream_error_max_retries = 2
    glm_stream_error_retry_interval = 0.0
    glm_max_output_tokens = 16384
    glm_blocked_tool_follow_ups = 0
    glm_empty_response_max_retries = 0
    glm_history_max_chars = 120000
    glm_request_deadline_seconds = 300.0
    request_timeout = 5
    blocked_tool_names = []
    debug_dump_all = False
    glm_assistant_id = "assistant"
    glm_delete_conversation = False
    glm_queue_wait_timeout = 5
    glm_max_concurrency = 1
    glm_base_url = "https://chatglm.cn/chatglm"
    glm_persistent_conversation = False


class _FakeResponse:
    def __init__(self, events):
        self._events = events
        self.closed = False

    def close(self):
        self.closed = True


def _make_client():
    client = GLMWebClient.__new__(GLMWebClient)
    client.config = _LoopGuardConfig()
    client.logger = SimpleNamespace(
        warning=lambda *a, **k: None, info=lambda *a, **k: None, debug=lambda *a, **k: None
    )
    client.request_queue = SimpleNamespace(
        acquire=lambda name: SimpleNamespace(ticket=0, released=False, release=lambda: None)
    )
    client.auth = SimpleNamespace(
        get_account_count=lambda: 1, get_access_token_for_account=lambda i: "tok"
    )
    events = [_native_open_event(f"call_{i}") for i in range(6)]
    client._open_chat_stream = lambda p, preferred_account_index=None, filtered_tools=None: (
        _FakeResponse(events),
        "assistant-1",
    )
    client.delete_conversation = lambda cid, assistant_id=None: None
    client._iter_sse_events = lambda response: iter(response._events)
    return client


def _payload():
    return {
        "model": "glm-5.3",
        "messages": [{"role": "user", "content": "lies die datei"}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "read",
                    "parameters": {
                        "type": "object",
                        "properties": {"filePath": {"type": "string"}},
                        "required": ["filePath"],
                    },
                },
            }
        ],
    }


# --- Sichtbarkeit im Antwortstrom ----------------------------------------


def test_stream_antwort_enthaelt_die_loop_guard_notice():
    client = _make_client()
    chunks = [c.decode("utf-8") for c in client.stream_chat_completion(_payload())]
    text = "".join(chunks)
    assert "[loop_guard_notice]" in text
    assert "4 identical open call" in text
    assert "NO tool limit" in text


def test_stream_liefert_genau_zwei_calls_und_keine_mehr():
    client = _make_client()
    text = "".join(c.decode("utf-8") for c in client.stream_chat_completion(_payload()))
    # die argument-string stehen im SSE-chunk escaped
    assert text.count("filePath") == 2, "der guard darf nicht auf 6 durchlassen"


def test_non_stream_antwort_enthaelt_die_loop_guard_notice():
    client = _make_client()
    result, _ = client.chat_completion(_payload())
    message = result["choices"][0]["message"]
    # S-22: die notice steht im DENKKANAL, nicht im sichtbaren text.
    # Live 2026-09-28: als content landete sie mitten in der antwort und
    # das modell las sie als teil seiner eigenen narration.
    content = message.get("reasoning_content") or ""
    assert "[loop_guard_notice]" in content
    assert "NO tool limit" in content
    assert "[loop_guard_notice]" not in (message.get("content") or "")
    assert len(message.get("tool_calls") or []) == 2


def test_stream_guard_notice_gilt_auch_fuer_textprotokoll_calls():
    client = _make_client()
    client._open_chat_stream = lambda p, preferred_account_index=None, filtered_tools=None: (
        _FakeResponse([_text_read_event(10)]),
        "assistant-1",
    )

    text = "".join(c.decode("utf-8") for c in client.stream_chat_completion(_payload()))

    assert text.count("filePath") == 2
    assert "[loop_guard_notice]" in text
    assert "8 identical read call" in text


def test_non_stream_guard_notice_gilt_auch_fuer_textprotokoll_calls():
    client = _make_client()
    client._open_chat_stream = lambda p, preferred_account_index=None, filtered_tools=None: (
        _FakeResponse([_text_read_event(10)]),
        "assistant-1",
    )

    result, _ = client.chat_completion(_payload())
    message = result["choices"][0]["message"]

    assert len(message.get("tool_calls") or []) == 2
    assert "[loop_guard_notice]" in (message.get("reasoning_content") or "")
    assert "8 identical read call" in message["reasoning_content"]
    assert "[loop_guard_notice]" not in (message.get("content") or "")


def test_stream_blocked_tool_notice_survives_alongside_valid_native_calls():
    client = _make_client()
    events = [_native_open_event("call_bad", "turn0search1")]
    events.append(
        {
            "status": "finish",
            "parts": [
                {
                    "logic_id": "good-read",
                    "status": "finish",
                    "content": [
                        {
                            "type": "tool_calls",
                            "tool_calls": {
                                "name": "read",
                                "id": "read-good",
                                "arguments": {"filePath": "/workspaces/MAIN/README.md"},
                            },
                        }
                    ],
                }
            ],
        }
    )
    client._open_chat_stream = lambda p, preferred_account_index=None, filtered_tools=None: (
        _FakeResponse(events),
        "assistant-1",
    )

    text = "".join(c.decode("utf-8") for c in client.stream_chat_completion(_payload()))

    assert "[blocked_tool_notice]" in text
    assert "open" in text
    assert "NOT executed" in text
    assert '"name":"read"' in text
    assert '"name":"open"' not in text


def test_stream_loop_guard_notice_survives_alongside_valid_native_calls():
    client = _make_client()
    events = [_native_open_event(f"call_{index}") for index in range(6)]
    events.append(
        {
            "status": "finish",
            "parts": [
                {
                    "logic_id": "good-read",
                    "status": "finish",
                    "content": [
                        {
                            "type": "tool_calls",
                            "tool_calls": {
                                "name": "read",
                                "id": "read-good",
                                "arguments": {"filePath": "/workspaces/MAIN/README.md"},
                            },
                        }
                    ],
                }
            ],
        }
    )
    client._open_chat_stream = lambda p, preferred_account_index=None, filtered_tools=None: (
        _FakeResponse(events),
        "assistant-1",
    )

    text = "".join(c.decode("utf-8") for c in client.stream_chat_completion(_payload()))

    assert "[loop_guard_notice]" in text
    assert "4 identical open call" in text
    assert "NO tool limit" in text
    assert '"name":"read"' in text
    assert '"name":"open"' not in text



def test_ohne_drops_keine_notice_im_strom():
    """Gegenprobe: ein turn mit zwei verschiedenen zielen darf keine
    alarmmeldung produzieren, sonst schickt der proxy bei jedem normalen
    tool-loop eine."""
    client = _make_client()
    events = [_native_open_event(f"call_a{i}", "/workspaces/MAIN/a.md") for i in range(2)]
    events += [_native_open_event(f"call_b{i}", "/workspaces/MAIN/b.md") for i in range(2)]
    client._open_chat_stream = lambda p, preferred_account_index=None, filtered_tools=None: (
        _FakeResponse(events),
        "assistant-1",
    )
    text = "".join(c.decode("utf-8") for c in client.stream_chat_completion(_payload()))
    assert "[loop_guard_notice]" not in text


# --- S-21: ehrliche Notice fuer AUSGEFUEHRTE native-remaps -------------------
#
# Live-Fall 2026-09-28 (`ses_f17123666ffeMwmhdXlMz3HO1l`): das modell rief
# ~40x `open`. Die meisten wurden vom proxy auf `read` gemappt und lieferten
# ECHTE ergebnisse; 4 `open`-aufrufe mit `ref_id=turn*search*` waren blockiert
# und erzeugten die blocked-notice "open wurde NICHT ausgefuehrt". Das modell
# bekam damit die widerspruechliche botschaft "open ist tot" NEBEN 15 fertigen
# `read`-ergebnissen — und produzierte die 15x-identische-open-schleife, weil
# es aus dieser luecke keine regel ableiten konnte. Die remap-notice schliesst
# genau diese luecke: sie benennt den gemappten, TATSAECHLICH ausgefuehrten
# namen und sagt "nutze ihn direkt".


def test_remap_notice_nennt_den_gemappten_echten_namen():
    from glm2api.services.glm_client import _native_remap_notice_text

    notice = _native_remap_notice_text([("open", "read")])
    # `read` ist der name, unter dem der call WIRKLICH lief.
    assert "[native_remap_notice]" in notice
    assert "`open`" in notice and "`read`" in notice
    # das ergebnis ist echt — sonst wuerde das modell weiter `open` probieren.
    assert "are real" in notice or "is real" in notice
    # und es wird zum GEBRAUCH des richtigen namens angewiesen.
    assert "DIRECTLY" in notice


def test_remap_notice_erklaert_open_zu_webfetch_zu_read_mehrfach():
    from glm2api.services.glm_client import _native_remap_notice_text

    notice = _native_remap_notice_text([("open", "read"), ("open", "webfetch")])
    assert "`read`" in notice and "`webfetch`" in notice
    # der native name wird als ausfuehrendes mapping benannt, nicht als tot.
    assert "transparently executed" in notice


def test_remap_notice_nennt_keinen_nicht_mappbaren_pfad():
    """Sie darf das mapping nicht als verlaesslichen vertrag behaupten —
    genau daran ist der live-fall gescheitert (nicht-abbildbares ziel)."""
    from glm2api.services.glm_client import _native_remap_notice_text

    notice = _native_remap_notice_text([("open", "read")])
    assert "not mappable" in notice
    assert "compatibility" in notice


def test_ohne_remaps_keine_notice():
    from glm2api.services.glm_client import _native_remap_notice_text

    assert _native_remap_notice_text([]) == ""
    assert _native_remap_notice_text(None) == ""
    assert _native_remap_notice_text("kein-paar") == ""


def test_stream_remap_notice_erscheint_bei_gemapptem_open():
    """Ein `open`, das als `read` ausgefuehrt wurde, erzeugt die notice."""
    client = _make_client()
    events = [_native_open_event("call_m", "/workspaces/MAIN/README.md")]
    client._open_chat_stream = lambda p, preferred_account_index=None, filtered_tools=None: (
        _FakeResponse(events),
        "assistant-1",
    )
    text = "".join(c.decode("utf-8") for c in client.stream_chat_completion(_payload()))
    assert "[native_remap_notice]" in text
    assert "`read`" in text


def test_stream_remap_und_blocked_notice_koexistieren_konsistent():
    """Der Kern des Live-Falls: EIN turn mit gemappten `open`-aufrufen
    (ausgefuehrt) UND blockierten `open`-aufrufen (nicht ausgefuehrt). Beide
    notices muessen dastehen und sich NICHT widersprechen: die remap-notice
    zuerst (ergebnis echt), die blocked-notice danach (nur die nicht
    abbildbaren liefen nicht)."""
    client = _make_client()
    # zwei init-events: ein abbildbares open (Pfad -> read) und ein
    # nicht-abbildbares (turn0search1 -> blockiert), dann das finish-event,
    # das den turn beendet.
    events = [
        _native_open_event("call_ok", "/workspaces/MAIN/README.md"),
        _native_open_event("call_bad", "turn0search1"),
        {"status": "finish", "parts": []},
    ]
    client._open_chat_stream = lambda p, preferred_account_index=None, filtered_tools=None: (
        _FakeResponse(events),
        "assistant-1",
    )
    text = "".join(c.decode("utf-8") for c in client.stream_chat_completion(_payload()))

    assert "[native_remap_notice]" in text, "ausgefuehrtes mapping muss sichtbar sein"
    assert "[blocked_tool_notice]" in text, "blockierter versuch muss sichtbar bleiben"
    # reihenfolge: erst das echte ergebnis, dann die nicht-ausfuehrung.
    assert text.index("[native_remap_notice]") < text.index("[blocked_tool_notice]")
    # die remap-notice sagt "ergebnis ist echt", die blocked-notice
    # "nicht ausgefuehrt" — kein widerspruch, weil sie verschiedene calls
    # beschreibt. Kern: das modell wird auf `read` verwiesen.
    assert "`read`" in text


def test_remap_zaehlt_nicht_als_blockiert():
    """Ein erfolgreich gemappter `open` darf NICHT als blockierter versuch
    enden — sonst greift die negative-follow-up-runde grundlos und der
    korrekte `read`-call geht verloren."""
    from glm2api.services.translator import GLMEventAccumulator

    acc = GLMEventAccumulator(model="m", allowed_tool_names={"read", "webfetch", "bash"})
    event = {
        "status": "finish",
        "parts": [
            {
                "id": "p1",
                "logic_id": "l1",
                "role": "assistant",
                "status": "finish",
                "content": [
                    {
                        "type": "tool_calls",
                        "tool_calls": {
                            "id": "c1",
                            "name": "open",
                            "arguments": json.dumps({"open": [{"ref_id": "/workspaces/MAIN/README.md", "lineno": 1}]}),
                        },
                    }
                ],
            }
        ],
    }
    acc.consume_event(event)
    assert acc.blocked_tool_attempt_names == [], "gemappt darf nicht blockiert sein"
    assert ("open", "read") in acc.native_remapped_calls



# --- S-22: notices gehen in den DENKKANAL, nicht in den sichtbaren text -------
#
# Live-Befund 2026-09-28 (Session `build` + `glm-5.3`, Ordnervergleich): die
# notices wurden per `content`-delta in die antwort geschrieben und landeten
# mitten im sichtbaren text — der client zeigte
#   "Abbruch ehrlich gem [loop_guard_notice] 8 identical open call(s) ...
#    [native_remap_notice] ... [blocked_tool_notice] ..."
# als EINE normale antwort. Das modell las die notices als teil seiner
# eigenen narration und produzierte genau die drift, die sie verhindern
# sollen. Der kanal IST die botschaft.


def test_stream_notice_stand_im_denkkanal_nicht_im_text():
    client = _make_client()
    events = [_native_open_event("call_m", "/workspaces/MAIN/README.md")]
    client._open_chat_stream = lambda p, preferred_account_index=None, filtered_tools=None: (
        _FakeResponse(events),
        "assistant-1",
    )
    text = "".join(c.decode("utf-8") for c in client.stream_chat_completion(_payload()))

    # Die notice MUSS als reasoning_content raus ...
    assert '"reasoning_content":"[native_remap_notice]' in text.replace("\\n", ""), (
        "die notice muss im denkkanal stehen"
    )
    # ... und darf NICHT als sichtbarer content-delta erscheinen.
    assert '"content":"[native_remap_notice]' not in text, (
        "die notice darf nicht im sichtbaren text stehen (live-bug 2026-09-28)"
    )


def test_stream_notices_kommen_in_fester_reihenfolge_remap_blocked_loop():
    """S-22 (bug 3): der prepend-stempel kehrt die reihenfolge um. Bei mehr
    als drei notices pro turn (live: loop, remap, blocked, remap, blocked)
    wich die ausgabe von der beabsichtigten ab. Jetzt explizit gebaut."""
    client = _make_client()
    events = [
        _native_open_event("ok1", "/workspaces/MAIN/README.md"),
        _native_open_event("bad1", "turn0search0"),
    ] + [_native_open_event(f"dup{i}", "/workspaces/MAIN/a.md") for i in range(4)]
    events.append({"status": "finish", "parts": []})
    client._open_chat_stream = lambda p, preferred_account_index=None, filtered_tools=None: (
        _FakeResponse(events),
        "assistant-1",
    )
    text = "".join(c.decode("utf-8") for c in client.stream_chat_completion(_payload()))

    positions = {}
    for tag in ("native_remap_notice", "blocked_tool_notice", "loop_guard_notice"):
        idx = text.find(f"[{tag}]")
        assert idx >= 0, f"{tag} fehlt im stream"
        positions[tag] = idx
    assert positions["native_remap_notice"] < positions["blocked_tool_notice"], (
        "remap muss vor blocked stehen: 'ergebnis ist echt' vor 'lief nicht'"
    )
    assert positions["blocked_tool_notice"] < positions["loop_guard_notice"], (
        "blocked muss vor loop stehen"
    )


def test_non_stream_notice_stand_im_denkkanal_nicht_im_text():
    from glm2api.services.glm_client import _native_remap_notice_text, _loop_guard_notice_text
    from glm2api.services.translator import GLMEventAccumulator

    acc = GLMEventAccumulator(model="m", allowed_tool_names={"read", "bash", "webfetch"})
    acc.consume_event(_native_open_event("call_m", "/workspaces/MAIN/README.md"))
    acc.loop_guard_dropped_count = 2
    acc.loop_guard_dropped_tools = ["open"]

    result = {"choices": [{"index": 0, "message": {"content": "echte antwort"}}]}
    client = _make_client()
    client._inject_turn_notices(result, acc)
    message = result["choices"][0]["message"]

    assert "[native_remap_notice]" in (message.get("reasoning_content") or "")
    assert "[loop_guard_notice]" in (message.get("reasoning_content") or "")
    # der sichtbare text bleibt unberuehrt — das ist der eigentliche fix.
    assert message["content"] == "echte antwort", (
        "die notices duerfen den sichtbaren text nicht veraendern (live-bug)"
    )
