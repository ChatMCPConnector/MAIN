import json
from types import SimpleNamespace

from glm2api.services.glm_client import GLMWebClient, UpstreamAPIError


class _RetryConfig:
    glm_stream_error_max_retries = 2
    glm_stream_error_retry_interval = 0.0
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
    assert "open_url" not in text


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
