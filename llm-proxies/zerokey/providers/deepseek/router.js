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

// Zeichen pro Token fuer die prompt_tokens-Schaetzung. 4 ist die gaengige
// Naeherung fuer Deutsch/Codemarken; bewusst pessimistisch gerundet, weil ein
// zu kleiner Wert opencode zu frueh kompaktieren laesst (Last wegwerfen) und
// ein zu grosser erst zu spaet (der Proxy kappt dann selbst).
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
  const usageState = { lastAccumulated: null }
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
      const deepseekStream = await deepseekApi.chatCompletion(
        activeSession.chatSessionId,
        prompt,
        activeSession.parentMessageId,
        thinkingEnabled,
        searchEnabled,
        modelType,
        fileIds,
      )

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
      pipeline.tokenUsage.prompt_tokens = Math.ceil(prompt.length / CHARS_PER_TOKEN)

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
