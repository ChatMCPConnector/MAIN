"""Anthropic Messages API (/v1/messages) adapter.

Converts between Anthropic Messages format and the internal OpenAI
chat/completions format so the existing GLM pipeline can be reused.
"""

from __future__ import annotations

import json
import time
import uuid

from ..utils.tool_protocol import safe_json_dumps as _safe_json


def _openai_content_message(role: str, parts: list[dict[str, object]]) -> dict[str, object]:
    if len(parts) == 1 and parts[0].get("type") == "text":
        return {"role": role, "content": parts[0].get("text", "")}
    return {"role": role, "content": parts}


def _anthropic_thinking_part(block: dict[str, object]) -> dict[str, object]:
    block_type = block.get("type")
    if block_type == "redacted_thinking":
        data = block.get("data", "")
        if not isinstance(data, str) or not data:
            raise ValueError("Anthropic redacted_thinking block requires non-empty data")
        return {"type": "redacted_thinking", "data": data}

    thinking = block.get("thinking", "")
    signature = block.get("signature", "")
    if not isinstance(signature, str) or not signature.strip():
        raise ValueError("Anthropic thinking block requires a non-empty signature")
    return {"type": "thinking", "thinking": str(thinking), "signature": signature}


def _anthropic_image_part(source: object) -> dict[str, object] | None:
    if not isinstance(source, dict):
        return None
    source_type = source.get("type")
    if source_type == "base64" and source.get("data"):
        media_type = str(source.get("media_type", "image/png"))
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{media_type};base64,{source['data']}"},
        }
    if source_type == "url" and source.get("url"):
        return {"type": "image_url", "image_url": {"url": str(source["url"])}}
    return None


def _anthropic_result_content(value: object) -> object:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, list):
        parts: list[dict[str, object]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "text":
                parts.append({"type": "text", "text": str(item.get("text", ""))})
            elif item_type == "image":
                image = _anthropic_image_part(item.get("source"))
                if image:
                    parts.append(image)
            elif item_type in {"document", "file"}:
                source = item.get("source")
                if isinstance(source, dict) and source.get("type") == "base64" and source.get("data"):
                    media_type = str(source.get("media_type", "application/octet-stream"))
                    parts.append({
                        "type": "file",
                        "file_url": {"url": f"data:{media_type};base64,{source['data']}"},
                    })
                elif isinstance(source, dict) and source.get("url"):
                    parts.append({"type": "file", "file_url": {"url": str(source["url"])}})
        if len(parts) == 1 and parts[0].get("type") == "text":
            return parts[0].get("text", "")
        return parts
    if isinstance(value, dict):
        item_type = value.get("type")
        if item_type == "text":
            return str(value.get("text", ""))
        if item_type in {"image", "input_image"}:
            image = _anthropic_image_part(value.get("source") or value)
            if image is not None:
                return image
    return _safe_json(value)


def _append_anthropic_content_message(
    messages: list[dict[str, object]],
    role: str,
    content_parts: list[dict[str, object]],
    tool_calls: list[dict[str, object]],
) -> None:
    if not content_parts and not tool_calls:
        return
    content_snapshot = list(content_parts)
    tool_snapshot = list(tool_calls)
    if tool_snapshot:
        if not content_snapshot:
            assistant_content: object = None
        elif len(content_snapshot) == 1 and content_snapshot[0].get("type") == "text":
            assistant_content = content_snapshot[0].get("text", "")
        else:
            assistant_content = content_snapshot
        messages.append({
            "role": "assistant",
            "content": assistant_content,
            "tool_calls": tool_snapshot,
        })
    else:
        messages.append(_openai_content_message(role, content_snapshot))
    content_parts.clear()
    tool_calls.clear()


# ---------------------------------------------------------------------------
# Request conversion: Anthropic -> OpenAI chat/completions
# ---------------------------------------------------------------------------


def anthropic_to_openai(payload: dict[str, object]) -> dict[str, object]:
    """Convert an Anthropic Messages request body to OpenAI chat/completions."""
    messages: list[dict[str, object]] = []

    # --- system ---
    system = payload.get("system")
    if system:
        if isinstance(system, str):
            messages.append({"role": "system", "content": system})
        elif isinstance(system, list):
            text_parts = []
            for block in system:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(str(block.get("text", "")))
            if text_parts:
                messages.append({"role": "system", "content": "\n".join(text_parts)})

    # --- messages ---
    for msg in payload.get("messages", []):  # type: ignore[union-attr]
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role", "user"))
        content = msg.get("content")

        if isinstance(content, str):
            messages.append({"role": role, "content": content})
            continue

        if not isinstance(content, list):
            messages.append({"role": role, "content": ""})
            continue

        openai_content_parts: list[dict[str, object]] = []
        tool_calls: list[dict[str, object]] = []
        recognized_block = False

        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")

            if block_type == "text":
                recognized_block = True
                openai_content_parts.append({"type": "text", "text": block.get("text", "")})

            elif block_type in {"thinking", "redacted_thinking"}:
                recognized_block = True
                openai_content_parts.append(_anthropic_thinking_part(block))

            elif block_type == "image":
                image_part = _anthropic_image_part(block.get("source"))
                if image_part is not None:
                    recognized_block = True
                    openai_content_parts.append(image_part)

            elif block_type == "tool_use":
                recognized_block = True
                tool_calls.append({
                    "id": str(block.get("id", f"call_{uuid.uuid4().hex[:24]}")),
                    "type": "function",
                    "function": {
                        "name": str(block.get("name", "")),
                        "arguments": json.dumps(
                            block.get("input", {}), ensure_ascii=False, separators=(",", ":")
                        ),
                    },
                })

            elif block_type == "tool_result":
                recognized_block = True
                _append_anthropic_content_message(messages, role, openai_content_parts, tool_calls)
                tool_call_id = str(block.get("tool_use_id", "")).strip()
                if not tool_call_id:
                    raise ValueError("Anthropic tool_result requires a non-empty tool_use_id")
                tool_result: dict[str, object] = {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": _anthropic_result_content(block.get("content", "")),
                }
                if "is_error" in block:
                    tool_result["is_error"] = bool(block.get("is_error"))
                messages.append(tool_result)

        _append_anthropic_content_message(messages, role, openai_content_parts, tool_calls)
        if not recognized_block:
            messages.append({"role": role, "content": ""})

    # --- build output payload ---
    result: dict[str, object] = {
        "model": payload.get("model", "glm-4"),
        "messages": messages,
        "stream": payload.get("stream", False),
    }
    if payload.get("max_tokens"):
        result["max_tokens"] = payload["max_tokens"]
    if payload.get("temperature") is not None:
        result["temperature"] = payload["temperature"]
    if payload.get("top_p") is not None:
        result["top_p"] = payload["top_p"]
    if payload.get("stop_sequences"):
        result["stop"] = payload["stop_sequences"]

    # --- tools ---
    anthropic_tools = payload.get("tools")
    if isinstance(anthropic_tools, list) and anthropic_tools:
        openai_tools = []
        for tool in anthropic_tools:
            if not isinstance(tool, dict):
                continue
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {}),
                },
            })
        if openai_tools:
            result["tools"] = openai_tools
    tool_choice = payload.get("tool_choice")
    if tool_choice is not None:
        if isinstance(tool_choice, str):
            choice_type = tool_choice.strip().lower()
            if choice_type not in {"auto", "any", "none", "required"}:
                raise ValueError(f"Unsupported Anthropic tool_choice: {tool_choice!r}")
            if choice_type == "any":
                result["tool_choice"] = "required"
            else:
                result["tool_choice"] = choice_type
            tool_choice_data: dict[str, object] = {}
        elif isinstance(tool_choice, dict):
            tool_choice_data = tool_choice
            choice_type = str(tool_choice.get("type", "")).strip().lower()
            if choice_type == "auto":
                result["tool_choice"] = "auto"
            elif choice_type == "any":
                result["tool_choice"] = "required"
            elif choice_type == "none":
                result["tool_choice"] = "none"
            elif choice_type in {"required", "tool"}:
                if choice_type == "required":
                    result["tool_choice"] = "required"
                else:
                    name = str(tool_choice.get("name", "")).strip()
                    if not name:
                        raise ValueError("Anthropic tool_choice.tool requires a non-empty name")
                    result["tool_choice"] = {"type": "function", "function": {"name": name}}
            else:
                raise ValueError(f"Unsupported Anthropic tool_choice: {tool_choice!r}")
        else:
            raise ValueError("Anthropic tool_choice must be a string or object")

        disable_parallel = tool_choice_data.get("disable_parallel_tool_use")
        if disable_parallel is None and "disable_parallel_tool_use" in payload:
            disable_parallel = payload.get("disable_parallel_tool_use")
        if disable_parallel is not None:
            if not isinstance(disable_parallel, bool):
                raise ValueError("disable_parallel_tool_use must be boolean")
            result["parallel_tool_calls"] = not disable_parallel

    # --- thinking ---
    thinking = payload.get("thinking")
    if isinstance(thinking, dict) and thinking.get("type") == "enabled":
        # budget_tokens ist ein INT — keine Stufen-Angabe. Auf "medium"
        # normalisieren (denken aktiviert), statt die Zahl durchzureichen.
        result["reasoning_effort"] = "medium"

    return result


def _parse_openai_tool_call(tool_call: object, index: int) -> dict[str, object]:
    if not isinstance(tool_call, dict):
        raise ValueError(f"OpenAI tool call {index} must be an object")
    tool_id = tool_call.get("id")
    if not isinstance(tool_id, str) or not tool_id.strip():
        raise ValueError(f"OpenAI tool call {index} requires a non-empty id")
    if tool_call.get("type", "function") != "function":
        raise ValueError(f"OpenAI tool call {index} has an unsupported type")
    function = tool_call.get("function")
    if not isinstance(function, dict):
        raise ValueError(f"OpenAI tool call {index} requires a function object")
    name = function.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"OpenAI tool call {index} requires a non-empty function name")
    arguments = function.get("arguments")
    if isinstance(arguments, str):
        if not arguments.strip():
            raise ValueError(f"OpenAI tool call {index} has empty arguments")
        try:
            parsed_arguments = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise ValueError(f"OpenAI tool call {index} has invalid JSON arguments") from exc
    elif isinstance(arguments, dict):
        parsed_arguments = arguments
    else:
        raise ValueError(f"OpenAI tool call {index} arguments must be a JSON object")
    if not isinstance(parsed_arguments, dict):
        raise ValueError(f"OpenAI tool call {index} arguments must decode to an object")
    return {
        "id": tool_id,
        "name": name,
        "arguments": parsed_arguments,
    }


def _reasoning_to_anthropic_block(message: dict[str, object], reasoning: object) -> dict[str, object]:
    signature = ""
    for key in ("reasoning_signature", "thinking_signature", "signature"):
        candidate = message.get(key)
        if isinstance(candidate, str) and candidate.strip():
            signature = candidate
            break
    if signature:
        return {"type": "thinking", "thinking": str(reasoning), "signature": signature}
    return {"type": "redacted_thinking", "data": str(reasoning)}


# ---------------------------------------------------------------------------
# Non-streaming response conversion: OpenAI -> Anthropic
# ---------------------------------------------------------------------------


def openai_to_anthropic_response(result: dict[str, object], model: str) -> dict[str, object]:
    """Convert an OpenAI chat/completions response to Anthropic Messages format."""
    content: list[dict[str, object]] = []
    stop_reason = "end_turn"

    choices = result.get("choices", [])
    if isinstance(choices, list) and choices:
        choice = choices[0]
        if isinstance(choice, dict):
            message = choice.get("message", {})
            if isinstance(message, dict):
                reasoning = message.get("reasoning_content")
                if reasoning:
                    content.append(_reasoning_to_anthropic_block(message, reasoning))

                text = message.get("content")
                if text:
                    content.append({"type": "text", "text": str(text)})

                tool_calls = message.get("tool_calls")
                if tool_calls is not None:
                    if not isinstance(tool_calls, list):
                        raise ValueError("OpenAI message tool_calls must be a list")
                    valid_calls = [
                        _parse_openai_tool_call(tool_call, index)
                        for index, tool_call in enumerate(tool_calls)
                    ]
                    if valid_calls:
                        stop_reason = "tool_use"
                        for tool_call in valid_calls:
                            content.append({
                                "type": "tool_use",
                                "id": tool_call["id"],
                                "name": tool_call["name"],
                                "input": tool_call["arguments"],
                            })

            finish_reason = choice.get("finish_reason")
            if finish_reason == "length":
                stop_reason = "max_tokens"
            elif finish_reason == "tool_calls" and stop_reason != "tool_use":
                raise ValueError("OpenAI finish_reason=tool_calls contains no valid tool call")

    if not content:
        content.append({"type": "text", "text": ""})

    usage = result.get("usage", {})
    input_tokens = usage.get("prompt_tokens", 0) if isinstance(usage, dict) else 0
    output_tokens = usage.get("completion_tokens", 0) if isinstance(usage, dict) else 0

    return {
        "id": f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message",
        "role": "assistant",
        "content": content,
        "model": model,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        },
    }


# ---------------------------------------------------------------------------
# Streaming: OpenAI SSE -> Anthropic SSE
# ---------------------------------------------------------------------------


class AnthropicStreamAccumulator:
    """Converts OpenAI chat/completions streaming chunks into Anthropic SSE events."""

    def __init__(self, model: str) -> None:
        self.model = model
        self.message_id = f"msg_{uuid.uuid4().hex[:24]}"
        self.created = int(time.time())
        self.started = False
        self.content_index = 0
        self.current_block_type: str | None = None
        self.input_tokens = 0
        self.output_tokens = 0
        self.stop_reason = "end_turn"
        self._pending_tool_calls: dict[object, dict[str, object]] = {}
        self._tool_content_indices: dict[object, int] = {}
        self._pending_reasoning = ""
        self._reasoning_signature = ""
        self._finish_reason: str | None = None
        self._block_open = False
        self._finished = False
        self._pending_sse = ""

    def start_message(self) -> str:
        """Emit message_start event."""
        self.started = True
        msg = {
            "id": self.message_id,
            "type": "message",
            "role": "assistant",
            "content": [],
            "model": self.model,
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": self.input_tokens, "output_tokens": 0},
        }
        return self._sse("message_start", {"type": "message_start", "message": msg})

    def feed_chunk(self, chunk: bytes) -> list[str]:
        """Process a raw SSE chunk line (already decoded). Returns Anthropic SSE events.

        Ueber Chunks gesplittete data-Bloecke werden gepuffert (analog
        ResponsesStreamAccumulator) — ein Fragment bleibt in _pending_sse
        liegen, bis der Rest des Blocks nachkommt."""
        text = self._pending_sse + chunk.decode("utf-8", errors="ignore")
        self._pending_sse = ""
        events: list[str] = []
        blocks = text.split("\n\n")
        if not text.endswith("\n\n"):
            self._pending_sse = blocks.pop()
        for line in blocks:
            line = line.strip()
            if not line:
                continue
            if line == "data: [DONE]":
                events.extend(self._finish())
                continue
            if line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                events.extend(self._process_openai_chunk(data))
        return events

    def _process_openai_chunk(self, data: dict[str, object]) -> list[str]:
        events: list[str] = []
        if not self.started:
            events.append(self.start_message())

        choices = data.get("choices", [])
        if not isinstance(choices, list) or not choices:
            # Usage update
            usage = data.get("usage")
            if isinstance(usage, dict):
                self.input_tokens = usage.get("prompt_tokens", self.input_tokens)  # type: ignore
                self.output_tokens = usage.get("completion_tokens", self.output_tokens)  # type: ignore
            return events

        choice = choices[0]
        if not isinstance(choice, dict):
            return events
        delta = choice.get("delta", {})
        if not isinstance(delta, dict):
            return events
        finish_reason = choice.get("finish_reason")

        reasoning = delta.get("reasoning_content")
        if reasoning:
            self._pending_reasoning += str(reasoning)
            for key in ("reasoning_signature", "thinking_signature", "signature"):
                candidate = delta.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    self._reasoning_signature = candidate
                    break

        content = delta.get("content")
        if content:
            if self._pending_reasoning:
                if self._block_open:
                    events.append(self._content_block_stop())
                events.extend(self._flush_reasoning())
            if self.current_block_type != "text":
                if self._block_open:
                    events.append(self._content_block_stop())
                events.append(self._content_block_start("text", {"text": ""}))
                self.current_block_type = "text"
            events.append(self._sse("content_block_delta", {
                "type": "content_block_delta",
                "index": self.content_index,
                "delta": {"type": "text_delta", "text": str(content)},
            }))

        tool_calls = delta.get("tool_calls")
        if tool_calls is not None:
            if not isinstance(tool_calls, list):
                raise ValueError("OpenAI streaming tool_calls must be a list")
            for tc in tool_calls:
                if not isinstance(tc, dict):
                    raise ValueError("OpenAI streaming tool call must be an object")
                if tc.get("type", "function") != "function":
                    raise ValueError("OpenAI streaming tool call has an unsupported type")
                tc_index = tc.get("index", 0)
                try:
                    hash(tc_index)
                except TypeError as exc:
                    raise ValueError("OpenAI streaming tool call index must be hashable") from exc
                fn = tc.get("function")
                if not isinstance(fn, dict):
                    raise ValueError("OpenAI streaming tool call requires a function object")
                if tc_index not in self._pending_tool_calls:
                    self._pending_tool_calls[tc_index] = {
                        "id": "",
                        "name": "",
                        "arguments": "",
                        "content_index": None,
                    }
                state = self._pending_tool_calls[tc_index]
                if tc.get("id") is not None:
                    if not isinstance(tc.get("id"), str):
                        raise ValueError("OpenAI streaming tool call id must be a string")
                    state["id"] = tc["id"]
                if fn.get("name") is not None:
                    if not isinstance(fn.get("name"), str):
                        raise ValueError("OpenAI streaming tool call name must be a string")
                    state["name"] = fn["name"]
                args_delta = fn.get("arguments")
                if args_delta is not None:
                    if not isinstance(args_delta, str):
                        raise ValueError("OpenAI streaming tool arguments must be strings")
                    state["arguments"] = str(state["arguments"]) + args_delta
                self.stop_reason = "tool_use"

        if finish_reason:
            self._finish_reason = str(finish_reason)
            if self._finish_reason == "length":
                self.stop_reason = "max_tokens"
            elif self._finish_reason == "tool_calls":
                self.stop_reason = "tool_use"

        # Usage in final chunk
        usage = data.get("usage")
        if isinstance(usage, dict):
            self.input_tokens = usage.get("prompt_tokens", self.input_tokens)  # type: ignore
            self.output_tokens = usage.get("completion_tokens", self.output_tokens)  # type: ignore

        if finish_reason:
            events.extend(self._finish())
        return events

    def _flush_reasoning(self) -> list[str]:
        if not self._pending_reasoning:
            return []
        events: list[str] = []
        if self._reasoning_signature:
            events.append(self._content_block_start("thinking", {
                "thinking": "",
                "signature": self._reasoning_signature,
            }))
            events.append(self._sse("content_block_delta", {
                "type": "content_block_delta",
                "index": self.content_index,
                "delta": {"type": "thinking_delta", "thinking": self._pending_reasoning},
            }))
            self.current_block_type = "thinking"
        else:
            events.append(self._content_block_start("redacted_thinking", {
                "data": self._pending_reasoning,
            }))
            self.current_block_type = "redacted_thinking"
        events.append(self._content_block_stop())
        self._pending_reasoning = ""
        self._reasoning_signature = ""
        return events

    def _flush_tool_calls(self) -> list[str]:
        events: list[str] = []
        ordered = sorted(
            self._pending_tool_calls.items(),
            key=lambda item: (
                (0, item[0]) if isinstance(item[0], int) else (1, str(item[0]))
            ),
        )
        for tool_index, state in ordered:
            tool_id = state.get("id", "")
            tool_name = state.get("name", "")
            arguments = state.get("arguments", "")
            if not isinstance(tool_id, str) or not tool_id.strip():
                raise ValueError(f"OpenAI streaming tool call {tool_index} requires a non-empty id")
            if not isinstance(tool_name, str) or not tool_name.strip():
                raise ValueError(f"OpenAI streaming tool call {tool_index} requires a non-empty name")
            if not isinstance(arguments, str) or not arguments.strip():
                raise ValueError(f"OpenAI streaming tool call {tool_index} has empty arguments")
            try:
                parsed_arguments = json.loads(arguments)
            except json.JSONDecodeError as exc:
                raise ValueError(f"OpenAI streaming tool call {tool_index} has invalid JSON arguments") from exc
            if not isinstance(parsed_arguments, dict):
                raise ValueError(f"OpenAI streaming tool call {tool_index} arguments must decode to an object")
            content_index = self.content_index
            state["content_index"] = content_index
            self._tool_content_indices[tool_index] = content_index
            events.append(self._content_block_start("tool_use", {
                "id": tool_id,
                "name": tool_name,
                "input": {},
            }))
            events.append(self._sse("content_block_delta", {
                "type": "content_block_delta",
                "index": content_index,
                "delta": {"type": "input_json_delta", "partial_json": arguments},
            }))
            events.append(self._content_block_stop())
        self._pending_tool_calls.clear()
        return events

    def _finish(self) -> list[str]:
        if self._finished:
            return []
        self._finished = True
        events: list[str] = []
        if self._block_open:
            events.append(self._content_block_stop())
        if self._pending_reasoning:
            events.extend(self._flush_reasoning())
        if self._pending_tool_calls:
            if self._finish_reason != "length":
                events.extend(self._flush_tool_calls())
            else:
                self._pending_tool_calls.clear()
        elif self._finish_reason == "tool_calls":
            raise ValueError("OpenAI finish_reason=tool_calls contains no valid tool call")
        events.append(self._sse("message_delta", {
            "type": "message_delta",
            "delta": {"stop_reason": self.stop_reason, "stop_sequence": None},
            "usage": {"output_tokens": self.output_tokens},
        }))
        events.append(self._sse("message_stop", {"type": "message_stop"}))
        return events

    def finish(self) -> list[str]:
        """Public: terminale events (idempotent) — server ruft das nach dem stream."""
        return self._finish()

    def error_event(self, message: str, error_type: str = "api_error") -> str:
        """Anthropic SSE error event (spezifikationskonform) fuer mid-stream fehler."""
        self._finished = True  # kein message_stop mehr nach einem error
        return self._sse("error", {
            "type": "error",
            "error": {"type": error_type, "message": message},
        })

    @staticmethod
    def ping_event() -> str:
        """Heartbeat: ping event, damit clients/proxies bei langem thinking nicht timeouten."""
        return 'event: ping\ndata: {"type": "ping"}\n\n'

    def _content_block_start(self, block_type: str, initial: dict[str, object]) -> str:
        block: dict[str, object] = {"type": block_type}
        block.update(initial)
        self._block_open = True
        event = self._sse("content_block_start", {
            "type": "content_block_start",
            "index": self.content_index,
            "content_block": block,
        })
        return event

    def _content_block_stop(self) -> str:
        event = self._sse("content_block_stop", {
            "type": "content_block_stop",
            "index": self.content_index,
        })
        self.content_index += 1
        self._block_open = False
        return event

    def _sse(self, event_type: str, data: dict[str, object]) -> str:
        return f"event: {event_type}\ndata: {_safe_json(data)}\n\n"
