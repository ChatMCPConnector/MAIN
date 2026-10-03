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

const promptLimit = 128_000

const setupSteps = {
  url: 'https://chat.deepseek.com',
  requestFilter: '/api/v0/chat/completion',
  instructions:
    'Open DevTools → Network tab. Visit chat.deepseek.com and start a conversation. ' +
    'Find a request to /api/v0/chat/completion. Right-click → Copy → Copy as fetch (Node.js).',
}

module.exports = { models, reasoning, promptLimit, setupSteps }
