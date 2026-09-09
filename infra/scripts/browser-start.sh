#!/usr/bin/env bash
# browser-start.sh: Startet den VNC-Browser-Stack (Firefox statt Chromium).
# Xvfb + x11vnc + noVNC bleiben identisch; Firefox ersetzt Chromium.
# Zweck des Wechsels: Google-Logins in Firefox erzeugen KEINE DBSC-gebundenen
# Sessions — deren Cookies kann gemini-web2api per Sentinel-Refresh unbegrenzt
# selbst erneuern (Chrome/Chromium-Cookies sterben nach ~30-60 min, s. CHANGELOG).
# Remote-Debugging: Firefox --start-debugger-server (Marionette/DevTools) ist für
# Cookie-Exports nicht nötig — Cookies liegen in .runtime/firefox-profile
# (cookies.sqlite), Export via DevTools im noVNC-Browser.
set -euo pipefail

readonly root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly runtime_dir="${root_dir}/.runtime"
readonly profile_dir="${root_dir}/.runtime/firefox-profile"
readonly log_dir="${runtime_dir}/log"
readonly display="${DISPLAY:-:120}"
readonly start_url="${1:-https://gemini.google.com}"

firefox_bin="${runtime_dir}/firefox/firefox"
if [[ ! -x "${firefox_bin}" ]]; then
  echo "Firefox is not installed. Run infra/scripts/firefox-install.sh first." >&2
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
  nohup Xvfb "${display}" -screen 0 1280x800x24 \
    >"${log_dir}/xvfb.log" 2>&1 </dev/null &
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
  nohup x11vnc -display "${display}" -forever -shared -nopw -localhost -rfbport 5920 \
    >"${log_dir}/x11vnc.log" 2>&1 </dev/null &
fi

if ! ss -ltn | grep -q ':6082'; then
  nohup websockify --web=/usr/share/novnc 6082 localhost:5920 \
    >"${log_dir}/novnc.log" 2>&1 </dev/null &
fi

if ! pgrep -f "firefox.*firefox-profile" >/dev/null; then
  nohup env DISPLAY="${display}" "${firefox_bin}" \
    --no-remote \
    --profile "${profile_dir}" \
    "${start_url}" >"${log_dir}/firefox.log" 2>&1 </dev/null &
fi

for _ in {1..300}; do
  if pgrep -f "firefox.*firefox-profile" >/dev/null \
    && ss -ltn | grep -q '127.0.0.1:5920' \
    && ss -ltn | grep -q ':6082'; then
    echo "Browser services are ready:"
    echo "  noVNC: http://localhost:6082/vnc.html?autoconnect=1&resize=scale"
    echo "  Cookie-Export: DevTools (F12) im Browser -> Storage -> Cookies"
    exit 0
  fi
  sleep 0.1
done

echo "Browser services did not become ready; inspect ${log_dir}" >&2
exit 1