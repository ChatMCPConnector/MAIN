#!/usr/bin/env bash
# proxy-watchdog.sh: hält alle lokalen LLM-Proxies am Leben (glm2api, gemini-web2api, antigravity-proxy)
# egal was passiert (OOM-Kill, Container-Reattach, Idle-Stopp...).
#
# Wird von start-on-boot.sh und setup.sh als Hintergrund-Daemon gestartet und prüft
# alle 30s den Proxy-Health.
set -u
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK=/tmp/opencode/proxy-watchdog.lock

if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK")" 2>/dev/null; then
  exit 0  # läuft schon
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT
trap '' HUP  # SIGHUP ignorieren

while true; do
  # 1. glm2api (Port 8001)
  if ! curl -sf -m 3 http://127.0.0.1:8001/health >/dev/null 2>&1; then
    echo "$(date '+%H:%M:%S') [watchdog] glm2api (Port 8001) weg — starte neu..." >> /tmp/opencode/watchdog.log
    bash "$REPO_ROOT/llm-proxies/scripts/start-glm2api.sh" >> /tmp/opencode/watchdog.log 2>&1 || true
  fi

  # 2. gemini-web2api (Port 8083)
  if ! curl -sf -m 3 http://127.0.0.1:8083/ >/dev/null 2>&1; then
    echo "$(date '+%H:%M:%S') [watchdog] gemini-web2api (Port 8083) weg — starte neu..." >> /tmp/opencode/watchdog.log
    bash "$REPO_ROOT/llm-proxies/gemini-web2api/scripts/start.sh" >> /tmp/opencode/watchdog.log 2>&1 || true
  fi

  # 3. antigravity-proxy (Port 9878)
  if ! curl -sf -m 3 http://127.0.0.1:9878/v1/models >/dev/null 2>&1; then
    echo "$(date '+%H:%M:%S') [watchdog] antigravity-proxy (Port 9878) weg — starte neu..." >> /tmp/opencode/watchdog.log
    bash "$REPO_ROOT/llm-proxies/antigravity-proxy/scripts/start.sh" >> /tmp/opencode/watchdog.log 2>&1 || true
  fi

  # 4. opencode-server (Port 4096)
  if ! curl -sf -m 3 http://127.0.0.1:4096/ >/dev/null 2>&1; then
    echo "$(date '+%H:%M:%S') [watchdog] opencode-server (Port 4096) weg — starte neu..." >> /tmp/opencode/watchdog.log
    bash "$REPO_ROOT/infra/scripts/opencode-server.sh" start >> /tmp/opencode/watchdog.log 2>&1 || true
  fi

  # 5. autosave-daemon
  if ! { [ -f /tmp/opencode/autosave-daemon.lock ] && kill -0 "$(cat /tmp/opencode/autosave-daemon.lock 2>/dev/null)" 2>/dev/null; }; then
    echo "$(date '+%H:%M:%S') [watchdog] autosave-daemon weg — starte neu..." >> /tmp/opencode/watchdog.log
    setsid nohup bash "$REPO_ROOT/.devcontainer/autosave-daemon.sh" </dev/null >> /tmp/opencode/autosave.log 2>&1 &
    disown $! 2>/dev/null || true
  fi

  sleep 30
done
