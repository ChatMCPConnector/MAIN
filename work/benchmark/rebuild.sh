#!/usr/bin/env bash
# work/benchmark/rebuild.sh: ChaosShop-Benchmark-Kopien aus dem Template
# (im Repo) unter /workspaces/benchmark wiederherstellen.
#
#   ./work/benchmark/rebuild.sh              # alle drei Proxy-Work-Kopien
#   ./work/benchmark/rebuild.sh glm2api      # nur eine (glm2api|hellogml|chat2api)
#
# Startzustand je Kopie: 4 failed / 5 passed (repoduzierbar via pytest).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEMPLATE="$REPO_ROOT/work/benchmark/template"
DEST_ROOT="/workspaces/benchmark"

PROXIES=("glm2api" "hellogml" "chat2api")
ONLY="${1:-all}"
[ "$ONLY" != "all" ] && PROXIES=("$ONLY")

mkdir -p "$DEST_ROOT"
for p in "${PROXIES[@]}"; do
  DEST="$DEST_ROOT/${p}-work"
  if [ -d "$DEST" ]; then
    echo "[$p] Kopie vorhanden, übersprungen: $DEST (Reset: rm -rf $DEST && nochmal laufen lassen)"
    continue
  fi
  cp -r "$TEMPLATE" "$DEST"
  rm -rf "$DEST/tests/__pycache__" "$DEST/.pytest_cache"
  echo "[$p] angelegt: $DEST"
done

echo ""
echo "Verifikation (je Kopie): cd /workspaces/benchmark/<proxy>-work && python3 -m pytest tests/ -q"
echo "Erwartet: 4 failed, 5 passed (Startzustand)."
