# Revision

## Analyseauftrag und redaktioneller Status

Dieses Dokument ist ein statischer Audit-Trail für `/workspaces/MAIN` vom 24.09.2026. Die einzelnen Anhänge A–V sind zeitlich markierte Prüfberichte; ihre Commit-, Inventar- und Zeilenzahlen sind Momentaufnahmen und keine dauerhaften Verträge.

- **Arbeitsgrenze:** ausschließlich `/workspaces/MAIN`; externe Pfade wurden nur als Verträge oder Laufzeitverweise inventarisiert, nicht als Quellobjekte gelesen.
- **Vorgehen:** Dateien wurden inventarisiert, Textdateien zeilenweise gelesen, Binär-, Vendor- und Runtime-Dateien strukturell katalogisiert. `Revision.md` selbst war in Teil A kein Prüfobjekt.
- **Secret-Grenze:** Klartext- und verschlüsselte Secret-Dateien wurden nicht in diesen Bericht kopiert; dokumentiert wurden nur Pfad, Typ, Größe, Schutzstatus und beobachtete Referenzen.
- **Abgeschlossen** bezeichnet ausschließlich die Analyse-/Dokumentationsabdeckung. Technische Behebung, Build, Test, Runtime-, Port- und Remote-Verifikation wurden damit nicht behauptet.
- **Produktstatus:** nicht abnahmefähig; die in den Anhängen dokumentierten offenen Befunde bleiben bestehen, sofern sie nicht ausdrücklich als behoben oder superseded markiert sind.
- **Redaktionsstand:** Diese Bereinigung bearbeitet nur die Dokumentstruktur und Statusaussagen; Anwendungscode, Secrets und andere Dateien werden nicht verändert.

## Executive Summary

- **Dokumentations-/Coverage-Check:** A–U sind als historische Berichte eingebettet; R, S und U werden nicht als konkurrierende aktuelle Endstände geführt.
- **Aktueller maßgeblicher Dokumentstatus:** die redaktionelle Endkontrolle am Dokumentende; historische Reports behalten ihre eigene Provenienz.
- **Technischer Status:** offene Befunde aus Produktivcode, Proxy-Betrieb, Bundle, Config und Benchmark bleiben bestehen; es wurde keine technische Behebung vorgenommen.
- **Verifikationsgrenze:** keine Tests, Builds, Serverstarts, HTTP-/Remote-Aktionen oder Live-Benchmarkläufe; geschützte Secret-Inhalte blieben ungeöffnet.

## Startinventur und Snapshot-Hinweise

| Bereich | Dateien laut einem jeweiligen Snapshot | Bearbeitung / Geltung |
|---|---:|---|
| versionierte Arbeitsdateien | 178 | quellenah geprüft; `Revision.md` ist selbst keine verlässliche Abdeckungsquelle für Teil A |
| ignorierte Runtime-/Dependency-/Log-Dateien | 5.518–5.524 | textuelle Dateien wurden zeilenweise, Binär-/Runtime-Bestände strukturell geprüft; Zählung ist zeitabhängig |
| Kandidaten außerhalb des Git-Objektspeichers | 5.696–5.702 | durch A–U abgedeckt; nachgelagerte `REVIEW-*.md`-Dateien sind zusätzliche, ignorierte Arbeitsbelege |
| `.git` | separat katalogisiert | keine Objekt-/Blob-Inhalte als Quellcode analysiert |

Die Bereiche in dieser Tabelle sind Snapshots aus unterschiedlichen Prüfzeitpunkten. Maßgeblich ist jeweils nur der ausdrücklich genannte Commit und Prüfzeitpunkt des Berichts; die Spanne ersetzt keinen aktuellen Inventarvertrag.

## Abdeckungsstatus der historischen Analyse

| Prozess | Bereich | Status der Analyse |
|---|---|---|
| Initialisierung | Gesamtbestand und Methodik | abgeschlossen |
| A | Top-Level, Dokumentation, Devcontainer, OpenCode-Direktkonfiguration | abgeschlossen |
| B | Infrastruktur-Skripte und Infra-Dokumentation | abgeschlossen |
| C | MCP-Server, SQL, Löschschutz und Querverweise | abgeschlossen |
| D | antigravity-proxy: Betrieb, OAuth, Build, Pakete und CI | abgeschlossen |
| E | antigravity-proxy: Cmd, Auth, Credentials, HTTP, Project, Logger | abgeschlossen |
| F | antigravity-proxy: Modelle, OpenAI-Transformation und Streaming | abgeschlossen |
| G | antigravity-proxy: Server, Middleware und HTTP-Routen | abgeschlossen |
| H | glm2api: Betrieb, Rebuild, Bundle und Dokumentation | abgeschlossen |
| I | glm2api: produktiver Python-Anwendungscode | abgeschlossen |
| J | glm2api: Tests und Benchmark-Fixtures | abgeschlossen |
| K | ignorierter Node-Dependency-Baum | abgeschlossen, strukturell |
| L | ignorierte Firefox-Runtime und Browserprofil | abgeschlossen, strukturell |
| M | ignorierte Venv-, Log-, Build- und Cache-Artefakte | abgeschlossen, strukturell |
| N | `.git`, Restbestand und Querverweise | abgeschlossen, read-only |
| O | `.opencode/agent/glm2api.md` und `command/quota.md` | abgeschlossen |
| P | `config/`-Secret-Artefakte | abgeschlossen, redigiert |
| Q | getracktes glm2api-Bundle-ZIP | abgeschlossen, ZIP read-only |
| R | historischer Gap-Check | abgeschlossen, durch S und die redaktionelle Endkontrolle überholt |
| S | historischer Gesamt-/Coverage-Check | abgeschlossen, nicht mehr maßgeblich |
| T | AuditMesh-Benchmark-Recheck | abgeschlossen, fachlicher Benchmark-Snapshot |
| U | Delta-Audit der extern übernommenen glm2api-Änderung | abgeschlossen, Delta-Snapshot |
| V | redaktionelle Konsistenzprüfung und Endkontrolle | abgeschlossen; keine technische Behebung |

## Report- und Vorrangmatrix

| Reports | Rolle | Vorrang / Lesart |
|---|---|---|
| A–Q | historische Baseline- und Scope-Berichte | fachliche Evidenz mit ihrem jeweiligen Snapshot; nicht pauschal auf aktuellen Source übertragen |
| R | historischer Gap-Check | superseded; keine aktuelle Endstatusquelle |
| S | historischer Gesamt-/Coverage-Check | superseded durch T, U und V |
| T | späterer Benchmark-Vertragscheck | maßgeblich für den dort geprüften Benchmark-Snapshot, nicht für Build-/Runtime-Sicherheit |
| U | Delta-Audit der zwei extern geänderten glm2api-Dateien | maßgeblich für dieses Delta; beseitigt die älteren Baseline-Befunde nicht |
| V | redaktionelle Endkontrolle | einzige Quelle für den Status dieses Dokuments; keine technische Produktfreigabe |

## Methodik und Protokollstand

### Initialisierung

Die erste Inventur wurde aus dem tatsächlichen Dateisystem und der Git-Index-Liste erstellt. Der Bestand enthält Quellcode, Shell-/Python-/Go-/JSON-Dateien, verschlüsselte Secret-Artefakte, installierte Python-/Node-Abhängigkeiten, Browser-Runtime, Logs, PID-/Cache-Dateien sowie Binärdateien. Die fachliche Datei-für-Datei-Bewertung wurde in den oben genannten unabhängigen Teilprozessen durchgeführt; Build-, Test- und Laufzeitverifikation waren ausdrücklich nicht Teil dieses Schritts.

### Leseschutz und technische Grenzen

- Secret-Inhalte wurden nicht wiedergegeben; Pfadnummern und Runtime-Artefakte sind keine Freigabe zum Öffnen geschützter Dateien.
- `.runtime/revision-parts/*.md` sind nicht-kanonische, ignorierte Arbeitsbelege; die wesentlichen Aussagen dieses Dokuments stehen hier im Masterdokument.
- Die eingebetteten A–V-Report-Inhalte bleiben als historische Berichtformate erhalten; die Reporttitel sind als H2 normalisiert, ihre lokalen Unterebenen bleiben unverändert. Maßgeblich für die aktuelle Navigation sind die Überschriften vor dem Anhang A und die Vorrangmatrix.


## Anhang A — Top-Level, Dokumentation, Devcontainer und OpenCode

<!-- BEGIN PART A -->
## Revision Partition A – statische Bestandsanalyse

**Analysedatum:** 24.09.2026
**Arbeitsgrenze:** ausschließlich der unten aufgeführte Bestand unter `/workspaces/MAIN`
**Änderungen am analysierten Bestand:** keine

## 1. Prüfumfang und Methodik

### 1.1 Vollständige Dateiliste

| # | Pfad | Logische Zeilen | Git-Modus | Lesestatus | Strukturstatus |
|---:|---|---:|---:|---|---|
| 1 | `AGENTS.md` | 44 | `100644` | geprüft: ja | vollständig lesbarer UTF-8-Text |
| 2 | `README.md` | 28 | `100644` | geprüft: ja | vollständig lesbarer UTF-8-Text |
| 3 | `infrastructure.md` | 747 | `100644` | geprüft: ja | vollständig lesbarer UTF-8-Text |
| 4 | `.gitignore` | 23 | `100644` | geprüft: ja | vollständig lesbarer UTF-8-Text |
| 5 | `.env.example` | 8 | `100644` | geprüft: ja | vollständig lesbarer UTF-8-Text |
| 6 | `config.json` | 1 | `100644` | geprüft: ja | gültiges JSON |
| 7 | `.devcontainer/autosave-daemon.sh` | 63 | `100755` | geprüft: ja | `bash -n` erfolgreich |
| 8 | `.devcontainer/devcontainer.json` | 27 | `100644` | geprüft: ja | gültiges JSON |
| 9 | `.devcontainer/proxy-watchdog.sh` | 52 | `100755` | geprüft: ja | `bash -n` erfolgreich |
| 10 | `.devcontainer/setup.sh` | 204 | `100755` | geprüft: ja | `bash -n` erfolgreich |
| 11 | `.devcontainer/start-on-boot.sh` | 71 | `100755` | geprüft: ja | `bash -n` erfolgreich |
| 12 | `.opencode/.gitignore` | 2 | `100644` | geprüft: ja | vollständig lesbarer UTF-8-Text |
| 13 | `.opencode/package-lock.json` | 401 | `100644` | geprüft: ja | gültiges JSON, keine doppelten Schlüssel |
| 14 | `.opencode/package.json` | 5 | `100644` | geprüft: ja | gültiges JSON, keine doppelten Schlüssel |
| 15 | `.opencode/opencode.json` | 310 | `100644` | geprüft: ja | gültiges JSON, keine doppelten Schlüssel |
| 16 | `.opencode/tui.json` | 18 | `100644` | geprüft: ja | gültiges JSON, keine doppelten Schlüssel |

**Gesamtumfang:** 16 reguläre Textdateien, 2.004 logische Zeilen. Keine Symlinks und keine Binärdateien im Prüfumfang. Alle Dateien sind versioniert; der Arbeitsbaum war für diesen Pfadumfang unverändert.

### 1.2 Abgrenzung

- Der gesamte Ordner `.devcontainer/` umfasst genau die fünf unter Punkt 1.1 gelisteten Dateien.
- Unter `.opencode/` wurden nur die versionierten Dateien **direkt** im Ordner berücksichtigt: `.gitignore`, `package.json`, `package-lock.json`, `opencode.json` und `tui.json`.
- `.opencode/node_modules/` wurde ausgeschlossen.
- Die Unterordner `.opencode/agent/` und `.opencode/command/` waren nicht Teil der Formulierung „direkt unter `.opencode/`“ und wurden nicht in die Dateiliste aufgenommen.
- `Revision.md` wurde nicht verändert und nicht als Prüfobjekt behandelt.
- `.env` und `config/passphrase` wurden nicht gelesen. Deren Inhalte oder Werte werden in diesem Report nicht ausgegeben.

### 1.3 Durchgeführte lokale Prüfungen

- Jede der 16 Dateien wurde vollständig und zeilenweise gelesen.
- UTF-8-Dekodierung, NUL-Bytes, reguläre Dateiart, logische Zeilenzahl und abschließender Zeilenumbruch wurden geprüft.
- Alle sechs JSON-Dateien wurden lokal geparst; zusätzlich wurden doppelte JSON-Schlüssel geprüft. Es gab keine Syntaxfehler.
- Alle vier Bash-Skripte wurden ausschließlich mit `bash -n` statisch auf Syntaxfehler geprüft. Sie wurden nicht gestartet.
- Der versionierte Modus der Skripten ist `100755`; alle übrigen Dateien sind im Git-Index `100644`.
- Es erfolgten keine Installationen, keine Skript-/Dienststarts, keine lokalen oder externen HTTP-/Netzwerkzugriffe und keine destruktiven Aktionen.
- Eine JSON-Schema-Validierung gegen das im Config referenzierte externe Schema wurde wegen des Verbots von Netzwerkzugriffen nicht durchgeführt. „JSON gültig“ bedeutet daher nur syntaktisch gültig, nicht vollständig schema- oder semantikvalidiert.
- `shellcheck` ist nicht installiert; es wurde deshalb nicht nachinstalliert und nicht ausgeführt.

### 1.4 Lesbarkeit

Alle 16 Dateien waren lesbar. Es gibt keine unlesbare Datei und daher keinen eingeschränkten strukturellen Prüfstatus.

## 2. Priorisierte Gesamtbefunde

### Hoch

1. **Zwei Credentials sind im versionierten `opencode.json` im Klartext eingebettet.** Betroffen sind ein externer API-Schlüssel in `.opencode/opencode.json:12` und ein lokales Proxy-Token in `.opencode/opencode.json:114`. Die Werte werden hier bewusst nicht wiederholt. Das widerspricht `AGENTS.md:43` und `infrastructure.md:66-67`, wonach API-Schlüssel aus dem versionierten Config heraus über Dateireferenzen bezogen werden. Durch Git-Historie, Forks, Logs oder versehentliche Config-Kopien sind die Credentials exponiert.
2. **Globales `permission: "allow"` erhöht die Wirkung des Secret-Risikos.** `.opencode/opencode.json:284` erlaubt Tool-/Aktionen ohne interaktive Rückfrage. Zusammen mit untrusted Repository-Inhalten, Remote-Provider-Fehlern und einem Agenten mit weitreichenden Datei-/Shell-Rechten ist dies eine hohe Betriebs- und Prompt-Injection-Gefahr.
3. **`postStartCommand` mutiert unabhängig vom aktuellen Branch.** `.devcontainer/devcontainer.json:13` führt bei jedem Start `git pull --rebase --autostash origin main` aus. Auf einem Feature-Branch wird dieser Branch auf `origin/main` rebased, nicht lediglich der Main-Branch aktualisiert. Fehler und Rebase-Konflikte werden durch `|| true` verborgen.
4. **Der Setup-Pfad für Go ist im frischen Zustand nicht ordnungsgemäß garantiert.** `.devcontainer/setup.sh:146` schreibt nach `/tmp/opencode/go.tgz`, erstellt `/tmp/opencode` aber erst später in `.devcontainer/setup.sh:178`. Ohne vorherige Seiteneffekte anderer, nicht garantierter Skripte schlägt der Go-Download auf einem frischen Codespace fehl.
5. **`setup.sh` hält einen beliebigen Portbeleg für den gewünschten Dienst.** Die Prüfungen in `.devcontainer/setup.sh:128`, `.devcontainer/setup.sh:154` und `.devcontainer/setup.sh:165` prüfen nur, ob ein Listener existiert, nicht Prozessidentität oder HTTP-Health. Ein fremder Listener wird als „Proxy/Server läuft bereits“ gemeldet. Das widerspricht der im Changelog beschriebenen Fremdbelegungserkennung des Startpfads.
6. **Der Autosave-Daemon committet und pusht automatisch alle nicht ignorierten Änderungen.** `.devcontainer/autosave-daemon.sh:38` erkennt untracked Dateien und `.devcontainer/autosave-daemon.sh:58` übergibt sie an `save.sh` mit `add -A`. Das kann unfertige, versehentlich erzeugte oder nicht ausreichend ignorierte Secrets veröffentlichen und widerspricht der Agentenregel „Commits nur auf explizite Aufforderung“ in `AGENTS.md:44`.
7. **Die behauptete Reproduzierbarkeit ist durch mehrere ungepinnte Installationsquellen eingeschränkt.** `devcontainer.json` verwendet ein bewegliches Image und nur Hauptversions-Tags für Features (`.devcontainer/devcontainer.json:3-6`). `setup.sh` installiert apt-Pakete ohne Versionen, opencode über ein wechselndes Installationsskript und `uv` über ein wechselndes Installationsskript (`.devcontainer/setup.sh:8-15`, `.devcontainer/setup.sh:30-35`). Direkt in `setup.sh` ist nur Go versionsgebunden festgelegt; rclone und Firefox werden an separate, laut Doku gepinnte Skripte delegiert.

### Mittel

1. Der Root-Einstieg `config.json` ist ein valides, aber leeres JSON-Objekt und hat im geprüften Partitionsbestand keinen erkennbaren Verbraucher.
2. `.env.example` enthält nur Kommentare und keine Beispielzuweisungen. Der genannte Secrets-Befehl in `.env.example:2` lässt `infra/` aus und ist aus der Repo-Wurzel heraus falsch.
3. Die lokale Node-Version ist 18.19.1, während `package-lock.json` für benötigte transitive Pakete höhere Engines fordert: `toml` mindestens Node 20 in `.opencode/package-lock.json:339-346` und `ini` eine deutlich neuere Node-Version in `.opencode/package-lock.json:214-221`. `setup.sh` installiert lediglich die Ubuntu-Pakete `nodejs`/`npm` (`.devcontainer/setup.sh:9`). Je nach npm-Konfiguration ist die Installation damit nur mit Engine-Warnung möglich oder sie bricht ab; Laufzeitkompatibilität ist nicht garantiert.
4. `opencode` und `@opencode-ai/plugin` werden unterschiedlich gepinnt: Setup installiert die jeweils aktuelle opencode-Version (`.devcontainer/setup.sh:12-17`), `.opencode/package.json:3` pinnt das Plugin-SDK auf 1.18.30. API-Skew ist möglich.
5. `setup.sh` führt die Projektabhängigkeiten in `.opencode/` nicht explizit mit einer reproduzierbaren Paketmanager-Operation aus. Die Funktion hängt davon ab, dass opencode die vorhandene `package.json` implizit selbst installiert.
6. Das MCP-Setup behauptet in `.devcontainer/setup.sh:96`, den Pfad für einen Checkout außerhalb `/workspaces/MAIN` anzupassen. Tatsächlich wird ein vorhandener Eintrag nur anhand seines Namens gesucht und nicht auf einen neuen absoluten Pfad umgeschrieben (`.devcontainer/setup.sh:100-115`). Die aktuelle Config ist hart auf `/workspaces/MAIN` verdrahtet (`.opencode/opencode.json:287-295`).
7. Health-Checks in `proxy-watchdog.sh` und `start-on-boot.sh` akzeptieren jeden erfolgreichen HTTP-Status unter 400, ohne Antwortinhalt oder Prozessidentität zu validieren (`.devcontainer/proxy-watchdog.sh:20-34`, `.devcontainer/start-on-boot.sh:16-45`). Für Antigravity wird `/v1/models` ohne Authentifizierung geprüft; die Robustheit hängt von der tatsächlichen Endpoint-Semantik ab.
8. Die Lockfile-Prüfung aller drei Daemonen ist nicht atomar und validiert weder PID-Identität noch ein Kommandozeilenprofil. Ein stale PID kann einen Neustart blockieren; ein Start-Race kann mehrere Instanzen zulassen.
9. `setup.sh` behauptet Idempotenz, bricht wegen `set -euo pipefail` aber bei einem transienten Fehler in `apt-get update`, opencode-Installation oder uv-Installation ab und erreicht spätere optionale/recoveryfähige Schritte nicht.
10. Für `xinjianya/gpt-5.6-sol` und den neuen TokenRouter-Eintrag fehlen explizite Context-/Output-Limits. Das kann Compaction, Abbruchverhalten und Kostenkontrolle weniger vorhersagbar machen.
11. `setup.sh` löscht den apt-Paketcache automatisch (`.devcontainer/setup.sh:10`) und entfernt bei einer Go-Neuinstallation `/usr/local/go` (`.devcontainer/setup.sh:147`). Das steht in Spannung zur Agentenregel, wonach Caches/Installationen nicht ohne explizite Freigabe gelöscht werden sollen (`AGENTS.md:37`).
12. `start-on-boot.sh` verwendet für den Hintergrund-Rebuild nur `nohup`, nicht `setsid` (`.devcontainer/start-on-boot.sh:24-26`). Das ist schwächer als die im gleichen Boot-Pfad korrekt abgesicherten Daemonen und kann vom Process-Group-Cleanup der Devcontainer-CLI betroffen sein.

### Niedrig

1. Vier Dateien haben keinen finalen Zeilenumbruch: `README.md`, `config.json`, `.devcontainer/devcontainer.json` und `.opencode/opencode.json`.
2. `proxy-watchdog.sh` springt in den Kommentaren von Block 3 zu Block 5; `start-on-boot.sh` von Block 2 zu Block 4. Das ist rein strukturell.
3. `.gitignore` verwendet sehr breite Muster für `*.db`, `*.log` und `*.pid`; gewollte Test-Fixtures oder Logs könnten unbeabsichtigt unbemerkbar bleiben.
4. Die Watchdog- und Autosave-Logs wachsen ohne lokale Rotation; sie liegen nur unter `/tmp` und sind damit ephemer, aber in einer langen Sitzung kann das Volumen wachsen.
5. Die README-/Layout-Tabellen nennen bei `.devcontainer/` und `.opencode/` nur einen Teil des tatsächlichen Bestands.

## 3. Querverweise und Widersprüche

| ID | Aussage A | Aussage B / Ist-Befund | Bewertung |
|---|---|---|---|
| Q-01 | `AGENTS.md:5` nennt `setup.sh` beim „Codespace-Start“ und ordnet es `postCreateCommand` zu. | `infrastructure.md:247-256` und `.devcontainer/devcontainer.json:12-13` trennen `postCreateCommand` und `postStartCommand` korrekt. | Lifecycle-Aussage in `AGENTS.md` verkürzt und missverständlich. |
| Q-02 | `AGENTS.md:6` nennt „Benchmark-Kopien“ als letzter Setup-Stufe. | In `.devcontainer/setup.sh` gibt es keinen Benchmark-Kopier- oder Benchmark-Startschritt. | Nicht belegter Querverweis. |
| Q-03 | `AGENTS.md:8` verlangt PAT **und Passphrase** als Codespaces-Secrets. | `AGENTS.md:9` und `infrastructure.md:56-65` nennen die Passphrase als repo-resident und optionale Umgebungsvariable. | Interner Widerspruch im Agentenvertrag. |
| Q-04 | `AGENTS.md:44`: Commits nur auf explizite Aufforderung. | `.devcontainer/autosave-daemon.sh:37-58` automatisiert Commit und Push. | Kein dokumentierter Policy-Ausnahme für den Hintergrunddienst. |
| Q-05 | `AGENTS.md:43` und `infrastructure.md:66-67`: Klartext-Secrets nicht committen bzw. API-Keys per Dateireferenz. | `.opencode/opencode.json:12` und `.opencode/opencode.json:114` enthalten Klartext-Credentials. | Direkter Sicherheits- und Doku-Widerspruch. |
| Q-06 | `infrastructure.md:24` listet `infra/browser/` mit Playwright 1.48.2 als aktuellen Layout-Bestand. | `infrastructure.md:192-196` und `infrastructure.md:556-564` erklären den Stack als entfernt; `infra/browser` existiert nicht. | Veralteter Layout-Eintrag. |
| Q-07 | `infrastructure.md:77` nennt im aktuellen Provider-Table zusätzlich `glm-5.3-think`. | `.opencode/opencode.json:91-106` enthält nur `glm-5.3`; `infrastructure.md:300-304` und `infrastructure.md:483-487` dokumentieren die Entfernung. | Veralteter aktueller Table. |
| Q-08 | `infrastructure.md:132`: Setup rebuildet nur bei `LANDSCAPE_REBUILD_LLM_PROXIES=1`. | `.devcontainer/setup.sh:128-134` führt den Rebuild bei freiem Port immer aus; die Variable kommt im Setup nicht vor. | Direkt widersprüchliche Betriebsregel. |
| Q-09 | `infrastructure.md:159-164` nennt für Opus/Sonnet 75.000 Context und Opus/Sonnet als Konfiguration. | `.opencode/opencode.json:143-167` enthält nur Opus mit 100.000 Context; `infrastructure.md:78` nennt bereits 100.000, der Changelog dokumentiert die Entfernung von Sonnet. | Veralteter Abschnitt innerhalb der aktuellen Sollbeschreibung. |
| Q-10 | `infrastructure.md:73-78` listet vier Provider. | `.opencode/opencode.json:4-19` enthält zusätzlich einen nicht dokumentierten TokenRouter-Provider. | Anbieter-Tabelle unvollständig; kein Changelog-Eintrag im geprüften Bestand. |
| Q-11 | `.env.example:2` nennt `scripts/secrets.sh lock`. | `infrastructure.md:64` und alle tatsächlichen Skriptaufrufe nutzen `infra/scripts/secrets.sh`. | Falscher relativer Pfad im Beispiel. |
| Q-12 | `.devcontainer/setup.sh:96` verspricht Pfadanpassung für einen Checkout außerhalb `/workspaces/MAIN`. | Bestehender MCP-Eintrag wird nicht ersetzt; `.opencode/opencode.json:291` bleibt absolut. `.devcontainer/devcontainer.json:13` ist ebenfalls absolut. | Portable-Claim nicht für die bestehende Config erfüllt. |
| Q-13 | `README.md:3-5` beschreibt alles als reproduzierbar. | Image-/Feature-Tags, apt-Pakete, opencode und uv sind nicht versionsgebunden gepinnt; mehrere Installationspfade sind zustandsabhängig. | Reproduzierbarkeit ist zu absolut formuliert. |

Historische Changelog-Einträge wurden nicht als aktueller Sollzustand bewertet, sofern sie eindeutig als vergangene Änderung datiert sind. Die Widersprüche oben betreffen aktuelle Übersichten, Kommentare oder tatsächlich ausgeführte Pfade.

## 4. Dateiweise Analyse

### 4.1 `AGENTS.md`

- **Pfad:** `AGENTS.md`
- **Zeilenzahl:** 44
- **geprüft:** ja
- **Zweck:** Session- und Agentenvertrag für Persistenz, Infrastrukturklassifikation, Safety, Dokumentationspflicht und Commit-Politik.
- **Wichtige Abhängigkeiten:** `infrastructure.md`, `.devcontainer/setup.sh`, `.devcontainer/start-on-boot.sh`, `infra/scripts/save.sh`, `config/passphrase`, Git und das feste Workspace-Verzeichnis `/workspaces/MAIN`.
- **Konfigurations-/Betriebsrisiken:**
  - Fester Pfad setzt einen Standard-Codespace-Layout voraus.
  - Die Passphrasen-Pflicht in Zeile 8 widerspricht dem optionalen Repo-Fallback in Zeile 9 und der Soll-Doku.
  - Die Commit-Regel steht im Konflikt zum automatischen Autosave.
  - Die Secret-Regel wird durch den aktuellen `opencode.json`-Bestand verletzt.
- **Konkrete Befunde:**
  - `AGENTS.md:5-6` verwechselt Create- und Resume-Lifecycle und erwähnt eine nicht im Setup vorhandene Benchmark-Kopie.
  - `AGENTS.md:28-30` fordert gepinnte, reproduzierbare Infrastruktur; die effektiven Installationsquellen erfüllen das nur teilweise.
  - `AGENTS.md:37` verbietet Cache-/Installationslöschung ohne Freigabe; Setup löscht apt-Caches und ersetzt Go ohne eigenen Rückweg.
  - Die Datei ist strukturell vollständig und enthält keine unlesbaren Abschnitte.

### 4.2 `README.md`

- **Pfad:** `README.md`
- **Zeilenzahl:** 28
- **geprüft:** ja
- **Zweck:** Kurze öffentliche Übersicht über Layout, Doku und Quick-Start.
- **Wichtige Abhängigkeiten:** `infrastructure.md`, `.devcontainer/`, `.opencode/`, `config/`, `infra/`, `llm-proxies/`, `infra/scripts/save.sh`.
- **Konfigurations-/Betriebsrisiken:**
  - „Alles versioniert und reproduzierbar“ ist zu absolut; Runtime-Zustand, Browserprofil und ungepinnte Installateile sind nicht vollständig reproduzierbar.
  - Die `config/`-Beschreibung erwähnt Bundle und Manifest, nicht den bewusst im Repo liegenden Klartext-Passphrasenbestand.
- **Konkrete Befunde:**
  - Der Link auf `infrastructure.md` ist strukturell korrekt.
  - Die Layouttabellen fassen `.devcontainer/` und `.opencode/` unvollständig zusammen; mehrere Daemon- und Paketdateien fehlen.
  - `README.md` besitzt keinen finalen Zeilenumbruch.
  - Es wurden keine Quellwerte oder Secrets ausgegeben.

### 4.3 `infrastructure.md`

- **Pfad:** `infrastructure.md`
- **Zeilenzahl:** 747
- **geprüft:** ja
- **Zweck:** Zentrale Betriebs-, Layout-, Secrets-, Port-, Proxy-, Lifecycle- und Changelog-Dokumentation.
- **Wichtige Abhängigkeiten:** sämtliche unter `infra/`, `.devcontainer/`, `.opencode/`, `llm-proxies/` und `config/` genannten Dateien; externe Provider, Ports 8001/9878/4096, Browser-Runtime, Google Drive und GitHub Codespaces.
- **Konfigurations-/Betriebsrisiken:**
  - Das Dokument bündelt Sollzustand und historische, teils live verifizierte Aussagen; dadurch sind Verfalls- und Widerspruchspotenzial hoch.
  - Das Secrets-Modell ist absichtlich lax, und eine Klartext-Passphrase schützt das Bundle nicht gegen kompromittierte Repositories oder Konten.
  - Live-/Remote-Aussagen wurden im Rahmen dieser statischen Analyse nicht erneut verifiziert.
- **Konkrete Befunde:**
  - Aktuelle Angaben zu Standardmodell, TUI-Maus-Einstellung, Port 8001, Opus-Context 100.000 und der einzigen GLM-`max`-Variante sind mit `opencode.json`/`tui.json` vereinbar.
  - Aktuelle Übersichten widersprechen dem Ist bei `infra/browser/`, `glm-5.3-think`, dem Rebuild-Gate und dem 75k/16k-Maßnahmenabschnitt.
  - Der Provider-Table omittiert den aktuell vorhandenen TokenRouter-Provider.
  - `infrastructure.md:66-67` beschreibt sämtliche API-Keys als Dateireferenzen; die zwei Klartext-Credentials in `opencode.json` widerlegen dies.
  - `infrastructure.md:132` beschreibt ein im Setup nicht vorhandenes Rebuild-Gate.
  - Die Changelog-Aussagen zu früheren Modellen wurden als historisch behandelt und nicht pauschal als Widerspruch gewertet.

### 4.4 `.gitignore`

- **Pfad:** `.gitignore`
- **Zeilenzahl:** 23
- **geprüft:** ja
- **Zweck:** Ausschluss von Runtime-, Secret-, Datenbank-, Log-, PID-, Node-/Python-Cache- und Proxy-Runtime-Dateien.
- **Wichtige Abhängigkeiten:** Git-Ignore-Semantik; `.env`; `.secrets/`; `.runtime/`; `llm-proxies/glm2api/`; `llm-proxies/dist/`.
- **Konfigurations-/Betriebsrisiken:**
  - Breite Glob-Muster können legitime Test-Fixtures oder bewusst versionierte Logs/DBs aus Versehen verbergen.
  - `.gitignore` schützt nicht gegen bereits im Index befindliche Klartext-Credentials in `.opencode/opencode.json`.
  - `config/passphrase` ist absichtlich nicht ignoriert.
- **Konkrete Befunde:**
  - Das Muster `.env` deckt auch verschachtelte `.env`-Dateien ab; der explizite glm2api-Eintrag ist daher redundant, aber dokumentierend.
  - `node_modules/` wird zusätzlich durch `.opencode/.gitignore` abgedeckt.
  - Der alte `.secrets/`-Eintrag bleibt als Rückwärtsschutz sinnvoll, obwohl der aktuelle Sollzustand auf `~/.config/landscape/` migriert wurde.
  - Es wurden keine `.env`-Inhalte gelesen.

### 4.5 `.env.example`

- **Pfad:** `.env.example`
- **Zeilenzahl:** 8
- **geprüft:** ja
- **Zweck:** Sollte eine nicht geheimhaltbare Vorlage für manuelle `.env`-Werte sein.
- **Wichtige Abhängigkeiten:** `.env`, Secrets-Bundle, `infra/scripts/secrets.sh`, `~/.config/landscape/`.
- **Konfigurations-/Betriebsrisiken:**
  - Die Datei enthält keine Variablen-Zuweisungen und ist damit keine funktionale Wertevorlage.
  - Der Befehl in Zeile 2 ist relativ zur Repo-Wurzel falsch.
- **Konkrete Befunde:**
  - Der Pfad muss auf `infra/scripts/secrets.sh lock` lauten.
  - Die Datei nennt nur Dateiziele für Credentials, aber weder Schlüsselnamen/Werte noch eine `.env`-Struktur.
  - Es wurden keine Werte aus einer echten `.env` ausgegeben oder benötigt.

### 4.6 `config.json`

- **Pfad:** `config.json`
- **Zeilenzahl:** 1
- **geprüft:** ja
- **Zweck:** Im Bestand nicht bestimmbar; syntaktisch ein leeres JSON-Objekt.
- **Wichtige Abhängigkeiten:** Im geprüften Partitionsbestand keine erkennbare.
- **Konfigurations-/Betriebsrisiken:**
  - Die Datei kann ein Platzhalter oder ein überholtes Artefakt sein.
  - Ohne Verbraucher oder Kommentar ist die beabsichtigte Laufzeitfunktion nicht nachvollziehbar.
- **Konkrete Befunde:**
  - JSON-Syntax gültig; keine doppelten Schlüssel.
  - Kein finaler Zeilenumbruch.
  - Die Datei ist versioniert, aber im untersuchten Partitionsbestand nicht referenziert.

### 4.7 `.devcontainer/autosave-daemon.sh`

- **Pfad:** `.devcontainer/autosave-daemon.sh`
- **Zeilenzahl:** 63
- **geprüft:** ja
- **Zweck:** Endlosschleife, die alle 30 Minuten uncommittete oder ungepushte Änderungen über `save.sh` committen/pushen soll.
- **Wichtige Abhängigkeiten:** Bash, Git, `infra/scripts/save.sh`, `/tmp/opencode/`, der aktuelle Checkout und `origin/main`.
- **Konfigurations-/Betriebsrisiken:**
  - Automatischer `add -A` kann nicht ignorierte Secrets, Credentials oder unfertige Arbeit veröffentlichen.
  - Nur `origin/main..HEAD` gilt als Upstream-Prüfung; ein anderer oder fehlender Tracking-Referenzzustand wird nicht korrekt abgebildet.
  - Ein alter Lockfile-PID kann einen echten Neustart verhindern; das Schreiben ist nicht atomar.
  - Keine Log-Rotation.
- **Konkrete Befunde:**
  - `bash -n` erfolgreich.
  - Die untracked-Prüfung erfasst neue, nicht ignorierte Dateien (`git ls-files --others --exclude-standard`).
  - Fehlgeschlagenes `save.sh` beendet den Daemon nicht; der nächste Intervallversuch erfolgt erneut.
  - Die Automatik widerspricht `AGENTS.md:44` und sollte als explizite Ausnahme oder durch einen sicheren Dateifilter geregelt werden.

### 4.8 `.devcontainer/devcontainer.json`

- **Pfad:** `.devcontainer/devcontainer.json`
- **Zeilenzahl:** 27
- **geprüft:** ja
- **Zweck:** Definition des Ubuntu-24.04-Codespaces, Features, Create-/Start-Hooks, TZ und VS-Code-Erweiterungen.
- **Wichtige Abhängigkeiten:** `mcr.microsoft.com/devcontainers/base:ubuntu-24.04`, zwei Devcontainer-Features, `.devcontainer/setup.sh`, `.devcontainer/start-on-boot.sh`, `/workspaces/MAIN`, Git und `origin/main`.
- **Konfigurations-/Betriebsrisiken:**
  - Bewegliches Image, Feature-Hauptversionen und nicht gepinnte Erweiterungen sind nicht deterministisch.
  - Docker-in-Docker erweitert die Angriffs-/Fehlerfläche, ohne in Partition A eine notwendige Abhängigkeit zu belegen.
  - `postStartCommand` rebased den aktuell ausgecheckten Branch und unterdrückt Fehler.
  - `postStartCommand` ist auf `/workspaces/MAIN` fest verdrahtet.
- **Konkrete Befunde:**
  - JSON-Syntax gültig; keine doppelten Schlüssel.
  - `postCreateCommand` und `postStartCommand` sind als getrennte Hooks grundsätzlich korrekt angelegt.
  - Kein finaler Zeilenumbruch.
  - Der Pull sollte branchbewusst erfolgen und Fehler mindestens sichtbar bleiben.

### 4.9 `.devcontainer/proxy-watchdog.sh`

- **Pfad:** `.devcontainer/proxy-watchdog.sh`
- **Zeilenzahl:** 52
- **geprüft:** ja
- **Zweck:** Alle 30 Sekunden Health-Checks für zwei Proxies und den opencode-Server ausführen und fehlende Dienste sowie Autosave-/Config-Watchdog starten.
- **Wichtige Abhängigkeiten:** `curl`, `/tmp/opencode/`, `llm-proxies/scripts/start-glm2api.sh`, `llm-proxies/antigravity-proxy/scripts/start.sh`, `infra/scripts/opencode-server.sh`, `infra/scripts/config-watchdog.sh`, `.devcontainer/autosave-daemon.sh`.
- **Konfigurations-/Betriebsrisiken:**
  - Jeder erfolgreiche HTTP-Status unter 400 wird als Identitätsnachweis akzeptiert; ein fremder HTTP-Dienst kann als gesund gelten.
  - Antigravity-Health hängt davon ab, dass `/v1/models` ohne Authentifizierungsheader erreichbar ist.
  - Watchdog selbst stellt kein `/tmp/opencode` sicher; das ist eine Abhängigkeit von einem vorgeschalteten Erzeuger.
  - Lockfile-Race/stale PID, unbegrenztes Logwachstum und serielle Startlatenz.
- **Konkrete Befunde:**
  - `bash -n` erfolgreich.
  - Die Startskripte werden nicht bei Fremdbelegung oder wiederholtem Fehlstart unterschieden.
  - Kommentarnummerierung springt von 3 auf 5; funktional irrelevant.
  - `disown` wird zusätzlich trotz `setsid nohup` verwendet; dies ist redundant, aber nicht zwingend fehlerhaft.

### 4.10 `.devcontainer/setup.sh`

- **Pfad:** `.devcontainer/setup.sh`
- **Zeilenzahl:** 204
- **geprüft:** ja
- **Zweck:** Vollständiger Post-Create-Setup für Systempakete, opencode/uv, Aliase, Secrets, Git-Auth, rclone, Firefox, MCP, GLM-/Antigravity-Proxies, opencode-Server und drei Watchdogs/Daemons.
- **Wichtige Abhängigkeiten:** `sudo`, apt, `curl`, `wget`, `git`, `jq`, `sed`, `python3`, `ss`, `grep`, `head`, `setsid`, `disown`, mehrere `infra/scripts/*`-Dateien, beide Proxy-Startpfade, `config/secrets.enc` und optionale Codespaces-Variablen.
- **Konfigurations-/Betriebsrisiken:**
  - Netzwerk- und Supply-Chain-Abhängigkeit über apt, Installationsskripte, rclone, Firefox und Go.
  - Nur Existenz, nicht Version, wird für bereits vorhandenes opencode/uv geprüft.
  - `set -euo pipefail` macht frühe Netzfehler fatal; spätere Recovery-Schritte werden nicht erreicht.
  - Portbelegungsprüfungen sind keine Health-/Identitätsprüfungen.
  - `/tmp/opencode` wird für den Go-Download zu spät sichergestellt.
  - Go ist auf `linux-amd64` und ohne dokumentierte Prüfsumme festgelegt; andere Architekturen sind nicht abgedeckt.
  - Die MCP-Injektion per String/Python/sed ist fragil bei nichtstandardmäßigem JSON/JSONC, leerer Datei, BOM oder veraltetem gleichnamigen Eintrag.
  - Der bestehende MCP-Pfad wird bei einem Checkout außerhalb des Standardpfads nicht aktualisiert.
  - `sudo rm -rf /var/lib/apt/lists/*` und `sudo rm -rf /usr/local/go` sind pauschale Löschungen.
- **Konkrete Befunde:**
  - `bash -n` erfolgreich.
  - Die wichtigsten referenzierten Betriebsdateien existieren im Repository.
  - `setup.sh` enthält kein `LANDSCAPE_REBUILD_LLM_PROXIES`-Gate.
  - Beim Rebuild wird glm2api bei freiem Port immer gestartet; Antigravity und opencode-Server folgen danach.
  - Die MCP-Zeile wird sowohl in die Projekt- als auch globale opencode-Config einzufügen versucht.
  - Setup stellt nach den drei Proxy-/Serverstarts `/tmp/opencode` erst für die Watchdog-Phase her.

### 4.11 `.devcontainer/start-on-boot.sh`

- **Pfad:** `.devcontainer/start-on-boot.sh`
- **Zeilenzahl:** 71
- **geprüft:** ja
- **Zweck:** Leichtgewichtiger Resume-/Startpfad für Secrets-Sentinel, Proxies, Server und Hintergrunddienste.
- **Wichtige Abhängigkeiten:** `curl`, `secrets.sh`, beide Proxy-Startskripte, `opencode-server.sh`, `config-watchdog.sh`, `autosave-daemon.sh`, `/tmp/opencode`.
- **Konfigurations-/Betriebsrisiken:**
  - Das Health-Modell ist dasselbe wie im Proxy-Watchdog und nur HTTP-statusbasiert.
  - Secrets werden nur dann erneut entpackt, wenn genau ein OAuth-Zieldatei-Sentinel fehlt; andere fehlende Bundle-Ausgaben werden nicht erkannt.
  - Der Hintergrund-Rebuild nutzt kein `setsid` und startet vor der lokalen Erstellung seines Logverzeichnisses.
  - Daemon-Lockfiles sind nicht atomar und PID-basiert.
- **Konkrete Befunde:**
  - `bash -n` erfolgreich.
  - `/tmp/opencode` wird erst nach dem möglichen Rebuild-Aufruf erstellt.
  - Kommentarnummerierung springt von 2 auf 4; funktional irrelevant.
  - Der Startpfad ist auf feste Repo-Skriptpfade relativ zum eigenen Ort robust, während `devcontainer.json` selbst den übergeordneten festen Workspace-Pfad nutzt.

### 4.12 `.opencode/.gitignore`

- **Pfad:** `.opencode/.gitignore`
- **Zeilenzahl:** 2
- **geprüft:** ja
- **Zweck:** Ausschluss von `node_modules/` und `bun.lock` innerhalb von `.opencode/`.
- **Wichtige Abhängigkeiten:** npm-Lockfile als aktuell versionierter Repro-Referenz; Bun, falls ein Entwickler damit arbeitet.
- **Konfigurations-/Betriebsrisiken:**
  - Ignorieren von `bun.lock` verhindert eine versehentlich eingecheckte zweite Lockfile-Historie, macht Bun-Installationen aber nicht reproduzierbar.
- **Konkrete Befunde:**
  - `node_modules/` ist bereits durch das Root-`.gitignore` abgedeckt.
  - Keine strukturellen Syntaxprobleme.

### 4.13 `.opencode/package.json`

- **Pfad:** `.opencode/package.json`
- **Zeilenzahl:** 5
- **geprüft:** ja
- **Zweck:** NPM-Metadaten für die exakt gepinnte opencode-Plugin-/SDK-Abhängigkeit.
- **Wichtige Abhängigkeiten:** `@opencode-ai/plugin` 1.18.30, `package-lock.json`, npm und implizite opencode-Paketautomatisierung.
- **Konfigurations-/Betriebsrisiken:**
  - Keine `engines`, kein `packageManager`, keine Projektversion und keine `private`-Markierung.
  - Kein Root-Script legt die Installationsstrategie fest.
  - Das Plugin-SDK ist gepinnt, das im Setup installierte opencode nicht.
- **Konkrete Befunde:**
  - JSON-Syntax gültig; keine doppelten Schlüssel.
  - Root-Abhängigkeit stimmt exakt mit dem Lockfile überein.

### 4.14 `.opencode/package-lock.json`

- **Pfad:** `.opencode/package-lock.json`
- **Zeilenzahl:** 401
- **geprüft:** ja
- **Zweck:** npm-Lockfile v3 für Plugin-SDK, transitiven Runtime-Baum und optionale Plattformpakete.
- **Wichtige Abhängigkeiten:** Registry-/Integritätsmetadaten, npm ≥ Lockfile-3-Unterstützung, Node-Versionen der transitiven Pakete, Zielplattform.
- **Konfigurations-/Betriebsrisiken:**
  - `toml` fordert Node ≥20, `ini` fordert eine wesentlich neuere Node-Version; Setup und lokale Laufzeit liefern Node 18.19.1.
  - Das Lockfile ist plattformübergreifend, enthält aber native optionale Pakete; Installation hängt von npm-Plattformauflösung und optionalen Prebuilds ab.
  - Ein unpinntes opencode kann eine ältere Plugin-SDK-Version erwarten oder umgekehrt.
- **Konkrete Befunde:**
  - JSON-Syntax gültig; keine doppelten Schlüssel.
  - Lockfile-Version 3, Root-Dependency und Version stimmen mit `package.json` überein.
  - Die verwendete lokale Node-Version erfüllt die genannten Engine-Mindestversionen nicht; dies ist ohne `engine-strict` nicht zwingend ein Installationsabbruch, aber eine reale Kompatibilitätsannahme.
  - Registry-URLs und Integritätswerte wurden nicht gegen das Netz verifiziert.

### 4.15 `.opencode/opencode.json`

- **Pfad:** `.opencode/opencode.json`
- **Zeilenzahl:** 310
- **geprüft:** ja
- **Zweck:** Zentrale opencode-Konfiguration für Remote-/lokale Provider, Modelle, Limits, Reasoning-Varianten, Standardmodell, Rechte, LSP, MCP und Compaction.
- **Wichtige Abhängigkeiten:** opencode-Schema und -Runtime; externe NVIDIA-/XinJianYa-/TokenRouter-Provider; lokale Ports 8001 und 9878; Dateien unter `~/.config/landscape/`; lokaler stdio-MCP-Prozess mit direktem SQLite-Zugriff; Node unter `/workspaces/MAIN/infra/mcp/opencode-sessions-mcp.js`.
- **Konfigurations-/Betriebsrisiken:**
  - Zwei versionierte Klartext-Credentials.
  - Globales `allow` für Berechtigungen.
  - Undokumentierter Remote-Provider mit Klartext-Credential.
  - Absolute MCP-Pfade verhindern einen Checkout außerhalb `/workspaces/MAIN`; setup.sh ersetzt vorhandene Pfade nicht.
  - Zwei Provider-Modelle ohne explizite Context-/Output-Limits.
  - Das Standardmodell hängt von lokalen, durch Watchdog verwalteten Diensten ab.
- **Konkrete Befunde:**
  - JSON-Syntax gültig; keine doppelten Schlüssel.
  - Standardmodell, GLM-`max`-Variante, Gemini-Limits, Opus-100k/16k-Limit, Compaction-Reserve und TUI-Einstellung entsprechen dem aktuellen Teil der Betriebsdoku.
  - `.opencode/opencode.json:12` und `.opencode/opencode.json:114` enthalten Klartext-Credentials; Werte wurden nicht wiederholt.
  - `.opencode/opencode.json:284` setzt globale Permission auf `allow`.
  - Der TokenRouter-Block ist in keinem aktuellen Provider-Table des Changelogs dokumentiert.
  - Der MCP-BLOCK ist nicht relativ und widerspricht dem Portable-Claim.
  - Für TokenRouter und XinJianYa fehlen explizite Context-/Output-Limits.
  - Kein finaler Zeilenumbruch.
  - Das externe Schema wurde aus Gründen des Netzwerkverbots nicht validiert.

### 4.16 `.opencode/tui.json`

- **Pfad:** `.opencode/tui.json`
- **Zeilenzahl:** 18
- **geprüft:** ja
- **Zweck:** Opencode-TUI-Maus- und Keybind-Konfiguration.
- **Wichtige Abhängigkeiten:** Opencode-TUI-Schema, xterm.js-Mausradübersetzung, Browser-/Terminal-UI.
- **Konfigurations-/Betriebsrisiken:**
  - Die gewünschte Halbseiten-Navigation über Auf-/Ab-Tasten hängt von der dokumentierten xterm.js-Interpretation ab.
  - Zwei Tastenfolgen für `variant_cycle` können bei Terminal-/Browser-Implementierungen unterschiedlich ankommen.
- **Konkrete Befunde:**
  - JSON-Syntax gültig; keine doppelten Schlüssel.
  - `mouse: false` stimmt mit `infrastructure.md:85-87` überein.
  - `input_move_up`/`input_move_down` sind bewusst auf `none` gesetzt und konsistent mit der Halbseiten-Navigation.

## 5. Reale Betriebsannahmen

1. **Standardpfad:** Der überwiegende Betrieb setzt einen Checkout unter `/workspaces/MAIN` voraus. `devcontainer.json` und `opencode.json` erzwingen dies; die Portable-Aussage ist daher nur unter diesem Codespace-Layout belastbar.
2. **Privilegien:** `setup.sh` setzt funktionierendes passwortloses `sudo`, vorhandenes `ss`, `setsid`, `disown`, GNU-Sed und die installierten Systemwerkzeuge voraus. `iproute2` für `ss` wird nicht ausdrücklich installiert; die Annahme stammt aus dem Basis-Image.
3. **Hook-Arbeitsverzeichnis:** Beide Hooks setzen voraus, dass die Devcontainer-CLI `.devcontainer/...` aus dem Repo-Wurzelverzeichnis auflöst.
4. **Netzwerk:** `postCreateCommand` ist trotz „idempotent“ nicht offlinefähig; apt, Feature-Pulls, opencode, uv, rclone, Firefox und Go benötigen erreichbare Quellen.
5. **Architektur:** Der Go-Download ist für x86-64 gebaut. Auf ARM-Codespaces oder anderen Hosts ist dieser Pfad nicht korrekt.
6. **Dienstidentität:** Port- und HTTP-Checks unterscheiden nicht zwischen gewünschtem Dienst und beliebigem Listener.
7. **Antigravity-Health:** Der Watchdog setzt voraus, dass `/v1/models` ohne das konfigurierte lokale Token einen Erfolgsstatus liefert.
8. **MCP-Pakete:** Es wird vorausgesetzt, dass opencode die `.opencode/package.json`-Abhängigkeit selbst installiert/verwaltet; `setup.sh` führt dazu keinen expliziten `npm ci` aus.
9. **Plugin-Kompatibilität:** Es wird vorausgesetzt, dass die jeweils aktuelle opencode-Version mit Plugin-SDK 1.18.30 kompatibel bleibt.
10. **Secrets-Wiederherstellung:** Ein einzelner OAuth-Sentinel wird als ausreichender Hinweis für den Zustand des gesamten Secrets-Bundles verwendet.
11. **Autosave-Sicherheit:** Das Betriebsmodell setzt voraus, dass alle nicht ignorierbaren Dateien commitfähig und veröffentlichungswürdig sind.
12. **Schema-Semantik:** JSON-Schlüsselnamen wurden nicht gegen das externe opencode-Schema validiert; syntaktisch gültiges JSON garantiert keine Akzeptanz durch das konkrete opencode-Schema.

## 6. Priorisierte Empfehlungen ohne Durchführung

1. Die beiden Klartext-Credentials aus dem versionierten Config entfernen, ersetzen/rotieren und ausschließlich über verwaltete Dateireferenzen beziehen; Git-Historie und eventuelle Kopien separat bewerten.
2. `permission: "allow"` auf eine engere Tool-/Edit-Policy zurücknehmen oder mindestens als bewusste, dokumentierte Ausnahme behandeln.
3. `postStartCommand` branchbewusst machen: nur auf dem beabsichtigten Branch pullen, Divergenz explizit behandeln und Fehler nicht vollständig verschlucken.
4. `/tmp/opencode` vor jedem Zugriff sicherstellen und Go-Installpfad sowie Architektur/Prüfsumme robuster machen.
5. Portprüfungen durch Health- plus Prozessidentitätsprüfung ersetzen; Setup darf keinen beliebigen Listener als passenden Dienst akzeptieren.
6. Rebuild-, opencode-, uv-, Image-, Feature- und Node-Versionsstrategie tatsächlich pinnen oder die Reproduzierbarkeitsaussage abschwächen.
7. Node-Anforderungen des Lockfiles mit dem installierten Node/mit opencodes Laufzeitmodell abstimmen und einen expliziten reproduzierbaren Installationsschritt definieren.
8. Autosave auf branch- und upstream-korrekte Erkennung umstellen und Credentials/Dateitypen vor `add -A` filtern oder den automatischen Commit-Push als explizite Ausnahme dokumentieren.
9. Die aktuellen Abschnitte in `infrastructure.md`, `AGENTS.md` und `.env.example` mit Setup-, Provider-, Modell- und Pfadrealität synchronisieren.
10. Root-`config.json` entweder einem benannten Consumer zuordnen oder als bewusstes leeres Platzhalterformat dokumentieren.

## 7. Abschluss

Partition A umfasst 16 vollständig gelesene, strukturell lesbare Textdateien. Es wurden keine Dateien des Prüfumfangs verändert, keine Secrets aus `.env` oder `config/passphrase` ausgegeben, keine externen Klartext-Credentials im Report wiederholt und keine Revision-Datei geschrieben.
<!-- END PART A -->

## Anhang B — Infrastruktur-Skripte und Reverse-Engineering-Dokumentation

<!-- BEGIN PART B -->
## Audit Partition B — infra/scripts/ und infra/docs/

## Prüfrahmen

- Scope ausschließlich: `/workspaces/MAIN/infra/scripts/` und `/workspaces/MAIN/infra/docs/`.
- Vollständig gelesen: 16 Dateien in `infra/scripts/` (14 Shell-Skripte, 2 Python-Skripte) und 4 Dateien in `infra/docs/` (2 Python-Skripte, 2 Markdown-Dateien).
- Zeilen zählen alle sichtbaren Zeilen einschließlich Kommentar- und Leerzeilen; die Angaben unten sind mit einer statischen Zeilenzählung abgeglichen.
- Lokale, nicht-destruktive Prüfungen: `bash -n` für alle 14 Shell-Dateien erfolgreich; AST-Parse für alle 4 Python-Dateien erfolgreich. `shellcheck` ist nicht installiert. Es wurden keine auditierten Skripte, Browser, Server oder Installationsläufe gestartet und kein Netzwerkzugriff ausgeführt.
- Secret-Dateien wurden nicht gelesen. Secret-Werte werden in diesem Bericht nicht ausgegeben; genannt werden ausschließlich Pfade, Variablennamen und Kategorien.
- Quellcode und `Revision.md` wurden nicht verändert.

## Risikostufen

- **Niedrig:** überwiegend Dokumentations- oder Komfortrisiko.
- **Mittel:** relevantes Robustheits- oder Betriebsrisiko ohne unmittelbare Secret-Offenlegung.
- **Hoch:** Datenverlust, Prozess-/Port-Übernahme, Secret-Leakage, unsicherer Backup-/Restore-Pfad oder gravierende Doku-/Implementierungsabweichung.

## Datei-Audits

### 1. `infra/scripts/aliases.sh`

- **Zeilenzahl:** 129
- **Zweck:** Sourced-Shell-Bibliothek für Aliase, Daemon-Wrapper, den OpenCode-Server-Attach und `landscape-diff`.
- **Befunde:**
  - **Control-Flow/Fehler/Signale:** Die Datei ist als Sourced-Skript ohne `set -e` gedacht. Die PID-Prüfungen in `autosave` und `config-watchdog` (Z. 18–23, 26–33, 36–40, 78–83, 85–92, 95–99) prüfen weder numerische PID noch Prozessidentität; stale PID-Reuse kann einen fremden Prozess als Daemon ausgeben oder beim Stoppen beenden. `pause`/`resume` (Z. 104–110) melden Erfolg auch, wenn `touch`/`rm` fehlschlägt, weil die Funktion keinen Fehlerstatus auswertet. Ein Interrupt während `start` kann einen unbestätigten Daemonzustand hinterlassen.
  - **Quoting/Pfade:** `save`, `auth`, `secrets` und `ports` verwenden relative `./infra/scripts/...`-Pfade (Z. 5–8) und funktionieren nur aus dem Repository-Root. `quota`, `gdrive`, `opencode-server` und Daemon-Starts sind dagegen auf `/workspaces/MAIN` fest verdrahtet (Z. 9, 12, 29, 70, 88). `/tmp/opencode` wird von den Wrapper-Funktionen nicht vor dem Öffnen von Log-/Pause-Dateien angelegt. Das ist inkonsistent und nicht portabel.
  - **Ports/Lifecycle:** Port 4096 wird nur über HTTP-Erreichbarkeit akzeptiert (Z. 53–67); jeder 2xx-Dienst dort gilt als OpenCode. `setsid` trennt die Prozessgruppe, schützt aber nicht vor Container-/cgroup-weitem Cleanup; die Wrapper besitzen keine Prozessidentitäts- oder Startbestätigungsprüfung.
  - **Secrets/Doku:** `landscape-diff` gibt nur Secret-Pfade und Namen aus, keine Inhalte (Z. 118–128). Die Doku-/Alias-Namen entsprechen den übrigen B-Dateien; die festen `/workspaces/MAIN`-Annahmen bleiben ein Portabilitätsrisiko.
- **Risikostufe:** Mittel
- **geprüft:** ja

### 2. `infra/scripts/auth.sh`

- **Zeilenzahl:** 79
- **Zweck:** GitHub-PAT-Ablage, Credential-Helper-/Git-Auth-Einrichtung, stiller `gh`-Login und nicht-interaktiver Push-Test.
- **Befunde:**
  - **Control-Flow/Fehler/Signale:** `set -euo pipefail` (Z. 12) ist grundsätzlich streng. `store_token` schreibt jedoch PAT-Datei, Credential-Datei, Git-Konfiguration und `gh`-Login nacheinander (Z. 20–35) ohne Rollback; ein Abbruch kann einen halb eingerichteten Auth-Zustand hinterlassen. `cmd_status` (Z. 49–65) leitet Autorisierungsurteil aus Fehlertexten ab und gibt bei anderen Fehlern die ersten Rohzeilen aus, statt eine belastbare Capability-Prüfung zu liefern.
  - **Quoting/Pfade:** `repo_slug` (Z. 16–18) ist auf GitHub-URLs zugeschnitten; bei unbekanntem Remote kann der Roh-URL-String als Slug erscheinen. `TOKEN_FILE`/`CREDS_FILE` hängen von `$HOME` ab. Der Credential-Helper-Wert (Z. 28) ist bei Leerzeichen/Sonderzeichen im Home-Pfad nicht robust escaped. Der PAT wird unescaped in eine URL geschrieben (Z. 26).
  - **Ports/Lifecycle:** Kurzlebiges Skript ohne Daemon. `gh auth status` und `git push --dry-run` wären netzwerk-/umgebungsabhängig, wurden hier aber nicht ausgeführt. Eine Signal-Trap für Teilaktionen fehlt.
  - **Secrets/Doku:** Die Datei gibt den PAT nicht absichtlich aus, akzeptiert ihn aber als Kommandozeilenargument (Z. 5, 75); besonders der Aufruf aus `secrets.sh` (dort Z. 80) legt ihn in Shell-History/Prozessliste. `cmd_clear` entfernt lokale Dateien, lässt aber eine bestehende `gh`-Anmeldung bestehen (Z. 68–71), obwohl „Token entfernt“ Vollständigkeit suggeriert. Rohes Git-Fehleroutput (Z. 63) ist nicht redigiert.
- **Risikostufe:** Hoch
- **geprüft:** ja

### 3. `infra/scripts/browser-start.sh`

- **Zeilenzahl:** 72
- **Zweck:** Start und Readiness-Prüfung des Firefox-/VNC-Stacks aus Xvfb, x11vnc und noVNC/websockify.
- **Befunde:**
  - **Control-Flow/Fehler/Signale:** Die Abhängigkeitsprüfung erfasst nur `Xvfb`, `x11vnc` und `websockify` (Z. 19–24), nicht `pgrep`, `ss`, `nohup` oder `grep`. Die Readiness-Schleifen (Z. 33–40, 59–69) prüfen Socket, Prozessmuster beziehungsweise Listener, nicht die tatsächliche Dienstidentität. Ein falscher oder kurz danach sterbender Prozess kann als bereit gelten. Es gibt keine Signal-Trap und keinen Rollback eines bereits gestarteten Teilstacks.
  - **Quoting/Pfade:** `root_dir` wird relativ zum Skript korrekt bestimmt (Z. 6). `DISPLAY` und die Start-URL werden ungeprüft aus Umgebung/Argument übernommen (Z. 10–11). `pgrep -f` verwendet Display-Text als Regex (Z. 28, 52); Metazeichen können Fehltreffer verursachen. `mkdir -p` legt das Firefox-Profil ohne explizit restriktive Rechte an (Z. 26), obwohl es Logins/Cookies enthalten kann. `/usr/share/novnc` wird nicht als Voraussetzung geprüft.
  - **Ports/Lifecycle:** 5920 wird auf `127.0.0.1` geprüft (Z. 42–45), 6082 nur generisch auf `:6082` (Z. 47–50, 61–62); ein fremder Listener wird nicht identifiziert. `x11vnc` läuft mit `-nopw`, aber `-localhost`. `websockify` erhält keine explizite Bind-Adresse und kann je nach Standard außerhalb des Localhost lauschen. Es fehlen PID-Dateien, Ownership-Tracking und `setsid`; gleichzeitige Starts können doppelte Prozesse erzeugen.
  - **Secrets/Doku:** Das Profil kann sensible Logins/Cookies enthalten, wird aber nicht ausgegeben. Die Ports sind im Skript konsistent; die Localhost-Zusage ist durch die fehlende Bind-Adresse nicht vollständig abgesichert.
- **Risikostufe:** Hoch
- **geprüft:** ja

### 4. `infra/scripts/config-watchdog.sh`

- **Zeilenzahl:** 103
- **Zweck:** Hintergrund-Daemon zum Erkennen von `.opencode/opencode.json`-Änderungen, Debounce, Pause, Busy-Guard und Server-Neustart.
- **Befunde:**
  - **Control-Flow/Fehler/Signale:** `set -u` (Z. 7) verhindert nur undefinierte Variablen. Der Lock (Z. 17–23) wird nicht atomar erstellt; zwei Daemons können gleichzeitig starten, und der EXIT-Trap eines Prozesses kann den Lock des anderen löschen. Nur HUP wird ignoriert; explizite TERM-/INT-Behandlung fehlt. Ein fehlgeschlagener `/session/status`-Request wird zu `{}` (Z. 48–60) und damit als idle gewertet. Nach 300 Sekunden wird auch bei fortgesetztem Busy-Zustand neu gestartet (Z. 43–65), entgegen „Niemals restarten solange aktiv“. Restart-Fehler werden mit `|| true` verschluckt (Z. 65–67), aber als abgeschlossen geloggt.
  - **Quoting/Pfade:** `REPO_ROOT` ist relativ robust (Z. 8), `/tmp/opencode` jedoch fest. Der Inotify-Aufruf überwacht das gesamte `.opencode`-Verzeichnis (Z. 86–95); die nachfolgende Prüfung filtert nicht den Dateinamen, sodass Schreibereignisse für andere Dateien ebenfalls einen Restart auslösen können. `md5sum`/`cut` werden im Polling-Fallback nicht als Abhängigkeiten geprüft (Z. 70–83).
  - **Ports/Lifecycle:** Port 4096 und `/session/status` sind fest verdrahtet (Z. 37–60). Jeder erreichbare HTTP-Dienst wird als Server akzeptiert. Es gibt keine Prozessidentitätsprüfung, kein eigenes `setsid` und keine Health-Bestätigung nach dem Restart.
  - **Secrets/Doku:** Es werden keine Secret-Werte verarbeitet oder geloggt; Logzeiten/Pfade sind unkritisch. Die Doku-Zusage eines sicheren Busy-Guards ist durch Request-Fehler, Text-Grep und den Timeout-Fallback nicht vollständig erfüllt.
- **Risikostufe:** Hoch
- **geprüft:** ja

### 5. `infra/scripts/firefox-install.sh`

- **Zeilenzahl:** 35
- **Zweck:** Gepinnten Firefox-Tarball nach `.runtime/firefox` herunterladen, entpacken und versionsprüfen.
- **Befunde:**
  - **Control-Flow/Fehler/Signale:** `set -euo pipefail` (Z. 5) bricht bei den meisten Fehlern ab. `curl` (Z. 24) hat weder Timeout noch Retry und kann hängen oder bei transienten Fehlern ohne Kontrolle abbrechen. Ein EXIT-Trap zum Entfernen eines unvollständigen Downloads fehlt. Wird das bestehende Ziel vor dem Entpacken gelöscht (Z. 26), bleibt bei Download-/Tar-Fehler keine funktionierende Installation und es gibt keinen Rollback.
  - **Quoting/Pfade:** `root_dir`/Runtime-Pfade sind relativ zum Skript gut bestimmt (Z. 8–11). Version, `linux-x86_64` und `en-US` sind hart codiert (Z. 7, 15–16); ARM- und andere Locale-Umgebungen werden nicht erkannt. Es fehlen SHA-256-/Signaturprüfung und Archiv-Inhaltsvalidierung. Ein fester `tmp_dir` erlaubt Konflikte bei parallelen Installationen.
  - **Ports/Lifecycle:** Keine Ports und kein Langzeitprozess; einmaliger Installer mit bedingter Temp-Bereinigung (Z. 28).
  - **Secrets/Doku:** Keine Secret-Referenzen. Die gepinnte Version und der Zielpfad entsprechen der B-Dokumentation; die fehlende Integritätsprüfung schwächt das als gepinnt beschriebene Installationsmodell.
- **Risikostufe:** Hoch
- **geprüft:** ja

### 6. `infra/scripts/gdrive-backup.sh`

- **Zeilenzahl:** 120
- **Zweck:** Git-Bundle mit Historie erzeugen, zwei Generationen auf einem rclone-Remote rotieren, Hash vergleichen und wiederherstellen.
- **Befunde:**
  - **Control-Flow/Fehler/Signale:** `set -uo pipefail` (Z. 24) enthält bewusst kein `-e`; Fehler werden nur selektiv behandelt. `cd` (Z. 25) wird nicht auf Fehler geprüft, sodass ein falscher Aufrufpfad im falschen Verzeichnis weiterlaufen kann. Rotationsfehler werden teilweise nur als Hinweis behandelt (Z. 73–75). Die Upload-Prüfung wertet den tatsächlichen Pipeline-Exitcode aus; wegen `pipefail` bleibt ein fehlgeschlagener `rclone`-Schritt auch bei erfolgreichem `grep` fehlerhaft (Z. 77–79). Es gibt keinen Trap zum Aufräumen lokaler Bundle-/State-Dateien bei Abbruch.
  - **Quoting/Pfade:** Das Root-Verzeichnis wird über `dirname "$0"` statt `BASH_SOURCE` bestimmt (Z. 25); Symlink-/PATH-Aufrufe können daher das falsche Arbeitsverzeichnis wählen. Lokale Pfade sind auf `.runtime` und `/tmp/opencode` festgelegt (Z. 32–33, 104–106). Restore-Ziel und Download-Datei sind nicht gegen Existenz oder konkurrierende Restores geschützt. `require_auth` ruft in Z. 45 direkt `rclone listremotes` statt `runc`/explizitem `RCLONE_CONFIG` auf.
  - **Ports/Lifecycle:** Keine lokalen Listener-Ports. `rclone` ist ein externer Prozess; der lokale Bundle-Pfad kann bei Abbruch das komplette Repository einschließlich `config/passphrase` enthalten und wird erst nach Erfolg gelöscht (Z. 65, 92). Es gibt keine Lock-Datei, sodass `save.sh` und manuelle Backups gleichzeitig rotieren können.
  - **Secrets/Doku:** `RCLONE_CONF` (Z. 27) verweist auf OAuth-Remote-Daten; Inhalte werden nicht ausgegeben. Die Doku behauptet MD5-Verifikation (Z. 4–10, 81–91), aber ein leerer Remote-Hash (Z. 82–86) wird als Erfolg gewertet. Das steht im Widerspruch zur Zusage der Integritätsprüfung.
- **Risikostufe:** Hoch
- **geprüft:** ja

### 7. `infra/scripts/glm2api.sh`

- **Zeilenzahl:** 188
- **Zweck:** glm2api auf `127.0.0.1:8001` über PID-/cwd-verankerte Prozesssuche verwalten.
- **Befunde:**
  - **Control-Flow/Fehler/Signale:** `set -uo pipefail` (Z. 5) erlaubt Weiterlaufen nach Fehlern. `start_server` gibt nach 30 Sekunden ohne Health-Erfolg dennoch 0 zurück (Z. 108–118). `restart_server` (Z. 167–175) kann diesen Fehler durch die abschließende Erfolgsmeldung maskieren. `check_status` hat keinen verlässlichen Gesamt-Fehlerstatus. Eine Signal-Trap fehlt; ein Interrupt während TERM/KILL oder Health-Wartezeit kann Zwischenzustände hinterlassen.
  - **Quoting/Pfade:** `GLM2API_DIR` ist absolut auf `/workspaces/MAIN/llm-proxies/glm2api` festgelegt (Z. 7). `managed_pids` erkennt jede Kommandozeile mit `main.py` und verlangt cwd (Z. 26–38); Test-/Editorprozesse im selben cwd können mitgedeckt werden. `readlink` kann bei Symlinkpfaden einen physischen cwd liefern, der nicht dem konfigurierten Pfad entspricht. Die PID-Datei wird ohne Lock/atomaren Start geschrieben (Z. 104–105).
  - **Ports/Lifecycle:** Port 8001 ist auf Localhost begrenzt (Z. 11–13). TERM/KILL ist cwd-/cmdline-verankert und besser als globales `pkill`, kann bei PID-Reuse aber trotzdem einen passenden Fremdprozess treffen. `nohup` schützt nicht zuverlässig vor Prozessgruppen-Kills; `setsid` und Ownership-Lock fehlen. Beim Stoppen kann die PID-Datei entfernt werden, während weitere Managed-Prozesse laufen (Z. 88–94).
  - **Secrets/Doku:** Keine direkte Token-/Passphrasenverarbeitung. Der Output-Log (Z. 102, 159–164) kann sensible Anwendungsdaten enthalten und wird ungefiltert ausgegeben. Die Health-Check-Zusage ist wegen Returncode 0 nach Timeout unvollständig.
- **Risikostufe:** Hoch
- **geprüft:** ja

### 8. `infra/scripts/nvidia-models.py`

- **Zeilenzahl:** 322
- **Zweck:** NVIDIA-Modellindex und Detailseiten abrufen, Free-/Bezahlstatus sowie optional API-Verfügbarkeit ermitteln und cachen.
- **Befunde:**
  - **Control-Flow/Fehler/Signale:** Breite `except Exception`-Blöcke (Z. 92–105, 120–140, 165–181) sind robust gegenüber HTML-/Netzänderungen, verdecken aber die Fehlerursache. `fetch_text` schläft auch nach dem letzten Fehlversuch (Z. 90–105). Eine unerwartete Exception aus `ex.map` (Z. 257–264) kann den Gesamtlauf abbrechen. Ein Ctrl-C-/SIGTERM-Handling fehlt; der ThreadPool kann das Ende verzögern. Cache-Schreiben (Z. 132–140) ist nicht atomar.
  - **Quoting/Pfade:** URLs sind fest vorgegeben (Z. 37–40, 143–165). `curl` wird als Argumentliste und damit ohne Shell-Interpolation aufgerufen (Z. 70–78), quoting-seitig positiv. Cache-/Key-Pfade hängen von `$HOME` ab. Cache-Daten werden ohne Signatur-/Strukturvalidierung übernommen; `free_names` verwendet eine positionsabhängige HTML-Array-Annahme (Z. 184–198).
  - **Ports/Lifecycle:** Keine Listener-Ports. Das Skript startet bei Ausführung externe HTTP-/Curl-Prozesse mit Timeout (Z. 70–84); im Audit wurde keiner gestartet. Index/Free-Status werden trotz Cache bei jedem Lauf live geladen (Z. 237–245, 264).
  - **Secrets/Doku:** `NVIDIA_API_KEY` und die Key-Datei werden als Bearer-Key an die NVIDIA-API gesendet (Z. 208–219), ohne Ausgabe des Keys. Das ist eine bewusste Secret-Verwendung. Die Cache-Doku (Z. 15–16) suggeriert sofortige Folgeläufe, obwohl Index/Free-Status weiterhin abgerufen werden. Die Beispiele nennen `scripts/nvidia-models.py` statt des tatsächlichen B-Pfads `infra/scripts/nvidia-models.py` (Z. 19–23).
- **Risikostufe:** Mittel
- **geprüft:** ja

### 9. `infra/scripts/opencode-server.sh`

- **Zeilenzahl:** 85
- **Zweck:** Zentralen OpenCode-Server auf `127.0.0.1:4096` starten, stoppen, neustarten und per HTTP prüfen.
- **Befunde:**
  - **Control-Flow/Fehler/Signale:** `set -euo pipefail` (Z. 4) bricht bei unbehandelten Fehlern ab. Der Port- und Health-Check (Z. 16–24, 33–43) prüft nicht die Prozessidentität. Ein belegter, aber nicht antwortender Port führt zum Stop-Aufruf (Z. 21–23), der wiederum den globalen `pkill`-Pfad auslösen kann. Der Start wartet nicht auf den eigenen Prozess, sondern nur 20 Sekunden auf den Health-Endpunkt; ein früh verstorbener Prozess hinterlässt eine PID-Datei. `stop` meldet „Gestoppt“ auch dann (Z. 46–64), wenn `pkill` fehlschlägt. Eine Signal-Trap fehlt.
  - **Quoting/Pfade:** `REAL_OPENCODE` und das Arbeitsverzeichnis sind auf `/home/vscode/.opencode/bin/opencode-bin` bzw. `/workspaces/MAIN` festgelegt (Z. 26–31). `$0` wird in `start`/`restart` unquoted verwendet (Z. 22, 76, 78), was bei Pfaden mit Leerzeichen fehleranfällig ist. Die PID-Datei wird direkt und nicht atomar geschrieben (Z. 31); ein gleichzeitiger Start kann sie überschreiben.
  - **Ports/Lifecycle:** Port 4096 ist auf Localhost begrenzt (Z. 6–8), aber jeder 2xx-Dienst auf diesem Port gilt als OpenCode. `pkill -f "opencode-bin serve"` (Z. 62) ist global und kann Server in anderen Workspaces/Konten beenden. `nohup`/`disown` schützen nicht vollständig vor Prozessgruppen-Kills; ein `setsid`-Start fehlt. Beim Stoppen wird weder cwd noch Executable des PID-Inhabers validiert, daher ist PID-Reuse gefährlich.
  - **Secrets/Doku:** Keine Secret-Referenzen. Die Soll-Beschreibung eines zentralen Multi-Client-Servers passt zum Alias, widerspricht aber dem in `glm2api.sh` dokumentierten Anspruch eines pfad-/PID-gesicherten, nicht-globalen Stopps.
- **Risikostufe:** Hoch
- **geprüft:** ja

### 10. `infra/scripts/opencode-wrapper.sh`

- **Zeilenzahl:** 31
- **Zweck:** OpenCode-Aufrufe direkt ausführen oder an den laufenden Server auf Port 4096 attachen; bei Bedarf den Server starten.
- **Befunde:**
  - **Control-Flow/Fehler/Signale:** `set -u` (Z. 5), aber kein `set -e`; Startfehler werden absichtlich verschluckt (Z. 22–28), danach wird der lokale Fallback gewählt. `exec` (Z. 13, 19, 26, 31) reicht Signale an den endgültigen Prozess weiter und ist lifecycle-seitig positiv. Fehlende `curl`- oder Binärabhängigkeiten werden nicht diagnostiziert; ein Fehler kann als „Server nicht aktiv“ erscheinen.
  - **Quoting/Pfade:** `REAL_OPENCODE`, Server-Skript und URL sind auf `/home/vscode` bzw. `/workspaces/MAIN` und Port 4096 festgelegt (Z. 7–8, 23–25). Die Pass-through-Liste (Z. 11–14) ist manuell gepflegt; neue CLI-Unterbefehle werden unerwartet als TUI/Attach behandelt. Die Argumentliste wird ansonsten korrekt mit `"$@"` weitergereicht.
  - **Ports/Lifecycle:** Die HTTP-Prüfung (Z. 18, 25) akzeptiert jeden erreichbaren Dienst auf Port 4096, nicht nach OpenCode-Identität. Der Wrapper kann als Nebenwirkung den Server starten; bei belegtem Port wird die globale Stop-Logik des Server-Skripts ausgelöst. Es gibt keine Signal-Trap, aber `exec` vermeidet einen zusätzlichen Wrapper-Prozess.
  - **Secrets/Doku:** Keine Secret-Referenzen. Die Wrapper-Doku ist mit `opencode-server.sh` konsistent; die nichtparametrisierbaren `/workspaces/MAIN`- und `/home/vscode`-Pfade bleiben eine Portabilitätsabweichung.
- **Risikostufe:** Mittel
- **geprüft:** ja

### 11. `infra/scripts/ports.sh`

- **Zeilenzahl:** 36
- **Zweck:** Lauschende TCP-Ports mit Labels sowie von GitHub Codespaces weitergeleitete Ports anzeigen.
- **Befunde:**
  - **Control-Flow/Fehler/Signale:** `set -uo pipefail` (Z. 3) ist absichtlich nicht fatal. Fehler von `ss`/`awk`/`sort` im Process-Substitution-Block (Z. 17–23) werden nicht zuverlässig in den Hauptstatus übernommen; bei fehlendem `ss` kann die Anzeige fälschlich „keine“ Ports melden. `gh`-Fehler und JSON-Fehler werden still verworfen (Z. 27–35), sodass nicht ermittelbar und nicht authentifiziert nicht unterscheidbar sind.
  - **Quoting/Pfade:** `label "$1"` (Z. 20) erhält nur dann ein Argument, wenn die while-Schleife korrekt Addressen liefert. IPv6-Adressen werden per `${addr##*:}` auf den Port reduziert; das ist brauchbar, aber nicht robust gegen ungewöhnliche `ss`-Ausgabeformate. Der Python-One-Liner (Z. 28) nutzt korrektes JSON-Parsing, wählt aber immer das erste Codespace-Element statt des aktuellen Codespaces/Repos.
  - **Ports/Lifecycle:** Die Ausgabe zeigt lokale Listener, prüft aber nicht deren Bind-Adresse; die Labels „localhost-only“ (Z. 9–10) sind daher nicht verifiziert. Das Skript startet selbst keine Prozesse. `gh codespace ports` ist ein externer, authentifizierungs-/netzwerkabhängiger Aufruf (Z. 30), hier nicht ausgeführt.
  - **Secrets/Doku:** Keine Secret-Werte; `gh` kann implizit Auth verwenden, die nicht ausgegeben wird. Die Doku nennt Port 9222 als Chromium-CDP (Z. 9), obwohl die B-Dokumentation Chromium/CDP als entfernt/deprecated beschreibt; Port 8787 wirkt ebenfalls wie ein nicht mehr im aktuellen Soll dokumentierter Proxy. Die statischen Infrastrukturangaben nennen 6082/5920, 4096, 8001 und 9878, die das Skript korrekt labels, aber nicht den Bind-Schutz.
- **Risikostufe:** Mittel
- **geprüft:** ja

### 12. `infra/scripts/quota.sh`

- **Zeilenzahl:** 161
- **Zweck:** Antigravity-Quoten live abfragen, primär 5h-/Wochenlimiten, mit Fallback auf flache Modelldaten; lokale OpenCode-Token aggregieren.
- **Befunde:**
  - **Control-Flow/Fehler/Signale:** `set -euo pipefail` (Z. 3) bricht bei fehlenden Programmen/JSON-Fehlern ab. Beide Curl-Aufrufe (Z. 16–29) haben kein `--fail`, keine Statuscodeprüfung, keinen Timeout und keine Retry-Logik; `|| true` verwandelt Netzwerkfehler in leere Antworten. Der komplexe Python-Block (Z. 37–161) fängt nur lokale Datenbankfehler ab; ungültige Response-Strukturen, nichtnumerische Quoten oder fehlende Datenbankfelder können den Prozess mit Traceback abbrechen. Der SQLite-Verbindungsfluss wird nicht explizit geschlossen (Z. 138–158).
  - **Quoting/Pfade:** Der Token wird per `jq` gelesen (Z. 12), aber nicht auf nichtleer/valide geprüft. `TOKEN` wird in den Curl-Argumenten als Authorization-Header übergeben (Z. 16–20, 24–28); damit kann er über Prozesslisten sichtbar werden. `CREDS_FILE` ist auf einen festen `$HOME`-Ablageort bezogen (Z. 5). Das Python-Skript wird per Here-String korrekt und ohne Shell-Interpolation mit Daten versorgt (Z. 37–161).
  - **Ports/Lifecycle:** Keine lokalen Listener-Ports. Zwei externe HTTPS-Endpunkte sind fest codiert (Z. 16, 24); die HTTP-Anfragen können unbegrenzt laufen. Der lokale SQLite-Zugriff öffnet die DB nicht explizit im Read-only-URI-Modus (Z. 135–140), führt aber nur SELECTs aus. Es gibt keinen Signal-Handler; Ctrl-C beendet nur den laufenden Python-Block.
  - **Secrets/Doku:** `CREDS_FILE` enthält den Antigravity-OAuth-Secretstore; der Token wird nicht direkt printed, aber als Curl-Argument offengelegt. Bei ungültiger Antwort wird die gesamte Response ausgegeben (Z. 31–34), was serverabhängige sensible Diagnosedaten enthalten kann. Die Doku beschreibt Primärendpunkt und Fallback korrekt; die Fallback-Modellnamen (Z. 110–113) und die harte `/home/vscode`-DB-Annahme (Z. 135) sind jedoch veraltungs-/portabilitätsanfällig.
- **Risikostufe:** Hoch
- **geprüft:** ja

### 13. `infra/scripts/rclone-install.sh`

- **Zeilenzahl:** 31
- **Zweck:** Gepinntes rclone-Binary v1.75.1 aus dem offiziellen Download in `/usr/local/bin` installieren.
- **Befunde:**
  - **Control-Flow/Fehler/Signale:** `set -euo pipefail` (Z. 7) bricht bei den meisten Fehlern ab. `curl` (Z. 23) hat Retry, aber keinen Connect-/Gesamt-Timeout und kann bei hängendem Server blockieren. Kein Trap räumt das temporäre Verzeichnis nach einem Fehler auf. `unzip -o` (Z. 24) kann ein vorhandenes Extraktionsverzeichnis wiederverwenden; die finale Bereinigung erfolgt nur im Erfolgsfall (Z. 28). Die bestehende Versionsprüfung mit `head`/`grep` (Z. 13) ist unter `pipefail` potenziell von einem SIGPIPE-/Kurzoutput-Effekt abhängig.
  - **Quoting/Pfade:** `target` ist fest `/usr/local/bin/rclone`, `tmp_dir` fest unter `/tmp/opencode` (Z. 10–11). Download-Archiv und Linux-`amd64`-Pfad sind hart codiert (Z. 19–26); andere Architekturen werden nicht erkannt. `sudo cp`/`sudo chmod` (Z. 26–27) setzen privilegierte Installation und mögliche sudo-Prompts voraus. Es gibt keine SHA-256-/Signaturprüfung des ZIPs und keine Inhalts-/Pfadvalidierung vor `sudo cp`.
  - **Ports/Lifecycle:** Keine Ports und kein Langzeitprozess. Der Installer startet nur Curl/Unzip/Sudo-Kommandos; alle wurden im Audit nicht gestartet. Ein Signal während `sudo cp` kann eine unvollständige Binary-Datei hinterlassen.
  - **Secrets/Doku:** Keine Secret-Referenzen. Version, Zielpfad und Zweck entsprechen der B-Dokumentation; „kanonisch/einziger Weg“ (Z. 5–6) ist durch die fehlende Integritätsprüfung und den nicht portablen amd64-Pfad nicht vollständig abgesichert.
- **Risikostufe:** Hoch
- **geprüft:** ja

### 14. `infra/scripts/save.sh`

- **Zeilenzahl:** 61
- **Zweck:** Repository-Änderungen optional committen, Rebase/pull ausführen und nach `origin/main` pushen; Status- und Push-only-Modi sowie Google-Drive-Backup-Hook.
- **Befunde:**
  - **Control-Flow/Fehler/Signale:** `set -uo pipefail` (Z. 6) ist nicht fatal. `cd` (Z. 7) wird nicht explizit geprüft, obwohl `set -e` hier zwar greifen würde, die Fehlermeldung aber nicht Kontext liefert. Commit-, Pull- und Push-Fehler werden an mehreren Stellen ignoriert oder in `if`-Bedingungen versteckt (Z. 43–57). Ein fehlgeschlagener Rebase wird mit `|| true` übergangen (Z. 50), danach wird trotzdem gepusht. Der Backup-Hook maskiert jeden Fehler (Z. 57). Keine Signal-Trap schützt Commit-/Rebase-Zwischenstände.
  - **Quoting/Pfade:** `MSG="${*:-...}"` (Z. 21) verwendet implizites `$*` und kann Argumente/Leerzeichen unkontrolliert zusammenziehen; die Commitnachricht wird zwar gequoted, die Semantik ist aber nicht robust. `slug` wird per Sed aus dem Remote abgeleitet (Z. 29); unbekannte oder nicht-GitHub-Remotes können einen unbrauchbaren Push-URL-String ergeben. `git add -A` (Z. 42) staged bewusst alle Änderungen, einschließlich möglicherweise unerwarteter Dateien. `cd` verwendet den Skriptpfad, aber der Erfolg wird nicht explizit verifiziert.
  - **Ports/Lifecycle:** Keine Listener-Ports. Das Skript startet bei Erfolg den externen rclone-Backupprozess (Z. 57), hier nicht ausgeführt. Es pusht immer `main` (Z. 31, 35, 50), unabhängig vom aktuellen Branch; Status setzt `origin/main` voraus (Z. 15). `GIT_TERMINAL_PROMPT=0` (Z. 8) verhindert interaktive Auth-Prompts, ist aber kein Ersatz für Fehlerdiagnose.
  - **Secrets/Doku:** Der PAT wird aus der Datei gelesen und in `GH_TOKEN`/`GITHUB_TOKEN` exportiert (Z. 23–27); der Fallback-Push schreibt ihn außerdem direkt in die URL (Z. 33–36), wodurch er in Prozesslisten sichtbar werden kann. Die Befunde/comments zu add/commit/pull/push und Backup-Hook entsprechen dem Soll, aber die fehlende Auth-/Rebase-Fehlerbehandlung und der Drive-Fehler werden nicht an den Aufrufer propagiert.
- **Risikostufe:** Hoch
- **geprüft:** ja

### 15. `infra/scripts/secrets.sh`

- **Zeilenzahl:** 129
- **Zweck:** PATs, API-Keys, OAuth-Credentials, rclone-Konfiguration, `.env` und OpenCode-Auth in einem AES-256-CBC/PBKDF2-Bundle sichern, Manifest schreiben und beim Unlock in lokale Secret-Pfade kopieren.
- **Befunde:**
  - **Control-Flow/Fehler/Signale:** `set -euo pipefail` (Z. 21) und ein `EXIT`-Trap (Z. 41, 70) fangen Temp-Bereinigung ab. `cmd_lock` schreibt Bundle und Manifest jedoch direkt und nicht atomar (Z. 56–57); ein Abbruch kann ein altes Bundle durch ein unvollständiges ersetzen. `cmd_unlock` verschluckt nur den OpenSSL-Fehler (Z. 71–75), nicht nachfolgende Tar-/Copy-Fehler. `get_passphrase` (Z. 26–37) nutzt eine Export-Variable als Passphrase-Schnittstelle; ein nicht exportierter Shell-Wert würde trotz Returncode 0 nicht an `openssl -pass env:` gelangen. Es gibt keine explizite Signalbehandlung außer dem EXIT-Trap.
  - **Quoting/Pfade:** `cd` zu Repo-Root (Z. 22) ist einfach, aber nicht per `BASH_SOURCE` gegen Symlink-/Umgebungsannahmen abgesichert. Secret-Dateien werden über feste `$HOME`-Pfade und `.env` im Repo gelesen (Z. 44–52). Die Datei enthält eine explizite Legacy-Fallback-Referenz `.secrets/chatglm-refresh-token` (Z. 49), obwohl die aktuelle Doku `.secrets` als aufgelöst beschreibt; der Fallback ist damit Kompatibilitäts- und Pfadrisiko. `tar` und `cp` sind gut gequotet, aber Archivinhalt/Dateiliste wird vor Extraktion nicht gegen eine Allowlist geprüft.
  - **Ports/Lifecycle:** Keine Ports. `openssl`, `tar`, `cp` und `auth.sh` sind kurzlebige externe Prozesse; `auth.sh setup` kann seinerseits `gh`/Git aufrufen (Z. 80). Das Skript gestartet hier keinen Prozess. Der EXIT-Trap schützt nicht vor `SIGKILL` oder abruptem Container-Termin.
  - **Secrets/Doku:** Passphrase, PAT und diverse Credential-Pfade werden verarbeitet, aber nicht als Inhalte ausgegeben. `openssl enc -aes-256-cbc -pbkdf2` bietet Verschlüsselung, aber keine authentifizierte Verschlüsselung/Integritätsprüfung (Z. 56, 71); CBC-Padding allein erkennt Manipulation nicht zuverlässig. Die Doku nennt `config/passphrase` absichtlich im Repo (Z. 8–12), widerspricht aber der einleitenden Aussage, das Bundle sei ohne Passphrase nutzlos, weil dieselbe Passphrase im Repo liegt. Der Unlock ruft `auth.sh` mit dem PAT als Argument auf (Z. 80), sodass der Secret-Wert in der Prozessliste sichtbar werden kann.
- **Risikostufe:** Hoch
- **geprüft:** ja

### 16. `infra/scripts/watch-subagent.py`

- **Zeilenzahl:** 78
- **Zweck:** OpenCode-SQLite-Datenbank read-only öffnen und neue Parts eines Subagenten (Toolstatus, Textantworten, Schritte) live auf dem Terminal anzeigen.
- **Befunde:**
  - **Control-Flow/Fehler/Signale:** `KeyboardInterrupt` wird abgefangen (Z. 73–74), aber SQLite-Fehler, fehlende DB, Schemaänderungen und kaputte Part-Daten außerhalb des JSON-Fehlerblocks nicht. Die Endlosschleife (Z. 35–72) beendet nur bei Ctrl-C; ein SIGTERM-/SIGHUP-Handler fehlt. `seen_parts` (Z. 32, 42–45) verarbeitet jede Part-ID nur einmal. Dadurch werden spätere Statusänderungen derselben Tool-Part (z. B. running→completed/error) nicht erneut angezeigt. Das Skript behauptet „neuesten/aktiven“ Subagenten, filtert aber nicht nach Aktivität (Z. 17–27).
  - **Quoting/Pfade:** `DB_PATH` ist auf `/home/vscode/.local/share/opencode/opencode.db` festgelegt (Z. 8), nicht auf `$HOME`; auf anderen Benutzern/Umgebungen schlägt der Read-only-Connect fehl. Session-IDs werden als SQL-Parameter korrekt gebunden (Z. 37–40), wodurch SQL-Injection vermieden wird. Eingabe- und Fehlerwerte werden nur durch Längenbegrenzung geschützt, nicht redigiert (Z. 56–63).
  - **Ports/Lifecycle:** Keine Ports und kein Netzwerk. SQLite wird mit `mode=ro` geöffnet (Z. 14), was Schreibschutz korrekt erzwingt; die Verbindung wird nicht explizit geschlossen. Polling alle 1,5 Sekunden (Z. 72) und wiederholtes Laden aller Parts (Z. 37–41) skaliert schlecht bei großen Sessions.
  - **Secrets/Doku:** Es gibt keine direkte Secret-Datei, aber Tool-Inputs, Fehlertexte und Antwortzeilen können API-Keys, Tokens, Dateiinhalte oder Prompt-Secrets enthalten und werden auf stdout ausgegeben (Z. 52–68). Das ist ein erhebliches Terminal-/Log-Leak-Risiko. Das Skript ist in der B-Dokumentation nicht als eigener Watcher beschrieben; seine Zweckbeschreibung ist daher undokumentiert.
- **Risikostufe:** Hoch
- **geprüft:** ja

### 17. `infra/docs/RESTORE.md`

- **Zeilenzahl:** 113
- **Zweck:** Manuelle Wiederherstellung des Git-Repositories aus Google-Drive-Bundles, anschließende neue GitHub-Authentifizierung und vollständiges Setup.
- **Befunde:**
  - **Control-Flow/Fehler/Signale:** Die Schritte sind rein dokumentarisch und nicht als failsafe Skript ausgeführt. `git clone` (Z. 41) wird vor dem destruktiven Ersetzen nicht durch `git bundle verify` abgesichert. `rm -rf MAIN.old` (Z. 42) löscht vorhandene Sicherung ohne Rückfrage; `mv MAIN MAIN.old` und `mv MAIN-restored MAIN` (Z. 43–44) können bei unerwartetem Dateisystemzustand einen unvollständigen Zustand erzeugen. Es gibt keinen Check, ob `MAIN-restored` ein erwartetes Git-Repository mit dem richtigen Remote ist.
  - **Quoting/Pfade:** Alle Pfade sind auf `/workspaces` bzw. `/workspaces/MAIN` festgelegt (Z. 20–21, 40–45, 84). Der Remote-Befehl enthält in Z. 47 ein unsichtbares Zero-Width-Zeichen in `https://github.com`; der kopierbare Befehl ist dadurch wahrscheinlich ungültig. Platzhalter wie `<NEUER-ACCOUNT>` und `<NEUER-PAT>` werden unquoted dokumentiert (Z. 47, 58); nach Ersetzung können Sonderzeichen in Account-/Tokenwerten quoting- oder URL-Probleme verursachen. `gdrive restore` nutzt den im B-Skript definierten Default-Pfad, der mit dem Dokument konsistent ist.
  - **Ports/Lifecycle:** Das Dokument nennt keine eigenen lokalen Listener-Ports, verweist aber auf noVNC/6082, VNC/5920 und den Restore-Alias (Z. 74–79, 94–99). `gdrive restore` startet externe rclone-/Git-Prozesse, hier nicht ausgeführt. Für den Download via Browser wird kein Integritäts- oder Prüfbefehl gezeigt.
  - **Secrets/Doku:** Der neue PAT wird als Kommandozeilenargument (Z. 58) und nicht über die im Skript vorgesehene unsichtbare Abfrage empfohlen; damit drohen Shell-History/Prozesslisten-Leaks. Die Aussage, eine RESTORE-Kopie liege immer neben den Bundles (Z. 4–5, 7–13), ist zu stark: `gdrive-backup.sh` versucht das Kopieren erst nach erfolgreichem Bundle-Upload (dort Z. 87–90) und meldet Fehler nur als Hinweis. Die MD5-/Bundle-Integritätszusage (Z. 108–109) ist wegen der oben festgestellten Remote-Hash-Lücke nicht garantiert. `.env`/Browserprofil/.runtime werden korrekt als nicht im Git-Bundle enthalten beschrieben (Z. 103–107).
- **Risikostufe:** Hoch
- **geprüft:** ja

### 18. `infra/docs/reverse-engineering/capture.py`

- **Zeilenzahl:** 84
- **Zweck:** CDP-Netzwerk-Capture für ChatGLM-POST-Requests; schreibt Request-URL, Body und Zeitstempel als JSONL.
- **Befunde:**
  - **Control-Flow/Fehler/Signale:** Das Skript ist Top-Level-Code ohne `if __name__ == "__main__"`-Guard; ein Import führt sofort Netzwerk-/Socket-Operationen aus. `urllib.request.urlopen` (Z. 9) hat keinen Timeout. Wenn keine passende Seite gefunden wird, bleibt `WS_URL` `None` (Z. 7–12) und der anschließende Aufruf verursacht einen Folgefehler. Die WebSocket-Handshake-Antwort wird einmal mit `recv(4096)` gelesen (Z. 27–29); Frame-Reste werden verworfen. Es gibt keine Signal-/`finally`-Behandlung, kein Socket-Close und keine Timeout-Begrenzung.
  - **Quoting/Pfade:** URL/Path werden per einfachem Split und festem Localhost-Port 9222 angenommen (Z. 20–26). Das passt nicht zur aktuellen B-Dokumentation, in der Chromium/CDP 9222 als entfernt/deprecated beschrieben ist. Schreibziel ist außerhalb des Repositories und hart codiert: `/workspaces/reverse-engeneer/reasoning-capture.jsonl` (Z. 64). Das Verzeichnis wird nicht angelegt; die Datei wird im Anhängermodus ohne restriktive Rechte/atomaren Replace geöffnet.
  - **Ports/Lifecycle:** Bind-Ziel ist ausschließlich `127.0.0.1:9222` (Z. 9, 23); es gibt keine Prozessverwaltung. Der CDP-WebSocket-Client behandelt keine Fragmentierung, Kontrollframes, Close-Frames oder maximalen Payload; bei EOF kann `read()` (Z. 43–46) in einer Endlosschleife hängen, weil ein leerer Socket-Receive nicht als Fehler geprüft wird. `assert` (Z. 28) wird unter `python -O` umgangen.
  - **Secrets/Doku:** Alle POST-Bodies von URLs mit `chatglm` werden unredigiert persistiert (Z. 72–84); sie können Prompts, Tokens, Session-Daten oder andere Geheimnisse enthalten. Die Doku nennt den Ablauf als Reverse-Engineering-Methodik, warnt aber nicht vor sensiblen Capture-Dateien oder restriktiven Rechten. Die Datei ist nicht als ausführbares, installierbares Diagnosewerkzeug mit klarer Secret-Policy beschrieben.
- **Risikostufe:** Hoch
- **geprüft:** ja

### 19. `infra/docs/reverse-engineering/cdp.py`

- **Zeilenzahl:** 56
- **Zweck:** Minimale CDP-WebSocket-Steuerung für Navigation, JavaScript-Auswertung und Screenshots einer ChatGLM-Seite.
- **Befunde:**
  - **Control-Flow/Fehler/Signale:** `connect()` (Z. 4–14) und `CDP.send()` (Z. 18–32) haben keine Socket-Timeouts. `send()` wartet unbegrenzt auf die passende Antwort; CDP-Serverfehler, Connection-Close und Protokollfehler werden nicht systematisch in verständliche Fehler übersetzt. `Runtime.evaluate` und `Page.captureScreenshot` prüfen den Erfolg nicht ausreichend (Z. 49–55). Fehlende CLI-Argumente erzeugen `IndexError` (Z. 45, 48), und ein unerwartetes Ergebnis kann `KeyError`/`TypeError` auslösen. `assert` (Z. 12) ist unter Optimized Python nicht belastbar. Kein `finally` schließt das Socket.
  - **Quoting/Pfade:** `sys.argv[2]` wird direkt als URL/Expression verwendet (Z. 45, 48); die Shell entscheidet über Quoting, Python nicht. Das Modul selbst verwendet keine unsicheren String-Interpolationen in SQL/Systemkommandos. Screenshot-Ausgabe ist auf `/workspaces/reverse-engeneer/screen.png` festgelegt (Z. 55), ohne Verzeichnisprüfung, atomaren Write oder restriktive Rechte.
  - **Ports/Lifecycle:** Die Verbindung ist auf `127.0.0.1:9222` festgelegt (Z. 5, 8, 11); dies entspricht nicht dem aktuellen Firefox-/VNC-Soll. `CDP._read` (Z. 33–39) erkennt EOF, aber keine Frame-Fragmentierung, Kontroll-/Close-Frames oder serverseitige Fehlerereignisse. `Page.enable` wird ohne Auswertung aufgerufen (Z. 45, 54).
  - **Secrets/Doku:** `eval` kann beliebigen Seiten-JavaScript ausführen und dessen Rückgabewert bis 4000 Zeichen ausgeben (Z. 47–52); `navigate` kann beliebige URLs öffnen. Beides kann sensible DOM-/Cookie-/Token-Daten preisgeben. Screenshots können sichtbare Logins/Tokens enthalten und werden ungeschützt gespeichert (Z. 53–56). Die Doku beschreibt die Werkzeuge, aber nicht die notwendige Secret-/Dateirechte-Policy.
- **Risikostufe:** Hoch
- **geprüft:** ja

### 20. `infra/docs/reverse-engineering/chatglm-reasoning-modes.md`

- **Zeilenzahl:** 54
- **Zweck:** Historische Reverse-Engineering-Dokumentation der ChatGLM-Web-UI-Reasoning-Modi und der damaligen Abbildung auf Proxy-`chat_mode`-Werte.
- **Befunde:**
  - **Control-Flow/Fehler/Signale:** Keine ausführbare Kontrolllogik; die verwendeten Codeblöcke sind Mapping-Tabellen und eine historische Methodikbeschreibung. Die beschriebenen acht Unit-Fälle und Live-Verifikationen (Z. 45–49) sind nicht im B-Ordner als reproduzierbare Tests/Artefakte vorhanden.
  - **Quoting/Pfade:** Die Methodik verweist auf `reverse-engeneer/capture.py` und `reverse-engeneer/cdp.py` (Z. 23–25), obwohl die Dateien im B unter `infra/docs/reverse-engineering/` liegen. Die genannte `reasoning-capture.jsonl` (Z. 53) wird von `capture.py` außerhalb des Repositories und unter `/workspaces/reverse-engeneer` geschrieben; der Pfad ist nicht als verlässlicher Doku-Vertrag beschrieben. CDP `127.0.0.1:9222` (Z. 20–23) widerspricht dem aktuellen Soll, das Chromium/CDP als entfernt bzw. veraltet beschreibt.
  - **Ports/Lifecycle:** Port 9222 ist als historische Methodik dokumentiert, nicht als aktuell unterstützter Betriebsport. Es werden keine Prozesse gestartet oder überwacht. Die genannten UI-Selektoren und CDP-Abläufe haben keine Fehler-/Timeout-/Retry-Spezifikation.
  - **Secrets/Doku:** Die Zuordnung `high|max|unknown → deep_thinking` und `-think → deep_thinking` (Z. 37–40) widerspricht der aktuellen Changelog-Angabe, dass `deep_thinking` entfernt und `max` auf `thinking` abgebildet wurde; die OpenCode-Varianten `low`, `medium`, `high`, `max` (Z. 43) widersprechen ebenfalls dem aktuellen Soll, das nur `max` als glm-Variante nennt. Auch die Aussage zur Playwright-Chromium-Runtime (Z. 22) ist veraltet. Diese Doku ist als historische, nicht als kanonische Betriebsanweisung zu kennzeichnen; sonst kann sie falsche Proxy- und Modellannahmen verbreiten.
- **Risikostufe:** Hoch
- **geprüft:** ja

## Abschließende Querverweise

- **Vollständigkeit:** Jede der 20 Textdateien besitzt einen eigenen Eintrag mit Zeilenzahl, Zweck, Befunden, Risikostufe und `geprüft: ja`.
- **Syntaxergebnis:** Shell- und Python-Prüfungen waren erfolgreich; die Befunde sind statische Robustheits-, Lifecycle-, Secret- und Konsistenzrisiken und wurden nicht durch Live-Ausführung verifiziert.
- **Keine Geheimnisse:** Der Bericht enthält keine Secret-Werte. Die Erwähnung von `config/passphrase`, Token-, Key- und Credential-Pfaden beschreibt nur Referenzen.
<!-- END PART B -->

## Anhang C — MCP-Sitzungsverwaltung

<!-- BEGIN PART C -->
## Revision-Audit — Partition C: `infra/mcp/`

**Audit-Datum:** 2026-09-24
**Scope:** ausschließlich `/workspaces/MAIN/infra/mcp/`; ergänzend nur die für die Registrierungs- und Aufrufgrenze benötigten, ausdrücklich benannten Querverweise in `.opencode/opencode.json`, `.devcontainer/setup.sh` und `.opencode/agent/glm2api.md`.
**Methode:** vollständiges Zeilenlesen aller Textdateien im Scope, statische Datenfluss-/SQL-/Fehleranalyse, Git-Inventar und rein statische Syntax-/Versionsprüfungen.
**Nicht ausgeführt:** kein MCP-Serverstart, keine SQLite-Datei geöffnet, keine Query ausgeführt, keine Löschung, kein `VACUUM`, keine Testdatenbank und keine Änderung an `Revision.md`.

## 1. Vollständiges Dateiinventar

| Datei | Zeilen | Git-Modus | Inhalt | Ergebnis |
|---|---:|---:|---|---|
| `infra/mcp/README.md` | 61 | `100644` | Betriebs-, Tool-, Schutz-, Lösch- und Integrationsdoku | vollständig gelesen |
| `infra/mcp/opencode-sessions-mcp.js` | 565 | `100755` | CommonJS-MCP-Server, SQL-Helfer, Session-Erkennung, sechs Tools, stdio-JSON-RPC | vollständig gelesen |

Weitere Dateien, Unterverzeichnisse, versteckte Dateien, Symlinks oder Binärdateien wurden im Scope nicht gefunden. Insbesondere existieren **keine**:

- `package.json` oder Lockdatei,
- eigene Config-/Schema-Datei,
- TypeScript-/TSX- oder Testdatei,
- `test/`, `tests/` oder `__tests__/`,
- npm-Test-, Lint- oder Typecheck-Skripte,
- fixture-/Snapshot-Tests.

Damit existiert im Partition-Scope keine automatisierte Testabdeckung. „Zero Dependencies“ bedeutet hier nur: keine npm-Laufzeitabhängigkeit; SQLite bleibt eine externe Systembinärdatei.

## 2. Gesamturteil

Der Server ist klein, direkt verständlich und syntaktisch gültig, greift aber ausschließlich per direktem SQLite-Zugriff auf die laufende opencode-Datenbank. Die wichtigsten Schutzversprechen der Doku sind mit dem Code **nicht belastbar garantiert**: Die aktuelle und aktiven Sessions werden lediglich über Verzeichnis-/Zeit-Heuristiken geschätzt, Schutzabfragen scheitern still, Zielauswahl und Löschung laufen in getrennten SQLite-Verbindungen, und Fehler nach oder innerhalb der Löschung können einen bereits teilweise committeten Zustand hinterlassen.

**Gesamtbewertung: hohes Datenverlust- und Integritätsrisiko bei destruktiver Nutzung.** Im normalen Einzelbenutzer-/Einzelsession-Fall funktionieren die offensichtlichen Schutzpfade, aber die Implementierung ist weder nebenläufigkeitssicher noch schema- oder protokollrobust.

## 3. Architektur und Datenfluss

### 3.1 Start- und Trust-Grenzen

1. Opencode startet laut Querverweis `.opencode/opencode.json:286-295` den absoluten Pfad `/workspaces/MAIN/infra/mcp/opencode-sessions-mcp.js` als lokalen stdio-Prozess.
2. Der Server liest `OPENCODE_DB` oder verwendet den Defaultpfad `opencode-sessions-mcp.js:29-38`.
3. Jeder SQL-Aufruf startet einen neuen `sqlite3`-Prozess (`opencode-sessions-mcp.js:53-84`); es gibt keine langlebige Node-SQLite-Verbindung.
4. MCP-Parameter werden als JSON-Text über stdio angenommen (`opencode-sessions-mcp.js:498-527,529-565`).
5. Lese-Tools liefern normalisierte Metadaten. `delete_sessions` schreibt direkt in die DB, bereinigt Orphans und startet `VACUUM` (`opencode-sessions-mcp.js:211-302`).
6. Der Prozess besitzt keine eigene Authentifizierung oder Autorisierung. Die Vertrauensgrenze ist der lokale Prozessstart durch den MCP-Host.

### 3.2 Externe Abhängigkeiten

- Node.js `>=18` laut `README.md:8-9`; statisch vorgefunden: Node `v18.19.1`.
- `sqlite3`-CLI laut `README.md:8-9`; statisch vorgefunden: SQLite `3.45.1`.
- POSIX-Dateisystem und `/proc` für den aktiven Session-Schutz (`opencode-sessions-mcp.js:97-129`).
- Das DB-Schema und die opencode-Prozessumgebung werden nicht versioniert, validiert oder abgefragt.
- Die Datei verwendet CommonJS (`require`), aber es gibt keine `package.json`, die Node-Modulemodus oder Skripte festlegt.

## 4. Befunde nach Schweregrad

### C-H01 — Aktuelle und aktive Sessions sind nicht zuverlässig identifizierbar; Schutz kann ausfallen

**Zeilen:** `opencode-sessions-mcp.js:97-169,223-240,304-320`; Doku-Versprechen `README.md:24-29`, Kopfkommentar `opencode-sessions-mcp.js:9-14`.

- `activeOpencodePids()` erkennt jeden `/proc`-Prozess, dessen gesamte Kommandozeile die Zeichenkette `opencode` enthält (`97-113`). Das erfasst auch den MCP-Server selbst, Hilfsprozesse oder beliebige Prozesse mit diesem Teilstring.
- `OPENCODE_PID` wird nur syntaktisch als Zahl geprüft, nicht gegen PID-Ursprung, Prozessexe oder Lebenszeit verifiziert (`110-112`).
- `activeSessions()` ordnet jedem Prozess nur sein `cwd` zu (`116-130`). `startedAt` wird berechnet, aber nie für eine Zuordnung verwendet.
- `guessActiveSessionIds()` nimmt pro Verzeichnis ausschließlich die neueste Session und schützt diese für alle Prozesse mit diesem cwd (`136-151`).
- `callerSessionId()` versucht ebenfalls „neueste Session im cwd“ statt einer tatsächlichen Request-/Client-Session-Bindung (`154-169`).
- Mehrere gleichzeitige Sessions im selben Arbeitsverzeichnis können daher nur als eine geschützt werden. Eine neu angelegte, aber nicht aktive Session kann durch ihr Aktualisierungsdatum Schutz „gewinnen“, während die echte aktuelle Session ungeschützt bleibt.
- cwd-/Pfadkanonisierung, symbolische Links und Slash-Varianten werden nicht normalisiert.
- Session-Erkennung ist faktisch Linux-/proc-spezifisch; auf anderen Systemen fällt sie auf `process.cwd()` zurück.
- Alle drei Erkennungspfade fangen SQL-/Dateisystemfehler still und liefern ein leeres Ergebnis (`107-109,121-126,147,161,167`). Der Löschpfad interpretiert „nicht erkannt“ als „nicht geschützt“.
- Auch die Share-Abfrage fällt bei jedem Fehler still auf „keine Shares“ zurück (`231-239,315-320`), statt destruktiv fail-closed zu arbeiten.

**Auswirkung:** Die Aussagen „aktuelle Session wird nie gelöscht“ und „aktive Sessions sind geschützt“ sind nicht garantiert. Im ungünstigsten Fall schützt die Heuristik die falsche Session und lässt die aktuelle Session löschbar.

### C-H02 — Schutzprüfung, Zielauswahl und Löschung sind nicht atomar

**Zeilen:** `opencode-sessions-mcp.js:223-278,304-330`.

Ablauf der destruktiven Operation:

1. aktive IDs in eigener SQLite-Verbindung bestimmen,
2. aktuelle Session in weiterer Verbindung bestimmen,
3. Shares in weiterer Verbindung bestimmen,
4. Zielmenge in weiterer Verbindung bestimmen,
5. erst danach `BEGIN` und Löschungen starten.

Zwischen Schritt 4 und 5 können andere opencode-Prozesse:

- eine Session starten oder deren `time_updated` verändern,
- neue Messages/Parts in eine bereits ausgewählte Session schreiben,
- Shares anlegen oder entfernen,
- Sessions löschen oder neu anlegen.

Die Transaktion prüft keine Schutz-IDs, Ziel-IDs, Zeitstempel oder Sessionversionen erneut. Abhängig vom Lockzeitpunkt können neue Inhalte einer inzwischen aktiven Zielsession noch von den `DELETE ... WHERE session_id IN (...)`-Anweisungen erfasst werden; nach dem ersten Write-Lock neu entstehende Inhalte können jedoch verwaiste Zeilen hinterlassen. Es gibt weder eine optimistische Versionsbedingung noch eine Sperre über die Vorprüfung.

**Auswirkung:** TOCTOU-Rennen zwischen Preview/Schutzermittlung und Löschung. Der MCP-Server kennt keine opencode-Sitzungssperren oder App-Level-Invarianten und umgeht die opencode-API vollständig.

### C-H03 — Fehler können einen bereits teilweise committeten Löschzustand hinterlassen

**Zeilen:** `opencode-sessions-mcp.js:56-84,261-301`.

- Der mehrteilige SQL-Text wird an `sqlite3` ohne `-bail` übergeben (`265-278`). Im Fehlerfall gibt es keinen expliziten Rollback und dennoch ein am Textende stehendes `COMMIT`. Je nach sqlite3-Fehlerfortsetzung können vorher erfolgreiche Deletes trotz eines späteren Tabellen-/Constraint-Fehlers committet werden.
- Die Session-Transaktion wird vor der Orphan-Bereinigung committet. Die beiden Orphan-Deletes laufen danach als separate autokommittierte Statements (`283-292`).
- `VACUUM` ist wiederum ein eigener Schritt (`293`). Fehler bei Orphan-Count, Orphan-Delete oder `VACUUM` werden nach bereits erfolgter Session-Löschung als Gesamtfehler gemeldet.
- Es gibt keine Nachprüfung mit `changes()`, Existenzabfrage oder Transaktionsstatus. `deleted: victims.length` (`295-301`) ist die beabsichtigte Zielanzahl, kein verifizierter Commit-Umfang.
- Ein Retry derselben breiten Filteranfrage kann weitere inzwischen vorhandene, ungeschützte Sessions löschen, nachdem der erste Aufruf bereits Daten entfernt, aber wegen `VACUUM` oder Cleanup kein Ergebnis geliefert hat.
- Temporärer Speicherbedarf, exklusive Sperren oder ein `SQLITE_BUSY` während `VACUUM` führen zu teilweisem Erfolg ohne strukturierten Teilerfolg.

**Auswirkung:** Der Client kann bei einer Fehlermeldung nicht erkennen, ob die Session-Transaktion bereits wirksam war. Das verletzt die erwartete All-or-nothing-Semantik.

### C-H04 — Breite destruktive Aufrufe und ungültige Zahlen sind nicht ausreichend begrenzt

**Zeilen:** `opencode-sessions-mcp.js:211-256,304-330,424-466`; Doku `README.md:35-44,56-61`.

- `{ "confirm": true }` ohne Filter ist gültig und erzeugt alle nicht geschützten Sessions als Zielmenge.
- Ein leeres `delete_ids`-Array gilt wie „nicht angegeben“ und fällt auf Filter bzw. auf „alle Sessions“ zurück (`243-255`).
- `older_than_days` wird ungeprüft mit `Number()` multipliziert (`250-253,325-328`). Negative Werte können alle Sessions erfassen; `NaN`/`Infinity` führen zu SQL-Fehlern; sehr große endliche Werte können ebenfalls praktisch alle erfassen.
- `delete_ids`, `keep_ids` und Such-/Listenlimits haben keine harte Mengenbegrenzung.
- `Math.min(Number(args.limit) || 100, 500)` garantiert nur ein numerisches Maximum, kein Minimum (`191,391`). Negative Limits werden von SQLite als „unbegrenzt“ interpretiert; `-1` umgeht damit das dokumentierte Maximum.
- `confirm=true` ist nur ein vom Modell/MCP-Client gesetztes Boolean. Es ist weder an einen Preview-Plan noch an eine Zielanzahl, Nutzeridentität oder Challenge gebunden.
- Preview ist nicht verpflichtend und wird nicht serverseitig erzwungen (`opencode-sessions-mcp.js:211-215`).
- `delete_preview` akzeptiert kein `delete_ids` (`304-343,438-450`), obwohl `README.md:35-44` dieselben Parameter für Preview und Delete dokumentiert. Ein expliziter ID-Löschaufruf kann daher nicht exakt durch das entsprechende Preview geprüft werden.
- Preview zeigt maximal 100 Victims, Delete nur die ersten 50 (`295-301,333-342`), ohne Trunkierungsflag.
- Unbekannte explizite `delete_ids` werden still ignoriert; es gibt keine Missing-ID-Liste.

**Auswirkung:** Ein syntaktisch gültiger, leicht unbeabsichtigter Aufruf kann sehr große Mengen betreffen, und Preview/Delete können unterschiedliche Zielmengen haben.

### C-H05 — Datenbankschema, Fremdschlüssel und Kaskaden werden nur angenommen

**Zeilen:** `opencode-sessions-mcp.js:89-93,143,185-190,233,245-293,317,349-355,383-391,404-407`.

Angenommen werden unter anderem:

- Tabelle `project` und Spalten `id`, `worktree`,
- `session.id`, `project_id`, `title`, `directory`, `agent`, `model`, `parent_id`, `cost`, Token-Spalten, Zeitfelder, `share_url`,
- `message.id`, `session_id`, `time_created`, `data`,
- `part.message_id`, `part.data`,
- `session_share.session_id`,
- `todo.session_id`,
- `event.aggregate_id`,
- `event_sequence.aggregate_id`,
- zusätzliche Session-Linker-Tabellen mit `session_id`.

Es gibt:

- keine Schema-/Migrationsversion,
- keinen Vergleich mit `PRAGMA user_version`,
- keine Prüfung auf erforderliche Tabellen oder Spalten,
- kein `PRAGMA foreign_keys=ON`,
- kein `PRAGMA busy_timeout`,
- keine Berücksichtigung von Triggern oder zusätzlichen Fremdschlüsseln.

`ensureDb()` prüft nur `fs.existsSync(DB)`, nicht Dateityp, Lesbarkeit, SQLite-Integrität oder Race-to-Swap (`89-93`).

Die explizite Löschreihenfolge löscht `message`, bevor `session_message` und weitere möglicherweise auf Messages bezogene Tabellen bereinigt werden (`267-273`). Ohne aktivierte Fremdschlüssel können Referenzintegrität still umgangen werden; mit aktivierten Fremdschlüsseln kann genau diese Reihenfolge fehlschlagen. `session.parent_id` wird ausgelesen (`360`), aber Kind-/Elternbeziehungen werden bei Löschung weder validiert noch kaskadiert. Eine Kind-Session kann also auf einen gelöschten Eltern-Datensatz verweisen, oder ein Löschvorgang kann an einer nicht berücksichtigten Relation scheitern.

**Auswirkung:** Schema-Drift kann zu SQL-Fehlern, partiellen Löschungen, verwaisten Datensätzen oder blockierten Löschungen führen. Die manuelle Löschliste ist kein Ersatz für foreign keys mit geprüfter ON DELETE-Semantik.

### C-M01 — Orphan-Bereinigung verwendet einen zu breiten LIKE-Prädikatsausdruck

**Zeilen:** `opencode-sessions-mcp.js:281-292`.

- `LIKE 'ses_%'` bedeutet wegen des nicht maskierten `_` nicht „Literal `ses_`“, sondern „`ses` + ein beliebiges Zeichen + beliebiger Rest“.
- Die Bereinigung läuft global über alle passenden Events, nicht nur über die aktuell gelöschten Victims.
- Andere Aggregate-Typen, deren ID zufällig dem Muster entspricht und nicht in `session` existiert, können gelöscht werden.
- Es wird angenommen, dass relevante Session-Events ausschließlich eine `ses_...`-ID als `aggregate_id` besitzen. Andere Event-Aggregate bleiben gegebenenfalls als Orphans zurück.
- `orphan_events_removed` summiert Events und Event-Sequences, wird aber ausschließlich als „Events“ bezeichnet (`300`).
- Zwei Count-/Delete-Phasen sind nicht atomar und können sich zwischen Count und Delete ändern.

### C-M02 — `VACUUM` ist unabhängig vom Löschergebnis immer blockierend

**Zeilen:** `opencode-sessions-mcp.js:293`; Doku `README.md:17,31-33,58-61`.

`VACUUM` läuft auch bei null Victims. Es benötigt eine exklusive Datenbanksperre und zusätzlichen temporären Speicher, kann bei aktivem opencode blockieren oder fehlschlagen und wird nicht innerhalb der Session-Transaktion ausgeführt. Ein Fehler kann nach erfolgreicher Löschung auftreten. Der Node-MCP-Prozess ist während des synchronen `spawnSync` vollständig blockiert.

### C-M03 — MCP-Argumente werden nicht entsprechend den Schemas validiert

**Zeilen:** `opencode-sessions-mcp.js:41-55,175-191,211-255,304-330,377-391,424-495,505-521`.

- Die veröffentlichten JSON Schemas sind Dokumentation, keine serverseitige Validierung.
- Arrays, Booleans, Zahlen, Strings und unbekannte Properties werden nicht erzwungen.
- `keep_ids`/`delete_ids` als String führen zu Iterations- oder `.map`-Fehlern bzw. Schutz einzelner Zeichen statt erwarteter Semantik.
- `lit()` serialisiert `NaN` und `Infinity` als nicht quotierte SQL-Tokens (`41-46`) und kann damit SQL-Fehler oder undefiniertes Verhalten in Vergleichsausdrücken verursachen.
- `bind()` prüft keine Placeholder-Anzahl (`48-55`). Fehlende Parameter werden still zu `NULL`; überzählige Parameter werden ignoriert. Ein späterer Schema-/Refactor-Fehler kann so still zu einer anderen Query-Menge führen.
- Suchlimits akzeptieren negative Werte; `older_than_days` ist unbeschränkt.
- LIKE maskiert `%` und `_`, aber nicht den Escape-Zeichen-Backslash selbst (`377-391`), sodass exakte Suchmuster mit Backslash semantisch falsch sein können.
- Die MCP-Schemas verbieten keine unbekannten Properties und definieren keine `minimum`, `maximum`, `minItems` oder `maxItems`.
- Der `list_sessions`-INNER-JOIN blendet Sessions ohne passenden Project-Datensatz aus (`185-190`), obwohl die Toolbeschreibung Session-Listung suggeriert.
- Direkte `Date.toISOString()`-Aufrufe können bei fehlenden/ungültigen Zeitfeldern das gesamte Tool scheitern lassen (`203-205,339,371-372,397`).

### C-M04 — MCP-/JSON-RPC-Grenze ist robustheitsarm

**Zeilen:** `opencode-sessions-mcp.js:498-565`; Debug-Doku `README.md:53-54`.

Positiv: Newline-delimited JSON passt zum üblichen MCP-stdio-Transport; Antworten enthalten `jsonrpc`, `id` und `result`; Initialisierungsnotifikation wird nicht beantwortet.

Probleme:

- Ungültiges JSON wird ohne Parse-Error still verworfen (`547-550`).
- `jsonrpc: "2.0"`, Batch-Form, Message-Struktur und Request-ID werden nicht validiert.
- `initialize` spiegelt jede Client-Protokollversion ungeprüft (`499-503`) und implementiert keine Versionsauswahl/-Ablehnung.
- Alle Tool-, Argument-, SQL- und Methodenfehler erhalten denselben Code `-32000`; Tool-Ausführungsfehler werden nicht als `CallToolResult` mit `isError` modelliert (`552-563`).
- Fehlerhafte JSON-Argument-Strings werden still zu `{}` (`508-511`); das kann bei Lese-Tools zu unbeabsichtigten Defaults führen.
- Tool- und Methodendispatch verwenden normale Objekte. Prototyp-Eigenschaften wie `constructor` oder `toString` sind dadurch nicht zuverlässig „unbekannte Namen“ (`512-520,552-555`).
- `notifications/cancelled` wird ignoriert. Da die Toolimplementierung synchron ist, kann eine lange Query weder abgebrochen noch währenddessen bearbeitet werden.
- `spawnSync` blockiert den kompletten MCP-Eventsystem-Loop; ein 120-Sekunden-Limit je SQLite-Aufruf ist kein Gesamt-Timeout.
- Der stdin-Puffer hat keine Größenbegrenzung (`529-540`).
- `process.exit(0)` beim stdin-Ende kann noch nicht vollständig geleerte stdout-Puffer abschneiden (`541`).
- Es gibt keine Logs, Trace-ID oder Telemetrie; Fehlerdiagnose erfolgt ausschließlich über generische JSON-RPC-Nachrichten.
- Die direkte CLI-Grenze besteht nur aus `node <script>` und stdin. Es gibt keinen CLI-Argumentparser, kein `--help`, kein `--version`, kein read-only-Modus und kein von Haus aus blockierter Destruktionsmodus.

### C-M05 — Vertraulichkeit und Prozessgrenze

**Zeilen:** `opencode-sessions-mcp.js:29-35,56-63,345-374,402-417,498-565`.

- `OPENCODE_DB` darf auf jede existierende SQLite-Datei zeigen. Es gibt keine Pfad-Allowlist, Auflösung auf den erwarteten Datenordner oder Symlink-/TOCTOU-Schutz.
- SQLite wird mit normalem Dateizugriff gestartet, nicht explizit read-only für Leseoperationen.
- `sqlite3` wird über `PATH` aufgelöst und erbt die gesamte MCP-Prozessumgebung. Ein kompromittiertes gleichnamiges Binary oder ein unsicherer PATH erhält damit auch alle geerbten Umgebungsvariablen.
- `session_info` gibt `share_url` vollständig zurück (`345-374`). Share-URLs können Zugriffsfähigkeiten sein und sollten als vertraulich behandelt werden. Im Audit wurde kein konkreter Wert ausgegeben.
- Titel, Verzeichnisse, Session-IDs, Suchtreffer, Kosten und Tokenwerte werden ausgegeben. Die Volltextsuche gibt zwar Inhalte nicht zurück, bestätigt aber deren Existenz.
- Fehler können DB-Pfad, SQLite-Schema- oder Locking-Informationen an den MCP-Client weiterreichen.
- Der Server hat keine eigene Authentifizierung; jeder lokale Prozess, der ihn starten und `confirm=true` senden kann, erhält dieselben Rechte wie der Host.
- Im globalen Opencode-Config steht `permission: allow` direkt neben dem aktivierten MCP (`Querverweis .opencode/opencode.json:284-295`). Der glm2api-Subagent sperrt Preview/Delete ausdrücklich (`.opencode/agent/glm2api.md:5-7`), dies ist aber keine MCP-Servergrenze und gilt nicht für andere Clients.

### C-M06 — Aktive-Prozess-Zähler und Session-Klassifikation sind irreführend

**Zeilen:** `opencode-sessions-mcp.js:97-151,402-417`.

- PIDs werden in einem Array statt Set gespeichert; dieselbe PID kann doppelt vorkommen.
- Jeder Prozess mit `opencode` im cmdline zählt, einschließlich typischerweise des MCP-Servers selbst.
- `active` bedeutet nur „neueste Session im cwd dieses Prozesses“, nicht nachweislich eine gerade laufende Session.
- `active_opencode_processes` (`414`) zählt erkannte cmdline-Treffer, nicht deduplizierte echte Opencode-Serverprozesse.

### C-M07 — Registrierungs- und Dokumentationsdrift

**Zeilen:** `README.md:3-9,24-29,35-54`; Querverweise `.opencode/opencode.json:286-295`, `.devcontainer/setup.sh:94-120`.

- `README.md:4` nennt `~/.local/share/opencode/opencode/opencode.db` mit einem zusätzlichen `opencode/`-Pfadsegment. Code (`opencode-sessions-mcp.js:32-35`) und Setup-Kommentar verwenden `~/.local/share/opencode/opencode.db`.
- Das Doku-Versprechen „aktuelle Session nie gelöscht“ ist stärker als die heuristische Implementierung.
- `README.md:35-44` nennt `delete_ids` für Preview und Delete, obwohl Preview weder Schema noch Implementierung dafür besitzt.
- `README.md:50-52` behauptet idempotente Pfad-Anpassung. Setup ergänzt einen Eintrag nur, wenn die Zeichenkette `opencode-sessions` fehlt (`.devcontainer/setup.sh:104-115`). Ein bereits vorhandener Eintrag mit veraltetem absolutem Pfad wird nicht korrigiert. Die aktuelle `.opencode/opencode.json:289-292`-Registrierung ist fest auf `/workspaces/MAIN` verdrahtet.
- `README.md:53` funktioniert nur, wenn der aktuelle cwd `/workspaces/MAIN/infra` ist; aus dem Repo-Root wäre der direkte Pfad `infra/mcp/opencode-sessions-mcp.js`.
- `README.md:8` nennt nur `child_process` als Built-in, obwohl der Code zusätzlich `fs`, `os` und `path` verwendet. Das ist nur eine unpräzise Beschreibung, keine zusätzliche npm-Abhängigkeit.
- `README.md:60-61` nennt eine historische DB-Verkleinerung als typisches Ergebnis; ein `VACUUM` kann aus Disk-, Lock- oder Fehlergründen ausbleiben.

### C-L01 — Ungenutzte Werte und Nebenwirkungen

**Zeilen:** `opencode-sessions-mcp.js:116-130,217,230-239,345-355`.

- `startedAt` wird berechnet, aber nie genutzt.
- `keepShared` in Zeile 217 wird berechnet, aber nicht verwendet; die Schutzlogik prüft stattdessen `args.keep_shared` erneut.
- `first` und `last` in `toolSessionInfo` (`353-354`) werden nicht in das Ergebnis aufgenommen. `last` liest unnötig das komplette `message.data` aus der DB, obwohl es nicht ausgegeben wird.
- Der Kommentar in Zeile 217 ist widersprüchlich und beschreibt eine Entscheidung, die der Code korrekt an anderer Stelle trifft.

## 5. Datenbank- und SQL-Inventar

| Zeilen | Operation | Zweck / Risiko |
|---|---|---|
| `143-146` | `SELECT` alle Sessions | aktive Sessions je cwd erraten; vollständiger Scan |
| `159-160` | `SELECT` neueste cwd-Session | aktuelle Session erraten |
| `165-166` | `SELECT` neueste cwd-Session | Fallback |
| `185-191` | `SELECT` Session+Project+Message-Count | Listen-Tool; INNER JOIN, Limit |
| `233-234` | `SELECT` alle Shares | Schutz; Fehler wird als leere Menge interpretiert |
| `245-246` | `SELECT` explizite IDs | Delete-Zielmenge |
| `255-256` | `SELECT` gefilterte Sessions | potenziell alle Sessions |
| `265-278` | `BEGIN` + zehn `DELETE` + `COMMIT` | Kernlöschung, keine Runtime-PRAGMAs |
| `283-284` | `SELECT count` Orphans | getrennte Snapshots |
| `286-287` | `DELETE` Event-Orphans | global, autocommittiert |
| `290-291` | `DELETE` Sequence-Orphans | global, autocommittiert |
| `293` | `VACUUM` | immer, separat, blockierend |
| `317-318` | `SELECT` alle Shares | Preview-Schutz, Fehler fail-open |
| `330-331` | `SELECT` gefilterte Sessions | Preview, potenziell alle |
| `349-350` | `SELECT * FROM session` | unbekanntes Schema vollständig gelesen, whitelisted ausgegeben |
| `352` | Message-Anzahl | read-only |
| `353-354` | erste/letzte Message | Ergebnis wird nicht verwendet; unnötiger Full-Data-Read |
| `355` | Todo-Anzahl | read-only |
| `383-391` | `LIKE`-Volltextsuche über `part.data` | potenziell teurer Scan; nur Metadaten zurück |
| `404-407` | vier Zählqueries | nicht konsistenter Snapshot |

### 5.1 SQL-Injektion und Parameterbindung

- Werte werden in SQL-Stringliterale mit verdoppelten einfachen Anführungszeichen escaped (`40-46,86-87`). Für die tatsächlich dynamischen Session-IDs und Verzeichnisse wurde kein direkter SQL-Injection-Pfad erkannt.
- Das ist dennoch kein natives Binding. Semantik hängt von `bind()`-Reihenfolge, identischer Placeholder-Anzahl und SQL-Typbehandlung ab.
- Tabellen- und Spaltennamen stammen ausschließlich aus statischem Quelltext.
- `LIKE`-Muster werden über denselben Mechanismus eingesetzt; der Backslash-Escape ist unvollständig.
- Fehlende Typprüfung bei `Number()` erzeugt bare Tokens für `NaN`/`Infinity`; das ist primär ein Verfügbarkeits- und Fehlerfall, kein direkt belegter Inject-Pfad.

## 6. Löschkaskade und Integrität

### 6.1 Vorhandene explizite Reihenfolge

1. Parts aller Messages der Victims (`267`),
2. Messages der Victims (`268`),
3. `session_message` (`269`),
4. `session_input` (`270`),
5. `session_context_epoch` (`271`),
6. `session_share` (`272`),
7. `todo` (`273`),
8. `event` (`274`),
9. `event_sequence` (`275`),
10. Session (`276`).

### 6.2 Annahmen und Lücken

- Alle genannten Tabellen müssen in jeder unterstützten opencode-Version existieren und die erwarteten Spalten besitzen.
- Kind-/Elternrelationen aus `parent_id` werden nicht berücksichtigt.
- Weitere zukünftige session-bezogene Tabellen werden nicht gelöscht.
- Foreign Keys werden nicht explizit aktiviert; Trigger-/Cascade-Verhalten wird nicht geprüft.
- Message-Linker werden nach Message gelöscht, was bei aktivierter FK immediate nicht zur bewiesenen Reihenfolge passt.
- Event-Bereinigung ist nicht auf die gelöschten IDs begrenzt und verwendet ein zu breites LIKE-Muster.
- Nach Bestehen der Transaktion gibt es keine Foreign-Key-Prüfung, `PRAGMA foreign_key_check`, Integritätsprüfung oder Mengenabgleich.
- Das Löschen von `session_share` erfolgt auch bei `keep_shared=true`, sofern die Session selbst Victim ist. Das ist plausibel, aber die Doku unterscheidet nicht zwischen Share-Datensatz und Schutzstatus der Session.
- `delete_ids` überschreibt Verzeichnis-/Altersfilter wie dokumentiert; unbekannte IDs bleiben ohne Rückmeldung.

## 7. Locking, Nebenläufigkeit und Atomizität

- Jeder `sql()`-/`sqlRun()`-Aufruf ist ein eigener CLI-Prozess und damit eine eigene SQLite-Verbindung (`53-84`).
- Alle Selects laufen als unabhängige Autocommit-Snapshots.
- Die einzige explizite Transaktion beginnt erst nach Target-Bestimmung (`265-278`).
- Es wird weder `BEGIN IMMEDIATE` noch eine separate Application-/Datei-Lock verwendet.
- Es fehlt ein explizites Busy-Timeout oder Retry. `timeout: 120000` betrifft nur den Kindprozess, nicht ein sqlite-busy-Wait.
- Ziel- und Schutz-Snapshots werden nicht in derselben Transaktion validiert.
- Orphan-Deletes und `VACUUM` sind außerhalb der Transaktion.
- Zwei parallele MCP-Prozesse können dieselbe Zielmenge berechnen, dieselbe Cleanup-/VACUUM-Phase auslösen und dennoch `deleted: victims.length` melden, obwohl eine andere Verbindung Sessions bereits entfernt hat.
- Die App weiß nicht von direkten SQLite-Manipulationen und kann abgeleitete Caches, Dateien oder Session-Locks nicht koordinieren.

## 8. Session-Schutz und Lösch-Sicherheit

### Vorhandene Schutzmechanismen

- harte `confirm === true`-Prüfung (`213-215`),
- aktuelle Session heuristisch geschützt (`227-228`),
- aktive Sessions standardmäßig heuristisch geschützt (`216,224-226`),
- Shares standardmäßig geschützt (`230-239`),
- `keep_ids` standardmäßig geschützt (`240`),
- aktuelle Session bleibt auch bei `keep_active=false` geschützt,
- unbekannte/explizite Delete-IDs werden über maskierte Literale in eine IN-Liste gesetzt.

### Nicht vorhandene Garantien

- keine robuste Caller-Session-ID aus MCP-Kontext,
- keine Busy-/Lock-Prüfung der betroffenen Session,
- kein Schutz vor Sessions, die zwischen Prüfung und Commit starten,
- kein fail-closed-Verhalten bei Erkennungsfehlern,
- kein Schutz mehrerer Sessions pro cwd,
- kein Plan-/Preview-Token,
- kein Mindestalter oder Mindestzielanzahl,
- kein Audit-Log außerhalb der gelöschten Session-Daten,
- kein serverseitiges Verbot paralleler Löschaufrufe,
- keine Postcondition-Prüfung.

Die Schutzwirkung im vorgesehenen Einzelbenutzerbetrieb ist plausibel, aber sie ist eine Heuristik und keine datenbankbasierte Sicherheitsmatrix.

## 9. Tool- und MCP-Grenzen

| Tool | Grenze / Standard | Wichtigste Risiken |
|---|---|---|
| `list_sessions` | read-only, max. behauptet 500 | negativer LIMIT umgeht Cap; INNER JOIN; falsche active/current Flags |
| `delete_preview` | read-only, aber nicht atomar an Delete gebunden | gleiche fail-open Erkennung; kein `delete_ids`; kein Plan-Token |
| `delete_sessions` | destruktiv, `confirm=true` | direkter DB-Write, Race, Teilcommit, Schemaannahmen, globales VACUUM |
| `session_info` | read-only Metadaten | vollständige `share_url`; unnötiger Message-Data-Read |
| `search_sessions` | read-only, max. behauptet 100 | negativer LIMIT; vollständiger LIKE-Scan; Backslash-Escape; nur Treffer-Metadaten |
| `db_stats` | read-only | vier inkonsistente Counts; falsche Prozesszählung; pre-`VACUUM`-Größe |

Die Toolnamen werden vom Opencode-Host mit dem MCP-Namespace `opencode-sessions_*` versehen. Im MCP-Prozess selbst sind die Namen unpräfixt; es gibt keine zweite Autorisierungsgrenze.

## 10. Fehler- und Abbruchfälle

| Fall | Aktuelles Verhalten | Risiko |
|---|---|---|
| DB fehlt | klarer Fehler aus `ensureDb` | kein Fallback |
| DB-Dateipfad ist kein SQLite/ist korrupt | SQL-/JSON-/SQLite-Fehler | Schema und Partials unklar |
| `sqlite3` fehlt | expliziter Fehler | MCP-Request endet |
| SQLite gesperrt/Busy | Timeout- oder SQLite-Fehler | keine Retry-/Rollback-Semantik |
| Tabelle/Spalte fehlt | einzelner Query kann scheitern | bei mehrteiligem Batch partieller Commit möglich |
| Message-Zeit unbrauchbar | Query läuft; `first`/`last` werden ignoriert | kein direkter Folgefehler |
| Session-Zeit ungültig | `toISOString()` wirft | gesamtes Tool schlägt fehl |
| JSON-RPC-Zeile ungültig | still verworfen | Client wartet möglicherweise |
| unbekannte Methode/Tool | `-32000` | keine standardisierte Fehlerklassifikation |
| ungültige Argument-JSON | `{}` | unbeabsichtigte Defaults bei Reads |
| Transaktionsfehler vor Abschluss | Gesamtfehler | vorherige Writes können dennoch persistiert sein |
| Orphan-/VACUUM-Fehler | Gesamtfehler | Session-Löschung bereits committet |
| stdin endet | `process.exit(0)` | möglicher stdout-Truncation |
| Output > 64 MiB | Spawn-/Buffer-Fehler | große Listen/Queries nicht robust |
| Cancellation | ignoriert | lange destruktive Operation läuft weiter |
| falsche Session-Erkennung | kein Fehler | potentiell aktuelle Session löschbar |

Es gibt weder Retry noch Idempotency-Key noch Result-Token. Wiederholungen eines fehlgeschlagenen Aufrufs sind deshalb nicht sicher.

## 11. CLI-Grenze

Der Server ist primär ein MCP-stdio-Server, keine CLI-Anwendung. Der einzige dokumentierte direkte Aufruf startet Node und wartet auf JSON-RPC-Zeilen (`README.md:53-54`). Nicht vorhanden sind:

- Subcommands für Preview/Delete,
- bestätigende CLI-Flags,
- Ausgabe- und Fehlercodes für Shell-Nutzung,
- ein expliziter read-only Startmodus,
- Lock-/Preflight-Ausgabe,
- eine Sicherheitsbarriere gegen direkte `delete_sessions`-Aufrufe.

Der MCP-Host und eine direkt gestartete Node-Instanz teilen sich damit dieselbe vollständige Schreib-API; es gibt keine kryptografische oder prozessbasierte Trennung.

## 12. Dokumentations-Audit `README.md`

| Zeilen | Aussage | Bewertung |
|---|---|---|
| `1-9` | Zweck, DB, Zero Dependencies | Zweck korrekt; DB-Pfad in Zeile 4 falsch; „Zero Dependencies“ nur npmbezogen |
| `11-20` | sechs Tools | Tool-Oberfläche stimmt mit Implementierung überein |
| `22-29` | Schutzmechanismen | Absicht korrekt dokumentiert, aber „nie“/garantierter Schutz zu stark |
| `31-33` | Kaskade | Tabellen grob korrekt; FK-/Parent-/Schema-Lücken nicht erwähnt |
| `35-44` | Preview/Delete-Parameter | `delete_ids` für Preview falsch; keine Validierungs-/Atomizitätsgrenzen |
| `46-54` | Integration, Debug, `OPENCODE_DB` | Setup-Pfadanpassung nicht zuverlässig idempotent; Debugpfad relativ zum cwd mehrdeutig |
| `56-61` | Preview→Delete→VACUUM | Workflow nicht erzwungen; Preview und Delete nicht atomar; VACUUM nicht garantiert |

## 13. Implementierungs-Audit `opencode-sessions-mcp.js` — vollständige Zeilenabdeckung

| Zeilen | Inhalt | Auditresultat |
|---|---|---|
| `1-16` | Shebang, Sicherheitsversprechen | CommonJS/stdio korrekt; Schutzversprechen überzeichnet |
| `18-23` | Imports, Version | Built-ins ausreichend; interne Version ohne Paketmanifest |
| `29-38` | DB-Auswahl | Defaultpfad plausibel; Override ohne Allowlist; README-Drift |
| `40-55` | Literal-/Placeholder-Bindung | Quotes grundsätzlich sicher; keine Typ-/Arity-Prüfung |
| `56-75` | read-only SQL-Helfer | Separate Prozesse, 64-MiB-/120-s-Grenzen; JSON-Fallback kann Rohdaten liefern |
| `77-93` | mutativer Helfer, DB-Check | Kein Rollback-Helfer; Existenzprüfung unvollständig |
| `95-114` | PID-Erkennung | cmdline-Substring, env PID, Duplikate, proc-Abhängigkeit |
| `116-130` | Prozesscwd/Startzeit | cwd-Heuristik; `startedAt` ungenutzt |
| `132-152` | aktive Session-Schätzung | eine neueste Session pro cwd; Fehler fail-open |
| `154-169` | Caller-Schätzung | keine echte Request-Session-Bindung; Fehler fail-open |
| `171-174` | Abschnittsmarke | keine Logik |
| `175-209` | List-Tool | read-only; Join-/Limit-/Zeit-/Flag-Risiken |
| `211-302` | Delete-Tool | höchstes Risiko; Schutz, Targets, Batch, Cleanup, VACUUM, Response |
| `304-343` | Preview-Tool | Schutz-/Fail-open-/ID-/Mengenlücken |
| `345-375` | Session-Info | Share-URL-Vertraulichkeit; ungenutzte First/Last-Abfragen |
| `377-400` | Suche | LIKE-/Escape-/Scan-/Metadatengrenzen |
| `402-418` | DB-Stats | inkonsistente Snapshots; Prozesszählung ungenau |
| `420-423` | Abschnittsmarke | keine Logik |
| `424-496` | Tool-Schemata | sechs Tools vollständig; Schemas validieren nicht und lassen Parameterbereiche aus |
| `498-527` | JSON-RPC-Methoden | Initialize/Tool-Dispatch/Errors; keine Versionsvalidierung/Schema-Checks |
| `529-540` | stdin-Framing | Newline-Transport; unbegrenzter Puffer; parse errors still |
| `541-545` | Ende/stdout | sofortiger Exit kann Ausgabe abschneiden; korrektes Newline-Framing |
| `547-565` | Message-Dispatch | keine JSON-RPC-Strukturvalidierung, generischer Fehlercode, Cancellation wirkungslos |

## 14. Test-, Qualitäts- und Sicherheitslücken

Es gibt keine Tests. Besonders ungeprüft sind:

- korrektes Escaping und alle SQL-Typen,
- Session-/Share-/Parent-Fremdschlüssel und ON DELETE-Verhalten,
- Reihenfolge der manuellen Kaskade,
- Verhalten bei fehlenden Tabellen/Spalten,
- Rollback nach Fehlern mitten im SQL-Batch,
- Verhalten bei Busy/Timeout,
- Schutz mehrerer Sessions im selben cwd,
- `OPENCODE_PID` fehlt/ist falsch/zeigt auf beendeten Prozess,
- Symlink-/DB-Race,
- Preview/Delete-Drift,
- leere und negative Filter,
- `delete_ids`-Duplikate/unbekannte IDs/große Listen,
- MCP-Stringargumente, unbekannte Properties und Protokollversionen,
- Newline-Puffer und stdout-Abbruch,
- Tool-Fehler als MCP-CallToolResult,
- gleichzeitige MCP-Serverprozesse,
- DB-Dateigröße inklusive WAL/SHM,
- Share-URL-Redaktion.

Die README nennt einen funktionierenden Erstlauf, dieser ersetzt aber keine automatisierte Regression für Schema- und Nebenläufigkeitsänderungen.

## 15. Durchgeführte sichere statische Prüfungen

| Prüfung | Ergebnis |
|---|---|
| Verzeichnisinventar über `infra/mcp/**/*` und `infra/mcp/**/.*` | genau die zwei oben genannten Dateien |
| Git-Tracking/Dateimodus | README `100644`, JS `100755` |
| `node --check infra/mcp/opencode-sessions-mcp.js` | bestanden, keine Ausgabe |
| Node-Version | `v18.19.1` |
| SQLite-CLI-Version | `3.45.1` |
| `git diff --check -- infra/mcp` | bestanden, keine Ausgabe |
| scoped `git status` vor Berichtserstellung | keine Änderung in `infra/mcp` |
| DB-/Schemaabfrage | bewusst nicht ausgeführt |
| Laufzeit-MCP-/Tooltests | mangels Tests nicht ausgeführt und ohnehin nicht statisch |

Es wurde keine Datei in `infra/mcp` verändert. Es wurden keine Secrets, Token-, Cookie-, Auth- oder vollständigen Share-Inhalte ausgegeben.

## 16. Priorität der notwendigen Härtung

1. **Session-Schutz:** Eine belastbare Caller-/Session-ID aus dem MCP-/Opencode-Kontext verwenden; pro cwd nicht heuristisch schätzen; Erkennungsfehler bei destruktiven Tools blockierend behandeln.
2. **Atomarer Preflight:** Zielmenge und Schutzstatus in derselben Transaktion unmittelbar vor dem Schreiben neu validieren; keine stale Session-/Share-Snapshots verwenden.
3. **Fehleratomizität:** sqlite-Aufruf mit echtem Bind, kontrolliertem Fehlerabbruch und explizitem Rollback; Teilerfolg nach bereits erfolgten Commits strukturiert melden.
4. **Destruktive Eingaben:** leere Gesamtfilter sperren, Grenzen für Anzahl/Alter/IDs festlegen, Preview-Plan an Zielmenge/Hash binden und serverseitig verpflichtend machen.
5. **Schemavertrag:** benötigte Tabellen/Fremdschlüssel/Parent-Beziehungen explizit validieren; manuelle Kaskade anhand der realen opencode-Migration definieren.
6. **Cleanup:** Orphan-Muster escapen, auf echte Event-Aggregate begrenzen, Zählung und Löschung nachvollziehbar machen; `VACUUM` nur bei Bedarf und mit klarer Fehlersemantik.
7. **MCP-Hardening:** JSON-Schema serverseitig validieren, Größenlimits, korrekte Fehler-/Cancellation-Semantik und sichere Dispatch-Maps.
8. **Vertraulichkeit:** `share_url` redigieren oder nur auf explizite Anforderung/Autorisierung ausgeben; DB-Pfad und Prozessdetails minimieren.
9. **Tests:** eine isolierte temporäre SQLite-Fixture und MCP-stdio-Tests hinzufügen; die konkrete opencode-DB darf von Tests nicht geöffnet oder verändert werden.

## 17. Schlussfolgerung

Die Implementierung erfüllt die dokumentierte Demo-/Alltagsfunktion, ist aber kein ausreichend abgesichertes Verwaltungswerkzeug für eine gleichzeitig laufende opencode-Instanz. Besonders die Kombination aus **heuristischem und fail-open Session-Schutz**, **nicht atomarer Zielauswahl/Löschung**, **angenommenem Schema ohne FK-Prüfung** und **separaten, fehleranfälligen Cleanup-/VACUUM-Schritten** macht den Partitions-Status revisionsreif. Es wurden entsprechend keine Änderungen an Implementierung, `Revision.md` oder Datenbank vorgenommen.
<!-- END PART C -->

## Anhang D — Antigravity-Proxy: Betrieb, Build, Pakete und CI

<!-- BEGIN PART D -->
## Revision D — `llm-proxies/antigravity-proxy`

## 1. Scope und Methode

- Analysierter Bereich: ausschließlich `/workspaces/MAIN/llm-proxies/antigravity-proxy/`.
- Einbezogen: alle Dateien im Wurzelverzeichnis sowie `scripts/`, `.github/`, `npm/` und `.claude/`.
- Ausgeschlossen wie angefordert: `cmd/` und `internal/`; außerdem keine Auswertung von `Revision.md` und keine Parent-Repository-Dateien als Revisionsquelle.
- `Revision.md` war bereits vor diesem Arbeitsgang als unversionierte Datei vorhanden; sie wurde weder gelesen noch geschrieben oder verändert.
- Umfang: 37 Dateien, davon 35 Textdateien mit insgesamt 4.048 Zeilen und 2 Binärdateien.
- Jede Textdatei wurde vollständig zeilenweise gelesen. `auth` und `antigravity-oauth-proxy` wurden als Binärdateien klassifiziert und nicht als Text interpretiert.
- Es wurden keine Installationen, Builds, Starts, Stopps, OAuth-Aktionen, Prozessprüfungen, Portprüfungen oder Netzwerkaktionen ausgeführt.
- Es wurden keine Secrets im Report ausgegeben. Credential-Literale werden nur als Fundstelle und Typ beschrieben.

## 2. Gesamtstatus

**Status: FAIL / nicht release-reif ohne Bereinigung.**

Wesentliche Blocker:

1. Zwei credential-artige Literale liegen in versionierten Shell-Dateien (`scripts/generateContent.sh:5` und `scripts/start.sh:45`). Sie sind unabhängig davon zu rotieren bzw. zu ersetzen, ob sie als Testwerte gedacht waren.
2. Vier OAuth-Skripte verwenden den fremden absoluten Pfad `/workspaces/dvcrn-antigravity-oauth-proxy` statt des analysierten Repositories und sind dadurch nicht reproduzierbar lauffähig (`setup_oauth.sh:6-13`, `setup_oauth_fixed.sh:11-13`, `setup_oauth_full.sh:11-13`, `setup_oauth_final.sh:9-11`).
3. Portannahmen widersprechen sich: 9878 in Start-/Launchagent-/README-Pfaden, 9877 in `AGENTS.md`/`CLAUDE.md`/`GEMINI.md`, 9888 im Testskript (`scripts/generateContent.sh:3`).
4. Prozesssteuerung ist nicht sicher genug: unvalidierte PID-Datei und breite `pkill -f`-Muster können fremde Prozesse beenden (`scripts/stop.sh:8-15`, mehrere OAuth-Skripte).
5. Build-/Release-Reproduzierbarkeit ist nur teilweise gegeben: Go-Abhängigkeiten sind gepinnt, aber GoReleaser ist `latest`, Actions sind nur über bewegliche Tags referenziert, Node-Locks liefern unterschiedliche Wrangler-Bäume, und der npm-Postinstall akzeptiert ein fehlendes/fehlgeschlagenes Checksum.
6. CI prüft weder Worker-/Node-/npm-Pfad noch Shell-Skripte; Release-Workflows laufen ohne Test-Gate und nicht ausreichend geschützt.
7. `wrangler.toml` enthält produktive Cloudflare-Konto-, KV- und Tunnel-Kennungen; die Doku verlangt zwar deren Austausch, die Datei ist aber versioniert. Vollständige, persistente Observability-Logs sind als Default riskant für sensible Proxy-/OAuth-Daten.

## 3. Befunde nach Priorität

### P0 — sofort behandeln

- **Credential-Literal im versionierten Testskript:** `scripts/generateContent.sh:5` enthält einen Bearer-Token als Header-Literal. Der Wert wird nicht aus dem Report wiederholt. Das Skript ist damit ein möglicher Secret-Leak und sollte aus Git-Historie/Verteilung genommen, der Token rotiert und die Datei auf einen Environment-/Secret-Store umgestellt werden.
- **Fester Admin-Schlüssel im Startskript:** `scripts/start.sh:45` setzt `ADMIN_API_KEY` als Literal. Damit ist der lokale Admin-Schlüssel vorhersagbar und im Repository sichtbar. Der Wert wird hier nicht wiederholt; der Schlüssel ist zu rotieren.
- **LaunchAgent legt den Admin-Schlüssel im Klartext ab:** `install-launchagent.sh:60-70` schreibt ihn in die lokale plist. Es gibt weder `umask 077` noch eine Absicherung der Dateirechte. Der Prompt in `install-launchagent.sh:5-9` ist außerdem nicht als Secret-Eingabe (`read -s`) geschützt.

### P1 — hohe Betriebs- und Release-Risiken

- **Falsche Repository-Pfade:** `setup_oauth.sh`, `setup_oauth_fixed.sh`, `setup_oauth_full.sh` und `setup_oauth_final.sh` erwarten Binary und Auth-Helper unter `/workspaces/dvcrn-antigravity-oauth-proxy`; der aktuelle Scope liegt unter `/workspaces/MAIN/llm-proxies/antigravity-proxy`.
- **Breite Prozessbeendigung:** `scripts/stop.sh:15` sowie `setup_oauth.sh:34`, `setup_oauth_full.sh:35` und `setup_oauth_final.sh:34` verwenden unpräzise Muster. `setup_oauth_fixed.sh:35` ist enger, aber weiterhin pfad-/regexbasiert. Es gibt keine Prüfung auf Eigentümer, Executable oder Port.
- **Unzuverlässiger Startzustand:** `scripts/start.sh:14-20` akzeptiert jeden Dienst auf Port 9878, dessen öffentlicher `/v1/models`-Check erfolgreich ist. Ein fremder Dienst mit derselben Antwort wird als Proxy akzeptiert; ein belegter, aber fehlerhafter Port wird anschließend ohne eindeutige Eigentümerdiagnose weiterverarbeitet.
- **Keine Binär-Provenienz:** `scripts/start.sh:39-42` verwendet ein vorhandenes Binary ungeprüft. Ein veraltetes, lokales oder manipuliertes Binary wird nicht anhand von Version, Architektur, Hash oder Quellstand geprüft.
- **Go-Installer ohne Integritätsprüfung:** `scripts/start.sh:26-35` lädt Go 1.25.7 als `linux-amd64` ohne Checksumme/Signatur, nutzt `sudo rm -rf /usr/local/go` und überspringt die Prüfung, wenn irgendein `go` im PATH vorhanden ist. Ein vorhandenes falsches Go wird nicht auf 1.25.7 geprüft.
- **npm-Binary-Install ohne verpflichtende Integrität:** `npm/postinstall.js:142-155` behandelt ein fehlgeschlagenes Checksumme nur als Warnung und extrahiert danach trotzdem. Ein bereits vorhandenes Binary wird in `npm/postinstall.js:119-124` ungeprüft wiederverwendet.
- **CI-/Release-Lücke:** `.github/workflows/release.yml:3-10` reagiert auf jeden Tag und auf manuelle Auslösung, hat `contents: write`, aber keine Testabhängigkeit, keine Umgebungsfreigabe, keine Concurrency-Sperre und keine npm-Veröffentlichung. `.github/workflows/test.yml:25-29` prüft nur Go-Tests und lokalen Go-Build.
- **Bewegliche CI-/Release-Abhängigkeiten:** `actions/checkout@v4`, `actions/setup-go@v5`, `jdx/mise-action@v2` und `goreleaser/goreleaser-action@v6` sind nicht per Commit-SHA fixiert; `ubuntu-latest` ist ebenfalls beweglich. `mise.development.toml:2` setzt GoReleaser auf `latest`.
- **Lockfile-Drift:** Root-`package-lock.json` löst `wrangler` auf 4.97.0 auf, `bun.lock:201` auf 4.24.3. Beide erfüllen den deklarierten Bereich, erzeugen aber unterschiedliche Dependency-Bäume. Eine Paketmanager-Auswahl ist nicht dokumentiert oder erzwungen.
- **Cloudflare-Metadaten und Logging:** `wrangler.toml:4-14` enthält Konto-, KV- und Tunnel-Kennungen. `wrangler.toml:22-26` aktiviert vollständige, persistente Observability. Das kann sensible Request-/OAuth-Daten in Logs sichtbar machen, abhängig von Cloudflare-Log-Inhalt und Runtime.
- **Versionierung nicht gekoppelt:** `npm/package.json:3` steht auf 1.1.1, während Root-`package.json:3` und der Root-Lock `@dvcrn/antigravity-proxy` auf 1.1.0 beziehen. GoReleaser und npm-Veröffentlichung haben keinen gemeinsamen, geprüften Versions-Schritt.

### P2 – Wartbarkeit, Portabilität und Dokumentation

- `AGENTS.md`, `CLAUDE.md` und `GEMINI.md` sind byte-/inhaltsgleiche 104-Zeilen-Duplikate und nennen Port 9877, während die operative Dokumentation 9878 verwendet.
- `README.md:179-183` weist korrekt an, Cloudflare-Konto-, Namespace- und Tunnel-IDs zu ersetzen; die versionierte `wrangler.toml` enthält trotzdem konkrete IDs.
- `README.md:246` behauptet, die geprüfte Workers-Konfiguration aktiviere `DEBUG_SSE`; in `wrangler.toml` ist keine entsprechende Variable sichtbar.
- `ADMIN_API.md:204-208` nennt einen anderen KV-Namespace-Namen als den in `wrangler.toml:9-10` sichtbaren Binding-Namen. Die Beziehung ist nicht eindeutig dokumentiert.
- `README.md:131-135` dokumentiert `/admin/tokens`, `ADMIN_API.md:57-113` primär `/admin/credentials`; `README.md:235` nennt die älteren Endpunkte nur als kompatibel. Die Kompatibilitätsmatrix sollte explizit und vollständig sein.
- `.claude/settings.local.json:4-5` erlaubt nicht vorhandene `just`-Kommandos und erlaubt mit `Bash(sed:*)` sehr breite Shell-Mutationen. `deny` ist leer.
- `mise.toml:38-39` setzt `bunx` voraus, ohne Bun als Tool im Manifest zu pinnen. Root-`package.json` enthält kein `engines`-Feld.
- Root-`package.json` hat keinen Namen, keine Version und keine Scripts; die Abhängigkeit `@dvcrn/antigravity-proxy` wird in den geprüften Betriebsdateien nicht referenziert. Das wirkt wie ein ungeklärter Second-Path zur npm-Verteilung.

## 4. Abhängigkeitsprüfung

### Go

- `go.mod:1-3` definiert Modul `github.com/dvcrn/antigravity-oauth-proxy` und Go 1.25.7.
- `go.mod:5-8` pinnt Go-Formatierungswerkzeuge; `go.mod:10-16` pinnt alle direkten Laufzeit-/Testabhängigkeiten auf exakte Versionen.
- `go.mod:18-37` pinnt auch indirekte Module. Es gibt keine lokalen `replace`-Regeln.
- `go.sum:1-66` enthält Checksummen für die direkten und indirekten Go-Module; kein offensichtlicher fehlender Direkt-Eintrag wurde bei statischer Prüfung festgestellt.
- `mise.toml:2-3` und `scripts/start.sh:26` nennen ebenfalls Go 1.25.7. Das ist konsistent, wird aber im Startskript nicht gegen eine vorhandene Toolchain verifiziert.
- `.github/workflows/test.yml:16-20` bezieht die Go-Version aus `go.mod`; dies ist eine gute Ausgangsbasis, erzwingt aber keine lokale Toolchain-Identität außerhalb des runners.
- `mise.toml:30-35` nutzt für Workers `go run github.com/syumai/workers/cmd/workers-assets-gen` ohne explizites `@version`; die Version kommt indirekt aus `go.mod`. Das ist nur so reproduzierbar, wie Modulauflösung und Cache-Verhalten kontrolliert sind.

### Node/Bun/npm

- Root-`package.json:2-5` deklariert `@dvcrn/antigravity-proxy` mit `^1.1.0` und Wrangler mit `^4.24.3`.
- Root-`package-lock.json:1394-1426` löst Wrangler 4.97.0 auf; der Lockbaum enthält Pakete mit Node `>=22` (`:17-19` und `:1411-1415`).
- `bun.lock:3-9` beschreibt nur Wrangler als Root-Abhängigkeit und pinnt es in `:201` auf 4.24.3. Die im Root-Manifest enthaltene `@dvcrn`-Abhängigkeit fehlt dort.
- `npm/package.json:24-26` und `npm/package-lock.json:18-29` sind untereinander konsistent für `semver` 7.7.4.
- `npm/package.json:15-17` startet bei Installation einen Postinstall-Prozess. `npm/postinstall.js:105-140` lädt ein externes Release-Binary; dies ist eine relevante Supply-Chain- und Offline-Reproduzierbarkeitsannahme.
- `npm/update_check.js:63-96` führt bei interaktiver CLI-Nutzung einen Registry-HTTP-Request aus. CI ist ausgeschaltet (`:14-24`), die Prüfung ist nur ein Hinweis und kein Update-Mechanismus.

## 5. Port-, Auth- und Prozessannahmen

| Bereich | Beobachtung | Status |
|---|---|---|
| Lokaler Proxy | `scripts/start.sh:8-10`, `install-launchagent.sh:60-69` und `README.md:58,71,241-246` nennen 9878; `wrangler.toml` beschreibt dagegen die entfernte Worker-Bereitdeployment ohne lokalen Port. | konsistent innerhalb der lokalen Pfade, aber `AGENTS.md:14-17`, `CLAUDE.md:14-17` und `GEMINI.md:14-17` nennen 9877. |
| Testskript | `scripts/generateContent.sh:3` verwendet 9888. | FAIL, nicht 9878/9877. |
| OAuth-Callback | `README.md:223-229` und `setup_oauth.sh:85-88` nennen 51121. | Dokumentiert; kein Callback-Server-Start ist in `setup_oauth.sh` sichtbar. |
| Healthcheck | `scripts/start.sh:10,14-20,49-52` nutzt den öffentlichen `/v1/models`-Endpunkt. | Authentifizierter Admin-/Credential-Zustand wird nicht geprüft. |
| Admin-Auth | README unterstützt Bearer, X-API-Key und X-Goog-Api-Key; `ADMIN_API.md:46-53` nennt nur Bearer/X-API-Key. | Dokumentationslücke. |
| Prozesskontrolle | `scripts/start.sh:45-47` schreibt eine PID aus einem Hintergrund-Shell-Konstrukt; `scripts/stop.sh:8-15` validiert sie nicht. | FAIL, Race-/Stale-PID-Risiko. |
| Stop-Verhalten | `scripts/stop.sh:15` nutzt globales `pkill -f`; OAuth-Skripte ebenso. | FAIL, kann fremde Prozesse treffen. |
| LaunchAgent | Nur macOS (`launchctl`), kein Linux-Pfad. `install-launchagent.sh:34-49` nutzt `RunAtLoad` und eingeschränktes `KeepAlive`. | Plattformabhängig; sauberes Beenden wird nicht neu gestartet. |
| Credentials | Standardpfad in README und OAuth-Skripten ist `~/.config/antigravity-oauth-proxy/oauth_creds.json`; `run_proxy.sh` lädt keine `.env` oder Credential-Datei selbst. | Nur korrekt, wenn der Prozess die Datei über die Runtime-Defaults findet. |
| Worker-Build | `wrangler.toml:1-3,19-20` verlangt `build/worker.mjs`; `mise.toml:30-35` erzeugt sichtbar `build/app.wasm` und ruft einen Asset-Generator auf. | Ohne Build nicht verifiziert; Output-Pfad ist eine Cross-Reference, die explizit geprüft werden sollte. |

## 6. Secrets-Handling

- **Klartext-Literale:** `scripts/generateContent.sh:5` und `scripts/start.sh:45`; Werte sind absichtlich nicht in diesem Report wiederholt.
- **Prozessumgebung:** Der Admin-Schlüssel wird in `scripts/start.sh:45` und den OAuth-Skripten als Environment gesetzt. Prozessumgebungen sind für berechtigte lokale Benutzer/Prozesse ein sichtbares Secret-Verbreitungsrisiko.
- **LaunchAgent:** `install-launchagent.sh:60-70` persistiert den Schlüssel in XML; kein `chmod 600`/`umask 077`, kein Secret-Store.
- **OAuth-Logs:** Die OAuth-Skripte schreiben nach `/tmp/oauth-setup.log` (`setup_oauth_fixed.sh:62-68`, `setup_oauth_full.sh:62-68`, `setup_oauth_final.sh:54-57`). Abhängig von Helper-Ausgabe können Autorisierungs-URL, Code oder Tokeninformationen dort verbleiben.
- **Beispielwerte:** `ADMIN_API.md:19-22` enthält nur einen als Beispiel markierten Wert. `ADMIN_API.md:120-125` gibt einen frisch generierten Schlüssel jedoch per `echo` aus; das ist keine Geheimniskompromittierung, aber ein unnötiger Terminal-/History-Leak.
- **Ignore-Regeln:** `.gitignore:1` schützt `.env`, aber nicht alle `.env.*`-Varianten oder OAuth-Credential-Dateien. Der Parent-Gitignore schützt den beobachteten PID; der im Target liegende `auth` ist dagegen versioniert.
- **Workers-Logging:** `wrangler.toml:22-26` aktiviert `head_sampling_rate = 1`, Invocation Logs und Persistenz. Das ist bei einem OAuth-/LLM-Proxy nur nach expliziter Prüfung der Log-Felder und Aufbewahrung akzeptabel.
- **NPM-Update-/Downloadpfad:** `npm/postinstall.js:17-39` und `npm/update_check.js:63-96` verwenden externe HTTPS-/Registry-Verbindungen. Das ist keine lokale Secret-Ausgabe, aber ein Trust- und Reproduzierbarkeitsrisiko.

## 7. Build- und Reproduzierbarkeitsprüfung

### Go-/Release-Pfad

Positiv:

- `go.mod`/`go.sum` sind versioniert und enthalten Checksummen.
- `.goreleaser.yml:9-30` setzt `CGO_ENABLED=0`, `-trimpath` und `-buildvcs=false`; das reduziert lokale Build-Metadaten.
- `.goreleaser.yml:32-40` erzeugt Archives und Checksummen; der Asset-Name passt grundsätzlich zu `npm/postinstall.js:105`.

Negativ:

- `.goreleaser.yml:41-45` erlaubt das Ersetzen bestehender Release-Artefakte.
- `mise.development.toml:2` ist nicht reproduzierbar (`goreleaser = "latest"`), und der GitHub-Action ist nicht per SHA fixiert.
- `scripts/start.sh:27-42` nutzt ein eventuell vorhandenes, nicht verifiziertes Go und überspringt den Download; die lokale Binary-Reproduzierbarkeit hängt damit vom Workspace-Zustand ab.
- `antigravity-oauth-proxy` ist ignoriert und nicht versioniert; ein vorgefundenes Binary kann alte oder lokale Quellen repräsentieren.
- `auth` ist dagegen ein großer, versionierter Binärblob. Quellbuild und Repository-Binary können auseinanderlaufen.
- `npm/postinstall.js:142-155` macht die einzige Binärintegritätsprüfung optional; bei fehlendem Checksumme wird weiter installiert.
- Root- und Bun-Locks liefern unterschiedliche Wrangler-Versionen; `bunx` ist als Voraussetzung nicht im Tool-Manifest gepinnt.
- `mise.toml:38-39` verwendet Bun für Wrangler, während CI nur npm-Lock-/Go-Pfade prüft.

### Workers

- `wrangler.toml:19-20` und `mise.toml:30-35` sind grundsätzlich verkettet.
- Der Asset-Generator wird ohne expliziten Versionsparameter aufgerufen; die Auflösung hängt vom Go-Modulgraphen und ggf. vom Netzwerk/Modulcache ab.
- `wrangler.toml:3` pinnt das Compatibility-Date, aber `ENV=production` (`:16-17`) und die Observability-Einstellungen sind nicht als reproduzierbare, minimale Security-Baseline dokumentiert.
- `README.md:179-210` beschreibt VPC/Tunnel/KV-Einrichtung, aber die versionierten IDs sind nicht platzhalterisiert.

## 8. CI-Prüfung

### `.github/workflows/test.yml`

- Gut: Go-Version aus `go.mod`, Setup-Go-Cache, mise und Tests vor dem lokalen Build.
- Lücken: kein `go vet`, kein Formatter-Check, keine Shell-Syntaxprüfung, kein Worker-Build, kein Wrangler-Dry-Run, kein npm-/Bun-Lock-Check, kein npm-Wrapper-Test, kein Secret-/License-/Dependency-Scan.
- Actions und Runner sind bewegliche Versionen; kein `concurrency`, kein explizites `timeout-minutes`, keine Permissions-Minimierung.
- Der Job testet nicht die tatsächlichen Betriebsdateien `scripts/start.sh`, `scripts/stop.sh`, `run_proxy.sh` oder OAuth-Skripte.

### `.github/workflows/release.yml`

- Kein `needs`-Gate auf CI; ein Tag kann GoReleaser ohne vorherigen Test-Job auslösen.
- Jeder Tag (`"*"`) und manuelle Auslösung sind aktiv; `workflow_dispatch` kann ohne nachvollziehbaren Release-Commit laufen.
- `contents: write` ist für GoReleaser nötig, aber zusammen mit `replace_existing_artifacts: true` und fehlender Umgebungsfreigabe zu weit gefächert.
- Keine npm-Publikation, kein Wrapper-Smoke-Test und keine Verknüpfung zwischen `npm/package.json:3`, GoReleaser-Version und Release-Asset.
- Keine Signaturen, Provenance, SBOM, Artefakt-Retention oder Integritätsprüfung im Workflow.

## 9. Datei- und Statusübersicht

Statuslegende:

- **OK:** vollständig gelesen; keine wesentliche Abweichung im geprüften Scope.
- **WARN:** grundsätzlich nutzbar, aber mit Wartungs-, Dokumentations- oder Reproduzierbarkeitsrisiko.
- **FAIL:** konkreter Fehler, Inkonsistenz oder konkretes Secret-/Prozessrisiko.
- **INFO:** Runtime-Artefakt ohne dauerhafte Aussage.
- **BINARY:** nicht zeilenweise als Text lesbar; nur Metadaten/Provenienz geprüft.

| Datei | Status | vollständige Prüfung / Ergebnis |
|---|---|---|
| `.claude/settings.local.json` | WARN | 11/11 Zeilen gelesen. Breites `sed`-Permission, `deny` leer; `just`-Verweise ohne sichtbares Justfile im Scope. |
| `.github/workflows/release.yml` | FAIL | 32/32 Zeilen gelesen. Kein Test-Gate, Tag-/Manual-Release, `contents: write`, bewegliche Action-Referenz, keine npm-Veröffentlichung. |
| `.github/workflows/test.yml` | WARN | 29/29 Zeilen gelesen. Go-Test/Build vorhanden; Worker-, Node-, npm-, Shell- und Security-Prüfungen fehlen. |
| `.gitignore` | WARN | 17/17 Zeilen gelesen. Binary/Plist/Build-Artefakte abgedeckt; `auth` nicht ignoriert und tatsächlich versioniert; `.env.*`/Credential-Namen nicht umfassend abgedeckt. |
| `.goreleaser.yml` | WARN | 56/56 Zeilen gelesen. Gepinnte Cross-Compile-Ziele und Reproduzierbarkeitsflags vorhanden; Tool-/Release-Reproduzierbarkeit und Artefaktersetzung unzureichend abgesichert. |
| `ADMIN_API.md` | WARN | 210/210 Zeilen gelesen. Gute Secret-Hinweise, aber `echo`-Ausgabe, unvollständige Header-Doku und unklarer KV-Namensabgleich. |
| `AGENTS.md` | WARN | 104/104 Zeilen gelesen. Duplikat von `CLAUDE.md`/`GEMINI.md`; Port 9877 widerspricht 9878. |
| `CLAUDE.md` | WARN | 104/104 Zeilen gelesen. Inhaltlich identisch zu `AGENTS.md`; veraltete Port-/Workflow-Angaben möglich. |
| `GEMINI.md` | WARN | 104/104 Zeilen gelesen. Inhaltlich identisch zu den beiden anderen Agent-Dokumenten; Port-/Pfadinkonsistenz. |
| `README.md` | WARN | 254/254 Zeilen gelesen. Gute Betriebsübersicht; `@latest`, Workers-IDs, DEBUG-SSE-Angabe und Endpoint-/Dokuabweichungen müssen bereinigt werden. |
| `antigravity-oauth-proxy` | BINARY/WARN | ELF-Binärdatei, ignoriert/nicht versioniert, ca. 13 MB; keine Textprüfung, keine Provenienz- oder Hashprüfung im Repo. |
| `antigravity-proxy.pid` | INFO | 1/1 Textzeile gelesen; enthält nur eine numerische Runtime-Angabe und ist im Parent-Gitignore ausgeschlossen. Kein Prozessstatus wurde abgeleitet. |
| `auth` | BINARY/FAIL | ELF-Binärdatei, ca. 9,8 MB, tatsächlich versioniert; nicht zeilenweise lesbar. OAuth-Skripte erwarten außerdem `auth` unter einem anderen absoluten Pfad. |
| `bun.lock` | WARN | 211/211 Zeilen gelesen. Bun-JSONC mit abschließenden Kommas; nur Wrangler-Root, Version 4.24.3; keine `@dvcrn`-Root-Abhängigkeit und Abweichung zu `package-lock.json`. |
| `go.mod` | OK/WARN | 37/37 Zeilen gelesen. Go 1.25.7 und direkte/indirekte Module gepinnt; keine Toolchain-Verifikation im Startpfad. |
| `go.sum` | OK | 66/66 Zeilen gelesen. Checksummen vorhanden; statisch kein offensichtlicher Direktmodul-Mangel. Kein `go mod verify` ausgeführt. |
| `install-launchagent.sh` | FAIL | 124/124 Zeilen gelesen. macOS-only, Klartext-Key, ungeschützte Eingabe/XML-Escaping, keine sichere Dateirechte-/plist-Validierung. |
| `mise.development.toml` | WARN | 14/14 Zeilen gelesen. `goreleaser = "latest"`; Snapshot/Release-Tasks ohne Test-Gate. |
| `mise.toml` | WARN | 39/39 Zeilen gelesen. Tasks referenzieren Go 1.25.7, `go test ./...`, Worker-Build und ungepinntes `bunx`; Format-Task mutiert Quellen. |
| `npm/.npmignore` | OK | 2/2 Zeilen gelesen. Schließt Binärdateien aus; die `files`-Whitelist in `npm/package.json` ist die primäre Paketgrenze. |
| `npm/index.js` | WARN | 65/65 Zeilen gelesen. Wrapper startet Binary korrekt als Child-Prozess, kann aber zur Laufzeit nachinstallieren und den Update-Check auslösen. |
| `npm/package-lock.json` | OK | 31/31 Zeilen gelesen. Striktes JSON, `semver` 7.7.4, konsistent mit `npm/package.json`; keine Secrets. |
| `npm/package.json` | WARN | 27/27 Zeilen gelesen. Version 1.1.1 und Postinstall korrekt als Wrapper beschrieben; keine `engines`-/Paketmanager-Pin, Release-Version separat. |
| `npm/postinstall.js` | FAIL | 182/182 Zeilen gelesen. Externer Binary-Download, Checksumme nur best effort, vorhandenes Binary ungeprüft, `tar`-Abhängigkeit und unbeschränkte URL-/Antwortverarbeitung. |
| `npm/update_check.js` | WARN | 169/169 Zeilen gelesen. TTY/CI-Guard, 1,2-s-Timeout und Cache sind positiv; Registry-Request und Cache-/Redirect-Handling sind externe Vertrauensannahmen. |
| `package-lock.json` | WARN | 1473/1473 Zeilen gelesen. Striktes JSON; Root-Lock löst Wrangler 4.97.0 und Node-`>=22`-Bäume auf, abweichend von `bun.lock`. |
| `package.json` | WARN | 6/6 Zeilen gelesen. Kein Name/Version/Scripts/Engines; `@dvcrn`-Abhängigkeit im geprüften Betriebspfad ohne erkennbare Verwendung. |
| `run_proxy.sh` | WARN | 17/17 Zeilen gelesen. Binary- und mise-Fallback existieren, aber relative Pfade, cwd-Annahme und fehlender expliziter Port/credential setup. |
| `scripts/generateContent.sh` | FAIL | 21/21 Zeilen gelesen. Falscher Port 9888, festes Bearer-Credential, kein Fail-/Timeout-Verhalten, `jq`-Abhängigkeit und veraltetes Modellbeispiel. |
| `scripts/start.sh` | FAIL | 59/59 Zeilen gelesen. Fester Admin-Key, unkontrollierter Go-Download, vorhandenes Binary blind vertraut, PID-/Port-Annahmen und fehlende Auth-/Provenienzprüfung. |
| `scripts/stop.sh` | FAIL | 16/16 Zeilen gelesen. Unvalidierte PID, globales `pkill -f`, kein Warten auf Prozess-/Port-Freigabe. |
| `setup_oauth.sh` | FAIL | 140/140 Zeilen gelesen. Falscher absoluter Pfad, breites Kill, zufälliger Key wird ausgegeben, fragile JSON-/URL-Verarbeitung, Default-Port-Annahme. |
| `setup_oauth_final.sh` | FAIL | 112/112 Zeilen gelesen. Falscher Pfad, Präfix-Kill, vorhandenes Helper-Binary wird nicht auf Aktualität geprüft, Key-Ausgabe und sehr lockere Statusprüfung. |
| `setup_oauth_fixed.sh` | FAIL | 123/123 Zeilen gelesen. Falscher Pfadbereich, Helper-Build nur bei fehlender Datei, Binary-/Go-Version nicht verifiziert, Key-Ausgabe und lockere Statusprüfung. |
| `setup_oauth_full.sh` | FAIL | 123/123 Zeilen gelesen. Nahezu Duplikat von `setup_oauth_fixed.sh`, mit breitem `pkill -f`; kein kanonischer OAuth-Einstieg. |
| `uninstall-launchagent.sh` | WARN | 43/43 Zeilen gelesen. macOS-only, symlink/file- und lokale plist-Entfernung mit Prompt; keine starke Fehler-/Plist-Validierung. |
| `wrangler.toml` | FAIL | 26/26 Zeilen gelesen. Produktive Identifikatoren, Main-/Build-Abhängigkeit, kein Secret im `[vars]`-Block und vollständige persistente Logs. |

## 10. Cross-Reference-Matrix

| Referenz | Ergebnis |
|---|---|
| `go.mod:1-3` ↔ `mise.toml:2-3` ↔ `.github/workflows/test.yml:16-20` | Go-Version grundsätzlich konsistent; Startskript installiert/prüft sie nicht strikt. |
| `go.mod:10-16` ↔ `go.sum:1-66` | Direkte Go-Abhängigkeiten und Checksummen sind vorhanden; keine statische Lücke erkannt. |
| `mise.toml:30-35` ↔ `wrangler.toml:1-3,19-20` | Worker-Build ist verknüpft; `build/worker.mjs` konnte ohne erlaubten Build nicht verifiziert werden. |
| `.goreleaser.yml:5-39` ↔ `npm/postinstall.js:105-155` | Binary-/Arch-/Asset-Namen passen grundsätzlich; Checksumme ist im Installer nicht verpflichtend. |
| `.goreleaser.yml:12-25` ↔ `npm/postinstall.js:73-103` | Linux/macOS/Windows und amd64/arm64/armv7 grundsätzlich abgedeckt; Windows-Entpackung setzt ein externes `tar` voraus. |
| `install-launchagent.sh:34-69` ↔ `run_proxy.sh:5-14` | LaunchAgent setzt cwd und `PORT`; `run_proxy.sh` verwendet relative Pfade und kein explizites `--port`. |
| `scripts/start.sh:8-10,45-50` ↔ `README.md:58,71,241-246` | 9878 stimmt; `AGENTS.md`/`CLAUDE.md`/`GEMINI.md` widersprechen mit 9877, `generateContent.sh` mit 9888. |
| `README.md:101,214-235` ↔ `ADMIN_API.md:46-53,57-113` | Credentials-/Admin-Dokumentation teilweise kompatibel, Header- und Endpoint-Matrix nicht vollständig synchron. |
| `wrangler.toml:9-14` ↔ `ADMIN_API.md:202-210` | KV-Binding/Name und Doku sind nicht eindeutig gleich; Umbenennung/Account-spezifische IDs nötig. |
| `package.json:2-5` ↔ `package-lock.json:6-10,1394-1426` ↔ `bun.lock:3-9,201` | npm- und Bun-Bäume sind unterschiedlich; kein eindeutiger Paketmanager ist festgelegt. |
| `npm/package.json:2-4` ↔ Root-Lock `@dvcrn/antigravity-proxy:1.1.0` ↔ `.goreleaser.yml` | Wrapper-Version 1.1.1 und upstream/npm-Abhängigkeit 1.1.0 sind nicht durch einen gemeinsamen Release-Schritt synchronisiert. |
| `AGENTS.md` ↔ `CLAUDE.md` ↔ `GEMINI.md` | Inhaltliche Duplikate; kein Hinweis auf eine kanonische Dokumentquelle. |
| `scripts/stop.sh:8-15` ↔ alle `setup_oauth*.sh`-Kill-Aufrufe | Mehrere unabhängige Prozessbeendigungswege mit unterschiedlicher, aber überwiegend breiter Semantik. |
| `.claude/settings.local.json:4-5` ↔ `mise.toml` | `just format`/`just build-worker:*` haben im analysierten Scope keine Entsprechung; tatsächliche Tasks heißen `mise run ...`. |

## 11. Durchgeführte statische Prüfungen

- `bash -n` für alle zehn Shell-Dateien: **PASS**.
- Striktes JSON für `package.json`, Root-`package-lock.json`, `npm/package.json`, `npm/package-lock.json` und `.claude/settings.local.json`: **PASS**.
- TOML für `wrangler.toml`, `mise.toml` und `mise.development.toml`: **PASS**.
- `bun.lock` wurde vollständig gelesen; es ist Bun-spezifisches JSONC und deshalb nicht als striktes JSON bewertet.
- Dateibestand: 37 Dateien, 35 Textdateien, 2 ELF-Binärdateien.
- `git status` war vor dem Schreiben im analysierten Scope und am Report-Pfad sauber; seitdem wurde nur der Report neu erstellt.
- Nicht ausgeführt: `mise run format`, `mise run test`, `mise run build`, Go-Builds, Worker-Builds, npm-/Bun-Installation, `go mod verify`, Netzwerk-/OAuth-/Prozess-/Portprüfungen. `mise run format` würde Quellen mutieren; die übrigen Test-/Build-Aktionen wären durch die explizite No-Build/No-Start-Vorgabe ausgeschlossen.

## 12. Empfohlene Reihenfolge

1. Betroffene Credentials rotieren, aus Git-Historie/Artefakten entfernen und alle Starts auf Secret-Store/Environment-Datei mit restriktiven Rechten umstellen.
2. `setup_oauth*.sh` konsolidieren, auf den Repository-Relativpfad umstellen und `pkill` durch validierte PID-/Prozess-/Portprüfung ersetzen.
3. Einen einzigen Port- und Auth-Vertrag festlegen; 9878, 9877, 9888 sowie Callback-Port und `run_proxy.sh`/`start.sh` angleichen.
4. npm-Postinstall mit verpflichtender, fest verankerter Integritätsprüfung und dokumentierten Binär-Artefakten versehen; vorhandene Binaries nicht blind vertrauen.
5. Root-`package-lock.json` und `bun.lock` auf einen Paketmanager/Version festlegen, GoReleaser pinnen und Actions per SHA fixieren.
6. CI um Shell-, npm-/Bun-, Worker- und Release-Smoke-Prüfungen erweitern; Release an Tests, Konkurrenzschutz und manuelle Freigabe koppeln.
7. Workers-spezifische IDs, Secrets, Logs und Callback-/OAuth-Dokumentation konsistent und minimal dokumentieren.

**Ende des Berichts.**
<!-- END PART D -->

## Anhang E — Antigravity-Proxy: Cmd, Auth, Credentials und HTTP

<!-- BEGIN PART E -->
## Revision Partition E — vollständiger Datei-Audit

**Audit-Scope:** ausschließlich `llm-proxies/antigravity-proxy/cmd/` sowie `internal/auth/`, `internal/credentials/`, `internal/http/`, `internal/env/`, `internal/project/` und `internal/logger/`.

**Prüfmethode:** statische, vollständige und zeilenweise Lektüre aller Go-Dateien in den genannten Verzeichnissen einschließlich Unterverzeichnissen. Es wurden keine Builds, Tests, Netzwerkverbindungen oder Prozessstarts ausgeführt und keine Quell- oder Betriebsdateien geändert. `Revision.md` wurde nicht gelesen, geschrieben oder verändert.

**Geheimnisbehandlung:** Der Bericht nennt keine Token-, Secret-, Credential-, Authorization-Code- oder personenbezogenen Werte. Ein im Source vorhandener OAuth-Client-Secret wird ausschließlich redigiert beschrieben.

## 1. Inventar und Vollständigkeitsnachweis

Im Scope liegen ausschließlich die folgenden 18 Go-Dateien; weitere Go-/Textdateien oder versteckte Dateien wurden nicht gefunden.

| Datei | Zeilen | Build-Tag | Ergebnis |
|---|---:|---|---|
| `cmd/antigravity-oauth-proxy-worker/main.go` | 75 | `js && wasm` | vollständig gelesen |
| `cmd/antigravity-oauth-proxy/main.go` | 72 | Standard | vollständig gelesen |
| `cmd/auth/main.go` | 162 | Standard | vollständig gelesen |
| `cmd/callback-server/main.go` | 176 | Standard | vollständig gelesen |
| `internal/auth/oauth.go` | 317 | Standard | vollständig gelesen |
| `internal/credentials/types.go` | 31 | Standard | vollständig gelesen |
| `internal/credentials/file_provider.go` | 185 | Standard | vollständig gelesen |
| `internal/credentials/cloudflare_kv_provider.go` | 120 | `js && wasm` | vollständig gelesen |
| `internal/credentials/provider.go` | 16 | Standard | vollständig gelesen |
| `internal/credentials/refresh.go` | 70 | Standard | vollständig gelesen |
| `internal/credentials/refresh_test.go` | 82 | Standard | vollständig gelesen |
| `internal/http/http_client.go` | 8 | Standard | vollständig gelesen |
| `internal/http/http_client_workers.go` | 45 | `js && wasm` | vollständig gelesen |
| `internal/http/http_client_default.go` | 30 | `!js || !wasm` | vollständig gelesen |
| `internal/env/env.go` | 22 | `!js || !wasm` | vollständig gelesen |
| `internal/env/env_workers.go` | 22 | `js && wasm` | vollständig gelesen |
| `internal/project/discover.go` | 240 | Standard | vollständig gelesen |
| `internal/logger/logger.go` | 107 | Standard | vollständig gelesen |
| **Summe** | **1.780** |  | **18/18 vollständig** |

## 2. Risikostufen

| Stufe | Bedeutung |
|---|---|
| **Kritisch** | Direkter, plausibler Zugriff auf Secrets oder Fernausführung ohne plausible Vorbedingung; im untersuchten Scope nicht belegt. |
| **Hoch** | Credential-Kompromittierung, authentifizationsbezogene Umgehung, dauerhafte Betriebsstörung oder nicht kontrollierbare Ressourcenbelastung. |
| **Mittel** | Erhöhte Verfügbarkeits-, Integritäts-, Datenschutz- oder Testrisiken; teils abhängig von nicht geprüften Aufrufern. |
| **Niedrig** | Defense-in-Depth, Robustheit, Hygiene oder eingeschränkte CLI-/Diagnosewirkung. |
| **Info** | Beobachtung oder bestätigte positive Eigenschaft ohne eigenständiges Risiko. |

## 3. Gesamturteil

Die wichtigsten Risiken sind:

1. ein im Quelltext eingebetteter und exportiert veränderlicher OAuth-Client-Secret-Wert (`internal/credentials/types.go:28-30`);
2. ein separates, statisch nicht übersetzbares Callback-Kommando mit unsicherem Callback, Credential-Leaks in Log/argv und einer nicht zum eigentlichen Auth-CLI verdrahteten PKCE-/State-Logik (`cmd/callback-server/main.go:20-176`);
3. nicht-atomare Credential-Speicherung sowie ein Refresh-Lebenszyklus, der bei Environment-Credentials erfolgreich scheitert, aber den aktualisierten Access Token verwirft (`internal/credentials/file_provider.go:102-176`);
4. unbegrenztes Polling, fehlende Request-Timeouts und unbeschränktes Response-Reading während Project Discovery/Onboarding (`internal/project/discover.go:97-204`);
5. ein fehlertolerant fortgesetzter Worker-Start mit möglicherweise nil Provider (`cmd/antigravity-oauth-proxy-worker/main.go:21-69`);
6. fehlende Bindungsvalidierung im Workers-HTTP-Adapter sowie fehlende zentrale HTTP-Richtlinien für Redirects, Timeouts, Headerwerte und Ressourcengrenzen (`internal/http/http_client_workers.go:19-44`, `internal/http/http_client_default.go:12-29`).

## 4. Datenfluss- und Lebenszyklusmodell

### 4.1 Nativer Proxy-Start

1. `PORT` und optional `CLOUDCODE_GCP_PROJECT_ID` werden aus der Environment gelesen (`cmd/antigravity-oauth-proxy/main.go:15`, `:58-60`).
2. `FileProvider` bestimmt den Credential-Pfad, migriert möglicherweise Legacy-Dateien und lädt anschließend JSON aus Datei oder Environment (`internal/credentials/file_provider.go:29-59`, `:66-130`).
3. Der Startup-Auth-Check verwendet den Provider über `antigravity.NewClient(...).LoadCodeAssist()` (`cmd/antigravity-oauth-proxy/main.go:23-28`). Die konkrete Ablauflogik dieser Paketgrenze wurde nicht geprüft.
4. `project.Discover` priorisiert Environment-Override, danach bekannte Projektinformationen, sonst Onboarding (`internal/project/discover.go:16-39`).
5. Beim Onboarding wird ein Access Token aus dem Provider gelesen und an Code-Assist-Anfragen gesetzt; auf HTTP 401 wird maximal ein Refresh pro Endpunkt-Zyklus versucht (`internal/project/discover.go:139-202`).
6. Der Server wird mit Provider und Projekt-ID erzeugt und an einen unvalidierten, typischerweise alle Interfaces bindenden Adressstring übergeben (`cmd/antigravity-oauth-proxy/main.go:65-70`).

### 4.2 Worker-Start

1. `ANTIGRAVITY_AUTH` wird als KV-Binding geöffnet; Fehler werden im Entrypoint dennoch als „weiterlaufen“ behandelt (`internal/credentials/cloudflare_kv_provider.go:22-35`, `cmd/antigravity-oauth-proxy-worker/main.go:21-30`).
2. Ein Startup-Auth-Check und gegebenenfalls Onboarding laufen bereits während `init()` (`cmd/antigravity-oauth-proxy-worker/main.go:19-69`).
3. Der Server erhält zusätzlich denselben Provider als Google-Auth-Quelle (`cmd/antigravity-oauth-proxy-worker/main.go:62-68`).
4. `workers.Serve` übernimmt danach den HTTP-Server (`cmd/antigravity-oauth-proxy-worker/main.go:72-74`).

### 4.3 Interaktiver Auth-CLI-Fluss

1. State und PKCE-Verifier werden mit kryptografischem Zufall erzeugt (`internal/auth/oauth.go:86-103`).
2. Eine Autorisierungs-URL wird erzeugt und entweder im Browser geöffnet oder manuell ausgegeben (`cmd/auth/main.go:33-69`).
3. Der Browser-Callback wird auf Loopback gebunden; im manuellen Modus wird eine Redirect-URL oder ein Code gelesen (`internal/auth/oauth.go:110-166`, `cmd/auth/main.go:146-161`).
4. Der State-Vergleich ist im manuellen Modus optional; ein leerer State umgeht die Prüfung (`cmd/auth/main.go:71-76`).
5. Code, PKCE-Verifier und Client-Credentials gehen als Form-Body an den Token-Endpunkt (`internal/auth/oauth.go:168-223`).
6. Userinfo ist optional; der Refresh Token ist zwingend (`cmd/auth/main.go:78-92`).
7. Credentials werden entweder im Klartext auf stdout gedruckt oder vor einer nachgelagerten Verifikation in den FileProvider geschrieben (`cmd/auth/main.go:94-121`).

### 4.4 Token-Lebenszyklus

- **Erzeugen:** Token-Exchange im Auth-CLI.
- **Speichern:** Datei oder Cloudflare KV als JSON-Objekt mit Access Token, Refresh Token, Ablaufzeit, Typ, Scope und optionalem ID Token (`internal/credentials/types.go:3-19`).
- **Verwenden:** Code-Assist-Anfragen verwenden den Access Token; in `project.Discover` wird das Ablaufdatum nicht geprüft, sondern auf 401 reagiert (`internal/credentials/file_provider.go:102-130`, `internal/project/discover.go:149-170`).
- **Auffrischen:** POST mit Refresh Token und Client-Credentials, 30-Sekunden-Kontext, Antwortlimit 1 MiB; nur Access Token, Ablaufzeit sowie optional Typ/Scope werden ersetzt (`internal/credentials/refresh.go:22-69`).
- **Persistieren:** Datei direkt per `os.WriteFile` oder KV per `PutString` (`internal/credentials/file_provider.go:133-159`, `internal/credentials/cloudflare_kv_provider.go:58-72`).
- **Beenden:** Im FileProvider wird die Datei nicht gelöscht; Legacy-Credentials bleiben zusätzlich erhalten. KV setzt keine Ablaufmetadaten.

## 5. Datei-Audit

### 5.1 `cmd/antigravity-oauth-proxy-worker/main.go`

| ID | Risiko | Zeilen | Befund | Empfehlung |
|---|---|---:|---|---|
| E-CMD-W-01 | **Hoch** | `21-30`, `46-69` | Fehler beim Erzeugen des KV-Providers werden geloggt, danach aber mit dem möglicherweise nil Provider weitergearbeitet. Die nachfolgenden Methodenaufrufe können dereferenzieren/panicen oder einen unbrauchbaren Server erzeugen; die Warnung behauptet zugleich, der Proxy laufe weiter. | Provider-Fehler fail-closed behandeln oder vor jeder Verwendung explizit auf einen non-nil Provider prüfen. |
| E-CMD-W-02 | **Mittel** | `27-33`, `42-69` | Mehrere potenziell netzwerk- und credentialabhängige Operationen laufen synchron in `init()`. Bei fehlgeschlagenem Auth-Check kann der Start mit Environment-Projekt fortgesetzt werden; die tatsächliche Serverbereitschaft ist damit nicht garantiert. | Startup-Artefakte lazy beim ersten Request oder in einer expliziten, begrenzten Initialisierungsphase erzeugen; Readiness erst nach erfolgreicher notwendiger Auth/Projektinitialisierung signalisieren. |
| E-CMD-W-03 | **Niedrig** | `34-39`, `59` | Tier- und Projektkennungen werden im Klartext geloggt. Sie sind keine Secrets, sind aber sensible Betriebsmetadaten. | Log-Redaktion oder Datensparsamkeit für Benutzer-/Projektkennungen konfigurierbar machen. |

**Positive:** Build-Tag und KV-Auswahl sind klar getrennt; der native Entrypoint behandelt seinen Startup-Pfad fail-closed. Der Worker-Entrypoint bleibt davon getrennt und ist beim Provider-Fehler fehlertolerant.

### 5.2 `cmd/antigravity-oauth-proxy/main.go`

| ID | Risiko | Zeilen | Befund | Empfehlung |
|---|---|---:|---|---|
| E-CMD-M-01 | **Mittel** | `15`, `69-70` | `PORT` wird ungeprüft übernommen und durch Voranstellen eines Doppelpunkts grundsätzlich an alle Interfaces addressiert. Ob der Proxy nur lokal erreichbar sein soll, hängt damit von Firewall/Netzwerk und nicht geprüfter Serverlogik ab. | Port als Zahl `1..65535` validieren; standardmäßig explizit an Loopback binden und externe Bindung als bewusstes opt-in behandeln. |
| E-CMD-M-02 | **Mittel** | `26-28`, `58-66` | Wenn der Startup-Auth-Check scheitert, kann ein gesetzter Environment-Projektwert den anschließenden `Discover`-Fehler vermeiden und der Server trotzdem starten. Die Proxy-Laufzeit ist dann vorhanden, aber jeder credentialabhängige Request kann fehlschlagen. | Mindest-Startup-Validität explizit festlegen; Readiness erst nach gültigem Refresh-/Access-Token und gültigem Projekt signalisieren. |
| E-CMD-M-03 | **Niedrig** | `30-52` | Umfangreiche Tier-, Kontingent-, Projekt- und Upgrade-Metadaten werden im Klartext geloggt. | Nur für Diagnose benötigte Felder auf Standardlogstufe ausgeben. |

**Grenze:** `server.NewServer`, `srv.Start` und das Laden von Credentials im Server wurden nicht geprüft; daraus werden keine Aussagen zu Routen, Middleware oder Request-Authentifizierung abgeleitet.

### 5.3 `cmd/auth/main.go`

| ID | Risiko | Zeilen | Befund | Empfehlung |
|---|---|---:|---|---|
| E-CMD-A-01 | **Hoch** | `27`, `103-107` | `--print` schreibt den vollständigen Credential-Satz einschließlich Refresh-/Access-/ID Token in stdout. Das ist für Pipe/CI/Terminal-History besonders gefährlich. | Opt-in beibehalten, aber nur nach expliziter interaktiver Bestätigung, mit dokumentierter sicheren Datei-Ausgabe; niemals Tokens in Logs oder normalen stdout schreiben. |
| E-CMD-A-02 | **Hoch** | `110-120` | Neue Credentials werden vor `LoadCodeAssist` gespeichert. Schlägt die Verifikation fehl, bleiben möglicherweise unbrauchbare neue Credentials zurück und ersetzen einen zuvor funktionierenden Satz. | Verifikation vor dem atomaren Commit ausführen oder alten Satz bis zum Erfolg verfügbar halten und Restore-Pfad anbieten. |
| E-CMD-A-03 | **Mittel** | `71-76` | State-Prüfung ist nur bei nichtleerem State aktiv. Manueller Modus akzeptiert fehlenden oder falschen State; auch ein Callback ohne State umgeht die Prüfung. PKCE begrenzt Code-Injection, ersetzt aber die CSRF-Bindung nicht. | State immer exakt und constant-time vergleichen; bei manueller Eingabe die vollständige Redirect-URL inklusive State verlangen. State-Werte nicht loggen. |
| E-CMD-A-04 | **Niedrig** | `131-143` | `exec.Cmd.Start` wird ohne `Wait` aufgerufen. Der Browserprozess kann bis zum CLI-Ende unaufgeräumt bleiben; ein Startfehler wird nur als „open manually“ behandelt. | Kurzlebiges, wait-fähiges Öffnungsmodell oder plattformübergreifend dokumentiertes Verhalten nutzen. |
| E-CMD-A-05 | **Niedrig** | `97` | Expiry wird über `Unix()*1000` berechnet und dadurch auf ganze Sekunden abgeschnitten. | `UnixMilli()` verwenden, analog zum Refresh-Pfad. |
| E-CMD-A-06 | **Niedrig** | `146-161` | Lesefehler und URL-Parsefehler werden als leere bzw. unveränderte Eingabe weitergereicht; fehlende OAuth-Error-Parameter werden nicht verständlich diagnostiziert. | Fehler explizit zurückgeben, Eingabegröße begrenzen und Redirect-URL-Fehler berichten. |
| E-CMD-A-07 | **Niedrig** | `87-92` | Die aus Userinfo gelesene E-Mail-Adresse wird im Klartext geloggt. Sie ist kein Token, aber ein personenbezogenes Betriebsdatum. | E-Mail nur zur interaktiven Bestätigung anzeigen oder Pseudonym/Hash in Logs verwenden. |

**Positive:** Kryptografischer State/PKCE, Refresh-Token-Pflicht, Response-Bodies werden nicht in Fehlertexte übernommen, und Tokens werden im normalen Save-Pfad nicht geloggt.

### 5.4 `cmd/callback-server/main.go`

| ID | Risiko | Zeilen | Befund | Empfehlung |
|---|---|---:|---|---|
| E-CMD-C-01 | **Hoch** | `3-11`, `67-175` | Die Datei ist statisch nicht übersetzbar: Im Importblock fehlen unter anderem `context`, `time`, `strings`, `runtime`, SHA-256-/Base64- und Zufalls-Unterstützung, obwohl die genannten Symbole verwendet werden; `io` wird importiert, aber nicht verwendet. Ein Build wurde auftragsgemäß nicht ausgeführt; der Befund folgt direkt aus Importen und Bezeichnern. | Datei entfernen oder auf den funktionalen Auth-Weg in `cmd/auth`/`internal/auth` konsolidieren; keine parallele Auth-Implementierung behalten. |
| E-CMD-C-02 | **Hoch** | `20-28`, `42-59`, `96-107` | Der Callback lauscht auf allen Interfaces, akzeptiert jeden Methodenaufruf, prüft weder State noch Absender und überschreibt globale Callback-Daten bei jedem Treffer. Eine erreichbare Gegenstelle kann den Ablauf blockieren oder einen fremden Code einspeisen. | Genau den funktionierenden Loopback-Callback aus `internal/auth` verwenden; Methode, State, Single-Use und Lifecycle serverseitig erzwingen. |
| E-CMD-C-03 | **Hoch** | `28`, `67-101` | Authorization-Code-Fragmente werden geloggt, der vollständige Code wird als Prozessargument an `go run` übergeben, Helper-Ausgabe wird geloggt und der manuelle Code wird auf stdout gedruckt. Damit bestehen mehrere Leakpfade in Logs, Process Table und Terminalauzeichnung. | Code nur über geschützte In-Memory-Kanäle übergeben; niemals als argv, stdout oder Log ausgeben. |
| E-CMD-C-04 | **Hoch** | `61-93`, `110-128`, `142` | `runAuthHelper` ignoriert URL, PKCE-Verifier und Challenge. Der gepollt State wird nicht validiert und ist als lokale Variable ungenutzt. Anschließend wird ein im eigentlichen `cmd/auth` nicht definiertes Manual-Code-Flag verwendet, zusammen mit einem fest codierten Arbeitsverzeichnis und einem nicht expandierenden PATH-Environment-Eintrag. Selbst nach Ergänzen der fehlenden Imports wäre der beabsichtigte PKCE-Lebenszyklus nicht verdrahtet. | Einen einzigen Auth-Fluss verwenden; Callback, State und denselben PKCE-Verifier innerhalb desselben Prozesses bis zum Token-Exchange halten. |
| E-CMD-C-05 | **Mittel** | `51-58`, `105-108` | `serverReady` wird geschlossen, bevor `ListenAndServe` erfolgreich gebunden hat. Portkonflikte/Laufzeitfehler werden nur geloggt; der Main meldet trotzdem erfolgreichen Start und wartet anschließend auf ein eventuell nie eintreffendes Callback. | Listener synchron binden, Fehler direkt zurückgeben und erst danach Bereitschaft signalisieren. |
| E-CMD-C-06 | **Mittel** | `46-49`, `67-90`, `147-149` | Keine HTTP-Server-Timeouts; der polling-Aufruf kann durch `CombinedOutput` unbegrenzt hängen; `Shutdown` erhält keinen Deadline-Kontext. | ReadHeader-/Idle-/Write-Timeouts, Command-Kontext und begrenzten Shutdown-Kontext verwenden. |
| E-CMD-C-07 | **Mittel** | `111-113`, `154-157` | State beruht auf `UnixNano` und ist vorhersagbar. Das Ergebnis des Zufallslesens wird außerdem ignoriert; welches Paket wegen der fehlenden Imports gemeint war, ist statisch nicht abschließend feststellbar. | State und PKCE immer mit kryptografischem Zufall erzeugen und Fehler propagieren. |
| E-CMD-C-08 | **Niedrig** | `165-175` | Der Browserprozess wird ohne `Wait` gestartet. | Wie beim eigentlichen Auth-CLI Prozessressourcen kontrolliert freigeben. |
| E-CMD-C-09 | **Niedrig** | `20-33`, `68-71` | Der Callback hält den globalen Mutex während Logging und Response-Write. Ein langsamer Client kann dadurch Polling oder weitere Callbacks blockieren. | Kritischen Callback-Zustand unter dem Mutex kopieren, danach ohne Lock antworten; Callback zusätzlich als Single-Use behandeln. |

**Positive:** Der globale Callback-Zustand wird mit einem Mutex geschützt. Das verhindert einen Data Race, beseitigt aber weder die fehlende Authentifizierung des Callbacks noch die Credential-Leaks.

### 5.5 `internal/auth/oauth.go`

| ID | Risiko | Zeilen | Befund | Empfehlung |
|---|---|---:|---|---|
| E-AUTH-01 | **Mittel** | `119-165` | Der temporäre Callback-Server besitzt keine ReadHeader-, Read-, Write- oder Idle-Timeouts. In allen drei Select-Zweigen wird `Shutdown(context.Background())` ohne Deadline verwendet und kann bei einer aktiven Verbindung hängen. | Server-Timeouts setzen und Shutdown mit kurzem, ableitbarem Kontext ausführen. |
| E-AUTH-02 | **Mittel** | `123-140` | Der Callback-Handler akzeptiert einen leeren State und jede HTTP-Methode und sendet Erfolg an den Browser, bevor der Aufrufer den State validiert. Die sicherheitskritische Prüfung ist damit außerhalb des Handlers und optional gekoppelt. | Erwarteten State serverseitig über Closure/Callback übergeben und dort atomar prüfen; nur GET zulassen und Erfolg erst nach Prüfung schreiben. |
| E-AUTH-03 | **Mittel** | `63-83` | `AuthorizationURL` prüft Client-ID, Redirect und Scopes, aber nicht leeren State oder leere PKCE-Challenge. Der Generator erzeugt korrekte Werte, die öffentliche Funktion erlaubt jedoch unsichere Aufrufe. | State und Challenge als nichtleer, gültig base64url-kodiert validieren. |
| E-AUTH-04 | **Niedrig** | `284-287` | `writeHTML` maskiert den Titel, nicht aber den übergebenen Body. Aktuelle Aufrufstellen sind kontrolliert, die Helper-API ist jedoch fehleranfällig. | Entweder ausschließlich maskierte Textfragmente übergeben oder auch den Body escapen; Sicherheitsheader für `nosniff`, `no-store` und eine minimale CSP ergänzen. |

**Positive:** State und PKCE werden mit 128 bzw. 256 Bit kryptografischem Zufall erzeugt; PKCE nutzt S256; Redirect-URIs werden auf HTTP, Loopback-Host und expliziten Port begrenzt; der Listener bindet explizit nur `127.0.0.1`; Token-/Userinfo-Antworten sind auf 1 MiB begrenzt; Request-Kontexte und Body-Closing sind vorhanden; Fehlertexte enthalten keine Upstream-Response-Bodies.

### 5.6 `internal/credentials/types.go`

| ID | Risiko | Zeilen | Befund | Empfehlung |
|---|---|---:|---|---|
| E-CRED-T-01 | **Hoch** | `28-30` | Ein OAuth-Client-Secret ist als exportierte, veränderliche globale Variable im Quelltext eingebettet; die String-Verkettung bietet keinen Schutz. PKCE reduziert Missbrauch, beseitigt aber weder Credential-Exposition noch Client-Impersonation oder spätere Rotation. Der Wert wird hier bewusst nicht wiederholt. | Bestehenden Wert als kompromittiert betrachten und rotieren; für Native Client keinen wiederverwendbaren geheimen Client-Key einbetten, sofern der OAuth-Flow dies unterstützt. Secret andernfalls nur aus Secret Store/Deployment-Konfiguration laden und nicht exportieren. |
| E-CRED-T-02 | **Mittel** | `3-19`, `28-30` | Datenmodell und globale Providerkonfiguration vermischen Identitätsmetadaten, Access-/Refresh-/ID-Token und veränderliche globale Clientkonfiguration. Es gibt keine Konstruktorvalidierung, Zero-Value-Schutz, Gültigkeitsprüfung oder Secret-Redaktionsmarkierung. | Credentials validieren, als unveränderliche Struktur behandeln, Refresh-/ID-Token-Lebenszyklus explizit modellieren und Providerkonfiguration nicht als veränderliche globale Secrets ablegen. |

### 5.7 `internal/credentials/file_provider.go`

| ID | Risiko | Zeilen | Befund | Empfehlung |
|---|---|---:|---|---|
| E-CRED-F-01 | **Hoch** | `141-159` | `SaveCredentials` schreibt direkt in den endgültigen Pfad. Ein Absturz kann eine trunkierte Datei hinterlassen. `0600` wirkt nur beim Anlegen; bei einer bereits vorhandenen Datei werden zu weite Rechte nicht korrigiert. Es gibt kein fsync/atomares Rename. | Im selben Verzeichnis eine neue Datei mit `0600` anlegen, explizit chmod, fsync und atomar ersetzen; Verzeichnisrechte/-persistenz absichern. |
| E-CRED-F-02 | **Hoch** | `102-138`, `163-176` | Beim Environment-Fallback setzt `GetCredentials` `filePath` dauerhaft auf leer. `SaveCredentials` gibt dann Erfolg zurück, schreibt aber nichts. `RefreshToken` verwirft somit den neu erzeugten Access Token; jeder spätere Ladevorgang verwendet wieder die abgelaufenen Environment-Credentials und löst erneut Refresh aus. Der Aufrufer erhält fälschlich Erfolg. | Environment-Modus als unveränderlichen Read-only-Modus modellieren. Refresh entweder explizit als nicht speicherbar melden oder Credentials im Prozess als immutable Override mit Thread-Sicherheit halten; niemals Erfolg vortäuschen. |
| E-CRED-F-03 | **Mittel** | `102-127`, `133-176` | `filePath` wird verändert und Refresh ist ein ungeschütztes Read-Modify-Write. Wenn der Provider gleichzeitig von Requests/Isolates genutzt wird, sind Data Race, doppelte Refreshes und Lost Updates möglich. | Providerzustand unveränderlich machen; Refresh mit Singleflight/Mutex und compare-and-swap-Semantik ausführen, gegebenenfalls pro Prozess/Datei locken. |
| E-CRED-F-04 | **Mittel** | `66-98` | Legacy-Migration läuft bereits beim Ermitteln des Pfads. Stat und Write sind nicht atomar; eine inzwischen neu angelegte Zieldatei kann mit Legacy-Inhalt überschrieben werden. Das alte Secret bleibt zusätzlich liegen. | Atomisches, überschreibschützendes Migrationsschema verwenden, alte Datei nach verifizierter Migration mit restriktiven Rechten entfernen und Fehler sichtbar behandeln. |
| E-CRED-F-05 | **Mittel** | `102-130`, `133-155` | JSON wird nur syntaktisch geprüft. Leere Tokens, ungültige Ablaufwerte, `nil` oder beliebige Scope-Werte werden akzeptiert bzw. können als `null` gespeichert werden. | Vor Persistieren und Rückgabe semantisch validieren: non-nil, Refresh Token, positive Ablaufzeit und erwartete Felder. |
| E-CRED-F-06 | **Niedrig** | `98`, `130`, `143-158`, `179-184` | Vollständige lokale Pfade erscheinen in Fehlern, Warnungen, Logs und im Providernamen. Das erleichtert die Offenlegung des Benutzer-/Arbeitsverzeichnisses. | Pfade in Logs auf Basisnamen oder redigierte Form reduzieren; `Name()` sollte keine sensitiven Infrastrukturdetails ausgeben. |

**Positive:** Directory `0700` und neue Datei `0600`; explizite Datei-vor-Environment-Präzedenz; JSON-Fehler werden sauber gewrappt; HTTP-Refresh-Client besitzt ein Gesamt-Timeout; Tokens werden nicht geloggt.

### 5.8 `internal/credentials/cloudflare_kv_provider.go`

| ID | Risiko | Zeilen | Befund | Empfehlung |
|---|---|---:|---|---|
| E-CRED-CF-01 | **Mittel** | `38-72`, `86-98` | Refresh-, Access- und ID Token werden als unverschlüsseltes JSON im KV gespeichert; zusätzlich existiert ein nicht ablaufendes Google-Auth-Sessionmarker-Objekt. Plattform-Verschlüsselung at rest wird dadurch nicht ersetzt. | Application-Layer-Verschlüsselung mit separatem Key erwägen; Credentials und Sessionmarker mit Ablauf-/Versionsmetadaten speichern. |
| E-CRED-CF-02 | **Mittel** | `100-114` | Refresh ist ein ungeschütztes Read-Refresh-Write über KV. Parallele Isolates/Requests können dieselben Credentials lesen und Updates gegenseitig überschreiben. | Versions-/ETag-Vergleich oder zentralen Lock verwenden; idempotente Refresh-Steuerung und Konfliktfehler implementieren. |
| E-CRED-CF-03 | **Mittel** | `75-98` | `google-auth-session` ist weder an einen Benutzer/Flow gebunden noch im sichtbaren Code ein expiry-, consume- oder delete-atomic. `CompleteGoogleAuth` schreibt Credentials und Marker in zwei separaten Operationen. | Session-ID zufällig erzeugen, Owner/Bindung und Ablauf speichern, atomar verbrauchen und Auth-Status vom Credential-Commit trennen oder versionieren. |
| E-CRED-CF-04 | **Mittel** | `38-68` | Gespeicherte/deserialisierte Credentials werden nicht semantisch validiert. `SaveCredentials(nil)` kann ein JSON-Null ablegen; nachfolgend kann Refresh nil dereferenzieren. | nil- und Feldvalidierung vor KV-Zugriff erzwingen. |
| E-CRED-CF-05 | **Niedrig** | `22-34` | Provider hängt vollständig vom festen Binding-Namen ab. Der Konstruktorfehler wird zwar sauber zurückgegeben, vom Worker-Entrypoint aber nicht sicher behandelt. | Binding-Verfügbarkeit und Typ validieren; fail-closed starten. |

**Positive:** Feste KV-Namespace-/Key-Konvention ist konsistent; Bodies und Fehler werden begrenzt/umschlossen; Save/Refresh trennen Transportantwort und Persistenz.

### 5.9 `internal/credentials/provider.go`

| ID | Risiko | Zeilen | Befund | Empfehlung |
|---|---|---:|---|---|
| E-CRED-I-01 | **Mittel** | `4-15` | Das Interface bietet weder Context noch atomare `GetAndRefresh`-/Compare-and-Swap-Semantik oder Validierungsverträge. Jede Implementierung muss schwierige Lifecycle-Regeln duplizieren; das Interface selbst verhindert kein Lost Update. | `GetCredentials(ctx)` und eine atomare Refresh-API mit Konflikt-/Retry-Semantik vorsehen. |
| E-CRED-I-02 | **Niedrig** | `6`, `9` | Ein veränderlicher Pointer wird unbeschränkt herausgegeben und akzeptiert. Ein Provider-Cache könnte Credentials versehentlich durch Aufrufer verändern lassen. | Credentials als Value mit eng begrenzten Methoden oder Read-only Snapshot zurückgeben. |

### 5.10 `internal/credentials/refresh.go`

| ID | Risiko | Zeilen | Befund | Empfehlung |
|---|---|---:|---|---|
| E-CRED-R-01 | **Mittel** | `52-69` | Das Refresh-Antwortmodell enthält kein neues Refresh Token. Wird dieser vom Provider rotiert, geht er verloren; ein altes ID Token wird pauschal weitergeführt und kann veralten. | Token-Rotation explizit unterstützen; ID Token als nicht automatisch verlängert kennzeichnen und bei Nutzung/Ablauf validieren. |
| E-CRED-R-02 | **Mittel** | `33-35` | Jeder Refresh startet einen neuen Background-Kontext. Aufrufer können Shutdown oder Backpressure nicht durch Context übertragen; jede parallel angestoßene Operation läuft bis 30 Sekunden. | Context vom Provideraufruf übernehmen und nur eine harte Obergrenze als Fallback setzen. |
| E-CRED-R-03 | **Mittel** | `47-50` | Temporäre Tokenfehler, `Retry-After` und 5xx werden nicht klassifiziert; jeder Fehler endet sofort. Refresh-Stürme oder kurze OAuth-Ausfälle verursachen harte Auth-Ausfälle. | Kleines exponentielles Backoff-Budget nur für klassifizierbare transiente Antworten, mit `Retry-After` und Jitter, implementieren. |
| E-CRED-R-04 | **Niedrig** | `60-68` | Expiry wird ohne Sicherheitsabstand gesetzt; ein unplausibel großer `expires_in` kann Dauerarithmetik überlaufen. | Ober-/Untergrenzen validieren und die Ablaufzeit um einen kleinen Clock-Skew reduzieren. |
| E-CRED-R-05 | **Niedrig** | `47-54` | Bei Fehlern werden nur 4 KiB drainiert; der JSON-Decoder stoppt nach dem ersten Wert und erzwingt kein abschließendes EOF innerhalb des Limits. Das kann Connection-Reuse und die tatsächliche Durchsetzung des Response-Limits schwächen. | Genau ein JSON-Dokument bis EOF unter einem festen Gesamtlimit lesen und bei Größenüberschreitung explizit fehlschlagen. |
| E-CRED-R-06 | **Niedrig** | `22-24` | Weder `creds` noch `client` werden auf nil geprüft. Ein fehlerhaft implementierter Provider kann deshalb bereits beim Refresh panicen. | Beide Argumente am Funktionsbeginn validieren und Konfigurations-/Providerfehler als normale Fehler zurückgeben. |

**Positive:** 30-Sekunden-Requestkontext; Context auf Form- und Request-Ebene; Response-Body wird geschlossen; Fehler enthalten weder Form- noch Response-Inhalt; vorhandene Felder werden durch Struct-Copy grundsätzlich erhalten.

### 5.11 `internal/credentials/refresh_test.go`

| ID | Risiko | Zeilen | Befund | Empfehlung |
|---|---|---:|---|---|
| E-CRED-TEST-01 | **Mittel** | `18-82` | Getestet werden nur Erfolgsfall und unvollständige Success-Antwort. Nicht abgedeckt sind Netzwerkfehler, non-2xx, 429/5xx, ungültiges JSON, fehlender Refresh Token, Header/Grant-Type, Body-Close, Größenlimit, Expiry-Skew sowie Nebenläufigkeit. | Tabellengestützte Fehler- und Lifecycle-Tests ergänzen; Request-Body und Close-Verhalten prüfen, ohne Credentials im Failure-Output auszugeben. |
| E-CRED-TEST-02 | **Niedrig** | `34-35`, `57-64` | Fehlerausgaben geben Form- und Credential-Strukturen vollständig aus. Die Testdaten sind synthetisch, aber das Muster könnte bei Umstellung auf echte Testdaten gefährlich werden. | Failure-Ausgabe auf Feldnamen und Anwesenheitsbooleans reduzieren. |

**Positive:** `t.Parallel` ist für die reinen Fixtures unkritisch; Nichtmutation des Originals wird geprüft; Ablaufzeitfenster und Erhalt von Refresh-/ID Token werden abgedeckt.

### 5.12 `internal/http/http_client.go`

| ID | Risiko | Zeilen | Befund | Empfehlung |
|---|---|---:|---|---|
| E-HTTP-I-01 | **Mittel** | `5-8` | Das Interface kapselt nur `Do`. Timeouts, Redirect-Policy, Header-Multiwerte, Body-Größen und Ressourcenfreigabe werden nicht zentral durchsetzbar. Zwei weitere Pfade umgehen das Interface bereits mit separaten `net/http`-Clients. | Eine zentrale Do-/DoContext-Richtlinie oder einen deklarativen Client mit festen Policies verwenden; alle Upstream-Aufrufer dazu verpflichten. |

### 5.13 `internal/http/http_client_default.go`

| ID | Risiko | Zeilen | Befund | Empfehlung |
|---|---|---:|---|---|
| E-HTTP-D-01 | **Mittel** | `13-29` | Es gibt keine `CheckRedirect`-Policy. Bei 307/308 kann Go einen requestbaren Body erneut senden; Token-Exchange- und Refresh-Requests enthalten im Form-Body sensible Client-/Token-Daten. Der native FileProvider-Refresh nutzt zusätzlich einen eigenen Default-Redirect-Client (`internal/credentials/file_provider.go:23-26`). | Redirects für Token-/Userinfo-Endpunkte vollständig ablehnen oder nur nach streng validiertem HTTPS-Host/Schema erlauben. |
| E-HTTP-D-02 | **Mittel** | `13-29` | Kein Gesamt-`Client.Timeout`, kein `ResponseHeaderTimeout`, keine aktive Verbindungsbegrenzung. Aktuelle Auth-Pfade nutzen Context, aber das Interface kann problematische unkontextualisierte Aufrufer erlauben. | Gesamt-Timeout als Fallback plus Dial/TLS/ResponseHeader-Timeouts und `MaxConnsPerHost` setzen; Context dennoch primär verwenden. |
| E-HTTP-D-03 | **Niedrig** | `14-28` | Der eigens konstruierte Transport setzt weder HTTP/2 forciert noch Proxy-Environment-Unterstützung. Das kann Performance bzw. Betrieb in Proxy-Umgebungen beeinträchtigen. | Bewusste HTTP/2-/Proxy-Policy dokumentieren und testen; bei Egress-Bedarf einen expliziten Proxy-Transport konfigurieren. |

**Positive:** TLS nutzt sichere Go-Defaults; Kompression bleibt aktiv; Idle-/Keepalive-Werte sind gesetzt; der gemeinsam genutzte Default-Transport wird nicht global verändert.

### 5.14 `internal/http/http_client_workers.go`

| ID | Risiko | Zeilen | Befund | Empfehlung |
|---|---|---:|---|---|
| E-HTTP-W-01 | **Hoch** | `19-25` | Das Egress-Binding wird ungeprüft verwendet. Fehlt es oder besitzt es keine Fetch-Funktion, kann der JS-Aufruf panicen; die Fehler werden nicht in `NewHTTPClient` übersetzt. | Binding auf Existenz/Typ prüfen und einen normalen Go-Fehler zurückgeben. |
| E-HTTP-W-02 | **Mittel** | `36-41` | Mehrfach Headerwerte werden mit `Set` statt `Add` kopiert; spätere Werte überschreiben frühere. Das kann Cookies, Accept-Varianten oder eigene Auth-Header verändern. | Alle Werte mit `Add` übernehmen oder die Map-Semantik der Fetch-API korrekt abbilden. |
| E-HTTP-W-03 | **Niedrig** | `29-44` | Der Adapter delegiert Request-Body-Ownership und Connection-/Response-Lifecycle implizit an die Drittbibliothek, ohne Vertragsprüfung oder Tests. Fehler bei einem manuell erzeugten nil Client sind nicht abgefangen. | Drittbibliotheksvertrag explizit testen; Body-Close und Fehlerfälle mit fiktiven Bindings abdecken. |

**Positive:** Redirects werden manuell behandelt, sodass der Adapter nicht stillschweigend Credentials an ein anderes Redirect-Ziel weiterreicht; Request-Kontext wird an Fetch übergeben.

### 5.15 `internal/env/env.go`

| ID | Risiko | Zeilen | Befund | Empfehlung |
|---|---|---:|---|---|
| E-ENV-N-01 | **Niedrig** | `8-21` | Leerer Wert und nicht gesetzter Wert sind nicht unterscheidbar; Whitespace wird nicht normalisiert. Das kann bei `PORT` oder Projekt-ID zu Default- bzw. schwer verständlichen Downstream-Fehlern führen. | Presence-Semantik dokumentieren; für bekannte Configurationsfelder typ-/bereichsvalidiert interpretieren. |

**Positive:** Native und Worker-Build-Tags schließen sich gegenseitig aus; die Semantik beider Environment-Implementierungen ist derzeit gleich.

### 5.16 `internal/env/env_workers.go`

| ID | Risiko | Zeilen | Befund | Empfehlung |
|---|---|---:|---|---|
| E-ENV-W-01 | **Niedrig** | `8-21` | Gleiche Presence-/Whitespace-Einschränkung wie im nativen Pfad; Cloudflare-Bindings können zusätzlich nicht die Process-Environment-Semantik von `os.Getenv` besitzen. | Worker-spezifische Config-Präsenz und Typen zentral testen. |

**Positive:** Der Worker-Pfad verwendet ausdrücklich die Cloudflare-Environment-API statt `os.Getenv`; Build-Tag und Default-Verhalten entsprechen dem nativen Pendant.

### 5.17 `internal/project/discover.go`

| ID | Risiko | Zeilen | Befund | Empfehlung |
|---|---|---:|---|---|
| E-PROJ-01 | **Hoch** | `160-204` | `callEndpoint` verwendet einen `http.Client` ohne Timeout, Requests ohne Context und `io.ReadAll` ohne Grenze. Ein hängender Upstream oder eine große/kompromittierte Antwort kann den Startup dauerhaft blockieren oder Speicher belasten. | Context mit Gesamtdeadline, Client-/ResponseHeader-Timeouts, Streaming-Cap und Abbruch beim Überschreiten eines festen Limits verwenden. |
| E-PROJ-02 | **Hoch** | `160-173` | Der Worker-Entrypoint nutzt diesen Code, aber `project/discover.go` umgeht den Workers-HTTP-Adapter und verwendet Standard-`net/http`. Ob dieser Transport im konkreten js/wasm-Runtime-Pfad Netzfähigkeit besitzt, ist im Scope nicht belegt; der Adapter existiert genau für diese Runtime-Differenz. | `serverhttp.HTTPClient` und Runtime-spezifischen Constructor auch für Project Discovery verbindlich injizieren. |
| E-PROJ-03 | **Hoch** | `97-136` | Das Onboarding-LRO kann unbegrenzt pollen: keine maximale Pollzahl, kein Gesamtkontext, kein Backoff/Jitter. Ein dauerhaft `done=false` hält den Proxy-Start unbegrenzt offen. | Gesamtkontext, konfigurierbare Deadline, exponentielles Backoff mit Jitter und harte Pollgrenze einführen. |
| E-PROJ-04 | **Mittel** | `19-38`, `46-52` | Environment- und Load-Response-Projektwerte werden nicht auf leer/Format validiert. Der Code kann eine leere Projekt-ID als erfolgreiches Discovery-Ergebnis zurückgeben. | Nichtleere und erlaubte GCP-Projekt-ID-Struktur prüfen, bevor ein Server erzeugt wird. |
| E-PROJ-05 | **Mittel** | `193-230` | Nach Refresh gibt ein Transportfehler sofort auf, statt die übrigen Endpunkte zu versuchen. Fehlerhaftes JSON von einem 200-Endpunkt beendet die gesamte Failover-Kette ebenfalls sofort. | Einheitliche Endpoint-Retry-State-Machine verwenden; Erfolg nur nach Schema-/JSON-Validierung, aber pro Endpunkt klassifizierbar fortsetzen. |
| E-PROJ-06 | **Mittel** | `219-224` | Der komplette Upstream-Body wird in `lastErr` aufgenommen und kann über den aufrufenden Fatal-/Warn-Pfad geloggt werden. Zusammen mit dem fehlenden Response-Limit drohen interne Details oder eine Memory-/Log-Amplifikation. | Fehlertext auf Status/Request-ID beschränken, Body separat begrenzen und sensible Felder redigieren. |
| E-PROJ-07 | **Niedrig** | `58-70` | Wenn kein Default-Tier vorhanden ist, wird ein fest konfigurierter interner Fallback verwendet. Dessen Vertrag ist im geprüften Code nicht belegt und kann ein falsches Onboarding-Ziel wählen. | Fallback explizit konfigurierbar machen und gegen aktuelle API-Verträge testen. |
| E-PROJ-08 | **Niedrig** | `172-179`, `193-217` | Die HTTP-Dauer misst nur den ersten Versuch, nicht den nach Refresh folgenden Retry. Diagnosewerte sind dadurch irreführend. | Metriken je Versuch erfassen und Gesamtdauer separat ausweisen. |

**Positive:** Environment-Override hat explizite Priorität; Endpoint-Failover und 401-Refresh sind vorhanden; Response-Bodies werden geschlossen; Tokens werden nicht geloggt; bekannte schnelle Projekt-Discovery wird vor Onboarding geprüft.

### 5.18 `internal/logger/logger.go`

| ID | Risiko | Zeilen | Befund | Empfehlung |
|---|---|---:|---|---|
| E-LOG-01 | **Mittel** | `43-62` | Logger liest `ENV` und `LOG_LEVEL` direkt aus `os.Getenv`, obwohl das Projekt für Workers eine eigene Environment-Abstraktion besitzt. Dadurch können Worker-Konfigurationen ignoriert und Development-Console-Logging als Production-Logging verwendet werden. | Logger über dieselbe Runtime-abstrakte Environment-API konfigurieren oder Build-Tag-spezifische Logger-Initialisierung bereitstellen. |
| E-LOG-02 | **Mittel** | `47-62`, `102-105` | `zerolog.SetGlobalLevel` und `TimeFieldFormat` verändern prozessweiten/globalen Library-Zustand. Unbekannte `ENV`-Werte führen zu JSON, fehlende/development-typische Werte zu farbigem Console-Output; beides kann andere Logger/Logparser beeinflussen. | Globalzustand nicht verändern; pro Logger lokale Timehook-/Level-Konfiguration verwenden und Production-Modus explizit verlangen. |
| E-LOG-03 | **Niedrig** | `49-54` | Ein ungültiger `LOG_LEVEL`-Wert wird ohne Quotierung in stderr ausgegeben. Steuerzeichen oder Log-Injection sind dadurch möglich. | Mit `%q` und einer sicheren Längenbegrenzung ausgeben. |
| E-LOG-04 | **Niedrig** | `70-94` | Level-Formatierung nimmt ohne Längenprüfung die ersten drei Bytes eines Strings. Standard-Level sind heute lang genug, aber die Hilfsfunktion ist für unbekannte/kurze Eingaben nicht panic-sicher. | Längensichere Formatierung oder eine vordefinierte Level-Map verwenden. |
| E-LOG-05 | **Niedrig** | `26-36`, `98-106` | Es existiert eine zentrale Redaktionsschicht für versehentlich als Felder übergebene Tokens. Der aktuelle Scope loggt tatsächliche Tokens nicht, aber die Sicherheitsgarantie hängt vollständig von jedem Aufrufer ab. | Für bekannte Secret-Feldnamen zentrale Redaction/Hook einführen und mit Regressionstests absichern. |

**Positive:** Singleton-Initialisierung ist mit `sync.Once` threadsicher; Ausgabe geht konsistent nach stderr; ungültige Log-Level fallen sicher auf Info zurück; Zeitstempel sind in beiden Modi vorhanden.

## 6. Querschnittsbefunde

### 6.1 Credential- und Refresh-Integrität — **Hoch**

- File- und KV-Implementierung besitzen jeweils eigene, nicht atomare Read-Modify-Write-Abläufe.
- Das Provider-Interface bietet keine zentrale Konflikt-/Singleflight-Semantik.
- Environment-Credentials können keinen neuen Access Token persistieren, melden Refresh aber trotzdem als Erfolg.
- Migration, Save und Refresh haben keinen einheitlichen Commit-/Rollback-Vertrag.

**Empfehlung:** Einen credential-sicheren Service mit validiertem Snapshot, process-/isolate-sicherem Refresh, atomarem Backend-Commit und explizitem Fehlschlag bei Read-only-Backends einführen.

### 6.2 HTTP-Sicherheitsrichtlinie — **Hoch**

- Native, Worker- und Project-Discovery-Pfade verwenden drei unterschiedliche Client-Policies.
- Redirect-, Timeout-, Header-Multiwert- und Response-Limit-Regeln sind nicht zentral.
- Project Discovery umgeht den Runtime-Adapter und hat keine Grenzen.

**Empfehlung:** Nur einen zentralen `HTTPClient`/`DoContext`-Pfad zulassen; sicherheitsrelevante Defaults nicht pro Paket improvisieren.

### 6.3 Callback- und State-Sicherheit — **Hoch**

- Der robuste Callback liegt in `internal/auth/oauth.go`.
- Der separate Callback-Entrypoint ist statisch defekt, unsicher und loggt Credentials.
- State-Prüfung ist in beiden Authpfaden nicht serverseitig atomar; im manuellen Modus ist sie optional.

**Empfehlung:** Den separaten Entrypoint entfernen und nur einen Lifecycle mit serverseitigem Exact-State-Check, Single-Use Callback und begrenztem Shutdown behalten.

### 6.4 Konfigurationsannahmen — **Mittel**

- Native: Callback-Port, OAuth-Endpunkte, Clientkonfiguration, Credential-Pfade, `PORT`, `ENV`, `LOG_LEVEL`.
- Worker: `ANTIGRAVITY_AUTH`, `ANTIGRAVITY_EGRESS`, KV-Key-Namen und Worker-spezifische Environment-Semantik.
- Discovery: Endpoint-Liste aus dem nicht geprüften `antigravity`-Paket, interner Tier-Fallback und unbegrenzte LRO-Semantik.

**Empfehlung:** Konfiguration beim Startup typisieren, Bindings prüfen, Defaults dokumentieren und Runtime-spezifische Konfigurationstests ergänzen.

### 6.5 Fehler- und Ressourcenmanagement — **Hoch**

- Mehrere `Fatal`-Pfade beenden den Prozess; `defer cancel`/`Shutdown` laufen bei `os.Exit`-Semantik nicht zuverlässig.
- Temporäre HTTP-Server besitzen unvollständige Timeouts.
- Browserprozesse werden ohne `Wait` gestartet.
- Upstream-Response-Bodies werden teils unbegrenzt gelesen oder in Fehlertexte übernommen.
- File-Saves sind nicht crash-atomar.

**Empfehlung:** Einheitliche `run()`-Funktion mit `defer`-Cleanup, expliziten Timeouts, kontrollierten Prozessen, begrenzten Bodies und transaktionalem Credential-Commit verwenden.

### 6.6 Testabdeckung — **Mittel**

Im gesamten Scope existiert nur `internal/credentials/refresh_test.go`. Nicht abgedeckt sind insbesondere:

- vollständiger OAuth-CLI- und Callback-Lifecycle;
- State-Mismatch, Single-Use, Callback-Methoden und Shutdown;
- File-Permissions, Migration, atomaren Save und Environment-Refresh;
- konkurrierende Refreshes;
- Cloudflare-KV-Fehler-/Konsistenzszenarien;
- native und Workers-HTTP-Adapter;
- Project-Discovery-Timeouts, Failover und LRO-Grenzen;
- Logger-Runtime-Konfiguration und Redaction.

## 7. Priorisierte Maßnahmen

### Priorität 0

1. Hartcodierten OAuth-Client-Secret-Wert rotieren und aus Source/global veränderlichem State entfernen; Wert im Bericht nicht wiederholen.
2. `cmd/callback-server` nicht betreiben und aus dem Produktpfad entfernen; den funktionierenden Loopback-/PKCE-Fluss konsolidieren.
3. File-Credentials atomar und restriktiv speichern; Environment-Read-only-Refresh darf keinen Erfolg vortäuschen.
4. Project Discovery mit Deadline, Context, Runtime-korrektem HTTP-Client, Response-Limit und begrenztem Polling härten.
5. Worker-Startup bei fehlendem Provider/Binding fail-closed ausführen.

### Priorität 1

1. State im Callback serverseitig und zwingend prüfen; Callback nur Loopback, nur GET, einmalig und mit Server-Timeouts.
2. `--print` für Credential-Volldaten absichern oder entfernen.
3. Auth-Verifikation vor atomarem Persistieren eines neuen Credential-Satzes durchführen.
4. Refresh-Operationen durch Singleflight/Lock/Compare-and-Swap koordinieren und Refresh-/ID-Token-Rotation abbilden.
5. Native HTTP-Redirects für Tokenflüsse sperren und zentrale Limits/Timeouts durchsetzen.

### Priorität 2

1. Projekt-ID, Port, Tier, Environment-Leerwerte und Worker-Bindings validieren.
2. Logger für Worker über Runtime-Environment initialisieren und globale Zerolog-Mutationen entfernen.
3. Tests für Fehler-, Concurrency-, Permissions-, Runtime- und Ressourcen-Lifecycle ergänzen.
4. Logging auf Datensparsamkeit, Upstream-Fehlerbegrenzung und zentrale Redaction umstellen.

## 8. Audit-Grenzen

Die folgenden für Aufrufe relevanten Pakete lagen außerhalb der beauftragten Partition und wurden nicht vollständig analysiert:

- `internal/antigravity/` für Client, Token-Gültigkeitsprüfung, Endpoints und Header;
- `internal/server/` für HTTP-Routen, Request-Authentifizierung, Admin-/Google-Auth-Middleware, Request-Body-Limits, Shutdown und serverseitige Refresh-Intervalle;
- `cmd/callback-server/` ist zwar vollständig geprüft; seine Weiterleitung an `cmd/auth` bleibt mangels Builds/Starts bewusst unverifiziert.

Daher trifft der Bericht keine Aussage darüber, ob der laufende Proxy im Gesamtsystem durch Middleware geschützt ist, ob der Server Credential-Refresh serialisiert oder ob Outbound-HTTP-Aufrufe außerhalb dieses Scopes ebenfalls Limits besitzen. Die beschriebenen Risiken der geprüften Dateien bleiben davon unabhängig bestehen, sofern nicht ausdrücklich als Abhängigkeit markiert.
<!-- END PART E -->

## Anhang F — Antigravity-Proxy: Modelle, Transformation und Streaming

<!-- BEGIN PART F -->
## Partition F – statische Tiefenanalyse

## 1. Prüfrahmen und Abgrenzung

- **Arbeitsstand:** Git-HEAD `5a5b7b6ddeaeee9bfc2cdc719ef1839772ccb92f` als historischer Snapshot, Datum 2026-09-24; der F-Scope blieb nach diesem Commit unverändert.
- **Analysierter Scope ausschließlich:**
  - `llm-proxies/antigravity-proxy/internal/antigravity/`
  - `llm-proxies/antigravity-proxy/internal/openai/`
  - `llm-proxies/antigravity-proxy/internal/transform/`
- **Vollständig gelesen:** 21 Dateien / 4.345 Quellzeilen: 20 Go-Dateien (12 Produktionsdateien, 8 Testdateien) und 1 Prompt-Datei. Alle Zeilen wurden erfasst; der Scope war vor dem Schreiben dieses Berichts unveraendert.
- **Methode:** reine statische Analyse, Querverweis-/Patternprüfung und `gofmt -d`. Keine Prozessstarts, keine Tests, kein Netzwerk, keine Codeänderung, kein Zugriff auf Secret-Dateien und keine Ausgabe von Secret-Werten.
- **Formatprüfung:** `gofmt -d` lieferte keine Ausgabe; alle 20 Go-Dateien sind mindestens gofmt-/parse-konform.
- **Abgrenzung:** Der Brückencode zwischen den rohen SSE-Zeilen aus `internal/antigravity` und den `StreamChunk`s aus `internal/openai` liegt nicht in diesem Scope. Credential-Provider-Implementierungen und Server-Router wurden ebenfalls nicht untersucht. Aussagen zu deren Verhalten sind daher ausdrücklich auf die hier sichtbaren Verträge begrenzt.

## 2. Vollständigkeitsinventar

| Datei | Zeilen | Art |
|---|---:|---|
| `internal/antigravity/client.go` | 378 | Produktion |
| `internal/antigravity/client_auth_test.go` | 66 | Test |
| `internal/antigravity/constants.go` | 28 | Produktion |
| `internal/antigravity/generate_content_test.go` | 135 | Test |
| `internal/antigravity/models.go` | 81 | Produktion |
| `internal/antigravity/prompt.go` | 9 | Produktion/Embed |
| `internal/antigravity/request.go` | 413 | Produktion |
| `internal/antigravity/request_test.go` | 366 | Test |
| `internal/antigravity/schema.go` | 105 | Produktion |
| `internal/antigravity/schema_test.go` | 142 | Test |
| `internal/antigravity/system_prompt.txt` | 77 | Prompt |
| `internal/antigravity/thinking.go` | 45 | Produktion |
| `internal/antigravity/tools.go` | 226 | Produktion |
| `internal/antigravity/types.go` | 376 | Produktion/Schema-DTOs |
| `internal/openai/stream_transformer.go` | 388 | Produktion |
| `internal/openai/stream_transformer_test.go` | 696 | Test |
| `internal/openai/types.go` | 74 | OpenAI-DTOs |
| `internal/transform/openai_to_gemini.go` | 354 | Produktion |
| `internal/transform/openai_to_gemini_tool_test.go` | 127 | Test |
| `internal/transform/openai_to_gemini_test.go` | 148 | Test |
| `internal/transform/tool_parity_test.go` | 111 | Test |
| **Summe** | **4.345** | **vollständig** |

## 3. End-to-End-Verträge im sichtbaren Scope

### 3.1 OpenAI-Request → CloudCode-Request

1. `openai.ChatCompletionRequest` nimmt `model`, `messages`, `max_tokens`, `stream`, `temperature`, `tools` und `reasoning_effort` an (`internal/openai/types.go:3-12`).
2. `ToGeminiRequest` konvertiert Nachrichten, extrahiert Systeminstruktionen, konvertiert ausschließlich Function-Tools und setzt Model/Project/GenerationConfig (`internal/transform/openai_to_gemini.go:14-55`).
3. Rollenabbildung:
   - `system` → separates `SystemInstruction` (`internal/transform/openai_to_gemini.go:86-113`).
   - `user` → Gemini `user`.
   - `assistant` → Gemini `model`.
   - `tool` → Gemini `user` mit `FunctionResponse`.
   - unbekannte Rollen → stillschweigend `user` (`internal/transform/openai_to_gemini.go:115-125`).
4. Aufeinanderfolgende Tool-Ergebnisse werden zu genau einem User-Turn aggregiert; ein folgender Nicht-Tool-Turn oder das Request-Ende flusht die Queue (`internal/transform/openai_to_gemini.go:63-84`, `282-301`).
5. Assistant-Tool-Calls werden zu `FunctionCall`-Parts; Text und Calls können im selben Model-Turn liegen (`internal/transform/openai_to_gemini.go:246-280`).
6. Tool-Ergebnisse werden immer als `{"output": <string>}` verpackt (`internal/transform/openai_to_gemini.go:164-170`, `224-230`).
7. `reasoning_effort` wird getrimmt und uppercase als `ThinkingLevel` weitergereicht (`internal/transform/openai_to_gemini.go:29-38`).
8. `stream` beeinflusst die Transformation nicht; es wird nur als Request-Metadatum gespeichert und im sichtbaren Transformer separat entschieden.

### 3.2 Request-Normalisierung vor dem Upstream

`prepareAntigravityRequest` verändert den Request in-place (`internal/antigravity/request.go:14-65`):

- setzt `userAgent=antigravity` und `requestType=agent`;
- erzeugt bei Bedarf Request-/Session-ID;
- entfernt leere Parts/Contents;
- wendet Thinking-Regeln an;
- deckt Tool-Schemata ab;
- ergänzt fehlende Call-/Response-IDs;
- stellt die System Instruction neu zusammen;
- loggt den resultierenden Thinking-Zustand.

Danach wird der Wrapper mit Top-Level-Feldern `model`, `project`, `request`, optionalen Session-/Request-Metadaten als JSON an `/v1internal:generateContent` bzw. `/v1internal:streamGenerateContent?alt=sse` gesendet (`internal/antigravity/types.go:206-224`, `internal/antigravity/client.go:227-242`, `300-312`).

### 3.3 Thinking-Matrix

| Modellfall | Resultat |
|---|---|
| Exakt kodierte Level-Modelle | explizites `thinkingLevel` wird geleert (`request.go:107-140`) |
| Gemini-Modelle mit `-low/-medium/-high` (3.7/3.8 sind Testfälle) | Suffix überschreibt eingehendes Level (`thinking.go:9-45`) |
| Claude mit `none/off` | Budget 0, gesamte `ThinkingConfig` wird `nil` (`request.go:165-195`) |
| Claude `minimal/low` | Budget 1024 |
| Claude `medium` oder Default | Budget 2048 |
| Claude `high` | Budget 4096 |
| Claude mit positivem Custom-Budget | Budget bleibt erhalten, maximal 4096 |
| GPT-OSS | `ThinkingConfig` vollständig entfernt (`request.go:146-152`) |
| Alle übrigen Modelle | bei fehlendem Budget wird 10001 gesetzt (`request.go:196-201`) |
| `includeThoughts` | standardmäßig `true`, außer GPT-OSS; vorhandenes `false` bleibt bei aktivem Thinking erhalten |

`maxOutputTokens` wird nach der Thinking-Anpassung gemäß Modell ceiling auf 32.768 oder 65.536 begrenzt (`request.go:204-234`). Bei Claude wird ein zu kleiner Output-Bereich auf Thinking-Budget + 4.000 erhöht (`request.go:188-195`).

### 3.4 Schema-Vertrag

Der interne Gemini-Schema-DTO kennt ausschließlich `type`, `description`, `properties`, `items`, `required` und `enum` (`internal/antigravity/types.go:31-39`). `ConvertSchema` mappt genau diese Felder (`internal/antigravity/schema.go:60-104`).

- `type` darf String oder String-Array sein; das erste nicht-`null`-Element gewinnt (`schema.go:5-17`, `60-63`).
- Implizite Objekt-/Array-Typen werden ergänzt (`schema.go:85-102`).
- `anyOf` hat Vorrang vor `oneOf`; eine Array-Alternative gewinnt, sonst die erste nicht-null Alternative (`schema.go:26-58`).
- Parent-Beschreibung wird in die gewählte Alternative kopiert; dabei wird die übergebene Map mutiert (`schema.go:41-45`, `53-55`).
- Nicht unterstützte JSON-Schema-Verträge (`allOf`, `$ref`, `const`, numerische Grenzen, `additionalProperties`, `default`, `format`, Pattern, Min/Max-Längen usw.) werden verworfen.
- Enum und Required akzeptieren bei `ConvertSchema` nur Strings.

### 3.5 Tool-Verträge

- OpenAI-Tools werden nur bei `type == function` akzeptiert; Reihenfolge bleibt erhalten (`internal/transform/openai_to_gemini.go:305-348`).
- Fehlende oder nicht als `map[string]interface{}` lesbare Parameter werden zunächst `nil`; `prepareAntigravityRequest` ergänzt später ein leeres OBJECT-Schema (`internal/antigravity/request.go:44-49`).
- Raw-Tool-Formen akzeptieren Name/Description/Schema auf Top Level, unter `custom` oder `function`; Schemaquellen sind `input_schema`, `inputSchema` und `parameters` (`internal/antigravity/tools.go:134-186`).
- Raw-Tool-Namen werden getrimmt, auf `[A-Za-z0-9_-]` normalisiert und auf 64 Bytes gekürzt (`internal/antigravity/tools.go:200-225`).
- Direkt deklarierte FunctionDeclarations werden nicht namensnormalisiert (`internal/antigravity/types.go:55-60`).
- Native Google-Tools ohne ein nach diesem Parser verständliches Name/Schema-Feld werden nicht in FunctionDeclarations überführt.

### 3.6 Non-Streaming-Response

`generateContentInternal` liest die gesamte Antwort, akzeptiert ausschließlich HTTP 200, entpackt das Top-Level-Feld `response` in eine generische Map und setzt intern das tatsächlich bediente Modell (`internal/antigravity/client.go:245-275`, `types.go:369-376`). Im sichtbaren Scope existiert keine Transformation dieser Map in einen OpenAI-`ChatCompletionResponse`; die entsprechende Response-DTO liegt nur vor (`internal/openai/types.go:51-74`).

### 3.7 Streaming-Response

1. `StreamGenerateContent` sendet pro Scanner-Zeile unveränderten Text über `chan string`; der Bridge-Code zu `StreamChunk` liegt außerhalb dieses Scopes (`internal/antigravity/client.go:284-378`).
2. `CreateOpenAIStreamTransformer` konvertiert typisierte `StreamChunk`s in OpenAI-SSE (`internal/openai/stream_transformer.go:115-279`):
   - `text`/`thinking_content` → `delta.content`;
   - `real_thinking` → `delta.reasoning` und `delta.reasoning_content`;
   - `reasoning` → dieselben beiden Felder;
   - `tool_code` → `delta.tool_calls`;
   - `native_tool` → nicht standardisierte `delta.native_tool_calls`;
   - `grounding_metadata` → nicht standardisierte `delta.grounding`;
   - `usage` → nur Usage im finalen Chunk.
3. Jeder transformierte Strom endet immer mit einem Choice-Finish-Chunk und `data: [DONE]`, auch bei leerem Input (`stream_transformer.go:242-275`).

## 4. Priorisierte Befunde

### Hoch

#### F-01 – Request-Normalisierung ist nicht idempotent; 404-Fallback dupliziert den System Prompt

**Beleg:** `prepareAntigravityRequest` ruft bei jedem Versuch `buildAntigravitySystemInstruction` auf (`internal/antigravity/request.go:63`). Der Builder prependet den eingebetteten Prompt und hängt anschließend sämtliche bestehenden Text-Parts an (`internal/antigravity/request.go:236-252`). Beim ersten Versuch wird der originale System Instruction bereits umgebaut. Beim Fallback wird derselbe Request erneut vorbereitet (`internal/antigravity/client.go:215-222`, `287-295`, `227-230`, `300-303`).

**Ergebnis:** Der zweite Versuch enthält den Antigravity-Prompt doppelt; vorhandene Client-Systeminstruktionen erscheinen zusätzlich ein zweites Mal. Das betrifft Non-Streaming und Streaming. Sämtliche Prepare-Schritte laufen erneut; die System-Instruction-Transformation ist besonders sichtbar nicht idempotent.

**Testlücke:** Die Fallback-Tests erfassen nur das angeforderte Modell (`internal/antigravity/generate_content_test.go:85-121`), nicht `request.systemInstruction`, Tool-IDs oder übrige Body-Felder.

#### F-02 – Channel-Lifecycle ist im Kommentar und Verhalten widersprüchlich

**Beleg:** Der Kommentar verspricht, dass der Aufrufer den Channel-Lifecycle besitzt und die Funktion ihn nicht schließt (`internal/antigravity/client.go:284-287`). Die Erfolgsgoroutine schließt ihn mit `defer close(out)` (`client.go:354-358`). In allen Fehlerpfaden vor dieser Goroutine (`client.go:308-377`) wird er dagegen nicht geschlossen.

**Risiko:** Ein Aufrufer, der dem expliziten Vertrag folgt, kann einen erfolgreichen Stream doppelt schließen und dadurch einen Panic auslösen; bei Fehlern kann er hingegen auf ein Lifetime- und Finalisierungsproblem stoßen, wenn er den Channel nicht schließt.

#### F-03 – Reaktiver Auth-Refresh ist nicht koordiniert und nicht nil-sicher

**Beleg:** Proaktive Expiry-Refreshes sind über `refreshMu` doppelt geprüft (`internal/antigravity/client.go:104-125`). Der 401-Pfad ruft `RefreshToken` dagegen ohne dieses Lock und ohne erneute Tokenprüfung auf (`client.go:87-101`).

**Risiken:**
- parallele 401-Antworten können mehrere Refreshes gleichzeitig auslösen;
- liefert `GetCredentials` nil Credentials ohne Fehler, dereferenziert `doRequest` `creds.AccessToken` (`client.go:78`);
- nach Refresh wird `refreshedCreds.AccessToken` ohne Nil-/Leerprüfung dereferenziert (`client.go:96-101`);
- ein nil Provider wird weder bei Konstruktion noch Aufruf abgefangen.

**Testlücke:** Nur proaktiver Einzel-Refresh wird getestet (`internal/antigravity/client_auth_test.go:44-66`); 401, Nebenläufigkeit, Fehler, leere Credentials und nil-Responses fehlen.

#### F-04 – Info-Logs können sensible Request-/Response-Inhalte und Signaturen vollständig oder anteilig ausgeben

**Beleg:**
- Upstream-Streamfehler loggen bis zu 1.024 Bytes Response- und Request-Body (`internal/antigravity/client.go:327-343`).
- `UpstreamError.Error` enthält bis zu 1.024 Bytes Upstream-Body (`client.go:36-50`).
- Der OpenAI-Transformer loggt den kompletten `StreamChunk` und das komplette ausgehende SSE-Chunk auf Info-Level (`internal/openai/stream_transformer.go:131-134`, `234-237`).
- Thought Signatures werden separat geloggt (`stream_transformer.go:167-170`; `internal/transform/openai_to_gemini.go:257-265`).
- Tool-Ergebnisse werden bis 300 Zeichen inklusive Tool-ID geloggt (`openai_to_gemini.go:145-155`, `204-215`).

**Risiko:** Prompts, Tool-Argumente, Tool-Ergebnisse, Reasoning, Signaturen oder Fehlerantworten können in Logs landen. Der Bericht gibt keine solchen Werte wieder. Produktionsrelevante Logs sollten Metadaten statt Payloads verwenden und Thought Signatures niemals im Klartext loggen.

#### F-05 – Ungültige Tool-Argument-JSON werden stillschweigend zu `{}`

**Beleg:** Jeder JSON-Unmarshal-Fehler für Assistant-Historie wird ignoriert und durch eine leere Map ersetzt (`internal/transform/openai_to_gemini.go:246-252`).

**Risiko:** Ein fehlerhaftes oder noch fragmentiertes historisches Tool-Call-Argument wird als gültiger Empty-Args-Call an Gemini gesendet. Das kann Required-Argument-Verletzungen, falsche Tool-Ausführung oder schwer zu lokalisierende Upstream-Fehler erzeugen. Ein expliziter 4xx-Validierungsfehler wäre sicherer.

**Testlücke:** Kein Test mit malformed, leerem, partiell gestreamtem oder Nicht-Objekt-Argument. Valides JSON `null` nimmt einen anderen stillen Pfad: `args` bleibt `nil` und wird durch `omitempty` gar nicht serialisiert.

#### F-06 – Stream-Abbruch/-Scannerfehler ist nicht von erfolgreicher Beendigung unterscheidbar

**Beleg:** Scannerfehler werden nur geloggt; die Goroutine beendet den Body und schließt den Channel (`internal/antigravity/client.go:354-369`). Der OpenAI-Transformer interpretiert das Ende eines beliebigen geschlossenen Input-Channels als reguläres Ende und sendet Finish plus `[DONE]` (`internal/openai/stream_transformer.go:242-275`).

**Risiko:** Wenn der externe Bridge-Code den geschlossenen Kanal in den Transformer leitet, kann ein nach Partial Output abgerissener Stream oder ein wegen einer zu großen SSE-Zeile abgebrochener Stream als erfolgreich abgeschlossen erscheinen. Es gibt weder Fehler-SSE noch Fehler-Metadatum und keinen Retry-Zustand.

### Mittel

#### F-07 – Tool-Streaming bildet weder Fragmente noch mehrere Calls vollständig OpenAI-konform ab

**Beleg:** Jeder `tool_code`-Chunk erhält eine neue zufällige ID und immer `Index: 0` (`internal/openai/stream_transformer.go:164-184`). Es gibt keinen Aggregationszustand pro Call, keinen steigenden Index und keine Wiederherstellung einer Gemini-Call-ID; `GeminiFunctionCall` besitzt überhaupt kein ID-Feld (`stream_transformer.go:24-29`).

**Risiken:**
- mehrere eigenständige Tool-Calls sind clientseitig nicht eindeutig über `index` unterscheidbar;
- ein Call über mehrere Argumentfragmente erzeugt mehrere neue Calls;
- `finish_reason=tool_calls` merkt sich nur, dass irgendein Tool-Call kam (`stream_transformer.go:242-246`);
- der Map-Pfad verlangt Name und non-nil Args, der direkte Struct-Pfad akzeptiert dagegen leere Namen und nil Args (`stream_transformer.go:308-334`);
- Fehler beim Marshaling der Args werden ignoriert und können als leerer Argumentstring in einen scheinbar gültigen Call gelangen (`stream_transformer.go:173-184`).

**Testlücke:** Nur ein Call in einem Chunk (`stream_transformer_test.go:158-246`, `473-483`); keine Fragmentierung, zwei Calls, Call-Index, ID-Übergabe oder identische Calls.

#### F-08 – Thought-Signature wird als OpenAI-ID-Payload transportiert

**Beleg:** Die Signatur wird mit `|` an die Tool-Call-ID angehängt (`stream_transformer.go:166-171`). Beim Zurückkonvertieren wird am ersten `|` getrennt und der Rest als Signatur interpretiert (`internal/transform/openai_to_gemini.go:253-272`).

**Risiken:** Die OpenAI-ID verlässt das übliche opaque-ID-Format; Größe und Zeichen werden nicht validiert; eine Signatur mit `|` wird verkürzt; die Signatur wird außerdem im Log offengelegt. Für den Signatur-Roundtrip existiert in Partition F kein Test.

#### F-09 – Raw-/Mixed-Tools werden teilweise stillschweigend verworfen

**Beleg:** Sobald ein Tool-Array mindestens eine FunctionDeclaration enthält, wird das gesamte Array sofort übernommen (`internal/antigravity/types.go:261-277`). Weitere Raw-, Custom- oder Native-Tools in diesem Array werden nicht konvertiert. `convertRawTools` liefert selbst dann Erfolg mit nil Tools, wenn keine FunctionDeclaration gebaut werden konnte (`internal/antigravity/tools.go:10-28`, `300-303`).

**Risiko:** Gemini-interne Function-Tools können funktionieren, während gleichzeitig deklarierte Native-/Custom-Tools verschwinden. Der Request erscheint erfolgreich, verliert aber Werkzeugfunktionalität. Nicht-`custom.map` Native-Tools werden nicht einmal statistisch als Custom gezählt (`tools.go:115-131`).

**Testlücke:** Keine Raw-Tool-, Mixed-Tool-, Custom-/Native-Tool- oder Schema-Quellen-Paritätstests.

#### F-10 – Direkt deklarierte Schemas werden anders und potenziell unnormalisiert verarbeitet

**Beleg:** `FunctionDeclaration.UnmarshalJSON` verwendet zunächst das Alias-Unmarshal und fällt bei fehlendem `parameters` auf Raw-Manipulation zurück (`internal/antigravity/types.go:62-100`). Dabei wird `GeminiParameterSchema` direkt befüllt; `ConvertSchema` mit Uppercase-Normalisierung wird nur für Raw-Tool-Payloads verwendet (`types.go:300-303`, `tools.go:77-90`).

**Risiken:**
- JSON-Schema-Kleinschreibung bleibt bei direktem `parametersJsonSchema`/`parameters` möglicherweise klein, während Raw-Konvertierung uppercase liefert;
- nicht-string Enum-/Required-Werte können den Direkt-Unmarshal scheitern lassen; mehrere Fehler werden danach ignoriert (`types.go:79-97`);
- alle nicht im kleinen DTO enthaltenen JSON-Schema-Keywords gehen verloren;
- camelCase und snake_case können gleichzeitig vorhanden sein, ohne Konfliktprüfung; camelCase gewinnt.

**Testlücke:** Keine Tests für `FunctionDeclaration.UnmarshalJSON`, `Tool.UnmarshalJSON`, `parametersJsonSchema`, snake_case, mixed keys, falsche Typen oder numerische Enums.

#### F-11 – Schema-Unionen sind bewusst verlustbehaftet und mutieren Input

**Beleg:** Array-Alternative gewinnt unabhängig von Position; nur die erste andere Alternative ist Fallback (`internal/antigravity/schema.go:26-58`). Parent-Description überschreibt die Description der gewählten Submap (`schema.go:41-45`, `53-55`).

**Risiken:** `anyOf`/`oneOf` werden nicht als Alternativenvertrag erhalten; Parent-Constraints gehen verloren. Der Aufrufer verliert seine Input-Map durch seitliche Mutation. Der Test codiert Array-Priorität, prüft aber weder Parent-Required noch Mutation (`schema_test.go:83-123`; `internal/transform/openai_to_gemini_test.go:43-110`).

#### F-12 – DTO-Vertrag und Transform-Acceptance widersprechen sich für Array-Content

**Beleg:** `Message.Content` dokumentiert String **oder** `[]ContentPart` (`internal/openai/types.go:14-18`). Der Transform akzeptiert aber nur `string` und `[]interface{}` (`internal/transform/openai_to_gemini.go:95-111`, `127-244`).

**Folge:** Programmatisch korrekt als `[]openai.ContentPart` gesetzter Content fällt in `default` und wird vollständig ignoriert. JSON-decodierte Requests funktionieren, weil `encoding/json` in `interface{}` `[]interface{}` erzeugt; der öffentliche Go-Vertrag ist damit enger als die Kommentarzusage.

#### F-13 – Nicht-Text- und strukturierte Tool-Inhalte verschwinden ohne Fehler

**Beleg:** User-/Assistant-Array-Content akzeptiert ausschließlich `type == "text"`; Bild-/Audio-/File-Parts werden ignoriert (`internal/transform/openai_to_gemini.go:177-241`, ausdrücklich TODO in Zeile 239). Tool-Inhalte in Number-, Boolean-, Object-, Array- oder typisiertem Struct-Form werden über denselben `default`-Zweig verworfen (`openai_to_gemini.go:127-244`).

**Risiko:** Tool-Ergebnisse können kommentarlos als leerer String bzw. ganz ohne Part ankommen. Bei multimodalen Requests entsteht semantischer Datenverlust ohne 4xx.

#### F-14 – Assistant-Rolle kann im Stream fehlen oder zu spät kommen

**Beleg:** `firstChunk` wird nur für `text`, `thinking_content` und `tool_code` aufgelöst (`internal/openai/stream_transformer.go:138-193`). `real_thinking`, `reasoning`, `native_tool` und `grounding_metadata` setzen keine Rolle (`stream_transformer.go:150-206`).

**Folge:** Ein reasoning-first-Stream beginnt ohne `role=assistant`; ein ausschließlich aus Reasoning/Native-Tool/Grounding bestehender Stream enthält nie eine Assistant-Rolle. Das ist mit den OpenAI-Deltas nicht konsistent und nur für text/tool getestet.

#### F-15 – Thinking-Verträge sind uneinheitlich und teilweise semantisch mehrdeutig

**Beleg:**
- `thinking_content` wird als sichtbarer Content ausgegeben (`stream_transformer.go:138-148`).
- `real_thinking` und `reasoning` werden gleichzeitig in zwei Reasoning-Felder geschrieben (`stream_transformer.go:150-162`).
- `ReasoningData.ToolCode` wird geparst, aber nicht in das Delta übertragen; ein Reasoning-Objekt mit nur `toolCode` erzeugt daher zwei leere Reasoning-Felder statt eines Tool-Code-Deltas (`stream_transformer.go:18-22`, `157-162`, `283-306`).
- Claude deaktiviert bei Budget 0 die gesamte ThinkingConfig und damit auch explizite IncludeThoughts-Semantik (`internal/antigravity/request.go:165-195`).

**Risiken:** Clients, die beide Reasoning-Aliase lesen, können Inhalte doppelt verarbeiten; Tool-Code geht verloren; sichtbares und verborgenes Denken sind nicht klar getrennt. Nur einfache/contentseitige Fälle sind getestet.

#### F-16 – Tatsächlich bedientes Fallback-Modell ist im Streaming nicht mitteilbar

**Beleg:** Non-Streaming setzt `GenerateContentResponse.Model` auf das tatsächlich verwendete Modell (`internal/antigravity/client.go:267-275`). Streaming kennt nur `error` und Rohzeilen; es gibt keine Model-Mitteilung (`client.go:284-298`). Der OpenAI-Transformer verwendet ausschließlich den bei Konstruktion übergebenen Modellnamen (`stream_transformer.go:118-126`, `217-222`).

**Folge:** Nach 3.7/3.8-Fallback kann ein Stream weiter den angeforderten, nicht den tatsächlich bedienten Modellnamen melden. Non-Streaming und Streaming haben unterschiedliche Observability-Verträge.

#### F-17 – Retry/Auth ist auf Proactive-Expiry, einmaligen 401-Replay und 404-Modell-Fallback begrenzt

**Beleg:** Authpfad `client.go:72-125`; 404-Fallback `client.go:202-225`, `284-298`; Endpoint-Schleifen `client.go:161-199`, `235-281`, `308-377`. `Endpoints` enthält aktuell nur einen Eintrag (`constants.go:16-18`).

**Fehlend:** Keine Backoff- oder Retry-Policy für 408/429/5xx, Netzfehler nach Verbindungsaufbau, unterbrochene Streams oder Scannerfehler; keine Jitter-/Retry-After-Auswertung. `generateContentInternal` und `LoadCodeAssist` ignorieren Client-Kontext und nutzen `context.Background()` (`client.go:164`, `238`).

#### F-18 – Unbegrenztes Response-Lesen und begrenzte SSE-Zeilenlänge erzeugen unterschiedliche Druckrisiken

**Beleg:** Non-Streaming und Fehlerpfade verwenden unbeschränktes `io.ReadAll` (`client.go:171`, `245`, `319`; `models.go:51-53`). Streaming erlaubt maximal 1 MiB pro Scannerzeile (`client.go:359-362`).

**Folge:** Ein einzelner großer JSON-Fehler-/Success-Body kann Speicher belasten; eine einzelne größere SSE-Datenzeile wird stillschweigend abgeschnitten, nur geloggt und anschließend als normaler Kanalabschluss dargestellt. Keine Tests für Grenzwerte.

#### F-19 – Nil- und Identitätsvalidierung fehlt an zentralen Einstiegen

**Beleg:** Sowohl `ToGeminiRequest` (`internal/transform/openai_to_gemini.go:15-20`) als auch `GenerateContent`/`StreamGenerateContent` (`internal/antigravity/client.go:214-217`, `287-290`) dereferenzieren Eingaben ohne Nil-Guard. Leere Funktionsnamen, unbekannte Tool-Typen, leere Content-Listen und leere Modelle werden nicht validiert.

**Folge:** Programmierfehler können Panics oder schlecht validierte Upstream-Requests erzeugen; bei einem 404 mit nil Request wäre die Fallback-Auswertung selbst nil-unsafe.

#### F-20 – Rollen- und Systeminstruktions-Vertrag ist enger als moderne OpenAI-Semantik

**Beleg:** Nur exakt `system` wird extrahiert; `developer` fällt in die Default-User-Rolle (`openai_to_gemini.go:74-125`). Der eingebettete Prompt enthält harte macOS-/Benutzerpfade und web-app-spezifische globale Regeln (`system_prompt.txt:7-69`). Der Builder setzt die zusammengeführte Instruktion auf Rolle `user` und stellt den Embedded Prompt vor die Client-Instruktion (`request.go:236-252`). Der `<user_rules>`-Block bleibt leer (`system_prompt.txt:74-77`).

**Risiken:** Developer-Systemrollen werden zu normalem User-Content; stale Persona-/Pfadangaben werden allen Requests aufgedrückt; globale Designregeln können unrelated Coding-Aufgaben beeinflussen; Client-Regeln stehen nicht innerhalb des angekündigten `<user_rules>`-Blocks.

#### F-21 – Stream-Finish wird erfunden; Upstream-Abschlusszustände können nicht erhalten bleiben

**Beleg:** `StreamChunk` besitzt nur `type` und `data` (`internal/openai/stream_transformer.go:12-16`). Der Transformer leitet aus irgendeinem Tool-Call `tool_calls`, sonst `stop` ab und sendet bei leerem Input ebenfalls `stop` (`stream_transformer.go:242-275`). Es gibt keine Repräsentation für `length`, Safety-/Content-Filter, Upstream-Fehler, max tokens oder Abbruch.

**Risiko:** Ein fachlich beendeter, blockierter oder unvollständiger Upstream-Stream kann clientseitig als normaler `stop` erscheinen. Die einzigen getesteten Finish-Fälle sind `stop` und `tool_calls` (`stream_transformer_test.go:459-515`).

#### F-22 – Call→Response-ID-Fallback ist bei parallelen gleichen Funktionsnamen mehrdeutig

**Beleg:** `toolCallIDByName` speichert pro Name nur eine ID; jede spätere Call-Definition desselben Namens überschreibt den vorherigen Wert (`internal/transform/openai_to_gemini.go:60-63`, `267-270`). Dieser Fallback wird bei Toolresultaten ohne ID verwendet (`openai_to_gemini.go:157-162`, `217-221`). Im Antigravity-Normalizer bleibt eine Response ohne passende Pending-ID unverändert; explizite IDs werden weder auf Existenz noch auf passenden Namen geprüft (`internal/antigravity/request.go:302-358`).

**Risiko:** Bei parallelen Calls mit demselben Funktionsnamen und resultierenden Toolnachrichten ohne ID kann eine Response der falschen Call-ID zugeordnet oder leer weitergereicht werden. Der Paritätstest sammelt Response-IDs, prüft sie aber nicht (`internal/transform/tool_parity_test.go:92-110`).

#### F-23 – Der OpenAI-Requestvertrag verwirft moderne Felder stillschweigend

**Beleg:** `ChatCompletionRequest` kennt nur `max_tokens`, Messages, Model, Stream, Temperature, Tools und ReasoningEffort (`internal/openai/types.go:3-12`). Der Transform wertet ausschließlich diese Felder aus (`internal/transform/openai_to_gemini.go:27-45`, `305-348`).

**Nicht abgebildet:** insbesondere `max_completion_tokens`, `stream_options`, `tool_choice`, `parallel_tool_calls`, `top_p`, Stop-Sequenzen, `response_format`, `n`, Seed und Penalties. Da unbekannte JSON-Felder stillschweigend verworfen werden, kann ein gültiger moderner OpenAI-Request mit anderer Semantik erfolgreich verarbeitet werden.

### Niedrig

#### F-24 – `ApplyHeaders` ignoriert seinen `accept`-Parameter

**Beleg:** Signatur und Aufruf übergeben Accept (`constants.go:24`, `client.go:72`, `127`), aber der Header wird nie gesetzt (`constants.go:24-28`). Der Test codiert ausdrücklich, dass Accept leer bleibt (`request_test.go:299-320`).

**Bewertung:** Der vorhandene Test fixiert dieses Verhalten; es kann CLI-Parität sein, ist aber kein allgemeiner HTTP-Vertrag. Streaming hängt derzeit ausschließlich an Query `alt=sse` und Chunked Transfer.

#### F-25 – Missing-Name-Logs werden nach dem Auffüllen erzeugt und sind daher leer

**Beleg:** `fillMissingParameters` setzt Parameters zuerst (`types.go:325-338`); `missingParameterNames` sucht anschließend nur noch `Parameters == nil` (`types.go:340-356`). Dasselbe geschieht im Prepare-Pfad (`request.go:44-49`).

**Folge:** `missing_names` ist bei den vorgesehenen Warnungen typisch leer und damit operativ nutzlos.

#### F-26 – Raw-Tool-Namensnormalisierung kann kollidieren; OpenAI-Pfad normalisiert nicht

**Beleg:** Raw-Namen werden zeichenweise ersetzt/gekürzt (`tools.go:200-225`); der normale OpenAI-Tool-Pfad übernimmt Namen unverändert (`openai_to_gemini.go:321-325`). Es gibt keine Duplikatprüfung.

**Folge:** Verschiedene Namen können nach Normalisierung kollidieren; dieselbe Tool-Namensform verhält sich abhängig von Payload-Form unterschiedlich.

#### F-27 – Leere oder negative Usage-Maps werden als gültige Usage akzeptiert

**Beleg:** Jede Map wird als `UsageData` zurückgegeben, selbst ohne Tokenfelder; Werte werden nicht validiert (`stream_transformer.go:336-362`).

**Folge:** Fehlende Felder erzeugen einen finalen Usage-Chunk mit Nullwerten; negative Werte werden unverändert übernommen. Der Test deckt nur int, float, direkten Struct und nil ab (`stream_transformer_test.go:597-645`).

#### F-28 – Modell-Cache ist ein stundenlanger Pointer-Cache ohne Singleflight oder Kopie

**Beleg:** Cache-Hit gibt internen Pointer direkt zurück; nur Cache-Fill ist gelockt (`internal/antigravity/models.go:30-36`, `69-74`).

**Risiko:** Aufrufer können den Cache mutieren; parallele Cache-Misses führen zu mehreren Upstream-Requests. `QuotaInfo` bleibt Raw JSON, DisplayName wird bewusst nicht als API-Identität verwendet. Keine Tests in Partition F.

#### F-29 – Fallback-Modellvergleich ist bei anderer Groß-/Kleinschreibung redundant

**Beleg:** `modelLower` wird kleingeschrieben, der Vergleich mit dem exakt kleingeschriebenen Tiered-Modell jedoch gegen das Original ausgeführt (`internal/antigravity/client.go:202-210`).

**Folge:** Ein bereits tiered benanntes Modell in anderer Schreibweise kann bei 404 ein semantisch identisches Modell erneut angefordert werden. Kein Test für case-insensitive Idempotenz.

## 5. Datei-/Zeilenbericht

### 5.1 `internal/antigravity/constants.go` (1–28)

- **1–7:** Paket/Imports; keine fachliche Transformation.
- **9–14:** Ein fester CloudCode-Host, statische CLI-Version, Request User-Agent/Request Type.
- **16–18:** Exportierbare, veränderbare Endpoint-Slice; derzeit genau ein Endpoint.
- **20–22:** Plattformabhängiger User-Agent aus OS/Arch und statischen Client-Metriken.
- **24–28:** Setzt Bearer-Authorization, JSON Content-Type und User-Agent. `accept` wird nicht angewandt; siehe F-24.

### 5.2 `internal/antigravity/types.go` (1–376)

- **1–9:** Paket/Imports.
- **11–29:** Gemini Content/Part/SystemInstruction; Text, ThoughtSignature, FunctionCall und FunctionResponse können formal gleichzeitig vorhanden sein.
- **31–39:** Begrenzter Gemini-Schemavertrag; keine Formate, Constraints, Defaults, nullable oder Union-Struktur.
- **41–53:** Call-/Response-DTOs; Args/Response sind generische Maps.
- **55–60:** FunctionDeclaration ohne ID- und Namensvalidierung.
- **62–100:** Custom Unmarshal für `parametersJsonSchema` (camelCase) und `parameters` (snake_case); Raw-Unmarshal-Fehler für Name, Description und Schemas werden mehrfach ignoriert.
- **102–141:** Tool-Unmarshal für camelCase/snake_case FunctionDeclarations; leere oder nicht vorhandene Deklarationen werden verworfen.
- **143–159:** ThinkingConfig mit Level/Budget/IncludeThoughts; GenerationConfig.
- **161–204:** LoadCodeAssist Request/Response, Tier und Credit.
- **206–224:** CloudCode-Wrapper und innere GeminiRequest-Struktur.
- **226–314:** Flexible GeminiInternalRequest-Unmarshal:
  - **230–249:** Felder und Session-ID camel/snake;
  - **251–255:** absent/null Tools;
  - **257–277:** Array mit FunctionDeclarations, Parameterdefault;
  - **280–298:** einzelnes Tool-Objekt;
  - **300–303:** Raw-Tool-Konvertierung;
  - **305–313:** strikter Fallback.
- **316–367:** Function-Deklarationsprüfung, Parameterdefault, Warnlisten und 400-Byte-Raw-Preview.
- **369–376:** generische Response-Map plus intern markiertes Served-Model.

### 5.3 `internal/antigravity/system_prompt.txt` (1–77)

- **1–6:** Identity/Paired-Programming-Vertrag.
- **7–13:** Hartcodiertes macOS, lokaler Benutzerpfad, Workspace und App-Data-Verzeichnis.
- **14–69:** HTML/JS/CSS/Framework-Regeln, Designästhetik, Workflow und SEO; global und ohne Taskbezug. Enthält sichtbare Listenfehler (`Technologies:,`, viele trailing commas, doppelte Nummer 4) und „Javascript“-Schreibweise.
- **70–73:** `EPHEMERAL_MESSAGE`-Semantik.
- **74–77:** `user_rules` wird angekündigt, enthält aber keine Regeln; Client-Systemtext wird als separater Part außerhalb dieses Blocks angehängt.

### 5.4 `internal/antigravity/schema.go` (1–105)

- **1–3:** Imports.
- **5–17:** Typstring-/`[]interface{}`-Extraktion, ignoriert `null`.
- **19–58:** `anyOf`/`oneOf`; Array-Priorität, Description-Merge und mutierende Submap-Auswahl.
- **60–83:** Type/Description/Required/Enum; nur passende Stringwerte.
- **85–102:** rekursive Properties/Items und implizite Typen.
- **104:** Rückgabe; alle übrigen JSON-Schema-Keywords sind bewusst nicht Teil des Vertrags.

### 5.5 `internal/antigravity/request.go` (1–413)

- **1–12:** Imports.
- **14–65:** zentrale in-place Prepare-Pipeline in fester Reihenfolge; Prompt-Duplikationsbefund F-01.
- **67–105:** Thinking-Logging ohne Payload-Inhalte; protokolliert Modell und Konfigurationszustand.
- **107–140:** harte Liste modellkodierter Thinking-Level und Clear-Logik.
- **142–202:** Claude-/GPT-OSS-/Gemini-Defaults, Claude-Budget-Matrix, IncludeThoughts, Output-Anhebung.
- **204–234:** Modell ceilings und Clamp.
- **236–253:** nicht-idempotenter SystemInstruction-Rebuild; bestehende non-empty Text-Parts, Rolle `user`.
- **255–259:** Request-ID `agent/<uuid>/<millis>/<uuid>/1`.
- **261–283:** Session-ID aus erstem User-Text oder neuer UUID.
- **285–300:** ergänzt fehlende FunctionCall-IDs.
- **302–371:** komplexe Call→Response-ID-Zuordnung nach Name/FIFO; explizite IDs werden konsumiert, aber nicht auf Existenz/Name/Pairing validiert.
- **373–406:** entfernt leere Contents und Parts.
- **408–413:** leere Text-/Signatur-Parts; eine reine ThoughtSignature ohne Call/Response wird als leer entfernt.

### 5.6 `internal/antigravity/generate_content_test.go` (1–135)

- **15–68:** Stub-Credentials und HTTP-Client; erfasst nur Top-Level-Request-Modell.
- **70–83:** erfolgreiches Modell meldet Served Model.
- **85–103:** 3.7-Fallback und Reihenfolge.
- **105–121:** 3.8-Fallback und Reihenfolge.
- **123–135:** kein Fallback für andere Modelle.
- **Lücke:** keine Body-/Prompt-/Header-/Auth-/Response-Inhaltsprüfung, kein nil Request, keine Non-200-Unterscheidung jenseits 404.

### 5.7 `internal/antigravity/tools.go` (1–226)

- **1–8:** Imports.
- **10–49:** Raw-Tool-Konvertierung, Logging und Single-Tool-Ergebnis.
- **51–63:** Array oder Object als Map-Liste.
- **65–94:** verständliche Raw-Felder zu FunctionDeclaration; Default-OBJECT.
- **96–132:** Toolstatistiken und Namensvorschau; native Nicht-Custom-Tools bleiben unklassifiziert.
- **134–170:** Feldauflösung Top Level → `custom` → `function`, anschließend Namenssanitizing.
- **172–186:** nur `input_schema`, `inputSchema`, `parameters`.
- **188–198:** Stringfeld-Helfer.
- **200–226:** ASCII-Name-Normalisierung und 64-Byte-Kürzung.

### 5.8 `internal/antigravity/client.go` (1–378)

- **1–19:** Imports.
- **21–51:** UpstreamError und Fehlertext mit Body-Preview.
- **53–70:** Client mit HTTP-/Credential-Provider, Refresh- und Model-Cache-Locks.
- **72–102:** Credentials, 401-Body-Close, Refresh/Replay; keine Lock-/Nil-Härtung.
- **104–125:** double-checked Proactive-Expiry-Refresh mit 5-Minuten-Fenster.
- **127–146:** Requestbau, Header, Host, Streaming-Chunked, HTTP-Ausführung.
- **148–200:** LoadCodeAssist; Background-Kontext, Endpoint-Schleife, Vollbody-Read, JSON-Parsing.
- **202–211:** 3.7/3.8-Tiered-Fallbackauswahl.
- **213–225:** öffentliche Non-Stream-Fallback-Orchestrierung.
- **227–282:** Prepare, Marshal, Background-Request, Vollbody-Read, UpstreamError, Served Model.
- **284–298:** öffentliche Streaming-Fallback-Orchestrierung.
- **300–378:** Streamingrequest, Fehlerbody/Logs, Erfolgsgoroutine, 1-MiB-Scannergrenze, Channelclose, nur protokollierter Scannerfehler.

### 5.9 `internal/antigravity/request_test.go` (1–366)

- **11–60:** CLI-Request-/SystemInstruction-Grundform.
- **62–82:** Default IncludeThoughts/Budget.
- **84–122:** Level-Clear für vier kodierte Modelle einschließlich Beibehalt von IncludeThoughts=false.
- **124–137:** GPT-OSS-Strip.
- **139–153:** 3.7 High-Preset.
- **155–197:** 3.8 Suffix-Default und Suffix-Override.
- **199–224:** Preservation expliziter Gemini-Thinkwerte.
- **226–262:** Output-Clamp-Matrix.
- **264–297:** PaidTier/Credit-Parsing.
- **299–321:** Header und absichtlich leerer Accept.
- **323–366:** Claude Low/Minimal/Medium/High/Default plus Output-Budget-Beziehung.
- **Lücken:** Claude none/off, Custom-Budget-Cap, Fallback-Idempotenz, Content-Sanitizing, Session-/ID-Pairing, Raw-/Mixed-Tools, Systeminstruction-Duplikat, Output/Thinking-Interaktion an Modellgrenzen.

### 5.10 `internal/antigravity/thinking.go` (1–45)

- **9–17:** nur Gemini-Modelle.
- **19–30:** Suffixerkennung Low → Medium → High in dieser Priorität.
- **32–45:** Logging und Erzeugen/Setzen der ThinkingConfig; überschreibt Client-Level auch für 3.8-Suffixmodelle.

### 5.11 `internal/antigravity/schema_test.go` (1–142)

- **8–123:** acht Schema-Fixtures: einfacher String, typisierte Nullable-Varianten, implizites Object/Array, `anyOf` String/Null und Array-Priorität.
- **125–142:** JSON-Vergleich.
- **Lücken:** `oneOf` in diesem Paket, `allOf`, Ref/Composition, zusätzliche Constraints, nicht-string Enums/Required, non-map/typed inputs, Inputmutation.

### 5.12 `internal/antigravity/prompt.go` (1–9)

- **3:** Blank-Import für Embed.
- **5–9:** exportierte, zur Laufzeit veränderbare Stringvariable mit `go:embed system_prompt.txt`; der Request-Builder verwendet später einen per Trim bereinigten Wert.

### 5.13 `internal/antigravity/client_auth_test.go` (1–66)

- **11–42:** threadsicherer Credential-Provider-Stub.
- **44–66:** einzelner proaktiver Refresh eines in einer Minute ablaufenden Tokens.
- **Lücken:** 401-Replay, konkurrierende Refreshes, Fehlerfälle, nil/leer/kein Expiry, Save/Get-Fehler.

### 5.14 `internal/antigravity/models.go` (1–81)

- **12–28:** Model-Map, Default-Agent-ID, DisplayName und Raw QuotaInfo; Kommentar begründet ID statt DisplayName als Client-Key.
- **30–36:** einstündiger RWMutex-Cache-Hit mit direktem Pointerreturn.
- **38–75:** Request, Endpoint-Schleife, Vollbody, Parsing, Cache-Fill.
- **77–80:** letzter Fehler/no endpoints.
- **Lücken:** alle Model-Cache-, Quota-, Context- und Fehlerpfade.

### 5.15 `internal/openai/types.go` (1–74)

- **3–12:** unterstütztes Request-Feldsegment; moderne Felder wie `max_completion_tokens`, `stream_options`, `tool_choice` und `response_format` fehlen ebenso wie Top‑P/Stop/Seed/Penalties und Multimodal-Metadaten. Die `developer`-Rolle wird später nicht als Systemrolle behandelt.
- **14–30:** Message mit generischem Content, ToolCalls, ToolCallID und Name.
- **32–36:** ContentPart nur Type/Text, obwohl der Kommentar `[]ContentPart` verspricht.
- **38–49:** Tool/Function; Parameter bleiben `interface{}`.
- **51–74:** Non-Streaming-Response/Choice/Usage; Usage ist immer vorhanden und serialisiert Nullwerte, wenn upstream keine Usage hatte.

### 5.16 `internal/openai/stream_transformer.go` (1–388)

- **1–10:** Imports.
- **12–113:** Gemini-/OpenAI-interne Stream-DTOs, Extensions für Native Tools/Grounding und Chunk-Shape. `Usage` ohne omitempty erzeugt `usage:null` in normalen Chunks.
- **115–129:** Transformer, Chat-ID/Zeit, First-State, letzte Tool-ID, Usage.
- **131–148:** Chunk-Logging; Text/ThinkingContent als Content und optionale erste Rolle.
- **150–162:** Real Thinking/Reasoning in zwei Feldern; ToolCode verworfen.
- **164–194:** Tool-Call, zufällige ID, optionale Signatur im ID, JSON Args, Index 0, optionale erste Rolle.
- **196–214:** Native Tool/Grounding/Usage.
- **216–239:** OpenAI-Chunk, stilles Ignorieren von Marshal-Fehlern, vollständiges SSE-Logging.
- **242–275:** statischer Finish `stop/tool_calls`, optionale Usage und immer `[DONE]`.
- **281–306:** Reasoning-Konvertierung.
- **308–334:** FunctionCall-Konvertierung; direkte Structs werden ohne Feldvalidierung akzeptiert.
- **336–363:** Usage-Konvertierung; leere Map akzeptiert.
- **365–388:** Native-Tool-Konvertierung; Type und Data-Nichtnil erforderlich.

### 5.17 `internal/openai/stream_transformer_test.go` (1–696)

- **9–63:** Basic Text, Modell, Role, Text, DONE.
- **65–92:** `thinking_content` als sichtbarer Content.
- **94–121:** `real_thinking.reasoning`.
- **123–156:** Reasoning-Map.
- **158–246:** ein Tool-Call; Role, Name, ID-Präfix, Type, optionaler Finish.
- **248–283:** Native Tool-Anzahl.
- **285–317:** Grounding vorhanden.
- **319–369:** Float-Usage im Final.
- **371–432:** mehrere Textchunks und genau eine Role.
- **434–457:** leerer Input endet mit Final/DONE.
- **459–515:** Stop vs. Tool Calls.
- **517–696:** Helper-Tests für Reasoning, FunctionCall, Usage und Native Tool.
- **Lücken:** ID/Args exakt, Signaturroundtrip, fragmentierte/mehrere Calls, Index, reasoning-first Role, Alias-Duplikation, ToolCode, native/grounding Role, leere/negative Usage, unbekannte Typen, Marshalfehler, Backpressure/Cancellation.

### 5.18 `internal/transform/openai_to_gemini.go` (1–354)

- **1–12:** Imports.
- **14–55:** Top-Level-Conversion; kein nil guard, Stream unused, GenerationConfig-Bedingung, Reasoning uppercase, Project/Model.
- **57–72:** Pre-Index der Call-ID→Name-Beziehung.
- **74–113:** Queue-Flush, Systemextraktion, String/`[]interface{}`-Systemcontent.
- **115–127:** Rollenabbildung inklusive Unknown→User.
- **127–176:** String-Content und String-Tool-Response, Pipe-ID-Bereinigung, Nameauflösung, ID-Fallback, Payload-Logging.
- **177–231:** Array-Content und Array-Tool-Response, Textaggregation.
- **232–244:** nur Textparts; alle anderen Inhalte stillschweigend verworfen.
- **246–280:** Assistant ToolCalls, JSON-Fallback `{}`, ID/ThoughtSignature-Roundtrip, Name-Maps.
- **282–303:** Tool-Run-Flush und abschließender Queue-Flush.
- **305–348:** nur Function-Tools; map-basierte Schemaextraktion; keine Namensvalidierung.
- **350–354:** direkter Delegationswrapper zu `antigravity.ConvertSchema`.

### 5.19 `internal/transform/openai_to_gemini_tool_test.go` (1–127)

- **15–72:** Toolresult ohne Name wird über einfache Call-ID aufgelöst; Output wird als String geprüft.
- **74–127:** Toolresult-Turn wird vor Folge-Assistant-Text eingefügt; Rollen und Name/ID geprüft.
- **Lücken:** Pipe-signierte ID, leere/duplizierte IDs, malformed Args, mehrere gleiche Funktionsnamen, unbekannte/non-text Inhalte, Systemrollen.

### 5.20 `internal/transform/openai_to_gemini_test.go` (1–148)

- **11–135:** vier Schema-Fixtures: einfaches Object, `anyOf`-Array, `oneOf`-Array, verworfene Unsupported-Keywords.
- **137–148:** DeepEqual plus JSON-Ausgabe.
- **Lücken:** Converter-End-to-End ohne Schema, scalar/nullable/required, direct-unmarshal parity, Inputmutation, raw/mixed tools.

### 5.21 `internal/transform/tool_parity_test.go` (1–111)

- **16–62:** zwei Assistant Calls mit zwei Toolresulten ohne Namen.
- **64–90:** drei Turns und zwei Calls in Reihenfolge.
- **92–110:** zwei FunctionResponses mit Output und Namensreihenfolge.
- **Lücken:** `respIDs` werden gesammelt (`tool_parity_test.go:93`, `99`), aber nie geprüft; damit bleibt die zentrale ID-Parität ungeprüft. Keine Reverse-/Signatur-/Malformed-/Duplicate-Name-Parität.

## 6. Testabdeckungs-Matrix

| Bereich | Abgedeckt | Wesentliche ungeprüfte Verträge |
|---|---|---|
| Non-Stream Generate | 200, 3.7/3.8 404-Fallback, kein Fremd-Fallback | vollständiger Body, Prompt-IDempotenz, Auth, 401/5xx/429, nil, Response-Parsing |
| Stream Generate | kein Test in Partition F | Zeilenweiterleitung, Channelclose, Scannerfehler, Context, 404-Fallback, 1-MiB-Grenze, Served Model |
| Auth | ein proaktiver Expiry-Refresh | 401, Nebenläufigkeit, Fehler, nil/leer/Expiry 0 |
| Thinking | Gemini Defaults/Presets, Claude 1024/2048/4096/Default, GPT-OSS, IncludeThoughts, Output clamp | Claude off/none, negative/0 Custom Budget, whitespace Level, unbekannte Nicht-Gemini-Modelle, Kombinationsgrenzen |
| System Prompt | Identity + ein Client-Part | vollständiger Promptvertrag, leere/whitespace Parts, User Rules, Duplicate auf Fallback |
| Content Sanitizing | kein direkter Test | leere/Whitespace/ThoughtSignature-only, Multi-Field-Parts, Rollenwechsel |
| Tool IDs | Nameauflösung einfacher Fälle | Fallback/Pairing bei gemischten Calls, missing pending IDs, explicit mismatch, gleiche Namen, tatsächliche Response-ID-Assertions |
| Raw Tools | kein direkter Test | custom/function/inputSchema/parameters, Mixed Arrays, native drop, Namenskollision |
| Schemas | einfache Typen, anyOf/oneOf Array-Priorität, Unsupported Drop | direct Unmarshal, camel/snake parity, numeric enum, allOf/ref, additionalProperties, mutation |
| OpenAI→Gemini | Toolresult-Rollen/Order und einfache Toolparität | System/Developer, multimodal, typed slices, GenerationConfig, invalid inputs/args, moderne Request-Felder |
| OpenAI Stream | Text, eine Reasoningform, ein Tool, native, grounding, usage, stop/tool_calls, empty | Fragment/multiple tools, IDs/index/signatur, role ordering, reasoning variants, Upstream-Finishzustände, unknown/error, usage validation |
| Models | kein Test in Partition F | Cache, Context, Quota, Fehler |

## 7. Priorisierte Prüfempfehlungen für eine spätere Revision

1. `prepareAntigravityRequest` in eine explizit idempotente Normalisierung überführen und den System-Prompt-Doppelappend im 404-Fallback mit einem Regressionstest verhindern.
2. Stream-Lifecycle auf genau einen Eigentümer festlegen; Erfolg, Fehler und Context-Cancellation über einen expliziten Abschlusskanal/Fehlerzustand modellieren.
3. Auth-Refresh auch im 401-Pfad unter denselben Lock/double-check-Mechanismus führen und nil/leere Credentials robust behandeln.
4. Sämtliche Payload-/Response-/ThoughtSignature-Logs aus Info-Level entfernen oder durch Längen, Hashes und sichere Metadaten ersetzen.
5. Tool-Historie strikt validieren: malformed Arguments/Names/IDs als Clientfehler behandeln; Call→Response-Parität inklusive IDs explizit testen.
6. Streaming-Tool-Calls mit stabilem Index/ID und Fragmentaggregation definieren; Signaturen über ein eigenes Feld oder eine eindeutig escapte Transportform statt über ein unvalidiertes `|`-Suffix führen.
7. Raw-/Mixed-Tool-Payloads vollständig konvertieren oder sichtbar ablehnen; niemals ein Array teilweise akzeptieren und still verkürzen.
8. Content-Typen und moderne OpenAI-Felder bewusst vertraglich festlegen und typisierte `[]ContentPart` ebenso behandeln wie JSON-decodierte `[]interface{}`.
9. Schema-Conversion normalisieren und Verlust/Constraints entweder bewusst dokumentieren oder erhalten; Input-Maps nicht mutieren.
10. Upstream-Finishzustände explizit bis zum OpenAI-Client transportieren, statt `stop` bei jedem Nicht-Tool-Ende zu erfinden.
11. Unterstützte moderne OpenAI-Felder explizit erfassen oder mit dokumentiertem 4xx ablehnen; insbesondere dürfen Token-Limit, Tool-Wahl, Stream-Optionen und Sampling-/Stop-Verträge nicht stillschweigend verloren gehen.
12. Retry-/Stream-Abbruch-Semantik für 429/5xx/Netz-/Scannerfehler mit Backoff, Grenzen und Tests definieren.

## 8. Abschlussaussage

Partition F ist in den getesteten Happy Paths strukturell gut lesbar und deckt zentrale Request-Umwandlung, Tool-Grundparität, Thinking-Presets, Schema-Basisfälle, Non-Stream-Fallback sowie die gängigsten OpenAI-Stream-Chunks ab. Die größten vertraglichen Risiken liegen nicht in den einzelnen Glücklichfällen, sondern in Retry/Wiederholung, Channel-/Auth-Lifecycle, strikt validierten Tool-Argumenten, partieller Tool-/Raw-Tool-Konvertierung, Streaming-ID-/Fragmentierung, stillen Datenverlusten und sensitiven Payload-Logs. Die Tests codieren einige bewusste Vereinfachungen, decken diese Kombinationen jedoch nicht ab.
<!-- END PART F -->

## Anhang G — Antigravity-Proxy: Server, Middleware und HTTP-Routen

<!-- BEGIN PART G -->
## Revision G – Dateiaudit Antigravity-Proxy-Server

**Auditgegenstand:** `/workspaces/MAIN/llm-proxies/antigravity-proxy/internal/server/`

**Prüfmodus:** statische, vollständige Zeilenprüfung. Es wurden keine Server gestartet, keine Tests ausgeführt, keine Netzwerkaktionen ausgeführt und keine Secrets ausgegeben. `Revision.md` wurde nicht verändert.

## 1. Umfang und Gesamtstatus

- 17 Go-Dateien vollständig gelesen: 11 Produktionsdateien und 6 Testdateien.
- Gesamtumfang: **3.565 Zeilen** (2.553 Produktionszeilen, 1.012 Testzeilen).
- Ausschließlich die angegebene Partition wurde für den fachlichen Audit bewertet. Abhängigkeiten in `antigravity`, `openai`, `transform`, `auth`, `credentials` und `http` wurden nur anhand ihrer hier sichtbaren Aufrufstellen und Schnittstellen bewertet.
- Alle nachfolgenden Prüfstatus bedeuten: **statisch geprüft, nicht ausgeführt**. Es gibt keine Aussage über einen erfolgreichen Lauf, eine Race-Detector-Prüfung, einen echten Upstream-Aufruf oder eine Deployment-Konfiguration.

## 2. Kurzfazit und priorisierte Befunde

### G-01 – API-Schlüssel kann in Anwendungslogs landen (hoch)

`adminMiddleware` akzeptiert den Admin-Schlüssel auch als Query-Parameter `key` (`admin_middleware.go:28,46-48`). Der Gemini-Handler protokolliert die vollständige Raw-Query (`stream_generate_content_handler.go:22-30`). Damit kann derselbe Schlüssel, den der Client bewusst als URL-Parameter sendet, im Prozesslog landen. Query-Schlüssel können zusätzlich durch Reverse Proxies, Access Logs, Browser-History oder Referrer offengelegt werden. **Status: Befund offen; statisch belegt.**

### G-02 – Keine Request-Body-Grenze und keine Server-Timeouts (hoch, Verfügbarkeit)

Die OpenAI- und Gemini-Request-Bodies werden mit unbeschränktem `io.ReadAll` gelesen (`chat_completions_handler.go:30-45`, `stream_generate_content_handler.go:74-87,154-167`). Der Listener wird ohne Read-, Write-, Idle- oder Header-Timeouts gestartet (`server.go:51-63`). Das erlaubt große Speicherbelastung und Slow-Client-/Slow-Request-Ressourcenbindung; bei geschütztem Endpunkt genügt dafür ein kompromittierter oder fehlkonfigurierter Client. **Status: Befund offen.**

### G-03 – Konkurrierende Schreibzugriffe auf denselben SSE-ResponseWriter (hoch, Protokollkorrektheit)

Im OpenAI-Stream schreibt ein Pinger-Goroutine direkt auf `w` (`chat_completions_handler.go:189-211`), während der Hauptgoroutine gleichzeitig SSE-Chunks auf `w` schreibt (`chat_completions_handler.go:415-428`). Es gibt keinen Write-Mutex. Dadurch können Bytes interleaven, SSE-Frames beschädigt werden oder der ResponseWriter race-anfällig sein. **Status: Befund offen; statisch belegt, Laufzeit nicht reproduziert.**

### G-04 – Abbruch und Ressourcenfreigabe sind im Non-Stream-/MCP-Pfad nicht durchgängig (mittel bis hoch)

`GenerateContent` wird in Gemini-, OpenAI- und MCP-Non-Stream-Pfaden ohne Request-`context` aufgerufen (`stream_generate_content_handler.go:98-105`, `chat_completions_handler.go:453-459`, `mcp_handler.go:129-134`). Der MCP-Handler erhält einen `ctx`, verwendet ihn für `ask_gemini` aber nicht (`mcp_handler.go:103-134`). Im OpenAI-Stream beendet der Adapter die Schleife bei einem Abbruchmarker, ohne den Upstream-Kanal zu drainen (`chat_completions_handler.go:215-250`). Ein Client-Abbruch kann dadurch Upstream-Goroutines, Kanäle oder Arbeit bis zur Kontextweitergabe blockieren. **Status: Befund offen; konkrete Client-Implementierung außerhalb der Partition nicht verifiziert.**

### G-05 – Fehler- und Statusmapping ist uneinheitlich und teils informationsleckend (mittel)

- Gemini-Streaming und Gemini-Non-Stream geben `UpstreamError` samt Status/Body weiter (`stream_generate_content_handler.go:114-124,252-262`).
- OpenAI wandelt Upstream-Fehler vor dem Response-Headerbeginn pauschal in 500 um; danach werden Fehler nur protokolliert und die Verbindung beendet (`chat_completions_handler.go:165-168,453-459`).
- `/v1/models` ist öffentlich und gibt bei Fehlern `err.Error()` an Clients aus (`models_handler.go:40-44,88-95`).
- Der ältere Credentials-Status legt den Provider-Fehlertext in die JSON-Antwort (`server.go:187-216`).
- Gemini-Fehler ohne typisierten Upstream-Fehler werden teilweise direkt formatiert (`stream_generate_content_handler.go:124,262`).

Das kann interne URLs/Provider-Details oder sensible Upstream-Informationen offenlegen und führt zu uneinheitlichen Client-Reaktionen. **Status: Befund offen.**

### G-06 – Mehrere mögliche Nil-Dereferenzen (mittel, Robustheit)

- `LoadCredentials` dereferenziert `creds` nach `GetCredentials()` ohne Nil-Prüfung (`server.go:65-75`).
- `GoogleAuth.Complete` verwendet `current.RefreshToken`, auch wenn `GetCredentials()` erfolgreich `nil` liefert (`google_auth.go:170-177`).
- `mcpAskGemini` dereferenziert `resp.Model` und `resp.Response` ohne Nil-Prüfung (`mcp_handler.go:145-153`).

Ob die Provider-/Client-Verträge Nilwerte tatsächlich zulassen, ist außerhalb der Partition nicht feststellbar; die Serverstellen selbst sichern den Fall nicht ab. **Status: Befund offen, Vertragsannahme zu verifizieren.**

### G-07 – Authentifizierte Google-Admin-Routen sind bei Reverse-Proxy-TLS potenziell zu streng (mittel)

`googleAuthRequestAllowed` leitet das Schema nur aus `r.URL` beziehungsweise `r.TLS` ab (`google_auth_handlers.go:144-157`). Übliche `X-Forwarded-Proto`-Angaben werden nicht berücksichtigt. Bei externem HTTPS-Terminierung kann ein gültiger Browser-Origin `https://host` als `http://host` bewertet und mit 403 abgewiesen werden. Fehlender Origin wird akzeptiert. **Status: Befund offen, abhängig vom äußeren Proxy.**

### G-08 – MCP schützt nur den Admin-Key; DNS-Rebinding-Schutz ist bewusst deaktiviert (mittel, Sicherheitsgrenze)

Der MCP-Handler deaktiviert den SDK-Localhost-/DNS-Rebinding-Schutz ausdrücklich (`mcp_handler.go:82-99`). Die Routen sind zwar mit `adminMiddleware` geschützt (`server.go:137-141`), aber es gibt keine zusätzliche MCP-spezifische Host-Allowlist, Origin-Prüfung, Rate-Limitierung oder Prompt-/Modellbegrenzung. Das ist im Code als Trade-off dokumentiert, aber bei einer öffentlichen Tunnel-Adresse bleibt der API-Key die einzige Zugriffsschranke. **Status: bewusste Designentscheidung, Restrisiko dokumentiert.**

### G-09 – Modellauflösung enthält Sonderfälle und tote Logik (niedrig bis mittel)

`resolveModelForThinking` nutzt breite Substring-Erkennung und behandelt mehrere 3.5-Flash-/Flash-Lite-Varianten als `gemini-3.1-flash-lite` (`model_resolver.go:34-112,174-207`). `isGemini35FlashModel` wird im gesamten Package nicht verwendet (`model_resolver.go:198-200`). Unbekannte Modelle werden unverändert durchgereicht. `applyModelThinkingDefaults` wirkt nur für 3.7-/3.8-Flash und setzt nur `ThinkingLevel`, nicht Budget/IncludeThoughts (`model_resolver.go:214-238`). **Status: Verhalten statisch nachvollzogen, Absicht nicht vollständig belegt.**

### G-10 – Route-/Response-Hygiene und Methodenbindung (niedrig bis mittel)

- `HandleFunc` bindet keine HTTP-Methode; Stream- und Chat-Handler prüfen selbst nicht auf POST (`server.go:132-141`, `stream_generate_content_handler.go:15-65`, `chat_completions_handler.go:22-45`).
- `/v1/models/{id}/...` ignoriert Pfadbestandteile nach dem Modell (`models_handler.go:64-76`).
- Mehrere Erfolgs-/Fehler-Encoder ignorieren Schreibfehler (`models_handler.go:70-85,88-95`).
- Ältere Credentials-Handler schließen den Request-Body nicht explizit (`server.go:149-178,180-217`); neuere OAuth-Helfer ebenso nicht (`google_auth_handlers.go:193-207`).

**Status: Befund offen; `net/http` schließt Bodies im Server-Lifecycle üblicherweise selbst, daher ist daraus allein kein bestätigter Produktions-Leak abgeleitet.**

## 3. HTTP-Routen, Middleware und Zugriffsmatrix

Die Routen werden in `server.go:122-142` aufgebaut. `Start` legt `loggingMiddleware` außen um das Mux (`server.go:61-62`). Die Admin-Auth liegt jeweils innerhalb dieser Route.

| Route | Handler/Methode laut Implementierung | Schutz | Befund |
|---|---|---|---|
| `/admin/credentials` | `credentialsHandler`; nur POST akzeptiert (`server.go:149-154`) | `adminMiddleware` | JSON-Decoder ohne Body-Limit; kein expliziter Body-Close; kein `Allow` bei 405. |
| `/admin/credentials/status` | `credentialsStatusHandler`; nur GET akzeptiert (`server.go:180-184`) | `adminMiddleware` | Fehlertext wird in Response aufgenommen; kein `no-store`/`nosniff` auf diesem Legacy-Pfad. |
| `/admin/auth/start` | `googleAuthStartHandler`; POST | `adminMiddleware` plus Origin-/Methodenprüfung | Proxy-TLS-Schema kann falsch sein; Body wird nur begrenzt verworfen. |
| `/admin/auth/status` | GET oder POST | `adminMiddleware` plus Origin-/Methodenprüfung | POST strikt JSON und 64 KiB; Session-/Tokeninformationen nur im geschützten Pfad. |
| `/admin/tokens` | `tokensHandler`; POST | `adminMiddleware` plus Origin-/Methodenprüfung | Strikte JSON-/Content-Type-Prüfung und 64 KiB; Refresh-Token-Pflicht. |
| `/admin/status` | `tokenStatusHandler`; GET | `adminMiddleware` plus Origin-/Methodenprüfung | Gibt nur einen booleschen Konfigurationsstatus zurück. |
| `/v1beta/models/{model}:{action}` | `streamGenerateContentHandler`; erwartet `generateContent` oder `streamGenerateContent` | `adminMiddleware` | Keine POST-Methodenprüfung; Query kann den Key enthalten und wird geloggt; Action-Parsing ist nicht strikt verankert. |
| `/v1/models` | `modelsHandler`; GET | **keine** Admin-Auth | Öffentliche Modell-Discovery und Upstream-Abfrage. |
| `/v1/models/{id}` | `modelsHandler`; GET | **keine** Admin-Auth | Detailpfad; zusätzliche Pfadsegmente werden ignoriert. |
| `/v1/chat/completions` | `openAIChatCompletionsHandler`; stream/nonstream | `adminMiddleware` | Keine POST-Methode-/Content-Type-Prüfung; Body-Limit fehlt. |
| `/mcp` und `/mcp/` | MCP Streamable HTTP, stateless/JSON response | `adminMiddleware` | SDK-Host-Schutz deaktiviert; gemeinsamer Admin-Key; kein MCP-spezifisches Origin-/Rate-Limit. |
| alle übrigen Pfade | `ServeMux` 404 | kein zusätzlicher Handler | Standardverhalten, im Partition-Code nicht weiter behandelt. |

### Middleware-Reihenfolge

1. `loggingMiddleware` protokolliert Beginn und Ende (`logging_middleware.go:11-31`).
2. Route-spezifisch schützt `adminMiddleware` Admin-, Gemini-, Chat- und MCP-Routen (`server.go:124-141`).
3. Für die neueren Google-Auth-Routen folgen Methoden-, Origin- und Eingabeprüfungen (`google_auth_handlers.go:16-18,93-129,131-160`).
4. Bei direktem `ServeHTTP` ohne `Start` entfällt die Logging-Middleware; das ist in den Tests der Fall, im normalen `Start`-Pfad nicht.

### Admin-Auth

`adminMiddleware` (`admin_middleware.go:14-72`) akzeptiert `Authorization: Bearer`, `X-Goog-Api-Key`, `X-API-Key` und `?key=...`. Der Vergleich erfolgt über SHA-256 und `subtle.ConstantTimeCompare`, was gegen timing-basierte Tokenvergleiche positiv ist. Es fehlen jedoch:

- kein TLS-Erzwang im Listener;
- kein Rate-Limit und kein Request-Body-Limit;
- kein Rotations- oder Per-Client-Scope;
- kein eigener Host-/Origin-Schutz für alle Admin-Routen;
- kein `WWW-Authenticate` und kein konsistenter `Allow`-Header.

Die Key-Prüfung erfolgt bei jedem Request neu. Das ist funktional, aber nicht explizit gegen Env-Wechsel/Concurrent-Zugriffe abgesichert.

## 4. Querschnittliche Datenflüsse

### 4.1 Gemini-API

`streamGenerateContentHandler` (`stream_generate_content_handler.go:15-65`) liest Modell und Action aus dem Pfad, normalisiert den Namen faktisch nicht, liest und unmarshalt den Body, löst das Modell auf, wendet Thinking-Defaults an und baut den CloudCode-Wrapper. Non-Stream ruft `GenerateContent` und schreibt `resp.Response`. Stream ruft `StreamGenerateContent` mit `r.Context()` und leitet Zeilen über `TransformSSELine` weiter (`stream_generate_content_handler.go:148-339`).

**Offene Punkte:** Methodenbindung, Body-Größe, genaue SSE-Framing-Regeln, Kontext im Non-Stream-Pfad, potenzielle Übertragung interner Fehlerdetails.

### 4.2 OpenAI-Chat-Completions

Der Handler (`chat_completions_handler.go:22-141`) liest und parst den Request, protokolliert Tool-Ergebnisse mit einer 300-Zeichen-Vorschau, versucht eine Fallback-Modellwahl und verzweigt in Stream/Non-Stream. `transform.ToGeminiRequest` ist die externe Transform-Grenze; die darauffolgende Modell-/Thinking-Auflösung ist lokal sichtbar.

Im Stream-Pfad (`chat_completions_handler.go:143-435`) werden Upstream-SSE-Daten zu `openai.StreamChunk`, anschließend durch den OpenAI-Stream-Transformer zu Client-SSE. Thinking-Teile, Text, Grounding-Metadaten, Usage und Function Calls werden getrennt erkannt. Der Non-Stream-Pfad (`chat_completions_handler.go:437-614`) liest nur den ersten Kandidaten und erzeugt OpenAI-`chat.completion` mit optionalem Tool-Call.

**Offene Punkte:** unbounded input, gleichzeitige Pinger-/Haupt-Writes, vorzeitiges `break`, keine Upstream-Statusdurchreichung, keine Kontextweitergabe im Non-Stream-Pfad.

### 4.3 MCP

`newMCPServer` registriert `ask_gemini` und `ask_gemini_models` (`mcp_handler.go:49-79`). Der Handler wird einmal gebaut, ist stateless und antwortet als JSON (`mcp_handler.go:82-100`). `ask_gemini` validiert nur leere Prompt-/Modellwerte, wendet dieselbe Modellauflösung an und ruft den Antigravity-Client auf (`mcp_handler.go:103-170`). `ask_gemini_models` filtert und sortiert die verfügbaren Modelle (`mcp_handler.go:172-200`).

**Offene Punkte:** fehlende Prompt-Längen-/Modell-Allowlist, ungenutzter `ctx` im Generate-Pfad, Nil-Antwortannahme, potenzielles Zusammenfügen mehrerer Kandidaten ohne Trenner.

### 4.4 Modellauflösung

Die lokale Auflösungsreihenfolge ist:

1. Exakte bekannte Upstream-ID: unverändert zurückgeben (`model_resolver.go:34-41`).
2. Claude-Aliase auf Opus-/Sonnet-Zielmodelle abbilden (`model_resolver.go:45-50`).
3. Gemini 3.1 Pro nach Thinking-Level auf Agent/ Low abbilden (`model_resolver.go:52-60`).
4. Gemini 3.8/3.7/3.6 Flash nach `high`, `medium`, `minimal/low/empty` auf die jeweiligen IDs abbilden (`model_resolver.go:62-96`).
5. 3.5-Flash/Flash-Lite breit auf `gemini-3.1-flash-lite` abbilden; Image, `gemini-3-flash` und GPT-OSS folgen (`model_resolver.go:98-112,202-212`).
6. Unbekannte IDs bleiben unverändert.

`applyModelThinkingDefaults` erzeugt nur bei 3.7-/3.8-Flash bei fehlender `GenerationConfig`/`ThinkingConfig` eine Struktur und setzt bei leerem Level `HIGH`, `MEDIUM` oder `LOW` aus dem Modellnamen (`model_resolver.go:214-238`). Thinking-Budget und IncludeThoughts werden dort nicht gesetzt.

## 5. Streaming-, Ressourcen- und Abbruchverhalten

### 5.1 Gemini-Stream

- `r.Context()` wird an `StreamGenerateContent` übergeben (`stream_generate_content_handler.go:180-184`), das ist für den Start/Abbruch positiv.
- Der Handler beendet die Schleife bei Context-Ende und beendet den Ticker per `defer` (`stream_generate_content_handler.go:285-330`).
- `TransformSSELine` verarbeitet ausschließlich exakt `data: ` und JSON auf einer einzelnen Zeile (`gemini_helpers.go:59-89`). Multi-Line-SSE, `data:` ohne Leerzeichen, alternative Event-Strukturen und beliebige Framing-Regeln werden nicht abgesichert.
- Bei ungültigem JSON wird die Originalzeile weitergereicht (`gemini_helpers.go:66-74`), wodurch ein defektes Upstream-Format als Client-Text/SSE weitergereicht werden kann.
- Der direkte Stream schreibt Ticker und Daten im selben Loop; im Gegensatz zum OpenAI-Pfad gibt es hier keinen Writer-Goroutine.

### 5.2 OpenAI-Stream

- Der Upstream-Kanal wird vor dem Adapter erzeugt und im Adapter-Goroutine verarbeitet (`chat_completions_handler.go:159-170,213-218`).
- Pinger und Hauptthread schreiben gleichzeitig auf `w` (`chat_completions_handler.go:189-211,415-428`): G-03.
- Der Adapter stoppt bei `[DONE]` oder leerem Payload mit `break` (`chat_completions_handler.go:239-250`), ohne den Upstream-Kanal explizit zu leeren oder einen Producer-Abbruch zu signalisieren.
- Für Client-Schreibfehler gibt es keine SSE-Fehlernachricht und keinen expliziten Upstream-Cancel vor Rückkehr (`chat_completions_handler.go:415-419`).
- `http.Flusher` wird korrekt optional genutzt, aber der konkurrierende Pinger beseitigt dessen Thread-Sicherheitsannahme nicht.

### 5.3 Body- und Timer-Lebenszyklus

- Explizite `defer r.Body.Close()` gibt es in den beiden OpenAI-/Gemini-Body-Readern (`chat_completions_handler.go:30-37`, `stream_generate_content_handler.go:74-80,154-161`).
- `readLimitedRequestBody` begrenzt die neueren Google-Auth-Bodies auf 64 KiB, schließt den Body aber nicht explizit (`google_auth_handlers.go:193-207`).
- Credentials-Legacy-Handler tun dasselbe nicht (`server.go:149-178,180-217`).
- `GoogleAuth.Complete` beendet seinen Timeout via `defer cancel` (`google_auth.go:161-163`).
- Der Refresh-Loop hat keinen Stop-Kanal und wird bei `ListenAndServe`-Ende nicht beendet (`server.go:95-119`). Ein ungültiger Wert `0s` oder negativ lässt `time.NewTicker` panicen (`server.go:97-111`).
- `Start` kann mehrfach gestartet werden und startet dann mehrere Refresh-Loops; es gibt keine `Shutdown`-Methode.

## 6. Fehler- und Statusmatrix

| Bereich | Erwartung/aktuelles Mapping | Befund |
|---|---|---|
| Admin-Middleware | fehlender Key: 500; fehlender/falscher Key: 401 | korrekt getrennt, aber 500 bei fehlender Konfiguration und kein `WWW-Authenticate`; Query-Key-Risiko. |
| Credentials-Handler | falsche Methode 405; Decode 400; Speichern 500 | kein Body-Limit, kein `Allow`, kein `no-store` auf diesem Pfad. |
| Google-Auth-Handler | Methode 405, Origin 403, Content-Type 415, Body 400/413, OAuth-Input 400, Exchange 502, Speicher-/Infrastruktur 500 | konsistente neuere Helper; Origin-Berechnung kann hinter TLS-Proxy falsch sein. |
| Gemini-Stream/-Non-Stream | Parse/Action/Body 400; typisierter Upstream-Fehler übernimmt Status; sonst 500 | Upstream-Detail-Bodies werden durchgereicht; generische Fehlertexte können interne Daten enthalten. |
| OpenAI-Chat | Parse/Body 400; Transform/Upstream 500 | kein Upstream-Status-Mapping, keine Methodenbindung; nach SSE-Headerbeginn sind Fehler nicht mehr als Status änderbar. |
| Model-Discovery | Methode 405; Upstream-Fehler 500 als JSON | Endpunkt öffentlich; `err.Error()` wird offengelegt. |
| MCP | Middleware 401/500; SDK bestimmt Protokoll-/Toolfehler | Toolfehler werden laut Test als `isError` erwartet; kein eigener HTTP-Statuskanal. |

## 7. Sicherheitsgrenzen

### Positiv

- Admin-/Generierungs-/Chat-/MCP-Routen sind im Mux durch `adminMiddleware` geschützt.
- Tokenvergleich ist hash-basiert und zeitkonstant.
- Google OAuth nutzt State, PKCE, Ablaufzeit, 15-Minuten-Session und 30-Sekunden-Exchange-Timeout.
- Neuere Admin-Antworten setzen `Cache-Control: no-store` und `X-Content-Type-Options: nosniff` (`google_auth_handlers.go:228-239`).
- Neuere JSON-Eingaben sind unbekannte-Feld-strict und größenbegrenzt.
- Der Gemini-Stream verwendet den Request-Kontext.

### Grenzen und Risiken

1. **Ein gemeinsamer statischer Key:** Wer den Admin-Key besitzt, erhält Zugang zu Credentials-/OAuth-Verwaltung, Gemini, Chat und MCP; es gibt keine Route- oder Client-Isolation.
2. **Query-Transport des Keys:** nicht durch Proxy/HTTP-Key-Parameter empfohlen und im Gemini-Pfad konkret geloggt.
3. **Klartext-Listener:** `http.ListenAndServe` bietet selbst kein TLS. Ein externer TLS-Terminator ist damit Voraussetzung für einen sicheren Remote-Betrieb, aber nicht im Server erzwingt.
4. **Öffentliche Model-Discovery:** `/v1/models` benötigt keinen Admin-Key und kann Account-/Entitlement-Informationen und Upstream-Ressourcen unbegrenzt abfragen.
5. **MCP-Host-Schutz:** bewusst deaktiviert; bei Fehlkonfiguration oder Key-Leak ist der MCP-Endpunkt direkt angreifbar.
6. **Daten in Logs:** Tool-Ergebnis-Vorschauen und vollständige Tool-Argumente werden auf INFO/DEBUG geloggt (`chat_completions_handler.go:55-99,364-379`), Thought-/Text-Tokens auf DEBUG (`chat_completions_handler.go:301-329`). Eine Redaktion ist im geprüften Package nicht erkennbar.
7. **Fehlerinformationen:** öffentliches Model-Discovery und mehrere generische Fehlerpfade geben interne Fehlertexte aus.
8. **Keine Rate-/Ressourcenlimits:** unabhängig vom Authentifizierungsstatus können große Bodies, lange Streams und wiederholte Upstream-Aufrufe Ressourcen binden.
9. **Methoden-/Origin-Heuristik:** Origin-Prüfung ist nicht auf allen Admin-Routen vorhanden und berücksichtigt keine Forwarded-Proto-Header.
10. **Modell-/Prompt-Grenzen:** Chat, Gemini und MCP akzeptieren beliebige Modell-IDs; MCP begrenzt weder Prompt- noch Modell-Länge bzw. erlaubte IDs.

## 8. Datei-Audit

### 8.1 Produktionsdateien

| Pfad | Zeilen | Zweck | Befund | Prüfstatus |
|---|---:|---|---|---|
| `server.go` | 217 | Serverkonstruktion, Optionen, Routen, Start, Token-Refresh, Legacy-Credentials | Auth-Routenmatrix; kein Shutdown/Timeout; Refresh-Loop-Lifecycle; nil `creds`; Legacy-Body-/Fehlerhygiene | vollständig statisch gelesen / nicht ausgeführt |
| `chat_completions_handler.go` | 614 | OpenAI-Request, Modell-Fallback, SSE- und JSON-Ausgabe, Tool-/Thought-/Usage-Transformation | unbeschränkter Body; kein POST/Content-Type-Check; gleichzeitige SSE-Writes; Pinger/Upstream-Abbruch; 500-Mapping ohne Upstream-Status; Non-Stream ohne Kontext | vollständig statisch gelesen / nicht ausgeführt |
| `stream_generate_content_handler.go` | 383 | Gemini-Pfad, Action-Dispatch, CloudCode-Wrapper, SSE-Weiterleitung | keine Methodenprüfung; Raw-Query-Logging; Body-Limit; einfache SSE-Erkennung; Kontext nur im Stream; Fehler-/Statusleck | vollständig statisch gelesen / nicht ausgeführt |
| `models_handler.go` | 136 | OpenAI-kompatible Model-Liste und Detailabfrage, Familienfilter | öffentlicher Endpunkt; Upstream-Fehler öffentlich; Detailpfad ignoriert Extra-Segmente; `gpt`/`openai`-Ownership inkonsistent; Encoderfehler ignoriert | vollständig statisch gelesen / nicht ausgeführt |
| `model_resolver.go` | 238 | Modellalias-/Thinking-Auflösung und Defaults | Substring-Sonderfälle; 3.5→3.1-Flash-Lite; toter Helper; unbekannte IDs werden durchgereicht; Defaults nur 3.7/3.8 und nur Level | vollständig statisch gelesen / nicht ausgeführt |
| `mcp_handler.go` | 265 | Stateless MCP-Server, `ask_gemini`, Modellliste, Text-/Schema-Helfer | Host-Schutz deaktiviert; Key-only; keine Prompt-/Modellgrenzen; `ctx` in `ask_gemini` ungenutzt; Nil-`resp`; Kandidaten-/Parts-Vereinfachungen | vollständig statisch gelesen / nicht ausgeführt |
| `google_auth.go` | 266 | PKCE-/State-Lifecycle, Tokenexchange, Sessionpersistenz | State-/PKCE-/Timeout-/Lock-Logik positiv; Nil-`current`-Dereferenz; absolute URL ohne Hostprüfung; Store-/Provider-Identität nicht erzwungen; Netzwerk unter Global-Mutex | vollständig statisch gelesen / nicht ausgeführt |
| `google_auth_handlers.go` | 239 | Admin-Endpunkte für Google Auth und manuelle Tokens, JSON-/Origin-/Body-Helfer | 64-KiB-/Strict-JSON/no-store positiv; Forwarded-Proto fehlt; Body-Close nicht explizit; Originfehler möglich; Fehlerkategorisierung grundsätzlich sauber | vollständig statisch gelesen / nicht ausgeführt |
| `admin_middleware.go` | 73 | API-Key-Prüfung für geschützte Routen | constant-time Vergleich positiv; Query-Key-Leak; keine TLS-/Rate-/Body-Grenze; unvollständige WWW-/Allow-Header | vollständig statisch gelesen / nicht ausgeführt |
| `logging_middleware.go` | 32 | Request-Start-/Enddauer-Logging | kein Statuscode, kein Panic-Recovery, keine globalen Security-Header; nur im `Start`-Pfad aktiv | vollständig statisch gelesen / nicht ausgeführt |
| `gemini_helpers.go` | 90 | Gemini-Pfadparser, No-op-Normalisierung, SSE-Unwrap | Regex nicht vollständig verankert; nur `data: `; keine Multi-Line-/CRLF-Sonderbehandlung; Metadaten-Merge; Rohdaten bei Parsefehler | vollständig statisch gelesen / nicht ausgeführt |

### 8.2 Testdateien

| Pfad | Zeilen | Zweck | Befund | Prüfstatus |
|---|---:|---|---|---|
| `google_auth_test.go` | 209 | OAuth-Start, Exchange, State-/URL-Parser und Teststore | deckt Happy Path und State-Fehler ab; keine Ablauf-, Refresh-, Timeout- oder Nebenläufigkeitsfälle | vollständig statisch gelesen / nicht ausgeführt |
| `google_auth_handlers_test.go` | 112 | Admin-Auth-Endpunkte, Token-Speicherung, unbekannte JSON-Felder | deckt Auth-401 und zentrale Erfolgsantworten ab; keine Origin-/Methoden-/Body-Fehlerfälle | vollständig statisch gelesen / nicht ausgeführt |
| `mcp_handler_test.go` | 302 | MCP-Auth, Initialisierung, Tool-Liste, Blank-Input, Textextraktion, Non-Loopback-Host | gute Protokoll-Basisabdeckung; kein Upstream-Ask, keine Grenzen/Cancellation, kein Nil-Response | vollständig statisch gelesen / nicht ausgeführt |
| `models_handler_test.go` | 79 | Modellfamilien, eindeutige Namen und Ownership | reine Helper-Tests; kein HTTP-Handler, Upstream-Fehler oder Pfaddetailtest | vollständig statisch gelesen / nicht ausgeführt |
| `model_resolver_test.go` | 249 | Tabellenabdeckung der Modell-/Thinking-Auflösung | gute Resolver-Baseline; kein Test der Thinking-Defaults oder unbekannter/fehlerhafter Upstream-IDs | vollständig statisch gelesen / nicht ausgeführt |
| `gemini_helpers_test.go` | 61 | No-op-Modellnormalisierung | kein Test für Regex-Pfadparser, SSE-Unwrap oder Fehlerfallback | vollständig statisch gelesen / nicht ausgeführt |

### 8.3 Einzeltests

Alle folgenden Tests wurden vollständig gelesen, aber nicht ausgeführt. Die in `mcp_handler_test.go` vorhandene `httptest.NewServer`-Prüfung wurde nicht gestartet.

| Test | Datei/Zeile | Abgedecktes Verhalten | Nicht abgedeckt / Befund | Prüfstatus |
|---|---|---|---|---|
| `TestGoogleAuthStart` | `google_auth_test.go:67-104` | Start, Pending-Status, State/PKCE, Authorization-URL, Expiry | Fehlerpfade, Persistenzfehler, Ablaufprüfung | gelesen / nicht ausgeführt |
| `TestGoogleAuthComplete` | `google_auth_test.go:106-147` | Redirect-URL, Tokenform, Credentials/Expiry | Refresh-Fallback, Tokenfehler, Timeout, Replay | gelesen / nicht ausgeführt |
| `TestGoogleAuthCompleteRejectsInvalidState` | `google_auth_test.go:149-179` | fehlender/falscher State | abgelaufene Session, leere/fehlerhafte URLs | gelesen / nicht ausgeführt |
| `TestParseGoogleAuthorizationInput` | `google_auth_test.go:181-204` | Redirect, Fragment, Query, einfacher Code | kodierte/fehlerhafte Varianten, Redirect-Host-Validierung | gelesen / nicht ausgeführt |
| `TestGoogleAuthHandlers` | `google_auth_handlers_test.go:15-73` | Admin-401, Start/Complete/Status, no-store | Origin, Content-Type, Methoden, Body-Limit, Upstreamfehler | gelesen / nicht ausgeführt |
| `TestTokensHandler` | `google_auth_handlers_test.go:75-89` | manuelle Token-Speicherung | bestehende Metadaten, fehlenden/ungültigen Refresh-Token, Fehlerstatus | gelesen / nicht ausgeführt |
| `TestTokensHandlerRejectsUnknownFields` | `google_auth_handlers_test.go:91-101` | striktes JSON | Trailing JSON, Content-Type, Größe | gelesen / nicht ausgeführt |
| `TestIsSupportedModel` | `models_handler_test.go:7-38` | Familienerkennung und unbekannte IDs | Endpoint, Filterung gegen echte Upstream-Daten, Ownership-Konsistenz | gelesen / nicht ausgeführt |
| `TestNewOpenAIModelNameIsModelID` | `models_handler_test.go:42-58` | eindeutiger Modellname | Handler/Response, Sortierung, Created | gelesen / nicht ausgeführt |
| `TestNewOpenAIModelOwnedBy` | `models_handler_test.go:60-79` | Claude/Gemini-Owner | GPT-/OpenAI-Owner und Familienklassifikation | gelesen / nicht ausgeführt |
| `TestMCPEndpointRequiresAdminKey` | `mcp_handler_test.go:61-71` | MCP-Admin-Key | alternative Key-Transportmittel, ungültige Headerformate | gelesen / nicht ausgeführt |
| `TestMCPInitialize` | `mcp_handler_test.go:73-95` | MCP-Initialisierung/Serverinfo | Version/Protokoll-Fehlerfälle, unbekannte Methoden | gelesen / nicht ausgeführt |
| `TestMCPToolsList` | `mcp_handler_test.go:97-135` | Toolnamen, Beschreibungen, Pflichtfelder | Schemafehler, zusätzliche Properties, Authorization-Ausgabe | gelesen / nicht ausgeführt |
| `TestMCPAskGeminiRejectsBlankInput` | `mcp_handler_test.go:137-175` | leerer Prompt/Model als Tool-Fehler | Length-/Modellgrenzen, Upstreamfehler, Cancellation | gelesen / nicht ausgeführt |
| `TestExtractGeminiText` | `mcp_handler_test.go:194-260` | Textteile, Thought-Ausschluss, fehlende Parts | `candidate.parts`-Fallback, mehrere Kandidaten, nil Response | gelesen / nicht ausgeführt |
| `TestMCPAllowsNonLoopbackHost` | `mcp_handler_test.go:267-302` | deaktiviertes Localhost-/Rebinding-Verhalten bei öffentlichem Host | echte Tunnel-/Proxy-Konfiguration, Origin/Key-Leak, Request-Body | gelesen / nicht ausgeführt |
| `TestNormalizeModelName` | `gemini_helpers_test.go:5-61` | No-op-Normalisierung | Pfadparser, SSE-Unwrap, Fehlerfallback | gelesen / nicht ausgeführt |
| `TestResolveModelForThinking` | `model_resolver_test.go:9-249` | Tabellenabdeckung vieler Modell-/Thinking-Aliase | `applyModelThinkingDefaults`, unbekannte IDs, alle `isKnown`-IDs, Nebenwirkungen | gelesen / nicht ausgeführt |

## 9. Testabdeckung und fehlende Regressionstests

Die sechs Testdateien enthalten 18 Top-Level-Testfunktionen. Abgedeckt sind vor allem reine Hilfsfunktionen, der Google-Auth-Happy-Path, Token-Persistenz, MCP-Protokollgrundlagen und die Modellauflösung. Nicht abgedeckt sind die größten Laufzeitbereiche:

- `Start`/`ListenAndServe`, Refresh-Loop und Shutdown;
- `adminMiddleware` in allen accepted/rejected Varianten;
- Request-Body-Limits, Methodenbindung, Origin/Reverse-Proxy;
- Gemini- und OpenAI-Streaming mit Cancellation, Upstream-Ende, `[DONE]`, Write-Fehlern und Pinger-Konkurrenz;
- Status-/Body-Weitergabe bei `UpstreamError`;
- Model-Discovery mit Fehlern und echten Clientpfaden;
- MCP-Upstream-Ask, Prompt-/Modelllimits, Nil-Antworten und Context-Abbruch;
- gleichzeitige OAuth-Sessions/Statuszugriffe und Store-Fehler;
- Ressourcenfreigabe, Nil-Provider-/Client-Fälle und Panic-Schutz.

Die Testquellen enthalten außerdem keine Tests für `chat_completions_handler.go`, `stream_generate_content_handler.go`, `server.go`, `admin_middleware.go` oder `logging_middleware.go`.

## 10. Abschlussstatus

- **Dateiprüfung:** vollständig für alle 17 Go-Dateien.
- **Testprüfung:** vollständig für alle 6 Testdateien und 18 Top-Level-Tests; nicht ausgeführt.
- **Laufzeitprüfung:** ausdrücklich nicht durchgeführt.
- **Änderungen:** ausschließlich diese Auditspur nach `.runtime/revision-parts/G.md`; keine Produktionsdatei geändert.
- **`Revision.md`:** unberührt.
- **Offene Befunde:** G-01 bis G-10; die Datei enthält statische Befunde, keine behaupteten Laufzeit-/Integrationstests.
<!-- END PART G -->

## Anhang H — glm2api: Betrieb, Rebuild und Bundle

<!-- BEGIN PART H -->
## Revision H — `llm-proxies/` / `glm2api` Betriebs- und Reproduzierbarkeitsprüfung

Datum: 2026-09-24
Prüfmodus: ausschließlich statisch
Gesamtstatus: **BEFUND — nicht abnahmefähig ohne die unten genannten Klärungen**

## 1. Scope und Methodik

Geprüft wurden:

- `llm-proxies/rebuild.sh`
- `llm-proxies/glm2api.env`
- `llm-proxies/scripts/` einschließlich `scripts/bundle/`
- alle Textdateien direkt unter `llm-proxies/glm2api/`
- die relevanten Verzeichnisnamen und Querverweise gegen `infrastructure.md`

Nicht inhaltlich gelesen wurden:

- Python-App-Code unter `llm-proxies/glm2api/src/`
- `llm-proxies/glm2api/tests/`
- `llm-proxies/glm2api/benchmarks/`
- Runtime-Inhalte unter `.venv/`, `.pytest_cache/` und `log/`
- Bundle-Dateien unter `llm-proxies/dist/`
- `llm-proxies/antigravity-proxy/`

Die 20 zum Inhaltsscope gehörenden Textdateien wurden vollständig und zeilenweise gelesen. `.env` wurde ebenfalls vollständig lokal eingelesen; ausgegeben und in diesem Bericht dokumentiert wurden ausschließlich Schlüsselnamen, Leer/gesetzt-Zustand, Duplikate und Abweichungsnamen, niemals Werte.

Nicht ausgeführt wurden Installation, Build, Start, Smoke-Test, Tests, Benchmarks, `curl`, Port-/Prozessabfragen oder Netzwerkzugriffe.

## 2. Kurzergebnis

### Bestätigt

- Die Standard-Portkette ist konsistent: operative Vorlage, MAIN-Start, Smoke-Test und Bundle-Start verwenden `127.0.0.1:8001`; `.env.example` verwendet abweichend `8000` als Beispielwert.
- `.python-version`, `pyproject.toml` und `uv.lock` verlangen Python 3.14.
- `main.py` und der Entry-Point in `pyproject.toml` zeigen auf dieselbe Funktion.
- Die getrackte operative Vorlage `llm-proxies/glm2api.env` ist secret-frei: Refresh-Token und Server-Keys sind leer.
- Die lokale `.env` ist ignoriert, syntaktisch strukturell sauber und enthält 25 eindeutige Zuweisungen ohne Duplikate.
- Das Bundle-ZIP ist getrackt; der danebenliegende entpackte Stage-Baum ist ignoriert.
- Das aktuell referenzierte externe Reverse-Engineering-Dokument existiert.

### Nicht bestätigt bzw. fehlerhaft

- Port-Overrides und der Start mit einer veränderten `.env` sind nicht konsistent.
- Das Bundle ist weder vollständig verifiziert noch hostübergreifend als deterministisch garantiert.
- Der Startpfad ist abhängig von nicht geprüften Systemwerkzeugen, hat keine belastbare Prozessidentifikation und keinen Single-Start-Lock.
- Rebuild und Bundle-Install sich Toolchain und Lock-Synchronität nicht ausreichend.
- Die bestehende `.env` wird nicht mit der Vorlage migriert.
- Mehrere Betriebsaussagen sind widersprüchlich: Gast-Modus, Debug-Logging, Bundle-Vollständigkeit, Abhängigkeiten, Logziel und Systemvoraussetzungen.
- Zwei Doku-Verweise sind im aktuellen Baum nicht auflösbar.

## 3. Befunde

### H-01 — Hoch: Portannahmen und dokumentierte Bundle-Overrides sind nicht belastbar

**Beobachtung**

- Die App-Konfiguration verwendet `HOST` und `PORT` in `llm-proxies/glm2api.env:14` und `llm-proxies/glm2api.env:18`.
- Der MAIN-Start prüft unabhängig davon fest `127.0.0.1:8001` in `llm-proxies/scripts/start-glm2api.sh:11-13`.
- Der Bundle-Start behauptet, `GLM_PORT`/`GLM_HOST` seien Overrides, legt aber nur Shellvariablen `PORT`/`HOST` an: `llm-proxies/scripts/bundle/start.sh:3-10`.
- Diese neuen Shellvariablen werden nicht explizit als `HOST`/`PORT` exportiert. Im mitgelieferten Konfigurationsformat existieren keine Variablen `GLM_PORT` oder `GLM_HOST`.

**Auswirkung**

- Eine absichtlich auf einen anderen Port gesetzte `.env` kann starten, während das Skript weiterhin 8001 prüft und anschließend einen Timeout meldet.
- Beim Bundle können Health-Check und App-Port auseinanderlaufen. Die behauptete Override-Funktion ist aus den verpackten Eingaben nicht reproduzierbar nachweisbar.
- Für den aktuellen unveränderten Standard 8001 ist kein Portfehler erkennbar; die Generalisierbarkeit ist aber nicht gegeben.

### H-02 — Hoch: Bundle-Verifikation und Determinismusgarantie sind überzogen

**Beobachtung**

- Feste Zeitstempel und `zip -X` werden verwendet: `llm-proxies/scripts/build-bundle.sh:48-52`.
- Es fehlen jedoch eine explizit sortierte Dateiliste, eine Normalisierung von Dateimodi und eine Pinning der verwendeten ZIP-/Build-Werkzeuge. Das Skript normalisiert nur Zeitstempel. Unterschiedliche Dateisystem-Traversierung, Umask-Modi oder Tool-Versionen können die ZIP-Bytes beeinflussen.
- Verifiziert werden nur:
  - Existenz aller `tests/*.py`, nicht ihre Inhalte: `llm-proxies/scripts/build-bundle.sh:54-61`
  - MD5-Identität ausschließlich für `src/**/*.py`: `llm-proxies/scripts/build-bundle.sh:62-69`
- Nicht verifiziert werden Top-Level-Metadaten, `glm2api.env`, Bundle-Skripte, README, externe Doku, Nicht-Python-Dateien unter `src/` oder das Fehlen zusätzlicher Dateien.
- Das externe Doku-File wird mit `|| true` kopiert: `llm-proxies/scripts/build-bundle.sh:42-44`. Ein fehlendes Doku-File lässt den Build trotzdem erfolgreich enden.
- `optimierung.md` wird nicht in die explizite Top-Level-Kopierliste aufgenommen: `llm-proxies/scripts/build-bundle.sh:33-35`.
- Das ZIP wird direkt gelöscht und neu erzeugt, nicht als temporäres ZIP mit atomarem Rename: `llm-proxies/scripts/build-bundle.sh:51-52`.
- Im geprüften Bereich existiert kein Commit-Hook, der vor einem Bundle-Commit zwingend den Builder ausführt.

**Auswirkung**

- `infrastructure.md:114-121` behauptet, Drift sei „strukturell ausgeschlossen“ und ein veraltetes Bundle könne nicht committet werden. Das ist aus dem geprüften Buildpfad nicht ableitbar.
- Ein unverändert committetes altes ZIP oder Drift in nicht verifizierten Dateien wird nicht erkannt.
- Die derzeitige Frische des getrackten ZIPs wurde unter dem Verbot von Build/Extraktion nicht festgestellt.

### H-03 — Hoch, deploymentabhängig: Secret- und Debug-Daten sind unnötig exponiert

**Beobachtung**

- Die lokale `.env` enthält genau eine Abweichung gegenüber `glm2api.env`: `GLM_REFRESH_TOKEN` ist gesetzt. Weitere Werte wurden nicht ausgegeben.
- Der Start liest den Token, entferntWhitespace und schreibt ihn persistent in `.env`: `llm-proxies/scripts/start-glm2api.sh:20-28`.
- Der Token erscheint dabei als Argument der verwendeten `grep`- und `sed`-Kommandos und ist damit kurzzeitig über die Prozessargumente sichtbar.
- `sed`-Ersetzungen escapen den Token nicht. Tokens mit für `sed` relevanten Zeichen könnten beschädigt werden; ein fehlender `GLM_REFRESH_TOKEN`-Block würde still nicht ergänzt.
- Im aktuellen Dateisystem hat `.env` den Modus `0666`. Das kann eine Workspace-Mount-Eigenschaft sein, ist aber als Ist-Zustand festzuhalten; andere lokale Benutzer könnten die Datei lesen oder verändern.
- Die operative Vorlage aktiviert `DEBUG_DUMP_ALL=true` und dokumentiert ausdrücklich Roh-Requests, Roh-Upstream-Daten und Roh-SSE: `llm-proxies/glm2api.env:24-30`. Da sich die lokale `.env` nur beim Refresh-Token unterscheidet, gilt dies auch dort.
- Der MAIN-Prozessstdout geht nach `/tmp/opencode/glm2api.log`, der Bundle-Prozessstdout nach `/tmp/glm2api.log`: `llm-proxies/scripts/start-glm2api.sh:9,48` und `llm-proxies/scripts/bundle/start.sh:7,33-35`.

**Positiv**

- `HOST` ist auf Loopback begrenzt und `SERVER_API_KEYS` ist in der getrackten Vorlage leer: `llm-proxies/glm2api.env:14,41-47`.
- Die getrackte Vorlage selbst enthält keinen Refresh-Token.
- `.env` und `glm2api.pid` werden durch Git ignoriert: `llm-proxies/glm2api/.gitignore:12-20`.

**Auswirkung**

- Prompts, Tool-Argumente oder Upstream-Daten können in Debug-Logs und Runtime-Dateien landen.
- Bei einer LAN-Änderung von `HOST=0.0.0.0` bleiben Auth und CORS standardmäßig offen, sofern nicht gleichzeitig `SERVER_API_KEYS` gesetzt wird.

### H-04 — Mittel: venv- und Dependency-Reproduzierbarkeit ist nur teilweise gegeben

**Bestätigt**

- `.python-version` fordert 3.14: `llm-proxies/glm2api/.python-version:1`.
- `pyproject.toml` fordert `>=3.14`: `llm-proxies/glm2api/pyproject.toml:10`.
- `uv.lock` fordert ebenfalls `>=3.14` und enthält Hashes für die aufgelösten Dev-Pakete: `llm-proxies/glm2api/uv.lock:1-79`.
- Im Workspace ist ein `.venv` mit `python`, `python3` und `python3.14` vorhanden. Es wurde nicht ausgeführt.

**Lücken**

- `uv` selbst ist nicht versioniert. Fehlt es, wird ein unversioniertes Installerskript per `curl | sh` verwendet: `llm-proxies/rebuild.sh:41-45` und `llm-proxies/scripts/bundle/install.sh:8-12`.
- Python 3.14 ist nicht patch- und buildgenau gepinnt.
- `uv sync --frozen` in `llm-proxies/rebuild.sh:47-49` verhindert eine Lock-Aktualisierung, prüft aber nicht explizit, dass das Lockfile zum aktuellen `pyproject.toml` frisch ist. Die Behauptung einer garantierten Lock-Synchronität in `llm-proxies/rebuild.sh:37-40` ist zu stark.
- Die Bundle-Installation verwendet nur `uv sync`, nicht `--frozen`, `--locked` oder `--no-dev`: `llm-proxies/scripts/bundle/install.sh:23`.
- `pyproject.toml` enthält eine Dev-Gruppe mit pytest: `llm-proxies/glm2api/pyproject.toml:16-17`; das Lockfile enthält pytest und seine Transitivabhängigkeiten: `llm-proxies/glm2api/uv.lock:29-79`. Ein normaler `uv sync` ist daher nicht als reine Runtime-Installation dokumentiert.
- Die Build-System-Abhängigkeiten `setuptools>=61.0` und `wheel` sind nicht exakt gepinnt: `llm-proxies/glm2api/pyproject.toml:1-3`.
- Beide Startskripte verwenden `uv run` ohne Frozen-/Locked-Modus: `llm-proxies/scripts/start-glm2api.sh:48` und `llm-proxies/scripts/bundle/start.sh:34`. Ein Start kann daher die Umgebung prüfen, verändern oder bei Drift Pakete nachladen.

### H-05 — Mittel: Prozess- und Portstart ist fragil

**Beobachtung**

- Der MAIN-Start ist auf `/workspaces/MAIN` fest verdrahtet: `llm-proxies/scripts/start-glm2api.sh:7-10`. `rebuild.sh` selbst ist relativ zum Repo robust, aber `--start` delegiert anschließend an diesen absoluten Pfad.
- Vorab werden weder `uv` noch `ss`, `curl`, `jq`, `setsid`, `nohup`, `seq` noch das Zielverzeichnis `/tmp/opencode` geprüft.
- Fehlt `ss`, gilt der Port durch die fehlgeschlagene Pipeline als frei; fehlt `jq`, kann ein tatsächlich laufender MAIN-Proxy als „fremd“ eingestuft werden.
- Die Erkennung stützt sich bei belegtem Port nur auf `/health`; ein beliebiger Dienst mit gleichem Health-Format kann als glm2api gelten. Das Bundle akzeptiert jeden HTTP-200-Health-Response: `llm-proxies/scripts/bundle/start.sh:22-30`.
- Zwischen Portprüfung und Start gibt es keinen Lock. Zwei gleichzeitige Starts können beide den freien Port sehen.
- Nach einem fehlgeschlagenen Health-Timeout wird ein möglicherweise gestarteter Prozess nicht beendet und nicht eindeutig identifiziert.
- Weder MAIN- noch Bundle-Start schreiben eine PID-Datei. Die vorhandene, ignorierte `glm2api.pid` ist im geprüften Start-/Rebuild-Pfad unbenutzt; ob der App-Code sie selbst schreibt, wurde wegen des Code-Ausschlusses nicht geprüft.
- Der Bundle-Start redirigiert stdin nicht auf `/dev/null`, im Gegensatz zum MAIN-Start.

**Bewertung**

- Für den aktuellen Einzelstart mit vorhandenen Werkzeugen und Port 8001 ist der Ablauf plausibel.
- Idempotenz ist nur „Port belegt + Health antwortet“, nicht robuste Prozess-Eigenidentifikation oder Single-Start-Garantie.

### H-06 — Mittel: Rebuild aktualisiert Runtime-Konfiguration nicht und beschreibt Gast-Modus falsch

**Beobachtung**

- `.env` wird nur kopiert, wenn sie fehlt: `llm-proxies/rebuild.sh:23-32` und `llm-proxies/scripts/start-glm2api.sh:15-18`.
- Bestehende Dateien werden nicht mit neuen Defaults, Kommentaren oder neuen Variablen migriert. Nur der Refresh-Token wird gesondert ersetzt.
- Die operative Vorlage setzt `GLM_USE_GUEST_REFRESH_TOKEN=false`: `llm-proxies/glm2api.env:63-67`.
- `rebuild.sh` meldet nach dem Kopieren dennoch „Guest-Mode aktiv“: `llm-proxies/rebuild.sh:23-27`.
- Auch die Bundle-Installation meldet „Guest-Mode aktiv“: `llm-proxies/scripts/bundle/install.sh:15-19`.
- Die Bundle-Doku behauptet `GLM_USE_GUEST_REFRESH_TOKEN=true`: `llm-proxies/scripts/bundle/README.md:51-59`.
- Tatsächlich bewirkt `false` laut derselben Vorlage nur dann expliziten Gastbetrieb, wenn weder Token-Datei noch Token gesetzt sind; dann greift der dokumentierte automatische Fallback. Mit injiziertem Refresh-Token läuft die aktuelle lokale Konfiguration nicht im expliziten Gast-Modus.

**Zusatz**

- `rebuild.sh` verwendet `set -uo pipefail`, aber nicht `set -e`: `llm-proxies/rebuild.sh:13`. Fehler beim Kopieren von `.env` oder beim `mkdir -p` werden nicht zuverlässig als sofortiger Abbruch behandelt.
- Kommentar und Wert widersprechen sich direkt: `llm-proxies/glm2api.env:16-18` sagen „default stays at 8000“, gesetzt ist 8001.

### H-07 — Mittel: Bundle-Vollständigkeit, Voraussetzungen und Installationsanleitung stimmen nicht überein

**Beobachtung**

- Das Bundle wird als vollständig und in „jeder Linux/WSL-Umgebung mit bash + curl“ startklar beschrieben: `llm-proxies/scripts/bundle/README.md:1-5,28-32`.
- Tatsächlich benötigen die Skripte unter anderem `ss`, `setsid`, `nohup`, `curl`, `tail`, `seq`, Dateikopier-/Verzeichniswerkzeuge und für den Build zusätzlich `zip`, `unzip`, `md5sum`, `find` und GNU-artiges `touch -d`.
- `ss` und `setsid` fehlen auf vielen minimalen Linux-Installationen und auf macOS in der vorausgesetzten Form. Die Doku nennt macOS nur „mit angepassten Pfaden“, nicht mit angepassten Werkzeugen: `llm-proxies/scripts/bundle/README.md:28-32`.
- Die Bundle-README nennt `README.md` „chinesisch“: `llm-proxies/scripts/bundle/README.md:19`; die tatsächlich mitgelieferte Datei ist deutsch: `llm-proxies/glm2api/README.md:1-4`.
- Sie behauptet „zero dependencies“ und ein Lockfile „nur das Projekt selbst“: `llm-proxies/scripts/bundle/README.md:12-17`; `uv.lock` enthält dagegen pytest und fünf weitere Paketeinträge.
- Sie nennt Debug-Logs unter `app/log/`: `llm-proxies/scripts/bundle/README.md:51-59`; der Bundle-Start schreibt mindestens den Prozessstdout nach `/tmp/glm2api.log`.
- Das ZIP besitzt einen äußeren Ordner `glm2api-bundle/`. Die Startanleitung beginnt direkt mit `bash scripts/install.sh`, ohne explizites Wechseln in diesen Ordner: `llm-proxies/scripts/bundle/README.md:34-39`. `infrastructure.md:105-112` beschreibt denselben Schritt ebenfalls ohne Wrapper-`cd`.
- Das externe Doku-File existiert aktuell, wird aber im Build nur optional kopiert. Die README nennt es als festen Inhalt: `llm-proxies/scripts/bundle/README.md:24-25`.
- `structure.md` verspricht das komplette glm2api-Verzeichnis ohne Runtime-Artefakte: `llm-proxies/glm2api/structure.md:168-175`; die Builder-Liste lässt `optimierung.md` aus.

### H-08 — Niedrig: Beispielconfig, Smoke-Test und Doku-Verweise veralten

**Beobachtung**

- `README.md` verweist für „alle weiteren Config-Variablen“ auf `.env.example`: `llm-proxies/glm2api/README.md:53`.
- `GLM_PERSISTENT_CONVERSATION` fehlt dort, ist aber in der operativen Vorlage enthalten: `llm-proxies/glm2api.env:86-88`.
- Weitere in `optimierung.md` dokumentierte Variablen wie `GLM_HISTORY_MAX_CHARS`, `GLM_EMPTY_RESPONSE_MAX_RETRIES` und `GLM_BLOCKED_TOOL_FOLLOW_UPS` stehen in keiner der beiden geprüften Env-Vorlagen.
- Der Smoke-Test verwendet standardmäßig `glm-4.7-flash`: `llm-proxies/scripts/smoke-test.sh:8-10`, während die Bundle-Nutzung `glm-5.3` zeigt: `llm-proxies/scripts/bundle/README.md:41-47`.
- Der Smoke-Test unterstützt keine `SERVER_API_KEYS`-Authentifizierung und schreibt nach `/tmp/opencode/`, ohne den Ordner anzulegen: `llm-proxies/scripts/smoke-test.sh:31-39,52-68`.
- `llm-proxies/scripts/smoke-test.sh:3` verweist auf `glm-api-audit.md`; im Workspace wurde keine Datei dieses Namens gefunden.
- `llm-proxies/glm2api/optimierung.md:100-105` verweist auf `io_utils.py`; diese Datei ist in der ausgeschlossenen, aber strukturell erfassten `src/glm2api/`-Struktur nicht vorhanden.
- `llm-proxies/glm2api/.gitignore:16` ignoriert ein lokales `docs/`-Verzeichnis. Aktuell existiert dort kein Docs-Ordner.

## 4. Port-, venv-, Secret- und Prozessmatrix

| Bereich | Erwartung | Statischer Status | Anmerkung |
|---|---|---|---|
| Standard-Port | 8001 | PASS | Vorlage, MAIN-Start, Smoke und Bundle-Start stimmen überein. |
| Beispiel-Port | 8000 in `.env.example` | PASS | Abweichung ist als Beispielwert erklärbar. |
| Freier Host-Port | 8001 | PASS | Nur für unveränderte `.env`; Skript liest App-Konfiguration nicht. |
| Belegter Fremdport | Fehler | TEILWEISE | Erkennung über Health, nicht Prozessidentität; `ss`-/Tool-Abhängigkeiten ungeprüft. |
| Host-Override MAIN | aus `.env` | NEIN | Skript fixiert Host/Port für den Check. |
| Host/Port-Override Bundle | dokumentiert | NEIN | `GLM_HOST`/`GLM_PORT` sind im Paket nicht als App-Konfiguration belegt. |
| Python | 3.14 | PASS | `.python-version`, `pyproject.toml`, `uv.lock` stimmen überein. |
| venv | vorhanden und nutzbar | NUR STRUKTURELL | `python3.14` vorhanden; Ausführung ausdrücklich unterlassen. |
| Lock-Synchronität | garantiert | NEIN | `--frozen` ist keine explizite Freshness-Prüfung. |
| uv-Version | gepinnt | NEIN | nicht versioniert. |
| Runtime-Dependencies | keine externen | TEILWEISE | App-Laufzeit ist stdlib-basiert; Installation kann Dev-Packages und Build-Isolation laden. |
| Getrackte Vorlage | secret-frei | PASS | Token und Server-Keys leer. |
| Lokale `.env` | secret-bearing, ignoriert | BEFAUND | Refresh-Token gesetzt; Modus aktuell 0666. |
| Debug-Daten | nicht standardmäßig | NEIN | Operative Vorlage aktiviert Raw-Debug-Dump. |
| Prozess-ID | belastbar | NEIN | Kein Start-Lock; vorhandene PID-Datei im Startpfad unbenutzt. |
| Prozess-Herkunft | eindeutig | NEIN | Health-Response genügt als Identitätsnachweis. |
| Autostart-Querverweise | konsistent | TEILWEISE | `infrastructure.md` verweist auf vorhandene Rebuild-/Startskripte; Watchdog-/Setup-Code war außerhalb des Scopes. |

## 5. Rebuild- und Startbewertung

### Rebuild

**Positiv**

- Relativer Repo-Root und klare Abbruchprüfungen für Source, Env-Quelle, uv-Sync und venv-Python: `llm-proxies/rebuild.sh:15-22,41-56`.
- `uv sync --frozen` läuft immer und repariert unvollständige venvs zumindest hinsichtlich des vorhandenen Lock-Inhalts.
- Secret-Werte werden nicht aus der Vorlage oder im Report ausgegeben.

**Negativ**

- Kein `set -e`; einfache Kopier-/Verzeichnisfehler werden nicht konsistent abgefangen.
- Kein uv-/Python-Pin.
- `--frozen` garantiert keine aktuelle Lock-Übereinstimmung.
- Bestehende `.env` wird nicht migriert.
- Erfolgs- und Gast-Modusmeldung sind irreführend.
- Fehlendes uv startet eine unversionierte Netzinstallation; dies war Teil der Skriptannahme, wurde hier nicht ausgeführt.

### MAIN-Start

**Positiv**

- Portkonflikt wird nicht blind akzeptiert.
- Health-Wait bis 60 Sekunden ist vorhanden.
- MAIN-Start entkoppelt stdin, stdout und stderr über `setsid`, `nohup` und `</dev/null`.

**Negativ**

- Absolute Repo-Pfade.
- Keine Werkzeug-/Logverzeichnis-Vorprüfung.
- Schwache Prozessidentität, keine Parallelstart-Sperre, kein PID-Management.
- Secret-Injektion über unescaped `grep`/`sed`-Argumente.
- Bei Timeout keine eindeutige Aufräum- oder Diagnose-ID.

### Bundle-Start/Install

**Positiv**

- Relative Bundle-Pfade.
- Env-Fallback und Health-Wait sind vorhanden.
- venv-Verzeichnis wird vor Start geprüft.

**Negativ**

- Dokumentierte Port-/Host-Overrides sind nicht verpackbar belegt.
- Nur Verzeichnisexistenz statt venv-/uv-/Python-Sanity.
- Kein stdin-Redirect, keine Lock-/PID-Logik, nur HTTP-200 als Identität.
- `uv sync` ist nicht Frozen/Locked und nicht auf Runtime-Dev-Abhängigkeit beschränkt.
- uv-Installation ist unversioniert und netzabhängig.

## 6. Bundle-Bewertung

### Buildinhalt

- Enthalten: `src/`, `tests/`, `main.py`, `pyproject.toml`, `uv.lock`, README, Struktur, LICENSE, Beispiel-Env, operative Env, `.python-version`, `.gitignore`, zwei portable Skripte, Root-README und optionale externe Doku.
- Nicht enthalten: `optimierung.md`, echte `.env`, Logs, venv, Caches, egg-info.
- Das getrackte Ziel ist `dist/glm2api-bundle.zip`; `dist/glm2api-bundle/` ist der ignorierte Stage-Baum.

### Verifikationsreichweite

- Source-Python: MD5-Abgleich.
- Tests: nur Namens-/Existenzprüfung.
- Alles andere: keine Inhaltsverifikation.
- Optionale Doku: kein Fail-on-missing.
- ZIP-Determinismus: nur Zeitstempel normalisiert; Dateimodus, Reihenfolge und Toolchain nicht vollständig normalisiert.

### Ergebnis

Das Bundle ist als manueller Export grundsätzlich nachvollziehbar, erfüllt aber die dokumentierten Zusagen „strukturell ausgeschlossen“, „byte-identisch“ und „vollständig“ nicht streng genug.

## 7. Verzeichnisstruktur

### `llm-proxies/`

```text
llm-proxies/
├── rebuild.sh                         geprüft
├── glm2api.env                        geprüft
├── scripts/                           geprüft
│   ├── build-bundle.sh
│   ├── smoke-test.sh
│   ├── start-glm2api.sh
│   └── bundle/
│       ├── README.md
│       ├── install.sh
│       └── start.sh
├── antigravity-proxy/                 außerhalb Scope, nicht abgestiegen
└── dist/                              außerhalb Inhaltsscope
    ├── glm2api-bundle.zip             getrackt, Inhalt nicht geprüft
    └── glm2api-bundle/                ignoriert, nur Top-Level-Struktur
```

### `llm-proxies/glm2api/`

```text
glm2api/
├── .env                               vollständig strukturell geprüft, Werte redigiert
├── .env.example                       geprüft
├── .gitignore                         geprüft
├── .python-version                    geprüft
├── LICENSE                            geprüft
├── glm2api.pid                        geprüft
├── main.py                            geprüft
├── optimierung.md                     geprüft
├── pyproject.toml                     geprüft
├── README.md                          geprüft
├── structure.md                       geprüft
├── uv.lock                            geprüft
├── .venv/                             nur Struktur
│   ├── .gitignore
│   ├── .lock
│   ├── CACHEDIR.TAG
│   ├── pyvenv.cfg
│   ├── bin/                           python, python3, python3.14 vorhanden
│   ├── lib/
│   └── lib64/
├── .pytest_cache/                     nur Struktur; Git-ignoriert
├── log/                               nur Struktur; Git-ignoriert
│   ├── glm2api_output.log
│   ├── glm2api_debug.log
│   ├── glm2api_debug.log.1
│   ├── glm2api_debug.log.2
│   ├── glm2api_debug.log.3
│   ├── glm2api_debug.log.4
│   └── glm2api_debug.log.5
├── src/                               CODE AUSCHLUSS, nur Struktur
│   ├── glm2api.egg-info/               generiert, Git-ignoriert
│   └── glm2api/
│       ├── __init__.py
│       ├── __main__.py
│       ├── app.py
│       ├── config.py
│       ├── logging_utils.py
│       ├── model_variants.py
│       ├── server.py
│       ├── services/
│       │   ├── __init__.py
│       │   ├── anthropic_adapter.py
│       │   ├── glm_auth.py
│       │   ├── glm_client.py
│       │   ├── responses_adapter.py
│       │   └── translator.py
│       └── utils/
│           ├── __init__.py
│           ├── tool_parser.py
│           └── tool_protocol.py
├── tests/                             AUSCHLUSS, nur Dateinamen
│   ├── __pycache__/
│   ├── test_config.py
│   ├── test_model_variants.py
│   ├── test_protocol_adapters.py
│   ├── test_stream_retry.py
│   ├── test_tool_parser.py
│   └── test_translator.py
├── benchmarks/                        AUSCHLUSS, nur Dateinamen
│   ├── __pycache__/
│   ├── benchmark.md
│   └── verify_auditmesh.py
├── app/                               nicht vorhanden
├── scripts/                           nicht vorhanden
└── docs/                              nicht vorhanden; lokal ignoriert
```

## 8. Vollständige Dateiliste und Prüfstatus

Statusdefinition:

- **OK**: innerhalb des erlaubten Inhaltsscopes vollständig geprüft, kein eigener Befund.
- **BEFUND**: vollständig geprüft, mindestens eine inkonsistente Annahme oder Dokuaussage.
- **NUR REFERENZ**: vollständig geprüft, Aussage konnte wegen des ausgeschlossenen Codes nicht verifiziert werden.

| Datei | Zeilen | Status | Ergebnis |
|---|---:|---|---|
| `llm-proxies/rebuild.sh` | 63 | BEFUND | Fehlende Fail-fast-Semantik, unversioniertes uv, `--frozen` nicht als Freshness-Garantie, irreführender Gast-Hinweis. |
| `llm-proxies/glm2api.env` | 124 | BEFUND | Secret-frei, aber expliziter Gast-Modus `false`, Raw-Debug aktiv, Portkommentar widersprüchlich. |
| `llm-proxies/scripts/start-glm2api.sh` | 60 | BEFUND | Absolute Pfade, feste Portannahme, ungeprüfte Werkzeuge/Logablage, schwache Identität, Secret-Sed-Injektion. |
| `llm-proxies/scripts/build-bundle.sh` | 76 | BEFUND | Optionale Doku, unvollständige Verifikation, keine vollständige Determinismusnormalisierung, keine Atomizität. |
| `llm-proxies/scripts/smoke-test.sh` | 71 | BEFUND | Veraltetes Defaultmodell, keine Auth-Unterstützung, `/tmp/opencode`-Annahme, fehlender Referenzbericht. |
| `llm-proxies/scripts/bundle/install.sh` | 23 | BEFUND | Nicht-Frozen-Sync, unversioniertes uv, irreführender Gast-Hinweis. |
| `llm-proxies/scripts/bundle/start.sh` | 46 | BEFUND | Port-Override unbelegt, Werkzeugabhängigkeiten, schwache Health-Identität, kein stdin-Redirect/Lock/PID. |
| `llm-proxies/scripts/bundle/README.md` | 78 | BEFUND | Gastwert, dependency count, Logziel, Voraussetzungen, Originalsprache und Entpackpfad inkonsistent. |
| `llm-proxies/glm2api/.env` | 124 | BEFUND | Vollständig strukturell gelesen; 25 eindeutige Keys, keine Duplikate, Refresh-Token gesetzt, nur dieser Wert weicht von der Vorlage ab, Modus 0666. |
| `llm-proxies/glm2api/.env.example` | 120 | BEFUND | `GLM_PERSISTENT_CONVERSATION` fehlt; nicht alle in Doku genannten Configvariablen sind enthalten. |
| `llm-proxies/glm2api/.gitignore` | 20 | BEFUND | `.env`, venv, Logs und PID korrekt ignoriert; lokales `docs/` pauschal ignoriert. |
| `llm-proxies/glm2api/.python-version` | 1 | OK | 3.14 stimmt mit Projektmetadaten überein. |
| `llm-proxies/glm2api/LICENSE` | 674 | OK | GPL-3.0-Text vollständig gelesen; im Bundle-Kopierplan enthalten. |
| `llm-proxies/glm2api/glm2api.pid` | 1 | BEFUND | Numerischer Runtime-Wert; im geprüften Startpfad unbenutzt, keine belastbare Prozesssteuerung. |
| `llm-proxies/glm2api/main.py` | 4 | OK | Import-/Entry-Point-Kette konsistent zum `pyproject.toml`; App-Zielmodul nicht inhaltlich geprüft. |
| `llm-proxies/glm2api/optimierung.md` | 153 | BEFUND | Offenes Encoding-Thema klar dokumentiert; ein Verweis auf nicht vorhandenes `io_utils.py`. |
| `llm-proxies/glm2api/pyproject.toml` | 23 | BEFUND | Python/Entry-Point konsistent; Build-Requirements nicht exakt gepinnt, Dev-Gruppe widerspricht Runtime-only-Doku. |
| `llm-proxies/glm2api/README.md` | 65 | BEFUND | `.env.example` wird als vollständig dargestellt, ist es für die operative Vorlage nicht. |
| `llm-proxies/glm2api/structure.md` | 179 | BEFUND | Dateistruktur passt; Komponentenbeschreibung wegen Code-Ausschluss unverifiziert, Bundle-Vollständigkeit ist überzogen. |
| `llm-proxies/glm2api/uv.lock` | 79 | BEFUND | Paketversionen und Hashes vorhanden; Dev-Pakete widersprechen „nur Projekt/zero dependencies“, Build-Isolation ist nicht vollständig im Lock abgebildet. |

## 9. Querverweisprüfung

| Referenz | Status | Anmerkung |
|---|---|---|
| `rebuild.sh` → `llm-proxies/glm2api/` | PASS | Source-, venv- und Env-Pfade vorhanden. |
| `rebuild.sh --start` → `start-glm2api.sh` | PASS | Datei vorhanden; Zielpfad MAIN ist absolut. |
| `main.py` → `glm2api.__main__:main` | PASS | Zielpfad ist in der Struktur vorhanden; Codeinhalt ausgeschlossen. |
| `pyproject.toml` → README/Source-Layout | PASS | Package-Layout und Readme-Ziel vorhanden. |
| `glm2api.env` → `HOST`, `PORT` | PASS | Startskripte lesen diese Werte nicht zuverlässig ein. |
| Start → `/health` | NUR REFERENZ | Endpoint in Doku beschrieben; App-Code ausgeschlossen. |
| `build-bundle.sh` → externe Reasoning-Doku | PASS, nicht hart | Datei existiert; Build behandelt Fehlen als Erfolg. |
| Bundle-README → `app/structure.md` | PASS | Builder kopiert die Datei. |
| Bundle-README → `docs/chatglm-reasoning-modes.md` | BEFUND | Datei derzeit vorhanden, aber optional und nicht verifiziert. |
| `smoke-test.sh` → `glm-api-audit.md` | FEHLT | Im Workspace nicht gefunden. |
| `optimierung.md` → `io_utils.py` | FEHLT | In der erfassten `src/glm2api/`-Struktur nicht vorhanden. |
| App-README → `infrastructure.md` | PASS | Relevante Abschnitte existieren und wurden für Konsistenz herangezogen. |
| `infrastructure.md` → Rebuild/Start/Bundle | PASS | Befehle und Pfade existieren. |
| `infrastructure.md` → deterministische Driftfreiheit | BEFUND | Garantie stärker als der geprüfte Builder. |
| `infrastructure.md` → Port 8001/Refresh-Token | PASS für Standard | Vorlage liefert Port; Token kommt optional über Secret-Injektion. |

## 10. Empfohlene Reihenfolge zur Behebung

1. Port-/Host-Ermittlung und Bundle-Override konsistent machen oder die nicht belegte Doku entfernen.
2. Bundle-Build als vollständigen Manifest-Build ausführen: fehlende Dateien hart fehlschlagen, alle Inhalte hashen, Dateiliste und Modi normalisieren, temporär bauen und atomar ersetzen; getracktes ZIP gegen eine Prüfsumme/Matrix absichern.
3. Runtime-Start auf vorhandene venv-Python oder einen explizit Frozen-/Locked-uv-Aufruf festlegen; uv- und Pythonversion definieren.
4. Prozessstart mit Werkzeug-Preflight, Logzielanlage, Lock, eindeutiger PID und Health-Signatur versehen.
5. Bestehende `.env` durch eine versionierte, nicht-zerstörende Migration aktualisieren; Gast-Aussagen an `false`/Fallback anpassen.
6. Refresh-Token ohne Übergabe im `sed`-Argument und mit restriktiven Dateirechten behandeln; Raw-Debug nicht als Default betreiben.
7. Bundle-Abhängigkeiten, macOS-/Linux-Matrix, Logpfade, Entpackpfad, Originallanguage und Dependency-Aussagen korrigieren.
8. Fehlende Verweise korrigieren oder als historische Referenzen markieren.

## 11. Grenzen der Aussage

- Alle POSIX-, Python-, uv-, ZIP- und Betriebsannahmen sind statisch aus Dateiinhalt und Verzeichnisstruktur abgeleitet.
- Es wurde kein App-Code unter `src/` bewertet; Aussagen zu tatsächlicher Env-Priorität, Logging, Health-JSON, Entry-Point-Verhalten oder Token-Persistenz bleiben außerhalb dieses Scopes.
- Tests und Benchmarks wurden weder gelesen noch ausgeführt; dokumentierte Testzahlen sind daher nicht verifiziert.
- Das bestehende ZIP wurde nicht gebaut, entpackt, gestartet oder gegen den Source gehasht; seine aktuelle Freshness ist unbekannt.
- Keine laufenden PIDs, Listener oder Health-Endpunkte wurden geprüft.
- Die beobachteten Dateimodi sind Ist-Zustände des aktuellen Dateisystems und wurden nicht mit Git-Modi gleichgesetzt.
- Es wurden keine Secrets ausgegeben und keine Quelldateien verändert.
<!-- END PART H -->

## Anhang I — glm2api: produktiver Python-Anwendungscode

<!-- BEGIN PART I -->
## Partition I — Statischer Audit des produktiven Python-Codes von `glm2api`

**Stand:** 2026-09-24
**Arbeitsverzeichnis:** `/workspaces/MAIN`
**Prüfungsart:** ausschließlich lokale statische Prüfung
**Snapshot-Grenze:** Die nachfolgenden Source-Umfänge und Zeilenbereiche sind ein historischer I-Report vor U. Für die extern geänderten Dateien ist U der maßgebliche Delta-Report; I wird nicht als vollständiger aktueller Source-Audit gelesen.

## 1. Scope und Vollständigkeitsnachweis

Der in der Aufgabenstellung genannte Pfad `llm-proxies/glm2api/app/` existiert im aktuellen Stand nicht. Der produktive Python-Anwendungscode liegt stattdessen unter `llm-proxies/glm2api/src/glm2api/`; der ausführbare Root-Einstieg ist `llm-proxies/glm2api/main.py`. Dieses alternative Layout wurde deshalb vollständig in den Scope aufgenommen.

Vollständig gelesen wurden **17 produktive Python-Dateien mit 7.142 Zeilen**:

| Datei | vollständig gelesener Bereich | Zeilen |
|---|---:|---:|
| `llm-proxies/glm2api/main.py` | 1–4 | 4 |
| `llm-proxies/glm2api/src/glm2api/__init__.py` | 1–5 | 5 |
| `llm-proxies/glm2api/src/glm2api/__main__.py` | 1–34 | 34 |
| `llm-proxies/glm2api/src/glm2api/app.py` | 1–107 | 107 |
| `llm-proxies/glm2api/src/glm2api/config.py` | 1–351 | 351 |
| `llm-proxies/glm2api/src/glm2api/logging_utils.py` | 1–226 | 226 |
| `llm-proxies/glm2api/src/glm2api/model_variants.py` | 1–46 | 46 |
| `llm-proxies/glm2api/src/glm2api/server.py` | 1–483 | 483 |
| `llm-proxies/glm2api/src/glm2api/services/__init__.py` | 1–1 | 1 |
| `llm-proxies/glm2api/src/glm2api/services/anthropic_adapter.py` | 1–468 | 468 |
| `llm-proxies/glm2api/src/glm2api/services/glm_auth.py` | 1–325 | 325 |
| `llm-proxies/glm2api/src/glm2api/services/glm_client.py` | 1–1346 | 1346 |
| `llm-proxies/glm2api/src/glm2api/services/responses_adapter.py` | 1–627 | 627 |
| `llm-proxies/glm2api/src/glm2api/services/translator.py` | 1–1524 | 1524 |
| `llm-proxies/glm2api/src/glm2api/utils/__init__.py` | 1–1 | 1 |
| `llm-proxies/glm2api/src/glm2api/utils/tool_parser.py` | 1–1400 | 1400 |
| `llm-proxies/glm2api/src/glm2api/utils/tool_protocol.py` | 1–194 | 194 |

Bewusst nicht gelesen bzw. auditiert:

- `tests/`
- `benchmarks/`
- `.venv/`
- `.env` und andere Secret-/Runtime-Inhalte
- `Revision.md`; die Datei wurde weder verändert noch in die Bewertung einbezogen
- Nicht-Anwendungscode wie Installations-, Benchmark- und Benchmark-Copy-Skripte

Die Dateiliste wurde zusätzlich per `pathlib` inventarisiert und jede Datei mit `ast.parse` ohne Import oder Ausführung auf Python-Syntax geprüft. Alle 17 Dateien wurden erfolgreich geparst. Es erfolgten keine Server-, Netzwerk- oder Installationsversuche, und es wurden keine Secret-Werte ausgegeben.

## 2. Architektur- und Lifecycle-Befund

Die Anwendung ist **keine FastAPI-/ASGI-Anwendung**. Es gibt weder FastAPI-Abhängigkeiten noch Lifespan-/`on_event`/`Depends`-Semantik. Der Stack ist:

1. `main.py` oder `glm2api.__main__:main`
2. `create_application()` → `load_config()`
3. `Application.__init__()` → Logging, `GLMWebClient`, `GLM2APIServer`
4. `ThreadingHTTPServer` mit dynamischer `BaseHTTPRequestHandler`-Klasse
5. Eingehender JSON-Request → Adapter für OpenAI Chat, Anthropic Messages oder OpenAI Responses
6. Auth-/Token-Pool → Warteschlange → urllib-Upstream-SSE
7. Translator/Event-Akkumulator → Tool-Parser → OpenAI-SSE oder API-spezifischer SSE

Positiv: `Application.run()` besitzt ein `finally`, das `stop()` aufruft; `GLM2APIServer.shutdown()` beendet Server und Socket; Streaming-Generatoren besitzen ebenfalls `finally`-Cleanup. Problematisch sind dagegen die unbegrenzte Request-Aufnahme, die nicht abbrechbaren Ressourcenpfade und die im Bericht beschriebenen Session-/Fehlerzustände.

## 3. Priorisierte Befunde

### I-001 — Kritisch: Ein Queue-Timeout kann die gesamte Ausführungsqueue dauerhaft blockieren

**Ort:** `llm-proxies/glm2api/src/glm2api/services/glm_client.py:86-121`

`ConcurrentRequestQueue.acquire()` vergibt bei einem Queue-Timeout zwar ein Ticket, markiert dieses aber nie als abgebrochen oder freigegeben. `_release()` kann `_serving_ticket` nur dann weiterbewegen, wenn die aktuelle Ticketnummer in `_released_tickets` enthalten ist. Sobald `_serving_ticket` das verworfene Timeout-Ticket erreicht, gibt es keinen Vorgänger, der dieses Ticket freigibt.

**Auswirkung:**

- Ein einzelner legitimer Queue-Timeout kann nach dem Abschluss der vorherigen Tickets alle nachfolgenden Chat-, Image-, Datei-Upload- und SSE-Operationen dauerhaft in Timeouts laufen lassen.
- Der Fehler ist nicht auf den auslösenden Request begrenzt und schlägt auch nach dessen Ende nicht zurück.

**Empfehlung:** Timeout-Tickets unter derselben Condition als „abandoned“ atomar markieren und die servierende Sequenz vorantreiben; alternativ eine echte Priority-/Fairness-Queue mit aktiven Tickets statt monotoner Ticketnummern verwenden.

### I-002 — Kritisch: Unbegrenzte Request-Bodies, Threads und blockierende Reads ermöglichen lokale DoS

**Orte:**

- `llm-proxies/glm2api/src/glm2api/server.py:40-44`
- `llm-proxies/glm2api/src/glm2api/server.py:118-128`
- `llm-proxies/glm2api/src/glm2api/server.py:442-447`

Bevor die eigentliche GLM-Warteschlange greift, liest jeder Thread die via `Content-Length` angegebene Byteanzahl vollständig in den Speicher. Es gibt:

- kein Request-Body-Limit,
- keine Prüfung auf zu kurze/inkonsistente Body-Länge; negative Werte werden früh abgewiesen,
- keine Ablehnung von `Transfer-Encoding: chunked`,
- kein Socket-/Header-/Gesamtlaufzeit-Timeout,
- keine maximale Anzahl akzeptierter Verbindungen oder Threads,
- unbegrenztes `ThreadingHTTPServer`-Threadwachstum.

Ein langsam sendender Client kann einen Handler-Thread und die Ingress-Ressourcen lange halten; ein sehr großer Body wird vollständig allokiert.

**Empfehlung:** Harte Body- und Request-Dauerlimits, Reject-on-`Transfer-Encoding`, gehäuseweite `socket.settimeout(...)`, begrenzte Thread-/Verbindungspool, exakte Reads mit eigener Short-Read-Prüfung und 413/408/431-Antworten vor jeder Proxy-Queue.

### I-003 — Hoch: Attachment-URLs sind ein SSRF- und lokaler Dateileser

**Orte:**

- `llm-proxies/glm2api/src/glm2api/services/glm_client.py:1136-1160`
- `llm-proxies/glm2api/src/glm2api/services/glm_client.py:1162-1237`
- `llm-proxies/glm2api/src/glm2api/services/glm_client.py:1075-1081`

`_fetch_file_payload()` reicht beliebige nicht-`data:`-URLs ungeprüft an `urllib.request.urlopen()` weiter. Es gibt keine Schema-Allowlist, keine DNS-/IP-Prüfung, keine Redirect-Policy und kein Schutz vor Loopback, Link-Local, RFC1918, Cloud-Metadata oder nicht-HTTP-Schemata. `file:`- und andere von urllib unterstützte Schemata werden nicht ausgeschlossen. Bei `data:`-URLs fehlt außerdem das 100-MB-Limit, das nur für Remote-URLs existiert. Die Gesamtzahl der Referenzen pro Request ist nicht begrenzt; jeder Retry/Follow-up kann dieselben Attachments erneut laden und hochladen.

`_download_image_as_base64()` begrenzt den Upstream-Datei ebenfalls nicht und kann sehr große Bodies plus Base64-Kopien erzeugen.

**Auswirkung:** Angreifer können interne HTTP-Dienste oder erreichbare lokale Ressourcen abrufen und zum GLM-Upstream senden; mit URL-Fehlern können vertrauliche signierte URLs an Clients gelangen.

**Empfehlung:** Nur kontrollierte HTTPS-/HTTP-Quellen zulassen, alle weiteren Schemata hart ablehnen; Ziel-IP nach jeder DNS-Auflösung und jedem Redirect gegen private/reservierte Netze prüfen; Redirects manuell und begrenzt verarbeiten; Content-Length, Stream-Bytes, Gesamtzahl und Gesamtgröße pro Request begrenzen.

### I-004 — Hoch: Persistente Konversation ist ein globaler, nicht mandantenfähiger Sessionzustand

**Orte:**

- `llm-proxies/glm2api/src/glm2api/services/glm_client.py:134-157`
- `llm-proxies/glm2api/src/glm2api/services/glm_client.py:781-789`
- `llm-proxies/glm2api/src/glm2api/services/glm_client.py:592-595`

Alle Requests eines `GLMWebClient` teilen bei aktivierter Persistenz genau eine `_persistent_conversation_id`. Es gibt keine Bindung an API-Key, Client, Session oder Thread. Zusätzlich akzeptiert der Client eine frei gelieferte `conversation_id` ohne Ownership- oder Account-Bindung.

**Auswirkung:**

- Mandanten können gegenseitige Upstream-Kontexte sehen bzw. in deren Historie schreiben, abhängig davon, wie ChatGLM die gesendete Vollhistorie mit der bestehenden Conversation kombiniert.
- `new_session`/`reset_conversation` und die „last writer wins“-Aktualisierung nach dem Request erzeugen Race Conditions mit laufenden Requests.
- Ein 400/404 für eine Conversation setzt den globalen Zustand zurück, auch wenn die ID client- oder request-spezifisch war (`glm_client.py:863-867`).
- Die Conversation wird nicht an den tatsächlich erfolgreichen Account gebunden; Tickets verteilen Requests auf Accounts, während nur eine ID global gespeichert wird.

**Empfehlung:** Standardmäßig strikt stateless bleiben. Persistenz nur als explizite, serverseitig verwaltete Session-ID pro authentifiziertem Mandanten; Conversation-Zuordnung in einer atomaren Map mit Account-Bindung und Request-Lock. Client-IDs niemals als Eigentumsnachweis akzeptieren.

### I-005 — Hoch: Debug-Modus protokolliert Auth-Header, Tokens und vollständige Nutzer-/Tool-Daten

**Orte:**

- `llm-proxies/glm2api/src/glm2api/config.py:266-268`
- `llm-proxies/glm2api/src/glm2api/logging_utils.py:188-200,207-226`
- `llm-proxies/glm2api/src/glm2api/server.py:126-153,469-475`
- `llm-proxies/glm2api/src/glm2api/services/glm_auth.py:201-202,248-249`
- `llm-proxies/glm2api/src/glm2api/services/glm_client.py:840-845,927-928,946-951,1168-1204`

`DEBUG_DUMP_ALL` erzwingt DEBUG-Logging und damit zusätzlich die rotierende Datei. `debug_dump()` redigiert nichts. Seriellisiert werden unter anderem:

- eingehende Authorization- und `x-api-key`-Header,
- Upstream-Authorization-Header mit Access-Tokens,
- vollständige Request-/Response-Bodies,
- Prompt-, Tool-, Datei- und Attachment-Inhalte,
- rohe Attachment-Bodies,
- potenziell signierte Attachment-URLs.

**Auswirkung:** Ein Debug-Start kann Secrets und private Inhalte in Konsole und `log/glm2api_debug.log` kopieren; die Datei ist dann über den Backup-Bestand mehrfach persistent.

**Empfehlung:** Header-Allowlist und konsequente Redaktion von Authorization, API-Key, Cookie, Token, Query-Secrets und signierten URLs. Binär-/Attachment-Inhalte nur als Hash/Metadaten. Debug-Dump und Request-Body-Logging standardmäßig als getrenntes, explizit gefährliches Feature behandeln.

### I-006 — Hoch: Token-Pool-Rennen können Refresh-Tokens überschreiben oder Guest-Tokens redundant erzeugen

**Orte:**

- `llm-proxies/glm2api/src/glm2api/services/glm_auth.py:162-180`
- `llm-proxies/glm2api/src/glm2api/services/glm_auth.py:182-225`
- `llm-proxies/glm2api/src/glm2api/services/glm_auth.py:267-312`
- `llm-proxies/glm2api/src/glm2api/services/glm_client.py:394-399,442-597`

Der Cache-Lookup ist gelockt, der eigentliche Refresh aber nicht. Mehrere gleichzeitige Requests desselben Accounts können denselben alten Refresh-Token benutzen. Die anschließende Double-Check-Logik verhindert nur doppelte Cache-Gewinner; sie verhindert weder mehrere Token-Rotationen noch veraltete Persistenzschreibvorgänge. `_persist_refresh_token()` serialisiert nur den Dateizugriff, nicht den Read-Modify-Write-Zyklus pro Account. Ein älterer Refresh kann einen bereits neueren Token aus `config.glm_refresh_tokens` wieder zurückschreiben.

Zusätzlich wird bei **jedem** `UpstreamAPIError` der Access-Token invalidiert und der Account gewechselt, unabhängig vom HTTP-Status (`glm_auth.py:314-325`, `glm_client.py:1323-1341`). Ein deterministischer 400er wird damit auf mehreren Accounts wiederholt.

**Empfehlung:** Pro Account einen Condition-Variable-Refresh-Lock mit Single-Flight; atomare, versionierte Token-Persistenz; nur 401/403, Token-/Netzwerkfehler und klar account-spezifische Fehler rotieren. Guest-Refreshes mit Jitter und zentraler Single-Flight-Struktur versehen.

### I-007 — Hoch: Abgeschnittene oder fehlgeschlagene Streams werden als Erfolg maskiert

**Orte:**

- `llm-proxies/glm2api/src/glm2api/services/glm_client.py:1083-1134`
- `llm-proxies/glm2api/src/glm2api/services/glm_client.py:491-556,557-582`
- `llm-proxies/glm2api/src/glm2api/server.py:237-276,292-358`
- `llm-proxies/glm2api/src/glm2api/services/anthropic_adapter.py:432-445`
- `llm-proxies/glm2api/src/glm2api/services/responses_adapter.py:579-615`

`_iter_sse_events()` beendet bei `IncompleteRead` das Reading, liefert aber keinen Fehlerzustand. Fehlt ein abschließendes `finish`, finalisiert der Client den Turn dennoch als `stop`; nicht parsebare SSE-Blöcke werden verworfen. Bei Anthropic wird danach `message_stop` gesendet, bei Responses `response.completed`; der tatsächliche Fehler wird nur geloggt. Bei noch nicht gestarteten Adaptern kann die HTTP-200-Antwort vollständig leer bleiben.

**Auswirkung:** Clients glauben, eine vollständige erfolgreiche Antwort erhalten zu haben, obwohl Inhalt fehlt, unvollständig ist oder die Anfrage mitten im Upstream abbrach. Das ist besonders problematisch bei Agenten- und Tool-Loops.

**Empfehlung:** Strikte SSE-Terminierungsregel: EOF ohne `[DONE]`/Finish ist ein `truncated_stream`-Fehler; unparsebare Events und leere erfolgreiche Streams sind ebenfalls Fehler. Nach SSE-Headern einen API-spezifischen `error`-/`response.failed`-Event senden, niemals `completed`; Completion-Events nur nach validem Upstream-Ende.

### I-008 — Hoch: History-Kompression trennt genau die geschützten Tool-Paare

**Ort:** `llm-proxies/glm2api/src/glm2api/services/translator.py:546-637`

Für ein `tool`-Result am Index `i` werden Assistant und Result zunächst gemeinsam in `kept` eingefügt, anschließend aber `messages[boundary - 1:]` mit `boundary = i + 1` verwendet. Der Slice beginnt damit erneut beim Tool-Result; der zuvor eingefügte Assistant-Call wird aus dem originalen Slice verworfen. Das Result bleibt ohne Call. Außerdem deckt der Code bei einem einzelnen zu großen neuesten Message dennoch `messages[:len-1]` auf und gibt diese unbegrenzte Message plus Summary zurück, sodass das Budget deutlich überschritten werden kann.

**Empfehlung:** Kompression auf Index-/Segmentebene mit expliziten atomaren Tool-Runden, danach validieren, dass jedes Result einen unmittelbar vorherigen Call besitzt. Eine einzelne nicht komprimierbare Message separat behandeln und ein hartes Gesamtsize-Limit vor dem Request erzwingen.

### I-009 — Hoch: Tool-Heuristiken akzeptieren Calls auch ohne deklarierte Tools

**Orte:**

- `llm-proxies/glm2api/src/glm2api/utils/tool_parser.py:782-915`
- `llm-proxies/glm2api/src/glm2api/utils/tool_parser.py:1230-1246`
- `llm-proxies/glm2api/src/glm2api/services/glm_client.py:159-176`
- `llm-proxies/glm2api/src/glm2api/services/translator.py:309-513,935-1031`

`allowed_tool_names=None` bedeutet im Parser „alles erlauben“. Gleichzeitig erkennt `_find_bare_tool_call_array()` normale JSON-Objekte mit einem `name`-Feld und Objekte mit `filePath`/`command` als mögliche Tool-Calls. Ein Aufruf ohne deklarierte Tools kann daher als synthetischer `write`-, `edit`-, `bash`-, `read`- oder beliebiger Function-Call enden.

Auch die native Mapping-Logik interpretiert `None` als Wildcard: Ein natives `open` oder Sandbox-Tool kann ohne deklarierte Client-Tools auf `read`, `webfetch` oder `bash` abgebildet werden. Die harte Blockliste wird überwiegend case-sensitiv geprüft; Varianten wie eine andere Schreibweise können die Semantik der gesperrten Namen umgehen.

**Auswirkung:** Normale JSON-Antworten können Datenverlust erleiden oder unbeabsichtigt Tool-Ausführung beim nachgelagerten Client auslösen.

**Empfehlung:** Ohne deklarierte Tools niemals aus Quelltext einen Tool-Call erzeugen. Native Calls nur mappen, wenn das exakt erlaubte Zieltool deklariert wurde. Namen vor Vergleich normalisieren und/oder eine kanonische Tool-Registry verwenden. Calls strikt gegen JSON-Schema validieren.

### I-010 — Hoch: Bildakkumulator verliert den Finish-Status und kann fertige Bilder verwerfen

**Orte:**

- `llm-proxies/glm2api/src/glm2api/services/translator.py:38-93`
- `llm-proxies/glm2api/src/glm2api/services/translator.py:897-916`
- `llm-proxies/glm2api/src/glm2api/services/glm_client.py:985-1041`

`_merge_part_texts()` kopiert bei einem Update nur `content`; `status` und andere Part-Metadaten bleiben vom ersten Part erhalten. `_build_images_response()` akzeptiert Bilder nur aus Parts mit `part["status"] == "finish"`. Bei der üblichen Sequenz Init-Fragment → Finish-Part bleibt der Init-Status stehen, sodass fertige Bilder verworfen und anschließend `502` ausgelöst werden können.

**Empfehlung:** Das gesamte Part-Objekt per Merge aktualisieren, Status/Meta kontrolliert übernehmen, Bildinhalte gegen die im Event beobachtete Reihenfolge statt gegen eine unvollständige Statuskopie zu prüfen.

### I-011 — Hoch: Anthropic-Streaming mischt Argumentdeltas mehrerer Tool-Calls

**Ort:** `llm-proxies/glm2api/src/glm2api/services/anthropic_adapter.py:383-416`

Der Adapter schließt beim ersten Auftreten einer neuen Tool-Call-Index den vorherigen Block. Spätere Deltas für eine ältere Tool-Call-Index werden trotzdem mit dem aktuellen globalen `content_index` gesendet. Bei parallelen oder interleavten OpenAI-Tool-Call-Chunks landen Argumentfragmente dadurch im falschen Anthropic-`input_json_delta`-Block. Gespeicherte Call-Objekte enthalten außerdem bereits assemblierte Argumente, während nur der zuletzt geöffnete Block eine Indexzuordnung hat.

**Empfehlung:** Pro Tool-Call-Index dauerhaft einen offenen/geschlossenen Anthropic-Block und dessen Argumentpuffer führen; Streaming-Content-Blöcke sind sequenziell, weshalb interleavte Indices entweder korrekt sequenziert oder als vollständige Calls am Final chunk emittiert werden müssen.

### I-012 — Hoch: Standardmäßig ist die lokale API ohne Authentifizierung und mit Wildcard-CORS exponiert

**Orte:**

- `llm-proxies/glm2api/src/glm2api/config.py:319-320`
- `llm-proxies/glm2api/src/glm2api/server.py:62-65`
- `llm-proxies/glm2api/src/glm2api/server.py:113-116,402-414`
- `llm-proxies/glm2api/src/glm2api/server.py:428-434`

Leere `SERVER_API_KEYS` deaktivieren die Authentifizierung vollständig; `CORS_ALLOW_ORIGIN` ist standardmäßig `*`, und OPTIONS erlaubt Authorization, `x-api-key` und diverse Content-Typen. Bei Default-Binding auf Loopback kann eine beliebige Website die lokale API per Browser-Preflight aufrufen und Responses lesen. In Kombination mit I-003 erhöht dies die praktische Angriffsfläche.

**Empfehlung:** Für Nicht-Loopback-Bindings Authentifizierung zwingend verlangen; Default-CORS auf lokale explizite Origins begrenzen; Header-Methoden minimieren; Auth auch für Model-Metadaten oder mindestens eine sichere Absicht dokumentieren. Die Token-Prüfung sollte constant-time erfolgen.

### I-013 — Mittel: Upstream-Timeouts werden als Client-Disconnects klassifiziert

**Orte:**

- `llm-proxies/glm2api/src/glm2api/server.py:28`
- `llm-proxies/glm2api/src/glm2api/server.py:214-215,261-263,343-345,385-387`

`socket.timeout` gehört zu `_CLIENT_DISCONNECTED`, obwohl die Client-Verbindung intakt sein kann und der Timeout aus dem urllib-Upstream-Socket stammen kann. Bei Streaming wird der Turn dann ohne Fehler-/SSE-Done-Semantik beendet bzw. mit `[DONE]` abgeschlossen; bei Non-Streaming bleibt die Antwort häufig ohne JSON.

**Empfehlung:** Client- und Upstream-Timeouts in getrennte Exception-Typen überführen; Socket-Timeouts nicht pauschal als Disconnect behandeln.

### I-014 — Hoch: Responses-Streaming nutzt eine unbeschränkte Queue und eine nicht abbrechbare Hintergrund-Thread-Pipeline

**Orte:**

- `llm-proxies/glm2api/src/glm2api/server.py:304-316,318-358`
- `llm-proxies/glm2api/src/glm2api/services/glm_client.py:442-597`

Ein Daemon-Thread liest den Upstream vollständig in eine `queue.Queue()` ohne Maxsize. Der HTTP-Client kann langsam oder disconnecten, während der Reader weiter läuft und Output unkontrolliert puffert. Es gibt kein Cancellation-Event und keinen `close()` des Upstream-Generators im Writer-Fehlerpfad. Der Reader fängt außerdem `BaseException` und leitet sie in die Queue.

**Empfehlung:** Backpressure mit begrenzter Queue oder synchrones Lesen; explizites Cancellation-Event; Upstream-Generator im `finally` schließen; nur `Exception`, nicht `BaseException`, transportieren.

### I-015 — Hoch: API-Parameter werden angenommen, aber nicht an das Modell weitergegeben

**Orte:**

- `llm-proxies/glm2api/src/glm2api/services/anthropic_adapter.py:142-189`
- `llm-proxies/glm2api/src/glm2api/services/responses_adapter.py:142-188`
- `llm-proxies/glm2api/src/glm2api/services/glm_client.py:790-819`

`max_tokens`, `temperature`, `top_p`, Stop-Sequenzen, Sampling und viele weitere API-Felder werden von den Adaptern in den internen Payload kopiert, aber `_open_chat_stream()` baut den eigentlichen Upstream-Body ausschließlich aus Assistant-, Conversation-, Messages- und Meta-Feldern. Das Ausgabelimit wird nicht durchgesetzt; die Responses-Usage behauptet statische Minimalwerte.

**Auswirkung:** Clients erhalten semantisch falsche Antworten und können keine Output-/Kostengrenzen durchsetzen.

**Empfehlung:** Unterstützte Felder explizit validieren und upstream abbilden oder mit dokumentiertem 400 ablehnen. Wenn das Upstream keine Felder unterstützt, darf ein empfangenes `max_tokens` nicht stillschweigend ignoriert werden. Usage entweder ehrlich als unbekannt markieren oder upstream erheben.

### I-016 — Mittel: Interne und Upstream-Fehlerdetails werden an Clients zurückgegeben

**Orte:**

- `llm-proxies/glm2api/src/glm2api/services/glm_auth.py:203-211,250-258`
- `llm-proxies/glm2api/src/glm2api/services/glm_client.py:863-867,954-957,1075-1081`
- `llm-proxies/glm2api/src/glm2api/server.py:201-207,216-221`

Upstream-Payloads und `str(exc)` werden als API-Details weitergereicht. Das kann interne URLs, Upstream-Response-Strukturen, Request-IDs, signierte URLs oder in Fehlertexten enthaltene Upstream-Daten offenlegen. Refresh-Fehler bauen außerdem das komplette Payload in die Exception ein.

**Empfehlung:** Intern correlation-ID-generieren, vollständige Details nur serverintern mit Redaktion loggen und eine stabile öffentliche Fehlermeldung senden. Upstream-Payload niemals ungefiltert als `details` zurückgeben.

### I-017 — Mittel: Kryptografisch schwache, fest eincodierte Signatur und optionales Klartext-Upstream

**Orte:**

- `llm-proxies/glm2api/src/glm2api/services/glm_auth.py:19-30`
- `llm-proxies/glm2api/src/glm2api/config.py:287-288,331-332`

`build_sign()` verwendet einen fest im Quelltext hinterlegten Signaturwert und MD5. Er wird nicht als Secret behandelt und ist damit kein schützenswerter kryptografischer Schlüssel. Zugleich akzeptiert die Konfiguration `http://`-Upstreams, über die Access-/Refresh-Tokens und Attachments im Klartext übertragen werden können.

**Empfehlung:** Klarstellen, ob die Signatur nur ein Upstream-Protokoll-/Anti-Bot-Wert ist. Falls sicherheitsrelevant: Secret extern konfigurieren, rotierbar halten und einen authentifizierten, replay-resistenten Mechanismus verwenden. Upstream-HTTPS erzwingen, sofern das Protokoll es erlaubt.

### I-018 — Mittel: Eingabevalidierung ist ad hoc und inkonsistent

**Orte:**

- `llm-proxies/glm2api/src/glm2api/server.py:118-186`
- `llm-proxies/glm2api/src/glm2api/services/translator.py:96-117`
- `llm-proxies/glm2api/src/glm2api/services/translator.py:640-752`

Nur der klassische Chat-Endpoint prüft `messages`/`model`; Messages und Responses akzeptieren strukturell unvollständige Payloads. Es gibt keine Limits für Arraylängen, Stringlängen, Verschachtelung oder Tool-Anzahl. Python-`json.loads()` akzeptiert außerdem Nichtstandard-Zahlen wie `NaN`/`Infinity`. Mehrere Translator-Helfer erwarten verschachtelte Dicts und lösen bei falschen Client-Typen `AttributeError` statt eines kontrollierten 400 aus.

**Empfehlung:** Da kein FastAPI/Pydantic vorhanden ist, eine explizite Schema- und Größenvalidierungsschicht vor allen Adaptern einführen; unbekannte Felder kontrolliert behandeln; standardkonformes JSON erzwingen.

### I-019 — Mittel: Konfigurationsnebenwirkungen und Dateirechte sind nicht abgesichert

**Orte:**

- `llm-proxies/glm2api/src/glm2api/config.py:52-73,106-121,187-204`
- `llm-proxies/glm2api/src/glm2api/config.py:207-224`
- `llm-proxies/glm2api/src/glm2api/logging_utils.py:168-200`

Beim Start kann eine `.env` automatisch kopiert werden; es gibt keine restriktive Dateirechteprüfung. Token-Dateien werden als Klartext gelesen/geschrieben. Der relative Debug-Logpfad wird im aktuellen Arbeitsverzeichnis angelegt. Außerdem konfiguriert `load_config()` früh einen Logger-Handler, den `setup_logging()` nicht am Logger `glm2api` entfernt, sondern nur die Root-Handler leert; doppelte Protokolle sind möglich.

**Empfehlung:** Existenz, Eigentümer und Modus von Secret-Dateien prüfen, Dateien mit restriktiven Rechten atomar anlegen, Secret-Verzeichnisse nicht aus dem Arbeitsverzeichnis ableiten und Logger-Hierarchie einmalig vollständig neu aufbauen.

### I-020 — Niedrig: Bare-Tool-Parser entfernt einen nachfolgenden Fence nicht

**Ort:** `llm-proxies/glm2api/src/glm2api/utils/tool_parser.py:841-850`

Nach dem erfolgreichen Parsen eines Bare-Call-Arrays soll ein nachfolgender Fence konsumiert werden. Die Zeile `consumed += len(rest) - len(rest)` addiert jedoch immer null. Der Fence kann dadurch als sichtbarer Antworttext leaken.

**Empfehlung:** Die beabsichtigte Offset-Berechnung korrigieren und mit abschließendem Fence, Newline und Textrest testen.

## 4. Detailaudit nach Themen

### 4.1 API- und FastAPI-/HTTP-Lifecycle

- Der Lifecycle ist bewusst ein `main()`-/`serve_forever()`-Modell, kein FastAPI-Lifespan: `__main__.py:10-34`, `app.py:17-97`, `server.py:32-51`.
- `Application.stop()` ist idempotent, schließt aber keine globalen Upstream-Sessions oder Dateien, weil der Client nur In-Memory-HTTP-Responses hält.
- Der Signal-Handler wirft `KeyboardInterrupt`; das ist für den Main-Thread brauchbar, aber nicht für beliebige Einbettung oder Threads.
- `ThreadingHTTPServer` plus HTTP/1.1 erlaubt persistente Verbindungen, ohne Request-/Idle-Timeout und ohne Body-Limit.
- JSON-Antworten setzen `Content-Length`; Streaming-Antworten schließen die Verbindung, was korrekt ist, aber keine Proxy-Buffering-Header enthält.
- Der Server bietet `/health` und `/v1/models` ohne Authentifizierung. Das kann beabsichtigt sein, sollte bei nicht-loopback Deployment explizit entschieden werden.
- Adapter- und Queue-Arbeit teilen keinen Request-Correlation-Identifikator; Logs sind bei parallelen Requests schwer zu korrelieren.

### 4.2 Authentifizierung und Token-Pool

- Die Downstream-Auth prüft Bearer und `x-api-key`, verwendet aber direkte Set-/Listenmitgliedschaft und ist daher weder constant-time noch gegen Varianten der Schreibweise robust (`server.py:402-414`).
- Guest-Marker werden auf `GLM_MAX_CONCURRENCY` Slots aufgefüllt (`config.py:231-243`), was Poolgröße und Queue-Kapazität koppelt. Ein sehr großer, nicht begrenzter Wert erzeugt viele Account-State-Einträge.
- Registrierte Tokens werden bevorzugt ticket-deterministisch verteilt; ein einzelner Account kann dabei mehrere gleichzeitige Requests tragen.
- Access-Token-Cache hat eine 60-Sekunden-Sicherheitsmarge, verwendet aber eine feste nominale Lebensdauer statt der Upstream-Ablaufzeit (`glm_auth.py:20,225,264`).
- `read_json_response()` und Fehler-Body-Decoding haben keine Größenbegrenzung; `gzip.decompress()` ist unbeschränkt (`glm_auth.py:105-123`, `glm_client.py:1254-1271`).
- Jeder `UpstreamAPIError` gilt als Accountwechselkriterium; 400/404/429 und echte Tokenfehler werden nicht sauber getrennt.
- Der Fortschritt des globalen Current-Index ist bei bevorzugten Ticket-Indizes nur begrenzt wirksam; die eigentliche Auswahl läuft über `_get_preferred_account_index()`.

### 4.3 Upstream-Retries und Fehlertaxonomie

- Drei Schichten existieren: Busy-HTTP-Retry (`glm_client.py:822-869`), Token-/Account-Failover (`glm_client.py:1304-1346`) und transiente Event-/Empty-Round-Retries (`glm_client.py:178-342,442-582`).
- Busy-Retry ist fest intervallbasiert, ohne `Retry-After`, exponentielles Backoff oder Jitter; parallele Clients können synchron retryen.
- Transiente Event-Retries zählen die maximale Anzahl korrekt als Erstversuch plus N Retries.
- „Fresh conversation“ ist nur bei nicht-persistentem, clientfreiem State wahr. Bei `conversation_id`, Persistenz oder Reset-bezogenen Zuständen kann derselbe Conversation-Kontext erneut verwendet werden.
- Wenn nur Reasoning gestreamt wurde, zählt `served_content` weiterhin `false`; ein späterer transienter Fehler kann bereits gesendetes Reasoning duplizieren (`glm_client.py:466-482,557-582`).
- Nach bereits sichtbarem Content findet kein Retry statt, um Doppeltext zu vermeiden; korrekt, aber ohne Resume-/Continuation-Strategie.
- Upstream-Timeouts haben keine gesamte, requestbezogene Deadline. Mehrere Accounts und Busy-Retries multiplizieren Wartezeit.
- Die Löschung der Conversation läuft im Client-`finally` und kann die Latenz der antwortenden HTTP-Request verlängern. Fehler werden bewusst verschluckt, was Cleanup-Fehler unsichtbar macht.

### 4.4 Streaming

- OpenAI Chat-Completions-Streaming wird nahezu direkt als SSE weitergereicht; das hält die Kompatibilität, übernimmt aber Token-/Usage-Semantik und Upstream-Formatfehler ungeprüft.
- Anthropic und Responses bauen eigene SSE-Akkumulatoren auf. Beide parsen SSE-Framing rudimentär über `split("\n\n")` und ignorieren ungültige UTF-8-/JSON-Blöcke.
- Anthropic/Responses beginnen HTTP-Headings vor dem ersten Upstream-Chunk. Bei einem leeren Stream kann dadurch eine leere, scheinbar erfolgreiche 200-Antwort entstehen.
- Responses verwendet den einzigen Heartbeat-Pfad und dadurch einen zusätzlichen Thread plus unbeschränkte Queue.
- Alle drei Streaming-Antworten senden üblicherweise `[DONE]`; die Adapter finishen über private `_finish()`-Methoden, wodurch Server und Akkumulator eng gekoppelt sind.
- Usage ist fest `1/1/2`; Adapter übernehmen diese Werte, sodass die APIs keine belastbaren Tokenzahlen liefern (`translator.py:1320-1333,1395-1408`).

### 4.5 Tool-Parser und Tool-Protokoll

- Gute Basis: Es gibt mehrere Parserpfade für JSON, DSML/XML und Bare JSON, ein explizites Allow-Set für Client-Tools, Echo-/Duplikaterkennung und negative Follow-up-Runden für blockierte Versuche.
- `xml.etree.ElementTree` parst Modelltext ohne direkten Codeausführungspfad; die Hauptbedrohung ist nicht XML-Codeausführung, sondern die semantische Übergabe manipulierter Calls an den nachgelagerten Client.
- Code-Fences werden über einen reinen Backtick-Regex maskiert; Tilde-Fences, andere Markdown-Fence-Formen und teilweise unterbrochene Formate sind nicht abgedeckt.
- Viele Reparaturpfade sind absichtlich tolerant, vergrößern aber den Parserzustand: unbekannte Eingabe kann als Tool-Call umgedeutet, Text kann verworfen oder Spaces/Neue-Zeilen beim Flush verändert werden.
- `detect_tool_call_names()` ist ungefiltert gedacht und wird ausschließlich zur Diagnose blockierter Versuche verwendet; das ist grundsätzlich sauber getrennt.
- Tool-Namen werden nicht gegen JSON-Schemas validiert; zusätzliche Properties, falsche Typen und unklare Pflichtfelder werden weitergereicht.
- Native Sandbox-zu-`bash`-Mapping verwendet ein Here-Document. Der Befehl wird nur erzeugt, wenn `bash` erlaubt ist, aber ein eingebettetes `EOF` kann die Here-Document-Grenze vorzeitig beenden.
- `build_tool_call_instructions()` und Schema-Prompts sind sehr lang und stark wiederholt; bei langen Tool-Listen kann der sichtbare Kontext das Budget dominieren.
- `blocked_examples` in `tool_protocol.py:88` wird berechnet, aber nicht verwendet.

### 4.6 Kontext- und Session-Isolation

- Der Standardpfad ist stateless und übergibt die gesamte Request-Historie; das ist grundsätzlich isolationfreundlich.
- `convert_messages()` flacht jedoch alle Rollen zu einer einzigen User-Nachricht mit textuellen `System:`, `User:` und `Assistant:`-Markern ab. Nutzerinhalt kann dadurch Rollenmarker imitieren; System/User/Assistant-Grenzen sind keine vertrauenswürdigen Structs mehr.
- Tool-Result-IDs werden validiert, aber unbekannte Results können durch, wenn noch keine gültige Call-ID-Menge existiert; sie werden anschließend meist mangels Tool-Name verworfen.
- Persistente und clientgelieferte Conversation-IDs umgehen die sichere stateless Isolation, wie in I-004 beschrieben.
- Kompression kann System- und User-Turns in einen User-Summary-Eintrag umwandeln und Tool-Paare beschädigen.
- Der Responses-Adapter ignoriert `previous_response_id`; Responses-Clients erhalten keine serverseitige Conversation-Kette, während die Antwort `previous_response_id: None` meldet (`responses_adapter.py:265-284`).

### 4.7 Ressourcen

- Queue-Leases sind im Normalpfad idempotent und werden in Client-Finallys freigegeben.
- Beim bloßen Erzeugen eines Streaming-Generators wird bereits ein Lease und eine Upstream-Verbindung erzeugt (`glm_client.py:394-399,584-597`). Wird der Generator nie gestartet oder nicht geschlossen, hängt der Lease bis zum nicht-deterministischen GC.
- Anthropic-/Chat-Streaming schreibt synchron und erzeugt Backpressure; Responses puffert stattdessen unbeschränkt.
- Remote Attachments haben 100 MB pro Datei, aber weder Gesamtlimit noch Maximalanzahl; Data-URLs haben nicht einmal das Einzellimit.
- Base64-Bilddownloads sind unbeschränkt.
- Upstream-JSON- und Fehler-Bodies sind unbeschränkt; gzip ist unbeschränkt.
- SSE- und Tool-Parser-Puffer wachsen ohne Längenlimit.
- Der Server startet unbegrenzt Daemon-Threads und besitzt keine globale Verbindungs- oder Request-Rate-Limitierung.

### 4.8 Fehlerbehandlung

- Breite Exception-Catches verhindern meist Prozessabstürze, geben aber oft `str(exc)` an Clients weiter.
- Queue- und Upstream-Timeouts werden getrennt benannt, aber Upstream-Socket-Timeouts falsch als Client-Disconnects behandelt.
- SSE-Parsing verwirft still Fehler und EOF-Semantik.
- Anthropic/Responses-Fehlerpfade signalisieren Erfolg statt Fehler.
- Bild-, Tool- und Adapter-Adapterfehler können als 502 erscheinen, obwohl Client-Eingaben die Ursache sind.
- Kein Request-Correlation-Id, keine strukturierten Fehlerobjekte und keine Metrik für Retries, Truncated Streams, Queue-Timeouts oder Account-Failover.

### 4.9 Konfiguration

Positiv:

- Umgebung überschreibt Dateiwerte; Port, Request-Timeout, Queue-Wait und Busy-Interval werden teilweise validiert (`config.py:323-332`).
- Gastmodus und Single-/Multi-Token-Modus sind explizit modelliert.
- Modellvarianten werden zentral erzeugt und Upstream-Mapping ist nachvollziehbar.

Probleme:

- `DEBUG_DUMP_ALL` koppelt Payload-Secrets an persistentes DEBUG-Logging.
- `glm_busy_max_retries` wird nicht auf mindestens null begrenzt; ein negativer Wert erzeugt einen leeren Retry-Loop und Endfehler 429.
- `glm_max_concurrency` hat keine Obergrenze und beeinflusst Pool, Queue und potenziell viele gleichzeitige Upstreams.
- Es gibt keine Request-Body-, SSE-, Prompt-, Tool-, Output- oder Attachment-Gesamtlimits in der Konfiguration.
- `GLM_BASE_URL` prüft nur das Schema und schützt damit auch nicht vor HTTP, Credentials in URL, Loopback oder Header-/Pfad-Injection.
- Modellalias-/Exposed-Model-Konfiguration ist im `AppConfig` vorhanden, im `load_config()` aber nicht konfigurierbar; die Variablen sind derzeit statisch.

## 5. Vollständiger Datei-Audit

### `llm-proxies/glm2api/main.py:1-4`

- Reiner Root-Einstieg; importiert `main` und beendet mit dessen Returncode.
- Kein eigener Lifecycle- oder Fehlerpfad.
- Keine Änderungsempfehlung.

### `llm-proxies/glm2api/src/glm2api/__init__.py:1-5`

- Nur Docstring, Exportliste und statische Version.
- Versionswert ist hart codiert und muss bei Package-Version pflegerisch synchron bleiben.
- Keine Laufzeitlogik.

### `llm-proxies/glm2api/src/glm2api/__main__.py:1-34`

- Vollständig geprüft: Early-Config-Fehler, KeyboardInterrupt, Application-Erzeugung, `run()` und Returncodes.
- Frühfehler werden per `print` ausgegeben; unerwartete Exceptions enthalten einen Traceback.
- Das Secret-Risiko überwiegend nachgelagert: Fehlertexte aus Config/Auth können intern sensible Daten enthalten.
- Keine Ressourcenlücke im Erfolgspfad, weil `Application.run()` selbst finalisiert.

### `llm-proxies/glm2api/src/glm2api/app.py:1-107`

- Vollständig geprüft: Logging-Initialisierung, Client-/Serveraufbau, Bindfehler, `serve_forever`, Signalhandler und idempotentes Stop.
- Korrekt: Bindfehler werden auf klare StartupError-Arten abgebildet; `finally: self.stop()`.
- Risiken: keine explizite Client-Cleanup-Struktur, keine Readiness-/Liveness-Übergabe an einen Supervisor, Signalhandler nicht thread-/embedding-sicher.
- Der Hauptkontrollfluss ist einfach und nachvollziehbar.

### `llm-proxies/glm2api/src/glm2api/config.py:1-351`

- Vollständig geprüft: Defaults, Dotenv-Parser, Bool/Int/Float/List, Tokenfile, Guestmarker, Dataclass, Env-Dateierzeugung, Pfadnormalisierung, Gesamt-Konfigurationsaufbau und Validierung.
- Stärken: klare ConfigError-Klasse; Umgebung hat Vorrang; sensible Werte werden nicht geloggt.
- Schwächen: naive Dotenv-Semantik, Auto-Dateikopie ohne Rechteprüfung, keine Scope-/Payloadlimits, nicht begrenzte Busy-Retry-/Concurrency-Werte, wildcard CORS, optionale Auth, freies HTTP-Upstream.
- Der Logger wird vor dem eigentlichen Setup vor konfiguriert; nach `setup_logging()` bleibt der Child-Handler potenziell doppelt.

### `llm-proxies/glm2api/src/glm2api/logging_utils.py:1-226`

- Vollständig geprüft: Formatter, Farbheuristik, Root-/Console-/RotatingFile-Handler, Debugserialisierung.
- Stärken: Rotation ist begrenzt, Console/Dateiformat getrennt, Windows-Umlaute werden abgesichert.
- Kritische Schwäche: keine Redaktion; DEBUG persistiert potenziell Secrets und Rohdaten.
- `root.handlers.clear()` entfernt den zuvor am Child `glm2api` gesetzten Handler nicht.
- `_name_width` wird bei parallelen Logs dynamisch verändert; funktional harmlos, aber nicht deterministisch.
- `serialize_for_debug()` kann bei nicht serialisierbaren Werten über `repr()` mehr preisgeben.

### `llm-proxies/glm2api/src/glm2api/model_variants.py:1-46`

- Vollständig geprüft: Feature-Suffix-Erkennung, Variantenexpandierung, Exclude-Set, Think-/Search-Prädikate.
- Logik ist lokal und deterministisch.
- Nur bekannte Suffixe werden erkannt; unbekannte Feature-Namen bleiben Teil des Basisnamens.
- AusAlias-Listen werden Features vor dem Upstream-Mapping entfernt; das ist beabsichtigt und konsistent.
- Keine eigenständigen Sicherheitsrisiken.

### `llm-proxies/glm2api/src/glm2api/server.py:1-483`

- Vollständig geprüft: Handlerbau, GET/POST/OPTIONS, Auth, Content-Length/JSON, vier API-Pfade, JSON/SSE-Responses, Anthropic-/Responses-Streaming, Header, Fehler, CORS und Logging.
- Stärken: Auth vor POST-Payloadverarbeitung; JSON-Encoding und Content-Length; SSE-Verbindungsclose; `finally` sendet Chat `[DONE]`; `BaseHTTPRequestHandler` kapselt grundlegende HTTP-Parsingfehler.
- Kritische Risiken: I-001 Queue-Blockade, I-002 Ingress-Ressourcen, I-003 SSRF plus CORS, I-005 Logs, I-007 Fehlermaskierung, I-012 Authdefault, I-013 Timeoutklassifikation, I-014 Readerthread.
- Es gibt keine FastAPI-Middleware für Validation, Request-ID, Exception-Handler, Body-Limit oder Security-Header.
- `/models` und `/health` sind ungeschützt; für lokale Betriebsdiagnose vertretbar, remote zu entscheiden.
- Fehlerantworten enthalten häufig interne `str(exc)`-Details.
- SSE-Adapter schreiben Headings vor Upstream-Erfolg und maskieren mid-stream Fehler als Abschluss.
- Threading-Server ist funktional, aber für adversariale lokale/remote Clients nicht begrenzt.

### `llm-proxies/glm2api/src/glm2api/services/__init__.py:1-1`

- Nur Service-Layer-Docstring.
- Keine Laufzeitlogik.

### `llm-proxies/glm2api/src/glm2api/services/anthropic_adapter.py:1-468`

- Vollständig geprüft: System/Messages/Tools/Tool-Choice/Thinking-Requestkonvertierung, Non-Stream-Response und Streaming-Accumulator.
- Stärken: Text/Thinking/Tool-Use werden grundsätzlich getrennt; Usage wird strukturiert; idempotentes `_finish()`.
- Probleme: gemischte Tool-Result-/Tool-Use-Blöcke verlieren Inhalte; fehlende Requestvalidierung; Non-Stream-Annahmen über `fn`; falscher Multi-Tool-Streamindex (I-011).
- Thinking wird beim Request als normaler Text in die History geschrieben.
- `max_tokens`/Sampling werden weitergereicht, aber später ignoriert.
- Adapter maskiert Upstream-Fehler als `message_stop`.

### `llm-proxies/glm2api/src/glm2api/services/glm_auth.py:1-325`

- Vollständig geprüft: Signatur-/Headeraufbau, AccessToken/AccountState, Accountauswahl, Caching, Refresh, Guestfetch, Persistenz und Failoverklassifikation.
- Stärken: Kontenobjekte werden gelockt; Cache-Hit mit Sicherheitsmarge; bestehende Refresh-Tokens werden persistiert; URLopen bekommt Timeouts.
- Probleme: Refresh-Race/Lost Update; starre Lebensdauer; unbeschränkte Bodies/Gzip; Upstream-Payload in Exceptions; statusbasierte zu breite Failoverregel.
- Plaintext-Persistenz ist beabsichtigt, aber Rechteprüfung/atomisches Replace fehlen.
- Der Signaturwert ist fest eincodiert; MD5 ist für einen echten kryptografischen Schlüssel ungeeignet.
- `should_switch_account()` prüft RuntimeError nur per Substring „token“, was fragil und fehleranfällig ist.

### `llm-proxies/glm2api/src/glm2api/services/glm_client.py:1-1346`

- Vollständig geprüft: Queue, Tokenclient, Chat/Image High-Level APIs, Streaming-Generator, SSE-Terminierung, Eventfehler, Conversation-Lifecycle, Upstreamrequest, Accountfailover, Bildresponse, Dateiupload/-download, Parser und Hilfen.
- Kritisch: Queue-Ghost-Ticket (I-001).
- Hoch: SSRF/Dateileser, globale Session, Tokenrennen, Truncated-Stream-Erfolg, unbounded Attachments/Downloads, Parameterignorierung.
- Weitere konkrete Defekte: doppelter Aufruf `extract_history_tool_call_signatures()` in `chat_completion()` (`186-191`); Bildstatusverlust; leere Bilder; wiederholte Attachment-Uploads bei Retries.
- Ressourcencleanup ist im normalen Generatorpfad gut, aber nicht bei nie konsumiertem Generator oder disconnectetem Responses-Reader.
- Upstream-Verbindungen werden in `finally` geschlossen; das ist positiv.
- `delete_conversation()` verschluckt Fehler absichtlich, verlängert aber Request-Latenz.
- HTTP-Runtime- und Transzientklassifikation ist inkonsistent: Upstream-Socket-Timeout wird im Server als Disconnect fehlklassifiziert.
- Es gibt keine Schema-Validierung für Messages, Tools oder File-Strukturen.
- Accountverteilung ist ticketbasiert und nicht conversation-gebunden.

### `llm-proxies/glm2api/src/glm2api/services/responses_adapter.py:1-627`

- Vollständig geprüft: Inputkonvertierung, Function Calls/Outputs, Toolkonvertierung, Reasoning, Non-Stream-Response und Streaming-Eventzustand.
- Stärken: unterstützt Function-Call-Outputs, mehrere Calls und strukturierte Responses-Events.
- Probleme: `previous_response_id` wird nicht umgesetzt; Outputs ohne passenden vorherigen Call werden still verworfen; max/sampling werden ignoriert; Reasoning wird bewusst verworfen.
- Streaming-Indexierung ist robuster als Anthropic, aber `_finish()` kann nach Error dennoch Completed liefern.
- Heartbeat/Backgroundthread liegen im Server, nicht im Adapter; Queue-/Cancellationrisiken bleiben bestehen.
- Keine Request-Schema- oder Content-Size-Validierung.

### `llm-proxies/glm2api/src/glm2api/services/translator.py:1-1524`

Der Dateiaudit umfasst alle folgenden Blöcke vollständig:

- Part-Merge und Content-Extraktion: `38-135`
- Command-/Toolargument-Reparatur und Sanitizing: `138-306`
- Native Open-/Sandbox-Mapping: `309-452`
- Tool-Call-Sanitizing und Tool-Choice: `455-543`
- History-Kompression: `546-637`
- Messagekonvertierung und Promptbau: `640-763`
- Modell-/Chatmode-/Networking-Auflösung und History-Signaturen: `766-848`
- `GLMEventAccumulator` inklusive Eventaufnahme, Deltas, Native Tools, Parserintegration, Finalisierung und Responsebau: `851-1524`

**Wesentliche Befunde:**

- I-008 History-Paare werden beschädigt.
- I-009 Native Mapping/Wildcard kann Calls ohne Tool-Deklaration erzeugen.
- I-010 Partstatus wird nicht zusammengeführt.
- Rollen werden unstrukturiert in eine User-Prompt flachgedrückt.
- Der Parser kann gewöhnliche JSON-Daten als Calls interpretieren.
- Calls mit Präambletext verlieren den Text, sobald Tool-Calls vorhanden sind (`1339-1418`).
- Serverseitige Calls werden nicht in allen Pfaden abschließend nochmals bereinigt.
- History-Echo-Signaturen unterdrücken auch echte, spätere identische Calls; ID wird bei Signaturvergleich nicht berücksichtigt.
- Logik-IDs werden lexikografisch sortiert, nicht zwingend in Upstream-Reihenfolge.
- Usage ist Dummy; maximale Outputlänge wird nicht durchgesetzt.
- Wiederholte identische serverseitige Calls mit verschiedenen IDs werden per Signatur kollabiert.
- Ungenutzte Helper und Variablen existieren, darunter `_conversation_has_tool_round`, das importierte `CANONICAL_TOOL_CALL_EXAMPLE`, `has_tools` und `blocked_examples` im Protokollmodul.

### `llm-proxies/glm2api/src/glm2api/utils/__init__.py:1-1`

- Nur Utility-Docstring.
- Keine Laufzeitlogik.

### `llm-proxies/glm2api/src/glm2api/utils/tool_parser.py:1-1400`

- Vollständig geprüft: JSON/DSML/Bare-Formate, Maskierung, XMLreparieren/-parsing, Argumentkonvertierung, Streaming-Holdback, Fehlerdiagnose, `StreamingToolParser.consume()` und `flush()`.
- Stärken: mehrere Schichten zur Überwindung real beobachteter Upstream-Drift; String-aware Brace-Scans; Allow-Set; getrennte Diagnose blockierter Namen; keine direkte Shell-/Codeausführung im Parser.
- Hochrisiken: permissive Bare-JSON-/Native-Mapping-Heuristik, Wildcard-Semantik, case-sensitive Blockliste, Fence-Begrenzung, mögliche Textverluste.
- Der Bare-Fence-Konsum ist ein klarer algebraischer Fehler (I-020).
- Holdback-Logik ist komplex; bei partiellen Strings kann arbiträrer Prätext bis zum Finish zurückgehalten werden.
- `_recover_call_elements()` berechnet eine ungenutzte `args_start`-Position.
- Es gibt keine Input-/Verschachtelungslimits; große Modellantworten können Parserarbeit und Speicher erhöhen.
- DSML-Heuristik kann reale Dokumentation in Inline-Code mit Markup als Call interpretieren.

### `llm-proxies/glm2api/src/glm2api/utils/tool_protocol.py:1-194`

- Vollständig geprüft: Blocknamen, JSON-Serialisierung, Toolfilter, Toolblock-/Resultserialisierung, Call-Instruktionen, Erinnerung und Schema-Prompt.
- Stärken: Tools werden vor Prompt-/Clientpfaden gefiltert; erlaubte XML-/Server-Tools werden getrennt; Resultate werden als kompakte JSON-Nachrichten serialisiert.
- Probleme: `filter_tools()` validiert keine Tool-/Function-Struktur; unbekannte `tool_choice`-Werte werden still auf auto gesetzt; Instruktions- und Beschreibungsinhalte gehen ohne Grenzen in den Prompt.
- Tool-Namen werden nicht kanonisiert; Groß-/Kleinschreibung und Duplikate bleiben inkonsistent zum Parser.
- Server-Side-Tools sind statisch leer.
- `blocked_examples` wird berechnet, aber nicht im Prompt verwendet.
- Keine Schema-Validierung der erzeugten Calls; nur Format-/Namefilterung.

## 6. Priorisierte Revisionsreihenfolge

1. Queue-Ghost-Ticket beseitigen und Ingress-Ressourcen begrenzen.
2. Request-Body-/Connection-Limits, Schema-Validation und standardkonformes JSON einführen.
3. Attachment-URLs strikt sandboxen; Datei-/Redirect-/Private-IP-Zugriff blockieren und Größen kumulativ begrenzen.
4. Default Auth/CORS härten und Debug-Redaktion implementieren.
5. Session-Isolation mandantenfähig machen oder Persistenz deaktivieren; clientgelieferte Conversation-IDs nicht als Eigentumsnachweis akzeptieren.
6. SSE-Terminierungszustand strikt machen; Anthropic/Responses nie bei Upstream-Fehlern als Completed abschließen.
7. Token-Refresh pro Account single-flight und Persistenz atomar machen; Failoverstatus klassifizieren.
8. History-Kompression und Tool-Interaktionsparser mit Invarianten testen; Wildcard-Mapping entfernen.
9. Parameterabbildung, Usage und Adapterprotokolle korrigieren.
10. Konfigurierbare, konsistente Resource-Limits und strukturierte Fehler/Correlation-IDs ergänzen.

## 7. Gesamturteil

Der Kern ist als lokaler, spezialisierter Proxy nachvollziehbar und enthält sinnvolle Schutzmechanismen: Downstream-Auth vor Payloadverarbeitung, Queue-Lease, Upstream-Close in `finally`, Allow-/Blocklisten, SSE-Terminatoren sowie Retry-/Failover-Grundlogik. Für den beschriebenen lokalen Einzelbenutzerbetrieb ist die bestehende Happy-Path-orientierte Auslegung erkennbar.

Für adversariale Clients, Remote-/Multi-Mandanten-Betrieb und lange Agent-Loops ist der aktuelle Stand jedoch nicht robust genug. Die kritische Queue-Blockade, unbegrenzten Ingress-Ressourcen, SSRF/Dateileser, optionale Authentifizierung mit Wildcard-CORS, globale Persistenz sowie als Erfolg maskierte Streamabbrüche sind vor einer Exponierung oder Mehrbenutzerverwendung zu beheben. Tool-Parser und Adapter sollten dabei nicht nur Happy Paths, sondern explizit fehlende Tools, blockierte Tools, Groß-/Kleinschreibungsvarianten, parallele Tool-Calls, leere oder abgeschnittene Streams, gemischte Inhalte sowie Resume/Continuation behandeln.
<!-- END PART I -->

## Anhang J — glm2api: Tests und Benchmarks

<!-- BEGIN PART J -->
## Partition J — Datei-Audit `glm2api/tests/` und `glm2api/benchmarks/`

**Snapshot-Grenze:** J ist die historische Test-/Benchmark-Baseline vor den späteren Änderungen an `translator.py` und `benchmark.md`. T ist der spätere Benchmark-Recheck; die fehlende Abdeckung der nach U hinzugekommenen Pfad- und Meta-Chatter-Zweige bleibt eine offene Frage.

## 1. Prüfauftrag, Umfang und Statusdefinition

- **Audit-Scope:** ausschließlich `/workspaces/MAIN/llm-proxies/glm2api/tests/` und `/workspaces/MAIN/llm-proxies/glm2api/benchmarks/`.
- **Vollständigkeit:** 8 Textdateien mit zusammen 3.505 Zeilen wurden zeilenweise vollständig gelesen. Zusätzlich wurden 14 Binärdateien unter `__pycache__/` inventarisiert; sie sind keine Textfixtures und wurden nicht decompiliert.
- **Ausführung:** Es wurden keine Tests, Benchmark-Skripte, Linter, Typechecker oder sonstigen Projektroutinen ausgeführt. Alle Testresultate sind daher **unbestätigt**; der Audit ist rein statisch.
- **Änderungen:** Außer dieser angeforderten Auditledatei wurden keine Dateien geändert. `Revision.md` wurde nicht verändert.
- **Secrets:** Im geprüften Text wurden keine realen Secrets erkannt. Konkrete tokenartige Fixture-Werte werden in diesem Bericht nicht wiederholt.
- **Bewertungsstatus:**
  - **STARK:** Für den beschriebenen engen Fall gibt es konkrete Assertions und Regressionstests.
  - **TEILWEISE:** Der Hauptpfad ist abgedeckt, entscheidende Grenz-, Fehler- oder Sicherheitsfälle fehlen.
  - **LÜCKE:** Die Behauptung wird durch die vorhandenen Dateien nicht automatisch abgesichert.
  - **RISIKO:** Statisch erkennbare Fehlermöglichkeit im Test-, Parser- oder Verifier-Design.

## 2. Kurzurteil

| Prüfbereich | Status | Kurzfassung |
|---|---|---|
| Vollständige Dateiinventur | STARK | Alle 8 Textdateien vollständig gelesen; keine separate Fixture- oder `conftest.py`-Datei vorhanden. |
| Parser-Regressionen | TEILWEISE | 39 hochspezifische Parserfälle, aber keine vollständige Chunk-Grenzen-Matrix, keine Fuzz-/Property-Tests und mehrere Assertions erlauben Duplikate oder zusätzliche Calls. |
| Streaming-Regressionen | TEILWEISE | Tool-Stream, Responses-SSE, Heartbeat und Retry sind teilweise end-to-end getestet; OpenAI-/Anthropic-Hauptstreaming, Cleanup, Truncation und viele Upstream-Fehlerpfade fehlen. |
| Testabdeckung | TEILWEISE | 115 Testfunktionen konzentrieren sich auf bekannte Regressionen; Auth, HTTP-Validierung, Nebenläufigkeit, Ressourcenlimits, Live-Upstream und viele Edge-Cases fehlen. |
| Sicherheit | RISIKO/LÜCKE | Tool-Allowlisting ist punktuell getestet; der Benchmark-Verifier führt erzeugten Code ohne Sicherheitsgrenze und mit vollständiger Umgebung aus. |
| Robustheit | TEILWEISE/RISIKO | Gute Happy-Path-Fixtures, aber keine Cleanup-Assertions, kaum Negativtests, keine Ressourcen-/Prozessgruppenlimits und wenig Verifier-Fehlerbehandlung. |
| Doku-/Behauptungsabsicherung | TEILWEISE | Fixture- und Metrikverträge sind gut codiert; Tool-Disziplin, Session-Kriterien, echte Testqualität, Isolation, exakte Floats und „genau drei Checks“ bleiben unbelegt. |
| Benchmark als reproduzierbarer Gate | TEILWEISE | Baseline und eine Mutation werden sinnvoll geprüft; als unabhängiger, sicherer oder vollständiger Benchmark-Gate ist er nicht ausreichend. |

## 3. Vollständige Dateiinventur

### 3.1 Textdateien

| Datei | Zeilen | Inhalt | Statische Test-/Prüffunktionen | Status |
|---|---:|---|---:|---|
| `tests/test_config.py` | 34 | Config-Tokenfallback und Sessionflags | 2 | Vollständig gelesen / TEILWEISE |
| `tests/test_model_variants.py` | 64 | Variantenauflösung und Modelllisten | 7 | Vollständig gelesen / TEILWEISE |
| `tests/test_protocol_adapters.py` | 256 | Responses-, Anthropic-, Header- und HTTP-Streampfade | 10 | Vollständig gelesen / TEILWEISE |
| `tests/test_stream_retry.py` | 447 | Upstream-Retries, Follow-ups, Leerantworten | 13 | Vollständig gelesen / TEILWEISE |
| `tests/test_tool_parser.py` | 640 | JSON/DSML/ML-Parser und Fragmentstreaming | 39 | Vollständig gelesen / STARK für bekannte Fälle, insgesamt TEILWEISE |
| `tests/test_translator.py` | 1.209 | Promptkonvertierung, Accumulator, Sanitizer, History und Native-Tools | 44 | Vollständig gelesen / breit, aber TEILWEISE |
| `benchmarks/benchmark.md` | 379 | AuditMesh-Auftrag, Fixtures, Sollwerte und Passkriterien | — | Vollständig gelesen / Vertragslücken |
| `benchmarks/verify_auditmesh.py` | 476 | Unabhängig behaupteter Runner/Post-Run-Oracle | — | Vollständig gelesen / TEILWEISE, Sicherheitsrisiko |
| **Summe Text** | **3.505** |  | **115 Testfunktionen** |  |

### 3.2 Binärinventar

Die folgenden Dateien sind kompilierte Python-Caches, keine Testhilfen und keine Quelldokumentation:

- `tests/__pycache__/test_config.cpython-312-pytest-9.1.1.pyc`
- `tests/__pycache__/test_config.cpython-314-pytest-9.1.1.pyc`
- `tests/__pycache__/test_model_variants.cpython-312-pytest-9.1.1.pyc`
- `tests/__pycache__/test_model_variants.cpython-314-pytest-9.1.1.pyc`
- `tests/__pycache__/test_protocol_adapters.cpython-312-pytest-9.1.1.pyc`
- `tests/__pycache__/test_protocol_adapters.cpython-314-pytest-9.1.1.pyc`
- `tests/__pycache__/test_stream_retry.cpython-312-pytest-9.1.1.pyc`
- `tests/__pycache__/test_stream_retry.cpython-314-pytest-9.1.1.pyc`
- `tests/__pycache__/test_stream_retry.cpython-314.pyc`
- `tests/__pycache__/test_tool_parser.cpython-312-pytest-9.1.1.pyc`
- `tests/__pycache__/test_tool_parser.cpython-314-pytest-9.1.1.pyc`
- `tests/__pycache__/test_translator.cpython-312-pytest-9.1.1.pyc`
- `tests/__pycache__/test_translator.cpython-314-pytest-9.1.1.pyc`
- `benchmarks/__pycache__/verify_auditmesh.cpython-312.pyc`

Der gemischte Bestand aus Python-3.12- und Python-3.14-Caches ist kein Testinput. Er zeigt lokale Ausführungs-/Vorbedingungen, darf aber nicht als Beleg für aktuelle Testresultate verwendet werden.

## 4. Testhilfen und Fixtures

### 4.1 Vorhandene Hilfen

- `tests/test_model_variants.py:6` — minimale `_Config`-Klasse für Aliasauflösung.
- `tests/test_protocol_adapters.py:15` — `_DummyConfig` mit User-Agent.
- `tests/test_protocol_adapters.py:177` — lokales `FakeGLM` für den HTTP-Servertest.
- `tests/test_protocol_adapters.py:183` — stummer `FakeLogger`.
- `tests/test_stream_retry.py:7` — `_RetryConfig` mit festen Grenzen, Retries und Queuewerten.
- `tests/test_stream_retry.py:23`, `tests/test_stream_retry.py:31`, `tests/test_stream_retry.py:44`, `tests/test_stream_retry.py:57` — Event-Fixtures für Fehler, Text-Finish, Reasoning-Finish und sichtbaren Prozess-Text.
- `tests/test_stream_retry.py:70` — `_FakeResponse` mit `closed`-Flag.
- `tests/test_stream_retry.py:79` — `_make_client` baut einen Client per `__new__` und ersetzt Upstream-/SSE-Methoden.
- `tests/test_stream_retry.py:195` — `_FollowUpConfig` aktiviert Follow-ups.
- `tests/test_stream_retry.py:199` und `tests/test_stream_retry.py:217` — blockiertes Tool und normale Folgeantwort.
- `tests/test_stream_retry.py:232` — Follow-up-Client mit Payload- und Aufrufzähler.
- Zahlreiche lokale Funktionen und Klassen in `tests/test_translator.py` erzeugen jeweils nur den aktuellen Eventzustand.
- `benchmarks/verify_auditmesh.py:24`, `benchmarks/verify_auditmesh.py:47`, `benchmarks/verify_auditmesh.py:62` — Required-File-, App-Log- und Security-Log-Verträge als Konstanten.

### 4.2 Fixture-Arten

- Es gibt **keine** `conftest.py`, keine parametrisierte Suite, keine goldenen Dateien und keine separat abgelegten Input-Fixtures.
- `tests/test_config.py:5` und `tests/test_config.py:24` erzeugen `.env`-Dateien mit `tmp_path`.
- Alle übrigen Tests nutzen Inline-Dictionaries, Strings und Eventlisten.
- Der AuditMesh-Benchmark hat keine tatsächlichen generierten Projekt-Fixtures im Repository. Die verpflichtenden Inhalte sind vollständig in `benchmarks/benchmark.md:180-260` und nochmals in `benchmarks/verify_auditmesh.py:47-67` eingebettet.
- Die beiden Embedded-Fixture-Definitionen stimmen für Dateinamen, Services, Limits, App-Log und Security-Log überein.

### 4.3 Fixture-Hilfen: Status

- **STARK:** Kleine, lokale Fixtures machen die Tests deterministisch und zeigen konkrete bekannte Live-Regressionen.
- **LÜCKE:** Lifecycle-Hilfen beobachten ihren eigentlichen Zweck nicht. `_FakeResponse.closed` und ein Release-Callback werden erzeugt, aber in keinem Test auf Cleanup geprüft (`tests/test_stream_retry.py:70-76`, `tests/test_stream_retry.py:87-90`).
- **LÜCKE:** Mehrere Clients werden mit `__new__` ohne reguläre Initialisierung gebaut; dadurch werden Konstruktor- und Setup-Invarianten nicht geprüft.
- **LÜCKE:** Testumgebung und `PYTHONPATH` werden nicht global isoliert.

## 5. Datei-Audit `tests/test_config.py`

**Prüfstatus:** Vollständig gelesen; 2 Tests; Abdeckung TEILWEISE.

### Abgedeckt

- Einzelner konfigurierter Refresh-Token plus Guest-Marker und korrektes Fallback-Verhalten (`tests/test_config.py:4-20`).
- Explizite Session-Isolationsflags: persistente Unterhaltung kann aktiviert und Löschen deaktiviert werden (`tests/test_config.py:23-33`).
- Defaults `glm_persistent_conversation=False` und `glm_delete_conversation=True` werden im ersten Test abgesichert (`tests/test_config.py:19-20`).

### Lücken und Robustheitsrisiken

1. Der erste Test entfernt nur zwei relevante Environment-Variablen (`tests/test_config.py:11-12`). Weitere `GLM_*`-Variablen aus der realen Testumgebung können das Ergebnis beeinflussen.
2. Der zweite Test isoliert überhaupt keine Umgebungsvariablen (`tests/test_config.py:23-33`). Das ist für Sessionflags derzeit wahrscheinlich harmlos, macht die Suite aber umgebungsabhängig.
3. Nicht getestet werden: Mehrfach-Tokenlisten, Reihenfolge, Duplikate, Whitespace/Quotes, leere Tokens, Malformed-Dotenv, Kommentare, fehlende Datei sowie Vorrang zwischen Prozessumgebung und Datei.
4. Nicht getestet werden: API-Key-Konfiguration, Modelllisten, Host/Port, CORS, Debug-Dumps, Queue- und History-Grenzen.
5. Das tatsächliche Request-Lifecycle-Verhalten bei frischer Session und anschließendem Löschen wird hier nicht geprüft; der Test belegt nur das Laden von Flags.

**Bewertung:** Für zwei konkrete Config-Regressionen brauchbar, nicht als Config-Gesamtabdeckung geeignet.

## 6. Datei-Audit `tests/test_model_variants.py`

**Prüfstatus:** Vollständig gelesen; 7 Tests; Abdeckung TEILWEISE.

### Abgedeckt

- Erzeugung von Basis-, Think-, Search- und kombinierten Varianten (`tests/test_model_variants.py:11-20`).
- Aufspalten der Suffixe in beiden Reihenfolgen (`tests/test_model_variants.py:23-26`).
- Auflösung von Basis- und Custom-Aliasen (`tests/test_model_variants.py:29-36`).
- Matrix für Chat-Modus und Networking (`tests/test_model_variants.py:39-50`).
- Kompatibilität eines bestehenden Thinking-Namens (`tests/test_model_variants.py:53-54`).
- Exposition und Pass-through von GLM-5.2 und GLM-5.3 (`tests/test_model_variants.py:57-64`).

### Lücken und Robustheitsrisiken

- Keine Tests für doppelte Varianten, Kollisionen zwischen Alias und Suffix, ausgeschlossene Varianten mit selbst kollidierendem Namen oder leere/kleine Namen.
- Keine Case-/Whitespace-Normalisierung und keine unbekannten Suffixe.
- Kein Test des tatsächlichen `/models`- oder Chat-Endpunkts. Die Tests bestätigen interne Konstanten, nicht die von außen beobachtbare Modellauflistung.
- Kein Test, ob Varianten nach Aliasauflösung eindeutig und korrekt geordnet sind.

**Bewertung:** Gute kleine Matrix für Basisvarianten; keine starke Absicherung gegen kombinatorische Auflösungsfehler.

## 7. Datei-Audit `tests/test_protocol_adapters.py`

**Prüfstatus:** Vollständig gelesen; 10 Tests; Abdeckung TEILWEISE.

### Abgedeckt

- Grundform des `X-Forwarded-For`-Headers (`tests/test_protocol_adapters.py:19-32`).
- Responses `tool_choice` sowie SDK-artige Text-/Image-Eingaben (`tests/test_protocol_adapters.py:35-84`).
- OpenAI-zu-Responses-Ausgabe und Usage-Abbildung (`tests/test_protocol_adapters.py:87-105`).
- Responses-SSE-Event-Hülle, geteilter SSE-Block und `[DONE]`-Fallback (`tests/test_protocol_adapters.py:108-171`).
- Echter lokaler HTTP-Stream mit Heartbeat bei langem Upstream-Sleep (`tests/test_protocol_adapters.py:174-217`).
- Anthropic-Mapping für `tool_choice=any` und benutztes Tool (`tests/test_protocol_adapters.py:220-236`).
- Upstream-SSE-Fehlerereignis mit Statuscode/Message (`tests/test_protocol_adapters.py:239-256`).

### Stärken

- Der Split-SSE-Test zerlegt sogar das Sentinel über Chunks (`tests/test_protocol_adapters.py:140-154`).
- Der HTTP-Test prüft nicht nur einen Unit-Aufruf, sondern einen laufenden Stdlib-HTTP-/ThreadingHTTPServer-Pfad (`tests/test_protocol_adapters.py:198-217`).
- Der Sentinel-Pfad ohne explizites `[DONE]` wird abgedeckt (`tests/test_protocol_adapters.py:157-171`).

### Lücken und Robustheitsrisiken

1. **X-Forwarded-For:** Trotz Testnamen „random“ wird keine Zufälligkeit über mehrere Aufrufe geprüft. Die Assertions erkennen nur einige erste Oktettwerte, nicht die vollständige Reserved/Private/Link-Local-/Benchmark-Range-Klassifikation (`tests/test_protocol_adapters.py:19-32`).
2. **Responses-Accumulator:** Kein Test für UTF-8-Byte-Grenzen, CRLF, `event:`/`id:`-Felder, mehrere Choices, Tool-Calls, Refusals, Fehlerobjekte, `[DONE]` ohne Finish, Truncated Stream oder EOF ohne irgendeinen Abschluss.
3. **Inputadapter:** Kein Test für `input_image` mit externer URL, Function-Call-/Function-Output-Blöcke, mehrere Bild-/Textblöcke, leere oder fehlerhafte Payloads.
4. **Anthropic:** Der Dateiname suggeriert Protokollabdeckung, getestet werden aber nur zwei `tool_choice`-Varianten. Systemprompt, Content-Blöcke, Toolresultate, Streaming, Usage und Fehlerpfade fehlen.
5. **HTTP:** Kein Test für API-Key-Authentifizierung, CORS/Host-Validierung, Content-Type, Request-Limits, unbekannte Routen, Upstream-Ausnahmen, Client-Disconnect oder mehrere Heartbeats.
6. Der HTTP-Test beendet den ThreadingHTTPServer über den Wrapper; der konkrete Cleanup-Befund ist hier nicht belegt. Weitere Server-Lifecycle- und Socket-Close-Grenzen bleiben im Test nur unzureichend abgedeckt (`tests/test_protocol_adapters.py:210-214`).
7. Der HTTP-Test liest erst den vollständigen Body; er misst weder Reihenfolge noch Frequenz oder Form der Heartbeats jenseits eines einzelnen Substrings.

**Bewertung:** Sinnvolle Adapter-Smokes und ein guter SSE-Split-Test, aber keine vollständige Protokoll- oder Serverrobustheit.

## 8. Datei-Audit `tests/test_stream_retry.py`

**Prüfstatus:** Vollständig gelesen; 13 Tests; Abdeckung TEILWEISE.

### Abgedeckt

- Retry eines transienten Streamfehlers und Recovery (`tests/test_stream_retry.py:113-123`).
- Initialversuch plus zwei Retries und transientes Endflag (`tests/test_stream_retry.py:126-141`).
- Sofortiges Scheitern bei nichttransientem Fehler (`tests/test_stream_retry.py:144-159`).
- Kein Retry nach bereits sichtbarem Content (`tests/test_stream_retry.py:162-180`).
- Non-Stream-Retry (`tests/test_stream_retry.py:183-192`).
- Blockiertes Tool mit Follow-up im Stream, nach sichtbarem Content und ohne Follow-up (`tests/test_stream_retry.py:270-368`).
- Non-Stream-Follow-up (`tests/test_stream_retry.py:371-387`).
- Transiente Fehlerklassifikation am Exception-Objekt (`tests/test_stream_retry.py:390-394`).
- Leerantwort- und Reasoning-only-Retry sowie Retry-Erschöpfung (`tests/test_stream_retry.py:396-447`).

### Stärken

- Retry-Anzahl, sichtbarer Output und Abbruch nach Content werden konkret geprüft.
- Follow-ups werden für Stream und Non-Stream getrennt getestet.
- Equality-/Retry-Ende wird begrenzt, sodass kein Endlosloop im Testmodell entsteht.

### Lücken und Robustheitsrisiken

1. Nur ein transienter Fehlercode wird als positiver Retry-Fall getestet; weitere Klassenzuordnungen sind innerhalb dieser Datei nicht abgedeckt.
2. Kein Test für HTTP-Timeouts, Verbindungsabbrüche, `OSError`, malformed SSE, fehlende Events, `[DONE]` vor Finish, rekursive Upstream-Fehler oder Abbruch während der Ausgabe eines Chunks.
3. `_FakeResponse.close()` und Request-Queue-Release werden nie überprüft (`tests/test_stream_retry.py:70-76`, `tests/test_stream_retry.py:87-90`). Conversation-/Response-/Lease-Cleanup ist damit nicht abgesichert.
4. Keine Assertion, welche konkrete `UpstreamAPIError`-Instanz nach sichtbarem Content propagiert wird; `test_error_after_visible_content_raises` schluckt jeden gleichnamigen Fehler (`tests/test_stream_retry.py:162-180`).
5. Account-Rotation, `preferred_account_index`, `filtered_tools`, Token-Lease und Failover werden durch einfache Lambdas umgangen.
6. Die Follow-up-Tests zählen Aufrufe, prüfen aber weder Side-Effect-Duplikate noch Concurrency, Session-ID oder das vollständige Resultat-Array.
7. Der Test „follow-up with served content“ (`tests/test_stream_retry.py:294-345`) erlaubt bewusst einen zweiten Upstream-Run nach sichtbarem Text. Das Verhalten ist dokumentiert, aber nicht gegen doppelte Seiteneffekte oder partielle Antworten abgesichert.
8. Reasoning-only gilt als leer und löst Retry aus (`tests/test_stream_retry.py:419-433`). Es fehlt ein Negativtest, ob eine legitim eigenständige Reasoning-Antwort ohne Toolrunde erhalten bleiben muss.
9. Leerantwort-Retry ist nur im Streampfad getestet. Non-Stream-Leerantwort, leere Teilantwort plus Call, Tool-only-Antwort, negative Retry-Grenzen und Abbruch während eines leeren Chunks fehlen.
10. Beim Give-up-Test wird nur ein `[DONE]`-Chunk geprüft (`tests/test_stream_retry.py:436-447`), nicht ein wirklich leeres, semantisch korrektes Endergebnis.
11. Die Config-Fixture enthält einen unsichtbaren Unicode-Separator in der Basis-URL (`tests/test_stream_retry.py:20`). Da `_open_chat_stream` ersetzt wird, prüft der Test diese URL nie; der Fall kann daher unbemerkt regressionsanfällig bleiben.

**Bewertung:** Gute deterministische Retry-Logiktests, aber erhebliche Lücken bei Upstream-Fehlerklassen, Cleanup und Partial-Output.

## 9. Datei-Audit `tests/test_tool_parser.py`

**Prüfstatus:** Vollständig gelesen; 39 Tests; bekannte Parserfälle STARK, Gesamtdeckung TEILWEISE.

### Abgedeckte Regressionsklassen

- Kanonischer JSON-Call, Einzelobjekt, terminierter Stream und flach extrahierte Sibling-Parameter (`tests/test_tool_parser.py:6-46`).
- Fehlender Array-Close mit erhaltendem Modelltext und Nicht-Rewrite anderer Malformed-JSON (`tests/test_tool_parser.py:49-69`).
- DSML, kanonisches Invoke-Markup, verschachtelte Parameter, CJK und Arrays (`tests/test_tool_parser.py:72-105`).
- Blockierte/nicht deklarierte Toolnamen auf Parser-Ebene (`tests/test_tool_parser.py:108-126`).
- Schutz von DSML/ML-Markup in vollständigen Codefences (`tests/test_tool_parser.py:129-139`, `tests/test_tool_parser.py:373-383`).
- Snippet-plus-Volltext-Duplikat, Whitespace vor Terminator und ein reproduzierter Live-Leak (`tests/test_tool_parser.py:142-197`).
- Multi-Call-Recovery bei fehlender Klammer (`tests/test_tool_parser.py:199-218`).
- Zeichenweises Streaming für DSML und ML ohne sichtbares Markup-Leak (`tests/test_tool_parser.py:221-241`, `tests/test_tool_parser.py:321-335`, `tests/test_tool_parser.py:400-416`).
- Mehrere DSML-CDATA-Schadensbilder (`tests/test_tool_parser.py:244-318`).
- XML/ML-Markup, verschachtelte Objekte, Prä-/Suffixtext und leere Toolblöcke (`tests/test_tool_parser.py:338-397`, `tests/test_tool_parser.py:480-487`).
- Ablehnung nichtkanonischer Legacy-Markups und fehlender Parameter (`tests/test_tool_parser.py:419-443`).
- Salvage eines fehlerhaften ML-Roots, param_name-only-Payload, Think-Fallback-Allowfilter und normales Inline-JSON (`tests/test_tool_parser.py:446-535`).
- Nackte Call-Arrays, kaputte/duplizierte Fence-Ausgabe, Komma-Siblings, führendes Komma, aufeinanderfolgende Calls und Nackt-Objekt-Heuristik (`tests/test_tool_parser.py:538-640`).

### Wesentliche Lücken

1. **Duplikate dürfen bestehen:** Der reproduktionstarke Test akzeptiert `len(tool_calls) >= 1` und prüft nur das erste Call-Argument (`tests/test_tool_parser.py:554-568`). Duplizierte Ausführung desselben Calls wäre damit vertraglich zulässig, obwohl die Benchmark-Doku Duplikate im selben Assistant-Turn als Anomalie bezeichnet (`benchmarks/benchmark.md:367`).
2. **Keine vollständige Split-Matrix:** Viele Streamingfälle nutzen nur einen fixierten Schnitt oder Zeichen-für-Zeichen für Markup. Für JSON werden nicht alle möglichen Chunk-Grenzen geprüft; ein Regression-Fall kann bei anderer Upstream-Fragmentierung unentdeckt bleiben.
3. **Vollständiges JSON-Codefence fehlt:** Es gibt Tests, die DSML/ML in Fences ignorieren, und einen kaputten ` ``json `-Fence mit bare Array. Ein vollständiges ` ```json\n{"tool_calls":...}\n``` `-Protokoll wird nicht explizit als gewünschte Call-Extraktion getestet.
4. **Unfiltered-Modus:** Mehrere Recovery-Tests übergeben `allowed_tool_names=None` (`tests/test_tool_parser.py:210`, `tests/test_tool_parser.py:313`). Dass nachgelagerte Translator-Schichten immer sicher filtern, wird nicht end-to-end bewiesen.
5. Der Test „blocked native tools“ kennt im Parser nur ein Allowset; eine echte globale Blockliste wird hier nicht geprüft (`tests/test_tool_parser.py:108-126`).
6. **Falsch-Positive-Heuristik:** Ein beliebiges JSON-Objekt mit passenden Schreibfeldern wird zum `write`-Call umgedeutet (`tests/test_tool_parser.py:628-640`). Ein Test gegen legitimen JSON-Text, Markdown-Beispiele oder ähnliche Dateiinhalte fehlt.
7. Keine Grenztests für: leere Allowset, unbekannte Toolnamen, `null`-Argument, nichtobjektartige Calls, duplicate JSON keys, `NaN`/`Infinity`, tiefe oder große Struktur, Steuerzeichen, extrem lange Strings oder Ressourcenlimits.
8. Keine Byte-/UTF-8-Grenzen, keine kombinierten DSML-/JSON-Chunks und kein vollständiger End-to-End-Stream vom HTTP-Client bis zum Tool-Call.
9. Viele Accumulatortests kontrollieren nur `[0]`, ohne die Call-Anzahl zu prüfen; zusätzliche Duplikate können unentdeckt bleiben.

**Bewertung:** Ungewöhnlich gute Abdeckung konkreter historischer Live-Leaks. Die Tests sichern jedoch einzelne Strings stärker als das Verhalten über Eingaberaum und Streamgrenzen.

## 10. Datei-Audit `tests/test_translator.py`

**Prüfstatus:** Vollständig gelesen; 44 Tests; breite Happy-Path-Abdeckung, insgesamt TEILWEISE.

### Abgedeckt

- Promptbau, History, Re-Anchor und Tool-Schema-Hinweise (`tests/test_translator.py:11-61`).
- JSON-, DSML- und Think-Fallback für Non-Stream und Stream (`tests/test_translator.py:64-92`, `tests/test_translator.py:173-234`).
- Sichtbarer Fallback bei blockiertem Tool und leere Antwort (`tests/test_translator.py:94-139`).
- Shell-Argumentnormalisierung für JSON-String, Quotes, Plaintext, Cmdlet-Array und native Exe-Liste (`tests/test_translator.py:237-301`).
- Tool-Preamble-Unterdrückung und Protokoll-Deferral (`tests/test_translator.py:304-378`).
- `tool_choice` none/specific, Filterung nativer URL-Tools und blockierter History (`tests/test_translator.py:410-510`).
- CherryFetch-URL-Reparatur und Entfernen eines invaliden Tool-Fehlers (`tests/test_translator.py:513-562`).
- Fallback-URL im Accumulator (`tests/test_translator.py:564-598`).
- History-Signaturen, Echo-Drop, 36-fache native Deduplizierung und unallowed native Calls (`tests/test_translator.py:601-690`).
- Markdown-Parttrenner und Snippet-plus-Finish-Idempotenz (`tests/test_translator.py:693-759`).
- Reparatur fehlender Call-ID, Python-Quoting-Compile-Oracle und Raw-Tool-Arg-Reparatur (`tests/test_translator.py:762-823`, `tests/test_translator.py:1131-1150`).
- Midstream-Protokoll-Deferral (`tests/test_translator.py:826-884`).
- History-Kompression unter und über Budget (`tests/test_translator.py:887-944`).
- Stringified-JSON-Array/Dict-Unpacking, Toolround-Erkennung und Prompt-Sprachlock (`tests/test_translator.py:947-1000`).
- Native `open`- und Sandbox-Mapping sowie Dummy-Sandbox-Erkennung (`tests/test_translator.py:1003-1128`).
- Write-Schema-Schutz und `file:///`-Normalisierung (`tests/test_translator.py:1153-1208`).

### Stärken

- Die Tests decken sowohl Parser-Resultat als auch Translator-/Accumulator-Ausgabe ab.
- Idempotente Full-Text-Merge- und Echo-Filter-Regressionen sind explizit vorhanden.
- Der 36fache native Echo-Fall bildet einen umfangreichen Deduplizierungs-Stressfall ab (`tests/test_translator.py:642-660`).
- Der Write-Test sichert Schema-Schutz für String und Dict (`tests/test_translator.py:1153-1188`).
- Die History-Kompression prüft zumindest, dass ein Tool-Ergebnis nicht direkt vor dem dazugehörigen Assistant-Call landet (`tests/test_translator.py:929-933`).

### Lücken, Sicherheits- und Robustheitsrisiken

1. **Fallback-URL aus Unterhaltung:** Der Test fixiert, dass eine fehlende Tool-URL aus vorherigem User-Text ergänzt wird (`tests/test_translator.py:513-560`, `tests/test_translator.py:564-598`). Es fehlen Negativtests für andere Hosts, lokale Adressen, Credentials, `file:`/Data-URLs, mehrere URLs und Prompt-Injection. Der Test sichert damit die Funktion, nicht deren Herkunftssicherheit.
2. **Native Sandbox → Bash:** Der Test verlangt, dass nativer Sandbox-Code als Bash gesendet wird (`tests/test_translator.py:1042-1092`). Es gibt keinen Test für Policy, Timeout, Ressourcenlimits oder ein Szenario, in dem die automatische Mapping-Funktion unterbleiben muss. Auf Benchmarkebene wird `execute_sandbox_code` gerade als verboten/Anomalie beschrieben (`benchmarks/benchmark.md:50`, `benchmarks/benchmark.md:86-88`); diese Tests sichern die Behauptung nicht, sondern prüfen das Gegenteil auf Proxyebene.
3. **Native `open` → `read`:** Nur ein lokaler Pfad wird geprüft (`tests/test_translator.py:1003-1039`). URL, `file:`, Escape-Pfade, nicht existente Pfade, fehlendes Read-Tool und Privilege-/`lineno`-Varianten fehlen.
4. Die Mapping-Tests prüfen überwiegend private interne Listen, nicht das finale HTTP-/SSE-Ergebnis. In `tests/test_translator.py:1034-1039` und `tests/test_translator.py:1087-1092` bleiben `chunks` ungeprüft.
5. **Schwache Assertions:** Mehrere Tests inspizieren nur das erste Tool-Call-Element und erzwingen keine exakte Anzahl (`tests/test_translator.py:85-91`, `tests/test_translator.py:228-234`). Dadurch sind zusätzliche oder doppelte Calls nicht zuverlässig ausgeschlossen.
6. `test_accumulator_defers_text_while_tool_protocol_pending` endet mit `assert ... or ...`; die zweite Bedingung ist sehr schwach und kann nicht beweisen, dass Text erhalten oder korrekt geparkt wurde (`tests/test_translator.py:360-377`).
7. Keine umfassenden Prompt-Tests für Systemrollen, Multimodal-Content, leere/None-Inhalte, Rollenwechsel, Injection-Delimiter, extreme Länge oder Toolresultat-Listen.
8. Keine vollständigen Eventsequenzen für `init → process → finish`, doppeltes Finish, Out-of-order-Parts, unbekannte Part-Typen, fehlende IDs, mehrere Logic-IDs oder Abbruch nach Tool-Call.
9. History-Kompression prüft weder Determinismus noch Nichtmutation, Standardbudget, einzelne zu große Runden, Unicode, strukturierte Content-Blöcke oder Aufbewahrung zusammengehöriger Runden an der exakten Schnittgrenze. Der Budgettest erlaubt zudem `< 20.000` bei Budget `8.000` und misst nur ausgewählte Felder (`tests/test_translator.py:921-944`).
10. Stringified-JSON wird generell in Array/Dict umgewandelt (`tests/test_translator.py:947-960`). Tests fehlen für Felder, deren Schema ausdrücklich String verlangt; das Verhalten kann semantische Daten verändern.
11. `filePath`-Normalisierung testet nur einen Unix-Pfad. Case-Varianten, URL-Encoding, `file://host`, Windows-URI, `null`, nicht-string Pfade und Path-Traversal fehlen (`tests/test_translator.py:1191-1208`).
12. Der Quote-Repair-Compile-Oracle ist gut gegen Überreparatur abgesichert, aber nur für wenige Python-Formen. Multiline-/Heredoc-/verschachtelte Command-Quotes, Timeouts und Commandlängen fehlen.
13. Keine Tests für Auth-/Request-Sicherheit, Rate-/Concurrency-Grenzen, Queue-Unterbrechung, Cancellation oder Ressourcenfreigabe im Server.

**Bewertung:** Sehr breite Translator-Regressionsbasis, aber einige Tests fixieren heuristische Reparaturoptionen, ohne deren Sicherheitsgrenzen zu prüfen.

## 11. Datei-Audit `benchmarks/benchmark.md`

**Prüfstatus:** Vollständig gelesen; Vertragsdokumentation ist detailliert, aber nicht vollständig durch mitgelieferte Automatisierung abgesichert.

### Intern konsistente und sinnvoll codierte Teile

- Die geforderte Struktur umfasst 20 Required-Dateien; `REQUIRED_FILES` in `benchmarks/verify_auditmesh.py:24-45` enthält dieselben 20 Pfade.
- Services, Limits, 12 App-Logzeilen und 4 Security-Logzeilen stimmen zwischen `benchmarks/benchmark.md:180-260` und `benchmarks/verify_auditmesh.py:47-67` überein.
- Baseline-Metriken in `benchmarks/benchmark.md:287-329` entsprechen den Erwartungen in `benchmarks/verify_auditmesh.py:275-299`.
- Die Mutation in `benchmarks/verify_auditmesh.py:393-444` erzeugt nachvollziehbar die Sollwerte in `benchmarks/verify_auditmesh.py:251-274`.
- Die Mutation testet sinnvoll Grenzgleichheit: Fehlerrate `5/13`, Coverage `1.0` und Security `5` liegen exakt auf den Grenzwerten und müssen bestanden werden (`benchmarks/verify_auditmesh.py:428-435`, `benchmarks/verify_auditmesh.py:266-273`).
- Baseline und Mutation prüfen Kernmetriken, Reportmarker und Unveränderlichkeit der nicht ignorierten Dateien.

### Erwartete Ergebnisse

| Fall | Erwartete Kernergebnisse | Statische Absicherung |
|---|---|---|
| Baseline | 12 App-Einträge, 4 Fehler, Fehlerrate `1/3`; 3 konfigurierte und 1 unbekannter Service; 2 Dependency-Kanten; 3 Fehlercodes mit 2/1/1 Vorkommen; Coverage `2/3`; 4 Security-Events; 1/3 Checks bestanden; `NON_COMPLIANT` | Weitgehend konkret in `benchmarks/verify_auditmesh.py:275-390` geprüft. |
| Mutation | 13 Einträge, 5 Fehler, Fehlerrate `5/13`; Catalog konfiguriert; alle 3 Codes dokumentiert; Coverage `1.0`; keine broken links; 5 Security-Events; 3/3 Checks bestanden; `COMPLIANT` | Weitgehend konkret in `benchmarks/verify_auditmesh.py:251-274` und `benchmarks/verify_auditmesh.py:446-449` geprüft. |

### Doku-Behauptungen ohne ausreichende Absicherung

1. **„Unabhängiger Verifier“:** `benchmarks/benchmark.md:33-36`. Das Skript ist logisch getrennt vom erzeugten Projekt, führt dessen Code aber im selben Host-/Runner-Kontext, mit Interpreter des Runners und vollständiger Umgebung aus. Unabhängig ist es fachlich, nicht als Sicherheitsgrenze.
2. **Nur Änderungen unter `<BENCHMARK_ROOT>`:** `benchmarks/benchmark.md:46-48`, `benchmarks/benchmark.md:174-178`. Der Verifier vergleicht nur Dateiinhalte innerhalb des Roots; Zugriffe und Änderungen außerhalb, Netzwerkzugriffe und kurzzeitige Änderungen werden nicht erkannt (`benchmarks/verify_auditmesh.py:123-129`).
3. **Kein Netzwerk und nur Standardbibliothek plus pytest:** `benchmarks/benchmark.md:55-58`. Weder Import-/Dependency-Whitelist noch Netzwerkisolation existiert im Skript.
4. **Echte Unit-/Integrationstests:** `benchmarks/benchmark.md:281-283`. Der Verifier prüft nur die Existenz der drei Testdateien (`benchmarks/verify_auditmesh.py:41-43`, `benchmarks/verify_auditmesh.py:173`). Leere, triviale oder nur Ausgaben lesende Tests können die Dateiprüfung bestehen.
5. **Installierbares Projekt mit Pytest-Konfiguration:** `benchmarks/benchmark.md:166-172`. `pyproject.toml` wird nur auf Existenz geprüft; Build, Installation, Konfiguration und Entry-Point-Vertrag werden nicht validiert.
6. **Nur zwei fachliche Output-Artefakte:** `benchmarks/benchmark.md:174-178`. `output` wird vollständig vom Immutable-Snapshot ignoriert (`benchmarks/verify_auditmesh.py:69`, `benchmarks/verify_auditmesh.py:117`); beliebige zusätzliche Dateien unter `output` sind erlaubt.
7. **Exakt drei Compliance-Checks:** `benchmarks/benchmark.md:277`. Der Verifier iteriert nur über die drei erwarteten Check-Namen und verbietet keine zusätzlichen Check-Objekte (`benchmarks/verify_auditmesh.py:358-369`). Er berechnet auch nicht, dass `passed_checks` zur Liste passt.
8. **Floats nicht gerundet:** `benchmarks/benchmark.md:289-290`. `require_float` erlaubt Abweichungen bis relativ/absolut `1e-9` (`benchmarks/verify_auditmesh.py:104-108`).
9. **Vollständiger Report mit korrekten Werten:** `benchmarks/benchmark.md:331-339`. Geprüft werden nur drei Marker; Tabellenwerte, Häufigkeiten, Dokumentationsstatus und Korrelation im Report werden nicht verifiziert.
10. **Tool-Abdeckung und Tool-Disziplin:** `benchmarks/benchmark.md:62-90`, `benchmarks/benchmark.md:361-370`. Im Partition-J-Artefakt gibt es keinen Session-Export oder Prüfer für deklarierte Tools, verbotene Tools, `glob`/`grep`, `task`, `webfetch`, `question`, Session-Statistik oder Toolzweck.
11. **Tool-Protokoll-Leaks und Duplicate-Integrität:** `benchmarks/benchmark.md:366-367`, `benchmarks/benchmark.md:372-375`. Nur als Prosa im Markdown beschrieben; kein Runner-Code im Scope setzt diese Kriterien durch.
12. **Frische Session, richtiges Modell, Autonomie, Preflight und Abschlussfrage:** `benchmarks/benchmark.md:10-36`, `benchmarks/benchmark.md:341-353`, `benchmarks/benchmark.md:361-370`. Diese sind manuelle Runneraufgaben, nicht durch `verify_auditmesh.py` testbar.
13. **Phasen 0, 7, 8 und 9:** `benchmarks/benchmark.md:94-131`. Weder Todo-Nutzung, Subagent, lokaler Webfetch noch Session-DB-Statistik werden im Verifier geprüft.
14. **Funktional bestanden nur mit Pytest und Verifier:** `benchmarks/benchmark.md:355-368`. Der Verifier selbst startet die generierten Projekttests nicht; nur der separat dokumentierte Runner-Befehl tut dies. Ein Aufruf des Verifiers allein erfüllt die Doku-Passbedingung nicht.

**Bewertung:** Ein sehr guter Spezifikations- und Fixture-Vertrag, aber kein vollständiges automatisches Benchmark-Gate.

## 12. Datei-Audit `benchmarks/verify_auditmesh.py`

**Prüfstatus:** Vollständig gelesen; fachlich brauchbarer Baseline-/Mutationstest, Sicherheitsstatus RISIKO.

### Stärken

- Strikte Typvergleiche in `values_equal` verhindern mehrere Verwechslungen von Boolean, Integer und Float (`benchmarks/verify_auditmesh.py:85-101`).
- Fehlende Dateien und typfremde JSON-Grundformen werden früh abgewiesen (`benchmarks/verify_auditmesh.py:169-208`, `benchmarks/verify_auditmesh.py:240-249`).
- Services, Limits, Logzeilen, Runbook-Headings und lokale Links werden konkret geprüft (`benchmarks/verify_auditmesh.py:177-237`).
- Die Metrics werden fast vollständig gegen Baseline oder Mutation validiert (`benchmarks/verify_auditmesh.py:240-390`).
- Das Projekt wird zweimal ausgeführt: einmal im echten Root und einmal in einer temporären Kopie mit veränderten Eingaben (`benchmarks/verify_auditmesh.py:452-466`).
- Die Child-Ausführung besitzt einen 60-Sekunden-Timeout (`benchmarks/verify_auditmesh.py:139-151`).
- Dateiänderungen innerhalb des geprüften Roots werden über SHA-256-Snapshots erkannt, außer in expliziten Ignorierlisten (`benchmarks/verify_auditmesh.py:111-129`).
- Temporäre Mutationsdaten werden nach Abschluss durch `TemporaryDirectory` entfernt (`benchmarks/verify_auditmesh.py:393-449`).

### Hauptbefunde

#### 12.1 HOCH — Keine Sicherheitsgrenze für erzeugten Code

`run_pipeline` übernimmt die komplette Runner-Umgebung und startet den erzeugten Python-Code direkt (`benchmarks/verify_auditmesh.py:131-147`). Es gibt keine Sandbox, kein Allowlist-Environment, keine Netzwerkisolierung, kein Dateisystem-Chroot und keine Prozess-/Ressourcengrenze außer einem Timeout.

**Folge:** Erzeugter oder kompromittierter Code kann Umgebungsvariablen lesen, Netzwerkverbindungen aufbauen, außerhalb des Benchmark-Roots schreiben/lesen und Subprozesse starten. Der nachträgliche Root-Snapshot bemerkt davon nur persistente Dateiänderungen innerhalb des Roots.

#### 12.2 HOCH — Fehlerausgabe kann Secrets oder sensible Inhalte zurückgeben

Bei CLI-Fehlercode werden stdout und stderr des Child-Prozesses ungefiltert in die Fehlermeldung übernommen (`benchmarks/verify_auditmesh.py:153-158`). Bei Erfolg verschwinden sie, bei Fehler können bis zu 3.000 beliebige Zeichen ausgegeben werden.

**Folge:** Ein Fehlerpfad kann Secrets oder sensible Daten leaken, falls der erzeugte Code sie aus der geerbten Umgebung ausgibt. Es gibt keine Redaktion.

#### 12.3 HOCH — Symlinks umgehen die implizite Root-Grenze

- `Path.is_file()` folgt Symlinks bei Required-Dateien (`benchmarks/verify_auditmesh.py:173`).
- `Path.read_bytes()` in Snapshot und `read_text()` folgen ebenfalls Symlinks (`benchmarks/verify_auditmesh.py:78`, `benchmarks/verify_auditmesh.py:119`, `benchmarks/verify_auditmesh.py:210-224`).
- `shutil.copytree` wird ohne `symlinks=True` aufgerufen und dereferenziert Symlinks standardmäßig (`benchmarks/verify_auditmesh.py:396-400`).
- `output` wird ignoriert, ohne den Typ oder den Linkzielpfad zu prüfen (`benchmarks/verify_auditmesh.py:69`, `benchmarks/verify_auditmesh.py:117`).

**Folge:** Ein Projekt kann Required-Dateien oder Output auf Ziele außerhalb des Roots zeigen lassen. Verifier kann externe Dateien lesen/kopieren/hashen; ein Output-Symlink kann Schreibzugriffe nach außen umgehen.

#### 12.4 HOCH — Prozessgrenze erfasst keine Nachfahren oder Ressourcen

`subprocess.run` beendet bei Timeout nur den direkten Child-Prozess zuverlässig. Keine Prozessgruppe, Session, cgroup, Jobobjekt-Äquivalent, Dateideskriptor-, Speicher- oder Output-Limit-Prüfung ist vorhanden. `capture_output=True` kann außerdem unbegrenzt Speicher verbrauchen (`benchmarks/verify_auditmesh.py:139-147`).

#### 12.5 HOCH/MITTEL — Projekttests und Installierbarkeit werden nicht verifiziert

Der Verifier prüft nur, dass drei Testdateien und eine `pyproject.toml` existieren (`benchmarks/verify_auditmesh.py:173`). Er startet weder `pytest` noch Build/Installation. No-op-Tests können bestehen, solange die erzeugte CLI für sich genommen die Sollmetriken liefert; die Tests beweisen dann keine fachliche Testabdeckung. Damit sind `benchmarks/benchmark.md:166-172` und `benchmarks/benchmark.md:281-283` nicht automatisch abgesichert.

#### 12.6 MITTEL — Output-Vertrag ist zu schwach

- Zusätzliche Dateien unter `output` sind erlaubt.
- Zusätzliche Top-Level-Metrikschlüssel sind erlaubt, passend zu „mindestens“, aber nicht zu einer stärkeren Schemaversion.
- Zusätzliche Check-Objekte sind erlaubt, obwohl genau drei Checks gefordert werden.
- `passed_checks` wird als Sollwert geprüft, aber nicht aus den tatsächlich vorhandenen Checks berechnet.
- Im Report werden nur Header-Marker, ein `ERR-404`-Marker und Status geprüft (`benchmarks/verify_auditmesh.py:376-385`).

#### 12.7 MITTEL — Float-Vertrag widerspricht der Implementierung

Die Doku verbietet Rundung, `require_float` akzeptiert aber Toleranz `1e-9` (`benchmarks/verify_auditmesh.py:104-108`). Das ist für robuste numerische Vergleiche sinnvoll, sichert aber nicht die behauptete exakte Repräsentation.

#### 12.8 MITTEL — Unvollständige Fehlerbehandlung

Nur `read_json`, `subprocess.run` und selbst definierte `VerificationError` werden in kontrollierte FAIL-Ausgaben überführt. Nicht abgefangen werden unter anderem:

- `UnicodeDecodeError` in mehreren `read_text`-Aufrufen,
- Fehler aus `rglob`, `read_bytes`, `shutil.copytree`, `write_text` und Snapshot-Hashing,
- unerwartete Exception-Typen im Verifier selbst,
- Diskfull-/Permission-/Race-Fehler.

Diese Fälle enden mit einem Stacktrace statt des dokumentierten `FAIL AuditMesh benchmark: ...`-Vertrags.

#### 12.9 MITTEL — Link-Parser ist bewusst eng, aber nicht robust

`local_markdown_links` erkennt nur Inline-Links mit einfacher Klammerform und schließt nur `http://`, `https://` und `#` aus (`benchmarks/verify_auditmesh.py:161-166`). Referenzlinks, Bilder, `<...>`-Links, `mailto:`, escaped Klammern, relative Pfadnormalisierung und URL-Encoding fehlen. Für die fest vorgegebenen minimalen Links reicht es; als allgemeiner Markdown-Linkvalidator nicht.

#### 12.10 MITTEL — Immutable bedeutet nicht unverändert im umfassenden Sinn

Der Snapshot erkennt nur Namen und Byteinhalt. Nicht erkannt werden:

- Änderungen an Berechtigungen, Ownership oder xattrs,
- Lesezugriffe und kurzzeitige Änderungen mit späterer Wiederherstellung,
- Zugriffe außerhalb des Roots,
- Netzwerkexfiltration,
- Prozess-/IPC-Auswirkungen.

Das ist für die funktionale Snapshot-Absicht angemessen, sollte aber nicht als allgemeine Sandbox-Garantie verstanden werden.

## 13. Parser-/Streaming-Regressionsmatrix

| Behauptung/Fall | Vorhandene Absicherung | Status |
|---|---|---|
| JSON-Call mit `[]`-Terminator im selben Token | Direkter Parserfall | STARK |
| Whitespace vor Terminator | Direkter Parserfall | STARK |
| Snippet plus Full-Text-Duplikat | Ein fixierter Split plus Original-Live-Fall | TEILWEISE |
| Unbalancierte Multi-Call-Ausgabe | Non-Stream-Recovery eines Six-Call-Falls | TEILWEISE |
| DSML/ML fragmentweises Streaming ohne Leak | Zeichenweises Streaming für mehrere Payloadformen | STARK für diese Formen |
| JSON-Fence-Entschlüsselung zu echtem Call | Nur kaputter Bare-Array-Fence; kein vollständiger JSON-Wrapper-Fence | LÜCKE |
| Bare Arrays, Comma-Siblings, aufeinanderfolgende Calls | Mehrere feste Strings | TEILWEISE |
| Blockiertes/undeklariertes Tool ohne strukturierten Call | Direkter Parser- und Translator-Teiltest | TEILWEISE |
| Verbotene Duplikate im selben Turn | 36 identische native Parts dedupliziert; Bare-Array-Test erlaubt Duplikate | TEILWEISE/RISIKO |
| Kein Midstream-Protokoll-Leak | Translator-Test mit Textdelta und Finalize-Safety-Net | TEILWEISE |
| Responses-SSE über Chunkgrenzen | Ein Block- und ein Sentinel-Split | TEILWEISE |
| OpenAI-Chat-HTTP-Stream | Kein entsprechender End-to-End-Test in J | LÜCKE |
| Anthropic-Stream | Kein Test | LÜCKE |
| Upstream-Stream endet ohne Finish/[DONE] | Kein Abschluss-EOF-Test | LÜCKE |
| UTF-8-Byte-Split | Kein Test | LÜCKE |
| Fehler nach Reasoning vor sichtbarem Text | Nur generisches Client-Eventmodell, nicht vollständige Eventmatrix | LÜCKE |
| Conversation/Response/Queue-Cleanup bei Retry | Fixture kann es beobachten, Assertions fehlen | LÜCKE |

## 14. Testabdeckung nach Schicht

| Schicht | Abgedeckt | Wesentliche Lücken |
|---|---|---|
| Config | Refresh-Fallback, Sessionflags | Umgebungsisolation, Malformed-Input, übrige Config |
| Modellvarianten | Suffixmatrix, zwei GL-Modelle | Aliaskollision, Endpoint-Sichtbarkeit, kombinatorische Auflösung |
| Toolparser | 39 bekannte JSON/DSML/ML-Fälle | vollständige Split-/Fuzz-Matrix, Ressourcenlimits, False Positives |
| Translator/Accumulator | 44 History-, Echo-, Sanitize-, Deferral- und Native-Tool-Fälle | Event-Randfälle, exakte Callmenge, URL-/Path-Policy |
| GLM-Client-Retry | ein transienter Code, Stream/Non-Stream, Content-Grenze | weitere transiente Codes, Netzwerkfehler, Cleanup, Cancellation |
| Responses/Anthropic | einfache Input-/Toolchoice-/SSE-Happy-Paths | Multimodal/Tools/Streaming/Fehler, Auth und HTTP-Randfälle |
| Stdlib-HTTP-/ThreadingHTTPServer-Integration | ein lokaler Responses-Stream/Heartbeat | API-Key, CORS, Requestlimits, Fehler, OpenAI-Chat |
| Upstream-Integration | keine Live-/Protokolltreue-Tests in J | reale Eventformen, Protokollversion, Timeout/429/5xx |
| Benchmark-Fixtures | exakte Dateien und Kernmetriken | Markdown-Formen, Reportwerte, Zusatzchecks |
| Benchmark-Mutation | Logs, Doku, Limits, Services, Gleichheitsgrenzen | Fehlerpfade, alternative Mutationen, Parser-Randfälle |
| Benchmark-Tool-/Session-Gate | nur Prosa im Markdown | keine implementierte automatisierte Prüfung in J |

## 15. Sicherheitsprüfung

### Positive vorhandene Absicherungen

- Nicht deklarierte bzw. nicht erlaubte native Toolnamen werden in vielen Paths verworfen.
- Blockierte URL-Tools werden aus Schema und History gefiltert.
- Native History-Echos werden kanonisiert und dedupliziert.
- Python-Quote-Reparatur nutzt einen Compile-Oracle und verändert eine bereits funktionierende Syntax nicht.
- Write-Dict-Inhalte werden vor schema-inkompatiblen JSON-Objekten geschützt.
- Der AuditMesh-Verifier prüft die wichtigsten Fixture-Inhalte und beide erwarteten Pipelinezustände.

### Offene Sicherheitslücken im geprüften Test-/Benchmark-Setup

1. **Verifier-Isolation:** erzeugter Code mit vollständiger Umgebung und ohne Sandbox.
2. **Fehler-Logging:** unredigierte Child-Ausgabe kann Secrets enthalten.
3. **Symlink-Escape:** Root- und Snapshot-Grenzen folgen Links.
4. **URL-Fallback:** keine nachweisbare Host-/Scheme-Policy im CherryFetch-Reparaturtest.
5. **Command-Mapping:** Native Sandbox wird ohne Negativ-/Ressourcenvertrag zu Bash.
6. **Parser-Fehlklassifikation:** Nacktes Datei-JSON wird als Schreibauftrag umgedeutet.
7. **Keine Server-Securitytests:** API-Key, CORS, Requestgröße, Host/SSRF und Fehlerredaktion sind nicht abgedeckt.
8. **Keine Benchmark-Prüfung gegen No-op-Tests oder zusätzliche Tools/Abhängigkeiten/Netzwerkzugriffe.**

## 16. Robustheitsprüfung

- **Deterministisch:** Viele Tests nutzen handgebaute Fixtures ohne Netzwerk oder Uhr. Das reduziert Flakes.
- **Timing:** Nur der HTTP-Heartbeat-Test verwendet `time.sleep` mit 10-ms-Schwelle; die Robustheit dieses Tests ist timingsensitiv, aber durch nur ein Keepalive-Substring begrenzt.
- **Cleanup:** Retry-Responses, Queue-Leases und Server-Sockets werden nicht vollständig als freigegeben geprüft.
- **Abbruch:** Keine Test-Timeouts für Parser/Accumulator/History; eine Endlosschleife kann die Suite blockieren.
- **Encoding:** CJK-Text wird funktional getestet, aber keine UTF-8-Chunkgrenze.
- **Malformed Input:** Viele Parserformen sind abgedeckt; JSON-Typen, extreme Größen, tiefe Strukturen und teilweise geschriebene Endframes fehlen.
- **Umgebung:** Configtests sind nicht vollständig von realen Environment-Variablen isoliert.
- **Verifier:** 60-Sekunden-Timeout vorhanden, aber keine Prozessgruppen-/Ressourcen-/Netzwerkgrenze und unvollständige Exception-Abdeckung.

## 17. Aussagekraft von Testanzahl und Testresultat

- Statisch enthalten die sechs Testdateien **115 Testfunktionen**: 2 + 7 + 10 + 13 + 39 + 44.
- Es gibt keine Parametrisierung, die zusätzliche Testfälle erzeugt.
- Wegen des ausdrücklichen Ausführungsverbots ist weder die Gesamtzahl „bestanden“ noch irgendein einzelnes Ergebnis bestätigt.
- Die vorhandenen `.pyc`-Dateien beweisen nur, dass Python die Module irgendwann kompiliert/geladen hat; sie sind kein Beleg für aktuelle Testresultate.
- Ohne eine im Partition-J-Scope enthaltene Coverage-Konfiguration oder Coverage-Ausgabe kann keine Aussage zu Zeilen-, Branch-, Pfad- oder Mutationsabdeckung gemacht werden.

## 18. Priorisierte Lücken

### P0 — Vor vertrauenswürdiger Verifier-Nutzung

1. Erzeugten Code in einer echten Sicherheitsgrenze ausführen; zumindest Environment-Allowlist, kein Secret-Erbe, Netzwerk-/Dateisystemisolierung und Prozessgruppen-/Ressourcenlimits vorsehen.
2. Child-Ausgaben vor Ausgabe vollständig redigieren oder bei Fehlern nicht wiedergeben.
3. Symlinks, Hardlink-/Mount-Anomalien und Output-Linkziele ablehnen; Root außerhalb definierter Workspace-Grenzen ablehnen.

### P1 — Benchmark-Vertrag schließen

1. Generierte Projekttests im Verifier tatsächlich ausführen und No-op/Trivialtests zurückweisen oder separat bewerten.
2. `pyproject.toml` parsen, Build/Installation und konfigurierten Pytest-Entry-Point prüfen.
3. Exakt drei Checks, vollständige Reportwerte, erlaubte Output-Dateien und Float-/Schemavertrag eindeutig festlegen und exakt prüfen.
4. Runner-Artefakt für Session-Extraktion und Tool-/Anomalieprüfung bereitstellen oder die Doku als manuelle Checkliste kennzeichnen.

### P1 — Parser-/Stream-Regressionen

1. Exakte Callanzahl in allen Duplicate-/Sibling-Tests erzwingen.
2. Vollständiges JSON-Protokoll in Codefences testen.
3. Exhaustive Split-/Chunk-Matrix für kritische JSON-Frames und UTF-8-Grenzen ergänzen.
4. Mixed allowed/blocked, malformed, duplicate, huge/deep JSON und untrusted-URL-Fallback testen.
5. Cleanup von Response, Conversation und Queue-Lease nach Erfolg, Fehler und Timeout direkt behaupten.

### P2 — Breitere Produktrobustheit

1. API-Key, CORS, Requestlimits, Fehlerpfade und OpenAI-/Anthropic-Streaming ergänzen.
2. Alle transienten Fehlercodes, Netzwerkexceptions, Truncated SSE und Upstream-EOF getrennt testen.
3. Config- und URL-/Pfadtests vollständig von Prozessumgebung und untrusted Text isolieren.

## 19. Abschlussstatus

- **Datei-Audit:** abgeschlossen.
- **Textvollständigkeit:** 8/8 Dateien vollständig gelesen.
- **Testausführung:** bewusst nicht durchgeführt; kein PASS/FAIL behauptet.
- **Gesamtbewertung:** Die Partition enthält eine starke Sammlung konkreter Parser-/Streaming-Regressionstests und einen nachvollziehbaren AuditMesh-Baseline-/Mutation-Oracle. Als Gesamtnachweis ist sie dennoch **teilsweise ausreichend**: Security-Isolation, Testauthentizität, Tool-/Session-Gates, exakte Vertragsprüfung und mehrere Streaming-/Cleanup-Randfälle sind nicht abgesichert.
<!-- END PART J -->

## Anhang K — Ignorierter Node-Dependency-Baum

<!-- BEGIN PART K -->
## Partition K — vollständiges Inventar `.opencode/node_modules`

Der vollständige Datei-, Verzeichnis-, Hash-, Rechte- und Lockfile-Report mit **jedem einzelnen Blatt-Eintrag** steht als laufender Audit-Anhang unter `/workspaces/MAIN/.runtime/revision-parts/K.md` (4.192 Zeilen). Er wird hier zusammengefasst, damit `Revision.md` nicht durch 3.648 Third-Party-Einträge unlesbar wird; die vollständige Einzelabdeckung bleibt darin nachvollziehbar.

## Prüfrahmen und Abdeckung

- **Scope:** ausschließlich `/workspaces/MAIN/.opencode/node_modules` unter `/workspaces/MAIN`; keine anderen Dependency-Bäume wurden bewertet.
- **Zweck:** read-only Bestandsaufnahme des vollständigen ignorierten Dependency-Bestands einschließlich aller darunterliegenden Lock-, Cache- und Metadateien.
- **Änderungen:** keine Installation, keine Löschung, kein Überschreiben und kein Ausführen von Paketcode. Geschrieben wurde nur der Teilreport.
- **Ignore-Status:** Der Dependency-Baum ist durch `.opencode/.gitignore` ignoriert.
- **Prüfzeit:** `2026-09-23T22:22:55.702568+00:00`.

### Abdeckungsnachweis

| Prüfobjekt | Ergebnis | Status |
|---|---:|---|
| Rekursive Einträge unterhalb des Scopes | 3.925 | vollständig enumeriert |
| Reguläre Dateien | 3.648 | jede Datei im vollständigen Anhang A des Teilreports |
| Symlinks | 7 | jeder Symlink im vollständigen Anhang A |
| Verzeichnisse | 270 | jedes Verzeichnis im vollständigen Anhang B |
| Paketwurzeln | 27 | gegen `package.json` geprüft |
| `package.json`-Manifeste | 42 | JSON parsebar; kein Parsefehler |
| Fehler beim Traversal/Hashing | 0 | keines |

- Blatt-Einträge insgesamt: **3.655** (3.648 Dateien + 7 Symlinks).
- Logische Dateigrößen: **54.790.444 B**; Blockbelegung laut Report ca. 65.294.336 B.
- Deterministischer Scope-Baumdigest: `sha256:d1014032d22d00f7be08295c7de4065b1359a70c7b4488ce32ed013aba3ffaf6` (Dateipfad, Größe, Datei-SHA256, Symlink-Zieltext).
- Kleine lesbare Textdateien (≤ 2 MiB): 3.642 zeilenweise verarbeitet; Inhalte wurden nicht ausgegeben, nur Trefferarten/Zeilennummern gespeichert.
- Zwei große Textdateien wurden nicht vertieft, aber vollständig inventarisiert: `effect/dist/unstable/httpapi/internal/httpApiScalar.js` und `effect/src/unstable/httpapi/internal/httpApiScalar.ts`.
- Vier Native-ELF-Dateien und vier Minified/Bundle-Kandidaten wurden strukturell inventarisiert, nicht als Quellcode interpretiert.

## Kurzfazit und Prüfstatus

| Prüfung | Status | Befund |
|---|---|---|
| Lock-Abgleich | PASS | Alle 27 installierten Paketwurzeln stimmen in Version mit Root- und Internal-Lock überein; keine zusätzliche Paketwurzel. |
| Optionale Plattformpakete | PASS/INFO | Sechs optionale Native-Plattformpakete sind im Root-Lock; auf Linux x86_64 ist nur das Linux-x64-Paket installiert. |
| Lock-/Cache-Metadaten | PASS | `.opencode/node_modules/.package-lock.json` ist die einzige zusätzliche Lockdatei. |
| Symlink-Scope | PASS | Alle 7 Symlinks zeigen auf existierende Ziele innerhalb `node_modules` und innerhalb `MAIN`. |
| Pfadnormalisierung | PASS | Keine absoluten, `..`-enthaltenden, Backslash-/NUL-Pfade; Lock-Schlüssel nur unter `node_modules/`. |
| npm-Abhängigkeitsbaum | PASS | `npm ls --all --json --offline` endete mit Exit 0 und ohne `problems`. |
| Node-Engine | WARN | Laufzeit `v18.19.1`; `ini@7.0.0` verlangt wesentlich neueres Node, `toml@4.3.0` mindestens Node 20. |
| Native-/Install-Risiko | WARN | `msgpackr-extract@3.0.4` hat ein Install-Skript; vier ELF-Addons und ein ausführbarer Prebuild-Downloader sind vorhanden. |
| Dateirechte | WARN | 270 Verzeichnisse `0777`, 3.637 Dateien `0666`, 7 Executables `0755`, 4 Native-Dateien `0777`; alle Einträge uid/gid 1000. |
| Credential-Scan | REVIEW | Keine High-Confidence-Provider-Key-/Private-Key-Treffer; generische Treffer wurden als Schema-/Beispiel-/Testinhalt eingeordnet. Große/Binärdateien nicht als credential-frei behauptet. |
| CVE-Status | N/A | Kein Online-`npm audit`/Advisory-Abruf; kein CVE-Status behauptet. |

## Installierte Pakete und relevante Befunde

- Root-Manifest: `@opencode-ai/plugin` exakt `1.18.30`; Root-Lock und Internal-Lock stimmen überein.
- Root-Lock: `lockfileVersion=3`, 32 Paket-Schlüssel; Internal-Lock: `lockfileVersion=3`, 27 installierte Paket-Einträge.
- 42 Manifeste wurden gelesen und geparst: 27 Paketwurzeln, 15 eingebettete Untermanifeste mit `name: null`.
- Lockfile-Integritätswerte sind keine Credentials; die Datei-SHA-256 im Anhang sind lokale Byte-Prüfungen, kein npm-Tarball-Integrity-Beweis.
- `msgpackr-extract@3.0.4` besitzt ein `install`-Skript und den ausführbaren Einstieg `download-msgpackr-prebuilds`; er wurde nicht ausgeführt.
- `node-gyp-build-optional-packages` enthält ausführbare Loader-/Testskripte; sie wurden nicht ausgeführt.
- Die vier Native-Dateien sind glibc-/musl-/NAPI-ELF-Addons des Linux-x64-Pakets; keine Disassembly oder Codeausführung.
- Alle Root-/Internal-Lock-`resolved`-Einträge zeigen auf `https://registry.npmjs.org`; keine `file:`-, `git:`- oder unbekannten Hosts.
- Third-Party-Source, Source Maps und Bundles wurden nicht als MAIN-Quellcode interpretiert.
- Vollständige Dateiliste, jeder Hash, jeder Symlink, jedes Verzeichnis und jeder Prüfstatus: `.runtime/revision-parts/K.md`, Anhang A/B.

## Grenzen

Die Dependency-Dateien wurden inventarisiert und kleine Textdateien zeilenweise verarbeitet; große Bundle-/Vendor-Dateien wurden nicht als eigene fachliche MAIN-Implementierung analysiert. `.runtime`-Dependency-/Cache-Dateien werden durch die separaten Partitionen L und M erfasst. `Revision.md` wurde durch diesen Teilprozess nicht verändert.
<!-- END PART K -->

## Anhang L — Ignorierte Firefox-Runtime und Browserprofil

<!-- BEGIN PART L -->
## Partition L — ignorierter `.runtime/`-Bestand

Der vollständige Datei-/Verzeichnis-/Signatur-/Rechte-Report mit 1.175 Einträgen steht unter `/workspaces/MAIN/.runtime/revision-parts/L.md` (1.309 Zeilen). Die folgende Zusammenfassung dokumentiert die wesentlichen Befunde und die Prüfgrenzen.

## Prüfrahmen und Abdeckung

- **Snapshot:** 2026-09-23T22:35:10Z; ausschließlich Quellen unter `/workspaces/MAIN`.
- **Bestand:** 1.175 Einträge = 1.086 Dateien, 88 Verzeichnisse, 1 Symlink, 0 Spezialdateien; 939.588.986 B (ca. 896 MiB).
- **Umfang:** Firefox 696.982.027 B; Browserprofil 242.599.460 B.
- **Zeilenprüfung:** 50 kleine lesbare Textdateien bis 65.536 B vollständig zeilenweise und redigiert geprüft.
- **Nicht geöffnet:** 2 große Textdateien, 1.036 Binär-/Archiv-/DB-/Cache-/sonstige Dateien; Symlink wurde nicht verfolgt.
- **Keine Aktion:** kein Start, keine Installation, keine Löschung, kein Netzwerk-/Updatevorgang; `.runtime/` ist ignoriert.

## Firefox- und Versionsbefund

| Bereich | Befund |
|---|---|
| Root-Runtime | Firefox 155.0.1, Build 20260903215306; entspricht dem Pin in `infra/scripts/firefox-install.sh:7`. |
| Update-Staging | `updated/` enthält Firefox 156.0.1, Build 20260921121718, Status `Install Pending`/`applied`. |
| Update-Policy | `policies.json` fehlt; keine explizite `app.update.*`-Pref gefunden. |
| Installer-Abgleich | `firefox-install.sh:18` beendet bei Root 155.0.1 und normalisiert das 156.0.1-Staging nicht. |
| Locks | `.parentlock`, Firefox-Update-Lock, WAL/SHM und mtime sind nur Indizien; kein aktiver Prozess/Listener wurde behauptet. |
| Signaturen | 57 ELF, 154 GZIP, 8 ZIP/XPI, 2 MAR, 32 SQLite-Magic, 11 Mozilla-LZ4. |

## Profil-, Cache- und Loginrisiken

- `.runtime/firefox-profile` besitzt `0777`-Wurzelrechte; 971 Dateien umfassen Cookies, Schlüssel-/Zertifikatsspeicher, Verlauf, Formulare, Bookmarks, Permissions, Origin Storage, Cache, Extensions und Recovery.
- 202 Einträge haben Gruppen-/Welt-Bits; 160 Nicht-Symlink-Einträge sind gruppen-/weltbeschreibbar.
- `key4.db`/`cert9.db` können NSS-Schlüssel/Zertifikate enthalten; sie wurden nicht geöffnet.
- `cookies.sqlite`, `places.sqlite`, Form-/Verlaufsdaten, Origin Storage und Cache können vertrauliche Inhalte, Tokens oder Sessiondaten enthalten; Inhalte wurden nicht ausgegeben.
- Keine `logins.json` oder Backup davon wurde gefunden; dies beweist keine Abwesenheit von Session-/Cookie-Secrets in DB-/WAL-Inhalten.
- Ein verdächtiger kleiner Session-Identifier in `datareporting/session-state.json` wurde redigiert als mittlere Konfidenz klassifiziert; kein Wert wurde ausgegeben.
- Ein großer Teil der Runtime- und Profildateien ist Binär/DB/Archiv; daraus wird kein Secretfreiheitsnachweis abgeleitet.

## Weitere Befunde

- GDrive-State entspricht dem zum Snapshot passenden HEAD; ein kurzzeitig sichtbares `.runtime/MAIN.bundle` war transitorisch und zum finalen Snapshot nicht vorhanden. Remote-Erfolg wurde nicht geprüft.
- `.runtime/revision-parts/` enthält die parallelen Audit-Ausgaben; diese wurden nicht als Browser-/Profilinhalt interpretiert.
- Vollständige Inventarzeilen mit Pfad, Größe, Modus, mtime, Typ, Signatur, Symlink-Ziel und Prüfstatus: `/workspaces/MAIN/.runtime/revision-parts/L.md:123ff`.

## Priorisierte Schlussfolgerungen

1. Browserprofil nicht kopieren, committen oder in Support-Bundles aufnehmen; Rechte/DB/WAL sind konkrete lokale Risiken.
2. Gewünschten Firefox-Pin 155.0.1 und Pending 156.0.1 getrennt dokumentieren; Pending-Staging nicht als aktiv behaupten.
3. DB-/Cache-/Archiv-/Großdateien bleiben eine Secret-Prüflücke; kein bestätigtes Klartext-Credential wird behauptet.
4. Keine Prozess-, Port-, VNC-/noVNC-, Bundle- oder Remote-Erfolgsbehauptung aus diesem statischen Snapshot ableiten.
<!-- END PART L -->

## Anhang M — Ignorierte Venv-, Log-, Build- und Cache-Artefakte

<!-- BEGIN PART M -->
## Partition M — Ignorierte Dateien und Runtime-Artefakte

Der vollständige Manifest- und Loganalyse-Report mit 755 Pfaden steht unter `/workspaces/MAIN/.runtime/revision-parts/M.md` (1.049 Zeilen). Diese Zusammenfassung übernimmt die sicherheits- und betriebsrelevanten Ergebnisse ohne Secretwerte.

## Prüfrahmen und Abdeckung

- **Snapshot:** 2026-09-23T22:57:05Z; Scope ausschließlich `/workspaces/MAIN`.
- **Git-Ignorbestand:** 5.510 ignorierte Dateien; `.runtime/` (1.100) und `.opencode/node_modules/` (3.655) separat ausgeschlossen.
- **Analysierter Scope:** 755 Pfade = 751 reguläre Dateien, 4 Symlinks, 594 Textdateien, 157 Binärdateien.
- **Textumfang:** 20.920.107 Zeilen; kleine Textdateien vollständig zeilenweise, Logs vollständig chunkweise und nur als Musterfrequenz ausgewertet.
- **Schutzgrenze:** keine Löschung, kein Build, kein Start, kein Netzwerkzugriff; `Revision.md` wurde nicht verändert.
- **Pfad-Einordnung:** Die Output-Log-Aussagen beziehen sich auf den manuellen Restart-Pfad `infra/scripts/glm2api.sh`; der kanonische Setup-/Watchdog-Start nutzt `llm-proxies/scripts/start-glm2api.sh`.

## Kurzurteil

**Gesamtrisiko: hoch.** Kein nachgewiesener Git-Leak, aber ein kritischer lokaler Datenleckpfad:

- `llm-proxies/glm2api/.env` enthält genau ein nichtleeres Secret-Feld (`GLM_REFRESH_TOKEN`) mit JWT-Form; die Datei ist `0666`.
- Sieben Workspace-Logs belegen ca. 1,37 GiB und 20.724.321 Zeilen; mindestens 900 JWT- und 824 Bearer-Formen wurden aggregiert erkannt.
- Muster für `messages`, `content`, `reasoning_content`, `tool_calls`, Tool-Argumente, rohes SSE, Conversation-IDs sowie Authorization-/Cookie-Felder bestätigen Rohdaten- und Prompt-/Response-Ablage.
- 751 reguläre Dateien sind für alle lesbar; 141 sind gruppen-/weltweit schreibbar; relevante Elternverzeichnisse sind `0777`.
- Besonders kritisch: `.venv/.../site-packages/_virtualenv.pth` ist `0666` und führt beim Python-Start `_virtualenv` aus.
- Positiv: Keiner der 755 analysierten Pfade ist aktuell tracked und keiner erscheint in `git log --all`; ein Commit-Leak wurde nicht gefunden.

## Secret- und Konfigurationsartefakte

| Pfad | Modus | Größe | Befund |
|---|---:|---:|---|
| `.env` | `0666` | 286 B | 8 Zeilen, nur Kommentar-/Leerzeilen, keine Zuweisung/Secret-Form. |
| `llm-proxies/glm2api/.env` | `0666` | 6.180 B | 124 Zeilen, 25 Schlüssel; ein nichtleeres JWT-Secret-Feld, Wert nicht ausgegeben. |
| `llm-proxies/dist/glm2api-bundle/app/glm2api.env` | `0666` | 5.829 B | 124 Zeilen, 25 Schlüssel; keine nichtleeren Secret-Felder, byte-identisch zur Vorlage. |

- Die lokale App-Env unterscheidet sich von der kanonischen Vorlage nur beim Feld `GLM_REFRESH_TOKEN`; alle übrigen 24 Werte sind identisch.
- `llm-proxies/glm2api.env:26,30` aktiviert Debug-Logging und Raw-Dumps; ein frischer Rebuild reproduziert damit das unsichere Logging-Verhalten.
- Der Startpfad injiziert den Refresh-Token per `grep`/`sed`; der Wert kann transient im Prozessargument sichtbar sein. Der Wert wurde nicht ausgegeben.
- Kein `llm-proxies/glm2api/token.txt` und kein `conversation.txt` vorhanden.

## Logs

Die Logs waren während mehrerer Metadaten-Snapshots aktiv; Größen/Zeilen sind eine zeitliche Momentaufnahme.

| Log | Größe | Zeilen | Secret-/Musterstatus |
|---|---:|---:|---|
| `glm2api_debug.log` | 7.560.015 B | 58.124 | JWT-/Bearer-Formen vorhanden; Debug-Rohtext-Marker. |
| `glm2api_debug.log.1` | 10.483.408 B | 102.767 | JWT-/Bearer-Formen vorhanden; Debug-Rohtext-Marker. |
| `glm2api_debug.log.2` | 10.485.721 B | 97.010 | JWT-/Bearer-Formen vorhanden; Debug-Rohtext-Marker. |
| `glm2api_debug.log.3` | 10.485.167 B | 94.680 | JWT-/Bearer-Formen vorhanden; Debug-Rohtext-Marker. |
| `glm2api_debug.log.4` | 10.483.742 B | 101.518 | JWT-/Bearer-Formen vorhanden; Debug-Rohtext-Marker. |
| `glm2api_debug.log.5` | 10.462.264 B | 94.251 | JWT-/Bearer-Formen vorhanden; Debug-Rohtext-Marker. |
| `glm2api_output.log` | 1.411.698.281 B | 20.175.971 | 844 JWT-, 772 Bearer-Treffer; umfangreiche Prompt-/Tool-/SSE-Marker. |

Aggregierte Muster (Trefferzählungen, keine Zeilen-/Secretwerte): Raw Inbound JSON 2.785; `messages` 1.768; `content` 1.503.596; `reasoning_content` 413.579; `tool_calls` 2.120.952; Tool-Argumente 23.543; Raw/parsed Upstream-SSE 716.072; SSE-Data 431.863; Outbound/Final-Response 216.012; Conversation-ID 738.897; Request-Header-Dump 1.682; Authorization 1.664; Cookie 1.673; Access-Token-Feld 1.036; Refresh-Token-Feld 60; API-Key-Feld 14; Prompt-Feld 272; JWT-Form 900; Bearer-Form 824.

- `glm2api_output.log` ist 1,31 GiB und maximal 1.444.319 B pro Zeile; der Startpfad hängt stdout/stderr unrotiert daran.
- `logging_utils.py:192` rotiert den Debug-Handler bei 10 MiB mit 5 Backups; ein einzelner großer Record kann die Grenze deutlich überschreiten.
- Erzeugende Codepfade umfassen Inbound-Payload (`server.py:153`), Raw SSE (`glm_client.py:1092`), Header (`glm_client.py:1193`) und Output/Events (`translator.py:898,1336,1417`).
- Logs sind ignoriert und nicht in erreichbarer Git-History; lokale Backup-/Support-Tools könnten sie dennoch erfassen.

## PID-, Venv- und Buildartefakte

- `llm-proxies/antigravity-proxy/antigravity-proxy.pid` und `llm-proxies/glm2api/glm2api.pid`: numerisch, `0666`, beim einmaligen Check verwaist; kein dauerhafter Betriebsblocker behauptet.
- `.venv`: 649 Dateien, ca. 8,59 MiB, CPython 3.14, `pyvenv.cfg` nennt uv 0.12.13, `include-system-site-packages=false`; Projekt editable installiert.
- 36 Venv-Dateien sind gruppen-/weltweit schreibbar; `_virtualenv.pth`/`_virtualenv.py` `0666`; der `.pth`-Import ist ein direkter lokaler Codeausführungspfad.
- Installierte Dist-Info-Metadaten stimmen mit den Lockfile-Paketen überein (u. a. pytest 9.1.1, Pygments 2.21.0, packaging 26.3); `requires-python >=3.14` ist nicht patchgenau gepinnt.
- Go-Binary `antigravity-oauth-proxy`: ELF64 x86-64, 13.130.866 B, Modus `0777`, Go 1.25.7, passende Git-Revision; ignoriertes Build-Artefakt, nicht kanonisch.
- Python-Bytecode: 156 Dateien (135 Python 3.14, 21 Python 3.12); ältere 3.12-Caches können stale sein.
- Bundle-Staging: 36 Dateien, 30 identisch und 6 gegenüber der kanonischen Quelle verschieden; Stage ist kein zuverlässiger aktueller Reproduktionsstand.

## Rechte und Prüfgrenzen

- 751 reguläre Dateien; 141 gruppen-/weltweit schreibbar. Der Report bewertet Rechte als aktuellen Zustand, nicht als dauerhafte Installationseigenschaft.
- Textdateien wurden vollständig verarbeitet; Logwerte nur aggregiert. Binärdateien wurden per Magic/Header und Go-Metadaten klassifiziert, nicht disassembliert.
- Symlinks wurden strukturell erfasst; Zielinhalte außerhalb des Repo-Roots wurden nicht inventarisiert.
- `.runtime/` und `.opencode/node_modules/` wurden separat durch L und K geprüft; keine Builds, Tests, Starts, Löschungen oder Netzwerkaktionen wurden ausgeführt.
- Vollständiger Pfad-/Zeilen-/Hash-Master: `/workspaces/MAIN/.runtime/revision-parts/M.md:1ff`.
<!-- END PART M -->

## Anhang N — `.git`, Restbestand und Querverweise

<!-- BEGIN PART N -->
## Partition N — `.git`-Bestand, Restbestand und Querverweise

## Snapshot und Grenzen

- Arbeitsgrenze: ausschließlich `/workspaces/MAIN`.
- Snapshot-Zeitpunkt: `2026-09-24T00:36:01+02:00`.
- Git-Stand: `3acce8f531e616286a1e1f7d3ea79a809dc3587a` auf `main`, Upstream `origin/main` synchron (`+0/-0`).
- Ausschließlich read-only Git-Abfragen mit `GIT_OPTIONAL_LOCKS=0`; keine Git-Schreibbefehle, kein `add`, `commit`, `checkout`, `reset`, `gc`, `prune` oder Hook-Aufruf.
- `.git`-Blobs wurden nicht als Quellcode gelesen oder ausgegeben. Aus Object-Dateien wurden nur Namen, Größen, Objekttypen, Pack-/Index-Metadaten und Integritätsergebnisse verwendet.
- Secret-Werte, Token, Passphrasen, Credential-Helper-Werte und Remote-Credentials werden nicht wiedergegeben.
- Während der Analyse schrieb ein externer Autosave-/Parallelprozess den Bestand von `5a5b7b6ddeaeee9bfc2cdc719ef1839772ccb92f` auf `3acce8f531e616286a1e1f7d3ea79a809dc3587a` fort. `Revision.md` wechselte dadurch von untracked auf tracked. Diese externe Mutation war kein Schritt dieses Berichts; der Bericht beschreibt den Endstand.

## Kurzfazit

Die Versionsdatenbank ist strukturell intakt: alle Dateien und Links sind einer Git-Menge zugeordnet, Index und Arbeitbaum sind sauber, `fsck` ist fehlerfrei, Refs sind synchron und es gibt keine unerwarteten nicht ignorierten Dateien. Es gibt jedoch mehrere konkrete Drift-/Sicherheitsbefunde:

1. **Kritisch:** Zwei API-/Admin-Anmeldedaten stehen als Klartext-Literale in versionierten Konfigurationsdateien; ein Literal ist zusätzlich als Default im Startskript vorhanden.
2. **Hoch:** Das versionierte glm2api-Bundle ist nicht byte-identisch zum kanonischen Source; sechs Source-/Testdateien weichen ab.
3. **Mittel:** mehrere aktiv aussehende Skripte enthalten absolute Pfade außerhalb des kanonischen Repo-Pfads.
4. **Mittel:** nichtstandardmäßiges `.git/opencode` ohne gültiges Git-Objekt, versioniertes `auth`-Binary und eine leere, unreferenzierte `config.json`.
5. **Niedrig:** Firefox-Updater-Reste, ein gebrochener Runtime-Symlink, ein veralteter Kommentar und eine nicht explizit im Root-Ignore abgedeckte pytest-Cache-Regel.

## Vollständige Datei- und Statusinventur

Der komplette Pfadbestand wurde ohne Symlink-Following traversiert. `.git` wurde separat inventarisiert.

| Kategorie | Endstand |
|---|---:|
| versioniert / tracked | 178 |
| untracked, nicht ignoriert | 0 |
| ignored | 5.508 |
| Dateien und Symlinks außerhalb `.git` | 5.686 |
| reguläre Dateien außerhalb `.git` | 5.672 |
| Symlinks außerhalb `.git` | 14 |
| Verzeichnisse außerhalb `.git` | 474 |
| Dateien in `.git` | 598 |
| Verzeichnisse in `.git` | 246 |
| unklassifizierte Datei/Link-Differenzen | 0 |
| fehlende Git-Pfade | 0 |

Die ignored-Menge enthält die erwarteten Runtime-/Vendor-Bestände: 3.655 Dateien unter `.opencode/node_modules`, 971 im Firefox-Profil, 712 unter `llm-proxies/glm2api` (venv, Cache und Logs), 111 im Firefox-Runtime-Verzeichnis, 36 Bundle-Staging-Dateien unter `llm-proxies/dist`, 11 bereits vorhandene Partition-Berichte, 4 Dateien unter `.runtime/log` sowie einzelne `.env`, PID- und State-Dateien. Es gab keine Datei außerhalb von tracked/ignored/untracked.

### Größte Dateien

Die logische Dateigröße der Worktree-Dateien beträgt `2.497.892.729` Bytes; Symlink-Ziele wurden nicht mitgezählt.

| Pfad | Größe | Bewertung |
|---|---:|---|
| `llm-proxies/glm2api/log/glm2api_output.log` | 1.411.698.281 B | großer ignorierter Runtime-Log |
| `.runtime/firefox/updated/libxul.so` | 185.967.288 B | Firefox-Update-Staging |
| `.runtime/firefox/libxul.so` | 185.928.352 B | installierter Firefox-Runtime |
| `.runtime/firefox/updated/browser/omni.ja` | 55.896.246 B | Firefox-Update-Staging |
| `.runtime/firefox/browser/omni.ja` | 55.880.019 B | installierter Firefox-Runtime |
| `.runtime/firefox/updated/omni.ja` | 46.063.999 B | Firefox-Update-Staging |
| `.runtime/firefox/omni.ja` | 44.865.495 B | installierter Firefox-Runtime |
| `.runtime/firefox-profile/cache2/entries/FC8AFC6B8CD2A8F5ED27C5F3B1F176B33CF6178F` | 34.152.866 B | Browserprofil-Cache |
| `.runtime/firefox/updates/0/update.mar` | 34.133.873 B | Firefox-Update-Rest |
| `llm-proxies/antigravity-proxy/antigravity-oauth-proxy` | 13.130.866 B | ignorierter Runtime-Binary |

`glm2api_output.log` und die Debug-Logs sind ignored, aber ihr zusammengefasstes Volumen ist ein wesentlicher Betriebs-/Speicherbefund.

## Text-, Binär- und Vendor-Scan

- 186 Textdateien wurden zeilenweise gelesen: 31.085 Zeilen, ohne Lesefehler in der geprüften Textmenge.
- Die übrigen 5.500 Dateien/Links wurden als Binär-, Vendor-, Browser-, Cache-, Log- oder sonstige Runtime-Struktur katalogisiert; sie wurden nicht als Quellcode interpretiert.
- JSON-Prüfung der nicht unterdrückten Text-/Konfigurationsdateien: keine ungültige JSON-Datei festgestellt.
- Drei Secret-/Passphrase-Dateien wurden für Referenzausgaben unterdrückt; es wurden keine Zeileninhalte oder Werte ausgegeben.
- Es gibt keine case-insensitiven Pfadkollisionen, keine Kontrollzeichen in Pfadnamen, keine Hardlink-Gruppen und keine Special Files (FIFO/Socket/Device).

## Querverweise und gelöschte Pfade

Aus der Git-Historie wurden 250 zuvor gelöschte Pfadnamen ermittelt; 247 davon sind aktuell nicht als Datei/Link vorhanden. Im aktuellen Textbestand gab es 9 Treffer auf 5 historische Pfade:

| Referenz | Einordnung |
|---|---|
| `infrastructure.md:633` → `infra/docs/Kontostand.md` | explizit als gelöscht dokumentiert |
| `infrastructure.md:647` → `AUDIT.md`, `glm-api-audit.md` | historischer Audit-Changelog |
| `llm-proxies/scripts/smoke-test.sh:3` → `glm-api-audit.md` | veralteter Kommentarbezug, kein Dateizugriff |
| `llm-proxies/glm2api/structure.md:177` → `llm-proxies/patches/glm2api.patch` | explizit als nicht mehr existent dokumentiert |
| Go-Dateien → `NewFile` | False Positive durch Teilstring `NewFileProvider`; keine Pfadreferenz |

Die verbleibenden Treffer auf derzeit fehlende Pfad-Literale sind erwartete Ignore-/Deprecation-/Changelog-Verweise: `infra/browser/`, alte Chromium-Runtime-Pfade, `token.txt`/`conversation.txt`, transientes `.runtime/MAIN.bundle`, `Kontostand.md` und `llm-proxies/patches/`. Kein aktiver Start-, Import- oder Dateisystempfad wurde als fehlend und ausführbar bestätigt.

## Findings

### N-01 — Klartext-Anmeldedaten in versionierter Konfiguration (kritisch)

Nur Schlüsselnamen und Fundstellen, ohne Werte:

| Datei:Zeile | Klassifikation |
|---|---|
| `.opencode/opencode.json:12` | `tokenrouter.options.apiKey` als Literalwert |
| `.opencode/opencode.json:114` | `antigravity.options.apiKey` als Literalwert |
| `llm-proxies/antigravity-proxy/scripts/start.sh:45` | `ADMIN_API_KEY` als fest gesetzter Literal-Default |
| `.opencode/opencode.json:28`, `:45` | korrekt als Datei-Referenz klassifiziert |
| `.opencode/opencode.json:88` | lokaler, nicht-geheimer `local`-Wert |

Der Wert in `start.sh:45` wurde intern mit dem Wert in `.opencode/opencode.json:114` verglichen; beide sind identisch. Der Bericht gibt den Wert nicht wieder. `infrastructure.md:66` beschreibt dagegen ein Datei-Referenzierungsmodell für API-Keys. Da die Dateien versioniert und bereits in der Git-Historie enthalten sind, ist eine Rotation/Invalidierung der betroffenen Zugangsdaten erforderlich; es wurde hier nichts geändert.

### N-02 — glm2api-Bundle driftet vom kanonischen Source ab (hoch)

`llm-proxies/dist/glm2api-bundle.zip` ist tracked, 119.601 Bytes groß und enthält 45 ZIP-Einträge. Der read-only Bytevergleich mit `llm-proxies/glm2api` ergab Abweichungen bei:

- `src/glm2api/utils/tool_parser.py`
- `src/glm2api/utils/tool_protocol.py`
- `src/glm2api/services/translator.py`
- `src/glm2api/services/glm_client.py`
- `tests/test_translator.py`
- `tests/test_tool_parser.py`

Das widerspricht der Verifikation in `llm-proxies/scripts/build-bundle.sh:54-73`, die byte-identischen Source und vollständige Tests verlangt. Die 36 ignored Dateien unter `llm-proxies/dist/glm2api-bundle/` sind erwartbares Build-Staging und sollten nicht als committed Source behandelt werden. Im ZIP wurden keine Runtime-/Secret-Dateinamen gefunden.

### N-03 — absolute Pfade außerhalb des kanonischen Repo-Pfads (mittel)

Aktiv aussehende Skripte referenzieren alte externe Workspace-Pfade:

- `llm-proxies/antigravity-proxy/setup_oauth.sh:6`
- `llm-proxies/antigravity-proxy/setup_oauth_fixed.sh:11-13`, `:41`, `:52`
- `llm-proxies/antigravity-proxy/setup_oauth_full.sh:11-13`, `:41`, `:52`
- `llm-proxies/antigravity-proxy/setup_oauth_final.sh:9-11`, `:40`, `:51`

Die Pfade zeigen auf `/workspaces/dvcrn-antigravity-oauth-proxy`, nicht auf `/workspaces/MAIN/llm-proxies/antigravity-proxy`. Das ist im aktuellen Layout nicht reproduzierbar. Zusätzlich schreiben `infra/docs/reverse-engineering/capture.py:64` und `cdp.py:55` nach `/workspaces/reverse-engeneer/...`; diese Pfade wurden nicht ausgeführt oder außerhalb des Repositories untersucht.

### N-04 — nichtstandardmäßiges `.git/opencode` (mittel)

- `.git/opencode` ist eine 40-stellige hexadezimale Marker-Datei.
- Der referenzierte Wert ist kein vorhandenes Git-Objekt; `git cat-file -t` liefert entsprechend `could not get object info`.
- Es gibt keinen Worktree-Verweis auf den Marker.
- Die Datei ist keine Standard-Git-Ref, Index-Datei, Object-Datei oder Hook-Datei.

Sie wurde weder entfernt noch verändert und sollte separat bewertet werden.

### N-05 — versioniertes Build-Artefakt `auth` (mittel)

`llm-proxies/antigravity-proxy/auth` ist ein tracked, ausführbares Binärblob mit 9.803.629 Bytes und Mode `0777`. Setup-Skripte bauen `./auth` aus `cmd/auth`, wenn die Datei fehlt; der tracked Binary ist damit potenziell stale. Das Projekt-`.gitignore` enthält keinen Eintrag für `auth`. Binärinhalt und Credentials wurden nicht untersucht.

### N-06 — leere, nicht referenzierte `config.json` (niedrig/mittel)

Die tracked Datei `config.json:1` enthält nur `{}`. Im aktuellen Repo wurde kein Verweis darauf gefunden. Sie ist ein unerwarteter, aber funktional unkritischer Konfigurationsrest.

### N-07 — Dokumentationsdrift (niedrig)

- `infrastructure.md:24` nennt `infra/browser/` noch als Playwright-Runtime-Bestandteil, obwohl der Ordner nicht existiert und die Entfernung an anderer Stelle dokumentiert ist.
- `llm-proxies/scripts/smoke-test.sh:3` verweist auf die gelöschte `glm-api-audit.md`.
- `llm-proxies/glm2api/structure.md:176-179` und `infrastructure.md:633-648` erklären die übrigen gelöschten Audit-/Patch-Pfade selbst als historisch; diese Treffer sind nicht aktiv.

### N-08 — Ignore-/Cache-Regel (niedrig)

Die vier `.pytest_cache`-Dateien werden aktuell durch die dortige `.gitignore` selbst ignoriert. Das Root-`.gitignore` enthält keine explizite `.pytest_cache/`-Regel. Bei Entfernen dieses Cache-Selbst-Ignores könnten Cache-Dateien untracked werden. Dies ist aktuell kein Statusfehler.

## `.git`-Versionsdatenbank

### Refs und Zustand

- `HEAD` zeigt auf `refs/heads/main`.
- `HEAD`, `refs/heads/main`, `refs/remotes/origin/main` und `refs/remotes/origin/HEAD` zeigen effektiv auf `3acce8f531e616286a1e1f7d3ea79a809dc3587a`.
- Keine Tags, keine Replace-Refs, kein Shallow-Repository, kein Sparse-Checkout, kein Worktree-Unterverzeichnis.
- Keine Merge-, Cherry-Pick-, Revert-, Rebase-, Sequencer-, Bisect- oder Lock-State-Dateien.
- `packed-refs` enthält einen alten, überschatteten Eintrag `2f3336cd...`; effektive Refs sind konsistent.
- `FETCH_HEAD` zeigt auf `e276b79b...`, ein Ancestor; `ORIG_HEAD` zeigt auf `55c79621...`, ein Ancestor.
- Reflogs: HEAD 67, lokale `main` 67, `origin/main` 65, `origin/HEAD` 1 Einträge.

### Index

- 178 Indexeinträge, alle mit gewöhnlichen `H`-Status.
- Keine unmerged/deleted/skip-worktree/assume-unchanged Einträge.
- Indexgröße 21.385 Bytes, Dateimodus `0666`.
- `core.filemode=true`; der aktuelle Arbeitsbaum zeigt keine tracked Abweichung.

### Object-Speicher und Integrität

- 561 lose Objects, 4,28 MiB loose.
- 2 Packfiles, 124,17 MiB Packdaten, 3.484 Pack-Records; beide Packs besitzen `.idx` und `.rev`.
- 3.917 eindeutige Object-OIDs: 525 Commits, 2.053 Trees, 1.339 Blobs.
- `git fsck --full --no-dangling`: Exit 0, keine Diagnose.
- `git count-objects -vH`: 0 garbage, 0 prune-packable.
- Keine Alternates-, Promisor-, Commit-Graph-, Multi-Pack-Index- oder Quarantine-Struktur.
- `.git` insgesamt 132.943.455 Bytes bei 598 regulären Dateien.

### Hooks und Metadaten

- 14 Dateien in `.git/hooks`, ausschließlich `*.sample`; kein aktiver Hook.
- Kein `core.hooksPath` gesetzt; Standardpfad aktiv.
- Sample-Hooks haben Mode `0777`, werden wegen `.sample` nicht als aktive Hooks ausgeführt.
- `.git/info/exclude` enthält nur Standardkommentarzeilen.
- Mehrere veränderliche `.git`-Metadaten (`config`, `index`, `HEAD`, Refs, Logs, `opencode`) haben Mode `0666`; Pack-/Index-Dateien sind `0444`. Das ist eine Permissions-Hygiene-Abweichung, kein erkannter Korruptionsfall.

## Config- und Secret-Redaktion

Die lokale `.git/config` wurde nur über Schlüsselnamen und sichere, nicht-geheime Werte ausgewertet:

- `core.repositoryformatversion=0`
- `core.filemode=true`
- `core.bare=false`
- `core.logallrefupdates=true`
- `remote.origin.fetch=+refs/heads/*:refs/remotes/origin/*`
- `branch.main.remote=origin`
- `branch.main.merge=refs/heads/main`
- `commit.gpgsign=true`
- `credential.helper` ist konfiguriert; der Helper-Wert wurde nicht ausgegeben.
- Remote-URL ist als HTTPS auf `github.com` konfiguriert; URL, Benutzerinformationen und eventuelle Credentials wurden nicht ausgegeben.
- Keine lokale `core.hooksPath`- oder Include-Konfiguration.
- `commit.gpgsign=true`, der beobachtete HEAD-Status ist jedoch nicht signiert; die effektive Signing-Konfiguration ist damit nicht durch den Endstand nachgewiesen.

Zusätzlich wurde eine zeilenweise Secret-Metadatenprüfung ohne Werteecho durchgeführt. Sie klassifizierte die Klartextfunde in `.opencode/opencode.json:12` und `:114` sowie den Default in `scripts/start.sh:45`; Datei-Referenzen und lokale nicht-geheime Werte wurden getrennt erkannt. Test-, Beispiel- und Variablennamen wurden nicht als echte Credentials gewertet.

## Restbestand: Symlinks und Runtime

14 Symlinks wurden gefunden, ohne externe Ziele zu folgen:

- 7 Node-`.bin`-Links unter `.opencode/node_modules`, gültig.
- 2 tracked Dokumentationslinks `AGENTS.md` und `GEMINI.md` → `CLAUDE.md`, gültig.
- 4 Venv-Links unter `llm-proxies/glm2api/.venv`; darunter ein absoluter Interpreterzielpfad außerhalb des Workspace, nicht untersucht.
- `.runtime/firefox/updated/lock` → `127.0.0.1:+77863`, derzeit gebrochen/als Runtime-Link nicht auflösbar.

`.runtime/firefox/updated/`, `.runtime/firefox/updates/` und die 1,4-GB-Logs sind ignored Runtime-Reste. Sie verursachen keinen Git-Statusfehler, sind aber große, potenziell veraltete Betriebsartefakte. Es wurde kein Prozess beendet und kein Cache/Profil gelöscht.

## Empfohlene Reihenfolge (nicht ausgeführt)

1. Klartext-Literale in OpenCode- und Antigravity-Konfiguration rotieren/ungültig machen und auf File-/Secret-Referenzen umstellen.
2. `llm-proxies/dist/glm2api-bundle.zip` aus dem aktuellen Source neu bauen und die sechs Abweichungen prüfen.
3. Legacy-OAuth-Skripte und Reverse-Engineering-Ausgabepfade auf den kanonischen Repo-Root umstellen oder als historisch markieren.
4. `auth`-Binary und `.git/opencode` als Build-/Tool-Artefakte klären; nicht ungeprüft löschen.
5. Root-Ignore für `.pytest_cache` und die Firefox-Update-/Log-Reste bereinigen, sofern dies außerhalb dieses read-only-Audits entschieden wird.

## Abschluss

Erstellt wurde ausschließlich dieser redigierte Bericht unter `.runtime/revision-parts/N.md`. Es wurden keine Secrets korrigiert, keine Git-Schreiboperation ausgeführt und keine bestehende Datei verändert. Wegen der während der Analyse beobachteten externen Git-Mutation ist der Snapshot-Hash oben maßgeblich; nach weiteren Parallel-Änderungen ist eine erneute Status-/Ref-Prüfung erforderlich.
<!-- END PART N -->

## Anhang O — OpenCode-Agent und Quota-Command

<!-- BEGIN PART O -->
## Revision O — `.opencode`-Agent und Quota-Command

**Prüfdatum:** 2026-09-24
**Prüfgrenze:** ausschließlich `/workspaces/MAIN`
**Prüfmodus:** statische Vollprüfung der beiden Zieldateien zeilenweise; relevante lokale Querverweise gezielt geprüft. Kein Dienststart, keine Netzwerkanfrage, keine Runtime-Credential-Datei geöffnet und keine Credentials verwendet; die unterstützende Konfiguration wurde nur zur Risiko-Einordnung gelesen. Keine Tests oder Benchmarks ausgeführt.
**Vertraulichkeit:** Es werden keine Geheimniswerte wiedergegeben. Secretbezüge werden nur als Pfad, Zeilennummer, Schlüsselname und Risikoklasse beschrieben.

## 1. Kurzfazit

Beide Dateien sind syntaktisch plausibel und ihre zentralen Querverweise existieren im aktuellen Workspace. Die Prüfung ergibt jedoch mehrere wesentliche Grenz- und Bedienrisiken:

1. **Hoch:** Die Tool-, Pfad- und Löschregeln des `glm2api`-Agenten sind überwiegend Prompt-Anweisungen, keine vollständige Sicherheitsgrenze. Die globale Opencode-Permission `allow` bleibt sehr weit.
2. **Hoch:** Der Agent kann über `bash` und andere nicht blockierte Tools Session-Daten, Dateien und Netzwerkziele erreichen; die beiden MCP-Löschsperren werden dadurch nicht umfassend geschützt.
3. **Hoch:** Für das Quota-Command fehlen eine erzwungene Tool-/Agentenbindung, eine belastbare Ausgabeprovenienz und eine sichere Fehlerdarstellung. Die angeforderte Markdown-Tabelle entsteht durch eine nachträgliche Modelltransformation.
4. **Mittel bis hoch:** `quota.sh` kann bei Netzwerk- oder Datenfehlern hängen, leere/teilweise Daten als gültige Quota darstellen und lokale Session-Inhalte vollständig aus der Datenbank laden.
5. **Mittel:** Beide Dateien sind auf den aktuellen `/workspaces/MAIN`-Betrieb zugeschnitten; Umzüge in andere Checkout-Pfade sind nicht abgesichert.

**Gesamtstatus:** **BEFUND — die Zieldateien sind vollständig geprüft, aber für eine harte Sicherheits- oder Compliance-Freigabe nicht ausreichend abgesichert.**

## 2. Dateiinventar

| Pfad | Logische Zeilen | Zweck | Befund | Geprüft |
|---|---:|---|---|---|
| `/workspaces/MAIN/.opencode/agent/glm2api.md` | 28 | Agentendefinition für autonome Software- und Benchmark-Arbeit über den lokalen glm2api-Proxy; enthält Tool-, Pfad-, MCP- und Phasenregeln | Mehrere Grenz- und Bedienrisiken; gute teilweise Übereinstimmung mit dem AuditMesh-Benchmark, aber nicht selbstständig sicher | **ja** |
| `/workspaces/MAIN/.opencode/command/quota.md` | 4 | Slash-Command zur Ausführung des Quota-Skripts und zur anschließenden Markdown-Ausgabe | Ausführungsweg existent, aber Host/Modell/Berechtigungen nicht festgelegt; Ausgabe- und Fehlerbehandlung sind nicht deterministisch | **ja** |

`glm2api.md` besitzt 28 logische Zeilen, aber nur 27 Zeilenumbruche; die letzte Zeile hat keinen abschließenden Zeilenumbruch. Das ist funktional harmlos, aber ein konkreter Text-Hygiene-Befund. `quota.md` hat 4 logische Zeilen.

## 3. Zeilenweise Prüfung: `.opencode/agent/glm2api.md`

| Zeile | Zweck/Inhalt | Befund |
|---:|---|---|
| 1 | Öffnender YAML-Frontmatter-Block | Struktur ist plausibel; die Wirksamkeit der nachfolgenden Regeln hängt von der Opencode-Runtime und dem konkreten Request ab. |
| 2 | Beschreibung: Arbeits-Agent über chatglm.cn und Port 8001 | Port und Proxy-Zuordnung stimmen mit `.opencode/opencode.json:83-107` überein. Der Text erwähnt nicht, dass die Tool- und Phasensregeln im Wesentlichen für den AuditMesh-Benchmark gelten. |
| 3 | `mode: all` | Gültiger Opencode-Modus. Er erlaubt sowohl primäre als auch Subagent-Verwendung; dadurch ist der Geltungsbereich breiter als die Beschreibung „Arbeits-Agent“ vermuten lässt. |
| 4 | `model: glm2api/glm-5.3` | Modell-ID ist in der Provider-Konfiguration und im Benchmark vorhanden. Die Verfügbarkeit hängt jedoch vollständig vom lokalen Proxy ab; ein Health-Check oder Fallback ist im Agenten nicht definiert. |
| 5 | Beginn der per-Agent-Permission | Nur die beiden folgenden MCP-Tools werden explizit verweigert. Für `bash`, `read`, `write`, `edit`, `webfetch`, Netzwerk und externe Pfade wird keine zusätzliche Einschränkung gesetzt. |
| 6 | `opencode-sessions_delete_sessions: deny` | Aktuelle direkte Tool-Bezeichnung passt zum lokalen MCP und ist sinnvoll als erste Schranke. Die Regel ist keine MCP-Server-Autorisierung und verhindert weder Shell-Indirektion noch Aufrufe anderer Agents. |
| 7 | `opencode-sessions_delete_preview: deny` | Verhindert den aktuellen direkten Preview-Aufruf. Es wird jedoch kein zukünftiges `delete_*`-Tool automatisch abgedeckt; die Body-Regel mit Wildcard ist wiederum nur Prompttext. |
| 8 | Schließender Frontmatter-Block | Kein eigener Befund. |
| 9 | Autonomer Software-Ingenieur mit Shell-, Datei- und Testwerkzeugen | Hohe Autonomie ohne sichtbare Benutzerbestätigung, Workspace-Root-Grenze sowie ohne eine Regel zum Umgang mit nicht vertrauenswürdigen Eingaben. Das ist im Benchmark durch den separaten Auftrag begrenzt, nicht durch diese Datei allein. |
| 10 | Leerzeile | Kein semantischer Befund. |
| 11 | Überschrift der Tool-Disziplin | Gute sichtbare Struktur; Regeln werden hier nur als Prompt festgelegt. |
| 12 | Leerzeile | Kein semantischer Befund. |
| 13 | Beispiele für verfügbare Tools | Die Liste deckt die im Benchmark erwarteten Kern-Tools weitgehend ab. `etc.` macht die behauptete Grenze jedoch nicht exhaustiv; `skill`, `websearch` und weitere MCP-Lesewerkzeuge werden nicht ausdrücklich ausgeschlossen. |
| 14 | Verbot von Session-Löschtools und nicht vorhandenen Sandbox-Tools | Gute Übereinstimmung mit `benchmark.md:86-90` und dem Proxy-Protokoll. Keine erzwingte Sandbox- oder Tool-Allowlist auf Host-/Shell-Ebene; `skill` fehlt im expliziten Verbot. |
| 15 | Codeausführung und Tests ausschließlich über `bash`; Python wird als Bash-Beispiel genannt | Passt zum Benchmark und zum Translator. Die Formulierung „kein Python-Interpreter als Tool“ ist neben den Python-Beispielen missverständlich: Python ist über `bash` ausdrücklich erlaubt. |
| 16 | Absolute Pfade für `read`, `write`, `edit`; Beispiel außerhalb des Repos | Verhindert relative Pfadmissverständnisse, legt aber keine Root-Grenze fest. Das Beispiel `/workspaces/benchmark/...` zeigt ausdrücklich außerhalb von `/workspaces/MAIN`; dies ist im Benchmark beabsichtigt, im allgemeinen Agentenbetrieb ein Risiko. |
| 17 | Sequenzielle Calls, kein Pipeline-Betrieb, Ergebnis erst im nächsten Turn lesen | Stimmt mit `benchmark.md:53-54,112-127` überein und reduziert Pipeline-/Race-Fehler. Es ist eine Verhaltensanweisung, keine Host-Sperre; sie erhöht außerdem Turn- und Kostenaufwand. |
| 18 | Überschrift der spezifischen Tool-Rollen | Organisatorisch sinnvoll. |
| 19 | `todowrite` für Phasenplan | Passt zur Benchmark-Phase 0. Ob das Tool im konkreten Subagenten deklariert ist, wird nicht ausdrücklich als Optionalfall behandelt. |
| 20 | `glob` und `grep` direkt statt über Bash-Pipelines | Gute, benchmarkkonforme disziplinarische Anweisung. Sie ist promptbasiert; ein unabhängiger `bash`-Aufruf kann sie umgehen. |
| 21 | `task` nur mit `subagent_type: "explore"` und rein lesend | Absicht und Benchmark stimmen überein. Die tatsächliche Berechtigungsgrenze des gestarteten Subagenten wird hier nicht definiert oder erzwungen. |
| 22 | `webfetch` für HTTP, Beispiel lokaler Testserver | Im Benchmark auf `127.0.0.1` beschränkt; im Agenten selbst fehlt eine Host-Allowlist. Ein deklariertes `webfetch` könnte externe Ziele erreichen, sofern der Host dies zulässt. |
| 23 | `question` genau einmal am Laufende | Passt zu `benchmark.md:79,128-131,350-353`. Außerhalb des Benchmarks kann die Regel eine notwendige Rückfrage blockieren oder ein nicht deklariertes Tool voraussetzen. |
| 24 | Keine Zwischentexte, sondern Tool-Calls | Passt zum Proxy-Protokoll `tool_protocol.py:103-113`. Der Nachteil ist fehlende laufende Diagnose- und Abbruchmöglichkeit; Fehler müssen über Tool-Ergebnisse verarbeitet werden. |
| 25 | Leerzeile | Kein semantischer Befund. |
| 26 | Überschrift der Arbeitsphasen | Verweist auf eine externe, nicht mitgelieferte Phasendefinition. |
| 27 | Leerzeile | Kein semantischer Befund. |
| 28 | Phase 0 bis Phase 10 | Der Querverweis ist im `benchmark.md:92-131` tatsächlich aufgelöst. Ohne den AuditMesh-Agentenauftrag bleibt die Phase 0–10 jedoch unbestimmt; die Datei ist als primärer Agent nicht selbstständig operational. |

## 4. Zeilenweise Prüfung: `.opencode/command/quota.md`

| Zeile | Zweck/Inhalt | Befund |
|---:|---|---|
| 1 | Öffnender Frontmatter-Block | Struktur ist plausibel. |
| 2 | Beschreibung der aktuellen Antigravity-Kontingente mit 5h- und Claude-Limit | Die Beschreibung ist unvollständig: Die lokale Betriebsdokumentation beschreibt zwei Modellpools mit jeweils 5h- und Wochenlimit (`infrastructure.md:135-149`). Wochenlimit, Gemini-Pool und die Fallback-Datenquelle werden hier nicht genannt. |
| 3 | Schließender Frontmatter-Block | Kein eigener Befund. |
| 4 | Anweisung zur Ausführung von `/workspaces/MAIN/infra/scripts/quota.sh` und zur Markdown-Tabelle mit Balken, Prozent und Reset | Zielskript und Querverweise existieren. Der Prompt legt weder Agent, Modell, Permission noch explizit das auszuführende Bash-Tool fest. Die Markdown-Tabelle ist eine Modellnachtransformation der Textausgabe, nicht eine geprüfte Skriptausgabe; Fallback, Zeitpunkt, Exit-Code und Rohfehler werden nicht verlangt. Der absolute Pfad ist nicht portabel. |

## 5. Querverweise und Grenzprüfung

| Referenz | Ergebnis | Bedeutung |
|---|---|---|
| `.opencode/agent/glm2api.md:4` → `.opencode/opencode.json:83-107` | **PASS** | `glm2api/glm-5.3`, Loopback-Basis-URL und Provider sind vorhanden. |
| `.opencode/agent/glm2api.md:5-7` → `infra/mcp/opencode-sessions-mcp.js:424-495,498-527` | **TEILWEISE** | Die beiden aktuellen Löschwerkzeuge werden passend benannt. Der MCP-Server selbst besitzt keine eigene Authentifizierung; die Schranke ist der lokale stdio-Host plus Agent-Permission. |
| `.opencode/agent/glm2api.md:13-14` → `llm-proxies/glm2api/benchmarks/benchmark.md:64-90` | **TEILWEISE** | Kernliste und Löschverbot passen. `etc.`, optionale Toolfälle und das fehlende `skill`-Verbot schwächen die behauptete Exhaustivität. |
| `.opencode/agent/glm2api.md:17,19-24,28` → `benchmark.md:92-131` | **PASS im Benchmark-Kontext** | Sequenz, Toolrollen und Phase 0–10 sind dort definiert. Ohne diesen Auftrag kein gültiger Phasenvertrag. |
| `.opencode/agent/glm2api.md:14,15` → `llm-proxies/glm2api/src/glm2api/utils/tool_protocol.py:90-113` und `services/translator.py:414-452,475-484` | **PASS mit Grenze** | Proxy-Anweisungen verlangen Tool-only und bilden bestimmte native Sandbox-Calls auf Bash ab oder verwerfen sie. Das ist keine allgemeine Host-Berechtigungsgrenze. |
| `.opencode/command/quota.md:4` → `infra/scripts/quota.sh:1-161` | **PASS** | Datei vorhanden; `bash -n` war erfolgreich. |
| `.opencode/command/quota.md:4` → `infra/scripts/aliases.sh:9` und `.devcontainer/setup.sh:53-54` | **PASS im aktuellen Layout, nicht portabel** | Alias und Setup verweisen auf denselben absoluten Pfad. Ein anderer Checkout wird nicht aufgelöst. |
| `infra/scripts/quota.sh:135` → `infra/mcp/opencode-sessions-mcp.js:29-38` | **TEILWEISE** | Standard-DB-Pfad passt; `quota.sh` beachtet die im MCP unterstützte `OPENCODE_DB`-Override nicht. |
| `infra/scripts/quota.sh:5,12` → `infra/scripts/secrets.sh:99-101` und `.devcontainer/start-on-boot.sh:8-12` | **PASS für Ablage, nicht für Laufzeitvalidierung** | Der Credential-Pfad wird beim Unlock mit restriktiven Rechten wiederhergestellt. Das Skript selbst prüft Dateityp, Eigentümer, Symlink und Inhalt nicht. |
| `infra/scripts/quota.sh:15-35` → `infrastructure.md:147-149,379-386` | **PASS für Architektur, BEFUND für Transparenz** | Primärendpunkt und Fallback sind dokumentiert. Das Command weist dem Nutzer nicht aus, welcher Endpunkt und welcher Datenstand verwendet wurden. |

## 6. Tool- und MCP-Grenzmatrix

| Vorgang | Mechanismus | Tatsächliche Grenze | Befund |
|---|---|---|---|
| Session-Löschung aus dem glm2api-Agenten | Per-Agent-Deny plus Body-Verbot | Nur direkte aktuelle MCP-Toolnamen; kein Server- oder Shellverbot | Andere Agents, zukünftige MCP-Tools und `bash`-Indirektion bleiben möglich |
| Session-Lesen | `opencode-sessions_list_sessions`, `session_info`, `search_sessions`, `db_stats` im MCP | Agent blockiert nur zwei Löschtools; Session-Lesewerkzeuge bleiben grundsätzlich verfügbar | Hohe Vertraulichkeitsgrenze: Session-Metadaten, Verzeichnisse, Kosten und Share-URLs können gelesen werden; Message-Inhalte bleiben über nicht blockierte Shell-/DB-Zugriffe erreichbar |
| MCP-Transport | lokaler stdio-Prozess aus `.opencode/opencode.json:286-295` | Keine eigene MCP-Authentifizierung; Vertrauen in den Opencode-Host | Ein Prompt- oder Modellfehler ist keine serverseitige Zugriffskontrolle |
| Quota-Ausführung | Slash-Command → `bash` → absolutes Shellskript | Globale `permission: allow`; direkter Shell- und Dateisystemzugriff | Das Quota-Command nutzt das MCP nicht und fällt damit vollständig unter die Bash-/Host-Policy |
| Lokale Verbrauchsstatistik | `quota.sh:135-156` öffnet die Opencode-DB direkt | Kein MCP, keine Nur-Lese-URI, keine Session-/Zeitfilter | Datenschutz- und Performance-Risiko durch Vollscan der Message-Tabelle |

## 7. Befunde

### O-01 — Hoch: Agentenregeln sind keine ausreichende Sicherheitsgrenze

`glm2api.md:5-7` verweigert nur zwei MCP-Tools. Die globale Konfiguration setzt dagegen `.opencode/opencode.json:284` auf `permission: "allow"`. `read`, `write`, `edit`, `bash`, `webfetch` und nicht blockierte MCP-Lesewerkzeuge bleiben damit für den Agenten erreichbar. Über `bash` können Löschungen, SQLite-Zugriffe, Netzwerkabfragen und Dateiänderungen auch dann ausgeführt werden, wenn das direkte Löschtool nicht verfügbar ist.

**Auswirkung:** Ein fehlerhaftes Modell, eine Prompt-Injection in einer gelesenen Datei oder ein unvorsichtiger Auftrag kann die Agenten-Promptregel umgehen. Die zwei Deny-Regeln schützen nicht andere Agents oder direkte Shell-Aufrufe.

### O-02 — Hoch: Autonomie ohne Root- oder Vertrauensgrenze

`glm2api.md:9` beschreibt einen autonomen Software-Ingenieur, `glm2api.md:16` verlangt absolute Pfade, aber keine Beschränkung auf ein Arbeitsverzeichnis. Das Beispiel außerhalb von `/workspaces/MAIN` ist im Benchmark beabsichtigt, wird aber nicht als Benchmark-only markiert. Der eigentliche Benchmark begrenzt die Arbeit separat auf seinen Laufpfad (`benchmark.md:44-48`).

**Auswirkung:** In einer allgemeinen Verwendung kann der Agent außerhalb des beabsichtigten Repositories lesen oder schreiben. Es fehlen außerdem eine explizite Regel zum Umgang mit nicht vertrauenswürdigen Eingaben und eine Bestätigungsstufe für destruktive oder geheimnisbezogene Aktionen.

### O-03 — Hoch: Session-Vertraulichkeit bleibt über MCP-Lesewerkzeuge offen

Die Agentendatei nennt in `glm2api.md:13` nur `opencode-sessions_db_stats`, verbietet aber nicht die übrigen Session-Lesewerkzeuge. Der registrierte MCP-Server stellt `list_sessions`, `session_info` und `search_sessions` zusätzlich zu `db_stats` bereit (`infra/mcp/opencode-sessions-mcp.js:424-495`). Der MCP selbst hat keine eigene Autorisierung; die Grenze ist der lokale Prozessstart.

**Auswirkung:** Der Agent kann Session-Metadaten, Verzeichnisnamen, Kosten, Tokenwerte oder Share-URLs über die MCP-Lesewerkzeuge erreichen; über nicht blockierte Shell-/DB-Zugriffe können zusätzlich Message-Inhalte verarbeitet werden. Das ist unabhängig davon, ob die beiden Löschtools blockiert sind.

### O-04 — Mittel: Toolvertrag ist nicht exhaustiv und teils widersprüchlich

`glm2api.md:13` sagt „nur deklarierte Tools“, nennt aber mit `etc.` eine offene Liste. `glm2api.md:14` verbietet `execute_sandbox_code` und Session-Löschtools, nicht aber `skill` oder `websearch`. Der Benchmark fordert dagegen ausdrücklich ein exhaustives Tool-Set und verbietet `skill` (`benchmark.md:81-90`).

**Auswirkung:** Bei einer erweiterten Tool-Deklaration kann der Agent ein im Benchmark verbotetes oder unerwartetes Werkzeug verwenden. Die Proxy-Anweisungen reduzieren das Risiko, sind aber keine vollständige Host-Policy.

### O-05 — Mittel: Benchmark-Phasenvertrag ist nicht selbstständig

`glm2api.md:28` verweist auf Phasen 0 bis 10. Die Phasen existieren tatsächlich nur im separaten `benchmark.md:92-131` und setzen den dortigen Arbeitsauftrag voraus. `mode: all` macht den Agenten auch für direkte primäre Aufrufe verfügbar.

**Auswirkung:** Ein direkter Aufruf ohne Benchmark-Prompt kann an einer undefinierten Phasendefinition hängen bleiben oder die in `glm2api.md:17,23` erzwungenen Workflow-Enden unpassend anwenden. Das ist kein Syntaxfehler, aber ein Betriebs- und Prompthärtungsproblem.

### O-06 — Hoch: Lokaler Proxy schützt keinen Agenten-Sandbox-Grenzbereich

Der Agent nutzt `glm2api/glm-5.3` über `http://127.0.0.1:8001/v1` (`.opencode/opencode.json:83-107`). Die operative Proxy-Vorlage begrenzt den Host auf Loopback, lässt die Server-Authentifizierung leer, erlaubt CORS `*` und aktiviert Raw-Debug-Dumps (`llm-proxies/glm2api.env:14,26-30,38,41-47`).

**Auswirkung:** Andere lokale Prozesse können den Proxy grundsätzlich erreichen; Debug-Logs können Prompts, Tool-Argumente, Header und Upstream-Daten enthalten. Die Agentendatei verlangt weder eine lokale Prozessgrenze noch eine Secret-/Output-Redaktion.

### O-07 — Mittel: Quota-Command ist nicht als deterministischer Runner definiert

`quota.md:1-4` legt weder `agent`, `model`, `permission` noch ein Ausführungswerkzeug fest. Die Formulierung „Führe den Befehl aus“ ist eine Modellaufforderung; der Host muss daraus einen Bash-Aufruf ableiten. Das globale `allow` aus `opencode.json:284` erleichtert die Ausführung.

**Auswirkung:** Unter einem restriktiveren Agenten kann der Command scheitern; unter einem autonomen Agenten kann die Ausführung oder Formatierung variieren. Ein reproduzierbarer Slash-Command sollte Agent, Tool, Exit-Code, Ausgabeformat und Fehlerfall explizit festlegen.

### O-08 — Mittel: Absoluter Pfad und fehlende Portabilität

`quota.md:4`, `infra/scripts/aliases.sh:9` und `.devcontainer/setup.sh:53-54` verwenden `/workspaces/MAIN/infra/scripts/quota.sh`. Das funktioniert im aktuellen Layout, ist aber nicht relativ zum geladenen Workspace.

**Auswirkung:** Ein Checkout unter einem anderen Pfad, ein Bundle oder ein manueller Aufruf außerhalb des Codespace-Layouts trifft nicht den beabsichtigten Runner. Die Setup-Dokumentation behauptet an anderer Stelle eine Pfadanpassung; der Slash-Command selbst verwendet diese jedoch nicht.

### O-09 — Hoch: Quota-Fehler- und Tokenbehandlung kann sensible oder falsche Ausgabe erzeugen

`quota.sh:12,16-20` liest das Access-Token und übergibt es als curl-Argument. `quota.sh:31-34` gibt bei ungültiger Antwort die Rohantwort aus. Der Command verlangt keine Redaktion, Quellenkennzeichnung oder Fehlerbehandlung. Die Credential-Datei wird beim Unlock zwar mit restriktiven Rechten abgelegt (`secrets.sh:99-101`), das Laufzeitskript prüft diese Rechte jedoch nicht.

**Auswirkung:** Das Token kann während des curl-Aufrufs über lokale Prozessinformationen sichtbar sein. Eine unerwartete Google-Antwort kann interne Details oder Credential-nahe Daten in die Modellantwort gelangen. Die Rohantwort sollte niemals ungefiltert an den Nutzer weitergereicht werden.

### O-10 — Hoch: Quota-Verfügbarkeit und Ressourcenverbrauch sind nicht begrenzt

In `quota.sh:16-28` fehlen beim curl-Aufruf ein Request-Timeout, eine maximale Antwortgröße, Retry-/Rate-Kontrolle und eine belastbare HTTP-Statusprüfung. `|| true` verschluckt Netzwerkfehler; die gesamte Antwort wird in einer Shell-Variable gehalten. Die nachfolgende Python-Ausgabe kann bei hängendem Netzwerk oder sehr großer Antwort blockieren.

**Auswirkung:** Ein Netzwerkproblem kann den Agent-Turn lange blockieren; ein fehlerhafter oder kompromittierter Antwortkanal kann Speicher- und CPU-Ressourcen belegen. Das Command meldet keinen Timeout- oder Abbruchstatus.

### O-11 — Hoch: Quota-Parsing ist fehlertolerant gegenüber falschen, nicht standardisierten Daten

`quota.sh:81-106` prüft nur auf ein vorhandenes Feld `groups`, nicht auf ein vollständiges Schema. Fehlende Buckets werden als `—` dargestellt, fehlende `remainingFraction` als 100 %. Unbekannte Gruppen werden pauschal als „Claude“ klassifiziert. Prozentwerte werden nicht auf 0–100 begrenzt; nur die Balkenlänge wird geklemmt.

Im Fallbackpfad `quota.sh:107-130` wird anhand des Reset-Strings geraten, ob ein Wert in die 5h- oder Wochen-Spalte gehört. Die Modellnamen sind hart codiert und nicht vollständig an `.opencode/opencode.json:117-167` gekoppelt. Fehlt ein passender Modelldatensatz, wird keine Zeile und keine verlässliche „unbekannt“-Kennzeichnung ausgegeben.

**Auswirkung:** Die angeforderte Kapazitätseinschätzung kann falsch sein, insbesondere bei neueren Modellnamen, unvollständigen Gruppen oder atypischen Reset-Zeiten. Das Command weist nicht darauf hin, ob Primär- oder Fallbackdaten verwendet wurden.

### O-12 — Mittel: Lokale Verbrauchsanzeige liest und verarbeitet die gesamte Message-Tabelle

`quota.sh:135-156` öffnet die Opencode-DB an einem festen Standardpfad, führt `SELECT data FROM message` aus und lädt alle Datensätze mit `fetchall()`. Jeder JSON-Blob wird geparst, obwohl am Ende nur Token-Summen ausgegeben werden. Es gibt keinen Read-only-Modus, keinen Session- oder Zeitfilter, keine Grenze für die Datenmenge und keine Berücksichtigung von `OPENCODE_DB`.

**Auswirkung:** Speicher-, CPU- und Datenbank-Lock-Risiko; außerdem können vertrauliche Message-Inhalte im Prozessspeicher verarbeitet werden. Die Zählung umfasst Input plus Output, aber nicht zwingend alle relevanten Verbrauchsarten, und ein JSON-Fehler lässt die lokale Zeile still ausfallen. Ein externer Session-DB-Pfad wird nicht berücksichtigt.

### O-13 — Niedrig: Quota-Ausgabe ist nicht direkt eine Markdown-Tabelle

`quota.sh:71-132` erzeugt eine formatierte Textausgabe mit Spalten, nicht die in `quota.md:4` geforderte Markdown-Tabelle. Das Command muss Werte, Unicode-Balken, Prozentwerte und Countdowns manuell in Markdown übertragen.

**Auswirkung:** Es besteht ein Modellfehler-Risiko bei Rundung, Zuordnung, fehlenden Werten und der Unterscheidung von 5h-Sprint und Wochenlimit. Ein maschinenlesbares JSON- oder eine echte Markdown-Ausgabe im Runner wäre deterministischer.

### O-14 — Niedrig: Dokumentations- und Textdrift

- `quota.md:2` beschreibt nicht die vollständige 2×2-Quota-Matrix aus `infrastructure.md:135-149`.
- `glm2api.md` endet ohne abschließenden Zeilenumbruch.
- `quota.md` ignoriert `$ARGUMENTS` und bietet daher keine erkennbare Parameter- oder Dry-Run-Schnittstelle.
- Die Formulierung in `glm2api.md:14-15` ist bezüglich „kein Python-Interpreter“ versus `python3` über `bash` nicht eindeutig.

## 8. Was bestätigt wurde

- Beide Zieldateien wurden vollständig und zeilenweise gelesen; die Zeilenzahlen und der fehlende abschließende Zeilenumbruch wurden geprüft.
- Der Agent-Dateiname, der Modellname, der Port und die zentralen Benchmark-Toolnamen sind im aktuellen Workspace aufgelöst.
- Die Sequenz-, reine Tool-Aufrufe und Phasenvorgaben des Agenten passen im AuditMesh-Benchmark zu den dortigen Regeln.
- Die beiden aktuellen Session-Löschtools werden im Agenten sowohl per Prompt als auch per Per-Agent-Permission adressiert.
- Das Quota-Skript existiert, seine Shell-Syntax ist gültig, und Alias/Setup verweisen im aktuellen Layout auf denselben Pfad.
- Primärer Quota-Endpunkt und Fallback sind in der lokalen Betriebsdokumentation beschrieben.
- Die Zieldateien enthalten keine Geheimniswerte. Nur Namen, Pfade, Zeilennummern und Risikoklassen werden in diesem Bericht verwendet.

## 9. Empfohlene Maßnahmen — nicht ausgeführt

1. Für den glm2api-Agenten eine echte Root-Allowlist, restriktive `bash`-/Datei-Permissions und eine serverseitige oder zumindest hostseitige Löschsperre definieren; Prompt-Regeln allein nicht als Sicherheitsgrenze behandeln.
2. MCP-Lesewerkzeuge auf einen expliziten Minimalumfang begrenzen und `skill`, `websearch`, externe `webfetch`-Ziele sowie Shell-Indirektion ausdrücklich sperren oder als bewusstes Risiko dokumentieren.
3. Den Agenten entweder auf den Benchmark-Auftrag festlegen oder die Phase-0–10-Regeln als selbstständige, konditionale Ausführungsspezifikation formulieren.
4. `quota.md` auf einen expliziten Agenten, ein explizites Ausführungswerkzeug, eine sichere Ausgabequelle, Fehler-/Fallback-Kennzeichnung und ein maschinenlesbares Format festlegen.
5. In `quota.sh` Request-Timeout, maximale Antwortgröße, HTTP-Fehlerbehandlung, Schema-/Wertvalidierung und eine redaktionssichere Fehlerausgabe ergänzen.
6. Lokale Verbrauchsstatistik nur lesend und begrenzt ausführen, `OPENCODE_DB` respektieren, Message-Inhalte nicht vollständig laden und Zählzeitraum/Modellgrenzen dokumentieren.
7. Absolutpfade durch einen stabilen Runner-/Repo-Root-Verweis ersetzen oder den Checkout-Pfad als bewusste Betriebsannahme dokumentieren.
8. Nach einer Freigabe die betroffenen lokalen Proxy-/Provider-Credentials separat rotieren; in diesem Audit wurden keine Werte ausgegeben und keine Credentials geändert.

## 10. Abschluss und Änderungsnachweis

- **Dateiprüfung:** `/workspaces/MAIN/.opencode/agent/glm2api.md` vollständig geprüft, **geprüft: ja**.
- **Dateiprüfung:** `/workspaces/MAIN/.opencode/command/quota.md` vollständig geprüft, **geprüft: ja**.
- **Unterstützende Dateien:** relevante Abschnitte in `.opencode/opencode.json`, `infra/scripts/quota.sh`, `infra/mcp/opencode-sessions-mcp.js`, `infra/mcp/README.md`, `infrastructure.md`, `infra/scripts/aliases.sh`, `.devcontainer/setup.sh`, `infra/scripts/secrets.sh`, `llm-proxies/glm2api/benchmarks/benchmark.md` sowie den Tool-Protokoll-/Translator-Dateien geprüft.
- **Ausführung:** Nur lokale Shell-Syntaxprüfung und Git-Status; kein Dienststart, keine Netzwerkanfrage, keine Runtime-Credentials verwendet, keine Löschung.
- **Änderungen:** Ausschließlich diese Auditspur unter `.runtime/revision-parts/O.md` wurde erstellt. Keine Quelldatei wurde geändert.
- **`Revision.md`:** von diesem Auftrag nicht geschrieben. Während der Analyse wurden externe Autosave-/Paralleländerungen beobachtet; diese sind kein Schritt dieses Berichts.
- **Geheimnisse:** keine Geheimniswerte ausgegeben.
<!-- END PART O -->

## Anhang P — Config-Secret-Artefakte (redigiert)

<!-- BEGIN PART P -->
## Redigierter Report — `config/`

**Beobachtungszeitpunkt:** 24.09.2026, lokale Workspace-Zeit (`+0200`)
**Scope:** ausschließlich `/workspaces/MAIN/config/`; Querverweise nur innerhalb von `/workspaces/MAIN`.
**Zweck:** Existenz, Metadaten, Hash-/Strukturinformationen, Schutzstatus, Risiken und beobachtete Referenzen.

## Kurzurteil

- `config/` enthält genau drei reguläre Dateien und keine Unterverzeichnisse oder Symlinks.
- Alle drei Dateien sind Git-tracked; `config/` selbst ist nicht ignoriert.
- `config/passphrase` ist ein bewusst im Klartext gehaltenes Repository-Artefakt. Damit schützt die Verschlüsselung von `secrets.enc` nicht gegen jeden Repository-Leser.
- `secrets.enc` ist strukturell ein OpenSSL-`enc`-Chiffretext mit Salt-Header. Das Skript verwendet AES-256-CBC mit PBKDF2, aber keine authentifizierte Verschlüsselung.
- Verzeichnis und Dateien sind lokal zu weit offen: Verzeichnis `0777`, Dateien `0666`.
- Das Git-Bundle-Backup enthält wegen der Tracker-Pfade `config/passphrase` im Klartext sowie `secrets.enc` und die Historie. Die Verschlüsselung des Einzelbundles schützt die Backup-Kopie nicht.
- Manifest und Bundle werden nicht kryptografisch aneinander gebunden; Bundle-/Manifest-Schreibvorgänge sind nicht atomar.
- **Gesamtbewertung:** sehr hohes Vertraulichkeits- und Integritätsrisiko, hohes Risiko für unvollständige Wiederherstellung. Die Automatik ist beabsichtigt, aber kein wirksames Schutzmodell gegen ein öffentlich lesbares Repository.

## Datenschutz- und Prüfgrenzen

- `config/passphrase` wurde nicht als verwertbarer Secret-Inhalt interpretiert, ausgegeben oder in zeichenweise Details zerlegt.
- `config/secrets.enc` wurde nicht entschlüsselt; nur Dateimetadaten, kryptografischer Fingerabdruck und nicht-reproduzierende Strukturmerkmale wurden bestimmt.
- `config/secrets.manifest` wurde vollständig und zeilenweise gelesen; wiedergegeben werden nur Archivmitgliednamen, keine Werte.
- Es wurde kein `lock`, `unlock`, Setup-, Restore- oder Startskript ausgeführt. Es gab keine Netzwerkaktion und keinen Entschlüsselungsversuch.

## Vollständiges Dateiinventar

### `config/`

- Verzeichnis: vorhanden, 4.096 B, `0777`, Eigentümer `vscode:root`, genau drei Dateien, keine Unterverzeichnisse/Symlinks.
- Default-POSIX-ACL vorhanden; konkrete Dateien haben Unix-Modus `0666`; keine Immutable-/Append-Attribute.

### `config/passphrase`

- Reguläre UTF-8-validierbare Text-/Bytefolge, 40 B, `0666`, tracked (`100644`), nicht ignoriert.
- 0 LF-Bytes und kein abschließender Zeilenumbruch; Inhalt nicht wiedergegeben.
- SHA-/Passphrasenfingerabdruck und mögliche Offline-Angriffsfläche wurden im Teilreport bewusst zurückhaltend behandelt und werden hier nicht wiederholt.
- Lesen/Ändern/Löschen sind für andere lokale Benutzer nicht zuverlässig blockiert.
- `infra/scripts/secrets.sh:26-37` liest die Datei in eine Passphrase-Umgebungsvariable und exportiert sie.

### `config/secrets.enc`

- Regulärer binärer OpenSSL-Chiffretext, 4.000 B, `0666`, tracked (`100644`), nicht ignoriert.
- `Salted__`-Header bestätigt; 16 Headerbytes + 3.984 Chiffretextbytes, 16-Byte-ausgerichtet.
- Keine Entschlüsselung; Klartextinhalt unbekannt; kein Secretwert ausgegeben.
- `secrets.sh:55-57` erzeugt gzip-komprimiertes TAR und anschließend `openssl enc -aes-256-cbc -pbkdf2`; explizite KDF-Iteration/Version werden nicht im Manifest gebunden.

### `config/secrets.manifest`

- UTF-8-Textdatei, 138 B, 9 logische Zeilen, `0666`, tracked (`100644`), nicht ignoriert.
- Vollständige Archivpfadzeilen ohne Werte:

```text
1: ./
2: ./antigravity-oauth_creds.json
3: ./chatglm-refresh-token
4: ./env
5: ./nvidia-nim-key
6: ./opencode-auth.json
7: ./pat
8: ./rclone.conf
9: ./xinjianya-key
```

- Das Manifest listet acht mögliche Secret-Zieldateinamen; es ist damit selbst ein sensibles Informationsinventar.
- Manifest und Bundle werden nacheinander direkt geschrieben; keine atomare Kopplung, kein Bundle-Hash im Manifest.

## Kryptografische und lokale Risiken

1. **Klartext-Passphrase im selben Repository (kritisch):** Ein Repository-/Bundle-Leser kann Passphrase und Chiffretext gemeinsam verwenden.
2. **Weltweit beschreibbare Dateien (hoch):** `0666` erlaubt lokale Manipulation; bei CBC ohne MAC ist Bitänderung nicht zuverlässig erkennbar.
3. **Keine authentifizierte Verschlüsselung (hoch):** CBC-Schutz gegen Vertraulichkeit ist kein Integritäts-/Authentizitätsschutz.
4. **Nicht-atomare Bundle-/Manifest-Paare (hoch):** Abbruch kann Chiffretext und Manifest verschiedener Generationen hinterlassen.
5. **TAR-Extraktion ohne Allowlist (hoch):** `tar -xzf` in `secrets.sh:71-76` prüft keine Pfad-, Symlink- oder Metadatenregeln.
6. **Implizite KDF-/Formatparameter (mittel):** OpenSSL-Standardwerte und Script-Version bestimmen Lesbarkeit/Schutz, ohne versioniertes Formatfeld.
7. **Prozesskontext (mittel bis hoch):** Passphrase wird exportiert; PAT-Restoration nutzt in `secrets.sh:80` ein Kommandozeilenargument.

## Backup- und Restore-Risiken

- `git bundle create --all` in `gdrive-backup.sh:63-69` enthält wegen tracked `config/` Passphrase, Chiffretext, Manifest und historische Versionen.
- Temporäres `.runtime/MAIN.bundle` kann bei Abbruch liegenbleiben; kein restriktiver Modus.
- Rotation kann alte Backup-Generation löschen, bevor ein Move/Upload sicher bestätigt ist; kein Lock.
- `save.sh:53-57` maskiert Backup-Fehler; Remote-MD5 akzeptiert fehlenden Hash nicht als Fehler.
- Restore führt direkt `git clone` ohne vorgeschalteten `git bundle verify` aus.
- `RESTORE.md` ist im Upload best effort; die Aussage „immer vorhanden“ ist nicht garantiert.

## Querverweise und Empfehlungen

- `secrets.sh:23-24,26-37,39-61,64-121`, `.devcontainer/setup.sh:56-61`, `.devcontainer/start-on-boot.sh:8-12` und `infrastructure.md:51-67` bestätigen den Passphrase-/Bundle-Lebenszyklus.
- `README.md` verschweigt den Klartext-Passphrase-Pfad; `aliases.sh` nennt nicht alle Manifestmitglieder.
- Vorrangig: Schlüsselmodell trennen/rotieren, `config/` und Dateien restriktiv schützen, AEAD und explizite KDF-Version verwenden, Generation atomar publizieren, Archiv-Allowlist erzwingen, Bundle/Restore mit Lock/Verify/Hash absichern und PAT nicht als argv übergeben.
- Vollständiger redigierter Report: `/workspaces/MAIN/.runtime/revision-parts/P.md`.
<!-- END PART P -->

## Anhang Q — Getracktes glm2api-Bundle-ZIP

<!-- BEGIN PART Q -->
## Partition Q — ZIP-Inventar `llm-proxies/dist/glm2api-bundle.zip`

## Prüfrahmen und Schutzgrenze

- Snapshot: `2026-09-24T01:29:57.782968+02:00`; Arbeitsgrenze ausschließlich `/workspaces/MAIN`.
- Eingabe: das getrackte ZIP wurde direkt aus seinem Dateisystempfad gelesen; keine Datei wurde aus dem ZIP auf die Platte entpackt.
- Keine Builds, keine Start-/Installationsskripte, keine Prozessprüfungen und keine Änderungen an `Revision.md` wurden ausgeführt.
- ZIP-Datei: `/workspaces/MAIN/llm-proxies/dist/glm2api-bundle.zip`; Größe `119601` B; Hostmodus `0666`; SHA-256 `e5b08e473f77377853eb743821f42c4a02caedecff677413b5c6f2c6e4a4527a`.
- Externe Autosave-/Parallelprozesse wurden während der Analyse beobachtet und als solche markiert; sie waren kein Schritt dieses Berichts.
- Secretwerte, Tokens, Cookies, Passphrasen und verschlüsselte Werte wurden nicht ausgegeben. `app/glm2api.env` wurde weder geöffnet noch dekomprimiert.
- `CRC32` ist der ZIP-Headerwert. `H-Inhalt` ist SHA-256 über den dekomprimierten Inhalt und wurde nur für nicht-geschützte Dateien berechnet. `H-Roh` ist SHA-256 über die gespeicherten Memberbytes; diese Definition gilt auch für den geschützten Eintrag.
- Alle ZIP-Inhalte wurden nur im Arbeitsspeicher gelesen. Es wurde kein `unzip -p`, kein Staging-Verzeichnis und kein Build erzeugt.

## Kurzfazit

- **Struktur:** 45 ZIP-Einträge = 36 Dateien + 9 Verzeichnisse; 451.719 B unkomprimiert, 112.749 B komprimiert; keine Duplikate, keine gefährlichen Pfade, keine fehlenden/unerwarteten Dateien gegenüber dem Build-Soll.
- **Integrität:** 35/36 nicht-geschützte Dateiinhalte per Dekompression/CRC32 geprüft, 0 Fehler; `app/glm2api.env` wurde wegen Secret-Schutzgrenze nicht per CRC/Plaintext verifiziert.
- **Kanonischer Vergleich:** 29 Dateien byte-identisch, 6 Dateien mit Drift, 1 geschützte Konfigurationsdatei metadata-only.
- **Manifest:** kein Manifest-Eintrag, kein ZIP-Kommentar, kein Central-Extra-Field und kein Texttreffer `manifest` in den 35 lesbaren Membern.
- **Gesamtstatus:** ZIP technisch lesbar und strukturell konsistent, aber **nicht build-verifiziert**, weil sechs enthaltene Source-/Testdateien vom aktuellen kanonischen Source abweichen.

## ZIP-/Container-Metadaten

| Feld | Ergebnis |
|---|---|
| EOCD | Offset `119579`, Signatur `PK\x05\x06`, Gesamtcomment `0` B, trailing bytes `0` |
| Central Directory | Offset `115804`, Größe `3775` B, Einträge `45` |
| Methoden | Deflate(8): `33`; Stored(0): `12` |
| Flags | `0x0000: 45`; verschlüsselt: `0`; Data Descriptor: `0` |
| ZIP64 | kein ZIP64-Extra-Feld; EOCD-16-bit-Felder ausreichend |
| Central-Extra-/Comment-Summen | Extra `0` B; Comments `0` B |
| Lokal-/Zentralheader | Alle 45 geprüft; inkonsistente Einträge: `0` |
| Pfad-Sicherheit | absolute Pfade: `0`; Backslash: `0`; `..`-Komponenten: `0`; NUL/Steuerzeichen: `0`; problematische Pfade gesamt: `0` |
| ZIP-Modi | 0666: `34`; 0777: `6`; 0755: `5` |
| ZIP-Dateitypen | regular: `36`; directory: `9`; Sonstige: `0` |
| ZIP-Zeit | Alle Einträge `1980-01-01 00:00:00` (deterministischer Epoch-0-Marker). |
| Build-Soll | erwartete Dateien `36`, tatsächlich `36`, fehlend `0`, unerwartet `0`. |

## Vollständiges ZIP-Eintrag-Inventar

`Bereich` ist lokaler Headeroffset, Datenstart und Datenende im ZIP. `H-Inhalt` und `H-Raw` haben die oben definierte Bedeutung; `—` bei Verzeichnissen bzw. geschütztem Plaintext. Angezeigte ZIP-Modi sind Unix-Berechtigungsbits; `Typ` unterscheidet Regular vs. Directory.

| # | ZIP-Pfad | Typ | Modus | ZIP-Zeit | Methode/Flags | unkomprimiert B | komprimiert B | CRC32 | H-Inhalt | H-Roh | Bereich | Prüfstatus |
|---:|---|---|---|---|---|---:|---:|---|---|---|---|---|
| 1 | `glm2api-bundle/` | DIR | `0777` | 1980-01-01 00:00:00 | Stored/`0x0000` | 0 | 0 | `0x00000000` | `—` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `0;45-45` | Struktur OK |
| 2 | `glm2api-bundle/README.md` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 3051 | 1590 | `0xe25a6c6d` | `c5c31cd1d1a4f7694a0f0ae6e8423d98116a4d8fb0299593f838e94eeaaf42a5` | `8495021e5b112475d787c1eb2aa660b3e7144337c12e1b1e85e43da4f2334308` | `45;99-1689` | CRC OK; IDENTISCH |
| 3 | `glm2api-bundle/app/` | DIR | `0777` | 1980-01-01 00:00:00 | Stored/`0x0000` | 0 | 0 | `0x00000000` | `—` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `1689;1738-1738` | Struktur OK |
| 4 | `glm2api-bundle/app/.env.example` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 5618 | 2553 | `0xc726def0` | `0fb3f717fcbf9521b705400f7b06e888bd32b91f03313ae51326b512b77d014b` | `1a7b6c9bce2378f9722e88cf5ed72fe18b0d67f7460fdc6a6bb9063dcf0b61bb` | `1738;1799-4352` | CRC OK; IDENTISCH |
| 5 | `glm2api-bundle/app/structure.md` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 6001 | 2776 | `0xc96bea2c` | `bde83790ad68497cbc954be861bf92195d585229d948205e73a7b6ddac279c2b` | `6413c3bbebde925e0a921f63b50d19765046a4c17ccb50b0e8c42d937d8c74d5` | `4352;4413-7189` | CRC OK; IDENTISCH |
| 6 | `glm2api-bundle/app/.python-version` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Stored/`0x0000` | 5 | 5 | `0x1e187808` | `a876e0b10411037a012498b9fe18d9bc1df32ed8b722a13564dc944ddcfd9135` | `a876e0b10411037a012498b9fe18d9bc1df32ed8b722a13564dc944ddcfd9135` | `7189;7253-7258` | CRC OK; IDENTISCH |
| 7 | `glm2api-bundle/app/tests/` | DIR | `0755` | 1980-01-01 00:00:00 | Stored/`0x0000` | 0 | 0 | `0x00000000` | `—` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `7258;7313-7313` | Struktur OK |
| 8 | `glm2api-bundle/app/tests/test_config.py` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 1205 | 393 | `0x5c4dd2e0` | `2eb9299a4bef64e32bd257aa7928e0cbe69ddcafe034d3f40a8a6209ee5a7f23` | `2ef2b01a5a9ad0523444cc192782fa080b641a7383077f9b94ef6d02abf94e05` | `7313;7382-7775` | CRC OK; IDENTISCH |
| 9 | `glm2api-bundle/app/tests/test_protocol_adapters.py` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 9192 | 2518 | `0xa7effd76` | `8c3d5d2be0e920eb90e174b368337b95ec26905b14bc9431c736d61f9887fe36` | `8da32b976e555c2208c10de65f3db5e78fc7a4f545ff1b6308f66d31582a44eb` | `7775;7855-10373` | CRC OK; IDENTISCH |
| 10 | `glm2api-bundle/app/tests/test_model_variants.py` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 2541 | 708 | `0x22a05f39` | `7907b1d5f24b26f345ef90c443f6f647dbf1497e88da460e83277eaff544d7ec` | `eff658031cec1285f7b7bbf435bf8a659af123955d98ff2d80885721ba8e74fb` | `10373;10450-11158` | CRC OK; IDENTISCH |
| 11 | `glm2api-bundle/app/tests/test_translator.py` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 40726 | 7381 | `0xc402359f` | `b2809d8514384701072e697ccadefaa8034794d6c226ea722f0036f1497d2067` | `b4d14863b415b21b0f74b8c9f05e207dd345f82e794b89f948df24c5f8b4289d` | `11158;11231-18612` | CRC OK; DRIFT; +89/−0; Hunks 1 |
| 12 | `glm2api-bundle/app/tests/test_stream_retry.py` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 13922 | 2862 | `0x9a74e470` | `88a8a047c211ecd974182212c5bd4797f68cf2f0ecef003357d596a5b60640a5` | `08298a157ad9719c38f48d092d33916d068f5e04c380d07bd2637cb4b55354aa` | `18612;18687-21549` | CRC OK; IDENTISCH |
| 13 | `glm2api-bundle/app/tests/test_tool_parser.py` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 22435 | 4651 | `0x4f7447e4` | `097156fe66460125db4e66c754abbdccf8213f97f1a0861f0368f2301d4b4db8` | `42fa035771e219e3cef4ac26914444ee6c3b497b161131ff5120c695db46a977` | `21549;21623-26274` | CRC OK; DRIFT; +53/−1; Hunks 2 |
| 14 | `glm2api-bundle/app/README.md` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 2140 | 1202 | `0xd910f362` | `32b4b4eabb98e2ff281e75ae3e77b50ae01ecadffc8357187cc3c8c6f38bf110` | `bb198452e3e6d8420c459891e06fa0484f520e06f9bce0df1f5df07fd55f5e8e` | `26274;26332-27534` | CRC OK; IDENTISCH |
| 15 | `glm2api-bundle/app/LICENSE` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 35145 | 12112 | `0xf772f0e1` | `6c7bdb574498786b458652674d3982a08788cfde895fad48b8fa780a0d9c2e5e` | `e79ef7905d23bd31386a9547dec9000c56461e94f0403d7b9775221f569bebf7` | `27534;27590-39702` | CRC OK; IDENTISCH |
| 16 | `glm2api-bundle/app/main.py` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 91 | 80 | `0x9e1d8b53` | `8cb2d225533883743db360e307e460aebde4e006598fdf02625e3c42e10a009a` | `acd33781d0ba51c4f3deb10dbb63e860a51a8df26caa237ac724fe27e79f5802` | `39702;39758-39838` | CRC OK; IDENTISCH |
| 17 | `glm2api-bundle/app/glm2api.env` | GESCHÜTZT | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 5829 | 2637 | `0x5db03652` | `unterdrückt` | `ade285a2a05a165f624d72b461b750c655ca42a38bb6112b72b1f2b1d9c8ffb0` | `39838;39898-42535` | GESCHÜTZT; CRC nicht geprüft; metadata-only |
| 18 | `glm2api-bundle/app/uv.lock` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 4645 | 1727 | `0x5cf30340` | `5bfccff4ed66457addfcdcc08a5906ee22638460a823a0debbe4dfda5f926391` | `8d8cda1874435606fb9c3a1c6d77d8e1d36725ae191840a8b3bd1ef0006a9edd` | `42535;42591-44318` | CRC OK; IDENTISCH |
| 19 | `glm2api-bundle/app/pyproject.toml` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 535 | 332 | `0xfffe465d` | `c2eddbc0dce8309776cb600329be8fc32980479a25b9ab8e8a4c4a3a7d788aaa` | `b7248a91cdd1539450bd9a56c51b275aab17354ba31e30a0a768bf4b6e679053` | `44318;44381-44713` | CRC OK; IDENTISCH |
| 20 | `glm2api-bundle/app/src/` | DIR | `0755` | 1980-01-01 00:00:00 | Stored/`0x0000` | 0 | 0 | `0x00000000` | `—` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `44713;44766-44766` | Struktur OK |
| 21 | `glm2api-bundle/app/src/glm2api/` | DIR | `0755` | 1980-01-01 00:00:00 | Stored/`0x0000` | 0 | 0 | `0x00000000` | `—` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `44766;44827-44827` | Struktur OK |
| 22 | `glm2api-bundle/app/src/glm2api/config.py` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 13570 | 3856 | `0x92e7d092` | `6ab6b1f4b30c65f7b33b06ee94659376360c7d106a3c6f24b7482ccc671de627` | `2ab29078224b41adabcccd16c0d73a1c33dbd90670af9917cb6ef926460f7d42` | `44827;44897-48753` | CRC OK; IDENTISCH |
| 23 | `glm2api-bundle/app/src/glm2api/__main__.py` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 1011 | 405 | `0x7d9b6e68` | `02d4a9d02de78af694f6233c01993d4b5ae4a0fbc27919a39036c1e8967d70ff` | `5becb9220d8561022cf1ccc2931cf5c0dff1a33f5e6101918016a222ac71cc77` | `48753;48825-49230` | CRC OK; IDENTISCH |
| 24 | `glm2api-bundle/app/src/glm2api/model_variants.py` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 1316 | 502 | `0xf4936b8c` | `41d568ac58e81427dd9779de69dd4434f439e734806821d70b6b098ec22248dc` | `f2f80f24ca060173b1cbf8fe03fbb0aa5e00ee8fc7e52138a1998765c9b9a1da` | `49230;49308-49810` | CRC OK; IDENTISCH |
| 25 | `glm2api-bundle/app/src/glm2api/__init__.py` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 92 | 83 | `0x0020a0cd` | `c43620168dcaf01e448f04e5de84eb06bf4203f61f5d2d9a4e30400a42765501` | `f2861fd5bb09bcf7e97a4c38bf4e31c32aae2cf5bf6580889d5eda18033f35e6` | `49810;49882-49965` | CRC OK; IDENTISCH |
| 26 | `glm2api-bundle/app/src/glm2api/server.py` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 23013 | 4218 | `0x456ebe02` | `30f0812219e909d7121054fb527cebd48e3bb2d754d8c05501f95d0e8d4a2d63` | `2ebf984fe31d72b7eca4500b524f8373980117d7aee5b3e31f1ae19f4d08907c` | `49965;50035-54253` | CRC OK; IDENTISCH |
| 27 | `glm2api-bundle/app/src/glm2api/utils/` | DIR | `0755` | 1980-01-01 00:00:00 | Stored/`0x0000` | 0 | 0 | `0x00000000` | `—` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `54253;54320-54320` | Struktur OK |
| 28 | `glm2api-bundle/app/src/glm2api/utils/__init__.py` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Stored/`0x0000` | 23 | 23 | `0x13e1fbda` | `bd3ce9cc0870670869f7177348df7949699fd36aa0c3b02c73450b5c6e1a1289` | `bd3ce9cc0870670869f7177348df7949699fd36aa0c3b02c73450b5c6e1a1289` | `54320;54398-54421` | CRC OK; IDENTISCH |
| 29 | `glm2api-bundle/app/src/glm2api/utils/tool_parser.py` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 47873 | 11106 | `0x84cf2db3` | `37d167d079fe833456b6719ba1f29834b70e4a639c9c02f92f6ff26512564f00` | `f4a7e2515c13c1b93ce5e1c8b4651aa743f57c3300dd0274c0891330b69a21cc` | `54421;54502-65608` | CRC OK; DRIFT; +160/−57; Hunks 14 |
| 30 | `glm2api-bundle/app/src/glm2api/utils/tool_protocol.py` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 8224 | 2856 | `0xbd59ee0a` | `40ca2a1dee29541204c64ddc48ff0cf9d4b9020492481646e29fbe7cd0e52951` | `dec4accb7a4e85ad2d422c69d1ff3479559bf2d7fceb0d03b74c6ecdeb48a57c` | `65608;65691-68547` | CRC OK; DRIFT; +10/−4; Hunks 6 |
| 31 | `glm2api-bundle/app/src/glm2api/app.py` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 4122 | 1284 | `0x7d33d0cf` | `61cb3c42a825d24713c2c82c9f822aa28aeefdb91e02f54b75354eeeb2ca1e4c` | `9d5f48e86e051a112451227a531ba0e97c822c75ddd8da2dfd5ff3bdeebcff50` | `68547;68614-69898` | CRC OK; IDENTISCH |
| 32 | `glm2api-bundle/app/src/glm2api/logging_utils.py` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 7882 | 2319 | `0x18ef7618` | `7f46e7dba4aeb3386c1f30bb618a49f828d699cb1000df23b0f769723248e593` | `ea69a6a356e1c64a7a74556c67aaf62f637cfcc665d311c71517d89488a50a70` | `69898;69975-72294` | CRC OK; IDENTISCH |
| 33 | `glm2api-bundle/app/src/glm2api/services/` | DIR | `0755` | 1980-01-01 00:00:00 | Stored/`0x0000` | 0 | 0 | `0x00000000` | `—` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `72294;72364-72364` | Struktur OK |
| 34 | `glm2api-bundle/app/src/glm2api/services/glm_auth.py` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 14048 | 3685 | `0x402465ba` | `9c149a7a0574bceb7f09195e8ce5d4efceb8fe832659b840ea01535ae09d5de5` | `5bb5669247ad507230f50e8c7f7561f228a58a8cbcda5ab6ca79d472d52f5aab` | `72364;72445-76130` | CRC OK; IDENTISCH |
| 35 | `glm2api-bundle/app/src/glm2api/services/translator.py` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 64319 | 14643 | `0x4f9e848c` | `348240937e95ad2391fdf390a931c7b55bf24d79533323b5bfb7e948b376d1b5` | `964679be988a833a894cc9ae44963ba770433cccee6b8f85b4a1a5e9f8f49d65` | `76130;76213-90856` | CRC OK; DRIFT; +146/−3; Hunks 10 |
| 36 | `glm2api-bundle/app/src/glm2api/services/__init__.py` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Stored/`0x0000` | 21 | 21 | `0x368ac88c` | `cf0c16951d8053d09a748f92fca56881d5f177333410a036b550387180105904` | `cf0c16951d8053d09a748f92fca56881d5f177333410a036b550387180105904` | `90856;90937-90958` | CRC OK; IDENTISCH |
| 37 | `glm2api-bundle/app/src/glm2api/services/responses_adapter.py` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 25465 | 4752 | `0x178b9a24` | `113f2533c6e2180b55f0106b486470dc4f9546d881a1d2d079854ee4d0b211c3` | `1072ed0d26d71a8d3ddbfdad81ce35fa391feb539440d002472d7043c4fb727b` | `90958;91048-95800` | CRC OK; IDENTISCH |
| 38 | `glm2api-bundle/app/src/glm2api/services/glm_client.py` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 64189 | 12823 | `0x48c892af` | `67b3ec0fadded6a4d944494823d96df0231330d1ae366144786eb019aa58820b` | `d73e1106e0a45504dffc927d5ccd0f34d5a6088473ab8beffde415e23ba12ed7` | `95800;95883-108706` | CRC OK; DRIFT; +2/−0; Hunks 2 |
| 39 | `glm2api-bundle/app/src/glm2api/services/anthropic_adapter.py` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 18640 | 3877 | `0x2d542063` | `4982ddf5d3a176658a115a2ee6e4b93a903cb427bee061e130b690f99dd6f45d` | `bf56ef1f2fd774d56585380d33ee41d8bfb3f09878576f2b7cc29e3ef461034d` | `108706;108796-112673` | CRC OK; IDENTISCH |
| 40 | `glm2api-bundle/app/.gitignore` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 172 | 139 | `0x0fff13c2` | `586eb8905a9b8958f16fae7c9ae958defe9e7599bb2fd4002827add03a524eb8` | `ba5e8b5e4f744aa294697185549b687c20534fc593c3c6ee64b38f9b3698145c` | `112673;112732-112871` | CRC OK; IDENTISCH |
| 41 | `glm2api-bundle/scripts/` | DIR | `0777` | 1980-01-01 00:00:00 | Stored/`0x0000` | 0 | 0 | `0x00000000` | `—` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `112871;112924-112924` | Struktur OK |
| 42 | `glm2api-bundle/scripts/install.sh` | TEXT/SOURCE | `0777` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 942 | 556 | `0x8abbdef6` | `b8699578e457f8a3c6da2fb51976ee38d3f8888973cb3da6a40dc3b48db94097` | `cdcdb12d642798589cf838d3b20211b1aeeb31fce67f1651e57490d855dcd748` | `112924;112987-113543` | CRC OK; IDENTISCH |
| 43 | `glm2api-bundle/scripts/start.sh` | TEXT/SOURCE | `0777` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 1532 | 795 | `0x91baf024` | `82f347df73162755eba94c6ff1c88727e4a56104bef3f526a3f7181c8fcf5df7` | `151051ecd48eff7bc6c901915f90087b0db70455db7b4efb24417786437bb634` | `113543;113604-114399` | CRC OK; IDENTISCH |
| 44 | `glm2api-bundle/docs/` | DIR | `0777` | 1980-01-01 00:00:00 | Stored/`0x0000` | 0 | 0 | `0x00000000` | `—` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `114399;114449-114449` | Struktur OK |
| 45 | `glm2api-bundle/docs/chatglm-reasoning-modes.md` | TEXT/SOURCE | `0666` | 1980-01-01 00:00:00 | Deflate/`0x0000` | 2184 | 1279 | `0x588e4513` | `5af4f21f9449ed128a88ebdc0a7f94a01c6b38fff0243eb10fd570472e87eacb` | `0a7abe763fc631ac233865538bdadd246563c5efc74620dc5a7be3d1bbda54a5` | `114449;114525-115804` | CRC OK; IDENTISCH |

**Hinweis:** In der obigen, bewusst lesbaren Kurzfassung wurden einzelne lange Roh-Hashes mit `…` abbreviert; der vollständige unveränderte Archiveintrag-Report steht in `/workspaces/MAIN/.runtime/revision-parts/Q.md`. Die Statusangaben und jeder Pfad sind vollständig übernommen.

## Read-only-Abgleich mit kanonischen Quellen

**Snapshot-Hinweis:** Die folgenden Archiv- und Source-Größen/Hashes beziehen sich auf den Q-Prüfzeitpunkt vor U. Die Drift-Dateiliste bleibt als historischer Befund erhalten; aktuelle Source-Größen werden nicht aus dieser Tabelle abgeleitet.

Alle 35 nicht-geschützten Dateien wurden vollständig aus dem ZIP gelesen, byteweise verglichen und ihre CRC32 gegen den ZIP-Header geprüft. `app/glm2api.env` wurde als Secret-Kandidat geschützt: kein `read`, keine Dekompression, kein Plaintext-Hash und keine inhaltliche Gleichheitsbehauptung.

| Kanonischer Pfad | Ergebnis |
|---|---|
| `llm-proxies/glm2api/src/glm2api/services/glm_client.py` | DRIFT: Archiv 1.344 Zeilen/64.189 B, Quelle 1.346/64.509 B; +2/−0, 2 Hunks. |
| `llm-proxies/glm2api/src/glm2api/services/translator.py` | DRIFT: Archiv 1.381 Zeilen/64.319 B, Quelle 1.524/69.477 B; +146/−3, 10 Hunks. |
| `llm-proxies/glm2api/src/glm2api/utils/tool_parser.py` | DRIFT: Archiv 1.297 Zeilen/47.873 B, Quelle 1.400/52.475 B; +160/−57, 14 Hunks. |
| `llm-proxies/glm2api/src/glm2api/utils/tool_protocol.py` | DRIFT: Archiv 188 Zeilen/8.224 B, Quelle 194/8.763 B; +10/−4, 6 Hunks. |
| `llm-proxies/glm2api/tests/test_tool_parser.py` | DRIFT: Archiv 588 Zeilen/22.435 B, Quelle 640/25.284 B; +53/−1, 2 Hunks. |
| `llm-proxies/glm2api/tests/test_translator.py` | DRIFT: Archiv 1.120 Zeilen/40.726 B, Quelle 1.209/43.892 B; +89/−0, 1 Hunk. |
| Alle übrigen 29 Dateien | byte-identisch zur jeweiligen kanonischen Quelle. |

- Erwartungsmenge des Build-Skripts: 36 Dateien; Archiv: 36 Dateien; fehlend/unerwartet: 0/0.
- `src/glm2api.egg-info` und Runtime-/Cache-Pfade werden gemäß Build-Skript ausgeschlossen.
- Die sechs Drift-Dateien verletzen die im Build-Skript dokumentierte Source-/Test-Byteverifikation.

## Secret-Namen und Abschlussstatus

- Keine verschlüsselten ZIP-Member, kein Manifest und kein Kommentar. Das explizit geschützte Env-Member `app/glm2api.env` ist die einzige in diesem Report genannte Secret-/Runtime-Datei; weitere solche Dateinamen wurden nicht behauptet.
- Sensible Kandidaten: `app/.env.example` (Template) und `app/glm2api.env` (geschützt).
- Hochsignante Schlüsselnamen wurden nur als Namen/Referenzen inventarisiert; keine JWT-, Bearer-, PEM- oder Provider-Key-Werte ausgegeben.
- ZIP lesbar/Zentralverzeichnis: PASS; Pfad-/Duplikat-/Header-Sicherheit: PASS; CRC 35/36: PASS; geschützte Datei: NOT TESTED BY DESIGN; Dateimenge 36/36: PASS; Byteidentität: FAIL (6 Drift); Extraktion/Build/Start: NO.
- Vollständiger Archivmember- und Hashreport: `/workspaces/MAIN/.runtime/revision-parts/Q.md`.
<!-- END PART Q -->

## Historischer Gap-Check R (superseded)

<!-- BEGIN PART R -->
## Revision R — read-only Abdeckungscheck (historischer Zwischenstand)

Der Report wurde vor dem Schreiben von Q und vor der Integration von O/P/Q erstellt. Er ist deshalb **kein aktueller Endstatus**.

- Zu diesem Zeitpunkt wurden 178 tracked, 5.514 ignorierte und 14 Symlinks erkannt.
- Als offene Coverage-Lücken wurden der damalige fehlende Q-Report, die noch nicht integrierten O/P-Berichte und die zwischenzeitlich geänderte `benchmark.md` genannt.
- Die Debug-Logs wurden als momentaner Snapshot mit möglicher Byte-/Größenänderung markiert.
- `R.md` behauptete außerdem, `Revision.md` ende vor O/P/Q; dieser Zwischenstand wurde durch die nachfolgenden Integrationen und S korrigiert.
- Q, O und P liegen nun vor; der aktuelle Benchmark ist in T geprüft; S und V sind die maßgeblichen Statusquellen.

**Keine Anwendungsdatei wurde durch R verändert.** Der vollständige historische Zwischenreport bleibt unter `/workspaces/MAIN/.runtime/revision-parts/R.md`.
<!-- END PART R -->

## Historischer Abschlusscheck S (superseded)

<!-- BEGIN PART S -->
## Revision S — historischer read-only Endstatus

**Prüfzeitpunkt:** 24.09.2026, 01:40:47 +0200 (Snapshot vor dem Schreiben dieser Datei)
**Wurzel:** ausschließlich `/workspaces/MAIN`
**HEAD:** `8e483ea195c53019a8956707fd0b82c56d85aa71`
**Modus:** statischer, read-only Abschlusscheck. Kein Dienststart, kein Build, kein Testlauf, keine Netzwerkanfrage und keine Löschung.

## Kurzurteil

- Der Bestand war zu diesem Snapshot vollständig inventarisiert: 178 tracked Einträge (176 reguläre Dateien, 2 Symlinks), 5.515 ignorierte Einträge (5.503 reguläre Dateien, 12 Symlinks) und 0 untracked, nicht ignorierte Einträge.
- Außerhalb `.git`: 5.679 reguläre Dateien, 14 Symlinks, 474 Unterverzeichnisse; jeder Datei-/Symlink-Eintrag war tracked oder ignoriert.
- `Revision.md` enthielt zu diesem Zeitpunkt die Anhänge A–Q; Q war vorhanden. Die fehlenden O/P/Q-Lücken aus R waren geschlossen.
- A–Q waren strukturell in `Revision.md` integriert, aber der Statusblock am Dateianfang war noch ein historischer A–K-Stand.
- Offen bleiben ZIP-Drift/Build-Nachweis, geschützter ZIP-Inhalt, Config-/Restore-Risiken, Agent-/Benchmark-Isolation und nicht ausgeführte Laufzeitverifikation.

## Verteilungs- und Coverage-Matrix

| Bereich | tracked | ignored | Abdeckung |
|---|---:|---:|---|
| `.devcontainer/` | 5 | 0 | A vollständig |
| `.opencode/` | 7 | 3.655 | A, O, K vollständig; Node-Baum strukturell |
| `config/` | 3 | 0 | P redigiert vollständig |
| `infra/` | 22 | 0 | B, C vollständig |
| `llm-proxies/` | 134 | 750 | D–I, Q vollständig; Runtime M/L |
| `.runtime/` | 0 | 1.105 | L vollständig strukturell |
| Root-/Cache-Dateien | 7 | 1 | A/N/M vollständig |
| `.pytest_cache`-Einträge ohne eigene Bereichszeile | 0 | 4 | N/M strukturell erfasst; in dieser historischen Matrix nachgetragen |

- O deckt `.opencode/agent/glm2api.md` und `.opencode/command/quota.md` vollständig ab.
- P deckt `config/passphrase`, `config/secrets.enc` und `config/secrets.manifest` redigiert strukturell ab.
- Q deckt alle 45 ZIP-Einträge strukturell ab; sechs Dateien driften vom kanonischen Source ab, ein geschützter Env-Member blieb metadata-only.
- R ist als historischer Zwischenstand zu behandeln, nicht als aktueller Endstatus.

## Geprüfte Grenzen

- Keine Secretwerte, Tokens, Cookies oder Passphrasen wurden im Abschlusscheck ausgegeben.
- ZIP wurde nicht entpackt; kein Build/Test/Server/Port/Remote wurde ausgeführt.
- Ältere Reports A–N wurden im Abschlusscheck nicht vollständig neu gelesen; ihre Aussagen sind zeitlich markierte Evidenz.
- Der aktuelle Benchmark benötigt den separaten Recheck T.
- Eine Umgebungs-/LSP-Diagnose in `llm-proxies/antigravity-proxy/cmd/callback-server/main.go` wurde weder durch Build/Test verifiziert noch geändert.

## Abschlussstatus

**Historischer Snapshot: Dokumentations-/Coverage-Check bestanden; Produktstatus nicht abnahmefähig; Build-, Test- und Laufzeitverifikation offen.** O, P und Q waren zu diesem Snapshot vorhanden; diese Aussage ist keine aktuelle Produktfreigabe. Ältere Snapshot-Mengen im Startblock wurden nicht automatisch umgeschrieben.
<!-- END PART S -->

## Anhang T — AuditMesh-Benchmark-Vertrag (historischer Snapshot)

<!-- BEGIN PART T -->
## Revision T — AuditMesh-Benchmark-Vertrag (Snapshot)

**Analysedatum:** 24.09.2026
**Arbeitsgrenze:** ausschließlich `/workspaces/MAIN`
**Prüfmodus:** statisch, read-only; keine Tests, Starts, HTTP-/Netzwerkaktionen oder Secret-Inhalte ausgegeben
**Zieldatei:** `llm-proxies/glm2api/benchmarks/benchmark.md`
**Zielstand:** 379 Zeilen, vollständig gelesen

## Kurzurteil

Der aktuelle Benchmark ist als fachlicher AuditMesh-Spezifikationsvertrag gut strukturiert: Struktur, Fixtures, Baseline-Metriken, eine Eingabemutation und die wichtigsten Reportmarker sind konkret beschrieben. Der neue absolute Pfadvertrag ist jedoch nicht vollständig geschlossen:

1. `/workspaces/benchmark/auditmesh-current` ist als kanonischer Root an 28 Literalvorkommen auf 25 Zeilen fest eingetragen.
2. Schritt 2 erlaubt weiterhin einen beliebigen frischen Laufpfad und verlangt nur eine Ersetzung im Agentenauftrag.
3. Die Post-Run-Befehle stehen vor dem Agentenauftrag und verwenden den festen `auditmesh-current`-Pfad. Bei wörtlicher Befolgung können Agentenlauf und Post-Run-Prüfung unterschiedliche Verzeichnisse prüfen.
4. Der Verifier akzeptiert einen beliebigen aufgelösten `root`, prüft keine erlaubte Parent-Basis, keine Canonical-Pfad-Regel und keine Symlink-/Race-Grenze.
5. Tool-, Session-, Test- und Sicherheitskriterien sind überwiegend manuell oder im Prosa-Vertrag formuliert; `verify_auditmesh.py` führt weder generierte Pytests noch Session-Part-Export, Tool-Allowlist-Check, Netzwerk-Check oder Sandbox-Prüfung aus.

**Gesamtstatus:** fachlich starke Spezifikation, aber **kein vollständig automatisierter oder sicherheitsisolierter Benchmark-Gate**.

## Änderungsdelta seit dem letzten Audit

| Commit | Betroffene aktuelle Datei | Relevante Änderung | Bewertung |
|---|---|---|---|
| `f296b7a` | `benchmarks/verify_auditmesh.py` | Von 314 auf 476 Zeilen; exakte Fixturezeilen, Baseline-/Mutation-Metriken, Reportmarker und SHA-256-Immutable-Snapshots ergänzt | Verbesserte fachliche Oracle-Abdeckung; Isolation und Testauthentizität bleiben offen |
| `6a17fc9` | `.opencode/agent/glm2api.md` | Toolliste erweitert; `webfetch`/`question`/`task` nicht mehr pauschal verweigert; Session-Löschtools explizit gesperrt | Benchmark-Phasen ermöglicht, aber Prompt-Regel |
| `862e52c` | `benchmark.md`, `translator.py` | Toolverfügbarkeit/Subagenten explizit; native `open`-Kommandos können auf `bash` abgebildet werden | Zusätzliche Mapping-/Anomalie-Lücke |
| `3acce8f` | `.opencode/agent/glm2api.md` | `mode: subagent` zu `mode: all` geändert | Haupt- und Subagent-Nutzung möglich |
| `3678a5c` | `benchmark.md` | Platzhalter durch absoluten Root `/workspaces/benchmark/auditmesh-current` ersetzt | Neuer Pfadvertrag; Runner-Substitution nicht eindeutig |
| `8e483ea` | Arbeitsbaum/Autosave | Aktueller HEAD; keine zusätzliche Benchmarkdatei geändert | Keine weitere Vertragsänderung festgestellt |

## Neuer absoluter Benchmarkpfad-Vertrag

| Referenz | Vertrag |
|---|---|
| `benchmark.md:19-21` | Ein frischer, leerer Laufpfad wird gewählt; Beispiel: `/workspaces/benchmark/auditmesh-20260923-01`. Der Runner soll den Literalpfad `/workspaces/benchmark/auditmesh-current` im Agentenauftrag durch den gewählten Pfad ersetzen. |
| `benchmark.md:26-31` | Nach dem Lauf werden `uv run --directory` und `verify_auditmesh.py` mit `/workspaces/benchmark/auditmesh-current` als Projektargument gezeigt. |
| `benchmark.md:40-51` | Agentenauftrag, Arbeitsgrenze und Dateioperationen verwenden den festen Root und verlangen vollständig absolute Pfade. |
| `benchmark.md:72-73,99-124` | `glob`, `grep`, Fixture-Prüfung, Implementierung, Tests, CLI, Subagent und lokaler Server werden an denselben Root gebunden. |
| `benchmark.md:136-177` | Erwartete Baumstruktur, Entry-Point und die beiden Output-Artefakte liegen unter demselben Root. |
| `benchmark.md:180-329` | Fixture- und Metrikverträge sind relativ zum Projektroot formuliert. |
| `benchmark.md:341-379` | Abschluss, Funktion, Toolabdeckung und Session-Export beziehen sich auf denselben Lauf, definieren den Root aber nicht erneut. |

Im aktuellen `benchmark.md` gibt es kein `<BENCHMARK_ROOT>` mehr. Der kanonische Root kommt in 28 Literalvorkommen auf 25 Zeilen vor; der Verifier selbst besitzt keine Root-Konstante und verwendet sein CLI-Argument.

## Widersprüche und Vertragslücken

- **T-01 (hoch, funktional):** `benchmark.md:19-21` spricht nur von einer Ersetzung im Agentenauftrag ab Zeile 38; Post-Run-Befehle mit Root stehen bei `29-30`. Ein wörtlich umgesetzter Lauf kann unter einem anderen Root arbeiten, während Prüfungen den alten `auditmesh-current`-Bestand prüfen.
- **T-02 (mittel, Vertragsmodell):** `current` ist zugleich Default und Ersetzungstoken; ein beliebiger Beispielpfad ist erlaubt, aber Parent-Basis, Freshness und Ersetzungsreichweite sind nicht definiert.
- **T-03 (hoch, Isolation):** Die Vertragsgrenze „ausschließlich unter dem Laufpfad“ ist nicht durch den Verifier erzwungen; `args.root.resolve()` ist keine Sandbox.
- **T-04 (mittel, Portabilität):** Es gibt kein Runner-/Substitutionsprogramm im aktuellen Benchmarkverzeichnis; die Pfadtransformation ist manuell.
- **T-05 (mittel, Kollision):** Ein vorhersehbarer Shared-Path ohne Lock-/Freshness-Prüfung erlaubt konkurrierende oder veraltete Läufe.
- **T-06/T-07 (mittel):** Optionale `question`/Subagentenwerkzeuge stehen gegen unbedingte Auswertung; `skill` wird im Benchmark verboten, aber nicht im Agentenprompt/Hostpermission gesperrt.
- **T-08/T-09 (hoch/mittel):** Native `open`-/Sandbox-Tools können auf `bash`/`read`/`webfetch` abgebildet werden; Herkunft und nichtlokale `webfetch`-Ziele werden nicht technisch erkannt.
- **T-10/T-11 (hoch):** Phasen, Autonomie, Toollecks und Sessionstatistik sind Prosa-/manuelle Kriterien und werden vom Verifier nicht geprüft.

## Vollständige Zeilenabdeckung

`benchmark.md:1-379` wurde vollständig und zeilenweise gelesen; Leerzeilen wurden ebenfalls geprüft.

| Zeilen | Inhalt und Ergebnis |
|---:|---|
| 1-8 | Zweck, Modell, Agentenlauf, kein Request-Geschwindigkeitsbenchmark — vollständig erfasst. |
| 10-17 | Proxy-Start und Smoke-Preflight — vollständig erfasst; Ausführung verboten. |
| 19-25 | Rootauswahl, Ersetzung, frische Session, kein Defaultmodell, nur Agentenauftrag — T-01/T-02. |
| 26-36 | Post-Run-Befehle, Verifier, Mutationstest — T-01 und Verifiergrenzen. |
| 38-60 | Projektanlage, Arbeitsgrenze, absolute Pfade, Tools, Netzabhängigkeit, sequenzielle Calls — vollständig erfasst. |
| 62-90 | Pflicht-/Optionaltools, Subagentenregel, verbotene Tools, `glob`/`grep`-Eigenständigkeit — T-06 bis T-09. |
| 92-131 | Phase 0–10, Fixtureprüfung, Tests, CLI, Task, lokaler Webfetch, DB-Statistik, Abschluss — Test-/Prozesslücken. |
| 133-178 | Erwartete Struktur, Entry-Point, unveränderte Eingaben/Quellen, Outputartefakte — T-03/Verifierabgleich. |
| 180-260 | Services, Limits, Dokumentbeziehungen, Log-/Security-Fixtures — gegen Verifierzeilen abgeglichen. |
| 262-285 | Dataclass-, Korrelations-, Fehlerraten-, Runbook-, Service- und Compliance-Regeln — nicht automatisiert. |
| 287-329 | Verbindliches Metrik-Schema inklusive Listenreihenfolge und Floats — Verifier nur tolerant/teilweise. |
| 331-339 | Reportheader, `ERR-404`, `obsolete.md`, Statusmarker — nur markerbasiert geprüft. |
| 341-353 | Tests, CLI, Metrikabgleich, Abschlussbericht, exakte Abschlussfrage — optionale Frage widersprüchlich. |
| 355-379 | Passkriterien, Preflight, Modell, Autonomie, Toollecks, Funktions-/Sessionkriterien — kein automatisierter Export-Gate. |

Zusätzliche statische Querverweise: aktueller `.opencode/agent/glm2api.md`, `verify_auditmesh.py:1-476`, `smoke-test.sh`, `start-glm2api.sh`, `pyproject.toml`, `translator.py:309-353`, `opencode.json:280-295` und relevante Teststellen.

## Verifier-Abgleich

**Stärken:**

- Required-Dateien, Services, Limits, Logs und Runbook-Überschriften stimmen zwischen Benchmark und Verifier überein.
- Baseline und Mutation prüfen die meisten Metrikfelder, Grenzgleichheiten und nicht ignorierte Dateisnapshots.
- Der Verifier prüft beide erwarteten Pipelinezustände.

**Lücken:**

1. Er startet generierte Tests nicht; Build, Installation, Entry-Point und Testqualität werden nicht geprüft.
2. Zusätzliche Check-Objekte sind erlaubt; `passed_checks` wird nicht aus der gelieferten Liste berechnet.
3. Float-Toleranz `1e-9` und `.get()`-Felder sichern den exakten JSON-/Float-Vertrag nicht.
4. Der vollständige Report wird nur über Marker geprüft; Häufigkeiten, Korrelation und Dokumentationsstatus fehlen.
5. `output`, Cache-/venv-Pfade und zusätzliche Dateien werden nicht vollständig vertraglich begrenzt.
6. Der Linkparser deckt nur einfache Inline-Links ab.

## Sicherheitsfolgen

- **Keine Sandbox (hoch):** `run_pipeline()` kopiert die Umgebung, startet erzeugten Code ohne Umgebungs-/Netzwerk-/Dateisystemisolierung und begrenzt nur den direkten Child-Prozess auf 60 Sekunden.
- **Symlink-/Root-Escape (hoch):** Required-Dateien, `read_text`/`read_bytes` und `copytree` folgen Symlinks; Root/Parent/Owner/Frische werden nicht geprüft.
- **Netzwerk-/Dependency-Grenze nicht erzwungen (hoch):** `127.0.0.1` ist eine Prompt-Regel, kein Socketfilter.
- **Fehlerausgabe/Prozessgrenze (hoch/mittel):** Bis zu 3.000 stdout-/stderr-Zeichen werden unredigiert übernommen; Nachfahren und Ressourcen werden nicht zuverlässig begrenzt.
- **Prompt-/Permission-Schichten (hoch):** globale `permission: allow`, Agentenregeln und Benchmark-Prosa sind keine technische Sandbox.
- **Shared-Path-Kollision (mittel):** kein Lock-/Freshness-Check für `/workspaces/benchmark/auditmesh-current`.

## Empfohlene Reihenfolge (nicht ausgeführt)

### P0

1. Einen einzigen unveränderlichen Runnervertrag mit Root-Variable einführen; Ersetzung muss alle Verwendungen einschließlich Pytest/Verifier erfassen.
2. Root canonicalisieren, Parent-/Freshness-/Eigentümer-/Rechte-/Symlink-Prüfung erzwingen.
3. Verifier in reduzierte Umgebung, Netzwerk-/Dateisystemisolierung, Prozessgruppen-/Ressourcenlimits und redigierte Fehlerausgabe überführen.
4. Symlink-/Hardlink-/Output-Linkziele vor Read/Write/Copy ablehnen.

### P1

1. Optionale/obligatorische Tool-, Phasen- und `question`-Logik vereinheitlichen.
2. Statischen Pfad-/Rootvertragstest ergänzen.
3. Generierte Tests, `pyproject`, Build und Entry-Point im kontrollierten Gate ausführen; No-op-Tests/Zusatzchecks ablehnen.
4. Session-Part-Export und Toolprüfung implementieren oder als manuelle Checkliste markieren.
5. `skill`, Native-Tool-Herkunft und nichtlokale `webfetch`-Ziele in einer kanonischen Toolpolicy behandeln.

### P2

1. Float-/JSON-Vertrag exakt definieren und Nichtstandardzahlen zurückweisen.
2. Reportwerte, Tabellen, Linkformen und erlaubte Outputmenge vollständig prüfen.
3. Preflight-Skripte self-contained machen.

## Abschlussstatus

- `benchmark.md:1-379`: vollständig gelesen, keine Zeile ausgelassen.
- Relevante Agent-, Verifier-, Preflight-, Proxy- und Testquerverweise statisch geprüft.
- Keine Tests, Benchmarkläufe, Starts, HTTP-Aktionen, Installationen oder Löschungen.
- Keine Secretwerte gelesen oder wiedergegeben.
- Vollständiger Recheck: `/workspaces/MAIN/.runtime/revision-parts/T.md`.
<!-- END PART T -->

## Anhang U — Delta-Audit der extern übernommenen glm2api-Änderung

<!-- BEGIN PART U -->
## Partition U – Statischer Delta-Audit der extern geänderten glm2api-Dateien

**Historischer Delta-Snapshot:** Dieses Ergebnis bleibt auf die beiden genannten Dateien und den Commit-Parent `8e483ea` begrenzt; es ist keine aktuelle Gesamtfreigabe des Projekts.

**Stand:** 24.09.2026
**Arbeitsverzeichnis:** `/workspaces/MAIN`
**Vergleichsbasis:** Commit-Parent `8e483ea195c53019a8956707fd0b82c56d85aa71`
**HEAD bei Abschlussprüfung:** `ac780204b00e97d89f95ea2f5a6ea08e5dcfe64a`

## Scope, Methode und Redaktion

Analysiert wurden ausschließlich:

- `llm-proxies/glm2api/src/glm2api/services/glm_client.py` – 1.346 Zeilen vollständig gelesen.
- `llm-proxies/glm2api/src/glm2api/services/translator.py` – 1.567 Zeilen vollständig gelesen.

Vorgehen: `git diff` für genau diese Pfade, vollständige zeilenweise Lektüre, Abgleich mit F/I, statisches `ast.parse` ohne Import/Ausführung, `git diff --check` und anschließende read-only Verifikation des externen Commit-Deltas. Keine Tests, Server, Clients, Netzwerkaktionen oder Installationen. Keine Secret-/Token-/Payloadwerte ausgegeben. `Revision.md` und die Quelldateien wurden durch diesen U-Auditprozess nicht verändert; nachfolgende externe Autosave-Änderungen sind davon getrennt zu betrachten.

## Beobachtetes Delta

| Datei | Ergänzungen | Löschungen | Inhalt |
|---|---:|---:|---|
| `glm_client.py` | 2 | 2 | Dieselbe Follow-up-Anweisung in zwei nahezu identischen Payload-Buildern: strukturierter Tool-Call nach blockiertem Tool, keine Entschuldigungs-/Meta-Texte. |
| `translator.py` | 43 | 0 | `filePath`-Reparatur, Meta-Chatter-Keyword-/Zeilenfilter und Integration in `finalize()`. |

Aktuelle Stellen: `glm_client.py:211-243,403-440`; `translator.py:237-247,374-406,1259-1263`. Das Delta wurde während des Audits extern als Commit `ac780204` mit Parent `8e483ea` übernommen; die Blob-IDs stimmen überein.

## Klassifikation älterer Befunde

- Kein Befund aus F/I wurde durch die Änderung beseitigt.
- I-001 bis I-006 und I-010 bis I-020 bleiben im aktuellen Stand bestehen, soweit ihre Dateien nicht geändert wurden.
- I-007 (Streamabbruch als Erfolg), I-008 (History-Paare) und I-009 (Wildcard-/Native-Mapping) bleiben bestehen und sind durch den neuen Stream-Filter bzw. die Pfadumschreibung teilweise stärker relevant.
- I-005, I-006, I-014–I-016 bleiben unverändert; die Änderung fügt keine Redaktion, kein Ressourcenlimit, keine Sessionbindung und keine strikte Terminierung hinzu.
- F-01–F-29 betreffen ausschließlich den Go-Scope unter `llm-proxies/antigravity-proxy/`; U berührt keine F-Datei.

## Neue Befunde

### U-01 — Mittel: Meta-Chatter-Filter ist all-or-nothing, stream-only und semantisch inkonsistent

`strip_meta_chatter()` entfernt ganze Zeilen anhand harter Sprach-/Schreibweisenmarker. Ohne Tool-Call wird Originaltext nur dann verworfen, wenn der Filter das gesamte Ergebnis leert. Mit Tool-Call wird der Text gefiltert, aber bei `all_tool_calls` nicht emittiert. Bereits gesendete Stream-Deltas werden nicht zurückgenommen; `build_response()` im Non-Stream-Pfad ruft den Helper nicht auf.

**Auswirkung:** Legitimer Text kann still verschwinden; Stream- und Non-Stream-Antworten behandeln denselben Modelltext unterschiedlich; der Filter ist keine Qualitäts- oder Sicherheitsgarantie.

**Empfehlung:** Keine hartcodierte Zeilenbereinigung in Nutzerausgaben; strukturierten Abschlusszustand und konsistente Anwendung auf beide Response-Pfade verwenden.

### U-02 — Mittel bis Hoch: `filePath` wird ohne Root-Kontext umgeschrieben

`workspaces/...` wird auf `/workspaces/...`, `benchmark/...` auf `/workspaces/benchmark/...` abgebildet, ohne Existenz-, Root-, Schema- oder kanonische Pfadprüfung. Das gilt auch für Conversation-Historie und nicht nur für Read/Write/Edit. Non-Stream- und serverseitige Call-Sanitisation bleiben uneinheitlich.

**Auswirkung:** Ein gültiger, absichtlich anders verankerter Pfad kann auf einen festen Hostpfad umgeleitet werden; bereits ausgeführte History-Calls können semantisch umgeschrieben werden.

**Empfehlung:** Nur explizit gegen den tatsächlichen Projektroot validierte absolute Pfade akzeptieren; Root als strukturiertes Toolargument und dieselbe Sanitisation für Streaming, Non-Stream und History verwenden.

### U-03 — Niedrig: Follow-up-Anweisung dupliziert Verzweigungslogik

Die neue Anweisung wurde in zwei lokalen Buildern wiederholt. Die doppelte History-Signatur-Extraktion und fehlende zentrale Follow-up-Repräsentation aus Anhang I bleiben bestehen; Drift-/Paritätsrisiko steigt.

## Nicht nummerierte Altbefunde

- Doppelte Signatur-Extraktion unverändert (`glm_client.py:186-191`).
- Präambeltextverlust bei Tool-Calls bleibt bestehen.
- Serverseitige Calls werden nicht in allen Pfaden final sanitisiert.
- History-Echo-/Signatur-Deduplizierung und fehlende ID-Berücksichtigung bleiben bestehen.
- Logik-IDs werden weiterhin nicht zwingend Ereignisreihenfolge folgend sortiert.
- Usage bleibt Dummy; ungenutzte Helper bleiben bestehen.

## Schlussfolgerung

Das externe Delta ist syntaktisch sauber, beseitigt keinen priorisierten I-Befund und verbessert weder Queue-Leasing, Ressourcenlimits, Session-Isolation, SSE-Terminierung, Tool-Allowlisting noch Inputvalidierung. Es kommen eine mögliche Output-Unterdrückung und eine kontextunabhängige Pfadumschreibung hinzu. Für den bestehenden Happy Path ist keine Verhaltensregression statisch belegt; die neuen Vertragsrisiken sind dennoch relevant.

Vollständiger Recheck: `/workspaces/MAIN/.runtime/revision-parts/U.md`.
<!-- END PART U -->

## Historische Endkontrolle nach U

Dieser Abschnitt ist ein historischer Snapshot vom Abschluss des U-Berichts und beansprucht keinen aktuellen Git- oder Inventarstand.

- **HEAD bei Abschlussprüfung:** `ac780204b00e97d89f95ea2f5a6ea08e5dcfe64a`.
- **Inventar bei diesem Snapshot:** 178 tracked, 5.518 ignorierte, 0 untracked-nicht-ignorierte Einträge; 14 Symlinks außerhalb `.git`.
- **Arbeitsbaum bei diesem Snapshot:** `Revision.md` war als Änderung sichtbar; die beiden in U genannten Quelldateien waren bereits extern committed.
- **Integrität zum damaligen Zeitpunkt:** `git diff --check` und die damalige Secret-Mustersuche waren ohne Treffer; diese Aussage gilt nicht automatisch für spätere Bearbeitungen.
- **Offen:** Keine Test-, Build-, Runtime-, Remote- oder Portverifikation; die Befunde der historischen Reports bleiben bestehen, sofern sie nicht ausdrücklich als behoben oder superseded markiert sind.

## Anhang V — Redaktionelle Endkontrolle

<!-- BEGIN PART V -->
## Revision V — redaktionelle Endkontrolle

**Prüfzeitpunkt:** 24.09.2026, 17:52:53 +0200
**Basis-HEAD:** `fd8f1ca1ffa8d4af80f14de0e886913819fce1ff`
**Arbeitsgrenze:** ausschließlich `/workspaces/MAIN`
**Änderungsumfang:** Dokumentstruktur, Statusqualifizierung und historische Snapshot-Kennzeichnung in `Revision.md`; keine Anwendungs-, Secret- oder Infrastrukturänderung durch diese redaktionelle Kontrolle.

## Kurzurteil

Die redaktionelle Markdown- und Markerstruktur ist konsistent: Das Dokument besitzt eine explizite Master-H1, eine eindeutige Vorrangmatrix, 22 historische/current Parts in der Reihenfolge A–Q, R, S, T, U, V und keine ungeschützten Endmarker. Die A–U-Berichte bleiben als historische Evidenz mit ihren ursprünglichen lokalen Unterebenen erhalten; die Reporttitel wurden zur Vermeidung konkurrierender H1-Ebenen als H2 normalisiert. Ihre früheren Commit-, Inventar- und Sourcezahlen werden nicht als aktuelle Produktwerte missverstanden.

**Format- und Redaktionscheck:** `Revision.md` hat 1 Master-H1, 22 vollständige Part-Marker-Paare, 6 Codefence-Zeilen (3 Blöcke) und keine ungeschützten Endmarker. `git diff --check` ist sauber; JWT-/PEM-/GitHub-/Google-Key-Muster ergeben 0 Treffer.

Die technische Produktlage bleibt unverändert offen: Build, Tests, Serverstart, Runtime, Port- und Remote-Verifikation wurden nicht ausgeführt. Die im Audit dokumentierten Bundle-, Config-, Security-, Benchmark- und glm2api-Befunde sind nicht als behoben zu verstehen.

## Verifizierte aktuelle Querverweise dieses Reviews

- `benchmark.md` enthält den Root `/workspaces/benchmark/auditmesh-current` in 28 Literalvorkommen auf 25 Zeilen; der qualitative Root-/Post-Run-Mismatch bleibt offen.
- `glm_client.py` umfasst 1.346 Zeilen; `translator.py` umfasst 1.567 Zeilen. Q/I-Metadaten bleiben als Prä-U-Snapshots markiert.
- Die vier OAuth-Skripte, die Reverse-Engineering-Ausgabepfade sowie die Verweise auf `glm-api-audit.md` und `io_utils.py` bleiben als offene Pfad-/Dokumentationsbefunde bestehen.
- Die in `infrastructure.md` genannten Layout-/Provider-/Rebuild-Abweichungen wurden nicht als Teil dieser Dokumentbereinigung geändert.

## Statusgrenzen

- Die technische Revision ist **nicht abnahmefähig**; die offenen Befunde bleiben im jeweiligen historischen Report nachvollziehbar.
- Ignorierte `.runtime/revision-parts/REVIEW-*.md` sind Arbeitsbelege und keine kanonischen Repository-Dateien.
- Commit- und Inventarzahlen sind Momentaufnahmen; für einen neuen Vergleich muss ein neuer Prüfzeitpunkt mit eigenem HEAD und Scope festgehalten werden.
- Secretwerte wurden nicht wiedergegeben. Checksummen und Commit-IDs in den historischen Reports sind Integritäts- bzw. Provenienzangaben, keine Credential-Werte.
- Diese Endkontrolle behauptet keine technische Behebung und keine Produktfreigabe.
<!-- END PART V -->
