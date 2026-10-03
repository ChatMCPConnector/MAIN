// Regressionstest fuer die Token-Meldung des DeepSeek-Providers.
//
// Zwei Fehler, live gefunden am 2026-10-03 und beide in derselben Datei:
//  1. upstream setzte `parser.tokenUsage.prompt_tokens = 0`. opencode sah damit
//     den Kontext nicht wachsen und kompaktierte nie, waehrend ZeroKeys
//     compiler.limitPrompt ab promptLimit Zeichen die Mitte des Gespraechs
//     wegwirft. Belegt: 5 Schritte mit input=0 / output=2555..9257.
//  2. DeepSeks SSE liefert `accumulated_token_usage` — kumuliert ueber die
//     CONVERSATION, nicht pro Turn. Ein Request-lokales Delta half nicht, weil
//     der ERSTE BATCH eines Turn die Gesamtsumme schon traegt. Belegt: 4
//     Nachrichten mit 804 724 "Output"-Tokens in 22 Sekunden.
//
// Der Zustand liegt deshalb im Router-Session-Closure (usageState), nicht im
// Request-Closure des Handlers. Genau das prueft dieser Test.
//
// Run: node scripts/test-token-usage.js
const { streamHandler } = require('../providers/deepseek/stream-handler')
const { Readable } = require('stream')

console.debug = () => {}
console.warn = () => {}

let failed = 0
function check(ok, label, got) {
  if (ok) console.log(`ok: ${label}`)
  else {
    console.error(`FAIL: ${label}${got !== undefined ? ` (got ${got})` : ''}`)
    failed++
  }
}

// Minimaler Parser: der Handler braucht tokenUsage, scan, emit, emitText,
// sendFinalChunk und onError.
function parserStub() {
  return {
    tokenUsage: {},
    scan() {},
    emit() {},
    emitText() {},
    sendFinalChunk() {},
    onError() {},
  }
}

// SSE-Strom aus einer Liste von data-Zeilen.
function sseOf(lines) {
  return Readable.from([lines.map((l) => `data: ${l}\n\n`).join('')])
}

// BATCH-Ereignis mit accumuliertem Tokenstand.
const batch = (accumulated) =>
  JSON.stringify({ o: 'BATCH', v: [{ p: 'accumulated_token_usage', v: accumulated }] })

function turn(usageState, accumulatedLines) {
  const parser = parserStub()
  const session = { parentMessageId: null }
  return new Promise((resolve) => {
    streamHandler(sseOf(accumulatedLines), session, parser, () => {}, usageState)
    // Der Handler schreibt asynchron ueber den Stream; nach dem Ende auflösen.
    setImmediate(() => resolve(parser.tokenUsage))
  })
}

;(async () => {
  // 1) Erster Turn einer Session: ehrlich 0, KEINE Gesamtsumme als Output.
  const state = { lastAccumulated: null }
  const t1 = await turn(state, [batch(897)])
  check(t1.prompt_tokens === undefined || t1.prompt_tokens === 0, 'erster Turn meldet keinen Prompt von sich aus', t1.prompt_tokens)
  check(t1.completion_tokens === 0, 'erster Turn meldet completion_tokens=0 statt der Gesamtsumme', t1.completion_tokens)

  // 2) Zweiter Turn: echtes Delta gegen den Stand aus Turn 1.
  const t2 = await turn(state, [batch(1726)])
  check(t2.completion_tokens === 829, 'zweiter Turn meldet das Delta 1726-897=829', t2.completion_tokens)
  check(t2.total_tokens === 829 + (t2.prompt_tokens || 0), 'total = completion + prompt', t2.total_tokens)

  // 3) Ruecklaufender Akkumulator darf nicht negativ werden.
  const t3 = await turn(state, [batch(10)])
  check(t3.completion_tokens === 0, 'sinkender Akkumulator ergibt 0, nicht negativ', t3.completion_tokens)

  // 4) Ohne usageState (Aufrufer, der den 5. Parameter nicht setzt) darf es
  //    keinen Zustand geben, das Script also nicht werfen.
  const t4 = await turn(undefined, [batch(500)])
  check(t4.completion_tokens === 0, 'fehlender usageState wird toleriert', t4.completion_tokens)

  // 5) Der Kern des Fehlers von 2026-10-03: derselbe Stand in zwei aufeinander
  //    folgenden Requests darf NICHT zweimal als Output gemeldet werden.
  const s2 = { lastAccumulated: null }
  const a = await turn(s2, [batch(900)])
  const b = await turn(s2, [batch(900)])
  check(a.completion_tokens === 0 && b.completion_tokens === 0, 'unveraenderter Stand meldet zweimal 0, nicht 2x den Stand', `${a.completion_tokens}/${b.completion_tokens}`)

  if (failed) {
    console.error(`\n${failed} FAIL`)
    process.exit(1)
  }
  console.log('\nok: alle Token-Meldungs-Pruefungen bestanden')
  process.exit(0)
})()
