# Makefile: EIN Einstiegspunkt für die Checks (AGENTS.md §6).
#
# Warum es das gibt (2026-10-01): die_checks lagen an vier Stellen verteilt —
# AGENTS.md-Tabelle, .githooks/pre-commit, verify-codespace.sh und zerokeys
# package.json. Nichts hat geprueft, ob die vier noch uebereinstimmen. `make
# check` ist ab jetzt der eine Befehl; die Einzelausschreibungen bleiben
# bestehen, weil der Hook nu die *angefasste* Sprache pruefen soll.
#
# Grundregel: dieses Makefile dupliziert KEINE Check-Liste. Jedes Target ruft
# exakt die Kommandos auf, die auch .githooks/pre-commit fahrt. Der Check
# "Makefile deckt Hook ab" in verify-codespace.sh vergleicht beide Dateien und
# wird rot, sobald sie auseinanderlaufen.
#
# Alle Kommandos laufen durch infra/scripts/timeout.sh (AGENTS.md §4: nichts
# ohne Timer). `make help` listet die Targets.

SHELL := /bin/bash
ROOT  := $(CURDIR)
# ABSOLUT, weil die Recipes mit `cd` in Unterordner wechseln — ein relativer
# Pfad waere dort schon beim ersten Target kaputt (live beim ersten Lauf).
TIMEOUT := $(ROOT)/infra/scripts/timeout.sh

GLMAPI      := llm-proxies/glm2api
ANTIGRAVITY := llm-proxies/antigravity-proxy
ZEROKEY     := llm-proxies/zerokey

GO     := $(if $(wildcard /usr/local/go/bin/go),/usr/local/go/bin/go,go)
GOFMT  := $(if $(wildcard /usr/local/go/bin/gofmt),/usr/local/go/bin/gofmt,gofmt)

# Zielverzeichnis fuer osv-scanner. Leer lassen fuer /usr/local/bin ( braucht
# sudo ); fuer eine installation ohne sudo z.B. OSV_DEST=$$HOME/.local/bin/osv-scanner
OSV_DEST ?=

.PHONY: help check check-fast verify verify-code smoke check-all ci \
        lint-py test-py lint-go test-go lint-js lint-zk test-zk syntax-sh \
        lint-py-infra mypy-infra test-infra cov cov-floor shellcheck shellcheck-baseline \
        deps deps-audit osv-install

## help: alle Targets mit Kurzbeschreibung
help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/^## /  /'

## check: alle Schnell-Checks inkl. Tests (der vollstaendige Gate-Lauf)
check: check-fast test-py test-go test-zk test-infra
	@echo "make check: alles gruen."

## check-fast: nur Lint/Syntax, ohne Tests — das ist das Hook-Niveau
check-fast: lint-py lint-py-infra mypy-infra lint-go lint-js syntax-sh shellcheck

## verify: verify-codespace.sh (read-only, prueft die LAUFENDE Kette)
verify:
	cd $(ROOT) && $(TIMEOUT) run 300 ./infra/scripts/verify-codespace.sh

## verify-code: nur der Quellcode-Teil von verify-codespace.sh.
# Braucht keine laufenden Dienste, kein Bundle, kein Netz — genau der Modus,
# den ein GitHub-Actions-Runner fahren kann (PLAN Stufe 1/2).
verify-code:
	cd $(ROOT) && $(TIMEOUT) run 300 ./infra/scripts/verify-codespace.sh --code

## smoke: echter Live-Smoke-Test gegen den laufenden glm2api (dauert Minuten)
smoke:
	cd $(ROOT) && $(TIMEOUT) run 400 bash ./llm-proxies/scripts/smoke-test.sh

## check-all: check + verify (Quelle + laufende Kette in einem Lauf)
check-all: check verify

## ci: exakt das, was .github/workflows/checks.yml fahren soll. Ohne Dienste,
# ohne Secrets, ohne Netz — ein Runner kann das. Wenn das hier gruen ist und der
# Workflow rot, ist einer von beiden kaputt (das ist der Zweck: zwei Wege, eine
# Wahrheit).
ci: check verify-code deps

## deps: Lockfile-Drift ueber alle drei Oekosysteme (hart, kein Netz noetig).
# `uv lock --check` (Root + glm2api), `go mod verify`, `pnpm install
# --frozen-lockfile`. Faellt fehl, sobald jemand ohne Lockfile-Update pinnt.
deps:
	cd $(ROOT) && $(TIMEOUT) run 400 bash ./infra/scripts/deps-check.sh

## deps-audit: CVE-Report (WEICH, endet immer mit 0). Ein CVE ohne erreichbare
# Codeposition soll den Agenten nicht blockieren; Updates bleiben manuelle
# Entscheidung (D-12). Benoetigt einmalig: sudo make osv-install
deps-audit:
	cd $(ROOT) && $(TIMEOUT) run 400 bash ./infra/scripts/deps-check.sh --audit

## osv-install: CVE-Waechter gepinnt + pruefsummenverifiziert installieren
osv-install:
	cd $(ROOT) && bash ./infra/scripts/osv-install.sh $(OSV_DEST)

## lint-py: glm2api mit ruff + mypy (identisch zum Hook)
lint-py:
	cd $(GLMAPI) && $(TIMEOUT) run 120 uv run ruff check .
	cd $(GLMAPI) && $(TIMEOUT) run 180 uv run mypy src

## test-py: glm2api-Testsuite
test-py:
	cd $(GLMAPI) && $(TIMEOUT) run 900 uv run pytest -q

# --- MAIN-eigenes Python (Root-pyproject.toml, PLAN Stufe 3) ---------------
# Zweite, kleine Python-Umgebung: sie deckt infra/scripts + infra/tests ab und
# fasst die Vendor-Baeume nicht an (extend-exclude). mypy lief hier zuerst nur
# als Bestandsaufnahme und war sofort gruen — deshalb ist es jetzt ein Gate.

## lint-py-infra: ruff ueber infra/ (Ausschluss der Vendor-Baeume in pyproject)
lint-py-infra:
	cd $(ROOT) && $(TIMEOUT) run 120 uv run ruff check .

## mypy-infra: mypy ueber infra/scripts
mypy-infra:
	cd $(ROOT) && $(TIMEOUT) run 180 uv run mypy

## test-infra: Tests der infra-Python-Skripte (Ebene 1 aus PLAN 6b)
test-infra:
	cd $(ROOT) && $(TIMEOUT) run 300 uv run pytest -q

## cov: Coverage-Zahlen fuer infra/scripts (Bestandsaufnahme, kein Floor)
cov:
	cd $(ROOT) && $(TIMEOUT) run 300 uv run pytest -q --cov --cov-report=term-missing

## cov-floor: Gate fuer die getestete Datei. Bewusst pro Datei, nicht global:
# freebuff-pty.py (571 LOC, PTY + Subprozesse) und watch-subagent.py sind ohne
# PTY-Mock nicht sinnvoll abzudecken — eine hohe Zahl waere Pseudosicherheit
# (PLAN Stufe 3). Die Einengung passiert ueber infra/coverage-floor.rc, damit
# `make cov` weiterhin alle drei Dateien zeigt.
cov-floor:
	cd $(ROOT) && $(TIMEOUT) run 300 uv run pytest -q --cov --cov-config=infra/coverage-floor.rc --cov-report=term-missing

## lint-go: antigravity-proxy mit go vet + gofmt -l (read-only, wie im Hook)
lint-go:
	cd $(ANTIGRAVITY) && $(TIMEOUT) run 180 $(GO) vet ./...
	@un="$$(cd $(ANTIGRAVITY) && $(GOFMT) -l . 2>/dev/null | grep -v '^vendor/' || true)"; \
	  if [ -n "$$un" ]; then echo "gofmt noetig: $$un"; exit 1; fi

## test-go: antigravity-proxy-Testsuite
test-go:
	cd $(ANTIGRAVITY) && $(TIMEOUT) run 600 $(GO) test ./...

## lint-js: MAIN-eigenes JS mit node --check (identisch zum Hook)
lint-js:
	@cd $(ROOT) && files=$$(git ls-files '*.js' | grep '^infra/' || true); \
	 if [ -z "$$files" ]; then echo "keine infra-JS-Dateien"; exit 0; fi; \
	 echo "$$files" | xargs -r -n1 node --check && echo "infra-JS ok"

## lint-zk: zerokey mit pnpm lint + pnpm check (braucht node_modules)
lint-zk:
	cd $(ZEROKEY) && pnpm lint
	cd $(ZEROKEY) && pnpm check

## test-zk: zerokey-Testsuite
test-zk:
	cd $(ZEROKEY) && $(TIMEOUT) run 600 pnpm test

## syntax-sh: bash -n ueber alle getrackten Shell-Skripte
syntax-sh:
	@cd $(ROOT) && files=$$(git ls-files '*.sh'); \
	 echo "$$files" | xargs -r -n1 bash -n && echo "bash -n ok ($$(echo "$$files" | wc -l) Skripte)"

## shellcheck: Shellcheck gegen die eingefrorene Baseline — nur NEUE Befunde
# sind rot. `bash -n` faengt Syntax, shellcheck faengt die echten Shell-Fehler
# (unquoted, set -u, cd ohne ||, Subshell-Fallen). 30 Befunde sind eingefroren,
# damit das Gate benutzbar bleibt (PLAN Stufe 4).
shellcheck:
	cd $(ROOT) && $(TIMEOUT) run 300 bash ./infra/scripts/shellcheck-check.sh

## shellcheck-baseline: Baseline bewusst neu einfrieren — nur wenn ein Befund
# bleiben soll. Mit Begruendung im Commit, sonst schrumpft sie still.
shellcheck-baseline:
	cd $(ROOT) && $(TIMEOUT) run 300 bash ./infra/scripts/shellcheck-check.sh --update