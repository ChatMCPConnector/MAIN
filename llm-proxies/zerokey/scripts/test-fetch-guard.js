// Regression test for the response-header watchdog in utils/fetch-guard.js.
//
// The failure it covers was measured live on 2026-10-02 (session brave-nebula):
// the socket was ESTABLISHED, 131 kB of request body had been sent, and
// `bytes_received` never moved. node-fetch resolves on response headers, so
// nothing was streaming yet and the stream watchdog (utils/sse-reader.js) had
// nothing to guard. The wait only ended when the provider `_fetch` hard cap
// fired at 300 s — and opencode immediately retried into the same silence.
//
// Run: node scripts/test-fetch-guard.js

// The provider-level cases below need a real header budget, and it has to be in
// place before config/constants.js is read, so the override comes first.
process.env.ZEROKEY_HEADER_TIMEOUT_MS = '400'

const http = require('http')
const { execFileSync } = require('child_process')
const path = require('path')
const { fetchWithHeaderWatchdog } = require('../utils/fetch-guard')
const { ChatGPTAPI } = require('../providers/chatgpt/api')
const { BaseAPI } = require('../providers/base/BaseAPI')

let failed = 0
function check(ok, label) {
  if (!ok) {
    console.error(`FAIL: ${label}`)
    failed++
  } else {
    console.log(`ok: ${label}`)
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// Stands in for node-fetch: resolves when the "server" answers, rejects with
// the same AbortError on an abort — that identity is why the guard records
// which timer fired instead of inspecting the error.
const hanging = (signal, log) =>
  new Promise((_, reject) => {
    signal.addEventListener('abort', () => {
      if (log) log.aborted = true
      const err = new Error('The user aborted a request.')
      err.name = 'AbortError'
      reject(err)
    })
  })

const lateResponse = (ms, value) => (_signal) => sleep(ms).then(() => value)

const envelope = (err) => {
  try {
    return JSON.parse(err.message).error
  } catch {
    return null
  }
}

// ── real sockets ────────────────────────────────────────────────────────────
// A local server that reads the request and then never answers: the exact shape
// of the live hang, reproducible on demand and without touching the internet.
const listen = (handler) =>
  new Promise((resolve) => {
    const server = http.createServer(handler)
    server.listen(0, '127.0.0.1', () => resolve({ server, port: server.address().port }))
  })

const answerAfter = (ms) => async (req, res) => {
  req.resume()
  await sleep(ms)
  res.writeHead(200, { 'content-type': 'application/json' })
  res.end('{"ok":true}')
}

const neverAnswer = (req) => req.resume()

// The provider clients build an https.Agent; a plain-HTTP test server needs a
// matching agent, and the fetch logic under test is untouched by that swap.
// `_headers` is normally seeded from the capture JSON; the tests only exercise
// the fetch path, so an empty object is the honest stand-in for it.
const localAgent = () => new http.Agent({ keepAlive: true })
const bareClient = (Cls) => {
  const api = new Cls({ log: false })
  api._headers = {}
  api._httpAgent = localAgent()
  return api
}

const withServer = async (handler, fn) => {
  const { server, port } = await listen(handler)
  try {
    return await fn(port)
  } finally {
    server.close()
  }
}

;(async () => {
  // ── stall watchdog ────────────────────────────────────────────────────────

  // An upstream that takes the request and then says nothing is aborted after
  // the silence budget, and the error names the cause instead of arriving as an
  // anonymous 504 five minutes later.
  {
    const log = {}
    const started = Date.now()
    let err = null
    try {
      await fetchWithHeaderWatchdog({
        start: (signal) => hanging(signal, log),
        url: 'https://chatgpt.com/backend-api/conversation',
        label: 'ChatGPTAPI',
        hardTimeoutMs: 5_000,
        stallTimeoutMs: 120,
        jsonError: true,
      })
    } catch (e) {
      err = e
    }
    const elapsed = Date.now() - started
    check(!!err, 'stall: the request did not hang forever')
    check(err && err.code === 'upstream_stall', 'stall: error is tagged upstream_stall')
    check(err && err.status === 504 && err.statusCode === 504, 'stall: error carries status 504')
    check(elapsed < 2_000, `stall: aborted at the budget (${elapsed} ms), not at the 5 s hard cap`)
    check(log.aborted === true, 'stall: the underlying request was really aborted')
    const body = err && envelope(err)
    check(body && body.type === 'upstream_stall', 'stall: the JSON envelope keeps the cause')
    check(body && /stalled/.test(body.message), 'stall: the message states the stall')
  }

  // A slow but working upstream must survive: the budget is an inactivity
  // budget, so a request that answers inside it is returned untouched.
  {
    const res = await fetchWithHeaderWatchdog({
      start: lateResponse(60, { status: 200 }),
      hardTimeoutMs: 5_000,
      stallTimeoutMs: 300,
    })
    check(res && res.status === 200, 'slow-but-alive request is not cut off')
  }

  // The caller's own cap wins when it is the shorter of the two, and stays a
  // timeout — a deliberate 2 s cap must not be reported as an upstream stall.
  {
    let err = null
    try {
      await fetchWithHeaderWatchdog({
        start: (signal) => hanging(signal),
        hardTimeoutMs: 80,
        stallTimeoutMs: 5_000,
        jsonError: true,
      })
    } catch (e) {
      err = e
    }
    check(!!err, 'tight cap: the request still ends')
    check(err && err.code !== 'upstream_stall', 'tight cap: not relabelled as a stall')
    check(
      err && envelope(err)?.type === 'request_timeout',
      'tight cap: reported as request_timeout',
    )
    check(
      err && /timed out after 0.08s/.test(envelope(err)?.message || ''),
      'tight cap: message quotes the budget',
    )
  }

  // A stall budget of 0 disables the watchdog, and only the hard cap is left.
  {
    let err = null
    try {
      await fetchWithHeaderWatchdog({
        start: (signal) => hanging(signal),
        hardTimeoutMs: 120,
        stallTimeoutMs: 0,
        jsonError: true,
      })
    } catch (e) {
      err = e
    }
    check(
      err && envelope(err)?.type === 'request_timeout',
      'stallTimeoutMs:0 leaves only the hard cap',
    )
  }

  // A stall budget of 0 must not stop a working request either.
  {
    const res = await fetchWithHeaderWatchdog({
      start: lateResponse(40, { status: 201 }),
      hardTimeoutMs: 5_000,
      stallTimeoutMs: 0,
    })
    check(res && res.status === 201, 'stallTimeoutMs:0 still returns a working response')
  }

  // ── unrelated failures ────────────────────────────────────────────────────

  // An error that did not come from our timers passes through untouched — the
  // 504 wrapper is for "we gave up waiting", not for every failure.
  {
    const boom = new TypeError('fetch failed')
    let err = null
    try {
      await fetchWithHeaderWatchdog({
        start: () => Promise.reject(boom),
        hardTimeoutMs: 5_000,
        stallTimeoutMs: 3_000,
      })
    } catch (e) {
      err = e
    }
    check(err === boom, 'a non-timeout error is rethrown unchanged')
    check(err && !err.status, 'a non-timeout error is not dressed up as a 504')
  }

  // The plain-message shape used by providers/base/BaseAPI.js.
  {
    let err = null
    try {
      await fetchWithHeaderWatchdog({
        start: (signal) => hanging(signal),
        hardTimeoutMs: 5_000,
        stallTimeoutMs: 60,
      })
    } catch (e) {
      err = e
    }
    check(err && envelope(err) === null, 'plain shape: the message is not a JSON envelope')
    check(err && /stalled/.test(err.message), 'plain shape: the message states the stall')
  }

  // No stray timer: neither watchdog may survive a resolved request.
  {
    const before = process.getActiveResourcesInfo().filter((r) => r === 'Timeout').length
    await fetchWithHeaderWatchdog({
      start: lateResponse(10, { status: 200 }),
      hardTimeoutMs: 5_000,
      stallTimeoutMs: 200,
    })
    await sleep(30)
    const after = process.getActiveResourcesInfo().filter((r) => r === 'Timeout').length
    check(after <= before, 'no watchdog timer survives a completed request')
  }

  // ── against the real provider clients ─────────────────────────────────────

  // The live failure reproduced over a real socket: ChatGPTAPI._fetch against a
  // server that reads 4 kB of request body and then goes quiet. 400 ms budget
  // (set at the top of this file), 300 s hard cap — the abort must come from the
  // budget, and the socket must be gone when it does.
  {
    const api = bareClient(ChatGPTAPI)
    let err = null
    const started = Date.now()
    try {
      await withServer(neverAnswer, (port) =>
        api._fetch(
          `http://127.0.0.1:${port}/backend-api/conversation`,
          { method: 'POST', body: 'x'.repeat(4096) },
          false,
          300_000,
        ),
      )
    } catch (e) {
      err = e
    }
    const elapsed = Date.now() - started
    check(!!err, 'real socket: the stalled request ends instead of hanging')
    check(err && envelope(err)?.type === 'upstream_stall', 'real socket: reported as upstream_stall')
    check(
      elapsed > 300 && elapsed < 3_000,
      `real socket: ended at the 400 ms budget (${elapsed} ms), not at 300 s`,
    )
  }

  // The negative test that matters most: a server that is merely slow — well
  // under the budget — still produces a normal response, JSON parse included.
  {
    const api = bareClient(ChatGPTAPI)
    const res = await withServer(answerAfter(150), (port) =>
      api._fetch(`http://127.0.0.1:${port}/backend-api/me`, { method: 'GET' }, true, 300_000),
    )
    check(res && res.ok === true, 'real socket: a slow but answering request still succeeds')
    check(res && res.data && res.data.ok === true, 'real socket: the JSON body is parsed as before')
  }

  // The same two cases through the shared base client, which uses the plain
  // message shape instead of the JSON envelope.
  {
    const api = bareClient(BaseAPI)
    let err = null
    try {
      await withServer(neverAnswer, (port) =>
        api._fetch(`http://127.0.0.1:${port}/api/account`, { method: 'GET' }),
      )
    } catch (e) {
      err = e
    }
    check(!!err && /stalled/.test(err.message), 'BaseAPI: a stalled request is named as such')
    check(!!err && err.status === 504, 'BaseAPI: the stall still carries status 504')

    const ok = await withServer(answerAfter(80), (port) =>
      api._fetch(`http://127.0.0.1:${port}/api/account`, { method: 'GET' }, true),
    )
    check(ok && ok.data && ok.data.ok === true, 'BaseAPI: a slow but answering request still succeeds')
  }

  // ── configuration ─────────────────────────────────────────────────────────

  // The default must sit above a slow-but-working answer (worst observed live:
  // 70 s to first byte) and be overridable per process.
  {
    const baseEnv = { ...process.env }
    delete baseEnv.ZEROKEY_HEADER_TIMEOUT_MS
    const read = (env) =>
      execFileSync(
        process.execPath,
        [
          '-e',
          'process.stdout.write(String(require(process.argv[1]).CONFIG.HEADER_IDLE_TIMEOUT_MS))',
          path.join(__dirname, '..', 'config', 'constants.js'),
        ],
        { env: { ...baseEnv, ...env }, encoding: 'utf8' },
      )
    check(read({}) === '90000', 'default header budget is 90s')
    check(read({ ZEROKEY_HEADER_TIMEOUT_MS: '1234' }) === '1234', 'ZEROKEY_HEADER_TIMEOUT_MS overrides it')
    check(read({ ZEROKEY_HEADER_TIMEOUT_MS: '0' }) === '90000', 'a 0 override falls back to the default')
  }

  if (failed) {
    console.error(`\n${failed} check(s) failed`)
    process.exit(1)
  }
  console.log('\nOK: the response-header watchdog holds')
})()
