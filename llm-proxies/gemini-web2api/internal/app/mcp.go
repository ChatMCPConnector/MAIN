package app

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
)

// MCP (Model Context Protocol) server: exposes the Gemini web app's web search as a
// web_search tool that MCP clients like Claude Desktop / Claude Code / Cursor can call.
//
// Transport is HTTP (Streamable HTTP), mounted at /mcp on the backend's existing
// --port, in the same process and on the same port as the OpenAI interface — once
// deployed as a server, remote clients just connect to the URL, reusing the existing
// account pool / proxy pool / rate limiting. (No stdio-style transport where the
// client spawns a local subprocess.)
//
// Hand-written JSON-RPC 2.0 instead of a third-party SDK: there's just one tool and
// the protocol surface is tiny (initialize / tools/list / tools/call), so hand-writing
// adds no dependencies and matches the single-binary style.
//
// Search goes through streamGenerate, reusing the existing proxy pool / rate
// limiting / retry / anti-blocking for free. Anonymous access suffices for search,
// so there is no dependency on the cookie pool.

const mcpProtocolVersion = "2025-06-18"

type rpcRequest struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      json.RawMessage `json:"id,omitempty"`
	Method  string          `json:"method"`
	Params  json.RawMessage `json:"params,omitempty"`
}

type rpcResponse struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      json.RawMessage `json:"id"`
	Result  interface{}     `json:"result,omitempty"`
	Error   *rpcError       `json:"error,omitempty"`
}

type rpcError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

// handleMCPHTTP is the HTTP transport for MCP (Streamable HTTP), mounted at `/mcp`
// on the backend, in the same process and on the same port as the OpenAI interface,
// reusing the existing account pool / proxy pool / rate limiting.
//
// The client POSTs a JSON-RPC message, we reply with a single application/json
// response. The tool use case is pure request-response and needs no server-initiated
// push, so no SSE stream is opened: GET directly returns 405.
// Notifications (no id) get a 202 empty body per spec.
func handleMCPHTTP(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodOptions:
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "POST, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization, Mcp-Session-Id, MCP-Protocol-Version")
		w.WriteHeader(http.StatusNoContent)
		return
	case http.MethodGet:
		// no server-initiated SSE stream is offered; the spec allows this response.
		w.Header().Set("Allow", "POST")
		http.Error(w, "this MCP endpoint is POST-only (no server-initiated stream)", http.StatusMethodNotAllowed)
		return
	case http.MethodPost:
		// handled below
	default:
		w.Header().Set("Allow", "POST")
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	body, err := io.ReadAll(io.LimitReader(r.Body, 8<<20))
	if err != nil {
		writeMCPHTTPError(w, nil, -32700, "read error")
		return
	}
	var req rpcRequest
	if json.Unmarshal(body, &req) != nil {
		writeMCPHTTPError(w, nil, -32700, "parse error")
		return
	}
	resp := dispatchMCP(&req)
	if resp == nil {
		w.WriteHeader(http.StatusAccepted) // notification: no response body
		return
	}
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Content-Type", "application/json")
	b, _ := json.Marshal(resp)
	w.Write(b)
}

func writeMCPHTTPError(w http.ResponseWriter, id json.RawMessage, code int, msg string) {
	w.Header().Set("Content-Type", "application/json")
	b, _ := json.Marshal(rpcResponse{JSONRPC: "2.0", ID: id, Error: &rpcError{Code: code, Message: msg}})
	w.Write(b)
}

func dispatchMCP(req *rpcRequest) *rpcResponse {
	// messages without an id are notifications (notifications/initialized etc.), no response is sent.
	if len(req.ID) == 0 {
		return nil
	}
	ok := func(result interface{}) *rpcResponse {
		return &rpcResponse{JSONRPC: "2.0", ID: req.ID, Result: result}
	}
	fail := func(code int, msg string) *rpcResponse {
		return &rpcResponse{JSONRPC: "2.0", ID: req.ID, Error: &rpcError{Code: code, Message: msg}}
	}

	switch req.Method {
	case "initialize":
		// echo back the protocol version the client requested (fall back to ours if absent).
		ver := mcpProtocolVersion
		var p struct {
			ProtocolVersion string `json:"protocolVersion"`
		}
		if json.Unmarshal(req.Params, &p) == nil && p.ProtocolVersion != "" {
			ver = p.ProtocolVersion
		}
		return ok(map[string]interface{}{
			"protocolVersion": ver,
			"capabilities":    map[string]interface{}{"tools": map[string]interface{}{}},
			"serverInfo":      map[string]interface{}{"name": "gemini-search-mcp", "version": Version},
		})

	case "tools/list":
		return ok(map[string]interface{}{"tools": []interface{}{webSearchToolDef()}})

	case "tools/call":
		var p struct {
			Name      string `json:"name"`
			Arguments struct {
				Query string `json:"query"`
			} `json:"arguments"`
		}
		if json.Unmarshal(req.Params, &p) != nil {
			return fail(-32602, "invalid params")
		}
		if p.Name != "web_search" {
			return fail(-32602, "unknown tool: "+p.Name)
		}
		query := strings.TrimSpace(p.Arguments.Query)
		if query == "" {
			return ok(toolTextError("query must not be empty"))
		}
		text, err := mcpWebSearch(query)
		if err != nil {
			return ok(toolTextError("search failed: " + err.Error()))
		}
		return ok(map[string]interface{}{
			"content": []interface{}{map[string]interface{}{"type": "text", "text": text}},
		})

	case "ping":
		return ok(map[string]interface{}{})

	default:
		return fail(-32601, "method not found: "+req.Method)
	}
}

// webSearchToolDef is the definition of the web_search tool (with JSON Schema).
func webSearchToolDef() map[string]interface{} {
	return map[string]interface{}{
		"name": "web_search",
		"description": "Search the web via Google Gemini and return a synthesized answer " +
			"with source links. Use for current events, facts, or anything needing " +
			"up-to-date information from the internet.",
		"inputSchema": map[string]interface{}{
			"type": "object",
			"properties": map[string]interface{}{
				"query": map[string]interface{}{
					"type":        "string",
					"description": "The search query or question to research.",
				},
			},
			"required": []interface{}{"query"},
		},
	}
}

// mcpWebSearch performs one web search and returns the "answer + source list" text.
func mcpWebSearch(query string) (string, error) {
	mc, ok := Models[rtCfg().DefaultModel]
	if !ok {
		mc = Models["gemini-3.6-flash"]
	}
	res, err := streamGenerate(query, query, mc, nil, nil)
	if err != nil {
		return "", err
	}
	text := extractResponseText(res.Raw)
	if text == "" {
		return "", fmt.Errorf("upstream returned no content")
	}
	sources := extractGrounding(res.Raw)
	var b strings.Builder
	b.WriteString(text)
	if len(sources) > 0 {
		b.WriteString("\n\n---\nSources:\n")
		for i, s := range sources {
			title := s.Title
			if title == "" {
				title = s.URL
			}
			fmt.Fprintf(&b, "%d. %s — %s\n", i+1, title, s.URL)
		}
	}
	return b.String(), nil
}

func toolTextError(msg string) map[string]interface{} {
	return map[string]interface{}{
		"content": []interface{}{map[string]interface{}{"type": "text", "text": msg}},
		"isError": true,
	}
}
