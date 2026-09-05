#!/usr/bin/env bash
set -euo pipefail

readonly root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly runtime_dir="${root_dir}/.runtime/ms-playwright"
readonly profile_dir="${root_dir}/.runtime/chromium-profile"
readonly log_dir="${root_dir}/.runtime/log"
readonly display="${DISPLAY:-:120}"
readonly start_url="${1:-https://new.xinjianya.top}"

chromium="$(find "${runtime_dir}" -type f -path '*/chrome-linux/chrome' -print -quit)"
if [[ -z "${chromium}" ]]; then
  echo "Chromium is not installed. Run scripts/browser-install.sh first." >&2
  exit 1
fi

for command in Xvfb x11vnc websockify; do
  if ! command -v "${command}" >/dev/null; then
    echo "Required command is unavailable: ${command}" >&2
    exit 1
  fi
done

mkdir -p "${profile_dir}" "${log_dir}"

if ! pgrep -f "Xvfb ${display}( |$)" >/dev/null; then
  Xvfb "${display}" -screen 0 1280x800x24 >"${log_dir}/xvfb.log" 2>&1 &
fi

for _ in {1..50}; do
  [[ -S "/tmp/.X11-unix/X${display#:}" ]] && break
  sleep 0.1
done
if [[ ! -S "/tmp/.X11-unix/X${display#:}" ]]; then
  echo "X server did not become ready on ${display}" >&2
  exit 1
fi

if ! ss -ltn | grep -q '127.0.0.1:5920'; then
  x11vnc -display "${display}" -forever -shared -nopw -localhost -rfbport 5920 \
    >"${log_dir}/x11vnc.log" 2>&1 &
fi

if ! ss -ltn | grep -q ':6082'; then
  websockify --web=/usr/share/novnc 6082 localhost:5920 \
    >"${log_dir}/novnc.log" 2>&1 &
fi

if ! ss -ltn | grep -q '127.0.0.1:9222'; then
  DISPLAY="${display}" "${chromium}" \
    --no-sandbox \
    --disable-dev-shm-usage \
    --remote-debugging-address=127.0.0.1 \
    --remote-debugging-port=9222 \
    --user-data-dir="${profile_dir}" \
    "${start_url}" >"${log_dir}/chromium.log" 2>&1 &
fi

for _ in {1..100}; do
  if curl -fsS http://127.0.0.1:9222/json/version >/dev/null \
    && ss -ltn | grep -q '127.0.0.1:5920' \
    && ss -ltn | grep -q ':6082'; then
    echo "Browser services are ready:"
    echo "  CDP:   http://127.0.0.1:9222"
    echo "  noVNC: http://localhost:6082/vnc.html?autoconnect=1&resize=scale"
    exit 0
  fi
  sleep 0.1
done

echo "Browser services did not become ready; inspect ${log_dir}" >&2
exit 1
