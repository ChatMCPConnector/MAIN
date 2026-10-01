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
| `.opencode/` | opencode-Config: opencode.json (Provider/MCP), tui.json |
| `config/` | secrets.enc (verschlüsseltes Bundle) + Manifest + passphrase (Klartext, bewusst) |
| `infra/` | **Werkzeugkasten:** `scripts/` (save/auth/secrets/ports/browser-*.sh, aliases.sh, config-watchdog.sh, verify-codespace.sh), `mcp/` (opencode-sessions MCP), `docs/` (Reverse-Engineering-Doku) |
| `llm-proxies/` | LLM-Proxies: **glm2api** (Port 8001, GLM-Haupt-Proxy) + **antigravity-proxy** (Port 9878, CloudCode OAuth) + **zerokey** (Port 7250, ChatGPT-Web) |

| `.env` `.runtime/` | GITIGNORED — Klartext-Secrets (.env), Browser-Profil, Runtime (nie committen) |

## Schnellstart

Codespace bauen → `setup.sh` stellt ALLES automatisch wieder her (Systempakete,
opencode, uv, Secrets-Unlock, Git-Auth, Freebuff-CLI, Browser-Runtime,
**glm2api-, antigravity- und zerokey-Proxy inkl. Start** — der Code liegt
komplett im Repo, es gibt nichts mehr zu klonen; nur `uv sync` (Python 3.14 +
Deps, beim ersten Mal ~2-5 Min) + `pnpm install` (ZeroKey, lädt einmalig
Playwright-Chromium) + Autostart). Danach:

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
- Freebuff CLI: kostenloser, werbefinanzierter Coding-Agent, gepinnt 0.0.204,
  liegt wie opencode ephemer in `$HOME/.local/share/freebuff` (Wrapper
  `freebuff` im PATH), Login verschlüsselt im Secret-Bundle → in jedem
  Codespace eingeloggt. `cd <projekt> && freebuff`.
  Kein API-Endpoint für opencode (kein OpenAI-kompatibler Server, kein
  Headless-Modus); werbefinanziert, Prompts werden zur Ad-Personalisierung
  ausgewertet → nichts Geheimes rein.
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
- XinJianYa-Keys in `opencode.json` referenzieren `{file:~/.config/landscape/<key>}` und kommen über das Bundle in jeden neuen Codespace. `glm2api` nutzt lokal `local` als Platzhalter. Zwei Literalwerte bleiben getrackt und stehen deshalb hier ausgeschrieben statt als Verweis auf einen gelöschten Audit: **TokenRouter** trägt einen echten `sk-…`-API-Key in `options.apiKey` (Provider wird nicht genutzt — die Whitelist enthält ein einziges `stealth/union-alpha`), **Antigravity** trägt den selbst erzeugten Admin-Key des lokalen Proxys (`127.0.0.1:9878`, nur von `localhost` erreichbar). Für den TokenRouter-Key ist das **bewusst so (Nutzerentscheidung 2026-09-27)** — der Provider wird nicht genutzt, und der Key wird deshalb bewusst nicht angefasst, statt ihn zu rotieren oder ins Bundle zu legen.
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
   und Netz-Ausfall),   `restore` holt fehlende Keys nach. `secrets.sh status`
   prüft zusätzlich, ob das Bundle überhaupt entschlüsselbar ist. **`status`,
   `doctor` und `opencode-version.sh check` liefern einen ehrlichen Exit-Code**
   (0 nur, wenn wirklich alles stimmt) — sie sind damit als Gate in
   `verify-codespace.sh` brauchbar, statt nur Text auszugeben.
   **Secret-Rechte:** alle Secret-Dateien (`config/passphrase`, `config/secrets.enc`,
   `config/secrets.manifest`, `llm-proxies/glm2api/.env`, `llm-proxies/zerokey/temp/users.json`)
   liegen auf 600, `.runtime` auf 700. `infra/scripts/secret-perms.sh` erzwingt das
   und entfernt die geerbte POSIX-Default-ACL (`rwx rwx rwx`), die `umask` aushebelt;
   `verify-codespace.sh` prüft die Rechte („Secrets nicht world-readable“).
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
| downloaddoctor | ZeroKey (16k Context, **2k** Output — `.opencode/opencode.json` `limit.output=2000`) | lokal, Port 7250, Platzhalter-Key `opencode`, Code im Repo |

- `downloaddoctor` ist in `opencode.json` konfiguriert (Loopback-only,
  Platzhalter-Key `opencode`).
- **`downloaddoctor` (ZeroKey) ist seit 2026-09-29 Teil der Setup-/Watchdog-Kette.**
  Vorher war er nur konfiguriert, aber in keiner Doku erwähnt und von keinem Skript
  gestartet (Befund aus dem Main-Analyse-Run 2026-09-28) — der Proxy lief nur, weil
  er von Hand gestartet worden war. `setup.sh` und `proxy-watchdog.sh` kümmern sich
  jetzt um ihn, der Code liegt in `llm-proxies/zerokey/`. Details im Abschnitt
  [ZeroKey](#zerokey--der-chatgpt-web-proxy-port-7250).
- `cyberpradeep` (ZeroKey-Variante, Port 8088) bleibt **außen vor**: kein Code im
  Repo, keine Credentials, nicht Teil der Kette — und **kein Provider-Eintrag in
  `opencode.json`**. Die frühere Doku behauptete hier das Gegenteil (acht Zeilen
  weiter oben), korrigiert 2026-10-01.

- `mcp.opencode-sessions`: Session-Verwaltung direkt auf der SQLite-DB
  (`infra/mcp/opencode-sessions-mcp.js`, zero deps) — list/preview/delete/search,
  kaskadierende Löschung + Orphan-Event-Cleanup, schützt aktive/aktuelle/geteilte
  Sessions, `confirm:true` Pflicht. Details: `infra/mcp/README.md`.
- `agent/glm2api.md`: Arbeits-Subagent fest auf `glm2api/glm-5.3` (Haupt-Proxy).
- `tui.json`: Maus-Capture **aus** (`mouse: false` ist Absicht: sobald eine App
  Mouse-Reporting einschaltet, behandelt das Terminal Mausereignisse als
  App-Eingaben — Text markieren und kopieren geht dann nicht mehr.
  **Nicht auf `true` ändern.**)
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
`.env` aus `llm-proxies/glm2api/.env.dist` (Port 8001, Guest-Mode, secret-frei), `uv sync`
(venv), Start. Kein Klon, kein Patch-Anwenden, keine externen Abhängigkeiten.
- Tool-Protokoll: von DSML-Markup auf JSON+`[]`-Terminator umgestellt (+ DSML/
  Mashup-Fallbacks, Part-Merge-Fix — chatglm.cn streamt erst Token-Schnipsel,
  dann Volltext; Fix = anhängen + idempotent ersetzen statt blind
  überschreiben). Direkt im Source eingearbeitet — der kanonische Code liegt
  im Repo (kein Patch-Artefakt mehr).
- setup.sh rebuilt nur bei `LANDSCAPE_REBUILD_LLM_PROXIES=1` (sonst manuell).
- Upstream-Limit ist pro Guest-Token (~5 Nachrichten) — der Pool rotiert das weg.

## ZeroKey — der ChatGPT-Web-Proxy (Port 7250)

OpenAI-kompatibler Proxy, der eine **ChatGPT-Web-Conversation** als
`/v1/chat/completions`-Endpunkt anbietet. Nötig, weil es keinen API-Key für
ChatGPT gibt: der Proxy fährt einen echten Browser (Playwright), übernimmt
Cookies und Sentinel-Token aus einem Capture und streamt die Conversation.

| | |
|---|---|
| **Code** | `llm-proxies/zerokey/` — **liegt im Repo, kein Klon** (vendored 2026-09-29 aus `/workspaces/downloaddoctor-zerokey`) |
| **Start** | `./llm-proxies/scripts/start-zerokey.sh` (`node server.js chatgpt main MAIN`) |
| **Port** | 7250, loopback-only |
| **opencode** | Provider `downloaddoctor`, Modell `zerokey`, Platzhalter-Key `opencode` |
| **Log** | `/tmp/opencode/zerokey.log`, PID `/tmp/opencode/zerokey.pid` |
| **Health** | `curl -s 127.0.0.1:7250/health` |
| **Stall-Watchdog** | `ZEROKEY_STREAM_IDLE_TIMEOUT_MS` (Default `90000`) — Stille-Budget pro SSE-Chunk. Ein Turn ohne jedes Byte für 90 s wird als `stream_stalled` (504) abgebrochen statt bis zum 300-s-`https.Agent`-Timeout zu warten. `0` schaltet den Watchdog ab. Siehe Changelog 2026-10-02 (16). |
| **Quelle** | upstream `downloaddoctor/zerokey`, Stand `11ea0bf` (Version 0.3.0) — vollständig, `origin/main` endet bei `4d635ab` und ist Vorfahr davon |
| **Historie** | `llm-proxies/zerokey/upstream-history.bundle` (198 Commits, alle Branches/Tags). Die beiden alten Checkouts unter `/workspaces` sind gelöscht; Wiederherstellung: `git clone llm-proxies/zerokey/upstream-history.bundle <ziel>` |

### Credentials — der Teil, der nicht im Git stehen kann

`llm-proxies/zerokey/temp/users.json` enthält die **ChatGPT-Cookies, das
Sentinel-Token und die Session-IDs**. Das ist ein Secret mit Auslaufdatum, kein
Quelltext — deshalb ist `temp/` per `.gitignore` ausgeschlossen und die Datei
wandert über das Secret-Bundle:

```
config/secrets.enc  --(secrets.sh unlock)-->  ~/.config/landscape/zerokey-users.json
                    --(start-zerokey.sh)-->  llm-proxies/zerokey/temp/users.json
```

`secrets.sh` packt sie bei `lock` ein und legt sie bei `unlock` ab (symmetrisch
zum `chatglm-refresh-token`). **Nach dem ersten `lock` mit dem neuen Eintrag**
überlebt der Proxy einen Codespace-Neubau ohne Browser-Login.

Solange das Bundle sie nicht enthält, startet `start-zerokey.sh` **nicht**
sondern sagt es klar — ein stiller Fehlstart ohne Credentials wäre ein Proxy, der
401 liefert und den Agenten raten lässt.

**Wenn die Cookies abgelaufen sind** (ChatGPT-Session, typisch nach Tagen):
`initializeFromJSON` schlägt dann mit `openai-sentinel-proof-token not found`
fehl. Neuer Login = ChatGPT im Browser öffnen, die Conversation als HAR
capturen, `utils/har-to-capture.js` drüber, Ergebnis nach
`~/.config/landscape/zerokey-users.json`, dann `secrets.sh lock` + `save.sh`.

### Abweichungen vom Upstream-Stand

Bewusst, beim Vendoring gemacht — jeweils weil das Original im MAIN-Repo Schaden
angerichtet hätte:

| Entfernt | Warum |
|---|---|
| `"postinstall": "git config core.hooksPath .githooks"` | Läuft bei jedem `pnpm install` **im MAIN-Repo** und würde dessen `core.hooksPath` auf einen relativen, nicht existierenden Pfad umbiegen — die Hooks des Haupt-Repos wären still weg. |
| `.githooks/pre-commit` | Macht `git add $files` über alle geänderten Dateien. Im geteilten MAIN-Repo (mehrere eigene Accounts) würde ein Commit eines Agenten damit fremde Arbeit mit einfrieren. |
| `.vscode/settings.json` | Editor-Konfiguration des Upstream-Klons (`chat.tools.terminal.autoApprove` für `Set-Content`). MAIN hat eigene `.vscode/`; die Datei hätte im Unterordner nur überflüssig gewirkt. |

`zerokey.sh` / `zerokey.bat` (Upstream-Download-/Klon-Helfer) sind bewusst
**da** — sie sind Teil der Upstream-Distribution und in dessen README
dokumentiert. Für dieses Setup gilt `llm-proxies/scripts/start-zerokey.sh`;
wer `./zerokey.sh` hier ausführt, erzeugt ein verschachteltes `zerokey/zerokey`.

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
- **Commit-Signierung: SSH statt Codespaces-Token.** `setup.sh` setzt repo-lokal
  `gpg.format=ssh`, `user.signingkey=~/.ssh/codespaces.auto.pub`,
  `gpg.ssh.allowedSignersFile=config/git-allowed-signers` (versioniert, Dedup pro
  Fingerabdruck — der hier früher genannte Pfad `.runtime/git-allowed-signers` ist
  der Stand vor 2026-09-30 und existiert nicht mehr) und `commit.gpgsign=true`. **Warum nicht der Codespaces-Signierer:**
  `/.codespaces/bin/gh-gpgsign` benutzt den Codespaces-`GITHUB_TOKEN`, ein
  App-/Integrationstoken, und lehnt jede Signatur ab: **`403 Author is
  invalid`**. In zwei Wegwerf-Repos reproduziert — **nicht** an Identität oder
  Token-Scope: Commit-Autor `tadeuslol <334215299+tadeuslol@…>`, GitHub-Account
  `login=tadeuslol id=334215299`, PAT gehört demselben Account, und trotzdem
  403, auch mit `GH_TOKEN`/`GITHUB_TOKEN` auf den PAT. Beleg für die
  Integrations-Art: `gh api user/emails` → `Resource not accessible by
  integration`. **SSH-Signierung läuft rein lokal**, braucht keine API und
  keinen Token. Verifiziert: Commit mit `sig=G`, Key
  `SHA256:jWmmf21DqioRG6oW/xFE8S5I3NG57BVKXQ79a1suSbA`.
  Die `allowedSignersFile` liegt in `.runtime/` (gitignoriert), weil der
  Codespace-Key pro Codespace neu sein kann — sie enthält nur den **öffentlichen**
  Schlüssel, ist also kein Secret. **Offen:** GitHub zeigt „Verified" erst, wenn
  der Key einmalig als **Signing key** im Account registriert ist
  (`user/ssh_signing_keys` ist derzeit leer); die Signatur ist gültig, aber
  serverseitig unbestätigt.

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
  **Aktueller Pin: `1.18.32`** (Stand 2026-10-01; Quelle `.opencode/package.json`,
  Dep `@opencode-ai/plugin` + `package-lock.json`) — die einzige Versionszahl im
  Repo. `./infra/scripts/opencode-version.sh bump` (Alias `ocver`) — updated Pin **und**
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
- **Linter automatisch im Commit (seit 2026-10-01):** `.githooks/pre-commit`
  (versioniert im Repo) fährt die Checks der **betroffenen** Sprache: glm2api
  `ruff`+`mypy`, antigravity-proxy `go vet`+`gofmt -l`, MAIN-eigenes JS
  (`infra/**.js`) `node --check` — jeweils **nur** wenn die passenden Dateien
  gestagt sind, damit Commits an fremde Teile nicht ausgebremst werden.
  `setup.sh` setzt `core.hooksPath=.githooks` (vom Repo-Root, relativ — genau
  das machte das entfernte zerokey-`postinstall` falsch, das denselben Wert aus
  einem Unterordner ins Leere bog). Der Hook fasst den Index **nicht** an (kein
  `git add`, kein `--fix`/`--write`); Notausstieg `git commit --no-verify`.
  `verify-codespace.sh` prüft die Verdrahtung. zerokeys `pnpm precommit`
  (Format+Lint+Check+Test) bleibt handgestartet, weil es `node_modules` braucht.
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

1. **Vendor-Binary-Patch (`patch_arrow_scroll` in `infra/scripts/freebuff-install.sh`):**
   Im kompilierten Bundle von `~/.config/manicode/freebuff` leitet ein atomarer 90-Byte-Patch
   `case "history-up"` und `case "history-down"` im Action-Dispatcher direkt auf `onScrollUp()`
   und `onScrollDown()` um.
   *Sicherheitsnetz:* Falls ein nativer Pfeil bei leerem Prompt durchrutscht, scrollt er
   die Unterhaltung statt die Prompt-Historie zu verändern.

2. **Vendor-Binary-Patch für saubere Wort-/Zeilengrenzen (`patch_word_boundary` in `infra/scripts/freebuff-install.sh`):**
   In Freebuffs Wortbewegungsfunktionen `LGA` (Word Backward) und `_GA` (Word Forward) fraß
   die originale Schleife (`while($>0&&/\s/.test(H[$-1]))$--;while($>0&&!/\s/.test(H[$-1]))$--;`)
   Leerzeilen und das vorherige Wort in einem einzigen Schritt mit, sodass der Cursor über Zeilen hinweg
   immer sofort am Zeilenanfang landete und `Strg+Backspace` die Zeile darüber mitlöschte.
   Der atomare 276-Byte-Patch trennt Whitespace- und Wortschritte sauber (`s = $>0 && /\s/.test(...)`):
   Steht der Cursor nach Zeilenumbrüchen am Zeilenanfang (`|Hey`), springt `Strg+Links` bzw. löscht
   `Strg+Backspace` präzise bis zum Zeilenende der vorigen Zeile (`Hey|`), statt das Wort mitzureißen.

3. **Vendor-Binary-Patch für Session-Löschung in `/history` (`patch_history_delete` in `infra/scripts/freebuff-install.sh`):**
   Freebuff implementiert das Löschen von Chats in `/history` ausschließlich per Mausklick auf `[×]` (`onClick: () => f(X, v)`),
   bietet jedoch kein Tastaturkürzel im UI an (`onKeyIntercept` leitete nur Up/Down/Right/Enter/Esc/Ctrl+C ab).
   Weil das Mouse-Reporting für das benutzerdefinierte Setup (Mausrad-Scrollen, native Terminal-Auswahl, Copy/Paste)
   im PTY-Filter bewusst deaktiviert ist, empfing die App keine Mausklicks und Sessions waren unlöschbar.
   Der atomare Patch erweitert `onKeyIntercept` um `Delete` (`Entf`), `Ctrl+D` und `Ctrl+X` auf der fokussierten Session
   (`s = F[R]`), ruft die native Löschaktion `l(s)` auf und aktualisiert die Statuszeile längengleich
   (`Click [×] to remove` -> `Del / Ctrl+D to remove`).

4. **PTY-Filter (`infra/scripts/freebuff-pty.py`):**
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
| Laufzeit | `start-glm2api.sh` idempotent | Doppelstart-sicher, Port-Check. **Merksatz:** die beiden Startwege müssen gleichwertig bleiben — `infra/scripts/glm2api.sh` (interaktiv) und `start-glm2api.sh` (Boot/Watchdog). Sie waren es nicht: nur der zweite startete mit `setsid`, und ein Agent-Tool-Call im Timeout schickte dem interaktiv gestarteten Proxy SIGTERM mitten im Stream (Changelog 2026-09-26) |
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
  - **Lösung:** Neuer atomarer Vendor-Patch `patch_history_delete` in `infra/scripts/freebuff-install.sh`. Er erweitert den `onKeyIntercept`-Callback in der History-Komponente um die Erkennung von `Delete` (`Entf`), `Ctrl+D` und `Ctrl+X` auf der fokussierten Session (`s = F[R]`), ruft die native Löschaktion `l(s)` auf und aktualisiert die Statuszeile exakt längengleich (`Click [×] to remove` -> `Del / Ctrl+D to remove`).
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

- 2026-10-02 (16): **Der 5-Minuten-Hänger war der `https.Agent`-Idle-Timer, nicht das Modell — und zwei weitere Defekte aus derselben Session.** Anlass war die Nutzerfrage „analysiere die Session": `ses_f06959c34ffem62VA5MinVvP4a` (2026-10-01 23:41–23:56, 5 User-Turns, 14m51s, 6 Tool-Calls, 0 davon in den drei abgeschlossenen Antwort-Turns). Auswertung aus `~/.local/share/opencode/opencode.db` (SQLite) + `log/opencode.log`.
  **(1) Der Hänger.** Letztes Tool-Ergebnis 21:51:04.360, neuer `stream`-Versuch 21:56:06.280, dazwischen **301,9 s** Funktstille, dann `cancel` → `MessageAbortedError`. Die Zahl ist keine Ähnlichkeit: `readSSE` hatte **keinerlei Inaktivitätsüberwachung** — `await reader.read()` wartet unbegrenzt, und beendet wurde der Read nur durch den `timeout: 300000` des `https.Agent` in `providers/{chatgpt,base,qwen}/api.js`, der als undurchsichtiger Socket-Fehler auftaucht. Neu: **Stall-Watchdog in `utils/sse-reader.js`** — Budget pro Chunk (`CONFIG.STREAM_IDLE_TIMEOUT_MS`, Default **90 s**, überschreibbar per `ZEROKEY_STREAM_IDLE_TIMEOUT_MS`, `0` schaltet ab), bei Überschreiten `Error` mit `code: 'stream_stalled'`, `status: 504`, der die Runde **als Fehlschlag** beendet (`onDone` läuft nicht). Das Budget ist ein **Stille-**, kein Gesamtbudget: ein langer, aber produktiver Reasoning-Turn wird bei jedem Chunk neu gestellt und nie abgeschnitten. **Zwei Fallen, die der erste Wurf hatte und die die Tests jetzt festhalten:** `Promise.race([pending, undefined])` löst bei deaktiviertem Watchdog **sofort** auf (liest gar nichts mehr), und `Readable.from(asyncGenerator)` emittiert bei `destroy(err)` **gar kein `'error'`**, wenn der Generator auf einem offenen `await` festhängt — auf dieses Event zu warten hieße, den Stall nie zu melden. Der Node-Zweig settled deshalb selbst und benutzt `destroy()` nur noch, um den Socket freizugeben. Beide Streamformen (WHATWG-`getReader` und Node-Readable) sind abgedeckt, 15 Checks in `scripts/test-sse-reader.js` inkl. „langsam aber lebendig wird nicht abgeschnitten“ und „kein Timer überlebt den Stream“.
  **(2) Die Konfiguration war richtig — und das musste erst festgestellt werden.** Meine erste Idee war, `compaction.reserved` zu erhöhen, damit die Kompaktierung vor der Proxy-Kürzung feuert. Das wäre ein Rückbau gewesen: `check-proxy-budget.py` (grün, Exit 0) und die Commits `f37a469`/`1baa16d`/`e63fd65` halten die Zahlen `context=16000 / output=2000 / reserved=2000` gegen eine **Nutzerentscheidung** fest — opencodes Summarizer verbietet Tool-Calls, ZeroKeys `instructions.md` schreibt sie vor, jeder Kompaktierungslauf endete an „Tool call not allowed while generating summary“. **Unangetastet.** Was die Kopplung *nicht* ausdrücken kann, ist die tatsächliche Fehlstelle, und die ist ein **Größenvergleich zweier verschiedener Dinge**: opencode kürzt ein **einzelnes** `read`-Ergebnis bei **50 KB** (und schreibt darunter `Use offset=729 to continue.` — das ist vorbildlich), ZeroKeys `promptLimit` ist aber **49.936 Zeichen für den gesamten Prompt**. Jedes große `read` ist damit per Konstruktion größer als alles, was der Proxy jemals bauen kann, und `limitPrompt` wirft middle-out den **Mittelteil genau dieses einen Ergebnisses** weg — ohne Fehlermeldung nach außen. `infrastructure.md` selbst ist das Extrembeispiel: 1.774 Zeilen, **312.895 Bytes**. Neu: **Abschnitt D in `.opencode/INSTRUCTIONS-glm2api.md`** („Kontextbudget: grosse Dateien immer fenstern“, global wie A, nicht glm2api-spezifisch wie B/C) — ein `read`-Ergebnis unter ~8.000 Zeichen, `limit` explizit auf ~200 Zeilen, `grep` vor dem Voll-Read, `offset` weiterzählen statt von vorn.
  **(3) Die stille Kürzung war am Client unsichtbar.** `buildUsage` meldete nur Token-Zahlen; das Modell sah die Lücke über die Drop-Marker, der Client sah einen normalen Turn. Ein Turn auf einem aufgeschmitzten Prompt war damit von einem vollständigen nicht unterscheidbar — das hat die Diagnose oben unnötig teuer gemacht. `usage` trägt jetzt zusätzlich `prompt_truncated` (rein additiv, opencode liest es und rendert es nicht), mit vier Zusicherungen in `test-ask-guard.js`.
  **(4) Der Ask-Guard sah „ich habe keinen Zugriff auf deine Maschine“ nicht.** Drei der fünf Turns waren genau das — **ohne jeden Tool-Call**, obwohl `read`/`bash`/`glob` im selben Request deklariert und `permission: allow` war. `isDriftText` kann das prinzipiell nicht: es matcht „was soll ich als Nächstes tun?“, nicht eine Fähigkeitsbehauptung. Neu: **`isNoAccessText`** (`engine/ask-guard.js`), verdrahtet in `finishOrRetry` als **`no-access`** mit eigenem Nudge, der die Falschangabe korrigiert und die Werkzeuge benennt. Absichtlich eng: greift nur bei Zugriffsverweigerung **plus** entweder generalisierter Bezug (Maschine/Arbeitsverzeichnis/Repository/Dateien) **oder** ein explizites Angebot, Inhalte hochzuladen/einzufügen. „Kein Zugriff auf Port 7250“ und fehlende Sentinel-Header bleiben echte Blocker und werden nicht gebremst; ein reines „X oder Y?“-Menü ohne Verweigerung ebenfalls nicht. **Zwei Testerwartungen von mir waren dabei falsch, nicht der Code:** der dritte „echte Turn“ war der abgeschnittene Schwanz von Turn 2 (ohne Verweigerung im Kopf → darf korrekt *nicht* greifen), steht jetzt als Gegenprobe im Test statt als erwarteter Treffer; und der erste Wurf behandelte den Tail eines Blocks nicht idempotent.
  **Zur Session selbst, nicht geändert:** `AGENTS.md` kam **zweimal als User-Nachricht** im Chat an (10.730 Zeichen, byteweise das Repo-`AGENTS.md` von 23:50, **kein einziges Zeichen echter User-Text**). Über die ganze DB geprüft: 2 Treffer, nur in dieser Session — opencode macht das also nicht systematisch, es wurde hineinkopiert. Als Löschanweisung taugt das nicht; der Guard aus (4) fängt die Folge ab.
  **Verifiziert:** `make ci` = `check` + `verify-code` grün (**16 PASS / 0 FAIL / 22 SKIP**), `make check` Exit 0, `pnpm lint`/`check`/`test` grün, `check-proxy-budget.py` unverändert grün, `test-sse-reader.js` 15/15, `test-ask-guard.js` und `test-ask-guard-e2e.js` inkl. der neuen Fälle (`[P] attempts=1 reason=no-access tools=[glob,read]`, `[Q] attempts=0`). **Nicht verifiziert:** ein echter Hänger am lebenden Upstream — der Watchdog ist gegen reproduzierte Streams getestet, nicht gegen einen echten Totalausfall von ChatGPT.

- 2026-10-02 (16): **Stufe 4: shellcheck mit eingefrorener Baseline — 30 Befunde eingefroren, alles Neue rot.** `bash -n` fängt Syntax; shellcheck fängt die echten Shell-Fehler. Über 41 committete Skripte (alle bash) sind es **30 eindeutige Befunde** (18 warnings, 12 notes; Rohform 60, weil derselbe Befund mehrfach vorkommt) — SC2002/2015/2016/2034/2064/2086/2097/2098/2115/2155/2162/2164. Ein Gate, das nicht in einem Durchgang zu beheben ist, wird mit `|| true` entschärft und ist dann wertlos, deshalb der Mittelweg: **Baseline eingefroren, alles neue rot.** Neu: `infra/scripts/shellcheck-check.sh` (read-only; `--update` friert bewusst neu ein) und `infra/scripts/shellcheck-baseline.txt`. **Zwei Entwurfsentscheidungen, die man kennen sollte:** (a) die Baseline ist **ohne Zeilennummer** normalisiert (`pfad | schwere | meldung | SC-Code`) — mit Zeilennummer wäre sie bei jeder harmlosen Zeilenverschiebung rot und damit unbrauchbar; der Preis ist, dass eine *zweite* Instanz desselben Befunds in derselben Datei nicht als neu gilt. (b) Fehlt shellcheck, endet das Skript mit **WARN + Exit 0**, damit ein Codespace ohne sudo nicht am Gate scheitert — `setup.sh` installiert es aus apt (Debian 24.04 = 0.9.0, ubuntu-24.04 = 0.9.0, gleiche Befundmenge), und der Verify-Check meldet das Fehlen getrennt. Verdrahtet in `make check-fast`, im pre-commit-Hook (triggert auf jede `.sh`-Änderung, der Hook selbst ist eine), im CI-Job `infra` und im neuen Verify-Check „Shellcheck-Baseline verdrahtet“. **Das Gate hat sich beim Bauen zweimal selbst bewährt:** Ein Kommentar mit dem Wort `shellcheck` am Zeilenanfang ist für shellcheck eine *Direktive* (SC1073/SC1126) — der Kommentar in `setup.sh` musste umformuliert werden; und ein inline `#`-Kommentar **innerhalb** einer `apt_install`-Fortsetzungszeile hat den Aufruf zerlegt (SC1072), wodurch ich fast ein `|| true` verloren hätte — beides fiel sofort auf, nicht beim Review.
- 2026-10-02 (15): **Stufe 3: `infra/scripts/*.py` hat jetzt Tests, ruff und mypy — plus ein Coverage-Floor, der beißen kann.** Die letzte Python-Fläche ohne jedes Werkzeug ist geschlossen: neue **Root-`pyproject.toml`** als reines Werkzeug-Projekt (`[tool.uv] package = false`, kein Build, kein Packaging) mit **gepinnten** Dev-Deps (mypy 1.18.2, pytest 9.1.1, pytest-cov 7.0.0, ruff 0.14.4 — dieselben Versionen wie im Vendor-Baum) und eigener `uv.lock`. Abgrenzung über `extend-exclude`: ein `ruff check` aus dem Root lintet **nicht** den Vendor-Baum. `infra/docs/reverse-engineering/*.py` sind per `extend-exclude` ausgenommen — das sind archivierte RE-Skripte (eines schreibt noch auf `/workspaces/reverse-engeneer/screen.png`), die 27 E7xx-Befunde wären ohne Nutzen, weil sie beim Boot nie laufen. **Erste Messung (Bestandsaufnahme, wie im Plan vorgesehen):** `check-proxy-budget.py` 70 %, `freebuff-pty.py` 0 % (310 Statements), `watch-subagent.py` 0 %, **gesamt 15 %**. mypy war überraschend **sofort grün** (3 Dateien, 0 Befunde) und ist deshalb als Gate verdrahtet, nicht nur als Messung. **`check-proxy-budget.py` ist dafür refaktoriert:** die Kopplungslogik steckt jetzt in `pruefe(ctx, out, reserved, limit)` — pure Rechnung, ohne I/O und ohne `print` — und `lade()` nimmt Pfade als Parameter statt `sys.argv` zu lesen. CLI-Verhalten unverändert. Ergebnis **20 Tests, `check-proxy-budget.py` bei 98 %**. **Zwei echte Befunde aus dem Testbau:** (a) Die Empfehlung im Fehlertext war falsch gerechnet (`output muss < 8750`, korrekt 3500) — ein Grund, warum die Regel einen Test verdient; (b) der Zweig `chars < limit*0.25` („Limit koennte hoeher“) ist **mathematisch unerreichbar**, sobald alle Fehlerregeln gruen sind: ohne reserved-Fehler gilt `chars ≥ 2*ctx`, ohne Kuerzungs-Fehler `limit < 4*ctx`, der Zweig will `limit > 8*ctx`. Er druckt also nur noch zusammen mit einem echten Fehler — als Hinweis toter Code. Die Eigenschaft ist als Test festgeschrieben (Sweep über ~44 000 Kombinationen), damit ein späteres Aufweichen einer Regel auffaellt. **Floor:** `infra/coverage-floor.rc` setzt `fail_under = 90` **für diese eine Datei** (`make cov-floor`, aktuell 97,78 %); `make cov` zeigt weiterhin alle drei. Negativtest: Floor auf 99 gehoben → Job rot. Neuer Verify-Check **„Root-Python-Umgebung verdrahtet“** verhindert das stille Zurückfallen (pyproject, uv.lock, vier Make-Targets, Hook-Zweig). Hook um den Zweig „MAIN-Python“ erweitert, CI um den Job `infra-python`. Der Vendor-Baum bleibt unberührt — uv nimmt immer die nächstgelegene `pyproject.toml`.
- 2026-10-01 (14a): **Drei echte CI-Fehler gefunden — der erste Lauf des Workflows war rot, der dritte grün.** Der erste überhaupt (Lauf 36932043836) starb schon in **0 s** an der Workflow-Datei, nicht an einem Job: `timeout-minutes` unter `defaults.run` ist **kein** gültiger Schlüssel (dort sind nur `shell` und `working-directory` erlaubt). Lauf 2 lief, drei Jobs waren rot — und alle drei Fehler waren Workflow-Bugs, keine Code-Bugs: (a) `go-version-file: go.mod` ist relativ zum **Repo-Root**, nicht zum `working-directory` des Jobs; (b) `cache: pnpm` in `setup-node` sucht pnpm auf dem PATH, **bevor** corepack es aktiviert hat → „Unable to locate executable file: pnpm" (corepack läuft jetzt nach der Node-Action, der Cache ist raus — Robustheit schlägt ein paar Sekunden); (c) `setup-uv` mit `enable-cache` im `repo`-Job scheiterte im Post-Step („cache path does not exist"), weil es dort keine uv.lock gibt — der Job braucht nur `python3`. **Lauf 3: alle fünf Jobs grün.** Und der **Negativbeweis** (PLAN Stufe 2 fordert ihn ausdrücklich) lief über einen Branch + PR statt über `main`: mit einem Absichtfehler in der Hook/Makefile-Kopplung (`ruff check` → `ruff chek`) wurde genau der `repo`-Job rot: „FAIL Makefile deckt Hook ab — Makefile und Hook nennen verschiedene Kommandos -> make:[ruff check]". PR wieder geschlossen, Branch gelöscht. **Nebenbefund mit echter Lücke:** der pre-commit-Hook hat den Fehler **nicht** gesehen, weil er pfad-scoped auf Quellsprachen läuft und eine reine `Makefile`-Änderung nicht triggert. Die Kopplung Makefile↔Hook wird derzeit nur von `make verify-code`/CI geprüft — für einen Commit wäre das ein Lint-Hook-Zweig auf `Makefile` + `.githooks/pre-commit` selbst.
- 2026-10-01 (14): **Erstmals CI: `.github/workflows/checks.yml` mit fünf Code-Jobs.** Bis hierher hing **jeder** Check daran, dass ein Agent `AGENTS.md §6` befolgt — wird er übersprungen, fällt alles still aus (PLAN Stufe 2). Jobs: `glm2api` (ruff + mypy + pytest), `antigravity` (`go vet` + `gofmt -l` + `go test`), `zerokey` (pnpm lint/check/test), `infra` (`bash -n` über 41 Skripte + `node --check`), `repo` (`verify-codespace.sh --code`). Trigger: Push auf `main`, jeder PR, `workflow_dispatch`; `permissions: contents: read`, `concurrency` bricht abgebrochene Läufe ab. **Keine Secrets, kein `pull_request_target`, keine Schreib-Rechte** — es sind reine Quellcode-Jobs. **Toolchain-Pins kommen aus dem Repo, nicht aus der Workflow-Datei:** Go aus `go.mod` (`go-version-file`), Python 3.14 aus `.python-version`, pnpm per `corepack` aus `packageManager`. Grund: der Job soll an genau der Toolchain des Codespaces hängen, nicht an einer zweiten Wahrheit. Der neue Verify-Check **„CI-Pins decken Repo-Pins“** prüft genau das (positiv und negativ getestet: Lockfile-Drift-Zeile entfernt → Check rot). **Ausdrücklich nicht drin:** Provider-Calls (`keys.sh doctor`, glm2api-Smoke-Test) — sie kosten Kontingent und ein flaky Live-Check wird schnell übersprungen (Stufe 5). **Arbeitsteilung:** CI = Quellcode, Codespace = laufende Kette; der `repo`-Job kann sauber sein, während im Codespace etwas fehlt. **Verifiziert:** YAML parst (5 Jobs), alle Job-Kommandos lokal ausgeführt (bash -n 41 Skripte, node --check, `uv lock --check`), `verify-codespace.sh --code` **15 PASS / 0 FAIL / 22 SKIP**, und im simulierten **frischen Clone** `/tmp/ci-sim` ebenfalls 0 FAIL.
- 2026-10-01 (13a): **Vier Checks nach Ebenen getrennt, weil sie im CI-Runner falsch rot geworden wären.** Ein simulierter frischer Checkout (`git clone` nach `/tmp`) hat es gezeigt: Git überträgt nur das executable-Bit, also liegen `config/passphrase` & Co. dort auf 644, `core.hooksPath` ist nicht gesetzt und `~/.gemini/settings.json` existiert nicht — drei Checks meldeten FAIL, obwohl **kein** Defekt vorlag. Aufgeteilt in je einen Code- und einen chain-Anteil: „Secret-Rechte: Werkzeug verdrahtet“ (prüft `secret-perms.sh` + Aufruf in `setup.sh`), „Gemini-Context verdrahtet“, „Lint-Hook im Repo“ (Datei da + startbar) und „core.hooksPath = .githooks“. Der Go-Check löst `go` jetzt über `command -v` auf (vorher fest `/usr/local/go/bin/go`) — auf einem Actions-Runner liegt Go im PATH, sonst wäre der Job an der Toolchain statt am Code rot. Negativtest unverändert: temporäre `GEMINI.md` → `--code` rot.
- 2026-10-01 (13): **`verify-codespace.sh` hat jetzt drei Modi — die Voraussetzung für CI (PLAN Stufe 1).** Rund 80 % der Checks prüften *laufende Dinge* (Prozess auf 8001/9878/7250/4096, Daemons, entschlüsseltes Bundle, Drive-Credentials). Unverändert auf einem GitHub-Runner gefahren wären das ~20 FAILs, weil dort nie etwas gestartet wurde — und ein roter Job, den man zu ignorieren lernt, ist schlimmer als keiner. Statt die 30 `if`-Blöcke umzubauen, trägt jetzt jeder Check eine **Ebene**: `code` (nur Repo + Toolchain), `chain` (laufende Dienste) oder `live` (echte Provider-Calls), über `check_layer <ebene> <name> <cmd…>`. Passt die Ebene nicht zum Modus, wird der Check **SKIP** statt FAIL. Modi: `--code` (Default in CI), heutiger chain-Default, `--live` (chain + `keys.sh doctor` + voller Smoke-Test). Unbekannte Argumente → Exit 2 mit Aufruf-Zeile. Die Quoten-Anzeige (echter Upstream-Call) und `FIREFOX`/`MCP`-Laufzeitteile sind im `--code`-Modus ebenfalls still, damit dort nichts an der Zielplattform scheitern kann. **Verifiziert:** `--code` → 14 PASS / 0 FAIL / 19 SKIP, chain → 31 PASS / 0 FAIL / 2 SKIP, `--live` → **33 PASS / 0 FAIL** (inkl. echtem Smoke-Test „ALLE OK“); **Negativtest** (temporäre `GEMINI.md` im Root) → `--code` wird rot mit `FAIL keine divergierenden Client-Kopien`. Neues Target `make verify-code`, `make ci` = `check` + `verify-code` (exakt der Workflow-Umfang), `AGENTS.md §6` ergänzt. Zwei Kosmetik-Funde dabei mitgenommen: fehlender Zeilenumbruch vor `== 9.` (Tabelle klebte am letzten PASS) und die Sektion-8-Trennung.
- 2026-10-01 (12): **Welle A abgeschlossen (A5–A12) + `make check` als Single-Entrypoint.** **Welle A** (aus dem Härtungsplan, alles einzeln committet und verifiziert): **A5** `setup.sh` bricht bei EINEM fehlenden apt-Paket den kompletten Codespace-Aufbau ab (`set -euo pipefail` + nackte `apt-get`-Zeilen) — jetzt sammelt `apt_install` die Fehler, versucht bei den versionsabhängigen GUI-Paketen erst `libgtk-3-0t64` & Co. und dann die klassischen Namen, und meldet alles am Ende als Sammelliste. Getestet mit gestubbtem `apt-get`: nur-t64-Fehler → Fallback greift, Gesamtausfall → Skript läuft trotzdem durch. **A6** pnpm war in der gesamten Kette nicht installiert/gepinnt (die installierte Version kam aus `npm i -g pnpm` in `zerokey.sh`); `setup.sh` aktiviert jetzt per corepack den Pin aus `llm-proxies/zerokey/package.json` (`packageManager`, 10.13.1), mit Fallback auf `corepack install --global` für neuere Node-Versionen. **A7** `start-on-boot.sh` hatte die Schritte 0,1,2,4,5,6 — **Schritt 3 (zerokey, Port 7250) fehlte**, nach jedem Resume blieb zerokey bis zum 30-s-Watchdog tot. **A8** `gdrive-backup.sh` endete bei fehlender Auth mit `exit 0`, und `save.sh` wertet nur den Exit-Code aus und druckt deshalb **keine** Warnung — ein komplett totes Backup war von einem gesunden nicht unterscheidbar. Jetzt `exit 1` (Positiv- und Negativpfad getestet; der Push bleibt sicher, `save.sh` fängt ab). **A9** `.freebuff/` und die Root-Caches standen nur in `.git/info/exclude` (nicht versioniert → in einem frischen Clone trackbar), jetzt im versionierten `.gitignore`. **A10** fünf Doku-Falschaussagen korrigiert: `cyberpradeep` existiert gar nicht (Provider-Zeile entfernt, der Selbstwiderspruch acht Zeilen darunter aufgelöst), downloaddoctor hat 2k statt „16k Output“ (`.opencode/opencode.json` `limit.output=2000`), `gpg.ssh.allowedSignersFile` ist `config/git-allowed-signers` (nicht `.runtime/…`), und der opencode-Pin (1.18.32) steht jetzt im Soll — die Changelog-Historie blieb bewusst unverändert. **A11** `auth.sh` schaltete `commit.gpgsign` unbedingt aus, `setup.sh` schaltet es ein — jedes manuelle `auth.sh setup` löschte die Signierung wieder; jetzt wird nur noch abgeschaltet, wenn wirklich kein `user.signingkey` hinterlegt ist. **A12** `glm2api.sh` hatte `start_log_guard` + „✓ Server gestartet“ doppelt; der zweite Guard überlagerte beim Rotations-Umschreiben der PID-Datei den ersten und ließ ihn orphan. **Stufe 0:** neues `Makefile` im Repo-Root als **ein** Einstiegspunkt (`check`, `check-fast`, `verify`, `smoke`, `check-all` plus Einzeltargets). Es dupliziert bewusst keine Check-Liste — jedes Target fährt exakt die Kommandos des pre-commit-Hooks, und der neue Verify-Check „Makefile deckt Hook ab“ vergleicht beide Dateien (positiv und negativ getestet). `AGENTS.md §6` verweist jetzt auf `make check`, statt die Kommandos selbst zu listen. **Verifiziert:** `make check-fast` grün (ruff, mypy, go vet, infra-JS, 41 Shell-Skripte), `bash -n` auf allen geänderten Skripten, `verify-codespace.sh` **31 PASS, 0 FAIL, 2 SKIP**.

- 2026-10-01 (11): **rclone sichert jetzt über einen eigenen Google-`client_id` — die vom Plan notierte Abschalt-Frist ist entschärft.** rclone warnte bei jedem Upload, es nutze einen *geteilten* Client, den Google 2026 abschaltet; danach wäre das Drive-Backup ausgefallen (`save.sh` ruft den Hook mit `|| true` auf, es bliebe unbemerkt). Ein eigener OAuth-Client (Typ **Desktop-App**, Projekt `423042998961`) wurde eingerichtet, `client_id` + `client_secret` stehen in `~/.config/rclone/rclone.conf`, der Refresh-Token ist über `rclone authorize drive <id> <secret>` neu ausgestellt und in die Config geschrieben (`~/.config/rclone/`, nicht `~/.config/landscape/`). Bundle via `secrets.sh lock` mitgezogen. **Drei Fallen, die dabei Zeit gekostet haben:** (a) die App im Modus *Testing* erlaubt nur **Testnutzer** — der Kontoeintrag im Consent-Screen (`…/auth/audience`) war die Lösung für `403 access_denied`; der frühere Reiter „OAuth consent screen" heißt jetzt „Google Auth Platform". (b) Beim Bestätigen mit `</dev/null` bricht `rclone config reconnect` mit EOF ab — `yes | rclone …` nötig. (c) `rclone config update gdrive client_secret=…` verschlüsselt (obfuskiert) das Feld doppelt, wenn das Secret base64-artig und ≥22 Zeichen ist: erst `rclone obscure` + `--no-obscure` (mit `config_refresh_token=false`, sonst versucht `config update` einen Token-Refresh) schreibt korrekt — geprüft mit `rclone reveal`. Zusätzlich schickte ein im Codespace-Firefox offen gebliebener *alter* Auth-Tab beim zweiten Versuch den alten `state` („Auth state doesn't match"); gelöst über `rclone authorize` (fasst die Config nicht an) statt `reconnect`. **Verifiziert:** `rclone about gdrive:` liest das echte Drive, `gdrive-backup.sh backup --force` lädt hoch + rotiert + verifiziert (119.241.241 Bytes, MD5 geprüft), **ohne** die geteilte-client_id-Warnung. Der Backup-Pfad selbst blieb unverändert. **Nachtrag:** Die OAuth-App wurde auf **„In production"** veröffentlicht (Startseite = öffentliches Repo, Datenschutz = `PRIVACY.md`), weil Google bei **Testing** die Refresh-Tokens nach **7 Tagen** ablaufen lässt; danach **einmal neu autorisiert**, damit der Token unter Production ausgestellt ist. Ab jetzt erneuert rclone den Token selbst — kein manuelles Anmelden mehr.

- 2026-10-01 (10): **Boot-Hang und `pkill -f` im Boot-Pfad beseitigt (A3/A4).** Zwei Befunde aus der zweiten Plan-Recherche, beide live belegt. **(A3)** `start-on-boot.sh` (postStartCommand, läuft bei jedem Resume) rief `secrets.sh unlock` **ohne** `SECRETS_NO_PROMPT=1` und **ohne** `</dev/null` auf — während `setup.sh` beides korrekt macht. `secrets.sh` fragt nur bei vorhandenem TTY (`[ -t 0 ]`), der Resume kann also unsichtbar auf eine Passphrase warten (die Ausgabe geht nach `/dev/null`). Jetzt dieselben zwei Flags wie in `setup.sh`. **(A4)** `opencode-server.sh` beendete Reste mit `pkill -f "opencode-bin serve"` — genau das Muster, das laut `AGENTS.md §4` die aufrufende Shell mitgetroffen hat (live passiert 2026-09-30). Ersetzt durch `timeout.sh kill "opencode-bin serve"`, das sich selbst und alle Vorfahren ausschließt; der `SCRIPT_DIR` wird aus `BASH_SOURCE` aufgelöst, damit der Helfer unabhängig vom cwd gefunden wird. **Verifiziert:** `bash -n` grün; `timeout.sh kill` mit Nicht-Muster liefert Exit 1 ohne Selbst-Treffer; `opencode-server.sh status` antwortet weiter (HTTP 200 auf 4096); `verify-codespace.sh` **30 PASS, 0 FAIL, 2 SKIP**.

- 2026-10-01 (9): **Secrets von 666 auf 600 — und der wahre Grund gefunden: eine Default-ACL, die `umask` aushebelt.** Der Härtungsplan schlug `umask 077` + `chmod 600` vor. Der erste Teil stellte sich als **wirkungslos** heraus: `/workspaces` (ext4) trägt eine geerbte POSIX-Default-ACL `USER_OBJ/GROUP_OBJ/OTHER = rwx`, die von jedem Unterverzeichnis weitervererbt wird. Sie überschreibt `umask` vollständig — live belegt: `umask 077; : > f` ergab trotzdem `666`, ein Verzeichnis `777`. `setfacl`/`getfacl` sind im Image nicht installiert. **Gelöst ohne neue Abhängigkeit:** `infra/scripts/secret-perms.sh` (von `setup.sh` vor dem Unlock aufgerufen) setzt die fünf Secret-Dateien explizit auf 600, `.runtime` auf 700 und entfernt per `python3 os.removexattr` die zu weite Default-ACL von Repo-Root + den vier empfindlichen Verzeichnissen (`config`, `.runtime`, `llm-proxies/glm2api`, `llm-proxies/zerokey/temp`). Danach greift dort wieder `umask` — verifiziert (Datei in `glm2api/` mit `umask 077` → 600). Das ist nötig, weil `temp/users.json` zur Laufzeit von der ZeroKey-App atomar neu geschrieben wird: die einmalige `chmod` allein hätte nicht gehalten, jetzt erbt der Node-Prozess `umask 077` aus `start-zerokey.sh`. **Umgesetzt an der Quelle statt nur einmalig:** `umask 077` in `secrets.sh` (`cmd_lock`), `start-zerokey.sh`, `rebuild.sh`, `start-glm2api.sh` (glm2api-`.env` trägt den echten `GLM_REFRESH_TOKEN`) und `gdrive-backup.sh` (116-MB-History-Bundle). `verify-codespace.sh` hat den neuen Check „Secrets nicht world-readable". **Verifiziert:** alle fünf Dateien 600, `.runtime` 700, alle fünf Default-ACLs entfernt, `bash -n` grün, `verify-codespace.sh` **30 PASS, 0 FAIL, 2 SKIP**.

- 2026-10-01 (8): **Vier Verifier können jetzt wirklich rot werden — ehrliche Exit-Codes statt Dauer-PASS.** Befund aus dem Repo-Härtungsplan: `verify-codespace.sh` hat 25+ Checks, aber vier davon waren Dauer-PASS, weil die dahinterliegenden Skripte immer 0 lieferten. **(a) `secrets.sh status`** endete immer auf `keys.sh status` (Exit 0) — auch bei falscher Passphrase; jetzt trägt es ein eigenes `rc` (1 bei nicht entschlüsselbarem oder fehlendem Bundle) und gibt den Exit-Code explizit zurück; der `keys.sh status`-Zusatzaufruf ist mit `|| true` entkoppelt, damit er den Bundle-Status nicht verfälscht. **(b) `keys.sh status`** endete auf einem `echo` (Exit 0); jetzt zählt jede `[LEER]`/`[FEHLT]`-Datei — auch ein leerer, in `opencode.json` referenzierter `{file:...}`-Key — und die Funktion gibt `rc` zurück. **(c) `opencode-version.sh check`** gab bei Lock- oder Installations-Abweichung nur Text aus und endete mit `return 0`; jetzt setzen `Lock != Pin` (Repo-Defekt) und `installiert != Pin` (Ursache des Dep-Churns) `rc=1`. Ein verfügbares Upstream-Update bleibt bewusst **Hinweis, kein FAIL** — sonst würde der Check nach jedem Release rot und damit ignoriert. **(d) `keys.sh doctor`** endete hart auf `return 0`; jetzt `return "$failed"`, damit `--live` einen nicht nutzbaren Provider als FAIL meldet. **Verifiziert:** Positivpfade alle Exit 0; Negativpfade getestet — `HOME=/tmp/... keys.sh status` mit fehlendem Key → Exit 1 + „STATUS: FEHLER", falsche Passphrase (config/passphrase temporär weg, `LANDSCAPE_PASSPHRASE` falsch) → `secrets.sh status` Exit 1; `bash -n` grün; `verify-codespace.sh` **29 PASS, 0 FAIL, 2 SKIP**. Erwartungshinweis: der Plan rechnete mit sofort rot werdenden Checks — im gesunden Codespace blieb alles grün, weil die Checks nur *bisher* nicht hätten rot werden können; den Beweis liefern die Negativtests. `PLAN.md` (außerhalb MAIN) ist um die korrigierte Repo-Sichtbarkeit (**public**, nicht privat) und den Stand `2aef1dc` ergänzt.
  
- 2026-10-01 (7): **Der glm2api-Live-Smoke-Test hängt jetzt an `verify-codespace.sh --live`.** `llm-proxies/scripts/smoke-test.sh` war ein funktionierender, aber von keinem Skript aufgerufener manueller Test (Befund aus (6)). Er prüft live drei API-Formate (OpenAI chat non-stream/stream, Anthropic messages, Responses) plus einen echten Tool-Call-Roundtrip über 2 Turns — genau die Tiefe, die `verify-codespace.sh` §4 bewusst **nicht** hat (dort nur Health + ein Chat-Call). Jetzt als Schritt in §9 (Provider live), **nur unter `--live`**, weil er echte Upstream-Calls macht und Minuten dauert; im schnellen Lauf als SKIP sichtbar. Schutz via `infra/scripts/timeout.sh run 400`, weil das Skript nur per-curl-Timeouts hat, kein Gesamtlimit. Der Default `SMOKE_MODEL=glm-4.7-flash` blieb: am laufenden Proxy ist das ein gültiges, schnelles Modell (82 Modelle gelistet). **Verifiziert:** Live-Lauf direkt — 8/8 Checks OK (`health`, `models (82)`, die drei Formate, `tool-call emittiert`, `tool-result verarbeitet`); Wiring im schnellen Lauf `verify-codespace.sh` → **29 PASS, 0 FAIL, 2 SKIP**; `bash -n` grün.

- 2026-10-01 (6): **Tieferer Dead-Code-Scan über das ganze Repo — alles kompiliert/lädt, eine tote Doku-Referenz gefunden.** Nachdem Go/JS in (4) einen echten Bruch hatten, wurde der Rest systematisch geprüft: `bash -n` auf allen getrackten `.sh`, `python3 -m py_compile` auf allen `.py`, `node --check` auf allen `.js` — **alles sauber**. Referenz-Prüfung: kein Live-Skript zeigt auf eine fehlende Datei; die sechs "FEHLT"-Treffer lagen **alle** nur im `infrastructure.md`-Changelog (gelöschte Historie: `autosave-daemon.sh`, `cline-models.py`, `free-models.py`, `validate-revision.sh`, `verify-verifier-selftest.sh`) bzw. waren ein `.json`-Substring-Fehltreffer (`.devcontainer/devcontainer.js` ⊂ `devcontainer.json`), und alle `aliases.sh`-Aliase existieren. **Ein echter Fund:** `llm-proxies/scripts/smoke-test.sh` verwies im Kopf noch auf das gelöschte `glm-api-audit.md` — Referenz entfernt. **Ein bewusst behaltener "Orphan":** `smoke-test.sh` wird von keinem Skript aufgerufen, ist aber ein funktionierender manueller Live-Smoke-Test (drei API-Formate + Tool-Roundtrip) und ergänzt `verify-codespace.sh`, deshalb nicht gelöscht.

- 2026-10-01 (5): **zerokeys `pnpm format` ist grün, und der pre-commit-Hook deckt jetzt alle drei Sprachen ab.** Zwei Folgeschritte aus (3)/(4). **(a) Prettier:** `pnpm format` war rot auf 5 vendorten Dateien. Ursache war ein Glob-Fehler: `.prettierignore` enthielt `engine/*.md`, was `engine/extra/instructions.md` **nicht** trifft (`*` überspringt keine Verzeichnisebene) — das Prosa-Instruktionsfile wurde geprüft, obwohl Markdown offensichtlich ausgenommen werden sollte. `engine/*.md` → `engine/**/*.md` (deckt Verschachteltes mit ab, **ohne** die Prosa umzubrechen — das war die Vorgabe). Die anderen vier sind reine JS-Formatierung (`printWidth 100`), deterministisch von `prettier --write` gesetzt; **kein** `.md` inhaltlich verändert. `pnpm format`/`lint`/`check`/`test` jetzt alle grün. **(b) Hook verbreitert:** `.githooks/pre-commit` prüft jetzt die **betroffene** Sprache statt nur glm2api — glm2api (`.py`/`.toml`) → `ruff`+`mypy`; `antigravity-proxy` (`.go`, `go.mod`/`go.sum`) → `go vet`+`gofmt -l` (read-only); MAIN-eigenes JS (`infra/**.js`) → `node --check`. Weiterhin **kein** Index-Eingriff und nur bei passenden gestagten Dateien; `printf | grep -q` bewusst durch `grep -q <<< "…"` ersetzt (unter `pipefail`+`grep -q` kann die Pipe per SIGPIPE vorzeitig schließen und die Bedingung fälschlich falsch werden). Alle vier Pfade positiv **und** negativ getestet (unformatiertes Go bzw. kaputte JS-Syntax → Exit 1). zerokeys `pnpm precommit` bleibt handgestartet (`node_modules`).

- 2026-10-01 (4): **Go- und JS-Teil aufgeräumt — und dabei zwei rote Checks gefunden.** Anlass war der Nutzerwunsch, auch Go/JS auf totes Code und fehlende Linter zu prüfen. **Go-Befund, der alles andere überwog:** `cmd/callback-server/main.go` war ein Upstream-Überbleibsel, das **gar nicht kompilierte** (7 fehlende Imports, `declared and not used: state`), von keiner Datei referenziert wurde und `/workspaces/dvcrn-antigravity-oauth-proxy` samt Google-`client_id` hardcodete. Folge: `go build ./...`, `go vet ./...` und `go test ./...` waren **rot** — der in AGENTS.md §6 dokumentierte Go-Check war damit unbenutzbar. Entfernt (dieselbe Klasse wie die 2026-10-01 (1) gelöschten `setup_oauth*.sh`: unreferenziert + hardcodeter Fremdpfad). Dazu der tote Helper `isGemini35FlashModel` (`model_resolver.go`, kein Aufrufer; `modelGemini35FlashHigh` blieb, wird in der Modell-Liste weiter genutzt). Jetzt: `go build/vet/test ./...` grün, `gofmt -l` leer. **Linting verdrahtet:** `mise` ist im Codespace **nicht** installiert, deshalb kann `mise run test` nie laufen — AGENTS.md §6 nennt jetzt die direkten `go`-Befehle, und `verify-codespace.sh` hat den neuen Check "Go-Lint antigravity (vet+fmt)" (`go vet ./...` + read-only `gofmt -l`; bewusst nicht `go fmt`, das würde schreiben). **JS-Befund:** zerokeys `pnpm lint` war **rot** — 4× `no-useless-escape` in `engine/tool-defs.js` (überflüssige `\[`/`\/` in Zeichenklassen, semantisch identisch beim Entfernen). Gefixt, `pnpm lint`/`check`/`test` jetzt grün. **Nicht angetastet, bewusst:** zerokeys `pnpm format` (prettier) ist unabhängig davon rot auf **5 vendorten Dateien** (u.a. `engine/extra/instructions.md`, Prosa) — das war schon vor dem Eingriff so (am HEAD-Stand gegengeprüft) und ein blindes `prettier --write` hätte Prosa-Instruktionstexte umbrechen können. Deshalb nur gemeldet, nicht "repariert". Neu: `verify-codespace.sh`-Check "MAIN-JS Syntax (node --check)" für den einzigen eigenen JS-Code (`infra/mcp`), ohne neues Toolchain. **Verifiziert:** `go build/vet/test ./...` grün, `gofmt -l` leer, `pnpm lint/check/test` grün, `verify-codespace.sh` **29 PASS, 0 FAIL**.

- 2026-10-01 (3): **`ruff` + `mypy` laufen jetzt im Commit statt von Hand — als pfad-scoped Git-Hook.** Anlass war der Nutzerwunsch, die in (1) eingeführten Linter zu verdrahten. **Neu:** `.githooks/pre-commit` (versioniert, `setup.sh` setzt `core.hooksPath=.githooks`). Der Hook läuft `ruff check .` + `mypy src` in `llm-proxies/glm2api/` und bricht den Commit bei Befunden ab. **Zwei Eigenschaften, die ihn in diesem shared Repo überhaupt erst tragbar machen:** (a) **pfad-scoped** — `git diff --cached --name-only` muss eine `.py`/`.toml` unter `llm-proxies/glm2api/` zeigen, sonst Exit 0; Commits an zerokey/Infra/Doku kostet er nichts. (b) **kein Index-Eingriff** — kein `git add`, kein `ruff --fix`, kein `--no-verify` im Aufrufer; er liest nur. Genau das war die Lehre aus dem 2026-09-29 entfernten zerokey-`.githooks` (machte `git add` über alle Änderungen und bog den Hookpfad des Haupt-Repos um) — der neue Hook tunt beides nicht. Timer kommt von `infra/scripts/timeout.sh` (AGENTS.md §4), der Hook darf nie hängen. Aktivierung bewusst in `setup.sh` statt `postinstall`: ein `postinstall` läuft bei jedem `pnpm install` und würde den Wert erneut aus einem Unterordner setzen. **Verifiziert:** Skip-Pfad (nichts glm2api gestaged → Exit 0, keine Ausgabe) und Run-Pfad (leere `.py` gestaged → `ruff` + `mypy` grün, Exit 0) je direkt getestet; `bash -n` auf Hook/setup/verify; `verify-codespace.sh` **27 PASS, 0 FAIL** mit neuem Check "Lint-Hook verdrahtet". `AGENTS.md` §6 um die Automatik-Zeile ergänzt.

- 2026-10-01 (2): **Die glm2api-Audit-Doku und `structure.md` sind doch raus.** Direkte Fortsetzung des Eintrags darunter: was dort als "nicht gelöscht" begründet stand, wurde auf Nutzerwunsch doch entfernt — der Audit (`glm2api-revision.md`, 116 K, plus `glm2api-revision-anhang/`, 7 Dateien/200 K) war statisch und nur noch ein Erinnerungsstück an den Stand vom 28.09., `structure.md` nur eine Kurzfassung desselben Codes. **Mitgelöscht statt stehen gelassen:** der Bundle-Bau hätte sonst gebrochen — `build-bundle.sh:34` kopierte `structure.md` in einer festen `for`-Liste unter `set -euo pipefail`, der Eintrag ist entfernt. Drei Verweisstellen nachgezogen: `glm2api/README.md` (Abschnitt "Architektur & Betrieb" → "Betrieb"), `scripts/bundle/README.md` (Baum-Zeile + Detailverweis) — die dritte ist `bundle/README.md` selbst, das ebenfalls ins Bundle kopiert wird. Die Changelog-Einträge des 2026-09-27, die `glm2api-revision.md` als bewusst geduldeten Proxy-Audit beschreiben, bleiben **unangetastet** (Historie wird nicht umgeschrieben); nur der gestrige 2026-10-01-Eintrag desselben Tages wurde auf den tatsächlichen Ausgang korrigiert. **Verifiziert:** `build-bundle.sh` läuft grün durch (Bundle-Verifikation OK), 1750 Tests grün, `ruff`/`mypy` je Exit 0.

- 2026-10-01: **Blindlast raus, Python-Code bekommt `ruff` + `mypy`, und die Nested-`AGENTS.md` driften nicht mehr.** Anlass war der Nutzerwunsch, gegen Altlasten/Duplikate im Repo vorzugehen. **Gelöscht:** die vier toten `antigravity-proxy/setup_oauth*.sh` (`_final`/`_fixed`/`_full`/plain, zusammen 494 Zeilen, von keinem Skript referenziert — die plain-Version hardcodete `/workspaces/dvcrn-antigravity-oauth-proxy` und nutzte `pkill -f`, das AGENTS.md §4 verbietet) und das 9,8-MB-ELF `antigravity-proxy/auth` (siehe Infra-Soll). **`ruff` + `mypy` eingeführt:** beide exakt in `llm-proxies/glm2api/pyproject.toml` gepinnt (`ruff==0.14.4`, `mypy==1.18.2`, uv.lock nachgezogen; Lauf: `uv run ruff check .` / `uv run mypy src`). `ruff` (Default E4/E7/E9/F) fand 25 echte Leichen (unbenutzte Imports/Variablen), `src/` jetzt clean. `mypy` ist **gezielt** konfiguriert, nicht global: ungefiltert 62 Fehler, davon ~50 reines `object`-Rauschen (bewusst dynamische JSON-Dicts) — deshalb nur die aussagekräftigen Codes aktiv (`no-redef`, `possibly-undefined`, …). Es fand drei doppelte Definitionen in `translator.py`; `found` (harmlose Zweideutigkeit über zwei Branches) umbenannt, `text_parts`/`reasoning_parts` war echte **Redundanz** (Liste zweimal gesetzt) und wurde zusammengeführt. Verifiziert: **1750 Tests grün**, `ruff`/`mypy` je Exit 0. **Eine Falle, die `ruff --fix` selbst stellte:** `translator.py` re-exportierte `BLOCKED_NATIVE_TOOL_NAMES` nur für `glm_client`/`test_translator`; `ruff` wertete das als unbenutzten Import (F401) und entfernte es, die Testsammlung brach mit `ImportError`. Lehre: ein Re-Export ist für `ruff` ein toter Import, solange er nicht als solcher markiert ist — die zwei Konsumenten importieren jetzt direkt aus `glm2api.utils.tool_protocol`. **Nested-`AGENTS.md` ruhiggestellt:** `antigravity-proxy/AGENTS.md` war unverändert upstreams `CLAUDE.md` (Überschrift `# CLAUDE.md`, Port 9877 statt 9878), `zerokey/AGENTS.md` **widersprach sich selbst** (Kopf: `.githooks/pre-commit` entfernt; Fuß: listete es als vorhanden) — beide mit MAIN-Hinweis/Realität versehen. `verify-codespace.sh` verlangt für jedes Nested-`AGENTS.md` den MAIN-Hinweis und prüft Client-Kopien rekursiv — aber **symlink- und vendored-bewusst**: im Root sind `GEMINI.md`/`CLAUDE.md`/… verboten, in vendored Unterordnern ist genau eine Quelle erlaubt (ein File oder ein Symlink-Verbund, wie `antigravity-proxy/`: `CLAUDE.md` echt, `AGENTS.md`/`GEMINI.md` Symlinks darauf). **Zunächst nicht gelöscht, im nächsten Arbeitsgang desselben Tages doch entfernt:** `glm2api/glm2api-revision.md` + `-anhang/` (bewusst als Proxy-Audit geduldet, Changelog 2026-09-27) und `structure.md` (wird von `build-bundle.sh:34` ins Bundle kopiert) — siehe den Eintrag darüber. `AGENTS.md` um Verifikationsbefehle, Repo-Karte und Anti-Drift-Regel ergänzt.

- 2026-09-30: **opencodes Neben-Requests landen nicht mehr in der Arbeits-Konversation — die wahrscheinlichste Ursache für „Sessions sind kaputt".**

  **Symptom.** `ses_f0b8b5273ffepn1uTEI3d3pf7P` (Titel „Hey – kurzer Plausch"): User sagt `hey`, das Modell antwortet **`Quick check-in`** — 4 Output-Tokens. Kein Fehler, kein Absturz, nur ein wertloser Turn. Dasselbe Muster in älteren Läufen: `Repository-Analyse: Struktur, LLM-Proxies und Infrastruktur von /workspaces/MAIN` (12 Tokens) und `Komplette Repository-Analyse von /workspaces/MAIN` (12 Tokens). **Das sind Titel, keine Antworten.**

  **Ursache, aus dem Binary belegt statt geraten.** `strings` auf `opencode-bin` 1.18.32 zeigt den Neben-Request wörtlich:

      stream({ agent: title, system: [], small: true, tools: {},
               messages: [{ role: "user", content: "Generate a title for ..." }] })

  **`system: []`** — der Title-Request hat **keine System-Nachricht**. `utils/session-classifier.js` prüfte aber zuerst `messages[0].role`:

      if (!first || first.role !== 'system' || ...) return true

  Keine System-Nachricht ⇒ Rückgabe `true` ⇒ **wird als Arbeits-Turn eingestuft** ⇒ hängt an derselben ChatGPT-Konversation wie die echte Arbeit. Live bestätigt: um 22:34–22:35 kein einziges `[SERVER] EPHEMERAL CALL`, obwohl opencode `agent=title` geschickt hat; der letzte EPHEMERAL-Eintrag lag bei Logzeile 11060, der letzte POST bei 18614. Der Folge-Turn erbt den Titel-Kontext — und antwortet auf „hey" mit einer Titel-Formulierung.

  **Fix.** Erkennung der Neben-Requests **vor** der System-Prüfung und über **alle** Nachrichten statt nur der letzten (der Marker steht in der einzigen User-Nachricht, nicht zwingend in der letzten):

      /generate a title|summari[sz]e|condense the (history|conversation)/i

  Das deckt Titel **und** Compromise ab und fasst nichts an, was vorher klassifiziert wurde. Die offene Default-Zeile `if (ide === 'opencode') return true` bleibt unangetastet — sie ist für unbekannte Identitäten die sichere Ausweichregel.

  **13/13 Regressionstests** in `scripts/test-session-classifier.js`, davon bewusst einer als Grenzfall dokumentiert: ein *Arbeitsauftrag*, der das Wort „summarize" enthält, wird als Neben-Request eingestuft. Das ist der bewusste trade-off — eine echte Session zu verlieren ist teurer als ein Neben-Request, der wie eine Session behandelt wird. Falsch-positiv kostet eine laufende Session, falsch-negativ verfälscht den Modellkontext der nächsten Runden. Zusätzlich abgesichert, dass ein Terax-Arbeitsturn real bleibt.

  **Live-Beleg.** Nach dem Neustart: `EPHEMERAL: 1` im Titel-Request (vorher 0), danach 6 Tool-Calls, alle `completed`, 0 Fehler, 0 Kompaktierung.

  **Ein bewusst verworfener Erklärungsversuch:** zuerst lag der Verdacht auf Prompt-Verschmutzung durch die Kompaktierung. Das war die Beobachtung aus den Fehlläufen, aber der 403/429-Blockade-Vorfall (`chatgpt flagged this device/IP`) hat dazwischengefunkt — die Live-Gegenprobe fehlt deshalb noch. Der Title-Befund ist davon unabhängig und für sich belegt.

  **Weiterhin offen:** der Drift — ~10 % der Turns liefern unbrauchbares. Der Title-Befund erklärt die *wiederholt beobachteten Titel-Antworten*, nicht die Fälle, in denen das Modell mitten in der Arbeit driftet.
- 2026-09-30: **`limit.output` 8000 → 2000: die Kompaktierung ist damit rechnerisch ausgeschlossen, nicht nur unwahrscheinlich.**

  **Nutzerentscheidung:** die Kompaktierung soll gar nicht einsetzen. Das ist die richtige Wahl, weil opencodes Summarizer (`agent=compaction`) **Tool-Calls verbietet**, ZeroKeys `instructions.md` sie dem Modell aber ausdrücklich vorschreibt — jeder Kompaktierungslauf endet mit `Tool call not allowed while generating summary`. ZeroKeys *eigene* Kürzung ist dagegen unkritisch: `limitPrompt` schneidet middle-out und behält Kopf (Auftrag) und Tail (letzte User-Nachricht, neueste Tool-Ergebnisse).

  **Die Rechnung.** opencode kompactiert ab `context − output` Tokens. Damit die Kürzung immer zuerst greift, muss gelten:

      (context − output) × 4 > promptLimit
      (16000 − 2000) × 4 = 56.000 Zeichen  >  49.936 Zeichen   ✓

  Bei `output = 8000` war es umgekehrt (32.000 Zeichen < 49.936), also griff die Kompaktierung **vor** der Kürzung — die Reihenfolge war genau verkehrt, und der erste Changelog-Empfehlung, opencode solle „vor ZeroKeys Kürzung kompactieren", war ebenfalls falsch. **Diese Empfehlung ist hiermit korrigiert.** Die Grenze kippt bei `output = 3500` (50.000 Zeichen == promptLimit), deshalb 2000 mit Marge.

  **Zur Prüfung gemacht.** `check-proxy-budget.py` wertet die Regel jetzt als **Fehler**, nicht als Hinweis: liegt die Schwelle vor der Kürzung, meldet der Check das mit dem Sollwert (`output muss < 3500 sein`). **7-Fälle-Matrix** inklusive der beiden Kipp-Punkte 3000 (grün) und 3500 (rot).

  **Live.** Mit `output=2000` lief ein voller MAIN-Analyse-Lauf **ohne jede Kompaktierung** durch. Er endete an etwas anderem: das Modell lieferte einen leeren Turn, der Guard griff wie vorgesehen (`empty-turn (Versuch 1/2)`), ein zweiter Versuch und danach ein `handoff-text` — am Ende blieb nichts Brauchbares. Das ist der offene Drift, nicht die Kompaktierung: 4 Guard-Arten, aber 10 % der Turns sind nicht-deterministisch unbrauchbar und werden nur **abgefangen**, nicht beseitigt.
- 2026-09-30: **`limit.output` war die echte Ursache — und ein zweiter, unabhängiger Defekt ist damit sichtbar geworden (offen).**

  Der unmittelbar vorherige Changelog-Eintrag gilt als überholt; **seine Diagnose war falsch**. Kurzfassung der Korrektur: `limit.output` stand auf **16.384** neben `limit.context` = **16.000**. opencode rechnet die Kompaktierungsschwelle als `context − output`; negativ heißt nicht positiv, die Kompaktierung lief **bedingungslos bei jedem Turn**, nicht „nach jedem Turn, weil reserved zu hoch". `reserved` war ein zweiter Fehler mit demselben Symptom, nicht der Auslöser. Fix `output` → **8.000**, Schwelle jetzt 8.000 Tokens bei gemessenen Prompts von ~1.200 (15 %). Details und die 7-Fälle-Matrix im Eintrag darüber; `0b84c38` ist gepusht und wurde bewusst nicht umgeschrieben (destruktiv, laut `AGENTS.md` rückfrage-pflichtig).

  **Live-Beleg der Wirkung, und was erst dadurch auffiel.** Mit `output=8000` greift die Kompaktierung erst bei **8.739** Input-Tokens (Turn-Verlauf: 794 → 2.474 → 8.739), also **nach drei Runden echter Arbeit** — vorher war sie bei **794**, in der ersten Runde. Damit läuft die normale Analyse sauber: 6 → 5 → 6 Tool-Calls, alle `completed`.

  **Der zweite Defekt: Compaction bricht opencode weiterhin ab.** Sobald die Schwelle erreicht ist, startet opencode seinen Summarizer (`agent=compaction`) und **verbietet dort Tool-Calls**. ZeroKey injiziert die vollen Agenten-Instruktionen („emit MHI directives"), das Modell hält sich daran, und opencode bricht den Lauf ab:

      Tool call not allowed while generating summary: read

  Das ist dieselbe Fehlerklasse wie beim Loop, nur eine Ebene tiefer: ZeroKeys Prompt-Vertrag kennt opencodes interne, nicht-werkzeugfähige Phasen (Titel, Compaction) nicht.

  **Messung statt Annahme.** `ZEROKEY_DEBUG_TOOLS=1` schaltet im Pipeline-Setup eine Messzeile frei (`tools=… toolCalling=… raw=… msgs=…`). Ergebnis:

  | Request | `tools` | msgs |
  |---|---|---|
  | Titel | `undefined` | 3 |
  | Build | **16** | 2 |

  opencode sendet die Werkzeugliste also **sehr wohl** — 16 Stück, sie ist nur beim Titel-Request leer. Die naheliegende Regel „keine Werkzeuge angeboten → keine MHI-Anweisung" ist damit zwar für den Titel richtig, war als alleinige Bedingung aber **noch nicht der Fehler**; das Signal, das die Compaction sicher von einem normalen Turn trennt, ist damit **nicht** gefunden.

  **Ein Fix-Versuch wurde zurückgenommen, weil er den Normalpfad zerstörte.** Mit „leeres `tools` → Raw-Modus" verlor der Build-Turn die MHI-Anweisung: der Lauf lieferte nur `Komplette Repository-Analyse von /workspaces/MAIN`, 12 Output-Tokens, Ende. Vermutlich hat der Raw-Pfad auf dem Title-Request den Session-Zustand so verändert, dass der Folgeturn leer blieb. Kein halbfertiger Stand im Repo: Verhalten entfernt, zugehöriger Test (`scripts/test-no-tools-request.js`) und der Eintrag in `package.json` zurückgenommen, Suite wieder 4/4 grün. **Offen, mit Messweg:** der Debug-Schalter bleibt stehen, weil er die Frage beantwortet.

  **Nebenbefund zum Werkzeugkatalog:** ZeroKey braucht die Werkzeugliste des Clients nicht — `engine/tool-defs.js` liefert einen eigenen Katalog pro IDE. Deshalb ist „der Client sendet keine Werkzeuge" als Signal untauglich, sobald ein Client kompatibel ist, aber seinen Katalog nicht spiegelt.
- 2026-09-30: **KORREKTUR: die Ursache des Resume-Loops war `limit.output`, nicht `compaction.reserved` — die Diagnose in `0b84c38` war falsch.**

  **Was falsch war.** Der Commit `0b84c38` und der Changelog-Eintrag `9f53b30` nennen `compaction.reserved` als Ursache: „opencode kompactiert nach JEDER Runde, das Modell liest Continue-if-you-have-next-steps als Resume-Marker". Der Reserve-Wert war tatsächlich zu hoch (15.000 von 16.000 Tokens), aber er war **nicht** der Auslöser. Die Änderung auf 2.000 beseitigte den Dauerzustand nicht, sie verschob ihn nur auf „nach step 1".

  **Was die echte Ursache war.** `limit.output` stand auf **16.384** neben `limit.context` = **16.000**. opencode rechnet die Kompaktierungsschwelle als `context − output`; das Ergebnis ist **negativ**, die Schwelle ist damit nicht positiv und die Kompaktierung lief **bedingungslos** — unabhängig vom Füllstand, bei jedem Turn. `reserved` war ein zweiter, unabhängiger Fehler mit demselben Symptom, nicht die Ursache. Fix: `limit.output` 16.384 → **8.000** (Schwelle 8.000 Tokens, gemessene Prompts ~1.200, also 15 % Auslastung).

  **Isoliert belegt, eine Variable zur Zeit (context jeweils 16000):**

  | output | reserved | beobachtetes Verhalten |
  |---|---|---|
  | 4.000 | 2.000 | `agent=build`, **keine** Kompaktierung |
  | 16.384 | 2.000 | `agent=compaction` nach step 1 |
  | 16.384 | 15.000 | Kompaktierung nach jedem Turn |

  **Live-Nachweis der Wirkung.** Vorher: Runde 1 = 6 Discovery-Calls, dann Abbruch mit `Tool call not allowed while generating summary: read` — opencode verbietet Tool-Calls während der Summary, und ZeroKeys `instructions.md` schreibt sie dem Modell ausdrücklich vor. Nachher: Runde 1 = 6 Calls, danach **keine** Kompaktierung, der Turn wuchs auf 5.881 Input-Tokens und endete mit `stop` — unter der 8.000er-Schwelle, also ohne Kompaktierung.

  **Was am Check falsch war.** `check-proxy-budget.py` aus `9f53b30` prüfte `reserved` gegen `context` und war deshalb blind für `output`. Ergänzt ist jetzt `output < context`, plus die Gleichheitsgrenze: bei `output == context` ist die Schwelle **exakt 0**, opencode kompactiert also ebenfalls bei jedem Turn mit mehr als 0 Token — auch das war vorher falsch und ist getestet. **7-Fälle-Matrix** inklusive Reproduktion des Originalzustands.

  **Zwei Testerwartungen von mir waren dabei falsch, nicht der Code:** den Fall `output == context` habe ich zuerst als PASS erwartet (die Schwelle ist aber 0, nicht positiv), die Matrix erwartete dort fälschlich Erfolg. Beides ist im Matrix-Lauf sichtbar gewesen und wurde korrigiert, nicht wegkommentiert.

  **Warum die Historie nicht umgeschrieben wird:** `0b84c38` ist gepusht. Umschreiben (`rebase`/`force-push`) wäre destruktiv und steht laut `AGENTS.md` unter Rückfrage-Pflicht. Diese Korrektur steht deshalb als eigener Eintrag, nicht als Ersetzung — der Commit-Text bleibt als Beleg für den damaligen Irrtum stehen.

  **Unberührt gültig:** `pnpm test` und der Eintrag `f514251` — Stillstands-Erkennung und usage-Meldung hängen nicht an dieser Konfiguration. Der `reserved`-Wert 2.000 bleibt sinnvoll, ist aber nicht die heilende Maßnahme.

- 2026-09-30: **Stillstands-Erkennung verallgemeinert und echte Token-Zahlen gemeldet.** Die zwei Punkte aus dem Testlauf, die keine Upstream-Requests brauchten.

  **5. `engine/ask-guard.js`: `isStalledReadRound` + `updateReadMemory`.** `isDuplicateToolRound` erkennt nur eine Wiederholung **gegenüber der Vorrunden-Runde** (>= 60 % Überlappung). Der Live-Loop war genau so gebaut, aber ein pendelndes `A,B → B,C → A,B` hat gegenüber der jeweiligen Vorrunde nur 50 % Überlappung und wäre durchgerutscht. Die neue Regel merkt sich **alle gelesenen Ziele der Session** und feuert, wenn eine Runde ausschließlich bereits bekannte Ziele liest und sich seitdem nichts geändert hat. Ein Round mit **einem einzigen** neuen Ziel gilt als Fortschritt. Der Mutationsschalter ist der Grund, warum das sicher ist: nach einem `write`/`cmd` ist erneutes Lesen echte Arbeit („Datei schreiben, zurücklesen, prüfen") und erlaubt, danach wieder Stillstand. Belegt in E2E-Fall O über **drei getrennte Requests**, weil das Gedächtnis am Session-Objekt hängt und ein Pipeline-Objekt pro Request neu ist. **Zwei eigene Testfehler dabei:** (a) ich hatte das Gedächtnis *vor* der Prüfung gefüllt — in der Pipeline läuft die Prüfung *davor*, also feuert bereits die **zweite** identische Runde, nicht die dritte; (b) die Gegenprobe `A,B` gegen `B,A` war kein Gegenbeweis, das ist derselbe Satz mit 100 % Überlappung. Echtes Unterscheidungsbeispiel ist `A,B → B,C → A,B`.

  **6. `engine/usage.js`: ZeroKey meldet jetzt echte Zahlen statt `{}`.** ZeroKey fragt ChatGPT über eine Web-Session ab, nicht über die API — der Upstream liefert keine usage, deshalb stand in **jedem** Turn `tokens: 0`. Der Client konnte sein Kontext-Wachstum nicht sehen, und genau diese Blindheit hat die Kopplung `compaction.reserved` vs. `promptLimit` zwei Tage unentdeckt leben lassen. `limitPrompt` merkt seine Kennzahlen jetzt in `compiler.lastPrompt` (beide Zweige, Truncation inklusive `droppedTurns`), die Pipeline zählt die Modell-Ausgabe in `_modelChars` und meldet `prompt_tokens`/`completion_tokens`/`total_tokens` im letzten SSE-Chunk. Es ist eine **Schätzung** (4 Zeichen/Token, Code ist dichter) und steht so im Modul-Docstring. `lastPrompt` ist außerdem der Punkt, an dem die Zahlen überhaupt verfügbar werden — vorher wurden sie geloggt und weggeworfen. Geprüft: 4.649 Zeichen werden zu 1.162 Tokens, fehlende Daten ergeben 0 statt `NaN`, 5 Zeichen runden auf 1 statt 0.

  **Nebenbei korrigiert:** `git status` nach dem Lauf war nicht sauber — `npx prettier --write engine/*.js` hatte `instructions.js`, `tool-defs.js` und `triggers.js` mitformatiert, drei Dateien außerhalb des Auftrags. Zurückgenommen; der Commit enthält nur `ask-guard.js`, `compiler.js`, `pipeline.js`, `usage.js` und die zwei Testskripte.

  **Weiterhin nicht live verifiziert:** beide Punkte sind durch Unit- und E2E-Tests belegt (pnpm test grün, prettier/eslint sauber), aber nicht gegen den echten Upstream — das Stundenlimit läuft bis etwa 19:25Z.

- 2026-09-30: **Vier Follow-ups zum Loop-Bug, alle aus dem Testlauf abgeleitet statt geraten.** Nach dem Fix von `0b84c38` vier offene Punkte, deren Grundlage jeweils eine Beobachtung war, keine Vermutung.

  **1. `infra/scripts/check-proxy-budget.py` — die Kopplung wird jetzt geprüft statt geglaubt.** Die eigentliche Fehlerklasse war: `limit.context`/`compaction.reserved` (Tokens, `.opencode/opencode.json`) und `promptLimit` (Zeichen, `providers/chatgpt/config.js`) sind zwei von Hand gepflegte Zahlen an zwei Orten, die zusammenpassen **müssen** und sich nicht selbst prüfen. Sie waren schon zweimal auseinander (128k → 16000). Zwei Brüche: `reserved >= context` (kompaktiert nach jeder Runde) und Arbeitsfenster < 50 % des Kontexts. **Der zweite fehlt in der ersten Fassung des Checks** — mit `reserved=15000` meldete er „PASS: Kopplung stimmt (Fenster 1000 von 16000)". Die Zeichen-Prüfung greift dort nicht, denn 1000 Tokens liegen *unter* dem Budget; gebrochen war die Häufigkeit der Kompaktierung, nicht die Menge. Jetzt mit Mindestfenster. Ein Heraufsetzen von `context` über das doppelte Budget wird als Fehler gewertet, leichtes Überschreiten nur als Hinweis — `limitPrompt` schneidet dafür middle-out und rettet Kopf und Tail. **8-Fälle-Matrix belegt** (grün bei 2000/16000, 7900/16000; rot bei 15000/16000, 9000/16000, context 200k und 120k). Die Logik liegt in einem eigenen Skript statt als Heredoc in `bash -c '…'` — das war zweimal in Quote-Fehler gelaufen und machte die Prüfung unprüfbar.

  **2. `utils/users-file.js` — eine ChatGPT-Sperre überlebt jetzt einen Neustart.** Beobachtung: Nach dem Stundenlimit (`cooldown 3591.7s`) stand in `users.json` `waitUntil: None`, weil der 429-Pfad nur den flüchtigen `_state` in `utils/rate-limiter.js` setzt. Ich hatte den Proxy neu gestartet, die Sperre war weg, der nächste Request lief wieder ins 429 statt zu warten. `buildChatGPTRouter` bekam `userData` bereits, ignorierte es aber (`_userData`). Jetzt setzt der Catch-Block bei 429 mit `cooldownMs` `waitUntil`/`waitReason` und schreibt atomar (tmp + rename, wie der SessionSelector). **Belegt:** Sperre gesetzt, Cookies unversehrt (8591 Zeichen), nach simuliertem Neustart noch 300 s vorhanden. Fehler werden geloggt, nicht geworfen — ein Persistenzfehler darf einen laufenden Request nicht abbrechen.

  **3. `fakeStream` verlangt Block-Strings.** Ein Testfall verschachtelte eine Ebene zu viel, drei Tool-Calls wurden zu *einem* kommagetrennten Payload. Der Parser tat korrekt, der Test prüfte die falsche Sache und meldete grün — mit falscher Aussage. Jetzt bricht er mit konkreter Meldung ab. Regressionsprobe: exakt der alte Fehlerfall schlägt jetzt laut fehl.

  **4. `start-zerokey.sh` wartet auf das tatsächliche Ende des Prozesses.** `kill; sleep 1` war unzuverlässig — der Port war beim Start des neuen Servers noch belegt. Neu `stop_pid()` mit 10 s SIGTERM-Wartezeit, SIGKILL als Notbremse, 5 s danach, harter Fehler statt blind weiterzumachen. Live geprüft: laufender Proxy wird erkannt (kein Doppelstart), Neustart mitten im Betrieb ergibt neue PID und gesundes `/health`.

  **Nicht ausgeführt:** `verify-codespace.sh` wurde beim Abschluss **zweimal unterbrochen hängen gelassen** (Netzwerk-Checks, nicht der neue Check). Verifiziert wurde stattdessen einzeln: Budget-Check in 8 Konfigurationen, Cooldown-Persistenz inkl. Cookie-Unversehrtheit, `fakeStream`-Regression, `stop_pid` im echten Neustart, `pnpm test` grün, prettier/eslint sauber. Lesson: die volle Suite nicht wiederholen, um eine Einzelheit zu prüfen — sie ist kein Testwerkzeug, sondern ein Betriebs-Smoke-Test.

- 2026-09-30: **`infra/scripts/timeout.sh` — Stoppuhr und selbstsicheres `kill` für Bash-Aufrufe.** Anlass waren zwei Hänger am selben Tag, beide live und beide mit demselben Muster: ein Bash-Aufruf brach sich **selbst** ab und lief danach in den 120-s-Tool-Timeout. (a) `pkill -f "opencode run"` — `-f` matcht die volle Kommandozeile, und die Kommandozeile der aufrufenden Shell **enthält das Muster selbst**; der Aufruf tötete daher seinen eigenen Aufrufer. (b) Ein im Hintergrund gestartetes Kommando, das stdout/stderr nicht umleitet, erbt die Pipe des Bash-Tools; das Tool wartet dann auf Leser, die nie EOF bekommen, und hängt bis zum Timeout. Skript mit zwei Aufträgen: `run <sekunden> <kommando>` (hartes Wall-Clock-Limit, `setsid` + coreutils-`timeout --foreground`, **Exit 124** = Zeitüberschreitung, alle anderen Exit-Codes und die Ausgabe kommen unverändert durch) und `kill <muster>` (`-f`-Semantik, aber sich selbst und **alle Vorfahren bis PID 1** ausgeschlossen — der Selbstschutz greift auch gegen die eigene Kommandozeile). `--foreground` ist nicht Kosmetik: ohne ihn legt coreutils-`timeout` für das Kommando eine *eigene* Prozessgruppe an, und das Aufräumen per `kill -- -$child` verfehlt sie — im ersten Test blieben dadurch zwei verwaiste `sleep` zurück. Eigener Watchdog-Subshell wurde bewusst verworfen, weil er genau die `Terminated`/`Killed`-Jobmeldungen erzeugt, die echte Fehlerausgabe überdecken. `./infra/scripts/timeout.sh selftest` prüft fünf Zusicherungen (Timeout greift, keine Waisen, Ausgabe/Exit-Code durchgereicht, `kill` trifft das Ziel, `kill` trifft den Aufrufer nicht) und läuft in ~8 s. `AGENTS.md` Abschnitt 4 verweist jetzt darauf.

- 2026-09-29: **ZeroKey ist jetzt wirklich offiziell: beide alten Checkouts unter `/workspaces` gelöscht, die Historie liegt als Bundle im Repo.** Nach der Übernahme stand `downloaddoctor-zerokey` noch als Nebenstand herum — und mit ihm `zerokey-v2.0`, ein **zweiter** Checkout desselben Upstream-Repos, sieben Commits älter. Der war keine unbenutzte Altlast, sondern eine echte Verwechslungsgefahr: beide heißen „zerokey", beide haben denselben Remote, und v2.0 sieht auf den ersten Blick vollständig aus. **Belegt wurde zuerst, dass nicht versehentlich der falsche übernommen wurde:** die Upstream-Historie ist *eine* Linie, `4d635ab` (v2.0-HEAD) ist ein **Vorfahr** von `11ea0bf` (übernommener Stand). Inhaltlich 22 Unterschiede, alle in Richtung neu: `engine/ask-guard.js` plus vier Testdateien und `start.sh`/`stop.sh` gibt es nur in MAIN, und `instructions.md` hat in MAIN die Sprach-Regel, die Autonomie-Regel, `path=`-Pflicht bei glob/grep und `ask` auf echte Blocker eingeschränkt — die Upstream-Fixes aus `d8b5a59`, die v2.0 noch nicht hatte. v2.0 hat dagegen noch `d:\Project\foo` in den Beispielen und die alte AGENTS.md-Speicher-Regel. **MAIN ⊃ v2.0**, es fehlt nichts. **Absicherung vor dem Löschen, verifiziert statt behauptet:** `git bundle create --all` (198 Commits, alle Branches, Tags v0.1.0–v0.3.0, 797 K) nach `llm-proxies/zerokey/upstream-history.bundle`, dann **aus dem Bundle in ein Temp-Verzeichnis geklont und der Inhalt gegen MAIN diffed** — 198 Commits, HEAD `11ea0bf`, null Unterschiede außer den drei bewussten Abweichungen (siehe Tabelle im ZeroKey-Abschnitt). Erst danach gelöscht. **Rückweg:** `git clone llm-proxies/zerokey/upstream-history.bundle <ziel>`. **Live gegengeprüft, nicht nur geprüft ob die Datei weg ist:** Proxy aus MAIN neu gestartet, `/health` ok, echter opencode-Request liefert 3 Tool-Calls — mit den beiden gelöschten Verzeichnissen existiert er weiter. Nebenbefund: `origin/main` ist **lesbar** (`git fetch` klappt, nur `push` scheitert an `403`), damit war „nichts vom Upstream verpasst" prüfbar: `origin/main` endet bei `4d635ab`, das ist ein Vorfahr des übernommenen Stands, es fehlt also kein Upstream-Commit.


- 2026-09-29: **ZeroKey offiziell ins Repo aufgenommen — der dritte LLM-Proxy war konfiguriert, aber nirgends gepflegt.** Anlass war die Fehlersuche an `ses_f16591f3…`, `ses_f16212e6…` und `ses_f15f39a8…`: der ChatGPT-Proxy auf Port 7250 hat drei aufeinanderfolgende Analyse-Sessions abgebrochen (Details im ZeroKey-Abschnitt oben und in `llm-proxies/zerokey/AGENTS.md`). **Der Fund, der unabhängig vom Bug zählte:** `infrastructure.md` führte `downloaddoctor` in der Provider-Tabelle mit *„128k Context"* — der Proxy erzwingt aber `promptLimit = 50_000` **Zeichen** (~12,5k Tokens, `providers/chatgpt/config.js`). Faktor 6,4 zwischen dem, was opencode glaubte, und dem, was der Proxy akzeptierte. `opencode.json` behauptete dieselben 128k, deshalb hat opencode **nie kompactiert** und ungebremst Historie geschickt, die der Proxy dann hart abschnitt. `limit.context` steht jetzt auf **16000**. **Drei Fehler, alle live reproduziert, nicht am grünen Unit-Test erkannt:** (a) `limitPrompt` schnitt überlange Prompts mit `slice(0, limit)` — behält den **Anfang** und wirft den **Schwanz** weg, und im Schwanz stehen die letzte User-Nachricht und die neuesten Tool-Ergebnisse. Das Modell verlor den Auftrag und fiel auf generische Rückfragen zurück; bei 78 kB waren 28 523 Zeichen weg, darunter wörtlich das „mach weiter". A/B gegen den echten Upstream: alter Code → *"What would you like me to do with it?"*, neuer Code → vollständige Analyse. (b) `readSSE` rief `onDone` bei `[DONE]` **außerhalb** von `finishOnce` — doppelter Aufruf, und ein werfender Handler entkam als unbehandelte Rejection; nötig geworden, weil der Ask-Guard aus `onDone` heraus retryt. (c) Ein Detektor-Muster matchte `key` ohne Wortgrenze und ließ dadurch genau die häufigste Drift-Frage („Zero**Key**") durch. **Die Leerlauf-Ursache ist ausdrücklich nicht behoben:** das Modell driftet gelegentlich aus dem Agent-Modus. Abgefangen werden jetzt die drei Ausbruchsformen (generische Frage als `⟦ask⟧`, leerer Turn, Drift als Text) plus der abgeschnittene Prompt — jeder mit eigenem Retry-Nudge, einmalig begrenzt, und **echte Blocker kommen durch** (live gegengeprüft: *„Which MHI command failed and what path or parameters should be corrected?"* nennt einen konkreten Artefakt und wurde nicht unterdrückt). **Übernahme ins Repo:** Code aus `/workspaces/downloaddoctor-zerokey` nach `llm-proxies/zerokey/` (117 Dateien via `git archive HEAD`, damit exakt der committete Stand und kein Runtime-State); `start-zerokey.sh` nach dem Muster von `start-glm2api.sh`; verdrahtet in `setup.sh` + `proxy-watchdog.sh` + `verify-codespace.sh`; **`postinstall` und `.githooks/` entfernt** — beide hätten das geteilte MAIN-Repo beschädigt (der erste biegt `core.hooksPath` des Haupt-Repos um, der zweite macht `git add` über alle geänderten Dateien); die ChatGPT-Cookies laufen jetzt über `secrets.sh` wie der ChatGLM-Token. **Ein Bug, den das Startskript erst im eigenen Betrieb zeigte:** `node ... >> "$LOG" 2>&1 &` ließ die aufrufende Subshell die stdout-Pipe des Aufrufers erben — bei `start-zerokey.sh | tail` wartete `tail` ewig auf EOF, während der Proxy längst lief. Das hätte **den Watchdog blockiert**, weil er das Skript aus einer Umleitung startet. Der Subshell-Body wird jetzt komplett umgeleitet. Live verifiziert: Proxy läuft aus `llm-proxies/zerokey`, `/health` ok, echter opencode-Request liefert Tool-Calls.

- 2026-09-28: **Befund-Abarbeitung aus dem Main-Analyse-Run (read-only
  `opencode run` über das gesamte Repo, Log `.runtime/opencode-main-analysis.log`).
  Drei Bereinigungen, zwei bewusste Ausnahmen, ein Code-Fix:**
  - **`config.json` gelöscht.** Inhalt war ein leeres `{}` (Autosave-Commit vom
    17.09.), kein Skript und keine Doku referenziert es, der Layout-Abschnitt
    kennt es nicht — herrkunftsloses Artefakt, weg damit.
  - **`save.sh` committet jetzt signiert.** Bis hierher lief jeder reguläre Commit
    über `git -c commit.gpgsign=false` — der in `setup.sh` (2026-09-27) sauber
    gebaute SSH-Signier-Pfad war für den Normalpfad wirkungslos, der Widerspruch
    zur Signierungs-Doku stand in der Doku selbst. Jetzt: signierter Commit,
    schlägt die Signatur fehl (z. B. frischer Codespace vor setup.sh), wird
    **unsigniert wiederholt — mit lauter WARNUNG**, nicht still. Persistence
    (Komfort > Sicherheit) bleibt immer möglich, der Verlust der Signatur ist
    aber sichtbar statt unsichtbar.
  - **Kapselungs-Fix glm2api:** `server.py` griff auf private Accumulator-
    Attribute zu (`accumulator._terminal_status`, `accumulator._completed_output`).
    `ResponsesStreamAccumulator` bekommt öffentliche Lese-Properties
    (`terminal_status`, `completed_output`), server.py nutzt sie — ein Refactor
    des Accumulators kann den Folgerunden-Pfad nicht mehr still brechen.
  - **`antigravity-proxy/auth` entfernt (2026-10-01):** 9,8-MB-ELF, von nichts
    referenziert; die 2026-09-28-Duldung ist beendet, siehe Changelog 2026-10-01.
  - **TokenRouter-Key bleibt als Literal** (Nutzerentscheidung 2026-09-27 gilt,
    heute bestätigt): Provider wird nicht genutzt, Key wird nicht angefasst.
  - **Doku nachgezogen:** Provider-Tabelle führt `downloaddoctor`/`cyberpradeep`
    auf (konfiguriert, aber bisher in keiner Doku; ohne Setup-/Watchdog-Betreuung),
    und die Anthropic-Stelle klärt die Richtung: `/v1/messages` hat der
    **glm2api**-Proxy (server.py, Anthropic-Adapter), **nicht** der
    antigravity-Proxy — die Stelle las sich bisher, als träfe „kein
    Messages-Endpoint“ beide.

- 2026-09-27: **`.github/copilot-instructions.md` gelöscht — damit ist die Client-Datei-Regel abgeschlossen: im Repo liegt nur noch `AGENTS.md`.** Nutzerentscheidung: Copilot wird nicht benutzt. Die Datei war kein Duplikat, sondern ein 25-Zeilen-Zeiger auf `AGENTS.md` — und genau darin liegt der Unterschied zum Gemini-Fall von zwei Stunden vorher: **bei Gemini war der Default-Dateiname falsch und musste durch eine User-Config ersetzt werden, weil ein leerer Konzept-Kontext ein stiller Totalausfall ist; Copilot liest seine Datei nativ, also räumt das Löschen hier nur auf und bricht nichts.** Ein Pflegeposten ohne Nutzen ist trotzdem ein Pflegeposten, und die Datei stand in vier Stellen: in `AGENTS.md` als „einzige verbleibende Ausnahme", in der Client-Tabelle und in zwei Absätzen dieses Abschnitts, als Check-Liste in `verify-codespace.sh` und als einziger Eintrag des gestrichenen Copilot-Musters. **Der Check hat sich dadurch selbst abgeschafft:** `Save-Regel in allen Client-Dateien` iterierte genau über eine Datei — mit deren Verschwinden war der Check sinnlos, also ist er raus; übrig bleiben `AGENTS.md (Referenz)`, `keine Client-Kopien mehr` (dessen Liste jetzt **auch** `.github/copilot-instructions.md` verbietet, also prüft er die vollständige Negativliste), `Gemini CLI liest AGENTS.md` und der Pfad-Check. **Eine Kopie im Repo ist damit nicht mehr Muster, sondern Fehlerfall** — der Abschnitt sagt das jetzt ausdrücklich, damit der nächste neue Client nicht wieder auf „kurze Kopie plus Check-Zeile" zurückfällt, sondern auf eine User-Config wie bei Gemini. Nebenwirkung: `.github/` verschwindet aus dem Repo, es enthielt nur diese Datei. **Und der Preis ist mitprotokolliert, statt ihn zu verschweigen:** ein Client ohne AGENTS.md-Support und ohne User-Config wäre ab jetzt nicht abgedeckt. Für Gemini und Claude ist das geprüft und gelöst, für Copilot irrelevant, weil der Client nicht verwendet wird — falls er doch einmal genutzt wird, ist `.github/copilot-instructions.md` in zwei Minuten wieder da und der Check schlägt dann sogar an.

- 2026-09-27: **`Revision.md` und `research/` gelöscht — mit der ganzen Kette, die daran hing.** Nutzerwunsch: „die beiden brauche ich nicht mehr". `Revision.md` war der statische Audit-Trail vom 24.09. (5606 Zeilen, 523 KB, Anhänge A–V), `research/` eine einzige Notiz vom 26.09. zu Cline-Free-Modellen — zu einem Provider, der inzwischen aus `opencode.json` raus ist. **Ein Löschen allein hätte die Kette kaputt gemacht, deshalb mitgelöscht:** `infra/scripts/validate-revision.sh` prüfte ausschließlich die Struktur *dieser einen Datei* (genau eine H1, 22 `BEGIN/END PART`-Marker in Reihenfolge, balancierte Code-Fences) und wäre ohne ihr Prüfobjekt toter Code gewesen; `infra/scripts/verify-verifier-selftest.sh` ist der Selbsttest genau dieses Verifiers (baut eine Regression ein, erwartet `exit != 0` mit `FAILED`, stellt wieder her, erwartet `exit 0`) und wäre ohne ihn eine Landmine gewesen — er schreibt in `validate-revision.sh` hinein und scheitert dann an der fehlenden Textstelle. **Deren Tod hat eine sichtbare Folge, und die ist Absicht:** `verify-codespace.sh` hatte in Abschnitt 9 als einzigen Check diesen Validator, der Abschnitt fiel damit leer und ist ersatzlos entfallen; die verbleibenden neun Abschnitte (Secrets, Ports, Provider, Daemons, Browser, Drive, Agenten-Anweisungen, Provider live) prüfen weiter dieselbe Kette, jetzt 23 statt 24 Checks. **Ein toter Verifier ist schlimmer als keiner:** er meldet grün, ohne irgendetwas zu prüfen — dieselbe Fehlerklasse, die im Repo bei `gdrive-backup.sh` schon einmal teuer war. **Zwei Doku-Stellen aufgeräumt, weil sie ins Leere zeigten:** der Schnellstart nannte `validate-revision.sh` als read-only Einstieg (jetzt `verify-codespace.sh`, der mehr abdeckt), und der Layout-Eintrag für `infra/` listete das Skript. Die Changelog-Einträge, die `Revision.md` erwähnen, sind **Bewusst nicht** angetastet — sie protokollieren, was damals gegolten hat, und Umschreiben von Historie ist hier derselbe Fehler wie bei den Agenten-Dateien. Aus demselben Grund lebt `llm-proxies/glm2api/glm2api-revision.md` weiter: das ist der Audit des **Proxys**, nicht des Repo, und wird von `validate-revision.sh` nie gelesen. **Ein Verweis musste trotzdem neu geschrieben werden, weil er eine gelöschte Datei als Beleg benutzt hat:** die Secrets-Sektion zeigte für zwei getrackte Literalwerte in `opencode.json` auf `Revision.md, SEC-02`. Der Befund ist am Live-File geprüft und **stimmt noch** — TokenRouter trägt einen echten `sk-…`-Key in `options.apiKey` (Provider ungenutzt, Whitelist hat ein einziges `stealth/union-alpha`), Antigravity den selbst erzeugten Admin-Key des lokalen Proxys auf `127.0.0.1:9878`. Die Stelle steht jetzt ausgeschrieben im Repo, statt auf ein totes Dokument zu zeigen. Der TokenRouter-Key ist damit eine offene Entscheidung (Provider raus oder Key ins Bundle wie bei allen anderen) und **bewusst nicht** in diesem Arbeitsgang geändert — das ist eine Secrets-Änderung, keine Dokumentationspflege.

- 2026-09-27: **Für Claude ist dieselbe Frage wie bei Gemini gestellt — und sie hat eine andere, bessere Antwort: nichts zu tun.** Auslöser war der Wunsch, auch Claude „per antigravity proxy" abzudecken. **Die Claude-Modelle laufen hier nicht als eigener Client, sondern als Modell in opencode** (`antigravity/claude-opus-4-6`, `claude-sonnet-4-6`), und damit ist opencode der Client, der `AGENTS.md` liest. Der Knackpunkt, der in der Gemini-Frage die ganze Arbeit gemacht hat, ist hier keiner: **Kontext stellt der Client zusammen, nicht das Modell** — ein Modellname ändert an der gelesenen Datei nichts, und der Proxy ist ein Transportweg, kein Client. Ein *eigener* Claude-Code-Client gegen diesen Proxy ist zudem gar nicht möglich, und das ist am Proxy-Quelltext belegt statt vermutet: `server.go:132-135` registriert `/v1beta/models/`, `/v1/models`, `/v1/chat/completions` und `/mcp` — **kein `/v1/messages`**, und `ServeHTTP` hat keinen Catch-all. Genau diesen Messages-Endpoint verlangt Claude Code. **Damit ist `CLAUDE.md` doppelt überflüssig:** für den jetzigen Betrieb (es läuft Claude in opencode) und für den Fall, dass Claude Code irgendwann doch als Client kommt — seit **v2.1.277** liest er `AGENTS.md` nativ, und der Default `claude-md-or-agents-md` greift genau dann, wenn keine `CLAUDE.md`/`CLAUDE.local.md` im Arbeitsverzeichnis oder darüber liegt, was hier ohnehin der Zustand ist. Umstellen nur über `~/.claude/settings.json` (`pluginConfigs."agents-md@builtin".options.instructionFiles`; in Projekt- und Local-Settings wirkungslos). Die Ausnahmen — Version < v2.1.277, erste Session nach Upgrade von ≤ v2.1.276, deaktiviertes `agents-md`-Plugin, einzelne Sessions vor v2.1.281 (Bedrock/Telemetrie aus) — rechtfertigen keine Datei im Repo, weil sie nur Altstände betreffen; der dokumentierte Rückweg wäre eine `CLAUDE.md` mit `@AGENTS.md`-Import, und genau die Kopie will das Repo nicht. **Alles nur in `infrastructure.md` dokumentiert, keine Skript- und keine Repo-Änderung** — anders als bei Gemini gab es hier nichts zu automatisieren, weil der Default des Clients bereits richtig ist; eine `~/.claude/settings.json` nur für einen Wert zu schreiben, den Claude Code schon hat, wäre eine Konfiguration ohne Fehler, die sie verhindert.

- 2026-09-27: **`GEMINI.md` gelöscht — im Repo bleibt genau eine Agenten-Datei, und Gemini CLI läuft trotzdem nicht mit leerem Kontext.** Der Nutzerwunsch war eindeutig („ich will aber kein GEMINI.md — alle sollen nur AGENTS.md nutzen"), die Umsetzung brauchte aber den Umweg über die User-Config. **Gemini CLI liest per Default ausschließlich `GEMINI.md`:** `DEFAULT_CONTEXT_FILENAME = 'GEMINI.md'` in `packages/core/src/tools/memoryTool.ts`. Der PR, der `AGENTS.md` als Default aufnehmen wollte (#24913), wurde am 2026-05-12 **geschlossen, ohne gemergt** zu werden; Issue #28227 bestätigt den Stand auch für das aktuelle `main`, und die Doku (`geminicli.com/docs/cli/gemini-md/`) nennt weiterhin nur `GEMINI.md`. **Ein bloßes Löschen wäre also ein stiller Totalausfall gewesen:** kein Fehler, keine Warnung, nur ein Agent ohne `AGENTS.md` — und damit ohne die Save-Pflicht, an deren Fehlen sich eine ganze Agentenstunde nicht abholen ließe. **Gelöst mit dem einen dafür vorgesehenen Hebel**, `context.fileName` in `~/.gemini/settings.json`. Neu: `infra/scripts/gemini-context.sh` (`apply|status|unapply`, idempotent), aufgerufen von `setup.sh` an der Stelle zwischen Freebuff und Browser-Runtime — es läuft auch dann durch, wenn `gemini` gar nicht installiert ist, denn `$HOME` ist ephemer und die Config muss bei jedem neuen Codespace wieder da sein. **Warum die Zuordnung in `$HOME` und nicht ins Repo:** die Client-Zuordnung ist eine Eigenschaft des *Clients*, nicht des Codes — sie ändert sich nicht mit dem Code, und als Datei im Repo wäre sie genau die Kopie, die man nicht pflegen wollte. Ein CLI-Skript ist damit gleichzeitig die Quelle und der Check-Punkt. **Merge statt Überschreiben, mit Beleg:** `apply` schreibt nur `context.fileName` und lässt den Rest der Datei stehen (gegenprobiert mit vorhandenem `"theme": "Dracula"` — bleibt erhalten), legt vorher ein `.bak` an und **verweigert** das Überschreiben bei kaputter Datei (Exit 1, Meldung nennt das `.bak`) statt zu raten. Getestet: frische Datei, Doppelaufruf (Idempotenz), Merge mit Fremdschlüssel, `unapply` entfernt `context` samt Restcontainer, kaputte Datei. `bash -n` grün. **Der Check in `verify-codespace.sh` (Abschnitt 8) wurde in vier Punkten nachgezogen:** `GEMINI.md` aus der Client-Datei-Liste raus, ein **neues** `check „keine Client-Kopien mehr"` (schlägt fehl, sobald `GEMINI.md`/`CLAUDE.md`/`.cursorrules`/`AGENT.md` zurückkommen — die Korrektur trifft also auch eine spätere Wiedervorlage), ein neues `check „Gemini CLI liest AGENTS.md"` über `gemini-context.sh status` (fällt genau dann durch, wenn der Kontext leer wäre) und der Pfad-Check unverändert. **Copilot bleibt bewusst die einzige Kopie im Repo:** `.github/copilot-instructions.md` ist ein 25-Zeilen-Zeiger auf `AGENTS.md`, keine Regelquelle — Copilot liest die Datei nativ, und eine Datei zu löschen, die nur verweist, würde den Zeiger ins Leere zeigen lassen, statt etwas zu vereinfachen. **Ein Punkt bleibt offen und ist hier ausdrücklich nicht erledigt:** Antigravity CLI (`agy`, der sanktionierte Nachfolger, siehe `infra/docs/free-cli-agents-2026-09.md`) wurde auf seinen Kontext-Dateinamen nicht geprüft. Er ist nicht Teil von `setup.sh`; falls er installiert wird, gehört er in denselben Hebel.

- 2026-09-26: **Cline und NVIDIA NIM aus opencode entfernt, `free-models.py` gelöscht — Grund ist Betriebsverlässlichkeit, nicht Modellqualität.** Auslöser war die Frage nach den Reasoning-Stufen von `stealth/pixel-canary`, deren Antwort in Cline-Timeouts und sporadischen 500ern unterging. **Was die Messung ergab** (Cap-Probe und Token-Vergleich, beide gegen die Cline-API): `none` liefert 0 Reasoning-Tokens, `high` 298, `xhigh` 464, `max` 349–349 — und `max` lief in 1 von 3 Läufen in einen Timeout >300 s, `xhigh` einmal in einen Vercel-500. opencode kennt intern genau sieben Stufen (`none, minimal, low, medium, high, xhigh, max`, Enum im Binary), mehr gibt es nicht; für `@ai-sdk/openai-compatible` reicht es jeden String ungeprüft als `reasoning_effort` durch. **Der eigentliche Befund ist aber der Provider, nicht die Stufen:** derselbe Aufruf lieferte im Tagesverlauf mal 200 und mal 500, ein Lauf von `max` lief 68 s, der nächste über 300 s in den Timeout, und ein `opencode run` gegen den Provider endete in `Unexpected server error`. Ein Provider, der ein Viertel der Anfragen verliert, ist im Hauptbetrieb unbrauchbar, egal wie gut die Modelle sind. **Entfernt:** beide Provider-Blöcke aus `opencode.json` (`cline`, `nvidia` — letzterer trug `z-ai/glm-5.3`), die Aliase `free-models`/`cline-models`/`nvidia-models`, die beiden `KEYS`-Zeilen in `keys.sh` sowie Pack- und Restore-Paar in `secrets.sh`. **Die Key-Dateien `~/.config/landscape/cline.key` und `nvidia-nim.key` bleiben bewusst auf der Platte** — sie sind nicht Teil des Caches oder der Profile, und `secrets.sh lock` ignoriert sie jetzt, sobald sie nicht mehr referenziert sind. **Nebenbefund, der die Entscheidung stützt:** die Cap-Probe, mit der die Stufen geprüft werden sollten, war an `space-bunny-alpha` zweimal hintereinander nicht reproduzierbar (einmal 500 „will mehr Reasoning", einmal 200 mit 0 Tokens) — dieselbe Fehlermeldung also ohne Aussagekraft. Verifiziert: `opencode models` zeigt keinen `cline/`- und keinen `nvidia/`-Eintrag mehr, `keys.sh status` listet nur noch `xinjianya.key`, `bash -n` auf allen drei geänderten Skripten, `opencode.json` valides JSON.

- 2026-09-26: **glm2api war im echten Betrieb kaputt: ein Tool-Call endete je nach Zerschnittenheit des Upstream-Texts als `stop` oder als `error` — und die Abschluss-Warnung dokumentierte das Gegenteil des Messwerts.** Anlass war die Übergabe aus der Debug-Session (`/workspaces/cline/handoff.md`), die „718 Tests grün" meldete; gemessen waren **716 + 2 rot**, und `git bisect` über `c8135d9..HEAD` traf den S-09-Commit `4af494e` selbst als ersten schlechten. **Befund 1:** der neue Narration-Holdback fraß auch das Werkzeug-Protokoll (`tool_calls` stand in seinem Auslöser-Muster), der Parser sah den Aufruf erst im `finalize`, und die Einstufung „unbrauchbarer Aufruf" (T-06) war da schon entschieden — `{"tool_calls":[{"name":"read","arguments":{}}]}` endete als leere, erfolgreiche Antwort (`stop`) statt als `error`. **Befund 2 (älter, schwerer):** die Abschluss-Einstufung stützte sich auf `dropped_call_count`, und der Zähler zählt *Teil-Parse-Versuche*, nicht unbrauchbare Aufrufe — er hängt an der Zerschnittenheit (gemessen: derselbe gesperrte Aufruf ergibt Chunk 100 → 1, Chunk 3 → 4, Chunk 1 → 0). Folge: ein **gesperrter** Aufruf, der über mehrere Deltas kam, endete in 9 von 15 Chunk-Größen und in **beiden** Abschluss-Pfaden als `error` — also als vermeintlicher Stream-Fehler, den der echte Client mit 5-Minuten-Backoff endlos wiederholt (der Fall, für den `c8135d9` den `stop` eingeführt hatte). Entscheidend ist, dass der Upstream-ChatGLM-Text live in **4–8-Zeichen-Teilen** ankommt; die Fehlerklasse ist im Normalbetrieb also der Regelfall, nicht die Ausnahme. **Fix:** Markup wird vor dem Narration-Muster ausgeschlossen (`contains_tool_markup`), und entschieden wird am **Text** des Turns statt am Parser-Zustand (`_text_attempted_tools`): erlaubter Name → `error`, nur gesperrte Namen → `stop`, kein Name lesbar (abgeschnitten) → `error`, kein Protokoll im Text → alte Rechnung über `_policy_dropped_call_count`. **Zweiter Fund im selben Durchgang, Betriebskonfiguration:** vier Keys in allen drei ausgelieferten `.env`-Dateien wirkten nicht (`GLM_REFRESH_TOKENS`, `GLM_QUEUE_WAIT_TIMEOUT`, `REQUEST_TIMEOUT`, `REQUEST_SOCKET_TIMEOUT` — die letzten beiden wurden nicht einmal gemeldet und hatten exakt den Standardwert), und sechs Keys standen doppelt. `parse_dotenv` ließ still den letzten Eintrag gewinnen; beim Korrigieren entstand dadurch in der echten `.env` eine leere zweite `GLM_REFRESH_TOKEN=`, die den echten Token verdrängte — **der Dienst startete nicht mehr** („kein ChatGLM-Konto konfiguriert"), bei intakter Datei. Dublette werden jetzt mit Zeilennummern gemeldet (ohne den Wert zu nennen, das hätte den Refresh-Token ins Log geschrieben), die vier Tot-Keys sind aus allen drei Dateien raus und über `_CONFIG_KEY_KNOWN_TYPOS` jetzt *laut* statt still. Verifiziert: **788 Tests grün** (70 neue in `test_translator.py`, 11 in `test_config.py`), Gegenprobe gegen den Vorher-Stand — 20 neue Tests schlagen gegen `4af494e~1` fehl, 12 gegen `4af494e` — und live gegen den echten Proxy: Neustart sauber (`health` ok, keine `IGNORED`-/Dublett-Warnung), Textantwort `stop`, Tool-Aufruf non-stream **und** stream mit `finish_reason: tool_calls` und `read {"filePath":"/etc/hostname"}`. Ein Live-Lauf endete mit `error`, weil das Modell sein eigenes Protokoll abgeschnitten hat (Roh-SSE `{"tool_calls":[{"name":"read","arguments":{"filePath`) — Modellverhalten, korrekt eingestuft. Der zugehörige Arbeits-Audit steht in `llm-proxies/glm2api/glm2api-revision.md` (S-08/S-09/Nachtrag).
- 2026-09-26: **`infra/scripts/glm2api.sh` ohne `setsid` — der Proxy bekam SIGTERM mitten im Stream, wenn ein Agent-Tool-Call in den Timeout lief.** Der Server blieb in der Prozessgruppe des aufrufenden Shells; lief ein Tool-Call in den Timeout, wurde er mitten in der Antwort beendet. Zweimal gemessen (17:47:15 und 19:25:19), jeweils Session abgerissen. **Das erklärt die hängengebliebenen ChatGLM-Conversations:** das Löschen sitzt im `finally` des Request-Handlers und lief nicht mehr mit — auf chatglm.cn blieben tote Gesprächshüllen zurück. `start-glm2api.sh` (Watchdog-Pfad) machte es seit jeher richtig, die zwei Startwege waren nicht gleichwertig. Fix: `setsid bash -c 'echo $$ > PID.tmp; exec python main.py' & disown` — `setsid` liefert kein `$!`, deshalb schreibt das `bash -c` seine **eigene** PID in eine Temp-Datei, die dann umbenannt wird; dazu **Adoption** eines bereits laufenden Servers, sonst starten `restart` und der `proxy-watchdog` beide. Verifiziert: `sid` des Servers == eigene PID, Tool-Call lief in den Timeout, Server lebte.

- 2026-09-26: **Freebuff CLI kommt fest in die Landschaft — Install + Login inklusive, mit zwei Fallen, die erst der Live-Test gezeigt hat.** Zuerst als reines `/workspaces`-Projekt gebaut (Nutzerwunsch: nicht global), nach Rückmeldung aber sauber ins Repo geholt, damit jeder neue Codespace es automatisch hat. `infra/scripts/freebuff-install.sh` (Pin **0.0.204**), `setup.sh` ruft es **nach** dem Secrets-Schritt, Login (`~/.config/manicode/credentials.json`) wandert über `secrets.sh` in `config/secrets.enc` — Muster exakt wie `rclone.conf`. Damit `secrets.sh lock` nicht versehentlich ein Secret verliert, sind **vor** dem Neuverschlüsseln alle 9 bisherigen Bundle-Einträge auf Existenz geprüft (alle OK).
  - **Falle 1 — npm-Pin ist nicht die Binary-Version:** `npm view freebuff version` stand bei 0.0.203, der Launcher zog beim selben Start **0.0.204** (`frebuff-metadata.json` + `.freebuff-0.0.204-linux-x64.tar.gz.part` in `~/.config/manicode`). Der Launcher lädt selbstständig das *neueste* native Binary, unabhängig von der npm-Pin, ohne jeden Env-Override (im `launcher.js` gibt es nur PostHog-/App-URL-Variablen). Konsequenz: Pin auf 0.0.204 angeglichen und die `.part`-/`-download-temp`-Reste eingeräumt, die sonst bei **jedem** Start ~30 MB in den ephemeren `$HOME` schreiben. Die Pin ist damit für den Launcher belastbar, für das Binary nicht — ein Upstream-Release kommt mit dem nächsten Build durch. Steht so in der Doku, damit das später niemand überrascht.
  - **Falle 2 — `rm -rf ~/.config/manicode` löscht den Login mit:** Der Testlauf „Rebuild simulieren" hat dabei den gerade erst erzeugten `credentials.json` mitgerissen (erst danach fiel mir auf, dass dort auch der Token liegt, den `secrets.sh` sichern soll). Der Token war danach nicht mehr rekonstruierbar — die API-Probe mit dem alten Wert lieferte 401, also: einmal neu einloggen, *dann* locken. Reihenfolge ist jetzt im Skript festgehalten (Login-Check am Ende, mit Hinweis auf `login` + `secrets.sh lock`).
  - **Gemessen:** frische Installation aus dem Repo-Skript **12-24 s** (1-3 s npm + 136-MB-Binary, netzabhängig; vier Läufe: 12,3 / 12,6 / 16,3 / 23,6 s). Der Login-Roundtrip über das Bundle wurde verifiziert: `credentials.json` gelöscht → `secrets.sh unlock` → Restore **byte-identisch** (360 B, 0600), alle 8 anderen Bundle-Secrets unverändert vorhanden.
  - **Korrigiert nach dem ersten Commit (Nutzerwunsch: „unter MAIN wie opencode"):** der erste Stand legte das npm-Projekt nach `/workspaces/freebuff` und cachte das Binary zwischen `/workspaces` und `$HOME` hin und her (Rebuild-Restore 3,3 s statt Download). Das war persistent, aber ein fremdes Zuständigkeitsmodell im Repo — opencode ist ephemer in `$HOME` und wird bei jedem Codespace neu gebaut. Jetzt identisch zu opencode: `$HOME/.local/share/freebuff` + Wrapper `~/.local/bin/freebuff`, **kein** `/workspaces`-Pfad und kein Cache mehr. **Der Gewinn des Caches ist damit weg — bewusst gegen diesen Preis:** jeder neue Codespace lädt 136 MB neu (12-24 s, läuft in setup.sh). Ein Zwischending aus beiden Welten (npm-Manifest im Repo, `node_modules` ephemer) wäre möglich, brächte aber einen zweiten Zustandspfad ohne Nutzen.
  - **Nebenbefund:** `/workspaces/fb-probe` (32 KB) lag als Rest eines Testlaufs mit gesetzter `FREEBUFF_CONFIG_DIR` herum — nur ein WARN-Log (`No auth token available`) plus anonyme Analytics-ID, keine Credentials. Gelöscht. Lehre: das native Binary kennt `FREEBUFF_CONFIG_DIR`, der npm-Launcher **nicht** — beide auf verschiedene Pfade zu setzen erzeugt genau solche „ausgeloggt"-Symptome, ohne Fehlermeldung.
  - **Mausrad-FiX, zweite Runde (das war nicht die ganze Wahrheit):** Die erste Keybinding-Mappt `mousewheel` auf **ein** PageUp/PageDown — und der Nutzer meldet zu Recht „scrollt nur den Chat, im Chatbereich, 10 Zeilen". Ursache im Binary, Chat-Screen-Handler woertlich: `case"pageup":J.current?.scrollBy(-10)` bzw. `scrollBy(10)` fuer down, dazu `home`/`end` als Sprung an Anfang/Ende — und am Ende `a.preventDefault?.()`. **Dieses `preventDefault` ist der ganze Befund:** es unterdrueckt opentuis eigenen ScrollBox-Handler, der `pageup` auf `scrollBy(-0.5,"viewport")` mappen wuerde. Ein Tastendruck scrollt in freebuff also hart begrenzt auf 10 Zeilen, und **eine Taste fuer einen Bildschirmsprung existiert nicht** — kein `ctrl+pageup` (der Component bails bei ctrl/meta/option per `return`, und der Root-Handler ueberspringt es ueber `xz=(H)=>Boolean(H.ctrl||H.meta||H.option)`), kein `shift+pageup` (feuert beide Handler, also 10 Zeilen plus Root-Scroll), `home`/`end` sind Spruenge. opencode kann es, weil es die Tasten selbst mappt (`tui.json`: `messages_page_up: pageup`) — das ist der Unterschied, nicht die Terminalseite. Loesung ohne Eingriff in die App: die Keybinding sendet **dreimal** die Sequenz (`\e[5~` x3 hoch, `\e[6~` x3 runter), ~30 Zeilen pro Rasterung, das entspricht einer Bildschirmseite. **Ehrlich als Magic Number markiert** (im Abschnitt „Maus, Copy/Paste & Scrollen in TUIs" und hier), weil sie an freebuffs Schrittweite hängt: ändert freebuff `scrollBy(-10)`, muss die 3 nachgezogen werden. Der zweite Teil der Nutzerbeobachtung ist keine Fehlfunktion: die Nachrichtenliste ist der einzige scrollbare Bereich, eine Ebene darüber existiert nicht — bei opencode ist es dieselbe Liste, nur mit voller Seite als Schritt. **Methodisch bemerkenswert:** die erste Fassung stützte sich auf die Doku-Behauptung, xterm.js übersetze das Rad in up/down, statt den tatsächlichen Handler zu lesen. Der Handler war in drei Klicks im Bundle auffindbar (`case"pageup":J.current?.scrollBy(-10)`), die Behauptung war falsch. Bei TUI-Innenleben ist der Binary-Code die Quelle, nicht die Terminal-Erwartung.
  - **Vierte Runde, und damit die Ursache statt des Symptoms: der Output-Bereich ist nicht „nicht scrollbar", er ist EINGEKAPPT und nur per Klick aufklappbar.** Die Navigation durch den minifizierten Bundle hat die Komponente `LAH` zutage geforscht, und die macht drei Dinge klar: `LAH=({command,output,expandable$=!0,maxVisibleLines:L,isRunning,…})` — `J=L??($?5:10)` heisst **5 Zeilen** collapsed bzw. **10** bei nicht aufklappbarem Block; der Aufklapp-Trigger ist `K(yA,{onClick:M,…})`, also ein **Maus-Klick**; und in der ganzen Komponente kommt `useKey`, `focusable` und `handleKeyPress` **null Mal** vor. Die App fuehrt laut Bundle genau vier Tasten-Actions ueberhaupt: `toggle-agent-mode`, `toggle-all`, `toggle-dock-panel`, `toggle-sponsored-dock` — **kein `expand`, kein `collapse`, kein `scroll-block`**. `LAH` wird an genau zwei Stellen benutzt: abgeschlossenes Kommando mit `expandable:!0, maxVisibleLines:5`, laufendes Kommando (`pending-bash`) mit `expandable:!1, maxVisibleLines:10`. **Damit ist der pty-Filter nicht die Ursache des Problems, sondern sein Ausloeser**: er entfernt genau den Klick, mit dem der Block aufklappbar waere. **Und damit ist die Grundsatzfrage beantwortet, die ich vorher falsch gestellt hatte:** 1:1-Uebertragbarkeit von opencode gibt es nicht, weil die Apps gegenlaeufig gebaut sind — opencode ist **tastatur-first** (`tui.json` bindet jede Aktion, deshalb funktioniert `mouse: false` dort), freebuff ist **maus-first** (seine eigenen Tips: „Drag to select text — it copies automatically (or click on a message)"). **Entscheidung des Nutzers: Maus aus, „genau wie opencode".** Der Default bleibt damit der pty-Filter, und der Preis wird nicht wegoptimiert, sondern benannt und mit freebuff-eigenen Mitteln entschaerft: `/copy` (Alias `copy-chat`) legt den **ganzen** Chat inkl. vollstaendigem Output in die Zwischenablage, `/export` (Alias `export-chat`, mit Zielargument) schreibt ihn als Datei — beides im Bundle als Slash-Commands verifiziert. Als Bonus-Loesung fand sich `wrapMode:"word"` + `maxVisibleLines`: der Cap zaehlt **umgebrochene** Zeilen, ein breiteres Terminal zeigt also im selben 5-Zeilen-Fenster mehr Text — die billigste Entlastung ueberhaupt. **Konsequenz fuer die Doku-Regel:** Bevor man am Terminal-Layer dreht, gehoert der UI-Aufbau der App gelesen — zwei FehlDiagnosen in dieser Session (Doku-Behauptung statt Bundle, Step-Groesse statt Region) waeren durch ein `LAH`-Lesen in einer Minute vermeidbar gewesen.
  - **Mausrad wird sanfter: Burst-Drosselung mit 120-ms-Fenster, per Env-Regler.** Nach dem Fix (=Bild hoch/runter) war der Bittgang „nur ein wenig langsamer“ — und die Ursache ist messbar doppelt: xterm.js schickt bei High-Resolution-Rad und Trackpad mehrere Steps pro Geste (im Key-Log als `ESC[A ESC[A` in **einem** Read sichtbar), jeder war eine volle Seite. `freebuff-pty.py` rastet deshalb pro Richtung ein Zeitfenster ein (`FREEBUFF_WHEEL_DEBOUNCE_MS`, Default **120 ms** ≈ 8 Seiten/s). **Der Test hat dabei einen echten Bug im Regler gefunden:** verworfene Pfeile wurden nicht konsumiert, dadurch schlichen genau die unterdrueckten Sequenzen unveraendert an der App vorbei — der Effekt waere je nach Timing **doppelt** statt sanfter gewesen. Der Fix ist simpel (`pos = match.end()` vor dem `continue`), der Fehler war wert: genau die Faelle „High-Resolution-Rad: 3 Notches in 1 Read“ und „runter analog (Burst)“ haben ihn sichtbar gemacht. Zehn Testfaelle gruen danach, inklusive der Grenzfaelle 90 ms > 80 ms (beide passieren — ein Ratenbegrenzer kann definitionsgemaess nur alle Fensterzeit eine Seite zulassen, keine Geste-Erkennung) und `ctrl+up`/links/rechts unveraendert. Live am pty: vier Notches in 200 ms -> **eine** `ESC[5~`. **Wichtig, weil es leicht falsch gelesen wird:** Das ist eine **Ratenbegrenzung, keine Gestenerkennung.** Eine einzelne Geste ueber 300 ms liefert weiterhin 2-3 Seiten. Wer das ganz anders will, braucht eine echte Gesten-Auswertung (Dauer bis Stille) — das waere ein eigener Hebel und ist bewusst nicht gebaut, weil 120 ms den Unterschied in der Praxis bereits aufhaelt. Und der Kommentar, der sich beim Einbauen selbst eingeschlichen hat („Fensterfenster“), ist im Doxygen-Kommentar des Skripts bereinigt.
  - **Scroll-Schrittweite: `fOA` 0.8 → 0.5 im Vendor-Binary gepatcht — opencodes Halbseiten-Navigation fuer freebuff.** Der Nutzer wollte die Aggressivitaet weg und die Frage gestellt, warum das bei opencode ging: dort ist es eine **Einstellung** (`messages_half_page_up: up` = halbe Seite, daneben `messages_line_up` = einzelne Zeile), bei freebuff gibt es **keine** — kein Flag, keine Env-Variable (beides im Binary geprueft), keine Keybind-Config, und die Konstante `fOA` kommt genau einmal vor. **Entscheidung des Nutzers: patchen.** `freebuff-install.sh` ersetzt `fOA=0.8` durch `fOA=0.5` (`FREEBUFF_SCROLL_STEP`, Default 0.5 = opencode) — drei Zeichen, **gleiche Laenge**, es wird also kein Byte verschoben. **Warum der Patch stecken bleibt:** der Launcher verifiziert per `verifyFileSha256` nur das **Archiv** (`partialArchivePath`) vor dem Entpacken, das entpackte Binary nicht mehr; es gibt also weder eine Pruefung, die den Patch bemerkt, noch eine, die ihn zurueckholt. **Sicherheitskette:** Patch nur bei **genau einem** Treffer, Backup unter `~/.config/manicode/freebuff.orig`, `verify_after_patch` startet das Binary nach dem Schreiben und **spielt das Backup zurueck**, falls es nicht mehr startet; Laengendifferenz, Mehrfach-Treffer und eine vom Upstream umbenannte Konstante bedeuten „unangetastet“ mit Meldung statt still falsch zu liegen. **Zwei Dinge live gelernt:** (a) Der erste Patchversuch brach mit `OSError: Text file busy` ab — **ein laufendes Executable laesst sich unter Linux nicht ueberschreiben**, weil die Testsession (und die productive) das Binary im Speicher hielten. Der Skript-Guard prueft jetzt vorher per `pgrep` und ueberspringt mit klarer Meldung; im naechsten Codespace-Build (keine Session laeuft) wird der Patch dann automatisch nachgeholt, und auch der Idempotenz-Pfad patcht erneut, weil ein Auto-Update ein frisches Binary legt. (b) Verifiziert wurde nicht nur der Byte-Tausch, sondern dass ein **gepatchtes Binary startet**: Kopie gepatcht, `--version` liefert `0.0.204`, Groesse unveraendert 135.981.184 B. **Die Doku-Regel, die dazugehoert:** Ein Hersteller-Setting, das es in der Ziel-App nicht gibt, laesst sich nicht durch Raten treiben, sondern nur durch Patchen — und dann gehört Sicherheitskette, Update-Nachholung und Rueckweg in **dieselben** Datei wie das Feature, nicht in eine Chatnachricht.
  - **Mausrad-Drosselung wieder aus (Default 0) — und die Schrittweite gemessen statt gefuehlt.** Der Nutzerwunsch „es soll mit 0 ms laufen, nur sollen weniger Zeilen gesprungen werden“ hat zwei Dinge getrennt, die ich verwechselt hatte: **Rate** (wie viele Schritte pro Geste) und **Schrittweite** (wie viele Zeilen je Schritt). Die Drosselung, die ich in zwei Runden „schaerfer“ gestellt habe, begrenzt die Rate — sie war damit am falschen Hebel und ist jetzt per Default 0 abgeschaltet (bleibt per `FREEBUFF_WHEEL_DEBOUNCE_MS` stellbar). Die **Schrittweite** ist im Bundle fest verdrahtet: `B=Math.floor(P.viewport.height * fOA)` mit **`fOA = 0.8`** — ein Klick springt also **80 % der Bildschirmhoehe**, unabhaengig von Terminalgroesse und ohne jede Konfigurationsmoeglichkeit. Feinere Schritte existieren in der App (opentui-ScrollBox: `pageup` = 0,5, `up`/`k` = 0,2 Viewport, dazu eine `scrollStep`-Eigenschaft, die freebuff mit `scrollboxProps:{}` nicht setzt), erreichbar aber **nur mit Fokus auf dem ScrollBox** — und Fokus setzt in freebuff ausschliesslich die Eingabe oder ein Agent, per `.focus()` auf `inputRef`. **Mit Maus aus gibt es keinen Weg, den Fokus auf den ScrollBox zu legen — der einzige waere ein Klick auf den Textbereich. `0.8` bleibt damit die einzige erreichbare Schrittweite.** **Und eine Korrektur an meiner eigenen Behauptung:** Ich habe aus dem Key-Log geschlossen, „xterm.js schickt das Mausrad als `up`/`down`“. Das Log beweist es **nicht** — dort stehen auch getippte Zeichen als `<1B>` (Zusammenfassung, seit der Ueberarbeitung), und die Pfeile koennen von Hand gekommen sein. Solange das offen ist, ist auch die Alternative nicht geprueft, ob VS Code das Rad ueberhaupt in den Terminal-Scrollback schickt (in dem Fall waere eine kleinere Schrittweite ohne Maus moeglich). **Der 5-Sekunden-Test dafuer steht noch aus.**
  - **Mausrad-Drosselung von 120 ms auf 200 ms** nach Nutzer-Feedback („besser, aber noch etwas zu langsam“), also ~5 statt ~8 Seiten/s. Der Wert steht als Default im Skript und ist per `FREEBUFF_WHEEL_DEBOUNCE_MS` ohne Codeaenderung ueber den Start tunable — bei einem Detail-Feedback wie diesem ist das die richtige Form: **Regler statt Wert**, damit die naechste Anpassung kein Commit braucht. Sechs Testfaelle gegen die neuen Grenzfaelle geprueft (150 ms < 200 ms wird geschluckt, 210 ms > 200 ms kommt durch) — die Grenze wandert mit dem Default mit, also gehoert der Wert in den Test, nicht nur ins Skript.
  - **Mausrad-FiX, fünfte Runde: die Lösung stand die ganze Zeit in `Revision.md` — und mein Keybinding-Weg war grundverkehrt.** Der Nutzer verwies auf die MAIN-Struktur, und dort steht es: **`Revision.md` 4.16 zu `.opencode/tui.json`** nennt als Zweck „Opencode-TUI-Maus- und Keybind-Konfiguration“, als **Abhängigkeit explizit die „xterm.js-Mausradübersetzung“** und als Betriebsannahme die **„gewünschte Halbseiten-Navigation über Auf-/Ab-Tasten“**; `input_move_up`/`input_move_down` seien „bewusst auf `none` gesetzt und konsistent mit der Halbseiten-Navigation“. `.opencode/tui.json` realisiert genau das: `messages_half_page_up: up`, `input_move_up: none`. **Der Trick ist die Umhaengung der Taste, die das Rad erzeugt — nicht eine Umleitung des Rads.** Bei freebuff gibt es keine Keybind-Config, aber der pty-Filter sitzt an derselben Stelle im Eingangsstrom, also haengt er dort `up`/`down` auf PageUp/PageDown um (`ESC[A`/`ESC OA` -> `ESC[5~`, `ESC[B`/`ESC OB` -> `ESC[6~`; links/rechts sowie `shift`/`ctrl`-Varianten unangetastet). **Damit ist auch die Nutzerbeobachtung „Mausrad scrollt nur Chatverlauf“ aufgeklaert:** das Rad kam als `up`/`down` an, und freebuff mappt die auf `bash-history-up`/`history-up` — also auf **Prompt-Historie**, nicht auf Scrollen. **Anker der Fixes ist die live bestaetigte Tatsache, dass `PageUp`/`PageDown` in freebuff funktionieren** (Nutzerbestaetigung), ueber den im Bundle belegten Root-Action `scroll-up`/`scroll-down`. Verifiziert: 9 Funktionstest-Faelle (Richtungs-Paare, SS3 im Application-Modus, links/rechts unveraendert, `shift+up`/`ctrl+up` unveraendert, Text+Pfeil, kein Doppel-Umschreiben) und end-to-end am echten pty — Kind bekam `ESC[5~ ESC[5~ ESC[6~ ESC[C` fuer `up up down rechts`. Abgesichert ist der Fall einer ueber zwei Reads **zerrissenen** Sequenz: unvollstaendige Praefixe werden zurueckgehalten (`abc` + `ESC[` / `A` -> `abc` + `ESC[5~`), sonst rueutscht ein geteilter Pfeil durch. **Der Preis ist derselbe wie bei opencode und deshalb korrekt:** `up`/`down` verschieben im Input nicht mehr den Cursor und navigieren nicht in der Prompt-Historie — genau der Verlust, den opencode mit `input_move_up: none` bewusst in Kauf nimmt. Bypass, falls doch noetig: `FREEBUFF_NO_ARROW_PAGE=1 freebuff`. **Und die Abgrenzung, die ich in vier Runden falsch gezogen habe:** Das Rad selbst umzuleiten ist unmöglich (VS Code dispatcht `mousewheel` nicht), die **Taste** umzuleiten war nie das Problem — sie war nur nie das, wonach ich gesucht habe. **Methodisch, die wichtigste Lehre dieser Session:** Bei einem Problem, das „dort war es doch schon gelöst“ heißt, gehört **zuerst** in die Repo-Doku geguckt, bevor Code analysiert wird. `Revision.md` 4.16 stand in der Struktur und war in Sekunden auffindbar — ich habe stattdessen vier Runden ein 136-MB-Bundle seziert. Dokumentation eines Vorgängers ist die billigste Fehlerquelle überhaupt.
  - **Mausrad-FiX, vierte Runde: die Keybinding war von Anfang an tot — und das Log hat es in 30 Sekunden gezeigt.** Weil die Diagnosen bisher immer am freebuff-Code hingen, habe ich den Weg umgedreht und **gemessen statt geraten**: `freebuff-pty.py` protokolliert (mit `FREEBUFF_PTY_DEBUG`, Standardpfad `/tmp/opencode/freebuff-keys.log`, **nur** Esc-/Steuersequenzen, getippter Text nur als Byte-Laenge `<12B text>`) jede Sequenz, die das Kind tatsächlich liest. Ergebnis nach drei Rasterungen: `-> ESC[A ESC[A` / `ESC[A` / `ESC[A` / `ESC[B` — **Pfeiltasten, kein einziges `ESC[5~`**. Zwei Schlussfolgerungen, beide belegt: **(a)** `.vscode/keybindings.json` mit `mousewheel up/down` hat **nie gefeuert**. Die VS-Code-Referenz listet die akzeptierten `key`-Werte auf (Buchstaben, Ziffern, Pfeile, `pageup`/`pagedown`, `home`/`end`, `tab`/`enter`/`escape`/`space`/`backspace`/`delete`, Nummernblock) — **`mousewheel` steht nicht darin und wird nicht dispatcht.** **(b)** Die Doku-Behauptung „xterm.js uebersetzt das Mausrad in `up`/`down`“ war **richtig**; ich hatte sie vorschnell als falsch abgetan und ist jetzt im Dokument wiederhergestellt. **Konsequenz:** Eine Umleitung des Mausrads ist im VS-Code-Terminal nicht moeglich — weder per Keybinding noch per Setting. Es bleiben zwei ehrliche Zustaende: Maus **an** (das Rad erreicht die App, sie scrollt ihre eigenen Bereiche — Chat *und* Output-Bloecke, Aufklappen per Klick geht, Kopieren ueber freebuffs eigenes Drag-to-copy) oder Maus **aus** (Terminal-Auswahl und -Kopieren wie opencode, aber das Rad kommt als `up`/`down` an und scrollt nichts). **Entfernt:** die tote `.vscode/keybindings.json` samt Doku-Verweisen, damit niemand denselben Weg noch einmal geht. Der Key-Log im Filter bleibt, weil er die Frage in Sekunden beantwortet. **Nebenbefund aus dem Log:** freebuff fordert die Maus-Sequenzen nach ein paar Sekunden erneut an (`Maus entfernt: 1000h 1002h 1003h 1006h` um 00:16:01 und 00:16:22) — der Filter faengt sie wieder ab, kostet aber nichts. **Methodisch, die eigentliche Lehre:** Bei „Taste kommt nicht an“-Problemen zuerst die **Tastatur-Event-Kette** (was kommt an?) pruefen, dann die **Anwendungslogik** (was macht die App damit?). Ich habe vier Runden die App analysiert, waehrend die Frage eine Ebene tiefer sass; der Logger sind 20 Zeilen und haetten Runde 1 ersetzt. **Und eine Korrektur an mir selbst aus derselben Session:** `git commit` committet den ganzen Index, nicht die genannten Pfade. Ein Commit hat eine parallel laufende, bereits gestagte Loeschung (`infra/scripts/free-models.py`, 905 Zeilen) mitgenommen. Ab jetzt pfadbegrenzt committen (`git commit -- <pfad>`), sonst schleppt man fremde Arbeit mit.
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
- 2026-09-11 (15): **glm2api: Kontext-Management für Lang-Agent-Sessions.**
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
  Bundle neu. Offen blieb der Encoding-Sanitizer (Steuerzeichen-Ausnahme in `translator.py`, `strip_turn_start_narration()`).
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
