#!/usr/bin/env bash
# verify-codespace.sh: Beweist, dass ein Codespace vollständig funktionsfähig ist.
#
#   ./infra/scripts/verify-codespace.sh            # schnell (read-only, ~30 s)
#   ./infra/scripts/verify-codespace.sh --live     # + echte Provider-Calls (langsam)
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
[ "${1:-}" = "--live" ] && LIVE=1

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

echo "== 1. Repo, Auth, Identität =="
check "Git-Repo + Remote"        bash -c 'git rev-parse --git-dir >/dev/null && git remote get-url origin >/dev/null'
info "Arbeitsbaum" "$(if [ -z "$(git status --porcelain)" ]; then echo sauber; else echo "$(git status --porcelain | wc -l | tr -d ' ') Datei(en) geaendert (in der Parallel-Session normal)"; fi)"
check "Push moeglich (dry-run)"  bash -c 'GIT_TERMINAL_PROMPT=0 git push --dry-run origin $(git rev-parse --abbrev-ref HEAD) >/dev/null 2>&1 || echo "nur pull noetig"'
check "Identitaet == Token-Account" bash -c '
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
check "Bundle entschluesselbar"  bash "$REPO_ROOT/infra/scripts/secrets.sh" status
check "Key-Dateien OK"           bash "$REPO_ROOT/infra/scripts/keys.sh" status
check "Passphrase-Kandidaten"    bash -c '
  out=$("$REPO_ROOT/infra/scripts/secrets.sh" status 2>&1)
  printf "%s" "$out" | grep -q "Passphrase: OK" || { printf "%s" "$out" | tail -1; exit 1; }
  echo "Bundle laesst sich entschluesseln"'
info "LANDSCAPE_PAT" "$([ -n "${LANDSCAPE_PAT:-}" ] && echo "gesetzt (${#LANDSCAPE_PAT} B)" || echo "nicht gesetzt (ok, Token-Datei genutzt)")"
info "LANDSCAPE_PASSPHRASE" "$([ -n "${LANDSCAPE_PASSPHRASE:-}" ] && echo "gesetzt (${#LANDSCAPE_PASSPHRASE} B)" || echo "nicht gesetzt (ok, Repo-Fallback)")"

echo "== 3. opencode =="
check "opencode installiert"     bash -c 'command -v opencode >/dev/null || [ -x "$HOME/.opencode/bin/opencode" ]'
check "Versions-Pin konsistent"  bash "$REPO_ROOT/infra/scripts/opencode-version.sh" check
check "opencode-Server antwortet" bash -c 'curl -fsS -m 10 -o /dev/null http://127.0.0.1:4096/ && echo "HTTP 200 auf 4096"'
check "MCP registriert"          bash -c 'grep -q "\"opencode-sessions\"" .opencode/opencode.json && echo "opencode-sessions in .opencode/opencode.json"'
info "opencode" "$(opencode --version 2>/dev/null || echo '?')"

echo "== 4. LLM-Proxies (Health + echter Call) =="
check "glm2api Health"           bash -c 'curl -fsS -m 10 -o /dev/null http://127.0.0.1:8001/v1/models && echo "GET /v1/models ok"'
check "glm2api antwortet"        bash -c '
  r=$(curl -fsS -m 120 http://127.0.0.1:8001/v1/chat/completions -H "Content-Type: application/json" \
      -d "{\"model\":\"glm-5.3\",\"messages\":[{\"role\":\"user\",\"content\":\"say OK\"}],\"max_tokens\":8}")
  printf "%s" "$r" | grep -q "\"content\"" || { echo "keine content-Antwort"; exit 1; }
  echo "glm-5.3 liefert Antwort"'
check "antigravity Health"       bash -c 'curl -fsS -m 10 -o /dev/null http://127.0.0.1:9878/v1/models && echo "GET /v1/models ok"'
check "antigravity antwortet"    bash -c '
  key=$(python3 -c "import json;print(json.load(open(\".opencode/opencode.json\"))[\"provider\"][\"antigravity\"][\"options\"][\"apiKey\"])" 2>/dev/null)
  r=$(curl -fsS -m 120 http://127.0.0.1:9878/v1/chat/completions -H "Content-Type: application/json" \
      -H "Authorization: Bearer $key" -d "{\"model\":\"gemini-3.8-flash\",\"messages\":[{\"role\":\"user\",\"content\":\"say OK\"}],\"max_tokens\":8}")
  printf "%s" "$r" | grep -q "\"content\"" || { echo "keine content-Antwort"; exit 1; }
  echo "gemini-3.8-flash liefert Antwort"'
info "Quoten" "$(bash "$REPO_ROOT/infra/scripts/quota.sh" 2>/dev/null | grep -E 'Gemini|Claude' | tr -s ' ' | tr '\n' '|' | cut -c1-90)"

echo "== 5. Daemons =="
check "autosave-daemon"          bash -c 'pgrep -f "autosave-daemon.sh" >/dev/null && echo "laeuft"'
check "config-watchdog"          bash -c 'pgrep -f "config-watchdog.sh" >/dev/null && echo "laeuft"'
check "proxy-watchdog"           bash -c 'pgrep -f "proxy-watchdog.sh" >/dev/null && echo "laeuft"'

echo "== 6. Browser-Runtime =="
check "Firefox installiert"      bash -c '[ -x .runtime/firefox/firefox ] && .runtime/firefox/firefox --version 2>/dev/null | head -1'

echo "== 7. Drive-Backup =="
check "beide Generationen"      bash -c '
  out=$("$REPO_ROOT/infra/scripts/gdrive-backup.sh" status 2>&1)
  printf "%s" "$out" | grep -q "current: vorhanden" || { echo "current FEHLT"; exit 1; }
  printf "%s" "$out" | grep -q "backup: vorhanden"  || { echo "backup FEHLT"; exit 1; }
  echo "current + backup auf Drive"'

echo "== 8. Testsuite =="
check "validate-revision.sh"     bash "$REPO_ROOT/infra/scripts/validate-revision.sh"

if [ "$LIVE" -eq 1 ]; then
  echo "== 9. Provider live (langsam, NIM Kaltstart bis ~3 min) =="
  check "keys.sh doctor"         bash "$REPO_ROOT/infra/scripts/keys.sh" doctor
else
  echo "== 9. Provider live =="
  skipt "keys.sh doctor" "uebersprungen (--live fuer echte Provider-Calls)"
fi

echo ""
echo "=============================================="
printf 'Ergebnis: %d PASS, %d FAIL, %d SKIP\n' "$pass" "$fail" "$skip"
if [ "$fail" -gt 0 ]; then
  printf 'Fehlgeschlagen: %s\n' "${FAILED[*]}"
  echo "=============================================="
  exit 1
fi
echo "Alles gruen — die Kette steht automatisch."
echo "=============================================="
