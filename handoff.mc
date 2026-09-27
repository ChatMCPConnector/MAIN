# Handoff glm2api — S-15…S-18 (Stand 2026-09-27, **Arbeit abgeschlossen**)

> Scratch-Datei für den Agenten-Wechsel. **Nicht committen** — sie ist kein
> Ergebnis, sondern der Zustandsbericht. Endgültige Doku ist
> `llm-proxies/glm2api/optimierung.md` + `harness/README.md`.

**Nachtrag 2026-09-27 (spätere Sitzung):** § 4 ist **abgearbeitet** — roter Test
korrigiert, Positivkontrolle gefahren, Doku nachgezogen. Es fehlt nur noch der
Commit (siehe § 4.6). `cline/handoff.md` existiert in diesem Repo **nicht mehr**
(das ganze `cline/`-Verzeichnis ist weg) — der frühere Punkt 4.5 ist gegenstandslos.

---

## 0. Wo steht die Arbeit?

**Fertig.** Alle vier Befunde behoben, gemessen, getestet, dokumentiert.

| | Stand |
|---|---|
| Tests | **1599 grün** (1426 + 173 neu aus S-15…S-18) |
| `harness/order_matrix.py` | **0 / 120** Verstöße (vorher 4) |
| `harness/sweep2.py` | **0 unbekannte** / 132; 1 bekannter Befund (S-14-Rest, 2/6) |
| `harness/leak_probe.py` | 4/215 Leck + 0/104 Gegenprobe — unverändert, akzeptierter S-14-Rest |
| Positivkontrolle an `02ceca2` | **127 der 173 neuen Fälle rot**, 46 Gegenproben grün |
| Docs | `optimierung.md` Abschnitt „S-15 bis S-18" auf erledigt umgeschrieben, Verifikation + Erledigt-Historie + Merkposten ergänzt; `harness/README.md` `KNOWN`-Tabelle aktualisiert |

Geänderte Dateien (alle uncommitted):

```
 M llm-proxies/glm2api/harness/order_matrix.py         29 +-
 M llm-proxies/glm2api/harness/sweep2.py               81 +-
 M llm-proxies/glm2api/harness/README.md               32 +-
 M llm-proxies/glm2api/optimierung.md                 243 +++-
 M llm-proxies/glm2api/src/glm2api/services/translator.py   600 +++-
 M llm-proxies/glm2api/src/glm2api/utils/tool_parser.py     75 ++-
 M llm-proxies/glm2api/src/glm2api/utils/tool_protocol.py    8 +-
 M llm-proxies/glm2api/tests/test_translator.py             295 ++-
```

---

## 1. Regeln (unverändert, aber hier zur Erinnerung)

- Nur unter `/workspaces/MAIN` arbeiten.
- **Committen/Pushen ist dauerhaft freigegeben**: nach jedem abgeschlossenen
  Arbeitsgang `./infra/scripts/save.sh "<message>"`.
- **Fremde freebuff-Änderungen NICHT mitcommitten.** Gezielt `git add <pfade>`.
  Aktuell fremd und *nicht* anfassen: `infra/scripts/freebuff-install.sh`,
  `freebuff-pty.py`, `free-models.py`, `aliases.sh`, `keys.sh`, `secrets.sh`.
- **Keine `infrastructure.md`-Änderung** — das war und ist keine Infra-Änderung.
- Testlauf: `cd /workspaces/MAIN/llm-proxies/glm2api && .venv/bin/python3 -m pytest tests -q`
- Harnesses: `cd /workspaces/MAIN/llm-proxies/glm2api && .venv/bin/python3 harness/<skript>.py [--quiet|--short]`
  (`common.py`, `leak_probe.py`, `order_matrix.py`, `sweep2.py`, `trace_stream.py`, `README.md`)
- **Eigenprüfung Pflicht** für neue Testklassen: müssen am alten Stand rot werden
  (`git worktree add -f /workspaces/wt-s15 02ceca2`). Die alten Worktrees
  `wt-pre` / `wt-pre2` wurden bereits entfernt.
- Tool-Fallen in dieser Session: `write_todos` will `completed` als **bool**;
  `run_terminal_command` braucht `process_type: "SYNC"`; `write_file` braucht
  `path` + `instructions` + `content`; `str_replace` scheitert bei
  Umlaut-/Leerzeichen-Differenzen (Zeilenweise exakt prüfen, besser `sed -n`).

---

## 2. Was in dieser Sitzung passiert ist (Reihenfolge)

### 2.1 Der eingeschlichene `NameError`

Der letzte `str_replace` der Vorsitzung hatte `self._deferred_is_answer` in den
Aufrufern **gesetzt**, aber im `finalize`-Block als **lokale** Variable
**gelesen** → `NameError`, **695 von 1426 Tests rot**.

Fix: Snapshot neben dem ohnehin nötigen `_deferred_at_finalize`:

```python
_deferred_at_finalize = self._deferred_visible_text
_deferred_is_answer = self._deferred_is_answer
```

Merksatz: ein unbestätigter Patch-Satz aus einer unterbrochenen Sitzung ist
 billiger zu prüfen als 695 Testfehler zu lesen. **Immer Suite laufen lassen,
 bevor weitergebaut wird.**

### 2.2 Messung nach dem `NameError`-Fix

| Harness | Ergebnis |
|---|---|
| Suite | 1426 grün |
| `order_matrix` | 4 Verstöße, alle `rand-links-im-carry` (3, 8, 11, 20) |
| `sweep2` | 0 unbekannt; bekannt: `selbst-steuerung+call` 2/6, `selbst-steuerung-mittelteil` 5/6 |
| `leak_probe` | 4/215 + 0/104 |

S-15 war also **halb** behoben: der ganze erste Satz überlebte nur bei chunk 1
und 10000. Der Rest war eine eigene, ältere Klasse: **verlorener linker Rand**.

### 2.3 Der S-15-Kern: `_strip_release_narration` + `strip_turn_start_narration`

War schon in der Vorsitzung gebaut, wirkt aber: `sweep2`-Szenario
`selbst-steuerung-mittelteil` **5/6 → 1/6**, `dsml-aufruf+prosa` **→ 0/6**.

### 2.4 Der S-15-Rest: `_owed_lead_edge` (neu in dieser Sitzung)

**Befund.** `order_matrix`, layout `rand-links-im-carry`, Text
`"Der Bericht ist fuer Sie. Ich"` + Aufruf, Erwartung
`"Der Bericht ist fuer Sie."`:

| chunk | IST vorher | Ursache |
|---|---|---|
| 3, 8 | `'Der Bericht ist fuer Sie'` | Carry war `'. Ich'` — der **Punkt** wanderte als „Trenner" in den Carry und starb mit der Narration |
| 11, 20 | `'Der Berichtist fuer Sie.'` / `'Der Bericht ist fuerSie.'` | Carry war `' ist fuer Sie. Ich'` bzw. `' Sie. Ich'` — der **Leerraum** wanderte mit |

Der `finalize`-Pfad hatte nur `lead_whitespace` (Leerraum) wieder angehängt, nie
den Satzendpunkt. Und `strip_turn_start_narration` frisst den Rand mit, weil
`_SENTENCE_END_RE` den Punkt als **Anfang** des Narration-Satzes liest.

**Fix.** Neue Methode `GLMEventAccumulator._owed_lead_edge(text) -> (eigener
anteil, geschuldeter rand)` in `translator.py`, plus Modul-Konstante
`_SENTENCE_TERMINATORS = ".!?…。"` (ohne `"`, `)`, `»` — die schließen, sie
stehen nie am **Anfang**).

Angewandt an **zwei** Stellen in `consume_event`:
1. im S-14-Zweig nach `_split_open_sentence` (nur wenn der fertige Präfix leer ist),
2. im S-09/Ganztext-Zweig („hier wird bewusst der GANZE text zurückgehalten").

Der Rand geht dabei **direkt an `chunks`**, nicht durch die restliche Kette.

**Die drei Schranken** (alle drei waren nötig, jede hat einen roten Alt-Test
verhindert — siehe § 2.5):

1. `self._emitted_visible_text` muss wahr sein. Sonst gibt es keinen Satz, den
   der Rand abschließen könnte, und ein führender Punkt/Leerraum wäre ein
   Artefakt am Turn-Anfang (`leerraum-artefakt`).
2. `self._deferred_visible_text` muss leer sein. Steht sichtbarer Text im
   S-05-Puffer, geht der zuerst raus.
3. `self.tool_parser.pending_text` muss leer sein. **Der teuerste Fund:**
   ohne diese Schranke riss der Rand einen Code-Fence auseinander —
   `test_s10_fenced_text_in_one_part_is_not_lost_before_a_native_call[3]` rot:
   der Parser hielt `` ```bash\nls ``, das `' '` vor `-la` wurde als Rand
   abgetrennt und direkt veröffentlicht, der Rest `-la` in den Carry →
   `ls-la` statt `ls -la`, dazu ein Fence mit führendem Leerraum.
   Trace: `delta ' -l' RAUS ' ' carry='-l' parser='```bash\nls'`.

**Zusatzbefund dabei:** `_emitted_text_tail` (Kontext für
`_preamble_narration_probe`) führt den **Upstream**-Text, nicht den
veröffentlichten — der Carry ist also darin enthalten. Deshalb las sich der
Rand `'. '` nach dem Carry `'Ich'` als Präambel (`'… fuer Sie. Ich' + '. '`)
und landete im S-05-Puffer statt raus. **Deshalb der direkte Weg an
`chunks`**: der Rand ist per Definition kein Text, er enthält weder Narration
noch Protokollfragment, er schließt nur ab.

**Weiterhin gültige Randregel:** der Rand umfasst **keinen Zeilenumbruch**,
sonst gehört er zum folgenden Block (`' '` + `'\t'` in der Schleife, nicht
`.isspace()`).

**Ergebnis:** `order_matrix` **4 → 0**, `sweep2` `selbst-steuerung-mittelteil`
**1/6 → 0/6**.

---

## 3. Was S-15…S-18 inhaltlich waren (für die Doku)

- **S-15** — Ein *fertiger, unauffälliger erster Satz* fiel im Aufruf-Turn
  **ganz** aus, wenn er mit Selbst-Steuerung in einem Delta ankam. Ursache:
  die S-12-Freigabeschranke `self._emitted_visible_text` beantwortet die
  Frage „kam vorher schon etwas raus"; die richtige Frage ist „ist der Rest
  eine **Präambel**". Filterkette: `strip_turn_start_narration`,
  `strip_self_steering(rcs=False)`, `strip_invented_limit_claim(rcs=False)`,
  `strip_protocol_meta_narration` — als **eine** Methode
  `_strip_release_narration`, drei Aufrufer. Plus Rand-Recovery (§ 2.4).
- **S-16** — Die erfundene Limit-Behauptung durchbrach den reinen Text-Turn
  (Stream **und** Body). Die Beschränkung „nur wenn der Turn Aufrufe hat"
  stammt aus S-08 und gilt für die **Selbst-Steuerung** (dort ist eine Aussage
  über `open` echter Inhalt), nicht für die Limit-Meldung. Stream: neue
  `_strip_invented_limit_claim()` (greift auch ohne Calls, gemeinsame Hülle
  `_apply_text_filters`). Body: Kette in `build_response()` direkt vor
  `stripped_echo`.
- **S-17** — `_SENTENCE_END_CHARS` enthielt `'` → jeder Part, der an einem
  kontrahierenden Apostroph endete, galt als Satzende, der Part-Merge fügte
  `\n\n` ein, das erste Präambel-Fragment entkam (`'I'\n\nll now read the
  file.'`). Apostroph raus; `)"»` bleiben.
- **S-18** — DSML über viele Parts zerschnitten leckte als Markup in den
  Stream, **zwei** Ursachen: (a) `_needs_paragraph_break()` brach an jeder
  `|`-Grenze um, weil `|` am Zeilenanfang wie eine Markdown-Tabelle aussieht
  → neue Regel 0: liegt die Grenze **innerhalb** von Markup (nach letztem `>`
  folgt ein `<`), kein Absatzumbruch; (b) `BEGUN_MARKUP_RE` =
  `_build_begun_markup_regex([*TAG_NAME_HINTS, '{"tool_calls"'])`.
  **Fallstrick dokumentiert:** die Fragmente müssen `re.escape()`t werden,
  sonst wird das `|` in `<|` zur Alternative und leere Alternativen matchen
  überall (falsch-positiver Treffer auf `'Pa'`).

---

## 4. Offen — nur noch der Commit

### 4.1 … 4.5 ✅ abgearbeitet

- **4.1** roter Test korrigiert (`BEGUN_MARKUP_RE` ist `\Z`-verankert; `'<|'` ist
  selbst ein `TAG_NAME_HINTS`-Eintrag, die kürzesten angefangenen Opener sind
  `'<'` und `'<|d'`). Suite: **1599 grün**.
- **4.2** Positivkontrolle an `02ceca2` gefahren (`git worktree add -f
  /workspaces/wt-s15 02ceca2`, Testdatei hinkopiert, mit `PYTHONPATH` auf den
  alten `src`): **127 rot / 46 grün**, Aufschlüsselung je Testklasse in
  `optimierung.md`. Worktree wieder entfernt.
- **4.3** `sweep2.py`-`KNOWN` bereinigt (nur `selbst-steuerung+call` bleibt),
  `order_matrix.py` war schon leer, `harness/README.md` aktualisiert.
- **4.4** `optimierung.md`: Abschnitt auf „behoben 2026-09-27" umgeschrieben
  (Ursache + Fix je Befund, Ergebnistabelle, Positivkontrolle-Tabelle,
  Reparaturreihenfolge), Verifikation (1599 Tests, 127/46), Erledigt-Historie,
  Merkposten.
- **4.5** ~~`cline/handoff.md`~~ — **existiert nicht mehr**, das ganze
  `cline/`-Verzeichnis ist aus dem Repo verschwunden. Gegenstandslos.

### 4.6 Commit (einzig offen)

```bash
cd /workspaces/MAIN
.venv  # glm2api
git add llm-proxies/glm2api/harness llm-proxies/glm2api/src \
        llm-proxies/glm2api/tests llm-proxies/glm2api/optimierung.md
./infra/scripts/save.sh "fix(glm2api): S-15..S-18 behoben — Praeambel satzweise, Rand des Carries, Limit-Behauptung ohne Calls, Apostroph kein Satzende, DSML ueber viele Parts"
```

`handoff.mc` (diese Datei) **nicht** committen.

---

## 5. Landkarte der Änderungen in `translator.py` (~5400 LOC)

| Ort | Was |
|---|---|
| `_SENTENCE_END_CHARS` / **`_SENTENCE_TERMINATORS`** | S-17 bzw. neu für den linken Rand |
| `_needs_paragraph_break` | S-18-Regel 0 (Grenze innerhalb von Markup) |
| `_split_open_sentence` | S-14 (Rand gehört zum Trenner) — unverändert, ist die Konvention, an der S-15-Rest ausgerichtet ist |
| `strip_turn_start_narration` | S-15, satzweise Präambel |
| `_apply_text_filters` | S-16, gemeinsame Filterhülle mit Rand-Erhalt |
| `_strip_self_talk` / `_strip_invented_limit_claim` | S-16 |
| **`_owed_lead_edge`** | **S-15-Rest, neu** |
| `_strip_release_narration` | S-15, eine Filterkette für zurückgehaltenen Text |
| `_turn_start_buffer_is_preamble` | S-15, „ist der Puffer Präambel?" |
| `_begun_tool_token_holdback` / `_NARRATION_BEGUN_TOKEN_RE` | S-14 |
| `_deferred_is_answer` / `_deferred_at_finalize` / `_flushed_was_preamble` | S-15 |
| `build_response` | S-16-Body-Kette |
| `consume_event` | zwei Aufrufer von `_owed_lead_edge` (S-14-Zweig, S-09-Ganztext-Zweig) |
| `tool_parser.py`: `BEGUN_MARKUP_RE`, `flushed_markup_prefix_is_preamble` | S-18 / S-15 |
| `tool_protocol.py`: `_TOOL_MARKUP_RE` + DSML-Alternative | S-18 |

Ad-hoc-Debug-Skripte (`harness/_dbg*.py`) sind **wieder entfernt**.

---

## 6. Merksätze aus dieser Sitzung

1. Ein unbestätigter Patch aus einer unterbrochenen Sitzung erst verifizieren
   (`NameError` → 695 rote Tests).
2. Ein Harness-Bug sieht aus wie ein Proxy-Bug. Umgekehrt gilt es auch: Ein
   **grüner** Harness kann einen kaputten Proxy verdecken, wenn die Erwartung
   im Harness mitgeschrieben wurde, statt aus den gepinnten Tests zu stammen.
3. Ein Auslöser, der ein *vollständiges* Merkmal sucht, ist an jeder
   Schnittstelle unvollständig (S-14-Lehre, galt für S-18 nochmal).
4. Drei Kandidaten für „wo gehört das Zeichen hin" — und die Reihenfolge ist
   keine Geschmacksfrage, sondern **Reihenfolge-Invariante**: der Rand gehört
   an die *Stelle*, an der er entstanden ist, nicht nachträglich an den
   Abschluss.
5. Ein Rand, der aus einem Container herausgebrochen wird, braucht drei
   Schranken: „gibt es schon Inhalt davor?", „ist der geordnete Senke leer?",
   „steht der Parser mitten in einer Struktur?".
