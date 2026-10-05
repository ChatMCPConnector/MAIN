#!/usr/bin/env bash
# start-on-boot.sh: läuft bei JEDEM Codespace-Start (postStartCommand, auch Resume).
# Leichtgewichtig: stellt sicher, dass die lokalen Dienste laufen und die
# Watchdogs aktiv sind — glm2api (8001), antigravity-proxy (9878), zerokey (7250),
# opencode-server (4096) plus proxy- und config-watchdog.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 0. Secrets entsperren, falls nötig (z.B. nach Container-Neustart)
if [ -f "$REPO_ROOT/config/secrets.enc" ] && { [ -n "${LANDSCAPE_PASSPHRASE:-}" ] || [ -f "$REPO_ROOT/config/passphrase" ]; }; then
  if [ ! -f "$HOME/.config/antigravity-oauth-proxy/oauth_creds.json" ]; then
    # SECRETS_NO_PROMPT + </dev/null: derselbe Boot-Hang wie in setup.sh — ohne
    # die beiden Flags kann secrets.sh bei vorhandenem TTY interaktiv nach der
    # Passphrase fragen, und der Boot wartet unsichtbar (Ausgabe geht nach
    # /dev/null). keys.sh ensure legt bei Fehlschlag Platzhalter an.
    SECRETS_NO_PROMPT=1 bash "$REPO_ROOT/infra/scripts/secrets.sh" unlock </dev/null >/dev/null 2>&1 || true
  fi
fi

# 1. glm2api (Port 8001)
if curl -sf -m 2 http://127.0.0.1:8001/health >/dev/null 2>&1; then
  echo "[boot] glm2api läuft bereits."
else
  if [ -d "$REPO_ROOT/llm-proxies/glm2api/src" ] && [ -x "$REPO_ROOT/llm-proxies/glm2api/.venv/bin/python3" ] && [ -f "$REPO_ROOT/llm-proxies/glm2api/.env" ]; then
    bash "$REPO_ROOT/infra/scripts/glm2api.sh" start >/dev/null 2>&1 \
      && echo "[boot] glm2api gestartet." \
      || echo "[boot] WARN: glm2api Start fehlgeschlagen."
  else
    echo "[boot] glm2api unvollständig — Rebuild im Hintergrund..."
    nohup bash "$REPO_ROOT/llm-proxies/rebuild.sh" --start >> /tmp/opencode/boot-rebuild.log 2>&1 &
  fi
fi

# 2. antigravity-proxy (Port 9878)
if curl -sf -m 2 http://127.0.0.1:9878/v1/models >/dev/null 2>&1; then
  echo "[boot] antigravity-proxy läuft bereits."
else
  if [ -x "$REPO_ROOT/llm-proxies/antigravity-proxy/scripts/start.sh" ]; then
    bash "$REPO_ROOT/llm-proxies/antigravity-proxy/scripts/start.sh" >/dev/null 2>&1 \
      && echo "[boot] antigravity-proxy gestartet." \
      || echo "[boot] WARN: antigravity-proxy Start fehlgeschlagen."
  fi
fi

# 3. zerokey (Port 7250)
# Fehlte hier bisher (die Schritte liefen 0,1,2,4,5,6). Nach jedem Resume blieb
# zerokey tot, bis der 30-s-Proxy-Watchdog ihn startete — bei totem Watchdog
# dauerhaft. Gegenprobe wie bei den anderen: /v1/models antwortet = laeuft.
if curl -sf -m 2 http://127.0.0.1:7250/v1/models >/dev/null 2>&1; then
  echo "[boot] zerokey läuft bereits."
else
  if [ -x "$REPO_ROOT/llm-proxies/scripts/start-zerokey.sh" ]; then
    bash "$REPO_ROOT/llm-proxies/scripts/start-zerokey.sh" >/dev/null 2>&1 \
      && echo "[boot] zerokey gestartet." \
      || echo "[boot] WARN: zerokey Start fehlgeschlagen."
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
  setsid nohup bash "$REPO_ROOT/.devcontainer/proxy-watchdog.sh" </dev/null >> /tmp/opencode/watchdog.log 2>&1 &
  disown $! 2>/dev/null || true
  echo "[boot] Proxy-Watchdog gestartet (30s-Intervall für alle Proxies + Server)."
fi

# 6. Config-Watchdog: restartet opencode-server automatisch bei opencode.json-Änderung
if ! { [ -f /tmp/opencode/config-watchdog.lock ] && kill -0 "$(cat /tmp/opencode/config-watchdog.lock 2>/dev/null)" 2>/dev/null; }; then
  setsid nohup bash "$REPO_ROOT/infra/scripts/config-watchdog.sh" </dev/null >>/tmp/opencode/config-watchdog.log 2>&1 &
  disown $! 2>/dev/null || true
  echo "[boot] Config-Watchdog gestartet (inotify auf opencode.json)."
fi

# 7. VS Code: ms-python.debugpy "no-config debugging" im Terminal neutralisieren
# debugpy injiziert ungefragt "debugpy <script.py>" in PATH und triggerte bei jedem
# Boot "Erweiterungen möchten das Terminal neu starten". Da debugpy keinen Schalter hat,
# wird registerNoConfigDebug beim Boot idempotent neutralisiert.
patch_debugpy() {
  for ext_js in "$HOME"/.vscode-remote/extensions/ms-python.debugpy*/dist/extension.js; do
    if [ -f "$ext_js" ]; then
      python3 -c '
import sys
p = sys.argv[1]
try:
    with open(p, "r", encoding="utf-8") as f:
        c = f.read()
    target = "t.registerNoConfigDebug=async function(e,t){const"
    if target in c:
        c = c.replace(target, "t.registerNoConfigDebug=async function(e,t){return;const", 1)
        with open(p, "w", encoding="utf-8") as f:
            f.write(c)
        print("[boot] ms-python.debugpy registerNoConfigDebug neutralisiert.")
except Exception:
    pass
' "$ext_js"
    fi
  done
}
patch_debugpy
(
  for _ in $(seq 1 30); do
    patch_debugpy
    sleep 2
  done
) >/dev/null 2>&1 &

# Kein autosave-daemon (siehe setup.sh, Nutzerentscheidung 2026-09-27).
