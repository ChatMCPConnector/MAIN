const express = require('express')

const { StreamPipeline } = require('../../engine/pipeline')
const { buildNudge } = require('../../engine/ask-guard')
const { setAccountCooldown } = require('../../utils/users-file')
const { ChatGPTAPI } = require('./api')
const { chatgptStreamHandler } = require('./stream-handler')
const { acquireSlot } = require('../../utils/rate-limiter')
const { validateMessages } = require('../../utils/route-helpers')
const chatgptApi = new ChatGPTAPI()

async function buildChatGPTRouter(parsedFetch, session, userData = null) {
  console.debug('[ChatGPT] Initializing from parsed capture JSON')
  await chatgptApi.initializeFromJSON(parsedFetch)

  const router = express.Router()

  router.post('/', async (req, res) => {
    const { messages = [], tools, reasoning_effort: reasoningEffort = null } = req.body

    if (!validateMessages(messages, res)) return

    StreamPipeline.setSSEHeaders(res)
    const pipeline = new StreamPipeline(res, session, 'chatgpt', req.ide, messages)
    const activeSession = pipeline.session
    const model = activeSession.model || 'auto'

    const attachments = []
    pipeline.bindUploader(chatgptApi, attachments)

    const { prompt, handled } = await pipeline.setup(messages, tools, req)
    if (handled) return

    if (pipeline.ephemeralMode) {
      pipeline.onFinalChunk = () => {
        if (activeSession.chatSessionId) {
          chatgptApi.deleteSession(activeSession.chatSessionId).catch(() => {})
        }
      }
    }

    await acquireSlot('ChatGPT')

    const thinkingEnabled = Boolean(
      reasoningEffort &&
      !['none', 'fast', '0', 'false'].includes(String(reasoningEffort).toLowerCase()),
    )

    try {
      let stream
      try {
        stream = await chatgptApi.chatCompletion(
          prompt,
          activeSession.chatSessionId,
          activeSession.parentMessageId,
          model,
          attachments,
          thinkingEnabled,
        )
      } catch (err) {
        if (err.message && err.message.includes('404')) {
          console.warn(
            '[ChatGPT] Conversation expired/deleted (404), retrying with fresh conversation...',
          )
          activeSession.chatSessionId = null
          activeSession.parentMessageId = null
          stream = await chatgptApi.chatCompletion(
            prompt,
            null,
            null,
            model,
            attachments,
            thinkingEnabled,
          )
        } else {
          throw err
        }
      }

      // Four turn shapes stop the agent without doing anything: a turn that is
      // nothing but a generic clarification, a turn that produced no output at
      // all, a turn that wrote the clarification (or a handover document) as
      // plain text, and a round that merely repeats the previous round's calls.
      // All four are replayed with a nudge to continue.
      //
      // Two attempts, not one: measured live on 2026-09-30 a single retry fixed
      // 3 of 4 rescued turns, the fourth re-drifted and had no second chance.
      // Bounded at 2 so a model that keeps drifting cannot loop against upstream.
      let attempts = 0
      const retryWastedTurn = async ({ asks, reason }) => {
        if (attempts >= 2 || pipeline.ephemeralMode || pipeline.rawMode) return false
        attempts++
        console.warn(
          `[ASK-GUARD] ${reason} (Versuch ${attempts}/2), re-prompting to continue` +
            (asks && asks.length ? `: ${asks.join(' | ')}` : ''),
        )

        const next = new StreamPipeline(res, activeSession, 'chatgpt', req.ide, messages)
        next.onFinalChunk = pipeline.onFinalChunk
        // The retry gets its own guard, so a turn that stalls again is caught
        // instead of reaching the user as a blocking question. It may only
        // report — the attempt budget above is the loop bound.
        const reReport = () => false

        await acquireSlot('ChatGPT')
        const retryStream = await chatgptApi.chatCompletion(
          prompt + buildNudge(reason, attempts),
          activeSession.chatSessionId,
          activeSession.parentMessageId,
          model,
          attachments,
          thinkingEnabled,
        )
        await chatgptStreamHandler(retryStream, activeSession, next, reReport)
        return true
      }

      await chatgptStreamHandler(stream, activeSession, pipeline, retryWastedTurn)
    } catch (error) {
      // Ein ChatGPT-Stundenlimit (429) muss die Sperre ueber einen Neustart
      // hinweg ueberleben. Der Provider-Cooldown in utils/rate-limiter.js ist
      // fluechtig, users.json war bisher unberuehrt — nach einem Restart lief der
      // naechste Request wieder ins 429 statt zu warten.
      if (error && error.statusCode === 429 && typeof error.cooldownMs === 'number') {
        const ok = setAccountCooldown(userData, 'chatgpt', 'main', error.cooldownMs, error.message)
        console.warn(
          `[users] Stundenlimit bis ${new Date(Date.now() + error.cooldownMs).toISOString()}` +
            (ok ? ' (in users.json gesichert)' : ' (NICHT gesichert — nur im RAM)'),
        )
      }
      return pipeline.onError(error)
    }
  })

  return router
}

module.exports = { buildChatGPTRouter }
