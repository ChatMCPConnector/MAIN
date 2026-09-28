/**
 * Serializes ALL incoming requests through this app instance: each request
 * only proceeds past this middleware once the previous one's response has
 * fully finished (or the client disconnected). Requests arriving while one
 * is in flight simply wait their turn — no concurrent handling at all.
 *
 * @returns {import('express').RequestHandler}
 */
function sequentialQueue() {
  let tail = Promise.resolve()

  return (req, res, next) => {
    const run = () =>
      new Promise((resolve) => {
        res.once('finish', resolve)
        res.once('close', resolve)
        next()
      })

    tail = tail.then(run, run)
  }
}

module.exports = { sequentialQueue }
