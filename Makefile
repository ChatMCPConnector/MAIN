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

.PHONY: help check check-fast verify verify-code smoke check-all ci \
        lint-py test-py lint-go test-go lint-js lint-zk test-zk syntax-sh

## help: alle Targets mit Kurzbeschreibung
help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/^## /  /'

## check: alle Schnell-Checks inkl. Tests (der vollstaendige Gate-Lauf)
check: check-fast test-py test-go test-zk
	@echo "make check: alles gruen."

## check-fast: nur Lint/Syntax, ohne Tests — das ist das Hook-Niveau
check-fast: lint-py lint-go lint-js syntax-sh

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
ci: check verify-code

## lint-py: glm2api mit ruff + mypy (identisch zum Hook)
lint-py:
	cd $(GLMAPI) && $(TIMEOUT) run 120 uv run ruff check .
	cd $(GLMAPI) && $(TIMEOUT) run 180 uv run mypy src

## test-py: glm2api-Testsuite
test-py:
	cd $(GLMAPI) && $(TIMEOUT) run 900 uv run pytest -q

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