from __future__ import annotations

import ast
import json
import logging
import re
import time
from bisect import insort
from collections.abc import Mapping
from dataclasses import dataclass, field
from logging import Logger
from typing import Any
from urllib.parse import urlsplit

from ..config import AppConfig
from ..logging_utils import debug_dump
from ..model_variants import model_requests_search, model_requests_thinking, split_model_features
from ..utils.tool_parser import (
    count_blocked_call_fragments,
    CODE_FENCE_PATTERN,
    StreamingToolParser,
    _find_unterminated_call_start,
    detect_tool_call_names,
    parse_tool_calls_from_text,
    strip_unparseable_call_fragments,
    text_continues_protocol,
)
from ..utils.tool_protocol import (
    strip_unterminated_tool_prefix,
    BLOCKED_NATIVE_TOOL_NAMES,
    is_blocked_tool_name,
    CANONICAL_TOOL_CALL_EXAMPLE,
    TOOL_FORMAT_REMINDER,
    build_tool_call_instructions as _protocol_build_tool_call_instructions,
    filter_tools,
    safe_json_dumps,
    serialize_tool_call_block as _protocol_serialize_tool_call_block,
    serialize_tool_result_block as _protocol_serialize_tool_result_block,
    tools_to_prompt as _protocol_tools_to_prompt,
)

# Grobe Zeichen-pro-Token-Schaetzung fuer die Ausgabegrenze: der
# upstream liefert keine Tokenzahl, ~4 Zeichen/Token ist die uebliche
# Naeherung fuer gemischten Text.
_CHARS_PER_TOKEN_ESTIMATE = 4

# Das aufgabenbudget ist zwischen zwei kanaelen zu verteilen: dem internen
# denkkanal (`reasoning_content`) und dem LIEFERKANAL (text + tool_calls,
# aus dem der parser die aufrufe gewinnt).
#
# Ohne diese reservierung fraess das reasoning bei `reasoning_effort: max`
# das gesamte budget. Gemessen an einer echten opencode-session
# (2026-09-25): reasoning_len=61 820 zeichen, der client bekam 1 768
# zeichen reasoning, NULL text und NULL tool_calls, `finish_reason: length`.
# Der agent hatte damit einen abgeschlossenen, erfolgreichen turn, in dem
# nichts zu tun war — er wartet vergeblich auf eine antwort, die nie
# kommen kann. Der auftrag war schlicht unerfuellbar.
#
# 30 % reserviert: genug fuer eine echte antwort oder einen tool-aufruf,
# auch bei sehr langem denkprozess. Das reasoning kann weiterhin 70 % des
# budgets nutzen — das ist der normale, grosse anteil.
_REASONING_BUDGET_SHARE = 0.7

ASSISTANT_ID_PATTERN = re.compile(r"^[a-z0-9]{24,}$")
URL_PATTERN = re.compile(r"https?://[^\s<>()\"']+")

_LOGGER = logging.getLogger("glm2api.translator")

# THEMA 3 (optimierung.md): C0-Steuerzeichen ausser \n \t \r (plus DEL) sind
# in Tool-Argumenten und sichtbarem Content nie legitim — das Modell streamt
# sie gelegentlich alsEncoding-Verderb (z.B. 'zur\u0014ck' statt 'zurück').
_C0_ALLOWED = {"\n", "\t", "\r"}


def _call_is_executable(tool_call: dict[str, object]) -> bool:
    """Trägt ein call die für sein tool erforderlichen argumente?

    Wird nach einer durchgesetzten Ausgabegrenze geprüft: ein am
    Abschrittpunkt halbfertiger call würde sonst als ausführbare
    Anweisung beim Client landen."""
    function = tool_call.get("function")
    if not isinstance(function, dict):
        return False
    name = str(function.get("name", "")).strip()
    raw_args = str(function.get("arguments", "")).strip()
    if raw_args in {"", "{}", "null"}:
        return name in {"todowrite", "task", "done", "stop", "list"}
    try:
        parsed = json.loads(raw_args)
    except (json.JSONDecodeError, TypeError, ValueError):
        # nicht parsebares argument-json: als roh-string weitergeben kann der
        # sanitizer reparieren, aber es ist nie sicher ausfuehrbar
        return False
    if not isinstance(parsed, dict) or parsed:
        return True
    return name in {"todowrite", "task", "done", "stop", "list"}


def _tool_call_signature(tool_call: dict[str, object]) -> str:
    """Name + normalisierte argumente — unabhaengig von der call-id (T-03)."""
    function = tool_call.get("function")
    name = ""
    arguments = "{}"
    if isinstance(function, dict):
        name = str(function.get("name", "")).strip()
        arguments = str(function.get("arguments", "{}"))
    try:
        parsed = json.loads(arguments)
    except (json.JSONDecodeError, TypeError):
        parsed = arguments
    rendered = arguments if isinstance(parsed, str) else safe_json_dumps(parsed)
    return f"{name}:{rendered}"


def _dedupe_tool_call_list(tool_calls: list[dict[str, object]]) -> list[dict[str, object]]:
    """T-05: entfernt doppelte calls innerhalb einer liste.

    Maßgeblich ist die call-id. Nur wenn eine der beiden **keine** id hat,
    entscheidet die signatur — sonst wuerden zwei bewusst gleiche aufrufe
    mit eigener id kollabieren (T-04)."""
    seen_ids: set[str] = set()
    seen_signatures_without_id: set[str] = set()
    unique: list[dict[str, object]] = []
    for tool_call in tool_calls:
        call_id = _coerce_call_id(tool_call.get("id"))
        if call_id:
            if call_id in seen_ids:
                continue
            seen_ids.add(call_id)
            unique.append(tool_call)
            continue
        signature = _tool_call_signature(tool_call)
        if signature in seen_signatures_without_id or signature in seen_ids:
            continue
        seen_signatures_without_id.add(signature)
        unique.append(tool_call)
    return unique


def _tool_call_identity(tool_call: dict[str, object]) -> str:
    """Identitaet eines tool-calls fuer die deduplizierung (T-04).

    Primaer die call-id: zwei calls mit unterschiedlicher id sind zwei
    aufrufe, auch bei identischen argumenten. Ohne id greift der
    name + die normalisierten argumente."""
    # T-11: `str(None)` erzeugte die id "None" — eine scheinbar gueltige,
    # aber erfundene call-id. Eine fehlende oder explizit null gesetzte id
    # ist eine LEERE id und wird als solche gefuehrt.
    call_id = _coerce_call_id(tool_call.get("id"))
    if call_id:
        return f"id:{call_id}"
    function = tool_call.get("function")
    name = arguments = ""
    if isinstance(function, dict):
        name = str(function.get("name", "")).strip()
        arguments = str(function.get("arguments", "")).strip()
    try:
        parsed = json.loads(arguments) if arguments else None
        arguments = json.dumps(parsed, sort_keys=True, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return f"sig:{name}:{arguments}"


def _merge_tool_calls(
    server_side: list[dict[str, object]],
    text_calls: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Fuehrt native und text/xml-calls zusammen, ohne doppelte
    auszuliefern (T-03/T-04), und nummeriert sie durch."""
    merged: list[dict[str, object]] = []
    seen: set[str] = set()
    # T-03: derselbe aufruf kann in BEIDEN quellen auftauchen (nativ und
    # text/xml). Die identitaet ist die call-id — ein text-call bekommt aber
    # bei jedem parse eine frische uuid und gleicht damit nie. Also
    # zusaetzlich ueber name + normalisierte argumente abgleichen, aber nur
    # QUELLUEBERGREIFEND: der text-call ist dann das echo des nativen.
    # Zwei bewusst gleiche calls in derselben quelle (mit eigener id)
    # bleiben erhalten (T-04).
    server_side_signatures = {_tool_call_signature(call) for call in server_side}
    for source_call in server_side:
        identity = _tool_call_identity(source_call)
        if identity in seen:
            continue
        seen.add(identity)
        entry = dict(source_call)
        entry["index"] = len(merged)
        merged.append(entry)
    for text_call in text_calls:
        identity = _tool_call_identity(text_call)
        if identity in seen:
            continue
        if server_side and _tool_call_signature(text_call) in server_side_signatures:
            # echo eines nativen calls aus der text-quelle
            continue
        seen.add(identity)
        entry = dict(text_call)
        entry["index"] = len(merged)
        merged.append(entry)
    return merged


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
    # T-19: non-text-items des incoming uebernehmen (bilder etc.) — aber
    # NUR, wenn sie nicht schon vorhanden sind. Vorher wurden sie bei
    # jedem update erneut angehaengt: ein bild-im-part nach fuenf
    # updates stand fuenfmal im content.
    for item in inc_content:
        if isinstance(item, dict) and item.get("type") != "text" and item not in non_text_old:
            merged["content"].append(item)
    # T-19: der berechnete eingangs-status wurde nie geschrieben — ein part
    # behielt nach dem finish-fragment sein 'init'. Das pruefte downstream
    # auf den volltext (bei "finish" notwendig, sonst "update").
    if incoming_status:
        merged["status"] = incoming_status
    return merged


def _coerce_call_id(value: object) -> str:
    """T-11: eine call-id ist ein string. `None`, Zahlen und leere Werte
    duerfen NICHT zu "None"/"1234" werden — das waere eine erfundene,
    scheinbar gueltige id, die beim roundtrip einen call mit falscher
    zuordnung erzeugt."""
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "none" else text


def _extract_nested_url(value: object) -> str:
    """T-23: akzeptiert `{"url": …}`, `{"image_url": {"url": …}}` und
    einen blossen string — ohne AttributeError."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        nested = value.get("url")
        if isinstance(nested, str):
            return nested
        image_url = value.get("image_url")
        if isinstance(image_url, dict) and isinstance(image_url.get("url"), str):
            return str(image_url["url"])
    return ""


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
        elif item_type in {"thinking", "redacted_thinking"}:
            # A-02: der adapter modelliert thinking und redacted_thinking
            # korrekt, aber `extract_text_content` kannte nur `text`,
            # `image_url` und `file`. Die Denkkette verschwand damit
            # VOR dem modell: das modell bekam seinen eigenen
            # gedankengang nie zurueck und musste alles neu herleiten.
            # Der inhalt wird als normaler text in die historie
            # uebernommen (es ist gedankeninhalt, kein werkzeugaufruf).
            thinking = item.get("thinking") or item.get("data") or item.get("text")
            if isinstance(thinking, str) and thinking.strip():
                text_parts.append(thinking)
        elif item_type == "image_url":
            # T-23: `image_url` ist laut schema ein OBJEKT, kommt aber
            # auch als reiner string vor. Das ungepruefte `.get()` brach
            # mit AttributeError ab — aus einem schiefen content-item
            # wurde ein 500er statt eines verstaendlichen texts.
            url = _extract_nested_url(item.get("image_url"))
            text_parts.append(f"[image:{url}]")
        elif item_type == "file":
            url = _extract_nested_url(item.get("file_url"))
            text_parts.append(f"[file:{url}]")
        elif item_type == "file_url":
            url = _extract_nested_url(item.get("file_url"))
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


# T-23: parameter, die nach namenskonvention SKALAR sind. Der proxy hat
# kein schema, mit dem er den zieltyp bestimmen koennte — fuer diese
# namen ist ein JSON-objekt/-array mit hoher wahrscheinlichkeit der
# gewollte STRING, und ein stiller typwechsel wuerde sie zerstoeren
# (`{"url": "{\"a\":1}"}` wurde zu `{"url": {"a": 1}}`).
# Alles andere — `command` (powerShell-argv-liste), `questions`, `meta`
# usw. — darf weiterhin entpackt werden.
_SCALAR_VALUE_PARAMETERS = frozenset(
    {
        "url",
        "uri",
        "fileurl",
        "image_url",
        "filepath",
        "path",
        "q",
        "query",
        "text",
        "content",
        "prompt",
        "description",
        "message",
        "name",
        "id",
        "newstring",
        "oldstring",
        "notebook_path",
        "pattern",
    }
)


def _expects_structured_value(key: str, all_arguments: dict[str, object]) -> bool:
    """Darf dieser parameter ein JSON-objekt/-array als wert tragen?

    Nur wenn der name nicht zu den bekannten skalaren parametern gehoert.
    Die Liste folgt der OpenAI/Anthropic-Tool-Konvention, in der
    `url`, `filePath`, `path`, `content` und `q` immer String sind."""
    return key.lower() not in _SCALAR_VALUE_PARAMETERS


def _scan_string_end(text: str, start: int) -> int:
    """Index des schliessenden anfuehrungszeichens, escape-bewusst.

    T-23: das feldende wurde mit `rfind('"')` bestimmt — das findet das
    LETZTE anfuehrungszeichen der zeile, nicht das des felds. Aus
    `{"filePath":"/a","content":"hello","other":"z"}` wurde so
    `content: 'hello","other":"z'` — bei einem bash-auftrag eine
    ausfuehrungsrelevante datenbeschädigung. Hier wird stattdessen
    vorwaerts gescannt; escapes (`\\"`, `\\\\`) ueberspringen.

    Ist der string abgeschnitten (kein schliessendes zeichen), wird das
    textende zurueckgegeben: der rest IST dann der wert."""
    index = start
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == '"':
            return index
        index += 1
    return len(text)


def repair_raw_tool_args(tool_name: str, raw_str: str) -> dict[str, object] | None:
    if tool_name in {"write", "edit"}:
        fp_match = re.search(r"\"filePath\"\s*:\s*\"([^\"]+)\"", raw_str)
        c_match = re.search(r"\"content\"\s*:\s*\"", raw_str)
        if fp_match and c_match:
            file_path = fp_match.group(1)
            content_start = c_match.end()
            content_end = _scan_string_end(raw_str, content_start)
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
            cmd_end = _scan_string_end(raw_str, cmd_start)
            if cmd_end > cmd_start:
                return {"command": _decode_escaped_text(raw_str[cmd_start:cmd_end])}
    return None


# Kein ':' und kein ';': damit endet auch ein rollen-praefix (`user:`),
# und die part-verkettung haette mitten im echo-präfix umgebrochen.
# T-04: maximale anzahl identischer nativer calls pro turn
_MAX_IDENTICAL_NATIVE_CALLS = 2
_SENTENCE_END_CHARS = ".!?\u2026\u3002\"')\u00bb"
# Eine part, die mit einem dieser zeichen beginnt, eroeffnet einen neuen
# block (markdown-tabelle, liste, ueberschrift, zitat) und ist damit KEINE
# fortsetzung — auch wenn die vorherige mitten im satz endete.
_BLOCK_START_RE = re.compile(r"\A[ \t]*(?:\||#|>|[-*+][ \t]|\d+[.)][ \t]|```|~~~)")


def _starts_new_block(part: str) -> bool:
    return bool(_BLOCK_START_RE.match(part))


# Nackter call-objekt-anfang: {"name": … / {"arguments": … / {"filePath": …
_BARE_CALL_OPENER_RE = re.compile(r'\{\s*"(?:name|arguments|filePath|command|content)"\s*:')

# S-05: die drei opnerformen, die den finalize-safety-net brauchen. Sie
# entscheiden, OB ein zurueckgehaltener text jetzt schon raus darf oder
# weiter warten muss (siehe `_deferred_visible_is_publishable`).
_PROTOCOL_FRAGMENT_MARKERS = (
    '{"tool_calls"',
    "<ml_tool_call",
    "<|DSML|tool_call",
)


def _contains_protocol_fragment(text: str) -> bool:
    """Traegt der text ein stueck tool-protokoll, das der finalize-pfad
    noch entfernen muss?"""
    if not text:
        return False
    if any(marker in text for marker in _PROTOCOL_FRAGMENT_MARKERS):
        return True
    return _BARE_CALL_OPENER_RE.search(text) is not None


def _fences_balanced(text: str) -> bool:
    """Sind alle code-fences im text geschlossen?

    Ein ungeschlossener fence darf nicht mitten im stream raus: er koennte
    das tool-protokoll umhuellen (```json {"tool_calls":...}), und genau
    diese unwrap-arbeit macht der finalize-pfad."""
    for marker in ("```", "~~~"):
        if text.count(marker) % 2 == 1:
            return False
    return True

# P-07/D-03: tool-markup, das nie geschlossen wurde. Der stream-pfad
# haelt es ueber den markup-holdback zurueck; der final-/non-stream-pfad
# tat das nicht und lieferte rohes DSML als antwort (gemessen in 12 von
# 12 chunk-groessen).
_UNTERMINATED_MARKUP_RE = re.compile(
    r"(?i)(?:<\|\s*dsml|<\/\|\s*dsml|<ml_|<tool_call|<tool_calls|<invoke|<parameter)"
)


def strip_unterminated_markup(text: str) -> tuple[str, int]:
    """Entfernt tool-markup, das nie geschlossen wurde (P-07/D-03).

    Ein abgeschnittenes DSML/XML ist keine antwort. **Vollstaendiges**
    markup wird nicht angefasst — es ist eine gueltige darstellung und der
    parser extrahiert daraus den call. Entfernt wird nur, was der parser
    NICHT zuordnen konnte, also ein opfer ohne passenden schliesser.

    Gibt (bereinigter_text, anzahl_fragmente) zurueck."""
    if not text:
        return text, 0
    residue = _markup_residue_after_parsing(text)
    if residue is None:
        return text, 0
    return text[: residue[1]].rstrip(), 1


def _markup_residue_after_parsing(text: str) -> tuple[str, int] | None:
    """(rest_text, startindex) des ersten unterminierten markup-uecks."""
    match = _UNTERMINATED_MARKUP_RE.search(text)
    if match is None:
        return None
    start = match.start()
    tail = text[start:]
    # ein passender schliesser irgendwo danach -> vollstaendig
    closer = re.search(r"(?i)</\|\s*dsml|</ml_|<\/tool_call|</invoke|</parameter", tail)
    if closer is not None and closer.start() > 0:
        return None
    return tail, start


# Nur so viele zeichen des gesendeten texts werden fuer die
# satzzeichen-/blockstart-pruefung vorgehalten.
_EMITTED_TAIL_CHARS = 64


def _scan_brackets(fragment: str, open_brackets: int, in_string: bool) -> tuple[int, bool]:
    """Inkrementeller klammer-/string-zustand ueber ein textfragment."""
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
        elif char in "{[":
            open_brackets += 1
        elif char in "}]" and open_brackets:
            open_brackets -= 1
    return open_brackets, in_string


def _ends_sentence(text: str) -> bool:
    """Endet der text mit einem satzzeichen (ohne absatztrenner)?

    Trennt 'mitten im satz' (fortsetzung) von 'ganzer absatz' (neuer
    absatz). Ein fragment, das mit `.` endet, ist ein satzende — dort ist
    ein absatzumbruch plausibel und wird gesetzt. Alles andere ist eine
    mitten im satz abgeschnittene part und wird direkt angehaengt."""
    stripped = text.rstrip()
    if not stripped:
        return True
    return stripped[-1] in _SENTENCE_END_CHARS


def normalize_file_path(raw_path: str) -> str:
    """T-16: `filePath` ohne URI-/Root-Kontext umzuschreiben war fehlerhaft.

    Zwei konkrete Fehler:
      * `file:/tmp/x` wurde durch `fp[6:]` zu `tmp/x` — ein RELATIVER Pfad,
        der im aktuellen Arbeitsverzeichnis landete. `file:///tmp/x` war
        korrekt. Jetzt wird das Schema ueber `urlsplit` gelesen, nicht
        ueber Abschneiden.
      * `.`/`..`-Segmente blieben unaufgeloest, sodass `workspaces/../x`
        auf einen anderen Root zeigen konnte. Sie werden jetzt aufgeloest
        — nach dem Aufloesung kann `..` den Pfad nicht mehr verlassen."""
    path = raw_path.strip()
    if not path:
        return path
    if path.lower().startswith("file:"):
        parsed = urlsplit(path)
        # netloc nur bei file://host/… beruecksichtigen
        path = parsed.path or (f"/{parsed.netloc}{parsed.query}" if parsed.netloc else "")
    # doppelte slashes und `.` aufloesen, `..` aufloesen ohne root-ausbruch
    absolute = path.startswith("/")
    resolved: list[str] = []
    for segment in path.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if resolved and resolved[-1] != "..":
                resolved.pop()
            elif not absolute:
                resolved.append("..")
            # absolut: `..` am anfang bleibt `/` (kann nicht ausbrechen)
            continue
        resolved.append(segment)
    normalized = "/".join(resolved)
    if absolute:
        normalized = "/" + normalized
    if not normalized:
        return path
    if normalized.startswith("workspaces/"):
        return "/" + normalized
    if normalized.startswith("benchmark/"):
        return "/workspaces/" + normalized
    if normalized == "benchmark.md":
        return "/workspaces/benchmark.md"
    return normalized


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
        else:
            # A-14: `_raw` war eine REPARATURMARKIERUNG, keine echte
            # parameterkategorie. Konnte sie nicht aufgeloest werden,
            # blieb sie im argument-objekt und das modell las daraus eine
            # fähigkeit namens `_raw`. Jetzt wird der aufruf verworfen —
            # der turn zaehlt dann ueber den unusable-call-pfad als
            # fehlerhaft.
            return None
    if cleaned == {"param_name": "url"} and fallback_url:
        cleaned = {"url": fallback_url}
    elif cleaned == {"param_name": "url"}:
        cleaned = {}
    if "param_name" in cleaned and "param_value" not in cleaned and len(cleaned) == 1:
        cleaned = {}

    if "filePath" in cleaned and isinstance(cleaned["filePath"], str):
        cleaned["filePath"] = normalize_file_path(cleaned["filePath"])

    # Repair: stringified JSON arrays or objects inside parameters
    # (e.g. questions: "[{...}]").
    #
    # T-23: das passierte fuer JEDEN parameter, dessen string wie JSON
    # aussah. `{"url": "{\"a\":1}"}` wurde zu `{"url": {"a": 1}}` — ein
    # stiller typwechsel, den der client nicht erwartet. Ohne schema gibt
    # es keine entscheidungsgrundlage, deshalb gilt die reparatur nur fuer
    # parameter, die nach benennung strukturierten inhalt erwarten
    # (PLURAL + inhalt), und nur wenn das gesamte argumentobjekt NICHT
    # aus einem einzelnen solchen feld besteht.
    if tool_name not in {"write", "edit"}:
        for key, val in list(cleaned.items()):
            if not isinstance(val, str):
                continue
            if not _expects_structured_value(key, cleaned):
                continue
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
    *,
    unrestricted: bool = False,
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
    extra_targets = 0
    if isinstance(open_list, list) and open_list:
        first = open_list[0]
        if isinstance(first, dict):
            command = str(first.get("command", "") or first.get("cmd", "") or "").strip()
            target = str(first.get("ref_id", "") or first.get("url", "") or first.get("path", "")).strip()
        # T-21: weitere ziele wurden stillschweigend verworfen. Der erste
        # MAPPBARE gewinnt; die uebrigen werden wenigstens protokolliert,
        # damit der aufruf nicht als vollstaendig verarbeitet gilt.
        extra_targets = max(0, len(open_list) - 1)
    if not command:
        command = str(parsed.get("command", "") or parsed.get("cmd", "") or "").strip()
    if command:
        if unrestricted or (allowed_tool_names is not None and "bash" in allowed_tool_names):
            return "bash", {"command": command}

    if not target:
        target = str(parsed.get("ref_id", "") or parsed.get("url", "") or parsed.get("path", "") or parsed.get("file", "")).strip()

    if not target:
        return None

    if target.startswith("http://") or target.startswith("https://"):
        if unrestricted or (allowed_tool_names is not None and "webfetch" in allowed_tool_names):
            if extra_targets:
                _LOGGER.warning(
                    "Native open call carried %s target(s); only the first was mapped",
                    extra_targets + 1,
                )
            return "webfetch", {"url": target}

    # S-08: `file://` ist die NATUERLICHSTE form, mit der das modell
    # "mach dieses lokale verzeichnis auf" ausdrueckt — und sie fiel vorher
    # einfach durch: kein http(s), also URL-pruefung nein; `://` im
    # ziel, also T-21-pfad "das ist eine URL, kein pfad" -> None. Ergebnis:
    # der verworfene aufruf, und weil danach nichts zurueckkam, wiederholte
    # das modell ihn (live 2026-09-26, session `glm2api-Ordner-Analyse`:
    # allererster aufruf `file:///workspaces/MAIN/glm2api`, danach ~30
    # weitere `open`-aufrufe und eine erfundene tool-limit-meldung).
    # `file://` ist hier KEIN fetch-ziel, sondern ein lokaler pfad in
    # schreibweise — er wird auf den pfad zurueckgefaltet und wie jeder
    # andere pfad behandelt.
    if target.lower().startswith("file://"):
        from urllib.parse import unquote

        # `file:///a/b` -> `//a/b` -> `/a/b`; `file://host/a` -> `/a`
        _split = urlsplit(target)
        target = unquote(_split.path or "")
        if _split.netloc and _split.netloc.lower() not in {"", "localhost"}:
            # `file://host/...` ist ein UNC-artiger zielpfad; der host ist
            # fuer uns nicht erreichbar -> nicht abbildbar.
            return None
        if not target:
            return None

    # T-21: `example.com` ohne schema fiel durch den punkt-check in die
    # datei-erkennung und wurde als read auf einen nicht existierenden
    # dateinamen abgebildet. Eine bare domain ist eine URL.
    if "://" not in target and re.fullmatch(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", target):
        if unrestricted or (allowed_tool_names is not None and "webfetch" in allowed_tool_names):
            if extra_targets:
                _LOGGER.warning(
                    "Native open call carried %s target(s); only the first was mapped",
                    extra_targets + 1,
                )
            return "webfetch", {"url": f"https://{target}"}

    if not target.startswith("turn") and ("/" in target or target.startswith(".") or "." in target):
        if _looks_like_tool_invocable(target):
            # Das Modell hat den Toolnamen selbst in das Argument geschrieben
            # (live-Fall 2026-09-25: 'filePath': 'read /workspaces/…').
            # Das ist kein Pfad — der aufruf waere sonst eine Lese-Anfrage
            # auf einen Dateinamen, den es nicht gibt, und der Agent raeumt
            # den Fehler nicht auf. Besser: als blockierten Versuch
            # kennzeichnen, damit die negative Rueckmeldung greift.
            return None
        # T-02/T-21: eine URL ist KEINE Datei. Ohne `webfetch` in der
        # deklarierten tool-liste darf sie nicht als read mit der URL als
        # filePath fallen — das erzeugt einen unerfuellbaren Leseauftrag.
        if "://" in target or re.fullmatch(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", target):
            return None
        if unrestricted or (allowed_tool_names is not None and "read" in allowed_tool_names):
            return "read", {"filePath": target}

    return None


def _looks_like_tool_invocable(target: str) -> bool:
    """Beginnt das 'argument' mit einem toolnamen und einem leerzeichen?

    Erkennt die vom Modell verursachte form 'read /pfad', 'write datei',
    'bash ls -la' — also eine Anweisung statt eines Ziels."""
    stripped = target.strip()
    if " " not in stripped:
        return False
    first_word, remainder = stripped.split(" ", 1)
    if not remainder.strip():
        return False
    known = {
        "read", "write", "edit", "bash", "glob", "grep", "webfetch",
        "todowrite", "task", "open", "list", "search",
    }
    return first_word.lower().strip("`'\"():") in known


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


# S-07: das Modell ERKLAERT das Werkzeugprotokoll, statt es zu benutzen.
#
# Live 2026-09-26 (glm-5.3, session `glm2api verify 4`): ein turn mit 8
# korrekten parallelen `read`-calls lieferte zusaetzlich genau diesen
# monolog als sichtbaren text:
#   "Wrong tool calls above — correcting to the allowed tools:I must use
#    `read`/`webfetch`/`bash` instead of `open`. Correct JSON protocol:"
# Der client (opencode) legte daraus eine assistant-nachricht an: sichtbarer
# ballast im TUI, dauerhafter ballast im kontext — und das modell lernt
# daran, dass narrativ erlaubt ist.
#
# Drei einsatzstellen, weil die drei pfade getrennt sind:
#   * `_PROTOCOL_META_NARRATION_TAIL_RE` — der stream-pfad, VOR dem parser.
#     Nur so greift die erkennung bei JEDER chunk-groesse: sie haelt deltas
#     zurueck, deren ende noch ein PRAEFIX einer marke ist ("Wro", "Wrong
#     tool", …), und gibt sie erst frei, wenn der text entweder zur marke
#     geworden ist (dann puffert die T-07-maschinery und verwirft sie bei
#     aufrufen) oder erkennbar etwas anderes ist. Ohne den lookahead
#     matcht die marke nur, wenn sie zufaellig in EINEN delta passt — bei
#     chunk-groesse 1-13 streamte sie komplett durch (gemessen).
#   * `_META_CHATTER_SENTENCE_RE` — der finalize-pfad fuer turns OHNE
#     aufrufe (mit aufrufen greift der verwurf oben).
#   * `strip_protocol_meta_narration` — der direktaufruf fuer tests und
#     fuer aufrufer, die den text ohne accumulator filtern wollen.
#
# Die phrasen sind WORTLISTEN, keine regexp. Daraus werden zwei muster
# erzeugt: die vollform und alle WORDPRAEFIXE. Jedes wort darf in
# backticks stehen ("instead of `open`") — das ist die live-form und ein
# eigenes literal-muster wuerde daran vorbeigehen.
_PROTOCOL_META_PHRASES = (
    "wrong tool call",
    "wrong tool calls",
    "tool call above",
    "tool calls above",
    "tool usage above",
    "tool calls earlier",
    "tool calls before",
    "tool calls wrong",
    "tool calls invalid",
    "tool calls not allowed",
    "correcting to the allowed tools",
    "correct to the allowed tools",
    "correctly to the allowed tools",
    "correct json protocol",
    "proper json protocol",
    "right json protocol",
    "the expected json protocol",
    "json protocol is",
    "json protocol below",
    "instead of open",
    "instead of open url",
    "instead of openurl",
    "instead of browse",
    "instead of web search",
    "instead of web run",
    "instead of execute sandbox code",
    "instead of code interpreter",
    "use read instead",
    "use write instead",
    "use bash instead",
    "use webfetch instead",
    "use glob instead",
    "use grep instead",
    "falsche tool calls",
    "falscher tool call",
    "fehlerhafte tool calls",
    "ungueltige tool calls",
    "unzulaessige tool calls",
    "tool calls oben",
    "tool calls ungueltig",
    "tool calls falsch",
    "korrigiere auf die erlaubten tools",
    "korrigiere zu den erlaubten tools",
    "statt open",
    # S-08: die selbst erfundene werkzeug-inventur + die erfundene
    # abbruch-erklaerung. Live 2026-09-26 (session
    # `glm2api-Ordner-Analyse` und repro C): nach ~30 verworfenen
    # `open`-aufrufen schrieb das modell in die antwort
    #   'In dieser Umgebung steht mir nur das `open`-Tool zur Verfügung,
    #    das ausschließlich Web-URLs öffnen kann'
    #   '`open` funktioniert nur für Web-URLs, nicht für lokale Pfade'
    #   'Ursache war ein Tool-Fehler meinerseits: …'
    #   'Ich musste die Tool-Aufrufe jetzt stoppen.'
    #   'Die Analyse konnte in dieser Sitzung nicht durchgeführt werden.'
    # und erfand ein tool-limit. Das ist KEINE antwort, sondern eine
    # halluzinierte umgebung — sie stand sichtbar beim client.
    # Umlaute in beiden schreibweisen: das modell wechselt je nach
    # aufgaben-sprache zwischen "verfuegbar" und "verfügbar".
    "steht mir nur das open tool",
    "steht mir nur das open",
    "steht mir nur ein open",
    "in dieser umgebung steht mir nur",
    "open funktioniert nur",
    "open funktioniert nicht",
    "open funktioniert ausschliesslich",
    "open funktioniert ausschließlich",
    "tool fehler meinerseits",
    "musste ich die tool aufrufe stoppen",
    "musste ich die tool aufrufe jetzt stoppen",
    "musste die tool aufrufe stoppen",
    "musste die tool aufrufe jetzt stoppen",
    "muss ich die tool aufrufe stoppen",
    "muss die tool aufrufe stoppen",
    "konnte ich in dieser sitzung nicht",
    "konnte in dieser sitzung nicht",
    "analyse konnte in dieser sitzung nicht",
    # englische varianten derselben erfundenen meldung (live repro D)
    "the open tool doesn't work",
    "the open tool does not work",
    "open doesn't work",
    "open does not work",
    "switching to read",
    # live repro E, weitere formen derselben selbstbeschreibung
    "in dieser umgebung defekt",
    "fur lokale pfade unzulassig",
    "für lokale pfade unzulässig",
    "aufruf zyklus",
    "alle versuche fehlgeschlagen",
)


def _meta_phrase_fragment(words: list[str], last_word_partial: bool = False) -> str:
    r"""Ein wort als regex, optional in backticks; woerter mit beliebigem
    whitespace dazwischen (live: 'Correct JSON protocol:').

    `last_word_partial` erlaubt JEDE unvollstaendige schreibung des letzten
    worts. Das ist fuer den fruehwarn-lookahead noetig: der upstream
    schneidet mitten im wort ("Wrong tool c"), und ein rein auf ganze
    woerter gebautes praefix-muster wuerde den holdback genau dort
    aufgeben — mit folge, dass die narration bei chunk-groesse 1-13
    komplett durchstreamt (live gemessen).

    Die wort-trenner sind `[-_\s]+`, nicht nur whitespace: das modell
    schreibt "Tool-Calls" (live, deutsch) und "open_url" (der echte
    werkzeugname) mit trennzeichen."""
    parts = []
    for index, word in enumerate(words):
        literal = re.escape(word)
        if last_word_partial and index == len(words) - 1:
            # Ein zeichen genuegt: der upstream schneidet nach dem
            # ersten buchstaben. Dass ein einzelnes 'r' nicht JEDEN text
            # matcht, sichert der wortgrenzen-anker im tail-muster
            # (siehe `_build_meta_narration_regexes`) — nicht diese
            # zeichenkette.
            literal = re.escape(word[0]) + "".join(
                re.escape(char) + "?" for char in word[1:]
            )
        parts.append(r"`?" + literal + r"`?")
    return r"`?[-_\s]+".join(parts)


def _build_meta_narration_regexes(phrases: tuple[str, ...]) -> tuple[re.Pattern[str], re.Pattern[str]]:
    full: list[str] = []
    prefixes: list[str] = []
    for phrase in phrases:
        words = phrase.split()
        for count in range(1, len(words) + 1):
            part = words[:count]
            # JEDE anzahl an woertern braucht die partielle form des
            # letzten worts: der upstream schneidet mitten im wort, und
            # "wrong tool c" ist ein praefix mit DREI woertern, dessen
            # drittes nur zur haelfte da ist. Ohne die partielle form
            # fuer count == len(words) greift der lookahead bei genau
            # diesem fall nicht.
            prefixes.append(_meta_phrase_fragment(part, last_word_partial=True))
            if count == len(words):
                full.append(_meta_phrase_fragment(part))
    full_re = re.compile("(?:" + "|".join(full) + r")\b", re.IGNORECASE)
    # laengere praefixe zuerst: sonst matcht "wrong" und der rest
    # "tool calls" bleibt als eigenstaendiges muster uebrig.
    ordered = sorted(set(prefixes), key=len, reverse=True)
    # S-07: der lookahead muss an einer WORTgrenze beginnen. Ohne den
    # anker matchte das einzelne 'r' aus 'right…' mitten in jedem text
    # ('Nachher' -> 'r') und der holdback griff an jedem turnende — mit
    # folge, dass ein fuehrender zeilenumbruch in den parser wanderte und
    # von dessen flush weggestrippt wurde (gemessen: '```Nachher' statt
    # '```\nNachher').
    tail_re = re.compile(
        r"(?:^|(?<=[\s`\-_]))(?:" + "|".join(ordered) + r")\s*$",
        re.IGNORECASE,
    )
    return full_re, tail_re


_PROTOCOL_META_NARRATION_RE, _PROTOCOL_META_NARRATION_TAIL_RE = (
    _build_meta_narration_regexes(_PROTOCOL_META_PHRASES)
)

def strip_protocol_meta_narration(text: str) -> str:
    """Entfernt Text, in dem das Modell das Werkzeugprotokoll kommentiert
    (S-07) — 'Wrong tool calls above', 'instead of `open`', 'Correct JSON
    protocol'.

    Klauselweise: der markierte abschnitt plus der satz, in dem er steht,
    faellt; alles andere bleibt. Klausel statt zeile, weil die marke auch
    mitten im satz stehen kann ('I must use `read` instead of `open`.') —
    eine zeilen- oder satz-Anfangserkennung greift dort nicht.

    Die phrasen sind am werkzeug-vokabular verankert, nicht an 'instead
    of' allgemein: 'The file uses 200 instead of 100 lines' bleibt
    unangetastet.

    S-08: der schnitt ist SATZ-aligned, nicht klausel-aligned. Mit
    klauselschnitt blieb bei einem marker mitten im satz ein fragment
    uebrig (live repro E: '`open` funktioniert nicht fuer lokale
    Dateien. Ich nutze jetzt `read` und `bash`' wurde zu
    '` nutze `read`:` nicht fuer lokale Dateien.'). Ein halber satz ist
    schlimmer als ein ganzer fehlender."""
    if not text:
        return ""
    if not _PROTOCOL_META_NARRATION_RE.search(text):
        return text
    spans: list[tuple[int, int]] = []
    for match in _PROTOCOL_META_NARRATION_RE.finditer(text):
        span = (match.start(), match.end())
        if any(start <= span[0] < stop for start, stop in spans):
            continue  # bereits von einem vorherigen treffer erfasst
        spans.append(span)
    if not spans:
        return text
    result: list[str] = []
    cursor = 0
    for start, stop in spans:
        result.append(text[cursor:_sentence_start_before(text, start)])
        cursor = _sentence_end_after(text, stop)
    result.append(text[cursor:])
    return re.sub(r"[ \t]{2,}", " ", "".join(result)).strip()


_META_CHATTER_SENTENCE_RE = re.compile(
    r"(?:^|(?<=[.!?…])\s)"
    r"(?:\W*)(?:"
    r"i(?:'m| am)\s+(?:so |very )?sorry\b"
    r"|i\s+(?:cannot|can't|can not|am\s+unable\s+to|don't\s+have\s+(?:access|the\s+ability)\s+to|do\s+not\s+have\s+access\s+to)\b"
    r"|as\s+an\s+ai\b"
    r"|es\s+tut\s+mir\s+leid"
    r"|ich\s+kann\s+(?:das\s+)?(?:nicht|leider\s+nicht)\b"
    r"|mir\s+steht\s+(?:das\s+|dieses\s+)?(?:tool|werkzeug)\s+(?:nicht|leider\s+nicht)\s+zur\s+verfügung"
    # S-07: die narration wird als eigener alternativ-zweig angehaengt
    # (siehe `strip_protocol_meta_narration`); das inline-`(?i)` ist weg,
    # weil python 3.11+ keine flags mehr in der mitte eines patterns
    # erlaubt. Verhalten identisch (re.IGNORECASE statt `(?i)` am anfang).
    r")[^.!?\n]*[.!?…]?",
    re.IGNORECASE,
)


# S-08: die ERFUNDENE LIMIT-MELDUNG. Sie ist die schaedlichste form, weil
# das modell danach aufhoert zu arbeiten und dem client eine fertige
# antwort samt grund fuer den abbruch liefert. Live reproduziert
# (repro D, 2026-09-26, wortwoertlich als erster satz der antwort):
#   'Tool-Limit erreicht — hier die Analyse basierend auf den gesammelten
#    Daten:'
# und in einer aelteren session: 'Tool-Limit (8/8 Runden) erreicht'.
#
# Zwei bedingungen, damit hier nicht echter inhalt verloren geht:
#   * die limit-behauptung steht in den ERSTEN 200 zeichen (dort lebt
#     die entschuldigungs-/abbruch-passage) ODER
#   * der satz enthaelt ein stopp-wort (das modell BEGRUENDET hier seinen
#     abbruch — genau das ist die gefaehrliche form).
# Ein technischer bericht, der die limit-KONFIGURATION erwaehnt
# ('bei 131072 tokenlimit greift finish_reason=length'), bleibt damit
# unangetastet: er steht nicht am anfang und hat kein stopp-wort.
_LIMIT_CLAIM_RE = re.compile(
    r"(?:tool|token|output|round|turn|schritt|aufruf)[\s_-]*limit"
    r"|(?:token|output)[\s_-]*(?:limit|budget|grenze)"
    r"|(?:runden|tool|token)[\s_-]*limit"
    r"|keine\s+tools?\s+mehr",
    re.IGNORECASE,
)

_STOP_WORD_RE = re.compile(
    r"(?:abgebrochen|abbrechen|bricht\s+ab|beendet|gestoppt|stoppen|stoppe|"
    r"aufgeben|nicht\s+weiter|aufh[oö]r|aborted|stopped|cannot\s+continue|"
    r"can\s+not\s+continue|give\s+up|unreachable"
    # live repro E: '... (alle Versuche fehlgeschlagen, Tool-Limit
    # erreicht)'. Das 'Tool-Limit' stand nicht am anfang, also griff nur
    # das stopp-wort — und 'fehlgeschlagen' fehlte.
    r"|fehlgeschlagen|gescheitert|vergeblich|verfehlt)",
    re.IGNORECASE,
)

_LIMIT_LEAD_WINDOW = 200

# S-08: SELBST-STEUERUNG. Die phrasenliste fuer die narration waechst ins
# uferlose, wenn man sie gegen jede erfundene Formel schaerft (live
# repro F: '`open` ist nur für Web-URLs', 'Ich muss das Tool `open`
# sofort stoppen', 'Ich muss den Vorgang hier abbrechen' — drei
# woertlich neue formen in einem lauf). Der robuste anteil ist nicht das
# schlagwort, sondern die STRUKTUR: ein satz in der ersten person, der
# das modell beim STEUERN beobachtet ('ich nutze/wechsle/stoppe/abbreche
# ... + werkzeug'), ist fast immer self-talk und keine antwort.
#
# Anwendungsbereich bewusst auf den STREAM-Pfad: das ist der text, den
# der client als laufende assistant-nachricht sieht. Der finale bericht
# geht durch `finalize`/`strip_meta_chatter` und bleibt konservativ —
# dort ist eine Aussage ueber `open` (z. B. in einer analyse ueber den
# proxy) echter inhalt.
_SELF_STEERING_RE = re.compile(
    r"(?i)(?:\bich\b[^.!?\n]{0,60}?\b(?:nutze|verwende|wechsle|muss|beende|stoppe|"
    r"abbreche|abbrechen|aufgeben|brauche|gehe|wechsle)\b[^.!?\n]{0,40}?"
    r"(?:`?(?:open|open_url|read|write|edit|bash|webfetch|glob|grep)`?"
    r"|tool[- ]?calls?|werkzeug|aufr(?:u|ü)fen)"
    r"|\bich\s+(?:muss|beende|stoppe|breche)\b[^.!?\n]{0,50}?"
    r"(?:`?open`?|tool|aufr(?:u|ü)fen|vorgang|abbruch)"
    r"|`?open`?[^.!?\n]{0,30}?\b(?:ist\s+(?:nur|ein)|kann|koennte|funktioniert|arbeitet)\b"
    r"[^.!?\n]{0,30}?(?:web|url|dateisystem|pfade|datei))"
)


def strip_self_steering(text: str, *, require_complete_sentence: bool = False) -> str:
    """Entfernt Sätze, in denen das Modell sein eigenes Werkzeugverhalten
    kommentiert (S-08). Nur fuer den stream-pfad — siehe
    `_SELF_STEERING_RE`.

    `require_complete_sentence=True` (der stream-pfad): entfernt wird nur,
    was **vollstaendig** in diesem stueck liegt. Grund: ein stream-delta
    beginnt mitten im satz. Ohne diese bedingung schnitt der filter mitten
    im wort und liess ein fragment stehen — live gemessen:
    '…fuer Dateisystem nutze ich jetzt `bash`:' wurde zu
    '`isystem nutze ich jetzt `bash`:'. Was ueber delta-grenzen laeuft,
    faellt beim finalize durch, wo der volle text vorliegt.
    """
    if not text or not _SELF_STEERING_RE.search(text):
        return text
    kept: list[tuple[int, int]] = []
    for match in _SELF_STEERING_RE.finditer(text):
        start = _sentence_start_before(text, match.start())
        stop = _sentence_end_after(text, match.end())
        if require_complete_sentence:
            # ein echter satzende-punkt muss im stueck liegen …
            if stop >= len(text.rstrip()) and not _SENTENCE_END_RE.search(text, match.end()):
                continue
            # … und davor muss eine echte satzgrenze liegen (nicht der
            # delta-anfang, der mitten im satz liegen kann).
            if start > 0 and text[start - 1] not in ".!?…\n":
                continue
        if any(s <= start < e for s, e in kept):
            continue
        kept.append((start, stop))
    if not kept:
        return text
    result: list[str] = []
    cursor = 0
    for start, stop in kept:
        result.append(text[cursor:start])
        cursor = stop
    result.append(text[cursor:])
    return re.sub(r"[ \t]{2,}", " ", "".join(result)).strip()


def strip_invented_limit_claim(text: str) -> str:
    """Entfernt die erfundene 'Tool-Limit erreicht'-Meldung samt Satz (S-08)."""
    if not text or not _LIMIT_CLAIM_RE.search(text):
        return text
    kept: list[tuple[int, int]] = []
    for match in _LIMIT_CLAIM_RE.finditer(text):
        start = _sentence_start_before(text, match.start())
        stop = _sentence_end_after(text, match.end())
        sentence = text[start:stop]
        near_start = match.start() <= _LIMIT_LEAD_WINDOW
        if not (near_start or _STOP_WORD_RE.search(sentence)):
            continue
        kept.append((start, stop))
    if not kept:
        return text
    result: list[str] = []
    cursor = 0
    for start, stop in kept:
        result.append(text[cursor:start])
        cursor = stop
    result.append(text[cursor:])
    return "".join(result).strip()


# Ein '.' beendet einen Satz NUR, wenn danach whitespace, zeilenumbruch oder
# ende folgt. Ohne diese bedingung frisst der filter '.env.' mit — der
# punkt darin ist kein satzende (gemessen: 'laut .env.' -> 'laut .').
_SENTENCE_END_RE = re.compile(r"\.(?=\s|$)|\n")


def _sentence_start_before(text: str, position: int) -> int:
    head = text.rfind(".", 0, position)
    line = text.rfind("\n", 0, position)
    boundary = max(head, line)
    return 0 if boundary == -1 else boundary + 1


def _sentence_end_after(text: str, position: int) -> int:
    match = _SENTENCE_END_RE.search(text, position)
    if match is None:
        return len(text)
    return match.end() if text[match.start()] == "\n" else match.end()


def strip_meta_chatter(text: str) -> str:
    """Strips self-apology and meta-commentary about failed/blocked tools and
    the model's own hallucinated conversation transcript.

    T-17: der filter war rein zeilenbasiert — eine Zeile mit meta-chatter
    UND der eigentlichen Antwort wurde entweder ganz verworfen (auch die
    Antwort) oder gar nicht erkannt. Die live beobachteten Formulierungen
    ("I'm sorry, I cannot use that tool", "I cannot access that URL")
    standen ueberhaupt nicht in der liste. Deshalb zusaetzlich satzweise:
    nur der verdaechtige Satz faellt, der Rest der Antwort bleibt.
    """
    if not text:
        return ""
    # S-07: protokoll-narration zuerst — sie ist der haeufigere fall und
    # steht in der Praxis VOR der selbstentschuldigung.
    text = strip_protocol_meta_narration(text)
    if not text:
        return ""
    # S-08: die erfundene limit-meldung. Sie muss VOR der zeilen-filterung
    # weg, sonst schuetzt die zeilenweise regel "meta-chatter steht immer
    # am anfang seiner zeile" genau die hier schlimmste passage.
    text = strip_invented_limit_claim(text)
    if not text:
        return ""
    # T-17: erst satzweise die fähigkeits-verleugnungen entfernen …
    without_meta_sentences = _META_CHATTER_SENTENCE_RE.sub(" ", text)
    lines = without_meta_sentences.splitlines(keepends=True)
    kept_lines = []
    for line in lines:
        lower = line.lower()
        # T-17: das schluesselwort muss am ANFANG der zeile stehen (evtl.
        # nach einem aufzaehlungspunkt). Vorher loeschte ein beliebiges
        # vorkommen die GANZE zeile — aus
        # 'Die Datei ist da, aber open ist nicht dasselbe wie read.' wurde
        # ''. Meta-chatter steht aber immer am anfang seiner zeile.
        stripped_line = lower.lstrip()
        if stripped_line[:2] in {"- ", "* "}:
            stripped_line = stripped_line[2:].lstrip()
        if any(stripped_line.startswith(kw) for kw in _META_CHATTER_KEYWORDS):
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
    # P1-Lauf 2026-09-25: die deny-list deckte nur feste strings ab. Das
    # Modell nutzt den sandbox-kanal als denk-kratzer und sendet
    # print("x"), print("done") & co. — alles, was nicht auf der liste
    # stand, wurde zu einem ECHTEN bash-aufruf (40 aufrufe in einem turn).
    return _is_side_effect_free_sandbox_code(code)


# Deckelung fuer sandbox->bash pro turn (schuetzt vor modell-degeneration,
# live-fall 2026-09-25: 40 mapped calls in einem turn).
_MAX_MAPPED_SANDBOX_CALLS = 8

# Aufrufe, die fuer sich genommen nichts bewirken.
_SIDE_EFFECT_FREE_CALLS = {"print", "pprint", "repr", "format", "len", "str", "int", "float", "bool", "list", "dict", "set"}


def _is_side_effect_free_sandbox_code(code: str) -> bool:
    """True, wenn ein snippet keine wirkung erzeugt — also denk-kratzer
    des modells ist und kein auszufuehrender auftrag.

    Bewertet ueber den abstrakten syntaxbaum statt ueber stringmuster: als
    wirkungslos gelten nur ausdruecke aus print/assert/pass sowie reine
    literale. Zuweisungen, imports, aufrufe, schleifen, dateizugriff und
    def/class zaehlen als wirkung."""
    stripped = code.strip()
    if not stripped:
        return True
    try:
        tree = ast.parse(stripped)
    except SyntaxError:
        # nicht parsebar: nicht als selbstgespraech einstufen, das waere
        # eine stillschweigende verweigerung echter aufgaben.
        return False
    if not tree.body:
        return True
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Import, ast.ImportFrom,
                             ast.For, ast.While, ast.With, ast.Try, ast.FunctionDef,
                             ast.AsyncFunctionDef, ast.ClassDef, ast.Raise, ast.Delete,
                             ast.Global, ast.Nonlocal, ast.Return)):
            return False
        if isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name not in _SIDE_EFFECT_FREE_CALLS:
                return False
    return True


def map_native_sandbox_tool_call(
    arguments: object,
    allowed_tool_names: set[str] | None = None,
    *,
    unrestricted: bool = False,
) -> tuple[str, dict[str, object]] | None:
    """Maps ChatGLM's native execute_sandbox_code(code=...) call to bash
    if bash is allowed. Runs python3 with the provided code.
    Returns (mapped_tool_name, mapped_arguments) or None if unmappable.

    T-02: `allowed_tool_names=None` bedeutet 'keine Tools deklariert' und
    damit 'nie einen Call erzeugen' — nicht 'alles erlaubt'. Vorher lief
    ein request ohne tools mit einem nativen sandbox-call in einen
    ausfuehrbaren bash-call."""
    if is_dummy_sandbox_code(arguments):
        return None
    if not unrestricted:
        if allowed_tool_names is None or "bash" not in allowed_tool_names:
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
        # T-21: der code wurde unveraendert in ein here-doc gesetzt. Eine
        # zeile exakt `EOF` (oder `PYTHON_EOF`, ...) beendet das here-doc
        # vorzeitig, und ALLES danach laeuft als shell-befehl:
        #   code = "y = 2\nEOF\nrm -rf /"
        #   -> python3 - << 'EOF'\ny = 2\nEOF\nrm -rf /\nEOF
        # Das ist eine Kommando-Injektion durch das modell in den
        # ausgefuehrten befehl. Zwei Massnahmen: der delimiter ist
        # daten-abhaengig und kommt im code nicht vor, und der code wird
        # escaped statt roh eingebettet.
        delimiter = "PY_EOF"
        while delimiter in code:
            delimiter += "_"
        bash_command = f"python3 - << {delimiter!r}\n{code}\n{delimiter}"

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
            # `unrestricted=True`: das ist die interne Namens-SEMANTIK
            # (open -> read/webfetch), NICHT die Ausführungsfreigabe. Die
            # entscheidet der accumulator über `allowed_tool_names`.
            mapped = map_native_open_tool_call(original_arguments, unrestricted=True)
            if mapped is not None:
                tool_name, mapped_args = mapped
                original_arguments = mapped_args
                original_value = mapped_args
        elif tool_name in {"execute_sandbox_code", "code_interpreter", "sandbox", "run_code"}:
            if is_dummy_sandbox_code(original_arguments):
                continue
            # siehe map_native_open_tool_call: interne Namens-Semantik,
            # keine Ausführungsfreigabe.
            mapped = map_native_sandbox_tool_call(original_arguments, unrestricted=True)
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
        # T-15: zwei arten von abweichung unterscheiden. Eine rein
        # semantische normalisierung (pfad, control-zeichen, json-string)
        # verletzt den call nicht — das ergebnis bleibt gueltig und muss dem
        # modell zurueckgegeben werden. Nur eine ERFORDERLICHES argument,
        # das fehlt oder nicht lesbar ist, macht den aufruf unbrauchbar.
        normalized = not isinstance(original_value, dict) or safe_json_dumps(cleaned_arguments) != safe_json_dumps(original_value)
        required_missing = False
        if tool_name in {"write", "edit"}:
            required_missing = not isinstance(cleaned_arguments, dict) or not cleaned_arguments.get("filePath")
        elif tool_name == "read":
            required_missing = not isinstance(cleaned_arguments, dict) or not cleaned_arguments.get("filePath")
        elif tool_name == "bash":
            required_missing = not isinstance(cleaned_arguments, dict) or not cleaned_arguments.get("command")
        if required_missing:
            # T-15: ohne das erforderliche argument ist der aufruf nicht
            # ausfuehrbar — er darf nicht als tool-call an den client gehen,
            # sonst scheitert die ausfuehrung mit einem kryptischen fehler.
            continue
        sanitized.append(
            {
                "id": _coerce_call_id(tool_call.get("id")) or f"call_repaired_{index}",
                "type": "function",
                "index": index,
                "_repaired": normalized and not required_missing,
                "_invalid": required_missing,
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
            # T-14: der paar-schutz griff nur fuer EIN result direkt nach
            # dem assistant. Bei einer multi-call-runde
            # (assistant(c1,c2) + tool(c1) + tool(c2)) wurde `tool c1` als
            # partner erkannt, `tool c2` aber als eigenstaendige message
            # behalten — im prompt stand danach ein result ohne seinen
            # call. Die gesamte runde wird als EIN atomarer block
            # behandelt: call + alle seine resultate, sonst nichts.
            run_start = i
            while run_start - 1 >= 0 and str(messages[run_start - 1].get("role", "")) == "tool":
                run_start -= 1
            owner_index = run_start - 1
            if owner_index >= 0:
                owner = messages[owner_index]
                if str(owner.get("role", "")) == "assistant" and owner.get("tool_calls"):
                    block = [owner, *messages[run_start : i + 1]]
                    block_size = sum(_msg_size(item) for item in block)
                    if running + block_size > max_total_chars:
                        first_kept = i + 1
                        break
                    for item in reversed(block):
                        kept.insert(0, item)
                    running += block_size
                    i = owner_index - 1
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
                # C-10: eine leere allowlist bedeutet 'keine tools erlaubt'.
                # Die frueher implizite 'kein filter' aus `available and ...`
                # liess historische calls ungeprueft durch — sie wurden
                # als ausfuehrbarer kontext zurueck ins prompt geschrieben.
                if is_blocked_tool_name(tool_name, None):
                    continue
                if tool_name not in available_tool_names:
                    continue
                tool_blocks.append(
                    serialize_tool_call_block(
                        name=tool_name,
                        arguments=function.get("arguments", "{}"),
                    )
                )
                tool_call_id = _coerce_call_id(tool_call.get("id"))
                if tool_call_id:
                    valid_tool_call_ids.add(tool_call_id)
                    tool_names_by_call_id[tool_call_id] = tool_name
            assistant_text = extract_text_content(content).strip() if content else ""
            block = "\n".join(tool_blocks)
            if not assistant_text and not block:
                continue
            content = f"{assistant_text}\n{block}".strip() if assistant_text and block else (assistant_text or block)
        elif role == "tool":
            tool_call_id = str(message.get("tool_call_id", "")).strip()
            # T-15: die beziehung call<->result muss belegt sein. Ein
            # repariertes_argument (pfad-normalisierung, control-zeichen,
            # json-string) macht den aufruf NICHT unbrauchbar — der client
            # hat genau die normalisierten argumente ausgefuehrt, also ist
            # sein result die WAHRE antwort auf diesen call und muss
            # zurueck. Verworfen wird nur, was sich als verwaist erweisen
            # laesst: eine id, die zu keinem call dieser historie gehoert,
            # oder ein erfundenes result mit eigenem namen.
            if tool_call_id and tool_call_id not in valid_tool_call_ids:
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


# Status, die eine regulaere, erfolgreiche antwort markieren.
_SUCCESSFUL_TERMINAL_STATUSES = frozenset({"", "stop", "finish", "completed", "success"})


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
    # T-20 (perf): die listen oben wurden per `in` durchsucht — ein linearer
    # scan ueber alle bisher gesehenen parts, also quadratisch. Bei 20k
    # parts waren das 110 Mikrosekunden pro event. Die sets daneben
    # beantworten dieselbe frage in O(1); die listen bleiben fuer die
    # reihenfolge erhalten.
    _known_text_id_set: set[str] = field(default_factory=set)
    _known_reasoning_id_set: set[str] = field(default_factory=set)
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
    # T-04: wie oft dieselbe signatur in diesem turn schon vorkam
    _server_side_signature_counts: dict[str, int] = field(default_factory=dict)
    # T-25 (live 2026-09-26): der loop guard hat bisher OHNE rueckmeldung
    # verworfen. Das modell zaehlte 10 calls und 2 ergebnisse und schloss
    # daraus auf ein erfundenes "tool-limit (8/8 runden) erreicht" — dann
    # aufgibt und verlangt einen neustart. Zaehler fuer die notice.
    loop_guard_dropped_count: int = 0
    loop_guard_dropped_tools: list[str] = field(default_factory=list)
    # T-20: laufender zustand des bereits gesendeten texts. Aus einem
    # wachsenden praefix-STRING wurde das: der originalansatz pruefte und
    # kopierte den GESAMTEN text bei jedem part (O(n) je part, also
    # quadratisch — 1000 parts kosteten 18,4 s gegenueber 3,5 s im
    # urspruenglichen audit). Jetzt wird nur noch das angehaengte
    # fragment betrachtet und der klammer-/string-zustand fortgeschrieben.
    _emitted_text_tail: str = ""
    _emitted_reasoning_tail: str = ""
    _emitted_text_open_brackets: int = 0
    _emitted_text_in_string: bool = False
    # T-20: inkrementeller aufbau des zusammengefuegten texts
    # je kanal: [text, anzahl_teile, offene_klammern, im_string, epoch]
    _joined_state: dict[str, list[Any]] = field(default_factory=dict)
    # T-20: logic-ids, deren inhalt sich seit dem letzten render geaendert
    # hat. Nur diese werden neu gerendert — sonst wurde bei jedem event
    # der komplette text aus allen parts neu zusammengesetzt (quadratisch:
    # 2000 parts kosteten 16,9 s).
    _dirty_logic_ids: set[str] = field(default_factory=set)
    # T-20 (perf): der aufbau liest aus diesen listen und haengt neue
    # parts an. Vorher wurde `text_parts` bei JEDEM event neu aus allen
    # bekannten parts gefuellt — bei 6000 parts 36 Mio dict-zugriffe und
    # 18 s. Neu: O(geaenderte parts) pro event.
    _rendered_text_parts: list[str] = field(default_factory=list)
    _rendered_text_chars: int = 0
    _last_render_epoch: int = -1
    _rendered_reasoning_parts: list[str] = field(default_factory=list)
    _logic_id_rank: dict[str, int] = field(default_factory=dict)
    # T-20 (perf): die im LETZTEN aufbau tatsaechlich neu aufbereiteten
    # parts. `_render_full_output()` leert `_dirty_logic_ids`, bevor
    # `_compute_deltas()` iteriert — ohne diesen schnappschuss lief die
    # delta-berechnung ueber ALLE bekannten parts, bei 1000 parts also
    # 1.000.000 dict-zugriffe (gemessen 3,5 s / 1000 parts, 20,7 s /
    # 2000 parts, je verdopplung 4-7x). Unveraenderte parts koennen
    # nichts beitragen: ihr zwischengespeicherter text ist gleich und
    # `_part_text_sent` steht schon darauf.
    _last_rendered_dirty: set[str] = field(default_factory=set)

    # wird erhoeht, wenn eine BEREITS zusammengefuegte part geaendert wird;
    # der inkrementelle aufbau wird dann verworfen und neu gebaut.
    _parts_epoch: int = 0

    _deferred_visible_text: str = ""
    # S-06: stand schon sichtbarer (nicht-rein-whitespace) text in diesem
    # turn im stream? Dann ist ein whitespace-delta ein trennzeichen
    # zwischen zwei sichtbaren stuecken und wird sofort rausgeschickt
    # (D-06). Vor dem ersten sichtbaren text ist er ein Kandidat fuer das
    # leerzeilen-artefakt neben tool-calls und wartet im puffer.
    _emitted_visible_text: bool = False
    # S-07: text, der noch NICHT an den parser gegeben wurde, weil sein
    # ende noch ein praefix einer narration-marke ist. Ohne diesen
    # vorlauf matcht die marke nur, wenn sie zufaellig in einen einzigen
    # delta passt — bei chunk-groesse 1-13 kam die komplette narration
    # durch (live gemessen).
    _narration_carry: str = ""
    _deferred_reasoning: str = ""
    _deferred_reasoning_calls: list[dict[str, object]] = field(default_factory=list)
    blocked_tool_attempt_names: list[str] = field(default_factory=list)
    _mapped_sandbox_calls: int = 0
    # T-13: true, wenn der turn an einem angebrochenen protokoll endete und
    # deshalb nicht als regulaerer 'stop' gelten darf.
    truncated_turn: bool = False
    # Ausgabegrenze (tokens). Der upstream kennt keine, deshalb setzt der
    # proxy sie durch: mitgezaehlt wird, was den client wirklich erreicht
    # (reasoning, sichtbarer text, tool-call-argumente).
    max_output_tokens: int | None = None
    output_limit_reached: bool = False
    _output_chars: int = 0
    # Anzahl der aus GRUND DER POLICY abgelehnten aufrufe. Sie sind
    # vollstaendig formuliert, nur nicht erlaubt — das ist etwas anderes
    # als ein unbrauchbarer call (fehlendes pflichtargument, kaputtes
    # json). `dropped_call_count` zaehlt beides, weshalb hier der
    # gesonderte zaehler noetig ist: sonst endet ein turn, in dem das
    # modell ein gesperrtes werkzeug versucht, als `error` — und der
    # client wiederholt ihn endlos (5 min backoff, gemessen 2026-09-26).
    _policy_dropped_call_count: int = 0
    # separat gefuehrt, weil das reasoning einen ANTEIL des budgets
    # bekommen darf, nicht alles (siehe `_REASONING_BUDGET_SHARE`).
    _reasoning_chars: int = 0
    # T-18: `tool_choice=required`/<namenswahl> stand bisher nur als text im
    # system-prompt. Ein turn, der stattdessen prosa lieferte, galt als
    # regulaerer 'stop' — der client hatte einen tool-vertrag verlangt und
    # bekam eine antwort. Das wird hier durchgesetzt.
    tool_choice_mode: str = "auto"
    tool_choice_name: str | None = None
    required_tool_missing: bool = False
    # T-22: ein turn wird genau einmal abgeschlossen
    _finalized: bool = False
    # T-07/D-06: eine praeambel wurde erkannt; bis ein tool-call auftaucht
    # oder der turn endet, wird der gesamte sichtbare text gepuffert.
    _preamble_pending: bool = False
    # T-13/S-08: der terminalstatus des turns. Nicht-erfolgreiche status
    # duerfen nicht als 'stop' enden.
    terminal_status: str | None = None
    # C-18: stop-sequenzen kann der upstream nicht, der proxy schon.
    stop_sequences: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        self.tool_parser.allowed_tool_names = self.allowed_tool_names

    def _cap_final_output(self, text: str) -> str:
        """Finalen text auf das budget kuerzen.

        Wichtig: die durchsetzung in consume_event() kappte nur die
        STREAM-Deltas. Der aus dem akkumulierten cache zusammengesetzte
        endtext (finalize/build_response) muss ebenfalls gekappt werden —
        sonst liefert der proxy eine als 'length' markierte, aber
        ungekappte antwort (live-verifiziert: 12k zeichen bei
        max_tokens=30)."""
        if self.max_output_tokens is None:
            return text
        budget = self.max_output_tokens * _CHARS_PER_TOKEN_ESTIMATE
        if len(text) <= budget:
            return text
        self.output_limit_reached = True
        if self.logger:
            self.logger.warning(
                "Output limit reached: final text capped from %s to %s characters (%s tokens)",
                len(text),
                budget,
                self.max_output_tokens,
            )
        return text[:budget]

    def _output_budget_remaining(self) -> int | None:
        """Restbudget in zeichen, oder None wenn keine grenze gesetzt ist."""
        if self.max_output_tokens is None:
            return None
        return max(0, self.max_output_tokens * _CHARS_PER_TOKEN_ESTIMATE - self._output_chars)

    def is_empty_response(self) -> bool:
        """True when a round has no client-visible result or tool call.

        Reasoning alone is not a usable response: OpenCode stores it as an
        internal thinking part and otherwise treats the turn as a successful
        stop, leaving an executing agent unable to continue.

        T-06: geprueft wird der ERGEBNIS-ZUSTAND, nicht der rohe parser-
        zustand — ein abgeschnittenes protokoll-fragment und ein
        write-call ohne content gelten nicht als verwertbares ergebnis,
        sonst greift der leer-retry nicht. Calls aus dem REASONING-kanal
        zaehlen mit: das modell versteckt tool-aufrufe dort regelmaessig,
        und ohne sie wurde eine echte tool-runde als leer verworfen (der
        retry half nicht, der turn ging verloren).
        """
        text, reasoning = self.render_full_output()
        clean_text, _fragment_count = strip_unparseable_call_fragments(text)
        clean_text = strip_transcript_echo(clean_text)
        has_visible_text = bool(
            clean_text.strip()
            and strip_meta_chatter(clean_text) != ""
        )
        raw_calls = (
            list(self._server_side_tool_calls)
            + list(self.tool_parser.tool_calls)
            + list(self._deferred_reasoning_calls)
            + self._extract_reasoning_tool_calls(reasoning)
        )
        has_calls = bool(sanitize_tool_calls(raw_calls, fallback_url=self.fallback_tool_url))
        has_blocked = bool(self.blocked_tool_attempt_names)
        return not has_visible_text and not has_calls and not has_blocked

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
        # D-05: siehe die verwendung unten.
        blocked_native_seen: list[bool] | None = None
        debug_dump(self.logger or logging.getLogger("glm2api.null"), self.debug_enabled, "GLM SSE parsed event", payload)
        if not self.conversation_id and payload.get("conversation_id"):
            self.conversation_id = str(payload["conversation_id"])

        for part in payload.get("parts", []) if isinstance(payload.get("parts"), list) else []: # pyright: ignore[reportGeneralTypeIssues]
            if isinstance(part, dict) and part.get("logic_id"):
                logic_id = str(part["logic_id"])
                if logic_id not in self.parts_by_logic_id:
                    # T-20: REIHENFOLGE DES EINGANGS, nicht lexikografisch.
                    # `insort` sortierte die ids als strings — ab zehn
                    # parts kam `p10` zwischen `p1` und `p2`, der
                    # sichtbare text wurde consequently zerwuerfelt.
                    # Die reihenfolge, in der der upstream die parts
                    # sendet, ist die gemeinte.
                    self.ordered_logic_ids.append(logic_id)
                    self._logic_id_rank[logic_id] = len(self._logic_id_rank)
                    self.parts_by_logic_id[logic_id] = part
                    self._dirty_logic_ids.add(logic_id)
                else:
                    # Der Upstream sendet bei init-Events TOKEN-Schnipsel (nicht den
                    # vollen Stand!) und im finish-Event den kompletten Text.
                    # Snipsel werden konkateniert; finish-Volltext ersetzt, WENN er
                    # nicht bloss die bereits akkumulierte Folge fortsetzt.
                    existing = self.parts_by_logic_id[logic_id]
                    merged = _merge_part_texts(existing, part, event_status=str(payload.get("status", "")))
                    self.parts_by_logic_id[logic_id] = merged
                    # T-20: eine geaenderte part invalidiert den
                    # inkrementellen aufbau des Gesamtexts.
                    self._dirty_logic_ids.add(logic_id)
                    self._parts_epoch += 1
                self._render_cache_dirty = True
            # D-05: ein gesperrter nativer call beendet den durchlauf nicht
            # mehr. Der marker merkt sich, dass einer gesehen wurde; nach dem
            # parts-durchlauf wird genau einmal 'intervene' gemeldet.
            if blocked_native_seen is None:
                blocked_native_seen = [False]
            # Intercept server-side tool calls from meta_data or content items
            meta = part.get("meta_data") if isinstance(part, dict) else None
            if isinstance(meta, dict):
                extra = meta.get("tool_result_extra")
                if isinstance(extra, dict):
                    tool_call_name = str(extra.get("tool_call_name", "")).strip()
                    if tool_call_name.lower() in {"finish", "intervene", "cancel", "none", "open", "execute_sandbox_code", "code_interpreter", "sandbox", "run_code"}:
                        pass
                    elif is_blocked_tool_name(tool_call_name, None):
                        if tool_call_name not in self.blocked_tool_attempt_names:
                            self.blocked_tool_attempt_names.append(tool_call_name)
                        self._policy_dropped_call_count += 1
                        if self.logger:
                            self.logger.warning(
                                "Intercepted blocked native tool call in meta_data tool=%s",
                                tool_call_name,
                            )
                        if blocked_native_seen is None:
                            blocked_native_seen = [True]
                        else:
                            blocked_native_seen[0] = True
                        continue

            # Extract server-side native tool_calls from content items
            if isinstance(part, dict) and isinstance(part.get("content"), list):
                for content in part["content"]:
                    if isinstance(content, dict) and content.get("type") == "tool_calls":
                        tool_calls_data = content.get("tool_calls")
                        # T-11: `tool_calls` kann auch eine LISTE sein
                        # (beobachtete upstream-form). Der dict-zweig
                        # ignorierte sie komplett — der native call
                        # kam nie an, der agent blieb stehen.
                        if isinstance(tool_calls_data, list):
                            # T-11: `tool_calls` kommt auch als LISTE vor.
                            # WICHTIG: die gleichen pruefungen wie im
                            # dict-zweig — ohne sie waeren gesperrte native
                            # tools und calls ohne deklarierte tools
                            # ausfuehrbar gewesen (selbst eingebaut und
                            # sofort gemessen).
                            for entry in tool_calls_data:
                                if not isinstance(entry, dict):
                                    continue
                                entry_name = str(entry.get("name", "")).strip()
                                if not entry_name or entry_name.lower() in {
                                    "finish", "intervene", "cancel", "none"
                                }:
                                    continue
                                entry_arguments = entry.get("arguments", "{}")
                                if entry_name == "open":
                                    mapped = map_native_open_tool_call(
                                        entry_arguments, self.allowed_tool_names
                                    )
                                    if mapped is None:
                                        self.blocked_tool_attempt_names.append(entry_name)
                                        continue
                                    entry_name, entry_arguments = mapped
                                elif entry_name == "execute_sandbox_code":
                                    mapped = map_native_sandbox_tool_call(
                                        entry_arguments, self.allowed_tool_names
                                    )
                                    if mapped is None:
                                        self.blocked_tool_attempt_names.append(entry_name)
                                        continue
                                    entry_name, entry_arguments = mapped
                                if is_blocked_tool_name(entry_name, None):
                                    self.blocked_tool_attempt_names.append(entry_name)
                                    if blocked_native_seen is not None:
                                        blocked_native_seen[0] = True
                                    continue
                                if (
                                    self.allowed_tool_names is None
                                    or entry_name not in self.allowed_tool_names
                                ):
                                    self.blocked_tool_attempt_names.append(entry_name)
                                    continue
                                self._server_side_tool_calls.append(
                                    {
                                        "id": _coerce_call_id(entry.get("id"))
                                        or f"native-list-{len(self._server_side_tool_calls)}",
                                        "type": "function",
                                        "index": len(self._server_side_tool_calls),
                                        "function": {
                                            "name": entry_name,
                                            "arguments": entry_arguments,
                                        },
                                    }
                                )
                            continue
                        if isinstance(tool_calls_data, dict):
                            tool_name = str(tool_calls_data.get("name", "")).strip()
                            tool_id = str(tool_calls_data.get("id", "")).strip()
                            arguments = tool_calls_data.get("arguments", "{}")
                            if tool_name.lower() in {"finish", "intervene", "cancel", "none"}:
                                continue
                            if tool_name == "open":
                                mapped = map_native_open_tool_call(arguments, self.allowed_tool_names)
                                if mapped is None:
                                    # T-02: nicht abbildbar heisst in
                                    # jedem fall 'nicht ausfuehrbar' — kein
                                    # mapping (kein webfetch/read vorhanden
                                    # oder gar keine tools deklariert). Der
                                    # call wird als blockierter versuch
                                    # gemeldet und NICHT ueber die interne
                                    # sanitize-stelle doch noch abgebildet.
                                    self.blocked_tool_attempt_names.append(tool_name)
                                    if self.logger:
                                        # DIE ARGUMENTE MITLOGGEN. Ein
                                        # verworfener aufruf, dessen
                                        # argument man nicht sieht, ist eine
                                        # sackgasse: live 2026-09-26 (session
                                        # `glm2api-Ordner-Analyse`) verwarf der
                                        # proxy ~30 `open`-aufrufe mit genau
                                        # dieser meldung, OHNE dass erkennbar
                                        # war, warum sie nicht abbildbar waren
                                        # — und ohne dass sich die frage
                                        # beantworten liess, welche
                                        # argumentform das modell wirklich
                                        # sendet. Das argument ist die
                                        # einzige information, die hier etwas
                                        # aendern kann.
                                        self.logger.info(
                                            "Dropped native open call: not mappable under the declared tool contract "
                                            "allowed=%s args=%s",
                                            sorted(self.allowed_tool_names or ()),
                                            str(arguments)[:300],
                                        )
                                    continue
                                else:
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
                                            "Dropped side-effect-free sandbox self-talk call args=%s",
                                            arguments,
                                        )
                                    continue
                                # Schutznetz gegen modell-degeneration: der
                                # sandbox-kanal wird als ausfuehrungsweg
                                # genutzt, und ein entarteter turn spammte
                                # 40 mapped calls (live-fall 2026-09-25).
                                # Mehr als _MAX_MAPPED_SANDBOX_CALLS pro
                                # akkumulator werden verworfen.
                                if self._mapped_sandbox_calls >= _MAX_MAPPED_SANDBOX_CALLS:
                                    self.blocked_tool_attempt_names.append(tool_name)
                                    if self.logger:
                                        self.logger.warning(
                                            "Sandbox->bash mapping cap reached (%s), dropped further calls this turn",
                                            _MAX_MAPPED_SANDBOX_CALLS,
                                        )
                                    continue
                                mapped = map_native_sandbox_tool_call(arguments, self.allowed_tool_names)
                                if mapped is None:
                                    # T-02: siehe open-Zweig — nicht
                                    # abbildbar heisst 'nicht ausfuehrbar'.
                                    self.blocked_tool_attempt_names.append(tool_name)
                                    continue
                                else:
                                    mapped_name, mapped_args = mapped
                                    tool_name = mapped_name
                                    arguments = mapped_args
                                    self._mapped_sandbox_calls += 1
                                    if self.logger:
                                        self.logger.info(
                                            "Mapped native sandbox tool call to %s args=%s",
                                            tool_name,
                                            mapped_args,
                                        )
                            # T-02: `None` bedeutet "keine Tools deklariert"
                            # und damit "kein Call ausfuehrbar". Vorher
                            # uebersprang die pruefung in diesem pfad
                            # komplett, sodass ein request OHNE tools einen
                            # nativen call ausfuehren konnte.
                            # D-05: bei einem gesperrten call wurde mit
                            # `return` der ganze parts-durchlauf abgebrochen —
                            # ein gueltiger call, der im selben event SPÄTER
                            # kommt, ging verloren (reihenfolgeabhaengig).
                            # Jetzt wird der versuch gemerkt und die
                            # verarbeitung laeuft weiter.
                            tool_not_permitted = (
                                self.allowed_tool_names is None
                                or tool_name not in self.allowed_tool_names
                            )
                            if tool_not_permitted:
                                if tool_name not in self.blocked_tool_attempt_names:
                                    self.blocked_tool_attempt_names.append(tool_name)
                                # pro VORKOMMEN, unabhaengig von der
                                # entdopplung oben — `dropped_call_count`
                                # zaehlt naemlich jedes fragment einzeln.
                                self._policy_dropped_call_count += 1
                                if is_blocked_tool_name(tool_name, None):
                                    if self.logger:
                                        self.logger.warning(
                                            "Intercepted blocked native tool call tool=%s, recording blocked attempt",
                                            tool_name,
                                        )
                                    if blocked_native_seen is not None:
                                        blocked_native_seen[0] = True
                                    continue
                                continue
                            if tool_name and tool_id and tool_id not in self._server_side_tool_call_ids:
                                # C-13: die id-losen serverseitigen calls
                                # gingen voellig ungeprueft in den parser
                                # weiter — bzw. wurden an anderen stellen
                                # still verworfen. Ein call OHNE id ist aber
                                # kein belegtes echo: er kann ein gewollter
                                # aufruf sein. Er wird deshalb wie ein
                                # normaler call aufgenommen; nur ECHTE
                                # signatur-treffer aus der historie und
                                # doppelte ids im selben turn werden
                                # unterdrueckt.
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
                                # T-04: die innerhalb-TURN-signatur-dedup
                                # ist entfernt. Zwei calls mit eigener id
                                # sind ZWEI aufrufe, auch bei identischen
                                # argumenten — der zweite ging verloren
                                # (empirisch: A und B mit gleichem
                                # `filePath` -> nur A). Die echo-pruefung
                                # gegen die HISTORIE oben bleibt: genau das
                                # ist der fall, den sie abdecken soll.
                                # T-04: DREI Anforderungen kollidieren hier.
                                #   (a) Zwei bewusst gleiche calls (gleiche
                                #       argumente, eigene id) sind ZWEI
                                #       aufrufe und muessen beide ankommen.
                                #   (b) Eine degenerationsschleife mit 36
                                #       identischen calls (live beobachtet)
                                #       darf nicht 36 ausfuehrungen ergeben.
                                #   (c) Ein echo aus der historie bleibt
                                #       draussen (pruefung oben).
                                # Loesung: pro signatur sind BIS ZU 2
                                # aufrufe erlaubt — das deckt einen
                                # plausiblen wiederholungsversuch ab und
                                # bricht die schleife.
                                repeat = self._server_side_signature_counts.get(signature, 0)
                                if repeat >= _MAX_IDENTICAL_NATIVE_CALLS:
                                    if self.logger:
                                        self.logger.info(
                                            "Dropped identical native tool_call (loop guard) tool=%s repeats=%s",
                                            tool_name,
                                            repeat,
                                        )
                                    # T-25: der verworfene call muss fuer das
                                    # modell sichtbar sein, sonst zaehlt es
                                    # calls gegen ergebnisse und erfindet ein
                                    # limit. Gezaehlt wird der NATIVE name
                                    # (vor dem mapping), sonst meldet die
                                    # notice "read" und das modell sucht den
                                    # fehler im falschen werkzeug.
                                    self.loop_guard_dropped_count += 1
                                    native_name = str(tool_calls_data.get("name", "")).strip() or tool_name
                                    if native_name not in self.loop_guard_dropped_tools:
                                        self.loop_guard_dropped_tools.append(native_name)
                                    continue
                                self._server_side_signature_counts[signature] = repeat + 1
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
                            elif tool_name and not tool_id:
                                # C-13: ohne id gibt es keinen beleg des
                                # echos. Frueher fielen solche calls ersatzlos
                                # weg — auch dann, wenn sie sich von jedem
                                # historischen call unterschieden (empirisch:
                                # ein `read` auf einen NEUEN pfad kam nicht
                                # an). Jetzt wird eine stabile id vergeben und
                                # der call ausgeliefert; echte signatur-echos
                                # bleiben ueber `history_tool_call_signatures`
                                # ausgeschlossen.
                                local_id = f"native-{len(self._server_side_tool_calls)}-{self.created}"
                                arguments_text = (
                                    arguments if isinstance(arguments, str) else safe_json_dumps(arguments)
                                )
                                local_signature = f"{tool_name}:{arguments_text}"
                                if local_signature in self.history_tool_call_signatures:
                                    if self.logger:
                                        self.logger.info(
                                            "Dropped echoed native tool_call without id (history signature match) tool=%s",
                                            tool_name,
                                        )
                                    continue
                                self._server_side_tool_calls.append(
                                    {
                                        "id": local_id,
                                        "type": "function",
                                        "index": len(self._server_side_tool_calls),
                                        "function": {
                                            "name": tool_name,
                                            "arguments": arguments_text,
                                        },
                                    }
                                )

        text_delta, reasoning_delta = self._compute_deltas()
        self.last_full_text = self._cached_full_text
        self.last_full_reasoning = self._cached_full_reasoning

        # Ausgabegrenze durchsetzen. Der upstream kennt keine, ein
        # entarteter turn laeuft sonst endlos (live: 30k zeichen / 24 calls
        # in einer runde). Geschnitten wird an der TOKEN-Grenze, und ein
        # dadurch unvollstaendiger tool-call wird verworfen statt als
        # kaputtes json ausgeliefert.
        if self.max_output_tokens is not None:
            if self.output_limit_reached:
                # Grenze bereits erreicht: nichts mehr nachliefern
                reasoning_delta = ""
                text_delta = ""
            else:
                budget_chars = self.max_output_tokens * _CHARS_PER_TOKEN_ESTIMATE
                room = budget_chars - self._output_chars
                if room <= 0:
                    reasoning_delta = ""
                    text_delta = ""
                    self.output_limit_reached = True
                else:
                    # der denkkanal darf hoechstens seinen anteil nehmen;
                    # der rest bleibt fuer den lieferkanal reserviert.
                    reasoning_budget = int(budget_chars * _REASONING_BUDGET_SHARE) - self._reasoning_chars
                    reasoning_room = min(room, max(0, reasoning_budget))
                    if len(reasoning_delta) > reasoning_room:
                        reasoning_delta = reasoning_delta[:reasoning_room]
                    if len(reasoning_delta) + len(text_delta) > room:
                        text_delta = text_delta[: max(0, room - len(reasoning_delta))]
                        self.output_limit_reached = True
                    self._output_chars += len(reasoning_delta) + len(text_delta)
                    self._reasoning_chars += len(reasoning_delta)

        chunks: list[str] = []
        if reasoning_delta:
            # T-05: rohe protokoll-fragmente duerfen auch im reasoning-kanal
            # nicht an den client. Das modell versteckt tool-aufrufe dort
            # regelmaessig; der sichtbare denktext streamt weiter, das
            # protokoll wird entfernt und die calls fuer das finalize
            # gesammelt.
            reasoning_open = _find_unterminated_call_start(reasoning_delta)
            if reasoning_open != -1:
                # noch angebrochenes protokoll: bis zum aufbau zurueckhalten
                self._deferred_reasoning += reasoning_delta[reasoning_open:]
                reasoning_delta = reasoning_delta[:reasoning_open]
            else:
                reasoning_text, reasoning_calls = parse_tool_calls_from_text(
                    reasoning_delta,
                    allowed_tool_names=self.allowed_tool_names,
                )
                if reasoning_calls:
                    self._deferred_reasoning_calls.extend(reasoning_calls)
                reasoning_delta = reasoning_text
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

        # S-07: fruehwarnung vor dem parser. Solange das ende des
        # mitgefuehrten texts noch ein praefix einer narration-marke ist,
        # wird der delta NICHT an den parser gegeben — sonst streamt die
        # marke bei kleinen chunk-groessen, bevor sie als marke erkennbar
        # ist. Sobald der text entweder zur marke geworden ist (dann
        # uebernimmt die T-07-praeambel das puffern und verwerfen) oder
        # erkennbar etwas anderes ist, geht der ganze carry in einem
        # rutsch an den parser — die reihenfolge bleibt so erhalten.
        text_delta = self._narration_carry + text_delta
        if text_delta and _PROTOCOL_META_NARRATION_TAIL_RE.search(text_delta):
            self._narration_carry = text_delta
            text_delta = ""
        else:
            self._narration_carry = ""

        visible_text_delta = self.tool_parser.consume(text_delta)
        # S-07 (verschachtelt): NACH den aufrufen kann noch narration
        # kommen. Live-Struktur (debug-log, glm-5.3, 8 parallele reads):
        #   lid=21436e text='Wrong tool calls above — correcting to…'
        #   lid=bd7fc0 ntc=1                      <- erster aufruf
        #   lid=dffe3c ntc=0
        #   lid=be301b ntc=1                      <- zweiter aufruf
        #   lid=5c55d7 text='I must use `read`…instead of `open`. Correct
        #                    JSON protocol:'      <- narration NACH den calls
        # Die T-07-praeambel verwirft nur die ERSTE narration (die stand
        # vor dem ersten aufruf an); die zweite lief danach ungefiltert als
        # antwort raus. Ist der turn bereits im aufruf-modus, ist
        # protokoll-narration per definition kein antworttext — sie wird
        # hier still entfernt, genau wie `strip_meta_chatter` es im
        # finalize-pfad tut.
        if visible_text_delta and (self._server_side_tool_calls or self.tool_parser.tool_calls):
            visible_text_delta = strip_protocol_meta_narration(visible_text_delta)
            # S-08: zusaetzlich die strukturelle selbst-steuerung. Nur
            # hier — der turn ist mit einem call noch nicht fertig, es ist
            # also der laufende self-talk, den der client als assistant-
            # nachricht sieht. Der finale bericht (turn OHNE calls) bleibt
            # unberuehrt, weil dort eine aussage ueber `open` echter
            # inhalt sein kann (z. B. in einer analyse ueber den proxy).
            visible_text_delta = strip_self_steering(visible_text_delta, require_complete_sentence=True)
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
            # T-09/D-03: der midstream-guard pruefte nur auf den
            # `{"tool_calls"`-wrapper. Die NACKTE objektform
            # (`sieh {"name":"bash","arguments":{…`)Contains keinen
            # wrapper und lief dadurch als sichtbarer text heraus
            # (gemessen in 7 von 12 chunk-groessen). Beide opnerformen
            # gehoeren in denselben holdback — der finalize-safety-net
            # entfernt sie anschliessend.
            protocol_fragment = self.allowed_tool_names is not None and (
                _contains_protocol_fragment(visible_text_delta)
            )
            # T-07: sobald dieser turn einen tool-call enthaelt, darf bereits
            # gesendeter text nicht als antwort stehen bleiben. Solange
            # unklar ist, ob der turn tool-calls liefert, wird der text
            # deshalb nur in kleinen, eindeutig protokollfreien stuecken
            # ausgegeben und bei einem spaeter auftauchenden call zurueck-
            # gehalten, statt unumkehrbar gestreamt zu werden.
            # D-06: solange eine praeambel offen ist, ALLES puffern — erst
            # ein tool-call (dann ist die praeambel gegenstand) oder das
            # ende des turns (dann ist der gepufferte text die antwort und
            # muss in reihenfolge ausgegeben werden) loest das auf.
            turn_has_calls = bool(self._server_side_tool_calls or self.tool_parser.tool_calls)
            if self._preamble_pending:
                if turn_has_calls:
                    # der turn liefert aufrufe: die gepufferte praeambel ist
                    # gegenstand und wird nicht ausgegeben
                    self._deferred_visible_text = ""
                    self._preamble_pending = False
                else:
                    self._deferred_visible_text += visible_text_delta
                    visible_text_delta = ""
            if (
                visible_text_delta
                and not self._preamble_pending
                and self.allowed_tool_names is not None
                and not self._server_side_tool_calls
                and not self.tool_parser.tool_calls
            ):
                looks_like_preamble = bool(
                    re.search(
                        # T-07: die muster waren ausschliesslich deutsch.
                        # Live vorgekommen sind englische varianten
                        # ("I will read the file", "Let me check the file",
                        # "I'll now open the file") — die liefen komplett
                        # unerkannt durch.
                        r"\b(?:ich|ich\s+werde|als\s+nächstes|jetzt\s+|zuerst|"
                        r"ich\s+schreibe|ich\s+lese|ich\s+führe"
                        r"|i\s+will|i['’]?ll\s+(?:now\s+)?|let\s+me|"
                        r"i\s+(?:am\s+going\s+to|will\s+now)|"
                        r"i'?m\s+going\s+to|now\s+i\s+will|"
                        r"ich\s+werde\s+jetzt|ich\s+schau(?:e|te)|"
                        r"als\s+nächstes\s+schau)"
                        # S-07: protokoll-narration ist ebenfalls eine
                        # "praeambel" — das model erklaert das protokoll,
                        # statt es zu benutzen ('Wrong tool calls above',
                        # 'instead of `open`'). Faellt sie hier durch,
                        # streamt sie unumkehrbar als antwort. Mit dem
                        # muster greift die vorhandene T-07-maschinerie:
                        # puffern und bei einem folgenden call verwerfen.
                        # S-07-Muster: alternativ zu den obigen
                        # (siehe `_PROTOCOL_META_PHRASES`).
                        r"|" + _PROTOCOL_META_NARRATION_RE.pattern,
                        visible_text_delta,
                        re.IGNORECASE,
                    )
                )
                if looks_like_preamble:
                    # D-06: nur die praeambel zurueckzuhalten liess den
                    # FOLGETEXT sofort streamen — der client bekam dann
                    # "mache das." und erst spaeter "Ich" (gemessen:
                    # 'Ich mache das.' bei chunk=3 als ' mache das.').
                    # Das ist eine REIHENFOLGEUMSTELLUNG des sichtbaren
                    # texts. Solange unklar ist, ob der turn ueberhaupt
                    # tool-calls liefert, wird deshalb ALLES gepuffert.
                    self._preamble_pending = True
                    self._deferred_visible_text += visible_text_delta
                    visible_text_delta = ""
            # D-06: ein reiner whitespace-delta wird NIE zurueckgehalten.
            # Er kann kein protokollfragment und keine fence-eroeffnung
            # enthalten — die zurueckhaltung hat also keinen zweck, und
            # weil der zurueckgehaltene text erst in der finalen antwort
            # wieder auftaucht, FEHLTE ein zwischenzeichen im stream:
            # 'Hier ist die Anleitung.' kam als 'Hier ist dieAnleitung.'
            # an (gemessen bei chunk-groesse 2).
            whitespace_only = not visible_text_delta.strip()
            if (
                visible_text_delta
                and not whitespace_only
                and self.allowed_tool_names is not None
                and (
                    self.tool_parser.pending_text
                    or fence_pending
                    or fence_opens
                    or protocol_fragment
                )
            ):
                # Deferral: (a) parser haelt ein potentielles tool-protokoll-
                # stueck, (b) ein fence ist offen, (c) dieser delta oeffnet
                # einen fence, oder (d) der delta enthaelt selbst protokoll-
                # fragmente. Fences koennen das tool-protokoll umhuellen
                # (```json {"tool_calls":...}); das unwrap passiert im
                # finalize. Sonst wuerde JEDER text bei deklarierten tools
                # bis zum finalize gebuffert (UX-regression).
                self._deferred_visible_text += visible_text_delta
                visible_text_delta = ""
            elif visible_text_delta:
                # S-05: der deferred-puffer und der direkte stream waren ZWEI
                # senken ohne reihenfolge-garantie. Ohne diese stelle kam der
                # earlier gepufferte text erst im finalize heraus und stand
                # damit HINTER dem zwischenzeitlich direkt gestreamten —
                # eine echte reihenfolgeumstellung, live gemessen:
                #   'geholt via' + '2. **README** ... bestaetigt).'
                #   + '`bash` + `curl`): ``` alpha beta gamma ```'
                # (abschnitt mitten im satz, nummerierung verschoben).
                # Ausloeser war ein fence, der MITTEN in einem delta
                # geschlossen wurde: `fence_pending` war fuer dieses delta
                # noch wahr, der puffer gefuellt, der rest des turns direkt
                # gestreamt.
                #
                # S-06: derselbe puffer ist jetzt der EINZIGE geordnete
                # senken fuer sichtbaren text, und er nimmt auch reine
                # whitespace-deltas auf. Grund: whitespace neben
                # tool-calls ist ein artefakt des part-merge (live: 7 native
                # calls -> 14 leerzeilen im stream) und laesst sich nur
                # rausreissen, wenn man ihn BIS zum ende wartet — vorher
                # weiss niemand, ob noch text kommt. Als trennende zeile
                # zwischen zwei sichtbaren woertern bleibt er voll
                # erhalten: sobald echter text folgt, wird er in
                # reihenfolge mit ausgegeben (D-06 unveraendert).
                merged = self._deferred_visible_text + visible_text_delta
                if not merged.strip() and not self._emitted_visible_text:
                    # S-06: nur whitespace und bisher gab es KEINEN sichtbaren
                    # text in diesem turn -> warten. Entweder folgt echter
                    # text (dann geht der whitespace in reihenfolge mit
                    # raus, D-06 unveraendert) oder der turn besteht aus
                    # nichts ausser aufrufen (dann faellt er beim finalize
                    # weg — genau der artefakt, um den es geht: glm-5.3
                    # liefert neben jedem nativen call eine eigene
                    # whitespace-part, live 7 calls -> 14 leerzeilen im
                    # stream).
                    self._deferred_visible_text = merged
                    visible_text_delta = ""
                elif not self._deferred_text_is_publishable(self._deferred_visible_text):
                    # der gepufferte teil traegt noch arbeit offen, die der
                    # finalize-pfad macht (offener fence / protokoll-
                    # fragment) -> sticky warten, reihenfolge bleibt gewahrt
                    self._deferred_visible_text = merged
                    visible_text_delta = ""
                else:
                    self._deferred_visible_text = ""
                    visible_text_delta = merged
            if visible_text_delta:
                if visible_text_delta.strip():
                    self._emitted_visible_text = True
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
        # D-05: ein gesperrter nativer call beendet den durchlauf nicht mehr
        # (ein gueltiger call im selben event geht nicht verloren) — er wird
        # aber weiterhin als 'intervene' gemeldet, damit die negative
        # rueckmeldung an das modell geht.
        if blocked_native_seen is not None and blocked_native_seen[0]:
            return chunks, "intervene"
        return chunks, str(payload.get("status")) if payload.get("status") is not None else None

    @staticmethod
    def _deferred_text_is_publishable(text: str) -> bool:
        """S-05: darf der gepufferte sichtbare text JETZT raus?

        Nein, wenn er noch arbeit offenlaesst, die der finalize-pfad
        macht: ein ungeschlossener code-fence (darin koennte das
        tool-protokoll stecken, das der finalize-unwrap entfernt) oder ein
        protokollfragment (das der finalize-safety-net zerschneidet). In
        beiden faellen wartet der puffer weiter — die zurueckhaltung
        bleibt dann sticky, damit die reihenfolge gewahrt bleibt.
        """
        if not text:
            return True
        if not _fences_balanced(text):
            return False
        return not _contains_protocol_fragment(text)

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
        # T-13/S-08: der terminalstatus wird festgehalten, damit die
        # abschlussbewertung (finish_reason, [DONE]) ihn beruecksichtigen
        # kann — nicht nur `truncated_turn` und `blocked_tool_attempt_names`.
        self.terminal_status = str(status or "")
        # T-22: finalisierung war nicht idempotent. Ein zweiter aufruf
        # spulte denselben parser erneut (`tool_parser.flush()`) und gab
        # dieselben serverseitigen/gespeicherten calls ein zweites mal
        # aus. In einer kette aus finalize/retry/prepend-notice entstehen
        # dadurch doppelte tool_calls beim client. Der turn wird jetzt
        # genau einmal abgeschlossen.
        if self._finalized:
            log = self.logger or _LOGGER
            log.debug("Ignoring repeated finalize() call; turn was already finalized")
            return []
        self._finalized = True
        # S-07: der fruehwarn-carry muss noch an den parser, sonst geht
        # der text verloren (er war nie im parser und wird beim flush
        # nicht zurueckgegeben).
        if self._narration_carry:
            self.tool_parser.pending_text += self._narration_carry
            self._narration_carry = ""
        tail_text, xml_tool_calls = self.tool_parser.flush()
        xml_tool_calls = sanitize_tool_calls(xml_tool_calls, fallback_url=self.fallback_tool_url)
        # T-05: zurueckgehaltenes reasoning (protokoll-verdacht) zuerst
        # auswerten — der reasoning-fallback lief bisher nur, wenn der
        # textseiten-parser nichts fand, wodurch ein call im reasoning
        # neben einem erlaubten text-call voellig uebersehen wurde.
        deferred_reasoning = self._deferred_reasoning
        self._deferred_reasoning = ""
        deferred_calls = list(self._deferred_reasoning_calls)
        self._deferred_reasoning_calls = []
        if deferred_reasoning:
            deferred_calls.extend(
                parse_tool_calls_from_text(
                    deferred_reasoning,
                    allowed_tool_names=self.allowed_tool_names,
                )[1]
            )
        if deferred_calls:
            xml_tool_calls = xml_tool_calls + sanitize_tool_calls(
                deferred_calls, fallback_url=self.fallback_tool_url
            )
        # T-05: der reasoning-fallback ist KEIN ersatz, sondern eine
        # zusaetzliche quelle. Vorher lief er nur, wenn der textparser
        # nichts fand — thereby wurde ein call im reasoning komplett
        # uebersehen, sobald im selben turn ein erlaubter text-call
        # entstanden war (beobachtet: read im text, write im reasoning
        # -> nur read kam an). Beide kanaele werden unabhaengig
        # ausgewertet und anschliessend dedupliziert zusammengefuehrt.
        # T-05: der reasoning-call lag doppelt vor — einmal aus
        # `_deferred_reasoning_calls` (die deltas) und einmal aus dieser
        # auswertung (dieselbe tatsache im zusammengefuehrten volltext).
        # Beide listen werden zusammengefuehrt, aber nur was NICHT bereits
        # aus den deltas stammt. Innerhalb der extrahierten liste bleibt die
        # deduplizierung bei der call-id (T-04: zwei bewusst gleiche
        # aufrufe sind zwei aufrufe).
        # `deferred_calls` (nicht `self._deferred_reasoning_calls`): die
        # listen wurde oben geleert, bevor die zusammenfuehrung passiert.
        already_deferred_signatures = {
            _tool_call_signature(call) for call in deferred_calls
        }
        # der parser kann denselben reasoning-call ebenfalls gefunden haben
        # (denktext laeuft durch denselben stream-parser) — der gehoert
        # ebenfalls zur "schon vorhanden"-menge
        already_deferred_signatures.update(
            _tool_call_signature(call) for call in self.tool_parser.tool_calls
        )
        reasoning_calls = [
            call
            for call in self._extract_reasoning_tool_calls()
            if _tool_call_signature(call) not in already_deferred_signatures
        ]
        if reasoning_calls:
            xml_tool_calls = xml_tool_calls + sanitize_tool_calls(
                reasoning_calls, fallback_url=self.fallback_tool_url
            )

        # T-03/T-04: quelluebergreifende deduplizierung. Server-seitige
        # (native) und text/xml-calls werden nicht blind gemergt — derselbe
        # aufruf kann in beiden quellen auftauchen und wurde dann doppelt
        # ausgeliefert. Identitaet ist die call-id, sonst der name +
        # normalisierte argumente.
        # T-05: derselbe reasoning-call lag doppelt vor — einmal aus
        # `consume_event` (deferred) und einmal aus der auswertung hier.
        # `_merge_tool_calls` dedupliziert nur ZWISCHEN den quellen, nicht
        # innerhalb von `xml_tool_calls`.
        xml_tool_calls = _dedupe_tool_call_list(xml_tool_calls)
        merged_raw_calls = _merge_tool_calls(self._server_side_tool_calls, xml_tool_calls)
        all_tool_calls = sanitize_tool_calls(merged_raw_calls, fallback_url=self.fallback_tool_url)
        # S-07: die praeambel-verwurf-logik in `consume_event` laeuft nur,
        # wenn in DEMSELBEN event ein sichtbarer delta ankommt. Traegt der
        # aufruf in einem eigenen event (der haeufige fall: die
        # protokoll-narration steht im text-event, die `{"tool_calls":…}[]`
        # bloecke kommen in den folgenden), wurde der puffer nie verworfen
        # und stand am ende als antwort da. Genau der live-befund:
        #   'Wrong tool calls above — correcting to the allowed tools:…'
        # neben 8 korrekten reads. Hier ist die entscheidung moeglich:
        # der turn HAT aufrufe, also ist der gepufferte text die praeambel
        # und gehoert verworfen.
        if all_tool_calls and self._preamble_pending:
            self._preamble_pending = False
            self._deferred_visible_text = ""
        # T-06: das modell WOLLTE einen aufruf, der wegen fehlendem
        # pflichtargument nicht ausfuehrbar ist (`write` ohne content,
        # `read` ohne filePath). Vorher galt der turn danach als leerer
        # ERFOLG — `finish_reason=stop`, `content=None`, und der leer-retry
        # feuerte nicht: der client bekam eine leere, erfolgreiche antwort
        # und blieb stehen.
        collected_raw_calls = list(self.tool_parser.tool_calls) + list(
            self._server_side_tool_calls
        )
        # Ein GESPERRTER aufruf ist ein vollstaendig formulierter aufruf,
        # der nur abgelehnt wurde — er hat weder ein fehlendes
        # pflichtargument noch ist er abgeschnitten. Ohne diese
        # unterscheidung endet der turn als `error` und der client
        # wiederholt ihn endlos (5 min backoff je versuch, gemessen am
        # 2026-09-26).
        def _call_name(call: object) -> str:
            if not isinstance(call, dict):
                return ""
            function = call.get("function")
            if isinstance(function, dict):
                return str(function.get("name", "")).strip()
            return str(call.get("name", "")).strip()

        # Die Klassifikation kommt aus der SOLL-liste, nicht aus
        # `blocked_tool_attempt_names`: die wird erst weiter unten aus dem
        # text ermittelt und ist an dieser stelle noch leer. Sonst wuerde
        # jeder abgelehnte aufruf hier als 'nicht ausfuehrbar' gelten und
        # der turn endet als fehler — der client wiederholt ihn dann
        # endlos (5 min backoff je versuch, gemessen 2026-09-26).
        if (
            collected_raw_calls or self.tool_parser.dropped_call_count
        ) and not all_tool_calls and not self._unusable_calls_are_only_policy(
            list(collected_raw_calls), self.tool_parser.dropped_call_count
        ):
            self.truncated_turn = True
            log = self.logger or _LOGGER
            log.warning(
                "Tool call(s) present but not executable (missing required argument): "
                "parsed=%s unusable=%s — treating the turn as failed",
                len(collected_raw_calls),
                self.tool_parser.dropped_call_count,
            )

        if self.output_limit_reached and all_tool_calls:
            # Die ausgabegrenze hat den turn abgeschnitten. sanitize_
            # tool_calls verwirft bereits calls ohne erforderliche
            # argumente (P-03) — ein unvollstaendiger call darf aber
            # NIE als ausfuehrung durchgehen. Wir pruefen deshalb
            # explizit auf parsebare, pflichtfeld-erfuellende calls.
            executable = [
                tc
                for tc in all_tool_calls
                if _call_is_executable(tc)
            ]
            if len(executable) != len(all_tool_calls):
                dropped = len(all_tool_calls) - len(executable)
                all_tool_calls = executable
                if self.logger:
                    self.logger.warning(
                        "Output limit reached (%s tokens): dropped %s incomplete tool call(s)",
                        self.max_output_tokens,
                        dropped,
                    )
                if not all_tool_calls:
                    self.output_limit_reached = False
                    self.truncated_turn = True

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
        # Ausgabegrenze auch auf dem ZUSAMMENGESETZTEN endtext durchsetzen
        # (die delta-kappung in consume_event greift fuer den cache nicht).
        final_text = self._cap_final_output(final_text)
        # C-18: `stop` kann der upstream nicht durchsetzen, der proxy schon.
        # Der text endet am ersten stop-folge; der rest wird abgeschnitten,
        # damit der client keine anteile sieht, die er nie bestellt hat.
        if self.stop_sequences and final_text:
            for stop_sequence in self.stop_sequences:
                stop_index = final_text.find(stop_sequence)
                if stop_index != -1:
                    final_text = final_text[:stop_index]
                    break
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
                detect_all=True,
            )
            final_text = cleaned_text.strip()
            if attempted_tool_calls:
                recovered_calls: list[dict[str, object]] = []
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
                        recovered_calls.append(tc_copy)
                    else:
                        self.blocked_tool_attempt_names.append(tool_name)
                        # policy-drop, kein unbrauchbarer call (siehe
                        # `_policy_dropped_call_count`): der aufruf war
                        # vollstaendig, nur nicht erlaubt.
                        self._policy_dropped_call_count += 1
                # T-12: safety-net-calls durch dieselbe sanitisation und
                # required-argument-pruefung schicken wie der normale
                # parser-pfad — sonst koennte ein write-call ohne content
                # oder ein ungepruefter filePath durchgehen.
                all_tool_calls.extend(
                    sanitize_tool_calls(recovered_calls, fallback_url=self.fallback_tool_url)
                )
                final_text = cleaned_text.strip()
            # Safety-net (Live-Fall 2026-09-24, ses_f2bc23762ffeoOkPYHAoqhwpwm):
            # der upstream brach mitten im call-json ab — das fragment ist
            # unparsebar und wurde vom parser zurueckgehalten, wuerde hier
            # aber als sichtbarer text durchgehen. Nie eine antwort.
            final_text, fragment_count = strip_unparseable_call_fragments(final_text)
            # Ein GESPERRTER aufruf ist vollstaendig formuliert und wurde
            # nur abgelehnt — er ist KEIN abgeschnittener turn. Ohne diese
            # gegenrechnung endet der turn als `error` und der client
            # wiederholt ihn endlos (5 min backoff, gemessen).
            # Die namen der abgelehnten aufrufe stehen zu diesem zeitpunkt
            # noch nicht fest (sie werden weiter unten erst aus dem text
            # ermittelt). Die klassifikation kommt deshalb direkt aus dem
            # text gegen die SOLL-liste: ein fragment, dessen werkzeug
            # nicht deklariert ist, ist ein policy-drop und KEIN
            # abgeschnittener turn.
            policy_fragments = 0
            if self.allowed_tool_names is not None:
                allowed_lower = {name.lower() for name in self.allowed_tool_names}
                for match in re.finditer(r'"name"\s*:\s*"([^"]{1,80})"', final_text):
                    if match.group(1).strip().lower() not in allowed_lower:
                        policy_fragments += 1
            fragment_count = max(0, fragment_count - policy_fragments)
            if fragment_count > 0:
                self.truncated_turn = True
                log = self.logger or _LOGGER
                log.warning(
                    "Stripped %s unparseable tool-call fragment(s) from final text "
                    "(upstream stream ended mid-JSON)",
                    fragment_count,
                )
        if self.allowed_tool_names is not None and not self.blocked_tool_attempt_names:
            # Blockierte Versuche IMMER erfassen, auch wenn im selben Turn
            # bereits gueltige Calls entstanden sind (V-02). Der alte Guard
            # `not all_tool_calls` liess genau diese Faelle unerkannt, sodass
            # das Modell keine negative Rueckmeldung bekam und den blockierten
            # Call wiederholte.
            attempted_names: list[str] = []
            for source_text in (self._cached_full_text.strip(), self._cached_full_reasoning.strip()):
                if source_text:
                    attempted_names.extend(detect_tool_call_names(source_text))
            # T-10/T-11: der vergleich ist case-insensitiv. Sonst umgeht
            # `OPEN_URL` die erkennung, obwohl `open_url` gesperrt ist.
            allowed_lower = {name.lower() for name in self.allowed_tool_names}
            unavailable_names = sorted(
                {
                    name
                    for name in attempted_names
                    if name.lower() not in allowed_lower
                    and name.lower() not in {"finish", "intervene", "cancel", "none"}
                }
            )
            if unavailable_names:
                self.blocked_tool_attempt_names.extend(unavailable_names)
                # Jeder hier gefundene name ist ein POLICY-drop: der
                # aufruf war vollstaendig formuliert und wurde nur
                # abgelehnt. Ohne diesen zaehler stuft die T-06-stelle
                # den turn als `truncated_turn` ein und der client
                # wiederholt ihn endlos (5 min backoff, gemessen
                # 2026-09-26 am agentenlauf).
                self._policy_dropped_call_count += len(unavailable_names)
                allowed_names = ", ".join(sorted(self.allowed_tool_names)) or "(none)"
                # Die Negativ-Rueckmeldung ersetzt nur dann den sichtbaren
                # Text, wenn es in diesem Turn keine gueltigen Calls gibt —
                # sonst wuerde sie den Call-Content verdraengen.
                if not all_tool_calls:
                    final_text = (
                        "The model attempted to call an undeclared tool: "
                        + ", ".join(f"`{name}`" for name in unavailable_names)
                        + f". Blocked. Only these tools are allowed in this round: {allowed_names}."
                    )
        if final_text:
            final_text = self._sanitize_visible_text(final_text)
            # S-06: derselbe whitespace-artefakt wie im stream, fuer den
            # non-stream-pfad. Mehrere protokollbloecke mit leerzeilen
            # dazwischen ergeben einen inhalt, der NICHTS sagt — der client
            # (opencode) legt daraus einen leeren text-part an bzw. sendet
            # eine leere assistant-nachricht. Mit inhalt daneben ist er
            # unschaedlich, allein ist er nur ballast.
            if all_tool_calls and not final_text.strip():
                final_text = ""
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
        # T-18: der client hat einen tool-vertrag verlangt (`required` oder
        # eine konkrete auswahl) und der turn liefert prosa. Das ist kein
        # ergebnis — die antwort wird als vertragsverletzung markiert, damit
        # der client sie nicht als abschluss liest, und der aufrufer kann
        # eine erneute runde starten.
        # S-12: `tool_choice: none` ist eine VERBOTSSPLICHT des clients.
        # Bisher wurden nur die tool-schemata aus dem prompt entfernt —
        # ein trotzdem erzeugter aufruf wurde regulaer ausgeliefert. Der
        # client, der tools ausdruecklich verboten hat, konnte so doch
        # einen strukturierten tool-call bekommen (das inverse
        # routing-problem zu `required`). Der aufruf wird verweigert und
        # als vertragsverletzung sichtbar gemacht, nicht ausgefuehrt.
        if all_tool_calls and self.tool_choice_mode == "none":
            refused = ", ".join(
                sorted(
                    {
                        str((call.get("function") or {}).get("name", ""))  # type: ignore[union-attr]
                        for call in all_tool_calls
                    }
                    - {""}
                )
            )
            for call in all_tool_calls:
                name = str((call.get("function") or {}).get("name", ""))  # type: ignore[union-attr]
                if name and name not in self.blocked_tool_attempt_names:
                    self.blocked_tool_attempt_names.append(name)
            all_tool_calls = []
            self.required_tool_missing = True
            violation = (
                f"[tool_choice_violation] The client set `tool_choice: none` for this round, "
                f"but the model requested {refused or 'a tool'}. No tool was executed.\n\n"
            )
            final_text = (violation + final_text) if final_text.strip() else violation
            log = self.logger or _LOGGER
            log.warning(
                "tool_choice=none violated: model requested %s — call refused, not executed",
                refused or "an unnamed tool",
            )

        if not all_tool_calls and final_text.strip() and self.tool_choice_mode in {"required", "specific"}:
            self.required_tool_missing = True
            contract = (
                f"exactly `{self.tool_choice_name}`" if self.tool_choice_mode == "specific" and self.tool_choice_name
                else "at least one tool"
            )
            final_text = (
                f"[tool_choice_violation] The client required {contract} in this round, "
                "but the model answered with text only. No tool was executed.\n\n" + final_text
            )
            log = self.logger or _LOGGER
            log.warning(
                "tool_choice=%s not satisfied: model answered with text instead of a tool call",
                self.tool_choice_mode,
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

        # T-13: ein turn, der mit einem blockierten oder abgeschnittenen
        # protokoll endet und keine verwertbare antwort hat, wird nicht als
        # regulaerer 'stop' ausgewiesen. Clients sollen daran erkennen
        # koennen, dass kein ergebnis vorliegt.
        if self.output_limit_reached:
            # Ausgabegrenze erreicht: das ist ein 'length'-Abschluss, kein
            # Fehler — der client kann daraus ableiten, dass es weiter
            # arbeiten muss.
            finish_reason = "length"
        elif self.blocked_tool_attempt_names and not (self.truncated_turn or self.required_tool_missing):
            # Ein GESPERRTER oder nicht deklarierter aufruf ist KEIN fehler.
            #
            # Gemessen an einem echten agentenlauf (2026-09-26): der
            # abschluss dieser klasse ging als `finish_reason: "error"`
            # raus. Der client wertete das als stream-fehler und
            # wiederholte den turn mit exponentiellem backoff — 5 min
            # bis zum naechsten versuch, dann wieder, weil das modell
            # `open` erneut aufrief (gleicher prompt, gleiche
            # modell-neigung; `open` ist im GLM-webchat ein natives
            # werkzeug und deshalb in der sperrliste). Endlose
            # schleife, ohne dass sich etwas bewegt hat.
            #
            # Der turn ist in Wahrheit VOLLSTAENDIG: das modell hat
            # geantwortet ("dieses werkzeug gibt es nicht, ich mache
            # stattdessen X"). Der sichtbare hinweis sagt ausdruecklich,
            # dass nichts ausgefuehrt wurde — es gibt also nichts zu
            # verbergen und nichts zu wiederholen. `stop` beendet den
            # turn regulaer; der agent liest den hinweis und macht
            # weiter.
            #
            # `truncated_turn` und `required_tool_missing` bleiben
            # `error`: dort fehlt dem client wirklich etwas
            # Brauchbares, und ein Retry ist berechtigt.
            finish_reason = "tool_calls" if all_tool_calls else "stop"
        elif self.terminal_status and self.terminal_status not in _SUCCESSFUL_TERMINAL_STATUSES:
            # T-13/S-08: es gab KEINEN terminalstatus-vertrag. Jeder status
            # ('error', 'aborted', 'cancelled', 'timeout', 'intervene')
            # endete mit `finish_reason: "stop"` und `data: [DONE]` — der
            # client las einen abgebrochenen turn als vollstaendige
            # antwort, und der anthropic-adapter uebersetzte das in
            # `stop_reason: end_turn` + `message_stop`, also ein
            # ERFOLGSSIGNAL. Eine abgebrohene runde ist jetzt ein fehler.
            finish_reason = "error"
        else:
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
        # T-13/S-08: `[DONE]` ist das ERFOLGSZEICHEN des SSE-streams. Nach
        # einem fehlerhafter abschluss wuerde es genau das wiederholen, was
        # gerade abgeschafft wurde.
        if finish_reason != "error" or all_tool_calls:
            chunks.append("data: [DONE]\n\n")
        debug_dump(self.logger or logging.getLogger("glm2api.null"), self.debug_enabled, "GLM SSE finalize output", chunks)
        return chunks

    def prepend_blocked_notice(
        self, blocked_names_text: str, finalize_chunks: list[str]
    ) -> list[str]:
        """T-10 (live 2026-09-25): die negativ-follow-up-runden sind
        erschoepft, das modell behauptet aber trotzdem, es habe den
        blockierten call ausgefuehrt. Diese notice geht VOR der antwort
        raus, damit der client die erfindung nicht als erfolg liest.

        Wichtig: NICHT erneut finalizen — `finalize()` ist nicht
        idempotent und wuerde den bereits erzeugten prose-chunk verlieren.
        Stattdessen wird genau ein zusaetzlicher content-delta vorangestellt."""
        notice = (
            f"[blocked_tool_notice] The tool(s) {blocked_names_text} are not available in "
            "this environment and were NOT executed. Do not claim to have called them "
            "or to have seen any result from them."
        )
        self.blocked_tool_attempt_names.extend(
            name.strip() for name in blocked_names_text.split(",") if name.strip()
        )
        delta: dict[str, object] = {"content": notice}
        if not self.emitted_role:
            delta = {"role": "assistant", "content": notice}
            self.emitted_role = True
        notice_chunk = self._chunk_json(
            {"choices": [{"index": 0, "delta": delta, "finish_reason": None}]}
        )
        return [notice_chunk, *finalize_chunks]

    def build_response(self, status: str | None = None) -> dict[str, object]:
        """T-13/S-08: `status` erlaubt dem aufrufer, einen
        fehlerhaften abschluss auch im non-stream-pfad durchzureichen. Ohne
        argument gilt der beim finalize() gespeicherte terminalstatus."""
        # T-13/S-08: expliziter status schlägt den gespeicherten.
        effective_status = self.terminal_status if status is None else str(status or "")
        full_text, full_reasoning = self._render_full_output()
        if not full_text and self.last_full_text:
            full_text = self.last_full_text
        if not full_reasoning and self.last_full_reasoning:
            full_reasoning = self.last_full_reasoning
        full_text = self._cap_final_output(full_text)
        # C-18: stop-sequenzen auch im non-stream-pfad durchsetzen
        if self.stop_sequences and full_text:
            for stop_sequence in self.stop_sequences:
                stop_index = full_text.find(stop_sequence)
                if stop_index != -1:
                    full_text = full_text[:stop_index]
                    break
        # P-07/D-03: unterminiertes tool-markup vor dem parser entfernen.
        # Der stream-pfad haelt es ueber den markup-holdback zurueck, der
        # finalpfad tat das nicht und lieferte rohes DSML als antwort
        # (gemessen in 12 von 12 chunk-groessen).
        # D-01: der streaming-pfad haelt einen angebrochenen
        # tool-protokoll-praefix im holdback zurueck, der final-pfad tat
        # das nicht. Der client sah im stream nichts und in der
        # abschlussantwort `{"tool` als inhalt — mit `finish_reason:
        # stop`, also als ERFOLG verlesen. Dieselbe entscheidung muss der
        # final-pfad treffen, sonst sind die beiden pfade nicht
        # gleichwertig.
        full_text, tool_prefix_fragments = strip_unterminated_tool_prefix(full_text)
        if tool_prefix_fragments:
            self.truncated_turn = True
            log = self.logger or _LOGGER
            log.warning(
                "Stripped %s unterminated tool-protocol prefix(es) from non-streaming text",
                tool_prefix_fragments,
            )
        full_text, markup_fragments = strip_unterminated_markup(full_text)
        if markup_fragments:
            self.truncated_turn = True
            log = self.logger or _LOGGER
            log.warning(
                "Stripped %s unterminated tool-markup fragment(s) from non-streaming text",
                markup_fragments,
            )
        clean_content, xml_tool_calls = parse_tool_calls_from_text(
            full_text.strip(),
            allowed_tool_names=self.allowed_tool_names,
        )
        # T-17: der meta-chatter-filter lief NUR im stream-pfad. Mit
        # vorhandenen tool-calls blieb er hier ungefiltert — der client bekam
        # 'open ist nicht verfuegbar' als antwort, waehrend der stream '' lieferte.
        # Gleiche bedingung, gleicher filter: nur wenn dieser turn
        # tatsaechlich tool-calls ausliefert, ist der rest meta-chatter.
        if self._server_side_tool_calls or xml_tool_calls or self.tool_parser.tool_calls:
            clean_content = strip_meta_chatter(clean_content)
        clean_content, fragment_count = strip_unparseable_call_fragments(clean_content)
        fragment_count -= count_blocked_call_fragments(
            clean_content, self.blocked_tool_attempt_names
        )
        if fragment_count > 0:
            self.truncated_turn = True
            log = self.logger or _LOGGER
            log.warning(
                "Stripped %s unparseable tool-call fragment(s) from non-streaming response text",
                fragment_count,
            )
        xml_tool_calls = sanitize_tool_calls(xml_tool_calls, fallback_url=self.fallback_tool_url)
        # T-05 (non-stream): derselbe fehler wie im stream-pfad. Der
        # reasoning-kanal wird unabhaengig ausgewertet, damit ein call
        # dort nicht verloren geht, nur weil der textparser schon einen
        # anderen gefunden hat.
        reasoning_tool_calls = self._extract_reasoning_tool_calls(full_reasoning)
        if reasoning_tool_calls:
            xml_tool_calls = xml_tool_calls + reasoning_tool_calls
        # T-05: was uebrig bleibt, ist denktext. Rohe protokoll-fragen
        # duerfen dem client nicht als thinking-antwort gezeigt werden.
        # Das ORIGINAL wird fuer die blocked-erkennung behalten: nach dem
        # bereinigen ist der name eines blockierten calls nicht mehr
        # sichtbar, der versuch ginge sonst als leerer turn durch.
        raw_reasoning = full_reasoning
        full_reasoning, reasoning_fragments = strip_unparseable_call_fragments(full_reasoning)
        if reasoning_fragments:
            self.truncated_turn = True
            log = self.logger or _LOGGER
            log.warning(
                "Stripped %s tool-call fragment(s) from non-streaming reasoning text",
                reasoning_fragments,
            )
        clean_reasoning, leaked_reasoning_calls = parse_tool_calls_from_text(
            full_reasoning.strip(),
            allowed_tool_names=None,
            detect_all=True,
        )
        # Immer den bereinigten text uebernehmen, auch wenn der parser KEINE
        # Calls lieferte: bei einem blockierten call entfernt er die
        # protokoll-spanne trotzdem, sonst bliebe das roh-protokoll als
        # denktext stehen.
        full_reasoning = clean_reasoning.strip()
        for leaked_call in leaked_reasoning_calls:
            leaked_function = leaked_call.get("function")
            if not isinstance(leaked_function, dict):
                continue
            leaked_name = str(leaked_function.get("name", "")).strip()
            if leaked_name:
                self.blocked_tool_attempt_names.append(leaked_name)
        full_reasoning, leftover = strip_unparseable_call_fragments(full_reasoning)
        if leftover:
            log = self.logger or _LOGGER
            log.warning("Stripped %s protocol residue(s) from reasoning text", leftover)
        if self.allowed_tool_names is not None and not xml_tool_calls:
            # Non-stream counterpart of finalize(): record blocked tool
            # attempts so the client can start a negative-result round.
            attempted_names: list[str] = []
            for source_text in (full_text.strip(), raw_reasoning.strip()):
                if source_text:
                    attempted_names.extend(detect_tool_call_names(source_text))
            allowed_lower = {name.lower() for name in self.allowed_tool_names}
            self.blocked_tool_attempt_names.extend(
                name
                for name in attempted_names
                if name.lower() not in allowed_lower
                and name.lower() not in {"finish", "intervene", "cancel", "none"}
            )

        # T-03/T-04: quelluebergreifende deduplizierung wie in finalize();
        # auch die gemergte liste sanitizen (reparatur + C0-filter, paritaet
        # zum stream-pfad)
        xml_tool_calls = _dedupe_tool_call_list(xml_tool_calls)
        merged_raw_calls = _merge_tool_calls(self._server_side_tool_calls, xml_tool_calls)
        all_tool_calls = sanitize_tool_calls(merged_raw_calls, fallback_url=self.fallback_tool_url)
        # T-06: siehe finalize() — ein turn, dessen einziger call
        # unbrauchbar war (fehlendes pflichtargument), ist kein leerer
        # erfolg, sondern ein fehlerhafter turn.
        #
        # Ein GESPERRTER aufruf ist davon zu unterscheiden: er war
        # vollstaendig formuliert und wurde nur abgelehnt. Zaehlt man ihn
        # hier mit, endet der turn als `error`, und der echte client
        # wiederholt ihn endlos (5 min backoff je versuch, gemessen am
        # agentenlauf 2026-09-26). Deshalb wird der anteil der
        # abgelehnten aufrufe herausgerechnet — dieselbe rechnung wie im
        # stream-pfad.
        _ns_collected = list(self.tool_parser.tool_calls) + list(self._server_side_tool_calls)
        if (
            _ns_collected or self.tool_parser.dropped_call_count
        ) and not all_tool_calls and not self._unusable_calls_are_only_policy(
            _ns_collected, self.tool_parser.dropped_call_count
        ):
            self.truncated_turn = True

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
        # T-18: MUSS vor dem message-bau passieren, sonst traegt die
        # verletzungs-meldung nicht in die antroed des clients.
        # S-12: non-stream-gegenstueck zu `tool_choice: none` — siehe
        # kommentar im stream-pfad. Ohne diesen guard waere die
        # stream/non-stream-paritaet gebrochen: der client mit
        # `none` bekame im non-stream-pfad trotzdem seinen aufruf.
        if all_tool_calls and self.tool_choice_mode == "none":
            refused = ", ".join(
                sorted(
                    {
                        str((call.get("function") or {}).get("name", ""))  # type: ignore[union-attr]
                        for call in all_tool_calls
                    }
                    - {""}
                )
            )
            for call in all_tool_calls:
                name = str((call.get("function") or {}).get("name", ""))  # type: ignore[union-attr]
                if name and name not in self.blocked_tool_attempt_names:
                    self.blocked_tool_attempt_names.append(name)
            all_tool_calls = []
            self.required_tool_missing = True
            final_content = (
                f"[tool_choice_violation] The client set `tool_choice: none` for this round, "
                f"but the model requested {refused or 'a tool'}. No tool was executed."
                + ("\n\n" + final_content if final_content else "")
            )
            log = self.logger or _LOGGER
            log.warning(
                "tool_choice=none violated (non-stream): model requested %s — call refused, not executed",
                refused or "an unnamed tool",
            )
        if not all_tool_calls and self.tool_choice_mode in {"required", "specific"}:
            contract = (
                f"exactly `{self.tool_choice_name}`" if self.tool_choice_mode == "specific" and self.tool_choice_name
                else "at least one tool"
            )
            self.required_tool_missing = True
            if final_content:
                final_content = (
                    f"[tool_choice_violation] The client required {contract} in this round, "
                    "but the model answered with text only. No tool was executed.\n\n" + final_content
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
                    "finish_reason": (
                        "tool_calls"
                        if all_tool_calls
                        else (
                            "length"
                            if self.output_limit_reached
                            else (
                                "error"
                                if (
                                    self.required_tool_missing
                                    or self.truncated_turn
                                    # Ein GESPERRTER aufruf ist KEIN fehler,
                                    # sondern eine vollstaendige antwort
                                    # ("dieses werkzeug gibt es nicht") — als
                                    # `error` wertete der echte client das als
                                    # stream-fehler und wiederholte den turn
                                    # mit 5-minuten-backoff endlos, weil das
                                    # modell `open` bei jedem versuch erneut
                                    # aufrief (agentenlauf 2026-09-26).
                                    # Ein abgeschnittener turn
                                    # (`truncated_turn`) bleibt `error`:
                                    # dort fehlt dem client wirklich etwas.
                                    or (
                                        self.blocked_tool_attempt_names
                                        and not self._blocked_only_turn()
                                    )
                                    or effective_status
                                    and effective_status not in _SUCCESSFUL_TERMINAL_STATUSES
                                )
                                else "stop"
                            )
                        )
                    ),
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

    def _track_emitted_state(self, text_delta: str, reasoning_delta: str) -> None:
        """T-20: fuehrt den umlautenden klammer-/string-zustand des
        gesendeten texts inkrementell nach (O(len(fragment)) statt
        O(gesamttext)) und behaelt nur die letzte zeichenkette fuer die
        satzzeichen-/blockstart-pruefung."""
        if text_delta:
            self._emitted_text_open_brackets, self._emitted_text_in_string = _scan_brackets(
                text_delta,
                self._emitted_text_open_brackets,
                self._emitted_text_in_string,
            )
            self._emitted_text_tail = (self._emitted_text_tail + text_delta)[-_EMITTED_TAIL_CHARS:]
        if reasoning_delta:
            self._emitted_reasoning_tail = (
                self._emitted_reasoning_tail + reasoning_delta
            )[-_EMITTED_TAIL_CHARS:]

    def _emitted_text_needs_continuation(self) -> bool:
        """Laeuft der gesendete text in einer offenen struktur? Dann ist die
        naechste part eine fortsetzung (T-20)."""
        if not (self._emitted_text_open_brackets or self._emitted_text_in_string):
            return False
        if '"' in self._emitted_text_tail or "{" in self._emitted_text_tail or "[" in self._emitted_text_tail:
            return True
        return text_continues_protocol(self._emitted_text_tail)

    def _compute_deltas(self) -> tuple[str, str]:
        self._render_full_output()
        text_delta_parts: list[str] = []
        reasoning_delta_parts: list[str] = []

        # T-20 (perf): siehe `_last_rendered_dirty`. Reihenfolge wie beim
        # vollen durchlauf — die deltas entstehen sonst in anderer
        # reihenfolge als die parts.
        ranked = sorted(
            self._last_rendered_dirty,
            key=lambda item: self._logic_id_rank.get(item, 0),
        )
        for logic_id in ranked:
            rendered_text = self._cached_part_texts.get(logic_id, "")
            rendered_reasoning = self._cached_part_reasonings.get(logic_id, "")

            if rendered_text:
                prev_len = self._part_text_sent.get(logic_id, 0)
                is_new = logic_id not in self._known_text_id_set
                if is_new:
                    self._known_logic_ids_for_text.append(logic_id)
                    self._known_text_id_set.add(logic_id)
                    # T-20 (interleaving): derselbe trenner-schutz wie in
                    # `_render_full_output()`. Hier ist er sogar wichtiger:
                    # dieser pfad IST der stream, den der client sieht. Ein
                    # eingefuegtes `\n\n` mitten im json-protokoll liess den
                    # parser den call verlieren und den rest als text
                    # ausliefern.
                    # T-20: dieselbe verkettungsregel wie im finalpfad —
                    # ein `\n\n` an jeder part-grenze zerreiss jede zeile,
                    # wenn der upstream einen text ueber viele logic_ids
                    # verteilt (live: 166 ids in einem turn).
                    # S-06: eine part OHNE inhalt bekommt keinen absatz-
                    # umbruch. Live (2026-09-26) lieferte glm-5.3 neben
                    # jedem nativen tool_call eine eigene (leere) text-part;
                    # 7 calls ergaben 6 grenzen und damit EXAKT 12
                    # leerzeilen als sichtbaren text — eine leere assistant-
                    # nachricht in der TUI und ballast im kontext. Der
                    # trenner ist zwischen zwei echten absaetzen richtig,
                    # vor einem leeren part ist er reiner muell.
                    if (
                        (text_delta_parts or self._part_text_sent)
                        and rendered_text.strip()
                        and not self._emitted_text_needs_continuation()
                        and (
                            _ends_sentence(self._emitted_text_tail)
                            or _starts_new_block(rendered_text)
                        )
                    ):
                        text_delta_parts.append("\n\n")
                    text_delta_parts.append(rendered_text)
                elif len(rendered_text) > prev_len:
                    text_delta_parts.append(rendered_text[prev_len:])
                self._part_text_sent[logic_id] = len(rendered_text)

            if rendered_reasoning:
                prev_len = self._part_reasoning_sent.get(logic_id, 0)
                is_new = logic_id not in self._known_reasoning_id_set
                if is_new:
                    self._known_logic_ids_for_reasoning.append(logic_id)
                    self._known_reasoning_id_set.add(logic_id)
                    # siehe text-zweig: gleiche regel fuer den
                    # reasoning-kanal (dort landen die protocol-fragmenten).
                    if (
                        (reasoning_delta_parts or self._part_reasoning_sent)
                        and not text_continues_protocol(self._emitted_reasoning_tail)
                        and (
                            _ends_sentence(self._emitted_reasoning_tail)
                            or _starts_new_block(rendered_reasoning)
                        )
                    ):
                        reasoning_delta_parts.append("\n\n")
                    reasoning_delta_parts.append(rendered_reasoning)
                elif len(rendered_reasoning) > prev_len:
                    reasoning_delta_parts.append(rendered_reasoning[prev_len:])
                self._part_reasoning_sent[logic_id] = len(rendered_reasoning)

        self._last_rendered_dirty.clear()
        text_delta = "".join(text_delta_parts)
        reasoning_delta = "".join(reasoning_delta_parts)
        # T-20: nur das NEUE fragment betrachten, nicht den gesamten
        # gesendeten text. Der klammer-/string-zustand wird fortgeschrieben.
        self._track_emitted_state(text_delta, reasoning_delta)
        return text_delta, reasoning_delta

    def _join_parts_incremental(self, parts: list[str], channel: str = "text") -> str:
        """T-20: fuegt neue parts an einen bereits gefuegten praefix an.

        chatglm zerlegt einen einzigen logischen text ueber viele logic_ids
        (live: 166 ids in einem turn). Ein `\n\n` an jeder part-grenze
        zerreiss nicht nur protokoll, sondern JEDE ZEILE — der text wurde
        zu `u\n\ns\n\ne\n\nr`. Ein absatzumbruch wird nur eingesetzt,
        wenn die vorherige part mit einem satzzeichen endet und die
        naechste keinen block-marker traegt; laeuft der text in einer
        offenen struktur, ist es eine fortsetzung.

        Die fruehere fassung baute den string bei JEDEM event komplett neu
        auf und pruefte fuer jede part erneut den gesamten text auf offene
        strukturen: 400 parts ergaben 79.800 vollstaendige scans (1,17 s von
        2,2 s), 1000 parts 20,7 s — quadratisch. Neu wird nur das neue
        fragment betrachtet (O(fragment)), der klammer-/string-zustand
        wird fortgeschrieben."""
        # getrennter zustand je kanal: text und reasoning clobbern sich
        # sonst gegenseitig (beide werden pro render aufgerufen).
        state = self._joined_state.setdefault(channel, ["", 0, 0, False, 0])
        parts = [part for part in parts if part]
        if len(parts) < state[1] or state[4] != self._parts_epoch:
            # eine bereits gefuegte part wurde entfernt/ersetzt: neu bauen
            state[0], state[1], state[2], state[3], state[4] = "", 0, 0, False, self._parts_epoch
        if state[1] == 0 and parts:
            state[0] = parts[0]
            state[2], state[3] = _scan_brackets(parts[0], 0, False)
            state[1] = 1
        for part in parts[state[1] :]:
            if not state[0]:
                state[0] = part
            elif state[2] or state[3]:
                # offene struktur -> das ist eine fortsetzung
                state[0] += part
            elif not part.strip():
                # S-06: gleiche regel wie im streampfad — eine part ohne
                # inhalt bekommt keinen absatzumbruch. Sonst erzeugt eine
                # leere part neben jedem nativen tool_call im cached
                # volltext (und damit in der non-stream-antwort) genau so
                # viele leerzeilen, wie der turn part-grenzen hat.
                state[0] += part
            elif _ends_sentence(state[0][-_EMITTED_TAIL_CHARS:]) or _starts_new_block(part):
                state[0] = f"{state[0]}\n\n{part}"
            else:
                state[0] += part
            state[2], state[3] = _scan_brackets(part, state[2], state[3])
        state[1] = len(parts)
        state[4] = self._parts_epoch
        return state[0]

    def _blocked_only_turn(self) -> bool:
        """War der EINZIGE MAENGEL dieses turns ein gesperrter aufruf?

        Ohne anderen Mangel (kein abgeschnittenes protokoll, keine
        fehlende pflichtauswahl, kein gestarteter ausgabepfad) ist ein
        gesperrter aufruf eine vollstaendige antwort und der turn endet
        regulaer. Sonst bleibt `error` bestehen.
        """
        return bool(self.blocked_tool_attempt_names) and not (
            self.truncated_turn
            or self.required_tool_missing
            or self.output_limit_reached
        )

    def _unusable_calls_are_only_policy(self, collected: list[object], dropped: int) -> bool:
        """Sind die NICHT ausfuehrbaren calls ausschliesslich POLICY-drops?

        Gemessen am agentenlauf 2026-09-26: ein turn, in dem das modell ein
        gesperrtes werkzeug versucht (hier `open`, ein natives GLM-
        werkzeug), endete als `finish_reason: "error"`. Der echte client
        wertete das als stream-fehler und wiederholte den turn mit
        exponentiellem backoff — 5 minuten bis zum naechsten versuch,
        dann wieder, weil `open` erneut aufgerufen wurde. Endlosschleife
        ohne jeden fortschritt.

        Die zwei faelle sind aber grundverschieden:

        * **Policy-drop** — der aufruf war vollstaendig formuliert, nur
          nicht erlaubt. Der turn ist eine vollstaendige antwort ("dieses
          werkzeug gibt es nicht") und endet regulaer mit `stop`.
        * **Unbrauchbar** — der aufruf war erlaubt, scheiterte aber an
          einem fehlenden pflichtargument (T-06) oder ist mitten im json
          abgeschnitten. Dem client fehlt etwas Brauchbares, `error` ist
          richtig und ein Retry ist berechtigt.

        Diese methode beantwortet genau diese Frage und wird an beiden
        abschluss-pfaden (stream und non-stream) benutzt, damit die beide
        nicht auseinanderlaufen.
        """
        if self.allowed_tool_names is None:
            return False
        allowed_lower = {name.lower() for name in self.allowed_tool_names}

        def call_name(call: object) -> str:
            if not isinstance(call, dict):
                return ""
            function = call.get("function")
            if isinstance(function, dict):
                return str(function.get("name", "")).strip()
            return str(call.get("name", "")).strip()

        # ERLAUBTE calls, die trotzdem nicht ausfuehrbar wurden: das ist
        # immer ein echter fehlschlag, unabhaengig vom policy-drop.
        for call in collected:
            name = call_name(call).lower()
            if name and name in allowed_lower:
                return False

        # policy-drops gegen die als "nicht deklariert" erkannten namen
        # herausrechnen — die stehen zu diesem zeitpunkt noch nicht in
        # `blocked_tool_attempt_names` (das wird erst beim abschluss
        # ermittelt), also direkt aus dem aufgebauten text nehmen.
        policy_drops = 0
        for source_text in (self._cached_full_text, self._cached_full_reasoning):
            if not source_text:
                continue
            for name in detect_tool_call_names(source_text):
                if name.lower() not in allowed_lower:
                    policy_drops += 1
        policy_drops = max(policy_drops, self._policy_dropped_call_count)
        return dropped - policy_drops <= 0

    def _render_full_output(self) -> tuple[str, str]:
        if not self._render_cache_dirty:
            return self._cached_full_text, self._cached_full_reasoning

        dirty = self._dirty_logic_ids
        # T-20 (perf): wird eine bestehende part ERNEUT GESENDET, aendert
        # sich die epoch und der inkrementelle aufbau ist ungueltig — dann
        # wird einmal komplett neu gebaut. Das ist der seltene fall; der
        # haeufige (neue part) kostet nur O(1).
        full_rebuild = self._last_render_epoch != self._parts_epoch
        if full_rebuild:
            self._rendered_text_parts = []
            self._rendered_text_chars = 0
            self._rendered_reasoning_parts = []
            self._last_render_epoch = self._parts_epoch
            for logic_id in list(self._cached_part_texts):
                if logic_id not in self.parts_by_logic_id:
                    del self._cached_part_texts[logic_id]
            for logic_id in list(self._cached_part_reasonings):
                if logic_id not in self.parts_by_logic_id:
                    del self._cached_part_reasonings[logic_id]
            candidates = self.ordered_logic_ids
            text_parts = []
            reasoning_parts = []
            self._rendered_text_parts = text_parts
            self._rendered_reasoning_parts = reasoning_parts
        else:
            # nur die tatsaechlich geaenderten parts, in part-reihenfolge
            candidates = sorted(dirty, key=lambda item: self._logic_id_rank.get(item, 0))

        text_parts: list[str] = self._rendered_text_parts
        reasoning_parts: list[str] = self._rendered_reasoning_parts
        for logic_id in candidates:
            if logic_id not in dirty and (
                logic_id in self._cached_part_texts or logic_id in self._cached_part_reasonings
            ):
                # unveraenderte part: den zwischengespeicherten text
                # uebernehmen statt neu aufzubereiten (T-20)
                cached_text = self._cached_part_texts.get(logic_id, "")
                cached_reasoning = self._cached_part_reasonings.get(logic_id, "")
                if cached_text:
                    text_parts.append(cached_text)
                if cached_reasoning:
                    reasoning_parts.append(cached_reasoning)
                continue
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

            # T-20: KEIN `.strip()` pro part. Ein part, der nur aus einem
            # leerzeichen besteht, war dadurch komplett verloren — bei
            # zeichenweiser zustellung ('Die Datei') fehlte der space
            # komplett und ergab 'DieDatei'. Getrimmt wird erst am
            # fertigen ergebnis, wo es nichts mehr zerstoert.
            rendered_text = "\n".join(item for item in part_text if item)
            rendered_reasoning = "\n".join(item for item in part_reasoning if item)
            if rendered_text:
                self._cached_part_texts[logic_id] = rendered_text
            if rendered_reasoning:
                self._cached_part_reasonings[logic_id] = rendered_reasoning
            if rendered_text:
                # T-20 (perf): ist das ausgabebudget bereits erschoepft,
                # wird nichts mehr angehaengt. Ohne diese grenze baute der
                # accumulator bei einem uebergrossen turn den kompletten
                # text auf — 944k zeichen bei 16k parts, davon 880k direkt
                # wieder weggeschnitten. Die zusammenfuehrung ist
                # string-verkettung und damit quadratisch in der
                # gesammellaenge. Der vertrag bleibt unveraendert: was
                # hinter der grenze liegt, wird ohnehin nie ausgeliefert,
                # `finish_reason=length` steht seit F-5a fest.
                # REINER PERFORMANCE-GUARD: er verhindert nur das
                # quadratische anhaengen. Er darf NIE text entfernen, den
                # der stream-pfad noch liefern wuerde.
                #
                # Die fruehere fassung verglich gegen
                # `_output_budget_remaining()` — also gegen
                # `max_output_tokens*4 - _output_chars`, wobei
                # `_output_chars` den bereits GESENDETEN text (und das
                # reasoning) bereits abgezogen hat. Zaehlte man den
                # aufgebauten text noch einmal dagegen, halbierte sich das
                # budget: gemessen 16 629 statt 32 768 zeichen (50,7 %),
                # `finish_reason: length` bei JEDEM turn. Mit
                # `reasoning_effort: max` frisst das reasoning
                # `_output_chars` zusaetzlich, wodurch es noch schlimmer
                # wurde — der agent bekam nahezu gar nichts.
                #
                # Korrekt ist der Vergleich gegen das VOLLE budget: text
                # allein kann nie mehr Zeichen liefern als das ganze
                # budget, also kann dieser guard nichts verlieren, was der
                # stream-pfad sonst ausliefern wuerde. Die ausgabegrenze
                # selbst setzt der stream-pfad (siehe `_output_chars`).
                full_budget = (
                    self.max_output_tokens * _CHARS_PER_TOKEN_ESTIMATE
                    if self.max_output_tokens is not None
                    else None
                )
                # REINER PERFORMANCE-GUARD, und er trigger nur, wenn der
                # STREAM ohnehin schon nichts mehr ausliefert. Dann ist
                # der weitere aufbau umsonst, und der quadratischen
                # anhaengen wird ein ende gesetzt.
                #
                # Die frueheren fassungen schnitten am text selbst ab —
                # einmal gegen das bereits abgezogene budget (50,7 % des
                # lieferkanals, siehe F-5w1), einmal gegen 70 % des
                # budgets. Beides nahm dem client text weg, den der
                # stream-pfad noch ausgeliefert haette. Eine
                # eigenstaendige grenze im aufbau ist hier grundlos
                # falsch: die budget-fuehrung gehoert an EINE stelle,
                # und das ist der stream.
                if self.output_limit_reached:
                    pass  # nichts mehr anhaengen
                elif full_budget is not None and self._rendered_text_chars >= full_budget:
                    # Rueckfallnetz fuer den pfad ohne max_tokens:
                    # text allein kann nie mehr zeichen liefern als das
                    # volle budget.
                    self.output_limit_reached = True
                else:
                    text_parts.append(rendered_text)
                    self._rendered_text_chars += len(rendered_text)
            if rendered_reasoning:
                reasoning_parts.append(rendered_reasoning)

        # T-20 (interleaving): chatglm zerlegt einen logischen text ueber
        # viele logic_ids. Ein `\n\n` zwischen zwei solchen parts zerreisst
        # ein JSON-protokoll, das ueber die part-grenze laeuft — der string
        # bricht mitten im `content` ab, der parser findet keinen call
        # mehr und der rest landet als sichtbarer text (23 leak-faelle im
        # chunk-sweep, vorher). Laeuft ein part mitten in einer
        # angebrochenen protokoll-struktur weiter, wird es deshalb OHNE
        # trenner angehaengt.
        self._last_rendered_dirty = set(dirty)
        self._dirty_logic_ids.clear()
        self._cached_full_text = self._join_parts_incremental(
            text_parts, "text"
        ).strip()
        self._cached_full_reasoning = self._join_parts_incremental(
            reasoning_parts, "reasoning"
        ).strip()
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
