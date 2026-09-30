const instructions = require('./instructions')
const SYNTAX = require('./syntax')
const { getIDEMapper } = require('./tool-defs')
const registry = require('../providers/registry')
const { matchMcpTrigger } = require('./triggers')
const { decodeContentParts } = require('../utils/extract-files')
const { TOOLS } = require('./tool-defs')

const BLOCK_SEP = '\n\n'
const DROPPED_MARKER =
  '\n\n[MIDDLE DROPPED: earlier turns exceeded the provider prompt limit — the task above and the most recent turns below are intact]\n\n'
const BLOCK_SQUEEZE_MARKER = '\n…[turn truncated]…\n'
// Fraction of the budget reserved for the head (instructions + original task).
// The remainder belongs to the tail (current request + recent results).
const HEAD_SHARE = 0.35

/**
 * Shorten one oversized turn to `room` chars, keeping its beginning and end.
 * A user message carries the request at its start, so cutting from the front
 * would lose exactly what the model needs to answer.
 */
function squeezeBlock(block, room) {
  const keep = room - BLOCK_SQUEEZE_MARKER.length
  if (keep < 2) return block.slice(0, room)

  const front = Math.ceil(keep * 0.6)
  const back = keep - front
  return (
    block.slice(0, front) +
    BLOCK_SQUEEZE_MARKER +
    (back > 0 ? block.slice(block.length - back) : '')
  )
}

class ToolCompiler {
  static objects = {}

  /**
   * @param {string} ideName - Target IDE name (e.g., 'vscode', 'terax', 'opencode')
   * @param {string} provider
   */
  constructor(ideName, provider = 'chatgpt') {
    const cacheKey = ideName + ':' + provider
    if (ToolCompiler.objects[cacheKey]) {
      return ToolCompiler.objects[cacheKey]
    }

    this.ideName = ideName
    this.provider = provider

    const { tools, user, tool, system, rawUser, reverseMap } = getIDEMapper(ideName)
    this._rawUser = rawUser

    this._reverseMap = reverseMap

    function getGenericToolName(id) {
      const name = id.slice(10)
      return reverseMap[name] || name
    }

    this._promptLimit = (registry.get(provider)?.promptLimit ?? 64_000) - 64

    this.tools = tools
    // Every MHI tool the prompt advertises, regardless of IDE. A tool that
    // exists in the catalogue but has no mapping for this IDE (`errors` is
    // vscode-only) must be reported as unavailable instead of leaking raw
    // ⟦errors¦…⟧ syntax into the answer text.
    this._catalogTools = new Set(Object.keys(TOOLS))
    this._handlers = {
      system: (mes) => system(mes.content),
      agent: (mes) => `AGENT: ${mes.content}`,
      assistant: (mes) => `ASSISTANT: ${mes.content}`,
      internal: (mes) => `<internal>\n${mes.content}\n</internal>`,
      instructions: (mes) => `<instructions>\n${mes.content}\n</instructions>`,
      live_instructions: (mes) => `<live_instructions>\n${mes.content}\n</live_instructions>`,
      user: async (mes, messages, isNewSession) => {
        if (mes.content === '<attachments>') return ''
        if (mes.content.startsWith('<attachment ')) {
          mes.content = '<attachments>' + mes.content
        }

        return user(mes.content, messages, isNewSession)
      },
      tool: async (mes) => {
        const name = getGenericToolName(mes.tool_call_id)
        const output = tool(name, mes.content)

        return `${SYNTAX.NAME}(${name}): ${output}`
      },
    }

    ToolCompiler.objects[cacheKey] = this
  }

  async uploadAndGetMessages(messages, parser, upload = true) {
    console.debug('[MESSAGES]', messages.length)

    let i = messages.length - 1
    for (; i >= 0; i--) if (messages[i].role === 'assistant') break
    i++

    const requestMessages = []
    for (; i < messages.length; i++) {
      const mes = messages[i]
      const files = decodeContentParts(mes.content)
      if (files.length) {
        for (const file of files) {
          if (upload) await parser.upload(file)
        }
        continue
      }

      requestMessages.push(mes)
    }

    return requestMessages
  }

  async uploadAndFormatPrompt(messages, parser) {
    const message = messages[messages.length - 1]

    let skill = null
    if (message?.role === 'user' && this._rawUser) {
      try {
        const raw = this._rawUser(message.content, messages, parser.isNewSession)
        const text = (typeof raw === 'string' ? raw : '').trim().toLowerCase()
        skill = ToolCompiler.matchSkill(text, raw)
        if (skill) {
          console.info('[SKILL]', skill.trigger)
          parser.emitText(`\n**SKILL TRIGGER:** \`${skill.trigger}\`\n`)

          // Passthrough skills (e.g. $browser) don't short-circuit the stream —
          // they register tools into this.tools and inline their grammar into the
          // triggering message, then the request continues to the provider as normal.
          if (skill.passthrough) {
            console.info('[SKILL]', skill.trigger, 'is passthrough!')
            skill.call({ messages, index: messages.length - 1, compilerTools: this.tools, parser })
            skill = null
          }
        }
      } catch (e) {
        console.error('[SKILL] rawUser check failed:', e.message)
      }
    }

    const requestMessages = await this.uploadAndGetMessages(messages, parser)
    const results = []

    for (const mes of requestMessages) {
      const handler = this._handlers[mes.role]
      const result = handler
        ? await handler(mes, messages, parser.isNewSession)
        : `${mes.role.toUpperCase()}: ${mes.content}`

      if (result) results.push(result)
    }

    return { prompt: results.join(BLOCK_SEP), blocks: results, skill }
  }

  async uploadAndFormatPromptForRaw(messages, parser, upload = false) {
    const requestMessages = await this.uploadAndGetMessages(messages, parser, upload)
    const results = []

    for (const mes of requestMessages) {
      const content = typeof mes.content === 'string' ? mes.content : JSON.stringify(mes.content)
      results.push(`${mes.role.toUpperCase()}: ${content}`)
    }

    return { prompt: results.join('\n\n') }
  }

  /**
   * Join prompt blocks into a single string, charging the separator between
   * them against the budget.
   */
  limitPrompt(blocks) {
    const limit = this._promptLimit
    const sep = BLOCK_SEP.length
    const total = blocks.reduce((n, b) => n + b.length, 0) + sep * (blocks.length - 1)

    if (total <= limit) {
      const prompt = blocks.join(BLOCK_SEP)
      this.lastPrompt = {
        chars: prompt.length,
        bytes: Buffer.byteLength(prompt, 'utf8'),
        limit,
        truncated: false,
      }
      console.debug('[PROMPT] FINAL', this.lastPrompt)
      return prompt
    }

    console.warn(`[PROMPT] Final prompt exceeded ${limit} chars: ${total}`)

    // Over-budget prompts are trimmed from the MIDDLE, never the tail.
    //
    // The head carries the system instructions and the original task, the tail
    // carries the current user request and the most recent tool results. Both
    // ends are load-bearing: slicing the tail off makes the model lose the
    // request it is answering (including a literal "continue") and fall back to
    // generic "what should I do next?" questions. Only the stale middle turns
    // are safe to drop.
    const usable = limit - DROPPED_MARKER.length - 2 * sep

    if (blocks.length === 1) {
      const prompt = squeezeBlock(blocks[0], usable)
      console.debug('[PROMPT] FINAL', {
        chars: prompt.length,
        limit,
        truncated: true,
        droppedTurns: 0,
      })
      return prompt
    }

    // Two independent hard budgets. The tail may not eat into the head's share
    // (or vice versa) — with one shared budget the tail wins the race and the
    // original task gets dropped.
    const headCap = Math.max(Math.floor(usable * HEAD_SHARE), 1)
    const tailCap = Math.max(usable - headCap, 1)
    const last = blocks.length - 1

    // Both anchors are mandatory: block 0 carries the system instructions, the
    // last block carries the request being answered. Each is squeezed to its
    // cap if it alone is too big, so it can never be pushed out by a neighbour.
    // Remaining budget then absorbs whole blocks, skipping any that do not fit —
    // a 38 kB assistant blob must not push a one-line "analyse the whole folder"
    // instruction out of the prompt.
    const tail = [
      blocks[last].length > tailCap ? squeezeBlock(blocks[last], tailCap) : blocks[last],
    ]
    let tailUsed = tail[0].length
    for (let j = last - 1; j >= 1; j--) {
      const cost = blocks[j].length + sep
      if (tailUsed + cost > tailCap) continue
      tailUsed += cost
      tail.unshift(blocks[j])
    }

    const tailStart = blocks.length - tail.length
    const head = [blocks[0].length > headCap ? squeezeBlock(blocks[0], headCap) : blocks[0]]
    let headUsed = head[0].length
    for (let i = 1; i < tailStart; i++) {
      const cost = blocks[i].length + sep
      if (headUsed + cost > headCap) continue
      headUsed += cost
      head.push(blocks[i])
    }

    const prompt = [...head, DROPPED_MARKER, ...tail].join(BLOCK_SEP)

    const stats = {
      chars: prompt.length,
      bytes: Buffer.byteLength(prompt, 'utf8'),
      limit,
      truncated: true,
      droppedTurns: tailStart - head.length,
    }
    console.debug('[PROMPT] FINAL', stats)
    this.lastPrompt = stats

    return prompt
  }

  buildPrompt(userPrompt, parser, blocks) {
    const parts = blocks && blocks.length ? [...blocks] : [userPrompt]

    if (
      !parser.haveInstructionsAPI &&
      parser.toolCalling &&
      (parser.isNewSession || !userPrompt.includes('<mhi_list>'))
    ) {
      const { content } = instructions.getFull()
      parts.unshift(content)
    }

    return this.limitPrompt(parts)
  }

  /**
   * Process LLM output string into IDE-specific format
   * @param {string} compactStr - Compact string from LLM
   * @returns {Object} IDE-specific tool call
   */
  compile(compactStr, session) {
    const internal = this.parse(compactStr)
    return this.emit(internal, session)
  }

  /**
   * Parse compact string format into internal JSON structure
   * @param {string} compactStr - Compact string format: "tool¦key=value¦key=value"
   * @returns {Object} Internal representation { tool, params }
   */
  parse(compactStr) {
    console.debug('[TOOL]', compactStr)
    const parts = SYNTAX.splitPayload(compactStr).filter((e) => e)
    const toolName = parts[0]
    const params = {}

    // Get valid parameter keys for this tool
    const toolDef = this.tools[toolName]

    if (!toolDef) {
      throw new Error(`Unknown tool: ${toolName} for IDE: ${this.ideName}`)
    }

    // Dynamic MCP tool — strict key filtering against schema
    if (toolDef && toolDef._passthrough) {
      const validKeys = toolDef._validKeys
      const dropped = []
      for (let i = 1; i < parts.length; i++) {
        const equalIdx = parts[i].indexOf('=')
        if (equalIdx > -1) {
          const key = parts[i].substring(0, equalIdx)
          if (validKeys.size === 0 || validKeys.has(key)) {
            params[key] = this.inferType(parts[i].substring(equalIdx + 1))
          } else {
            dropped.push(key)
          }
        }
      }
      if (dropped.length) {
        console.warn('[DynamicTool] dropped unknown keys:', dropped.join(', '))
      }
      return { tool: toolName, params, _passthrough: true }
    }

    // Collect key-value pairs
    const pairs = []
    for (let i = 1; i < parts.length; i++) {
      const equalIdx = parts[i].indexOf('=')

      if (equalIdx > -1) {
        const key = parts[i].substring(0, equalIdx)

        if (toolDef.keys[key]) {
          const value = parts[i].substring(equalIdx + 1)
          pairs.push({ key, value: this.inferType(value) })
          continue
        }
      }

      // No '=' — this segment is a continuation
      if (pairs.length) {
        pairs[pairs.length - 1].value += `¦${parts[i]}`
      }
    }

    // Get Repeating Tool format
    const repeatableKeys = toolDef.repeatable

    if (repeatableKeys) {
      // Handle repeating pattern
      const groups = []

      // Determine the anchor key: the first key listed in repeatableKeys
      // For multi_edit: 'path' starts a new group; for todo: 'id' starts a new group
      const anchorKey = Object.keys(repeatableKeys)[0]
      let current = null

      for (const pair of pairs) {
        if (!repeatableKeys[pair.key]) continue
        if (pair.key === anchorKey) {
          current = {}
          groups.push(current)
        }
        if (current) current[pair.key] = pair.value
      }

      // Get non-repeating fields (like path for edit)
      for (const pair of pairs) {
        if (!repeatableKeys[pair.key]) {
          params[pair.key] = pair.value
        }
      }

      params.$array = groups.filter((g) => g && Object.keys(g).length > 0)
    } else {
      for (const pair of pairs) params[pair.key] = pair.value
    }

    return { tool: toolName, params }
  }

  /**
   * Merge delta items into session.todos and return full list.
   */
  _mergeTodo(toolName, deltaItems, session) {
    if (!session.todos) session.todos = {}

    for (const item of deltaItems) {
      if (item.id === undefined) continue
      if (toolName === 'todos_set' && !session.todos[item.id]) {
        console.warn('[TODO] Invalid todo id:', item)
        continue
      }
      session.todos[item.id] = Object.assign({}, session.todos[item.id] || {}, item)
    }

    const all = Object.values(session.todos)
    const allDone = all.length > 0 && all.every((t) => t.status === 'done')
    if (allDone) {
      console.info('[TODO] All tasks complete — clearing list')
      session.todos = {}
      return []
    }

    return all
  }

  /**
   * Convert internal JSON to IDE-specific format
   * @param {Object} internalJson - Internal representation { tool, params }
   * @returns {Object} IDE-specific tool call
   */
  emit(internal, session) {
    const toolMapping = this.tools[internal.tool]
    if (!toolMapping) {
      throw new Error(`Unknown tool: ${internal.tool} for IDE: ${this.ideName}`)
    }

    // MCP passthrough tools have no generic->IDE field mapping (schema keys
    // already ARE the real argument names), so forward params as-is.
    if (toolMapping._passthrough) {
      return {
        tool: internal.tool,
        name: toolMapping.tool,
        arguments: { ...internal.params },
      }
    }

    toolMapping.transformer(internal.params)

    // For todoAdd / todo: merge delta into persistent state, emit full merged list
    if (internal.tool === 'todos_add' || internal.tool === 'todos_set') {
      const delta = internal.params.$array || []
      internal.params.$array = this._mergeTodo(internal.tool, delta, session)
    }

    // terax multi_edit split: one call per edit entry
    if (toolMapping.split) {
      const arrayData = internal.params.$array || []
      return arrayData
        .filter((item) => item && Object.keys(item).length > 0)
        .map((item) => {
          const args = Object.assign({}, toolMapping.default)
          for (const [genericField, ideField] of Object.entries(toolMapping.params)) {
            if (item[genericField] !== undefined) {
              args[ideField] = item[genericField]
            }
          }

          toolMapping.transform(args, item)

          return {
            tool: internal.tool,
            name: toolMapping.tool,
            arguments: args,
          }
        })
    }

    const result = {
      tool: internal.tool,
      name: toolMapping.tool,
      arguments: {},
    }

    Object.assign(result.arguments, toolMapping.default)

    // Handle array/repeating fields
    if (toolMapping.array) {
      const arrayData = internal.params.$array || []
      if (Array.isArray(arrayData) && arrayData.length) {
        result.arguments[toolMapping.array.key] = arrayData.map((item) => {
          const mappedItem = {}
          for (const [genericField, ideField] of Object.entries(toolMapping.array.fields)) {
            if (item[genericField] !== undefined) {
              if (typeof ideField === 'object') {
                mappedItem[genericField] = ideField[item[genericField]] || item[genericField]
              } else {
                mappedItem[ideField] = item[genericField]
              }
            }
          }
          return mappedItem
        })
      }
    }

    // Handle simple params
    for (const [genericField, ideField] of Object.entries(toolMapping.params)) {
      if (internal.params[genericField] !== undefined) {
        result.arguments[ideField] = internal.params[genericField]
      }
    }

    toolMapping.transform(result.arguments, internal.params)

    return result
  }

  /**
   * Infer the JavaScript type from a string value
   * @param {string} value - String value to infer type from
   * @returns {*} Inferred typed value
   */
  inferType(value) {
    if (value === 'true') return true
    if (value === 'false') return false
    if (/^-?\d+(?:\.\d+)?$/.test(value)) {
      // integer vs float
      return value.indexOf('.') === -1 ? parseInt(value, 10) : parseFloat(value)
    }
    // JSON array/object — used by MCP passthrough params (e.g. fields, paths, modifiers)
    if (
      (value.startsWith('[') && value.endsWith(']')) ||
      (value.startsWith('{') && value.endsWith('}'))
    ) {
      try {
        return JSON.parse(value)
      } catch {
        // not valid JSON — fall through and treat as a raw string
      }
    }
    return value
  }
}

const { triggers: skills } = require('./triggers')

// Precomputed trigger → skill lookup, built once at module load for O(1) matching.
const skillsByTrigger = new Map()
for (const skill of skills) {
  if (skill.trigger) skillsByTrigger.set(skill.trigger.toLowerCase(), skill)
  if (Array.isArray(skill.aliases)) {
    for (const alias of skill.aliases) skillsByTrigger.set(alias.toLowerCase(), skill)
  }
}

/**
 * Split a remainder string into up to `n` positional args by whitespace.
 * The final arg absorbs the rest of the string (so it may itself contain
 * spaces, e.g. a Windows path with spaces) — only the first n-1 splits
 * are whitespace-delimited.
 *
 * @param {string} str
 * @param {number} n
 * @returns {string[]}
 */
function splitArgs(str, n) {
  const parts = []
  let rest = str.trim()
  for (let i = 0; i < n - 1; i++) {
    const idx = rest.search(/\s+/)
    if (idx === -1) break
    parts.push(rest.slice(0, idx))
    rest = rest.slice(idx).trim()
  }
  if (rest) parts.push(rest)
  return parts
}

/**
 * Find the skill whose leading word matches a known trigger.
 * `text` is the trimmed/lowercased user message (used for the O(1) trigger
 * lookup); `raw` is the original untrimmed/uncased message (used to pull
 * param values with their original casing/path formatting preserved).
 *
 * Trigger param syntax: `$test d:\Project\apigen\` — everything after the
 * trigger word is split positionally into the skill's declared `params`
 * (e.g. `params: ['cwd']`), each substituted for its `#{name}#` placeholder
 * in the skill's template. Skills without a `params` array ignore any
 * trailing text.
 *
 * @param {string} text
 * @param {string} [raw]
 * @returns {object|null}
 */
ToolCompiler.matchSkill = function (text, raw) {
  if (!text) return null

  const spaceIdx = text.indexOf(' ')
  const word = spaceIdx === -1 ? text : text.slice(0, spaceIdx)

  const skill = skillsByTrigger.get(word) || matchMcpTrigger(word)
  if (!skill) return null

  const params = skill.params
  if (!params || !params.length) return skill

  const rawTrimmed = (typeof raw === 'string' ? raw : '').trim()
  const remainder = rawTrimmed.slice(word.length).trim()
  if (!remainder) return skill

  const values = splitArgs(remainder, params.length)

  let template = skill.template
  params.forEach((name, i) => {
    if (values[i] === undefined) return
    const value = values[i].replace(/[\\/]+$/, '')
    template = template.split(`#{${name}}#`).join(value)
  })

  return { ...skill, template }
}

module.exports = ToolCompiler
