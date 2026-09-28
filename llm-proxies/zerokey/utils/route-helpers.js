const { toOpenAIError } = require('./errors')

function validateMessages(messages, res) {
  if (!messages || messages.length === 0) {
    res
      .status(400)
      .json(
        toOpenAIError(
          400,
          'messages is required and must be a non-empty array',
          'invalid_request_error',
          'missing_messages',
        ),
      )
    return false
  }
  return true
}

module.exports = { validateMessages }
