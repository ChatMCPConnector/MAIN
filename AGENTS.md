# Agent Instructions

## 0. Automatik (was ohne dich passiert)

- Beim Codespace-Start läuft `.devcontainer/setup.sh` automatisch (`postCreateCommand`):
  Systempakete → opencode → Shell-Aliase → **Secrets-Auto-Unlock** (via `LANDSCAPE_PASSPHRASE`) → **Git-Auth** (via `LANDSCAPE_PAT`) → Browser-Runtime → Benchmark-Kopien.
- Erste Pflichtlektüre: `infrastructure.md` (Layout „was wozu", Betrieb, Proxies, Secrets-Modell, Changelog). `README.md` ist nur die kurze öffentliche GitHub-Übersicht.
- Repo ist shared für mehrere eigene Accounts. Alles Bleibende liegt unter `/workspaces/MAIN` und wird per `./infra/scripts/save.sh` gepusht. Einmal pro Account: PAT + Passphrase als Codespaces-Secrets hinterlegen, danach ist alles automatisch.
- **Gilt für jeden Agenten, unabhängig vom Client:** Diese Datei ist die
  einzige Quelle — es gibt bewusst **keine** Client-Kopien (`GEMINI.md`,
  `CLAUDE.md`, `.cursorrules`, `.github/copilot-instructions.md` sind entfernt;
  neu anzulegen verhindert nur Driften). Gemini CLI liest diese Datei, weil
  `infra/scripts/gemini-context.sh` `context.fileName=["AGENTS.md"]` in
  `~/.gemini/settings.json` setzt (siehe `infrastructure.md`, Abschnitt
  „Agenten-Anweisungen"). Copilot wird nicht benutzt.
- **Sicherheitsmodell: Komfort > Sicherheit.** Alle Accounts sind eigene. Die Secrets-Passphrase liegt absichtlich im Repo (`config/passphrase`). Kein „Geheimnis-Schutz"-Purismus, Automatik hat Vorrang.

## 1. Session-Start

- Lies `infrastructure.md` einmal pro Session (Layout-Abschnitt reicht im Alltag).
- Kein Re-Read vor jedem Edit. Nur erneut lesen, wenn der Task Infrastruktur berührt (Browser, Ports, Display, Profile, Installationen, Dependencies, Persistenzpfade).

## 1a. Repo-Karte (Kurzfassung)

`infrastructure.md` ist die volle Akte — die brauchst du selten ganz. Für den
Alltag:

- `llm-proxies/glm2api/` — Python-Haupt-Proxy (Port 8001), `src/` + `tests/`, uv.
- `llm-proxies/antigravity-proxy/` — Go (Port 9878), `mise`-Tasks, Binary wird gebaut.
- `llm-proxies/zerokey/` — Node/Express (Port 7250), `pnpm` (eslint + Tests).
- `infra/scripts/` — Shell-Werkzeugkasten (`save.sh`, `secrets.sh`, `keys.sh`, …).
- `infra/scripts/freebuff_patch.py` — die **Byte-Patches** des freebuff-Binaries
  (Mausrad-Scroll, `Entf` löscht eine Session in `/history`, Wortgrenzen,
  halbe Scrollseite). Freebuffs Launcher ersetzt das native Binary bei jedem
  Update ungefragt und löscht damit alle Patches; deshalb zieht der Wrapper sie
  **bei jedem Start** nach (`--ensure`, Stamp-Vergleich: ~0,1 s im Normalfall).
  **Kaputt? Das ist der eine Fall mit einer festen Reihenfolge:**
  1. `python3 infra/scripts/freebuff_patch.py --check` — read-only, Exit 1 =
     Drift; die Zeile nennt Patch **und** Grund.
  2. Handweis + Runbook im Docstring der Datei (Abschnitt „Wenn ein Patch nicht
     mehr passt"): erst den Byte-Kontext im Binary **belegen**, dann das Muster
     namenunabhängig neu schreiben, `STAMP_FORMAT` hochzählen, Fixture in
     `infra/tests/test_freebuff_patch.py` erweitern.
  3. **Nicht** durch bloßes `freebuff-install.sh` „reparieren" — das meldet
     dieselbe Drift erneut. Am Ende `make check` + `bash
     ./infra/scripts/freebuff-install.sh` + einmal `freebuff` starten.
- `.opencode/`, `.devcontainer/`, `config/` — Client-Config, Setup, Secrets.

## 2. Was als Infrastruktur-Änderung zählt

Nur das ist eine Infrastruktur-Änderung:

- neues/geändertes Tool, Version, Pfad, Port, Service, Profil,
- neues/geändertes Setup- oder Startskript,
- geänderte Persistenz- oder Sicherheitsregel.

Normale Code-, Doku- und Config-Edits sind keine Infrastruktur-Änderung: keine Infra-Prüfung, kein Doku-Zwang, kein Extra-Commit.

## 3. Infrastructure

- `infrastructure.md` (Abschnitt „Infrastruktur-Soll") beschreibt den Soll-Zustand. Kanonisch ist immer: gepinnte Version im Repo + reproduzierbares Skript unter `infra/scripts/`.
- PIDs, `ss`-Ausgaben und laufende Sitzungen sind ephemeral: vor Wiederverwendung einmal prüfen (`pgrep`, `ss`, `curl`), nie als dauerhaften Zustand dokumentieren oder als Blocker verwenden.
- Nur verifizierte, tatsächlich ausgeführte Änderungen dokumentieren. Planung und Ist-Zustand getrennt halten.
- Keine parallele agentspezifische Infrastrukturakte.
- Keine Secrets (Tokens, Cookies, Passwörter) in die Doku schreiben. Ausnahme (bewusst, Komfort > Sicherheit): `config/passphrase` ist als Klartext im Repo erlaubt.

## 4. Safety

- Vor Installation/Start/Löschung genau einen Bestandscheck machen (z. B. vorhandener Build, laufender Prozess, belegter Port). Danach handeln, nicht in Schleifen weiterprüfen.
- Keine fremden Prozesse beenden, keine Caches/Profile/Installationen löschen ohne einmalige explizite Freigabe des Users. Eine erteilte Freigabe gilt, muss nicht erneut eingeholt werden.
- Für schwer rückgängig machbare Aktionen Rückweg in einem Satz festhalten (Reinstall-/Restart-Befehl).
- **Nichts, was hängen kann, ohne Timer starten.** `./infra/scripts/timeout.sh run <sekunden> <kommando>` für jeden Aufruf, der (a) endlos laufen könnte, (b) im Hintergrund läuft, (c) eine Pipe/Subshell offen hält oder (d) ein Kind startet, das weiterläuft. Exit 124 = Zeitüberschreitung, alle anderen Exit-Codes kommen unverändert durch. Das Skript räumt die Prozessgruppe ab und ist der Grund, warum der Bash-Tool-Aufruf nicht im 120-s-Timeout endet.
- **Nie `pkill -f` bzw. `kill $(pgrep -f …)` direkt benutzen.** Das Muster steht in der Kommandozeile der aufrufenden Shell, also trifft es diese mit — live passiert, der Aufruf brach sich selbst ab und lief in den Timeout (2026-09-30). Stattdessen `./infra/scripts/timeout.sh kill <muster>`: schließt sich selbst und alle Vorfahren aus. `./infra/scripts/timeout.sh selftest` prüft beide Zusicherungen.

## 5. Persistence

- Fertige Arbeit liegt vollständig unter `/workspaces/MAIN` und wird per Git erfasst. Unfertige/temporäre Inhalte nach `/workspaces` oder `.runtime/`, nie als „fertig" behandeln.
- `.runtime/`, Browserprofile, Caches und Klartext-Secrets werden nicht committet (siehe `.gitignore`). Ausnahme (Komfort > Sicherheit): `config/passphrase` darf Klartext-Secrets enthalten. Was davon für einen neuen Codespace nötig ist, muss als reproduzierbares Skript unter `infra/scripts/` im Repo liegen.
- `infrastructure.md` (Changelog + Infra-Soll) nur bei tatsächlicher Infrastruktur-Änderung im selben Arbeitsgang aktualisieren. `README.md` (öffentliche Übersicht) nur bei relevanten Strukturänderungen. Kein Doku-Update und kein Commit für Nicht-Infra-Änderungen erzwingen.
- **Committen/Pushen ohne Rückfrage:** seit 2026-09-26 dauerhaft freigegeben („immer selber direkt"). Nach jedem abgeschlossenen Arbeitsgang `./infra/scripts/save.sh "<message>"` laufen lassen — das macht Commit, Rebase, Push und Drive-Backup in einem. Nicht mehr nachfragen. Vorher `git status`/`git diff` prüfen, Secrets sind durch `.gitignore` ausgeschlossen. Ausnahme: destruktive Historie (`rebase` auf gepushten Commits, `force-push`, `reset --hard`) bleibt Rückfrage-Pflicht.
- **Nur eigene Pfade committen.** `git commit` committet den **gesamten Index**, nicht die genannten Dateien — und `save.sh` macht vorher `git add -A`. Da das Repo für mehrere eigene Accounts shared ist, erwischt das fremde, gerade in Arbeit befindliche Änderungen (live passiert: eine 905-zeilige Löschung aus einer parallelen Refactor-Arbeit landete in einem fremden Commit). Deshalb: **vor dem Save `git status` ansehen.** Ist fremder Änderungsstand im Baum → nicht committen, melden, eigene Pfade mit `git commit -- <pfad>` separat sichern.
- **Kein Autosave-Daemon.** Bewusst abgeschaltet (2026-09-27), weil er per `git add -A` den Agent-Index mutierte und Halb-Zustände laufender Arbeit als eigene Commits einfror. **Damit ist der `save.sh`-Aufruf oben der einzige Auslöser für Commit *und* Drive-Backup** — ohne ihn ist bis zu einer Stunde Agent-Arbeit nach einem Codespace-Verlust weg.
- **Testläufe nicht committten.** Ein Test, der einen echten Commit erzeugt, gehört zurückgenommen (nicht gepusht), bevor weitergearbeitet wird — sonst landet er in `origin/main`.

## 6. Verifikation (nie „fertig" ohne grünen Check)

Ändere Code, dann laufe den Check. Nicht behaupten — messen.

**Ein Einstiegspunkt** (seit 2026-10-01, `Makefile` im Repo-Root):

| Befehl | Wirkung |
|---|---|
| `make check` | alle Schnell-Checks inkl. Tests — der volle Gate-Lauf |
| `make check-fast` | nur Lint/Syntax, ohne Tests (= Hook-Niveau) |
| `make verify` | `verify-codespace.sh` (read-only, prüft die **laufende** Kette) |
| `make verify-code` | nur der Quellcode-Teil — braucht keine Dienste, kein Bundle, kein Netz |
| `make ci` | `check` + `verify-code` + `deps`: exakt das, was GitHub Actions fährt |
| `make smoke` | echter Live-Smoke-Test gegen den laufenden glm2api (dauert Minuten) |
| `make check-all` | `check` + `verify` |
| `make help` | alle Targets |

Nur ein Teil:

| Bereich | Befehl |
|---|---|
| glm2api (Python) | `make lint-py` / `make test-py` |
| zerokey (JS) | `make lint-zk` / `make test-zk` |
| antigravity-proxy (Go) | `make lint-go` / `make test-go` |
| MAIN-eigenes JS | `make lint-js` |
| Shell | `make syntax-sh` (bash -n über alle getrackten Skripte) |
| Shell (tiefer) | `make shellcheck` — nur **neue** Befunde sind rot, der Bestand ist in `infra/scripts/shellcheck-baseline.txt` eingefroren. Baseline bewusst erneuern: `make shellcheck-baseline` |
| infra-Python | `make lint-py-infra` / `make mypy-infra` / `make test-infra` / `make cov-floor` |
| Gate-Kommentare | `make claims` — Aussagen über die Gate-Config (Coverage-Floor-Scope) gegen `infra/coverage-floor.rc`. Der Floor ist **global**, nicht pro Datei |
| Dependencies | `make deps` = Lockfile-Drift (hart, alle drei Ökosysteme) · `make deps-audit` = CVE-**Report**, endet immer mit 0 |


Der Makefile dupliziert **keine** Check-Liste: jedes Target ruft exakt die
Kommandos auf, die auch der pre-commit-Hook fährt. Der Verify-Check
„Makefile deckt Hook ab" vergleicht beide Dateien und wird rot, sobald sie
auseinanderlaufen. **Formatieren** bleibt Handarbeit (`gofmt -w .` in
antigravity-proxy) — ein Verifier darf nichts schreiben.

`mise` ist hier **nicht** installiert: die `mise.toml`-Tasks des vendorten
antigravity-proxy (`mise run test`/`format`) sind der Upstream-Weg, laufen aber
nur mit mise. Deshalb stehen oben die direkten `go`-Befehle (Go liegt unter
`/usr/local/go/bin`, auf dem PATH via `aliases.sh`).

Bei zerokey ist `pnpm lint`/`check`/`test` der belastbare Check; `pnpm format`
(prettier) ist auf dem vendorten Baum derzeit **nicht** sauber (5 Dateien, u.a.
Prosa-Instruktionen) — ein blindes `--write` kann Instruktionstexte umbrechen.

**Automatik:** `.githooks/pre-commit` fährt die Checks der **betroffenen**
Sprache bei jedem Commit, der die jeweiligen Dateien stagt — schlägt ein Check
fehl, bricht der Commit ab:

| gestagte Dateien | läuft |
|---|---|
| `llm-proxies/glm2api/**.py`/`toml` | `ruff check .` + `mypy src` |
| `llm-proxies/antigravity-proxy/**` (`.go`, `go.mod`/`go.sum`) | `go vet ./...` + `gofmt -l` |
| `infra/**.js` | `node --check` |

Aktiviert `setup.sh` per `core.hooksPath=.githooks`. Der Hook fasst den Index
**nicht** an (kein `git add`, kein `--fix`/`--write`) und läuft nur, wenn die
Sprache betroffen ist — Doku-/Infra-Commits kostet er nichts. Die Tabellen-
Befehle oben bleiben der **volle** Check (Tests laufen dort mit, der Hook
lintet nur). zerokeys `pnpm precommit` bleibt handgestartet (braucht
`node_modules`). Notausstieg: `git commit --no-verify`.

## 7. Anti-Drift (kein neues Rad)

- **Erst suchen, dann bauen:** kein neues Skript/Tool/Doku-File, wenn ein
  vorhandenes dasselbe tut. Ein zweites Start-Skript für denselben Dienst, eine
  zweite Anleitung, eine zweite Versionsangabe ist der Fehlerfall, nicht die Lösung.
- **Eine Quelle der Wahrheit:** Versionen gepinnt im Repo (§3), Regeln in *dieser*
  Datei. Keine Kopie anlegen, die auseinanderlaufen kann.
- **Nested `AGENTS.md`** (vendored Unterordner) sind erlaubt, müssen aber einen
  MAIN-Hinweis mit den Abweichungen vom Upstream tragen und dürfen keinen
  Upstream-Stand behaupten.
- **Client-Kopien** (`GEMINI.md`, `CLAUDE.md`, `.cursorrules`, …) sind im
  MAIN-Root verboten. In vendored Unterordnern ist genau **eine** Quelle erlaubt
  — ein File oder ein Symlink-Verbund (siehe `llm-proxies/antigravity-proxy/`),
  nie ein divergierender zweiter Regeltext. `verify-codespace.sh` prüft beides.
