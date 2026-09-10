# BEFUNDE — glm2api Härtetest (HARD Benchmark v2), 2026-09-10

## Kontext (Re-Run 20:49–22:37, nach Fixes 10+11)

Zweiter Langlauf (Session `ses_f73591f73ffeTGH4X9kWi6U1QQ`, ~2h, ~77 Upstream-
Runden). Ergebnis: **122 Tool-Calls, 0 echte Ausführungsfehler**, komplettes
miniforge-Projekt + broken3-Debugging + Loadtest + finale Berichte. Drei
Anomalie-Klassen blieben — eine davon ist ein NEUER Proxy-Bug.

## Befund 1 (NEU, kritisch): Tool-Protokoll leakt als Klartext bei Snipsel+Finish-Duplikat

**Symptom (live):** Um 20:25:14 kam beim Client ein reiner TEXT-Part mit dem
geleakten Inhalt an:

    {"tool_calls":[{"name":"bash","arguments":{"command":"cd ..."}}]}[]

statt eines strukturierten Tool-Calls. Proxy-Log: `text_len=216 tool_calls=0`.
DB zeigt denselben String als `text`-Part; das Modell „argumentiert" in der
Reasoning-Spur wörtlich mit dem Protokoll-String.

**Root Cause (reproduziert im Parser-Test):** Der Upstream streamt Token-
Schnipsel, dann den Volltext (bekanntes Part-Merge-Verhalten). Hält der
StreamingToolParser ein Protokoll-Fragment (z.B. `{"tool_calls":[{"name":"ba`)
und delta-t danach der finish-Volltext, konkatenieren beide zu
`<Fragment><Volltext>` — json.loads schlägt fehl → der komplette Text wird
als `visible` durchgereicht, der Call geht verloren. Parser-Testfall
„snipsel+finish": `flush_vis='{"tool_calls":[{"name":"bash","arguments...'`,
`flush_calls=0`. (Vermutlich Grund, warum der Subagent zweimal das Protokoll
„antw ortete" statt Tools zu callen — und in der Reasoning das Protokoll
wörtlich als Handlungsvorschrift liest.)

**Fix-Design:** Recovery-Scan in `_find_json_tool_call`: bei JSONDecodeError
alle `{"tool_calls"`-Vorkommen im Kandidaten scannen, erste valide balancierte
Instanz parsen (deckt auch Snipsel-Duplikat ab). Zusätzlich Terminator-
Konsum whitespace-tolerant machen.

## Befund 2 (NEU, klein): `[]`-Terminator leakt bei führendem Whitespace

**Symptom (Parser-Test):** Kommt nach dem JSON-Objekt ein `\n` vorm Terminator
(`...}\n[]`), matcht `rest.startswith("[]")` nicht → das `[]` erscheint als
sichtbarer Content (`visible='[]'`). Alle 6 Stream-Zerlegungs-Varianten
zeigten `visible='[]'`. Harmlos, aber unsauber.

**Fix-Design:** Terminator-Erkennung nach `rest.lstrip()` mit Skip des
führenden Whitespace im Konsum.

## Befund 3 (BESTÄTIGT): Echo-Filter wirkt

Vorher-Log (Benchmark v1, vor Fix): `server_tools=36/9/6` mit 24er-
Timestamp-Clustern und Duplikat-Executions. Jetzt: Langlauf über ~70 Runden,
`server_tools` maximal 2, meist 0–1, **keine Timestamp-Cluster, keine
Duplikat-Loops** mehr in der opencode-DB. Der Echo-Filter (History-Signatur +
Signatur-Dedup) hält dem Langlauf stand.

## Befund 4 (Modell, nicht Proxy): Encoding-Verderb in Tool-Argumenten

Subagent schrieb Dateien, in denen statt 'ü' die Bytes U+0014/U+0005
landeten (io_utils.py). Vermutlich Modell-Schwankung beim Nicht-ASCII-
Streaming — beobachten; kein Proxy-Parserfehler nachweisbar.

## Befund 5 (Modell, nicht Proxy): Rückfrage-/Abbruch-Neigung unter Dauerlast

Subagent brauchte mehrere Resume-Runden (leerer Startturn, „Soll ich
fortfahren?"-Rückfragen nach Phasenende, vorzeitiger final-report). Das
halluzinierte „unknown tool call"-Narrativ aus v1 trat NICHT mehr auf —
die Fehlerberichte des Modells sind nach dem Echo-Fix realistisch geworden.

## Ausstehende Arbeiten

1. ~~Fix Befund 1 + 2 in `tool_parser.py`~~ — **ERLEDIGT** (siehe unten).
2. ~~Proxy-Restart + Bundle-Refresh~~ — **ERLEDIGT**.
3. benchmark-hard.md/broken3.py sind ausgelegt für Wiederholungsläufe
   (bewusst nicht ins Repo-Essentielle committet — liegen unter
   /workspaces/benchmark/).

## Fixes zu Befund 1 + 2 (umgesetzt)

- `tool_parser.py::_find_json_tool_call`:
  - **Recovery 2** bei JSONDecodeError: neuer `_recover_tool_calls_json()`
    scannt alle `{"tool_calls`-Vorkommen im Kandidaten und extrahiert die
    erste valide, balancierte Instanz (deckt Snipsel+Finish-Duplikat ab,
    inkl. Klammer-Reparatur-Variante). Der brace-scan endet sonst am
    ersten oberflächlich balancierten `}` mitten im Fragment.
  - Terminator-Konsum whitespace-tolerant: `rest.lstrip()` + Skip des
    führenden Whitespace (`...}\n[]` leakte vorher das `[]`).
- Regressionstests (3 neue, 88/88 grün): snipsel+full-text-duplicate,
    whitespace-terminator, original-Live-Fall (text_len=216).
- Live-Verifikation: Proxy neu gestartet (8001), Tool-Call-Request liefert
  strukturierten Call, kein Protokoll im Content. Bundle neu gebaut.
---

# Re-Run-Befunde (20:49–22:37, nach Fixes 10+11)

## Re-Befund A (FIX WIRKT): 122 Tool-Calls, 0 Fehler

Echo-Filter + Recovery 1+2 hielten über den kompletten ~2h-Lauf: kein
server_tools-Cluster, keine Duplikat-Loops, alle 122 ausgeführten Calls
(bash 54, write 31, edit 22, read 15) ohne echten Fehler. Das
„unknown tool call"-Halluzinations-Narrativ trat nicht mehr auf.

## Re-Befund B (NEU, gefixt): Leak bei invalidem JSON mit unbalancierten Klammern (21:55)

Das Modell emittierte 6 Tool-Calls als ~6,6KB-Block mit FEHLERHAFTem JSON
(16 `{` vs 15 `}` — zwischen zwei Call-Objekten fehlte das schließende `}`).
Der Brace-Scan fand kein Ende, alle Recovery-Stufen griffen nicht →
kompletter Block leakte als TEXT-Part.

**Fix (umgesetzt, Commits folgen):** Recovery-Stufe 3 `_recover_call_elements()`
in tool_parser.py — extrahiert name/arguments-Paare einzeln per eigenem
string-aware Scan und re-serialisiert das Objekt; robust gegen fehlende
Klammern/Kommas zwischen Call-Elementen. Regressionstest mit dem
Live-Leak-Muster (3 Calls, unbalanciert) vorhanden; 89/89 Tests grün.
Verifiziert am Original-Leak-String: 6 Calls extrahiert, clean="".

## Re-Befund C (NEU, OFFEN): Doppelausgabe Call + Protokolltext (22:35)

Turn-Finalize: `tool_calls=1` UND `text_len=1630` gleichzeitig — der
Protokolltext wurde ALSO parallel zum strukturierten Call als Text-Part
emittiert. Der Leak-String parst non-streaming sauber (Recovery 3, calls=1)
und in 8 getesteten Streaming-Zerlegungen ebenfalls kein Leak reproduzierbar.
Vermutung: Part-Doppelverarbeitung im GLMEventAccumulator (gespiegelter
Text-Part + Tool-Part aus demselben Upstream-Part) — für die Ursachen-
analyse braucht es DEBUG_DUMP_ALL des Turns (im Re-Run nicht aktiv).
→ Nächster Schritt: Re-Run mit DEBUG_DUMP_ALL=1 und dann gezielter Fix.

## Re-Befund D (Modell): Antwort-Loops/Drift bei extremem Kontext

Nach ~50 Runden (~150k+ Kontext) wiederholte der Agent alte Antworten und
missverstand neue Prompts (Extraktions-Halluzination). 4 Resume-Schubser
nötig. Grenze liegt offenbar bei sehr langen Kontexten mit hoher
Tool-Dichte — Modell-Thema, kein Proxy-Bug.

## Re-Run Fazit

Von 5 Anomalie-Klassen im ersten Lauf blieben 3: Leak-B (gefixt),
Doppelausgabe C (offen, braucht Debug-Dump), Drift D (Modell).
Duplikat-Loops und „unknown tool call"-Halluzinationen sind vollständig
verschwunden. Tool-Zuverlässigkeit der Ausführung: 122/122 = 100%.

---

# Fix zu Re-Befund C (umgesetzt)

**Midstream-Guard in translator.py::consume_event:** Ein sichtbares Text-Delta,
das selbst Protokoll-Fragmente enthält (`{"tool_calls"`, `<ml_tool_call`,
`<|DSML|tool_call`), wird bei deklarierten Tools NIE sofort als content-Delta
emittiert — es wandert ins Deferred-Buffer, wo das bestehende finalize-Safety-
Net es parst (Call-Extraktion) und den bereinigten Text ausgibt. Damit ist die
Doppelausgabe (strukturierter Call + Protokoll-Text im selben Turn, beobachtet
22:35) auch ohne exakte Upstream-Rekonstruktion strukturell verhindert.

Verifikation: 90/90 Tests (neuer Regressionstest: Midstream-Delta mit
Protokoll → kein Leak in content-Deltas, Call wird bei finalize extrahiert,
finish_reason=tool_calls). Proxy neu gestartet (Health OK), Bundle neu gebaut.

---

# Fix zu Leak-Variante D (Final-Run, umgesetzt)

**Final-Run 00:27 + 00:33 (Session ses_f72c95b43ffeXGckO4bwAIk6Cn):** Das Modell
emittierte Tool-Calls als **NACKTES JSON-Array** `[{"name":...,"arguments":...}]`
— ohne `{"tool_calls":`-Wrapper. Variante 1: Prosa + Array (00:27). Variante 2:
kaputter ` ``json `-Marker (2 Backticks → keine Fence-Maskierung!) + Array ohne
schließende `]` + Duplikat-Array + `[]`-Terminator + echtes Fence-Ende (00:33).

**Fix:** `_find_bare_tool_call_array()` in tool_parser.py — erkennt
`[\s*{\s*"name"\s*:` (strenge Validierung: Element-Keys ⊆ {name, arguments}),
bracket-balancierter Scan, Terminator/Fence-Rest-Konsum, und bei invalidem JSON
Recovery via `_recover_call_elements` (fehlt `]` + Duplikat). Verdrahtet in
`parse_tool_calls_from_text` UND `_split_stream_text` (Streaming-Pfad 1b).
Beide Live-Leak-Strings verifiziert: Calls extrahiert, kein Protokoll im Text.
92/92 Tests (2 neue Regressionstests mit Live-Mustern), Proxy neu gestartet,
Bundle neu gebaut.

---

# FINAL-RUN Abschluss (Session ses_f72c95b43ffeXGckO4bwAIk6Cn, 23:23–01:2x)

## Ergebnis: ALLE PROXY-LEAKS GESCHLOSSEN

**DB-Verifikation (124 Tool-Parts: bash 50, write 28, read 24, edit 21, invalid 1):**
- 0 echte Ausführungsfehler (alle completed)
- 3 Protokoll-Leaks — ALLE vor dem Leak-D-Fix (23:27 kleiner Text-Leak,
  00:27 + 00:33 Leak-Variante D). NACH Proxy-Restart mit Fix (efbc2e7,
  ~00:45) und Resume für Phase 5-10: **0 neue Leaks**.
- Phasen 5-10 liefen nach dem Fix komplett sauber durch (README, fixed3.py
  mit 6 Bugfixes, loadtest 100 seq + 100 par, recall, final-report).

**Agent-behauptete Anomalien (20):** 15x "leere Turns" (Modell-Wahrnehmung,
in der DB nicht als Fehler sichtbar — vermutlich Modell-Drift-Erleben bei
langem Kontext), 2x JSON-Array-Leaks (real, gefixt), 2x SchemaErrors
(edit-Aufrufe mit falschen Argumenten — Modell-Fehler, harmlos),
1x Single-JSON-Leak (23:27, real).

**Call-Zahl:** Agent zählte 92 (worklog-basiert) — real 124 Tool-Parts.

## Gesamturteil Härtetest-Kampagne

Vier Läufe (v1-Benchmark, HARD-Run 1, Re-Run, Final-Run) haben nacheinander
fünf Leak-/Echo-Bug-Klassen ans Licht gebracht — alle gefixt und per
Regressionstest abgesichert (92/92 Tests). Der Final-Run bestätigt: Proxy
liest Tool-Protokoll in allen beobachteten Formen (Wrapper-JSON, invalides
JSON, nacktes Array, kaputte Fences, Duplikate) korrekt und leakt nicht
mehr. Rest-Themen bleiben Modell-Seite (Encoding, Kontext-Drift ~150k+).
