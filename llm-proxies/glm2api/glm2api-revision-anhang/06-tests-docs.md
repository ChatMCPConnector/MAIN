# 06 — tests/, benchmarks/, pyproject.toml, .env.example

(Scope: **3.886 Zeilen** vollständig mit `Read` in Chunks gelesen: `tests/test_tool_parser.py` 793, `tests/test_translator.py` 1.438, `tests/test_stream_retry.py` 497, `tests/test_protocol_adapters.py` 378, `tests/test_config.py` 53, `tests/test_model_variants.py` 67, `benchmarks/verify_auditmesh.py` 476, `pyproject.toml` 23 und `.env.example` 161 Zeilen. Ergänzende read-only In-Memory-Probes wurden gegen Parser, Accumulator, Konfiguration und Paket-Metadaten ausgeführt. Keine Projektdatei wurde geändert.)

## Testlauf

- `uv run pytest tests/ -q` → **150 passed in 1.33s**.
- Verteilung: 48 Parser-, 60 Translator-, 15 Retry-, 16 Adapter-, 3 Config- und 8 Modellvarianten-Tests.
- Ergebnis: Die Suite ist grün, deckt den gemeldeten Kernfehler aber an den entscheidenden Stream-Grenzen, Abbruchpfaden und gemischten Tool-Runden nicht ab.

## Test-Coverage-Lücken

### Abdeckungsinventar

| Bereich | Tatsächlich getestetes Verhalten | Referenz | Bewertung |
|---|---|---|---|
| JSON-Tool-Parser | Wrapper als Array/Objekt, flache Parameter, fehlende Array-Klammer, Duplikat-/Snipsel-Wiederherstellung, unbalancierte Multi-Calls, `[]`-Terminator mit Whitespace, native Allowlist-Filterung | `tests/test_tool_parser.py:6-218`, `:506-525` | Gute Unit-Abdeckung für den klassischen Happy Path; einzelne Reparaturfixture, keine systematische Grenzprüfung. |
| DSML/XML | Standard- und malformed Varianten, verschachtelte Parameter, CDATA-Reparatur, Code-Fence-Schutz, ausgewählte zeichenweise Streams | `tests/test_tool_parser.py:72-140`, `:221-416` | Die getesteten vollständigen Blockformen sind gut abgedeckt; partielle/alternative Formen bleiben Lücken. |
| Bare Calls | Bare Array, führendes Komma, nacktes Write-Objekt und Text-Funktionsaufruf werden im **Final Parser** getestet; Streaming nur für ausgewählte Bare-Array-Splits | `tests/test_tool_parser.py:538-723` | Bare Object und Text-Funktionsaufruf sind im Streampfad nicht abgedeckt. |
| Transcript-Echo | Vollständige Echo-Zeile im Parser und Non-Stream-Accumulator; ein handgewählter Chunk-Split | `tests/test_tool_parser.py:738-767`, `tests/test_translator.py:1385-1438` | Nur ein günstiger Split; echte Präfix- und Tokengrenzen fehlen. |
| Translator/Accumulator | Kanonische JSON-/DSML-Calls, Reasoning-Fallback, Preamble-Unterdrückung, Native-Echo/Dedup, Argument-Sanitisation, History-Kompression, Usage und sichtbare Control-Character | `tests/test_translator.py:68-238`, `:310-338`, `:607-666`, `:893-1162` | Viele echte Komponentenverhaltensweisen, aber kaum derselbe Payload über Stream und Non-Stream. |
| Retry/Follow-up | Transient-Event, Give-up, Non-Transient, Fehler nach Content, Stream-/Non-Stream-Retry, Empty-/Reasoning-Retry, Follow-up-Budget und einfacher SSE-CRLF-Split | `tests/test_stream_retry.py:113-192`, `:270-497` | Happy Paths sind gut abgedeckt; Truncation, Transportabbruch, gemischte Calls und Follow-up-Retrykontext fehlen. |
| Protokolladapter | Request-Grundkonvertierung, Text-SSE, Heartbeats, Error-/Finish-Idempotenz, einfache Tool-Choice-Varianten | `tests/test_protocol_adapters.py:35-171`, `:174-378` | Kein vollständiger Tool-Call- oder Tool-Result-Roundtrip über Anthropic/Responses. |
| Config/Modelle | Refresh-Token-Fallback, Conversation-Flags, Logging-Regression, Suffix-/Chat-Mode-Matrix und Exposure einzelner Modelle | `tests/test_config.py:7-53`, `tests/test_model_variants.py:10-67` | Eng, aber für die vielen dokumentierten Defaults und Parser-Schnittstellen nicht ausreichend. |

### D-01 — Hoch: Der „Deferral“-Test lässt das rohe Tool-Präfix tatsächlich sichtbar durch
**Ort:** `tests/test_translator.py:366-383`
**Beschreibung:** Der Test heißt `test_accumulator_defers_text_while_tool_protocol_pending`, behauptet aber nur `assert '{"tool' in combined or 'tool' in combined`. Da `tool` bereits im Fixture enthalten ist, ist die rechte Alternative erfüllt. Eine read-only Reproduktion mit exakt diesem Fixture erzeugt im ersten SSE-Delta sichtbaren Content `sieh '...'} before {"tool`; der Test besteht dennoch.
**Auswirkung:** Die Suite signalisiert Schutz vor einem Tool-Protokoll-Leak, obwohl genau der für den Nutzer relevante Fall als normaler Assistant-Content emittiert wird.
**Empfehlung:** Den Test durch exakte Inhalts- und Negativ-Assertions ersetzen: Kein Chunk darf `{"tool`, `tool_calls` oder einen partiellen Call enthalten; der normale Präfix muss exakt erhalten bleiben. Ein zweiter Test muss ein nachfolgendes vollständiges Event liefern und genau einen strukturierten `bash`-Call ohne rohen Rest erwarten.

### D-02 — Hoch: Bare/Whitespace-JSON ist nur im Final Parser getestet; reale Token-Chunks lecken
**Ort:** `tests/test_tool_parser.py:538-723`, insbesondere `:591-604`, `:655-690`, `:694-723`
**Beschreibung:** Bare Objects ohne Wrapper/Array und ein Text-Funktionsaufruf werden nur mit `parse_tool_calls_from_text()` geprüft. Die Streaming-Tests decken nur Bare Arrays mit zwei handgewählten Splitpunkten ab. Eine zeichenweise gesendete Bare-Object-Payload wurde vollständig als Text ausgegeben und ergab null Calls; dieselbe Probe mit einem pretty-formatierten `tool_calls`-Wrapper verhielt sich ebenso. Bei allen möglichen Zwei-Chunk-Splits scheiterten 7/73 Bare-Object- und 2/46 Bare-Array-Payloads; Compact-JSON in genau zwei Chunks bestand dagegen.
**Auswirkung:** Ob ein echter Call beim Client ankommt oder als Antwort erscheint, hängt von Upstream-Tokenisierung und Whitespace ab. Genau diese Chunk-Sensitivität ist im gemeldeten Fehlerbild relevant.
**Empfehlung:** Eine gemeinsame Matrix für Wrapper, Pretty-Wrapper, Bare Array, Bare Object und verkürzte Parameterform gegen **alle** Zwei-Chunk-Splitpunkte sowie 1-, 2-, 3- und zeichenweise Chunks ergänzen. Für Stream und Non-Stream dieselbe Fixture verwenden und sowohl `visible == ""`/exakte Prosa als auch Call-Name und Argumente prüfen.

### D-03 — Hoch: Abgeschnittenes JSON wird weder vollständig konsumiert noch als Fehler vertraglich getestet
**Ort:** `tests/test_tool_parser.py:63-69`, `:726-793`; zusätzlich fehlende Client-/Endpoint-Fälle in `tests/test_stream_retry.py`
**Beschreibung:** `test_truncated_bare_call_is_held_back_and_never_streamed_as_text` ruft nur `consume()` auf, prüft weder `flush()` noch den finalen Terminalstatus. Der Helper-Test verwendet ausschließlich ein Bare-Objekt und einen Start am Zeilenanfang. Weder `{"tool_calls": ...` noch ein Inline-Fragment nach Prosa laufen durch Client, Accumulator und beide Finalizer. Eine read-only Probe mit `Prefix {"tool_calls":[{"name":"bash","arguments":{"command":"pwd"` ergab sowohl im Stream als auch Non-Stream exakt das rohe Fragment als Content, null Calls und `stop`.
**Auswirkung:** Ein abgebrochener Upstream-Turn wird als scheinbar erfolgreiche Antwort weitergereicht. Der Agent kann den Text akzeptieren, obwohl ein Toolcall gemeint war.
**Empfehlung:** Einen End-to-End-Test mit Fragment im Raw-SSE, anschließendem EOF ohne Finish und alternativ explizitem `finish` ergänzen. Erwartung: kein roher JSON-Text, kein `stop`/`[DONE]` bei unvollständigem Protokoll, sondern begrenzter Retry oder ein strukturierter `truncated_stream`-Fehler. Wrapper, Bare Object und Fragment nach Prosa getrennt abdecken.

### D-04 — Hoch: Der Transcript-Echo-Test testet nur einen nicht fehleranfälligen Chunk-Split
**Ort:** `tests/test_tool_parser.py:738-756`; `tests/test_translator.py:1408-1438`
**Beschreibung:** Der vermeintliche Boundary-Test liefert `User: [{"call_id":...` als kompletten Anfangs-Chunk. Frühe Teilungen innerhalb `U`, `Us`, `User:`, `User: [` usw. fehlen. Von 58 Zwei-Chunk-Partitionen derselben Payload leckten 7; zeichenweises Streaming gab das komplette Echo aus. Der Translator-Test ist Non-Stream und vollständig ungeteilt.
**Auswirkung:** Halluzinierte `User:`/`Assistant:`-Toolresultate können bei normaler Tokenisierung als Antwort erscheinen. Der vorhandene Regressionstest schützt nur exakt seinen Chunkplan.
**Empfehlung:** Für `User` und `Assistant`, Groß-/Kleinschreibung und alle Präfix-Splitpunkte parametrisieren. Zusätzlich den kompletten `GLMEventAccumulator` streamen und prüfen, dass `call_id`, `name` und `content` des Echos in keinem Content-Delta erscheinen, während nachfolgende echte Prosa erhalten bleibt.

### D-05 — Hoch: Mixed allowed/blocked Calls sind vollständig ungetestet
**Ort:** `tests/test_tool_parser.py:108-126`, `:506-525`; `tests/test_stream_retry.py:199-388`; `tests/test_translator.py:620-696`
**Beschreibung:** Vorhanden sind nur blocked-only beziehungsweise undeclared-only sowie einzelne Native-Calls. Es fehlt ein Turn mit erlaubtem und blockiertem Call gleichzeitig. Eine Probe mit `bash` plus `open_url` lieferte in beiden Finalpfaden nur `bash`; `blocked_tool_attempt_names` blieb leer. Obwohl `detect_tool_call_names()` beide Namen separat erkennt, wird die Detection im Accumulator bei vorhandenen erlaubten Calls nicht ausgeführt. Native Mixed-Calls und gemischte Bare-/Wrapper-Formen fehlen ebenso.
**Auswirkung:** Der blockierte Teil kann still verschwinden, der Client erhält keine negative Tool-Rückmeldung und das Modell kann den verbotenen Call erneut versuchen. In der umgekehrten Native-Reihenfolge kann ein gültiger Call durch den Follow-up-Entscheid verloren gehen.
**Empfehlung:** Für JSON-Wrapper, Bare Array, DSML und Native Parts je eine Mixed-Call-Matrix in Stream und Non-Stream ergänzen. Der gewünschte Vertrag muss explizit sein: erlaubte Calls bleiben erhalten, blockierte Namen werden verlustfrei bilanziert, und die negative Rückmeldung darf keinen gültigen Call verwerfen.

### D-06 — Hoch: Es fehlt eine echte Stream-/Non-Stream-Paritätsmatrix für genau die fehleranfälligen Payloads
**Ort:** `tests/test_tool_parser.py:6-793`; `tests/test_translator.py:68-238`; `tests/test_protocol_adapters.py:87-171`, `:307-378`
**Beschreibung:** Die beiden Pfade werden separat mit verschiedenen Payloads getestet, nie mit derselben Matrix. Eine kompakte JSON-Fence-Payload erzeugt im Stream einen `bash`-Call, im Non-Stream jedoch `content="```json"` und keinen Call. `read("/tmp/a.py")` wird im Final Parser als Call erkannt, im Stream dagegen als normaler `stop`-Text. Pretty JSON, Bare Calls, Truncation, Transcript-Echo und Mixed Calls zeigen dieselbe strukturelle Lücke.
**Auswirkung:** Derselbe Modellturn verhält sich je nach angefragtem Stream-Flag semantisch verschieden. Der Client kann Text als Toolcall ausführen oder einen strukturierten Call als Text darstellen.
**Empfehlung:** Eine gemeinsame Fixture-Matrix definieren und für jede Payload beide öffentlichen Wege `finalize()` und `build_response()` vergleichen: identische Call-Namen/Argumente, identische bereinigte Prosa und äquivalenter Finish-Status. Die Matrix sollte anschließend durch die drei HTTP-Adapter laufen.

### D-07 — Hoch: Anthropic/Responses und der HTTP-Handler besitzen keinen Tool-Call-Roundtrip-Test
**Ort:** `tests/test_protocol_adapters.py:35-171`, `:174-378`
**Beschreibung:** Die Adapter-Tests decken Text, SSE-Envelopes, Heartbeats und Fehler ab, aber keinen strukturierten `tool_calls`-Delta in Non-Stream oder Stream und keinen Tool-Result-Turn. Der Responses-Test verwendet für eine spezifische Choice bereits die interne OpenAI-Form `{"type":"function","function":{"name":...}}` statt der flachen Responses-Form mit `name`; Anthropic `tool_choice: none` fehlt vollständig. Die HTTP-Tests prüfen nur Heartbeat plus Text.
**Auswirkung:** Ein Adapter oder Route kann einen vom Accumulator korrekt erzeugten Call in Text, ein falsches Event oder eine falsche Toolresult-Historie umwandeln, während die komplette Suite grün bleibt.
**Empfehlung:** Je Adapter mindestens einen vollständigen Tool-Call-/Tool-Result-Roundtrip über den realen HTTP-Handler testen: Request-Declaration, erzeugtes strukturiertes Call-Event, Folge-Request mit Result und Folgeantwort. Spezifische/none/required Choices mit den tatsächlichen API-Formen und ungültigen Formen abdecken.

### D-08 — Hoch: Mehrere Tests schreiben blockierte Tool-Versuche als normale erfolgreiche Antwort fest
**Ort:** `tests/test_translator.py:98-143`, `:386-413`; `tests/test_stream_retry.py:348-369`
**Beschreibung:** Die Tests verlangen bei deaktiviertem Follow-up-Budget ausdrücklich sichtbaren Content mit `unavailable tool`/`undeclared tool` und `finish_reason="stop"`. Der Retry-Test nennt das Verhalten korrekt „blocked notice forwarded as text“. Damit ist der aktuelle Fehler-Fallback als scheinbar finale Assistant-Antwort Teil des Testvertrags.
**Auswirkung:** Ein Agent kann eine Tool-Störung als fachliche Antwort akzeptieren und die Tool-Runde beenden. Tests, die diesen Fehlerzustand verbindlich auf `stop`/Text festlegen, erschweren genau die Korrektur des Kernproblems.
**Empfehlung:** Zuerst das gewünschte externe Fehlervertrag festlegen. Empfohlen sind ein strukturierter Tool-Failure-/Retry-Status und kein normaler `stop`-Text. Falls ein Text-Fallback bewusst gewollt ist, sollte er zumindest als Warnung mit stabiler Fehlerkennung und nicht als erfolgreiche finale Antwort modelliert werden; die Tests entsprechend ändern.

### D-09 — Hoch: Der AuditMesh-Verifier prüft das Kernsymptom nicht
**Ort:** `benchmarks/verify_auditmesh.py:24-45`, `:131-159`, `:452-471`
**Beschreibung:** Der Verifier prüft Dateien, Fixture-Inhalte, Pipeline-Metriken und eine mutierte Kopie. Er erhält weder Assistant-Text-Parts noch Tool-Parts einer OpenCode-Session und prüft weder rohe `tool_calls`-/Bare-Array-Protokolle noch blockierte Calls, Call-Parität oder vorgeschriebene Tool-Nutzung. Die erwähnten Proxy-Signale liegen vollständig außerhalb dieses ausführbaren Verifiers.
**Auswirkung:** Ein Lauf kann die erzeugten Dateien und Metriken korrekt abschließen und `OK AuditMesh benchmark verified` melden, obwohl der Nutzer während des Laufs Toolprotokoll als Antwort gesehen hat. Der Benchmark bestätigt damit nicht die behauptete Proxy-Anomalie-Freeheit.
**Empfehlung:** Dem Benchmark einen ausführbaren Session-Part-Check geben: exportierte Text-Parts auf keinerlei rohe Call-Protokolle prüfen, Calls gegen deklarierte Tools validieren, erlaubte/blockierte Calls und Tool-Abdeckung bilanzieren und den Exit-Code dieses Checks in das Gesamtergebnis einbeziehen.

### D-10 — Mittel: Der Verifier prüft nur Testdateinamen und besitzt keine Selbsttests
**Ort:** `benchmarks/verify_auditmesh.py:41-44`, `:131-159`, `:169-237`
**Beschreibung:** `REQUIRED_FILES` verlangt drei Testdateien, aber `run_pipeline()` führt nur `python -m auditmesh` aus. Leere oder bewusst schwache Dateien mit den richtigen Namen erfüllen den Verifier. Zwar verlangt der separate Benchmark-Workflow zusätzlich `pytest`, diese Ausführung ist aber nicht in den Exit-0-Vertrag des geprüften Verifiers eingebunden. Im geprüften Projekt gibt es außerdem keine Tests für `verify_auditmesh.py` selbst, seine Parser, Snapshot-Logik oder erwarteten Fehlerfälle.
**Auswirkung:** Der Benchmark kann seine Exit-0-Bedingung als vollständige Testabnahme ausgeben, obwohl die generierte Testsuite nicht ausgeführt wurde oder der Oracle selbst regressiert.
**Empfehlung:** Im Verifier die generierte Pytest-Suite mit Timeout und Exit-Code ausführen. Für den Oracle mindestens Mutationstests ergänzen: fehlende Datei, manipulierte Metrik, veränderte Source-Datei, kaputter Markdown-Link und absichtlich fehlerhafte Fixture-Struktur müssen jeweils mit exit code 1 scheitern.

## Konfigurations-Drift

### D-11 — Mittel: `.env.example` deckt alle AppConfig-Variablen ab, driftet aber beim Betriebsport und Log-Pfad
**Ort:** `.env.example:14-18`, `.env.example:24-30`; Vergleich zu `src/glm2api/config.py:275-316` und `src/glm2api/logging_utils.py:186-198`
**Beschreibung:** Der AST-/Text-Abgleich ergab **31/31** über `AppConfig` gelesene Variablen in `.env.example`; keine fehlt und kein Beispiel-Key ist unbekannt. Code und Beispiel verwenden jedoch `PORT=8000`, während Betriebsvorlage, Start-/Smoke-Skripte und der dokumentierte Proxy-Vertrag Port 8001 verwenden. Zusätzlich liest `logging_utils.py` direkt `GLM2API_LOG_DIR` aus `os.environ`; diese Variable fehlt im Beispiel und kann über die kopierte `.env` nicht wirksam werden, weil `load_config()` Dateiwerte nicht in `os.environ` exportiert. `tests/test_config.py` vergleicht weder Beispiel-Keys noch Defaults mit dem Betriebsvertrag.
**Auswirkung:** Ein aus `.env.example` erzeugter Direktstart kann auf 8000 lauschen, während OpenCode und die Startskripte 8001 erwarten. Ein über die Datei gesetzter Log-Pfad würde still ignoriert.
**Empfehlung:** Portdefault und Beispiel auf den kanonischen Betriebswert 8001 synchronisieren oder einen expliziten, dokumentierten Zwei-Default-Vertrag einführen. `GLM2API_LOG_DIR` entweder als bewusst nur exportierbare Prozessvariable in der Nutzer-Doku aufnehmen oder als `AppConfig`-Feld aus `.env` laden. Einen Paritätstest über alle Beispiel-Keys, Code-Defaults und den kanonischen Betriebsdefault ergänzen.

### D-12 — Niedrig: Build-Abhängigkeiten sind nicht vollständig gepinnt und die Testkonfiguration erzwingt keine Abdeckung
**Ort:** `pyproject.toml:1-3`, `pyproject.toml:16-23`
**Beschreibung:** Die Runtime-Dependency-Liste ist für den Standardbibliotheck-Code korrekt leer. `uv.lock` pinnt aktuell `pytest` auf 9.1.1, Build-Backend und `wheel` sind im Manifest jedoch nur mit offenen Untergrenzen angegeben und nicht als gelockte Projektpakete vorhanden. Die Pytest-Konfiguration besteht nur aus `pythonpath=["src"]`; es gibt weder Coverage-Gate noch CI-/Timeout-Konfiguration.
**Auswirkung:** `uv run`/`uv sync --frozen` ist heute reproduzierbar, aber ein späterer Build kann je nach aufgelöstem Build-Frontend eine inkompatible Setuptools-Version wählen. Hohe Critical-Path-Coverage kann vollständig regressieren, ohne den Testlauf zu beeinflussen.
**Empfehlung:** Build-Anforderungen auf eine kompatible, getestete Range begrenzen und den Build-Kontext mitpinnen. Kritische Parser-/Clientmodule mit Branch-Coverage und einem Mindestwert für die Tool-Protokollpfade absichern; die 150 grünen Tests allein sind dafür zu grob.

### D-13 — Niedrig: Config-Tests sind nicht vollständig von Prozess- und Logging-Globalzustand isoliert
**Ort:** `tests/test_config.py:26-53`
**Beschreibung:** `test_persistent_conversation_flag()` entfernt keine relevanten Prozessvariablen; `load_config()` priorisiert jedoch `os.environ` über die Datei. `test_setup_logging_removes_load_config_bootstrap_handler()` leert und ersetzt globale Root-Logger-Handler, ohne den Ausgangszustand wiederherzustellen.
**Auswirkung:** In einer anderen Testreihenfolge oder CI-Umgebung können Umgebungsvariablen bzw. Log-Capture das Ergebnis beeinflussen. Aktuell lief die Suite in der Standardreihenfolge ohne Fehler.
**Empfehlung:** Für jeden Config-Test relevante Env-Variablen per `monkeypatch` entfernen und einen Autouse-Fixture zum Sichern/Wiederherstellen von Logger-Handlern und Levels verwenden. Parameterisiert zusätzlich alle dokumentierten Boolean-/Numeric-Defaults und ungültigen Eingaben.

## Positiv

- Die 150 Tests prüfen überwiegend reales Komponentenverhalten und nicht nur Mock-Aufrufzähler: konkrete Tool-Argumente, sichtbaren Content, `finish_reason`, SSE-Payloads, Follow-up-Texte und Response-Felder werden exakt geprüft.
- Klassische JSON-Calls, Snipsel+Volltext-Duplikat, fehlende Array-Klammer, unbalancierte Multi-Calls, Terminator-Whitespace sowie erlaubte DSML-/XML-Formen besitzen gute Regressionstests.
- Der native Echo-Filter testet echte Signatur-Normalisierung und 36 wiederholte Parts; er ist mehr als ein reiner Implementation-Detailtest.
- `test_accumulator_drops_tool_preamble_and_repairs_shell_command_array()` prüft sowohl Entfernung der versehentlichen Prosa als auch Reparatur der Tool-Argumente.
- Retry-Tests prüfen Initialversuch plus Retry-Budget, Abbruch nach sichtbarem Content, Empty-/Reasoning-Rounds und das CRLF-Chunkproblem; die Follow-up-Runde wird für Stream und Non-Stream getrennt aufgerufen.
- Die Adaptertests prüfen Heartbeat-Verhalten, fragmentiertes `[DONE]`, `finish` ohne Sentinel, explizite Fehler-Events und Idempotenz der Abschluss-Events sinnvoll.
- Der AuditMesh-Verifier ist als unabhängiger Funktions-Oracle robust: Er prüft Source-/Fixture-Immutabilität, startet die Pipeline in einer geklonten Umgebung, verifiziert harte Soll-Metriken und wiederholt das Verhalten nach echten Input-Mutationen.
- Alle 31 von `AppConfig` gelesenen Variablen stehen in `.env.example`; Defaults stimmen dort mit `config.py` überein. Die Abweichung `GLM_MAX_CONCURRENCY` 3 im Code gegenüber 100 in der Beispielkonfiguration ist ausdrücklich dokumentiert und daher keine undokumentierte Drift.

## Geprüft und unauffällig

- `pyproject.toml` nutzt ein korrektes `src`-Layout, findet die Package-Unterpakete und deklariert den gültigen Console-Entry-Point `glm2api = glm2api.__main__:main`; Import und installierte Metadaten wurden read-only geprüft.
- Python `>=3.14` stimmt mit `.python-version`, `uv.lock` und den Betriebs-/Bundle-Skripten überein. Es ist restriktiv, aber im aktuellen Betriebsvertrag konsistent.
- Außer `pytest` werden für Runtime und Tests keine Drittanbieterpakete benötigt; die Dependency-Liste passt zum Standardbibliotheck-Design.
- `DEBUG_DUMP_ALL`, Request-Timeout, Token/Guest-Modus, Conversation-Flags, Assistant-IDs, Retrybudgets, History-Budget, Blocked-Tool-Liste und User-Agent sind im Beispiel vorhanden und entsprechen den Codewerten.
- Der Fehler `GLM2API_LOG_DIR` ist der einzige direkt aus der Prozessumgebung gelesene Betriebskey außerhalb des 31er-AppConfig-Vertrags; er ist in D-11 erfasst.
- Die vorhandenen Happy-Path-Tests sind überwiegend aussagekräftig. Direkte Zugriffe auf `pending_text`, `_server_side_tool_calls` und manuell per `__new__` gebaute Clients sind gezielte Komponententests, ersetzen aber keinen öffentlichen API-Roundtrip; diese Grenze ist in D-07 erfasst.
- Alle vorgegebenen Dateien wurden vollständig gelesen. Die zusätzlichen Probes waren read-only und erzeugten keine neuen Testdateien oder Projektänderungen.
