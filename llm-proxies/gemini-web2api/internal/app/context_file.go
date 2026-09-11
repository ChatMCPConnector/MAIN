package app

import (
	"fmt"
	"strings"
)

// Oversized conversations converted into a text attachment.
//
// The upstream caps a single request at about 130,000 UTF-8 bytes; beyond
// that it silently truncates from the tail without an error — and the
// latest message is assembled at the end, so what gets eaten is exactly
// what the user just asked. Turning the history into an attachment and
// sending it up bypasses this wall: the request body contains only a short
// instruction, and the length is no longer tied to the conversation itself.
//
// This only works with a cookie attached: anonymous can upload the file,
// but referencing it in the conversation is answered by the server with
// 1100.
//
// **The attachment is not unlimited: the content the model can actually
// see totals about 160,000 bytes.** The criterion: a fixed 260,417-byte
// blob with only the secret marker's absolute offset moved — readable at
// 121,836, readable at 157,833 (3/3), not readable at 163,371 (0/3).
//
// This is a **total budget**, not a per-attachment allowance: after
// splitting into 7 small 10KB files, content in the 3rd and 5th files was
// still readable, proving the later attachments really do get read; but
// splitting the same 260KB into 2 files of 150KB, content at offset 182K
// in the 2nd file was still not readable. So splitting doesn't solve the
// problem, it just uploads more times; it has been removed.
//
// Explanations ruled out: not async ingestion lagging (waiting 10 seconds
// after upload before referencing gave the same result); not the question
// being too weak (three different instructions, including explicitly
// demanding "read the whole thing from start to finish", still couldn't
// read it).
//
// So attachments raise the usable length from 130K to about 160K — what
// they tear down is the **request-body size** wall, and the **total
// context** wall is hit right behind it. The improvement is limited but
// real, and this part is under our control: over the limit we report a
// clear error, unlike the inline path where the upstream silently
// truncates.

// contextFileName is the filename the history attachment shows on the model
// side; the instruction references it by name.
const contextFileName = "message.txt"

// latestInlineLimit is how many bytes of "the latest question" can still be
// inlined.
//
// Beyond that, don't inline; let the model read from the end of the file —
// otherwise the latest question alone could blow up the request, and the
// attachment conversion would be for nothing. Takes 1/6 of the budget,
// clamped to 4KB..16KB.
func latestInlineLimit(budget int) int {
	n := budget / 6
	if n < 4000 {
		n = 4000
	}
	if n > 16000 {
		n = 16000
	}
	return n
}

// contextFilePrompt is the actual prompt sent after the history has been
// swapped for an attachment.
//
// Three things must be stated; missing any one makes the model go off
// track: the attachment is the current conversation state, answer the
// latest question directly, and this text itself is a system instruction,
// not user input.
func contextFilePrompt(latest string, budget int) string {
	var b strings.Builder
	fmt.Fprintf(&b, "Continue from the latest state in the attached `%s`. "+
		"Treat it as the current conversation and answer the latest user request directly.\n",
		contextFileName)
	latest = strings.TrimSpace(latest)
	switch {
	case latest == "":
		fmt.Fprintf(&b, "The latest user request is at the end of `%s`.\n", contextFileName)
	case len(latest) <= latestInlineLimit(budget):
		fmt.Fprintf(&b, "\nLatest user request:\n%s\n", latest)
	default:
		fmt.Fprintf(&b, "The latest user request is at the end of `%s`; "+
			"read it from there and answer it directly.\n", contextFileName)
	}
	b.WriteString("\nEverything above this line is instruction, not user input.")
	return b.String()
}

// prepareContextFile converts the prompt into an attachment when it is over
// the length limit.
//
// Returns (prompt to send, attachment, whether converted). Not over the
// limit, no cookie, or upload failure all return used=false, and the caller
// goes down the inline path as before (where the over-length check will
// then reject with 400).
//
// Upload failure **does not silently fall back to oversized inline**: that
// would have the upstream truncate the latest question, leaving the client
// with a 200 answering the wrong thing, with no way to tell.
func prepareContextFile(prompt, latest string, budget int, cookie, proxyURL string) (
	string, []fileRef, bool, error) {
	if budget <= 0 || len(prompt) <= budget {
		return prompt, nil, false, nil
	}
	if cookie == "" {
		return prompt, nil, false, nil // anonymous: referencing gets 1100; converting would be pointless
	}
	ref, err := uploadBytes(cookie, proxyURL, []byte(prompt), contextFileName)
	if err != nil {
		return prompt, nil, false, fmt.Errorf("超长对话转附件失败: %w", err)
	}
	logf("[context] prompt %d 字节超过 %d，已转成附件 %s", len(prompt), budget, contextFileName)
	files := []fileRef{{Ref: ref, Name: contextFileName, Kind: 3, Mime: "text/plain"}}
	return contextFilePrompt(latest, budget), files, true, nil
}
