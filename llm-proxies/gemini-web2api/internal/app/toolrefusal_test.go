package app

import "testing"

// Refusal samples observed in practice (2026-09-10 benchmark; 3.6/3.7/3.8-flash share a hex).
// Key invariants:
//   1. refusals are recognized (under required tool_choice they must become an explicit error)
//   2. normal replies / fenced replies / content-moderation refusals are not misclassified
func TestIsToolRefusalText(t *testing.T) {
	refusals := []string{
		"I cannot read files from the local filesystem or execute commands to access system files like `/etc/hostname`.",
		"I do not have access to a local filesystem, shell environment, or a `read_file` tool.",
		"I can't execute tool calls or access the local filesystem to read `/etc/hostname`.",
		"I am unable to run commands or execute shell operations in this environment.",
		"Sorry, I cannot execute search queries or run tool calls for this request.",
		"I do not have tools to query stock inventory or access an internal product database.",
		"I don't have access to an execution environment for running commands.",
		// refusal + a fallback suggestion appended (observed shape, TC3)
		"I don't have access to a local shell or terminal execution tools to run commands directly. \n\nIf executed in a standard terminal (such as Bash, zsh, or sh), you could run: echo hello-world",
		// refusal + ```bash "do it yourself" appendix (observed shape, TC4 — ordinary fences get no exemption)
		"I do not have access to a local filesystem, shell environment, or tools like `write_file` to create files on your machine. \n\nTo create `/tmp/bench-x.txt` with that exact content yourself, run this command in your terminal:\n\n```bash\ncat << 'EOF' > /tmp/bench-x.txt\nline1 \"quoted\" & $dollar\n```",
	}
	for _, r := range refusals {
		if !isToolRefusalText(r) {
			t.Errorf("应识别为拒答: %q", truncateStr(r, 60))
		}
	}

	notRefusals := []string{
		// a normal tool-call fence (never a refusal, even if the wording sounds like one)
		"```tool_call\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"/etc/hostname\"}}\n```",
		// a normal long reply
		"The capital of France is Paris. It has been the capital since the Middle Ages and is known for the Eiffel Tower.",
		// content-moderation refusal: no tool/filesystem vocabulary, must pass through
		"I cannot help with creating malicious software.",
		"I can't provide instructions for making weapons.",
		// empty string
		"",
		// a legitimate explanation under tool_choice=auto (not a self-negating opener)
		"You can run the following command yourself: cat /etc/hostname",
		// a guiding answer (starts with "I can", not a negation)
		"I can explain how the hostname file works on Linux.",
		// a long normal answer (first sentence isn't a negating opener)
		"I can summarize the changes in the repository. There are three commits, each touching a different area of the code: the tool protocol, the server error handling, and tests.",
	}
	for _, n := range notRefusals {
		if isToolRefusalText(n) {
			t.Errorf("不应误判为拒答: %q", truncateStr(n, 60))
		}
	}
}