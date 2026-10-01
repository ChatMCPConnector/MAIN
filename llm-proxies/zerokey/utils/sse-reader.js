const { CONFIG } = require('../config/constants')

const MAX_BUFFER_SIZE = 1024 * 1024 // 1MB cap on single-line buffer growth

/**
 * SSE reader for Web ReadableStream (fetch response body).
 *
 * @param {ReadableStream} stream - fetch().body
 * @param {object} options
 * @param {(parsed: object) => void} options.onData  - called with parsed JSON per data line
 * @param {() => void|Promise<void>}  options.onDone  - called on [DONE] or stream end; awaited
 * @param {(err: Error) => void}     options.onError - called on read error
 * @param {(n: number) => void}     [options.onBytes] - called with byte count per chunk
 * @param {number} [options.idleTimeoutMs] - silence budget per chunk; 0 disables
 *   the watchdog. Defaults to CONFIG.STREAM_IDLE_TIMEOUT_MS.
 */
async function readSSE(stream, { onData, onDone, onError, onBytes, idleTimeoutMs }) {
  const budget = idleTimeoutMs === undefined ? CONFIG.STREAM_IDLE_TIMEOUT_MS : idleTimeoutMs
  let buffer = ''
  let settled = false
  let settlePromise = null

  // ── stall watchdog ───────────────────────────────────────────────────────
  //
  // A read that never settles used to wait for the https.Agent idle timer
  // (300_000 ms) to destroy the socket, which surfaces as an opaque socket
  // error five minutes into a turn that is already dead. The timer below cuts
  // that silence short and names the cause. It is re-armed on every chunk, so
  // a long productive stream is never interrupted — only a truly idle one.
  let idleTimer = null
  let idleReject = null

  const clearIdle = () => {
    if (idleTimer) {
      clearTimeout(idleTimer)
      idleTimer = null
    }
    idleReject = null
  }

  const stallError = () => {
    const seconds = Math.round(budget / 1000)
    return Object.assign(
      new Error(
        `Upstream stalled — no data for ${seconds}s. ` +
          'The connection was idle, not slow; the turn was aborted instead of waiting further.',
      ),
      { code: 'stream_stalled', status: 504, statusCode: 504, idleMs: budget },
    )
  }

  /**
   * Arm the silence budget for the WHATWG branch, where the pending read is
   * raced against a rejection rather than torn down from the timer itself.
   */
  const armIdle = () => {
    clearIdle()
    if (!(budget > 0)) return
    let reject
    const promise = new Promise((_, rej) => {
      reject = rej
    })
    // Observed by the racing read below; this guard only keeps Node from
    // reporting it as unhandled when the read won the race first.
    promise.catch(() => {})
    idleTimer = setTimeout(() => reject(stallError()), budget)
    idleReject = { promise }
  }

  /**
   * Arm the same budget for a Node Readable. Defined per-branch because only
   * the Node branch can tear the stream down from the timer itself.
   */

  /**
   * Race a pending read against the silence budget.
   *
   * @param {Promise<any>} pending - the read to guard
   * @param {() => void} kill - tear the stream down when the budget wins
   */
  const guardIdle = async (pending, kill) => {
    armIdle()
    // `idleReject` is null when the budget is disabled. Racing a non-promise
    // would resolve immediately with it, so the read is awaited bare in that
    // case — a watchdog of 0 must mean "no watchdog", not "no reading".
    const raced = idleReject ? Promise.race([pending, idleReject.promise]) : pending
    try {
      return await raced
    } catch (err) {
      // The read stays pending forever once the stream is torn down; drop it so
      // it can never win a later race.
      kill()
      throw err
    } finally {
      clearIdle()
    }
  }

  // Runs `fn` at most once. The returned promise is memoized so a later caller
  // (e.g. the stream-end path after an earlier [DONE]) still awaits an async
  // onDone instead of racing past it.
  const finishOnce = (fn) => {
    if (settled) return settlePromise
    settled = true
    settlePromise = (async () => {
      try {
        await fn()
      } catch (err) {
        onError(err)
      }
    })()
    return settlePromise
  }

  const processLine = (line) => {
    if (line.startsWith('event:')) return
    if (!line.startsWith('data:')) return

    const dataStr = line.slice(5).trim()
    if (!dataStr) return
    if (dataStr === '[DONE]') {
      // Through finishOnce: guards against a second run when the stream ends,
      // and keeps a throwing async onDone inside the promise chain.
      void finishOnce(onDone)
      return
    }

    let data = dataStr
    try {
      data = JSON.parse(dataStr)
    } catch {
      return
    }

    try {
      onData(data)
    } catch (err) {
      console.error(err)
      onError(err)
    }
  }

  const processChunk = (chunk) => {
    if (onBytes && chunk.length) onBytes(chunk.length)
    buffer += chunk
    if (buffer.length > MAX_BUFFER_SIZE) {
      console.warn('[SSE] ⚠ Buffer exceeded 1MB — dropping line')
      buffer = ''
      return
    }
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      processLine(line)
    }
  }

  const decoder = new TextDecoder()

  // node-fetch returns a Node.js Readable; native fetch returns a WHATWG ReadableStream
  if (typeof stream.getReader === 'function') {
    const reader = stream.getReader()
    try {
      while (true) {
        const { done, value } = await guardIdle(reader.read(), () => {
          void reader.cancel().catch(() => {})
        })
        if (done) break
        processChunk(decoder.decode(value, { stream: true }))
      }
      await finishOnce(onDone)
    } catch (err) {
      await finishOnce(() => onError(err))
    } finally {
      clearIdle()
    }
  } else {
    let streamError = null
    await new Promise((resolve) => {
      let settledHere = false
      const settle = (err) => {
        if (settledHere) return
        settledHere = true
        clearIdle()
        if (err) streamError = err
        resolve()
      }

      // The idle timer settles the read itself. It does not wait for the
      // 'error' event that destroy(err) is supposed to emit, because that event
      // does not always arrive: a Readable.from(asyncGenerator) whose generator
      // is parked on a pending await swallows the error and never emits
      // anything at all. Waiting for it would leave the stall unreported.
      const armIdleDestroy = () => {
        clearIdle()
        if (!(budget > 0)) return
        idleTimer = setTimeout(() => {
          if (settledHere) return
          const err = stallError()
          // Releases the socket; harmless if the stream is already gone.
          try {
            stream.destroy(err)
          } catch {
            /* already destroyed */
          }
          settle(err)
        }, budget)
      }

      stream.on('data', (chunk) => {
        clearIdle()
        processChunk(Buffer.isBuffer(chunk) ? decoder.decode(chunk, { stream: true }) : chunk)
        armIdleDestroy()
      })
      stream.on('end', () => settle())
      stream.on('error', (err) => settle(err))
      armIdleDestroy()
    })
    await finishOnce(streamError ? () => onError(streamError) : onDone)
  }
}

module.exports = { readSSE }
