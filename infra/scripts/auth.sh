#!/usr/bin/env bash
# auth.sh: EINMAL pro Codespace (bzw. einmal pro Account als Codespaces-Secret) einrichten,
# danach kann der Agent jederzeit selbst pushen ohne dich zu fragen.
#
#   ./infra/scripts/auth.sh setup [TOKEN]   # Token speichern (oder ohne Arg -> versteckte Abfrage)
#   ./infra/scripts/auth.sh status          # Zeigt ob Pushen geht (ohne Token zu verraten)
#   ./infra/scripts/auth.sh identity        # Zeigt die git-Identität, die der Token setzt
#   ./infra/scripts/auth.sh clear           # Token wieder entfernen
#
# Empfohlen für mehrere Accounts: Token EINMAL als Codespaces-Secret `LANDSCAPE_PAT`
# anlegen (GitHub Settings -> Codespaces -> Secrets, Repo MAIN). Dann ist jeder neue
# Codespace automatisch authentifiziert, setup.sh verdrahtet alles von selbst.
#
# Git-Identität: wird aus dem Token ABGELEITET (Login + noreply-Adresse des Accounts),
# damit beim Account-Wechsel nicht die Identität des alten Accounts in neuen Commits
# steht. Repo-lokal, nicht global — ein Codespace, ein Account. Override via
# GIT_USER_NAME / GIT_USER_EMAIL, falls eine echte Adresse statt noreply gewünscht ist
# (Achtung: das Repo ist öffentlich, eine echte Adresse landet mit im Commit).
set -euo pipefail
TOKEN_FILE="$HOME/.config/landscape/pat"
CREDS_FILE="$HOME/.git-credentials-landscape"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

repo_slug() {
  git remote get-url origin 2>/dev/null | sed -E 's#.*github\.com[:/]([^/]+/[^/]+)(\.git)?#\1#; s/\.git$//'
}

# Identität aus dem Token ableiten: Login + <id>+<login>@users.noreply.github.com.
# noreply ist der Default, weil MAIN öffentlich ist und eine echte Mailadresse sonst
# in der Historie landet. Ohne Netz/API bleibt die bestehende Konfiguration unberührt.
gh_user_json() {
  curl -fsS --max-time 15 -H "Authorization: Bearer $1" \
    -H "Accept: application/vnd.github+json" https://api.github.com/user 2>/dev/null || true
}

token_resolves() {
  printf '%s' "$(gh_user_json "$1")" | grep -q '"login"'
}

sync_git_identity() {
  local token="$1" who login id
  who="$(gh_user_json "$token")"
  login="$(printf '%s' "$who" | sed -nE 's/.*"login"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' | head -1)"
  id="$(printf '%s' "$who" | sed -nE 's/.*"id"[[:space:]]*:[[:space:]]*([0-9]+).*/\1/p' | head -1)"
  if [ -z "$login" ] || [ -z "$id" ]; then
    echo "    git-Identität: Token nicht auflösbar (offline?) — bestehende Konfiguration bleibt."
    return 0
  fi
  local name="${GIT_USER_NAME:-$login}" email="${GIT_USER_EMAIL:-${id}+${login}@users.noreply.github.com}"
  git -C "$REPO_ROOT" config --local user.name "$name"
  git -C "$REPO_ROOT" config --local user.email "$email"
  echo "    git-Identität: $name <$email>  (aus Token-Account, repo-lokal)"
}

store_token() {
  local token="$1"
  mkdir -p "$(dirname "$TOKEN_FILE")"
  # Ein getippter/falscher Token darf einen funktionierenden nicht ersetzen: genau
  # daran scheitert sonst jeder Push, bis der naechste Codespace neu gebaut ist.
  # Nur ersetzen, wenn der neue Token sich aufloesen laesst ODER es noch keinen gab.
  if [ -s "$TOKEN_FILE" ] && [ "$(cat "$TOKEN_FILE")" != "$token" ] \
     && ! token_resolves "$token" && token_resolves "$(cat "$TOKEN_FILE")"; then
    echo "    ABBRUCH: neuer Token laesst sich nicht aufloesen, vorhandener war gueltig."
    echo "            Bestehender Token bleibt erhalten. Nichts geaendert."
    return 1
  fi
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
  # Git-Identität an den Account binden (macht Account-Wechsel zur Nicht-Sache)
  sync_git_identity "$token"
}

cmd_setup() {
  local token="${1:-${LANDSCAPE_PAT:-${GITHUB_PAT:-${GH_TOKEN:-}}}}"
  if [ -z "$token" ]; then
    read -rsp "GitHub PAT einfügen (unsichtbar, Scope: Contents read+write auf MAIN): " token
    echo ""
  fi
  if [ -z "$token" ]; then echo "Abgebrochen: kein Token."; exit 1; fi
  if ! store_token "$token"; then
    echo "    Setup abgebrochen — der bisherige Token bleibt aktiv."
    exit 1
  fi
  echo "Gespeichert in $TOKEN_FILE (600) + gh angemeldet."
  cmd_status
}

cmd_status() {
  local slug; slug="$(repo_slug)"
  echo "Repo: $slug"
  if [ -n "${LANDSCAPE_PAT:-}" ]; then echo "Env LANDSCAPE_PAT: vorhanden"; fi
  if [ -f "$TOKEN_FILE" ]; then echo "Token-Datei: vorhanden ($(wc -c < "$TOKEN_FILE" | tr -d ' ') Zeichen)"; else echo "Token-Datei: FEHLT"; fi
  if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then echo "gh auth: OK"; else echo "gh auth: nicht angemeldet"; fi
  echo "git-Identität: $(git -C "$REPO_ROOT" config --local user.name || echo '?') <$(git -C "$REPO_ROOT" config --local user.email || echo '?')>  (aus Token-Account; ./infra/scripts/auth.sh identity)"
  echo -n "Push-Test (dry-run): "
  local out
  if out="$(GIT_TERMINAL_PROMPT=0 git push --dry-run origin main 2>&1)"; then
    echo "OK - Agent kann pushen."
  elif echo "$out" | grep -qiE "fetch first|rejected|non-fast-forward"; then
    echo "OK (Auth geht, nur 'git pull --rebase' nötig) - Agent kann pushen (save.sh pullt automatisch)."
  else
    echo "FEHLT - ./infra/scripts/auth.sh setup ausführen oder LANDSCAPE_PAT als Codespaces-Secret setzen."
    echo "$out" | head -3
    return 1
  fi
}

cmd_identity() {
  echo "git-Identität (repo-lokal, wird aus dem Token-Account abgeleitet):"
  printf '  user.name  = %s\n' "$(git -C "$REPO_ROOT" config --local user.name || echo '(nicht gesetzt)')"
  printf '  user.email = %s\n' "$(git -C "$REPO_ROOT" config --local user.email || echo '(nicht gesetzt)')"
  local tok=""
  [ -f "$TOKEN_FILE" ] && tok="$(cat "$TOKEN_FILE")"
  if [ -n "$tok" ]; then
    echo "  Token-Account: $(gh_user_json "$tok" | sed -nE 's/.*"login"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' | head -1 || true)"
  fi
  echo "  Neu ableiten:  ./infra/scripts/auth.sh setup   (liest den Token neu)"
  echo "  Override:      GIT_USER_NAME=... GIT_USER_EMAIL=... ./infra/scripts/auth.sh setup"
}

cmd_clear() {
  rm -f "$TOKEN_FILE" "$CREDS_FILE"
  git config --local --unset credential.helper || true
  echo "Token entfernt."
}

case "${1:-status}" in
  setup) shift; cmd_setup "${1:-}" ;;
  status) cmd_status ;;
  identity) cmd_identity ;;
  clear) cmd_clear ;;
  *) echo "Usage: $0 {setup [TOKEN]|status|identity|clear}"; exit 1 ;;
esac
