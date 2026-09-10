package app

import (
	"fmt"
	"strings"
	"sync"
	"time"
)

// QuotaLimitError 表示 Google 账号的 5 小时用量额度用完了。
//
// 上游的表现极其隐蔽：HTTP 200、有内容帧，但正文只有一句
// "I encountered an error doing what you asked. Could you try again?"
// （实测 65 字节，requests 表里能看到）。以前这句被当成正常回复原样透传，
// agentic 客户端拿到一段没有 tool_call 的散文就中断整个 loop —— 这就是
// benchmark 里"I encountered an error"一闪而过的真正死因。
//
// 额度窗口是滚动的 5 小时（Pro/Flash 付费模型受限；3.5 Flash-Lite 不受限，
// 永远可用）。上游不告诉我们复位时间，只能估：窗口内**第一条**请求的时间
// + 5h —— 从 requests 表里查。
type QuotaLimitError struct {
	Model string // 触发限额的模型名
}

func (e *QuotaLimitError) Error() string {
	return fmt.Sprintf("gemini usage limit reached for %s (rolling 5h window, resets ~%s)",
		e.Model, quotaResetETA())
}

// isQuotaText 判断一段回复文本是不是额度耗尽的签名回复。
//
// 只认精确措辞：泛化的 "something went wrong" 是真实的上游瞬态故障
// （实测下一次请求就恢复），把它也当额度会把 5 小时的降级锁误触发。
func isQuotaText(text string) bool {
	t := strings.TrimSpace(text)
	if t == "" {
		return false
	}
	// 上游大小写/标点偶有漂移，前缀匹配 + 长度上限收紧误报面。
	return len(t) < 120 && strings.HasPrefix(strings.ToLower(t),
		"i encountered an error doing what you asked")
}

const (
	quotaKVKey        = "quota_limited_until"
	quotaWindow       = 5 * time.Hour
	quotaFallbackNote = "[quota-fallback]"
)

var quotaMu sync.Mutex

// quotaResetETA 估算额度窗口的复位时间（本地时区的 HH:MM）。
// 依据：窗口是滚动的 5h，从窗口内第一条请求算起。
func quotaResetETA() string {
	if until, ok := quotaUntil(); ok {
		return until.Local().Format("15:04")
	}
	return "unknown"
}

// quotaUntil 读 kv 里记录的额度复位时刻。
func quotaUntil() (time.Time, bool) {
	v := kvGet(quotaKVKey)
	if v == "" || v == "0" {
		return time.Time{}, false
	}
	var unix int64
	if _, err := fmt.Sscanf(v, "%d", &unix); err != nil || unix <= 0 {
		return time.Time{}, false
	}
	return time.Unix(unix, 0), true
}

// markQuotaLimited 记录"额度用完了"：估算复位时刻并落 kv。
// 后续请求（quotaActive 为真时）直接降级，省一次注定失败的上游调用。
func markQuotaLimited() {
	quotaMu.Lock()
	defer quotaMu.Unlock()
	// 窗口内第一条请求 + 5h。查不到（表空/全是旧数据）就保守取 now+5h。
	first := time.Now().Add(-quotaWindow).Unix()
	if db != nil {
		var minTS int64
		err := db.QueryRow(`SELECT MIN(ts) FROM requests WHERE ts > ?`, first).Scan(&minTS)
		if err == nil && minTS > 0 {
			first = minTS
		}
	}
	until := time.Unix(first, 0).Add(quotaWindow)
	if !until.After(time.Now()) {
		until = time.Now().Add(quotaWindow) // 估算已过期（理论不该发生）→ 保守再等 5h
	}
	_ = kvSet(quotaKVKey, fmt.Sprintf("%d", until.Unix()))
	logf("[quota] 额度耗尽已记录，估算复位 %s", until.Local().Format("15:04"))
}

// quotaBannerConfirmed 用 /app 页面的 out_of_quota 横幅做二次确认。
//
// 为什么需要：65 字节签名回复也可能是瞬态故障（下次就好）。拿它直接锁 5 小时，
// 一次抖动就白白降级半天。而额度真用完时 /app 页面带 out_of_quota 品牌位
// （实测抓到过 gemini_out_of_quota_input_inline_upgrade_banner）。确认了才锁；
// 查不到横幅（或没 cookie / 网络失败）就不锁，按瞬态处理。
func quotaBannerConfirmed() bool {
	a, ok := pickCookieAccount()
	if !ok {
		return false // 没号可查：宁可漏判（不锁），不误判（锁 5h）
	}
	proxyURL := ""
	if a.ProxyID > 0 {
		proxyURL = proxyURLByID(a.ProxyID)
	}
	page, err := fetchAppPage(a.Cookie, proxyURL)
	if err != nil {
		return false
	}
	return strings.Contains(string(page), "out_of_quota")
}

// quotaActive 报告额度锁是否仍在生效。过期的锁顺手清掉。
func quotaActive() bool {
	quotaMu.Lock()
	defer quotaMu.Unlock()
	until, ok := quotaUntil()
	if !ok {
		return false
	}
	if until.After(time.Now()) {
		return true
	}
	_ = kvSet(quotaKVKey, "0") // 已复位
	logf("[quota] 额度窗口已复位，恢复正常模型")
	return false
}

// quotaModelAffected 判断模型是否受 5h 额度约束（3.5 Flash-Lite 不受限）。
func quotaModelAffected(mc ModelConfig) bool {
	return mc.HexID != hexFlashLite
}

// quotaFallbackModel 选降级目标：3.5 Flash-Lite（原模型带思考且池里有号时用
// thinking 版）。返回 (目标模型名, 目标配置, 是否可用)。
func quotaFallbackModel(mc ModelConfig) (string, ModelConfig, bool) {
	name := "gemini-3.5-flash-lite"
	if mc.Thinking && hasCookie() {
		name = "gemini-3.5-flash-lite-thinking"
	}
	fb, ok := Models[name]
	return name, fb, ok
}

// quotaFallbackPrefix 拼降级回复的前置说明，客户端看得见发生了什么。
func quotaFallbackPrefix(origModel, fbModel string) string {
	return fmt.Sprintf("%s Google 账号的 %s 用量额度已用完（滚动 5h 窗口，估算 %s 复位）。"+
		"本回复由 %s 降级生成；额度复位后自动切回 %s。",
		quotaFallbackNote, origModel, quotaResetETA(), fbModel, origModel)
}
