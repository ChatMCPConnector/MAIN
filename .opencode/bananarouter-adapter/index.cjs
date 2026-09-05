const DEFAULT_ENDPOINT = "https://harmless-camel-846.convex.site/api/chat"

function createBananaRouter(options = {}) {
  const apiKey = (options && options.apiKey) || ""
  const baseURL = (options && options.baseURL) || DEFAULT_ENDPOINT

  function toMessages(prompt) {
    const messages = []
    for (const msg of prompt) {
      let text = ""
      for (const part of msg.content || []) {
        if (part.type === "text") text += part.text
      }
      if (text) messages.push({ role: msg.role, content: text })
    }
    return messages
  }

  async function request(body, signal) {
    const res = await fetch(baseURL, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + apiKey },
      body: JSON.stringify(body),
      signal,
    })
    if (!res.ok) {
      const text = await res.text().catch(() => "")
      throw new Error("BananaRouter HTTP " + res.status + ": " + text.slice(0, 200))
    }
    return res
  }

  async function* sse(body, signal) {
    const res = await request(body, signal)
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ""
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split("\n")
      buf = lines.pop() ?? ""
      for (const line of lines) {
        if (!line.startsWith("data:")) continue
        const payload = line.slice(5).trim()
        if (!payload || payload === "[DONE]") continue
        yield JSON.parse(payload)
      }
    }
  }

  function chatModel(modelId) {
    return {
      specificationVersion: "v3",
      provider: "bananarouter",
      modelId,
      async doGenerate(args) {
        const signal = args.abortSignal
        let text = ""
        let tokens = 0
        for await (const evt of sse(
          { model: modelId, messages: toMessages(args.prompt), thinking: false },
          signal,
        )) {
          if (evt.error) throw new Error(String(evt.error))
          if (evt.content) text += evt.content
          tokens++
        }
        return {
          content: [{ type: "text", text }],
          finishReason: { unified: "stop", raw: "stop" },
          usage: { inputTokens: { total: 0 }, outputTokens: { total: tokens } },
          response: { id: "bananarouter", timestamp: new Date(), modelId },
          warnings: [],
        }
      },
      async doStream(args) {
        const signal = args.abortSignal
        const body = { model: modelId, messages: toMessages(args.prompt), thinking: false }
        const stream = new ReadableStream({
          async start(controller) {
            let textOpen = false
            let reasoningOpen = false
            let tokens = 0
            try {
              controller.enqueue({ type: "stream-start", warnings: [] })
              for await (const evt of sse(body, signal)) {
                if (evt.error) throw new Error(String(evt.error))
                if (evt.reasoning) {
                  if (!reasoningOpen) {
                    controller.enqueue({ type: "reasoning-start", id: "r0" })
                    reasoningOpen = true
                  }
                  controller.enqueue({ type: "reasoning-delta", id: "r0", delta: evt.reasoning })
                }
                if (evt.content) {
                  if (!textOpen) {
                    controller.enqueue({ type: "text-start", id: "t0" })
                    textOpen = true
                  }
                  controller.enqueue({ type: "text-delta", id: "t0", delta: evt.content })
                  tokens++
                }
              }
              if (reasoningOpen) controller.enqueue({ type: "reasoning-end", id: "r0" })
              if (textOpen) controller.enqueue({ type: "text-end", id: "t0" })
              controller.enqueue({
                type: "finish",
                finishReason: { unified: "stop", raw: "stop" },
                usage: { inputTokens: { total: 0 }, outputTokens: { total: tokens } },
              })
            } catch (err) {
              controller.enqueue({ type: "error", error: err })
            } finally {
              controller.close()
            }
          },
        })
        return { stream, request: { body: JSON.stringify(body) }, warnings: [] }
      },
    }
  }

  const makeModel = (id) => chatModel(id)
  return { chat: makeModel, languageModel: makeModel }
}

module.exports = { createBananaRouter }
exports.createBananaRouter = createBananaRouter
