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


def _thinking_process_event(text="denke"):
    return {
        "status": "process",
        "parts": [
            {
                "logic_id": "p1",
                "status": "process",
                "content": [{"type": "think", "think": text}],
            }
        ],
    }


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
        [[_thinking_process_event()], [_finish_event("recovered")]],
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
        [[_thinking_process_event()], [_finish_event("ok")]],
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
