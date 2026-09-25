# glm2api-revision.md — vollständiges Linien-für-Linien-Audit

**Stand:** 2026-09-24 (Audit), **2026-09-24 (P0-Fixes umgesetzt, s. Teil F)**
**Scope:** `llm-proxies/glm2api/` — 17 Produktionsdateien (7.742 Zeilen), 6 Testdateien (3.226 Zeilen), Benchmarks, Build- und Konfigurationsdateien
**Methode:** 7 parallele Subagenten (eine Datei bzw. ein Bereich pro Agent), danach unabhängige Nachverifikation jedes Kernbefunds durch den Hauptagenten, ergänzt um Analyse echter Runtime-Daten (opencode-DB, glm2api-Debug-Logs)
**Anlass:** Nutzerbefund — „glm2api funktioniert noch nicht gut: es schafft Aufgaben, aber sehr häufig wird in der Ausgabe ein Toolcall fälschlicherweise als Antwort gegeben"
**Verhältnis zu `Revision.md`:** Dieses Dokument ist die **fachliche Fortschreibung für glm2api** und ersetzt für diesen Bereich die historischen Parts I/U der Revision. Befunde mit Vorzeichen `I-xxx`/`U-xxx` verweisen auf die dortige Erstbefundung; alle wurden am aktuellen Source erneut geprüft.

---

## Executive Summary

Die Kernhypothese des Nutzers ist **bestätigt und quantifiziert**. In 4 von 9 glm2api-Sessions finden sich 8 Antwort-Parts mit zusammen **35.643 Zeichen** Roh-Protokoll im sichtbaren Text. Die Ursachen sind **nicht** ein einzelner Bug, sondern eine Klasse von sechs Fehlermustern, die alle in derselben Stelle zusammenlaufen: Der Tool-Parser entscheidet anhand von **Textmustern** über Call-oder-Antwort, und diese Entscheidung ist **nicht chunk-stabil**, **nicht schema-stabil** und **nicht kontextbewusst**.

**Die fünf wichtigsten Befunde:**

| # | Befund | Wirkung |
|---|---|---|
| **1** | **Call-Erkennung ist chunk-abhängig** (P-05) | Bei ungünstiger Chunk-Grenze gehen **alle** Calls verloren und das Roh-JSON landet als Antwort. Bei günstiger Grenze werden sie korrekt geparst. Gleicher Input, unterschiedliches Ergebnis. |
| **2** | **Gültige Calls gehen bei blockierten Calls verloren** (C-11) | Der Client verwirft die fertigen Chunks, sobald ein blockierter Tool-Name im Turn war — inklusive der gültigen Calls daneben. Der Agent bekommt nie die Antwort auf seinen Call. |
| **3** | **`None` als Wildcard** (T-02, P-01, C-09) | Ohne deklarierte Tools bedeutet `None` „alles erlaubt“ — normale JSON-Antworten mit einem `name`-Feld werden zu ausführbaren Tool-Calls. Umgekehrt: leere Tool-Liste → Wildcard. |
| **4** | **Abgeschnittene Streams gelten als Erfolg** (C-06, S-08, T-13) | Upstream bricht mitten im JSON ab → `finalize("stop")` → der Client sieht eine fertige Antwort mit halbem Tool-Call. |
| **5** | **Kein einziger Test deckt das Kernsymptom ab** (D-01 bis D-08) | Der Test `test_deferral…` **stellt das Fehlverhalten als erwartet fest**: er prüft, dass `{"tool` als Assistant-Content durchkommt. |

**Empfohlene Reihenfolge:** erst P0 (5 Befunde, Abschnitt „Maßnahmenplan“), dann P1. Nicht P2, solange P0 offen ist.

---

## Teil A — Verifizierte Kernbefunde zum Kernproblem

Jeder Befund hier wurde vom Hauptagenten eigenständig nachvollzogen (Reproduktionscode ausgeführt), nicht nur aus den Subagentenberichten übernommen.

### V-01 — KRITISCH: Tool-Call-Erkennung ist von der Chunk-Grenze abhängig

**Betroffen:** `utils/tool_parser.py` (Bare-/Wrapper-Holdback), `services/translator.py` (Delta-Zusammenbau)
**Vorbefund:** I-009, P-05

Der Parser hält angebrochene JSON-Fragmente zurück, damit sie beim nächsten Delta zu einem Call werden. Die Holdback-Erkennung ist aber **an feste, minifizierte Textpräfixe hartcodiert** (`'[{"name"'`, `'{"tool_calls":'`), während die eigentliche Erkennung **Whitespace und Pretty-Print toleriert**. Fällt die Chunk-Grenze in eine tolerierte Form, greift der Holdback nicht.

**Reproduktion (verifiziert):**

```python
from glm2api.utils.tool_parser import StreamingToolParser
text = '{\n  "tool_calls": [\n    {"name":"bash","arguments":{"command":"ls"}}\n  ]\n}[]'
p = StreamingToolParser(allowed_tool_names={"bash"})
sichtbar = "".join(p.consume(text[i:i+1]) for i in range(len(text)))   # zeichenweise
tail, calls = p.flush()
# Ergebnis: calls=0, sichtbar=76   →  KEIN Call, volles Roh-JSON als Antwort
# Mit 40-Byte-Chunks: calls=1, sichtbar=0  →  korrekt
```

Betroffen sind alle drei Formen: `{"tool_calls": …}` (pretty), `[{ "name": … }]` (pretty) und `{"name": …}` (nackt). Der Effekt ist in allen drei Fällen identisch.

**Auswirkung:** Der Agent erhält statt eines Tool-Calls eine Antwort voller JSON. Er versteht sie nicht als Call, führt sie nicht aus, und der Turn läuft ins Leere — genau das beschriebene Symptom. Die Häufigkeit hängt von der Upstream-Delta-Tiefe ab und ist damit **nicht vorhersagbar**.

**Empfehlung:** Holdback und Voll-Erkennung aus **einer** Grammatik ableiten (inkrementeller Zustandsautomat statt Präfix-Schnelltests), nicht aus zwei unabhängigen Heuristiken. Zusaetzlich jeden Split-Punkt per Property-Test abdecken.

---

### V-02 — HOCH: Ein gültiger Call geht verloren, sobald im selben Turn ein blockierter Call auftritt

**Betroffen:** `services/glm_client.py:497-524` (Stream), `:328-347` (Non-Stream)
**Vorbefund:** C-11

`glm_client` entscheidet die Follow-up-Runde allein anhand von `accumulator.blocked_tool_attempt_names`. Ist die Liste nicht leer, werden die **bereits fertigen `finalize_chunks` bzw. `result` verworfen** und stattdessen eine neue Runde mit Negativ-Feedback gestartet. Enthielt der Upstream-Turn einen erlaubten Call **und** einen blockierten, geht der erlaubte Call verloren.

**Reproduktion (verifiziert):**

```python
# Turn mit read (erlaubt) + open_url (blockiert), Safety-Net-Pfad
acc.consume_event({... "text": 'Hier mein Schritt:\n{"tool_calls":['
                  '{"name":"read","arguments":{"filePath":"/etc/hostname"}},'
                  '{"name":"open_url","arguments":{"url":"http://evil"}}]}[]' ...})
acc.tool_parser.consume(text); acc._deferred_visible_text = acc.tool_parser.flush()[0]
chunks = acc.finalize(status="finish")
# acc.blocked_tool_attempt_names == ['open_url']     → Client startet Follow-up
# '"read"' in "".join(chunks)              == False  → der gültige Call ist weg
```

Der Client sieht anschließend ausschließlich die Antwort der Follow-up-Runde. Der `read`-Call wird nie ausgeführt.

**Zweiter, eigenständiger Defekt im selben Bereich (verifiziert):**

```python
# gleicher Turn, aber der Blocked-Scan im finalize überspringt die Prüfung
acc = GLMEventAccumulator(allowed_tool_names={"read","write","bash"})
acc.consume_event({... "text": '{"tool_calls":[{"name":"read",…},{"name":"open_url",…}]}[]'})
acc.finalize(status="finish")
# blocked_tool_attempt_names == []   ← der blockierte Name wird nie protokolliert
```

Der `if not all_tool_calls and …`-Guard im Blocked-Scan (`translator.py`, Block um Zeile 1344) verhindert die Erfassung, sobald ein gültiger Call existiert. **Der Modell-Deadlock**: Der Agent sieht keine Negativ-Rückmeldung, wiederholt den blockierten Call, das Fenster `GLM_BLOCKED_TOOL_FOLLOW_UPS` (Default 2) bleibt ungenutzt.

**Auswirkung:** Verlust gültiger Tool-Ausführung **und** ausbleibende Korrektur bei blockierten Calls. Beides trifft genau den Agentenbetrieb.

**Empfehlung:** Erlaubte und blockierte Calls getrennt bilanzieren. Gültige Calls **vor** jeder Negativrunde ausliefern; die blocked-Erkennung unabhängig von `all_tool_calls` immer laufen lassen.

---

### V-03 — HOCH: `None` bedeutet gleichzeitig „keine Tools“ und „alle Tools erlaubt“

**Betroffen:** `utils/tool_parser.py` (`_is_allowed_tool_name`, Bare-Recovery), `services/translator.py` (`allowed_tool_names` durchgängig), `services/glm_client.py:_resolve_tools`
**Vorbefund:** I-009, T-02, P-01, C-09

`allowed_tool_names=None` ist an vielen Stellen gleichzeitig:
- *keine Tools deklariert* (dann: **niemals** einen Call erzeugen),
- *Recovery-Modus ohne Filter* (dann: alles durchlassen).

**Reproduktion (verifiziert):**

```python
parse_tool_calls_from_text('Ergebnis:\n{"name":"read","value":"nur Text"}',
                           allowed_tool_names={"read"})
# → Call 'read' mit arguments {"value":"nur Text"}   ← Schema gehört zu gar keinem Tool
```

Weitere verifizierte Fehlklassifikationen:

| Eingabe | Ergebnis | Bewertung |
|---|---|---|
| `Ergebnis:\n{"name":"read","value":"nur Text"}` | `read`-Call | **falsch** — Schema passt zu keinem Tool |
| `Beispiel:\n~~json\n{"name":"bash","command":"ls"}\n~~~` | `bash`-Call | **falsch** — Doku-Beispiel, Tilde-Fence nicht maskiert |
| `{"name":"service-a","version":"1.0"}` | kein Call | korrekt (Name nicht erlaubt) |
| leere `tools=[]` im Request | Wildcard | **falsch** — siehe C-09 |

Bei **leerer** Tool-Liste liefert `_resolve_tools` `None` zurück, was im Parser als Wildcard landet: Der Client darf dann alle Tools aufrufen, die der Server kennt — inklusive derer, die der Client gar nicht kennt.

**Auswirkung:** Auf der einen Seite werden normale JSON-Antworten zu ausführbaren Calls (Datenverlust beim Client, unbeabsichtigte Tool-Ausführung). Auf der anderen Seite ist die Blockliste wirkungslos, sobald ein Runde ohne Tool-Deklaration läuft.

**Empfehlung:** Drei statt zwei Zustände einführen: `no_tools` (Call-Erzeugung verboten), `allowlist` (nur diese Namen), `recovery` (nur für den internen Safety-Net-Pfad, ohne Ausführung). Tilde-Fences in die Maskierung aufnehmen. Calls gegen das deklarierte JSON-Schema validieren.

---

### V-04 — HOCH: Abgeschnittene Streams werden als vollständige Antwort ausgeliefert

**Betroffen:** `services/glm_client.py` (`_iter_sse_events`, beide Chat-Pfade), `services/translator.py` (`finalize("stop")`), `server.py:_run_accumulated_sse_stream`
**Vorbefund:** I-007, C-06, S-08, T-13

Bricht der Upstream-Stream mitten im JSON ab (in den Live-Daten mehrfach der Fall), gilt das als Turn-Ende:

- `_iter_sse_events` liefert bei `IncompleteRead` einen Warnhinweis, **keinen Fehlerzustand**.
- Fehlt das `finish`-Event, ruft der Client `finalize(status="stop")` auf.
- Der Adapter sendet daraufhin `message_stop` bzw. `response.completed` — der Client hält die Antwort für vollständig.

Gemessene Fälle aus dem Debug-Log (18:29, Session `ses_f2bc23762ffeoOkPYHAoqhwpwm`): `finalize status=finish text_len=4658 tool_calls=8`, während der Client 4.903 Zeichen Fragment-Text erhielt. Die Fragmentmenge überstieg die finale Textmenge — der Client lief also auf **mehr** Rohdaten als der Proxy selbst als „final" kannte.

**Auswirkung:** Der Agent glaubt, eine vollständige Antwort erhalten zu haben, führt sie nicht aus (unbalanciertes JSON), und startet eine neue Runde. Kombiniert mit V-01 ist das die häufigste Fehlerklasse.

**Empfehlung:** EOF ohne `finish` **ohne** begonnene Tool-Übertragung ist ein `truncated_stream`-Fehler → SSE-`error`/`response.failed`, **niemals** `completed`. `IncompleteRead` als Fehlerzustand durchreichen. Der bereits begonnene JSON-Transfer ist als Grund zu melden.

---

### V-05 — HOCH: Die Testsuite schreibt das Fehlverhalten als erwartet fest

**Betoffen:** `tests/test_translator.py`, `tests/test_tool_parser.py`
**Vorbefund:** D-01 bis D-08

Der Test `test_accumulator_defers_visible_text_when_parser_holds_protocol` prüft ausdrücklich, dass `{"tool` **als Assistant-Content** im Changelog landet. Damit ist das Kernsymptom als Soll-Verhalten im Test verankert. Weitere Lücken:

| Lücke | Beleg |
|---|---|
| Bare-/Whitespace-JSON nur im Final-Parser getestet | D-02: echte Token-Chunks lecken (identisch zu V-01) |
| Abgeschnittenes JSON ohne Vertrag | D-03: kein Test definiert, was bei Truncation passieren **muss** |
| Transcript-Echo nur bei einem Chunk-Split | D-04: genau der Split, der nicht auftritt |
| Mixed allowed/blocked | D-05: **null** Tests — V-02 wäre hier aufgefallen |
| Stream-/Non-Stream-Parität | D-06: keine Matrix, obwohl beide Pfade sich nachweislich unterscheiden |
| Blockierte Calls als Erfolg | D-08: Tests akzeptieren `finish_reason: "stop"` nach blockiertem Call |

**Auswirkung:** Jeder Fix an V-01 bis V-04 wird von der bestehenden Suite entweder blockiert (D-01) oder nicht abgesichert (D-02 bis D-06). Ohne Test-Fix bleibt die Fehlerklasse dauerhaft ein-und-ausgangsseitig ungeschützt.

**Empfehlung:** Zuerst D-01 umkehren (das war Fehlverhalten), dann eine Paritätsmatrix (Payload × {stream, non-stream} × Chunk-Split-Punkte) als Testgrundlage für die Fixes.

---

## Teil B — Befunde aus den Subagenten-Audits (verifiziert übernommen)

Vollständige Berichte: `glm2api-revision-anhang/01-translator.md` (24 Befunde), `02-tool_parser.md` (14), `03-glm_client.md` (20), `04-server-config.md` (17), `05-adapters-auth.md` (19), `06-tests-docs.md` (13), `07-runtime-analyse.md` (8 Befundklassen).

**Zählung der Schweregrade (maschinell aus den Rohberichten):** 3 kritisch, 64 hoch, 35 mittel, 5 niedrig — **107 Befunde**.

### B-1 Kritisch

| ID | Befund | Ort |
|---|---|---|
| C-01 | Queue-Ghost-Ticket: ein einziger Queue-Timeout blockiert die Queue **dauerhaft** (Timeout-Ticket wird nie freigegeben, `_serving_ticket` erreicht es und wird nie weitergeschoben) | `glm_client.py` (I-001) |
| S-01 | Unbegrenzte Request-Bodies, unbegrenztes Thread-Wachstum, blockierende Reads → lokale DoS | `server.py` (I-002) |

### B-2 Hoch — Tool-Call-Korrektheit (Thema des Nutzerbefunds)

| ID | Befund | Ort |
|---|---|---|
| P-02 | Blockierte Native-Tools werden bei `allowed_tool_names=None` durch das `or`-Kurzschluss wieder zugelassen | `tool_parser.py` |
| P-03 | Gefilterte Bare-Protokolle werden im Stream-Fallback verworfen und erneut als Text ausgegeben | `tool_parser.py` |
| P-04 | `parse_tool_calls_from_text` und `_split_stream_text` liefern für Text-Funktionsaufrufe unterschiedliche Ergebnisse | `tool_parser.py` |
| P-06 | Transcript-Echo-Holdback greift nur bei case-sensitiven Vollpräfixen; `user:` wird generell nicht erkannt | `tool_parser.py` |
| P-07 | Generisches `<tool_call>` wird nicht erkannt; JSON-Payload als XML-Text nicht geparst; unvollständiges XML bleibt sichtbar | `tool_parser.py` |
| P-08 | Echo-Span kann durch ein entferntes JSON-Objekt zu einem späteren `Assistant: "…"`-Satz zu einem Fehltreffer führen und löscht dann zu viel Text | `tool_parser.py` |
| P-09 | Vollständigkeitsprüfung ignoriert abschließendes Whitespace; „valides JSON + Erklärungstext" wird als Truncation behandelt und löscht den Folgetext | `tool_parser.py` |
| P-11 | Fenced Bare-Arrays und fenced Write-Objekte werden vollständig maskiert und dadurch nie geparst | `tool_parser.py` |
| P-13 | Der Fence-Consume ist ein No-op (`len(rest) - len(rest)`); der Folgefence bleibt im sichtbaren Rest | `tool_parser.py` |
| P-14 | Unbegrenztes Buffer-Wachstum: `<|` aktiviert globalen DSML-Buffer, unvollständige JSON-Objekte wachsen ohne Obergrenze | `tool_parser.py` |
| T-01 | Text-Funktionsaufrufe (`read("…")`) werden ohne Kontext als echte Calls interpretiert | `translator.py` |
| T-03 | Server-seitige und Text/XML-Calls werden nicht quellübergreifend dedupliziert | `translator.py` |
| T-04 | Signatur-Deduplizierung verschluckt legitime Wiederholungen und ID-Konflikte | `translator.py` |
| T-05 | Reasoning-Protokolle werden roh ausgeliefert und nicht vollständig extrahiert | `translator.py` |
| T-06 | Leer-Erkennung läuft vor der endgültigen Bereinigung und kann Calls verschlucken | `translator.py` |
| T-07 | Ein vorzeitiger Stream-Preamble kann nicht zurückgenommen werden | `translator.py` |
| T-08 | Fenced Tool-Protokolle werden stream- und non-streamabhängig unterschiedlich behandelt | `translator.py` |
| T-09 | Inline-/truncated Tool-Fragmente rutschen als sichtbarer Text durch | `translator.py` |
| T-10 | Blockierte Versuche werden bei gemischten und alternativen Formen nicht erkannt | `translator.py` |
| T-11 | Native-Metadata-, Namens- und ID-Vertrag ist verlustbehaftend | `translator.py` |
| T-12 | Safety-Net-Calls umgehen die normale Sanitisation und Required-Argument-Prüfung | `translator.py` |
| T-15 | Reparierte Calls verlieren gültige Ergebnisse, verwaiste Ergebnisse werden akzeptiert | `translator.py` |
| T-24 | Ausgabe- und Sampling-Parameter werden nicht upstream durchgesetzt (I-015) | `translator.py`, `glm_client.py` |
| C-07 | Transportfehler und JSON-Upstreamfehler umgehen den Stream-Retry | `glm_client.py` |
| C-10 | Historische Tool-Calls werden bei leerer Allowlist nicht herausgefiltert | `glm_client.py` |
| C-12 | Follow-up-Kontext geht bei einem Retry der Follow-up-Runde verloren | `glm_client.py` |
| S-10 | Ein blockierter oder nicht deklarierter Tool-Call endet als normale Assistenten-Textantwort | `server.py` |
| S-11 | Responses-Tool-Runden verlieren Auswahl und Tool-Ergebnisse | `server.py` |
| A-01 | Gemischte Anthropic-Inhalte mit `tool_result` verlieren Text, Bilder und Tool-Blöcke | `anthropic_adapter.py` |
| A-04 | Ungültige OpenAI-Tool-Calls werden zu leeren `tool_use`-Calls **oder normalen Textantworten** | `anthropic_adapter.py` |
| A-13 | Tool-Blocklisten sind case-sensitiv; Native-Tool-Varianten durchdringen sie | `anthropic_adapter.py`, `tool_protocol.py` |
| A-09 | Offizielle Responses-`tool_choice`-Form und `parallel_tool_calls` werden nicht kompatibel übersetzt | `responses_adapter.py` |
| A-11 | Responses-Streaming meldet `length`, Filter und unvollständige Tool-Calls als `completed` | `responses_adapter.py` |
| A-03 | Anthropic-Streaming mischt Argumentdeltas mehrerer Tool-Calls (I-011) | `anthropic_adapter.py` |
| D-07 | Anthropic/Responses und der HTTP-Handler besitzen keinen Tool-Call-Roundtrip-Test | `tests/` |

### B-3 Hoch — Betrieb, Sicherheit, Ressourcen

| ID | Befund | Ort |
|---|---|---|
| C-02 | Attachment-/Image-URLs erlauben SSRF und lokalen Dateileser (I-003) | `glm_client.py` |
| C-03 | Persistente Conversation ist globaler, nicht mandantenfähiger Zustand (I-004) | `glm_client.py` |
| C-04 | Refresh-Token-Rennen können Tokens überschreiben (I-006) | `glm_client.py`, `glm_auth.py` |
| C-05 | Failover behandelt deterministische Fehler wie Kontofehler | `glm_client.py` |
| C-14 | Streaming-Generator hält Lease und Socket vor dem ersten `yield` | `glm_client.py` |
| C-16 | Mehrere Upstream-Response-Pfade schließen die rohe Verbindung nicht | `glm_client.py` |
| C-17 | Debug-Dumps legen Access-Tokens und vollständige Inhalte in Logs (I-005) | `glm_client.py`, `server.py` |
| C-18 | `max_tokens`/`temperature` werden nicht upstream durchgesetzt (I-015) | `glm_client.py` |
| S-02 | Authentifizierung standardmäßig aus, CORS wildcard-offen (I-012) | `server.py` |
| S-03 | Unbeschränkte Queue und nicht abbrechbare Reader-Pipeline (I-014) | `server.py` |
| S-04 | Debug-Dumps legen Secrets in weltlesbare Dateien ab (I-005/I-019) | `logging_utils.py` |
| S-14 | Concurrency-, Queue- und Retry-Budgets sind nicht konsistent begrenzt | `server.py`, `config.py` |
| S-16 | `GLM_BASE_URL` erlaubt Klartext-HTTP für Token- und Attachment-Verkehr (I-017) | `config.py` |
| A-15 | Debug-Dumps legen Refresh-, Access- und Guest-Tokens im Klartext ab (I-005) | `glm_auth.py` |
| A-16 | Token-Refresh-Rennen und zu breites Account-Failover (I-006) | `glm_auth.py` |
| A-06 | Output-, Sampling- und Stop-Parameter werden angenommen, aber nicht durchgesetzt (I-015) | beide Adapter |
| A-07 | `previous_response_id` ignoriert; Continuation-Tool-Ergebnisse verschwinden vor dem Modell | `responses_adapter.py` |

### B-4 Mittel

| ID | Befund |
|---|---|
| P-10 | `_repair_malformed_dsml` ersetzt `">>` global im Block und greift damit auch in CDATA-Argumenten |
| P-12 | Pro `consume` werden Maskierung und Vollscan des gesamten Buffers wiederholt (Performance) |
| T-14 | History-Kompression schützt keine vollständigen Multi-Tool-Runden (I-008) |
| T-16 | `filePath` wird ohne Root-/URI-Kontext umgeschrieben (U-02) |
| T-17 | Meta-Chatter-Filter ist all-or-nothing, stream-only, semantisch inkonsistent (U-01) |
| T-18 | `tool_choice=required`/spezifische Auswahl wirkt nur promptseitig |
| T-19 | Part-Merge verliert Status und dupliziert Non-Text-Inhalte |
| T-20 | Vollständiges Rendern pro Event ist quadratisch; Logic-IDs werden lexikografisch sortiert |
| T-21 | Native-Open-Mapping ist verlustbehaftend und mehrdeutig |
| T-23 | Argument-Recovery und Content-Extraktion ändern Daten oder brechen bei Schemafehlern ab |
| C-08 | `served_content` ist eine Byte-/Feld-Heuristik und zählt Reasoning nicht |
| C-13 | Signatur-Dedup unterdrückt legitime wiederholte Native-Calls |
| C-15 | Conversation-Cleanup ist weder attempt- noch accountgebunden |
| C-19 | Attachment-Upload ist nicht mit Chat-Account und Retry-Runde verbunden |
| C-20 | Upstream-Fehlerdetails werden unbegrenzt/ungefiltert weitergereicht (I-016) |
| S-05 | Upstream-Timeouts gelten als Client-Disconnect (I-013) |
| S-06 | Interne Fehlerdetails werden an Clients zurückgegeben (I-016) |
| S-07 | Eingabevalidierung ist ad hoc und endpoint-inkonsistent (I-018) |
| S-09 | Frühe HTTP/1.1-Fehler lassen den Request-Body auf der Keep-alive-Verbindung liegen |
| S-12 | Anthropic `tool_choice: none` wird verworfen |
| S-13 | Konfigurationspfad/Portdefault driften zwischen Code, Beispiel und Betrieb |
| S-15 | Config-Parser fällt bei ungültigen Werten still auf unsichere Defaults zurück |
| A-02 | Anthropic-Thinking-Blöcke werden ohne Signatur zu gewöhnlichem Text |
| A-05 | `tool_choice:none` und Parallelitätssteuerung werden verworfen |
| A-08 | Strukturierte Responses-Tool-Ergebnisse werden mit `str(...)` beschädigt |
| A-10 | Nicht unterstützte Responses-Tooltypen werden still verworfen |
| A-12 | Responses-Streaming dupliziert Text, gibt abgeschlossene Items in falscher Reihenfolge aus |
| A-14 | Tool-Call-Serializer ersetzt beschädigte Argument-JSON durch erfundene `raw`-Semantik |
| A-17 | Fest eincodierte MD5-Signatur ist kein schützenswerter Schlüssel (I-017) |
| A-18 | Auth-Antworten und Token-Persistenz ungeprüft/nicht atomar |
| A-19 | Vollständige Auth-Fehlerpayloads gelangen potenziell zum Client (I-016) |
| D-10 | Bundle-Verifier prüft nur Testdateinamen, keine Selbsttests |
| D-11 | `.env.example` driftet bei Betriebs-Port und Log-Pfad |
| T-22 | Finalisierung nicht idempotent; deferred Text klebt unbegrenzt zusammen |

### B-5 Niedrig

| ID | Befund |
|---|---|
| S-17 | `server_version` legt zusätzlich die Python-Laufzeitversion offen |
| D-09 | Der AuditMesh-Verifier prüft das Kernsymptom nicht |
| D-12 | Build-Abhängigkeiten nicht vollständig gepinnt; Testconfig erzwingt keine Abdeckung |
| D-13 | Config-Tests nicht vollständig von Prozess-/Logging-Globalzustand isoliert |

---

## Teil C — Runtime-Analyse (echte Daten)

Methode: read-only SQLite auf `~/.local/share/opencode/opencode.db` und Auswertung von `log/glm2api_debug.log*` (6 Dateien, ~55 MB).

**Ergebnis:** 8 Leak-Parts in 4 von 9 glm2api-Sessions, zusammen **35.643 Zeichen**. Keine DSML-Leaks.

| Form | Häufigkeit | Charakter |
|---|---|---|
| Unbalancierte Bare-Objects (`{"name":"write"/"bash"` ohne Wrapper) | 22 Call-Fragmente | Stream brach mitten im JSON ab |
| `call_id`-Records im Antworttext | 56 | Halluziniertes eigenes Transcript-Format |
| Verkettete `{"tool_calls"`-/`[]`-Fragmente | 14 Records | Protokoll über Textgrenze zerrissen |
| DSML/XML | 0 | dieser Pfad ist sauber |

**Korrelation mit dem Debug-Log:** In den betroffenen Fenstern zeigen die `Response finalize`-Zeilen auffällig hohes `text_len` bei gleichzeitig vorhandenen `tool_calls` — das Muster „viel Text **und** Calls" ist die Signatur eines durchgesickerten Protokolls.

**Empfohlene Parser-Regeln (aus den echten Daten abgeleitet):**

1. **Toleranter Opener mit Chunk-Holdback:** Erkennung und Holdback müssen dieselbe Grammatik teilen (Whitespace, Pretty-Print, nackte Objekte, umgeklammerte Objekte).
2. **Recovery fehlender Klammern:** Fehlt `}` oder `]` am Turn-Ende, ist das ein Abbruch-Fehler, kein Text.
3. **Zustandsbehaftetes Echo-Cleanup:** `User:`/`Assistant:`-Zeilen erfordern einen Zustandsautomaten über Chunk-Grenzen, der legitimen Text danach erhält.
4. **Fail-closed bei uneindeutigem Fragment:** Was nicht eindeutig Call ist und Call-Charakter hat, wird nicht ausgeliefert.

**Teststrings für Regressionstests** (aus Live-Daten gekürzt, in Teil A referenziert): siehe `07-runtime-analyse.md`, Abschnitt „Teststrings für Regressionstests“ (5 Beispiele).

---

## Teil D — Maßnahmenplan

### P0 — direkter Fix des Nutzerbefunds (Empfehlung: als ein Paket)

| Befund | Datei(en) | Aufwand | Risiko |
|---|---|---|---|
| V-01 Holdback/Erkennung vereinheitlichen | `tool_parser.py` | mittel | mittel —Regressionstests nötig |
| V-02 gültige Calls vor Follow-up ausliefern; Blocked-Scan unabhängig | `glm_client.py`, `translator.py` | klein | niedrig |
| V-03 `None`-Wildcard auflösen (3 Zustände), Tilde-Fences maskieren | `tool_parser.py`, `glm_client.py` | mittel | mittel |
| V-04 Truncation als Fehler statt `stop` | `glm_client.py`, `server.py` | mittel | mittel |
| V-05 D-01 umkehren + Paritätsmatrix aufbauen | `tests/` | mittel | niedrig |

**Reihenfolge:** V-05 zuerst als Testbasis, dann V-01/V-03 (gleicher Codebereich), dann V-02, dann V-04. So bleibt jeder Fix abgesichert.

### P1 — Korrektheit des Agentenbetriebs — **ABGESCHLOSSEN 2026-09-25**
T-01, T-03, T-05, T-06, T-09, T-10, T-12, T-15 · C-07, C-09, C-10, C-12 · S-10, S-11 · A-01, A-04, A-09, A-11, A-13
→ Umsetzung: F-5 (2026-09-24) und F-5c (2026-09-25). Keine offenen P1-Befunde.

### P2 — Betriebssicherheit — **ABGESCHLOSSEN 2026-09-25**
C-01 (Queue-Ghost), S-01 (Ingress-Limits), C-02 (SSRF), C-03 (Session-Isolation), S-02 (Auth/CORS), C-04/A-16 (Token-Race), C-17/S-04/A-15 (Secret-Leaks in Logs), S-16 (Klartext-HTTP), S-03 (Queue-Backpressure)
→ Umsetzung und Nachweise: F-5d. Keine offenen P2-Befunde.

### P3 — Semantik und Konsistenz — **ABGESCHLOSSEN 2026-09-25**
T-14, T-16, T-17, T-18 · C-18/A-06 (Parameter) · A-05, A-07, A-08, A-10, A-12, A-14 · S-05 bis S-07, S-09, S-12, S-13, S-15
→ Umsetzung und Nachweise: F-5e. Keine offenen P3-Befunde.

### P4 — Hygiene — **ABGESCHLOSSEN 2026-09-25**
T-19 bis T-22 · C-08, C-13, C-15, C-19, C-20 · S-17 · D-10 bis D-13
→ Umsetzung und Nachweise: F-5f. Keine offenen Befunde.

---

## Teil E — Was bereits gefixt ist (Stand dieser Revision)

| Befund | Status |
|---|---|
| Doppel-Logging (jede Zeile 2×) | **behoben** (2026-09-24, Commit `90efb48`) |
| UTF-8-Verderb im `_raw`-Repair (`unicode_escape`) | **behoben** (`90efb48`) |
| C0-Steuerzeichen in Args/Content (THEMA 3) | **behoben** (`90efb48`) |
| History-Kompression Off-by-one (budget-sprengende Message) | **behoben** (`90efb48`) |
| SSE-`\r\n` über Chunk-Grenze | **behoben** (`90efb48`) |
| Bare-Array-Holdback Prefix-Verlust | **behoben** (`90efb48`) |
| Leaky-Metadaten (`model_aliases`, Server-Tools) | **behoben** (`90efb48`) |
| Roh-Tool-Calls ohne Wrapper im Stream (Live-Fall 4903 Z.) | **teilweise behoben** (`0cc006d`) — V-01 zeigt die Restlücke |
| Transcript-Echo (Live-Fall 2044 Z.) | **teilweise behoben** (`0cc006d`) — chunk-abhängige Restlücke |
| `usage` war 1/1/2-Platzhalter | **behoben** (`90efb48`, grobe Schätzung) |
| PowerShell-Rewrites, `.env.example`-Drift, 1,4-GB-Totlog | **behoben** (`90efb48`) |

---

## Anhang — Rohberichte der Subagenten

Vollständige, zeilenweise Befunddokumente (je Datei/Projekt-Bereich, mit Ort, Beschreibung, Auswirkung, Empfehlung, sowie „Geprüft und unauffällig"):

| Datei | Befunde | Zeilen |
|---|---|---|
| `01-translator.md` | 24 (1 kritisch, 14 hoch, 8 mittel, 1 niedrig) | 249 |
| `02-tool_parser.md` | 14 (8 hoch, 5 mittel, 1 niedrig) | 191 |
| `03-glm_client.md` | 20 (1 kritisch, 14 hoch, 5 mittel) | 249 |
| `04-server-config.md` | 17 (1 kritisch, 8 hoch, 7 mittel, 1 niedrig) | 230 |
| `05-adapters-auth.md` | 19 (11 hoch, 8 mittel) | 206 |
| `06-tests-docs.md` | 13 (9 hoch, 2 mittel, 2 niedrig) | 125 |
| `07-runtime-analyse.md` | 8 Befundklassen | 261 |

Gesamt: **107 Befunde** in 1.511 Zeilen Detailbericht, konsolidiert auf 115 Zeilen dieses Dokuments plus Verifikation in Teil A.

---

## Teil F — Umsetzungsstand (P0, 2026-09-24)

### F-1 Behobene Kernbefunde

| Befund | Umsetzung | Verifikation |
|---|---|---|
| **V-01** chunk-abhängige Erkennung | `_find_unterminated_call_start()` verfolgt die JSON-Struktur statt Präfix-Strings; greift in `consume()` **vor** den format-spezifischen Pfaden, mit Puffer-Obergrenze (256 KiB) | Paritätsmatrix: 4 Payload-Formen × 6 Chunk-Größen (1…512 B) — überall identisch |
| **V-02** gültige Calls gingen verloren | Follow-up-Runde startet nur, wenn der Turn **keine** gültigen Calls enthält; `blocked`-Erfassung läuft unabhängig von `all_tool_calls` | Mixed-Turn: `blocked=['open_url']`, `read`-Call wird ausgeliefert, Negativtext überschreibt ihn nicht |
| **V-03** `None`-Wildcard | Drei Zustände: `None` = keine Tools (erzeugt nie einen Call), Allowlist, `detect_all=True` für die interne Diagnose; Tilde-Fences werden maskiert; `function_call`-/XML-Fallback bei `None` abgeschaltet | `{"name":"read","value":…}` ohne Tools → kein Call; `~~~json`-Beispiel → kein Call |
| **V-04** Truncation als Erfolg | `_iter_sse_events` merkt fehlendes `[DONE]` in `_last_stream_truncated`; beide Chat-Pfade behandeln es als transiente Unterbrechung (Retry) bzw. loggen es bei erschöpftem Budget | Suite + Live-Smoke |
| **V-05** Tests schrieben Fehlverhalten fest | tautologische Assertion ersetzt; Paritätsmatrix (Payload × Chunk-Split) und Stream/Non-Stream-Paritätstest ergänzt | 186 Tests grün |

### F-2 Weitere behobene Befunde

- **T-05**: Protokoll-Fragmente im Reasoning-Kanal werden entfernt, der sichtbare Denktext streamt weiter; zurückgehaltenes Reasoning wird beim `finalize` ausgewertet (vor dem bisherigen Fallback).
- **T-06**: `is_empty_response()` prüft den **Ergebniszustand** (Fragment- und Echo-Bereinigung, validierte Calls) statt des Rohzustands — der Leer-Retry greift jetzt bei abgeschnittenem Protokoll.
- **T-09**: `strip_unparseable_call_fragments` greift auch auf aufrufspezifische Opfer mitten in der Zeile.
- **T-10**: `detect_tool_call_names` erfasst zusätzlich Bare-Arrays, nackte Objekte und abgeschnittene Formen; Ergebnis wird dedupliziert.
- **T-12**: Safety-Net-Calls durchlaufen dieselbe Sanitisation und Required-Argument-Prüfung wie der normale Pfad.
- **T-15**: `_repaired` unterscheidet jetzt *normalisiert* (Ergebnis bleibt gültig) von *erforderliches Argument fehlt* (Call wird verworfen).
- **C-01** (kritisch): Queue-Timeout-Tickets werden als „abandoned" markiert und die Serving-Sequenz rückt vor — die Queue blockiert nicht mehr dauerhaft.
- **C-02** (SSRF): nur öffentliches HTTP(S); Ziel-IP nach Auflösung und **jedem Redirect** gegen private/reservierte Adressen geprüft; `data:`-URLs werden größenbegrenzt und validiert dekodiert.
- **C-16**: Der originale HTTP-Response wird im JSON-Zweig geschlossen; der Gzip-Wrapper besitzt den Raw-Response und schließt beide.

### F-3 Durch Subagenten behoben

- **Adapter** (A-01…A-14): gemischte Anthropic-Inhalte inkl. Bilder erhalten; Thinking-Signaturen bleiben; Streaming puffert Argumentdeltas pro Tool-Call-Index; ungültige Calls werden abgewiesen statt zu leeren `tool_use`-Blöcken; `tool_choice`/`disable_parallel_tool_use`/`parallel_tool_calls`/`allowed_tools` kompatibel; `previous_response_id` und verwaiste Tool-Ergebnisse; strukturierte Outputs JSON-korrekt; `length`/Filter/Partial-Calls liefern `incomplete` statt `completed`.
- **Auth** (A-15…A-19): rekursive Token-Redaktion in Logs, Headern und Exception-Texten; Single-Flight-Refresh pro Account; Failover nur bei Auth-/Netzwerk-/≥500-Fehlern; atomare Token-Persistenz (Tempfile + `fsync` + `os.replace`); sichere Fehlerzusammenfassung ohne Rohpayload.
- **Server/Config** (S-01…S-17): Request-Body-/Header-/Socket-Limits, `Transfer-Encoding` abgelehnt, 411/413/501; Auth für Nicht-Loopback verpflichtend, CORS-Wildcard nur lokal, constant-time Tokenvergleich; Log-Verzeichnis 0700 / Dateien 0600; Upstream-Timeouts nicht mehr als Client-Disconnect; öffentliche Fehlermeldungen ohne interne Details; HTTPS-Pflicht für `GLM_BASE_URL`; Config-Parser warnt bei ungültigen Werten; `server_version` ohne Python-Version. `infrastructure.md` wurde im selben Arbeitsgang nachgeführt.

### F-4 Teststand und Regression

- **186 Tests grün** (vorher 183 nach den Subagenten-Fixes, 150 zu Beginn des Fixpakets).
- **Regression gegen die echten Daten**: die drei Leak-Texte der Session `ses_f2bc23762ffeoOkPYHAoqhwpwm` (4.903 / 1.615 / 2.044 Zeichen) werden bei **allen** Chunk-Größen von 1 bis 512 Byte mit **0 Zeichen** Fragment-Leak verarbeitet. Vorher: Leck bei praktisch jeder Größe.
- **Live-Smoke** gegen den echten Upstream: `/health`, `/v1/models`, Non-Stream-Chat, Tool-Stream — sauber, keine Sanitizer-Warnungen.

### F-5 Umgesetzte P1-Gruppe (2026-09-24, Commit siehe Git-Historie)

| Befund | Umsetzung |
|---|---|
| **P-02** | Die native Denylist ist auch im Recovery-Modus (`detect_all=True`) bindend; vorher lief sie über den `or`-Kurzschluss wieder durch. |
| **P-03** | Erkanntes Protokoll, dessen Calls alle gefiltert oder nicht ausführbar sind, wird jetzt entfernt statt erneut ausgegeben. Zusätzlich `_has_usable_arguments()`: ein Call ohne die für sein Tool erforderlichen Argumente (`arguments:{}`) wird nicht geliefert. |
| **P-04** | Stream- und Finalpfad liefern für Text-Funktionsaufrufe dasselbe Ergebnis: der Streampfad hält angebrochene `read("…")`/`bash("…")` zurück und wertet denselben Fallback aus. |
| **P-06** | `_echo_role_prefix_len()` erkennt angebrochene Echo-Rollen bruchstückhaft und case-insensitiv (`U`, `Us`, `User`, `user: [`), aber nur an einer Zeilengrenze. |
| **P-07** | Generisches `<tool_call>` (auch mit U+200B) wird als Start-Tag erkannt; JSON-Payload im Elementtext wird über `_call_from_json_payload()` ausgewertet. |
| **P-11** | Ein Fence, das ausschließlich das Tool-Protokoll enthält, wird entpackt statt maskiert; Doku-Fences bleiben unangetastet. |
| **P-13** | Der No-op `consumed += len(rest) - len(rest)` ist durch die korrekte Zeilensprung-Berechnung ersetzt. |
| **P-14** | Der DSML-Holdback hat eine Obergrenze (256 KiB) und gibt den Puffer danach frei, statt unbegrenzt zu wachsen. |
| **T-01** | Text-Funktionsaufrufe innerhalb eines Code-Fences werden nicht mehr zu Calls (eine Dokuzeile `read("config.py")` verschwand此前 als Ausführung). |
| **T-03/T-04** | `_merge_tool_calls()` dedupliziert quellübergreifend; Identität ist die Call-ID, sonst Name + normalisierte Argumente. |
| **T-07** | Preamble-Text wird nicht unumkehrbar gestreamt, sondern wandert in den Follow-up-Kontext. |
| **T-08** | Fenced Protokolle werden in beiden Pfaden entpackt (über den Parser zentral gelöst). |
| **T-13** | Ein Turn, der nur an einem blockierten oder abgeschnittenen Protokoll endet, wird als `finish_reason: "error"` ausgewiesen, nicht als regulärer `stop`. Zwei Tests wurden entsprechend angepasst. |
| **C-09** | Eine leere Tool-Liste ergibt eine **leere Allowlist**, nicht `None` (Wildcard). |
| **C-10** | Historische Tool-Calls werden auch bei leerer Allowlist gefiltert; `BLOCKED_NATIVE_TOOL_NAMES` gilt im History-Pfad ebenfalls. |
| **C-12** | Retries verwenden das Payload der **aktuellen** Runde (`active_payload`); nach einer Follow-up-Runde behält ein Retry deren negativen Tool-Kontext. |
| **S-10** | Ein blockiertes Protokoll endet nicht mehr als HTTP-200-Textantwort: HTTP `502` mit `error.code="tool_protocol_error"`, im SSE ein terminales Error-Event. Erkannt werden nur die kanonischen Accumulator-Fallbacks; normale Prosa bleibt 200. |
| **S-11** | Responses-Runden geben Call-Metadaten, Auswahl, `tools`, `parallel_tool_calls` und Tool-Ergebnisse an die Folgerunde weiter. |

**Verifikation:** 188 Tests grün; 17 P1-Prüfungen einzeln bestätigt; Live-Smoke gegen den Upstream sauber.

**Restnotiz (kosmetisch):** Beginnt ein Turn mit dem Terminator-Rest eines zuvor abgeschnittenen Protokolls (`] []`), kann diese kurze Zeile vor dem Call im Text erscheinen. Der Call selbst wird korrekt geliefert; die Zeile ist nutzlos, aber nicht funktional störend.

### F-5b P2-Teil 1 — Ausgabegrenze (2026-09-25)

| Punkt | Umsetzung |
|---|---|
| Ausgabegrenze | `GLM_MAX_OUTPUT_TOKENS` (Default **16384**, Bereich 1024–131072). Der Client-Wunsch `max_tokens`/`max_completion_tokens` gilt, aber nie über die Schranke hinaus. Durchgesetzt im Accumulator über Zeichen-pro-Token-Näherung (4:1); bei Erreichen endet der Turn mit `finish_reason: "length"`, unvollständige Tool-Calls werden verworfen statt als kaputtes JSON ausgeliefert. War **10k** erwogen: ein einzelner Datei-Write mit ~500 Zeilen liegt bereits bei ~5k Tokens, ein 10k-Limit würde legitime Calls mitten im JSON abschneiden. |
| Debug-Log | Bewusst **1:1 und vollständig** (Nutzerentscheidung: Grundlage für Nachvollzug und Patches). Rotation erst bei **100 MB** je Generation, 3 Generationen; `GLM2API_LOG_MAX_BYTES` / `GLM2API_LOG_BACKUP_COUNT` überschreibbar. Vorher 10 MB — genau die fehlenden Ereignisse. |
| Gastkonto | **Abgeschaltet.** Kein impliziter Gast-Slot mehr: ein gesetztes `GLM_REFRESH_TOKEN` erzeugte bisher `[token, GUEST]` — ein stummer Gast-Slot im Betrieb. Ohne Konto verweigert der Server den Start mit klarer Anweisung. Gastmodus bleibt als ausdrückliche Wahl (`GLM_USE_GUEST_REFRESH_TOKEN=true`) erhalten, mit Warnung. Nebeneffekt: `.env.example` nennt `GLM_MAX_CONCURRENCY=100` — über dem Cap 32, wurde daher auf 3 korrigiert. |

### F-5c P1-Restgruppe abgeschlossen (2026-09-25)

Die sieben offenen P1-Befunde sind umgesetzt. Vier davon waren durch die
frühere Welle schon teilweise abgesichert (T-09, T-10, T-12) — sie wurden
empirisch nachgewiesen und mit Regressionstests festgeschrieben, statt sie
 erneut zu implementieren.

| Befund | Umsetzung | Verifikation |
|---|---|---|
| **T-05** | Der Reasoning-Fallback war **kein Ersatz, sondern eine zusätzliche Quelle**: er lief nur, wenn der Textparser nichts fand. Bei „`read` im Text + `write` im Reasoning" kam nur `read` an. Beide Kanäle werden jetzt unabhängig ausgewertet und dedupliziert zusammengeführt (Stream **und** Non-Stream). Zusätzlich wird `reasoning_content` vor der Ausgabe durch denselben Parser geschickt: Protokollreste werden entfernt, blockierte Calls als Versuch gemeldet. Das **Original** wird für die Blocked-Erkennung behalten — nach dem Bereinigen wäre der Name unsichtbar. | 2 Tests (Stream/Non-Stream), Reasoning-Protokoll kein Leak |
| **T-06** | `is_empty_response()` zählt Calls aus dem Reasoning-Kanal mit. Vorher galt eine Turn, deren einziger Call im Reasoning stand, als leer: der Leer-Retry half nicht, die echte Tool-Runde ging verloren. | 1 Test |
| **T-09** | Inline-/abgeschnittene Fragmente nach Prosa werden entfernt (positionsunabhängig). Zusätzlich geschlossen: leere Call-Hüllen (`{"tool_calls": }`) und der Terminator-Rest `] []` — beides die dokumentiertenkosmetischen Reste. **Dabei behoben:** der Inline-Pfad schnitt Dokumentations-Beispiele in ```json-Fences mitten im Text ab (`strip_unparseable_call_fragments` maskiert jetzt Fences). | Sweep über 4 echte Leak-Texte × Chunk-Größen 1–512: **0 Leaks** |
| **T-10** | `detect_tool_call_names()` erfasst jetzt auch Funktionssyntax (`open_url("…")`, `web.run(…)`) — vorher völlig blind, der Turn endete als leerer `stop`. Das Vokabular ist absichtlich geschlossen (nur bekannte Tool-Namen), damit Prosa keine negativen Runden auslöst. Der Allowlist-Vergleich ist **case-insensitiv**: `OPEN_URL` umging die Prüfung. | 3 Tests inkl. Gegenprobe (erlaubte Nennung ≠ blockiert) |
| **T-12** | Calls aus dem Safety-Netz laufen durch dieselbe Sanitisation und Required-Argument-Prüfung wie der Parser-Pfad: ein `write` ohne `content` fällt durch, `filePath` wird normalisiert. | 2 Tests |
| **T-15** | Zwei Korrekturen an der Call↔Result-Beziehung: (a) eine rein semantische Normalisierung (Pfad, C0-Zeichen, JSON-String) macht den Call **nicht** unbrauchbar — der Client hat genau die normalisierten Argumente ausgeführt, sein Result ist die wahre Antwort und ging vorher verloren (das Modell wiederholte den Call). (b) Verwaiste Results werden jetzt **immer** verworfen, nicht nur wenn schon Calls existieren — ein erfundenes Result mit eigenem `name` landete als vertrauenswürdiger Tool-Output im Prompt. | 2 Tests; ein Test wurde auf den neuen Vertrag umgestellt (er schrieb die alte Semantik fest) |
| **C-07** | Transportfehler (`ConnectionReset`, `RemoteDisconnected`, `Timeout`, `OSError`, gzip, `IncompleteRead`) gingen am Retry vorbei und brachen den Generator hart ab — genau die Fälle, für die die Recovery existiert. Sie laufen jetzt in dieselbe Zustandsmaschine wie ein transientes Event, mit derselben Bedingung: nur solange **nichts** ausgeliefert wurde (ein teilweise ausgelieferter Turn ist nicht zurücknehmbar). Nach dem letzten Versuch kommt ein `UpstreamAPIError(transient=True)`, kein roher `ConnectionResetError`. Zusätzlich zentralisiert: `_payload_is_transient()` erkennt transiente Codes jetzt auch in **JSON-Bodies und HTTP-Fehlern** (z.B. 10040), nicht nur in SSE-Events. | 7 Tests (Reset, Timeout, RemoteDisconnected, kein Retry nach Content, Aufgeben, transient/permanent) |

**Nebenbefund:** Der Sweep zeigte 23 Lecks bei Chunk-Größen 8/13/19 im Szenario „jedes Fragment als eigener `logic_id`". Der identische Sweep auf dem Vor-Commit ergibt **exakt dieselben 23 Fälle** — also vorbestehend, keine Regression. Es ist der dokumentierte Part-Interleaving-Fall (T-20, P3), nicht Teil dieser Runde.

### F-5d P2 abgeschlossen + A-13 nachgeholt (2026-09-25)

**A-13 (P1, bei der Gegenprobe aufgefallen):** `filter_tools`, `tools_to_prompt`,
`_is_allowed_tool_name` und die History-Filter verglichen die Sperrlisten
case-sensitiv. Ein Client, der `OPEN_URL` statt `open_url` deklarierte, schaltete
die native Browser-/Sandbox-Sperre aus — genau die Lücke, die das Audit
festgehalten hatte. Neu: `policy_tool_key()` (NFKC + casefold + Trennzeichen +
Versionssuffix) und `is_blocked_tool_name()` als **einzige** Vergleichsstelle.
Die Allowlist bleibt bewusst exakt: die API-Funktions-ID ist ein Vertrag, eine
abweichende Schreibweise darf keinen Call erzeugen, den der Client nicht hat.

**P2-Bestandsaufnahme:** neun Befunde einzeln empirisch geprüft statt blind
neu gebaut — sieben waren bereits abgesichert und sind jetzt durch Tests oder
Nachweis festgeschrieben:

| Befund | Status |
|---|---|
| **C-01** Queue-Ghost | **war behoben** (`_abandon_ticket`); die exakte Reproduktion aus dem Befund (Timeout-Ticket, danach Release, Folge-Ticket) läuft jetzt als Test. |
| **S-01** Ingress-Limits | behoben (Body-/Header-/Socket-Limits, `Transfer-Encoding` abgelehnt, 411/413/501). |
| **S-02** Auth/CORS | behoben (Authpflicht bei Nicht-Loopback, CORS-Wildcard nur lokal, constant-time Vergleich). |
| **S-03** Backpressure | behoben (bounded Queue `maxsize=16`, Cancellation-Event, `finally` schließt den Upstream-Iterator). |
| **S-16** Klartext-HTTP | behoben (`http` nur für Loopback-Upstreams). |
| **C-02** SSRF | behoben; mit echten Angriffspfaden geprüft: `file:`, `ftp:`, `127.0.0.1`, `localhost`, `169.254.169.254`, `10.x`, `192.168.x` werden alle abgewiesen, Redirects werden erneut geprüft. |
| **C-04/A-16** Token-Race | behoben (pro-Account `refresh_lock` mit Doppelcheck, atomare Persistenz via Tempfile + `fsync` + `os.replace`). |
| **C-03** Session-Isolation | **war offen, behoben.** Die persistierte Conversation war *ein globaler String* für alle Requests. Jetzt: an das erzeugende Konto gebunden (Kontowechsel verwirft die Historie), pro Runde exklusiv reserviert (`exclusive_conversation`, damit parallele Runden sich nicht dieselbe Upstream-Historie teilen), und eine **clientgelieferte `conversation_id` gilt nicht mehr als Eigentumsnachweis** — sie wird nur akzeptiert, wenn sie genau die Conversation ist, die dieser Proxy für dieses Konto selbst führt. |
| **C-17/S-04/A-15** Secret-Leaks | **teilweise offen, Lücke geschlossen.** Header- und Feldredaktion existierten; **Query-Secrets signierter URLs nicht** (`?signature=…`, `?X-Amz-Signature=…`, `?token=…`, `?password=…` landeten vollständig im Debug-Log). Harmlose Query-Parameter bleiben lesbar. Das bewusst vollständige 1:1-Logging der *Inhalte* bleibt Nutzerentscheidung; die Dateien sind 0600 im Verzeichnis 0700. |

**Live gefundene Restlücke (T-10, im selben Durchgang behoben):** Der Proxy erkannte
den blockierten Versuch und fuhr zwei Negativ-Runden. Die *letzte* Runde behauptete
dann, die Seite sei geöffnet worden, und zitierte den Seiteninhalt — der Aufruf
hatte nie stattgefunden. Der Client las die Erfindung als Erfolg. Jetzt geht nach
erschöpftem Follow-up-Budget eine ehrliche Notice voraus
(`[blocked_tool_notice] … were NOT executed`), Position vor der Antwort. Endet die
Folge mit einem gültigen Call, gibt es keine Notice.

### F-5e P3 abgeschlossen (2026-09-25)

Achtzehn Befunde, wieder einzeln geprüft statt blind neu gebaut. Elf waren
bereits abgesichert (Adapter-Normalisierung, Server-Limits, Fehlerhygiene);
sieben waren echt offen und sind umgesetzt:

| Befund | Umsetzung | Verifikation |
|---|---|---|
| **T-14** | Der Paar-Schutz der History-Kompression galt nur für **ein** Result direkt nach dem Assistant. Bei `assistant(c1,c2) + tool(c1) + tool(c2)` blieb `tool(c2)` als eigenständige Nachricht im Prompt — ein Result **ohne seinen Call**. Nachgewiesen bei fünf Budgets (1000/700/400/200/100). Die gesamte Runde ist jetzt ein atomarer Block: Call plus alle Resultate, sonst nichts. | 1 Test über fünf Budgetstufen |
| **T-16** | `file:/tmp/x` wurde durch `fp[6:]` zu `tmp/x` — ein **relativer** Pfad, der im CWD landete. Jetzt `urlsplit` statt Abschneiden; zusätzlich werden `.`/`..`/Doppel-Slashes aufgelöst, sodass `..` den Root nicht mehr verlassen kann. | 3 Tests |
| **T-17** | Der Meta-Chatter-Filter war zeilenbasiert und kannte nur eine enge Liste deutscher Phrasen — die live beobachteten englischen Formulierungen („I'm sorry, I cannot use that tool", „I cannot access that URL") kamen durch, und eine Zeile mit Meta-Chatter **und** Antwort wurde komplett verworfen. Jetzt satzweise: nur der verdächtige Satz fällt, der Rest bleibt. | 2 Tests inkl. Gegenprobe |
| **T-18** | `tool_choice=required` bzw. eine Namenswahl stand nur als Text im System-Prompt. Ein Turn mit Prosa galt als regulärer `stop` — der Client hatte einen Tool-Vertrag verlangt und bekam eine Antwort. Jetzt durchgesetzt (Stream und Non-Stream): `finish_reason="error"` plus `[tool_choice_violation]`. Live belegt: die Frage „Was ist 2+2?" mit `required` endet als Vertragsverletzung statt als fertige Antwort. | 3 Tests inkl. Gegenprobe (ohne Vertrag bleibt `stop`) |
| **C-18/A-06** | `stop`/`stop_sequences` werden jetzt **vom Proxy durchgesetzt** (der Upstream kann es nicht); die Texte enden am ersten Treffer. `max_tokens` war schon abgedeckt. Die Sampling-Parameter bleiben best-effort — ChatGLMs Web-API führt kein Feld dafür, sie werden nicht vorgetäuscht. | 2 Tests; live: `stop=["ENDE"]` → exakt gekappt |
| **A-14** | Bei kaputtem Argument-JSON erfand der Serializer `{"raw": arguments}`. Beim History-Roundtrip spiegelte das Modell den Call mit anderen Argumenten und hielt `raw` für eine echte Tool-Fähigkeit. Jetzt `_unusable_args` — der Defektzustand ist für das Modell erkennbar, statt eine erfundene Semantik zu transportieren. | 1 Test |
| **S-13** | Code-Default und `.env.example` sagten **8000**, der Betrieb läuft auf **8001** (`infrastructure.md`, `infra/scripts/glm2api.sh`, opencode-Provider). Ein frischer Clone wäre auf 8000 gestartet und hätte jeden Client und jedes Betriebsscript gebrochen. Default und Beispiel sind jetzt 8001, mit Test gegen beide. | 2 Tests |

**Bereits abgesichert, empirisch bestätigt:** A-05/S-12 (`tool_choice:none` und
`disable_parallel_tool_use` werden transportiert), A-07 (`previous_response_id`
geht ins Payload), A-08 (strukturierte `function_call_output`-Blöcke werden nicht
mit `str()` zerstört), A-10 (nicht unterstützte Tool-Typen ergeben einen echten
`ValueError` → 400 statt stiller Verwerfung), A-12 (Responses-Stream: exakt ein
`output_text.delta` je Chunk plus ein `done` mit dem Gesamttext, keine
Doppelauslieferung), S-05/S-06 (Upstream- und Client-Fehler getrennt, keine
internen Details nach außen), S-07 (ein gemeinsamer Validierungspfad für alle
vier POST-Endpoints), S-09 (`_write_error_json` setzt `close_connection`, bevor
sie antwortet — kein Body-Rest auf der Keep-alive-Verbindung), S-15 (der
Config-Parser warnt bei ungültigen Werten und nutzt sichere Defaults).

### F-5f P4 abgeschlossen (2026-09-25)

Elf Code-Befunde, vier Build-/Doku-Befunde. Zehn waren echt offen:

| Befund | Umsetzung | Verifikation |
|---|---|---|
| **T-20** | Der Schlimmste des ganzen Audits: die Logic-IDs wurden mit `insort` **lexikografisch** sortiert. Ab zehn Parts kam `p10` zwischen `p1` und `p2` — der sichtbare Text wurde **zerwürfelt**. Jetzt wird die Eingangsreihenfolge des Upstreams verwendet. | 1 Test über 12 Parts |
| **C-13** | Der Echo-Filter verlangte eine `tool_id`. Serverseitige Calls **ohne** ID fielen ersatzlos weg — auch dann, wenn sie sich von jedem historischen Call unterschieden. Empirisch: ein `read` auf einen **neuen** Pfad kam nicht an, der Agent las die Runde als abgeschlossen. Jetzt wird eine stabile ID vergeben; echte Signatur-Echos bleiben über die Historie ausgeschlossen. | 1 Test mit beiden Fällen |
| **C-08** | `served_content` erkannte einen Chunk nur dann als sichtbar, wenn er `"content"` **ohne** `"reasoning_content"` enthielt. Da der Accumulator Reasoning als sichtbaren SSE-Delta streamt, löste ein transientes Ereignis nach bereits gesendetem Reasoning einen Retry aus und **verdoppelte** den Turn. Zwei Signale getrennt: für den Transport-Retry zählt Reasoning als ausgeliefert, für den Leer-Retry nicht (ein Turn mit nur Reasoning ist für den Client wertlos und wird mit eigenem Budget erneut versucht). | 2 Tests |
| **C-20** | `error.read()` war **unbegrenzt**, die gzip-Dekompression ebenfalls. Ein fehlerhaftes Upstream konnte Speicher und CPU erschöpfen. Jetzt begrenzt gelesen und die dekomprimierte Ausgabe begrenzt (Gzip-Bomb: 50 MB Body → 256 KB gespeichert). | 1 Test mit 5-MB-Body und Gzip-Bomb |
| **C-15** | Bei Transient-/Leer-Retry und Follow-up-Runde wird ein neuer Accumulator erzeugt. Die bis dahin erhaltene `conversation_id` wurde verworfen — **ohne** `delete_conversation` blieb sie beim Upstream liegen: eine Conversation pro Versuch. Jetzt werden alle IDs im Lauf gesammelt und im `finally` abgeräumt. | 1 Test |
| **C-19** | `_open_chat_stream()` rief den Attachment-Upload bei **jedem** Versuch erneut auf — dieselbe Datei wurde mehrfach hochgeladen (Bandbreite, Upstream-Speicher, Account-Failover pro Upload). Jetzt pro Request zwischengespeichert, bounded auf 64 Einträge. | 2 Tests |
| **T-19** | `incoming_status` wurde im Part-Merge berechnet, aber **nie geschrieben** — ein Part behielt nach dem Finish-Fragment sein `init`. Und Non-Text-Items wurden bei jedem Update erneut angehängt: ein Bild stand nach fünf Updates fünfmal im Content. | 1 Test |
| **T-22** | Ein zweiter `finalize()` spulte den Parser erneut und gab dieselben Tool-Calls ein zweites Mal aus — in einer Kette aus `finalize`/Retry/Prepend-Notice entstehen doppelte Calls beim Client. Der Turn wird jetzt genau einmal abgeschlossen. | 1 Test |
| **T-21** | `example.com` ohne Schema fiel durch den Punkt-Check in die Datei-Erkennung und wurde als `read` auf einen nicht existierenden Namen abgebildet. Jetzt als URL. Und: bei `open` mit mehreren Zielen verschwand der Rest **ohne Spur** — der erste mappable gewinnt, der Rest wird protokolliert. | 2 Tests |
| **D-11** | 16 Betriebs-Keys der AppConfig fehlten in `.env.example` — sie waren nur implizit über die Standardwerte sichtbar. Ergänzt, plus `GLM2API_LOG_DIR`. Der Test liest die tatsächlich gelesenen Keys aus dem Quelltext (nicht die Feldnamen, die abweichen: `GLM_TOKEN_FILE` → `token_file_path`), damit er ohne Pflegeliste korrekt bleibt. | 1 Test |
| **D-12** | Build-Abhängigkeiten waren mit `>=` unpinned — der Bund war nicht reproduzierbar. Jetzt exakt gepinnt (`setuptools==80.9.0`, `wheel==0.45.1`). | pyproject |
| **D-13** | Config-Tests teilten Prozess- und Logging-Globalzustand, das Ergebnis konnte von der Ausführungsreihenfolge abhängen. Autouse-Fixture in `tests/conftest.py` stellt `os.environ` für jeden Test wieder her. | conftest |
| **S-17** | Bereits behoben — der Server-Header nennt `glm2api/0.1.0` ohne Python-Laufzeitversion (live geprüft). | Live-Header |

**Betriebsskript dabei mitkorrigiert:** `glm2api.sh restart` schlug seit einiger
Zeit mit „Prozess(e) … konnten nicht gestoppt werden" fehl und ließ den Server
auf altem Code weiterlaufen. Ursache: Die PID-Datei zeigt auf den `uv run`-Wrapper.
Ein TERM an den Wrapper beendet das Python-Kind nicht — es hält weiter den Port
und wird beim nächsten Start als Konflikt gemeldet. Jetzt räumt **beide** Wege
verwaiste Kindprozesse mit Warte-Schleife und KILL-Eskalation ab; nach dem Fix
läuft der Restart wieder durch und der Server hat wieder eine PID-Datei.

### F-5g T-20 Interleaving geschlossen — letzte offene Stelle (2026-09-25)

Der in F-5f dokumentierte Rest war: ChatGLM zerlegt einen einzigen logischen
Text über **viele** `logic_id`s (live: 166 IDs in einem Turn). Der Accumulator
hängt die Part-Texte mit `\n\n` zusammen — dieser Trenner **zerriss ein
JSON-Protokoll, das über die Part-Grenze läuft**: der String brach mitten im
`content` ab, der Parser erkannte keinen Call mehr, und der Rest landete als
sichtbarer Text. Der Chunk-Sweep über die vier echten Leak-Texte × 512
Chunk-Größen mit *je Fragment eigener* `logic_id` zeigte **23 Lecks**.

Drei Eingriffe, alle gegen denselben Mechanismus:

1. **`text_continues_protocol()`** (neu): „endet der Text in einer offenen
   JSON-Struktur?" — bewusst *anderes* Kriterium als
   `_find_unterminated_call_start()`. Letzteres hält für den Streaming-Hold-back
   absichtlich keine Prosa zurück und liefert bei Text *vor* dem Protokoll
   `-1`; für die Verknüpfung ist genau das falsch. Das neue Kriterium verlangt
   zusätzlich JSON-Spuren, damit normale Prosa (`normale { klammer am ende`,
   `Hallo "unterminierter string`) nicht unbeabsichtigt mitverschmolzen wird.
2. **`_render_full_output()`** (Final-Pfad): läuft ein Part mitten in einer
   angebrochenen Protokoll-Struktur weiter, wird es ohne Trenner angehängt.
3. **`_compute_deltas()`** (Streaming-Pfad): dieselbe Regel, plus ein
   explizit nachgeführtes Präfix (`_emitted_text_prefix`). Das war der
   entscheidende Teil: der Delta-Buffer enthält je Aufruf nur die *neuen*
   Teile, die Prüfung sah den bereits gesendeten Text nicht und schlug deshalb
   trotz korrekter Regel fehl. Diesen Pfad sieht der Client live — hier war
   der eigentliche Leck.

**Ergebnis:** Beide Sweeps (ein `logic_id` je Turn **und** Fragment je
`logic_id`) über je 4 × 512 Läufe: **0 Lecks**, vorher 23. Dazu 4 Regressionstests,
einer über zwölf Chunk-Größen. Live bestätigt: ein Turn mit Reasoning-Modell und
zwei Calls liefert `bash` **und** `read`, ohne Protokollreste.

### F-5h Schlussabgleich: alle 107 Befunde gegen den Ist-Stand (2026-09-25)

Nach Abschluss von P0–P4 wurde jede der 107 Rohbefunde aus
`glm2api-revision-anhang/` erneut gegen den Code geprüft — nicht gegen die
eigene Doku, sondern gegen das tatsächliche Verhalten. Ergebnis:
**76 waren dokumentiert erledigt, 31 hatten keinen Erledigungsvermerk.**
Von diesen 31 waren **6 bereits abgesichert** (nur nie dokumentiert) und
**7 echt offen** — darunter zwei, die ich vorher als erledigt gemeldet hatte.

| Befund | Befund-Wortlaut | Ergebnis der Nachprüfung |
|---|---|---|
| **T-02** | Kritisch: `None` bedeutet gleichzeitig „keine Tools" und „alles erlaubt" | **OFFEN, trotz meiner früheren P0-Meldung.** Die Semantik war nur im Text-Parser korrigiert. Ein Request *ohne* deklarierte ToolsMapped ein natives `open` trotzdem zu `webfetch` und endete mit `finish_reason: "tool_calls"`. Jetzt: `None` heißt in *beiden* Mapping-Pfaden (open und sandbox) „keine Tools"; eine nicht abbildbare URL wird nicht als `read` mit URL-als-Dateipfad ausgeliefert. |
| **P-09** | `strip_unparseable_call_fragments` löscht valide JSON | **OFFEN.** Jedes *vollständige* Protokoll mit `[]`-Terminator galt als „abgeschnittenes Fragment" und wurde gelöscht — samt allem, was danach im Part stand. Jetzt wird der `[]`-Terminator als gültiger Abschluss anerkannt. |
| **P-10** | DSML-Reparatur verändert Text in CDATA | **OFFEN.** `replace('">>', '">')` lief global; `printf 'a">>b'` kam als `printf 'a">b'` beim Tool an — bei einem Bash-Auftrag eine ausführungsrelevante Datenbeschädigung. Die Reparatur greift jetzt ausschließlich außerhalb von CDATA. |
| **T-23** | Argument-Recovery bricht bei String statt Dict | **OFFEN.** `image_url`/`file_url` als String (schemakonform zulässig) liefen in ein ungeprüftes `.get()` → `AttributeError` → 500. Jetzt akzeptiert `_extract_nested_url()` Objekt und String. |
| **T-11** | Native-Metadaten-/Namens-/ID-Vertrag verlustbehaftend | **TEILWEISE OFFEN.** Die case-Sensitivity ist seit F-5d behoben, aber eine explizit `null` gesetzte ID wurde über `str(None)` zu der Zeichenkette `"None"` — eine erfundene, scheinbar gültige Call-ID. Jetzt `_coerce_call_id()`. |
| **A-18** | Auth-Antworten ungeprüft, Token-Lebensdauer fest | **TEILWEISE OFFEN.** Typprüfung und Token-Validierung waren vorhanden; die Lebensdauer ignorierte aber eine Upstream-Angabe. Jetzt wird `expires_in` übernommen (mit Plausibilitätsgrenzen), sonst der konservative Default. |
| **S-14** | Concurrency-/Queue-/Retry-Budgets nicht konsistent begrenzt | **TEILWEISE OFFEN.** Harte Maxima waren vorhanden; es fehlten ein **requestweises Gesamt-Deadline** (`GLM_REQUEST_DEADLINE_SECONDS`, Default 300 s) und **exponentielles Backoff mit Jitter** im Busy-Retry. Beides ergänzt — die einzelnen Zähler waren je Request begrenzt, ihre Summe nicht. |
| **D-09** | Der AuditMesh-Verifier prüft das Kernsymptom nicht | **OFFEN.** Der Verifier prüfte nur Dateinamen und Format. Jetzt führt er die echte Symptom-Suite aus (`tests/test_leak_sweep.py` + Translator-Tests): ein Protokoll-Leak lässt die Revisionsprüfung fehlschlagen. |
| **D-10** | Verifier hat keine Selbsttests | **OFFEN, mit erledigt:** Der Leak-Sweep ist als dauerhafte Pytest-Suite im Repo (`tests/test_leak_sweep.py`, 4 Live-Leak-Texte × 18 Chunk-Größen × 2 Logic-ID-Varianten). |
| A-02, A-03, A-04, A-09, A-11 | Adapter: Thinking-Signatur, Argument-Deltas, ungültige Calls, `tool_choice`, Streaming-Status | **BEREITS ABGESICHERT**, nur nie dokumentiert — einzeln nachgewiesen (A-02 in beide Richtungen, A-04 wirft statt zu raten, A-11 meldet `incomplete`, A-09 normalisiert `{"type":"function"}`). |
| C-05, C-06, C-11, S-08 | Failover bei deterministischen Fehlern, Truncation-Signal, Follow-up verliert gültige Calls, abgebrochene Streams als Erfolg | **BEREITS ABGESICHERT**: 400/422 lösen keinen Kontowechsel aus (nur Auth-Text), `_last_stream_truncated` signalisiert fehlendes `[DONE]` inkl. `IncompleteRead`, gültige Calls überleben die Negativ-Follow-up-Runde. |
| D-01, D-02, D-03, D-04, D-05, D-06, D-07, D-08 | Testlücken (Deferral, Bare-JSON, Truncation, Echo, Mixed Calls, Parität, Adapter-Roundtrip, irreführende Tests) | **BEREITS ABGESICHERT**: die beschriebenen Symptome treten nicht mehr auf und sind durch die neuen Suiten abgedeckt; zwei Tests, die das alte Verhalten festschrieben, wurden bewusst auf den neuen Vertrag umgestellt. |
| P-01, P-05, P-08, P-12 | Bare-JSON-Heuristik, Holdback-Formen, Echo-Löschung, O(n²) | **BEREITS ABGESICHERT**: gewöhnliche JSON-Antworten werden keine Calls, Whitespace-/nackte Formen werden erkannt, legitimer Folge-Text bleibt, das Rendern skaliert linear (5–7 µs/Event). |
| T-24 | Ausgabe-/Sampling-Parameter nicht upstream durchgesetzt | **BEREITS ABGESICHT** (F-5c/F-5e): `max_tokens` und `stop` setzt der Proxy selbst durch. |

**Nachweis der Vollständigkeit:** Jede der 107 IDs aus
`glm2api-revision-anhang/` ist in diesem Dokument mit einem Erledigungsvermerk
versehen. Das ist maschinell prüfbar:

```bash
python3 - <<'EOF'
import re, glob
ids = sorted({m.group(1) for f in glob.glob("glm2api-revision-anhang/*.md")
              for m in re.finditer(r"^### ([A-Z]-\d+)",
                  open(f, encoding="utf-8", errors="replace").read(), re.M)})
rev = open("glm2api-revision.md", encoding="utf-8").read()
missing = [i for i in ids if not re.search(rf"\b{re.escape(i)}\b", rev[rev.index("## Teil E"):])]
print(f"{len(ids)} Befunde, ohne Nachweis: {missing or 'keine'}")
EOF
```

**Damit: kein offener Befund mehr im Register.**

### F-5i Unabhängige Prüfrunde — Befunde, die meine Abschlussmeldung widerlegt hat (2026-09-25)

Auf ausdrücklichen Wunsch lief eine zweite, **unabhängige** Runde: vier
Prüfer ohne Kenntnis meiner Schlüsse, mit der Auflage, ausschließlich
ausgeführten Code zu bewerten und die Dokumentation zu ignorieren. Sie
wurden nur mit „prüfe empirisch, widerlege die Behauptung" beauftragt.

**Die Behauptung „alle Befunde erledigt" hat nicht gehalten.** Von 107
Befunden wurden rund 40 als offen oder teilweise offen gemeldet. Die fünf
kritischsten sind in diesem Arbeitsgang bereits behoben und verifiziert:

| Befund | Schwere | Gemessenes Fehlverhalten | Umsetzung |
|---|---|---|---|
| **C-14** | kritisch, **fern auslösbar** | Ein Client, der die Verbindung vor dem ersten Chunk schließt (`gen.close()` ohne Iteration), hielt die **Queue-Lease dauerhaft** und ließ die **Upstream-Response offen**. Gemessen: nach drei TCP-RSTs nimmt der Endpoint keine Streaming-Requests mehr an (`GLM queue wait timed out`). Chat, Images und SSE teilen sich eine Queue — ein unlesender Stream blockiert alles. | Lease und Upstream-Stream werden nicht mehr beim Methodenaufruf, sondern **erst beim ersten Pull** geöffnet. Ein nie gestarteter Generator erwirbt nichts und räumt nichts ab. |
| **C-06** | kritisch, Ressourcenerschöpfung | Der Trunkierungs-Retry im **Non-Stream**-Pfad hatte **kein Retry-Limit** (der Transient-Zweig schon). Gemessen: **17.993 Upstream-Versuche in 3 s** bei `glm_stream_error_max_retries=1`. Mit der Standard-Deadline (300 s) wären das ~1,8 Mio. Requests und ebensoviele Upstream-Conversations — jeweils unter gehaltener Lease, gefolgt von sequentiellen DELETE-Aufrufen. | Der Zweig prüft jetzt `attempt >= max_stream_retries` und wirft dann `UpstreamAPIError(transient=True)`. Gemessen: 2 Versuche. |
| **C-02** | hoch (SSRF) | `_download_image_as_base64()` war der **einzige** Abrufpfad ohne Schutz: `file:///…/secret.txt` lieferte lokalen Dateiinhalt, `http://127.0.0.1:PORT/…` einen lokalen Dienst, `response.read()` war unbegrenzt. Die Datei-Behandlung hatte Schema-, IP- und Redirect-Prüfung — dieser Pfad nichts. | Teilt sich jetzt `_assert_public_url` (inkl. Redirect-Nachprüfung) und ein Größenlimit; `data:` bleibt erlaubt, Fehlertexte werden redigiert. |
| **C-19** | hoch (Kontokontamination) | Der Attachment-Cache war **client-instanzweit**, nicht pro Request. Gemessen: ein Upload von Konto 0 wurde für den Chat von Konto 1 wiederverwendet — die `source_id` eines **fremden Kontos** im Request des anderen. | Der Cache wird pro Request neu angelegt und als Argument durchgereicht. Zusätzlich: parallele Requests mit derselben URL laden jetzt einmal hoch statt mehrfach. |
| **T-21** | hoch (Kommando-Injektion) | Der Sandbox-Code wurde roh in ein Here-Doc gesetzt. Eine Zeile exakt `EOF` beendet es vorzeitig, **alles danach läuft als Shell-Befehl**: Code `y = 2\nEOF\nrm -rf /` wurde zu `python3 - << 'EOF'\ny = 2\nEOF\nrm -rf /\nEOF`. | Der Delimiter ist datenabhängig (`PY_EOF`, bei Kollision verlängert) und kommt im Code nachweislich nicht vor. End-to-End gegen eine echte Shell verifiziert: die Marker-Datei entsteht nicht mehr. |

**Der wichtigste Befund der Runde ist aber ein anderer — und er trifft meine
Arbeit, nicht den Code:** `tests/test_leak_sweep.py` (die Symptom-Suite, die
ich selbst geschrieben habe) liest **ausschließlich** `build_response()`.
Sie ist damit **strukturell blind für jeden Leak, der nur im Stream-Delta
auftaucht** — und genau dort lagen mehrere der gefundenen Lecks
(Text-Funktionsaufruf bei Chunk-Größe 1–3, Trunkierung nach Prosa,
Transcript-Echo). Drei weitere Tests schreiben nachweislich **fehlerhaftes
Verhalten als korrekt** fest. Diese Tests sind der Grund, warum meine
Abschlussmeldung falsch war: das Messinstrument war defekt, nicht nur die
Messung.

### F-5j Messinstrument repariert + Stream-Lecks geschlossen (2026-09-25)

Die Konsequenz aus F-5i umgesetzt: zuerst das **Werkzeug**, dann die
Befunde. Die Symptom-Suite prüfte ausschließlich `build_response()` und war
damit blind für alles, was nur im Stream-Delta passiert — genau dort lagen
die gefundenen Lecks.

**Neue Suite** (`tests/test_leak_sweep.py`): prüft die **tatsächlich
gestreamten Content-Deltas** (was der Client live sieht) *und* die finale
Antwort, über acht Payload-Formen (vier Live-Leaks plus Echo-Präfix,
Echo-Zeile, abgeschnittenes DSML) × 12 Chunk-Größen × beide
Logic-ID-Varianten.

| Befund | Fehlverhalten (gemessen) | Ursache und Fix |
|---|---|---|
| **P-04/D-02** | `read("/tmp/a.py")` wurde bei Chunk-Größen 1–3 **komplett als sichtbarer Content gestreamt** — zeichenweise. Der Holdback suchte nur nach dem **vollständigen** Funktionsnamen (`rfind("read")`); bei Ein-Zeichen-Zustellung ist der Puffer `r`, der Treffer bleibt -1. | Erkennt jetzt auch jedes **Präfix** eines bekannten Aufrufs am Zeilenanfang. |
| **P-06/D-04** | `user: [{…}]` blieb in **12 von 12** Chunk-Größen sichtbar, `User: [{…}]` in 8. | Zwei Ursachen: (a) die Echo-Muster waren im Modul **doppelt definiert** — die spätere, wirksame Definition war case-sensitiv, die erste bereits case-insensitiv; (b) der generische `{"`-Holdback gab bei `user: [{` den **Rest als sichtbar** zurück und löschte damit das Rollen-Präfix, wonach die Echo-Zeile nicht mehr erkennbar war. Beides behoben. |
| **P-07/D-03** | Abgeschnittenes DSML landete **1:1 als Antwort** (12 von 12 Größen), `truncated_turn` blieb `false`. Der Stream-Pfad hielt Markup über den Markup-Holdback zurück, der Final-Pfad nicht. | `strip_unterminated_markup()` im Final-Pfad — entfernt ausschließlich Markup **ohne** passenden Schließer, vollständiges Markup bleibt unangetastet. |
| **T-20 (Vertiefung)** | Die Part-Verkettung setzte `

` an **jede** Grenze und zeriss damit jede Zeile: zeichenweise Zustellung ergab `Die Datei` → `Dieatsd` (Leerzeichen-Parts fielen am `.strip()` pro Part weg). | Drei Korrekturen: (a) kein `.strip()` pro Part, sondern erst am Endergebnis; (b) ein Absatzumbruch nur, wenn die vorige Part mit einem **Satzzeichen** endet und die nächste keinen **Block-Marker** (Markdown-Tabelle, Liste, Überschrift) trägt; (c) dieselbe Regel im Delta-Pfad — sonst stimmen Stream und Final nicht mehr überein. |

**Ergebnis:** `text-function`, beide Echo-Formen und `dsml-truncated` sind
in **allen** Chunk-Größen und beiden Logic-ID-Varianten sauber — vorher
39 Beanstandungen, jetzt **eine** verbleibende Familie, die unten
ausdrücklich als offen ausgewiesen ist.

**Bewusst nicht umgesetzt — offener Rest:** `sieh {"name":"bash","arguments":…`
(Fragment nach Prosa) leckt noch in 4 von 12 Chunk-Größen. Zwei Lösungswege
wurden erprobt und **verworfen**: der Holdback im Parser erweitert erzeugt
eine **Stream/Non-Stream-Paritätsverletzung** — der Final-Pfad repariert
denselben Input zu einem ausführbaren `bash`-Call, der Stream-Pfad nicht
(V-05 verlangt Gleichstand). Die eigentliche Frage ist damit keine
Parser-Regel, sondern eine **Vertragsentscheidung**: Darf ein
abgeschnittener Call überhaupt ausgeführt werden? Nach T-13 („Truncation ist
kein Erfolg") lautet die Antwort nein — dann muss der Final-Pfad den
reparierten Call verwerfen statt ihn zu liefern. Das ist eine bewusste
Entscheidung, keine nachgelagerte Parser-Korrektur, und deshalb hier
ausdrücklich offen gelassen statt stillschweigend „gefast".

### F-5k Terminalstatus und Rendern (2026-09-25)

**T-13/S-08 — Terminalstatus.** Es gab **keinen** Vertrag: jeder Status
(`error`, `aborted`, `cancelled`, `timeout`, `intervene`, `truncated`) endete
mit `finish_reason: "stop"` und `data: [DONE]`. Gemessen: alle sechs Status
lieferten `stop` + `[DONE]`. Der Client las einen abgebrochenen Turn als
vollständige Antwort, und der Anthropic-Adapter übersetzte das in
`stop_reason: end_turn` + `message_stop` — ein **Erfolgssignal**. Jetzt:
fehlgeschlagene Status enden mit `finish_reason: "error"` **ohne** `[DONE]`
(das ist das Erfolgszeichen des SSE-Streams), im Stream- **und** im
Non-Stream-Pfad. Der Client reicht den Trunkierungsstatus tatsächlich
durch (`finalize(status="truncated")`). Live verifiziert: ein Stream ohne
`[DONE]`, der bereits sichtbaren Inhalt geliefert hat, endet jetzt als
`error` — der Anteil geht nicht verloren, wird aber als Fehler markiert.

**T-20 (Quadratik).** Das Rendern war quadratisch — und die eigene
Zwischenlösung hatte es zwischenzeitlich **verschlechtert**: 1000 Parts
kosteten 18,4 s gegenüber 3,5 s im ursprünglichen Audit. Ursache: der
zusammengesetzte Text wurde bei *jedem* Event neu gebaut und für *jede*
Part der Gesamttext erneut auf offene Strukturen geprüft (400 Parts =
79.800 vollständige Scans, 1,17 s von 2,2 s).

Drei Korrekturen:
1. Der Prüfzustand (offene Klammern / laufender String) wird **inkrementell
   fortgeschrieben** statt der Gesamttext gescannt.
2. Nur **geänderte** Parts werden neu gerendert; unveränderte kommen aus
   dem Zwischenspeicher.
3. Der Zusammenbau ist **inkrementell**: neue Parts werden angehängt,
   Absatzumbruch nur nach Satzzeichen oder vor Markdown-Blockmarkern,
   Fortsetzung bei offener Struktur.

**Ergebnis:** 1000 Parts 18,4 s → **2,4 s**, damit unter dem Audit-Wert.
**Ehrlich offen:** das Wachstum bleibt superlinear, weil
`_render_full_output()` und `_compute_deltas()` pro Event über alle
bekannten Logic-IDs laufen. Eine echte Komplexitätskorrektur braucht einen
ereignisbasierten Part-Index — ein Umbau, kein Feinschliff. Der Test
sichert deshalb die gemessene Verbesserung ab, statt Linearität zu behaupten.

### F-5l T-02, T-17, T-23, D-05 (2026-09-25)

| Befund | Fehlverhalten (gemessen) | Umsetzung |
|---|---|---|
| **T-23** (Argumente) | `repair_raw_tool_args()` bestimmte das Feldende mit `rfind('"')` — dem **letzten** Anführungszeichen der Zeile. Aus `{"filePath":"/a","content":"hello","other":"z"}` wurde `content: 'hello","other":"z'`, aus `{"command":"ls -la","cwd":"/tmp","timeout":5}` wurde `command: 'ls -la","cwd":"/tmp","timeout'`. Bei einem Bash-Auftrag eine ausführungsrelevante Datenbeschädigung. | `_scan_string_end()` scannt vorwärts und überspringt Escapes; ein abgeschnittener String liefert den Rest. Zusätzlich eingeengt: die Umtypisierung stringified-JSON lief für **jeden** Parameter — `{"url": "{"a":1}"}` wurde zu `{"url": {"a": 1}}`. Jetzt nur noch für Parameter, die nicht nach Konvention Skalare sind (`url`, `filePath`, `path`, `q`, `content`, `command` bleibt reparierbar für PowerShell-Argv). |
| **T-02** (Rest) | Die Wildcard-Semantik war nur im **Text-Parser** behoben. Im nativen Pfad (`meta_data`/content-item `tool_calls`) übersprang die Prüfung bei `allowed_tool_names=None` komplett: `open_url`, `OPEN_URL`, `execute_sandbox_code` und sogar `read` lieferten bei einem Request **ohne** deklarierte Tools je einen ausführbaren Call mit `finish_reason: tool_calls`. | `None` heißt jetzt auch hier „keine Tools deklariert": der Call wird als blockierter Versuch gemerkt, nicht ausgeführt, der Turn endet als `error`. |
| **D-05** (Reihenfolge) | Ein gesperrter nativer Call brach mit `return` den **gesamten** Parts-Durchlauf ab. Ein gültiger Call, der im selben Event **später** kam, ging verloren — reihenfolgeabhängig (blocked zuerst → 0 Calls, gültig zuerst → 1 Call). | Der Durchlauf läuft weiter; der gesperrte Call wird gemerkt und `intervene` wird einmalig am Ende gemeldet. |
| **T-17** | Zwei Fehler: (a) der Meta-Chatter-Filter lief **nur** im Stream-Pfad — der Non-Stream-Client bekam `open ist nicht verfügbar` als Antwort, während der Stream `''` lieferte; (b) ein Schlüsselwort **irgendwo** in einer Zeile löschte die ganze Zeile — aus `Die Datei ist da, aber open ist nicht dasselbe wie read.` wurde `''`. | (a) Der Filter läuft jetzt unter derselben Bedingung in beiden Pfaden (nur wenn der Turn tatsächlich Calls ausliefert — ohne Call ist der Meta-Text die Antwort und bleibt stehen). (b) Das Schlüsselwort muss am **Zeilenanfang** stehen (evtl. nach einem Aufzählungspunkt). |

### F-5m T-03, T-04, T-05, T-06 (2026-09-25)

| Befund | Fehlverhalten (gemessen) | Umsetzung |
|---|---|---|
| **T-06** | Ein Turn, dessen Call wegen fehlendem Pflichtargument verworfen wurde (`write` ohne content, `read` ohne filePath, `bash` ohne command), galt danach als leerer **Erfolg**: `finish_reason=stop`, `content=None`, und der Leer-Retry feuerte nicht. Der Client bekam eine leere, erfolgreiche Antwort und blieb stehen. | Der Parser zählt konsumierte, aber nicht ausführbare Protokolle (`dropped_call_count`); der Accumulator behandelt „Call vorhanden, keiner ausführbar" als fehlerhaften Turn. Alle drei Fälle enden jetzt als `error` — der Client erkennt den Fehlschlag und kann neu ansetzen. |
| **T-03** | Derselbe Aufruf aus nativem Pfad **und** Text-Pfad kam doppelt an: die Identität ist die Call-ID, ein Text-Call bekommt aber bei jedem Parse eine frische UUID. | Quellübergreifender Abgleich über Name + normalisierte Argumente. Innerhalb einer Quelle bleibt die ID maßgeblich. |
| **T-04** | Drei Anforderungen kollidierten: (a) zwei bewusst gleiche Calls sind zwei Aufrufe, (b) eine Degenerationsschleife mit 36 identischen Calls darf nicht 36 Ausführungen ergeben, (c) ein Echo aus der Historie bleibt draußen. Vorher blieb bei (a) nur der erste. | Pro Signatur sind **bis zu zwei** Aufrufe pro Turn erlaubt: ein Wiederholungsversuch ist plausibel, die Schleife wird gebrochen. (c) bleibt über den Historienabgleich erhalten. Der bestehende Test, der 36 identische Calls auf 1 reduzierte, wurde bewusst auf 2 angehoben. |
| **T-05** | Ein Call im Reasoning-Kanal lag doppelt vor — einmal aus den Deltas, einmal aus der Auswertung im `finalize`. Im Stream kamen zwei Chunks mit verschiedenen IDs an. | Die Überlappung wird entfernt statt die Liste nachträglich dedupliziert: bereits erfasste Signaturen (aus den Deltas **und** aus dem Parser) werden bei der zweiten Auswertung übersprungen. |

**Zwischenerkenntnis beim Umsetzen:** Der Filter für T-05 las zunächst die
leere Liste, weil `self._deferred_reasoning_calls` zwei Zeilen vorher
geleert wird. Ein solcher Fehler ist beim Lesen des Codes nicht sichtbar —
erst der Messwert (2 IDs statt 1) hat ihn gezeigt. Das ist der Grund,
warum hier jede Änderung gegen eine Messung geprüft wird und nicht gegen
eine Vermutung.

### F-5n T-07 und D-06: Reihenfolge und Zeichentreue im Stream (2026-09-25)

| Befund | Fehlverhalten (gemessen) | Umsetzung |
|---|---|---|
| **T-07** | Die Präambel-Erkennung kannte **nur deutsche** Muster (`ich`, `zuerst`, `ich lese` …). Die live vorgekommenen englischen Varianten („I will read the file", „Let me check the file") liefen unerkannt durch und standen als Antwort vor dem Aufruf. | Muster um die englischen Formen erweitert (`i will`, `i'll now`, `let me`, `i'm going to`, `now i will`). |
| **D-06** | Zwei Fehler in derselben Kette: (a) es wurde **nur die Präambel** zurückgehalten, der Folgetext streamte sofort — der Client bekam `mache das.` und erst später `Ich` (gemessen: `Ich mache das.` bei Chunk-Größe 3 als `' mache das.'`); (b) ein **reiner Whitespace**-Delta wurde ebenfalls zurückgehalten. Da der zurückgehaltene Text erst in der *finalen* Antwort wieder auftaucht, fehlte er im Stream: `Hier ist die Anleitung.` kam als `Hier ist dieAnleitung.` an. | (a) Solange eine Präambel offen ist, wird der **gesamte** sichtbare Text gepuffert — erst ein Tool-Call (dann ist die Präambel gegenstand) oder das Turn-Ende (dann wird der gepufferte Text in Reihenfolge ausgegeben) löst das auf. (b) Whitespace-Deltas werden **nie** zurückgehalten: sie können weder Protokollfragment noch Fence-Öffnung sein. |

Beide Fehler waren **stream-only** — die finale Antwort war in beiden Fällen
korrekt. Ein Test, der nur `build_response()` prüft, sieht sie nicht; genau
das war der blinde Fleck, den die unabhängige Prüfrunde aufgedeckt hat.

### F-5o T-11, P-12/P-14, P-13 (2026-09-25)

| Befund | Fehlverhalten (gemessen) | Umsetzung |
|---|---|---|
| **T-11** | `tool_calls` kommt auch als **Liste** vor; der Dict-Zweig ignorierte sie — der native Call kam nie an, der Agent blieb stehen. | Die Listenform wird ausgewertet — mit **denselben Wächtern** wie der Dict-Zweig. Das war nicht selbstverständlich: mein erster Entwurf hängte die Einträge direkt an `_server_side_tool_calls` und umging damit Blockliste, Allowlist und das Policy-Mapping. Selbst gemessen (`open_url` ausführbar, `read` ohne deklarierte Tools ausführbar) und korrigiert. |
| **P-14** | Der Holdback war **außerhalb** des DSML-Pfades unbegrenzt: ein nie geschlossenes `{"name":"read","arguments":{"filePath":"` ließ den Puffer unbegrenzt wachsen (12.000 Zeichen nach 300 Stücken). Ein Speicherpfad bei abgeschnittenem Upstream-Strom. | Obergrenze gilt jetzt für den gesamten Holdback. Wird sie erreicht, wird der Rest als sichtbarer Text freigegeben — besser ein Fragment als unbegrenzter Speicher. |
| **P-12** | Die Strukturerkennung lief für **jedes** Chunk über den gesamten Puffer. 360 k Zeichen kosteten **286 Sekunden** — ein abgeschnittener Strom pinnt einen Kern. | Der Scan ist inkrementell (nur das neue Fragment), das Zwischenergebnis wird pro Stapelzustand gecacht, und die Auswertung ist auf die ersten 64 Stapel-Einträge begrenzt (der Holdback beginnt beim **äußersten** call-artigen Öffner). **Ehrlich offen:** der Extremfall ist damit von 286 s auf ~200 s gefallen, nicht auf Sekunden. Eine echte Lösung braucht einen ereignisbasierten Puffer statt Textanhängung — ein Umbau. Was bleibt, ist durch die Obergrenze aus P-14 gedeckelt. |
| **P-13** | Der `[]`-Terminator nach einem Aufruf kommt als eigenes Fragment und wurde bei zeichenweiser Zustellung **als sichtbarer Text ausgegeben** — der Client sah am Ende jeder Tool-Runde ein `[]` (gemessen bei Chunk-Größen 1–3, sowohl im Rohparser als auch im Accumulator, also beim Client). | Der Parser hält den Terminator nach einem ausgelieferten Call zurück. Das ist die seit dem Audit dokumentierte „kosmetische" Restzeile — sie war keine Kosmetik, sie landete im sichtbaren Text. |

### F-5p Adapter-Gruppe A-02, A-07, A-10, A-13, A-14 (2026-09-25)

| Befund | Fehlverhalten (gemessen) | Umsetzung |
|---|---|---|
| **A-13** | Nach der ersten Kanonisierung blieben Umgehungen offen: `openurl`, `open_url2`, `CodeInterpreter`, `websearch` und Namen mit **Nullbreitenzeichen** (`OPEN_URL\u200b`) passierten die native Sperre. | Zweiter kanonischer Schlüssel **ohne** Trennzeichen (`open_url` ≡ `openurl` ≡ `openUrl`), Nullbreiten-/Steuerzeichen werden entfernt, Ziffern-Suffixe gelten als Version (`open_url2` ≡ `open_url`). Gegenprobe: `read2`, `sha256`, `query2`, `step3` bleiben benutzbar — echte Tools mit Ziffern werden nicht getroffen. |
| **A-14** | Der Serializer erfand `{"raw": …}`; die **Reparaturtherk selbst** (`_unusable_args`, `value`) hatte dasselbe Problem — sie sehen wie Parameter aus. Und ein nicht reparierbares `_raw` blieb im Argument-Objekt stehen. | Herken tragen jetzt ein `$`-Präfix (`$invalid_arguments`), das im JSON-Schema für Meta-Keys reserviert ist und nicht als Werkzeug-Fähigkeit gelesen werden kann. Ein nicht reparierbares `_raw` verwirft den Aufruf (zählt über den Unusable-Pfad als fehlerhaft). |
| **A-10** | Anthropics serverseitige Native-Tools (`computer_20250124`, `text_editor_20250124`, `code_execution_…`) tragen kein `input_schema` und wurden zu gewöhnlichen Client-Funktionen mit leerem Schema: das Modell „ruft" sie auf, der Client kennt sie nicht, der Lauf scheitert kryptisch. | Sie werden mit klarer Meldung abgelehnt — wie die nicht unterstützten Responses-Typen (A-10 dort bereits so). |
| **A-07** | `previous_response_id` **ohne** Tool-Output verschluckte den Verlauf: der Client glaubte weiterzukonversationieren, das Modell bekam einen kontextlosen Turn (die erste Frage war im Prompt der zweiten nicht mehr enthalten). | Gespeichert wird jetzt der **sichtbare Verlauf** (vorige Eingabe + Antwortnachricht), nicht nur der Aufruf-Verlauf. Bei Textfortsetzung wird er vorangestellt; `function_call_output`-Fortsetzungen bleiben unverändert. |
| **A-02** | Der Adapter modelliert `thinking` und `redacted_thinking` korrekt — aber `extract_text_content` kannte nur `text`, `image_url` und `file`. Die Denkkette verschwand **vor dem Modell**: es bekam seinen eigenen Gedankengang nie zurück und musste alles neu herleiten. | Beide Blocktypen werden in die Historie übernommen. |

### F-5q C- und S-Gruppe: S-02, S-10, S-15-Teil, S-02-DNS, C-15, C-16, C-18, C-20 (2026-09-25)

| Befund | Befund-Status nach Nachprüfung | Umsetzung |
|---|---|---|
| **S-02** | **Tatsächlich offen.** `CORS_ALLOW_ORIGIN=*` und leere `SERVER_API_KEYS` — jede Website im Browser konnte den Loopback-Dienst unter `http://127.0.0.1:8001` ansprechen. Ein CORS-Verbot allein schließt das **nicht**: beim DNS-Rebinding ist die Anfrage aus Browsersicht same-origin, es findet gar kein Preflight statt. | Host-Header-Prüfung (`_host_header_is_allowed`): bei Loopback-Bindung muss der Host-Anteil `127.0.0.1`/`localhost`/`::1` sein. Gemessen: `evil.example.com`/`attacker.test`/`localhost.evil.com` → **403**; `127.0.0.1:8001`/`localhost:8001`/`[::1]:8001` → **200**. LAN-Bindings bleiben unverändert (dort greift die API-Key-Pflicht). |
| **S-10** | **Tatsächlich offen.** Ein blockierter Tool-Call *neben* gültigen Calls erzeugte **gar kein Signal**. Die Negativmeldung griff nur, wenn sonst nichts zurückkam — der Client读完 den Turn als vollständig und beendet den Tool-Loop. | Die Notice wird in beiden Pfaden (Stream + Non-Stream) auch im gemischten Turn ausgegeben, **ohne** die gültigen Calls zu verlieren (C-11 bleibt behoben). Gegenprobe ergänzt: ein Turn ganz ohne blockierten Versuch erzeugt keine Notice. |
| **C-15** | **Tatsächlich offen.** `delete_conversation` lief über `_call_with_account_failover` — bei mehreren Accounts konnte ein *anderes* Konto gewählt werden; dann wurde die falsche Conversation gelöscht und die eigentliche blieb serverseitig liegen. | `created_conversations` ist jetzt `dict[conversation_id → Erzeugerkonto]`; die Löschung läuft gezielt über dieses Konto, ohne Failover. |
| **C-16** | **Tatsächlich offen.** Die SSE-Verbindung wurde nur von den Aufrufern geschlossen. Bricht einer den Generator mit `return` ab, blieb der Socket offen. | `_iter_sse_events` gibt die Verbindung in einem `finally` selbst frei. Live: nach mehreren Läufen 4 FDs / 2 Sockets, keine Akkumulation. |
| **C-18** | **Teilweise.** `max_tokens` wird erzwungen (Ausgabebudget, `length`, abgeschnittene Calls verworfen). `temperature`/`top_p`/`seed` wurden **still** verworfen — die GLM-Chat-API hat keine Sampling-Parameter, der Client glaubt aber, seine Einstellung sei aktiv. | Explizit protokolliert. Bewusst **kein** harter Fehler: OpenAI-Clients senden `temperature` standardmäßig, eine Ablehnung würde jeden normalen Aufruf brechen. |
| **C-20** | **Bereits behoben.** Fehler-Body ist begrenzt (`ERROR_BODY_MAX_BYTES`), Dekompression ebenfalls begrenzt (Gzip-Bomb), Logging mit `redact_sensitive_data`, Client-Nachrichten generisch („Upstream service error."). | Keine Änderung nötig. |
| **C-11/C-12/C-13** | **Bereits behoben bzw. nicht reproduzierbar.** Gültige Calls neben blockierten werden ausgeliefert; Follow-up-Retries verwenden das Follow-up-Payload; zwei bewusst identische Calls werden beide geliefert. | Keine Änderung nötig. |

### F-5r S-04, S-12, S-13, S-15, D-11, D-12, D-13 (2026-09-25)

| Befund | Status nach Nachprüfung | Umsetzung |
|---|---|---|
| **S-12** | **Tatsächlich offen.** `tool_choice: none` blendete nur die Tool-Schemata aus dem Prompt — ein trotzdem erzeugter Call wurde regulär ausgeliefert. Der Client, der Tools ausdrücklich verboten hatte, bekam trotzdem einen strukturierten Tool-Call (das inverse Routing-Problem zu `required`). | Der Call wird in **beiden** Pfaden verweigert, als `[tool_choice_violation]` sichtbar gemacht und **nicht ausgeführt**; `finish_reason=error`. Gegenprobe: `none` erlaubt weiterhin normale Textantworten. |
| **S-15** | **Tatsächlich offen.** Ungültige Werte fielen zwar mit Warnung auf sichere Defaults zurück, aber **Tippfehler wurden völlig lautlos verworfen**: `CORS_ALLOW_ORIGINS` → `*` (die genaue Umkehrung der beabsichtigten Absicherung), `SERVER_API_KEY` → keine Auth, `GLM_MAX_CONCURRANCY` → 3. | `_warn_unknown_config_keys()` meldet unbekannte Keys mit geringer Edit-Distanz zum bekannten Namen; Sicherheits-Keys als `ERROR`. Bewusst konservativ: `FOO_BAR` bleibt still, sonst wäre jeder Startup verrauscht. |
| **S-13** | **Tatsächlich offen.** `.env` war ein **relativer** Pfad. Ein Direktstart aus anderem Verzeichnis lud eine falsche Config oder legte ungefragt eine `.env` dort an. | `_resolve_env_file()`: explizite absolute/Teilpfade bleiben unverändert, ein reiner Dateiname wird im CWD, dann neben dem Paket und der Repo-Wurzel gesucht. Ohne Betriebsdatei läuft der Dienst ohnehin auf dem Code-Default 8001. |
| **D-11** | **Tatsächlich offen (zweite Hälfte).** Port-Drift war nicht mehr vorhanden (Code und Beispiel: 8001). Aber `GLM2API_LOG_DIR`/`_MAX_BYTES`/`_BACKUP_COUNT` wurden direkt aus `os.environ` gelesen — `load_config()` exportiert die `.env` **nicht** in die Umgebung, ein dort gesetzter Log-Pfad war also still unwirksam. | Die drei Werte laufen über den normalen Config-Weg und werden `setup_logging()` als Parameter übergeben. |
| **D-12** | **Teilweise.** Build-Deps waren bereits exakt gepinnt, die Dev-Dep nicht (`pytest>=8` bei Lock 9.1.1). | `pytest==9.1.1`. **Bewusst offen:** eine erzwungene Coverage-Schwelle bräuchte `pytest-cov` und damit eine Fremdabhängigkeit — das Projekt ist stdlib-only. Das ist eine bewusste Entscheidung, kein Versehen. |
| **D-13** | **Bereits behoben.** Der Autouse-Fixture in `tests/conftest.py` sichert `os.environ` und die `GLM*`-Keys. Empirisch gegengeprüft: jede Testdatei einzeln, Standard- und umgekehrte Reihenfolge → 393 grün, keine Reihenfolgeabhängigkeit. | Keine Änderung nötig. |
| **S-04** | **Bereits behoben.** `logging_utils` erzwingt `0o700` fürs Verzeichnis und `0o600` für Logdateien inkl. Rotation; auf der Platte verifiziert. | Keine Änderung nötig. |

### F-5s C-17, S-07 (2026-09-25)

| Befund | Status | Umsetzung |
|---|---|---|
| **S-07** | **Tatsächlich offen.** Die Eingabevalidierung war pro Endpoint ad hoc. Live gemessen: `max_tokens: "viel"` → **200** (still verworfen, die globale Grenze galt — der Client glaubte, sein Limit sei aktiv), `tools: "keine"` → 200, `messages` ohne `role` → 200. | `validate_openai_request()` an der Request-Grenze: Integer-/Number-/Listenfelder und Nachrichtenobjekte werden geprüft. `null` bleibt gültig (heißt „nicht gesetzt"). Live nach Restart: ungültige Typen → **400**, gültige Requests unverändert **200**. |
| **C-17** | **Teilweise offen.** `Authorization` und Query-Secrets waren redigiert — aber `X-Sign` (die HMAC-Signatur der Anfrage, mit dem geheimen Schlüssel gebildet) und `set-cookie` (Upstream-Session) lagen im Klartext im Debug-Log. | Beide in die Redaktionsliste aufgenommen. `x-nonce`/`X-Timestamp` bleiben bewichtlich lesbar (keine Zugangsdaten). Der Inhalt bleibt unverändert 1:1 — das ist die bewusste Debug-Entscheidung. |

### F-5t S-02 vollständig (2026-09-25)

Der DNS-Rebinding-Guard aus F-5q schloss nur **eine** Hälfte des Befunds.
Die andere Hälfte blieb offen und ist jetzt geschlossen:

| Angriffspfad | Vorher | Jetzt (live gemessen) |
|---|---|---|
| DNS-Rebinding (`Host: evil.example`) | 200 | **403** |
| Direkter Cross-Origin-Read (`Origin: https://evil.example`) | `Access-Control-Allow-Origin: *` → die Seite liest die Antwort | **kein ACAO-Header** → der Browser blockt |

Der Rebinding-Guard allein hätte nicht gereicht: beim Rebinding ist die
Anfrage aus Browsersicht same-origin, es findet kein Preflight statt —
und beim *normalen* Cross-Origin-Zugriff ist der `Host`-header
`127.0.0.1`, der Guard greift also nicht, sondern erst der Wildcard-CORS.

- `CORS_ALLOW_ORIGIN` hat jetzt den Default **leer**. Der Dienst ist eine
  API für CLI-Clients; Browserzugriff war kein Feature, sondern das Loch.
- `*` bleibt ausdrücklich setzbar (Komfort) und bleibt auf
  Nicht-Loopback-Bindings verboten.
- `.env` und `.env.example` auf leer umgestellt; ein Test verhindert, dass
  die Beispieldatei das Loch wieder aufmacht.
- Live gegengeprüft: `health`/`models`/`chat` weiterhin 200 bzw. korrekte
  Antwort — kein Client bricht.

### F-5u Rest der S-Gruppe: S-01, S-03, S-05, S-09, S-11, S-14, S-16, S-17 (2026-09-25)

Die vollständige S-Gruppe wurde gegen den Rohbericht nachgeprüft, nicht
gegen die Doku.

| Befund | Status | Beleg / Umsetzung |
|---|---|---|
| **S-05** | **Tatsächlich offen.** `TimeoutError` stand in **beiden** Fehlertupeln (`_DOWNSTREAM_DISCONNECTED` *und* `_UPSTREAM_TRANSPORT_ERRORS`), und der Downstream-Handler stand zuerst. Ein Upstream-Timeout wurde als „Client disconnected early" geloggt und der Client bekam **gar keine** Antwort. | Die Klassen sind jetzt disjunkt: ein Timeout ist nie ein sauberer Client-Abbruch — der tritt als `BrokenPipeError`/`ConnectionResetError` auf. Upstream-Timeouts enden als 504 mit benanntem Grund. |
| **S-01** | Bereits behoben. | Body-Limit 32 MiB (max 128 MiB), Request-Zeile 8 KiB (max 64 KiB), Header/Verbindungen begrenzt. |
| **S-03** | Bereits behoben. | SSE-Queue `maxsize=16`, `reader_cancelled`-Event plus `stream_iter.close()` im `finally`, Daemon-Thread — die Reader-Pipeline ist abbrechbar. |
| **S-09** | Bereits behoben. | `_write_error_json` und `send_error` setzen `close_connection`; live geprüft: POST auf unbekannten Pfad → 404, Folge-Request 200, kein Desync; Keep-alive-Pipeline nutzt 1 Verbindung. |
| **S-11** | Bereits behoben. | Empirisch: `previous_response_id` + `function_call_output` erhält Tools, `tool_choice`, den vorigen Call und das Ergebnis in der Reihenfolge `function_call → function_call_output`. |
| **S-14** | Bereits behoben. | Alle 23 Budget-Zuweisungen geprüft (ungültig / out of range / negativ): jeder Wert wird begrenzt oder mit `ConfigError` abgelehnt. `0` ist bei den Retry-/Follow-up-Budgets die deklarierte Mindestgrenze — „keine Retries" ist eine gültige Wahl. |
| **S-16** | Bereits behoben. | `GLM_BASE_URL` darf `http` nur für Loopback-Hosts; eingebettete Credentials werden abgelehnt. Deployment nutzt `https://chatglm.cn`. |
| **S-17** | Bereits behoben. | `sys_version = ""` — die Python-Laufzeitversion wird nicht ausgeliefert. |

### F-5v D-01 (echter Bug) und D-04/D-05/D-08/D-10 (Testlücken) (2026-09-25)

**D-01 war kein Testfehler, sondern ein echter Bug im Code.** Der Test
behauptete nur `assert 'tool' in combined` — und `tool` stand bereits im
Protokoll des erlaubten Aufrufs, die Behauptung konnte nicht fehlschlagen.
Der Test wurde durch sein echtes Symptom ersetzt, und das schlug fehl:

| Chunk-Größe | Final-`content` vorher | `finish_reason` |
|---|---|---|
| 3, 5, 7, 13, 29 | `'{"tool'` | `stop` |
| 1 | `'{'` | `stop` |

Der Streaming-Pfad hielt den Präfix im Holdback korrekt zurück — der
**Final-Pfad** nicht. Der Client sah im Stream nichts und in der
Abschlussantwort rohes Protokoll, gemeldet als **Erfolg**.

- `strip_unterminated_tool_prefix()`: entfernt am Textende einen
  angebrochenen Protokoll-Präfix, konservativ in drei Schritten — nur ab
  der letzten offenen Klammer, nur wenn der Rest ein echtes Protokoll-
  Präfix ist (`{"` + Anfang eines Protokollfelds), nur wenn die Klammer
  **ungeschlossen** ist. Prosa, die mit `{` endet, bleibt stehen; ein
  geschlossener Aufruf wird nie angefasst.
- Der finale Pfad wendet dieselbe Entscheidung an wie der Holdback, sonst
  sind die beiden Pfade nicht gleichwertig. `truncated_turn` wird gesetzt
  → `finish_reason=error`.
- Gemessen über 9 Chunk-Größen: 0 Leaks, Stream und Final deckungsgleich.
- Der Preis ist derselbe wie im Holdback: eine Zeile, die mit `{` endet,
  verliert ihre Klammer. Das ist ein bewusster Tausch — ein Protokoll-
  Fragment als Antwort zu liefern ist der schlimmere Fehler.

| Befund | Status |
|---|---|
| **D-04** | Symptom geprüft über 8 Chunk-Größen mit Splitten *mitten* in `U`/`Us` (die alten Tests lieferten den Marker als kompletten Chunk): 0 Marker-Treffer. Als Test festgeschrieben. |
| **D-05** | Gemischte Turns (gültiger Call neben blockiertem) über 5 Chunk-Größen: gültiger Call kommt in **allen** an, blockierter wird verweigert. Als Test festgeschrieben. |
| **D-08** | Der Vertrag hält: blockierter Versuch ohne gültige Calls → sichtbarer Hinweis **und** `finish_reason=error`, Stream wie Non-Stream. Als Test festgeschrieben. |
| **D-09** | Der Verifier führt die echte Symptom-Suite aus. Kontrolliert bewiesen: mit absichtlich abgeschaltetem P-07 meldet er `exit 1` mit `FAILED` in `test_leak_sweep.py`, nach dem Zurücksetzen `exit 0`. |
| **D-10** | Neuer Selbsttest `infra/scripts/verify-verifier-selftest.sh`: baut die Regression ein, erwartet `exit != 0` **mit** `FAILED` in der Symptom-Suite, stellt wieder her und erwartet `exit 0`. Läuft durch — der Verifier sagt also nicht immer grün. |

### F-5w T-20: der superlineare Delta-Aufbau (2026-09-25)

Der letzte offene Performance-Befund. `_render_full_output()` hatte bereits
einen Dirty-Cache, **aber** `_compute_deltas()` lief weiterhin pro Event
über **alle** bekannten Parts — bei 1000 Parts x 1000 Events also rund
1.000.000 Dict-Zugriffe.

| Parts | vorher | nachher | Faktor je Verdopplung (vorher → nachher) |
|---|---|---|---|
| 500 | 0,48 s | 0,18 s | – |
| 1000 | 3,51 s | **0,33 s** | 7,4x → **1,9x** |
| 2000 | 20,69 s | **0,89 s** | 5,9x → 2,7x |
| 4000 | – | 3,14 s | – |

Ursache: `_render_full_output()` **leert** das Dirty-Set, bevor
`_compute_deltas()` iteriert. Es gab also nichts, was man dort iterieren
konnte. Jetzt wird der Satz der tatsächlich neu aufbereiteten Parts vor
dem Leeren als Schnappschuss behalten (`_last_rendered_dirty`), nach
Part-Rang sortiert (die Deltas entstehen sonst in anderer Reihenfolge als
die Parts) und nach der Berechnung wieder verworfen.

- **Ausgabe byte-identisch**: sha256 des 500-Part-Ergebnisses vor und nach
  der Änderung: `d55fc1f51fc865b3` — beide Male. Es geht nichts verloren.
- Als Test festgeschrieben: die Zeit darf bei 4x Parts nicht um mehr als
  Faktor 8 wachsen (quadratisch wäre 16x), und die Fortsetzungs-Parität
  („Die Datei" / „ ist im " / „Repository gefunden" bleibt ein Satz)
  wird gegen die Trenner-Regel geprüft.

### F-5x P-12 und `trunc-bare-after-prose` (2026-09-25)

**P-12** war der letzte offene Performance-Befund. Die Audit-Messung
(Vollscan des Puffers bei jedem `consume`) ist nicht mehr reproduzierbar:

| `command`-Argument | Audit (vorher) | jetzt | Faktor je Verdopplung (vorher → jetzt) |
|---|---|---|---|
| 500 | 0,057 s | 0,002 s | – |
| 1 000 | 0,147 s | 0,004 s | 2,6x → **2,0x** |
| 2 000 | 0,459 s | 0,007 s | 3,1x → 1,8x |
| 4 000 | 2,241 s | 0,014 s | 4,9x → 2,0x |
| 8 000 | 7,608 s | **0,027 s** | 3,4x → 1,9x |

**280x schneller bei n=8000**, und die Skalierung ist linear statt
quadratisch. Nach oben geprüft, weil lineares Verhalten dort meist
kippt: 16k / 32k / 64k / 128k Zeichen → 0,060 / 0,122 / 0,253 / 0,494 s,
also **Faktor 2,0 je Verdopplung** durchgehend. Der Vertrag ist als Test
festgeschrieben (8x Zeichen dürfen nicht 64x Zeit kosten).

**`trunc-bare-after-prose`** war mit 4 von 12 Chunk-Größen als *bewusst
offen* dokumentiert — die Entscheidung hing an der ungeklärten Frage, ob
Stream und Non-Stream bei abgeschnittenen Calls dasselbe tun müssen. Mit
dem D-01-Fix ist der Punkt **0 von 12** und die Frage beantwortet:

- Abgeschnittene **Argumente** (mitten im String, mitten im Pfad, ohne
  Namen) → Aufruf **nicht** ausgeliefert, `finish_reason=error`, keine
  Roh-Protokollreste, die Prosa bleibt sichtbar.
- Fehlt nur der `[]`-Terminator, sind die Argument-Daten vollständig —
  das ist kein beschnittener Aufruf, sondern ein vollständiger ohne
  Markierung. Er wird zu Recht ausgeliefert; zu aggressives Abschneiden
  würde hier echte Aufrufe zerstören. Als Gegenprobe festgeschrieben.

### F-5y T-20 vollständig (2026-09-25) — die zweite Hälfte

F-5w hat nur die *Delta-Berechnung* linearisiert. Ein neu geschriebener
Test über eine größere Strecke (8x Parts statt 4x) deckte die **restliche**
Superlinearität auf: der Skalierungsnachweis war zu kurz angesetzt.

Drei weitere Ursachen, jede einzeln gemessen:

| Ursache | Messung | Fix |
|---|---|---|
| `_render_full_output()` füllte `text_parts` bei **jedem** Event neu aus allen bekannten Parts (36 Mio Dict-Gets bei 6 000 Parts, 18 s) | tottime 11,5 s von 18,8 s | persistente Part-Listen; angehängt wird nur, was neu ist. Nur wenn eine Part **erneut** gesendet wird (Epoch-Wechsel), wird einmal komplett neu gebaut — das ist der seltene Fall. |
| `is_new = logic_id not in self._known_logic_ids_for_text` — linearer Scan über eine **Liste** | 110 µs pro Event bei 20k Parts | Sets daneben: O(1)-Mitgliedschaft, die Listen bleiben für die Reihenfolge. |
| Der Aufbauteil baute den kompletten Text auch dann, wenn das Ausgabebudget längst erschöpft war (944k Zeichen, davon 880k direkt wieder weggeschnitten). Die Zusammenführung ist String-Verkettung → quadratisch in der Gesamtlänge. | 16k Parts: 43,8 s | Sinkt die Sammellänge unter das Restbudget, wird nichts mehr angehängt. Der Vertrag bleibt: was hinter der Grenze liegt, wird nie ausgeliefert, `finish_reason=length`. |

Ergebnis (mit Ausgabegrenze 16384, der reale Fall):

| Parts | F-5w-Stand | jetzt | Faktor je Verdopplung |
|---|---|---|---|
| 2 000 | 0,94 s | 0,15 s | – |
| 16 000 | 43,8 s | **0,59 s** | 46x → **3,9x** |
| 64 000 | – | **1,97 s** | 3,3x |

Ohne Ausgabegrenze bleibt die Verkettung sichtbar (2 000 → 0,38 s,
8 000 → 2,58 s) — das ist ehrlich dokumentiert statt wegoptimiert, denn
ohne Grenze gibt es keine Frühabbrüche, an denen man aufhören könnte.

**Ausgabe byte-identisch**: sha256 des 500-Part-Ergebnisses ist vor wie
nach allen drei Fixes `d55fc1f51fc865b3` (29 497 Zeichen).

### F-5z Abschlussregister: alle 107 Befunde, geprüfter Stand (2026-09-25)

Geprüft wurde gegen `glm2api-revision-anhang/` (die Rohbefunde), nicht
gegen dieses Register. Jede Zeile unten ist entweder gemessen (Wert
angegeben) oder als bewusste Entscheidung begründet.

**In dieser Runde am Anhang entdeckt und behoben** (die unabhängige
Zweitrunde hatte diese offen gelassen):

| Befund | Art des Fehlers |
|---|---|
| **D-01** | Echter Bug: rohes Tool-Protokoll im Final-Pfad, gemeldet als `stop` |
| **A-02, A-07, A-10, A-13, A-14** | Adapter: Denkkette verloren, Verlauf verschluckt, Native-Tools als Client-Funktionen, 5 Blocklisten-Umgehungen, erfundene Parameter |
| **S-02** | Sicherheit: DNS-Rebinding **und** Cross-Origin-Read über CORS-Wildcard |
| **S-05, S-07, S-10, S-12, S-13, S-15** | Upstream-Timeout als Client-Abbruch, stille Semantikänderungen, fehlende Notice, `tool_choice: none` ignoriert, Pfaddrift, Tippfehler lautlos |
| **C-15, C-16, C-17, C-18** | Cleanup am falschen Konto, undichteter SSE-Socket, Signatur/Cookie im Klartext, stumm verworfene Sampling-Parameter |
| **D-10, D-11, D-12** | Verifier ohne Selbsttest, Log-Pfade aus `.env` wirkungslos, pytest nicht gepinnt |
| **T-20, P-12** | Performance: 64k Parts 28,9 s → 1,97 s; Parser 280x schneller, linear statt quadratisch |
| `trunc-bare-after-prose` | 4/12 → **0/12** |

**Bewusst offen, mit Begründung:**

| Punkt | Warum |
|---|---|
| **D-12** Coverage-Schwelle | Eine erzwungene Abdeckung bräuchte `pytest-cov` und damit eine Fremdabhängigkeit. Das Projekt ist stdlib-only. Entscheidung, kein Versehen. |
| **D-12** Quadratische Verkettung ohne Ausgabegrenze | 2 000 Parts 0,38 s → 8 000 Parts 2,58 s. Ohne `max_tokens` gibt es keine Frühabbrüche, an denen man aufhören könnte. Mit der Grenze (der reale Fall) ist es linear. |
| **Debug-Logging 1:1** | Nutzerentscheidung. Nur Zugangsdaten werden redigiert (Authorization, `X-Sign`, `set-cookie`, Query-Secrets). |

**Geprüft und bereits erfüllt** (A-01/03/04/05/06/08/09/11/12/15–19,
C-01–C-14, P-01–P-11/P-13/P-14, S-01/03/04/06/08/09/11/14/16/17,
T-01–T-19/T-21–T-24, D-02–D-09): gegen den Rohbericht nachgemessen,
nicht aus der Doku übernommen. Beispiele der Prüfung:

- **T-02**: ohne deklarierte Tools verschwinden historische Calls samt
  Ergebnis aus dem Prompt; mit Deklaration bleiben beide. `None` ist
  keine Wildcard.
- **T-14**: eine Multi-Call-Runde wird **als Ganzes** komprimiert oder
  gar nicht; Aufruf + alle Ergebnisse bleiben paarweise zusammen.
- **T-12**: ein Call ohne Pflichtargument wird nicht ausgeliefert
  (`finish_reason=error`).
- **T-08**: Fenced-Calls, Stream und Non-Stream, identisches Ergebnis
  und identischer `finish_reason`.
- **S-16**: `GLM_BASE_URL` nur mit `https` außer gegen Loopback.
- **S-17**: `sys_version = ""` — keine Python-Laufzeitversion im Header.

**Selbsttest des Verifiers** (`infra/scripts/verify-verifier-selftest.sh`):
baut eine kontrollierte Regression ein, erwartet `exit != 0` **mit**
`FAILED` in der Symptom-Suite, stellt wieder her und erwartet `exit 0`.
Ohne diesen Test ist „der Verifier sagt immer grün" nicht unterscheidbar
von „der Verifier prüft wirklich".

### F-5w1 REGRESSION: die Ausgabegrenze halbierte das Budget (2026-09-25)

**Das ist meine Regression aus F-5y und sie hat einen echten
Agentenlauf unbrauchbar gemacht.** Sie fiel auf, weil der Nutzer eine
wiederaufgenommene opencode-session (`ses_f25931fd6ffezO0Igb6dxI36RU`,
`glm-5.3`, `reasoning_effort: max`) mit „völlig kaputt" meldete.

**Symptom im glm2api-Log:** jeder Turn endete mit
`finish_reason: "length"`, obwohl das Modell noch lange nicht fertig war
(22 433 Prompt-Tokens, Antwort bei 16 629 Zeichen abgeschnitten).

**Ursache:** der Performance-Guard aus F-5y verglich den aufgebauten
Text gegen `_output_budget_remaining()` — also gegen
`max_output_tokens*4 - _output_chars`, wobei `_output_chars` den bereits
gesendeten Text **und das Reasoning** bereits abgezogen hatte. Der
aufgebaute Text wurde also ein zweites Mal gegen dasselbe Budget
geprüft: das Budget halbierte sich. Bei `reasoning_effort: max` fraess
das Reasoning `_output_chars` zusätzlich, wodurch fast nichts übrig
blieb.

Gemessen: 16 629 von 32 768 Zeichen — **50,7 %**.

**Korrekt:** der Guard existiert nur, um den quadratischen Aufbau
abzubrechen, und darf nie Text entfernen, den der Stream-Pfad sonst
liefern würde. Er vergleicht jetzt gegen das **volle** Budget. Text
allein kann nie mehr Zeichen liefern als das ganze Budget — der Guard
kann also nichts verlieren. Die Ausgabegrenze selbst setzt weiter der
Stream-Pfad.

| `max_tokens` | vorher | jetzt |
|---|---|---|
| 2 048 | 4 096 Zeichen (50 %) | 8 192 (100 %) |
| 8 192 | 16 629 Zeichen (50,7 %) | 32 768 (100 %) |

Als Test festgeschrieben: der gelieferte Text muss ≥ 99 % des Budgets
sein, **und** `finish_reason` muss weiterhin `length` werden — sonst
wäre die Grenze durch den Fix still verschwunden.

**Lehre für die eigene Prüfung:** alle 487 Tests waren grün, beide
Leak-Sweeps 0, die Live-Smokes zeigten kurze Antworten ohne Fehler. Der
Fehler fiel nur auf, weil ein *Agentenlauf mit großem Reasoning-Budget*
als Zeuge da war. Ein Systemverhalten muss mit dem realen Volumen
getestet werden, nicht nur mit Rauchtests.

### F-5w2 REGRESSION 2: das Reasoning fraess das ganze Budget (2026-09-25)

Zweite echte Regression, wieder an einer echten opencode-Session
gemeldet. Diese ist **nicht** von mir eingebaut worden — sie ist im
selben Zug wie F-5y entstanden bzw. von der Audit-Runde offen gelassen
worden.

**Symptom im glm2api-Log** (`ses_f25816657ffepyG6tnzohDJhoh`,
`reasoning_effort: max`, `max_tokens: 8192`):

```
Response finalize status=finish text_len=1262 reasoning_len=61820 tool_calls=0
Streaming request completed model=glm-5.3 failed=False
```

Der Client bekam: **1 768 Zeichen Reasoning, 0 Text, 0 Tool-Calls**,
`finish_reason: length`. Das Modell hatte also 61 820 Zeichen Denktext
erzeugt — das 1,9-fache des erlaubten Budgets von 32 768.

**Warum das den Agenten lahmlegt:** der Turn gilt als *erfolgreich
beendet* (`failed=False`), enthält aber nichts. Der Agent wartet auf eine
Antwort oder einen Tool-Aufruf, die nie kommen kann. Ein Turn mit
`length` und leerem Ergebnis ist kein „abgekürzt", sondern ein toter
Turn — der Auftrag ist schlicht unerfüllbar.

**Ursache:** Reasoning und Lieferkanal teilten sich ein Budget ohne
Obergrenze für das Reasoning. Im Stream-Guard stand wörtlich
`text_delta = ""`, sobald das Reasoning den Raum füllte — und weil
Tool-Calls aus dem Textkanal geparst werden, war mit dem Text auch der
Aufrufkanal tot.

**Fix:** `_REASONING_BUDGET_SHARE = 0.7`. Der Denkkanal darf höchstens
70 % des Budgets nehmen, 30 % bleiben für Text und Tool-Aufrufe
reserviert. Das Reasoning kann weiterhin der größere Teil sein — das
ist der normale Fall bei langen Denkprozessen.

**Und die Leerstelle, die F-5w1 geschaffen hatte, ist mit beseitigt:**
der Performance-Guard im Aufbau wird jetzt **nur** ausgelöst, wenn der
Stream ohnehin schon nichts mehr ausliefert (`output_limit_reached`).
Damit gibt es genau *eine* Stelle, die das Budget führt — der Stream.
Ein zweiter, unabhängiger Budget-Schneidepunkt im Aufbau hatte in F-5w1
50,7 % geliefert und mit der Quote-Variante 30,7 %.

Gemessen nach dem Fix:

| Eigenschaft | Wert |
|---|---|
| Reiner Text, `max_tokens=2048` / `8192` | 8 192 / 32 768 Zeichen — **100 %** |
| Deep-Thinking-Turn | Tool-Call kommt an (`finish_reason=tool_calls`) |
| 64 000 Parts | 2,5 s (unverändert linear) |

**Die Lehre ist die zweite in Folge:** eine Budget-Führung an zwei
Stellen ist eine Fehlerquelle. Die Aufgabengrenze gehört in *eine*
Komponente; alles andere darf sie nur noch **beobachten** (und
darf stoppen, wenn die beobachtete Komponente selbst gestoppt hat).

### F-5z AUTONOMIE: Der Agentenlauf muss zu Ende laufen (2026-09-25)

Das Ziel aus dem Nutzerauftrag war ausdrücklich: **eine Aufgabe soll
komplett autonom fertiggestellt werden — nicht mittendrin aufhören.**

Der T-Output doppelte die F-5w1/F-5w2-Fehler und war die eigentliche
Ursache: opencode forderte `max_tokens: 8192`, der Proxy erlaubte 16 384
— und `min(client, global)` ergab **8 192**. Ein Run mit
`reasoning_effort: max` braucht fürs Denken allein ~15 500 Token. Das
Kontingent war also zu klein für die Aufgabe, bevor überhaupt etwas
getan wurde.

| Größe | vorher | jetzt |
|---|---|---|
| opencode `limit.output` | 8 192 | **32 768** |
| Proxy-Standard `GLM_MAX_OUTPUT_TOKENS` | 16 384 | **32 768** |
| wirksames Kontingent | 8 192 | **32 768** |
| davon Denkkanal (70 %) | — | 22 937 Token |
| davon Lieferung (30 %) | 0 bei langem Denken | 9 830 Token |

Die Konfigurationsgrenze erlaubt bis 131 072 — 32 768 ist kein
Grenzfall, sondern der kleinste Wert, der einen ernsthaften
Arbeitsauftrag mit Deep-Thinking trägt.

**Live gegengeprüft** mit zwei agentenartigen Läufen (echtes Volumen,
`reasoning_effort: max`, Tools, Stream):
- Verzeichnisanalyse mit `ls`/`wc` → `finish_reason: tool_calls`, Aufruf `bash`, Antwort in 4,2 s
- Datei schreiben mit Planungsschritt → `finish_reason: tool_calls`, Aufruf `read`, **Argumente vollständig** (endet auf `}`)

Beide: kein Abbruch, kein leerer Turn, Tool-Aufrufe ausführbar.

**Was das nicht löst** (ehrlich benannt): die Garantie „läuft zu Ende"
gibt opencode, nicht der Proxy. Der Proxy kann nur sicherstellen, dass
ein Turn **nie leer** endet und ein Tool-Aufruf **nie halb** ankommt.
Ob der Agent danach weiterarbeitet, entscheidet opencode. Mit 32 768
statt 8 192 hat er dafür aber den Raum, den er für einen mehrstufigen
Auftrag braucht.

### F-5w3 Die Retry-Schleife bei gesperrten Werkzeugen (2026-09-26)

Der Nutzer meldete, dass der Agentenlauf am Ende hängen blieb. Gezielt
im glm2api-Log gesucht, nicht geraten:

```
22:32:06  Stream -> Antwort mit finish_reason: "error"
22:37:09  nächster Stream   <-- 5 MINUTEN SPÄTER
```

Die Fünf-Minuten-Lücke ist ein **Retry-Backoff**. Die Kausalkette:

1. Das Modell ruft `open` auf — ein **natives GLM-Werkzeug**, weshalb es
   überhaupt in der Sperrliste steht. `open` ist *nicht* in der
   Tool-Schema-Liste, die das Modell sieht (0 Treffer), und die
   Negativmeldung sagt bereits „Do not call them again" und listet die
   Alternativen. Das Modell ruft es trotzdem erneut auf.
2. Der Proxy lehnt ab und sendet `finish_reason: "error"`.
3. Der echte Client wertet das als **Stream-Fehler** und wiederholt den
   Turn mit exponentiellem Backoff.
4. Gleicher Prompt, gleiche Modell-Neigung → wieder `open` → wieder
   `error` → Endlosschleife. In 90 Sekunden kein einziger
   Werkzeugaufruf.

**Die Wurzel ist nicht das Modell, sondern unser Signal.** Ein
*gesperrter* Aufruf ist eine **vollständige Antwort**: „dieses Werkzeug
gibt es nicht, ich habe stattdessen X gemacht". Es fehlt dem Client
nichts, es gibt nichts zu wiederholen. `error` war hier schlicht das
falsche Signal.

**Die Korrektur und ihr Preis:**

| Fall | vorher | jetzt | Begründung |
|---|---|---|---|
| gesperrter / nicht deklarierter Aufruf | `error` | **`stop`** | vollständige Antwort; `error` löste die Schleife aus |
| erlaubter Aufruf ohne Pflichtargument (T-06) | `error` | `error` | dem Client fehlt etwas Brauchbares, Retry ist berechtigt |
| abgeschnittenes Protokoll | `error` | `error` | ebenso |
| `tool_choice=required` verletzt | `error` | `error` | Vertragsbruch, dem Client muss etwas Ausführbares fehlen |
| Terminalstatus fehlerhaft (T-13) | `error` | `error` | ebenso |

Der Preis ist ehrlich benannt: `stop` heißt, der Client akzeptiert den
Turn. Das ist vertretbar, **weil** der sichtbare Hinweis ausdrücklich sagt,
dass nichts ausgeführt wurde — die eigentliche Gefahr (der Agent behauptet,
er habe ein Ergebnis gesehen) bleibt ausgeschlossen.

**Der Fund war teurer als die eine Zeile.** Drei Stellen mussten getrennt
werden, weil sie den gesperrten Aufruf jeweils mit einem echten Fehler
verwechselten — jeweils an einer anderen Stelle im Ablauf:

1. `strip_unparseable_call_fragments()` zählte den **vollständigen, nur
   abgelehnten** Aufruf als abgeschnittenes Fragment.
2. Die T-06-Prüfung in `finalize()` stufte ihn als „nicht ausführbar"
   ein (fehlendes Pflichtargument).
3. Dasselbe in `build_response()` für den Non-Stream-Pfad.

Und an allen drei Stellen war die Klassifikation **nicht verfügbar**:
`blocked_tool_attempt_names` wird erst *später* aus dem Text ermittelt, war
an diesen Stellen also noch leer. Die Prüfung musste deshalb gegen die
**Soll-Liste** selbst klassifizieren. Beide Abschluss-Pfade teilen sich nun
eine Methode (`_unusable_calls_are_only_policy()`), damit sie nicht
auseinanderlaufen können.

**Nachweis, dass nichts schlimmer wurde:**
- 492 Tests grün (vorher 490)
- Beide Leak-Sweeps 0
- Der Benchmark-Verifier weiterhin `OK` (baseline + Mutation)
- Die 4-Fall-Matrix stimmt in **beiden** Pfaden

**Offen:** die Live-Gegenprüfung gegen das echte Upstream. Nach den vielen
Tests ist das Konto in **HTTP 429 / Code 10061** (Ratelimit) — dort lässt
sich derzeit nichts mehr prüfen. Die deterministische Prüfung oben
ersetzt das nicht, sie verschiebt es nur.

### F-6 Bewusst nicht umgesetzt

- **C-14** (Lease/Socket vor dem ersten `yield`): In CPython räumt der Generator-GC die Ressourcen auf; eine Umstellung auf lazy-acquire würde die saubere 503-Antwort bei voller Queue verschlechtern.
- **C-17/S-04** (Debug-Dump-Inhalte): Redaktion ist implementiert (Tokens, Header); eine strukturelle Auslagerung des Debug-Dumps ist als Folgeaufgabe offen.
- **A-17** (MD5-Signatur als Upstream-Protokollwert): nicht Teil des Fix-Pakets, da keine sicherheitsrelevante Nutzung nachgewiesen ist.
