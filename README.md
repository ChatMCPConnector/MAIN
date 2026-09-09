# MAIN — Multi-Account Arbeitsumgebung als Code

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/ChatMCPConnector/MAIN?quickstart=1&ref=main)

Geteiltes Multi-Account-Repo (ein User, mehrere GitHub-Accounts, je max. ~60h
Codespaces/Monat): die komplette persönliche Arbeitsumgebung — Dev-Container,
opencode-Config (mehrere LLM-Provider), Secrets-Mechanik, GLM-Haupt-Proxy.
Alles Bleibende liegt im Repo; pro Account einmalig PAT + Passphrase als
Codespaces-Secrets, danach läuft alles automatisch (`postCreateCommand` →
`.devcontainer/setup.sh`).

**Doku-Aufteilung:** Diese README = Überblick + Layout + Betrieb.
`AGENTS.md` = Verhaltensregeln für Agenten (wird von opencode automatisch gelesen).

## Layout — was wozu gehört

| Pfad | Zweck |
|---|---|
| `.devcontainer/` | devcontainer.json + setup.sh (läuft automatisch bei jedem Codespace-Bau) |
| `.opencode/` | opencode-Config: opencode.json (Provider/MCP), tui.json |
| `config/` | secrets.enc (verschlüsseltes Bundle) + Manifest + passphrase (Klartext, bewusst) |
| `infra/` | **Werkzeugkasten:** `scripts/` (save/auth/secrets/ports/kontostand/browser-*.sh, aliases.sh), `browser/` (Playwright-Runtime 1.48.2, gepinnt), `mcp/` (opencode-sessions MCP) |
| `llm-proxies/` | glm2api-Haupt-Proxy: **kompletter Code liegt im Repo** (`llm-proxies/glm2api/` inkl. Patches) + `glm2api.env` + Start/rebuild-Skripte + **portables Bundle** (`dist/glm2api-bundle.zip`, Bau via `scripts/build-bundle.sh`) |
| `work/` | Eigene Projekte: `docs/` (Reverse-Engineering-Doku: `docs/reverse-engineering/`) |
| `.secrets/` `.env` `.runtime/` | GITIGNORED — Klartext-Secrets, Browser-Profil, Runtime (nie committen) |

## Schnellstart

Codespace bauen → `setup.sh` stellt ALLES automatisch wieder her (Systempakete,
opencode, uv, Secrets-Unlock, Git-Auth, Browser-Runtime, **glm2api-Proxy inkl.
Start** — der Code liegt komplett im Repo, es gibt nichts mehr zu klonen; nur
`uv sync` (Python 3.14 + Deps, beim ersten Mal ~2-5 Min) + Autostart). Danach:

```bash
./infra/scripts/save.sh status                       # Überblick (Repo, Auth, Secrets)
```

Aliase (via `infra/scripts/aliases.sh`, automatisch in .bashrc): `save`, `auth`,
`secrets`, `ports`, `st`, `ll`, `landscape-diff`.

## Enthalten

- Ubuntu 24.04, Bash, Git, GitHub CLI, Docker, Python 3, Build-Werkzeuge
- Ports 3000/8000 (Apps), 8001 (LLM-Proxy), 9222/6082/5920 (Browser, nur lokal) · Zeitzone Europe/Berlin
- opencode, Default-Modell `tokenrouter/z-ai/glm-5.3-free` (1M Kontext)
- `infra/scripts/nvidia-models.py`: eigenständiges Utility — NVIDIA-Modellindex
  von build.nvidia.com (kostenlos, NIM-Keys), für Modell-Discovery

## Secrets-Modell (bewusst: Komfort > Sicherheit)

Repo ist shared für mehrere **eigene** Accounts. Automatik hat Vorrang vor
Secret-Schutz-Purismus:

- `config/passphrase`: Entschlüsselungs-Passphrase als Klartext im Repo → jeder
  eigene Codespace entsperrt sich beim Start selbst. Sie ist NUR ein
  Entschlüsselungswort — nie ein Secret/PAT als Passphrase zweckentfremden
  (der alte PAT wurde dadurch geleakt und von GitHub revoked).
- `config/secrets.enc` (+ Manifest): verschlüsseltes Bundle mit
  `pat`, `tokenrouter.key`, `nvidia-nim.key`, `xinjianya.key`, `gemini.key`, `chatglm-refresh-token`,
  `env`, `opencode-auth.json` → landen beim Unlock unter `~/.config/landscape/`,
  `~/.local/share/opencode/auth.json` bzw. `.env`/`.secrets/`.
- `./infra/scripts/secrets.sh lock|unlock|status` verwaltet das Bundle.
- Codespaces-Secrets pro Account: `LANDSCAPE_PAT` (Git-Auth), `LANDSCAPE_PASSPHRASE` (optional).
- API-Keys in `opencode.json` referenzieren `{file:~/.config/landscape/<key>}` —
  kommen also über das Bundle in jeden neuen Codespace.

## opencode-Konfiguration (`.opencode/`)

Provider (`opencode.json`, Default `tokenrouter/z-ai/glm-5.3-free`):

| Provider | Modelle | Auth |
|---|---|---|
| tokenrouter | z-ai/glm-5.3-free (1M) | tokenrouter.key |
| nvidia | nemotron-3-ultra, deepseek-v4-flash/pro | nvidia-nim.key |
| xinjianya | gpt-5.6-sol, kimi-k3, deepseek-v4-pro | xinjianya.key |
| **glm2api** | glm-5.3, glm-5.3-think | lokal, Port 8001, kein Key |
| google | gemini-flash-latest (1M) | gemini.key |

- `mcp.opencode-sessions`: Session-Verwaltung direkt auf der SQLite-DB
  (`infra/mcp/opencode-sessions-mcp.js`, zero deps) — list/preview/delete/search,
  kaskadierende Löschung + Orphan-Event-Cleanup, schützt aktive/aktuelle/geteilte
  Sessions, `confirm:true` Pflicht. Details: `infra/mcp/README.md`.
- `agent/glm2api.md`: Arbeits-Subagent fest auf `glm2api/glm-5.3` (Haupt-Proxy).
- `tui.json`: Maus-Capture **aus** (`mouse: false` ist Absicht — xterm.js
  übersetzt dann das Mausrad in `up`/`down`, die auf halben Seitenwechsel
  gemappt sind. **Nicht auf `true` ändern.**)

## glm2api — der LLM-Haupt-Proxy (Port 8001)

Chatglm.cn-Reverse (Python/FastAPI, Guest-Token-Pool: 100 Slots, Auto-Refetch
+ 10 Retries), OpenAI-kompatibel. Gewinner des 3-Wege-Agenten-Benchmarks
(2026-09-06): als einziger Proxy 2/2 SWE-Tasks **vollautonom in je 1 Run**
(35+ Tool-Executions, 0 Abbrüche). hellogml (Guest-Token-Erschöpfung bei
Lang-Runs) und chat2api (Markup-Fragilität bei Agent-Loops) wurden daraufhin
komplett entfernt — glm2api ist der verlässliche Agent-Proxy.

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

## Infrastruktur-Soll (Details Betrieb)

- **Kanonisch ist:** gepinnte Version im Repo + reproduzierbares Skript.
  PID-/Port-Ausgaben sind ephemeral — vor Wiederverwendung einmal prüfen
  (`pgrep`, `ss`, `curl`), nie als Blocker oder Dauerzustand dokumentieren.
- **Browser-Runtime:** Playwright 1.48.2 gepinnt in `infra/browser/package.json`
  → `./infra/scripts/browser-install.sh` (installiert nach `.runtime/ms-playwright`,
  gitignored) → `./infra/scripts/browser-start.sh [URL]` (Xvfb, x11vnc, noVNC,
  Chromium; idempotent). Dienste: Display `:120`, VNC `localhost:5920`,
  noVNC Port `6082`, CDP `http://127.0.0.1:9222` — CDP nie öffentlich freigeben.
  Profil `.runtime/chromium-profile/` enthält evtl. Logins — nie committen/kopieren.
- **Systempakete** via setup.sh (idempotent): nodejs, npm, xvfb, x11vnc, novnc,
  websockify, sqlite3, build-essential, python3-* etc.
- **Deprecated (löschbar nach Freigabe):** alte npx-Playwright-Caches
  (`~/.npm/_npx/705bc*/`, `~/.npm/_npx/7f49*/`), `~/.cache/ms-playwright/chromium-1140/`,
  `~/.config/chromium/` (altes Profil) — redundant seit `infra/browser/` +
  `infra/scripts/browser-*.sh`. Rückweg: browser-install.sh + browser-start.sh.

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

**Proxy-Verhalten nach Stopp:** Prozesse sterben, `/tmp` (Logs) wird geleert —
Code, venv und .env in MAIN überleben alles. Der Boot-Mechanismus zieht den
Proxy bei jedem Start automatisch hoch.

## Changelog

- 2026-09-08 (6): **Kompaktierung/Audit-Umsetzung** (AUDIT.md + glm-api-audit.md
  abgearbeitet): korrupter Patch gestrichen (`llm-proxies/patches/` — der
  Source im Repo ist kanonisch); Bundle neu gebaut mit vollständigen Tests
  (inkl. test_config.py) und deterministischen Zeitstempeln (md5-stabil,
  Doppelbuild verifiziert); 15 MB Debug-Logs + __pycache__/egg-info
  aufgeräumt; README-Changelog gekürzt; `.env.example` vervollständigt
  (SYSTEM_ACCESS_TOKEN, TOKENROUTER_API_KEY); Start-/Rebuild-Skripte gehärtet
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
