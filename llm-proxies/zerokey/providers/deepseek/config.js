/**
 * DeepSeek provider configuration.
 * Single source of truth — moved from config/constants.js
 */

const models = {
  title: 'DeepSeek',
  owned_by: 'deepseek',
  models: {
    default: {
      id: 'default',
      name: 'DeepSeek V4.1',
      vision: true,
      created: 1_784_736_000,
      context_length: 1_000_000,
      max_output_length: 384_000,
      defaultReasoning: 'DeepThink',
    },
  },
}

const reasoning = {
  labels: ['Off', 'Search', 'DeepThink', 'DeepThink Search'],
  // MAIN (2026-10-03): upstream kennt kein `default` — ohne reasoning_effort im
  // Request fiel der Router auf {think:false, search:false} zurueck, es wurde
  // also gar nicht gedacht. Gemessen an der laufenden Proxy-Instanz:
  //   Off / Search                -> 0 Denk-Zeichen,     7-8 SSE-Events
  //   DeepThink / DeepThinkSearch -> 73-4895 Zeichen,  112-1173 Events
  // `Search` allein erzeugt nachweislich KEIN Denken (im Stream identisch zu
  // Off) und ist damit als Default die schlechteste Wahl. `think` und `search`
  // sind zwei unabhaengige Flags, keine Stufenleiter — deshalb bleibt das Label
  // erhalten und nur der Default wandert. Ausdruecklich senden kann man Off
  // weiterhin, der Fallback greift nur bei fehlendem/unbekanntem Wert.
  default: 'DeepThink',
  map: {
    Off: { think: false, search: false },
    Search: { think: false, search: true },
    DeepThink: { think: true, search: false },
    'DeepThink Search': { think: true, search: true },
  },
}

// MAIN (2026-10-03): Upstream stand hier 128_000. Das ist KEINE Modellgrenze —
// DeepSeek V4.1 hat 1M Token Context — sondern ein konservativer Wert, der den
// Proxy ~8x unter der Moeglichkeit deckelt. Durchgemessen ueber den Browser-
// Transport (der im Betrieb default ist), jeweils ungekuerzt, Antwort FERTIG:
//   150 000 Zeichen  (~37k Tokens)   OK   8,8 s
//   1 000 000 Zeichen (~250k Tokens)  OK  23,7 s
//   2 000 000 Zeichen (~500k Tokens)  OK  20,2 s
//   3 000 000 Zeichen (~750k Tokens)  FEHLER: "unexpected error occurred with
//                                     deepseek" (HTTP 200, Fehler im Stream)
// Also: 2M Zeichen ist der gemessene sichere Wert, ~500k Tokens. Die vollen
// 1M Tokens sind ueber den Web-Pfad nicht erreichbar, egal was die Modellkarte
// sagt. `check-proxy-budget.py` prueft die Kopplung gegen DIE Zahl.
const promptLimit = 2_000_000

const setupSteps = {
  url: 'https://chat.deepseek.com',
  requestFilter: '/api/v0/chat/completion',
  instructions:
    'Open DevTools → Network tab. Visit chat.deepseek.com and start a conversation. ' +
    'Find a request to /api/v0/chat/completion. Right-click → Copy → Copy as fetch (Node.js).',
}

module.exports = { models, reasoning, promptLimit, setupSteps }
