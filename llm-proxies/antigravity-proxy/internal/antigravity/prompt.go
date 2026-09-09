package antigravity

import _ "embed"

// SystemInstructionText is the Antigravity CLI-style system instruction sent to
// CloudCode before any client-provided system instructions.
//
//go:embed system_prompt.txt
var SystemInstructionText string
