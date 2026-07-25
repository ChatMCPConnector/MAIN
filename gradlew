#!/usr/bin/env sh
set -eu

GRADLE_VERSION="8.11.1"
DIST_ROOT="${HOME}/.gradle/chatgpt-wrapper/gradle-${GRADLE_VERSION}"
GRADLE_HOME="${DIST_ROOT}/gradle-${GRADLE_VERSION}"

if [ ! -x "${GRADLE_HOME}/bin/gradle" ]; then
  mkdir -p "${DIST_ROOT}"
  ARCHIVE="${DIST_ROOT}/gradle-${GRADLE_VERSION}-bin.zip"
  if [ ! -f "${ARCHIVE}" ]; then
    curl --fail --location --silent --show-error \
      "https://services.gradle.org/distributions/gradle-${GRADLE_VERSION}-bin.zip" \
      --output "${ARCHIVE}"
  fi
  rm -rf "${GRADLE_HOME}"
  unzip -q "${ARCHIVE}" -d "${DIST_ROOT}"
fi

exec "${GRADLE_HOME}/bin/gradle" "$@"
