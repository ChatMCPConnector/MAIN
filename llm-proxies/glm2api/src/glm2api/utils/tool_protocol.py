from __future__ import annotations

import json
import re


BLOCKED_NATIVE_TOOL_NAMES = {
    "open",
    "open_url",
    "open_ul",
    "browser.open",
    "web.run",
    "web.open",
    "web.search",
    "web_search",
    "browse",
    "open_link",
}
SERVER_SIDE_TOOL_NAMES: set[str] = set()

CANONICAL_TOOL_CALL_EXAMPLE = (
    '{"tool_calls":[{"name":"TOOL_NAME","arguments":{"actual_parameter_name":"value"}}]}[]'
)


def safe_json_dumps(payload: object) -> str:
    json_str = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return json_str.replace("\n", "\\n").replace("\r", "\\r")


def normalize_tool_name(name: object) -> str:
    return str(name).strip()


def filter_tools(tools: list[dict[str, object]] | None, blocked_tool_names: set[str]) -> list[dict[str, object]] | None:
    if not tools:
        return None

    filtered_tools: list[dict[str, object]] = []
    for tool in tools:
        fn = tool.get("function", {})
        tool_name = normalize_tool_name(fn.get("name", ""))  # type: ignore[union-attr]
        if not tool_name or tool_name in blocked_tool_names:
            continue
        filtered_tools.append(tool)

    return filtered_tools or None


def serialize_tool_call_block(name: str, arguments: object) -> str:
    """Serialisiert einen Tool-Call im JSON-Protokoll (mit []-Terminator)."""
    parsed_arguments = arguments
    if isinstance(arguments, str):
        try:
            parsed_arguments = json.loads(arguments)
        except json.JSONDecodeError:
            parsed_arguments = {"raw": arguments}
    if not isinstance(parsed_arguments, dict):
        parsed_arguments = {"value": parsed_arguments}
    return safe_json_dumps({"tool_calls": [{"name": name, "arguments": parsed_arguments}]}) + "[]"


def serialize_tool_result_block(tool_call_id: object, tool_name: str, content: str) -> str:
    """Tool-Result als JSON-Nachricht (vom Translator in eine tool-Rolle gemappt)."""
    return safe_json_dumps(
        [{"call_id": str(tool_call_id or "unknown"), "name": tool_name, "content": content}]
    )

def build_tool_call_instructions(
    tool_names: list[str],
    server_side_tool_names: set[str] | None = None,
    tool_choice_policy: dict[str, object] | None = None,
) -> str:
    server_side_tool_names = server_side_tool_names or set()
    xml_tools = [name for name in tool_names if name not in server_side_tool_names]
    server_tools = [name for name in tool_names if name in server_side_tool_names]

    available_xml_names = ", ".join(f"`{name}`" for name in xml_tools) or "`(none)`"
    available_server_names = ", ".join(f"`{name}`" for name in server_tools) or "`(none)`"

    policy = tool_choice_policy or {"mode": "auto", "tool_name": None}
    mode = str(policy.get("mode", "auto"))
    specific_name = str(policy.get("tool_name", "") or "")

    lines = [
        "# TOOL USE PROTOCOL",
        f"Available tools: {available_xml_names}. No other tools exist — no browser, no open_url, no web.search.",
        "To call a tool, output this JSON format (and nothing else in the answer):",
        CANONICAL_TOOL_CALL_EXAMPLE,
        "Rules:",
        "- The trailing [] after the JSON object is MANDATORY: write the JSON, then immediately [].",
        "- Parameter names must exactly match the schema.",
        "- Multiple calls go in one \"tool_calls\" array.",
        "- Emit tool calls ONLY as this JSON — never as prose, XML, fences, or narration.",
    ]

    if mode == "none":
        lines.extend(
            [
                "Tool choice policy: none.",
                "Do not emit any tool-call JSON. Answer with normal text only.",
            ]
        )
    elif mode == "required":
        lines.extend(
            [
                "Tool choice policy: required.",
                "You must call at least one tool before giving a final answer.",
            ]
        )
    elif mode == "specific" and specific_name:
        lines.extend(
            [
                "Tool choice policy: specific function.",
                f"You must call exactly `{specific_name}`.",
            ]
        )
    return "\n".join(lines)


TOOL_FORMAT_REMINDER = (
    "[System instruction — highest priority]: To use a tool, output the JSON "
    "format from the TOOL USE PROTOCOL with the trailing [] — this is the ONLY "
    "way tools get executed. Prose, XML, or fenced blocks will NOT be executed. "
    "Call the tool now; do not describe or narrate it."
)


def tools_to_prompt(
    tools: list[dict[str, object]],
    blocked_tool_names: set[str] | None = None,
    tool_choice_policy: dict[str, object] | None = None,
    server_side_tool_names: set[str] | None = None,
) -> str:
    tool_names: list[str] = []
    tool_schemas: list[str] = []
    for tool in tools:
        fn = tool.get("function", {})
        name = str(fn.get("name", "unknown"))  # type: ignore[union-attr]
        description = str(fn.get("description", "") or "")  # type: ignore[union-attr]
        parameters = fn.get("parameters", {})  # type: ignore[union-attr]
        if blocked_tool_names and name in blocked_tool_names:
            continue
        tool_names.append(name)
        tool_schemas.append(
            "\n".join(
                [
                    f"Tool: {name}",
                    f"Description: {description}",
                    f"Parameters: {safe_json_dumps(parameters) if isinstance(parameters, dict) else '{}'}",
                ]
            )
        )

    parts = [
        "# TOOL SCHEMAS",
        "Treat the following schema list as the authoritative tool contract for this request.",
        "",
        "\n\n".join(tool_schemas),
        "",
        build_tool_call_instructions(
            tool_names,
            server_side_tool_names=server_side_tool_names,
            tool_choice_policy=tool_choice_policy,
        ),
    ]
    return "\n".join(part for part in parts if part is not None).strip()
