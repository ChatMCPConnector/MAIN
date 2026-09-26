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
| `infra/` | **Werkzeugkasten:** `scripts/` (save/auth/secrets/ports/browser-*.sh, aliases.sh, config-watchdog.sh, validate-revision.sh), `mcp/` (opencode-sessions MCP), `docs/` (Reverse-Engineering-Doku) |
| `llm-proxies/` | LLM-Proxies: **glm2api** (Port 8001, GLM-Haupt-Proxy) + **antigravity-proxy** (Port 9878, CloudCode OAuth) |

| `.env` `.runtime/` | GITIGNORED — Klartext-Secrets (.env), Browser-Profil, Runtime (nie committen) |

## Schnellstart

Codespace bauen → `setup.sh` stellt ALLES automatisch wieder her (Systempakete,
opencode, uv, Secrets-Unlock, Git-Auth, Freebuff-CLI, Browser-Runtime,
**glm2api-Proxy inkl. Start** — der Code liegt komplett im Repo, es gibt nichts
mehr zu klonen; nur `uv sync` (Python 3.14 + Deps, beim ersten Mal ~2-5 Min) +
Autostart). Danach:

```bash
./infra/scripts/save.sh status                       # Überblick (Repo, Auth, Secrets)
./infra/scripts/validate-revision.sh                # read-only Revision.md-Check
```

Aliase (via `infra/scripts/aliases.sh`, automatisch in .bashrc): `save`, `auth`,
`secrets`, `keys` (status/doctor/restore), `ports`, `quota`, `st`, `ll`, `autosave` (status/start/stop/log),
`config-watchdog` (status/start/stop/log), `landscape-diff`, `ocver`
(opencode-Versionspin: check/latest/bump/install), `csecret` (Codespaces-Secrets).

## Enthalten

- Ports 3000/8000 (Apps), 4096 (opencode-Server für Multi-Client), 8001 (glm2api LLM-Proxy), 9878 (antigravity-proxy), 6082/5920 (Browser-VNC, nur lokal)
- opencode, Default-Modell `antigravity/gemini-3.8-flash` (fest auf high Thinking gemappt)
- Freebuff CLI: kostenloser, werbefinanzierter Coding-Agent, gepinnt 0.0.204,
  liegt wie opencode ephemer in `$HOME/.local/share/freebuff` (Wrapper
  `freebuff` im PATH), Login verschlüsselt im Secret-Bundle → in jedem
  Codespace eingeloggt. `cd <projekt> && freebuff`.
  Kein API-Endpoint für opencode (kein OpenAI-kompatibler Server, kein
  Headless-Modus); werbefinanziert, Prompts werden zur Ad-Personalisierung
  ausgewertet → nichts Geheimes rein.
- `.vscode/keybindings.json`: **Mausrad = PageUp/PageDown im Terminal**
  (`terminal.sendSequence` mit `\e[5~`/`\e[6~`, `when: terminalFocus`). Nötig,
  weil das Mausrad nach dem Abschalten des Mouse-Reportings ein
  Terminal-Scrollback-Ereignis ist — und Freebuff im Alternate Screen keinen
  Scrollback hat. opencode scrollt über denselben Weg, Freebuff nicht. Weil
  freebuff pro Tastendruck nur 10 Zeilen scrollt (der Chat-Handler ruft
  `preventDefault` und unterdrückt opentuis 0,5-Viewport-Schritt), sendet die
  Keybinding **dreimal** PageUp/PageDown — die `3` ist eine Magic Number, die
  bei freebuff-Updates nachgezogen werden muss. Der Kommando-Output-Block in
  einer Nachricht ist dagegen **nur mit der Maus** scrollbar (freebuff setzt
  `focusable` nirgends, `onMouseWheel` kommt nicht vor) — das Rad dort ist ein
  Entweder-oder gegen Copy/Paste, umschaltbar mit
  `FREEBUFF_NO_PTY_FILTER=1 freebuff`. Details: „Maus, Copy/Paste & Scrollen
  in TUIs".
## Secrets-Modell (bewusst: Komfort > Sicherheit)

Repo ist shared für mehrere **eigene** Accounts. Automatik hat Vorrang vor
Secret-Schutz-Purismus:

- `config/passphrase`: Entschlüsselungs-Passphrase als Klartext im Repo → jeder
  eigene Codespace entsperrt sich beim Start selbst. Sie ist NUR ein
  Entschlüsselungswort — nie ein Secret/PAT als Passphrase zweckentfremden
  (der alte PAT wurde dadurch geleakt und von GitHub revoked).
- `config/secrets.enc` (+ Manifest): verschlüsseltes Bundle mit
  `pat`, `xinjianya.key`, `antigravity-oauth_creds.json`,
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
- XinJianYa-Keys in `opencode.json` referenzieren `{file:~/.config/landscape/<key>}` und kommen über das Bundle in jeden neuen Codespace. `glm2api` nutzt lokal `local` als Platzhalter; TokenRouter und Antigravity enthalten weiterhin getrackte Literalwerte (siehe `Revision.md`, `SEC-02`).
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
    (2026-09-26 verifiziert). Im Zweifel `opencode run --model
    <provider>/<modell>` — nur das beweist Nutzbarkeit.


## opencode-Konfiguration (`.opencode/`)

Provider (`opencode.json`, Default `antigravity/gemini-3.8-flash`):

| Provider | Modelle | Auth |
|---|---|---|
| xinjianya | gpt-5.6-sol | xinjianya.key |
| **glm2api** | glm-5.3 | lokal, Port 8001, kein Key |
| **antigravity** | claude-opus-4-6 (100k Context, Thinking 1k/4k/8k), gemini-3.8-flash (1M, 64k Output, fest auf High-Thinking gemappt) | lokal, Port 9878, Google Cloud Code OAuth |

- `mcp.opencode-sessions`: Session-Verwaltung direkt auf der SQLite-DB
  (`infra/mcp/opencode-sessions-mcp.js`, zero deps) — list/preview/delete/search,
  kaskadierende Löschung + Orphan-Event-Cleanup, schützt aktive/aktuelle/geteilte
  Sessions, `confirm:true` Pflicht. Details: `infra/mcp/README.md`.
- `agent/glm2api.md`: Arbeits-Subagent fest auf `glm2api/glm-5.3` (Haupt-Proxy).
- `tui.json`: Maus-Capture **aus** (`mouse: false` ist Absicht: sobald eine App
  Mouse-Reporting einschaltet, behandelt das Terminal Mausereignisse als
  App-Eingaben — Text markieren und kopieren geht dann nicht mehr.
  **Nicht auf `true` ändern.**) Das Mausrad ist separat gelöst, siehe
  „Maus, Copy/Paste & Scrollen in TUIs".

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
- **Freebuff CLI** (werbefinanzierter, kostenloser Coding-Agent von CodebuffAI),
  Version **0.0.204 gepinnt** in `infra/scripts/freebuff-install.sh`, automatisch
  via setup.sh — **nach** dem Secrets-Schritt, weil der Login aus dem Bundle
  kommt. Modell **bewusst wie opencode**: das Repo *verwaltet* die Installation,
  die Dateien liegen ephemer in `$HOME/.local/share/freebuff`, der Einstiegspunkt
  ist der Wrapper `~/.local/bin/freebuff` (PATH via `aliases.sh`). **Nichts unter
  `/workspaces`** — ein früherer Zwischenstand hatte das native Binary zwischen
  `/workspaces/freebuff/bin/` und `$HOME` hin- und herkopiert; der ist verworfen.
  - **Zwei Ebenen, die man unterscheiden muss:** die npm-Pin (Launcher, hier
    gepinnt) und das **native Binary, das der Launcher selbst nachlädt** — es
    zieht immer das *neueste* veröffentlichte Binary (live belegt: npm-Pin
    0.0.203, Launcher zog 0.0.204 und schrieb `.freebuff-0.0.204-*.tar.gz.part`
    nach `$HOME`). Die Pin ist damit für den Launcher belastbar, für das Binary
    nicht — ein Upstream-Release kommt mit dem nächsten Codespace-Build durch.
    Deshalb: `FREEBUFF_VERSION` im Skript an `npm view freebuff version`
    angleichen, und die `.part`-/`.freebuff-download-temp-*`-Reste aufräumen
    (fressen sonst bei jedem Start Platte).
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

### Maus, Copy/Paste & Scrollen in TUIs (opencode + Freebuff)

Eine Klaesse Problem, zwei Loesungen — und die Reihenfolge ist wichtig, weil
beide Enabls sich ausschliessen:

| | Mouse-Reporting | Markieren/Kopieren | Mausrad scrollt |
|---|---|---|---|
| Default (App schaltet Maus an) | an | **nein** | ja (App-Scroll) |
| opencode mit `mouse: false` | aus | ja | ja (Terminal-Scrollback, kein Alternate Screen) |
| Freebuff ueber `freebuff-pty.py` | aus | ja | **nein** (Alternate Screen) |

**1. Copy/Paste.** opencode: `mouse: false` in `.opencode/tui.json` (Terminal-
Eigenheit, keine App-Abschaltung). Freebuff: den Kniff gibt es nicht — weder
`settings.json`-Key, noch CLI-Flag, noch Env (am Binary 0.0.204 verifiziert;
opentui kennt intern `useMouse`, Default `true`, Freebuff setzt es nicht).
Loesung deshalb **aussen**: `infra/scripts/freebuff-pty.py` (pty-Relay) filtert
ausschliesslich `CSI ? 1000|1001|1002|1003|1005|1006|1015|1016 (h|l)` aus dem
Output. `?2004` bracketed Paste, `?1004`, `?1049` und Kitty-Keys bleiben
angetastet — sonst waere Pasten kaputt. Der Wrapper `~/.local/bin/freebuff`
startet nur bei echtem TTY ueber den Filter (`FREEBUFF_NO_PTY_FILTER=1` =
Direktstart). Preis: Freebuffs eigene Auswahl per Drag entfaellt, kopiert wird
wie im normalen Terminal (Maus ziehen, `Ctrl+Shift+C`).

**2. Mausrad.** Nach Schritt 1 nimmt das Terminal die Rad-Events als
Scrollback-Aktion — und **genau hier unterscheiden sich die beiden Apps:**
opencode rendert im normalen Buffer, also scrollt das Terminal den sichtbaren
Text mit. Freebuff nutzt den Alternate Screen (`CSI ? 1049 h`, live belegt) —
dort existiert kein Scrollback, ein Rad-Ereignis bewegt sich sichtbar also
**nichts**. Man kann den Rad-Event aber zu einer Taste machen, denn die App
bindet sie ohnehin: im Binary steht `case"pageup": scrollBy(-0.5,"viewport")`
und `case"pagedown": scrollBy(0.5,"viewport")`, der Key-Parser mappt
`\e[5~`/`\e[6~` darauf. Also mappt **`.vscode/keybindings.json`** (neu, Repo-
Ebene, `when: terminalFocus`):

```json
{ "key": "mousewheel up",   "command": "workbench.action.terminal.sendSequence",
  "args": { "text": "\u001b[5~" }, "when": "terminalFocus" }
{ "key": "mousewheel down", "command": "workbench.action.terminal.sendSequence",
  "args": { "text": "\u001b[6~" }, "when": "terminalFocus" }
```

Das ist **anwendungsneutral** und gilt fuer jeden Terminal, auch fuer `less`,
`vim`, `man`, `htop`. Was sich aendert: das Mausrad scrollt in TUIs jetzt
Tastenseiten (PageUp/PageDown) statt Terminal-Scrollback. Bei opencode ist das
genau das Gewuenschte (`messages_page_up`/`messages_page_down` in `tui.json`).

**Freebuff braucht dafuer einen Multiplikator — und der Grund ist nicht
Kosmetik.** Im Chat-Screen von freebuff gibt es keine Taste fuer einen
Seitensprung. Der Component-Handler lautet woertlich:

```
case"up":X(); break;  case"down":v(); break;
case"pageup":J.current?.scrollBy(-10); break;      // 10 ZEILEN
case"pagedown":J.current?.scrollBy(10); break;
case"home":J.current?.scrollTo(0); break;  case"end":B(); break;  // Anfang/Ende
a.preventDefault?.()                                    // Event wird geschluckt
```

Das `preventDefault` ist der entscheidende Punkt: opentuis eigener ScrollBox-
Handler wuerde `pageup` auf **0,5 Viewport** mappen (`scrollBy(-0.5,"viewport")`),
wird aber nie erreicht, weil der Component das Event vorher konsumiert. **Ein
Tastendruck scrollt in freebuff also maximal 10 Zeilen** — „Bild hoch/runter"
existiert als Taste nicht. Die Keybinding sendet deshalb **drei** PageUp/
PageDown pro Rasterung (`\e[5~` dreimal), das ergibt ~30 Zeilen und damit
gefuehlsmaessig eine Bildschirmseite. Die `3` ist eine Magic Number und steht
deshalb an beiden Stellen im Repo (hier und im Changelog). Aendert freebuff den
Schritt, muss sie nachgezogen werden; `home`/`end` im Tastaturlayout sind der
Rettungsweg fuer den Sprung ans Ende.

**Die harte Grenze: Block-Scrollen vs. Copy/Paste — ein Entweder-oder.**
Der Wunsch „Mausrad soll nur im Kommando-Output-Block scrollen, nicht im Chat"
ist in freebuff 0.0.204 **nicht baubar**, und das ist kein Verkken des Rezepts.
Belegt am Bundle:

* Es gibt 7 `scrollbox`-Instanzen. Eine davon ist der Kommando-Output-Block
  (berechnet `heightLines`/`isScrollable`, `verticalScrollbarOptions.visible`,
  `trackOptions.width:1`) — der hat also **eigene Scrollbar** und ist ab einer
  Höhenkappe scrollbar. Die anderen sechs sind Nachrichtenliste, Agentenliste,
  Detailpanel, Leerzustandsliste.
* opentui wuerde diesem Block ueber `handleKeyPress` **0,5 Viewport** pro `pageup`
  geben — aber **nur, wenn er fokussiert ist**.
* freebuff setzt `focusable` **nirgends** (alle 17 Treffer im Bundle sind
  opentuis Basisklasse, keine freebuff-Verwendung), und `onMouseWheel` kommt
  **null Mal** vor. Es gibt also keinen Weg, den Block zu fokussieren.

Damit bleibt dem Block genau **eine** Bedienart: die Maus. Und die Maus ist
derselbe Kanal, an dem die native Textauswahl des Terminals haengt. Die beiden
Wünsche schliessen sich aus:

| | Rad scrollt Output-Block | Block aufklappbar | Terminal-Auswahl/Kopieren |
|---|---|---|---|
| Maus-Reporting **an** (Filter aus) | ja | ja (Klick) | nein — aber freebuff kopiert selbst (`Drag to select text — it copies automatically`) |
| Maus-Reporting **aus** (Filter an, **Default**) | nein | nein | ja, wie opencode |

Default ist bewusst die zweite Zeile (Entscheidung des Nutzers am 2026-09-26:
„Maus soll aus, ich brauche keine Maus genau wie bei opencode").

opencode hat diesen Konflikt nicht, weil `tui.json` **jede** Scroll-Aktion an
Tasten bindet. Genau das fehlt freebuff.

**Praxis-Konsequenz (und der Grund, warum das so bleibt):** Die Engineered-
Entscheidung vom 2026-09-26 ist **Maus aus** — freebuff soll sich wie opencode
anfuehlen, terminal-native Auswahl und Kopieren, keine Mausklicks. Der Preis ist
der 5/10-Zeilen-Cap der Kommando-Outputs, und der laesst sich nicht umgehen,
sondern nur umgehen *umgangen* — mit den Mitteln, die freebuff selbst mitbringt:

| Weg | Was | Belegt am Bundle |
|---|---|---|
| `/copy` (Alias `copy-chat`) | kopiert den **ganzen** Chat inkl. vollstaendigem Kommando-Output in die Zwischenablage | `s0({name:"copy",aliases:["copy-chat"],handler:…iCA(H)})` |
| `/export` (Alias `export-chat`, nimmt ein Ziel) | schreibt den Chat als Datei — der robusteste Weg, unabhaengig von der Zwischenablage | `eX({name:"export",aliases:["export-chat"],handler:…jCA(H,A)})` |
| breiteres Terminal | `maxVisibleLines` zaehlt **umgebrochene** Zeilen — mehr Spalten = mehr Text in denselben 5 Zeilen | `wrapMode:"word"`, `J=L??($?5:10)` |
| `FREEBUFF_NO_PTY_FILTER=1 freebuff` | einmaliger Start **mit** Maus, wenn es schneller gehen muss: Block aufklappbar und scrollbar, Kopieren dann ueber freebuffs eigenes Drag-to-copy | Wrapper-Env, siehe oben |

Die ersten drei brauchen keine Maus und sind der Grund, warum der Filter
Default bleibt. `!bash`/`/bash` fuehrt zusaetzlich direkt im TUI ein Kommando
aus — dessen Ausgabe erscheint im selben 10-Zeilen-Cap, also gilt fuer sie
`/copy` genauso.

**3. Reihenfolge nicht umkehren.** Wer `mouse: true` setzt, bekommt Copy/Paste
zurueck, verliert aber das Mausrad **und** die Block-Scrollbarkeit. Wer
`freebuff-pty.py` entfernt, verliert Copy/Paste. Die Keybinding-Zeile allein
reicht nicht — sie ersetzt den Scrollback-Mechanismus nicht, den man fuer
Copy/Paste abgeschaltet hat, und sie erreicht den Output-Block ueberhaupt nicht,
weil der Block nicht fokussierbar ist.

**4. Ausserhalb von VS Code** (ssh, tmux, eigener Terminal-Emulator): die
Keybinding greift nicht, dann einfach die Tastatur — `PageUp`/`PageDown`
scrollen in beiden TUIs. `tmux`-Nutzern: Maus ist dort per `set -g mouse off`
ohnehin deaktiviert, dieselbe Wirkung.

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
| Laufzeit | `start-glm2api.sh` idempotent | Doppelstart-sicher, Port-Check. **Merksatz:** die beiden Startwege müssen gleichwertig bleiben — `infra/scripts/glm2api.sh` (interaktiv) und `start-glm2api.sh` (Boot/Watchdog). Sie waren es nicht: nur der zweite startete mit `setsid`, und ein Agent-Tool-Call im Timeout schickte dem interaktiv gestarteten Proxy SIGTERM mitten im Stream (Changelog 2026-09-26) |
| **Idle-Schutz** (offene Commits vor Shutdown sichern) | **`autosave-daemon.sh`** (Daemon, 30-Min-Intervall) | Alle 30 Min: prüft auf uncommittete Änderungen oder ungepushte Commits → `save.sh` (add -A, commit, pull --rebase, push). Kein leerer Commit-Spam. Start via start-on-boot.sh + setup.sh, Lockfile `/tmp/opencode/autosave-daemon.lock`, Log `/tmp/opencode/autosave.log`. Shell: `autosave {status|start|stop|log}` |
| **Config-Auto-Restart** (neue Modelle sofort verfügbar) | **`config-watchdog.sh`** (Daemon, inotify-Event-basiert) | Überwacht `.opencode/opencode.json` per `inotifywait` (close_write/moved_to) auf dem **Verzeichnis**; **Hash-Vergleich** nach jedem Event, damit Schreibvorgänge auf anderen Dateien im Ordner (`tui.json`, `package-lock.json`, neue `agent/*.md`) keinen Restart auslösen; Debounce 8s + **Busy-Guard** (prüft `/session/status`, wartet bis alle Sessions idle sind vor Restart, kein Abbruch laufender Turns) + Pause-Mechanismus (`config-watchdog.pause`). Fallback auf Polling (10s md5sum) falls inotify-tools fehlt. Start via start-on-boot.sh + setup.sh, Lockfile `/tmp/opencode/config-watchdog.lock`, Log `/tmp/opencode/config-watchdog.log`. Shell: `config-watchdog {status|start|stop|pause|resume|log}` |

**Proxy-Verhalten nach Stopp:** Prozesse sterben, `/tmp` (Logs) wird geleert —
Code, venv und .env in MAIN überleben alles. Der Boot-Mechanismus zieht den
Proxy bei jedem Start automatisch hoch.

## Changelog

- 2026-09-26: **Cline und NVIDIA NIM aus opencode entfernt, `free-models.py` gelöscht — Grund ist Betriebsverlässlichkeit, nicht Modellqualität.** Auslöser war die Frage nach den Reasoning-Stufen von `stealth/pixel-canary`, deren Antwort in Cline-Timeouts und sporadischen 500ern unterging. **Was die Messung ergab** (Cap-Probe und Token-Vergleich, beide gegen die Cline-API): `none` liefert 0 Reasoning-Tokens, `high` 298, `xhigh` 464, `max` 349–349 — und `max` lief in 1 von 3 Läufen in einen Timeout >300 s, `xhigh` einmal in einen Vercel-500. opencode kennt intern genau sieben Stufen (`none, minimal, low, medium, high, xhigh, max`, Enum im Binary), mehr gibt es nicht; für `@ai-sdk/openai-compatible` reicht es jeden String ungeprüft als `reasoning_effort` durch. **Der eigentliche Befund ist aber der Provider, nicht die Stufen:** derselbe Aufruf lieferte im Tagesverlauf mal 200 und mal 500, ein Lauf von `max` lief 68 s, der nächste über 300 s in den Timeout, und ein `opencode run` gegen den Provider endete in `Unexpected server error`. Ein Provider, der ein Viertel der Anfragen verliert, ist im Hauptbetrieb unbrauchbar, egal wie gut die Modelle sind. **Entfernt:** beide Provider-Blöcke aus `opencode.json` (`cline`, `nvidia` — letzterer trug `z-ai/glm-5.3`), die Aliase `free-models`/`cline-models`/`nvidia-models`, die beiden `KEYS`-Zeilen in `keys.sh` sowie Pack- und Restore-Paar in `secrets.sh`. **Die Key-Dateien `~/.config/landscape/cline.key` und `nvidia-nim.key` bleiben bewusst auf der Platte** — sie sind nicht Teil des Caches oder der Profile, und `secrets.sh lock` ignoriert sie jetzt, sobald sie nicht mehr referenziert sind. **Nebenbefund, der die Entscheidung stützt:** die Cap-Probe, mit der die Stufen geprüft werden sollten, war an `space-bunny-alpha` zweimal hintereinander nicht reproduzierbar (einmal 500 „will mehr Reasoning", einmal 200 mit 0 Tokens) — dieselbe Fehlermeldung also ohne Aussagekraft. Verifiziert: `opencode models` zeigt keinen `cline/`- und keinen `nvidia/`-Eintrag mehr, `keys.sh status` listet nur noch `xinjianya.key`, `bash -n` auf allen drei geänderten Skripten, `opencode.json` valides JSON.

- 2026-09-26: **glm2api war im echten Betrieb kaputt: ein Tool-Call endete je nach Zerschnittenheit des Upstream-Texts als `stop` oder als `error` — und die Abschluss-Warnung dokumentierte das Gegenteil des Messwerts.** Anlass war die Übergabe aus der Debug-Session (`/workspaces/cline/handoff.md`), die „718 Tests grün" meldete; gemessen waren **716 + 2 rot**, und `git bisect` über `c8135d9..HEAD` traf den S-09-Commit `4af494e` selbst als ersten schlechten. **Befund 1:** der neue Narration-Holdback fraß auch das Werkzeug-Protokoll (`tool_calls` stand in seinem Auslöser-Muster), der Parser sah den Aufruf erst im `finalize`, und die Einstufung „unbrauchbarer Aufruf" (T-06) war da schon entschieden — `{"tool_calls":[{"name":"read","arguments":{}}]}` endete als leere, erfolgreiche Antwort (`stop`) statt als `error`. **Befund 2 (älter, schwerer):** die Abschluss-Einstufung stützte sich auf `dropped_call_count`, und der Zähler zählt *Teil-Parse-Versuche*, nicht unbrauchbare Aufrufe — er hängt an der Zerschnittenheit (gemessen: derselbe gesperrte Aufruf ergibt Chunk 100 → 1, Chunk 3 → 4, Chunk 1 → 0). Folge: ein **gesperrter** Aufruf, der über mehrere Deltas kam, endete in 9 von 15 Chunk-Größen und in **beiden** Abschluss-Pfaden als `error` — also als vermeintlicher Stream-Fehler, den der echte Client mit 5-Minuten-Backoff endlos wiederholt (der Fall, für den `c8135d9` den `stop` eingeführt hatte). Entscheidend ist, dass der Upstream-ChatGLM-Text live in **4–8-Zeichen-Teilen** ankommt; die Fehlerklasse ist im Normalbetrieb also der Regelfall, nicht die Ausnahme. **Fix:** Markup wird vor dem Narration-Muster ausgeschlossen (`contains_tool_markup`), und entschieden wird am **Text** des Turns statt am Parser-Zustand (`_text_attempted_tools`): erlaubter Name → `error`, nur gesperrte Namen → `stop`, kein Name lesbar (abgeschnitten) → `error`, kein Protokoll im Text → alte Rechnung über `_policy_dropped_call_count`. **Zweiter Fund im selben Durchgang, Betriebskonfiguration:** vier Keys in allen drei ausgelieferten `.env`-Dateien wirkten nicht (`GLM_REFRESH_TOKENS`, `GLM_QUEUE_WAIT_TIMEOUT`, `REQUEST_TIMEOUT`, `REQUEST_SOCKET_TIMEOUT` — die letzten beiden wurden nicht einmal gemeldet und hatten exakt den Standardwert), und sechs Keys standen doppelt. `parse_dotenv` ließ still den letzten Eintrag gewinnen; beim Korrigieren entstand dadurch in der echten `.env` eine leere zweite `GLM_REFRESH_TOKEN=`, die den echten Token verdrängte — **der Dienst startete nicht mehr** („kein ChatGLM-Konto konfiguriert"), bei intakter Datei. Dublette werden jetzt mit Zeilennummern gemeldet (ohne den Wert zu nennen, das hätte den Refresh-Token ins Log geschrieben), die vier Tot-Keys sind aus allen drei Dateien raus und über `_CONFIG_KEY_KNOWN_TYPOS` jetzt *laut* statt still. Verifiziert: **788 Tests grün** (70 neue in `test_translator.py`, 11 in `test_config.py`), Gegenprobe gegen den Vorher-Stand — 20 neue Tests schlagen gegen `4af494e~1` fehl, 12 gegen `4af494e` — und live gegen den echten Proxy: Neustart sauber (`health` ok, keine `IGNORED`-/Dublett-Warnung), Textantwort `stop`, Tool-Aufruf non-stream **und** stream mit `finish_reason: tool_calls` und `read {"filePath":"/etc/hostname"}`. Ein Live-Lauf endete mit `error`, weil das Modell sein eigenes Protokoll abgeschnitten hat (Roh-SSE `{"tool_calls":[{"name":"read","arguments":{"filePath`) — Modellverhalten, korrekt eingestuft. Doku in `llm-proxies/glm2api/optimierung.md` THEMA 8 (S-08/S-09/Nachtrag) und THEMA 9.
- 2026-09-26: **`infra/scripts/glm2api.sh` ohne `setsid` — der Proxy bekam SIGTERM mitten im Stream, wenn ein Agent-Tool-Call in den Timeout lief.** Der Server blieb in der Prozessgruppe des aufrufenden Shells; lief ein Tool-Call in den Timeout, wurde er mitten in der Antwort beendet. Zweimal gemessen (17:47:15 und 19:25:19), jeweils Session abgerissen. **Das erklärt die hängengebliebenen ChatGLM-Conversations:** das Löschen sitzt im `finally` des Request-Handlers und lief nicht mehr mit — auf chatglm.cn blieben tote Gesprächshüllen zurück. `start-glm2api.sh` (Watchdog-Pfad) machte es seit jeher richtig, die zwei Startwege waren nicht gleichwertig. Fix: `setsid bash -c 'echo $$ > PID.tmp; exec python main.py' & disown` — `setsid` liefert kein `$!`, deshalb schreibt das `bash -c` seine **eigene** PID in eine Temp-Datei, die dann umbenannt wird; dazu **Adoption** eines bereits laufenden Servers, sonst starten `restart` und der `proxy-watchdog` beide. Verifiziert: `sid` des Servers == eigene PID, Tool-Call lief in den Timeout, Server lebte.

- 2026-09-26: **Freebuff CLI kommt fest in die Landschaft — Install + Login inklusive, mit zwei Fallen, die erst der Live-Test gezeigt hat.** Zuerst als reines `/workspaces`-Projekt gebaut (Nutzerwunsch: nicht global), nach Rückmeldung aber sauber ins Repo geholt, damit jeder neue Codespace es automatisch hat. `infra/scripts/freebuff-install.sh` (Pin **0.0.204**), `setup.sh` ruft es **nach** dem Secrets-Schritt, Login (`~/.config/manicode/credentials.json`) wandert über `secrets.sh` in `config/secrets.enc` — Muster exakt wie `rclone.conf`. Damit `secrets.sh lock` nicht versehentlich ein Secret verliert, sind **vor** dem Neuverschlüsseln alle 9 bisherigen Bundle-Einträge auf Existenz geprüft (alle OK).
  - **Falle 1 — npm-Pin ist nicht die Binary-Version:** `npm view freebuff version` stand bei 0.0.203, der Launcher zog beim selben Start **0.0.204** (`frebuff-metadata.json` + `.freebuff-0.0.204-linux-x64.tar.gz.part` in `~/.config/manicode`). Der Launcher lädt selbstständig das *neueste* native Binary, unabhängig von der npm-Pin, ohne jeden Env-Override (im `launcher.js` gibt es nur PostHog-/App-URL-Variablen). Konsequenz: Pin auf 0.0.204 angeglichen und die `.part`-/`-download-temp`-Reste eingeräumt, die sonst bei **jedem** Start ~30 MB in den ephemeren `$HOME` schreiben. Die Pin ist damit für den Launcher belastbar, für das Binary nicht — ein Upstream-Release kommt mit dem nächsten Build durch. Steht so in der Doku, damit das später niemand überrascht.
  - **Falle 2 — `rm -rf ~/.config/manicode` löscht den Login mit:** Der Testlauf „Rebuild simulieren" hat dabei den gerade erst erzeugten `credentials.json` mitgerissen (erst danach fiel mir auf, dass dort auch der Token liegt, den `secrets.sh` sichern soll). Der Token war danach nicht mehr rekonstruierbar — die API-Probe mit dem alten Wert lieferte 401, also: einmal neu einloggen, *dann* locken. Reihenfolge ist jetzt im Skript festgehalten (Login-Check am Ende, mit Hinweis auf `login` + `secrets.sh lock`).
  - **Gemessen:** frische Installation aus dem Repo-Skript **12-24 s** (1-3 s npm + 136-MB-Binary, netzabhängig; vier Läufe: 12,3 / 12,6 / 16,3 / 23,6 s). Der Login-Roundtrip über das Bundle wurde verifiziert: `credentials.json` gelöscht → `secrets.sh unlock` → Restore **byte-identisch** (360 B, 0600), alle 8 anderen Bundle-Secrets unverändert vorhanden.
  - **Korrigiert nach dem ersten Commit (Nutzerwunsch: „unter MAIN wie opencode"):** der erste Stand legte das npm-Projekt nach `/workspaces/freebuff` und cachte das Binary zwischen `/workspaces` und `$HOME` hin und her (Rebuild-Restore 3,3 s statt Download). Das war persistent, aber ein fremdes Zuständigkeitsmodell im Repo — opencode ist ephemer in `$HOME` und wird bei jedem Codespace neu gebaut. Jetzt identisch zu opencode: `$HOME/.local/share/freebuff` + Wrapper `~/.local/bin/freebuff`, **kein** `/workspaces`-Pfad und kein Cache mehr. **Der Gewinn des Caches ist damit weg — bewusst gegen diesen Preis:** jeder neue Codespace lädt 136 MB neu (12-24 s, läuft in setup.sh). Ein Zwischending aus beiden Welten (npm-Manifest im Repo, `node_modules` ephemer) wäre möglich, brächte aber einen zweiten Zustandspfad ohne Nutzen.
  - **Nebenbefund:** `/workspaces/fb-probe` (32 KB) lag als Rest eines Testlaufs mit gesetzter `FREEBUFF_CONFIG_DIR` herum — nur ein WARN-Log (`No auth token available`) plus anonyme Analytics-ID, keine Credentials. Gelöscht. Lehre: das native Binary kennt `FREEBUFF_CONFIG_DIR`, der npm-Launcher **nicht** — beide auf verschiedene Pfade zu setzen erzeugt genau solche „ausgeloggt"-Symptome, ohne Fehlermeldung.
  - **Mausrad-FiX, zweite Runde (das war nicht die ganze Wahrheit):** Die erste Keybinding-Mappt `mousewheel` auf **ein** PageUp/PageDown — und der Nutzer meldet zu Recht „scrollt nur den Chat, im Chatbereich, 10 Zeilen". Ursache im Binary, Chat-Screen-Handler woertlich: `case"pageup":J.current?.scrollBy(-10)` bzw. `scrollBy(10)` fuer down, dazu `home`/`end` als Sprung an Anfang/Ende — und am Ende `a.preventDefault?.()`. **Dieses `preventDefault` ist der ganze Befund:** es unterdrueckt opentuis eigenen ScrollBox-Handler, der `pageup` auf `scrollBy(-0.5,"viewport")` mappen wuerde. Ein Tastendruck scrollt in freebuff also hart begrenzt auf 10 Zeilen, und **eine Taste fuer einen Bildschirmsprung existiert nicht** — kein `ctrl+pageup` (der Component bails bei ctrl/meta/option per `return`, und der Root-Handler ueberspringt es ueber `xz=(H)=>Boolean(H.ctrl||H.meta||H.option)`), kein `shift+pageup` (feuert beide Handler, also 10 Zeilen plus Root-Scroll), `home`/`end` sind Spruenge. opencode kann es, weil es die Tasten selbst mappt (`tui.json`: `messages_page_up: pageup`) — das ist der Unterschied, nicht die Terminalseite. Loesung ohne Eingriff in die App: die Keybinding sendet **dreimal** die Sequenz (`\e[5~` x3 hoch, `\e[6~` x3 runter), ~30 Zeilen pro Rasterung, das entspricht einer Bildschirmseite. **Ehrlich als Magic Number markiert** (im Abschnitt „Maus, Copy/Paste & Scrollen in TUIs" und hier), weil sie an freebuffs Schrittweite hängt: ändert freebuff `scrollBy(-10)`, muss die 3 nachgezogen werden. Der zweite Teil der Nutzerbeobachtung ist keine Fehlfunktion: die Nachrichtenliste ist der einzige scrollbare Bereich, eine Ebene darüber existiert nicht — bei opencode ist es dieselbe Liste, nur mit voller Seite als Schritt. **Methodisch bemerkenswert:** die erste Fassung stützte sich auf die Doku-Behauptung, xterm.js übersetze das Rad in up/down, statt den tatsächlichen Handler zu lesen. Der Handler war in drei Klicks im Bundle auffindbar (`case"pageup":J.current?.scrollBy(-10)`), die Behauptung war falsch. Bei TUI-Innenleben ist der Binary-Code die Quelle, nicht die Terminal-Erwartung.
  - **Vierte Runde, und damit die Ursache statt des Symptoms: der Output-Bereich ist nicht „nicht scrollbar", er ist EINGEKAPPT und nur per Klick aufklappbar.** Die Navigation durch den minifizierten Bundle hat die Komponente `LAH` zutage geforscht, und die macht drei Dinge klar: `LAH=({command,output,expandable$=!0,maxVisibleLines:L,isRunning,…})` — `J=L??($?5:10)` heisst **5 Zeilen** collapsed bzw. **10** bei nicht aufklappbarem Block; der Aufklapp-Trigger ist `K(yA,{onClick:M,…})`, also ein **Maus-Klick**; und in der ganzen Komponente kommt `useKey`, `focusable` und `handleKeyPress` **null Mal** vor. Die App fuehrt laut Bundle genau vier Tasten-Actions ueberhaupt: `toggle-agent-mode`, `toggle-all`, `toggle-dock-panel`, `toggle-sponsored-dock` — **kein `expand`, kein `collapse`, kein `scroll-block`**. `LAH` wird an genau zwei Stellen benutzt: abgeschlossenes Kommando mit `expandable:!0, maxVisibleLines:5`, laufendes Kommando (`pending-bash`) mit `expandable:!1, maxVisibleLines:10`. **Damit ist der pty-Filter nicht die Ursache des Problems, sondern sein Ausloeser**: er entfernt genau den Klick, mit dem der Block aufklappbar waere. **Und damit ist die Grundsatzfrage beantwortet, die ich vorher falsch gestellt hatte:** 1:1-Uebertragbarkeit von opencode gibt es nicht, weil die Apps gegenlaeufig gebaut sind — opencode ist **tastatur-first** (`tui.json` bindet jede Aktion, deshalb funktioniert `mouse: false` dort), freebuff ist **maus-first** (seine eigenen Tips: „Drag to select text — it copies automatically (or click on a message)"). **Entscheidung des Nutzers: Maus aus, „genau wie opencode".** Der Default bleibt damit der pty-Filter, und der Preis wird nicht wegoptimiert, sondern benannt und mit freebuff-eigenen Mitteln entschaerft: `/copy` (Alias `copy-chat`) legt den **ganzen** Chat inkl. vollstaendigem Output in die Zwischenablage, `/export` (Alias `export-chat`, mit Zielargument) schreibt ihn als Datei — beides im Bundle als Slash-Commands verifiziert. Als Bonus-Loesung fand sich `wrapMode:"word"` + `maxVisibleLines`: der Cap zaehlt **umgebrochene** Zeilen, ein breiteres Terminal zeigt also im selben 5-Zeilen-Fenster mehr Text — die billigste Entlastung ueberhaupt. **Konsequenz fuer die Doku-Regel:** Bevor man am Terminal-Layer dreht, gehoert der UI-Aufbau der App gelesen — zwei FehlDiagnosen in dieser Session (Doku-Behauptung statt Bundle, Step-Groesse statt Region) waeren durch ein `LAH`-Lesen in einer Minute vermeidbar gewesen.
  - **Mausrad-FiX, dritte Runde — und die ehrliche Aufloesung: es geht nicht beides.** Die Keybinding-Mappt das Rad auf PageUp/PageDown; der Nutzer meldet danach korrekt: „scrollt das Chatfenster, nicht den Output-Block". Der Output-Block ist der Kommando-Output **innerhalb** einer Nachricht, und genau da liegt eine Eigenschaft, die ich erst jetzt belegt habe: **Er hat eine eigene Scrollbar** (`verticalScrollbarOptions.visible`, `trackOptions.width:1`, berechnetes `isScrollable` ab einer Hoehenkappe) — er ist also ein eigenstaendiger scrollbarer Bereich. Der Screen-Handler kann ihn trotzdem nicht erreichen: er behandelt `pageup`/`pagedown` und ruft danach `preventDefault`, wodurch opentuis `handleKeyPress` (das `pageup` auf **0,5 Viewport** mappen wuerde) fuer **kein** Kind mehr ausgefuehrt wird. Der zweite Hebel — Fokus — existiert ebenfalls nicht: `focusable` setzt freebuff **nirgends** (alle 17 Bundle-Treffer sind opentuis Basisklasse), `onMouseWheel` kommt **null Mal** vor, und es gibt keine Tab-Fokus-Zyklen (`Tab` oeffnet die Datei-/Slash-/Mention-Menues, `Esc` macht `unfocus-agent` fuer Agenten, nicht fuer Scrollboxen). **Folge: Der Block ist ausschliesslich mit der Maus scrollbar — und die Maus ist genau der Kanal, an dem die native Textauswahl haengt. Es ist ein echtes Entweder-oder**, kein Rezeptfehler: Maus an ⇒ Rad scrollt Blöcke, aber keine Terminal-Auswahl (freebuff kopiert dann selbst, „Drag to select text — it copies automatically"); Maus aus ⇒ Copy/Paste wie opencode, aber der Block steht still. opencode entkommt dem Dilemma, weil `tui.json` jede Scroll-Aktion an Tasten bindet — genau das fehlt freebuff 0.0.204. Statt weiter an der Keybinding zu drehen, ist der dokumentierte Ausweg der bereits vorhandene Bypass im Wrapper: `FREEBUFF_NO_PTY_FILTER=1 freebuff` (Maus an) vs. `freebuff` (Default, Maus aus). **Methodisch, als dritte Lektion festgehalten:** Ich hatte zweimal auf die Doku- bzw. Terminal-Erwartung gebaut statt auf den Bundle-Code, und einmal die Nutzer-Rückmeldung als „Step-Groesse" gelesen, obwohl sie eine **andere Region** meinte. Bei TUI-Innenleben gilt: erst Census (`XH("scrollbox")`-Vorkommen zählen, `focusable`/`onMouseWheel` suchen), dann bauen — und wenn die App die Fähigkeit nicht hat, laut sagen statt sie zu simulieren.
  - **Mausrad-FiX (Nachtrag):** Copy/Paste fixt und das Mausrad ist tot — die andere Hälfte derselben Münze. Die alte Doku behauptete, xterm.js übersetze das Rad in `up`/`down`; das stimmt nicht, und die Erklärung lief in die falsche Richtung: **nach `mouse: false` bzw. nach dem pty-Filter ist das Mausrad ein Terminal-Scrollback-Ereignis — und Terminal-Scrollback ist im Alternate Screen unsichtbar.** opencode rendert im normalen Buffer, deshalb war dort nie etwas kaputt; Freebuff schaltet `CSI ? 1049 h` (live aus der Aufzeichnung) und hat damit keinen Scrollback. Die App kann aber nichts dagegen tun, dass das Rad ankommt — sie **bindet** die passenden Tasten ohnehin (`case"pageup": scrollBy(-0.5,"viewport")`, `case"pagedown": scrollBy(0.5,"viewport")`, Key-Parser mappt `\e[5~`/`\e[6~`). Der einzige Hebel ist deshalb eine **VS-Code-Keybinding**: neues `.vscode/keybindings.json` mappt `mousewheel up`/`down` per `workbench.action.terminal.sendSequence` auf genau diese zwei Sequenzen, `when: terminalFocus`. Anwendungsneutral (gilt auch für `less`/`vim`/`man`/`htop`) und in VS Code ohne Neustart wirksam. Gegengeprüft, dass der pty-Filter die Tasten nicht beschädigt: `\e[5~`/`\e[6~` passieren ihn unverändert (sein Regex verlangt `\e[?` + Ziffern + `h`/`l`), im selben Durchlauf verschwinden `\e[?1003h`/`\e[?1000h`. **Bewusster Trade-off, im neuen Abschnitt „Maus, Copy/Paste & Scrollen in TUIs" dokumentiert:** das Rad scrollt jetzt Tastenseiten statt Terminal-Scrollback, bei opencode also eine Nachrichtenseite statt drei Zeilen; wer das nicht will, löscht die zwei Einträge in der Keybinding-Datei. Der Abschnitt ist als eigene Übersetzung geschrieben, weil das Problem in zwei Apps steckt und die Reihenfolge nicht umkehrbar ist: `mouse: true` ⇒ Copy/Paste weg, pty-Filter weg ⇒ Copy/Paste weg, und die Keybinding allein ersetzt den abgeschalteten Scrollback-Mechanismus nicht.
  - **Copy/Paste-Fix (Nachtrag derselben Sitzung):** „ich kann nichts markieren und kopieren" — dieselbe Klasse wie bei opencode, dort per `mouse: false` in `.opencode/tui.json` gelöst. Für Freebuff existiert dieser Kniff **nicht** (settings.json-Reader akzeptiert nur `mode`/`adsEnabled`/`freebuffModel`; keine CLI-Flags, keine Env-Variablen; opentui's `useMouse` wird nicht gesetzt). Daher der äußere Eingriff: `infra/scripts/freebuff-pty.py` startet das TUI auf einem pty und entfernt aus dem Output ausschließlich `CSI ? 1000|1001|1002|1003|1005|1006|1015|1016 (h|l)`. **Bewusst nicht entfernt:** `?2004` (bracketed Paste — sonst wäre Pasten kaputt), `?1004`, `?1049`, Kitty-Keys. Bidirektional-Relay, SIGWINCH-Durchreichung und Exit-Code sind implementiert und getestet (Kind liest eine Zeile, Exit 42 kommt durch), Fenstergröße wird beim Start und bei Resize gesetzt. **Beleg statt Behauptung:** TUI-Aufzeichnung mit leerem Config-Dir (damit keine Session-Slot verbraucht wird) — mit Filter null Maus-Modi im Stream, ohne Filter `?1000h ?1002h ?1003h ?1006h`, TUI rendert in beiden Fällen. Damit ist zusätzlich ausgeschlossen, dass das Entfernen der Sequenzen das TUI blockiert (es wartet an keiner Stelle auf Mausereignisse). Der Wrapper wird bei **jedem** `setup.sh`-Lauf neu erzeugt, damit der Repo-Pfad nicht driftet — deshalb wandert `write_wrapper` auch in den Idempotenz-Pfad (vorher wäre der Wrapper nach einem Repo-Umzug still veraltet geblieben). **Für den Nutzer heißt das: laufende Freebuff-Session einmal beenden und neu starten**, der Filter hängt am Startpfad.
  - **Bewusst nicht gebaut:** ein API-Provider für opencode. Es gibt keinen OpenAI-kompatiblen Endpoint, kein Headless-Modus (einziges CLI-Kommando ist `login`) — die interne `codebuff.com/api/v1/freebuff/session`-Admission nachzubauen wäre ein Shim gegen das werbefinanzierte Geschäftsmodell, kein Weg. Für gratis-Modelle in opencode bleiben die BYOK-Pools.

- 2026-09-26: **`nvidia-models.py` und `cline-models.py` zu `free-models.py` zusammengeführt — eine Datei, ein Aufruf, `fetch_models()`, 14-Tage-Filter für beide Anbieter.** Zwei Skripte mit demselben Zweck und sehr unterschiedlichem Reifegrad: zwei Caches, zwei Ausgabeformate, zwei Sortierungen — und die Antwort auf „welches kostenlose Modell ist neu" musste je nach Anbieter anders zusammengesucht werden. Zentrale Funktion ist `fetch_models(providers, args, now)`, die für beide Anbieter dieselbe normalisierte Zeilenform liefert (`provider`, `id`, `ts`, `age`, `free`, `desc`, `date_src` plus Anbieter-Extras). **Was bewusst nicht vereinheitlicht wurde, ist der Abruf:** Cline ist eine JSON-API, NVIDIA nur HTML-Scraping über `build.nvidia.com` (`models.md` + `nimType`-Attribute, mit `updated` als einziger belastbarer Datumsquelle, weil die integrate-API nur ein Dummy-`created` liefert). Beides in eine Funktion zu zwingen hieße, den billigen JSON-Abruf mit dem teuren Scraping zu verheiraten und die zwei Caches in einen mit einer TTL zusammenzuziehen, die keinem der beiden gerecht wird — sie sind deshalb getrennt geblieben (NVIDIA-Modellseiten 24 h, Cline-Probes 1 h, `first_seen` ungekürzt), inklusive kompatiblem Format, sodass die vorhandenen Caches weiterverwendet werden. **NVIDIA bekam die Cline-Regeln:** Default nur kostenlose Modelle der letzten 14 Tage, neueste zuerst. Bei NVIDIA ist das nicht nur Kosmetik — der Index führt 97 Modelle, davon nur 8 im 14-Tage-Fenster, also blendet der Filter 89 durchwegs als Dauerbestand erkennbare Einträge aus. Das Alter kommt dort aus `updated` und ist damit ein echtes Datum, nicht wie bei Cline eine Beobachtung. Aliase zeigen alle auf das eine Skript (`free-models`, `cline-models` = nur Cline, `nvidia-models` = nur NVIDIA). **Zwei Fehler beim Zusammenführen gefunden, beide beim Testen:** (a) `--api` war im neuen Skript ein stiller No-op — `nv_api_ids()` war definiert, wurde aber nirgends aufgerufen, das Flag tat also nichts, ohne zu warnen; jetzt füllt es ein `live`-Feld, das die Spalte nur dann einblendet, wenn es belastbar ermittelt wurde (kein Key oder Netzfehler → Spalte weg statt einer Behauptung). (b) Beim Nachtragen fiel die **Lücke auf, die der Doku-Index von NVIDIA verdeckt: von 41 als free markierten Modellen sind live nur 7 abrufbar, 34 stehen ausschließlich in der Dokumentation.** Das `Free Endpoint`-Flag sagt also nichts darüber aus, ob ein Modell wirklich rufbar ist. `--api` bleibt opt-in, um die Standardausgabe nicht zu überladen — wer ein NVIDIA-Modell tatsächlich nutzen will, sollte es mit `--api` prüfen. Verifiziert: `free-models` 103 geladen / 10 passend (Cline 2, NVIDIA 8), `cline --all` 6/6 mit vollen Spalten, `--days 5` und `--days 8` korrekt, `--emit-config` unverändert, `--api` mit belastbarer `live`-Spalte und korrektem „kein API", alle drei Aliase, `bash -n` auf aliases.sh, beide Caches formatkompatibel wiederverwendet.

- 2026-09-26: **`cline-models.py` auf den tatsächlichen Zweck zugeschnitten: nur was in opencode nutzbar ist, nur was höchstens 7 Tage alt ist.** Der ausführliche Modus hatte den Zweck, die Verfügbarkeitsfrage zu klären — einmal geklärt war sie beantwortet, und die 4 `cline-free/*`-Zeilen waren nur noch Rauschen: Sie sind für opencode per Definition irrelevant (403, unabhängig von Key und von jedem Eintrag in `opencode.json`), also nicht „nicht konfigurierbar, wenn man es richtig macht", sondern generell unbrauchbar. Neuer Default filtert deshalb auf **nutzbar** *und* **≤ `--days` (7)**, und die Ausgabe wird entsprechend schlank: Status- und Cost-Spalte entfallen im Default-Modus, weil sie dort in jeder Zeile „ok" bzw. „0" gesagt hätten — stattdessen kommt `ctx` dazu (aus dem Katalog, `1000k` für space-bunny-alpha), das tatsächlich variiert. Mit `--all` kommen beide Spalten zurück, wo sie echte Information tragen. Der Probe selbst wurde leichter: kürzerer Prompt („Read /etc/hostname."), weil er ohnehin nur beweisen soll, dass das Modell antwortet, Tools aufruft und nichts kostet — gegengeprüft, dass der kurze Prompt weiterhin Tool-Calls auslöst (pixel-canary und space-bunny-alpha, beide `tool=True cost=0`), sonst wäre die Spalte `tool ok` eine Lüge. **Zwei Fehler beim Umbauen, beide beim Testen aufgefallen und gefixt:** (a) `--days 0` ließ `max_age` auf `None` und crashte die Zusammenfassungszeile mit `TypeError: unsupported format string passed to NoneType.__format__`; (b) **`--emit-config` benutzte die bereits gefilterte Menge** — ein nutzbares, aber älteres Modell wäre dadurch nie mehr zum Konfigurieren vorgeschlagen worden, obwohl es in opencode weiterhin nutzbar ist. Der Altersfilter ist jetzt eine reine Lesehilfe, `--emit-config` rechnet auf dem Stand davor (mit `--days 1` geprüft: die Ausgabe zeigt nur ein Modell, das Snippet enthält weiterhin beide). Verifiziert: Default 0,5 s aus dem Cache, 16 s kalt; `--all` 6/6 mit Status- und Cost-Spalte; `--days 0/1/2` korrekt; `--no-probe` ohne Key; `--emit-config` gegen leere und gefüllte Whitelist (Config danach byte-identisch wiederhergestellt).

- 2026-09-26: **`cline-models.py` um ein belastbares Modell-Alter erweitert — und dabei zwei echte Fehler gefunden, die das Alter selbst betrafen.** Anlass war die Frage „seit wann sind die Modelle da", um daran filtern zu können. **Die Datenlage ist schlechter als erwartet und musste erst geklärt werden:** Cline führt für 5 der 6 Free-Modelle **kein** `created`. Der `free`-Block der `recommended-models` liefert nur `id`/`name`/`desc`, und die `cline-free/*` stehen in *keinem* der beiden Kataloge (`/v1/models` und das reichere `ai/cline/models`) — von den 6 ist dort nur `stealth/space-bunny-alpha` aufgeführt, immerhin mit `created=2026-09-23`, `context_length=1000000` und `pricing: {prompt: "0", completion: "0"}`, also ein herstellerseitiger Beleg für die Null-Preis-Position, unabhängig von der Messung. Für die übrigen 5 lässt sich kein Datum aus Cline holen, also führt das Skript jetzt eine eigene `first_seen`-Registry. Die Registry **altert absichtlich nicht** (die Probes dagegen 1 h) und überlebt das Verschwinden eines Modells: sonst wäre die Angabe genau dann wertlos, wenn man sie braucht. In der Ausgabe steht die Quelle mit: `Cline` = herstellerseitig belegt, `erstmals` = von uns beim ersten Lauf notiert, also „seit wann wir es kennen", nicht „seit wann es existiert" — diese Unterscheidung steht auch in der Doku, weil sie sonst wie ein Erstellungsdatum gelesen wird. Dazu `--min-age TAGE` / `--max-age TAGE`, Sortierung neueste-zuerst wie in `nvidia-models.py`. **Fehler 1, direkt beim Bauen aufgefallen:** `pixel-canary` fiel mit `http_500` durch, und es lag nicht am Modell. Derselbe Fall wie beim `keys.sh`-Probe-Fehler von gestern, nur eine Stufe härter: mit Tool-Spec braucht das Reasoning-Budget **512+** Tokens, bei 256 antwortet Cline `HTTP 500 inference request failed: failed to invoke model 'stealth/pixel-canary'` (gemessen 256 → 500, 512 → 200, 1024 → 200). Ein fester Wert allein wäre bei der nächsten unbekannten Reasoning-Länge wieder zu knapp, deshalb Grundwert 1024 und **einmalige** Eskalation auf 2048, aber ausschließlich bei genau diesen zwei Fehlerbildern (`empty response content`, `inference request failed`) — 403/401/Netz werden nicht erneut versucht. **Fehler 2, beim Testen des Alters aufgefallen:** `first_seen` wurde im `--no-probe`-Zweig nie aus dem Cache geladen, das anschließende `setdefault` setzte daher jedes Alter auf 0. Ein `--min-age 1` hätte dann 5 Modelle als „alt genug" ausgeblendet, mit einer Meldung, die das Gegenteil der Wahrheit behauptet — ein Filter, der im `--no-probe`-Modus alles verschluckt. Die Registry wird jetzt unabhängig von Probe und Key geladen, und der Guard, den ich dafür zuerst geschrieben hatte, war toter Code und ist raus. Verifiziert: Alter aufsummiert (Registry testweise auf 1/3/9 Tage zurückdatiert — Ausgabe und beide Filter korrekt, danach die Testmanipulation verworfen, damit das Skript das echte Erstlauf-Datum erfasst), `--no-probe` lädt die Registry, `--no-cache` schreibt weiterhin nicht, pixel-canary wieder `nutzbar / cost=0`, Probe-Pfade 0,4 s bzw. 8,5 s. **Unabhängig davon, nicht von mir:** in `llm-proxies/glm2api/src/glm2api/services/translator.py` arbeitet eine parallele opencode-Session (S-09-Marker im Diff). `validate-revision.sh` meldete 419/421, die zwei Fehlschläge (`test_turn_with_only_unusable_calls…`, `test_blocked_only_turn_ends_cleanly…`) liegen in `test_translator.py` und schlagen **auch gegen HEAD fehl** — die S-09-Arbeit behebt sie. Beim Zuschreiben der Ursache habe ich die Datei einmal auf HEAD zurückgesetzt und danach aus einer Sicherung restauriert; die 106-Zeilen-Version liegt ohnehin in `4af494e`, es ist also nichts verloren, und die Datei wird von hier nicht mehr angefasst oder mitcommittet.

- 2026-09-26: **`infra/scripts/cline-models.py` (neu) — Cline-Free-Modelle live geprüft — und die gelben Python-Warndreiecke in der VS-Code-Terminalanzeige beseitigt.** Zwei getrennte Anlässe. **(a) Modell-Discovery:** Cline rotiert seine Free-Modelle, und die Unterscheidung, was davon in opencode überhaupt nutzbar ist, lässt sich aus keiner Doku ableiten, weil sie selbst widersprüchlich ist — der `/v1/models`-Katalog listet `:free`-Modelle mit, die als Free-Artikel erscheinen, sind aber OpenRouter-Passthrough-Modelle und nicht dieselben wie die Cline-`cline-free/*`-Serie. Das neue Skript holt den `free`-Block aus `GET /api/v1/ai/cline/recommended-models` (das ist die Quelle, aus der sich auch der Picker in der Cline-CLI speist) und prüft jedes Modell per echtem POST gegen `chat/completions`: API-erreichbar, Tool-Call-Funktionsfähigkeit, tatsächliche Kosten über `usage.cost`. Ergebnis dieser Trennung, und deshalb der eigentliche Wert des Skripts: **`stealth/*` funktioniert über die API, `cline-free/*` nicht** (HTTP 403 `only available via Cline product surfaces`, also IDE/CLI-only). Aktuell 2 von 6 nutzbar, beide $0 — genau die zwei, die in der `whitelist` stehen. Kein eigenes `nvidia-models.py`-Pendant wäre auch nicht sinnvoll gewesen: dort ist der Index HTML-Scraping über `build.nvidia.com` (`models.md` + `nimType`-Attribute), hier eine JSON-API — zwei Abrufwege in einer Funktion erzwingen wäre der falsche Schnitt, deshalb ein eigenes Skript mit eigenem Cache (`~/.cache/cline-models-cache.json`, 1 h für die Probes; die Modellliste wird bewusst *immer* frisch geholt, weil ein 24-h-Cache neue Free-Modelle tagelang unterschlüge). Zusätzlich: Abgleich mit der Whitelist aus `opencode.json` (`cfg ja/nein`), `--emit-config` für ein direkt einfügbares Snippet, und ein Guard, der `--emit-config` mit `--no-probe` ablehnt — ohne Probe ist nicht feststellbar, welche Modelle nutzbar sind, und der Aufruf meldete dann fälschlich „alles konfiguriert". Aliase `cline-models` und `nvidia-models` (letzterer bislang ohne Alias, obwohl das Skript existierte). Verifiziert: Live-Lauf 6/6 Modelle in 8,5 s, Cache-Lauf 0,4 s, `--no-probe` ohne Key lauffähig, `--emit-config` gegen leer und gegen gefüllte Whitelist (Config danach byte-identisch wiederhergestellt), `python` **und** `python3` laufen. **(b) Python-Warnung:** die gelben Warndreiecke in der bash-Anzeige unter Codespaces hatten zwei Ursachen, beide davon unabhängig vom opencode-Setup. Es gab **kein `python`-Binary** — nur `python3` — also scheiterte jedes Tooling, das bare `python` aufruft, mit `command not found`; und im Repo-Root liegt **kein venv**, der Python-Extension fehlte damit ein auswählbarer Interpreter. Fix: `python-is-python3` in die apt-Zeile von `setup.sh` (legt `/usr/bin/python` an) und `python.defaultInterpreterPath: /usr/bin/python3` sowie `python.terminal.activateEnvironment: false` in `.vscode/settings.json`. Das Repo hat bewusst **kein** `pyproject.toml` im Root und alle Skripte nutzen `python3` — der System-Interpreter 3.12 ist damit der richtige Default, während das separate glm2api-venv (3.14, via uv) davon unberührt bleibt. Nebenbefund beim Nachtragen: `apt-get install` schlägt in einer laufenden Session fehl, weil `setup.sh` am Ende `rm -rf /var/lib/apt/lists/*` macht und die Paketlisten damit löscht — in einem frischen Codespace greift das `apt-get update` davor, die laufende Session brauchte ein manuelles `update`. Verifiziert: `python --version` → 3.12.3, `bash -n` auf setup.sh/aliases.sh, `.vscode/settings.json` valides JSON, 421 Tests grün.

- 2026-09-26: **Cline als opencode-Provider ergänzt — und zwei Fehlannahmen über Cline korrigiert.** Auslöser war die Frage nach kostenlosen Modellen. Der Cline-Key liegt jetzt als `~/.config/landscape/cline.key` und ist über `{file:...}` in `opencode.json` referenziert, also im secrets-Bundle (`secrets.sh lock|unlock`) und in `keys.sh status|doctor` mitgeschleift — die bestehende `referenced_files()`-Mechanik hätte die Datei ohnehin erkannt, der `KEYS`-Eintrag macht sie aber überhaupt erst prüfbar. **Befund 1: die Cline-`cline-free/*`-Modelle gehen *nicht* über die API.** Sie antworten `Error 403: <modell> is only available via Cline product surfaces` und sind damit auf IDE-Extension und Cline-CLI beschränkt — die offizielle Doku sagt das, sie ist nur an einer Stelle missverständlich formuliert, weil der `/v1/models`-Katalog `:free`-Modelle mit auflistet. Über die API funktionieren nur die `stealth/*`-Modelle, verifiziert mit Tool-Call und Kostenmessung: `stealth/pixel-canary` (cost 0) und `stealth/space-bunny-alpha` (cost 0). **Befund 2: `:free` und `cline-free/` sind verschiedene Familien.** Ein erster Versuch mit den `:free`-OpenRouter-Passthrough-Modellen war fachlich falsch — andere Modelle, andere Quellen, und `qwen/qwen3.8-27b:free`, `google/gemma-4-31b-it:free` sowie `thinkingmachines/inkling:free` lieferten gar keinen Request durch. Die `whitelist` enthält nur noch die zwei verifizierten `stealth/*`-Modelle; ein Bezug auf kostenpflichtige Modelle ist ausgeschlossen, damit der Provider nicht unbemerkt Credits abbucht. **Nebenbefund mit eigener Ursache: `keys.sh doctor` meldete den funktionierenden Cline-Key als tot.** Der Live-Probe fragte mit `max_tokens: 1`; Reasoning-Modelle schreiben zuerst ins Reasoning-Feld, das Budget war damit aufgebraucht, der Content blieb leer, und Cline antwortete `HTTP 500 empty response content`. Gemessen an pixel-canary: `max_tokens=1` → 500, `=16` → 500, `=200` → 200 (content 49, reasoning 105 Zeichen). Probe auf 256 erhöht, mit den Messwerten im Skript kommentiert — dieselbe Fehlerklasse wie der NIM-Kaltstart im Eintrag weiter unten, nur mit anderem Symptom. Verifiziert: Probe liefert HTTP 200, `bash -n` auf beiden Skripten ok, `secrets.sh status` listet `cline-key`, `opencode models cline` zeigt genau die zwei Modelle, `opencode.json` valides JSON.

- 2026-09-26: **Frischer Codespace verifiziert: 20/20 grün — und der Test fand zwei echte Lücken (Secrets repo-scoped, opencode nicht im PATH).** Erster echter Test der Kette auf einem leeren Container, ausgelöst durch die Frage nach einem Account-Bann. Voraussetzung war eine Hürde: **weder ambient Codespace-Token noch Bundle-PAT dürfen einen Codespace per API erzeugen** (403 bzw. 404) — Codespace-Erstellung geht nur über die Web-UI. Die Web-UI wiederum akzeptiert `ChatMCPConnector/MAIN` auch für einen Kollaborator mit Push (dieser Codespace ist so entstanden); ich hatte daraus zunächst zu pauschal "Repo muss geforkt sein" geschlossen, was der Beleg nicht trägt. Für den Test wurde deshalb ein kurzer Weg über einen Fork genommen, der Test lief auf einem Codespace aus `tadeuslol/MAIN` mit `./infra/scripts/verify-codespace.sh` (neu, 20 read-only Checks inkl. echter LLM-Calls auf beiden Proxys): **20 PASS, 0 FAIL** — Secrets entschlüsselt, opencode-Pin konsistent, Server auf 4096, glm2api *und* antigravity mit realer Antwort, alle drei Daemons, Firefox, beide Drive-Generationen, Testsuite grün. Zwei Befunde, die nur ein echter Container zeigen konnte: **(a) Codespaces-Secrets sind repo-scoped.** Im Fork-Codespace waren `LANDSCAPE_PAT` und `LANDSCAPE_PASSPHRASE` **beide leer**, weil ihr `visibility=selected` nur `ChatMCPConnector/MAIN` umfasst — auf dem Original-Repo kommen beide an (belegt: dieser Codespace hat sie injiziert bekommen). Genau deshalb wird ohne Fork gearbeitet: dort ist der Secret-Pfad von Haus aus aktiv. Unauffällig geblieben ist es nur, weil `auth.sh` über die Token-Datei aus dem Bundle pushen kann und `secrets.sh` über `config/passphrase` entschlüsselt — der Git-Auth-Pfad aus dem Secret fehlte trotzdem. Ein Fork würde deshalb zusätzlich erfordern, das Fork-Repo in den Secret-Scope nachtragen (UI; der `…/repositories`-PUT scheitert mit beiden verfügbaren Tokens) — Grund genug, ohne Fork zu arbeiten. **(b) `opencode` war installiert, aber nicht im PATH des interaktiven Terminals** (`command not found`), obwohl der Checker über `~/.opencode/bin/opencode` grün ging. Ursache: `setup.sh` exportiert sein PATH nur im eigenen Prozess und verlässt sich für interaktive Shells auf den Installer, der die rc-Zeile nicht garantiert schreibt. Fix: `setup.sh` ergänzt die Zeile jetzt selbst, idempotent über einen Marker (`# MAIN-landscape opencode-path`) in `.bashrc`/`.zshrc` — in isoliertem Test-HOME geprüft (wird genau einmal geschrieben). Damit ist der Ersteindruck im Terminal nicht mehr `command not found`, was den Nutzer sonst direkt zum manuellen Nachinstallieren verleitet.

- 2026-09-26: **`LANDSCAPE_PASSPHRASE` auf den echten Passphrasen-Wert gesetzt — per API, mit reproduzierbarem Skript.** Der Secret enthielt erneut den PAT (derselbe Fehler wie im Changelog-Eintrag vom 2026-09-26 weiter unten, zweite Wiederholung). Funktional war und ist es harmlos: `secrets.sh` verwirft PAT-Kandidaten und entschlüsselt über `config/passphrase` (40 B, im Repo) — beide Zustände liefern dieselbe Ausgabe, live gegengeprüft. Behoben wurde es trotzdem, weil ein falsches Secret Warnungen erzeugt und verschleiert, ob der Auto-Unlock über den ersten Kandidaten läuft. **Die Codespaces-Secrets sind per REST-API schreibbar** (`PUT /user/codespaces/secrets/{name}`) — im UI wäre das ein Copy-Paste mit unsichtbarem Newline-Risiko gewesen. GitHub erwartet libsodium-**Sealed-Box** (X25519, 32 rohe Bytes aus `GET …/public-key`); umgesetzt mit `nacl.public.SealedBox` über `uv run --with pynacl`, ohne dauerhafte Installation. **Drei Dinge, die dabei nicht funktioniert haben wie erwartet und die deshalb im Skript kommentiert stehen:** (a) `lsjson`-Kompakt-JSON — hier nicht relevant, aber dieselbe Klasse Fehler wie im gdrive-Fix; (b) **der Bundle-PAT darf `…/secrets/{name}/repositories` nicht** (live: `total_count: 0`, während public-key und list gehen) — der Script nimmt daher den ambienten Codespace-Token zuerst; (c) ein leerer Scope wird **nicht geraten**, sondern mit Fehler abgebrochen, weil der PUT sonst den Scope stillschweigend auf ein Repo zurücksetzt. Neubau der Chiffre vor dem PUT verifiziert (Selbsttest-Roundtrip mit eigenem Schlüssel, Chiffre 88 B = 40 + 48 Overhead). Neu: `infra/scripts/codespace-secret.sh` (Alias `csecret`) mit `list|set-passphrase|set NAME DATEI|delete NAME`; der Wert kommt immer aus `config/passphrase`, nie aus dem Kopf. Damit ist der Account-Wechsel in `infrastructure.md` als Befehlsfolge dokumentiert statt als Web-UI-Erinnerung. Verifiziert: `set-passphrase` lief live durch, `updated_at` aktualisiert, `visibility=selected` und Repo-Scope `ChatMCPConnector/MAIN` unverändert.

- 2026-09-26: **Drive-Backup meldete Erfolg, während `MAIN.bundle` auf Drive fehlte — und die „MD5-Verifikation" verifizierte nie etwas.** Beim Nachfassen des zweiten `save.sh`-Laufs fiel auf: `gdrive status` listete **kein `MAIN.bundle`**, nur `MAIN.backup.bundle` — das Skript hatte aber „OK: Drive-Stand = MAIN.bundle (verifiziert)" gemeldet. Rekonstruktion der Kausalkette über Zeitstempel, Drive-Hashes und Bundle-MD5s: Lauf 1 (17:02) ließ `moveto` **still** scheitern (stderr unterdrückt, kein Zustandscheck) und lud das frische Bundle als `current` hoch. Lauf 2 (17:18) löschte die Backup-Generation, verschob `current` → `backup` — **erfolgreich**, was der verwaiste Backup-Hash `0b557bf23dd4…` (= Bundle aus Lauf 1) belegt — meldete aber „noch kein vorhandenes current (Erst-Backup)", weil `moveto` trotz Erfolg nonzero lieferte. Der anschließende Upload **scheiterte**, und genau hier wurde es unsichtbar: `runc copy … | grep -v '^$'` gibt den Exitcode von `grep` zurück, die `||`-Fehlerbehandlung war toter Code. Die „Verifikation" prüfte dann nichts, weil `rclone lsjson` **ohne `--hash` kein Hash-Feld liefert** (remote_md5 leer) und der Vergleich `[ -n "$md5" ] && …` bei leerem Wert übersprungen wurde. Derselbe `lsjson`-Defekt im Skip-Check (`[]` mit Exit 0 = „Remote-Stand vorhanden") hätte den Zustand dauerhaft konserviert. **Drei Fehler, eine Ursache: Remote-Zustand wurde geglaubt statt geprüft.** Dazu kam, dass die alte Rotationsreihenfolge die Backup-Generation **vor** dem Move löschte — ein Move-Fehler hätte die letzte Kopie gekostet. Umbau: Upload als `MAIN.new.bundle` **vor** der Rotation, jede Mutation über den Zustand prüfen (Datei vorhanden? Größe? MD5?), `current` nach der Rotation fail-closed erneut prüfen, `status` nennt beide Generationen und warnt bei Fehlen, Skip verlangt **beide** Generationen, neu `backup --force` zur Reparatur. Drei eigene Fallstricke dabei (alle live nachgestellt und im Skript kommentiert): (a) `rclone copy <lokal> <nicht existierender Pfad>` legt ein **Verzeichnis** an (`MAIN.new.bundle/MAIN.bundle`) — Upload geht jetzt in `$REMOTE_DIR`; (b) Drive liefert den MD5 **asynchron**, die Prüfung muss die Größe als Primärnachweis nehmen und den Hash nur prüfen, **wenn** er da ist; (c) rclones Roh-JSON ist **kompakt** (`"IsDir":false`), ein Muster mit genau einem Leerzeichen lieferte ein Falsch-Negativ und meldete einen erfolgreichen Rename als Fehlschlag — alle Muster sind jetzt whitespace-tolerant. Zustand nach der Reparatur wieder 2 Generationen (je 116.636.960 Bytes, MD5 `cd378ce7f63f…` verifiziert), Restore-Test gefahren. **Lehre für die anderen Skripte:** `remote/prüfe-nicht-Exitcode` — überall dort, wo ein Fehlalarm teurer ist als eine zweite Anfrage.

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
