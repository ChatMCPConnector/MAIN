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

// ── handoff drift ─────────────────────────────────────────────────────────
//
// Observed live in session ses_f0d24ecf8ffeyVk9PdMT42EOEY (2026-09-30): instead
// of working, the model answered with a task-handover document — literally the
// compaction template opencode itself uses ("## Objective", "## Important
// Details", "## Work State", "### Completed", "## Next Move", "## Relevant
// Files"), in German on round 3 and English on rounds 1 and 4.
//
// It is a stall, not an answer: the run produced 1712 → 2533 → 3635 characters
// of plan and zero repository findings. Cause was a config feedback loop, not
// the model — ZeroKey truncates at 50k chars while opencode believed the model
// had 16k tokens with 15k reserved for compaction, so compaction fired after
// *every* turn and opencode's synthetic "Continue if you have next steps" was
// read by the model as a resume-from-handoff marker.
//
// The template is a compaction artefact, so two or more of these headings in a
// tool-calling turn is a reliable marker. isDriftText deliberately rejects
// headings (a structured text is an answer) — which is exactly why this shape
// slipped past it.
const HANDOFF_HEADINGS = [
  /^#{1,6}\s*objective\b/im,
  /^#{1,6}\s*important details\b/im,
  /^#{1,6}\s*work state\b/im,
  /^#{1,6}\s*(next move|next steps)\b/im,
  /^#{1,6}\s*relevant files\b/im,
  /^#{1,6}\s*(completed|active|blocked|in progress)\b/im,
]

/**
 * True when a turn is a task-handover/compaction document rather than work.
 *
 * @param {string} text - the turn's visible text
 * @returns {boolean}
 */
function isHandoffText(text) {
  if (typeof text !== 'string') return false
  const t = text.trim()
  if (!t) return false
  let hits = 0
  for (const re of HANDOFF_HEADINGS) if (re.test(t)) hits++
  return hits >= 2
}

// ── no-access drift ───────────────────────────────────────────────────────
//
// Observed live in session ses_f06959c34ffem62VA5MinVvP4a (2026-10-01): three
// turns in a row, no tool call at all, each one telling the user it could not
// reach the machine and asking for the files to be uploaded instead.
//
//   "Ich habe keinen Zugriff auf deine lokale Maschine oder dieses Repository
//    in diesem Chat."
//   "Ich habe hier keinen Zugriff auf dein `/workspaces/MAIN`."
//   "kannst du entweder: die relevanten Dateien/Ordner hier hochladen"
//
// It reads like a blocker but is the same stall as the others: the agent *does*
// have read/bash/glob on the user's machine, the tool list is in its request, and
// the turn produced no work. Asking for an upload is not resolvable by any tool
// call — there is no upload tool — so it parks the run until the user answers.
//
// isDriftText cannot see it: none of these are "what should I do next?" turns.
// The distinguishing feature is a claim about capability plus an offer to work
// from pasted content, so that is what is matched here.
const ACCESS_DENY =
  /\b(kein(?:en|em)?\s+zugriff|keine\s+zugriffs?n?rechte?n?\b|nicht\s+zugreifen|kann\s+ich\s+nicht\s+auf)\b/i
const ACCESS_DENY_EN =
  /\b(i\s+(?:do\s+not|don'?t|cannot|can'?t)\s+have\s+access|no\s+access\s+to\s+(?:your|the)\b|unable\s+to\s+access)/i

// A denial scoped to the whole machine/workspace rather than to one artifact.
// "kein Zugriff auf Port 7250" is a real blocker and must not match — the
// difference is the scope word, not the phrasing.
const GENERAL_DENY =
  /\b(?:lokale[nrs]?\s+|deine[rns]?\s+|dieser?\s+)*(maschine|arbeitsverzeichnis|dateisystem|workspace|working\s+directory|repository|repo|ordner|dateien)\b/i
const GENERAL_DENY_EN =
  /\b(?:your|the|this)\s+(?:local\s+)?(machine|filesystem|file\s+system|workspace|working\s+directory|repository|repo|files|folders)\b/i

// "laden Sie die Dateien hoch", "fügen Sie die Inhalte ein", "paste the contents"
const SUPPLY_OFFER =
  /(hoch\s*laden|hochgeladen|hier\s+einf(?:ü|ue)g|hier\s+hoch|stelle\s+die\s+\w+\s+(?:bereit|zur\s+verfügung)|einf(?:ü|ue)gen\s+sie\s+die|kopier(?:e|en)\s+sie\s+den\s+(?:inhalt|code)|upload\s+(?:the|your)|paste\s+(?:the|your|its)\s+(?:contents?|files?|output))/i

/**
 * True when a tool-less turn claims the agent cannot reach the user's machine
 * and offers to work from pasted or uploaded content instead.
 *
 * Like isDriftText this skips the CONCRETE escape: the whole point is that the
 * turn names a path (`/workspaces/MAIN`). What separates it from an answer is
 * shape, not vocabulary — an answer is structured, a capability denial is a
 * short paragraph plus a menu of ways to hand over the files.
 *
 * @param {string} text - the turn's visible text
 * @returns {boolean}
 */
function isNoAccessText(text) {
  if (typeof text !== 'string') return false
  const t = text.trim()
  if (!t) return false
  // A structured text is an answer, not a stall.
  if (/```|^#{1,6}\s|^\s*\|/m.test(t)) return false
  if (t.length > 1600) return false

  const denied = ACCESS_DENY.test(t) || ACCESS_DENY_EN.test(t)
  if (!denied) return false

  // Either the denial is about the machine/workspace as a whole, or it is paired
  // with an explicit offer to take the content from the user instead. A denial
  // about one concrete thing plus no offer is a legitimate blocker.
  const general = GENERAL_DENY.test(t) || GENERAL_DENY_EN.test(t)
  return general || SUPPLY_OFFER.test(t)
}

// ── duplicate tool rounds ─────────────────────────────────────────────────
//
// The same session showed the second failure mode: the discovery round
// (ls + 4 globs + find) was emitted three times in a row, each time with
// cosmetic variation — glob max=50 → max=200 → max=100, "**/AGENTS.md" →
// "**/*AGENTS.md", "find /workspaces/MAIN" → "cd /workspaces/MAIN && find .".
// Twenty upstream requests burned, no ASK-GUARD fired, because every one of
// those turns *did* emit tool calls — the guard only rescues tool-less turns.
//
// Repetition is judged by overlap, not set equality, so cosmetic tweaks do not
// hide it. Only the pure-read tools qualify: a round that also ran bash, wrote
// a file or changed the tree is doing something and must pass through.
const READ_ONLY_TOOLS = new Set(['read', 'ls', 'glob', 'grep', 'view_image'])

// Result caps carry no meaning: re-globbing with max=200 instead of max=50
// returns a superset, but in a session that already holds the max=50 answer the
// repeat is still redundant work.
const CAP_KEYS = /^(max|limit|till|timeout)$/

/**
 * Normalise one raw MHI payload ("glob¦path=/x¦pattern=<star>¦max=50") into a
 * comparable signature, dropping result caps.
 *
 * @param {string} payload
 * @returns {string|null} null when the tool is not pure-read
 */
function toolSignature(payload) {
  const parts = String(payload).split('¦')
  const name = parts[0]
  if (!READ_ONLY_TOOLS.has(name)) return null
  const args = parts
    .slice(1)
    .map((a) => {
      const eq = a.indexOf('=')
      const key = eq === -1 ? a : a.slice(0, eq)
      if (key === 'pattern') {
        // Observed across rounds: glob "**/AGENTS.md" then "**/*AGENTS.md".
        const v = eq === -1 ? a : a.slice(eq + 1)
        return `${key}=${v.replace(/\*\*\/\*/g, '**/')}`
      }
      return a
    })
    .filter((a) => a && !CAP_KEYS.test(a.split('=')[0]))
    .sort()
  return `${name}¦${args.join('¦')}`
}

/**
 * True when a round is a repeat of the previous round's calls — a loop.
 *
 * Requires at least two read-only calls and at least 60% overlap, so a single
 * legitimate re-read is never suppressed.
 *
 * @param {string[]} payloads - this round's raw MHI tool payloads
 * @param {string[]|undefined} previousPayloads - the previous round's
 * @returns {boolean}
 */
function isDuplicateToolRound(payloads, previousPayloads) {
  if (!Array.isArray(previousPayloads) || !previousPayloads.length) return false
  if (!Array.isArray(payloads) || payloads.length < 2) return false

  const sigs = payloads.map(toolSignature)
  // A round that contains anything but pure reads is doing real work.
  if (sigs.some((s) => s === null)) return false

  const prev = new Set(previousPayloads.map(toolSignature).filter(Boolean))
  if (!prev.size) return false
  const overlap = sigs.filter((s) => prev.has(s)).length
  return overlap >= 2 && overlap >= 0.6 * sigs.length
}

/**
 * True when a round reads nothing it has not read before, and nothing has
 * changed since. The generalisation of isDuplicateToolRound: that one needs a
 * recognisable repeat against the *previous* round, this one remembers every
 * read target in the session and catches the wandering variant —
 * A, B, A, B — that no overlap test can see.
 *
 * A re-read right after a write is normal work ("write the file, read it back
 * to check"), so the session remembers whether anything was mutated. Until
 * something is, a pure re-read round is treated as the stall it is.
 *
 * @param {string[]} payloads - this round's raw MHI tool payloads
 * @param {Set<string>|undefined} seenReads - read signatures already used
 * @param {boolean} mutated - did anything get written/run since the last round
 * @returns {boolean}
 */
function isStalledReadRound(payloads, seenReads, mutated) {
  // `instanceof`, not a truthiness check: a Set that made a round trip through
  // users.json comes back as `{}`, which is truthy and has no `.has`. Measured
  // 2026-10-02 — 9 dead turns, all `seenReads.has is not a function`.
  if (!(seenReads instanceof Set) || seenReads.size === 0 || mutated) return false
  if (!Array.isArray(payloads) || payloads.length < 2) return false
  const sigs = payloads.map(toolSignature)
  // Anything but pure reads means real work.
  if (sigs.some((s) => s === null)) return false
  // A round that reaches for even one unseen target is making progress.
  if (sigs.some((s) => !seenReads.has(s))) return false
  return sigs.length >= 2
}

/**
 * Folds a round into the session's read/mutation memory.
 *
 * `memory.mutated` answers one question for the NEXT round: did anything
 * change? A round that wrote, ran a command or edited a file sets it, which is
 * what makes the following re-read legitimate work instead of a stall. A round
 * of pure reads clears it again — nothing happened, so reading the same thing
 * once more is pointless.
 *
 * @param {string[]} payloads - raw MHI tool payloads of the round
 * @param {{reads?: Set<string>, mutated?: boolean}} memory - session-held state
 * @returns {boolean} whether this round opened at least one new read target
 */
function updateReadMemory(payloads, memory) {
  if (!memory) return true
  // Same JSON round trip as in isStalledReadRound: `{}` is truthy, so a plain
  // `memory.reads || …` guard lets it through and dies on the first `.has`.
  const reads = memory.reads instanceof Set ? memory.reads : (memory.reads = new Set())
  const sigs = (payloads || []).map(toolSignature)
  const sawNewRead = sigs.some((s) => s !== null && !reads.has(s))
  for (const s of sigs) if (s !== null) reads.add(s)
  memory.mutated = sigs.some((s) => s === null)
  return sawNewRead
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
  'handoff-text': [
    'Your previous turn was a task-handover summary, not work. Such a summary is',
    'never a deliverable here: do not restate the objective, the work state or a plan.',
    'The task is still running — perform its next step now and emit the MHI directives',
    'for it. Summarise only after the final step is done.',
  ],
  'duplicate-tools': [
    'Your previous turn repeated tool calls that were already made and answered.',
    'Those results are already in the conversation; repeating them changes nothing.',
    'Do not re-issue the same calls — take the next unfinished step of the task',
    'instead, or, if the task is complete, give the final answer.',
  ],
  'stalled-reads': [
    'Your previous turn re-read files you have already read in this session, and',
    'nothing changed since. Those results are already in the conversation.',
    'Do not read them again — take the next unfinished step of the task instead:',
    'work on a part not yet inspected, or, if the task is complete, answer.',
  ],
  'no-access': [
    'Your previous turn said you have no access to the user\'s machine or files.',
    'That is not true here: your request declares tools that run on this machine',
    '— read, glob, grep, bash, write, edit — with the working directory already set.',
    'There is no upload mechanism and nothing to paste; the files are on disk and the',
    'tools read them. Do not ask the user for file contents or claim you cannot see',
    'the repository. Start from the working directory: list it, then read what the',
    'task needs, windowing large files instead of reading them whole.',
  ],
}

/**
 * Build the retry nudge for a given wasted-turn reason.
 *
 * On the second attempt the text is tightened: the model already ignored a
 * neutral reminder once, so the second one states plainly that the turn was
 * wasted and that no further attempt is made.
 *
 * @param {'generic-ask'|'empty-turn'|'drift-text'|'handoff-text'|'duplicate-tools'} reason
 * @param {number} [attempt] - 1 for the first retry, 2 for the last one
 */
function buildNudge(reason, attempt = 1) {
  const lines = NUDGES[reason] || NUDGES['empty-turn']
  const body =
    attempt >= 2
      ? [...lines, 'This is the last retry — a third wasted turn ends the turn as failed.']
      : lines
  return ['', '<internal>', ...body, '</internal>'].join('\n')
}

module.exports = {
  isGenericAsk,
  isDriftText,
  isHandoffText,
  isNoAccessText,
  isDuplicateToolRound,
  isStalledReadRound,
  updateReadMemory,
  buildNudge,
}
