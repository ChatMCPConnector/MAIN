package app

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"time"

	fhttp "github.com/bogdanfinn/fhttp"
	"github.com/google/uuid"
)

// Model ids the Gemini server accepts, from the authoritative list returned by batchexecute?rpcids=otAQ7b.
const (
	hexFlash36   = "fbb127bbb056c959" // 3.6 Flash
	hexFlashLite = "cf41b0e0dd7d53e5" // 3.5 Flash-Lite
	hexPro31     = "9d8ca3786ebdfbea" // 3.1 Pro
	// 3.7 Flash: rolled out per account. The hex is the **primary hex** (first element) of the 3.7 entry in otAQ7b,
	// present in the lists of two independently rolled-out accounts, and users with 3.7 measured that sending it
	// gets "3.7 Flash" reported back (issue #4 / PR #11). Do NOT use the 797f3d0293f288ad from the compat list —
	// that is a generic "current Flash" pointer: old batch ids get 3.6 from it, which impersonates 3.7. Old batch
	// ids sending this primary hex cleanly downgrade to 3.5 Flash-Lite (like 3.1 Pro), hence the cookie gate.
	hexFlash38 = "56fdd199312815e2" // 3.8 Flash (previously recorded as 3.7; Google upgraded this hex in place to 3.8, HAR response frames already show the display name "3.8 Flash")
)

// innerSlots is the length of the inner array in the payload. The browser sends 97-98 slots; we used to open
// only 80, so inner[80] (extended thinking) had no position at all and could not be filled in.
//
// Extending is safe in itself: we once grew it from 80 to 102 to test whether inner[79] would come back to
// life — it does not; model selection is entirely decided by the x-goog-ext-525001261-jspb header, length has no effect.
const innerSlots = 97

// Value of inner[80] / model header index 15: 1=normal, 2=extended thinking.
//
// **Only effective when signed in**: on anonymous requests the server silently ignores it — the reported model
// stays normal and the reasoning chain is 0 characters (re-tested 3 groups with signed-in packet-capture
// parameters, 0 of 8 succeeded). So models using it are hidden without a cookie, same as 3.1 Pro.
const (
	thinkingNormal   = 1
	thinkingExtended = 2
)

// ModelConfig holds the server-side model id plus the legacy MODE_CATEGORY value.
type ModelConfig struct {
	// HexID travels in the x-goog-ext-525001261-jspb header and is the only model switch the server honors.
	// Measured: without this header, inner[79] values 1..6 all land on 3.5 Flash-Lite;
	// header saying 3.6 with inner[79]=6 yields 3.6 — the header overrides inner[79].
	HexID string
	Mode  int
	Desc  string
	// When true, sets inner[80]=2 — "extended thinking" in the web UI. Orthogonal to HexID:
	// all three models can enable it; it is not exclusive to any one model.
	Thinking bool
	// When non-zero, fills inner[49] so the server swaps in a backend model to generate media artifacts
	// (14=image Nano Banana / 21=music Lyria). Artifacts are not in the StreamGenerate response: fetch the
	// download link via hNvQHb and pull the raw bytes with the cookie subset the download host accepts, see
	// media.go. Requires a signed-in state: anonymous requests are silently downgraded to a plain "Are you signed in?" text.
	Tool int
}

// Only expose models that actually exist in the server list (batchexecute?rpcids=otAQ7b).
// The old gemini-3.5-flash / -thinking / -thinking-lite / gemini-auto /
// gemini-flash-lite aliases have been removed: they have no server-side entry, and keeping them
// only suggested there were five different models to choose from.
var Models = map[string]ModelConfig{
	"gemini-3.6-flash":      {HexID: hexFlash36, Mode: 1, Desc: "Latest all-around model"},
	"gemini-3.5-flash-lite": {HexID: hexFlashLite, Mode: 6, Desc: "Fastest, lightweight"},
	"gemini-3.1-pro":        {HexID: hexPro31, Mode: 3, Desc: "Most capable; needs a signed-in cookie (downgraded to Flash-Lite without one)"},
	// 3.8 Flash: Google upgraded the original 3.7 hex in place (same hex, server display name went 3.7 → 3.8).
	// Measured to be **paid-account exclusive** (not a rollout): only paid Gemini accounts have it; free accounts
	// are downgraded to 3.5 Flash-Lite. gemini-3.7-flash is kept as an alias (same hex).
	"gemini-3.8-flash": {HexID: hexFlash38, Mode: 1, Desc: "3.8 Flash; needs a signed-in PAID Google account (free accounts get downgraded to 3.5 Flash-Lite)"},
	"gemini-3.7-flash": {HexID: hexFlash38, Mode: 1, Desc: "alias of gemini-3.8-flash (same hex; Google renamed 3.7→3.8)"},

	// Extended-thinking variants. inner[80]=2 is orthogonal to the model hex, all models can enable it; but it
	// only works signed in, so they are hidden without a cookie, same as 3.1 Pro.
	"gemini-3.6-flash-thinking":      {HexID: hexFlash36, Mode: 1, Thinking: true, Desc: "3.6 Flash with extended thinking; needs a signed-in cookie"},
	"gemini-3.5-flash-lite-thinking": {HexID: hexFlashLite, Mode: 6, Thinking: true, Desc: "3.5 Flash-Lite with extended thinking; needs a signed-in cookie"},
	"gemini-3.1-pro-thinking":        {HexID: hexPro31, Mode: 3, Thinking: true, Desc: "3.1 Pro with extended thinking; needs a signed-in cookie"},
	"gemini-3.8-flash-thinking":      {HexID: hexFlash38, Mode: 1, Thinking: true, Desc: "3.8 Flash with extended thinking; needs a signed-in cookie"},
	"gemini-3.7-flash-thinking":      {HexID: hexFlash38, Mode: 1, Thinking: true, Desc: "alias of gemini-3.8-flash-thinking"},

	// Media generation. Once inner[49] is set, the server swaps in a backend model for images/music; artifacts
	// are fetched via hNvQHb + download host and returned as base64 data URLs in content. All require a signed-in state; hidden without a cookie.
	"gemini-image": {HexID: hexFlash36, Mode: 1, Tool: toolImage, Desc: "Image generation (Nano Banana); returns a base64 data URL; needs a signed-in cookie"},
	"gemini-music": {HexID: hexFlash36, Mode: 1, Tool: toolMusic, Desc: "Music generation (Lyria, ~30s); returns a base64 data URL; needs a signed-in cookie"},
	"gemini-video": {HexID: hexFlash36, Mode: 1, Tool: toolVideo, Desc: "Video generation (Veo, async); returns a base64 data URL; needs a signed-in cookie (usually a paid account)"},
	// Canvas: generates an immersive interactive HTML document, returned inline (not binary, no download). Requires a signed-in state.
	"gemini-canvas": {HexID: hexFlash36, Mode: 1, Tool: toolCanvas, Desc: "Canvas: generates an interactive HTML document (returned inline as a ```html block); needs a signed-in cookie"},
}

// hasCookie reports whether the cookie pool has a usable account. Decides whether 3.1 Pro appears in the model list.
func hasCookie() bool {
	_, enabled := accountCount()
	return enabled > 0
}

// modelNeedsLogin reports whether a model truly requires a signed-in state to work. Anonymous requests for
// this set are silently downgraded by the server: 3.1 Pro / 3.8 Flash → 3.5 Flash-Lite; the reasoning chain
// disappears; media tools become an "Are you signed in?" text. Single criterion shared by "which models to
// exclude without a cookie" and "#20 anon-first: whether to occupy a cookie account".
//
// Decided by HexID + Thinking + Tool; verified equivalent model-by-model to the old name-based check
// (3.1-pro/3.8-flash/3.7-flash): those three canonical names have HexID hexPro31 / hexFlash38, and the
// remaining login models are all covered by Thinking or Tool.
func modelNeedsLogin(mc ModelConfig) bool {
	return mc.HexID == hexPro31 || mc.HexID == hexFlash38 || mc.Thinking || mc.Tool > 0
}

// anonFirstEligible reports whether, under the "anon-first" toggle, this request can go anonymous (without
// occupying a cookie account): toggle on + no attachments + model needs no signed-in state. Referencing
// attachments (image/video) in a conversation requires login (anonymous gets 1100 upstream), so attachments
// always pick an account. Toggle off always returns false (old behavior: use an account whenever the pool has one).
func anonFirstEligible(mc ModelConfig, hasAttachment bool) bool {
	return rtCfg().AnonFirst && !hasAttachment && !modelNeedsLogin(mc)
}

// availableModels returns the models worth exposing under the current configuration.
//
// Without a cookie, 3.1 Pro is excluded: measured, anonymous requests for it are silently downgraded to
// 3.5 Flash-Lite while the client believes it is using Pro. Rather than letting it "succeed", don't offer it
//
// at all and fail at model-selection time.
// With a valid cookie it genuinely works: 6 consecutive calls all reported "3.1 Pro" itself, each with a
// reasoning chain (118-152 characters; plain 3.6 Flash is 0). The earlier note that "even signed in, free
// accounts only get 3.6 Flash" was measured without an XSRF token, when cookie-bearing requests could not be sent at all (see xsrf.go).
func availableModels() map[string]ModelConfig {
	if hasCookie() {
		return Models
	}
	out := make(map[string]ModelConfig, len(Models))
	for k, v := range Models {
		if modelNeedsLogin(v) {
			continue
		}
		out[k] = v
	}
	return out
}

// resolveModel maps a model name to its config.
//
// A "name@think=N" suffix is stripped and ignored. An old version wrote it into inner[17] as thinking depth —
// a misreading: packet captures show inner[17] is the turn index within the conversation (first turn [[0]],
// second turn with a conversation id [[1]], incrementing per turn), unrelated to thinking depth. We always
// start a new conversation, so it stays 0. The suffix is ignored without an error to avoid breaking clients already configured this way.
func resolveModel(modelName string) (string, ModelConfig, error) {
	if idx := strings.Index(modelName, "@think="); idx >= 0 {
		modelName = modelName[:idx]
	}
	mc, ok := availableModels()[modelName]
	if !ok {
		if full, exists := Models[modelName]; exists && !hasCookie() {
			downgrade := "are silently downgraded to 3.5 Flash-Lite"
			if full.Tool > 0 {
				downgrade = "are silently downgraded to a plain \"Are you signed in?\" text reply"
			}
			return "", ModelConfig{}, fmt.Errorf(
				"%s is unavailable without a Google account cookie: anonymous requests for it "+
					"%s. Add a cookie in the admin panel (Cookie pool) or via --cookie-file to enable it",
				modelName, downgrade)
		}
		return "", ModelConfig{}, fmt.Errorf("unknown model: %s", modelName)
	}
	// Since 2026-09-11: Gemini-Web models **always** run with extended thinking (user directive: "thinking IMMER,
	// nie ohne"). Implementation: when signed in, plain models are internally promoted to the same-hex thinking
	// variant — transparent to the client (model name unchanged), the response just gains a reasoning_content
	// while the body stays the same. No promotion when anonymous: the server ignores inner[80]=2, promoting
	// would be pointless (thinking and inner[96] are signed-in switches). Media models (image/music/video/
	// canvas) are not promoted either — their artifacts do not go through a text reasoning chain.
	mc = applyAlwaysThinking(modelName, mc, hasCookie())
	return modelName, mc, nil
}

// applyAlwaysThinking implements the always-thinking policy (pure function, called directly by tests).
// Signed in + plain text model + a thinking variant with the same hex and mode exists → promote.
func applyAlwaysThinking(modelName string, mc ModelConfig, hasLogin bool) ModelConfig {
	if hasLogin && !mc.Thinking && mc.Tool == 0 {
		if think, exists := Models[modelName+"-thinking"]; exists &&
			think.HexID == mc.HexID && think.Mode == mc.Mode && think.Thinking {
			logf("[model] %s -> thinking variant (always-thinking policy)", modelName)
			return think
		}
	}
	return mc
}

// StreamResult holds raw body + per-request proxy + timing info.
type StreamResult struct {
	// Emitted is the text already sent out via onDelta in streaming mode; empty for non-streaming.
	Emitted string
	Raw     string
	// Reasoning is the model's reasoning chain (only 3.1 Pro produces one).
	// The upstream sends it every time; we used to keep only the body and throw it away.
	Reasoning string
	// EmittedReasoning is the reasoning chain already sent out via onReasoning in streaming; empty for non-streaming.
	EmittedReasoning string
	// UpstreamModel is the model display name the server self-reports in response frame [42].
	// It need not match the requested model: gemini-3.1-pro is silently downgraded to 3.5 Flash-Lite when
	// anonymous — invisible if you only look at the request name, hence this field is always recorded.
	UpstreamModel string
	ProxyID       int64
	ProxyName     string
	// Which cookie-pool account was used, 0 = anonymous. Failed requests must carry it too — when debugging
	// "adding cookies caused mass failures", the most needed fact is which account the failed request used.
	AccountID    int64
	AccountLabel string
	TTFBMs       int64
	TotalMs      int64
	// Artifacts holds the raw artifact bytes fetched for media models (image/music); empty for non-media models.
	Artifacts []MediaArtifact
	// MediaErr records why media artifact retrieval failed: generation itself returned 200, but the hNvQHb /
	// download step failed. The caller reports an error on it instead of returning a "half-success" with text but no image.
	MediaErr string
}

// RateLimitError indicates that every IP slot has reached its rate limit.
// The HTTP handler returns 429 to the client when it sees this error.
type RateLimitError struct {
	Reason  string // "concurrent" / "rpm" / "rph"
	ProxyID int64  // 0 = direct slot full
}

func (e *RateLimitError) Error() string {
	if e.ProxyID == 0 {
		return "direct IP slot full: " + e.Reason + " limit reached (configure proxies to scale)"
	}
	return "all proxy slots full: " + e.Reason + " limit reached"
}

// acquireSlot picks a slot with spare capacity for this request.
// Priority: a proxy in the pool with capacity → direct.
// All full → *RateLimitError.
//
// A caller that gets (proxy, ok=true) must pair it with a deferred releaseSlot().
func acquireSlot(preferProxyID int64) (Proxy, bool, error) {
	// 1. Try the proxy pool first (if configured)
	proxyMu.RLock()
	hasProxies := len(proxyCache) > 0
	proxyMu.RUnlock()

	if hasProxies {
		if p, ok := pickProxyPreferring(preferProxyID); ok {
			return p, true, nil
		}
		// The pool has proxies but none is usable (rate-limit full / all disabled / all circuit-broken
		// and not past cooldown). By default **no fallback to direct** — configuring a proxy pool means
		// the local IP must not be shown to upstream, and silently going direct voids that premise; it
		// looks like ordinary requests in the logs and is hard to notice. Deployments preferring availability over IP hiding can enable fallback_direct.
		if !rtCfg().FallbackDirect {
			return Proxy{}, false, &RateLimitError{Reason: "rph", ProxyID: -1}
		}
		if ok, reason := trySlotAcquire(0); ok {
			logf("[proxy] no available egress in the proxy pool, falling back to direct for this request (fallback_direct enabled)")
			return Proxy{}, true, nil
		} else {
			return Proxy{}, false, &RateLimitError{Reason: reason, ProxyID: 0}
		}
	}

	// 2. No proxy pool → use the direct slot (id=0)
	if ok, reason := trySlotAcquire(0); ok {
		return Proxy{}, true, nil // ProxyID=0 means direct
	} else {
		return Proxy{}, false, &RateLimitError{Reason: reason, ProxyID: 0}
	}
}

// How many cookies one request tries at most. With a big pool, trying every account drags failed
// requests out for a long time, and 3 consecutive failures basically mean a pool-wide problem, not one bad account.
const maxCookieTries = 3

// releaseSlot releases the slot. proxyID=0 means direct.
func releaseSlot(proxyID int64) {
	slotRelease(proxyID)
}

// deltaTracker converts the upstream's cumulative frames into deltas.
//
// Each upstream frame carries the **full text so far**, not the newly added part, so it must be
// prefix-compared against what was already emitted. Frames occasionally break the prefix relation
// (the model rewrites, or a cleaned artifact straddles the boundary); then skipping beats sending —
// sending would push duplicated content to the client, and emitted content cannot be taken back. The missed part is made up by the caller via remainingText at the end.
type deltaTracker struct{ emitted string }

// Push takes one frame's cumulative full text and returns the delta since the last call; returns "" when nothing is new or no safe diff exists.
func (d *deltaTracker) Push(fullText string) string {
	cleaned := cleanGeminiText(fullText)
	if len(cleaned) <= len(d.emitted) || !strings.HasPrefix(cleaned, d.emitted) {
		return ""
	}
	delta := cleaned[len(d.emitted):]
	d.emitted = cleaned
	return delta
}

// streamGenerate POSTs to Gemini's StreamGenerate endpoint and returns raw body
// plus proxy/timing telemetry for the metrics layer.
// The 80-slot inner array is verbatim from the Python reference.
// With onDelta non-nil, true streaming is enabled: each frame the upstream writes is parsed once and
// prefix-diffed against the emitted content, and new parts are called back immediately. Each upstream
// frame carries the cumulative full text, not deltas, so the diff is ours to do. No retry once content has been emitted — a retry would deliver duplicate text to the client.
func streamGenerate(prompt, latest string, mc ModelConfig,
	onDelta, onReasoning func(string)) (*StreamResult, error) {
	return streamGenerateWithFiles(prompt, latest, mc, nil, onDelta, onReasoning)
}

// fileRef references one uploaded attachment.
type fileRef struct {
	Ref  string // path returned by the upload, like /contrib_service/ttl_1d/…
	Name string // file name shown to the model
	Kind int    // attachment kind: 1=image, 3=text/plain file
	Mime string // content type; the server decides how to parse the attachment from it
}

// streamGenerateWithFiles is the same, but can carry attachments.
//
// Attachments go into inner[0][3], shaped [[[ref, 1], "file name"], …]. Attachments only work with a
// signed-in state: anonymous can upload the file, but referencing it in the conversation is answered with 1100 by the server.
func streamGenerateWithFiles(prompt, latest string, mc ModelConfig, pending []pendingUpload,
	onDelta, onReasoning func(string)) (*StreamResult, error) {
	var files []fileRef

	// Pick the account first, then the proxy by the egress it was last bound to — one account should stick
	// to one egress IP as much as possible; otherwise an account hopping between dozens of egresses looks
	//
	// like account sharing to Google.
	// Picking the account before acquireSlot does not violate "fetching the XSRF must go through the official
	// egress": picking only reads the DB and sends no request; the actual sender is the getXSRF below, which runs after the slot is acquired.
	// #20 anon-first: without signed-in capabilities, no cookie account is occupied — anonymous saves quota (see anonFirstEligible). With attachments (image/video) anonymous is impossible — the uploadBytes section below errors out directly on cookieStr=="".
	var acct *CookieAccount
	if !anonFirstEligible(mc, len(pending) > 0) {
		if a, ok := pickCookieAccount(); ok {
			acct = a
		}
	}
	preferProxy := int64(0)
	if acct != nil {
		preferProxy = acct.ProxyID
	}

	// On errors, "which account / which egress" must be carried back too, otherwise failure records are all blank.
	// picked is only set after the slot is acquired; the closure captures it so every later attrib carries the egress of that moment.
	var picked Proxy
	var cookieID int64
	var cookieLabel string
	attrib := func(err error) (*StreamResult, error) {
		return &StreamResult{
			AccountID: cookieID, AccountLabel: cookieLabel,
			ProxyID: picked.ID, ProxyName: picked.Name,
		}, err
	}

	// Acquire a slot through the rate limiter (proxy or direct). All slots full → straight 429.
	p, slotOK, slotErr := acquireSlot(preferProxy)
	if !slotOK {
		return attrib(slotErr)
	}
	picked = p
	defer releaseSlot(picked.ID) // picked.ID=0 means the direct slot

	// picked.URL empty = direct slot. The proxy pool is the only entry point for proxies; there is no other
	// fallback egress anymore (the old "static proxy" field was merged into the pool, see seedProxiesFromConfig).
	proxyURL := picked.URL
	pickedOK := picked.ID > 0 // whether a proxy from the pool was actually used

	// The endpoint can only be assembled once the egress is settled: currentBL may kick off a background
	// fetch, and that fetch must go through the same egress as the real request — otherwise, even with a proxy pool configured, one request leaks from the local IP.
	reqid := time.Now().Unix() % 1000000
	endpoint := fmt.Sprintf(
		"https://gemini.google.com/u/1/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate?bl=%s&hl=en&_reqid=%d&rt=c",
		currentBL(proxyURL), reqid,
	)

	// Fetch the XSRF token. One dead cookie must not fail the whole request: if the current account can't
	// get one, move to the next, at most maxCookieTries. Without this, 1 bad account out of 2 in the pool
	// fail about half of all requests, every failure looking like an upstream problem — users just see a "mysteriously low success rate".
	//
	// Switching accounts does **not** switch egress: the egress was already chosen by the first account's binding; switching egress mid-request makes no sense.
	cookieStr, sapisid, xsrfToken := "", "", ""
	var lastCookieErr error
	tried := map[int64]bool{}
	// Each account gets only one "retry after rotation" chance, to avoid hitting accounts.google.com repeatedly within one request.
	rotatedOnce := map[int64]bool{}
	for acct != nil && len(tried) < maxCookieTries {
		tried[acct.ID] = true
		// Record attribution up front: even if this round fails, the panel shows which account is going bad.
		cookieID, cookieLabel = acct.ID, accountDisplayName(acct)
		tok, err := getXSRF(acct.Cookie, proxyURL)
		if err == nil {
			cookieStr, sapisid, xsrfToken = acct.Cookie, extractSAPISID(acct.Cookie), tok
			// Only write the binding when "never bound" or "the bound egress is gone".
			//
			// Never overwrite just because "this time went through a different egress": the egress was chosen
			// by the binding of the **first account picked this time**, and picking can change (newly added
			// accounts with last_used_at=0 sort first, so hitting a bad account switches). Overwriting the
			// current account's binding with someone else's egress re-scatters a good account's stickiness on every bad-account hit — measured, that is exactly how it got scattered.
			if acct.ProxyID == 0 || !proxyUsableByID(acct.ProxyID) {
				bindAccountProxy(acct.ID, picked.ID)
			}
			break
		}
		// Failing to get SNlM0e basically means the cookie is dead (the page treats us as anonymous).
		// Before switching accounts, give it one chance: force one rotation, then retry.
		//
		// Rotation re-issues __Secure-1PSIDTS (the ticket that expires in ~30 minutes) and merges *SIDCC.
		// Accounts where only the ticket expired but the persistent identity survives can be saved by this
		// step; if it can't be saved, switch accounts. Only tried once, and only in this round.
		if !rotatedOnce[acct.ID] {
			rotatedOnce[acct.ID] = true
			if _, _, rerr := rotateAccount(*acct); rerr == nil {
				if fresh := accountByID(acct.ID); fresh != nil {
					if tok2, err2 := getXSRF(fresh.Cookie, proxyURL); err2 == nil {
						logf("[cookie] account #%d recovered after rotation", acct.ID)
						acct = fresh
						cookieStr, sapisid, xsrfToken = fresh.Cookie, extractSAPISID(fresh.Cookie), tok2
						if fresh.ProxyID == 0 || !proxyUsableByID(fresh.ProxyID) {
							bindAccountProxy(fresh.ID, picked.ID)
						}
						break
					}
				}
			}
		}
		// Unrecoverable: record a failure so the panel shows which account should be replaced, then move to the next.
		markCookieByStatus(acct.ID, 401, err.Error())
		lastCookieErr = err
		logf("[cookie] account #%d unavailable, trying the next one: %v", acct.ID, err)
		acct, _ = pickCookieAccountExcept(tried) // returns nil when none is left; the loop ends naturally
	}
	if lastCookieErr != nil && cookieStr == "" {
		if !rtCfg().FallbackAnon {
			// Error out by default instead of downgrading: with a dead cookie the upstream doesn't reject, it
			// just treats you as anonymous — plain-text requests still get 200, so 3.1 Pro is silently
			// downgraded to 3.5 Flash-Lite, the reasoning chain vanishes, and the client can't tell. Prefer a clear failure over a fake success.
			return attrib(fmt.Errorf("all %d accounts in the cookie pool are unavailable (last one: %w); "+
				"use the \"Check\" button in the admin panel (Cookie pool) to inspect them one by one, or enable fallback_anon to downgrade to anonymous",
				len(tried), lastCookieErr))
		}
		logf("[cookie] all %d tried accounts are unavailable, downgrading to anonymous for this request (capabilities drop to the anonymous tier)", len(tried))
		cookieID, cookieLabel = 0, ""
	}
	// Anonymous request: grab a /app session cookie (NID/COMPASS etc.) **purely as a transport vehicle**.
	//
	// Measured 2026-09-10: an anonymous POST without a session cookie leaves the connection half-open after
	// the content frames arrive — the end-marker frame ([{"37":[0]}]) takes ~60 seconds to arrive
	// (reliably reproduced with tls-client; the control with a session cookie arrives immediately). The
	// multi-turn path (conversation.go getAnonSession) always did this; the single-turn path missed it,
	// so every anonymous request drained readBody's full idle budget. Failure is not fatal: it degrades to the old behavior (slow) but still sends.
	//
	// Note: this is an **anonymous session**, not a signed-in state. Never write it back into cookieStr —
	// prepareContextFile / media downloads below use cookieStr=="" to decide "signed in or not"; letting an
	// anonymous session slip in would push oversized prompts onto the upload path (anonymous references get 1100 upstream).
	reqCookie := cookieStr
	if reqCookie == "" {
		if c := getAnonSessionCached(proxyURL); c != "" {
			reqCookie = c
		}
	}
	// Image attachments: uploading needs a cookie and must go through the same egress as the real request, hence the position here.
	if len(pending) > 0 {
		if cookieStr == "" {
			return attrib(fmt.Errorf("image input needs a Google account cookie: " +
				"anonymous uploads succeed but referencing them in a conversation is " +
				"rejected upstream. Add a cookie in the admin panel (Cookie pool)"))
		}
		nImg, nVid := 0, 0
		for _, u := range pending {
			ref, uerr := uploadBytes(cookieStr, proxyURL, u.Data, u.Name)
			if uerr != nil {
				return attrib(fmt.Errorf("failed to upload attachment %s: %w", u.Name, uerr))
			}
			files = append(files, fileRef{Ref: ref, Name: u.Name, Kind: u.Kind, Mime: u.Mime})
			if u.Kind == 2 {
				nVid++
			} else {
				nImg++
			}
		}
		logf("[vision] uploaded %d images / %d videos", nImg, nVid)
	}

	// An oversized prompt is turned into a text attachment. This must wait until account and egress are
	// picked: uploading needs a cookie and must go through the same egress as the real request.
	budget := rtCfg().MaxPromptBytes
	if p, f, used, ferr := prepareContextFile(prompt, latest, budget, cookieStr, proxyURL); ferr != nil {
		return attrib(ferr)
	} else if used {
		prompt = p
		files = append(files, f...)
	}
	if budget > 0 && len(prompt) > budget {
		return attrib(&PromptTooLongError{
			Bytes: len(prompt), Budget: budget, HasCookie: cookieStr != "",
		})
	}

	inner := make([]interface{}, innerSlots)
	if len(files) > 0 {
		// Shape taken verbatim from browser packet captures:
		//   [[[path, kind, null, mime], "file name", nil×6, [0]], …]
		// The kind slot is 1=image / 3=text file — sending a text file with 1 tells the server "this is an image".
		refs := make([]interface{}, 0, len(files))
		for _, f := range files {
			kind := f.Kind
			if kind == 0 {
				kind = 3
			}
			mime := f.Mime
			if mime == "" {
				mime = "text/plain"
			}
			refs = append(refs, []interface{}{
				[]interface{}{f.Ref, kind, nil, mime}, f.Name,
				nil, nil, nil, nil, nil, nil,
				[]interface{}{0},
			})
		}
		inner[0] = []interface{}{prompt, 0, nil, refs, nil, nil, 0}
	} else {
		inner[0] = []interface{}{prompt, 0, nil, nil, nil, nil, 0}
	}
	inner[1] = []interface{}{"en"}
	inner[2] = []interface{}{"", "", "", nil, nil, nil, nil, nil, nil, ""}
	inner[6] = []interface{}{0}
	inner[7] = 1
	inner[10] = 1
	inner[11] = 0
	// Turn index within the conversation; we always start a new conversation, so always 0.
	inner[17] = []interface{}{[]interface{}{0}}
	inner[18] = 0
	inner[27] = 1
	inner[30] = []interface{}{4}
	// In packet captures the browser sends [1] in all three scenarios (with cookie / without cookie /
	// extended thinking). Our old [2] was an early copied value, since disproven at the protocol level.
	// The meaning is still unknown; both values work for anonymous, but there is no reason to keep deviating from the browser.
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
	// Media tool switch. When set, the server swaps in a backend model for images/music (the response carries artifact references; bytes are fetched separately).
	if mc.Tool > 0 {
		inner[49] = mc.Tool
	}
	// Video additionally needs the aspect ratio in inner[55]: [[16]]=16:9, [[17]]=9:16 (packet capture).
	if mc.Tool == toolVideo {
		inner[55] = []interface{}{[]interface{}{16}}
	}

	innerJSON, err := json.Marshal(inner)
	if err != nil {
		return nil, err
	}
	outer := []interface{}{nil, string(innerJSON)}
	outerJSON, err := json.Marshal(outer)
	if err != nil {
		return nil, err
	}

	// With a cookie, the extra form field at (XSRF token) must be sent, or the upstream returns 400 directly.
	// Anonymous requests don't need it; getXSRF returns an empty string for an empty cookie. See xsrf.go.
	buildBody := func(at string) string {
		form := url.Values{}
		form.Set("f.req", string(outerJSON))
		if at != "" {
			form.Set("at", at)
		}
		return form.Encode()
	}

	body := buildBody(xsrfToken)

	thinkVal := thinkingNormal
	if mc.Thinking {
		thinkVal = thinkingExtended
	}
	// In packet captures, header index 16 and inner[59] are two different uuids, each generated on its own.
	modelHeader := buildModelHeader(mc.HexID, mc.Mode, thinkVal, uuid.NewString())
	sessionHeader := fmt.Sprintf(`["%s",1]`, reqUUID)

	geminiHeaders := buildGeminiHeaders(reqCookie, sapisid, mc.HexID)
	geminiHeaders["x-goog-ext-525001261-jspb"] = modelHeader
	geminiHeaders["x-goog-ext-525005358-jspb"] = sessionHeader
	var lastErr error
	// The HTTP status code of the last attempt, 0 means the network layer failed before a response arrived.
	// Cookie health only counts 401/403; other statuses are not blamed on the cookie, see markCookieByStatus.
	lastStatus := 0
	xsrfRetried := false // XSRF self-healing happens only once, to avoid an endless loop
	t0 := time.Now()

	tracker := &deltaTracker{}
	rtracker := &deltaTracker{}
	var lineCB func(string)
	if onDelta != nil || onReasoning != nil {
		lineCB = func(line string) {
			// The reasoning chain finishes before the body, so handle it first — the client then receives them in the right order.
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

	for attempt := 0; attempt < rtCfg().RetryAttempts; attempt++ {
		statusCode, raw, ttfb, setCookie, err := doGeminiRequest(endpoint, body, geminiHeaders, proxyURL, lineCB)
		if len(setCookie) > 0 && cookieID > 0 {
			if merged := mergeSetCookie(cookieStr, setCookie); merged != cookieStr {
				cookieStr = merged
				updateAccountCookie(cookieID, merged)
			}
		}
		if err != nil {
			lastErr = err
			if pickedOK {
				recordProxyResult(picked.ID, false, err.Error())
			}
			// No retry once content has been emitted to the client, or it would duplicate (emitted reasoning counts too).
			if tracker.emitted != "" || rtracker.emitted != "" {
				break
			}
			if attempt < rtCfg().RetryAttempts-1 {
				logf("retry %d/%d: %v", attempt+1, rtCfg().RetryAttempts, err)
				time.Sleep(time.Duration(rtCfg().RetryDelaySec) * time.Second)
			}
			continue
		}
		if statusCode != 200 {
			// On token expiry the upstream returns 400 + xsrf. Invalidate the cache, re-fetch once, and retry;
			// this self-healing doesn't count against the retry budget, otherwise one expiry eats all retries.
			if statusCode == 400 && isXSRFError(string(raw)) && cookieStr != "" && !xsrfRetried {
				xsrfRetried = true
				invalidateXSRF(cookieStr)
				if tok, e := getXSRF(cookieStr, proxyURL); e == nil {
					body = buildBody(tok)
					geminiHeaders = buildGeminiHeaders(cookieStr, sapisid, mc.HexID)
					geminiHeaders["x-goog-ext-525001261-jspb"] = modelHeader
					geminiHeaders["x-goog-ext-525005358-jspb"] = sessionHeader
					attempt--
					continue
				}
			}
			lastErr = fmt.Errorf("upstream HTTP %d: %s", statusCode, truncate(string(raw), 200))
			lastStatus = statusCode
			if pickedOK {
				recordProxyResult(picked.ID, false, lastErr.Error())
			}
			if tracker.emitted != "" || rtracker.emitted != "" {
				break
			}
			if attempt < rtCfg().RetryAttempts-1 {
				time.Sleep(time.Duration(rtCfg().RetryDelaySec) * time.Second)
			}
			continue
		}
		// HTTP 200 but not a single content frame — the upstream's transient rejection (that 1155 in the
		// response). It is not rate limiting: a clean IP passed 15 back-to-back calls at 1s intervals,
		// 10-way concurrency on one IP passed all 18 calls, and an IP that already made 60+ calls still
		// succeeds afterwards — no predictable threshold; identical requests sometimes succeed, sometimes fail. One resend usually fixes it, so it must stay within retries — otherwise one blip becomes a client-visible 502.
		//
		// The criterion is **whether a content frame exists**, not BardErrorInfo: the end frame of a normal
		// response also carries error codes (1096 = conversation not persisted); judging by it would mark every normal response as failed.
		if !hasContentFrame(string(raw)) {
			// 1095 = throttling/refusal without content frames (measured late on 2026-09-10: starts
			// appearing after many requests from the same IP, intermittent, recovers on its own after a while).
			// Used as a **message** only (detection logic unchanged — the criterion is still "content frame
			// or not"), so the client can tell "the egress blipped" from "this IP is temporarily throttled by Google".
			detail := ""
			if strings.Contains(string(raw), "[1095]") {
				detail = " (BardErrorInfo 1095: upstream throttling this IP — back off or rotate egress)"
			}
			lastErr = fmt.Errorf("upstream returned no content frame (raw %d bytes)%s", len(raw), detail)
			if pickedOK {
				// Record it into proxy health: 1155 correlates strongly with egress quality (clean
				// egress 0 occurrences in 60+ calls, dirty egress ~9 a day); repeated hits mean this egress needs a rest.
				recordProxyResult(picked.ID, false, lastErr.Error())
			}
			if tracker.emitted != "" || rtracker.emitted != "" {
				break
			}
			if attempt < rtCfg().RetryAttempts-1 {
				logf("retry %d/%d: empty response (no content frames, %d bytes)", attempt+1, rtCfg().RetryAttempts, len(raw))
				time.Sleep(time.Duration(rtCfg().RetryDelaySec) * time.Second)
			}
			continue
		}
		if pickedOK {
			recordProxyResult(picked.ID, true, "")
		}
		markCookieByStatus(cookieID, 200, "")
		result := &StreamResult{
			Emitted:          tracker.emitted,
			EmittedReasoning: rtracker.emitted,
			Raw:              string(raw),
			Reasoning:        extractReasoning(string(raw)),
			UpstreamModel:    extractUpstreamModel(string(raw)),
			ProxyID:          picked.ID,
			ProxyName:        picked.Name,
			AccountID:        cookieID,
			AccountLabel:     cookieLabel,
			TTFBMs:           ttfb,
			TotalMs:          time.Since(t0).Milliseconds(),
		}
		// Media models: the generated artifact bytes are not in this response; go through hNvQHb +
		// download host once more with the same cookie / egress to fetch them. On failure, record MediaErr so the layer above errors out instead of returning a half product.
		if mc.Tool == toolImage || mc.Tool == toolMusic || mc.Tool == toolVideo {
			mime := "image/png"
			switch mc.Tool {
			case toolMusic:
				mime = "audio/mpeg"
			case toolVideo:
				mime = "video/mp4"
			}
			arts, aerr := fetchMediaArtifacts(
				mc.Tool, string(raw), extractConversationID(string(raw)),
				cookieStr, sapisid, xsrfToken, proxyURL, mime)
			if aerr != nil {
logf("[media] failed to retrieve artifacts: %v", aerr)
			result.MediaErr = aerr.Error()
		} else {
			result.Artifacts = arts
			logf("[media] retrieved %d artifacts", len(arts))
			}
		}
		// #19 auto-delete conversation: after the result, delete the conversation left on
		// gemini.google.com so they don't pile up in the user's account. Only works signed in (needs XSRF); async best-effort, doesn't affect the response.
		if rtCfg().AutoDeleteConversation && cookieStr != "" && xsrfToken != "" {
			if cid := extractConversationID(string(raw)); cid != "" {
				go deleteConversation(cid, cookieStr, sapisid, xsrfToken, proxyURL)
			}
		}
		return result, nil
	}
	if lastErr != nil {
		markCookieByStatus(cookieID, lastStatus, lastErr.Error())
	}
	return attrib(lastErr)
}

// upstreamModelRe matches the model display name the server self-reports in a response frame (the frame's [42] slot).
// Looks like ...,"fbb127bbb056c959",null,null,"3.6 Flash",true,...
var upstreamModelRe = regexp.MustCompile(`\\"[0-9a-f]{16}\\",null,null,\\"([^"\\]{1,40})\\"`)

// extractUpstreamModel extracts the model name the server actually used; returns an empty string when absent.
func extractUpstreamModel(raw string) string {
	m := upstreamModelRe.FindAllStringSubmatch(raw, -1)
	if len(m) == 0 {
		return ""
	}
	return m[len(m)-1][1]
}

// buildModelHeader assembles x-goog-ext-525001261-jspb, shape taken slot-by-slot from packet captures:
//
//	[1,null,null,null,"<hex>",null,null,0,[4,5,6,8],null,null,1,null,null,<mode>,<think>,"<uuid>"]
//	index                4                8                          14      15       16
//
// Index 14 equals inner[79] and index 15 equals inner[80] — model and thinking mode are stored in both
// the header and the payload. **The server honors the header**: filling only inner[80]=2 while leaving the
// header in minimal form yields a 0-character reasoning chain on all three models — the same rule as "header overrides inner[79]" in model selection itself.
//
// Index 16 is **another** uuid, not the same value as inner[59] — the one matching inner[59] is
// x-goog-ext-525005358-jspb. Both packet captures show this pattern; don't reuse one uuid for convenience.
//
// An empty uuid falls back to the minimal form (the anonymous path doesn't need these slots; sending less is simpler).
func buildModelHeader(hexID string, mode, think int, uuid string) string {
	if uuid == "" {
		return fmt.Sprintf(`[1,null,null,null,"%s"]`, hexID)
	}
	return fmt.Sprintf(
		`[1,null,null,null,"%s",null,null,0,[4,5,6,8],null,null,1,null,null,%d,%d,"%s"]`,
		hexID, mode, think, uuid)
}

// buildGeminiHeaders prepares the application-layer headers StreamGenerate requires.
// hexID decides which model the server uses; empty makes the server always fall back to 3.5 Flash-Lite.
func buildGeminiHeaders(cookieStr, sapisid, hexID string) map[string]string {
	h := map[string]string{
		"Accept":          "*/*",
		"Accept-Language": "en-US,en;q=0.9",
		"Content-Type":    "application/x-www-form-urlencoded;charset=UTF-8",
		"Origin":          "https://gemini.google.com",
		"Referer":         "https://gemini.google.com/u/1/app",
		"X-Same-Domain":   "1",
		"X-Goog-AuthUser": "0",
		// The browser sends these two on every request, with fixed values.
		"x-goog-ext-73010989-jspb": "[0]",
		"x-goog-ext-73010990-jspb": "[0,0,0]",
	}
	if hexID != "" {
		h["x-goog-ext-525001261-jspb"] = buildModelHeader(hexID, 0, 0, "")
	}
	if cookieStr != "" {
		h["Cookie"] = cookieStr
	}
	if sapisid != "" {
		h["Authorization"] = makeSAPISIDHash(sapisid)
	}
	return h
}

// doGeminiRequest sends one request to the endpoint. A non-empty proxyURL goes through stdlib (socks5/http
// supported), an empty one through tls-client (real chrome146 fingerprint). Returns (HTTP status, body bytes, err).
// The return value adds setCookie: nearly every server response refreshes SIDCC / __Secure-1PSIDCC /
// __Secure-3PSIDCC, which the browser stores and sends back. A client that keeps sending stale values is
// judged an expired session — measured, accounts die after one to two hours — so these must be collected and written back to the account.
func doGeminiRequest(endpoint, body string, headers map[string]string, proxyURL string,
	onLine func(string)) (int, []byte, int64, []string, error) {
	sendAt := time.Now()
	if proxyURL != "" {
		// Goes through stdlib http.ProxyURL; known to pass socks5/socks5h.
		req, err := http.NewRequest("POST", endpoint, strings.NewReader(body))
		if err != nil {
			return 0, nil, 0, nil, err
		}
		applyChromeHeaders(req)
		for k, v := range headers {
			req.Header.Set(k, v)
		}
		client := getStdlibClient(proxyURL)
		resp, err := client.Do(req)
		if err != nil {
			return 0, nil, 0, nil, err
		}
		defer resp.Body.Close()
		raw, ttfb, err := readBody(resp.Body, onLine, sendAt)
		if err != nil {
			return resp.StatusCode, nil, ttfb, resp.Header.Values("Set-Cookie"), err
		}
		return resp.StatusCode, raw, ttfb, resp.Header.Values("Set-Cookie"), nil
	}

	// Direct → tls-client, keeping the real chrome146 TLS/HTTP2 fingerprint
	req, err := fhttp.NewRequest("POST", endpoint, strings.NewReader(body))
	if err != nil {
		return 0, nil, 0, nil, err
	}
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	client := getTLSClient()
	resp, err := client.Do(req)
	if err != nil {
		return 0, nil, 0, nil, err
	}
	defer resp.Body.Close()
	raw, ttfb, err := readBody(resp.Body, onLine, sendAt)
	if err != nil {
		return resp.StatusCode, nil, ttfb, resp.Header.Values("Set-Cookie"), err
	}
	return resp.StatusCode, raw, ttfb, resp.Header.Values("Set-Cookie"), nil
}

// readBody reads the whole response body and returns it verbatim; with onLine non-nil, every line read is
// called back so the layer above can forward to the client while the upstream is still writing.
//
// Line scanning is always used (rather than a convenient io.ReadAll when onLine==nil) because the
// **moment the first line arrives** is needed as the TTFB. ReadAll returns only when everything has been
// read — the measured "first-byte latency" would really be the full latency, always equal to the total.
//
// start must be the time **before the request is sent**, passed in by the caller. Taking time.Now()
// inside this function is wrong: by then client.Do has returned and the response headers — even part of the body — have arrived, so it measures a constant 0.
//
// 2026-09-10: the upstream (measured on the anonymous path) no longer sends the classic `25\n[[\"e\",4,...]]` end
// frame + connection close — the connection **stays open** after all content frames arrive (no EOF even
// after 180s; measured with a 95s timeout, the 6 content frames were long complete). Waiting for EOF
// would push every anonymous request into the full RequestTimeout and then a 502. So two safeguards here:
//   1. isStreamEndLine: after seeing an end-marker frame (classic [["e",… or the new [{"37":[0]}]
//      tail frame), wait streamEndGrace for possible trailing frames; if nothing comes, treat the
//      response as complete and finish proactively (return what was read, no error).
//   2. streamIdleAbort: fallback for when no new line arrives for a long time — a half-open connection
//      with neither EOF nor an end marker; on expiry it is treated as an error and handed to the layer above for retry.
func readBody(r io.Reader, onLine func(string), start time.Time) ([]byte, int64, error) {
	var buf bytes.Buffer
	sc := bufio.NewScanner(io.TeeReader(r, &buf))
	// A single frame can be large (400,000-byte responses observed in practice); the default 64KB cap is not enough.
	sc.Buffer(make([]byte, 0, 64*1024), 8*1024*1024)

	type lineMsg struct {
		text string
		ok   bool
	}
	lines := make(chan lineMsg, 64)
	scanErrCh := make(chan error, 1)
	go func() {
		for sc.Scan() {
			lines <- lineMsg{sc.Text(), true}
		}
		close(lines)
		scanErrCh <- sc.Err()
	}()

	var ttfb int64 = -1
	endSeen := false
	var endGrace <-chan time.Time
	idle := time.NewTimer(streamIdleAbort)
	defer idle.Stop()
	for {
		select {
		case <-idle.C:
			return buf.Bytes(), ttfb, fmt.Errorf(
				"stream idle timeout (%s): no lines and no EOF (half-open connection)", streamIdleAbort)
		case <-endGrace:
			// No new line within the grace period after the end marker → response complete, finish proactively.
			return buf.Bytes(), ttfb, nil
		case m, more := <-lines:
			if !more {
				if err := <-scanErrCh; err != nil {
					return buf.Bytes(), ttfb, err
				}
				return buf.Bytes(), ttfb, nil
			}
			if ttfb < 0 {
				ttfb = time.Since(start).Milliseconds()
			}
			if onLine != nil {
				onLine(m.text)
			}
			if isStreamEndLine(m.text) {
				endSeen = true
			}
			if !idle.Stop() {
				nonBlockingDrain(idle.C)
			}
			idle.Reset(streamIdleAbort)
			if endSeen {
				// More trailing frames keep extending the grace; after the last frame, grace expiry finishes the read.
				endGrace = time.After(streamEndGrace)
			}
		}
	}
}

func nonBlockingDrain(c <-chan time.Time) {
	select {
	case <-c:
	default:
	}
}

const (
	// streamEndGrace: how long to keep waiting after the end-marker frame (possible trailing frames).
	streamEndGrace = 1500 * time.Millisecond
	// streamIdleAbort: fallback abort duration when not a single line arrives.
	streamIdleAbort = 45 * time.Second
)

// isStreamEndLine reports whether a line is a marker frame meaning "the response ends here".
//
// Two shapes:
//   - classic end frame: [["e",4,null,null,216]] (old captures, the server then closes the connection)
//   - new tail frame: [["wrb.fr",null,"[{\\"37\\":[0]}]"]] (measured 2026-09 on the anonymous path:
//     the connection stays open after the content frames, and this frame is the last one)
func isStreamEndLine(line string) bool {
	t := strings.TrimSpace(line)
	if strings.HasPrefix(t, `[["e"`) {
		return true
	}
	if !strings.HasPrefix(t, `[["wrb.fr"`) {
		return false
	}
	// The payload is JSON-in-JSON: "37" appears on the wire as \"37\". Both shapes are
	// accepted (with/without escaping) for robustness against upstream format tweaks.
	return strings.Contains(t, `\"37\":[0]`) || strings.Contains(t, `"37":[0]`)
}

// reasoningInLine extracts the reasoning chain from a single wrb.fr line.
//
// Its position is inner[4][0][37][0][0], two levels deeper than the body (inner[4][0][1][0]).
// Only 3.1 Pro produces one; 3.6 Flash / Flash-Lite are always empty.
//
// Timing (measured on a river-crossing puzzle): the reasoning chain accumulated to 660 characters
// over the first 5 frames while the body was still empty; from frame 6 on, the body grows while
// the reasoning chain freezes. Both are **cumulative full text**, not deltas, so the streaming side can reuse deltaTracker's prefix diff directly.
func reasoningInLine(line string) string {
	if !strings.Contains(line, `"wrb.fr"`) || len(line) < 200 {
		return ""
	}
	var arr []interface{}
	if err := json.Unmarshal([]byte(line), &arr); err != nil || len(arr) == 0 {
		return ""
	}
	first, ok := arr[0].([]interface{})
	if !ok || len(first) < 3 {
		return ""
	}
	innerStr, ok := first[2].(string)
	if !ok || len(innerStr) < 50 {
		return ""
	}
	var inner []interface{}
	if err := json.Unmarshal([]byte(innerStr), &inner); err != nil || len(inner) <= 4 {
		return ""
	}
	parts, ok := inner[4].([]interface{})
	if !ok || len(parts) == 0 {
		return ""
	}
	p0, ok := parts[0].([]interface{})
	if !ok || len(p0) <= 37 {
		return ""
	}
	lvl1, ok := p0[37].([]interface{})
	if !ok || len(lvl1) == 0 {
		return ""
	}
	lvl2, ok := lvl1[0].([]interface{})
	if !ok || len(lvl2) == 0 {
		return ""
	}
	s, _ := lvl2[0].(string)
	return s
}

// extractReasoning returns the longest reasoning chain in the whole response.
// Longest, not last: after the chain freezes, later frames may drop or truncate that slot.
//
// It must go through cleanGeminiText like extractResponseText: the streaming-side deltaTracker
// pushes cleaned text; without the cleaning here the prefixes don't match, and the final catch-up
// would resend the whole reasoning chain (measured block order became R→C→R).
func extractReasoning(raw string) string {
	best := ""
	for _, line := range strings.Split(raw, "\n") {
		if r := reasoningInLine(line); len(r) > len(best) {
			best = r
		}
	}
	return cleanGeminiText(best)
}

// textsInLine extracts candidate reply texts from a single wrb.fr line.
// Each upstream frame carries **cumulative full text**, not deltas, so streaming forwarding must do its own prefix diff.
func textsInLine(line string) []string {
	if !strings.Contains(line, `"wrb.fr"`) || len(line) < 200 {
		return nil
	}
	var arr []interface{}
	if err := json.Unmarshal([]byte(line), &arr); err != nil || len(arr) == 0 {
		return nil
	}
	first, ok := arr[0].([]interface{})
	if !ok || len(first) < 3 {
		return nil
	}
	innerStr, ok := first[2].(string)
	if !ok || len(innerStr) < 50 {
		return nil
	}
	var inner []interface{}
	if err := json.Unmarshal([]byte(innerStr), &inner); err != nil || len(inner) <= 4 {
		return nil
	}
	parts, ok := inner[4].([]interface{})
	if !ok {
		return nil
	}
	var texts []string
	for _, p := range parts {
		pl, ok := p.([]interface{})
		if !ok || len(pl) < 2 {
			continue
		}
		tl, ok := pl[1].([]interface{})
		if !ok {
			continue
		}
		for _, t := range tl {
			if s, ok := t.(string); ok && s != "" {
				texts = append(texts, s)
			}
		}
	}
	return texts
}

// hasContentFrame reports whether the response contains any content frame at all.
//
// Deliberately not reusing extractResponseText: that one runs cleanGeminiText first, which strips code
// artifacts, so a reply made purely of code artifacts looks empty to it — yet the upstream clearly
// produced content. Here we only ask "is there a frame": the question is whether the pipeline succeeded, not whether the content is usable.
func hasContentFrame(raw string) bool {
	for _, line := range strings.Split(raw, "\n") {
		if len(textsInLine(line)) > 0 || reasoningInLine(line) != "" {
			return true
		}
	}
	return false
}

// extractResponseText parses StreamGenerate's wrb.fr stream and returns the
// last non-empty text chunk (matches Python extract_response_text behavior).
func extractResponseText(raw string) string {
	var texts []string
	for _, line := range strings.Split(raw, "\n") {
		texts = append(texts, textsInLine(line)...)
	}
	for i := len(texts) - 1; i >= 0; i-- {
		if strings.TrimSpace(texts[i]) != "" {
			cleaned := cleanGeminiText(texts[i])
			if cleaned == "" {
				// The whole reply is a code-execution artifact (on math/formula prompts the model runs code
				// directly) and is stripped empty by the cleaning. Don't return empty — callGemini would treat
				// it as "no content frame" and 502, and the user sees a failed call. Fallback: only strip the ?code_reference/stdout markers, keep the code and result, and deliver it as a normal code block.
				cleaned = strings.TrimSpace(codeMarkerRe.ReplaceAllString(texts[i], "```$1"))
			}
			return cleaned
		}
	}
	return ""
}

var codeArtifactRe = regexp.MustCompile("(?s)```(?:python|javascript|text)\\?code_(?:reference|stdout)&code_event_index=\\d+\\n.*?```\\n?")

// codeMarkerRe matches only the **opening fence marker** of code artifacts (```python?code_reference&code_event_index=N),
// used for the fallback when cleaning empties the reply: downgrade the marker to plain ```python, keeping code/result instead of wiping the whole thing.
var codeMarkerRe = regexp.MustCompile("```(python|javascript|text)\\?code_(?:reference|stdout)&code_event_index=\\d+")

func cleanGeminiText(text string) string {
	return strings.TrimSpace(codeArtifactRe.ReplaceAllString(text, ""))
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n]
}

// ProbeResult is the connectivity diagnostic returned by the admin test endpoint.
type ProbeResult struct {
	OK           bool   `json:"ok"`
	Status       string `json:"status"` // "success" / "blocked_sorry" / "rate_limited" / "upstream_error" / "network_error"
	HTTPCode     int    `json:"http_code"`
	TotalMs      int64  `json:"total_ms"`
	ProxyID      int64  `json:"proxy_id"`
	ProxyName    string `json:"proxy_name"`
	UseDirect    bool   `json:"use_direct"`
	ResponseText string `json:"response_text"` // truncated to 200 characters
	UpstreamSnip string `json:"upstream_snip"` // first 300 characters of the raw upstream response
	Diagnostic   string `json:"diagnostic"`    // human-readable diagnostic text
	Impersonate  string `json:"impersonate"`
}

// probeGemini calls Gemini StreamGenerate directly (bypassing the rate limiter) and returns a detailed
// diagnostic. Writes no db and consumes no rate-limit slot.
func probeGemini(prompt, proxyURL string) ProbeResult {
	res := ProbeResult{Impersonate: rtCfg().Impersonate}

	inner := make([]interface{}, innerSlots)
	inner[0] = []interface{}{prompt, 0, nil, nil, nil, nil, 0}
	inner[1] = []interface{}{"en"}
	inner[2] = []interface{}{"", "", "", nil, nil, nil, nil, nil, nil, ""}
	inner[6] = []interface{}{0}
	inner[7] = 1
	inner[10] = 1
	inner[11] = 0
	inner[17] = []interface{}{[]interface{}{0}}
	inner[18] = 0
	inner[27] = 1
	inner[30] = []interface{}{4}
	// In packet captures the browser sends [1] in all three scenarios (with cookie / without cookie /
	// extended thinking). Our old [2] was an early copied value, since disproven at the protocol level.
	// The meaning is still unknown; both values work for anonymous, but there is no reason to keep deviating from the browser.
	inner[41] = []interface{}{2}
	inner[53] = 0
	inner[59] = uuid.NewString()
	inner[61] = []interface{}{}
	inner[68] = 1
	probeModel := Models["gemini-3.6-flash"]
	inner[79] = probeModel.Mode

	innerJSON, _ := json.Marshal(inner)
	outer := []interface{}{nil, string(innerJSON)}
	outerJSON, _ := json.Marshal(outer)
	form := url.Values{}
	form.Set("f.req", string(outerJSON))
	body := form.Encode()

	reqid := time.Now().Unix() % 1000000
	endpoint := fmt.Sprintf(
		"https://gemini.google.com/u/1/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate?bl=%s&hl=en&_reqid=%d&rt=c",
		currentBL(proxyURL), reqid,
	)

	// probe is a bypass diagnostic and does not write back cookie health: its failure reasons are unrelated
	// to the cookie. But at must be sent — otherwise, once a cookie is attached, connectivity probes keep reporting 400 and falsely claim breakage.
	cookieStr, sapisid := loadCookie()
	if tok, e := getXSRF(cookieStr, proxyURL); e == nil && tok != "" {
		form.Set("at", tok)
		body = form.Encode()
	}
	headers := buildGeminiHeaders(cookieStr, sapisid, probeModel.HexID)

	// Reuse the main path's client selection rule: proxy → stdlib, no proxy → tls-client.
	// But the probe needs the 302 Location header, so it sends directly instead of using doGeminiRequest.
	var statusCode int
	var raw []byte
	var locHeader string
	var err error

	if proxyURL != "" {
		req, e := http.NewRequest("POST", endpoint, strings.NewReader(body))
		if e != nil {
			res.Status = "network_error"
			res.Diagnostic = "failed to build the request: " + e.Error()
			return res
		}
		applyChromeHeaders(req)
		for k, v := range headers {
			req.Header.Set(k, v)
		}
		client := getStdlibClient(proxyURL)
		resp, e := client.Do(req)
		if e != nil {
			res.Status = "network_error"
			res.Diagnostic = "network-layer error (DNS/TCP/TLS failure): " + e.Error()
			return res
		}
		defer resp.Body.Close()
		statusCode = resp.StatusCode
		locHeader = resp.Header.Get("Location")
		raw, err = io.ReadAll(resp.Body)
	} else {
		req, e := fhttp.NewRequest("POST", endpoint, strings.NewReader(body))
		if e != nil {
			res.Status = "network_error"
			res.Diagnostic = "failed to build the request: " + e.Error()
			return res
		}
		for k, v := range headers {
			req.Header.Set(k, v)
		}
		client := getTLSClient()
		resp, e := client.Do(req)
		if e != nil {
			res.Status = "network_error"
			res.Diagnostic = "network-layer error (DNS/TCP/TLS failure): " + e.Error()
			return res
		}
		defer resp.Body.Close()
		statusCode = resp.StatusCode
		locHeader = resp.Header.Get("Location")
		raw, err = io.ReadAll(resp.Body)
	}
	_ = err
	res.HTTPCode = statusCode
	res.UpstreamSnip = truncate(string(raw), 300)

	switch {
	case statusCode == 302:
		res.Status = "blocked_sorry"
res.Diagnostic = "IP flagged by Google risk control (redirected to sorry/index). " +
		"Usually clears in 6-24 hours, or switch VPN/proxy IP for immediate recovery. Location: " + truncate(locHeader, 200)
		return res
	case statusCode == 429:
		res.Status = "rate_limited"
		res.Diagnostic = "Google returned 429 rate limiting directly. Also an IP suspicion, but a different risk-control branch (plain SDK path)."
		return res
	case statusCode != 200:
		res.Status = "upstream_error"
		res.Diagnostic = fmt.Sprintf("upstream returned non-200 (HTTP %d), possibly a protocol change or transient failure.", statusCode)
		return res
	}

	text := extractResponseText(string(raw))
	if text == "" {
		res.Status = "upstream_error"
res.Diagnostic = "upstream returned 200 but only the end frame, no content frames; usually the request was rejected server-side " +
		"(e.g. an unaccepted conversation id or tool flag), not a frame-format change."
		return res
	}

	res.OK = true
	res.Status = "success"
	res.ResponseText = truncate(text, 200)
	res.Diagnostic = "call succeeded. Latency / content see fields above."
	return res
}
