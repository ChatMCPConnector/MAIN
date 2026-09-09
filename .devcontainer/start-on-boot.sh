#!/usr/bin/env bash
# start-on-boot.sh: läuft bei JEDEM Codespace-Start (postStartCommand, auch Resume).
# Leichtgewichtig: kein Paket-Install, kein Rebuild — nur sicherstellen, dass der
# glm2api-Haupt-Proxy läuft. Die volle Wiederherstellung macht setup.sh
# (postCreateCommand); hier ist nur der laufende Zustand garantiert.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Proxy-Health-Check: läuft er schon? (Watchdog unten wird trotzdem gesichert)
if curl -sf -m 2 http://127.0.0.1:8001/health >/dev/null 2>&1; then
  echo "[boot] glm2api läuft bereits."
else
  # Code/venv/.env vollständig? Wenn ja: einfach starten.
  if [ -d "$REPO_ROOT/llm-proxies/glm2api/src" ] && [ -x "$REPO_ROOT/llm-proxies/glm2api/.venv/bin/python3" ] && [ -f "$REPO_ROOT/llm-proxies/glm2api/.env" ]; then
    bash "$REPO_ROOT/llm-proxies/scripts/start-glm2api.sh" >/dev/null 2>&1 \
      && echo "[boot] glm2api gestartet." \
      || echo "[boot] WARN: Proxy-Start fehlgeschlagen — manuell: ./llm-proxies/rebuild.sh --start"
  else
    # Etwas fehlt (frischer Stand?) → voller Rebuild im Hintergrund.
    echo "[boot] glm2api unvollständig — Rebuild im Hintergrund..."
    nohup bash "$REPO_ROOT/llm-proxies/rebuild.sh" --start >> /tmp/opencode/boot-rebuild.log 2>&1 &
    echo "[boot] Rebuild läuft (Log: /tmp/opencode/boot-rebuild.log). Proxy in ~1-5 Min verfügbar."
  fi
fi

# Watchdog immer (re-)starten: hält den Proxy auch über OOM-Kills/Reattaches am Leben
# (postStartCommand greift nur bei echtem Container-Start, nicht bei Client-Reconnect).
mkdir -p /tmp/opencode
if ! { [ -f /tmp/opencode/proxy-watchdog.lock ] && kill -0 "$(cat /tmp/opencode/proxy-watchdog.lock 2>/dev/null)" 2>/dev/null; }; then
  # setsid zwingend: ohne eigene Session killt devcontainer-cli die ganze
  # Prozessgruppe beim Aufräumen des postStartCommand (nohup schützt da nicht).
  setsid bash "$REPO_ROOT/.devcontainer/proxy-watchdog.sh" </dev/null >/dev/null 2>&1 &
  echo "[boot] Proxy-Watchdog gestartet (30s-Intervall)."
fi

# gemini-web2api-Check
if curl -sf -m 2 http://127.0.0.1:8083/ >/dev/null 2>&1; then
  echo "[boot] gemini-web2api läuft bereits."
else
  if [ -x "$REPO_ROOT/llm-proxies/gemini-web2api/scripts/start.sh" ]; then
    bash "$REPO_ROOT/llm-proxies/gemini-web2api/scripts/start.sh" >/dev/null 2>&1 \
      && echo "[boot] gemini-web2api gestartet." \
      || echo "[boot] WARN: gemini-web2api Start fehlgeschlagen."
  fi
fi

# antigravity-proxy-Check
if ss -tln | grep -q ":9878 "; then
  echo "[boot] antigravity-proxy läuft bereits."
else
  if [ -x "$REPO_ROOT/llm-proxies/antigravity-proxy/scripts/start.sh" ]; then
    bash "$REPO_ROOT/llm-proxies/antigravity-proxy/scripts/start.sh" >/dev/null 2>&1 \
      && echo "[boot] antigravity-proxy gestartet." \
      || echo "[boot] WARN: antigravity-proxy Start fehlgeschlagen."
  fi
fi
