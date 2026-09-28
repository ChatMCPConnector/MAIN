"""order_matrix: Reihenfolge-Invariante der nativen Parts, gemessen ueber
Text/Call-Layouts × Chunk-Groessen.

Zwei Pruefungen je Fall, und die zweite ist die wertvollere:

1. **Soll-Vergleich.** Der sichtbare Stream muss genau der im Layout
   hinterlegten Erwartung entsprechen. Die Erwartungen sind aus den
   gepinnten Tests abgeleitet (S-05 `_S05_TEXTS`, S-10 `_S10_PROSE_*`),
   plus der S-11-Regel: zwischen zwei GETRENNTEN text-parts setzt der
   part-merge einen absatzumbruch — nicht zu verwechseln mit dem
   S-06-leerzeilen-artefakt, das zwischen zwei sichtbaren wörtern
   erhalten bleibt.
2. **Chunk-Invariante.** Alle Chunk-Groessen muessen denselben Text
   ergeben. Das ist die eigentliche Invariante: der Client darf nicht
   davon abhaengen, wo der upstream schneidet. Diese Pruefung braucht
   keine handgeschriebene Erwartung und hat deshalb 2026-09-27 den
   S-15-fund gefunden, den kein Test sah.

Die aktuell akzeptierten Whitespace-Outputs sind pro Layout und
Chunkgroesse exakt hinterlegt. Alle anderen Abweichungen (einschliesslich
Call-Zahl und Protokollfehlern) bleiben unbekannt und schlagen fehl.

    python3 order_matrix.py            # Tabelle + Protokoll
    python3 order_matrix.py --quiet    # Zusammenfassung und Verstoesse
"""

from __future__ import annotations

import sys

from common import ALLOWED, NARRATION, native_event, stream

PROSE_A = "Der Bericht nennt drei Punkte."
PROSE_B = "Zweiter Absatz mit Erklaerung."
PROSE_C = "Dritter Absatz schliesst ab."
PREAMBLE = "Ich lese die Datei jetzt."  # T-07: wird im aufruf-turn verworfen
FENCED = "Hier der Aufruf:\n```bash\nls -la\n```\nDann weiter."
SPACE = "Der Bericht ist fuer Sie. Ich"  # S-10: der rand-links des carries
# S-15: der sichtbare anteil ist der fertige satz. `Ich` ist ein
# praeambel-Anfang und faellt als eigener satz — vor S-15 ging der ganze
# text verloren (chunk 1000: ''), jetzt bleibt der echte satz.
SPACE_ERWARTET = "Der Bericht ist fuer Sie."
WS = "  \n  "  # S-06: leerraum zwischen zwei sichtbaren werten bleibt
PARA = "\n\n"  # S-11: absatzumbruch zwischen zwei getrennten text-parts


def call(logic_id="c1", name="read", path="/a.py"):
    return native_event(logic_id, name=name, filePath=path)


# (label, parts, erwarteter sichtbarer text, erwartete anzahl calls)
LAYOUTS: list[tuple[str, list, str, int]] = [
    ("prose-vor-call", [PROSE_A, call()], PROSE_A, 1),
    ("call-dann-prose", [call(), PROSE_A], PROSE_A, 1),
    ("prose-call-prose", [PROSE_A, call(), PROSE_B], PROSE_A + PARA + PROSE_B, 1),
    ("call-prose-call", [call("c1"), PROSE_A, call("c2")], PROSE_A, 2),
    ("prose-call-call-prose", [PROSE_A, call("c1"), call("c2"), PROSE_B], PROSE_A + PARA + PROSE_B, 2),
    ("prose-call-prose-call-prose", [PROSE_A, call("c1"), PROSE_B, call("c2"), PROSE_C], PROSE_A + PARA + PROSE_B + PARA + PROSE_C, 2),
    ("praeambel-wird-verworfen", [PREAMBLE, call()], "", 1),
    ("praeambel-call-prose", [PREAMBLE, call(), PROSE_B], PARA + PROSE_B, 1),
    ("gefencet-vor-call", [FENCED, call()], FENCED, 1),
    ("rand-links-im-carry", [SPACE, call()], SPACE_ERWARTET, 1),
    ("leerraum-artefakt", [PROSE_A, WS, call(), PROSE_B], PROSE_A + WS + PROSE_B, 1),
    ("nur-prosa-ohne-call", [PROSE_A, PROSE_B], PROSE_A + PARA + PROSE_B, 0),
    # Absatztrenner direkt vor einem Call: exakt einmal sichtbar erhalten.
    ("absatz-vor-call", [PROSE_A, PARA, call(), PROSE_B], PROSE_A + PARA + PROSE_B, 1),
    # Spiegel: Absatztrenner direkt nach einem Call.
    ("absatz-nach-call", [PROSE_A, call(), PARA, PROSE_B], PROSE_A + PARA + PROSE_B, 1),
    # S-19: explizite Trenner auf beiden Seiten eines unsichtbaren Calls
    # muessen EINEN Absatzwechsel bilden, keine vier Newlines.
    ("absatz-beide-seiten-call", [PROSE_A, PARA, call(), PARA, PROSE_B], PROSE_A + PARA + PROSE_B, 1),
    ("einzelnewline-beide-seiten-call", [PROSE_A, "\n", call(), "\n", PROSE_B], PROSE_A + PARA + PROSE_B, 1),
    # Gegenprobe: späterer Absatz nach sichtbarer Folgeprosa bleibt Absatz 2.
    ("späterer-absatz-nach-call", [PROSE_A, PARA, call(), PARA, PROSE_B, PARA, PROSE_C], PROSE_A + PARA + PROSE_B + PARA + PROSE_C, 1),
]

CHUNK_SIZES = (1, 2, 3, 5, 7, 8, 11, 13, 20, 1000)
S14_PREFIXES: dict[int, str] = {}

# Das Layout liefert je nach Chunkgrenze exakt bekannte Rand-Whitespace-
# Varianten. Ein dritter Output oder ein zusätzlicher Call-/Protokollfehler
# bleibt unbekannt und schlägt fehl.
KNOWN_CHUNK_OUTPUTS: dict[str, dict[int, str]] = {
    "rand-links-im-carry": {
        1: "Der Bericht ist fuer Sie. ",
        2: "Der Bericht ist fuer Sie. ",
        3: "Der Bericht ist fuer Sie. ",
        5: "Der Bericht ist fuer Sie. ",
        7: "Der Bericht ist fuer Sie.",
        8: "Der Bericht ist fuer Sie. ",
        11: "Der Bericht ist fuer Sie.",
        13: "Der Bericht ist fuer Sie. ",
        20: "Der Bericht ist fuer Sie.",
        1000: "Der Bericht ist fuer Sie.",
    },
}


def check(
    parts: list,
    expected: str,
    expected_calls: int,
    chunk: int,
    label: str = "",
    *,
    expected_stream: str | None = None,
) -> tuple[str, list[str]]:
    streamed, _body, accumulator = stream(parts, chunk)
    problems: list[str] = []

    if streamed != expected:
        problems.append(f"soll-exakt: IST {streamed!r} != SOLL {expected!r}")
    if label in KNOWN_CHUNK_OUTPUTS and streamed != KNOWN_CHUNK_OUTPUTS[label].get(chunk):
        problems.append(f"chunk-output-unbekannt: IST {streamed!r}")
    if expected_stream is not None and streamed != expected_stream:
        problems.append(
            f"chunk-invariante: IST {streamed!r} != REFERENZ {expected_stream!r}"
        )
    if label in {
        "absatz-vor-call",
        "absatz-nach-call",
        "absatz-beide-seiten-call",
        "einzelnewline-beide-seiten-call",
        "späterer-absatz-nach-call",
    } and streamed != expected:
        # Bei diesen Layouts ist Whitespace Teil des Vertrags —
        # der Absatztrenner muss vor UND nach dem Call genau einmal erhalten
        # bleiben. Der allgemeine Vergleich normalisiert sonst Leerraum.
        problems.append(f"absatz-exakt: IST {streamed!r} != SOLL {expected!r}")
    if "\n\n\n" in streamed:
        problems.append(f"leerzeilen-artefakt im stream: {streamed!r}")

    message = accumulator.build_response()["choices"][0]["message"]
    calls = message.get("tool_calls") or []
    if len(calls) != expected_calls:
        problems.append(
            f"{len(calls)} aufrufe, erwartet {expected_calls}: "
            f"{[entry['function']['name'] for entry in calls]}"
        )
    for entry in calls:
        if not (entry.get("function") or {}).get("arguments"):
            problems.append(f"aufruf ohne argumente: {entry}")
    return streamed, problems


def check_s14_residuals() -> list[tuple[int, str]]:
    """Prueft den S-14-Stream ueber alle Chunkgroessen auf leeren Text."""
    failures = []
    for chunk in range(1, len(NARRATION) + 1):
        streamed, _body, accumulator = stream(
            [NARRATION, call()], chunk, allowed=ALLOWED
        )
        expected = S14_PREFIXES.get(chunk, "")
        if streamed != expected:
            failures.append((chunk, streamed))
        calls = accumulator.build_response()["choices"][0]["message"].get("tool_calls") or []
        if len(calls) != 1:
            failures.append((chunk, f"call-count={len(calls)}"))
    return failures


def main() -> int:
    quiet = "--quiet" in sys.argv
    measurements = 0
    unknown = 0
    known_chunk_hits: dict[str, list[int]] = {
        label: [] for label in KNOWN_CHUNK_OUTPUTS
    }

    print(f"{len(LAYOUTS)} layouts × {len(CHUNK_SIZES)} chunk-groessen")
    print(f"{'layout':<28} {'chunk':>6}  ergebnis")
    print("-" * 78)
    for label, parts, expected, expected_calls in LAYOUTS:
        reference_stream: str | None = None
        for chunk in CHUNK_SIZES:
            measurements += 1
            streamed, problems = check(
                parts,
                expected,
                expected_calls,
                chunk,
                label,
                expected_stream=reference_stream,
            )
            if reference_stream is None:
                reference_stream = streamed
            whitespace_problems = [
                problem
                for problem in problems
                if problem.startswith(("soll-exakt:", "chunk-invariante:"))
            ]
            other_problems = [
                problem for problem in problems if problem not in whitespace_problems
            ]
            known_chunk_output = (
                label in KNOWN_CHUNK_OUTPUTS
                and streamed == KNOWN_CHUNK_OUTPUTS[label].get(chunk)
                and bool(whitespace_problems)
                and not other_problems
            )
            if (
                label in KNOWN_CHUNK_OUTPUTS
                and streamed != KNOWN_CHUNK_OUTPUTS[label].get(chunk)
                and not any(
                    problem.startswith("chunk-output-unbekannt:")
                    for problem in problems
                )
            ):
                problems.append(f"chunk-output-unbekannt: {streamed!r}")
            known_chunk_variation = (
                known_chunk_output
                and reference_stream is not None
                and streamed != reference_stream
            )
            if known_chunk_output:
                problems = other_problems
                if known_chunk_variation:
                    known_chunk_hits[label].append(chunk)
            if not problems:
                if not quiet:
                    result = "bekannt" if known_chunk_variation else "ok"
                    print(f"{label:<28} {chunk:>6}  {result}")
                continue
            unknown += 1
            print(f"{label:<28} {chunk:>6}  VERSTOSS")
            for problem in problems:
                print(f"{'':<37} - {problem}")
    print("-" * 78)
    print(f"Messungen: {measurements}, unbekannte Verstoesse: {unknown}")
    residual_failures = check_s14_residuals()
    if residual_failures:
        print(f"S-14-Praefix-Messung: {len(residual_failures)} Abweichungen")
        for chunk, actual in residual_failures[:10]:
            print(f"  chunk={chunk}: {actual!r}")
        unknown += len(residual_failures)
    else:
        print(f"S-14-Narrationsmessung: {len(NARRATION)}/{len(NARRATION)} ohne Rest, Calls exakt")
    for label, chunks in known_chunk_hits.items():
        if chunks:
            print(
                f"  bekannte chunk-variante: {label} — "
                f"{len(chunks)}/{len(CHUNK_SIZES)} abweichende chunk-groessen"
            )
            print(
                "    exakt akzeptierte Chunk-Outputs: "
                f"{KNOWN_CHUNK_OUTPUTS[label]}"
            )
    return 1 if unknown else 0


if __name__ == "__main__":
    raise SystemExit(main())
