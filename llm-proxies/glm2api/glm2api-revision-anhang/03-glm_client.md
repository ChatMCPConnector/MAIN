# 03 — glm_client.py

(Scope: **1.336 Zeilen**, vollständig mit `Read` in den Chunks 1–200, 201–400, 401–600, 601–800, 801–1000, 1001–1200 und 1201–1336 gelesen. Keine Codeänderungen vorgenommen.)

## Befunde

### C-01 — Kritisch: Queue-Ghost-Ticket blockiert die gesamte Ausführungsqueue (I-001)

**Ort:** `glm_client.py:85-121`

`ConcurrentRequestQueue.acquire()` vergibt eine monoton steigende Ticketnummer. Bei einem Queue-Timeout wird die Ticketnummer weder als abgebrochen markiert noch über `_released_tickets` freigegeben. `_release()` kann `_serving_ticket` deshalb nicht über diese Lücke hinwegbewegen.

**Auswirkung:** Ein einzelner Timeout blockiert nach Abschluss der vorherigen Tickets alle nachfolgenden Chat-, Image- und SSE-Anfragen. Ein In-Memory-Test bestätigte: Ticket 1 läuft in den Timeout, Ticket 2 bleibt auch nach dem Release von Ticket 0 dauerhaft blockiert.

**Empfehlung:** Timeout-Tickets unter derselben `Condition` atomar als abandoned markieren und die Sequenz vorantreiben oder eine Queue mit explizit entfernten/aktiven Tickets verwenden.

### C-02 — Hoch: Attachment- und Image-URLs erlauben SSRF und lokalen Dateileser (I-003)

**Ort:** `glm_client.py:1061-1067`, `glm_client.py:1126-1227`

`_fetch_file_payload()` reicht beliebige Nicht-`data:`-URLs ungeprüft an `urllib.request.urlopen()` weiter. Es gibt keine Schema-Allowlist, keine DNS-/IP-Prüfung, keine Redirect-Policy und keinen Schutz vor Loopback, Link-Local, RFC1918, Cloud-Metadata oder `file:`-URLs. Der `file:`-Handler von `urllib` ist nachweislich erreichbar. `data:`-URLs umgehen außerdem das 100-MB-Limit, weil die Größenprüfung nur im Remote-Zweig stattfindet. `_download_image_as_base64()` verwendet ebenfalls eine ungeprüfte Upstream-URL und begrenzt den gelesenen Image-Body nicht.

**Auswirkung:** Ein Client kann interne Dienste oder erreichbare lokale Dateien abrufen und deren Inhalt an den GLM-Upstream senden. Ein nicht limitierter Body kann außerdem Speicher- und Netzwerkressourcen erschöpfen.

**Empfehlung:** Nur kontrollierte HTTP(S)-Quellen zulassen, alle anderen Schemata ablehnen, DNS/IP nach jeder Auflösung und jedem Redirect gegen private/reservierte Netze prüfen sowie Content-Length, Stream-Bytes, Dateianzahl und Gesamtgröße begrenzen.

### C-03 — Hoch: Persistente/clientgelieferte Conversation ist global und nicht mandantenfähig (I-004)

**Ort:** `glm_client.py:207-230`, `glm_client.py:655-657`, `glm_client.py:767-779`, `glm_client.py:850-853`

Alle Requests desselben `GLMWebClient` teilen bei aktivierter Persistenz genau eine `_persistent_conversation_id`. Der Lock schützt nur den Zugriff auf den String, nicht die Verwendung der Conversation über die Request-Laufzeit. Zusätzlich wird ein frei geliefertes `conversation_id` ohne Ownership- oder Accountbindung akzeptiert. Ein 400/404 für eine solche ID setzt außerdem den globalen aktiven Zustand zurück, auch wenn die ID nur für den aktuellen Client/Request bestimmt war.

**Auswirkung:** Bei `GLM_PERSISTENT_CONVERSATION=true` können parallele oder aufeinanderfolgende Mandanten dieselbe Upstream-Historie verwenden. Last-Writer-Wins-Rennen, ein fremder Reset und wechselnde Ticket-Accounts können Kontext voneinander erzeugen, verlieren oder in den falschen Account verschieben.

**Empfehlung:** Stateless als sicheren Default beibehalten. Persistenz nur als serverseitig verwaltete Session-ID pro authentifiziertem Mandanten mit Accountbindung und atomarer Request-Zuordnung; clientgelieferte IDs niemals als Eigentumsnachweis verwenden.

### C-04 — Hoch: Refresh-Token-Rennen können Tokens überschreiben (I-006)

**Ort:** `glm_client.py:265`, `glm_client.py:429`, `glm_client.py:1311-1312`; nachgelagerte Ursache in `glm_auth.py:162-225` und `glm_auth.py:267-312`

Mehrere gleichzeitige Requests können für dasselbe Konto parallel `get_access_token_for_account()` aufrufen. Der Cache-Lookup ist gelockt, der eigentliche Refresh und die anschließende Persistierung aber nicht als Single-Flight pro Konto serialisiert. Zwei Refreshes können unterschiedliche rotierte Refresh-Tokens erhalten; der spätere Datei-Write kann den neueren Token wieder überschreiben.

**Auswirkung:** Ein Konto kann trotz scheinbar erfolgreicher Requests dauerhaft invalidiert werden, auf ein anderes Konto ausweichen oder bei einem Neustart einen veralteten Token verwenden. Guest-Accounts erzeugen unter Umständen redundant neue Tokens.

**Empfehlung:** Pro Konto eine Condition/Single-Flight-Refresh-Sperre, versionierte Refresh-Tokens und atomare Read-Modify-Write-Persistenz verwenden; Guest-Refreshes ebenfalls zentral koordinieren.

### C-05 — Hoch: Failover behandelt deterministische Fehler wie Kontofehler und ist nicht an Conversation/Account gebunden

**Ort:** `glm_client.py:835-862`, `glm_client.py:1294-1331`, `glm_client.py:655-713`

`send_request()` verpackt praktisch jeden HTTP-Fehler in `UpstreamAPIError` mit `status_code`. `should_switch_account()` behandelt wiederum jedes Objekt mit `status_code` als account-spezifischen Fehler. Ein deterministischer 400/404/422 für Request oder Conversation wird dadurch auf allen Konten wiederholt, invalidiert deren Access-Token und verschiebt den globalen Accountzyklus.

Die Closure verwendet außerdem ein unveränderliches `target_conv_id` für jeden Account. Bei einem Failover wird dieselbe Conversation-ID auf einem anderen Konto versucht, obwohl die ID weder validiert noch an den erfolgreichen Account gebunden ist. Ein Midstream-Retry ruft `_open_chat_stream()` erneut mit demselben Ticket-Account auf; eine echte Midstream-Accountrotation findet nicht statt.

**Auswirkung:** Deterministische Fehler werden vervielfacht, Token-Caches unnötig invalidiert und Conversation-Kontext kann beim Kontowechsel fehlen, beim falschen Konto weiterlaufen oder in einen 400/404-Zyklus geraten.

**Empfehlung:** Fehlerklassen nach 401/403, Auth-/Netzwerkfehlern, Rate-Limit und deterministischen 4xx trennen. Conversation-IDs an den erzeugenden Account binden; bei 400/404 nicht blind auf andere Konten ausweichen; für Midstream-Retries eine explizite Accountrotation mit sicherem Kontextwechsel implementieren.

### C-06 — Hoch: Abgeschnittene oder ungültige SSE-Streams werden als Erfolg finalisiert (I-007)

**Ort:** `glm_client.py:289-350`, `glm_client.py:446-487`, `glm_client.py:1069-1124`, `glm_client.py:375-400`

`_iter_sse_events()` fängt `IncompleteRead`, verarbeitet die Teilbytes und beendet sich anschließend wie ein normales EOF. Es gibt kein Signal an `chat_completion()` oder `stream_chat_completion()`, dass der Stream unvollständig war. Ungültige JSON-SSE-Blöcke werden mit `return None` verworfen. Der inkrementelle UTF-8-Decoder verwendet außerdem `errors="ignore"`, wodurch fehlerhafte Bytestellen still verschwinden können.

Ohne Top-Level-`finish` wird im Non-Stream-Pfad `build_response()` und im Stream-Pfad `finalize(status="stop")` verwendet. `[DONE]` wird zwar erkannt, aber ein fehlendes `[DONE]`/Finish wird nicht als Fehlerzustand unterschieden. Der Image-Pfad prüft ebenfalls weder `_raise_for_event_error()` noch einen zwingenden Finish-Status.

**Auswirkung:** Ein mitten in Tool-Call-Parametern abgebrochener Stream kann als `stop` mit bereinigtem oder fehlendem Text, unvollständigem Call oder gar ohne Call erscheinen. Der Client glaubt, die Runde sei erfolgreich; genau daraus kann ein Toolcall als Antwort bzw. ein verlorener Toolcall entstehen.

**Empfehlung:** Eine explizite Stream-Terminierungszustandsmaschine einführen: EOF ohne gültiges Finish/`[DONE]` ist `truncated_stream`; unparsebare Events sind Fehler oder mindestens retrybare Fehlertokens, niemals still verworfene Events. Nur ein tatsächlich vollständiges Ende darf `stop`/`tool_calls` erzeugen.

### C-07 — Hoch: Transportfehler und JSON-Upstreamfehler umgehen den Stream-Retry

**Ort:** `glm_client.py:289-299`, `glm_client.py:446-460`, `glm_client.py:835-853`, `glm_client.py:952-965`, `glm_client.py:1089-1097`

Der Controller setzt `retry_exc` nur bei einem von `_raise_for_event_error()` erkannten SSE-Event. `ConnectionResetError`, `RemoteDisconnected`, `TimeoutError`, `OSError` und Gzip-Lesfehler aus `response.read()` werden nicht in diese Retry-Zustandsmaschine überführt; sie brechen den Generator ab. In einem In-Memory-Test löste ein `ConnectionResetError` genau einen Öffnungsversuch und keinen Retry aus.

Zusätzlich erzeugen `send_request()` und `_prepare_chat_response()` `UpstreamAPIError` aus HTTP-/JSON-Antworten ohne `transient`-Kennzeichnung. Ein transienter Code im Response-Body wird daher nicht vom Stream-Retry-Mechanismus erkannt.

**Auswirkung:** Ein Abbruch während eines Tool-Call-Fragments oder unmittelbar vor dem Finish kann ohne Recovery als harter Streamfehler enden; ein transienter HTTP/JSON-Fallback wird je nach Account nur failover-artig behandelt.

**Empfehlung:** Transport- und Gzip-Exceptions in eine eigene Fehlerklasse überführen, vor clientseitigem Abbruch klassifizieren und denselben `served_content`-Checkpoint verwenden. Die Transient-Erkennung für HTTP- und JSON-Payloads zentralisieren, nicht nur in SSE-Events.

### C-08 — Mittel: `served_content` ist eine Byte-/Feld-Heuristik und zählt Reasoning nicht

**Ort:** `glm_client.py:441-475`, `glm_client.py:551-569`

Ein Chunk gilt nur dann als sichtbar, wenn er `"content"` enthält und nicht gleichzeitig `"reasoning_content"` enthält. Der Accumulator streamt Reasoning jedoch als sichtbaren SSE-Delta. Ein transienter Fehler nach bereits gesendetem Reasoning startet deshalb erneut, obwohl bereits Output an den Client gegangen ist. Umgekehrt kann sichtbarer Text, dessen serialisierter Inhalt zufällig den String `reasoning_content` enthält, nicht als gesendet erkannt werden.

**Auswirkung:** Reasoning kann dupliziert werden; im ungünstigen Fall kann ein Retry nach für den Client bereits sichtbarem Content ausgelöst werden. Das ist kein direkter Tool-Call-Duplikatpfad, weil Tool-Calls bis `finalize()` gepuffert werden, aber die Retry-Grenze ist strukturell unzuverlässig.

**Empfehlung:** Jeden Delta strukturell parsen und jeden client-sichtbaren Outputtyp (Content, Reasoning, Calls) separat verfolgen; den State nicht über Byte-Substrings oder den Feldnamen `reasoning_content` bestimmen. Nach bereits gesendetem Output eine explizite Continuation-/Fehlerstrategie verwenden.

### C-09 — Hoch: Leere oder vollständig blockierte Toollisten werden zu einer Wildcard-Allowlist (I-009)

**Ort:** `glm_client.py:232-249`, `glm_client.py:718-748`, `glm_client.py:270-279`, `glm_client.py:416-425`

`_resolve_tools()` liefert bei einer leeren oder vollständig gefilterten Toolliste `filtered_tools=None` und `allowed_tool_names=None`. Downstream bedeutet `None` nicht „keine erlaubten Tools“, sondern „keine Allowlist“: Native Tool-Calls werden dann nicht nach einem Allow-Set geprüft, und die Mapping-Helfer können `open`/Sandbox-Calls auf `bash`, `read` oder `webfetch` abbilden. Die Blockliste wird überwiegend case-sensitiv verglichen.

Ein In-Memory-Test mit nur einem blockierten `foo`-Tool und einem nativen `bar`-Call lieferte `bar` als strukturierten Toolcall. Auch `OPEN_URL` umging die case-sensitive Blockierung.

**Auswirkung:** Ein Request ohne deklarierte Tools oder mit ausschließlich blockierten Tools kann beliebige bzw. native Calls an den Client weiterreichen. Das kann unbeabsichtigte Tool-Ausführung, Datenverlust oder eine falsche Antwort erzeugen.

**Empfehlung:** „Keine Tools“, „alle Tools blockiert“ und „nicht deklarriert“ als getrennte Zustände modellieren. Für Client-Calls standardmäßig eine leere Allowlist verwenden, Wildcard-Mapping entfernen und Namen vor allen Vergleichen kanonisieren.

### C-10 — Hoch: Historische Tool-Calls werden bei leerer Allowlist nicht herausgefiltert

**Ort:** `glm_client.py:732-748`

`_open_chat_stream()` übergibt bei fehlenden oder vollständig blockierten Tools `filtered_tools=None` an `convert_messages()`. Im Translator bleibt die berechnete Namensmenge dadurch leer; die Bedingung, historische Assistant-Calls zu verwerfen, ist bei einer leeren Menge aber nicht aktiv. Ein vorheriger `open_url`-Call aus der Historie landet dadurch wieder im Prompt, obwohl kein Tool dafür erlaubt ist.

Ein In-Memory-Test bestätigte, dass ein historischer `open_url`-Call bei `tools=None` im konvertierten Prompt enthalten bleibt.

**Auswirkung:** Der Upstream erhält gerade die blockierte Tool-Historie, die durch die negative Follow-up-Logik vermieden werden soll. Das kann blockierte Calls und Tool-Limits erneut auslösen.

**Empfehlung:** Historische Calls unabhängig von einer leeren Toolmenge strikt filtern. Für jeden Assistant-Call den Zielnamen gegen die tatsächlich deklarierte Allowlist prüfen; unbekannte Calls und zugehörige Results aus dem Prompt entfernen.

### C-11 — Hoch: Ein gültiger Call neben einem blockierten Call geht beim Follow-up verloren

**Ort:** `glm_client.py:131-172`, `glm_client.py:300-347`, `glm_client.py:478-524`

Der Client entscheidet die Follow-up-Runde anhand von `blocked_tool_attempt_names`, bevor er die bereits erzeugten `finalize_chunks` bzw. `result` ausgibt. Im Stream-Pfad werden die Chunks in `glm_client.py:497-524` bei aktivem Follow-up nicht ausgegeben; im Non-Stream-Pfad wird `result` in `glm_client.py:328-347` verworfen. Enthielt derselbe Upstream-Turn einen gültigen `read`-Call und danach einen nativen `open_url`-Call, wurde in einem In-Memory-Test der gültige Read-Call nicht ausgeliefert, sondern nur die Folgeantwort.

Bei einem Text-JSON mit erlaubtem und blockiertem Call wird der blockierte Call vom Parser dagegen oft verworfen, ohne in `blocked_tool_attempt_names` aufzutauchen, sobald der erlaubte Call existiert. Die negative Rückmeldung bleibt dann aus. Zusätzlich wird in `chat_completion()` der von `consume_event()` zurückgegebene Status (`"intervene"`) ignoriert; nur der vorher gelesene Top-Level-Status wird geprüft.

**Auswirkung:** Gültige Tool-Calls können verloren gehen oder in eine unerwartete Folgeaktion umgewandelt werden. Das ist ein direkter Verlust-/Duplikationspfad an der Client-Accumulator-Schnittstelle.

**Empfehlung:** Erlaubte und blockierte Calls getrennt bilanzieren. Gültige Calls vor einer negativen Folgeaktion ausgeben oder die Runde unverändert weiterreichen; `blocked`-Status immer aus dem Rückgabewert von `consume_event()` übernehmen und niemals einen bereits aufgebauten Call verwerfen.

### C-12 — Hoch: Follow-up-Kontext geht bei einem Retry der Follow-up-Runde verloren

**Ort:** `glm_client.py:328-366`, `glm_client.py:497-569`, `glm_client.py:131-172`

`follow_up` wird nur für den unmittelbar nächsten `_open_chat_stream()`-Aufruf verwendet. Wird diese Follow-up-Runde anschließend leer oder transient fehlerhaft, verwendet der Empty-Retry beziehungsweise der Transient-Retry wieder das ursprüngliche `payload` (`glm_client.py:546` und `glm_client.py:569`, Non-Stream analog `glm_client.py:326`/`366`). Die negative Tool-Rückmeldung aus `follow_up` ist dann nicht mehr Teil des Requests.

Ein In-Memory-Test mit blockiertem Tool, anschließend leerer Follow-up-Runde und drittem Versuch zeigte, dass die dritte Anfrage die Follow-up-Anweisung nicht enthielt.

**Auswirkung:** Der Retry kann exakt den ursprünglichen blockierten Call erneut auslösen. Die kontextabhängige Korrektur wird verworfen, obwohl der Client bereits einen Follow-up-Budgetzähler erhöht hat.

**Empfehlung:** Einen `active_payload` für die aktuelle Runde führen und bei allen weiteren Retries verwenden; das ursprüngliche Payload nur als Basis für die Historie behalten. Follow-up-Hinweise außerdem nur für tatsächlich erlaubte Tools formulieren.

### C-13 — Mittel: Signatur-Dedup unterdrückt legitime wiederholte Native-Calls

**Ort:** `glm_client.py:260-262`, `glm_client.py:410-412`; Filterlogik in `translator.py:1133-1164`

Die aus der gesamten Request-Historie extrahierten Signaturen werden für den Accumulator verwendet. Ein aktueller nativer Call mit gleichem Namen und gleichen Argumenten wird dadurch als Echo verworfen, auch wenn er eine neue, gewollte Wiederholung ist. Die zusätzliche Signatur-Deduplizierung kollabiert auch mehrere identische Calls innerhalb desselben Turns; eine fehlende `tool_id` führt ebenfalls zum stillen Verwerfen.

**Auswirkung:** Ein erneutes `read`/`bash` mit identischen Argumenten oder zwei bewusst identische Calls können verschwinden. Der Agent erhält dann keinen Call und interpretiert die Runde als abgeschlossen.

**Empfehlung:** Echo-Unterdrückung auf nachweislich gespiegelte IDs/Upstream-Echo-Metadaten begrenzen. Aktuelle Call-IDs bzw. Turn-Sequenzen berücksichtigen und Calls ohne ID explizit repararieren oder als Fehler melden, nicht still verwerfen.

### C-14 — Hoch: Streaming-Generator hält Lease und Socket vor dem ersten `yield`

**Ort:** `glm_client.py:427-434`, `glm_client.py:571-584`

`stream_chat_completion()` öffnet den Upstream und reserviert den Queue-Slot, bevor der zurückgegebene Generator gestartet wird. Die Cleanup-Blöcke liegen in `wrapped()`/`generate()` und laufen bei einem noch nicht gestarteten Generator nicht beim Aufrufen von `.close()`.

Ein In-Memory-Test bestätigte: Generator erzeugen, sofort schließen — Response bleibt offen und der Lease bleibt nicht freigegeben.

**Auswirkung:** Ein früh abgebrochener, verworfener oder nie konsumierter Client-Stream kann einen Queue-Slot und eine Upstream-Verbindung bis zum nicht-deterministischen GC halten. Bei vielen solchen Requests blockiert die Queue.

**Empfehlung:** Lease und Upstream erst beim ersten Generator-`next()` öffnen oder einen explizit schließbaren Context-Manager zurückgeben. Jeder Abbruchpfad muss `close()`/Abbruchsignal garantieren; Cleanup nicht von der zufälligen Generator-Finalisierung abhängig machen.

### C-15 — Mittel: Conversation-Cleanup ist weder attempt- noch accountgebunden

**Ort:** `glm_client.py:318-371`, `glm_client.py:538-581`, `glm_client.py:655-713`

Bei Transient-Retry, Empty-Retry und Follow-up wird der alte Accumulator verworfen. Seine bereits erhaltene `conversation_id` wird nicht an `delete_conversation()` übergeben; übrig bleibt nur der letzte Accumulator. Im Finally wird außerdem kein Accountindex des erzeugenden Requests an die Löschung weitergegeben. `_call_with_account_failover()` startet standardmäßig am aktuell globalen Account, der nicht der Ticket-Account des Chats sein muss.

Ein In-Memory-Test mit `old`/`new` Conversation-IDs zeigte, dass nur `new` gelöscht wurde. Löschfehler werden verschluckt, während der Lease während der potenziell langen Löschanfrage gehalten wird.

**Auswirkung:** Retry-Runden hinterlassen serverseitige Conversations; die letzte Conversation kann am falschen Konto gelöscht werden. Das erzeugt Speicher-/Contextlecks und verlängert die Zeit, in der ein Queue-Slot belegt ist.

**Empfehlung:** Pro Versuch Response, Conversation-ID, Assistant-ID und Accountindex zurückgeben; jede abgebrochene Conversation am selben Account best-effort löschen. Cleanup mit Timeout/Worker ausführen und den Lease nicht für beliebig lange Cleanup-Netzwerkaufrufe halten.

### C-16 — Hoch: Mehrere Upstream-Response-Pfade schließen die rohe Verbindung nicht

**Ort:** `glm_client.py:367-368`, `glm_client.py:952-969`, `glm_client.py:1238-1242`

Im JSON-Zweig von `_prepare_chat_response()` wird die originale HTTP-Response gelesen, aber nicht geschlossen; danach wird ein neuer `BufferedReader` über `BytesIO` zurückgegeben. Im Gzip-Zweig wird `gzip.GzipFile(fileobj=response)` erzeugt. `GzipFile.close()` schließt einen extern übergebenen `fileobj` nicht zuverlässig; ein In-Memory-Test mit `BytesIO` bestätigte, dass der zugrunde liegende Stream danach offen war. Die Caller schließen nur den Wrapper.

**Auswirkung:** HTTP-Sockets/File-Descriptors können über viele Requests akkumulieren, wodurch Upstream-Verbindungen, Threads und Queue-Slots indirekt belastet werden.

**Empfehlung:** Den roten Response-Besitz klar an einen Wrapper übergeben und im `finally` sowohl Wrapper als auch Raw-Response schließen. JSON-Bodies in einem eigenen Kontext kopieren und den Originalresponse vor jeder Rückgabe/Ausnahme schließen.

### C-17 — Hoch: Debug-Dumps legen Access-Tokens und vollständige Inhalte in Logs (I-005)

**Ort:** `glm_client.py:826-834`, `glm_client.py:932-943`, `glm_client.py:1158-1195`

Bei `DEBUG_DUMP_ALL=true` werden `dict(request.header_items())` für Chat, Image und File-Upload geloggt. Das enthält den `Authorization`-Bearer. Zusätzlich werden Rohtext, Prompts, Tool-Argumente, Request-Bodies und Binär-/Attachment-Inhalte geloggt; `debug_dump()` redigiert nichts.

**Auswirkung:** Ein Debug-Start kann Access-Tokens, API-Daten, private Dateien und signierte URLs in Konsole und rotierende Logdateien kopieren. Damit ist der Debug-Modus ein Secret- und Datenschutzleck.

**Empfehlung:** Header auf eine Allowlist reduzieren und Authorization, Cookies, API-Keys, Query-Secrets sowie signierte URLs konsequent redigieren; Binärinhalt nur als Hash/Metadaten loggen.

### C-18 — Hoch: `max_tokens`/`temperature` und weitere API-Parameter werden nicht upstream durchgesetzt (I-015)

**Ort:** `glm_client.py:716-798`

`_open_chat_stream()` baut den Upstream-Body ausschließlich aus Assistant-, Conversation-, Messages- und Meta-Feldern. `max_tokens`, `temperature`, `top_p`, Stop-Sequenzen und verwandte Felder aus dem internen Payload werden nicht übernommen. Die Adapter reichen diese Felder zwar weiter, der Client verwendet sie aber nicht.

**Auswirkung:** Clients können ihr Ausgabelimit und Sampling nicht durchsetzen. Upstream kann länger laufen als angefordert; bei einem Upstream-Limit kann ein Tool-Call mitten in den Argumenten abgeschnitten werden. Die geschätzten Usage-Werte im Accumulator sind ebenfalls nicht belastbar.

**Empfehlung:** Unterstützte Felder explizit upstream abbilden oder kontrolliert mit 400 ablehnen. Bei nicht unterstützten Feldern dürfen insbesondere `max_tokens` und `temperature` nicht stillschweigend ignoriert werden.

### C-19 — Mittel: Attachment-Upload ist nicht mit Chat-Account und Retry-Runde verbunden

**Ort:** `glm_client.py:732-753`, `glm_client.py:1126-1209`

`_open_chat_stream()` ruft `_upload_referenced_files()` bei jedem Erstversuch, Retry und Follow-up erneut auf und scannt dabei die ursprünglichen, nicht die komprimierten Messages. Jeder Upload verwendet `_call_with_account_failover()` ohne den Ticket-Account, während der Chat mit einem anderen bevorzugten Konto laufen kann. Uploadfehler werden pro Referenz verschluckt und als fehlende Referenz weitergereicht.

**Auswirkung:** Ein Retry kann ein Attachment erneut von einer geänderten oder abgelaufenen URL laden; Upload und Chat können auf verschiedenen Konten laufen, sodass `source_id`/Datei-URL im Chat ungültig sind. Das kann Datei-/Pfadaufgaben scheitern lassen, obwohl der Client einen erfolgreichen Request sieht. Historische Attachments werden trotz History-Kompression erneut verarbeitet.

**Empfehlung:** Referenzen einmal pro logischem Request materialisieren, an den Chat-Account binden und bei Accountwechsel explizit neu hochladen. Aktuellen komprimierten Message-Satz verwenden, Fehlschläge kontrolliert melden und Gesamtanzahl/-größe begrenzen.

### C-20 — Mittel: Upstream-Fehlerdetails und Fehler-Bodies werden unbegrenzt/ungefiltert weitergereicht (I-016)

**Ort:** `glm_client.py:621-625`, `glm_client.py:691-700`, `glm_client.py:1023-1027`, `glm_client.py:1244-1261`

`UpstreamAPIError` transportiert das komplette Event bzw. Fehler-Payload. Der HTTP-Server gibt `exc.payload` als `details` weiter. `_read_error_payload()` liest den kompletten `HTTPError`-Body und dekomprimiert Gzip ohne Größenlimit. Fehlertexte und Upstream-IDs/URLs können damit sowohl intern als auch nach außen sichtbar werden; ein fehlerhaftes oder gzip-bombenartiges Error-Body verursacht zusätzlichen Speicherdruck.

**Auswirkung:** Interne Upstream-Strukturen, signierte URLs oder Request-Metadaten können an Clients durchsickern; fehlerhafte Upstream-Responses können Ressourcen erschöpfen.

**Empfehlung:** Öffentliche Fehler auf stabile Meldung plus Correlation-ID reduzieren, Details nur redigiert intern loggen und Error-/Gzip-Bodies mit einem harten Byte-Limit lesen.

## Positiv

- Der normale, vollständig konsumierte Chat-/Stream-Pfad schließt die Response und gibt den Lease in `finally` frei; `QueueLease.release()` ist grundsätzlich idempotent.
- Modellierte SSE-Transientfehler (`10025`, `10040`, `10061`, `10062`) werden als `UpstreamAPIError.transient` klassifiziert; der Retry-Zähler ist als Erstversuch plus N Retries implementiert.
- Tool-Call-Fragmente werden vom `StreamingToolParser` bis `finalize()` zurückgehalten. Ein partieller JSON-Call wird daher nicht schon als Client-Toolcall ausgegeben, solange kein sichtbarer Prätext ausgegeben wurde.
- Nach normalem sichtbarem Content wird kein Retry gestartet; der bestehende `test_error_after_visible_content` prüft diese Doppel-/Retry-Vermeidung.
- Die kumulierte `\r\n`-Normalisierung in `glm_client.py:1100-1104` behandelt einen über die 4096-Byte-Grenze getrennten CRLF-Paar korrekt. `[DONE]` und ein abschließender Pending-Block werden grundsätzlich erkannt.
- Bei einer nichtleeren Toolliste werden erlaubte Tools normalerweise beibehalten und konfigurierte/native Blocklistennamen aus dem Prompt entfernt.
- Die Follow-up-Anweisung ist aktuell in `_build_blocked_tool_follow_up_payload()` zentralisiert und wird nur einmal als Textbaustein erzeugt. U-03 ist damit im aktuellen Source behoben; es gibt keine zweite duplizierte Builder-Funktion mehr.
- Die Historie-Signatur-Extraktion wird im aktuellen Chat-Pfad nur einmal pro Request berechnet und an die Retry-Accumulatoren weitergereicht.

## Geprüft und unauffällig

- `chat_completion()` und `stream_chat_completion()` lösen die Tools zu Requestbeginn einmal auf und geben das Ergebnis an Folge-Öffnungen weiter; nur der defensive `None`-Zweig in `_open_chat_stream()` löst denselben Input nochmals auf, statt eine neue Filterentscheidung zu treffen.
- `_halve_history_budget()` setzt den reduzierten Budgetwert als internes Payload-Feld und wird im Retrypfad für die nächste `_open_chat_stream()`-Runde verwendet.
- `delete_conversation()` überspringt das Löschen im expliziten Persistent-Modus grundsätzlich; das ist als bewusste Lebensdauerentscheidung nachvollziehbar, deckt aber nicht die oben genannten Account-/Attempt-Bindungsfehler.
- `QueueLease.release()` verhindert mehrfaches Freigeben derselben Lease; der Gap entsteht ausschließlich vor der Lease-Erzeugung bei einem Queue-Timeout.
- Die vorhandenen Tests decken die üblichen Retry-, Follow-up-, CRLF- und `[DONE]`-Happy Paths ab. Sie decken jedoch weder Queue-Ghost-Tickets noch Netzwerk-Read-Exceptions, Follow-up-Retry-Payloads, gemischte erlaubte/blockierte Calls, vollständig blockierte Toollisten oder Cleanup bei accountgebundenen Conversations ab.

## Verifikation

- `uv run pytest tests/test_stream_retry.py -q`: **15 passed**.
- `uv run pytest -q`: **150 passed**.
- Read-only In-Memory-Probes bestätigten Queue-Ghost-Ticket, Wildcard-Allowlist, historische blocked Calls, gültigen Call neben blockiertem Native-Call, Follow-up-Payloadverlust, `ConnectionResetError` ohne Retry, ungestarteten Generator-lease sowie rohe JSON/Gzip-Response-Leaks.
- Im `pyproject.toml` ist kein Lint- oder Typecheck-Script definiert; es wurde deshalb kein nicht vorhandenes Kommando behauptet.
