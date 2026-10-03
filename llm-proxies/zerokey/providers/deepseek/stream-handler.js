const { readSSE } = require('../../utils/sse-reader')
const { LogSaver, serializeError } = require('../../utils/log-saver')

const streamLog = new LogSaver({ name: 'deepseek-error' })

const RETRY_REASONS = {
  'Messages too frequent. Try again later.': true,
  'Server busy, please try again later.': true,
  'A message is being generated, please try again later.': true,
}

/**
 * DeepSeek SSE Stream Handler
 *
 * DeepSeek streams its assistant reply as an ordered list of fragments.
 * Each fragment has a `type`:
 *   - "THINK"    → chain-of-thought / reasoning text
 *   - "RESPONSE" → the user-visible answer
 *
 * Fragment lifecycle (verified against DevTools captures):
 *   1. Initial snapshot:  data: {"v":{"response":{...,"fragments":[{type:"THINK",content:"We"}]}}}
 *   2. Deltas while on a fragment (either shape):
 *        data: {"p":"response/fragments/-1/content","o":"APPEND","v":" need"}
 *        data: {"v":" answer"}
 *      Both target the *current last* fragment, so they must be routed by
 *      the tracked `currentFragmentType`.
 *   3. Thinking finalize marker: data: {"p":"response/fragments/-1/elapsed_secs","o":"SET","v":0.66}
 *   4. Next fragment creation:   data: {"p":"response/fragments","o":"APPEND","v":[{"type":"RESPONSE","content":"Hi"}]}
 *      → switches `currentFragmentType` to the new fragment's type.
 *   5. Done: data: {"p":"response/status","o":"SET","v":"FINISHED"}
 *
 * THINK fragments are emitted as OpenAI-style `reasoning_content` deltas
 * (matching the Qwen handler); RESPONSE fragments go through `parser.scan`
 * so BLOCK tool-calls / raw text pass through the normal pipeline.
 *
 * Other event shapes:
 *   data: {"o":"SET","v":"FINISHED"}         → stream complete (legacy path)
 *   data: {"o":"BATCH","v":[...]}            → token usage
 */
function streamHandler(stream, session, parser, retry, usageState) {
  let cancelled = false
  let finished = false

  // Diagnostics — captured so a silent close can be logged with context.
  let dataCount = 0
  let producedOutput = false
  let lastEventType = null
  let lastError = null
  // MAIN (2026-10-03): letzter kumulierter Token-Stand. Bewusst NICHT hier im
  // Closure, sondern im Router-Session-Objekt uebergeben: DeepSeks Wert ist
  // kumuliert ueber die Conversation, das Delta muss also Turn-Grenzen
  // ueberschreiten. Mit einem reinen Request-closure wurde jeder Turn die
  // Gesamtsumme der Unterhaltung gemeldet (live: 804 724 statt ~2 000).
  const st = usageState || { lastAccumulated: null }

  // Current fragment type: 'THINK' | 'RESPONSE' | null
  let currentFragmentType = null
  // OpenAI-compatible clients open the reasoning channel.
  let hasSentReasoningRole = false
  let outputChars = 0
  let lastBatchAccumulated = null
  let lastStatus = null

  const emitReasoning = (delta) => {
    if (!delta) return
    producedOutput = true
    if (!hasSentReasoningRole) {
      parser.emit({ role: 'assistant', reasoning_content: '' })
      hasSentReasoningRole = true
    }
    parser.emit({ reasoning_content: delta })
  }

  const routeDelta = (text) => {
    if (!text) return
    producedOutput = true
    outputChars += text.length
    if (currentFragmentType === 'THINK') emitReasoning(text)
    else parser.scan(text)
  }

  const applyUsage = (accumulated) => {
    const prev = st.lastAccumulated
    st.lastAccumulated = accumulated
    const zunahme = prev === null || prev === undefined ? accumulated : Math.max(0, accumulated - prev)
    st.lastZunahme = zunahme

    // MAIN (2026-10-03):
    // DeepSeek liefert `accumulated_token_usage` kumuliert ueber die gesamte
    // Conversation. In Multi-Turn-Sessions enthaelt das Delta (`zunahme`) sowohl
    // den Input-Nachschub (z.B. gelesene Dateien) als auch die Modellausgabe.
    // Wuerde zunahme als completion_tokens deklariert, wuerde jede 50-KB-Datei
    // als Modellausgabe gezaehlt (live belegt: 201 210 Output-Tokens in 11 Schritten,
    // Turn 4 meldete 27 693 Output-Tokens fuer das Lesen von infrastructure.md).
    //
    // Wenn Modellausgabe gestreamt wurde (outputChars > 0), schaetzen wir
    // completion_tokens aus der tatsaechlichen Ausgabelaenge (~4 Zeichen/Token).
    // prompt_tokens spiegelt den Kontextstand vor der Antwort wider.
    // Fehlt outputChars (synthetische Tests ohne Textfragmente), faellt es
    // sicher auf das Delta zunahme zurueck.
    const completionTokens = outputChars > 0
      ? Math.max(1, Math.round(outputChars / 4))
      : zunahme
    const promptTokens = Math.max(0, accumulated - (outputChars > 0 ? completionTokens : 0))

    parser.tokenUsage.prompt_tokens = promptTokens
    parser.tokenUsage.completion_tokens = completionTokens
    parser.tokenUsage.total_tokens = promptTokens + completionTokens
    console.debug(
      `[DeepSeek] Tokens: akkumuliert=${accumulated}, prompt=${promptTokens}, completion=${completionTokens} (chars=${outputChars}), delta=${zunahme}, status: ${lastStatus || '-'}`,
    )
  }

  const doRetry = (reason) => {
    cancelled = true
    console.error(`[DeepSeek] Stream error: ${reason}`)
    streamLog.log({
      ts: new Date().toISOString(),
      reason,
      chatSessionId: session.chatSessionId,
      parentMessageId: session.parentMessageId,
      currentFragmentType,
      lastEventType,
      dataCount,
      producedOutput,
      hasSentReasoningRole,
      retryable: !!RETRY_REASONS[reason] && !!retry,
      error: lastError,
    })
    parser.emitText(`\n\n⚠ Stream error: ${reason}\n`)

    if (RETRY_REASONS[reason] && retry) {
      console.debug('[DeepSeek] Retrying...')
      parser.emitText(`Retrying...\n`)
      try {
        stream.destroy()
      } catch {}
      retry()
        .then((newStream) => {
          streamHandler(newStream, session, parser, retry)
        })
        .catch((err) => {
          console.error(`[DeepSeek] Retry failed: ${err.message}`)
          streamLog.log({
            ts: new Date().toISOString(),
            reason: `retry failed — ${err?.message || err}`,
            chatSessionId: session.chatSessionId,
            parentMessageId: session.parentMessageId,
            dataCount,
            producedOutput,
            error: serializeError(err),
          })
          parser.sendFinalChunk()
        })
      return
    }
    parser.sendFinalChunk()
  }

  const onData = (data) => {
    if (cancelled) return
    dataCount++
    lastEventType = data.type || data.o || data.p || typeof data.v

    if (data.type === 'error') {
      lastError = serializeError(data)
      doRetry(data.content)
      return
    }

    if (data.o === 'SET') {
      if (data.v === 'FINISHED') {
        finished = true
      }
      return
    }

    if (data.o === 'BATCH') {
      const usageEntry = data.v?.find((e) => e.p === 'accumulated_token_usage')
      const statusEntry = data.v?.find((e) => e.p === 'quasi_status')
      if (statusEntry) lastStatus = statusEntry.v
      if (usageEntry) {
        lastBatchAccumulated = Number(usageEntry.v) || 0
        applyUsage(lastBatchAccumulated)
      }
      return
    }

    // Initial response snapshot — carries message ids and the first fragment.
    const response = data.v?.response
    if (response) {
      session.parentMessageId = response.message_id
      session.lastUsed = new Date().toISOString()
      const firstFragment = response.fragments?.[0]
      if (firstFragment) {
        currentFragmentType = firstFragment.type || currentFragmentType
        routeDelta(firstFragment.content || '')
      }
      return
    }

    // Fragment APPEND — new fragment created; adopt its type and content.
    if (data.p === 'response/fragments' && data.o === 'APPEND' && Array.isArray(data.v)) {
      const frag = data.v[0]
      if (frag) {
        currentFragmentType = frag.type || currentFragmentType
        routeDelta(frag.content || '')
      }
      return
    }

    // Path-targeted content write to the current (last) fragment.
    if (data.p === 'response/fragments/-1/content') {
      if (typeof data.v === 'string') routeDelta(data.v)
      return
    }

    // Bare delta — belongs to whichever fragment is currently last.
    if (typeof data.v === 'string') {
      routeDelta(data.v)
    }
  }

  const onDone = () => {
    if (cancelled) return
    if (finished) {
      if (lastBatchAccumulated != null) {
        applyUsage(lastBatchAccumulated)
      }
      parser.sendFinalChunk()
      return
    }
    doRetry(
      producedOutput
        ? 'stream closed unexpectedly (partial output)'
        : 'stream closed with no output',
    )
  }

  readSSE(stream, {
    onData,
    onDone,
    onError: (e) =>
      parser.onError(e, {
        source: 'stream',
        finished,
        lastEventType,
        dataCount,
        producedOutput,
        currentFragmentType,
      }),
  })
}

module.exports = { streamHandler }
