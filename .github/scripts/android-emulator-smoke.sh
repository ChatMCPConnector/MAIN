#!/usr/bin/env bash
set -euo pipefail

PACKAGE="com.chatmcpconnector.nebulastride"
AVD_NAME="nebula-stride-ci"
SERIAL="emulator-5554"

mkdir -p test-artifacts/screenshots "${RUNNER_TEMP}/avd"
: > test-artifacts/foreground-checks.txt
export ANDROID_AVD_HOME="${RUNNER_TEMP}/avd"

app_pid() {
  adb -s "${SERIAL}" shell pidof "${PACKAGE}" 2>/dev/null | tr -d '\r' || true
}

current_focus() {
  adb -s "${SERIAL}" shell dumpsys window 2>/dev/null \
    | tr -d '\r' \
    | grep -m1 'mCurrentFocus=' || true
}

top_resumed_activity() {
  adb -s "${SERIAL}" shell dumpsys activity activities 2>/dev/null \
    | tr -d '\r' \
    | grep -m1 'topResumedActivity=' || true
}

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

assert_app_active() {
  local stage="$1"
  local pid focus resumed
  pid="$(app_pid)"
  focus="$(current_focus)"
  resumed="$(top_resumed_activity)"
  {
    echo "[${stage}]"
    echo "pid=${pid:-<none>}"
    echo "focus=${focus:-<none>}"
    echo "resumed=${resumed:-<none>}"
  } >> test-artifacts/foreground-checks.txt

  if [[ -z "${pid}" ]]; then
    echo "App process is not active during ${stage}."
    collect_diagnostics
    return 1
  fi
  if [[ "${focus}" != *"${PACKAGE}"* ]]; then
    echo "App window is not focused during ${stage}: ${focus:-<none>}"
    collect_diagnostics
    return 1
  fi
  if [[ "${resumed}" != *"${PACKAGE}"* ]]; then
    echo "App activity is not resumed during ${stage}: ${resumed:-<none>}"
    collect_diagnostics
    return 1
  fi
}

capture_screen() {
  local name="$1"
  assert_app_active "${name}"
  adb -s "${SERIAL}" exec-out screencap -p > "test-artifacts/screenshots/${name}.png"
  test -s "test-artifacts/screenshots/${name}.png"
}

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
  -gpu lavapipe \
  -no-snapshot \
  -noaudio \
  -no-boot-anim \
  -camera-back none \
  -memory 2048 \
  -cores 2 \
  -no-metrics \
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
adb -s "${SERIAL}" shell settings put secure immersive_mode_confirmations confirmed || true

# Use a complete APK installation so CI does not depend on incremental package mappings.
adb -s "${SERIAL}" install --no-incremental -r build/NebulaStride-debug.apk
adb -s "${SERIAL}" shell am force-stop "${PACKAGE}"
adb -s "${SERIAL}" logcat -c

COMPONENT="$(adb -s "${SERIAL}" shell cmd package resolve-activity --brief "${PACKAGE}" 2>/dev/null | tr -d '\r' | tail -n 1)"
if [[ "${COMPONENT}" != */* ]]; then
  echo "Could not resolve launcher activity for ${PACKAGE}: ${COMPONENT:-<none>}"
  exit 1
fi
adb -s "${SERIAL}" shell am start -W -n "${COMPONENT}"

PID=""
for _ in $(seq 1 45); do
  PID="$(app_pid)"
  [[ -n "${PID}" ]] && break
  sleep 1
done
if [[ -z "${PID}" ]]; then
  echo "App process did not become active."
  exit 1
fi

# Godot imports and compiles the first Compatibility shaders on initial launch.
sleep 12

# Fallback for emulator images that still show Android's first immersive-mode hint.
if [[ "$(current_focus)" != *"${PACKAGE}"* ]]; then
  adb -s "${SERIAL}" shell input tap 1040 390 || true
  sleep 2
fi

capture_screen "01-tutorial"
adb -s "${SERIAL}" shell input swipe 820 360 360 360 300
sleep 1
adb -s "${SERIAL}" shell input swipe 360 360 820 360 300
sleep 1
adb -s "${SERIAL}" shell input swipe 640 520 640 220 300
sleep 1
adb -s "${SERIAL}" shell input swipe 640 220 640 520 300
sleep 2
capture_screen "02-main-menu"
adb -s "${SERIAL}" shell input tap 640 330
sleep 5
adb -s "${SERIAL}" shell input swipe 640 400 350 400 300
adb -s "${SERIAL}" shell input swipe 350 400 850 400 300
adb -s "${SERIAL}" shell input swipe 640 500 640 230 300
adb -s "${SERIAL}" shell input swipe 640 250 640 540 300
sleep 3
capture_screen "03-gameplay"
adb -s "${SERIAL}" shell input keyevent 111
sleep 2
capture_screen "04-pause"
adb -s "${SERIAL}" shell input tap 640 300
sleep 2
adb -s "${SERIAL}" shell input keyevent 35
sleep 2
capture_screen "05-game-over"
adb -s "${SERIAL}" shell input tap 640 445
sleep 4
capture_screen "06-restart"

collect_diagnostics
if grep -E "FATAL EXCEPTION|Fatal signal [0-9]+|ANR in ${PACKAGE}|Process ${PACKAGE}.*has died|App crashed on incremental package ${PACKAGE}|Program linking failed|shader failed to compile" test-artifacts/logcat.txt; then
  echo "Crash, ANR, or shader failure marker found in logcat."
  exit 1
fi
trap - EXIT
cleanup
