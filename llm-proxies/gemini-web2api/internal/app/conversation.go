package app

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"sync"
	"time"

	fhttp "github.com/bogdanfinn/fhttp"
	"github.com/google/uuid"
)

// convState is the state of one native Gemini conversation. The whole conversation is bound
// to one cookie / egress and never switches mid-way — a switch makes Gemini treat it as a different conversation and the continuation cid becomes invalid.
type convState struct {
	cid, rid, rcid, tok26 string
	turn                  int    // turn index within the conversation, goes into inner[17], +1 per turn
	cookie                string // conversation-bound cookie: a signed-in account's cookie, or the session from an anonymous /app fetch
	sapisid               string // for computing SAPISIDHASH when signed in; empty for anonymous
	isLogin               bool
	accountID             int64
	proxyID               int64
	proxyURL              string
	updated               time.Time
}

const (
	// convTTL aligns with the ~2-hour lifetime of exported cookies; an expired conversation state has no reuse value.
	convTTL = 90 * time.Minute
	convMax = 4000
)

var (
	convMu    sync.Mutex
	convStore = map[string]*convState{}
)

// convDelete invalidates one conversation (used on continuation failure, so client retries don't hit the same dead conversation again).
func convDelete(key string) {
	if key == "" {
		return
	}
	convMu.Lock()
	delete(convStore, key)
	convMu.Unlock()
}

// convGet fetches one conversation and prunes expired ones along the way.
func convGet(key string) *convState {
	if key == "" {
		return nil
	}
	convMu.Lock()
	defer convMu.Unlock()
	st, ok := convStore[key]
	if !ok {
		return nil
	}
	if time.Since(st.updated) > convTTL {
		delete(convStore, key)
		return nil
	}
	return st
}

// convPut stores one conversation; over the limit, evicts a batch of the oldest.
func convPut(key string, st *convState) {
	if key == "" {
		return
	}
	convMu.Lock()
	defer convMu.Unlock()
	st.updated = time.Now()
	convStore[key] = st
	if len(convStore) > convMax {
		// Simple eviction: drop expired ones; still over, drop a small batch of the oldest.
		var oldestK string
		var oldestT time.Time
		first := true
		for k, v := range convStore {
			if time.Since(v.updated) > convTTL {
				delete(convStore, k)
				continue
			}
			if first || v.updated.Before(oldestT) {
				oldestK, oldestT, first = k, v.updated, false
			}
		}
		if len(convStore) > convMax && oldestK != "" {
			delete(convStore, oldestK)
		}
	}
}

// canonicalMessages flattens the message list into a stable role+text string for
// conversation fingerprinting. Only role and text content are taken — clients
//
// 2026-09-11 fix (Agent-Loop-Support): tool messages **are included in the fingerprint**.
// The original only flattened role+content, but an agent's history alternates
// user / assistant(null+tool_calls) / tool(result) — the assistant's content is null,
// flattened to an empty string; the tool's content is the execution result.
// convChildKey stores "the history the client will bring next turn after our reply",
// and the tool result is already in that history; both sides must use the same canonical function to match.
// Previously tool messages flattened identically and the assistant-null differed between turns, so continuation hit rates in agent loops dropped to nearly zero (every turn a new conversation; 7 turns → 4+ sessions; the upstream rate-limits it as spam).
func canonicalMessages(messages []map[string]interface{}) string {
	var b strings.Builder
	for _, m := range messages {
		b.WriteString(getStr(m, "role"))
		b.WriteByte(0x1f)
		b.WriteString(contentToString(m["content"]))
		b.WriteByte(0x1e)
	}
	return b.String()
}

func hashStr(s string) string {
	h := sha256.Sum256([]byte(s))
	return hex.EncodeToString(h[:])
}

// convParentKey is the fingerprint of "the history before this turn": everything
// except the last message. A store hit means this is the continuation of a known conversation; only the last new message needs sending.
//
// 2026-09-11 Agent-Loop-Support: an agent's history alternates user →
// assistant(tool_calls) → tool(result) → user. The tool's result content is
// produced locally on the client and unknowable when the proxy stores the
// childKey last turn — so besides the exact fingerprint, convGetByParentKey also tries a fallback fingerprint with the trailing tool messages stripped.
// assistant(tool_calls) flattens to an empty string in the fingerprint (content
func convParentKey(messages []map[string]interface{}) string {
	if len(messages) < 2 {
		return ""
	}
	return hashStr(canonicalMessages(messages[:len(messages)-1]))
}

// stripTrailingToolMsgs removes the trailing run of tool messages (the assistant's
// tool_calls block stays; canonical flattens its content=null → empty string, matching childKey).
func stripTrailingToolMsgs(messages []map[string]interface{}) []map[string]interface{} {
	n := len(messages)
	for n > 0 && getStr(messages[n-1], "role") == "tool" {
		n--
	}
	if n == len(messages) {
		return messages
	}
	return messages[:n]
}

// parentKeyCandidate: one candidate fingerprint plus the history prefix length it
// corresponds to (when sending the new message, we need to know where "new" starts).
type parentKeyCandidate struct {
	key     string
	prefixLen int
}

// parentKeyCandidates lists this turn's identification fingerprints by priority:
//  1. exact: the whole history (minus the last new message)
//  2. fallback: same, with trailing tool messages stripped — the agent-brings-tool-results-back case
func parentKeyCandidates(messages []map[string]interface{}) []parentKeyCandidate {
	if len(messages) < 2 {
		return nil
	}
	prefix := messages[:len(messages)-1]
	exact := hashStr(canonicalMessages(prefix))
	stripped := stripTrailingToolMsgs(prefix)
	if len(stripped) == len(prefix) {
		return []parentKeyCandidate{{key: exact, prefixLen: len(prefix)}}
	}
	return []parentKeyCandidate{
		{key: exact, prefixLen: len(prefix)},
		{key: hashStr(canonicalMessages(stripped)), prefixLen: len(stripped)},
	}
}

// convGetByParentKey finds a conversation by candidate fingerprints: exact hit first, fallback fingerprint as backstop.
// Returns the conversation plus the matched prefix length (= how many messages the server-side history already covers; everything after must be sent).
func convGetByParentKey(messages []map[string]interface{}) (*convState, int) {
	for _, cand := range parentKeyCandidates(messages) {
		if conv := convGet(cand.key); conv != nil {
			return conv, cand.prefixLen
		}
	}
	return nil, 0
}

// convChildKey is the fingerprint of "the history after this turn": history + this
// turn's model reply. The next request's parentKey equals it exactly (the client brings our reply back verbatim), which continues the conversation.
func convChildKey(messages []map[string]interface{}, responseText string) string {
	full := append(append([]map[string]interface{}{}, messages...),
		map[string]interface{}{"role": "assistant", "content": responseText})
	return hashStr(canonicalMessages(full))
}

var rcidRe = regexp.MustCompile(`"(rc_[A-Za-z0-9_-]{6,})"`)

// parseConvIDs extracts the four things continuation needs from a StreamGenerate
// response: cid=[1][0], rid=[1][1], tok26=frame[26], rcid=the rc_xxx in the body (needed as the 3rd element when continuing signed in; empty for anonymous).
func parseConvIDs(raw string) (cid, rid, rcid, tok26 string) {
	for _, line := range strings.Split(raw, "\n") {
		line = strings.TrimSpace(line)
		if !strings.HasPrefix(line, "[[") {
			continue
		}
		var arr []interface{}
		if json.Unmarshal([]byte(line), &arr) != nil {
			continue
		}
		for _, it := range arr {
			row, ok := it.([]interface{})
			if !ok || len(row) < 3 || row[0] != "wrb.fr" {
				continue
			}
			payload, ok := row[2].(string)
			if !ok {
				continue
			}
			var f []interface{}
			if json.Unmarshal([]byte(payload), &f) != nil {
				continue
			}
			if len(f) > 1 {
				if meta, ok := f[1].([]interface{}); ok && len(meta) >= 2 {
					if s, ok := meta[0].(string); ok && s != "" {
						cid = s
					}
					if s, ok := meta[1].(string); ok && s != "" {
						rid = s
					}
				}
			}
			if len(f) > 26 {
				if s, ok := f[26].(string); ok && s != "" {
					tok26 = s
				}
			}
		}
	}
	if m := rcidRe.FindStringSubmatch(raw); m != nil {
		rcid = m[1]
	}
	return
}

// getAnonSession does an anonymous GET /app for a session cookie (NID/COMPASS etc.),
// the conversation carrier for anonymous multi-turn. Continuation requests must
// carry it every turn, or the server treats it as a new conversation (measured: without it 0/4 pass, with it 4/4).
//
// 2026-09-10: the single-turn path (gemini.go) also uses it as the transport vehicle for anonymous requests (otherwise the upstream delays the end-marker frame to ~60s).
// Hence an in-process per-egress cache (TTL 30 minutes; exported cookies live ~2h, so 30 minutes is safely inside) — not one /app hit per request,
// saving a round trip and rate-limit quota. The conversation path still fetches its own (the conv binds its own cookie; the cache is not shared).
var (
	anonSessMu    sync.Mutex
	anonSessCache = map[string]anonSessEntry{}
)

type anonSessEntry struct {
	cookie string
	at     time.Time
}

const anonSessionTTL = 30 * time.Minute

// getAnonSessionCached: the anonymous session cached per egress; fetched fresh
// when expired or never obtained. Returns an empty string on failure (the caller
func getAnonSessionCached(proxyURL string) string {
	anonSessMu.Lock()
	e, ok := anonSessCache[proxyURL]
	anonSessMu.Unlock()
	if ok && time.Since(e.at) < anonSessionTTL {
		return e.cookie
	}
	c, err := getAnonSession(proxyURL)
	if err != nil {
		return ""
	}
	anonSessMu.Lock()
	anonSessCache[proxyURL] = anonSessEntry{cookie: c, at: time.Now()}
	anonSessMu.Unlock()
	return c
}
func getAnonSession(proxyURL string) (string, error) {
	req := func() (*http.Response, io.ReadCloser, []string, error) {
		if proxyURL != "" {
			r, err := http.NewRequest("GET", "https://gemini.google.com/app", nil)
			if err != nil {
				return nil, nil, nil, err
			}
			applyChromeHeaders(r)
			resp, err := getStdlibClient(proxyURL).Do(r)
			if err != nil {
				return nil, nil, nil, err
			}
			return resp, resp.Body, resp.Header.Values("Set-Cookie"), nil
		}
		r, err := fhttp.NewRequest("GET", "https://gemini.google.com/app", nil)
		if err != nil {
			return nil, nil, nil, err
		}
		r.Header.Set("User-Agent", webUA)
		resp, err := getTLSClient().Do(r)
		if err != nil {
			return nil, nil, nil, err
		}
		return nil, resp.Body, resp.Header.Values("Set-Cookie"), nil
	}
	_, body, setCookies, err := req()
	if err != nil {
		return "", err
	}
	if body != nil {
		io.Copy(io.Discard, body)
		body.Close()
	}
	var pairs []string
	seen := map[string]bool{}
	for _, sc := range setCookies {
		nv := strings.SplitN(sc, ";", 2)[0]
		name := strings.TrimSpace(strings.SplitN(nv, "=", 2)[0])
		if name == "" || seen[name] {
			continue
		}
		seen[name] = true
		pairs = append(pairs, strings.TrimSpace(nv))
	}
	if len(pairs) == 0 {
		return "", fmt.Errorf("anonymous /app returned no Set-Cookie")
	}
	return strings.Join(pairs, "; "), nil
}

// webUA is the User-Agent for the anonymous GET /app (the tls-client path must set it manually).
const webUA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
	"(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"

// streamGenerateConv sends one turn of a conversation. turn==0 is the first turn (creating the conversation), >0 is a continuation (only the new message).
// The whole conversation is bound to conv.cookie / conv.proxyID, never switching account or egress mid-way.
// On success, fills the conv's cid/rid/rcid/tok26 and turn+1 for the next continuation.
func streamGenerateConv(prompt string, mc ModelConfig, conv *convState,
	onDelta, onReasoning func(string)) (*StreamResult, error) {
	p, slotOK, slotErr := acquireSlot(conv.proxyID)
	if !slotOK {
		return &StreamResult{}, slotErr
	}
	defer releaseSlot(p.ID)
	proxyURL := p.URL
	pickedOK := p.ID > 0

	// The first turn fixes the egress; continuations reuse the conversation's original
	// egress (acquireSlot already prefers it, but if unavailable it must switch —
	if conv.turn == 0 {
		conv.proxyID = p.ID
		conv.proxyURL = proxyURL
		// Anonymous first turn: no signed-in cookie; fetch a session cookie on the spot as the conversation carrier.
		if conv.cookie == "" && !conv.isLogin {
			c, err := getAnonSession(proxyURL)
			if err != nil {
				return &StreamResult{ProxyID: p.ID, ProxyName: p.Name}, fmt.Errorf("failed to create an anonymous conversation: %w", err)
			}
			conv.cookie = c
		}
	}

	// Signed-in turns must carry at (XSRF); anonymous doesn't.
	xsrf := ""
	if conv.isLogin && conv.cookie != "" {
		if tok, err := getXSRF(conv.cookie, proxyURL); err == nil {
			xsrf = tok
		} else {
			return &StreamResult{ProxyID: p.ID, ProxyName: p.Name, AccountID: conv.accountID},
				fmt.Errorf("failed to get XSRF: %w", err)
		}
	}

	inner := make([]interface{}, innerSlots)
	inner[0] = []interface{}{prompt, 0, nil, nil, nil, nil, 0}
	inner[1] = []interface{}{"en"}
	if conv.turn == 0 {
		inner[2] = []interface{}{"", "", "", nil, nil, nil, nil, nil, nil, ""}
	} else {
		// Continuation: [cid, rid, rcid(signed-in)/""(anonymous), null×6, tok26]
		inner[2] = []interface{}{conv.cid, conv.rid, conv.rcid,
			nil, nil, nil, nil, nil, nil, conv.tok26}
	}
	inner[6] = []interface{}{0}
	inner[7] = 1
	inner[10] = 1
	inner[11] = 0
	inner[17] = []interface{}{[]interface{}{conv.turn}}
	inner[18] = 0
	inner[27] = 1
	inner[30] = []interface{}{4}
	inner[41] = []interface{}{2}
	inner[53] = 0
	reqUUID := uuid.NewString()
	inner[59] = reqUUID
	inner[61] = []interface{}{}
	inner[68] = 1
	inner[79] = mc.Mode
	inner[80] = thinkingNormal
	inner[91] = 0
	inner[96] = 0
	if mc.Thinking {
		inner[80] = thinkingExtended
		inner[96] = 1
	}

	innerJSON, _ := json.Marshal(inner)
	outerJSON, _ := json.Marshal([]interface{}{nil, string(innerJSON)})

	buildBody := func(at string) string {
		form := url.Values{}
		form.Set("f.req", string(outerJSON))
		if at != "" {
			form.Set("at", at)
		}
		return form.Encode()
	}
	body := buildBody(xsrf)

	thinkVal := thinkingNormal
	if mc.Thinking {
		thinkVal = thinkingExtended
	}
	geminiHeaders := buildGeminiHeaders(conv.cookie, conv.sapisid, mc.HexID)
	geminiHeaders["x-goog-ext-525001261-jspb"] = buildModelHeader(mc.HexID, mc.Mode, thinkVal, uuid.NewString())
	geminiHeaders["x-goog-ext-525005358-jspb"] = fmt.Sprintf(`["%s",1]`, reqUUID)

	reqid := time.Now().UnixNano() % 1000000
	endpoint := fmt.Sprintf(
		"https://gemini.google.com/u/1/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate?bl=%s&hl=en&_reqid=%d&rt=c",
		currentBL(proxyURL), reqid)

	tracker := &deltaTracker{}
	rtracker := &deltaTracker{}
	var lineCB func(string)
	if onDelta != nil || onReasoning != nil {
		lineCB = func(line string) {
			if onReasoning != nil {
				if r := reasoningInLine(line); r != "" {
					if d := rtracker.Push(r); d != "" {
						onReasoning(d)
					}
				}
			}
			if onDelta == nil {
				return
			}
			for _, t := range textsInLine(line) {
				if d := tracker.Push(t); d != "" {
					onDelta(d)
				}
			}
		}
	}

	t0 := time.Now()
	var lastErr error
	for attempt := 0; attempt < rtCfg().RetryAttempts; attempt++ {
		statusCode, raw, ttfb, setCookie, err := doGeminiRequest(endpoint, body, geminiHeaders, proxyURL, lineCB)
		if len(setCookie) > 0 && conv.cookie != "" {
			if merged := mergeSetCookie(conv.cookie, setCookie); merged != conv.cookie {
				conv.cookie = merged
			}
		}
		if err != nil || statusCode != 200 || !hasContentFrame(string(raw)) {
			if err == nil && statusCode == 200 {
				lastErr = fmt.Errorf("continuation produced no content frames (the conversation may have expired, raw %d bytes)", len(raw))
			} else if err != nil {
				lastErr = err
			} else {
				lastErr = fmt.Errorf("upstream HTTP %d: %s", statusCode, truncate(string(raw), 160))
			}
			if pickedOK {
				recordProxyResult(p.ID, false, lastErr.Error())
			}
			if tracker.emitted != "" || rtracker.emitted != "" {
				break
			}
			if attempt < rtCfg().RetryAttempts-1 {
				time.Sleep(time.Duration(rtCfg().RetryDelaySec) * time.Second)
			}
			continue
		}
		// Success: fill in the continuation state.
		cid, rid, rcid, tok26 := parseConvIDs(string(raw))
		if cid != "" {
			conv.cid = cid
		}
		if rid != "" {
			conv.rid = rid
		}
		if rcid != "" {
			conv.rcid = rcid
		}
		conv.tok26 = tok26 // updated every turn (may be empty)
		conv.turn++
		if pickedOK {
			recordProxyResult(p.ID, true, "")
		}
		return &StreamResult{
			Emitted:          tracker.emitted,
			EmittedReasoning: rtracker.emitted,
			Raw:              string(raw),
			Reasoning:        extractReasoning(string(raw)),
			UpstreamModel:    extractUpstreamModel(string(raw)),
			ProxyID:          p.ID,
			ProxyName:        p.Name,
			AccountID:        conv.accountID,
			TTFBMs:           ttfb,
			TotalMs:          time.Since(t0).Milliseconds(),
		}, nil
	}
	return &StreamResult{ProxyID: p.ID, ProxyName: p.Name, AccountID: conv.accountID}, lastErr
}

// callGeminiConv is the multi-turn entry point: identifies continuations by history prefix.
//   - Hit on a known conversation → send only the last new message (user or tool result); the history stays on the server (bypassing the byte wall).
//   - No hit → create a new conversation and send the fully assembled history on the first turn (including tools instructions, handing the current context to the server).
//
// Tools are supported (```tool_call``` fences are parsed in continuations too); images go through the original single-turn path (callGemini).
func callGeminiConv(messages []map[string]interface{}, mc ModelConfig,
	tools []map[string]interface{}, toolChoice interface{},
	onDelta, onReasoning func(string)) (string, []ToolCall, *StreamResult, error) {
	// 2026-09-11: candidate-fingerprint identification (see parentKeyCandidates) —
	// in agent loops the tool result is in the history, but we didn't know its content
	// when storing the childKey; the fallback fingerprint (trailing tool messages stripped) does the hitting.
	conv, hitLen := convGetByParentKey(messages)
	fresh := conv == nil
	var hitKeys []string
	if conv != nil {
		for _, cand := range parentKeyCandidates(messages) {
			if convGet(cand.key) != nil {
				hitKeys = append(hitKeys, cand.key)
			}
		}
	}

	var prompt string
	if fresh {
		conv = &convState{}
		// With a cookie pool, use a signed-in account (fuller capabilities); otherwise anonymous (first turn fetches a session cookie on the spot).
		// #20 anon-first: when the model needs no signed-in state, don't occupy an account (multi-turn is already gated to no-images-no-tools,
		// so attachments are never present and the second argument is false). Must short-circuit before the call:
		// pickCookieAccount updates last_used_at, calling it without using the account wastes a rotation slot.
		if !anonFirstEligible(mc, false) {
			if a, ok := pickCookieAccount(); ok {
				conv.cookie = a.Cookie
				conv.sapisid = extractSAPISID(a.Cookie)
				conv.isLogin = true
				conv.accountID = a.ID
				conv.proxyID = a.ProxyID
			}
		}
		// The first turn carries the tools instructions: the model needs them to know how to emit tool_call fences.
		prompt, _ = messagesToPrompt(messages, tools, toolChoice)
	} else {
		// Continuation turn: send **all new messages after the matched prefix** (2026-09-11
		// fix: previously only the last one — in agent loops the new part is two messages,
		// tool(result) + user, and the tool result was swallowed, leaving the model to
		// guess without the execution result (measured: it answered localhost instead of the real hostname). When the fallback fingerprint hits, hitLen points after the
		// assistant(tool_calls); everything from there is sent. The history before the hit stays on the server.
		var newTurns []string
		for i := hitLen; i < len(messages); i++ {
			if s := formatNewTurn(messages[i]); strings.TrimSpace(s) != "" {
				newTurns = append(newTurns, s)
			}
		}
		prompt = strings.Join(newTurns, "\n\n")
		// The tool-fence format instructions live in the server-side first-turn history,
		// but measured, the model loses discipline after a few turns (no more
		// ```tool_call```, plain prose answers); later (~turn 9) the context window even
		// pushes the first turn's tool definitions out, and the model answers "no tools". So every turn re-sends the format rules + the complete tool schema (toolsReminderBlock).
		if reminder := toolsReminderBlock(tools); reminder != "" {
			prompt += "\n\n" + reminder
		}
	}
	if fresh {
		logf("[conv] new conversation, first turn sends %d bytes (tools=%d)", len(prompt), len(tools))
	} else {
		logf("[conv] continuation hit turn=%d, sending only %d bytes (history stays server-side)", conv.turn, len(prompt))
	}

res, err := streamGenerateConv(prompt, mc, conv, onDelta, onReasoning)
	// On continuation failure (the conversation is dead server-side), **re-anchor in place**: before 2026-09-11 it deleted the conversation and errored to the client,
	// and only the client's/retry layer's next attempt took the new-conversation path — one extra meaningless (and conspicuous) upstream request.
	// Now: invalidate, and within this turn resend everything once as a new conversation, transparent to the client.
	// Re-anchor only when **no delta has been written to the client yet** (res.Emitted empty; once the stream started there's no redo, or content duplicates).
	if err != nil && !fresh && res != nil && res.Emitted == "" && res.EmittedReasoning == "" {
		for _, k := range hitKeys {
			convDelete(k)
		}
		logf("[conv] continuation failed (%v), re-anchoring in place as a new conversation this turn", err)
		conv = &convState{}
		if !anonFirstEligible(mc, false) {
			if a, ok := pickCookieAccount(); ok {
				conv.cookie = a.Cookie
				conv.sapisid = extractSAPISID(a.Cookie)
				conv.isLogin = true
				conv.accountID = a.ID
				conv.proxyID = a.ProxyID
			}
		}
		prompt, _ = messagesToPrompt(messages, tools, toolChoice)
		logf("[conv] re-anchor, first turn sends %d bytes (tools=%d)", len(prompt), len(tools))
		res, err = streamGenerateConv(prompt, mc, conv, onDelta, onReasoning)
	}
	if err != nil {
		return "", nil, res, err
	}
	text := extractResponseText(res.Raw)
	var toolCalls []ToolCall
	if len(tools) > 0 {
		text, toolCalls = parseToolCalls(text)
	}
	if text == "" && len(toolCalls) == 0 {
		if !fresh {
			for _, k := range hitKeys {
				convDelete(k)
			}
		}
		return "", nil, res, fmt.Errorf("upstream returned no content frame (raw %d bytes)", len(res.Raw))
	}
	// Store the continuation state: when the client brings this reply back verbatim
	// next turn, its parentKey hits here. What's stored is the fence-parsed body — the
	// client brings back the same text as the assistant message content. 2026-09-11: in agent loops the client next appends the tool result — that content is unknown
	// to us when storing the key; next turn hits via parentKeyCandidates' fallback fingerprint (trailing tool messages stripped), see the callGeminiConv header comment.
	convPut(convChildKey(messages, text), conv)
	return text, toolCalls, res, nil
}

// formatNewTurn formats the new message a continuation sends, aligned with how messagesToPrompt writes each role,
// so the model in the server-side history can tell whether it's a tool result or a new user message.
func formatNewTurn(msg map[string]interface{}) string {
	content := contentToString(msg["content"])
	if getStr(msg, "role") == "tool" {
		return fmt.Sprintf("[Tool result for %s]: %s", getStr(msg, "name"), content)
	}
	return content
}
