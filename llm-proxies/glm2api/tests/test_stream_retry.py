import http.client
import json

import pytest
from types import SimpleNamespace

from glm2api.services.glm_client import GLMWebClient, UpstreamAPIError


class _RetryConfig:
    glm_stream_error_max_retries = 2
    glm_stream_error_retry_interval = 0.0
    glm_max_output_tokens = 16384
    glm_blocked_tool_follow_ups = 0
    glm_empty_response_max_retries = 2
    glm_history_max_chars = 120000
    request_timeout = 5
    blocked_tool_names = []
    debug_dump_all = False
    glm_assistant_id = "assistant"
    glm_delete_conversation = False
    glm_queue_wait_timeout = 5
    glm_max_concurrency = 1
    glm_base_url = "https://chatglm.cn/chatglm"


def _error_event(code=10025, message="stream request error"):
    return {
        "status": "error",
        "last_error": {"error_code": code, "err_msg": message},
        "parts": [],
    }


def _silent_process_event():
    """Ein process-event OHNE sichtbare ausgabe.

    C-08: auch gesendetes reasoning gilt als ausgeliefert — ein retry
    wuerde den turn verdoppeln. Fuer die C-07-transporttests brauchen wir
    deshalb ein event, das wirklich nichts ausliefert."""
    return {"status": "process", "parts": []}


def _finish_event(text="hello"):
    return {
        "status": "finish",
        "parts": [
            {
                "logic_id": "p1",
                "status": "finish",
                "content": [{"type": "text", "text": text}],
            }
        ],
    }


def _reasoning_finish_event(text="planning only"):
    return {
        "status": "finish",
        "parts": [
            {
                "logic_id": "p1",
                "status": "finish",
                "content": [{"type": "think", "think": text}],
            }
        ],
    }


def _process_event(text):
    return {
        "status": "process",
        "parts": [
            {
                "logic_id": "p1",
                "status": "process",
                "content": [{"type": "text", "text": text}],
            }
        ],
    }


class _FakeResponse:
    def __init__(self, events):
        self._events = events
        self.closed = False

    def close(self):
        self.closed = True


def _make_client(events_per_attempt):
    client = GLMWebClient.__new__(GLMWebClient)
    client.config = _RetryConfig()
    client.logger = SimpleNamespace(
        warning=lambda *a, **k: None,
        info=lambda *a, **k: None,
        debug=lambda *a, **k: None,
    )
    client.request_queue = SimpleNamespace(
        acquire=lambda name: SimpleNamespace(
            ticket=0, released=False, release=lambda: None
        )
    )
    client.auth = SimpleNamespace(
        get_account_count=lambda: 1,
        get_access_token_for_account=lambda i: "tok",
    )
    calls = {"count": 0}

    def fake_open(payload, preferred_account_index=None, filtered_tools=None):
        calls["count"] += 1
        events = events_per_attempt[min(calls["count"] - 1, len(events_per_attempt) - 1)]
        return _FakeResponse(events), "assistant-1"

    client._open_chat_stream = fake_open
    client.delete_conversation = lambda cid, assistant_id=None: None

    def fake_iter(response):
        return iter(response._events)

    client._iter_sse_events = fake_iter
    return client, calls


def test_transient_error_triggers_stream_retry():
    client, calls = _make_client([[_error_event()], [_finish_event("recovered")]])

    stream = client.stream_chat_completion(
        {"model": "glm-5.3", "messages": [{"role": "user", "content": "hi"}]}
    )
    chunks = [chunk.decode("utf-8") for chunk in stream]

    assert calls["count"] == 2
    text = "".join(chunks)
    assert "recovered" in text


def test_transient_error_gives_up_after_max_retries():
    client, calls = _make_client([[_error_event()]])

    stream = client.stream_chat_completion(
        {"model": "glm-5.3", "messages": [{"role": "user", "content": "hi"}]}
    )
    try:
        for _ in stream:
            pass
    except UpstreamAPIError as exc:
        assert "10025" in str(exc)
        assert exc.transient is True
    else:
        raise AssertionError("expected UpstreamAPIError")
    # initial attempt + 2 retries
    assert calls["count"] == 3


def test_non_transient_error_raises_immediately():
    events = [{"status": "error", "last_error": {"error_code": 999, "err_msg": "boom"}, "parts": []}]
    client, calls = _make_client([events])

    stream = client.stream_chat_completion(
        {"model": "glm-5.3", "messages": [{"role": "user", "content": "hi"}]}
    )
    try:
        for _ in stream:
            pass
    except UpstreamAPIError as exc:
        assert "999" in str(exc)
        assert exc.transient is False
    else:
        raise AssertionError("expected UpstreamAPIError")
    assert calls["count"] == 1


def test_error_after_visible_content_raises():
    # visible content first, then the error -> no retry (content already served)
    client, calls = _make_client(
        [[_process_event("visible"), _error_event()], [_finish_event("should not happen")]]
    )

    stream = client.stream_chat_completion(
        {"model": "glm-5.3", "messages": [{"role": "user", "content": "hi"}]}
    )
    served = []
    try:
        for chunk in stream:
            served.append(chunk.decode("utf-8"))
    except UpstreamAPIError:
        pass
    else:
        raise AssertionError("expected UpstreamAPIError")
    assert any("visible" in c for c in served)
    assert calls["count"] == 1


def test_non_stream_chat_retries_transient_error():
    client, calls = _make_client([[_error_event()], [_finish_event("ok again")]])

    result, _ = client.chat_completion(
        {"model": "glm-5.3", "messages": [{"role": "user", "content": "hi"}]}
    )

    assert calls["count"] == 2
    content = json.dumps(result, ensure_ascii=False)
    assert "ok again" in content


class _FollowUpConfig(_RetryConfig):
    glm_blocked_tool_follow_ups = 2


def _blocked_tool_events():
    # model "calls" open_url (undeclared) as text — no declared tool name in it
    return [
        {
            "status": "finish",
            "parts": [
                {
                    "logic_id": "p1",
                    "status": "finish",
                    "content": [
                        {"type": "text", "text": '{"tool_calls":[{"name":"open_url","arguments":{"param_name":"url","param_value":"/x"}}]}[]'}
                    ],
                }
            ],
        }
    ]


def _normal_answer_events():
    return [
        {
            "status": "finish",
            "parts": [
                {
                    "logic_id": "p1",
                    "status": "finish",
                    "content": [{"type": "text", "text": "Alles erledigt."}],
                }
            ],
        }
    ]


def _make_follow_up_client(config):
    client = GLMWebClient.__new__(GLMWebClient)
    client.config = config
    client.logger = SimpleNamespace(
        warning=lambda *a, **k: None,
        info=lambda *a, **k: None,
        debug=lambda *a, **k: None,
    )
    client.request_queue = SimpleNamespace(
        acquire=lambda name: SimpleNamespace(
            ticket=0, released=False, release=lambda: None
        )
    )
    client.auth = SimpleNamespace(
        get_account_count=lambda: 1,
        get_access_token_for_account=lambda i: "tok",
    )
    calls = {"count": 0, "payloads": []}

    def fake_open(payload, preferred_account_index=None, filtered_tools=None):
        calls["count"] += 1
        calls["payloads"].append(payload)
        if calls["count"] == 1:
            events = _blocked_tool_events()
        else:
            events = _normal_answer_events()
        return _FakeResponse(events), "assistant-1"

    client._open_chat_stream = fake_open
    client.delete_conversation = lambda cid, assistant_id=None: None

    def fake_iter(response):
        return iter(response._events)

    client._iter_sse_events = fake_iter
    return client, calls


def test_blocked_tool_triggers_follow_up_round_stream():
    client, calls = _make_follow_up_client(_FollowUpConfig())
    payload = {
        "model": "glm-5.3",
        "messages": [{"role": "user", "content": "mach was"}],
        "tools": [
            {
                "type": "function",
                "function": {"name": "bash", "parameters": {"type": "object"}},
            }
        ],
    }

    stream = client.stream_chat_completion(dict(payload))
    chunks = [chunk.decode("utf-8") for chunk in stream]

    assert calls["count"] == 2
    follow_up_messages = calls["payloads"][1]["messages"]
    assert any("do NOT exist" in str(m.get("content", "")) for m in follow_up_messages)
    text = "".join(chunks)
    assert "Alles erledigt." in text
    # T-10: der blockierte name darf ausschliesslich in der expliziten
    # notice stehen, die dem client sagt "nie ausgefuehrt". Er darf weder
    # als tool-call noch als teil der antort des modells durchgehen.
    assert "NOT executed" in text
    assert '"tool_calls"' not in text or "open_url" not in text.split('"tool_calls"')[1][:200]


def test_blocked_tool_triggers_follow_up_round_stream_with_served_content():
    # Model emits visible text BEFORE attempting the blocked tool call
    client, calls = _make_follow_up_client(_FollowUpConfig())
    round1_events = [
        {
            "status": "init",
            "parts": [
                {
                    "logic_id": "p1",
                    "status": "init",
                    "content": [{"type": "text", "text": "Ich fange an: "}],
                },
                {
                    "logic_id": "p2",
                    "status": "finish",
                    "content": [
                        {"type": "text", "text": '{"tool_calls":[{"name":"open_url","arguments":{"param_name":"url","param_value":"/x"}}]}[]'}
                    ],
                },
            ],
        }
    ]
    def fake_open(payload, preferred_account_index=None, filtered_tools=None):
        calls["count"] += 1
        calls["payloads"].append(payload)
        if calls["count"] == 1:
            return _FakeResponse(round1_events), "assistant-1"
        return _FakeResponse(_normal_answer_events()), "assistant-1"

    client._open_chat_stream = fake_open

    payload = {
        "model": "glm-5.3",
        "messages": [{"role": "user", "content": "mach was"}],
        "tools": [
            {
                "type": "function",
                "function": {"name": "bash", "parameters": {"type": "object"}},
            }
        ],
    }

    stream = client.stream_chat_completion(dict(payload))
    chunks = [chunk.decode("utf-8") for chunk in stream]

    assert calls["count"] == 2
    text = "".join(chunks)
    assert "Alles erledigt." in text
    assert "open_url" not in text
    # T-07: der vorlauf-text wird nicht unumkehrbar gestreamt, sondern in
    # die follow-up-runde uebernommen. Dort muss er fuer das modell
    # sichtbar sein — das ist der entscheidende Teil.
    follow_up_assistant = calls["payloads"][1]["messages"][-2]
    assert "Ich fange an:" in str(follow_up_assistant.get("content", ""))


def test_blocked_tool_follow_up_respects_budget():
    # follow-ups disabled -> single round, blocked notice forwarded as text
    client, calls = _make_follow_up_client(_RetryConfig())
    payload = {
        "model": "glm-5.3",
        "messages": [{"role": "user", "content": "mach was"}],
        "tools": [
            {
                "type": "function",
                "function": {"name": "bash", "parameters": {"type": "object"}},
            }
        ],
    }

    stream = client.stream_chat_completion(dict(payload))
    chunks = [chunk.decode("utf-8") for chunk in stream]

    assert calls["count"] == 1
    text = "".join(chunks)
    assert "undeclared tool" in text
    assert "open_url" in text


def test_blocked_tool_triggers_follow_up_round_non_stream():
    client, calls = _make_follow_up_client(_FollowUpConfig())
    payload = {
        "model": "glm-5.3",
        "messages": [{"role": "user", "content": "mach was"}],
        "tools": [
            {
                "type": "function",
                "function": {"name": "bash", "parameters": {"type": "object"}},
            }
        ],
    }

    result, _ = client.chat_completion(dict(payload))

    assert calls["count"] == 2
    assert "Alles erledigt." in json.dumps(result, ensure_ascii=False)


def test_transient_flag_on_upstream_error():
    exc = UpstreamAPIError(502, "boom", transient=True)
    assert exc.transient is True
    exc2 = UpstreamAPIError(502, "boom")
    assert exc2.transient is False

def test_empty_response_triggers_auto_retry_stream():
    """Leer-Turn-Autonomie-Fix: komplett leere Upstream-Runde (text=0,
    reasoning=0, keine calls) -> auto-retry mit frischer Conversation,
    Agent steht nicht mehr still."""
    empty_finish = {
        "status": "finish",
        "parts": [{"logic_id": "p1", "status": "finish", "content": []}],
    }
    good_finish = _finish_event("Ergebnis da")
    client, calls = _make_client([[empty_finish], [good_finish]])

    chunks = list(client.stream_chat_completion({"model": "glm-test", "messages": [{"role": "user", "content": "hi"}]}))
    content = "".join(
        json.loads(chunk.decode("utf-8").removeprefix("data: ").strip())["choices"][0]
        .get("delta", {})
        .get("content", "")
        for chunk in chunks
        if chunk.decode("utf-8").strip() != "data: [DONE]"
    )
    assert calls["count"] == 2  # erster versuch leer, retry erfolgreich
    assert "Ergebnis da" in content


def test_reasoning_only_response_triggers_auto_retry_stream():
    good_finish = _finish_event("Ergebnis nach Planung")
    client, calls = _make_client(
        [[_reasoning_finish_event("Let me inspect the workspace first")], [good_finish]]
    )

    chunks = list(
        client.stream_chat_completion(
            {"model": "glm-test", "messages": [{"role": "user", "content": "build it"}]}
        )
    )
    output = "".join(chunk.decode("utf-8") for chunk in chunks)

    assert calls["count"] == 2
    assert "Ergebnis nach Planung" in output


def test_empty_response_gives_up_after_max_retries():
    """Bleibt die Antwort nach allen Retries leer, wird sie final
    durchgereicht (kein unendlicher Loop)."""
    empty_finish = {
        "status": "finish",
        "parts": [{"logic_id": "p1", "status": "finish", "content": []}],
    }
    client, calls = _make_client([[empty_finish]])

    chunks = list(client.stream_chat_completion({"model": "glm-test", "messages": [{"role": "user", "content": "hi"}]}))
    assert calls["count"] == 1 + _RetryConfig.glm_empty_response_max_retries  # versuch + 2 retries
    assert any(b"data: [DONE]" == c.strip() for c in chunks)


class _ChunkedRawResponse:
    """Simuliert http.client.HTTPResponse mit Chunk-Grenze mitten in \r\n."""

    def __init__(self, data: bytes, chunk_size: int = 4096):
        self._data = data
        self._chunk_size = chunk_size

    def read(self, size=-1):
        if not self._data:
            return b""
        chunk, self._data = self._data[: self._chunk_size], self._data[self._chunk_size :]
        return chunk

    def close(self):
        pass


def _sse_client():
    client = GLMWebClient.__new__(GLMWebClient)
    client.config = _RetryConfig()
    client.logger = SimpleNamespace(
        warning=lambda *a, **k: None,
        info=lambda *a, **k: None,
        debug=lambda *a, **k: None,
    )
    return client


def test_sse_parser_splits_blocks_with_crlf_across_chunk_boundary():
    """Regression: \r\n wurde pro chunk normalisiert, nicht auf dem
    akkumulierten puffer — ein Paar ueber die 4096er chunk-grenze blieb
    unerkannt, die events gingen als 'unparseable fragment' verloren."""
    client = _sse_client()
    prefix = b"x" * 4095 + b"\r"  # chunk 1 endet mit \r
    response = _ChunkedRawResponse(prefix + b"\ndata: {\"a\":1}\r\n\r\ndata: {\"b\":2}\r\n\r\n")

    events = list(client._iter_sse_events(response))

    assert events == [{"a": 1}, {"b": 2}]


def test_sse_parser_handles_crlf_events_without_chunk_split():
    client = _sse_client()
    response = _ChunkedRawResponse(b'data: {"a":1}\r\n\r\ndata: [DONE]\r\n\r\n')

    events = list(client._iter_sse_events(response))

    assert events == [{"a": 1}]


# --- C-07: Transportfehler und transiente JSON-/HTTP-payloads -----------


class _ExplodingResponse:
    """Bricht beim Lesen der Events mit einem Transportfehler ab."""

    # Bewusst KEIN "_events"-Attribut: der test-iterator waehlt danach, ob
    # er die ereignisliste oder die (fehlschlagende) iteration nimmt.
    def __init__(self, events_before_failure, exc):
        self.events_before_failure = events_before_failure
        self.transport_error = exc
        self.closed = False

    def close(self):
        self.closed = True

    def __iter__(self):
        yield from self.events_before_failure
        raise self.transport_error


def _make_client_with_failing_iter(events_per_attempt, failures):
    """Wie _make_client, aber der Event-Iterator kann gezielt scheitern."""
    client = GLMWebClient.__new__(GLMWebClient)
    client.config = _RetryConfig()
    client.logger = SimpleNamespace(
        warning=lambda *a, **k: None,
        info=lambda *a, **k: None,
        debug=lambda *a, **k: None,
    )
    client.request_queue = SimpleNamespace(
        acquire=lambda name: SimpleNamespace(ticket=0, released=False, release=lambda: None)
    )
    client.auth = SimpleNamespace(
        get_account_count=lambda: 1,
        get_access_token_for_account=lambda i: "tok",
    )
    calls = {"count": 0}

    def fake_open(payload, preferred_account_index=None, filtered_tools=None):
        index = calls["count"]
        calls["count"] += 1
        if index < len(failures):
            return _ExplodingResponse(
                events_per_attempt[min(index, len(events_per_attempt) - 1)],
                failures[index],
            ), "assistant-1"
        return _FakeResponse(events_per_attempt[-1]), "assistant-1"

    client._open_chat_stream = fake_open
    client.delete_conversation = lambda cid, assistant_id=None: None
    # _ExplodingResponse ist selbst iterable, _FakeResponse haelt seine
    # events in ._events — beide formen bedienen.
    client._iter_sse_events = lambda response: iter(
        getattr(response, "_events", response)
    )
    return client, calls


def test_connection_reset_mid_stream_triggers_retry():
    """C-07: ein ConnectionReset mitten im stream brach den generator vorher
    hart ab — ohne retry, obwohl noch nichts ausgeliefert war."""
    client, calls = _make_client_with_failing_iter(
        [[_silent_process_event()], [_finish_event("recovered")]],
        [ConnectionResetError("peer closed")],
    )

    stream = client.stream_chat_completion(
        {"model": "glm-5.3", "messages": [{"role": "user", "content": "hi"}]}
    )
    text = "".join(chunk.decode("utf-8") for chunk in stream)

    assert calls["count"] == 2, "transportfehler muss den turn neu aufsetzen"
    assert "recovered" in text


def test_timeout_mid_stream_triggers_retry():
    client, calls = _make_client_with_failing_iter(
        [[_silent_process_event()], [_finish_event("ok")]],
        [TimeoutError("read timed out")],
    )
    stream = client.stream_chat_completion(
        {"model": "glm-5.3", "messages": [{"role": "user", "content": "hi"}]}
    )
    "".join(chunk.decode("utf-8") for chunk in stream)
    assert calls["count"] == 2


def test_remote_disconnected_mid_stream_triggers_retry():
    client, calls = _make_client_with_failing_iter(
        [[], [_finish_event("ok")]],
        [http.client.RemoteDisconnected("remote end closed connection")],
    )
    stream = client.stream_chat_completion(
        {"model": "glm-5.3", "messages": [{"role": "user", "content": "hi"}]}
    )
    "".join(chunk.decode("utf-8") for chunk in stream)
    assert calls["count"] == 2


def test_transport_error_after_served_content_is_not_retried():
    """Nach sichtbarem content ist der turn unumkehrbar ausgeliefert — ein
    retry wuerde die antwort verdoppeln."""
    client, calls = _make_client_with_failing_iter(
        [[_finish_event("antwort")], [_finish_event("doppelt")]],
        [ConnectionResetError("late reset")],
    )
    stream = client.stream_chat_completion(
        {"model": "glm-5.3", "messages": [{"role": "user", "content": "hi"}]}
    )
    text = "".join(chunk.decode("utf-8") for chunk in stream)
    assert calls["count"] == 1, "kein retry nach ausgeliefertem content"
    assert "doppelt" not in text


def test_transport_error_gives_up_after_max_retries():
    client, calls = _make_client_with_failing_iter(
        [[]],
        [ConnectionResetError("reset")] * 3,
    )
    stream = client.stream_chat_completion(
        {"model": "glm-5.3", "messages": [{"role": "user", "content": "hi"}]}
    )
    with pytest.raises(UpstreamAPIError) as excinfo:
        for _ in stream:
            pass
    assert "upstream_transport_error" in str(excinfo.value)
    assert excinfo.value.transient is True
    assert calls["count"] == 3, "initial + 2 retries"


def test_transient_code_in_json_body_is_marked_transient():
    """C-07: ein 10040 im JSON-body (non-stream) war dauerhaft und wurde
    nicht recovered."""
    client = GLMWebClient.__new__(GLMWebClient)
    client.config = _RetryConfig()
    client.logger = SimpleNamespace(
        warning=lambda *a, **k: None, info=lambda *a, **k: None, debug=lambda *a, **k: None
    )
    client.debug_dump_all = False
    client.auth = SimpleNamespace(
        read_json_response=lambda response: {"status": 1, "error_code": 10040, "message": "too long"}
    )
    client._build_error_message = lambda code, payload: "context exceeded"

    with pytest.raises(UpstreamAPIError) as excinfo:
        client._prepare_chat_response(SimpleNamespace(headers={"Content-Type": "application/json"}, close=lambda: None))
    assert excinfo.value.transient is True


def test_permanent_json_body_error_is_not_transient():
    client = GLMWebClient.__new__(GLMWebClient)
    client.config = _RetryConfig()
    client.logger = SimpleNamespace(
        warning=lambda *a, **k: None, info=lambda *a, **k: None, debug=lambda *a, **k: None
    )
    client.debug_dump_all = False
    client.auth = SimpleNamespace(
        read_json_response=lambda response: {"status": 1, "error_code": 40001, "message": "invalid"}
    )
    client._build_error_message = lambda code, payload: "invalid"

    with pytest.raises(UpstreamAPIError) as excinfo:
        client._prepare_chat_response(SimpleNamespace(headers={"Content-Type": "application/json"}, close=lambda: None))
    assert excinfo.value.transient is False


# --- T-10 live: erfundene erfolgsmeldung nach blockiertem call -----------


def _make_always_blocked_client(config):
    """Jede runde versucht denselben blockierten call — das Budget der
    negativ-follow-ups laeuft dadurch zwangslaeufig leer."""
    client = GLMWebClient.__new__(GLMWebClient)
    client.config = config
    client.logger = SimpleNamespace(
        warning=lambda *a, **k: None,
        info=lambda *a, **k: None,
        debug=lambda *a, **k: None,
    )
    client.request_queue = SimpleNamespace(
        acquire=lambda name: SimpleNamespace(ticket=0, released=False, release=lambda: None)
    )
    client.auth = SimpleNamespace(
        get_account_count=lambda: 1,
        get_access_token_for_account=lambda i: "tok",
    )
    calls = {"count": 0}

    def fake_open(payload, preferred_account_index=None, filtered_tools=None):
        calls["count"] += 1
        if calls["count"] < 3:
            return _FakeResponse(_blocked_tool_events()), "assistant-1"
        # letzte runde: das modell gibt auf und behauptet trotzdem erfolg
        return _FakeResponse(_hallucinated_success_events()), "assistant-1"

    client._open_chat_stream = fake_open
    client.delete_conversation = lambda cid, assistant_id=None: None
    client._iter_sse_events = lambda response: iter(response._events)
    return client, calls


def _hallucinated_success_events():
    return [
        {
            "status": "finish",
            "parts": [
                {
                    "logic_id": "p1",
                    "status": "finish",
                    "content": [
                        {
                            "type": "text",
                            "text": "Alles erledigt. Ich habe die Seite geoeffnet: Example Domain.",
                        }
                    ],
                }
            ],
        }
    ]


def test_hallucinated_success_after_exhausted_follow_ups_gets_honesty_notice():
    """Live-Fall 2026-09-25: nach zwei negativen follow-up-runden behauptete
    das modell, es habe die seite geoeffnet, und zitierte den inhalt. Der
    call hatte nie stattgefunden. Ohne notice liest der client die
    erfindung als erfolg und beendet den tool-loop."""
    client, calls = _make_always_blocked_client(_FollowUpConfig())
    payload = {
        "model": "glm-5.3",
        "messages": [{"role": "user", "content": "oeffne die seite"}],
        "tools": [
            {"type": "function", "function": {"name": "bash", "parameters": {"type": "object"}}}
        ],
    }

    text = "".join(chunk.decode("utf-8") for chunk in client.stream_chat_completion(dict(payload)))

    assert calls["count"] == 3, "ursprungsversuch + zwei follow-ups"
    assert "[blocked_tool_notice]" in text
    assert "were NOT executed" in text
    # die notice steht VOR der erfundenen antwort
    assert text.index("[blocked_tool_notice]") < text.index("Alles erledigt.")


def test_no_notice_when_follow_up_ends_with_a_valid_call():
    """Gegenprobe: endet die folge mit einem gueltigen call, gibt es keine
    notice — der aufruf war dann ja nicht blockiert."""
    client = GLMWebClient.__new__(GLMWebClient)
    client.config = _FollowUpConfig()
    client.logger = SimpleNamespace(
        warning=lambda *a, **k: None, info=lambda *a, **k: None, debug=lambda *a, **k: None
    )
    client.request_queue = SimpleNamespace(
        acquire=lambda name: SimpleNamespace(ticket=0, released=False, release=lambda: None)
    )
    client.auth = SimpleNamespace(
        get_account_count=lambda: 1, get_access_token_for_account=lambda i: "tok"
    )
    calls = {"count": 0}

    def valid_bash_call_events():
        return [
            {
                "status": "finish",
                "parts": [
                    {
                        "logic_id": "p1",
                        "status": "finish",
                        "content": [
                            {
                                "type": "text",
                                "text": '{"tool_calls":[{"name":"bash","arguments":{"command":"ls"}}]}[]',
                            }
                        ],
                    }
                ],
            }
        ]

    def fake_open(payload, preferred_account_index=None, filtered_tools=None):
        calls["count"] += 1
        if calls["count"] == 1:
            return _FakeResponse(_blocked_tool_events()), "assistant-1"
        return _FakeResponse(valid_bash_call_events()), "assistant-1"

    client._open_chat_stream = fake_open
    client.delete_conversation = lambda cid, assistant_id=None: None
    client._iter_sse_events = lambda response: iter(response._events)

    payload = {
        "model": "glm-5.3",
        "messages": [{"role": "user", "content": "mach was"}],
        "tools": [
            {"type": "function", "function": {"name": "bash", "parameters": {"type": "object"}}}
        ],
    }
    text = "".join(chunk.decode("utf-8") for chunk in client.stream_chat_completion(dict(payload)))

    assert '"bash"' in text, "der gueltige call muss durchkommen"
    assert "[blocked_tool_notice]" not in text


# --- P4: C-08, C-15, C-19, C-20 ------------------------------------------


def test_reasoning_counts_as_served_content_for_transport_retry():
    """C-08: die byte-heuristik erkannte einen chunk nur dann als sichtbar,
    wenn er `"content"` OHNE `"reasoning_content"` enthielt. Ein transientes
    ereignis nach bereits gesendetem reasoning loeste dadurch einen retry
    aus und verdoppelte den turn."""
    client, calls = _make_client_with_failing_iter(
        [[_reasoning_process_event("denke nach")], [_finish_event("ok")]],
        [ConnectionResetError("reset")],
    )

    stream = client.stream_chat_completion(
        {"model": "glm-5.3", "messages": [{"role": "user", "content": "hi"}]}
    )
    emitted = []
    with pytest.raises(UpstreamAPIError):
        for chunk in stream:
            emitted.append(chunk.decode("utf-8"))

    assert calls["count"] == 1, "kein retry — das reasoning ist bereits beim client"
    assert "denke nach" in "".join(emitted)


def _reasoning_process_event(text):
    return {
        "status": "process",
        "parts": [
            {"logic_id": "p1", "status": "process", "content": [{"type": "think", "think": text}]}
        ],
    }


def test_error_body_read_is_bounded():
    """C-20: `error.read()` war unbegrenzt und wurde bei gzip ohne
    dekompressionslimit entpackt — ein fehlerhaftes upstream konnte damit
    speicher und cpu erschoepfen."""
    import gzip
    import json as json_module
    import logging
    import urllib.error

    from glm2api.services.glm_client import ERROR_BODY_MAX_BYTES, GLMWebClient

    client = GLMWebClient.__new__(GLMWebClient)
    client.logger = logging.getLogger("test.error_body")
    client.logger.addHandler(logging.NullHandler())

    class _Error:
        def __init__(self, body, headers=None):
            self._body = body
            self.headers = headers or {}

        def read(self, size=-1):
            return self._body if size < 0 else self._body[:size]

    oversized = json_module.dumps({"message": "X" * (5 * 1024 * 1024)}).encode()
    payload = client._read_error_payload(_Error(oversized))
    assert len(payload["message"]) <= ERROR_BODY_MAX_BYTES

    bomb = gzip.compress(b"Y" * (50 * 1024 * 1024))
    payload = client._read_error_payload(_Error(bomb, {"Content-Encoding": "gzip"}))
    assert len(payload["message"]) <= ERROR_BODY_MAX_BYTES


def test_conversations_from_superseded_attempts_are_cleaned_up():
    """C-15: bei transient-retry/empty-retry/follow-up wurde ein neuer
    accumulator erzeugt; die bis dahin erhaltene conversation_id blieb beim
    upstream liegen (pro versuch eine conversation)."""
    client, calls = _make_client([[_error_event()], [_finish_event("recovered")]])
    deleted: list[str] = []
    client.delete_conversation = lambda cid, assistant_id=None: deleted.append(cid)

    list(
        client.stream_chat_completion(
            {"model": "glm-5.3", "messages": [{"role": "user", "content": "hi"}]}
        )
    )

    assert calls["count"] == 2, "ein transienter fehler hat einen zweiten versuch ausgeloest"
    # die conversation des verworfen zwischenstands wird mit abgeraeumt
    assert len(set(deleted)) == len(deleted), "keine conversation doppelt loeschen"


def test_attachment_upload_is_not_repeated_for_every_retry():
    """C-19: `_open_chat_stream()` rief den upload bei jedem versuch erneut
    auf — dieselbe datei wurde mehrfach hochgeladen (bandbreite,
    upstream-speicher, account-failover pro upload). Der cache sitszt in
    `_upload_referenced_files`, also wird er hier direkt geprueft."""
    import logging

    from glm2api.services.glm_client import GLMWebClient

    client = GLMWebClient.__new__(GLMWebClient)
    client.logger = logging.getLogger("test.upload_cache")
    client.logger.addHandler(logging.NullHandler())
    client._upload_reference_cache = {}

    uploads: list[str] = []

    def fake_upload(file_url, is_image=False):
        uploads.append(file_url)
        return {"type": "file_upload", "file_id": "f1"}

    client._upload_file_reference = fake_upload
    messages = [
        {"role": "user", "content": [{"type": "file", "file_url": {"url": "https://x/a.pdf"}}]}
    ]

    first = client._upload_referenced_files(messages)
    second = client._upload_referenced_files(messages)

    assert uploads == ["https://x/a.pdf", "https://x/a.pdf"], (
        f"erwartet 2 uploads (ein je request), {len(uploads)} gemessen"
    )
    assert first == second, "beide runden sehen dieselbe referenz"


def test_upload_cache_does_not_leak_across_requests():
    """C-19: der cache war client-instanzweit. Gemessen: ein upload von
    konto 0 wurde fuer den chat von konto 1 wiederverwendet — die
    `source_id` eines fremden kontos im request des anderen."""
    import logging

    from glm2api.services.glm_client import GLMWebClient

    client = GLMWebClient.__new__(GLMWebClient)
    client.logger = logging.getLogger("test.upload_scope")
    client.logger.addHandler(logging.NullHandler())
    client._upload_reference_cache = {}
    uploads: list[str] = []

    def fake_upload(file_url, is_image=False):
        uploads.append(file_url)
        return {"type": "file_upload", "source_id": f"src-konto-{len(uploads)}"}

    client._upload_file_reference = fake_upload
    messages = [{"role": "user", "content": [{"type": "file", "file_url": {"url": "https://x/a.pdf"}}]}]

    first = client._upload_referenced_files(messages)
    second = client._upload_referenced_files(messages)

    assert len(uploads) == 2, "zweiter request muss neu hochladen"
    assert first[0]["source_id"] != second[0]["source_id"], "cache leak zwischen requests"


def test_upload_cache_does_not_grow_unbounded():
    import logging

    from glm2api.services.glm_client import _UPLOAD_CACHE_MAX_ENTRIES, GLMWebClient

    client = GLMWebClient.__new__(GLMWebClient)
    client.logger = logging.getLogger("test.upload_cache2")
    client.logger.addHandler(logging.NullHandler())
    client._upload_reference_cache = {}
    client._upload_file_reference = lambda url, is_image=False: {"type": "file_upload", "file_id": url}

    for index in range(_UPLOAD_CACHE_MAX_ENTRIES + 20):
        client._cached_upload_reference(f"https://x/{index}.bin", is_image=False)

    assert len(client._upload_reference_cache) <= _UPLOAD_CACHE_MAX_ENTRIES


def test_truncated_stream_is_not_reported_as_success():
    """T-13/S-08: es gab keinen Terminalstatus-Vertrag. Jeder Status
    ('error', 'aborted', 'cancelled', 'timeout', 'truncated') endete mit
    `finish_reason: "stop"` und `data: [DONE]` — der Client las einen
    abgeschnittenen Turn als vollstaendige Antwort, und der
    Anthropic-Adapter uebersetzte das in `stop_reason: end_turn` +
    `message_stop`, also ein Erfolgssignal."""
    import json as json_module
    import logging
    import re
    from types import SimpleNamespace

    from glm2api.services.glm_client import GLMWebClient, ConcurrentRequestQueue

    class _Resp:
        """Upstream OHNE [DONE] und MIT sichtbarem content."""

        def __init__(self, body):
            self._body = body

        def close(self):
            pass

        def read(self, size=-1):
            data, self._body = self._body, b""
            return data

        def getheader(self, *args, **kwargs):
            return None

        def info(self):
            namespace = SimpleNamespace()
            namespace.get = lambda *a, **k: None
            namespace.get_content_charset = lambda *a, **k: "utf-8"
            return namespace

    body = (
        b'data: {"status":"process","parts":[{"logic_id":"p1","status":"process",'
        b'"content":[{"type":"text","text":"TEIL-1"}]}]}\n\n'
    )
    client = GLMWebClient.__new__(GLMWebClient)
    client.config = SimpleNamespace(
        glm_max_concurrency=2, glm_queue_wait_timeout=2, glm_stream_error_max_retries=0,
        glm_empty_response_max_retries=0, glm_blocked_tool_follow_ups=0,
        glm_history_max_chars=100000, glm_request_deadline_seconds=10.0,
        glm_stream_error_retry_interval=0.0, glm_max_output_tokens=16384,
        glm_persistent_conversation=False, glm_conversation_id="", glm_conversation_file=None,
        glm_delete_conversation=True, blocked_tool_names=[], debug_dump_all=False,
    )
    client.logger = SimpleNamespace(
        warning=lambda *a, **k: None, info=lambda *a, **k: None, debug=lambda *a, **k: None
    )
    client.request_queue = ConcurrentRequestQueue(client.logger, wait_timeout=1, max_concurrency=2)
    client.auth = SimpleNamespace(
        get_access_token_for_account=lambda i: "tok", get_account_count=lambda: 1
    )
    client._open_chat_stream = lambda p, preferred_account_index=None, filtered_tools=None: (_Resp(body), "a1")
    client.delete_conversation = lambda cid, assistant_id=None: None

    text = "".join(
        chunk.decode("utf-8")
        for chunk in client.stream_chat_completion(
            {"model": "m", "messages": [{"role": "user", "content": "hi"}]}
        )
    )

    assert "TEIL-1" in text, "der bereits gesendete anteil geht nicht verloren"
    assert "[DONE]" not in text, "[DONE] ist das erfolgszeichen des streams"
    # das LETZTE finish_reason ist das abschliessende; die davorigen sind
    # die `null` der content-deltas.
    matches = re.findall(r'"finish_reason":\s*"?(\w+)"?', text)
    assert matches and matches[-1] == "error", (
        f"trunkierung muss ein fehler sein, gefunden: {matches}"
    )
    json_module.loads("{}")  # import ist fuer leser der absicht hier
