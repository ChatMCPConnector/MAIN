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
    lastUpdated: new Date(),
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

  return result
}

export default Plugin.define({
  id: "antigravity.quota",
  setup(context) {
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

    const stopExecutionListener = context.data.on("session.execution.succeeded", () => {
      refresh()
    })

    const getColor = (pct: number) => {
      if (pct < 30) return context.theme.text.feedback.error.base
      if (pct < 70) return context.theme.text.feedback.warning.base
      return context.theme.text.feedback.success.base
    }

    const showDetails = () => {
      const q = quota()
      if (!q) {
        refresh()
        return
      }
      const g = q.gemini
      const c = q.claude
      const updated = q.lastUpdated ? q.lastUpdated.toLocaleTimeString() : "gerade"
      const makeBar10 = (pct: number) => {
        const len = Math.min(10, Math.max(0, Math.round(pct / 10)))
        return "█".repeat(len) + "░".repeat(10 - len)
      }
      const msg = [
        "Antigravity Live-Kontingente (Google CloudCode):",
        "",
        `Gemini (Flash & Pro):`,
        `  • 5h:    ${g.sprint.pct}% [${makeBar10(g.sprint.pct)}] Reset ${g.sprint.reset}`,
        `  • Woche: ${g.weekly.pct}% [${makeBar10(g.weekly.pct)}] Reset ${g.weekly.reset}`,
        "",
        `Claude & GPT (Opus, Sonnet, GPT-OSS):`,
        `  • 5h:    ${c.sprint.pct}% [${makeBar10(c.sprint.pct)}] Reset ${c.sprint.reset}`,
        `  • Woche: ${c.weekly.pct}% [${makeBar10(c.weekly.pct)}] Reset ${c.weekly.reset}`,
        "",
        `Stand: ${updated}${q.error ? ` (${q.error})` : ""}`,
      ].join("\n")

      context.ui.dialog.alert({
        title: "⚡ Antigravity Quota Status",
        message: msg,
      })
    }

    context.keymap.layer(() => ({
      mode: "global",
      commands: [
        {
          id: "antigravity.quota.details",
          title: "Show Antigravity Quota",
          group: "Antigravity",
          palette: true,
          suggested: true,
          run: () => showDetails(),
        },
        {
          id: "antigravity.quota.refresh",
          title: "Refresh Antigravity Quota",
          group: "Antigravity",
          palette: true,
          run: () => refresh(),
        },
      ],
    }))

    // Eine Quota-Zeile mit pixelgenauer Spaltenausrichtung
    const QuotaRow = (props: { label: string; pct: number; reset: string }) => {
      const fill = () => Math.min(10, Math.max(0, Math.round(props.pct / 10)))
      const pctStr = () => String(props.pct).padStart(3) + "%"
      const labelStr = () => ("  " + props.label).padEnd(8)
      const resetStr = () => props.reset.padStart(7)

      return (
        <box flexDirection="row">
          <text fg={context.theme.text.muted}>{labelStr()}</text>
          <text fg={getColor(props.pct)}>{pctStr()}</text>
          <text fg={context.theme.text.muted}> [</text>
          <text fg={getColor(props.pct)}>{"█".repeat(fill())}</text>
          <text fg={context.theme.text.muted}>{"░".repeat(10 - fill()) + "] "}</text>
          <text fg={context.theme.text.muted}>{resetStr()}</text>
        </box>
      )
    }

    // Sidebar-Bereich: Dauerhaft geöffnet, ohne Aufklapp-Pfeil, sauber ausgerichtet
    const SidebarSection = () => {
      const q = quota()
      const g = q?.gemini
      const c = q?.claude

      return (
        <box flexDirection="column" gap={0}>
          {/* Header ohne Pfeil */}
          <box flexDirection="row" gap={1}>
            <text fg={context.theme.text.base}>
              <b>Quota</b>
            </text>
            <text fg={context.theme.text.muted}>(Antigravity)</text>
            <Show when={loading()}>
              <text fg={context.theme.text.muted}>↻</text>
            </Show>
          </box>

          {/* Inhalt direkt dauerhaft sichtbar */}
          <Show
            when={q}
            fallback={
              <box paddingLeft={1}>
                <text fg={context.theme.text.muted}>Lade Kontingente…</text>
              </box>
            }
          >
            <box flexDirection="column" gap={0}>
              {/* Gemini */}
              <text fg={context.theme.text.base}>• Gemini</text>
              <QuotaRow label="5h" pct={g!.sprint.pct} reset={g!.sprint.reset} />
              <QuotaRow label="Woche" pct={g!.weekly.pct} reset={g!.weekly.reset} />

              {/* Claude */}
              <text fg={context.theme.text.base}>• Claude / GPT</text>
              <QuotaRow label="5h" pct={c!.sprint.pct} reset={c!.sprint.reset} />
              <QuotaRow label="Woche" pct={c!.weekly.pct} reset={c!.weekly.reset} />
            </box>
          </Show>
        </box>
      )
    }

    // Registrierung ausschließlich in der rechten Sidebar
    context.ui.slot({
      append: "sidebar.content",
      render: () => <SidebarSection />,
    })

    return () => {
      clearInterval(timer)
      stopExecutionListener()
    }
  },
})
