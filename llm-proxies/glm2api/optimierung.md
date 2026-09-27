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

### S-10 — Reihenfolge-Invariante für native Parts (Text vor/nach/zwischen Calls)

Gefordert war die Invariante selbst: „Text vor, nach und zwischen nativen
Calls bleibt unabhängig von der Zerschnittenheit". Gemessen mit zwei neuen
Harnesses (`/tmp/glmtest/order_matrix.py`, `/tmp/glmtest/holdback_probe.py`):
11 Layouts × 10 Chunk-Größen, Referenz ist der sichtbare Stream inklusive
`finalize`. Vorher **23 Verstöße**, jetzt **0**. Fünf Fehlerklassen, alle
unabhängig voneinander gefunden:

**(1) `ich` traf mitten im Wort.** Das Präambel-Muster begann mit `\b(?:ich|…)`
— an einem Stream-Delta ist der Anfang aber *immer* eine Wortgrenze, das `\b`
war also bedeutungslos. Ein Delta, das mit `icht` begann (Rest von
`Ber|icht`), war damit eine deutsche Selbst-Narration; die T-07-Maschinerie
pufferte den Rest und verwarf ihn beim Aufruf. Gemessen bei Chunk 7: der
Client sah `Der Ber` und sonst nichts, **mitten im Wort**, bei allen anderen
Chunk-Größen den vollen Text.

**(2) Zwischenwort-Leerzeichen fielen nach einem Call.** `_strip_self_talk`
liefert für ein reines Whitespace-Delta `""` — im Aufruf-Turn fraß der Filter
so jedes Zwischenzeichen: `Zweiter Absatz mit` kam als `ZweiterAbsatzmit` an
(Chunk-Größen 1–5, vor dem Call war der Zwischenraum da). Dieselbe Folge hatte
D-06 einmal für die Zurückhaltung.

**(3) Präambel über der Chunk-Grenze.** Ein Delta allein kann eine Phrase nicht
sehen, die der Upstream zerschnitten hat: `Ic` + `h lese die Datei` lief als
**Antwort** durch. Mit Kontext erkannt (emittierter Schwanz + Delta) verschwindet
sie wieder — dafür blieb vor dem Fix ein Fragment des ersten Wortes stehen
(`I`, `Ic`, `Ich`, je nach Chunk-Größe), weil es schon raus war. Der Fix ist
derselbe Trick wie bei S-07: **Vorhalte-Lookahead**. `_preamble_narration_undecided`
gibt den Text zurück, solange er auf einem unvollständigen Präambel-Anfang endet
(`_PREAMBLE_STEM_PREFIX_RE`, aus allen Präfixen der Stämme gebaut, mit
Wortgrenze davor, damit `Datei` nicht am `i` hängen bleibt). Erst eine
vollständige Marke entscheidet.

**(4) Ein kompletter Text mit Code-Fence verschwand.** Der S-05-Puffer ist die
einzige geordnete Senke, und im Aufruf-Turn gab es danach keine mehr: was im
Abschluss noch zurücklag, verließ den Turn nicht (bei Calls gab `finalize`
Leftover-Text nicht heraus). Kam ein kompletter gefenceter Text in **einem**
Part — Chunk-Größe 1000 —, war er danach spurlos weg; bei 1–20 kam er
vollständig an. Der Text war nicht am falschen Platz, er fehlte. Jetzt wird der
Puffer veröffentlicht, sobald der Turn Aufrufe hat: in Reihenfolge, durch
dieselben Filter, und `[]`-Protokollrest wird nicht mitgeliefert (S-06).

**(5) `tool_parser.flush()` strippt seinen Anteil.** Der Rand links gehört zum
zuvor gesendeten Text: `Der Bericht` + ` ist fuer Sie.` kam als
`Der Berichtist fuer Sie.` an (Chunk 11 und 20, ganz ohne Calls). D-06 hatte
denselben Fehler für die Zurückhaltung behoben, für Carry und Puffer nicht.

**Gegenprobe zum Vorhalte:** Der Lookahead darf Text weder verschlucken noch
 verzögern. `holdback_probe.py` prüft 13 Texte (deutsch/englisch, mit/ohne
Call, Liste, Codeblock, Narration, Text auf `I`/`Ich`/`Jetzt`/`Datei`
endend) — alle 13 liefern whitespace-normalisiert **genau ein** Ergebnis über
alle Chunk-Größen. Übrig bleibt eine reine Whitespace-Klasse, die
**vorbestehend** und dokumentiert ist: der Part-Merge fügt um native Calls
Absatzabstände ein, deren Position bei künstlich zerschnittenen Parts
schwankt (S-06).

**Merksatz für die nächste Session:** Ein Wort-Muster, das auf einen
Stream-Delta geprüft wird, braucht beides: eine **abschließende** Wortgrenze
(sonst trifft es Wortanfänge) **und** den davorstehenden Text als Kontext
(sonst ist das führende `\b` wertlos). Und: wenn der sichtbare Text
zurückgehalten wird, braucht er *genau eine* Senke — ein Puffer, den der
Abschluss nicht mehr ausleert, ist kein Puffer, sondern ein Loch.

### S-11 — Absatzumbrüche des Part-Merges hingen an der Part-Aufteilung

Die Restklasse aus S-10 (der Part-Merge fügte um native Calls Absatzabstände
ein, deren Position schwankte) hat dieselbe Ursache wie Fehler 1: ein
**Transport-Artefakt wurde als Inhalt gedeutet**. Alle drei Fundstellen
(Stream-Deltas, Reasoning-Kanal, `_join_parts_incremental`) benutzten dieselbe
Regel

```
_ends_sentence(previous) or _starts_new_block(following)
```

und die erste Hälfte urteilt über eine Part-Grenze. Die ist aber keine
Aussage über Absätze: live liefert glm-5.3 den Text in 4–8-Zeichen-Teilen
(166 `logic_id`s in einem Turn). Fiel die Grenze genau auf ein Satzende,
klebte der Absatzumbruch mitten in einen fortlaufenden Satz. Gemessen mit
`/tmp/glmtest/paragraph_probe.py` (7 Texte × 8 Chunk-Größen, mit/ohne Call) —
**derselbe Text in drei Ausgaben**:

```
'…Punkte. Nichts weiter.'        (1 Part)
'…Punkte.\n\n Nichts weiter.'    (Schnitt vor dem Leerzeichen)
'…Punkte. \n\nNichts weiter.'    (Schnitt nach dem Leerzeichen)
```

und eine Markdown-Liste zerfiel in `1.\n\n Erster Punkt\n2.\n\n Zweiter Punkt`.
Der Cache-Pfad war in 6 von 7 Texten chunk-abhängig, der Stream in 4.

**Fix:** `_needs_paragraph_break(previous, following)` — eine gemeinsame
Regel für alle drei Stellen. Der maßgebliche Hinweis ist der **Leerraum am
Rand der Grenze**, denn der gehört zum Text des Modells und ist damit
unabhängig von der Aufteilung:

1. Die nächste Part beginnt mit Leerraum (auch ein Zeilenumbruch) → das
   Modell hat selbst getrennt: nur anhängen. **Das ist der Regelfall** —
   nach einem Satzende schreibt jedes Modell ein Trennzeichen, und genau
   dieses Zeichen entscheidet.
2. Die vorherige Part endet mit Leerraum → dasselbe. Ohne diese Regel stand
   der Umbruch *hinter* einem vorhandenen Leerzeichen (`'Punkte. \n\nNichts'`).
3. Die nächste Part eröffnet einen neuen Markdown-Block → Umbruch.
4. Sonst: Umbruch, wenn die vorherige Part mit einem Satzzeichen endet. Das
   ist die Anti-Kleb-Regel für wirklich getrennte Parts
   (`'Erster Absatz.' + 'Zweiter Absatz.'` bleiben zwei Absätze) — sie greift
   nur, wenn das Modell zwischen den Teilen nichts geschrieben hat.

Der erste Versuch, die Anti-Kleb-Regel ganz zu streichen, machte **vier
bestehende Tests rot**, darunter `test_prose_parts_are_still_separated_by_a_blank_line`
(„echte, getrennte Text-Parts dürfen NICHT zusammenschmelzen"). Die ist
Absicht und bleibt — deshalb regelt die Leerzeichen-Bedingung *vor* ihr,
statt sie zu ersetzen.

**Was inhaltlich nicht entscheidbar bleibt** (und so dokumentiert ist): ein
Text, in dem das Modell nach einem Satzende **gar kein** Trennzeichen
schreibt. `'Absatz. Absatz'` (zwei getrennte Parts) und `'Punkte.Nichts'`
(ein Text) sind an der Grenze nicht unterscheidbar; die Entscheidung hängt
dann an der Aufteilung des Upstreams. Der Regelfall — mit Trenner — ist
abgedeckt.

**Zweite Restklasse (dann S-12, siehe dort):** was der Stream beim Eintreffen
des Calls noch in der Hand hält, ging im Aufruf-Turn verloren — Narration-Carry
(S-07/S-09, 1–2 Zeichen), `pending_text` des Parsers (schließender ```` ``` ````)
und der S-05-Puffer bei unausgeglichenem Fence. S-10 hatte den
*veröffentlichbaren* Puffer geholt, S-12 die beiden anderen.

### S-12 — Der beim Call-Eintreffen zurückgehaltene Rest wird freigegeben

**Behälter:** `tool_parser.flush()` liefert im `finalize` genau den Anteil, den
der Stream beim Eintreffen des Calls noch in der Hand hatte — den
Narration-Carry (S-07/S-09) und den `pending_text` des Parsers
(Protokollverdacht). Der Abschluss gab ihn bei Calls nicht heraus, also ging
er verloren. Gemessen mit `leftover_probe.py` (3 Texte × 8 Chunk-Größen):
`… Dritter Punk` statt `… Dritter Punkt` (Carry, 1 Buchstabe),
`Vorher\n```\nalpha\n` ohne den schließenden Fence (Parser),
`'Nachher\n```\nalpha\n'`. **7 von 24 Messungen betroffen.**

**Fix:** der Rest wird im Aufruf-Turn freigegeben — nach denselben Filtern
wie ein Stream-Delta, mit zwei bewussten Unterschieden:

1. **`require_complete_sentence=False`.** Im Stream *muss* ein Delta auf
   einen fertigen Satz warten, sonst schneidet der Filter mitten hindurch
   (S-08: `'…nutze ich jetzt \`bash\`:'` → `'…\`isystem nutze ich jetzt…'`). Am
   Release-Punkt ist der Satz namenslich vollständig — der Aufruf ist da und
   der Text nicht. Mit `True` blieb genau die S-09-Narration stehen (sie endet
   auf `':'`, der Filter verweigert den Schnitt); mit `False` fällt sie ganz
   (`''`), während ein Antwortrest (`'t'`, `'er'`, `'Punkt'`, ```` ``` ````)
   unangetastet durchgeht.
2. **Nur was als Fortsetzung von bereits Gesendetem zurücklag.** Steht der
   Rest am *Anfang* eines Turns, ist er die Präambel — und die verwirft T-07
   grundsätzlich, in jeder Sprache, auch ohne dass ein Muster sie kennt.
   Das ist keine Feinheit: `test_accumulator_drops_tool_preamble_and_repairs_shell_command_array`
   pint `'我将创建文件。'` vor einem DSML-Aufruf, und die T-07-Muster kennen
   kein Chinesisch. Nur die Regel „Text vor dem ersten Aufruf ist Präambel"
   trägt dort. Diese Bedingung stand als erstes rot — sie ist die eigentliche
   Freigabeschranke, nicht der Filter.

Der S-05-Puffer ist **nicht** Teil der Freigabe: den veröffentlicht S-10
bereits am Call-Event, und der unausgeglichene Fence bleibt bewusst liegen
(die Fence-Unwrapping-Arbeit des Abschlusses braucht den Schluss, und der
Turn ist vorbei). Betroffen sind nur Zeichen am Textende, nie der Text; der
Cache-/Non-Stream-Pfad war nie betroffen.

**Ergebnis:** `leftover_probe` 24/24 exakt (vorher 17/24),
`paragraph_probe` 12/14 → 0 bis auf den nicht-entscheidbaren Fall, `order_matrix`,
`holdback_probe`, `sweep2`, `dsml_check` unverändert 0. **852 Tests grün** (4
neu), davon schlagen **3** gegen `b040b73` fehl; die Präambel-Gegenprobe ist
gegen beide Stände grün.

**Merksatz:** Wer einen Holdback einführt, muss die Frage beantworten, was
mit dem Zurückgehaltenen beim Turn-Ende passiert — und die Antwort darf nicht
„wird schon irgendwo verworfen" sein. Ein Container ohne Ausgang ist kein
Zwischenspeicher, sondern ein Loch; die Prüfung ist eine Zeile in der
Abschluss-Behandlung und drei Zeilen Test.



**Merksatz für die nächste Session:** Jede Formatierungsentscheidung an einer
Transportgrenze (Part-Grenze, Chunk-Grenze) ist verdächtig. Fragen, die die
Antwort liefern: (a) Ist der Wert, den ich prüfe, *Inhalt* des Modells oder
*Zustand* der Übertragung? (b) Liegt das entscheidende Signal im Text
selbst — dann ist es aufteilungsunabhängig; liegt es in der Grenze selbst,
dann hängt das Ergebnis an einem Schnitt, den niemand kontrolliert.

### S-13 — Stream/Non-Stream-Parität bei Text neben Tool-Calls: entschieden, nicht geändert

**Die Frage:** Der Stream liefert sichtbaren Text auch dann, wenn der Turn
Tool-Calls ausliefert (S-05/S-09/S-10/S-12 pinnen das). Der Non-Stream-Body
setzt `content` auf `None`, sobald Calls da sind — der Modelltext geht dort
verloren. Zwei Pfade, zwei Antworten auf dieselbe Frage.

**Messung, deterministisch** (`/tmp/glmtest/parity_probe.py`, ein Turn, beide
Pfade, Prosa in 5-Zeichen-Teilen):

| Turn | Stream | `message.content` | `tool_calls` |
|---|---|---|---|
| Prosa + Call | `'Die Datei enthaelt drei Zeilen.'` | **`None`** | `['read']` |
| Präambel + Call | `''` (T-07 verwirft) | `None` | `['read']` |
| nur Prosa (ohne Call) | `'Die Datei enthaelt drei Zeilen.'` | `'Die Datei enthaelt drei Zeilen.'` | `[]` |

**Messung, live** gegen den echten Proxy (Prompt: „Sag in einem kurzen Satz
welchen Pfad du liest, lies die Datei dann mit dem read-Tool …"; zwei Läufe —
das Modell ist nicht deterministisch, die Läufe sind also *nicht* derselbe
Turn):

- **Non-Stream:** `finish_reason=error`, `content='Ich lese den Pfad
  \`/workspaces/README.md\` mit dem read-Tool.'`, keine Calls — das Modell hat
  den Call *erzählt* statt gemacht, T-06 stuft das korrekt als Fehlschlag
  ein. Nebeneffekt: der Body zeigt den Präambel-Satz, den der Stream
  verworfen hätte.
- **Stream:** `finish_reason=tool_calls`, `content=''`, `read
  {"filePath":"/workspaces/hello.txt"}` — der Aufruf, ohne Narration.

**Entscheidung (Option B): die Asymmetrie bleibt und wird festgeschrieben.**

1. Der Proxy ist eine **Kompatibilitätsschicht**. Der OpenAI-Vertrag sagt bei
   `tool_calls`: `content` ist null. Ein Client, der darauf wartet, bekommt
   keinen unerwarteten Text und keine leere Assistant-Nachricht in der TUI —
   genau das war das S-06-Problem in seiner anderen Hälfte.
2. Der sichtbare Text geht **nicht** verloren, sondern über den Stream — dort
   ist er seit S-05/S-09/S-10/S-12 ordentlich geführt: in Reihenfolge, an
   Wortgrenzen geschnitten, Präambel verworfen, chunk-unabhängig. Der Stream
   ist damit der Textkanal, der Body der Aufrufkanal.
3. Wer es umdrehen will, hat genau **eine** Stelle: `build_response`,
   `"content": None if all_tool_calls or not final_content else final_content`.
   Die drei Tests, die `content is None` pinnen, haben alle *keinen* Text im
   Turn und bleiben dabei grün — die Umstellung wäre also kein Teststurm,
   sondern eine bewusste Zeile plus Client-Prüfung.

**Umsetzung:** zwei Tests, die den Vertrag in beide Richtungen festnageln
(`s13_body_carries_no_content_next_to_tool_calls_while_the_stream_does`,
`s13_body_still_carries_plain_text_for_text_only_turns`). Sie sind
**bewusst gegen beide Stände grün** — S-13 ändert kein Verhalten, es macht
die Asymmetrie explizit. Ein roter Test wäre hier ein Fehler: es gibt keinen
Zustand, in dem es diese Asymmetrie nicht gab.

**Nebenbefund, unabhängig davon** (an `02ceca2~1` gegengeprüft, also
vorbestehend): bei einer in Teile geschnittenen Narration entkommt das
**erste** Fragment, weil es noch keine Marke enthält — der S-09-Holdback
erkennt erst den Rest. Gemessen: `narration + call` liefert `'The \`'` im
Stream, vor wie nach S-12 identisch. Ein echter Leck, aber klein (ein
Fragment), und die Reparatur wäre ein Holdback für „Satz noch offen plus
Werkzeug-Token im Fragment" — das kostt Latenz auf *jedem* Satz mit
Backtick und ist eine eigene Entscheidung, keine Nebenbei. → **S-14 unten.**

### S-14 — das erste Fragment einer zerschnittenen Narration (Nebenbefund aus S-13)

**Symptom.** Der S-09-Holdback kennt das Werkzeug-Token nur in
*vollständiger* Form: `` `read` ``. Schneidet der Upstream früher — und das
tut er bei `'The \`open\` tool only works …'` —, trägt das erste Fragment noch
gar keinen Namen, der Auslöser greift nicht, und der Text ist unwiderruflich
beim Client. `finalize` kann nichts zurückholen, was schon draußen ist.

**Messung** (`harness/leak_probe.py`, **alle** 215 Chunk-Größen, nicht
Stichproben — genau die Fragmentgrenze löst den Fehler aus; Layout
`narration + nativer call`):

| Chunk | vorher | nachher |
|---|---|---|
| 1 | `'Der \`'` | `'D'` |
| 2 | `'De'` | `'De'` |
| 3 | `'Der'` | `'Der'` |
| 4 | `'Der'` | `'Der'` |
| 5 | `'Der \`'` | *(leer)* |
| 6…215 | *(leer)* | *(leer)* |

Vorher **5** von 215 Chunk-Größen mit sichtbarem Narration-Rest, nachher
**4** — und die vier sind ausschließlich der Wortrest **vor** der ersten
Werkzeug-Marke. Der Tool-Token-Rest ist vollständig weg, der Aufruf kam in
allen 215 Fällen an.

**Fix.** Zwei neue Bausteine, ein eigener Auslöser:

1. `_NARRATION_TOOL_NAMES` + `_build_begun_token_regex()` →
   `_NARRATION_BEGUN_TOKEN_RE`: **alle echten und abgeschnittenen** Anfänge
   der Werkzeug-Namen, hinter einem noch offenen Backtick, verankert am
   Satzende. Das blanke Backtick gehört dazu — das ist der Fall `'The \`'`
   (Chunk 5), in dem noch gar kein Namenteil angekommen ist. Zweifache
   Backticks reichen (Anfang eines `` ``read`` ``-Spans); ein drittes wäre
   der Anfang eines Code-Fences und gehört nicht hierher.
2. `_begun_tool_token_holdback()` als **eigener** Auslöser in
   `consume_event`, plus `_split_open_sentence()`: gehalten wird nur der
   **offene** Satz, der fertige davor geht sofort an den Parser.

**Warum Punkt 2 ein eigener Auslöser sein muss.** Der erste Versuch zog den
Schnitt auf die bestehende Holdback-Bedingung — das kostete **3 Alt-Tests**:

- `test_stream_preserves_order_across_code_fences[8]`: `'…alpha\nbeta…'` kam
  als `'…alphabeta…'` an. Der fertige Teil wanderte in den S-05-Puffer, und
  der Abschluss strippt ihn weg (`final_text = cleaned_text.strip()`).
- `test_s10_space_between_streamed_text_and_finalize_tail_survives[11,20]`:
  `'Der Bericht ist fuer Sie.Ich'` — der Rand-links des Carries geht über
  `_lead_source` in `finalize` ein und war leer.
- `test_accumulator_drops_tool_preamble_and_repairs_shell_command_array`:
  `'我将创建文件。\n\n'` streamte, statt gepuffert zu bleiben. Die
  T-07-Präambel muss den Text *sehen*, um ihn verwerfen zu können.

Diese drei Pfade sind gepinnt und behalten deshalb unverändert „ganzer Text
zurückhalten". `_begun_tool_token_holdback` greift nur, wenn
`_self_steering_holdback` **nicht** greift — steht ein vollständiges Token im
offenen Satz, entscheidet weiterhin S-09. Der Fence-Fall ist übrigens
genau der, an dem der Schnitt nötig *war*: `…alpha\nbeta\n\`\`` — ohne ihn
ging die Zeilenwende zwischen zwei Code-Zeilen verloren.

**Was bewusst bleibt.** Der Wortrest vor der ersten Marke (`'D'`, `'De'`,
`'Der'`) ist nicht reparierbar, ohne die erste Satzhälfte *jedes* Parts zu
puffern — Verzögerung auf jeder Antwort, auch ohne Calls. Entschieden wurde
Option (a) „nur der reparierbare Rest" gegen Option (b) „auch der Wortrest,
mit Latenzpreis". Der Rest ist als `_S14_RESIDUE = ("", "D", "De", "Der")` in
den Tests festgeschrieben, damit eine spätere Ausweitung eine bewusste
Entscheidung sein muss und keine stille Verbesserung.

**Preis.** Jeder Satz, der mit einem Backtick endet, wartet jetzt bis zur
Satzgrenze. Das ist Verzögerung, kein Textverlust — dieselbe Zusicherung,
die schon S-09 gibt. Gemessen an echtem Antworttext mit `` `read` ``/`` `bash` ``
und Fence: **0 von 104** Chunk-Größen verändert.

**Positivkontrolle** (gegen `02ceca2`, S-12 ohne S-14): **4** der neuen
Tests schlagen fehl — `s14_narration_fragment_never_reaches_the_client[1]`
und `[5]` mit echten Assertion-Fehlern (das ist der Leck selbst), die beiden
Regel-Tests mit `ImportError` (die Helfer existieren dort nicht). 568 der
572 neuen Tests sind gegen beide Stände grün: die Gegenproben (Aufruf kommt
an, Antworttext unverändert, Fence-Neubruch bleibt) beweisen Unverändertheit.

**Harnesses liegen jetzt im Repo** (`harness/`, mit README). Sie lagen nur
unter `/tmp/glmtest/` und waren nach dem Codespace-Neustart weg — die
Messbasis der S-10…S-13-Arbeit war damit nicht reproduzierbar. Das
`GLM_SRC=`-Schema für die Positivkontrolle steht dort dokumentiert.

**Merksatz:** Ein Auslöser, der ein *vollständiges* Merkmal sucht, ist an
jeder Schnittstelle unvollständig — das Fragment, in dem das Merkmal noch
unvollständig ist, ist genau das Fragment, das durchrutscht. Und: wer einen
Holdback einführt, muss *jede* Stelle entscheiden, die er in den Schnitt
einbezieht; „verzögert statt gelöscht" gilt für den neuen Pfad, nicht für
die drei gepinnten daneben.

### S-15 bis S-18 — vier Funde aus dem Harness-Neuaufbau (**behoben 2026-09-27**)

Am 2026-09-27 wurden `order_matrix` und `sweep2` neu gebaut (die alten Fassungen
lagen nur unter `/tmp` und waren weg). Beide melden **0 unbekannte Verstöße** —
und haben dabei vier Befunde zutage gefördert, die kein Test sah. Alle vier
waren an `02ceca2` und `9054325` gegengeprüft: **vorbestehend**, nicht von
S-10…S-14 verursacht. In `harness/` waren sie als `KNOWN` hinterlegt, damit sie
auffallen, ohne den Exit-Code zu fälschen; seit dem 2026-09-27 ist die
`KNOWN`-Tabelle bis auf eine bewusst akzeptierte S-14-Grenze leer.

**S-15 — die S-12-Freigabeschranke frisst legitimen Text am Turn-Anfang.**
S-12 gibt beim Aufruf-Eintreffen nur heraus, was „als Fortsetzung von bereits
Gesendetem" zurücklag (`self._emitted_visible_text`). Gemessen:

| Eingabe (Text-Part, dann nativer `read`) | Chunk 1 | Chunk 7 | Chunk 1000 |
|---|---|---|---|
| `'Der Bericht ist fuer Sie. Ich'` | `'Der Bericht ist fuer Sie. Ich'` | — | **`''`** |
| `'Der Bericht ist da. Ich nutze jetzt \`read\` fuer den Rest.'` | `'Der Bericht ist da'` (ohne Punkt) | `'Der Ber'` (mitten im Wort) | **`''`** |

Ein **fertiger, unauffälliger Satz** verschwindet in einem Turn mit Tool-Call —
komplett, wenn er in einem Delta kommt, und abhängig davon, wo der Upstream
schneidet. Dieselbe Schranke frisst auch die Prosa, die einem DSML-Aufruf
folgt (`dsml-aufruf+prosa`): Stream `''`, Body `None` — der Client bekommt
einen Aufruf und sonst nichts, obwohl das Modell einen Satz geschrieben hat.
Die Schranke war zu grob: „steht am Turn-Anfang" heißt „Präambel" ist nur für
Text *vor* einem Call richtig, nicht für Text, der erst durch ein
Protokoll-Fragment in den Puffer kam.

**S-15, zweite Hälfte — der linke Rand des zurückgehaltenen Textes.** Nach dem
ersten Fix war der ganze Satz gerettet, aber der **Satzendpunkt fehlte**.
Layout `rand-links-im-carry`, Soll `'Der Bericht ist fuer Sie.'`:

| | Chunk 3 / 8 | Chunk 11 / 20 |
|---|---|---|
| IST | `'Der Bericht ist fuer Sie'` (Punkt fehlt) | `'Der Berichtist fuer Sie.'` / `'Der Bericht ist fuerSie.'` (Leerraum fehlt) |
| Carry | `'. Ich'` | `' ist fuer Sie. Ich'` bzw. `' Sie. Ich'` |

Der Punkt und der Leerraum, die den **schon gesendeten** Satz abschließen,
wandern als „Trenner" in den Carry — dieselbe Konvention wie in
`_split_open_sentence` (S-14), nur an der *falschen Stelle* angewandt. Sie
sterben dort mit der Narration, denn `_SENTENCE_END_RE` liest den Punkt als
*Anfang* des Narration-Satzes. `finalize()` hängte nur `lead_whitespace` wieder
an, nie den Satzendpunkt.

**Fix zu S-15.** Zwei Teile, beide nötig:

1. *Die Schranke.* Die Frage „kam vorher schon etwas raus" wird durch „ist der
   Rest eine **Präambel**" ersetzt, entschieden **satzweise**. Neue
   Modul-Funktion `strip_turn_start_narration()`, neue Methode
   `_strip_release_narration()` — die Filterkette `strip_turn_start_narration` →
   `strip_self_steering(rcs=False)` → `strip_invented_limit_claim(rcs=False)` →
   `strip_protocol_meta_narration` an **einer** Stelle, mit drei Aufrufern
   (Verwurf am Aufruf-Event, S-09-Zweig in `finalize`,
   `tool_parser.flush()`-Signal `flushed_markup_prefix_is_preamble`). Vorher
   entschieden drei Pfade unabhängig, was „Präambel" heißt.
2. *Der Rand.* Neue Methode `_owed_lead_edge(text) -> (eigener Anteil,
   geschuldeter Rand)`, angewandt an zwei Stellen in `consume_event` (S-14-Zweig
   nach `_split_open_sentence`, S-09-Ganztext-Zweig). Drei Schranken, jede hat
   einen gepinnten Alt-Test gerettet:
   - `self._emitted_visible_text` muss wahr sein — sonst gibt es keinen Satz,
     den der Rand abschließen könnte, und ein führender Punkt/Leerraum wäre
     ein Artefakt am Turn-Anfang (`leerraum-artefakt`);
   - `self._deferred_visible_text` muss leer sein — der S-05-Puffer geht zuerst
     raus, ein jetzt veröffentlichter Rand käme ihm in die Quere;
   - `self.tool_parser.pending_text` muss leer sein — steht der Parser mitten
     in einer Struktur, ist der Rand **Inhalt der Struktur**. Ohne diese dritte
     Schranke riss der Rand einen Code-Fence auseinander:
     `test_s10_fenced_text_in_one_part_is_not_lost_before_a_native_call[3]`
     lieferte `ls-la` statt `ls -la` und einen Fence mit führendem Leerraum
     (der Rand `' '` vor `-la` war abgetrennt, während der Parser
     `` ```bash\nls `` hielt).

   Der Rand enthält **keinen Zeilenumbruch** (sonst gehört er zum folgenden
   Block) und nur echte Satzenden, nicht `"`, `)`, `»` — die schließen, sie
   stehen nie am Anfang; dafür die neue Konstante
   `_SENTENCE_TERMINATORS`. Er geht **direkt an `chunks`** und nicht durch die
   restliche Kette: der Auftrag `_preamble_narration_probe` prüft gegen den
   **Upstream**-Text (`_emitted_text_tail`), nicht gegen den veröffentlichten —
   der gerade zurückgehaltene Carry ist darin enthalten, der Rand `'. '` nach
   dem Carry `'Ich'` las sich dadurch als Präambel und fiel im Aufruf-Turn mit.
   Der Rand ist per Definition kein Text: er enthält weder Narration noch
   Protokoll-Fragment, er schließt nur ab.

**S-16 — der Non-Stream-Pfad filtert den Antworttext überhaupt nicht.**
`chat_completion` (der Non-Stream-Einstieg, `glm_client.py` Z. 491–795) ruft
`accumulator.finalize()` **nie**; er gibt `build_response()` zurück, und das
rendert den Text neu aus den Parts (`_render_full_output()`). Die gesamte
Filterkette des Abschlusses — `strip_meta_chatter`,
`strip_invented_limit_claim`, `strip_protocol_meta_narration`,
Halluzinations-Echo, Fence-Unwrap, S-06-Leerzeilen, die S-12-Freigabe — hängt
an `finalize()` und gilt damit **nur für den Stream**. Gemessen, rein
Text-Turn, Text `'Tool-Limit erreicht — hier die Analyse.'`:

| | Ergebnis |
|---|---|
| `strip_invented_limit_claim(...)` direkt | `''` (der Filter kann sie) |
| `strip_meta_chatter(...)` direkt | `''` |
| Stream | `'Tool-Limit erreicht — hier die Analyse.'` |
| Body (`build_response()` **und** `build_response('finish')`) | `'Tool-Limit erreicht — hier die Analyse.'` |

Das ist genau die Form, vor der S-08 gebaut wurde („die schädlichste Form: das
Modell hört auf zu arbeiten und legt dem Client eine fertige Antwort samt
Grund für den Abbruch hin"). Die Doku behauptete seit S-08, der finale Bericht
gehe durch `finalize`/`strip_meta_chatter` — für den Body stimmt das nicht.
**Wichtig:** die Test-Hilfen rufen `finalize()` *vor* `build_response()` auf.
Diese Reihenfolge gibt es in Produktion nicht, deshalb blieb die ganze
Body-Pfad-Klasse ungetestet.

**Fix zu S-16, bewusst eng.** Die Behauptung „der Non-Stream-Pfad filtert
nichts" ist **halb** wahr und wurde nicht so übernommen: `build_response()`
enthält selbst Filter (Fence-Unwrap, Echo-`strip`, Self-Steering über den
gerenderten Text) — sie greifen nur nicht für die *Abschluss*-Kette, und der
S-13-Fall `content is None` bei Calls darf nicht angetastet werden. Behoben
wurde die schädliche Klasse, an zwei Stellen:

- *Stream:* neue Methode `_strip_invented_limit_claim()`, die auch **ohne**
  Calls greift. Die Beschränkung „nur wenn der Turn Aufrufe hat" stammt aus
  S-08 und gilt für die **Selbst-Steuerung** (dort ist eine Aussage über
  `open` echter Inhalt), nicht für die Limit-Meldung — die ist so gebaut, dass
  sie nur greift, wenn sie am Anfang steht (200 Zeichen) oder ein
  Abbruch-Wort enthält. Die gemeinsame Hülle ist die Modul-Funktion
  `_apply_text_filters(text, steps, require_complete_sentence)`.
- *Body:* die Kette in `build_response()` **direkt vor**
  `stripped_echo = strip_transcript_echo(...)`: mit Calls nur Meta-Chatter, ohne
  Calls auch dann, wenn der Filter alles entfernt.

**S-17 — ein Apostroph gilt als Satzende.** `_SENTENCE_END_CHARS` enthielt `'`
(neben `"`, `)`, `»`). Eine Part, die an einem Kontraktions-Apostroph endet, gilt
`_ends_sentence()` als Satzende, und `_needs_paragraph_break()` setzt daraufhin
einen **Absatzumbruch mitten im Wort**:
`"I'll now read the file."` bei Chunk 1 → `"I'\n\nll now read the file."`.
Vorhanden seit S-11 (dort wurde die Regel nur umsortiert, das Zeichen war
schon vorher ein Satzende) und an `9054325` identisch. Die Gegenprobe ohne
Apostroph ist unauffällig.

**Fix zu S-17.** `'` aus `_SENTENCE_END_CHARS` streichen — es ist
Vokabelöffner oder Possessiv, kein Satzende. `)"»` **bleiben**: sie schließen
ein Zitat oder eine Klammer, dort ist ein Satzende plausibel. Gepinnt in
`test_s17_real_sentence_enders_still_end_a_sentence`.

**S-18 — DSML über viele Parts leckt als Markup.** Bei Chunk-Größen 1–3 leckt
das DSML als sichtbarer Text in den Stream, obwohl der Aufruf korrekt geborgen
wird. Vorhanden an allen geprüften Ständen.

**Fix zu S-18 — zwei Ursachen, nicht eine.** Genau wie bei S-14: ein Auslöser,
der ein *vollständiges* Merkmal sucht, ist an jeder Schnittstelle unvollständig.
1. `_needs_paragraph_break()` brach an **jeder** `|`-Grenze um, weil `|` am
   Zeilenanfang wie eine Markdown-Tabelle aussieht: aus einem Part wurde `<` +
   `|DSML` + `|tool_calls>` und damit drei Parts mit zwei Umbrüchen. Neue
   **Regel 0**: liegt die Grenze **innerhalb** von Markup (nach dem letzten `>`
   folgt ein `<`), bricht kein Absatz um — das ist ein Transportschaden, keine
   Formatierung.
2. `TAG_NAME_HINTS` erkennt einen Opener erst, wenn er **vollständig** im Puffer
   liegt; bis dahin wurde jedes Zeichen einzeln als sichtbarer Text ausgegeben.
   Neu: `BEGUN_MARKUP_RE = _build_begun_markup_regex([*TAG_NAME_HINTS, '{"tool_calls"'])`
   — endet der Text an einem **angefangenen** Opener, gibt `consume()` `""`
   zurück. *Fallstrick, im Code dokumentiert:* die Fragmente müssen
   `re.escape()`t werden. Sonst wird das `|` in `<|` zur Alternative, leere
   Alternativen matchen überall, und der Mustertest auf `'Pa'` schlägt an —
   genau das war der erste Fehlversuch.

Dazu kam `tool_protocol.py`: `contains_tool_markup` kannte DSML nicht, wodurch
der Carry Markup festhalten konnte, während der Parser die folgende Prosa
verschluckte. `_TOOL_MARKUP_RE` bekam die DSML-Alternative
(`r"<\|?\s*dsml\|"`).

**Ergebnis nach den Fixes (alle drei Harnesses, 2026-09-27)**

| Harness / Szenario | vorher | nachher |
|---|---|---|
| `order_matrix` | 4 Verstöße (alle `rand-links-im-carry`) | **0 / 120** |
| `sweep2` | 0 unbekannte, aber 6 Szenarien nur per `KNOWN` auf 0 | **0 unbekannte / 132**, 1 bekannter Befund |
| `sweep2` `selbst-steuerung-mittelteil` | 5 von 6 Chunkgrößen falsch | **0 / 6** |
| `sweep2` `dsml-aufruf+prosa` | 4 von 6 (Prosa fehlt im Stream) | **0 / 6** |
| `sweep2` `dsml-ueber-viele-parts` | 2 von 6 (Markup im Stream) | **0 / 6** |
| `sweep2` `praeambel-en+call` | 1 von 6 (Umbruch mitten im Wort) | **0 / 6** |
| `sweep2` `limit-erfunden+nur-text` | 6 von 6 (Stream **und** Body) | **0 / 6** |
| `sweep2` `praeambel-cn-eigener-part` | 2 von 6 (Wortrest vor der Marke) | **0 / 6** (Mitreise des S-15-Filters) |
| `leak_probe` | 4/215 + 0/104 | 4/215 + 0/104 (unverändert, der S-14-Rest) |

**Positivkontrolle (Pflicht, sonst beweisen die Tests nichts).** Die 13 neuen
Tests (173 Fälle) gegen `02ceca2` gefahren: **127 rot, 46 grün**. Rot sind
genau die Klassen, die die Fixes behaupten:

| Test | rot am alten Stand |
|---|---|
| `s15_finished_sentence_before_narration_survives_every_chunk_size` | 50 von 57 |
| `s16_invented_limit_claim_is_dropped_without_tool_calls` | 39 von 39 |
| `s15_lead_edge_of_the_held_text_reaches_the_client` | 29 von 29 |
| `s18_dsml_split_over_many_parts_never_leaks_as_markup` | 3 von 7 (genau Chunk 1–3) |
| `s17_contraction_does_not_end_a_sentence` | 2 von 23 |
| `s15_owed_lead_edge_needs_published_text_and_an_empty_buffer` | 1 von 1 |
| `s15_prose_after_a_protocol_fragment_is_not_lost` | 1 von 1 |
| `s17_real_sentence_enders_still_end_a_sentence` | 1 von 1 |
| `s18_begun_markup_opener_is_held_by_the_parser` | 1 von 1 |

Grün bleiben die Gegenproben — genau so soll es sein: der Turn-Anfang bleibt
Präambel (`s15_turn_start_preamble_is_still_dropped`, 6/6), der Fence bleibt
ganz (`s15_owed_lead_edge_is_never_taken_out_of_a_parser_structure`, 6/6),
ein `open`-Hinweis ohne Calls bleibt Inhalt
(`s16_legitimate_open_mention_without_calls_survives`, 1/1), die Absatzregel
außerhalb von Markup bleibt
(`s18_paragraph_break_is_never_inserted_inside_markup`, 1/1).

**Nicht behoben, bewusst.** `sweep2`, Szenario `selbst-steuerung+call`: bei 2
von 6 Chunkgrößen entkommt der Wortrest vor der ersten Werkzeug-Marke. Das ist
die **akzeptierte S-14-Grenze**, nicht S-15 — die Selbst-Steuerung steht dort
am *Anfang* des Turns, es gibt also keinen fertigen Satz davor, den S-15
retten könnte; der Rest ist der erste Teil des ersten Narration-Satzes.

**Reihenfolge, in der repariert wurde (die Vorschlagsreihenfolge war falsch).**
S-18 zuerst, weil die Ursache eindeutig war und die beiden Hälften unabhängig
blieben; dann S-17 (Einzeiler, mit Gegenprobe), dann S-16, dann S-15 als
letztes, weil es die beiden anderen in sich aufnahm. Die ursprüngliche
Überlegung „S-16 zuerst, es ist die Ursache hinter einer ganzen Filterklasse"
hätte den halben Teil des Problems vergrößert: `build_response()` filtert
durchaus, nur die *Abschluss*-Kette fehlt — und die S-13-Regel
(`content is None` bei Calls) hätte dabei verteidigt werden müssen.

### Verifikation

- **1599 Tests grün** (1426 + 173 neue aus S-15…S-18; Suite 11,8 s → 12,5 s).
  Historie: 839 (794 + 45 aus S-10), mit S-11 **848** (+ 9), mit S-12
  **852** (+ 4), mit S-13 **854** (+ 2, Verhaltens-neutral), mit S-14
  **1426** (+ 572).
- **S-15…S-18 gegen den Vorher-Stand `02ceca2` (Positivkontrolle): 127 der 173
  neuen Fälle schlagen fehl**, die 46 Gegenproben sind gegen beide Stände grün.
  Aufschlüsselung im Abschnitt oben. Zwei Klassen, die man beim Lesen der Zahl
  nicht erwartet: `s17_contraction` ist nur 2 von 23 rot (der Wortumbruch ist im
  Stream erst bei ganz kleinen Chunkgrößen sichtbar), und
  `s18_dsml_split_over_many_parts` 3 von 7 (genau die Chunkgrößen 1–3 — der
  Rest war schon vorher in Ordnung). Beides ist gemessen, nicht geschätzt.
- Harnesses (nach den Fixes): `order_matrix` 120 Messungen / **0** unbekannte
  Verstöße (vorher 4), `sweep2` 132 / **0** (vorher 0, aber 6 Szenarien nur per
  `KNOWN` auf 0). `leak_probe` unverändert 4/215 + 0/104. Eigenprüfung: an
  `9054325` melden die Sweeps 14 bzw. 7 unbekannte Verstöße — sie sehen also
  echte Fehler und verschlucken keine.
- S-11 gegen den Vorher-Stand (Positivkontrolle): **8** der 9 neuen Tests
  schlagen fehl — alle sechs Chunk-Unabhängigkeits-Fälle, der
  Doppelumbruch und der Regel-Test. Die Anti-Kleb-Gegenprobe
  (`…_still_separated_by_a_blank_line`) ist gegen **beide** Stände grün.
- S-14 gegen den Vorher-Stand `02ceca2` (**Positivkontrolle**): **4** der 572
  neuen Tests schlagen fehl — der Leck selbst bei Chunk 1 und 5 (echte
  Assertion-Fehler) und die zwei Regel-Tests (`ImportError`). Die 568
  Gegenproben sind gegen beide Stände grün.
- S-10 gegen den Vorher-Stand `9054325` (**Positivkontrolle**): **13** der 45
  neuen Tests schlagen fehl, und zwar je Fehlerklasse mindestens einer —
  `prose … cut mid word[7]`, `preamble pattern … word prefix`,
  `undecided preamble prefix`, `preamble … remnant[1,2]`,
  `interword spaces[1]`, `fenced text …[1000]`,
  `space … finalize tail[5,11,20]` und die drei Layouts mit Calls. Die
  übrigen 32 sind gegen beide Stände grün (Gegenproben).
- `order_matrix.py`: 11 Layouts × 10 Chunk-Größen → 0 Verstöße
  (vorher 23). `holdback_probe.py` whitespace-normalisiert: 0 (vorher 10).
- `sweep2.py` (31 Szenarien × 2 Pfade × 3 Achsen, 7818 Messungen) und die
  794 Alt-Tests unverändert grün.
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
für reine Stream-Aussagen dort also nichts nachprüfbar. Das ist eine
**bewusste Entscheidung** (S-13), mit zwei Tests festgenagelt — sie steht
nicht zufällig da und soll auch nicht beim Aufräumen verschwinden.

Und der Nachsatz aus S-15, der beim Bauen des Fixes drei Stunden gekostet hat:
`_preamble_narration_probe` prüft gegen den **Upstream**-Text
(`_emitted_text_tail`), nicht gegen den, den der Client schon sieht. Der
gerade zurückgehaltene Carry ist darin enthalten. Wer eine „der Rand gehört
nach vorn"-Korrektur baut, muss also damit rechnen, dass ein rand, der über
`text_delta` in die Kette geht, sofort als Präambel wiedererkannt und in den
S-05-Puffer geschrieben wird — er landet dann im Aufruf-Turn im selben
Verwurf, den man eigentlich beheben wollte. Der Rand ging deshalb direkt an
`chunks`.

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
- Reihenfolge-Invariante native Parts: Wortpräfix-Fehlmatch, verlorene Zwischenräume, Präambel über der Chunk-Grenze, gefenceter Text im Aufruf-Turn, `flush()`-Strip (S-10) — DONE 2026-09-27
- Absatzumbrüche des Part-Merges hingen an der Part-Aufteilung (S-11) — DONE 2026-09-27
- Stream/Non-Stream-Parität bei Text neben Calls: Asymmetrie entschieden und gepinnt (S-13) — DONE 2026-09-27
- Beim Call-Eintreffen zurückgehaltener Rest (Carry/Parser) ging im Aufruf-Turn verloren (S-12) — DONE 2026-09-27
- Erstes Fragment einer zerschnittenen Narration entkam (Nebenbefund aus S-13): angefangener Werkzeug-Token als Holdback-Auslöser (S-14) — DONE 2026-09-27
- Mess-Harnesses lagen nur in `/tmp` und waren nach Neustart weg — jetzt in `llm-proxies/glm2api/harness/` — DONE 2026-09-27- Vier Funde aus dem Harness-Neuaufbau (alle vorbestehend, gegengeprüft an `02ceca2`/`9054325`) — **DONE 2026-09-27**: S-15 Präambel wird satzweise statt pauschal erkannt (der linke Rand des zurückgehaltenen Textes kam als S-15-Rest noch dazu, `_owed_lead_edge`), S-16 erfundene Limit-Behauptung greift auch ohne Calls (Stream **und** Body), S-17 Apostroph ist kein Satzende, S-18 DSML über viele Parts leckt nicht mehr (Absatzregel **und** angefangener Opener)
- Harnesses lagen nur in `/tmp` und waren nach Neustart weg — jetzt in `llm-proxies/glm2api/harness/`, mit `trace_stream.py` und `common.py` — DONE 2026-09-27

Siehe auch: Git-Commit 1039311 (Härtetest-Kampagne komplett),
infrastructure.md Changelog (10)–(14).