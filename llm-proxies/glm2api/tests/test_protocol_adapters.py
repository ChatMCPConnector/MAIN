import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

from glm2api import server as server_module
from glm2api.services import glm_auth
from glm2api.services.anthropic_adapter import (
    AnthropicStreamAccumulator,
    anthropic_to_openai,
    openai_to_anthropic_response,
)
from glm2api.services.glm_auth import AccessToken, GLMAccessTokenManager, GLMAuthError, redact_token
from glm2api.services.glm_client import GLMWebClient, UpstreamAPIError

from glm2api.services.responses_adapter import ResponsesStreamAccumulator, openai_to_responses, responses_to_openai


class _DummyConfig:
    glm_user_agent = "Mozilla/5.0"


class DummyConfig:
    def __init__(self, tmp_path, refresh_tokens: list[str]) -> None:
        self.glm_user_agent = "Mozilla/5.0"
        self.glm_refresh_tokens = list(refresh_tokens)
        self.glm_refresh_token = refresh_tokens[0]
        self.debug_dump_all = True
        self.request_timeout = 1
        self.refresh_url = "https://example.invalid/refresh"
        self.guest_refresh_url = "https://example.invalid/guest"
        self.token_file_path = tmp_path / "tokens.txt"
        self.env_file_path = tmp_path / ".env"


class DummyLogger:
    def __init__(self) -> None:
        self.records: list[str] = []

    def _record(self, level: str, message: str, *args) -> None:
        self.records.append(f"{level}: {message % args if args else message}")

    def debug(self, message, *args) -> None:
        self._record("DEBUG", message, *args)

    def info(self, message, *args) -> None:
        self._record("INFO", message, *args)

    def warning(self, message, *args) -> None:
        self._record("WARNING", message, *args)

    def error(self, message, *args) -> None:
        self._record("ERROR", message, *args)


class FakeResponse:
    def __init__(self, body: bytes, content_type: str = "application/json", status: int = 200) -> None:
        self.body = body
        self.headers = {"Content-Type": content_type}
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None

    def getcode(self) -> int:
        return self.status

    def read(self, size: int = -1) -> bytes:
        return self.body if size < 0 else self.body[:size]


def test_get_browser_headers_includes_random_x_forwarded_for():
    manager = GLMAccessTokenManager.__new__(GLMAccessTokenManager)
    manager.config = _DummyConfig()

    headers = manager.get_browser_headers()
    assert headers["X-Lang"] == "en"
    assert headers["Accept-Language"].startswith("en")
    xff = headers["X-Forwarded-For"]
    octets = xff.split(".")

    assert len(octets) == 4
    assert all(part.isdigit() for part in octets)
    assert 1 <= int(octets[0]) <= 223
    assert int(octets[0]) not in {10, 127, 169, 172, 192}


def test_auth_debug_dumps_and_account_logs_redact_token_values(tmp_path, monkeypatch):
    refresh_token = "registered-refresh-token-123456789"
    access_token = "issued-access-token-987654321"
    payload = json.dumps(
        {
            "code": 0,
            "result": {
                "access_token": access_token,
                "refresh_token": "rotated-refresh-token-456789123",
            },
        }
    ).encode()
    monkeypatch.setattr(
        glm_auth.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse(payload),
    )
    logger = DummyLogger()
    manager = GLMAccessTokenManager(DummyConfig(tmp_path, [refresh_token]), logger)

    assert manager.get_access_token_for_account(0) == access_token
    manager.advance_account(0, f"Authorization: Bearer {access_token}")
    log_output = "\n".join(logger.records)

    assert refresh_token not in log_output
    assert access_token not in log_output
    assert "rotated-refresh-token-456789123" not in log_output
    assert "…" in log_output
    assert redact_token(refresh_token) != refresh_token


def test_guest_token_response_is_redacted_in_debug_dumps(tmp_path, monkeypatch):
    access_token = "guest-access-token-987654321"
    refresh_token = "guest-refresh-token-123456789"
    payload = json.dumps(
        {"code": 0, "result": {"access_token": access_token, "refresh_token": refresh_token}}
    ).encode()
    monkeypatch.setattr(
        glm_auth.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse(payload),
    )
    logger = DummyLogger()
    config = DummyConfig(tmp_path, [glm_auth.GUEST_REFRESH_TOKEN_MARKER])
    manager = GLMAccessTokenManager(config, logger)

    assert manager.get_access_token_for_account(0) == access_token
    log_output = "\n".join(logger.records)

    assert access_token not in log_output
    assert refresh_token not in log_output
    assert "…" in log_output


def test_auth_exception_only_contains_safe_status_and_code(tmp_path):
    access_token = "sensitive-access-token-123456789"
    manager = GLMAccessTokenManager(DummyConfig(tmp_path, ["old-refresh-token"]), DummyLogger())

    with pytest.raises(GLMAuthError) as exc_info:
        manager._validate_auth_response(
            200,
            {
                "code": "access_denied",
                "trace_id": "private-trace-123",
                "result": {"access_token": access_token, "refresh_token": "new-refresh-token"},
            },
            "old-refresh-token",
        )

    message = str(exc_info.value)
    assert "status=200" in message
    assert "code=access_denied" in message
    assert access_token not in message
    assert "private-trace-123" not in message


def test_same_account_refresh_is_single_flight(tmp_path, monkeypatch):
    manager = GLMAccessTokenManager(DummyConfig(tmp_path, ["old-refresh-token"]), DummyLogger())
    access_token = "single-flight-access-token"
    call_count = 0
    count_lock = threading.Lock()
    ready = threading.Barrier(3)

    def fake_refresh(account_index: int) -> AccessToken:
        nonlocal call_count
        with count_lock:
            call_count += 1
        time.sleep(0.05)
        return AccessToken(access_token, "new-refresh-token", time.time() + 3600)

    monkeypatch.setattr(manager, "_refresh_access_token", fake_refresh)
    results: list[str] = []
    errors: list[Exception] = []

    def worker() -> None:
        ready.wait()
        try:
            results.append(manager.get_access_token_for_account(0))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    ready.wait()
    for thread in threads:
        thread.join(timeout=2)

    assert not any(thread.is_alive() for thread in threads)
    assert errors == []
    assert results == [access_token, access_token]
    assert call_count == 1


def test_refresh_token_persistence_uses_atomic_same_directory_replace(tmp_path, monkeypatch):
    config = DummyConfig(tmp_path, ["old-refresh-token"])
    config.token_file_path.write_text("old-refresh-token\n", encoding="utf-8")
    manager = GLMAccessTokenManager(config, DummyLogger())
    real_replace = glm_auth.os.replace
    replace_calls: list[tuple[Path, Path]] = []

    def checked_replace(source, destination) -> None:
        source_path = Path(source)
        destination_path = Path(destination)
        replace_calls.append((source_path, destination_path))
        assert source_path.parent == destination_path.parent == tmp_path
        assert config.token_file_path.read_text(encoding="utf-8") == "old-refresh-token\n"
        real_replace(source, destination)

    monkeypatch.setattr(glm_auth.os, "replace", checked_replace)
    manager._persist_refresh_token(0, "new-refresh-token")

    assert len(replace_calls) == 1
    assert config.token_file_path.read_text(encoding="utf-8") == "new-refresh-token\n"
    assert config.glm_refresh_tokens == ["new-refresh-token"]
    assert list(tmp_path.glob(".tokens.txt.*")) == []


@pytest.mark.parametrize(
    ("body", "content_type"),
    [
        (b"<html>denied</html>", "text/html"),
        (b"[]", "application/json"),
        (b"x" * (glm_auth.MAX_JSON_RESPONSE_BYTES + 1), "application/json"),
    ],
)
def test_auth_json_response_rejects_invalid_content_type_shape_or_size(tmp_path, body, content_type):
    manager = GLMAccessTokenManager(DummyConfig(tmp_path, ["old-refresh-token"]), DummyLogger())

    with pytest.raises(RuntimeError):
        manager.read_json_response(FakeResponse(body, content_type=content_type))


@pytest.mark.parametrize(
    "payload",
    [
        {"code": 0, "result": []},
        {"code": 0, "result": {"access_token": None, "refresh_token": "refresh"}},
        {"code": 0, "result": {"access_token": 123, "refresh_token": "refresh"}},
        {"code": 0, "result": {"access_token": "access", "refresh_token": []}},
    ],
)
def test_auth_response_rejects_invalid_result_schema(tmp_path, payload):
    manager = GLMAccessTokenManager(DummyConfig(tmp_path, ["old-refresh-token"]), DummyLogger())

    with pytest.raises(GLMAuthError):
        manager._validate_auth_response(200, payload, "old-refresh-token")


def test_registered_refresh_response_keeps_old_token_when_rotation_is_null(tmp_path):
    manager = GLMAccessTokenManager(DummyConfig(tmp_path, ["old-refresh-token"]), DummyLogger())

    access_token, refresh_token = manager._validate_auth_response(
        200,
        {"code": 0, "result": {"access_token": "new-access-token", "refresh_token": None}},
        "old-refresh-token",
    )

    assert access_token == "new-access-token"
    assert refresh_token == "old-refresh-token"


def test_account_failover_excludes_deterministic_request_errors():
    manager = GLMAccessTokenManager.__new__(GLMAccessTokenManager)

    assert not manager.should_switch_account(UpstreamAPIError(400, "invalid model request"))
    assert not manager.should_switch_account(UpstreamAPIError(404, "conversation not found"))
    assert not manager.should_switch_account(UpstreamAPIError(422, "invalid request content"))
    assert not manager.should_switch_account(RuntimeError("token count in model prompt is invalid"))
    assert manager.should_switch_account(UpstreamAPIError(401, "unauthorized"))
    assert manager.should_switch_account(UpstreamAPIError(403, "forbidden"))
    assert manager.should_switch_account(UpstreamAPIError(429, "busy"))
    assert manager.should_switch_account(UpstreamAPIError(502, "upstream unavailable"))
    assert manager.should_switch_account(
        UpstreamAPIError(400, "invalid token", {"code": "invalid_token"})
    )
    assert manager.should_switch_account(
        UpstreamAPIError(400, "expired access token", {"message": "expired access token"})
    )
    assert not manager.should_switch_account(
        UpstreamAPIError(400, "invalid token count", {"message": "invalid token count"})
    )
    assert not manager.should_switch_account(
        UpstreamAPIError(502, "context exceeded", {"code": 10040})
    )
    assert manager.should_switch_account(urllib.error.URLError("connection reset"))
    assert manager.should_switch_account(TimeoutError())


def test_responses_to_openai_preserves_tool_choice():
    payload = {
        "model": "glm-4",
        "input": "hi",
        "tools": [
            {
                "type": "function",
                "name": "get_weather",
                "description": "查询天气",
                "parameters": {"type": "object"},
            }
        ],
        "tool_choice": {"type": "function", "function": {"name": "get_weather"}},
    }

    converted = responses_to_openai(payload)

    assert converted["tool_choice"] == {"type": "function", "function": {"name": "get_weather"}}


def test_responses_to_openai_accepts_sdk_style_input_messages():
    payload = {
        "model": "glm-4",
        "input": [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": [{"type": "output_text", "text": "hello"}],
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "look"},
                    {"type": "input_image", "image_url": "data:image/png;base64,abc"},
                ],
            },
        ],
    }

    converted = responses_to_openai(payload)

    assert converted["messages"][0] == {"role": "user", "content": "hi"}
    assert converted["messages"][1] == {"role": "assistant", "content": "hello"}
    assert converted["messages"][2] == {
        "role": "user",
        "content": [
            {"type": "text", "text": "look"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
        ],
    }


def test_openai_to_responses_exposes_output_text_and_standard_fields():
    response = openai_to_responses(
        {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "hello"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 2, "completion_tokens": 3},
        },
        model="glm-4",
    )

    assert response["object"] == "response"
    assert response["output_text"] == "hello"
    assert response["error"] is None
    assert response["incomplete_details"] is None
    assert response["usage"] == {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5}


def test_responses_stream_uses_openai_event_envelope():
    accumulator = ResponsesStreamAccumulator(model="glm-4")

    events = accumulator.start_response()
    events.extend(
        accumulator.feed_chunk(
            b'data: {"choices":[{"delta":{"role":"assistant","content":"hi"},"finish_reason":null}]}\n\n'
            b"data: [DONE]\n\n"
        )
    )

    payloads = [
        json.loads(event.split("data: ", 1)[1])
        for event in events
        if event.startswith("event: ")
    ]

    assert payloads[0]["type"] == "response.created"
    assert payloads[0]["sequence_number"] == 0
    assert payloads[0]["response"]["object"] == "response"
    assert payloads[0]["response"]["usage"] is None
    assert payloads[0]["response"]["parallel_tool_calls"] is True
    text_delta = next(payload for payload in payloads if payload["type"] == "response.output_text.delta")
    assert text_delta["delta"] == "hi"
    assert text_delta["response_id"] == payloads[0]["response"]["id"]
    assert payloads[-1]["type"] == "response.completed"
    assert payloads[-1]["response"]["status"] == "completed"
    assert payloads[-1]["response"]["completed_at"] is not None
    assert payloads[-1]["response"]["usage"]["total_tokens"] == 0
    assert events[-1] == "data: [DONE]\n\n"


def test_responses_stream_buffers_split_sse_blocks_until_done():
    accumulator = ResponsesStreamAccumulator(model="glm-4")

    events = accumulator.feed_chunk(
        b'data: {"choices":[{"delta":{"role":"assistant","content":"hi"},"finish_reason":null}]}\n'
    )
    events.extend(accumulator.feed_chunk(b"\ndata: [DO"))
    events.extend(accumulator.feed_chunk(b"NE]\n\n"))

    payload_events = [event for event in events if event.startswith("event: ")]
    payloads = [json.loads(event.split("data: ", 1)[1]) for event in payload_events]

    assert any(payload["type"] == "response.output_text.delta" and payload["delta"] == "hi" for payload in payloads)
    assert payloads[-1]["type"] == "response.completed"
    assert events[-1] == "data: [DONE]\n\n"


def test_responses_stream_completes_on_finish_reason_without_done_sentinel():
    accumulator = ResponsesStreamAccumulator(model="glm-4")

    events = accumulator.feed_chunk(
        b'data: {"choices":[{"delta":{"role":"assistant","content":"hi"},"finish_reason":null}]}\n\n'
        b'data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":2,"completion_tokens":3,"total_tokens":5}}\n\n'
    )

    payload_events = [event for event in events if event.startswith("event: ")]
    payloads = [json.loads(event.split("data: ", 1)[1]) for event in payload_events]

    assert payloads[-1]["type"] == "response.completed"
    assert payloads[-1]["response"]["usage"]["input_tokens"] == 2
    assert payloads[-1]["response"]["usage"]["output_tokens"] == 3
    assert events[-1] == "data: [DONE]\n\n"


def test_responses_http_stream_sends_keepalive_while_upstream_is_idle(monkeypatch):
    monkeypatch.setattr(server_module, "STREAM_HEARTBEAT_SECONDS", 0.01)

    class FakeGLM:
        def stream_chat_completion(self, payload):
            yield b'data: {"choices":[{"delta":{"role":"assistant","content":"hi"},"finish_reason":null}]}\n\n'
            time.sleep(0.05)
            yield b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'

    class FakeLogger:
        def debug(self, *args, **kwargs): pass
        def info(self, *args, **kwargs): pass
        def warning(self, *args, **kwargs): pass
        def error(self, *args, **kwargs): pass

    config = SimpleNamespace(
        host="127.0.0.1",
        port=0,
        api_prefix="/v1",
        cors_allow_origin="*",
        server_api_keys=[],
        debug_dump_all=False,
        exposed_models=["glm-4"],
    )
    server = server_module.GLM2APIServer(config, FakeGLM(), FakeLogger())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server._server.server_address[1]
    try:
        body = json.dumps({"model": "glm-4", "input": "hi", "stream": True}).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/responses",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            stream_text = response.read().decode("utf-8")
    finally:
        server.shutdown()
        thread.join(timeout=1)

    assert ": keep-alive\n\n" in stream_text
    assert "response.completed" in stream_text


def test_anthropic_http_stream_sends_ping_while_upstream_is_idle(monkeypatch):
    monkeypatch.setattr(server_module, "STREAM_HEARTBEAT_SECONDS", 0.01)

    class FakeGLM:
        def stream_chat_completion(self, payload):
            yield b'data: {"choices":[{"delta":{"role":"assistant","content":"hi"},"finish_reason":null}]}\n\n'
            time.sleep(0.05)
            yield b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'

    class FakeLogger:
        def debug(self, *args, **kwargs): pass
        def info(self, *args, **kwargs): pass
        def warning(self, *args, **kwargs): pass
        def error(self, *args, **kwargs): pass

    config = SimpleNamespace(
        host="127.0.0.1",
        port=0,
        api_prefix="/v1",
        cors_allow_origin="*",
        server_api_keys=[],
        debug_dump_all=False,
        exposed_models=["glm-4"],
    )
    server = server_module.GLM2APIServer(config, FakeGLM(), FakeLogger())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server._server.server_address[1]
    try:
        body = json.dumps(
            {"model": "glm-4", "messages": [{"role": "user", "content": "hi"}], "stream": True}
        ).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/messages",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            stream_text = response.read().decode("utf-8")
    finally:
        server.shutdown()
        thread.join(timeout=1)

    assert "event: ping" in stream_text
    assert "message_stop" in stream_text


def test_anthropic_to_openai_maps_tool_choice_variants():
    any_payload = {
        "model": "glm-4",
        "messages": [{"role": "user", "content": "hi"}],
        "tool_choice": {"type": "any"},
    }
    tool_payload = {
        "model": "glm-4",
        "messages": [{"role": "user", "content": "hi"}],
        "tool_choice": {"type": "tool", "name": "get_weather"},
    }

    any_converted = anthropic_to_openai(any_payload)
    tool_converted = anthropic_to_openai(tool_payload)

    assert any_converted["tool_choice"] == "required"
    assert tool_converted["tool_choice"] == {"type": "function", "function": {"name": "get_weather"}}


def test_glm_client_raises_for_sse_error_event():
    client = GLMWebClient.__new__(GLMWebClient)

    try:
        client._raise_for_event_error(
            {
                "status": "error",
                "last_error": {"error_code": 10025, "err_msg": "stream request error"},
                "parts": [],
            },
            stream=True,
        )
    except UpstreamAPIError as exc:
        assert exc.status_code == 502
        assert "10025" in str(exc)
        assert "stream request error" in str(exc)
    else:
        raise AssertionError("expected UpstreamAPIError")


def test_anthropic_stream_error_event_shape():
    accumulator = AnthropicStreamAccumulator(model="glm-4")
    accumulator.start_message()
    accumulator.feed_chunk(
        b'data: {"choices":[{"delta":{"role":"assistant","content":"hi"},"finish_reason":null}]}\n\n'
    )

    event = accumulator.error_event("upstream kaputt", "UpstreamAPIError")
    payload = json.loads(event.split("data: ", 1)[1])

    assert event.startswith("event: error")
    assert payload["type"] == "error"
    assert payload["error"]["type"] == "UpstreamAPIError"
    assert "upstream kaputt" in payload["error"]["message"]
    # nach einem error darf kein message_stop mehr kommen
    assert accumulator.finish() == []


def test_anthropic_stream_ping_event_shape():
    event = AnthropicStreamAccumulator.ping_event()
    payload = json.loads(event.split("data: ", 1)[1])

    assert event.startswith("event: ping")
    assert payload["type"] == "ping"


def test_anthropic_stream_finish_is_idempotent():
    accumulator = AnthropicStreamAccumulator(model="glm-4")
    accumulator.start_message()
    accumulator.feed_chunk(
        b'data: {"choices":[{"delta":{"role":"assistant","content":"hi"},"finish_reason":null}]}\n\n'
    )

    first = accumulator.finish()
    second = accumulator.finish()

    assert any("message_stop" in event for event in first)
    assert second == []


def test_responses_stream_error_event_shape():
    accumulator = ResponsesStreamAccumulator(model="glm-4")
    accumulator.start_response()
    accumulator.feed_chunk(
        b'data: {"choices":[{"delta":{"role":"assistant","content":"hi"},"finish_reason":null}]}\n\n'
    )

    event = accumulator.error_event("upstream kaputt", "UpstreamAPIError")
    payload = json.loads(event.split("data: ", 1)[1])

    assert event.startswith("event: response.failed")
    assert payload["type"] == "response.failed"
    assert payload["response"]["status"] == "failed"
    assert payload["response"]["error"]["message"] == "upstream kaputt"
    assert payload["response"]["error"]["code"] == "UpstreamAPIError"
    # nach response.failed darf kein response.completed mehr kommen
    assert accumulator.finish() == []


def test_thinking_budget_tokens_normalizes_reasoning_effort():
    # budget_tokens ist ein int — darf nicht ungeprueft als reasoning_effort
    # durchgereicht werden (faellt sonst durchs mapping).
    result = anthropic_to_openai(
        {
            "model": "glm-4",
            "max_tokens": 1000,
            "messages": [{"role": "user", "content": "hi"}],
            "thinking": {"type": "enabled", "budget_tokens": 8000},
        }
    )

    assert result["reasoning_effort"] == "medium"


def test_anthropic_mixed_tool_result_preserves_content_blocks():
    converted = anthropic_to_openai(
        {
            "model": "glm-4",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "KEEP"},
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": "image/png", "data": "img"},
                        },
                        {
                            "type": "tool_result",
                            "tool_use_id": "call_1",
                            "content": [
                                {"type": "text", "text": "RESULT"},
                                {
                                    "type": "image",
                                    "source": {"type": "url", "url": "https://example.test/result"},
                                },
                            ],
                        },
                    ],
                }
            ],
        }
    )

    assert converted["messages"][0]["content"] == [
        {"type": "text", "text": "KEEP"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,img"}},
    ]
    assert converted["messages"][1]["role"] == "tool"
    assert converted["messages"][1]["content"] == [
        {"type": "text", "text": "RESULT"},
        {"type": "image_url", "image_url": {"url": "https://example.test/result"}},
    ]


def test_anthropic_thinking_blocks_keep_signature_and_redacted_data():
    converted = anthropic_to_openai(
        {
            "model": "glm-4",
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "reason", "signature": "sig-1"},
                        {"type": "redacted_thinking", "data": "opaque"},
                    ],
                }
            ],
        }
    )
    response = openai_to_anthropic_response(
        {
            "choices": [
                {
                    "message": {
                        "reasoning_content": "reason",
                        "reasoning_signature": "sig-2",
                        "content": "answer",
                    },
                    "finish_reason": "stop",
                }
            ]
        },
        "glm-4",
    )

    assert converted["messages"][0]["content"] == [
        {"type": "thinking", "thinking": "reason", "signature": "sig-1"},
        {"type": "redacted_thinking", "data": "opaque"},
    ]
    assert response["content"][0] == {
        "type": "thinking",
        "thinking": "reason",
        "signature": "sig-2",
    }


def test_anthropic_stream_keeps_interleaved_tool_arguments_separate():
    accumulator = AnthropicStreamAccumulator(model="glm-4")
    chunks = [
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call-a", "function": {"name": "a", "arguments": "{\"x\":"}}]}, "finish_reason": None}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 1, "id": "call-b", "function": {"name": "b", "arguments": "{\"y\":"}}]}, "finish_reason": None}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "1}"}}, {"index": 1, "function": {"arguments": "2}"}}]}, "finish_reason": "tool_calls"}]},
    ]
    events = []
    for chunk in chunks:
        events.extend(accumulator.feed_chunk((("data: " + json.dumps(chunk) + "\n\n")).encode()))

    payloads = [json.loads(event.split("data: ", 1)[1]) for event in events if event.startswith("event: ")]
    deltas = [payload for payload in payloads if payload["type"] == "content_block_delta"]
    starts = [payload for payload in payloads if payload["type"] == "content_block_start"]

    assert [payload["index"] for payload in starts] == [0, 1]
    assert [payload["index"] for payload in deltas] == [0, 1]
    assert [json.loads(payload["delta"]["partial_json"]) for payload in deltas] == [{"x": 1}, {"y": 2}]


def test_anthropic_response_rejects_invalid_tool_calls_instead_of_inventing_input():
    with pytest.raises(ValueError):
        openai_to_anthropic_response(
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call-bad",
                                    "type": "function",
                                    "function": {"name": "bash", "arguments": "{BROKEN"},
                                }
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
            "glm-4",
        )

    empty = openai_to_anthropic_response(
        {"choices": [{"message": {"tool_calls": []}, "finish_reason": "stop"}]},
        "glm-4",
    )
    assert empty["stop_reason"] == "end_turn"
    assert empty["content"] == [{"type": "text", "text": ""}]


def test_anthropic_tool_choice_none_and_parallel_control_are_forwarded():
    converted = anthropic_to_openai(
        {
            "model": "glm-4",
            "messages": [{"role": "user", "content": "hi"}],
            "tool_choice": {"type": "none", "disable_parallel_tool_use": True},
        }
    )

    assert converted["tool_choice"] == "none"
    assert converted["parallel_tool_calls"] is False


def test_responses_previous_response_tool_result_is_preserved_as_user_text():
    converted = responses_to_openai(
        {
            "model": "glm-4",
            "previous_response_id": "resp-previous",
            "input": [
                {
                    "type": "function_call_output",
                    "call_id": "call-old",
                    "output": {"ok": True},
                }
            ],
        }
    )

    assert converted["previous_response_id"] == "resp-previous"
    assert converted["messages"][0]["role"] == "user"
    assert "resp-previous" in converted["messages"][0]["content"]
    assert "{\"ok\":true}" in converted["messages"][0]["content"]


def test_responses_structured_tool_output_uses_json_not_python_repr():
    converted = responses_to_openai(
        {
            "model": "glm-4",
            "input": [
                {"type": "function_call", "call_id": "call-1", "name": "lookup", "arguments": "{}"},
                {"type": "function_call_output", "call_id": "call-1", "output": {"a": 1, "b": [2]}},
            ],
        }
    )

    assert converted["messages"][1]["role"] == "tool"
    assert converted["messages"][1]["content"] == '{"a":1,"b":[2]}'


def test_responses_official_tool_choice_and_parallel_calls_are_normalized():
    converted = responses_to_openai(
        {
            "model": "glm-4",
            "input": "hi",
            "tool_choice": {"type": "function", "name": "lookup"},
            "parallel_tool_calls": False,
        }
    )

    assert converted["tool_choice"] == {"type": "function", "function": {"name": "lookup"}}
    assert converted["parallel_tool_calls"] is False


def test_responses_unsupported_tool_type_is_rejected_explicitly():
    with pytest.raises(ValueError, match="Unsupported Responses tool type"):
        responses_to_openai(
            {
                "model": "glm-4",
                "input": "hi",
                "tools": [{"type": "web_search_preview"}],
            }
        )


def test_responses_stream_length_and_partial_tool_calls_are_incomplete():
    for finish_reason, delta in [
        ("length", {"content": "partial"}),
        ("tool_calls", {"tool_calls": [{"index": 0, "id": "call-1", "function": {"name": "lookup", "arguments": "{"}}]}),
    ]:
        accumulator = ResponsesStreamAccumulator(model="glm-4")
        events = accumulator.feed_chunk(
            ("data: " + json.dumps({"choices": [{"delta": delta, "finish_reason": finish_reason}]}) + "\n\n").encode()
        )
        payloads = [json.loads(event.split("data: ", 1)[1]) for event in events if event.startswith("event: ")]
        terminal = payloads[-1]

        assert terminal["type"] == "response.incomplete"
        assert terminal["response"]["status"] == "incomplete"
        assert terminal["response"]["incomplete_details"]["reason"] in {"max_output_tokens", "incomplete_tool_call"}
        assert not any(payload["type"] == "response.completed" for payload in payloads)


def test_responses_stream_output_text_is_not_duplicated_and_items_keep_index_order():
    accumulator = ResponsesStreamAccumulator(model="glm-4")
    chunks = [
        {"choices": [{"delta": {"content": "first"}, "finish_reason": None}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call-1", "function": {"name": "lookup", "arguments": "{\"a\":1}"}}]}, "finish_reason": None}]},
        {"choices": [{"delta": {"content": "second"}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
    ]
    events = []
    for chunk in chunks:
        events.extend(accumulator.feed_chunk((("data: " + json.dumps(chunk) + "\n\n")).encode()))

    payloads = [json.loads(event.split("data: ", 1)[1]) for event in events if event.startswith("event: ")]
    response = next(payload["response"] for payload in payloads if payload["type"] == "response.completed")
    output = response["output"]

    assert [item["type"] for item in output] == ["message", "function_call", "message"]
    assert [part["text"] for part in output[0]["content"]] == ["first"]
    assert [part["text"] for part in output[2]["content"]] == ["second"]


def test_blocked_tool_fallback_is_an_error_but_related_prose_stays_normal():
    blocked_text = (
        "The model attempted to call an undeclared tool: `open_url`. Blocked. "
        "Only these tools are allowed in this round: bash."
    )
    legitimate_text = blocked_text + " I can inspect the workspace with the available bash tool instead."

    class FakeGLM:
        def chat_completion(self, payload):
            prompt = payload["messages"][-1]["content"]
            content = legitimate_text if prompt == "legitimate prose" else blocked_text
            return {
                "choices": [
                    {
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ]
            }, None

    config = SimpleNamespace(
        host="127.0.0.1",
        port=0,
        api_prefix="/v1",
        cors_allow_origin="*",
        server_api_keys=[],
        debug_dump_all=False,
        exposed_models=["glm-4"],
    )
    server = server_module.GLM2APIServer(config, FakeGLM(), DummyLogger())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server._server.server_address[1]

    def post(prompt: str):
        body = json.dumps(
            {
                "model": "glm-4",
                "messages": [{"role": "user", "content": prompt}],
                "tools": [
                    {
                        "type": "function",
                        "function": {"name": "bash", "parameters": {"type": "object"}},
                    }
                ],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/chat/completions",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        return urllib.request.urlopen(request, timeout=5)

    try:
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            post("blocked call")
        error_response = exc_info.value
        error_payload = json.loads(error_response.read())

        assert error_response.code == 502
        assert error_payload["error"]["code"] == "tool_protocol_error"
        assert error_payload["error"]["type"] == "tool_protocol_error"
        assert error_payload["error"]["blocked_tool_names"] == ["open_url"]
        assert "choices" not in error_payload

        with post("legitimate prose") as response:
            response_payload = json.loads(response.read())
        assert response.status == 200
        assert response_payload["choices"][0]["message"]["content"] == legitimate_text
    finally:
        server.shutdown()
        thread.join(timeout=1)


def test_responses_http_tool_round_replays_call_result_and_selection():
    class FakeGLM:
        def __init__(self):
            self.payloads = []

        def chat_completion(self, payload):
            self.payloads.append(json.loads(json.dumps(payload)))
            if len(self.payloads) == 1:
                message = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "lookup", "arguments": '{"city":"Berlin"}'},
                        }
                    ],
                }
                finish_reason = "tool_calls"
            else:
                message = {"role": "assistant", "content": "done"}
                finish_reason = "stop"
            return {
                "choices": [{"message": message, "finish_reason": finish_reason}]
            }, None

    fake_glm = FakeGLM()
    config = SimpleNamespace(
        host="127.0.0.1",
        port=0,
        api_prefix="/v1",
        cors_allow_origin="*",
        server_api_keys=[],
        debug_dump_all=False,
        exposed_models=["glm-4"],
    )
    server = server_module.GLM2APIServer(config, fake_glm, DummyLogger())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server._server.server_address[1]

    def post(payload: dict[str, object]):
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read())

    try:
        first_response = post(
            {
                "model": "glm-4",
                "input": "look up Berlin",
                "tools": [
                    {
                        "type": "function",
                        "name": "lookup",
                        "parameters": {"type": "object"},
                    }
                ],
                "tool_choice": {"type": "function", "name": "lookup"},
                "parallel_tool_calls": False,
            }
        )
        second_response = post(
            {
                "model": "glm-4",
                "previous_response_id": first_response["id"],
                "input": [
                    {
                        "type": "function_call_output",
                        "call_id": "call-1",
                        "output": {"temperature": 21},
                    }
                ],
            }
        )
    finally:
        server.shutdown()
        thread.join(timeout=1)

    continued_payload = fake_glm.payloads[1]
    assistant_message = next(message for message in continued_payload["messages"] if message["role"] == "assistant")
    tool_message = next(message for message in continued_payload["messages"] if message["role"] == "tool")

    assert continued_payload["tool_choice"] == {"type": "function", "function": {"name": "lookup"}}
    assert continued_payload["parallel_tool_calls"] is False
    assert continued_payload["tools"][0]["function"]["name"] == "lookup"
    assert assistant_message["tool_calls"][0]["id"] == "call-1"
    assert tool_message["tool_call_id"] == "call-1"
    assert tool_message["name"] == "lookup"
    assert tool_message["content"] == '{"temperature":21}'
    assert second_response["previous_response_id"] == first_response["id"]
    assert second_response["output_text"] == "done"


# --- P3: C-18/A-06 — sampling-parameter und stop werden weitergereicht ----


def test_stop_sequences_are_carried_into_internal_payload():
    from glm2api.services.anthropic_adapter import anthropic_to_openai

    payload = anthropic_to_openai(
        {
            "messages": [{"role": "user", "content": "x"}],
            "stop_sequences": ["ENDE", "STOP"],
        }
    )
    assert payload.get("stop") == ["ENDE", "STOP"]


def test_client_extracts_tool_choice_policy_and_stop():
    """C-18/T-18: policy und stop werden aus dem request gezogen und
    durchgesetzt — nicht nur in den prompt geschrieben."""
    from glm2api.services.glm_client import GLMWebClient

    policy, stops = GLMWebClient._extract_tool_choice_and_stop(
        {"tool_choice": "required", "stop": "ENDE", "stop_sequences": ["X", "ENDE"]}
    )
    assert policy["mode"] == "required"
    assert stops == ("ENDE", "X"), "reihenfolge bleibt stabil, duplikate raus"

    policy_specific, _ = GLMWebClient._extract_tool_choice_and_stop(
        {"tool_choice": {"type": "function", "function": {"name": "read"}}}
    )
    assert policy_specific["mode"] == "specific"
    assert policy_specific["tool_name"] == "read"
