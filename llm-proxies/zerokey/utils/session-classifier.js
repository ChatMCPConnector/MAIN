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
