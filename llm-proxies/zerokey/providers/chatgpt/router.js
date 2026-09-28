const express = require('express')

const { StreamPipeline } = require('../../engine/pipeline')
const { buildNudge } = require('../../engine/ask-guard')
const { ChatGPTAPI } = require('./api')
const { chatgptStreamHandler } = require('./stream-handler')
const { acquireSlot } = require('../../utils/rate-limiter')
const { validateMessages } = require('../../utils/route-helpers')
const chatgptApi = new ChatGPTAPI()

async function buildChatGPTRouter(parsedFetch, session, _userData = null) {
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

      // Two turn shapes stop the agent without doing anything: a turn that is
      // nothing but a generic clarification, and a turn that produced no output
      // at all. Both are replayed once with a nudge to continue. Bounded to one
      // retry so a model that keeps drifting cannot loop.
      let retried = false
      const retryWastedTurn = async ({ asks, reason }) => {
        if (retried || pipeline.ephemeralMode || pipeline.rawMode) return false
        retried = true
        console.warn(`[ASK-GUARD] ${reason}, re-prompting to continue:`, asks)

        const next = new StreamPipeline(res, activeSession, 'chatgpt', req.ide, messages)
        next.onFinalChunk = pipeline.onFinalChunk

        await acquireSlot('ChatGPT')
        const retryStream = await chatgptApi.chatCompletion(
          prompt + buildNudge(reason),
          activeSession.chatSessionId,
          activeSession.parentMessageId,
          model,
          attachments,
          thinkingEnabled,
        )
        await chatgptStreamHandler(retryStream, activeSession, next)
        return true
      }

      await chatgptStreamHandler(stream, activeSession, pipeline, retryWastedTurn)
    } catch (error) {
      return pipeline.onError(error)
    }
  })

  return router
}

module.exports = { buildChatGPTRouter }
