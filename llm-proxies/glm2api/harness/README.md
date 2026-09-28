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

Die Harness-Ausnahmen sind exakt pro Chunk und erwartetem Output erfasst.
Andere Streamtexte oder Abweichungen bei Calls, Finish-Grund oder Body
werden weiterhin als Verstöße gemeldet.

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
| `leak_probe.py` | Narration-Rest je Chunkgröße 1…215; Antwort-Gegenprobe mit `read`/`bash`/Fence | S-14 erwartet exakt 0 sichtbaren Narrationstext; 0/215 Calls verloren, Antworttext exakt 0/104 verändert |
| `order_matrix.py` | Exakter Soll- und Chunk-Invarianzvergleich über 17 Text/Call-Layouts × 10 Chunkgrößen; zusätzlich S-14-Rest über alle 215 Chunkgrößen | zuletzt: 170 Layout-Messungen + 215 S-14-Messungen, 0 unbekannte Abweichungen; S-14 ohne Rest, 4/10 bekannte Whitespacevarianten nur in `rand-links-im-carry` |
| `sweep2.py` | Exakter Vertrags-Sweep: 23 Szenarien × 6 Chunkgrößen, Stream- **und** Non-Stream-Pfad (Text, Aufrufe, `finish_reason`, Body) | zuletzt: 138 Messungen, 0 unbekannte Verstöße; S-15-Schlussleerzeichen 2/6 bekannte Chunk-Abweichungen; keine S-14-Ausnahme |
| `trace_stream.py` | Delta-für-Delta-Trace, wenn ein Fall unklar ist | Werkzeug, kein Soll |

**Eigenprüfung der Harnesses** (Pflicht, sonst misst man nichts): beide
Sweeps müssen an einem alten Stand **rot** werden. `order_matrix` meldet
an `9054325` 14 unbekannte Verstöße, `sweep2` 7 — dort sind sie grün, wo
sie heute grün sind.

## Bekannte Befunde

**Der S-15-Produktionsrand ist nicht vollständig invariant:** bei dem
`rand-links-im-carry`-Layout unterscheidet sich je nach Chunkgrenze ein
abschließendes Leerzeichen. Exakte Messwerte stehen oben und in der
Harness-Whitelist. Eine nachträgliche Korrektur im Stream wurde bewusst
nicht vorgenommen, weil bereits ausgegebene Bytes nicht rücknehmbar sind.

Die früheren S-15…S-19-Produktionsbefunde waren an den damaligen Fällen
behoben (2026-09-27). S-15…S-18 waren die Funde aus dem
Harness-Neuaufbau und sind an `02ceca2` und `9054325` gegengeprüft:
vorbestehend, nicht von S-10…S-14 verursacht. Die Messungen und die
Positivkontrollergebnisse (127 von 173 neuen Testfällen rot an `02ceca2`)
stehen in `../optimierung.md`.

| Befund | Kurzfassung | Stand |
|---|---|---|
| **S-15** | Die S-12-Freigabeschranke verwarf auch einen fertigen, legitimen Satz; der Punkt und Leerraum am Carry-Rand starben mit der Narration. | Satzinhalt behoben mit `strip_turn_start_narration()` + `_owed_lead_edge()`; das Rand-Whitespace-Layout bleibt für Chunk 7/11/20/1000 abweichend und ist exakt dokumentiert |
| **S-16** | Erfundenen Limit-Behauptungen gingen im Text-only-Turn durch — Stream und Body. | behoben: Limit-Filter auch ohne Calls + Body-Kette |
| **S-17** | Apostroph als Satzende erzeugte Absatzumbruch mitten im Wort. | behoben: Apostroph aus Satzendzeichen entfernt |
| **S-18** | Über Parts zerschnittenes DSML leckte im Stream; Ursache: Absatzregel im Markup und fehlender Holdback für angefangene Opener. | behoben: Markup-Grenze + `BEGUN_MARKUP_RE` |
| **S-14-Rest** | Die mehrdeutigen initialen Artikel-Fragmente (`D`, `De`, `Der `, `T`, `Th`, `The `) werden bis zur Disambiguierung gehalten; bekannte Selbst-Narration bleibt unsichtbar, gewöhnliche Prosa mit `Der`/`The` bleibt erhalten. | behoben und verifiziert: 0/215 sichtbare Reste, 0/215 Calls verloren, Prosa-Gegenprobe 0/104 verändert |
| **S-19** | Trenner auf beiden Seiten eines unsichtbaren Calls verdoppelten Absatz-Newlines; auch zwei einzelne Newlines müssen sich über einen Call zu einem Absatz ergänzen. | behoben und mit vier Call-Layouts plus späterer Absatz-Gegenprobe über alle Chunkgrößen geprüft |

Der exakte Streamvergleich kann dokumentierte Whitespace-Reste nicht
weg-normalisieren: `rand-links-im-carry` weicht für Chunk 7, 11, 20 und
1000 nur beim abschließenden Leerzeichen von seiner Sollausgabe ab. Die
Harness-Ausnahme gilt für vollständigen Output und exakte Chunkgröße, nicht
für beliebige Probleme dieses Szenarios.
