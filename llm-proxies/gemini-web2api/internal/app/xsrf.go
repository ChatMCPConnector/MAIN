package app

import (
	"crypto/sha1"
	"encoding/hex"
	"fmt"
	"io"
	"net/http"
	"regexp"
	"strings"
	"sync"
	"time"

	fhttp "github.com/bogdanfinn/fhttp"
)

// When login cookies are present, Gemini requires batchexecute requests to carry an
// extra form field "at" (the XSRF token); without it you get an immediate 400 with a
// body like [["er",...,400,...,[{"48448350":["xsrf", ...]}]]].
// Anonymous requests don't need it, which is why this pitfall stayed hidden — the
// moment a valid cookie is attached, every request starts failing.
//
// The token comes from "SNlM0e":"<token>:<millisecond timestamp>" in the /app page
// HTML and is bound to the cookie session, so it is cached per cookie. Observed in
// practice: the same token can be reused; once expired the server still returns the
// xsrf error, and the caller must invalidate and fetch a fresh one on seeing it.
var (
	xsrfMu    sync.Mutex
	xsrfCache = map[string]xsrfEntry{}
)

type xsrfEntry struct {
	token   string
	pushID  string // Push-ID header used for file uploads
	pctx    string // X-Client-Pctx header used for file uploads
	fetched time.Time
}

// The page doesn't state an expiry for the token, so re-fetch periodically with a conservative TTL.
const xsrfTTL = 20 * time.Minute

var snlm0eRe = regexp.MustCompile(`"SNlM0e":"([^"]{10,200})"`)

// Two page parameters needed for uploads, extracted from the same page as the XSRF token to save one page request.
var pushIDRe = regexp.MustCompile(`"qKIAYe":"([^"]{4,400})"`)

var pctxRe = regexp.MustCompile(`"Ylro7b":"([^"]{4,400})"`)

// cookieKey uses a short digest of the cookie as cache key, avoiding the full credential string in a map key.
func cookieKey(cookie string) string {
	sum := sha1.Sum([]byte(cookie))
	return hex.EncodeToString(sum[:8])
}

// invalidateXSRF drops the cached token for a cookie; the next fetch re-fetches the page.
func invalidateXSRF(cookie string) {
	if cookie == "" {
		return
	}
	xsrfMu.Lock()
	delete(xsrfCache, cookieKey(cookie))
	xsrfMu.Unlock()
}

// getXSRF returns the XSRF token for a cookie; a cache hit within TTL is returned directly.
// An empty cookie (anonymous) yields an empty string — anonymous requests don't need this field.
func getXSRF(cookie, proxyURL string) (string, error) {
	if cookie == "" {
		return "", nil
	}
	key := cookieKey(cookie)

	xsrfMu.Lock()
	if e, ok := xsrfCache[key]; ok && time.Since(e.fetched) < xsrfTTL {
		xsrfMu.Unlock()
		return e.token, nil
	}
	xsrfMu.Unlock()

	e, err := fetchAppTokens(cookie, proxyURL)
	if err != nil {
		return "", err
	}
	xsrfMu.Lock()
	xsrfCache[key] = e
	xsrfMu.Unlock()
	return e.token, nil
}

// getUploadTokens returns the Push-ID / X-Client-Pctx needed for uploads, from the same cache as the XSRF token.
func getUploadTokens(cookie, proxyURL string) (pushID, pctx string, err error) {
	key := cookieKey(cookie)

	xsrfMu.Lock()
	if e, ok := xsrfCache[key]; ok && time.Since(e.fetched) < xsrfTTL {
		xsrfMu.Unlock()
		return e.pushID, e.pctx, nil
	}
	xsrfMu.Unlock()

	e, err := fetchAppTokens(cookie, proxyURL)
	if err != nil {
		return "", "", err
	}
	xsrfMu.Lock()
	xsrfCache[key] = e
	xsrfMu.Unlock()
	return e.pushID, e.pctx, nil
}

// fetchAppPage fetches the HTML of gemini.google.com/app.
// It uses the same egress (proxy) as the main request: with a proxy configured it goes
// through stdlib, without one through tls-client, so the token from the page and the
// subsequent requests don't come from two different IPs.
// An empty cookie means an anonymous fetch (the page still returns, just without logged-in fields).
func fetchAppPage(cookie, proxyURL string) ([]byte, error) {
	const pageURL = "https://gemini.google.com/u/1/app"
	headers := map[string]string{
		"Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
		"Accept-Language": "en-US,en;q=0.9",
	}
	if cookie != "" {
		headers["Cookie"] = cookie
	}

	var body []byte
	if proxyURL != "" {
		req, err := http.NewRequest("GET", pageURL, nil)
		if err != nil {
			return nil, err
		}
		applyChromeHeaders(req)
		for k, v := range headers {
			req.Header.Set(k, v)
		}
		resp, err := getStdlibClient(proxyURL).Do(req)
		if err != nil {
			return nil, err
		}
		defer resp.Body.Close()
		if resp.StatusCode == 301 || resp.StatusCode == 302 || resp.StatusCode == 307 {
			loc := resp.Header.Get("Location")
			if strings.HasPrefix(loc, "https://gemini.google.com") {
				req2, err2 := http.NewRequest("GET", loc, nil)
				if err2 == nil {
					applyChromeHeaders(req2)
					for k, v := range headers {
						req2.Header.Set(k, v)
					}
					resp2, err2 := getStdlibClient(proxyURL).Do(req2)
					if err2 == nil {
						defer resp2.Body.Close()
						if resp2.StatusCode == 200 {
							return io.ReadAll(resp2.Body)
						}
					}
				}
			}
			if strings.Contains(loc, "accounts.google.com") {
				return nil, fmt.Errorf("Google-Cookie abgelaufen: Weiterleitung zum Login (%s)", loc)
			}
			return nil, fmt.Errorf("fetch /app: HTTP %d -> %s", resp.StatusCode, loc)
		}
		if resp.StatusCode != 200 {
			return nil, fmt.Errorf("fetch /app: HTTP %d", resp.StatusCode)
		}
		body, err = io.ReadAll(resp.Body)
		if err != nil {
			return nil, err
		}
	} else {
		req, err := fhttp.NewRequest("GET", pageURL, nil)
		if err != nil {
			return nil, err
		}
		for k, v := range headers {
			req.Header.Set(k, v)
		}
		resp, err := getTLSClient().Do(req)
		if err != nil {
			return nil, err
		}
		defer resp.Body.Close()
		if resp.StatusCode == 301 || resp.StatusCode == 302 || resp.StatusCode == 307 {
			loc := resp.Header.Get("Location")
			if strings.HasPrefix(loc, "https://gemini.google.com") {
				req2, err2 := fhttp.NewRequest("GET", loc, nil)
				if err2 == nil {
					for k, v := range headers {
						req2.Header.Set(k, v)
					}
					resp2, err2 := getTLSClient().Do(req2)
					if err2 == nil {
						defer resp2.Body.Close()
						if resp2.StatusCode == 200 {
							return io.ReadAll(resp2.Body)
						}
					}
				}
			}
			if strings.Contains(loc, "accounts.google.com") {
				return nil, fmt.Errorf("Google-Cookie abgelaufen: Weiterleitung zum Login (%s)", loc)
			}
			return nil, fmt.Errorf("fetch /app: HTTP %d -> %s", resp.StatusCode, loc)
		}
		if resp.StatusCode != 200 {
			return nil, fmt.Errorf("fetch /app: HTTP %d", resp.StatusCode)
		}
		body, err = io.ReadAll(resp.Body)
		if err != nil {
			return nil, err
		}
	}
	return body, nil
}

// fetchAppTokens fetches the /app page once and extracts all three tokens together.
func fetchAppTokens(cookie, proxyURL string) (xsrfEntry, error) {
	body, err := fetchAppPage(cookie, proxyURL)
	if err != nil {
		return xsrfEntry{}, err
	}
	e := xsrfEntry{fetched: time.Now()}
	if m := snlm0eRe.FindSubmatch(body); m != nil {
		e.token = string(m[1])
	} else if cookie != "" {
		// a cookie present but no token = the cookie expired and we're being treated as anonymous. Anonymous never has this field, so that's not an error.
		return xsrfEntry{}, fmt.Errorf("no SNlM0e in page (cookie expired or not signed in)")
	}
	if p := pushIDRe.FindSubmatch(body); p != nil {
		e.pushID = string(p[1])
	}
	if p := pctxRe.FindSubmatch(body); p != nil {
		e.pctx = string(p[1])
	}
	return e, nil
}

// isXSRFError checks whether an upstream 400 is an XSRF token problem.
// Response body looks like: [["er",null,...,400,...,[{"48448350":["xsrf","<newtoken>",...]}]]]
func isXSRFError(raw string) bool {
	return strings.Contains(raw, `"xsrf"`)
}
