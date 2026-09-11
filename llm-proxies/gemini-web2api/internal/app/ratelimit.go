package app

import (
	"sort"
	"sync"
	"time"
)

// IPSlot identifies a distinct IP (id=0 = the direct host IP; id>0 = a
// proxy in the proxy pool).
// Each slot independently maintains a concurrency count + sliding-window
// RPM/RPH counts.
//
// The limits come from the cfg.PerIP* fields, defaulted from the measured
// per-IP tolerance of Google:
//   - instantaneous concurrency: 5 (measured in practice, 50 concurrent all
//     passed immediately, but mid/long term triggers sorry)
//   - per minute: 30 (leaving 2x headroom for bursts)
//   - per hour: 80 (the lower edge of the measured 80-180 range, see below)
//
// There is no single number for how many hits one egress can take; it is
// mostly determined by **connection strategy and egress quality**. The
// criterion only recognizes 302 → /sorry/: at concurrency 10 with a reused
// connection pool, 151/172/177; with a fresh connection every time,
// 106/109 (both arms started simultaneously, same batch of egresses, 80
// seconds end to end; within-arm spread only 3 and 5); on a static IP, 188.
//
// And **pacing matters more than any of these**: a calm rhythm of 10
// requests/minute fired 800 times over 110 minutes without ever being
// blocked. Once blocked it's a hard block, auto-recovering after 106-121
// minutes.
//
// So the rolling 1-hour hourWin window is a conservative assumption, not a
// measured conclusion — the real threshold behaves more like "burst to the
// max and get blocked, go slowly and don't" rather than "N per hour". The
// default takes the range's lower edge; better to send less. Deployments
// that knowingly run at low rates can raise RPH a lot.

type ipSlot struct {
	mu        sync.Mutex
	inflight  int
	minuteWin []int64 // unix timestamp (seconds) of each request in the sliding window
	hourWin   []int64
}

var (
	slotsMu sync.RWMutex
	slots   = map[int64]*ipSlot{} // proxy_id -> slot; 0 = direct
)

func getSlot(proxyID int64) *ipSlot {
	slotsMu.RLock()
	s, ok := slots[proxyID]
	slotsMu.RUnlock()
	if ok {
		return s
	}
	slotsMu.Lock()
	defer slotsMu.Unlock()
	if s, ok := slots[proxyID]; ok {
		return s
	}
	s = &ipSlot{}
	slots[proxyID] = s
	return s
}

// trySlotAcquire tries to occupy a slot; over the limit it returns false +
// a reason code.
// A caller receiving true must call slotRelease() deferred.
//
//	"concurrent" — instantaneous concurrency cap reached
//	"rpm"        — per-minute limit exceeded
//	"rph"        — per-hour limit exceeded
func trySlotAcquire(proxyID int64) (bool, string) {
	s := getSlot(proxyID)
	s.mu.Lock()
	defer s.mu.Unlock()

	now := time.Now().Unix()
	// Clear expired windows
	cutMin := now - 60
	cutHour := now - 3600
	s.minuteWin = pruneTimestamps(s.minuteWin, cutMin)
	s.hourWin = pruneTimestamps(s.hourWin, cutHour)

	if rtCfg().PerIPConcurrent > 0 && s.inflight >= rtCfg().PerIPConcurrent {
		return false, "concurrent"
	}
	if rtCfg().PerIPRPM > 0 && len(s.minuteWin) >= rtCfg().PerIPRPM {
		return false, "rpm"
	}
	if rtCfg().PerIPRPH > 0 && len(s.hourWin) >= rtCfg().PerIPRPH {
		return false, "rph"
	}

	s.inflight++
	s.minuteWin = append(s.minuteWin, now)
	s.hourWin = append(s.hourWin, now)
	return true, ""
}

// slotRelease releases the concurrency count (window counts expire
// naturally; not cleared here).
func slotRelease(proxyID int64) {
	s := getSlot(proxyID)
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.inflight > 0 {
		s.inflight--
	}
}

// SlotUsage is for viewing usage in the admin UI.
type SlotUsage struct {
	ProxyID   int64 `json:"proxy_id"`
	Inflight  int   `json:"inflight"`
	RPM       int   `json:"rpm"`
	RPH       int   `json:"rph"`
	LimitConc int   `json:"limit_concurrent"`
	LimitRPM  int   `json:"limit_rpm"`
	LimitRPH  int   `json:"limit_rph"`
}

func slotUsage(proxyID int64) SlotUsage {
	s := getSlot(proxyID)
	s.mu.Lock()
	defer s.mu.Unlock()
	now := time.Now().Unix()
	s.minuteWin = pruneTimestamps(s.minuteWin, now-60)
	s.hourWin = pruneTimestamps(s.hourWin, now-3600)
	return SlotUsage{
		ProxyID:   proxyID,
		Inflight:  s.inflight,
		RPM:       len(s.minuteWin),
		RPH:       len(s.hourWin),
		LimitConc: rtCfg().PerIPConcurrent,
		LimitRPM:  rtCfg().PerIPRPM,
		LimitRPH:  rtCfg().PerIPRPH,
	}
}

// allSlotUsage returns a usage snapshot of all slots (direct + all
// proxies).
// allSlotUsage lists every IP slot that can currently **be scheduled to**,
// including ones never used even once.
//
// Returning only what already exists in the slots map is not enough: that
// map is lazily created on first use and is empty right after a service
// restart, leaving the panel's "distance to the ban red line" entirely
// blank — precisely the screen most worth watching at deployment time.
// Here we enumerate by the same rules as acquireSlot: with proxies
// configured, list only the proxies (when proxies exist there is no
// fallback to direct); otherwise list direct.
func allSlotUsage() []SlotUsage {
	seen := map[int64]bool{}
	var ids []int64

	proxyMu.RLock()
	for _, p := range proxyCache {
		if p.Enabled {
			ids = append(ids, p.ID)
			seen[p.ID] = true
		}
	}
	hasProxies := len(ids) > 0
	proxyMu.RUnlock()

	if !hasProxies {
		ids = append(ids, 0)
		seen[0] = true
	}

	// Also include slots that have counts but were removed/disabled from the
	// pool, otherwise their usage would vanish into thin air
	slotsMu.RLock()
	for id := range slots {
		if !seen[id] && (hasProxies == (id != 0)) {
			ids = append(ids, id)
		}
	}
	slotsMu.RUnlock()

	sort.Slice(ids, func(i, j int) bool { return ids[i] < ids[j] })
	out := make([]SlotUsage, 0, len(ids))
	for _, id := range ids {
		out = append(out, slotUsage(id))
	}
	return out
}

func pruneTimestamps(ts []int64, cutoff int64) []int64 {
	// ts is appended in increasing time order; find the first position
	// >= cutoff and cut off everything before it
	i := 0
	for i < len(ts) && ts[i] < cutoff {
		i++
	}
	if i == 0 {
		return ts
	}
	return ts[i:]
}
