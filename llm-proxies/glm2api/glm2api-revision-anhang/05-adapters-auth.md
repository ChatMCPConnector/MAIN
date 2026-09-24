# 05 — anthropic_adapter.py, responses_adapter.py, glm_auth.py, tool_protocol.py

(Scope: **1.633 Zeilen** vollständig mit `Read` in offset/limit-Chunks gelesen und Zeile für Zeile geprüft: `anthropic_adapter.py` 485, `responses_adapter.py` 638, `glm_auth.py` 325, `tool_protocol.py` 185. Integrationspfade in `server.py`, `glm_client.py`, `translator.py`, die aktuelle opencode-Konfiguration und `tests/test_protocol_adapters.py` wurden gezielt zur Verifikation herangezogen. Keine Codeänderung und kein GLM-/Account-Netzwerkaufruf.)

## Befunde

### A-01 — Hoch: Gemischte Anthropic-Inhalte mit `tool_result` verlieren Text, Bilder und Tool-Blöcke
**Ort:** anthropic_adapter.py:53-138, insbesondere 101-121

**Beschreibung:** Sobald in einer Nachricht mindestens ein `tool_result` vorhanden ist, gewinnt der `if tool_results:`-Zweig. Er hängt nur die Tool-Ergebnisse an und verwirft alle parallel gesammelten Text-/Bildanteile sowie sämtliche `tool_use`-Blöcke derselben Nachricht. Die ursprüngliche Blockreihenfolge geht ebenfalls verloren. Innerhalb eines `tool_result`-Arrays werden nur `text`-Blöcke extrahiert; Bild-/Dateiblöcke werden verworfen und `is_error` nicht abgebildet. Der In-Memory-Check mit `text="KEEP"`, einem Text-Result und einem Image-Result ergab ausschließlich `{"role":"tool", ... ,"content":"RESULT"}`.

**Auswirkung:** Ein nach einem Tool-Call mitgeschickter erklärender User-Text, ein Tool-Fehlerstatus oder multimodale Tool-Ausgaben verschwinden. Das Modell kann den ausgeführten Schritt nicht korrekt verstehen, denselben Call wiederholen oder eine Folgefrage falsch beantworten. Das ist ein direkter Tool-Runden-Datenverlust.

**Empfehlung:** Content-Blöcke in ihrer Reihenfolge in atomare OpenAI-Nachrichten expandieren: Text/Medien erhalten, jedes `tool_result` separat als `tool`-Nachricht ausgeben und `tool_use` nur in zulässigen Assistant-Nachrichten konvertieren. `is_error` als explizites internes Fehlerfeld erhalten; nicht unterstützte Modalitäten explizit ablehnen statt still zu entfernen. Leere/fehlende `tool_use_id` vor der Konvertierung validieren.

### A-02 — Hoch: Anthropic-Thinking-Blöcke werden ohne Signatur und redacted Inhalte vollständig zu gewöhnlichem Text
**Ort:** anthropic_adapter.py:66-70, anthropic_adapter.py:210-216

**Beschreibung:** Ein eingehender `thinking`-Block wird auf seinen Text reduziert; `signature` geht verloren. `redacted_thinking` wird gar nicht erkannt. Der Thinking-Text wird als normaler Rolleninhalt in die interne History geschrieben. Umgekehrt erzeugt der Adapter aus `reasoning_content` einen ausgehenden `thinking`-Block ohne das im Anthropic-Schema erforderliche `signature`-Feld. Damit kann er weder die Originalblockidentität noch die von Anthropic verlangte Signatur-/Reihenfolge-Integrität aufrechterhalten.

**Auswirkung:** Offizielle Anthropic-Clients können die Antwortvalidierung scheitern lassen oder die Thinking-Kette beim nächsten Request verlieren. Redacted Reasoning geht vollständig verloren. Ein vermeintlich signierter Thinking-Block ohne Signatur ist semantisch unzuverlässig.

**Empfehlung:** Thinking intern als eigenen signierten Blocktyp mit `signature`/`data` modellieren und redacted Blöcke unterstützen. Wenn GLM keine gültige Anthropic-Signatur liefert, keine erfundene Thinking-Signatur ausgeben: Reasoning entweder als neutralen Textkanal behandeln oder den nicht unterstützten Anthropic-Modus mit einem klaren 400 ablehnen. Blockreihenfolge beim History-Roundtrip erhalten.

### A-03 — Hoch (I-011 verifiziert): Anthropic-Streaming mischt Argumentdeltas mehrerer Tool-Calls
**Ort:** anthropic_adapter.py:383-416, anthropic_adapter.py:464-482

**Beschreibung:** `_pending_tool_calls` ist zwar pro OpenAI-Index, die tatsächlich emittierten `input_json_delta`-Events verwenden aber immer den globalen `content_index` des zuletzt geöffneten Anthropic-Blocks. Beim ersten Auftreten eines neuen Index wird der vorherige Block geschlossen. Ein späteres Delta für Index 0 nach Index 1 wird deshalb Index 1 zugeordnet. Der synthetische Stream mit Indexfolge `0, 1, 0` erzeugte die Anthropic-Delta-Indizes `[0, 1, 1]`. Auch Text/Reasoning zwischen zwei bekannten Tool-Indizes kann deren Deltas in einen Text- oder Thinking-Block schreiben.

**Auswirkung:** Bei gültigem parallelem oder interleavtem Chat-Completions-Streaming werden Argumentfragmente mehrerer Tools vermischt oder an falsche Blöcke gebunden. Das kann ungültige JSON-Argumente, falsche Tool-Ausführung oder verlorene Calls verursachen. Der aktuelle interne GLM-Translator emittiert Calls normalerweise sequenziell; der Adapter ist dennoch für den offenen OpenAI-Chat-Vertrag falsch.

**Empfehlung:** Pro Tool-Index dauerhaft Name, ID, kompletten Argumentpuffer und Zielstatus speichern. Da Anthropic Content-Blöcke sequenziell sind, interleavte Calls entweder bis zum Final-Chunk puffern und danach vollständig ausgeben oder vor jeder Emittierung in stabile Indexreihenfolge serialisieren. Niemals `content_index` unabhängig vom konkreten Tool-Index wählen.

### A-04 — Hoch: Ungültige OpenAI-Tool-Calls werden bei Anthropic zu leeren `tool_use`-Calls oder normalen Textantworten
**Ort:** anthropic_adapter.py:223-245

**Beschreibung:** Jede `tool_calls`-Liste setzt `stop_reason="tool_use"`, auch wenn sie leer ist. Ungültiges Argument-JSON wird still zu `{}`; der Adapter sendet dennoch einen ausführbaren `tool_use`-Block. Der Check `"{BROKEN"` wurde reproduzierbar zu `name="bash", input={}` und `stop_reason="tool_use"`. JSON-Arrays/-Skalare werden als `input` akzeptiert, obwohl Anthropic ein Objekt verlangt. Umgekehrt bleibt ein OpenAI-`finish_reason="tool_calls"` ohne Calls `end_turn`; ein falsches `function`-Shape kann zudem mit einem ungefangenen `AttributeError` enden.

**Auswirkung:** Ein `bash`-/`read`-Call kann mit leeren oder falschen Argumenten ausgeführt werden. Ein vorhandener, aber fehlerhafter Call wird als scheinbar fertiger Tool-Call getarnt. Fehlende Calls werden dagegen als normale Endantwort klassifiziert — genau die Fehlklassifikation „Toolcall als Antwort“ in umgekehrter Form.

**Empfehlung:** Vor der Antwortkonstruktion jeden Call gegen ein striktes Schema prüfen: nichtleere ID und Name, `function` als Dict, `arguments` als vollständiges JSON-Objekt. Parsefehler als expliziten Adapter-/Upstream-Fehler ausgeben, niemals `{}` erfinden. `stop_reason="tool_use"` nur bei mindestens einem validem Call setzen; ein `finish_reason="tool_calls"` ohne validen Call ist ein Protokollfehler.

### A-05 — Mittel: Anthropic `tool_choice:none` und Parallelitätssteuerung werden verworfen
**Ort:** anthropic_adapter.py:172-183

**Beschreibung:** Der Adapter mappt nur `auto`, `any` und `tool`. `{"type":"none"}` fällt aus dem internen Payload heraus, während die Tool-Deklarationen erhalten bleiben; der interne Default ist damit `auto`. Für `auto`, `any` und `tool` wird `disable_parallel_tool_use` ebenfalls ignoriert.

**Auswirkung:** Ein Client, der Tool-Nutzung ausdrücklich verbietet, kann trotzdem einen strukturierten Tool-Call erhalten. Ein Verbot paralleler Calls wird nicht transportiert; dies kann Reihenfolge- und Nebenwirkungsannahmen des Clients verletzen.

**Empfehlung:** `none` auf `tool_choice="none"` abbilden und `disable_parallel_tool_use` auf `parallel_tool_calls=False` durchreichen. Alle Choices strikt validieren; unbekannte Varianten nicht still auf `auto` degradieren.

### A-06 — Hoch (I-015 verifiziert): Output-, Sampling- und Stop-Parameter werden angenommen, aber nicht durchgesetzt
**Ort:** anthropic_adapter.py:140-153, anthropic_adapter.py:184-190, responses_adapter.py:140-151, responses_adapter.py:179-184, responses_adapter.py:315-345

**Beschreibung:** Beide Adapter kopieren `max_tokens` beziehungsweise `max_output_tokens`, `temperature` und `top_p` in den internen OpenAI-Payload; Anthropic kopiert zusätzlich `stop_sequences`. Der gemeinsame GLM-Pfad baut seinen tatsächlichen Upstream-Body aber nur aus Conversation-/Message-/Meta-Daten; diese Felder werden nicht umgesetzt. Anthropic normalisiert `budget_tokens` zu `medium`, was den konkreten Token-Budget-Vertrag ebenfalls nicht erfüllt. Responses meldet in Stream-Metadaten statisch `max_output_tokens=None`, `temperature=1`, `top_p=1`, `tool_choice="auto"` und `tools=[]`, auch wenn der Request etwas anderes verlangt hat.

**Auswirkung:** Clients können weder Ausgabelängen noch Sampling- oder Stop-Semantik zuverlässig kontrollieren. Das kann zu abgeschnittenen, unerwartet langen oder semantisch falschen Antworten führen; die Antwortmetadaten behaupten dabei Werte, die nicht durchgesetzt wurden.

**Empfehlung:** Unterstützte Felder explizit upstream abbilden oder mit einem dokumentierten 400 ablehnen. Nicht unterstützte Budgets nicht als erfüllt darstellen. Response-Metadaten aus dem tatsächlich angewandten Request-State statt aus Defaults erzeugen.

### A-07 — Hoch: `previous_response_id` wird ignoriert; Continuation-Tool-Ergebnisse verschwinden vor dem Modell
**Ort:** responses_adapter.py:82-115, responses_adapter.py:263-276, responses_adapter.py:315-349

**Beschreibung:** `previous_response_id` wird weder gelesen noch gespeichert. Die Antwort behauptet in Non-Stream und Stream immer `previous_response_id=None` und `store=False`. Ein Tool-Name für `function_call_output` wird nur durch Rückwärtssuche nach einem `function_call` im selben Payload rekonstruiert. Der übliche Responses-Flow `previous_response_id + function_call_output` erzeugte intern zwar eine `tool`-Nachricht, diese ohne `name` wurde im nachfolgenden `convert_messages()` jedoch vollständig verworfen. Der In-Memory-Check bestätigte: Adapter-Nachricht enthielt `OK`, der finale Upstream-Prompt enthielt es nicht.

**Auswirkung:** Offizielle Responses-Clients, die nur den neuen Output mit `previous_response_id` senden, liefern dem Modell kein Tool-Ergebnis. Das Modell kann den Call wiederholen, eine alte Antwort hallucinieren oder stattdessen Textantworten produzieren. Das ist ein direkter Bruch des Tool-Result-Vertrags.

**Empfehlung:** Entweder `previous_response_id` serverseitig sicher persistieren und Call-ID→Name-Auflösung dafür implementieren oder den Zustandsmodus konsequent ablehnen. Für den stateless Betrieb nur vollständig replayte `function_call` + `function_call_output`-Runden akzeptieren und vor dem Upstream prüfen, dass jedes Result eine passende Call-ID und einen Tool-Namen hat.

### A-08 — Mittel: Strukturierte Responses-Tool-Ergebnisse werden mit `str(...)` beschädigt
**Ort:** responses_adapter.py:16-38, responses_adapter.py:95-115

**Beschreibung:** `function_call_output.output` wird unabhängig vom Typ immer mit `str(item.get("output", ""))` in die interne Tool-Nachricht übernommen. Ein Array mit einem `input_text`-Block wurde damit zu `"[{'type': 'input_text', 'text': 'OK'}]"`, also Python-Repr statt eines strukturierten Inhalts. Bild-/Dateierrgebnisse und `file_id`-Varianten werden nicht über `_response_content_to_openai()` verarbeitet. Fehlende oder leere `call_id` werden nicht als Fehler abgewiesen.

**Auswirkung:** Text-/JSON-Inhalte können maschinenlesbar verändert, multimodale Tool-Ausgaben können verloren gehen und ungültige Call-IDs können verwaiste Results erzeugen. Der Client und das Modell erhalten nicht mehr denselben Tool-Output.

**Empfehlung:** Stringausgaben unverändert übernehmen, Content-Arrays mit demselben Parts-Konverter wie User-Content verarbeiten und Nicht-Text-/Nicht-Datei-Typen kontrolliert behandeln. `call_id` und den zugehörigen `function_call` vor dem Prompt-Aufbau validieren.

### A-09 — Hoch: Offizielle Responses-`tool_choice`-Form und `parallel_tool_calls` werden nicht kompatibel übersetzt
**Ort:** responses_adapter.py:153-177, responses_adapter.py:263-276, responses_adapter.py:315-345

**Beschreibung:** Der Adapter reicht `tool_choice` unverändert weiter. Das offizielle Responses-Format für eine erzwungene Funktion ist `{"type":"function","name":"..."}`, während die interne Policy nur `{"type":"function","function":{"name":"..."}}` versteht. Der vorhandene Test verwendet die nicht standardgemäße Chat-Form. Der Standardfall wurde verifiziert: Der Adapter behielt `{"type":"function","name":"foo"}`, die interne Policy wurde jedoch zu `{"mode":"auto","tool_name":null}` herabgestuft. Auch `allowed_tools` wird nicht verstanden, `parallel_tool_calls` wird ignoriert und die Antwort meldet stets `parallel_tool_calls=True` sowie `tool_choice="auto"`.

**Auswirkung:** Eine explizit erzwungene Function-Choice kann als Textantwort oder als Call einer anderen Funktion enden. `required`/erzwungene Auswahl verliert damit eine zentrale Garantie und kann die beobachtete vorzeitige Beendigung des Tool-Loops begünstigen.

**Empfehlung:** String-Choices sowie die Standardform `{"type":"function","name":...}` und `allowed_tools` in ein internes, validiertes Choice-Modell normalisieren. Nicht unterstützte Formen mit 400 ablehnen. `parallel_tool_calls` durchreichen und in Responses-Metadaten wahrheitsgemäß abbilden.

### A-10 — Mittel: Nicht unterstützte Responses-Tooltypen werden still verworfen oder als falsche Client-Tools behandelt
**Ort:** responses_adapter.py:153-175, anthropic_adapter.py:155-171

**Beschreibung:** Nur `type="function"` wird in eine Function-Deklaration übersetzt. `web_search*` setzt lediglich ein boolesches Netzwerk-Flag. `file_search`, Code Interpreter, Computer Use, MCP, Custom Tools und sonstige Responses-Tooltypen werden kommentarlos aus der Tool-Liste entfernt. Im Anthropic-Pfad werden dagegen beliebige Tool-Dicts zu normalen Functions gemacht, auch wenn es sich um serverseitige Anthropic-Tools mit datierten Toolnamen handelt.

**Auswirkung:** Der Client erkennt nicht, dass eine verlangte Fähigkeit nicht implementiert ist. Das Modell erhält eine unvollständige Tool-Liste, kann nicht korrekt callen und antwortet möglicherweise mit Text statt mit einem strukturierten Tool-Event. Datierte oder anders benannte Native-Tools können die Blocklist umgehen.

**Empfehlung:** Unterstützte Tooltypen explizit per Schema validieren. Nicht unterstützte Built-ins mit einem stabilen 400 oder einem strukturierten `unsupported_tool`-Fehler ablehnen; nicht still aus dem Vertrag entfernen. Serverseitige Tooltypen nicht als Client-Functions vortäuschen.

### A-11 — Hoch: Responses-Streaming meldet `length`, Filter- und unvollständige Tool-Calls als `completed`
**Ort:** responses_adapter.py:472-505, responses_adapter.py:577-613

**Beschreibung:** Jeder truthy `finish_reason` beendet den Accumulator als Erfolg. `finish_reason="length"` wurde verifiziert als `response.completed` mit `status="completed"` und `incomplete_details=null` emittiert, obwohl der Non-Stream-Pfad an derselben Stelle `status="incomplete"` und `reason="max_output_tokens"` erzeugt. Auch `content_filter` oder unvollständige Argument-JSON werden nicht als Fehler klassifiziert. Der finale `arguments.done`-Event enthält den rohen, nicht validierten Argumentpuffer.

**Auswirkung:** OpenAI-SDKs können eine abgeschnittene, gefilterte oder nicht ausführbare Antwort als vollständig abgeschlossene Response akzeptieren und ihren Tool-Loop beenden. Das reproduziert die Kernwirkung „ein Toolcall/Partial-Turn wird als Antwort gegeben“ auf dem Responses-Endpoint.

**Empfehlung:** Finish-Zustände strikt tabellieren: `stop`/gültiges `tool_calls` → completed, `length`/`content_filter` → incomplete mit korrektem Grund, Upstream-/Parsefehler → failed. Vor `function_call_arguments.done` das assemblierte JSON validieren; bei Truncation niemals `response.completed` senden.

### A-12 — Mittel: Responses-Streaming dupliziert Text und gibt abgeschlossene Output-Items in falscher Reihenfolge aus
**Ort:** responses_adapter.py:400-470, responses_adapter.py:508-575, responses_adapter.py:577-609

**Beschreibung:** `_full_text` wird beim Start einer zweiten Message nicht zurückgesetzt. Fließt nach einem Tool-Call noch Text, enthält die zweite abgeschlossene Message den vorherigen plus neuen Text. Außerdem werden offene Tool-Items erst in `_finish()` an `_completed_output` angehängt, während eine später begonnene Text-Message vorher abgeschlossen und bereits angehängt werden kann. Die finale Output-Liste kann dann `[Message, Tool]` ausgeben, obwohl die Events `[Tool, Message]` emittiert haben.

**Auswirkung:** SDKs, die die finale `response.completed.output`-Liste verwenden, erhalten doppelten Text oder eine andere Reihenfolge als im Live-Stream. Das kann Folgekontext, Toolauswahl und dargestellte Antwort verfälschen. Der aktuelle GLM-Pfad liefert Tools üblicherweise am Turn-Ende, sodass dies vor allem alternative/verschachtelte Streams betrifft.

**Empfehlung:** Text- und Message-State pro Output-Item führen und beim Item-Abschluss vollständig einfrieren. Jedes abgeschlossene Item direkt in seiner `output_index`-Reihenfolge in `_completed_output` schreiben; offene Tool-Calls nur anhand ihres gespeicherten Output-Index anhängen.

### A-13 — Hoch: Tool-Blocklisten sind case-sensitiv und lassen Native-Tool-Varianten durch
**Ort:** tool_protocol.py:7-22, tool_protocol.py:33-47, tool_protocol.py:148-171

**Beschreibung:** `normalize_tool_name()` normalisiert nur mit `strip()`. Vergleiche gegen konfigurierte und native Blocknamen erfolgen case-sensitiv. Der In-Memory-Check mit Blockmenge `{"open_url"}` und Toolname `OPEN_URL` zeigte, dass das Tool unverändert im gefilterten Ergebnis blieb. Das Gleiche gilt für `Browser.Open`, `WEB.SEARCH`, `Execute_Sandbox_Code`, datierte Native-Toolnamen und normalisierungsabhängige Unicode-/Leerzeichenvarianten. Der Name wird im Prompt ohne strukturelle Maskierung in Backticks und Schemata eingesetzt.

**Auswirkung:** Native Browser-/Sandbox-Sperren können durch Schreibweise oder Suffixe umgangen werden. Da die Tool-Liste später als vollständiger Vertrag gilt, kann das Modell verbotene Fähigkeiten halluzinieren oder der Client einen unbekannten Handler auslösen. Das ist zugleich die im Audit geforderte Case-Sensitivity-Lücke.

**Empfehlung:** Eine kanonische Native-Tool-Registry mit expliziten Alias- und Versionssuffix-Regeln verwenden. Policy-Vergleiche über normalisierten Namen (`strip`, definierte Unicode-Normalisierung, `casefold`) durchführen, die originale API-Funktions-ID aber nicht unkontrolliert verändern. Toolnamen zusätzlich auf Typ, Länge, eindeutige Namen und erlaubte Zeichen prüfen.

### A-14 — Mittel: Der Tool-Call-Serializer ersetzt beschädigte Argument-JSON durch erfundene `raw`-Semantik
**Ort:** tool_protocol.py:52-62

**Beschreibung:** `serialize_tool_call_block()` parseiert Argument-Strings tolerant. Bei Syntaxfehlern wird daraus `{"raw": arguments}`; nicht-objektive JSON-Werte werden unter `value` verpackt. Damit wird ein Parsing- oder Übertragungsfehler als scheinbar gültiges Tool-Schema mit einem zusätzlichen Parameter weitergereicht.

**Auswirkung:** Ein fehlerhafter Call kann bei einem History-Roundtrip mit anderen Argumenten erneut ausgeführt werden. Das Modell erhält den Eindruck, `raw` sei ein regulärer Parameter, obwohl es sich um eine Reparaturmarkierung handelt. Das begünstigt falsche Calls und schwer zuordenbare Tool-Ergebnisse.

**Empfehlung:** Nur schema-validierte Argumentobjekte serialisieren. Parsefehler als Fehlerzustand beziehungsweise sichtbaren Tool-Failure übergeben, nicht als Datenparameter umbenennen. Für absichtlich flexible Non-JSON-Argumente einen separaten, expliziten Protokolltyp verwenden.

### A-15 — Hoch (I-005 verifiziert): Debug-Dumps legen Refresh-, Access- und Guest-Tokens im Klartext ab
**Ort:** glm_auth.py:105-114, glm_auth.py:201-202, glm_auth.py:248-249

**Beschreibung:** Für registrierte Accounts wird der komplette `Authorization: Bearer <refresh_token>`-Header über `dict(request.header_items())` protokolliert. `read_json_response()` schreibt vor dem Parsen außerdem den gesamten rohen JSON-Body; dieser enthält üblicherweise `access_token` und `refresh_token`. Guest-Token-Requests werden ebenfalls vollständig gedumpt. `debug_dump()` redigiert keine Header- oder Tokenfelder.

**Auswirkung:** Debug-Modus persistiert wiederverwendbare Credentials in Konsole/Rotating-Log und kann damit weit über die vorgesehene lokale Sitzung hinaus Konten übernehmen. Der Refresh-Body `{}` ist harmlos, die Header- und Response-Bodies sind es nicht.

**Empfehlung:** Vor jeder Secret-Dump-Zeile zwingend `Authorization`, `x-api-key`, Cookie sowie `access_token`/`refresh_token` redigieren. Nur Header-Allowlist und Feldnamen/Hash-Metadaten loggen. Secret-Debugmodus explizit und standardmäßig aus; Logs mit restriktiven Rechten und eigener kurzer Retention betreiben.

### A-16 — Hoch (I-006 verifiziert): Token-Refresh-Rennen und zu breites Account-Failover
**Ort:** glm_auth.py:162-180, glm_auth.py:182-225, glm_auth.py:267-280, glm_auth.py:314-325

**Beschreibung:** Der Cache-Lookup ist gelockt, der Refresh nicht. Zwei Threads für dasselbe Account wurden mit einem kontrollierten In-Memory-Refresh verifiziert: Es erfolgten **zwei** Refresh-Aufrufe; das zuerst gestartete Ergebnis wurde später durch das zwischenzeitlich gecachte Token diskrediert. Bei rotierenden Refresh-Tokens können zwei Antworten unterschiedliche Token-Stände besitzen und in belieriger Reihenfolge persistiert werden; `_persist_lock` serialisiert nur den Schreibzugriff, nicht den gesamten Read-Modify-Write-/Versions-Zyklus. Guest-Accounts erzeugen parallel redundante Tokens. Zusätzlich bewertet `should_switch_account()` jede Exception mit einem `status_code`-Attribut als account-spezifisch. Der Check für einen deterministischen 400er ergab `True`.

**Auswirkung:** Ein veralteter Refresh-Token kann einen neueren überschreiben, Auth-Rotationen werden verschwendet, und deterministische 400/404/Content-Fehler werden auf mehreren Accounts wiederholt. Das erhöht Ausfälle, Upstream-Last und die Gefahr, dass ein transienter Fehler die Token-Rotation weiter eskaliert.

**Empfehlung:** Pro Account eine Condition-Variable-/`Future`-Single-Flight-Struktur einführen, inklusive monotoner Tokenversion. Refresh plus Persistenz als eine versionierte Transaktion behandeln und Guest-Refresh mit Backoff/Jitter bündeln. Nur 401/403, klar tokenbezogene Fehler und transiente Netzwerk-/Upstream-Auth-Fehler rotieren; deterministische Request-/Content-Fehler nicht.

### A-17 — Mittel (I-017 verifiziert): Fest eincodierte MD5-Signatur ist kein schützenswerter kryptografischer Schlüssel; Klartext-HTTP ist möglich
**Ort:** glm_auth.py:19-30, glm_auth.py:187-203, glm_auth.py:228-250

**Beschreibung:** `SIGN_SECRET` liegt fest im Quelltext; `build_sign()` verwendet MD5 über Timestamp, Nonce und diesen öffentlich bekannten Wert. Jeder mit dem Repository vertraute Prozess kann gültige Signaturen erzeugen. Die Refresh- und Guest-Anfragen enthalten Bearer-Credentials. Die Upstream-URL stammt aus `config.glm_base_url`; die bestehende Konfigurationsvalidierung akzeptiert `http://` ebenso wie `https://`.

**Auswirkung:** Die Signatur darf nicht als kryptografische Authentifizierung oder Anti-Replay-Sicherheit betrachtet werden. Bei HTTP-Upstream können Access-/Refresh-Tokens und Inhalte mitgelesen oder verändert werden. Wer den Wert als nicht geheime Anti-Bot-Property versteht, darf darauf trotzdem keine Vertraulichkeit oder Client-Authentifizierung aufbauen.

**Empfehlung:** Semantik der Signatur dokumentieren und sie konsequent als öffentliche Upstream-Property behandeln. Falls das Protokoll einen echten HMAC/authentifizierten Mechanismus anbietet, diesen mit externem, rotierbarem Secret verwenden. Produktions-HTTPS erzwingen; HTTP nur als explizite Development-Ausnahme mit Loopback zulassen.

### A-18 — Mittel: Auth-Upstreamantworten und Token-Persistenz werden ungeprüft beziehungsweise nicht atomar verarbeitet
**Ort:** glm_auth.py:105-123, glm_auth.py:206-225, glm_auth.py:253-280, glm_auth.py:282-312

**Beschreibung:** Mehrere Punkte können den Auth-State beschädigen:

- `result` wird ungeprüft wie ein Dictionary behandelt; ein Array/String führt zu einem späten `AttributeError`.
- `access_token`/`refresh_token` werden nicht als nichtleere Strings validiert. Ein explizites `refresh_token:null` kann den In-Memory- und Config-Token auf `None` setzen; der folgende Refresh fällt dann in den Gastpfad.
- Die Token-Lebensdauer wird unabhängig von einer Upstream-Ablaufangabe fest auf knapp eine Stunde gesetzt.
- Der Response-Body und `gzip.decompress()` sind unbeschränkt; nur exakt `Content-Encoding: gzip` wird behandelt, obwohl die gesendeten Accept-Encoding-Header auch Deflate anbieten.
- Token-Datei und `.env` werden direkt per `write_text()` überschrieben, nicht atomar und ohne Rechteprüfung. In `.env` wird nur die erste exakt beginnende `GLM_REFRESH_TOKEN=`-Zeile ersetzt; Duplikate können den neuen Wert später wieder überschreiben.

**Auswirkung:** Ein unerwarteter Upstream-Response kann Auth-State mit `None` erzeugen, Persistenz kann bei Crash/Concurrency einen veralteten oder leeren Secret-Stand hinterlassen, und große/komprimierte Bodies belegen unbegrenzt Memory. Das führt zu vermeidbaren 401-/502-Kaskaden und potenziell unbrauchbaren Token-Dateien.

**Empfehlung:** Upstream-JSON per Schema validieren, nur nichtleere String-Tokens akzeptieren, echte Ablaufzeit verwenden und Fehlerantworten begrenzen. Deflate/Encoding-Listen explizit behandeln. Token-Updates als versionierten Single-Flight ausführen, in restriktiven Dateien im gleichen Verzeichnis temporär schreiben und atomar ersetzen; alle konkurrierenden Env-Duplikate erkennen.

### A-19 — Mittel (I-016): Vollständige Auth-Fehlerpayloads werden in Exception-Text und damit potenziell zum Client transportiert
**Ort:** glm_auth.py:210-211, glm_auth.py:257-258

**Beschreibung:** Bei fehlgeschlagenem Refresh bzw. Gast-Fetch wird das komplette Upstream-Payload in `RuntimeError(f"Failed ...: {payload}")` aufgenommen. Der Server leitet `str(exc)` bei Upstream-/allgemeinen Fehlern als öffentliche API-Meldung weiter. Payloads können Request-IDs, interne Felder, Account-/Tokenstatus oder in Fehlerfällen sogar Credentials enthalten.

**Auswirkung:** Interne Upstream- und Accountinformationen werden über die Downstream-API offengelegt. Das erleichtert gezielte Account-/Endpoint-Aufklärung und kann Debug-Logs mit Secrets zum Clientkanal erweitern.

**Empfehlung:** Intern eine stabile Fehlerklasse mit Correlation-ID und redigierter serverseitiger Diagnose verwenden. Nach außen nur eine konstante, nicht-sensitive Meldung senden; vollständige Payloads nur im geschützten internen Log mit Token-/URL-Redaktion speichern.

## Positiv

- In diesen vier Dateien gibt es **keine freie Text-zu-Tool-Call-Heuristik**: Anthropic `tool_use` und Responses `function_call` werden nur anhand ihrer strukturierten Blocktypen konvertiert. Die im Projekt gefährliche Text-/JSON-Fallback-Interpretation liegt im separat auditierten `tool_parser.py`/`translator.py`, nicht in diesen Adaptern.
- Der einfache Anthropic-Happy-Path funktioniert: `tool_use` mit Objektinput wird zu einem OpenAI-`tool_calls`-Assistant mit erhaltener ID, Name und JSON-Argumenten; ein einfacher String-`tool_result` wird korrekt als `role="tool"` mit `tool_call_id` weitergereicht.
- Der einfache Responses-Happy-Path funktioniert: Ein `function_call` und ein unmittelbar nachfolgendes `function_call_output` mit gleicher `call_id` im selben Payload werden zu Assistant-Tool-Call plus Tool-Result; der Tool-Name wird rückwärts aufgelöst.
- Die Responses-Streaming-Akkumulation ist pro Tool-Call-Index korrekt: Ein synthetischer Stream mit interleavten Deltas `0,1,0,1` erzeugte die zu den jeweiligen `item_id`s passenden Deltas und die getrennten fertigen Argumente `{"p":1}` und `{"q":2}`. I-011 betrifft den Anthropic-Adapter, nicht diesen Response-Index-Accumulator.
- Beide Streaming-Adapter puffern geteilte SSE-Blöcke und die vorhandenen Tests decken den Split bis `[DO` + `NE]` ab. `ResponsesStreamAccumulator` kann sowohl mit `[DONE]` als auch mit einem expliziten `finish_reason` terminieren.
- Die öffentliche Terminal-API ist wie bekannt gefixt: `finish()` ist bei beiden Accumulatoren öffentlich und idempotent; `error_event()` setzt `_finished`, sodass danach kein `message_stop`/`response.completed` erzeugt wird. Die zugehörigen Regressionstests sind grün.
- Die INT-Falle bei Anthropic Thinking ist gefixt: `budget_tokens` wird nicht ungeprüft als `reasoning_effort` weitergereicht, sondern `thinking.type="enabled"` wird auf `"medium"` normalisiert. Der Regressionstest ist grün.
- Das `_safe_json`-Duplikat ist gefixt: Beide Adapter importieren ausschließlich `safe_json_dumps` aus `tool_protocol.py`; im Adapterbereich existiert keine zweite Implementierung.
- Normale strukturierte Ausgabe-Calls werden nicht absichtlich als Text serialisiert: Ein valider OpenAI-Tool-Call wird im Anthropic-Pfad zu `tool_use`, im Responses-Pfad zu `function_call` mit separater `call_id`.
- Der Access-Token-Cache besitzt eine untere Sicherheitsmarge von 60 Sekunden, Cache-Hit und Account-Indexzugriffe sind grundsätzlich gelockt, und Upstream-Requests besitzen ein konfigurierbares Timeout.

## Geprüft und unauffällig

- Alle **1.633** Zeilen der vier Scope-Dateien wurden vollständig und in der angegebenen Reihenfolge gelesen; es wurden keine Zeilen oder Dateien übersprungen.
- `uv run pytest tests/test_protocol_adapters.py -q` → **16 passed in 1.13s**.
- `uv run pytest -q` → **150 passed in 1.23s**.
- Die gezielten In-Memory-Prüfungen verwendeten ausschließlich Dummy-Daten und mutierten keine Projektdatei; es erfolgten keine GLM-, Upstream- oder Account-Netzwerkaufrufe. Offizielle API-Schema-Dokumentation wurde read-only zum Feldvergleich konsultiert.
- `test_protocol_adapters.py` deckt einfache Tool-Choice-Varianten, Responses SDK-style Messages, Standard-Textantworten, SSE-Splitting, Terminalisierung, öffentliche Finish-/Error-Events, Anthropic-Pings und die INT-Falle ab. Die obigen Parallel-, Mixed-Content-, Choice- und Fehlerklassifikationslücken sind davon nicht abgedeckt.
- Die aktuelle opencode-Konfiguration (`.opencode/opencode.json:107-131`) verwendet `@ai-sdk/openai-compatible`; dieser Provider nutzt Chat Completions, nicht `/v1/messages` oder `/v1/responses`. Für opencode 1.18.30 ist `tool_call` bei Custom Models standardmäßig `true`, auch wenn es im glm2api-Eintrag nicht explizit steht. Die beiden Adapter sind deshalb **nicht der aktuelle Requestpfad des beobachteten opencode-Fehlers**; `tool_protocol.py` wirkt dagegen auch auf den Chat-Pfad.
- Der aktuelle interne GLM-Stream emittiert validierte Tool-Calls üblicherweise als sequenzielle, komplette `function.arguments`-Chunks. Der Anthropic-Interleaving-Bug ist im aktuellen glm2api-Generator deshalb ein latenter Adapterfehler; der Responses-Adapter kann hingegen auch echte interleavte Indizes verarbeiten.
- Es wurden keine Änderungen an Projektcode oder Konfiguration vorgenommen. Das einzige geschriebene Artefakt ist der ausdrücklich angeforderte Bericht unter `/tmp/opencode/`.
