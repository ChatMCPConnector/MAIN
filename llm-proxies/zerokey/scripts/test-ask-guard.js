// Regression test for the generic-ask guard.
//
// The model intermittently answers a turn with nothing but a generic
// "what should I do?" clarification (session ses_f16212e61ffe5pi3nIZ55LikLL).
// Emitted as a tool call, that blocks the agent on a question the user never
// needed to answer. isGenericAsk diverts it; genuine blockers must pass.
//
// Run: node scripts/test-ask-guard.js
const {
  isGenericAsk,
  isDriftText,
  isHandoffText,
  isDuplicateToolRound,
  isStalledReadRound,
  updateReadMemory,
  buildNudge,
} = require('../engine/ask-guard')
const { buildUsage } = require('../engine/usage')

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

  // ── handoff drift ─────────────────────────────────────────────────────────
  // Verbatim shape from ses_f0d24ecf8ffeyVk9PdMT42EOEY, where the model spent
  // four rounds writing handover documents instead of analysing the repo.
  const OBSERVED_HANDOFF = [
    '## Objective\n- Analyse des Repositorys unter `/workspaces/MAIN` strukturiert fortsetzen.\n\n## Important Details\n- Keine Aenderungen, Commits, Pushes oder Loeschungen durchfuehren.\n\n## Work State\n### Completed\n- Top-Level-Struktur mit glob und find geprueft.\n\n### Blocked\n- Keine Blocker.\n',
    '## Objective\n- Analyze the complete repository under `/workspaces/MAIN` in a structured way.\n\n## Important Details\n- User requested tool-driven analysis only.\n\n## Work State\n### Active\n- Repository exploration has not yet started.\n\n## Next Move\n1. Read the root documentation.',
    '## Objective\n- Fortsetzung.\n\n## Relevant Files\n- `/workspaces/MAIN/AGENTS.md`\n- `/workspaces/MAIN/README.md`',
  ]
  for (const [i, text] of OBSERVED_HANDOFF.entries()) {
    check(isHandoffText(text), `observed handover document #${i + 1} is drift`)
    check(!isDriftText(text), `handover #${i + 1} is deliberately NOT plain-text drift`)
  }
  check(
    isHandoffText('## Work State\n### Completed\n- x\n\n### Active\n- y\n'),
    'EN subheadings count too',
  )
  check(
    !isHandoffText('## Objective\n- one heading only is not enough'),
    'one heading is not a handover',
  )
  check(!isHandoffText('The ## Objective was clear.'), 'a heading word in prose is not a handover')
  check(
    !isHandoffText(
      '## Objective\nThe objective is to serve traffic.\n\n## Notes\nPort 7250 is live.',
    ),
    'an answer that happens to use headings is kept',
  )
  check(!isHandoffText(''), 'empty text is not a handover')
  check(!isHandoffText(null), 'null is not a handover')

  // ── duplicate tool rounds ─────────────────────────────────────────────────
  // The discovery round of ses_f0d24ecf8ffeyVk9PdMT42EOEY, three times over,
  // with the cosmetic variation the model used to disguise it.
  const ROUND_A = [
    'ls¦path=/workspaces/MAIN',
    'glob¦path=/workspaces/MAIN¦pattern=*¦max=50',
    'glob¦path=/workspaces/MAIN¦pattern=**/AGENTS.md¦max=20',
    'glob¦path=/workspaces/MAIN¦pattern=**/README.md¦max=20',
    'glob¦path=/workspaces/MAIN¦pattern=**/infrastructure.md¦max=20',
  ]
  const ROUND_B = [
    'ls¦path=/workspaces/MAIN',
    'glob¦path=/workspaces/MAIN¦pattern=*¦max=200',
    'glob¦path=/workspaces/MAIN¦pattern=**/AGENTS.md¦max=20',
    'glob¦path=/workspaces/MAIN¦pattern=**/README.md¦max=20',
    'glob¦path=/workspaces/MAIN¦pattern=**/infrastructure.md¦max=20',
  ]
  const ROUND_C = [
    'ls¦path=/workspaces/MAIN',
    'glob¦path=/workspaces/MAIN¦pattern=*¦max=100',
    'glob¦path=/workspaces/MAIN¦pattern=**/*AGENTS.md¦max=20',
    'glob¦path=/workspaces/MAIN¦pattern=**/*README.md¦max=20',
    'glob¦path=/workspaces/MAIN¦pattern=**/*infrastructure.md¦max=20',
  ]
  check(isDuplicateToolRound(ROUND_B, ROUND_A), 'identical round repeated (only max changed)')
  check(
    isDuplicateToolRound(ROUND_C, ROUND_B),
    'glob patterns **/X.md -> **/*X.md still count as a repeat',
  )
  check(!isDuplicateToolRound(ROUND_A, null), 'first round is never a duplicate')
  check(!isDuplicateToolRound(ROUND_A, []), 'no previous round is never a duplicate')
  check(
    !isDuplicateToolRound(ROUND_A, [
      'ls¦path=/workspaces/MAIN/llm-proxies',
      'glob¦path=/workspaces/MAIN/llm-proxies¦pattern=**/*.js¦max=20',
      'grep¦pattern=acquireSlot¦path=/workspaces/MAIN/llm-proxies',
      'read¦filePath=/workspaces/MAIN/infrastructure.md',
    ]),
    'a genuinely different round is not a duplicate',
  )
  check(
    !isDuplicateToolRound(['read¦filePath=/workspaces/MAIN/AGENTS.md'], ROUND_A),
    'a single re-read is legitimate and must pass',
  )
  check(
    !isDuplicateToolRound([...ROUND_A, 'cmd¦run=git status¦till=30'], ROUND_A),
    'a round that also runs a command is doing work',
  )
  check(
    !isDuplicateToolRound(
      ['write¦filePath=/workspaces/MAIN/x.md¦content=a', 'read¦filePath=/workspaces/MAIN/y.md'],
      ['write¦filePath=/workspaces/MAIN/x.md¦content=a', 'read¦filePath=/workspaces/MAIN/y.md'],
    ),
    'mutating tools are never loop-detected',
  )
  check(
    !isDuplicateToolRound(['glob¦path=/workspaces/MAIN¦pattern=*¦max=50'], ROUND_A),
    'one matching call is not enough (needs 2)',
  )

  // ── stalled read rounds (Verallgemeinerung von duplicate) ─────────────────
  const SEP = '¦'
  const A = `read${SEP}filePath=/workspaces/MAIN/AGENTS.md`
  const B = `read${SEP}filePath=/workspaces/MAIN/README.md`
  const mem = () => ({ reads: new Set(), mutated: false })

  // Reihenfolge wie in der Pipeline: erst pruefen, dann das Gedaechtnis falten.
  // Lauf 1: leere Historie, A und B sind neu -> kein Stillstand, wird gemerkt.
  {
    const m = mem()
    check(!isStalledReadRound([A, B], m.reads, m.mutated), 'neue Ziele sind kein Stillstand')
    const neu = updateReadMemory([A, B], m)
    check(neu, 'erste Runde mit neuen Zielen zaehlt als Fortschritt')
    check(m.reads.size === 2, 'beide Ziele sind jetzt bekannt')
    check(m.mutated === false, 'eine reine Lese-Runde setzt den Mutationsschalter nicht')
  }
  // Lauf 2: exakt dieselben zwei erneut. Das ist bereits der Stillstand — die
  // Ergebnisse stehen seit Lauf 1 im Gespraech. Der beobachtete Live-Loop
  // (dreimal dieselbe Discovery-Runde) wird also beim ZWEITEN Mal gefangen,
  // nicht erst beim dritten.
  {
    const m = mem()
    updateReadMemory([A, B], m)
    check(
      isStalledReadRound([A, B], m.reads, m.mutated),
      'zweite identische Lese-Runde ist der Stillstand',
    )
  }
  // Das wandernde Muster A,B -> B,C -> A,B. Gegenueber der VORRUNDEN-Runde
  // betraegt die Ueberlappung nur 50 % und bleibt damit unter der 60-%-Schwelle;
  // gegenueber der ganzen Session sind alle Ziele aber laengst gelesen. Genau
  // diesen Fall sieht isDuplicateToolRound nicht.
  {
    const C = `read${SEP}filePath=/workspaces/MAIN/infrastructure.md`
    const m = mem()
    updateReadMemory([A, B], m)
    updateReadMemory([B, C], m)
    check(
      !isDuplicateToolRound([A, B], [B, C]),
      'Gegenprobe: Ueberlappungstest sieht A,B nach B,C nicht (50 % < 60 %)',
    )
    check(
      isStalledReadRound([A, B], m.reads, m.mutated),
      'wanderndes A,B -> B,C -> A,B wird als Stillstand erkannt',
    )
  }
  // Nach einem Write ist Wiederlesen echte Arbeit.
  {
    const m = mem()
    updateReadMemory([A, B], m)
    updateReadMemory([`write${SEP}filePath=/x.md${SEP}content=a`], m)
    check(
      !isStalledReadRound([A, B], m.reads, m.mutated),
      'nach einem Write ist erneutes Lesen erlaubt',
    )
    updateReadMemory([A, B], m)
    check(isStalledReadRound([A, B], m.reads, m.mutated), 'aber danach ist es wieder Stillstand')
  }
  // Ein einziges neues Ziel macht die ganze Runde zur Fortschrittsrunde.
  {
    const m = mem()
    updateReadMemory([A, B], m)
    check(
      !isStalledReadRound(
        [A, B, `read${SEP}filePath=/workspaces/MAIN/infra/README.md`],
        m.reads,
        m.mutated,
      ),
      'ein einziges neues Ziel macht die Runde wertvoll',
    )
  }
  // Runden mit gemischten Werkzeugen sind immer Arbeit.
  {
    const m = mem()
    updateReadMemory([A, B], m)
    check(
      !isStalledReadRound([A, B, `grep${SEP}pattern=x${SEP}path=/w`], m.reads, m.mutated),
      'eine Runde mit grep (neues Ziel) ist Arbeit',
    )
  }
  check(!isStalledReadRound([A, B], new Set(), false), 'ohne Historie ist nichts ein Stillstand')
  check(
    !isStalledReadRound([A], mem().reads, false),
    'eine einzelne Lese-Runde ist kein Stillstand',
  )
  check(!isStalledReadRound([A, B], undefined, false), 'fehlende Historie ist kein Stillstand')

  // ── usage ─────────────────────────────────────────────────────────────────
  {
    // 4.649 Zeichen groesster realer Prompt bei 49.936 Grenze (2026-09-30).
    const u = buildUsage({ chars: 4649, truncated: false }, 1200)
    check(u.prompt_tokens === 1162, `prompt_tokens 4649 Zeichen -> 1162 (ist ${u.prompt_tokens})`)
    check(
      u.completion_tokens === 300,
      `completion_tokens 1200 Zeichen -> 300 (ist ${u.completion_tokens})`,
    )
    check(u.total_tokens === u.prompt_tokens + u.completion_tokens, 'total = prompt + completion')
    const leer = buildUsage(undefined, 0)
    check(
      leer.prompt_tokens === 0 && leer.total_tokens === 0,
      'fehlende Kennzahlen ergeben 0, kein NaN',
    )
    check(Number.isFinite(leer.total_tokens), 'keine NaN bei fehlenden Daten')
    const kurz = buildUsage({ chars: 5 }, 0)
    check(kurz.prompt_tokens === 1, '5 Zeichen auf 1 Token gerundet (nicht 0)')
  }

  // ── nudges ────────────────────────────────────────────────────────────────
  for (const reason of [
    'generic-ask',
    'empty-turn',
    'drift-text',
    'handoff-text',
    'duplicate-tools',
    'stalled-reads',
  ]) {
    const n1 = buildNudge(reason)
    check(n1.includes('<internal>') && n1.includes('</internal>'), `${reason} nudge is wrapped`)
    check(!n1.includes('last retry'), `${reason} first attempt has no escalation`)
    const n2 = buildNudge(reason, 2)
    check(n2.includes('last retry'), `${reason} second attempt escalates`)
    check(n2.length > n1.length, `${reason} escalation is longer`)
  }
}

if (failed) {
  console.error(`\n${failed} check(s) failed`)
  process.exit(1)
}
console.log('\nOK: generic asks suppressed, real blockers kept')
