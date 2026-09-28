// Guard against generic "what should I do?" clarifications.
//
// The model occasionally drops out of agent mode and asks a generic question
// instead of continuing — "What change or coding task should I perform in this
// project?", "What should I inspect or change next?", "Was soll ich als Nächstes
// prüfen?". Observed live in session ses_f16212e61ffe5pi3nIZ55LikLL, where it
// ended an otherwise healthy 4-round analysis run.
//
// Emitting that as a tool call blocks the agent on a question popup the user
// never needed to answer. Genuine blockers must survive untouched, so the
// detector below is deliberately narrow: it only matches questions about *the
// task itself*, never about a concrete parameter, path or decision.
//
// Only the English and German phrasings seen in real transcripts are listed.
// A real blocker ("Which port should the server listen on?") matches none of
// them and passes through as before.

// Matches the question, not the whole call.
const GENERIC_PATTERNS = [
  // English
  /\bwhat (change or coding task|coding task|change|task)s?\b/i,
  /\bwhat (change or coding task|coding task|change|task) should i\b/i,
  /\bwhat should i (do|work on|inspect|change|check|look at|fix|start)\b/i,
  /\bwhat would you like me to (do|work on|change|inspect)\b/i,
  /\bwhat do you want me to (do|work on|change|inspect)\b/i,
  /\bplease (provide|give|send|tell me) the (task|instructions|goal)\b/i,
  /\bwhat (issue|bug|problem) should i\b/i,
  /\bwhich (file|module|bug|issue) should i (look at|inspect|fix|start)\b/i,
  /\bis there (anything|any(?:thing)?)\b.{0,40}\bfor me to\b/i,
  // German
  /\bwas soll\b/i,
  /\bwas (möchte|moechte)st?( du)?,? dass ich\b/i,
  /\bwelche (aufgabe|arbeit) soll ich\b/i,
  /\bbitte (schick|sende|schicke) mir\b.{0,40}\b(aufgabe|anweisung)\b/i,
  /\bwas ist (deine|die) aufgabe\b/i,
]

// A question naming a concrete artifact is a real blocker, not drift. Every
// alternative is \b-anchored on BOTH sides: an unanchored `key` matches inside
// "ZeroKey" and would let the most common generic question through.
const CONCRETE =
  /(\/[\w.-]+\/|\b[\w-]+\.[a-z]{1,5}\b|\b(?:ports?|branches?|commits?|schlüssel|passwords?|api[- ]?keys?|keys?)\b)/i

/**
 * True when an `ask` — or a whole assistant turn written as plain text — is a
 * generic "what should I work on" drift rather than a real blocker.
 *
 * @param {string} question - the ask's question text
 * @returns {boolean}
 */
function isGenericAsk(question) {
  if (typeof question !== 'string') return false
  const q = question.trim()
  if (!q) return false
  // Real blockers name a concrete thing to decide about.
  if (CONCRETE.test(q)) return false
  return matchesGenericPattern(q)
}

function matchesGenericPattern(q) {
  return GENERIC_PATTERNS.some((re) => re.test(q))
}

/**
 * True when a turn's text is drift rather than a deliverable.
 *
 * The model does not always reach for ⟦ask⟧ — sometimes it writes the very same
 * clarification as plain text ("I have the context loaded. What would you like
 * me to do with it? I can, for example: …"). That is the same stall, and the
 * ask guard never sees it. Such a turn carries no work, so it can be retried.
 *
 * Unlike isGenericAsk this skips the CONCRETE escape: a drift turn still names
 * the files it just loaded ("the `engine/compiler.js` context is loaded"), and
 * rejecting on a file path would miss exactly the case being handled. What
 * separates it from an answer is shape, not vocabulary — an answer is
 * structured, a drift is a short lead-in plus a menu.
 */
function isDriftText(text) {
  if (typeof text !== 'string') return false
  const t = text.trim()
  if (!t) return false
  if (!matchesGenericPattern(t)) return false
  if (t.length > 1200) return false
  // Deliverables are structured; a clarification is not.
  if (/```|^#{1,6}\s|^\s*\|/m.test(t)) return false
  return true
}

// Appended to the prompt when a wasted turn is retried, so the model continues
// the task instead of stalling. Phrased as an internal note — the model treats
// <internal> as operator context, not as user text.
const NUDGES = {
  'generic-ask': [
    'Your previous turn asked a generic clarifying question instead of continuing.',
    'The task was already given to you and is still in progress — do not ask what to do.',
    'Continue the task now: emit the next MHI directives, or if the task is already',
    'complete, give the final answer. Reserve ⟦ask⟧ for a genuine blocker that no',
    'tool call can resolve.',
  ],
  'empty-turn': [
    'Your previous turn produced no output at all — no tool directives and no text.',
    'Do not end your turn empty. The task is still in progress: continue it now by',
    'emitting the next MHI directives, or, if the task is already complete, give the',
    'final answer in text.',
  ],
  'drift-text': [
    'Your previous turn was a generic clarifying question instead of work.',
    'The task was already given to you and is still in progress — do not ask what to',
    'do, do not offer a menu of options. Continue the task now: emit the next MHI',
    'directives, or if the task is already complete, give the final answer.',
  ],
}

/**
 * Build the retry nudge for a given wasted-turn reason.
 * @param {'generic-ask'|'empty-turn'} reason
 */
function buildNudge(reason) {
  const lines = NUDGES[reason] || NUDGES['empty-turn']
  return ['', '<internal>', ...lines, '</internal>'].join('\n')
}

module.exports = { isGenericAsk, isDriftText, buildNudge }
