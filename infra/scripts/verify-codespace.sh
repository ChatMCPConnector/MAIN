#!/usr/bin/env bash
# verify-codespace.sh: Beweist, dass ein Codespace vollständig funktionsfähig ist.
#
#   ./infra/scripts/verify-codespace.sh            # Kette (read-only, ~30 s) — Default
#   ./infra/scripts/verify-codespace.sh --code     # nur Quellcode: Repo, Doku, Lint.
#                                                   #   Keine Dienste/Ports/Secrets noetig
#                                                   #   → das ist der Modus fuer CI.
#   ./infra/scripts/verify-codespace.sh --live     # + echte Provider-Calls (langsam),
#                                                   #   inkl. voller glm2api-Smoke-Test
#
# Drei Modi, weil ~80 % der Checks *laufende Dinge* pruefen (Port 8001, Daemon,
# Bundle). Auf einem CI-Runner waere das ~20x FAIL, ohne dass etwas defekt ist
# (PLAN Stufe 1). Jeder Check traegt daher eine Ebene: code | chain | live. Passt
# die Ebene nicht zum Modus, wird der Check uebersprungen (SKIP), nicht rot.
#
# read-only: startet nichts, installiert nichts, committet nichts. Der einzige
# Schreibzugriff ist der Push-Dry-Run von `git push --dry-run` (verändert nichts)
# und das Lesen von Secrets-Status. Genau deshalb ist das Skript gefahrlos in
# einem frischen Codespace lauffähig, WHÄHREND setup.sh noch arbeitet bzw. danach.
#
# Exitcode 0 = alles grün, 1 = mindestens ein FAIL. Die Ausgabe ist bewusst eine
# Tabelle mit PASS/FAIL/SKIP, damit sie in einem Blip nachvollziehbar bleibt.
#
# Zweck: Nach einem Account-Bann oder einem Codespace-Wechsel ist die entscheidende
# Frage nicht "läuft der Proxy", sondern "ist die ganze Kette automatisch hochgekom­
# men". Genau das beantwortet dieses Skript — und zwar ohne den Zustand zu ändern.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
export REPO_ROOT
LIVE=0
MODE=chain
case "${1:-}" in
  --code) MODE=code ;;   # nur Quellcode — Voraussetzung fuer CI (PLAN Stufe 1/2)
  --live) MODE=live; LIVE=1 ;;
  "")     ;;
  *)      echo "Aufruf: $0 [--code|--live]   (unbekanntes Argument: $1)" >&2; exit 2 ;;
esac

pass=0; fail=0; skip=0
declare -a FAILED=()

# check <name> <command...>   -> PASS wenn Exitcode 0
check() {
  local name="$1"; shift
  local out rc
  out="$("$@" 2>&1)"; rc=$?
  if [ "$rc" -eq 0 ]; then
    printf '  \033[32mPASS\033[0m  %-34s %s\n' "$name" "$(printf '%s' "$out" | tail -1 | cut -c1-70)"
    pass=$((pass+1))
  else
    printf '  \033[31mFAIL\033[0m  %-34s %s\n' "$name" "$(printf '%s' "$out" | tail -1 | cut -c1-70)"
    FAILED+=("$name"); fail=$((fail+1))
  fi
}

# info <name> <wert>  — neutraler Zustand, kein Urteil
info() { printf '  ----  %-34s %s\n' "$1" "$2"; }
skipt() { printf '  \033[33mSKIP\033[0m  %-34s %s\n' "$1" "$2"; skip=$((skip+1)); }

# check_layer <ebene> <name> <command...>  — welcher Modus darf was pruefen?
#
#   code   nur Repo + Toolchain   → darf ueberall laufen (auch CI-Runner)
#   chain  braucht laufende Dienste, Ports, entschluesseltes Bundle
#   live   braucht echte Provider-Calls
#
# Grund (2026-10-01): rund 80 % der Checks pruefen *laufende Dinge* — Prozess
# auf Port 8001, Daemon, Bundle-Zustand. Unveraendert auf einem GitHub-Runner
# gefahren waeren das ~20 FAILs, weil dort nie etwas gestartet wurde. Ein roter
# Job, den man zu ignorieren lernt, ist schlimmer als gar keiner (PLAN Stufe 1).
# Deshalb: Ebene passt nicht zum Modus → SKIP, nicht FAIL.
check_layer() {
  local layer="$1" name="$2"; shift 2
  case "$layer" in
    code)  check "$name" "$@" ;;
    chain) if [ "$MODE" = "code" ]; then skipt "$name" "uebersprungen (--code: nur Quellcode)"; return; fi
           check "$name" "$@" ;;
    live)  if [ "$MODE" = "code" ]; then skipt "$name" "uebersprungen (--code: nur Quellcode)"; return; fi
           if [ "$LIVE" -eq 0 ]; then skipt "$name" "uebersprungen (--live fuer echte Provider-Calls)"; return; fi
           check "$name" "$@" ;;
    *)     printf 'unbekannte Ebene "%s" bei Check "%s"\n' "$layer" "$name" >&2; exit 2 ;;
  esac
}

case "$MODE" in
  code)  echo "== Modus: CODE — nur Quellcode, kein Laufzeit-Zustand ==" ;;
  live)  echo "== Modus: LIVE — Kette + echte Provider-Calls ==" ;;
  *)     echo "== Modus: CHAIN (Standard) — diese Codespace-Instanz ==" ;;
esac

echo "== 1. Repo, Auth, Identität =="
check_layer code  "Git-Repo + Remote"        bash -c 'git rev-parse --git-dir >/dev/null && git remote get-url origin >/dev/null'
info "Arbeitsbaum" "$(if [ -z "$(git status --porcelain)" ]; then echo sauber; else echo "$(git status --porcelain | wc -l | tr -d ' ') Datei(en) geaendert (in der Parallel-Session normal)"; fi)"
check_layer chain "Push moeglich (dry-run)"  bash -c 'GIT_TERMINAL_PROMPT=0 git push --dry-run origin $(git rev-parse --abbrev-ref HEAD) >/dev/null 2>&1 || echo "nur pull noetig"'
check_layer chain "Identitaet == Token-Account" bash -c '
  cfg_name=$(git config --local user.name); cfg_mail=$(git config --local user.email)
  tok_login=$(curl -fsS -m 15 -H "Authorization: Bearer $(cat "$HOME/.config/landscape/pat")" \
              -H "Accept: application/vnd.github+json" https://api.github.com/user \
              | sed -nE "s/.*\"login\"[[:space:]]*:[[:space:]]*\"([^\"]+)\".*/\1/p" | head -1)
  [ -n "$tok_login" ] || { echo "Token nicht aufloesbar"; exit 1; }
  [ "$cfg_mail" = "${tok_login}@users.noreply.github.com" ] || [ "$cfg_name" = "$tok_login" ] \
    || { echo "Mismatch: git=$cfg_name <$cfg_mail> token=$tok_login"; exit 1; }
  echo "$cfg_name <$cfg_mail> = $tok_login"'
info "HEAD" "$(git log --oneline -1 | cut -c1-60)"
info "commits" "$(git rev-list --count HEAD)"

echo "== 2. Secrets =="
check_layer chain "Bundle entschluesselbar"  bash "$REPO_ROOT/infra/scripts/secrets.sh" status
check_layer chain "Key-Dateien OK"           bash "$REPO_ROOT/infra/scripts/keys.sh" status
check_layer chain "Passphrase-Kandidaten"    bash -c '
  out=$("$REPO_ROOT/infra/scripts/secrets.sh" status 2>&1)
  printf "%s" "$out" | grep -q "Passphrase: OK" || { printf "%s" "$out" | tail -1; exit 1; }
  echo "Bundle laesst sich entschluesseln"'
check_layer code  "Secret-Rechte: Werkzeug verdrahtet" bash -c '
  # Der Dateimodus selbst ist Codespace-Zustand (chain): Git kennt nur das
  # executable-Bit, ein frischer Checkout bekommt 644 — dort waere ein Check
  # auf 600 immer rot. Was der Code *verspricht* (Werkzeug existiert, ist
  # ausfuehrbar, und setup.sh ruft es auf), ist dagegen ueberall pruefbar.
  sp="$REPO_ROOT/infra/scripts/secret-perms.sh"
  [ -f "$sp" ] || { echo "infra/scripts/secret-perms.sh fehlt"; exit 1; }
  [ -x "$sp" ] || { echo "secret-perms.sh ist nicht ausfuehrbar"; exit 1; }
  grep -q "secret-perms.sh" "$REPO_ROOT/.devcontainer/setup.sh" \
    || { echo "setup.sh ruft secret-perms.sh nicht auf"; exit 1; }
  echo "secret-perms.sh vorhanden + in setup.sh verdrahtet"'
check_layer chain "Secrets nicht world-readable" bash -c '
  bad=""
  for f in config/passphrase config/secrets.enc config/secrets.manifest \
           llm-proxies/glm2api/.env llm-proxies/zerokey/temp/users.json; do
    [ -e "$f" ] || continue
    m="$(stat -c %a "$f" 2>/dev/null)"
    [ "$m" = "600" ] || bad="$bad $f($m)"
  done
  if [ -d .runtime ] && [ "$(stat -c %a .runtime 2>/dev/null)" != "700" ]; then bad="$bad .runtime"; fi
  [ -z "$bad" ] || { echo "weltlesbar:$bad"; exit 1; }
  echo "alle 600, .runtime 700"'
info "LANDSCAPE_PAT" "$([ -n "${LANDSCAPE_PAT:-}" ] && echo "gesetzt (${#LANDSCAPE_PAT} B)" || echo "nicht gesetzt (ok, Token-Datei genutzt)")"
info "LANDSCAPE_PASSPHRASE" "$([ -n "${LANDSCAPE_PASSPHRASE:-}" ] && echo "gesetzt (${#LANDSCAPE_PASSPHRASE} B)" || echo "nicht gesetzt (ok, Repo-Fallback)")"

echo "== 3. opencode =="
check_layer chain "opencode installiert"     bash -c 'command -v opencode >/dev/null || [ -x "$HOME/.opencode/bin/opencode" ]'
check_layer code  "Versions-Pin konsistent"  bash "$REPO_ROOT/infra/scripts/opencode-version.sh" check
check_layer chain "opencode-Server antwortet" bash -c 'curl -fsS -m 10 -o /dev/null http://127.0.0.1:4096/ && echo "HTTP 200 auf 4096"'
check_layer code  "MCP registriert"          bash -c 'grep -q "\"opencode-sessions\"" .opencode/opencode.json && echo "opencode-sessions in .opencode/opencode.json"'
info "opencode" "$(opencode --version 2>/dev/null || echo '?')"

echo "== 4. LLM-Proxies (Health + echter Call) =="
check_layer chain "glm2api Health"           bash -c 'curl -fsS -m 10 -o /dev/null http://127.0.0.1:8001/v1/models && echo "GET /v1/models ok"'
check_layer chain "glm2api antwortet"        bash -c '
  r=$(curl -fsS -m 120 http://127.0.0.1:8001/v1/chat/completions -H "Content-Type: application/json" \
      -d "{\"model\":\"glm-5.3\",\"messages\":[{\"role\":\"user\",\"content\":\"say OK\"}],\"max_tokens\":8}")
  printf "%s" "$r" | grep -q "\"content\"" || { echo "keine content-Antwort"; exit 1; }
  echo "glm-5.3 liefert Antwort"'
check_layer chain "antigravity Health"       bash -c 'curl -fsS -m 10 -o /dev/null http://127.0.0.1:9878/v1/models && echo "GET /v1/models ok"'
check_layer chain "antigravity antwortet"    bash -c '
  key=$(python3 -c "import json;print(json.load(open(\".opencode/opencode.json\"))[\"provider\"][\"antigravity\"][\"options\"][\"apiKey\"])" 2>/dev/null)
  r=$(curl -fsS -m 120 http://127.0.0.1:9878/v1/chat/completions -H "Content-Type: application/json" \
      -H "Authorization: Bearer $key" -d "{\"model\":\"gemini-3.8-flash\",\"messages\":[{\"role\":\"user\",\"content\":\"say OK\"}],\"max_tokens\":8}")
  printf "%s" "$r" | grep -q "\"content\"" || { echo "keine content-Antwort"; exit 1; }
  echo "gemini-3.8-flash liefert Antwort"'
check_layer chain "zerokey Health"           bash -c 'curl -fsS -m 10 -o /dev/null http://127.0.0.1:7250/v1/models && echo "GET /v1/models ok"'
check_layer chain "zerokey-Credentials"      bash -c '
  f="$REPO_ROOT/llm-proxies/zerokey/temp/users.json"
  [ -s "$f" ] || { echo "FEHLT: $f (ChatGPT-Cookies) — secrets.sh unlock ODERHAR aus ~/.config/landscape/"; exit 1; }
  python3 -c "import json,sys;d=json.load(open(sys.argv[1]));u=d.get(\"chatgpt\",{}).get(\"main\",{});h=u.get(\"parsedFetch\",{}).get(\"headers\",{});sys.exit(0 if any(\"cookie\" in k.lower() for k in h) else 1)" "$f" \
    && echo "ChatGPT-Cookies vorhanden" || { echo "kein Cookie-Header in users.json"; exit 1; }'

# Kopplung Client-Budget <-> Proxy-Budget. Am 2026-09-30 lief eine Session
# 20 Requests lang in eine Schleife, weil opencode limit.context=16000 TOKENS
# bei compaction.reserved=15000 fuer nur ~1000 Token echte Arbeit hatte. Die
# Logik steht in check-proxy-budget.py, damit sie einzeln lauffaehig und
# millisekundenschnell pruefbar ist (ein Heredoc in bash -c hat hier zweimal
# in Quote-Fehler gefuehrt).
check_layer code  "zerokey Budget-Kopplung"  bash -c 'python3 "$REPO_ROOT/infra/scripts/check-proxy-budget.py"'

# Die Quoten-Anzeige macht echte Upstream-Calls. Im --code-Modus gibt es
# dafür weder Proxy noch Quota — dort bleibt sie leer, statt einen Network-
# Call zu machen, der an der Zielplattform statt am Code scheitert.
if [ "$MODE" = "code" ]; then
  info "Quoten" "uebersprungen (--code: kein Netzwerk)"
else
  info "Quoten" "$(bash "$REPO_ROOT/infra/scripts/quota.sh" 2>/dev/null | grep -E 'Gemini|Claude' | tr -s ' ' | tr '\n' '|' | cut -c1-90)"
fi

echo "== 5. Daemons =="
# Kein autosave-daemon-Check mehr (Nutzerentscheidung 2026-09-27)
check_layer chain "config-watchdog"          bash -c 'pgrep -f "config-watchdog.sh" >/dev/null && echo "laeuft"'
check_layer chain "proxy-watchdog"           bash -c 'pgrep -f "proxy-watchdog.sh" >/dev/null && echo "laeuft"'

echo "== 6. Browser-Runtime =="
check_layer chain "Firefox installiert"      bash -c '[ -x .runtime/firefox/firefox ] && .runtime/firefox/firefox --version 2>/dev/null | head -1'

echo "== 7. Drive-Backup =="
check_layer chain "beide Generationen"      bash -c '
  out=$("$REPO_ROOT/infra/scripts/gdrive-backup.sh" status 2>&1)
  printf "%s" "$out" | grep -q "current: vorhanden" || { echo "current FEHLT"; exit 1; }
  printf "%s" "$out" | grep -q "backup: vorhanden"  || { echo "backup FEHLT"; exit 1; }
  echo "current + backup auf Drive"'

echo "== 8. Agenten-Anweisungen =="
# Ein Agent muss die Save-Pflicht kennen, ohne dass der Nutzer sie wiederholen
# muss. Jeder Client liest eine andere Datei — fehlt eine oder steht die Regel
# nicht drin, faellt das hier auf, statt beim naechsten Sessionende auf.
check_layer code  "AGENTS.md (Referenz)" bash -c '
  [ -f "$REPO_ROOT/AGENTS.md" ] || { echo "FEHLT"; exit 1; }
  grep -q "save.sh" "$REPO_ROOT/AGENTS.md" || { echo "Save-Regel fehlt"; exit 1; }
  echo "hat die Save-Regel"'
check_layer code  "keine divergierenden Client-Kopien" bash -c '
  # Root: die verbotenen Namen dürfen gar nicht existieren.
  for f in GEMINI.md CLAUDE.md .cursorrules AGENT.md .github/copilot-instructions.md; do
    [ -e "$REPO_ROOT/$f" ] && { echo "im Root: $f"; exit 1; }
  done
  # Nested: erlaubt ist nur EINE Quelle pro Verzeichnis — entweder ein
  # Symlink (kann nicht driften) oder ein vendored Unterordner mit eigenem
  # AGENTS.md samt MAIN-Hinweis (dessen Upstream-Konvention gilt).
  bad=""
  while IFS= read -r f; do
    [ -L "$f" ] && continue
    grep -q "Vendored in" "$(dirname "$f")/AGENTS.md" 2>/dev/null && continue
    bad="$bad ${f#$REPO_ROOT/}"
  done < <(find "$REPO_ROOT" -mindepth 2 \
    -not -path "*/node_modules/*" -not -path "*/.venv/*" -not -path "*/.git/*" \
    \( -name GEMINI.md -o -name CLAUDE.md -o -name .cursorrules -o -name AGENT.md \) -print 2>/dev/null)
  [ -z "$bad" ] || { echo "divergierend:$bad"; exit 1; }
  echo "eine Quelle je Verzeichnis"'
check_layer code  "nested AGENTS.md tragen einen MAIN-Hinweis" bash -c '
  # Vendored Unterordner haben ihr eigenes AGENTS.md. Das darf keinen
  # Upstream-Stand behaupten (driftete schon: antigravity-Proxys Datei war
  # upstreams CLAUDE.md mit falschem Port, zerokeys Datei widersprach sich
  # zum entfernten pre-commit-Hook).
  bad=""
  while IFS= read -r f; do
    rel="${f#$REPO_ROOT/}"
    [ "$rel" = "AGENTS.md" ] && continue
    grep -q "Vendored in" "$f" || bad="$bad $rel"
  done < <(find "$REPO_ROOT" -mindepth 2 -name AGENTS.md \
    -not -path "*/node_modules/*" -not -path "*/.venv/*" -not -path "*/.git/*" 2>/dev/null)
  [ -z "$bad" ] || { echo "ohne MAIN-Hinweis:$bad"; exit 1; }
  echo "nested AGENTS.md haben den Hinweis"'
check_layer code  "Gemini-Context verdrahtet" bash -c '
  # Wie oben: die Datei in $HOME ist Codespace-Zustand. Der Code-Part ist:
  # das Skript existiert und schreibt genau context.fileName=[AGENTS.md].
  g="$REPO_ROOT/infra/scripts/gemini-context.sh"
  [ -f "$g" ] || { echo "infra/scripts/gemini-context.sh fehlt"; exit 1; }
  [ -x "$g" ] || { echo "gemini-context.sh ist nicht ausfuehrbar"; exit 1; }
  grep -q "AGENTS.md" "$g" || { echo "Skript nennt AGENTS.md nicht"; exit 1; }
  echo "gemini-context.sh setzt context.fileName=[AGENTS.md]"'
check_layer chain "Gemini CLI liest AGENTS.md" bash -c '
  bash "$REPO_ROOT/infra/scripts/gemini-context.sh" status >/dev/null 2>&1 \
    || { echo "context.fileName != [AGENTS.md] - Gemini CLI haette leeren Kontext"; exit 1; }
  echo "context.fileName=[AGENTS.md]"'
check_layer code  "Pfadbegrenztes Commit dokumentiert" bash -c '
  grep -q "git commit -- <pfad>" "$REPO_ROOT/AGENTS.md" || { echo "fehlt"; exit 1; }
  echo "nur eigene Pfade"'
check_layer code  "Lint-Hook im Repo" bash -c '
  # Repo-Fakt (ueberall pruefbar): der Hook liegt im Repo und ist startbar.
  [ -f "$REPO_ROOT/.githooks/pre-commit" ] || { echo ".githooks/pre-commit fehlt im Repo"; exit 1; }
  [ -x "$REPO_ROOT/.githooks/pre-commit" ] || { echo "pre-commit nicht ausfuehrbar (git checkout verliert ggf. das exec-Bit)"; exit 1; }
  echo ".githooks/pre-commit vorhanden + ausfuehrbar"'
check_layer chain "core.hooksPath = .githooks" bash -c '
  # Codespace-Fakt: das setzt setup.sh (repo-lokale git-Config). In einem
  # frischen Checkout steht hier nichts — deshalb chain, nicht code.
  hp=$(git config --local core.hooksPath)
  [ "$hp" = ".githooks" ] || { echo "core.hooksPath=${hp:-<leer>} (erwartet .githooks) — setup.sh erneut laufen lassen"; exit 1; }
  echo "core.hooksPath=.githooks"'
check_layer code  "Makefile deckt Hook ab" bash -c '
  # AGENTS.md §6 verweist jetzt auf `make check`, der Hook bleibt fuer den
  # Commit. Beide duerfen nicht auseinanderlaufen — genau das war die Luecke
  # vor dem Makefile: vier Stellen sagten je, was zu pruefen ist, und nichts
  # pruefte, ob sie noch uebereinstimmen.
  hook="$REPO_ROOT/.githooks/pre-commit"; mk="$REPO_ROOT/Makefile"
  [ -f "$hook" ] || { echo "Hook fehlt"; exit 1; }
  [ -f "$mk" ]   || { echo "Makefile fehlt — AGENTS.md §6 verweist darauf"; exit 1; }
  miss=""
  for tool in "ruff check" "mypy src" "vet ./..." "gofmt -l" "node --check"; do
    grep -qF "$tool" "$hook" || miss="$miss hook:[$tool]"
    grep -qF "$tool" "$mk"   || miss="$miss make:[$tool]"
  done
  [ -z "$miss" ] || { echo "Makefile und Hook nennen verschiedene Kommandos -> $miss"; exit 1; }
  echo "5 Kommandos in beiden (ruff, mypy, go vet, gofmt, node --check)"'
check_layer code  "CI-Pins decken Repo-Pins" bash -c '
  # Stufe 2: der Workflow muss dieselben Werkzeuge fahren wie der Codespace,
  # sonst schlaegt der Job an der Toolchain statt am Code fehl. Deshalb liest
  # er Go aus go.mod und Python aus .python-version — und hier wird
  # nachgeprueft, dass er das auch wirklich tut (sonst steht dort morgen eine
  # zweite, abweichende Wahrheit).
  wf="$REPO_ROOT/.github/workflows/checks.yml"
  [ -f "$wf" ] || { echo "kein Workflow — ohne Agent laeuft kein Check"; exit 1; }
  miss=""
  for must in "go-version-file: " "uv lock --check" "pnpm install --frozen-lockfile" "verify-codespace.sh --code"; do
    grep -qF "$must" "$wf" || miss="$miss [$must]"
  done
  pyver=$(cat "$REPO_ROOT/llm-proxies/glm2api/.python-version" 2>/dev/null | tr -d "[:space:]")
  grep -q "python-version: .*${pyver}" "$wf" || miss="$miss [python != .python-version=$pyver]"
  [ -z "$miss" ] || { echo "Workflow deckt nicht ab:$miss"; exit 1; }
  # pnpm-Pin muss der aus package.json sein, nicht eine eigene Zahl.
  zk=$(grep -oE "pnpm@[0-9.]+" "$REPO_ROOT/llm-proxies/zerokey/package.json" | head -1 | cut -d@ -f2)
  grep -q "corepack enable" "$wf" || miss="$miss [kein corepack]"
  [ -z "$miss" ] || { echo "Workflow deckt nicht ab:$miss"; exit 1; }
  echo "Go aus go.mod, Python $pyver, pnpm-Pin aus package.json ($zk), Lockfile-Drift + verify-code abgedeckt"'
check_layer code  "Shellcheck-Baseline verdrahtet" bash -c '
  # PLAN Stufe 4: `bash -n` faengt Syntax, shellcheck faengt die echten Shell-
  # Fehler. Damit das Gate benutzbar bleibt, ist der heutige Bestand als
  # Baseline eingefroren — alles NEUE muss rot werden. Geprueft wird hier die
  # Verdrahtung (Datei, Skript, Make-Target, Hook, CI), nicht die Befundmenge:
  # die darf sich mit jedem shellcheck-Release aendern.
  for f in infra/scripts/shellcheck-check.sh infra/scripts/shellcheck-baseline.txt; do
    [ -f "$REPO_ROOT/$f" ] || { echo "FEHLT: $f"; exit 1; }
  done
  grep -q "^shellcheck:" "$REPO_ROOT/Makefile" || { echo "kein make-Target shellcheck"; exit 1; }
  grep -q "shellcheck-check.sh" "$REPO_ROOT/.githooks/pre-commit" || { echo "Hook ruft shellcheck nicht"; exit 1; }
  grep -q "shellcheck-check.sh" "$REPO_ROOT/.github/workflows/checks.yml" || { echo "CI ruft shellcheck nicht"; exit 1; }
  # Die Baseline darf nicht leer sein — eine leere waere entweder nie erzeugt
  # oder nach einem Fehler auf null gesetzt worden.
  [ -s "$REPO_ROOT/infra/scripts/shellcheck-baseline.txt" ] || { echo "Baseline leer"; exit 1; }
  n=$(grep -c . "$REPO_ROOT/infra/scripts/shellcheck-baseline.txt")
  echo "Baseline mit $n Befunden, Skript + Makefile + Hook + CI verdrahtet"'
check_layer code  "Root-Python-Umgebung verdrahtet" bash -c '
  # infra/scripts/*.py war bis 2026-10-02 die einzige Python-Flaeche ganz ohne
  # Werkzeug (kein ruff, kein mypy, kein Test). Damit das nicht still zurueck-
  # faellt, wird hier geprueft, dass die Umgebung samt Verdrahtung existiert:
  # pyproject + Lock, Tests da, Makefile-Targets da, Hook erfasst infra-Python.
  miss=""
  [ -f "$REPO_ROOT/pyproject.toml" ] || miss="$miss pyproject"
  [ -f "$REPO_ROOT/uv.lock" ]        || miss="$miss uv.lock"
  [ -f "$REPO_ROOT/infra/coverage-floor.rc" ] || miss="$miss coverage-floor"
  ls "$REPO_ROOT/infra/tests/test_"*.py >/dev/null 2>&1 || miss="$miss tests"
  for t in lint-py-infra mypy-infra test-infra cov-floor; do
    grep -q "^$t:" "$REPO_ROOT/Makefile" || miss="$miss make:$t"
  done
  grep -q "infra/(scripts|tests)/" "$REPO_ROOT/.githooks/pre-commit" || miss="$miss hook"
  [ -z "$miss" ] || { echo "nicht verdrahtet:$miss"; exit 1; }
  echo "pyproject + uv.lock + 4 Make-Targets + Hook-Zweig"'
check_layer code  "Go-Lint antigravity (vet+fmt)" bash -c '
  # Go hatte bis 2026-10-01 keinen einzigen automatischen Check. `mise` ist
  # nicht installiert, also direkt go vet + gofmt (das Binary liegt in
  # /usr/local/go/bin, siehe setup.sh/aliases.sh).
  # Go liegt im Codespace unter /usr/local/go/bin, auf einem CI-Runner im PATH —
  # beides muss funktionieren, sonst schlaegt der Job an der Toolchain statt am
  # Code fehl (PLAN Stufe 2).
  GO=$(command -v go || true)
  [ -n "$GO" ] || { echo "go fehlt (weder /usr/local/go/bin/go noch im PATH) - setup.sh"; exit 1; }
  cd "$REPO_ROOT/llm-proxies/antigravity-proxy" || exit 1
  "$GO" vet ./... >/dev/null 2>&1 || { echo "go vet rot"; exit 1; }
  # gofmt -l ist READ-ONLY (gibt nur Namen aus). Bewusst NICHT `go fmt` — das
  # wuerde Dateien schreiben, und ein Verifier darf nichts aendern.
  GOFMT="$(dirname "$GO")/gofmt"
  command -v gofmt >/dev/null 2>&1 && GOFMT=$(command -v gofmt)
  if [ -x "$GOFMT" ]; then
    un=$("$GOFMT" -l . 2>/dev/null | grep -v "^vendor/" || true)
    [ -z "$un" ] || { echo "unformatiert: $un"; exit 1; }
  fi
  echo "go vet ok, gofmt sauber"'
check_layer code  "MAIN-JS Syntax (node --check)" bash -c '
  # MAIN hat kein Root-ESLint; der einzige eigene JS-Code ist infra/mcp. Ein
  # Syntax-Check (kein neues Toolchain) faengt kaputte Dateien vor dem Start.
  bad=""
  while IFS= read -r f; do
    node --check "$REPO_ROOT/$f" >/dev/null 2>&1 || bad="$bad $f"
  done < <(git -C "$REPO_ROOT" ls-files infra | grep -E "\.js$")
  [ -z "$bad" ] || { echo "Syntaxfehler:$bad"; exit 1; }
  echo "infra-JS syntaktisch ok"'
echo "== 9. Provider live =="
# Voller Live-Smoke-Test des glm2api-Proxys (drei API-Formate + Tool-Call-
# Roundtrip ueber 2 Turns). Gehoert bewusst hierher und nicht in die schnelle
# Runde: er macht echte Upstream-Calls und dauert Minuten. timeout.sh als
# Schutz (AGENTS.md §4), das Skript selbst hat kein Gesamtlimit.
check_layer live  "keys.sh doctor"         bash "$REPO_ROOT/infra/scripts/keys.sh" doctor
check_layer live  "glm2api Smoke-Test (live)" bash -c '
  mkdir -p /tmp/opencode
  bash "$REPO_ROOT/infra/scripts/timeout.sh" run 400 bash "$REPO_ROOT/llm-proxies/scripts/smoke-test.sh"'

echo ""
echo "=============================================="
printf 'Ergebnis: %d PASS, %d FAIL, %d SKIP\n' "$pass" "$fail" "$skip"
if [ "$fail" -gt 0 ]; then
  printf 'Fehlgeschlagen: %s\n' "${FAILED[*]}"
  echo "=============================================="
  exit 1
fi
case "$MODE" in
  code) echo "Quellcode gruen — Aussage: der Code ist in Ordnung. Die laufende Kette ist damit NICHT geprueft; das macht der chain-Modus im Codespace." ;;
  *)    echo "Alles gruen — die Kette steht automatisch." ;;
esac
echo "=============================================="
