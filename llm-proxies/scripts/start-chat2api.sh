#!/bin/bash
# Chat2API headless startup (Electron under Xvfb, direct binary from out/)
# Proxy: 127.0.0.1:8080 (OpenAI-compatible), App-Data: ~/.chat2api
set -u

REPO="/workspaces/chat2api/repo"
LOG="/tmp/opencode/chat2api.log"
ELECTRON_BIN="$REPO/node_modules/electron/dist/electron"
PROXY_HOST="127.0.0.1"
PROXY_PORT="8080"

mkdir -p /tmp/opencode

echo "[$(date -u +%FT%TZ)] === Chat2API start requested ===" >> "$LOG"

# --- 1) Kill previous instances (proxy port holder + electron of this repo) ---
PORT_PID=$(ss -tlnp 2>/dev/null | grep ":$PROXY_PORT" | grep -oP 'pid=\K[0-9]+' | head -1)
if [ -n "${PORT_PID}" ]; then
  echo "[$(date -u +%FT%TZ)] Killing old proxy holder PID $PORT_PID" >> "$LOG"
  kill "${PORT_PID}" 2>/dev/null
fi
pkill -f "$REPO/node_modules/electron" 2>/dev/null
pkill -f "electron-vite (preview|dev)" 2>/dev/null
sleep 2
# Force-kill leftovers holding the port
PORT_PID=$(ss -tlnp 2>/dev/null | grep ":$PROXY_PORT" | grep -oP 'pid=\K[0-9]+' | head -1)
if [ -n "${PORT_PID}" ]; then
  echo "[$(date -u +%FT%TZ)] Force-killing PID $PORT_PID" >> "$LOG"
  kill -9 "${PORT_PID}" 2>/dev/null
  sleep 1
fi

# --- 2) Start Electron headless under Xvfb, detached via setsid ---
export ELECTRON_DISABLE_GPU=1
export ELECTRON_ENABLE_LOGGING=1
export ELECTRON_NO_ATTACH_CONSOLE=1
export ELECTRON_HEADLESS=1
setsid xvfb-run -a --server-args="-screen 0 1024x768x24" \
  "$ELECTRON_BIN" "$REPO" \
  --no-sandbox --disable-gpu --disable-software-rasterizer \
  --disable-dev-shm-usage --disable-features=SpareRendererForSitePerProcess \
  >> "$LOG" 2>&1 &
echo "[$(date -u +%FT%TZ)] Launched electron (bg), waiting for port $PROXY_HOST:$PROXY_PORT ..." >> "$LOG"

# --- 3) Wait until the proxy port is listening (max 60s) ---
for i in $(seq 1 60); do
  if ss -tln 2>/dev/null | grep -q "$PROXY_HOST:$PROXY_PORT"; then
    echo "[$(date -u +%FT%TZ)] Proxy is listening on $PROXY_HOST:$PROXY_PORT after ${i}s" >> "$LOG"
    # health check (best effort)
    curl -s -m 5 "http://$PROXY_HOST:$PROXY_PORT/health" >> "$LOG" 2>/dev/null
    echo "" >> "$LOG"
    echo "OK: proxy up on $PROXY_HOST:$PROXY_PORT after ${i}s"
    exit 0
  fi
  sleep 1
done

echo "ERROR: proxy port $PROXY_HOST:$PROXY_PORT not reachable within 60s, see $LOG" >&2
exit 1
