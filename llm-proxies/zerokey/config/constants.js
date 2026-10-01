/**
 * Application constants and configuration.
 */

// How long an SSE stream may stay completely silent before it counts as
// stalled. This is an *inactivity* budget, not a total budget: a long but
// productive turn (high reasoning effort streams for minutes) resets the timer
// on every chunk and is never touched.
//
// Without it a dead upstream connection is only ended by the https.Agent idle
// timer in the provider clients (300_000 ms), so a single dead turn parks the
// IDE on a spinner for five minutes and opencode can only break out with a
// manual abort. Measured live in session ses_f06959c34ffem62VA5MinVvP4a
// (2026-10-01): 301.9 s of silence between the last tool result and the retry.
const STREAM_IDLE_TIMEOUT_MS =
  Number(process.env.ZEROKEY_STREAM_IDLE_TIMEOUT_MS) > 0
    ? Number(process.env.ZEROKEY_STREAM_IDLE_TIMEOUT_MS)
    : 90_000

const CONFIG = {
  PORT: process.env.PORT || 7250,
  STREAM_IDLE_TIMEOUT_MS,
}

module.exports = { CONFIG }
