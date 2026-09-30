from __future__ import annotations

import base64
import codecs
import gzip
import http.client
import ipaddress
import json
import mimetypes
import random
import re
import socket
import threading
import time
import uuid
import zlib
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from email.generator import _make_boundary # type: ignore
from io import BufferedReader, BytesIO
from logging import Logger
from typing import Callable, Iterator

from ..config import AppConfig
from ..logging_utils import debug_dump, redact_sensitive_text
from .glm_auth import GLMAccessTokenManager, build_sign
from ..utils.tool_protocol import TOOL_DISCIPLINE_RECAP
from .translator import (
    BLOCKED_NATIVE_TOOL_NAMES,
    GLMEventAccumulator,
    compress_history_messages,
    convert_messages,
    extract_history_tool_call_signatures,
    extract_history_tool_results,
    extract_recent_user_url,
    extract_text_content,
    extract_user_url_context,
    filter_tools,
    is_abandon_claim,
    parse_tool_choice_policy,
    resolve_chat_mode,
    resolve_networking,
    resolve_upstream_model,
)


FILE_UPLOAD_URL_SUFFIX = "/backend-api/assistant/file_upload"
# C-20: fehler-bodies werden begrenzt gelesen — auch nach dekompression.
ERROR_BODY_MAX_BYTES = 256 * 1024
# C-19: cache fuer attachment-uploads innerhalb eines requests
_UPLOAD_CACHE_MAX_ENTRIES = 64
FILE_SIZE_LIMIT = 100 * 1024 * 1024
IMAGE_SIZE_TO_ASPECT_RATIO = {
    "1024x1024": "1:1",
    "1024x1536": "2:3",
    "1536x1024": "3:2",
    "1024x1792": "9:16",
    "1792x1024": "16:9",
}


class UpstreamAPIError(RuntimeError):
    def __init__(self, status_code: int, message: str, payload: dict[str, object] | None = None, transient: bool = False) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}
        self.transient = transient


# C-07: transportfehler, die weder in _raise_for_event_error() noch in der
# queue-logik auftauchen. Ein ConnectionReset/Timeout/gzip-defekt mitten in
# einem tool-call-fragment hat den generator vorher einfach abgebrochen — ohne
# retry, obwohl bis dahin noch NICHTS an den client gegangen war. Genau die
# faelle, die die recovery existiert: der retry setzt den turn neu auf und
# liefert eine vollstaendige antwort statt eines halben protocols.
#   RemoteDisconnected erbt von ConnectionResetError, BadGzipFile von OSError,
#   IncompleteRead von HTTPException.
_TRANSPORT_ERRORS: tuple[type[BaseException], ...] = (
    ConnectionError,
    TimeoutError,
    OSError,
    EOFError,
    http.client.HTTPException,
)


def _mirror_loop_guard_counts(accumulator: object, scope: dict[str, int]) -> None:
    """S-26: den loop-guard-zaehlerstand request-uebergreifend spiegeln.

    Live 2026-09-28 (`ses_f161565c6ffeZp78k7WqoSoF06`): 21x `open` auf denselben
    nicht existierenden pfad, jeder aufruf erneut ausgefuehrt, null drops. Der
    Zaehler lag im Accumulator, der pro Upstream-Runde neu gebaut wird — damit
    sah jede Runde "erster Call dieser Signatur" und `_MAX_IDENTICAL_NATIVE_CALLS`
    (2) griff nie. Der Guard existiert genau fuer diesen Fall.

    Der Stand wird deshalb nach jedem `consume_event` in ein request-scope dict
    zurueckgeschrieben und beim frischen Accumulator wieder hineingespeist.
    """
    counts = getattr(accumulator, "_server_side_signature_counts", None)
    if isinstance(counts, dict):
        scope.update(counts)


def _mirror_drop_counts(accumulator: object, scope: dict[str, int]) -> int:
    """S-27: `loop_guard_dropped_count` request-uebergreifend fuehren.

    Live 2026-09-28 (`ses_f1605c9d0ffeCSJmR08y4q29FK`): 75 `open`-mappings,
    6 drops — und **null** korrekturrunden. `needs_correction` prueft
    `loop_guard_dropped_count`, der im Accumulator lebt; der wird pro
    Upstream-Runde neu gebaut. In der Runde, in der die drops passieren,
    ist der Zaehler am Ende > 0, aber der turn endet und ein frischer
    accumulator startet mit 0. Im log deshalb durchgehend
    `blocked_follow_ups=0` — die korrektur konnte nie feuern, und das
    modell bekam keine einzige notice. Es erfand daraufhin erklaerungen
    (*"the system has repeatedly interrupted me"*, *"MCP-Scrape-Fehler"*),
    die es nicht gab.

    Dieselbe Fehlerklasse wie S-26 (zaehler im accumulator statt
    request-scope), an anderer stelle. Gibt die gesamt-zahl zurueck."""
    # Delta rechnen: der accumulator startet per `_seed_drop_counts` bereits
    # mit dem request-weiten grundstand. Was der mirror zaehlt, ist deshalb nur
    # das, was SEIT DEM LETZTEN MIRROR dazugekommen ist — sonst wird der
    # grundstand je `consume_event` erneut addiert (live regression: 88 drops
    # statt 44, doppelt gezaehlt).
    total = int(getattr(accumulator, "loop_guard_dropped_count", 0) or 0)
    previous = int(scope.get("_last_drop_reading", 0) or 0)
    if total > previous:
        scope["drops"] = int(scope.get("drops", 0) or 0) + (total - previous)
    scope["_last_drop_reading"] = total
    return int(scope.get("drops", 0) or 0)


def _seed_drop_counts(accumulator: object, scope: dict[str, int]) -> None:
    """S-27: request-weiten drop-stand in einen frischen accumulator
    zurueckspielen, damit `needs_correction` ihn sieht."""
    total = int(scope.get("drops", 0) or 0)
    if total:
        setattr(accumulator, "loop_guard_dropped_count", total)
    # Die letzte ablesung ist der grundstand: der accumulator startet ja
    # damit, der mirror darf ihn also nicht erneut addieren.
    scope["_last_drop_reading"] = total


def _seed_loop_guard_counts(accumulator: object, scope: dict[str, int]) -> None:
    """S-26: request-uebergreifenden stand in einen frischen accumulator
    zurueckspielen, damit die wiederholungsgrenze ueber rounds greift."""
    counts = getattr(accumulator, "_server_side_signature_counts", None)
    if isinstance(counts, dict) and scope:
        counts.update(scope)


# S-28: maximale korrektur-runden, wenn das modell in einer werkzeug-schleife
# steckt. Angelehnt an `MAX_BLOCKED_TOOL_FOLLOW_UPS` in der config, aber hier
# als eigener wert, damit die schleife unabhaengig von der `.env` genug
# korrekturen bekommt. Begruendung: die korrektur-runden sind die einzige
# echte faktuelle quelle fuer das modell; ist sie erschoepft, erfindet es
# gruende (live 2026-09-28).
_MAX_CORRECTION_ROUNDS = 5


def _is_transport_error(exc: BaseException) -> bool:
    """True fuer Verbindungsabbruch/Timeout/gzip-Fehler beim Lesen."""
    return isinstance(exc, _TRANSPORT_ERRORS) and not isinstance(exc, QueueTimeoutError)


# S-25: wie lange sichtbarer text zurueckgehalten wird, bevor er als
# „kein abbruch" durchgewinkt wird. 600 zeichen ist laenger als jeder
# realistische abbruch-satz ("…bis das Rundenlimit erreicht war. Schick mir
# bitte eine neue Nachricht." = ~90 zeichen) und kurz genug, dass eine
# laengere passage ohne tool-call nicht unbegrenzt wartet. Ab hier an ist
# ein treffer so unwahrscheinlich, dass das durchlassen guenstiger ist als
# weiteres zurueckhalten.
_ABANDON_HOLD_CHARS = 600


def _extract_nested_url_value(value: object) -> object:
    """C-19: `image_url`/`file_url` kommen als objekt ODER als string."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        nested = value.get("url")
        if isinstance(nested, str):
            return nested
        image_url = value.get("image_url")
        if isinstance(image_url, dict) and isinstance(image_url.get("url"), str):
            return image_url["url"]
    return None


def _transport_error_to_upstream(exc: BaseException) -> UpstreamAPIError:
    return UpstreamAPIError(
        502,
        f"upstream_transport_error: {type(exc).__name__}: {exc}",
        transient=True,
    )


class QueueTimeoutError(RuntimeError):
    pass


@dataclass(slots=True)
class QueueLease:
    ticket: int
    release_callback: Callable[[int], None]
    released: bool = False

    def release(self) -> None:
        if self.released:
            return
        self.released = True
        self.release_callback(self.ticket)


class ConcurrentRequestQueue:
    def __init__(self, logger: Logger, wait_timeout: int, max_concurrency: int) -> None:
        self.logger = logger
        self.wait_timeout = wait_timeout
        self.max_concurrency = max(1, max_concurrency)
        self._condition = threading.Condition()
        self._next_ticket = 0
        self._serving_ticket = 0
        self._released_tickets: set[int] = set()

    def acquire(self, request_name: str) -> QueueLease:
        with self._condition:
            ticket = self._next_ticket
            self._next_ticket += 1
            queue_ahead = max(0, ticket - (self._serving_ticket + self.max_concurrency) + 1)
            start = time.monotonic()

            if queue_ahead > 0:
                self.logger.info("Request entered GLM queue ticket=%s ahead=%s request=%s", ticket, queue_ahead, request_name)

            while ticket >= self._serving_ticket + self.max_concurrency:
                remaining = self.wait_timeout - (time.monotonic() - start)
                if remaining <= 0:
                    # C-01: das timeout-ticket muss als "abandoned"
                    # markiert werden, sonst blockiert es die
                    # serving-sequenz dauerhaft: sobald _serving_ticket
                    # dieses ticket erreicht, gibt es keinen vorgänger,
                    # der es freigibt, und alle folgenden requests
                    # laufen in timeouts.
                    self._abandon_ticket(ticket)
                    raise QueueTimeoutError(
                        f"GLM queue wait timed out, {ticket - (self._serving_ticket + self.max_concurrency) + 1} request(s) still ahead, please retry later."
                    )
                self._condition.wait(timeout=remaining)

            active_slots = ticket - self._serving_ticket + 1
            self.logger.info(
                "Request acquired GLM execution slot ticket=%s active=%s/%s request=%s",
                ticket,
                active_slots,
                self.max_concurrency,
                request_name,
            )
            return QueueLease(ticket=ticket, release_callback=self._release)

    def _abandon_ticket(self, ticket: int) -> None:
        """Timeout-tickets atomar freigeben und die warteschlange
        vorruecken (muss mit self._condition gehalten werden)."""
        self._released_tickets.add(ticket)
        while self._serving_ticket in self._released_tickets:
            self._released_tickets.remove(self._serving_ticket)
            self._serving_ticket += 1
        self.logger.warning(
            "Abandoned timed-out GLM queue ticket=%s; serving window advanced to=%s",
            ticket,
            self._serving_ticket,
        )
        self._condition.notify_all()

    def _release(self, ticket: int) -> None:
        with self._condition:
            self._released_tickets.add(ticket)
            while self._serving_ticket in self._released_tickets:
                self._released_tickets.remove(self._serving_ticket)
                self._serving_ticket += 1
            self.logger.info("Request released GLM execution slot ticket=%s", ticket)
            self._condition.notify_all()


def _estimate_prompt_chars(payload: dict[str, object]) -> int:
    """Grober prompt-groessen-massstab fuer die usage-schaetzung (~4 zeichen/token)."""
    try:
        return len(json.dumps(payload, ensure_ascii=False))
    except (TypeError, ValueError):
        return 0


def _log_history_guards(
    client: "GLMWebClient",
    payload: dict[str, object],
    signatures: set[str],
) -> None:
    """B-01-DIAG: wie viele wiederholungen aus der Historie erkennbar sind?

    Live 2026-10-01 (burst-probe-4, 12x `du -sh`): der client sah 14
    identische `bash`-calls, aber weder der cache-hit (C-01) noch der
    echo-filter griff EIN einziges mal — beide sehen nur
    `extract_history_tool_call_signatures` /
    `extract_history_tool_results`. Ohne diese Zahl ist nicht
    unterscheidbar, ob der client gar keine/tool-call-historie schickt
    (dann muesste opencode-seitig oder in der session etwas aendern) oder
    ob er sie schickt und nur die signaturen nicht matchen (dann ist ein
    normalisierungsfehler im proxy die ursache). Genau diese eine zahl
    trennt die beiden faelle.
    """
    logger = getattr(client, "logger", None)
    if not logger:
        return
    messages = payload.get("messages", [])
    role_counts: dict[str, int] = {}
    if isinstance(messages, list):
        for message in messages:
            if isinstance(message, dict):
                role = str(message.get("role", "?"))
                role_counts[role] = role_counts.get(role, 0) + 1
    results = extract_history_tool_results(list(messages)) if isinstance(messages, list) else {}
    logger.info(
        "B-01-DIAG history_guards messages=%d roles=%s signatures=%d results=%d",
        role_counts and sum(role_counts.values()) or 0,
        sorted(role_counts.items()),
        len(signatures),
        len(results),
    )


def _turn_notice_texts(accumulator: GLMEventAccumulator, blocked: list[str]) -> list[str]:
    """S-22/S-24: die Notices eines Turns in der EINZIGEN gueltigen
    Reihenfolge — remap, blocked, loop. An einer Stelle, damit stream- und
    non-stream-pfad nicht auseinanderlaufen (S-21 musste die reihenfolge
    noch per prepend-erzwingen, S-22 hat das durch eine geordnete liste
    ersetzt, S-24 braucht sie fuer den „content war schon raus"-pfad).

    Die reihenfolge ist die botschaft: "dein `open` lief als `read`, das
    ergebnis ist echt" zuerst, "dieser versuch lief nicht" danach, "du hast
    denselben aufruf wiederholt" zuletzt."""
    notices: list[str] = []
    remap_notice = _native_remap_notice_text(
        getattr(accumulator, "native_remapped_calls", [])
    )
    if remap_notice:
        notices.append(remap_notice)
    if blocked:
        blocked_notice = _blocked_notice_text(blocked)
        if blocked_notice:
            notices.append(blocked_notice)
    # B-01: die burst-meldung kommt an eigene stelle VOR der
    # loop-guard-meldung — sie ist deren eskalation und traegt die
    # handlungsanweisung ("warte auf ein ergebnis"), nicht nur die zaehlung.
    for burst_notice in list(getattr(accumulator, "burst_notices", []) or []):
        if burst_notice and burst_notice not in notices:
            notices.append(burst_notice)
    loop_notice = _loop_guard_notice_text(
        int(getattr(accumulator, "loop_guard_dropped_count", 0) or 0),
        getattr(accumulator, "loop_guard_dropped_tools", []),
    )
    if loop_notice:
        notices.append(loop_notice)
    # C-01: cache-hits zuletzt — sie sind die konkrete antwort auf
    # "warum kam da kein ergebnis": das ergebnis existiert bereits.
    for cached_notice in list(getattr(accumulator, "cached_result_notices", []) or []):
        if cached_notice and cached_notice not in notices:
            notices.append(cached_notice)
    return notices


def _build_blocked_tool_follow_up_payload(
    payload: dict[str, object],
    accumulator: GLMEventAccumulator,
    allowed_tool_names: set[str] | None,
) -> dict[str, object] | None:
    """S-23: die echte Systemrueckmeldung als EIGENE USER-NACHICHT.

    Warum das der einzige Weg ist, der das Modell sicher erreicht:
    eine Notice im SSE-delta (`content` oder `reasoning_content`) ist ein
    Ausgabekanal zum CLIENTEN, kein kontext. Live gemessen am 2026-09-28
    (`build` + `glm-5.3`, README-Vergleich): `opencode run` gibt
    `reasoning_content` nicht als `reasoning`-part aus und schickt es in
    der Folgeanfrage NICHT zurueck — nach S-22 (Notices in den Denkkanal)
    kam beim Modell gar nichts an. Die Folge war die volle Abbruch-
    Pathologie: das Modell rief 13x `open` (11 davon erfolgreich als `read`
    ausgefuehrt), erklaerte dann *"`open` funktioniert nicht fuer lokale
    Pfade"* (falsch), *„bis das Rundenlimit erreicht war"* (erfunden, es
    gab keins) und *„schick mir einfach eine neue Nachricht"* (Aufgaben-
    Abandon) — obwohl `loop_guard_notice` ausdruecklich das Gegenteil
    sagte. Vor S-22 waren die Notices zwar sichtbar (im Fliesstext), aber
    das modell las sie als Teil seiner eigenen narration. Beide Kanaele
    sind damit unzuverlaessig fuer Modell-Rueckmeldung.

    Deshalb: die Notices gehen als `user`-nachricht in die KONVERSATION.
    Das ist derselbe Weg, den diese Funktion schon fuer blockierte Tools
    ging und der nachweislich funktioniert — er erzeugt eine echte
    Kontextnachricht, die der Client nicht verlieren kann, weil er sie nie
    sieht. Sichtbar fuer den Menschen wird sie dadurch nicht, was genau
    der Zweck ist.
    """
    blocked = sorted(set(accumulator.blocked_tool_attempt_names))
    remapped = list(getattr(accumulator, "native_remapped_calls", []) or [])
    dropped = int(getattr(accumulator, "loop_guard_dropped_count", 0) or 0)
    if not (blocked or remapped or dropped):
        return None
    allowed = sorted(allowed_tool_names or [])
    follow_up = dict(payload)
    messages = list(payload.get("messages", [])) # type: ignore[arg-type]
    rendered_text, _ = accumulator.render_full_output()
    assistant_content = rendered_text.strip()

    # Die Reihenfolge ist die beabsichtigte: zuerst "das lief und ist
    # echt", dann "das lief nicht", dann "du hast wiederholt".
    parts: list[str] = []
    remap_notice = _native_remap_notice_text(remapped)
    if remap_notice:
        parts.append(remap_notice)
    if blocked:
        parts.append(
            "The tool(s) "
            + ", ".join(f"`{name}`" for name in blocked)
            + " do NOT exist in this environment and were NOT executed. Do not call them again."
            + (" Available tools: " + ", ".join(f"`{name}`" for name in allowed) + ". Use them instead." if allowed else "")
            + " For filesystem operations (such as inspecting or creating /workspaces), use `bash` or `read`/`write`."
            + " For executing code, running Python, or running tests (pytest), use `bash` (e.g. `python3 ...`). NEVER call `execute_sandbox_code`."
        )
    loop_notice = _loop_guard_notice_text(
        dropped, getattr(accumulator, "loop_guard_dropped_tools", [])
    )
    if loop_notice:
        parts.append(loop_notice)
    correction = "\n\n".join(parts)

    if assistant_content:
        assistant_text = assistant_content
        if blocked:
            assistant_text += "\n\nTool call attempt: " + ", ".join(blocked)
    else:
        assistant_text = (
            "Tool call attempt: " + ", ".join(blocked) if blocked else "Tool call round."
        )
    messages = messages + [
        {
            "role": "assistant",
            "content": assistant_text,
        },
        {
            "role": "user",
            "content": (
                correction
                + " Continue the task now with the available tools."
                " If actual tool outputs are present in the conversation, read them"
                " before concluding anything; blocked attempts above have no result."
                " There is NO tool limit and NO round limit; never report one."
                " If a path does not exist, correct the path or choose a different one —"
                " do not end the task and do not ask for a new message."
                " Do not claim a tool succeeded unless its corresponding tool output is present."
                " Continue only from results actually present in the history."
                " Output ONLY the structured tool call for the next step."
                " Do NOT output any apologies, conversational text, or meta-explanations."
            ),
        },
    ]
    follow_up["messages"] = messages
    return follow_up


def _halve_history_budget(
    payload: dict[str, object],
    history_budget: int,
    retry_exc: Exception,
    logger: Logger,
) -> int:
    """Bei upstream 10040 ("context exceeded"): kompressions-budget halbieren
    und im payload vermerken — der retry schrumpft die historie so lange,
    bis der upstream mitmacht (min 20k)."""
    if "code=10040" not in str(retry_exc):
        return history_budget
    halved = max(20000, history_budget // 2)
    if halved < history_budget:
        payload["_glm_history_budget"] = halved
        logger.info(
            "Upstream 10040 (context exceeded) — halved history budget to %s chars",
            halved,
        )
        return halved
    return history_budget


def _blocked_notice_text(names: object) -> str:
    """S-10: sichtbarer hinweis, dass ein tool-Aufruf ABGELEHNT wurde.

    Das OpenAI-schema hat kein feld fuer abgelehnte aufrufe. Ohne
    signal bleibt der client bei 'alles gelaufen' stehen und beendet
    den tool-loop — oder behauptet gar, das ergebnis gesehen zu haben.
    Der text geht deshalb VOR der inhaltlichen antwort raus.

    S-08: der text sagt AUCH, was jetzt zu tun ist. Live 2026-09-26
    (session `glm2api-Ordner-Analyse`): das modell rief ~30x `open` mit
    `ref_id=turn*search*` auf (eine referenz aus dem EIGENEN web-search
    des modells, fuer uns nicht aufloesbar), bekam nur 'nicht verfuegbar'
    zurueck, erklaerte schliesslich 'mir steht nur das open-tool zur
    verfuegung' und erfand ein tool-limit. Ein reines 'nein' ohne
    ausweg laesst das modell raten; der ausweg muss im text stehen.
    """
    if isinstance(names, str):
        cleaned = [part.strip() for part in names.split(",") if part.strip()]
    elif isinstance(names, (list, tuple, set)):
        cleaned = [str(part).strip() for part in names if str(part).strip()]
    else:
        cleaned = []
    if not cleaned:
        return ""
    return (
        f"[blocked_tool_notice] The tool(s) {', '.join(cleaned)} are not available in "
        "this environment and were NOT executed. Do not claim to have called them "
        "or to have seen any result from them. "
        "A reference like `turn1fetch0`/`turn2search0` is an ID from your OWN web "
        "search and cannot be opened here — the content behind it does not exist "
        "on this machine. Never call these IDs again. "
        "Use instead: `read` with an absolute local path (files and directories "
        "both work), `glob` to find files, `bash` to list or search, and `webfetch` "
        "for an http(s) URL. Re-issue the task with those tools and continue; do not "
        "stop and do not report a tool limit."
    )


def _native_remap_notice_text(remapped: object) -> str:
    """S-21: der native name wurde auf ein echtes Tool umgeschrieben und
    AUSGEFUEHRT — dem Modell den RICHTIGEN namen nennen.

    Live 2026-09-28 (session `ses_f17123666ffeMwmhdXlMz3HO1l`): das modell rief
    ~40x `open`. ~34 davon wurden vom proxy auf `read`/`webfetch` gemappt und
    lieferten ECHTE ergebnisse (der agent las die README). Parallel blockierte
    der proxy 4 `open`-aufrufe mit `ref_id=turn*search*` und meldete per
    `blocked_tool_notice`: "open wurde NICHT ausgefuehrt". Das modell bekam
    damit widerspruechliche rueckmeldung — "open ist tot" neben 15 fertigen
    `read`-ergebnissen — und produzierte die 15x-identische-open-schleife.

    Diese notice schliesst die Luecke: sie sagt dem Modell, dass sein `open`
    stillschweigend als `read`/`webfetch` gelaufen ist und es kuenftig den
    gemappten namen direkt verwenden soll. Ohne sie bleibt das mapping ein
    versteckter rettungsanker, und das modell sucht den fehler am falschen
    werkzeug (`open`) statt das richtige (`read`) zu benutzen.
    """
    if not isinstance(remapped, (list, tuple, set)):
        return ""
    pairs: list[tuple[str, str]] = []
    for item in remapped:
        if not (isinstance(item, (list, tuple)) and len(item) >= 2):
            continue
        native = str(item[0]).strip()
        mapped = str(item[1]).strip()
        if native and mapped and (native, mapped) not in pairs:
            pairs.append((native, mapped))
    if not pairs:
        return ""
    native_to_mapped: dict[str, list[str]] = {}
    for native, mapped in pairs:
        bucket = native_to_mapped.setdefault(native, [])
        if mapped not in bucket:
            bucket.append(mapped)
    sentences = [
        "[native_remap_notice] Correction to the tool name: "
        + "; ".join(
            f"your `{native}` call(s) were transparently executed as "
            + ", ".join(f"`{m}`" for m in mapped_names)
            for native, mapped_names in sorted(native_to_mapped.items())
        )
        + ". Those results are in this conversation and are real — you did see them. "
        f"From now on call "
        + ", ".join(
            f"`{m}`" for mapped_names in native_to_mapped.values() for m in mapped_names
        )
        + " DIRECTLY instead of using the native name. Do not treat the native name as "
        "a working tool and do not keep retrying it: the mapping is a compatibility "
        "shim, not a tool contract, and it fails on targets that are not mappable "
        "(for example a `turn*search*` reference from your own web search)."
    ]
    return "".join(sentences)


def _loop_guard_notice_text(dropped_count: int, tool_names: object) -> str:
    """T-25 (live 2026-09-26): sichtbarer hinweis auf LOOP-GUARD-DROPS.

    Der Guard begrenzt bewusst identische native calls pro Turn (zwei
    erlaubt, der Rest wird verworfen, damit keine Entartung 36 Ausfuehrungen
    erzeugt). Ohne Rueckmeldung sieht das Modell nur weniger Ergebnisse als
    Aufrufe und schliesst auf ein nicht existentes Limit — live gehaessert:
    "Tool-Limit (8/8 Runden) erreicht", Aufgabe abgebrochen, Neustart
    verlangt. Der Text nennt deshalb die WAHRE Begruendung und verbietet die
    Limits-Narrative ausdruecklich."""
    if dropped_count <= 0:
        return ""
    if isinstance(tool_names, (list, tuple, set)):
        cleaned = [str(part).strip() for part in tool_names if str(part).strip()]
    else:
        cleaned = []
    subject = ", ".join(cleaned) if cleaned else "tool"
    return (
        f"[loop_guard_notice] {dropped_count} identical {subject} call(s) in this turn were "
        "dropped by a loop guard — they were NOT executed and there is NO tool limit or "
        "round limit. The identical call already ran; read its result. If it failed, fix the "
        "argument (for example the path) instead of repeating the same call, and never end "
        "the task by claiming a limit was reached."
    )


# C-18: die GLM-Web-Chat-API kennt KEINE sampling-parameter. Ein
# client, der `temperature`/`top_p` sendet, erwartet eine Wirkung, die es
# technisch nicht geben kann. Statt den wunsch zu erfuellen (erfundene
# semantik) oder ihn kommentarlos zu verwerfen (der client glaubt, seine
# einstellung sei aktiv), wird er sichtbar protokolliert. `max_tokens` ist
# die ausnahme: der wird als ausgabebudget erzwungen, weiter unten.
_IGNORED_SAMPLING_PARAMS = ("temperature", "top_p", "top_k", "frequency_penalty", "presence_penalty", "seed")


def _log_unsupported_sampling_params(payload: dict[str, object], logger: object) -> None:
    """Meldet sampling-parameter, die dieser proxy nicht umsetzen kann.

    Bewusst KEIN harter fehler: OpenAI-clients (opencode, aider, ...)
    senden `temperature` standardmaessig mit. Eine ablehnung wuerde jeden
    normalen aufruf brechen, obwohl an der stelle nichts falsch laeuft —
    der parameter hat upstream schlicht keine Entsprechung.
    """
    if not isinstance(payload, dict):
        return
    present = [name for name in _IGNORED_SAMPLING_PARAMS if payload.get(name) is not None]
    if not present:
        return
    log = getattr(logger, "warning", None)
    if callable(log):
        log(
            "Client sent sampling parameter(s) %s that this proxy cannot enforce: "
            "the GLM chat upstream exposes no sampling controls. max_tokens IS enforced "
            "as an output budget.",
            ", ".join(present),
        )


class GLMWebClient:
    def __init__(self, config: AppConfig, logger: Logger) -> None:
        self.config = config
        self.logger = logger
        # V-04: true, wenn der letzte upstream-stream ohne [DONE] endete
        self._last_stream_truncated = False
        self.auth = GLMAccessTokenManager(config=config, logger=logger)
        self.request_queue = ConcurrentRequestQueue(
            logger=logger,
            wait_timeout=config.glm_queue_wait_timeout,
            max_concurrency=config.glm_max_concurrency,
        )
        self._upload_reference_cache: dict[tuple[str, bool], dict[str, object] | None] = {}
        self._persistent_conversation_id: str = getattr(config, "glm_conversation_id", "")
        # C-03: die persistierte conversation war EIN globaler string fuer
        # alle requests. Zwei parallele runden teilten sich dadurch dieselbe
        # upstream-historie (last-writer-wins), und ein kontowechsel
        # erzeugte kontext im falschen account. Deshalb:
        #   * die id ist an das konto gebunden, das sie erzeugt hat,
        #   * ein kontowechsel verwirft sie (kein kontextuebergang),
        #   * eine runde haelt sie fuer ihre dauer exklusiv.
        self._persistent_conversation_account: int | None = None
        self._conversation_lock = threading.Lock()
        # T-30: vorgemerkte Proxy-Rueckmeldungen (remaps/drops/blocked) pro
        # Konversation. Sie werden an das naechste echte Tool-Result
        # angehaengt — der einzige Kanal, den OpenCode dem Modell garantiert
        # zurueckspiegelt (der Denkkanal wird vom Client verworfen, siehe
        # S-22/S-23-Lehre in `_build_blocked_tool_follow_up_payload`).
        self._pending_result_notices: dict[str, str] = {}
        self._pending_result_notice_lock = threading.Lock()
        # Wird nur gehalten, solange eine runde die conversation nutzt.
        self._conversation_use_lock = threading.RLock()

    def get_active_conversation_id(self) -> str:
        with self._conversation_lock:
            return self._persistent_conversation_id

    def set_active_conversation_id(self, conv_id: str, account_index: int | None = None) -> None:
        with self._conversation_lock:
            if self._persistent_conversation_id != conv_id:
                self._persistent_conversation_id = conv_id
                # C-03: die id gehoert zu genau einem konto. Ein wechsel
                # startet mit frischer historie, statt sie in ein anderes
                # konto zu tragen.
                self._persistent_conversation_account = account_index
                self.logger.info(
                    "Persisted active GLM conversation_id: %s (account=%s)",
                    conv_id,
                    account_index,
                )
                conversation_file = getattr(self.config, "glm_conversation_file", None)
                if conversation_file:
                    try:
                        if conv_id:
                            conversation_file.write_text(conv_id, encoding="utf-8")
                        elif conversation_file.exists():
                            conversation_file.unlink(missing_ok=True)
                    except Exception as exc:
                        self.logger.warning("Failed to write GLM conversation_file: %s", exc)

    def conversation_for_account(self, account_index: int) -> str:
        """Conversation-id fuer ein konto; bei kontowechsel wird verworfen."""
        with self._conversation_lock:
            if (
                self._persistent_conversation_id
                and self._persistent_conversation_account is not None
                and self._persistent_conversation_account != account_index
            ):
                self.logger.info(
                    "Dropping persistent GLM conversation on account change %s -> %s",
                    self._persistent_conversation_account,
                    account_index,
                )
                self._persistent_conversation_id = ""
                self._persistent_conversation_account = None
            return self._persistent_conversation_id

    @contextmanager
    def exclusive_conversation(self, account_index: int) -> Iterator[str]:
        """C-03: reserviert die persistierte conversation fuer exakt eine
        runde. Ohne diese exklusion laufen zwei parallele runden in
        derselben upstream-historie und die letzte gewinnt."""
        if not getattr(self.config, "glm_persistent_conversation", False):
            yield ""
            return
        with self._conversation_use_lock:
            yield self.conversation_for_account(account_index)

    def reset_active_conversation(self) -> None:
        self.set_active_conversation_id("")

    def _resolve_tools(self, openai_payload: dict[str, object]) -> tuple[list[dict[str, object]] | None, set[str] | None]:
        raw_tools = list(openai_payload.get("tools", [])) if isinstance(openai_payload.get("tools"), list) else None # type: ignore
        blocked_tool_names = {
            name.strip()
            for name in self.config.blocked_tool_names
            if name.strip()
        } | BLOCKED_NATIVE_TOOL_NAMES
        filtered_tools = filter_tools(raw_tools, blocked_tool_names)
        if raw_tools and len(raw_tools) != len(filtered_tools or []):
            blocked_names: list[str] = []
            for tool in raw_tools:
                fn = tool.get("function", {})
                tool_name = str(fn.get("name", "")).strip()
                if tool_name in blocked_tool_names:
                    blocked_names.append(tool_name)
            if blocked_names:
                self.logger.info("Filtered unsupported tools: %s", ", ".join(blocked_names))
        # C-09: eine leere tool-liste ist NICHT 'keine allowlist'. Vorher
        # lieferte `else None` zurueck, was downstream als Wildcard
        # gelesen wurde — native calls wurden dann ungeprueft gemappt.
        # Leer heisst jetzt: keine tools erlaubt.
        if not filtered_tools:
            return filtered_tools, set()
        return filtered_tools, {tool["function"]["name"] for tool in filtered_tools} # type: ignore[index]

    @staticmethod
    def _extract_tool_choice_and_stop(payload: dict[str, object]) -> tuple[dict[str, object], tuple[str, ...]]:
        """C-18/T-18: die tool-wahl-policy und die stop-sequenzen aus dem
        request holen. Die adapter normalisieren beide auf die interne form
        (`tool_choice` als string/dict, `stop` bzw. `stop_sequences`)."""
        policy = parse_tool_choice_policy(payload.get("tool_choice"))
        stop_sequences: list[str] = []
        for source in (payload.get("stop"), payload.get("stop_sequences")):
            if isinstance(source, str) and source:
                stop_sequences.append(source)
            elif isinstance(source, list):
                stop_sequences.extend(str(item) for item in source if item)
        return policy, tuple(dict.fromkeys(stop_sequences))

    # ------------------------------------------------------------------
    # T-30 (Live-Analyse 2026-09-30): Feedback-Kanal "Tool-Result".
    #
    # Der Denkkanal (`reasoning_content`) ist ein Ausgabekanal zum Clienten:
    # OpenCode gibt ihn nicht als `reasoning`-Part aus und spiegelt ihn in
    # der Folgeanfrage NICHT zurueck — das Modell sieht seine own notices
    # nie (S-22/S-23, 87 Loop-Guard-Drops im Log wirkten fuer das Modell wie
    # "Erfolg ohne Ergebnis"). Ein echtes Tool-Result dagegen kommt als
    # `role: "tool"` zurueck und landet 1:1 im Modellkontext.
    # ------------------------------------------------------------------
    _RESULT_NOTICE_MAX_CHARS = 1800

    def _ensure_notice_store(self) -> tuple[dict[str, str], threading.Lock]:
        """T-30: Lazy-Init des Vormerk-Speichers. Der Client wird in Teilen
        der Testsuite per `__new__` ohne `__init__` gebaut — der Speicher
        darf deshalb nicht nur im Konstruktor existieren."""
        store = getattr(self, "_pending_result_notices", None)
        lock = getattr(self, "_pending_result_notice_lock", None)
        if not isinstance(store, dict):
            store = {}
            self._pending_result_notices = store
        if not isinstance(lock, type(threading.Lock())):
            lock = threading.Lock()
            self._pending_result_notice_lock = lock
        return store, lock

    def _conversation_key(self, payload: dict[str, object]) -> str:
        return str(payload.get("conversation_id", "") or "")

    def _store_pending_result_notice(
        self,
        payload: dict[str, object],
        accumulator: object,
        blocked: list[str],
    ) -> None:
        """T-30: Rueckmeldungen des soeben beendeten Turns vormerken.

        Reihenfolge wie `_turn_notice_texts` (remap -> blocked -> loop) plus
        dem Disziplin-RECAP. Bewusst VOR der Follow-up-Entscheidung aufgerufen:
        die client-seitige Historie enthaelt interne Korrektur-Runden nie, die
        Ankerung stellt deshalb sicher, dass die Rueckmeldung trotzdem ankommt.
        """
        notices = _turn_notice_texts(accumulator, list(blocked or []))
        if not notices:
            return
        self._append_pending_result_notice_text(payload, " \n".join(notices))

    def _append_pending_result_notice_text(self, payload: dict[str, object], text: str) -> None:
        """T-30: Rohtext an die vorgemerkte Rueckmeldung derselben Konversation
        anhaengen. Der Disziplin-RECAP wird erst beim Anker ergaenzt (genau
        einmal), damit Mehrex-Legungen ihn nicht vervielfaeltigen."""
        if not text:
            return
        store, lock = self._ensure_notice_store()
        key = self._conversation_key(payload)
        with lock:
            existing = store.get(key, "")
            combined = f"{existing}\n{text}" if existing else text
            store[key] = combined

    def _take_pending_result_notice(self, payload: dict[str, object]) -> str:
        """T-30: vorgemerkte Rueckmeldung abholen (und verbrauchen)."""
        store, lock = self._ensure_notice_store()
        key = self._conversation_key(payload)
        with lock:
            return store.pop(key, "")

    def _anchor_pending_result_notice(self, payload: dict[str, object]) -> None:
        """T-30: vorgemerkte Rueckmeldung an das LETZTE Tool-Result der
        Request-Historieanhaengen — genau das sieht das Modell beim
        naechsten Denkschritt zuerst.

        Sonderfall: liefert der Client KEIN Tool-Result (erste Runde oder
        Textantwort), wird die Rueckmeldung als eigene Tool-Nachricht mit
        dem Namen `system` angehaengt — der Upstream-Transkript-Serializer
        rendert sie als Werkzeugprotokoll-Block, den das Modell als
        Systemrueckmeldung liest (kein erfundener Call, keine Echo-Gefahr:
        die Call-ID `system-notice` existiert in keiner Historie).
        """
        notice = self._take_pending_result_notice(payload)
        if not notice:
            return
        # T-30: der RECAP kommt genau hier dazu — naehe zum Aktionszeitpunkt.
        if len(notice) > self._RESULT_NOTICE_MAX_CHARS:
            notice = notice[: self._RESULT_NOTICE_MAX_CHARS - 20] + " …[truncated]"
        notice = f"{notice}\n\n{TOOL_DISCIPLINE_RECAP}"
        messages = payload.get("messages")
        if not isinstance(messages, list):
            return
        target_index: int | None = None
        for index in range(len(messages) - 1, -1, -1):
            if str(messages[index].get("role", "")) == "tool":
                target_index = index
                break
        anchored = False
        if target_index is not None:
            message = messages[target_index]
            existing = message.get("content")
            existing_text = extract_text_content(existing) if existing else ""
            message["content"] = f"{notice}\n\n---\n{existing_text}".strip()
            anchored = True
        if not anchored:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": "system-notice",
                    "name": "system",
                    "content": notice,
                }
            )
        self.logger.warning(
            "T-30: pending proxy feedback anchored to %s of the next request "
            "(tool-result channel reaches the model; reasoning deltas do not)",
            f"tool result #{target_index}" if anchored else "a synthetic system tool message",
        )

    def chat_completion(self, payload: dict[str, object]) -> tuple[dict[str, object], str | None]:
        payload = dict(payload)  # lokal kopierbar fuer retry-mutationen (10040-budget)
        # T-30: Holder fuer die jeweils aktive Runde. Im Stream-Pfad lebt
        # `active_payload` generator-lokal und ist fuer die Fabrik-Closure
        # nicht sichtbar — der Holder transportiert die aktive Runde hinein.
        _active_round_payload_holder: list = []
        filtered_tools, allowed_tool_names = self._resolve_tools(payload)
        tool_choice_policy, stop_sequences = self._extract_tool_choice_and_stop(payload)
        max_stream_retries = self.config.glm_stream_error_max_retries
        # S-28: das korrektur-budget waechst mit der schleife. Live
        # `ses_f15e98754ffe8E5GoHP4rWsBs6`: 12 mappings, budget 2 — nach der
        # zweiten korrektur war die faktuelle quelle erschoepft, und das
        # modell erfand die einzig noch moegliche erklaerung: *"weitere
        # tool-aufrufe sind laut system nicht mehr moeglich"*. Das ist keine
        # modell-eigenheit, sondern eine folge des budgets: die korrektur
        # RUNDE sind die einzigen echten fakten, die das modell bekommt, und
        # nach `max` davon hat es keine mehr und ratet.
        #
        # Deshalb: sobald drops/remaps vorliegen, gilt das Maximum des Codes
        # (5), unabhaengig von der konfiguration. Der konfigurationswert
        # bleibt die basis fuer den normalfall (blocked-only).
        _configured_follow_ups = self.config.glm_blocked_tool_follow_ups
        max_blocked_follow_ups = _configured_follow_ups
        max_empty_response_retries = self.config.glm_empty_response_max_retries
        empty_retries = 0
        history_budget = self.config.glm_history_max_chars
        prompt_chars = _estimate_prompt_chars(payload)
        history_tool_call_signatures = extract_history_tool_call_signatures(
            list(payload.get("messages", [])) # type: ignore[arg-type]
        )
        _log_history_guards(self, payload, history_tool_call_signatures)
        lease = self.request_queue.acquire(f"chat:{payload.get('model', 'unknown')}")
        # S-14: gesamt-deadline fuer diesen request. Die einzelnen
        # retry-zaehler sind begrenzt, ihre summe nicht — ohne deadline
        # konnte ein request mit vielen transienten runden einen slot
        # minutenlang belegen und die queue aufhalten.
        deadline = self._request_deadline()
        account_index = self._get_preferred_account_index(lease.ticket)
        # C-03: die persistierte conversation gehoert fuer die dauer dieser
        # runde exklusiv zu dieser runde — sonst teilen sich parallele
        # runden dieselbe upstream-historie.
        conversation_slot = self.exclusive_conversation(
            account_index if account_index is not None else 0
        )
        conversation_slot.__enter__()
        try:
            response, assistant_id = self._open_chat_stream(payload, preferred_account_index=account_index, filtered_tools=filtered_tools)
        except Exception:
            conversation_slot.__exit__(None, None, None)
            lease.release()
            raise

        # Ausgabegrenze: der client-wunsch gilt, aber nie ueber die
        # konfigurationsschranke hinaus (der upstream kann sie nicht
        # durchsetzen, der proxy muss es selbst tun).
        _log_unsupported_sampling_params(payload, self.logger)
        client_max = payload.get("max_tokens")
        if not isinstance(client_max, int) or client_max <= 0:
            client_max = payload.get("max_completion_tokens")
        if isinstance(client_max, int) and client_max > 0:
            effective_max_tokens = min(client_max, self.config.glm_max_output_tokens)
        else:
            effective_max_tokens = self.config.glm_max_output_tokens

        def new_accumulator() -> GLMEventAccumulator:
            accumulator_obj = GLMEventAccumulator(
                model=str(payload["model"]),
                allowed_tool_names=allowed_tool_names,
                fallback_tool_url=extract_recent_user_url(list(payload.get("messages", []))), # type: ignore[arg-type]
                # D-02: die vom nutzer selbst genannten URLs — damit der
                # `open`-mapper erfundene platzhalter-ziele erkennt.
                user_url_context=extract_user_url_context(list(payload.get("messages", []))), # type: ignore[arg-type]
                # C-01: bereits gelieferte ergebnisse der request-historie —
                # macht wiederholte calls zu cache-hits.
                history_tool_results=extract_history_tool_results(list(payload.get("messages", []))), # type: ignore[arg-type]
                debug_enabled=self.config.debug_dump_all,
                logger=self.logger,
                history_tool_call_signatures=history_tool_call_signatures,
                prompt_chars=prompt_chars,
                max_output_tokens=effective_max_tokens,
                # T-18/C-18: policy und stop werden durchgesetzt, nicht nur
                # in den prompt geschrieben.
                tool_choice_mode=str(tool_choice_policy.get("mode", "auto")),
                tool_choice_name=(
                    str(tool_choice_policy.get("tool_name"))
                    if tool_choice_policy.get("tool_name")
                    else None
                ),
                stop_sequences=stop_sequences,
            )
            # T-30: Eskalations-Notices (prepend_blocked_notice) zusaetzlich
            # in den Tool-Result-Kanal vormerken. Der Holder wird auf die
            # jeweils aktive Runde gesetzt; bis dahin gilt das Ausgangs-Payload.
            accumulator_obj._pending_result_notice_sink = ( # type: ignore[union-attr]
                lambda notice_text: self._append_pending_result_notice_text(
                    _active_round_payload_holder[0] or payload, notice_text
                )
            )
            return accumulator_obj

        # C-15: bei transient-retry, leer-retry und follow-up wird ein neuer
        # accumulator erzeugt. Die bis dahin erhaltene conversation_id
        # wurde dabei verworfen — ohne delete_conversation blieb sie beim
        # upstream liegen (pro versuch eine conversation). Alle im lauf
        # gesammelten ids werden im finally abgeraeumt.
        # C-15: conversation_id -> ERZEUGERKONTO. Ohne das konto konnte
        # der aufraeumpfad die falsche conversation loeschen.
        created_conversations: dict[str, int] = {}
        # S-26: loop-guard-zaehler request-uebergreifend (siehe
        # `_mirror_loop_guard_counts`). Ohne das sah jede Upstream-Runde "erster
        # Call dieser Signatur" und die Wiederholungsgrenze griff nie — live
        # belegt in `ses_f161565c6ffeZp78k7WqoSoF06` (21x `open` auf denselben
        # nicht existierenden pfad, null drops, das modell erfand ein "the
        # system has repeatedly interrupted me", das es nicht gab).
        request_scope_signatures: dict[str, int] = {}  # S-27: 'drops' -> int
        # C-15: das konto, mit dem die AKTUELLE runde laeuft. Die
        # conversation gehoert diesem konto, nicht irgendeinem.
        _conversation_account_index = account_index
        accumulator = new_accumulator()
        # S-26: request-uebergreifenden loop-guard-stand einspielen.
        # S-27: drop-zaehler request-uebergreifend (siehe `_mirror_drop_counts`).
        _seed_drop_counts(accumulator, request_scope_signatures)
        _seed_loop_guard_counts(accumulator, request_scope_signatures)
        # C-12: retries der non-stream-runde verwenden das payload der
        # aktuellen runde; nach einer follow-up-runde ist das deren payload
        # mit der negativen tool-rueckmeldung.
        active_payload = payload
        _active_round_payload_holder.clear()
        _active_round_payload_holder.append(active_payload)
        # T-30: vorgemerkte Rueckmeldung ins letzte Tool-Result anhaengen
        # (siehe Stream-Pfad).
        self._anchor_pending_result_notice(active_payload)

        # S-26 (live 2026-09-28): der loop-guard-Zaehler muss request-
        # uebergreifend leben. Er lag im Accumulator, der pro Upstream-Runde
        # neu gebaut wird — damit sah JEDE Runde "erster Call dieser
        # Signatur" und die Grenze `_MAX_IDENTICAL_NATIVE_CALLS = 2` griff
        # nie. Live belegt: die session `ses_f161565c6ffeZp78k7WqoSoF06`
        # rief 21x `open` auf denselben nicht existierenden pfad
        # (/workspaces/gibtsnicht/README.md), jeder aufruf wurde erneut
        # ausgefuehrt (30x `Mapped native open` im log, null drops), und das
        # modell kam nie heraus: es erfand eine "the system has repeatedly
        # interrupted me"-erklaerung, die es nicht gab. Der guard ist genau
        # dafuer da, und er hat in diesem pfad nie ausgeloest.
        # (Deklaration weiter oben bei `created_conversations`.)

        try:
            attempt = 0
            blocked_follow_ups = 0
            while True:
                retry_exc: UpstreamAPIError | None = None
                finished = False
                self._last_stream_truncated = False
                # C-07: ein verbindungsabbruch mitten im stream (reset,
                # timeout, gzip-defekt) brach den generator vorher hart ab —
                # ohne retry, obwohl noch nichts ausgeliefert war. Solche
                # fehler sind transient und gehoeren in dieselbe
                # zustandsmaschine wie ein 10040-event.
                try:
                    for event in self._iter_sse_events(response):
                        if not event:
                            continue
                        status = event.get("status")
                        try:
                            self._raise_for_event_error(event, stream=False)
                        except UpstreamAPIError as exc:
                            if exc.transient and attempt < max_stream_retries and not self._deadline_exceeded(deadline):
                                retry_exc = exc
                                break
                            raise
                        accumulator.consume_event(event)
                        _mirror_loop_guard_counts(accumulator, request_scope_signatures)
                        _mirror_drop_counts(accumulator, request_scope_signatures)
                        if status in {"finish", "intervene"}:
                            finished = True
                            break
                except UpstreamAPIError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    if not _is_transport_error(exc):
                        raise
                    upstream_exc = _transport_error_to_upstream(exc)
                    if attempt >= max_stream_retries:
                        # Auch der letzte versuch meldet den vertrag:
                        # ein UpstreamAPIError mit transient=True, damit die
                        # server-schicht daraus ein 502 mit retrybarem code
                        # macht — nicht ein roher ConnectionResetError.
                        raise upstream_exc from exc
                    retry_exc = upstream_exc
                    self.logger.warning(
                        "Upstream transport error mid-stream (%s: %s); retrying attempt=%s/%s",
                        type(exc).__name__,
                        exc,
                        attempt + 1,
                        max_stream_retries,
                    )
                if self._last_stream_truncated and not finished:
                    # V-04: stream endete ohne finish/[DONE]. Als transiente
                    # Unterbrechung behandeln und mit frischer Conversation
                    # erneut versuchen — sonst gaenge ein abgeschnittener
                    # tool-call als vollstaendige antwort an den client.
                    # C-06: diese verzweigung hatte KEIN retries-limit. Der
                    # transient-event-zweig prueft `attempt <
                    # max_stream_retries`, dieser nicht — gemessen 17.993
                    # upstream-versuche in 3 s trotz `max_stream_retries=1`.
                    # Folge: ~1,8 mio requests und ebensoviele
                    # upstream-conversations bei der standard-deadline, alle
                    # unter gehaltener lease.
                    if attempt >= max_stream_retries:
                        self.logger.warning(
                            "Upstream stream truncated before finish and retry budget exhausted "
                            "(attempt=%s/%s) — failing as transient",
                            attempt + 1,
                            max_stream_retries,
                        )
                        raise UpstreamAPIError(
                            502,
                            "truncated_stream: upstream ended without [DONE]",
                            transient=True,
                        )
                    retry_exc = UpstreamAPIError(
                        502,
                        "truncated_stream: upstream ended without [DONE]",
                        transient=True,
                    )
                    self.logger.warning(
                        "Upstream stream truncated before finish; retrying attempt=%s/%s",
                        attempt + 1,
                        max_stream_retries,
                    )
                if finished:
                    # build_response() also populates blocked_tool_attempt_names
                    # (detect_tool_call_names side effect) — call before deciding.
                    result = accumulator.build_response()
                    # Leer-Turn-Autonomie-Fix: der
                    # Upstream liefert gelegentlich KOMPLETT leere runden
                    # (text_len=0, keine calls) — bisher blieb der agent dort
                    # einfach stehen. Solche runden sind transient: retry mit
                    # frischer conversation, BEVOR die leere antwort rausgeht.
                    if (
                        accumulator.is_empty_response()
                        and empty_retries < max_empty_response_retries
                    ):
                        empty_retries += 1
                        response.close() # type: ignore
                        self.logger.warning(
                            "Empty GLM response (no text/reasoning/calls) — auto-retrying round %s/%s",
                            empty_retries,
                            max_empty_response_retries,
                        )
                        time.sleep(self.config.glm_stream_error_retry_interval)
                        if accumulator.conversation_id:
                            created_conversations.setdefault(accumulator.conversation_id, _conversation_account_index)
                        accumulator = new_accumulator()
                        # S-26: request-uebergreifenden loop-guard-stand uebernehmen.
                        # S-27: drop-zaehler request-uebergreifend (siehe `_mirror_drop_counts`).
                        _seed_drop_counts(accumulator, request_scope_signatures)
                        _seed_loop_guard_counts(accumulator, request_scope_signatures)
                        _conversation_account_index = self._get_preferred_account_index(lease.ticket)
                        response, assistant_id = self._open_chat_stream(active_payload, preferred_account_index=_conversation_account_index, filtered_tools=filtered_tools)
                        continue
                    has_valid_calls = False
                    choices_obj = result.get("choices")
                    if isinstance(choices_obj, list) and choices_obj and isinstance(choices_obj[0], dict):
                        message_obj = choices_obj[0].get("message")
                        if isinstance(message_obj, dict):
                            has_valid_calls = bool(message_obj.get("tool_calls"))
                    # T-30: Rueckmeldung fuer das naechste Tool-Result
                    # vormerken (siehe Stream-Pfad).
                    self._store_pending_result_notice(
                        active_payload,
                        accumulator,
                        list(accumulator.blocked_tool_attempt_names),
                    )
                    # S-23: wie im stream-pfad — die Folge-runde feuert bei
                    # JEDER rueckmeldung, die das modell sehen muss, nicht nur
                    # bei blockierten tools. Begruendung siehe
                    # `_build_blocked_tool_follow_up_payload`.
                    needs_correction = bool(
                        accumulator.blocked_tool_attempt_names
                        or getattr(accumulator, "native_remapped_calls", [])
                        # S-27: der drop-stand muss request-uebergreifend sein — im
                        # accumulator sieht die naechste runde wieder 0.
                        or int(request_scope_signatures.get("drops", 0) or 0) > 0
                    )
                    if (
                        needs_correction
                        and not has_valid_calls
                        and blocked_follow_ups < max_blocked_follow_ups
                    ):
                        # Never run an internal correction while valid tool
                        # calls are waiting for OpenCode to execute them. The
                        # client only sends their results in its NEXT request;
                        # an internal GLM round here would falsely tell the
                        # model that results are already available.
                        # Negative tool-result round instead of silently
                        # dropping blocked tool calls (see stream path).
                        # V-02: nur wenn der Turn KEINE gueltigen Calls
                        # enthaelt — sonst wuerde das Ergebnis verwerfen.
                        blocked_follow_ups += 1
                        follow_up = _build_blocked_tool_follow_up_payload(active_payload, accumulator, allowed_tool_names)
                        if follow_up is None:
                            return result, accumulator.conversation_id
                        self.logger.warning(
                            "Model attempted blocked tool(s) %s; starting negative-result follow-up round %s/%s",
                            ", ".join(sorted(set(accumulator.blocked_tool_attempt_names))),
                            blocked_follow_ups,
                            max_blocked_follow_ups,
                        )
                        response.close() # type: ignore
                        if accumulator.conversation_id:
                            created_conversations.setdefault(accumulator.conversation_id, _conversation_account_index)
                        accumulator = new_accumulator()
                        # S-26: request-uebergreifenden loop-guard-stand uebernehmen.
                        # S-27: drop-zaehler request-uebergreifend (siehe `_mirror_drop_counts`).
                        _seed_drop_counts(accumulator, request_scope_signatures)
                        _seed_loop_guard_counts(accumulator, request_scope_signatures)
                        response, assistant_id = self._open_chat_stream(follow_up, preferred_account_index=self._get_preferred_account_index(lease.ticket), filtered_tools=filtered_tools)
                        # C-12: follow-up-runde wird zur aktiven runde
                        active_payload = follow_up
                        _active_round_payload_holder.clear()
                        _active_round_payload_holder.append(active_payload)
                        # T-30: siehe Stream-Pfad — keine Ankerung noetig, die
                        # Korrektur-Nachricht enthaelt die Rueckmeldungen.
                        continue
                    # S-22: ALLE notices eines turns an EINER stelle, in
                    # fester reihenfolge, im DENKKANAL statt im sichtbaren
                    # text. Siehe die ausfuehrliche begruendung im
                    # stream-pfad. Reihenfolge: remap -> blocked -> loop.
                    # T-30: zusaetzlich fuer das naechste Tool-Result vormerken.
                    self._store_pending_result_notice(active_payload, accumulator, [])
                    self._inject_turn_notices(result, accumulator)
                    return result, accumulator.conversation_id
                if retry_exc is None:
                    break
                # Transient upstream error: retry the stream with a fresh
                # conversation before giving up. Bei 10040 ("context exceeded")
                # das kompressions-budget halbieren (siehe stream-pfad).
                attempt += 1
                response.close() # type: ignore
                self.logger.warning(
                    "Transient GLM error in non-streaming chat, retrying attempt=%s/%s error=%s",
                    attempt,
                    max_stream_retries,
                    retry_exc,
                )
                if retry_exc is not None:
                    if self._deadline_exceeded(deadline):
                        self.logger.warning(
                            "Request deadline exceeded before another retry (attempt=%s) — giving up",
                            attempt + 1,
                        )
                        raise retry_exc
                    history_budget = _halve_history_budget(active_payload, history_budget, retry_exc, self.logger)
                time.sleep(self.config.glm_stream_error_retry_interval)
                if accumulator.conversation_id:
                    created_conversations.setdefault(accumulator.conversation_id, _conversation_account_index)
                accumulator = new_accumulator()
                # S-26: request-uebergreifenden loop-guard-stand uebernehmen.
                # S-27: drop-zaehler request-uebergreifend (siehe `_mirror_drop_counts`).
                _seed_drop_counts(accumulator, request_scope_signatures)
                _seed_loop_guard_counts(accumulator, request_scope_signatures)
                _conversation_account_index = self._get_preferred_account_index(lease.ticket)
                response, assistant_id = self._open_chat_stream(active_payload, preferred_account_index=_conversation_account_index, filtered_tools=filtered_tools)
        finally:
            response.close() # type: ignore
            if getattr(self.config, "glm_persistent_conversation", False) and accumulator.conversation_id:
                self.set_active_conversation_id(accumulator.conversation_id, account_index)
            if accumulator.conversation_id:
                created_conversations.setdefault(accumulator.conversation_id, _conversation_account_index)
            for conversation_id, owner_account in sorted(created_conversations.items()):
                self.delete_conversation(
                    conversation_id,
                    assistant_id=assistant_id,
                    account_index=owner_account,
                )
            conversation_slot.__exit__(None, None, None)
            lease.release()
        # T-25/S-22: der pfad fuer einen turn OHNE terminalen upstream-status
        # (abgeschnitten, kein `finish`) hatte die notice vorher nicht —
        # obwohl er der fall ist, in dem dem modell die erklaerung am
        # meisten fehlt: es hat calls gesendet und keine ergebnisse
        # gesehen. Also auch hier. S-22: alle notices, im denkkanal.
        # T-30: auch der letzte Turn einer Non-Streaming-Runde merkt seine
        # Rueckmeldung fuer den naechsten Client-Request vor.
        self._store_pending_result_notice(active_payload, accumulator, [])
        final_result = accumulator.build_response()
        self._inject_turn_notices(final_result, accumulator)
        return final_result, accumulator.conversation_id

    def _inject_turn_notices(self, result: dict[str, object], accumulator: object) -> None:
        """S-22: alle turn-notices an EINER stelle, in fester reihenfolge,
        in den DENKKANAL (`reasoning_content`) statt in `content`.

        Live 2026-09-28 (Session `build` + `glm-5.3`, Ordnervergleich): die
        notices standen per `content`-injektion mitten im sichtbaren text der
        antwort — der client zeigte "Abbruch ehrlich gem ...
        [loop_guard_notice] 8 identical open call(s) ... [blocked_tool_notice]
        The tool(s) open ..." als EINE normale antwort, und das modell
        erkannte die notices nicht als systemrueckmeldung. Sie landen jetzt in
        `reasoning_content`: fuer das modell sichtbar, fuer den client vom
        antworttext getrennt.

        Reihenfolge remap -> blocked -> loop ist die beabsichtigte und
        deshalb explizit: "dein `open` lief als `read`, ergebnis ist echt"
        zuerst, "dieser versuch lief nicht" danach, "du hast denselben
        aufruf wiederholt" zuletzt."""
        remap_notice = _native_remap_notice_text(
            getattr(accumulator, "native_remapped_calls", [])
        )
        blocked_names = sorted(
            set(getattr(accumulator, "blocked_tool_attempt_names", []) or [])
        )
        has_valid_calls = False
        choices = result.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            message = choices[0].get("message")
            has_valid_calls = bool(isinstance(message, dict) and message.get("tool_calls"))
        notices: list[str] = []
        if remap_notice:
            self.logger.warning(
                "Turn remapped native tool call(s) and executed them; telling the model the real tool name",
            )
            notices.append(remap_notice)
        # V-02/S-10/C-11: gemischter Turn. Die gueltigen calls werden
        # ausgeliefert, aber der abgelehnte aufruf muss fuer das modell
        # sichtbar bleiben — sonst wiederholt es ihn.
        if blocked_names and has_valid_calls:
            self.logger.warning(
                "Turn contained valid and blocked tool calls; delivering valid calls, blocked=%s",
                ", ".join(blocked_names),
            )
            blocked_notice = _blocked_notice_text(blocked_names)
            if blocked_notice:
                notices.append(blocked_notice)
        # T-25: der loop guard ist ebenfalls ein abgelehnter aufruf.
        dropped = int(getattr(accumulator, "loop_guard_dropped_count", 0) or 0)
        if dropped > 0:
            loop_notice = _loop_guard_notice_text(
                dropped, getattr(accumulator, "loop_guard_dropped_tools", [])
            )
            if loop_notice:
                self.logger.warning(
                    "Turn dropped %s identical native call(s) via the loop guard; telling the model the real reason",
                    dropped,
                )
                notices.append(loop_notice)
        if not notices:
            return
        if not isinstance(choices, list) or not choices:
            return
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if not isinstance(message, dict):
            return
        block = "\n".join(notices)
        existing_reasoning = str(message.get("reasoning_content") or "")
        message["reasoning_content"] = (
            f"{block}\n{existing_reasoning}" if existing_reasoning else block
        )

    def generate_images(self, payload: dict[str, object]) -> dict[str, object]:
        lease = self.request_queue.acquire(f"image:{payload.get('model', self.config.glm_image_model_name)}")
        try:
            response, assistant_id = self._open_image_stream(payload, preferred_account_index=self._get_preferred_account_index(lease.ticket))
        except Exception:
            lease.release()
            raise

        accumulator = GLMEventAccumulator(
            model=str(payload.get("model", self.config.glm_image_model_name)),
            debug_enabled=self.config.debug_dump_all,
            logger=self.logger,
        )
        try:
            for event in self._iter_sse_events(response):
                if not event:
                    continue
                status = event.get("status")
                accumulator.consume_event(event)
                if status == "finish":
                    return self._build_images_response(payload, event, accumulator)

            return self._build_images_response(payload, {}, accumulator)
        finally:
            response.close() # type: ignore
            self.delete_conversation(accumulator.conversation_id, assistant_id=assistant_id)
            lease.release()

    def stream_chat_completion(self, payload: dict[str, object]):
        payload = dict(payload)  # lokal kopierbar fuer retry-mutationen (10040-budget)
        # T-30: Holder fuer die jeweils aktive Runde. Im Stream-Pfad lebt
        # `active_payload` generator-lokal und ist fuer die Fabrik-Closure
        # nicht sichtbar — der Holder transportiert die aktive Runde hinein.
        _active_round_payload_holder: list = []
        filtered_tools, allowed_tool_names = self._resolve_tools(payload)
        tool_choice_policy, stop_sequences = self._extract_tool_choice_and_stop(payload)
        max_stream_retries = self.config.glm_stream_error_max_retries
        # S-28: das korrektur-budget waechst mit der schleife. Live
        # `ses_f15e98754ffe8E5GoHP4rWsBs6`: 12 mappings, budget 2 — nach der
        # zweiten korrektur war die faktuelle quelle erschoepft, und das
        # modell erfand die einzig noch moegliche erklaerung: *"weitere
        # tool-aufrufe sind laut system nicht mehr moeglich"*. Das ist keine
        # modell-eigenheit, sondern eine folge des budgets: die korrektur
        # RUNDE sind die einzigen echten fakten, die das modell bekommt, und
        # nach `max` davon hat es keine mehr und ratet.
        #
        # Deshalb: sobald drops/remaps vorliegen, gilt das Maximum des Codes
        # (5), unabhaengig von der konfiguration. Der konfigurationswert
        # bleibt die basis fuer den normalfall (blocked-only).
        _configured_follow_ups = self.config.glm_blocked_tool_follow_ups
        max_blocked_follow_ups = _configured_follow_ups
        max_empty_response_retries = self.config.glm_empty_response_max_retries
        empty_retries = 0
        history_tool_call_signatures = extract_history_tool_call_signatures(
            list(payload.get("messages", [])) # type: ignore[arg-type]
        )
        _log_history_guards(self, payload, history_tool_call_signatures)
        history_budget = self.config.glm_history_max_chars
        prompt_chars = _estimate_prompt_chars(payload)

        # Ausgabegrenze: der client-wunsch gilt, aber nie ueber die
        # konfigurationsschranke hinaus (der upstream kann sie nicht
        # durchsetzen, der proxy muss es selbst tun).
        _log_unsupported_sampling_params(payload, self.logger)
        client_max = payload.get("max_tokens")
        if not isinstance(client_max, int) or client_max <= 0:
            client_max = payload.get("max_completion_tokens")
        if isinstance(client_max, int) and client_max > 0:
            effective_max_tokens = min(client_max, self.config.glm_max_output_tokens)
        else:
            effective_max_tokens = self.config.glm_max_output_tokens

        def new_accumulator() -> GLMEventAccumulator:
            accumulator_obj = GLMEventAccumulator(
                model=str(payload["model"]),
                allowed_tool_names=allowed_tool_names,
                fallback_tool_url=extract_recent_user_url(list(payload.get("messages", []))), # type: ignore[arg-type]
                # D-02: die vom nutzer selbst genannten URLs — damit der
                # `open`-mapper erfundene platzhalter-ziele erkennt.
                user_url_context=extract_user_url_context(list(payload.get("messages", []))), # type: ignore[arg-type]
                # C-01: bereits gelieferte ergebnisse der request-historie —
                # macht wiederholte calls zu cache-hits.
                history_tool_results=extract_history_tool_results(list(payload.get("messages", []))), # type: ignore[arg-type]
                debug_enabled=self.config.debug_dump_all,
                logger=self.logger,
                history_tool_call_signatures=history_tool_call_signatures,
                prompt_chars=prompt_chars,
                max_output_tokens=effective_max_tokens,
                # T-18/C-18: policy und stop werden durchgesetzt, nicht nur
                # in den prompt geschrieben.
                tool_choice_mode=str(tool_choice_policy.get("mode", "auto")),
                tool_choice_name=(
                    str(tool_choice_policy.get("tool_name"))
                    if tool_choice_policy.get("tool_name")
                    else None
                ),
                stop_sequences=stop_sequences,
            )
            # T-30: Eskalations-Notices (prepend_blocked_notice) zusaetzlich
            # in den Tool-Result-Kanal vormerken. Der Holder wird auf die
            # jeweils aktive Runde gesetzt; bis dahin gilt das Ausgangs-Payload.
            accumulator_obj._pending_result_notice_sink = ( # type: ignore[union-attr]
                lambda notice_text: self._append_pending_result_notice_text(
                    _active_round_payload_holder[0] or payload, notice_text
                )
            )
            return accumulator_obj

        # C-14: lease und upstream-stream werden NICHT schon beim aufruf der
        # methode geoeffnet, sondern erst beim ersten pull des generators.
        # Vorher konnte ein client, der die verbindung vor dem ersten chunk
        # schloss (`gen.close()` ohne iteration), die queue-lease dauerhaft
        # halten und die upstream-response offen lassen — gemessen: nach drei
        # solchen abbruechen nimmt der endpoint keine streaming-requests mehr
        # an (`GLM queue wait timed out`). Ein nie gestarteter generator tut
        # jetzt gar nichts, weil er nichts erworben hat.
        stream_state: dict[str, object] = {}

        def _open_stream() -> None:
            """Erwirbt lease + conversation-slot und oeffnet den upstream."""
            lease = self.request_queue.acquire(f"stream:{payload.get('model', 'unknown')}")
            stream_account_index = self._get_preferred_account_index(lease.ticket)
            # C-03: siehe chat_completion() — die conversation wird fuer die
            # dauer des streams exklusiv reserviert. Wichtig fuer SSE: der
            # generator darf die conversation nicht beim ersten chunk
            # freigeben, sonst laeuft der naechste request mitten hinein.
            conversation_slot = self.exclusive_conversation(
                stream_account_index if stream_account_index is not None else 0
            )
            conversation_slot.__enter__()
            try:
                response, assistant_id = self._open_chat_stream(
                    payload,
                    preferred_account_index=stream_account_index,
                    filtered_tools=filtered_tools,
                )
            except Exception:
                conversation_slot.__exit__(None, None, None)
                lease.release()
                raise
            # C-15: siehe chat_completion() — jede im lauf erhaltene
            # conversation-id wird im finally abgeraeumt, nicht nur die letzte.
            stream_state.update(
                lease=lease,
                response=response,
                assistant_id=assistant_id,
                conversation_slot=conversation_slot,
                stream_account_index=stream_account_index,
                deadline=self._request_deadline(),
                created_conversations={},
                accumulator=new_accumulator(),
            )

        lease = None  # type: ignore[assignment]
        response = None  # type: ignore[assignment]
        assistant_id = None
        conversation_slot = None
        stream_account_index = 0
        deadline = self._request_deadline()
        created_conversations: dict[str, int] = {}
        # C-15: siehe non-stream — pro runde das verwendete konto mitschreiben.
        _conversation_account_index = stream_account_index
        # S-26: loop-guard-zaehler request-uebergreifend (siehe
        # `_mirror_loop_guard_counts`). Der accumulator wird pro Upstream-Runde
        # neu gebaut; ohne diesen request-scope zaehler sah jede Runde "erster
        # Call dieser Signatur" und die Wiederholungsgrenze griff nie — live
        # belegt in `ses_f161565c6ffeZp78k7WqoSoF06` (21x `open` auf denselben
        # fehlenden pfad, null drops, das modell erfand ein "the system has
        # repeatedly interrupted me", das es nicht gab).
        request_scope_signatures: dict[str, int] = {}  # S-27: 'drops' -> int
        accumulator = new_accumulator()
        # S-27: drop-zaehler request-uebergreifend (siehe `_mirror_drop_counts`).
        _seed_drop_counts(accumulator, request_scope_signatures)
        _seed_loop_guard_counts(accumulator, request_scope_signatures)

        def generate():
            nonlocal response, assistant_id, accumulator, empty_retries, history_budget
            # S-28: das korrektur-budget wird bei drops/remaps angehoben;
            # ohne `nonlocal` waere es im generator lokal und der
            # aussenbereich haette keinen wert (`UnboundLocalError`).
            nonlocal max_blocked_follow_ups
            nonlocal lease, conversation_slot, stream_account_index, deadline, created_conversations, _conversation_account_index
            # C-14: alles aufraeumen, was dieser generator besitzt. Ein
            # generator, der nie bis hierher kommt, besitzt nichts.
            if "lease" not in stream_state:
                _open_stream()
                lease = stream_state["lease"]  # type: ignore[assignment]
                response = stream_state["response"]  # type: ignore[assignment]
                assistant_id = stream_state["assistant_id"]
                conversation_slot = stream_state["conversation_slot"]
                stream_account_index = stream_state["stream_account_index"]  # type: ignore[assignment]
                deadline = stream_state["deadline"]  # type: ignore[assignment]
                created_conversations = stream_state["created_conversations"]  # type: ignore[assignment]
                accumulator = stream_state["accumulator"]  # type: ignore[assignment]
            # C-12: retries muessen das payload der AKTUELLEN runde
            # verwenden. Vorher griffen leer- und transient-retry auf das
            # urspruengliche payload zurueck und warfen damit die negative
            # tool-rueckmeldung der follow-up-runde weg — der retry loeste
            # denselben blockierten call erneut aus.
            active_payload = payload
            _active_round_payload_holder.clear()
            _active_round_payload_holder.append(active_payload)
            # T-30: falls ein frueherer Request dieser Konversation eine
            # Rueckmeldung vorgemerkt hat, geht sie jetzt ins erste
            # Tool-Result der Historie (garantiert zurueckgespiegelt).
            self._anchor_pending_result_notice(active_payload)
            attempt = 0
            blocked_follow_ups = 0
            # Namen, die in IRGEND EINER runde dieses turns blockiert
            # wurden. Die negative follow-up-runde setzt den namen nicht
            # zurueck — ohne diese merkung wuerde die letzte runde eine
            # erfundene erfolgsmeldung als antwort durchlassen.
            turn_blocked_names: list[str] = []
            while True:
                # C-08: zwei getrennte signale.
                #   served_content        = fuer den TRANSPORT-retry. Auch
                #     gesendetes reasoning zaehlt: ein retry wuerde den
                #     sichtbaren turn verdoppeln.
                #   served_visible_text   = fuer den LEER-retry. Ein turn, der
                #     nur reasoning lieferte, ist fuer den client wertlos —
                #     er beendet den agenten — und wird deshalb mit einem
                #     eigenen, begrenzten budget erneut versucht.
                served_content = False
                served_visible_text = False
                # S-25: gesetzt, wenn ein aufgaben-abandon erkannt und
                # unterdrueckt wurde. Treibt die fortsetzungs-runde. Der
                # prose-text wird erst in `finalize()` erzeugt, deshalb wird
                # er dort erkannt und gefiltert — nicht im sse-chunkpfad.
                suppress_abandon_reason: str | None = None
                retry_exc: UpstreamAPIError | None = None
                finalize_chunks: list[str] | None = None
                blocked: list[str] = []
                status: str | None = None
                self._last_stream_truncated = False
                # C-07: transportfehler mitten im stream gehoeren in die
                # retry-zustandsmaschine. Bedingung wie beim transient-event:
                # nur solange noch NICHTS an den client ging — ein teilweise
                # ausgelieferter turn kann nicht zurueckgenommen werden.
                try:
                    for event in self._iter_sse_events(response):
                        if not event:
                            continue
                        try:
                            self._raise_for_event_error(event, stream=True)
                        except UpstreamAPIError as exc:
                            if (
                                exc.transient
                                and not served_content
                                and attempt < max_stream_retries
                            ):
                                retry_exc = exc
                                break
                            raise
                        chunks, status = accumulator.consume_event(event)
                        _mirror_loop_guard_counts(accumulator, request_scope_signatures)
                        _mirror_drop_counts(accumulator, request_scope_signatures)
                        for chunk in chunks:
                            encoded = chunk.encode("utf-8")
                            if not served_content and (b'"content"' in encoded or b'"reasoning_content"' in encoded):
                                # trivial protocol residue ("[]") does not count
                                # as served content — it must not block recovery
                                # rounds (blocked-tool follow-up, transient retry)
                                # C-08: die alte byte-heuristik erkannte einen
                                # chunk nur dann als sichtbar, wenn er
                                # `"content"` OHNE `"reasoning_content"` enthielt.
                                # Der accumulator streamt reasoning aber als
                                # sichtbaren SSE-delta — ein transientes
                                # ereignis nach bereits gesendetem reasoning
                                # loeste dadurch einen retry aus und verdoppelte
                                # den turn. Jetzt wird der chunk ausgewertet.
                                try:
                                    delta = json.loads(
                                        encoded.decode("utf-8").removeprefix("data: ").strip()
                                    )["choices"][0]["delta"]
                                    content_value = delta.get("content")
                                    reasoning_value = delta.get("reasoning_content")
                                    for value in (content_value, reasoning_value):
                                        if value and str(value).strip() not in ("", "[]"):
                                            served_content = True
                                            break
                                    if content_value and str(content_value).strip() not in ("", "[]"):
                                        served_visible_text = True
                                except (json.JSONDecodeError, KeyError, IndexError, ValueError):
                                    served_content = True
                            yield encoded

                        if status in {"finish", "intervene"}:
                            finalize_chunks = accumulator.finalize(
                                status=status,
                                last_error=event.get("last_error") if isinstance(event.get("last_error"), dict) else None,
                            )
                            blocked = list(accumulator.blocked_tool_attempt_names)
                            for blocked_name in blocked:
                                if blocked_name not in turn_blocked_names:
                                    turn_blocked_names.append(blocked_name)
                            # S-25 -> S-27: der aufgaben-abandon wird NICHT
                            # mehr unterdrueckt. Das unterdruecken war die
                            # ursache der erfundenen system-meldungen: das
                            # modell bekam den text nie, in dem es seinen
                            # zustand beschrieb, und erfand stattdessen
                            # erklaerungen, die es nicht gab (live
                            # `ses_f1605c9d0ffeCSJmR08y4q29FK`: *"the system
                            # has repeatedly interrupted me telling me to stop
                            # calling `open`"*, *"MCP-Scrape-Fehler"*, *"wie
                            # vom System gefordert"* — alles frei erfunden).
                            #
                            # Der text bleibt jetzt sichtbar UND loest die
                            # korrekturrunde aus: das modell erfaehrt die
                            # aufgaben-abandon, bekommt dazu eine echte
                            # korrektur als user-nachricht (mit den notices),
                            # und arbeitet weiter. Information statt
                            # Schweigen — der umgekehrte ansatz von S-25 hat
                            # das system genau in die totecke getrieben.
                            final_text, _ = accumulator.render_full_output()
                            final_reason = is_abandon_claim(final_text)
                            if final_reason:
                                self.logger.warning(
                                    "S-27: task-abandon detected (reason=%s, chars=%s) — text stays "
                                    "visible, a correction round runs so the model gets the real facts",
                                    final_reason,
                                    len(final_text),
                                )
                                suppress_abandon_reason = final_reason
                            break
                except UpstreamAPIError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    if not _is_transport_error(exc):
                        raise
                    upstream_exc = _transport_error_to_upstream(exc)
                    if served_content or attempt >= max_stream_retries:
                        # Nach ausgeliefertem content ist der turn unumkehrbar
                        # (S-03/P-04: der client haette sonst zwei antworten),
                        # nach dem letzten versuch gibt es nichts mehr zu
                        # versuchen. Beides endet als UpstreamAPIError.
                        raise upstream_exc from exc
                    retry_exc = upstream_exc
                    self.logger.warning(
                        "Upstream transport error mid-stream (%s: %s); retrying attempt=%s/%s",
                        type(exc).__name__,
                        exc,
                        attempt + 1,
                        max_stream_retries,
                    )
                if self._last_stream_truncated and finalize_chunks is None:
                    # V-04: stream endete ohne finish/[DONE] — als transiente
                    # Unterbrechung retryen, solange nichts ausgeliefert wurde.
                    if not served_content and attempt < max_stream_retries and not self._deadline_exceeded(deadline):
                        retry_exc = UpstreamAPIError(
                            502,
                            "truncated_stream: upstream ended without [DONE]",
                            transient=True,
                        )
                        self.logger.warning(
                            "Upstream stream truncated before finish; retrying attempt=%s/%s",
                            attempt + 1,
                            max_stream_retries,
                        )
                    else:
                        # T-13/S-08: der turn wurde ABGESCHNITTEN. Er wird
                        # nicht als `stop` abgeschlossen — der client las
                        # die unvollstaendige antwort sonst als erfolg
                        # (und der anthropic-adapter uebersetzte sie in
                        # `stop_reason: end_turn` + `message_stop`).
                        finalize_chunks = accumulator.finalize(status="truncated")
                        blocked = list(accumulator.blocked_tool_attempt_names)
                        self.logger.warning(
                            "Upstream stream truncated; finalizing partial turn as error (retry budget exhausted or content already served)"
                        )
                if finalize_chunks is None and retry_exc is None:
                    finalize_chunks = accumulator.finalize(status="stop")
                    blocked = list(accumulator.blocked_tool_attempt_names)

                self.logger.warning(
                    "Stream turn ended status=%s blocked=%s blocked_follow_ups=%s max_blocked=%s",
                    status,
                    blocked,
                    blocked_follow_ups,
                    max_blocked_follow_ups,
                )

                if finalize_chunks is not None:
                    # V-02: eine Negativ-Folge-runde darf niemals bereits
                    # erzeugte gueltige Calls verwerfen. Enthielt der Turn
                    # einen erlaubten Call, wird er ausgeliefert; die
                    # blockierte Namensliste wird fuer die Diagnose geloggt.
                    turn_has_valid_calls = any(
                        b'"tool_calls"' in chunk.encode("utf-8", "ignore") and b'"name"' in chunk.encode("utf-8", "ignore")
                        for chunk in finalize_chunks
                    )
                    # Korrektur-runden sind nur sicher, wenn dieser turn
                    # KEINE ausfuehrbaren calls enthaelt. Sobald ein gueltiger
                    # call ausgeliefert wird, kann dessen Ergebnis erst in der
                    # naechsten OpenCode-Anfrage vorliegen; eine interne Runde
                    # hier wuerde die naechste Modellantwort ohne dieses echte
                    # Ergebnis verbrauchen und den Call/Turn entkoppeln.
                    # Remap-/Loop-Notices gehen in diesem Fall als Delta mit,
                    # und OpenCode liefert den Call normal aus. Die naechste
                    # Anfrage bringt anschliessend die tatsaechliche Ausgabe.
                    # Fuer einen blockierten-only-turn bleibt die interne
                    # Negativ-Korrektur moeglich, weil nichts auszufuehren ist.
                    # T-30: die Rueckmeldungen dieses Turns fuer das naechste
                    # echte Tool-Result vormerken. Bewusst VOR der
                    # Follow-up-Entscheidung: die client-seitige Historie
                    # enthaelt interne Korrektur-Runden nie — die Ankerung
                    # stellt sicher, dass die Rueckmeldung trotzdem ankommt.
                    self._store_pending_result_notice(active_payload, accumulator, blocked)
                    needs_correction = bool(
                        blocked
                        or getattr(accumulator, "native_remapped_calls", [])
                        # S-27: der drop-stand muss request-uebergreifend sein — im
                        # accumulator sieht die naechste runde wieder 0.
                        or int(request_scope_signatures.get("drops", 0) or 0) > 0
                        # S-25: ein unterdrueckter aufgaben-abandon ist selbst
                        # der grund fuer eine korrektur-runde — auch wenn sonst
                        # keine notice ansteht. Live: das modell bot die
                        # abgabe an, der text wurde verworfen, jetzt laeuft die
                        # fortsetzung.
                        or suppress_abandon_reason
                    )
                    # S-28/V-03: die byte-marken der BLOCKIERTEN werkzeugnamen.
                    # Sie duerfen beim vorab-zustellen der gueltigen calls
                    # (unten, vor dem accumulator-wechsel) nicht mit
                    # durchrutschen — V-03 gilt unveraendert.
                    _blocked_call_markers = [
                        b'"' + name.encode("utf-8") + b'"'
                        for name in sorted(
                            set(blocked)
                            | set(self.config.blocked_tool_names or [])
                        )
                    ]
                    if (
                        needs_correction
                        and not turn_has_valid_calls
                        and blocked_follow_ups < max_blocked_follow_ups
                    ):
                        # A valid call is handed to OpenCode below. Its
                        # output cannot exist until the client executes it and
                        # sends the next request, so never pre-empt that with
                        # an internal model round. Correct inline only when
                        # this turn has no executable calls to deliver.
                        # Follow-up round with a negative tool result
                        # instead of forwarding the blocked-call notice
                        # as final assistant text.
                        blocked_follow_ups += 1
                        follow_up = _build_blocked_tool_follow_up_payload(active_payload, accumulator, allowed_tool_names)
                        if follow_up is None:
                            self.logger.warning("blocked_tool_follow_up_payload returned None; blocked=%s", blocked)
                            for chunk in finalize_chunks:
                                yield chunk.encode("utf-8")
                            return
                        # S-24 -> S-27: ist dem client schon text gestreamt,
                        # kann die antwort nicht mehr zurueckgenommen werden
                        # (V-03: sonst haette der client zwei antworten).
                        #
                        # **BEI DROPS UND REMAPS WIRD DIE KORREKTUR JETZT
                        # IMMER GEFAHREN**, auch wenn schon text raus ist.
                        # Begruendung aus zwei Live-Faellen: die schleife
                        # `ses_f1605c9d0ffeCSJmR08y4q29FK` (75 mappings,
                        # 6 drops, **null** korrekturrunden — das modell
                        # erfand "the system has repeatedly interrupted me" /
                        # "MCP-Scrape-Fehler") und der abbruch mit
                        # "bis das Rundenlimit erreicht war" (null korrektur,
                        # aufgabe unvollstaendig). Der fruehere skip nach
                        # `served_content` war praktisch IMMER aktiv, weil
                        # `served_content` bei jedem normalen turn true ist
                        # (der turn streamt ja sichtbaren text) — die
                        # korrektur kam also nie an, egal wie gut die
                        # bedingung gebaut war. Ein zweiter Antwort-Block
                        # ist ein kosmetischer schaden; die fehlenden Fakten
                        # sind ein sachlicher, weil sie den Auftrag
                        # abbrechen lassen und den Grund verfaelschen.
                        #
                        # `served_content` gilt damit nur noch fuer den
                        # blocked-only-Fall, wo es nichts zu korrigieren gibt.
                        if served_content and not (
                            suppress_abandon_reason
                            or int(request_scope_signatures.get("drops", 0) or 0) > 0
                            or getattr(accumulator, "native_remapped_calls", [])
                        ):
                            self.logger.warning(
                                "Correction round skipped: content already served to the client "
                                "(V-03: a turn cannot be retracted) — notices go out as deltas",
                            )
                            for notice_text in _turn_notice_texts(accumulator, blocked):
                                yield accumulator._notice_chunk(notice_text).encode("utf-8")
                            for chunk in finalize_chunks:
                                yield chunk.encode("utf-8")
                            return
                        if served_content and (
                            suppress_abandon_reason
                            or int(request_scope_signatures.get("drops", 0) or 0) > 0
                            or getattr(accumulator, "native_remapped_calls", [])
                        ):
                            self.logger.warning(
                                "S-27: content already served, but the model needs the real facts "
                                "(abandon/drops/remaps present) — running the correction round anyway",
                            )
                        self.logger.warning(
                            "Starting negative-result follow-up round %s/%s (served_content=%s) "
                            "reason=blocked[%s]+drops[%s]+remaps[%s]",
                            blocked_follow_ups,
                            max_blocked_follow_ups,
                            served_content,
                            ", ".join(sorted(set(blocked))),
                            request_scope_signatures.get("drops", 0),
                            len(getattr(accumulator, "native_remapped_calls", []) or []),
                        )
                        response.close() # type: ignore
                        if accumulator.conversation_id:
                            created_conversations.setdefault(accumulator.conversation_id, _conversation_account_index)
                        accumulator = new_accumulator()
                        # S-26: request-uebergreifenden loop-guard-stand uebernehmen.
                        # S-27: drop-zaehler request-uebergreifend (siehe `_mirror_drop_counts`).
                        # In diesem Pfad gab es keine ausfuehrbaren Calls
                        # (siehe turn_has_valid_calls-Guard). Nur die sichere
                        # blockierte-only-Korrektur wird intern fortgesetzt;
                        # die urspruengliche Turn-Ausgabe wird nicht als
                        # vermeintlicher Tool-Resultat-Ersatz weitergereicht.
                        for _chunk in finalize_chunks:
                            _encoded = _chunk.encode("utf-8")
                            if b'"tool_calls"' in _encoded and not any(
                                _blocked_bytes in _encoded for _blocked_bytes in _blocked_call_markers
                            ):
                                yield _encoded
                        _seed_drop_counts(accumulator, request_scope_signatures)
                        _seed_loop_guard_counts(accumulator, request_scope_signatures)
                        accumulator.emitted_role = True
                        response, assistant_id = self._open_chat_stream(follow_up, preferred_account_index=self._get_preferred_account_index(lease.ticket), filtered_tools=filtered_tools)
                        # C-12: ab jetzt ist die follow-up-runde die aktive —
                        # ein retry darunter muss deren kontext behalten.
                        active_payload = follow_up
                        _active_round_payload_holder.clear()
                        _active_round_payload_holder.append(active_payload)
                        # T-30: KEINE zusaetzliche Ankerung hier — die
                        # Korrektur-Nachricht von
                        # `_build_blocked_tool_follow_up_payload` traegt die
                        # Rueckmeldungen bereits in sich; eine zweite Kopie
                        # als synthetisches Tool-Result waere Redundanz.
                        continue
                    # Leer-Turn-Autonomie-Fix: komplett
                    # leere Upstream-runden (kein text, keine reasoning, keine
                    # calls) liessen den agent bisher STEHEN (stresstest 10:21:
                    # 'finalize status=stop text_len=0 reasoning_len=0'). Bei
                    # leerer runde und noch nicht gestreamtem content ist ein
                    # retry mit frischer conversation sauber moeglich — der
                    # agent laeuft autonom weiter, ohne externen resume-schubser.
                    if (
                        not served_visible_text
                        and accumulator.is_empty_response()
                        and empty_retries < max_empty_response_retries
                        and not self._deadline_exceeded(deadline)
                    ):
                        empty_retries += 1
                        response.close() # type: ignore
                        self.logger.warning(
                            "Empty GLM response (no text/reasoning/calls) in stream — auto-retrying round %s/%s",
                            empty_retries,
                            max_empty_response_retries,
                        )
                        time.sleep(self.config.glm_stream_error_retry_interval)
                        if accumulator.conversation_id:
                            created_conversations.setdefault(accumulator.conversation_id, _conversation_account_index)
                        accumulator = new_accumulator()
                        # S-26: request-uebergreifenden loop-guard-stand uebernehmen.
                        # S-27: drop-zaehler request-uebergreifend (siehe `_mirror_drop_counts`).
                        _seed_drop_counts(accumulator, request_scope_signatures)
                        _seed_loop_guard_counts(accumulator, request_scope_signatures)
                        _conversation_account_index = self._get_preferred_account_index(lease.ticket)
                        response, assistant_id = self._open_chat_stream(active_payload, preferred_account_index=_conversation_account_index, filtered_tools=filtered_tools)
                        continue
                    # Ist die negativ-follow-up-runde erschoepft (oder war von
                    # anfang an keine moeglich) und hat die LETZTE runde selbst
                    # nichts blockiert, steht hier nur noch die antwort des
                    # modells. Live beobachtet (2026-09-25): sie behauptete
                    # "ich habe die seite geoeffnet" und zitierte sogar den
                    # seiteninhalt — der call hatte nie stattgefunden. Ohne
                    # diese notice liest der client die erfindung als erfolg
                    # und beendet den tool-loop.
                    #
                    # Die blocked-notice selbst wird gleich mitgebaut (siehe
                    # den S-22-block darunter) — alle notices eines turns
                    # gehen an einer stelle raus, in fester reihenfolge und im
                    # denkkanal statt im sichtbaren text.
                    # S-24/S-22: alle notices EINER stelle, in fester
                    # reihenfolge (siehe `_turn_notice_texts`), im DENKKANAL
                    # statt im sichtbaren text. Die reihenfolge ist damit
                    # nicht mehr von einem prepend-stempel abhaengig, der sie
                    # bei mehr als drei notices pro turn umkehrte.
                    notices = _turn_notice_texts(accumulator, turn_blocked_names)
                    for notice_text in notices:
                        yield accumulator._notice_chunk(notice_text).encode("utf-8")
                    if turn_blocked_names and not turn_has_valid_calls and not blocked:
                        blocked_names_text = ", ".join(sorted(set(turn_blocked_names)))
                        self.logger.warning(
                            "Blocked tool(s) %s were never executed; prepending honesty notice",
                            blocked_names_text,
                        )
                        for chunk in accumulator.prepend_blocked_notice(blocked_names_text, finalize_chunks):
                            yield chunk.encode("utf-8")
                        return
                    for chunk in finalize_chunks:
                        yield chunk.encode("utf-8")
                    return
                # Transient upstream error before any visible content: retry
                # the stream with a fresh conversation (guest tokens and
                # fresh sessions die quickly; reasoning replay is harmless).
                # Bei 10040 ("context exceeded"): kompressions-budget halbieren
                # und im aktiven payload weiterreichen — auch ein retry aus
                # einer Korrekturrunde muss deren Rueckmeldung behalten.
                if self._deadline_exceeded(deadline):
                    raise retry_exc or UpstreamAPIError(
                        502, "request deadline exceeded before stream retry", transient=True
                    )
                attempt += 1
                response.close() # type: ignore
                self.logger.warning(
                    "Transient GLM stream error before any visible content, retrying attempt=%s/%s error=%s",
                    attempt,
                    max_stream_retries,
                    retry_exc,
                )
                if retry_exc is not None:
                    history_budget = _halve_history_budget(active_payload, history_budget, retry_exc, self.logger)
                time.sleep(self.config.glm_stream_error_retry_interval)
                if accumulator.conversation_id:
                    created_conversations.setdefault(accumulator.conversation_id, _conversation_account_index)
                accumulator = new_accumulator()
                # S-26: request-uebergreifenden loop-guard-stand uebernehmen.
                # S-27: drop-zaehler request-uebergreifend (siehe `_mirror_drop_counts`).
                _seed_drop_counts(accumulator, request_scope_signatures)
                _seed_loop_guard_counts(accumulator, request_scope_signatures)
                _conversation_account_index = self._get_preferred_account_index(lease.ticket)
                response, assistant_id = self._open_chat_stream(active_payload, preferred_account_index=_conversation_account_index, filtered_tools=filtered_tools)

        def _release_stream_state() -> None:
            """C-14: gibt genau das frei, was dieser generator erworben hat.
            Ein nie gestarteter generator erwirbt nichts und raeumt nichts ab.
            Wird aus dem `finally` aufgerufen, damit dort KEIN `return`
            steht — ein return in einem finally wuerde eine laufende
            exception verschlucken."""
            try:
                response.close()  # type: ignore[union-attr]
            except Exception:
                pass
            if getattr(self.config, "glm_persistent_conversation", False) and accumulator.conversation_id:
                self.set_active_conversation_id(accumulator.conversation_id, stream_account_index)
            if accumulator.conversation_id:
                created_conversations.setdefault(accumulator.conversation_id, _conversation_account_index)
            for conversation_id, owner_account in sorted(created_conversations.items()):
                self.delete_conversation(
                    conversation_id,
                    assistant_id=assistant_id,
                    account_index=owner_account,
                )
            if conversation_slot is not None:
                conversation_slot.__exit__(None, None, None)
            if lease is not None:
                lease.release()

        def wrapped():
            try:
                yield from generate()
            finally:
                if "lease" in stream_state:
                    _release_stream_state()

        return wrapped()

    # Error codes the upstream may emit mid-stream that are worth a retry
    # with the same or a rotated account instead of failing the whole request.
    # 10040 = "model response context exceeded": input-historie zu gross —
    # retry koppelt an halbierung des kompressions-budgets (siehe
    # _open_chat_stream), deshalb transient.
    #
    # F-6: 10061 steht hier BEWUSST NICHT mehr. Der code traegt zwei
    # voellig verschiedene bedeutungen:
    #   "请等待其他对话生成完毕"  = nebenlauf-busy, weg in sekunden
    #   "请求过于频繁"            = konto-drosselung, weg in minuten
    # Beide ueber denselben transient-pfad zu schicken war die ursache der
    # ratelimit-eskalation: der stream-retry (2x, 1s) UND der
    # busy-http-loop (30x, 2s) feuerten beide auf eine echte drosselung und
    # verstaerkten sie mit jedem versuch. Die trennung passiert jetzt in
    # _classify_upstream_throttle; ein 10061 ist nur dann transient, wenn es
    # der nebenlauf-busy ist.
    TRANSIENT_UPSTREAM_ERROR_CODES = {10025, 10040, 10062}

    # Der code, dessen beide varianten oben getrennt behandelt werden.
    THROTTLE_UPSTREAM_ERROR_CODES = {10061}
    # Textmarker des nebenlauf-busy: eine andere konversation im web-chat
    # blockiert den slot, das ist in sekunden vorbei.
    THROTTLE_BUSY_MARKERS = ("请等待其他对话生成完毕",)
    # Textmarker der echten drosselung (kleinbuchstaben, wird gegen
    # .casefold() geprueft — die chinesischen marker sind davon unberuehrt).
    THROTTLE_RATE_LIMIT_MARKERS = (
        "请求过于频繁",
        "过于频繁",
        "访问频繁",
        "too many requests",
        "rate limit",
        "rate-limit",
        "ratelimit",
    )

    @staticmethod
    def _payload_error_sources(payload: dict[str, object]) -> list[dict[str, object]]:
        """payload + seine `error`/`last_error`-objekte. Der upstream legt
        den fehlercode je nach antwortform in eine dieser ebenen."""
        sources = [payload]
        for key in ("error", "last_error"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                sources.append(nested)
        return sources

    @classmethod
    def _payload_has_code(
        cls,
        payload: dict[str, object],
        codes: set[int],
        keys: tuple[str, ...] = ("error_code", "code"),
    ) -> bool:
        for source in cls._payload_error_sources(payload):
            for key in keys:
                candidate = source.get(key)
                if candidate is None:
                    continue
                try:
                    if int(candidate) in codes:  # type: ignore[arg-type]
                        return True
                except (TypeError, ValueError):
                    continue
        return False

    @classmethod
    def _payload_error_text(cls, payload: dict[str, object]) -> str:
        """gesamter meldungstext des payloads, casefolded. Deckt die
        message-felder des 429-bodies genauso ab wie die eines SSE-events,
        weil `error`/`last_error` mitgezogen werden."""
        parts: list[str] = []
        for source in cls._payload_error_sources(payload):
            for key in ("message", "err_msg", "error_msg", "detail"):
                value = source.get(key)
                if value:
                    parts.append(str(value))
        return " ".join(parts).casefold()

    @classmethod
    def _classify_upstream_throttle(cls, payload: object) -> str:
        """F-6: trennt die zwei bedeutungen von code 10061.

        Rueckgabe: ``"busy"``, ``"rate_limit"`` oder ``""`` (kein throttling).
        Der text entscheidet, nicht der code: beide varianten melden 10061,
        nur die eine ist in sekunden weg.

        Ein 10061 OHNE erkennbare message wird als ratelimit behandelt. Das
        ist der harmlosere fehlerfall: im zweifel zwei versuche mit 30s/60s
        abstand und danach ein sauberer 429 — statt 30 schneller versuche,
        die eine bestehende drosselung nur verstaerken.
        """
        if not isinstance(payload, dict):
            return ""
        message = cls._payload_error_text(payload)
        if any(marker in message for marker in cls.THROTTLE_BUSY_MARKERS):
            return "busy"
        if any(marker in message for marker in cls.THROTTLE_RATE_LIMIT_MARKERS):
            return "rate_limit"
        # `status` ist das feld, in dem chatglm.cn den 10061 im 429-body
        # meldet; error_code/code decken die SSE-variante ab.
        if cls._payload_has_code(
            payload,
            cls.THROTTLE_UPSTREAM_ERROR_CODES,
            ("error_code", "code", "status"),
        ):
            return "rate_limit"
        return ""

    def _payload_is_transient(self, payload: object) -> bool:
        """C-07: transient-Erkennung ZENTRAL. Vorher galt sie nur fuer SSE-
        events; ein transienter code im JSON-body (non-stream) oder im
        HTTP-error wurde als permanenter fehler behandelt und nicht
        recovered.

        F-6: 10061 ist nur der nebenlauf-busy transient. Die drosselung
        darf nicht in den stream-retry laufen — sie wuerde dort weitere
        versuche in sekundenabstaenden produzieren."""
        if not isinstance(payload, dict):
            return False
        if self._payload_has_code(
            payload,
            self.THROTTLE_UPSTREAM_ERROR_CODES,
            ("error_code", "code", "status"),
        ):
            return self._classify_upstream_throttle(payload) == "busy"
        return self._payload_has_code(payload, self.TRANSIENT_UPSTREAM_ERROR_CODES)

    def _raise_for_event_error(self, event: dict[str, object], stream: bool) -> None:
        status = str(event.get("status", "")).strip().lower()
        last_error = event.get("last_error")
        event_error = self._extract_event_error(event)
        if status != "error" and not event_error and not isinstance(last_error, dict):
            return

        error_payload: dict[str, object] = {}
        if isinstance(last_error, dict):
            error_payload.update(last_error)
        if isinstance(event_error, dict):
            error_payload.update(event_error)
        if not error_payload and status != "error":
            return

        error_code = error_payload.get("error_code", error_payload.get("code"))
        error_message = str(
            error_payload.get("err_msg")
            or error_payload.get("message")
            or ("GLM stream request error" if stream else "GLM request error")
        ).strip()
        detail = f"code={error_code} " if error_code is not None else ""
        transient = self._payload_is_transient(error_payload or event)
        # F-6: eine drosselung, die mitten im stream kommt, ist kein
        # gateway-defekt. Sie als 429 zu melden statt als 502, damit der
        # client den Unterschied zwischen "upstream kaputt" und "warte,
        # zu schnell" sieht und nicht sein eigenes retry-verhalten
        # darauf ausrichtet.
        status_code = 429 if self._classify_upstream_throttle(error_payload or event) == "rate_limit" else 502
        raise UpstreamAPIError(
            status_code=status_code,
            message=f"GLM upstream returned an error | {detail}{error_message}".strip(),
            payload=error_payload or event,
            transient=transient,
        )

    def _extract_event_error(self, event: dict[str, object]) -> dict[str, object] | None:
        parts = event.get("parts")
        if not isinstance(parts, list):
            return None
        for part in parts:
            if not isinstance(part, dict):
                continue
            error = part.get("error")
            if isinstance(error, dict) and error:
                return error
            part_status = str(part.get("status", "")).strip().lower()
            if part_status == "error":
                # Der Upstream spiegelt unsere OpenAI-tool-Runde als native
                # 'tool'-Rolle zurueck (show_type mc_tool_result*), wenn das
                # Modell versucht, ein client-tool serverseitig auszufuehren.
                # Das ist kein fataler Fehler: wir ueberspringen solche Parts
                # und lassen das Modell weiter antworten.
                role = str(part.get("role", "")).strip().lower()
                meta = part.get("meta_data")
                show_type = ""
                if isinstance(meta, dict):
                    show_type = str(meta.get("show_type", ""))
                if role == "tool" or show_type.startswith("mc_tool_result"):
                    continue
                return {"message": "GLM part status error"}
        return None

    def delete_conversation(
        self,
        conversation_id: str,
        assistant_id: str | None = None,
        account_index: int | None = None,
    ) -> None:
        """C-15: die conversation gehoert DEM konto, das sie erzeugt hat.

        Ohne die bindung lief `delete_conversation` ueber
        `_call_with_account_failover` und konnte ein anderes konto waehlen.
        Bei mehreren accounts loeschte das dann die falsche conversation
        und die eigentliche blieb serverseitig liegen (memory-/context-leck
        und ein haenger queue-slot)."""

        if getattr(self.config, "glm_persistent_conversation", False):
            return
        if not self.config.glm_delete_conversation:
            return
        if not conversation_id:
            self.logger.warning("Skipping GLM conversation deletion: no conversation_id obtained assistant_id=%s", assistant_id or self.config.glm_assistant_id)
            return

        actual_assistant_id = assistant_id or self.config.glm_assistant_id
        body = json.dumps(
            {
                "assistant_id": actual_assistant_id,
                "conversation_id": conversation_id,
            }
        ).encode("utf-8")
        try:
            def send_request(account_index: int, access_token: str):
                timestamp, nonce, sign = build_sign()
                request = urllib.request.Request(
                    self.config.delete_conversation_url,
                    method="POST",
                    data=body,
                    headers={
                        **self.auth.get_browser_headers(),
                        "Authorization": f"Bearer {access_token}",
                        "Referer": "https://chatglm.cn/main/alltoolsdetail",
                        "X-Device-Id": uuid.uuid4().hex,
                        "X-Nonce": nonce,
                        "X-Request-Id": uuid.uuid4().hex,
                        "X-Sign": sign,
                        "X-Timestamp": timestamp,
                    },
                )
                return urllib.request.urlopen(request, timeout=self.config.request_timeout)

            if account_index is not None:
                # C-15: gezielt das erzeugerkonto, kein failover.
                try:
                    access_token = self.auth.get_access_token_for_account(account_index)
                except Exception as exc:  # pragma: no cover - konto weg
                    self.logger.warning(
                        "Skipping conversation deletion: account %s unavailable (%s)",
                        account_index,
                        exc,
                    )
                    return
                with send_request(account_index, access_token) as response:  # type: ignore
                    payload = self.auth.read_json_response(response)
            else:
                with self._call_with_account_failover("delete_conversation", send_request) as response: # type: ignore
                    payload = self.auth.read_json_response(response)
            status = payload.get("status", payload.get("code"))
            if status not in {0, None}:
                self.logger.warning(
                    "GLM conversation deletion returned non-success status conversation_id=%s assistant_id=%s payload=%s",
                    conversation_id,
                    actual_assistant_id,
                    payload,
                )
                return
            self.logger.info(
                "Deleted GLM conversation conversation_id=%s assistant_id=%s",
                conversation_id,
                actual_assistant_id,
            )
        except Exception as exc:
            self.logger.warning(
                "Failed to delete GLM conversation conversation_id=%s assistant_id=%s error=%s",
                conversation_id,
                actual_assistant_id,
                exc,
            )

    def _resolve_target_conversation_id(
        self, openai_payload: dict[str, object], preferred_account_index: int | None
    ) -> str:
        """C-03: welche upstream-conversation darf diese runde verwenden?

        Eine clientgelieferte id ist KEIN eigentumsnachweis. Sie wird nur
        akzeptiert, wenn sie genau die conversation ist, die dieser proxy
        fuer dieses konto selbst fuehrt. Alles andere (fremde oder geratene
        id) wird ignoriert und startet eine eigene runde — sonst koennte ein
        client die upstream-historie eines anderen fortsetzen. Ohne
        persistenz bleibt es beim expliziten `new_session`/`reset`."""
        client_conv_id = openai_payload.get("conversation_id")
        if client_conv_id and isinstance(client_conv_id, str):
            requested_conv_id = client_conv_id.strip()
            owned_conv_id = (
                self.conversation_for_account(preferred_account_index)
                if preferred_account_index is not None
                else self.get_active_conversation_id()
            )
            if not requested_conv_id:
                return ""
            if requested_conv_id == owned_conv_id:
                return requested_conv_id
            self.logger.info(
                "Ignoring unverified client conversation_id (not owned by this proxy/account)"
            )
            return ""
        if bool(openai_payload.get("new_session")) or bool(openai_payload.get("reset_conversation")):
            return ""
        if getattr(self.config, "glm_persistent_conversation", False):
            return (
                self.conversation_for_account(preferred_account_index)
                if preferred_account_index is not None
                else self.get_active_conversation_id()
            )
        return ""

    def _open_chat_stream(self, openai_payload: dict[str, object], preferred_account_index: int | None = None, filtered_tools: list[dict[str, object]] | None = None):
        requested_model = str(openai_payload.get("model", "glm-4"))
        upstream_model, assistant_id = resolve_upstream_model(requested_model, self.config)
        if filtered_tools is None:
            filtered_tools, _ = self._resolve_tools(openai_payload)
        # H1 aus der kontext-arbeit: chatglm.cn driftet bei aufgeblähter
        # request-historie. Historie VOR der Konvertierung komprimieren, damit
        # budget-grenze auf den rohen messages liegt (nicht auf dem
        # flachen prompt — tools-instructions brauchen ihr eigenes budget).
        # Retry-Kopplung bei upstream 10040 ("context exceeded"): der
        # retry-pfad (TRANSIENT_UPSTREAM_ERROR_CODES) halbiert dieses budget
        # ueber das payload-feld _glm_history_budget, bis der upstream
        # mitmacht — kein harter fail mehr auf langen sessions.
        history_budget = self.config.glm_history_max_chars
        raw_budget = openai_payload.get("_glm_history_budget")
        if isinstance(raw_budget, int) and raw_budget > 0:
            history_budget = raw_budget
        compressed_messages = compress_history_messages(
            list(openai_payload.get("messages", [])), # type: ignore[arg-type]
            history_budget,
        )
        if len(compressed_messages) != len(list(openai_payload.get("messages", []))): # type: ignore[arg-type]
            self.logger.info(
                "Compressed request history messages=%s -> %s (budget=%s chars)",
                len(list(openai_payload.get("messages", []))), # type: ignore[arg-type]
                len(compressed_messages),
                history_budget,
            )
        converted_messages = convert_messages(
            messages=compressed_messages, # type: ignore
            tools=filtered_tools,
            blocked_tool_names={name.strip() for name in self.config.blocked_tool_names if name.strip()},
            tool_choice=openai_payload.get("tool_choice"),
        )
        debug_dump(self.logger, self.config.debug_dump_all, "OpenAI raw chat request payload", openai_payload)
        debug_dump(self.logger, self.config.debug_dump_all, "Converted GLM messages", converted_messages)
        refs = self._upload_referenced_files(list(openai_payload.get("messages", []))) # type: ignore
        if refs:
            converted_messages[0]["content"] = refs + list(converted_messages[0]["content"]) # type: ignore
            debug_dump(self.logger, self.config.debug_dump_all, "GLM messages after appending upload references", converted_messages)

        chat_mode = resolve_chat_mode(
            model=requested_model,
            reasoning_effort=openai_payload.get("reasoning_effort"),
            deep_research=openai_payload.get("deep_research"),
            has_tools=bool(filtered_tools),
        )
        is_networking = resolve_networking(
            model=requested_model,
            web_search=openai_payload.get("web_search"),
        )

        target_conv_id = self._resolve_target_conversation_id(
            openai_payload, preferred_account_index
        )

        request_body = json.dumps(
            {
                "assistant_id": assistant_id,
                "conversation_id": target_conv_id,
                "project_id": "",
                "chat_type": "user_chat",
                "messages": converted_messages,
                "meta_data": {
                    "channel": "",
                    "chat_mode": chat_mode,
                    "draft_id": "",
                    "if_plus_model": True,
                    "input_question_type": "xxxx",
                    "is_networking": is_networking,
                    "is_test": False,
                    "platform": "pc",
                    "quote_log_id": "",
                    "cogview": {"rm_label_watermark": False},
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

        self.logger.info(
            "Forwarding request model=%s upstream=%s stream=%s",
            requested_model,
            upstream_model,
            openai_payload.get("stream"),
        )
        debug_dump(self.logger, self.config.debug_dump_all, "Raw chat request body forwarded to GLM", request_body)

        def send_request(account_index: int, access_token: str):
            # F-6: busy und ratelimit teilen sich den HTTP-429/code-10061-
            # pfad, brauchen aber gegensetzliche antworten. Busy = eine
            # andere konversation blockiert den slot, das ist in sekunden
            # vorbei -> viele kurze versuche (GLM_BUSY_MAX_RETRIES).
            # Ratelimit = konto-drosselung, die erst in minuten abklingt ->
            # wenige versuche mit langem backoff, danach ein sauberer 429 an
            # den client. Vorher liefen beide ueber denselben 30er-loop und
            # hauen bei echter drosselung 30 mal in ~4 minuten auf dasselbe
            # konto, was die sperre jeweils verlaengert hat.
            busy_attempts = 0
            rate_limit_attempts = 0
            deadline = self._request_deadline()
            while True:
                try:
                    timestamp, nonce, sign = build_sign()
                    request = urllib.request.Request(
                        self.config.chat_stream_url,
                        data=request_body,
                        method="POST",
                        headers={
                            **self.auth.get_browser_headers(),
                            "Authorization": f"Bearer {access_token}",
                            "X-Device-Id": uuid.uuid4().hex,
                            "X-Nonce": nonce,
                            "X-Request-Id": uuid.uuid4().hex,
                            "X-Sign": sign,
                            "X-Timestamp": timestamp,
                        },
                    )
                    debug_dump(
                        self.logger,
                        self.config.debug_dump_all,
                        f"Chat request headers forwarded to GLM account={account_index} attempt={busy_attempts + rate_limit_attempts + 1}",
                        dict(request.header_items()),
                    )
                    return self._prepare_chat_response(
                        urllib.request.urlopen(request, timeout=self.config.request_timeout)
                    )
                except urllib.error.HTTPError as exc:
                    error_payload = self._read_error_payload(exc)
                    throttle = self._classify_upstream_throttle(error_payload) if exc.code == 429 else ""
                    if (
                        throttle == "rate_limit"
                        and rate_limit_attempts < self.config.glm_rate_limit_max_retries
                    ):
                        wait_seconds = self._rate_limit_backoff_seconds(rate_limit_attempts + 1)
                        enough_deadline = (
                            deadline is None
                            or time.monotonic() + wait_seconds < deadline
                        )
                        if not enough_deadline:
                            # Kein Retry, dessen Backoff die verbleibende
                            # Request-Deadline bereits ueberschreitet.
                            wait_seconds = 0.0
                        else:
                            rate_limit_attempts += 1
                            self.logger.warning(
                                "GLM upstream rate limit hit (code 10061), backing off instead of hammering attempt=%s/%s wait=%.1fs account=%s",
                                rate_limit_attempts,
                                self.config.glm_rate_limit_max_retries,
                                wait_seconds,
                                account_index,
                            )
                            time.sleep(wait_seconds)
                            continue
                    if (
                        throttle == "busy"
                        and busy_attempts < self.config.glm_busy_max_retries
                        and not self._deadline_exceeded(deadline)
                    ):
                        busy_attempts += 1
                        # S-14: exponentielles backoff mit jitter statt
                        # fester wartezeit. Ohne exponentiellen anteil
                        # stampfen alle versuche im gleichen takts erneut
                        # auf dasselbe ausgelastete upstream; der jitter
                        # entzerrt mehrere parallele clienten.
                        wait_seconds = self._busy_backoff_seconds(busy_attempts - 1)
                        self.logger.warning(
                            "GLM is processing another conversation, waiting to retry attempt=%s/%s wait=%.1fs account=%s",
                            busy_attempts,
                            self.config.glm_busy_max_retries,
                            wait_seconds,
                            account_index,
                        )
                        time.sleep(wait_seconds)
                        continue

                    message = self._build_error_message(exc.code, error_payload)
                    if target_conv_id and (exc.code in {400, 404} or "conversation" in message.lower() or "对话" in message):
                        self.logger.warning("GLM conversation %s seems invalid or expired (%s) — resetting active conversation", target_conv_id, message)
                        self.reset_active_conversation()
                    if throttle:
                        # F-6: das budget ist erschoepft oder die request-
                        # deadline laeuft ab. Bewusst KEIN `transient` —
                        # sonst nimmt der stream-retry die drosselung wieder
                        # auf und produziert genau die versuche, die wir
                        # hier gerade vermieden haben. Der client sieht 429.
                        self.logger.warning(
                            "GLM upstream still throttled after %s retries (kind=%s) — returning 429 to client",
                            (rate_limit_attempts if throttle == "rate_limit" else busy_attempts),
                            throttle,
                        )
                    # C-07: transienter upstream-code im error-body (z.b. 10040
                    # bei zu grosser historie) wird auch bei HTTP-Fehlern
                    # als transient markiert, damit der stream-retry ihn
                    # mit halbiertem budget aufnehmen kann.
                    raise UpstreamAPIError(
                        status_code=exc.code,
                        message=message,
                        payload=error_payload,
                        transient=self._payload_is_transient(error_payload),
                    ) from exc

        response = self._call_with_account_failover(
            f"chat:{requested_model}",
            send_request,
            preferred_account_index=preferred_account_index,
        )
        return response, assistant_id

    def _open_image_stream(self, payload: dict[str, object], preferred_account_index: int | None = None):
        prompt = str(payload.get("prompt", "")).strip()
        if not prompt:
            raise UpstreamAPIError(status_code=400, message="Image generation request is missing prompt")

        size = str(payload.get("size", "1024x1024")).strip().lower()
        aspect_ratio = self._resolve_aspect_ratio(size)
        user_model = str(payload.get("model", self.config.glm_image_model_name)).strip() or self.config.glm_image_model_name
        request_body = json.dumps(
            {
                "assistant_id": self.config.glm_image_assistant_id,
                "conversation_id": "",
                "project_id": "",
                "chat_type": "user_chat",
                "meta_data": {
                    "cogview": {
                        "aspect_ratio": aspect_ratio,
                        "style": self._resolve_image_style(payload),
                        "scene": self._resolve_image_scene(payload),
                        "chat_model": "",
                        "rm_label_watermark": False,
                    },
                    "is_test": False,
                    "input_question_type": "xxxx",
                    "channel": "",
                    "draft_id": "",
                    "chat_mode": "",
                    "is_networking": False,
                    "quote_log_id": "",
                    "platform": "pc",
                },
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": prompt}],
                    }
                ],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

        self.logger.info(
            "Forwarding image request model=%s assistant_id=%s size=%s n=%s",
            user_model,
            self.config.glm_image_assistant_id,
            size,
            payload.get("n", 1),
        )
        debug_dump(self.logger, self.config.debug_dump_all, "OpenAI raw image request payload", payload)
        debug_dump(self.logger, self.config.debug_dump_all, "Raw image request body forwarded to GLM", request_body)

        def send_request(account_index: int, access_token: str):
            timestamp, nonce, sign = build_sign()
            request = urllib.request.Request(
                self.config.chat_stream_url,
                data=request_body,
                method="POST",
                headers={
                    **self.auth.get_browser_headers(),
                    "Authorization": f"Bearer {access_token}",
                    "X-Device-Id": uuid.uuid4().hex,
                    "X-Nonce": nonce,
                    "X-Request-Id": uuid.uuid4().hex,
                    "X-Sign": sign,
                    "X-Timestamp": timestamp,
                },
            )
            debug_dump(
                self.logger,
                self.config.debug_dump_all,
                f"Image request headers forwarded to GLM account={account_index}",
                dict(request.header_items()),
            )
            try:
                return self._prepare_chat_response(urllib.request.urlopen(request, timeout=self.config.request_timeout))
            except urllib.error.HTTPError as exc:
                error_payload = self._read_error_payload(exc)
                message = self._build_error_message(exc.code, error_payload)
                raise UpstreamAPIError(status_code=exc.code, message=message, payload=error_payload) from exc

        response = self._call_with_account_failover(
            f"image:{user_model}",
            send_request,
            preferred_account_index=preferred_account_index,
        )
        return response, self.config.glm_image_assistant_id

    def _prepare_chat_response(self, response):
        content_type = response.headers.get("Content-Type", "").lower()
        if "application/json" in content_type:
            # C-16: der originale HTTP-response wird vollstaendig gelesen und
            # geschlossen; zurueckgegeben wird ein eigener stream ueber einen
            # kopierten body. Andernfalls bleiben sockets offen.
            try:
                payload = self.auth.read_json_response(response)
            finally:
                try:
                    response.close()
                except Exception:
                    pass
            debug_dump(self.logger, self.config.debug_dump_all, "GLM non-streaming raw JSON response", payload)
            status = payload.get("status")
            message = str(payload.get("message", "")).strip()
            if status not in (0, None) or message:
                raise UpstreamAPIError(
                    status_code=502,
                    message=self._build_error_message(200, payload),
                    payload=payload,
                    # C-07: ein transienter code im JSON-body (z.B. 10040
                    # "kontext zu gross") war hier dauerhaft und wurde
                    # weder retried noch mit halbiertem historien-budget
                    # erneut versucht.
                    transient=self._payload_is_transient(payload),
                )

            response_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            return BufferedReader(BytesIO(response_body))

        return self._wrap_stream_response(response)

    def _build_images_response(
        self,
        request_payload: dict[str, object],
        final_event: dict[str, object],
        accumulator: GLMEventAccumulator,
    ) -> dict[str, object]:
        requested_count = self._coerce_positive_int(request_payload.get("n"), default=1, maximum=10)
        response_format = str(request_payload.get("response_format", "url")).strip().lower()
        created = int(time.time())

        data: list[dict[str, object]] = []
        ordered_parts = list(accumulator.parts_by_logic_id.values())
        ordered_parts.sort(key=lambda item: str(item.get("logic_id", "")))

        for part in ordered_parts:
            if len(data) >= requested_count:
                break
            if not isinstance(part, dict):
                continue
            part_status = str(part.get("status", ""))
            if part_status != "finish":
                continue
            content_items = part.get("content", [])
            if not isinstance(content_items, list):
                continue
            for content in content_items:
                if len(data) >= requested_count:
                    break
                if not isinstance(content, dict) or content.get("type") != "image":
                    continue
                images = content.get("image", [])
                if not isinstance(images, list):
                    continue
                revised_prompt = str(content.get("code", "")).strip() or None
                for image in images:
                    if len(data) >= requested_count:
                        break
                    if not isinstance(image, dict):
                        continue
                    image_url = str(image.get("image_url", "")).strip()
                    if not image_url:
                        continue
                    item: dict[str, object] = {}
                    if response_format == "b64_json":
                        item["b64_json"] = self._download_image_as_base64(image_url)
                    else:
                        item["url"] = image_url
                    if revised_prompt:
                        item["revised_prompt"] = revised_prompt
                    data.append(item)

        if not data:
            raise UpstreamAPIError(
                status_code=502,
                message="GLM image request completed but returned no usable image results.",
                payload=final_event,
            )

        self.logger.info("Image generation completed image_count=%s", len(data))
        return {
            "created": created,
            "data": data,
        }

    def _resolve_aspect_ratio(self, size: str) -> str:
        normalized = size.strip().lower()
        if normalized in IMAGE_SIZE_TO_ASPECT_RATIO:
            return IMAGE_SIZE_TO_ASPECT_RATIO[normalized]
        if re.fullmatch(r"\d+x\d+", normalized):
            width_str, height_str = normalized.split("x", 1)
            width = max(int(width_str), 1)
            height = max(int(height_str), 1)
            return f"{width}:{height}"
        return "1:1"

    def _resolve_image_style(self, payload: dict[str, object]) -> str:
        style = str(payload.get("style", "none")).strip().lower()
        return style if style else "none"

    def _resolve_image_scene(self, payload: dict[str, object]) -> str:
        scene = str(payload.get("scene", "none")).strip().lower()
        return scene if scene else "none"

    def _coerce_positive_int(self, value: object, default: int, maximum: int) -> int:
        try:
            parsed = int(value) if value is not None else default # type: ignore
        except (TypeError, ValueError):
            parsed = default
        return max(1, min(parsed, maximum))

    def _download_image_as_base64(self, image_url: str) -> str:
        """C-02: dieser pfad war der einzige ohne SSRF-schutz —

        gemessen: `_download_image_as_base64("file:///…/secret.txt")` lieferte
        den lokalen dateiinhalt, `http://127.0.0.1:PORT/…` den inhalt eines
        lokalen diensts, und `response.read()` war unbegrenzt. Die
        datei-abhandlung (`_fetch_file_payload`) hatte schema-pruefung,
        ip-pruefung, redirect-nachpruefung und groessenlimit — dieser
        pfad davon nichts. Jetzt teilt er sich die schutzfunktionen."""
        try:
            # schema-pruefung + ip-pruefung (auch auf private/loopback/
            # link-local/reserved) wie beim datei-pfad
            self._assert_public_url(image_url)
            check_url = self._assert_public_url

            class _NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    # ein redirect ins private netz darf nicht durchgehen
                    check_url(newurl)
                    return super().redirect_request(req, fp, code, msg, headers, newurl)

            opener = urllib.request.build_opener(_NoRedirect)
            with opener.open(image_url, timeout=self.config.request_timeout) as response:
                # C-20-Prinzip: unbegrenztes lesen eines vom client
                # kontrollierten ziels ist ein speicher-vektor.
                image_bytes = response.read(FILE_SIZE_LIMIT + 1)
                if len(image_bytes) > FILE_SIZE_LIMIT:
                    raise ValueError("Image exceeds the size limit, download rejected.")
            return base64.b64encode(image_bytes).decode("ascii")
        except UpstreamAPIError:
            raise
        except Exception as exc:
            raise UpstreamAPIError(status_code=502, message=f"Failed to download image: {redact_sensitive_text(image_url)} error={type(exc).__name__}") from exc

    def _iter_sse_events(self, response):
        """C-16: die SSE-verbindung wird hier selbst geschlossen.

        Vorher hing die Freigabe ausschliesslich an den aufrufern. Bricht
        einer den generator vorzeitig ab (`return` mitten in der
        schleife, client-abruf), blieb der socket offen — ueber viele
        requests sammelten sich HTTP-verbindungen und file-descriptoren
        an und belasteten upstream-verbindungen, threads und queue-slots.

        Kein aufrufer verwendet `response` nach der schleife, doppeltes
        `close()` ist bei http.client unkritisch."""
        pending = ""
        decoder = codecs.getincrementaldecoder("utf-8")("ignore")
        saw_done = False
        incomplete_read = False

        def emit_block(block: str):
            lines = [line for line in block.split("\n") if line.startswith("data:")]
            if not lines:
                return None
            payload = "\n".join(line[5:].strip() for line in lines)
            debug_dump(self.logger, self.config.debug_dump_all, "GLM raw SSE block", block)
            if payload == "[DONE]":
                return "[DONE]"
            try:
                parsed = json.loads(payload)
                debug_dump(self.logger, self.config.debug_dump_all, "GLM parsed SSE payload", parsed)
                return parsed
            except json.JSONDecodeError:
                self.logger.debug("Ignoring unparseable SSE fragment: %s", payload)
                return None

        try:
            while True:
                stop_after_chunk = False
                try:
                    raw_chunk = response.read(4096)
                except http.client.IncompleteRead as exc:
                    raw_chunk = exc.partial or b""
                    stop_after_chunk = True
                    incomplete_read = True
                    self.logger.warning("Upstream SSE connection closed early, finalizing with received data bytes=%s", len(raw_chunk))
                if not raw_chunk:
                    break

                # \r\n-Normalisierung auf dem AKKUMULIERTEN pending: ein Paar,
                # das ueber eine 4096er chunk-grenze split ('\r' | '\n'), wird
                # sonst nie ersetzt — die block-separatoren bleiben unerkannt
                # und events gehen als 'unparseable fragment' verloren.
                pending = (pending + decoder.decode(raw_chunk, False)).replace("\r\n", "\n")

                while "\n\n" in pending:
                    block, pending = pending.split("\n\n", 1)
                    event = emit_block(block.strip())
                    if event == "[DONE]":
                        saw_done = True
                        return
                    if event is not None:
                        yield event

                if stop_after_chunk:
                    break

            remaining = decoder.decode(b"", True)
            if remaining:
                pending = (pending + remaining).replace("\r\n", "\n")

            if pending.strip():
                event = emit_block(pending.strip())
                if event == "[DONE]":
                    return
                if event is not None:
                    yield event

            # V-04: ein stream, der ohne [DONE] endet, ist abgeschnitten. Das war
            # bisher ein stiller erfolg — der client finalisierte daraus eine
            # vollstaendige antwort, obwohl inhalt fehlte oder ein tool-call
            # mitten im json abbrach. Der fehler wird jetzt als zustand
            # gemerkt; die aufrufer entscheiden ueber retry oder fehler.
            if not saw_done:
                self._last_stream_truncated = True
                self.logger.warning(
                    "Upstream SSE ended without [DONE] sentinel (incomplete_read=%s) — treating turn as truncated",
                    incomplete_read,
                )

        finally:
            # C-16: verbindung auch bei fruehem abbruch freigeben.
            try:
                response.close()
            except Exception:
                pass
    def _upload_referenced_files(self, messages: list[dict[str, object]]) -> list[dict[str, object]]:
        """C-19: der upload lief bei JEDEM versuch erneut — transient-retry,
        leer-retry und negative follow-up-runde rufen `_open_chat_stream()`
        erneut auf, dieselbe datei wurde also mehrfach hochgeladen
        (bandbreite, upstream-speicher, und der account-failover pro
        upload). Die refs werden deshalb pro request zwischengespeichert."""
        refs: list[dict[str, object]] = []
        # C-19: der cache war client-instanzweit. Gemessen: ein upload von
        # konto 0 wurde fuer den chat von konto 1 wiederverwendet — die
        # `source_id` eines fremden kontos im request des anderen. Der
        # cache gilt jetzt fuer genau EINEN request und wird beim
        # aufbauen dieser refs neu angelegt.
        upload_cache: dict[tuple[str, bool], dict[str, object] | None] = {}
        for message in messages:
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for item in content:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("type")
                if item_type == "image_url":
                    url = _extract_nested_url_value(item.get("image_url"))
                    if isinstance(url, str) and url:
                        ref = self._cached_upload_reference(url, is_image=True, cache=upload_cache)
                        if ref:
                            refs.append(ref)
                elif item_type in {"file", "file_url"}:
                    url = _extract_nested_url_value(item.get("file_url"))
                    if isinstance(url, str) and url:
                        ref = self._cached_upload_reference(url, is_image=False, cache=upload_cache)
                        if ref:
                            refs.append(ref)
        if refs:
            self.logger.info("Attachment upload completed success_count=%s", len(refs))
        return refs

    def _cached_upload_reference(
        self,
        file_url: str,
        is_image: bool,
        cache: dict[tuple[str, bool], dict[str, object] | None] | None = None,
    ) -> dict[str, object] | None:
        """Ein und dieselbe URL wird pro request genau einmal hochgeladen.

        Der cache wird bewusst als ARGUMENT uebergeben und nicht als
        instanzfeld gefuehrt: eine `source_id` gilt nur fuer das konto, das
        sie hochgeladen hat (C-19)."""
        active_cache = self._upload_reference_cache if cache is None else cache
        cache_key = (file_url, is_image)
        if cache_key in active_cache:
            return active_cache[cache_key]
        ref = self._upload_file_reference(file_url, is_image=is_image)
        # Bounded: ein request kann viele attachments haben, aber der cache
        # darf nicht unbegrenzt wachsen.
        if len(active_cache) >= _UPLOAD_CACHE_MAX_ENTRIES:
            active_cache.clear()
        active_cache[cache_key] = ref
        return ref

    def _upload_file_reference(self, file_url: str, is_image: bool) -> dict[str, object] | None:
        try:
            filename, mime_type, payload = self._fetch_file_payload(file_url)
            boundary = _make_boundary()
            body = self._build_multipart(boundary, filename, mime_type, payload)
            upload_url = f"{self.config.glm_base_url}{FILE_UPLOAD_URL_SUFFIX}"
            debug_dump(
                self.logger,
                self.config.debug_dump_all,
                f"Preparing attachment upload url={file_url} filename={filename} mime={mime_type}",
                {"filename": filename, "mime_type": mime_type, "bytes": len(payload)},
            )

            def send_request(account_index: int, access_token: str):
                timestamp, nonce, sign = build_sign()
                request = urllib.request.Request(
                    upload_url,
                    method="POST",
                    data=body,
                    headers={
                        **self.auth.get_browser_headers(),
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": f"multipart/form-data; boundary={boundary}",
                        "Referer": "https://chatglm.cn/",
                        "X-Device-Id": uuid.uuid4().hex,
                        "X-Nonce": nonce,
                        "X-Request-Id": uuid.uuid4().hex,
                        "X-Sign": sign,
                        "X-Timestamp": timestamp,
                    },
                )
                debug_dump(
                    self.logger,
                    self.config.debug_dump_all,
                    f"file_upload request headers forwarded to GLM account={account_index}",
                    dict(request.header_items()),
                )
                debug_dump(
                    self.logger,
                    self.config.debug_dump_all,
                    f"Raw file_upload request body forwarded to GLM account={account_index}",
                    body,
                )
                return urllib.request.urlopen(request, timeout=self.config.request_timeout)

            with self._call_with_account_failover("file_upload", send_request) as response: # type: ignore
                result = self.auth.read_json_response(response).get("result", {})
            debug_dump(self.logger, self.config.debug_dump_all, "GLM file upload response result", result)
            source_id = result.get("source_id") # type: ignore
            file_result_url = result.get("file_url", file_url) # type: ignore
            if not source_id:
                return None
            if is_image:
                return {"type": "image_url", "image_url": {"url": file_result_url or source_id}}
            return {"type": "file", "file": [{"source_id": source_id, "file_url": file_result_url}]}
        except Exception as exc:
            self.logger.warning("Attachment upload failed url=%s error=%s", file_url, exc)
            return None

    def _assert_public_url(self, file_url: str) -> None:
        """C-02/SSRF: nur öffentliches http(s) zulassen. Vor dem Abruf wird
        das Ziel aufgelöst und gegen private, reservierte und
        Cloud-Metadata-Adressen geprüft — nach jedem Redirect erneut."""
        parsed = urllib.parse.urlparse(file_url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError(f"Unsupported attachment URL scheme: {parsed.scheme!r}")
        host = parsed.hostname
        if not host:
            raise ValueError("Attachment URL without host")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        for info in socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP):
            ip = info[4][0]
            try:
                address = ipaddress.ip_address(ip)
            except ValueError:
                continue
            if (
                address.is_private
                or address.is_loopback
                or address.is_link_local
                or address.is_multicast
                or address.is_reserved
                or address.is_unspecified
            ):
                raise ValueError(f"Attachment URL resolves to a non-public address: {ip}")

    def _fetch_file_payload(self, file_url: str) -> tuple[str, str, bytes]:
        if file_url.startswith("data:"):
            header, encoded = file_url.split(",", 1)
            mime_type = header.split(";")[0][5:] or "application/octet-stream"
            extension = mimetypes.guess_extension(mime_type) or ".bin"
            if len(encoded) > FILE_SIZE_LIMIT * 4 // 3:
                raise ValueError("Data-URL attachment exceeds the size limit, upload rejected.")
            payload = base64.b64decode(encoded, validate=True)
            if len(payload) > FILE_SIZE_LIMIT:
                raise ValueError("Data-URL attachment exceeds the size limit, upload rejected.")
            return f"upload-{uuid.uuid4().hex}{extension}", mime_type, payload

        self._assert_public_url(file_url)
        parsed = urllib.parse.urlparse(file_url)
        filename = parsed.path.rsplit("/", 1)[-1] or f"upload-{uuid.uuid4().hex}.bin"

        check_url = self._assert_public_url

        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                check_url(newurl)
                return super().redirect_request(req, fp, code, msg, headers, newurl)

        opener = urllib.request.build_opener(_NoRedirect)
        with opener.open(file_url, timeout=self.config.request_timeout) as response:
            payload = response.read(FILE_SIZE_LIMIT + 1)
            if len(payload) > FILE_SIZE_LIMIT:
                raise ValueError("File exceeds 100MB, upload rejected.")
            mime_type = response.headers.get_content_type()
        mime_type = mime_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return filename, mime_type, payload

    def _build_multipart(self, boundary: str, filename: str, mime_type: str, payload: bytes) -> bytes:
        start = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode("utf-8")
        end = f"\r\n--{boundary}--\r\n".encode("utf-8")
        return start + payload + end

    def _wrap_stream_response(self, response):
        content_encoding = response.headers.get("Content-Encoding", "").lower()
        if content_encoding == "gzip":
            # C-16: GzipFile.close() schliesst ein extern uebergebenes
            # fileobj NICHT. Der wrapper besitzt den raw-response deshalb
            # mit und schliesst beides.
            raw_response = response

            class _GzipStreamOwner(BufferedReader):
                def close(self) -> None:
                    try:
                        super().close()
                    finally:
                        try:
                            raw_response.close()
                        except Exception:
                            pass

            return _GzipStreamOwner(gzip.GzipFile(fileobj=raw_response))
        return response

    def _read_error_payload(self, error: urllib.error.HTTPError) -> dict[str, object]:
        # C-20: der fehler-body war unbegrenzt (`error.read()`) und wurde
        # bei gzip ohne dekompressionslimit entpackt. Ein fehlerhaftes oder
        # boesartiges upstream kann damit speicher und cpu erschoepfen.
        # Begrenzt lesen und die dekompression ebenfalls begrenzen.
        try:
            raw_body = error.read(ERROR_BODY_MAX_BYTES + 1)
            if len(raw_body) > ERROR_BODY_MAX_BYTES:
                self.logger.warning(
                    "Upstream error body exceeds %s bytes — truncated for diagnostics",
                    ERROR_BODY_MAX_BYTES,
                )
                raw_body = raw_body[:ERROR_BODY_MAX_BYTES]
            content_encoding = error.headers.get("Content-Encoding", "").lower()

            if content_encoding == "gzip":
                # NUR die dekomprimierte Ausgabe begrenzen: ein gzip-bomb
                # mit kleinem body und riesiger ausgabe wird abgeschnitten
                # statt den speicher zu fressen.
                decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
                raw_body = decompressor.decompress(raw_body, ERROR_BODY_MAX_BYTES)

            text = raw_body.decode("utf-8", errors="ignore")
        except Exception as exc:
            return {"message": f"Failed to read upstream error response: {type(exc).__name__}"}
        try:
            payload = json.loads(text)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass
        return {"message": text}

    def _request_deadline(self) -> float | None:
        """S-14: absolute grenze fuer die gesamte requestlaufzeit."""
        total = float(getattr(self.config, "glm_request_deadline_seconds", 0.0) or 0.0)
        if total <= 0:
            return None
        return time.monotonic() + total

    @staticmethod
    def _deadline_exceeded(deadline: float | None) -> bool:
        return deadline is not None and time.monotonic() >= deadline

    def _busy_backoff_seconds(self, attempt: int) -> float:
        """S-14: exponentiell mit jitter, gedeckelt.

        `glm_busy_retry_interval` ist die basis. Jeder weitere versuch
        verdoppelt (bis zum vierfachen der basis), plus bis zu 50 %
        jitter nach oben und 10 % nach unten — damit sich mehrere clienten nicht
        synchron wieder auf dasselbe fenster stauen."""
        base = max(0.1, float(self.config.glm_busy_retry_interval))
        backoff = min(base * (2 ** min(attempt, 3)), base * 4)
        return backoff * random.uniform(0.9, 1.5)

    def _rate_limit_backoff_seconds(self, attempt: int) -> float:
        """F-6: ratelimit braucht sekunden->minuten, nicht sekunden.

        `glm_rate_limit_retry_interval` ist die basis (standard 30s), jeder
        weitere versuch verdoppelt, gedeckelt beim achtfachen. Bewusst KEIN
        jitter nach unten: bei einer drosselung ist gleichzeitiges Aufwachen
        mehrerer clients genau das, was die sperre am laufen haelt. 10 %
        jitter nach oben entzerrt nur, ohne die drosselung zu fuettern."""
        base = max(1.0, float(self.config.glm_rate_limit_retry_interval))
        backoff = min(base * (2 ** max(0, attempt - 1)), base * 8)
        return backoff * random.uniform(1.0, 1.1)

    def _build_error_message(self, status_code: int, payload: dict[str, object]) -> str:
        message = str(payload.get("message", "")).strip()
        inner_status = payload.get("status")
        rid = payload.get("rid")
        parts = [f"GLM request failed HTTP {status_code}"]
        if inner_status is not None:
            parts.append(f"status={inner_status}")
        if message:
            parts.append(message)
        if rid:
            parts.append(f"rid={rid}")
        return " | ".join(parts)

    def _get_preferred_account_index(self, ticket: int) -> int | None:
        get_registered = getattr(self.auth, "get_registered_account_indices", None)
        if callable(get_registered):
            registered = get_registered()
            if isinstance(registered, list) and registered:
                return registered[ticket % len(registered)]
        account_count = self.auth.get_account_count()
        if account_count <= 0:
            return None
        return ticket % account_count

    def _call_with_account_failover(
        self,
        request_name: str,
        operation: Callable[[int, str], object],
        preferred_account_index: int | None = None,
    ):
        account_count = self.auth.get_account_count()
        if account_count <= 0:
            raise RuntimeError("No usable GLM account or guest token configured")
        start_index = preferred_account_index % account_count if preferred_account_index is not None else self.auth.get_current_account_index()
        last_exc: Exception | None = None

        for offset in range(account_count):
            account_index = (start_index + offset) % account_count
            guest_retry_limit = self.config.glm_guest_max_retries if self.auth.is_guest_account(account_index) else 0
            for attempt in range(guest_retry_limit + 1):
                try:
                    access_token = self.auth.get_access_token_for_account(account_index)
                    return operation(account_index, access_token)
                except Exception as exc:
                    last_exc = exc
                    should_switch = self.auth.should_switch_account(exc)
                    if should_switch:
                        self.auth.invalidate_account(account_index)
                    if should_switch and attempt < guest_retry_limit:
                        self.logger.warning(
                            "Guest account request failed, re-obtaining guest ck and retrying attempt=%s/%s request=%s account=%s error=%s",
                            attempt + 1,
                            guest_retry_limit,
                            request_name,
                            account_index,
                            exc,
                        )
                        continue
                    if not should_switch or account_count == 1:
                        raise
                    self.auth.advance_account(account_index, f"{request_name}: {exc}")
                    break

        self.auth.reset_account_cycle()
        if last_exc is not None:
            raise last_exc
        raise RuntimeError(f"Account rotation failed: {request_name}")
