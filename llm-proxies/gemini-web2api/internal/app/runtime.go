package app

import (
	"encoding/json"
	"fmt"
	"sync"
)

// RuntimeConfig is the part of the configuration that can be changed in the
// panel at any time and takes effect immediately.
//
// Deployment-time configuration (listen address, DB path, admin token, API
// key, cookie file) is **not here**: those already require a process
// restart to change, so docker-compose.yml's environment / command is the
// right home — it also keeps credentials out of a web form. This struct
// only holds tuning parameters — restarting the service to change a timeout
// would be silly.
//
// Value precedence: changed in the panel (stored in the kv table) >
// config.json / CLI flag > built-in defaults.
//
// Required reading before adding a field: panel saves go through whole-
// struct deserialization (Decode(&RuntimeConfig) in admin.go), while the
// frontend saveRtCfg builds the PUT body only from admin_ui's RT_GROUPS. A
// new field must be added to RT_GROUPS in sync, otherwise it won't be in
// the body and every click of "save and apply" decodes it as a zero value
// and wipes it (multi_turn was silently reset this way, even wiping what
// was set in config.json, see #27).
type RuntimeConfig struct {
	RetryAttempts   int    `json:"retry_attempts"`
	RetryDelaySec   int    `json:"retry_delay_sec"`
	RequestTimeout  int    `json:"request_timeout_sec"`
	DefaultModel    string `json:"default_model"`
	PerIPConcurrent int    `json:"per_ip_concurrent"`
	PerIPRPM        int    `json:"per_ip_rpm"`
	PerIPRPH        int    `json:"per_ip_rph"`
	RetentionDays   int    `json:"retention_days"`
	LogRequests     bool   `json:"log_requests"`
	Impersonate     string `json:"impersonate"`
	GeminiBL        string `json:"gemini_bl"`
	// ProxyCooldownMin is how many minutes a circuit-broken proxy waits before
	// going back into the pool.
	// 0 = no recovery (circuit-broken = permanently removed, manual reset
	// required). Default is 120, based on the measured ban-recovery duration.
	ProxyCooldownMin int `json:"proxy_cooldown_min"`
	// FallbackDirect decides whether, when no egress in the proxy pool can
	// be used, we fall back to direct connection or return 429 outright.
	// Default false: configuring a proxy pool implies not wanting to expose
	// this machine's IP; silently going direct would nullify that premise.
	FallbackDirect bool `json:"fallback_direct"`
	// FallbackAnon decides whether a stale cookie downgrades to anonymous
	// and keeps going, or errors out directly.
	// Default false: the anonymous tier gets no 3.1 Pro / extended thinking /
	// image generation, and the client can't tell it was downgraded.
	FallbackAnon bool `json:"fallback_anon"`
	// GeminiBLAuto decides whether to periodically fetch the latest bl
	// version from the /app page to override the pinned value above.
	GeminiBLAuto bool `json:"gemini_bl_auto"`
	// MaxPromptBytes is the per-request UTF-8 byte cap on the prompt; over
	// it, an error is returned directly.
	// The unit is bytes, not tokens: measured in practice, the upstream's
	// wall is byte-based and language-independent, see messages.go.
	// 0 = disable the check (send as-is; the upstream silently truncates
	// from the tail).
	MaxPromptBytes int `json:"max_prompt_bytes"`
	// MultiTurn enables Gemini's native conversation_id server-side
	// multi-turn: continuations are recognized by history prefix, and on a
	// hit only the latest message is sent while history stays server-side,
	// bypassing the per-request byte wall. Works for both anonymous and
	// logged-in, see conversation.go.
	// Default false (keeps the current "assemble the full prompt every
	// turn" behavior). Measured in practice, multi-turn does not enlarge
	// the context window; it only keeps long conversations from hitting the
	// per-request wall — useful for long sessions like Codex, useless for
	// "feeding long documents".
	MultiTurn bool `json:"multi_turn"`
	// Automatically delete this conversation on gemini.google.com after the
	// result is done (#19). Only effective when logged in. Default false.
	AutoDeleteConversation bool `json:"auto_delete_conversation"`
	// Anonymous first (#20): requests not needing logged-in capabilities
	// (plain text, non-thinking, no tools, no images) go anonymous and
	// don't occupy a cookie account, saving account quota; accounts are
	// picked only when login is needed. Default false, see modelNeedsLogin.
	AnonFirst bool `json:"anon_first"`
	// QuotaFallback: when the 5h usage quota is exhausted, downgrade to
	// 3.5 Flash-Lite and keep answering (with an explanatory prefix);
	// when off, return 429 instead. See quota.go. Required reading before
	// adding a field: the file-header comment (#27: must sync RT_GROUPS).
	QuotaFallback bool `json:"quota_fallback"`
}

const runtimeConfigKey = "runtime_config"

var (
	rtMu  sync.RWMutex
	rtVal RuntimeConfig
)

// initRuntimeConfig uses the startup configuration as the baseline, then
// overlays the values changed in the panel.
// Must be called after the DB is opened.
func initRuntimeConfig() {
	base := RuntimeConfig{
		RetryAttempts:   cfg.RetryAttempts,
		RetryDelaySec:   cfg.RetryDelaySec,
		RequestTimeout:  cfg.RequestTimeout,
		DefaultModel:    cfg.DefaultModel,
		PerIPConcurrent: cfg.PerIPConcurrent,
		PerIPRPM:        cfg.PerIPRPM,
		PerIPRPH:        cfg.PerIPRPH,
		RetentionDays:   cfg.RetentionDays,
		LogRequests:     cfg.LogRequests,
		Impersonate:     cfg.Impersonate,
		GeminiBL:        cfg.GeminiBL,

		ProxyCooldownMin: cfg.ProxyCooldownMin,
		FallbackDirect:   cfg.FallbackDirect,
		FallbackAnon:     cfg.FallbackAnon,
		GeminiBLAuto:     cfg.GeminiBLAuto,
		MaxPromptBytes:   cfg.MaxPromptBytes,
		MultiTurn:        cfg.MultiTurn,

		AutoDeleteConversation: cfg.AutoDeleteConversation,
		AnonFirst:              cfg.AnonFirst,
		QuotaFallback:          cfg.QuotaFallback,
	}
	if raw := kvGet(runtimeConfigKey); raw != "" {
		saved := base
		if err := json.Unmarshal([]byte(raw), &saved); err == nil {
			if err := validateRuntimeConfig(saved); err == nil {
				base = saved
			} else {
				logf("[config] ignoring invalid runtime config in kv: %v", err)
			}
		}
	}
	rtMu.Lock()
	rtVal = base
	rtMu.Unlock()
}

// rtCfg returns a snapshot of the current runtime configuration.
func rtCfg() RuntimeConfig {
	rtMu.RLock()
	defer rtMu.RUnlock()
	return rtVal
}

// validateRuntimeConfig validates the values coming from the panel.
//
// These numbers directly determine retry counts, timeouts, and rate-limit
// quotas — external input flowing into sensitive spots: a zero or negative
// value makes the rate limiter reject forever or admit forever, and a huge
// value can hang a single request for hours. The upper bounds are looser
// than any reasonable use, only blocking obviously absurd input.
func validateRuntimeConfig(c RuntimeConfig) error {
	type rangeCheck struct {
		name     string
		v        int
		min, max int
	}
	for _, r := range []rangeCheck{
		{"retry_attempts", c.RetryAttempts, 1, 10},
		{"retry_delay_sec", c.RetryDelaySec, 0, 60},
		{"request_timeout_sec", c.RequestTimeout, 5, 600},
		{"per_ip_concurrent", c.PerIPConcurrent, 0, 1000},
		{"per_ip_rpm", c.PerIPRPM, 0, 10000},
		{"per_ip_rph", c.PerIPRPH, 0, 100000},
		{"retention_days", c.RetentionDays, 1, 3650},
		{"proxy_cooldown_min", c.ProxyCooldownMin, 0, 10080},
		{"max_prompt_bytes", c.MaxPromptBytes, 0, 10000000},
	} {
		if r.v < r.min || r.v > r.max {
			return fmt.Errorf("%s=%d out of the allowed range [%d, %d]", r.name, r.v, r.min, r.max)
		}
	}
	if _, _, err := resolveModel(c.DefaultModel); err != nil {
		return fmt.Errorf("default_model not available: %v", err)
	}
	if c.Impersonate == "" {
		return fmt.Errorf("impersonate must not be empty")
	}
	if c.GeminiBL == "" {
		return fmt.Errorf("gemini_bl must not be empty")
	}
	return nil
}

// saveRuntimeConfig validates and persists; takes effect immediately on
// success.
func saveRuntimeConfig(next RuntimeConfig) error {
	if err := validateRuntimeConfig(next); err != nil {
		return err
	}
	b, err := json.Marshal(next)
	if err != nil {
		return err
	}
	if err := kvSet(runtimeConfigKey, string(b)); err != nil {
		return err
	}
	rtMu.Lock()
	rtVal = next
	rtMu.Unlock()
	logf("[config] runtime config updated")
	return nil
}
