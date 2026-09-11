package app

import (
	"encoding/json"
	"os"
	"sync"
)

type Config struct {
	Port           int    `json:"port"`
	Host           string `json:"host"`
	RetryAttempts  int    `json:"retry_attempts"`
	RetryDelaySec  int    `json:"retry_delay_sec"`
	RequestTimeout int    `json:"request_timeout_sec"`
	GeminiBL       string `json:"gemini_bl"`
	DefaultModel   string `json:"default_model"`
	LogRequests    bool   `json:"log_requests"`
	CookieFile     string `json:"cookie_file"`
	Proxy          string `json:"proxy"` // only used to seed the proxy pool at startup, see seedProxiesFromConfig
	Impersonate    string `json:"impersonate"`
	DBPath         string `json:"db_path"`
	AdminToken     string `json:"admin_token"`
	AdminEnabled   bool   `json:"admin_enabled"`
	RetentionDays  int    `json:"retention_days"`

	// Per-IP rate limit (one slot = direct connection or one proxy); 0 means unlimited.
	// Default takes the lower edge of the measured 80-180 range; see the notes in ratelimit.go.
	PerIPConcurrent int `json:"per_ip_concurrent"` // instantaneous concurrency cap
	PerIPRPM        int `json:"per_ip_rpm"`        // requests-per-minute cap
	PerIPRPH        int `json:"per_ip_rph"`        // requests-per-hour cap

	// How long (minutes) a proxy is held out of the pool after consecutive-failure circuit breaking; 0 = never returns.
	ProxyCooldownMin int `json:"proxy_cooldown_min"`
	// Whether to fall back to a direct connection when the proxy pool has no available egress. Default false.
	FallbackDirect bool `json:"fallback_direct"`
	// Whether to downgrade to anonymous and keep going when the cookie expires. Default false.
	FallbackAnon bool `json:"fallback_anon"`
	// Whether to auto-fetch the latest bl version from the /app page. Default true.
	GeminiBLAuto bool `json:"gemini_bl_auto"`
	// Per-request UTF-8 byte cap on the prompt; 0 = unlimited.
	MaxPromptBytes int `json:"max_prompt_bytes"`
	// Whether to use Gemini's native conversation_id server-side multi-turn. Default true (since 2026-09-10):
	// opening a new conversation per request wastes upstream quota and loses the server-side context of the same dialogue.
	// Past pitfall: default false + a true manually set in the panel lived only in the DB kv, so on a new machine/Codespace
	// it silently reverted — this default is that once-lost fix, now pinned into code.
	MultiTurn bool `json:"multi_turn"`
	// Whether to auto-delete the conversation left on gemini.google.com after the result is produced (#19, rpc GzXR5e).
	// Login-only (deletion needs XSRF); async best-effort, a failed delete only logs and never affects the response. Default false.
	AutoDeleteConversation bool `json:"auto_delete_conversation"`
	// Anonymous first (#20): when a request needs no logged-in capabilities (plain text, non-thinking, no tools, no images),
	// it skips the cookie account and goes anonymous to save quota; an account is picked only when login is needed. Default false. See modelNeedsLogin.
	AnonFirst bool `json:"anon_first"`
	// Whether to auto-downgrade to 3.5 Flash-Lite when the 5h usage quota is exhausted (with a downgrade notice prefix),
	// otherwise a 429 usage_limit_reached is returned directly. 3.5 Flash-Lite is unmetered and always available. Default true.
	QuotaFallback bool `json:"quota_fallback"`
}

var (
	cfg     Config
	cfgOnce sync.Once
)

func defaultConfig() Config {
	return Config{
		Port:           8083,
		Host:           "0.0.0.0",
		RetryAttempts:  3,
		RetryDelaySec:  2,
		RequestTimeout: 180,
		GeminiBL:       "boq_assistant-bard-web-server_20260525.09_p0",
		DefaultModel:   "gemini-3.6-flash",
		LogRequests:    true,
		CookieFile:     "",
		Proxy:          "",
		Impersonate:    "chrome_146",
		DBPath:         "./data/gemini.db",
		AdminToken:     "",
		AdminEnabled:   true,
		RetentionDays:  30,
		// Measured 80-180 per egress (depending on connection strategy and egress quality); 188 on a static IP.
		// RPH takes the lower edge 80 as conservative headroom; low-rate deployments can raise it a lot —
		// 10 requests/minute fired 800 times over 110 minutes without ever being blocked.
		PerIPConcurrent: 5,
		PerIPRPM:        30,
		PerIPRPH:        80,
		// Observed in practice: blocked egresses recover automatically after 106-121 minutes; the cooldown is 120 minutes.
		ProxyCooldownMin: 120,
		FallbackDirect:   false,
		FallbackAnon:     false,
		GeminiBLAuto:     true,
		// Measured in practice the upstream wall sits at ~130k UTF-8 bytes: 129,950 bytes passed 3/3 for both Chinese and English,
		// 135,990 bytes 1/3 each, 141,920 bytes 1/3 each. 128000 leaves a little margin.
		MaxPromptBytes:         128000,
		MultiTurn:              true,
		AutoDeleteConversation: false,
		AnonFirst:              false,
		QuotaFallback:          true,
	}
}

func loadConfig(path string) error {
	cfg = defaultConfig()
	if path == "" {
		for _, p := range []string{"./config.json", os.ExpandEnv("$HOME/.config/gemini-web2api/config.json")} {
			if _, err := os.Stat(p); err == nil {
				path = p
				break
			}
		}
	}
	if path == "" {
		return nil
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(data, &cfg)
}
