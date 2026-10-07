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


# A-13: format-/steuerzeichen, die in einem toolnamen nichts zu suchen
# haben und mit denen die sperre umgangen wurde (`OPEN_URL\u200b`).
_ZERO_WIDTH_CHARS = re.compile(
    "[\u200b\u200c\u200d\ufeff\u00ad\u2060\u180e\u00a0]"
)


def policy_tool_key(name: object) -> str:
    """Kanonischer Schluessel fuer ALLE sicherheits-/sperr-vergleiche (A-13).

    Vorher wurde nur `strip()` verglichen — dadurch umgingen `OPEN_URL`,
    `Browser.Open`, `Execute_Sandbox_Code` und `web.run_v2` die native
    sperre, sobald ein client eine abweichende schreibweise deklariert hat.

    Kanonisiert werden: unicode-NFKC, casefold, punkte/Leerzeichen zu `_`
    und Versions-/Trailing-Suffixe. Der ORIGINAL-API-name bleibt unberuehrt:
    `normalize_tool_name()` wird weiterhin fuer den wire-format verwendet."""
    text = unicodedata.normalize("NFKC", str(name)).strip().casefold()
    text = _ZERO_WIDTH_CHARS.sub("", text)
    text = re.sub(r"[\s.\-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    # `web.run_v2`, `open_url-2`, `browse_v1` sind dieselbe faehigkeit.
    return re.sub(r"_(?:v\d+|version\d+|\d+)$", "", text)


def policy_tool_key_compact(name: object) -> str:
    """Zweiter kanonischer schluessel OHNE trennzeichen (A-13).

    `open_url`, `openurl`, `open-url` und `openUrl` sind dieselbe
    faehigkeit — mit dem unterstrich-schluessel blieb `openurl` ungesperrt.
    Nur fuer den sperrvergleich, nie fuer den wire-format: die
    Originalschreibweise ist der API-vertrag."""
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", policy_tool_key(name))


# Vorberechnete kanonische schluessel der nativen sperre (A-13) — beide
# formen, damit auch `openurl`/`CodeInterpreter` gesperrt sind.
_NATIVE_BLOCK_KEYS = frozenset(policy_tool_key(name) for name in BLOCKED_NATIVE_TOOL_NAMES)
_NATIVE_BLOCK_KEYS_COMPACT = frozenset(
    policy_tool_key_compact(name) for name in BLOCKED_NATIVE_TOOL_NAMES
)
# zusaetzliche schreibweisen, die dieselbe faehigkeit bezeichnen
_NATIVE_BLOCK_ALIASES = frozenset(
    policy_tool_key_compact(alias)
    for alias in (
        "code_interpreter",
        "codeinterpreter",
        "python",
        "python_code",
        "exec_code",
        "execute_code",
        "web_search",
        "websearch",
        "open_url",
        "openurl",
        "openuri",
        "browse",
        "browsing",
        "fetch_url",
        "fetchurl",
        "visit_url",
        "visiturl",
    )
)


def is_blocked_tool_name(name: object, blocked_tool_names: set[str] | None) -> bool:
    """Trifft der (normalisierte) Name die native sperre oder eine
    konfigurierte blockliste? Beide Seiten werden ueber `policy_tool_key`
    verglichen, damit schreibweise und version keine umgehung sind."""
    if name in BLOCKED_NATIVE_TOOL_NAMES:
        return True
    key = policy_tool_key(name)
    if key in _NATIVE_BLOCK_KEYS:
        return True
    compact = policy_tool_key_compact(name)
    if (
        compact in _NATIVE_BLOCK_KEYS_COMPACT
        or compact in _NATIVE_BLOCK_ALIASES
        # `open_url2` / `websearch3`: auch die ziffern-Suffixe sind
        # versionen. Gegenprobe: `read2` -> `read` steht nicht in der
        # sperre, `sha256` -> `sha` ebenfalls nicht — echte tools mit
        # ziffern bleiben benutzbar.
        or re.sub(r"\d+$", "", compact) in _NATIVE_BLOCK_KEYS_COMPACT
        or re.sub(r"\d+$", "", compact) in _NATIVE_BLOCK_ALIASES
    ):
        return True
    if not blocked_tool_names:
        return False
    if any(policy_tool_key(blocked) == key for blocked in blocked_tool_names):
        return True
    return any(policy_tool_key_compact(blocked) == compact for blocked in blocked_tool_names)


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


def serialize_tool_call_block(
    name: str, arguments: object, *, include_terminator: bool = True
) -> str:
    """Serialisiert einen Tool-Call im JSON-Protokoll (mit []-Terminator).

    `include_terminator=False` (R-04): in der gerenderten History wird der
    `[]`-Terminator weggelassen. Er ist eine AUSGABE-anweisung, kein
    History-inhalt — als History-rest las das Modell das `]` als eigene
    Nutzereingabe (`].`) und antwortete auf einen Input, den es nie gab
    (live 2026-10-03, `ses_efdcfe5a…`). Der Parser toleriert einen
    fehlenden Terminator, die Format-anweisung steht weiter am Prompt-ende.

    A-14: bei kaputtem argument-json wurde `{"raw": arguments}` erfunden. Beim
    History-Roundtrip sieht das Modell daraus einen Call mit einem *echten*
    Parameter `raw` — der Aufruf wird mit anderen Argumenten erneut
    ausgeführt, und das Modell hält `raw` für eine Fähigkeit des Tools.

    Die Reparaturtherke selbst war nur die andere Hälfte desselben Problems:
    auch `_unusable_args` und `value` sind Namen, die wie Parameter
    aussehen. Sie tragen jetzt ein `$`-Praefix (`$invalid_arguments`), das
    im JSON-Schema für Meta-Keys reserviert ist und nicht als
    Werkzeug-Fähigkeit gelesen werden kann.
    """
    parsed_arguments = arguments
    if isinstance(arguments, str):
        try:
            parsed_arguments = json.loads(arguments)
        except json.JSONDecodeError:
            parsed_arguments = {"$invalid_arguments": arguments}
    if not isinstance(parsed_arguments, dict):
        parsed_arguments = {"$invalid_arguments_value": parsed_arguments}
    block = safe_json_dumps({"tool_calls": [{"name": name, "arguments": parsed_arguments}]})
    return block + "[]" if include_terminator else block


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

    lines = [
        "# TOOL USE PROTOCOL",
        "",
        "## Allowed tools (EXHAUSTIVE list — no others exist)",
        f"Available tools: {available_names}. No other tools exist — no browser, no open_url, no web.search, no execute_sandbox_code.",
        "Only the tools listed above exist in this environment. Do not attempt to call any other tools.",
        "Before emitting any tool call, verify the tool name appears in the allowed list above. When a task requires tools (e.g. inspecting directories, creating files, running commands), you MUST call the appropriate allowed tool (e.g. bash, write). Never describe actions in prose instead of calling the tool.",
        "## Finishing (read carefully)",
        "When the task is fully done and no further tool is needed, you MUST stop and deliver your final answer as normal prose and WITHOUT any tool call. A finished answer with prose alone is allowed and expected. Never append a tool call to an answer you consider complete, and never re-run tools just to look busy. Do NOT write a summary and then continue with more calls.",
        "",
        "## Filesystem, Code Execution & Web Rules",
        "- For filesystem operations (inspecting, listing, or creating directories like `/workspaces`, reading/writing files), you MUST use `bash` (e.g. `ls`, `mkdir`) or `read`/`write`. NEVER attempt to call `open` on directory paths or files — `open` is NOT a filesystem tool and will fail.",
        "- For each read/search/list/write operation, call the exact declared tool directly with its schema arguments (`read.filePath`, `grep.pattern/path`, `glob.pattern`, `bash.command`, etc.). Do NOT wrap a tool in `open`, put a tool name in `ref_id`, or turn `bash:`/`read:` pseudo-targets into paths.",
        "- After each tool result, inspect that result and choose a new, task-relevant call. Never resend a completed identical call, never fetch placeholder/example URLs, and do not claim a tool/round limit. If a call failed, correct its arguments or use an appropriate declared alternative.",
        "- For executing Python, running tests (pytest), or executing code, you MUST use `bash` (e.g. `python3 -m pytest ...`, `python3 script.py`). NEVER attempt to call `execute_sandbox_code`, `code_interpreter`, or any sandbox tool — no sandbox tools exist in this environment.",
        "- For web requests, use `webfetch` (if available). Never call `open`, `open_url`, or `browser`.",
        "",
        "## Complete repository audits",
        "For a complete repository audit: inventory with bash `git ls-files`; track coverage with todowrite; inspect actual implementation files and tests in EVERY top-level area, not only READMEs. Run relevant checks through the repository timeout wrapper. A README-only assessment is incomplete. Report measured evidence and justified exclusions; continue inspecting missing areas rather than asking for a new session.",
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
    "Call the exact declared tool directly with its schema arguments; do not wrap a tool in `open` or encode commands/paths as `ref_id`. After each result, choose a new task-relevant action and never repeat a completed identical call. "
    "For running Python scripts or pytest, use `bash` — NEVER call `execute_sandbox_code`. "
    "Do NOT output plans, summaries, or descriptions in prose INSTEAD OF a tool call the task still needs. "
    "But if the task is fully complete and no further tool is needed, STOP and give your final answer as normal prose with NO tool call — that is allowed and expected. Never append a tool call to a finished answer and never summarize and then continue. "
    "Prose, XML, or fenced blocks will NOT be executed as tool calls. "
    "NEVER call tools that are not in the allowed list (such as execute_sandbox_code, open, open_url, web_search). "
    "If you need information from a URL, use an allowed tool or tell the user — do NOT invent a tool. "
    "Do not output any preamble, commentary, or thoughts in Chinese or any other language before the tool call. "
    "If answering the user directly (only when no tools are needed), provide the answer in the conversation language (e.g. German)."
)


# T-29 (Live-Analyse 2026-09-30): Der Tool-Disziplin-Kopf (System-Prompt von
# OpenCode mit INSTRUCTIONS-glm2api.md) steht am ANFANG des Transkripts und
# faellt bei langen Sessions zuerst in die History-Kompression. Der hier
# verankerte RECAP steht dagegen am PROMPT-ENDE (nach dem letzten User-Turn,
# vor TOOL_FORMAT_REMINDER) und ist damit kompressionssicher — er beginnt
# IMMER mit `[System instruction — highest priority]`, damit das Modell ihn
# nie als Teil der eigenen Narration liest. Regeln bewusst redundant zum
# Kopf: unter langem Kontext gewinnt nicht der Recall (den hat das Modell,
# live geprueft), sondern die Naehe zum Aktionszeitpunkt.
TOOL_DISCIPLINE_RECAP = (
    "[System instruction — highest priority] TOOL DISCIPLINE (restated closest to your action point): "
    "The COMPLETE tool contract is the TOOL SCHEMAS list above. `open`, `open_url`, `browse`, "
    "`web_search`, `execute_sandbox_code` and `sandbox` DO NOT exist here — use `read` "
    "(absolute filePath) for files, `webfetch` (full https URL) for web pages, `bash` for commands. "
    "Never invent tool names, URLs, or `ref_id`/`turn0search*` references; never repeat an "
    "identical call after you have seen its result. If proxy notices like `[native_remap_notice]`, "
    "`[blocked_tool_notice]`, `[internal_reference_notice]` or `[loop_guard_notice]` appear in a "
    "tool result, obey them immediately and switch to the named tool. "
    "FINISHING: once the task is genuinely complete, end with a normal prose answer and NO tool "
    "call — never append a tool call to a finished answer and never summarize and then continue. "
    # D-02/F-01: VERBOTE werden bei glm-5.3 zuverlässig überstimmt (live: `open`
    # trotz explizitem "DO NOT exist", 5× `example.com` trotz Verbot). Formate
    # werden dagegen zuverlässig IMITIERT. Deshalb zwei echte Beispiele der
    # gewuenschten Form — je eines fuer "Datei" und "Suche", exakt in der
    # Shape, in der der Tool-Call emittiert werden muss. `grep:/pfad` und
    # `ref_id`-Hüllen sind bewusst NICHT im Beispiel: sie wären sonst als
    # Muster lesbar (der Mapper akzeptiert sie, siehe `map_native_open_tool_call`).
    "Correct call shapes, copied exactly: "
    'file -> {"name":"read","arguments":{"filePath":"/workspaces/MAIN/README.md"}} '
    'listing/du/size/git -> {"name":"bash","arguments":{"command":"ls -la /workspaces/MAIN"}} '
    'text search -> {"name":"grep","arguments":{"pattern":"TODO","path":"/workspaces/MAIN"}} '
    'web page (ONLY a real URL given in the task) -> {"name":"webfetch","arguments":{"url":"https://developer.mozilla.org/en-US/docs/Web/API"}} '
    "Never: {\"name\":\"open\"...}, {\"name\":\"webfetch\",\"arguments\":{\"url\":\"https://example.com\"}}, "
    "a URL you did not receive in the task, or a local path inside a url argument."
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


# D-01: alle praefixe, mit denen ein unvollstaendiger tool-aufruf beginnen
# kann — auch ABGESCHNITTENE. `{"tool` ist ein praefix von `{"tool_calls"`,
# genau der fall, der im final-pfad durchrutschte.
_TOOL_PROTOCOL_STARTS = (
    '{"tool_calls"',
    '{"name"',
    '{"arguments"',
    '{"function"',
    '{"type": "function"',
    '{"id"',
)
_TOOL_PROTOCOL_PREFIX_SET = frozenset(
    token[:length]
    for token in _TOOL_PROTOCOL_STARTS
    for length in range(3, len(token) + 1)
)


def strip_unterminated_tool_prefix(text: str) -> tuple[str, int]:
    """Entfernt einen angebrochenen tool-protokoll-praefix am textende.

    D-01: der streaming-pfad haelt so einen praefix im holdback zurueck,
    der FINAL-pfad nicht. Ergebnis: der client sah im stream nichts, in
    der abschlussantwort aber `{"tool` als inhalt — und bekam dazu
    `finish_reason: stop`, also eine als ERFOLG verlesene antwort.

    Konservativ, in drei schritten:
      1. nur kandidaten ab der LETZTEN offenen geschweiften klammer,
      2. der rest ab dort muss ein echtes protokoll-praefix sein
         (`{"` + anfang eines protokollfelds),
      3. die klammer muss ungeschlossen sein — ein vollstaendiger
         aufruf darf hier nicht ankommen, den holt der parser.
    Prosa, die mit `{` endet, bleibt unangetastet.
    """
    if not text:
        return text, 0
    # Ein einzelnes abschliessendes `{` ist der ERSTE character des
    # protokolls und damit der erste character, den der stream-holdback
    # zurueckhaelt. Der final-pfad muss dasselbe tun, sonst laeuft er bei
    # chunk-groesse 1 eine stufe weiter als der stream. Der preis: eine
    # normale zeile, die mit `{` endet, verliert ihre klammer — das ist
    # derselbe tradeoff, den der stream-pfad bereits macht, und deutlich
    # guenstiger als ein protokoll-fragment als antwort zu liefern.
    stripped_text = text.rstrip()
    if stripped_text.endswith("{") and not _braces_balanced(stripped_text):
        return stripped_text[:-1].rstrip(), 1
    if '"' not in text:
        return text, 0
    for index in range(text.rfind("{"), -1, -1):
        tail = text[index:]
        if not tail.startswith('{"'):
            continue
        # (2) echtes protokoll-praefix?
        if not any(token.startswith(tail) or tail.startswith(token) for token in _TOOL_PROTOCOL_PREFIX_SET):
            continue
        # (3) ungeschlossen? bei geschlossener klammer hat der parser
        # den aufruf schon geholt — nichts zu entfernen.
        if _braces_balanced(tail):
            continue
        return text[:index].rstrip(), 1
    return text, 0


# S-09 (Nachtrag): Werkzeug-MARKUP gegen Prosa unterscheiden.
#
# `_NARRATION_TOKEN_RE` im translator matcht unter anderem `tool_calls` —
# das ist im PROSA-Fall richtig (das Modell ERZÄHLT über das Protokoll), im
# Markup-Fall aber ein Fehlalarm: `{"tool_calls":[…]}` ist kein Satz, den man
# zurückhalten kann, sondern der aufruf selbst. Wird es doch zurückgehalten,
# sieht der parser den aufruf erst im `finalize`, und die bewertung
# „unbrauchbarer aufruf" (T-06, `dropped_call_count`) ist da bereits
# vorbei. Gemessen 2026-09-26: `{"tool_calls":[{"name":"read",
# "arguments":{}}]}` endete als `finish_reason: stop` mit leerem inhalt
# statt als `error` — der leere ERFOLG, den T-06 genau abstellen sollte.
#
# Deshalb die Entscheidung "darf ich warten?" VOR dem Muster: markup geht
# immer direkt an den parser (der hat mit D-01/D-03 seinen eigenen
# holdback fuer angebrochenes markup), der narration-holdback fasst nur
# Prosa an.
_TOOL_MARKUP_RE = re.compile(
    r"(?i)(?:"
    r"\"tool_calls?\"\s*:"          # {"tool_calls": [...]}  (JSON-Protokoll)
    r"|\btool_calls?_(?:begin|end)\b"  # DSML-Marker
    r"|<\s*/?\s*tool_call[\s>/]"    # <tool_call> / </tool_call> (Legacy-XML)
    # S-18: das DSML-aufrufprotokoll (`<|DSML|tool_calls>…`) fehlte hier.
    # Folge: der narration-holdback im translator erkannte es nicht als
    # markup, behielt es im carry fest und gab es dem parser ZU SPAET — der
    # puffer des parsers enthielt dann markup UND die folgende prosa, und die
    # ging beim flush verloren (gemessen in `harness/sweep2.py`,
    # `dsml-aufruf+prosa`, 6 von 6 chunk-groessen: der client bekam den
    # aufruf und sonst nichts).
    r"|<\|?\s*dsml\|"
    r")"
)


def contains_tool_markup(text: str) -> bool:
    """Enthaelt `text` werkzeug-Markup statt reiner Prosa?

    Conservative by design: nur eindeutige marker zaehlen. Ein Wort
    `tool` in einem Satz ist Prosa, `{"tool_calls":` ist Protokoll.
    """
    if not text:
        return False
    return bool(_TOOL_MARKUP_RE.search(text))


def _braces_balanced(fragment: str) -> bool:
    depth = 0
    in_string = False
    escaped = False
    for char in fragment:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
    # nur am ENDE zaehlt: eine zwischenzeitlich auf 0 fallende klammer ist
    # eine verschachtelte, nicht der schluss des ganzen fragments.
    # `depth <= 0` statt `== 0`: der `[]`-terminator schliesst das
    # aufruf-objekt und zieht den zaehler darueber hinaus ins negative —
    # das ist ein vollstaendiger aufruf, kein abgeschnittener.
    return depth <= 0 and not in_string
