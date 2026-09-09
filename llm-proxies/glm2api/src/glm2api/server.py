from __future__ import annotations

import json
import queue
import socket
import threading
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from logging import Logger
from urllib.parse import urlparse

from .config import AppConfig
from .logging_utils import debug_dump
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


_CLIENT_DISCONNECTED = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, socket.timeout)
RESPONSES_STREAM_HEARTBEAT_SECONDS = 5.0


class GLM2APIServer:
    def __init__(self, config: AppConfig, glm_client: GLMWebClient, logger: Logger) -> None:
        self.config = config
        self.glm_client = glm_client
        self.logger = logger
        handler_cls = self._build_handler()
        # daemon_threads + allow_reuse_address als Klassen-Attribute: nach der
        # Instantiierung gesetzte Werte wirkten nicht mehr (Bindung schon passiert)
        class _Server(ThreadingHTTPServer):
            daemon_threads = True
            allow_reuse_address = True

        self._server = _Server((config.host, config.port), handler_cls)

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
            server_version = "glm2api/0.1.0"
            protocol_version = "HTTP/1.1"

            def do_OPTIONS(self) -> None:
                self.send_response(HTTPStatus.NO_CONTENT)
                self._send_common_headers()
                self.end_headers()

            def do_GET(self) -> None:
                try:
                    self._debug_log_request_start()
                    path = self._path_without_query()
                    if path == "/health":
                        self._write_json(HTTPStatus.OK, {"status": "ok"})
                        return

                    if path == f"{config.api_prefix}/models":
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
                    self._write_json(HTTPStatus.NOT_FOUND, {"error": {"message": "Not Found"}})
                except _CLIENT_DISCONNECTED:
                    logger.warning("Client disconnected before GET response was written path=%s", self.path)
                except Exception as exc:
                    logger.error("Failed to handle GET request path=%s error=%s\n%s", self.path, exc, traceback.format_exc())
                    self._safe_write_json(
                        HTTPStatus.INTERNAL_SERVER_ERROR,
                        {"error": {"message": "Internal server error", "type": exc.__class__.__name__}},
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
                        self._write_json(HTTPStatus.NOT_FOUND, {"error": {"message": "Not Found"}})
                        return

                    if not self._authorize():
                        logger.warning("Authentication failed path=%s ip=%s", self.path, self.client_address[0])
                        self._write_json(HTTPStatus.UNAUTHORIZED, {"error": {"message": "Unauthorized"}})
                        return

                    content_length = self._parse_content_length()
                    if content_length < 0:
                        self._write_json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": {"message": "Content-Length must not be negative.", "type": "invalid_content_length"}},
                        )
                        return
                    raw_body = self.rfile.read(content_length) if content_length else b"{}"
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
                        result = glm_client.generate_images(payload)
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
                    result, conversation_id = glm_client.chat_completion(payload)
                    self._write_json(HTTPStatus.OK, result)
                except QueueTimeoutError as exc:
                    logger.warning("GLM queue wait timeout error=%s", exc)
                    self._write_json(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        {"error": {"message": str(exc), "type": "queue_timeout"}},
                    )
                except UpstreamAPIError as exc:
                    logger.warning("Upstream GLM returned an error status=%s error=%s", exc.status_code, exc)
                    status = self._safe_http_status(exc.status_code, fallback=HTTPStatus.BAD_GATEWAY)
                    self._write_json(
                        status,
                        {"error": {"message": str(exc), "type": "upstream_error", "details": exc.payload}},
                    )
                except ValueError as exc:
                    logger.warning("Invalid request parameters path=%s error=%s", self.path, exc)
                    self._write_json(
                        HTTPStatus.BAD_REQUEST,
                        {"error": {"message": str(exc), "type": "invalid_request"}},
                    )
                except _CLIENT_DISCONNECTED as exc:
                    logger.warning("Client disconnected early path=%s error=%s", self.path, exc)
                except Exception as exc:
                    logger.error("Failed to handle request error=%s\n%s", exc, traceback.format_exc())
                    self._safe_write_json(
                        HTTPStatus.BAD_GATEWAY,
                        {"error": {"message": str(exc), "type": exc.__class__.__name__}},
                    )

            # ---- Anthropic Messages API ----

            def _handle_anthropic_messages(self, payload: dict[str, object]) -> None:
                model = str(payload.get("model", "glm-4"))
                openai_payload = anthropic_to_openai(payload)

                if payload.get("stream"):
                    self._stream_anthropic(openai_payload, model)
                    return

                result, _ = glm_client.chat_completion(openai_payload)
                response = openai_to_anthropic_response(result, model)
                self._write_json(HTTPStatus.OK, response)

            def _stream_anthropic(self, openai_payload: dict[str, object], model: str) -> None:
                openai_payload["stream"] = True
                stream_iter = glm_client.stream_chat_completion(openai_payload)
                accumulator = AnthropicStreamAccumulator(model=model)

                self.send_response(HTTPStatus.OK)
                self._send_common_headers()
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()

                try:
                    for chunk in stream_iter:
                        if not chunk:
                            continue
                        if not accumulator.started:
                            start_event = accumulator.start_message()
                            self.wfile.write(start_event.encode("utf-8"))
                            self.wfile.flush()
                        events = accumulator.feed_chunk(chunk)
                        for event in events:
                            self.wfile.write(event.encode("utf-8"))
                            self.wfile.flush()
                except _CLIENT_DISCONNECTED as exc:
                    logger.warning("Client disconnected during Anthropic streaming response model=%s error=%s", model, exc)
                    return
                except Exception as exc:
                    logger.error("Anthropic streaming request failed model=%s error=%s\n%s", model, exc, traceback.format_exc())

                # Ensure message_stop is always sent (idempotent via _finished flag)
                if accumulator.started:
                    try:
                        for event in accumulator._finish():
                            self.wfile.write(event.encode("utf-8"))
                            self.wfile.flush()
                    except _CLIENT_DISCONNECTED:
                        pass

                logger.info("Anthropic streaming request completed model=%s", model)

            # ---- OpenAI Responses API ----

            def _handle_responses(self, payload: dict[str, object]) -> None:
                model = str(payload.get("model", "glm-4"))
                openai_payload = responses_to_openai(payload)

                if payload.get("stream"):
                    self._stream_responses(openai_payload, model)
                    return

                result, _ = glm_client.chat_completion(openai_payload)
                response = openai_to_responses(result, model)
                self._write_json(HTTPStatus.OK, response)

            def _stream_responses(self, openai_payload: dict[str, object], model: str) -> None:
                openai_payload["stream"] = True
                stream_iter = glm_client.stream_chat_completion(openai_payload)
                accumulator = ResponsesStreamAccumulator(model=model)

                self.send_response(HTTPStatus.OK)
                self._send_common_headers()
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()

                chunk_queue: queue.Queue[object] = queue.Queue()
                sentinel = object()

                def read_upstream() -> None:
                    try:
                        for upstream_chunk in stream_iter:
                            chunk_queue.put(upstream_chunk)
                    except BaseException as exc:
                        chunk_queue.put(exc)
                    finally:
                        chunk_queue.put(sentinel)

                threading.Thread(target=read_upstream, daemon=True).start()

                try:
                    while True:
                        try:
                            queued = chunk_queue.get(timeout=RESPONSES_STREAM_HEARTBEAT_SECONDS)
                        except queue.Empty:
                            self.wfile.write(b": keep-alive\n\n")
                            self.wfile.flush()
                            continue

                        if queued is sentinel:
                            break
                        if isinstance(queued, BaseException):
                            raise queued
                        chunk = queued
                        if not chunk:
                            continue
                        if not accumulator.started:
                            start_events = accumulator.start_response()
                            for event in start_events:
                                self.wfile.write(event.encode("utf-8"))
                            self.wfile.flush()
                        events = accumulator.feed_chunk(chunk)  # type: ignore[arg-type]
                        for event in events:
                            self.wfile.write(event.encode("utf-8"))
                            self.wfile.flush()
                except _CLIENT_DISCONNECTED as exc:
                    logger.warning("Client disconnected during Responses streaming response model=%s error=%s", model, exc)
                    return
                except Exception as exc:
                    logger.error("Responses streaming request failed model=%s error=%s\n%s", model, exc, traceback.format_exc())

                # Ensure response.completed is always sent (idempotent via _finished flag)
                if accumulator.started:
                    try:
                        for event in accumulator._finish():
                            self.wfile.write(event.encode("utf-8"))
                            self.wfile.flush()
                    except _CLIENT_DISCONNECTED:
                        pass

                logger.info("Responses streaming request completed model=%s", model)

            # ---- Chat completions (original) ----

            def _stream_completion(self, payload: dict[str, object]) -> None:
                model = str(payload.get("model", "unknown"))
                logger.info("Starting streaming response model=%s", model)
                stream_iter = glm_client.stream_chat_completion(payload)
                self.send_response(HTTPStatus.OK)
                self._send_common_headers()
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()

                sent_done = False
                try:
                    for chunk in stream_iter:
                        if chunk:
                            debug_dump(logger, config.debug_dump_all, f"HTTP outbound streaming chunk model={model}", chunk)
                            self.wfile.write(chunk)
                            self.wfile.flush()
                            if b"data: [DONE]\n\n" in chunk:
                                sent_done = True
                except UpstreamAPIError as exc:
                    logger.warning("Upstream error received mid-stream status=%s error=%s", exc.status_code, exc)
                    self._write_sse_error(str(exc), "upstream_error")
                except _CLIENT_DISCONNECTED as exc:
                    logger.warning("Client disconnected during streaming response model=%s error=%s", model, exc)
                    return
                except Exception as exc:
                    logger.error("Streaming request failed model=%s error=%s\n%s", model, exc, traceback.format_exc())
                    self._write_sse_error(str(exc), exc.__class__.__name__)
                finally:
                    if not sent_done:
                        try:
                            self.wfile.write(b"data: [DONE]\n\n")
                            self.wfile.flush()
                        except _CLIENT_DISCONNECTED:
                            pass
                logger.info("Streaming request completed model=%s", model)

            # ---- Auth ----

            def _authorize(self) -> bool:
                if not config.server_api_keys:
                    return True
                # Support both Bearer token and x-api-key header (Anthropic style)
                authorization = self.headers.get("Authorization", "")
                if authorization.startswith("Bearer "):
                    token = authorization[7:].strip()
                    if token in config.server_api_keys:
                        return True
                x_api_key = self.headers.get("x-api-key", "")
                if x_api_key and x_api_key.strip() in config.server_api_keys:
                    return True
                return False

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
                self.send_header("Access-Control-Allow-Origin", config.cors_allow_origin)
                self.send_header(
                    "Access-Control-Allow-Headers",
                    "Authorization, Content-Type, x-api-key, anthropic-version",
                )
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

            def _safe_write_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
                try:
                    self._write_json(status, payload)
                except _CLIENT_DISCONNECTED:
                    logger.warning("Client disconnected before JSON response was written path=%s", self.path)

            def _parse_content_length(self) -> int:
                raw_value = self.headers.get("Content-Length", "0").strip()
                try:
                    return int(raw_value or "0")
                except ValueError as exc:
                    raise ValueError(f"Invalid Content-Length: {raw_value}") from exc

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
                except _CLIENT_DISCONNECTED:
                    logger.warning("Client disconnected before SSE error was written path=%s", self.path)

            def _safe_http_status(self, value: int, fallback: HTTPStatus) -> HTTPStatus:
                try:
                    return HTTPStatus(value)
                except ValueError:
                    return fallback

            def _debug_log_request_start(self) -> None:
                debug_dump(
                    logger,
                    config.debug_dump_all,
                    f"HTTP inbound request {self.command} {self.path} headers",
                    {key: value for key, value in self.headers.items()},
                )

            def _path_without_query(self) -> str:
                return urlparse(self.path).path

            def log_message(self, format: str, *args) -> None:
                logger.info("%s - %s", self.address_string(), format % args)

        return RequestHandler
