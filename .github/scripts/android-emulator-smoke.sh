#!/usr/bin/env bash
set -euo pipefail
mkdir -p test-artifacts/screenshots "${RUNNER_TEMP}/avd"
export ANDROID_AVD_HOME="${RUNNER_TEMP}/avd"
AVD_NAME="nebula-stride-ci"
SERIAL="emulator-5554"

collect_diagnostics() {
  adb -s "${SERIAL}" logcat -d > test-artifacts/logcat.txt 2>/dev/null || true
  adb -s "${SERIAL}" shell dumpsys window > test-artifacts/window-dump.txt 2>/dev/null || true
  adb -s "${SERIAL}" shell dumpsys activity activities > test-artifacts/activity-dump.txt 2>/dev/null || true
  adb -s "${SERIAL}" exec-out screencap -p > test-artifacts/screenshots/99-final-state.png 2>/dev/null || true
}
cleanup() {
  collect_diagnostics
  adb -s "${SERIAL}" emu kill >/dev/null 2>&1 || true
  if [[ -n "${EMULATOR_PID:-}" ]]; then
    kill "${EMULATOR_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "no" | avdmanager create avd \
  --force \
  --name "${AVD_NAME}" \
  --package "system-images;android-35;google_apis;x86_64" \
  --device "pixel_6"

adb start-server
"${ANDROID_SDK_ROOT}/emulator/emulator" \
  -avd "${AVD_NAME}" \
  -port 5554 \
  -no-window \
  -gpu swiftshader_indirect \
  -no-snapshot \
  -noaudio \
  -no-boot-anim \
  -camera-back none \
  -memory 2048 \
  -cores 2 \
  > test-artifacts/emulator.log 2>&1 &
EMULATOR_PID=$!

BOOTED=0
for _ in $(seq 1 180); do
  if ! kill -0 "${EMULATOR_PID}" 2>/dev/null; then
    echo "Emulator process exited before boot."
    cat test-artifacts/emulator.log
    exit 1
  fi
  if [[ "$(adb -s "${SERIAL}" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" == "1" ]]; then
    BOOTED=1
    break
  fi
  sleep 5
done
if [[ "${BOOTED}" != "1" ]]; then
  echo "Emulator did not boot within 15 minutes."
  cat test-artifacts/emulator.log
  exit 1
fi

adb -s "${SERIAL}" shell input keyevent 82 || true
adb -s "${SERIAL}" shell wm size 1280x720
adb -s "${SERIAL}" shell wm density 320
adb -s "${SERIAL}" shell settings put system accelerometer_rotation 0
adb -s "${SERIAL}" shell settings put system user_rotation 1
adb -s "${SERIAL}" logcat -c
adb -s "${SERIAL}" install -r build/NebulaStride-debug.apk
adb -s "${SERIAL}" shell am force-stop com.chatmcpconnector.nebulastride
adb -s "${SERIAL}" shell monkey -p com.chatmcpconnector.nebulastride 1

PID=""
for _ in $(seq 1 30); do
  PID="$(adb -s "${SERIAL}" shell pidof com.chatmcpconnector.nebulastride | tr -d '\r')"
  [[ -n "${PID}" ]] && break
  sleep 1
done
test -n "${PID}"
sleep 4

adb -s "${SERIAL}" exec-out screencap -p > test-artifacts/screenshots/01-tutorial.png
adb -s "${SERIAL}" shell input swipe 820 360 360 360 300
sleep 1
adb -s "${SERIAL}" shell input swipe 360 360 820 360 300
sleep 1
adb -s "${SERIAL}" shell input swipe 640 520 640 220 300
sleep 1
adb -s "${SERIAL}" shell input swipe 640 220 640 520 300
sleep 2
adb -s "${SERIAL}" exec-out screencap -p > test-artifacts/screenshots/02-main-menu.png
adb -s "${SERIAL}" shell input tap 640 330
sleep 5
adb -s "${SERIAL}" shell input swipe 640 400 350 400 300
adb -s "${SERIAL}" shell input swipe 350 400 850 400 300
adb -s "${SERIAL}" shell input swipe 640 500 640 230 300
adb -s "${SERIAL}" shell input swipe 640 250 640 540 300
sleep 3
adb -s "${SERIAL}" exec-out screencap -p > test-artifacts/screenshots/03-gameplay.png
adb -s "${SERIAL}" shell input keyevent 111
sleep 2
adb -s "${SERIAL}" exec-out screencap -p > test-artifacts/screenshots/04-pause.png
adb -s "${SERIAL}" shell input tap 640 300
sleep 2
adb -s "${SERIAL}" shell input keyevent 35
sleep 2
adb -s "${SERIAL}" exec-out screencap -p > test-artifacts/screenshots/05-game-over.png
adb -s "${SERIAL}" shell input tap 640 445
sleep 4
adb -s "${SERIAL}" exec-out screencap -p > test-artifacts/screenshots/06-restart.png

PID="$(adb -s "${SERIAL}" shell pidof com.chatmcpconnector.nebulastride | tr -d '\r')"
test -n "${PID}"
collect_diagnostics
if grep -E "FATAL EXCEPTION|ANR in com.chatmcpconnector.nebulastride|Process com.chatmcpconnector.nebulastride.*has died" test-artifacts/logcat.txt; then
  exit 1
fi
trap - EXIT
cleanup
