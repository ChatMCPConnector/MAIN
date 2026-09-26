# Kostenlose Modelle in Coding-CLIs — Recherche-Snapshot 2026-09-26

Snapshot, keine Infrastruktur-Änderung. Free-Tiers ändern sich schnell →
Datum im Dateinamen. Angaben nach offiziellen Quellen (s. u.); mit
„(reported)" markiertes nur über Recherche-Subagenten belegt, nicht selbst
gegengefetcht.

## A. Kostenlos nutzbare CLIs (kein eigener API-Key nötig)

| Tool | Install / Login | Free-Umfang | Modelle | Haken |
|---|---|---|---|---|
| **Antigravity CLI** (`agy`) | `curl -fsSL https://antigravity.google/cli/install.sh \| bash`; Google-Login (oder `GEMINI_API_KEY` via `modelProvider: gemini`, Custom-Endpoint via `GOOGLE_GEMINI_BASE_URL`) | Individuen $0/Monat; „basic weekly rate limits"; unbegrenzte Tab-/Command-Requests | Gemini 3.8/3.7/3.6 Flash, Gemini 3.1 Pro, **Claude Sonnet & Opus 4.6**, gpt-oss-120b | Nachfolger des Gemini-CLI-Free-Tiers (18.06.2026); Google-Konto |
| **Gemini CLI** | npm/`gemini`; Google-Login | **Unpaid/Google-One-Tier ersetzt** durch Antigravity CLI (18.06.2026, offizielles Banner); API-Key-Pfad bleibt (AI-Studio-Free, Datenverbesserung) | Gemini-3-Familie | Free via Google-Konto praktisch Geschichte |
| **Kiro CLI** (AWS) | kiro.dev, Social-/Builder-ID-Login | **Free: 50 Credits/Monat** (perpetual), rate-limited | Claude Sonnet 4.5, Qwen3 Coder Next, DeepSeek 3.2, MiniMax M2.1 | Credits statt Requests; Pro $20 |
| **Kilo Code CLI** | Kilo-Account (free, keine Karte) | **17 aktive $0-Modelle** (Live-Katalog) | Hy3 (free), Nemotron 3 Super (free), Space Bunny Alpha (1M ctx), MiniMax M3 (1M ctx), Ling 3.0 Flash VL, Nex-N2.5-Pro, Dots3-Note … | Anaconda/EU (Amsterdam); Promotion-Modelle können enden |
| **Cline CLI** | `npm i -g cline`, Cline-Account | Rotierende **FREE-Promo-Modelle** (IDE+CLI, nicht API) mit Quota | wechselnd (Picker) | Quota danach ClinePass $9.99/Mo; Free-Nutzung kann Modelltraining sein |
| **Freebuff** | `npm i -g freebuff`, Account, keine Karte | **100 Freebucks/Tag**; Stunden/Tag je Modell: GLM 5.3 Flash 20h, Solar Mini 4 20h, MiMo 2.6 Flash 10h, DeepSeek V4.1 Flash 6h, GPT-6 Luna 5h …; Space Bunny Alpha ohne Verbrauch | s. links; Gemini 3.8 Flash nur bezahlt | **Werbefinanziert**, Prompts ggf. für Ad-Personalisierung; Session-Limits; Zugang landes-/VPN-abhängig; kein Firmencode |
| **CodeBuddy CLI** (Tencent) | CodeBuddy-Account | Free: **100 Credits/Monat** + Promo **30/Tag** + 250 Welcome; 5.000 Completions | Auto-Routing (in Promo alle Modelle) | Promo-Konditionen befristet |
| **Qoder CLI** (Alibaba) | Qoder-Account | Credits-Metering; Free-Tier + „100 Credits/Tag"-Event (reported) | Qwen-Serie | Free-Kontingent nicht offiziell publiziert |
| **GitHub Copilot CLI** | GitHub-Login | Copilot Free: 2.000 Completions + kleines AI-Credit-Budget (Höhe nicht publiziert); CLI in allen Plänen verfügbar | Auto-Auswahl | Budget klein, unquantifiziert |
| **OpenCode Zen** (bereits im Repo!) | im opencode: `/connect` → Zen, API-Key aus Zen-Konsole | Free-Modelle ohne publizierte Raten-Limits (nur eigenes Budget) | Big Pickle, Space Bunny Free, LongCat 2.5 Preview Free, MiMo-V2.6-Flash Free, MiMo-V2.5 Free, Ling 3.0 Flash Fin Free, Nemotron 3 Ultra Free, Nemotron 3.5 Lightning Free, Muse Spark 1.3 Contributor Free, Jev 1.13 Free | Einige Modelle: Daten zur Modellverbesserung (Big Pickle/MiMo/Ling), NVIDIA-Trial-Logging, Muse Spark → Meta-Training; US-Hosting |

## B. Kostenlose BYOK-Pools (für opencode / Crush / Aider / Goose / Qwen Code)

| Provider | Free-Limits | Coding-Modelle | Quelle |
|---|---|---|---|
| **Groq** | 30 RPM / 1.000 RPD / 200K TPD (gpt-oss-120b, gpt-oss-20b, qwen3.8-27b) | GPT-OSS, Qwen3.8 | console.groq.com/docs/rate-limits — Groq dokumentiert **OpenCode/Kilo/Cline/Roo/Droid**-Integrationen |
| **OpenRouter** | `:free`-Modelle: 20 RPM, 50 RPD; **1.000 RPD ab ~$10 Lifetime-Credits** | ~21 `:free`-Modelle (qwen3.8-27b, nemotron-3-ultra, cohere/north-mini-code, poolside/laguna …) | openrouter.ai/docs/api-reference/limits |
| **NVIDIA NIM** | Free-Endpoints bis 40 RPM / 10k RPD (reported); im Repo bereits via `nvidia-models.py` | Kimi K3, DeepSeek V4 Pro/Flash, Nemotron | build.nvidia.com |
| **Google AI Studio API-Key** | Free-Tier (Limits nur in AI Studio sichtbar; Daten werden zur Produktverbesserung genutzt) | Gemini 3.8 Flash, 3.1 Pro | ai.google.dev |
| **Z.ai (Zhipu)** | GLM-4.7-Flash / GLM-4.5-Flash = $0 (reported) | GLM-Flash-Serie | docs.z.ai |
| **Cloudflare Workers AI** | 10.000 Neurons/Tag (reported) | qwen3-30b, qwen2.5-coder-32b, gpt-oss, glm-4.7-flash | developers.cloudflare.com |
| **Alibaba ModelStudio** | 1 Mio. Tokens/Modell, 90 Tage (nur SG) | Qwen inkl. Coder | alibabacloud.com/help/en/model-studio/new-free-quota |
| **SambaNova** | 20 RPM / 20 RPD / 200K TPD (reported) | DeepSeek V3.2, gpt-oss-120b | docs.sambanova.ai |
| **Ollama/LM Studio (lokal)** | unbegrenzt, eigene Hardware | qwen3-coder 30B, gpt-oss-20B, devstral, laguna-xs | ollama.com |

## C. 2026 gestrichen / geändert (wichtig)

- **iFlow CLI**: eingestellt zum 17.04.2026 (offizielles Banner im Repo).
- **Qwen Code Free-OAuth**: 15.04.2026 geschlossen (GitHub-Issue #3203) → nur noch BYOK/ModelStudio.
- **Gemini CLI Free**: seit 18.06.2026 → Antigravity CLI.
- **Amazon Q Developer**: End-of-Support angekündigt; Neue Signups ab 15.05.2026 gestoppt, IDE-Plugins bis 30.04.2027; Nachfolger **Kiro** (Top-Modelle exklusiv dort).
- **GitHub Models**: retired seit 30.07.2026 (reported).
- **Cerebras**: kein dauerhafter Free-Tier mehr, nur $5-Trial mit Karte (reported).
- **Roo Code**: eingestellt 15.05.2026, Community-Fork „Zoo Code" (reported).
- **Sourcegraph**: „Amp Free" (werbefinanziert) weg; Cody nur Enterprise (reported).
- **Codebuff**: kostenpflichtig (ab $100/Mo); Free-Ableger = Freebuff (reported).
- **Tabnine CLI**: Produkt eingestellt (reported).

## D. Empfehlung für dieses Repo

1. **Sofort, ohne neues Tool:** opencode `/connect` → Zen, Free-Modelle wählen (Space Bunny Free / Nemotron / MiMo) — nur für Code ohne Vertraulichkeit.
2. **Stärkster Gratis-Zugang:** offizielle **Antigravity CLI** (`agy`) — Gemini 3.8 Flash + Claude 4.6 gratis, sanktionierter Weg (Alternative zum inoffiziellen Proxy); `GOOGLE_GEMINI_BASE_URL` erlaubt Custom-Endpoints.
3. **Zweit-Tool mit Planbarkeit:** Kiro CLI Free (50 Credits/Mo) oder Kilo Code (17 $0-Modelle, EU).
4. **BYOK-Pools** für opencode: Groq (großzügig, schnell), OpenRouter `:free`, NVIDIA (im Repo), Z.ai GLM-Flash.
5. **Vorsicht:** Freebuff = werbefinanziert/Datenräume beachten; Cline-Promo/Freebuff/Zen-Free nie mit Secrets/Kundencode füttern.

## Quellen (selbst geprüft am 2026-09-26)

antigravity.google/pricing · antigravity.google/docs/cli/install/ · geminicli.com/plans/ · kiro.dev/pricing/ · kilocode.ai/landing/free-models · docs.cline.bot/getting-started/free-models · freebuff.com · opencode.ai/docs/zen/ (+ sst/opencode zen.mdx) · codebuddy.ai/docs/ide/Account/pricing · docs.qoder.com/cli/usage · console.groq.com/docs/rate-limits · openrouter.ai/docs/api-reference/limits · github.com/QwenLM/qwen-code/issues/3203 · github.com/iFlow-ai/iflow-cli · aws.amazon.com/blogs/devops/amazon-q-developer-end-of-support-announcement/ · docs.github.com/en/copilot/get-started/plans

