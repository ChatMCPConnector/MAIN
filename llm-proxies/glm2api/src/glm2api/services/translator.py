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
    CODE_FENCE_PATTERN,
    StreamingToolParser,
    _find_unterminated_call_start,
    detect_tool_call_names,
    parse_tool_calls_from_text,
    strip_unparseable_call_fragments,
    text_continues_protocol,
)
from ..utils.tool_protocol import (
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


_META_CHATTER_SENTENCE_RE = re.compile(
    r"(?i)(?:^|(?<=[.!?…])\s)"
    r"(?:\W*)(?:"
    r"i(?:'m| am)\s+(?:so |very )?sorry\b"
    r"|i\s+(?:cannot|can't|can not|am\s+unable\s+to|don't\s+have\s+(?:access|the\s+ability)\s+to|do\s+not\s+have\s+access\s+to)\b"
    r"|as\s+an\s+ai\b"
    r"|es\s+tut\s+mir\s+leid"
    r"|ich\s+kann\s+(?:das\s+)?(?:nicht|leider\s+nicht)\b"
    r"|mir\s+steht\s+(?:das\s+|dieses\s+)?(?:tool|werkzeug)\s+(?:nicht|leider\s+nicht)\s+zur\s+verfügung"
    r")[^.!?\n]*[.!?…]?"
)


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

    # wird erhoeht, wenn eine BEREITS zusammengefuegte part geaendert wird;
    # der inkrementelle aufbau wird dann verworfen und neu gebaut.
    _parts_epoch: int = 0

    _deferred_visible_text: str = ""
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
                                        self.logger.info(
                                            "Dropped native open call: not mappable under the declared tool contract"
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
                    if len(reasoning_delta) > room:
                        reasoning_delta = reasoning_delta[:room]
                        text_delta = ""
                        self.output_limit_reached = True
                    elif len(reasoning_delta) + len(text_delta) > room:
                        text_delta = text_delta[: max(0, room - len(reasoning_delta))]
                        self.output_limit_reached = True
                    self._output_chars += len(reasoning_delta) + len(text_delta)

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
            # T-09/D-03: der midstream-guard pruefte nur auf den
            # `{"tool_calls"`-wrapper. Die NACKTE objektform
            # (`sieh {"name":"bash","arguments":{…`)Contains keinen
            # wrapper und lief dadurch als sichtbarer text heraus
            # (gemessen in 7 von 12 chunk-groessen). Beide opnerformen
            # gehoeren in denselben holdback — der finalize-safety-net
            # entfernt sie anschliessend.
            protocol_fragment = self.allowed_tool_names is not None and (
                '{"tool_calls"' in visible_text_delta
                or "<ml_tool_call" in visible_text_delta
                or "<|DSML|tool_call" in visible_text_delta
                or _BARE_CALL_OPENER_RE.search(visible_text_delta) is not None
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
                        r"als\s+nächstes\s+schau)\b",
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
        # D-05: ein gesperrter nativer call beendet den durchlauf nicht mehr
        # (ein gueltiger call im selben event geht nicht verloren) — er wird
        # aber weiterhin als 'intervene' gemeldet, damit die negative
        # rueckmeldung an das modell geht.
        if blocked_native_seen is not None and blocked_native_seen[0]:
            return chunks, "intervene"
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
        # T-06: das modell WOLLTE einen aufruf, der wegen fehlendem
        # pflichtargument nicht ausfuehrbar ist (`write` ohne content,
        # `read` ohne filePath). Vorher galt der turn danach als leerer
        # ERFOLG — `finish_reason=stop`, `content=None`, und der leer-retry
        # feuerte nicht: der client bekam eine leere, erfolgreiche antwort
        # und blieb stehen.
        collected_raw_calls = list(self.tool_parser.tool_calls) + list(
            self._server_side_tool_calls
        )
        if (collected_raw_calls or self.tool_parser.dropped_call_count) and not all_tool_calls:
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
            if fragment_count:
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
        elif self.blocked_tool_attempt_names or self.truncated_turn or self.required_tool_missing:
            finish_reason = "error" if not all_tool_calls else "tool_calls"
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
        if fragment_count:
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
        if (
            list(self.tool_parser.tool_calls)
            or self._server_side_tool_calls
            or self.tool_parser.dropped_call_count
        ) and not all_tool_calls:
            # T-06: siehe finalize() — ein turn, dessen einziger call
            # unbrauchbar war (fehlendes pflichtargument), ist kein leerer
            # erfolg, sondern ein fehlerhafter turn.
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
                                    or self.blocked_tool_attempt_names
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

        for logic_id in self.ordered_logic_ids:
            rendered_text = self._cached_part_texts.get(logic_id, "")
            rendered_reasoning = self._cached_part_reasonings.get(logic_id, "")

            if rendered_text:
                prev_len = self._part_text_sent.get(logic_id, 0)
                is_new = logic_id not in self._known_logic_ids_for_text
                if is_new:
                    self._known_logic_ids_for_text.append(logic_id)
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
                    if (
                        (text_delta_parts or self._part_text_sent)
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
                is_new = logic_id not in self._known_logic_ids_for_reasoning
                if is_new:
                    self._known_logic_ids_for_reasoning.append(logic_id)
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
            elif _ends_sentence(state[0][-_EMITTED_TAIL_CHARS:]) or _starts_new_block(part):
                state[0] = f"{state[0]}\n\n{part}"
            else:
                state[0] += part
            state[2], state[3] = _scan_brackets(part, state[2], state[3])
        state[1] = len(parts)
        state[4] = self._parts_epoch
        return state[0]

    def _render_full_output(self) -> tuple[str, str]:
        if not self._render_cache_dirty:
            return self._cached_full_text, self._cached_full_reasoning

        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        # T-20: nicht-dirty parts kommen aus dem zwischenspeicher. Das war
        # der quadratische anteil: bei jedem event wurde JEDE part neu
        # aufbereitet und der komplette text neu gebaut.
        dirty = self._dirty_logic_ids
        for logic_id in list(self._cached_part_texts):
            if logic_id not in self.parts_by_logic_id:
                del self._cached_part_texts[logic_id]
        for logic_id in list(self._cached_part_reasonings):
            if logic_id not in self.parts_by_logic_id:
                del self._cached_part_reasonings[logic_id]
        for logic_id in self.ordered_logic_ids:
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
                text_parts.append(rendered_text)
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
