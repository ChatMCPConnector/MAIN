package app

import (
	"fmt"
	"strings"
	"sync"
	"time"
)

// QuotaLimitError signals that a Google account's 5-hour usage quota is
// exhausted.
//
// The upstream's manifestation is extremely subtle: HTTP 200, content
// frames, but the body is just one sentence:
// "I encountered an error doing what you asked. Could you try again?"
// (measured in practice at 65 bytes, visible in the requests table).
// Previously this sentence was passed through as a normal reply; an
// agentic client receiving prose without a tool_call aborts the whole loop —
// that is the real cause of death behind the fleeting "I encountered an
// error" in benchmarks.
//
// The quota window is a rolling 5 hours (paid Pro/Flash models are limited;
// 3.5 Flash-Lite is unlimited and always available). The upstream doesn't
// tell us the reset time, so it has to be estimated: the time of the
// **first** request within the window + 5h — looked up from the requests
// table.
type QuotaLimitError struct {
	Model string // model name that hit the limit
}

func (e *QuotaLimitError) Error() string {
	return fmt.Sprintf("gemini usage limit reached for %s (rolling 5h window, resets ~%s)",
		e.Model, quotaResetETA())
}

// CannedReplyError signals that the upstream replied with a short "canned
// error" sentence (a transient failure or a refusal phrase, issued in the
// account's language).
// Signature: HTTP 200, content frames, an extremely short body with fixed
// wording (see cannedErrorPrefixes).
// Unlike quota exhaustion: this one is transient, and resending once usually
// gets through — hence the handler layer does a single-turn retry instead
// of locking the window.
type CannedReplyError struct {
	Text string // the original canned reply
}

func (e *CannedReplyError) Error() string {
	return fmt.Sprintf("upstream returned a canned error reply (transient): %q", truncateStr(e.Text, 100))
}

func truncateStr(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "..."
}

// isQuotaText decides whether a reply text is the signature reply for quota
// exhaustion.
//
// Only the exact wording counts: a generalized "something went wrong" is a
// real upstream transient failure (measured in practice, the next request
// recovers); treating it as quota too would falsely trigger the 5-hour
// downgrade lock.
func isQuotaText(text string) bool {
	t := strings.TrimSpace(text)
	if t == "" {
		return false
	}
	// The upstream occasionally drifts in case/punctuation; prefix matching +
// a length cap tightens the false-positive surface.
	return len(t) < 120 && strings.HasPrefix(strings.ToLower(t),
		"i encountered an error doing what you asked")
}

// cannedGate delays opening the stream: it holds the first 220 bytes of
// delta in a buffer, releasing them all at once once enough accumulate
// (meaning it's not a canned error — canned ones are all extremely short)
// or when the stream ends.
//
// Why it's needed: detecting a canned error requires the **complete short
// sentence**, but true streaming pushes the first few deltas to the client
// already — sse.Started() turns true, and once detection hits, what was
// emitted can't be taken back; all that's left is Fail, and the agentic run
// breaks off right there (measured in practice, benchmark turn 7 hung). With
// the first 220 bytes held back: normal replies barely notice (first paint
// a few hundred ms later), while a canned reply never leaves the door at
// all, so a hit allows a clean retry.
type cannedGate struct {
	emit    func(string) // the real downstream (sse.SendContent / SendReasoning)
	buf     string
	flushed bool
	canned  bool
}

func newCannedGate(emit func(string)) *cannedGate {
	return &cannedGate{emit: emit}
}

const cannedGateHold = 220

// Push ingests a delta. During the buffering phase (not yet flushed) it
// accumulates; crossing the hold line means this is not canned — release
// everything and switch to pass-through mode.
func (g *cannedGate) Push(s string) {
	if g == nil || g.emit == nil {
		return
	}
	if g.flushed {
		g.emit(s)
		return
	}
	g.buf += s
	if len(g.buf) > cannedGateHold {
		g.flush()
	}
}

func (g *cannedGate) flush() {
	if g.flushed {
		return
	}
	g.flushed = true
	if g.buf != "" {
		g.emit(g.buf)
		g.buf = ""
	}
}

// Finish is called when the stream ends: short replies (possibly canned)
// are judged here.
// Canned → discard the buffer and set the canned flag (the caller retries
// accordingly; the client received not a single character);
// normal → release.
func (g *cannedGate) Finish() {
	if g == nil || g.flushed {
		return
	}
	g.flushed = true
	if isCannedErrorText(g.buf) {
		g.canned = true
		g.buf = ""
		return
	}
	if g.buf != "" {
		g.emit(g.buf)
		g.buf = ""
	}
}

// Canned reports whether Finish judged the reply to be canned.
func (g *cannedGate) Canned() bool {
	return g != nil && g.canned
}

// flushedForStarted reports whether real body text has already been
// released out the door (for distinguishing the sse.Started scenario:
// already released = the client truly saw body text, only Fail remains;
// canned verdict discarded the buffer = not a single character left the
// door, a clean retry is still possible).
func (g *cannedGate) flushedForStarted() bool {
	return g == nil || (g.flushed && !g.canned)
}

// cannedErrorPrefixes are the known prefixes of upstream "canned error"
// replies (issued in the account's language). These are all short sentences
// inside 200 + content frames, previously passed through as normal replies.
// Common signature: extremely short + fixed wording. Normal answers never
// start with these (exact prefix match).
var cannedErrorPrefixes = []string{
	"i encountered an error doing what you asked", // quota exhausted (en)
	"sorry, something went wrong",                 // transient failure (en)
	"i'm a language model",                        // transient/refusal (en)
	"i am a language model",                       // same, variant
	"ich bin ein sprachmodell",                    // transient/refusal (de)
	"leider ist beim verarbeiten",                 // transient failure (de)
	"es ist ein fehler aufgetreten",               // transient failure (de)
}

// cannedErrorMarkers is the heuristic's second net: canned errors all
// contain one of these word stems, while normal answers (especially those
// with tool_call fences) are almost never **both short and containing an
// error word**. Upstream variants keep appearing (measured in practice,
// 4 new wordings within one week); enumerating them one by one can't keep
// up — the two conditions together clamp the false-positive surface:
// length < 150 plus a word-stem hit.
var cannedErrorMarkers = []string{
	"error", "fehler", "language model", "sprachmodell",
	"programmierung hinaus", "hard time", "try again", "try something else",
	"erneut versuchen", "geht über", "can't fulfill", "kann ich nicht",
}

// isCannedErrorText decides whether the reply is a known canned error (any
// kind). The quota signature is a subset of it: quota gets a 5h lock, the
// rest are retried as transient.
func isCannedErrorText(text string) bool {
	t := strings.ToLower(strings.TrimSpace(text))
	if t == "" {
		return false
	}
	if len(t) > 200 { // canned errors are all short; real replies are almost certainly longer
		return false
	}
	for _, p := range cannedErrorPrefixes {
		if strings.HasPrefix(t, p) {
			return true
		}
	}
	// Heuristic: short + error word stem. Anything with a ```tool_call fence can
	// never be canned.
	if strings.Contains(t, "```") {
		return false
	}
	for _, m := range cannedErrorMarkers {
		if strings.Contains(t, m) {
			return true
		}
	}
	return false
}

const (
	quotaKVKey        = "quota_limited_until"
	quotaWindow       = 5 * time.Hour
	quotaFallbackNote = "[quota-fallback]"
)

var quotaMu sync.Mutex

// quotaResetETA estimates the quota window's reset time (HH:MM in local
// timezone).
// Basis: the window is a rolling 5h counted from the first request within
// it.
func quotaResetETA() string {
	if until, ok := quotaUntil(); ok {
		return until.Local().Format("15:04")
	}
	return "unknown"
}

// quotaUntil reads the quota reset timestamp recorded in kv.
func quotaUntil() (time.Time, bool) {
	v := kvGet(quotaKVKey)
	if v == "" || v == "0" {
		return time.Time{}, false
	}
	var unix int64
	if _, err := fmt.Sscanf(v, "%d", &unix); err != nil || unix <= 0 {
		return time.Time{}, false
	}
	return time.Unix(unix, 0), true
}

// markQuotaLimited records "quota exhausted": estimates the reset time and
// persists it in kv. Later requests (while quotaActive is true) downgrade
// immediately, saving an upstream call that is doomed to fail.
func markQuotaLimited() {
	quotaMu.Lock()
	defer quotaMu.Unlock()
	// First request within the window + 5h. If the lookup fails (empty table /
	// all stale data), conservatively use now+5h.
	first := time.Now().Add(-quotaWindow).Unix()
	if db != nil {
		var minTS int64
		err := db.QueryRow(`SELECT MIN(ts) FROM requests WHERE ts > ?`, first).Scan(&minTS)
		if err == nil && minTS > 0 {
			first = minTS
		}
	}
	until := time.Unix(first, 0).Add(quotaWindow)
	if !until.After(time.Now()) {
		until = time.Now().Add(quotaWindow) // estimate already expired (theoretically impossible) → conservatively wait another 5h
	}
	_ = kvSet(quotaKVKey, fmt.Sprintf("%d", until.Unix()))
	logf("[quota] quota exhaustion recorded, estimated reset at %s", until.Local().Format("15:04"))
}

// quotaBannerConfirmed is deprecated: the "out_of_quota" in the /app page is
// a **permanently present UTM link** (gemini_out_of_quota_input_inline_
// upgrade_banner, pointing to an upgrade ad on one.google.com/ai) that has
// nothing to do with whether quota is exhausted — measured in practice, the
// page carries it even when quota is fine; using it would falsely lock 5
// hours on every transient blip. The function signature is kept as a
// placeholder to avoid errors elsewhere; always returns false.
//
// The replacement lives in the server layer: retry-based confirmation —
// upon detecting the signature, **resend once**; if the signature doesn't
// reappear it was transient, no lock; if it reappears, quota is really
// exhausted, lock.
func quotaBannerConfirmed() bool {
	return false
}

// quotaActive reports whether the quota lock is still in effect. An expired
// lock is cleared along the way.
func quotaActive() bool {
	quotaMu.Lock()
	defer quotaMu.Unlock()
	until, ok := quotaUntil()
	if !ok {
		return false
	}
	if until.After(time.Now()) {
		return true
	}
	_ = kvSet(quotaKVKey, "0") // reset
	logf("[quota] quota window has reset, restoring normal models")
	return false
}

// quotaModelAffected decides whether the model is subject to the 5h quota
// (3.5 Flash-Lite is not).
func quotaModelAffected(mc ModelConfig) bool {
	return mc.HexID != hexFlashLite
}

// quotaFallbackModel picks the fallback target: 3.5 Flash-Lite (the
// thinking variant when the original model has thinking and the pool has an
// account). Returns (target model name, target config, available).
func quotaFallbackModel(mc ModelConfig) (string, ModelConfig, bool) {
	name := "gemini-3.5-flash-lite"
	if mc.Thinking && hasCookie() {
		name = "gemini-3.5-flash-lite-thinking"
	}
	fb, ok := Models[name]
	return name, fb, ok
}

// quotaFallbackPrefix assembles the preamble for the fallback reply so the
// client can see what happened.
func quotaFallbackPrefix(origModel, fbModel string) string {
	return fmt.Sprintf("%s The %s usage quota of this Google account is exhausted (rolling 5h window, estimated reset at %s). "+
		"This reply was generated by the downgraded %s; it switches back to %s automatically once the quota resets.",
		quotaFallbackNote, origModel, quotaResetETA(), fbModel, origModel)
}
