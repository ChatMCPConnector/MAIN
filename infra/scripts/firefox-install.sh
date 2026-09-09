#!/usr/bin/env bash
# firefox-install.sh: Installiert Firefox (Mozilla-Tarball, gepinnte Version) nach .runtime/firefox.
# Snap/apt-Firefox ist im Codespace unbrauchbar (apt-Paket ist nur ein Snap-Wrapper).
# Firefox statt Chromium: Google-Cookies aus Firefox sind NICHT DBSC-gebunden,
# gemini-web2api kann __Secure-1PSIDTS damit unbegrenzt selbst erneuern.
# Kanonisch: FIREFOX_VERSION unten pinnen + dieses Skript ist der einzige Weg.
set -euo pipefail

readonly FIREFOX_VERSION="155.0.1"
readonly root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly runtime_dir="${root_dir}/.runtime"
readonly target_dir="${runtime_dir}/firefox"
readonly tmp_dir="${runtime_dir}/firefox-dl"

mkdir -p "${runtime_dir}" "${tmp_dir}"

archive="firefox-${FIREFOX_VERSION}.tar.xz"
url="https://download-installer.cdn.mozilla.net/pub/firefox/releases/${FIREFOX_VERSION}/linux-x86_64/en-US/${archive}"

if [ -x "${target_dir}/firefox" ] && "${target_dir}/firefox" --version 2>/dev/null | grep -q "${FIREFOX_VERSION}"; then
  echo "[firefox] ${FIREFOX_VERSION} bereits installiert unter ${target_dir}"
  exit 0
fi

echo "[firefox] Lade Firefox ${FIREFOX_VERSION}..."
curl -fsSL -o "${tmp_dir}/${archive}" "${url}"
echo "[firefox] Entpacke nach ${target_dir}..."
rm -rf "${target_dir}"
tar -xJf "${tmp_dir}/${archive}" -C "${runtime_dir}"
rm -rf "${tmp_dir}"

# Headless-Umgebungen: Wayland/X11-Abhängigkeiten sind vorhanden (Xvfb-Stack),
# aber GTK-Fallbacks setzen dbus-x11 voraus — still installieren falls nötig.
command -v dbus-launch >/dev/null 2>&1 || echo "[firefox] HINWEIS: dbus-launch fehlt (paket dbus-x11), ggf. nachinstallieren"

"${target_dir}/firefox" --version
echo "[firefox] OK: ${target_dir}/firefox"