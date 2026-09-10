# BEFUNDE — glm2api Härtetest (HARD Benchmark v2), 2026-09-10

## Kontext

Aufbauend auf dem Echo-Filter-Fix (Commit 3cd794e) wurde der Benchmark
massiv verschärft (`/workspaces/benchmark/benchmark-hard.md` + Fehlerinjektion
`/workspaces/benchmark/broken3.py`) und ein ~30-Min-Langlauf über den
glm2api-Subagent gefahren (Session `ses_f73ad1933ffex8biaYnwMJmM05`,
Modell glm2api/glm-5.3, ~70 Upstream-Runden, 19:20–20:25 Uhr).

Der Langlauf reproduzierte EINEN neuen, echten Proxy-Bug (Protokoll-Leak)
plus mehrere Bestätigungen der vorherigen Fixes.

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