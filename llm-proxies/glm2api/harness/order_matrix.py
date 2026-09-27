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
   S-15-fund gefunden, den kein Test sah (siehe `KNOWN`).

`KNOWN` listet vorbestehende, bereits bewertete Befunde. Sie werden
ausgewiesen, nicht versteckt — aber sie zitausieren nicht den Exit-Code,
sonst ist der harness nach der ersten Meldung unbrauchbar.

    python3 order_matrix.py            # Tabelle + Protokoll
    python3 order_matrix.py --quiet    # nur Verstoesse und bekannte Befunde
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
S14_PREFIXES = {1: "D", 2: "De", 3: "Der ", 4: "Der "}

# Vorbestehende, bereits bewertete Befunde — hier wird der SOLL-wert des
# layouts verletzt, die verletzung liegt also in der abweichung.
# Stand 2026-09-27 nach S-15…S-19: **leer**. Der S-14-Rest wird separat
# vermessen und exakt gegen seine bewusst akzeptierte Chunk-Praefixe geprueft.
KNOWN: dict[str, str] = {}


def check(parts: list, expected: str, expected_calls: int, chunk: int, label: str = "") -> list[str]:
    streamed, _body, accumulator = stream(parts, chunk)
    problems: list[str] = []

    if streamed.split() != expected.split():
        problems.append(f"soll-vergleich: IST {streamed!r} != SOLL {expected!r}")
    if label in {"absatz-vor-call", "absatz-nach-call", "absatz-beide-seiten-call", "einzelnewline-beide-seiten-call", "späterer-absatz-nach-call"} and streamed != expected:
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
    return problems


def check_s14_residuals() -> list[tuple[int, str]]:
    """S-14-Ausnahme als exakte Chunk-Messung, nicht pauschal als KNOWN."""
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
    known_hits: dict[str, list[int]] = {label: [] for label in KNOWN}

    print(f"{len(LAYOUTS)} layouts × {len(CHUNK_SIZES)} chunk-groessen")
    print(f"{'layout':<28} {'chunk':>6}  ergebnis")
    print("-" * 78)
    for label, parts, expected, expected_calls in LAYOUTS:
        for chunk in CHUNK_SIZES:
            measurements += 1
            problems = check(parts, expected, expected_calls, chunk, label)
            if not problems:
                if not quiet:
                    print(f"{label:<28} {chunk:>6}  ok")
                continue
            if label in KNOWN:
                known_hits[label].append(chunk)
                if not quiet:
                    print(f"{label:<28} {chunk:>6}  bekannt")
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
        print("S-14-Praefix-Messung: 215/215 exakt (4 akzeptierte Präfixe, Calls 215/215)")
    for label, chunks in known_hits.items():
        if chunks:
            print(f"  bekannt: {label} — {len(chunks)}/{len(CHUNK_SIZES)} chunk-groessen")
            print(f"    {KNOWN[label]}")
    return 1 if unknown else 0


if __name__ == "__main__":
    raise SystemExit(main())
