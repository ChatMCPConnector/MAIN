# Infrastructure

Soll-Zustand des Codespaces. Details zu Regeln in `AGENTS.md`. Nur verifizierte, ausgeführte Änderungen stehen hier.

## Kanonischer Stand (2026-09-06)

- Playwright: `1.48.2`, gepinnt in `browser/package.json`, installiert via `browser/` (`npm ci`).
- Setup: `scripts/browser-install.sh` → installiert Chromium nach `.runtime/ms-playwright` (gitignored, reproduzierbar).
- Start: `scripts/browser-start.sh [URL]` → startet Xvfb, x11vnc, noVNC, Chromium. Idempotent, prüft selbst ob Dienste schon laufen.
- Runtime (nicht committet, wird per Skript neu erzeugt):
  - Browser-Builds: `.runtime/ms-playwright/`
  - Profil: `.runtime/chromium-profile/` (enthält evtl. Login-Daten — nie committen, kopieren oder veröffentlichen)
  - Logs: `.runtime/log/`
- Dienste (alle nur lokal, ephemeral — vor Wiederverwendung einmal prüfen, nie als dauerhaft behandeln):
  - Display `:120`, x11vnc `localhost:5920`, noVNC Port `6082` (`/vnc.html?autoconnect=1&resize=scale`), CDP `http://127.0.0.1:9222`
  - CDP nie öffentlich freigeben (erlaubt Kontrolle über die Browsersitzung). In Remote-Codespaces `localhost:6082` durch die weitergeleitete Port-URL ersetzen.

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

- 2026-09-06: Kanonik auf `browser/` (Playwright 1.48.2) + `scripts/browser-install.sh` / `scripts/browser-start.sh` + `.runtime/` (gitignored) umgestellt. Alte npx-Caches, `chromium-1140` und `/home/vscode/.config/chromium` als deprecated markiert (löschbar nach Freigabe). Doku-Loop entfernt: kein Voll-Read/Doku-Zwang pro Edit mehr.
- 2026-09-05: Erstaufnahme (npx-Caches 1.63.0/1.48.2, chromium-1140, PID 392273, Display :120, Ports 5920/6082/9222, Profil `/home/vscode/.config/chromium`). Konsolidierung war damals noch offen — ist mit dem Stand vom 2026-09-06 erledigt.
