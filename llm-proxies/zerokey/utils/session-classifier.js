// Known system-prompt prefix each IDE sends on a real conversational turn.
// Fingerprinted from live captures. Anything arriving with a system-first
// message that does NOT start with the matching prefix is not a real chat
// turn — treat it as an ephemeral/utility call (title-gen, tool-optimizer,
// or any other short-lived request not yet individually fingerprinted).
const REAL_SESSION_SIGNATURES = {
  opencode: 'You are opencode',
  terax: 'You are Terax, an AI agent',
  vscode: 'You are an expert AI programming assistant',
}

/**
 * @param {string} ide - req.ide
 * @param {Array} messages - req.body.messages
 * @returns {boolean} true if this looks like a real conversational turn for
 *   the given IDE, false if it should be treated as an ephemeral utility call
 */
function isRealChatSession(ide, messages) {
  // opencode schickt seine Neben-Requests OHNE System-Nachricht. Aus dem
  // Binary (opencode 1.18.32) belegt:
  //   stream({ agent: title, system: [], small: true, tools: {},
  //            messages: [{ role: "user", content: "Generate a title for ..." }] })
  // Die Pruefung auf messages[0].role unten wertet das als Arbeits-Turn, der
  // Titel-Request haengt damit an derselben ChatGPT-Konversation wie die
  // echte Arbeit — und der naechste Turn erbt den Titel-Kontext. Live
  // belegt am 2026-09-30: Antwort auf "hey" war "Quick check-in" (4 Tokens),
  // in aelteren Laeufen "Repository-Analyse: Struktur, LLM-Proxies ...".
  //
  // Deshalb VOR der System-Pruefung und ueber ALLE Nachrichten, nicht nur
  // die letzte: der Titel-Marker steht in der einzigen User-Nachricht.
  if (Array.isArray(messages)) {
    for (const m of messages) {
      if (m && m.role === 'user' && typeof m.content === 'string') {
        if (/generate a title|summari[sz]e|condense the (history|conversation)/i.test(m.content)) {
          return false
        }
      }
    }
  }

  const first = messages && messages[0]
  if (!first || first.role !== 'system' || typeof first.content !== 'string') return true

  // If the last message is purely title generation or summarization, it's ephemeral
  const last = messages[messages.length - 1]
  const lastContent = typeof last?.content === 'string' ? last.content : ''
  if (/generate a title|summarize/i.test(lastContent)) {
    return false
  }

  const sig = REAL_SESSION_SIGNATURES[ide]
  if (sig && first.content.startsWith(sig)) return true

  // For opencode, match custom identities or assistant instructions
  if (ide === 'opencode') {
    return true
  }

  return false
}

module.exports = { isRealChatSession, REAL_SESSION_SIGNATURES }
