// Regression test for readSSE's finalization contract.
//
// onDone may be async (the ask guard retries the upstream request from inside
// it). readSSE must await it — a fire-and-forget onDone would return control to
// the router while the retry was still streaming, and the response would be
// finalized twice.
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

  if (failed) {
    console.error(`\n${failed} check(s) failed`)
    process.exit(1)
  }
  console.log('\nOK: readSSE finalization contract holds')
})()
