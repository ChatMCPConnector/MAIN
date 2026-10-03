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

function turn(usageState, accumulatedLines, promptChars = 0) {
  const parser = parserStub()
  const session = { parentMessageId: null }
  if (usageState) usageState.promptChars = promptChars
  return new Promise((resolve) => {
    streamHandler(sseOf(accumulatedLines), session, parser, () => {}, usageState)
    // Der Handler schreibt asynchron ueber den Stream; nach dem Ende auflösen.
    setImmediate(() => resolve(parser.tokenUsage))
  })
}

;(async () => {
  // 1) Erster Turn einer Session: ehrlich 0, KEINE Gesamtsumme als Output.
  const state = { lastAccumulated: null }
  const t1 = await turn(state, [batch(897)], 2457)
  check(t1.prompt_tokens === 897, 'erster Turn meldet den akkumulierten Stand als Kontext', t1.prompt_tokens)
  check(t1.completion_tokens === 897, 'erster Turn meldet den vollen Stand als Zunahme (kein Vorwert vorhanden)', t1.completion_tokens)

  // 2) Zweiter Turn: echtes Delta gegen den Stand aus Turn 1.
  const t2 = await turn(state, [batch(1726)], 10687)
  check(t2.prompt_tokens === 1726, 'prompt_tokens waechst monoton mit der Conversation', t2.prompt_tokens)
  check(t2.completion_tokens === 829, 'zweiter Turn meldet das Delta 1726-897=829', t2.completion_tokens)
  check(t2.total_tokens === t2.prompt_tokens + t2.completion_tokens, 'total = prompt + completion', t2.total_tokens)

  // 3) Ruecklaufender Akkumulator darf nicht negativ werden.
  const t3 = await turn(state, [batch(10)])
  check(t3.completion_tokens === 0, 'sinkender Akkumulator ergibt 0, nicht negativ', t3.completion_tokens)

  // 4) Ohne usageState (Aufrufer, der den 5. Parameter nicht setzt) darf es
  //    keinen Zustand geben, das Script also nicht werfen.
  let threw = false
  try { await turn(undefined, [batch(500)]) } catch { threw = true }
  check(!threw, 'fehlender usageState wird toleriert (kein Wurf)')

  // 5) Der Kern des Fehlers von 2026-10-03: derselbe Stand in zwei aufeinander
  //    folgenden Requests darf NICHT zweimal als Output gemeldet werden.
  const s2 = { lastAccumulated: null, promptChars: 0 }
  const a = await turn(s2, [batch(900)], 3000)
  const b = await turn(s2, [batch(900)], 3000)
  check(a.completion_tokens === 900 && b.completion_tokens === 0, 'unveraenderter Stand: erster Turn 900, zweiter 0 statt 2x 900', `${a.completion_tokens}/${b.completion_tokens}`)

  // 6) opencode pruned die Historie, DeepSeek haelt den Faden: der Prompt, den
  //    WIR senden, ist viel kleiner als die echte Conversation. Deshalb muss
  //    prompt_tokens dem akkumulierten Stand folgen und waechst.
  const s3 = { lastAccumulated: null, promptChars: 0 }
  const t = []
  for (const acc of [1000, 9000, 40000]) t.push(await turn(s3, [batch(acc)], 4000))
  check(
    t[0].prompt_tokens === 1000 && t[1].prompt_tokens === 9000 && t[2].prompt_tokens === 40000,
    'prompt_tokens folgt dem Conversation-Stand (1000/9000/40000), nicht der Prompt-Laenge',
    t.map((x) => x.prompt_tokens).join('/'),
  )
  check(
    t[0].completion_tokens === 1000 && t[1].completion_tokens === 8000 && t[2].completion_tokens === 31000,
    'completion_tokens ist je Turn das echte Delta (1000/8000/31000)',
    t.map((x) => x.completion_tokens).join('/'),
  )
  check(
    t.every((x) => x.prompt_tokens + x.completion_tokens === x.total_tokens),
    'prompt + completion = total in jedem Turn',
  )
  check(
    t[0].prompt_tokens < t[1].prompt_tokens && t[1].prompt_tokens < t[2].prompt_tokens,
    'prompt_tokens waechst monoton — opencode sieht die Kontextgroesse',
  )
  // 7) Ein winziger Nachschub (800 Zeichen) darf den gemeldeten Kontext nicht
  //    auf ~200 Tokens schrumpfen lassen — genau der Fehler, an dem opencode
  //    855 Tokens sah, wo 30 000 standen.
  const s4 = { lastAccumulated: null, promptChars: 0 }
  await turn(s4, [batch(30000)], 200000)      // erster Turn, gross gesendet
  const klein = await turn(s4, [batch(31000)], 800)  // zweiter Turn, winziger Nachschub
  check(klein.prompt_tokens === 31000, 'kleiner Nachschub schrumpft den Kontext nicht (31000, nicht ~200)', klein.prompt_tokens)
  check(klein.completion_tokens === 1000, 'der Winz-Nachschub kostet 1000, nicht die ganze Conversation', klein.completion_tokens)

  if (failed) {
    console.error(`\n${failed} FAIL`)
    process.exit(1)
  }
  console.log('\nok: alle Token-Meldungs-Pruefungen bestanden')
  process.exit(0)
})()
