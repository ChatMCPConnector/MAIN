from __future__ import annotations

import hmac
import json
import queue
import socket
import threading
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from logging import Logger
from typing import Any
from urllib.parse import urlparse

from . import __version__
from .config import (
    DEFAULT_MAX_CONNECTIONS,
    DEFAULT_MAX_HEADER_BYTES,
    DEFAULT_MAX_HEADERS,
    DEFAULT_MAX_REQUEST_BODY_BYTES,
    DEFAULT_MAX_REQUEST_LINE_BYTES,
    DEFAULT_REQUEST_QUEUE_SIZE,
    DEFAULT_REQUEST_SOCKET_TIMEOUT_SECONDS,
    MAX_CONNECTIONS_LIMIT,
    MAX_HEADER_BYTES_LIMIT,
    MAX_HEADERS_LIMIT,
    MAX_REQUEST_BODY_BYTES_LIMIT,
    MAX_REQUEST_LINE_BYTES_LIMIT,
    MAX_REQUEST_QUEUE_SIZE_LIMIT,
    MAX_REQUEST_SOCKET_TIMEOUT_SECONDS,
    AppConfig,
    is_loopback_host,
)
from .logging_utils import debug_dump, redact_sensitive_data, redact_sensitive_text
from .services.anthropic_adapter import (
    AnthropicStreamAccumulator,
    anthropic_to_openai,
    openai_to_anthropic_response,
)
from .services.glm_client import GLMWebClient, QueueTimeoutError, UpstreamAPIError
from .services.responses_adapter import (
    ResponsesStreamAccumulator,
    openai_to_responses,
    responses_to_openai,
)


_CLIENT_DISCONNECTED = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)
_DOWNSTREAM_DISCONNECTED = (*_CLIENT_DISCONNECTED, TimeoutError)
_UPSTREAM_TRANSPORT_ERRORS = (socket.timeout, TimeoutError, ConnectionError, OSError)
STREAM_HEARTBEAT_SECONDS = 5.0


def _config_limit(
    config: object,
    name: str,
    default: int,
    maximum: int | None = None,
) -> int:
    try:
        value = int(getattr(config, name))
    except (AttributeError, TypeError, ValueError):
        return default
    value = max(1, value)
    return min(value, maximum) if maximum is not None else value


class _BoundedThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address,
        request_handler,
        *,
        max_connections: int,
        request_queue_size: int,
    ) -> None:
        self.request_queue_size = max(1, request_queue_size)
        self._connection_slots = threading.BoundedSemaphore(max(1, max_connections))
        super().__init__(server_address, request_handler)

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self._connection_slots.acquire(blocking=False):
            try:
                request.settimeout(1.0)
                request.sendall(
                    b"HTTP/1.1 503 Service Unavailable\r\n"
                    b"Connection: close\r\n"
                    b"Content-Length: 0\r\n\r\n"
                )
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._connection_slots.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._connection_slots.release()


class GLM2APIServer:
    def __init__(self, config: AppConfig, glm_client: GLMWebClient, logger: Logger) -> None:
        self.config = config
        self.glm_client = glm_client
        self.logger = logger
        if not is_loopback_host(getattr(config, "host", "127.0.0.1")) and not getattr(
            config, "server_api_keys", []
        ):
            raise ValueError("SERVER_API_KEYS must be configured for non-loopback HTTP bindings")
        if not is_loopback_host(getattr(config, "host", "127.0.0.1")) and getattr(
            config, "cors_allow_origin", ""
        ) == "*":
            raise ValueError("CORS wildcard is not allowed for non-loopback HTTP bindings")
        handler_cls = self._build_handler()
        self._server = _BoundedThreadingHTTPServer(
            (config.host, config.port),
            handler_cls,
            max_connections=_config_limit(
                config, "max_connections", DEFAULT_MAX_CONNECTIONS, MAX_CONNECTIONS_LIMIT
            ),
            request_queue_size=_config_limit(
                config, "request_queue_size", DEFAULT_REQUEST_QUEUE_SIZE, MAX_REQUEST_QUEUE_SIZE_LIMIT
            ),
        )

    def serve_forever(self) -> None:
        self._server.serve_forever()

    def shutdown(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def _build_handler(self):
        config = self.config
        glm_client = self.glm_client
        logger = self.logger

        class RequestHandler(BaseHTTPRequestHandler):
            server_version = f"glm2api/{__version__}"
            sys_version = ""
            protocol_version = "HTTP/1.1"

            def version_string(self) -> str:
                return self.server_version

            def setup(self) -> None:
                super().setup()
                try:
                    socket_timeout = float(
                        getattr(
                            config,
                            "request_socket_timeout",
                            getattr(config, "request_timeout", DEFAULT_REQUEST_SOCKET_TIMEOUT_SECONDS),
                        )
                    )
                except (TypeError, ValueError):
                    socket_timeout = DEFAULT_REQUEST_SOCKET_TIMEOUT_SECONDS
                if socket_timeout <= 0:
                    socket_timeout = DEFAULT_REQUEST_SOCKET_TIMEOUT_SECONDS
                socket_timeout = min(socket_timeout, MAX_REQUEST_SOCKET_TIMEOUT_SECONDS)
                self.connection.settimeout(socket_timeout)

            def send_response(self, code, message=None) -> None:
                self._response_started = True
                super().send_response(code, message)

            def send_header(self, keyword, value) -> None:
                if str(keyword).lower() == "connection" and str(value).lower() == "close":
                    self._connection_header_sent = True
                super().send_header(keyword, value)

            def end_headers(self) -> None:
                if getattr(self, "close_connection", False) and not getattr(
                    self, "_connection_header_sent", False
                ):
                    self.send_header("Connection", "close")
                super().end_headers()

            def send_error(self, code, message=None, explain=None) -> None:
                self.close_connection = True
                super().send_error(code, message, explain)

            def handle_one_request(self) -> None:
                self._connection_header_sent = False
                self._response_started = False
                try:
                    request_line_limit = _config_limit(
                        config, "max_request_line", DEFAULT_MAX_REQUEST_LINE_BYTES, MAX_REQUEST_LINE_BYTES_LIMIT
                    )
                    self.raw_requestline = self.rfile.readline(request_line_limit + 1)
                    if len(self.raw_requestline) > request_line_limit:
                        self.requestline = ""
                        self.request_version = ""
                        self.command = ""
                        self.send_error(HTTPStatus.REQUEST_URI_TOO_LONG, "Request line too long")
                        return
                    if not self.raw_requestline:
                        self.close_connection = True
                        return
                    if not self.parse_request():
                        return
                    if self.headers.get("Transfer-Encoding") is not None:
                        self._write_error_json(
                            HTTPStatus.NOT_IMPLEMENTED,
                            {
                                "error": {
                                    "message": "Transfer-Encoding is not supported.",
                                    "type": "transfer_encoding_not_supported",
                                }
                            },
                        )
                        return
                    method_name = "do_" + self.command
                    if not hasattr(self, method_name):
                        self.send_error(
                            HTTPStatus.NOT_IMPLEMENTED,
                            "Unsupported method (%r)" % self.command,
                        )
                        return
                    getattr(self, method_name)()
                    self.wfile.flush()
                except _CLIENT_DISCONNECTED as exc:
                    self.close_connection = True
                    self.log_error("Client disconnected: %r", exc)
                except TimeoutError as exc:
                    self.close_connection = True
                    if not getattr(self, "_response_started", False):
                        try:
                            self.send_error(HTTPStatus.REQUEST_TIMEOUT, "Request timed out")
                        except OSError:
                            pass
                    self.log_error("Request timed out: %r", exc)

            def parse_request(self) -> bool:
                if not super().parse_request():
                    return False
                header_count = len(self.headers)
                header_limit = _config_limit(
                    config, "max_headers", DEFAULT_MAX_HEADERS, MAX_HEADERS_LIMIT
                )
                if header_count > header_limit:
                    self.send_error(
                        HTTPStatus.REQUEST_HEADER_FIELDS_TOO_LARGE,
                        "Too many request headers",
                    )
                    return False
                header_bytes = len(self.raw_requestline)
                for key, value in self.headers.items():
                    header_bytes += len(str(key).encode("iso-8859-1")) + len(
                        str(value).encode("iso-8859-1")
                    ) + 4
                header_byte_limit = _config_limit(
                    config, "max_header_bytes", DEFAULT_MAX_HEADER_BYTES, MAX_HEADER_BYTES_LIMIT
                )
                if header_bytes > header_byte_limit:
                    self.send_error(
                        HTTPStatus.REQUEST_HEADER_FIELDS_TOO_LARGE,
                        "Request headers too large",
                    )
                    return False
                return True

            def do_OPTIONS(self) -> None:
                self.send_response(HTTPStatus.NO_CONTENT)
                self._send_common_headers()
                self.end_headers()

            def do_GET(self) -> None:
                try:
                    self._debug_log_request_start()
                    path = self._path_without_query()
                    if path == "/health":
                        if not self._authorize():
                            logger.warning("Authentication failed path=%s ip=%s", self.path, self.client_address[0])
                            self._write_error_json(
                                HTTPStatus.UNAUTHORIZED,
                                {"error": {"message": "Unauthorized"}},
                            )
                            return
                        self._write_json(HTTPStatus.OK, {"status": "ok"})
                        return

                    if path == f"{config.api_prefix}/models":
                        if not self._authorize():
                            logger.warning("Authentication failed path=%s ip=%s", self.path, self.client_address[0])
                            self._write_error_json(
                                HTTPStatus.UNAUTHORIZED,
                                {"error": {"message": "Unauthorized"}},
                            )
                            return
                        self._write_json(
                            HTTPStatus.OK,
                            {
                                "object": "list",
                                "data": [
                                    {"id": model, "object": "model", "owned_by": "glm2api"}
                                    for model in config.exposed_models
                                ],
                            },
                        )
                        return

                    logger.debug("GET unmatched path=%s", self.path)
                    self._write_error_json(
                        HTTPStatus.NOT_FOUND,
                        {"error": {"message": "Not Found"}},
                    )
                except _DOWNSTREAM_DISCONNECTED:
                    logger.warning("Client disconnected before GET response was written path=%s", self.path)
                except Exception as exc:
                    logger.error("Failed to handle GET request path=%s error=%s\n%s", self.path, exc, traceback.format_exc())
                    self._safe_write_json(
                        HTTPStatus.INTERNAL_SERVER_ERROR,
                        {"error": {"message": "Internal server error", "type": "internal_error"}},
                    )

            def do_POST(self) -> None:
                try:
                    self._debug_log_request_start()
                    path = self._path_without_query()
                    if path not in {
                        f"{config.api_prefix}/chat/completions",
                        f"{config.api_prefix}/images/generations",
                        f"{config.api_prefix}/messages",
                        f"{config.api_prefix}/responses",
                    }:
                        logger.debug("POST unmatched path=%s", self.path)
                        self._write_error_json(
                            HTTPStatus.NOT_FOUND,
                            {"error": {"message": "Not Found"}},
                        )
                        return

                    if not self._authorize():
                        logger.warning("Authentication failed path=%s ip=%s", self.path, self.client_address[0])
                        self._write_error_json(
                            HTTPStatus.UNAUTHORIZED,
                            {"error": {"message": "Unauthorized"}},
                        )
                        return

                    content_length = self._parse_content_length()
                    if content_length is None:
                        return
                    try:
                        raw_body = self.rfile.read(content_length) if content_length else b""
                    except TimeoutError:
                        self._write_error_json(
                            HTTPStatus.REQUEST_TIMEOUT,
                            {"error": {"message": "Request body read timed out.", "type": "request_timeout"}},
                        )
                        return
                    if len(raw_body) != content_length:
                        self._write_error_json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": {"message": "Request body was incomplete.", "type": "incomplete_body"}},
                        )
                        return
                    debug_dump(logger, config.debug_dump_all, f"HTTP inbound raw request body path={self.path}", raw_body)
                    try:
                        payload = json.loads(raw_body.decode("utf-8"))
                    except UnicodeDecodeError:
                        self._write_json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": {"message": "Request body must be UTF-8 encoded.", "type": "invalid_encoding"}},
                        )
                        return
                    except json.JSONDecodeError as exc:
                        self._write_json(
                            HTTPStatus.BAD_REQUEST,
                            {
                                "error": {
                                    "message": f"Request body is not valid JSON: {exc.msg}",
                                    "type": "invalid_json",
                                }
                            },
                        )
                        return

                    if not isinstance(payload, dict):
                        self._write_json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": {"message": "Request body top level must be a JSON object.", "type": "invalid_payload"}},
                        )
                        return
                    debug_dump(logger, config.debug_dump_all, f"HTTP inbound parsed JSON path={self.path}", payload)

                    # --- Anthropic Messages API ---
                    if path == f"{config.api_prefix}/messages":
                        logger.info("Received Anthropic request model=%s stream=%s", payload.get("model"), payload.get("stream"))
                        self._handle_anthropic_messages(payload)
                        return

                    # --- OpenAI Responses API ---
                    if path == f"{config.api_prefix}/responses":
                        logger.info("Received Responses request model=%s stream=%s", payload.get("model"), payload.get("stream"))
                        self._handle_responses(payload)
                        return

                    # --- Image generation ---
                    if path == f"{config.api_prefix}/images/generations":
                        if not payload.get("prompt"):
                            self._write_json(
                                HTTPStatus.BAD_REQUEST,
                                {"error": {"message": "Image generation request must include a prompt field."}},
                            )
                            return
                        logger.info("Received image generation request model=%s prompt=%s", payload.get("model"), payload.get("prompt"))
                        result = self._call_upstream(glm_client.generate_images, payload)
                        self._write_json(HTTPStatus.OK, result)
                        return

                    # --- Chat completions ---
                    if not isinstance(payload.get("messages"), list) or not payload.get("model"):
                        self._write_json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": {"message": "Request body must include model and messages fields."}},
                        )
                        return

                    if payload.get("stream"):
                        self._stream_completion(payload)
                        return

                    logger.info("Received chat request model=%s", payload.get("model"))
                    result, _ = self._call_upstream(glm_client.chat_completion, payload)
                    self._write_json(HTTPStatus.OK, result)
                except QueueTimeoutError as exc:
                    logger.warning("GLM queue wait timeout error=%s", exc)
                    self._safe_write_json(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        {"error": {"message": "Service is busy. Please retry later.", "type": "queue_timeout"}},
                    )
                except UpstreamAPIError as exc:
                    logger.warning(
                        "Upstream GLM returned an error status=%s error=%s payload=%r",
                        exc.status_code,
                        exc,
                        redact_sensitive_data(exc.payload),
                    )
                    status = self._safe_http_status(exc.status_code, fallback=HTTPStatus.BAD_GATEWAY)
                    self._safe_write_json(
                        status,
                        {"error": {"message": "Upstream service error.", "type": "upstream_error"}},
                    )
                except ValueError as exc:
                    logger.warning("Invalid request parameters path=%s error=%s", self.path, exc)
                    self._safe_write_json(
                        HTTPStatus.BAD_REQUEST,
                        {"error": {"message": "Invalid request.", "type": "invalid_request"}},
                    )
                except _DOWNSTREAM_DISCONNECTED as exc:
                    logger.warning("Client disconnected early path=%s error=%s", self.path, exc)
                except _UPSTREAM_TRANSPORT_ERRORS as exc:
                    logger.error("Upstream transport failed path=%s error=%s", self.path, exc)
                    self._safe_write_json(
                        HTTPStatus.GATEWAY_TIMEOUT,
                        {"error": {"message": "Upstream service unavailable.", "type": "upstream_error"}},
                    )
                except Exception as exc:
                    logger.error("Failed to handle request error=%s\n%s", exc, traceback.format_exc())
                    self._safe_write_json(
                        HTTPStatus.INTERNAL_SERVER_ERROR,
                        {"error": {"message": "Internal server error.", "type": "internal_error"}},
                    )

            # ---- Anthropic Messages API ----

            def _handle_anthropic_messages(self, payload: dict[str, object]) -> None:
                model = str(payload.get("model", "glm-4"))
                openai_payload = anthropic_to_openai(payload)

                if payload.get("stream"):
                    self._stream_anthropic(openai_payload, model)
                    return

                result, _ = self._call_upstream(glm_client.chat_completion, openai_payload)
                response = openai_to_anthropic_response(result, model)
                self._write_json(HTTPStatus.OK, response)

            def _stream_anthropic(self, openai_payload: dict[str, object], model: str) -> None:
                openai_payload["stream"] = True
                stream_iter = self._open_upstream_stream(openai_payload)
                accumulator = AnthropicStreamAccumulator(model=model)

                self._run_accumulated_sse_stream(
                    stream_iter=stream_iter,
                    accumulator=accumulator,
                    start=lambda: [accumulator.start_message()],
                    heartbeat=AnthropicStreamAccumulator.ping_event().encode("utf-8"),
                    error_event=lambda message, error_type: accumulator.error_event(message, error_type),
                    model=model,
                    label="Anthropic",
                )

            # ---- OpenAI Responses API ----

            def _handle_responses(self, payload: dict[str, object]) -> None:
                model = str(payload.get("model", "glm-4"))
                openai_payload = responses_to_openai(payload)

                if payload.get("stream"):
                    self._stream_responses(openai_payload, model)
                    return

                result, _ = self._call_upstream(glm_client.chat_completion, openai_payload)
                response = openai_to_responses(result, model)
                self._write_json(HTTPStatus.OK, response)

            def _stream_responses(self, openai_payload: dict[str, object], model: str) -> None:
                openai_payload["stream"] = True
                stream_iter = self._open_upstream_stream(openai_payload)
                accumulator = ResponsesStreamAccumulator(model=model)

                self._run_accumulated_sse_stream(
                    stream_iter=stream_iter,
                    accumulator=accumulator,
                    start=accumulator.start_response,
                    heartbeat=b": keep-alive\n\n",
                    error_event=lambda message, error_type: accumulator.error_event(message, error_type),
                    model=model,
                    label="Responses",
                )

            def _run_accumulated_sse_stream(
                self,
                stream_iter,
                accumulator,
                start,
                heartbeat: bytes,
                error_event,
                model: str,
                label: str,
            ) -> None:
                """Gemeinsamer SSE-Loop fuer /v1/messages und /v1/responses:
                heartbeat bei upstream-stille, spec-konforme error-events bei
                mid-stream-fehlern (statt stillem abbruch) und idempotente
                finish-events am ende."""

                self.send_response(HTTPStatus.OK)
                self._send_common_headers()
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()

                chunk_queue: queue.Queue[object] = queue.Queue(maxsize=16)
                sentinel = object()
                reader_cancelled = threading.Event()

                def enqueue(item: object) -> bool:
                    while not reader_cancelled.is_set():
                        try:
                            chunk_queue.put(item, timeout=0.5)
                            return True
                        except queue.Full:
                            continue
                    return False

                def read_upstream() -> None:
                    try:
                        for upstream_chunk in stream_iter:
                            if not enqueue(upstream_chunk):
                                return
                    except _UPSTREAM_TRANSPORT_ERRORS as exc:
                        enqueue(UpstreamAPIError(504, "Upstream service unavailable"))
                        logger.warning("%s upstream transport failed model=%s error=%s", label, model, exc)
                    except ValueError:
                        enqueue(UpstreamAPIError(502, "Upstream service error"))
                    except Exception as exc:
                        enqueue(exc)
                    finally:
                        enqueue(sentinel)

                threading.Thread(target=read_upstream, daemon=True).start()

                failed: Exception | None = None
                client_disconnected = False
                try:
                    while True:
                        try:
                            queued = chunk_queue.get(timeout=STREAM_HEARTBEAT_SECONDS)
                        except queue.Empty:
                            self.wfile.write(heartbeat)
                            self.wfile.flush()
                            continue

                        if queued is sentinel:
                            break
                        if isinstance(queued, Exception):
                            raise queued
                        chunk = queued
                        if not chunk:
                            continue
                        if not accumulator.started:
                            for event in start():
                                self.wfile.write(event.encode("utf-8"))
                            self.wfile.flush()
                        for event in accumulator.feed_chunk(chunk):  # type: ignore[arg-type]
                            self.wfile.write(event.encode("utf-8"))
                        self.wfile.flush()
                except UpstreamAPIError as exc:
                    failed = exc
                    logger.warning(
                        "%s upstream request failed model=%s status=%s error=%s",
                        label,
                        model,
                        exc.status_code,
                        exc,
                    )
                    try:
                        self.wfile.write(
                            error_event("Upstream service error.", "upstream_error").encode("utf-8")
                        )
                        self.wfile.flush()
                    except _DOWNSTREAM_DISCONNECTED:
                        client_disconnected = True
                except _DOWNSTREAM_DISCONNECTED as exc:
                    client_disconnected = True
                    logger.warning("Client disconnected during %s streaming response model=%s error=%s", label, model, exc)
                except Exception as exc:
                    failed = exc
                    logger.error("%s streaming request failed model=%s error=%s\n%s", label, model, exc, traceback.format_exc())
                    try:
                        self.wfile.write(
                            error_event("Streaming request failed.", "internal_error").encode("utf-8")
                        )
                        self.wfile.flush()
                    except _DOWNSTREAM_DISCONNECTED:
                        client_disconnected = True
                finally:
                    reader_cancelled.set()
                    close = getattr(stream_iter, "close", None)
                    if close is not None:
                        try:
                            close()
                        except Exception:
                            pass

                if client_disconnected:
                    return

                if accumulator.started and failed is None:
                    try:
                        for event in accumulator.finish():
                            self.wfile.write(event.encode("utf-8"))
                        self.wfile.flush()
                    except _DOWNSTREAM_DISCONNECTED:
                        return

                logger.info("%s streaming request completed model=%s failed=%s", label, model, bool(failed))

            # ---- Chat completions (original) ----

            def _stream_completion(self, payload: dict[str, object]) -> None:
                model = str(payload.get("model", "unknown"))
                logger.info("Starting streaming response model=%s", model)
                stream_iter = self._open_upstream_stream(payload)
                self.send_response(HTTPStatus.OK)
                self._send_common_headers()
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()

                sent_done = False
                failed = False
                client_disconnected = False
                iterator = iter(stream_iter)
                try:
                    while True:
                        try:
                            chunk = next(iterator)
                        except StopIteration:
                            break
                        except _UPSTREAM_TRANSPORT_ERRORS as exc:
                            raise UpstreamAPIError(504, "Upstream service unavailable") from exc
                        except ValueError as exc:
                            raise UpstreamAPIError(502, "Upstream service error") from exc
                        if chunk:
                            debug_dump(logger, config.debug_dump_all, f"HTTP outbound streaming chunk model={model}", chunk)
                            self.wfile.write(chunk)
                            self.wfile.flush()
                            if b"data: [DONE]\n\n" in chunk:
                                sent_done = True
                except UpstreamAPIError as exc:
                    failed = True
                    logger.warning("Upstream error received mid-stream status=%s error=%s", exc.status_code, exc)
                    self._write_sse_error("Upstream service error.", "upstream_error")
                except _DOWNSTREAM_DISCONNECTED as exc:
                    client_disconnected = True
                    logger.warning("Client disconnected during streaming response model=%s error=%s", model, exc)
                except Exception as exc:
                    failed = True
                    logger.error("Streaming request failed model=%s error=%s\n%s", model, exc, traceback.format_exc())
                    self._write_sse_error("Streaming request failed.", "internal_error")
                finally:
                    close = getattr(stream_iter, "close", None)
                    if close is not None:
                        try:
                            close()
                        except Exception:
                            pass
                    if not sent_done and not failed and not client_disconnected:
                        try:
                            self.wfile.write(b"data: [DONE]\n\n")
                            self.wfile.flush()
                        except _DOWNSTREAM_DISCONNECTED:
                            client_disconnected = True
                logger.info("Streaming request completed model=%s failed=%s", model, failed)

            def _call_upstream(self, operation, *args, **kwargs):
                try:
                    return operation(*args, **kwargs)
                except UpstreamAPIError:
                    raise
                except ValueError as exc:
                    raise UpstreamAPIError(502, "Upstream service error") from exc
                except _UPSTREAM_TRANSPORT_ERRORS as exc:
                    raise UpstreamAPIError(504, "Upstream service unavailable") from exc

            def _open_upstream_stream(self, payload: dict[str, object]):
                try:
                    return glm_client.stream_chat_completion(payload)
                except UpstreamAPIError:
                    raise
                except ValueError as exc:
                    raise UpstreamAPIError(502, "Upstream service error") from exc
                except _UPSTREAM_TRANSPORT_ERRORS as exc:
                    raise UpstreamAPIError(504, "Upstream service unavailable") from exc

            # ---- Auth ----

            def _authorize(self) -> bool:
                if not config.server_api_keys:
                    return True
                authorization = self.headers.get("Authorization", "")
                scheme, separator, token = authorization.partition(" ")
                bearer_token = token.strip() if separator and scheme.lower() == "bearer" else ""
                x_api_key = self.headers.get("x-api-key", "").strip()
                supplied_tokens = tuple(token for token in (bearer_token, x_api_key) if token)
                authorized = False
                for supplied_token in supplied_tokens:
                    for configured_token in config.server_api_keys:
                        authorized |= hmac.compare_digest(supplied_token, configured_token)
                return authorized

            # ---- Helpers ----

            def _write_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
                body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                debug_dump(logger, config.debug_dump_all, f"HTTP outbound JSON response status={int(status)} path={self.path}", body)
                self.send_response(status)
                self._send_common_headers()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_common_headers(self) -> None:
                origin = getattr(config, "cors_allow_origin", "")
                if origin:
                    self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header(
                    "Access-Control-Allow-Headers",
                    "Authorization, Content-Type, x-api-key, anthropic-version",
                )
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

            def _write_error_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
                self.close_connection = True
                self._write_json(status, payload)

            def _safe_write_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
                try:
                    self._write_json(status, payload)
                except _DOWNSTREAM_DISCONNECTED:
                    logger.warning("Client disconnected before JSON response was written path=%s", self.path)

            def _parse_content_length(self) -> int | None:
                raw_values = self.headers.get_all("Content-Length", [])
                if not raw_values:
                    self._write_error_json(
                        HTTPStatus.LENGTH_REQUIRED,
                        {"error": {"message": "Content-Length is required.", "type": "length_required"}},
                    )
                    return None
                if len(raw_values) != 1:
                    self._write_error_json(
                        HTTPStatus.BAD_REQUEST,
                        {"error": {"message": "Invalid Content-Length.", "type": "invalid_content_length"}},
                    )
                    return None
                raw_value = raw_values[0].strip()
                if not raw_value or not raw_value.isascii() or not raw_value.isdigit():
                    self._write_error_json(
                        HTTPStatus.BAD_REQUEST,
                        {"error": {"message": "Invalid Content-Length.", "type": "invalid_content_length"}},
                    )
                    return None
                try:
                    content_length = int(raw_value)
                except ValueError:
                    self._write_error_json(
                        HTTPStatus.BAD_REQUEST,
                        {"error": {"message": "Invalid Content-Length.", "type": "invalid_content_length"}},
                    )
                    return None
                body_limit = _config_limit(
                    config,
                    "max_request_body_bytes",
                    DEFAULT_MAX_REQUEST_BODY_BYTES,
                    MAX_REQUEST_BODY_BYTES_LIMIT,
                )
                if content_length > body_limit:
                    self._write_error_json(
                        HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                        {"error": {"message": "Request body is too large.", "type": "request_too_large"}},
                    )
                    return None
                return content_length

            def _write_sse_error(self, message: str, error_type: str) -> None:
                event = {
                    "error": {
                        "message": message,
                        "type": error_type,
                    }
                }
                try:
                    payload = f"data: {json.dumps(event, ensure_ascii=False, separators=(',', ':'))}\n\n".encode("utf-8")
                    self.wfile.write(payload)
                    self.wfile.flush()
                except _DOWNSTREAM_DISCONNECTED:
                    logger.warning("Client disconnected before SSE error was written path=%s", self.path)

            def _safe_http_status(self, value: int, fallback: HTTPStatus) -> HTTPStatus:
                try:
                    return HTTPStatus(value)
                except (TypeError, ValueError):
                    return fallback

            def _debug_log_request_start(self) -> None:
                headers = {key: value for key, value in self.headers.items()}
                debug_dump(
                    logger,
                    config.debug_dump_all,
                    f"HTTP inbound request {self.command} {self.path} headers",
                    redact_sensitive_data(headers),
                )

            def _path_without_query(self) -> str:
                return urlparse(self.path).path

            def log_message(self, format: str, *args) -> None:
                safe_args = tuple(redact_sensitive_data(arg) for arg in args)
                message = redact_sensitive_text(format % safe_args)
                logger.info("%s - %s", self.address_string(), message)

        return RequestHandler
