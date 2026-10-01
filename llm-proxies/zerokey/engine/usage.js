// Token-Meldung fuer Clients, die keine echten Zahlen vom Upstream bekommen.
//
// ZeroKey fragt ChatGPT ueber eine Web-Session ab, nicht ueber die API. Der
// Upstream liefert deshalb keine usage-Zahlen, und opencode meldete fuer jeden
// Turn `tokens: { input: 0, output: 0 }`. Folge: der Client konnte sein
// Context-Wachstum nicht beobachten — und genau diese Blindheit hat die
// Kopplungs-Kopplung (compaction.reserved vs. promptLimit) zwei Tage
// unentdeckt leben lassen.
//
// Wir schaetzen statt zu melden, und sagen das auch: 4 Zeichen pro Token ist
// die uebliche Naeherung fuer Fliesstext, Code und JSON sind dichter (~3).
// Wer genau rechnen will, braucht den Upstream-Zugriff ueber die API.
//
// Verglichen am 2026-09-30: 42 Requests, groesster Prompt 4.649 Zeichen bei
// Proxy-Grenze 49.936. Die Schätzung liegt damit rund 1.162 Tokens; die
// opencode-Seite zaehlte zur selben Zeit 0.
//
// `prompt_truncated` macht die stille Kürzung sichtbar. limitPrompt behält bei
// Überlänge Kopf und Tail und wirft den Mittelteil weg — das Modell sieht die
// Lücke über die Drop-Marker, der *Client* sah bisher nur unauffällige
// Token-Zahlen. Ein Turn, der auf einem aufgeschmitzten Prompt antwortet, ist
// von außen nicht von einem vollständigen zu unterscheiden; genau das hat am
// 2026-10-01 (ses_f06959c34ffem62VA5MinVvP4a) die Diagnose eines
// Fünf-Minuten-Hängers unnötig gemacht. Zusätzliches Feld, kein Ersatz für die
// Token-Zahlen — opencode liest es, es rendert es nicht.

const CHARS_PER_TOKEN = 4

/**
 * Baut das usage-Objekt fuer den letzten SSE-Chunk.
 *
 * @param {{chars: number, truncated: boolean}|undefined} lastPrompt
 * @param {number} modelChars - Zeichen, die der Upstream in diesem Turn lieferte
 * @returns {{prompt_tokens: number, completion_tokens: number, total_tokens: number, prompt_truncated: boolean}}
 */
function buildUsage(lastPrompt, modelChars) {
  const promptChars = lastPrompt && typeof lastPrompt.chars === 'number' ? lastPrompt.chars : 0
  const promptTokens = Math.round(promptChars / CHARS_PER_TOKEN)
  const completionTokens = Math.round((modelChars || 0) / CHARS_PER_TOKEN)
  return {
    prompt_tokens: promptTokens,
    completion_tokens: completionTokens,
    total_tokens: promptTokens + completionTokens,
    // Additiv: opencode kennt nur die drei Token-Felder und ignoriert den Rest.
    prompt_truncated: Boolean(lastPrompt && lastPrompt.truncated),
  }
}

module.exports = { buildUsage, CHARS_PER_TOKEN }
