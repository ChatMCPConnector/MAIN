from __future__ import annotations

import base64
import codecs
import gzip
import http.client
import json
import mimetypes
import re
import threading
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from email.generator import _make_boundary # type: ignore
from io import BufferedReader, BytesIO
from logging import Logger
from typing import Callable

from ..config import AppConfig
from ..logging_utils import debug_dump
from .glm_auth import GLMAccessTokenManager, build_sign
from .translator import (
    BLOCKED_NATIVE_TOOL_NAMES,
    GLMEventAccumulator,
    SERVER_SIDE_TOOL_NAMES,
    convert_messages,
    extract_recent_user_url,
    filter_tools,
    resolve_chat_mode,
    resolve_networking,
    resolve_upstream_model,
)


FILE_UPLOAD_URL_SUFFIX = "/backend-api/assistant/file_upload"
FILE_SIZE_LIMIT = 100 * 1024 * 1024
IMAGE_SIZE_TO_ASPECT_RATIO = {
    "1024x1024": "1:1",
    "1024x1536": "2:3",
    "1536x1024": "3:2",
    "1024x1792": "9:16",
    "1792x1024": "16:9",
}


class UpstreamAPIError(RuntimeError):
    def __init__(self, status_code: int, message: str, payload: dict[str, object] | None = None, transient: bool = False) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}
        self.transient = transient


class QueueTimeoutError(RuntimeError):
    pass


@dataclass(slots=True)
class QueueLease:
    ticket: int
    release_callback: Callable[[int], None]
    released: bool = False

    def release(self) -> None:
        if self.released:
            return
        self.released = True
        self.release_callback(self.ticket)


class ConcurrentRequestQueue:
    def __init__(self, logger: Logger, wait_timeout: int, max_concurrency: int) -> None:
        self.logger = logger
        self.wait_timeout = wait_timeout
        self.max_concurrency = max(1, max_concurrency)
        self._condition = threading.Condition()
        self._next_ticket = 0
        self._serving_ticket = 0
        self._released_tickets: set[int] = set()

    def acquire(self, request_name: str) -> QueueLease:
        with self._condition:
            ticket = self._next_ticket
            self._next_ticket += 1
            queue_ahead = max(0, ticket - (self._serving_ticket + self.max_concurrency) + 1)
            start = time.monotonic()

            if queue_ahead > 0:
                self.logger.info("Request entered GLM queue ticket=%s ahead=%s request=%s", ticket, queue_ahead, request_name)

            while ticket >= self._serving_ticket + self.max_concurrency:
                remaining = self.wait_timeout - (time.monotonic() - start)
                if remaining <= 0:
                    raise QueueTimeoutError(
                        f"GLM queue wait timed out, {ticket - (self._serving_ticket + self.max_concurrency) + 1} request(s) still ahead, please retry later."
                    )
                self._condition.wait(timeout=remaining)

            active_slots = ticket - self._serving_ticket + 1
            self.logger.info(
                "Request acquired GLM execution slot ticket=%s active=%s/%s request=%s",
                ticket,
                active_slots,
                self.max_concurrency,
                request_name,
            )
            return QueueLease(ticket=ticket, release_callback=self._release)

    def _release(self, ticket: int) -> None:
        with self._condition:
            self._released_tickets.add(ticket)
            while self._serving_ticket in self._released_tickets:
                self._released_tickets.remove(self._serving_ticket)
                self._serving_ticket += 1
            self.logger.info("Request released GLM execution slot ticket=%s", ticket)
            self._condition.notify_all()


class GLMWebClient:
    def __init__(self, config: AppConfig, logger: Logger) -> None:
        self.config = config
        self.logger = logger
        self.auth = GLMAccessTokenManager(config=config, logger=logger)
        self.request_queue = ConcurrentRequestQueue(
            logger=logger,
            wait_timeout=config.glm_queue_wait_timeout,
            max_concurrency=config.glm_max_concurrency,
        )

    def _resolve_tools(self, openai_payload: dict[str, object]) -> tuple[list[dict[str, object]] | None, set[str] | None]:
        raw_tools = list(openai_payload.get("tools", [])) if isinstance(openai_payload.get("tools"), list) else None # type: ignore
        blocked_tool_names = {
            name.strip()
            for name in self.config.blocked_tool_names
            if name.strip()
        } | BLOCKED_NATIVE_TOOL_NAMES
        filtered_tools = filter_tools(raw_tools, blocked_tool_names)
        if raw_tools and len(raw_tools) != len(filtered_tools or []):
            blocked_names: list[str] = []
            for tool in raw_tools:
                fn = tool.get("function", {})
                tool_name = str(fn.get("name", "")).strip()
                if tool_name in blocked_tool_names:
                    blocked_names.append(tool_name)
            if blocked_names:
                self.logger.info("Filtered unsupported tools: %s", ", ".join(blocked_names))
        return filtered_tools, {tool["function"]["name"] for tool in filtered_tools} if filtered_tools else None # type: ignore[index]

    def chat_completion(self, payload: dict[str, object]) -> tuple[dict[str, object], str | None]:
        filtered_tools, allowed_tool_names = self._resolve_tools(payload)
        max_stream_retries = self.config.glm_stream_error_max_retries
        lease = self.request_queue.acquire(f"chat:{payload.get('model', 'unknown')}")
        try:
            response, assistant_id = self._open_chat_stream(payload, preferred_account_index=self._get_preferred_account_index(lease.ticket), filtered_tools=filtered_tools)
        except Exception:
            lease.release()
            raise
        accumulator = GLMEventAccumulator(
            model=str(payload["model"]),
            allowed_tool_names=allowed_tool_names,
            fallback_tool_url=extract_recent_user_url(list(payload.get("messages", []))), # type: ignore[arg-type]
            debug_enabled=self.config.debug_dump_all,
            logger=self.logger,
        )
        try:
            attempt = 0
            while True:
                retry_exc: UpstreamAPIError | None = None
                for event in self._iter_sse_events(response):
                    if not event:
                        continue
                    status = event.get("status")
                    try:
                        self._raise_for_event_error(event, stream=False)
                    except UpstreamAPIError as exc:
                        if exc.transient and attempt < max_stream_retries:
                            retry_exc = exc
                            break
                        raise
                    accumulator.consume_event(event)
                    if status in {"finish", "intervene"}:
                        return accumulator.build_response(), accumulator.conversation_id
                if retry_exc is None:
                    break
                # Transient upstream error: retry the stream with a fresh
                # conversation before giving up.
                attempt += 1
                response.close() # type: ignore
                self.logger.warning(
                    "Transient GLM error in non-streaming chat, retrying attempt=%s/%s error=%s",
                    attempt,
                    max_stream_retries,
                    retry_exc,
                )
                time.sleep(self.config.glm_stream_error_retry_interval)
                accumulator = GLMEventAccumulator(
                    model=str(payload["model"]),
                    allowed_tool_names=allowed_tool_names,
                    fallback_tool_url=extract_recent_user_url(list(payload.get("messages", []))), # type: ignore[arg-type]
                    debug_enabled=self.config.debug_dump_all,
                    logger=self.logger,
                )
                response, assistant_id = self._open_chat_stream(payload, preferred_account_index=self._get_preferred_account_index(lease.ticket), filtered_tools=filtered_tools)
        finally:
            response.close() # type: ignore
            self.delete_conversation(accumulator.conversation_id, assistant_id=assistant_id)
            lease.release()
        return accumulator.build_response(), accumulator.conversation_id

    def generate_images(self, payload: dict[str, object]) -> dict[str, object]:
        lease = self.request_queue.acquire(f"image:{payload.get('model', self.config.glm_image_model_name)}")
        try:
            response, assistant_id = self._open_image_stream(payload, preferred_account_index=self._get_preferred_account_index(lease.ticket))
        except Exception:
            lease.release()
            raise

        accumulator = GLMEventAccumulator(
            model=str(payload.get("model", self.config.glm_image_model_name)),
            debug_enabled=self.config.debug_dump_all,
            logger=self.logger,
        )
        try:
            for event in self._iter_sse_events(response):
                if not event:
                    continue
                status = event.get("status")
                accumulator.consume_event(event)
                if status == "finish":
                    return self._build_images_response(payload, event, accumulator)

            return self._build_images_response(payload, {}, accumulator)
        finally:
            response.close() # type: ignore
            self.delete_conversation(accumulator.conversation_id, assistant_id=assistant_id)
            lease.release()

    def stream_chat_completion(self, payload: dict[str, object]):
        filtered_tools, allowed_tool_names = self._resolve_tools(payload)
        max_stream_retries = self.config.glm_stream_error_max_retries

        def new_accumulator() -> GLMEventAccumulator:
            return GLMEventAccumulator(
                model=str(payload["model"]),
                allowed_tool_names=allowed_tool_names,
                fallback_tool_url=extract_recent_user_url(list(payload.get("messages", []))), # type: ignore[arg-type]
                debug_enabled=self.config.debug_dump_all,
                logger=self.logger,
            )

        lease = self.request_queue.acquire(f"stream:{payload.get('model', 'unknown')}")
        try:
            response, assistant_id = self._open_chat_stream(payload, preferred_account_index=self._get_preferred_account_index(lease.ticket), filtered_tools=filtered_tools)
        except Exception:
            lease.release()
            raise

        accumulator = new_accumulator()

        def generate():
            nonlocal response, assistant_id, accumulator
            attempt = 0
            while True:
                served_content = False
                retry_exc: UpstreamAPIError | None = None
                for event in self._iter_sse_events(response):
                    if not event:
                        continue
                    try:
                        self._raise_for_event_error(event, stream=True)
                    except UpstreamAPIError as exc:
                        if (
                            exc.transient
                            and not served_content
                            and attempt < max_stream_retries
                        ):
                            retry_exc = exc
                            break
                        raise
                    chunks, status = accumulator.consume_event(event)
                    for chunk in chunks:
                        encoded = chunk.encode("utf-8")
                        if b'"content"' in encoded and b'"reasoning_content"' not in encoded:
                            served_content = True
                        yield encoded

                    if status in {"finish", "intervene"}:
                        for chunk in accumulator.finalize(
                            status=status,
                            last_error=event.get("last_error") if isinstance(event.get("last_error"), dict) else None,
                        ):
                            yield chunk.encode("utf-8")
                        return
                if retry_exc is None:
                    for chunk in accumulator.finalize(status="stop"):
                        yield chunk.encode("utf-8")
                    return
                # Transient upstream error before any visible content: retry
                # the stream with a fresh conversation (guest tokens and
                # fresh sessions die quickly; reasoning replay is harmless).
                attempt += 1
                response.close() # type: ignore
                self.logger.warning(
                    "Transient GLM stream error before any visible content, retrying attempt=%s/%s error=%s",
                    attempt,
                    max_stream_retries,
                    retry_exc,
                )
                time.sleep(self.config.glm_stream_error_retry_interval)
                accumulator = new_accumulator()
                response, assistant_id = self._open_chat_stream(payload, preferred_account_index=self._get_preferred_account_index(lease.ticket), filtered_tools=filtered_tools)

        def wrapped():
            try:
                yield from generate()
            finally:
                try:
                    response.close() # type: ignore
                except Exception:
                    pass
                self.delete_conversation(accumulator.conversation_id, assistant_id=assistant_id)
                lease.release()

        return wrapped()

    # Error codes the upstream may emit mid-stream that are worth a retry
    # with the same or a rotated account instead of failing the whole request.
    TRANSIENT_UPSTREAM_ERROR_CODES = {10025, 10061, 10062}

    def _raise_for_event_error(self, event: dict[str, object], stream: bool) -> None:
        status = str(event.get("status", "")).strip().lower()
        last_error = event.get("last_error")
        event_error = self._extract_event_error(event)
        if status != "error" and not event_error and not isinstance(last_error, dict):
            return

        error_payload: dict[str, object] = {}
        if isinstance(last_error, dict):
            error_payload.update(last_error)
        if isinstance(event_error, dict):
            error_payload.update(event_error)
        if not error_payload and status != "error":
            return

        error_code = error_payload.get("error_code", error_payload.get("code"))
        error_message = str(
            error_payload.get("err_msg")
            or error_payload.get("message")
            or ("GLM stream request error" if stream else "GLM request error")
        ).strip()
        detail = f"code={error_code} " if error_code is not None else ""
        transient = False
        if error_code is not None:
            try:
                transient = int(error_code) in self.TRANSIENT_UPSTREAM_ERROR_CODES  # type: ignore[arg-type]
            except (TypeError, ValueError):
                transient = False
        raise UpstreamAPIError(
            status_code=502,
            message=f"GLM upstream returned an error | {detail}{error_message}".strip(),
            payload=error_payload or event,
            transient=transient,
        )

    def _extract_event_error(self, event: dict[str, object]) -> dict[str, object] | None:
        parts = event.get("parts")
        if not isinstance(parts, list):
            return None
        for part in parts:
            if not isinstance(part, dict):
                continue
            error = part.get("error")
            if isinstance(error, dict) and error:
                return error
            part_status = str(part.get("status", "")).strip().lower()
            if part_status == "error":
                # Der Upstream spiegelt unsere OpenAI-tool-Runde als native
                # 'tool'-Rolle zurueck (show_type mc_tool_result*), wenn das
                # Modell versucht, ein client-tool serverseitig auszufuehren.
                # Das ist kein fataler Fehler: wir ueberspringen solche Parts
                # und lassen das Modell weiter antworten.
                role = str(part.get("role", "")).strip().lower()
                meta = part.get("meta_data")
                show_type = ""
                if isinstance(meta, dict):
                    show_type = str(meta.get("show_type", ""))
                if role == "tool" or show_type.startswith("mc_tool_result"):
                    continue
                return {"message": "GLM part status error"}
        return None

    def delete_conversation(self, conversation_id: str, assistant_id: str | None = None) -> None:
        if not self.config.glm_delete_conversation:
            return
        if not conversation_id:
            self.logger.warning("Skipping GLM conversation deletion: no conversation_id obtained assistant_id=%s", assistant_id or self.config.glm_assistant_id)
            return

        actual_assistant_id = assistant_id or self.config.glm_assistant_id
        body = json.dumps(
            {
                "assistant_id": actual_assistant_id,
                "conversation_id": conversation_id,
            }
        ).encode("utf-8")
        try:
            def send_request(account_index: int, access_token: str):
                timestamp, nonce, sign = build_sign()
                request = urllib.request.Request(
                    self.config.delete_conversation_url,
                    method="POST",
                    data=body,
                    headers={
                        **self.auth.get_browser_headers(),
                        "Authorization": f"Bearer {access_token}",
                        "Referer": "https://chatglm.cn/main/alltoolsdetail",
                        "X-Device-Id": uuid.uuid4().hex,
                        "X-Nonce": nonce,
                        "X-Request-Id": uuid.uuid4().hex,
                        "X-Sign": sign,
                        "X-Timestamp": timestamp,
                    },
                )
                return urllib.request.urlopen(request, timeout=self.config.request_timeout)

            with self._call_with_account_failover("delete_conversation", send_request) as response: # type: ignore
                payload = self.auth.read_json_response(response)
            status = payload.get("status", payload.get("code"))
            if status not in {0, None}:
                self.logger.warning(
                    "GLM conversation deletion returned non-success status conversation_id=%s assistant_id=%s payload=%s",
                    conversation_id,
                    actual_assistant_id,
                    payload,
                )
                return
            self.logger.info(
                "Deleted GLM conversation conversation_id=%s assistant_id=%s",
                conversation_id,
                actual_assistant_id,
            )
        except Exception as exc:
            self.logger.warning(
                "Failed to delete GLM conversation conversation_id=%s assistant_id=%s error=%s",
                conversation_id,
                actual_assistant_id,
                exc,
            )

    def _open_chat_stream(self, openai_payload: dict[str, object], preferred_account_index: int | None = None, filtered_tools: list[dict[str, object]] | None = None):
        requested_model = str(openai_payload.get("model", "glm-4"))
        upstream_model, assistant_id = resolve_upstream_model(requested_model, self.config)
        if filtered_tools is None:
            filtered_tools, _ = self._resolve_tools(openai_payload)
        converted_messages = convert_messages(
            messages=list(openai_payload.get("messages", [])), # type: ignore
            tools=filtered_tools,
            blocked_tool_names={name.strip() for name in self.config.blocked_tool_names if name.strip()},
            tool_choice=openai_payload.get("tool_choice"),
            server_side_tool_names=SERVER_SIDE_TOOL_NAMES,
        )
        debug_dump(self.logger, self.config.debug_dump_all, "OpenAI raw chat request payload", openai_payload)
        debug_dump(self.logger, self.config.debug_dump_all, "Converted GLM messages", converted_messages)
        refs = self._upload_referenced_files(list(openai_payload.get("messages", []))) # type: ignore
        if refs:
            converted_messages[0]["content"] = refs + list(converted_messages[0]["content"]) # type: ignore
            debug_dump(self.logger, self.config.debug_dump_all, "GLM messages after appending upload references", converted_messages)

        chat_mode = resolve_chat_mode(
            model=requested_model,
            reasoning_effort=openai_payload.get("reasoning_effort"),
            deep_research=openai_payload.get("deep_research"),
        )
        is_networking = resolve_networking(
            model=requested_model,
            web_search=openai_payload.get("web_search"),
        )

        request_body = json.dumps(
            {
                "assistant_id": assistant_id,
                "conversation_id": "",
                "project_id": "",
                "chat_type": "user_chat",
                "messages": converted_messages,
                "meta_data": {
                    "channel": "",
                    "chat_mode": chat_mode,
                    "draft_id": "",
                    "if_plus_model": True,
                    "input_question_type": "xxxx",
                    "is_networking": is_networking,
                    "is_test": False,
                    "platform": "pc",
                    "quote_log_id": "",
                    "cogview": {"rm_label_watermark": False},
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

        self.logger.info(
            "Forwarding request model=%s upstream=%s stream=%s",
            requested_model,
            upstream_model,
            openai_payload.get("stream"),
        )
        debug_dump(self.logger, self.config.debug_dump_all, "Raw chat request body forwarded to GLM", request_body)

        def send_request(account_index: int, access_token: str):
            for attempt in range(self.config.glm_busy_max_retries + 1):
                try:
                    timestamp, nonce, sign = build_sign()
                    request = urllib.request.Request(
                        self.config.chat_stream_url,
                        data=request_body,
                        method="POST",
                        headers={
                            **self.auth.get_browser_headers(),
                            "Authorization": f"Bearer {access_token}",
                            "X-Device-Id": uuid.uuid4().hex,
                            "X-Nonce": nonce,
                            "X-Request-Id": uuid.uuid4().hex,
                            "X-Sign": sign,
                            "X-Timestamp": timestamp,
                        },
                    )
                    debug_dump(
                        self.logger,
                        self.config.debug_dump_all,
                        f"Chat request headers forwarded to GLM account={account_index} attempt={attempt + 1}",
                        dict(request.header_items()),
                    )
                    return self._prepare_chat_response(
                        urllib.request.urlopen(request, timeout=self.config.request_timeout)
                    )
                except urllib.error.HTTPError as exc:
                    error_payload = self._read_error_payload(exc)
                    if self._should_retry_busy_error(exc.code, error_payload) and attempt < self.config.glm_busy_max_retries:
                        wait_seconds = self.config.glm_busy_retry_interval
                        self.logger.warning(
                            "GLM is processing another conversation, waiting to retry attempt=%s/%s wait=%.1fs account=%s",
                            attempt + 1,
                            self.config.glm_busy_max_retries,
                            wait_seconds,
                            account_index,
                        )
                        time.sleep(wait_seconds)
                        continue

                    message = self._build_error_message(exc.code, error_payload)
                    raise UpstreamAPIError(status_code=exc.code, message=message, payload=error_payload) from exc

            raise UpstreamAPIError(status_code=429, message="GLM has been busy for a long time, please retry later.")

        response = self._call_with_account_failover(
            f"chat:{requested_model}",
            send_request,
            preferred_account_index=preferred_account_index,
        )
        return response, assistant_id

    def _open_image_stream(self, payload: dict[str, object], preferred_account_index: int | None = None):
        prompt = str(payload.get("prompt", "")).strip()
        if not prompt:
            raise UpstreamAPIError(status_code=400, message="Image generation request is missing prompt")

        size = str(payload.get("size", "1024x1024")).strip().lower()
        aspect_ratio = self._resolve_aspect_ratio(size)
        user_model = str(payload.get("model", self.config.glm_image_model_name)).strip() or self.config.glm_image_model_name
        request_body = json.dumps(
            {
                "assistant_id": self.config.glm_image_assistant_id,
                "conversation_id": "",
                "project_id": "",
                "chat_type": "user_chat",
                "meta_data": {
                    "cogview": {
                        "aspect_ratio": aspect_ratio,
                        "style": self._resolve_image_style(payload),
                        "scene": self._resolve_image_scene(payload),
                        "chat_model": "",
                        "rm_label_watermark": False,
                    },
                    "is_test": False,
                    "input_question_type": "xxxx",
                    "channel": "",
                    "draft_id": "",
                    "chat_mode": "",
                    "is_networking": False,
                    "quote_log_id": "",
                    "platform": "pc",
                },
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": prompt}],
                    }
                ],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

        self.logger.info(
            "Forwarding image request model=%s assistant_id=%s size=%s n=%s",
            user_model,
            self.config.glm_image_assistant_id,
            size,
            payload.get("n", 1),
        )
        debug_dump(self.logger, self.config.debug_dump_all, "OpenAI raw image request payload", payload)
        debug_dump(self.logger, self.config.debug_dump_all, "Raw image request body forwarded to GLM", request_body)

        def send_request(account_index: int, access_token: str):
            timestamp, nonce, sign = build_sign()
            request = urllib.request.Request(
                self.config.chat_stream_url,
                data=request_body,
                method="POST",
                headers={
                    **self.auth.get_browser_headers(),
                    "Authorization": f"Bearer {access_token}",
                    "X-Device-Id": uuid.uuid4().hex,
                    "X-Nonce": nonce,
                    "X-Request-Id": uuid.uuid4().hex,
                    "X-Sign": sign,
                    "X-Timestamp": timestamp,
                },
            )
            debug_dump(
                self.logger,
                self.config.debug_dump_all,
                f"Image request headers forwarded to GLM account={account_index}",
                dict(request.header_items()),
            )
            try:
                return self._prepare_chat_response(urllib.request.urlopen(request, timeout=self.config.request_timeout))
            except urllib.error.HTTPError as exc:
                error_payload = self._read_error_payload(exc)
                message = self._build_error_message(exc.code, error_payload)
                raise UpstreamAPIError(status_code=exc.code, message=message, payload=error_payload) from exc

        response = self._call_with_account_failover(
            f"image:{user_model}",
            send_request,
            preferred_account_index=preferred_account_index,
        )
        return response, self.config.glm_image_assistant_id

    def _prepare_chat_response(self, response):
        content_type = response.headers.get("Content-Type", "").lower()
        if "application/json" in content_type:
            payload = self.auth.read_json_response(response)
            debug_dump(self.logger, self.config.debug_dump_all, "GLM non-streaming raw JSON response", payload)
            status = payload.get("status")
            message = str(payload.get("message", "")).strip()
            if status not in (0, None) or message:
                raise UpstreamAPIError(
                    status_code=502,
                    message=self._build_error_message(200, payload),
                    payload=payload,
                )

            response_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            return BufferedReader(BytesIO(response_body))

        return self._wrap_stream_response(response)

    def _build_images_response(
        self,
        request_payload: dict[str, object],
        final_event: dict[str, object],
        accumulator: GLMEventAccumulator,
    ) -> dict[str, object]:
        requested_count = self._coerce_positive_int(request_payload.get("n"), default=1, maximum=10)
        response_format = str(request_payload.get("response_format", "url")).strip().lower()
        created = int(time.time())

        data: list[dict[str, object]] = []
        ordered_parts = list(accumulator.parts_by_logic_id.values())
        ordered_parts.sort(key=lambda item: str(item.get("logic_id", "")))

        for part in ordered_parts:
            if len(data) >= requested_count:
                break
            if not isinstance(part, dict):
                continue
            part_status = str(part.get("status", ""))
            if part_status != "finish":
                continue
            content_items = part.get("content", [])
            if not isinstance(content_items, list):
                continue
            for content in content_items:
                if len(data) >= requested_count:
                    break
                if not isinstance(content, dict) or content.get("type") != "image":
                    continue
                images = content.get("image", [])
                if not isinstance(images, list):
                    continue
                revised_prompt = str(content.get("code", "")).strip() or None
                for image in images:
                    if len(data) >= requested_count:
                        break
                    if not isinstance(image, dict):
                        continue
                    image_url = str(image.get("image_url", "")).strip()
                    if not image_url:
                        continue
                    item: dict[str, object] = {}
                    if response_format == "b64_json":
                        item["b64_json"] = self._download_image_as_base64(image_url)
                    else:
                        item["url"] = image_url
                    if revised_prompt:
                        item["revised_prompt"] = revised_prompt
                    data.append(item)

        if not data:
            raise UpstreamAPIError(
                status_code=502,
                message="GLM image request completed but returned no usable image results.",
                payload=final_event,
            )

        self.logger.info("Image generation completed image_count=%s", len(data))
        return {
            "created": created,
            "data": data,
        }

    def _resolve_aspect_ratio(self, size: str) -> str:
        normalized = size.strip().lower()
        if normalized in IMAGE_SIZE_TO_ASPECT_RATIO:
            return IMAGE_SIZE_TO_ASPECT_RATIO[normalized]
        if re.fullmatch(r"\d+x\d+", normalized):
            width_str, height_str = normalized.split("x", 1)
            width = max(int(width_str), 1)
            height = max(int(height_str), 1)
            return f"{width}:{height}"
        return "1:1"

    def _resolve_image_style(self, payload: dict[str, object]) -> str:
        style = str(payload.get("style", "none")).strip().lower()
        return style if style else "none"

    def _resolve_image_scene(self, payload: dict[str, object]) -> str:
        scene = str(payload.get("scene", "none")).strip().lower()
        return scene if scene else "none"

    def _coerce_positive_int(self, value: object, default: int, maximum: int) -> int:
        try:
            parsed = int(value) if value is not None else default # type: ignore
        except (TypeError, ValueError):
            parsed = default
        return max(1, min(parsed, maximum))

    def _download_image_as_base64(self, image_url: str) -> str:
        try:
            with urllib.request.urlopen(image_url, timeout=self.config.request_timeout) as response:
                image_bytes = response.read()
            return base64.b64encode(image_bytes).decode("ascii")
        except Exception as exc:
            raise UpstreamAPIError(status_code=502, message=f"Failed to download image: {image_url} error={exc}") from exc

    def _iter_sse_events(self, response):
        pending = ""
        decoder = codecs.getincrementaldecoder("utf-8")("ignore")

        def emit_block(block: str):
            lines = [line for line in block.split("\n") if line.startswith("data:")]
            if not lines:
                return None
            payload = "\n".join(line[5:].strip() for line in lines)
            debug_dump(self.logger, self.config.debug_dump_all, "GLM raw SSE block", block)
            if payload == "[DONE]":
                return "[DONE]"
            try:
                parsed = json.loads(payload)
                debug_dump(self.logger, self.config.debug_dump_all, "GLM parsed SSE payload", parsed)
                return parsed
            except json.JSONDecodeError:
                self.logger.debug("Ignoring unparseable SSE fragment: %s", payload)
                return None

        while True:
            stop_after_chunk = False
            try:
                raw_chunk = response.read(4096)
            except http.client.IncompleteRead as exc:
                raw_chunk = exc.partial or b""
                stop_after_chunk = True
                self.logger.warning("Upstream SSE connection closed early, finalizing with received data bytes=%s", len(raw_chunk))
            if not raw_chunk:
                break

            pending += decoder.decode(raw_chunk, False).replace("\r\n", "\n")

            while "\n\n" in pending:
                block, pending = pending.split("\n\n", 1)
                event = emit_block(block.strip())
                if event == "[DONE]":
                    return
                if event is not None:
                    yield event

            if stop_after_chunk:
                break

        remaining = decoder.decode(b"", True)
        if remaining:
            pending += remaining

        if pending.strip():
            event = emit_block(pending.strip())
            if event not in (None, "[DONE]"):
                yield event

    def _upload_referenced_files(self, messages: list[dict[str, object]]) -> list[dict[str, object]]:
        refs: list[dict[str, object]] = []
        for message in messages:
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for item in content:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("type")
                if item_type == "image_url":
                    url = item.get("image_url", {}).get("url")
                    if isinstance(url, str) and url:
                        ref = self._upload_file_reference(url, is_image=True)
                        if ref:
                            refs.append(ref)
                elif item_type == "file":
                    url = item.get("file_url", {}).get("url")
                    if isinstance(url, str) and url:
                        ref = self._upload_file_reference(url, is_image=False)
                        if ref:
                            refs.append(ref)
        if refs:
            self.logger.info("Attachment upload completed success_count=%s", len(refs))
        return refs

    def _upload_file_reference(self, file_url: str, is_image: bool) -> dict[str, object] | None:
        try:
            filename, mime_type, payload = self._fetch_file_payload(file_url)
            boundary = _make_boundary()
            body = self._build_multipart(boundary, filename, mime_type, payload)
            upload_url = f"{self.config.glm_base_url}{FILE_UPLOAD_URL_SUFFIX}"
            debug_dump(
                self.logger,
                self.config.debug_dump_all,
                f"Preparing attachment upload url={file_url} filename={filename} mime={mime_type}",
                {"filename": filename, "mime_type": mime_type, "bytes": len(payload)},
            )

            def send_request(account_index: int, access_token: str):
                timestamp, nonce, sign = build_sign()
                request = urllib.request.Request(
                    upload_url,
                    method="POST",
                    data=body,
                    headers={
                        **self.auth.get_browser_headers(),
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": f"multipart/form-data; boundary={boundary}",
                        "Referer": "https://chatglm.cn/",
                        "X-Device-Id": uuid.uuid4().hex,
                        "X-Nonce": nonce,
                        "X-Request-Id": uuid.uuid4().hex,
                        "X-Sign": sign,
                        "X-Timestamp": timestamp,
                    },
                )
                debug_dump(
                    self.logger,
                    self.config.debug_dump_all,
                    f"file_upload request headers forwarded to GLM account={account_index}",
                    dict(request.header_items()),
                )
                debug_dump(
                    self.logger,
                    self.config.debug_dump_all,
                    f"Raw file_upload request body forwarded to GLM account={account_index}",
                    body,
                )
                return urllib.request.urlopen(request, timeout=self.config.request_timeout)

            with self._call_with_account_failover("file_upload", send_request) as response: # type: ignore
                result = self.auth.read_json_response(response).get("result", {})
            debug_dump(self.logger, self.config.debug_dump_all, "GLM file upload response result", result)
            source_id = result.get("source_id") # type: ignore
            file_result_url = result.get("file_url", file_url) # type: ignore
            if not source_id:
                return None
            if is_image:
                return {"type": "image_url", "image_url": {"url": file_result_url or source_id}}
            return {"type": "file", "file": [{"source_id": source_id, "file_url": file_result_url}]}
        except Exception as exc:
            self.logger.warning("Attachment upload failed url=%s error=%s", file_url, exc)
            return None

    def _fetch_file_payload(self, file_url: str) -> tuple[str, str, bytes]:
        if file_url.startswith("data:"):
            header, encoded = file_url.split(",", 1)
            mime_type = header.split(";")[0][5:] or "application/octet-stream"
            extension = mimetypes.guess_extension(mime_type) or ".bin"
            payload = base64.b64decode(encoded)
            return f"upload-{uuid.uuid4().hex}{extension}", mime_type, payload

        parsed = urllib.parse.urlparse(file_url)
        filename = parsed.path.rsplit("/", 1)[-1] or f"upload-{uuid.uuid4().hex}.bin"
        with urllib.request.urlopen(file_url, timeout=self.config.request_timeout) as response:
            payload = response.read(FILE_SIZE_LIMIT + 1)
            if len(payload) > FILE_SIZE_LIMIT:
                raise ValueError("File exceeds 100MB, upload rejected.")
            mime_type = response.headers.get_content_type()
        mime_type = mime_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return filename, mime_type, payload

    def _build_multipart(self, boundary: str, filename: str, mime_type: str, payload: bytes) -> bytes:
        start = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode("utf-8")
        end = f"\r\n--{boundary}--\r\n".encode("utf-8")
        return start + payload + end

    def _wrap_stream_response(self, response):
        content_encoding = response.headers.get("Content-Encoding", "").lower()
        if content_encoding == "gzip":
            return BufferedReader(gzip.GzipFile(fileobj=response))
        return response

    def _read_error_payload(self, error: urllib.error.HTTPError) -> dict[str, object]:
        try:
            raw_body = error.read()
            content_encoding = error.headers.get("Content-Encoding", "").lower()

            if content_encoding == "gzip":
                raw_body = gzip.decompress(raw_body)

            text = raw_body.decode("utf-8", errors="ignore")
        except Exception as exc:
            return {"message": f"Failed to read upstream error response: {exc}"}
        try:
            payload = json.loads(text)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass
        return {"message": text}

    def _should_retry_busy_error(self, status_code: int, payload: dict[str, object]) -> bool:
        if status_code != 429:
            return False
        message = str(payload.get("message", ""))
        inner_status = payload.get("status")
        return inner_status == 10061 or "请等待其他对话生成完毕" in message

    def _build_error_message(self, status_code: int, payload: dict[str, object]) -> str:
        message = str(payload.get("message", "")).strip()
        inner_status = payload.get("status")
        rid = payload.get("rid")
        parts = [f"GLM request failed HTTP {status_code}"]
        if inner_status is not None:
            parts.append(f"status={inner_status}")
        if message:
            parts.append(message)
        if rid:
            parts.append(f"rid={rid}")
        return " | ".join(parts)

    def _get_preferred_account_index(self, ticket: int) -> int | None:
        account_count = self.auth.get_account_count()
        if account_count <= 0:
            return None
        return ticket % account_count

    def _call_with_account_failover(
        self,
        request_name: str,
        operation: Callable[[int, str], object],
        preferred_account_index: int | None = None,
    ):
        account_count = self.auth.get_account_count()
        if account_count <= 0:
            raise RuntimeError("No usable GLM account or guest token configured")
        start_index = preferred_account_index % account_count if preferred_account_index is not None else self.auth.get_current_account_index()
        last_exc: Exception | None = None

        for offset in range(account_count):
            account_index = (start_index + offset) % account_count
            guest_retry_limit = self.config.glm_guest_max_retries if self.auth.is_guest_account(account_index) else 0
            for attempt in range(guest_retry_limit + 1):
                try:
                    access_token = self.auth.get_access_token_for_account(account_index)
                    return operation(account_index, access_token)
                except Exception as exc:
                    last_exc = exc
                    should_switch = self.auth.should_switch_account(exc)
                    if should_switch:
                        self.auth.invalidate_account(account_index)
                    if should_switch and attempt < guest_retry_limit:
                        self.logger.warning(
                            "Guest account request failed, re-obtaining guest ck and retrying attempt=%s/%s request=%s account=%s error=%s",
                            attempt + 1,
                            guest_retry_limit,
                            request_name,
                            account_index,
                            exc,
                        )
                        continue
                    if not should_switch or account_count == 1:
                        raise
                    self.auth.advance_account(account_index, f"{request_name}: {exc}")
                    break

        self.auth.reset_account_cycle()
        if last_exc is not None:
            raise last_exc
        raise RuntimeError(f"Account rotation failed: {request_name}")
