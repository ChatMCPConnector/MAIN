#!/usr/bin/env bash
# proxy-watchdog.sh: hält glm2api am Leben — egal was passiert
# (OOM-Kill, Container-Reattach, Idle-Stopp...).
#
# Wird von start-on-boot.sh als Hintergrund-Daemon gestartet und prüft
# alle 30s den Proxy-Health. Wand das Skript selbst schon laufen, exit.
set -u
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK=/tmp/opencode/proxy-watchdog.lock

if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK")" 2>/dev/null; then
  exit 0  # läuft schon
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

while true; do
  if ! curl -sf -m 3 http://127.0.0.1:8001/health >/dev/null 2>&1; then
    echo "$(date '+%H:%M:%S') Proxy weg — starte neu..." >> /tmp/opencode/watchdog.log
    bash "$REPO_ROOT/llm-proxies/scripts/start-glm2api.sh" >> /tmp/opencode/watchdog.log 2>&1
  fi
  sleep 30
done
