#!/usr/bin/env bash
# save.sh = dein manueller Befehl zum Mitnehmen. Ruft den gleichen Agent-Push auf.
# Usage: ./scripts/save.sh [commit-message] | ./scripts/save.sh status
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "${1:-}" = "status" ]; then
  git status -sb
  echo "--- unpushed ---"
  git log --oneline origin/main..HEAD 2>/dev/null || git log --oneline -5
  ./scripts/auth.sh status || true
  exit 0
fi

exec ./scripts/push.sh "${@:-}"
