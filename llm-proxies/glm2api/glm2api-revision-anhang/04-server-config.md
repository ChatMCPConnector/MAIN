# 04 — server.py, config.py, app.py, logging_utils.py, model_variants.py, Entry-Points
(Scope: 1.251 Zeilen in sieben Dateien: `server.py` 489, `config.py` 347, `app.py` 107, `logging_utils.py` 224, `model_variants.py` 46, `main.py` 4, `__main__.py` 34. `.env.example` wurde zusätzlich mit 161 Zeilen vollständig gelesen.)

## Befunde

### S-01 — KRITISCH (bestätigt I-002): Unbegrenzte Request-Aufnahme ermöglicht lokale DoS
**Ort:** `server.py:41-45`, `server.py:119-129`, `server.py:448-453`

`ThreadingHTTPServer` startet für jede Verbindung einen Thread. Vor der GLM-Queue wird der komplette via `Content-Length` angeforderte Body mit `self.rfile.read(content_length)` gelesen. Es gibt kein Body-Limit, keinen Socket-/Header-/Gesamtlaufzeit-Timeout, keine Ablehnung von `Transfer-Encoding: chunked` und keine Prüfung auf eine tatsächlich vollständig empfangene Body-Länge. Negative Längen werden abgewiesen, aber ein beliebig große positive Länge nicht.

**Auswirkung:** Ein langsam sendender Client bindet Threads und Ingress-Ressourcen; ein großer Body erzwingt große Allokationen. Bei `HOST=0.0.0.0` ist das auch remote ausnutzbar. Die GLM-Queue wirkt nicht als Eingangsschutz, weil der Body vorher vollständig im Handler liegt.

**Empfehlung:** Hartes konfigurierbares Body-Limit, `413`/`408`/`431`, exakte Reads mit Timeout, Reject-on-chunked/uneinheitlichen Längen, Socket-Timeouts und ein begrenzter Executor-/Connection-Semaphor statt unbeschränktem Threadwachstum.

### S-02 — HOCH (bestätigt I-012): Authentifizierung ist standardmäßig aus und CORS ist wildcard- offen
**Ort:** `config.py:315-316`, `server.py:63-66`, `server.py:68-87`, `server.py:114-117`, `server.py:408-420`, `server.py:434-440`

Eine leere `SERVER_API_KEYS`-Liste deaktiviert die Authentifizierung vollständig. `CORS_ALLOW_ORIGIN` ist im Code und in `.env.example` `*`; der Preflight erlaubt außerdem `Authorization` und `x-api-key`. `/health` und `/v1/models` werden grundsätzlich vor jeder Autorisierung bedient. Die Tokenprüfung verwendet direkte Membership-Prüfung statt constant-time Vergleich.

**Auswirkung:** Eine beliebige Website kann einen im Browser erreichbaren Loopback-Dienst per CORS-Preflight ansprechen und Responses lesen. Bei LAN-/Remote-Binding ist der Proxy ohne zusätzliche Konfiguration offen. Health/Model-Metadaten sind zusätzlich nicht an die API-Authentifizierung gebunden.

**Empfehlung:** Bei jedem Nicht-Loopback-Binding Authentifizierung erzwingen; CORS-Default auf explizite Origins setzen; nur benötigte Preflight-Header zulassen; `/models` authentifizieren oder die öffentliche Absicht explizit dokumentieren; Key-Vergleich mit `hmac.compare_digest` und Rotation/Hashing.

### S-03 — HOCH (bestätigt I-014): Responses-/Anthropic-Streaming nutzt eine unbeschränkte Queue und eine nicht abbrechbare Reader-Pipeline
**Ort:** `server.py:304-316`, `server.py:318-364`

`_run_accumulated_sse_stream` startet einen Daemon-Reader, der den gesamten Upstream in `queue.Queue()` ohne `maxsize` legt. Der Writer hat weder ein Cancellation-Event noch einen `finally`, der `stream_iter.close()` oder die Response schließt. Bei einem langsamen oder disconnecteten Client läuft der Reader weiter; der Client-Pfad kehrt zurück, während Queue, Upstream-Slot und Generator weiterleben können. Der Reader transportiert außerdem `BaseException`.

**Auswirkung:** Ein disconnecteter Client kann den Upstream weiter vollständig lesen und unbegrenzt puffern. Queue-Speicher, Threadanzahl und belegte GLM-Konten steigen; nachfolgende Agentenaufrufe warten oder timeouten. Das betrifft `/v1/responses` und `/v1/messages`, nicht den direkten Chat-Streampfad.

**Empfehlung:** Synchrones Lesen oder bounded Queue mit Backpressure, explizites Cancellation-Event, Upstream-Iterator im `finally` schließen, aktive Reader mit einem begrenzten Executor verwalten und ausschließlich `Exception` transportieren.

### S-04 — HOCH (bestätigt I-005/I-019): Debug-Dumps legen Secrets und Rohdaten in weltlesbaren Dateien ab
**Ort:** `config.py:264-267`, `logging_utils.py:186-198`, `logging_utils.py:205-224`, `server.py:127`, `server.py:154`, `server.py:424-426`, `server.py:475-481`

`DEBUG_DUMP_ALL=true` erzwingt DEBUG und aktiviert damit die rotierende Datei. `debug_dump()` redigiert nichts. Eingehende Header, einschließlich `Authorization` und `x-api-key`, sowie rohe Bodies, Prompts, Tool-Argumente, SSE-Chunks und Upstream-Daten werden serialisiert. `_debug_log_request_start()` logged alle Request-Header; Upstream-Dumps enthalten ebenfalls Token-Header.

Im geprüften Runtime-Zustand war `DEBUG_DUMP_ALL=true` gesetzt. `.env`, `.env.example`, `log/` und alle rotierenden Logdateien waren mit Modus `0666` bzw. Verzeichnis `0777` angelegt; die `.env` enthielt einen nichtleeren Refresh-Token (der Wert wurde nicht ausgegeben). Der Inhalt der Logs wurde nicht gelesen.

**Auswirkung:** Andere lokale Benutzer können Secrets, Prompts und Tool-Inhalte lesen oder Konfiguration/Logs verändern. Debug-Daten können über Backups und Rotation dauerhaft erhalten bleiben.

**Empfehlung:** Debug-Dump standardmäßig deaktiviert und als explizit gefährliches Feature behandeln; Header-/Token-/URL-Redaktion, Binärinhalte nur als Hash/Metadaten, Secret-Dateien atomar mit `0600`, Logverzeichnis `0700` und restriktive Ownership-Prüfung.

### S-05 — MITTEL (bestätigt I-013): Upstream-Timeouts und Upstream-Verbindungsfehler gelten als Client-Disconnect
**Ort:** `server.py:29`, `server.py:215-216`, `server.py:342-344`, `server.py:391-393`

`_CLIENT_DISCONNECTED` enthält `socket.timeout`, `ConnectionResetError`, `BrokenPipeError` und `ConnectionAbortedError`. Diese Exceptions können aus dem Upstream-Socket stammen, nicht nur aus `self.wfile`/`self.rfile`. Im Non-Stream-Pfad wird dann keine JSON-Antwort geschrieben. Im Chat-Stream führt `finally` trotzdem zu `data: [DONE]`; der Adapter-Stream liefert bei Disconnect weder Error- noch Finish-Event.

**Auswirkung:** Ein Upstream-Timeout kann als scheinbar erfolgreicher, leerer oder abgeschlossener Turn beim Client ankommen. Agenten verlieren dadurch Retry- und Fehlerinformationen.

**Empfehlung:** Client-Disconnects und Upstream-Timeouts in getrennte Exception-Typen aufteilen; nur Schreibfehler des Downstream-Sockets als Disconnect behandeln; Upstream-Fehler als `502/504` oder API-spezifisches Failed-Event ausgeben und nach einem Fehler kein `[DONE]` senden.

### S-06 — MITTEL (bestätigt I-016): Interne und Upstream-Fehlerdetails werden an Clients zurückgegeben
**Ort:** `server.py:196-222`, `server.py:455-467`

`UpstreamAPIError` gibt `str(exc)` und das komplette `exc.payload` als `details` zurück. Der generische Exception-Handler gibt `str(exc)` plus Exception-Klasse zurück; der `ValueError`-Handler klassifiziert jeden solchen Fehler als Client-400. Das kann interne URLs, Upstream-Response-Strukturen, Request-IDs, signierte URLs oder Dateipfade offenlegen. Ein interner Datei-/JSON-Fehler wird dadurch außerdem als Benutzerfehler missklassifiziert.

**Auswirkung:** Informationsleck, unbeabsichtigte Offenlegung sensibler Upstream-Daten und falsche Client-Retry-Entscheidungen.

**Empfehlung:** Öffentliche stabile Fehlermeldungen mit Correlation-ID verwenden; vollständige Details nur redigiert serverintern loggen; `details` entfernen; Upstream-, Datei- und Request-Validierungsfehler getrennt klassifizieren.

### S-07 — MITTEL (bestätigt I-018): Eingabevalidierung ist ad hoc und endpoint-inkonsistent
**Ort:** `server.py:119-186`, `server.py:226-236`, `server.py:255-265`, `server.py:368-371`

Nur `/chat/completions` prüft `model` und `messages`. `/messages` und `/responses` akzeptieren fehlende/ungültige Messages, Tool-Strukturen und `max_tokens`; der Image-Pfad akzeptiert jeden truthy `prompt`-Wert. Es gibt keine Grenzen für Arraylängen, Strings, Verschachtelung, Tool-Anzahl oder Prompt-/Schema-Ausgabe. `json.loads()` akzeptiert standardmäßig `NaN`/`Infinity`, und `payload.get("stream")` verwendet Truthiness statt einer strikten Boolean-Prüfung. Ungültige Tool-Definitionen werden von den Adaptern still verworfen.

**Auswirkung:** Malformed Requests enden in sporadischen 502ern/Attributefehlern oder werden mit veränderter Semantik an GLM weitergereicht. still verworfene Tool-Deklarationen können dazu führen, dass das Modell statt eines strukturierten Calls textlich antwortet.

**Empfehlung:** Vor allen Adaptern eine zentrale strikte Schema- und Größenvalidierung einführen, unbekannte/fehlende Felder explizit behandeln, Standard-JSON ohne NaN/Infinity erzwingen, `stream` als Boolean validieren und Tool-Schemata vollständig prüfen.

### S-08 — HOCH (bestätigt I-007): Abgebrochene oder unvollständige Streams werden als erfolgreiche Terminalantwort behandelt
**Ort:** `server.py:282-364`, `server.py:368-404`; Upstream-Abbruchpfad in `services/glm_client.py:1089-1124` und `442-584`

Der Server unterscheidet kein EOF ohne gültiges Finish von einem erfolgreichen Ende. Der GLM-Client finalisiert einen Turn bei fehlendem Finish als `stop`; anschließend sendet der Server für Anthropic `message_stop`, für Responses `response.completed` oder für Chat `[DONE]`. Im Chat-Pfad wird `[DONE]` im `finally` auch nach einem Stream-Error gesendet. Der lokale Fake-Upstream-Test bestätigte: ein abrupter Stream erzeugte `message_stop` beziehungsweise `[DONE]` ohne Error; ein `socket.timeout` erzeugte ebenfalls `[DONE]` ohne Error.

**Auswirkung:** Ein partieller Text, ein unvollständiger Tool-Call oder ein fehlender Turn kann als vollständige Antwort beim Agenten ankommen. Der Agent beendet den Tool-Loop oder interpretiert eine zufällige Textantwort als Ergebnis. Das ist der direkteste verbleibende Pfad für das gemeldete „Toolcall als Antwort“-Symptom.

**Empfehlung:** Upstream-Terminierungsstatus explizit modellieren; EOF ohne `[DONE]`/Finish als `truncated_stream` behandeln; niemals `completed`, `message_stop` oder `[DONE]` nach Fehlern senden; Tool-Result-/Text-Status im Terminalzustand eindeutig kodieren und je Endpoint mit Abschneidefällen testen.

### S-09 — MITTEL: Frühe HTTP/1.1-Fehler lassen den Request-Body auf der Keep-alive-Verbindung liegen
**Ort:** `server.py:61`, `server.py:104-125`, `server.py:110-117`

`protocol_version` ist HTTP/1.1. Bei unbekanntem Pfad, fehlender Authentifizierung oder negativem `Content-Length` wird geantwortet, ohne den Body zu lesen, ohne `Connection: close` zu setzen oder den Socket zu schließen. Der nächste Request-Parse beginnt daher mit den Rest-Bytes des vorherigen Bodies. Ein lokaler Raw-Socket-Test nach einer 401-Antwort erzeugte danach `501 Unsupported method` mit dem vorherigen JSON-Body plus Folgerequest im Request-Text.

**Auswirkung:** HTTP-Desynchronisation, vergeblicte Handler-Threads, unzuverlässige Pipeline-/Proxy-Kommunikation und mögliche Request-Smuggling-/Boundary-Fehler bei vorgeschalteten Reverse Proxies.

**Empfehlung:** Bei jeder Frühantwort `close_connection=True`/`Connection: close` setzen oder den Body innerhalb eines eigenen Limits drainieren; Chunked-Encoding, doppelte Längen und Pipelining ablehnen; die HTTP-Request-Lifecycle-Logik zentralisieren.

### S-10 — HOCH: Ein blockierter oder nicht deklarierter Tool-Call endet als normale Assistenten-Textantwort
**Ort:** `config.py:310`, `config.py:313`, `server.py:181-195`, `server.py:226-236`, `server.py:255-265`; Verarbeitung in `services/glm_client.py:328-348` und `497-550`, `services/translator.py:1469-1492` und `1563-1572`

Nicht erlaubte beziehungsweise blockierte Calls werden aus dem strukturierten Call entfernt. Nach `GLM_BLOCKED_TOOL_FOLLOW_UPS` beziehungsweise wenn Follow-ups deaktiviert sind, erzeugt der Accumulator einen normalen `content`-Text wie eine „unavailable tool“-Meldung und `finish_reason=stop`. Der Server reicht diesen Text mit HTTP 200 weiter; die Anthropic-/Responses-Adapter machen daraus ebenfalls normale Textantworten.

**Auswirkung:** Der Client kann nicht strukturiert erkennen, dass ein Tool-Protokoll fehlgeschlagen ist. Ein Agent kann die Meldung als finale fachliche Antwort darstellen und den Tool-Loop beenden. Das entspricht direkt der beobachteten Fehlklassifikation „Toolcall als Antwort“.

**Empfehlung:** Keine prose Fallback-Antwort als scheinbar finalen Assistant-Turn senden. Stattdessen ein definiertes API-Fehler-/Tool-Failure-Schema mit stabiler Fehlerkennung verwenden, Follow-up-/Retry-Status explizit ausweisen und Textantworten von Protokollfehlern trennen.

### S-11 — HOCH: Responses-Tool-Runden verlieren Auswahl und Tool-Ergebnisse
**Ort:** Server-Dispatch `server.py:162-165` und `server.py:255-265`; `services/responses_adapter.py:95-115` und `153-177`; `services/translator.py:637-660` und `823-838`

Zwei Responses-spezifische Vertragsprobleme bleiben bestehen:

1. Die Responses-API verwendet für eine erzwungene Function Choice üblicherweise `{"type":"function","name":"..."}`. Der Adapter reicht die Choice unverändert an die interne OpenAI-Logik weiter, die aber `{"type":"function","function":{"name":"..."}}` erwartet. Eine spezifische Choice wird dadurch zu `auto` und kann einen anderen Call oder Text erzeugen.
2. Ein `function_call_output` erhält nur dann einen `name`, wenn der passende vorherige Assistant-Call im selben Payload liegt. `previous_response_id` wird nicht ausgewertet. Der anschließende `convert_messages`-Pfad verwirft einen Tool-Turn ohne Namen. Tool-Ergebnisse aus einer vorherigen Responses-Runde können damit vollständig aus der Upstream-Historie fallen.

**Auswirkung:** Tool-Schritt-Zuordnung und erzwungene Auswahl sind nicht zuverlässig; der Agent kann ein Ergebnis nicht zurückgeben, denselben Call wiederholen oder stattdessen prose antworten.

**Empfehlung:** Beide Choice-Formen normalisieren, unbekannte Choices mit 400 ablehnen, `previous_response_id`/serverseitigen Responses-State sicher abbilden, Call-IDs und Toolnamen validieren und für jeden Responses-Tool-Rundlauf einen Roundtrip-Test ergänzen.

### S-12 — MITTEL: Anthropic `tool_choice: none` wird verworfen
**Ort:** Server-Dispatch `server.py:156-160`; `services/anthropic_adapter.py:155-183`

Der Anthropic-Adapter behandelt `auto`, `any` und `tool`, aber nicht `{"type":"none"}`. Die Tool-Deklarationen bleiben im OpenAI-Payload, während `tool_choice` fehlt; die interne Default-Policy ist anschließend `auto`.

**Auswirkung:** Ein Client, der Tool-Nutzung ausdrücklich verbietet, kann trotzdem einen strukturierten Tool-Call erhalten. Das ist das inverse Routing-Problem und kann ebenfalls zu unerwarteten Agentenaktionen führen.

**Empfehlung:** `none` explizit auf `tool_choice="none"` abbilden, alle Anthropic-Varianten strikt validieren und gemischte Tool-Use-/Tool-Result-Blöcke entweder verlustfrei konvertieren oder mit einem klaren 400 ablehnen.

### S-13 — MITTEL: Konfigurationspfad und Portdefault driften zwischen Code, Beispiel und Betrieb auseinander
**Ort:** `config.py:205`, `config.py:219-221`, `config.py:280`; `app.py:100-106`; `__main__.py:10-16`; `.env.example:16-18`; betriebliche Vorlage `llm-proxies/glm2api.env:16-18`

`load_config()` verwendet relativ zum aktuellen Arbeitsverzeichnis `.env`; es gibt keinen stabilen Projekt-/Package-Pfad und keine CLI-Option. Der Code- und Beispieldefault ist Port `8000`, die Betriebsvorlage und der Start-/Health-Vertrag verwenden Port `8001`. `rebuild.sh` warnt selbst vor dem 8000-Fallback, während der Startpfad 8001 prüft.

**Auswirkung:** Ein direkter `glm2api`-Start aus einem anderen Verzeichnis kann eine falsche/fehlende Config laden und `.env` dort anlegen. Ohne die Betriebsdatei läuft der Proxy auf 8000, während Agent/Supervisor auf 8001 warten; Auth-, CORS- und Upstream-Einstellungen können unerwartet wechseln.

**Empfehlung:** Einen kanonischen Port festlegen und alle Defaults/Vorlagen synchronisieren; Configpfad explizit als CLI-/ENV-Argument übergeben; bei fehlender erwarteter Config fail-closed starten oder den Port explizit per Startargument setzen.

### S-14 — HOCH: Concurrency-, Queue- und Retry-Budgets sind nicht konsistent begrenzt
**Ort:** `config.py:224`, `config.py:284`, `config.py:304-312`, `config.py:319-328`; `.env.example:105-149`; `llm-proxies/glm2api.env:90-107`

Der Code-Default für `GLM_MAX_CONCURRENCY` ist 3, die ausgelieferte Vorlage setzt 100. Im Gastmodus werden 100 Account-State-Einträge erzeugt; im automatischen Gast-Fallback gilt das auch, wenn keine Token konfiguriert ist. Bei einem Einzelaccount werden nur zwei Refresh-Token-Einträge (Account plus Guest-Fallback) erzeugt, während die Queue bis zu 100 Slots freigibt und die bevorzugte Ticket-Zuordnung den registrierten Account konzentrieren kann. Es gibt keine Obergrenze. `GLM_QUEUE_WAIT_TIMEOUT_SECONDS=600`, `REQUEST_TIMEOUT_SECONDS=120`, 30 Busy-Retries mit je 2 Sekunden sowie weitere Stream-/Leer-/Follow-up-Retries sind unabhängige Budgets ohne Gesamtdeadline. Die Betriebsvorlage erhöht `GLM_GUEST_MAX_RETRIES` zudem von 3 auf 10.

**Auswirkung:** Ein einzelner Request kann einen Slot über Minuten belegen; Multiplikatoren aus Queue, Busy-Retry, Upstream-Timeout und Stream-Retry verlängern die Latenz. Ein sehr großer Concurrency-Wert kann in Gastmodus Speicher/Upstream-Risiko erzeugen. Die Abweichung zwischen Code und Vorlage macht Defaults unvorhersehbar.

**Empfehlung:** Getrennte, harte Maxima für Slots und Gastkonten, sichere Defaultwahl je Auth-Modus, ein requestweises Gesamtdeadline, exponentielles Backoff mit Jitter, ein Retry-Budget statt unabhängiger Zähler und synchronisierte Betriebs-/Beispielvorlagen.

### S-15 — MITTEL: Config-Parser fällt bei ungültigen Werten still auf unsichere oder ungültige Defaults zurück
**Ort:** `config.py:75-103`, `config.py:224`, `config.py:305-316`, `config.py:319-328`

`parse_bool()` behandelt jeden unbekannten Wert als `false`; ein Tippfehler kann Auth-/Debug-/Gastlogik unerwartet deaktivieren. `CORS_ALLOW_ORIGIN=` wird durch `or "*"` wieder zu Wildcard. Negative Busy-Retries werden nicht abgewiesen, `parse_float()` akzeptiert `NaN`/`Inf`, und `GLM_MAX_CONCURRENCY` wird bei negativen Werten still auf 1 gesetzt. Es gibt keine fail-closed-Semantik für fehlerhafte Security-relevanten Werte.

**Auswirkung:** Tippfehler können Auth/CORS/Logging deaktivieren, Requests mit unendlichen oder ungültigen Sleep-Werten abstürzen lassen oder den Betrieb mit unbeabsichtigten Defaults starten.

**Empfehlung:** Strikte Boolean-/Numeric-Parser, `math.isfinite()`, explizite Mindest-/Maximalwerte und `ConfigError` für unbekannte oder leere Security-Werte; CORS-Leerwert darf nicht zu `*` werden.

### S-16 — HOCH (bestätigt I-017): `GLM_BASE_URL` erlaubt Klartext-HTTP für Token- und Attachment-Verkehr
**Ort:** `config.py:285`, `config.py:327-328`; Upstream-Aufrufe in `services/glm_auth.py:203-211` und `services/glm_client.py:812-834`

Die Validierung akzeptiert sowohl `http://` als auch `https://`. Refresh-/Access-Tokens, Request-Bodies und potenziell Attachment-Daten werden dadurch bei einer fehlkonfigurierten URL im Klartext übertragen.

**Auswirkung:** Ein lokaler Angreifer, manipulierter DNS-Eintrag oder ein kompromittiertes Netzwerk kann Tokens und sensible Inhalte abfangen. Der Default ist zwar HTTPS, die Fehlkonfiguration ist aber nicht sicherheitssicher abgesichert.

**Empfehlung:** Für Produktion HTTPS erzwingen; HTTP nur über ein explizites, development-only Flag mit Loopback-Bindung erlauben; URL-Parse, Host und Redirect-Policy validieren.

### S-17 — NIEDRIG: Der korrekt bezogene Server-Version-String legt zusätzlich die Python-Laufzeitversion offen
**Ort:** `server.py:60-61`

`server_version` wird korrekt aus `__version__` gebildet. `BaseHTTPRequestHandler.version_string()` hängt standardmäßig jedoch `sys_version` an; der beobachtete Header war `glm2api/0.1.0 Python/3.14.7`.

**Auswirkung:** Unnötige Fingerprinting-Information bei einem ansonsten lokalen Dienst.

**Empfehlung:** `sys_version=""` setzen oder `version_string()` überschreiben, wenn die Python-Laufzeit nicht offengelegt werden soll.

## Konfigurations-Audit

Ein AST-Abgleich von `config.py` und `.env.example` ergab **31 Codevariablen und 0 fehlende Variablen in `.env.example`**. Die nachfolgenden Defaults sind die Codewerte; relative Pfade werden in `config.py:225-227` beziehungsweise `243-246` relativ zur Env-Datei aufgelöst.

| Variable | Default | .env.example | sinnvoll? | Befund |
|---|---|---|---|---|
| `HOST` | `127.0.0.1` | `127.0.0.1` | Ja für lokal | Bei `0.0.0.0` ohne Auth gefährlich (S-02). |
| `PORT` | `8000` | `8000` | **Nein, Drift** | Betriebsvorlage/Start Health nutzen 8001 (S-13). |
| `API_PREFIX` | `/v1` | `/v1` | Ja | Keine unabhängige Resource-/Sicherheitswirkung. |
| `LOG_LEVEL` | `INFO` | `INFO` | Ja als Default | Betriebsvorlage setzt DEBUG; dadurch Datei-/Secret-Risiko (S-04). |
| `DEBUG_DUMP_ALL` | `false` | `false` | Ja als Default | Betriebsvorlage setzt `true`; Rohdaten-/Token-Dumps (S-04). |
| `REQUEST_TIMEOUT_SECONDS` | `120` | `120` | Bedingt | Sinnvoll für langsame Upstreams, aber kein Gesamtdeadline (S-14). |
| `CORS_ALLOW_ORIGIN` | `*` | `*` | **Nein** | Leerwert wird wieder `*`; Auth-/CORS-Defaultproblem (S-02/S-15). |
| `SERVER_API_KEYS` | `[]` | leer | **Nein als Default** | Auth vollständig aus; nicht-loopback unsicher (S-02). |
| `GLM_TOKEN_FILE` | `token.txt` | `token.txt` | Bedingt | Klartextdatei ohne Rechteprüfung (S-04). |
| `GLM_REFRESH_TOKEN` | `""` | leer | Nicht als Default | Bei Einzelaccount wird zusätzlich ein Guest-Fallback angelegt; Betrieb kann dadurch unerwartet zwei Konten verwenden. |
| `GLM_USE_GUEST_REFRESH_TOKEN` | `false` | `false` | Ja | Kein Token führt weiterhin automatisch zu Gastmodus. |
| `GLM_BASE_URL` | `https://chatglm.cn/chatglm` | identisch | Default ja | `http://` bleibt erlaubt (S-16). |
| `GLM_ASSISTANT_ID` | `65940acff94777010aa6b796` | identisch | Ja | Upstream-spezifisch, keine lokale Resourcegrenze. |
| `GLM_IMAGE_ASSISTANT_ID` | `65a232c082ff90a2ad2f15e2` | identisch | Ja | Upstream-spezifisch. |
| `GLM_IMAGE_MODEL_NAME` | `glm-image-1` | `glm-image-1` | Ja | In beiden Betriebsdateien fehlt der Key; Code fällt still auf Default zurück. |
| `GLM_USER_AGENT` | Chrome/143-Browser-UA | identisch | Ja | Keine Validierung; nicht sicherheitsrelevant, solange vertrauenswürdig konfiguriert. |
| `GLM_DELETE_CONVERSATION` | `true` | `true` | Ja | Cleanup ist sinnvoll, kann aber Request-Latenz verlängern. |
| `GLM_PERSISTENT_CONVERSATION` | `false` | `false` | Ja | Statelesser Default vermeidet globale Session-Kontamination. |
| `GLM_CONVERSATION_FILE` | `conversation.txt` | `conversation.txt` | Bedingt | In Betriebsdateien nicht dokumentiert; nur bei Persistenz relevant, Dateirechte fehlen. |
| `GLM_CONVERSATION_ID` | `""` | leer | Bedingt | Explizite ID kann bei Aktivierung Session-/Ownership-Risiken verstärken; nicht in Betriebsdateien. |
| `GLM_MAX_CONCURRENCY` | `3` | `100` | **Default bedingt, Vorlage riskant** | Code-/Vorlagen-Drift; keine Obergrenze, Gastkonten/Pool-Amplifikation (S-14). |
| `GLM_QUEUE_WAIT_TIMEOUT_SECONDS` | `600` | `600` | **Allein zu lang** | 10 Minuten plus Retries; zusammen mit unbeschränktem Ingress gefährlich (S-01/S-14). |
| `GLM_BUSY_MAX_RETRIES` | `30` | `30` | Bedingt | Hohe Latenz, keine Negativ-/Obergrenzenprüfung (S-15). |
| `GLM_BUSY_RETRY_INTERVAL_SECONDS` | `2.0` | `2` | Bedingt | Festes Intervall ohne Jitter/Backoff; `NaN/Inf` nicht abgewiesen. |
| `GLM_GUEST_MAX_RETRIES` | `3` | `3` | Bedingt | Betriebsvorlage `10`; erhöht Gastlast und Latenz (S-14). |
| `GLM_STREAM_ERROR_MAX_RETRIES` | `2` | `2` | Ja | Begrenzt, aber nach sichtbarem Content nicht retry-fähig; Streamabschluss bleibt problematisch (S-08). |
| `GLM_STREAM_ERROR_RETRY_INTERVAL_SECONDS` | `1.0` | `1` | Ja | Kein Jitter; als Einzelbudget unkritisch. |
| `GLM_EMPTY_RESPONSE_MAX_RETRIES` | `2` | `2` | Ja | Sinnvolle Obergrenze; fehlt in Betriebsdateien. |
| `GLM_HISTORY_MAX_CHARS` | `120000` | `120000` | Bedingt sinnvoll | Ungefähres Zeichen-, nicht Gesamt-Tokenbudget; `0` wird bei 10040 intern wieder aktiviert. |
| `GLM_BLOCKED_TOOL_FOLLOW_UPS` | `2` | `2` | Begrenzt, aber semantisch riskant | Nachfolgerunde kann in eine Text-Fallbackantwort enden (S-10). |
| `BLOCKED_TOOL_NAMES` | `()` | Liste mit URL-/Browser-/Sandboxnamen | Beispiel ja | Native Namen werden immer zusätzlich blockiert; Code-Default und Beispiel sind absichtlich unterschiedlich, aber nicht transparent. |

**Vorlagen-/Betriebsdrift:** `glm2api.env` und die geprüfte `.env` enthalten nicht `GLM_IMAGE_MODEL_NAME`, `GLM_CONVERSATION_FILE`, `GLM_CONVERSATION_ID`, `GLM_EMPTY_RESPONSE_MAX_RETRIES`, `GLM_HISTORY_MAX_CHARS` und `GLM_BLOCKED_TOOL_FOLLOW_UPS`. Dadurch werden diese sechs Werte nicht aus der Betriebsdatei sichtbar, sondern still vom Code gesetzt. Zusätzlich weicht die Betriebsvorlage bei Port, Debug-Modus, Concurrency und Guest-Retries von `.env.example` ab. Die Variable `GLM_REFRESH_TOKEN` ist in der Betriebsdatei belegt; ihr Wert wurde nicht in diesen Bericht übernommen.

## Positiv

- **Routing:** `server.py:156-195`, `226-236` und `255-265` trennen Chat, Anthropic Messages und Responses. Bei einem echten JSON-Boolean wird der jeweilige Streampfad beziehungsweise Non-Stream-Pfad korrekt gewählt; es wurde keine generelle Stream-/Non-Stream-Verwechslung im Dispatch gefunden.
- **Standard-Tool-Deklarationen:** Normale Anthropic- und Responses-Function-Tools werden in `anthropic_adapter.py:155-171` und `responses_adapter.py:153-175` in das interne `tools`-Feld überführt. `GLMWebClient._resolve_tools()` filtert sie, und `convert_messages()` erzeugt daraus Schemas und Tool-Instruktionen. Ein lokaler Fake-Client bestätigte für beide Endpunkte den Erhalt des Toolnamens `foo` im weitergeleiteten Payload.
- **Strukturierte Standardantworten:** Bei einem normalen OpenAI-Resultat wird ein Tool-Call im Chatpfad als `message.tool_calls` weitergereicht und von den Adaptern als Anthropic `tool_use` beziehungsweise Responses `function_call` strukturiert ausgegeben. Die Kernkonvertierung stringifiziert einen gültigen Tool-Call nicht absichtlich zu Text.
- **Erfolgreiche SSE-Terminierung:** Der gemeinsame Adapter-Loop sendet Heartbeats, explizite Fehler-Events und bei einem expliziten Mid-Stream-Exception-Fall keine terminalen Completed-Events. Das ist eine Verbesserung, ersetzt aber nicht die fehlende Upstream-EOF-Erkennung aus S-08.
- **Doppel-Logging behoben:** `load_config()` erzeugt den Bootstrap-Handler in `config.py:212-217`; `setup_logging()` entfernt ihn in `logging_utils.py:170-176`. `tests/test_config.py` bestätigt diesen Regressionstest.
- **Server-Version:** `server.py:13` und `server.py:60` beziehen den Wert aus `__version__`; `__init__.py` und `pyproject.toml` stehen beide auf `0.1.0`. Nur der zusätzliche Python-String bleibt als S-17.
- **Modellvarianten:** `model_variants.py:12-46` ist deterministisch, entfernt nur bekannte `think`-/ `search`-Suffixe und schließt Image-/CogView-Varianten korrekt vom Alias-Ausbau aus.

## Geprüft und unauffällig

- `main.py` ist ein korrekter, minimaler Entry-Point mit `SystemExit(main())`.
- `__main__.py:10-34` behandelt Config-/Startup-Fehler, KeyboardInterrupt und unerwartete Exceptions mit getrennten Returncodes; `Application.run()` finalisiert den Server in `app.py:54-65`.
- `GLM2APIServer.shutdown()` schließt Listener; `Application.stop()` ist im Erfolgspfad idempotent.
- JSON-Antworten setzen Content-Length und einen expliziten Content-Type; SSE-Antworten schließen die Verbindung. Diese positiven Punkte beseitigen die frühzeitigen Body-/Lifecycle-Probleme aus S-01 und S-09 nicht.
- Die Entry-Point- und Modellvarianten-Dateien enthalten keine eigenständige Routing- oder Tool-Deklarationsentscheidung.
- Der historische Befund zum doppelten Logging ist im aktuellen Code und im ausgeführten Regressionstest nicht mehr reproduzierbar.

## Verifikation

- `uv run pytest tests/test_config.py -q` → **3 passed**.
- `uv run pytest tests/ -q` → **150 passed**.
- Read-only AST-/Config-Abgleich: 31 Codevariablen, 0 fehlend in `.env.example`; sechs fehlende Keys in beiden Betriebsdateien.
- Lokale Fake-Upstream-Tests ohne Netzwerk: abrupter `/v1/messages`-Stream erzeugte `message_stop`; abrupter Chat-Stream erzeugte `[DONE]`; Upstream-Timeout erzeugte `[DONE]`, jeweils ohne Error-Event. Diese Beobachtungen belegen S-05/S-08.
- Read-only `stat`-Prüfung: `.env`, `.env.example` und Logdateien `0666`, Logverzeichnis `0777`; keine Loginhalte ausgegeben.
- Es wurden keine Projektdateien geändert. Im `pyproject.toml` ist kein Lint- oder Typecheck-Skript konfiguriert.
