import { Plugin } from "@opencode/plugin/tui"
import { createSignal, onCleanup } from "solid-js"
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
  lastUpdated?: Date
  error?: string
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

  const creds = JSON.parse(fs.readFileSync(credsPath, "utf8"))
  if (!creds.access_token) {
    return {
      gemini: { sprint: { pct: 100, reset: "" }, weekly: { pct: 100, reset: "" } },
      claude: { sprint: { pct: 100, reset: "" }, weekly: { pct: 100, reset: "" } },
      error: "Kein Token",
    }
  }

  const res = await fetch("https://daily-cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary", {
    method: "POST",
    headers: {
      Authorization: "Bearer " + creds.access_token,
      "Content-Type": "application/json",
      "User-Agent": "antigravity/cli/1.1.13 (aidev_client; os_type=linux; arch=amd64; cl=964361259; auth_method=consumer)",
    },
    body: JSON.stringify({ project: "aicode-consumers" }),
  })

  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`)
  }

  const data: any = await res.json()
  const result: QuotaState = {
    gemini: { sprint: { pct: 100, reset: "" }, weekly: { pct: 100, reset: "" } },
    claude: { sprint: { pct: 100, reset: "" }, weekly: { pct: 100, reset: "" } },
    lastUpdated: new Date(),
  }

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

  return result
}

export default Plugin.define({
  id: "antigravity.quota",
  setup(context) {
    console.log("ANTIGRAVITY_QUOTA_SETUP: width=", context.renderer?.width)
    const [quota, setQuota] = createSignal<QuotaState | null>(null)
    const [loading, setLoading] = createSignal(false)

    const refresh = async () => {
      if (loading()) return
      setLoading(true)
      try {
        const q = await fetchQuota()
        setQuota(q)
      } catch (err: any) {
        setQuota((prev) => (prev ? { ...prev, error: err.message } : null))
      } finally {
        setLoading(false)
      }
    }

    refresh()
    const timer = setInterval(refresh, 45000)

    const showDetails = () => {
      const q = quota()
      if (!q) {
        refresh()
        return
      }
      const g = q.gemini
      const c = q.claude
      const updated = q.lastUpdated ? q.lastUpdated.toLocaleTimeString() : "gerade"
      const msg = [
        "Antigravity Live-Kontingente (Google CloudCode):",
        "",
        `Gemini (Flash & Pro):`,
        `  • 5h-Sprint:    ${g.sprint.pct}% [${makeBar(g.sprint.pct)}] Reset ${g.sprint.reset}`,
        `  • Wochen-Limit: ${g.weekly.pct}% [${makeBar(g.weekly.pct)}] Reset ${g.weekly.reset}`,
        "",
        `Claude & GPT (Opus, Sonnet, GPT-OSS):`,
        `  • 5h-Sprint:    ${c.sprint.pct}% [${makeBar(c.sprint.pct)}] Reset ${c.sprint.reset}`,
        `  • Wochen-Limit: ${c.weekly.pct}% [${makeBar(c.weekly.pct)}] Reset ${c.weekly.reset}`,
        "",
        `Stand: ${updated}${q.error ? ` (${q.error})` : ""}`,
      ].join("\n")

      context.ui.dialog.alert({
        title: "⚡ Antigravity Quota Status",
        message: msg,
      })
    }

    function makeBar(pct: number): string {
      const len = Math.min(10, Math.max(0, Math.round(pct / 10)))
      return "█".repeat(len) + "░".repeat(10 - len)
    }

    const getColor = (pct: number) => {
      if (pct < 30) return context.theme.text.feedback.error.base
      if (pct < 70) return context.theme.text.feedback.warning.base
      return context.theme.text.muted
    }

    const QuotaView = () => {
      const q = quota()
      if (!q) {
        return (
          <box flexDirection="row" onMouseUp={refresh}>
            <text fg={context.theme.text.muted}>⚡ Quota…</text>
          </box>
        )
      }

      const gSprint = q.gemini.sprint.pct
      const gWeek = q.gemini.weekly.pct
      const cSprint = q.claude.sprint.pct
      const cWeek = q.claude.weekly.pct

      const width = context.renderer?.width ?? 120
      const compact = width < 100

      if (compact) {
        return (
          <box flexDirection="row" gap={1} onMouseUp={showDetails}>
            <text fg={context.theme.text.muted}>⚡</text>
            <text fg={getColor(Math.min(gSprint, gWeek))}>G:{gSprint}%</text>
            <text fg={context.theme.text.muted}>·</text>
            <text fg={getColor(Math.min(cSprint, cWeek))}>C:{cSprint}%</text>
          </box>
        )
      }

      return (
        <box flexDirection="row" gap={1} onMouseUp={showDetails}>
          <text fg={context.theme.text.muted}>⚡</text>
          <text fg={context.theme.text.muted}>G:</text>
          <text fg={getColor(gSprint)}>{gSprint}%</text>
          <text fg={context.theme.text.muted}>/</text>
          <text fg={getColor(gWeek)}>{gWeek}%</text>
          <text fg={context.theme.text.muted}>│</text>
          <text fg={context.theme.text.muted}>C:</text>
          <text fg={getColor(cSprint)}>{cSprint}%</text>
          <text fg={context.theme.text.muted}>/</text>
          <text fg={getColor(cWeek)}>{cWeek}%</text>
        </box>
      )
    }

    context.ui.slot({
      append: "home.footer",
      render: () => <QuotaView />,
    })

    context.ui.slot({
      append: "prompt.footer",
      render: () => <QuotaView />,
    })

    return () => clearInterval(timer)
  },
})
