// End-to-end test of the ask guard against a scripted upstream, so the
// behaviour is deterministic: the fake provider answers attempt 1 with nothing
// but a generic ask, and attempt 2 with real work.
//
// Verifies the three cases that matter:
//   A) ask + real tool calls  -> calls go through, ask does not block
//   B) ask only              -> turn is retried, retry's work is delivered
//   C) real blocker ask only -> passed through, NOT retried
//
// Run: node scripts/test-ask-guard-e2e.js
const { Readable } = require('stream')
const { StreamPipeline } = require('../engine/pipeline')
const { buildNudge } = require('../engine/ask-guard')

console.debug = () => {}
console.warn = () => {}

let failed = 0
function check(ok, label) {
  if (!ok) {
    console.error(`FAIL: ${label}`)
    failed++
  } else {
    console.log(`ok: ${label}`)
  }
}

const OPEN = '⟦'
const CLOSE = '⟧'
const SEP = '¦'

const mhi = (s) =>
  `data: ${JSON.stringify({ p: '/message/content/parts/0', o: 'append', v: s })}\n\n`

// A scripted upstream: `turns` is a list of turns, each a list of MHI blocks
// the model emits in that turn. Every block needs its own append event —
// scanning is incremental and only closes a block on ⟧.
//
// The type assertion is not paranoia: nesting a turn one level too deep
// ([[blocks]] instead of [blocks]) turns three blocks into ONE block whose
// payload is the comma-joined string "glob¦…,ls¦…,cmd¦…". The parser then
// correctly reports one malformed call, the test sees a short tool list and
// passes — while asserting nothing about the case it was written for. That
// happened on 2026-09-30 and cost a debugging round.
function fakeStream(turns) {
  const chunks = []
  for (const [t, turn] of turns.entries()) {
    if (!Array.isArray(turn)) throw new TypeError(`Runde ${t} ist kein Array: ${typeof turn}`)
    for (const [b, block] of turn.entries()) {
      if (typeof block !== 'string') {
        throw new TypeError(
          `Runde ${t}, Block ${b} ist kein String (${Array.isArray(block) ? 'Array' : typeof block}). ` +
            `Ein Turn ist eine flache Liste von Block-Strings — vermutlich ein Array zu viel verschachtelt.`,
        )
      }
      chunks.push(mhi(OPEN + block + CLOSE))
      chunks.push(mhi('\n'))
    }
  }
  chunks.push('data: [DONE]\n\n')
  return Readable.from([Buffer.from(chunks.join(''))])
}

// Like fakeStream, but the turns are raw assistant TEXT with no MHI wrapper —
// the shape of a turn that explains itself instead of calling a tool. The other
// cases all script tool blocks, so text-only drift needs its own builder.
function fakeTextStream(turns) {
  const chunks = []
  for (const turn of turns) {
    chunks.push(mhi(turn))
  }
  chunks.push('data: [DONE]\n\n')
  return Readable.from([Buffer.from(chunks.join(''))])
}

// Run a text-only upstream through the pipeline, the same way run() does for
// tool turns, and report what the guard decided.
async function runText(label, upstreamTurns, { expectRetry, expectReason }) {
  const res = fakeRes()
  const pipeline = new StreamPipeline(res, session, 'chatgpt', 'opencode', messages)
  pipeline.ephemeralMode = false
  pipeline.rawMode = false

  let attempts = 0
  let reason = null
  const { chatgptStreamHandler } = require('../providers/chatgpt/stream-handler')
  const retry = async (info) => {
    attempts++
    reason = info.reason
    const next = new StreamPipeline(res, session, 'chatgpt', 'opencode', messages)
    next.ephemeralMode = false
    next.rawMode = false
    await chatgptStreamHandler(fakeStream(upstreamTurns.slice(1)), session, next)
    return true
  }

  await chatgptStreamHandler(fakeTextStream(upstreamTurns.slice(0, 1)), session, pipeline, retry)

  const names = res.toolNames()
  console.log(`\n[${label}]`)
  console.log(`  attempts=${attempts} reason=${reason} tools=[${names}]`)
  check(attempts === (expectRetry ? 1 : 0), `${label}: retry count ${expectRetry ? 1 : 0}`)
  if (expectRetry) check(reason === expectReason, `${label}: reason is ${expectReason} (ist ${reason})`)
  return { res, names, attempts }
}

// Collect everything the pipeline writes to the fake response.
function fakeRes() {
  const out = { chunks: [], ended: false }
  out.setHeader = () => {}
  out.write = (s) => out.chunks.push(s)
  out.end = () => {
    out.ended = true
  }
  out.body = () => out.chunks.join('')
  out.toolNames = () => {
    const names = []
    for (const c of out.chunks) {
      for (const line of c.split('\n')) {
        if (!line.startsWith('data: ')) continue
        try {
          const j = JSON.parse(line.slice(6))
          for (const tc of j.choices?.[0]?.delta?.tool_calls || []) {
            names.push(tc.function.name)
          }
        } catch {}
      }
    }
    return names
  }
  out.finishReasons = () => {
    const r = []
    for (const c of out.chunks) {
      for (const line of c.split('\n')) {
        if (!line.startsWith('data: ')) continue
        try {
          const j = JSON.parse(line.slice(6))
          if (j.choices?.[0]?.finish_reason) r.push(j.choices[0].finish_reason)
        } catch {}
      }
    }
    return r
  }
  return out
}

const session = { chatSessionId: 'c1', parentMessageId: 'p1', toolCalling: true, model: 'auto' }
const messages = [
  { role: 'system', content: 'You are opencode' },
  { role: 'user', content: 'analysiere den kompletten /workspaces bereich' },
]

const genericAsk = `ask${SEP}question=What change or coding task should I perform in this project?`
const realAsk = `ask${SEP}question=Which port should the server listen on?`
const reads = [`glob${SEP}path=/workspaces${SEP}pattern=*`, `ls${SEP}path=/workspaces/MAIN`]

// Verbatim assistant turn from ses_f06959c34ffem62VA5MinVvP4a: the model denies
// access to the machine and offers to work from uploaded files instead.
const OBSERVED_NO_ACCESS_TURN =
  'Es sieht so aus, als wäre der Chat in eine Schleife geraten: Es wurden ' +
  'mehrfach dieselben Agenten-/MHI-Anweisungen und der Repository-Analyseauftrag ' +
  'eingefügt.\n\nKurz gesagt:\n- Die MHI-Blöcke sind **nur Anweisungen für einen ' +
  'bestimmten Coding-Agenten-Workflow**, nicht normale Chat-Befehle.\n- Ich habe ' +
  'hier **keinen Zugriff auf dein `/workspaces/MAIN`**, außer du gibst ' +
  'Dateien/Ergebnisse über passende Uploads oder Inhalte weiter.'

async function run(label, upstreamTurns, { expectRetry }) {
  const res = fakeRes()
  const pipeline = new StreamPipeline(res, session, 'chatgpt', 'opencode', messages)
  pipeline.ephemeralMode = false
  pipeline.rawMode = false

  let attempts = 0
  const retry = async () => {
    attempts++
    const { chatgptStreamHandler } = require('../providers/chatgpt/stream-handler')
    const next = new StreamPipeline(res, session, 'chatgpt', 'opencode', messages)
    next.ephemeralMode = false
    next.rawMode = false
    await chatgptStreamHandler(fakeStream(upstreamTurns.slice(1)), session, next)
    return true
  }

  const { chatgptStreamHandler } = require('../providers/chatgpt/stream-handler')
  await chatgptStreamHandler(fakeStream(upstreamTurns.slice(0, 1)), session, pipeline, retry)

  const names = res.toolNames()
  console.log(`\n[${label}]`)
  console.log(`  attempts=${attempts} tools=[${names}] finish=${res.finishReasons().join(',')}`)
  console.log(`  ended=${res.ended}`)

  check(attempts === (expectRetry ? 1 : 0), `${label}: retry count ${expectRetry ? 1 : 0}`)
  return { res, names, attempts }
}

;(async () => {
  // A) generic ask + real tool calls in the same turn: no retry, work delivered.
  {
    const { names } = await run('A ask+tools', [[genericAsk, ...reads]], { expectRetry: false })
    check(!names.includes('question'), 'A: generic ask not emitted as a tool call')
    // opencode maps the generic MHI `ls` onto its native `read` tool.
    check(names.includes('glob') && names.includes('read'), 'A: real tool calls survive')
  }

  // B) generic ask alone: turn would end empty, so it is retried.
  {
    const { names } = await run('B ask only', [[genericAsk], reads], { expectRetry: true })
    check(!names.includes('question'), 'B: generic ask not emitted')
    check(names.includes('glob') && names.includes('read'), 'B: retry work delivered to the IDE')
  }

  // C) real blocker alone: must be passed through, never suppressed.
  {
    const { names, attempts } = await run('C real blocker', [[realAsk]], { expectRetry: false })
    check(names.includes('question'), 'C: real blocker reaches the IDE')
    check(attempts === 0, 'C: real blocker is not retried')
  }

  // D) the nudge the retry sends must exist and instruct continuation.
  {
    await run('D nudge', [[genericAsk], reads], { expectRetry: true })
    const nudge = buildNudge('generic-ask')
    check(nudge.includes('<internal>'), 'D: nudge is wrapped as internal context')
    check(/continue the task/i.test(nudge), 'D: nudge tells the model to continue the task')
    check(
      /no output at all/i.test(buildNudge('empty-turn')),
      'D: the empty-turn nudge names the actual failure',
    )
  }

  // E) A provider that passes no retry (claude/deepseek/qwen still call
  // sendFinalChunk) must keep emitting the ask: without a retry, suppressing an
  // ask-only turn would end the response empty and stop the agent harder than
  // the question ever did.
  {
    const res = fakeRes()
    const pipeline = new StreamPipeline(res, session, 'claude', 'opencode', messages)
    pipeline.ephemeralMode = false
    pipeline.rawMode = false
    const { chatgptStreamHandler } = require('../providers/chatgpt/stream-handler')
    // no retry argument — mirrors the other providers' stream handlers
    await chatgptStreamHandler(fakeStream([[genericAsk]]), session, pipeline, undefined)
    const names = res.toolNames()
    console.log('\n[E no retry]')
    console.log(`  tools=[${names}]`)
    check(names.includes('question'), 'E: without a retry the ask is still emitted')
    check(res.finishReasons().includes('tool_calls'), 'E: finish_reason stays tool_calls')
  }

  // F) An empty turn — no tool calls, no visible text (observed live: a turn of
  // pure whitespace) — is also wasted and must be retried.
  {
    const res = fakeRes()
    const pipeline = new StreamPipeline(res, session, 'chatgpt', 'opencode', messages)
    pipeline.ephemeralMode = false
    pipeline.rawMode = false
    let attempts = 0
    let reason = null
    const { chatgptStreamHandler } = require('../providers/chatgpt/stream-handler')
    const retry = async (info) => {
      attempts++
      reason = info.reason
      const next = new StreamPipeline(res, session, 'chatgpt', 'opencode', messages)
      next.ephemeralMode = false
      next.rawMode = false
      await chatgptStreamHandler(fakeStream([reads]), session, next)
      return true
    }
    // whitespace only — no MHI block at all
    await chatgptStreamHandler(fakeStream([[]]), session, pipeline, retry)
    console.log('\n[F empty turn]')
    console.log(`  attempts=${attempts} reason=${reason} tools=[${res.toolNames()}]`)
    check(attempts === 1, 'F: empty turn is retried once')
    check(reason === 'empty-turn', 'F: reported as empty-turn')
    check(res.toolNames().includes('glob'), 'F: retry work reaches the IDE')
  }

  // G) A real final answer is text and must never be retried.
  {
    const res = fakeRes()
    const pipeline = new StreamPipeline(res, session, 'chatgpt', 'opencode', messages)
    pipeline.ephemeralMode = false
    pipeline.rawMode = false
    let attempts = 0
    const { chatgptStreamHandler } = require('../providers/chatgpt/stream-handler')
    // The model wrote a real answer: no MHI block, just text.
    await chatgptStreamHandler(
      Readable.from([
        Buffer.from(
          'data: ' +
            JSON.stringify({
              p: '/message/content/parts/0',
              o: 'append',
              v: 'Die Analyse ist fertig.',
            }) +
            '\n\ndata: [DONE]\n\n',
        ),
      ]),
      session,
      pipeline,
      async () => {
        attempts++
        return true
      },
    )
    console.log('\n[G final answer]')
    console.log(`  attempts=${attempts}`)
    check(attempts === 0, 'G: a real answer is never retried')
    check(res.finishReasons().includes('stop'), 'G: a real answer finishes as stop')
  }

  // H) An MHI tool the IDE has no mapping for (`errors` is vscode-only) must be
  // reported as unavailable, not leaked as raw ⟦errors¦…⟧ syntax into the answer.
  {
    const res = fakeRes()
    const pipeline = new StreamPipeline(res, session, 'chatgpt', 'opencode', messages)
    pipeline.ephemeralMode = false
    pipeline.rawMode = false
    const { chatgptStreamHandler } = require('../providers/chatgpt/stream-handler')
    await chatgptStreamHandler(
      fakeStream([[`errors${SEP}path=/workspaces/zerokey-v2.0`]]),
      session,
      pipeline,
      null,
    )
    const body = res.body()
    console.log('\n[H unavailable tool]')
    console.log(`  text contains raw MHI: ${body.includes('errors' + SEP)}`)
    check(!body.includes('errors' + SEP + 'path='), 'H: raw MHI syntax is not leaked')
    check(/nicht verfügbar/.test(body), 'H: tool is reported as unavailable')
    check(res.toolNames().length === 0, 'H: no bogus tool call emitted')
  }

  // I) Drift written as plain text: the same clarification, no ⟦ask⟧ anywhere.
  {
    const res = fakeRes()
    const pipeline = new StreamPipeline(res, session, 'chatgpt', 'opencode', messages)
    pipeline.ephemeralMode = false
    pipeline.rawMode = false
    let attempts = 0
    let reason = null
    const { chatgptStreamHandler } = require('../providers/chatgpt/stream-handler')
    const retry = async (info) => {
      attempts++
      reason = info.reason
      const next = new StreamPipeline(res, session, 'chatgpt', 'opencode', messages)
      next.ephemeralMode = false
      next.rawMode = false
      await chatgptStreamHandler(fakeStream([reads]), session, next)
      return true
    }
    const drift =
      'I have the `engine/compiler.js` and project architecture context loaded. ' +
      'What would you like me to do with it?\n\nI can, for example:\n- review `ToolCompiler`'
    await chatgptStreamHandler(
      Readable.from([
        Buffer.from(
          'data: ' +
            JSON.stringify({ p: '/message/content/parts/0', o: 'append', v: drift }) +
            '\n\ndata: [DONE]\n\n',
        ),
      ]),
      session,
      pipeline,
      retry,
    )
    console.log('\n[I drift text]')
    console.log(`  attempts=${attempts} reason=${reason} tools=[${res.toolNames()}]`)
    check(attempts === 1, 'I: drift text is retried once')
    check(reason === 'drift-text', 'I: reported as drift-text')
    check(res.toolNames().includes('glob'), 'I: retry work reaches the IDE')
  }

  // J) An unavailable MHI tool split across several SSE deltas must still be
  // reported, not leaked — the close ⟧ only arrives in the last chunk.
  {
    const res = fakeRes()
    const pipeline = new StreamPipeline(res, session, 'chatgpt', 'opencode', messages)
    pipeline.ephemeralMode = false
    pipeline.rawMode = false
    const { chatgptStreamHandler } = require('../providers/chatgpt/stream-handler')
    const block = `${OPEN}errors${SEP}path=/workspaces/zerokey-v2.0${CLOSE}`
    const head = block.slice(0, 30)
    const tail = block.slice(30)
    const evt = (v) =>
      `data: ${JSON.stringify({ p: '/message/content/parts/0', o: 'append', v })}\n\n`
    await chatgptStreamHandler(
      Readable.from([
        Buffer.from(evt(head)),
        Buffer.from(evt(tail)),
        Buffer.from('data: [DONE]\n\n'),
      ]),
      session,
      pipeline,
      null,
    )
    const body = res.body()
    console.log('\n[J split block]')
    console.log(`  raw MHI leaked: ${body.includes('errors' + SEP + 'path=')}`)
    check(!body.includes('errors' + SEP + 'path='), 'J: split block does not leak raw MHI')
    check(/nicht verfügbar/.test(body), 'J: split block is reported as unavailable')
  }

  // K) Handover document instead of work: retried. Shape observed in
  // ses_f0d24ecf8ffeyVk9PdMT42EOEY, where four rounds were spent writing
  // "## Objective / ## Work State / ## Next Move" instead of analysing MAIN.
  {
    const handoff =
      '## Objective\n- Analyse des Repositorys unter `/workspaces/MAIN` fortsetzen.\n\n' +
      '## Important Details\n- Keine Aenderungen durchfuehren.\n\n' +
      '## Work State\n### Completed\n- Top-Level-Struktur geprueft.\n\n' +
      '### Blocked\n- Keine Blocker.\n'
    const { names } = await run('K handoff document', [[handoff], reads], { expectRetry: true })
    check(names.includes('glob') && names.includes('read'), 'K: work delivered after the retry')
  }

  // L) The same read-only round twice: a loop. Retried, because burning upstream
  // requests on an identical discovery round is the failure this guards.
  {
    session._lastToolRound = [...reads]
    const { names } = await run('L duplicate read round', [[...reads], reads], {
      expectRetry: true,
    })
    check(names.includes('glob'), 'L: the loop round is retried and work is delivered')
    delete session._lastToolRound
  }

  // M) A read round followed by the same read round is a loop, but a round that
  // also runs a command is not — the command may legitimately depend on the
  // read, so it must never be suppressed.
  {
    session._lastToolRound = [...reads]
    const withCmd = [...reads, `cmd${SEP}run=git status${SEP}till=30`]
    // withCmd ist bereits die flache Turn-Liste — ein zusaetzliches [] ergibt
    // einen einzigen kommagetrennten Block statt drei.
    const { names, attempts } = await run('M round with a command', [withCmd, reads], {
      expectRetry: false,
    })
    check(attempts === 0, 'M: a round that runs a command is never treated as a loop')
    check(names.length >= 3, 'M: all three calls are delivered')
    delete session._lastToolRound
  }

  // N) A single repeated read is legitimate work and must survive untouched —
  // it is the common "re-read after an edit" shape.
  {
    session._lastToolRound = [`read${SEP}filePath=/workspaces/MAIN/AGENTS.md`]
    const one = [`read${SEP}filePath=/workspaces/MAIN/AGENTS.md`]
    const { attempts } = await run('N single re-read', [one, reads], { expectRetry: false })
    check(attempts === 0, 'N: a single re-read is not a loop')
    delete session._lastToolRound
  }

  // O) Stillstand ueber mehrere Runden. Der Live-Loop war eine Discovery-Runde
  //    dreimal hintereinander; hier laeuft dieselbe Logik ueber drei getrennte
  //    Requests, weil das Gedaechtnis am Session-Objekt haengt.
  {
    session._readMemory = undefined
    session._lastToolRound = undefined
    const r1 = [
      `read${SEP}filePath=/workspaces/MAIN/AGENTS.md`,
      `read${SEP}filePath=/workspaces/MAIN/README.md`,
    ]
    const r2 = [
      `read${SEP}filePath=/workspaces/MAIN/README.md`,
      `read${SEP}filePath=/workspaces/MAIN/infrastructure.md`,
    ]
    const r3 = [
      `read${SEP}filePath=/workspaces/MAIN/AGENTS.md`,
      `read${SEP}filePath=/workspaces/MAIN/README.md`,
    ]

    const a = await run('O1 neue Ziele', [r1], { expectRetry: false })
    check(a.attempts === 0, 'O: erste Runde mit neuen Zielen wird nicht gebremst')
    const b = await run('O2 neues Ziel', [r2], { expectRetry: false })
    check(b.attempts === 0, 'O: eine Runde mit einem neuen Ziel wird nicht gebremst')
    const c = await run('O3 nur bekannte Ziele', [r3, reads], { expectRetry: true })
    check(c.attempts === 1, 'O: die dritte Runde wiederholt nur Bekanntes und wird gebremst')
    delete session._readMemory
    delete session._lastToolRound
  }

  // P) Live belegt in ses_f06959c34ffem62VA5MinVvP4a (2026-10-01): der Agent
  //    behauptete drei Turns hintereinander, keinen Zugriff auf die Maschine zu
  //    haben, und bat um Uploads — obwohl read/glob/bash im selben Request
  //    deklariert waren. Dreimal hintereinander, weil isDriftText das nicht
  //    sieht: das ist keine "was soll ich als Naechstes tun"-Runde.
  {
    const noAccess = OBSERVED_NO_ACCESS_TURN
    const { names } = await runText('P no-access drift', [noAccess, reads], {
      expectRetry: true,
      expectReason: 'no-access',
    })
    check(
      names.includes('glob') && names.includes('read'),
      'P: die Arbeit des Retry erreicht die IDE',
    )
  }

  // Q) Gegenprobe derselben Form: eine echte Antwort ohne Tool-Call ist eine
  //    fertige Antwort und darf nicht gebremst werden.
  {
    const answer =
      'Die Proxy-Kette laeuft in dieser Reihenfolge: Antigravity (9878), ' +
      'glm2api (8001), ZeroKey (7250). Jede Stufe spricht OpenAI-kompatibel.'
    const { attempts } = await runText('Q echte Antwort', [answer], { expectRetry: false })
    check(attempts === 0, 'Q: eine Antwort ohne Tool-Call ist kein Stillstand')
  }

  if (failed) {
    console.error(`\n${failed} check(s) failed`)
    process.exit(1)
  }
  console.log('\nOK: ask guard behaves correctly in all cases')
})()
