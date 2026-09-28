// Regression test for the generic-ask guard.
//
// The model intermittently answers a turn with nothing but a generic
// "what should I do?" clarification (session ses_f16212e61ffe5pi3nIZ55LikLL).
// Emitted as a tool call, that blocks the agent on a question the user never
// needed to answer. isGenericAsk diverts it; genuine blockers must pass.
//
// Run: node scripts/test-ask-guard.js
const { isGenericAsk, isDriftText } = require('../engine/ask-guard')

console.debug = () => {}
console.warn = () => {}

let failed = 0
function check(ok, label) {
  if (!ok) {
    console.error(`FAIL: ${label}`)
    failed++
  } else {
    console.log(`ok: ${label}`)
  }
}

// ── 1. Every generic ask actually observed in production transcripts.
const OBSERVED_GENERIC = [
  'What change or coding task should I perform in the ZeroKey repository?',
  'What change or coding task should I perform on the provided ZeroKey files?',
  'What coding task should I perform in the ZeroKey repository?',
  'What should I inspect or change next in the repository?',
  'Was soll ich im Repository als Nächstes prüfen?',
  'Was soll am ZeroKey-Projekt als Nächstes geprüft werden?',
  'What would you like me to do with the ZeroKey repo?',
  'Which file should I inspect first?',
  'What bug should I investigate?',
  'Please provide the task you want me to perform.',
  'Was möchtest du, dass ich als Nächstes tue?',
  'Welche Aufgabe soll ich übernehmen?',
]
for (const q of OBSERVED_GENERIC) {
  check(isGenericAsk(q), `suppressed: ${q.slice(0, 58)}`)
}

// ── 2. Real blockers that must survive untouched.
const REAL_BLOCKERS = [
  'Which port should the server listen on?',
  'Soll ich die Datei config/users.json überschreiben?',
  'Die Datei existiert schon — überschreiben oder abbrechen?',
  'Which branch should I push to?',
  'Soll ich den Commit mit gpgsign erstellen?',
  'Bitte sende den Inhalt von $agent, damit ich AGENTS.md lesen kann.',
  'The file /workspaces/MAIN/config.json is malformed — repair or skip?',
  'Soll ich den Commit mit gpgsign erstellen?',
]
for (const q of REAL_BLOCKERS) {
  check(!isGenericAsk(q), `kept as blocker: ${q.slice(0, 58)}`)
}

// ── 3. Edge cases.
check(!isGenericAsk(''), 'empty question is not generic')
check(!isGenericAsk('   '), 'whitespace question is not generic')
check(!isGenericAsk(undefined), 'undefined is not generic')
check(!isGenericAsk(null), 'null is not generic')
check(!isGenericAsk(42), 'non-string is not generic')

// ── 4. Concrete artifacts force the "real blocker" branch, so a phrase that
// would otherwise match must still be kept.
check(
  !isGenericAsk('What should I do with the failing test in utils/parser.js?'),
  'generic phrase plus a concrete path is kept',
)

// ── 5. Drift written as plain text instead of ⟦ask⟧ (observed verbatim in
// session ses_f15f39a88ffeCtxSsoSDzVDhDh).
{
  const observed =
    'I have the `engine/compiler.js` and project architecture context loaded. ' +
    'What would you like me to do with it?\n\n' +
    'I can, for example:\n- review/debug `ToolCompiler`\n- find a bug or regression'
  check(isDriftText(observed), 'observed drift text is detected')

  check(
    isDriftText('What change or coding task should I perform in this project?'),
    'short generic text is drift',
  )

  // Deliverables must never be retried.
  check(
    !isDriftText(
      '# Analyse `/workspaces`\n\n## Übersicht\nDer Bereich besteht aus zwei Projekten.',
    ),
    'a real answer with headings is not drift',
  )
  check(
    !isDriftText('Die Analyse ist fertig. Soll ich das committen?'),
    'a real closing question is not drift',
  )
  check(
    !isDriftText(
      'Ich habe server.js gelesen. Die Route /health gibt 200 zurueck. Soll ich weitermachen?',
    ),
    'findings plus a real question are not drift',
  )
  check(
    !isDriftText('```js\ncode\n```\nWas soll ich als naechstes tun?'),
    'a code block is not drift',
  )
  check(!isDriftText('| a | b |\n|---|---|\nWas soll ich tun?'), 'a table is not drift')
  check(!isDriftText(''), 'empty text is not drift')
  check(!isDriftText(null), 'null is not drift')

  // A long generic-flavoured answer is still a deliverable.
  check(!isDriftText('What should I do? '.repeat(120)), 'overlong text is never drift (length cap)')
}

if (failed) {
  console.error(`\n${failed} check(s) failed`)
  process.exit(1)
}
console.log('\nOK: generic asks suppressed, real blockers kept')
