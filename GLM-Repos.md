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

## Verwandte Große (nicht GLM-spezifisch, aber relevant)

- songquanpeng/one-api (36.746★) — LLM-API-Management/-Gateway
- xiaoY233/Chat2API — Electron-Original von FreeAI-Gateway (GLM/Kimi/Qwen/MiniMax/DeepSeek/Z.ai/Perplexity)
- dwgx/WindsurfAPI (3k★) — Windsurf/Devin-Modelle als OpenAI-API (inkl. GLM)
