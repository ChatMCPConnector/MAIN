"""OpenAI Responses API (/v1/responses) adapter.

Converts between the OpenAI Responses format and the internal OpenAI
chat/completions format so the existing GLM pipeline can be reused.
"""

from __future__ import annotations

import json
import time
import uuid
from contextvars import ContextVar

from ..utils.tool_protocol import safe_json_dumps as _safe_json


_response_request_metadata: ContextVar[dict[str, object] | None] = ContextVar(
    "glm2api_responses_request_metadata",
    default=None,
)


def _response_part_to_openai(part: dict[str, object]) -> dict[str, object] | None:
    part_type = part.get("type")
    if part_type in {"input_text", "output_text", "text"}:
        return {"type": "text", "text": part.get("text", "")}
    if part_type in {"input_image", "image_url"}:
        image_url = part.get("image_url") or part.get("url")
        if isinstance(image_url, dict):
            image_url = image_url.get("url")
        if not image_url:
            return None
        converted: dict[str, object] = {"type": "image_url", "image_url": {"url": str(image_url)}}
        detail = part.get("detail")
        if detail:
            converted["image_url"]["detail"] = detail  # type: ignore[index]
        return converted
    if part_type in {"input_file", "file"}:
        file_url = part.get("file_url")
        if isinstance(file_url, dict):
            file_url = file_url.get("url")
        if not file_url:
            return None
        return {"type": "file", "file_url": {"url": str(file_url)}}
    return None


def _response_content_to_openai(content: object) -> object | None:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None

    openai_parts: list[dict[str, object]] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        converted = _response_part_to_openai(part)
        if converted:
            openai_parts.append(converted)
    if len(openai_parts) == 1 and openai_parts[0].get("type") == "text":
        return openai_parts[0].get("text", "")
    if openai_parts:
        return openai_parts
    return None


def _append_response_message(messages: list[dict[str, object]], item: dict[str, object]) -> None:
    role = str(item.get("role", "user"))
    converted_content = _response_content_to_openai(item.get("content"))
    if converted_content is not None:
        messages.append({"role": role, "content": converted_content})


def _response_output_to_openai(output: object) -> object:
    if isinstance(output, str):
        return output
    if output is None:
        return ""
    if isinstance(output, list):
        if all(
            isinstance(part, dict)
            and part.get("type") in {"input_text", "output_text", "text", "input_image", "image_url", "input_file", "file"}
            for part in output
        ):
            converted = _response_content_to_openai(output)
            if converted is not None:
                return converted
        return _safe_json(output)
    if isinstance(output, dict):
        converted = _response_part_to_openai(output)
        if converted is not None:
            return converted
        return _safe_json(output)
    return _safe_json(output)


def _normalize_responses_tool_choice(value: object) -> object:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"auto", "none", "required", "any"}:
            return "required" if normalized == "any" else normalized
        raise ValueError(f"Unsupported Responses tool_choice: {value!r}")
    if not isinstance(value, dict):
        raise ValueError("Responses tool_choice must be a string or object")

    choice_type = str(value.get("type", "")).strip().lower()
    if choice_type in {"auto", "none", "required"}:
        return choice_type
    if choice_type != "function":
        raise ValueError(f"Unsupported Responses tool_choice: {value!r}")
    name = value.get("name")
    if not name:
        function = value.get("function")
        if isinstance(function, dict):
            name = function.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Responses function tool_choice requires a non-empty name")
    return {"type": "function", "function": {"name": name.strip()}}


def _allowed_responses_tool_names(value: dict[str, object]) -> tuple[set[str], str]:
    mode = str(value.get("mode", "auto")).strip().lower()
    if mode not in {"auto", "required"}:
        raise ValueError("Responses allowed_tools.mode must be auto or required")
    tools = value.get("tools")
    if not isinstance(tools, list) or not tools:
        raise ValueError("Responses allowed_tools requires a non-empty tools list")
    names: set[str] = set()
    for tool in tools:
        if not isinstance(tool, dict) or str(tool.get("type", "")).strip().lower() != "function":
            raise ValueError("Responses allowed_tools currently supports function tools only")
        name = str(tool.get("name", "")).strip()
        if not name:
            raise ValueError("Responses allowed_tools function requires a non-empty name")
        names.add(name)
    return names, mode


def _parse_openai_tool_call(tool_call: object, index: int) -> dict[str, object]:
    if not isinstance(tool_call, dict):
        raise ValueError(f"OpenAI tool call {index} must be an object")
    if tool_call.get("type", "function") != "function":
        raise ValueError(f"OpenAI tool call {index} has an unsupported type")
    function = tool_call.get("function")
    if not isinstance(function, dict):
        raise ValueError(f"OpenAI tool call {index} requires a function object")
    tool_id = tool_call.get("id")
    name = function.get("name")
    if not isinstance(tool_id, str) or not tool_id.strip():
        raise ValueError(f"OpenAI tool call {index} requires a non-empty id")
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
    return {"id": tool_id, "name": name, "arguments": parsed_arguments}


# ---------------------------------------------------------------------------
# Request conversion: Responses -> OpenAI chat/completions
# ---------------------------------------------------------------------------


def responses_to_openai(payload: dict[str, object]) -> dict[str, object]:
    """Convert an OpenAI Responses API request body to chat/completions format."""
    _response_request_metadata.set(None)
    messages: list[dict[str, object]] = []

    previous_response_id = payload.get("previous_response_id")
    if previous_response_id is not None and not isinstance(previous_response_id, str):
        raise ValueError("previous_response_id must be a string or null")

    instructions = payload.get("instructions")
    if instructions and isinstance(instructions, str):
        messages.append({"role": "system", "content": instructions})

    input_data = payload.get("input")
    if isinstance(input_data, str):
        messages.append({"role": "user", "content": input_data})
    elif isinstance(input_data, list):
        call_names: dict[str, str] = {}
        for item in input_data:
            if not isinstance(item, dict) or item.get("type") != "function_call":
                continue
            call_id = str(item.get("call_id", "")).strip()
            name = str(item.get("name", "")).strip()
            if call_id and name:
                call_names[call_id] = name

        for item in input_data:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")

            if item_type == "message" or (item_type is None and "content" in item):
                _append_response_message(messages, item)

            elif item_type == "function_call_output":
                call_id = str(item.get("call_id", "")).strip()
                if not call_id:
                    raise ValueError("Responses function_call_output requires a non-empty call_id")
                output_content = _response_output_to_openai(item.get("output", ""))
                tool_name = call_names.get(call_id, "")
                if tool_name:
                    msg: dict[str, object] = {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": tool_name,
                        "content": output_content,
                    }
                    messages.append(msg)
                else:
                    marker = f"[tool result continuation for call_id {call_id}"
                    if previous_response_id:
                        marker += f" and previous_response_id {previous_response_id}"
                    marker += "]"
                    if isinstance(output_content, list):
                        continuation_content: object = [
                            {"type": "text", "text": marker},
                            *output_content,
                        ]
                    elif isinstance(output_content, str):
                        continuation_content = f"{marker}\n{output_content}" if output_content else marker
                    else:
                        continuation_content = f"{marker}\n{_safe_json(output_content)}"
                    messages.append({"role": "user", "content": continuation_content})

            elif item_type == "function_call":
                call_id = str(item.get("call_id", "")).strip()
                name = str(item.get("name", "")).strip()
                if not call_id:
                    raise ValueError("Responses function_call requires a non-empty call_id")
                if not name:
                    raise ValueError("Responses function_call requires a non-empty name")
                arguments = item.get("arguments", {})
                if isinstance(arguments, str):
                    args = arguments
                else:
                    try:
                        args = _safe_json(arguments)
                    except (TypeError, ValueError) as exc:
                        raise ValueError("Responses function_call arguments are not JSON serializable") from exc
                tc_entry = {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": args},
                }
                call_names[call_id] = name
                if messages and messages[-1].get("role") == "assistant" and isinstance(messages[-1].get("tool_calls"), list):
                    messages[-1]["tool_calls"].append(tc_entry)  # type: ignore[union-attr]
                else:
                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [tc_entry],
                    })

    result: dict[str, object] = {
        "model": payload.get("model", "glm-4"),
        "messages": messages,
        "stream": payload.get("stream", False),
    }
    if previous_response_id is not None:
        result["previous_response_id"] = previous_response_id
    if payload.get("max_output_tokens") is not None:
        result["max_tokens"] = payload["max_output_tokens"]
    if payload.get("temperature") is not None:
        result["temperature"] = payload["temperature"]
    if payload.get("top_p") is not None:
        result["top_p"] = payload["top_p"]

    parallel_tool_calls = payload.get("parallel_tool_calls")
    if parallel_tool_calls is not None:
        if not isinstance(parallel_tool_calls, bool):
            raise ValueError("parallel_tool_calls must be boolean")
        result["parallel_tool_calls"] = parallel_tool_calls

    raw_tool_choice = payload.get("tool_choice")
    allowed_tool_names: set[str] | None = None
    allowed_tool_mode = "auto"
    if isinstance(raw_tool_choice, dict) and str(raw_tool_choice.get("type", "")).strip().lower() == "allowed_tools":
        allowed_tool_names, allowed_tool_mode = _allowed_responses_tool_names(raw_tool_choice)

    resp_tools = payload.get("tools")
    if isinstance(resp_tools, list) and resp_tools:
        openai_tools: list[dict[str, object]] = []
        for tool in resp_tools:
            if not isinstance(tool, dict):
                raise ValueError("Responses tools must contain objects")
            tool_type = str(tool.get("type", "")).strip().lower()
            if tool_type != "function":
                raise ValueError(f"Unsupported Responses tool type: {tool_type or '(missing)'}")
            name = str(tool.get("name", "")).strip()
            if not name:
                raise ValueError("Responses function tool requires a non-empty name")
            if allowed_tool_names is not None and name not in allowed_tool_names:
                continue
            function_tool: dict[str, object] = {
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {}),
                },
            }
            if tool.get("strict") is not None:
                function_tool["function"]["strict"] = tool["strict"]  # type: ignore[index]
            openai_tools.append(function_tool)
        result["tools"] = openai_tools

    if raw_tool_choice is not None:
        if allowed_tool_names is not None:
            result["tool_choice"] = "required" if allowed_tool_mode == "required" else "auto"
        else:
            result["tool_choice"] = _normalize_responses_tool_choice(raw_tool_choice)

    reasoning = payload.get("reasoning")
    if isinstance(reasoning, dict):
        effort = reasoning.get("effort")
        if effort:
            result["reasoning_effort"] = effort

    _response_request_metadata.set({
        "parallel_tool_calls": result.get("parallel_tool_calls", True),
        "tool_choice": result.get("tool_choice", "auto"),
        "previous_response_id": previous_response_id,
    })
    return result


# ---------------------------------------------------------------------------
# Non-streaming response: OpenAI -> Responses
# ---------------------------------------------------------------------------


def openai_to_responses(
    result: dict[str, object],
    model: str,
    *,
    parallel_tool_calls: bool | None = None,
    tool_choice: object | None = None,
    previous_response_id: str | None = None,
) -> dict[str, object]:
    """Convert an OpenAI chat/completions response to Responses API format."""
    metadata = _response_request_metadata.get()
    if metadata:
        if parallel_tool_calls is None:
            candidate = metadata.get("parallel_tool_calls", True)
            parallel_tool_calls = candidate if isinstance(candidate, bool) else True
        if tool_choice is None:
            tool_choice = metadata.get("tool_choice", "auto")
        if previous_response_id is None:
            candidate = metadata.get("previous_response_id")
            if isinstance(candidate, str):
                previous_response_id = candidate
    _response_request_metadata.set(None)
    if parallel_tool_calls is None:
        parallel_tool_calls = True
    if tool_choice is None:
        tool_choice = "auto"
    response_id = f"resp_{uuid.uuid4().hex[:24]}"
    created = int(time.time())
    output: list[dict[str, object]] = []
    output_text_parts: list[str] = []
    status = "completed"
    incomplete_details: dict[str, object] | None = None
    valid_tool_calls = 0
    invalid_tool_calls = False
    finish_reason: object = None

    choices = result.get("choices", [])
    if isinstance(choices, list) and choices:
        choice = choices[0]
        if isinstance(choice, dict):
            message = choice.get("message", {})
            if isinstance(message, dict):
                msg_content: list[dict[str, object]] = []
                text = message.get("content")
                if text:
                    output_text_parts.append(str(text))
                    msg_content.append({
                        "type": "output_text",
                        "text": str(text),
                        "annotations": [],
                    })

                if msg_content:
                    output.append({
                        "type": "message",
                        "id": f"msg_{uuid.uuid4().hex[:24]}",
                        "status": "completed",
                        "role": "assistant",
                        "content": msg_content,
                    })

                tool_calls = message.get("tool_calls")
                if tool_calls is not None:
                    if not isinstance(tool_calls, list):
                        invalid_tool_calls = True
                    else:
                        for index, tool_call in enumerate(tool_calls):
                            try:
                                parsed = _parse_openai_tool_call(tool_call, index)
                            except ValueError:
                                invalid_tool_calls = True
                                continue
                            valid_tool_calls += 1
                            output.append({
                                "type": "function_call",
                                "id": f"fc_{uuid.uuid4().hex[:24]}",
                                "call_id": parsed["id"],
                                "name": parsed["name"],
                                "arguments": _safe_json(parsed["arguments"]),
                                "status": "completed",
                            })

            finish_reason = choice.get("finish_reason")

    normalized_finish = str(finish_reason).strip().lower() if finish_reason is not None else ""
    if normalized_finish == "length":
        status = "incomplete"
        incomplete_details = {"reason": "max_output_tokens"}
    elif normalized_finish == "content_filter":
        status = "incomplete"
        incomplete_details = {"reason": "content_filter"}
    elif normalized_finish == "tool_calls" and valid_tool_calls == 0:
        status = "incomplete"
        incomplete_details = {"reason": "incomplete_tool_call"}
    elif normalized_finish not in {"", "stop", "tool_calls"}:
        status = "incomplete"
        incomplete_details = {"reason": "incomplete_response"}
    if invalid_tool_calls:
        status = "incomplete"
        incomplete_details = {"reason": "incomplete_tool_call"}
    if status == "incomplete":
        for item in output:
            if item.get("type") == "message":
                item["status"] = "incomplete"
            elif item.get("type") == "function_call":
                item["status"] = "incomplete"

    usage = result.get("usage", {})
    input_tokens = usage.get("prompt_tokens", 0) if isinstance(usage, dict) else 0
    output_tokens = usage.get("completion_tokens", 0) if isinstance(usage, dict) else 0

    return {
        "id": response_id,
        "object": "response",
        "created_at": created,
        "status": status,
        "error": None,
        "incomplete_details": incomplete_details,
        "instructions": None,
        "model": model,
        "output": output,
        "output_text": "".join(output_text_parts),
        "parallel_tool_calls": parallel_tool_calls,
        "previous_response_id": previous_response_id,
        "tool_choice": tool_choice,
        "store": False,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    }


# ---------------------------------------------------------------------------
# Streaming: OpenAI SSE -> Responses SSE
# ---------------------------------------------------------------------------


class ResponsesStreamAccumulator:
    """Converts OpenAI chat/completions streaming chunks into Responses SSE events."""

    def __init__(
        self,
        model: str,
        *,
        parallel_tool_calls: bool | None = None,
        tool_choice: object | None = None,
        previous_response_id: str | None = None,
    ) -> None:
        metadata = _response_request_metadata.get()
        if metadata:
            if parallel_tool_calls is None:
                candidate = metadata.get("parallel_tool_calls", True)
                parallel_tool_calls = candidate if isinstance(candidate, bool) else True
            if tool_choice is None:
                tool_choice = metadata.get("tool_choice", "auto")
            if previous_response_id is None:
                candidate = metadata.get("previous_response_id")
                if isinstance(candidate, str):
                    previous_response_id = candidate
        _response_request_metadata.set(None)
        if parallel_tool_calls is None:
            parallel_tool_calls = True
        if tool_choice is None:
            tool_choice = "auto"
        self.model = model
        self.parallel_tool_calls = parallel_tool_calls
        self.tool_choice = tool_choice
        self.previous_response_id = previous_response_id
        self.response_id = f"resp_{uuid.uuid4().hex[:24]}"
        self.created = int(time.time())
        self.started = False
        self.output_index = 0
        self.content_index = 0
        self.current_type: str | None = None
        self.input_tokens = 0
        self.output_tokens = 0
        self._text_buffer = ""
        self._full_text = ""
        self._message_text_parts: list[str] = []
        self._current_msg_id: str | None = None
        self._current_fc_id: str | None = None
        self._pending_tool_calls: dict[object, dict[str, object]] = {}
        self._message_started = False
        self._content_part_started = False
        self._completed_output_by_index: dict[int, dict[str, object]] = {}
        self._completed_output: list[dict[str, object]] = []
        self._finished = False
        self._finish_reason: str | None = None
        self._terminal_status: str | None = None
        self._incomplete_details: dict[str, object] | None = None
        self._invalid_tool_calls = False
        self.sequence_number = 0
        self._pending_sse = ""

    def _record_output(self, output_index: int, item: dict[str, object]) -> None:
        self._completed_output_by_index[output_index] = item
        self._completed_output = [
            self._completed_output_by_index[index]
            for index in sorted(self._completed_output_by_index)
        ]

    def _base_response(self, status: str = "in_progress") -> dict[str, object]:
        usage: dict[str, object] | None = None
        if status in {"completed", "incomplete", "failed"}:
            usage = {
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "output_tokens_details": {"reasoning_tokens": 0},
                "total_tokens": self.input_tokens + self.output_tokens,
            }
        return {
            "id": self.response_id,
            "object": "response",
            "created_at": self.created,
            "status": status,
            "completed_at": int(time.time()) if status == "completed" else None,
            "error": None,
            "incomplete_details": self._incomplete_details if status == "incomplete" else None,
            "instructions": None,
            "max_output_tokens": None,
            "model": self.model,
            "output": list(self._completed_output),
            "parallel_tool_calls": self.parallel_tool_calls,
            "previous_response_id": self.previous_response_id,
            "reasoning": {"effort": None, "summary": None},
            "store": False,
            "temperature": 1,
            "text": {"format": {"type": "text"}},
            "tool_choice": self.tool_choice,
            "tools": [],
            "top_p": 1,
            "truncation": "disabled",
            "usage": usage,
            "user": None,
            "metadata": {},
        }

    def start_response(self) -> list[str]:
        if self.started:
            return []
        self.started = True
        return [
            self._sse("response.created", self._base_response()),
            self._sse("response.in_progress", self._base_response()),
        ]

    def feed_chunk(self, chunk: bytes) -> list[str]:
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
                if isinstance(data, dict):
                    events.extend(self._process_openai_chunk(data))
        return events

    def _process_openai_chunk(self, data: dict[str, object]) -> list[str]:
        if self._finished:
            return []
        events: list[str] = []
        if not self.started:
            events.extend(self.start_response())

        choices = data.get("choices", [])
        if not isinstance(choices, list) or not choices:
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

        content = delta.get("content")
        text_delta = str(content) if content else ""
        if text_delta:
            if not self._message_started:
                events.extend(self._start_message_output())
            if not self._content_part_started:
                events.extend(self._start_content_part())
            events.append(self._sse("response.output_text.delta", {
                "type": "response.output_text.delta",
                "item_id": self._current_msg_id,
                "output_index": self.output_index,
                "content_index": self.content_index,
                "delta": text_delta,
            }))
            self._text_buffer += text_delta
            self._full_text += text_delta

        tool_calls = delta.get("tool_calls")
        if tool_calls is not None:
            if not isinstance(tool_calls, list):
                raise ValueError("OpenAI streaming tool_calls must be a list")
            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    raise ValueError("OpenAI streaming tool call must be an object")
                if tool_call.get("type", "function") != "function":
                    raise ValueError("OpenAI streaming tool call has an unsupported type")
                tool_index = tool_call.get("index", 0)
                try:
                    hash(tool_index)
                except TypeError as exc:
                    raise ValueError("OpenAI streaming tool call index must be hashable") from exc
                function = tool_call.get("function")
                if not isinstance(function, dict):
                    raise ValueError("OpenAI streaming tool call requires a function object")

                if tool_index not in self._pending_tool_calls:
                    if self._content_part_started:
                        events.extend(self._end_content_part())
                    if self._message_started:
                        events.extend(self._end_message_output())
                    fc_id = f"fc_{uuid.uuid4().hex[:24]}"
                    self._pending_tool_calls[tool_index] = {
                        "id": fc_id,
                        "call_id": "",
                        "name": "",
                        "arguments": "",
                        "output_index": self.output_index,
                    }
                    self._current_fc_id = fc_id
                    self.current_type = "function_call"
                    call_id = tool_call.get("id", "")
                    tool_name = function.get("name", "")
                    events.append(self._sse("response.output_item.added", {
                        "type": "response.output_item.added",
                        "output_index": self.output_index,
                        "item": {
                            "type": "function_call",
                            "id": fc_id,
                            "call_id": str(call_id),
                            "name": str(tool_name),
                            "arguments": "",
                            "status": "in_progress",
                        },
                    }))
                    self.output_index += 1

                state = self._pending_tool_calls[tool_index]
                if tool_call.get("id") is not None:
                    if not isinstance(tool_call.get("id"), str):
                        raise ValueError("OpenAI streaming tool call id must be a string")
                    state["call_id"] = tool_call["id"]
                if function.get("name") is not None:
                    if not isinstance(function.get("name"), str):
                        raise ValueError("OpenAI streaming tool call name must be a string")
                    state["name"] = function["name"]
                args_delta = function.get("arguments")
                if args_delta is not None:
                    if not isinstance(args_delta, str):
                        raise ValueError("OpenAI streaming tool arguments must be strings")
                    state["arguments"] = str(state["arguments"]) + args_delta
                    events.append(self._sse("response.function_call_arguments.delta", {
                        "type": "response.function_call_arguments.delta",
                        "item_id": state["id"],
                        "output_index": state["output_index"],
                        "delta": args_delta,
                    }))

        finish_reason = choice.get("finish_reason")
        if finish_reason is not None:
            self._finish_reason = str(finish_reason).strip().lower()

        usage = data.get("usage")
        if isinstance(usage, dict):
            self.input_tokens = usage.get("prompt_tokens", self.input_tokens)  # type: ignore
            self.output_tokens = usage.get("completion_tokens", self.output_tokens)  # type: ignore

        if finish_reason is not None:
            events.extend(self._finish())
        return events

    def _start_message_output(self) -> list[str]:
        self._current_msg_id = f"msg_{uuid.uuid4().hex[:24]}"
        self._message_started = True
        self.current_type = "text"
        self._text_buffer = ""
        self._full_text = ""
        self._message_text_parts = []
        return [self._sse("response.output_item.added", {
            "type": "response.output_item.added",
            "output_index": self.output_index,
            "item": {
                "type": "message",
                "id": self._current_msg_id,
                "status": "in_progress",
                "role": "assistant",
                "content": [],
            },
        })]

    def _start_content_part(self) -> list[str]:
        self._content_part_started = True
        return [self._sse("response.content_part.added", {
            "type": "response.content_part.added",
            "item_id": self._current_msg_id,
            "output_index": self.output_index,
            "content_index": self.content_index,
            "part": {"type": "output_text", "text": "", "annotations": []},
        })]

    def _end_content_part(self) -> list[str]:
        events: list[str] = []
        part_text = self._text_buffer
        events.append(self._sse("response.output_text.done", {
            "type": "response.output_text.done",
            "item_id": self._current_msg_id,
            "output_index": self.output_index,
            "content_index": self.content_index,
            "text": part_text,
        }))
        events.append(self._sse("response.content_part.done", {
            "type": "response.content_part.done",
            "item_id": self._current_msg_id,
            "output_index": self.output_index,
            "content_index": self.content_index,
            "part": {"type": "output_text", "text": part_text, "annotations": []},
        }))
        self._content_part_started = False
        self.content_index += 1
        self._text_buffer = ""
        if part_text:
            self._message_text_parts.append(part_text)
        return events

    def _end_message_output(self, status: str = "completed") -> list[str]:
        content = [
            {"type": "output_text", "text": text, "annotations": []}
            for text in self._message_text_parts
        ]
        output_index = self.output_index
        msg_done: dict[str, object] = {
            "type": "message",
            "id": self._current_msg_id,
            "status": status,
            "role": "assistant",
            "content": content,
        }
        self._record_output(output_index, msg_done)
        events = [self._sse("response.output_item.done", {
            "type": "response.output_item.done",
            "output_index": output_index,
            "item": msg_done,
        })]
        self._message_started = False
        self._current_msg_id = None
        self.output_index += 1
        self.content_index = 0
        self._text_buffer = ""
        self._full_text = ""
        self._message_text_parts = []
        return events

    @staticmethod
    def _ordered_tool_items(tool_calls: dict[object, dict[str, object]]) -> list[tuple[object, dict[str, object]]]:
        def sort_key(item: tuple[object, dict[str, object]]) -> tuple[int, object]:
            index = item[0]
            if isinstance(index, int):
                return 0, index
            if isinstance(index, float) and index.is_integer():
                return 0, int(index)
            return 1, str(index)

        return sorted(tool_calls.items(), key=sort_key)

    @staticmethod
    def _valid_tool_state(state: dict[str, object]) -> bool:
        call_id = state.get("call_id")
        name = state.get("name")
        arguments = state.get("arguments")
        if not isinstance(call_id, str) or not call_id.strip():
            return False
        if not isinstance(name, str) or not name.strip():
            return False
        if not isinstance(arguments, str) or not arguments.strip():
            return False
        try:
            return isinstance(json.loads(arguments), dict)
        except json.JSONDecodeError:
            return False

    def _resolve_terminal_status(self) -> str:
        reason = self._finish_reason or ""
        if reason == "length":
            self._incomplete_details = {"reason": "max_output_tokens"}
            return "incomplete"
        if reason == "content_filter":
            self._incomplete_details = {"reason": "content_filter"}
            return "incomplete"
        if reason not in {"", "stop", "tool_calls"}:
            self._incomplete_details = {"reason": "incomplete_response"}
            return "incomplete"
        if self._invalid_tool_calls:
            self._incomplete_details = {"reason": "incomplete_tool_call"}
            return "incomplete"
        if self._pending_tool_calls:
            if reason == "tool_calls" and not all(self._valid_tool_state(state) for _, state in self._ordered_tool_items(self._pending_tool_calls)):
                self._incomplete_details = {"reason": "incomplete_tool_call"}
                return "incomplete"
            if not all(self._valid_tool_state(state) for _, state in self._ordered_tool_items(self._pending_tool_calls)):
                self._incomplete_details = {"reason": "incomplete_tool_call"}
                return "incomplete"
        elif reason == "tool_calls":
            self._incomplete_details = {"reason": "incomplete_tool_call"}
            return "incomplete"
        return "completed"

    def _finalize_tool_calls(self, status: str) -> list[str]:
        events: list[str] = []
        for _, state in self._ordered_tool_items(self._pending_tool_calls):
            output_index_value = state.get("output_index")
            if not isinstance(output_index_value, int):
                continue
            output_index = output_index_value
            valid = self._valid_tool_state(state)
            if not valid:
                self._invalid_tool_calls = True
            if valid and status == "completed":
                events.append(self._sse("response.function_call_arguments.done", {
                    "type": "response.function_call_arguments.done",
                    "item_id": state["id"],
                    "output_index": output_index,
                    "arguments": state["arguments"],
                }))
                item_status = "completed"
            else:
                item_status = "incomplete"
            if isinstance(state.get("call_id"), str) and state["call_id"] and isinstance(state.get("name"), str) and state["name"]:
                fc_done: dict[str, object] = {
                    "type": "function_call",
                    "id": state["id"],
                    "call_id": state["call_id"],
                    "name": state["name"],
                    "arguments": str(state.get("arguments", "")),
                    "status": item_status,
                }
                self._record_output(output_index, fc_done)
                events.append(self._sse("response.output_item.done", {
                    "type": "response.output_item.done",
                    "output_index": output_index,
                    "item": fc_done,
                }))
        self._pending_tool_calls.clear()
        return events

    def _finish(self) -> list[str]:
        if self._finished:
            return []
        terminal_status = self._resolve_terminal_status()
        self._terminal_status = terminal_status
        self._finished = True
        events: list[str] = []
        if self._content_part_started:
            events.extend(self._end_content_part())
        if self._message_started:
            events.extend(self._end_message_output(terminal_status))
        events.extend(self._finalize_tool_calls(terminal_status))
        if terminal_status == "completed":
            events.append(self._sse("response.completed", self._base_response("completed")))
        elif terminal_status == "incomplete":
            events.append(self._sse("response.incomplete", self._base_response("incomplete")))
        else:
            events.append(self._sse("response.failed", self._base_response("failed")))
        events.append("data: [DONE]\n\n")
        return events

    def finish(self) -> list[str]:
        """Public: terminale events (idempotent) — server ruft das nach dem stream."""
        return self._finish()

    def error_event(self, message: str, error_type: str = "api_error") -> str:
        """Responses-SSE response.failed event fuer mid-stream fehler."""
        self._finished = True
        failed_response = {
            **self._base_response("failed"),
            "error": {"code": error_type, "message": message},
        }
        return self._sse("response.failed", failed_response)

    def _sse(self, event_type: str, data: dict[str, object]) -> str:
        if data.get("object") == "response":
            event_payload: dict[str, object] = {"type": event_type, "response": data, "response_id": self.response_id}
        else:
            event_payload = dict(data)
            event_payload["type"] = event_type
            event_payload.setdefault("response_id", self.response_id)
        event_payload["model"] = self.model
        event_payload["sequence_number"] = self.sequence_number
        self.sequence_number += 1
        return f"event: {event_type}\ndata: {_safe_json(event_payload)}\n\n"
