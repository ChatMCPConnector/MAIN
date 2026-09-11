package app

import (
	"encoding/json"
	"fmt"
	"net/http"
)

// sseWriter writes chat.completion.chunk in OpenAI-spec order:
// first delta{role} → several delta{content} → delta{} + finish_reason → optional usage → [DONE].
//
// Headers are sent lazily: WriteHeader(200) happens only when the first chunk is
// actually written. This way, if the upstream fails before the first byte, we can
// still fall back to a normal 502 JSON instead of leaving the client with half a stream.
type sseWriter struct {
	w       http.ResponseWriter
	flusher http.Flusher
	id      string
	created int64
	model   string
	started bool
}

func newSSEWriter(w http.ResponseWriter, id string, created int64, model string) *sseWriter {
	f, _ := w.(http.Flusher)
	return &sseWriter{w: w, flusher: f, id: id, created: created, model: model}
}

func (s *sseWriter) Started() bool { return s.started }

// start sends the SSE response headers and the first delta{"role":"assistant"} chunk. Idempotent.
func (s *sseWriter) start() {
	if s.started {
		return
	}
	s.started = true
	s.w.Header().Set("Content-Type", "text/event-stream")
	s.w.Header().Set("Cache-Control", "no-cache")
	s.w.Header().Set("Connection", "keep-alive")
	// disable full buffering of SSE by reverse proxies (nginx etc.): without this header
	// a directly connected client sees streaming, but through a reverse proxy it gets
	// buffered up and delivered in one blob (that's how Dify-style setups turn non-streaming).
	s.w.Header().Set("X-Accel-Buffering", "no")
	s.w.Header().Set("Access-Control-Allow-Origin", "*")
	s.w.WriteHeader(200)
	s.chunk(map[string]interface{}{"role": "assistant"}, nil, nil)
}

func (s *sseWriter) chunk(delta map[string]interface{}, finish interface{}, usage map[string]int) {
	c := map[string]interface{}{
		"id":      s.id,
		"object":  "chat.completion.chunk",
		"created": s.created,
		"model":   s.model,
		"choices": []map[string]interface{}{{
			"index":         0,
			"delta":         delta,
			"finish_reason": finish,
		}},
	}
	if usage != nil {
		c["usage"] = usage
	}
	b, _ := json.Marshal(c)
	fmt.Fprintf(s.w, "data: %s\n\n", b)
	if s.flusher != nil {
		s.flusher.Flush()
	}
}

// SendContent sends a content delta, for direct use by streamGenerate's onDelta callback.
// SendReasoning sends reasoning-chain deltas. The upstream pushes the reasoning chain
// before starting the content, so the client sees the "thinking process" first and
// then the answer, matching the web app's behavior.
func (s *sseWriter) SendReasoning(delta string) {
	if delta == "" {
		return
	}
	s.start()
	s.chunk(map[string]interface{}{"reasoning_content": delta}, nil, nil)
}

func (s *sseWriter) SendContent(delta string) {
	if delta == "" {
		return
	}
	s.start()
	s.chunk(map[string]interface{}{"content": delta}, nil, nil)
}

func (s *sseWriter) SendToolCalls(tcs []ToolCall) {
	s.start()
	// every tool_call in a streaming delta must carry an index; clients use it to
	// reassemble the sharded tool_call (OpenAI streaming spec requirement).
	// The ToolCall struct itself has no index, so we fill it in sequentially here.
	out := make([]map[string]interface{}, len(tcs))
	for i, tc := range tcs {
		out[i] = map[string]interface{}{
			"index": i,
			"id":    tc.ID,
			"type":  tc.Type,
			"function": map[string]interface{}{
				"name":      tc.Function.Name,
				"arguments": tc.Function.Arguments,
			},
		}
	}
	s.chunk(map[string]interface{}{"tool_calls": out}, nil, nil)
}

// Finish wraps up: empty delta + finish_reason, an optional usage chunk, then [DONE].
func (s *sseWriter) Finish(reason string, usage map[string]int) {
	s.start()
	s.chunk(map[string]interface{}{}, reason, nil)
	if usage != nil {
		// OpenAI's usage chunk: choices is an empty array
		c := map[string]interface{}{
			"id": s.id, "object": "chat.completion.chunk",
			"created": s.created, "model": s.model,
			"choices": []map[string]interface{}{},
			"usage":   usage,
		}
		b, _ := json.Marshal(c)
		fmt.Fprintf(s.w, "data: %s\n\n", b)
	}
	fmt.Fprintf(s.w, "data: [DONE]\n\n")
	if s.flusher != nil {
		s.flusher.Flush()
	}
}

// Fail is used when an error occurs after the stream has already opened: send a chunk
// carrying the error, then wrap up. The HTTP status code is already 200 and can't be changed.
func (s *sseWriter) Fail(err error) {
	s.start()
	c := map[string]interface{}{
		"id": s.id, "object": "chat.completion.chunk",
		"created": s.created, "model": s.model,
		"choices": []map[string]interface{}{},
		"error":   map[string]string{"message": err.Error(), "type": "upstream_error"},
	}
	b, _ := json.Marshal(c)
	fmt.Fprintf(s.w, "data: %s\n\n", b)
	fmt.Fprintf(s.w, "data: [DONE]\n\n")
	if s.flusher != nil {
		s.flusher.Flush()
	}
}
