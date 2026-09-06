#!/usr/bin/env bash
# proxies/rebuild.sh: GLM-Proxy-Repos + lokale Patches in einem frischen Codespace
# wiederherstellen. Idempotent: vorhandene Klones werden überspritzt/gepatcht.
#
#   ./proxies/rebuild.sh          # alle drei Proxies klonen + patchen
#   ./proxies/rebuild.sh glm2api  # nur einen
#
# Quellen:
#   glm2api   https://github.com/XxxXTeam/glm2api          (Port 8001)
#   hellogml  https://github.com/Hello-Application-XH/HelloGML (Port 8787)
#   chat2api  https://github.com/xiaoY233/Chat2API         (Port 8080)
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PATCH_DIR="$REPO_ROOT/proxies/patches"
WS="/workspaces"
LOG_DIR="/tmp/opencode"
mkdir -p "$LOG_DIR"

# name|cloneurl|zielverzeichnis(repo)|patchfile
TARGETS=(
  "glm2api|https://github.com/XxxXTeam/glm2api.git|$WS/glm2api/repo|glm2api.patch"
  "hellogml|https://github.com/Hello-Application-XH/HelloGML.git|$WS/hellogml/repo|hellogml.patch"
  "chat2api|https://github.com/xiaoY233/Chat2API.git|$WS/chat2api/repo|chat2api.patch"
)

do_one() {
  local name="$1" url="$2" dir="$3" patch="$4"
  echo "==> [$name]"

  # 1) Klon (falls fehlend)
  if [ -d "$dir/.git" ]; then
    echo "    Klon vorhanden: $dir"
  else
    echo "    Klone $url -> $dir"
    mkdir -p "$(dirname "$dir")"
    git clone --depth 1 "$url" "$dir" 2>&1 | sed 's/^/      /' || { echo "    FEHLER: Klon fehlgeschlagen"; return 1; }
  fi

  # 2) Patch anwenden (idempotent)
  if [ ! -f "$PATCH_DIR/$patch" ]; then
    echo "    WARN: Patch $patch fehlt — Repo bleibt unpatched"
    return 0
  fi
  if git -C "$dir" apply --check --reverse "$PATCH_DIR/$patch" 2>/dev/null; then
    echo "    Bereits gepatcht (Patch bereits angewendet — OK)"
  elif git -C "$dir" apply --check "$PATCH_DIR/$patch" 2>/dev/null; then
    git -C "$dir" apply "$PATCH_DIR/$patch" \
      && echo "    Patch angewendet ($patch)" \
      || { echo "    FEHLER: Patch anwenden fehlgeschlagen"; return 1; }
  else
    echo "    WARN: Patch passt nicht auf aktuellen Stand (Upstream geändert?). Manuell prüfen:"
    echo "      git -C $dir apply --3way $PATCH_DIR/$patch"
  fi

  # 3) Dependencies (nur wenn node_modules fehlt)
  case "$name" in
    hellogml)
      [ -d "$dir/node_modules" ] || (cd "$dir" && npm install --no-audit --no-fund 2>&1 | tail -1 | sed 's/^/      /')
      ;;
    chat2api)
      [ -d "$dir/node_modules" ] || (cd "$dir" && npm install --no-audit --no-fund 2>&1 | tail -1 | sed 's/^/      /')
      # Build für out/ (Electron-Binary), dauert einige Minuten
      [ -d "$dir/out" ] || { echo "    Baue out/ (kann dauern)..."; (cd "$dir" && npm run build 2>&1 | tail -1 | sed 's/^/      /') || echo "    WARN: Build fehlgeschlagen — manuell: npm run build"; }
      ;;
    glm2api)
      # uv run lädt Abhängigkeiten on-demand, kein Install nötig
      :
      ;;
  esac
  return 0
}

ONLY="${1:-all}"
FAILED=0
for t in "${TARGETS[@]}"; do
  IFS='|' read -r name url dir patch <<< "$t"
  if [ "$ONLY" != "all" ] && [ "$ONLY" != "$name" ]; then continue; fi
  do_one "$name" "$url" "$dir" "$patch" || FAILED=1
done

# start.sh-Symlinks ins /workspaces-Root legen (DOKU-Pfad-Konvention: /workspaces/<name>/start.sh)
for f in "$REPO_ROOT"/proxies/scripts/start-*.sh; do
  base="$(basename "$f")"
  proxy="${base#start-}"; proxy="${proxy%.sh}"
  [ -d "$WS/$proxy" ] && { cp "$f" "$WS/$proxy/start.sh"; chmod +x "$WS/$proxy/start.sh"; echo "==> start.sh für $proxy aktualisiert"; }
done

echo ""
echo "Fertig. Starten mit: /workspaces/<proxy>/start.sh  (Logs: $LOG_DIR/<proxy>.log)"
exit $FAILED
