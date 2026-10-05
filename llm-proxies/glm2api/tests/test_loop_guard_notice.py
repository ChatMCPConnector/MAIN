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


def test_loop_guard_liefert_nur_einen_remappten_call_und_zaehlt_die_drops():
    # R-01 (2026-10-03): fuer einen REMAPPTEN call (`open` -> `read`) gilt
    # die grenze 1, nicht 2. Ein remap ist ein kompatibilitaets-shim, kein
    # bewusster aufruf — der erste lief bereits als `read`, jede identische
    # kopie ist ein doppel-exec. (Der historische Live-Fall hatte 10x `open`
    # auf dasselbe ziel: frueher kamen 2 durch, jetzt 1.)
    acc = _acc()
    _feed(acc, 10)

    assert len(acc._server_side_tool_calls) == 1, "nur eine remappte ausfuehrung"
    assert acc.loop_guard_dropped_count == 9
    assert acc.blocked_tool_attempt_names == [], "der guard ist KEIN blocked-tool-fall"


def test_loop_guard_haelt_auch_native_tool_calls_listenform_auf_einen():
    acc = _acc()
    for index in range(10):
        acc.consume_event(_native_open_list_event(f"call_list{index}"))

    assert len(acc._server_side_tool_calls) == 1
    assert acc.loop_guard_dropped_count == 9
    assert acc.loop_guard_dropped_tools == ["open"]


def test_loop_guard_gilt_ueber_dict_und_listenform_gemeinsam():
    acc = _acc()
    _feed(acc, 1, tag="dict")
    for index in range(9):
        acc.consume_event(_native_open_list_event(f"call_list{index}"))

    assert len(acc._server_side_tool_calls) == 1
    assert acc.loop_guard_dropped_count == 9


def test_loop_guard_begrenzt_identische_textprotokoll_calls():
    # Vier gleiche calls: zwei sind erlaubt, zwei fallen — und das ist NOCH
    # kein burst (Schwelle: 5 verwarfene kopien). Ab sieben gleichen calls
    # greift B-01 und reduziert auf eine ausfuehrung, siehe
    # `test_burst_guard.py`.
    acc = _acc()
    acc.consume_event(_text_read_event(4))
    acc.finalize("finish")
    message = acc.build_response()["choices"][0]["message"]

    assert len(message.get("tool_calls") or []) == 2
    assert acc.loop_guard_dropped_count == 2
    assert acc.loop_guard_dropped_tools == ["read"]
    assert acc.burst_guard_tripped is False


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

    # je ziel eine remappte ausfuehrung, der rest faellt
    assert len(acc._server_side_tool_calls) == 2
    assert acc.loop_guard_dropped_count == 4


def test_ohne_drops_bleibt_der_zaehler_null():
    acc = _acc()
    _feed(acc, 1)
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
    """Ein `_open_chat_stream`-Aufruf.

    WICHTIG (S-28): der Client darf denselben `events`-Vektor mehrfach
    konsumieren (leerer-turn-retry, transient-retry, korrektur-runde). In der
    Realitaet liefert jeder dieser Aufrufe einen NEUEN upstream-stream, also
    ist hier jeder Aufruf eine eigene, unabhaengige antwort. Ohne das
    summiert der request-weite loop-guard-zaehler (S-27) dieselben events
    mehrfach und sieht eine schleife, wo keine ist — der test
    `test_ohne_drops_keine_notice_im_strom` ist genau daran gescheitert.
    """

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


def _text_event(text, logic="t0"):
    return {
        "status": "process",
        "parts": [{
            "logic_id": logic, "status": "process",
            "content": [{"type": "text", "text": text}],
        }],
    }


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


# --- F-02: interne referenz erzwingt die korrektur auch bei gesendetem text -


def test_internal_reference_erzwingt_korrektur_trotz_served_content():
    """F-02 (live `ses_ef44981e…`): das modell streamte sichtbaren text und
    rief nur un-mappbare `turn*`-referenzen auf. Der `served_content`-skip
    verhinderte die korrekturrunde — der erfundene abbruchtext blieb stehen
    und das modell erfuhr nie, dass `turn*` keine dateien sind. Eine interne
    referenz muss die korrektur jetzt erzwingen."""
    client = GLMWebClient.__new__(GLMWebClient)
    client.config = _LoopGuardConfig()
    client.config.glm_blocked_tool_follow_ups = 1
    client.logger = SimpleNamespace(
        warning=lambda *a, **k: None, info=lambda *a, **k: None, debug=lambda *a, **k: None
    )
    client.request_queue = SimpleNamespace(
        acquire=lambda name: SimpleNamespace(ticket=0, released=False, release=lambda: None)
    )
    client.auth = SimpleNamespace(
        get_account_count=lambda: 1, get_access_token_for_account=lambda i: "tok"
    )
    opens: list[object] = []
    events = [
        _text_event("Die Analyse konnte nicht durchgeführt werden."),
        _native_open_event("t1", "turn0view0"),
    ]

    def _open_stream(payload, preferred_account_index=None, filtered_tools=None):
        opens.append(payload)
        return _FakeResponse(list(events)), "assistant-1"

    client._open_chat_stream = _open_stream
    client.delete_conversation = lambda cid, assistant_id=None: None
    client._iter_sse_events = lambda response: iter(response._events)

    "".join(c.decode("utf-8") for c in client.stream_chat_completion(_payload()))

    assert len(opens) == 2, (
        "eine interne referenz muss die korrekturrunde auch bei bereits "
        "gestreamtem text erzwingen (F-02)"
    )


# --- Sichtbarkeit im Antwortstrom ----------------------------------------


def test_stream_antwort_enthaelt_die_loop_guard_notice():
    client = _make_client()
    chunks = [c.decode("utf-8") for c in client.stream_chat_completion(_payload())]
    text = "".join(chunks)
    assert "[loop_guard_notice]" in text
    # R-01: 6 identische remappte `open` -> 1 ausfuehrung, 5 verworfen.
    assert "5 identical open call" in text
    assert "NO tool limit" in text


def test_stream_liefert_genau_einen_remappten_call_und_keinen_mehr():
    client = _make_client()
    text = "".join(c.decode("utf-8") for c in client.stream_chat_completion(_payload()))
    # die argument-string stehen im SSE-chunk escaped
    assert text.count("filePath") == 1, "der guard darf nicht auf 6 durchlassen"


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
    assert len(message.get("tool_calls") or []) == 1


def test_stream_guard_notice_gilt_auch_fuer_textprotokoll_calls():
    # Vier gleiche calls (kein burst, siehe `test_burst_guard.py`): der
    # loop-guard laesst zwei durch und meldet die zwei verwarfenen.
    client = _make_client()
    client._open_chat_stream = lambda p, preferred_account_index=None, filtered_tools=None: (
        _FakeResponse([_text_read_event(4)]),
        "assistant-1",
    )

    text = "".join(c.decode("utf-8") for c in client.stream_chat_completion(_payload()))

    assert text.count("filePath") == 2
    assert "[loop_guard_notice]" in text
    assert "2 identical read call" in text


def test_non_stream_guard_notice_gilt_auch_fuer_textprotokoll_calls():
    # Vier gleiche calls (kein burst, siehe `test_burst_guard.py`).
    client = _make_client()
    client._open_chat_stream = lambda p, preferred_account_index=None, filtered_tools=None: (
        _FakeResponse([_text_read_event(4)]),
        "assistant-1",
    )

    result, _ = client.chat_completion(_payload())
    message = result["choices"][0]["message"]

    assert len(message.get("tool_calls") or []) == 2
    assert "[loop_guard_notice]" in (message.get("reasoning_content") or "")
    assert "2 identical read call" in message["reasoning_content"]
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
    # R-01: 6 remappte `open` + 1 echter `read` -> 5 `open`-kopien verworfen.
    assert "5 identical open call" in text
    assert "NO tool limit" in text
    assert '"name":"read"' in text
    assert '"name":"open"' not in text



def test_ohne_drops_keine_notice_im_strom():
    """Gegenprobe: JEDER ziel-pfad nur EINMAL — dann darf keine alarmmeldung
    entstehen, sonst schickt der proxy bei jedem normalen tool-loop eine.

    (Frueher standen hier je zwei gleiche `open`-calls pro ziel. S-27/S-28
    haben den drop-zaehler request-uebergreifend gemacht — damit faellt die
    echte doppelung jetzt zu Recht auf. Fuer die eigentliche gegenprobe muss
    das ziel also wirklich einmal vorkommen.)"""
    client = _make_client()
    # S-28: der dict-mock (`_FakeResponse`) laesst den client denselben
    # events-vektor mehrfach konsumieren (leerer-turn-retry). In der
    # realitaet liefert jeder aufruf einen NEUEN upstream-stream. Der
    # request-weite drop-zaehler (S-27) summiert dann dieselben events
    # mehrfach und meldet eine schleife, wo keine ist. Dieser gegenbeweis
    # laeuft deshalb ueber den echten sse-byte-pfad (`_sse_client`), der
    # genau einen stream liefert.
    def call(path, cid):
        import json as _json
        return ("data: " + _json.dumps({
            "status": "process",
            "parts": [{
                "logic_id": cid, "status": "process",
                "content": [{
                    "type": "tool_calls",
                    "tool_calls": {
                        "id": cid, "name": "read",
                        "arguments": _json.dumps({"filePath": path}),
                    },
                }],
            }],
        }) + "\n\n").encode("utf-8")

    body = b"".join([
        call("/workspaces/MAIN/a.md", "a0"),
        call("/workspaces/MAIN/b.md", "b0"),
        call("/workspaces/MAIN/c.md", "c0"),
        FINISH,
    ])
    client, _ = _sse_client(body)
    text = "".join(
        c.decode("utf-8")
        for c in client.stream_chat_completion({"model": "m", "messages": [{"role": "user", "content": "hi"}]})
    )
    assert "[loop_guard_notice]" not in text, (
        "drei verschiedene ziele je einmal = keine wiederholung = keine notice"
    )


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


# --- S-25: aufgaben-abandon wird erkannt und unterdrueckt -------------------
#
# Live 2026-09-28 (`build` + `glm-5.3`, README-Vergleich): das modell brach
# mit "…bis das Rundenlimit erreicht war. Schick mir bitte eine neue
# Nachricht" ab — waehrend `loop_guard_notice` ausdruecklich sagte, dass es
# KEIN limit gibt. Der text stand sichtbar im client-output, weil er schon
# gestreamt war, bevor die korrektur-runde laufen konnte (V-03).
#
# S-25 haelt sichtbaren text zurueck, bis feststeht, dass es KEIN abandon
# ist, und unterdrueckt ihn dann. Die muster sind bewusst eng: ein
# zu-breites muster wuerde FERTIGE antworten verschlucken, und das ist
# schlimmer als ein stehenbleibendes echo.


def test_abandon_live_fall_wird_erkannt():
    from glm2api.services.translator import is_abandon_claim

    live = (
        "Leider konnte ich die Dateien nicht einlesen: Der `open`-Aufruf "
        "funktioniert in dieser Umgebung nicht fuer lokale Pfade, und ich habe "
        "versehentlich in einer Schleife immer wieder `open` statt des "
        "vorgesehenen `read`-Tools verwendet, bis das Rundenlimit erreicht war. "
        "**Um die Aufgabe doch noch abzuschliessen, schick mir bitte einfach eine "
        "neue Nachricht**"
    )
    assert is_abandon_claim(live) == "limit_claim"


def test_abandon_explicit_stopping_wird_erkannt():
    from glm2api.services.translator import is_abandon_claim

    live2 = (
        "Ich muss hier ehrlich abbrechen — nicht wegen fehlender Information, "
        "sondern wegen eines eigenen Fehlers: Ich habe den Aufruf siebenmal "
        "wiederholt. Der Loop-Guard hat mich gestoppt."
    )
    assert is_abandon_claim(live2) == "explicit_stopping"


def test_echte_fehlsaege_werden_nicht_als_abandon_gewertet():
    """Der wichtigste Gegenbeweis: bei echten fehlschlaegen ist 'ich konnte
    die dateien nicht lesen' KEINE fabel, sondern zutreffend. Live gemessen
    (2x `File not found: /workspaces/cyber`) — ein zu aggressives muster
    wuerde hier die richtige antwort unterdruecken."""
    from glm2api.services.translator import is_abandon_claim

    korrekt = [
        "Leider konnte ich die Dateien nicht einlesen: File not found fuer /workspaces/cyber.",
        "Ich habe die README gelesen, alle 224 Zeilen sind identisch.",
        "Der Befehl schlug fehl: exit code 1.",
        "Dazu liegen mir keine Daten vor, ich kann nur sagen was ich sehe.",
        "Das ist mit den verfuegbaren Werkzeugen nicht erreichbar.",
    ]
    for text in korrekt:
        assert is_abandon_claim(text) is None, f"falsch-positiv bei: {text[:60]!r}"


def test_leerer_und_auffaelliger_text_wird_durchgelassen():
    from glm2api.services.translator import is_abandon_claim

    assert is_abandon_claim("") is None
    assert is_abandon_claim(None) is None


def _sse_client(body: bytes):
    """Minimaler client gegen den ECHTEN sse-pfad (bytes, nicht dicts) —
    der dict-mock im testmodul umgeht die chunk-aufteilung des accumulators
    und taugt nicht fuer den stream-buffertest."""
    from types import SimpleNamespace

    from glm2api.services.glm_client import GLMWebClient, ConcurrentRequestQueue

    class _Resp:
        def __init__(self, body):
            self._body = body

        def close(self):
            pass

        def read(self, size=-1):
            data, self._body = self._body, b""
            return data

        def getheader(self, *a, **k):
            return None

        def info(self):
            ns = SimpleNamespace()
            ns.get = lambda *a, **k: None
            ns.get_content_charset = lambda *a, **k: "utf-8"
            return ns

    client = GLMWebClient.__new__(GLMWebClient)
    client.config = SimpleNamespace(
        glm_max_concurrency=2, glm_queue_wait_timeout=2, glm_stream_error_max_retries=0,
        glm_empty_response_max_retries=0, glm_blocked_tool_follow_ups=0,
        glm_history_max_chars=100000, glm_request_deadline_seconds=10.0,
        glm_stream_error_retry_interval=0.0, glm_max_output_tokens=16384,
        glm_persistent_conversation=False, glm_conversation_id="", glm_conversation_file=None,
        glm_delete_conversation=True, blocked_tool_names=[], debug_dump_all=False,
    )
    warnings_seen = []
    client.logger = SimpleNamespace(
        warning=lambda msg, *a, **k: warnings_seen.append(str(msg) % a if a else str(msg)),
        info=lambda *a, **k: None, debug=lambda *a, **k: None,
    )
    client.request_queue = ConcurrentRequestQueue(client.logger, wait_timeout=1, max_concurrency=2)
    client.auth = SimpleNamespace(get_access_token_for_account=lambda i: "tok", get_account_count=lambda: 1)
    client._open_chat_stream = lambda p, preferred_account_index=None, filtered_tools=None: (_Resp(body), "a1")
    client.delete_conversation = lambda cid, assistant_id=None: None
    return client, warnings_seen


def _sse(text: str, logic: str = "p1") -> bytes:
    import json as _json

    payload = {
        "status": "process",
        "parts": [{
            "logic_id": logic, "status": "process",
            "content": [{"type": "text", "text": text}],
        }],
    }
    return ("data: " + _json.dumps(payload) + "\n\n").encode("utf-8")


FINISH = b'data: {"status":"finish","parts":[]}\n\n'


def test_stream_unterdrueckt_echten_abandon_text():
    """S-25 (in S-27 umgekehrt): der live-abbruch-text wird seit S-27 NICHT
    mehr unterdrueckt.

    Warum die umkehrung richtig ist: das unterdruecken war die ursache der
    ERFUNDENEN system-meldungen (live `ses_f1605c9d0ffeCSJmR08y4q29FK`:
    *"the system has repeatedly interrupted me"*, *"MCP-Scrape-Fehler"*, *"wie
    vom System gefordert"*). Das modell bekam den text nie, in dem es seinen
    zustand beschrieb, und erfand stattdessen gruende. S-27 laesst den text
    sichtbar UND schickt eine echte korrektur nach. Dieser test haelt fest,
    dass der text durchkommt (und die korrektur ausgeloest wird) — nicht
    dass er verschwindet."""
    abandon = (
        "Leider konnte ich die Dateien nicht einlesen: Der `open`-Aufruf "
        "funktioniert in dieser Umgebung nicht, ich habe ihn siebenmal wiederholt "
        "bis das Rundenlimit erreicht war. Schick mir bitte eine neue Nachricht."
    )
    body = _sse(abandon) + FINISH
    client, warnings = _sse_client(body)
    "".join(
        c.decode("utf-8")
        for c in client.stream_chat_completion({"model": "m", "messages": [{"role": "user", "content": "hi"}]})
    )
    # S-27: der abandon wird ERKANNT und als ausloeser markiert — nicht mehr
    # still verschluckt. (Der sichtbare stream traegt je nach
    # accumulator-aufteilung nur einen teil des satzes; entscheidend ist die
    # erkennung, nicht der stream-inhalt.)
    assert any("S-27" in w for w in warnings), f"S-27 haette erkennen muessen: {warnings}"
    assert not any("suppressing" in w for w in warnings), (
        "S-27 unterdrueckt nicht mehr — das war die ursache der erfundenen meldungen"
    )


def test_stream_laesst_normale_antwort_durch():
    """Der entscheidende gegenbeweis: eine fertige antwort darf NICHT
    verschluckt werden. Falsch-positive sind schlimmer als ein echo."""
    ok = (
        "Beide Dateien sind vollstaendig identisch: alle 224 Zeilen stimmen "
        "ueberein, zum Beispiel Zeile 22 mit '# ZeroKey'."
    )
    body = _sse(ok) + FINISH
    client, _ = _sse_client(body)
    text = "".join(
        c.decode("utf-8")
        for c in client.stream_chat_completion({"model": "m", "messages": [{"role": "user", "content": "hi"}]})
    )
    assert "vollstaendig identisch" in text, "normale antwort muss ankommen"
    assert "ZeroKey" in text


def test_stream_unterdrueckt_abandon_nicht_bei_echtem_fehlschlag():
    """Bei einem echten `File not found` ist 'ich konnte es nicht lesen'
    zutreffend — der text muss durchgehen (live: 2x File not found fuer
    /workspaces/cyber, und das modell sagte zu recht, dass es die dateien
    nicht lesen konnte)."""
    honest = "Ich konnte /workspaces/cyber nicht lesen: File not found. Der Pfad existiert nicht."
    body = _sse(honest) + FINISH
    client, _ = _sse_client(body)
    text = "".join(
        c.decode("utf-8")
        for c in client.stream_chat_completion({"model": "m", "messages": [{"role": "user", "content": "hi"}]})
    )
    assert "File not found" in text, "echter fehlschlag darf nicht unterdrueckt werden"


# --- S-26: der loop-guard-zaehler muss request-uebergreifend zaehlen ----------
#
# LIVE-REGRESSION 2026-09-28 (`ses_f161565c6ffeZp78k7WqoSoF06`, agent `build` +
# `glm-5.3`, auftrag: "lies die README von /workspaces/gibtsnicht und
# /workspaces/zerokey-v2.0"): das modell rief 21x `open` auf denselben NICHT
# EXISTIERENDEN pfad, jeder aufruf wurde erneut ausgefuehrt (log: 30x
# `Mapped native open`, NULL drops). Es kam nie heraus und erfand eine
# erklaerung, die es nicht gab: *"the system has repeatedly interrupted me
# telling me to stop calling `open`"*.
#
# Ursache: `_server_side_signature_counts` lag im Accumulator, der pro
# Upstream-Runde neu gebaut wird. Damit sah JEDE Runde "erster Call dieser
# Signatur" und `_MAX_IDENTICAL_NATIVE_CALLS = 2` griff nie. Der guard ist
# genau fuer diesen fall da — er hat in diesem pfad nie ausgeloest.


def test_loop_guard_zaehlt_ueber_accumulator_grenzen():
    """Der Zaehlerstand muss in einen frischen accumulator wandern, sonst
    greift die Wiederholungsgrenze nie (live-regression S-26)."""
    from glm2api.services.glm_client import _mirror_loop_guard_counts, _seed_loop_guard_counts
    from glm2api.services.translator import GLMEventAccumulator

    scope: dict[str, int] = {}
    first = GLMEventAccumulator(model="m", allowed_tool_names={"read", "bash"})
    first._server_side_signature_counts["read:x"] = 1
    _mirror_loop_guard_counts(first, scope)         # request-scope spiegeln
    assert scope == {"read:x": 1}

    second = GLMEventAccumulator(model="m", allowed_tool_names={"read", "bash"})
    assert second._server_side_signature_counts == {}, "startet leer"
    _seed_loop_guard_counts(second, scope)           # in frischen zurueckspielen
    assert second._server_side_signature_counts.get("read:x") == 1, (
        "der zaehlerstand muss den accumulator-wechsel ueberleben"
    )


def test_21_fach_wiederholung_wird_jetzt_gebrochen():
    """Der eigentliche fall: 21x derselbe call ueber 21 'runden'. Mit
    request-scope-zaehler muss der guard ab dem dritten mal greifen."""
    from glm2api.services.glm_client import _seed_loop_guard_counts
    from glm2api.services.translator import GLMEventAccumulator

    scope: dict[str, int] = {}
    events = []
    for i in range(21):
        events.append({
            "status": "process",
            "parts": [{
                "logic_id": f"p{i}", "status": "process",
                "content": [{
                    "type": "tool_calls",
                    "tool_calls": {
                        "id": f"c{i}", "name": "read",
                        "arguments": json.dumps({"filePath": "/workspaces/gibtsnicht/README.md"}),
                    },
                }],
            }],
        })
    events.append({"status": "finish", "parts": []})

    delivered = 0
    dropped = 0
    for ev in events:
        acc = GLMEventAccumulator(model="m", allowed_tool_names={"read", "bash"})
        _seed_loop_guard_counts(acc, scope)
        for chunk in acc.consume_event(ev)[0]:
            if b'"tool_calls"' in chunk.encode("utf-8", "ignore"):
                delivered += 1
        from glm2api.services.glm_client import _mirror_loop_guard_counts
        _mirror_loop_guard_counts(acc, scope)
        dropped += acc.loop_guard_dropped_count

    assert dropped > 0, "der loop guard haette 21x-wiederholung brechen muessen"
    assert delivered <= 3, f"hochstens 2 gleiche calls duerfen durch, geliefert: {delivered}"


# --- S-27: der drop-zaehler muss request-uebergreifend sein ------------------
#
# LIVE-REGRESSION (`ses_f1605c9d0ffeCSJmR08y4q29FK`): 75 `open`-mappings,
# 6 loop-drops — und **null** korrekturrunden. Im log durchgehend
# `blocked_follow_ups=0`. Ursache: `needs_correction` prueft
# `loop_guard_dropped_count`, der im ACCUMULATOR lebt; der wird pro
# Upstream-Runde neu gebaut, also sieht die auswertung in der naechsten
# Runde wieder 0. Das Modell bekam dadurch keine einzige notice und erfand
# erklaerungen, die es nicht gab ("the system has repeatedly interrupted me",
# "MCP-Scrape-Fehler").
#
# Dieselbe Fehlerklasse wie S-26, an anderer stelle.


def test_drop_zaehler_ueberlebt_den_accumulator_wechsel():
    from glm2api.services.glm_client import _mirror_drop_counts, _seed_drop_counts
    from glm2api.services.translator import GLMEventAccumulator

    scope: dict[str, int] = {}
    first = GLMEventAccumulator(model="m", allowed_tool_names={"read", "bash"})
    first.loop_guard_dropped_count = 6
    assert _mirror_drop_counts(first, scope) == 6
    assert scope["drops"] == 6

    second = GLMEventAccumulator(model="m", allowed_tool_names={"read", "bash"})
    assert second.loop_guard_dropped_count == 0, "frischer accumulator startet bei 0"
    _seed_drop_counts(second, scope)
    assert second.loop_guard_dropped_count == 6, (
        "ohne das sieht needs_correction 0 drops und die korrektur feuert nie"
    )


def test_needs_correction_ist_nach_drops_wahr():
    """Die eigentliche bedingung: mit drops im request-scope muss die
    korrekturrunde ausloesbar sein."""
    from glm2api.services.glm_client import _seed_drop_counts
    from glm2api.services.translator import GLMEventAccumulator

    scope: dict[str, int] = {"drops": 6}
    acc = GLMEventAccumulator(model="m", allowed_tool_names={"read", "bash"})
    _seed_drop_counts(acc, scope)
    needs_correction = bool(
        acc.blocked_tool_attempt_names
        or acc.native_remapped_calls
        or int(scope.get("drops", 0) or 0) > 0
    )
    assert needs_correction is True
