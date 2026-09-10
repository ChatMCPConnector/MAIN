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

// CannedReplyError 表示上游回了"罐头错误"短句（瞬态故障或拒答话术，按账号语言出）。
// 特征：HTTP 200、有内容帧、正文极短且措辞固定（见 cannedErrorPrefixes）。
// 与额度耗尽不同：这个是瞬态的，重发一次通常就过 —— 所以 handler 层做一次
// 单轮重发而不是锁窗口。
type CannedReplyError struct {
	Text string // 原始罐头回复
}

func (e *CannedReplyError) Error() string {
	return fmt.Sprintf("upstream returned a canned error reply (transient): %q", truncateStr(e.Text, 100))
}

func truncateStr(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "..."
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

// cannedGate 延迟流式开闸：把前 220 字节的 delta 扣在缓冲里，攒够了（说明
// 不是罐头错误——罐头都极短）或流结束时再一次性放行。
//
// 为什么需要：罐头错误的检测要等**完整短句**出来才能判定，但真流式会把
// 前几个 delta 先推给客户端 —— sse.Started() 变 true，检测命中时已吐出去
// 收不回，只能 Fail，agentic run 就此中断（实测 benchmark turn 7 卡死）。
// 扣住头 220 字节后：正常回复几乎无感（首屏晚几百毫秒），罐头回复则一个
// 字都没出门，检测命中就能干净地重试。
type cannedGate struct {
	emit    func(string) // 真正的下游（sse.SendContent / SendReasoning）
	buf     string
	flushed bool
	canned  bool
}

func newCannedGate(emit func(string)) *cannedGate {
	return &cannedGate{emit: emit}
}

const cannedGateHold = 220

// Push 吃进一段 delta。缓冲期（未 flush）内攒着；超过保持线说明这不是罐头，
// 全部放行并进入直通模式。
func (g *cannedGate) Push(s string) {
	if g == nil || g.emit == nil {
		return
	}
	if g.flushed {
		g.emit(s)
		return
	}
	g.buf += s
	if len(g.buf) > cannedGateHold {
		g.flush()
	}
}

func (g *cannedGate) flush() {
	if g.flushed {
		return
	}
	g.flushed = true
	if g.buf != "" {
		g.emit(g.buf)
		g.buf = ""
	}
}

// Finish 在流结束时调用：短回复（可能罐头）在这里判定。
// 罐头 → 丢弃缓冲、标记 canned（调用方据此走重试，客户端一个字没收到）；
// 正常 → 放行。
func (g *cannedGate) Finish() {
	if g == nil || g.flushed {
		return
	}
	g.flushed = true
	if isCannedErrorText(g.buf) {
		g.canned = true
		g.buf = ""
		return
	}
	if g.buf != "" {
		g.emit(g.buf)
		g.buf = ""
	}
}

// Canned 报告 Finish 是否判定为罐头回复。
func (g *cannedGate) Canned() bool {
	return g != nil && g.canned
}

// flushedForStarted 报告是否有真实正文已经放行出门（供 sse.Started 场景区分：
// 已放行 = 客户端真见过正文，只能 Fail；罐头判定丢弃了缓冲 = 一个字没出门，
// 还能干净重试）。
func (g *cannedGate) flushedForStarted() bool {
	return g == nil || (g.flushed && !g.canned)
}

// cannedErrorPrefixes 是上游"罐头错误"回复的已知前缀（按账号语言出）。
// 这些都是 200 + 内容帧里的短句，以前被当正常回复透传。共同特征：极短 +
// 固定措辞。正常回答不会以这些开头（前缀精确匹配）。
var cannedErrorPrefixes = []string{
	"i encountered an error doing what you asked", // 额度耗尽（en）
	"sorry, something went wrong",                 // 瞬态故障（en）
	"i'm a language model",                        // 瞬态/拒答（en）
	"i am a language model",                       // 同上变体
	"ich bin ein sprachmodell",                    // 瞬态/拒答（de）
	"leider ist beim verarbeiten",                 // 瞬态故障（de）
	"es ist ein fehler aufgetreten",               // 瞬态故障（de）
}

// cannedErrorMarkers 是启发式的第二道网：罐头错误全都含这些词根之一，而
// 正常回答（尤其带 tool_call 围栏的）几乎不会**又短又含错误词**。上游变体
// 层出不穷（实测一周内就出了 4 种新措辞），逐条枚举跟不上 —— 两个条件
// 一起卡误报面：长度 < 150 且命中词根。
var cannedErrorMarkers = []string{
	"error", "fehler", "language model", "sprachmodell",
	"programmierung hinaus", "hard time", "try again", "try something else",
	"erneut versuchen", "geht über", "can't fulfill", "kann ich nicht",
}

// isCannedErrorText 判断回复是否是已知的罐头错误（任何一种）。
// 额度签名是它的子集：quota 是要锁 5h 的，其余按瞬态重试。
func isCannedErrorText(text string) bool {
	t := strings.ToLower(strings.TrimSpace(text))
	if t == "" {
		return false
	}
	if len(t) > 200 { // 罐头错误都很短；真实回复几乎必然更长
		return false
	}
	for _, p := range cannedErrorPrefixes {
		if strings.HasPrefix(t, p) {
			return true
		}
	}
	// 启发式：短 + 错误词根。带 ```tool_call 围栏的绝不可能是罐头。
	if strings.Contains(t, "```") {
		return false
	}
	for _, m := range cannedErrorMarkers {
		if strings.Contains(t, m) {
			return true
		}
	}
	return false
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

// quotaBannerConfirmed 已废弃：/app 页面里的 "out_of_quota" 是一个**永久存在的
// UTM 链接**（gemini_out_of_quota_input_inline_upgrade_banner，指向 one.google.com/ai
// 的升级广告），跟额度是否耗尽无关 —— 实测额度正常时页面照样带它，用它会
// 把每次瞬态抖动都误锁 5 小时。保留函数签名做占位避免别处报错，恒返回 false。
//
// 替代方案在 server 层：retry-based confirmation —— 检出签名后**重发一次**，
// 签名不再出现 = 瞬态，不锁；再次出现 = 真耗尽，锁。
func quotaBannerConfirmed() bool {
	return false
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
