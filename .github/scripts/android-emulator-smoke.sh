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

wait_for_app_foreground() {
  local attempts="${1:-60}"
  local pid focus resumed
  for _ in $(seq 1 "${attempts}"); do
    pid="$(app_pid)"
    focus="$(current_focus)"
    resumed="$(top_resumed_activity)"
    if [[ -n "${pid}" && "${focus}" == *"${PACKAGE}"* && "${resumed}" == *"${PACKAGE}"* ]]; then
      return 0
    fi
    sleep 1
  done
  echo "App did not reach a stable foreground state."
  assert_app_active "foreground-timeout" || true
  return 1
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
  -memory 3072 \
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
  BOOT_COMPLETED="$(adb -s "${SERIAL}" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')"
  BOOT_ANIM="$(adb -s "${SERIAL}" shell getprop init.svc.bootanim 2>/dev/null | tr -d '\r')"
  if [[ "${BOOT_COMPLETED}" == "1" && "${BOOT_ANIM}" == "stopped" ]]; then
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

adb -s "${SERIAL}" wait-for-device
adb -s "${SERIAL}" shell input keyevent 82 || true
adb -s "${SERIAL}" shell settings put global window_animation_scale 0
adb -s "${SERIAL}" shell settings put global transition_animation_scale 0
adb -s "${SERIAL}" shell settings put global animator_duration_scale 0
adb -s "${SERIAL}" shell wm size 1280x720
adb -s "${SERIAL}" shell wm density 320
adb -s "${SERIAL}" shell settings put system accelerometer_rotation 0
adb -s "${SERIAL}" shell settings put system user_rotation 1
adb -s "${SERIAL}" shell settings put secure immersive_mode_confirmations confirmed || true

# sys.boot_completed is published before Google services and the launcher have
# completely settled. Wait for pending broadcasts and a stable launcher so
# Godot does not compete with first-boot work for the software renderer.
adb -s "${SERIAL}" shell am wait-for-broadcast-idle >/dev/null 2>&1 || true
for _ in $(seq 1 12); do
  FOCUS="$(current_focus)"
  if [[ -n "${FOCUS}" && "${FOCUS}" != *"Application Not Responding"* ]]; then
    break
  fi
  sleep 5
done
sleep 45

if current_focus | grep -q "Application Not Responding"; then
  echo "Android launcher remained in ANR after boot stabilization."
  collect_diagnostics
  exit 1
fi

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
wait_for_app_foreground 60

# Allow initial resource upload and Compatibility shader compilation to settle.
sleep 10

# Fallback for emulator images that still show Android's first immersive-mode hint.
if [[ "$(current_focus)" != *"${PACKAGE}"* ]]; then
  adb -s "${SERIAL}" shell input tap 1040 390 || true
  wait_for_app_foreground 10
fi

# Validate that the tutorial is visible, then leave it through its dedicated button.
# All four swipe directions are exercised in actual gameplay below.
capture_screen "01-tutorial"
adb -s "${SERIAL}" shell input tap 640 565
sleep 2
capture_screen "02-main-menu"
adb -s "${SERIAL}" shell input tap 640 330
sleep 4

# Exercise lane changes, jump, and slide while the runner is active.
adb -s "${SERIAL}" shell input swipe 640 400 350 400 300
adb -s "${SERIAL}" shell input swipe 350 400 850 400 300
adb -s "${SERIAL}" shell input swipe 640 500 640 230 300
adb -s "${SERIAL}" shell input swipe 640 250 640 540 300
sleep 2
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
sleep 3
capture_screen "06-restart"

collect_diagnostics
if grep -E "FATAL EXCEPTION|Fatal signal [0-9]+|ANR in ${PACKAGE}|Process ${PACKAGE}.*has died|App crashed on incremental package ${PACKAGE}|Program linking failed|shader failed to compile" test-artifacts/logcat.txt; then
  echo "Crash, ANR, or shader failure marker found in logcat."
  exit 1
fi
trap - EXIT
cleanup
