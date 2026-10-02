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

// The same idea for the phase *before* the first response byte. node-fetch
// resolves when the response headers arrive, so a dead upstream that never
// sends them is only ended by the hard cap in the provider `_fetch` (300_000
// ms) — and the stream watchdog above never sees it, because no stream exists
// yet. Measured live on 2026-10-02 (session brave-nebula): socket ESTABLISHED,
// 131 kB request body sent, `bytes_received` frozen, zero stall log lines.
// Measured against the same upstream on 2026-10-02: first byte after 8–12 s
// (worst observed 70 s), so 90 s stays above a slow-but-working request.
const HEADER_IDLE_TIMEOUT_MS =
  Number(process.env.ZEROKEY_HEADER_TIMEOUT_MS) > 0
    ? Number(process.env.ZEROKEY_HEADER_TIMEOUT_MS)
    : 90_000

const CONFIG = {
  PORT: process.env.PORT || 7250,
  STREAM_IDLE_TIMEOUT_MS,
  HEADER_IDLE_TIMEOUT_MS,
}

module.exports = { CONFIG }
