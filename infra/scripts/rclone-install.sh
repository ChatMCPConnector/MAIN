#!/usr/bin/env bash
# rclone-install.sh: Installiert rclone (gepinnte Version, Official-Binary) nach /usr/local/bin.
# Zweck: Google-Drive-Backup (gdrive-backup.sh) — Repo-Sicherung außerhalb von GitHub,
# für den Fall dass der GitHub-Account gebannt wird / das Repo geschlossen wird.
# Kanonisch: RCLONE_VERSION unten pinnen + dieses Skript ist der einzige Weg.
# /usr/local/bin ist ephemeral (Rebuild) -> setup.sh ruft dieses Skript automatisch auf.
set -euo pipefail

readonly RCLONE_VERSION="1.75.1"
readonly target="/usr/local/bin/rclone"
readonly tmp_dir="/tmp/opencode/rclone-install"

if command -v rclone >/dev/null 2>&1 && rclone version 2>/dev/null | head -1 | grep -q "rclone v${RCLONE_VERSION}"; then
  echo "[rclone] v${RCLONE_VERSION} bereits installiert ($(command -v rclone))"
  exit 0
fi

mkdir -p "$tmp_dir"
archive="rclone-v${RCLONE_VERSION}-linux-amd64.zip"
url="https://downloads.rclone.org/${archive}"

echo "[rclone] Lade rclone v${RCLONE_VERSION}..."
curl -fsSL --retry 5 --retry-all-errors -o "${tmp_dir}/${archive}" "${url}"
unzip -o -q "${tmp_dir}/${archive}" -d "${tmp_dir}/extract"

sudo cp "${tmp_dir}/extract/rclone-v${RCLONE_VERSION}-linux-amd64/rclone" "$target"
sudo chmod +x "$target"
rm -rf "$tmp_dir"

rclone version | head -1
echo "[rclone] OK: ${target}"