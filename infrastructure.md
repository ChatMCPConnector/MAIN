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
| `.devcontainer/` | devcontainer.json + setup.sh (läuft automatisch bei jedem Codespace-Bau), proxy-watchdog.sh. **Kein autosave-daemon** (Nutzerentscheidung 2026-09-27, siehe Changelog) |
| `.opencode/` | opencode-Config: opencode.json (Provider/MCP), tui.json (v1) |
| `config/` | secrets.enc (verschlüsseltes Bundle) + Manifest + passphrase (Klartext, bewusst); `opencode-cli.json` = v2-TUI-Config |
| `infra/` | **Werkzeugkasten:** `scripts/` (save/auth/secrets/ports/browser-*.sh, aliases.sh, config-watchdog.sh, verify-codespace.sh), `mcp/` (opencode-sessions MCP), `docs/` (Reverse-Engineering-Doku) |
| `llm-proxies/` | LLM-Proxies: **glm2api** (Port 8001, GLM-Haupt-Proxy) + **antigravity-proxy** (Port 9878, CloudCode OAuth) |

| `.env` `.runtime/` | GITIGNORED — Klartext-Secrets (.env), Browser-Profil, Runtime (nie committen) |

## Schnellstart

Codespace bauen → `setup.sh` stellt ALLES automatisch wieder her (Systempakete,
opencode, uv, Secrets-Unlock, Git-Auth, Freebuff-CLI, Browser-Runtime,
**glm2api- und antigravity-Proxy inkl. Start** — der Code liegt
komplett im Repo, es gibt nichts mehr zu klonen; nur `uv sync` (Python 3.14 +
Deps, beim ersten Mal ~2-5 Min) + Autostart). Danach:

```bash
./infra/scripts/save.sh status                       # Überblick (Repo, Auth, Secrets)
./infra/scripts/verify-codespace.sh                  # read-only Check der ganzen Kette
```

Aliase (via `infra/scripts/aliases.sh`, automatisch in .bashrc): `save`, `auth`,
`secrets`, `keys` (status/doctor/restore), `ports`, `quota`, `st`, `ll`,
`config-watchdog` (status/start/stop/log), `landscape-diff`, `ocver`
(opencode-Versionspin: check/latest/bump/install), `csecret` (Codespaces-Secrets).

## Enthalten

- Ports 3000/8000 (Apps), 4096 (opencode-Server für Multi-Client), 8001 (glm2api LLM-Proxy), 9878 (antigravity-proxy), 6082/5920 (Browser-VNC, nur lokal)
- opencode, Default-Modell `antigravity/gemini-3.8-flash` (fest auf high Thinking gemappt)
- Freebuff CLI: kostenloser, werbefinanzierter Coding-Agent, **ohne
  Versions-Pin** (`freebuff@latest`, Entscheidung 2026-09-27), liegt wie opencode
  ephemer in `$HOME/.local/share/freebuff` (Wrapper `freebuff` im PATH), Login
  verschlüsselt im Secret-Bundle → in jedem Codespace eingeloggt.
  `cd <projekt> && freebuff`. Die vier Byte-Patches (Mausrad, Entf in
  `/history`, …) liegen in `infra/scripts/freebuff_patch.py` und werden vom
  Wrapper bei jedem Start nachgezogen — der Launcher ersetzt das Binary sonst
  bei jedem Update.
  Kein API-Endpoint für opencode (kein OpenAI-kompatibler Server, kein
  Headless-Modus); werbefinanziert, Prompts werden zur Ad-Personalisierung
  ausgewertet → nichts Geheimes rein.
- `config/passphrase`: Entschlüsselungs-Passphrase als Klartext im Repo → jeder
  eigene Codespace entsperrt sich beim Start selbst. Sie ist NUR ein
  Entschlüsselungswort — nie ein Secret/PAT als Passphrase zweckentfremden
  (der alte PAT wurde dadurch geleakt und von GitHub revoked).
- `config/secrets.enc` (+ Manifest): verschlüsseltes Bundle mit
  `pat`, `antigravity-oauth_creds.json`,
  `chatglm-refresh-token`, `env`, `opencode-auth.json`, `rclone.conf`,
  `freebuff-credentials.json` → landen beim Unlock unter
  `~/.config/landscape/`, `~/.local/share/opencode/auth.json`, `.env`,
  `~/.config/rclone/` bzw. `~/.config/manicode/` (Freebuff-Login).
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
  das Secret ist also Komfort, keine Voraussetzung. **Codespaces-Secrets sind
  repo-scoped** (`visibility=selected`) und werden nur in Codespaces **dieses**
  Repos injiziert. Für den Account-Wechsel wird der Codespace aber aus dem
  **Fork** erstellt — und der Fork ist im Scope standardmäßig **nicht**
  enthalten: live am 2026-09-26 geprüft, im Fork-Codespace waren *beide*
  Variablen leer (es lief über Token-Datei und Repo-Fallback, also unauffällig,
  aber ohne Git-Auth aus dem Secret). Nach dem Fork daher einmalig im UI
  `github.com/settings/codespaces` → Secret → *Selected repositories* → Fork
  nachtragen. Per API nicht möglich: der ambient Codespace-Token bekommt 403
  (`not accessible by integration`), der Bundle-PAT 404. `csecret scope NAME
  owner/name` versucht es und sagt dir, wenn es nicht geht.
  **Setzen per Skript statt Web-UI:** `./infra/scripts/codespace-secret.sh set-passphrase` (Alias `csecret`) liest den
  Wert aus `config/passphrase`, verschlüsselt ihn libsodium-sealed-box mit dem
  Public Key aus `GET /user/codespaces/secrets/public-key` und legt ihn per
  `PUT /user/codespaces/secrets/…` mit erhaltenem Repo-Scope ab. Das eliminiert den
  Fehler, der zweimal passiert ist (2026-09-26 stand dort der PAT). Weitere
  Befehle: `csecret list` (alle Secrets inkl. Scope), `csecret set NAME DATEI`,
  `csecret scope NAME owner/name`, `csecret delete NAME`. **Token-Rechte (live geprüft):** der ambient
  Codespace-Token darf public-key/list/scope-put nicht (403), der Bundle-PAT darf
  public-key und list, liefert für `…/repositories` aber `total_count: 0` —
  deshalb wird der Ambient-Token bevorzugt und ein nicht lesbarer Scope **nicht
  geraten**, sondern mit Fehler abgebrochen (sonst würde der PUT den Scope
  stillschweigend auf ein Repo zurücksetzen).
- `glm2api` nutzt lokal `local` als Platzhalter. Ein Literalwert bleibt getrackt und steht deshalb hier ausgeschrieben statt als Verweis auf einen gelöschten Audit: **Antigravity** trägt den selbst erzeugten Admin-Key des lokalen Proxys (`127.0.0.1:9878`, nur von `localhost` erreichbar). Frühere externe Provider (`xinjianya`, `tokenrouter`) wurden aus `opencode.json` entfernt.
- **Keine `{file:...}`-Referenzen mehr:** `opencode.json` verweist seit dem
  Entfernen der externen Provider (`xinjianya`, `tokenrouter`) auf keine
  Key-Datei mehr. Das frühere Key-Subsystem (`infra/scripts/keys.sh`, am
  2026-10-21 entfernt) hatte damit keine Eingabe mehr und ist entfallen —
  inklusive der Aliase `keys`/`keys-doctor`/`keys-restore` und des
  Verify-Checks „Key-Dateien OK". `secrets.sh status` prüft weiterhin, ob das
  Bundle entschlüsselbar ist; `opencode-version.sh check` liefert einen
  ehrlichen Exit-Code (0 nur, wenn wirklich alles stimmt). Beide sind damit
  als Gate in `verify-codespace.sh` brauchbar, statt nur Text auszugeben.
  **Secret-Rechte:** alle Secret-Dateien (`config/passphrase`, `config/secrets.enc`,
  `config/secrets.manifest`, `llm-proxies/glm2api/.env`)
  liegen auf 600, `.runtime` auf 700. `infra/scripts/secret-perms.sh` erzwingt das
  und entfernt die geerbte POSIX-Default-ACL (`rwx rwx rwx`), die `umask` aushebelt;
  `verify-codespace.sh` prüft die Rechte („Secrets nicht world-readable").


## opencode-Konfiguration (`.opencode/`)

Provider (`opencode.json`, Default `antigravity/gemini-3.8-flash`):

| Provider | Modelle | Auth |
|---|---|---|
| **glm2api** | glm-5.3 | lokal, Port 8001, kein Key |
| **antigravity** | claude-opus-4-6 (100k Context, Thinking 1k/4k/8k), gemini-3.8-flash (1M, 64k Output, fest auf High-Thinking gemappt) | lokal, Port 9878, Google Cloud Code OAuth |

- `mcp.opencode-sessions`: Session-Verwaltung direkt auf der SQLite-DB
  (`infra/mcp/opencode-sessions-mcp.js`, zero deps) — list/preview/delete/search,
  kaskadierende Löschung + Orphan-Event-Cleanup, schützt aktive/aktuelle/geteilte
  Sessions, `confirm:true` Pflicht. **Dual-Schema (v1 + v2):** erkennt
  `session_v2` automatisch, liest v2 aus `session_v2`/`session_message` und
  entfernt in migrierten DBs auch die v1-Altzeilen. Details: `infra/mcp/README.md`.
- `agent/glm2api.md`: Arbeits-Subagent fest auf `glm2api/glm-5.3` (Haupt-Proxy).
- `tui.json`: Maus-Capture **aus** (`mouse: false` ist Absicht: sobald eine App
  Mouse-Reporting einschaltet, behandelt das Terminal Mausereignisse als
  App-Eingaben — Text markieren und kopieren geht dann nicht mehr.
  **Nicht auf `true` ändern.**)
- **v2-TUI-Config:** `config/opencode-cli.json` ist die v2-Entsprechung; setup.sh
  installiert sie nach `~/.config/opencode/cli.json`. v1 ignoriert die Datei.
  Die Keybinds sind 1:1 zu `tui.json` gemappt; `infra/tests/test_opencode_cli_config.py`
  haelt beide Seiten synchron (Maus aus, Bildvorschau an, Halbseiten-Scrollen).
- **Das Mausrad lässt sich in VS Code nicht umleiten.** Ohne Mouse-Reporting
  übersetzt **xterm.js das Rad in `up`/`down`** (live gemessen: die Testsession
  bekam `ESC[A`/`ESC[B`, siehe `infra/scripts/freebuff-pty.py`-Log). Eine
  Keybinding auf `mousewheel up/down` ist **kein gültiges Keybinding** — laut
  VS-Code-Referenz besteht die `key`-Liste aus Buchstaben, Ziffern, Pfeilen,
  `pageup`/`pagedown`, `home`/`end`, `tab`/`enter`/`escape`/`space`/`backspace`/
  `delete` und Nummernblock; `mousewheel` steht nicht darin, wird also nicht
  dispatcht. **Diese Keybinding wurde probeweise eingefügt, hat nie gefeuert und
  wurde wieder entfernt** — der Versuch steht im Changelog, die Lehre unten.

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
./infra/scripts/glm2api.sh start    # starten (idempotent, PID-Datei/Log-Rotation)
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
`.env` aus `llm-proxies/glm2api/.env.dist` (Port 8001, Guest-Mode, secret-frei), `uv sync`
(venv), Start. Kein Klon, kein Patch-Anwenden, keine externen Abhängigkeiten.
- **Die Betriebs-Config hat genau eine Saat-Vorlage: `.env.dist`.** Drei
  Stellen sät aus ihr — `rebuild.sh`, `infra/scripts/glm2api.sh:prepare_env`
  und `config.py:ensure_env_file()` (zur Laufzeit, wenn `.env` fehlt).
  `secrets.sh` stellt nur die **Wurzel**-`.env` aus dem Bundle wieder her.
  Bis 2026-10-21 lag daneben eine zweite Kopie `.env.example`, aus der
  `ensure_env_file()` las; die U1-Entscheidung (1M → 300k History-Zeichen,
  `14bae8f`) kam damals nur in einer der beiden an. Ein frischer Codespace
  hätte die alte Konfiguration geseedet, während der laufende Betrieb korrekt
  blieb — der Fehler war nur beim Neuaufbau sichtbar. Die Kopie ist entfallen;
  `tests/test_config.py::test_only_one_shipped_env_template` hält die
  Eine-Quelle-Regel fest. Die Wurzel-`.env.example` ist davon unabhängig (sie
  ist der Hinweis auf die per `secrets.sh` verschlüsselte Wurzel-`.env`, keine
  glm2api-Vorlage).
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
- **Commit-Signierung: bewusst AUS** (Nutzerentscheidung 2026-10-21).
  `setup.sh` und `auth.sh` setzen repo-lokal `commit.gpgsign=false`, `save.sh`
  committet mit `git -c commit.gpgsign=false` (gilt auch bei geerbter Config).
  Grund: der Codespaces-Signierer `/.codespaces/bin/gh-gpgsign` (aus
  `/etc/gitconfig`) benutzt den Codespaces-`GITHUB_TOKEN`, ein
  App-/Integrationstoken, und lehnt jede Signatur ab — **`403 Author is
  invalid`** (nicht Identität oder Token-Scope; `gh api user/emails` liefert
  „Resource not accessible by integration"). Die frühere SSH-Lösung
  (2026-09-27 bis 2026-10-21: `gpg.format=ssh`, `user.signingkey`,
  `config/git-allowed-signers`) ist mit `config/git-allowed-signers` entfernt;
  sie brachte auf GitHub nur „signed, unverified", weil der Key pro Codespace
  neu ist. Kein Ersatz, keine Prüfung im Verify — nichts hängt an Signaturen.

- **Freebuff CLI** (werbefinanzierter, kostenloser Coding-Agent von CodebuffAI),
  **keine Versions-Pin** (Nutzerentscheidung 2026-09-27: `freebuff@latest`, weil
  der Pin ohnehin nichts brachte — der Launcher lädt das native Binary selbst
  nach), automatisch via setup.sh — **nach** dem Secrets-Schritt, weil der Login
  aus dem Bundle kommt. Modell **bewusst wie opencode**: das Repo *verwaltet* die
  Installation, die Dateien liegen ephemer in `$HOME/.local/share/freebuff`, der
  Einstiegspunkt ist der Wrapper `~/.local/bin/freebuff` (PATH via `aliases.sh`).
  **Nichts unter `/workspaces`** — ein früherer Zwischenstand hatte das native
  Binary zwischen `/workspaces/freebuff/bin/` und `$HOME` hin- und herkopiert;
  der ist verworfen.
  - **Zwei Ebenen, die man unterscheiden muss:** die npm-Seite (Launcher, ohne
    Pin) und das **native Binary, das der Launcher selbst nachlädt** — es zieht
    immer das *neueste* veröffentlichte Binary (live belegt: npm-Pin 0.0.203,
    Launcher zog 0.0.204 und schrieb `.freebuff-0.0.204-*.tar.gz.part` nach
    `$HOME`). Das heißt: **jedes Update ersetzt ungefragt `~/.config/manicode/
    freebuff`** — und die vier Byte-Patches (siehe „Byte-Patches") liegen als
    Bytes in genau dieser Datei. Sie sind deshalb nicht mehr Sache des
    Codespace-Builds allein, sondern werden **bei jedem Start** nachgezogen
    (`freebuff_patch.py --ensure` aus dem Wrapper). Die `.part`-/
    `.freebuff-download-temp-*`-Reste räumt dasselbe Skript auf (live am
    2026-10-02: drei Reste mit je 133 MB).
  - **Binary-Pfad ist im Launcher hart verdrahtet:** `~/.config/manicode/freebuff`
    (`launcher.js`: `path.join(os.homedir(), '.config', 'manicode')`). Das native
    Binary kennt zusätzlich `FREEBUFF_CONFIG_DIR` — **nicht** setzen: der Launcher
    würde den Login weiter nach `~/.config/manicode` schreiben, das Binary sucht
    ihn dann unter dem anderen Pfad, und es landet bei jedem Start ein
    `No auth token available` im Log.
  - **Preis des `$HOME`-Modells:** `$HOME` ist ephemer, also lädt jeder neue
    Codespace das 136-MB-Binary neu. Frische Installation live gemessen:
    **12-24 s** (davon 1-3 s npm, Rest Download, schwankt mit dem Netz — vier
    Läufe: 12,3 / 12,6 / 16,3 / 23,6 s). Der Login überlebt das, weil er im
    Secret-Bundle liegt.
  - **Login:** `~/.config/manicode/credentials.json` (Account-Token +
    Fingerprint) liegt **verschlüsselt** in `config/secrets.enc`
    (`secrets.sh` packt `freebuff-credentials.json`, Unlock legt es mit 0600
    zurück) → in jedem neuen Codespace eingeloggt. `freebuff login` geht nicht
    headless (gibt eine Browser-URL aus und wartet). **Der Token kann
    serverseitig ablaufen** — dann einmal `freebuff login` + `secrets.sh lock`
    + `save`.
  - **Kosten/Modell:** 100 Freebucks/Tag (Reset Mitternacht PT), werbefinanziert
    (Text Ads, Prompts werden zur Ad-Personalisierung ausgewertet), Modelle mit
    Training-Freigabe u.a. DeepSeek V4/V4.1 Flash, Muse Spark, Space Bunny
    Alpha. **Nicht** mit Secrets, `.env` oder Kundencode füttern. Session =
    60-Minuten-Slot (`/end-session` beendet vorzeitig, ungenutzte Freebucks
    werden erstattet, nach 5 min Idle läuft keine Zeit mehr).
  - **Keine API für opencode:** es gibt keinen OpenAI-kompatiblen Endpoint und
    keinen Headless-Modus (einziges CLI-Kommando ist `login`); die interne
    `codebuff.com/api/v1/freebuff/session`-Admission wäre ein Shim, kein Weg.
     Für gratis-Modelle in opencode bleiben die BYOK-Pools (Groq, OpenRouter
     `:free`, Z.ai GLM-Flash).
  - **Copy/Paste wie opencode `mouse: false`:** Freebuff (opentui) schaltet beim
    Start Mouse-Reporting ein (`CSI ? 1000/1002/1003/1006/1015/1016 h`) — danach
    ist die native Textauswahl des Terminals tot, man kann nichts markieren und
    kopieren. **Einen Config-Kniff gibt es nicht:** weder `settings.json`-Key
    (dort werden nur `mode`, `adsEnabled`, `freebuffModel` gelesen), noch
    CLI-Flag, noch Env-Variable — am Binary 0.0.204 verifiziert; opentui kennt
    intern `useMouse` (Default `true`), Freebuff setzt es nicht. Lösung wie bei
    opencode, nur außen: `infra/scripts/freebuff-pty.py` (pty-Relay) filtert
    **nur** die Maus-Sequenzen aus dem Output, lässt aber `?2004` bracketed
    Paste, `?1004` Fokus, `?1049` Alternate Screen und Kitty-Keys unangetastet;
    Eingaben und Cursor-Position-Antworten gehen unverändert durch, SIGWINCH
    wird durchgereicht, Exit-Code des Kindes wird zurückgegeben. Der Wrapper
    `~/.local/bin/freebuff` startet das TUI nur bei echtem TTY darüber,
    sonst direkt (`FREEBUFF_NO_PTY_FILTER=1` erzwingt den Direktstart).
    **Live verifiziert, nicht behauptet:** Aufzeichnung eines echten
    TUI-Starts mit leerem Config-Dir — mit Filter **null** Maus-Modi im Stream,
    ohne Filter `?1000h ?1002h ?1003h ?1006h`; TUI rendert in beiden Fällen
    (Login-Screen), Bidirektional-Relay und Exit-Code (42) im Einzeltest.
    Preis wie bei opencode: das Mausrad scrollt wieder im Terminal statt in der
    App. **Nach einem Update des Wrappers (`freebuff-install.sh`) muss eine
    laufende Session neu gestartet werden** — der Filter hängt am Startpfad.
  - **Rückweg:** `rm -rf ~/.local/share/freebuff ~/.local/bin/freebuff ~/.config/manicode`
    (Bundle-Eintrag `freebuff-credentials.json` bleibt, ist nur ungenutzt).
- **opencode ist gepinnt, mit EINER Quelle der Wahrheit:** dem
  `@opencode-ai/plugin`-Dep in `.opencode/package.json`. Das ist genau die Version,
  die opencode für seinen Plugin-Ladepfad selbst nachinstalliert — deshalb ist der
  Pin auch der richtige: laufen beide auseinander, schreibt opencode den Dep beim
  ersten TUI-Start um und der Codespace hinterlässt dauerhaft uncommittete
  Änderungen. `.devcontainer/setup.sh` liest die Version von dort und installiert
  genau sie (`opencode.ai/install --version`); weicht die vorhandene Installation
  ab, aktualisiert setup.sh (Vergleich über `opencode-bin`, weil der
  Multi-Client-Wrapper `opencode` ersetzt). **Pin wechseln:**
  **Aktueller Pin: `2.1.2`** (Stand 2026-10-21; Quelle `.opencode/package.json`,
  Dep `@opencode/cli` + `package-lock.json`) — die einzige Versionszahl im
  Repo. `./infra/scripts/opencode-version.sh bump` (Alias `ocver`) — updated Pin **und**
  Lock in einem Schritt, ein Commit. `ocver check` zeigt Repo-Pin / Lock /
  installiert / Latest und ein Urteil; `ocver latest` nur die neueste Release.
  Bewusst **kein** Auto-Tracking: ein automatisch nachgeführter Pin würde bei jedem
  Release das Repo verändern und über den Autosave-Daemon die Historie
  beschreiben. Ein Codespace, ein Build — der laufende Server nutzt bis zum
  Neustart seine alte Version.

### opencode v2 — Vollzogener Cutover (2026-10-21)

- **v2.1.2 ist der aktive Default.** Der Repo-Pin steht auf `2.1.2`
  (`@opencode/cli`).
- **DB-Schema v2:** `session_v2`/`session_message` statt `session`/`message`/`part`.
  Migrierte DBs behalten die v1-Tabellen; neue Sessions schreiben nur v2.
  Eine Sicherung der v1-DB vor dem Cutover liegt unter
  `~/.local/share/opencode/opencode.db.pre-v2-backup`.
- **MCP ist portiert:** `infra/mcp/opencode-sessions-mcp.js` (v2.0.0) erkennt
  beide Schemata, zählt v2-Parts aus `session_message.data.content` und löscht
  in migrierten DBs beide Welten.
- **TUI-Config:** `config/opencode-cli.json` + Setup-Installation nach
  `~/.config/opencode/cli.json`. Maus-Capture bleibt aus (`mouse: false`),
  Bildvorschau und Halbseiten-Scrollen aktiv.
- **Wrapper:** v2 wird direkt durchgereicht (Managed Service, kein `attach`
  mehr nötig).
- **Cutover- & Rollback-Werkzeug:** `infra/scripts/opencode-cutover.sh` erlaubt
  Statusprüfung, erneuten Cutover sowie Rollback auf v1.18.32.
- **Git-Identität folgt dem Account** (siehe Secrets-/Auth-Abschnitt): `auth.sh
  setup` leitet Name + `<id>+<login>@users.noreply.github.com` aus dem Token ab und
  setzt sie **repo-lokal**; `auth.sh identity` zeigt sie. Beim Account-Wechsel
  damit nichts zu tun. `store_token` überschreibt einen funktionierenden Token
  **nicht** mit einem, der sich nicht auflösen lässt (Tippfehler ⇒ Push tot bis
  zum nächsten Codespace). Override: `GIT_USER_NAME=… GIT_USER_EMAIL=… auth.sh setup`
  — nur mit Bedacht, MAIN ist öffentlich und eine echte Adresse landet mit im Commit.
- **Linter automatisch im Commit (seit 2026-10-01):** `.githooks/pre-commit`
  (versioniert im Repo) fährt die Checks der **betroffenen** Sprache: glm2api
  `ruff`+`mypy`, antigravity-proxy `go vet`+`gofmt -l`, MAIN-eigenes JS
  (`infra/**.js`) `node --check` — jeweils **nur** wenn die passenden Dateien
  gestagt sind, damit Commits an fremde Teile nicht ausgebremst werden.
  `setup.sh` setzt `core.hooksPath=.githooks` (vom Repo-Root, relativ).
  Der Hook fasst den Index **nicht** an (kein `git add`, kein `--fix`/`--write`);
  Notausstieg `git commit --no-verify`. `verify-codespace.sh` prüft die Verdrahtung.
- **Go-Toolchain:** Go 1.25.7 (gepinnt, entspricht `mise.toml` im antigravity-proxy)
  nach `/usr/local/go` via setup.sh — das Proxy-Binary liegt nicht im Git und wird
  pro Codespace neu gebaut (`scripts/start.sh` baut automatisch nach, Fallback
  `/usr/local/go/bin/go`). PATH via `aliases.sh`. **Lint seit 2026-10-01:**
  `verify-codespace.sh` prüft `go vet ./...` + `gofmt -l` (read-only) für
  `antigravity-proxy`. `mise` ist **nicht** installiert — die
  `mise.toml`-Tasks (`test`/`format`) sind der Upstream-Weg; die direkten
  `go`-Befehle stehen in AGENTS.md §6.
- **Getrackte Ausnahme — am 2026-10-01 beendet:** `antigravity-proxy/auth`
  (ELF, ~9,8 MB) war ein 2026-09-28 bewusst geduldetes, versehentlich
  committetes Binary — kein Skript referenzierte es, das eigentliche Proxy-Binary
  `antigravity-oauth-proxy` liegt korrekt außerhalb des Git (`.gitignore`) und
  wird pro Codespace gebaut. Auf Nutzerwunsch entfernt (Blindlast raus, kein
  Nutzen). Zusammen mit den vier toten `setup_oauth*.sh`-Varianten, siehe
  Changelog 2026-10-01.
- **Deprecated (gelöscht 2026-09-10):** kompletter Chromium-Stack entfernt
  (`infra/browser/` Playwright 1.48.2, `.runtime/ms-playwright/`,
  `.runtime/chromium-profile/`, `browser-install.sh`, CDP-Port 9222).
  Rückweg: Commit revertieren — bzw. für Chromium-CDP: Playwright-Setup neu
  anlegen.

### Agenten-Anweisungen: die Save-Regel muss jeder Client kennen

**Nutzervorgabe (2026-09-27):** Der Nutzer arbeitet nie selbst unter `MAIN`; er
sagt einem Agenten „commite/pushe“ und erwartet, dass **jeder** Agent das ohne
Nachfrage tut. Damit das nicht vom jeweiligen Client abhängt, liegt die Regel in
den Client-Dateien, die der Client liest:

| Datei | Client |
|---|---|
| `AGENTS.md` | **Referenz und einzige Quelle** — opencode, Codex, jeder Agent, der `AGENTS.md` liest |
| `~/.gemini/settings.json` | Gemini CLI — kein Repo-File, sondern `context.fileName=["AGENTS.md"]` (siehe unten) |

**Nutzervorgabe (2026-09-27, später als die Client-Dateien):** Im Repo liegt
**nur `AGENTS.md`** — und damit ist der Punkt erreicht, an dem es nichts mehr
zu pflegen gibt. `CLAUDE.md` und `.cursorrules` waren zuerst raus, dann
`GEMINI.md`, zuletzt `.github/copilot-instructions.md` (Copilot wird nicht
benutzt). Grund ist nicht Geschmack, sondern die Fehlerquelle selbst: jede Kopie
ist ein zweiter Regeltext, der auseinanderdriftet (in der Historie standen
`AGENTS.md`/`CLAUDE.md`/`GEMINI.md` als 104-Zeilen-Duplikate mit einem Port, den
drei andere Dateien anders nannten). Ein Cursor, eine komplett neue Regel oder
ein geändertes `save.sh` erreicht eine Kopie nur, wenn sie jemand mitdenkt.
**Und der Preis dieser Regel ist ehrlich benannt:** ein Client, der
`AGENTS.md` nicht von selbst liest und keine User-Config dafür kennt, ist in
dieser Landschaft nicht abgedeckt — für Gemini und Claude ist das geprüft und
gelöst, für Copilot ist es irrelevant, weil der Client nicht verwendet wird.

**Gemini CLI liest `AGENTS.md` — über die User-Config, nicht über eine Kopie.**
Gemini CLI nimmt per Default **nur** `GEMINI.md` als Kontextdatei. Der PR, der
`AGENTS.md` als Default aufnehmen wollte (google-gemini/gemini-cli#24913), wurde
am 2026-05-12 **ohne Merge** geschlossen; Issue #28227 bestätigt den aktuellen
Stand (`DEFAULT_CONTEXT_FILENAME = 'GEMINI.md'` in
`packages/core/src/tools/memoryTool.ts`). Wer `GEMINI.md` einfach löscht,
bekommt also **leeren Kontext** — keine Warnung, keine Fehlermeldung, nur ein
Agent ohne Repo-Regeln und ohne Save-Pflicht. Der dokumentierte Ausweg ist
`context.fileName` in `~/.gemini/settings.json` (geminicli.com/docs/cli/gemini-md/).
`infra/scripts/gemini-context.sh` (neu, idempotent, `apply|status|unapply`)
setzt genau das, `setup.sh` ruft es bei jedem Codespace-Start auf. Damit ist die
Client-Zuordnung **Konfiguration in `$HOME`** statt Datei im Repo — dort gehört
sie hin, weil sie sich nicht mit dem Code ändert.

Das Skript merged über Python in die bestehende Datei (andere Schlüssel bleiben),
legt vorher ein `.bak` an und überschreibt **nichts**, wenn die Datei kaputt ist.
Getestet: frische Datei, Doppelaufruf, Merge mit bestehendem `"theme"`,
`unapply`, kaputte Datei (Exit 1, Datei unverändert).

**Copilot ist raus, weil der Client nicht benutzt wird (Nutzerentscheidung
2026-09-27).** `.github/copilot-instructions.md` war zwar nur ein 25-Zeilen-Zeiger
auf `AGENTS.md` und damit kein Duplikat — aber eine Zeigerdatei für einen Client,
den es in dieser Landschaft nicht gibt, ist nur noch ein Pflegeposten ohne
Nutzen. Der Unterschied zu Gemini ist der entscheidende: bei Gemini war der
Default-Dateiname falsch, den man nicht wegkriegt, ohne es zu ersetzen; Copilot
liest die Datei nativ, also **behebt das Löschen hier nichts und bricht nichts**,
es räumt nur auf. `.github/` verschwindet damit aus dem Repo (es enthielt
nur diese eine Datei).

**Claude braucht nichts — weder eine Datei im Repo noch eine Config in `$HOME`.**
Die Claude-Modelle laufen hier über den antigravity-Proxy **innerhalb von
opencode** (`antigravity/claude-opus-4-6`, `claude-sonnet-4-6`): opencode ist der
Client, und der liest `AGENTS.md`. Das Modell ist für die Kontextdatei
irrelevant — Kontext stellt der **Client** zusammen, nicht das Modell, ein
Modellname ändert daran nichts. Ein *eigener* Claude-Code-Client wäre mit diesem
Proxy ohnehin nicht möglich: er spricht nur Gemini-nativ (`/v1beta`) und
OpenAI-kompatibel (`/v1/chat/completions`, `server.go:132-135`) und hat **kein**
Anthropic-Messages-Endpoint — `/v1/messages` existiert nicht, und es gibt keinen
Catch-all. Genau den braucht Claude Code. (Klarstellung 2026-09-28: das betrifft
nur den antigravity-Proxy — der **glm2api**-Proxy hat `/v1/messages` sehr wohl
(`server.py`, Anthropic-Adapter Z. 743–872). Die beiden Proxys sind an dieser
Stelle nicht austauschbar.)

**Falls Claude Code später doch als eigener Client dazukommt, ist es trotzdem
konfigurationsfrei:** seit **v2.1.277** liest er `AGENTS.md` nativ, und der
Default (`claude-md-or-agents-md`) nimmt `AGENTS.md`, sobald keine `CLAUDE.md`
oder `CLAUDE.local.md` im Arbeitsverzeichnis oder darüber liegt — in diesem Repo
ist genau das der Fall. Umstellen lässt sich das nur in `~/.claude/settings.json`
unter `pluginConfigs."agents-md@builtin".options.instructionFiles` (in Projekt-
und Local-Settings wird der Wert ignoriert). Ausnahmen, in denen Claude nur
`CLAUDE.md` liest: Versionen vor v2.1.277, die erste Session nach einem Upgrade
von ≤ v2.1.276, ein deaktiviertes `agents-md`-Plugin sowie einzelne Sessions
vor v2.1.281 (Bedrock oder Telemetrie aus). **Dafür wird hier bewusst keine
`CLAUDE.md` angelegt** — sie wäre genau die Kopie, die es nicht mehr geben soll,
und sie wird nur für Altstände gebraucht, nicht für den Normalbetrieb.

Komplett entfernt, weil die zweite Kopie die Fehlerquelle war — gestrichen ist
dabei die **Drift-Gefahr**, nicht die Information. Die drei Zusätze, die
diese Sitzung in `AGENTS.md` selbst erzwungen hat, stehen dort nach wie vor:
**nur eigene Pfade committen** (`git commit -- <pfad>`, weil `save.sh` vorher
`git add -A` macht und das Repo shared ist), **kein Autosave-Daemon** (womit der
Save-Aufruf der einzige Auslöser für Commit *und* Backup ist) und **Testläufe
nicht committten**.

**Gegen das Auseinanderlaufen gibt es einen Check:** `verify-codespace.sh`
prüft, dass `AGENTS.md` existiert und die Save-Regel enthält, dass **keine**
Client-Kopien zurückgekommen sind (`GEMINI.md`/`CLAUDE.md`/`.cursorrules`/
`AGENT.md`/`.github/copilot-instructions.md`) und dass Gemini CLIs
`context.fileName` wirklich auf `AGENTS.md` zeigt. Ein Client, der `AGENTS.md`
nicht von selbst liest, braucht **keine** Kopie, sondern eine User-Config
(wie Gemini) — eine Kopie im Repo ist ab jetzt der Fehlerfall, kein Muster.

### Drive-Backup: Fehler werden nicht mehr verschluckt

`save.sh` rief das Backup mit `|| true` auf — ein fehlgeschlagenes Backup sah
unverändert wie ein erfolgreicher Save aus. Da Drive die **einzige** Kopie
außerhalb von GitHub ist, war das der teuerste stille Fehler der Repo-Sicherung.
Seit 2026-09-27 meldet `save.sh` den Fehler nach dem erfolgreichen Push:

```
WARNUNG: Push ok, aber das Google-Drive-Backup ist FEHLGESCHLAGEN.
         Drive ist damit die veraltete Generation — nicht vergessen:
         ./infra/scripts/gdrive-backup.sh backup --force
```

**Der Push-Erfolg wird weiterhin nie gefährdet** (der Backup-Hook läuft nach
dem Push und beendet `save.sh` nicht mit Fehler). Verifiziert mit absichtlich
kaputtem Backup-Skript — die Warnung erscheint, der Save meldet Erfolg.

**Kein periodischer Backup-Timer, bewusst** (Nutzerentscheidung): es wird nur
gesichert, wenn ein Agent etwas committen will. Der Preis ist dokumentiert: fällt
der Codespace zwischen zwei Arbeitsgängen weg, ist der Drive-Stand so alt wie der
letzte `save.sh`.

### Maus, Copy/Paste & Scrollen in TUIs (opencode + Freebuff)

**Es gibt genau eine Betriebsart, und sie ist die mit dem pty-Filter (Maus aus).**
Nach vier Umbau-Runden entschieden, weil sie die einzige ist, die
`Ctrl+C`/`Ctrl+V` **und** Mausrad-Scrollen gemeinsam liefert.

| Fähigkeit | Zustand | Wie |
|---|---|---|
| `Ctrl+C` kopiert | ✅ | Terminal-Auswahl per Maus-Drag, dann `Ctrl+C`. xterm.js kopiert **nur mit Auswahl**; ohne Auswahl geht `Ctrl+C` als `^C` an die App = Interrupt |
| `Ctrl+V` fügt ein | ✅ | bracketed Paste (`?2004h` bleibt vom Filter unangetastet), live geprüft: `ESC[200~textESC[201~` landet in der Eingabe |
| Mausrad scrollt | ✅ | ohne Mouse-Reporting schickt xterm.js das Rad als `up`/`down`; der Filter hängt sie **kontextabhängig** auf `PageUp`/`PageDown` um |
| Output-Block aufklappen | ❌ | nur per Klick, und Klicks kommen nicht durch (siehe Punkt 1) |

**Warum genau das die richtige Wahl ist — und nicht die Maus.** Beide Wege
wurden gebaut und am echten TUI-Stream verifiziert:

| | Maus an (Filter aus) | **Maus aus (Filter an, Default)** |
|---|---|---|
| `Ctrl+C` | ✗ Interrupt der App | ✅ **kopiert** |
| `Ctrl+V` | ✅ | ✅ |
| Rad scrollt die Unterhaltung | ✅ | ✅ (über die Umleitung) |
| Rad scrollt den Output-Block | ✅ | ✗ |
| Block aufklappen (5 → voll) | ✅ | ✗ |

Die Entscheidung fiel gegen die Maus, weil **Kopieren im Alltag häufiger ist als
ein langer Output-Block** — und weil der Verlust bei der Maus *auch* das
Kopieren betrifft, während der Verlust bei der Maus-aus-Variante nur den
Block betrifft, dessen vollständigen Inhalt es trotzdem gibt: `/copy` (Alias
`copy-chat`) legt den **gesamten** Chat in die Zwischenablage, `/export`
(Alias `export-chat`) schreibt ihn als Datei.

**1. Was die Maus ausliefert — und warum sie den Filter nicht überlebt.**
Belegt am Bundle, nicht vermutet:

* Output-Bloecke rendert `wAH` — `expandable$=!0, maxVisibleLines:L` mit
  `J = L ?? (expandable ? 5 : 10)`, also **5 Zeilen collapsed, 10 bei nicht
  aufklappbarem Block**. Ausklappen: `onClick`.
* opentui vergibt Fokus **per Klick**:
  `processMouseEvent($), this.autoFocus && $.type==="down" && $.button===0 … while(L){if(L.focusable){L.focus();break}L=L.parent}`
  und **nur ein fokussierter ScrollBox** übersetzt `pageup`/`up` in `scrollBy`
  (0,5 bzw. 0,2 Viewport).
* freebuff setzt nirgends `focusable` und fokussiert nur die Eingabe
  (`.focus()` auf `inputRef`), und die **vollständige** Action-Liste der App
  lautet `toggle-agent-mode`, `toggle-all`, `toggle-dock-panel`,
  `toggle-sponsored-dock` — **kein `expand`, kein `collapse`, kein `scroll-block`**.

**Der Fokus im Output-Block entsteht also ausschließlich per Klick, und der
Filter entfernt genau diese Klicks.** Das ist der Preis der Wahl — und er ist
begrenzt: der Inhalt ist vollständig erreichbar, nur nicht *im TUI*
sichtbar.

**2. Was der Filter tut (und was er unangetastet lässt).** `freebuff-pty.py`
ist ein pty-Relay, das ausschließlich Mouse-Reporting entfernt
(`?1000/1001/1002/1003/1005/1006/1015/1016 (h|l)`). Unangetastet: `?2004`
bracketed Paste, `?1004` Fokus, `?1049` Alternate Screen, Kitty-Keys. Am echten
TUI-Stream verifiziert: alle vier Maus-Sequenzen weg, `?2004h` und `?1004h`
da. Bidirektional-Relay, SIGWINCH-Durchreichung und Exit-Code sind
implementiert und getestet.

**3. Wie Opencode und Freebuff aufgebaut sind (Pfeiltasten, PageUp/Down und Mausrad).**
Das Fundament ist die Arbeitsweise von `xterm.js` im Browser:
Sobald Mouse-Reporting deaktiviert ist (damit native Textauswahl und `Ctrl+C` / `Ctrl+V`
funktionieren), sendet der Browser beim Drehen des Mausrads im Alternate Screen Buffer
hartcodiert dieselben Bytes wie die Pfeiltasten der Tastatur:
- Rad hoch = `\x1b[A` (Pfeil hoch)
- Rad runter = `\x1b[B` (Pfeil runter)

Da xterm.js und VS Code keine Einstellung bieten, um das Mausrad im Terminal auf andere
Sequenzen umzulegen, müssen die TUI-Anwendungen bzw. ihre Umhüllungen das Verhalten regeln:

#### A. Wie Opencode aufgebaut ist (tastatur-first, native Config)
Opencode besitzt eine eigene Keybinding-Konfiguration (`.opencode/tui.json`):
```json
{
  "mouse": false,
  "keybinds": {
    "messages_half_page_up": "up,ctrl+alt+u",
    "messages_half_page_down": "down,ctrl+alt+d",
    "input_move_up": "none",
    "input_move_down": "none",
    "history_previous": "ctrl+up",
    "history_next": "ctrl+down"
  }
}
```
* **Mausrad / Pfeiltasten:** Da `messages_half_page_up: "up"` gesetzt ist, scrollen Auf-/Ab-Pfeile die Unterhaltung in Halbseiten-Schritten.
* **Eingabezeile:** `input_move_up: "none"` verhindert, dass Pfeiltasten den Prompt oder die Prompt-Historie verschieben.
* **Historie:** Weicht bewusst auf `ctrl+up` / `ctrl+down` aus.
* Opencode benötigt keinen PTY-Filter für Tasten, weil es eine vollständige native Keybind-Engine besitzt.

#### B. Wie Freebuff aufgebaut ist (Mausrad 1:1 PageUp/Down + native Menüs)
Freebuff besitzt keine Keybinding-Konfigurationsdatei. Deshalb wird die Trennung
über zwei abgestimmte Mechanismen erreicht:

**Alle Byte-Patches liegen in `infra/scripts/freebuff_patch.py`** (nicht mehr in
`freebuff-install.sh` — das Skript installiert nur noch und ruft den Patcher
auf). Vier Patches, alle **längengleich** (das Bundle hängt an Fixed Offsets im
ELF), alle mit **Mustersuche statt Namenssuche** und alle mit der Regel
`!= 1 Treffer → unangetastet melden, nie raten`:

1. **Scroll-Schrittweite (`patch_scroll_step`):** freebuff springt hartcodiert
   80 % des Viewports pro `scroll-up` (`Math.floor(X*VAR)` mit `VAR=0.8` neben
   `viewport.height`; der Variablenname ist von `fOA` über `$hA` bis `jzA`
   umbenannt worden — deshalb Mustersuche). Gepatcht auf **0,5**, also eine halbe
   Seite wie opencode (`messages_half_page_up: up`).

2. **Mausrad = Scroll (`patch_arrow_scroll`):**
   Im kompilierten Bundle von `~/.config/manicode/freebuff` leitet ein 90-Byte-Patch
   `case "history-up"` und `case "history-down"` im Action-Dispatcher direkt auf `onScrollUp()`
   und `onScrollDown()` um — ohne Maus-Reporting ist das Mausrad dasselbe Byte wie die
   Pfeiltaste, also ist dieser Patch das, was das Rad überhaupt scrollen lässt.
   *Sicherheitsnetz:* Falls ein nativer Pfeil bei leerem Prompt durchrutscht, scrollt er
   die Unterhaltung statt die Prompt-Historie zu verändern.

3. **Saubere Wort-/Zeilengrenzen (`patch_word_boundary`):**
   In Freebuffs Wortbewegungsfunktionen (0.0.204 hießen sie `LGA`/`_GA`, in 0.2.12
   `iKA`/`yKA` — **der Minifier benennt um**, deshalb greift der Patch über die
   gefundenen Bezeichner) fraß die originale Schleife
   (`while($>0&&/\s/.test(H[$-1]))$--;while($>0&&!/\s/.test(H[$-1]))$--;`)
   Leerzeilen und das vorherige Wort in einem einzigen Schritt mit, sodass der Cursor über Zeilen hinweg
   immer sofort am Zeilenanfang landete und `Strg+Backspace` die Zeile darüber mitlöschte.
   Der Patch trennt Whitespace- und Wortschritte sauber (`s = $>0 && /\s/.test(...)`):
   Steht der Cursor nach Zeilenumbrüchen am Zeilenanfang (`|Hey`), springt `Strg+Links` bzw. löscht
   `Strg+Backspace` präzise bis zum Zeilenende der vorigen Zeile (`Hey|`), statt das Wort mitzureißen.

4. **Session-Löschung in `/history` (`patch_history_delete`):**
   Freebuff implementiert das Löschen von Chats in `/history` ausschließlich per Mausklick auf `[×]` (`onClick: () => f(X, v)`),
   bietet jedoch kein Tastaturkürzel im UI an (`onKeyIntercept` leitete nur Up/Down/Right/Enter/Esc/Ctrl+C ab).
   Weil das Mouse-Reporting für das benutzerdefinierte Setup (Mausrad-Scrollen, native Terminal-Auswahl, Copy/Paste)
   im PTY-Filter bewusst deaktiviert ist, empfing die App keine Mausklicks und Sessions waren unlöschbar.
   Der atomare Patch erweitert `onKeyIntercept` um `Delete` (`Entf`), `Ctrl+D` und `Ctrl+X` auf der fokussierten Session
   (`s = F[R]`), ruft die native Löschaktion `l(s)` auf und aktualisiert die Statuszeile längengleich
   (`Click [×] to remove` -> `Del / Ctrl+D to remove`; **optional** — der Text fehlt in
   0.2.12, der Patch selbst sitzt trotzdem).

5. **Update-Festigkeit (`--ensure` aus dem Wrapper, Stamp-Datei):**
   Weil der Launcher das Binary jederzeit ersetzt, prüft der Wrapper **bei jedem
   Start** `freebuff_patch.py --ensure`: eine Stamp-Datei (Größe + mtime +
   Formatversion) gegen das Binary, patchen nur bei Änderung. Normalfall **ein
   `stat()` (~0,09 s)**, nach einem Update einmalig ein Durchlauf über 136 MB
   (**2,4 s** live gemessen, inkl. Schreiben und Starttest `freebuff --version`).
   Passt ein Muster nicht mehr (Struktur-Drift), startet freebuff trotzdem und
   meldet es: Exit 1, Zustand in `~/.config/manicode/freebuff-patch.status`.
   **`--check` schreibt nichts** und ist der read-only Verifier in
   `verify-codespace.sh` („freebuff-Patches sitzen").** Tests:
   `infra/tests/test_freebuff_patch.py` (21 Fälle) pinnen die Update-Festigkeit —
   das Fixture trägt **absichtlich andere Bezeichner** als das echte Bundle, ein
   Test prüft die Idempotenz (das hätte den Footer-Text-Bug gefangen) und einer,
   dass generierte Bezeichner keine belegten Namen kollidieren.

6. **PTY-Filter (`infra/scripts/freebuff-pty.py`):**
   * **Im Chat-Fenster (1:1 Replikation von PageUp/PageDown):**
     Egal ob der Prompt leer ist oder Text darin getippt wird: Auf-/Ab-Pfeile werden
     **immer und sofort zu `PageUp` (`\x1b[5~`) und `PageDown` (`\x1b[6~`)**.
     *Hintergrund:* Freebuff ignoriert Pfeiltasten bei befülltem Prompt (`return {type: "none"}`),
     während `PageUp`/`PageDown` immer und ausschließlich das Nachrichtenfenster scrollt und den
     Schreibbanner nie berührt.
   * **In Menüs & Modaldialogen (Pfeiltasten 100% nativ):**
     - **Slash-Menü (`/`):** Erkannt über `text.startswith("/")` → Pfeiltasten nativ für die Befehlsauswahl.
     - **Modale Screens (`/history`, `/model`):** Erkannt über Befehl und Screen-Muster
       (`Select a chat to resume`, `Search chats...`, `choose model`) → Pfeiltasten nativ für die Listenauswahl.
     - **Agenten-Fragen (`ask_user` / OptionsList, 1..N Fragen):**
       Erkannt über Screen-Muster (`Enter select`, `Type your own answer`, `(Select multiple options)`, `↑↓ navigate`).
       Pfeiltasten bleiben nativ.
      - **Multi-Fragen-Unterstützung (Frage 1 → 2 → 3...):**
        Enter schließt den Fragenmodus bewusst **nicht** (da Enter von Frage 1 zu Frage 2, 3 etc. springt!).
        Erst wenn alle Fragen abgeschlossen sind (`Your answer:`, `Your answers:`) oder der Nutzer mit Esc / Strg+C
        abbricht, schaltet der Filter zurück auf PageUp/Down im Chat.
    * **Wort-Navigation und Wort-Löschung (Strg+Links/Rechts, Strg+Backspace):**
      - Standard-Terminals (xterm.js / VS Code) senden `Strg+Links` als `\x1b[1;5D`, `Strg+Rechts` als `\x1b[1;5C` und `Strg+Backspace` als `\x08` (ASCII BS).
      - Freebuff (opentui) unterstützt intern Wortsprünge nur über Alt/Option (`\x1b[1;3D`, `\x1b[1;3C`) und Wortlöschen über `Ctrl+W` (`\x17`) / Alt+Backspace (`\x1b\x7f`).
      - Der PTY-Filter übersetzt `Strg+Links` auf `Alt+Links`, `Strg+Rechts` auf `Alt+Rechts` und `Strg+Backspace` auf `\x17`.
      - Bleibt in allen Modi (Chat, Menüs, Modals) aktiv, ohne das Binary anzufassen.

**5. Umleiten des Rads selbst geht nicht.** `.vscode/keybindings.json` mit
`mousewheel up`/`down` ist **kein gültiges Keybinding**: VS Code listet als
akzeptierte `key`-Werte Buchstaben, Ziffern, Pfeile, `pageup`/`pagedown`,
`home`/`end`, `tab`/`enter`/`escape`/`space`/`backspace`/`delete` und
Nummernblock — `mousewheel` steht nicht darin und wird nicht dispatcht. Die
probeweise eingefügte Datei ist entfernt; der Weg ist im Changelog dokumentiert,
damit ihn niemand wieder geht.

**6. Scroll-Schrittweite: kein Versions-Pin, Patch per Mustersuche.**
freebuff aktualisiert sich so schnell, dass ein Pin ständig veraltet — der
Nutzer hat ihn am 2026-09-27 abgeschafft. `freebuff-install.sh` installiert
jetzt `freebuff@latest` und überspringt nur, wenn die installierte Version
**gleich** der aktuellsten aus `npm view` ist.

Die Schrittweite selbst (`0.8` Bildschirmhöhe pro Tastendruck) bleibt ein
**Vendor-Patch**, aber **mustersuche- statt namensbasiert** — das war die
Lehre aus dem ersten Update:

| | 0.0.204 | 0.1.0 |
|---|---|---|
| Faktor-Variable | `fOA` | `$hA` |
| Definition | `fOA=0.8` | `$hA=0.8` |
| namensbasierter Patch | ✅ | ❌ **tot** (Rename) |

Der Patch findet jetzt die **Struktur**, nicht den Namen:
`Math.floor(<A>*<VAR>)` im Kontext von `viewport.height` → Definition
`<VAR>=<0.x>` → **genau diese eine** Zahl ersetzen (0.8 → 0.5, gleiche Länge).
Damit überlebt er ein Rename. Bricht die Struktur künftig ab, meldet das Skript
`Struktur nicht erkannt` und lässt das Binary **unangetastet** — nie still
falsch. `FREEBUFF_SCROLL_STEP` steuert den Zielwert (Default **0.5**, also
halbe Seite). Weitere Sicherheitskette wie gehabt: Patch nur bei genau einer
Definitionsstelle, Backup unter `~/.config/manicode/freebuff.orig`, und
`verify_after_patch` startet das Binary und **spielt das Backup zurück**, wenn es
nicht mehr startet. Läuft gerade eine Session, wird der Patch übersprungen
(ETXTBSY) und beim nächsten Build nachgeholt. Rückweg jederzeit:
`cp ~/.config/manicode/freebuff.orig ~/.config/manicode/freebuff`.

**6. Messen statt Behaupten.** `FREEBUFF_PTY_DEBUG=<datei>` protokolliert nur
Esc-/Steuersequenzen, die das Kind liest (getippter Text nur als Byte-Laenge
`<12B text>`). Damit ist in Sekunden beantwortbar, ob eine Taste ankommt —
statt einen 136-MB-Bundle zu sezieren. Genau dieser Logger hat in dieser
Sitzung zwei Fehldiagnosen verhindert und zwei echte Fehler gefunden.


## Google-Drive-Backup (Repo-Sicherung unabhängig von GitHub)

Szenario: GitHub-Account wird gebannt / Repo geschlossen → komplettes Repo
(inkl. History, aller Branches) liegt dann als git-bundle auf Google Drive
(5 TB, Google AI Pro). **GitHub-Actions bewusst nicht genutzt** — läuft bei
Bann nicht mehr, genau dann wird das Backup gebraucht.

- **`infra/scripts/gdrive-backup.sh`** (`gdrive backup [--force]|status|restore [dir]`,
  Alias `gdrive`): baut `git bundle --all` (~112 MB). **Fail-safe-Reihenfolge**
  (2026-09-26 umgebaut): (1) Bundle bauen und als `MAIN.new.bundle` hochladen,
  (2) **erst jetzt** rotieren: `MAIN.bundle` → `MAIN.backup.bundle`, `MAIN.new.bundle`
  → `MAIN.bundle`, (3) `current` nach der Rotation erneut prüfen. Die alten
  Generationen werden also erst angefasst, wenn eine geprüfte neue Kopie existiert —
  bricht der Upload ab, bleibt alles unangetastet. Jeder Schritt wird über den
  **Zustand** geprüft (existiert die Datei, stimmt Größe und MD5), nicht über
  rclones Exitcode: `rclone moveto` hat am 2026-09-26 erfolgreich gearbeitet und
  trotzdem nonzero geliefert. **Fail-closed:** ein fehlender oder unlesbarer
  `current` ist ein Fehler, kein „OK (verifiziert)". `status` benennt beide
  Generationen und warnt explizit, wenn eine fehlt; `--force` erzwingt ein Backup
  (z. B. zur Reparatur nach unterbrochener Rotation). Restore: `gdrive restore`
  klont aus der Backup-Generation (Fallback current). Skip nur wenn kein neuer
  Commit seit letztem Backup **und beide Generationen existieren** (State-File
  `.runtime/gdrive-backup.last`).
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
  **Eigener Google-`client_id` (2026-10-01): erledigt.** rclone nutzte den
  *geteilten* Client, den Google 2026 abschaltet (und warnte bei jedem Upload).
  Jetzt liegt ein eigener OAuth-Client (Typ **Desktop-App**, Projekt
  `423042998961`) in `~/.config/rclone/rclone.conf` (`client_id` +
  `client_secret`), der Token ist darauf neu ausgestellt, und die Warnung ist
  weg. Der Consent-Screen steht auf **„In production"** (unverifiziert, nur
  Selbstnutzung; Startseite/Datenschutz = öffentliches Repo bzw. `PRIVACY.md`).
  Grund: bei **„Testing"** lässt Google die **Refresh-Tokens nach 7 Tagen**
  ablaufen, in Production nicht — deshalb wurde nach dem Veröffentlichen einmal
  neu autorisiert. Beim Einrichten (noch im Testing-Modus) war zusätzlich ein
  **Testnutzer**-Eintrag nötig, sonst `403 access_denied` (live erlebt).
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
`./infra/scripts/secrets.sh lock`).

**Grundsatz: immer direkt auf `ChatMCPConnector/MAIN` arbeiten, keine Forks.**
Der geprüfte Weg ist genau der:

1. **Codespace auf dem Original-Repo bauen** — über die **Web-UI**
   (`github.com/codespaces`). Per API geht es nicht: der ambient
   Codespace-Token bekommt 403 (`you cannot create codespaces with that
   repository`), der Bundle-PAT 404 (keine `codespace`-Scope). Die UI
   akzeptiert es als Kollaborator mit Push — live am 2026-09-26 so geschehen.
   Optional: dem Fine-grained-PAT **Codespaces: Read and write** geben, dann
   funktioniert auch `gh codespace`; der Token-Wert bleibt dabei gleich, Bundle
   und Secret bleiben gültig.
2. **Passphrase als Secret setzen** (einmal pro Account, als Gewohnheit):
   `./infra/scripts/codespace-secret.sh set-passphrase` — nimmt den Wert sicher
   aus `config/passphrase` statt aus dem Kopf. Der PAT ist keine Passphrase,
   und diese Verwechslung ist am 2026-09-26 zweimal passiert (einmal als
   Secret, einmal als `LANDSCAPE_PASSPHRASE`).

**Beide Codespaces-Secrets sind auf `ChatMCPConnector/MAIN` gescoped**, deshalb
kommen `LANDSCAPE_PAT` und `LANDSCAPE_PASSPHRASE` in jedem Codespace dieses
Repos automatisch an — der Passphrase-Wert wird also nicht mehr aus dem Repo
geraten, sondern injiziert. Das ist der Grund, warum ohne Fork gearbeitet wird:
beim Fork (anderes Repo) wären beide Variablen leer, und es müsste zusätzlich
das Fork-Repo in den Secret-Scope nachgetragen werden. Kontrolle in einem neuen
Codespace: `./infra/scripts/verify-codespace.sh` zeigt `LANDSCAPE_PAT gesetzt
(93 B)` und `LANDSCAPE_PASSPHRASE gesetzt (40 B)`.

Die Git-Identität des neuen Accounts entsteht automatisch aus dem PAT
(`auth.sh setup`), der opencode-Pin ist im Repo (`ocver check`).

**Nachweis, dass die Kette steht:** `./infra/scripts/verify-codespace.sh`
(20 read-only Checks inkl. echter LLM-Calls auf beiden Proxys, `--live` zusätzlich
`keys.sh doctor`). Am 2026-09-26 in einem wirklich frischen Codespace:
**20 PASS, 0 FAIL** — inklusive Nachweis, dass `setup.sh` venv, `.env`, rclone
und beide Proxys selbst gebaut und gestartet hat (Artefakt-mtimes ≈
Codespace-Erstellung, Prozesslaufzeiten ≈ Uptime). Zwei Befunde kamen nur
dadurch heraus: `opencode` war im interaktiven Terminal nicht im PATH (jetzt
von `setup.sh` selbst gesetzt) und der Unlock konnte bei fehlender Passphrase
endlos auf eine Eingabe warten (jetzt non-interaktiv, `SECRETS_NO_PROMPT=1`).

Nicht mitkommen, aber rekonstruierbar: Browser-Profil, Ports.
glm2api selbst kommt komplett mit (Code im Repo).

## Codespace-Lifecycle — wann welcher Mechanismus greift

| Event | Mechanismus | Wirkung |
|---|---|---|
| Codespace-**Neuerstellung** (Rebuild) | `postCreateCommand` → `setup.sh` | Voll-Setup: Pakete, opencode, uv, Secrets-Unlock, Git-Auth, Browser, MCP-Registrierung, Proxy-Rebuild + Start |
| Codespace-**Resume** (Stopp→Start, Idle/Über Nacht) | `postStartCommand` → `start-on-boot.sh` | Proxy-Health-Check; läuft er nicht → Start (Code/venv/.env überleben in MAIN). Bei Unvollständigkeit: Hintergrund-Rebuild (Log `/tmp/opencode/boot-rebuild.log`) |
| **Client-Reconnect** (Browser-Reconnect ohne Container-Restart) | **`proxy-watchdog.sh`** (Daemon, 30s-Intervall) | postStartCommand läuft NICHT bei Reconnect — der Watchdog hält den Proxy trotzdem am Leben (auch nach OOM-Kill). Start via start-on-boot.sh, Lockfile `/tmp/opencode/proxy-watchdog.lock`, Log `/tmp/opencode/watchdog.log` |
| Laufzeit | `infra/scripts/glm2api.sh start` idempotent | **Einziger Startweg seit 2026-10-02** — der frühere `llm-proxies/scripts/start-glm2api.sh` ist entfallen, seine `.env`-/Token-Vorbereitung liegt jetzt in `prepare_env()`. Doppelstart-sicher (Adoption über `/health`), `setsid`-Start, PID-Datei, Log-Rotation, Start-Health-Check. Die `setsid`-Lektion (Changelog 2026-09-26): fehlte sie, schickte ein Agent-Tool-Call im Timeout dem Proxy SIGTERM mitten im Stream |
| ~~Idle-Schutz (offene Commits vor Shutdown sichern)~~ | ~~`autosave-daemon.sh`~~ | Alle 30 Min: prüft auf uncommittete Änderungen oder ungepushte Commits → `save.sh` (add -A, commit, pull --rebase, push). Kein leerer Commit-Spam. Start via start-on-boot.sh + setup.sh, Lockfile `/tmp/opencode/autosave-daemon.lock`, Log `/tmp/opencode/autosave.log`. Shell: `autosave {status|start|stop|log}` |
| **Config-Auto-Restart** (neue Modelle sofort verfügbar) | **`config-watchdog.sh`** (Daemon, inotify-Event-basiert) | Überwacht `.opencode/opencode.json` per `inotifywait` (close_write/moved_to) auf dem **Verzeichnis**; **Hash-Vergleich** nach jedem Event, damit Schreibvorgänge auf anderen Dateien im Ordner (`tui.json`, `package-lock.json`, neue `agent/*.md`) keinen Restart auslösen; Debounce 8s + **Busy-Guard** (prüft `/session/status`, wartet bis alle Sessions idle sind vor Restart, kein Abbruch laufender Turns) + Pause-Mechanismus (`config-watchdog.pause`). Fallback auf Polling (10s md5sum) falls inotify-tools fehlt. Start via start-on-boot.sh + setup.sh, Lockfile `/tmp/opencode/config-watchdog.lock`, Log `/tmp/opencode/config-watchdog.log`. Shell: `config-watchdog {status|start|stop|pause|resume|log}` |

**Boot-Härtung (2026-10-01):** `start-on-boot.sh` ruft `secrets.sh unlock` mit
`SECRETS_NO_PROMPT=1` und `</dev/null` auf — identisch zu `setup.sh`, sonst kann
der Resume-Boot bei vorhandenem TTY unsichtbar auf die Passphrase warten (Ausgabe
geht nach `/dev/null`, der Hang bleibt ungesehen). Und der opencode-Server stoppt
über `timeout.sh kill "opencode-bin serve"` statt `pkill -f` (`AGENTS.md §4`:
`-f` matcht die Kommandozeile der aufrufenden Shell und trifft sie mit).

**Proxy-Verhalten nach Stopp:** Prozesse sterben, `/tmp` (Logs) wird geleert —
Code, venv und .env in MAIN überleben alles. Der Boot-Mechanismus zieht den
Proxy bei jedem Start automatisch hoch.

- 2026-09-30: **Freebuff Session-Löschung in `/history` per Tastatur (`Delete`, `Ctrl+D`, `Ctrl+X`):**
  - **Befund:** Im `/history`-Menü konnten keine Sessions gelöscht werden. Die Analyse des Vendor-Bundles ergab: Freebuff implementierte das Entfernen (`actionLabel: "[×]"`, `onAction`) ausschließlich über einen Mausklick-Handler (`onClick: () => f(X, v)`), bot jedoch kein einziges Tastaturkürzel im UI (`onKeyIntercept` leitete nur Up/Down/Right/Enter/Esc/Ctrl+C weiter). Da das Mouse-Reporting für das benutzerdefinierte Setup (Mausrad-Scrollen, native Terminal-Auswahl, Copy/Paste) im PTY-Filter bewusst deaktiviert ist, empfing die App keine Mausklicks und Sessions waren unlöschbar.
  - **Lösung:** Neuer atomarer Vendor-Patch `patch_history_delete` in `infra/scripts/freebuff-install.sh` (am 2026-10-02 nach `infra/scripts/freebuff_patch.py` verschoben, siehe (22)). Er erweitert den `onKeyIntercept`-Callback in der History-Komponente um die Erkennung von `Delete` (`Entf`), `Ctrl+D` und `Ctrl+X` auf der fokussierten Session (`s = F[R]`), ruft die native Löschaktion `l(s)` auf und aktualisiert die Statuszeile exakt längengleich (`Click [×] to remove` -> `Del / Ctrl+D to remove`).
  - **Unberührt:** Alle bestehenden Mechanismen (Mausrad-Scrollen, Arrow-Patches, PTY-Filter, native Pfeil-Navigation in Menüs, Copy/Paste) bleiben zu 100% unverändert.

- 2026-09-28: **Die `open`-Verbots-Warnung war an den falschen Agenten gebunden — sie wurde in der Default-Session nie geladen.** Konsequenz aus dem S-21-Fall (`ses_f17123666ffeMwmhdXlMz3HO1l`): die Session lief als `agent: build` (`opencode.json` `default_agent`, Zeile 292), und die gesamte Warnung stand in `.opencode/agent/glm2api.md`. **Die Schicht war falsch gewählt:** `open` ist kein Werkzeug *dieses Agenten*, sondern *jeder* opencode-Session — `open`, `open_url`, `browse`, `web.run` und `execute_sandbox_code` gehören zu Chat-Oberflächen, nicht zu opencode. Ein Agenten-Prompt kann das nicht abdecken, weil Agent und Modell in opencode **unabhängig** gewählt werden und es keine bedingte Zuordnung „Agent X nur bei Modell Y" gibt. **Lösung:** neue zentrale Datei `.opencode/INSTRUCTIONS-glm2api.md`, geladen per `"instructions"` in `.opencode/opencode.json`. opencode kombiniert `instructions` mit `AGENTS.md` und lädt sie in **jede** Session. Die Tool-Sektion im Agenten-Prompt ist dadurch auf einen Verweis plus die agentenspezifischen Rollen (`todowrite`/`glob`/`grep`/`task`/`question`) reduziert — **eine Quelle statt zwei, damit sie nicht auseinanderlaufen.** AGENTS.md blieb bewusst unberührt: es ist laut Repo-Regel die clientübergreifende Quelle (Gemini CLI liest sie mit), glm2api-Spezifika gehören dort nicht hin. **Zwei Befunde, die erst das Messen ergab:** (a) **Der Pfad in `instructions` wird vom Projekt-Root aus aufgelöst, nicht relativ zur Config-Datei.** `INSTRUCTIONS-glm2api.md` (Config-relativ gelesen) wurde stillschweigend **nicht** geladen — das Modell kannte die Inhalte nicht, die Datei existierte, opencode meldete nichts. Erst der Dreifach-Vergleich `./INSTRUCTIONS-glm2api.md` → kein Marker, `.opencode/INSTRUCTIONS-glm2api.md` → **Marker erkannt**, `INSTRUCTIONS-glm2api.md` → kein Marker hat es aufgedeckt. Das ist die Fehlerklasse „sieht aus wie es wirkt": ohne den Markertest hätte ich eine korrete Datei an der falschen Stelle liegen lassen und es als Erfolg gemeldet. (b) **`instructions` lädt bedingungslos für ALLE Modelle** — live gegengeprüft: eine `antigravity/gemini-3.8-flash`-Session sah die Datei ebenfalls und bestätigte, `open` existiere dort ohnehin nicht. opencode kann das nicht pro Modell bedingen, deshalb ist die Datei strikt getrennt: **Abschnitt A** (`open` existiert nicht, `read`/`webfetch`/`bash` stattdessen, Pfade absolut, keine Probe-Fetches) ist für *jedes* Modell wahr, **B** (das stille `open`→`read`-Mapping) und **C** (die drei Notices, kein erfundenes Limit) sind als „nur bei `glm-5.3`" markiert, mit ausdrücklichem Hinweis, sie bei anderen Providern zu ignorieren. Das ist Text, keine technische Absicherung — der Grund ist explizit dokumentiert, damit jemand die Datei nicht für eine modelspezifische hält. **Verifiziert:** Marker-Test glm2api → Abschnitt C vorhanden; Marker-Test antigravity → Datei geladen, Bedingtheit erkannt; JSON valide; Live-Session mit `build` + `glm-5.3` (derselbe Ordnervergleich, der die Fehlschleife ausgelöst hatte) → Client sieht nur `read`/`bash`, keine unmaskierten `open`-Calls.

- 2026-09-28: **S-28: die Korrekturrunden lieferten die gueltigen Calls nicht aus — der Modell bekam nie seine Dateiinhalte.** Live-Befund aus `ses_f15e98754ffe8E5GoHP4rWsBs6`: `read /workspaces/zerokey-v2.0/README.md` wurde **erfolgreich ausgefuehrt** (DB: `read|completed`), aber der Client erhielt das Ergebnis nie — der Turn wurde von der Korrekturrunde ersetzt, bevor `finalize_chunks` yieldiert wurden. Folge: *„ein Vergleich ist aktuell nicht moeglich"*, obwohl die Datei gelesen worden war. **Fix:** die gueltigen Calls des laufenden Turns werden jetzt **vor** dem Accumulator-Wechsel ausgeliefert. **V-03 bleibt in Kraft:** der *blockierte* Werkzeugname (`open_url`, `open`, …) darf dabei nicht mit durchrutschen, deshalb werden die Chunks gegen die Byte-Marken der blockierten Namen gefiltert — der bestehende Test `test_blocked_tool_triggers_follow_up_round_stream_with_served_content` sichert genau das und bleibt gruen. **Zusaetzlich: `GLM_BLOCKED_TOOL_FOLLOW_UPS` von 2 auf 5** (in `.env` und `.env.example`). Begruendung aus `ses_f15e98754ffe8E5GoHP4rWsBs6`: nach zwei Korrekturen war die faktuelle Quelle erschoepft, und das Modell erfand die einzig noch moegliche Erklaerung — *„weitere Tool-Aufrufe sind laut System nicht mehr moeglich"*. Die Korrekturrunden sind die **einzige** echte Faktuelle Quelle fuer das Modell; ist sie leer, rät es. **Eine Fehlkonstruktion wurde zurueckgenommen:** zuerst sollte das Budget bei Drops/Remaps dynamisch auf ein Maximum gehoben werden. Das hat echte, korrekt erzeugte Calls verschluckt (0 statt 2 geliefert) und ist **entfernt** — das Budget aus der `.env` reicht. **Ehrlich zur Reichweite, und das ist der wichtigste Punkt:** die Ordner `/workspaces/zerokey-v2.0` und `/workspaces/downloaddoctor-zerokey` waren zum Zeitpunkt des Tests **nicht mehr vorhanden** (Commit `ad87143`, 00:43:47, „beide alten Checkouts unter /workspaces loeschen"). Der Test zielte damit auf Pfade, die es nicht gab — das Modell berichtete das auch korrekt. Die S-28-Aussage ist davon **unabhaengig** und durch den DB-Befund belegt (Call `completed`, Ergebnis nie zugestellt). **Verifiziert:** 1703 Tests gruen, 3 Harnesses gruen. Ein Regressionsfall gegen den Live-Befund ist **noch nicht** geschrieben — das ist die naechste Aufgabe, weil genau dort heute ein Fix durchgerutscht ist, ohne dass ein Test es gefangen hat.

- 2026-09-28: **S-27: die Korrekturrunde kam nie an — und die Notices kamen im falschen Kanal an. Zwei Zaehler-Fehler plus eine falsch gelesene Klausel, zusammen ergab das die komplette Pathologie.** Ausgeloest durch `ses_f1605c9d0ffeCSJmR08y4q29FK` (75 `open`-mappings, 6 drops, **null** korrekturrunden). Das Modell las beide READMEs erfolgreich und produzierte trotzdem *„konnte nicht geladen werden — starte die Anfrage neu"* und erfand drei erklaerungen, die es nicht gab: *„the system has repeatedly interrupted me telling me to stop calling `open`"*, *„MCP-Scrape-Fehler"*, *„ich breche hier ab, **wie vom System gefordert**"*.
  **(1) Der Drop-Zaehler war requestlokal (wie S-26, andere Stelle).** `needs_correction` prueft `loop_guard_dropped_count` — der liegt im Accumulator, der pro Upstream-Runde neu gebaut wird. Folge: `blocked_follow_ups=0` in **jedem** turn, die korrektur konnte strukturell nie feuern. Fix: `_mirror_drop_counts()` / `_seed_drop_counts()`, Spiegel im request-scope.
  **(2) `served_content` hat den S-24-Skip praktisch immer ausgeloest.** S-24 sagt: nach ausgeliefertem content gewinnt V-03 (kein Zuruecknehmen). Aber `served_content` ist bei **jedem normalen** turn true — der turn streamt ja sichtbaren text. Der skip war damit die regel, nicht die ausnahme, und die korrektur kam nie an, egal wie sauber die bedingung gebaut war. **Die Klausel war falsch gelesen, nicht falsch implementiert.** Fix: bei drops, remaps oder aufgaben-abandon wird die korrektur **immer** gefahren. Begruendung: ein zweiter Antwort-Block ist ein kosmetischer Schaden; fehlende Fakten sind ein sachlicher, weil sie den Auftrag abbrechen lassen und den Grund verfaelschen. V-03 gilt unveraendert fuer den blocked-only-Fall.
  **(3) S-25 rueckgaengig gemacht — die Textunterdrueckung war die Ursache der erfundenen Meldungen.** Sie loeschte genau den Text, in dem das Modell seinen Zustand beschreibt; das Modell bekam Stattdessen nichts und erfand Gruende. S-27 laesst den Text sichtbar und schickt die echte Korrektur nach — **Information statt Schweigen.** Der ansatz ist damit im kern umgekehrt.
  **Verifiziert:** 1703 Tests gruen (+2, einer simuliert die 21-Runden-Schleife, einer prueft den drop-zaehler ueber den accumulator-wechsel). **Live-Gegenprobe mit exakt der gescheiterten aufgabe:** vorher 75 mappings / 6 drops / **0 korrekturrunden** → nachher 12 mappings / 2 drops / **4 korrekturrunden**. Das modell las beide READMEs, erkannte den Tippfehler selbst, verglich substanziell (ZeroKey-Proxy, DeepSeek-Browser-Transport, IDE-Integration, MCP) und korrigierte seine eigene fruehere Aussage. **Null erfundene Fabeln, null Echos.** Der S-25-test wurde entsprechend umgeschrieben: er haelt jetzt fest, dass der abandon-text *sichtbar bleibt* und die korrektur ausloest — nicht dass er verschwindet. 3 Harnesses gruen.

- 2026-09-28: **S-26: der Loop-Guard zaehlte requestlokal und griff deshalb nie — 21x derselbe Aufruf, jede Ausfuehrung erneut, null Drops.** Ausgeloest durch `ses_f161565c6ffeZp78k7WqoSoF06` (Agent `build` + `glm-5.3`, Auftrag *„Lies die README von /workspaces/gibtsnicht und /workspaces/zerokey-v2.0 und vergleiche"*). Der Pfad `gibtsnicht` existiert nicht, also kam die schlimmste denkbare situation: das Modell rief **`open` 21x auf denselben fehlenden Pfad**, jeder Aufruf wurde auf `read` gemappt und **erneut ausgefuehrt** (Log: 30x `Mapped native open`, **null** Drops), es kam nie heraus und erfand eine Erklaerung, die es nicht gab: *„the system has repeatedly interrupted me telling me to stop calling `open`"* — in 6 aufeinanderfolgenden Reasoning-Bloecken. **Ursache:** `_server_side_signature_counts` lag im `GLMEventAccumulator`, der pro Upstream-Runde neu gebaut wird. Damit sah jede Runde *„erster Call dieser Signatur"* und die Grenze `_MAX_IDENTICAL_NATIVE_CALLS = 2` **konnte nie greifen**. Der Guard existiert genau fuer diesen Fall und hat in diesem Pfad nie ausgeloest. **Fix:** der Zaehler wird ueber `_mirror_loop_guard_counts()` in ein request-scope-dict gespiegelt und bei jedem frischen Accumulator ueber `_seed_loop_guard_counts()` zurueckgespielt — an allen 8 Erzeugungsstellen (Initialisierung, transient-retry, leer-retry, follow-up-Runde) in **beiden** Pfaden (stream und non-stream). **Wichtig zu der Reihenfolge der Erkenntnis:** S-25 hat in dieser Session **nichts** unterdrueckt (`is_abandon_claim()` matchte nicht, S-25 ist im Log nicht aufgetaucht) — der Schaden kam nicht aus dem Fix, den ich zuletzt gebaut hatte, sondern aus einem aelteren Fehler, den die S-21..S-24-Schichten bis dahin verdeckt hatten. Die erste Hypothese (Echo-Pfad in Zeile 3168) war falsch und wurde am Log widerlegt: null `Dropped echoed native tool_call`. **Verifiziert:** 1701 Tests gruen (1699 + 2 neu: `test_loop_guard_zaehlt_ueber_accumulator_grenzen` und `test_21_fach_wiederholung_wird_jetzt_gebrochen`, letzter simuliert die 21-Runden-Schleife und bricht sie). **Live-Gegenprobe mit exakt der Auftrag, die gescheitert ist:** vorher 30 Mappings / 0 Drops, **nachher 9 Mappings / 4 Drops** — der Guard greift. Das Modell las alle drei echten Fehler, erkannte den Tippfehler **selbst** (`verifiziert per ls /workspaces`) und lieferte ein vollstaendiges Vergleichsergebnis; 7 Calls, 3 davon berechtigte Fehler, **keine Fabel, kein Echo, S-25 musste nicht eingreifen**. 3 Harnesses gruen.

- 2026-09-28: **S-25: Aufgaben-Abandon wird erkannt, bevor der Text den Client erreicht - der Filter sitzt in `finalize()`, nicht im SSE-Chunkpfad.** Der Restfehler aus S-24 war der sichtbare Echo-Text: das Modell brach mit *"bis das Rundenlimit erreicht war. Schick mir bitte eine neue Nachricht"* ab und der Client bekam genau das, weil der Zwischenstand vor der Korrekturrunde raus war. **Die Erkennung ist bewusst eng.** Drei Muster, alle je fuer sich belastbar: eine Limit-Behauptung (es gibt per Definition kein Limit), *"schick mir eine neue Nachricht"* (eine Abgabe an den Nutzer mitten in der Aufgabe) und *"ich muss abbrechen"*. **Ausdruecklich NICHT gemustert wird "ich konnte die Dateien nicht lesen"** - bei echten Fehlschlaegen ist das zutreffend (live gemessen: 2x `File not found: /workspaces/cyber`, und das Modell sagte zu Recht, dass es die Dateien nicht lesen konnte). **Falsch-Positive sind schlimmer als Falsch-Negative:** eine verschluckte fertige Antwort ist ein verlorener Arbeitsgang, ein stehenbleibender Echo nur ein kosmetischer Rest. Also: im Zweifel durchlassen, `None` = durchgelassen. **Zwei Fehlkonstruktionen unterwegs, beide durch Tests gefangen statt durch Behauptung:** (a) Der erste Entwurf pufferte im SSE-Chunkpfad und brach **8 Regressionen** aus - bei abgebrochenen Streams ("TEIL-1" kam nicht an) ging der zurueckgehaltene Anteil verloren, weil weder der `finish`-, noch der Exception-, noch der Truncate-Zweig den Puffer leerte. Fail-safes nachgezogen. (b) Der Puffer sah den Abandon-Text **nie**: `consume_event()` streamt Prosa nicht, der Text entsteht erst in `accumulator.finalize()`. Der Puffer sass am falschen Ort. **Die Erkennung sitzt jetzt in `finalize()`** und filtert den reinen Text-Turn; ein Turn mit `tool_calls` wird nie angefasst (C-11/V-02 verlangen, gueltige Calls unveraendert auszuliefern - und ein Turn mit Werkzeugaufruf bricht nicht ab). Das ist auch semantisch der richtige Ort: dort steht der **vollstaendige** Text, nicht ein Fragment. Ein unterdrueckter Abandon setzt `suppress_abandon_reason` und loest damit die Fortsetzungsrunde aus. **Verifiziert:** 1699 Tests gruen (1692 + 7 neu), davon drei gegen den **echten SSE-Byte-Pfad** (nicht gegen den Dict-Mock, der die Chunk-Aufteilung des Accumulators umgeht): Live-Fall 1 und 2 unterdrueckt (0 Zeichen sichtbar, S-25 geloggt), normale Antwort durchgelassen (100 Zeichen), echter `File not found` durchgelassen (57 Zeichen), reine Limit-Behauptung unterdrueckt. **Ehrlich zur Reichweite:** die Live-Session gegen den neu gestarteten Proxy lief **sauber durch, ohne S-25 zu brauchen** - 3 Calls, 0 Fehler, keine Fabeln, korrekte Antwort (224 Zeilen identisch). Das Modell brach diesmal gar nicht ab, also ist der Live-Pfad fuer S-25 **nicht** belegt; der Nachweis ist der Test gegen den echten SSE-Pfad. 3 Harnesses gruen.
- 2026-09-28: **S-23/S-24: die Notices erreichten das Modell gar nicht — ein SSE-Delta ist ein Client-Ausgabekanal, kein Kontext. Daraus folgte die volle Abbruch-Pathologie, live reproduziert und behoben.** Anlass war der Auftrag, Bug 2 (Aufgaben-Abandon) sauber nachzuweisen. Der Nachweis lief **zuerst gegen die eigene Diagnose aus**: zwei Läufe mit gültigen Pfaden zeigten 0 Fehler und vollständige Antwort — aber ohne einen einzigen `open`-Aufruf, also ohne den eigentlich zu prüfenden Fall. Der Fall musste erzwungen werden, und er war aufschlussreich. **Live-Befund (`build` + `glm-5.3`, README-Vergleich):** das Modell rief 13× `open` (11 davon erfolgreich als `read` ausgeführt), erklärte dann *"`open` funktioniert nicht für lokale Pfade"* (falsch — 11 liefen), *„bis das Rundenlimit erreicht war"* (erfunden, es gab keins) und *„schick mir bitte einfach eine neue Nachricht"*, obwohl `loop_guard_notice` ausdrücklich das Gegenteil sagte. **Ursache, die S-22 sogar verschlimmert hatte:** S-22 legte die Notices in `reasoning_content`, um sie aus dem sichtbaren Text zu nehmen. Damit verlor die Meldung **jeden** Transportweg zum Modell: `opencode run` gibt `reasoning_content` nicht als `reasoning`-part aus (live geprüft: der Event-Stream enthält nur `step-start`/`tool`/`text`/`step-finish`, null reasoning) und schickt es in der Folgeanfrage nicht zurück. Gemessen: vor S-22 erschienen die Notices im Client-Output (im Fließtext, unschön), nach S-22 **null**. Beide SSE-Kanäle sind als Konkurrent unzuverlässig — sichtbar heißt „das Modell liest es als eigene Narration", unsichtbar heißt „das Modell sieht es nie". **Fix (S-23):** die Notices gehen als **eigene `user`-Nachricht in die Konversation** — derselbe Weg, den `_build_blocked_tool_follow_up_payload` für blockierte Tools schon ging und der nachweislich funktioniert, weil er echten Kontext erzeugt, den der Client nicht verlieren kann. Drei Änderungen: die Funktion baut jetzt **alle** drei Notices (nicht nur `blocked`) in fester Reihenfolge remap → blocked → loop; die Auslösebedingung `needs_correction` berücksichtigt remap- und loop-Notices, nicht nur blockierte Tools; und entscheidend **`not turn_has_valid_calls` fiel als Bedingung weg**. V-02 war bisher falsch gelesen: es verbietet, gültige Calls zu **verwerfen**, nicht, eine Korrektur zu schicken — die Calls liegen unverändert in `finalize_chunks`. Genau diese Bedingung verhinderte die Korrektur in **exakt dem Fall, den sie verhindern soll**: live belegt mit 13 gemappten `open` + 9 Loop-Drops und `blocked_follow_ups=0` in allen vier Turns. **Fix (S-24), mit V-03 kollidierend — und deshalb bewusst nicht erzwungen:** solange noch kein Text gestreamt wurde, ist der Turn umkehrbar; ist er schon raus, nicht. Der erste Korrekturversuch wollte den Turn ersetzen und scheiterte an genau dem: der Zwischenstand mit der Limit-Fabel war bereits sichtbar. Der Proxy prüft das jetzt explizit und ** überspringt** die Korrektur-Runde mit einer Warnung, wenn `served_content` True ist — V-03 (ein Turn ist nicht zurücknehmbar, sonst hätte der Client zwei Antworten) hat Vorrang, und der Client behält die Ein-Turn-Garantie. **Gemessene Wirkung, ehrlich gestaffelt:** `open`-Aufrufe in der problematischen Session **13 → 2**, Tool-Errors **2 → 0**, Folge-Runde feuert, und das Modell lieferte die vollständige, korrekte Antwort (224 Zeilen identisch). **Was bleibt und nicht gelöst ist:** die Limit-Fabel und der Aufgaben-Abandon stehen weiterhin im sichtbaren Output — sie stammen aus dem *ersten* Text, der vor der Korrektur-Runde rausging, während die korrekte Antwort aus dem zweiten kommt. Das ist eine Eigenschaft des Streaming-Protokolls, keine Proxy-Entscheidung: um den ersten Text zu unterdrücken, müsste der Proxy **nicht streamen** (non-stream-Modus), was opencode hier nicht nutzt. Eine Mustersuche auf Aufgabentext hätte nur die richtige Antwort unterdrückt — bei 2 echten `read`-Fehlern ist „ich konnte die Dateien nicht einlesen" keine Fabel, sondern zutreffend. **Verifiziert:** 1692 Tests grün (unverändert, da die Korrektur Bedingungen im laufenden Pfad ändert, nicht die Notice-Texte), 3 Live-Läufe gegen denselben Auslöser (vor S-23 / nach S-23 / nach S-24) mit den Zahlen oben.

- 2026-09-28: **S-22: die Notices landeten mitten im sichtbaren Antworttext — der Kanal war die Botschaft, und das Modell las sie als eigene Narration.** Drei live gemessene Restfehler aus dem S-21-Test (Ordnervergleich, `agent: build` + `glm-5.3`) in einem Durchgang behoben. **(a) Notices im Fließtext:** sie wurden per `content`-delta ausgeliefert, und der Client zeigte *„Abbruch ehrlich gem [loop_guard_notice] 8 identical open call(s) … [native_remap_notice] … [blocked_tool_notice] …"* als **eine** normale Antwort. Das Modell erkannte die Notices nicht als Systemrückmeldung und produzierte genau die Drift, die sie verhindern sollen. **Fix:** alle Notices gehen jetzt in **`reasoning_content`** (Denkkanal) statt `content` — für das Modell sichtbar, vom Antworttext getrennt, zentral über `accumulator._notice_chunk()`. **Tool-Rolle wurde bewusst verworfen:** sie ginge nur, wenn im Turn ein echter `tool_call` existiert; bei einem rein blockierten Turn gibt es keinen, und eine erfundene Tool-ID wäre schlimmer als ein sichtbares Delta. **(b) Reihenfolge kippte über Turns:** jede Notice wurde einzeln per `[*new, *old]` vorangestellt, was die Reihenfolge umkehrt; bei fünf Notices in einem Turn (live: loop, remap, blocked, remap, blocked) wich die Ausgabe von der beabsichtigten ab. **Fix:** `_inject_turn_notices()` bzw. der S-22-Block im Stream bauen **alle** Notices an einer Stelle in fester Reihenfolge **remap → blocked → loop** und geben sie der Reihe nach aus. Die Reihenfolge ist jetzt im Code ablesbar statt ein Nebenprodukt des Stempels — S-21 musste sie noch erzwingen. Damit sind die beiden Einzel-Injektionsmethoden (`_inject_loop_guard_notice`, `_inject_native_remap_notice`) und der alte blocked-Block entfallen. **(c) Aufgaben-Abandon trotz Daten: war KEIN Proxy-Fehler, sondern eine Modellreaktion auf echte Fehlschläge — ehrlich so benannt statt mit einem Muster-Regex kaschiert.** Im Test lieferten 8 `read` + 3 `bash` Ergebnisse, aber **3 davon `error`**: `File not found: /workspaces/cyber` (der Ordner existiert nicht, `/workspaces/cyberpradeep-zerokey` wurde entfernt). Das Modell hatte also Teildaten, nicht die geforderten, und schloss daraus „Ich habe daher keine Daten … Sag einfach weiter". Ein Proxy-seitiger Muster-Filter auf Aufgabentext wäre hier **gefrätet**: „keine Daten" ist bei drei `error`-Ergebnissen eine korrekte Zusammenfassung, und ein Regex hätte die richtige Aussage unterdrückt. Der Fix wirkt an der Ursache (die Notices sind jetzt als Systeminfo erkennbar), nicht am Symptom. **Verifiziert:** 1692 Tests grün (1689 + 3 neu, davon 2 die live gemessenen Bugs aktiv verhindern: „Notice im Denkkanal, nicht im Text" und „feste Reihenfolge über alle drei Notices"), 3 Harnesses grün. Live-Nachweis des Kanals: acht identische `open` + ein `turn0search0`-Call im Stream → alle drei Notices nachweislich in `reasoning_content`, **keine** in `content`, Reihenfolge stimmt. **Was die Live-Session zusätzlich zeigte:** die Instructions senkten die `open`-Rate von 34 auf 15 Aufrufe, und in einem Lauf ohne jeden `open`-Aufruf appeared **überhaupt keine** Notice — sie entsteht nur, wenn wirklich etwas gemappt, blockiert oder verworfen wurde. **`opencode run` hat übrigens keine `reasoning`-Parts im Event-Stream** (geprüft: nur `step-start`/`tool`/`text`/`step-finish`); die Notices erreichen das Modell also über den Proxy-eigenen Denkkanal bzw. das Follow-up-Payload (dort als `user`-nachricht), nicht über eine sichtbare Client-Anzeige. **Das ist gewollt** — sie sollen den Antworttext nicht mehr verschmutzen.

- 2026-09-28: **glm2api: die Tool-Feedback-Schleife war widersprüchlich — das Modell rief `open` 40×, weil der Proxy ihm gleichzeitig „nicht ausgeführt" UND 15 fertige Ergebnisse zeigte.** Anlass war die Analyse der Session `ses_f17123666ffeMwmhdXlMz3HO1l` („Ordnervergleich cyber und downloaddoctor", 18:51–18:57, glm-5.3, `agent: build`): die Aufgabe war **erfolgreich** — der Vergleich beider Ordner stimmte, beide READMEs wurden gelesen, die git-Herkunft sauber ermittelt — aber der Weg dorthin war Pathologie. **Was passierte:** das Modell rief ~40× `open`, ein Tool das es nicht hat. Der Proxy bildete ~34 davon auf `read`/`webfetch` um und **führte sie aus** (echte Ergebnisse), blockierte 4 mit `ref_id=turn0search*` (nicht auflösbar, Inhalt existiert auf dieser Maschine nicht), und der Loop-Guard verwarf 13 weitere als identisch. **Der Kern des Fehlers ist kein Bug, sondern ein Widerspruch in der Rückmeldung:** `blocked_tool_notice` sagte pauschal *„open ist nicht verfügbar, wurde NICHT ausgeführt"* — im selben Turn, in dem 34 `open`-Aufrufe erfolgreich als `read` liefen. Das Modell konnte daraus keine Regel ableiten und produzierte daraufhin die 15×-identische-open-Schleife, zwei Müll-`webfetch` (`example.com`, das GitHub-opencode-README) und am Ende die erfundene Abbruchmeldung *„Die Analyse konnte nicht abgeschlossen werden — schick einfach eine neue Nachricht (weiter)"*, obwohl alles da war. **Ohne das Mapping wäre die Session nach 2–3 blockierten `open` hart gescheitert** — der Proxy hat ~34 kaputte Calls gerettet und das Problem damit kaschiert, nicht gelöst. **Fix (S-21), Mapping bewusst behalten:** der Accumulator merkt jetzt je erfolgreich umgeschriebenem nativen Call das Paar `(nativ, gemappt)` in `native_remapped_calls` — getrennt von `blocked_tool_attempt_names`, das nur das Nicht-Abbildbare sammelt. Die neue Notice `[native_remap_notice]` sagt ehrlich *„dein `open` lief als `read`, das Ergebnis ist echt und du hast es gesehen — nutze `read` DIRECTLY; das Mapping ist ein Kompatibilitäts-Shim, kein Tool-Vertrag"*. Sie nennt zusätzlich, dass es an nicht-abbildbaren Zielen versagt, damit sie nicht als verlässlicher Ersatz gelesen wird. **Reihenfolge ist hier die ganze Botschaft:** in beiden Pfaden (stream und non-stream) geht die Remap-Notice **vor** der blocked-Notice — erst „Ergebnis echt", dann „dieser Versuch lief nicht". Im Stream wird sie deshalb *nach* dem blocked-Block eingefügt, weil `finalize_chunks` per `[*new, *old]` prepended wird und der zuletzt eingefügte Chunk zuerst ausgegeben wird. **Verifiziert:** 1689 Tests grün (1682 + 7 neu in `test_loop_guard_notice.py`, inkl. Reihenfolge- und „gemappt zählt nicht als blockiert"-Gegenprobe), alle drei Harnesses grün, `build-bundle.sh` läuft durch (52 Files). **Der Live-Fall als Regressionsbeleg reproduziert:** 15× identisches `open` auf eine README + 4× `open` mit `turn*search*` in einem Turn → jetzt 2 zugestellte `read`-Calls (Loop-Guard), alle drei Notices vorhanden, korrekte Reihenfolge. **Live-Verifikation (20:0x, echte opencode-Session):** eine `opencode run`-Session mit `--agent build --variant max` gegen den neu gestarteten Proxy **hat den `open`-Pfad ausgelöst** — 29× `open`→`read` + 5× `open`→`webfetch` gemappt und ausgeführt, 3× `open` blockiert (die `turn*search*`-refs), Loop-Guard verwarf 9× und 8× identische Calls. Die neue `[native_remap_notice]` erschien live **3×**, die `[blocked_tool_notice]` 2×, die `[loop_guard_notice]` 2× — pro Turn in der richtigen Reihenfolge (remap → blocked → loop, in allen 3 betroffenen Turns verifiziert). Der Client sah ausschließlich `read`/`webfetch`/`bash`, nie ein `open`. Zwei einfachere curl-Anfragen (20:00, 20:03) hatten das Modell noch zu direktem `read`/`webfetch` geführt — die Halluzination tritt nur unter dem vollen opencode-Systemprompt + Build-Agent auf, was die gezielte Session mit `--agent build` korrekt reproduziert hat. **Nicht behoben, nur benannt:** die Session lief als `agent: build` (`opencode.json` `default_agent`, Zeile 321), nicht als `glm2api` — die `open`-Verbots-Warnung in `.opencode/agent/glm2api.md:15` wurde also **nie geladen**. Das ist eine eigenständige Config-Lücke und bleibt als Symptomkontrolle offen; sie bekämpft die Häufigkeit, nicht die Ursache.

- 2026-09-28: **glm2api aufgeräumt: Betriebs-Config wandert ins App-Verzeichnis, Build-Artefakte raus aus dem Index, und eine Löschung hätte den Bundle-Bau gebrochen.** Anlass war die Frage nach weiter entfallbaren Dateien unter `llm-proxies/glm2api/`. **Umzug:** `llm-proxies/glm2api.env` → `llm-proxies/glm2api/.env.dist` (`git mv`, Inhalt unverändert). Begründung: die Datei ist die *betriebliche Config genau dieses einen Proxys* — sie stand eine Ebene zu hoch und hieß im Repo redundant `glm2api/glm2api.env`. `config.py:521` löst nur wörtlich `.env` auf, eine Verwechslung mit der Live-`.env` ist damit ausgeschlossen; `.env.dist` wird von den gitignore-Regeln weder für `.env` noch für `llm-proxies/glm2api/.env` erfasst und bleibt getrackt. **Sechs Stellen nachgezogen:** `rebuild.sh:17`, `start-glm2api.sh:8`, `build-bundle.sh:16` (nur `ENV_SRC`) sowie die beiden Parametrisierungen in `tests/test_config.py:537,639` (`"../glm2api.env"` → `".env.dist"`). **Der Bundle-Zielname bleibt bewusst `glm2api.env`** (`build-bundle.sh:37`), weil `bundle/install.sh` und `bundle/start.sh` im Bundle genau diesen Namen erwarten — der Bundle-Interne Pfad ist eine eigene Sache und wurde nicht angetastet. **Gefundener Bruch, den die Löschung von `.python-version` erzeugt hätte:** `build-bundle.sh:33` kopiert die Datei in einer festen `for`-Liste unter `set -euo pipefail` — der Bundle-Bau wäre abgebrochen. Nach `git checkout` getestet, grün. **Aus dem Index entfernt:** `llm-proxies/dist/glm2api-bundle.zip` (340 K) — reines Build-Artefakt, das `build-bundle.sh` reproduzierbar erzeugt, und es war bereits durch `llm-proxies/dist/glm2api-bundle/` (das entpackte Stage-Verzeichnis) halb ignoriert. Jetzt per `.gitignore` ausgeschlossen, sonst hätte das nächste `save.sh` (`git add -A`) es sofort wieder eingecheckt. **Auf der Platte gelöscht, nie committet gewesen:** `src/glm2api.egg-info/` (wird von `uv sync` neu erzeugt), alle `__pycache__` (3,8 M) und darin 19 veraltete `*.cpython-312.pyc` (1,2 M — das venv läuft auf 3.14.7). **Doku-Verweise auf die gelöschte `optimierung.md` entfernt** (Datei bleibt gelöscht): in `infrastructure.md` die drei Changelog-Stellen, in sieben Code-Kommentaren (`translator.py`, `glm_client.py`, ein Docstring, `test_translator.py`) und in `harness/README.md:75`. Zwei davon waren Belegverweise, keine Dekorationen: `harness/README.md` verwies auf die S-15…S-18-Messungen *und* die Positivkontrollen (127 von 173 Testfällen rot an `02ceca2`) — der Inhalt steht jetzt im Absatz selbst, die Kontrollen zusätzlich als Verweis auf `tests/test_translator.py`. **Die Changelog-Einträge selbst blieben stehen**, nur ihre Zeiger auf die gelöschte Datei: zwei Einträge (2026-09-26 Tool-Call-Fix, 2026-09-11 Kontext-Management) dokumentieren reale Fixes, und Historie umzuschreiben ist hier derselbe Fehler wie bei den Agenten-Dateien. **Verifiziert:** 1682 Tests grün, alle drei Harnesses grün, `build-bundle.sh` läuft durch (52 Files, Bundle enthält `.python-version` und `app/glm2api.env` mit 11345 B = `.env.dist`), `bash -n` auf allen drei geänderten Skripten, Live-Proxy unberührt (`/health` ok, PID 210911) — er liest `.env`, nicht `.env.dist`.

- 2026-09-27: **Freebuff Wort-Navigation (`Strg+Links`/`Strg+Rechts`) und Wort-Löschen (`Strg+Backspace`) inklusive sauberer Zeilengrenzen:**
  - **Auslöser 1:** Nutzerbefund „ich kann bei freebuff mit strg+ pfeiltaste links und rechts nicht über wörter springen und strg + backspace löscht auch keine ganze wörter“. Analyse des Bundles (`RJ`, `pP`) belegte: Wort-Sprünge (`moveWordForward`/`moveWordBackward`, `cqA`/`lqA`) waren intern ausschließlich für `Alt`/`Option` (`\x1b[1;3D`, `\x1b[1;3C`, `\x1bb`, `\x1bf`) registriert, `Strg+Links`/`Rechts` (`\x1b[1;5D`, `\x1b[1;5C`) liefen ins Leere; `Strg+Backspace` sendet `\x08` (ASCII BS), was Freebuff als Einzelzeichen-Backspace behandelte. Gelöst in `freebuff-pty.py` via transparenter Sequenz-Übersetzung auf `Alt+Links`/`Rechts` und `Ctrl+W` (`\x17`).
  - **Auslöser 2:** Nutzerbefund „es springt immer zum Zeilenanfang — bei `Hey\n\nHey\n\nHey|` soll 2x Strg+Links zu `Hey\n\nHey|\n\nHey` springen, derzeit landet es bei `Hey\n\n|Hey\n\nHey`, genau wie beim Löschen“. Analyse von `LGA` (`word-backward`) und `_GA` (`word-forward`): Die interne Schleife fraß Leerzeilen/Umbruch (`/\s/`) und das davorstehende Wort in *einem* Aufruf zusammen. Gelöst über atomaren Vendor-Patch `patch_word_boundary` in `freebuff-install.sh`: Whitespace- und Wortschritte werden sauber getrennt (`s = $>0 && /\s/.test(...)`). Steht der Cursor am Zeilenanfang (`|Hey`), stoppt `Strg+Links` bzw. `Strg+Backspace` exakt am Zeilenende der vorigen Zeile (`Hey|`). `track_input` im PTY-Relay spiegelt dieselbe Wort-/Leerzeilen-Logik wider.
- 2026-09-27: **Autosave-Daemon abgeschaltet — er kam beiden schaden, und es war messbar.** Der Nutzer nutzt `save.sh` selbst am Ende jedes Arbeitsgangs; der Daemon lief zusätzlich alle 30 Min und tat drei Dinge, von denen zwei schadeten:
  - **`git add -A` mutierte den Index, den der auslösende Agent danach committet.** In der Freebuff-Sitzung hat das konkret schiefgegangen: Der Daemon hatte `infra/scripts/free-models.py` (905 Zeilen, Löschung aus einer parallel laufenden Refactor-Arbeit) **gestaged**, und mein pfadbegrenztes `git commit -- infrastructure.md` war eigentlich gedacht, genau solche Fremdänderungen nicht mitzunehmen — der Commit nimmt aber den **Index**, nicht die genannten Pfade, also flog die Löschung mit in `afed24f`. **Die Lehre war danach „pfadbegrenzt committen“, die eigentliche Ursache ist das `add -A` eines Dritten.**
  - **Halb-Zustände wurden als eigener Arbeitsgang verbucht:** 42 Commits mit Namen `autosave <Zeitstempel>` im Log, darunter `2eec781 autosave 2026-09-26T21:29Z`, das den glm2api-Refactor mitten im Arbeiten eingefroren hat. Die Commit-Nachricht transportiert keine Information, und der Zwischenstand ist im Verlauf schwer wiederzufinden.
  - **Nützlich war nur das Drive-Backup** — GitHub allein ist kein Backup, der Codespace ist ephemer. Genau daran hat es in dieser Sitzung gelitten: Das Backup von 01:27 enthielt `690e891`, mein Commit `6ab56c0` (Rechte-Korrektur am freebuff-Skript) fehlte und musste nachgeholt werden.
  **Umsetzung:** `.devcontainer/autosave-daemon.sh` gelöscht, die Startblöcke in `setup.sh` und `start-on-boot.sh` sowie der Neustart-Posten im `proxy-watchdog.sh` entfernt, der `autosave`-Alias aus `aliases.sh` und der Check in `verify-codespace.sh` drauf. `save.sh` bleibt unverändert und macht weiter Commit, Push **und** Drive-Backup in einem.
  **Die bewusste Konsequenz, die daraus folgt:** Was zwischen zwei `save.sh`-Aufrufen entsteht, ist nur noch über den Arbeitsbaum geschützt. Für verlorene Commits gilt weiter das alte Argument — der Codespace ist selbst ephemer, deshalb ist das Drive-Backup genau das, was der Daemon lieferte und jetzt `save.sh` liefert. Ein Workflow, in dem ein Agent minutenlang ohne Abschluss arbeitet und dann der Codespace wegfällt, verliert diesen Zwischenstand; das ist jetzt dokumentiert statt kaschiert.
- 2026-09-27: **Git-Signierung war kaputt und ist jetzt über SSH gelöst.** Symptom: jeder `git commit` bricht ab mit `gpg failed to sign the data … 403 | Author is invalid`. Ursache ist **nicht** die Identität, wie der Fehlertext suggeriert: Autor ist `tadeuslol <334215299+tadeuslol@users.noreply.github.com>`, GitHub-Account ist `login=tadeuslol id=334215299`, und selbst der PAT (`LANDSCAPE_PAT`) gehört demselben Account. `gh api user/emails` liefert dagegen `Resource not accessible by integration` — der Codespaces-`GITHUB_TOKEN` ist ein **App-/Integrationstoken**, und der Signierer `/.codespaces/bin/gh-gpgsign` (aus `/etc/gitconfig`) lehnt damit jede Signatur ab. In **zwei Wegwerf-Repos** A/B getestet: mit `GH_TOKEN=PAT` und mit `GITHUB_TOKEN=PAT` identisch 403, mit **SSH-Signierung** sofort `sig=G`.
  **Umsetzung:** `setup.sh` konfiguriert repo-lokal `gpg.format=ssh`, `user.signingkey=~/.ssh/codespaces.auto.pub`, `gpg.ssh.allowedSignersFile=.runtime/git-allowed-signers`, `commit.gpgsign=true` — der ED25519-Key gehört jedem Codespace und wird **lokal** benutzt, also ohne API und ohne Token. Die `allowedSignersFile` liegt bewusst in `.runtime/` statt im Repo: der Key kann pro Codespace neu sein, und sie enthält ohnehin nur den öffentlichen Schlüssel. Ohne sie meldet Git `%G? = N` („needs to be configured"), mit ihr `G`.
  **Was gelöst ist und was nicht:** Commit-Signaturen sind gültig und lokal prüfbar. GitHub wird sie aber als **signed, nicht verified** anzeigen, bis der Key einmalig unter *Settings → SSH and GPG keys* als **Signing key** registriert ist (`user/ssh_signing_keys` ist leer). Das ist ein Account-Schritt, der nicht im Codespace passiert — und die Wurzel, an der ein späterer Versuch wieder ansetzt.
  **Nebenbefund, wichtig für die Historie:** Bis dahin ist **jeder Commit unsigniert** (`%G? = N`), auch die aus der Parallel-Session. Ein nachträgliches Signieren historischer Commits ist nicht möglich; ab hier sind sie es.
- 2026-09-27: **Mausrad **und** Pfeiltasten funktionieren jetzt beide — weil sie dieselben Bytes sind und nur am Takt zu unterscheiden sind.** Ausloeser war ein Screenshot-Nutzerbefund in zwei Etappen: Pfeiltasten sollten im **gruen markierten Slash-Befahl-Menue** (`/new`, `/diagnostics`, `/history`, `/copy`) hoch und runter gehen und die Menues ueberhaupt bedienen; sie scrollten aber den Chat (rot markiert). **Erste Reaktion, die falsch war:** Umhaengung ersatzlos abgeschaltet, weil sie als opencode-1:1-Kopie eingebaut war und deren bewussten Preis mitnahm (`input_move_up: none` — der Input verliert die Pfeile). Bei opencode kostet der Preis nur Cursorbewegung, bei freebuff ist er der Nutzwert selbst. **Der Nutzer meldete zurueck: „jetzt geht Mausrad scrollen nicht mehr“ — und damit die entscheidende Tatsache, die in sechs Runden Doku-Debatte nie belegt war:** xterm.js schickt das Rad ohne Mouse-Reporting als `up`/`down`, **dieselben Bytes wie die Pfeiltaste**. Pauschal umhaengen macht die Pfeile kaputt, nicht umhaengen macht das Rad kaputt — **es gibt keine dritte Variante, die man per Tasten-Byte trennen koennte.** **Befund aus dem Key-Log** (`/tmp/opencode/freebuff-keys.log`, 13:20:17, waehrend des Nutzertests): ein Radschwung = **ein Log-Eintrag mit ~30 Ereignissen**, ein Tastendruck = **ein Eintrag**. Der Takt unterscheidet sie. **Umsetzung — Burst-Test in `infra/scripts/freebuff-pty.py`:** ein einzelnes `up`/`down` geht nativ an die App (Menue wandert), ein zweites **gleichgerichtetes** Ereignis binnen `FREEBUFF_WHEEL_GAP_MS` (Default 25 ms) macht die Geste zum Rad und schickt PageUp/PageDown. Das Einzelereignis wird dafuer hoechstens 25 ms zurueckgehalten — **das ist der ganze Preis der Trennung, und die Latenz ist der ehrliche Weg, den man bezahlt**, weil der Filter an dieser Stelle nichts anderes hat: die App bekommt in beiden Faellen dieselbe Taste, nur mit anderem Takt. 25 ms liegen ueber dem Abstand zweier Rad-Ereignisse (sub-ms, gleicher Read) und unter dem Tastenwiederholungs-Takt (Browser ~33 ms ab 500 ms Haltezeit), d.h. **ein gehaltener Pfeil wandert weiter das Menue und scrollt nicht**. Der `select`-Timeout der Hauptschleife wird auf das offene Fenster gekuerzt, sonst laege ein Einzelpfeil bis zum naechsten Event. **Verifiziert:** 26 Funktionstest-Faelle (Einzelpfeil nativ, 2x/6x-Burst = Seite, 40-ms-Doppeltipp und 3x-Wiederholung bleiben nativ, SS3-Varianten, rechts/links und `shift`/`ctrl` unveraendert und unverzoegert, Text+Pfeil, ueber zwei Reads zerrissene Sequenz, gemischte Richtungen, Drosselung, Fenster-Timeout) und end-to-end am echten pty — die Byte-Folge ans Kind war `ESC[A ESC[B ESC[A | 8x ESC[5~ | 5x ESC[6~ | ESC[B | hi`. **Zwei Bugs, die die Tests gefunden haben und die ohne sie in den Betrieb gegangen waeren:** (a) im Burst-Zweig wurde das *erste* Ereignis der Geste geschluckt, jeder Rad-Schwung scrollte also eine Zeile zu wenig — (b) der `select`-Timeout kann nicht 1 s bleiben. **Ehrliche Grenzen, die in die Doku gehoeren:** innerhalb des 25-ms-Fensters koennen andere Tasten dem zurueckgehaltenen Pfeil zuvorkommen (Reihenfolge kann kippen, Schrittzahl nicht), und der Debug-Log markiert den Fall zur Diagnose (`(Fenster abgelaufen)` = Tastatur, `ESC[5~` = Rad). Maus, bracketed Paste, Alternate Screen, `?1004` und der Scroll-Patch (`fOA` 0,5) sind unangetastet — **der Auftrag lautete ausdruecklich, die Maus nicht anzufassen.** **Modi:** Default Burst-Test, `FREEBUFF_ARROW_PAGE=1` alte Pauschal-Umleitung, `FREEBUFF_NO_ARROW_PAGE=1` gar keine Umschreibung. **Lehre, die den Fehler gekippt hat:** in sechs Runden wurde ueber *Dokumentation* gestritten, wer dem xterm.js-Versprechen glaubt; die eine Messung, die niemand gemacht hatte, war das Key-Log zur **richtigen Zeit** — es lag die ganze Zeit da und beantwortete die Frage in Sekunden. Und die Reihenfolge war lehrreicher als der Fix: „erst abschalten, dann sehen“ lieferte zwar sofort die richtige Diagnose („es ist dieselbe Taste“), kostete aber einen Nutzer-Rueckmelde-Rundgang, weil die halbe Wahrheit — dass das Rad an derselben Taste haengt — im Repo schon behauptet, aber nie belegt war.
- 2026-09-27: **Mausrad und Prompt-Historie — der Konflikt, der sich erst mit dem Screenshot zeigte, und seine Auflösung.** Nach dem Burst-Fix (Pfeiltasten-Umleitung, `FREEBUFF_ARROW_PAGE`) meldete der Nutzer zwei Dinge zugleich: die grüne Zone (Slash-Menü) war wieder mit Pfeiltasten bedienbar — **und** das Mausrad scrollte jetzt die Chatbox-Historie hoch und runter. Das ist kein Konfigurationsfehler, sondern die Konsequenz aus `xterm.js` schickt das Rad ohne Mouse-Reporting als `up`/`down`: **ein Rad-Klick ist byte- und taktgleich zu einem Tastendruck** (belegt im Key-Log: Radschwung ≈ 30 Ereignisse/s, Tastendruck = 1), und in freebuff ist `up` auf leerer Eingabe per Definition `history-up`. Dieselben Bytes, zwei gewünschte Bedeutungen.
  **Auflösung (Nutzerentscheidung): kontextabhängig nach Eingabe-Inhalt.** Der Filter zählt den Zeichenstand aus den **eigenen Tastatur-Bytes** (`track_input`: Enter → 0, Backspace −1, Ctrl+U → 0, Paste zählt mit, UTF-8-Fortsetzungsbytes nicht). Eingabe **leer** → jeder Pfeil sofort `PageUp`/`PageDown`, ohne Burst-Fenster (Rad blättert, Historie unberührt, ~0 ms Latenz). Eingabe **voll** → Pfeil nativ bzw. Burst-Test (Slash-Menü bedienbar, Rad-Geste blättert trotzdem). **Preis, bewusst akzeptiert:** `up` auf leerer Eingabe holt nicht mehr die letzte Nachricht, dafür gibt es `/history`.
  **Zwei echte Bugs hat die Testarbeit dabei gefunden** — beide in der ersten Fassung, beide aus derselben Wurzel (Entscheidung im falschen Moment): **(a)** `0x7f`/`0x08` (Backspace) wurden als druckbare Zeichen **gezählt**, im Strip-Regex stand zusätzlich versehentlich `[]`, was `0x08` ersatzlos entfernte — ein Backspace machte die Eingabe *länger*. **(b)** Der Kontext wurde **pro Chunk** statt **pro Position** ausgewertet: Tippen und Pfeil kommen im selben Read an (schnelles Tippen, Paste + Pfeil, träger Terminal), dann galt die Eingabe als leer und ein Pfeil im selben Chunk wurde zum Seitensprung — das hätte das grüne Menü wieder kaputtgemacht. Beide Fälle sind als eigene Testfälle festgehalten („Backspace zieht ab“, „`/ne` + Pfeile im selben Read“), 22 Funktionstest-Fälle grün, end-to-end am pty: `hallo\r wie gehts\r hey\r` + Rad → `ESC[5~ ESC[5~ ESC[6~`, `/ne` + Pfeile → `ESC[A ESC[B`.
  **Nebenbefund mit Sprengkraft:** freebuff hat sich **selbst auf 0.1.0 aktualisiert** (npm-Paket bleibt 0.0.204, der Launcher zieht das Binary immer neu). Damit ist der Anker des Scroll-Patches weg — `fOA=0.8` existiert nicht mehr, `fOA` ist in 0.1.0 ein React-`memo`-Bezeichner. Der Patch scheitert **laut** („Muster nicht gefunden → unangetastet“), nicht still; die Halbe-Seiten-Schrittweite ist damit bis zu einer Neuanbindung an die 0.1.0-Konstante weg. Und `scrollLines` in 0.1.0 ist **intern** (Split-Footer-Übergänge), keine Config — es gibt dort weiterhin keinen einstellbaren Scroll-Schritt.
- 2026-09-27: **Default umgedreht: freebuff laeuft wieder mit Maus — und der Grund steht im Bundle, nicht in einer Vermutung.** Ausgangspunkt war der Nutzerwunsch „das Rad soll NUR den Output-Block scrollen, nicht den Chat“. Nach vier Runden TUI-Analyse ist die Antwort belegt: **Output-Bloecke sind in freebuff ausschliesslich mausbedienbar.** Drei Belege aus 0.1.0: (a) der Block wird von `wAH` gerendert mit `J = L ?? (expandable ? 5 : 10)` — **5 Zeilen collapsed, 10 bei nicht aufklappbarem Block**; (b) der Ausklapp-Trigger ist `onClick`, und die **vollstaendige** Action-Liste der App lautet `toggle-agent-mode`, `toggle-all`, `toggle-dock-panel`, `toggle-sponsored-dock` — **kein `expand`, kein `collapse`, kein `scroll-block`**; (c) opentui vergibt Fokus **per Klick** (`while(L){if(L.focusable){L.focus();break}L=L.parent}`), nur ein fokussierter ScrollBox uebersetzt `pageup`/`up` in `scrollBy` (0,5 / 0,2 Viewport), und freebuff setzt nirgends `focusable` und fokussiert nur die Eingabe. **Der Fokus im Block entsteht also ausschliesslich per Klick** — und der pty-Filter entfernt genau diese Klicks. Damit war meine fruehere Rahmung falsch: „Maus aus, genau wie opencode“ war fuer **Copy/Paste** richtig und fuer **Scrollen im Output-Block** falsch; opencode ist tastatur-first, freebuff ist maus-first, das ist der Unterschied.
  **Was der Default jetzt kostet:** die native Terminal-Auswahl waehrend freebuff laeuft. **Was er bringt:** Rad scrollt Chat *und* Output-Bloecke, Bloecke klappen auf (5 → voll), Kopieren bleibt moeglich — freebuff kopiert beim Ziehen selbst, und `/copy` legt den **gesamten** Chat inkl. vollstaendigem Output in die Zwischenablage. Der Filter umhuelt ohnehin nur freebuff; in anderen Tabs und Sheets bleibt die native Auswahl unveraendert. Wer sie im TUI braucht: `FREEBUFF_PTY_FILTER=1` (der Filter bleibt vollstaendig, inkl. der kontextabhaengigen Pfeil-Umleitung).
  **Umsetzung:** Der generierte Wrapper startet freebuff direkt und nimmt den Filter nur noch bei `FREEBUFF_PTY_FILTER=1`; `FREEBUFF_NO_PTY_FILTER=1` bleibt als explizites Ausschalten erhalten. Verifiziert an echten Startsequenzen: Default lässt `?1000l ?1002l ?1003l ?1006l` durch (Maus an), mit Filter bleiben nur `?1004l` (Fokus) und `?2004l` (bracketed Paste) — beide Modi starten freebuff 0.1.0.
  **Nebenbefund mit Sprengkraft:** freebuff hat sich **selbst auf 0.1.0 aktualisiert**, das npm-Paket bleibt gepinnt bei 0.0.204. Damit ist der Anker des Halbseiten-Patches (`fOA=0.8`) weg — `fOA` ist in 0.1.0 ein React-`memo`-Bezeichner, und `scrollLines` ist intern (Split-Footer), keine Config. Der Patch scheitert laut statt still, und der naechste Anbindungsversuch sollte **mustersuche-basiert** (`viewport.height * Faktor`) statt namensbasiert erfolgen, damit ein Rename ihn nicht erneut killt.
- 2026-09-27: **Copy/Paste mit Maus an: `Ctrl+V` geht, `Ctrl+C` kann nicht — beides ist gemessen, nicht vermutet.** Nach dem Default-Wechsel auf Maus kam der Befund „copy paste mit Strg+C und Strg+V geht nicht“. Zwei getrennte Sachen, die man trennen muss: **`Ctrl+V` funktioniert** — freebuff schaltet Bracketed Paste (`?2004`) frei, und live geprueft erscheint `ESC[200~eingefuegter text ESC[201~` im TUI-Output, der Text landet also in der Eingabe. **`Ctrl+C` kopiert nur mit Auswahl**, und eine Auswahl kann im Terminal nur per Maus-Drag entstehen; die Maus hat jetzt freebuff, also ist `Ctrl+C` dort der Interrupt-Befehl der App (doppelt = beenden). Das ist xterm.js-Mechanik und **nicht behebbar**, ohne die Auswahl wiederherzustellen — was die Output-Bloecke wieder unbedienbar macht. **Deshalb als ein Schalter statt als zwei Betriebsarten im Alltag:** `freebuff -c` startet mit pty-Filter (Maus aus, Terminal-Auswahl, `Ctrl+C` kopiert), `freebuff` bleibt Default (Maus an, Rad und Klick im Block). Der Wrapper filtert das Flag selbst heraus; `--version`/`--continue`/`--cwd` werden unveraendert durchgereicht, an echten Startsequenzen verifiziert (Default laesst `?1000l` durch, `-c` entfernt es, beide starten 0.1.0 sauber). **Copy im TUI mit Maus an:** freebuff kopiert beim Ziehen selbst, `/copy` legt den gesamten Chat inkl. voller Outputs in die Zwischenablage.
- 2026-09-27: **Eine Betriebsart, und sie ist die mit Maus aus — der Default-Wechsel von eben wurde zurückgenommen.** Der Nutzerwunsch war eindeutig: `Ctrl+C` kopieren, `Ctrl+V` einfügen **und** Mausrad-Scrollen, alles in **einer** Version, ohne Schalter. Genau das liefert der pty-Filter: Maus aus heißt, das Terminal kann auswählen, also kopiert `Ctrl+C` (xterm.js kopiert nur mit Auswahl), `Ctrl+V` läuft über bracketed Paste (beides am echten TUI-Stream verifiziert: alle vier Maus-Sequenzen entfernt, `?2004h` und `?1004h` bleiben), und das Mausrad kommt als `up`/`down` an und wird kontextabhängig auf `PageUp`/`PageDown` umgehängt. **Der zwischenzeitlich eingebaute Schalter `freebuff -c` ist wieder entfernt**, samt der Dokuzeile „Default umgedreht“ als aktuelle Empfehlung — bleibt aber im Changelog als Historie stehen, weil die Begründung (Blöcke sind ausschließlich mausbedienbar) gültig bleibt.
  **Die Entscheidung fällt bewusst gegen die Maus**, obwohl die Maus mehr kann: Rad im Output-Block ja, Block aufklappen ja. Denn der Verlust bei „Maus an“ betrifft **das Kopieren** (Häufigkeit im Alltag: hoch), der Verlust bei „Maus aus“ betrifft **nur das Aufklappen eines Blocks** — und dessen vollständiger Inhalt ist trotzdem erreichbar: `/copy` legt den gesamten Chat in die Zwischenablage, `/export` schreibt ihn als Datei. Andersherum gilt: `Ctrl+C` ist in jedem TUI der Interrupt-Befehl, „Strg+C kopiert“ ist Terminal-Muskelgedächtnis, und das Terminal kopiert nur mit Auswahl — Auswahl braucht die Maus, die Maus braucht die App. Diese Kette ist der eigentliche Grund, warum es keine Konfiguration mit beidem für einen Cursor gibt.
  **Ein Irrtum, der mitkorrigiert wurde:** bei der Verifikation hatte ich das Binary direkt statt über den Wrapper gestartet und „Maus-Sequenzen vorhanden“ gemeldet — der Wrapper war umgangen. Nach Korrektur über `freebuff` exakt das erwartete Bild. (Dieselbe Sorte Fehler wie zuvor: nicht am Instrument, sondern am Aufrufpfad messen.)
- 2026-09-27: **Das war der opencode-Fix, und er ist 1:1 übertragbar — ich hatte die falsche Regel gebaut.** Der Nutzerbericht „es war genau das gleiche Problem bei opencode, das wurde hier gefixt“ war richtig, und die Lösung steht in `.opencode/tui.json`: `messages_half_page_up: "up"` (**Pfeiltasten gehören dem Scrollen**), `input_move_up/down: "none"` (**der Input bekommt sie nicht**), `history_previous: "ctrl+up"` (Historie umgezogen, weil die Pfeiltasten jetzt scrollen). Drei Zeilen Config — bei freebuff ohne Keybind-Config, aber der pty-Filter ist genau die Stelle, an der man sie nachbauen kann.
  **Meine Regel war zu eng und genau deshalb kam der Restfehler durch:** Ich habe nur bei *leerer* Eingabe umgehängt, sonst nativ durchgelassen — und freebuffs `history-up` konnte dann doch zuschnappen, sobald ein Entwurf in der Eingabe stand. Der Nutzer sah „manchmal scrollt das Rad die Chatbox mit“. Bei einer **einzeiligen** Eingabe gibt es für vertikale Bewegung aber nichts Vernünftliches: `up`/`down` sind dort entweder Historie oder gar nichts. **Also gilt jetzt dieselbe Aussage wie `input_move_up: "none"` — Pfeiltasten gehören dem Scrollen, der Input sieht sie nicht** — und der relevante Zustand ist der **Inhalt** der Eingabe, nicht ihre Länge, weil das Slash-Menü genau dann offen ist, wenn die Eingabe mit `/` beginnt. `track_input` führt deshalb jetzt den Inhalt (gekappt auf 512 Zeichen) statt einer Zeichenanzahl.
  **Regel:** Eingabe beginnt mit `/` → Pfeil nativ (Menü bedienbar). **Alles andere** → sofort `PageUp`/`PageDown`, ohne Burst-Fenster: das Rad scrollt die Unterhaltung und **nie** die Prompt-Historie. End-to-end am pty belegt mit dem Nutzerfall (`Hey ␍ ␍ Bye ␍` + zwei Radklicks → `ESC[5~ ESC[5~`).
  **Die Lektion aus fünf Runden:** Ich hatte „Eingabe leer" als Proxy für „der Input ist unzuständig" gewählt, statt die *ursprüngliche* Regel aus der Repo-Doku zu nehmen. `Revision.md` 4.16 nennt sie wörtlich — Halbseiten-Navigation über Auf-/Ab-Tasten, `input_move_up/down` bewusst auf `none`. Ein Proxy, den ich selbst erfunden habe, ist schwächer als die Regel, die schon dokumentiert war.
- 2026-09-27: **Save-Regel für jeden Agenten sichtbar gemacht — und ein stiller Fehler beseitigt, der teurer war als er aussah.** Zwei Aufträge: (a) `save.sh` meldet ein **fehlgeschlagenes** Drive-Backup nicht mehr als Erfolg, (b) jeder Agent kennt die Save-Pflicht nativ, ohne dass der Nutzer „commite/pushe“ sagen muss.
  **(a)** Der Backup-Hook stand auf `./infra/scripts/gdrive-backup.sh backup || true` — ein totes Backup war damit unsichtbar, und Drive ist die einzige Kopie außerhalb von GitHub. Jetzt: Warnblock nach dem Push mit dem Nachhol-Befehl `backup --force`; der Push-Erfolg bleibt unangetastet. Mit absichtlich kaputtem Backup-Skript verifiziert (Warnung erscheint, Save meldet Erfolg).
  **(b)** Nur `AGENTS.md` enthielt die Regel — die liest aber nur opencode/Codex. Claude Code liest `CLAUDE.md`, Gemini CLI `GEMINI.md`, Cursor `.cursorrules`, Copilot `.github/copilot-instructions.md`. **Neu angelegt:** `CLAUDE.md`, `GEMINI.md`, `.cursorrules`, `.github/copilot-instructions.md` — jeweils kurz, mit **verbindlichem** Zeiger auf `AGENTS.md` (doppelte lange Regeln driften auseinander, eine kurze Kopie mit Zeiger nicht). In `AGENTS.md` selbst drei Zusätze aus dieser Sitzung ergänzt: **nur eigene Pfade committen** (`git commit -- <pfad>` — `save.sh` macht vorher `git add -A`, und das Repo ist shared, live passiert), **kein Autosave-Daemon** (macht den Save-Aufruf zum einzigen Auslöser für Commit *und* Backup) und **Testläufe nicht committten**. **Gegen das Auseinanderlaufen prüft `verify-codespace.sh`** jetzt in einem neuen Abschnitt, dass alle fünf Client-Dateien existieren, die Save-Regel enthalten und die Pfad-Regel dokumentiert ist; ein neuer Client braucht eine Datei nach dem Muster plus eine Zeile im Check.
  **Und ein Fehler, den ich dabei selbst gemacht habe:** Mein Verifikationstest für (a) lief über `save.sh` mit einer Message — und erzeugte damit einen **echten Commit auf `origin/main`**, der das `gdrive-backup.sh` als 2-Zeilen-Stub enthielt. Behoben: Commit auf den echten Inhalt umgeschrieben und mit `--force-with-lease` gepusht (Nutzungsfreigabe), Message korrigiert. Die Lehre steht jetzt als eigene Regel in `AGENTS.md` unter „Testläufe nicht committten“ — ich hätte den Test mit einem Wegwerf-Repo fahren müssen, nicht über den echten Save.
- 2026-09-27: **Pfeiltasten zurück an die Menüs, und der Scroll-Patch lernt aus seinem eigenen Tod: Mustersuche statt Name.** Zwei Nutzeraufträge: (a) „Pfeiltasten gehören dem Scrollen — das soll nicht sein, Pfeiltasten sollen die Menüs bedienen können, nur die Pfeiltasten rausnehmen", (b) „keine Versionsnummern mehr, die aktualisieren immer schnell — und ich will die Scrollgeschwindigkeit wie zuvor".
  **(a)** Die Regel ist jetzt **burst-only**: ein einzelner Tastendruck läuft nativ durch (Slash-Menü, Auswahl — der Auftrag), eine **Geste** (≥ 2 gleichgerichtete Ereignisse binnen 25 ms) wird zu `PageUp`/`PageDown` (das Rad blättert die Unterhaltung), echte `PageUp`/`PageDown` gehen unverändert durch. Damit ist die Kontextlogik (`track_input`, 512-Zeichen-Inhalt, Erkennung des Slash-Menüs) **überflüssig geworden und entfernt** — sie diente nur dazu, den *einzelnen* Rad-Klick abzufangen, und genau der weicht jetzt dem Auftrag. **Preis, bewusst akzeptiert:** ein einzelner Rad-Klick (keine Geste) ist byte- und taktgleich zu einem Tastendruck und läuft nativ durch, rollt auf leerer Eingabe also die Prompt-Historie zurück. Das ist der Fall, der den Nutzer zuletzt gestört hat — er ist dem Wunsch nach Menü-Bedienung gewichen, und wer ihn nicht riskieren will, senkt `FREEBUFF_WHEEL_GAP_MS` (dann zählt auch der Einzelklick als Geste). Verifiziert: 1× hoch = nativ, 1× runter = nativ, Geste 2/4/6 und gemischt = Seiten, `links`/`rechts` unberührt, `FREEBUFF_ARROW_PAGE=1` erzwingt Seiten, zerrissene Sequenz über zwei Reads korrekt; end-to-end am pty: 8 Rad-Ereignisse → 8 `ESC[5~`, echte `ESC[5~`/`ESC[6~` unverändert.
  **(b)** **Versions-Pin entfernt** — `freebuff-install.sh` installiert `freebuff@latest` und überspringt nur, wenn die installierte Version der aktuellsten aus `npm view` entspricht. **Und der Scroll-Patch ist auf Mustersuche umgebaut**, weil sein Tod die Ursache exakt belegt: 0.0.204 hieß die Faktor-Variable `fOA`, 0.1.0 heißt sie `$hA` — beide mit dem Wert 0.8, und der namensbasierte Patch (`fOA=0.8`) war beim ersten Update tot. Jetzt sucht er die Struktur: `Math.floor(<A>*<VAR>)` neben `viewport.height` → Definition `<VAR>=<0.x>` → genau diese eine Zahl ersetzen. Ein Rename killt ihn damit nicht mehr; bricht die Struktur ab, meldet er `Struktur nicht erkannt` und lässt das Binary unangetastet. Am echten Binary verifiziert: erkannte Variable `$hA`, Definitionsstelle 1, `0.8 → 0.5`, gepatchtes Binary startet (0.1.0), Größe unverändert, Idempotenz bestätigt.
- 2026-09-27: **Pfeiltasten-Änderung zurückgenommen — der Stand vor dem Auftrag war der richtige.** Der Nutzerwunsch war, Pfeiltasten aus dem Scroll-Pfad zu nehmen (Menüs bedienen). Umgesetzt als **burst-only**: einzelne Tastendrücke nativ, nur Gesten werden zu `PageUp`/`PageDown`. Das Ergebnis war schlechter: **das Rad scrollte den Text wieder hoch und runter** — also genau das, was zwei Runden vorher als Fehler gemeldet und behoben war. Der Nutzer ordnete an: **auf den Stand davor zurück**. `infra/scripts/freebuff-pty.py` ist wieder exakt der Commit `918f26b` (kontextabhängige Umleitung nach Eingabe-Inhalt, `track_input` wieder da, `flush_pending` mit lokaler Variable gegen die Fehlermeldung des Type-Checkers).
  **Was dabei bewusst NICHT zurückgenommen wurde**, weil es zwei getrennte Aufträge waren: **kein Versions-Pin** (Installiert wird `freebuff@latest`) und der **Scroll-Patch per Mustersuche** (`0.8 → 0.5`, rename-robust). Beides hat der Nutzer ausdrücklich gewollt.
  **Die Lehre, die ich dazuschreibe, weil sie das eigentliche Problem ist:** Ich habe „Pfeiltasten rausnehmen" als *die* Änderung gelesen und die beiden anderen Aufträge desselben Satzes mit erledigt — und dann das Ganze als geschlossen gemeldet, ohne die eine Sache zu prüfen, auf die es ankam: **scrollt das Rad noch in der richtigen Richtung?** Bei einem TUI-Problem ist „Filterlogik umgebaut" kein Ergebnis, sondern nur die Voraussetzung; das Ergebnis ist „Rad blättert, Menü bedienbar, Historie unberührt", und das prüft man am laufenden TUI, nicht am Test.
- 2026-09-27: **Pfeiltasten-Regel richtiggestellt: Pfeiltasten bleiben nativ, nur eine Geste wird `PageUp`/`PageDown`.** Der Nutzer meldete live: „jetzt funktionieren die Pfeiltasten hoch und runter gar nicht mehr" — die unmittelbar vorherige Fassung hatte Einzelereignisse **verworfen** (Kontext: nur bei offenem Slash-Menü nativer Pfeil). Das war eine Fehlinterpretation von „Pfeiltasten nativ": Verwerfen ist keine Nativeingabe, es ist Totstellen. **Verworfen wurde nicht nur die Taste, sondern auch der Zweck — das Mausrad wurde dadurch keinen Deut besser, weil es dieselben Bytes sendet.** Ein verworfener Tastendruck ist damit reiner Verlust gewesen.
  **Die Regel ist jetzt zweiteilig, und die Reihenfolge der Prüfung ist der Kern:** *Geste* (zweiter Treffer im 25-ms-Fenster oder `burst_until` aktiv) → `PageUp`/`PageDown`, beide Ereignisse werden gemeldet; *Einzelereignis* → **nativ, unverändert**, inklusive `history-up`. Das erste Ereignis einer Serie wird dafür **zurückgehalten, nicht verworfen** — nur so erkennt ein zweites gleichgerichtetes Ereignis die Geste.
  **Der Preis bleibt und ist unausweichlich:** Ein *einzelner* Rad-Klick ist byte- und taktgleich zu einem Tastendruck; „Pfeiltasten nativ" und „kein Rad-Klick löst `history-up` aus" schließen sich aus. Der Nutzer hat entschieden — Pfeiltasten nativ. Ein Einzelklick errollt die Historie deshalb wie die echte Taste, jede *Geste* (also normales Scrollen) blättert die Unterhaltung.
  **Dazu die tote Kette konsequent entfernt** (das war die eigentliche Ursache für den Totalausfall): `track_input`, `ESC_SEQ_RE`, der `text`-Parameter von `rewrite_arrows` und die `text`-Verfolgung in der Hauptschleife sind ersatzlos gestrichen. Der Filter muss am Ende **nichts** über den Eingabeinhalt wissen — die frühere Kontextlogik („Pfeil bleibt nativ, wenn die Zeile mit `/` beginnt") war selbst die Ursache dafür, dass `history-up` ohne Menü nicht mehr erreichbar war.
  **Zwei Fehler beim Testen gefunden, nicht durch Raten ersetzt:** (1) Der Test-Harness hat zwischen zwei Reads nicht geflusht, obwohl die echte Schleife das über den Select-Timeout tut — dadurch erschienen „3 einzelne Pfeile" als *eine* Ausgabe. (2) Beim Messen am echten pty schrieb der Treiber die ersten Tasten, bevor der Filter im `select` war; die pty pufferte sie, zwei kamen gemeinsam an. Mit Wartezeit auf Startbereitschaft: 28 Byte-exakte Funktionstests grün, am echten pty bestätigt — 3 einzelne Pfeile (100 ms) → 3 native Pfeile, 5× gehaltener Pfeil im 33-ms-Wiederholungstakt → 5 native Pfeile und **0** Seiten, Rad-Geste mit 10 Events → 10 `PageUp` und 0 native Pfeile, `links`/`rechts` und echtes `PageUp`/`PageDown` unverändert, `/ne` + Pfeile nativ.
  **Dokumentierte Feinheit statt versteckt:** Der gehaltene Pfeil ist 25 ms verzögert; wird innerhalb dieses Fensters weitergeschrieben, verschiebt sich die Byte-Reihenfolge. Für die Navigation irrelevant, im Test mitprotokolliert.
- 2026-09-27: **Pfeiltasten- und Mausrad-Dilemma endgültig gelöst: 1:1 PageUp/Down im Chat, nativ in Menüs und Multi-Fragen.**
  - **Problem & Ursache:** Im Browser-Terminal (xterm.js) schickt das Mausrad hartcodiert dieselben Bytes wie die Pfeiltasten (`ESC[A`/`ESC[B`). Freebuff ignoriert Pfeiltasten bei befüllter Eingabezeile komplett (`return {type:"none"}`), während `PageUp`/`PageDown` (`ESC[5~`/`ESC[6~`) immer und ausschließlich das Unterhaltungsfenster scrollt und den Schreibbanner nie berührt.
  - **Lösung:**
    * **Im Chatfenster (leer oder während des Tippens):** Pfeile werden 1:1 zu `PageUp`/`PageDown` umgeschrieben. Mausrad scrollt 1:1 die Unterhaltung, bewegt nie den Schreibbanner, und Scrollen funktioniert auch mit getipptem Text im Fenster.
    * **In Menüs (Slash-Menü `/`, `/history`, `/model`):** Pfeiltasten bleiben 100 % nativ für die Tastaturauswahl.
    * **In Agenten-Fragen (`ask_user` / OptionsList):** Wird anhand der Screen-Muster (`Enter select`, `Type your own answer`, `(Select multiple options)`, `↑↓ navigate`) erkannt. Pfeile bleiben nativ.
    * **Multi-Fragen-Unterstützung (Frage 1 → 2 → 3...):** Enter schließt den Fragenmodus bewusst **nicht** (da Enter von Frage 1 zu Frage 2 springt). Der Fragenmodus schließt erst, wenn Freebuff `Your answer:` / `Your answers:` ausgibt oder der Nutzer Esc / Strg+C drückt.
    * **Textauswahl & Copy/Paste:** Bleibt unberührt (PTY-Filter filtert Maus-Reporting, Strg+C kopiert, Strg+V fügt ein).
## Changelog

Die Historie liegt in [`infra/docs/changelog.md`](infra/docs/changelog.md),
neueste zuerst. Ausgelagert am 2026-10-21 (sie machte 81 % dieser Akte aus).
Der Soll-Zustand steht weiter hier; **neue Eintraege gehoeren in die
Changelog-Datei**, nicht in diese.
