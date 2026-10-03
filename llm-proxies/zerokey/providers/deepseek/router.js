const express = require('express')

const { StreamPipeline } = require('../../engine/pipeline')
const { DeepSeekAPI } = require('./api')
const { getSharedTransport } = require('./browser-transport')
const { streamHandler } = require('./stream-handler')
const { acquireSlot } = require('../../utils/rate-limiter')
const { validateMessages } = require('../../utils/route-helpers')
const { reasoning } = require('./config')

// Transport selection: 'browser' (default) drives the real web UI; 'api' keeps
// the legacy direct-fetch path (PoW headers, cookie jar). Set via env when you
// need to compare or fall back. The transport singleton is resolved lazily
// inside buildDeepSeekRouter so it can be keyed to the selected local username
// (profile dir = temp/profiles/deepseek/<username>/) — never constructed at
// module load.
const TRANSPORT = (process.env.DEEPSEEK_TRANSPORT || 'browser').toLowerCase()

// O(1) reasoning_effort → { think, search } lookup.
// Keys are the exact labels VS Code advertises (utils/sync-ide-config.js).
// MAIN (2026-10-03): unbekannte/fehlende Werte fallen auf reasoning.default
// ('DeepThink') zurueck — upstream fielen sie auf "kein Denken" zurueck, und
// das war messbar der falsche Default (0 Denk-Zeichen). Reihenfolge:
// expliziter Wert → default aus config.js → harte Notfallstufe.
const REASONING_MAP = reasoning.map
const REASONING_FALLBACK =
  REASONING_MAP[reasoning.default] || REASONING_MAP.Off || { think: false, search: false }

// Zeichen pro Token fuer die Groessenordnung des gesendeten Nachschubs. Der
// Wert geht als usageState.promptTokens an den Stream-Handler und dient dort
// als Protokollzeile und als untere Schranke, wenn kein Vorwert existiert. Er
// ist ausdruecklich NICHT die Kontextzahl: ZeroKey sendet den Nachschub, nicht
// die Unterhaltung (siehe stream-handler.js und infrastructure.md). Er steht
// hier und nicht im Handler, weil die Naeherung eine Einstellung ist und der
// Handler sie nur konsumiert.
const CHARS_PER_TOKEN = 4

async function buildDeepSeekRouter(parsedFetch, session, userData) {
  const username = userData?.username
  // MAIN (2026-10-03): DeepSeks `accumulated_token_usage` ist kumuliert ueber die
  // CONVERSATION, nicht pro Turn. Ein Delta nur innerhalb eines Requests (was der
  // Stream-Handler zuerst tat) half nicht: der ERSTE BATCH eines Turn traegt
  // bereits die Gesamtsumme, also meldete jeder Turn die Summe der ganzen
  // Unterhaltung als seinen Output — live belegt: 4 Nachrichten, 804 724
  // "Output"-Tokens in 22 Sekunden. Der Stand muss deshalb ueber Turn-Grenzen
  // gehalten werden. Diese Closure laeuft einmal pro Session (der Router wird
  // beim Start mit der Session gebaut), haelt den Zustand also weder in
  // users.json noch in einem Modul-Singleton.
  const usageState = { lastAccumulated: null, promptTokens: 0 }
  if (TRANSPORT !== 'api' && !username) {
    throw new Error('[Deepseek] userData.username (local key) is required for browser transport')
  }
  const deepseekApi = TRANSPORT === 'api' ? new DeepSeekAPI() : getSharedTransport({ username })

  console.debug('[Deepseek] Initializing from parsed capture JSON')
  await deepseekApi.initializeFromJSON(parsedFetch)

  if (!session) throw new Error('No session provided')

  if (!session.chatSessionId) {
    try {
      session.chatSessionId = await deepseekApi.createChatSession()
      await deepseekApi.warmupSession(session.chatSessionId)
    } catch (error) {
      if (error.code === 'account_suspended' && error.muteUntil != null && userData) {
        userData.waitUntil = Math.ceil(error.muteUntil * 1000)
        userData.waitReason = 'account_suspended'
      }
      throw error
    }
  }

  const router = express.Router()

  router.post('/', async (req, res) => {
    const { messages = [], tools, reasoning_effort: reasoningEffort = null } = req.body
    if (!validateMessages(messages, res)) return

    StreamPipeline.setSSEHeaders(res)
    const pipeline = new StreamPipeline(res, session, 'deepseek', req.ide, messages)

    if (pipeline.ephemeralMode) {
      pipeline.sendFinalChunk()
      return
    }

    const activeSession = pipeline.session

    // MAIN (2026-10-03): Erkennung einer neuen opencode-Session.
    // Wenn in messages[] KEINE einzige Assistant-Nachricht vorkommt, ist dies der
    // erste Turn einer neuen Konversation. Haengt die DeepSeek-Session noch an
    // einem alten Faden (parentMessageId != null), setzen wir chatSessionId,
    // parentMessageId und den Token-Akkumulator zurueck. Dadurch startet jede neue
    // opencode-Session mit einem sauberen DeepSeek-Chat bei 0 Tokens statt alten
    // Kontext (Kontext-Bleed) weiterzuschleppen.
    const hasAssistant = Array.isArray(messages) && messages.some((m) => m && m.role === 'assistant')
    if (!hasAssistant && activeSession.parentMessageId != null) {
      console.debug(
        `[DeepSeek] Neue Session erkannt (keine Assistant-Nachrichten im Prompt, alter Parent: ${activeSession.parentMessageId}) — Konversation wird zurueckgesetzt`,
      )
      activeSession.chatSessionId = null
      activeSession.parentMessageId = null
      usageState.lastAccumulated = null
      pipeline.isNewSession = true
    }

    if (!activeSession.chatSessionId) {
      try {
        activeSession.chatSessionId = await deepseekApi.createChatSession()
        await deepseekApi.warmupSession(activeSession.chatSessionId)
      } catch (error) {
        if (error.code === 'account_suspended' && error.muteUntil && userData) {
          userData.waitUntil = Math.ceil(error.muteUntil * 1000)
          userData.waitReason = 'account_suspended'
        }
        return pipeline.onError(error)
      }
    }
    const modelType = pipeline.isNewSession ? activeSession.model || 'default' : null
    const { think: thinkingEnabled, search: searchEnabled } = REASONING_MAP[reasoningEffort] ?? REASONING_FALLBACK

    const fileIds = []
    pipeline.bindUploader(deepseekApi, fileIds)

    const { prompt, handled } = await pipeline.setup(messages, tools, req)
    if (handled) return

    try {
      await acquireSlot('DeepSeek')
      let deepseekStream
      try {
        deepseekStream = await deepseekApi.chatCompletion(
          activeSession.chatSessionId,
          prompt,
          activeSession.parentMessageId,
          thinkingEnabled,
          searchEnabled,
          modelType,
          fileIds,
        )
      } catch (err) {
        if (err.message && (err.message.includes('invalid chat session id') || err.message.includes('404'))) {
          console.warn('[DeepSeek] Chat-Session abgelaufen oder ungueltig — Wiederholung mit neuer Konversation...')
          activeSession.chatSessionId = await deepseekApi.createChatSession()
          await deepseekApi.warmupSession(activeSession.chatSessionId)
          activeSession.parentMessageId = null
          usageState.lastAccumulated = null
          pipeline.isNewSession = true
          deepseekStream = await deepseekApi.chatCompletion(
            activeSession.chatSessionId,
            prompt,
            null,
            thinkingEnabled,
            searchEnabled,
            modelType,
            fileIds,
          )
        } else {
          throw err
        }
      }

      const retry = async () => {
        await acquireSlot('DeepSeek', true)
        return deepseekApi.chatCompletion(
          activeSession.chatSessionId,
          prompt,
          activeSession.parentMessageId,
          thinkingEnabled,
          searchEnabled,
          modelType,
          fileIds,
        )
      }

      // MAIN (2026-10-03): DeepSeek meldet im SSE nur `accumulated_token_usage`
      // (kumuliert über die Conversation) und **gar keine** Prompt-Token. Der
      // Stream-Handler gab deshalb `prompt_tokens = 0` weiter — opencode hielt
      // damit den GESAMTEN Kontext fuer Ausgabe und kompaktierte nie, waehrend
      // `compiler.limitPrompt` ab 128 000 Zeichen still die Mitte der
      // Unterhaltung wirft (live belegt: opencode meldete in 5 Schritten
      // input=0 / output=2555..9257 und war bei 86 963 von 127 936 Zeichen).
      // Also hier, wo `prompt` vorliegt, eine Schaetzung setzen: ~4 Zeichen pro
      // Token. Das ist eine Naeherung, aber sie ist um eine Groessenordnung
      // besser als 0 — und sie ist die Groesse, die opencode fuer die
      // Kompaktionsentscheidung braucht. Die Hartzahl aus DeepSeks
      // Antwort waere ein Schritt weiter, laesst sich aber nicht erahnen.
      // Weitergereicht an den Stream-Handler als untere Schranke fuer
      // prompt_tokens: das ist die Groesse, die WIR wirklich senden. Weil
      // opencode die Historie pruned und DeepSeek den Faden serverseitig haelt,
      // ist das fuer den Turn viel kleiner als die echte Unterhaltung — der
      // Handler rechnet deshalb mit dem akkumulierten Stand (siehe dort).
      usageState.promptTokens = Math.ceil(prompt.length / CHARS_PER_TOKEN)

      streamHandler(deepseekStream, activeSession, pipeline, retry, usageState)
    } catch (error) {
      if (error.code === 'account_suspended' && error.muteUntil && userData) {
        userData.waitUntil = Math.ceil(error.muteUntil * 1000)
        userData.waitReason = 'account_suspended'
      }
      return pipeline.onError(error)
    }
  })

  return router
}

module.exports = { buildDeepSeekRouter }
