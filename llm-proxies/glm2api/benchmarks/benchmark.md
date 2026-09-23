# glm2api Agenten-Benchmark: AuditMesh

Dieser Benchmark misst einen kompletten OpenCode-Agentenlauf ueber
`glm2api/glm-5.3`: Dateierstellung, Lesen, gezielte Aenderungen, Testen,
mehrere Tool-Result-Runden und einen maschinenpruefbaren Abschluss. Er ist
kein Benchmark fuer die Geschwindigkeit eines einzelnen API-Requests. Er
prueft zusaetzlich die vollstaendige und disziplinierte Nutzung aller im Chat
deklarierten OpenCode-Tools.

## Ausfuehrung durch den Runner

1. Den Proxy starten und vor jedem Lauf den Transport pruefen:

   ```bash
   ./llm-proxies/scripts/start-glm2api.sh
   SMOKE_MODEL=glm-5.3 ./llm-proxies/scripts/smoke-test.sh
   ```

2. Einen frischen, leeren Laufpfad festlegen, zum Beispiel
   `/workspaces/benchmark/auditmesh-20260923-01`. Der Runner ersetzt im
   Agentenauftrag unten `<BENCHMARK_ROOT>` durch genau diesen Pfad.
3. Eine frische OpenCode-Session mit **`glm2api/glm-5.3`** starten. Nicht das
   Defaultmodell verwenden und keinen bereits langen Chat fortsetzen.
4. Ausschliesslich den Abschnitt **Agentenauftrag** einreichen. Keine
   Nachfragen, Resume-Nachrichten oder inhaltlichen Hinweise nachschieben.
5. Nach dem Abschluss unabhaengig vom Agenten ausfuehren:

   ```bash
   uv run --directory "<BENCHMARK_ROOT>" pytest -q
   python3 /workspaces/MAIN/llm-proxies/glm2api/benchmarks/verify_auditmesh.py "<BENCHMARK_ROOT>"
   ```

Der Verifier gehoert dem Runner, nicht dem erzeugten Projekt. Er startet die
Pipeline erneut und prueft in einer temporaeren Kopie einen zweiten,
vollstaendig konformen Datenzustand. Das erschwert hart kodierte Metriken und
prueft, ob die entscheidenden Analysen auf geaenderte Eingaben reagieren.

## Agentenauftrag

Erstelle unter `<BENCHMARK_ROOT>` ein vollstaendiges Python-Projekt namens
`AuditMesh`. Es analysiert Markdown-Dokumente, Anwendungslogs,
Sicherheitsereignisse und JSON-Konfigurationen und erzeugt einen Auditbericht.

### Grenzen und Arbeitsweise

- Arbeite ausschliesslich unter `<BENCHMARK_ROOT>`. Der Pfad ist leer und wird
  vom Runner vorbereitet. Weder `/workspaces/MAIN` noch Dateien ausserhalb des
  Laufpfads duerfen veraendert werden.
- Nutze nur die in diesem Chat tatsaechlich deklarierten OpenCode-Tools (`read`, `write`, `edit`, `bash` etc.).
  Erfinde keine Toolnamen (insb. KEIN `execute_sandbox_code`, kein Browser, kein `open_url`).
  Fuer alle Dateioperationen nutze `write`/`read` mit VOLLSTAENDIGEN ABSOLUTEN PFADEN (z. B. `<BENCHMARK_ROOT>/data/...`).
  Fuer Code-Ausfuehrung und Tests nutze AUSSCHLIESSLICH `bash`.
- Fuehre logisch abhaengige Tool-Aufrufe sequenziell aus: Ergebnis abwarten,
  pruefen, dann den naechsten Schritt ausfuehren.
- Kein Netzwerkzugriff auf externe Hosts, keine externen Runtime-Abhaengigkeiten
  und keine generierten Binardateien. Python-Standardbibliothek plus `pytest`
  fuer Tests genuegt. Einzige Ausnahme: der lokale Endpunkt `127.0.0.1` aus
  Phase 8.
- Veraendere die Eingabedaten nicht waehrend der Analyse. Erst nach erfolgreichem
  Testlauf darfst du den Abschlussbericht schreiben.

### Verbindliche Tool-Abdeckung

Der Lauf muss jedes der folgenden Tools mindestens einmal und ausschliesslich
fuer den genannten Zweck verwenden:

| Tool | Vorgesehener Einsatz |
|---|---|
| `todowrite` | Phase 0: Plan anlegen und waehrend des Laufs aktuell halten |
| `write` | alle neuen Projekt- und Fixture-Dateien |
| `read` | Ruecklesen von Fixtures und Output |
| `bash` | Verzeichnispruefung, Tests, CLI-Lauf, lokaler HTTP-Server |
| `glob` | Phase 2: Mustersuche `**/*.md` unter `<BENCHMARK_ROOT>/data` |
| `grep` | Phase 2: Inhaltssuche nach `ERR-101` unter `<BENCHMARK_ROOT>/data` |
| `edit` | Phase 4: genau eine gezielte Nachaenderung nach dem ersten Schreiben |
| `task` | Phase 7: genau ein rein lesender `explore`-Subagent |
| `webfetch` | Phase 8: Abruf vom lokalen 127.0.0.1-Server |
| `opencode-sessions_db_stats` | Phase 9: einmaliger read-only Abruf der Session-Statistik |
| `question` | Phase 10: definierter Laufabschluss |

Verboten und als Proxy-Anomalie gewertet sind: alle
`opencode-sessions_delete_*`-Tools, `skill` (kein Skill passt zu diesem
Auftrag) sowie erfundene Tools (`execute_sandbox_code`, Browser, `open_url`).
`glob` und `grep` muessen als eigenstaendige Tool-Aufrufe erfolgen und duerfen
nicht durch `bash`-Kombinationen wie `find | grep` ersetzt werden.

### Phasenweiser Ablauf (verbindlich)

0. **Phase 0 — Plan:** Lege mit `todowrite` einen Plan an, der alle Phasen
   dieses Auftrags enthaelt, und aktualisiere ihn waehrend der Arbeit.
1. **Phase 1 — Setup & Fixtures:** Verzeichnisse anlegen und alle 7 Fixture-Dateien
   (3 Docs, 2 Logs, 2 Configs) vollstaendig schreiben.
2. **Phase 2 — Verifikation der Fixtures:** Pruefe mit
   `find <BENCHMARK_ROOT>/data -type f | sort`, dass wirklich alle 7 Dateien existieren.
   Fuehre zusaetzlich einen `glob`-Aufruf mit Muster `**/*.md` unter
   `<BENCHMARK_ROOT>/data` und einen `grep`-Aufruf nach `ERR-101` unter
   `<BENCHMARK_ROOT>/data` aus (eigene Tools, nicht via `bash`).
3. **Phase 3 — Implementierung:** Schreibe die Module unter `<BENCHMARK_ROOT>/src/auditmesh/`
   und `<BENCHMARK_ROOT>/pyproject.toml`.
4. **Phase 4 — Tests:** Schreibe Unit- und Integrationstests unter `<BENCHMARK_ROOT>/tests/`
   und fuehre sie mit `bash` aus:
   `PYTHONPATH=<BENCHMARK_ROOT>/src python3 -m pytest tests -v` (workdir: `<BENCHMARK_ROOT>`).
   Behebe Fehler im Code, bis alle Tests gruen sind. Setze danach mit genau
   einem `edit`-Aufruf den Docstring in
   `<BENCHMARK_ROOT>/src/auditmesh/__init__.py` auf `AuditMesh audit pipeline.`
   und fuehre die Tests erneut aus.
5. **Phase 5 — Pipeline-Lauf:** Starte die CLI:
   `PYTHONPATH=<BENCHMARK_ROOT>/src python3 -m auditmesh --root <BENCHMARK_ROOT>`.
   Erst im darauffolgenden Schritt/Turn pruefst du, dass `<BENCHMARK_ROOT>/output/metrics.json` und
   `<BENCHMARK_ROOT>/output/audit_report.md` existieren und korrekte Werte enthalten (nicht im selben Turn).
6. **Phase 6 — Output-Pruefung:** Lies `output/metrics.json` und
   `output/audit_report.md` mit `read` und vergleiche die Werte mit dem
   verbindlichen Metrik-Schema.
7. **Phase 7 — Struktur-Selbstkontrolle:** Starte mit `task` genau einen
   Subagenten vom Typ `explore`, der die Dateistruktur unter `<BENCHMARK_ROOT>`
   gegen die erwartete Struktur praueft und Fehlendes zurueckmeldet. Der
   Subagent ist rein lesend.
8. **Phase 8 — Lokaler Webfetch:** Starte mit `bash` im Hintergrund
   `python3 -m http.server 8931 --bind 127.0.0.1 --directory <BENCHMARK_ROOT>/data`,
   rufe mit `webfetch` `http://127.0.0.1:8931/configs/rules.json` ab,
   vergleiche die drei Grenzwerte mit den Vorgaben und beende den
   Server-Prozess danach wieder.
9. **Phase 9 — Session-Statistik:** Rufe einmal `opencode-sessions_db_stats`
   auf; Session-Anzahl und DB-Groesse gehoeren in den Abschlussbericht.
10. **Phase 10 — Abschluss:** Knapper Abschlussbericht gemaess Vorgabe unten,
    danach genau ein `question`-Aufruf als Laufende.

### Erwartete Struktur

```text
<BENCHMARK_ROOT>/
|-- data/
|   |-- docs/
|   |   |-- architecture.md
|   |   |-- runbook.md
|   |   `-- api_spec.md
|   |-- logs/
|   |   |-- service_app.log
|   |   `-- audit_security.txt
|   `-- configs/
|       |-- rules.json
|       `-- services.json
|-- src/auditmesh/
|   |-- __init__.py
|   |-- __main__.py
|   |-- models.py
|   |-- analyzer.py
|   |-- reporter.py
|   `-- parsers/
|       |-- __init__.py
|       |-- doc_parser.py
|       |-- log_parser.py
|       `-- config_loader.py
|-- tests/
|   |-- test_parsers.py
|   |-- test_analyzer.py
|   `-- test_reporter.py
`-- pyproject.toml
```

`pyproject.toml` muss ein installierbares Projekt mit `src`-Layout und einer
Pytest-Konfiguration enthalten. Der Einstiegspunkt muss ohne Installation
funktionieren:

```bash
PYTHONPATH=<BENCHMARK_ROOT>/src python3 -m auditmesh --root <BENCHMARK_ROOT>
```

Die Pipeline darf Eingabedaten und Quellcode nicht veraendern. Ihre fachlichen
Artefakte liegen ausschliesslich in
`<BENCHMARK_ROOT>/output/audit_report.md` und
`<BENCHMARK_ROOT>/output/metrics.json`; uebliche Python-Cache-Dateien sind
ausgenommen.

### Verbindliche Eingabedaten

Die Formulierung und das Layout der Dokumente darfst du sinnvoll gestalten.
Die folgenden Fakten, Dateinamen und Werte muessen jedoch exakt vorhanden
sein.

`data/configs/services.json` enthaelt unter dem Top-Level-Key `services` diese
drei Services:

```json
{
  "services": [
    {
      "name": "gateway",
      "port": 8080,
      "depends_on": [
        "identity",
        "ledger"
      ]
    },
    {
      "name": "identity",
      "port": 8081,
      "depends_on": []
    },
    {
      "name": "ledger",
      "port": 8082,
      "depends_on": []
    }
  ]
}
```

`data/configs/rules.json` enthaelt diese Top-Level-Keys:

```json
{
  "max_error_rate": 0.4,
  "min_runbook_coverage": 0.75,
  "max_security_events": 3
}
```

Die Markdown-Dokumente muessen diese Beziehungen ausdruecken:

- `architecture.md` beschreibt die drei Services und verlinkt lokal auf
  `runbook.md` und `api_spec.md`.
- `runbook.md` hat eigenstaendige Abschnitte fuer `ERR-101` und `ERR-500`.
- `api_spec.md` verlinkt lokal auf `architecture.md` und absichtlich auf die
  nicht vorhandene Datei `obsolete.md`.
- Externe URLs und Anker spielen fuer diesen Benchmark keine Rolle. Es wird
  nur die Existenz relativer lokaler Markdown-Dateilinks bewertet.

`service_app.log` hat genau diese 12 inhaltlichen Zeilen. Das Pipe-Format ist
verbindlich, damit ein unabhaengiger Verifier eine zusaetzliche Zeile anhaengen
kann:

```text
2026-01-15T09:00:00Z | INFO  | gateway  | REQUEST_STARTED | request=r-001
2026-01-15T09:00:01Z | INFO  | identity | TOKEN_VALIDATED | request=r-001
2026-01-15T09:00:02Z | WARN  | gateway  | CACHE_MISS | key=profile-17
2026-01-15T09:00:03Z | ERROR | identity | ERR-101 | upstream timeout
2026-01-15T09:00:04Z | INFO  | ledger   | SYNC_OK | batch=42
2026-01-15T09:00:05Z | ERROR | gateway  | ERR-500 | ledger unavailable
2026-01-15T09:00:06Z | WARN  | ledger   | RETRY_SCHEDULED | after=5s
2026-01-15T09:00:07Z | ERROR | gateway  | ERR-101 | upstream timeout
2026-01-15T09:00:08Z | INFO  | gateway  | REQUEST_OK | request=r-002
2026-01-15T09:00:09Z | ERROR | catalog  | ERR-404 | catalog entry missing
2026-01-15T09:00:10Z | INFO  | identity | SESSION_CLOSED | request=r-001
2026-01-15T09:00:11Z | INFO  | gateway  | HEALTHY | latency_ms=12
```

`audit_security.txt` hat genau diese vier Zeilen im Pipe-Format:

```text
2026-01-15T09:00:20Z | AUTH_FAIL | user=alice | source=198.51.100.10
2026-01-15T09:00:21Z | AUTH_FAIL | user=bob | source=198.51.100.11
2026-01-15T09:00:22Z | ACCESS_DENIED | user=carol | resource=ledger
2026-01-15T09:00:23Z | RATE_LIMIT | client=mobile | limit=100
```

### Implementierungsregeln

- Verwende Dataclasses fuer mindestens Dokumente, Logeintraege, Incidents und
  Analyseergebnisse.
- `AuditAnalyzer.analyze()` liest alle Fixtures und liefert die gesamte
  Korrelation. Der Reporter berechnet keine eigenen Analysewerte.
- Die Analyse arbeitet mit **verschiedenen** Fehlercodes, nicht mit der Anzahl
  ihrer Vorkommen, wenn sie die Runbook-Abdeckung bestimmt.
- Ein Fehlercode ist dokumentiert, wenn er einen eigenen Runbook-Abschnitt
  besitzt. `ERR-404` ist daher undokumentiert.
- Die Fehlerrate ist `ERROR-Zeilen / alle Anwendungslog-Zeilen`.
- Leite `configured_services`, `unknown_log_services`, `service_count` und
  `dependency_edge_count` aus `services.json` und den Anwendungslogs ab.
  Die Namen in beiden Listen sind alphabetisch sortiert. Ein Log-Service ohne
  Katalogeintrag ist unbekannt.
- Es gibt genau drei Compliance-Checks: Fehlerrate, Runbook-Abdeckung und
  Anzahl Sicherheitsereignisse. Ein Grenzwert ist bei Gleichheit bestanden.
- `compliance_score` ist `passed_checks / total_checks`; `compliant` ist nur
  bei drei bestandenen Checks `true`.
- Schreibe echte Unit- und Integrationstests, die aus den Rohdaten lesen oder
  die oeffentliche Analyse-API aufrufen. Tests, die nur bereits geschriebene
  Ausgabe lesen, sind nicht ausreichend.
- Greife tolerant auf Fixture-Sammlungen zu (z. B. `docs.get('runbook.md')`),
  damit isolierte Unit-Tests mit Teil-Fixtures nicht an `KeyError` scheitern.

### Verbindliches Metrik-Schema

`output/metrics.json` muss valides JSON mit mindestens diesen Keys liefern.
Listen sind alphabetisch sortiert. Floats duerfen nicht gerundet werden.

```json
{
  "schema_version": 1,
  "app_log_entries": 12,
  "app_error_entries": 4,
  "error_rate": 0.3333333333333333,
  "configured_services": ["gateway", "identity", "ledger"],
  "unknown_log_services": ["catalog"],
  "service_count": 3,
  "dependency_edge_count": 2,
  "error_code_counts": {
    "ERR-101": 2,
    "ERR-404": 1,
    "ERR-500": 1
  },
  "documented_error_codes": ["ERR-101", "ERR-500"],
  "undocumented_error_codes": ["ERR-404"],
  "runbook_coverage": 0.6666666666666666,
  "broken_local_links": [
    {"source": "api_spec.md", "target": "obsolete.md"}
  ],
  "security_event_counts": {
    "ACCESS_DENIED": 1,
    "AUTH_FAIL": 2,
    "RATE_LIMIT": 1
  },
  "security_event_total": 4,
  "checks": {
    "error_rate": {"actual": 0.3333333333333333, "limit": 0.4, "passed": true},
    "runbook_coverage": {"actual": 0.6666666666666666, "limit": 0.75, "passed": false},
    "security_events": {"actual": 4, "limit": 3, "passed": false}
  },
  "passed_checks": 1,
  "total_checks": 3,
  "compliance_score": 0.3333333333333333,
  "compliant": false
}
```

`audit_report.md` muss eine lesbare Markdown-Incident-Tabelle mit exakt diesem
Header und mindestens einer `ERR-404`-Zeile enthalten:

```text
| Error code | Occurrences | Documentation | Status |
```

Der Bericht enthaelt ausserdem die stabilen Marker `ERR-404`, `obsolete.md`
und eine eigene Statuszeile `AUDIT_STATUS: NON_COMPLIANT`.

### Abschluss

1. Fuehre die Tests selbst aus und behebe echte Fehler.
2. Fuehre danach die CLI einmal aus, so dass beide Output-Dateien vorliegen.
3. Pruefe die erzeugten Metriken gegen die Werte oben.
4. Antworte erst dann mit einem knappen Abschlussbericht: Test-Ergebnis,
   Output-Pfade, wichtigste Metriken sowie die Zahlen aus
   `opencode-sessions_db_stats`. Keine Quellcode-Dumps und keine inhaltliche
   Rueckfrage an den Benutzer.
5. Beende den Lauf mit genau einem `question`-Aufruf, dessen Frage exakt
   `Benchmark-Lauf abgeschlossen?` lautet. Dieser Aufruf ist das definierte
   Laufende und gilt nicht als Rueckfrage im Sinne von Punkt 4.

## Auswertung

Ein Lauf ist funktional bestanden, wenn der unabhaengige Verifier und die
Projekttests erfolgreich enden. Die folgenden Proxy-Signale werden zusaetzlich
pro Session protokolliert:

| Kriterium | Bestehen |
|---|---|
| Preflight | Smoke-Test mit `SMOKE_MODEL=glm-5.3` und Exit-Code 0 |
| Modell | frische Session mit `glm2api/glm-5.3` |
| Autonomie | keine manuelle Resume- oder Korrektur-Nachricht |
| Tool-Protokoll | kein Assistant-Text-Part mit `{"tool_calls"`, `<ml_tool_call`, `<|DSML|tool_call` oder einem Tool-Array der Form `[{"name":...}]` |
| Tool-Integritaet | keine undeclared/blocked Calls; kein gleicher Toolname mit kanonisch gleichen Argumenten mehr als einmal im selben Assistant-Turn |
| Funktion | Pytest und `verify_auditmesh.py` beide mit Exit-Code 0 |
| Tool-Abdeckung | jedes Tool aus der Tabelle „Verbindliche Tool-Abdeckung" mindestens einmal mit dem vorgesehenen Zweck verwendet |
| Tool-Disziplin | keines der verbotenen Tools (`opencode-sessions_delete_*`, `skill`, erfundene Tools) aufgerufen; genau ein `question`-Aufruf als Laufende |

Der Runner exportiert nach dem Lauf die Assistant-Text- und Tool-Parts der
Session und prueft die beiden Tool-Kriterien direkt dagegen. Unabhaengige,
spaetere Wiederholungen desselben Calls sind erlaubt; nur Duplikate innerhalb
eines einzelnen Assistant-Turns zaehlen als Proxy-Anomalie.

Session-ID, Laufzeit, Anzahl Tool-Parts, Anzahl Assistant-Turns und etwaige
Ausreisser gehoeren in das Laufprotokoll. Die Zahlen sind Vergleichswerte,
keine kuenstlichen Zielwerte.
