package app

import (
	"encoding/json"
	"strings"
)

// Source is one cited source from a web search.
type Source struct {
	URL     string `json:"url"`
	Title   string `json:"title,omitempty"`
	Snippet string `json:"snippet,omitempty"`
}

// extractGrounding pulls the web-search sources out of the raw StreamGenerate response.
//
// Location: a frame's inner[4][0][2][1] is a set of grounding chunks; each chunk's [2]
// is the source list, and each source looks like [url, title, favicon, snippet]. Taken
// verbatim from packet captures, using the same wrb.fr → inner parsing path as
// textsInLine. Without web search this structure doesn't exist and nil is returned.
//
// URLs often carry a `#:~:text=` text-fragment anchor (Google search's "scroll to the
// specified text"); stripping it makes display cleaner.
func extractGrounding(raw string) []Source {
	var out []Source
	seen := map[string]bool{}
	for _, line := range strings.Split(raw, "\n") {
		if !strings.Contains(line, `"wrb.fr"`) || len(line) < 200 {
			continue
		}
		var arr []interface{}
		if json.Unmarshal([]byte(line), &arr) != nil || len(arr) == 0 {
			continue
		}
		first, ok := arr[0].([]interface{})
		if !ok || len(first) < 3 {
			continue
		}
		innerStr, ok := first[2].(string)
		if !ok {
			continue
		}
		var inner []interface{}
		if json.Unmarshal([]byte(innerStr), &inner) != nil || len(inner) <= 4 {
			continue
		}
		chunks := groundingChunks(inner)
		for _, c := range chunks {
			cl, ok := c.([]interface{})
			if !ok || len(cl) <= 2 {
				continue
			}
			srcs, ok := cl[2].([]interface{})
			if !ok {
				continue
			}
			for _, s := range srcs {
				sl, ok := s.([]interface{})
				if !ok || len(sl) < 2 {
					continue
				}
				url, _ := sl[0].(string)
				url = stripTextFragment(url)
				if url == "" || seen[url] {
					continue
				}
				title, _ := sl[1].(string)
				snippet := ""
				if len(sl) > 3 {
					snippet, _ = sl[3].(string)
				}
				seen[url] = true
				out = append(out, Source{URL: url, Title: title, Snippet: snippet})
			}
		}
	}
	return out
}

// groundingChunks returns inner[4][0][2][1]; nil if any level is missing.
func groundingChunks(inner []interface{}) []interface{} {
	f4, ok := inner[4].([]interface{})
	if !ok || len(f4) == 0 {
		return nil
	}
	node, ok := f4[0].([]interface{})
	if !ok || len(node) <= 2 {
		return nil
	}
	g, ok := node[2].([]interface{})
	if !ok || len(g) <= 1 {
		return nil
	}
	chunks, ok := g[1].([]interface{})
	if !ok {
		return nil
	}
	return chunks
}

// stripTextFragment removes a trailing `#:~:text=...` fragment anchor from a URL.
func stripTextFragment(u string) string {
	if i := strings.Index(u, "#:~:text="); i >= 0 {
		return u[:i]
	}
	return u
}
