from __future__ import annotations

import json
import logging
import re
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from .tool_protocol import BLOCKED_NATIVE_TOOL_NAMES, is_blocked_tool_name

CODE_FENCE_PATTERN = re.compile(r"(?:```|~~~)[\s\S]*?(?:```|~~~)")

# Tolere Protokoll-Suche: {' "tool_calls" ' mit beliebigem Whitespace dazwischen
# (Pretty-Print / Leerzeichen nach '{' — vom Modell beobachtet).
_TOOL_CALLS_PROTOCOL_RE = re.compile(r"\{\s*\"tool_calls\"\s*:")


def find_tool_calls_protocol(text: str) -> int:
    """Findet den Start eines JSON-Tool-Protokoll-Objekts (tolerant gegen
    Pretty-Printing). Gibt -1 zurueck, wenn keines vorhanden ist."""
    match = _TOOL_CALLS_PROTOCOL_RE.search(_mask_code_fences(text))
    return match.start() if match else -1


TOOL_RESULT_PATTERN = re.compile(
    r"<(?:(?:\|DSML\|)|ml_)?tool_result\b[\s\S]*?</(?:(?:\|DSML\|)|ml_)?tool_result>",
    re.IGNORECASE,
)
START_TAG_PATTERN = re.compile(
    # P-07: 'tool_call' (singular) fehlte — das generische <tool_call> wurde
    # weder als start erkannt noch extrahiert und blieb als text stehen.
    r"<(?P<tag>\|DSML\|tool_calls|DStool_calls|tool_calls|tool_call|ml_tool_calls|ml_tool_call|DSMLtool_calls|dsmltool_calls|dstool_calls|dstoolcall|DSML_tool_calls|DSMLtoolcalls|invoke|ml_invoke|parameter|ml_parameter)(?=\b|\|)[^>]*>",
    re.IGNORECASE,
)
DSML_TAG_PATTERN = re.compile(r"</?\|DSML\|(?P<name>tool_calls|invoke|parameter|tool_result)\b", re.IGNORECASE)
DSML_OPEN_TAG_PATTERN = re.compile(
    r"<\|dsml\|(?P<name>tool_calls|toolcalls|invoke|parameter|tool_result|toolresult)\b(?P<attrs>[^<>]*?)>",
    re.IGNORECASE,
)
DSML_CLOSE_TAG_PATTERN = re.compile(
    r"</\|dsml\|(?P<name>tool_calls|toolcalls|invoke|parameter|tool_result|toolresult)\s*\|?\s*>",
    re.IGNORECASE,
)
DSML_COMPACT_CLOSE_TAG_PATTERN = re.compile(
    r"(?:</\|dsml|<\|/dsml)(?P<name>toolcalls|invoke|parameter|toolresult)\s*\|\s*>",
    re.IGNORECASE,
)
DSML_DOUBLE_PIPE_CLOSE_TAG_PATTERN = re.compile(
    r"<\|\|dsml\|(?P<name>tool_calls|toolcalls|invoke|parameter|tool_result|toolresult)\s*\|?\s*>",
    re.IGNORECASE,
)
DSML_TOOL_CALLS_CLOSE_PATTERN = re.compile(
    r"(?:</\|dsml\|tool_calls\s*>|</\|dsml\|tool_calls\s*\|\s*>|</\|dsmltool_?calls\s*\|\s*>|<\|/dsmltool_?calls\s*\|\s*>|</\|?dsml\|?tool_?calls\s*>?)",
    re.IGNORECASE,
)
DSML_TOOL_CALLS_TRAILING_CLOSE_PATTERN = re.compile(
    r"(?:</\|dsml\|tool_calls\s*>|</\|dsml\|tool_calls\s*\|\s*>|</\|dsmltool_?calls\s*\|\s*>|<\|/dsmltool_?calls\s*\|\s*>|</\|dsml\|tool_calls\s*$|</\|dsmltool_?calls\s*\|?\s*$|<\|/dsmltool_?calls\s*\|?\s*$|</\|?dsml\|?tool_?calls\s*\|?\s*$)",
    re.IGNORECASE,
)
PARAM_NAME_TAG_PATTERN = re.compile(r"<param_name>\s*(.*?)\s*</param_name>", re.IGNORECASE | re.DOTALL)
PARAM_VALUE_TAG_PATTERN = re.compile(r"<param_value>\s*(.*?)\s*</param_value>", re.IGNORECASE | re.DOTALL)
TAG_NAME_HINTS = [
    "<|",
    "</|",
    "<|DSML|",
    "</|DSML|",
    "<|DSML|tool_calls",
    "</|DSML|tool_calls",
    "<|DSML|invoke",
    "</|DSML|invoke",
    "<|DSML|parameter",
    "</|DSML|parameter",
    "<|DSML|tool_result",
    "</|DSML|tool_result",
    "<DStool_calls",
    "</DStool_calls",
    "<ml_",
    "</ml_",
    "<ml_tool_calls",
    "</ml_tool_calls",
    "<ml_tool_call",
    "</ml_tool_call",
    "<ml_tool_name",
    "</ml_tool_name",
    "<ml_parameters",
    "</ml_parameters",
    "<ml_tool_result",
    "</ml_tool_result",
    "<tool_calls",
    "</tool_calls",
    "<invoke",
    "</invoke",
    "<parameter",
    "</parameter",
    # P-07: generisches <tool_call> (auch mit zero-width-space, vom Modell
    # beobachtet) bisher nicht erkannt — der aufruf landete als text.
    "<tool_call",
    "</tool_call",
    "<tool_call",
    "</tool_call",
]


def _local_name(tag: str) -> str:
    if "}" in tag:
        tag = tag.split("}", 1)[1]
    if ":" in tag:
        tag = tag.split(":", 1)[1]
    return tag.lower()


def _normalize_root_tag(tag: str) -> str:
    """'dstool_calls' -> 'tool_calls' (das Modell emittiert diverse Varianten)."""
    name = _local_name(tag)
    if name in ("dstoolcalls", "dstool_calls", "dstoolcall", "ds_tool_calls"):
        return "tool_calls"
    return name


def _canonical_dsml_name(name: str) -> str:
    normalized = name.lower().replace("_", "")
    if normalized == "toolcalls":
        return "tool_calls"
    if normalized == "toolresult":
        return "tool_result"
    return normalized


def _repair_malformed_dsml(block: str) -> str:
    if "<|" not in block and "]]|>" not in block and "<![CDATA[" not in block:
        return block

    repaired = block.replace("]]|>", "]]>")
    # Mashup-Variante: '<|DSML|invoke name="x"><![CDATA[name="TOOL">' —
    # das Modell packt den echten Tool-Namen in CDATA statt ins name-Attribut.
    repaired = re.sub(
        r"<(\|?DSML\|?)invoke\s+name=\"[^\"]*\"><!\[CDATA\[name=\"([^\"]+)\"",
        lambda m: f"<{m.group(1)}invoke name=\"{m.group(2)}\">",
        repaired,
        flags=re.IGNORECASE,
    )
    # leeres CDATA-Öffnen ('<![CDATA[>') fallen lassen — öffnet sonst einen
    # CDATA-Bereich, der alle nachfolgenden Tags bis zum nächsten ']]>' schluckt
    repaired = repaired.replace("<![CDATA[>", "")
    # doppeltes '>' nach Mashup-Repair fallen lassen
    repaired = repaired.replace('">>', '">')
    # Root-Varianten '<DStool_calls>' auf kanonisch '<tool_calls>' mappen,
    # damit der schließende Tag '</tool_calls>' matched
    repaired = re.sub(r"<dstool_calls\b[^>]*>", "<DStool_calls>", repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"<dstool_calls>", "<tool_calls>", repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"</dstool_calls\s*>", "</tool_calls>", repaired, flags=re.IGNORECASE)
    if "<![CDATA[" in repaired:
        repaired = re.sub(
            r"(?<!\])\]>(?=</\|dsml\|parameter\b|</\|DSML\|parameter\b|</parameter\b|</\|dsmlparameter\|)",
            "]]>",
            repaired,
            flags=re.IGNORECASE,
        )

    def replace_open(match: re.Match[str]) -> str:
        name = _canonical_dsml_name(match.group("name"))
        attrs = match.group("attrs").rstrip("|").rstrip()
        return f"<|DSML|{name}{attrs}>"

    def replace_close(match: re.Match[str]) -> str:
        return f"</|DSML|{_canonical_dsml_name(match.group('name'))}>"

    repaired = DSML_OPEN_TAG_PATTERN.sub(replace_open, repaired)
    repaired = DSML_CLOSE_TAG_PATTERN.sub(replace_close, repaired)
    repaired = DSML_COMPACT_CLOSE_TAG_PATTERN.sub(replace_close, repaired)
    repaired = DSML_DOUBLE_PIPE_CLOSE_TAG_PATTERN.sub(replace_close, repaired)
    repaired = re.sub(
        r"(?:</\|dsml\|tool_calls|</\|dsmltool_?calls|<\|/dsmltool_?calls)\s*\|?\s*$",
        "</|DSML|tool_calls>",
        repaired,
        flags=re.IGNORECASE,
    )
    return repaired


def _normalize_dsml_to_xml(block: str) -> str:
    repaired = _repair_malformed_dsml(block)
    return DSML_TAG_PATTERN.sub(lambda match: match.group(0).replace("|DSML|", ""), repaired)


def _is_allowed_tool_name(tool_name: str, allowed_tool_names: set[str] | None) -> bool:
    """Tool-Namen gegen die deklarierte Allowlist pruefen.

    `allowed_tool_names=None` bedeutet 'keine Tools deklariert' und damit
    'nie einen Call erzeugen' — nicht mehr 'alles erlaubt'. Fuer die interne
    diagnose (blockierte Versuche sammeln) gibt es `detect_all=True`.

    A-13: die native sperre wird ueber die kanonische policy verglichen,
    sonst umgingen `OPEN_URL`/`Browser.Open`/`web.run_v2` die sperre,
    sobald der client genau diese schreibweise deklariert hatte."""
    if is_blocked_tool_name(tool_name, None):
        return False
    if allowed_tool_names is None:
        return False
    return tool_name in allowed_tool_names


def _balanced_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _leaf_text(element: ET.Element) -> str:
    return _balanced_text("".join(element.itertext()))


def _coerce_leaf_value(text: str) -> object:
    stripped = text.strip()
    if stripped == "":
        return ""
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            if stripped.startswith("[") and not stripped.endswith("]"):
                try:
                    return json.loads(stripped + "]")
                except json.JSONDecodeError:
                    pass
            return stripped
    if stripped in {"true", "false"}:
        return stripped == "true"
    if stripped == "null":
        return None
    if re.fullmatch(r"-?\d+", stripped):
        try:
            return int(stripped)
        except ValueError:
            return stripped
    if re.fullmatch(r"-?\d+\.\d+", stripped):
        try:
            return float(stripped)
        except ValueError:
            return stripped
    return stripped


def _append_value(mapping: dict[str, object], key: str, value: object) -> None:
    if key not in mapping:
        mapping[key] = value
        return
    existing = mapping[key]
    if isinstance(existing, list):
        existing.append(value)
        return
    mapping[key] = [existing, value]


def _xml_value_to_object(element: ET.Element) -> object:
    children = [child for child in list(element) if isinstance(child.tag, str)]
    if not children:
        return _coerce_leaf_value(_leaf_text(element))

    repeated_item_only = all(_local_name(child.tag) == "item" for child in children)
    if repeated_item_only:
        return [_xml_value_to_object(child) for child in children]

    result: dict[str, object] = {}
    for child in children:
        key = child.attrib.get("name", "").strip() or _local_name(child.tag)
        _append_value(result, key, _xml_value_to_object(child))
    return result


def _extract_tool_name(element: ET.Element) -> str:
    if _local_name(element.tag) == "invoke":
        return element.attrib.get("name", "").strip()
    for tag_name in ("ml_tool_name", "tool_name"):
        tool_name_element = element.find(tag_name)
        if tool_name_element is not None:
            return _leaf_text(tool_name_element)
    return ""


def _extract_arguments(element: ET.Element) -> dict[str, object] | None:
    if _local_name(element.tag) == "invoke":
        parameters: dict[str, object] = {}
        parameter_children = [
            child
            for child in list(element)
            if isinstance(child.tag, str) and _local_name(child.tag) == "parameter"
        ]
        for child in parameter_children:
            key = child.attrib.get("name", "").strip()
            if key:
                _append_value(parameters, key, _xml_value_to_object(child))
        return parameters

    for tag_name in ("ml_parameters", "parameters"):
        parameters_element = element.find(tag_name)
        if parameters_element is not None:
            parsed = _xml_value_to_object(parameters_element)
            if isinstance(parsed, dict):
                return parsed
            return {"value": parsed}
    return None


def _build_tool_call(name: str, arguments: dict[str, object], index: int) -> dict[str, object]:
    return {
        "id": f"call_{uuid.uuid4().hex[:24]}",
        "type": "function",
        "index": index,
        "function": {
            "name": name,
            "arguments": json.dumps(arguments, ensure_ascii=False, separators=(",", ":")),
        },
    }


def _parse_tool_call_element(
    element: ET.Element,
    allowed_tool_names: set[str] | None,
    index: int,
) -> dict[str, object] | None:
    if _local_name(element.tag) not in {"invoke", "tool_call", "ml_tool_call"}:
        return None

    tool_name = _extract_tool_name(element)
    if not tool_name:
        # P-07: der generic <tool_call> trägt den aufruf als JSON-Payload
        # im elementtext statt als attribute — ohne diesen zweitweg bleibt
        # der komplette block als sichtbarer text stehen.
        payload_call = _call_from_json_payload(element)
        if payload_call is not None:
            return payload_call
        return None
    if not _is_allowed_tool_name(tool_name, allowed_tool_names):
        return None

    arguments = _extract_arguments(element)
    if arguments is None:
        return None

    return _build_tool_call(tool_name, arguments, index)


def _call_from_json_payload(element: ET.Element) -> dict[str, object] | None:
    """Tool-Call aus einem JSON-Payload im elementtext (P-07).

    Deckt die formen ab, die das Modell bei einem generischen
    <tool_call> liefert: reines JSON, JSON in CDATA und JSON mit
    vorangestelltem praefix-text."""
    raw = (element.text or "").strip()
    if not raw:
        return None
    candidates = [raw]
    if raw.startswith("<![CDATA[") and raw.endswith("]]>"):
        candidates.append(raw[9:-3].strip())
    brace = raw.find("{")
    if brace != -1:
        candidates.append(raw[brace:])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(parsed, dict):
            continue
        name = str(parsed.get("name", "")).strip()
        if not name:
            continue
        arguments = parsed.get("arguments")
        if arguments is None:
            arguments = parsed.get("parameters", {})
        args_str = _extract_call_arguments({"name": name, "arguments": arguments})
        return {
            "index": 0,
            "id": f"call_{uuid.uuid4().hex[:24]}",
            "type": "function",
            "function": {"name": name, "arguments": args_str or "{}"},
        }
    return None


def _extract_malformed_tool_call_from_root(
    root: ET.Element,
    allowed_tool_names: set[str] | None,
    index: int,
) -> dict[str, object] | None:
    root_name = _local_name(root.tag)
    if root_name not in {"tool_calls", "ml_tool_calls"}:
        return None

    tool_name = _extract_tool_name(root)
    if not tool_name:
        return None
    if not _is_allowed_tool_name(tool_name, allowed_tool_names):
        return None

    for tag_name in ("ml_parameters", "parameters"):
        parameters_element = root.find(tag_name)
        if parameters_element is not None:
            parsed = _xml_value_to_object(parameters_element)
            arguments = parsed if isinstance(parsed, dict) else {"value": parsed}
            return _build_tool_call(tool_name, arguments, index)

    names = [match.group(1).strip() for match in PARAM_NAME_TAG_PATTERN.finditer(ET.tostring(root, encoding="unicode"))]
    values = [match.group(1).strip() for match in PARAM_VALUE_TAG_PATTERN.finditer(ET.tostring(root, encoding="unicode"))]
    if names and values and len(names) == len(values):
        arguments = {
            key: _coerce_leaf_value(value)
            for key, value in zip(names, values, strict=False)
            if key
        }
        return _build_tool_call(tool_name, arguments, index)
    if names and not values:
        return None

    direct_pairs: dict[str, object] = {}
    children = [child for child in list(root) if isinstance(child.tag, str)]
    for child in children:
        key = _local_name(child.tag)
        if key in {"tool_name", "ml_tool_name", "tool_call", "ml_tool_call"}:
            continue
        if key in {"param_name", "param_value"}:
            continue
        direct_pairs[key] = _xml_value_to_object(child)
    if direct_pairs:
        return _build_tool_call(tool_name, direct_pairs, index)
    return None


def _parse_xml_block(
    block: str,
    allowed_tool_names: set[str] | None,
    start_index: int,
) -> tuple[list[dict[str, object]], tuple[int, int] | None]:
    try:
        root = ET.fromstring(_normalize_dsml_to_xml(block))
    except ET.ParseError:
        return [], None

    root_name = _normalize_root_tag(root.tag)
    if root_name in {"tool_calls", "ml_tool_calls"}:
        candidates = [
            child
            for child in list(root)
            if isinstance(child.tag, str) and _local_name(child.tag) in {"invoke", "tool_call", "ml_tool_call"}
        ]
    elif root_name in {"tool_call", "ml_tool_call"}:
        candidates = [root]
    else:
        return [], None

    tool_calls: list[dict[str, object]] = []
    for candidate in candidates:
        parsed = _parse_tool_call_element(candidate, allowed_tool_names, len(tool_calls))
        if parsed is not None:
            tool_calls.append(parsed)

    if not tool_calls:
        malformed = _extract_malformed_tool_call_from_root(root, allowed_tool_names, 0)
        if malformed is not None:
            tool_calls.append(malformed)

    if not tool_calls:
        return [], None
    return tool_calls, (start_index, start_index + len(block))


def _mask_code_fences(text: str) -> str:
    masked = list(text)
    for match in CODE_FENCE_PATTERN.finditer(text):
        for index in range(match.start(), match.end()):
            masked[index] = " "
    return "".join(masked)


def _find_matching_block(
    masked_text: str,
    start_match: re.Match[str],
    *,
    allow_trailing_close: bool = False,
) -> tuple[int, int] | None:
    tag_name = start_match.group("tag").lower()
    if tag_name in ("|dsml|tool_calls", "dstool_calls"):
        closing_pattern = DSML_TOOL_CALLS_TRAILING_CLOSE_PATTERN if allow_trailing_close else DSML_TOOL_CALLS_CLOSE_PATTERN
    else:
        closing_pattern = re.compile(rf"</{re.escape(tag_name)}\s*>", re.IGNORECASE)
    closing_match = closing_pattern.search(masked_text, start_match.end())
    if closing_match is None:
        return None
    return start_match.start(), closing_match.end()


def _extract_tool_blocks(
    text: str,
    allowed_tool_names: set[str] | None,
    *,
    allow_trailing_close: bool = False,
) -> tuple[list[tuple[int, int]], list[dict[str, object]]]:
    masked_text = _mask_code_fences(text)
    spans: list[tuple[int, int]] = []
    tool_calls: list[dict[str, object]] = []
    cursor = 0

    while cursor < len(masked_text):
        match = START_TAG_PATTERN.search(masked_text, cursor)
        if match is None:
            break
        span = _find_matching_block(masked_text, match, allow_trailing_close=allow_trailing_close)
        if span is None:
            break

        start, end = span
        block_calls, parsed_span = _parse_xml_block(text[start:end], allowed_tool_names, start)
        if parsed_span is not None and block_calls:
            for offset, tool_call in enumerate(block_calls, start=len(tool_calls)):
                tool_call["index"] = offset
            spans.append(parsed_span)
            tool_calls.extend(block_calls)
            cursor = end
            continue
        if match.group("tag").lower() in {"|dsml|tool_calls", "tool_calls", "ml_tool_calls", "ml_tool_call"}:
            spans.append((start, end))
            cursor = end
            continue

        cursor = match.end()

    return spans, tool_calls


def _remove_spans(text: str, spans: list[tuple[int, int]], *, trim_outer_whitespace: bool = True) -> str:
    if not spans:
        cleaned = TOOL_RESULT_PATTERN.sub("", text)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip() if trim_outer_whitespace else cleaned

    parts: list[str] = []
    cursor = 0
    for start, end in spans:
        if start < cursor:
            continue
        parts.append(text[cursor:start])
        cursor = end
    parts.append(text[cursor:])
    cleaned = "".join(parts)
    cleaned = TOOL_RESULT_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip() if trim_outer_whitespace else cleaned


def _find_unmatched_fence_start(text: str) -> int | None:
    last_open = None
    cursor = 0
    while True:
        index = text.find("```", cursor)
        if index == -1:
            break
        if last_open is None:
            last_open = index
        else:
            last_open = None
        cursor = index + 3
    return last_open


def _find_incomplete_block_start(text: str, *, allow_trailing_close: bool = False) -> int | None:
    masked_text = _mask_code_fences(text)
    cursor = 0
    while cursor < len(masked_text):
        match = START_TAG_PATTERN.search(masked_text, cursor)
        if match is None:
            break
        span = _find_matching_block(masked_text, match, allow_trailing_close=allow_trailing_close)
        if span is None:
            return match.start()
        cursor = span[1]
    return None


def _find_partial_tag_start(text: str) -> int | None:
    lowered_text = text.lower()
    pipe_tag_start = lowered_text.rfind("<|")
    if pipe_tag_start != -1 and ">" not in lowered_text[pipe_tag_start:]:
        return pipe_tag_start
    for hint in TAG_NAME_HINTS:
        lowered_hint = hint.lower()
        max_overlap = min(len(hint), len(text))
        for size in range(max_overlap, 0, -1):
            if lowered_text.endswith(lowered_hint[:size]):
                return len(text) - size
    return None


def _looks_like_tool_markup_fragment(text: str) -> bool:
    stripped = text.strip()
    lowered = stripped.lower()
    if not stripped:
        return False
    if lowered.startswith("<|dsml|") or lowered.startswith("</|dsml|") or lowered.startswith("<|/dsml"):
        return True
    if stripped.startswith("<ml_") or stripped.startswith("</ml_"):
        return True
    if stripped.startswith("<tool_") or stripped.startswith("</tool_"):
        return True
    if stripped.startswith("<invoke") or stripped.startswith("</invoke"):
        return True
    if stripped.startswith("<parameter") or stripped.startswith("</parameter"):
        return True
    if stripped.startswith("<m") and any(token in stripped for token in ("ml_", "tool_", "tool_calls", "tool_result")):
        return True
    return False


def _extract_call_arguments(call: dict[str, object]) -> str:
    args = call.get("arguments")
    if args is not None and (isinstance(args, str) or (isinstance(args, dict) and args)):
        return args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)
    # Fallback: model emitted parameters directly as sibling keys of "name"
    siblings = {k: v for k, v in call.items() if k not in ("name", "id", "type", "arguments", "index", "_repaired")}
    if siblings:
        return json.dumps(siblings, ensure_ascii=False)
    if isinstance(args, dict):
        return json.dumps(args, ensure_ascii=False)
    return "{}"


def _recover_call_elements(
candidate: str) -> dict[str, object] | None:
    """Recovery-Stufe 3: Das Modell liefert gelegentlich invalides JSON
    mit unbalancierten klammern (haeufig fehlt das '}' zwischen zwei
    call-objekten, z.B. '..."arguments":{...}]},{\"name\":...'). Der
    brace-scan findet dann kein ende und der komplette block leakt als
    text. Hier: die 'name'/'arguments'-paare einzeln extrahieren —
    arguments via eigenem string-aware brace-scan — und das objekt neu
    serialisieren. Robust gegen fehlende kommas/klammern zwischen den
    call-elementen."""
    calls: list[dict[str, object]] = []
    pos = 0
    len_c = len(candidate)
    while pos < len_c:
        name_idx = candidate.find('"name"', pos)
        if name_idx == -1:
            break
        # name-wert lesen (string nach dem colon)
        colon = candidate.find(":", name_idx + 6)
        if colon == -1:
            break
        j = colon + 1
        while j < len_c and candidate[j] in " \t\r\n":
            j += 1
        if j >= len_c or candidate[j] != '"':
            pos = name_idx + 6
            continue
        j += 1
        name_chars: list[str] = []
        while j < len_c:
            ch = candidate[j]
            if ch == "\\" and j + 1 < len_c:
                name_chars.append(ch + candidate[j + 1])
                j += 2
                continue
            if ch == '"':
                break
            name_chars.append(ch)
            j += 1
        name = "".join(name_chars)
        if not name:
            pos = j
            continue
        # arguments-objekt: naechstes '{"' nach dem name-wert
        args_start = candidate.find("{", j)
        # naechstes '"arguments"' vorziehen, wenn es vor args_start+? liegt —
        # einfach: arguments-schluessel suchen, danach brace-scan
        args_key = candidate.find('"arguments"', j)
        if args_key == -1:
            break
        brace = candidate.find("{", args_key + 11)
        if brace == -1:
            break
        depth = 0
        in_str = False
        esc = False
        end = -1
        k = brace
        while k < len_c:
            ch = candidate[k]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                k += 1
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = k + 1
                    break
            k += 1
        if end == -1:
            # arguments unvollstaendig bis text-ende: bis zum letzten '}' vor
            # terminator-artigem rest nehmen
            break
        args_raw = candidate[brace:end]
        try:
            arguments = json.loads(args_raw)
        except json.JSONDecodeError:
            arguments = None
        if arguments is None:
            # reparaturversuch: array-bracket ergaenzen
            try:
                arguments = json.loads(args_raw[:-1] + "]}")
            except json.JSONDecodeError:
                arguments = {"_raw": args_raw}
        calls.append({"name": name, "arguments": arguments})
        pos = end
    if not calls:
        return None
    return {"tool_calls": calls}


def _recover_tool_calls_json(candidate: str) -> dict[str, object] | None:
    """Recovery fuer Snipsel+Finish-Duplikate: Der stream-buffer enthaelt
    '<fragment><volltext>' (upstream streamt token-schnipsel, dann den
    volltext als eigenes delta). Der brace-scan bricht dann am ersten
    oberflaechlich balancierten '}' ab und json.loads scheitert am doppelten
    prefix. Hier: alle '{"tool_calls'-vorkommen im kandidaten scannen, das
    erste valide, balancierte objekt extrahieren und parsen."""
    probe = '{"tool_calls'
    search_from = 0
    while True:
        idx = candidate.find(probe, search_from)
        if idx == -1:
            return None
        depth = 0
        in_str = False
        esc = False
        end = -1
        for i in range(idx, len(candidate)):
            ch = candidate[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end != -1:
            sub = candidate[idx:end]
            try:
                parsed = json.loads(sub)
            except json.JSONDecodeError:
                try:
                    parsed = json.loads(sub[:-1] + "]}")
                except json.JSONDecodeError:
                    parsed = None
            if isinstance(parsed, dict) and isinstance(parsed.get("tool_calls"), (list, dict)):
                return parsed
        search_from = idx + len(probe)


# Erkennt den Start eines nackten Tool-Call-Objekts '{"name": ...}'. Erlaubt
# '[' (Array-Anfang), ',' (Object-Separator) und — neu — Textanfang bzw.
# Zeilenumbruch davor: das Modell liefert die Calls oft OHNE
# 'tool_calls'-Wrapper und OHNE Array-Klammern, beginnt dann aber mit
# '{\n"name"' oder direkt mit '{"name"'. Vorher wurden genau diese Calls
# nicht erkannt und landeten als Roh-Fragment im sichtbaren Text.
_BARE_ARRAY_START_RE = re.compile(r"(?:^|[\[,]|\n)\s*\{\s*\"name\"\s*:")
_NAKED_WRITE_START_RE = re.compile(r"(?:^|[\[,]|\n)\s*\{\s*\"filePath\"\s*:\s*\"[^\"]+\"\s*,\s*\"content\"\s*:")
_CALL_OPENER_KEYS = (
    '"tool_calls"',
    '"arguments"',
    '"filePath"',
    '"command"',
    '"call_id"',
    '"name"',
)
_TRANSCRIPT_ECHO_START_RE = re.compile(
    r'(?:^|\n)[ \t]*(?:User|Assistant)[ \t]*:[ \t]*(?=\[?\s*\{?\s*"(?:call_id|name|content|arguments|tool_calls)")'
)
_TRANSCRIPT_ECHO_ROW_RE = re.compile(
    r'(?:\A|\n)[ \t]*(?:User|Assistant)[ \t]*:[ \t]*(?=\[?\s*\{?\s*"(?:call_id|name|content|arguments|tool_calls)")'
)
_TRANSCRIPT_ECHO_ROW_TAIL_RE = re.compile(
    r'[ \t]*(?:User|Assistant)[ \t]*:[ \t]*(?=\[?\s*\{?\s*"(?:call_id|name|content|arguments|tool_calls)")'
)
_CALL_OPENER_INLINE_RE = re.compile(r'\{\s*"(?:tool_calls|name)"\s*:')
_FUNC_CALL_NAME_RE = re.compile(r"(?<![\w.$])([A-Za-z_][A-Za-z0-9_.\-]*)\s*\(")
_INLINE_BARE_NAME_RE = re.compile(r'\{\s*"name"\s*:\s*"([A-Za-z_][A-Za-z0-9_\-]*)"')
# Obergrenze fuer zurueckgehaltenen text: darueberhinweg wird die aufbewahrung
# aufgegeben, damit ein nie geschlossener opfer keine unbegrenzte
# speicherhaltung erzeugt.
_MAX_HOLDBACK_CHARS = 262144

# Halluziniertes eigenes konversations-format: 'User: [{"call_id": "..."}]'.
# Erkennt den START einer Echo-Zeile; das JSON darin kann mehrzeilig sein
# (content enthaelt newlines), deshalb wird das blockende per balance-scan
# bestimmt, nicht per zeilenanker.
_TRANSCRIPT_ECHO_START_RE = re.compile(
    r'(?:^|\n)[ \t]*(?:User|Assistant)[ \t]*:[ \t]*(?=\[?\s*\{?\s*"(?:call_id|name|content|arguments|tool_calls)")'
)
_TRANSCRIPT_ECHO_ROW_RE = re.compile(
    r'(?:\A|\n)[ \t]*(?:User|Assistant)[ \t]*:[ \t]*(?=\[?\s*\{?\s*"(?:call_id|name|content|arguments|tool_calls)")'
)
# gleiche zeile, aber ohne den zeilenanker — wird direkt an der position
# nach whitespace geprueft (follow-up-echo-zeilen).
_TRANSCRIPT_ECHO_ROW_TAIL_RE = re.compile(
    r'[ \t]*(?:User|Assistant)[ \t]*:[ \t]*(?=\[?\s*\{?\s*"(?:call_id|name|content|arguments|tool_calls)")'
)
# Maximale praefixe, die am chunkende noch gehalten werden muessen, damit
# ein ueber chunk-grenzen verteilter echo-beginn nicht leakt.
_ECHO_ROLE_NAMES = ("user", "assistant")
# moegliche praefixlaengen des echo-beginns: 'U', 'Us', ..., 'User', 'User:',
# 'User: ', 'User: [' — jeweils nur, solange es sich um den anfang einer
# zeile handelt.
_ECHO_PREFIX_FORMS = {
    role: [role[:n] for n in range(1, len(role) + 1)] + [role + s for s in (":", ": ", ": [", ": [{")]
    for role in _ECHO_ROLE_NAMES
}


def _echo_role_prefix_len(text: str) -> int:
    """Laenge des am textende beginnenden, noch unvollstaendigen echo-
    rollen-praefixes, sonst 0 (P-06).

    Erkennt 'U', 'Us', 'User', 'user:', 'User: [', 'ASSISTANT: [{"' usw. —
    unabhaengig von gross/klein-schreibung und davon, an welcher stelle eine
    chunk-grenze den praefix zerschneidet. Erkannt wird nur an einer
    zeilengrenze; mitten im satz bleibt es normaler text."""
    lowered = text.lower()
    best = 0
    for forms in _ECHO_PREFIX_FORMS.values():
        for form in forms:
            if not lowered.endswith(form):
                continue
            pos = len(text) - len(form)
            prefix = text[:pos]
            line_start = prefix.rfind("\n") + 1
            if not prefix[line_start:].strip() and len(form) > best:
                best = len(form)
    return best
# Laufender, noch unvollstaendiger echo-präfix: die rolle steht, das json
# ist angebrochen ('User: [{"', 'User: [{"call_id": ...') und noch nicht
# balanciert — dann muss der rest des fragments zurueckgehalten werden.
_TRANSCRIPT_ECHO_OPEN_RE = re.compile(
    r'(?:\A|\n)[ \t]*(?:User|Assistant)[ \t]*:[ \t]*\[?\s*\{[^{}]*$'
)


def _balanced_json_end(text: str, start: int) -> int:
    """Index NACH dem balanced JSON-Objekt/-Array ab start, oder -1."""
    pos = start
    while pos < len(text) and text[pos] in " \t\r\n":
        pos += 1
    if pos >= len(text) or text[pos] not in "[{":
        return -1
    depth = 0
    in_str = False
    esc = False
    for i in range(pos, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


def _find_transcript_echo_span(text: str) -> tuple[int, int]:
    """(start, end) des halluzinierten transcript-echo-blocks, sonst (-1, -1).
    Das block umfasst alle aufeinanderfolgenden 'User:'/'Assistant:'-json-zeilen."""
    first = _TRANSCRIPT_ECHO_START_RE.search(text)
    if first is None:
        return -1, -1
    start = first.start() + (1 if text[first.start()] == "\n" else 0)
    pos = start
    end = -1
    while True:
        # role + json-beginn ab pos finden
        row = _TRANSCRIPT_ECHO_ROW_RE.search(text, pos if pos == 0 else max(pos - 1, 0))
        if row is None or (row.start() > pos and end != -1):
            break
        row_start = row.start() + (1 if text[row.start()] == "\n" else 0)
        # json-beginn ('[' oder '{') der zeile; find() liefert absolut
        json_start = text.find("[", row_start)
        brace = text.find("{", row_start)
        if brace != -1 and (json_start == -1 or brace < json_start):
            json_start = brace
        if json_start == -1:
            break
        obj_end = _balanced_json_end(text, json_start)
        if obj_end == -1:
            end = len(text) if end == -1 else end
            break
        end = obj_end
        # weitere aufeinanderfolgende echo-zeilen (tolerante whitespace)
        nxt = end
        while nxt < len(text) and text[nxt] in " \t\r\n":
            nxt += 1
        follow = _TRANSCRIPT_ECHO_ROW_TAIL_RE.match(text, nxt)
        if follow is None:
            break
        pos = nxt
    if end == -1:
        return -1, -1
    return start, end


def _is_structural_opener(text: str, pos: int) -> bool:
    """Steht die klammer am anfang einer zeile (bzw. auf position 0)?
    Tool-calls starten immer so; eine klammer mitten in einem satz
    ('nutze {} in CSS') ist keine call-struktur und wird nicht
    zurueckgehalten, damit normaler text live streamen kann."""
    prefix = text[:pos]
    line_start = prefix.rfind("\n") + 1
    return not prefix[line_start:].strip()


def _looks_like_call_opener(text: str, pos: int) -> bool:
    """Potenzieller tool-call ab pos? Zeilenposition plus JSON-beginn
    genuegen; ein sichtbares schluesselwort im fenster ist zusaetzlich
    ein hinweis, aber keine bedingung (beim ersten chunk ist das fenster
    noch leer)."""
    if not _is_structural_opener(text, pos):
        return False
    return text[pos:].lstrip().startswith(("{", "["))


def _find_unterminated_call_start(text: str) -> int:
    """Index, ab dem eine angebrochene tool-call-struktur steht und bis zum
    textende NICHT abgeschlossen ist, sonst -1.

    Damit ist der hold-back unabhaengig von der konkret ueber eine
    chunk-grenze zerrissenen stelle: whitespace, pretty-print, nackte
    objekte, arrays und der 'tool_calls'-wrapper werden alle erfasst.
    Ein unterminierter string (in_str am ende) zaehlt ebenfalls als
    angebrochen — genau der fall, an dem ein call mitten im content-string
    abgeschnitten wurde."""
    stack: list[tuple[str, int]] = []
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append((ch, i))
        elif ch in "}]":
            if stack:
                stack.pop()
    if in_str and stack:
        _ch, pos = stack[-1]
        if _looks_like_call_opener(text, pos):
            return pos
    for _ch, pos in reversed(stack):
        if _looks_like_call_opener(text, pos):
            return pos
    return -1


def strip_unparseable_call_fragments(text: str) -> tuple[str, int]:
    """Entfernt tool-call-Fragmente, die NICHT parsebar sind (typisch: der
    upstream-stream brach mitten im JSON ab). Sie sind nie eine echte antwort
    und duerfen nicht als sichtbarer text durchgehen.

    Greift auf zwei faelle: fragment am zeilenanfang (mit filePath/command
    auch generische opfer) und aufruf-spezifische opfer ("tool_calls",
    "name") an beliebiger position. Vor dem fragment bleibender text bleibt
    erhalten.

    Gibt (bereinigter_text, anzahl_entfernter_fragmente) zurueck."""
    if not text:
        return text, 0
    # T-09/T-05: leere call-huellen und terminator-reste sind genauso wenig
    # eine antwort wie ein abgeschnittenes fragment. Sie entstehen, wenn der
    # parser einen blockierten call entfernt hat und die huelle zuruecklässt
    # ('{"tool_calls": }') bzw. wenn ein turn mit dem rest eines
    # abgeschnittenen protokolls beginnt ('] []').
    for residue_pattern in (_EMPTY_CALL_WRAPPER_RE, _TERMINATOR_RESIDUE_RE):
        match = residue_pattern.search(text)
        if match is not None:
            return text[: match.start()].rstrip(), 1
    # T-01/T-09: ein opfer in einer ```-fence ist eine DOKUMENTATION, kein
    # abgeschnittenes protokoll. Ohne diese pruefung riss der inline-pfad
    # dokumentations-beispiele mitten im text ab ('```json {"tool_calls":…
    # ``` als Beispiel' wurde zu '```json').
    masked = _mask_code_fences(text)
    match = _UNPARSEABLE_CALL_START_RE.search(text)
    if match is not None and masked[match.start()] != match.group()[0]:
        return text, 0
    if match is not None:
        start = match.start() + (1 if text[match.start()] == "\n" else 0)
    else:
        # T-09: aufruf-spezifische opfer duerfen auch mitten in einer zeile
        # greifen — 'sieh vorher {"tool_calls":...' ist haeufig.
        inline = _CALL_OPENER_INLINE_RE.search(text)
        if inline is None or masked[inline.start()] != inline.group()[0]:
            return text, 0
        start = inline.start()
    fragment = text[start:]
    if not fragment.lstrip().startswith("{"):
        return text, 0
    if _balanced_json_end(fragment, 0) == len(fragment):
        return text, 0
    return text[:start].rstrip(), 1


def _scan_bare_objects_span(text: str, start: int) -> int:
    """Scans contiguous {"name": ..., "arguments": ...} objects starting from start."""
    pos = start
    while pos < len(text) and text[pos] in " \t\r\n,":
        pos += 1
    end = pos
    while pos < len(text):
        if text[pos] != "{":
            break
        depth = 0
        in_str = False
        esc = False
        obj_end = -1
        for i in range(pos, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    obj_end = i + 1
                    break
        if obj_end == -1:
            obj_end = len(text)
            end = obj_end
            break
        end = obj_end
        next_pos = obj_end
        while next_pos < len(text) and text[next_pos] in " \t\r\n":
            next_pos += 1
        if next_pos < len(text) and text[next_pos] == ",":
            after_comma = next_pos + 1
            while after_comma < len(text) and text[after_comma] in " \t\r\n":
                after_comma += 1
            if after_comma < len(text) and text[after_comma] == "{" and any(k in text[after_comma:after_comma+30] for k in ('"name"', '"filePath"', '"command"')):
                pos = after_comma
                continue
        elif next_pos < len(text) and text[next_pos] == "{" and any(k in text[next_pos:next_pos+30] for k in ('"name"', '"filePath"', '"command"')):
            pos = next_pos
            continue
        break
    return end


def _has_usable_arguments(tool_name: str, args_str: str | None) -> bool:
    """Trägt ein call die für sein tool erforderlichen argumente (P-03)?"""
    if not args_str or args_str in {"{}", "null"}:
        return tool_name in {"todowrite", "task", "done", "stop", "list"}
    try:
        parsed = json.loads(args_str)
    except (json.JSONDecodeError, TypeError, ValueError):
        return True
    if not isinstance(parsed, dict) or parsed:
        return True
    return tool_name in {"todowrite", "task", "done", "stop", "list"}


def _find_bare_tool_call_array(
    text: str,
    final: bool,
    allowed_tool_names: set[str] | None = None,
    *,
    detect_all: bool = False,
) -> tuple[str, str, list[dict[str, object]]] | None:
    """Leak-Variante D (Final-Run 00:27/00:33): das Modell emittiert
    Tool-Calls als NACKTES JSON-Array '[{"name": ..., "arguments": ...}]'
    oder nackte Objekte '{"name": ..., "arguments": ...}' (teils mit fuehrendem
    Komma ',{"name": ...}') — ohne {"tool_calls"}-Wrapper.
    Streng: jedes Element NUR name+arguments.
    Gibt None zurueck, wenn kein bare-Call-Protokoll gefunden wurde."""
    masked = _mask_code_fences(text)
    match = _BARE_ARRAY_START_RE.search(masked)
    if match is None:
        match = _NAKED_WRITE_START_RE.search(masked)
    if match is None:
        # hold-back: partielle array-anfaenge am textende — prefix bleibt
        # sichtbar, nur der partielle array-rest wird zurueckgehalten
        if not final:
            probe = '[{"name"'
            for length in range(min(len(text), len(probe)), 1, -1):
                if text.endswith(probe[:length]):
                    return text[:-length], text[-length:], []
        return None
    matched_prefix = masked[match.start():].lstrip()
    start = match.start() + (len(masked[match.start():]) - len(matched_prefix))
    if matched_prefix.startswith("["):
        # array-grenzen scannen: bracket-balance ueber den gesamttext ab start
        depth = 0
        in_str = False
        esc = False
        end = -1
        bracket_start = start
        for i in range(bracket_start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end == -1:
            if not final:
                return text[:start], text[start:], []
            end = len(text)
    else:
        end = _scan_bare_objects_span(text, start)
    candidate = text[start:end]
    rest = text[end:]
    # trailing '[]'-terminator + kaputtes/echtes fence-ende tolerieren
    rest_stripped = rest.lstrip()
    skipped = len(rest) - len(rest_stripped)
    consumed = skipped
    if rest_stripped.startswith("[]"):
        consumed += 2
        rest_stripped = rest_stripped[2:]
    if rest_stripped.startswith(("```", "~~~")):
        # P-13: `len(rest) - len(rest)` war immer 0 — der abschliessende
        # fence blieb im sichtbaren rest stehen (P-13). Jetzt wird die
        # zeile des abschliessenden fences korrekt uebersprungen.
        newline = rest_stripped.find("\n")
        if newline == -1:
            consumed += len(rest_stripped)
        else:
            consumed += newline + 1
        rest_stripped = rest_stripped[newline + 1 :] if newline != -1 else ""
    rest = rest[consumed:]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list) or not parsed:
        # Recovery: das modell laesst gern die schliessende ']' weg und
        # haengt direkt einen (kaputten) '``json'-marker + ein duplikat-array
        # an. name/arguments-paare einzeln extrahieren (strenge key-pruefung
        # bleibt: keys <= {name, arguments}).
        inner = candidate.strip()
        if inner.startswith("["):
            inner = inner[1:]
        recovered = _recover_call_elements(inner)
        if recovered is not None:
            rec_calls = recovered.get("tool_calls")
            if isinstance(rec_calls, list):
                parsed = [
                    item for item in rec_calls
                    if isinstance(item, dict) and set(item.keys()) <= {"name", "arguments"}
                ]
        if not isinstance(parsed, list) or not parsed:
            if not final:
                return text[:start], text[start:], []
            return None
    tool_calls: list[dict[str, object]] = []
    names: list[str] = []
    for item in parsed:
        if not isinstance(item, dict):
            return None
        keys = set(item.keys())
        if "name" not in keys:
            if "filePath" in keys and "content" in keys:
                item = {"name": "write", "arguments": dict(item)}
            elif "filePath" in keys and ("newString" in keys or "oldString" in keys):
                item = {"name": "edit", "arguments": dict(item)}
            elif "command" in keys:
                item = {"name": "bash", "arguments": dict(item)}
            elif "filePath" in keys and len(keys) == 1:
                item = {"name": "read", "arguments": dict(item)}
            else:
                return None
        name = str(item.get("name", "")).strip()
        if not name:
            return None
        names.append(name)
        # P-02: auch im Recovery-Modus bleibt die native Denylist bindend —
        # vorher liess das `or allowed_tool_names is None` jedes blockierte
        # native tool wieder durch.
        if not is_blocked_tool_name(name, None) and (
            detect_all or _is_allowed_tool_name(name, allowed_tool_names)
        ):
            args_str = _extract_call_arguments(item)
            # P-03: ein call ohne verwertbare argumente (z.B. arguments:{} bei
            # einem tool mit pflichtfeldern) ist kein ausfuehrbarer aufruf.
            # Er wird nicht geliefert — das protokoll wird trotzdem entfernt,
            # damit kein roh-json in der antwort steht.
            if not _has_usable_arguments(name, args_str):
                continue
            tool_calls.append({
                "index": len(tool_calls),
                "id": f"call_{uuid.uuid4().hex[:24]}",
                "type": "function",
                "function": {"name": name, "arguments": args_str or "{}"},
            })
    if not tool_calls:
        # nur gefilterte oder nicht ausfuehrbare calls: array strippen, kein
        # leak des rohen protokolls. Auch eine durch die argument-pruefung
        # (P-03) geleerte liste muss das protokoll entfernen.
        visible = text[:start].strip()
        if not final or find_tool_calls_protocol(rest) != -1 or _BARE_ARRAY_START_RE.search(rest):
            return visible, rest, []
        return (visible + (" " + rest.strip() if rest.strip() else "")).strip(), "", []
    visible = text[:start].strip()
    if not final or find_tool_calls_protocol(rest) != -1 or _BARE_ARRAY_START_RE.search(rest):
        return visible, rest, tool_calls
    return (visible + (" " + rest.strip() if rest.strip() else "")).strip(), "", tool_calls


def _find_json_tool_call(
    text: str,
    final: bool,
    allowed_tool_names: set[str] | None = None,
    *,
    detect_all: bool = False,
) -> tuple[str, str, list[dict[str, object]]]:
    """Findet das JSON-Tool-Protokoll: {"tool_calls":[...]}[] (mit Terminator).
    Gibt (visible, remainder, tool_calls) zurueck.

    Code-Fences sind maskiert: ein Tool-Call-Beispiel innerhalb ```...```
    wird NICHT als echter Aufruf geparst. Der Brace-Scan laeuft auf dem
    Original-Text (Argumente duerfen ihrerseits ``` enthalten)."""
    masked = _mask_code_fences(text)
    start = find_tool_calls_protocol(text)
    if start == -1:
        # partial am ende halten — NUR suffixe, die praefix des
        # tool-protokolls '{"tool_calls' sein koennen (ab 2 zeichen, also
        # '{"'). nicht jedes inline-'{': sonst stockt normaler text.
        # '}'/'"'-dynamik egal: das hier ist nur hold-back, geparsed wird
        # spaeter ohnehin der komplette block.
        if not final:
            protocol = '{"tool_calls":'
            max_hold = min(len(masked), len(protocol))
            for length in range(max_hold, 0, -1):
                if masked.endswith(protocol[:length]):
                    idx = len(text) - length
                    return text[:idx], text[idx:], []
        return text, "", []
    # komplettes JSON-objekt scannen (balanced braces, CDATA/strings beachten)
    depth = 0
    in_str = False
    esc = False
    end = -1
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == -1:
        # JSON noch unvollständig (streaming)
        if final:
            # kein terminator: trotzdem probieren bis text-ende
            end = len(text)
            candidate = text[start:]
        else:
            return text[:start], text[start:], []
    else:
        candidate = text[start:end]
    rest = text[end:] if end != -1 else ""
    # terminator '[]' oder '.[]' konsumieren (flexibel, um Fehlformatierungen
    # zu tolerieren; fuehrender whitespace zwischen JSON und terminator wird
    # mitkonsumiert, sonst leakt '[]' als sichtbarer text)
    rest_stripped = rest.lstrip()
    skipped_ws = len(rest) - len(rest_stripped)
    terminators = ("[]", ".[]")
    consumed = 0
    for t in terminators:
        if rest_stripped.startswith(t):
            consumed = len(t) + skipped_ws
            break
    if consumed:
        rest = rest[consumed:]
    elif not final and rest_stripped == "":
        # warte noch auf den terminator
        return text[:start], text[start:], []
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        # Recovery 1: GLM schliesst manchmal das aeussere objekt, laesst aber
        # die ']'-klammer des tool_calls-arrays weg — exakt diese grenze
        # reparieren, ohne modelltext davor/danach anzufassen.
        repaired = candidate[:-1] + "]}" if candidate.endswith("}") else candidate
        parsed = None
        try:
            parsed = json.loads(repaired)
        except json.JSONDecodeError:
            parsed = None
        # Recovery 2: Snipsel+Finish-Duplikat. Der Upstream streamt Token-
        # schnipsel und danach den Volltext als eigenes Delta; der buffer
        # enthaelt dann '<fragment><volltext>'. Der brace-scan endet am
        # ersten '}'-zurueck auf depth 0 — mitten im fragment, json.loads
        # scheitert. Hier scannen wir alle '{"tool_calls'-vorkommen im
        # kandidaten und nehmen die erste valide, balancierte instanz.
        if parsed is None:
            parsed = _recover_tool_calls_json(candidate)
        if parsed is None:
            parsed = _recover_call_elements(candidate)
        if parsed is None:
            return text, "", []
    calls_raw = parsed.get("tool_calls") if isinstance(parsed, dict) else None
    if isinstance(calls_raw, dict):
        calls_raw = [calls_raw]
    if not isinstance(calls_raw, list):
        return text, "", []

    # Recovery 3: Consecutive sibling tool calls (z.B. {"tool_calls":[...]}, {"name": "write", ...})
    # Falls das Modell das Array vorzeitig geschlossen und Folgetools mit Komma abgetrennt hat:
    while True:
        r_strip = rest.lstrip()
        for t in terminators:
            if r_strip.startswith(t):
                rest = r_strip[len(t):]
                r_strip = rest.lstrip()
                break
        if r_strip.startswith(","):
            after = r_strip[1:].lstrip()
        elif r_strip.startswith(('{"name"', '{"tool_calls"')):
            after = r_strip
        else:
            break
        if not after.startswith("{"):
            break
        end2 = -1
        depth2 = 0
        in_str2 = False
        esc2 = False
        for i2 in range(len(after)):
            ch2 = after[i2]
            if in_str2:
                if esc2:
                    esc2 = False
                elif ch2 == "\\":
                    esc2 = True
                elif ch2 == '"':
                    in_str2 = False
                continue
            if ch2 == '"':
                in_str2 = True
            elif ch2 == "{":
                depth2 += 1
            elif ch2 == "}":
                depth2 -= 1
                if depth2 == 0:
                    end2 = i2 + 1
                    break
        if end2 == -1:
            break
        try:
            cand2 = json.loads(after[:end2])
            if isinstance(cand2, dict):
                if "tool_calls" in cand2:
                    c2 = cand2["tool_calls"]
                    calls_raw.extend(c2 if isinstance(c2, list) else [c2])
                    rest = after[end2:]
                elif "name" in cand2:
                    calls_raw.append(cand2)
                    rest = after[end2:]
                else:
                    break
            else:
                break
        except Exception:
            break

    # Finaler Terminator-Check
    r_strip = rest.lstrip()
    for t in terminators:
        if r_strip.startswith(t):
            rest = r_strip[len(t):]
            break

    tool_calls = []
    for idx, call in enumerate(calls_raw):
        if not isinstance(call, dict):
            continue
        name = str(call.get("name", "")).strip()
        args_str = _extract_call_arguments(call)
        if name and _is_allowed_tool_name(name, allowed_tool_names) and _has_usable_arguments(name, args_str):
            tool_calls.append({
                "index": len(tool_calls),
                "id": f"call_{uuid.uuid4().hex[:24]}",
                "type": "function",
                "function": {"name": name, "arguments": args_str or "{}"},
            })
    if not tool_calls:
        if allowed_tool_names is None:
            return text, "", []
        # The block contained ONLY filtered (undeclared/blocked) tool calls.
        # Never emit the raw protocol as visible text — strip the block so
        # the caller can detect the blocked attempt via a follow-up parse
        # with allowed_tool_names=None and answer with a negative result.
        if rest.strip() and (not final or find_tool_calls_protocol(rest) != -1 or _BARE_ARRAY_START_RE.search(rest)):
            return text[:start].strip(), rest, []
        return (text[:start] + rest).strip(), "", []

    if rest.strip() and (not final or find_tool_calls_protocol(rest) != -1 or _BARE_ARRAY_START_RE.search(rest)):
        return text[:start].strip(), rest, tool_calls
    return text[:start] + rest, "", tool_calls


_UNPARSEABLE_CALL_START_RE = re.compile(r'(?:\A|\n)[ \t]*\{\s*"(?:tool_calls|name|filePath|command)"\s*:')
# T-09/T-05: leere call-huelle (blockierter call wurde entfernt, die huelle
# blieb zurueck) und der terminator-rest eines abgeschnittenen protokolls.
_EMPTY_CALL_WRAPPER_RE = re.compile(r'\s*\{\s*"tool_calls"\s*:\s*(?:\}|\]|\{\s*\}\s*,?\s*\}\s*[,;]?)')
_TERMINATOR_RESIDUE_RE = re.compile(r'(?:\A|(?<=\s))\][ \t]*\[\](?=\s|\Z)')


def _split_stream_text(
    text: str,
    allowed_tool_names: set[str] | None,
    final: bool,
    *,
    detect_all: bool = False,
) -> tuple[str, str, list[dict[str, object]]]:
    # 0) Halluziniertes eigenes konversations-format (V-01/THEMA 5):
    #    'User: [{"call_id": ...}]' ist nie eine echte antwort.
    echo_start, echo_end = _find_transcript_echo_span(text)
    if echo_start != -1:
        if not final:
            return text[:echo_start], text[echo_start:], []
        return _split_stream_text(
            text[:echo_start] + text[echo_end:],
            allowed_tool_names,
            final=True,
            detect_all=detect_all,
        )
    if not final:
        # Angebrochene call-strukturen generisch zurueckhalten: der
        # hold-back leitet sich aus derselben JSON-struktur ab wie die
        # vollstaendige erkennung und ist dadurch ueber jede chunk-grenze
        # hinweg stabil (V-01).
        open_call = _find_unterminated_call_start(text)
        if open_call != -1:
            return text[:open_call], text[open_call:], []
        echo_prefix = _echo_role_prefix_len(text)
        if echo_prefix:
            return text[:-echo_prefix], text[-echo_prefix:], []
        echo_row = _TRANSCRIPT_ECHO_ROW_RE.search(text)
        if echo_row is not None:
            row_start = echo_row.start() + (1 if text[echo_row.start()] == "\n" else 0)
            if _balanced_json_end(text, row_start) == -1:
                return text[:row_start], text[row_start:], []
    # 0) Halluziniertes eigenes konversations-format: das Modell schreibt
    #    'User: [{"call_id": "..."}]'-zeilen (seine eigene transcript-
    #    representation) als antwort. Nie eine echte antwort. Im stream
    #    zurueckhalten (chunk-grenzen uebergreifend), bei final entfernen
    #    und den text danach weiterverarbeiten.
    echo_start, echo_end = _find_transcript_echo_span(text)
    if echo_start != -1:
        if not final:
            return text[:echo_start], text[echo_start:], []
        return _split_stream_text(
            text[:echo_start] + text[echo_end:],
            allowed_tool_names,
            final=True,
        )
    if not final:
        # P-06: die echo-rolle darf nicht emittiert werden, sobald sie
        # angefangen wurde — unabhaengig von gross/klein-schreibung und
        # davon, wo eine chunk-grenze den praefix zerschneidet. Ein ganzes
        # wort wird nur an einer zeilengrenze gehalten; mitten im satz
        # bleibt es normaler text.
        echo_prefix = _echo_role_prefix_len(text)
        if echo_prefix:
            return text[:-echo_prefix], text[-echo_prefix:], []
        if _TRANSCRIPT_ECHO_OPEN_RE.search(text):
            echo_start, echo_end = _find_transcript_echo_span(text)
            if echo_start == -1:
                return "", text, []

    # 1) JSON-Protokoll prüfen (neues Format); ohne Treffer bleibt nur der
    # Partial-Suffix-Holdback von _find_json_tool_call relevant.
    if find_tool_calls_protocol(text) != -1:
        visible, remainder, tool_calls = _find_json_tool_call(
            text, final, allowed_tool_names, detect_all=detect_all
        )
        if tool_calls:
            return visible, remainder, tool_calls
        # P-03: protokoll erkannt, aber jeder call wurde gefiltert oder
        # war nicht ausfuehrbar. Der bereinigte text muss uebernommen
        # werden, sonst bleibt das roh-protokoll als antwort stehen.
        if visible != text:
            return visible, remainder, []
    visible, remainder, tool_calls = _find_json_tool_call(text, final, allowed_tool_names, detect_all=detect_all)
    if tool_calls or (remainder and not final):
        return visible, remainder, tool_calls

    # 1b) Leak-Variante D: nacktes JSON-array als tool-protokoll
    bare = _find_bare_tool_call_array(text, final, allowed_tool_names, detect_all=detect_all)
    if bare is not None:
        bare_visible, bare_remainder, bare_calls = bare
        if bare_calls or (bare_remainder and not final):
            return bare_visible, bare_remainder, bare_calls
        # P-03: der bare-finder hat ein vollstaendig gefiltertes protokoll
        # korrekt aus dem sichtbaren text entfernt und liefert leere
        # calls. Im final-fall wurde dieses bereinigte ergebnis verworfen
        # und der unbereinigte text erneut ausgegeben — das protokoll
        # leakte. Wir uebernehmen die bereinigung auch ohne calls.
        if not bare_calls and bare_visible != text:
            return bare_visible, "", []

    # nur konkrete positionen verwenden — die helfer geben None zurueck,
    # wenn sie nichts finden
    hold_from_candidates = [
        index
        for index in (_find_unmatched_fence_start(text), _find_incomplete_block_start(text, allow_trailing_close=final))
        if index is not None
    ]

    if not final:
        partial_start = _find_partial_tag_start(text)
        if partial_start is not None:
            hold_from_candidates.append(partial_start)
        # P-04: angebrochene text-funktionsaufrufe (read("…", bash("…))
        # zurueckhalten. Sonst wird jeder teil sofort emittiert und der
        # streampfad erkennt den aufruf nie, waehrend der finalpfad ihn
        # noch als call repararieren wuerde — die beiden pfade liefeu
        # auseinander.
        func_partial = _find_partial_text_function_start(text)
        if func_partial is not None:
            hold_from_candidates.append(func_partial)

    if final:
        safe_end = min(hold_from_candidates) if hold_from_candidates else len(text)
    elif hold_from_candidates:
        safe_end = min(hold_from_candidates)
    else:
        safe_end = len(text)

    processable = text[:safe_end]
    remainder = text[safe_end:]
    spans, tool_calls = _extract_tool_blocks(processable, allowed_tool_names, allow_trailing_close=final)
    if not tool_calls:
        # P-04: gleicher recovery-fallback wie im final-parser, damit
        # stream- und finalpfad fuer dieselbe eingabe zum selben ergebnis
        # kommen. Nur auf bereits geschlossenen text angewandt (kein
        # fragment), sonst wuerde ein halber aufruf als call gelten.
        func_call = _find_text_function_call(
            processable, allowed_tool_names=allowed_tool_names
        )
        if func_call is not None and func_call[1]:
            f_vis, f_calls = func_call
            return f_vis, remainder, f_calls
    visible = _remove_spans(processable, spans, trim_outer_whitespace=final)
    return visible, remainder, tool_calls


_TEXT_FUNC_CALL_RE = re.compile(
    r'^\s*(read|write|edit|bash|webfetch|todowrite|glob|grep)\s*\(\s*(?:filePath\s*=\s*)?["\']([^"\']+)["\']\s*\)\s*$',
    re.MULTILINE,
)


_TEXT_FUNC_NAMES = ("read", "write", "edit", "bash", "webfetch", "todowrite", "glob", "grep")


def _find_partial_text_function_start(text: str) -> int | None:
    """Start eines angebrochenen text-funktionsaufrufs am zeilenanfang
    (P-04), sonst None. Nur die zeilenanfangsform wird gehalten, damit
    ein erwaehnung im fliesstext ('nutze read("x") zum lesen') nicht
    haengen bleibt."""
    for name in _TEXT_FUNC_NAMES:
        idx = text.rfind(name)
        while idx != -1:
            prefix = text[:idx]
            line_start = prefix.rfind("\n") + 1
            if not prefix[line_start:].strip() and text[idx + len(name) : idx + len(name) + 1] in {"(", ""}:
                rest = text[idx + len(name) :]
                # holdback, solange der aufruf nicht geschlossen ist — bzw.
                # immer, wenn er am chunk-ende abgeschnitten wurde
                if not rest or rest.count("(") > rest.count(")") or not rest.strip().endswith(")"):
                    return idx
                return None
            idx = text.rfind(name, 0, idx)
    return None


def _find_text_function_call(
    text: str,
    allowed_tool_names: set[str] | None = None,
) -> tuple[str, list[dict[str, object]]] | None:
    match = _TEXT_FUNC_CALL_RE.search(text)
    if not match:
        return None
    # T-01: die zeile darf nicht in einem code-fence liegen. Sonst wurde
    # eine dokumentationszeile ('read("config.py")' im python-beispiel) zu
    # einem echten tool-call und verschwand aus der antwort.
    masked = _mask_code_fences(text)
    if masked[match.start() : match.end()].strip("") != match.group(0).strip(""):
        return None
    tool_name, arg = match.groups()
    if not _is_allowed_tool_name(tool_name, allowed_tool_names):
        return None
    if tool_name == "read":
        args = {"filePath": arg}
    elif tool_name == "bash":
        args = {"command": arg}
    elif tool_name == "webfetch":
        args = {"url": arg}
    else:
        return None
    call = {
        "index": 0,
        "id": f"call_{uuid.uuid4().hex[:24]}",
        "type": "function",
        "function": {"name": tool_name, "arguments": json.dumps(args)},
    }
    visible = (text[:match.start()] + text[match.end():]).strip()
    return visible, [call]


def _unwrap_protocol_only_fence(text: str) -> str | None:
    """Entpackt ein fence, dessen inhalt AUSSCHLIESSLICH das tool-protokoll
    ist (P-11). Gibt None zurueck, wenn das fence nicht ausschliesslich
    protokoll enthaelt oder gar kein fence vorhanden ist — dann greift die
    normale fence-maskierung, damit echte doku-beispiele im text bleiben."""
    match = CODE_FENCE_PATTERN.search(text)
    if match is None:
        return None
    if CODE_FENCE_PATTERN.search(text, match.end()):
        # mehrere fences: keiner davon ist "nur protokoll"
        return None
    if text[: match.start()].strip():
        return None
    inner = match.group(0).strip("`~").strip()
    lowered = inner.lower()
    for prefix in ("json", "jsonc", ""):
        candidate = inner[len(prefix) :].strip() if lowered.startswith(prefix) else inner
        if not candidate:
            continue
        if (
            find_tool_calls_protocol(candidate) != -1
            or _BARE_ARRAY_START_RE.search(candidate) is not None
        ):
            return text[: match.start()] + candidate + text[match.end() :]
    return None


def parse_tool_calls_from_text(
    text: str,
    allowed_tool_names: set[str] | None = None,
    *,
    detect_all: bool = False,
) -> tuple[str, list[dict[str, object]]]:
    """Zerlegt Modelltext in (sichtbarer_text, tool_calls).

    `allowed_tool_names` ist die vom Client deklarierte Allowlist; `None`
    bedeutet 'keine Tools deklariert' und erzeugt dann KEINE Calls aus
    Quelltext. `detect_all=True` schaltet den internen Recovery-Modus fuer
    die Diagnose frei."""
    if not text:
        return "", []
    # P-11: ein fence, das AUSSCHLIESSLICH das tool-protokoll enthaelt, ist
    # keine doku und wird entpackt statt maskiert. Sonst blieb ein echter
    # call in ```json ... ``` unerkannt und landete als text.
    unwrapped = _unwrap_protocol_only_fence(text)
    if unwrapped is not None:
        text = unwrapped
    echo_start, echo_end = _find_transcript_echo_span(text)
    if echo_start != -1:
        text = text[:echo_start] + text[echo_end:]
        if not text.strip():
            return "", []
    # Halluziniertes eigenes konversations-format zuerst entfernen — es ist
    # nie ein tool-call und darf nie als antwort durchgehen.
    echo_start, echo_end = _find_transcript_echo_span(text)
    if echo_start != -1:
        text = text[:echo_start] + text[echo_end:]
        if not text.strip():
            return "", []
    # zuerst neues JSON-protokoll pruefen
    visible, remainder, tool_calls = _find_json_tool_call(
        text, final=True, allowed_tool_names=allowed_tool_names, detect_all=detect_all
    )
    if tool_calls:
        return visible, tool_calls
    # P-03: protokoll erkannt, aber jeder call wurde gefiltert oder war nicht
    # ausfuehrbar. Der bereinigte text muss uebernommen werden, sonst bleibt
    # das roh-protokoll als antwort stehen.
    if visible != text:
        return visible, []
    # Leak-Variante D: nacktes JSON-array als tool-protokoll
    bare = _find_bare_tool_call_array(text, final=True, allowed_tool_names=allowed_tool_names, detect_all=detect_all)
    if bare is not None:
        bare_visible, _, bare_calls = bare
        if bare_calls:
            return bare_visible, bare_calls
        if bare_visible != text:
            return bare_visible, []
    if allowed_tool_names is None and not detect_all:
        # Ohne deklarierte Tools wird nie ein Call aus Quelltext erzeugt.
        return text, []
    # P-04: der text-funktions-fallback (read("…"), bash("…")) ist der
    # dokumentierte recovery-pfad fuer faelle, in denen das Modell gar kein
    # JSON-protokoll emittiert (live-fall ses_f2bcdbfb8ffe). Er wird deshalb
    # hier bewusst NICHT deaktiviert. Die paritaet zwischen stream- und
    # finalpfad entsteht dadurch, dass consume_event() den gesamten
    # zurueckgehaltenen text im finalize ueber parse_tool_calls_from_text
    # laufen laesst — ein frueher stream-emitierter teil wird dort erneut
    # erfasst. (siehe test_parity_matrix_stream_and_non_stream_agree_on_garbage)
    func_call = _find_text_function_call(text, allowed_tool_names=allowed_tool_names)
    if func_call is not None:
        f_vis, f_calls = func_call
        if f_calls:
            return f_vis, f_calls
    spans, tool_calls = _extract_tool_blocks(text, allowed_tool_names, allow_trailing_close=True)
    return _remove_spans(text, spans), tool_calls


def detect_tool_call_names(text: str) -> list[str]:
    """Erkennt Tool-Call-Namen OHNE Allow-Filter (auch BLOCKED_NATIVE wie
    open_url). Dient nur der Diagnose blockierter Versuche — niemals zur
    Ausfuehrung: das Ergebnis wird fuer negative tool-results genutzt."""
    if not text:
        return []
    names: list[str] = []
    masked = _mask_code_fences(text)
    start = find_tool_calls_protocol(text)
    if start != -1:
        depth = 0
        in_str = False
        esc = False
        end = -1
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end != -1:
            try:
                parsed = json.loads(text[start:end])
            except json.JSONDecodeError:
                parsed = None
            calls_raw = parsed.get("tool_calls") if isinstance(parsed, dict) else None
            if isinstance(calls_raw, dict):
                calls_raw = [calls_raw]
            if isinstance(calls_raw, list):
                for call in calls_raw:
                    if isinstance(call, dict):
                        name = str(call.get("name", "")).strip()
                        if name:
                            names.append(name)
    for pattern in (
        re.compile(r"<\|?dsml\|?invoke\s+name=[\"']([^\"']+)[\"']", re.IGNORECASE),
        re.compile(r"<invoke\s+name=[\"']([^\"']+)[\"']", re.IGNORECASE),
    ):
        for match in pattern.finditer(masked):
            name = match.group(1).strip()
            if name:
                names.append(name)
    # T-10: auch bare-arrays, nackte objekte und abgeschnittene formen
    # erfassen — bisher wurden nur json-wrapper und xml erkannt, wodurch
    # blockierte versuche in diesen formen unentdeckt blieben. Rein
    # textbasiert, damit die denylist hier nichts verschluckt.
    for pattern in (_BARE_ARRAY_START_RE, _INLINE_BARE_NAME_RE):
        for match in pattern.finditer(masked):
            name = ""
            if pattern is _INLINE_BARE_NAME_RE:
                name = match.group(1)
            else:
                window = masked[match.end() : match.end() + 200]
                name_match = re.search(r'"name"\s*:\s*"([A-Za-z_][A-Za-z0-9_\-]*)"', window)
                if name_match:
                    name = name_match.group(1)
            name = name.strip()
            if name:
                names.append(name)
    # T-10 (nachtrag): funktionssyntax. Das modell schreibt tool-aufrufe
    # auch als `open_url("https://…")` — diese Form war voellig blind und
    # liess einen blockierten versuch als leeren stop-turn durchgehen. Das
    # vokabular ist absichtlich geschlossen (nur bekannte tool-namen), damit
    # ein normaler funktionsaufruf im prosatext keine negative
    # follow-up-runde ausloest.
    known_tool_names = {name.lower() for name in BLOCKED_NATIVE_TOOL_NAMES}
    known_tool_names.update(name.lower() for name in _TEXT_FUNC_NAMES)
    for match in _FUNC_CALL_NAME_RE.finditer(masked):
        candidate = match.group(1)
        if candidate.lower() not in known_tool_names:
            continue
        names.append(candidate)
    # Reihenfolge erhalten, Duplikate entfernen: dieselbe struktur wird von
    # mehreren formen erkannt (wrapper + bare-namensregex).
    seen: set[str] = set()
    unique: list[str] = []
    for name in names:
        if name not in seen:
            seen.add(name)
            unique.append(name)
    return unique


@dataclass
class StreamingToolParser:
    pending_text: str = ""
    tool_calls: list[dict[str, object]] = field(default_factory=list)
    allowed_tool_names: set[str] | None = None
    detect_all: bool = False
    buffering_dsml: bool = False
    _holdback_warned: bool = False

    def logger_warning_once(self, message: str) -> None:
        """Warnung genau einmal pro parser (P-14: puffer-grenzen-warnung)."""
        if self._holdback_warned:
            return
        self._holdback_warned = True
        logging.getLogger("glm2api.tool_parser").warning("%s", message)

    def consume(self, chunk: str) -> str:
        if not chunk:
            return ""
        self.pending_text += chunk

        if self.buffering_dsml:
            # P-14: puffer darf nicht unbegrenzt wachsen — ein niemals
            # geschlossener markup-opfer wuerde sonst den speicher
            # auffressen. Obergrenze: dann aufgeben und ausgeben.
            if len(self.pending_text) > _MAX_HOLDBACK_CHARS:
                self.logger_warning_once(
                    "tool-markup holdback limit reached, releasing buffer as visible text"
                )
                self.buffering_dsml = False
                released = self.pending_text
                self.pending_text = ""
                return released
            return ""

        # Once a tool-markup opener starts, keep the complete block buffered.
        # Parsing individual stream characters must never expose internal DSML/XML.
        # P-07: zero-width-space (U+200B) vor markup neutralisieren, sonst
        # wird <\u200btool_call> weder erkannt noch ausgegeben.
        if "\u200b" in self.pending_text:
            self.pending_text = self.pending_text.replace("\u200b", "")
        markup_starts = [
            index
            for marker in TAG_NAME_HINTS
            if (index := self.pending_text.lower().find(marker.lower())) != -1
        ]
        if markup_starts:
            start = min(markup_starts)
            prefix = self.pending_text[:start]
            self.pending_text = self.pending_text[start:]
            if self.pending_text.lower().startswith("<|"):
                # P-14: das generische '<|' aktivierte den dsml-puffer fuer
                # JEDEN rest des turns. Ein niemals geschlossener opfer liess
                # den puffer unbegrenzt wachsen. Obergrenze einfuehren: wird
                # sie ueberschritten, wird der puffer aufgegeben und der
                # text als sichtbar ausgegeben (besser als speicherleck).
                if len(self.pending_text) > _MAX_HOLDBACK_CHARS:
                    self.logger_warning_once("tool-markup holdback limit reached, releasing buffer")
                    self.buffering_dsml = False
                    released = self.pending_text
                    self.pending_text = ""
                    return prefix + released
                self.buffering_dsml = True
                return prefix
            start_match = START_TAG_PATTERN.search(self.pending_text)
            matched_span = _find_matching_block(self.pending_text, start_match) if start_match else None
            if matched_span is None or matched_span[1] == len(self.pending_text):
                return prefix
            visible, remainder, parsed_calls = _split_stream_text(
                self.pending_text,
                allowed_tool_names=self.allowed_tool_names,
                final=False,
                detect_all=self.detect_all,
            )
            self.pending_text = remainder
            self.tool_calls.extend(parsed_calls)
            return prefix + visible

        # JSON-tool-protokoll: partial am ende halten, komplette sofort parsen
        if find_tool_calls_protocol(self.pending_text) != -1:
            emitted_vis: list[str] = []
            while find_tool_calls_protocol(self.pending_text) != -1:
                jvis, jrem, jcalls = _find_json_tool_call(self.pending_text, final=False, allowed_tool_names=self.allowed_tool_names, detect_all=self.detect_all)
                if jvis:
                    emitted_vis.append(jvis)
                self.tool_calls.extend(jcalls)
                if jrem == self.pending_text:
                    break
                self.pending_text = jrem
            return "".join(emitted_vis)

        # Angebrochene call-strukturen generisch zurueckhalten, BEVOR die
        # format-spezifischen pfade laufen (V-01). Deren eigener hold-back
        # greift nur bei fest verdrahteten praefixen.
        open_call = _find_unterminated_call_start(self.pending_text)
        if open_call != -1 and len(self.pending_text) <= _MAX_HOLDBACK_CHARS:
            visible, remainder, parsed_calls = _split_stream_text(
                self.pending_text,
                allowed_tool_names=self.allowed_tool_names,
                final=False,
                detect_all=self.detect_all,
            )
            self.pending_text = remainder
            self.tool_calls.extend(parsed_calls)
            return visible
        # P-04: angebrochene text-funktionsaufrufe ebenfalls halten, sonst
        # wird jeder teil emittiert und der streampfad erkennt den aufruf
        # nie, waehrend der finalpfad ihn noch reparieren wuerde.
        func_partial = _find_partial_text_function_start(self.pending_text)
        if func_partial is not None and len(self.pending_text) <= _MAX_HOLDBACK_CHARS:
            visible, remainder, parsed_calls = _split_stream_text(
                self.pending_text,
                allowed_tool_names=self.allowed_tool_names,
                final=False,
                detect_all=self.detect_all,
            )
            self.pending_text = remainder
            self.tool_calls.extend(parsed_calls)
            return visible

        # Check partial JSON holdback
        jvis, jrem, jcalls = _find_json_tool_call(self.pending_text, final=False, allowed_tool_names=self.allowed_tool_names, detect_all=self.detect_all)
        if jrem:
            self.pending_text = jrem
            return jvis
        visible, remainder, parsed_calls = _split_stream_text(
            self.pending_text,
            allowed_tool_names=self.allowed_tool_names,
            final=False,
        )
        self.pending_text = remainder
        self.tool_calls.extend(parsed_calls)
        return visible

    def flush(self) -> tuple[str, list[dict[str, object]]]:
        all_visible: list[str] = []
        while self.pending_text:
            visible, remainder, parsed_calls = _split_stream_text(
                self.pending_text,
                allowed_tool_names=self.allowed_tool_names,
                final=True,
                detect_all=self.detect_all,
            )
            if parsed_calls:
                self.tool_calls.extend(parsed_calls)
                if visible:
                    all_visible.append(visible)
                if remainder == self.pending_text:
                    break
                self.pending_text = remainder
                continue
            else:
                if visible:
                    all_visible.append(visible)
                self.pending_text = remainder
            break
        tail = "" if _looks_like_tool_markup_fragment(self.pending_text) else self.pending_text
        self.pending_text = ""
        self.buffering_dsml = False
        return (" ".join(all_visible) + (" " + tail if tail else "")).strip(), self.tool_calls
