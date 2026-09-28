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
 */
async function readSSE(stream, { onData, onDone, onError, onBytes }) {
  let buffer = ''
  let settled = false
  let settlePromise = null

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
        const { done, value } = await reader.read()
        if (done) break
        processChunk(decoder.decode(value, { stream: true }))
      }
      await finishOnce(onDone)
    } catch (err) {
      await finishOnce(() => onError(err))
    }
  } else {
    let streamError = null
    await new Promise((resolve) => {
      stream.on('data', (chunk) => {
        processChunk(Buffer.isBuffer(chunk) ? decoder.decode(chunk, { stream: true }) : chunk)
      })
      stream.on('end', () => resolve())
      stream.on('error', (err) => {
        streamError = err
        resolve()
      })
    })
    await finishOnce(streamError ? () => onError(streamError) : onDone)
  }
}

module.exports = { readSSE }
