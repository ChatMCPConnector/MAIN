/**
 * Clones a real session into a disposable one for a single request: no
 * chatSessionId/parentMessageId link to the real thread, and any mutation
 * the stream handler makes (chatSessionId, parentMessageId, lastUsed) lands
 * on the clone only — it is never written back to user.sessions, so it is
 * naturally discarded once the request completes.
 *
 * @param {object} session - the real session object
 * @returns {object} a shallow clone safe to mutate per-request
 */
function ephemeralSession(session) {
  return {
    ...session,
    chatSessionId: null,
    parentMessageId: null,
  }
}

module.exports = { ephemeralSession }
