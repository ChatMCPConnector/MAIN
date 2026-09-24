from __future__ import annotations

import json
import logging
import re
import time
from bisect import insort
from collections.abc import Mapping
from dataclasses import dataclass, field
from logging import Logger
from typing import Any

from ..config import AppConfig
from ..logging_utils import debug_dump
from ..model_variants import model_requests_search, model_requests_thinking, split_model_features
from ..utils.tool_parser import CODE_FENCE_PATTERN, StreamingToolParser, detect_tool_call_names, parse_tool_calls_from_text, strip_unparseable_call_fragments
from ..utils.tool_protocol import (
    BLOCKED_NATIVE_TOOL_NAMES,
    CANONICAL_TOOL_CALL_EXAMPLE,
    TOOL_FORMAT_REMINDER,
    build_tool_call_instructions as _protocol_build_tool_call_instructions,
    filter_tools,
    safe_json_dumps,
    serialize_tool_call_block as _protocol_serialize_tool_call_block,
    serialize_tool_result_block as _protocol_serialize_tool_result_block,
    tools_to_prompt as _protocol_tools_to_prompt,
)

ASSISTANT_ID_PATTERN = re.compile(r"^[a-z0-9]{24,}$")
URL_PATTERN = re.compile(r"https?://[^\s<>()\"']+")

_LOGGER = logging.getLogger("glm2api.translator")

# THEMA 3 (optimierung.md): C0-Steuerzeichen ausser \n \t \r (plus DEL) sind
# in Tool-Argumenten und sichtbarem Content nie legitim — das Modell streamt
# sie gelegentlich alsEncoding-Verderb (z.B. 'zur\u0014ck' statt 'zurück').
_C0_ALLOWED = {"\n", "\t", "\r"}


def sanitize_control_characters(text: str) -> tuple[str, int]:
    """Ersetzt C0-Steuerzeichen (ausser \\n \\t \\r) und DEL durch '?'.

    Returns (bereinigter_text, anzahl_ersetzungen). Valides UTF-8 (echte
    Umlaute etc.) bleibt unangetastet."""
    if not text:
        return text, 0
    cleaned: list[str] = []
    replaced = 0
    for ch in text:
        code = ord(ch)
        if (code < 32 and ch not in _C0_ALLOWED) or code == 127:
            cleaned.append("?")
            replaced += 1
        else:
            cleaned.append(ch)
    if not replaced:
        return text, 0
    return "".join(cleaned), replaced


def _sanitize_value_control_chars(value: object) -> tuple[object, int, set[str]]:
    """Rekursiver C0-Sanitizer fuer geparste Tool-Argumente.
    Returns (bereinigter_wert, anzahl, gefundene_steuerzeichen)."""
    if isinstance(value, str):
        cleaned, count = sanitize_control_characters(value)
        if not count:
            return value, 0, set()
        chars = {ch for ch in value if (ord(ch) < 32 and ch not in _C0_ALLOWED) or ord(ch) == 127}
        return cleaned, count, chars
    if isinstance(value, list):
        cleaned_items: list[object] = []
        total = 0
        found: set[str] = set()
        for item in value:
            cleaned_item, count, chars = _sanitize_value_control_chars(item)
            cleaned_items.append(cleaned_item)
            total += count
            found |= chars
        return cleaned_items, total, found
    if isinstance(value, dict):
        cleaned_dict: dict[str, object] = {}
        total = 0
        found: set[str] = set()
        for key, item in value.items():
            cleaned_item, count, chars = _sanitize_value_control_chars(item)
            cleaned_dict[key] = cleaned_item
            total += count
            found |= chars
        return cleaned_dict, total, found
    return value, 0, set()



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

# JSON-Ersatzzeichen fuer den _raw-Repair-Pfad: single-pass, UTF-8-sicher.
# unicode_escape hat latin-1-semantik und macht aus 'ü' ein 'Ã¼' — deshalb
# hier JSON als primaeren Decoder und nur fuer harte Faelle einen
# regex-fallback fuer die haeufigsten escapes.
_ESCAPE_SEQ_RE = re.compile(r"\\(u[0-9a-fA-F]{4}|.)", re.DOTALL)
_JSON_UNESCAPES = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f"}


def _decode_escaped_text(raw: str) -> str:
    """Dekodiert JSON-Style-Escapes in einem Roh-String OHNE UTF-8 zu verderben."""
    try:
        decoded = json.loads(f'"{raw}"')
        if isinstance(decoded, str):
            return decoded
    except json.JSONDecodeError:
        pass

    def _sub(match: re.Match[str]) -> str:
        seq = match.group(1)
        if len(seq) == 5 and seq[0] == "u":
            try:
                return chr(int(seq[1:], 16))
            except ValueError:
                return match.group(0)
        return _JSON_UNESCAPES.get(seq, match.group(0))

    return _ESCAPE_SEQ_RE.sub(_sub, raw)


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


def repair_raw_tool_args(tool_name: str, raw_str: str) -> dict[str, object] | None:
    if tool_name in {"write", "edit"}:
        fp_match = re.search(r"\"filePath\"\s*:\s*\"([^\"]+)\"", raw_str)
        c_match = re.search(r"\"content\"\s*:\s*\"", raw_str)
        if fp_match and c_match:
            file_path = fp_match.group(1)
            content_start = c_match.end()
            content_end = raw_str.rfind('"')
            if content_end > content_start:
                return {"filePath": file_path, "content": _decode_escaped_text(raw_str[content_start:content_end])}
    elif tool_name in {"read"}:
        fp_match = re.search(r"\"filePath\"\s*:\s*\"([^\"]+)\"", raw_str)
        if fp_match:
            return {"filePath": fp_match.group(1)}
    elif tool_name in {"bash", "shell"}:
        cmd_match = re.search(r"\"command\"\s*:\s*\"", raw_str)
        if cmd_match:
            cmd_start = cmd_match.end()
            cmd_end = raw_str.rfind('"')
            if cmd_end > cmd_start:
                return {"command": _decode_escaped_text(raw_str[cmd_start:cmd_end])}
    return None


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

    cleaned: dict[str, Any] = {str(key): value for key, value in parsed_arguments.items()}
    if "_raw" in cleaned and isinstance(cleaned["_raw"], str):
        repaired_raw = repair_raw_tool_args(tool_name, cleaned["_raw"])
        if repaired_raw is not None:
            cleaned = repaired_raw
    if cleaned == {"param_name": "url"} and fallback_url:
        cleaned = {"url": fallback_url}
    elif cleaned == {"param_name": "url"}:
        cleaned = {}
    if "param_name" in cleaned and "param_value" not in cleaned and len(cleaned) == 1:
        cleaned = {}

    if "filePath" in cleaned and isinstance(cleaned["filePath"], str):
        fp = cleaned["filePath"].strip()
        while fp.startswith("file://"):
            fp = fp[7:]
        while fp.startswith("file:/"):
            fp = fp[6:]
        if fp.startswith("workspaces/"):
            fp = "/" + fp
        elif fp.startswith("benchmark/"):
            fp = "/workspaces/" + fp
        elif fp == "benchmark.md":
            fp = "/workspaces/benchmark.md"
        cleaned["filePath"] = fp

    # Repair: stringified JSON arrays or objects inside parameters (e.g. questions: "[{...}]")
    # Ausgenommen write/edit: deren Textinhalte (content, newString, oldString) MÜSSEN Strings bleiben.
    if tool_name not in {"write", "edit"}:
        for key, val in list(cleaned.items()):
            if isinstance(val, str):
                stripped_val = val.strip()
                if (stripped_val.startswith("[") and stripped_val.endswith("]")) or (
                    stripped_val.startswith("{") and stripped_val.endswith("}")
                ):
                    try:
                        parsed_nested = json.loads(stripped_val)
                        if isinstance(parsed_nested, (dict, list)):
                            cleaned[key] = parsed_nested
                    except json.JSONDecodeError:
                        pass

    # Sicherheitsnetz fuer write/edit: falls das Modell ein Dictionary/Array direkt
    # als content/newString/oldString uebergeben hat, in einen formatierten JSON-String serialisieren
    if tool_name in {"write", "edit"}:
        for str_key in ("content", "newString", "oldString"):
            val = cleaned.get(str_key)
            if val is not None and not isinstance(val, str):
                cleaned[str_key] = json.dumps(val, indent=2, ensure_ascii=False)

    if tool_name in {"bash", "shell", "run", "execute"}:
        command = cleaned.get("command")
        if isinstance(command, str):
            # Quote-Repair fuer python-commands (compile-oracle-geprüft)
            stripped = command.strip()
            if re.match(r"^(python3?|pypy3?)\s", stripped):
                cleaned["command"] = repair_python_command_quotes(command)

    # THEMA 3 (F1): C0-Steuerzeichen in den Argumenten ersetzen + loggen.
    sanitized_value, control_count, control_chars = _sanitize_value_control_chars(cleaned)
    if control_count:
        cleaned = sanitized_value  # type: ignore[assignment]
        _LOGGER.warning(
            "Sanitized control characters in tool call arguments tool=%s count=%s chars=%s",
            tool_name,
            control_count,
            sorted(repr(ch) for ch in control_chars),
        )

    return cleaned


def map_native_open_tool_call(
    arguments: object,
    allowed_tool_names: set[str] | None = None,
) -> tuple[str, dict[str, object]] | None:
    """Maps ChatGLM's native open(ref_id=...) call to an allowed OpenCode tool
    (read or webfetch) if the target is a valid path or URL.
    Returns (mapped_tool_name, mapped_arguments) or None if unmappable."""
    parsed = arguments
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return None
    if not isinstance(parsed, dict):
        return None

    command = ""
    target = ""
    open_list = parsed.get("open")
    if isinstance(open_list, list) and open_list:
        first = open_list[0]
        if isinstance(first, dict):
            command = str(first.get("command", "") or first.get("cmd", "") or "").strip()
            target = str(first.get("ref_id", "") or first.get("url", "") or first.get("path", "")).strip()
    if not command:
        command = str(parsed.get("command", "") or parsed.get("cmd", "") or "").strip()
    if command:
        if allowed_tool_names is None or "bash" in allowed_tool_names:
            return "bash", {"command": command}

    if not target:
        target = str(parsed.get("ref_id", "") or parsed.get("url", "") or parsed.get("path", "") or parsed.get("file", "")).strip()

    if not target:
        return None

    if target.startswith("http://") or target.startswith("https://"):
        if allowed_tool_names is None or "webfetch" in allowed_tool_names:
            return "webfetch", {"url": target}

    if not target.startswith("turn") and ("/" in target or target.startswith(".") or "." in target):
        if allowed_tool_names is None or "read" in allowed_tool_names:
            return "read", {"filePath": target}

    return None


_DUMMY_SANDBOX_PATTERNS = {
    "placeholder",
    "raise systemexit",
    "true",
    "pass",
    "noop",
    "no-op",
    "none",
    "exit()",
    "sys.exit()",
    "1",
    "0",
}

_META_CHATTER_KEYWORDS = (
    "execute_sandbox_code ist",
    "execute_sandbox_code calls",
    "open ist kein",
    "open ist nicht",
    "open ist für",
    "fehler meinerseits",
    "fehler erkannt: open",
    "fehler erkannt: execute_sandbox",
    "kein weiteres open",
    "ich stoppe die open",
    "dieser aufruf war fehlerhaft",
    "wechsle auf das datei-tool",
    "tool call attempt:",
    "the tool(s) `open` do not exist",
    "the tool(s) `execute_sandbox_code` do not exist",
)

# Das Modell halluziniert gelegentlich das eigene konversations-format:
# "User: [{"call_id": "...", "name": "read", "content": "..."}]" — das ist die
# interne transcript-repraesentation aus dem prompt, nie eine echte antwort.
_TRANSCRIPT_ECHO_RE = re.compile(
    r'^\s*(?:User|Assistant)\s*:\s*(?:\[\s*\{\s*"(?:call_id|name|content|arguments)"'
    r'|\{\s*"(?:call_id|name|content|arguments|tool_calls)")',
)


def strip_transcript_echo(text: str) -> str:
    """Entfernt halluzinierte konversations-transcript-zeilen des modells
    ('User: [{"call_id": ...}]'). Das ist immer eine halluzination, nie eine
    echte antwort — daher unabhaengig von vorhandenen tool-calls anwendbar."""
    if not text:
        return ""
    lines = text.splitlines(keepends=True)
    kept_lines = []
    for line in lines:
        if _TRANSCRIPT_ECHO_RE.search(line):
            continue
        kept_lines.append(line)
    return "".join(kept_lines).strip()


def strip_meta_chatter(text: str) -> str:
    """Strips self-apology and meta-commentary sentences about failed/blocked tools
    and the model's own hallucinated conversation transcript (User:/Assistant: lines
    echoing the internal tool-result format)."""
    if not text:
        return ""
    lines = text.splitlines(keepends=True)
    kept_lines = []
    for line in lines:
        lower = line.lower()
        if any(kw in lower for kw in _META_CHATTER_KEYWORDS):
            continue
        if lower.strip() in {"read", "read read", "read\nread", "open", "write"}:
            continue
        if _TRANSCRIPT_ECHO_RE.search(line):
            continue
        kept_lines.append(line)
    return "".join(kept_lines).strip()


def _extract_code_like(parsed: Mapping[str, object]) -> str:
    return str(
        parsed.get("code", "")
        or parsed.get("command", "")
        or parsed.get("script", "")
        or parsed.get("input", "")
        or ""
    ).strip()


def is_dummy_sandbox_code(arguments: object) -> bool:
    """Detects self-chastising or dummy no-op code snippets emitted by GLM."""
    parsed = arguments
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            parsed = {"code": arguments}
    if not isinstance(parsed, dict):
        return False
    code = _extract_code_like(parsed).lower()
    if not code:
        return True
    if code in _DUMMY_SANDBOX_PATTERNS:
        return True
    if code.startswith("print(") and code.endswith(")"):
        inner = code[6:-1].strip("'\" \t")
        keywords = (
            "stop",
            "noop",
            "no-op",
            "switching",
            "wrong tool",
            "unused",
            "stopped",
            "acknowledge",
            "switch to",
            "sandbox",
            "proper tools",
            "misuse",
            "proper tool",
        )
        if any(kw in inner for kw in keywords) or not inner:
            return True
    return False


def map_native_sandbox_tool_call(
    arguments: object,
    allowed_tool_names: set[str] | None = None,
) -> tuple[str, dict[str, object]] | None:
    """Maps ChatGLM's native execute_sandbox_code(code=...) call to bash
    if bash is allowed. Runs python3 with the provided code.
    Returns (mapped_tool_name, mapped_arguments) or None if unmappable."""
    if is_dummy_sandbox_code(arguments):
        return None
    if allowed_tool_names is not None and "bash" not in allowed_tool_names:
        return None

    parsed = arguments
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return None
    if not isinstance(parsed, dict):
        return None

    code = _extract_code_like(parsed)

    if not code:
        return None

    first_word = code.split()[0] if code.split() else ""
    if first_word in {"pytest", "python", "python3", "pip", "uv", "ls", "cd", "cat", "mkdir", "find", "grep"}:
        bash_command = code
    else:
        bash_command = f"python3 - << 'EOF'\n{code}\nEOF"

    return "bash", {"command": bash_command}


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
        if tool_name == "open":
            mapped = map_native_open_tool_call(original_arguments)
            if mapped is not None:
                tool_name, mapped_args = mapped
                original_arguments = mapped_args
                original_value = mapped_args
        elif tool_name in {"execute_sandbox_code", "code_interpreter", "sandbox", "run_code"}:
            if is_dummy_sandbox_code(original_arguments):
                continue
            mapped = map_native_sandbox_tool_call(original_arguments)
            if mapped is not None:
                tool_name, mapped_args = mapped
                original_arguments = mapped_args
                original_value = mapped_args
            else:
                continue
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
        if tool_name == "write":
            if not isinstance(cleaned_arguments, dict) or not cleaned_arguments.get("filePath") or "content" not in cleaned_arguments:
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


def compress_history_messages(
    messages: list[dict[str, object]],
    max_total_chars: int,
) -> list[dict[str, object]]:
    """H1/THEMA 1 aus optimierung.md: chatglm.cn driftet bei aufgeblähter
    request-historie (loops, missdeutungen ab ~150k token) — auch wenn das
    modell nominell mehr kann. Die serverseitige Komprimierung hält den Kontext
    stundenlang stabil.

    Strategie hier (konfigurierbar via GLM_HISTORY_MAX_CHARS, default 120k
    chars, 0 = aus): die messages-liste wird von NEU nach ALT gesammelt bis
    das budget ausgeschöpft ist; alles ältere wird zu EINEM summarischen
    eintrag verdichtet ("system" → user-transkript), tool-JSON überlebt
    unangetastet im erhaltenen teil. Wichtig:Paarweise assistant-tool-nachrichten
    nie auseinanderreissen — ein tool-result ohne seinen call verwirrt das
    modell, ein call ohne result führt zu phantom-erwartungen.
    """
    if max_total_chars <= 0:
        return messages

    def _msg_size(message: dict[str, object]) -> int:
        content = message.get("content")
        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False) if content else ""
        size = len(text)
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list):
            size += len(json.dumps(tool_calls, ensure_ascii=False))
        return size

    total = sum(_msg_size(m) for m in messages)
    if total <= max_total_chars:
        return messages

    # von hinten (neueste) sammeln, paare intakt lassen. first_kept ist der
    # index der ersten roh erhaltenen message; die message, die das budget
    # sprengt, faellt in die summary — ausnahme: ist sie die neueste
    # ueberhaupt (kept leer), bleibt sie roh (sonst wuerde die aktuelle
    # frage wegsummarisiert).
    kept: list[dict[str, object]] = []
    running = 0
    first_kept = len(messages)
    i = len(messages) - 1
    while i >= 0:
        message = messages[i]
        size = _msg_size(message)
        role = str(message.get("role", ""))
        if role == "tool" and kept and i > 0:
            # tool-result gehört zum vorherigen assistant-call: nur zusammen
            # behalten oder zusammen verwerfen (assistant davor prüfen)
            prev = messages[i - 1]
            prev_role = str(prev.get("role", ""))
            if prev_role == "assistant" and prev.get("tool_calls"):
                size += _msg_size(prev)
                if running + size > max_total_chars:
                    first_kept = i + 1
                    break
                kept.insert(0, prev)
                kept.insert(1, message)
                running += size
                i -= 2
                continue
        if running + size > max_total_chars:
            first_kept = i if not kept else i + 1
            break
        kept.insert(0, message)
        running += size
        i -= 1

    if first_kept <= 0 or first_kept >= len(messages):
        return messages
    dropped = messages[:first_kept]
    # summary-budget: die snippets duerfen das gesamt-budget nicht sprengen —
    # jede gedroppte message maximal budget/8 zeichen, gesamt gedeckelt.
    per_snippet = max(120, max_total_chars // 8)
    summary_budget = max(1000, max_total_chars // 2)
    summary_parts: list[str] = []
    summary_len = 0
    for message in dropped:
        role = str(message.get("role", "user"))
        content = message.get("content")
        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False) if content else ""
        if role == "assistant" and message.get("tool_calls"):
            text = (text or "") + " " + json.dumps(message.get("tool_calls"), ensure_ascii=False)
        snippet = text[:per_snippet]
        part = f"{role}: {snippet}"
        if summary_len + len(part) > summary_budget:
            break
        summary_parts.append(part)
        summary_len += len(part)
    summary = (
        "[Conversation history summary — earlier messages were compacted. "
        "The full recent conversation follows below.] "
        + " | ".join(summary_parts)
    )
    summary_entry: dict[str, object] = {"role": "user", "content": summary}
    return [summary_entry] + list(messages[first_kept:])


def convert_messages(
    messages: list[dict[str, object]],
    tools: list[dict[str, object]] | None,
    blocked_tool_names: set[str] | None = None,
    tool_choice: object | None = None,
) -> list[dict[str, object]]:
    tools = filter_tools(tools, blocked_tool_names or set())
    available_tool_names = {
        str(tool.get("function", {}).get("name", "")).strip()
        for tool in (tools or [])
        if isinstance(tool, dict) and isinstance(tool.get("function"), dict)
    }
    available_tool_names.discard("")
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
    # Re-Anchor: am Prompt-Ende verankern, damit das Modell auch nach extrem
    # langem Reasoning (60k+ Tokens im max/deep_thinking Modus) oder Tool-Result-Runden
    # sofort mit dem JSON-Tool-Call startet statt in Prosa/Plaene abzudriften.
    if tools and tool_choice_policy.get("mode") != "none":
        prompt = prompt + "\n\n" + TOOL_FORMAT_REMINDER
    return [{"role": "user", "content": [{"type": "text", "text": prompt + "\n\nAssistant: "}]}]


def resolve_upstream_model(requested_model: str, config: AppConfig) -> tuple[str, str]:
    """Base-Modell (ohne think/search-Suffixe) + assistant_id (falls das
    Modell selbst eine 24-stellige hex-id ist, wird sie als assistant_id
    interpretiert)."""
    base_model, _ = split_model_features(requested_model)
    assistant_id = base_model if ASSISTANT_ID_PATTERN.fullmatch(base_model) else config.glm_assistant_id
    return base_model, assistant_id


# Reasoning levels: real chat_mode values of the chatglm.cn web UI (verified
# via CDP reverse engineering 2026-09-07):
#   ""             = quick (no thinking)
# chat_mode values for GLM upstream API:
#   ""              = quick (no thinking)
#   "thinking"      = standard thinking (fast CoT, ~7s)
#   "deep_research" = autonomous multi-turn web research
# Hinweis: "deep_thinking" ist der ChatGLM-Web-Research-Modus (verursacht Latenzen
# und Fails durch interne Web-Scraper-Schleifen). Daher mappt "max" direkt auf "thinking".
CHAT_MODE_THINKING = "thinking"

_EFFORT_TO_CHAT_MODE = {
    # low    = quick (no thinking)
    # medium = thinking (standard thinking)
    # high   = thinking (standard thinking)
    # max    = thinking (standard thinking)
    "low": "",
    "minimal": "",
    "medium": CHAT_MODE_THINKING,
    "high": CHAT_MODE_THINKING,
    "max": CHAT_MODE_THINKING,
}


def resolve_chat_mode(model: str, reasoning_effort: object, deep_research: object, has_tools: bool = False) -> str:
    lower_model = (model or "").lower()
    if deep_research or "deepresearch" in lower_model or "deep-research" in lower_model:
        return "deep_research"
    # Explizite Stufe (reasoning_effort) übersetzt in den UI-Wert.
    if isinstance(reasoning_effort, str) and reasoning_effort.lower() in _EFFORT_TO_CHAT_MODE:
        return _EFFORT_TO_CHAT_MODE[reasoning_effort.lower()]
    if reasoning_effort:
        return CHAT_MODE_THINKING
    if model_requests_thinking(model) or "think" in lower_model or "zero" in lower_model:
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
    prompt_chars: int = 0
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

    def is_empty_response(self) -> bool:
        """True when a round has no client-visible result or tool call.

        Reasoning alone is not a usable response: OpenCode stores it as an
        internal thinking part and otherwise treats the turn as a successful
        stop, leaving an executing agent unable to continue.
        """
        text, _ = self.render_full_output()
        has_calls = bool(self._server_side_tool_calls or self.tool_parser.tool_calls)
        has_blocked = bool(self.blocked_tool_attempt_names)
        return not text.strip() and not has_calls and not has_blocked

    def render_full_output(self) -> tuple[str, str]:
        """Public: (volltext, reasoning) — u.a. fuer follow-up-renders."""
        return self._render_full_output()

    def _estimated_usage(self, completion_chars: int) -> dict[str, int]:
        """Grobe Token-Schaetzung (~4 Zeichen/Token): der Upstream liefert
        keine echten Usage-Zahlen, aber 1/1/2-Platzhalter verwirren jedes
        Kosten-Tracking im Client."""
        prompt_tokens = max(1, self.prompt_chars // 4)
        completion_tokens = max(1, completion_chars // 4)
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }

    def _completion_chars(self, final_text: str, all_tool_calls: list[dict[str, object]]) -> int:
        chars = len(final_text) + len(self._cached_full_reasoning)
        for tool_call in all_tool_calls:
            function = tool_call.get("function", {})
            if isinstance(function, dict):
                chars += len(str(function.get("name", ""))) + len(str(function.get("arguments", "")))
        return chars

    def _sanitize_visible_text(self, final_text: str) -> str:
        """THEMA 3 (F2): C0-Steuerzeichen im sichtbaren Content ersetzen."""
        cleaned, count = sanitize_control_characters(final_text)
        if count:
            log = self.logger or _LOGGER
            log.warning("Sanitized %s control character(s) in visible response text", count)
        return cleaned

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
            # Intercept server-side tool calls from meta_data or content items
            meta = part.get("meta_data") if isinstance(part, dict) else None
            if isinstance(meta, dict):
                extra = meta.get("tool_result_extra")
                if isinstance(extra, dict):
                    tool_call_name = str(extra.get("tool_call_name", "")).strip()
                    if tool_call_name.lower() in {"finish", "intervene", "cancel", "none", "open", "execute_sandbox_code", "code_interpreter", "sandbox", "run_code"}:
                        pass
                    elif tool_call_name in BLOCKED_NATIVE_TOOL_NAMES:
                        if tool_call_name not in self.blocked_tool_attempt_names:
                            self.blocked_tool_attempt_names.append(tool_call_name)
                        if self.logger:
                            self.logger.warning(
                                "Intercepted blocked native tool call in meta_data tool=%s, triggering immediate intervene",
                                tool_call_name,
                            )
                        return [], "intervene"

            # Extract server-side native tool_calls from content items
            if isinstance(part, dict) and isinstance(part.get("content"), list):
                for content in part["content"]:
                    if isinstance(content, dict) and content.get("type") == "tool_calls":
                        tool_calls_data = content.get("tool_calls")
                        if isinstance(tool_calls_data, dict):
                            tool_name = str(tool_calls_data.get("name", "")).strip()
                            tool_id = str(tool_calls_data.get("id", "")).strip()
                            arguments = tool_calls_data.get("arguments", "{}")
                            if tool_name.lower() in {"finish", "intervene", "cancel", "none"}:
                                continue
                            if tool_name == "open":
                                mapped = map_native_open_tool_call(arguments, self.allowed_tool_names)
                                if mapped is not None:
                                    mapped_name, mapped_args = mapped
                                    tool_name = mapped_name
                                    arguments = mapped_args
                                    if self.logger:
                                        self.logger.info(
                                            "Mapped native open tool call to %s args=%s",
                                            tool_name,
                                            mapped_args,
                                        )
                            elif tool_name in {"execute_sandbox_code", "code_interpreter", "sandbox", "run_code"}:
                                if is_dummy_sandbox_code(arguments):
                                    if self.logger:
                                        self.logger.info(
                                            "Dropped dummy sandbox self-talk call args=%s",
                                            arguments,
                                        )
                                    continue
                                mapped = map_native_sandbox_tool_call(arguments, self.allowed_tool_names)
                                if mapped is not None:
                                    mapped_name, mapped_args = mapped
                                    tool_name = mapped_name
                                    arguments = mapped_args
                                    if self.logger:
                                        self.logger.info(
                                            "Mapped native sandbox tool call to %s args=%s",
                                            tool_name,
                                            mapped_args,
                                        )
                            if self.allowed_tool_names is not None and tool_name not in self.allowed_tool_names:
                                if tool_name not in self.blocked_tool_attempt_names:
                                    self.blocked_tool_attempt_names.append(tool_name)
                                if tool_name in BLOCKED_NATIVE_TOOL_NAMES:
                                    if self.logger:
                                        self.logger.warning(
                                            "Intercepted blocked native tool call tool=%s, triggering immediate intervene",
                                            tool_name,
                                        )
                                    return [], "intervene"
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
            # THEMA 3 (F2): C0-Steuerzeichen im gestreamten Content ersetzen
            visible_text_delta = self._sanitize_visible_text(visible_text_delta)
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
            # nur wenn das GESAMTE fence dem protokoll entspricht
            # (trailing []-terminator + whitespace ist ok)
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
        all_tool_calls = sanitize_tool_calls(all_tool_calls, fallback_url=self.fallback_tool_url)

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
            # Safety-net (Live-Fall 2026-09-24, ses_f2bc23762ffeoOkPYHAoqhwpwm):
            # der upstream brach mitten im call-json ab — das fragment ist
            # unparsebar und wurde vom parser zurueckgehalten, wuerde hier
            # aber als sichtbarer text durchgehen. Nie eine antwort.
            final_text, fragment_count = strip_unparseable_call_fragments(final_text)
            if fragment_count:
                log = self.logger or _LOGGER
                log.warning(
                    "Stripped %s unparseable tool-call fragment(s) from final text "
                    "(upstream stream ended mid-JSON)",
                    fragment_count,
                )
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
                    and name.lower() not in {"finish", "intervene", "cancel", "none"}
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
        if final_text:
            final_text = self._sanitize_visible_text(final_text)
            # Halluziniertes eigenes konversations-format (User:/Assistant: mit
            # [{"call_id":...}]) ist nie eine echte antwort — hier sind die
            # zeilen vollstaendig, deshalb erst hier strippen.
            stripped_echo = strip_transcript_echo(final_text)
            if stripped_echo != final_text:
                log = self.logger or _LOGGER
                log.warning(
                    "Stripped %s hallucinated transcript-echo line(s) from final text",
                    final_text.count("\n") - stripped_echo.count("\n") or 1,
                )
                final_text = stripped_echo
            if all_tool_calls:
                final_text = strip_meta_chatter(final_text)
            elif strip_meta_chatter(final_text) == "":
                final_text = ""
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
            intervene_text = self._sanitize_visible_text(str(last_error["intervene_text"]))
            chunks.append(
                self._chunk_json(
                    {
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": "\n\n" + intervene_text},
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

        if not all_tool_calls and not final_text.strip() and self.blocked_tool_attempt_names:
            blocked_names = ", ".join(sorted(set(self.blocked_tool_attempt_names)))
            fallback_content = (
                "The model attempted to call an unavailable tool "
                f"({blocked_names}) and returned no final response."
            )
            if self.logger:
                self.logger.warning(
                    "Replacing empty streaming response after blocked tool attempts: %s",
                    blocked_names,
                )
            chunks.append(
                self._chunk_json(
                    {
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": fallback_content},
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
                    "usage": self._estimated_usage(self._completion_chars(final_text, all_tool_calls)),
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
        clean_content, fragment_count = strip_unparseable_call_fragments(clean_content)
        if fragment_count:
            log = self.logger or _LOGGER
            log.warning(
                "Stripped %s unparseable tool-call fragment(s) from non-streaming response text",
                fragment_count,
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
                and name.lower() not in {"finish", "intervene", "cancel", "none"}
            )

        # Merge server-side and XML tool calls, re-indexing; wie in finalize()
        # auch die gemergte liste sanitizen (reparatur + C0-filter, paritaet
        # zum stream-pfad)
        all_tool_calls: list[dict[str, object]] = list(self._server_side_tool_calls)
        for tc in xml_tool_calls:
            tc_copy = dict(tc)
            tc_copy["index"] = len(all_tool_calls)
            all_tool_calls.append(tc_copy)
        all_tool_calls = sanitize_tool_calls(all_tool_calls, fallback_url=self.fallback_tool_url)

        final_content = self._sanitize_visible_text(clean_content.strip())
        stripped_echo = strip_transcript_echo(final_content)
        if stripped_echo != final_content:
            log = self.logger or _LOGGER
            log.warning("Stripped hallucinated transcript-echo line(s) from non-streaming response text")
            final_content = stripped_echo
        if not all_tool_calls and not final_content and self.blocked_tool_attempt_names:
            blocked_names = ", ".join(sorted(set(self.blocked_tool_attempt_names)))
            final_content = (
                "The model attempted to call an unavailable tool "
                f"({blocked_names}) and returned no final response."
            )
            if self.logger:
                self.logger.warning(
                    "Replacing empty non-streaming response after blocked tool attempts: %s",
                    blocked_names,
                )
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
            "usage": self._estimated_usage(self._completion_chars(final_content or "", all_tool_calls)),
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
