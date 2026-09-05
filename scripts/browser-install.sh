#!/usr/bin/env bash
set -euo pipefail

readonly root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly browser_dir="${root_dir}/browser"
readonly runtime_dir="${root_dir}/.runtime/ms-playwright"

mkdir -p "${runtime_dir}"
cd "${browser_dir}"

npm ci
PLAYWRIGHT_BROWSERS_PATH="${runtime_dir}" npx playwright install chromium

echo "Chromium runtime installed under ${runtime_dir}"
