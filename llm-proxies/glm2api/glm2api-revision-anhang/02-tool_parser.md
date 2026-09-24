# 02 — tool_parser.py

(Scope: 1553 Zeilen, vollständig gelesen und geprüft)

## Befunde

### P-01 — Hoch: Bare-JSON-Heuristik macht gewöhnliche Antworten zu Tool-Calls
**Ort:** tool_parser.py:178-181, 719-720, 890-1024, 1370-1399

**Beschreibung:** Jedes zeilenbeginnende Objekt mit `"name"` gilt als möglicher Tool-Call. Im normalen JSON-Pfad werden beliebige Geschwister-Schlüssel über `_extract_call_arguments` zu Argumenten; in den danach akzeptierten Bare-Items werden Objekte ohne `"name"` anhand von `filePath`/`content`, `filePath` plus Edit-Feldern, `command` oder einem einzelnen `filePath` automatisch zu `write`, `edit`, `bash` oder `read` umgedeutet. `allowed_tool_names=None` ist ausdrücklich ein Wildcard. Damit fehlt nicht nur ein Wrapper, sondern auch eine belastbare Shape- oder Kontextprüfung.

**Verifizierte Ausgabe:**
- `Hier ist die Konfiguration:\n{"name":"service-a","version":"1.0","features":["a"]}` → Call `service-a` mit `{"version":"1.0","features":["a"]}`.
- `Konfiguration:\n{"name":"read","value":"nur Text"}` mit Allowlist `{"read"}` → echter `read`-Call mit `{"value":"nur Text"}`.
- Eingerückte JSON-Beispiele und Tilde-Fences (`~~~json`) werden ebenfalls geparst; nur Backtick-Fences sind geschützt.

**Auswirkung:** Normale JSON-Antworten können als auszuführende Calls emittiert und aus dem sichtbaren Text entfernt werden. Das reproduziert den bekannten I-009-Fund und kann bei passendem Namen reale Tools auslösen.

**Empfehlung:** `None` nicht als Ausführungs-Wildcard verwenden; zwischen „keine Tools verfügbar“ und einem bewussten Recovery-Modus unterscheiden. Bare-Recovery nur bei explizitem Tool-Kontext, Allowlist und streng validiertem Call-Schema aktivieren; generische JSON-Objekte nicht anhand weniger Schlüsselnamen in Tools umdeuten.

### P-02 — Hoch: Bare-Parser umgeht die Blockliste nativer Tools
**Ort:** tool_parser.py:178-181, 1007-1014

**Beschreibung:** `_is_allowed_tool_name` lehnt Namen in `BLOCKED_NATIVE_TOOL_NAMES` korrekt ab. Der Bare-Parser wertet jedoch `if _is_allowed_tool_name(...) or allowed_tool_names is None` aus: Bei `None` wird jedes blockierte Native-Tool durch das zweite `or` wieder zugelassen.

**Verifizierte Ausgabe:** `{"name":"open_url","arguments":{"url":"https://example.com"}}` mit `allowed_tool_names=None` erzeugt einen `open_url`-Call.

**Auswirkung:** Die zentrale Native-Tool-Sperre wird im Bare-Format umgangen. Je nach Client kann ein nicht deklariertes bzw. ausdrücklich gesperrtes Tool dennoch als Tool-Call weitergereicht werden.

**Empfehlung:** Die Bedingung durch `if _is_allowed_tool_name(name, allowed_tool_names):` ersetzen. Wildcard-Semantik darf niemals eine Denylist-Prüfung überstimmen.

### P-03 — Hoch: Gefilterte Bare-Calls werden im Stream roh sichtbar
**Ort:** tool_parser.py:1015-1024, 1304-1333, 1402-1457

**Beschreibung:** `_find_bare_tool_call_array` kann ein gefiltertes Protokoll korrekt aus dem sichtbaren Text entfernen und liefert dann `tool_calls=[]`. `_split_stream_text` übernimmt dieses Ergebnis aber nur bei Calls oder bei nicht-finalem `remainder`; im finalen Fall mit leerem Remainder wird das bereinigte Ergebnis verworfen und der ursprüngliche Prozessierbar-Text erneut ausgegeben. Der Final-Parser übernimmt die Bereinigung dagegen. Außerdem erkennt `detect_tool_call_names` Bare-Formen grundsätzlich nicht und verwendet nicht die Recovery-Stufe für fehlende Array-Abschlüsse.

**Verifizierte Ausgabe:** Direkt- und Array-Form von `{"name":"bash","arguments":{"command":"pwd"}}` mit Allowlist `{"read"}`:
- Streaming: sichtbarer Roh-Call, `calls=[]`.
- Final: sichtbarer Text `""`, `calls=[]`.

**Auswirkung:** Genau die vom Nutzer gemeldete Fehlklassifikation bleibt im Stream-Pfad bestehen: Ein blockierter oder nicht deklarierter Bare-Call landet als Antwort im Text. Wegen der fehlenden Bare-Erkennung in `detect_tool_call_names` fehlt außerdem der negative Follow-up-Pfad.

**Empfehlung:** Auch ein bereinigtes Ergebnis mit null Calls als semantisch relevant weiterreichen. Die Detection sollte denselben Parser und dieselben Recovery-Stufen verwenden und Bare-/Bare-Array- sowie fehlende-Abschluss-Formen abdecken. Endgültig unterdrückte Call-Versuche als strukturiertes Signal statt als sichtbaren Text behandeln.

### P-04 — Hoch: Text-Funktions-Call-Fallback fehlt nur im Stream-Pfad
**Ort:** tool_parser.py:1262-1333, 1336-1399

**Beschreibung:** `parse_tool_calls_from_text` enthält mit `_find_text_function_call` einen Fallback für `read("…")`, `bash("…")` und `webfetch("…")`. `_split_stream_text` ruft diesen Fallback nie auf. Final- und Stream-Pfad liefern daher für dieselbe Eingabe unterschiedliche Ergebnisse.

**Verifizierte Ausgabe:** Zeichenweises Streaming von `read("/tmp/a.py")` mit Allowlist `{"read"}` ergibt sichtbaren Text `read("/tmp/a.py")` und null Calls; der Final-Parser erkennt denselben Text als `read`-Call.

**Auswirkung:** Ein im Live-Fall beobachteter Fallback kann im Stream als sichtbarer Text erscheinen und nicht ausgeführt werden. Ein später Finalize-Safety-Net kann bereits emittierten Content nicht zuverlässig zurückziehen.

**Empfehlung:** Eine gemeinsame, zustandsbasierte Parse-Kernfunktion für Final und Stream verwenden. Den Text-Fallback nur an vollständigen Zeilen und nur im expliziten Recovery-Modus anwenden; nicht blind in den Streampfad duplizieren.

### P-05 — Hoch: JSON-Holdback bricht bei Whitespace- und nackten Call-Formen
**Ort:** tool_parser.py:713-720, 906-913, 1041-1052, 1296-1333

**Beschreibung:** Die vollständigen Start-Regex akzeptieren Pretty-Print und Whitespace. Die partiellen Holdback-Suchen sind dagegen hart auf die minifizierten Strings `'[{"name"'` und `'{"tool_calls":'` codiert. Für einen nackten Call ohne `[` existiert überhaupt kein Prefix-Holdback.

**Verifizierte Ausgabe bei zeichenweisem Streaming:**
- `{\n  "tool_calls": [...] }[]` → vollständiger Rohtext, null Calls.
- `[\n  {\n    "name": "bash", ... }]` → vollständiger Rohtext, null Calls.
- `{"name":"bash","arguments":{...}}` → vollständiger Rohtext, null Calls.

**Auswirkung:** Erkennung und Sichtbarkeit hängen von der Chunk-Grenze ab. Echte Tool-Calls können sowohl verloren gehen als auch als JSON sichtbar werden.

**Empfehlung:** Holdback aus derselben Grammatik wie die vollständige Erkennung ableiten, vorzugsweise per inkrementellem Zustandsautomaten. Tests sollten jeden Split-Punkt sowie gemischte Chunkgrößen für Wrapper, Array und nackte Calls fuzzen.

### P-06 — Hoch: Transcript-Echo-Holdback ist von bestimmten Chunk-Formen abhängig
**Ort:** tool_parser.py:726-762, 1281-1295

**Beschreibung:** `_TRANSCRIPT_ECHO_PARTIAL_PROBES` enthält nur vollständig ausgeschriebene, case-sensitiv passende Präfixe wie `User: [{"`. Beginnt ein Chunk mit `U`, `Us` oder einem anderen Teil des Rollenpräfixes, wird dieses bereits emittiert; der spätere Chunk kann keinen zusammenhängenden Echo-Start mehr bilden. Kleingeschriebene `user:`-Zeilen werden generell nicht erkannt.

**Verifizierte Ausgabe:** Selbst die kanonische Echo-Zeile `User: [{"call_id":"c1","name":"read","content":"x"}]` wird bei zeichenweisem Streaming vollständig sichtbar; ebenso `user: [...]`.

**Auswirkung:** Der Live-Fix gegen `User: [{"call_id":…}]`-Echoes ist nur für bestimmte Upstream-Chunking-Schemata wirksam. Andere Tokenisierung führt weiterhin zu sichtbaren Halluzinations-Transkripten.

**Empfehlung:** Ein case-insensitives, partielles Regex oder einen Echo-Zustandsautomaten verwenden und bereits den frühestmöglichen Präfix zurückhalten. Chunk-Fuzzing mit jedem Split-Punkt und gemischten Größen als Regressionstest aufnehmen.

### P-07 — Hoch: Generische `<tool_call>`- und JSON-in-XML-Formen fehlen
**Ort:** tool_parser.py:29-32, 296-385, 1398-1399

**Beschreibung:** Der Start-Tag-Automat erkennt `tool_calls`/`ml_tool_calls` und `ml_tool_call`, aber kein generisches einzelnes `<tool_call>`, auch nicht mit U+200B. Die Extraktion akzeptiert bei XML nur `invoke@name` oder `ml_tool_name`/`tool_name` und `ml_parameters`/`parameters`; ein JSON-Payload als Text des Call-Elements wird nicht geparst. Unvollständige XML wird im Final-Parser weder als Call verarbeitet noch unterdrückt.

**Verifizierte Ausgabe:**
- `<tool_call>{"name":"bash","arguments":{...}}</tool_call>` sowie `<\u200btool_call>{"name":"bash","arguments":{...}}</\u200btool_call>` bleiben sichtbar, null Calls.
- `<tool_calls>{"name":"bash","arguments":{...}}</tool_calls>` wird still entfernt, aber nicht ausgeführt.
- Ein abgeschnittener XML-Block bleibt im Final-Parser als Rohmarkup sichtbar.

**Auswirkung:** Reale XML-/DSML-ähnliche Call-Varianten werden nicht ausgeführt; je nach Form entstehen entweder sichtbares internes Markup oder ein still verschwundener Call. Das ist eine relevante False-Negative-Lücke neben dem JSON-Fix.

**Empfehlung:** Die XML-Grammatik explizit um generische `tool_call`-Elemente und einen strikt validierten JSON-Payload ergänzen. Optional U+200B nur an Tag-Grenzen normalisieren. Final- und Stream-Pfad bei unvollständigem Markup auf dieselbe sichere Unterdrückungs-/Diagnosebehandlung bringen.

### P-08 — Mittel: Transcript-Echo-Erkennung kann beliebige Folgetexte löschen
**Ort:** tool_parser.py:726-735, 796-833

**Beschreibung:** `_TRANSCRIPT_ECHO_START_RE` erlaubt ein optionales Anführungszeichen auch ohne `{`/`[`. Dadurch matcht bereits `Assistant: "name" is required`. `_find_transcript_echo_span` sucht anschließend `[` oder `{` nicht auf derselben Zeile, sondern an jeder späteren Position und entfernt bis zum Ende dieses weit entfernten JSON-Objekts.

**Verifizierte Ausgabe:** `Assistant: "name" is a required field.\nHere is the data:\n{"value": 1}\nDone.` wird zu `Done.`; die eigentliche Antwort fehlt.

**Auswirkung:** Normale Rollen-bezeichnete Prosa kann zusammen mit einer späteren JSON-Struktur still gelöscht werden. Das ist eine False-Positive-/Datenverlustregression des Echo-Schutzes.

**Empfehlung:** Echo-Start nur akzeptieren, wenn `[` oder `{` auf derselben Zeile folgt; das öffnende Delimiter erfassen und den Balance-Scan auf diesen exakten Start begrenzen. Rollenname und JSON-Form sollten gemeinsam validiert werden.

### P-09 — Mittel: `strip_unparseable_call_fragments` löscht valide JSON
**Ort:** tool_parser.py:1230-1259

**Beschreibung:** Die Vollständigkeitsprüfung vergleicht das Ende des balancierten JSON-Objekts mit `len(fragment)`, ohne abschließende Whitespace zu ignorieren. Ein gültiges JSON-Objekt mit Newline gilt dadurch als abgeschnitten. Endet das JSON-Objekt gefolgt von normalem Erklärungstext, wird ebenfalls alles ab dem Objekt gelöscht.

**Verifizierte Ausgabe:**
- `Konfiguration:\n{"command":"pwd","cwd":"/tmp"}\n` → `Konfiguration:`.
- `Konfiguration:\n{"filePath":"/tmp/a","other":1}\nErklärung folgt.` → `Konfiguration:`.
- Dieselbe JSON-Zeile ohne abschließenden Newline bleibt erhalten.

**Auswirkung:** Gültige JSON-Antworten, die nach dem Parsen nicht als Call akzeptiert wurden, können als angebliche Call-Fragmente still verschwinden. Besonders `command`-/`filePath`-Objekte ohne Tool-Schema sind betroffen.

**Empfehlung:** Nach dem Balance-Scan den abgeschlossenen JSON-Teil tatsächlich mit `json.loads` prüfen. Whitespace außerhalb des Objekts nicht als Unvollständigkeit werten; nur syntaktisch unparsebare Restfragmente und nur bis zum echten Streamende unterdrücken.

### P-10 — Mittel: DSML-Reparatur verändert Text in CDATA
**Ort:** tool_parser.py:121-170, insbesondere 137-138

**Beschreibung:** `_repair_malformed_dsml` führt global `repaired.replace('">>', '">')` auf dem gesamten Block aus. Diese Ersetzung ist nicht auf fehlerhafte Tags begrenzt und greift daher auch in CDATA-Argumenten.

**Verifizierte Ausgabe:** Der Command-Text `printf 'a">>b'` wird als `printf 'a">b'` an den Tool-Call übergeben.

**Auswirkung:** Ein semantisch gültiges Tool-Argument kann still verändert werden; bei einem Bash-Command ist das eine potenziell ausführungsrelevante Datenbeschädigung.

**Empfehlung:** Reparaturen nur an Tag-Strukturen anwenden, z. B. durch tagbewusste Ersetzungen oder XML-/DSML-Tokenisierung. CDATA-Inhalte vor und nach Reparatur unverändert erhalten.

### P-11 — Mittel: Fenced Bare-Calls werden nicht erkannt
**Ort:** tool_parser.py:11, 403-408, 890-905, 1035-1039

**Beschreibung:** `_mask_code_fences` maskiert den gesamten Inhalt jedes ```-Fences. Dadurch werden sowohl echte fenced Bare-Arrays als auch fenced nackte Write-Objekte vom Parser ignoriert. Der direkte Final- und Stream-Parser besitzt keine Ausnahme für einen eindeutig protokoll-only Fence.

**Verifizierte Ausgabe:** Ein Block mit ` ```json `, einem Bare-Array mit `bash`-Call und schließendem ` ``` ` bleibt im Stream und im Final-Parser unverändert sichtbar; null Calls.

**Auswirkung:** Eine echte Call-Variante, die das Modell in einen fenced Block legt, landet als Text statt als Tool-Call. Die nachgelagerte Translator-/Callback-Ebene rettet derzeit nur den klassischen `{"tool_calls":...}`-Wrapper, nicht die Bare-Form.

**Empfehlung:** Eine zentrale, strikt validierende Fence-Protokoll-Erkennung für beide Wege ergänzen. Nur ein Fence, dessen gesamter Inhalt dem erlaubten Call-Format entspricht, darf entpackt werden; Dokumentationsfences und Markdown-Beispiele müssen maskiert bleiben.

### P-12 — Hoch: Wiederholtes Vollscan des Streams erzeugt O(n²)-Verhalten
**Ort:** tool_parser.py:403-408, 1027-1053, 1467-1527

**Beschreibung:** Jeder `consume`-Aufruf hängt an den bestehenden Buffer an. Bei jedem Aufruf werden u. a. `pending_text.lower()` und Marker-Suchen für alle `TAG_NAME_HINTS` wiederholt; anschließend scannen `find_tool_calls_protocol`/`_find_json_tool_call` den gesamten Buffer erneut. Die Maskierung erzeugt zusätzlich pro Scan eine vollständige Zeichenliste.

**Messung:** Ein minifizierter JSON-Call mit entsprechend 500, 1 000, 2 000, 4 000 und 8 000 Zeichen im `command`-Argument benötigte bei zeichenweisem Konsumieren etwa 0,057 s, 0,147 s, 0,459 s, 2,241 s und 7,608 s. Bei 8 000 Zeichen kosteten 8er-Chunks noch 1,179 s, 32er-Chunks 0,247 s und ein einzelner Chunk 0,0015 s.

**Auswirkung:** Ein langer Tool-Output kann bei token-/zeichenweisen Upstream-Deltas CPU blockieren und die Stream-Latenz stark erhöhen. Das ist nicht nur ein theoretisches O(n²)-Risiko.

**Empfehlung:** Parser als inkrementelle Zustandsmaschine implementieren: Lowercase/Maskierung und delimiterbezogene Suchen pro Chunk einmal ausführen, nur den neuen Tail scannen und offene JSON-/Bracket-Zustände speichern. Zusätzlich eine Holdback-Obergrenze definieren.

### P-13 — Niedrig: Bare-Parser entfernt den nachfolgenden Fence nicht
**Ort:** tool_parser.py:950-959

**Beschreibung:** Der vermeintliche Fence-Consume ist `consumed += len(rest) - len(rest)`, also ein No-op. Der nachfolgende Fence bleibt im sichtbaren Rest.

**Verifizierte Ausgabe:** `{"name":"bash","arguments":{"command":"pwd"}}``` ` erzeugt den Call und lässt drei Backticks als sichtbaren Text stehen.

**Auswirkung:** Ein bekannter I-020-Fall: Der Call wird zwar erkannt, aber der Fence leckt als sichtbares Antwortfragment. Das kann Clientdarstellung und nachgelagerte Heuristiken beeinflussen.

**Empfehlung:** Die tatsächlich zu konsumierende Länge aus `rest_stripped` berechnen und nur den Fence-Präfix bis zum passenden Ende entfernen.

### P-14 — Mittel: Holdback ist bei Literal-`<|` und Truncation unbegrenzt
**Ort:** tool_parser.py:60-93, 906-945, 1078-1085, 1472-1488, 1529-1553

**Beschreibung:** Jedes Vorkommen des Generics `<|` aktiviert `buffering_dsml` und lässt den gesamten Rest bis `flush()` liegen. Für unvollständige JSON-/Bare-Calls gibt es ebenfalls keine Obergrenze für `pending_text`; bei einem begonnenen, aber nie geschlossenen Objekt wächst der Buffer mit jedem weiteren Chunk unbegrenzt.

**Verifizierte Ausgabe:** `Die Formel lautet <| und danach folgt eine sehr lange Antwort.` emittiert vor `flush()` nur den Präfix; der Rest kommt erst beim Flush. Ein abgeschnittenes `write`-JSON hielt nach 5 000 zusätzlichen Zeichen weiterhin über 5 000 Zeichen in `pending_text`.

**Auswirkung:** Kein dauerhafter Bufferverlust bei korrektem `flush()`, aber erhebliche Latenz, Speicherverbrauch und Leere-Anzeige bei gewöhnlichem `<|`-Text oder einem früh beschädigten Call-Stream. Der Flush bricht bei fehlendem Fortschritt, daher gibt es hier keine Endlosschleife.

**Empfehlung:** Nur echte DSML-/Markup-Präfixe in den DSML-Modus schalten, einen begrenzten Pending-Buffer einführen und bei Überschreitung eine explizite, sichtbare Fehler-/Fallback-Policy anwenden. Der Stream sollte auch bei fehlendem `flush()` nicht unbegrenzt wachsen.

## Positiv

- Die bestehende Testsuite ist aktuell grün: `uv run pytest tests/test_tool_parser.py -q` → **48 passed in 0.10s**.
- Die JSON-Brace-Scans sind string-aware: Verschachtelte Objekte/Arrays sowie `}` und escapte Quotes in Argument-Strings wurden korrekt verarbeitet.
- `arguments` als JSON-String und als Objekt werden in den JSON-Pfaden korrekt weitergereicht; ein String mit verschachteltem `}` wurde nicht vorzeitig abgeschnitten.
- Ein kanonischer `{"tool_calls": ...}`-Block ohne abschließendes `[]` wird im Final-Pfad repariert; ein Bare-Array ohne schließende `]` wird über die Recovery-Stufe verarbeitet. Das sind im Final-Pfad keine Standard-False-Negatives.
- Kanonische DSML- und die im Repo getesteten malformed DSML-Varianten werden geparst; Triple-Backtick-Fences mit vollständigem klassischem Wrapper werden als Dokumentationsinhalt maskiert.
- `flush()` setzt `pending_text` und `buffering_dsml` zurück und bricht bei fehlendem Fortschritt, sodass im geprüften Pfad keine Endlosschleife entsteht.

## Geprüft und unauffällig

- Normale, vollständige JSON-Objekte ohne Tool-typischen Anfangsschlüssel werden von `_find_json_tool_call` nicht als klassischer Wrapper akzeptiert.
- Ein klassischer JSON-Wrapper mit ausreichend Argumenten wird auch dann nicht geparst, wenn sein Name nicht erlaubt ist; der Wrapper-Text wird im Final-Parser unterdrückt. Die Abweichung des Bare-Pfads ist separat in P-03 dokumentiert.
- Vollständige, korrekt balancierte JSON-Arrays mit verschachtelten Stringwerten wurden nicht durch den Brace-Scan abgeschnitten.
- Die getesteten vollständigen DSML-Close-Tag-Reparaturen und XML-Close-Tag-Reparaturen funktionieren für die im Testbestand abgedeckten Formen.
- Bei einem leeren Input liefern Parser und Stream-Klasse leere Ergebnisse; bei leerem Tool-Input wird kein Phantom-Call erzeugt.
- Der unvollständige Wrapper-Stream wartet auf `flush()` oder auf nachfolgenden Text, statt sich endlos zu wiederholen; die relevante praktische Lücke sind die in P-05 beschriebenen Whitespace-/Bare-Formen.
