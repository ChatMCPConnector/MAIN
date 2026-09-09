# MAIN-Landschafts-Audit

Auditdatum: 2026-09-08
Umfang: gesamtes /workspaces/MAIN (git-Repo, 76 committete Dateien, Branch main @ 7dc23b7)
Methode: nur verifizierte Befehle, keine Spekulation. Deep-Dive glm2api-Code: siehe `glm-api-audit.md` (gleicher Tag).

---

## Executive Summary

Das Repo ist in gutem Zustand: keine Runtime-Artefakte committet (.venv, log, __pycache__, node_modules, .runtime sauber ignoriert), .git nur 1,3 MB, klare Skript-Struktur. Die drei echten Probleme: (1) das committete portable Bundle ist drifted/veraltet und der Referenz-Patch syntaktisch korrupt, (2) 40 % der README sind Changelog-Altlasten, (3) ~27 MB ephemere Log/Venv-Daten liegen im Workspace. Größtes Einsparpotenzial liegt nicht im Repo, sondern im Workspace (555 MB Playwright-Browser, 15 MB glm2api-Logs — beide jederzeit regenerierbar).

**Top-3-Befunde:**
1. `llm-proxies/dist/glm2api-bundle.zip` + `llm-proxies/patches/glm2api.patch` sind Artefakte mit Drift bzw. Defekt — neu bauen oder aus dem Repo nehmen.
2. README.md: 106 von 267 Zeilen (40 %) sind Changelog — kompaktieren.
3. `llm-proxies/glm2api/log/` (15 MB) und alte Chinesisch-Upstream-README (345 Zeilen) aufräumen.

---

## 1. Bestandsaufnahme (Ist-Zustand, verifiziert)

| Bereich | Größe | committet | Zweck |
|---|---|---|---|
| `.git` | 1,3 MB | — | Historie, 76 Dateien, `git count-objects -vH`: 866 KiB packed |
| `.runtime/` | 555 MB | nein (ignored) | Playwright Chromium 1140 (550 MB) + ffmpeg (4,9 MB) |
| `.opencode/` | 63 MB | Config ja, `node_modules` nein | opencode-Plugins (nur `@opencode-ai/plugin` als Dep) |
| `llm-proxies/` | 27 MB | 45 Dateien | glm2api-Source (git: 31), dist/ 105 KB, patches/, scripts/ |
| `llm-proxies/glm2api/.venv` | 11 MB | nein (ignored) | Python 3.14 venv, via `uv sync` regenerierbar |
| `llm-proxies/glm2api/log/` | 15 MB | nein (ignored) | Debug-Logs (Rotation vorhanden, wächst aber) |
| `infra/` | 12 MB | 14 Dateien | scripts/ (10), browser/ (nur package.json+lock committet, node_modules 12 MB untracked), mcp/ |
| `work/` | 40 KB | 5 Dateien | Kontostand-Spec + reverse-engineering Doku |
| `config/` | 16 KB | 3 Dateien | passphrase + secrets.enc + Manifest (bewusst im Repo) |
| `.secrets/` | 8 KB | nein | entlockte Klartext-Secrets (Landscapes-Auto-Unlock) |
| `.devcontainer/` | 24 KB | 4 Dateien | setup.sh, watchdog, start-on-boot, devcontainer.json |

Verifizierung: `du -sh .[!.]* */`, `git ls-files | wc -l`, `git check-ignore -v <pfad>`.

**Git-Hygiene: OK.** Kein .venv/log/pyc/egg-info/token committet (`git ls-files | grep -E "\.venv|__pycache__|node_modules|\.pyc|egg-info|\.log|token"` → leer). Größtes Blob im Repo: bundle.zip (105 KB). In der Historie liegt ein alter 41-KB-Game-Prototype (Assets/Game/RiftboundPrototype.cs) — zu klein, um eine History-Rewrite zu rechtfertigen.

---

## 2. Findings

### Kategorie LÖSCHEN (sicher, reproduzierbar wiederherstellbar)

**L-1: glm2api-Debug-Logs (15 MB)**
- Pfad: `llm-proxies/glm2api/log/` (glm2api_debug.log + .1)
- Befund: ephemere Runtime-Logs, ignoriert, Rotation vorhanden.
- Empfehlung: löschen oder auf aktuelle Datei kürzen. Rückweg: keiner nötig (entsteht bei Betrieb neu).
- Verifizierung: `du -sh llm-proxies/glm2api/log/`

**L-2: Doppelte Python-Bytecode-Caches**
- Pfad: `llm-proxies/glm2api/src/**/__pycache__/`, `src/glm2api.egg-info/`
- Befund: untracked, regenerieren sich automatisch.
- Empfehlung: darf jederzeit gelöscht werden (Platz-Gewinn marginal, eher Kosmetik bei Bundle-Kopien).

**L-3: README-Changelog-Einträge vor 2026-09-06 kürzen**
- Pfad: `README.md:162-267` (106 Zeilen Changelog, 40 % der Datei)
- Befund: Detaillierte Tagesberichte (Härtetests, Switchover-Historie) mit historischem Wert, aber Operativ-Infos (z. B. Altpfad /workspaces/glm2api, Zeile 234-242) sind nur noch Historie.
- Empfehlung: auf letzte 10-15 Einträge kürzen, Rest als `CHANGELOG.md` archivieren oder verwerfen. Ersparnis: ~70-90 Zeilen README.
- Verifizierung: `sed -n '162,267p' README.md | wc -l`

### Kategorie LÖSCHEN / NEU BAUEN (nach kurzer Rücksprache)

**L-4: Veraltetes, committetes Bundle — `llm-proxies/dist/glm2api-bundle.zip`**
- Pfad: 105 KB, committet, Build vom 2026-09-08 01:31
- Befund: MD5-Drift gegen kanonischen Source — `tool_parser.py` und `translator.py` im Bundle ≠ Source (die heutigen Parser-Fixes fehlen), `tests/test_config.py` fehlt komplett. Nutzer des Bundles bekommen veralteten Code.
- Empfehlung (Varianten): (a) Bundle aus dem Repo entfernen und nur noch on demand via `llm-proxies/scripts/build-bundle.sh` bauen — ist ohnehin ein Build-Artefakt und gehört normalerweise nicht in git; oder (b) nach Patch-Fix (L-5) neu bauen und committen.
- Verifizierung: `unzip -p llm-proxies/dist/glm2api-bundle.zip glm2api-bundle/app/src/glm2api/utils/tool_parser.py | md5sum` vs. `md5sum llm-proxies/glm2api/src/glm2api/utils/tool_parser.py`

**L-5: Korrupter Referenz-Patch — `llm-proxies/patches/glm2api.patch`**
- Pfad: 24 KB, committet, zuletzt geändert in 7dc23b7 (heute)
- Befund: `git apply --check` schlägt fehl mit `error: corrupt patch at line 309` (Hunk endet mitten in einer List-Comprehension). Zudem drifted der Patch gegenüber dem Source (Source enthält Änderungen, die der Patch nicht abbildet, und umgekehrt).
- Empfehlung: aus aktuellem Source gegen saubere Upstream-Basis neu erzeugen oder ganz streichen — der kanonische Stand ist der Source im Repo; der Patch ist nur Referenz-/Wiederherstellungsartefakt und im jetzigen Zustand inoperabel.
- Verifizierung: `git apply --check llm-proxies/patches/glm2api.patch`

### Kategorie KOMPAKTIEREN

**K-1: glm2api-Dokumentation dreifach**
- Pfade: `llm-proxies/glm2api/README.md` (345 Zeilen, chinesisch, Upstream-Fork), `structure.md` (174 Zeilen, deutsch, aktuell), glm2api-Abschnitt in Haupt-README (Zeilen 86-121)
- Befund: structure.md ist die aktuelle Architektur-Doku; der chinesische Upstream-README enthält Anleitung zum refresh_token-Holen (F12 → Local Storage), die einzige verbliebene nützliche Info. Setup/Betrieb ist im Haupt-README und automatisiert.
- Empfehlung: chinesischen README auf die Token-Anleitung + Gast-Modus-Hinweis (~40 Zeilen) kürzen oder als `UPSTREAM.md`-Anhang in structure.md integrieren; Token-Anleitung vorher sichern ( ist die einzige Kopie).
- Verifizierung: `wc -l llm-proxies/glm2api/README.md llm-proxies/glm2api/structure.md`

**K-2: `main.py` Wrapper (Upstream-Ankündigung)**
- Pfad: `llm-proxies/glm2api/main.py` (10 Zeilen): chinesische Ankündigung + QQ-Gruppe, dann `main()` aus `__main__.py`.
- Befund: kosmetischer Upstream-Overhead; kanonischer Start (`start-glm2api.sh`, watchdog) nutzt genau diesen Pfad.
- Empfehlung: Print-Block entfernen, nur `raise SystemExit(main())` behalten (2 Zeilen). Rein optional.

**K-3: Dist-Ordner**
- Pfad: `llm-proxies/dist/` (nur die eine ZIP)
- Befund: falls L-4 mit Variante (a) umgesetzt wird, wird der Ordner leer → `.gitkeep` oder weg.

### Kategorie OPTIMIEREN

**O-1: `.env.example` fehlen 2 Variablen**
- Befund: `.env` (live) nutzt `SYSTEM_ACCESS_TOKEN` und `TOKENROUTER_API_KEY` (nur var-namen verglichen, keine Werte), die in `.env.example` nicht dokumentiert sind.
- Empfehlung: beide Keys mit Platzhalter in `.env.example` aufnehmen, sonst bricht Nachbau-Konfiguration nach Account-Wechsel.
- Verifizierung: `diff <(grep -o "^[A-Z_]*" .env.example | sort) <(cut -d= -f1 .env | grep -v "^#" | grep . | sort)`

**O-2: `infra/scripts/nvidia-models.py` (322 Zeilen) schwach integriert**
- Befund: eigenständiges Utility (NVIDIA-Modellindex von build.nvidia.com), wird von keinem anderen Skript referenziert, nur README erwähnt nvidia-Keys.
- Empfehlung: behalten (aktives Tool für Modell-Discovery), aber in README-Zeile `## Enthalten` explizit als eigenständiges Utility listen (falls nicht schon geschehen) — oder, falls ungenutzt, zur Löschung vormerken.

**O-3: Betriebsskript-Muster glm2api.sh** (aus glm-api-audit.md M-1 übernommen)
- `infra/scripts/glm2api.sh`: `pkill -f "python3 main\.py"` kann fremde Prozesse treffen; `PID_FILE` wird deklariert, aber nie genutzt; Start prüft Muster statt Health.
- Empfehlung: PID-File wirklich nutzen (atomar beim Start schreiben), vor Kill PID+Kommandozeile validieren. Details in `glm-api-audit.md` (M-1/M-2/M-3).

**O-4: `rebuild.sh` überspringt `uv sync` bei existierender .venv** (glm-api-audit.md M-3)
- Empfehlung: `uv sync --frozen` immer ausführen, Existenz reicht nicht als Frische-Indikator.

### Kategorie OK-BESTAND (bewusst unverändert)

| Pfad | Warum OK |
|---|---|
| `config/passphrase` (Klartext) | bewusstes Komfort>Sicherheit-Modell laut AGENTS.md/README — nicht ändern |
| `.secrets/` | Auto-Unlock-Zwischenlager, ignoriert, funktioniert |
| `.runtime/` 555 MB Playwright | ignoriert + regenerierbar via `infra/scripts/browser-install.sh`; Löschen spart 550 MB Platte, kostet aber Re-Download — nur bei Platznot |
| `.opencode/node_modules` 63 MB | ignoriert, npm-install-getrieben, minimal (1 Paket) |
| `infra/browser/node_modules` 12 MB | ignoriert; nur package.json+lock committet = sauber pinnt die Version |
| `infra/mcp/opencode-sessions-mcp.js` | aktiver MCP-Server (Sessions-Tools), in opencode-Config referenziert |
| `work/docs/` (Kontostand-Spec, reverse-engineering) | aktive Spec für kontostand.sh + dokumentierte RE-Ergebnisse (chat_mode-Werte, die in translator.py einfließen) |
| `.devcontainer/` 4 Skripte | untereinander konsistent, alle Referenzpfade existieren |
| Git-Historie (alter Game-Blob 41 KB) | zu klein für History-Rewrite, ignorieren |
| `llm-proxies/glm2api/uv.lock` | korrekt gepinnt, Bundle stimmt mit Source überein |

---

## 3. Querverweis-Check (alle bestanden)

- README-Dateireferenzen: alle referenzierten Pfade existieren (Skript-Check über grep + test -e).
- Skript-Verweise: jedes infra/scripts-Skript hat mind. einen aktiven Referenten (setup.sh, aliases, save, secrets, README) — kein verwaistes Skript. Ausnahme siehe O-2 (nvidia-models.py nur Eigen-Referenz).
- Altpfad `/workspaces/glm2api`: nur noch in README-Changelog (historisch korrekt), nirgendwo operativ.
- `.devcontainer/setup.sh`: alle eingebundenen Pfade (infra/browser, llm-proxies/rebuild.sh, start-glm2api.sh, watchdog) vorhanden.

---

## 4. Empfohlene Reihenfolge der Umsetzung

1. **Sofort, risikofrei:** L-1 (Logs löschen, 15 MB), L-3 (Changelog kürzen), O-1 (.env.example sync).
2. **Kurz:** L-5 (Patch neu erzeugen oder streichen), dann L-4 (Bundle neu bauen oder aus git entfernen).
3. **Gelegenheit:** K-1 (Doku-Konsolidierung glm2api), O-3/O-4 (Betriebsskripte härten — Details glm-api-audit.md).
4. **Nur bei Platznot:** .runtime (550 MB, Re-Download-Kosten).

Geschätztes Einsparpotenzial: Workspace ~28 MB sofort (Logs+venv-Caches) bzw. ~578 MB inkl. .runtime; Repo ~105 KB (Bundle aus git) plus deutlich schlankere Doku.

---

## Umsetzungsstatus (2026-09-08)

Findings aus AUDIT.md und glm-api-audit.md abgearbeitet:

- **L-1**: glm2api-Debug-Logs (15 MB) gelöscht — log/ leer, Verzeichnis bleibt.
- **L-2**: `__pycache__`-Ordner (src/tests) + `src/glm2api.egg-info` entfernt.
- **L-3**: README-Changelog gekürzt — 2026-09-04 bis 09-06 zu einem Sammel-Eintrag zusammengefasst.
- **L-4**: Bundle neu gebaut (aus kanonischem Repo-Source, Drift beseitigt).
- **L-5**: Korrupter Patch (`llm-proxies/patches/glm2api.patch`) gestrichen; alle Referenzen (README, build-bundle.sh, bundle/README.md, structure.md) angepasst; patches/-Ordner entfernt.
- **K-1**: glm2api-README (345 Zeilen chinesisch) ersetzt durch kompakte deutsche Fassung; Refresh-Token-Anleitung (F12 → Application → Local Storage → chatglm_refresh_token) erhalten.
- **K-2**: main.py-Wrapper entschlackt (chinesische QQ-Ankündigung entfernt).
- **K-3**: dist/ enthält nur die neu gebaute ZIP (kein .gitkeep nötig).
- **O-1**: .env.example um SYSTEM_ACCESS_TOKEN + TOKENROUTER_API_KEY (Platzhalter) ergänzt.
- **O-2**: nvidia-models.py als eigenständiges Utility in README „Enthalten" gelistet.
- **O-3/M-1**: infra/scripts/glm2api.sh gehärtet — PID-Datei (atomar geschrieben), gezielter Kill statt globalem pkill, Fallback mit /proc/<pid>/cwd-Pfad-Anker, Health-Check im Status.
- **M-2**: start-glm2api.sh — bei belegtem Port Health-Check; glm2api → OK/Exit 0, Fremdbelegung → Fehler-Exit ≠ 0.
- **O-4/M-3**: rebuild.sh — `uv sync --frozen` läuft immer, danach Sanity-Check (.venv/bin/python --version).
- **N-1**: Bundle enthält jetzt alle tests/*.py inkl. test_config.py (unzip verifiziert).
- **N-2**: Deterministischer Bundle-Build — feste Zeitstempel (SOURCE_DATE_EPOCH) + zip -X; Doppelbuild → identische md5.

Bewusst NICHT umgesetzt:
- `.runtime/` (555 MB Playwright-Browser) unverändert — regenerierbar via browser-install.sh, Löschen kostet nur Re-Download (nur bei Platznot).
- Git-Historie (alter Game-Blob, 41 KB) unverändert — zu klein für History-Rewrite.
- `config/passphrase` Klartext-Modell unverändert — bewusste Entscheidung (Komfort > Sicherheit).
- **pytest-Pinning**: pytest war nie im uv.lock (ad-hoc installiert) — als dev-Dependency-Group gepinnt, damit `uv sync --frozen` die Test-Runner reproduzierbar liefert.
