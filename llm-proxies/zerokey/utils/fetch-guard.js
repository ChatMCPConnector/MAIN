const { CONFIG } = require('../config/constants')

// Kept in sync with the default `timeoutMs` of the provider `_fetch`
// implementations — that 300 s cap is the wait this module exists to shorten.
const DEFAULT_HARD_TIMEOUT_MS = 300_000

// Budgets are read from config in milliseconds but named in seconds, and the
// test suite runs on sub-second budgets — `0s` in a log line would hide which
// timer actually fired.
const formatDuration = (ms) => (ms >= 1000 ? `${Math.round(ms / 1000)}s` : `${Math.round(ms)}ms`)

/**
 * Shape a failure the way the provider clients have always shaped their fetch
 * failures: status 504, either a JSON error envelope or a plain message.
 *
 * A stall stays distinguishable from a timeout (`upstream_stall` vs
 * `request_timeout`) so the cause survives into the client and the log. Before
 * this, both surfaced as an anonymous 504 five minutes into a dead turn.
 */
function providerError({ stalled, budgetMs, jsonError }) {
  const message = stalled
    ? `Upstream stalled — no response headers for ${formatDuration(budgetMs)}. ` +
      'The connection took the request and then went silent; ' +
      'the turn was aborted instead of waiting further.'
    : `Request timed out after ${budgetMs / 1000}s`
  const err = jsonError
    ? new Error(JSON.stringify({ error: { type: stalled ? 'upstream_stall' : 'request_timeout', message } }))
    : new Error(message)
  err.status = 504
  err.statusCode = 504
  if (stalled) err.code = 'upstream_stall'
  return err
}

/**
 * Wait for `start(signal)` to produce response headers under a silence budget.
 *
 * node-fetch resolves as soon as the response *headers* arrive, so the header
 * phase is exactly the window in which a dead upstream is invisible: the socket
 * is established, the request body is fully sent, and the server simply never
 * answers. Without the stall timer below, only the caller's own hard cap ends
 * that wait — 300 s by default — and the caller learns nothing except a generic
 * 504. Measured live on 2026-10-02 (session brave-nebula): 131 kB sent,
 * `bytes_received` frozen, no stream watchdog in sight because no stream
 * existed yet.
 *
 * The budget is an *inactivity* budget on the header phase only; once the
 * headers are in, the caller owns the body, and CONFIG.STREAM_IDLE_TIMEOUT_MS
 * guards that. A slow but working request that stays below the budget is
 * returned untouched.
 *
 * @param {object} options
 * @param {(signal: AbortSignal) => Promise<any>} options.start - performs the request
 * @param {string} [options.url] - for the log line and the error message
 * @param {string} [options.label] - provider name for the log line
 * @param {number} [options.hardTimeoutMs] - caller's own budget; always armed
 * @param {number} [options.stallTimeoutMs] - silence budget; 0 disables it
 * @param {boolean} [options.jsonError] - JSON error envelope vs plain message
 * @returns {Promise<any>} the response, once its headers arrived
 */
async function fetchWithHeaderWatchdog({
  start,
  url = '',
  label = 'upstream',
  hardTimeoutMs = DEFAULT_HARD_TIMEOUT_MS,
  stallTimeoutMs = CONFIG.HEADER_IDLE_TIMEOUT_MS,
  jsonError = false,
}) {
  const controller = new AbortController()

  // Which timer fired, if any. Both abort through the same controller and
  // node-fetch rejects both with an identical AbortError, so the cause is
  // recorded here instead of being guessed in the catch block. `null` also
  // covers an abort that did not come from us, which must pass through
  // untouched.
  let firedBy = null

  const hardTimer = setTimeout(() => {
    firedBy = 'hard'
    controller.abort()
  }, hardTimeoutMs)

  // Only arm the stall budget while it is the shorter of the two. When the
  // caller passed a tighter cap, that cap is the budget and its expiry is a
  // timeout — relabelling it as a stall would misreport a deliberate timeout.
  const stallBudget = stallTimeoutMs > 0 && stallTimeoutMs < hardTimeoutMs ? stallTimeoutMs : 0
  const stallTimer = stallBudget
    ? setTimeout(() => {
        firedBy = 'stall'
        console.warn(
          `[FETCH] ⏱ ${label} upstream_stall — no response headers for ` +
            `${formatDuration(stallBudget)} (${url})`,
        )
        controller.abort()
      }, stallBudget)
    : null

  try {
    return await start(controller.signal)
  } catch (err) {
    if (!firedBy) throw err
    const stalled = firedBy === 'stall'
    throw providerError({ stalled, budgetMs: stalled ? stallBudget : hardTimeoutMs, jsonError })
  } finally {
    clearTimeout(hardTimer)
    if (stallTimer) clearTimeout(stallTimer)
  }
}

module.exports = { fetchWithHeaderWatchdog, providerError, formatDuration, DEFAULT_HARD_TIMEOUT_MS }
