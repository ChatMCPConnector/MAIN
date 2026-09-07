#!/usr/bin/env bash
# start-on-boot.sh: läuft bei JEDEM Codespace-Start (postStartCommand, auch Resume).
# Leichtgewichtig: kein Paket-Install, kein Rebuild — nur sicherstellen, dass der
# glm2api-Haupt-Proxy läuft. Die volle Wiederherstellung macht setup.sh
# (postCreateCommand); hier ist nur der laufende Zustand garantiert.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Proxy-Health-Check: läuft er schon?
if curl -sf -m 2 http://127.0.0.1:8001/health >/dev/null 2>&1; then
  echo "[boot] glm2api läuft bereits."
  exit 0
fi

# Code/venv/.env vollständig? Wenn ja: einfach starten.
if [ -d "$REPO_ROOT/llm-proxies/glm2api/src" ] && [ -x "$REPO_ROOT/llm-proxies/glm2api/.venv/bin/python3" ] && [ -f "$REPO_ROOT/llm-proxies/glm2api/.env" ]; then
  bash "$REPO_ROOT/llm-proxies/scripts/start-glm2api.sh" >/dev/null 2>&1 \
    && echo "[boot] glm2api gestartet." \
    || echo "[boot] WARN: Proxy-Start fehlgeschlagen — manuell: ./llm-proxies/rebuild.sh --start"
  exit 0
fi

# Etwas fehlt (frischer Stand?) → voller Rebuild im Hintergrund, ports offen halten.
echo "[boot] glm2api unvollständig — Rebuild im Hintergrund..."
nohup bash "$REPO_ROOT/llm-proxies/rebuild.sh" --start >> /tmp/opencode/boot-rebuild.log 2>&1 &
echo "[boot] Rebuild läuft (Log: /tmp/opencode/boot-rebuild.log). Proxy ist in ~1-5 Min verfügbar."
