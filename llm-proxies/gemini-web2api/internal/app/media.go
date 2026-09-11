package app

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"time"

	fhttp "github.com/bogdanfinn/fhttp"
)

// inner[49] media tool switch: when set, the server swaps in a backend model to generate the artifact.
const (
	toolImage  = 14 // image → Nano Banana
	toolMusic  = 21 // music → Lyria (~30 seconds)
	toolCanvas = 2  // canvas → immersive HTML document (inline in the response; no extra download)
	toolVideo  = 11 // video → Veo (async: submit, poll MUAZcd until done, then get the download link via hNvQHb)
)

// extractCanvasDoc pulls the generated HTML document out of a canvas (inner[49]=2) response.
//
// Unlike image/music: the document needs no separate download, it is inline in the
// frames — the immersive structure (the inner[4][0][30]… branch) contains a string
// shaped like "```html\n<!DOCTYPE html>…```". In streaming, the same document is re-sent cumulatively across frames; take the **longest** string containing DOCTYPE across all frames = the final complete version.
func extractCanvasDoc(raw string) string {
	best := ""
	var walk func(interface{})
	walk = func(o interface{}) {
		switch v := o.(type) {
		case string:
			if len(v) > len(best) && strings.Contains(v, "DOCTYPE") {
				best = v
			}
		case []interface{}:
			for _, x := range v {
				walk(x)
			}
		case map[string]interface{}:
			for _, x := range v {
				walk(x)
			}
		}
	}
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
			if !ok || len(row) < 3 {
				continue
			}
			payload, ok := row[2].(string)
			if !ok {
				continue
			}
			var inner interface{}
			if json.Unmarshal([]byte(payload), &inner) == nil {
				walk(inner)
			}
		}
	}
	return best
}

// downloadOPI is the mandatory opi parameter on the artifact download URL (the contribution one).
// Taken from the /app page; measured identical across two independent accounts, used as a global constant. The lh3 CDN image path doesn't need it.
const downloadOPI = "103135050"

// MediaArtifact is the raw bytes of one generated media artifact.
type MediaArtifact struct {
	Mime string
	Data []byte
}

// downloadCookieNames is the cookie whitelist the artifact download host accepts —
// exactly these 18 entries are what the browser sends it, all .google.com-scoped.
//
// Critical: sending the gemini/accounts host-specific cookies (__Host-1PLSID /
// __Host-GAPS / LSID / OSID / OTZ / COMPASS / _ga* etc.) along makes the download
// host's auth return 403 with a gzipped empty error page. Measured: only these 18
// entries get 200. This is one root cause of media-download 403s — unrelated to token freshness / TLS fingerprint / opi / any headers.
//
// The other root cause is cross-domain redirects: the image link
// (lh3.googleusercontent.com/gg-dl/…) 302s to work.fife.usercontent.google.com/rd-gg-dl/…,
// and http clients by default don't carry the Cookie header to the new domain, so the
var downloadCookieNames = map[string]bool{
	"HSID": true, "SSID": true, "APISID": true, "SAPISID": true,
	"__Secure-1PAPISID": true, "__Secure-3PAPISID": true,
	"SID": true, "__Secure-1PSID": true, "__Secure-3PSID": true,
	"GOOGLE_ABUSE_EXEMPTION": true, "NID": true,
	"__Secure-1PSIDTS": true, "__Secure-1PSIDRTS": true,
	"__Secure-3PSIDTS": true, "__Secure-3PSIDRTS": true,
	"SIDCC": true, "__Secure-1PSIDCC": true, "__Secure-3PSIDCC": true,
}

// filterDownloadCookies keeps only the 18 entries the download host accepts; nothing else is sent.
func filterDownloadCookies(cookie string) string {
	var kept []string
	for _, p := range strings.Split(cookie, ";") {
		p = strings.TrimSpace(p)
		i := strings.IndexByte(p, '=')
		if i <= 0 {
			continue
		}
		if downloadCookieNames[p[:i]] {
			kept = append(kept, p)
		}
	}
	return strings.Join(kept, "; ")
}

// fetchMediaArtifacts retrieves the media artifact bytes. cookie / sapisid / xsrf /
// proxyURL must be the same set as the generating call — the artifacts hang on that
//
// Image and music take different retrieval paths: images go through the lh3 CDN
// (link in the StreamGenerate response, follow the 302), music/video through
// contribution.usercontent.google.com/download (link in the hNvQHb history, single
func fetchMediaArtifacts(tool int, raw, cid, cookie, sapisid, xsrf, proxyURL, defaultMime string) ([]MediaArtifact, error) {
	if tool == toolImage {
		return fetchImageArtifacts(raw, cid, cookie, sapisid, xsrf, proxyURL, defaultMime)
	}
	// Music is ready almost immediately; video takes tens of seconds to minutes, so video polling gets a generous budget.
	maxPolls, interval := 6, 2*time.Second
	if tool == toolVideo {
		maxPolls, interval = 45, 8*time.Second // ~6 minutes
	}
	arts, err := fetchDownloadArtifacts(cid, cookie, sapisid, xsrf, proxyURL, defaultMime, maxPolls, interval)
	if err != nil {
		return arts, err
	}
	// Video attaches multiple download links in one hNvQHb response (presumably Veo's multiple candidates/encodings; meaning not rigorously verified) — keep only the
	// largest so the client doesn't get two videos at once. Telling them apart needs a clean egress to verify (see CLAUDE.md).
	if tool == toolVideo && len(arts) > 1 {
		largest := arts[0]
		for _, a := range arts[1:] {
			if len(a.Data) > len(largest.Data) {
				largest = a
			}
		}
		arts = []MediaArtifact{largest}
	}
	return arts, nil
}

// fetchImageArtifacts retrieves generated images. The links are in the StreamGenerate
// response; if none can be extracted, fall back to polling hNvQHb. Downloads go through mediaGetFollow (follows 302s and re-sends cookies on every hop).
func fetchImageArtifacts(raw, cid, cookie, sapisid, xsrf, proxyURL, defaultMime string) ([]MediaArtifact, error) {
	urls := collectImageURLs(raw)
	if len(urls) == 0 {
		for i := 0; i < 6; i++ {
			if body, err := pollHistoryRaw(cid, cookie, sapisid, xsrf, proxyURL); err == nil {
				if u := collectImageURLs(body); len(u) > 0 {
					urls = u
					break
				}
			}
			time.Sleep(2 * time.Second)
		}
	}
	if len(urls) == 0 {
		return nil, fmt.Errorf("响应里没有图片 CDN 链接")
	}
	var arts []MediaArtifact
	for _, u := range urls {
		mime, data, err := downloadBytes(imageFullResURL(u), cookie, proxyURL, defaultMime)
		if err != nil {
			return arts, err
		}
		// The same image may appear with different tokens in the response (different
		// resolutions/thumbnails); dedupe by bytes so the client doesn't get several identical images.
		if !artifactSeen(arts, data) {
			arts = append(arts, MediaArtifact{Mime: mime, Data: data})
		}
	}
	return arts, nil
}

// imageFullResURL adds a size parameter to the image CDN link to get the original.
// A plain gg-dl link defaults to a ~500px thumbnail (issue #14: 1365×768 in the
// console; changing the link's =s1024-rj to =s2048-rj yields bigger). The
// googleusercontent convention appends =sN for the max edge, =s0 for the original
//
// Options live in the last path segment, separated by =; the gg-dl token is
// base64url without =, so cut at the = in the last path segment, drop existing
func imageFullResURL(u string) string {
	i := strings.LastIndexByte(u, '/')
	if i < 0 {
		return u + "=s0"
	}
	seg := u[i+1:]
	if j := strings.IndexByte(seg, '='); j >= 0 {
		u = u[:i+1] + seg[:j]
	}
	return u + "=s0"
}

// fetchDownloadArtifacts retrieves music/video: poll hNvQHb until the response_data download link appears, then download.
// The gg-dl (lh3) and temp_data links are previews; only the response_data one yields the real bytes.
func fetchDownloadArtifacts(cid, cookie, sapisid, xsrf, proxyURL, defaultMime string,
	maxPolls int, interval time.Duration) ([]MediaArtifact, error) {
	if cid == "" {
		return nil, fmt.Errorf("没拿到会话 id，无法定位产物")
	}
	var dlURLs []string
	for i := 0; i < maxPolls; i++ {
		if body, err := pollHistoryRaw(cid, cookie, sapisid, xsrf, proxyURL); err == nil {
			if picked := pickResponseDataURLs(collectDownloadURLs(body)); len(picked) > 0 {
				dlURLs = picked
				break
			}
			// When a video is rejected by content policy, hNvQHb says "I can't generate that video" — don't wait out the timeout.
			if strings.Contains(body, "can't generate that video") {
				return nil, fmt.Errorf("视频被内容政策拒绝（换个 prompt 再试）")
			}
		}
		time.Sleep(interval)
	}
	if len(dlURLs) == 0 {
		return nil, fmt.Errorf("hNvQHb 里没等到可下载的产物链接（response_data）")
	}
	var arts []MediaArtifact
	for _, u := range dlURLs {
		// The contribution link needs filename / opi appended.
		if !strings.Contains(u, "opi=") {
			sep := "?"
			if strings.Contains(u, "?") {
				sep = "&"
			}
			u += sep + "filename=artifact&opi=" + downloadOPI
		}
		mime, data, err := downloadBytes(u, cookie, proxyURL, defaultMime)
		if err != nil {
			return arts, err
		}
		if !artifactSeen(arts, data) {
			arts = append(arts, MediaArtifact{Mime: mime, Data: data})
		}
	}
	return arts, nil
}

// pollHistoryRaw calls hNvQHb once to fetch the conversation history and returns the raw response body.
func pollHistoryRaw(cid, cookie, sapisid, xsrf, proxyURL string) (string, error) {
	inner, _ := json.Marshal([]interface{}{cid, 10, nil, 1, []interface{}{0}, []interface{}{4}, nil, 1})
	freq, _ := json.Marshal([]interface{}{[]interface{}{[]interface{}{"hNvQHb", string(inner), nil, "generic"}}})
	form := url.Values{}
	form.Set("f.req", string(freq))
	if xsrf != "" {
		form.Set("at", xsrf)
	}
	reqid := time.Now().UnixNano() % 1000000
	endpoint := fmt.Sprintf(
		"https://gemini.google.com/_/BardChatUi/data/batchexecute?rpcids=hNvQHb&bl=%s&hl=en&_reqid=%d&rt=c",
		currentBL(proxyURL), reqid)

	// batchexecute carries no model header; the rest (cookie / SAPISIDHASH / x-same-domain) matches the main request.
	headers := buildGeminiHeaders(cookie, sapisid, "")
	delete(headers, "x-goog-ext-525001261-jspb")

	status, _, body, err := uploadPost(endpoint, headers, []byte(form.Encode()), proxyURL)
	if err != nil {
		return "", err
	}
	if status != 200 {
		return "", fmt.Errorf("hNvQHb HTTP %d", status)
	}
	return string(body), nil
}

// deleteConversation removes a conversation left on gemini.google.com (#19).
//
// Protocol taken verbatim from packet captures: rpc GzXR5e, parameter ["<cid>"], mode "generic", with at=XSRF.
//   f.req=[[["GzXR5e","[\"c_xxx\"]",null,"generic"]]]&at=<xsrf>
// Only works signed in (anonymous has no XSRF and the conversation isn't tied to an
// account). Best-effort: a failed delete only logs; the response already returned to the client is unaffected.
func deleteConversation(cid, cookie, sapisid, xsrf, proxyURL string) {
	inner, _ := json.Marshal([]interface{}{cid})
	freq, _ := json.Marshal([]interface{}{[]interface{}{[]interface{}{"GzXR5e", string(inner), nil, "generic"}}})
	form := url.Values{}
	form.Set("f.req", string(freq))
	form.Set("at", xsrf)
	reqid := time.Now().UnixNano() % 1000000
	endpoint := fmt.Sprintf(
		"https://gemini.google.com/_/BardChatUi/data/batchexecute?rpcids=GzXR5e&bl=%s&hl=en&_reqid=%d&rt=c",
		currentBL(proxyURL), reqid)
	headers := buildGeminiHeaders(cookie, sapisid, "")
	delete(headers, "x-goog-ext-525001261-jspb")
	status, _, body, err := uploadPost(endpoint, headers, []byte(form.Encode()), proxyURL)
	if err != nil {
		logf("[autodel] 删会话 %s 失败: %v", cid, err)
		return
	}
	if status != 200 {
		logf("[autodel] 删会话 %s 返回 HTTP %d: %s", cid, status, truncate(string(body), 120))
		return
	}
	logf("[autodel] 已删会话 %s", cid)
}

// walkFramesForURLs recursively walks all strings in the batchexecute envelope and
//
// Response shape: each line [["wrb.fr","<rpc>","<json string>",…], the real data
// buried in that inner json string at an unspecified depth. JSON parsing is
// mandatory, not a regex over the raw — the raw is **double-escaped** JSON; slashes
// and boundaries in URLs differ from the unescaped form, so a regex grabs too many
func walkFramesForURLs(raw string, want func(string) bool) []string {
	seen := map[string]bool{}
	var out []string
	var walk func(interface{})
	walk = func(o interface{}) {
		switch v := o.(type) {
		case string:
			if want(v) && !seen[v] {
				seen[v] = true
				out = append(out, v)
			}
		case []interface{}:
			for _, x := range v {
				walk(x)
			}
		case map[string]interface{}:
			for _, x := range v {
				walk(x)
			}
		}
	}
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
			if !ok || len(row) < 3 {
				continue
			}
			payload, ok := row[2].(string)
			if !ok {
				continue
			}
			var inner interface{}
			if json.Unmarshal([]byte(payload), &inner) == nil {
				walk(inner)
			}
		}
	}
	return out
}

// collectDownloadURLs digs all contribution download links out of the response (for music/video).
func collectDownloadURLs(raw string) []string {
	return walkFramesForURLs(raw, func(s string) bool {
		return strings.Contains(s, "contribution.usercontent.google.com/download")
	})
}

// collectImageURLs digs all generated-image CDN links out of the response (gg-dl from
// the first frame, gg from hNvQHb). This plain link returns the real image on a plain
// GET — do NOT add the rd- prefix (that rd- in captures is **a different token set**; building rd- with this link's token 400s).
func collectImageURLs(raw string) []string {
	return walkFramesForURLs(raw, func(s string) bool {
		return strings.Contains(s, "lh3.googleusercontent.com/gg-dl/") ||
			strings.Contains(s, "lh3.googleusercontent.com/gg/")
	})
}

// pickResponseDataURLs picks the actually downloadable kind from a pile of download links
// (the c parameter decodes to contain "response_data"). The other two kinds (temp_data
func pickResponseDataURLs(urls []string) []string {
	var out []string
	for _, u := range urls {
		if downloadIsResponseData(u) {
			out = append(out, u)
		}
	}
	return out
}

// downloadIsResponseData decodes the c parameter's base64 and checks the protobuf for
// the "response_data" marker. No bare substring matching on the base64 blob: that is alignment-sensitive and misses on a different prefix.
func downloadIsResponseData(rawURL string) bool {
	u, err := url.Parse(rawURL)
	if err != nil {
		return false
	}
	c := u.Query().Get("c")
	if c == "" {
		return false
	}
	dec, err := base64.RawURLEncoding.DecodeString(strings.TrimRight(c, "="))
	if err != nil {
		dec, err = base64.StdEncoding.DecodeString(c)
		if err != nil {
			return false
		}
	}
	return strings.Contains(string(dec), "response_data")
}

// downloadBytes GETs an artifact link, follows redirects re-sending the cookie subset on
// every hop, and returns content-type and raw bytes. Both image links (302) and contribution links (single 200) go through this.
func downloadBytes(rawURL, cookie, proxyURL, defaultMime string) (string, []byte, error) {
	headers := map[string]string{
		"Cookie":  filterDownloadCookies(cookie),
		"Origin":  "https://gemini.google.com",
		"Referer": "https://gemini.google.com/",
		"Accept":  "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
	}
	status, respHead, body, err := mediaGetFollow(rawURL, headers, proxyURL)
	if err != nil {
		return "", nil, err
	}
	if status != 200 {
		return "", nil, fmt.Errorf("下载产物 HTTP %d（%d 字节）", status, len(body))
	}
	mime := respHead["content-type"]
	if i := strings.IndexByte(mime, ';'); i >= 0 {
		mime = strings.TrimSpace(mime[:i])
	}
	if mime == "" || strings.HasPrefix(mime, "text/html") {
		mime = defaultMime
	}
	return mime, body, nil
}

// mediaGetFollow manually follows redirects (at most 6 hops), re-sending the same
//
// Why not the client's built-in following: image links 302 cross-domain
// (lh3 → work.fife.usercontent.google.com), and http clients, for safety, don't carry
// the Cookie header to the new domain, so the redirect target gets no cookie and 403s. Manual following with a per-hop cookie re-send passes. Both clients are configured with "don't auto-follow" anyway.
func mediaGetFollow(rawURL string, headers map[string]string, proxyURL string) (int, map[string]string, []byte, error) {
	cur := rawURL
	for hop := 0; hop < 6; hop++ {
		status, respHead, body, err := mediaGetOnce(cur, headers, proxyURL)
		if err != nil {
			return status, respHead, body, err
		}
		if status >= 300 && status < 400 {
			loc := respHead["location"]
			if loc == "" {
				return status, respHead, body, nil
			}
			next, err := resolveRef(cur, loc)
			if err != nil {
				return status, respHead, body, err
			}
			cur = next
			continue
		}
		return status, respHead, body, nil
	}
	return 0, nil, nil, fmt.Errorf("下载重定向次数过多")
}

// resolveRef resolves the Location against the current URL (mostly absolute, but relative works too).
func resolveRef(base, ref string) (string, error) {
	b, err := url.Parse(base)
	if err != nil {
		return "", err
	}
	r, err := url.Parse(ref)
	if err != nil {
		return "", err
	}
	return b.ResolveReference(r).String(), nil
}

// mediaGetOnce sends one GET without following redirects, returning the response
// headers too (content-type / location are needed). Proxy → stdlib, no proxy →
func mediaGetOnce(rawURL string, headers map[string]string, proxyURL string) (int, map[string]string, []byte, error) {
	if proxyURL != "" {
		req, err := http.NewRequest("GET", rawURL, nil)
		if err != nil {
			return 0, nil, nil, err
		}
		applyChromeHeaders(req)
		for k, v := range headers {
			req.Header.Set(k, v)
		}
		resp, err := getStdlibClient(proxyURL).Do(req)
		if err != nil {
			return 0, nil, nil, err
		}
		defer resp.Body.Close()
		b, err := io.ReadAll(resp.Body)
		return resp.StatusCode, flattenHeaders(resp.Header), b, err
	}
	req, err := fhttp.NewRequest("GET", rawURL, nil)
	if err != nil {
		return 0, nil, nil, err
	}
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	resp, err := getTLSClient().Do(req)
	if err != nil {
		return 0, nil, nil, err
	}
	defer resp.Body.Close()
	b, err := io.ReadAll(resp.Body)
	return resp.StatusCode, flattenFHeaders(resp.Header), b, err
}

func flattenHeaders(h http.Header) map[string]string {
	m := map[string]string{}
	for k := range h {
		m[strings.ToLower(k)] = h.Get(k)
	}
	return m
}

func flattenFHeaders(h fhttp.Header) map[string]string {
	m := map[string]string{}
	for k := range h {
		m[strings.ToLower(k)] = h.Get(k)
	}
	return m
}

// extractConversationID pulls the conversation id (the frame's [1][0]) from a
// StreamGenerate response. Retrieving music/video artifacts needs it to fetch this
func extractConversationID(raw string) string {
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
			var inner []interface{}
			if json.Unmarshal([]byte(payload), &inner) != nil || len(inner) < 2 {
				continue
			}
			meta, ok := inner[1].([]interface{})
			if ok && len(meta) > 0 {
				if cid, ok := meta[0].(string); ok && cid != "" {
					return cid
				}
			}
		}
	}
	return ""
}

// artifactSeen reports whether these bytes were already collected (compared by content, dropping same-image-different-token duplicates).
func artifactSeen(arts []MediaArtifact, data []byte) bool {
	for _, a := range arts {
		if bytes.Equal(a.Data, data) {
			return true
		}
	}
	return false
}

// appendArtifactMarkdown turns artifact bytes into base64 data URLs appended after
// the body. Images use markdown image syntax (most chat UIs render it directly); the rest (audio) uses link syntax.
func appendArtifactMarkdown(text string, arts []MediaArtifact) string {
	var b strings.Builder
	b.WriteString(text)
	for _, a := range arts {
		if b.Len() > 0 {
			b.WriteString("\n\n")
		}
		dataURL := "data:" + a.Mime + ";base64," + base64.StdEncoding.EncodeToString(a.Data)
		if strings.HasPrefix(a.Mime, "image/") {
			b.WriteString("![image](" + dataURL + ")")
		} else {
			b.WriteString("[audio](" + dataURL + ")")
		}
	}
	return b.String()
}

// dataURLRe matches one whole base64 data URL.
var dataURLRe = regexp.MustCompile(`data:([-\w.+/]+);base64,[A-Za-z0-9+/=]+`)

// stripDataURLs strips base64 data URLs from text, leaving a short placeholder. Used
// when counting tokens / recording length — one image's base64 is millions of
// characters; billing it means charging the user for invisible binary, and downstream newapi charges by output token. The artifact itself is still returned in content.
func stripDataURLs(text string) string {
	return dataURLRe.ReplaceAllString(text, "data:$1;base64,<omitted>")
}
