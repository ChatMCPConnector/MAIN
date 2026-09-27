# Mess-Harnesses (`harness/`)

Skripte, mit denen Verhalten des Translators **gemessen** wurde, bevor es
geändert wurde. Sie sind keine Tests — die pinnen den Zustand als
`tests/test_translator.py` (S-10 … S-18). Der Unterschied: ein Harness
misst über *alle* Chunkgrößen (Schnittkante des Upstreams) und liefert ein
Protokoll zum Nachlesen; ein Test pinnt eine Aussage.

Bis 2026-09-27 lagen diese Skripte nur unter `/tmp/glmtest/` und waren nach
dem Codespace-Neustart weg — die Messbasis der S-10…S-13-Arbeit war damit
nicht reproduzierbar. Deshalb liegen sie hier.

## Aufruf

```bash
cd llm-proxies/glm2api
.venv/bin/python3 harness/leak_probe.py            # S-14: Narration-Leak
.venv/bin/python3 harness/leak_probe.py --short    # nur die Zeilen mit Befund
.venv/bin/python3 harness/order_matrix.py --quiet  # Reihenfolge-Invariante
.venv/bin/python3 harness/sweep2.py --quiet        # Vertrags-Sweep beider Pfade
.venv/bin/python3 harness/trace_stream.py s09 7    # Delta-für-Delta-Trace
```

`trace_stream.py <preset> <chunk>`: `preamble`, `fence`, `s09`, `s14`, oder
`eigen:<text>` (mit `\n` für Umbruch). Gibt je Delta Carry, S-05-Puffer,
`tool_parser.pending_text` und den wirklich rausgehenden SSE-Text aus.

## Positivkontrolle (Pflicht)

Ein Harness-Bug sieht aus wie ein Proxy-Bug — in dieser Session waren es
drei Stück. Vor jeder "gemessenen" Änderung gehört daher dieselbe Messung
gegen den Vorzustand gefahren:

```bash
git worktree add -f /workspaces/wt-x <commit-vor-der-aenderung>
GLM_SRC=/workspaces/wt-x/llm-proxies/glm2api/src \
  .venv/bin/python3 harness/leak_probe.py --short
git worktree remove --force /workspaces/wt-x
```

Erwartung: das alte Ergebnis ist genau das, was kaputt war. Bleibt die neue
Messung auch dort grün, ist entweder die Messung blind oder der Fix wirkungslos.

## Stand

| Skript | Misst | Stand |
|---|---|---|
| `leak_probe.py` | Narration-Rest, der den Client erreicht, je Chunkgröße 1…215; dazu die Gegenprobe „echter Antworttext mit `` `read` ``/`` `bash` ``/Fence" | 4/215 (nur Wortrest vor der ersten Marke, bewusst so), Antworttext 0/104 verändert |
| `order_matrix.py` | Reihenfolge-Invariante über 12 Text/Call-Layouts × 10 Chunkgrößen: Soll-Vergleich **und** Chunk-Invariante | 120 Messungen, **0** unbekannte Verstöße (vor dem S-15-Fix 4, alle im Layout `rand-links-im-carry`) |
| `sweep2.py` | Vertrags-Sweep: 22 Szenarien × 6 Chunkgrößen, Stream- **und** Non-Stream-Pfad (Text, Aufrufe, `finish_reason`, Body) | 132 Messungen, **0** unbekannte Verstöße, 1 bekannter Befund (S-14-Rest, 2/6) |
| `trace_stream.py` | Delta-für-Delta-Trace, wenn ein Fall unklar ist | Werkzeug, kein Soll |

**Eigenprüfung der Harnesses** (Pflicht, sonst misst man nichts): beide
Sweeps müssen an einem alten Stand **rot** werden. `order_matrix` meldet
an `9054325` 14 unbekannte Verstöße, `sweep2` 7 — dort sind sie grün, wo
sie heute grün sind.

## Bekannte Befunde (im Code als `KNOWN` hinterlegt)

**S-15…S-18 sind behoben** (2026-09-27). Sie standen hier eine Sitzung lang als
`KNOWN`-Tabelle — sie waren der Grund, warum diese Sweeps überhaupt gebaut
wurden. Die Messungen, die sie belegt haben, stehen in `../optimierung.md`,
Abschnitt „S-15 bis S-18"; dort auch die Positivkontrolle (127 der 173 neuen
Testfälle fallen an `02ceca2` um).

Ein `KNOWN`-Eintrag für ein Szenario, das **nicht** mehr verstößt, wird
gestrichen, nicht mitgeführt: der Harness zählt die Treffer selbst mit, und
eine Tabelle, die „grün wegen der Ausnahmeliste" meldet, ist ein Messgerät,
das nichts mehr misst.

| Befund | Kurzfassung | Stand |
|---|---|---|
| **S-15** | Die S-12-Freigabeschranke (`_emitted_visible_text`) verwarf alles, was nur vom Turn-Anfang zurücklag — auch einen **fertigen, legitimen Satz** (`'Der Bericht ist fuer Sie. Ich'` → `''` bei Chunk 1000). Der Rest war der linke Rand des Carrys: Punkt und Leerraum, die den gesendeten Satz abschließen, starben mit der Narration (4/10 Chunkgrößen). | behoben: `strip_turn_start_narration()` + `_owed_lead_edge()` |
| **S-16** | Die erfundene Limit-Behauptung durchbrach den reinen Text-Turn — im Stream **und** im Body, weil die Beschränkung „nur bei Calls" aus S-08 für die Selbst-Steuerung gilt, nicht für diese Klasse. | behoben: `_strip_invented_limit_claim()` ohne Call-Bedingung, plus Body-Kette in `build_response()` |
| **S-17** | `_SENTENCE_END_CHARS` zählte `'` zu den Satzzeichen. Eine Part, die an einem Apostroph endet, galt als Satzende → der Part-Merge brach **mitten im Wort** um (`'I'\n\nll now read the file.'`). | behoben: `'` raus, `)"»` bleiben |
| **S-18** | DSML, das über viele Parts zerschnitten ist, leckt als sichtbares Markup in den Stream (der Aufruf wird trotzdem korrekt geborgen). Zwei Ursachen: die Absatzregel im Markup, und ein Opener, der erst bei *Vollständigkeit* erkannt wird. | behoben: Regel 0 in `_needs_paragraph_break()` + `BEGUN_MARKUP_RE` |
| **S-14-Rest** | `selbst-steuerung+call`: bei 2 von 6 Chunkgrößen entkommt der Wortrest vor der ersten Werkzeug-Marke. Bewusst akzeptiert — die Selbst-Steuerung steht am *Anfang* des Turns, es gibt also keinen fertigen Satz davor, den S-15 retten könnte. | `KNOWN`, zählt nicht als Verstoß |

Alle vier waren an `02ceca2` und `9054325` gegengeprüft: **vorbestehend**, nicht
von S-10…S-14 verursacht. Details in `../optimierung.md`, THEMA 8.
