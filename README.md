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
| `infra/` | **Werkzeugkasten:** `scripts/` (save/auth/secrets/ports/browser-*.sh, aliases.sh, nvidia-models.py), `browser/` (Playwright-Runtime 1.48.2, gepinnt), `mcp/` (opencode-sessions MCP), `docs/` (Reverse-Engineering-Doku) |
| `llm-proxies/` | LLM-Proxies: **glm2api** (Port 8001, GLM-Haupt-Proxy) + **gemini-web2api** (Port 8083, Gemini Web Pro) + **antigravity-proxy** (Port 9878, CloudCode OAuth) |

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

- Ports 3000/8000 (Apps), 4096 (opencode-Server für Multi-Client), 8001 (glm2api LLM-Proxy), 8083 (gemini-web2api Proxy), 9878 (antigravity-proxy), 9222/6082/5920 (Browser, nur lokal)
- opencode, Default-Modell `antigravity/gemini-3.8-flash` (Thinking immer aktiv auf high)
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
  `pat`, `tokenrouter.key`, `nvidia-nim.key`, `xinjianya.key`, `gemini-web-cookie.txt`, `antigravity-oauth_creds.json`, `chatglm-refresh-token`,
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
| **gemini-web** | gemini-3.1-pro-thinking, gemini-3.8-flash-thinking, gemini-3.5-flash-lite-thinking | lokal, Port 8083, Google AI Pro (Cookie-Pool) |
| **antigravity** | claude-opus-4-6 (1M, Thinking 2k/16k/32k), gemini-3.8-flash (1M, 64k Output), gemini-3.1-pro (1M, 64k Output), gemini-3.5-flash-light (1M, 32k Output) | lokal, Port 9878, Google Cloud Code OAuth |

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

**Bundle-Refresh (immer aktuell halten):** `build-bundle.sh` überschreibt das
alte `dist/glm2api-bundle.zip` bei jedem Lauf vollständig mit dem aktuellen
Source-Stand (rm + Neubau, kein Merge). Nach jeder glm2api-Code-Änderung
einfach neu laufen lassen. Deterministisch (feste Zeitstempel, inhaltlich
identische Stands = byte-identische ZIPs) und mit eingebauter Verifikation:
alle tests/*.py im Zip + byte-identischer src/ gegen den Repo-Source, sonst
exit 1. Drift ist damit strukturell ausgeschlossen — ein veraltetes Bundle
kann nicht mehr committet werden, ohne dass der Build vorher scheitert.

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
- 2026-09-10: **gemini-web2api Multi-Turn aktiviert + Tool-Disziplin gefixt (2 Ebenen).**
  (a) `multi_turn=true` in der Runtime-Config (kv-Tabelle, Admin-Panel) aktiviert — Proxy
  erkennt Konversations-Fortsetzungen per History-Fingerprint (`convParentKey`) und sendet
  nur noch die neueste Nachricht statt der kompletten Historie: **eine** gemini.google.com-
  Session pro Konversation statt eine pro Request; löst auch das 130k-Byte-Prompt-Wand-
  Problem (502 „no content frame") aus der Session „Gemini web fehler". (b) Fix 1:
  Format-Erinnerung (```tool_call```) in jeder 续接轮 — Modell verlor sonst nach wenigen
  Runden die Tool-Disziplin und antwortete in Prosa („I encountered an error"-Symptom in
  opencode). (c) Fix 2: Tool-Schemas in jeder 续接轮 neu injiziert (`toolsReminderBlock`)
  — Gemini-Webserver entfernt die Erstrunden-Tool-Definitionen nach ~9 Runden aus dem
  Kontext, Modell sagte dann „Ich habe kein Dateisystem-Tool". Langzeit-Stresstest:
  15 续接 in einer Web-Session, 10/10 korrekte Tool-Calls inkl. 4er-Kette ohne neue
  User-Nachricht, 0 Fehler. Proxy neu gebaut + läuft.
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
  `setup.sh` und `start-on-boot.sh` eingebunden. Standard-Modell in opencode auf
  `gemini-web/gemini-3.1-pro-thinking` (small_model: `gemini-3.8-flash-thinking`) umgestellt.
- 2026-09-09 (6): Gemini Web Pro Proxy (`gemini-web2api-go`) unter `llm-proxies/gemini-web2api/`
  integriert (Port 8083, Chrome-146-Fingerprinting, Cookie-Auto-Refresh). Multi-Turn-Persistenz
  für Google AI Pro Account unter `/u/1/` eingerichtet. Modelle in opencode (`gemini-web`):
  `gemini-3.1-pro-thinking`, `gemini-3.8-flash-thinking`, `gemini-3.5-flash-lite-thinking`.
  Cookie-Persistenz ins verschlüsselte Secrets-Bundle (`gemini-web-cookie.txt`) aufgenommen.
  Autostart in `setup.sh` und `start-on-boot.sh` verdrahtet.
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
