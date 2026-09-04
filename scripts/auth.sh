#!/usr/bin/env bash
# auth.sh: EINMAL pro Codespace (bzw. einmal pro Account als Codespaces-Secret) einrichten,
# danach kann der Agent jederzeit selbst pushen ohne dich zu fragen.
#
#   ./scripts/auth.sh setup [TOKEN]   # Token speichern (oder ohne Arg -> versteckte Abfrage)
#   ./scripts/auth.sh status          # Zeigt ob Pushen geht (ohne Token zu verraten)
#   ./scripts/auth.sh clear           # Token wieder entfernen
#
# Empfohlen für mehrere Accounts: Token EINMAL als Codespaces-Secret `LANDSCAPE_PAT`
# anlegen (GitHub Settings -> Codespaces -> Secrets, Repo MAIN). Dann ist jeder neue
# Codespace automatisch authentifiziert, setup.sh verdrahtet alles von selbst.
set -euo pipefail
TOKEN_FILE="$HOME/.config/landscape/pat"
CREDS_FILE="$HOME/.git-credentials-landscape"

repo_slug() {
  git remote get-url origin 2>/dev/null | sed -E 's#.*github\.com[:/]([^/]+/[^/]+)(\.git)?#\1#; s/\.git$//'
}

store_token() {
  local token="$1"
  mkdir -p "$(dirname "$TOKEN_FILE")"
  printf '%s' "$token" > "$TOKEN_FILE"
  chmod 600 "$TOKEN_FILE"
  # git-Credentials für https-Push (Datei liegt AUSSERHALB des Repos -> kommt nie ins Git)
  printf 'https://x-access-token:%s@github.com\n' "$token" > "$CREDS_FILE"
  chmod 600 "$CREDS_FILE"
  git config --local credential.helper "store --file $CREDS_FILE"
  # GPG-Signing blockiert non-interactive Commits -> lokal aus (global bleibt an)
  git config --local commit.gpgsign false
  # gh CLI gleich mit anmelden (still, für API-Calls)
  if command -v gh >/dev/null 2>&1; then
    printf '%s' "$token" | gh auth login --with-token >/dev/null 2>&1 || true
  fi
}

cmd_setup() {
  local token="${1:-${LANDSCAPE_PAT:-${GITHUB_PAT:-${GH_TOKEN:-}}}}"
  if [ -z "$token" ]; then
    read -rsp "GitHub PAT einfügen (unsichtbar, Scope: Contents read+write auf MAIN): " token
    echo ""
  fi
  if [ -z "$token" ]; then echo "Abgebrochen: kein Token."; exit 1; fi
  store_token "$token"
  echo "Gespeichert in $TOKEN_FILE (600) + gh angemeldet."
  cmd_status
}

cmd_status() {
  local slug; slug="$(repo_slug)"
  echo "Repo: $slug"
  if [ -n "${LANDSCAPE_PAT:-}" ]; then echo "Env LANDSCAPE_PAT: vorhanden"; fi
  if [ -f "$TOKEN_FILE" ]; then echo "Token-Datei: vorhanden ($(wc -c < "$TOKEN_FILE" | tr -d ' ') Zeichen)"; else echo "Token-Datei: FEHLT"; fi
  if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then echo "gh auth: OK"; else echo "gh auth: nicht angemeldet"; fi
  echo -n "Push-Test (dry-run): "
  local out
  if out="$(GIT_TERMINAL_PROMPT=0 git push --dry-run origin main 2>&1)"; then
    echo "OK - Agent kann pushen."
  elif echo "$out" | grep -qiE "fetch first|rejected|non-fast-forward"; then
    echo "OK (Auth geht, nur 'git pull --rebase' nötig) - Agent kann pushen (save.sh pullt automatisch)."
  else
    echo "FEHLT - ./scripts/auth.sh setup ausführen oder LANDSCAPE_PAT als Codespaces-Secret setzen."
    echo "$out" | head -3
    return 1
  fi
}

cmd_clear() {
  rm -f "$TOKEN_FILE" "$CREDS_FILE"
  git config --local --unset credential.helper || true
  echo "Token entfernt."
}

case "${1:-status}" in
  setup) shift; cmd_setup "${1:-}" ;;
  status) cmd_status ;;
  clear) cmd_clear ;;
  *) echo "Usage: $0 {setup [TOKEN]|status|clear}"; exit 1 ;;
esac
