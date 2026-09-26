# glm2api — Optimierungs-Arbeitsdatei (lebendiges Dokument)

Zweck: Zentrale Anlaufstelle für offene Probleme und geplante/zu-
laufende Optimierungsarbeiten. **Neue Sessions/Agenten: zuerst hier lesen** —
steht unten ein Thema auf OFFEN, ist genau das Arbeitsfeld.

Status-Legende: DONE (fix + regressionstest + commit) · OFFEN (zu tun) ·
BEACHTEN (kein Fix nötig/sinnvoll, nur beobachten).

---

## Kontext des Härtetests (Stand 2026-09-11)

Vier Benchmark-Läufe (~500 Tool-Calls) haben 5 Proxy-Bug-Klassen aufgedeckt —
alle DONE (Commits 3cd794e, c33da91, fea9c22/79fca84, 7a2a2cd, efbc2e7).
92/92 Tests. Proxy-Ebene: 100% Tool-Call-Ausführung, 0 Leaks nach letztem Fix.
Details inkl. Live-Leak-Strings sind in Git (Commit 1039311) dokumentiert.

---

---

## THEMA 4 — Komplett-Audit Ordner-Review (DONE 2026-09-24)

Systematische Durchsicht des gesamten Ordners (Code, Config, Doku, Tests,
Runtime-Artefakte). Gefunden und behoben:

**Echte Bugs**
- Doppel-Logging: `load_config()`-Handler auf dem `glm2api`-Logger wurde von
  `setup_logging()` nicht entfernt → jede Logzeile doppelt (plain + TUI).
  Regressionstest in test_config.py.
- `repair_raw_tool_args()` mit `unicode_escape` verderbte echtes UTF-8
  (→ THEMA 3, dort dokumentiert).
- `compress_history_messages()` Off-by-one: die budget-sprengende Message
  blieb vollständig roh erhalten statt summarisiert (Budget um ein Vielfaches
  überschritten). Jetzt: fällt in die Summary, außer sie ist die neueste.
- SSE-Parser normalisierte `\r\n` pro Chunk statt auf dem akkumulierten
  Puffer; ein Paar über die 4096er-Grenze blieb unerkannt → Events gingen
  als „unparseable fragment" verloren.
- Bare-Array-Holdback im StreamingParser war tot bzw. Prefix-verwerfend
  (`return "", text[start:]`): sichtbarer Text vor einem unvollständigen
  Array wurde verworfen. Drei Stellen korrigiert + Regressionstests.
- `usage` war ein 1/1/2-Platzhalter → jetzt grobe Schätzung (~4 Z./Token).

**Konsistenz / Bloat**
- Dead Code: ~55-zeiliger unerreichbarer „think-Feld"-Block in
  `_split_stream_text`, `CHAT_MODE_DEEP_THINKING`,
  `_conversation_has_tool_round` (nur von einem Test genutzt),
  `_is_partial_protocol_suffix`, `SERVER_SIDE_TOOL_NAMES`-Leer-Maschinerie
  (3 Funktionsschichten), Identity-`model_aliases`, `safe_json_dumps`-No-op.
- Duplikate: doppelter `extract_history_tool_call_signatures`-Aufruf,
  zweimal kopiertes `blocked_tool_follow_up_payload` (jetzt geteilte
  Helfer `_build_blocked_tool_follow_up_payload` / `_halve_history_budget`),
  doppeltes `_safe_json`/`_pad_name`.
- Streaming-Parität: `/v1/messages` und `/v1/responses` teilen jetzt
  `_run_accumulated_sse_stream` (Heartbeat + spec-konforme Error-Events;
  vorher schwie /v1/messages bei Midstream-Fehlern).
- PowerShell-Rewrites (Legacy aus dem Windows-Ursprungsprojekt) entfernt —
  auf Linux hätten sie `shell`-Commands in `powershell.exe`-Aufrufe
  umgeschrieben. `web.search` in `BLOCKED_NATIVE_TOOL_NAMES` ergänzt.
- Private-Zugriffe (`accumulator._finish()`, `._render_full_output()`) durch
  public `finish()` / `render_full_output()` ersetzt.
- `.env.example` synchronisiert (6 undokumentierte Vars, falsche
  Kommentare), `GLM_IMAGE_MODEL_NAME` konfigurierbar gemacht,
  `.gitignore`-Leichen (`docs`, `main.spec`, `tokenizer.json`) entfernt.
- 1,4-GB-Totlog `log/glm2api_output.log` gelöscht (seit 22.9. tot, von
  keinem Skript referenziert).

Status: **DONE** (141/141 Tests grün).

---

## THEMA 5 — Roh-Tool-Calls & Halluzinations-Echo im Antworttext (DONE 2026-09-24)

### Symptom

Benchmark-Session `ses_f2bc23762ffeoOkPYHAoqhwpwm` (18:26–19:16) lief
erfolgreich durch, lieferte aber hässliche Antworten:

- **4903 Zeichen** rohes `{"name":"write","arguments":{...}}-JSON` im
  sichtbaren Text (2 abgeschnittene Call-Fragmente, u.a. `log_parser.py`,
  `reporter.py`) → opencode Execute-Host PipeError, Agent musste die
  Dateien neu schreiben
- **1615 Zeichen** python-Code-Fragment (`{'...`) — ebenfalls Tail eines
  abgeschnittenen Write-Calls
- **2044 Zeichen** halluziniertes Konversations-Echo: das Modell schrieb
  `User: [{"call_id":"call_webfetch_rules",...}]` (sein eigenes internes
  Transcript-Format) mit erfundenen call_ids in die Antwort

### Ursachen

1. `tool_parser._BARE_ARRAY_START_RE` verlangte `[` oder `,` vor
   `{"name":`. Das Modell lieferte die Calls aber **ohne** `tool_calls`-Wrapper
   und **ohne** Array-Klammern, direkt am Zeilenanfang/Textanfang
   (`{"name":"write",...}`) bzw. nach `\n`. Der Parser erkannte nur die
   *zweiten* Objekte (nach `,`) — das erste Fragment fiel durch und wurde
   als sichtbarer Text gestreamt.
2. Der Upstream brach den Stream **mitten im JSON** ab (unbalancierte
   Klammern). Beim `finalize` war der Text dann nicht mehr parsebar →
   `parse_tool_calls_from_text` gab den Rohtext zurück.
3. Das Echo ist ein Modell-Verhalten (Prompt-Format halluziniert), kein
   Parser-Bug — brauchte einen eigenen Filter.

### Fix

- `_BARE_ARRAY_START_RE` / `_NAKED_WRITE_START_RE`: erlauben nun
  `^` (Textanfang) und `\n` (Zeilenanfang) als Präfix → erste Fragmente
  werden erkannt und **zurückgehalten** statt gestreamt.
- `_split_stream_text` Schritt 0: `User:`/`Assistant:`-Zeilen mit JSON-Call
  werden chunk-grenzenübergreifend zurückgehalten (Prefix-Holdback +
  `_find_transcript_echo_span` mit JSON-Balance-Scan) und bei `final`
  entfernt — legitimer Text **danach** bleibt erhalten.
- `strip_unparseable_call_fragments()`: Final-Safety-Net für
  Stream-abgebrochene, unparsebare Call-Fragmente (mit Log-Warnung).
- `strip_transcript_echo()`: entfernt Echo-Zeilen im finalen Text
  (Stream + Non-Stream), mit Log-Warnung.

### Verifikation

- **Reproduktion mit echten Daten**: 4903/1615/2044-Zeichen-Leak-Texte aus
  der Session-DB in den echten `GLMEventAccumulator` gefüttert → alle drei
  liefern jetzt **0 Zeichen** Fragment-Leak.
- **Echte Log-Runde** (205 SSE-Events, 18:29): 8 korrekte write/todowrite-Calls,
  **0 Bytes** sichtbarer Müll-Text (vorher ~4658 Zeichen).
- 150/150 Tests grün (7 neue Regressionstests mit Live-Texten).
- Chunk-Grenzen-Robustheit geprüft: 40–4096 Bytes sauber (3–17 Bytes sind
  ein theoretischer Extremfall mit Rest-Leck, keine echte SSE-Größe).

Status: **DONE — der upstream-stream bricht gelegentlich mitten im JSON ab;
der proxy faengt das jetzt ab, statt es als antwort durchzulassen.**

### THEMA 6 — Chunk-stabile Call-Erkennung (DONE 2026-09-24, aus glm2api-revision.md)

Die Call-Erkennung hing an der Chunk-Grenze: Holdback und Voll-Erkennung
benutzten zwei verschiedene Grammatiken. Behoben durch einen JSON-Struktur-
Scanner (`_find_unterminated_call_start`), der im `consume()` vor allen
format-spezifischen Pfaden laeuft. Zusaetzlich: `allowed_tool_names=None`
erzeugt keine Calls mehr (Recovery nur explizit via `detect_all=True`),
blockierte Versuche werden auch in Bare-Formen erkannt, und ein gemischter
Turn aus erlaubten und blockierten Calls liefert die erlaubten aus.

Verifikation: Paritätsmatrix ueber 4 Payload-Formen und 6 Chunk-Groessen
sowie die drei echten Leak-Texte der Benchmark-Session bei 1 bis 512 Byte
— ueberall 0 Zeichen Fragment-Leak. Details in `glm2api-revision.md` Teil F.

### THEMA 7 — P1-Gruppe aus dem Voll-Audit (DONE 2026-09-24)

Die zweite Welle des Audits (P1) ist umgesetzt: 18 Befunde aus Parser,
Translator, Client und Server. Schwerpunkte: quelluebergreifende
Call-Deduplizierung, generische `<tool_call>`- und Fence-Erkennung,
echte `None`-Semantik fuer leere Tool-Listen, Follow-up-Kontext in
Retries, sowie `finish_reason: error` statt Schein-Erfolg bei blockiertem
Protokoll. 188 Tests gruen. Vollstaendige Liste: `glm2api-revision.md` Teil F-5.

---

## THEMA 1 — Kontext-Management für Lang-Agent-Sessions (ERLEDIGT 2026-09-11, Beobachtung läuft)

### Umsetzung (P1) — Historien-Kompression + 10040-Auto-Retry + Leer-Turn-Auto-Retry

- **H1-Kompression**: `compress_history_messages()` in translator.py —
  Historie VOR der Konvertierung auf Budget begrenzen (von NEU nach ALT
  sammeln, assistant+tool-Paare nie trennen, ältere Runden zu einem
  summarischen Eintrag verdichten). Konfigurierbar: `GLM_HISTORY_MAX_CHARS`
  (Default 120000, 0 = aus).
- **10040-Auto-Retry**: chatglm.cn lehnt bei "model response context
  exceeded" (code 10040) ab — jetzt transient; Retry halbiert das Budget
  (`_glm_history_budget` im Payload) bis der Upstream mitmacht (min 20k).
  Beide Pfade (stream + non-stream).
- **Leer-Turn-Auto-Retry** (Autonomie-Fix): `is_empty_response()` im
  Accumulator erkennt komplett leere Upstream-Runden (text=0, reasoning=0,
  calls=0 — zuvor blieb der Agent genau dort STEHEN, z.B. Stresstest
  10:21). glm_client retryt automatisch mit frischer Conversation, BEVOR
  die leere Antwort den Client erreicht. Config:
  `GLM_EMPTY_RESPONSE_MAX_RETRIES` (Default 2). Kondition: nur wenn noch
  kein Content gestreamt wurde (sonst wäre der Retry unsauber).

### Verifikation (P2)

Autonomie-Lauf (agent-glm2api-hard6, Session ses_f6fc7bff6ffevWATNhrlzCPTYO):
ALLE Phasen 0-10 durchgelaufen, ~86 Upstream-Runden, 171 Tool-Parts,
0 Ausführungsfehler, Kompression live (268→52 Messages), keine
Resume-Schubser während der Arbeit, kein Drift, keine Loops.
Vorher (ohne Fix): alle 2h-Läufe brauchten 4-6 Schubser und standen
an Leer-Turns komplett still.

Status: **ERLEDIGT — BEACHTEN** (in künftigen Langläufen auf
"Empty GLM response — auto-retrying"-Logzeilen und 10040-Halbierungen
achten; Budget ggf. tunen).

## THEMA 2 — Tool-Halluzination: GLM ruft nicht-existente Tools auf (DONE 2026-09-22 / ERWEITERT 2026-09-24)

### Symptom

GLM-5.3 halluziniert Tool-Calls (`open_url`, `browse`, `web.search`, `execute_sandbox_code` etc.),
obwohl diese nicht in der Tool-Liste stehen. Der Proxy blockiert sie korrekt
(bounded Follow-up, max 2 Runden), aber das Modell ignorierte die alte
System-Instruktion ("no open_url") und halluzinierte persistent weiter.
Ergebnis: alle Follow-up-Runden verbraucht, Fehlermeldung an Client.
Zusätzlich: Bei Code-Ausführung rief GLM nativ `execute_sandbox_code` (ChatGLM-Builtin) auf
und geriet in eine 5-Runden-Schleife, bis es mit einer erfundenen Ausrede ("Rundenlimit 5/5") abbrach.

### Root Cause

1. Der alte System-Prompt in `build_tool_call_instructions()` erwähnte das
   Verbot nur beiläufig in einer Zeile ("No other tools exist — no browser,
   no open_url, no web.search"). Zu schwach für GLM-5.3, das nach Tool-Result-
   Runden die Format-Disziplin verliert.
2. `execute_sandbox_code` fehlte in `BLOCKED_NATIVE_TOOL_NAMES` und hatte kein
   Mapping auf `bash`.

### Fix (tool_protocol.py, translator.py, glm_client.py)

1. **`build_tool_call_instructions()`**: Restrukturiert mit eigener Sektion
   `## CRITICAL: Tool-call hallucination prevention` — listet alle
   `BLOCKED_NATIVE_TOOL_NAMES` explizit auf, warnt vor Rejection + Runden-
   Verlust, fordert Verifikation vor dem Emit. Explizite Regel: Code-Ausführung
   nur über `bash`.
2. **`TOOL_FORMAT_REMINDER`** (Re-Anchor nach Tool-Result-Runden): Explizites
   Verbot von `open_url`, `browse`, `web.search`, `execute_sandbox_code`;
   Instruktion, für Python/Tests `bash` zu nutzen.
3. **`tools_to_prompt()`** Schema-Header: "authoritative" → "COMPLETE and
   EXHAUSTIVE", plus "Do not guess, infer, or invent any tool names."
4. **`map_native_sandbox_tool_call()`** in `translator.py`: Wandelt native
   `execute_sandbox_code(code=...)`-Aufrufe transparent in `bash(command="python3 - << 'EOF'\n{code}\nEOF")`
   bzw. Direktschalenbefehle um, wenn `bash` erlaubt ist.
5. **`BLOCKED_NATIVE_TOOL_NAMES`**: Um `execute_sandbox_code`, `code_interpreter`,
   `sandbox`, `run_code` erweitert.

Status: **DONE** (111/111 Tests grün zum damaligen Stand; inzwischen 141).

---

## THEMA 3 — Encoding-Verderb: Umlaute → Steuerzeichen (DONE 2026-09-24)

### Symptom

Selten (2 Vorfälle auf ~500 Calls) schreibt das Modell per write-Tool
Dateien, in denen statt `ü` die Steuerzeichen U+0014/U+0005 landen
(io_utils.py: `zurück` → kaputt). Die JSON-Tool-Argumente sind syntaktisch
valide — nur der INHALT ist kaputt. Proxy reicht sie unverändert durch.

### Root Causes (beim Audit gefunden)

1. Der `_raw`-Reparaturpfad in `repair_raw_tool_args()` dekodierte den
   Roh-String mit `bytes.decode("unicode_escape")` — das hat
   Latin-1-Semantik und verderbte echtes UTF-8 (`hübsch` → `hÃ¼bsch`).
   Behoben: JSON als primärer Decoder, Regex-Single-Pass als Fallback
   (`_decode_escaped_text()`); niemals mehr `unicode_escape`.
2. Der Upstream kann ein gültiges JSON-Escape `\u0014` für ein verunglücktes
   Zeichen streamen; dieses materialisierte bisher ein echtes Steuerzeichen
   (exakt das beobachtete `zur\x14ck`).

### Fix (F1–F4 aus dem Design umgesetzt)

- F1+F2: `sanitize_control_characters()` / `_sanitize_value_control_chars()`
  in translator.py — C0-Steuerzeichen (außer `\n\t\r`) und DEL werden in
  Tool-Argumenten (rekursiv) und sichtbarem Content (Stream-Deltas,
  Final-Text, `intervene_text`, Non-Stream-Response) durch `?` ersetzt.
- F3: Jede Bereinigung wird geloggt (Tool-Name + Anzahl + gefundene
  Zeichen bzw. "control characters in visible response text").
- F4: Regressionstests in tests/test_translator.py — Steuerzeichen werden
  ersetzt, echtes UTF-8 (Umlaute, CJK, Emoji) bleibt unangetastet.

### Verifikation

141/141 Tests grün (Stand 2026-09-24, inkl. 25 neuer Regressionstests aus
dem Komplett-Audit). Akzeptanzkriterium erfüllt: kein C0-Steuerzeichen
(außer `\n\t\r`) in Tool-Argumenten oder sichtbarem Content, echtes UTF-8
unberührt, jede Bereinigung geloggt.

Status: **DONE — BEACHTEN** (Häufigkeit in kommenden Läufen über die
`Sanitized control characters`-Logzeilen tracken).

---

## THEMA 8 — Live-Session-Test 2026-09-26: drei Stream-Bugs (DONE 2026-09-26)

Drei Fehlerklassen, die ausschliesslich im **echten opencode-Betrieb**
auftraten und von keinem bestehenden Test abgedeckt waren. Alle drei kamen
aus demselben Grund: die Tests prüften den *gecachten Volltext*
(`build_response().content`), nicht das, was **im Stream** beim Client
ankommt. Der cached text war in allen Fällen korrekt — der Stream nicht.

### S-05 — Sichtbarer Text in falscher Reihenfolge (Textverlust/Duplikat)

**Symptom (live, session `glm2api limited 3`):** die Schlussantwort kam
umgestellt und mit Textverlust an:

```
Alle 3 Schritte sind abgeschlossen:
1. **URL-Inhalt** (`http://127.0.0.1:8899/data.txt`, geholt via2. **README-Prüfung** (via `read`): …
3. **Ergebnisdatei**: … geschrieben (erfolgreich bestätigt).`bash` + `curl`):
   ```
   alpha
   ```
```

Der Absatz nach dem Code-Fence stand **hinter** dem restlichen Text, der
Abschnitt mitten im Satz war abgeschnitten.

**Ursache:** zwei Senken ohne Reihenfolge-Garantie. `_deferred_visible_text`
(puffert, wenn ein Fence offen ist / der Parser hält / ein Protokollfragment
im Delta steckt) und der direkte Stream. Sobald ein Delta in den Puffer ging,
konnte der nächste direkt raus — und der Puffer wurde erst im `finalize`
angehängt, also **hinter** allem. Auslöser live: ein Fence, das **mitten in
einem Delta** geschlossen wurde (`fence_pending` war für dieses Delta noch
wahr). Reproduziert bei **15 von 15** Chunk-Größen, mit Textverlust *und*
Duplikaten (chunk=5 gab den Text zweimal aus).

**Fix:** ein einziger geordneter Sensen für sichtbaren Text. Vor jedem
direkten Emit wird der Puffer geleert; ist er noch nicht „sauber"
(offener Fence / Protokollfragment), bleibt die Zurückhaltung **sticky**,
damit die Reihenfolge gewahrt bleibt. Zusätzlich `_deferred_text_is_publishable()`.

### S-06 — Leerzeilen-Artefakt neben Tool-Calls

**Symptom (live, 8 parallele `read`s):** der Client bekam einen Text-Part,
der aus **12 Leerzeilen** bestand — eine leere assistant-Nachricht in der TUI
und dauerhafter Ballast im Kontext.

**Ursache:** glm-5.3 liefert neben jedem nativen `tool_calls`-Part eine eigene
Text-Part, die nur aus Whitespace besteht. Der Part-Merge setzte an **jeder**
`logic_id`-Grenze zusätzlich einen Absatzumbruch. Reproduziert: 7 Calls →
14 Leerzeilen im Stream. (Eine **leere** Part ist nicht der Auslöser — die
trifft die `if rendered_text`-Bedingung gar nicht; es muss eine
Whitespace-Part sein.)

**Fix (zwei Stellen):** (a) der Merge setzt keinen Absatzumbruch vor eine
Part ohne Inhalt; (b) reiner Whitespace wandert in denselben geordneten
Puffer (S-05) und wird erst mit echtem Text ausgegeben — steht bis zum
Ende nur Whitespace im Puffer, fällt er beim `finalize` weg. D-06 bleibt
unverändert: nach dem ersten sichtbaren Text ist ein Whitespace-Delta ein
Trennzeichen zwischen zwei Wörtern und geht sofort raus.

### S-07 — Protokoll-Narration statt Protokoll-Nutzung (das `open`-Problem)

**Symptom (live, 8 parallele `read`s):** die Schlussantwort begann mit dem
Monolog des Modells:

```
Wrong tool calls above — correcting to the allowed tools:I must use
`read`/`webfetch`/`bash` instead of `open`. Correct JSON protocol:
```

Das ist die gesuchte Stelle: das Modell **erzählt** über `open` und das
JSON-Protokoll, statt es zu benutzen — der Aufrufer war nie ein
Tool-Call (`blocked=[]` im Proxy-Log), es ist reiner Text.

**Ursache:** die Muster der Meta-Chatter-Filter kannten nur
Selbstentschuldigung. Dazu kam eine **verschachtelte** Struktur, die der
T-07-Preamble-Pfad nicht abdeckt. Aus dem Debug-Log (Part-Folge desselben
Turns):

```
lid=21436e text='Wrong tool calls above — correcting to…'
lid=bd7fc0 ntc=1                       <- erster Aufruf
lid=dffe3c ntc=0
lid=be301b ntc=1                       <- zweiter Aufruf
lid=5c55d7 text='I must use `read`…instead of `open`. Correct JSON protocol:'
```

Die erste Passage wird von der T-07-Maschinerie verworfen (sie stand vor dem
ersten Aufruf an). Die **zweite** kam danach und lief ungefiltert raus.

**Fix (drei Einsatzstellen, weil die Pfade getrennt sind):**
1. **Frühwarnung vor dem Parser** (`_PROTOCOL_META_NARRATION_TAIL_RE`):
   Deltas, deren Ende noch ein *Präfix* einer Marke ist, werden
   zurückgehalten und erst freigegeben, wenn der Text entweder zur Marke
   geworden ist oder erkennbar etwas anderes. Ohne diesen Lookahead matcht
   die Marke nur, wenn sie zufällig in **einen** Delta passt — bei
   Chunk-Größe 1–13 streamte sie komplett durch.
2. **Nach den Aufrufen**: ist der Turn bereits im Aufruf-Modus, wird
   Protokoll-Narration still entfernt (`strip_protocol_meta_narration`).
3. **Finalize/Preamble-Discard**: der Preamble-Puffer wird auch dann
   verworfen, wenn die Aufrufe in einem *eigenen* Event kamen (der
   Discard lief nur, wenn im selben Event ein sichtbarer Delta ankam).

Die Phrasen sind WORTLISTEN; daraus werden Voll- und Präfix-Muster erzeugt,
Worttrenner sind `[-_\s]+` (live: „Tool-Calls", `open_url`) und jedes Wort
darf in Backticks stehen (live: „instead of \`open\`"). Das Tail-Muster ist
an einer **Wortgrenze** verankert — ohne den Anker matchte das einzelne `r`
aus „right…" mitten in jedem Text.

### Verifikation

- **675 Tests grün** (532 vor diesem Arbeitsgang + 143 neue).
- Jede neue Testklasse wurde gegen den **Vorher-Stand** laufen gelassen:
  34 (S-05) bzw. 17 (S-07) schlagen ohne den Fix fehl, mit dem Fix grün.
  Nichts davon war ein leerer Test.
- Live: `smoke-test.sh` 8/8. Vier opencode-Sessions gegen den echten Proxy
  (`glm2api verify 4/5/6/7`): eine finale Text-Part, **0** Whitespace-Parts,
  13 Tool-Calls, 0 Fehler. Regressionslauf mit dem 7-Schritt-Stresstest
  ebenfalls sauber.

### Merkposten für die nächste Session

Ein Test, der `build_response()["choices"][0]["message"]["content"]` prüft,
prüft den **gecachten** Text. Für Stream-Verhalten muss der Test die Chunks
aus `consume_event` **und** aus `finalize()` sammeln — `_stream_visible()`
in `test_translator.py` tat das nicht und hat genau diese drei Bugs
durchgelassen. Bei `allowed_tool_names` gesetzt ist `content` im
Non-Stream-Response per OpenAI-Vertrag `None`, sobald Tool-Calls da sind:
für reine Stream-Aussagen dort also nichts nachprüfbar.

---

## Erledigt-Historie (Kurzreferenz)

- Echo/Duplikat-Loops (native Parts, 36/Turn) — DONE 3cd794e
- Snipsel+Finish-Protokoll-Leak + `[]`-Whitespace-Leak — DONE c33da91
- Invalides JSON (unbalancierte Klammern, 6,6KB) — DONE fea9c22/79fca84
- Doppelausgabe Call+Text (Midstream) — DONE 7a2a2cd
- Nacktes JSON-Array als Protokoll (Leak-Variante D) — DONE efbc2e7
- Stream-Reihenfolge umgestellt (S-05) — DONE 2026-09-26
- Leerzeilen-Artefakt neben Tool-Calls (S-06) — DONE 2026-09-26
- Protokoll-Narration im Client-Text (S-07) — DONE 2026-09-26

Siehe auch: Git-Commit 1039311 (Härtetest-Kampagne komplett),
infrastructure.md Changelog (10)–(14).