package app

import (
	"crypto/sha1"
	"encoding/hex"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"strings"
	"sync"
	"time"

	tls_client "github.com/bogdanfinn/tls-client"
	"github.com/bogdanfinn/tls-client/profiles"
)

var (
	clientCache   = map[string]tls_client.HttpClient{}
	clientCacheMu sync.RWMutex
)

// resolveProfile maps a config string to a tls-client ClientProfile.
// Defaults to Chrome_146 (matches Python v2's curl_cffi chrome146).
func resolveProfile(name string) profiles.ClientProfile {
	switch strings.ToLower(name) {
	case "chrome_120":
		return profiles.Chrome_120
	case "chrome_124":
		return profiles.Chrome_124
	case "chrome_131":
		return profiles.Chrome_131
	case "chrome_133":
		return profiles.Chrome_133
	case "chrome_144":
		return profiles.Chrome_144
	case "chrome_146", "chrome146":
		return profiles.Chrome_146
	case "firefox_120":
		return profiles.Firefox_120
	case "firefox_123":
		return profiles.Firefox_123
	case "firefox_147", "firefox147":
		return profiles.Firefox_147
	case "safari_16_0":
		return profiles.Safari_16_0
	case "safari_ios_17_0":
		return profiles.Safari_IOS_17_0
	default:
		return profiles.Chrome_146
	}
}

// getTLSClient returns a tls-client (Chrome 146 fingerprint) for direct connections only.
// For proxied connections we use stdlib (see getStdlibClient) — tls-client's SOCKS5
// implementation is fragile compared to net/http.
func getTLSClient() tls_client.HttpClient {
	clientCacheMu.RLock()
	if c, ok := clientCache[rtCfg().Impersonate]; ok {
		clientCacheMu.RUnlock()
		return c
	}
	clientCacheMu.RUnlock()

	clientCacheMu.Lock()
	defer clientCacheMu.Unlock()
	if c, ok := clientCache[rtCfg().Impersonate]; ok {
		return c
	}
	opts := []tls_client.HttpClientOption{
		tls_client.WithTimeoutSeconds(rtCfg().RequestTimeout),
		tls_client.WithClientProfile(resolveProfile(rtCfg().Impersonate)),
		tls_client.WithNotFollowRedirects(),
	}
	client, err := tls_client.NewHttpClient(tls_client.NewNoopLogger(), opts...)
	if err != nil {
		fmt.Fprintf(os.Stderr, "[client] tls-client init failed: %v\n", err)
		os.Exit(1)
	}
	clientCache[rtCfg().Impersonate] = client
	return client
}

// ─── Stdlib HTTP client for proxied requests ─────────────────────────────────
//
// When going through a proxy we switch to stdlib instead of tls-client, because:
// 1. stdlib's http.ProxyURL natively supports socks5:// / socks5h:// / http:// / https://,
//    known to work with the proxies we have on hand.
// 2. tls-client's built-in SOCKS implementation hits EOF on some proxy endpoints (observed in practice).
//
// The trade-off, stated plainly: through a proxy Google sees **our own TLS fingerprint**,
// i.e. the Go standard library's, not Chrome 146's. HTTP CONNECT only builds the tunnel;
// TLS is negotiated end-to-end between us and the target.
// JA3 echo, measured: stdlib direct and stdlib through the proxy show the same JA3
// (03117a8e…), while swapping to tls-client on the same proxy yields a different one
// (2d25c563…) — both criteria confirm the proxy doesn't touch TLS.
//
// But this is no reason to switch back to tls-client: in a simultaneous head-to-head,
// tls-client Chrome_146 got blocked at 111 requests vs Go stdlib at 103 — a gap of 8;
// meanwhile the same config on a different egress varies by up to 36% (151 vs 111).
// The fingerprint difference is real but has no observable impact on the blocking threshold.
//
// Without a proxy we still use getTLSClient (keeping the genuine utls/chrome146
// fingerprint advantage).

var (
	stdlibClientCache sync.Map // proxyURL -> *http.Client
)

// getStdlibClient returns an http.Client routed through proxyURL.
// proxyURL must not be empty (caller checks).
func getStdlibClient(proxyURL string) *http.Client {
	if cached, ok := stdlibClientCache.Load(proxyURL); ok {
		return cached.(*http.Client)
	}
	t := &http.Transport{
		MaxIdleConns:        100,
		MaxIdleConnsPerHost: 20,
		IdleConnTimeout:     90 * time.Second,
		DisableCompression:  false,
		// don't insist on HTTP/2 through a proxy; some proxies don't support it.
		ForceAttemptHTTP2: false,
	}
	if u, err := url.Parse(proxyURL); err == nil {
		t.Proxy = http.ProxyURL(u)
	}
	c := &http.Client{
		Timeout:   time.Duration(rtCfg().RequestTimeout) * time.Second,
		Transport: t,
		// same as tls-client: don't follow redirects automatically (302 is a diagnostic signal)
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
	stdlibClientCache.Store(proxyURL, c)
	return c
}

// loadCookie reads the cookie file (Netscape one-line format or JSON).
// loadCookie returns (cookie string, SAPISID). Only the bypass probe uses it — the
// main request path picks its own account inside streamGenerate, because it also
// needs to rotate accounts one by one and bind an egress.
//
// Cookies come from exactly one source: the cookie pool. Pick an enabled account
// (least recently used first, auto-rotation spreads the per-IP cap). Empty pool =
// anonymous. The old "empty pool falls back to a single cookie" path has been
// removed; its value is merged into the pool at startup by seedCookiesFromConfig.
//
// The third return value is the pool record's ID, used after the request finishes
// to call markCookieByStatus and write back health.
func loadCookie() (cookie, sapisid string) {
	if a, ok := pickCookieAccount(); ok {
		return a.Cookie, extractSAPISID(a.Cookie)
	}
	return "", ""
}

func makeSAPISIDHash(sapisid string) string {
	ts := time.Now().Unix()
	h := sha1.Sum([]byte(fmt.Sprintf("%d %s https://gemini.google.com", ts, sapisid)))
	return fmt.Sprintf("SAPISIDHASH %d_%s", ts, hex.EncodeToString(h[:]))
}

// ChromeUA is the genuine Chrome 146 UA template used for stdlib requests through a proxy.
const ChromeUA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"

// applyChromeHeaders fills stdlib requests with the application-layer headers of a simulated Chrome 146.
// The utls layer's TLS/HTTP2 fingerprinting isn't achievable through a proxy, but the headers must be complete.
func applyChromeHeaders(req *http.Request) {
	req.Header.Set("User-Agent", ChromeUA)
	req.Header.Set("Sec-CH-UA", `"Chromium";v="146", "Google Chrome";v="146", "Not?A_Brand";v="24"`)
	req.Header.Set("Sec-CH-UA-Mobile", "?0")
	req.Header.Set("Sec-CH-UA-Platform", `"Windows"`)
	req.Header.Set("Sec-Fetch-Dest", "empty")
	req.Header.Set("Sec-Fetch-Mode", "cors")
	req.Header.Set("Sec-Fetch-Site", "same-origin")
}
