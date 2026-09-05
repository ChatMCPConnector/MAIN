# GLM-Web-2-API-Recherche (Sep 2026)

Suche nach Projekten, die GLM-Web-UIs (chatglm.cn / chat.z.ai) als OpenAI-kompatible API freigeben.
Ziel: GLM 5.3 mit max reasoning (Zero/Think-Modus) kostenlos, bevorzugt über chatglm.cn mit JWT/refresh_token.

## Vergleich aller gefundenen Projekte

### Spitzenkandidaten

| # | Projekt | Stars | Backend | Sprache | Login nötig? | Max-Reasoning | Status |
|---|---|---|---|---|---|---|---|
| 1 | XxxXTeam/glm2api | 123★ | **chatglm.cn** | Python (uv) | **Nein — Guest-Mode** | ✅ `-think`-Suffix, `reasoning_effort`, deep-research | aktiv (2026-08-23), 34 Forks |
| 2 | hmjz100/Z.ai2api | 152★ | chat.z.ai | Python | Nein (Anonymous) | ✅ Think-Chain → `reasoning_content` | **archiviert** (2026-07-24) |
| 3 | ForgetMeAI/FreeGLMKimiAPI | 69★ | z.ai + **chatglm.cn** + Kimi | **Node.js** | z.ai: JWT / chatglm: refresh_token | ✅ (think-Modelle) | aktiv (2026-06-20) |
| 4 | izaart95-jpg/GLM-Free-API | 80★ | chat.z.ai | **Go** | Nein (Guest `x-preview-l`) | ✅ `reasoning_effort` high/max | sehr aktiv (täglich) |
| 5 | spf0209/FreeAI-Gateway (Chat2API-Fork) | 33★ | **chatglm.cn** + z.ai + Kimi/Qwen/MiniMax/DeepSeek | Node/TS | je Provider (refresh_token) | ✅ | aktiv (2026-03-29) |
| 6 | Godde3s/glm-free-api | 2★ | chat.z.ai | Go (Fork von #4) | JWT-Pool | ✅ | neu, +429-Failover |

### Zweite Liga

| Projekt | Stars | Backend | Anmerkung |
|---|---|---|---|
| D3-vin/GLM-ZAI-2API | 39★ | chat.z.ai (Go) | solide, zuletzt 2026-07-16 |
| FANATFANATA/DanyAPI | 26★ | deepseek+qwen (**kein GLM**) | Vorbild: public hosted instance `https://danyapi.cloudpub.ru/v1/` |
| zerox90x90/freeclaude | 10★ | deepseek+GLM | Anthropic-API für Claude Code |
| LLM-Red-Team/zhipuai-agent-to-openai | 58★ | alte Zhipu-Agent-API | veraltet (Mai 2024) |
| uicaster/GLM-WebApi | 0★ | chatglm.cn | Windows-GUI (Tkinter+Tray), simpel |
| SertraFurr/GLM4Free | 3★ | chat.z.ai ohne Account | Mini-Wrapper |
| yangxiangyou/glm2api | 3★ | chatglm.cn | 120-Commit-Fork von #1 mit Admin-Panel |
| hoangcoderr/glm2api | 1★ | chatglm.cn | TS-Fork |
| rohan1416242-sys/glm-bridge-railway | 0★ | z.ai | Railway-Deployment von #4 |

## Wichtige Erkenntnisse

1. **Domain-Trennung:** `chat.z.ai` (international, JWT aus localStorage `token`) und `chatglm.cn` (China, `chatglm_refresh_token`) sind verschiedene Backends. Tokens sind nicht austauschbar. Alle z.ai-Projekte sind technisch auch für chatglm-Nutzer relevant, aber nur FreeGLMKimiAPI (#3) und FreeAI-Gateway (#5) sprechen chatglm.cn nativ.

2. **chatglm.cn „max reasoning" = GLM-Zero-Preview**: Im glm2api-Quellcode verifiziert — `resolve_chat_mode()` aktiviert den Upstream-"zero"-Modus (Deep-Thinking), wenn `reasoning_effort` gesetzt ist, das Modell auf `-think` endet oder "zero" im Namen trägt. chatglm.cn bietet zusätzlich `glm-deep-research` und `glm-zero-preview` als eigene Deep-Reasoning-Modelle.

3. **glm2api-Modellexposition** (via `expand_model_variants`): `glm-5.3`, `glm-5.3-think`, `glm-5.3-search`, `glm-5.3-think-search` usw. + `cogView-4-250304` (Bilder) + `glm-4.1v-thinking-flashx` (Vision+Think).

4. **z.ai-Guest ist tot**: Unsere gehostete GLM-Free-API-Instanz lief kurz und warf dann konsequent 405 (Z.AI blockt Guest-Sessions). Z.ai2api wurde genau dann archiviert. chatglm.cn-Guest funktioniert dagegen weiterhin (glm2api holt sich selbst Guest-Tokens).

5. **Empfehlung**: **XxxXTeam/glm2api** im Codespace betreiben — Python/uv, Port 8000, Guest-Mode zum Sofort-Testen, eigenes refresh_token (token.txt, Multi-Account, Auto-Refresh mit Write-Back) für volle Power. OpenAI + Anthropic + Responses API → direkt via `@ai-sdk/openai-compatible` in opencode anbindbar. Sessions werden nach Request automatisch gelöscht (kein Kontext-Müll).

## Token-Anleitungen (aus den READMEs)

- **chatglm.cn refresh_token**: Login → F12 → Application → Local Storage → `chatglm_refresh_token` (oder Cookies). Alternativ via Network-Tab: `/user-api/user/refresh` → `Authorization: Bearer ...`
- **chat.z.ai JWT**: Login → F12 → Console → `localStorage.getItem('token')`

## Zweite Suchrunde (breit, allgemein für GLM — Sep 2026)

### Neue Top-Funde

| Projekt | Stars | Backend / Quelle | Sprache | Anmerkung |
|---|---|---|---|---|
| **eequaled/GLM_proxy** (`npm: glmproxy`) | 21★ | **AutoClaw** (autoclaw.z.ai Desktop-App) | Node | Liest Auth direkt aus AutoClaws Token-Datei; OpenAI **und** Anthropic-Format; Tool-Calls; Claude Code/Cursor/OpenCode-Integrationen; v2.6.0, aktiv (Sep 4) |
| **sitimas9/autoclaw2api** | 0★ | AutoGLM/Z.ai (AutoClaw backend) | Python/FastAPI | Gratis GLM-5.2, GLM-5 Turbo, DeepSeek via Google-SSO-Token-Pool (24h Auto-Refresh). OAuth-Route wurde Aug 26 deprecated → Token-Import manuell aus Desktop-App nötig; Chat-Completions Upstream LIVE |
| **guell11/OmniClaw-GLM-Proxy** | 3★ | AutoClaw | Node | OpenAI + Responses + Anthropic, Browser-Console, Tool-Calls, Model-Routing — Claude Code/Codex/OpenCode-ready |
| **stefandevo/glm-acp-agent** | 46★ | **GLM Coding Plan** (api.z.ai/api/coding/paas/v4) | TS | ACP-Agent (Zed/DevFlow): GLM-5.3, 5.3-Flash, 5 Turbo, 4.7 mit Thinking (`reasoning_content` → agent_thought_chunk), Vision via MCP — **benötigt Coding-Plan-Abo (nicht gratis)** |
| **1837620622/cto-new-openai-proxy** | 38★ | **cto.new** (Engine Labs) | Go | GPT-5.4 + **GLM-5.1** gratis über Account-Pool (Clerk-Cookie-Refresh, Dashboard). **Kein Function Calling** (Upstream ist eigener Agent) → nur Plan-Mode, kein Build-Mode |
| **gravixrdp/oxalpha-api** | 0★ | **oxalpha.com** | Python | FastAPI-Proxy auf oxalpha-Web-Chat (`z-ai/glm-5.3-flash` via OpenRouter/GMICloud upstream) |
| **loxalpha.com selbst** | — | oxalpha.com/api/chat | — | ⚠️ **Live getestet**: funktioniert ohne Key (XSRF-Session), liefert `z-ai/glm-5.3-flash` **mit reasoning-Feld** im OpenRouter-SSE-Format — aber **Cloudflare-Turnstile nach 2 Nachrichten/Tag** (Checkpoint 3) → für Agent-Nutzung unbrauchbar, nur gelegentliche manuelle Nutzung |
| **dwgx/WindsurfAPI** | 2964★ | Windsurf/Devin Desktop | JS | 100+ Modelle (inkl. GLM) als OpenAI/Anthropic/Gemini-API — braucht Windsurf-Subscription |
| **Wei-Shaw/sub2api** | 40.541★ | Claude/OpenAI/Gemini/Grok-Subscriptions | — | Ökosystem-Referenz für Subscription-2-API (kein GLM native) |
| **router-for-me/CLIProxyAPI** | 50.551★ | Antigravity, Codex, Claude Code, Grok Build | — | General-Proxy-Ökosystem (GLM nicht primary) |
| FANATFANATA/DanyAPI | 26★ | deepseek+qwen | Python | public hosted instance `https://danyapi.cloudpub.ru/v1/` (kein GLM) |
| LyubomirT/intense-rp-next | 197★ | LLM-Web-UIs (inkl. GLM) | Python | Desktop-App + OpenAI-API für SillyTavern (Rollenpiel-Fokus) |
| sebattfg/ZeroScript-Free | 213★ | ChatGPT/DeepSeek/Gemini/**Kimi/GLM**/Qwen/Arena/Meta | JS | Roblox-Studio-Agent (Browser-Extension + Bridge) — Nische |
| sunflower0305/claude-proxy | 34★ | DeepSeek/Qwen/GLM/MiniMax | — | Claude-Code-Proxy für eigene API-Keys |
| 0xgetz/mistral-bridge | 12★ | OpenAI→Mistral-Konversation für GLM-5.2 | — | Format-Übersetzer |
| rajakumar865465/Free-Claude-Code-Gateway | 6★ | Kimi/GLM/DeepSeek/OpenRouter | — | "Claude Code free" |
| Draxnyn/Puter.js-in-OpenCode | 0★ | **Puter.js** (GLM 4.7 Flash „unlimited") | — | Puter als Free-GLM-Quelle in OpenCode |
| ramkrishna3245/glm52-free-chat | 2★ | Puter | — | Browser-only Free-GLM-5.2-Chat |
| zyroxteamuk/ZyroxZLM | 0★ | GLM-4.5/4.6/4.7 | Node | API-Proxy + Live-Dashboard |
| sabyaghosh/glm-free-api-admin-panel | 0★ | chat.z.ai | Go+Next | Fork-Stil von GLM-Free-API + Admin-Panel |
| lothiann/Free-ZAI-Api | 3★ | z.ai | Python | neu (Sep 3) |
| Jasmyn-X/glm-coding-grabber | 5★ | — | Userscript | 智谱 GLM Coding Plan 自动抢购 (Flash-Sale-Bot) — Coding-Plans sind knapp! |
| MeIotCOM/CodingPlanQuota | 17★ | — | — | Quota-Checker für GLM-Coding-Plan (5h/Wochen-Reset) |
| OLmatter/llm-api-ledger | 21★ | — | — | Coding-Plan-Verbrauchs-Benchmark (Herstellerangabe vs. Messung) |

### Erkenntnisse Runde 2

1. **Neuer GLM-Kanal: AutoClaw** (autoclaw.z.ai, Zhipus eigenes Desktop-Coding-Tool mit GLM-5.3). Drei Brücken (glmproxy, autoclaw2api, OmniClaw) machen daraus lokale APIs — teils mit Tool-Calls. Voraussetzung: AutoClaw-Login (Google-SSO), OAuth-Auto-Registrierung wurde Aug 26 von Z.ai gedrosselt (405), Token-Import aus der Desktop-App nötig.
2. **oxalpha.com** ist ein Gratis-Webchat, der z-ai/glm-5.3-flash über OpenRouter-Freikontingente durchreicht — inkl. reasoning-Feld. Aber Cloudflare-Turnstile nach 2 Messages/Tag = für Agents tot.
3. **cto.new** bietet gratis GLM-5.1 (+GPT-5.4) — Account-Pool machbar, aber kein Function Calling → für opencode Build-Mode ungeeignet, Plan-Mode ok.
4. **GLM Coding Plan** (Zhipu-Abo) ist die offizielle, stabile Route (glm-acp-agent 46★) — kostet aber (~3€/Monat lite) und ist oft ausverkauft (daher Grabber-Bots). Kein „Free".
5. **Puter.js** als „unlimited free GLM"-Quelle taucht mehrfach auf (GLM 4.7 Flash) — Browser-only, Qualität/Rate-Limit unklar.
6. **Große Ökosysteme** (sub2api 40k★, CLIProxyAPI 50k★, WindsurfAPI 3k★) zeigen das Muster Subscription→API, sind aber für GLM-free nicht direkt nutzbar (Windsurf braucht eigenes Abo).

### Aktualisierte Gesamtwertung (GLM gratis + reasoning + Agent-tauglich)

1. **XxxXTeam/glm2api** (chatglm.cn, Guest + refresh_token, think/zero-Mode) — weiter Platz 1 für dein Ziel
2. **AutoClaw-Bridgen** (glmproxy/OmniClaw) — GLM-5.3 mit Tool-Calls, braucht AutoClaw-Account (Google-SSO, gratis) — stärkster Neuzugang, prüfenswert
3. izaart95-jpg/GLM-Free-API (chat.z.ai) — JPEG-only Guest tot (405), mit eigenem JWT noch ok
4. FreeGLMKimiAPI / FreeAI-Gateway — chatglm.cn-Refresh-Token-Support als Zweitverwertung ok
5. cto.new-Pool — kein Tool-Calling, nur Plan-Mode
6. oxalpha — Turnstile-Limit, nur manuell

