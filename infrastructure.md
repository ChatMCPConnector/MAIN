# MAIN — Multi-Account Arbeitsumgebung als Code

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/ChatMCPConnector/MAIN?quickstart=1&ref=main)

Geteiltes Multi-Account-Repo (ein User, mehrere GitHub-Accounts, je max. ~60h
Codespaces/Monat): die komplette persönliche Arbeitsumgebung — Dev-Container,
opencode-Config (mehrere LLM-Provider), Secrets-Mechanik, GLM-Haupt-Proxy.
Alles Bleibende liegt im Repo; pro Account einmalig PAT + Passphrase als
Codespaces-Secrets, danach läuft alles automatisch (`postCreateCommand` →
`.devcontainer/setup.sh`).

**Doku-Aufteilung:** `README.md` = kurze öffentliche Übersicht (GitHub).
Diese Datei (`infrastructure.md`) = **vollständige Doku** (Layout + Betrieb +
Secrets-Modell + Changelog). `AGENTS.md` = Verhaltensregeln für Agenten
(wird von opencode automatisch gelesen).

## Layout — was wozu gehört

| Pfad | Zweck |
|---|---|
| `.devcontainer/` | devcontainer.json + setup.sh (läuft automatisch bei jedem Codespace-Bau), autosave-daemon.sh (30-Min-Auto-Commit+Push), proxy-watchdog.sh |
| `.opencode/` | opencode-Config: opencode.json (Provider/MCP), tui.json |
| `config/` | secrets.enc (verschlüsseltes Bundle) + Manifest + passphrase (Klartext, bewusst) |
| `infra/` | **Werkzeugkasten:** `scripts/` (save/auth/secrets/ports/browser-*.sh, aliases.sh, config-watchdog.sh, nvidia-models.py, validate-revision.sh), `mcp/` (opencode-sessions MCP), `docs/` (Reverse-Engineering-Doku) |
| `llm-proxies/` | LLM-Proxies: **glm2api** (Port 8001, GLM-Haupt-Proxy) + **antigravity-proxy** (Port 9878, CloudCode OAuth) |

| `.env` `.runtime/` | GITIGNORED — Klartext-Secrets (.env), Browser-Profil, Runtime (nie committen) |

## Schnellstart

Codespace bauen → `setup.sh` stellt ALLES automatisch wieder her (Systempakete,
opencode, uv, Secrets-Unlock, Git-Auth, Browser-Runtime, **glm2api-Proxy inkl.
Start** — der Code liegt komplett im Repo, es gibt nichts mehr zu klonen; nur
`uv sync` (Python 3.14 + Deps, beim ersten Mal ~2-5 Min) + Autostart). Danach:

```bash
./infra/scripts/save.sh status                       # Überblick (Repo, Auth, Secrets)
./infra/scripts/validate-revision.sh                # read-only Revision.md-Check
```

Aliase (via `infra/scripts/aliases.sh`, automatisch in .bashrc): `save`, `auth`,
`secrets`, `ports`, `quota`, `st`, `ll`, `autosave` (status/start/stop/log),
`config-watchdog` (status/start/stop/log), `landscape-diff`, `ocver`
(opencode-Versionspin: check/latest/bump/install).

## Enthalten

- Ports 3000/8000 (Apps), 4096 (opencode-Server für Multi-Client), 8001 (glm2api LLM-Proxy), 9878 (antigravity-proxy), 6082/5920 (Browser-VNC, nur lokal)
- opencode, Default-Modell `antigravity/gemini-3.8-flash` (fest auf high Thinking gemappt)
- `infra/scripts/nvidia-models.py`: NVIDIA-Modellindex von build.nvidia.com
  (kostenlos, NIM-Keys), für Modell-Discovery

## Secrets-Modell (bewusst: Komfort > Sicherheit)

Repo ist shared für mehrere **eigene** Accounts. Automatik hat Vorrang vor
Secret-Schutz-Purismus:

- `config/passphrase`: Entschlüsselungs-Passphrase als Klartext im Repo → jeder
  eigene Codespace entsperrt sich beim Start selbst. Sie ist NUR ein
  Entschlüsselungswort — nie ein Secret/PAT als Passphrase zweckentfremden
  (der alte PAT wurde dadurch geleakt und von GitHub revoked).
- `config/secrets.enc` (+ Manifest): verschlüsseltes Bundle mit
  `pat`, `nvidia-nim.key`, `xinjianya.key`, `antigravity-oauth_creds.json`, `chatglm-refresh-token`,
  `env`, `opencode-auth.json` → landen beim Unlock unter `~/.config/landscape/`,
  `~/.local/share/opencode/auth.json` bzw. `.env`.
- `./infra/scripts/secrets.sh lock|unlock|status` verwaltet das Bundle.
  `unlock` probiert **alle** Passphrase-Kandidaten durch, bis einer das Bundle
  tatsächlich entschlüsselt (`LANDSCAPE_PASSPHRASE`, dann `config/passphrase`,
  dann die interaktive Abfrage). Der erste Versuch gewinnt nicht mehr —
  ein falsch gesetztes Secret kann den Auto-Unlock nicht mehr totlegen.
  Kandidaten mit PAT-Präfix (`ghp_`, `github_pat_`, `glpat-`, …) werden
  verworfen: ein PAT ist keine Passphrase (siehe Changelog 2026-09-26).
- Codespaces-Secrets pro Account: `LANDSCAPE_PAT` (Git-Auth), `LANDSCAPE_PASSPHRASE` (optional).
  `LANDSCAPE_PASSPHRASE` muss der **Inhalt von `config/passphrase`** sein, nicht
  der PAT. Ist das Secret nicht gesetzt, greift der Repo-Fallback automatisch —
  das Secret ist also Komfort, keine Voraussetzung.
- NVIDIA-/XinJianYa-Keys in `opencode.json` referenzieren `{file:~/.config/landscape/<key>}` und kommen über das Bundle in jeden neuen Codespace. `glm2api` nutzt lokal `local` als Platzhalter; TokenRouter und Antigravity enthalten weiterhin getrackte Literalwerte (siehe `Revision.md`, `SEC-02`).
- **Start-Garantie:** eine fehlende `{file:...}`-Referenz lässt opencode
  *komplett* nicht starten (`Configuration is invalid … bad file reference`).
  Deshalb legt `infra/scripts/keys.sh ensure` jede referenzierte Key-Datei als
  leeren Platzhalter an, falls sie fehlt. Aufgerufen von `setup.sh`,
  `opencode-server.sh` und dem `opencode`-Wrapper — damit startet opencode in
  jedem Codespace, auch wenn der Unlock einmal scheitert. Ein 0-Byte-Platzhalter
  gilt beim Unlock und beim Lock als „fehlt": er überschreibt nie einen echten
  Key und landet nie im Bundle.
   `./infra/scripts/keys.sh status|doctor|restore` (Aliase `keys`, `keys-doctor`,
   `keys-restore`): `status` zeigt je Datei `OK/LEER/FEHLT`, `doctor` testet live
   gegen die Provider (unterscheidet echt von Auth-Fehler, Cloudflare-Challenge
   und Netz-Ausfall), `restore` holt fehlende Keys nach. `secrets.sh status`
   prüft zusätzlich, ob das Bundle überhaupt entschlüsselbar ist.
   **Zwei bekannte Fehlalarme von `doctor`** (beide kein Key-Problem, live geprüft
   2026-09-26): (a) **Cloudflare 403 HTML** bei `xinjianya` — der Bot-Schutz
   filtert den TLS-Fingerprint von `curl`, nicht den von opencode; der Key
   funktioniert, `opencode run --model xinjianya/gpt-5.6-sol` liefert Antwort
   (2026-09-26 verifiziert). (b) **TIMEOUT bei `nvidia`** — NIM-Kaltstarts
   schwanken (57 s bis 91 s gemessen), weshalb `PROBE_TIMEOUT_SECONDS` auf 180 s
   steht; die Meldung `TIMEOUT/KEIN KONTAKT` bedeutet also "langsamer als 180 s",
   nicht "tot". Im Zweifel `opencode run --model <provider>/<modell>` — nur das
   beweist Nutzbarkeit.


## opencode-Konfiguration (`.opencode/`)

Provider (`opencode.json`, Default `antigravity/gemini-3.8-flash`):

| Provider | Modelle | Auth |
|---|---|---|
| nvidia | GLM 5.3 (1M/128K, Text, Reasoning) | nvidia-nim.key |
| xinjianya | gpt-5.6-sol | xinjianya.key |
| **glm2api** | glm-5.3 | lokal, Port 8001, kein Key |
| **antigravity** | claude-opus-4-6 (100k Context, Thinking 1k/4k/8k), gemini-3.8-flash (1M, 64k Output, fest auf High-Thinking gemappt) | lokal, Port 9878, Google Cloud Code OAuth |

- `mcp.opencode-sessions`: Session-Verwaltung direkt auf der SQLite-DB
  (`infra/mcp/opencode-sessions-mcp.js`, zero deps) — list/preview/delete/search,
  kaskadierende Löschung + Orphan-Event-Cleanup, schützt aktive/aktuelle/geteilte
  Sessions, `confirm:true` Pflicht. Details: `infra/mcp/README.md`.
- `agent/glm2api.md`: Arbeits-Subagent fest auf `glm2api/glm-5.3` (Haupt-Proxy).
- `tui.json`: Maus-Capture **aus** (`mouse: false` ist Absicht — xterm.js
  übersetzt dann das Mausrad in `up`/`down`, die auf halben Seitenwechsel
  gemappt sind. **Nicht auf `true` ändern.**)

## glm2api — der LLM-Haupt-Proxy (Port 8001)

Chatglm.cn-Reverse (Python-Standardbibliothek-HTTP, Gast-Token-Pool: 100 Slots,
Auto-Refetch + 10 Retries), OpenAI-kompatibel. Gewinner des 3-Wege-Agenten-
Benchmarks (2026-09-06): als einziger Proxy 2/2 SWE-Tasks **vollautonom in je
1 Run** (35+ Tool-Executions, 0 Abbrüche). hellogml (Guest-Token-Erschöpfung
bei Lang-Runs) und chat2api (Markup-Fragilität bei Agent-Loops) wurden daraufhin
komplett entfernt — glm2api ist der verlässliche Agent-Proxy.

**Sicherheits- und Betriebsverträge:**
- **Bindung/Auth:** Loopback-Bindungen (`127.0.0.1`, `localhost`, `::1`) dürfen ohne API-Key laufen. Jede andere `HOST`-Bindung startet nur mit nichtleerem `SERVER_API_KEYS`; der Token-Vergleich ist constant-time. CORS `*` ist ausschließlich für Loopback erlaubt, ein leerer CORS-Wert sendet keinen Allow-Origin-Header. Sind Keys gesetzt, sind auch Health-/Models-Endpunkte geschützt.
- **Ingress:** HTTP/1.1-POST benötigt genau einen gültigen `Content-Length`; fehlend → `411`, ungültig → `400`, über dem Limit → `413`, `Transfer-Encoding` → `501`. Der Body-Limit-Default ist 32 MiB (`MAX_REQUEST_BODY_BYTES`, hart maximal 128 MiB); frühe Fehler schließen die Keep-alive-Verbindung. Handler-Socket-Timeout: 30 s (maximal 300 s), Request-Line standardmäßig 8192 Byte (maximal 64 KiB), 64 Header (maximal 100), Header-Daten maximal 64 KiB (maximal 1 MiB), maximal 32 aktive Verbindungen (maximal 128) und Listen-Queue 32 (maximal 128).
- **Upstream:** `GLM_BASE_URL` muss HTTPS verwenden; Klartext-HTTP ist nur für `127.0.0.1`/`localhost` (einschließlich `::1`) erlaubt. Upstream-Transportfehler werden nicht als Client-Disconnect behandelt und öffentlich nur generisch gemeldet.
- **Logs:** `GLM2API_LOG_DIR` (Default `log`) wird mit `0700` angelegt bzw. erzwungen; Debug-Log und Rotationsdateien erhalten `0600`. `Authorization`, `x-api-key`, `Cookie` und `api-key` werden in Header-Dumps und Request-Logs redigiert.
- **Budgets:** Request- und Queue-Timeouts, Upstream-Timeouts, Concurrency sowie Retry-/Follow-up-Zähler werden aus der Config geladen und durch harte Obergrenzen begrenzt (u.a. Concurrency 32, Queue-/Request-Timeout 900 s). Upstream-Code `10061` wird nach Meldungstext in zwei Budgets getrennt: Nebenlauf-Busy (`请等待其他对话生成完毕`, `GLM_BUSY_MAX_RETRIES`/`_INTERVAL_SECONDS`) und Konto-Drosselung (`请求过于频繁`, `GLM_RATE_LIMIT_MAX_RETRIES`/`_INTERVAL_SECONDS`, Default 2 Versuche ab 30 s) — eine Drosselung ist bewusst **nicht** transient und endet in HTTP 429 an den Client, statt das Upstream weiterzufeuern.

**Wiederaufbau im frischen Codespace:**

```
./llm-proxies/rebuild.sh            # .env + venv vorbereiten (Sekunden)
./llm-proxies/scripts/start-glm2api.sh   # starten (uv run)
```

**Portables Bundle (anderer Rechner/Umgebung):**

```
./llm-proxies/scripts/build-bundle.sh    # baut dist/glm2api-bundle.zip
# drin: app/ (Code+Tests+Config, kanonischer Source), scripts/install.sh+start.sh
# (relative Pfade), docs/ (chat_mode-Reverse-Engineering)
# Ziel: entpacken → bash scripts/install.sh → bash scripts/start.sh (Port 8001)
```

**Bundle-Refresh (immer aktuell halten):** `build-bundle.sh` baut das
`dist/glm2api-bundle.zip` aus dem aktuellen Source neu. Der Builder kopiert
Source und Tests und prüft die Produktionsdateien byteweise sowie die
Testdateinamen; Testinhalte, Metadaten und ein vollständiger Commit-Fingerprint
werden nicht geprüft. Das getrackte Bundle kann daher trotz Verifikation
veraltet sein. Nach jeder glm2api-Code-Änderung neu bauen und die sechs
aktuell bekannten Drift-Member separat prüfen.

**100 %-Wiederherstellung:** Der Proxy-Code lebt komplett in MAIN — nach
einem Codespace-Wechsel macht setup.sh automatisch: uv-Install (falls nötig),
`.env` aus `glm2api.env` (Port 8001, Guest-Mode, secret-frei), `uv sync`
(venv), Start. Kein Klon, kein Patch-Anwenden, keine externen Abhängigkeiten.
- Tool-Protokoll: von DSML-Markup auf JSON+`[]`-Terminator umgestellt (+ DSML/
  Mashup-Fallbacks, Part-Merge-Fix — chatglm.cn streamt erst Token-Schnipsel,
  dann Volltext; Fix = anhängen + idempotent ersetzen statt blind
  überschreiben). Direkt im Source eingearbeitet — der kanonische Code liegt
  im Repo (kein Patch-Artefakt mehr).
- setup.sh rebuilt nur bei `LANDSCAPE_REBUILD_LLM_PROXIES=1` (sonst manuell).
- Upstream-Limit ist pro Guest-Token (~5 Nachrichten) — der Pool rotiert das weg.

## Antigravity Quota-Architektur & Token-Multiplikator (Befunde)

### 1. Dual-Bucket Quota-Architektur bei Google Antigravity
Google teilt Modelle in zwei getrennte Pools ein:
- **`Gemini Models`** (`gemini-3.8-flash`, `gemini-pro`, `gemini-flash-lite` etc.)
- **`Claude and GPT models`** (`claude-opus-4-6`, `claude-sonnet-4-6`, `gpt-oss-120b` etc.)

Jeder Pool besitzt zwei voneinander unabhängige Kontingente:
1. **5-Stunden-Sprint (`window: "5h"`):** Glättet globale Lastspitzen; setzt sich alle 5 Stunden wieder auf 100% zurück.
2. **Wochen-Limit (`window: "weekly"`):** Das harte vertragliche Tier-Kontingent; setzt sich erst nach 7 Tagen zurück (Rolling-Window).

**Kanonischer Endpunkt:**
`POST https://daily-cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary`
Liefert die vollständige 2×2-Matrix (beide Fenster mit Restquoten `remainingFraction` und sekundengenauem `resetTime`).
*Hinweis:* Der bisherige Endpunkt `fetchAvailableModels` liefert pro Modell nur ein einzelnes `quotaInfo` (das jeweils restriktivste), was dazu führte, dass das Claude-Wochenlimit irrtümlich als 5h-Sprint interpretiert wurde.

### 2. Der Claude/Opus Token-Multiplikator in Tool-Loops (Befund)
In langen Konversationen kann ein einzelner, scheinbar harmloser Prompt in kürzester Zeit hunderttausende Tokens verbrennen:
- **Live-Messung 1:** Ein Folge-Prompt (*„ist das dokumentiert?“*) in einer Session mit ~32k Historie führte zu 7 Tool-Calls à ~50k Kontext = **333.905 Input-Tokens in 57 Sekunden**.
- **Live-Messung 2:** Ein Folge-Prompt in einer Session mit ~52k Historie führte zu 10 Tool-Calls à ~52k Kontext = **523.966 Input-Tokens in 48 Sekunden** (-18% im 5h-Sprint, -6% im Wochenlimit).
- **Ursache:** Agenten-Frameworks wie opencode senden bei **jedem einzelnen Tool-Call in einer Kette die vollständige bisherige Konversationshistorie** erneut an das Modell.
- **Thinking-Budget-Overhead:** `antigravity-proxy` erzwang bei `claude-opus-4-6-thinking` standardmäßig ein `thinkingBudget: 8192`. Dadurch fielen bei jedem Zwischenschritt bis zu 8k Output-Tokens an.

### 3. Implementierte Gegenmaßnahmen für Claude/Opus
1. **Aktueller OpenCode-Kontextvertrag:** `.opencode/opencode.json` setzt
   `claude-opus-4-6` auf 100.000 Context- und 16.384 Output-Tokens; Sonnet ist
   nicht mehr als aktives Modell konfiguriert. Gemini behält 1.000.000 Context-
   Tokens. Die frühere 75.000/75000er Darstellung ist historisch.
2. **Thinking-Budget neu kalibriert (Proxy-Ebene):**
   In `llm-proxies/antigravity-proxy` wurde `ensureAntigravityThinkingDefaults` für Claude neu gestaffelt:
   - `none` / `off`: `budget = 0` (Thinking komplett aus, `ThinkingConfig: nil`)
   - `low` / `minimal`: `budget = 1024` Tokens
   - `medium` (Default): `budget = 2048` Tokens (ausgewogener Sweet-Spot)
   - `high`: `budget = 4096` Tokens (hartes Limit, der 8.192-Overkill ist deaktiviert)
   In `.opencode/opencode.json` sind alle 4 Varianten (`none`, `low`, `medium`, `high`) wählbar,
   Default steht auf `medium`.
3. **Session-Hygiene:**
   In langen Sessions (>40k Tokens) keine kurzen Nachfragen stellen, sondern `/new` oder `/compact` nutzen.

## Infrastruktur-Soll (Details Betrieb)

- **Kanonisch ist:** gepinnte Version im Repo + reproduzierbares Skript.
  PID-/Port-Ausgaben sind ephemeral — vor Wiederverwendung einmal prüfen
  (`pgrep`, `ss`, `curl`), nie als Blocker oder Dauerzustand dokumentieren.
- **Kanonische Codespace-Ports (4 Dienste):** Port `4096` (opencode-Server), Port `6082` (noVNC Browser), Port `8001` (glm2api-Proxy), Port `9878` (antigravity-proxy). In `.devcontainer/devcontainer.json` und `.vscode/settings.json` via `forwardPorts` + `portsAttributes` + `remote.autoForwardPorts: true` + `remote.autoForwardPortsSource: "process"` und `remote.restoreForwardedPorts: false` verdrahtet: Die 4 Dauer-Dienste bleiben permanent geforwarded; neue temporäre Dev-Server (z.B. Web-Apps auf 3000/5173) werden während ihrer aktiven Laufzeit automatisch erkannt und nach Prozessende sofort wieder sauber aus dem Ports-Panel entfernt. Interne Sockets (2000, 5900, 5920) werden ignoriert.
- **Bindung der LLM-Proxies:** beide Proxys laufen **ausschließlich auf Loopback** —
  glm2api auf `127.0.0.1:8001`, antigravity auf `127.0.0.1:9878`. Das Codespace-
  Port-Forwarding funktioniert über Loopback genauso, aber die Proxys sind so
  nicht aus dem Netz erreichbar. Upstream band der antigravity hardcoded auf
  `":" + port` (alle Interfaces); `cmd/antigravity-oauth-proxy/main.go` liest
  deshalb jetzt `HOST` (Default `127.0.0.1`, `*` bewusst wieder auf 0.0.0.0),
  und `scripts/start.sh` setzt `HOST` explizit. `start.sh` prüft die tatsächliche
  Bindung nach dem Health-Check per `ss` und warnt bei Abweichung — ein
  erfolgreicher Health-Check beweist nichts über die Erreichbarkeit.
- **Browser-Runtime:** **Firefox** (Mozilla-Tarball, Version gepinnt in
  `infra/scripts/firefox-install.sh`, Install nach `.runtime/firefox`, gitignored)
  → `./infra/scripts/browser-start.sh [URL]` (Xvfb, x11vnc, noVNC; idempotent).
  Dienste: Display `:120`, VNC `localhost:5920`, noVNC Port `6082`.
  Profil `.runtime/firefox-profile/` enthält evtl. Logins — nie committen.
- **Systempakete** via setup.sh (idempotent): nodejs, npm, xvfb, x11vnc, novnc,
  websockify, sqlite3, dbus-x11, build-essential, python3-* etc.
- **opencode ist gepinnt, mit EINER Quelle der Wahrheit:** dem
  `@opencode-ai/plugin`-Dep in `.opencode/package.json`. Das ist genau die Version,
  die opencode für seinen Plugin-Ladepfad selbst nachinstalliert — deshalb ist der
  Pin auch der richtige: laufen beide auseinander, schreibt opencode den Dep beim
  ersten TUI-Start um und der Codespace hinterlässt dauerhaft uncommittete
  Änderungen. `.devcontainer/setup.sh` liest die Version von dort und installiert
  genau sie (`opencode.ai/install --version`); weicht die vorhandene Installation
  ab, aktualisiert setup.sh (Vergleich über `opencode-bin`, weil der
  Multi-Client-Wrapper `opencode` ersetzt). **Pin wechseln:**
  `./infra/scripts/opencode-version.sh bump` (Alias `ocver`) — updated Pin **und**
  Lock in einem Schritt, ein Commit. `ocver check` zeigt Repo-Pin / Lock /
  installiert / Latest und ein Urteil; `ocver latest` nur die neueste Release.
  Bewusst **kein** Auto-Tracking: ein automatisch nachgeführter Pin würde bei jedem
  Release das Repo verändern und über den Autosave-Daemon die Historie
  beschreiben. Ein Codespace, ein Build — der laufende Server nutzt bis zum
  Neustart seine alte Version.
- **Git-Identität folgt dem Account** (siehe Secrets-/Auth-Abschnitt): `auth.sh
  setup` leitet Name + `<id>+<login>@users.noreply.github.com` aus dem Token ab und
  setzt sie **repo-lokal**; `auth.sh identity` zeigt sie. Beim Account-Wechsel
  damit nichts zu tun. `store_token` überschreibt einen funktionierenden Token
  **nicht** mit einem, der sich nicht auflösen lässt (Tippfehler ⇒ Push tot bis
  zum nächsten Codespace). Override: `GIT_USER_NAME=… GIT_USER_EMAIL=… auth.sh setup`
  — nur mit Bedacht, MAIN ist öffentlich und eine echte Adresse landet mit im Commit.
- **Go-Toolchain:** Go 1.25.7 (gepinnt, entspricht `mise.toml` im antigravity-proxy)
  nach `/usr/local/go` via setup.sh — das Proxy-Binary liegt nicht im Git und wird
  pro Codespace neu gebaut (`scripts/start.sh` baut automatisch nach, Fallback
  `/usr/local/go/bin/go`). PATH via `aliases.sh`.
- **Deprecated (gelöscht 2026-09-10):** kompletter Chromium-Stack entfernt
  (`infra/browser/` Playwright 1.48.2, `.runtime/ms-playwright/`,
  `.runtime/chromium-profile/`, `browser-install.sh`, CDP-Port 9222).
  Rückweg: Commit revertieren — bzw. für Chromium-CDP: Playwright-Setup neu
  anlegen.

## Google-Drive-Backup (Repo-Sicherung unabhängig von GitHub)

Szenario: GitHub-Account wird gebannt / Repo geschlossen → komplettes Repo
(inkl. History, aller Branches) liegt dann als git-bundle auf Google Drive
(5 TB, Google AI Pro). **GitHub-Actions bewusst nicht genutzt** — läuft bei
Bann nicht mehr, genau dann wird das Backup gebraucht.

- **`infra/scripts/gdrive-backup.sh`** (`gdrive backup|status|restore [dir]`,
  Alias `gdrive`): baut `git bundle --all` (~110 MB), Rotation nach
  2-Generationen-Schema — (1) altes `MAIN.backup.bundle` löschen, (2)
  `MAIN.bundle` → `MAIN.backup.bundle` umbenennen, (3) frisches Bundle
  hochladen, (4) MD5-Verifikation remote vs. lokal. Bricht der Upload ab,
  bleibt die Backup-Generation intakt → immer mindestens eine
  funktionsfähige Kopie auf Drive. Restore: `gdrive restore` klont aus der
   Backup-Generation (Fallback current). Skip wenn kein neuer Commit seit
   letztem Backup (State-File `.runtime/gdrive-backup.last`).
- **Keine Drosselung — bewusst.** Ein Zeitintervall zwischen den Backups wurde
  implementiert und wieder verworfen. Das Bundle ist ~111 MB; der Upload dauerte
  gemessen zwischen **5,3 s und 40 s** (≈21 MB/s bis ≈5,5 MB/s, je nach
  Codespace-Netz) — also Schwankung, keine Google-Drosselung, und in der
  schnellsten Variante vernachlässigbar. Zwei parallele Uploads zusammen
  kamen nur auf ~5,5 MB/s gesamt, es ist also eine Gesamt-Bandbreite-Begrenzung
  der Codespace-Egress, die sich mit Parallelität nicht umgehen lässt. Weder
  Speicher noch Bandbreite sind der Engpass: Drive meldet 5 TiB, davon
  4,988 TiB frei, belegt sind zwei Bundle-Generationen (~222 MB).
  Der maßgebliche Grund für den Verzicht ist ohnehin nicht die Zeit: Der
  Schutzzweck ist Account-Bann ODER Repo-Löschung, und dann zählt nicht
  Traffic, sondern Aktualität. Ein Backup, das 6 h alt ist, verliert im
  Worst Case (GitHub-Account gebannt UND Codespace im selben Fenster verloren)
  bis zu 6 h Commits unwiederbringlich, weil der Codespace selbst ephemer ist.
  Das ist echter Datenverlust, kein Tuning. Also: **voller Upload bei jedem
  Save mit neuem Commit.**
  **Offen und wichtiger als jede Optimierung:** rclone nutzt einen *geteilten*
  Google-`client_id`, den Google 2026 abschaltet. Dann bricht das Backup aus —
  und weil `save.sh` den Hook mit `|| true` aufruft (damit ein Push nie
  scheitert), bliebe das unbemerkt. Eigener `client_id` ist der Pfad.
- **Trigger:** `save.sh` ruft nach jedem erfolgreichen Push den Backup-Hook
  auf — damit sichert auch der Autosave-Daemon (alle 30 Min) automatisch nach
  Drive. Fehlt die rclone-Auth, überspringt sich der Hook selbst (Push-Erfolg
  wird nie gefährdet).
- **rclone** v1.75.1 (gepinnt): `infra/scripts/rclone-install.sh`, automatisch
  via `setup.sh` nach `/usr/local/bin` (ephemeral, wird je Codespace neu
  installiert).
- **Auth:** OAuth-Refresh-Token in `~/.config/rclone/rclone.conf`, im
  Secrets-Bundle (`rclone.conf`) mitgeschleift. **Bewusst NICHT
  `~/.config/landscape/`** — dort werden `refresh_token`s von einem
  Sanitizer aus Dateien entfernt (2026-09-11 2x beobachtet: 333→212 Bytes
  nach cp); `~/.config/rclone/` bleibt unangetastet. Gotcha bei der
  Einrichtung: rclone verwirft den refresh_token beim Config-Save wenn
  `access_token` leer ist — Token-Paste immer mit vollem access_token
  (`rclone authorize "drive"` im noVNC-Firefox, siehe unten).
- **Erst-Einrichtung (neu/erneuert):** `rclone authorize "drive"` im
  Hintergrund starten (lauscht 127.0.0.1:53682), Firefox via
  `browser-start.sh "<auth-url>"` auf die state-URL schicken, im noVNC
  (Port 6082) Google-Login + Zugriff erlauben, dann das Token-JSON aus dem
  Log als `token = {...}` in `~/.config/rclone/rclone.conf` (Remote `gdrive`,
  type drive, scope drive) und `secrets.sh lock`.
- Remote-Layout: `gdrive:MAIN-backup/` mit `MAIN.bundle` (aktuell) +
  `MAIN.backup.bundle` (vorherige Generation).

## Account-Wechsel (60h-Limit)

Ein Codespace gehört zu Account+Repo+Branch, nicht übertragbar. Mitkommt 1:1
alles gepushte. Im alten Codespace: `./infra/scripts/save.sh` (+ ggf.
`./infra/scripts/secrets.sh lock`). Im neuen: Repo forken, Codespace bauen —
Rest automatisch; einmalig `LANDSCAPE_PAT` (+ optional `LANDSCAPE_PASSPHRASE`)
als Codespaces-Secrets. Nicht mitkommen, aber rekonstruierbar: Browser-Profil, Ports.
glm2api selbst kommt komplett mit (Code im Repo).

## Codespace-Lifecycle — wann welcher Mechanismus greift

| Event | Mechanismus | Wirkung |
|---|---|---|
| Codespace-**Neuerstellung** (Rebuild) | `postCreateCommand` → `setup.sh` | Voll-Setup: Pakete, opencode, uv, Secrets-Unlock, Git-Auth, Browser, MCP-Registrierung, Proxy-Rebuild + Start |
| Codespace-**Resume** (Stopp→Start, Idle/Über Nacht) | `postStartCommand` → `start-on-boot.sh` | Proxy-Health-Check; läuft er nicht → Start (Code/venv/.env überleben in MAIN). Bei Unvollständigkeit: Hintergrund-Rebuild (Log `/tmp/opencode/boot-rebuild.log`) |
| **Client-Reconnect** (Browser-Reconnect ohne Container-Restart) | **`proxy-watchdog.sh`** (Daemon, 30s-Intervall) | postStartCommand läuft NICHT bei Reconnect — der Watchdog hält den Proxy trotzdem am Leben (auch nach OOM-Kill). Start via start-on-boot.sh, Lockfile `/tmp/opencode/proxy-watchdog.lock`, Log `/tmp/opencode/watchdog.log` |
| Laufzeit | `start-glm2api.sh` idempotent | Doppelstart-sicher, Port-Check |
| **Idle-Schutz** (offene Commits vor Shutdown sichern) | **`autosave-daemon.sh`** (Daemon, 30-Min-Intervall) | Alle 30 Min: prüft auf uncommittete Änderungen oder ungepushte Commits → `save.sh` (add -A, commit, pull --rebase, push). Kein leerer Commit-Spam. Start via start-on-boot.sh + setup.sh, Lockfile `/tmp/opencode/autosave-daemon.lock`, Log `/tmp/opencode/autosave.log`. Shell: `autosave {status|start|stop|log}` |
| **Config-Auto-Restart** (neue Modelle sofort verfügbar) | **`config-watchdog.sh`** (Daemon, inotify-Event-basiert) | Überwacht `.opencode/opencode.json` per `inotifywait` (close_write/moved_to) auf dem **Verzeichnis**; **Hash-Vergleich** nach jedem Event, damit Schreibvorgänge auf anderen Dateien im Ordner (`tui.json`, `package-lock.json`, neue `agent/*.md`) keinen Restart auslösen; Debounce 8s + **Busy-Guard** (prüft `/session/status`, wartet bis alle Sessions idle sind vor Restart, kein Abbruch laufender Turns) + Pause-Mechanismus (`config-watchdog.pause`). Fallback auf Polling (10s md5sum) falls inotify-tools fehlt. Start via start-on-boot.sh + setup.sh, Lockfile `/tmp/opencode/config-watchdog.lock`, Log `/tmp/opencode/config-watchdog.log`. Shell: `config-watchdog {status|start|stop|pause|resume|log}` |

**Proxy-Verhalten nach Stopp:** Prozesse sterben, `/tmp` (Logs) wird geleert —
Code, venv und .env in MAIN überleben alles. Der Boot-Mechanismus zieht den
Proxy bei jedem Start automatisch hoch.

## Changelog

- 2026-09-26: **Versionsdrift gelöst (eine Quelle der Wahrheit) + Git-Identität folgt dem Account.** Aufbauend auf dem Infra-Check: Ein gepinnter opencode allein löst das Problem nicht — das eigentliche Problem sind **zwei Zahlen für dieselbe Sache** (Pin im Skript *und* Plugin-Dep im Repo). Dazu die Beobachtung, dass **opencode den `@opencode-ai/plugin`-Dep in der Version nachinstalliert, die es selbst hat**: laufen installierte Version und Dep auseinander, schreibt opencode beim ersten TUI-Start in `.opencode/package.json` + `package-lock.json` um, der Autosave-Daemon committet das, und der nächste Codespace macht es wieder. **Deshalb ist der Plugin-Dep selbst der Pin**, und `.devcontainer/setup.sh` liest die Version von dort — keine zweite Zahl, die veralten kann. Nachweis der Schreibstelle (Zeitstempel): 16:46:40 `opencode serve` gestartet → 16:47:51/56 zwei `opencode attach` → 16:48:08 `node_modules/@opencode-ai/plugin` angelegt → 16:48:15 `package.json` + Lock umgeschrieben. **Einschränkung, bewusst nicht überinterpretiert:** der Server allein und `opencode run` reproduzieren den Rewrite **nicht** — zwei Gegenproben mit absichtlich falschem Dep: nur der TUI-Pfad legte `node_modules` neu an, ohne den Dep zu korrigieren. Der Schreibvorgang ist also an den TUI-Client gebunden und nicht in jedem Fall reproduzierbar. Die Invariante „Pin == Dep == installierte Version" ist trotzdem die richtige, weil sie den Angriffspfad (TUI-Start) eliminiert statt ihn zu bekämpfen. Neu: `infra/scripts/opencode-version.sh` (Alias `ocver`) mit `check` (Repo-Pin / Lock / installiert / Latest + Urteil), `latest`, `bump [VERSION]` (Pin **und** Lock in einem Schritt) und `install` (lokales opencode auf den Pin bringen, brennt Tokens). Der Lock wird bewusst per `npm install --package-lock-only` neu berechnet statt handeditiert, weil nur npm den transitiven Baum korrekt zieht (eine opencode-Version kann auch `@ai-sdk/provider` mitziehen); Nebenwirkung des System-npm 9.2.0: es schreibt keine `"license"`-Felder, der Diff zeigt dann ~8 entfernte Zeilen — kosmetisch, Versionen und `integrity` bleiben identisch. **Kein Auto-Tracking**, bewusst: es würde bei jedem Release das Repo verändern und die Historie beschreiben; ein Upgradeschritt ist ein Commit. Verifiziert: `ocver check` meldet „Alles konsistent", `bump 1.18.30` und zurück auf 1.18.32 lieferten einen exakten Round-Trip, beide Branches von `setup.sh` getestet (Pin stimmt → kein Reinstall; Abweichung → Update-Zweig). **(2) Git-Identität an den Account gebunden:** nach einem Account-Wechsel standen die Commits weiter auf dem alten Account, weil `git config user.*` lokal erhalten blieb und sich nie mit dem Token abgleichte. `auth.sh setup` leitet jetzt Name + `<id>+<login>@users.noreply.github.com` aus dem Token ab und setzt sie **repo-lokal** (ein Codespace, ein Account, kein globaler Zustand); `auth.sh identity` zeigt sie, `auth.sh status` eine Zeile mit. `noreply` ist Default, weil MAIN **öffentlich** ist und eine echte Adresse sonst mit in der Historie landet; Override via `GIT_USER_NAME`/`GIT_USER_EMAIL`. **Dabei gefunden und behoben:** `store_token` überschrieb einen funktionierenden Token mit einem, der sich nicht auflösen lässt — ein Tippfehler in der PAT hätte jeden Push bis zum nächsten Codespace getötet (live nachgestellt: ABBRUCH, Token und Push-Test unverändert). Ein ungültiger Token lässt die Identität unangetastet, offline ebenfalls.

- 2026-09-26: **opencode war ungepinnt — Codespace bekam eine andere Version als das Repo; `keys.sh doctor` meldete funktionierende Keys als tot.** Befund aus dem Infra-Check eines **frischen Codespaces nach Account-Bann** (der neue Account ist Kollaborator mit Push auf `ChatMCPConnector/MAIN`, Bundle-PAT + `LANDSCAPE_PAT` gehören ihm, Push-/Secrets-/Proxy-/Backup-Pfad lief vollständig automatisch hoch). Zwei echte Mängel: (a) `setup.sh` installierte opencode mit `curl -fsSL https://opencode.ai/install | bash` — **floating, ohne Pin**, obwohl das Repo-Soll „gepinnte Version im Repo + reproduzierbares Skript" verlangt. Folge: Der frische Codespace bekam 1.18.32, das Repo pinnte im `@opencode-ai/plugin`-Dep noch 1.18.30, und der erste TUI-Start schrieb den Dep eigenmächtig auf 1.18.32 um — dauerhaft uncommitteter Churn in `.opencode/package.json` + Lock, den der Autosave-Daemon regelmäßig mitcommittete. Fix: `OPENCODE_VERSION="1.18.32"` in `setup.sh`, Installation via `--version`; das Skript ermittelt die vorhandene Version (auch über den schon umbenannten `opencode-bin`, weil der Multi-Client-Wrapper `opencode` ersetzt) und aktualisiert nur bei Abweichung vom Pin. Release + Asset verifiziert. **Der hier eingebaute `OPENCODE_VERSION`-Pin ist im Eintrag darüber ersetzt** — der `@opencode-ai/plugin`-Dep ist die einzige Quelle, ein Bump geht über `ocver bump`. (b) `keys.sh doctor` meldete **beide** Provider als unbrauchbar, obwohl beide funktionieren: nvidia mit `TIMEOUT/KEIN KONTAKT`, weil der 90-s-Timeout unter dem echten Kaltstart liegt (live gemessen: **91 s** bis zur Antwort, ein früherer Durchlauf 57 s — der Upstream-Wärmestand schwankt); xinjianya mit `CLOUDFLARE (403)`, was die Doku als bekannten Fehlalarm kannte, dessen Meldung aber selbst falsch war: sie behauptete, der Bot-Schutz blockiere „den Weg, den auch opencode nimmt" — live geprüft ist das Gegenteil, Cloudflare filtert den TLS-Fingerprint von `curl`, der Key funktioniert (`opencode run --model xinjianya/gpt-5.6-sol` → `OK`). Fix: `PROBE_TIMEOUT_SECONDS=180` als Konstante (doctor ist Diagnose, ein Fehlalarm „Provider tot" ist teurer als Warten), Timeout-Text nennt die echte Schwelle, und die Cloudflare-Meldung nennt `opencode run` als den einzigen beweisenden Test. Verifiziert: `doctor` meldet danach `nvidia OK (HTTP 200)`, Syntax beider Skripte ok, Pin-Vergleich in beide Richtungen getestet (Pin stimmt → kein Reinstall; Abweichung → Update-Zweig). **Die Git-Identität stand nach dem Account-Wechsel noch auf dem alten Account** (`tadeeussus1`/gmail) — sie wird im Eintrag darüber systematisch aus dem Token abgeleitet. **Hinweis für den Account-Wechsel (nicht automatisch lösbar):** das Codespaces-Secret `LANDSCAPE_PASSPHRASE` enthielt erneut den **PAT** statt des Passphrasen-Inhalts — genau der Fehler aus dem Changelog-Eintrag weiter unten. Harmlos geblieben, weil `secrets.sh` PAT-Kandidaten verwirft und `config/passphrase` (40 B, im Repo) entschlüsselt; das Secret muss trotzdem auf diesen Inhalt gesetzt werden. **Nebenbefund:** `glm2api.md` (Tracker „Offene Punkte", Status *beide Punkte geschlossen*) wurde am selben Tag über die GitHub-Web/API mit entfernt — die Changelog-Einträge verweisen noch darauf, der Inhalt liegt nur noch in der Historie (`git show 2952c2b:glm2api.md`).

- 2026-09-26: **glm2api: der Loop-Guard war für das Modell unsichtbar — daher die erfundenen „Tool-Limit"-Abbruchgründe (T-25).** Aus der Session `ses_f21fbf23…`: das Modell rief **10× in einem Turn** `open` mit identischem Ziel `/workspaces/MAIN/glm2api` (Proxy-Log: 8× `Dropped identical native tool_call (loop guard) repeats=2`, 2× durchgelassen). Es sah 10 Calls und 2 Ergebnisse, schloss daraus auf **„Tool-Limit (8/8 Runden) erreicht"**, brach ab und verlangte einen Neustart. **Korrektur der früheren Diagnose:** `open` wird nicht verworfen — `map_native_open_tool_call` (`translator.py:804`) schreibt es auf `read`/`webfetch`/`bash` um (Pfad→`read`, URL→`webfetch`, `command`→`bash`); verworfen wird nur, was nicht abbildbar ist. Der Pfad war falsch (`llm-proxies/glm2api`, nicht `MAIN/glm2api`), opencode meldete „File not found" **mit** dem richtigen Vorschlag, und das Modell wiederholte denselben Call statt das Argument zu korrigieren. Der Kern: der Guard hat ohne jede Rückmeldung verworfen, das Modell hatte **kein Signal** und erfand eine Begründung. Fix: der Accumulator zählt die Drops (`loop_guard_dropped_count`/`_tools`, der **native** Name wird gemerkt, nicht der gemappte — sonst sucht das Modell den Fehler im falschen Werkzeug), und Client wie Antwortstrom erhalten eine `[loop_guard_notice]`: Anzahl, native Tool-Namen, explizit „there is NO tool limit or round limit", Hinweis auf das bereits vorliegende Ergebnis und auf das Korrigieren des Arguments. Der Non-Stream-Pfad hat **zwei** Returns (terminaler Status und abgeschnittener Turn) — beide werden injiziert, gerade der abgeschnittene Fall ist der, in dem die Erklärung am meisten fehlt. Dabei gefunden und behoben: der Guard-Notice fehlte zunächst an genau diesem zweiten Return. Agent-Prompt entsprechend korrigiert: `open` als nicht-deklariertes Werkzeug **mit** Remap-Hinweis (nicht als „existiert nicht" — das widersprach dem beobachteten Verhalten), „bei File-not-found den Pfad korrigieren, nicht wiederholen", und beide echten Rückmeldungen (`[blocked_tool_notice]`, `[loop_guard_notice]`) als Nicht-Limits benannt. Verifiziert: 532 Tests grün (12 neu in `tests/test_loop_guard_notice.py` — Guard-Verhalten, Notice-Text, Sichtbarkeit in Stream **und** Non-Stream, Gegenprobe ohne Drops), Live-Fall mit 10 Calls deterministisch nachgestellt (2 durch / 8 verworfen / Notice korrekt). Live über HTTP nicht erzwingbar: das Modell weigert sich, 10 identische Calls auf Kommando zu senden — der Guard ist genau dagegen.

- 2026-09-26: **glm2api: Tokenlimits angehoben (1M/131072) + `open`-Halluzination und erfundene „Tool-Limit"-Narrative im Agent-Prompt adressiert.** Aus einer realen Session (`ses_f220f960…`, Modell `glm2api/glm-5.3`) kamen drei Befunde: (a) Das Modell rief **11× ein Tool `open`** auf, das es nicht hat (Proxy-Log: `blocked=['open'×5]`, dann 3, dann 3). opencode hat nie eines bekommen — `open` steht in `BLOCKED_NATIVE_TOOL_NAMES` (`tool_protocol.py:9`) und wird immer verworfen. Die Korrektur-Runde greift nicht, weil sie nur feuert, wenn der Turn **keine** gültigen Calls enthält (`glm_client.py:655`); hier standen `open` neben echten Calls, es blieb bei der `[blocked_tool_notice]` im Text — die das Modell ignorierte. (b) Drei sinnlose `webfetch`: `https://glm2api.md` (lokale Datei als URL, 2× parallel), `https://example.com` und das Git-README von raw.githubusercontent.com. (c) **„Tool-Limit erreicht" war erfunden** — bei 1282 von 32768 erlaubten Output-Tokens, `finish` durchgehend `tool-calls`, nie `length`, Kontext-Peak 20973 von 128000. Das ist die in der Revision dokumentierte Modell-Restwirkung, keine Konfigurationsgrenze. Änderungen: `opencode.json` `glm2api/glm-5.3.limit` 128000/32768 → **1000000/131072** (deckungsgleich mit dem nvidia-Provider für dasselbe Modell); `GLM_MAX_OUTPUT_TOKENS` 32768 → 131072 (Maximum der Proxy-Schranke) und `GLM_HISTORY_MAX_CHARS` 120000 → 1000000 in `.env`, `.env.example`, `glm2api.env` — **beide Stellen müssen zusammen**, sonst kappt der Proxy bei seinem Wert ab (`min(client_max, glm_max_output_tokens)`, `glm_client.py:491`/`:793`). `GLM_HISTORY_MAX_CHARS=1000000` ist ausdrücklich **keine** 1M-Token-Garantie: chatglm.cn hat eine eigene, undokumentierte Obergrenze, und Code 10040 halbiert das Budget dann automatisch bis es passt (Minimum 20000). `.opencode/agent/glm2api.md` verschärft: explizit „es gibt KEIN `open`-Tool" mit der Werkzeugzuordnung (Dateien → `read`, URLs → `webfetch`, lokaler Pfad an `webfetch` = Transport-Error), Verbot von Probe-/Platzhalter-Fetches, Verbot paralleler Calls desselben Tools, und ein neuer Abschnitt gegen erfundene Abbruchgründe („es gibt kein Tool-Limit", niemals „Tool-Limit/Tokenlimit/Rundenlimit" schreiben, bei abgelehntem Call den Tool-Namen korrigieren statt aufzugeben). Verifiziert: 520 Tests grün, Live-Smoke 8/8 nach Proxy-Neustart, neue Config-Werte aus der laufenden `.env` gelesen (131072 / 1000000), `opencode.json` valides JSON. **Noch nicht aktiv:** der `config-watchdog` hat den `opencode.json`-Wechsel bemerkt und wartet im Busy-Guard auf eine freie Session, bevor er den opencode-Server neu startet — die neuen Limits und der Agent-Prompt gelten erst danach.

- 2026-09-26: **glm2api: Upstream-Code 10061 (Rate-Limit) wird nicht mehr mit dem Busy-Profil gehämmert (F-6).** Code `10061` trägt zwei Bedeutungen: `请等待其他对话生成完毕` = Nebenlauf-Busy (Web-Chat blockiert den Slot, in Sekunden weg) und `请求过于频繁` = Konto-Drosselung (klingt in Minuten ab). Beide liefen über denselben Pfad — HTTP 429 → `_should_retry_busy_error` → 30 Versuche im 2-s-Raster — und `10061` stand zusätzlich in `TRANSIENT_UPSTREAM_ERROR_CODES`, sodass auch der Stream-Retry (2×, 1 s) mitlief. Bei echter Drosselung feuerte der Proxy bis zu **30 Requests in ~4 Minuten auf ein bereits gedrosseltes Konto** und verlängerte die Sperre mit jedem Versuch. Fix: `10061` aus den transienten Codes entfernt (ein 10061 ist nur als Busy transient, eine Drosselung ist explizit **nicht** transient und löst keinen Stream-Retry mehr aus); neuer eigener Rate-Limit-Pfad in `send_request` mit eigenem Budget `GLM_RATE_LIMIT_MAX_RETRIES` (Default 2, max. 5) und Backoff `GLM_RATE_LIMIT_RETRY_INTERVAL_SECONDS` (Default 30 s → 60 s → 120 s, gedeckelt beim 8-fachen, Jitter nur nach oben, weil gleichzeitiges Aufwachen mehrerer Clients die Sperre am Laufen hält); nach erschöpftem Budget oder erreichter Request-Deadline geht ein **sauberer HTTP 429** an den Client (mitten im Stream als 429 statt 502). `_should_retry_busy_error` ist durch `_classify_upstream_throttle()` ersetzt, das nach Meldungstext klassifiziert (10061 ohne erkennbare Meldung = Ratelimit, der schädlichere Fehlerfall). **Unverändert:** der Nebenlauf-Busy behält 30 Versuche / 2-s-Basis / `transient=True`. Verifiziert: 520 Tests grün (493 + 27 neu in `tests/test_rate_limit_split.py`, inkl. Busy-Regressionstest und Backoff-Deckel), Live-Smoke-Test 8/8 nach Proxy-Neustart, Bundle neu gebaut und byte-identisch verifiziert. Betriebshinweis: Port 8001 ist die Modellversorgung der laufenden Session — ein Neustart unterbricht sie kurz (Watchdog, wenige Sekunden). Details in `glm2api.md`.

- 2026-09-26: **Drive-Backup-Drosselung verworfen (bewusste Entscheidung, nicht vergessen).** Zuerst umgesetzt: zeitbasierte Drosselung (Default 6 h). Zurückgenommen, weil der Schutzzweck Account-Bann/Repo-Löschung ist und dort nicht Traffic, sondern Aktualität zählt: Ein 6 h altes Bundle verliert im Worst Case (GitHub gebannt UND Codespace im selben Fenster weg — der Codespace ist selbst ephemer) bis zu 6 h Commits unwiederbringlich. Ein Mittelweg existiert nicht, ein git-bundle ist Alles-oder-nichts. Also: voller Upload bei jedem Save mit neuem Commit, wie vorher. **Die Begründung mit dem Traffic war allerdings falsch gemessen:** Ein 111-MB-Upload dauerte 5,3 s *und* 40 s in zwei Messungen (≈21 MB/s bis ≈5,5 MB/s), zwei parallele Uploads kamen zusammen nur auf ≈5,5 MB/s. Das ist Schwankung bzw. eine Gesamt-Egress-Begrenzung der Codespace, keine Google-Drosselung — und das Google-AI-Pro-Abo ändert daran nichts, es liefert Speicher (Drive meldet 5 TiB / 4,988 TiB frei) und Gemini-Zugang, keine Upload-Bandbreite. Die Drosselung wäre also auch zeitlich nie das Problem gewesen; der Datenverlust-Aspekt ist der einzige Grund. Die beiden anderen Optimierungen bleiben, weil sie ohne Nebenwirkung sind: (a) `config-watchdog.sh` verglich im inotify-Pfad — anders als der Polling-Fallback — **keinen Hash**; `inotifywait` überwacht das Verzeichnis `.opencode/`, wodurch jeder Write auf `tui.json`, `package-lock.json` oder eine neue `agent/*.md` 8 s Debounce plus opencode-Server-Neustart auslöste (mit Restsessions-Risiko). Jetzt Hash-Vergleich nach dem Event. (b) `secrets.sh unlock` entschlüsselte das Bundle zweimal — einmal beim Durchprobieren der Passphrase-Kandidaten, einmal für echt; `find_working_passphrase` hinterlässt das Tarball jetzt zur Wiederverwendung, `status` räumt es auf, damit kein Temp-Verzeichnis leakt. Nicht angefasst: `keys.sh ensure` im opencode-Wrapper (18 ms pro Start, unter der Messgrenze). Verifiziert: `tui.json`-Write löst keinen Restart mehr (Server-PID unverändert), Guard in 5 Logikfällen korrekt, `unlock` stellt den Key byte-identisch wieder her, keine Temp-Dirs danach.

- 2026-09-26: **rclone-Installation repariert, Drive-Backup lief ins Leere.** `rclone-install.sh` lädt von `downloads.rclone.org/rclone-v<VER>-linux-amd64.zip`; rclone hat sein URL-Schema geändert, die Dateien liegen jetzt unter `downloads.rclone.org/v<VER>/`. Der alte flache Pfad liefert 404, das Skript bricht mit `set -e` ab, `setup.sh` schluckt den Fehler (`>/dev/null 2>&1`) — Ergebnis: `rclone` fehlt, und `gdrive-backup.sh` meldete dann irreführend „Remote 'gdrive' fehlt" statt „rclone fehlt". Der Pfad ist korrigiert, `gdrive-backup.sh` prüft das Binary jetzt getrennt vom Remote, Upload auf `gdrive:MAIN-backup/MAIN.bundle` verifiziert wieder. **Offen:** rclone warnt, dass der gemeinsam genutzte Google-Drive-`client_id` 2026 abgeschaltet wird — für den Drive-Backup braucht es einen eigenen `client_id` (siehe `https://rclone.org/drive/#making-your-own-client-id`, Token-Austausch über das eigene Konto).

- 2026-09-26: **antigravity-proxy bindet jetzt auf Loopback statt auf alle Interfaces.** Upstream startet den Server fest mit `srv.Start(":" + port)`, also `0.0.0.0:9878` — im Codespace damit aus dem Netz erreichbar, obwohl das Token im Klartext in `opencode.json` steht und `infrastructure.md` für die Proxys durchgehend Loopback vorsieht. `cmd/antigravity-oauth-proxy/main.go` liest jetzt `HOST` (Default `127.0.0.1`, via `net.JoinHostPort`, `*` bewusst weiterhin 0.0.0.0) und loggt die Bind-Adresse; `scripts/start.sh` setzt `HOST` explizit und prüft die Bindung nach dem Health-Check per `ss` (der Health-Check allein beweist die Bindung nicht). glm2api war schon korrekt auf `127.0.0.1`. Verifiziert: von außen (`10.0.1.81:9878`) keine Verbindung, von loopback `/v1/models` 200 und `claude-opus-4-6` liefert „OK"; `go build` + `go test ./internal/...` grün. Das Binary liegt nicht im Git, nach dem Pull in einem bestehenden Codespace `scripts/stop.sh && scripts/start.sh` — der Proxy-Watchdog baut es sonst nicht neu.

- 2026-09-26: **opencode startet in neuen Codespaces wieder — Ursache war ein falsch befülltes Secret, nicht die Config.** `LANDSCAPE_PASSPHRASE` enthielt in einem Account den GitHub-PAT statt der Passphrase. `secrets.sh`nahm die Env-Variable blind als Passphrase, das Entschlüsseln schlug fehl, `~/.config/landscape/{nvidia-nim,xinjianya}.key` blieben aus — und weil `opencode.json` die Keys per `{file:…}` referenziert, verweigerte opencode den **komplett** Start (`bad file reference: … does not exist`). Drei Ebenen Fix: (a) `unlock` probiert alle Kandidaten durch (`LANDSCAPE_PASSPHRASE` → `config/passphrase` → Abfrage), verwirft PAT-ähnliche Werte und meldet PAT-Verdacht explizit; (b) neu `infra/scripts/keys.sh` (`ensure|status|doctor|restore`) — `ensure` legt referenzierte Key-Dateien als leere Platzhalter an, eingehängt in `setup.sh`, `opencode-server.sh` und den `opencode`-Wrapper, damit ein Secret-Problem nie wieder den Editor blockiert; (c) 0-Byte-Dateien gelten beim Unlock als „fehlt" (echter Key wird wiederhergestellt) und beim Lock als „nicht sichern" (Platzhalter überschreibt keinen Key). Nebenbefund zweier Bash-Fallen: ein `[ -n "$X" ] && …`-Statement unter `set -e` brach die Kandidatenliste ab, und `read` verwirft eine letzte Zeile ohne Newline — `config/passphrase` hat keins, die Passphrase wäre nie angekommen. `doctor` unterscheidet echte Auth-Fehler von einer Cloudflare-Challenge (xinjianya liefert 403-HTML für gut *und* schlecht) und nutzt 90 s Timeout, weil NIM Kaltstarts ~57 s braucht.

- 2026-09-25: **`glm2api.sh restart` repariert.** Die PID-Datei zeigt auf den `uv run`-Wrapper; ein TERM an den Wrapper beendet das Python-Kind nicht. Es hielt weiter Port 8001, der Restart brach mit „konnten nicht gestoppt werden" ab und der Server lief auf altem Code weiter. Beide Stop-Wege räumen jetzt verwaiste Kindprozesse mit Warte-Schleife und KILL-Eskalation ab; danach startet der Server wieder sauber und die PID-Datei wird wieder gesetzt.

- 2026-09-25: **glm2api-Port vereinheitlicht auf 8001.** Code-Default und `.env.example` sagten 8000, während der Betrieb (Start-/Restart-Skript, openode-Provider, Doku) auf 8001 lief — ein frisch geklonter Workspace wäre auf 8000 gestartet und hätte jeden Client und jedes Betriebsscript gebrochen. Default und Beispiel sind jetzt 8001, mit Test gegen beide.

- 2026-09-25: glm2api-Betriebsverträge: **Ausgabegrenze** `GLM_MAX_OUTPUT_TOKENS` (Default 16384, Cap 131072) — der Client-Wunsch `max_tokens` gilt, nie darüber hinaus; bei Erreichen `finish_reason: length`, unvollständige Tool-Calls werden verworfen. **Kein Gastkonto im Normalbetrieb:** ohne konfiguriertes Konto verweigert der Server den Start (Gastmodus nur noch als ausdrückliche Wahl, mit Warnung). **Debug-Log bleibt vollständig (1:1)** und rotiert erst bei 100 MB je Generation (3 Generationen, überschreibbar über `GLM2API_LOG_MAX_BYTES`/`GLM2API_LOG_BACKUP_COUNT`) — Vorrang hat Nachvollziehbarkeit für Patches. `GLM_MAX_CONCURRENCY` in `.env.example` auf 3 korrigiert (100 lag über dem Cap 32).

- 2026-09-25: Codespace Port-Forwarding gehärtet: In `.devcontainer/devcontainer.json` und `.vscode/settings.json` wurden `forwardPorts: [4096, 6082, 8001, 9878]`, `remote.autoForwardPorts: true`, `remote.autoForwardPortsSource: "process"` und `remote.restoreForwardedPorts: false` hinterlegt. Dadurch werden ausschließlich die 4 kanonischen Dienste dauerhaft weitergeleitet, temporäre Dev-Server automatisch nach Prozessende entfernt und interne Sockets (2000, 5900, 5920) ignoriert.
- 2026-09-25: glm2api stdout/stderr-Spiegel rotierend: `infra/scripts/glm2api.sh` kürzt `log/glm2api_output.log` beim Start und über einen Größenwächter alle 5 Minuten per Copy-Truncate auf 20 MiB (Historie in `glm2api_output.log.1`, 2 Generationen, `0600`). Grund: ohne Rotation wuchs die Datei bei `LOG_LEVEL=DEBUG` auf ~3,4 GB/Tag (1,4 GB in 6 h beobachtet). Copy-Truncate statt Rename, weil der Server die Datei über einen offenen Deskriptor weiterbeschreibt — ein Rename ließe ihn auf die Alt-Generation schreiben. Die Größenprüfung läuft gegen den Plattenverbrauch (`du`), nicht gegen `stat`, weil der nach dem Kürzen versetzte Deskriptor eine Sparse-Lücke erzeugt. Der Wächter wird beim Stop mitgebeendet; ein Kill erfolgt nur, wenn die PID wirklich zum Skript gehört (Schutz gegen PID-Wiederverwendung).

- 2026-09-24: glm2api-Sicherheits-/Ingress-Verträge gehärtet: nicht-Loopback-Bindungen verlangen API-Keys, CORS-Wildcards und Klartext-Upstream werden begrenzt, Request-/Header-/Body-/Socket-/Verbindungslimits sind hart begrenzt, Upstream-Timeouts werden von Client-Disconnects getrennt, interne Fehler bleiben generisch und Debug-Logs werden mit `0700`-Verzeichnis/`0600`-Dateien sowie Header-Redaktion betrieben. Raw-HTTP-Smoke-Checks für `411`/`400`/`413`/`501`, `Connection: close`, generische `504`-Upstream-Fehler und die Version ohne Python-Laufzeit wurden ausgeführt.

- 2026-09-24: Statusdokumentation synchronisiert: entferntes `infra/browser/`, glm2api-Provider-/HTTP-/Bundle-/Context-Verträge und der Validator `infra/scripts/validate-revision.sh` entsprechen dem aktuellen Source-Stand.

- 2026-09-24: **NVIDIA NIM: GLM 5.3 ergänzt, Provider bereinigt.**
  `z-ai/glm-5.3` mit 1.048.576 Tokens Gesamtkontext, 131.072 Tokens Output,
  Text-Ein-/Ausgabe, Tool-Calling und den Reasoning-Varianten `low`, `high` und
  `max` (Default) konfiguriert; Modell-ID und Inferenz per Live-Smoke-Test
  verifiziert. `deepseek-ai/deepseek-v4.1-flash` wurde nach fehlender Antwort
  des NVIDIA-Endpunkts nicht übernommen, `nvidia/nemotron-3-ultra-550b-a55b`
  entfernt.
- 2026-09-23: **Freebuff2API-Provider entfernt.**
  Freebuff2API samt `z-ai/glm-5.3-flash` und `deepseek/deepseek-v4.1-flash` aus
  `.opencode/opencode.json` entfernt; JSON- und OpenCode-Config-Validierung erfolgreich.
- 2026-09-23: **Secrets-Vereinheitlichung: `.secrets/` aufgelöst nach `~/.config/landscape/`.**
  (1) `chatglm-refresh-token` von `.secrets/chatglm-refresh-token` nach `~/.config/landscape/chatglm-refresh-token`
  migriert (gleicher Standard-Key-Pfad wie `pat`, `nvidia-nim.key`, `xinjianya.key`).
  (2) `infra/scripts/secrets.sh`: `lock` & `unlock` unterstützen `~/.config/landscape/chatglm-refresh-token`
  (mit abwärtskompatiblem Fallback auf `.secrets/`).
  (3) `llm-proxies/scripts/start-glm2api.sh`: Liest Refresh-Token primär aus `~/.config/landscape/` (Fallback `.secrets/`).
  (4) `infra/scripts/aliases.sh` (`landscape-diff`) & Doku aktualisiert. Workspace-Ordner `.secrets/` vollständig entfernt.
- 2026-09-22: **Config-Watchdog Busy-Guard & Modell-Bereinigung.**
  (1) `config-watchdog.sh` mit Busy-Guard gehärtet: Vor dem Restart wird `http://127.0.0.1:4096/session/status`
  geprüft. Solange Sessions im Status `busy` sind (Agent antwortet/führt Tools aus),
  wartet der Watchdog und killt den Server nicht mehr mitten im Turn. Debounce von 3s
  auf 8s erhöht + 3s Cooldown nach Turn-Ende. Neuer Pause/Resume-Modus via Alias
  `config-watchdog pause|resume` (/tmp/opencode/config-watchdog.pause).
  (2) Inaktive Provider und Modelle aus `.opencode/opencode.json` bereinigt.
  `grok-4.6` und `z-ai/glm-5.3` aus `xinjianya` entfernt, `moonshotai/kimi-k3` hinzugefügt.
  (3) Nicht mehr genutzte Web-Proxies und Web-Modelle vollständig entfernt:
  Ordner unter `llm-proxies/` gelöscht, Watchdog-/Boot-Einträge in `proxy-watchdog.sh`,
  `start-on-boot.sh`, `setup.sh`, `ports.sh`, `secrets.sh` und Secrets-Bundle bereinigt.
  Google-Modelle laufen ausschließlich über `antigravity`.
  (4) **glm2api Session-Isolation & Cleanup:** Persistente Websession (`GLM_PERSISTENT_CONVERSATION`)
  standardmäßig deaktiviert (`false`). Grund: Eine einzige persistente Web-Session vermischte verschiedene
  Tasks/Sessions, akkumulierte Historie quadratisch (da Clients wie opencode den Gesamtverlauf je Turn mitsenden)
  und schleppte frühere Fehlversuche (z. B. `open_url`-Toolhalluzinationen) in neue Sessions ein. Stattdessen
  wird je Request eine frische, isolierte Web-Session genutzt und per `GLM_DELETE_CONVERSATION=true` nach
  Antwort sofort serverseitig gelöscht. Standalone-Bundle `dist/glm2api-bundle.zip` aktualisiert.
  (5) **Modell-Feinschliff Antigravity:** `Gemini 3.8 Flash` fest als Standardmodell
  mit erzwungenem High-Thinking hinterlegt (`gemini-3.8-flash-high`, 1M Context, 64k Output).
  `Claude Opus 4.6` auf 100k Context-Limit angehoben. Unbenutzte Modelle (`gemini-3.5-flash-light`,
  `claude-sonnet-4-6`, `moonshotai/kimi-k3`) vollständig aus der Config bereinigt.
  (6) **glm2api Mega-Reasoning Format-Fix:** Re-Anchor (`TOOL_FORMAT_REMINDER`) an das
  Ende jedes Prompts verlegt (auch Turn 1), damit GLM-5.3 nach 60k+ Tokens Denkarbeit im
  `max`-Modus (`deep_thinking`) nicht mehr in Fließtext-Pläne abdriftet, sondern sofort
  den JSON-Tool-Call emittiert. Standalone-Bundle `dist/glm2api-bundle.zip` aktualisiert.
  (7) **glm2api Tool-Calling-Stabilisierung & Vereinheitlichung auf `thinking`:** (a) `deep_thinking`
  vollständig entfernt und `max` fest auf `thinking` (ca. 7s CoT) gemappt. ChatGLMs serverseitiger
  Web-Research-Modus (`deep_thinking`) ist damit dauerhaft deaktiviert (verhinderte Tool-Ausführung
  durch interne Web-Scraper-Schleifen). (b) In `.opencode/opencode.json` Varianten für `glm-5.3` auf
  ausschließlich `max` reduziert (`low` und `high` entfernt). (c) `_extract_call_arguments` fängt flach
  emittierte Tool-Parameter ab (`{"name":"todowrite","todos":[...]}`), statt sie auf `{}` zu
  leeren. (d) Alarmistische System-Prompts („waste an entire round") entschärft. (e) **Native
  Server-Tool Interception (`open`/`web_search`):** Wenn ChatGLMs Server native Web-Tools wie `open`
  (z. B. fälschlich für `/workspaces`) triggert, fängt `consume_event` dies sofort ab und bricht
  den Stream mit `status="intervene"` ab, statt 70 Sekunden auf 8 Upstream-Fehlversuche zu warten.
  Der bounded Follow-up-Mechanismus leitet das Modell direkt mit `bash` weiter. (f) **Mehrfach-Tool-Calls
  (Komma-separiert):** `_find_json_tool_call` extrahiert nun auch aufeinanderfolgende Sibling-Tool-Calls,
  falls das Modell das `tool_calls`-Array vorzeitig schließt und Folgetools mit Komma abtrennt
  (`{"tool_calls":[...]},{"name":"write"...}`). Leakt nicht mehr als sichtbarer Text. (g) **Schema-Schutz
  für `write`/`edit` & `file://`-Stripping:** Verhindert, dass JSON-Inhalte von `write` fälschlicherweise
  in Dicts geparst werden (SchemaError in OpenCode). Übergibt das Modell dennoch ein Dict/Array als Dateiinhalt,
  wird es automatisch in formatierten JSON-Text serialisiert. `file:///`-Präfixe in `filePath` werden
  automatisch zu echten absoluten Pfaden normalisiert. Standalone-Bundle `dist/glm2api-bundle.zip` aktualisiert.

- 2026-09-17: **Config-Watchdog + neue Modelle.**
  Neuer Daemon `infra/scripts/config-watchdog.sh`: überwacht `opencode.json`
  per inotifywait (close_write/moved_to), 3s Debounce, dann automatischer
  `opencode-server.sh restart`. Fallback auf 10s-md5sum-Polling falls
  inotify-tools fehlt. Lockfile `/tmp/opencode/config-watchdog.lock`, Log
  `/tmp/opencode/config-watchdog.log`. Start via setup.sh + start-on-boot.sh,
  Resurrection via proxy-watchdog.sh. Shell-Alias: `config-watchdog
  {status|start|stop|log}`. inotify-tools zu setup.sh-Paketliste hinzugefügt.
  Neue Modelle in xinjianya-Provider: `z-ai/glm-5.3`, `moonshotai/kimi-k3`.
  Live verifiziert: touch opencode.json → Debounce → Restart → Health-Check OK.
- 2026-09-17 (2): **xinjianya-Reasoning-Test: GLM 5.3 mit 6 Stufen, kimi-k3 entfernt.**
  `z-ai/glm-5.3` live über `opencode run --variant` auf allen Stufen getestet
  (none/low/medium/high/xhigh/max): alle 6 liefern Antworten (38/3/16/34/3/23
  Output-Tokens; Reasoning läuft upstream, wird von newapi nicht als
  `reasoning_tokens` ausgewiesen). Varianten dafür in der opencode.json
  ergänzt (Default `reasoningEffort: medium`). `moonshotai/kimi-k3` wieder
  entfernt: Upstream antwortet nicht (Cloudflare 524 nach ~125 s, auch
  streaming; `opencode run` endet ohne Ausgabe). Rückweg: Modell-Eintrag in
  opencode.json + Zeile hier wiederherstellen.
- 2026-09-11 (18): **Google-Drive-Backup: 2-Generationen-Repo-Sicherung nach Drive.**
  Szenario Account-Bann: komplettes Repo (History, alle Branches) liegt als
  git-bundle auf Google Drive (5 TB, Google AI Pro). Neuer Worker
  `infra/scripts/gdrive-backup.sh` (Alias `gdrive`): `git bundle --all` →
  Rotation (altes backup löschen, current → backup, frisch hochladen, MD5-
  Verifikation) → immer eine intakte Kopie auch bei abgebrochenem Upload.
  Trigger: save.sh-Hook nach jedem Push (deckt auch Autosave-Daemon mit ab).
  rclone v1.75.1 gepinnt (`rclone-install.sh`, via setup.sh). OAuth-Conf in
  `~/.config/rclone/rclone.conf` + Secrets-Bundle; bewusst NICHT
  `~/.config/landscape/` (Sanitizer stript dort refresh_tokens). Live
  verifiziert: Upload + MD5-Check, Rotation (beide Generationen auf Drive),
  Restore-Test (Clone aus Backup-Generation, Commit-Identität stimmt).
  Nebenher gefixt: setup.sh installiert jetzt Firefox-GTK-Deps
  (libgtk-3-0t64, libdbus-glib-1-2, libxt6t64, libasound2t64) — der
  noVNC-Browser startete sonst nach frischem Codespace nicht (XPCOMGlueLoad
  libgtk-3.so.0 fehlt). Rückweg: Commits revertieren.
- 2026-09-11 (15): **glm2api: Kontext-Management für Lang-Agent-Sessions (THEMA 1, optimierung.md).**
  Symptom: Ab ~150k Kontext driftete das Modell (Loops, Missdeutungen), Leer-
  Turns ließen Agents komplett stehen — alle Langläufe brauchten 4-6 externe
  Resume-Schubser. Drei Fixes: (1) Historien-Kompression `compress_history_
  messages()` (Budget GLM_HISTORY_MAX_CHARS=120k, paarweise assistant+tool-
  Nachrichten bleiben zusammen, ältere Runden werden zu einer Summary
  verdichtet); (2) Upstream-10040 ("context exceeded") ist jetzt transient —
  Retry halbiert das Budget automatisch bis der Upstream mitmacht (min 20k,
  beide Pfade); (3) Leer-Turn-Auto-Retry via `is_empty_response()` — komplett
  leere Upstream-Runden werden mit frischer Conversation retried, BEVOR die
  leere Antwort den Client erreicht (GLM_EMPTY_RESPONSE_MAX_RETRIES=2, nur
  wenn noch nichts gestreamt). Verifikation: Autonomie-Lauf hard6 (~86
  Runden, 171 Tool-Parts, 0 Fehler) lief ohne EINEN Schubser durch,
  Kompression live (268→52 Messages). 99/99 Tests (2 neue Leer-Turn-Tests),
  Bundle neu. THEMA 2 (Encoding-Sanitizer) bleibt OFFEN — siehe optimierung.md.
- 2026-09-11 (17): **Claude/Opus Quota-Schutz: 75k-Kontextdeckel & neu kalibriertes Thinking-Budget.**
  Maßnahmen gegen den Token-Multiplikator bei Claude Opus:
  1. `antigravity-proxy`: Claude Thinking-Budget neu kalibriert (`none`=0, `low`=1024,
     `medium`=2048 Default, `high`=4096 Cap statt 8192 Overkill). 92/92 Tests bestanden,
     Proxy neu gebaut und live verifiziert.
  2. `.opencode/opencode.json`: `limit.context` für Opus & Sonnet auf 75.000 (Output 16.384),
     Default auf `reasoningEffort: medium` mit Varianten `none`, `low`, `medium`, `high`.
     `compaction.reserved` von 83.400 auf 15.000 korrigiert (Auto-Pruning greift bei 60k).
  Gemini (1M) und GLM bleiben vollständig unberührt.

- 2026-09-11 (16): **quota.sh: Live 5h-Sprint & Wochen-Limit via retrieveUserQuotaSummary.**
  Bisher nutzte `quota.sh` den flachen Endpunkt `fetchAvailableModels`, der nur
  einen einzigen Quota-Wert lieferte (bei Claude starr das 7-Tage-Wochenlimit,
  welches fälschlicherweise in die Spalte „5h-Sprint“ gedruckt wurde).
  Umgestellt auf `v1internal:retrieveUserQuotaSummary` (exakt wie in der Antigravity
  Desktop-App): zeigt nun die vollständige 2×2-Matrix (Gemini Models & Claude/GPT
  jeweils mit 5-Stunden-Sprint und Wochen-Limit getrennt inkl. Restzeiten, Balken
  und lokalem Opencode-Tokenverbrauch). Fallback auf `fetchAvailableModels` gesichert.

- 2026-09-11 (15): **Autosave-Daemon: automatischer Commit+Push alle 30 Minuten.**
  Neuer Hintergrund-Daemon (`.devcontainer/autosave-daemon.sh`) sichert den
  Arbeitsstand automatisch, damit bei Codespace-Idle-Shutdown nichts verloren
  geht — egal welcher Agent oder User gerade parallel arbeitet. Prüft erst ob
  es tatsächlich uncommittete Änderungen oder ungepushte Commits gibt (kein
  leerer Commit-Spam), nutzt `save.sh` intern (add -A, commit `autosave
  <timestamp>`, pull --rebase --autostash, push). Lockfile-gesichert
  (`/tmp/opencode/autosave-daemon.lock`), Log `/tmp/opencode/autosave.log`.
  Autostart via `start-on-boot.sh` (Block 6) und `setup.sh` (letzter Block).
  Shell-Funktion `autosave` in `aliases.sh` für Status/Start/Stop/Log-Zugriff.

- 2026-09-11 (14): **glm2api: Leak-Variante D gefixt — nacktes JSON-Array als Tool-Protokoll.**
  Auslöser: Final-Run des HARD-Benchmarks — das Modell emittierte Tool-Calls als
  nacktes Array [{"name":...,"arguments":...}] OHNE {"tool_calls"}-Wrapper
  (Prosa+Array, und: kaputter ``json-Marker + Array ohne ']' + Duplikat + '[]').
  Vorher lief beides als sichtbarer Text durch (Parser kannte nur das Wrapper-
  Format; der kaputte 2-Backtick-Marker umging zusätzlich die Fence-Maskierung).
  Fix: `_find_bare_tool_call_array()` (strenge Element-Validierung, Bracket-Scan,
  Terminator/Fence-Konsum, Recovery via _recover_call_elements) in
  parse_tool_calls_from_text + _split_stream_text (Streaming). Beide Live-Leak-
  Strings verifiziert, 92/92 Tests (2 neue Regressionstests), Proxy neu
  gestartet, Bundle neu gebaut. Details: Git-Commit 1039311.
- 2026-09-10 (13): **glm2api: Midstream-Guard gegen Protokoll-Fragmente in content-Deltas (Re-Befund C).**
  Auslöser: Re-Run-Doppelausgabe 22:35 (tool_calls=1 UND text_len=1630 im selben
  Turn — Protokoll lief parallel zum strukturierten Call als Text). Fix in
  translator.py::consume_event: Ein sichtbares Delta mit Protokoll-Fragmenten
  ({"tool_calls", <ml_tool_call, <|DSML|tool_call) wird bei deklarierten Tools
  ins Deferred-Buffer geparkt statt sofort emittiert; das finalize-Safety-Net
  extrahiert den Call und gibt nur bereinigten Text aus. 90/90 Tests (neuer
  Regressionstest), Proxy neu gestartet, Bundle neu gebaut. Damit sind alle
  drei Leak-Befunde (B, C) aus dem Härtetest-Re-Run geschlossen; offenes
  Rest-Thema ist nur noch Modell-Drift bei ~150k+ Kontext (kein Proxy-Bug).
- 2026-09-10 (12): **glm2api: Recovery-Stufe 3 für invalides Tool-JSON (Re-Run-Befund B).**
  Auslöser: HARD-Benchmark-Re-Run (2h, 122 Tool-Calls, 0 Ausführungsfehler)
  reproduzierte einen Leak, bei dem das Modell 6 Calls als ~6,6KB-Block mit
  unbalancierten Klammern (16 `{` vs 15 `}`) emittierte — Brace-Scan ohne
  Ende, kompletter Block leakte als Text. Fix: `_recover_tool_calls_json()`
  erweitert um `_recover_call_elements()` (name/arguments-Paare einzeln
  extrahieren + re-serialisieren), verdrahtet als dritte Recovery-Stufe.
  89/89 Tests (inkl. Live-Leak-Regressionstest), am Original-Leak-String
  verifiziert (6 Calls, clean=""), Bundle neu gebaut. Offen bleibt
  Re-Befund C (Doppelausgabe Call+Text bei gespiegelten Parts — Re-Run mit
  DEBUG_DUMP_ALL nötig). Details: Git-Commit 1039311.
- 2026-09-10 (11): **glm2api: Parser-Recovery gegen Snipsel+Finish-Duplikat und
  Terminator-Whitespace-Leak (HARD-Benchmark-Befunde 1+2).**
  Auslöser: ~30-Min-Langlauf (HARD Benchmark v2, benchmark-hard.md + broken3.py
  unter /workspaces/benchmark) reproduzierte live einen Protokoll-Leak: Der
  Upstream streamt Token-Schnipsel und danach den Volltext als eigenes Delta;
  der StreamingToolParser-Buffer enthielt dann `<Fragment><Volltext>`, der
  Brace-Scan brach am ersten scheinbar balancierten `}` ab, json.loads scheiterte
  → komplettes `{"tool_calls":[...]}`  leakte als sichtbarer TEXT-Part
  (text_len=216, tool_calls=0) und der Call ging verloren. Zweiter Leak: `\n`
  zwischen JSON und `[]`-Terminator ließ das `[]` als Content durchrutschen.
  Fix in tool_parser.py: (1) `_recover_tool_calls_json()` — bei
  JSONDecodeError werden alle `{"tool_calls`-Vorkommen im Kandidaten gescannt
  und die erste valide balancierte Instanz geparst; (2) Terminator-Konsum
  whitespace-tolerant (lstrip + Skip). Verifikation: 88/88 Tests (3 neue
  Regressionstests inkl. Original-Live-Fall), Proxy neu gestartet, Live-Check
  strukturiert, Bundle neu gebaut. Echo-Filter (10) hielt im Langlauf stand
  (keine server_tools-Cluster, keine Duplikate); Details siehe Git-Commit 1039311.
- 2026-09-10 (10): **glm2api: Echo-Filter für gespiegelte native tool_calls (Benchmark-Toolcall-Fix).**
  Auslöser: SWE-Benchmark-Run (Subagent auf glm2api/glm-5.3) — ~25% „unknown
  tool call"-Fehler, massive Duplikat-Executions (24 Tools in einem Timestamp-
  Cluster, write 5x). Root Cause: chatglm.cn spiegelt die Tool-Call-Historie
  als native `tool_calls`-Parts zurück (bis zu 36 pro Turn, im Proxy-Log als
  `server_tools=36` sichtbar); `consume_event` leitete jedes Echo als neuen
  Call an den Client weiter → Duplikat-Loops + halluzinierte Fehlerberichte
  des Modells. Fix (2 Ebenen, translator.py + glm_client.py): (1) Echo-Filter
  — native Parts, deren Signatur (Name + normalisierte Argumente) exakt einem
  bereits ausgeführten Assistant-Call der Request-Historie entspricht, werden
  verworfen (`extract_history_tool_call_signatures()`); (2) Signatur-Dedup —
  mehrfach identische Parts kollabieren auf einen (statt nur ID-Dedup).
  Verifikation: 85/85 Tests (3 neu: Signatur-Extraktion, Echo-Drop, Dedup),
  Live-Repro (Multi-Turn mit Tool-Result-Runde) sauber, Proxy neu gestartet,
  Benchmark-Re-Run 6/6 PASS mit 0 Toolcall-Fehlern, Bundle neu gebaut.
- 2026-09-10 (9): **antigravity-proxy-Autostart repariert (Root Cause: unsichtbares Zero-Width-Space in der go.dev-URL).**
  Nach jedem Codespace-Rebuild fehlte Go: In `setup.sh` steckte in der
  Download-URL ein unsichtbares U+200B (`https://<ZWP>go.dev/...`) — curl
  lehnt so eine URL immer ab, der Go-Install-Schritt scheiterte still, und
  ohne Go kann `antigravity-proxy/scripts/start.sh` das Binary (liegt nicht
  im Git) nicht bauen. Fixes: (1) U+200B aus setup.sh und start.sh
  entfernt, (2) setup.sh lädt Go jetzt mit `curl --retry 5 --retry-all-errors`
  (Boot-Netz transient), (3) `start.sh` installiert Go 1.25.7 selbst nach
  `/usr/local/go`, falls go nirgends vorhanden ist. Verifiziert mit
  Go+Binary entfernt: start.sh stellt beides selbst her, Port 9878
  antwortet mit 200.
- 2026-09-10 (8): **glm2api: Nicht-Think-Modell mit reasoning_effort als stabiler Standard.**
  Vergleich mit glmfree (externer glm-free-api, gleicher chatglm.cn-Upstream)
  ergab: glmfree aktiviert Thinking über `reasoning_effort` (z.B. `max`) im
  Request — nicht über den `-think`-Modellnamen. glm2api unterstützt das
  ebenfalls sauber (`resolve_chat_mode` mapped effort → chat_mode). Bei
  `-think`-Modellen löst opencode beides GLEICHZEITIG aus (Suffix +
  `reasoningEffort: "max"` aus der Modell-Config) — diese Doppelauslösung
  korreliert mit den instabilen Reasoning-Streams (Tool-JSON im Reasoning,
  leere Turns, 30K+-Loops). Neu in `.opencode/opencode.json`:
  `glm2api/glm-5.3` (non-think) mit `reasoningEffort: "max"` — verifiziert:
  Killer-Szenarien fresh+multiturn sauber, Benchmark TOOLCALL-PASS 25/25.
  `glm-5.3-think` wurde aus der Config ENTFERNT (inkl. Agent-Umstellung),
  damit es keine Verwirrung gibt — Thinking läuft ab jetzt ausschließlich
  über `reasoningEffort` beim non-think-Modell.
- 2026-09-10 (7): **glm2api: Tool-Protokoll verschlankt + Re-Anchor + Pretty-JSON/Fragment-Parser-Fix.**
  Auslöser: Vergleich mit glmfree (externer glm-free-api-Server, gleicher
  chatglm.cn-Upstream) — der liefert im selben Killer-Szenario (11 Tools +
  großer Systemprompt + Multi-Turn) immer perfekt strukturierte tool_calls,
  während glm2api-Runde um Runde in Text-Abbrüche kippte. Voll-Audit der
  Pipeline (server/translator/parser/client) mit 4 Fixes:
  (1) `build_tool_call_instructions` von ~40 auf 9 Zeilen verschlankt
  (glmfree-Minimum: Format-Beispiel + `[]`-Terminator-Regel — der Terminator
  wirkt token-weise als Wahrscheinlichkeits-Anker, da das Modell den Prompt
  bei jedem Output-Token neu liest). (2) Re-Anchor nach Tool-Result-Runden:
  `TOOL_FORMAT_REMINDER` am Prompt-Ende (Blaupause:
  Re-Anchor-Fix, Commit 105480a) — dort am stärksten wirksam. (3) Pretty-JSON:
  tolerante Regex `\{\s*"tool_calls"\s*:` an allen 3 Parser-Fundstellen —
  pretty-printed Protokoll wurde vorher als Text geleakt. (4) Fragment-Hold:
  Präfix-Hold auf `{"tool_calls":` inkl. Länge 0 — das 13-Zeichen-Fragment
  `{"tool_calls"` (Live-Leak reproduziert) wurde vorher durchgereicht.
  Verifikation: 82/82 Tests, Fragment-Matrix (1..full) ohne Leak,
  Live-Killer-Szenarien fresh+multiturn → saubere TOOLCALLs mit text_len=0,
  Benchmark TOOLCALL-PASS 25/25 beim ersten Harness-Run. Restrisiko
  (Modell, nicht Proxy): gelegentliche leere Assistant-Turns + halluzinierte
  „Tool-Limit"-Narrative → Session-Resumes nötig; Hebel wäre opencode-seitiges
  Auto-Resume. Hinweis: Teile dieser Fixes wurden versehentlich im Commit
  f8a8aad (feat antigravity) mitcommittet; dieser Commit ergänzt Doku + den
  finalen Fragment-Hold-Fix.
- 2026-09-10 (6): **glm2api: Tool-Calls in ```json-Fences werden echte Calls (Benchmark TOOLCALL-PASS).**
  Auslöser: TOOLCALL-360-Benchmark-Run 6 — glm-5.3-think verpackte den Tool-Call in
  einen ```json-Code-Fence; der Parser maskiert Fences bewusst (Doku-Beispiel-Schutz),
  also lief der echte Call als Klartext durch → opencode beendete die Session.
  Fixes (82/82 Tests): (1) Fence-Deferral im Stream — öffnende/unbalancierte
  Fences werden bei deklarierten Tools im `_deferred_visible_text` gehalten,
  statt sofort als Content-Delta zu leaken. (2) `_unwrap_protocol_only_fences()`
  im finalize: Fences, deren Inhalt (fast) nur das Tool-Protokoll ist, werden
  entpackt und als echte strukturierte Tool-Calls geliefert; Doku-Beispiele mit
  Prosa bleiben maskiert. Ergebnis: Benchmark glm2api/glm-5.3-think erreicht
  TOOLCALL-PASS (25/25, 1 Korrekturschleife). Restrisiko dokumentiert: Modell
  halluziniert gelegentlich ein „3/3-Rundenlimit" und bricht in Text ab —
  workaround Session-Resume; kein Proxy-Bug.
- 2026-09-10 (5): **glm2api: Negative Tool-Results für blockierte Tool-Calls + Protokoll-Leak-Stopp.**
  Auslöser: ZEPLAN-Benchmark — glm-5.3-think rief in 4 Testläufen wiederholt das
  halluzinierte native Web-Tool `open_url` auf; glm2api warf diese Calls still weg
  → das Modell bekam kein Feedback, wiederholte bis das clientseitige Rundenlimit
  (3/3) verbrannt war → Benchmark-FAIL ohne einen einzigen Arbeitsschritt. Zweites
  Symptom (live reproduziert mit 11 deklarierten Tools + großem Systemprompt): das
  Modell streamt das Tool-Protokoll fragmentweise als Text (`{"`, `tool`, `_calls`…),
  der Parser hielt Fragmente unter 9 Zeichen Präfix-Länge nicht zurück → Protokoll
  leakte als sichtbarer Content. Fixes (verifiziert mit 82/82 Tests + Live-Repro):
  (1) **Folgerunde mit negativem Tool-Result**: Erkennt der Proxy blockierte/
  undeklarierte Call-Versuche (JSON- UND DSML-Protokoll, Text- UND Reasoning-Kanal,
  via neue `detect_tool_call_names()`-Diagnosefunktion), startet er automatisch
  eine Folgerunde mit „Tool X existiert nicht, wurde NICHT ausgeführt, verfügbar
  sind …" — Budget `GLM_BLOCKED_TOOL_FOLLOW_UPS` (Default 2), nur solange kein
  sichtbarer Content gesendet wurde (triviales `[]`-Restgerümpel zählt nicht).
  (2) **Parser-Härtung**: Fragment-Hold-Logik ab 2 Zeichen Präfix (`{"`),
  Leak-Stripping von Blöcken mit nur gefilterten Calls, korrekte while/break-
  Struktur statt `continue`-in-for-Schleife (die neue Response wurde nie iteriert).
  (3) **finalize()-Safety-Net**: geleakte Protokoll-Blöcke werden ohne Allow-Filter
  geparst — erlaubte Calls werden echte Tool-Calls, blockierte in
  `blocked_tool_attempt_names` protokolliert. Live-Verifikation: das vorher
  zuverlässig leckende Szenario liefert jetzt einen sauberen strukturierten
  `read`-Tool-Call.
- 2026-09-10 (6): **Go-Toolchain im Landschafts-Setup verankert.** Root Cause
  „antigravity-proxy startet nicht": Binary liegt nicht im Git, und weder `go`
  noch `mise` waren installiert — `run_proxy.sh` und `scripts/start.sh` konnten
  nicht bauen. Fix: Go 1.25.7 (gepinnt, wie Upstream-`mise.toml`) wird jetzt von
  `setup.sh` automatisch nach `/usr/local/go` installiert (idempotent),
  `scripts/start.sh` baut das Binary bei Bedarf selbst nach, `/usr/local/go/bin`
  im PATH via `aliases.sh`. Autostart-Kette (setup.sh → start-on-boot.sh →
  proxy-watchdog.sh) greift damit auch nach Rebuild/Resume ohne manuellen Build.
- 2026-09-10 (3): **Chromium-Stack komplett entfernt, Firefox als VNC-Browser.**
  Google-Logins in Chromium erzeugen DBSC-gebundene Sessions (Device-Bound Session Credentials),
  wodurch Cookies nach ~30-60 Min ablaufen. Firefox-Sessions sind nicht DBSC-gebunden.
  Entfernt: `infra/browser/` (Playwright 1.48.2),
  `browser-install.sh`, `.runtime/ms-playwright/` (555 MB), `.runtime/chromium-profile/`
  (66 MB), CDP-Port 9222. Neu: `infra/scripts/firefox-install.sh` (Mozilla-Tarball,
  gepinnt 155.0.1, nach `.runtime/firefox`), `browser-start.sh` auf Firefox umgeschrieben
  (Xvfb/x11vnc/noVNC unverändert: Display :120, VNC 5920, noVNC 6082), setup.sh umgestellt,
  dbus-x11 nachinstalliert. Rückweg: Commit revertieren.
- 2026-09-10 (2): **glm2api: Transient-Stream-Error-Retry (Code 10025/10061/10062).**
  Auslöser: Session „glm2api fehler" starb nach 5 Min Arbeit an
  `GLM upstream returned an error | code=10025 stream request error` — chatglm.cn
  bricht frische Streams gelegentlich transient ab, glm2api hatte dafür keine
  Retry-Logik (nur Busy-429 und Failover *vor* Stream-Start). Fix: `UpstreamAPIError`
  trägt jetzt ein `transient`-Flag (error_code ∈ {10025, 10061, 10062}); Stream- und
  Non-Stream-Pfad öffnen bei transientem Fehler vor sichtbarem Content (Reasoning-
  Replay ist harmlos, Text-Duplikate nicht) die Upstream-Konversation neu —
  frischer Accumulator + Retry, bis `GLM_STREAM_ERROR_MAX_RETRIES` (Default 2,
  Intervall `GLM_STREAM_ERROR_RETRY_INTERVAL_SECONDS`, Default 1s) erschöpft; nach
  bereits gesendetem Text weiterhin sofort raise. Cleanup (Response/Conversation/
  Lease) garantiert in `finally`. Zusätzlich: Betrieb auf registrierten
  `GLM_REFRESH_TOKEN` umgestellt (`.env` + `glm2api.env`, Guest nur noch Fallback).
  Tests 73 → 79 (neu: test_stream_retry.py — Retry-Trigger, Give-up, Non-transient,
  Error-nach-Content, Non-Stream-Retry), Proxy neu gestartet, live verifiziert
  (stream + non-stream), Bundle neu gebaut. Token-Hinweis: der registrierte
  Refresh-Token liegt nur in der lokalen `.env` (gitignored); für neue Codespaces
  als `chatglm-refresh-token` ins Secrets-Bundle (`config/secrets.enc`) packen.
- 2026-09-09 (9): Claude Opus 4.6 (`antigravity/claude-opus-4-6`) im Antigravity-Proxy
  und opencode integriert (1M Context, bis 64k Output, Thinking-Budget dynamisch stufbar:
  `low`=2k, `medium`=16k, `high`=32k, Default `high`). Umgeht das 1024-Token-Limit der
  Google-IDE vollständig. opencode-Server auf Port 4096 als echter Daemon (`nohup </dev/null disown`)
  gehärtet (verhindert SIGHUP beim Schließen von Terminals). Volle 1M Context + 64k/32k
  Output-Limits für alle drei Gemini-Modelle (`gemini-3.8-flash`, `gemini-3.1-pro`,
  `gemini-3.5-flash-light`) in `opencode.json` freigeschaltet. Alias `opencode-server` ergänzt.
- 2026-09-09 (8): Multi-Client opencode-Server (`opencode serve`, Port 4096)
  eingerichtet. Smart-Wrapper in `aliases.sh` verbindet alle Terminals via
  `opencode attach http://localhost:4096` — parallele Sessions terminieren
  sich nicht mehr gegenseitig. In Watchdog (`proxy-watchdog.sh`), `start-on-boot.sh`
  und `setup.sh` verankert.
- 2026-09-09 (7): `antigravity-proxy` (`dvcrn-antigravity-oauth-proxy`) fest unter
  `llm-proxies/antigravity-proxy/` integriert (Port 9878, CloudCode Assist OAuth).
  OAuth-Credentials ins verschlüsselte Secrets-Bundle aufgenommen. Autostart in
  `setup.sh` und `start-on-boot.sh` eingebunden.
- 2026-09-09 (5): Tool-Call-Resilienz gegen LLM-Quoting-Versagen:
  (a) Protokoll-Instruktion erweitert — keine fragilen Inline-`python3 -c
  "..."`-Commands mit verschachtelten Quotes in Tool-Argumenten (Heredocs/
  Skriptdateien bevorzugt). (b) Auto-Repair `x'key'` → `x['key']` beim
  Tool-Call-Parsing für bash/shell/python-Commands mit Compile-Oracle
  (Reparatur nur wenn Ergebnis kompiliert und Original nicht — keine
  False Positives, funktionierender Code bleibt unberührt). Ausgelöst
  durch Session-Vorfall: glm-4.7-flash erzeugte `creds'expiry_date'`
  (ungültiges Python). Bei doppelt kaputten Commands (Quotes + Struktur)
  greift das Oracle schützend nicht. Tests 70 → 73.
- 2026-09-09 (4): glm2api komplett auf Englisch übersetzt (China-Audit,
  ~283 A-Stellen): alle Log-/Fehler-/Kommentar-Strings in config, app,
  __main__, server, glm_auth, glm_client, translator + pyproject.toml +
  .env.example + glm2api.env + Live-.env. Bewusst chinesisch bleiben nur
  funktionale Stellen: Busy-Erkennung (glm_client.py:880), Gast-Alias
  `游客` (config.py:128), chatglm.cn-Header — plus CJK-Test-Fixtures
  (gewollte Abdeckung). Fortschritts-Doku: /workspaces/china-audit.md.
  Tests 70 grün (neu: undeclared-tool-EN-Assertion), Proxy neu gestartet,
  8/8 Smoke-Checks, Bundle neu gebaut.
- 2026-09-09 (3): glm2api-Tiefenrevision (2 parallele Subagenten-Audits)
  umgesetzt — alle Befunde gefixt: Part-Merge-Duplikat (finish-Volltext
  ohne part-status verdoppelte Text; jetzt status-unabhängig idempotent),
  Anthropic-SSE-Fragment-Puffer (analog Responses-Adapter), 160 Z. toter
  Legacy-Code entfernt (translator + tool_protocol), Auth-Lock-Scope
  verkleinert (Refresh läuft außerhalb des Locks, double-checked),
  allowed-Filter auch im think-Fallback, Streaming-Deferral nur noch bei
  echten Tool-Partials (kein Puffer-Regress bei deklarierten Tools),
  `'{"'`-Holding auf Tool-Präfixe begrenzt, `"‚<m'`-Hint entfernt (math-
  Text fließt), Tool-Results zu ID-reparierten Calls bleiben erhalten,
  `_resolve_tools` einmal pro Request, Server-Klassen-Attribute wirksam,
  Config-Logging vor setup, Syntaxfehler in uncommitteter CN→EN-Übersetzung
  behoben, smoke-test $SMOKE_MODEL fix + JSON-Body-Fix, bundle/start.sh
  Health-Check, kontostand.sh gestrichen. Tests 63 → 69, alle grün;
  Proxy neu gestartet, 8/8 Smoke-Checks bestanden.
- 2026-09-09 (2): Kontostand-Spec (infra/docs/Kontostand.md, 432 Zeilen)
  gelöscht — nicht mehr benötigt. kontostand.sh bleibt, Header-Verweis
  entfernt. README: Bundle-Refresh-Doku ergänzt (build-bundle.sh
  überschreibt dist/glm2api-bundle.zip immer mit aktuellem Stand,
  deterministisch + Verifikation gegen Source-Drift).
- 2026-09-09: Kompaktierung Runde 2: totes Modul `model_profiles.py`
  entfernt (nirgends importiert). Betriebs-Bug gefixt: `infra/scripts/
  glm2api.sh` startete System-Python 3.12 statt venv-Python 3.14 (App
  requires >=3.14) — Restart wäre mit ImportError gescheitert. README
  "Enthalten" gestrafft, Bundle neu gebaut (44 statt 45 Dateien).
- 2026-09-09: Struktur-Kompaktierung: `work/` aufgelöst — `docs/` nach
  `infra/docs/` (Reverse-Engineering-Doku). Ein Top-Level-
  Ordner weniger, Referenzen in kontostand.sh / build-bundle.sh angepasst.

- 2026-09-08 (6): **Kompaktierung/Audit-Umsetzung** (AUDIT.md + glm-api-audit.md
  abgearbeitet): korrupter Patch gestrichen (`llm-proxies/patches/` — der
  Source im Repo ist kanonisch); Bundle neu gebaut mit vollständigen Tests
  (inkl. test_config.py) und deterministischen Zeitstempeln (md5-stabil,
  Doppelbuild verifiziert); 15 MB Debug-Logs + __pycache__/egg-info
  aufgeräumt; README-Changelog gekürzt; `.env.example` vervollständigt; Start-/Rebuild-Skripte gehärtet
  (glm2api.sh: PID-Datei statt globalem pkill, Health-Check im Status;
  start-glm2api.sh: Fremdbelegung von Port 8001 wird erkannt statt als OK
  gemeldet; rebuild.sh: `uv sync --frozen` immer + Sanity-Check);
  glm2api-README kompaktiert (deutsch, Refresh-Token-Anleitung erhalten).
  Zusätzlich pytest als dev-Dependency-Group gepinnt (pyproject+uv.lock), damit
  `uv sync --frozen` die Test-Runner reproduzierbar mitliefert.
  Rückweg: Commit revertieren.
- 2026-09-08 (5): **Watchdog-Start gefixt** — Watchdog lief zwar laut
  Boot-Log an, wurde aber beim Aufräumen des `postStartCommand` von
  devcontainer-cli mitgekillt (`nohup` ohne `setsid` schützt nicht vor
  Process-Group-Kill). Fix: `setsid`-Start in `start-on-boot.sh` UND
  `setup.sh` (startet jetzt auch beim Codespace-Bau/Rebuild). Verifiziert:
  Proxy killen → Watchdog zog ihn in <30s hoch; Watchdog überlebt jetzt
  Shell-/postStart-Ende (eigene Session, `ps`: SID=PGID=PID). Rückweg: Commit
  revertieren, Watchdog ggf. manuell `setsid bash
  .devcontainer/proxy-watchdog.sh &` starten.
- 2026-09-08 (4): **google-Provider** (nativ, Modell `gemini-flash-latest`,
  1M Kontext / 64k Output) in `.opencode/opencode.json`; Key als `gemini.key`
  über `{file:~/.config/landscape/gemini.key}` referenziert, `secrets.sh`
  lock/unlock erweitert, Bundle+Manifest aktualisiert. Live verifiziert:
  `opencode models` listet ihn, `opencode run --model google/gemini-flash-latest`
  antwortete OK. Hinweis: `generateContent` meldete einmalig 503 (Modell
  überlastet, transient) — bei Wiederholung OK.
- 2026-09-08 (3): vovoapi-Provider **wieder entfernt** (Modelle `gpt-5.6-sol` +
  `gpt-6-astra`, `vovoapi.key`, `secrets.sh`-Erweiterung, Bundle-Eintrag) — Key
  wurde von der API als `INVALID_API_KEY` abgelehnt. Rückweg: Provider-Block aus
  (2) erneut in `.opencode/opencode.json` eintragen + Key nach
  `~/.config/landscape/vovoapi.key` + `secrets.sh lock`.
- 2026-09-08 (2): **vovoapi-Provider** (`https://vovoapi.com/v1`, OpenAI-kompatibel,
  Modelle `gpt-5.6-sol` + `gpt-6-astra` mit Reasoning-Varianten none/low/medium/high/
  xhigh/max) in `.opencode/opencode.json`; Key als `vovoapi.key` über
  `{file:~/.config/landscape/vovoapi.key}` referenziert, `secrets.sh` lock/unlock
  erweitert, Bundle+Manifest aktualisiert. Status: Config lädt (`opencode models`
  listet beide), API antwortet aktuell `INVALID_API_KEY` — Key prüfen/rotieren.
- 2026-09-08 (1): glm2api **portables Bundle**: `llm-proxies/scripts/build-bundle.sh`
  baut `llm-proxies/dist/glm2api-bundle.zip` (reproduzierbar aus dem Repo —
  Code, Tests, glm2api.env, portable install/start-Skripte mit relativen
  Pfaden, Patch-Referenz, Reverse-Engineering-Doku). Live verifiziert:
  Entpacken → install.sh → start.sh → Health + Chat-Antwort OK, 60/60 Tests.
  Aufgeräumt: /workspaces/patch-glm2api (veraltetes Duplikat-Repo, gelöscht —
  Rückweg: MAIN enthält den vollständigen gepatchten Code im Git) und
  /workspaces/reverse-engeneer (Doku übernommen nach work/docs/). Zip-Quellen
  leben kanonisch unter `llm-proxies/scripts/bundle/` (README/install/start).
- 2026-09-07 (7): (a) Proxy-Watchdog: postStartCommand greift bei Client-
  Reconnect NICHT (nur echter Container-Start) — deshalb Daemon
  (`proxy-watchdog.sh`, 30s-Health-Check, Lockfile), der den Proxy nach
  OOM-Kill/Reconnect automatisch hochzieht. Live bewiesen: kill -9 → Proxy in
  ≤40s wieder da. (b) Reasoning-Default jetzt **max** (极致), Varianten
  reduziert auf **low/high/max** (medium entfällt — war doppelt zu high).
  MiniKV-SWE-Benchmark je Modus: low (0 Reasoning-Zeichen, 9/9, mehr Steps),
  high (9198 Z., 9/9), max (10053 Z., 9/9, wenigste Steps — effizienteste
  Lösung); medium/default zeigten je 1 Abbruch (Token-Rotation).
- 2026-09-07 (6): postStartCommand-BUGFIX: devcontainer.json hatte den Key
  DUPZIERT (2. Definition = git-pull überschrieb das Boot-Skript) — deshalb
  war glm2api nach jedem Codespace-Start offline. Beide jetzt zusammengeführt
  (erst git-pull, dann start-on-boot.sh). Deren Wirken ist damit garantiert;
  Alters-Empfehlung falls doch etwas klemmt: `bash .devcontainer/start-on-boot.sh`.
- 2026-09-07 (5): Reasoning-Mapping final (User-Spezifikation): low = 快速/leer
  (kein Denken), medium = thinking, high = thinking, max = 极致/deep_thinking,
  Default (ohne Stufe) = deep_thinking. Alle Modi live verifiziert (low: 0
  Reasoning-Zeichen + 4s; thinking/deep_thinking mit Reasoning; alle korrekt),
  Upstream-Log bestätigt die chat_mode-Werte. Reverse-Engineering-Doku jetzt
  im Repo: `work/docs/reverse-engineering/` (ERGEBNIS.md + capture.py/cdp.py,
  Quelle: /workspaces/reverse-engeneer — Workspace danach entfernt).
- 2026-09-07 (4): Proxy-Autostart bei JEDEM Start: `postStartCommand`
  (`start-on-boot.sh`) — `postCreateCommand` lief nur bei Neuerstellung, nach
  Resume (Stopp/Über Nacht) war der Proxy tot. Boot-Skript: Health-Check →
  Start → Background-Rebuild (bei Unvollständigkeit). Live getestet (Proxy
  hochgezogen, LLM antwortete).
- 2026-09-07 (3): glm2api-Modell: nur noch `glm-5.3-think` (Denk-Modus,
  interner Name — Anzeigename „GLM-5.3 glm2api"), Varianten low/medium/high/
  max. Messung: reasoning_effort wirkt am Proxy nur als Denk-Schalter
  (chatglm.cn kennt keine Stufen) — Reasoning-Länge ist Modell-Varianz,
  Varianten bleiben als Komfort drin. Alle Stufen live getestet (korrekt).
- 2026-09-07 (2): glm2api-Code VOLLSTÄNDIG ins Repo gewandert
  (`llm-proxies/glm2api/`, inkl. Patches — kein GitHub-Klon mehr nötig).
  rebuild.sh macht nur .env + uv sync (~Sekunden, kein Minuten-Klon);
  start-glm2api.sh läuft aus MAIN; /workspaces/glm2api entfällt komplett.
  Switchover live verifiziert: Proxy läuft aus MAIN-Pfad, Health/Chat/
  Tool-Calls OK, /workspaces/glm2api gelöscht.
- 2026-09-08: glm2api-Betriebsskript erkennt den tatsächlichen Prozess
  `python3 main.py` einheitlich bei Status, Stopp und Startprüfung. Der
  Tool-Parser repariert gezielt eine fehlende schließende `]` des
  `tool_calls`-Arrays, ohne umgebenden Modelltext umzuschreiben.
- 2026-09-07 (1): Finaler Härtetest glm2api nach Umbau BESTANDEN (alle 5 Phasen):
  (A) Kaltstart von Null — /workspaces/glm2api gelöscht → rebuild.sh stellte
  Klon+Patch+.env+venv+start wieder her, Proxy lief; (B) API komplett: 80
  Modelle, non-stream, stream (Part-Merge sauber), Multi-Turn-Kontext; (C)
  Agent-Loop 3/3 Tool-Call-Schritte inkl. History-ohne-user-msg; (D) opencode
  end-to-end via `--model glm2api/glm-5.3` (Datei erstellen+testen, 6
  Tool-Executions); (E) Parallel-Load 5/5 korrekt (6.3s) + Token-Rotation.
  Zusätzlich `agent/glm2api.md` als fest verdrahteter Arbeits-Subagent.
- 2026-09-04 bis 09-06: Initialer Landschafts-Aufbau, glm2api-Umbau von Klon
  auf Repo-internen Source, Browser-Infrastruktur, Kontostand-Tool,
  Secrets-Modell etabliert.
