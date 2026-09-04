#!/usr/bin/env bash
# push.sh: Agent-Push. Non-interaktiv, fragt NIE nach. Darf vom Agent jederzeit laufen.
#   ./scripts/push.sh [commit-message]   # add+commit (falls nötig)+pull-rebase+push
#   ./scripts/push.sh --only-push        # nur push (kein commit)
set -uo pipefail
cd "$(dirname "$0")/.."
export GIT_TERMINAL_PROMPT=0

TOKEN_FILE="$HOME/.config/landscape/pat"
ONLY_PUSH=0
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
  echo "PUSH FEHLGESCHLAGEN. Einmalig: ./scripts/auth.sh setup (oder LANDSCAPE_PAT als Codespaces-Secret setzen)."
  exit 1
fi
