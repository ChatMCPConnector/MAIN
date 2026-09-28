// Regression test for prompt truncation.
//
// An over-budget prompt used to be cut with prompt.slice(0, limit), which keeps
// the HEAD and throws away the TAIL. The tail holds the newest user request and
// the most recent tool results, so the model lost the turn it was answering and
// fell back to generic "what should I do next?" questions — or returned nothing.
// That is what broke long analysis runs (see session ses_f16591f32ffeNm4APkzAujD4zk).
//
// limitPrompt now trims the MIDDLE: instructions + original task at the front,
// current request + recent results at the back.
//
// Run: node scripts/test-prompt-limit.js
const ToolCompiler = require('../engine/compiler')

// chatgpt's promptLimit minus the 64-char safety margin the constructor applies.
const LIMIT = 50_000 - 64

function compilerFor(provider) {
  const c = new ToolCompiler('opencode', provider)
  return c
}

const compiler = compilerFor('chatgpt')
if (compiler._promptLimit !== LIMIT) {
  console.error(`FAIL: expected chatgpt promptLimit ${LIMIT}, got ${compiler._promptLimit}`)
  process.exit(1)
}

let failed = 0
function check(ok, label) {
  if (!ok) {
    console.error(`FAIL: ${label}`)
    failed++
  } else {
    console.log(`ok: ${label}`)
  }
}

// The compiler logs every prompt decision via console.debug/warn; keep the
// test output readable.
console.debug = () => {}
console.warn = () => {}

const big = (n, ch) => ch.repeat(n)
const marker = '[MIDDLE DROPPED'

// ── 1. Under the limit: byte-identical passthrough, no marker.
{
  const blocks = ['<role>instructions</role>', 'USER: analyse the folder', 'MHI(read): ok']
  const out = compiler.limitPrompt(blocks)
  check(out === blocks.join('\n\n'), 'under-limit prompt passes through unchanged')
  check(!out.includes(marker), 'under-limit prompt gets no drop marker')
}

// ── 2. The original failure: newest user request must survive.
{
  const blocks = [
    '<role>Coding Expert Agent ...</role>',
    'USER: analyse the whole zerokey 2.0 folder',
    'ASSISTANT: ' + big(38000, 'a'),
    'MHI(read): ' + big(67000, 'b'),
    'ASSISTANT: ' + big(33000, 'c'),
    'USER: mach weiter',
  ]
  const out = compiler.limitPrompt(blocks)
  check(out.length <= LIMIT, 'over-limit prompt stays within the limit')
  check(out.includes('USER: mach weiter'), 'newest user request survives (the primary bug)')
  check(out.includes('USER: analyse the whole zerokey 2.0'), 'original task survives in the head')
  check(out.includes('Coding Expert Agent'), 'system instructions survive')
  check(out.includes(marker), 'the drop is announced to the model')
  check(!out.includes(big(38000, 'a')), 'stale middle turns are actually dropped')
  check(
    out.indexOf('Coding Expert Agent') < out.indexOf(marker) &&
      out.indexOf(marker) < out.indexOf('USER: mach weiter'),
    'head -> marker -> tail order is preserved',
  )
}

// ── 3. A single turn larger than the whole budget.
{
  const blocks = ['<role>sys</role>', 'MHI(read): ' + big(200000, 'z'), 'USER: bitte weiter']
  const out = compiler.limitPrompt(blocks)
  check(out.length <= LIMIT, 'one oversized turn does not blow the limit')
  check(out.includes('USER: bitte weiter'), 'newest request survives an oversized sibling')
  check(out.includes('sys'), 'instructions survive an oversized sibling')
}

// ── 4. Two oversized turns.
{
  const out = compiler.limitPrompt([big(60000, 'A'), big(60000, 'B')])
  check(out.length <= LIMIT, 'two oversized turns stay within the limit')
  check(out.includes(big(1000, 'B')), 'tail turn survives')
}

// ── 5. A single block only.
{
  const out = compiler.limitPrompt([big(120000, 'q')])
  check(out.length <= LIMIT, 'single oversized block is clamped')
}

// ── 6. Long-running session: the request must never be lost.
{
  const blocks = ['<role>sys</role>', 'USER: task statement']
  for (let i = 0; i < 98; i++) blocks.push(`MHI(read): result ${i} ${big(900, 'r')}`)
  blocks.push('ASSISTANT: ' + big(20000, 'z'))
  blocks.push(`USER: turn-99 ${big(300, 'q')}`)
  const out = compiler.limitPrompt(blocks)
  check(out.length <= LIMIT, 'long session stays within the limit')
  check(out.includes('USER: task statement'), 'long session keeps the task statement')
  check(out.includes('USER: turn-99'), 'long session keeps the newest request')
  check(!out.includes('result 50 '), 'long session drops the middle')
}

// ── 7. Property: over random conversation shapes the two ends always survive.
{
  let seed = 987654321
  const rnd = () => {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff
    return seed / 0x7fffffff
  }
  const kinds = ['USER', 'ASSISTANT', 'MHI(read)', 'MHI(grep)', 'MHI(cmd)']
  let over = 0
  let lostTail = 0
  let lostHead = 0
  for (let n = 0; n < 2000; n++) {
    const count = 2 + Math.floor(rnd() * 60)
    const blocks = []
    for (let i = 0; i < count; i++) {
      const kind = kinds[Math.floor(rnd() * kinds.length)]
      blocks.push(`${kind}: ${big(Math.floor(Math.pow(rnd(), 3) * 120000), 'w')} #${i}`)
    }
    // Zero-padded so "FINAL-0007" is not a substring of "FINAL-00071".
    const tag = `FINAL-${String(n).padStart(5, '0')}`
    blocks[blocks.length - 1] = `USER: ${tag}`

    const out = compiler.limitPrompt(blocks)
    if (out.length > LIMIT) over++
    if (!out.includes(tag)) lostTail++
    if (!out.includes(blocks[0].slice(0, 30))) lostHead++
  }
  check(over === 0, `2000 random shapes stay within the limit (violations: ${over})`)
  check(lostTail === 0, `2000 random shapes keep the newest request (lost: ${lostTail})`)
  check(lostHead === 0, `2000 random shapes keep the first block (lost: ${lostHead})`)
}

if (failed) {
  console.error(`\n${failed} check(s) failed`)
  process.exit(1)
}
console.log('\nOK: prompt truncation keeps head and tail')
