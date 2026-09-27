# Mess-Harnesses (`harness/`)

Skripte, mit denen Verhalten des Translators **gemessen** wurde, bevor es
geändert wurde. Sie sind keine Tests — die pinnen den Zustand als
`tests/test_translator.py` (S-10 … S-19). Der Unterschied: ein Harness
misst über *alle* Chunkgrößen und liefert ein Protokoll zum Nachlesen; ein
Test pinnt eine Aussage.

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
drei Stück. Vor jeder "gemessenen" Änderung gehört dieselbe Messung
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
| `leak_probe.py` | Narration-Rest, der den Client erreicht, je Chunkgröße 1…215; dazu die Gegenprobe „echter Antworttext mit `` `read` ``/`` `bash` ``/Fence" | 4/215 sichtbare Präfixe (`D`, `De`, `Der `, `Der ` bei Chunk 1–4), Antworttext 0/104 verändert |
| `order_matrix.py` | Reihenfolge-Invariante über 17 Text/Call-Layouts × 10 Chunkgrößen; fünf Absatz/Call-Layouts prüfen Whitespace exakt; zusätzlich S-14-Rest über alle 215 Chunkgrößen | 170 Layout-Messungen + 215 S-14-Messungen, **0** unbekannte Abweichungen (vor S-19: 10/150 Layout-Verstöße durch verdoppelten Trenner) |
| `sweep2.py` | Vertrags-Sweep: 23 Szenarien × 6 Chunkgrößen, Stream- **und** Non-Stream-Pfad (Text, Aufrufe, `finish_reason`, Body) | 138 Messungen, **0** unbekannte Verstöße, 1 bekannter Befund (S-14-Rest, 2/6) |
| `trace_stream.py` | Delta-für-Delta-Trace, wenn ein Fall unklar ist | Werkzeug, kein Soll |

**Eigenprüfung der Harnesses** (Pflicht, sonst misst man nichts): beide
Sweeps müssen an einem alten Stand **rot** werden. `order_matrix` meldet
an `9054325` 14 unbekannte Verstöße, `sweep2` 7 — dort sind sie grün, wo
sie heute grün sind.

## Bekannte Befunde

**S-15…S-19 sind behoben** (2026-09-27). S-15…S-18 waren die Funde aus dem
Harness-Neuaufbau und sind an `02ceca2` und `9054325` gegengeprüft:
vorbestehend, nicht von S-10…S-14 verursacht. Die Messungen und die
Positivkontrollergebnisse (127 von 173 neuen Testfällen rot an `02ceca2`)
stehen in `../optimierung.md`.

| Befund | Kurzfassung | Stand |
|---|---|---|
| **S-15** | Die S-12-Freigabeschranke verwarf auch einen fertigen, legitimen Satz; der Punkt und Leerraum am Carry-Rand starben mit der Narration. | behoben: `strip_turn_start_narration()` + `_owed_lead_edge()` |
| **S-16** | Erfundenen Limit-Behauptungen gingen im Text-only-Turn durch — Stream und Body. | behoben: Limit-Filter auch ohne Calls + Body-Kette |
| **S-17** | Apostroph als Satzende erzeugte Absatzumbruch mitten im Wort. | behoben: Apostroph aus Satzendzeichen entfernt |
| **S-18** | Über Parts zerschnittenes DSML leckte im Stream; Ursache: Absatzregel im Markup und fehlender Holdback für angefangene Opener. | behoben: Markup-Grenze + `BEGUN_MARKUP_RE` |
| **S-14-Rest** | 4/215 Chunkgrößen lassen vor dem ersten Backtick `'D'`, `'De'` oder `'Der '` durch (Chunk 1–4); ab Chunk 5 kein sichtbarer Rest. Höchstens vier Präfixzeichen in diesem Repro, keine generelle Wortlänge-Latenz in jedem Turn. | bewusst akzeptiert; im `sweep2` als `KNOWN` |
| **S-19** | Trenner auf beiden Seiten eines unsichtbaren Calls verdoppelten Absatz-Newlines; auch zwei einzelne Newlines müssen sich über einen Call zu einem Absatz ergänzen. | behoben und mit vier Call-Layouts plus späterer Absatz-Gegenprobe über alle Chunkgrößen geprüft |

Die ursprünglichen Coverage-Fälle `absatz-vor-call`/`absatz-nach-call`
(20 Fälle) und `selbst-steuerung+nur-text` (7 Fälle) pinnen bestehende
Verträge und waren an `02ceca2` bereits grün. S-19 hatte vor der ersten
Gegenprobe 10/150 Layout-Verstöße im neuen Doppeltrenner-Fall; nach der
Erweiterung auf fünf Absatz/Call-Layouts sind 170/170 Layout-Messungen grün.
