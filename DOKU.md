# DOKU — Projektstand MAIN-Landscape (2026-09-06)

Zentrale Projektdokumentation: Was dieses Workspace ist, wie es aufgebaut ist,
was läuft, und was beim Umzug mitkommt. Ergänzt `README.md` (Setup/Accounts),
`INFRASTRUCTURE.md` (Browser-Soll-Zustand) und `AGENTS.md` (Agent-Regeln) —
nicht doppelt pflegen, nur verlinken.

## 1. Was das ist

`/workspaces/MAIN` ist ein geteiltes Multi-Account-Repo (ein User, mehrere
GitHub-Accounts, je max. ~60h Codespaces/Monat). Es enthält die komplette
persönliche Arbeitsumgebung als Code: Dev-Container, opencode-Konfiguration
(mehrere LLM-Provider), Secrets-Mechanik und Skripte. Alles Bleibende liegt
im Repo und wird per `./scripts/save.sh` gepusht; pro Account werden einmalig
PAT + Passphrase als Codespaces-Secrets hinterlegt, danach läuft alles
automatisch (`postCreateCommand` → `.devcontainer/setup.sh`).

## 2. Layout

```
/workspaces/MAIN/          ← dieses Repo (wird gepusht, wandert beim Umzug mit)
  .devcontainer/           devcontainer.json + setup.sh (Auto-Setup beim Start)
  .opencode/               opencode-Config: opencode.json, tui.json, agent/*.md
  scripts/                 save.sh, auth.sh, secrets.sh, ports.sh, kontostand.sh,
                           browser-install.sh, browser-start.sh, nvidia-models.py
  mcp/                     opencode-sessions MCP (Session-Verwaltung, zero deps)
  proxies/                  GLM-Proxy-Patches + Startskripte + rebuild.sh (Kap. 5)
  dotfiles/                aliases.sh (wird in .bashrc verlinkt)
  config/                  secrets.enc (verschlüsseltes Bundle) + Manifest + passphrase (Klartext, bewusst)
  browser/                 Playwright-Runtime 1.48.2 (gepinnt, Details → INFRASTRUCTURE.md)
  work/                    eigene Projekte: docs/ + benchmark/ (ChaosShop, Kap. 6)
  .secrets/                Klartext-Secrets, GITIGNORED (u.a. chatglm-refresh-token)
  MASTERPROMPT.md          Benchmark-Prompt für den 3-Wege-GLM-Vergleich

/workspaces/{glm2api,hellogml,chat2api}/   ← GLM-Proxy-Klone (NICHT im Repo, via proxies/rebuild.sh rekonstruierbar)
/workspaces/benchmark/                     ← ChaosShop-Kopien (via work/benchmark/rebuild.sh aus Template)
```

**Wichtig:** Alles unter `/workspaces/*` außer `MAIN` ist flüchtig — geht beim
Codespace-Neubau verloren, ist aber vollständig aus MAIN reproduzierbar
(`proxies/rebuild.sh` + `work/benchmark/rebuild.sh`, Details Kap. 5/6).

## 3. Secrets-Modell

- Klartext-Keys liegen unter `~/.config/landscape/` und `.secrets/`
  (beide nie im Git): `pat`, `tokenrouter.key`, `nvidia-nim.key`, `xinjianya.key`,
  `chatglm-refresh-token`, dazu `~/.local/share/opencode/auth.json` und `.env`.
  Ausnahme (bewusst, Komfort > Sicherheit): die Enthüllungs-Passphrase liegt
  als Klartext im Repo unter `config/passphrase`; `Free-API.txt` darf Klartext-Keys
  enthalten.
- `./scripts/secrets.sh lock` packt sie verschlüsselt nach `config/secrets.enc`
  (Manifest: `config/secrets.manifest`); `unlock` stellt sie wieder her.
- Codespaces-Secrets pro Account: `LANDSCAPE_PAT` (Git-Auth, einmalig) steuert
  den Auto-Push; `LANDSCAPE_PASSPHRASE` ist optional, weil `config/passphrase`
  den Auto-Unlock beim Start bereits ermöglicht. `landscape-diff()` im
  Alias zeigt, was nur im Bundle, nicht im Git liegt.

## 4. opencode-Konfiguration (`.opencode/`)

Provider (`opencode.json`, Default-Modell `tokenrouter/z-ai/glm-5.3-free`):

| Provider | Modelle | Auth |
|---|---|---|
| tokenrouter | z-ai/glm-5.3-free | `{file:~/.config/landscape/tokenrouter.key}` |
| nvidia | nemotron-3-ultra, deepseek-v4-flash/pro | nvidia-nim.key |
| xinjianya | gpt-5.6-sol, kimi-k3, deepseek-v4-pro | xinjianya.key |
| glm2api | glm-5.3, glm-5.3-think | lokal, Port 8001, kein Key |
| hellogml | glm-5.3, glm-5.3-think | lokal, Port 8787, Key `sk-test-local-1` |
| chat2apilocal | GLM-5.3, GLM-5.3-Think | lokal, Port 8080, kein Key |

- `disabled_providers: ["github-copilot"]` — Copilot-Modelle ausgeblendet.
- `tui.json`: Maus-Capture **aus** (`mouse: false`), Mausrad hoch/runter ist auf
  Nachrichten-Seitenwechsel gemappt (Pfeiltasten/Up-Down-History umbelegt).
- Agenten (`agent/*.md`, Subagent-Typ, fest verdrahtete Modelle für Benchmarks):
  `bench-glm2api`, `bench-hellogml`, `bench-chat2api`. TUI-Agenten: build/plan.

## 5. Die drei GLM-Proxies (chatglm.cn-Reverse, Ports 8001/8787/8080)

Alle drei parsen chatglm.cn per Token (Guest-Pool/Auto-Refresh, kein Login nötig)
und sprechen OpenAI-kompatibel.

| Proxy | Port | Auth-Mechanik | Stand |
|---|---|---|---|
| glm2api (Python/FastAPI, Rang 1) | 8001 | 100 Guest-Slots, Auto-Refetch + 10 Retries | ✅ läuft, Tool-Calls verifiziert |
| HelloGML (TS/Worker via wrangler dev) | 8787 | 100er Token-Pool, Auto-Fill | ✅ läuft, Tool-Calls verifiziert |
| Chat2API (Electron headless) | 8080 | 10 Guest-Accounts, Round-Robin | ✅ läuft (Start wiegt ~70s), Tool-Calls verifiziert |

**Wiederaufbau in einem frischen Codespace (alles im Repo, reproduzierbar):**

```
./proxies/rebuild.sh            # alle drei: klonen + patchen + deps (+ build bei chat2api)
/workspaces/<name>/start.sh     # starten (Logs: /tmp/opencode/<name>.log)
```

- Patches: `proxies/patches/*.patch` (glm2api 228 Zeilen, hellogml, chat2api — Tool-Protokoll/Part-Merge-Fixes)
- Startskripte: `proxies/scripts/start-*.sh` (rebuild.sh kopiert sie nach `/workspaces/<name>/start.sh`)
- setup.sh rebuilt Proxies nur bei `LANDSCAPE_REBUILD_PROXIES=1` (Klones/Builds dauern Minuten)

**Patch-Inhalt (lokal, via .patch-Dateien gesichert):**
- glm2api `tool_protocol.py` + `tool_parser.py`: Tool-Protokoll von DSML-Markup
  auf JSON+`[]`-Terminator umgestellt (+ DSML/Mashup-Fallbacks, Part-Merge-Fix).
- HelloGML `chat.ts` (+ `wrangler.toml` KV-Platzhalter): gleicher Part-Merge-Fix,
  Non-Stream-Thinking-Fix, `[]`-Terminator im Tool-Prompt.
- Chat2API `providerProfiles.ts` (GLM → `managed_bracket`), `window/manager.ts`
  (Fenster hidden im Headless), `index.ts` (Hardware-Accel aus).

Gewonnene Erkenntnis (gilt für alle drei): chatglm.cn streamt pro Part erst
Token-Schnipsel ohne Akkumulation, dann den Volltext — blindes Überschreiben
erzeugt überlappenden Müll (`{"ol_callh"…). Fix = Schnipsel anhängen,
Finish-Volltext idempotent ersetzen.

Upstream-Limit ist pro Guest-Token (~5 Nachrichten), die Pools rotieren das
weg — kein Repo-Limit. Nach `git pull`/Rebuild der Proxy-Repos sind Patches
ggf. neu anzuwenden (rebuild.sh macht das idempotent; Konflikt-Fall: `--3way`).

## 6. Benchmark (ChaosShop-Vergleich)

- `MASTERPROMPT.md`: tool-agnostischer SWE-Bench-Prompt (4 Phasen, kein Tool namentlich).
- `work/benchmark/template/`: absichtlich vermurkster Python-Shop
  (Race, SQLi, Auth-Bypass, Randfälle), Startzustand **4 failed / 5 passed**,
  im Repo gesichert.
- `work/benchmark/rebuild.sh` legt `/workspaces/benchmark/<proxy>-work`-Kopien
  aus dem Template an (setup.sh macht das automatisch, wenn nötig).
- Agenten `bench-*` lösen je ihre Kopie.
- Frühere Runs liefen versehentlich über TokenRouter (8-req/min-Limit) — nur Runs
  über die drei lokalen Provider zählen für den Vergleich.

## 7. Skripte

`save.sh` (push), `auth.sh` (PAT/Git), `secrets.sh` (lock/unlock/status),
`ports.sh` (Alias `ports`: lauschende + geforwardete Ports, Prozess, URL, Fazit),
`kontostand.sh` (Kontostand/Verbrauch, Details → `work/docs/Kontostand.md`),
`nvidia-models.py` (Modelliste abziehen), `browser-*.sh` (→ INFRASTRUCTURE.md).

## 8. Umzug (neuer Account/Codespace)

1. Altem Codespace: `./scripts/save.sh` (+ ggf. `./scripts/secrets.sh lock`).
2. Repo forken, Codespace erstellen — `setup.sh` installiert alles, `unlock`
   läuft automatisch (Secrets als Codespaces-Secrets hinterlegt).
3. Nicht mitkommen, aber rekonstruierbar: `/workspaces/{glm2api,hellogml,chat2api}`
   (`./proxies/rebuild.sh` bzw. `LANDSCAPE_REBUILD_PROXIES=1` beim Codespace-Bau),
   `/workspaces/benchmark` (automatisch aus `work/benchmark/template`),
   Browser-Profil/Volumes, Ports (werden neu vergeben).

## 9. Historie-Hinweis

`GLM-Repos.md` (Recherche-Vergleich ~20 GLM-Web-Reverse-Projekte) wurde in
einem anderen Arbeitsgang gelöscht (Commit `5168629`) und ist nicht mehr im
aktuellen Tree. Inhalt bei Bedarf wiederherstellbar aus der Git-Historie
(Commits `f713ed5`, `0377d34`, `15013cc`, `eeff682`, `94757da`).
