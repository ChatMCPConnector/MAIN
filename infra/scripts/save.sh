#!/usr/bin/env bash
# save.sh: add+commit+push in einem. Der Agent darf das jederzeit non-interaktiv laufen lassen.
#   ./infra/scripts/save.sh [commit-message]   # committen (falls nötig) + pull-rebase + push
#   ./infra/scripts/save.sh --only-push        # nur pushen, nichts committen
#   ./infra/scripts/save.sh status             # Repo-, Auth- und Secrets-Status
set -uo pipefail
cd "$(dirname "$0")/../.."
export GIT_TERMINAL_PROMPT=0

TOKEN_FILE="$HOME/.config/landscape/pat"
ONLY_PUSH=0
if [ "${1:-}" = "status" ]; then
  git status -sb
  echo "--- unpushed ---"
  git log --oneline origin/main..HEAD 2>/dev/null || git log --oneline -5
  ./infra/scripts/auth.sh status || true
  ./infra/scripts/secrets.sh status || true
  exit 0
fi
if [ "${1:-}" = "--only-push" ]; then ONLY_PUSH=1; shift; fi
MSG="${*:-auto $(date -u +%Y-%m-%dT%H:%MZ)}"

# Token aus Datei als Fallback anbieten (ohne es zu loggen)
if [ -z "${GH_TOKEN:-}" ] && [ -z "${GITHUB_TOKEN:-}" ] && [ -f "$TOKEN_FILE" ]; then
  GH_TOKEN="$(cat "$TOKEN_FILE")"
  export GH_TOKEN GITHUB_TOKEN="$GH_TOKEN"
fi

slug="$(git remote get-url origin 2>/dev/null | sed -E 's#.*github\.com[:/]([^/]+/[^/]+)(\.git)?#\1#; s/\.git$//')"
push_cmd() {
  if GIT_TERMINAL_PROMPT=0 git push origin main 2>/dev/null; then return 0; fi
  # Fallback: direkter Push per Token-URL (wenn Codespaces-Helper keinen Token hat)
  if [ -f "$TOKEN_FILE" ]; then
    local tok; tok="$(cat "$TOKEN_FILE")"
    GIT_TERMINAL_PROMPT=0 git push "https://x-access-token:${tok}@github.com/${slug}.git" main 2>/dev/null
    return $?
  fi
  return 1
}

if [ "$ONLY_PUSH" -eq 0 ]; then
  git add -A
  if ! git diff --cached --quiet; then
    git -c commit.gpgsign=false commit -m "$MSG" --quiet
    echo "Committed: $MSG"
  else
    echo "Nichts zu committen."
  fi
  # Fremde Commits (z.B. vom anderen Account) vorher rebasen, best effort
  git pull --rebase --autostash origin main >/dev/null 2>&1 || true
fi

if push_cmd; then
  echo "Gepusht -> $slug/main"
else
  echo "PUSH FEHLGESCHLAGEN. Einmalig: ./infra/scripts/auth.sh setup (oder LANDSCAPE_PAT als Codespaces-Secret setzen)."
  exit 1
fi
