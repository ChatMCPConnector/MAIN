// Regression test for readSSE's finalization contract and its stall watchdog.
//
// onDone may be async (the ask guard retries the upstream request from inside
// it). readSSE must await it — a fire-and-forget onDone would return control to
// the router while the retry was still streaming, and the response would be
// finalized twice.
//
// The watchdog half covers the failure from session
// ses_f06959c34ffem62VA5MinVvP4a (2026-10-01): a dead upstream stream left the
// read pending until the https.Agent idle timer killed the socket 301.9 s later.
//
// Run: node scripts/test-sse-reader.js
const { Readable } = require('stream')
const { readSSE } = require('../utils/sse-reader')

let failed = 0
function check(ok, label) {
  if (!ok) {
    console.error(`FAIL: ${label}`)
    failed++
  } else {
    console.log(`ok: ${label}`)
  }
}

const sse = (lines) => Readable.from([Buffer.from(lines.join(''))])
const line = (obj) => `data: ${JSON.stringify(obj)}\n\n`

async function run(lines) {
  const seen = []
  await readSSE(sse(lines), {
    onData: (d) => seen.push(d),
    onDone: () => seen.push({ done: true }),
    onError: (e) => seen.push({ error: e.message }),
  })
  return seen
}

// A Readable that emits `lines` and then goes silent forever — the shape of a
// dropped upstream connection. Never resolves the final await, so the stream
// stays open with no further 'end' and no 'error'.
const stallingSSE = (lines) =>
  Readable.from(
    (async function* () {
      for (const l of lines) yield Buffer.from(l)
      await new Promise(() => {})
    })(),
  )

;(async () => {
  // Basic parsing still works.
  {
    const seen = await run([line({ a: 1 }), line({ a: 2 }), 'data: [DONE]\n\n'])
    check(seen.filter((s) => s.a).length === 2, 'parses every data line')
    check(
      seen.some((s) => s.done),
      'onDone runs',
    )
  }

  // The contract this change protects: an async onDone is awaited to completion
  // before readSSE resolves.
  {
    let finished = false
    const lines = [line({ a: 1 }), 'data: [DONE]\n\n']
    const stream = sse(lines)
    await readSSE(stream, {
      onData: () => {},
      onDone: async () => {
        await new Promise((r) => setTimeout(r, 60))
        finished = true
      },
      onError: () => {},
    })
    check(finished, 'async onDone is awaited before readSSE resolves')
  }

  // Same when the stream ends without an explicit [DONE].
  {
    let finished = false
    await readSSE(sse([line({ a: 1 }), '\n']), {
      onData: () => {},
      onDone: async () => {
        await new Promise((r) => setTimeout(r, 40))
        finished = true
      },
      onError: () => {},
    })
    check(finished, 'async onDone is awaited on stream end too')
  }

  // onDone must still run exactly once.
  {
    let count = 0
    await readSSE(sse([line({ a: 1 }), 'data: [DONE]\n\n']), {
      onData: () => {},
      onDone: () => count++,
      onError: () => {},
    })
    check(count === 1, 'onDone runs exactly once')
  }

  // A throwing onDone is routed to onError, not an unhandled rejection.
  {
    const seen = []
    await readSSE(sse(['data: [DONE]\n\n']), {
      onData: () => {},
      onDone: () => {
        throw new Error('boom')
      },
      onError: (e) => seen.push(e.message),
    })
    check(seen.includes('boom'), 'a throwing onDone is routed to onError')
  }

  // ── stall watchdog ───────────────────────────────────────────────────────

  // A stream that goes silent is aborted, and the abort names the cause
  // instead of surfacing as an opaque socket error minutes later.
  {
    const seen = []
    let done = false
    await readSSE(stallingSSE([line({ a: 1 })]), {
      onData: (d) => seen.push(d),
      onDone: () => {
        done = true
      },
      onError: (e) => seen.push(e),
      idleTimeoutMs: 60,
    })
    const data = seen.filter((s) => s && s.a)
    check(data.length === 1 && data[0].a === 1, 'stall: data before the silence was delivered')
    const err = seen.find((s) => s instanceof Error)
    check(!!err, 'stall: onError was called')
    check(err && err.code === 'stream_stalled', 'stall: error is tagged stream_stalled')
    check(!!err && /stalled/.test(err.message), 'stall: the message states the stall')
    check(!done, 'stall: onDone did not run — a stall is a failure, not a completion')
  }

  // A slow-but-alive stream must survive: the budget is re-armed per chunk, so
  // a turn that streams for longer than one budget in total is never cut off.
  {
    const seen = []
    const chunk = line({ a: 1 })
    const slow = Readable.from(
      (async function* () {
        for (let i = 0; i < 4; i++) {
          await new Promise((r) => setTimeout(r, 40))
          yield Buffer.from(chunk)
        }
      })(),
    )
    await readSSE(slow, {
      onData: (d) => seen.push(d),
      onDone: () => seen.push({ done: true }),
      onError: (e) => seen.push(e),
      idleTimeoutMs: 90,
    })
    // 4 chunks x 40 ms = 160 ms of streaming, well past the 90 ms budget.
    check(seen.filter((s) => s && s.a).length === 4, 'slow-but-alive stream is not cut off')
    check(seen.some((s) => s && s.done), 'slow-but-alive stream still finishes normally')
  }

  // A budget of 0 disables the watchdog entirely and must not break reading.
  {
    const seen = await new Promise((resolve) => {
      const acc = []
      readSSE(stallingSSE([line({ a: 1 }), line({ a: 2 })]), {
        onData: (d) => acc.push(d),
        onDone: () => resolve(acc),
        onError: (e) => resolve([e]),
        idleTimeoutMs: 0,
      })
      // Nothing will ever finish: the watchdog is off, so end the stream by
      // hand after the first chunk was processed.
      setTimeout(() => resolve(acc), 150)
    })
    check(seen.filter((s) => s && s.a).length === 2, 'idleTimeoutMs:0 still reads every chunk')
  }

  // No stray timer: readSSE must not hold the process open after it resolves.
  {
    const before = process.getActiveResourcesInfo().filter((r) => r === 'Timeout').length
    await run([line({ a: 1 }), 'data: [DONE]\n\n'])
    await new Promise((r) => setTimeout(r, 30))
    const after = process.getActiveResourcesInfo().filter((r) => r === 'Timeout').length
    check(after <= before, 'no watchdog timer survives a completed stream')
  }

  if (failed) {
    console.error(`\n${failed} check(s) failed`)
    process.exit(1)
  }
  console.log('\nOK: readSSE finalization contract + stall watchdog hold')
})()
