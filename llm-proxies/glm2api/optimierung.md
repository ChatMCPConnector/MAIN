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

## Erledigt-Historie (Kurzreferenz)

- Echo/Duplikat-Loops (native Parts, 36/Turn) — DONE 3cd794e
- Snipsel+Finish-Protokoll-Leak + `[]`-Whitespace-Leak — DONE c33da91
- Invalides JSON (unbalancierte Klammern, 6,6KB) — DONE fea9c22/79fca84
- Doppelausgabe Call+Text (Midstream) — DONE 7a2a2cd
- Nacktes JSON-Array als Protokoll (Leak-Variante D) — DONE efbc2e7

Siehe auch: Git-Commit 1039311 (Härtetest-Kampagne komplett),
infrastructure.md Changelog (10)–(14).