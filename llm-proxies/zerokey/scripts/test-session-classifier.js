// Regression fuer utils/session-classifier.js.
//
// Gefundene Ursache am 2026-09-30: opencode schickt Titel- und Compaction-
// Requests OHNE System-Nachricht (`stream({agent: title, system: [], tools: {},
// messages:[{role:"user", content:"Generate a title for ..."}]})`, belegt aus
// dem Binary 1.18.32). Der Klassifizierer pruefte messages[0].role und wertete
// das als Arbeits-Turn. Folge: der Neben-Request haengt an derselben
// ChatGPT-Konversation wie die echte Arbeit, und der Modellkontext der
// Folgeturns ist mit "Titel erzeugen" verunreinigt. Live: Antwort auf "hey"
// war "Quick check-in" (4 Output-Tokens).
const { isRealChatSession } = require('../utils/session-classifier')

const SYS = 'You are opencode'
const USER = (c) => ({ role: 'user', content: c })

const cases = [
  ['echter Arbeits-Turn', [{ role: 'system', content: SYS }, USER('baue was')], true],
  ['opencode-Titel ohne System', [USER('Generate a title for this conversation.')], false],
  [
    'opencode-Titel mit System',
    [{ role: 'system', content: SYS }, USER('Generate a title for this conversation.')],
    false,
  ],
  ['Compaction "Summarize the conversation"', [USER('Summarize the conversation so far.')], false],
  ['Compaction "condense the history"', [USER('Condense the history into a handover.')], false],
  [
    'Titel-Marker NICHT in der letzten Nachricht',
    [
      { role: 'system', content: SYS },
      USER('Generate a title for this conversation.'),
      USER('weiter'),
    ],
    false,
  ],
  [
    'Arbeitsturn mit Arbeitssystem-Prompt',
    [{ role: 'system', content: SYS }, USER('analysiere /workspaces/MAIN')],
    true,
  ],
  [
    'Arbeitsturn, der das Wort summarize enthaelt',
    [
      { role: 'system', content: SYS },
      USER('Lies die Datei und summarize den Inhalt in Stichpunkten.'),
    ],
    false, // bewusst: lieber eine echte Session als eine faelschliche Vermischung
  ],
  ['leere Liste', [], true],
  ['undefined', undefined, true],
  ['null-Nachricht', [null], true],
  ['System ohne Content', [{ role: 'system' }, USER('mach was')], true],
]

let failed = 0
for (const [name, msgs, wantReal] of cases) {
  let got
  try {
    got = isRealChatSession('opencode', msgs)
  } catch (e) {
    console.log(`FAIL ${name.padEnd(44)} wirft: ${e.message}`)
    failed++
    continue
  }
  const ok = got === wantReal
  if (!ok) failed++
  console.log(
    (ok ? 'ok  ' : 'FAIL') +
      ' ' +
      name.padEnd(44) +
      ` erwartet=${wantReal ? 'real' : 'ephemeral'} ist=${got ? 'real' : 'ephemeral'}`,
  )
}

// Andere IDEs duerfen nicht mitgerissen werden.
const other = isRealChatSession('terax', [
  { role: 'system', content: 'You are Terax, an AI agent' },
  USER('x'),
])
if (!other) {
  console.log('FAIL terax-Arbeitsturn wird als ephemeral eingestuft')
  failed++
} else {
  console.log('ok   terax-Arbeitsturn bleibt real')
}

if (failed) {
  console.error(`\n${failed} check(s) failed`)
  process.exit(1)
}
console.log('\nOK: Neben-Requests von opencode landen nicht in der Arbeits-Konversation')
