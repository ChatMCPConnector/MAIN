import { Plugin } from "@opencode/plugin/tui"
import { createSignal, Show } from "solid-js"
import * as fs from "node:fs"
import * as os from "node:os"
import * as path from "node:path"

interface BucketInfo {
  pct: number
  reset: string
}

interface QuotaState {
  gemini: { sprint: BucketInfo; weekly: BucketInfo }
  claude: { sprint: BucketInfo; weekly: BucketInfo }
  lastUpdated?: string
  error?: string
}

const CACHE_FILE = "/tmp/opencode/quota-cache.json"

function loadCache(): QuotaState | null {
  try {
    if (fs.existsSync(CACHE_FILE)) {
      const raw = fs.readFileSync(CACHE_FILE, "utf8")
      const parsed = JSON.parse(raw)
      if (parsed?.gemini && parsed?.claude) {
        return parsed
      }
    }
  } catch {}
  return null
}

function saveCache(data: QuotaState) {
  try {
    fs.mkdirSync(path.dirname(CACHE_FILE), { recursive: true })
    fs.writeFileSync(CACHE_FILE, JSON.stringify(data), "utf8")
  } catch {}
}

function formatTime(resetStr?: string): string {
  if (!resetStr) return "bereit"
  try {
    const dt = new Date(resetStr)
    const sec = Math.floor((dt.getTime() - Date.now()) / 1000)
    if (sec <= 0) return "bereit"
    const days = Math.floor(sec / 86400)
    const hours = Math.floor((sec % 86400) / 3600)
    const mins = Math.floor((sec % 3600) / 60)
    if (days > 0) return `${days}d ${hours}h`
    if (hours > 0) return `${hours}:${String(mins).padStart(2, "0")}h`
    return `${mins}m`
  } catch {
    return resetStr || "bereit"
  }
}

async function fetchQuota(): Promise<QuotaState | null> {
  const credsPath = path.join(os.homedir(), ".config/antigravity-oauth-proxy/oauth_creds.json")
  if (!fs.existsSync(credsPath)) {
    return {
      gemini: { sprint: { pct: 100, reset: "" }, weekly: { pct: 100, reset: "" } },
      claude: { sprint: { pct: 100, reset: "" }, weekly: { pct: 100, reset: "" } },
      error: "Keine Credentials",
    }
  }

  let creds: any
  try {
    creds = JSON.parse(fs.readFileSync(credsPath, "utf8"))
  } catch {
    return {
      gemini: { sprint: { pct: 100, reset: "" }, weekly: { pct: 100, reset: "" } },
      claude: { sprint: { pct: 100, reset: "" }, weekly: { pct: 100, reset: "" } },
      error: "Fehler beim Lesen",
    }
  }

  if (!creds?.access_token) {
    return {
      gemini: { sprint: { pct: 100, reset: "" }, weekly: { pct: 100, reset: "" } },
      claude: { sprint: { pct: 100, reset: "" }, weekly: { pct: 100, reset: "" } },
      error: "Kein Token",
    }
  }

  const headers = {
    Authorization: "Bearer " + creds.access_token,
    "Content-Type": "application/json",
    "User-Agent": "antigravity/cli/1.1.13 (aidev_client; os_type=linux; arch=amd64; cl=964361259; auth_method=consumer)",
  }

  let data: any
  try {
    const res = await fetch("https://daily-cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary", {
      method: "POST",
      headers,
      body: JSON.stringify({ project: "aicode-consumers" }),
      signal: AbortSignal.timeout(4000),
    })
    if (res.ok) {
      data = await res.json()
    }
  } catch {
    // Fallback
  }

  if (!data?.groups) {
    try {
      const res = await fetch("https://daily-cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels", {
        method: "POST",
        headers,
        body: JSON.stringify({ project: "aicode-consumers" }),
        signal: AbortSignal.timeout(4000),
      })
      if (res.ok) {
        data = await res.json()
      }
    } catch {
      // Ignorieren
    }
  }

  if (!data || (!data.groups && !data.models)) {
    throw new Error("Ungültige Antwort von Google")
  }

  const result: QuotaState = {
    gemini: { sprint: { pct: 100, reset: "" }, weekly: { pct: 100, reset: "" } },
    claude: { sprint: { pct: 100, reset: "" }, weekly: { pct: 100, reset: "" } },
    lastUpdated: new Date().toISOString(),
  }

  if (data.groups) {
    for (const group of data.groups || []) {
      const isGemini = (group.displayName || "").toLowerCase().includes("gemini")
      const target = isGemini ? result.gemini : result.claude
      for (const b of group.buckets || []) {
        const w = ((b.window || "") + (b.bucketId || "")).toLowerCase()
        const frac = typeof b.remainingFraction === "number" ? b.remainingFraction : 1
        const pct = Math.round(frac * 100)
        const reset = formatTime(b.resetTime)
        if (w.includes("5h")) {
          target.sprint = { pct, reset }
        } else if (w.includes("week")) {
          target.weekly = { pct, reset }
        }
      }
    }
  } else if (data.models) {
    const pools = [
      { key: "gemini", keys: ["gemini-3.8-flash-high", "gemini-pro-agent"] },
      { key: "claude", keys: ["claude-opus-4-6-thinking", "claude-sonnet-4-6", "gpt-oss-120b-medium"] },
    ]
    for (const pool of pools) {
      const target = pool.key === "gemini" ? result.gemini : result.claude
      let q: any = null
      for (const k of pool.keys) {
        q = data.models[k]?.quotaInfo
        if (q) break
      }
      if (q) {
        const frac = typeof q.remainingFraction === "number" ? q.remainingFraction : 1
        const pct = Math.round(frac * 100)
        const reset = formatTime(q.resetTime)
        target.sprint = { pct, reset }
        target.weekly = { pct, reset }
      }
    }
  }

  saveCache(result)
  return result
}

export default Plugin.define({
  id: "antigravity.quota",
  setup(context) {
    const [quota, setQuota] = createSignal<QuotaState | null>(loadCache())
    const [loading, setLoading] = createSignal(false)

    const refresh = async (force = false) => {
      if (loading()) return
      const current = quota()
      if (!force && current?.lastUpdated) {
        const age = Date.now() - new Date(current.lastUpdated).getTime()
        if (age < 25000) return
      }

      setLoading(true)
      try {
        const q = await fetchQuota()
        if (q) setQuota(q)
      } catch (err: any) {
        setQuota((prev) => (prev ? { ...prev, error: err.message } : null))
      } finally {
        setLoading(false)
      }
    }

    refresh(false)
    const timer = setInterval(() => refresh(true), 45000)

    const stopExecutionListener = context.data.on("session.execution.succeeded", () => {
      refresh(true)
    })

    const getQuotaColor = (pct: number) => {
      if (pct < 30) return context.theme.text.feedback.error.base
      if (pct < 70) return context.theme.text.feedback.warning.base
      return context.theme.text.base
    }

    const getContextColor = (pct: number) => {
      if (pct >= 90) return context.theme.text.feedback.error.base
      if (pct >= 75) return context.theme.text.feedback.warning.base
      return context.theme.text.base
    }

    const formatTokenCount = (n: number) => {
      if (n >= 1_000_000) return (n / 1_000_000).toFixed(2).replace(/\.00$/, "") + "M"
      if (n >= 10_000) return (n / 1000).toFixed(2).replace(/\.00$/, "") + "K"
      return n.toLocaleString("en-US")
    }

    const makeBar = (pct: number, totalLen = 30) => {
      const filled = Math.min(totalLen, Math.max(0, Math.round((pct / 100) * totalLen)))
      return {
        filled: "█".repeat(filled),
        empty: "░".repeat(totalLen - filled),
      }
    }

    const currencyFormatter = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" })

    // 1. Context-Bereich (mit Fortschrittsbalken)
    const ContextSection = (props: { sessionID?: string }) => {
      const session = () => (props.sessionID ? context.data.session.get(props.sessionID) : undefined)
      const messages = () => (props.sessionID ? context.data.session.message.list(props.sessionID) : [])
      const cost = () => (props.sessionID ? context.data.session.cost(props.sessionID) : 0)

      const models = () => {
        const s = session()
        return context.data.location.model.list(s?.location ?? context.location)
      }

      const contextInfo = () => {
        const msgs = messages()
        if (!msgs || msgs.length === 0) return null
        const s = session()
        const revertID = s?.revert?.messageID

        const limitIdx = revertID ? msgs.findIndex((m) => m.id === revertID) : -1
        const endIdx = limitIdx === -1 ? msgs.length : limitIdx

        const compactionIdx = msgs.findLastIndex(
          (m, i) => m.type === "compaction" && m.status === "completed" && i < endIdx
        )

        const lastAssistant = msgs.findLast(
          (m, i) => m.type === "assistant" && m.tokens && i > compactionIdx && i < endIdx
        )
        if (!lastAssistant || !lastAssistant.tokens) return null

        const t = lastAssistant.tokens
        const total = (t.input || 0) + (t.output || 0) + (t.reasoning || 0) + (t.cache?.read || 0) + (t.cache?.write || 0)
        if (total <= 0) return null

        const modList = models()
        const modelInfo = modList?.find(
          (m) => m.providerID === lastAssistant.model?.providerID && m.id === lastAssistant.model?.id
        )
        const contextLimit = modelInfo?.limit?.context

        let percent: number | undefined
        if (contextLimit && contextLimit > 0) {
          percent = Math.round((total / contextLimit) * 100)
        }

        return {
          tokens: total,
          limit: contextLimit,
          percent,
        }
      }

      return (
        <Show when={contextInfo() || cost() > 0}>
          <box flexDirection="column" gap={0} paddingBottom={1}>
            <text fg={context.theme.text.base}>
              <b>Context</b>
            </text>

            <Show when={contextInfo()}>
              {(info) => {
                const inf = info()
                const pct = () => inf.percent ?? 0
                const bar = () => makeBar(pct(), 30)
                const tokenStr = () => {
                  if (inf.limit) {
                    return `${inf.tokens.toLocaleString("en-US")} / ${formatTokenCount(inf.limit)} tokens`
                  }
                  return `${inf.tokens.toLocaleString("en-US")} tokens`
                }

                return (
                  <box flexDirection="column" gap={0}>
                    <text fg={context.theme.text.muted}>{tokenStr()}</text>
                    <Show when={inf.percent !== undefined}>
                      <box flexDirection="row">
                        <text fg={getContextColor(pct())}>{bar().filled}</text>
                        <text fg={context.theme.text.muted}>{bar().empty}</text>
                      </box>
                      <text fg={context.theme.text.muted}>{pct()}% used</text>
                    </Show>
                  </box>
                )
              }}
            </Show>

            <Show when={cost() > 0}>
              <text fg={context.theme.text.muted}>
                {currencyFormatter.format(cost())} spent
              </text>
            </Show>
          </box>
        </Show>
      )
    }

    // 2. QuotaRow mit gerader Spaltenausrichtung
    const QuotaRow = (props: { label: string; pct: number; reset: string }) => {
      const fill = () => Math.min(10, Math.max(0, Math.round(props.pct / 10)))
      const pctStr = () => String(props.pct).padStart(3) + "%"
      const labelStr = () => ("  " + props.label).padEnd(8)
      const resetStr = () => props.reset.padStart(7)

      return (
        <box flexDirection="row">
          <text fg={context.theme.text.muted}>{labelStr()}</text>
          <text fg={getQuotaColor(props.pct)}>{pctStr()}</text>
          <text fg={context.theme.text.muted}> [</text>
          <text fg={getQuotaColor(props.pct)}>{"█".repeat(fill())}</text>
          <text fg={context.theme.text.muted}>{"░".repeat(10 - fill()) + "] "}</text>
          <text fg={context.theme.text.muted}>{resetStr()}</text>
        </box>
      )
    }

    // 3. Quota-Bereich (dauerhaft geöffnet, ohne Aufklapp-Pfeil)
    const QuotaSection = () => {
      const q = quota()
      const g = q?.gemini
      const c = q?.claude

      return (
        <box flexDirection="column" gap={0}>
          <box flexDirection="row" gap={1}>
            <text fg={context.theme.text.base}>
              <b>Quota</b>
            </text>
            <text fg={context.theme.text.muted}>(Antigravity)</text>
            <Show when={loading()}>
              <text fg={context.theme.text.muted}>↻</text>
            </Show>
          </box>

          <Show
            when={q}
            fallback={
              <box paddingLeft={1}>
                <text fg={context.theme.text.muted}>Lade Kontingente…</text>
              </box>
            }
          >
            <box flexDirection="column" gap={0}>
              <text fg={context.theme.text.base}>• Gemini</text>
              <QuotaRow label="5h" pct={g!.sprint.pct} reset={g!.sprint.reset} />
              <QuotaRow label="Woche" pct={g!.weekly.pct} reset={g!.weekly.reset} />

              <text fg={context.theme.text.base}>• Claude / GPT</text>
              <QuotaRow label="5h" pct={c!.sprint.pct} reset={c!.sprint.reset} />
              <QuotaRow label="Woche" pct={c!.weekly.pct} reset={c!.weekly.reset} />
            </box>
          </Show>
        </box>
      )
    }

    // In der rechten Sidebar: Context (mit Balken) + Quota
    context.ui.slot({
      prepend: "sidebar.content",
      render: (input) => (
        <box flexDirection="column" gap={0}>
          <ContextSection sessionID={input?.sessionID} />
          <QuotaSection />
        </box>
      ),
    })

    return () => {
      clearInterval(timer)
      stopExecutionListener()
    }
  },
})
