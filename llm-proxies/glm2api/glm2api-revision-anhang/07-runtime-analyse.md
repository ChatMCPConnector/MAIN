# 07 — Runtime-Analyse: Tool-Call-Leaks in echten Sessions

## Methode

- **DB:** ausschließlich read-only über `sqlite3 "file:/home/vscode/.local/share/opencode/opencode.db?mode=ro"`. Die Auswertung verwendet `json_extract` und indizierte Verknüpfungen über `message.session_id`, `message.id` und `part.message_id`.
- **Sessions:** `message.data.providerID = 'glm2api'`; alle 82 so gefundenen Nachrichten sind Assistant-Nachrichten mit `modelID = 'glm-5.3'` (63 `variant = default`, 19 `variant = max`).
- **Zählung:** `tool_calls` in dieser Analyse bedeutet persisted `part.type='tool'` bzw. `tool_calls` in Assistant-Antworten. Davon getrennt werden die später gezählten JSON-Fragmente in Text-Parts.
- **Text-Erkennung:** Literal `{"tool_calls"`, `{"name"`, `"arguments"`, `call_id`, `<tool_call` und `<|DSML|`, zusätzlich tolerant `{"tool_calls` ohne schließendes Anführungszeichen. Die Klammerprüfung ist string-/escape-bewusst; verschachtelte/überlappende Kandidaten werden nicht als separate Calls gewertet.
- **Logs:** alle sechs Dateien `glm2api_debug.log*` wurden read-only gelesen (zusammen 56.417.696 Byte). Ausgewertet wurden `x-session-id`, `Response finalize`, `GLM raw SSE block`, `GLM SSE parsed event`, `GLM SSE finalize output` und echte Warn-Header.
- **Zeit:** DB-Zeiten wurden als UTC aus `time_created/1000` gelesen. Log-Zeiten sind die Logger-Zeiten. Für die Zuordnung wurde primär die exakte `x-session-id` verwendet, nicht eine heuristische Dateinamen- oder Benchmarktext-Zuordnung.
- **Schutz:** Keine Rohprompts, Header-Credentials, Tokens oder Secrets werden in diesen Bericht übernommen. Beispiele mit langen `content`-/`filePath`-Werten sind auf `<PATH>`/`<CONTENT>` reduziert; Schlüssel, Tool-Namen, Reihenfolge und kaputte Klammern bleiben erhalten.

## Gefundene Leaks (mit Zahlen)

### Session-Übersicht

`Messages` ist als `glm2api-Nachrichten / alle Nachrichten der Session` angegeben. Jede Session besitzt genau eine zusätzliche Nachricht ohne `providerID='glm2api'`.

| Session | UTC-Zeitfenster | Messages | Tool-Parts | Text-Parts | Tool-Fehler |
|---|---|---:|---:|---:|---:|
| `ses_f309e34acffehwJ7lOr5eOprf4` | 2026-09-23 17:48:07–18:12:08 | 16 / 17 | 30 | 8 | 2 |
| `ses_f306b94a6ffebsDKrmnTEPczF8` | 2026-09-23 18:43:25–18:50:59 | 7 / 8 | 38 | 5 | 0 |
| `ses_f302a0208ffeBOnsPFM6GqKECF` | 2026-09-23 19:55:03–20:02:54 | 7 / 8 | 68 | 5 | 7 |
| `ses_f3017a878ffe0HUEM2Q7xB7UmE` | 2026-09-23 20:15:06–20:28:22 | 13 / 14 | 107 | 9 | 0 |
| `ses_f2fe31a3effe0jUCOkyfyqFbw9` | 2026-09-23 21:12:30–21:12:30 | 1 / 2 | 0 | 1 | 0 |
| `ses_f2fdc1badffepYZ6ShuLVBeMBI` | 2026-09-23 21:20:08–21:21:32 | 3 / 4 | 9 | 2 | 7 |
| `ses_f2fd31507ffeox6tR1Lp6H61DJ` | 2026-09-23 21:29:59–21:30:55 | 5 / 6 | 8 | 1 | 1 |
| `ses_f2fb54b58ffe0ZaTUfSFcpg3wJ` | 2026-09-23 22:02:32–22:12:09 | 11 / 12 | 42 | 10 | 2 |
| `ses_f2bc23762ffeoOkPYHAoqhwpwm` | 2026-09-24 16:26:54–17:16:08 | 19 / 20 | 57 | 4 | 5 |
| **Summe** | — | **82 / 91** | **359** | **45** | **24** |

### Marker-positive Text-Parts

- **8 Leak-bearing Text-Parts in 4 Sessions:** `ses_f309...`, `ses_f306...`, `ses_f302...` und `ses_f2bc...`.
- Die 8 Parts enthalten **35.643 Zeichen**. Das sind **54,15 %** aller 65.819 Text-Zeichen in den 45 glm2api-Text-Parts.
- Eine zusätzliche, grobe Union-Messung der strukturellen Marker-Spans ergibt ca. **30.567 Zeichen**; diese Zahl ist nur eine annähernde Payload-Messung, weil bei verschachtelten Fragmenten die semantische Grenze nicht immer eindeutig ist. Die exakte Part-Länge von 35.643 Zeichen ist die belastbare Obergrenze.
- **22** direkte `{"name":...,"arguments":...}`-Kandidaten: 20 balanciert, 2 unvollständig. Tool-Namen: 10 `write`, 12 `bash`.
- **57** literale `call_id`-Vorkommen: 56 JSON-ähnliche `call_id`-Objekt-Starts (48 balanciert, 8 malformed) und 1 gewöhnlicher Prosa-Erwähnung von `call_id`.
- **Transcript-Namen:** 40 `write`, 10 `bash`, je 1 `output_check`, `webfetch`, `opencode-sessions_db_stats` und `todowrite`; 2 `call_id`-Objektstarts haben keinen extrahierten `name`-Wert.
- **14** malformed Wrapper-Starts `{"tool_calls` ohne vollständiges `"tool_calls":`; der vollständig abgeschlossene Marker `{"tool_calls"` kommt in den DB-Text-Parts nicht vor.
- **Startformen:** In den DB-Text-Parts beginnen die Protokollkandidaten überwiegend mit `{"name"` oder `{"tool_calls`; standalone `[{"name"` kommt nicht vor. Transcript-Echos beginnen mit `User:`/`Assistant:` plus `[{"call_id"`.
- **0** DSML-/Legacy-Tag-Leaks (`<tool_call`, `<|DSML|`) in den Text-Parts.
- Die Form verteilt sich wie folgt:

| Form | Text-Parts | strukturelle Kandidaten | Befund |
|---|---:|---:|---|
| Bare `{"name":...,"arguments":...}` | 5 | 22 | 20 balanciert; zwei `write`-Objekte in einem ungeschlossenen 4.903-Zeichen-Part |
| Transcript-Echo `[{ "call_id": ..., "name": ..., "content": ... }]` | 5 | 56 JSON-Objekt-Starts | 48 balanciert, 8 malformed; meist `User:`/`Assistant:`-Echo |
| `{"tool_calls` / `{"tool_calls]}[]`-Fragmente | 2 | 14 | fehlende Quotes/Klammern, direkte Verkettung mit nächstem `{"name"` |
| DSML-/Legacy-Tag | 0 | 0 | nicht beobachtet |

### Tool-Parts mit `state.status='error'`

| Tool | Fehler | Anzahl | Klassifikation |
|---|---|---:|---|
| `read` | `File not found` (auch wenn eine URL/der falsche Pfad an `read` übergeben wurde) | 21 | Datei-/Pfad-/Agenten-Umgebungsfehler |
| `webfetch` | `Transport error (GET http://127.0.0.1:8931/configs/rules.json)` | 2 | lokaler Testserver-/Umgebungsfehler |
| `write` | `SchemaError(Missing key ["content"])` | 1 | ungültige Tool-Eingabe |
| **Proxy-/Parse-Fehler** | `Tool .* not found`, `No tool found`, JSON-/Protocol-Parsefehler | **0** | **keine gefunden** |

Damit sind alle 24 Tool-Fehler der Gegenklasse Datei/Umgebung/Tool-Eingabe zuzuordnen; es gibt keinen Runtime-Hinweis auf einen glm2api-Proxy- oder Parserfehler. Zusätzlich existieren zwei `MessageAbortedError`-Nachrichten, aber keine weiteren Proxy-/Parse-Fehler; sie sind nicht in den 24 Tool-Fehlern enthalten.

## Form der Leaks (konkrete Beispiele, gekürzt)

### 1. Bare Call-Objekte ohne Wrapper

Der 4.903-Zeichen-Part in `ses_f2bc...` beginnt direkt mit `{"name":"write","arguments":...}` und enthält ein zweites `{"name":"write","arguments":...}` innerhalb desselben noch nicht geschlossenen Blocks. Beide direkten Call-Objekte laufen bis zum Textende; es gibt keinen `tool_calls`-Wrapper.

- **Beobachtete Form:** `{"name":"write","arguments":{...}},{"name":"write","arguments":{...}`
- **Tool-Namen:** `write`, `write`
- **Bilanz:** 2 offene Objektklammern am Ende; kein valides Gesamtobjekt.
- **Ursache im Log:** Die benachbarten Raw-SSE-Texte sind 18.463 Zeichen (10 direkte `name`/`arguments`-Paare) bzw. 7.643 Zeichen (3 Paare); der DB-Part ist ein zusammengeführter Fragment-/Volltext-Rest.

### 2. Wrapper- und Array-Fragmentierung

In einem 14.459-Zeichen-Part folgen mehrere `write`-Objekte direkt aufeinander. Einmal stehen drei schließende Klammern vor dem nächsten `{"name"`, ein anderes Mal fehlt eine schließende Klammer. Danach folgt ein Transcript-Echo mit `call_id`-Objektstarts. Die vier direkten `name`/`arguments`-Objekte sind einzeln balanciert, der umgebende Wrapper-/Array-Rahmen nicht.

Ein Raw-Log-Block um 18:30:43 hat die Form `{"tool_calls":[{"name":"write","arguments":...}, ...` mit 10 `name`-Paaren, ist als Gesamttext aber nicht balanciert. `Response finalize` meldet dort 6 `tool_calls`; die Rohstruktur enthält mehr Kandidaten als die finalisierte Tool-Liste.

### 3. Transcript-Echo

Der 2.044-Zeichen-Part in `ses_f2bc...` enthält nach normalem Prosa-Text:

```text
User: [{"call_id":"call_webfetch_rules","name":"webfetch","content":"{ ... }"}]
User: [{"call_id":"call_pkill_8931","name":"bash","content":"stopped\n"}]
```

Das sind keine neuen Tool-Aufrufe, sondern vom Modell halluzinierte interne Transcript-Daten. Vier solche Records sind balanciert. Der Record mit `content` und `name` ist ein Tool-Result-Echo; er darf nicht als Assistant-Antwort sichtbar bleiben.

### 4. Fehlerhafter Wrapper-Präfix

Der 8.355-Zeichen-Part enthält sowohl einen balancierten Transcript-Record als auch den eindeutig kaputten Präfix:

```text
Tests schreiben mit `write`.{"tool_calls{"content":"...","filePath":"..."}}
```

und am Ende:

```text
{"tool_calls]}[]\n\nIch verwende ab jetzt ausschließlich `bash`.
```

Hier fehlen mindestens Quote, Doppelpunkt und/oder Array-/Object-Klammer. Ein Parser, der nur `{"tool_calls":` sucht, erkennt diese Variante nicht.

### 5. Stream-/Chunk-Grenze

Die Logs zeigen direkt aufeinanderfolgende Raw-SSE-Fragmente wie:

```text
Assistant: {"tool_calls":[{"name
User: [{"call_id":"call_webfetch_rules
```

bzw. `{"name":"write","arguments":...` in einem späteren Chunk. Der sichtbare DB-Part enthält die resultierenden Transcript-Fragmente. Die JSON-Tests unten müssen deshalb sowohl als kompletter Finaltext als auch chunkweise wiedergegeben werden.

## Korrelation mit Debug-Logs

### Logabdeckung und Session-Zuordnung

| Logdatei | Logger-Zeitfenster |
|---|---|
| `glm2api_debug.log.5` | 2026-09-24 01:16:56–01:19:51 |
| `glm2api_debug.log.4` | 2026-09-24 01:19:51–18:29:57 |
| `glm2api_debug.log.3` | 2026-09-24 18:29:57–18:32:32 |
| `glm2api_debug.log.2` | 2026-09-24 18:32:32–18:37:35 |
| `glm2api_debug.log.1` | 2026-09-24 18:37:35–18:41:09 |
| `glm2api_debug.log` | 2026-09-24 18:41:09–21:55:29 |

Von den neun DB-Sessions ist nur `ses_f2bc23762ffeoOkPYHAoqhwpwm` in den Headern der erhaltenen Logs exakt vorhanden. Für diese Session wurden 20 Inbound-Requests mit `x-session-id` und 21 `Response finalize`-Zeilen gefunden. Die übrigen acht Sessions liegen am 2026-09-23 zwischen 17:48 und 22:12 UTC und damit außerhalb der erhaltenen Logabdeckung; generische Benchmarktexte in den Logs wurden nicht als eindeutiger Session-Match verwendet.

### `Response finalize` für die exakt passende Session

| Zeit | Log / Zeile | status | text_len | tool_calls | text_len / max(tool_calls,1) |
|---|---|---|---:|---:|---:|
| 18:26:57 | `.4:28810` | finish | 41 | 0 | 41 |
| 18:28:15 | `.4:40763` | finish | 86 | 1 | 86 |
| 18:28:37 | `.4:48737` | finish | 1082 | 1 | 1082 |
| 18:28:50 | `.4:52991` | finish | 448 | 1 | 448 |
| 18:29:25 | `.4:70498` | finish | 4658 | 8 | 582 |
| 18:29:36 | `.4:74392` | finish | 333 | 3 | 111 |
| 18:30:43 | `.3:43426` | finish | 18463 | 6 | 3077 |
| 18:31:28 | `.3:71902` | finish | 7643 | 2 | 3822 |
| 18:31:52 | `.3:84060` | finish | 236 | 2 | 118 |
| 18:33:23 | `.2:37979` | finish | 13259 | 6 | 2210 |
| 18:33:43 | `.2:45998` | finish | 224 | 1 | 224 |
| 18:33:54 | `.2:49972` | finish | 194 | 1 | 194 |
| 18:37:00 | `.2:66186` | finish | 0 | 0 | 0 |
| 18:37:34 | `.2:81940` | finish | 420 | 2 | 210 |
| 18:37:49 | `.1:5930` | finish | 121 | 1 | 121 |
| 18:38:05 | `.1:9090` | finish | 124 | 1 | 124 |
| 18:39:03 | `.1:37384` | intervene | 0 | 0 | 0 |
| 18:40:09 | `.1:57029` | finish | 142 | 1 | 142 |
| 18:41:24 | `current:8583` | finish | 4483 | 6 | 747 |
| 19:16:08 | `current:16257` | finish | 1098 | 1 | 1098 |
| 19:16:20 | `current:21912` | finish | 238 | 0 | 238 |

**Auffällige `text_len`-Werte:**

- 7/21 Finalizes haben `text_len >= 1000`; 3/21 haben `text_len >= 5000`.
- 3/21 haben `text_len >= 1000` und höchstens 2 `tool_calls`.
- 5/21 haben `text_len / max(tool_calls,1) >= 1000`: 18:28:37 (1082/1), 18:30:43 (18463/6), 18:31:28 (7643/2), 18:33:23 (13259/6), 19:16:08 (1098/1).
- Der Leak-korrelierte 18:41:24-Fall hat 4483 Zeichen bei 6 Calls; der absolute Wert ist hoch, der Verhältniswert 747 liegt knapp unter der 1000er-Schwelle.
- Hoher `text_len` allein ist kein sicherer Leak-Beweis: 18:31:28 und 18:33:23 zeigen im Raw-SSE ebenfalls große Tool-JSON-Payloads, aber der korrespondierende DB-Text-Part enthält keinen Marker. 18:30:43 und der 18:40:59–18:41:24-Block sind dagegen direkt mit den persistierten Leak-Parts korreliert.

### Konkrete Rohlog-Korrelation

- **18:30:43:** `GLM raw SSE block` ist 18.463 Zeichen, beginnt mit `{"tool_calls":[{"name":"write"...`, enthält 10 `name`/`arguments`-Paare und ist nicht valide balanciert. `Response finalize` meldet `text_len=18463 tool_calls=6`. Der 4.903-Zeichen-DB-Part ist ein daraus und dem 7.643-Zeichen-Folgeblock zusammengeführter Rest. Der 4.903-Zeichen-Text erscheint als History-Inhalt in `glm2api_debug.log.3:43487` (18:30:45).
- **18:40:59–18:41:15:** Raw-SSE-Fragmente enthalten `Assistant: {"tool_calls"...` und `User: [{"call_id"...`-Echoes. Der 18:41:15-Block ist 3.467 Zeichen, hat 5 Wrapper-Starts, 5 direkte `name`-Paare und 4 `call_id`-Vorkommen. Der 2.044-Zeichen-DB-Part ist ein daraus sichtbar geblieberener Transcript-Rest. `Response finalize` um 18:41:24 meldet `text_len=4483 tool_calls=6`; der 2.044-Zeichen-Text erscheint erneut in der History unter `glm2api_debug.log:8656` und `:16298`.
- **18:31:27/28:** 7.643 Zeichen, 3 direkte Call-Objekte, aber malformed/fragmentiert. Dieser Fall ist ein Beispiel für einen Parser-Fehlversuch, obwohl der korrespondierende DB-Part selbst nicht als marker-positive Text-Part gespeichert wurde.

### Warnungen

Im exakten Zielzeitfenster gibt es 23 echte GLM-Warn-Header:

- 21 `Stream turn ended`-Warnungen, jeweils passend zu den 21 Finalize-Zeilen: 20 mit `status=finish` (19 mit `blocked=[]`, 1 mit `blocked_follow_ups=1`) und 1 mit `status=intervene`. Die jeweils zugehörigen Warnzeilen stehen im Log unmittelbar nach den Finalize-Blocks; die zwei zusätzlichen Blocked-Tool-Zeilen sind unten mit Datei und Zeile genannt.
- Alle 21 `Stream turn ended`-Header (der jeweils passende Eintrag ist damit vollständig referenziert):

  | Zeit | Log / Zeile | Header-Meldung |
  |---|---|---|
  | 18:26:57 | `.4:28816` | `Stream turn ended status=finish blocked=[] blocked_follow_ups=0 max_blocked=2` |
  | 18:28:15 | `.4:40772` | `Stream turn ended status=finish blocked=[] blocked_follow_ups=0 max_blocked=2` |
  | 18:28:37 | `.4:48745` | `Stream turn ended status=finish blocked=[] blocked_follow_ups=0 max_blocked=2` |
  | 18:28:50 | `.4:52999` | `Stream turn ended status=finish blocked=[] blocked_follow_ups=0 max_blocked=2` |
  | 18:29:25 | `.4:70513` | `Stream turn ended status=finish blocked=[] blocked_follow_ups=0 max_blocked=2` |
  | 18:29:36 | `.4:74402` | `Stream turn ended status=finish blocked=[] blocked_follow_ups=0 max_blocked=2` |
  | 18:30:43 | `.3:43439` | `Stream turn ended status=finish blocked=[] blocked_follow_ups=0 max_blocked=2` |
  | 18:31:28 | `.3:71910` | `Stream turn ended status=finish blocked=[] blocked_follow_ups=0 max_blocked=2` |
  | 18:31:52 | `.3:84069` | `Stream turn ended status=finish blocked=[] blocked_follow_ups=0 max_blocked=2` |
  | 18:33:23 | `.2:37993` | `Stream turn ended status=finish blocked=[] blocked_follow_ups=0 max_blocked=2` |
  | 18:33:43 | `.2:46006` | `Stream turn ended status=finish blocked=[] blocked_follow_ups=0 max_blocked=2` |
  | 18:33:54 | `.2:49980` | `Stream turn ended status=finish blocked=[] blocked_follow_ups=0 max_blocked=2` |
  | 18:37:00 | `.2:66196` | `Stream turn ended status=finish blocked=[] blocked_follow_ups=0 max_blocked=2` |
  | 18:37:34 | `.2:81949` | `Stream turn ended status=finish blocked=[] blocked_follow_ups=0 max_blocked=2` |
  | 18:37:49 | `.1:5938` | `Stream turn ended status=finish blocked=[] blocked_follow_ups=0 max_blocked=2` |
  | 18:38:05 | `.1:9098` | `Stream turn ended status=finish blocked=[] blocked_follow_ups=0 max_blocked=2` |
  | 18:39:03 | `.1:37392` | `Stream turn ended status=intervene blocked=['open'] blocked_follow_ups=0 max_blocked=2` |
  | 18:40:09 | `.1:57040` | `Stream turn ended status=finish blocked=[] blocked_follow_ups=1 max_blocked=2` |
  | 18:41:24 | `current:8599` | `Stream turn ended status=finish blocked=[] blocked_follow_ups=0 max_blocked=2` |
  | 19:16:08 | `current:16265` | `Stream turn ended status=finish blocked=[] blocked_follow_ups=0 max_blocked=2` |
  | 19:16:20 | `current:21918` | `Stream turn ended status=finish blocked=[] blocked_follow_ups=0 max_blocked=2` |

- Zusätzlich um 18:39:03: `Intercepted blocked native tool call tool=open` (`.1:37383`) und `Model attempted blocked tool(s) open; starting negative-result follow-up` (`.1:37393`).
- Im selben breiten Zeitfenster liegt zusätzlich ein Testlog `DOPPEL-TEST-ZEILE` (`.2:22920`, 18:33:05); dieser ist nicht der glm2api-Session zuzuordnen.
- In den echten Log-Headern wurde **kein** `Stripped ...`, `Sanitized ...`, `Filtered unsupported tools`, `No tool found` oder Protocol-Parsefehler gefunden. Das Fehlen dieser Cleanup-Meldungen bei gleichzeitig sichtbaren DB-Leaks ist ein starkes Indiz für eine nicht ausgelöste bzw. nicht ausreichende Cleanup-Regel.

## Empfohlene Parser-Regeln

1. **Toleranten Opener erkennen und chunk-sicher halten.** Nicht nur `{"tool_calls":`, sondern auch `{"tool_calls`, `{"tool_calls]`, `{"tool_calls}`, Whitespace-/Zeilenumbruchvarianten und einen nachfolgenden `[]`/`[]}[]`-Terminator als Protokollkandidat behandeln. Ein Opener darf niemals sichtbar ausgegeben werden, solange der Stream noch unvollständig ist. Das schließt die aktuelle Lücke zwischen `_TOOL_CALLS_PROTOCOL_RE` in `tool_parser.py:15` und den Partial-Holdback-Proben ab Zeile 1047.
2. **Bare Objects/Arrays an jeder strukturellen Grenze parsen.** `{"name":...,"arguments":...}` darf nach Text, Komma, Array-Klammer, abgeschlossenem Object oder Stream-Chunk beginnen. Fehlende `}`/`]` zwischen Sibling-Calls anhand des nächsten `{"name"`-/`{"call_id"`-Starts rekonstruieren. Die Erkennung darf nicht auf die aktuelle Zeilenanker-Regel in `tool_parser.py:719` beschränkt bleiben.
3. **Transcript-Echo zustandsbehaftet entfernen.** `User:`/`Assistant:` plus `[{"call_id"...` auch mitten in einer Zeile, ohne `name`, mit `content_truncated`, `calloutput?` und kaputtem Array erkennen. Der gesamte Echo-Block, nicht nur die Zeile mit dem Präfix, muss entfernt werden. Die aktuellen Muster in `tool_parser.py:726–735` und `translator.py:453–471` sind zu stark zeilen- und schemaabhängig.
4. **Raw-Volltext/Token-Duplikate vor dem Parsen mergen.** Wenn ein Buffer aus einem Fragment plus anschließendem Volltext besteht, den Volltext idempotent auswählen und nicht den kompletten Payload nochmals anhängen. Die Logfolge 18:30:43/18:31:27 zeigt, dass der resultierende sichtbare Part über mehrere Raw-Blöcke verteilt war.
5. **Fehlgeschlagene Protokollkandidaten fail-closed behandeln.** Wenn ein Kandidat `name`/`arguments` oder `call_id` enthält, aber nicht valide ist, darf der rohe Kandidat nicht als normaler Text durchfallen. Stattdessen fragmentweise entfernen oder als blockierten/parse-failed Attempt markieren; `strip_unparseable_call_fragments` in `tool_parser.py:1230–1259` muss auch mitten im Text und bei Wrapper-/Sibling-Fehlern arbeiten.
6. **Schema- und Allowlist-Prüfung nach strukturellem Scan.** Nur Quotes-/Escapes-korrekt erkannte Call-Objekte mit erlaubtem Tool-Namen und plausiblen Argumenten als Calls ausführen. `call_id`-Records mit ausschließlich `content` oder unbekanntem `name` sind Transcript-Reste und dürfen nicht als Tool-Call interpretiert werden.
7. **Diagnose-Metriken ergänzen.** Pro Turn `raw_tool_candidates`, `parsed_calls`, `dropped_fragments`, `visible_tool_markers` und `text_len/tool_calls` protokollieren. Ein `text_len`-Ausreißer sollte einen Parser-Audit auslösen, aber nicht allein als Fehler gewertet werden.

## Teststrings für Regressionstests (5 Beispiele)

Die Beispiele übernehmen die beobachtete Schlüsselreihenfolge und die kaputte Terminierung. Nur lange Nutzdaten wurden durch `<PATH>`/`<CONTENT>` ersetzt; sie sind keine Secrets.

1. **Bare, ungeschlossene Sibling-Calls** (aus dem 4.903-Zeichen-Part):

   ```text
   {"name":"write","arguments":{"filePath":"<PATH>","content":"<CONTENT>"},{"name":"write","arguments":{"filePath":"<PATH>","content":"<CONTENT>"}
   ```

   Erwartung: zwei Call-Kandidaten rekonstruieren, keinen sichtbaren JSON-Text ausgeben und den fehlenden Schluss als Fragment behandeln.

2. **Wrapper mit Sibling-Objects und kaputtem Terminator** (aus dem 14.459-Zeichen-/Raw-SSE-Muster):

   ```text
   {"tool_calls":[{"name":"write","arguments":{"filePath":"<PATH>","content":"<CONTENT>"}},{"name":"write","arguments":{"filePath":"<PATH>","content":"<CONTENT>"}}]}[] 
   ```

   Erwartung: alle gültigen Calls extrahieren, überzählige/fehlende Klammern und `[]` ohne sichtbaren Rest verbrauchen.

3. **Transcript-Echo mit `call_id`** (aus dem 2.044-Zeichen-Part):

   ```text
   User: [{"call_id":"call_webfetch_rules","name":"webfetch","content":"{\"max_error_rate\":0.4}"}]
   ```

   Erwartung: Echo vollständig entfernen, weder `webfetch` ausführen noch `call_id` als Textantwort ausgeben.

4. **Malformed Opener plus Terminalfragment** (aus dem 8.355-Zeichen-Part):

   ```text
   Tests schreiben mit `write`.{"tool_calls{"content":"<CONTENT>","filePath":"<PATH>"}} ... {"tool_calls]}[]\n
   ```

   Erwartung: beide Fragmentvarianten als Protokoll erkennen, strippen/als fehlerhaft markieren und den umgebenden Prosa-Text erhalten.

5. **Chunk-Grenze** (aus den Raw-SSE-Fragmenten um 18:40:59):

   ```text
   chunk1 = Assistant: {"tool_calls":[{"name
   chunk2 = :"bash","arguments":{"command":"pwd"}}]}]
   ```

   Erwartung: beim Zeichen-/Chunk-Replay darf `chunk1` nicht sichtbar werden; nach `chunk2` muss genau ein `bash`-Call mit `{"command":"pwd"}` resultieren.
