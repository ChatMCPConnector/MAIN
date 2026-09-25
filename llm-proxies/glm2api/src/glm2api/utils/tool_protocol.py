from __future__ import annotations

import json
import re
import unicodedata


BLOCKED_NATIVE_TOOL_NAMES = {
    "open",
    "open_url",
    "open_ul",
    "browser.open",
    "web.run",
    "web.open",
    "browse",
    "open_link",
    "web_search",
    "web.search",
    "execute_sandbox_code",
    "code_interpreter",
    "sandbox",
    "run_code",
}

CANONICAL_TOOL_CALL_EXAMPLE = (
    '{"tool_calls":[{"name":"TOOL_NAME","arguments":{"actual_parameter_name":"value"}}]}[]'
)

def safe_json_dumps(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def normalize_tool_name(name: object) -> str:
    return str(name).strip()


def policy_tool_key(name: object) -> str:
    """Kanonischer Schluessel fuer ALLE sicherheits-/sperr-vergleiche (A-13).

    Vorher wurde nur `strip()` verglichen — dadurch umgingen `OPEN_URL`,
    `Browser.Open`, `Execute_Sandbox_Code` und `web.run_v2` die native
    sperre, sobald ein client eine abweichende schreibweise deklariert hat.

    Kanonisiert werden: unicode-NFKC, casefold, punkte/Leerzeichen zu `_`
    und Versions-/Trailing-Suffixe. Der ORIGINAL-API-name bleibt unberuehrt:
    `normalize_tool_name()` wird weiterhin fuer den wire-format verwendet."""
    text = unicodedata.normalize("NFKC", str(name)).strip().casefold()
    text = re.sub(r"[\s.\-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    # `web.run_v2`, `open_url-2`, `browse_v1` sind dieselbe faehigkeit.
    return re.sub(r"_(?:v\d+|version\d+|\d+)$", "", text)


# Vorberechnete kanonische schluessel der nativen sperre (A-13).
_NATIVE_BLOCK_KEYS = frozenset(policy_tool_key(name) for name in BLOCKED_NATIVE_TOOL_NAMES)


def is_blocked_tool_name(name: object, blocked_tool_names: set[str] | None) -> bool:
    """Trifft der (normalisierte) Name die native sperre oder eine
    konfigurierte blockliste? Beide Seiten werden ueber `policy_tool_key`
    verglichen, damit schreibweise und version keine umgehung sind."""
    if name in BLOCKED_NATIVE_TOOL_NAMES:
        return True
    key = policy_tool_key(name)
    if key in _NATIVE_BLOCK_KEYS:
        return True
    if not blocked_tool_names:
        return False
    return any(policy_tool_key(blocked) == key for blocked in blocked_tool_names)


def filter_tools(tools: list[dict[str, object]] | None, blocked_tool_names: set[str]) -> list[dict[str, object]] | None:
    if not tools:
        return None

    filtered_tools: list[dict[str, object]] = []
    for tool in tools:
        fn = tool.get("function", {})
        tool_name = normalize_tool_name(fn.get("name", ""))  # type: ignore[union-attr]
        if not tool_name or is_blocked_tool_name(tool_name, blocked_tool_names):
            continue
        filtered_tools.append(tool)

    return filtered_tools or None


def serialize_tool_call_block(name: str, arguments: object) -> str:
    """Serialisiert einen Tool-Call im JSON-Protokoll (mit []-Terminator).

    A-14: bei kaputtem argument-json wurde `{"raw": arguments}` erfunden. Beim
    History-Roundtrip sieht das Modell daraus einen Call mit einem *echten*
    parameter `raw` — der Aufruf wird mit anderen Argumenten erneut
    ausgeführt, und das Modell hält `raw` für eine Fähigkeit des Tools.
    Stattdessen wird ein nicht darstellbares Argument-Objekt als
    `_unusable_args`-markiert: das Modell erkennt den defekten Zustand und
    kann den Call korrigieren, statt ihn mit erfundener Semantik zu spiegeln.
    """
    parsed_arguments = arguments
    if isinstance(arguments, str):
        try:
            parsed_arguments = json.loads(arguments)
        except json.JSONDecodeError:
            parsed_arguments = {"_unusable_args": arguments}
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
    tool_choice_policy: dict[str, object] | None = None,
) -> str:
    available_names = ", ".join(f"`{name}`" for name in tool_names) or "`(none)`"

    policy = tool_choice_policy or {"mode": "auto", "tool_name": None}
    mode = str(policy.get("mode", "auto"))
    specific_name = str(policy.get("tool_name", "") or "")

    blocked_examples = ", ".join(f"`{n}`" for n in sorted(BLOCKED_NATIVE_TOOL_NAMES))

    lines = [
        "# TOOL USE PROTOCOL",
        "",
        "## Allowed tools (EXHAUSTIVE list — no others exist)",
        f"Available tools: {available_names}. No other tools exist — no browser, no open_url, no web.search, no execute_sandbox_code.",
        "Only the tools listed above exist in this environment. Do not attempt to call any other tools.",
        "Before emitting any tool call, verify the tool name appears in the allowed list above. When a task requires tools (e.g. inspecting directories, creating files, running commands), you MUST call the appropriate allowed tool (e.g. bash, write). Never describe actions in prose instead of calling the tool.",
        "",
        "## Filesystem, Code Execution & Web Rules",
        "- For filesystem operations (inspecting, listing, or creating directories like `/workspaces`, reading/writing files), you MUST use `bash` (e.g. `ls`, `mkdir`) or `read`/`write`. NEVER attempt to call `open` on directory paths or files — `open` is NOT a filesystem tool and will fail.",
        "- For executing Python, running tests (pytest), or executing code, you MUST use `bash` (e.g. `python3 -m pytest ...`, `python3 script.py`). NEVER attempt to call `execute_sandbox_code`, `code_interpreter`, or any sandbox tool — no sandbox tools exist in this environment.",
        "- For web requests, use `webfetch` (if available). Never call `open`, `open_url`, or `browser`.",
        "",
        "## Call format",
        "To call a tool, output this JSON format (and nothing else in the answer):",
        CANONICAL_TOOL_CALL_EXAMPLE,
        "",
        "## Rules",
        "- The trailing [] after the JSON object is MANDATORY: write the JSON, then immediately [].",
        "- Parameter names must exactly match the schema.",
        "- Multiple calls go in one \"tool_calls\" array.",
        "- Emit tool calls ONLY as this JSON — never as prose, XML, fences, or narration.",
        "- When calling a tool, do NOT output conversational text, internal thoughts, or preamble before or after the JSON. Start directly with the JSON.",
        "- Language consistency: Always think and respond in the language of the conversation (e.g. German, English). NEVER output internal monologue, reasoning, or responses in Chinese unless explicitly prompted in Chinese.",
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
    "[System instruction — highest priority]: When the user task requires inspecting, creating, "
    "or editing files, running commands, or calling any tool, you MUST IMMEDIATELY output the JSON "
    "format from the TOOL USE PROTOCOL with the trailing [] — this is the ONLY way tools get executed. "
    "For filesystem operations (like inspecting/creating /workspaces), use `bash` or `read`/`write` — NEVER call `open`. "
    "For running Python scripts or pytest, use `bash` — NEVER call `execute_sandbox_code`. "
    "Do NOT output plans, summaries, or descriptions in prose instead of calling the tool. "
    "Prose, XML, or fenced blocks will NOT be executed. "
    "NEVER call tools that are not in the allowed list (such as execute_sandbox_code, open, open_url, web_search). "
    "If you need information from a URL, use an allowed tool or tell the user — do NOT invent a tool. "
    "Do not output any preamble, commentary, or thoughts in Chinese or any other language before the tool call. "
    "If answering the user directly (only when no tools are needed), provide the answer in the conversation language (e.g. German)."
)


def tools_to_prompt(
    tools: list[dict[str, object]],
    blocked_tool_names: set[str] | None = None,
    tool_choice_policy: dict[str, object] | None = None,
) -> str:
    tool_names: list[str] = []
    tool_schemas: list[str] = []
    for tool in tools:
        fn = tool.get("function", {})
        name = str(fn.get("name", "unknown"))  # type: ignore[union-attr]
        description = str(fn.get("description", "") or "")  # type: ignore[union-attr]
        parameters = fn.get("parameters", {})  # type: ignore[union-attr]
        if blocked_tool_names and is_blocked_tool_name(name, blocked_tool_names):
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
        "Treat the following schema list as the COMPLETE and EXHAUSTIVE tool contract for this request.",
        "No tools exist beyond what is listed here. Do not guess, infer, or invent any tool names.",
        "",
        "\n\n".join(tool_schemas),
        "",
        build_tool_call_instructions(
            tool_names,
            tool_choice_policy=tool_choice_policy,
        ),
    ]
    return "\n".join(part for part in parts if part is not None).strip()
