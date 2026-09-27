"""sweep2: der breite Vertrags-Sweep. Szenarien × Pfade × Chunk-Groessen.

Anders als `order_matrix` (das die Reihenfolge-Invariante misst) prüft
dieser Sweep den *Vertrag* beider Pfade:

- **Stream:** was der Client als laufende assistant-nachricht sieht.
- **Non-Stream:** was `build_response()` in den Body schreibt.

Das Szenario `selbst-steuerung+nur-text` pinnt die S-08-Politik: ohne
Werkzeug-Aufrufe ist eine Selbst-Steuerungsaussage Inhalt und bleibt sowohl
im Stream als auch im Body erhalten. Am Vorher-Stand `02ceca2` ebenfalls
grün (6/6) — dies ist eine bewusst dokumentierte Erwartung, kein Fix.

Der wichtigste Vertrag ist S-13: bei Tool-Calls ist `message.content`
`None` (Option B, bewusst entschieden), der Text geht über den Stream.
Der zweite ist T-06: ein Aufruf ohne Pflichtargument ist `error`, nicht
`stop` mit leerem Inhalt.

Jedes Szenario nennt seine Erwartung ausdrücklich. Sie stammen aus den
gepinnten Tests, nicht aus dem, was der Proxy gerade tut — ein Sweep, der
nur aufzählt, ist eine sehr teure Kopie der Testsuite.

`KNOWN` listet offene, bewusst akzeptierte Befunde. S-15…S-18 sind behoben;
übrig bleibt eine bewusst akzeptierte S-14-Grenze. Sie wird ausgewiesen, nicht
versteckt, zitiert aber nicht den Exit-Code.

    python3 sweep2.py            # Tabelle + Protokoll
    python3 sweep2.py --quiet    # nur Verstoesse
"""

from __future__ import annotations

import sys

from common import native_event, stream

READ = {"read", "bash"}
READ_ONLY = {"read"}

PROSE = "Der Bericht nennt drei Punkte."
ANSWER = "Die Datei enthaelt drei Zeilen."
FENCED = "Hier der Aufruf:\n```bash\nls -la\n```\nDann weiter."

CALL = native_event("c1")
CALL2 = native_event("c2", name="bash", filePath="/b.sh", command="ls")
DSML = (
    "<|DSML|tool_calls><|DSML|invoke name=\"read\">"
    "<|DSML|parameter name=\"filePath\"><![CDATA[/etc/hostname]]></|DSML|parameter>"
    "</|DSML|invoke></|DSML|tool_calls>"
)
UNUSABLE = native_event("c3", name="read", filePath=None)

# label, parts, allowed, erwarteter stream, erwartete aufrufe, finish_reason,
# erwarteter body-content
SCENARIOS: list[tuple[str, list, set, str, list[str], str, str | None]] = [
    # --- prosa und aufruf (S-10/S-13) -------------------------------------
    ("prosa+call", [PROSE, CALL], READ, PROSE, ["read"], "tool_calls", None),
    ("call+prosa", [CALL, PROSE], READ, PROSE, ["read"], "tool_calls", None),
    ("prosa+call+call", [PROSE, CALL, CALL2], READ, PROSE, ["read", "bash"], "tool_calls", None),
    # --- praeambel (T-07/S-10): wird verworfen, der rest nicht -----------
    ("praeambel-de+call", ["Ich lese die Datei jetzt.", CALL], READ, "", ["read"], "tool_calls", None),
    ("praeambel-en+call", ["I'll now read the file.", CALL], READ, "", ["read"], "tool_calls", None),
    # die chinesische praeambel ist nur GEPINNT, wenn sie im selben part
    # steht wie das DSML (`test_accumulator_drops_tool_preamble_…`). In
    # einem eigenen part kennt kein muster sie — sie wird gestreamt. Der
    # wortrest, der bis S-15 noch davor entkam ('D'/'De'/'Der'), faellt
    # seit der filterkette in `strip_turn_start_narration` mit.
    ("praeambel-cn-eigener-part", ["我将创建文件。\n\n", CALL], READ, "我将创建文件。\n\n", ["read"], "tool_calls", None),
    ("praeambel+call+prosa", ["Ich lese die Datei jetzt.", CALL, PROSE], READ, PROSE, ["read"], "tool_calls", None),
    # --- selbst-steuerung (S-08/S-09) ------------------------------------
    ("selbst-steuerung+call", ["Der `open`-Tool-Aufruf funktioniert hier nicht, ich nutze `read`.", CALL], READ, "", ["read"], "tool_calls", None),
    ("selbst-steuerung-mittelteil", ["Der Bericht ist da. Ich nutze jetzt `read` fuer den Rest.", CALL], READ, "Der Bericht ist da.", ["read"], "tool_calls", None),
    ("limit-erfunden+nur-text", ["Tool-Limit erreicht — hier die Analyse."], READ, "", [], "stop", None),
    # Luecke B (2026-09-27): S-08-Politik — im reinen Text-Turn ist die
    # selbst-steuerung bewusst Inhalt. Ohne Calls darf der Filter nicht
    # die technische Aussage ueber `open` entfernen. Stream und Body werden
    # beide gegen den vollstaendigen Text geprueft.
    ("selbst-steuerung+nur-text", ["Der `open`-Aufruf funktioniert hier nicht, ich nutze `read`."], READ, "Der `open`-Aufruf funktioniert hier nicht, ich nutze `read`.", [], "stop", "Der `open`-Aufruf funktioniert hier nicht, ich nutze `read`."),
    # --- protokoll-meta (S-07) -------------------------------------------
    ("protokoll-meta+call", ["Wrong tool calls above — correcting to `read`.", CALL], READ, "", ["read"], "tool_calls", None),
    # --- fences und leerraum (S-05/S-06/S-10) ----------------------------
    ("fence+call", [FENCED, CALL], READ, FENCED, ["read"], "tool_calls", None),
    ("leerraum+call", ["  \n  ", CALL], READ, "", ["read"], "tool_calls", None),
    ("prosa+leerraum+call+prosa", [PROSE, "  \n  ", CALL, ANSWER], READ, PROSE + "  \n  " + ANSWER, ["read"], "tool_calls", None),
    # --- aufruf-protokoll -------------------------------------------------
    ("json-protokoll+call", ['{"tool_calls":[{"name":"read","arguments":{"filePath":"/a.py"}}]}', CALL], READ, "", ["read", "read"], "tool_calls", None),
    ("dsml-aufruf+prosa", [DSML, PROSE], READ_ONLY, PROSE, ["read"], "tool_calls", None),
    # S-18: DSML ueber viele parts zerschnitten — der aufruf muss ankommen
    # und das markup darf nicht in den stream lecken
    ("dsml-ueber-viele-parts", ["我将创建文件。\n\n", DSML], READ_ONLY, "我将创建文件。\n\n", ["read"], "tool_calls", None),
    ("unbrauchbarer-aufruf", [UNUSABLE], READ, "", [], "error", None),
    ("unbrauchbarer-aufruf-hinter-prosa", [PROSE, UNUSABLE], READ, PROSE, [], "error", PROSE),
    # --- nur text (S-13 gegenrichtung) -----------------------------------
    ("nur-prosa", [PROSE], READ, PROSE, [], "stop", PROSE),
    ("nur-prosa-zwei-teile", [PROSE, ANSWER], READ, PROSE + "\n\n" + ANSWER, [], "stop", PROSE + "\n\n" + ANSWER),
    ("nur-fence", [FENCED], READ, FENCED, [], "stop", FENCED),
]

CHUNK_SIZES = (1, 3, 7, 13, 29, 10_000)

# Vorbestehende, am 2026-09-27 gefundene und noch nicht behobene Befunde.
# Stand nach S-15…S-18: **ein** eintrag uebrig. Die anderen fuenf sind
# behoben und deshalb aus der tabelle gestrichen — ein `KNOWN`-eintrag fuer
# ein sauberes szenario waere eine luege, die den harness unbrauchbar macht
# (er zaehlt die treffer ja selbst mit). Die messungen, die die befunde
# belegt haben, stehen in optimierung.md.
KNOWN: dict[str, str] = {
    "selbst-steuerung+call": (
        "S-14 (bewusst akzeptiert, nicht S-15): nur der wortrest vor der "
        "ersten werkzeug-marke entkommt. Die selbst-steuerung steht hier am "
        "ANFANG des turns, es gibt also keinen fertigen satz davor, den "
        "S-15 retten koennte — der rest ist der erste teil des ersten "
        "satzes der narration."
    ),
}


def check(label, parts, allowed, expect_stream, expect_calls, expect_finish, expect_body, chunk):
    streamed, body, accumulator = stream(parts, chunk, allowed=allowed)
    problems: list[str] = []
    message = accumulator.build_response("finish")["choices"][0]["message"]
    finish = message.get("finish_reason") or (
        accumulator.build_response("finish")["choices"][0].get("finish_reason")
    )
    names = [entry["function"]["name"] for entry in (message.get("tool_calls") or [])]

    if streamed.split() != expect_stream.split():
        problems.append(f"stream: IST {streamed!r} != SOLL {expect_stream!r}")
    if names != expect_calls:
        problems.append(f"aufrufe: IST {names} != SOLL {expect_calls}")
    if finish != expect_finish:
        problems.append(f"finish_reason: IST {finish!r} != SOLL {expect_finish!r}")
    if (message.get("content") or "") != (expect_body or ""):
        problems.append(
            f"body: IST {message.get('content')!r} != SOLL {expect_body!r}"
        )
    return problems


def main() -> int:
    quiet = "--quiet" in sys.argv
    measurements = 0
    violations = 0
    known_hits: dict[str, list[int]] = {label: [] for label in KNOWN}
    print(f"{len(SCENARIOS)} szenarien × {len(CHUNK_SIZES)} chunk-groessen")
    print(f"{'szenario':<30} {'chunk':>6}  ergebnis")
    print("-" * 78)
    for label, parts, allowed, expect_stream, expect_calls, expect_finish, expect_body in SCENARIOS:
        for chunk in CHUNK_SIZES:
            measurements += 1
            problems = check(
                label, parts, allowed, expect_stream, expect_calls,
                expect_finish, expect_body, chunk,
            )
            if problems:
                if label in KNOWN:
                    known_hits[label].append(chunk)
                    if not quiet:
                        print(f"{label:<30} {chunk:>6}  bekannt")
                    continue
                violations += 1
                print(f"{label:<30} {chunk:>6}  VERSTOSS")
                for problem in problems:
                    print(f"{'':<37} - {problem}")
            elif not quiet:
                print(f"{label:<30} {chunk:>6}  ok")
    print("-" * 78)
    print(f"Messungen: {measurements}, unbekannte Verstoesse: {violations}")
    for label, chunks in known_hits.items():
        if chunks:
            print(f"  bekannt: {label} — {len(chunks)}/{len(CHUNK_SIZES)} chunk-groessen")
            print(f"    {KNOWN[label]}")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
