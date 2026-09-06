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
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


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


def _xml_escape_text(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _xml_wrap_scalar(value: object) -> str:
    if isinstance(value, str):
        return f"<![CDATA[{value.replace(']]>', ']]]]><![CDATA[>')}]]>"
    return safe_json_dumps(value)


def _safe_parameter_name(value: object) -> str:
    return re.sub(r"[^a-zA-Z0-9_.:-]", "_", str(value).strip()) or "value"


def _dsml_parameters_from_object(payload: object) -> str:
    if isinstance(payload, dict):
        parts: list[str] = []
        for key, value in payload.items():
            name = _xml_escape_text(_safe_parameter_name(key))
            parts.append(f'<|DSML|parameter name="{name}">{_dsml_parameters_from_object(value)}</|DSML|parameter>')
        return "".join(parts)
    if isinstance(payload, list):
        return "".join(f"<item>{_dsml_parameters_from_object(item)}</item>" for item in payload)
    return _xml_wrap_scalar(payload)


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
    return safe_json_dumps({"tool_call_id": str(tool_call_id or "unknown"), "name": tool_name, "result": content})


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
        "The following tool schemas are the only executable tool definitions for this turn.",
        "Ignore any tool names that are not listed below, even if they appear in prior context or model memory.",
        "You are connected through an OpenAI-compatible proxy. You do not have hidden browser, web, or URL-opening tools.",
        "Never call native tools such as `open_url`, `web.search`, `web.run`, `browser.open`, `browse`, `open_link`, `search`, or `find`.",
        "Do not output hidden reasoning, chain-of-thought, or labels such as `Thinking:`.",
        "Do not narrate tool selection, failed tool attempts, retries, fallback plans, or tool status banners.",
    ]

    if server_tools:
        lines.extend(
            [
                "",
                f"Server-side native tools (executed by backend automatically): {available_server_names}.",
                "When you need to call a server-side native tool, output a single structured JSON block with type 'tool_calls' in the assistant content.",
                'Format: {"type":"tool_calls","tool_calls":{"id":"call_<random_hex>","name":"TOOL_NAME","arguments":"<JSON_STRING>"}}',
                "The arguments field must be a JSON string (not a raw object). The server will intercept this block, execute the tool, and inject the result back into the stream as a tool message.",
                "Do not wrap server-side tool calls in DSML. Do not mix prose and the tool_calls JSON block in the same response.",
            ]
        )

    if xml_tools:
        lines.extend(
            [
                "",
                f"Executable tools (parsed by this server): {available_xml_names}.",
                "Only these tools are available. Use their exact names and exact parameter fields from the schemas.",
                "If a tool is needed, output ONE single JSON object and nothing else. Do not add prose, apologies, analysis, or progress text in the same assistant answer.",
                "The tool call must appear in the final assistant text channel, not in Thinking/reasoning. Do not hide tool calls inside reasoning.",
                "Use this exact format:",
                CANONICAL_TOOL_CALL_EXAMPLE,
                "The trailing [] after the JSON object is mandatory — it marks the end of the tool call. Output the JSON object, then immediately [].",
                "The server will parse the JSON block back into standard OpenAI tool_calls.",
                "Parameter rules:",
                "- The root is a single JSON object with one key \"tool_calls\" holding an array of calls.",
                "- Each call is an object with keys \"name\" (tool name string) and \"arguments\" (object of parameter name → value).",
                "- Parameter names are case-sensitive and must exactly match the schema. For example, use `filePath` only when the schema says `filePath`; never change it to `filepath`, `file_path`, or `FilePath`.",
                "- Values must be plain JSON values (strings, numbers, booleans, null, nested objects, arrays).",
                "- Output raw JSON only: no markdown fences, no code blocks, no comments, no trailing commas.",
            ]
        )

    lines.extend(
        [
            "",
            "Rules:",
            "- Do not invent tool names outside the declared list.",
            "- If a URL, browsing, or search action is needed, use only an explicitly listed client tool. If none is listed, explain that no such tool is available. Never use bare tool names `search` or `find` unless they are explicitly listed above.",
            "- If you decide to call a tool, call the selected tool directly; do not say you will try, switch, retry, or use a correct tool.",
            "- Never output tool-call display text such as `⚙ tool_name [...]`; output only the tool-call JSON.",
            "- After receiving a tool result, answer the user directly from the result and do not repeat the earlier tool-call decision process.",
            "- For the JSON tool format, do not emit XML, DSML markup, function_call objects, or any other tool syntax.",
            "- Do not mix normal explanation text with the tool-call JSON.",
            "- When you truly need multiple calls in one turn, put them all in the \"tool_calls\" array of one JSON object.",
        ]
    )
    if mode == "none":
        lines.extend(
            [
                "Tool choice policy: none.",
                "Do not emit any executable tool markup. Answer with normal text only.",
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
                f"You must call exactly `{specific_name}` before giving a final answer.",
                f"Do not call any tool other than `{specific_name}`.",
            ]
        )
    return "\n".join(lines)


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
