# Read-only Code- und Infrastruktur-Audit: glm2api

Auditdatum: 2026-09-08

## Findings

### Kritisch

Keine verifizierten kritischen Findings.

### Hoch

#### H-1: Referenz-Patch ist syntaktisch beschädigt

- **Schweregrad:** Hoch
- **Datei/Zeile:** `llm-proxies/patches/glm2api.patch:294-320`, insbesondere Zeile 309
- **Auswirkung:** Der als Referenz und als Bestandteil des portablen Bundles geführte Patch kann weder geprüft noch angewendet werden. Die projektspezifischen Änderungen sind über dieses Artefakt nicht reproduzierbar.
- **Begründung:** `git apply --check llm-proxies/patches/glm2api.patch` und `git apply --reverse --check llm-proxies/patches/glm2api.patch` brechen mit `error: corrupt patch at line 309` ab. Der vorherige Hunk endet in Zeile 308 mitten in einer List-Comprehension, bevor in Zeile 309 ein neuer Hunk beginnt.
- **Abhilfe:** Patch aus einer bekannten Upstream-Basis und dem aktuellen Quellbaum neu erzeugen. Danach Vorwärts- und Rückwärtsprüfung gegen die passenden Basen automatisieren.

#### H-2: Portables Bundle enthält veralteten Anwendungscode

- **Schweregrad:** Hoch
- **Datei/Zeile:** `llm-proxies/dist/glm2api-bundle.zip`; Erzeugung in `llm-proxies/scripts/build-bundle.sh:24-47`; Dokumentation in `README.md:23,105`
- **Auswirkung:** Nutzer des als portabel dokumentierten Bundles erhalten nicht denselben Parser-, Translator- und Teststand wie Nutzer des Workspace-Codes. Neuere Tool-Call- und Streaming-Korrekturen können fehlen.
- **Begründung:** SHA-256-Vergleiche zeigen Abweichungen für `src/glm2api/utils/tool_parser.py`, `src/glm2api/services/translator.py` und `tests/test_tool_parser.py`. `pyproject.toml` und `uv.lock` stimmen dagegen überein. Auch die Patchdatei im Bundle weicht vom Workspace-Patch ab.
- **Abhilfe:** Bundle nach Reparatur des Patches neu bauen. Anschließend alle vorgesehenen Dateien per Manifest oder Hash gegen den kanonischen Quellbaum prüfen und Drift in CI als Fehler behandeln.

### Mittel

#### M-1: Betriebsskript kann fremde Prozesse erkennen und beenden

- **Schweregrad:** Mittel
- **Datei/Zeile:** `infra/scripts/glm2api.sh:10,24-25,62-70,80-91`
- **Auswirkung:** `status` kann einen fremden Prozess als glm2api melden. `restart` kann mit `pkill -f` mehrere passende Prozesse anderer Checkouts oder Anwendungen beenden. Zugleich startet das Skript `python main.py`, sucht aber ausschließlich nach `python3 main.py`.
- **Begründung:** Das Prozessmuster enthält weder den absoluten Anwendungspfad noch eine verwaltete PID. Die Variable `PID_FILE` wird nicht verwendet. Der kanonische Startpfad verwendet außerdem `uv run main.py` in `llm-proxies/scripts/start-glm2api.sh:28`.
- **Abhilfe:** Einen einzigen Startweg verwenden, PID atomar erfassen und vor Signalen PID, Kommandozeile, Arbeitsverzeichnis und Portinhaber validieren. Kein globales `pkill -f` verwenden.

#### M-2: Beliebige Portbelegung wird als erfolgreicher Start behandelt

- **Schweregrad:** Mittel
- **Datei/Zeile:** `llm-proxies/scripts/start-glm2api.sh:22-25`
- **Auswirkung:** Belegt ein anderer Dienst Port 8001, beendet sich das Startskript erfolgreich, ohne glm2api oder dessen Health-Antwort zu identifizieren. Automatische Setups können einen funktionsfähigen Proxy melden, obwohl glm2api nicht läuft.
- **Begründung:** Der frühe Erfolgszweig prüft nur `ss -tln`. Die vorhandene Health-Prüfung in Zeilen 30-36 wird dann nicht erreicht.
- **Abhilfe:** Bei belegtem Port den Health-Endpunkt mit kurzem Timeout und erwarteter Antwort validieren. Bei fremder Belegung eindeutig und mit ungleich null abbrechen.

#### M-3: `rebuild.sh` synchronisiert vorhandene Umgebungen nicht

- **Schweregrad:** Mittel
- **Datei/Zeile:** `llm-proxies/rebuild.sh:37-51`
- **Auswirkung:** Änderungen an `pyproject.toml`, `uv.lock` oder der Python-Version werden bei vorhandener `.venv` nicht übernommen. Eine veraltete oder beschädigte Umgebung kann als vorbereitet gemeldet werden.
- **Begründung:** `uv sync` läuft ausschließlich, wenn das Verzeichnis `.venv` fehlt. Seine bloße Existenz belegt weder Vollständigkeit noch Lockfile-Synchronität.
- **Abhilfe:** Bei jedem Rebuild `uv sync --frozen` ausführen und mindestens die Existenz sowie Funktionsfähigkeit von `.venv/bin/python` prüfen.

### Niedrig

#### N-1: Bundle lässt den vorhandenen Konfigurationstest aus

- **Schweregrad:** Niedrig
- **Datei/Zeile:** `llm-proxies/glm2api/tests/test_config.py`; Bundle-Erzeugung in `llm-proxies/scripts/build-bundle.sh:25`
- **Auswirkung:** Tests aus dem Bundle decken die Konfigurationsvalidierung nicht vollständig ab.
- **Begründung:** `tests/test_config.py` ist im Workspace vorhanden, fehlt aber in der ZIP-Dateiliste.
- **Abhilfe:** Bundle neu erzeugen und automatisiert prüfen, dass alle versionierten Tests enthalten sind.

#### N-2: ZIP-Build ist trotz Dokumentation nicht vollständig deterministisch

- **Schweregrad:** Niedrig
- **Datei/Zeile:** `llm-proxies/scripts/build-bundle.sh:45-47`
- **Auswirkung:** Inhaltlich identische Builds können durch abweichende Dateizeiten unterschiedliche ZIP-Hashes erzeugen.
- **Begründung:** `zip -X` entfernt zusätzliche Attribute, aber nicht die normalen Zeitstempel der ZIP-Einträge. Neu angelegte Stage-Verzeichnisse und kopierte Dateien besitzen variable Zeiten.
- **Abhilfe:** Stage-Inhalte auf einen festen, aus `SOURCE_DATE_EPOCH` abgeleiteten Zeitstempel setzen, stabil sortieren und zwei unabhängige Builds auf identische SHA-256-Hashes prüfen.

## Audit-Umfang

Geprüft wurden:

- der relevante Kontext in `README.md`
- der vollständige Python-Quellbaum unter `llm-proxies/glm2api/src/glm2api/`
- alle Tests unter `llm-proxies/glm2api/tests/`
- `main.py`, `pyproject.toml`, `uv.lock`, `.python-version`, `.env.example`, `glm2api.env`, Projekt-README und Strukturdokumentation
- `llm-proxies/patches/glm2api.patch`
- Start-, Rebuild-, Bundle- und portable Installationsskripte
- `infra/scripts/glm2api.sh`, `infra/scripts/ports.sh` und glm2api-bezogene Setup-Referenzen
- zugehörige opencode-Provider- und Agent-Konfiguration
- `.gitignore`, Reverse-Engineering-Dokumentation und `llm-proxies/dist/glm2api-bundle.zip`

Die Oberfläche wurde zunächst namensbasiert per Glob und anschließend referenzbasiert per Grep ermittelt. Laufzeitverzeichnisse wie `.venv`, `__pycache__` und Logs wurden nur auf versehentliche Versionierung und betriebliche Risiken geprüft.

## Durchgeführte Prüfungen

### Erfolgreich

- `README.md` wurde vor den Detailprüfungen gelesen.
- Glob- und Grep-Suchen erfassten direkte Dateinamen und indirekte glm2api-Referenzen.
- `.venv/bin/pytest -q`: 63 Tests bestanden in 0,66 Sekunden.
- `.venv/bin/python -m compileall -q src tests`: ohne Syntaxfehler.
- `bash -n` für `start-glm2api.sh`, `infra/scripts/glm2api.sh`, `rebuild.sh` und `build-bundle.sh`: ohne Syntaxfehler.
- Prüfung auf versionierte `.venv`, `__pycache__`, Logs, `token.txt` und PID-Dateien: keine entsprechenden Runtime-Artefakte gefunden.
- ZIP-Inhaltsprüfung: 46 Einträge, insgesamt 362626 Bytes.
- SHA-256-Vergleich: Abweichungen für Parser, Translator, Parser-Tests und Patch; Übereinstimmung für `pyproject.toml` und `uv.lock`.
- Prüfung auf `tests/test_config.py` im Bundle: Datei fehlt.

### Fehlgeschlagen oder nicht ausführbar

- Vorwärts- und Rückwärtsprüfung des Patches: wegen `error: corrupt patch at line 309` nicht ausführbar.
- Ergänzende `rg`-Teilschritte waren in einer Shell nicht ausführbar, weil `rg` dort nicht im `PATH` lag. Die Audit-Oberfläche war zuvor mit den bereitgestellten Glob- und Grep-Werkzeugen ermittelt worden.
- Keine Live-API-, Upstream-, Last-, Neustart-, Portkonflikt- oder Deploymenttests. Entsprechend der Vorgabe wurden keine Prozesse gestartet oder gestoppt und keine Abhängigkeiten installiert.
- Das Bundle wurde nicht neu gebaut, weil das Buildskript Stage- und ZIP-Artefakte löscht beziehungsweise überschreibt.

## Kategorien ohne weitere verifizierte Findings

- **Funktionale Anwendungslogik:** Außer den dokumentierten Auslieferungs- und Betriebsskriptrisiken wurde kein weiterer konkreter Fehler reproduziert.
- **Parser und Streaming:** Im aktuellen Workspace-Code kein zusätzlicher reproduzierbarer Fehler; die einschlägigen Unit-Tests bestanden. Das veraltete Bundle ist ausgenommen.
- **Tool-Call-Protokoll:** Im aktuellen Workspace-Code kein weiterer verifizierter Protokollfehler; Parser- und Adaptertests bestanden.
- **Eingabevalidierung:** Die geprüfte Konfiguration validiert unter anderem Port, positive Timeouts, Retry-Intervall und URL-Schema. Kein weiterer konkret ausnutzbarer Fehler wurde verifiziert.
- **Fehlerbehandlung:** Kein zusätzlicher reproduzierbarer Fehlerpfad gefunden.
- **Nebenläufigkeit:** Kein konkreter Deadlock, Lease-Verlust oder Race verifiziert. Live-Lasttests waren nicht zulässig.
- **Secrets und Logging:** Keine versehentlich versionierten Token-, Log-, PID- oder Virtual-Environment-Artefakte und kein konkretes Secret-Leak gefunden.
- **Dependency-Sicherheit:** Keine konkrete bekannte Schwachstelle verifiziert. Eine aktuelle Online-Vulnerability-Abfrage und zusätzliche Scanner waren nicht Bestandteil des Laufs.
- **Verhaltensregressionen:** Im Workspace-Teststand keine Regression festgestellt; alle 63 Tests bestanden. Bundle-Drift ist separat dokumentiert.

## Offene Annahmen

- `llm-proxies/glm2api` ist der kanonische aktuelle Quellstand; der Patch ist ein Referenz- oder Wiederherstellungsartefakt.
- `llm-proxies/dist/glm2api-bundle.zip` ist zur Weitergabe vorgesehen, da README und Buildskript es als portables Bundle beschreiben.
- Port 8001 und `127.0.0.1` sind der beabsichtigte lokale Betriebsmodus.
- Die konfigurierte Gast-Nebenläufigkeit von 100 ist bewusst gewählt und wurde ohne zulässigen Lasttest nicht als Fehler eingestuft.

## Positive Beobachtungen

- 63 von 63 Tests bestanden.
- Parser, Translator, Modellvarianten, Protokolladapter und Konfiguration besitzen dedizierte Tests.
- Python-Quellen und Tests sind syntaktisch kompilierbar.
- Die geprüften Shellskripte bestehen `bash -n`.
- Runtime-Artefakte und Token-Dateien sind ignoriert und nicht versioniert.
- `uv.lock` ist vorhanden und stimmt zwischen Workspace und Bundle überein.
- Mehrere zentrale Konfigurationswerte werden explizit validiert.
- Der kanonische Startpfad bindet lokal und prüft nach dem Start den Health-Endpunkt.
- Debug-Logs verwenden Größenbegrenzung und Rotation.

## Verbleibende Testlücken

- Keine End-to-End-Prüfung gegen den realen Upstream oder tatsächliche SSE-Chunk-Grenzen.
- Kein Live-Test der OpenAI-, Anthropic- und Responses-kompatiblen Endpunkte.
- Kein Last- oder Fairness-Test der Queue mit Timeouts, Abbrüchen und Stream-Disconnects.
- Kein automatisierter Test für PID-Zuordnung, fremde Portbelegung oder mehrere Checkouts.
- Kein Upgrade-Test mit vorhandener, veralteter oder beschädigter `.venv`.
- Kein automatisierter Patch-Syntax- und Anwendbarkeitstest.
- Kein automatisierter Vollständigkeits- und Hashvergleich des Bundles.
- Kein Doppelbuild zur Bestätigung eines byteidentischen ZIP-Artefakts.
- Keine aktuelle externe Dependency-Vulnerability-Prüfung.

## Zusammenfassung

Dokumentiert sind 7 verifizierte Findings: **0 kritisch, 2 hoch, 3 mittel und 2 niedrig**. Der aktuelle Workspace-Code besteht alle 63 vorhandenen Tests. Die größten Risiken sind die beschädigte Patchreferenz, das veraltete portable Bundle und die uneinheitlichen beziehungsweise zu breiten Prozess- und Startprüfungen.
