from __future__ import annotations

import json
import logging
import re
import time
from bisect import insort
from dataclasses import dataclass, field
from logging import Logger

from ..config import AppConfig
from ..logging_utils import debug_dump
from ..model_variants import model_requests_search, model_requests_thinking, split_model_features
from ..utils.tool_parser import CODE_FENCE_PATTERN, StreamingToolParser, detect_tool_call_names, parse_tool_calls_from_text
from ..utils.tool_protocol import (
    BLOCKED_NATIVE_TOOL_NAMES,
    CANONICAL_TOOL_CALL_EXAMPLE,
    TOOL_FORMAT_REMINDER,
    SERVER_SIDE_TOOL_NAMES,
    build_tool_call_instructions as _protocol_build_tool_call_instructions,
    filter_tools,
    normalize_tool_name,
    safe_json_dumps,
    serialize_tool_call_block as _protocol_serialize_tool_call_block,
    serialize_tool_result_block as _protocol_serialize_tool_result_block,
    tools_to_prompt as _protocol_tools_to_prompt,
)


ASSISTANT_ID_PATTERN = re.compile(r"^[a-z0-9]{24,}$")
URL_PATTERN = re.compile(r"https?://[^\s<>()\"']+")
POWERSHELL_CMDLET_PATTERN = re.compile(r"^[A-Z][A-Za-z]+-[A-Z][A-Za-z]+$")
POWERSHELL_ALIASES = {"cat", "cd", "copy", "del", "dir", "echo", "erase", "ls", "md", "move", "pwd", "rd", "ren", "rm", "sc", "type"}



def _merge_part_texts(existing: dict[str, object], incoming: dict[str, object], event_status: str = "") -> dict[str, object]:
    """Fusioniert zwei Part-Events desselben logic_id zu EINEM akkumulierten
    Text-Item (die Delta-Logik arbeitet mit rendered_text[prev_len:]).

    Upstream-Verhalten: init-Events enthalten je einen TOKEN-Schnipsel im
    text-Feld (Deltas, keine Akkumulation!), das finish-Event den kompletten
    Text. Snipsel werden an den Akkumulat angehängt; ein finish-Volltext,
    der mit dem Akkumulat beginnt, ersetzt ihn idempotent.

    Der finish-Status kann im Part ODER nur top-level im Event stehen
    (beide Varianten im Upstream beobachtet) — daher event_status als
    Fallback. Der Volltext-Ersatz selbst ist status-unabhängig robust:
    beginnt der Fragment mit dem Akkumulierten, ist er immer der Volltext
    (Deltas können niemals den bisherigen Stand als Präfix haben)."""
    merged = dict(existing)
    inc_content = incoming.get("content")
    if not isinstance(inc_content, list):
        return merged
    old_content = existing.get("content")
    old_text = ""
    non_text_old: list[object] = []
    if isinstance(old_content, list):
        for item in old_content:
            if isinstance(item, dict) and item.get("type") == "text":
                old_text += str(item.get("text", ""))
            else:
                non_text_old.append(item)

    incoming_status = str(incoming.get("status", ""))
    if not incoming_status and event_status:
        incoming_status = str(event_status)
    new_text_total = old_text
    for item in inc_content:
        if not (isinstance(item, dict) and item.get("type") == "text"):
            continue
        fragment = str(item.get("text", ""))
        if not fragment:
            continue
        if old_text and fragment.startswith(old_text):
            # finish-Volltext: akkumulat auf den volltext anheben
            # (idempotent — gilt fuer part-status UND event-status-Variante)
            new_text_total = fragment
        else:
            new_text_total = old_text + fragment if new_text_total == old_text else new_text_total + fragment
            if new_text_total == old_text:
                new_text_total = old_text  # keine aenderung
    # ein einzelnes text-item mit dem akkumulierten stand
    content: list[object] = []
    if new_text_total:
        content.append({"type": "text", "text": new_text_total})
    merged["content"] = content + non_text_old
    # auch non-text-items des incoming uebernehmen (bilder etc.)
    for item in inc_content:
        if isinstance(item, dict) and item.get("type") != "text":
            merged["content"].append(item)
    return merged


def extract_text_content(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return json.dumps(content, ensure_ascii=False, separators=(",", ":"))
    if not isinstance(content, list):
        return ""

    text_parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "text":
            text_parts.append(str(item.get("text", "")))
        elif item_type == "image_url":
            url = item.get("image_url", {}).get("url", "")
            text_parts.append(f"[image:{url}]")
        elif item_type == "file":
            url = item.get("file_url", {}).get("url", "")
            text_parts.append(f"[file:{url}]")
    return "\n".join(part for part in text_parts if part)


def extract_first_url(text: str) -> str | None:
    match = URL_PATTERN.search(text)
    if not match:
        return None
    return match.group(0).rstrip(".,;:!?)}+")


def extract_recent_user_url(messages: list[dict[str, object]]) -> str | None:
    for message in reversed(messages):
        if str(message.get("role", "")).strip() != "user":
            continue
        text = extract_text_content(message.get("content"))
        url = extract_first_url(text)
        if url:
            return url
    return None


# Gezieltes Repair fuer ein bekanntes LLM-Quoting-Versagen: das Modell
# emittiert python-code mit x'key' statt x['key'] (fehlende brackets beim
# dict-zugriff, beobachtet mit inline `python3 -c "..."` commands).
_BROKEN_DICT_ACCESS = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)'([A-Za-z_][A-Za-z0-9_]*)'")
_PYTHON_CMD_INNER = re.compile(r"""^(python3?|pypy3?)\s+-c\s+(?:"([^"]*)"|'([^']*)')\s*$""", re.DOTALL)


def _python_compiles(code: str) -> bool:
    """Der Compile-Oracle: true wenn der code syntaktisch gueltiges python ist."""
    try:
        compile(code, "<tool-command>", "exec")
        return True
    except SyntaxError:
        return False


def repair_python_command_quotes(command: str) -> str:
    """Repariert x'key' -> x['key'] in python-commands.

    Compile-Oracle auf dem INNEREN von `python3 -c \"...\"` (der shell-wrapper
    selbst ist kein python und kompiliert nie). Reparatur wird nur uebernommen,
    wenn das innere vorher nicht kompilierte und nachher tut — funktionierender
    code wird nie angerührt (keine false positives)."""
    match = _PYTHON_CMD_INNER.match(command.strip())
    if not match:
        return command
    inner = match.group(2) if match.group(2) is not None else match.group(3)
    quote = '"' if match.group(2) is not None else "'"
    if _python_compiles(inner):
        return command
    repaired_inner = _BROKEN_DICT_ACCESS.sub(r"\1['\2']", inner)
    if repaired_inner != inner and _python_compiles(repaired_inner):
        return command[: match.start(2) if match.group(2) is not None else match.start(3)] + repaired_inner + command[(match.end(2) if match.group(2) is not None else match.end(3)) :]
    return command


def sanitize_tool_call_payload(
    tool_name: str,
    arguments: object,
    fallback_url: str | None = None,
) -> dict[str, object] | None:
    parsed_arguments = arguments
    if isinstance(arguments, str):
        try:
            parsed_arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return None

    if parsed_arguments is None:
        parsed_arguments = {}
    if not isinstance(parsed_arguments, dict):
        return None

    cleaned = {str(key): value for key, value in parsed_arguments.items()}
    if cleaned == {"param_name": "url"} and fallback_url:
        cleaned = {"url": fallback_url}
    elif cleaned == {"param_name": "url"}:
        cleaned = {}
    if "param_name" in cleaned and "param_value" not in cleaned and len(cleaned) == 1:
        cleaned = {}

    if tool_name in {"bash", "shell", "run", "execute"}:
        command = cleaned.get("command")
        if isinstance(command, str):
            # Quote-Repair fuer python-commands (compile-oracle-geprüft)
            stripped = command.strip()
            if re.match(r"^(python3?|pypy3?)\s", stripped):
                cleaned["command"] = repair_python_command_quotes(command)

    if tool_name == "shell":
        command = cleaned.get("command")
        if isinstance(command, str):
            stripped_command = command.strip()
            if stripped_command.startswith("["):
                try:
                    parsed_command = json.loads(stripped_command)
                except json.JSONDecodeError:
                    parsed_command = None
                if isinstance(parsed_command, list):
                    cleaned["command"] = [str(part) for part in parsed_command]
            elif stripped_command.startswith('"'):
                try:
                    parsed_command = json.loads(f"[{stripped_command}]")
                except json.JSONDecodeError:
                    parsed_command = None
                if isinstance(parsed_command, list):
                    cleaned["command"] = [str(part) for part in parsed_command]
            else:
                cleaned["command"] = ["powershell.exe", "-Command", stripped_command]
        elif isinstance(command, list) and command:
            command_parts = [str(part) for part in command]
            command_name = command_parts[0].strip()
            lower_name = command_name.lower()
            is_shell_host = lower_name in {"powershell", "powershell.exe", "pwsh", "pwsh.exe", "cmd", "cmd.exe"}
            is_powershell_command = bool(POWERSHELL_CMDLET_PATTERN.fullmatch(command_name)) or lower_name in POWERSHELL_ALIASES
            if is_powershell_command and not is_shell_host:
                cleaned["command"] = ["powershell.exe", "-Command", " ".join(command_parts)]

    return cleaned


def sanitize_tool_calls(
    tool_calls: list[dict[str, object]],
    fallback_url: str | None = None,
) -> list[dict[str, object]]:
    sanitized: list[dict[str, object]] = []
    for index, tool_call in enumerate(tool_calls):
        function = tool_call.get("function", {})
        if not isinstance(function, dict):
            continue
        tool_name = str(function.get("name", "")).strip()
        if not tool_name:
            continue
        original_arguments = function.get("arguments", "{}")
        original_value: object = original_arguments
        if isinstance(original_arguments, str):
            try:
                original_value = json.loads(original_arguments)
            except json.JSONDecodeError:
                original_value = original_arguments
        cleaned_arguments = sanitize_tool_call_payload(
            tool_name=tool_name,
            arguments=original_arguments,
            fallback_url=fallback_url,
        )
        if cleaned_arguments is None:
            continue
        repaired = not isinstance(original_value, dict) or safe_json_dumps(cleaned_arguments) != safe_json_dumps(original_value)
        sanitized.append(
            {
                "id": str(tool_call.get("id", "")) or f"call_repaired_{index}",
                "type": "function",
                "index": index,
                "_repaired": repaired,
                "function": {
                    "name": tool_name,
                    "arguments": safe_json_dumps(cleaned_arguments),
                },
            }
        )
    return sanitized


def parse_tool_choice_policy(tool_choice: object, available_tool_names: set[str] | None = None) -> dict[str, object]:
    available = available_tool_names or set()
    if tool_choice is None:
        return {"mode": "auto", "tool_name": None}
    if isinstance(tool_choice, str):
        normalized = tool_choice.strip().lower()
        if normalized in {"auto", "none", "required"}:
            return {"mode": normalized, "tool_name": None}
        return {"mode": "auto", "tool_name": None}
    if not isinstance(tool_choice, dict):
        return {"mode": "auto", "tool_name": None}

    choice_type = str(tool_choice.get("type", "")).strip().lower()
    if choice_type == "function":
        function = tool_choice.get("function", {})
        if isinstance(function, dict):
            tool_name = str(function.get("name", "")).strip()
            if tool_name and (not available or tool_name in available):
                return {"mode": "specific", "tool_name": tool_name}
        return {"mode": "auto", "tool_name": None}

    if choice_type in {"auto", "none", "required"}:
        return {"mode": choice_type, "tool_name": None}
    return {"mode": "auto", "tool_name": None}
build_tool_call_instructions = _protocol_build_tool_call_instructions
serialize_tool_call_block = _protocol_serialize_tool_call_block
serialize_tool_result_block = _protocol_serialize_tool_result_block
tools_to_prompt = _protocol_tools_to_prompt


def convert_messages(
    messages: list[dict[str, object]],
    tools: list[dict[str, object]] | None,
    blocked_tool_names: set[str] | None = None,
    tool_choice: object | None = None,
    server_side_tool_names: set[str] | None = None,
) -> list[dict[str, object]]:
    tools = filter_tools(tools, blocked_tool_names or set())
    available_tool_names = {
        str(tool.get("function", {}).get("name", "")).strip()
        for tool in (tools or [])
        if isinstance(tool, dict) and isinstance(tool.get("function"), dict)
    }
    available_tool_names.discard("")
    server_side_tool_names = server_side_tool_names or SERVER_SIDE_TOOL_NAMES
    tool_choice_policy = parse_tool_choice_policy(tool_choice, available_tool_names)
    processed: list[dict[str, str]] = []
    latest_user_url: str | None = extract_recent_user_url(messages)
    valid_tool_call_ids: set[str] = set()
    tool_names_by_call_id: dict[str, str] = {}
    repaired_tool_call_ids: set[str] = set()
    for message in messages:
        role = str(message.get("role", "user"))
        content = message.get("content")
        if role == "user":
            current_text = extract_text_content(content)
            current_url = extract_first_url(current_text)
            if current_url:
                latest_user_url = current_url
        if role == "assistant" and message.get("tool_calls"):
            tool_blocks: list[str] = []
            raw_tool_calls = message.get("tool_calls", []) # pyright: ignore[reportGeneralTypeIssues]
            sanitized_tool_calls = sanitize_tool_calls(
                raw_tool_calls if isinstance(raw_tool_calls, list) else [],
                fallback_url=latest_user_url,
            )
            for tool_call in sanitized_tool_calls:
                function = tool_call.get("function", {})
                tool_name = str(function.get("name", "unknown"))
                if available_tool_names and tool_name not in available_tool_names:
                    continue
                tool_blocks.append(
                    serialize_tool_call_block(
                        name=tool_name,
                        arguments=function.get("arguments", "{}"),
                    )
                )
                tool_call_id = str(tool_call.get("id", "")).strip()
                if tool_call_id:
                    valid_tool_call_ids.add(tool_call_id)
                    tool_names_by_call_id[tool_call_id] = tool_name
                    # Argumente wurden repariert -> die alte (fehlerhafte) tool-result
                    # dieser id gehoert zum kaputten call und verwirrt das modell nur
                    if bool(tool_call.get("_repaired")):
                        repaired_tool_call_ids.add(tool_call_id)
            assistant_text = extract_text_content(content).strip() if content else ""
            block = "\n".join(tool_blocks)
            if not assistant_text and not block:
                continue
            content = f"{assistant_text}\n{block}".strip() if assistant_text and block else (assistant_text or block)
        elif role == "tool":
            tool_call_id = str(message.get("tool_call_id", "")).strip()
            if tool_call_id and valid_tool_call_ids and tool_call_id not in valid_tool_call_ids:
                continue
            if tool_call_id and tool_call_id in repaired_tool_call_ids:
                continue
            role = "user"
            tool_name = str(message.get("name", "")).strip() or tool_names_by_call_id.get(tool_call_id, "")
            if not tool_name:
                continue
            tool_result_text = extract_text_content(content)
            content = serialize_tool_result_block(
                tool_call_id=tool_call_id or message.get("tool_call_id", "unknown"),
                tool_name=tool_name,
                content=tool_result_text,
            )
        elif role == "assistant" and not content:
            continue

        text = extract_text_content(content) if content else ""
        if text:
            processed.append({"role": role, "content": text})

    transcript_parts: list[str] = []

    if tools and tool_choice_policy.get("mode") != "none":
        transcript_parts.append(
            tools_to_prompt(
                tools,
                blocked_tool_names=blocked_tool_names,
                tool_choice_policy=tool_choice_policy,
                server_side_tool_names=server_side_tool_names,
            )
        )
        transcript_parts.append("# CONVERSATION")

    for item in processed:
        title = (
            item["role"]
            .replace("system", "System")
            .replace("assistant", "Assistant")
            .replace("user", "User")
            .replace("developer", "Developer")
        )
        transcript_parts.append(f"{title}: {item['content']}".strip())

    prompt = "\n\n".join(part for part in transcript_parts if part).strip()
    # Re-Anchor: nach Tool-Result-Runden verliert das Modell die Format-
    # Disziplin (prose statt JSON, halluzinierte Limits — Blaupause
    # gemini-web2api Re-Anchor-Fix). Der Reminder steht damit DIREKT am
    # Prompt-Ende, wo die []-Terminator-Wahrscheinlichkeit pro generiertem
    # Token am staerksten wirkt.
    if tools and tool_choice_policy.get("mode") != "none" and _conversation_has_tool_round(processed):
        prompt = prompt + "\n\n" + TOOL_FORMAT_REMINDER
    return [{"role": "user", "content": [{"type": "text", "text": prompt + "\n\nAssistant: "}]}]


def _conversation_has_tool_round(processed: list[dict[str, str]]) -> bool:
    for item in processed:
        content = item.get("content", "")
        if item.get("role") == "assistant" and content.startswith('{"tool_calls"'):
            return True
    return False


def resolve_upstream_model(requested_model: str, config: AppConfig) -> tuple[str, str]:
    base_model, _ = split_model_features(requested_model)
    upstream_model = config.model_aliases.get(base_model, base_model)
    assistant_id = upstream_model if ASSISTANT_ID_PATTERN.fullmatch(upstream_model) else config.glm_assistant_id
    return upstream_model, assistant_id


# Reasoning levels: real chat_mode values of the chatglm.cn web UI (verified
# via CDP reverse engineering 2026-09-07):
#   ""             = quick (no thinking)
#   "thinking"     = deep (standard thinking)
#   "deep_thinking" = ultra (full thinking, takes longer)
# Note: The old value "zero" was never sent by the real UI.
CHAT_MODE_THINKING = "thinking"
CHAT_MODE_DEEP_THINKING = "deep_thinking"

_EFFORT_TO_CHAT_MODE = {
    # low    = quick (no thinking)
    # medium = deep (standard thinking)  — intermediate level
    # high   = thinking (full thinking via UI mode deep+)
    # max    = ultra (deep_thinking, full-power reasoning)
    "low": "",
    "minimal": "",
    "medium": CHAT_MODE_THINKING,
    "high": CHAT_MODE_THINKING,
    "max": CHAT_MODE_DEEP_THINKING,
}


def resolve_chat_mode(model: str, reasoning_effort: object, deep_research: object) -> str:
    lower_model = (model or "").lower()
    if deep_research or "deepresearch" in lower_model or "deep-research" in lower_model:
        return "deep_research"
    # Explizite Stufe (reasoning_effort) übersetzt 1:1 in den echten UI-Wert.
    if isinstance(reasoning_effort, str) and reasoning_effort.lower() in _EFFORT_TO_CHAT_MODE:
        return _EFFORT_TO_CHAT_MODE[reasoning_effort.lower()]
    # truthy-aber-unbekannt (z.B. Zahlen, "xhigh") → volles Denken als Default.
    if reasoning_effort:
        return CHAT_MODE_DEEP_THINKING
    if model_requests_thinking(model) or "think" in lower_model:
        # -think-Modell ohne Stufe: volles Denken (früheres "zero" war ein
        # von der UI nie gesendeter Wert).
        return CHAT_MODE_DEEP_THINKING
    if "zero" in lower_model:
        return CHAT_MODE_THINKING
    return ""


def resolve_networking(model: str, web_search: object) -> bool:
    return bool(web_search) or model_requests_search(model)


def extract_history_tool_call_signatures(messages: list[dict[str, object]]) -> set[str]:
    """Signatur aller Assistant-Tool-Calls der Request-Historie
    (name + kanonische Argumente). Dient als Echo-Filter: der Upstream
    spiegelt fruehere Tool-Calls gern als native 'tool_calls'-Parts
    zurueck — solche Echos duerfen nie als neue Calls durchgeleitet
    werden (beobachtet: 36 gespiegelte Parts pro Turn, Duplikat-Loops)."""
    signatures: set[str] = set()
    for message in messages:
        if str(message.get("role", "")) != "assistant":
            continue
        tool_calls = message.get("tool_calls")
        if not isinstance(tool_calls, list):
            continue
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue
            function = tool_call.get("function", {})
            if not isinstance(function, dict):
                continue
            name = str(function.get("name", "")).strip()
            if not name:
                continue
            arguments = function.get("arguments", "{}")
            if isinstance(arguments, str):
                args_str = arguments
            else:
                args_str = json.dumps(arguments or {}, ensure_ascii=False, sort_keys=True)
            try:
                normalized = json.dumps(json.loads(args_str), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            except json.JSONDecodeError:
                normalized = args_str
            signatures.add(f"{name}:{normalized}")
    return signatures


@dataclass
class GLMEventAccumulator:
    model: str
    allowed_tool_names: set[str] | None = None
    fallback_tool_url: str | None = None
    debug_enabled: bool = False
    logger: Logger | None = None
    history_tool_call_signatures: set[str] = field(default_factory=set)
    conversation_id: str = ""
    created: int = field(default_factory=lambda: int(time.time()))
    parts_by_logic_id: dict[str, dict[str, object]] = field(default_factory=dict)
    ordered_logic_ids: list[str] = field(default_factory=list)
    last_full_text: str = ""
    last_full_reasoning: str = ""
    _part_text_sent: dict[str, int] = field(default_factory=dict)
    _part_reasoning_sent: dict[str, int] = field(default_factory=dict)
    _known_logic_ids_for_text: list[str] = field(default_factory=list)
    _known_logic_ids_for_reasoning: list[str] = field(default_factory=list)
    tool_parser: StreamingToolParser = field(default_factory=StreamingToolParser)
    emitted_role: bool = False
    _render_cache_dirty: bool = True
    _cached_full_text: str = ""
    _cached_full_reasoning: str = ""
    _cached_part_texts: dict[str, str] = field(default_factory=dict)
    _cached_part_reasonings: dict[str, str] = field(default_factory=dict)
    _server_side_tool_calls: list[dict[str, object]] = field(default_factory=list)
    _server_side_tool_call_ids: set[str] = field(default_factory=set)
    _server_side_tool_call_signatures: set[str] = field(default_factory=set)
    _deferred_visible_text: str = ""
    blocked_tool_attempt_names: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.tool_parser.allowed_tool_names = self.allowed_tool_names

    def consume_event(self, payload: dict[str, object]) -> tuple[list[str], str | None]:
        debug_dump(self.logger or logging.getLogger("glm2api.null"), self.debug_enabled, "GLM SSE parsed event", payload)
        if not self.conversation_id and payload.get("conversation_id"):
            self.conversation_id = str(payload["conversation_id"])

        for part in payload.get("parts", []) if isinstance(payload.get("parts"), list) else []: # pyright: ignore[reportGeneralTypeIssues]
            if isinstance(part, dict) and part.get("logic_id"):
                logic_id = str(part["logic_id"])
                if logic_id not in self.parts_by_logic_id:
                    insort(self.ordered_logic_ids, logic_id)
                    self.parts_by_logic_id[logic_id] = part
                else:
                    # Der Upstream sendet bei init-Events TOKEN-Schnipsel (nicht den
                    # vollen Stand!) und im finish-Event den kompletten Text.
                    # Snipsel werden konkateniert; finish-Volltext ersetzt, WENN er
                    # nicht bloss die bereits akkumulierte Folge fortsetzt.
                    existing = self.parts_by_logic_id[logic_id]
                    merged = _merge_part_texts(existing, part, event_status=str(payload.get("status", "")))
                    self.parts_by_logic_id[logic_id] = merged
                self._render_cache_dirty = True
            # Extract server-side native tool_calls from content items
            if isinstance(part, dict) and isinstance(part.get("content"), list):
                for content in part["content"]:
                    if isinstance(content, dict) and content.get("type") == "tool_calls":
                        tool_calls_data = content.get("tool_calls")
                        if isinstance(tool_calls_data, dict):
                            tool_name = str(tool_calls_data.get("name", "")).strip()
                            tool_id = str(tool_calls_data.get("id", "")).strip()
                            arguments = tool_calls_data.get("arguments", "{}")
                            if self.allowed_tool_names is not None and tool_name not in self.allowed_tool_names:
                                continue
                            if tool_name and tool_id and tool_id not in self._server_side_tool_call_ids:
                                # Echo-Filter: der Upstream spiegelt bereits
                                # ausgefuehrte Assistant-Tool-Calls der Historie
                                # als native Parts zurueck (bis zu Dutzende pro
                                # Turn). Eine Signatur, die exakt einem Call aus
                                # der Request-Historie entspricht, ist ein Echo —
                                # nie ein neuer Call. Zusaetzlich Signatur-Dedup:
                                # mehrfach identische Parts kollabieren auf einen.
                                if isinstance(arguments, str):
                                    args_str = arguments
                                else:
                                    args_str = safe_json_dumps(arguments)
                                try:
                                    normalized = json.dumps(json.loads(args_str), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                                except json.JSONDecodeError:
                                    normalized = args_str
                                signature = f"{tool_name}:{normalized}"
                                if signature in self.history_tool_call_signatures:
                                    if self.logger:
                                        self.logger.info(
                                            "Dropped echoed native tool_call (history signature match) tool=%s",
                                            tool_name,
                                        )
                                    continue
                                if signature in self._server_side_tool_call_signatures:
                                    if self.logger:
                                        self.logger.info(
                                            "Dropped duplicate native tool_call (signature dedup) tool=%s",
                                            tool_name,
                                        )
                                    continue
                                self._server_side_tool_call_signatures.add(signature)
                                self._server_side_tool_call_ids.add(tool_id)
                                self._server_side_tool_calls.append(
                                    {
                                        "id": tool_id,
                                        "type": "function",
                                        "index": len(self._server_side_tool_calls),
                                        "function": {
                                            "name": tool_name,
                                            "arguments": str(arguments) if isinstance(arguments, str) else safe_json_dumps(arguments),
                                        },
                                    }
                                )

        text_delta, reasoning_delta = self._compute_deltas()
        self.last_full_text = self._cached_full_text
        self.last_full_reasoning = self._cached_full_reasoning

        chunks: list[str] = []
        if reasoning_delta:
            chunks.append(
                self._chunk_json(
                    {
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"reasoning_content": reasoning_delta},
                                "finish_reason": None,
                            }
                        ]
                    }
                )
            )

        visible_text_delta = self.tool_parser.consume(text_delta)
        if visible_text_delta:
            fence_pending = self._deferred_visible_text.count("```") % 2 == 1
            fence_opens = "```" in visible_text_delta
            # Midstream-Guard (Re-Befund C): ein delta, das Protokoll-
            # fragmente enthaelt, darf NIE sofort als content raus. Der
            # StreamingToolParser haelt vollstaendige protokolle zurueck,
            # aber gespiegelte/verstueckelte parts (observed 22:35:
            # tool_calls=1 UND text_len=1630 gleichzeitig) koennen am
            # parser vorbei fragmente enthalten. Parken im deferred buffer —
            # dort greift das finalize-safety-net (parse + cleanup).
            protocol_fragment = self.allowed_tool_names is not None and (
                '{"tool_calls"' in visible_text_delta
                or "<ml_tool_call" in visible_text_delta
                or "<|DSML|tool_call" in visible_text_delta
            )
            if self.allowed_tool_names is not None and (
                self.tool_parser.pending_text
                or fence_pending
                or fence_opens
                or protocol_fragment
            ):
                # Deferral: (a) parser haelt ein potentielles tool-protokoll-
                # stueck, (b) ein fence ist offen, (c) dieser delta oeffnet
                # einen fence, oder (d) der delta enthaelt selbst protokoll-
                # fragmente. Fences koennen das tool-protokoll umhuellen
                # (```json {"tool_calls":...}); das unwrap passiert im
                # finalize. Sonst wuerde JEDER text bei deklarierten tools
                # bis zum finalize gebuffert (UX-regression).
                self._deferred_visible_text += visible_text_delta
            else:
                delta_payload: dict[str, object] = {"content": visible_text_delta}
                if not self.emitted_role:
                    delta_payload = {"role": "assistant", "content": visible_text_delta}
                    self.emitted_role = True
                chunks.append(
                    self._chunk_json(
                        {
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": delta_payload,
                                    "finish_reason": None,
                                }
                            ]
                        }
                    )
                )
        debug_dump(self.logger or logging.getLogger("glm2api.null"), self.debug_enabled, "GLM SSE generated delta chunks", chunks)
        return chunks, str(payload.get("status")) if payload.get("status") is not None else None

    def _unwrap_protocol_only_fences(self, text: str) -> str | None:
        """Entfernt ```-Fences, deren Inhalt (fast) NUR das Tool-Protokoll
        ist. Ein Agent, der seinen Call in einen ```json-Fence packt, ist ein
        echter Aufruf; ein Doku-Beispiel mit Prosa im selben Text bleibt
        maskiert. Gibt None zurueck, wenn nichts entpackt wurde."""
        matches = list(CODE_FENCE_PATTERN.finditer(text))
        if not matches:
            return None
        result = text
        for match in reversed(matches):
            body = match.group(0)
            stripped = body.strip("`").strip()
            # Sprache-Praefix wie 'json' tolerieren
            if stripped.lower().startswith("json"):
                stripped = stripped[4:].strip()
            inner = stripped
            if not inner.lstrip().startswith('{"tool_calls"'):
                continue
            # Fences, die das Protokoll umschliessen: nur ungefaehr nothing else
            # erlauben (trailing []-terminator + whitespace ist ok)
            remainder = inner.strip()
            if remainder.startswith('{"tool_calls"'):
                # nur wenn das GESAMTE fence dem protokoll entspricht
                result = result[: match.start()] + inner + result[match.end():]
        if result != text:
            return result
        return None

    def finalize(self, status: str | None, last_error: dict[str, object] | None = None) -> list[str]:
        tail_text, xml_tool_calls = self.tool_parser.flush()
        xml_tool_calls = sanitize_tool_calls(xml_tool_calls, fallback_url=self.fallback_tool_url)
        if not xml_tool_calls:
            # Streaming counterpart of build_response(): when the model emits
            # the tool-call protocol inside the REASONING channel (observed
            # with glm-5.3-think under large system prompts), the text-side
            # parser never sees it. Recover the calls from the reasoning text
            # instead of leaking raw protocol fragments as visible content.
            xml_tool_calls = self._extract_reasoning_tool_calls()

        # Merge server-side and XML tool calls, re-indexing
        all_tool_calls: list[dict[str, object]] = list(self._server_side_tool_calls)
        for tc in xml_tool_calls:
            tc_copy = dict(tc)
            tc_copy["index"] = len(all_tool_calls)
            all_tool_calls.append(tc_copy)

        if self.logger:
            self.logger.info(
                "Response finalize status=%s text_len=%s reasoning_len=%s tool_calls=%s server_tools=%s",
                status,
                len(self._cached_full_text),
                len(self._cached_full_reasoning),
                len(xml_tool_calls),
                len(self._server_side_tool_calls),
            )

        chunks: list[str] = []
        final_text = self._deferred_visible_text + tail_text
        self._deferred_visible_text = ""
        if final_text and self.allowed_tool_names is not None:
            # Fence-unwrap: models sometimes wrap the tool-call protocol in
            # a ```json fence. A fence whose content is (almost) ONLY the
            # protocol is an agent tool call, not a documentation example —
            # strip the fence before the protocol scan. Prosa around the
            # fence keeps it masked (documentation case stays protected).
            unwrapped = self._unwrap_protocol_only_fences(final_text)
            if unwrapped is not None:
                final_text = unwrapped
            # Safety net: if tool-call protocol blocks leaked into the
            # visible text (observed with glm-5.3-think after tool-result
            # rounds: token-snipsel + finish-fulltext part-merge can emit
            # protocol fragments as content), extract them here instead of
            # forwarding raw JSON protocol to the client. Parse WITHOUT the
            # allow-list so blocked/undeclared attempts are detected too —
            # allowed ones become real tool calls, blocked ones are recorded
            # for the negative-result follow-up round.
            cleaned_text, attempted_tool_calls = parse_tool_calls_from_text(
                final_text,
                allowed_tool_names=None,
            )
            if attempted_tool_calls:
                for tool_call in attempted_tool_calls:
                    function = tool_call.get("function", {})
                    if not isinstance(function, dict):
                        continue
                    tool_name = str(function.get("name", "")).strip()
                    if not tool_name:
                        continue
                    if tool_name in self.allowed_tool_names:
                        tc_copy = dict(tool_call)
                        tc_copy["index"] = len(all_tool_calls)
                        all_tool_calls.append(tc_copy)
                    else:
                        self.blocked_tool_attempt_names.append(tool_name)
                final_text = cleaned_text.strip()
        if not all_tool_calls and self.allowed_tool_names is not None:
            attempted_names: list[str] = []
            for source_text in (self._cached_full_text.strip(), self._cached_full_reasoning.strip()):
                if source_text:
                    attempted_names.extend(detect_tool_call_names(source_text))
            unavailable_names = sorted(
                {
                    name
                    for name in attempted_names
                    if name not in self.allowed_tool_names
                }
            )
            if unavailable_names:
                self.blocked_tool_attempt_names.extend(unavailable_names)
                allowed_names = ", ".join(sorted(self.allowed_tool_names)) or "(none)"
                final_text = (
                    "The model attempted to call an undeclared tool: "
                    + ", ".join(f"`{name}`" for name in unavailable_names)
                    + f". Blocked. Only these tools are allowed in this round: {allowed_names}."
                )
        if final_text and not all_tool_calls:
            delta_payload: dict[str, object] = {"content": final_text}
            if not self.emitted_role:
                delta_payload = {"role": "assistant", "content": final_text}
                self.emitted_role = True
            chunks.append(
                self._chunk_json(
                    {
                        "choices": [
                            {
                                "index": 0,
                                "delta": delta_payload,
                                "finish_reason": None,
                            }
                        ]
                    }
                )
            )

        if status == "intervene" and last_error and last_error.get("intervene_text"):
            chunks.append(
                self._chunk_json(
                    {
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": "\n\n" + str(last_error["intervene_text"])},
                                "finish_reason": None,
                            }
                        ]
                    }
                )
            )

        if all_tool_calls:
            if not self.emitted_role:
                chunks.append(
                    self._chunk_json(
                        {
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"role": "assistant"},
                                    "finish_reason": None,
                                }
                            ]
                        }
                    )
                )
                self.emitted_role = True
            for tool_call in all_tool_calls:
                chunks.append(
                    self._chunk_json(
                        {
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {
                                        "tool_calls": [
                                            {
                                                "index": tool_call["index"],
                                                "id": tool_call["id"],
                                                "type": "function",
                                                "function": tool_call["function"],
                                            }
                                        ]
                                    },
                                    "finish_reason": None,
                                }
                            ]
                        }
                    )
                )

        finish_reason = "tool_calls" if all_tool_calls else "stop"
        chunks.append(
            self._chunk_json(
                {
                    "choices": [
                        {
                            "index": 0,
                            "delta": {},
                            "finish_reason": finish_reason,
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }
            )
        )
        chunks.append("data: [DONE]\n\n")
        debug_dump(self.logger or logging.getLogger("glm2api.null"), self.debug_enabled, "GLM SSE finalize output", chunks)
        return chunks

    def build_response(self) -> dict[str, object]:
        full_text, full_reasoning = self._render_full_output()
        if not full_text and self.last_full_text:
            full_text = self.last_full_text
        if not full_reasoning and self.last_full_reasoning:
            full_reasoning = self.last_full_reasoning
        clean_content, xml_tool_calls = parse_tool_calls_from_text(
            full_text.strip(),
            allowed_tool_names=self.allowed_tool_names,
        )
        xml_tool_calls = sanitize_tool_calls(xml_tool_calls, fallback_url=self.fallback_tool_url)
        if not xml_tool_calls:
            xml_tool_calls = self._extract_reasoning_tool_calls(full_reasoning)
        if self.allowed_tool_names is not None and not xml_tool_calls:
            # Non-stream counterpart of finalize(): record blocked tool
            # attempts so the client can start a negative-result round.
            attempted_names: list[str] = []
            for source_text in (full_text.strip(), full_reasoning.strip()):
                if source_text:
                    attempted_names.extend(detect_tool_call_names(source_text))
            self.blocked_tool_attempt_names.extend(
                name
                for name in attempted_names
                if name not in self.allowed_tool_names
            )

        # Merge server-side and XML tool calls, re-indexing
        all_tool_calls: list[dict[str, object]] = list(self._server_side_tool_calls)
        for tc in xml_tool_calls:
            tc_copy = dict(tc)
            tc_copy["index"] = len(all_tool_calls)
            all_tool_calls.append(tc_copy)

        final_content = clean_content.strip()
        message: dict[str, object] = {
            "role": "assistant",
            "content": None if all_tool_calls or not final_content else final_content,
            "reasoning_content": full_reasoning or None,
        }
        if all_tool_calls:
            message["tool_calls"] = [
                {"id": item["id"], "type": "function", "function": item["function"]}
                for item in all_tool_calls
            ]
        response = {
            "id": self.conversation_id,
            "object": "chat.completion",
            "created": self.created,
            "model": self.model,
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": "tool_calls" if all_tool_calls else "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        if self.logger:
            self.logger.info(
                "Non-streaming response built model=%s text_len=%s reasoning_len=%s tool_calls=%s",
                self.model,
                len(final_content),
                len(full_reasoning),
                len(all_tool_calls),
            )
        debug_dump(self.logger or logging.getLogger("glm2api.null"), self.debug_enabled, "GLM non-streaming final response", response)
        return response

    def _extract_reasoning_tool_calls(self, reasoning_text: str | None = None) -> list[dict[str, object]]:
        source = (reasoning_text if reasoning_text is not None else self.last_full_reasoning) or self._cached_full_reasoning
        if not source:
            return []
        _, tool_calls = parse_tool_calls_from_text(
            source.strip(),
            allowed_tool_names=self.allowed_tool_names,
        )
        return sanitize_tool_calls(tool_calls, fallback_url=self.fallback_tool_url)

    def _compute_deltas(self) -> tuple[str, str]:
        self._render_full_output()
        text_delta_parts: list[str] = []
        reasoning_delta_parts: list[str] = []

        for logic_id in self.ordered_logic_ids:
            rendered_text = self._cached_part_texts.get(logic_id, "")
            rendered_reasoning = self._cached_part_reasonings.get(logic_id, "")

            if rendered_text:
                prev_len = self._part_text_sent.get(logic_id, 0)
                is_new = logic_id not in self._known_logic_ids_for_text
                if is_new:
                    self._known_logic_ids_for_text.append(logic_id)
                    if text_delta_parts or self._part_text_sent:
                        text_delta_parts.append("\n\n")
                    text_delta_parts.append(rendered_text)
                elif len(rendered_text) > prev_len:
                    text_delta_parts.append(rendered_text[prev_len:])
                self._part_text_sent[logic_id] = len(rendered_text)

            if rendered_reasoning:
                prev_len = self._part_reasoning_sent.get(logic_id, 0)
                is_new = logic_id not in self._known_logic_ids_for_reasoning
                if is_new:
                    self._known_logic_ids_for_reasoning.append(logic_id)
                    if reasoning_delta_parts or self._part_reasoning_sent:
                        reasoning_delta_parts.append("\n\n")
                    reasoning_delta_parts.append(rendered_reasoning)
                elif len(rendered_reasoning) > prev_len:
                    reasoning_delta_parts.append(rendered_reasoning[prev_len:])
                self._part_reasoning_sent[logic_id] = len(rendered_reasoning)

        return "".join(text_delta_parts), "".join(reasoning_delta_parts)

    def _render_full_output(self) -> tuple[str, str]:
        if not self._render_cache_dirty:
            return self._cached_full_text, self._cached_full_reasoning

        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        self._cached_part_texts.clear()
        self._cached_part_reasonings.clear()
        for logic_id in self.ordered_logic_ids:
            part = self.parts_by_logic_id.get(logic_id)
            if not isinstance(part, dict):
                continue
            content_items = part.get("content", [])
            if not isinstance(content_items, list):
                continue

            part_text: list[str] = []
            part_reasoning: list[str] = []
            for content in content_items:
                if not isinstance(content, dict):
                    continue
                item_type = content.get("type")
                if item_type == "text":
                    part_text.append(str(content.get("text", "")))
                elif item_type == "think":
                    part_reasoning.append(str(content.get("think", "")))
                elif item_type == "code":
                    part_text.append(f"```python\n{content.get('code', '')}\n```")
                elif item_type == "execution_output":
                    part_text.append(str(content.get("content", "")))
                elif item_type == "image":
                    images = content.get("image", [])
                    if isinstance(images, list):
                        for image in images:
                            if isinstance(image, dict) and image.get("image_url"):
                                part_text.append(f"![image]({image['image_url']})")

            rendered_text = "\n".join(filter(None, part_text)).strip()
            rendered_reasoning = "\n".join(filter(None, part_reasoning)).strip()
            if rendered_text:
                text_parts.append(rendered_text)
                self._cached_part_texts[logic_id] = rendered_text
            if rendered_reasoning:
                reasoning_parts.append(rendered_reasoning)
                self._cached_part_reasonings[logic_id] = rendered_reasoning

        self._cached_full_text = "\n\n".join(text_parts)
        self._cached_full_reasoning = "\n\n".join(reasoning_parts)
        self._render_cache_dirty = False
        return self._cached_full_text, self._cached_full_reasoning

    def _chunk_json(self, patch: dict[str, object]) -> str:
        payload = {
            "id": self.conversation_id,
            "object": "chat.completion.chunk",
            "created": self.created,
            "model": self.model,
        }
        payload.update(patch)
        return "data: " + safe_json_dumps(payload) + "\n\n"
