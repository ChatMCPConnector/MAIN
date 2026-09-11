package app

import (
	"regexp"
	"sync"
	"time"
)

// bl is the upstream frontend's build version, e.g. boq_assistant-bard-web-server_20260805.16_p0,
// required by every StreamGenerate request. It is buried in the "cfb2h" field of the /app page HTML.
//
// Pinning a fixed value works — our pinned 20260525.09_p0 is over two months older than the browser's
// 20260805.16_p0 from the packet capture, and observed in practice still works. But "still works" is not "works forever":
// once the upstream retires the value, the symptom is mass failures of all requests, and during debugging it is hard to think of
// an expired version number. Since xsrf.go already fetches the /app page, grabbing it too costs almost nothing.
var (
	blMu       sync.RWMutex
	blFetched  string    // latest fetched value; empty = not fetched yet
	blFetchAt  time.Time // time of the last fetch attempt (success or failure, to avoid retry storms on failure)
	blFetching bool      // a fetch is currently in flight
)

// bl changes on a daily granularity; checking every few hours is enough.
const blTTL = 6 * time.Hour

var cfb2hRe = regexp.MustCompile(`"cfb2h":"([^"]{10,120})"`)

// blValueRe pins the shape: boq_assistant-bard-web-server_<8-digit date>.<2-digit>_p<digits>.
// The page's cfb2h should in theory match this format, but it is external input — splicing it straight into a URL
// lets the upstream page decide what requests we send. On a shape mismatch, treat it as not fetched and keep the pinned value —
// better stale than sending garbage.
var blValueRe = regexp.MustCompile(`^boq_assistant-bard-web-server_\d{8}\.\d{2}_p\d+$`)

// currentBL returns the bl to use for this request.
//
// Non-blocking: when stale it only kicks off one background fetch and still returns the current value for this request. bl is a slowly changing version number;
// an old value is at most a few versions behind (observed in practice it still worked over two months behind), not worth adding
// a page-fetch delay to every request for it. When auto is off, the configured value is always used.
func currentBL(proxyURL string) string {
	pinned := rtCfg().GeminiBL
	if !rtCfg().GeminiBLAuto {
		return pinned
	}

	blMu.RLock()
	val, fetchedAt, inflight := blFetched, blFetchAt, blFetching
	blMu.RUnlock()

	if !inflight && time.Since(fetchedAt) > blTTL {
		blMu.Lock()
		// Double-check: under concurrent requests only one goroutine goes fetching.
		if !blFetching && time.Since(blFetchAt) > blTTL {
			blFetching = true
			go refreshBL(proxyURL)
		}
		blMu.Unlock()
	}

	if val != "" {
		return val
	}
	return pinned
}

// refreshBL fetches /app once and extracts cfb2h. Anonymous fetching is fine; the value has nothing to do with login state.
func refreshBL(proxyURL string) {
	defer func() {
		blMu.Lock()
		blFetching = false
		blFetchAt = time.Now() // recorded for success and failure alike; on failure the full TTL must still elapse before retrying
		blMu.Unlock()
	}()

	body, err := fetchAppPage("", proxyURL)
	if err != nil {
		logf("[bl] failed to fetch /app, keeping the current value: %v", err)
		return
	}
	m := cfb2hRe.FindSubmatch(body)
	if m == nil {
		logf("[bl] no cfb2h in the page, keeping the current value")
		return
	}
	got := string(m[1])
	if !blValueRe.MatchString(got) {
		logf("[bl] fetched value has the wrong shape, ignoring: %q", truncate(got, 60))
		return
	}

	blMu.Lock()
	changed := blFetched != got
	blFetched = got
	blMu.Unlock()
	if changed {
		logf("[bl] updated to %s (config pins %s)", got, rtCfg().GeminiBL)
	}
}
