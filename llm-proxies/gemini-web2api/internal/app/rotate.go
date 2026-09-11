package app

import (
	"fmt"
	"io"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	fhttp "github.com/bogdanfinn/fhttp"
)

// Conversation keep-alive. The same POST /RotateCookies has two payloads,
// refreshing different cookie families:
//
//  1. Sentinel `[000,"-0000000000000000000"]`: unconditionally reissues
//     `__Secure-1PSIDTS` / `__Secure-3PSIDTS`. These are the truly
//     short-lived tickets of the logged-in state (~30 minutes); without
//     refreshing them, the session is treated as anonymous. The payload
//     must be this exact JSPB string (leading zeros valid, strict JSON
//     invalid) — json.Marshal would turn it into `[0,"…"]`, which the
//     server rejects.
//
//  2. The browser-iframe route: first GET RotateCookiesPage to obtain a
//     session id, then POST `[658,"<id>"]`. This only refreshes SIDCC /
//     `__Secure-1PSIDCC` / `__Secure-3PSIDCC`, with the interval given by
//     the last argument of the page's init(...) (measured in practice:
//     600 seconds).
//
// Previously only route 2 was implemented, so accounts died after about
// half an hour (issue #6). Newer Chrome also has DBSC device binding
// (GET /RotateBoundCookies + signed JWT), which we cannot replicate; the
// sentinel route works for Firefox exports and sessions without device
// binding. If a Chrome-exported account keeps getting 401s, re-login with
// Firefox and export again.

const (
	rotatePageURL = "https:/​/accounts.google.com/RotateCookiesPage" +
		"?og_pid=658&rot=3&origin=https%3A%2F%2Fgemini.google.com&exp_id=0"
	rotatePostURL = "https:/​/accounts.google.com/RotateCookies"
	// og_pid is the product identifier, fixed at 658 for Gemini; it appears
	// both as a query on the page above and echoed inside the page.
	rotateProductID = 658
	// Fallback when the server gives no interval.
	defaultRotateInterval = 10 * time.Minute
	// Refresh once soon after startup: at import time the cookie may already
	// be near expiry; idly waiting 10 minutes would let it expire outright.
	firstRotateDelay = 15 * time.Second
	// Sentinel payload. The leading zeros are intentional, see file header.
	rotate1PSIDTSBody = `[000,"-0000000000000000000"]`
	// Calling too frequently gets 429. Gemini-API / notebooklm-py both use a
	// 60-second floor.
	min1PSIDTSInterval = 60 * time.Second
)

// Refreshing 1PSIDTS carries only this pair. Carrying more gets 401 in
// practice.
var rotate1PSIDTSCookies = []string{"__Secure-1PSID", "__Secure-1PSIDTS"}

var (
	psidtsMu     sync.Mutex
	psidtsLastAt = map[int64]time.Time{}
)

// The page contains something like: init('4162200486104360679', 658.0, 0.0, 0.0, 600.0)
// The first argument is this session's identifier, the last one is the
// interval in seconds until the next rotation.
var rotateInitRe = regexp.MustCompile(`init\('([^']{4,64})'\s*,\s*([0-9.]+)\s*,[^)]*?([0-9.]+)\s*\)`)

// rotateAccount performs one keep-alive pass for an account: refresh
// 1PSIDTS first, then SIDCC.
// Returns the server-suggested next interval, plus the cookie names
// actually refreshed this turn.
func rotateAccount(a CookieAccount) (time.Duration, []string, error) {
	proxyURL := ""
	if a.ProxyID > 0 {
		proxyURL = proxyURLByID(a.ProxyID)
	}

	cookie := a.Cookie
	var names []string
	var psidtsErr, sidccErr error
	interval := defaultRotateInterval

	c2, n, err := tryRotate1PSIDTS(a.ID, cookie, proxyURL)
	if err != nil {
		psidtsErr = err
		logf("[rotate] 账号 #%d 刷新 1PSIDTS 失败: %v", a.ID, err)
	} else {
		cookie = c2
		names = append(names, n...)
	}

	c3, iv, n2, err := rotateSIDCC(cookie, proxyURL)
	if err != nil {
		sidccErr = err
		logf("[rotate] 账号 #%d SIDCC 保活失败: %v", a.ID, err)
	} else {
		cookie = c3
		names = append(names, n2...)
		if iv > 0 {
			interval = iv
		}
	}

	names = uniqueKeepOrder(names)
	if cookie != a.Cookie {
		old := a.Cookie
		updateAccountCookie(a.ID, cookie)
		invalidateXSRF(old)
	}
	if len(names) > 0 {
		logf("[rotate] 账号 #%d 刷新了 %s", a.ID, strings.Join(names, ", "))
	}
	// Failure requires both routes to fail. If 1PSIDTS was refreshed but the
	// iframe page had no init, keep-alive still succeeded.
	if cookie == a.Cookie && len(names) == 0 {
		if psidtsErr != nil {
			return 0, nil, psidtsErr
		}
		if sidccErr != nil {
			return 0, nil, sidccErr
		}
	}
	return interval, names, nil
}

// tryRotate1PSIDTS reissues 1PSIDTS using the sentinel payload. Skipped
// (not counted as failure) when __Secure-1PSID is absent or the last
// attempt was less than 60 seconds ago.
func tryRotate1PSIDTS(id int64, cookie, proxyURL string) (string, []string, error) {
	if cookieValue(cookie, "__Secure-1PSID") == "" {
		return cookie, nil, nil
	}
	if ok, _ := allow1PSIDTSRotate(id); !ok {
		logf("[rotate] 账号 #%d 跳过 1PSIDTS 刷新（距上次不足 %s，避免 429）", id, min1PSIDTSInterval)
		return cookie, nil, nil
	}
	c2, names, err := rotate1PSIDTS(cookie, proxyURL)
	note1PSIDTSAttempt(id, err)
	if err != nil {
		return cookie, nil, err
	}
	return c2, names, nil
}

func allow1PSIDTSRotate(id int64) (bool, time.Duration) {
	psidtsMu.Lock()
	defer psidtsMu.Unlock()
	last := psidtsLastAt[id]
	if last.IsZero() {
		return true, 0
	}
	elapsed := time.Since(last)
	if elapsed >= min1PSIDTSInterval {
		return true, 0
	}
	return false, min1PSIDTSInterval - elapsed
}

func note1PSIDTSAttempt(id int64, err error) {
	// Record the time for success, 401/403 and 429 alike, to avoid immediately
	// hitting it again. Network errors are not recorded; immediate retry is
	// allowed.
	if err != nil {
		msg := err.Error()
		if !strings.Contains(msg, "HTTP 401") &&
			!strings.Contains(msg, "HTTP 403") &&
			!strings.Contains(msg, "HTTP 429") {
			return
		}
	}
	psidtsMu.Lock()
	psidtsLastAt[id] = time.Now()
	psidtsMu.Unlock()
}

// rotate1PSIDTS POSTs the sentinel payload and merges the Set-Cookie
// response back into the full cookie string.
func rotate1PSIDTS(cookie, proxyURL string) (string, []string, error) {
	subset := cookieSubset(cookie, rotate1PSIDTSCookies)
	headers := map[string]string{
		"Accept":         "*/*",
		"Content-Type":   "application/json",
		"Origin":         "https://accounts.google.com",
		"Cookie":         subset,
		"Cache-Control":  "no-cache",
		"Pragma":         "no-cache",
		"Sec-Fetch-Dest": "empty",
		"Sec-Fetch-Mode": "cors",
		"Sec-Fetch-Site": "same-origin",
	}
	status, setCookie, respBody, err := rotatePost(rotatePostURL, headers, []byte(rotate1PSIDTSBody), proxyURL)
	if err != nil {
		return cookie, nil, err
	}
	if status == 401 || status == 403 {
		return cookie, nil, fmt.Errorf("RotateCookies 1PSIDTS 返回 HTTP %d（Chrome 导出的 cookie 可能受设备绑定限制，建议用 Firefox 重新导出）: %s",
			status, truncate(string(respBody), 120))
	}
	if status != 200 {
		return cookie, nil, fmt.Errorf("RotateCookies 1PSIDTS 返回 HTTP %d: %s", status, truncate(string(respBody), 120))
	}
	merged := mergeSetCookie(cookie, setCookie)
	return merged, setCookieNames(setCookie), nil
}

// rotateSIDCC takes the browser-iframe route: GET the rotation page for a
// session id, then POST [658, id].
func rotateSIDCC(cookie, proxyURL string) (string, time.Duration, []string, error) {
	id, interval, pageSet, err := fetchRotateParams(cookie, proxyURL)
	if err != nil {
		return cookie, 0, nil, err
	}
	cookie = mergeSetCookie(cookie, pageSet)

	body := fmt.Sprintf(`[%d,"%s"]`, rotateProductID, id)
	headers := rotatePostHeaders()
	headers["Cookie"] = cookie
	status, setCookie, respBody, err := rotatePost(rotatePostURL, headers, []byte(body), proxyURL)
	if err != nil {
		return cookie, 0, nil, err
	}
	if status != 200 {
		return cookie, 0, nil, fmt.Errorf("RotateCookies 返回 HTTP %d: %s", status, truncate(string(respBody), 120))
	}
	cookie = mergeSetCookie(cookie, setCookie)
	names := setCookieNames(append(append([]string{}, pageSet...), setCookie...))
	return cookie, interval, names, nil
}

func uniqueKeepOrder(in []string) []string {
	seen := map[string]bool{}
	var out []string
	for _, s := range in {
		if s == "" || seen[s] {
			continue
		}
		seen[s] = true
		out = append(out, s)
	}
	return out
}

// setCookieNames extracts and dedups the names from Set-Cookie headers; for
// logging only.
func setCookieNames(headers []string) []string {
	seen := map[string]bool{}
	var out []string
	for _, h := range headers {
		name := h
		if i := strings.Index(name, "="); i > 0 {
			name = name[:i]
		}
		name = strings.TrimSpace(name)
		if name == "" || seen[name] {
			continue
		}
		seen[name] = true
		out = append(out, name)
	}
	return out
}

// fetchRotateParams fetches RotateCookiesPage for the session identifier, the
// server-specified interval, and the Set-Cookie that this very call brings
// back.
func fetchRotateParams(cookie, proxyURL string) (string, time.Duration, []string, error) {
	status, setCookie, body, err := rotateGet(rotatePageURL, cookie, proxyURL)
	if err != nil {
		return "", 0, nil, err
	}
	if status != 200 {
		return "", 0, nil, fmt.Errorf("取轮转页返回 HTTP %d", status)
	}
	m := rotateInitRe.FindSubmatch(body)
	if m == nil {
		// Page fetched but no init(...): most likely the cookie has expired and it
		// bounced to the login page.
		return "", 0, nil, fmt.Errorf("轮转页里没有 init(...)（cookie 可能已失效）")
	}
	id := string(m[1])
	interval := defaultRotateInterval
	if sec, e := strconv.ParseFloat(string(m[3]), 64); e == nil && sec >= 60 && sec <= 3600 {
		interval = time.Duration(sec) * time.Second
	}
	return id, interval, setCookie, nil
}

// The two header sets below are copied item by item from packet capture
// (wireHeaders, not headers — the latter lacks cookies). The capture also
// has sec-ch-ua-arch / -bitness / -form-factors / -full-version-list /
// -model / -platform-version / -wow64 and x-browser-* / x-client-data /
// x-chrome-id-consistency-request — those are browser-identity headers
// Chrome attaches itself; sending them ourselves would clash with the TLS
// fingerprint, so we don't.

// rotateGet fetches the rotation page. In the browser it is an iframe
// navigation, so the sec-fetch group differs completely from a normal XHR
// (dest=iframe / mode=navigate / site=same-site); don't use the defaults.
func rotateGet(url, cookie, proxyURL string) (int, []string, []byte, error) {
	return rotateDo("GET", url, map[string]string{
		"Cookie":                    cookie,
		"Accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
		"Referer":                   "https://gemini.google.com/",
		"Sec-Fetch-Dest":            "iframe",
		"Sec-Fetch-Mode":            "navigate",
		"Sec-Fetch-Site":            "same-site",
		"Sec-Fetch-User":            "?1",
		"Upgrade-Insecure-Requests": "1",
		"Priority":                  "u=0, i",
	}, nil, proxyURL)
}

// rotatePostHeaders is the complete header set for the POST /RotateCookies
// call; the caller only fills in Cookie.
func rotatePostHeaders() map[string]string {
	return map[string]string{
		"Accept":         "*/*",
		"Content-Type":   "application/json",
		"Origin":         "https://accounts.google.com",
		"Referer":        rotatePageURL,
		"Cache-Control":  "no-cache",
		"Pragma":         "no-cache",
		"Priority":       "u=1, i",
		"Sec-Fetch-Dest": "empty",
		"Sec-Fetch-Mode": "same-origin",
		"Sec-Fetch-Site": "same-origin",
	}
}

func rotatePost(url string, headers map[string]string, body []byte, proxyURL string) (
	int, []string, []byte, error) {
	return rotateDo("POST", url, headers, body, proxyURL)
}

// rotateDo goes through the same egress (proxy) as regular requests:
// sending keep-alives from a different IP amounts to telling the upstream
// that this session is active in two places.
//
// Both transport paths share the same header set. Previously only the
// proxy path called applyChromeHeaders; the direct path didn't even send a
// User-Agent — so the same account presented two different clients to the
// upstream depending on whether it went through a proxy.
func rotateDo(method, url string, headers map[string]string, body []byte, proxyURL string) (
	int, []string, []byte, error) {
	var rdr io.Reader
	if body != nil {
		rdr = strings.NewReader(string(body))
	}
	merged := map[string]string{
		"User-Agent":         ChromeUA,
		"Accept-Language":    "en-US,en;q=0.9",
		"Sec-CH-UA":          `"Chromium";v="146", "Google Chrome";v="146", "Not?A_Brand";v="24"`,
		"Sec-CH-UA-Mobile":   "?0",
		"Sec-CH-UA-Platform": `"Windows"`,
	}
	for k, v := range headers {
		merged[k] = v
	}
	if proxyURL != "" {
		req, err := http.NewRequest(method, url, rdr)
		if err != nil {
			return 0, nil, nil, err
		}
		for k, v := range merged {
			req.Header.Set(k, v)
		}
		resp, err := getStdlibClient(proxyURL).Do(req)
		if err != nil {
			return 0, nil, nil, err
		}
		defer resp.Body.Close()
		b, err := io.ReadAll(resp.Body)
		return resp.StatusCode, resp.Header.Values("Set-Cookie"), b, err
	}
	req, err := fhttp.NewRequest(method, url, rdr)
	if err != nil {
		return 0, nil, nil, err
	}
	for k, v := range merged {
		req.Header.Set(k, v)
	}
	resp, err := getTLSClient().Do(req)
	if err != nil {
		return 0, nil, nil, err
	}
	defer resp.Body.Close()
	b, err := io.ReadAll(resp.Body)
	return resp.StatusCode, resp.Header.Values("Set-Cookie"), b, err
}

// rotateAllAccounts performs one keep-alive pass for every enabled account
// in the pool and returns how long to wait until the next one.
//
// Failures **do not count toward health**: keep-alive hits
// accounts.google.com, which is a different matter from whether the
// conversation works; a moment of network jitter marking an account bad
// would sink it in account selection and actually hurt availability.
func rotateAllAccounts() time.Duration {
	next := defaultRotateInterval
	for _, a := range accountList() {
		if a.Status != "enabled" {
			continue
		}
		iv, _, err := rotateAccount(a)
		if err != nil {
			logf("[rotate] 账号 #%d 保活失败: %v", a.ID, err)
			continue
		}
		if iv > 0 {
			next = iv
		}
	}
	return next
}
