# MAIN — Multi-Account Arbeitsumgebung als Code

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/ChatMCPConnector/MAIN?quickstart=1&ref=main)

Geteiltes Multi-Account-Repo (ein User, mehrere GitHub-Accounts, je max. ~60h
Codespaces/Monat): die komplette persönliche Arbeitsumgebung — Dev-Container,
opencode-Config (mehrere LLM-Provider), Secrets-Mechanik, GLM-Proxies,
Benchmark. Alles Bleibende liegt im Repo; pro Account einmalig PAT + Passphrase
als Codespaces-Secrets, danach läuft alles automatisch
(`postCreateCommand` → `.devcontainer/setup.sh`).

**Doku-Aufteilung:** Diese README = Überblick + Layout + Betrieb.
`AGENTS.md` = Verhaltensregeln für Agenten (wird von opencode automatisch gelesen).

## Layout — was wozu gehört

| Pfad | Zweck |
|---|---|
| `.devcontainer/` | devcontainer.json + setup.sh (läuft automatisch bei jedem Codespace-Bau) |
| `.opencode/` | opencode-Config: opencode.json (Provider/MCP), tui.json, agent/*.md (bench-*) |
| `config/` | secrets.enc (verschlüsseltes Bundle) + Manifest + passphrase (Klartext, bewusst) |
| `infra/` | **Werkzeugkasten:** `scripts/` (save/auth/secrets/ports/kontostand/browser-*.sh, aliases.sh), `browser/` (Playwright-Runtime 1.48.2, gepinnt), `mcp/` (opencode-sessions MCP) |
| `proxies/` | GLM-Proxy-Patches + Startskripte + `rebuild.sh` (→ Kap. Proxies) |
| `work/` | Eigene Projekte: `docs/` (Kontostand), `benchmark/` (ChaosShop + MASTERPROMPT.md + rebuild.sh) |
| `.secrets/` `.env` `.runtime/` | GITIGNORED — Klartext-Secrets, Browser-Profil, Runtime (nie committen) |

```
/workspaces/{glm2api,hellogml,chat2api}/   GLM-Proxy-Klones (flüchtig, via proxies/rebuild.sh rekonstruierbar)
/workspaces/benchmark/                     ChaosShop-Kopien (flüchtig, via work/benchmark/rebuild.sh)
```

## Schnellstart

Codespace bauen → `setup.sh` läuft automatisch (Systempakete, opencode,
Secrets-Unlock, Git-Auth, Browser-Runtime, Benchmark-Kopien). Danach:

```bash
./infra/scripts/save.sh status                       # Überblick (Repo, Auth, Secrets)
./proxies/rebuild.sh                                 # GLM-Proxies (optional, dauert Minuten)
/workspaces/<glm2api|hellogml|chat2api>/start.sh     # Proxy starten (Log: /tmp/opencode/<name>.log)
```

Aliase (via `infra/scripts/aliases.sh`, automatisch in .bashrc): `save`, `auth`,
`secrets`, `ports`, `st`, `ll`, `landscape-diff`.

## Enthalten

- Ubuntu 24.04, Bash, Git, GitHub CLI, Docker, Python 3, Build-Werkzeuge
- Ports 3000/8000 (Apps), 8001/8787/8080 (LLM-Proxies), 9222/6082/5920 (Browser, nur lokal) · Zeitzone Europe/Berlin
- opencode, Default-Modell `tokenrouter/z-ai/glm-5.3-free` (1M Kontext)

## Secrets-Modell (bewusst: Komfort > Sicherheit)

Repo ist shared für mehrere **eigene** Accounts. Automatik hat Vorrang vor
Secret-Schutz-Purismus:

- `config/passphrase`: Enthüllungs-Passphrase als Klartext im Repo → jeder
  eigene Codespace entsperrt sich beim Start selbst (Fallback ohne
  `LANDSCAPE_PASSPHRASE`-Secret).
- `config/secrets.enc` (+ Manifest): verschlüsseltes Bundle mit
  `pat`, `tokenrouter.key`, `nvidia-nim.key`, `xinjianya.key`, `chatglm-refresh-token`,
  `env`, `opencode-auth.json` → landen beim Unlock unter `~/.config/landscape/`,
  `~/.local/share/opencode/auth.json` bzw. `.env`/`.secrets/`.
- `./infra/scripts/secrets.sh lock|unlock|status` verwaltet das Bundle.
- Codespaces-Secrets pro Account: `LANDSCAPE_PAT` (Git-Auth), `LANDSCAPE_PASSPHRASE` (optional).
- API-Keys in `opencode.json` referenzieren `{file:~/.config/landscape/<key>}` —
  kommen also über das Bundle in jeden neuen Codespace. Klartext-Nie-committen
  gilt weiter für `.env`, `.secrets/`, Browserprofile.

## opencode-Konfiguration (`.opencode/`)

Provider (`opencode.json`, Default `tokenrouter/z-ai/glm-5.3-free`):

| Provider | Modelle | Auth |
|---|---|---|
| tokenrouter | z-ai/glm-5.3-free (1M) | tokenrouter.key |
| nvidia | nemotron-3-ultra, deepseek-v4-flash/pro | nvidia-nim.key |
| xinjianya | gpt-5.6-sol, kimi-k3, deepseek-v4-pro | xinjianya.key |
| glm2api | glm-5.3, glm-5.3-think | lokal, Port 8001, kein Key |
| hellogml | glm-5.3, glm-5.3-think | lokal, Port 8787, Key sk-test-local-1 |
| chat2apilocal | GLM-5.3, GLM-5.3-Think | lokal, Port 8080, kein Key |

- `mcp.opencode-sessions`: Session-Verwaltung direkt auf der SQLite-DB
  (`infra/mcp/opencode-sessions-mcp.js`, zero deps) — list/preview/delete/search,
  kaskadierende Löschung + Orphan-Event-Cleanup, schützt aktive/aktuelle/geteilte
  Sessions, `confirm:true` Pflicht. Details: `infra/mcp/README.md`.
- `tui.json`: Maus-Capture **aus** (`mouse: false` ist Absicht — xterm.js
  übersetzt dann das Mausrad in `up`/`down`, die auf halben Seitenwechsel
  gemappt sind. **Nicht auf `true` ändern.**)
- `agent/*.md`: `bench-glm2api`, `bench-hellogml`, `bench-chat2api`
  (Subagenten mit fest verdrahtetem Proxy-Modell für Benchmark-Runs).

## Die drei GLM-Proxies (chatglm.cn-Reverse, Ports 8001/8787/8080)

Alle drei parsen chatglm.cn per Guest-Token-Pool (kein Login) und sprechen
OpenAI-kompatibel:

| Proxy | Port | Mechanik | Stand |
|---|---|---|---|
| glm2api (Python/FastAPI, Rang 1) | 8001 | 100 Guest-Slots, Auto-Refetch + 10 Retries | ✅ läuft, Tool-Calls verifiziert |
| HelloGML (TS/Worker via wrangler dev) | 8787 | 100er Token-Pool, Auto-Fill | ✅ läuft, Tool-Calls verifiziert |
| Chat2API (Electron headless) | 8080 | 10 Guest-Accounts, Round-Robin | ✅ läuft (~70s Start), Tool-Calls verifiziert |

**Wiederaufbau im frischen Codespace (alles im Repo):**

```
./proxies/rebuild.sh            # klonen + patchen + deps (+ build bei chat2api) + start.sh kopieren
/workspaces/<name>/start.sh     # starten
```

- `proxies/patches/*.patch`: Tool-Protokoll-Part-Merge-Fixes je Proxy
  (glm2api: JSON+`[]`-Terminator statt DSML-Markup; hellogml: Part-Merge +
  Non-Stream-Thinking-Fix; chat2api: GLM→`managed_bracket`, Fenster hidden, HW-Accel aus).
- Kern-Erkenntnis aller drei: chatglm.cn streamt pro Part erst Token-Schnipsel
  ohne Akkumulation, dann den Volltext — Fix = Schnipsel anhängen, Finish-Volltext
  idempotent ersetzen (blindes Überschreiben erzeugt Müll wie `{"ol_callh"…`).
- setup.sh rebuilt nur bei `LANDSCAPE_REBUILD_PROXIES=1` (sonst manuell, dauert Minuten).
- Upstream-Limit ist pro Guest-Token (~5 Nachrichten) — Pools rotieren das weg.

## Benchmark (ChaosShop 3-Wege-Vergleich)

- `work/benchmark/MASTERPROMPT.md`: tool-agnostischer SWE-Bench-Prompt (4 Phasen).
- `work/benchmark/template/`: absichtlich vermurkster Python-Shop (Race, SQLi,
  Auth-Bypass, Randfälle). Startzustand **4 failed / 5 passed** (verifiziert).
- `work/benchmark/rebuild.sh` legt `/workspaces/benchmark/<proxy>-work`-Kopien an
  (setup.sh macht das automatisch). Agenten `bench-*` lösen je ihre Kopie.
- Nur Runs über die drei lokalen Provider zählen (TokenRouter: 8 req/min).

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
als Codespaces-Secrets. Nicht mitkommen, aber rekonstruierbar:
`/workspaces/{glm2api,hellogml,chat2api}` (rebuild.sh), `/workspaces/benchmark`
(automatisch), Browser-Profil, Ports.

## Changelog

- 2026-09-06 (2): Struktur radikal vereinfacht: `scripts/` + `browser/` + `mcp/` +
  dotfiles zusammengezogen in `infra/`; Free-API.txt gelöscht (XinJianYa-Key lag
  byteweiß identisch im Secrets-Bundle, kommt via Auto-Unlock zurück);
  MASTERPROMPT.md nach `work/benchmark/`; README+DOKU+INFRASTRUCTURE zu dieser
  einen README.md gemerged (AGENTS.md bleibt separat — opencode-Regeln).
- 2026-09-06 (1): Proxies + Benchmark reproduzierbar im Repo (patches/,
  rebuild-Skripte), Trash gelöscht (1.9 MB), Doku konsolidiert.
- 2026-09-06 (0): opencode-sessions MCP (Session-Verwaltung direkt auf SQLite-DB,
  574 MB → 2 MB Orphan-Cleanup), Playwright-Reproduzierbarkeit in setup.sh,
  Secrets-Modell Komfort>Sicherheit festgeschrieben.
