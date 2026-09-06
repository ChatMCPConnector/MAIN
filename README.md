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
| `llm-proxies/` | glm2api-Haupt-Proxy: Patch + Startskript + `rebuild.sh` |
| `work/` | Eigene Projekte: `docs/` |
| `.secrets/` `.env` `.runtime/` | GITIGNORED — Klartext-Secrets, Browser-Profil, Runtime (nie committen) |

```
/workspaces/glm2api/   GLM-Proxy-Klon (flüchtig, via llm-proxies/rebuild.sh rekonstruierbar)
```

## Schnellstart

Codespace bauen → `setup.sh` läuft automatisch (Systempakete, opencode,
Secrets-Unlock, Git-Auth, Browser-Runtime). Danach:

```bash
./infra/scripts/save.sh status                       # Überblick (Repo, Auth, Secrets)
./llm-proxies/rebuild.sh                             # glm2api-Proxy (optional, dauert 1-2 Min)
/workspaces/glm2api/start.sh                         # Proxy starten (Log: /tmp/opencode/glm2api.log)
```

Aliase (via `infra/scripts/aliases.sh`, automatisch in .bashrc): `save`, `auth`,
`secrets`, `ports`, `st`, `ll`, `landscape-diff`.

## Enthalten

- Ubuntu 24.04, Bash, Git, GitHub CLI, Docker, Python 3, Build-Werkzeuge
- Ports 3000/8000 (Apps), 8001 (LLM-Proxy), 9222/6082/5920 (Browser, nur lokal) · Zeitzone Europe/Berlin
- opencode, Default-Modell `tokenrouter/z-ai/glm-5.3-free` (1M Kontext)

## Secrets-Modell (bewusst: Komfort > Sicherheit)

Repo ist shared für mehrere **eigene** Accounts. Automatik hat Vorrang vor
Secret-Schutz-Purismus:

- `config/passphrase`: Entschlüsselungs-Passphrase als Klartext im Repo → jeder
  eigene Codespace entsperrt sich beim Start selbst. Sie ist NUR ein
  Entschlüsselungswort — nie ein Secret/PAT als Passphrase zweckentfremden
  (der alte PAT wurde dadurch geleakt und von GitHub revoked).
- `config/secrets.enc` (+ Manifest): verschlüsseltes Bundle mit
  `pat`, `tokenrouter.key`, `nvidia-nim.key`, `xinjianya.key`, `chatglm-refresh-token`,
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

- `mcp.opencode-sessions`: Session-Verwaltung direkt auf der SQLite-DB
  (`infra/mcp/opencode-sessions-mcp.js`, zero deps) — list/preview/delete/search,
  kaskadierende Löschung + Orphan-Event-Cleanup, schützt aktive/aktuelle/geteilte
  Sessions, `confirm:true` Pflicht. Details: `infra/mcp/README.md`.
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
./llm-proxies/rebuild.sh            # klonen + patchen + start.sh kopieren
/workspaces/glm2api/start.sh        # starten (uv run lädt Deps on-demand)
```

- `llm-proxies/patches/glm2api.patch`: Tool-Protokoll von DSML-Markup auf
  JSON+`[]`-Terminator umgestellt (+ DSML/Mashup-Fallbacks, Part-Merge-Fix —
  chatglm.cn streamt erst Token-Schnipsel, dann Volltext; Fix = anhängen +
  idempotent ersetzen statt blind überschreiben).
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
als Codespaces-Secrets. Nicht mitkommen, aber rekonstruierbar:
`/workspaces/glm2api` (rebuild.sh), Browser-Profil, Ports.

## Changelog

- 2026-09-06 (4): Konsolidierung nach Benchmark: **glm2api ist der Haupt-Proxy**
  (einziger verbliebener, Benchmark-Gewinner — 2/2 Agent-Tasks vollautonom).
  hellogml + chat2api KOMPLETT entfernt (Klones, Patches, Provider, Agenten,
  start-Skripte). Benchmark-Suite komplett entfernt (Templates, MASTERPROMPT,
  bench-Agents, Reports). `llm-proxies/rebuild.sh` auf nur-glm2api vereinfacht.
- 2026-09-06 (3): Struktur radikal vereinfacht: `infra/` (scripts+browser+mcp),
  Free-API.txt gelöscht (Key identisch im Secrets-Bundle), Doku-Merge zu einer
  README.md, `llm-proxies/` statt `proxies/`.
- 2026-09-06 (2): PAT geleakt+revoked → Secrets-Modell korrigiert: echte
  Zufalls-Passphrase (nur Entschlüsselungswort), PAT nur verschlüsselt im Bundle.
- 2026-09-06 (1): Proxies reproduzierbar im Repo; opencode-sessions MCP
  (Session-Verwaltung direkt auf SQLite-DB, 574 MB → 2 MB Orphan-Cleanup);
  Playwright-Reproduzierbarkeit in setup.sh; Secrets-Modell Komfort>Sicherheit.
