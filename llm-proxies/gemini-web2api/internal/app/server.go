package app

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

const Version = "4.20.0"

func writeJSON(w http.ResponseWriter, status int, data interface{}) {
	body, _ := json.Marshal(data)
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.WriteHeader(status)
	w.Write(body)
}

func handleModels(w http.ResponseWriter, r *http.Request) {
	var data []map[string]interface{}
	for name, c := range availableModels() {
		data = append(data, map[string]interface{}{
			"id":          name,
			"object":      "model",
			"created":     1700000000,
			"owned_by":    "google",
			"description": c.Desc,
		})
	}
	writeJSON(w, 200, map[string]interface{}{"object": "list", "data": data})
}

func handleRoot(w http.ResponseWriter, r *http.Request) {
	var modelNames []string
	for n := range availableModels() {
		modelNames = append(modelNames, n)
	}
	writeJSON(w, 200, map[string]interface{}{
		"status":  "ok",
		"version": Version,
		"models":  modelNames,
	})
}

func handleOptions(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
	w.Header().Set("Access-Control-Allow-Headers", "*")
	w.WriteHeader(204)
}

// buildUsage computes token counts with tiktoken, consistent with what the requests table records.
// responsesAPI=true uses the /v1/responses field names (input_tokens/output_tokens).
func buildUsage(prompt, text string, responsesAPI bool) map[string]int {
	return buildUsageWithReasoning(prompt, text, "", responsesAPI)
}

// buildUsageWithReasoning lists the reasoning chain's token count separately in usage.
//
// The reasoning chain is **not counted** in completion_tokens: it is the model's own
// inference process, hidden by default on the client; counting it makes users pay for output
// they never see (downstream newapi bills by completion_tokens). Listed separately in
// completion_tokens_details.reasoning_tokens, matching OpenAI's approach; whoever wants to bill for it adds it themselves.
func buildUsageWithReasoning(prompt, text, reasoning string, responsesAPI bool) map[string]int {
	// Media artifacts are base64 data URLs, millions of characters. Not counted as output tokens:
	// that is binary content; billing it as tokens makes users pay for bytes they never see, and downstream newapi charges by output token.
	in, out := countTokens(prompt), countTokens(stripDataURLs(text))
	if responsesAPI {
		return map[string]int{
			"input_tokens":  in,
			"output_tokens": out,
			"total_tokens":  in + out,
		}
	}
	u := map[string]int{
		"prompt_tokens":     in,
		"completion_tokens": out,
		"total_tokens":      in + out,
	}
	if reasoning != "" {
		u["reasoning_tokens"] = countTokens(reasoning)
	}
	return u
}

// rejectUnsupported checks for fields the client sent that we cannot honor.
//
// Only blocks cases where "silently ignoring" hands the client a wrong result: n>1 returns fewer candidates,
// and dropped image input makes the model answer the wrong question. Sampling parameters
// (temperature/top_p/max_tokens/...) have no corresponding upstream knob at all — accept and ignore them; erroring would only block well-behaved clients.
func rejectUnsupported(req map[string]interface{}, messages []map[string]interface{}) error {
	if n, ok := req["n"].(float64); ok && n > 1 {
		return fmt.Errorf("n=%d not supported: upstream returns a single candidate", int(n))
	}
	for _, m := range messages {
		parts, ok := m["content"].([]interface{})
		if !ok {
			continue
		}
		for _, c := range parts {
			cm, ok := c.(map[string]interface{})
			if !ok {
				continue
			}
			switch getStr(cm, "type") {
			case "image_url", "input_image":
				// With a cookie these are fine: images get uploaded as attachments and referenced.
				// Anonymous is not — they upload fine, but the first reference is rejected by the server, so accepting only hands the client an incomprehensible failure.
				if !hasCookie() {
					return fmt.Errorf("image input needs a Google account cookie: anonymous " +
						"uploads succeed but referencing them in a conversation is rejected " +
						"upstream. Add a cookie in the admin panel (Cookie pool)")
				}
			case "video_url", "input_video":
				// Videos work like images: referencing needs a signed-in state; anonymous references get 1100.
				if !hasCookie() {
					return fmt.Errorf("video input needs a Google account cookie: anonymous " +
						"uploads succeed but referencing them in a conversation is rejected " +
						"upstream. Add a cookie in the admin panel (Cookie pool)")
				}
			case "input_audio":
				return fmt.Errorf("audio input not supported")
			}
		}
	}
	return nil
}

func callGemini(prompt, latest string, mc ModelConfig, tools []map[string]interface{},
	images []pendingUpload, onDelta, onReasoning func(string)) (string, []ToolCall, *StreamResult, error) {
	res, err := streamGenerateWithFiles(prompt, latest, mc, images, onDelta, onReasoning)
	if err != nil {
		// res non-nil: on failure it carries only attribution (which account / which egress), for recordRequest
		return "", nil, res, err
	}
	text := extractResponseText(res.Raw)
	// Canvas: the HTML document is inline in the response (unlike image/music, no download),
	// extracted from the immersive structure. Standard text extraction only gets the preamble
	// ("I will generate…"); the document sits at inner[4][0][30]… and is pulled out separately by extractCanvasDoc.
	if mc.Tool == toolCanvas {
		doc := extractCanvasDoc(res.Raw)
		if doc == "" {
			return "", nil, res, fmt.Errorf("canvas generation failed: no HTML document in response (raw %d bytes)", len(res.Raw))
		}
		if text != "" && !strings.Contains(doc, text) {
			return text + "\n\n" + doc, nil, res, nil // preamble + document
		}
		return doc, nil, res, nil
	}
	// Media models (image/music): generation returned 200 but the artifact bytes were not retrieved — error out instead of returning a half product with text but no image; the client wants exactly that image / that piece of music.
	if mc.Tool == toolImage || mc.Tool == toolMusic || mc.Tool == toolVideo {
		if len(res.Artifacts) == 0 {
			msg := res.MediaErr
			if msg == "" {
				msg = "媒体产物取回失败"
			}
			return "", nil, res, fmt.Errorf("media generation succeeded but artifact retrieval failed: %s", msg)
		}
		// Artifacts are appended to the body as base64 data URLs (there may be no body at all, only image/music/video).
		text = appendArtifactMarkdown(text, res.Artifacts)
		return text, nil, res, nil
	}
	if text == "" {
		// On upstream rejection only an end frame comes back, no content frame (measured:
		// raw is just 216 bytes when rejected). This must error: it used to be returned as an
		// empty reply with 200 + content:null, and the client could not tell the request had failed.
		// Note: don't use BardErrorInfo to detect errors — normal responses' end frames also carry that code.
		return "", nil, res, fmt.Errorf("upstream returned no content frame (raw %d bytes)", len(res.Raw))
	}
	var toolCalls []ToolCall
	if len(tools) > 0 {
		text, toolCalls = parseToolCalls(text)
	}
	return text, toolCalls, res, nil
}

// recordRequest writes one row of metadata to the requests table.
// Privacy: the prompt/response strings themselves are never persisted —
// only their length, model name, latency, status, and proxy info.
func recordRequest(endpoint, model, prompt, response string, res *StreamResult, status int, errStr string, stream bool) {
	// Media artifacts are huge base64 strings; strip them before counting tokens/length: keeps them out of the statistics and avoids running tiktoken over millions of characters on the request thread for nothing.
	response = stripDataURLs(response)
	r := &RequestRow{
		TS:            time.Now().Unix(),
		Model:         model,
		Status:        status,
		Error:         errStr,
		PromptChars:   len(prompt),
		ResponseChars: len(response),
		PromptTokens:  countTokens(prompt),
		OutputTokens:  countTokens(response),
		Endpoint:      endpoint,
	}
	if stream {
		r.Stream = 1
	}
	if res != nil {
		r.UpstreamModel = res.UpstreamModel
		r.TotalMs = res.TotalMs
		r.TTFBMs = &res.TTFBMs
		if res.ProxyID > 0 {
			r.ProxyID = &res.ProxyID
		}
		r.ProxyName = res.ProxyName
		if res.AccountID > 0 {
			r.AccountID = &res.AccountID
		}
		r.AccountLabel = res.AccountLabel
	}
	go insertRequest(r)
}

// fbNameOrModel picks the model name for failure records: on a failed downgrade retry, record the downgrade target; otherwise the original model.
func fbNameOrModel(fb, model string) string {
	if fb != "" {
		return fb
	}
	return model
}

func handleChatCompletions(w http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(r.Body)
	if err != nil {
		writeJSON(w, 400, map[string]interface{}{"error": map[string]string{"message": err.Error()}})
		return
	}
	var req map[string]interface{}
	if err := json.Unmarshal(body, &req); err != nil {
		writeJSON(w, 400, map[string]interface{}{"error": map[string]string{"message": "invalid JSON"}})
		return
	}

	modelInput := getStr(req, "model")
	if modelInput == "" {
		modelInput = rtCfg().DefaultModel
	}
	modelName, modelCfg, err := resolveModel(modelInput)
	if err != nil {
		writeJSON(w, 400, map[string]interface{}{"error": map[string]string{"message": err.Error()}})
		return
	}

	messagesRaw, _ := req["messages"].([]interface{})
	var messages []map[string]interface{}
	for _, m := range messagesRaw {
		if mm, ok := m.(map[string]interface{}); ok {
			messages = append(messages, mm)
		}
	}

	toolsRaw, _ := req["tools"].([]interface{})
	var tools []map[string]interface{}
	for _, t := range toolsRaw {
		if tm, ok := t.(map[string]interface{}); ok {
			tools = append(tools, tm)
		}
	}

	if err := rejectUnsupported(req, messages); err != nil {
		writeJSON(w, 400, map[string]interface{}{"error": map[string]string{
			"message": err.Error(), "type": "invalid_request_error"}})
		return
	}

	// Decode images up front and carry them along; the actual upload waits until account and egress are picked (see streamGenerate).
	images, err := collectImages(messages, "")
	if err != nil {
		writeJSON(w, 400, map[string]interface{}{"error": map[string]string{
			"message": err.Error(), "type": "invalid_request_error"}})
		return
	}

	prompt, latest := messagesToPrompt(messages, tools, req["tool_choice"])
	if strings.TrimSpace(prompt) == "" && len(images) == 0 {
		writeJSON(w, 400, map[string]interface{}{"error": map[string]string{"message": "empty prompt"}})
		return
	}

	stream, _ := req["stream"].(bool)
	includeUsage := false
	if so, ok := req["stream_options"].(map[string]interface{}); ok {
		includeUsage, _ = so["include_usage"].(bool)
	}

	cid := "chatcmpl-" + randHex(12)
	created := time.Now().Unix()

	// With tools, the body passes through a fence gate: ```tool_call``` blocks need the full
	// text to parse; forwarding directly would push the raw fence to the client, so only parts
	// certainly outside the fence are let through. The reasoning chain is unrelated to the fence
	// and always streams. Outside that, the body is wrapped in a canned gate (cannedGate):
	// hold back the first 220 bytes, release only once enough accumulated — canned errors
	// are all one short sentence, so on detection nothing has left the building and a clean retry is possible (without holding back, sse.Started() is already true and only Fail remains, killing the run).
	var sse *sseWriter
	var gate *toolFenceGate
	var cgate *cannedGate
	var onDelta, onReasoning func(string)
	if stream {
		sse = newSSEWriter(w, cid, created, modelName)
		onReasoning = sse.SendReasoning
		// The canned gate wraps the outermost layer (without tools directly around SendContent; with tools around the fence gate) — the body on both paths must pass the canned hold first, otherwise canned prose from the tool path leaks straight through the fence gate to the client (measured: the benchmark turn 7 hang was exactly this). The reasoning
		// chain is not held: it is not a canned carrier, and replaying it on retry is harmless.
		cgate = newCannedGate(sse.SendContent)
		if len(tools) == 0 {
			onDelta = cgate.Push
		} else {
			gate = newToolFenceGate(cgate.Push)
			onDelta = gate.Push
		}
	}

	// 5h quota lock (#quota): while quota is exhausted, affected models downgrade directly to
	// 3.5 Flash-Lite, saving one doomed upstream call. The downgrade must be visible (prefix note) so the client knows what happened.
	fbPrefix := ""
	if rtCfg().QuotaFallback && quotaActive() && quotaModelAffected(modelCfg) {
		if fbName, fbCfg, ok := quotaFallbackModel(modelCfg); ok {
			logf("[quota] %s 额度受限，本请求降级 %s", modelName, fbName)
			fbPrefix = quotaFallbackPrefix(modelName, fbName) + "\n\n"
			modelName, modelCfg = fbName, fbCfg
		}
	}

	var text string
	var toolCalls []ToolCall
	var res *StreamResult
	fbName := ""
	if rtCfg().MultiTurn && len(images) == 0 && modelCfg.Tool == 0 {
		// Multi-turn: detect a continuation by history prefix; on a hit, send only the new message and leave the history on the server. Also taken with tools.
		text, toolCalls, res, err = callGeminiConv(messages, modelCfg, tools, req["tool_choice"], onDelta, onReasoning)
	} else {
		text, toolCalls, res, err = callGemini(prompt, latest, modelCfg, tools, images, onDelta, onReasoning)
	}
	// Stream finalization: canned-gate verdict (are the held 220 bytes a canned sentence?). After the verdict, release what should be released; if canned, nothing has left yet, and the detection below triggers a clean retry.
	if cgate != nil {
		cgate.Finish()
	}
	// The quota-exhausted signature reply is 200 + one fixed 65-byte sentence (see quota.go). It used to be passed through as a normal reply, and agentic clients aborted on prose without a tool_call. Translated here into an explicit error so the branches below take the downgrade/429 path. Parts already streamed can't be taken back, but the signature sentence is short and we sse.Fail immediately — the client sees one clean failure instead of a fake success.
	if err == nil && isQuotaText(text) {
		err = &QuotaLimitError{Model: modelName}
		text = ""
	}
	// Other canned errors ("Sorry, something went wrong" / "Ich bin ein Sprachmodell…", short
	// transient sentences in the account's language): also translated into explicit errors,
	// handled below with a **single-turn retry** — the retry goes through callGemini (full prompt),
	// not a conv continuation (the canned sentence is already in the server-side history; continuing would treat it as a normal turn, and the model tends to keep canning).
	if err == nil && isCannedErrorText(text) {
		err = &CannedReplyError{Text: text}
		text = ""
	}
	// 3.6+ tool refusal (see toolrefusal.go): the model treats the injected tool protocol as a
	// prompt injection and refuses, returning prose like "I cannot access the filesystem/tools".
	// When tool_choice requires tools (required / named function) but the reply has no
	// tool_calls, translate into an explicit error — agentic clients receiving finish_reason=stop
	// prose would mistake the task for done; that is how benchmark runs got stuck.
	// Only error when "the client explicitly required a tool call": under tool_choice=auto,
	// the model choosing not to call tools and explaining why is legitimate and is passed through as-is.
	if err == nil && len(tools) > 0 && len(toolCalls) == 0 {
		if mode, _ := parseToolChoice(req["tool_choice"]); mode == "required" && isToolRefusalText(text) {
			err = &ToolRefusalError{Model: modelName, Text: text}
			text = ""
		}
	}
	if err != nil {
		if tre, ok := err.(*ToolRefusalError); ok {
			// If streaming already started, Fail (the refusal prose usually got partly through the gate);
			// without a stream, 502. Retrying is pointless: ten prompt framings measured, none changed the model's refusal stance.
			recordRequest("chat.completions", modelName, prompt, "", res, 502, tre.Error(), stream)
			if sse != nil && sse.Started() {
				sse.Fail(tre)
				return
			}
			writeJSON(w, 502, map[string]interface{}{"error": map[string]string{
				"message": tre.Error() + " — this model (Gemini web 3.6+ flash family, same hex as " +
					"3.8-flash) has anti-injection training that rejects tool_call prompts; " +
					"use gemini-3.5-flash-lite for tool-based agent loops",
				"type": "tool_refusal",
				"code": "model_refuses_tool_protocol",
			}})
			return
		}
		if cre, ok := err.(*CannedReplyError); ok {
			// Transient canned error: single-turn retry, **at most 3 times** (measured, the upstream
			// recovers after 2-3 consecutive blips; one retry is not enough — two canned errors in a
			// row once froze a benchmark run). The retry goes through callGemini (full prompt), not
			// a conv continuation — the canned sentence is already in the server-side history;
			// continuing would treat it as a normal turn, and the model tends to keep canning. No retry once the stream started (sse.Started): what left can't be taken back.
			recordRequest("chat.completions", modelName, prompt, "", res, 502, cre.Error(), stream)
			if sse != nil && sse.Started() && (cgate == nil || cgate.flushedForStarted()) {
				sse.Fail(cre)
				return
			}
			retryOK := false
			for i := 0; i < 3; i++ {
				logf("[canned] %s 罐头错误（%q），单轮重发 %d/3", modelName, truncateStr(cre.Text, 60), i+1)
				text, toolCalls, res, err = callGemini(prompt, latest, modelCfg, tools, images, nil, nil)
				if err != nil {
					recordRequest("chat.completions", modelName, prompt, "", res, 502, err.Error(), stream)
					writeJSON(w, 502, map[string]interface{}{"error": map[string]string{"message": "upstream error: " + err.Error()}})
					return
				}
if !isCannedErrorText(text) {
				// The retry got non-canned content — but it may be exactly the 3.6+ tool refusal
				// (canned retries often blip once or twice with "I'm having a hard time" first, then
				// the model produces refusal prose; isCannedErrorText lets it through, so add a second check here).
				if len(tools) > 0 && len(toolCalls) == 0 {
					if mode, _ := parseToolChoice(req["tool_choice"]); mode == "required" && isToolRefusalText(text) {
						err = &ToolRefusalError{Model: modelName, Text: text}
						text = ""
						break // retryOK stays false → refusal handling
					}
				}
				retryOK = true
				break
			}
				logf("[canned] 重发 %d/3 仍是罐头：%q", i+1, truncateStr(text, 60))
			}
if !retryOK {
			if tre, ok := err.(*ToolRefusalError); ok {
				// Refusal after canned retries: same refusal exit as above, clean error.
				recordRequest("chat.completions", modelName, prompt, "", res, 502, tre.Error(), stream)
				if sse != nil && sse.Started() {
					sse.Fail(tre)
					return
				}
				writeJSON(w, 502, map[string]interface{}{"error": map[string]string{
					"message": tre.Error() + " — this model (Gemini web 3.6+ flash family, same hex as " +
						"3.8-flash) has anti-injection training that rejects tool_call prompts; " +
						"use gemini-3.5-flash-lite for tool-based agent loops",
					"type": "tool_refusal",
					"code": "model_refuses_tool_protocol",
				}})
				return
			}
			recordRequest("chat.completions", modelName, prompt, "", res, 502, "canned error retry failed (3x)", stream)
				writeJSON(w, 502, map[string]interface{}{"error": map[string]string{
					"message": "upstream keeps returning canned error replies; try again later",
				}})
				return
			}
			// Retry succeeded: take the normal return path. The conv state is already decoupled from the client history; the next request's continuation fingerprint simply won't match, and it re-sends everything as a new conversation. Safe.
			recordRequest("chat.completions", modelName, prompt, text, res, 200, "canned-error retry ok", stream)
			if stream {
				// The retry ran without streaming callbacks (nulled to avoid duplicates); send body + tool_calls here in one shot.
				if res != nil && res.Reasoning != "" {
					sse.SendReasoning(res.Reasoning)
				}
				sse.SendContent(text)
				if len(toolCalls) > 0 {
					sse.SendToolCalls(toolCalls)
				}
				var usage map[string]int
				if includeUsage {
					usage = usageOf(prompt, text, res)
				}
				sse.Finish(finishFor(toolCalls), usage)
			} else {
				writeJSON(w, 200, map[string]interface{}{
					"id":      "chatcmpl-" + randHex(12),
					"object":  "chat.completion",
					"created": time.Now().Unix(),
					"model":   modelName,
					"choices": []map[string]interface{}{{
						"index":         0,
						"message":       assistantMessage(text, toolCalls, res),
						"finish_reason": finishFor(toolCalls),
					}},
					"usage": usageOf(prompt, text, res),
				})
			}
			return
		}
		if qle, ok := err.(*QuotaLimitError); ok {
			// The quota signature reply (fixed 65-byte wording) is first treated as a **suspect**, confirmed by a retry: re-send once with the same model verbatim; the signature reappears = truly exhausted → lock 5h + downgrade/429; doesn't reappear = transient blip → return the retry result normally. (The /app banner approach was dropped: its out_of_quota string is a permanent UTM link, present in the page even when quota is fine.)
			recordRequest("chat.completions", modelName, prompt, "", res, 429, qle.Error(), stream)
			// Fail only if the stream is already open and the gate has released (non-canned path
			// really wrote something); while the canned gate holds the head, sse may not have started yet, and a clean retry is possible.
			if sse != nil && sse.Started() && (cgate == nil || cgate.flushedForStarted()) {
				sse.Fail(qle) // stream already open, can only fail out
				return
			}
			logf("[quota] 检出额度签名回复（%s），原模型重发一次确认", modelName)
			text, toolCalls, res, err = callGemini(prompt, latest, modelCfg, tools, images, nil, nil)
			confirmed := err == nil && isQuotaText(text)
			if !confirmed && err == nil {
				// Transient: the retry got normal content → return normally (no lock, no downgrade).
				recordRequest("chat.completions", modelName, prompt, text, res, 200, "quota-signature transient, retry ok", stream)
				if stream {
					if res != nil && res.Reasoning != "" {
						sse.SendReasoning(res.Reasoning)
					}
					sse.SendContent(text)
					if len(toolCalls) > 0 {
						sse.SendToolCalls(toolCalls)
					}
					var usage map[string]int
					if includeUsage {
						usage = usageOf(prompt, text, res)
					}
					sse.Finish(finishFor(toolCalls), usage)
				} else {
					writeJSON(w, 200, map[string]interface{}{
						"id":      "chatcmpl-" + randHex(12),
						"object":  "chat.completion",
						"created": time.Now().Unix(),
						"model":   modelName,
						"choices": []map[string]interface{}{{
							"index":         0,
							"message":       assistantMessage(text, toolCalls, res),
							"finish_reason": finishFor(toolCalls),
						}},
						"usage": usageOf(prompt, text, res),
					})
				}
				return
			}
			// Signature reappeared (or the retry errored with a quota-class error) → truly exhausted: lock + downgrade/429.
			markQuotaLimited()
			if err != nil && !isQuotaText(text) {
				// The retry failed but not with the quota signature (network/upstream error): report it as-is, don't mislead as a quota issue.
				recordRequest("chat.completions", modelName, prompt, "", res, 502, err.Error(), stream)
				writeJSON(w, 502, map[string]interface{}{"error": map[string]string{"message": "upstream error: " + err.Error()}})
				return
			}
			if fb, fbCfg, ok := quotaFallbackModel(modelCfg); rtCfg().QuotaFallback && ok {
				// One downgrade retry (single-turn path: the conv state is invalidated, flash-lite is not quota-limited, so sending the full prompt is safest). Streaming callbacks nulled — the prefix note must come first.
				logf("[quota] %s 额度耗尽（重发确认），降级 %s 重发", modelName, fb)
				fbPrefix = quotaFallbackPrefix(modelName, fb) + "\n\n"
				text, toolCalls, res, err = callGemini(prompt, latest, fbCfg, tools, images, nil, nil)
				if err == nil {
					fbName, modelName = fb, fb
				}
			} else {
				text, res, err = "", nil, qle
			}
			if err != nil {
				if qle2, ok := err.(*QuotaLimitError); ok {
					writeJSON(w, 429, map[string]interface{}{"error": map[string]string{
						"message": qle2.Error(),
						"type":    "rate_limit_exceeded",
						"code":    "usage_limit_reached",
					}})
					return
				}
				recordRequest("chat.completions", fbNameOrModel(fbName, modelName), prompt, "", res, 502, err.Error(), stream)
				writeJSON(w, 502, map[string]interface{}{"error": map[string]string{"message": "upstream error: " + err.Error()}})
				return
			}
		} else {
			recordRequest("chat.completions", modelName, prompt, "", res, 502, err.Error(), stream)
		}
		if sse != nil && sse.Started() {
			sse.Fail(err) // stream already open, the HTTP status code can't be changed anymore
			return
		}
		if ptl, ok := err.(*PromptTooLongError); ok {
			// Report 400 explicitly rather than sending it and letting the upstream truncate the
			// user's question — that hands the client an off-topic 200 with no hint the request never got through.
			writeJSON(w, 400, map[string]interface{}{"error": map[string]string{
				"message": ptl.Error(), "type": "invalid_request_error",
				"code": "context_length_exceeded"}})
			return
		}
		if rle, ok := err.(*RateLimitError); ok {
			writeJSON(w, 429, map[string]interface{}{"error": map[string]string{
				"message": rle.Error(),
				"type":    "rate_limit_exceeded",
				"code":    "ip_slot_full",
			}})
			return
		}
		writeJSON(w, 502, map[string]interface{}{"error": map[string]string{"message": "upstream error: " + err.Error()}})
		return
	}

	msg := map[string]interface{}{"role": "assistant"}
	if text != "" {
		// Downgrade note prefix: on quota fallback, notify first, then the body (the prefix was never streamed; add it here).
		if fbPrefix != "" && sse != nil && !strings.Contains(sentText(res, gate), quotaFallbackNote) {
			sse.SendContent(fbPrefix)
		}
		text = fbPrefix + text
		msg["content"] = text
	} else {
		msg["content"] = nil
	}
	// The reasoning chain goes into reasoning_content — the de-facto standard popularized by DeepSeek-R1; newapi and mainstream clients recognize it and render it as a collapsible "thought process". Only 3.1 Pro has one; the rest are empty.
	if res != nil && res.Reasoning != "" {
		msg["reasoning_content"] = res.Reasoning
	}
	finish := "stop"
	if len(toolCalls) > 0 {
		msg["tool_calls"] = toolCalls
		finish = "tool_calls"
	}

	recordRequest("chat.completions", modelName, prompt, text, res, 200, "", stream)
	if stream {
		var usage map[string]int
		if includeUsage {
			usage = usageOf(prompt, text, res)
		}
		// What true streaming already sent is not re-sent; only the tail is made up. With tools, true streaming never ran, so the full text is sent here. Same for the reasoning chain, which must be made up before the body — keeping the "think first, then answer" order.
		if res != nil && res.Reasoning != "" {
			if rest := remainingOf(res.Reasoning, res.EmittedReasoning); rest != "" {
				sse.SendReasoning(rest)
			}
		}
		// The tail must compare against **what was actually sent to the client**. Through the gate, res.Emitted contains the raw fence; prefix-comparing against it fails to match, and the whole tail would be dropped.
		if rest := remainingOf(text, sentText(res, gate)); rest != "" {
			sse.SendContent(rest)
		}
		if len(toolCalls) > 0 {
			sse.SendToolCalls(toolCalls)
		}
		sse.Finish(finish, usage)
		return
	}

	writeJSON(w, 200, map[string]interface{}{
		"id":      cid,
		"object":  "chat.completion",
		"created": created,
		"model":   modelName,
		"choices": []map[string]interface{}{{
			"index":         0,
			"message":       msg,
			"finish_reason": finish,
		}},
		"usage": usageOf(prompt, text, res),
	})
}

// usageOf is a convenience wrapper around buildUsageWithReasoning; res may be nil.
func usageOf(prompt, text string, res *StreamResult) map[string]int {
	r := ""
	if res != nil {
		r = res.Reasoning
	}
	return buildUsageWithReasoning(prompt, text, r, false)
}

// finishFor returns the finish_reason based on whether tool_calls exist.
func finishFor(toolCalls []ToolCall) string {
	if len(toolCalls) > 0 {
		return "tool_calls"
	}
	return "stop"
}

// assistantMessage assembles one assistant message body (text/tool calls/reasoning chain).
func assistantMessage(text string, toolCalls []ToolCall, res *StreamResult) map[string]interface{} {
	msg := map[string]interface{}{"role": "assistant"}
	if text != "" {
		msg["content"] = text
	} else {
		msg["content"] = nil
	}
	if res != nil && res.Reasoning != "" {
		msg["reasoning_content"] = res.Reasoning
	}
	if len(toolCalls) > 0 {
		msg["tool_calls"] = toolCalls
	}
	return msg
}

// remainingText returns the part of the final text not yet sent via onDelta. In true
// streaming usually only a tail bit or nothing; without true streaming, Emitted is empty and the full text is returned.
func remainingText(text string, res *StreamResult) string {
	if res == nil {
		return text
	}
	return remainingOf(text, res.Emitted)
}

// sentText returns the body actually sent to the client this time. Without the fence
// gate it's what the deltaTracker emitted; through the gate, the gate is authoritative —
// it withheld the fence, so it is not the same text as res.Emitted.
func sentText(res *StreamResult, gate *toolFenceGate) string {
	if gate != nil {
		return gate.Sent()
	}
	if res == nil {
		return ""
	}
	return res.Emitted
}

// remainingOf returns the not-yet-sent tail of full. With emitted empty, returns the full text.
func remainingOf(full, emitted string) string {
	if emitted == "" {
		return full
	}
	if strings.HasPrefix(full, emitted) {
		return full[len(emitted):]
	}
	// Prefix doesn't match (the upstream rewrote mid-stream); what was sent can't be taken back, and nothing more is sent to avoid duplication.
	return ""
}

// handleResponses implements OpenAI's /v1/responses (Codex CLI format).
func handleResponses(w http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(r.Body)
	if err != nil {
		writeJSON(w, 400, map[string]interface{}{"error": map[string]string{"message": err.Error()}})
		return
	}
	var req map[string]interface{}
	if err := json.Unmarshal(body, &req); err != nil {
		writeJSON(w, 400, map[string]interface{}{"error": map[string]string{"message": "invalid JSON"}})
		return
	}

	modelInput := getStr(req, "model")
	if modelInput == "" {
		modelInput = rtCfg().DefaultModel
	}
	modelName, modelCfg, err := resolveModel(modelInput)
	if err != nil {
		writeJSON(w, 400, map[string]interface{}{"error": map[string]string{"message": err.Error()}})
		return
	}

	var messages []map[string]interface{}
	if instr := getStr(req, "instructions"); instr != "" {
		messages = append(messages, map[string]interface{}{"role": "system", "content": instr})
	}

	switch input := req["input"].(type) {
	case string:
		messages = append(messages, map[string]interface{}{"role": "user", "content": input})
	case []interface{}:
		for _, raw := range input {
			switch item := raw.(type) {
			case string:
				messages = append(messages, map[string]interface{}{"role": "user", "content": item})
			case map[string]interface{}:
				if t := getStr(item, "type"); t == "function_call_output" {
					messages = append(messages, map[string]interface{}{
						"role":         "tool",
						"tool_call_id": getStr(item, "call_id"),
						"name":         getStr(item, "name"),
						"content":      getStr(item, "output"),
					})
					continue
				}
				role := getStr(item, "role")
				if role == "assistant" || (getStr(item, "type") == "message" && role == "assistant") {
					var textAcc strings.Builder
					var tcList []map[string]interface{}
					if cp, ok := item["content"].([]interface{}); ok {
						for _, c := range cp {
							cm, ok := c.(map[string]interface{})
							if !ok {
								continue
							}
							switch getStr(cm, "type") {
							case "output_text":
								textAcc.WriteString(getStr(cm, "text"))
							case "function_call":
								tcList = append(tcList, cm)
							}
						}
					} else if s, ok := item["content"].(string); ok {
						textAcc.WriteString(s)
					}
					m := map[string]interface{}{"role": "assistant", "content": textAcc.String()}
					if len(tcList) > 0 {
						var tcs []map[string]interface{}
						for i, tc := range tcList {
							id := getStr(tc, "call_id")
							if id == "" {
								id = fmt.Sprintf("call_%d", i)
							}
							tcs = append(tcs, map[string]interface{}{
								"id":   id,
								"type": "function",
								"function": map[string]interface{}{
									"name":      getStr(tc, "name"),
									"arguments": getStr(tc, "arguments"),
								},
							})
						}
						m["tool_calls"] = tcs
					}
					messages = append(messages, m)
				} else {
					if role == "" {
						role = "user"
					}
					content := contentToString(item["content"])
					messages = append(messages, map[string]interface{}{"role": role, "content": content})
				}
			}
		}
	}

	toolsRaw, _ := req["tools"].([]interface{})
	var tools []map[string]interface{}
	for _, t := range toolsRaw {
		tm, ok := t.(map[string]interface{})
		if !ok {
			continue
		}
		// Normalize Responses API tool shape to Chat Completions shape.
		if getStr(tm, "type") == "function" && tm["function"] == nil {
			tools = append(tools, map[string]interface{}{
				"type": "function",
				"function": map[string]interface{}{
					"name":        getStr(tm, "name"),
					"description": getStr(tm, "description"),
					"parameters":  tm["parameters"],
				},
			})
		} else {
			tools = append(tools, tm)
		}
	}

	if err := rejectUnsupported(req, messages); err != nil {
		writeJSON(w, 400, map[string]interface{}{"error": map[string]string{
			"message": err.Error(), "type": "invalid_request_error"}})
		return
	}

	images, err := collectImages(messages, "")
	if err != nil {
		writeJSON(w, 400, map[string]interface{}{"error": map[string]string{
			"message": err.Error(), "type": "invalid_request_error"}})
		return
	}

	prompt, latest := messagesToPrompt(messages, tools, req["tool_choice"])
	if strings.TrimSpace(prompt) == "" && len(images) == 0 {
		writeJSON(w, 400, map[string]interface{}{"error": map[string]string{"message": "empty input"}})
		return
	}

	stream, _ := req["stream"].(bool)
	rid := "resp_" + randHex(16)
	mid := "msg_" + randHex(12)

	// The Responses streaming protocol requires a response.output_item.added event declaring the item before sending output_text.delta on it; skipping it makes strict clients like Codex report "OutputTextDelta without active item". msgIndex/nextIdx assign each output item a number; ensureMsg lazily declares the message item (only on the first delta; a pure tool-call turn sends no empty message).
	msgIndex := -1
	nextIdx := 0
	var ensureMsg func()

	// Streaming must send the headers and response.created first so deltas can be pushed as
	// they arrive. The cost: once the stream opens, the HTTP status code is fixed; upstream
	// failures can only be reported via a response.failed event — the same trade-off as the /v1/chat/completions path.
	var writeEvent func(string, interface{})
	var emitDelta func(string)
	var gate *toolFenceGate
	var onDelta func(string)
	if stream {
		w.Header().Set("Content-Type", "text/event-stream")
		w.Header().Set("Cache-Control", "no-cache")
		w.Header().Set("X-Accel-Buffering", "no") // disables reverse-proxy SSE buffering, see sse.go
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.WriteHeader(200)
		flusher, _ := w.(http.Flusher)
		writeEvent = func(eventType string, payload interface{}) {
			pj, _ := json.Marshal(payload)
			fmt.Fprintf(w, "event: %s\ndata: %s\n\n", eventType, pj)
			if flusher != nil {
				flusher.Flush()
			}
		}
		writeEvent("response.created", map[string]interface{}{
			"type": "response.created",
			"response": map[string]interface{}{
				"id":     rid,
				"object": "response",
				"status": "in_progress",
				"model":  modelName,
				"output": []interface{}{},
			},
		})
		ensureMsg = func() {
			if msgIndex >= 0 {
				return
			}
			msgIndex = nextIdx
			nextIdx++
			writeEvent("response.output_item.added", map[string]interface{}{
				"type":         "response.output_item.added",
				"output_index": msgIndex,
				"item": map[string]interface{}{
					"id": mid, "type": "message", "role": "assistant",
					"status": "in_progress", "content": []interface{}{},
				},
			})
			writeEvent("response.content_part.added", map[string]interface{}{
				"type": "response.content_part.added", "item_id": mid,
				"output_index": msgIndex, "content_index": 0,
				"part": map[string]interface{}{"type": "output_text", "text": "", "annotations": []interface{}{}},
			})
		}
		emitDelta = func(d string) {
			ensureMsg()
			writeEvent("response.output_text.delta", map[string]interface{}{
				"type":          "response.output_text.delta",
				"item_id":       mid,
				"output_index":  msgIndex,
				"content_index": 0,
				"delta":         d,
			})
		}
		// Same fence gate as the chat path: with tools, only parts certainly outside the fence are let through.
		if len(tools) == 0 {
			onDelta = emitDelta
		} else {
			gate = newToolFenceGate(emitDelta)
			onDelta = gate.Push
		}
	}

	// onReasoning is nil: the Responses API has its own reasoning event shape, incompatible
	// with chat's reasoning_content; this path does not expose the reasoning chain for now.
	var text string
	var toolCalls []ToolCall
	var res *StreamResult
	if rtCfg().MultiTurn && len(images) == 0 && modelCfg.Tool == 0 {
		text, toolCalls, res, err = callGeminiConv(messages, modelCfg, tools, req["tool_choice"], onDelta, nil)
	} else {
		text, toolCalls, res, err = callGemini(prompt, latest, modelCfg, tools, images, onDelta, nil)
	}
	if err != nil {
		recordRequest("responses", modelName, prompt, "", res, 502, err.Error(), stream)
		if stream {
			writeEvent("response.failed", map[string]interface{}{
				"type": "response.failed",
				"response": map[string]interface{}{
					"id":     rid,
					"object": "response",
					"status": "failed",
					"model":  modelName,
					"error":  map[string]string{"message": err.Error()},
				},
			})
			return
		}
		if ptl, ok := err.(*PromptTooLongError); ok {
			// Report 400 explicitly rather than sending it and letting the upstream truncate the
			// user's question — that hands the client an off-topic 200 with no hint the request never got through.
			writeJSON(w, 400, map[string]interface{}{"error": map[string]string{
				"message": ptl.Error(), "type": "invalid_request_error",
				"code": "context_length_exceeded"}})
			return
		}
		if rle, ok := err.(*RateLimitError); ok {
			writeJSON(w, 429, map[string]interface{}{"error": map[string]string{
				"message": rle.Error(),
				"type":    "rate_limit_exceeded",
				"code":    "ip_slot_full",
			}})
			return
		}
		writeJSON(w, 502, map[string]interface{}{"error": map[string]string{"message": "upstream error: " + err.Error()}})
		return
	}

	var output []map[string]interface{}
	for _, tc := range toolCalls {
		output = append(output, map[string]interface{}{
			"type":      "function_call",
			"id":        tc.ID,
			"call_id":   tc.ID,
			"name":      tc.Function.Name,
			"arguments": tc.Function.Arguments,
			"status":    "completed",
		})
	}
	if text != "" || len(toolCalls) == 0 {
		output = append(output, map[string]interface{}{
			"type":   "message",
			"id":     mid,
			"role":   "assistant",
			"status": "completed",
			"content": []map[string]interface{}{{
				"type":        "output_text",
				"text":        text,
				"annotations": []interface{}{},
			}},
		})
	}

	recordRequest("responses", modelName, prompt, text, res, 200, "", stream)
	if stream {
		// Make up the tail the gate withheld or the prefix diff skipped, then send the terminal events.
		if rest := remainingOf(text, sentText(res, gate)); rest != "" {
			emitDelta(rest)
		}
		for _, item := range output {
			switch item["type"] {
			case "function_call":
				// Tool-call items must also be wrapped added → done, or Codex won't accept them.
				idx := nextIdx
				nextIdx++
				writeEvent("response.output_item.added", map[string]interface{}{
					"type": "response.output_item.added", "output_index": idx, "item": item,
				})
				writeEvent("response.function_call_arguments.done", map[string]interface{}{
					"type":      "response.function_call_arguments.done",
					"item_id":   item["id"],
					"call_id":   item["call_id"],
					"name":      item["name"],
					"arguments": item["arguments"],
				})
				writeEvent("response.output_item.done", map[string]interface{}{
					"type": "response.output_item.done", "output_index": idx, "item": item,
				})
			case "message":
				ensureMsg() // with a body but no delta, declare the message item here
				if cps, ok := item["content"].([]map[string]interface{}); ok {
					for ci, cp := range cps {
						writeEvent("response.output_text.done", map[string]interface{}{
							"type":          "response.output_text.done",
							"item_id":       item["id"],
							"output_index":  msgIndex,
							"content_index": ci,
							"text":          cp["text"],
						})
						writeEvent("response.content_part.done", map[string]interface{}{
							"type": "response.content_part.done", "item_id": item["id"],
							"output_index": msgIndex, "content_index": ci,
							"part": map[string]interface{}{"type": "output_text", "text": cp["text"], "annotations": []interface{}{}},
						})
					}
				}
				writeEvent("response.output_item.done", map[string]interface{}{
					"type": "response.output_item.done", "output_index": msgIndex, "item": item,
				})
			}
		}
		respObj := map[string]interface{}{
			"id":     rid,
			"object": "response",
			"status": "completed",
			"model":  modelName,
			"output": output,
			"usage":  buildUsage(prompt, text, true),
		}
		writeEvent("response.completed", map[string]interface{}{
			"type":     "response.completed",
			"response": respObj,
		})
		return
	}

	writeJSON(w, 200, map[string]interface{}{
		"id":         rid,
		"object":     "response",
		"created_at": time.Now().Unix(),
		"status":     "completed",
		"model":      modelName,
		"output":     output,
		"usage":      buildUsage(prompt, text, true),
	})
}
