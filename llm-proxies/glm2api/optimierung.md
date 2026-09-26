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

## THEMA 8 — Live-Session-Test 2026-09-26: fünf Fehlerbilder, ein Muster (DONE 2026-09-26)

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

### S-08 — `open` ist ein natives Modell-Werkzeug, kein Bug im Prompt

**Symptom (live, session `glm2api-Ordner-Analyse`):** der allererste Aufruf
war `open` mit `file:///workspaces/MAIN/glm2api`. Der Proxy konnte ihn nicht
abbilden, verwarf ihn, und **ohne jede Rückmeldung** wiederholte das Modell
den Aufruf ~30-mal. Danach zwei erfundene Aussagen:

- „In dieser Umgebung steht mir nur das `open`-Tool zur Verfügung"
- „**Analyse abgebrochen** — das Tool-Limit (8/8) ist erreicht; ich musste `open` stoppen"

Das war eine Fehlerklasse („open gibt es nicht") **und** das erfundene
Tool-Limit — dieselbe Ursache, nicht zwei.

**Ursache:** GLM-5.3 ist ein ChatGLM-**Web-Agent**-Modell und hat `open` als
natives Server-Werkzeug. In `map_native_open_tool_call` fiel der Pfad durch:
`file://` ist kein http(s), also keine URL — und `://` im Ziel schlug auf den
T-21-Pfad „das ist eine URL, kein Pfad" an, also `None`. Der verworfene Aufruf
ohne Rückmeldung ist die eigentliche Fehlerklasse; das Tool-Limit hat das
Modell erfunden, weil es nichts zurückbekam.

**Fix:** `file://` auf den Pfad zurückfalten (Prozent-Decoding,
`file://localhost`, fremder Host → `None`), plus drei Dinge, die den Fehler
überhaupt nicht wiederholen lassen: ein Hinweistext, der die nicht
auflösbaren ChatGLMs-eigenen Refs (`turn2search0`, `turn1fetch0`) erklärt und
`read`/`glob`/`bash`/`webfetch` anbietet, strukturelle Filter gegen
Selbst-Steuerung (`_SELF_STEERING_RE`) und gegen die erfundene Limit-Meldung
(`_LIMIT_CLAIM_RE`) statt einer Phrasenliste.

**Diagnose-Deadlock, der mit ausgebaut wurde:** die Logzeile „Dropped native
open call" nannte das Argument nicht — man konnte nicht sehen, *was* nicht
abbildbar war, und stand vor einem toten „nicht mappable". Erst als `args=`
mitkam, war der Fall in zwei Minuten erklärt.

### S-09 — Selbst-Narration über Delta-Grenzen

**Symptom (live, repro M, 19:29, 20 Tool-Calls im Turn):** ein Text-Part
mitten im Lauf enthielt drei Varianten desselben Selbstgesprächs,
aneinandergeklebt:

```
Der `open`-Tool-Aufruf funktioniert in dieser Umgebung nicht zuverlässig für
lokale Pfade – ich nutze stattdessen `read`/`bash`:The `open` tool only works
for web URLs — for local files I need to use `read`/`bash`:Der `o…
```

**Ursache:** `_SELF_STEERING_RE` und `_LIMIT_CLAIM_RE` brauchen **beide**
Hälften eines Satzes (Ich/Steuer-Verb **und** Werkzeugname) in *einem*
String. Die Sätze liefen über mehrere Stream-Deltas, also traf kein Filter —
und `finalize` kann nichts zurückholen, was schon beim Client steht. (Der
Alternative-Ansatz „Filter im `finalize` auf `_deferred_visible_text`" greift
für einen Turn mit Calls gar nicht: `finalize` gibt Content nur aus, wenn
**keine** Calls da sind — `if final_text and not all_tool_calls`.)

**Fix:** das S-07-Prinzip auf die Selbst-Narration übertragen —
`_narration_carry` hält den Text **vor** dem Parser zurück, solange sein
letzter Satz noch Narration werden *kann* (`_self_steering_holdback`). Der
Auslöser ist bewusst billig (ein Werkzeug-/Limit-/Ich-Token im unvollständigen
Satz): Was er zu viel zurückhält, kommt spätestens mit der nächsten
Satzgrenze ungekürzt wieder raus — das ist Verzögerung, kein Textverlust.
Entscheiden tun weiterhin ausschließlich die beiden Muster.

### S-09-Nachtrag — der Holdback fraß das Werkzeug-Protokoll (2 rote Tests)

**Symptom:** die Übergabe meldete „718 Tests grün", tatsächlich waren es
**716 + 2 rot**: `test_turn_with_only_unusable_calls_is_a_failure_not_an_empty_success`
und `test_blocked_only_turn_ends_cleanly_in_both_paths`. Der Commit, der sie
kaputt gemacht hatte, war der S-09-Commit selbst (`4af494e`); `git bisect`
über `c8135d9..HEAD` traf ihn als ersten schlechten Commit.

**Ursache:** `_NARRATION_TOKEN_RE` enthält `tool_calls` — im Prosa-Fall richtig
(das Modell *erzählt* über das Protokoll), im Markup-Fall ein Fehlalarm:
`{"tool_calls":[…]}` hat kein Satzende und wird deshalb zurückgehalten. Der
Parser sah den Aufruf erst im `finalize`, und die Einstufung „unbrauchbarer
Aufruf" (T-06, `dropped_call_count` → `truncated_turn` → `error`) war da
schon entschieden. Gemessen, gleicher Text, nur die Zerschnittenheit
anders:

```
HEAD          {"tool_calls":[{"name":"read","arguments":{}}]}  → stop    parser_calls=0 dropped=0
4af494e~1     dito                                              → error   parser_calls=0 dropped=1
```

Das ist genau der Fehler, den T-06 behoben hat („leerer ERFOLG": der Client
bekommt eine leere, erfolgreiche Antwort und bleibt stehen).

**Fix:** Markup wird vor dem Muster ausgeschlossen (`contains_tool_markup` in
`tool_protocol.py`) — der Holdback fasst danach nur noch Prosa an. Der
Parser hat mit D-01/D-03 ohnehin seinen eigenen Holdback für angebrochenes
Markup; ein zweiter davor macht nur den Aufruf unsichtbar.

### Gefunden beim selben Durchgang: die Abschluss-Einstufung hing an der Zerschnittenheit

**Symptom:** ein **gesperrter** Aufruf, der über mehrere Deltas kam, endete als
`finish_reason: error` — in **9 von 15** Chunk-Größen und in **beiden**
Abschluss-Pfaden. Das ist exakt der Fall, für den `c8135d9` den `stop`
eingeführt hatte; der echte Client wertete `error` als Stream-Fehler und
wiederholte den Turn mit 5-Minuten-Backoff endlos (Agentenlauf 2026-09-26).
Gleichzeitig blieb der umgekehrte Fall falsch: ein **erlaubter** Aufruf ohne
Pflichtargument endete bei Chunk-Größe 1/2 als `stop` statt `error`.

**Ursache:** die Einstufung stützte sich auf `dropped_call_count`. Der Zähler
zählt **Teil-Parse-Versuche**, nicht unbrauchbare Aufrufe, und hängt damit an
der Zerschnittenheit des Upstream-Texts (gemessen, derselbe gesperrte Aufruf:
Chunk 100 → 1, Chunk 3 → 4, Chunk 1 → 0). Die Rechnung
`dropped − policy_drops <= 0` kippte dadurch je nach Chunk-Größe. Und bei
Chunk 1/2 waren `collected` **und** `dropped` leer — die Frage wurde gar nicht
gestellt, weil der Vorlauf `collected or dropped_call_count` lautete.

**Fix:** entschieden wird am **Text** des Turns, der unabhängig von der
Zerschnittenheit ist (`_text_attempted_tools()`):

| Text des Turns | Ergebnis |
|---|---|
| Protokoll, nur **erlaubte** Namen | `error` — dem Client fehlt etwas |
| Protokoll, nur **gesperrte** Namen | `stop` — vollständige Antwort |
| Protokoll, kein Name lesbar (abgeschnitten) | `error` |
| kein Protokoll im Text (nur ein nativer Part ging verloren) | alte Rechnung über `_policy_dropped_call_count` |

Der Vorlauf wurde auf `_unresolved_tool_attempt()` umgestellt, damit die
Frage bei Chunk-Größe 1 überhaupt gestellt wird.

### Gefunden beim selben Durchgang II: DSML über Part-Grenzen (seit Repo-Anfang)

**Methode:** Differenzmessung statt Vermutung. Für jedes Szenario ist das
Ergebnis bei **einem** großen Delta die Referenz; jede andere Zerschnittenheit
muss dasselbe liefern. Zwei Achsen, weil der Upstream beide Formen liefert:
Zeichen innerhalb eines Parts (`chars`) und Part-Grenzen (`logic_id`-Schnitte,
gleichmäßig und ungleichmäßig). Geprüft wurde, was der **Client** bekommt:
`finish_reason`, `tool_calls` (Namen + Argumente) und der sichtbare Text.

Die Teile sind dabei **typisiert**, weil nicht alles zerlegbar ist:

| Teil | Form | zerlegbar? |
|---|---|---|
| Text-Part | `{"type": "text"}` | ja — beides |
| Denk-Part | `{"type": "think"}` | ja — beides |
| **native Part** | `{"type": "tool_calls", ...}` (Dict *und* Listenform) | **nein** — der Upstream zerlegt sie nicht |

Der native Pfad ist damit von der Messung ausdrücklich **nicht** abgedeckt:
`_scan_brackets`/`_scan_markup` sehen ihn gar nicht, er läuft an der
Text-Part-Verarbeitung vorbei. Das ist Absicht — ein Bug dort wäre kein
Zerschnittenheits-Bug, sondern ein Bug in der Part-Reihenfolge, und der hätte
die Messung nur verfälscht.

**Die Messung braucht eine Positivkontrolle**, sonst beweist „null
Abweichungen" nichts: drei Szenarien sind gegen ältere Stände nachweislich
fehlgeschlagen (`ctl-dsml` gegen `1ec7ff4`: 400 Abweichungen; `ctl-dsml` +
`ctl-blocked-text-protocol` gegen `4af494e~1`: 810). Ein Sweep, der auf
diesen Ständen sauber bliebe, würde nichts messen.

**Symptom:** ein DSML-Aufruf ging bei **34 von 147** Chunk-Größen verloren
(vor T-20, als der Merge noch nicht inkrementell war: 126 von 147), und das
zerschnittene Markup kam als Antworttext an. `finish_reason` kippte dabei
zusätzlich zwischen `stop` und `error`.

**Ursache:** der Part-Merge schützte nur JSON. `{"tool_calls":` ist eine
**offene Klammer**, und `_scan_brackets` verhindert dort jeden Eingriff.
DSML/XML hat keine Klammern, also fiel die Entscheidung an `_starts_new_block`:
`|` und `>` am Part-Anfang gelten als Markdown-Block (Tabelle, Zitat) — im
DSML sind es Protokollzeichen. Der Merge setzte mitten im Markup einen
Absatzumbruch:

```
1 part       <|DSML|tool_calls><|DSML|invoke name="read">…
1 char/part  <\n\n|DSML\n\n|tool_calls\n\n><\n\n|DSML\n\n|invoke name="read"…
```

**Fix:** `_scan_markup` zählt neben den Klammern mit, ob das Fragment mitten
in einem Tag endet (`open_tag`) und ob ein `…tool_calls…`-Block läuft
(`in_call_run`). Beides heißt: die nächste Part ist eine Fortsetzung.

**Zur Reichweite:** das war kein Rückschritt, sondern ein latenter Fehler seit
dem ersten Commit, in dem glm2api im Repo liegt (`19c2e1d`, dort 126/147).
Live nachgewiesen ist er nicht — der Prompt schreibt das JSON-Protokoll vor,
DSML ist Legacy. `test_leak_sweep.py` hat aber DSML-Fälle, weil die Form
durchaus vorkommt; wenn das Modell in sie zurückfällt, ging der Aufruf vorher
stillschweigend verloren.

**Merksatz für die nächste Session:** „chunk-stabil" ist keine Eigenschaft,
die man einmal prüft und dann abhakt — sie ist eine **Invariante**, und sie
gilt pro Achse (Zeichen, Parts) und pro Pfad. Die Messung kostet Sekunden
und hat einen Fehler gefunden, den kein bestehender Test abgedeckt hat.

### Verifikation

- **794 Tests grün** (718 vor dem Nachtrag + 76 neue; Basis der Übergabe
  wiederum 532 + 143 aus S-05/06/07).
- Jede neue Testklasse wurde gegen den **Vorher-Stand** laufen gelaufen, wie
  schon bei S-05/S-07: gegen `4af494e~1` (ohne S-09) schlagen **20** der
  neuen Tests fehl (6× Mid-Run-Narration, 14× gesperrter Aufruf über
  Delta-Grenzen), gegen `4af494e` (S-09 ohne Nachtrag) **12** (die beiden
  ursprünglich roten plus der Fall „unbrauchbarer Aufruf hinter Narration").
  Nichts davon war ein leerer Test.
- Live gegen den echten Proxy (Neustart mit dem neuen Code, `health` ok,
  Start ohne jede Warnung): Text-Antwort `stop`/„Ja"; Tool-Aufruf
  **non-stream** `finish_reason: tool_calls`, `read {"filePath":"/etc/hostname"}`;
  Tool-Aufruf **stream** `finish_reason: tool_calls`, gleicher Aufruf, kein
  geleakter Content. Der Upstream liefert dabei Text in 4–8-Zeichen-Teilen —
  genau die Zerschnittenheit, an der die beiden Fehler sichtbar wurden.
- Ein Live-Lauf endete mit `error`, weil das Modell sein eigenes Protokoll
  abgeschnitten hat (Roh-SSE: `{"tool_calls":[{"name":"read","arguments":{"filePath`).
  Das ist Modellverhalten und wird korrekt als unbrauchbarer Aufruf
  eingestuft — nicht Proxy-Seite.
- `.env`-Korrektur (THEMA 9) live bestätigt: der Dienst startet wieder mit
  `token_source=.env GLM_REFRESH_TOKEN` und ohne `IGNORED`-Warnung.
- **Differenzmessung** (31 Szenarien × 2 Pfade × 3 Zerschnittenheits-Achsen ×
  jede Chunk-Größe = 7818 Messungen, inklusive **nativer** `tool_calls`-Parts
  in Dict- und Listenform sowie **Denk-Parts** als eigene Teile): vor dem
  Markup-Fix 210 Abweichungen, alle DSML; nach dem Fix **null**. Erweitert um
  native Parts und Reasoning-Kanal: ebenfalls **null** — die native und die
  Denk-Form haben keine weitere Zerschnittenheitsabhängigkeit.
- DSML-Gegenprobe: die 4 neuen DSML-Tests schlagen gegen `1ec7ff4` fehl, die
  beiden Gegenproben (Markdown-Block bekommt weiter seinen Absatzumbruch,
  Markup-Zustand leakt nicht in Prosa) sind gegen **beide** Stände grün.
- Live nach dem Markup-Fix: Neustart ok, Textantwort `stop`/„Ja",
  Tool-Aufruf `tool_calls` — unverändert zum Stand davor.
- Historie (S-05/06/07): `smoke-test.sh` 8/8; vier opencode-Sessions gegen den
  echten Proxy (`glm2api verify 4/5/6/7`): eine finale Text-Part, **0**
  Whitespace-Parts, 13 Tool-Calls, 0 Fehler; Regressionslauf mit dem
  7-Schritt-Stresstest ebenfalls sauber.

### Merkposten für die nächste Session

Ein Test, der `build_response()["choices"][0]["message"]["content"]` prüft,
prüft den **gecachten** Text. Für Stream-Verhalten muss der Test die Chunks
aus `consume_event` **und** aus `finalize()` sammeln — `_stream_visible()`
in `test_translator.py` tat das nicht und hat genau diese drei Bugs
durchgelassen. Bei `allowed_tool_names` gesetzt ist `content` im
Non-Stream-Response per OpenAI-Vertrag `None`, sobald Tool-Calls da sind:
für reine Stream-Aussagen dort also nichts nachprüfbar.

---

## THEMA 9 — Betriebs-Keys: vier wirkungslos, sechs doppelt (DONE 2026-09-26)

Aus dem Rest der Übergabe, beim Ausführen von THEMA 8 aufgefallen und
empirisch nachgewiesen (jeder Key einzeln gesetzt und die geladene Config
gemessen, nicht aus dem Code gelesen).

### Symptom

Vier Keys standen in **allen drei** ausgelieferten Dateien (`.env`,
`.env.example`, `llm-proxies/glm2api.env`) und wirkten nicht:

| tot | richtig | gemeldet? |
|---|---|---|
| `GLM_REFRESH_TOKENS` | `GLM_REFRESH_TOKEN` | ja (SECURITY) |
| `GLM_QUEUE_WAIT_TIMEOUT` | `GLM_QUEUE_WAIT_TIMEOUT_SECONDS` | ja |
| `REQUEST_TIMEOUT` | `REQUEST_TIMEOUT_SECONDS` | **nein** |
| `REQUEST_SOCKET_TIMEOUT` | `REQUEST_SOCKET_TIMEOUT_SECONDS` | **nein** |

Die beiden stillen hatten zudem exakt den Standardwert — deshalb fiel der
Unterschied nie auf. Bei `GLM_REFRESH_TOKENS=` wäre der Inline-Kommentar
sogar als *Wert* eingelesen worden (`parse_dotenv` strippt den Wert, nicht
den Kommentar).

### Ursache

Der „Betriebs-Keys"-Block (D-11) war als **Vollständigkeitsliste** gegen
`AppConfig` geschrieben worden, ohne die Datei auf bereits gesetzte Keys zu
prüfen. Ergebnis: alle vier Tot-Schreibweisen standen als Dublette neben dem
echten Key, und `parse_dotenv` ließ still den letzten gewinnen.

### Der teure Teil: derselbe Mechanismus hat den Dienst stillgelegt

Beim Korrigieren entstand in der echten `.env` eine zweite, leere
`GLM_REFRESH_TOKEN=` — der Token stand weiter oben in Zeile 63. Der Neustart
sagte:

```
glm2api: kein ChatGLM-Konto konfiguriert.
  Setze GLM_REFRESH_TOKEN in .env (oder hinterlege token.txt)
```

Die Datei sah korrekt aus, sie enthielt den Token, und trotzdem startete
nichts. Genau diese Fehlerklasse ist teuer: ein stilles Überschreiben, das
man erst bemerkt, wenn ein Dienst nicht mehr kommt.

### Fix

1. Die vier Tot-Schreibweisen aus allen drei Dateien entfernt bzw. auf den
   richtigen Namen umgestellt; die Dubletten (`GLM_REFRESH_TOKEN`,
   `GLM_TOKEN_FILE`, `GLM_BUSY_RETRY_INTERVAL_SECONDS`,
   `GLM_RATE_LIMIT_MAX_RETRIES`, `GLM_RATE_LIMIT_RETRY_INTERVAL_SECONDS`,
   `GLM_STREAM_ERROR_RETRY_INTERVAL_SECONDS`) raus — die Werte bleiben an
   ihrer Stelle weiter oben.
2. `_CONFIG_KEY_KNOWN_TYPOS`: die beiden stillen Fälle werden jetzt
   **gelistet** statt über die Unschärfe erkannt. `get_close_matches` mit
   `cutoff=0.82` liegt bei `REQUEST_TIMEOUT` gegen
   `REQUEST_TIMEOUT_SECONDS` nur bei 0.77 — ein echter Tippfehler, aber für
   die Heuristik zu weit weg. Ein Präfix-Key ist prinzipiell nie „nah" an
   seinem echten Namen, deshalb gibt es für diese Klasse eine Liste.
3. `parse_dotenv` meldet doppelte Keys mit **Zeilennummern** — und ohne den
   Wert zu nennen, das hätte hier den Refresh-Token ins Log geschrieben.
   Gleicher Wert zweimal bleibt still (harmlose Kopie am Dateiende).
4. Tests: die vier Tot-Keys dürfen in keiner ausgelieferten Datei stehen,
   die Dateien dürfen keine Dubletten haben, und die stillen Tippfehler
   müssen gemeldet werden.

### Verifikation

- 788 Tests grün (davon 11 neue in `test_config.py`).
- `GLM_REFRESH_TOKENS` / `REQUEST_TIMEOUT` / `REQUEST_SOCKET_TIMEOUT` einzeln
  gesetzt → kein Effekt auf die geladene Config; die korrekten Schreibweisen
  → `queue_wait=7`, `request_timeout=7` (vorher belegt).
- Live: Neustart mit `token_source=.env GLM_REFRESH_TOKEN`, **keine**
  `IGNORED`- und keine `Duplicate key`-Warnung mehr im Log.

### Merkposten

Ein `.env` ist eine Datei mit **Handpflege-Drift**, kein generiertes Artefakt.
Drei Kopien derselben Vorlage sind drei Chancen auf einen stillen Fehler —
deshalb prüft jetzt ein Test *alle* Kopien, nicht nur `.env.example`.

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
- `file://` als nativer `open`-Aufruf + Selbst-Narration (S-08) — DONE 2026-09-26
- Selbst-Narration über Delta-Grenzen (S-09) — DONE 2026-09-26
- Holdback fraß das Werkzeug-Protokoll → T-06 ging verloren (S-09-Nachtrag) — DONE 2026-09-26
- Abschluss-Einstufung hing an der Zerschnittenheit (`stop`/`error`) — DONE 2026-09-26
- DSML-Aufruf an Part-Grenzen zerschnitten (latent seit Repo-Anfang) — DONE 2026-09-26
- Vier wirkungslose + sechs doppelte Betriebs-Keys, `parse_dotenv` warnt jetzt — DONE 2026-09-26

Siehe auch: Git-Commit 1039311 (Härtetest-Kampagne komplett),
infrastructure.md Changelog (10)–(14).