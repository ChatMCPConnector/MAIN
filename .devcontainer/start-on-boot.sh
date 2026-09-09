#!/usr/bin/env bash
# start-on-boot.sh: läuft bei JEDEM Codespace-Start (postStartCommand, auch Resume).
# Leichtgewichtig: stellt sicher, dass alle lokalen LLM-Proxies (glm2api, gemini-web2api,
# antigravity-proxy) laufen und der Watchdog aktiv ist.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 0. Secrets entsperren, falls nötig (z.B. nach Container-Neustart)
if [ -f "$REPO_ROOT/config/secrets.enc" ] && { [ -n "${LANDSCAPE_PASSPHRASE:-}" ] || [ -f "$REPO_ROOT/config/passphrase" ]; }; then
  if [ ! -f "$HOME/.config/antigravity-oauth-proxy/oauth_creds.json" ] || [ ! -f "$REPO_ROOT/.secrets/gemini-web-cookie.txt" ]; then
    bash "$REPO_ROOT/infra/scripts/secrets.sh" unlock >/dev/null 2>&1 || true
  fi
fi

# 1. glm2api (Port 8001)
if curl -sf -m 2 http://127.0.0.1:8001/health >/dev/null 2>&1; then
  echo "[boot] glm2api läuft bereits."
else
  if [ -d "$REPO_ROOT/llm-proxies/glm2api/src" ] && [ -x "$REPO_ROOT/llm-proxies/glm2api/.venv/bin/python3" ] && [ -f "$REPO_ROOT/llm-proxies/glm2api/.env" ]; then
    bash "$REPO_ROOT/llm-proxies/scripts/start-glm2api.sh" >/dev/null 2>&1 \
      && echo "[boot] glm2api gestartet." \
      || echo "[boot] WARN: glm2api Start fehlgeschlagen."
  else
    echo "[boot] glm2api unvollständig — Rebuild im Hintergrund..."
    nohup bash "$REPO_ROOT/llm-proxies/rebuild.sh" --start >> /tmp/opencode/boot-rebuild.log 2>&1 &
  fi
fi

# 2. gemini-web2api (Port 8083)
if curl -sf -m 2 http://127.0.0.1:8083/ >/dev/null 2>&1; then
  echo "[boot] gemini-web2api läuft bereits."
else
  if [ -x "$REPO_ROOT/llm-proxies/gemini-web2api/scripts/start.sh" ]; then
    bash "$REPO_ROOT/llm-proxies/gemini-web2api/scripts/start.sh" >/dev/null 2>&1 \
      && echo "[boot] gemini-web2api gestartet." \
      || echo "[boot] WARN: gemini-web2api Start fehlgeschlagen."
  fi
fi

# 3. antigravity-proxy (Port 9878)
if curl -sf -m 2 http://127.0.0.1:9878/v1/models >/dev/null 2>&1; then
  echo "[boot] antigravity-proxy läuft bereits."
else
  if [ -x "$REPO_ROOT/llm-proxies/antigravity-proxy/scripts/start.sh" ]; then
    bash "$REPO_ROOT/llm-proxies/antigravity-proxy/scripts/start.sh" >/dev/null 2>&1 \
      && echo "[boot] antigravity-proxy gestartet." \
      || echo "[boot] WARN: antigravity-proxy Start fehlgeschlagen."
  fi
fi

# 4. opencode-server (Port 4096)
if curl -sf -m 2 http://127.0.0.1:4096/ >/dev/null 2>&1; then
  echo "[boot] opencode-server läuft bereits."
else
  if [ -x "$REPO_ROOT/infra/scripts/opencode-server.sh" ]; then
    bash "$REPO_ROOT/infra/scripts/opencode-server.sh" start >/dev/null 2>&1 \
      && echo "[boot] opencode-server gestartet." \
      || echo "[boot] WARN: opencode-server Start fehlgeschlagen."
  fi
fi

# 5. Proxy-Watchdog immer (re-)starten: hält alle Proxies und opencode-server am Leben
mkdir -p /tmp/opencode
if ! { [ -f /tmp/opencode/proxy-watchdog.lock ] && kill -0 "$(cat /tmp/opencode/proxy-watchdog.lock 2>/dev/null)" 2>/dev/null; }; then
  setsid bash "$REPO_ROOT/.devcontainer/proxy-watchdog.sh" </dev/null >/dev/null 2>&1 &
  echo "[boot] Proxy-Watchdog gestartet (30s-Intervall für alle Proxies + Server)."
fi
