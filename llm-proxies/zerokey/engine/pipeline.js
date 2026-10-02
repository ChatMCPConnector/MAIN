const SYNTAX = require('./syntax')
const ToolCompiler = require('./compiler')
const { toOpenAIError } = require('../utils/errors')
const { LogSaver, serializeError } = require('../utils/log-saver')

const routeErrorLog = new LogSaver({ name: 'errors', maxSize: 1024 * 1024 })
const {
  restoreMcpInjections,
  showAvailableMcpTags,
  handleSkill,
  registerAutoMcpServers,
} = require('./triggers')
const { isRealChatSession } = require('../utils/session-classifier')
const { ephemeralSession } = require('../utils/ephemeral-session')
const {
  isGenericAsk,
  isDriftText,
  isHandoffText,
  isNoAccessText,
  isDuplicateToolRound,
  isStalledReadRound,
  updateReadMemory,
} = require('./ask-guard')
const { buildUsage } = require('./usage')

let callCounter = 0

function buildCall(index, tool, funcName, args) {
  callCounter++
  const id = String(callCounter).padStart(4, '0')
  return {
    index,
    id: `call_${id}_${tool}`,
    type: 'function',
    function: {
      name: funcName,
      arguments: JSON.stringify(args),
    },
  }
}

function buildToolDelta(tool_calls) {
  return {
    role: 'assistant',
    content: null,
    tool_calls,
  }
}

const TODO_TOOLS = new Set(['todos_add', 'todos_set'])

/**
 * Compile and emit tool calls, holding back generic `ask` drifts.
 *
 * A generic "what should I do?" clarification blocks the agent on a question
 * the user never needed to answer (see ask-guard.js). It is diverted to
 * `suppressed` instead of being emitted.
 *
 * `suppressed` is null on providers that pass no retry handler: without a
 * retry, dropping an ask-only turn would end the response empty and stop the
 * agent harder than the question did. Those providers keep emitting the ask.
 *
 * @returns {number} how many tool calls were emitted
 */
function emitToolCalls(compiler, session, payloads, emit, suppressed) {
  const compiled = payloads
    .flatMap((payload) => {
      const func = compiler.compile(payload, session)
      if (!func) return []
      return Array.isArray(func) ? func : [func]
    })
    .filter(Boolean)

  const keep = suppressed
    ? compiled.filter((f) => {
        if (f.tool !== 'ask' && f.tool !== 'question') return true
        const question = f.arguments?.question ?? f.arguments?.questions?.[0]?.question
        if (!isGenericAsk(question)) return true
        suppressed.push(question)
        return false
      })
    : compiled

  if (!keep.length) return 0

  const ordered = []
  let todoGroup = []

  for (const f of keep) {
    if (TODO_TOOLS.has(f.tool)) {
      todoGroup.push(f)
    } else {
      if (todoGroup.length) {
        ordered.push(todoGroup.pop())
        todoGroup = []
      }
      ordered.push(f)
    }
  }
  // Flush any remaining todo group at the end.
  if (todoGroup.length) ordered.push(todoGroup.pop())

  const tool_calls = ordered.map((f, i) => buildCall(i, f.tool, f.name, f.arguments))

  if (!tool_calls.length) return 0

  const delta = buildToolDelta(tool_calls)
  console.debug('[TOOL] EMIT', delta.tool_calls)
  emit(delta)

  return tool_calls.length
}

class StreamPipeline {
  static setSSEHeaders(res) {
    res.setHeader('Content-Type', 'text/event-stream')
    res.setHeader('Cache-Control', 'no-cache')
    res.setHeader('Connection', 'keep-alive')
    res.setHeader('Access-Control-Allow-Origin', '*')
  }

  /**
   * @param {import('express').Response} res
   * @param {object} session
   * @param {string} provider - 'deepseek' | 'claude' | 'chatgpt'
   * @param {string} ideName - 'vscode' | 'terax' | 'opencode'
   * @param {Array} [messages] - req.body.messages; when supplied, classifies
   *   this request as a real chat turn vs an ephemeral utility call
   *   (title-gen, tool-optimizer, etc.) via isRealChatSession. Ephemeral
   *   calls get a disposable session clone and rawMode=true (skips
   *   instructions/skill/MCP-tag setup and the block tool-parser — see setup()
   *   and scan()). Omit `messages` to always use the real session (e.g. for
   *   the title-gen short-circuit itself, which is already ephemeral by
   *   construction).
   */
  constructor(res, session, provider, ideName, messages = []) {
    this.compiler = new ToolCompiler(ideName, provider)

    const isReal = isRealChatSession(ideName, messages)

    this.res = res
    this.provider = provider
    this.session = isReal ? session : ephemeralSession(session)

    this.isNewSession = this.session.parentMessageId == null
    this.toolCalling = this.session.toolCalling ?? false
    this.haveInstructionsAPI = false
    this.ephemeralMode = !isReal
    this.rawMode = this.ephemeralMode ? true : !this.toolCalling

    this.inTool = false
    this.toolStartFound = false
    this.buffer = ''
    this.toolBuffers = []
    // Generic "what should I do?" asks held back from the tool-call stream.
    this.suppressedAsks = []
    this._askGuardEnabled = false
    this._toolCallCount = 0
    this._hasVisibleText = false
    this._visibleText = ''
    // Raw MHI payloads of this round, plus the previous round's, for loop
    // detection. Read from the session so it survives across requests.
    this._roundPayloads = []
    this._prevRoundPayloads = this.session?._lastToolRound || null
    // Read targets seen in this session + the "did anything change" latch.
    // Like _lastToolRound this lives on the session, because a new pipeline is
    // built per request while the session outlives it.
    this._readMemory = (this.session &&
      (this.session._readMemory ||= { reads: new Set(), mutated: false })) || {
      reads: new Set(),
      mutated: false,
    }
    // `reads` is a Set, and this object outlives the request on the session —
    // which is persisted as JSON in users.json. JSON.stringify(new Set(['a']))
    // is `{}`, so every reloaded session returned an empty plain object where a
    // Set belongs, and the next tool round died on `reads.has is not a
    // function` inside finishOrRetry. Measured 2026-10-02: 18 dead turns across
    // two days, all of them silent hangs (see onError). Rebuilt on every request
    // rather than only when absent, because the serialized form is
    // unrecoverable — a Set's contents do not survive JSON at all, so "nothing
    // remembered yet" is the only correct state to recover to.
    if (!(this._readMemory.reads instanceof Set)) this._readMemory.reads = new Set()
    this.toolIndex = this.compiler.tools
    this.lastChar = ''
    this._maxToolLen = Math.max(...Object.keys(this.compiler.tools).map((k) => k.length)) + 3

    const chunk = {
      id: `chatcmpl-${Date.now()}${Math.random().toString(36).slice(2, 8)}`,
      object: 'chat.completion.chunk',
      created: Math.floor(Date.now() / 1000),
      model: this.compiler.provider,
      choices: [],
    }

    this.emit = (delta, finishReason = null, usage = null) => {
      chunk.choices = [{ index: 0, delta, finish_reason: finishReason, logprobs: null }]

      if (usage != null) {
        chunk.usage = usage
      }

      res.write(`data: ${JSON.stringify(chunk)}\n\n`)
    }

    this.tokenUsage = {}
    this._modelChars = 0
    this._finished = false

    // bindUploader curries the API's uploadFile — must be set per-request.
    this.bindUploader = (api, collector) => {
      this.upload = (file) => this._uploadFile(api.uploadFile.bind(api), file, collector)
    }
  }

  upload(_file) {}

  // ── public emit methods ────────────────────────────────────────────────
  emit(delta, _finishReason = null, _usage = null) {}

  emitText(content, role = 'assistant') {
    if (content && content.trim()) {
      this._hasVisibleText = true
      if (role === 'assistant') this._visibleText += content
    }
    this.emit({ role, content })
  }

  emitAndEnd(text) {
    this.scan(text)
    this.flush()
    this.emit({}, 'stop', {})
    this.res.write('data: [DONE]\n\n')
    this.res.end()
  }

  sendFinalChunk() {
    if (this._finished) return
    this._finished = true
    this.flush()
    const finishReason = this._toolCallCount > 0 ? 'tool_calls' : 'stop'
    this.emit({}, finishReason, this.tokenUsage)
    this.res.write('data: [DONE]\n\n')
    this.res.end()
    this.session.lastUsed = new Date().toISOString()
    if (this.onFinalChunk) this.onFinalChunk()
  }

  /**
   * Flush, then decide whether this turn was wasted and retry upstream once.
   *
   * Two turn shapes stop the agent without doing anything, both observed live:
   *
   *  - ask-only: the model answered with nothing but a generic clarification.
   *    The ask is held back (ask-guard), so the turn would end empty.
   *  - empty: the model produced neither tool calls nor any visible text —
   *    a turn of pure whitespace. Nothing to suppress, still nothing to do.
   *
   * Three more shapes reach here as plain text rather than as a suppressed ask:
   * a generic clarification written out, a task-handover document, and a claim
   * that the agent has no access to the user's machine.
   *
   * A turn that produced a real answer is never retried: `text` is what makes
   * it a finished turn rather than a wasted one.
   *
   * `retry` receives { asks, reason } and must resolve true if it took over
   * finalization. Suppressed questions are surfaced as plain text otherwise, so
   * nothing is lost silently.
   *
   * @param {(info: {asks: string[], reason: string}) => Promise<boolean>|boolean} [retry]
   */
  async finishOrRetry(retry) {
    if (this._finished) return
    this._finished = true
    // Only guard wasted turns when a retry can rescue them.
    this._askGuardEnabled = Boolean(retry)
    this.flush()

    const askOnly = this.suppressedAsks.length > 0 && this._toolCallCount === 0
    const empty = this._toolCallCount === 0 && !this._hasVisibleText
    // The same clarification, written as plain text instead of ⟦ask⟧.
    const drift =
      this._toolCallCount === 0 && this._hasVisibleText && isDriftText(this._visibleText)
    // A compaction/handover document instead of work — same stall, different shape.
    const handoff =
      this._toolCallCount === 0 && this._hasVisibleText && isHandoffText(this._visibleText)
    // The agent claims it cannot reach the machine and asks for uploads. The
    // tools are in its own request; asking the user for file contents is not
    // something any tool call could resolve. Observed three turns in a row in
    // ses_f06959c34ffem62VA5MinVvP4a (2026-10-01), each one producing no work.
    const noAccess =
      this._toolCallCount === 0 && this._hasVisibleText && isNoAccessText(this._visibleText)
    // Repeating the previous round's calls. This one fires *with* tool calls, so
    // it needs the raw payloads, and it must not consume the single tool-less
    // retry budget: a loop keeps producing calls, a stall never gets this far.
    const duplicate =
      this._toolCallCount > 0 && isDuplicateToolRound(this._roundPayloads, this._prevRoundPayloads)
    // Generalisation of duplicate: every read target in this round was already
    // read earlier and nothing changed since. Catches the wandering A,B,A,B loop
    // that no overlap test can see.
    const stalled =
      this._toolCallCount > 0 &&
      isStalledReadRound(this._roundPayloads, this._readMemory.reads, this._readMemory.mutated)

    if ((askOnly || empty || drift || handoff || noAccess || duplicate || stalled) && retry) {
      const reason = askOnly
        ? 'generic-ask'
        : empty
          ? 'empty-turn'
          : drift
            ? 'drift-text'
            : handoff
              ? 'handoff-text'
              : noAccess
                ? 'no-access'
                : duplicate
                  ? 'duplicate-tools'
                  : 'stalled-reads'
      try {
        console.warn(
          `[ASK-GUARD] ${reason}, re-prompting to continue` +
            (this.suppressedAsks.length ? `: ${this.suppressedAsks.join(' | ')}` : ''),
        )
        if (await retry({ asks: [...this.suppressedAsks], reason })) return
      } catch (err) {
        console.error('[ASK-GUARD] retry failed:', err.message)
      }
    }

    // Only fold an accepted round into the memory: a round we just threw away
    // must not count as work the model already did.
    if (!duplicate && !stalled) {
      updateReadMemory(this._roundPayloads, this._readMemory)
    }

    // Remember this round so the next one can be compared against it. Stored on
    // the session (not the pipeline) because a new pipeline is built per request
    // while the session outlives it.
    if (this._toolCallCount > 0 && !duplicate) {
      this.session._lastToolRound = [...this._roundPayloads]
    }

    if (this.suppressedAsks.length) {
      this.emitText(
        `\n*(Erkennungsfrage übersprungen: ${this.suppressedAsks.join(' | ')} — Aufgabe läuft weiter.)*\n`,
      )
    }

    // Echte usage statt {}: siehe engine/usage.js. Ohne das meldete opencode
    // fuer jeden Turn 0 Tokens und konnte das Context-Wachstum nicht sehen.
    this.emit(
      {},
      this._toolCallCount > 0 ? 'tool_calls' : 'stop',
      buildUsage(this.compiler.lastPrompt, this._modelChars),
    )
    this.res.write('data: [DONE]\n\n')
    this.res.end()
    this.session.lastUsed = new Date().toISOString()
    if (this.onFinalChunk) this.onFinalChunk()
  }

  // ── file upload ────────────────────────────────────────────────────────

  async _uploadFile(uploadFn, file, collector) {
    this.emitText(`\nUploading image...`)
    const result = await uploadFn(file)
    this.emitText(' done.\n')
    collector.push(result)
    return result
  }

  // ── pipeline setup ─────────────────────────────────────────────────────

  /**
   * Shared pipeline: restore MCP injections, format prompt, build prompt,
   * show available MCP tags on new sessions, and handle skills.
   * Returns { prompt } — if a skill was triggered the response is already
   * ended by handleSkill and the caller should return early.
   *
   * When this.rawMode is set (ephemeral/non-real-session calls), all of the
   * above is skipped entirely — no instructions injection, no skill
   * matching, no MCP tag scanning. Just a flat role-tagged prompt built
   * straight from the raw messages.
   *
   * @param {Array}  messages
   * @param {Array}  tools
   * @param {object} req
   * @returns {Promise<{prompt: string, handled: boolean}>}
   */
  async setup(messages, tools, req) {
    if (this.ephemeralMode) {
      console.warn('[SERVER] EPHEMERAL CALL')
      const { prompt } = await this.compiler.uploadAndFormatPromptForRaw(messages, this, false)
      return { prompt, handled: false }
    }

    // DIAGNOSE (2026-09-30): die Annahme, ein Request ohne `tools` sei ein
    // Summarizer, war FALSCH. opencode sendet fuer ZeroKey offenbar keine
    // Werkzeugliste — ZeroKey hat einen eigenen Katalog (tool-defs.js) und
    // braucht sie nicht. Mit dieser Regel lief der normale Turn in den
    // Raw-Modus: keine MHI-Anweisung, der Modelltext war ein Einzeiler,
    // Ende. Deshalb hier KEIN Verhalten, nur eine Messzeile.
    if (process.env.ZEROKEY_DEBUG_TOOLS) {
      console.warn(
        `[DEBUG] tools=${Array.isArray(tools) ? tools.length : typeof tools} ` +
          `toolCalling=${this.toolCalling} raw=${this.rawMode} msgs=${messages.length}`,
      )
    }

    if (this.rawMode) {
      const { prompt } = await this.compiler.uploadAndFormatPromptForRaw(messages, this, true)
      return { prompt, handled: false }
    }

    registerAutoMcpServers(tools, this.session)
    restoreMcpInjections(this.session, this.compiler.tools, tools)

    const { prompt, blocks, skill } = await this.compiler.uploadAndFormatPrompt(messages, this)

    if (skill) {
      handleSkill(skill, req, this)
      return { prompt: '', handled: true }
    }

    if (this.isNewSession) showAvailableMcpTags(tools, this)

    const built = this.compiler.buildPrompt(prompt, this, blocks)

    return { prompt: built, handled: false }
  }

  // ── error handling ─────────────────────────────────────────────────────

  /**
   * Emit an error through the stream in OpenAI-compatible format.
   * @param {Error} error
   */
  onError(error, ctx = {}) {
    const source = ctx.source || 'route'
    // `writableEnded` is the only authoritative "is the response actually
    // closed" signal, and the only one that may gate this method. `_finished`
    // is set at the TOP of finishOrRetry as a re-entrancy guard, long before
    // `res.end()` runs, so every throw between those two points used to look
    // like a finished response: this method returned without closing anything,
    // and the client sat on an open SSE stream until it gave up. Same for
    // `ctx.finished`, which only says the *upstream* finished — not that our
    // response was written. Measured 2026-10-02, 18 turns: `TypeError: reads.has
    // is not a function` right after `[TOOL] EMIT`, no `[DONE]`, nothing logged.
    const responseClosed = this.res.writableEnded === true
    const contentComplete = !!ctx.finished
    const detail = ctx.detail || error?.message || String(error)

    const reason = responseClosed
      ? `post-finalization ${source} error — ${detail}`
      : contentComplete
        ? `post-completion ${source} error — ${detail}`
        : `${source} error — ${detail}`

    routeErrorLog.log({
      ts: new Date().toISOString(),
      provider: this.provider,
      reason,
      chatSessionId: this.session?.chatSessionId,
      parentMessageId: this.session?.parentMessageId,
      model: this.session?.model,
      lastEventType: ctx.lastEventType,
      dataCount: ctx.dataCount,
      producedOutput: ctx.producedOutput,
      currentFragmentType: ctx.currentFragmentType,
      hasSentReasoningRole: ctx.hasSentReasoningRole,
      responseId: ctx.responseId,
      error: serializeError(error),
    })

    if (responseClosed) return

    this._finished = true
    console.error(`[${this.provider}] ${source} error:\n`, error.message)
    const err = toOpenAIError(error, this.provider)
    this.emitAndEnd(`\n\n⚠ ${err.error.message}${err.error.action ? ' ' + err.error.action : ''}\n`)
  }

  // ── block scanning ───────────────────────────────────────────────────────

  scan(text) {
    // Modell-Ausgabe mitzaehlen fuer die usage-Meldung. ZeroKey erhaelt vom
    // Upstream keine Token-Zahlen, deshalb stand in jedem step-finish
    // tokens: 0 — der Client konnte sein Context-Wachstum nicht sehen.
    this._modelChars += text ? text.length : 0
    if (this.rawMode) {
      this.emitText(text)
      return
    }

    this.buffer += text

    while (true) {
      if (this.inTool) {
        const closeIdx = SYNTAX.findClose(this.buffer)
        if (closeIdx === -1) return

        const payload = this.buffer.slice(1, closeIdx)
        this.buffer = this.buffer.slice(closeIdx + 1)

        this.inTool = false
        this.toolStartFound = false

        this.toolBuffers.push(payload)
        continue
      }

      if (this.toolStartFound) {
        const pipeIdx = this.buffer.indexOf(SYNTAX.SEP)
        if (pipeIdx === -1) {
          if (this.buffer.length <= this._maxToolLen) return
          this.emitText(this.buffer)
          this.buffer = ''
          this.toolStartFound = false
          return
        }

        const tool = this.buffer.slice(1, pipeIdx)
        // Catalog tools without an IDE mapping are captured as tool blocks too.
        // Deciding here would require the closing ⟧ to already be in the
        // buffer, and a block split across several SSE deltas would then leak
        // as raw syntax. emitToolCalls reports them instead.
        if (this.toolIndex[tool] || this.compiler._catalogTools?.has(tool)) {
          console.debug('[TOOL]', tool)
          this.inTool = true
          continue
        }

        this.emitText(this.buffer.slice(0, pipeIdx + 1))
        this.buffer = this.buffer.slice(pipeIdx + 1)
        this.toolStartFound = false
        continue
      }

      const startIdx = this.buffer.indexOf(SYNTAX.OPEN)
      if (startIdx === -1) {
        if (this.buffer) this.lastChar = this.buffer[this.buffer.length - 1]
        this.emitText(this.buffer)
        this.buffer = ''
        return
      }

      const charBefore = startIdx > 0 ? this.buffer[startIdx - 1] : this.lastChar
      if (charBefore === '`') {
        this.emitText(this.buffer.slice(0, startIdx + 1))
        this.lastChar = SYNTAX.OPEN
        this.buffer = this.buffer.slice(startIdx + 1)
        continue
      }

      this.emitText(this.buffer.slice(0, startIdx))
      if (startIdx > 0) this.lastChar = this.buffer[startIdx - 1]
      this.buffer = this.buffer.slice(startIdx)
      this.toolStartFound = true
    }
  }

  flush() {
    if (this.inTool) this.scan(SYNTAX.CLOSE)

    // Split out tool blocks that exist in the catalogue but have no mapping for
    // this IDE (`errors` is vscode-only). They are advertised in
    // instructions.md for every IDE, so the model does call them — reporting
    // them is what keeps the raw ⟦errors¦…⟧ syntax out of the answer text.
    const runnable = []
    const unavailable = []
    for (const payload of this.toolBuffers) {
      const name = payload.slice(0, payload.indexOf(SYNTAX.SEP))
      if (name && !this.toolIndex[name] && this.compiler._catalogTools?.has(name)) {
        unavailable.push(name)
        continue
      }
      runnable.push(payload)
    }
    if (unavailable.length) {
      console.debug('[TOOL] unavailable on', this.compiler.ideName, unavailable)
      this.emitText(
        `\n[⟦${unavailable.join('⟧, ⟦')}⟧ ist auf dieser IDE nicht verfügbar — nutze ein anderes Werkzeug]\n`,
      )
    }

    this._roundPayloads = runnable
    this._toolCallCount = emitToolCalls(
      this.compiler,
      this.session,
      runnable,
      this.emit,
      this._askGuardEnabled ? this.suppressedAsks : null,
    )
    // Flushing is final: the payloads are handed over and the buffer is empty.
    // Without this reset a second flush — an error path closing the response
    // after finishOrRetry already flushed it — emits the same tool calls again,
    // and the client runs them twice.
    this.toolBuffers = []

    if (!this.toolStartFound || !this.buffer) return

    this.emitText(this.buffer)
    this.buffer = ''
    this.toolStartFound = false
  }
}

module.exports = { StreamPipeline }
