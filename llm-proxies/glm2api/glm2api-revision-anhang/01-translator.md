# 01 — translator.py

(Scope: **1.713 Zeilen**, vollständig in mehreren `Read`-Chunks gelesen und Zeile für Zeile geprüft. Stand des geprüften Arbeitsstands: aktueller Repository-HEAD. Keine Codeänderung, kein Serverstart und kein Netzwerkaufruf. Die lokale Testsuite lief mit `uv run pytest -q`: **150 passed**.)

## Befunde

### T-01 — Hoch: Text-Funktionsaufrufe werden ohne Kontext als echte Calls interpretiert
**Ort:** translator.py:1277-1285, translator.py:1519-1532

**Beschreibung:** `finalize()` und `build_response()` rufen `parse_tool_calls_from_text()` ohne einen Recovery- oder Kontextmodus auf. Dadurch greift auch der Text-Funktions-Fallback für Zeilen wie `read("...")`, `bash("...")` und `webfetch("...")`. Dieser Fall prüft weder, ob die Zeile Teil eines Codebeispiels ist, noch ob sie im aktuellen Turn überhaupt ein Tool-Protokoll ist. Empirisch wurde ein `read("/tmp/example.py")` innerhalb eines Python-Codeblocks als `read`-Tool-Call emittiert; auch eine erklärende Zeile mit diesem Muster kann verschwinden und durch einen Call ersetzt werden.

**Auswirkung:** Eine normale Erklärung, ein Quellcode-Snippet oder eine Dokumentationszeile kann eine reale Tool-Ausführung auslösen. Für `bash(...)` ist der Argumentinhalt nicht auf einen sicheren Schema-/Kontextkontext beschränkt. Das ist eine direkte False-Positive-Quelle für „Text wird als Tool-Call interpretiert“ und kann beim Client zu unbeabsichtigter Ausführung oder zu einer leeren Antwort führen.

**Empfehlung:** Den Text-Funktions-Fallback nur in einem expliziten, zustandsbehafteten Recovery-Modus und nur bei einer validierten Tool-Deklaration verwenden. Code-Fences und Dokumentationskontext müssen vor der Fallback-Erkennung geprüft werden. Stream- und Non-Stream-Pfad sollten dieselbe strikt validierende Parse-Kernfunktion benutzen.

### T-02 — Kritisch (I-009 verifiziert): `None` bedeutet gleichzeitig „keine Tools“ und „alle Tools erlaubt“
**Ort:** translator.py:371-415, translator.py:541-573, translator.py:1047-1132, translator.py:1277-1293, translator.py:1519-1555

**Beschreibung:** `allowed_tool_names=None` wird an mehreren Stellen als Wildcard interpretiert. Das ist problematisch, weil derselbe Wert im Client auch dann entsteht, wenn der Request überhaupt keine deklarierten Tools besitzt: `map_native_open_tool_call()` und `map_native_sandbox_tool_call()` erlauben bei `None` das Mapping auf `bash`, `read` oder `webfetch`; der serverseitige native Pfad überspringt bei `None` die Allowlist-Prüfung; und `convert_messages()` filtert bei einer leeren Tool-Menge nicht (`if available_tool_names and ...`, Zeile 802). Empirisch erzeugte ein native Call `totally_unknown` bei `allowed_tool_names=None` einen echten Tool-Call. Ebenso wurden `open` und `execute_sandbox_code` ohne deklarierte Tools auf `read`/`bash` abgebildet.

**Auswirkung:** Ein Request ohne Tools kann mit strukturierten Tool-Calls und `finish_reason="tool_calls"` enden. Ein nachgelagerter Agent kann daraus unbemerkt Aktionen ausführen. Historische Calls können außerdem erneut in den Prompt gelangen, obwohl in diesem Turn keine Tools freigegeben sind.

**Empfehlung:** „Keine Tools“ und ein bewusster interner Recovery-Modus müssen zwei verschiedene Zustände sein. Ohne eine konkrete, deklarierte Ziel-Allowlist darf weder aus Quelltext ein Call erzeugt noch ein natives Tool gemappt werden. Native Namen vor jedem Vergleich kanonisieren und die Blockliste unabhängig von der Allowlist durchsetzen.

### T-03 — Hoch: Serverseitige und Text/XML-Calls werden nicht quellübergreifend dedupliziert
**Ort:** translator.py:1133-1165, translator.py:1287-1293, translator.py:1547-1555

**Beschreibung:** Die Signatur-Deduplizierung existiert nur innerhalb des serverseitigen Native-Pfads. Beide Finalisierer mergen anschließend blind `self._server_side_tool_calls` und die aus Text/XML extrahierten Calls. Empirisch führte ein Native-`read`-Call plus ein XML-`read`-Call mit denselben Argumenten zu zwei OpenAI-Tool-Calls mit unterschiedlichen IDs. Auch der Safety-Net-Pfad kann einen bereits vorhandenen Call nochmals anhängen.

**Auswirkung:** Ein Modell, das denselben Call in zwei Upstream-Kanälen spiegelt, kann zweimal ausgeführt werden. Das erzeugt doppelte Schreib-/Bash-Nebenwirkungen, zusätzliche Tool-Runden und schwer zuzuordenbare Ergebnisse. Die bisherige Signatur-Deduplizierung löst das Problem nur für Echo-Parts desselben Kanals.

**Empfehlung:** Erst nach dem Zusammenführen aller Quellen kanonisch deduplizieren. Dabei Herkunft, Call-ID und eine explizite Echo-Markierung berücksichtigen; legitime, bewusst parallel angeforderte Calls dürfen nicht allein wegen gleicher Argumente verschwinden.

### T-04 — Hoch: Signatur-Deduplizierung verschluckt legitime Wiederholungen und ID-Konflikte
**Ort:** translator.py:928-960, translator.py:1133-1165

**Beschreibung:** Die serverseitige Dedup-Logik verwendet nur `Name + normalisierte Argumente`, nicht die Call-ID als Identität. Zwei Calls mit verschiedenen IDs und identischen Argumenten werden auf einen reduziert. Eine zweite Native-Nachricht mit derselben ID, aber anderen Argumenten, wird ebenfalls still verworfen, weil die ID bereits im Set steht. Auch ein absichtlich wiederholter `read`- oder `bash`-Call aus der aktuellen Runde wird als Echo behandelt, wenn er einer historischen Signatur entspricht.

**Auswirkung:** Ein gültiger zweiter Tool-Schritt kann verschluckt werden. Das ist besonders schädlich bei `bash("pwd")`, wiederholten Dateioperationen oder zwei nahezu identischen, aber semantisch getrennten Aufgaben. Der Client erhält keine Fehlermeldung, weil der Drop als Echo-Logik behandelt wird.

**Empfehlung:** Native Calls anhand einer stabilen Call-ID deduplizieren und Signaturen nur zur Erkennung eines nachweislich historischen Echoes verwbaren. IDs mit abweichenden Argumenten als Konflikt behandeln, nicht still verwerfen.

### T-05 — Hoch: Reasoning-Protokolle werden roh ausgeliefert und nicht vollständig extrahiert
**Ort:** translator.py:1182-1196, translator.py:1279-1285, translator.py:1356-1360, translator.py:1519-1533, translator.py:1574-1578, translator.py:1609-1617

**Beschreibung:** Der `think`-Inhalt wird in `consume_event()` direkt als `reasoning_content` gesendet und weder durch den Tool-Parser noch durch eine Protokollbereinigung geschickt. Im Non-Stream-Pfad wird `full_reasoning` unverändert in die Antwort geschrieben. Der Reasoning-Fallback läuft außerdem nur, wenn der Textseiten-Parser keine Calls liefert. Enthält eine Antwort sowohl einen erlaubten Text-Call als einen weiteren Call im Reasoning, wird der Reasoning-Call vollständig übersehen. Empirisch blieb ein JSON-Protokoll im `reasoning_content` sichtbar; bei DSML-Fragment-Plus-Finish-Duplikat konnte der Reasoning-Fallback zusätzlich gar keinen Call extrahieren.

**Auswirkung:** Der Client kann das interne Tool-Protokoll als Thinking-Antwort anzeigen. Ein im Reasoning versteckter Call kann verschluckt werden, während ein anderer Call ausgeführt wird. Das erzeugt genau die gemeldete Mischung aus sichtbarem Protokolltext, fehlendem Call und inkonsistenten Tool-Runden.

**Empfehlung:** Reasoning vor der Ausgabe mit derselben strikt validierenden Call-Logik behandeln, Calls aus allen Kanälen unabhängig extrahieren und anschließend kanonisch zusammenführen. Tool-Protokoll aus `reasoning_content` entfernen oder als internes, nicht client sichtbares Feld behandeln. Den Fallback nicht vom Ergebnis des Textparsers abhängig machen.

### T-06 — Hoch: Leer-Erkennung läuft vor der endgültigen Bereinigung und kann Calls verschlucken
**Ort:** translator.py:998-1008, translator.py:1325-1355, translator.py:1519-1557

**Beschreibung:** `is_empty_response()` prüft den rohen gerenderten Text sowie die noch nicht endgültig validierten Parser-/Server-Call-Listen. Es prüft weder die nach der Sanitisation verbleibenden Calls noch Calls, die erst aus dem Reasoning extrahiert werden. Der Client ruft diese Methode nach `finalize()`/`build_response()` für den Leer-Turn-Retry auf. Ein abgeschnittenes Inline-Protokoll gilt dadurch als „nicht leer“, obwohl die sichtbare Ausgabe leer oder nur ein Protokollrest ist. Ein Parser-Call für `write` ohne `content` gilt als Call, wird aber später in `sanitize_tool_calls()` verworfen. Reasoning-Calls werden vor dem Retry-Check nicht als Calls gezählt.

**Auswirkung:** Gültige Retry-Fälle werden nicht erneut versucht; der Client bekommt einen leeren oder protokollhaltigen `stop`-Turn. Ein gültiger Reasoning-Call kann trotz vorhandener Tool-Aktion als leerer Turn verworfen werden. Das erzeugt leere Agentenrunden und wiederholte Fehlversuche.

**Empfehlung:** Einen unveränderlichen, einmal finalisierten Result-State erzeugen und `is_empty_response()` ausschließlich auf den daraus validierten Calls und dem endgültig bereinigten Text anwenden. Parser-Kandidaten, blockierte Versuche und Reasoning-Calls müssen getrennt modelliert werden.

### T-07 — Hoch: Ein vorzeitiger Stream-Preamble kann nicht zurückgenommen werden
**Ort:** translator.py:1198-1247, translator.py:1305-1411, translator.py:1557-1577

**Beschreibung:** Sobald `visible_text_delta` keinen Parser-Holdback auslöst, wird der Text sofort als SSE-`content` gesendet. Kommt der Tool-Call in einem späteren Event oder als serverseitiger Native-Call, unterdrückt `finalize()` nur noch `final_text` und nicht die bereits gesendeten Deltas. Empirisch wurde bei zwei Events zuerst `Ich führepwd aus.` und danach ein `bash`-Call gesendet; der finale Stream enthielt sowohl sichtbaren Text als auch `tool_calls`. Der Non-Stream-Pfad setzt `content` in diesem Fall dagegen auf `None`.

**Auswirkung:** Der Client kann die Präambel als fachliche Antwort interpretieren oder den Turn trotz Tool-Call beenden. Stream- und Non-Stream-Antworten sind semantisch verschieden. `strip_meta_chatter()` kann einen bereits emittierten Preamble nicht reparieren.

**Empfehlung:** Bei deklarierten Tools die vollständige Turn-Klassifikation vor der ersten sichtbaren Textausgabe erzwingen oder den Upstream als strukturierten Tool-Event-Stream verwenden. Ein nachträgliches Filtern allein ist kein ausreichender Schutz gegen irreversible SSE-Ausgabe.

### T-08 — Hoch: Fenced Tool-Protokolle werden stream- und non-streamabhängig unterschiedlich behandelt
**Ort:** translator.py:1251-1274, translator.py:1308-1316, translator.py:1519-1530

**Beschreibung:** `_unwrap_protocol_only_fences()` wird nur im Streaming-Finalizer aufgerufen und erkennt nur einen sehr engen Präfix (`{"tool_calls"` ohne zusätzliche Leerzeichen). Der Parser maskiert Backtick-Fences grundsätzlich. Im Non-Stream-Pfad gibt es keinen entsprechenden Fence-Unwrap. Empirisch wurde ein kompakter fenced JSON-Call im Stream korrekt extrahiert, im Non-Stream-Pfad jedoch zu `content="```json"` verfälscht und der Call verloren. Pretty-Print mit Leerzeichen nach `{` blieb auch im Stream als Fence-Rest mit `json`-Prefix stehen und lieferte keinen Call.

**Auswirkung:** Ein gültiger Call kann verschwinden und stattdessen sichtbarer Fence-Rest als Antwort erscheinen. Das ist eine direkte Stream/Non-Stream-Paritätsabweichung und eine weitere Quelle für Rohprotokoll-Leaks.

**Empfehlung:** Fence-Erkennung, Sprachprefix, Whitespace und Tool-Format in eine gemeinsame, strikt validierende Normalisierung vor beiden Finalisierern verschieben. Nur ein vollständig protokollkonformer Fence darf entpackt werden; der Non-Stream-Pfad muss denselben Pfad wie Streaming verwenden.

### T-09 — Hoch: Inline-/truncated Tool-Fragmente können als sichtbarer Text durchrutschen
**Ort:** translator.py:1325-1355, translator.py:1519-1529

**Beschreibung:** Der importierte `strip_unparseable_call_fragments()`-Safety-Net greift im Wesentlichen nur für ein Call-Objekt am Zeilenanfang. Ein abgeschnittenes JSON-Protokoll nach Prosa auf derselben Zeile wird nicht entfernt. Empirisch blieb der Input `prefix {"tool_calls":[{"name":"bash","arguments":{"command":"x"` als sichtbarer JSON-Text im Stream. Ein malformed JSON-Block mit `arguments:{}` erzeugte im Non-Stream-Pfad einen Rest wie `{"tool_calls": }[]`. Die rohe Fragment-Präsenz verhindert außerdem den Leer-Retry.

**Auswirkung:** Der Upstream-Abbruch wird als scheinbare Antwort weitergereicht. Das entspricht dem Kernsymptom „Tool-Call-Protokoll landet als sichtbarer Text“ und kann Clients dazu bringen, den Text als Antwort zu rendern.

**Empfehlung:** Fragment-Scanning zustandsbehaftet und positionsunabhängig über den gesamten verbleibenden Text ausführen. Nur die tatsächlich unparsebare Call-Spanne entfernen, Prosa erhalten und bei nicht rekonstruierbaren Calls einen expliziten Fehler-/Retry-Status statt `stop` erzeugen.

### T-10 — Hoch: Blockierte Versuche werden bei gemischten und alternativen Formen nicht erkannt
**Ort:** translator.py:1329-1343, translator.py:1356-1376, translator.py:1533-1545, translator.py:1062-1132

**Beschreibung:** Im Safety-Net wird mit `allowed_tool_names=None` geparst, aber der Parser filtert die Native-Denylist-Namen bereits vor der Rückgabe. Mixed Calls werden dadurch nicht vollständig sichtbar: Ein Wrapper mit erlaubtem `bash` und blockiertem `open_url` lieferte nur den `bash`-Call und keine blockierte Namensmeldung, weil die nachgelagerte Erkennung nur bei `not all_tool_calls` läuft. `detect_tool_call_names()` erkennt außerdem überwiegend nur JSON-Wrapper und DSML, nicht Bare-Arrays, Naked-Objects, Funktionssyntax oder abgeschnittene JSON-Formen. Empirisch erzeugte ein Bare-Array mit `open_url` weder Call noch `blocked_tool_attempt_names` und endete als leerer `stop`-Turn.

**Auswirkung:** Kein negativer Follow-up-Round wird gestartet. Das Modell kann denselben blockierten Call wiederholen, während der Client bereits einen scheinbar abgeschlossenen Text-Turn erhält. Das ist sowohl ein False Negative als auch eine Fehlklassifikation des Endzustands.

**Empfehlung:** Call-Namen und Call-Ausführbarkeit in zwei Phasen erfassen: erst alle Namen ungefiltert und in allen unterstützten Protokollformen sammeln, dann die Ausführbarkeit gegen die Allowlist entscheiden. Blockierte Namen müssen auch neben erlaubten Calls und unabhängig vom verwendeten Format gespeichert werden.

### T-11 — Hoch: Native-Metadata-, Namens- und ID-Vertrag ist verlustbehaftet
**Ort:** translator.py:1062-1078, translator.py:1080-1133

**Beschreibung:** Mehrere native Eingabeformen werden stillschweigend verworfen oder inkonsistent behandelt:

- Der Meta-Data-Pfad lässt `open`, `execute_sandbox_code` und verwandte Namen wegen der Kleinschreibungssonderbehandlung explizit durch; die anschließende Blocklistenprüfung ist nicht case-insensitiv. `OPEN_URL` oder `EXECUTE_SANDBOX_CODE` werden dadurch nicht zuverlässig als blockiert erkannt.
- Ein serverseitiges `tool_calls`-Objekt ohne ID wird nicht angehängt; eine explizite `null`-ID wird durch `str(None)` zu `"None"`.
- Ein `tool_calls`-Array statt eines einzelnen Dictionarys wird ignoriert.

Empirisch fehlten Calls ohne ID vollständig, `null` erzeugte die ID `"None"`, und ein Array mit zwei Calls blieb ohne Ergebnis.

**Auswirkung:** Gültige Native-Calls können verschluckt werden, IDs können kollidieren oder Results nicht zugeordnet werden. Case-Varianten nativer Tools umgehen die vorgesehene Blockierung und fördern Halluzinationsschleifen.

**Empfehlung:** Native-Toolnamen vor jeder Entscheidung kanonisieren. Für Calls ohne brauchbare ID eine deterministische Proxy-ID erzeugen oder den Call explizit ablehnen; das tatsächlich unterstützte Payload-Schema strikt validieren und mehrere Calls atomar verarbeiten.

### T-12 — Hoch: Safety-Net-Calls umgehen die normale Sanitisation und Required-Argument-Prüfung
**Ort:** translator.py:1277-1293, translator.py:1325-1343, translator.py:576-634

**Beschreibung:** Die zusammengeführte Call-Liste wird bei Zeile 1293 grundsätzlich durch `sanitize_tool_calls()` geschickt. Die Calls, die der spätere Safety-Net aus sichtbarem Text gewinnt, werden aber direkt an diese Liste angehängt; es findet weder eine erneute Sanitisation noch die Write-Validierung statt. Empirisch wurde ein `write`-Call ohne `content` als echter Tool-Call ausgegeben. Ein `filePath` mit `workspaces/a` blieb im Safety-Net-Pfad unverändert, während der normale Parserpfad ihn umschreibt.

**Auswirkung:** Ein aus dem Safety-Net recoverter Call kann ungültige Argumente, nicht normalisierte Pfade oder nicht bereinigte Steuerzeichen an den Client weiterreichen. Derselbe Modelltext erzeugt je nach Erkennungspfad unterschiedliche Tool-Semantik.

**Empfehlung:** Auch Safety-Net-Calls durch dieselbe kombinierte Sanitize-/Schema-Validierungsfunktion schicken. Nach jedem Merge erneut filtern, indizieren und verwerfen; verworfene Calls als Fehler-/Blocked-Attempt protokollieren.

### T-13 — Hoch: Fehlender oder fehlerhafter Terminalstatus wird als erfolgreicher `stop` maskiert
**Ort:** translator.py:1276-1511, translator.py:1513-1607; Aufrufpfad in glm_client.py:485-486

**Beschreibung:** `finalize()` akzeptiert beliebige Statuswerte und erzeugt bei fehlenden Calls immer `finish_reason="stop"` sowie `[DONE]`. `build_response()` besitzt überhaupt keinen Terminalstatus. Der Upstream-Client finalisiert einen Turn auch dann mit `status="stop"`, wenn kein gültiges Finish-Event angekommen ist. `last_error` wird nur für einen optionalen `intervene_text` verwendet; ein sonstiger Error-/Abbruchstatus geht nicht in die Response ein. Im `intervene`-Zweig wird `intervene_text` außerdem nur auf C0-Zeichen geprüft und direkt als Content angehängt, ohne Tool-Protokoll-, Meta- oder Transcript-Parsing. Empirisch blieb ein JSON-Call-Protokoll in diesem Fehlertext sichtbar.

**Auswirkung:** Ein abgeschnittener Stream, ein Upstream-Error oder ein unvollständiger Tool-Call kann als erfolgreich abgeschlossene Antwort mit leerem/partialem Content beim Client ankommen. Agenten beenden dann den Tool-Loop oder akzeptieren ein Protokollfragment als Antwort. Dies ist die aktuelle Ausprägung des bekannten I-007-Risikos.

**Empfehlung:** Terminalstatus als strikten Vertrag modellieren: EOF ohne Finish/DONE ist ein Fehler, kein `stop`. Nach Upstream-Fehlern weder `[DONE]` noch `finish_reason="stop"` senden; für Non-Stream einen eindeutigen Fehlerstatus zurückgeben.

### T-14 — Mittel (I-008 verifiziert): History-Kompression schützt keine vollständigen Multi-Tool-Runden
**Ort:** translator.py:667-762

**Beschreibung:** Der Pair-Schutz greift nur, wenn ein `tool`-Result auf genau die unmittelbar vorherige Assistant-Nachricht folgt (`i-1`). Bei einem Assistant mit mehreren Calls und mehreren aufeinanderfolgenden Result-Nachrichten wird der erste Result-Block verarbeitet, der nächste aber als eigenständige Nachricht betrachtet. Empirisch wurde aus `assistant(tool_calls 1,2) + tool(1) + tool(2) + user` eine History mit Summary, einem verwaisten `tool(2)` und der letzten User-Nachricht. Außerdem wird die neueste Nachricht, wenn sie das Budget sprengt und nichts Neueres bereits gehalten wurde, als Ausnahme roh übernommen; bei einer einzelnen großen Nachricht greift der Early Return, sodass das Budget ebenfalls nicht hart durchgesetzt wird.

**Auswirkung:** Das Modell erhält verwaiste Tool-Ergebnisse und verliert den Zusammenhang zwischen Call und Result. Das führt zu erneuten Calls, falschen Erklärungen oder Tool-Loop-Schleifen; zusätzlich kann die History-Kompression den Kontext nicht zuverlässig begrenzen.

**Empfehlung:** History in atomare Assistant/Tool-Runden segmentieren und alle Resultate über `tool_call_id` zuordnen. Nach der Kompression validieren, dass jedes Result eine passende Call-ID und umgekehrt eine gültige Result-Beziehung hat. Für eine nicht komprimierbare neueste Nachricht eine explizite Ausnahme mit hartem Gesamtlimit machen.

### T-15 — Hoch: Reparierte Calls verlieren gültige Ergebnisse, verwaiste Ergebnisse werden akzeptiert
**Ort:** translator.py:611-634, translator.py:781-838

**Beschreibung:** `_repaired` wird nicht nur für syntaktisch kaputte Calls gesetzt, sondern für jede semantische Normalisierung, etwa `workspaces/`→`/workspaces/`, Control-Character-Bereinigung oder JSON-String-Umwandlung. `convert_messages()` verwirft dann jedes Tool-Result dieser ID. Ein erfolgreicher Read mit repariertem Pfad verliert so sein Resultat. Umgekehrt wird ein unbekanntes Tool-Result nicht geprüft, wenn `valid_tool_call_ids` noch leer ist; mit einem `name`-Feld wird es als User-Tool-Result serialisiert. Empirisch verschwanden Resultate nach Pfad-/Control-Character-Normalisierung, während ein verwaistes Result mit eigenem Namen in den Prompt gelangte.

**Auswirkung:** Das Modell erhält kein Feedback über einen tatsächlich ausgeführten Schritt und kann denselben Call wiederholen. Ein erfundenes oder blockiertes Resultat kann umgekehrt als vertrauenswürdiger Tool-Output in den Kontext gelangen.

**Empfehlung:** Call- und Result-Beziehung in einem zweistufigen, ID-basierten Pass validieren. Ergebnisse bei semantisch äquivalenter Normalisierung behalten und nur bei nachweislich unbrauchbaren Calls verwerfen; `name`, Reihenfolge und `tool_call_id` müssen zusammenpassen.

### T-16 — Mittel bis Hoch (U-02 verifiziert): `filePath` wird ohne Root- oder URI-Kontext umgeschrieben
**Ort:** translator.py:311-323, translator.py:795-813, translator.py:1325-1343

**Beschreibung:** `workspaces/...` wird blind auf `/workspaces/...` und `benchmark/...` auf `/workspaces/benchmark/...` gesetzt. Es gibt keine Root-, Existenz-, Schema- oder Canonical-Path-Prüfung; `..` und `//` werden nicht aufgelöst. Zusätzlich ist die URI-Schleife fehlerhaft: `file:/tmp/x` wird durch `fp[6:]` zu `tmp/x`, während `file:///tmp/x` korrekt `/tmp/x` ergibt. Die Reparatur gilt für History-Calls und alle Tools mit einem `filePath`-Feld; der Safety-Net-Pfad kann sie sogar umgehen.

**Auswirkung:** Ein absichtlich relativer oder anders verwurzelter Pfad erhält eine andere Semantik. Ein `file:/`-Pfad kann relativ im aktuellen Arbeitsverzeichnis landen; `workspaces/../...` kann auf einen anderen Root zeigen. History kann semantisch umgeschrieben oder ein Pfad beim Safety-Net unverändert weitergereicht werden.

**Empfehlung:** URI-Scheme mit einer URL-Parser-API behandeln, den Pfad anschließend gegen den tatsächlich konfigurierten Root canonicalisieren und traversal-sicher validieren. Nur für explizit dateibasierte Tools anwenden und nach jeder Call-Quelle dieselbe Sanitisation erzwingen.

### T-17 — Mittel (U-01 verifiziert): Meta-Chatter-Filter ist all-or-nothing, stream-only und semantisch inkonsistent
**Ort:** translator.py:432-491, translator.py:1377-1393, translator.py:1557-1563

**Beschreibung:** `strip_meta_chatter()` entfernt ganze Zeilen anhand harter, sprachabhängiger Substrings. Mit Calls wird der verbleibende Text gefiltert, aber ohne Calls wird der Originaltext nur dann verworfen, wenn das Filterergebnis komplett leer ist. Bereits emittierte Stream-Deltas werden nicht zurückgenommen. `build_response()` ruft den Helper überhaupt nicht auf.

**Auswirkung:** Legitime Zeilen mit Wörtern wie `open ist nicht`, `tool call attempt:` oder `open` können still verschwinden; eine teilweise passende Antwort bleibt meta-artig zurück. Stream und Non-Stream liefern für denselben Modelltext unterschiedliche Inhalte. Der Filter ist keine verlässliche Garantie gegen Tool-Protokoll-Leaks.

**Empfehlung:** Hartcodiertes Keyword-Stripping aus Nutzerantworten entfernen oder durch strukturierten Turn-State ersetzen. Wenn eine Bereinigung gewollt ist, muss sie vor jeder irreversiblen Stream-Ausgabe und identisch in beiden Response-Pfaden erfolgen.

### T-18 — Mittel: `tool_choice=required` und spezifische Auswahl werden nur in den Prompt geschrieben
**Ort:** translator.py:637-660, translator.py:848-874

**Beschreibung:** `parse_tool_choice_policy()` erzeugt lediglich Prompttext. Der Accumulator erhält keine Choice-Policy und erzwingt weder `required` noch eine konkrete Funktion; auch `none` verhindert die nachgelagerte Parser-/Native-Extraktion nicht. Empirisch blieb ein Modell-Text `No tool needed.` bei `required` und bei einer spezifischen `read`-Choice mit `finish_reason="stop"` und ohne Tool-Call. Ungültige Choice-Werte werden außerdem still zu `auto`; bei leerer Allowlist kann eine spezifische Choice als gültig erscheinen.

**Auswirkung:** Der OpenAI-Vertrag wird nicht eingehalten. Der Client kann einen Turn als finale Textantwort behandeln, obwohl zwingend ein Tool ausgeführt werden sollte; das fördert genau die beobachtete Vermischung von Textantwort und Tool-Loop.

**Empfehlung:** Choice-Policy bis zum Accumulator durchreichen und die finale Antwort gegen sie validieren. Nicht unterstützte oder leere Auswahlen kontrolliert ablehnen; `required` und spezifische Tools nicht nur als Modellhinweis behandeln.

### T-19 — Mittel: Part-Merge verliert Status und dupliziert Non-Text-Inhalte
**Ort:** translator.py:94-149, translator.py:1047-1061

**Beschreibung:** `incoming_status` wird berechnet, aber nie in das zusammengeführte Part geschrieben; `merged` startet als Kopie des ersten Parts. Dadurch bleibt ein Initial-Status wie `init` erhalten, auch wenn ein Finish-Part `finish` liefert. Non-Text-Items aus Incoming werden bei jedem Update erneut an die bereits gespeicherte Liste angehängt. Das ist für Bildstatus außerhalb dieser Datei direkt relevant und erzeugt außerdem unbegrenztes Wachstum bei wiederholten Image-/Tool-Parts.

**Auswirkung:** Fertige Bild-Parts können downstream verworfen werden. Wiederholte Native-Parts verbrauchen Speicher und werden bei nicht exakter Signatur-Deduplizierung mehrfach verarbeitet. Reasoning-/Text- und Non-Text-Status können nicht konsistent aus demselben Part gelesen werden.

**Empfehlung:** Status und relevante Metadaten aus dem tatsächlich letzten Finish-Event kontrolliert übernehmen. Non-Text-Items nach einer stabilen Item-ID oder strukturellem Schlüssel idempotent mergen und die Part-Anzahl begrenzen.

### T-20 — Mittel: Vollständiges Rendern pro Event ist quadratisch und Logic-IDs werden lexikografisch sortiert
**Ort:** translator.py:1047-1053, translator.py:1178-1180, translator.py:1619-1703

**Beschreibung:** Jedes neue Part-Event setzt den Cache dirty; `_render_full_output()` und `_compute_deltas()` durchlaufen danach sämtliche bekannten Logic-IDs und den gesamten akkumulierten Text. `insort()` sortiert Logic-IDs als Strings, nicht nach Ereignisreihenfolge. Empirisch benötigten 1.000 eindeutige Parts in der In-Memory-Simulation etwa 3,47 s, 3.000 Parts etwa 74,1 s. Bei Ereignisreihenfolge `2`, danach `10` wurde die Ausgabe als `10`, dann `2` gerendert.

**Auswirkung:** Lange Streams können CPU und Latenz stark erhöhen; bei ausreichend vielen Parts drohen Timeouts. Nummerisch/UUID-artige Logic-IDs können Text- und Tool-Reihenfolge gegenüber der Upstream-Reihenfolge verändern, wodurch Antworten oder Calls semantisch falsch zugeordnet werden.

**Empfehlung:** Logic-IDs eine monotone Sequenz zuordnen und die Append-Reihenfolge speichern. Nur geänderte Parts neu rendern und Delta-Indizes inkrementell fortschreiben; Text-/Reasoning-Caches pro Logic-ID getrennt aktualisieren.

### T-21 — Mittel: Native-Open-Mapping ist verlustbehaftend und mehrdeutig
**Ort:** translator.py:387-415, translator.py:567-573

**Beschreibung:** `map_native_open_tool_call()` verarbeitet bei einer `open`-Liste nur `open[0]`; weitere Ziele werden verworfen. Ein Ziel wie `example.com` wird wegen des Punktregex als `read` behandelt, nicht als URL, während ein explizites `https://…` zu `webfetch` wird. `map_native_sandbox_tool_call()` erzeugt außerdem einen Here-Doc mit dem festen Delimiter `EOF`; Code, der eine eigene Zeile `EOF` enthält, kann den Wrapper verlassen und nachfolgende Shell-Zeilen ausführen.

**Auswirkung:** Mehrere Ziele können verschluckt, URLs können als lokale Dateien gelesen und Sandbox-Code kann unbeabsichtigt als Shell-Code außerhalb des beabsichtigten Python-Blocks ausgeführt werden.

**Empfehlung:** Native Open- und Sandbox-Argumente streng typisieren und mehrdeutige Ziele ablehnen oder explizit klassifizieren. Bei mehreren Zielen atomare Calls erzeugen. Für Here-Docs ein nicht im Code vorkommendes, zufälliges Delimiter verwenden oder den Code anderweitig sicher quoten.

### T-22 — Niedrig: Finalisierung ist nicht idempotent und kann deferred Text ohne Grenze zusammenkleben
**Ort:** translator.py:1276-1307, translator.py:1513-1607

**Beschreibung:** Es gibt keinen `finalized`-Status und keinen Guard gegen mehrfaches `finalize()`. Ein zweiter Aufruf gibt dieselben serverseitigen/gespeicherten Parser-Calls erneut aus. Außerdem wird `self._deferred_visible_text + tail_text` ohne Grenzseparator zusammengesetzt; bei deferred `Hello` und Tail `world` entsteht `Helloworld`.

**Auswirkung:** Bei einem versehentlich doppelten Finalize-/Renderpfad können Calls oder Text doppelt an den Client gehen. Der Separatorverlust kann normale Antworten beschädigen.

**Empfehlung:** Finalisierung als einmalige Zustandsübergangs-Operation mit eingefrorem Result-State implementieren. Deferred-Chunk-Grenzen erhalten und die Zusammenführung mit einem expliziten Kontext-/Whitespace-Regelwerk durchführen.

### T-23 — Mittel: Argument-Recovery und Content-Extraktion ändern Daten oder brechen bei Schemafehlern ab
**Ort:** translator.py:152-173, translator.py:258-279, translator.py:299-339

**Beschreibung:** `extract_text_content()` ruft bei `image_url`/`file_url` ungeprüft `.get()` auf und kann bei einem String statt einem Dictionary mit `AttributeError` abbrechen. Die statische Typprüfung meldet in den betroffenen Translator-Ausdrücken zusätzlich den Zugriff auf `.get()` bei `object` (aktuell translator.py:773, 801, 807). `repair_raw_tool_args()` nimmt für `content`/`command` das letzte Quotezeichen des gesamten Raw-Objekts; ein nachfolgender Parameter wird dadurch in den Stringwert aufgenommen. Das wurde mit `content:"hello","other":"z"` reproduziert. Die generische Umwandlung von JSON-ähnlichen Strings in Objekte/Arrays erfolgt ohne Tool-Schema und kann legitime Stringparameter falsch typisieren; `{"param_name":"url"}` wird ohne Fallback zu `{}` und als potenziell ungültiger Call weitergereicht.

**Auswirkung:** Fehlerhafter Content kann als Serverfehler enden; Raw-Recovery kann Dateiinhalte oder Shell-Commands beschädigen; schema-konforme Stringwerte können in falsche JSON-Typen umgewandelt werden. Das begünstigt anschließend leere, verschluckte oder falsch ausgeführte Calls.

**Empfehlung:** Vor jedem Zugriff eine strenge Content-/Tool-Schema-Validierung einführen. Raw-Felder mit einem JSON-/AST-Scanner statt `rfind()` zerlegen. JSON-String-Normalisierung nur anhand des jeweiligen Parameter-Schemas durchführen und Calls ohne erforderliche Argumente verwerfen oder als Fehler markieren.

### T-24 — Hoch (I-015 verifiziert): Ausgabe- und Sampling-Parameter werden nicht upstream durchgesetzt
**Ort:** translator.py:910-925 (Parameter-Weiterleitung fehlt); tatsächlicher Upstream-Body glm_client.py:776-794

**Beschreibung:** Der Translator verarbeitet `reasoning_effort`, `deep_research` und `web_search`, aber keine `max_tokens`, `temperature`, `top_p` oder Stop-Sequenzen. Der tatsächliche Request-Body in `glm_client.py` enthält nur Assistant-/Conversation-/Messages-/Meta-Daten. Damit bleibt I-015 im aktuellen Stand unverändert; die Annahme der API-Parameter ist nicht gleich ihre Durchsetzung.

**Auswirkung:** Clients können keine Output-Grenze, Sampling-Einstellungen oder Kosten-/Längenlimits verlässlich durchsetzen. Das kann zu unerwartet langen Tool-/Textantworten und zusätzlichen Runden führen.

**Empfehlung:** Unterstützte Felder explizit validieren und upstream abbilden oder mit einem dokumentierten Fehler ablehnen. Wenn das Upstream sie nicht unterstützt, dürfen sie nicht stillschweigend als erfüllt behandelt werden.

## Positiv

- `sanitize_control_characters()` und `_sanitize_value_control_chars()` ersetzen C0/DEL in normalen Tool-Argumenten und sichtbarem Content, behalten Newline/Tab/CR sowie gültiges UTF-8 bei. Die vorhandenen Regressionstests dafür sind grün.
- Der Standardpfad für einen vollständigen, erlaubten JSON- oder DSML-Call erzeugt strukturierte `tool_calls` und unterdrückt den Protokolltext im finalen Non-Stream-Content. Der einfache Final-Text wird bei `all_tool_calls` korrekt auf `content=None` gesetzt.
- Die Text-Delta-Längenfortschreibung verhindert im üblichen Happy Path (`Token-Snippets` plus Finish-Volltext mit passendem Präfix) eine doppelte Ausgabe.
- Die native Signatur-Normalisierung sortiert JSON-Argumente und erkennt exakte historische Echo-Signaturen; die absichtlich echoartigen, exakten Duplikate im Native-Kanal werden damit abgefangen.
- `safe_json_dumps()` erzeugt gültige, kompakte JSON-Ausgaben; die normalen, nach dem Merge ausgeführten Tool-Calls werden in beiden Finalisierern nochmals sanitized und neu indiziert.
- Die Tool-Schema-/Format-Prompts und der abschließende Format-Reminder werden bei deklarierten Tools und `tool_choice != none` erzeugt.
- Die vorhandenen 150 Tests bestehen; sie decken allerdings die oben konstruierten Split-Stream-, Mixed-Call-, Fence-, Reasoning- und Multi-Result-Fälle nicht bzw. nicht mit den beobachteten Fehlverhalten ab.

## Geprüft und unauffällig

- Die komplette Datei wurde ohne Auslassung bis Zeile 1713 gelesen; die angrenzenden Parser-/Clientpfade wurden nur zur Verifikation der Target-Integration herangezogen.
- Vollständige klassische JSON-Protokolle mit erlaubtem Toolnamen werden im Final-Pfad als Calls erkannt; der `[]`-Terminator wird nicht als sichtbarer Rest ausgegeben.
- Vollständige DSML-/XML-Aufrufe mit erlaubten Namen werden im Final-Pfad extrahiert; die getesteten malformed Close-Tag-Varianten bleiben im normalen Fall parsebar.
- Die C0-Bereinigung wird auf sichtbare Stream-Deltas, finalen sichtbaren Text, `intervene_text` und normale Tool-Argumente angewendet.
- Bei einem gültigen `all_tool_calls`-Ergebnis wird der noch nicht emittierte `final_text` in `finalize()` nicht als Content gesendet; die Einschränkung ist nur die bereits emittierte Präambel aus T-07.
- Exakte, erlaubte Calls werden im normalen XML-/JSON-Pfad gegen `allowed_tool_names` gefiltert; die nicht abgedeckten Formen sind in T-02 und T-10 dokumentiert.
- Ein einzelner unmittelbarer Assistant-/Tool-Result-Paarblock wird im getesteten Kompressionsfall zusammen gehalten; der Multi-Result-Fall ist als T-14 erfasst.
- Die harte Blockliste wird für die getesteten exakt geschriebenen Native-Namen (`open_url`, `execute_sandbox_code`, `sandbox`, `run_code`) im Standardpfad erkannt; Case- und Metadata-Varianten sind in T-11 dokumentiert.
- Es wurden keine Netzwerkaufrufe, kein Upstream-Server und keine externen Accounts benutzt. Die einzige Verifikation mit Ausführung war die lokale, read-only In-Memory-Suite.
