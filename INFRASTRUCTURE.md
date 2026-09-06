# Infrastructure

Soll-Zustand des Codespaces. Details zu Regeln in `AGENTS.md`. Nur verifizierte, ausgeführte Änderungen stehen hier.

## Sicherheitsmodell (bewusst: Komfort > Sicherheit)

Das Repo ist shared für mehrere **eigene** Accounts. Automatik hat Vorrang vor Sekret-Schutz:

- Die Secrets-Enthüllungs-Passphrase liegt absichtlich als Klartext im Repo unter `config/passphrase`. Dadurch entsperrt sich jeder eigene Codespace beim Start selbst (`scripts/secrets.sh` nutzt sie als Fallback, `setup.sh` triggert Auto-Unlock auch ohne `LANDSCAPE_PASSPHRASE`).
- `Free-API.txt` darf Klartext-API-Keys enthalten (eigene Keys).
- Der Rest bleibt verschlüsselt (`config/secrets.enc`) bzw. klartext-los: `.env`, `~/.config/landscape/*`, `.secrets/`, Browserprofile, `.runtime/` werden weiterhin nicht committet.

## TUI / Mausrad-Mapping (bleibend — nicht kaputt machen)

Konfig: `.opencode/tui.json` (committet in MAIN → kommt in jede Codespace automatisch mit, opencode liest es beim Start). Das Mausrad-Scrollen läuft **nicht** über opencodes eigenen Maus-Modus, sondern über den Terminal:

- `"mouse": false` ist Absicht. Ohne Maus-Modus setzt opencode keinen Mouse-Tracking-Mode, also übersetzt **xterm.js** (Codespaces-/VS-Code-Terminal) das Mausrad im Alternate-Screen automatisch in `up`/`down`-Tasten.
- `keybinds`: genau diese `up`/`down` sind auf `messages_half_page_up` / `messages_half_page_down` gemappt (Viertelseite, ruhiger als die halbe Seite von `pageup`/`pagedown`).
- Konfliktfreie Umbelegung, damit `up`/`down` frei bleiben: `history_previous/next` → `ctrl+up`/`ctrl+down`, `input_move_up/down` → `none`, `session_parent` → `<leader>up`.
- **Nicht auf `mouse: true` ändern**: dann fängt opencode das Rad selbst und das `up`/`down`-Mapping bricht (Rad scrollt nicht mehr).
- Nur in xterm.js-Terminals (Codespaces Web, VS Code). In einem anderen Terminal (z. B. reines SSH ohne xterm) kann das Rad stattdessen als Escape-Sequenz ankommen und anderes Verhalten zeigen.

## Kanonischer Stand (2026-09-06)

- Playwright: `1.48.2`, gepinnt in `browser/package.json`, installiert via `browser/` (`npm ci`).
- Systempakete (in `.devcontainer/setup.sh`, idempotent): `nodejs`, `npm`, `xvfb`, `x11vnc`, `novnc`, `websockify` — nötig für Browser-Runtime und von `browser-install.sh`/`browser-start.sh` vorausgesetzt.
- Setup: `scripts/browser-install.sh` → installiert Chromium nach `.runtime/ms-playwright` (gitignored, reproduzierbar).
- Start: `scripts/browser-start.sh [URL]` → startet Xvfb, x11vnc, noVNC, Chromium. Idempotent, prüft selbst ob Dienste schon laufen.
- Runtime (nicht committet, wird per Skript neu erzeugt):
  - Browser-Builds: `.runtime/ms-playwright/`
  - Profil: `.runtime/chromium-profile/` (enthält evtl. Login-Daten — nie committen, kopieren oder veröffentlichen)
  - Logs: `.runtime/log/`
- Dienste (alle nur lokal, ephemeral — vor Wiederverwendung einmal prüfen, nie als dauerhaft behandeln):
  - Display `:120`, x11vnc `localhost:5920`, noVNC Port `6082` (`/vnc.html?autoconnect=1&resize=scale`), CDP `http://127.0.0.1:9222`
  - CDP nie öffentlich freigeben (erlaubt Kontrolle über die Browsersitzung). In Remote-Codespaces `localhost:6082` durch die weitergeleitete Port-URL ersetzen.

## Sessions-MCP (opencode-sessions)

- Lokaler MCP-Server `mcp/opencode-sessions-mcp.js` (Node >= 18 + `sqlite3`-CLI, zero dependencies) für Session-Verwaltung direkt auf `~/.local/share/opencode/opencode.db`: list/delete/preview/search/info/stats. Kaskadierende Löschung inkl. Orphan-Event-Cleanup + VACUUM; schützt automatisch die aktuelle + aktive + geteilte Sessions; `confirm: true` Pflicht.
- Registriert in `.opencode/opencode.json` (`mcp.opencode-sessions`), kommt mit dem Repo in jeden Codespace. `setup.sh` stellt die Registrierung idempotent her (passt Pfade an, legt Config an, fügt mcp-Key ein, falls fehlt).
- Details: `mcp/README.md`.

## Deprecated (darf weg, kein Soll mehr)

Alte, nicht reproduzierbare Ablagen — werden nicht mehr verwendet, seit `browser/` + `scripts/` existieren:

- `/home/vscode/.npm/_npx/705bc6b22212b352/node_modules/playwright*` (Playwright 1.63.0)
- `/home/vscode/.npm/_npx/7f4967a1621aa3dc/node_modules/playwright*` (Playwright 1.48.2)
- `/home/vscode/.cache/ms-playwright/chromium-1140/chrome-linux/chrome` (Chromium 130.0.6723.31)
- `/home/vscode/.config/chromium` (altes Profil)

Regel: nach Verifikation von `scripts/browser-start.sh` in einer Sitzung sind diese Pfade redundant und dürfen nach einmaliger User-Freigabe gelöscht werden (Rückweg: `scripts/browser-install.sh` + `scripts/browser-start.sh` erneut laufen lassen). Keine erneute Freigabe-Schleife.

Hinweis: `require("playwright")` aus `/workspaces/MAIN` schlägt mit `MODULE_NOT_FOUND` fehl — das ist kein Installationsfehler, Playwright liegt absichtlich nur unter `browser/node_modules`.

## Prüfung (nur bei Browser-/Infra-Tasks)

```bash
pgrep -af 'chrome|chromium|Xvfb' | head -20
ss -ltnp | grep -E ':9222|:6082|:5920' || true
ls .runtime/ms-playwright 2>/dev/null || echo "runtime fehlt -> scripts/browser-install.sh"
curl -fsS http://127.0.0.1:9222/json/version | head -c 300; echo
```

Läuft etwas Passendes → wiederverwenden. Fehlt der Build → `scripts/browser-install.sh`. Laufen Dienste nicht → `scripts/browser-start.sh`.

## Changelog

- 2026-09-06: Sessions-MCP `opencode-sessions` hinzugefügt (`mcp/opencode-sessions-mcp.js`, zero deps): Session-Verwaltung direkt auf der opencode-SQLite-DB (list/preview/delete/search/info/stats), kaskadierende Löschung + Orphan-Event-Cleanup (574 MB → 2 MB beim Erstsäuberungslauf). In `.opencode/opencode.json` registriert, `setup.sh` stellt Registrierung idempotent in jedem neuen Codespace her.
- 2026-09-06: Reproduzierbarkeit geschlossen: `setup.sh` installiert jetzt `nodejs`, `npm`, `xvfb`, `x11vnc`, `novnc`, `websockify` (waren nur manuell vorhanden — frischer Codespace hätte die Browser-Runtime nicht starten können). `tui.json` unverändert: `mouse: false` ist Absicht — ohne Maus-Modus übersetzt xterm.js das Mausrad in `up`/`down`, die auf `messages_half_page_up`/`_down` gemappt sind (Mausrad-Scrollen funktioniert so nativ).
- 2026-09-06: Sicherheitsmodell festgeschrieben (Komfort > Sicherheit): Passphrase liegt als Klartext in `config/passphrase`, `setup.sh` + `scripts/secrets.sh` entsperren sich selbst (Fallback ohne `LANDSCAPE_PASSPHRASE`). `scripts/secrets.sh` sichert jetzt auch `nvidia-nim.key` + `xinjianya.key`; Bundle + `config/secrets.manifest` neu generiert (kein veraltetes `bananarouter-key` mehr, enthält nun `chatglm-refresh-token`).

- 2026-09-06: Kanonik auf `browser/` (Playwright 1.48.2) + `scripts/browser-install.sh` / `scripts/browser-start.sh` + `.runtime/` (gitignored) umgestellt. Alte npx-Caches, `chromium-1140` und `/home/vscode/.config/chromium` als deprecated markiert (löschbar nach Freigabe). Doku-Loop entfernt: kein Voll-Read/Doku-Zwang pro Edit mehr.
- 2026-09-05: Erstaufnahme (npx-Caches 1.63.0/1.48.2, chromium-1140, PID 392273, Display :120, Ports 5920/6082/9222, Profil `/home/vscode/.config/chromium`). Konsolidierung war damals noch offen — ist mit dem Stand vom 2026-09-06 erledigt.
