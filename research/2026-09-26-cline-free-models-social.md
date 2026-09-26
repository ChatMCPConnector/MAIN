# Social-Media-Recherche: Cline & kostenlose Modelle (X/Twitter + LinkedIn)

**Stand:** 2026-09-26 · **Scope:** Fokus letzte ~12 Monate · **Autor:** x-scout (Team t_jwr3krzq_2)
**Methodenhinweis:** Eine native X-Suche ist ohne Login nicht zugänglich. Belege stammen aus: (a) direkt abrufbaren Tweet-Statusseiten (einige funktionieren), (b) Profil-Spiegel sotwe.com, (c) Suchmaschinen-Snippets (Brave Search, Google News RSS), (d) HN-Algolia-API, (e) LinkedIn-URLs/Snippets + aus Activity-IDs abgeleiteten Datumsangaben. Nichts ist erfunden; nicht direkt Verifizierbares ist ausdrücklich markiert.

## 1) Kernbefunde

- Cline bewirbt seit 2025 **rotierende Gratis-Modelle** über den eigenen Provider („Cline usage-billing", Modelle mit FREE-Tag) sowie teilweise über ClinePass. Es ist kein dauerhaftes „Free Tier", sondern eine Folge befristeter Promos.
- **Aktueller Stand (Tracker-Stand 25.09.2026):** freellm.net listet 6 aktive Gratis-Modelle für Cline CLI/IDE: Gemini 3.8 Flash, DeepSeek V4.1 Flash, MiMo V2.6 Flash, Muse Spark 1.3 Contributor, Space Bunny Alpha, Pixel Canary.
- **Bedingungen (laut Cline-Doku, Stand 29.07.2026):** Cline-Konto nötig, Quota-begrenzt, rotierend, **nur IDE-Extension + CLI, nicht über die Cline-API**; danach ClinePass (9,99 $/Monat) oder Pay-as-you-go. Datenschutz-Hinweis: „Free model usage may be used to help improve model performance and quality."
- **Größte Einzelaktion:** Grok Code Fast 1 (xAI) ab 28.08.2025, laut Cline „free for a week … without usage caps or throttling", am 12.09.2025 verlängert (Dauer unbekannt); xAI nannte Cline als Launch-Partner („free for a limited time").
- **2026 dominieren kurze Stealth-/Partner-Promos:** MiniMax M2.1, Kimi K2.5 (CLI), Nemotron 3.5 Lightning, LongCat-2.0, Kimi K3 (Desktop), Union Alpha, Stealth Bunny Alpha, Gemini 3.8 Flash, Pixel Canary — meist „limited time"/rotierend, ohne festes Enddatum.
- **Sentiment:** überwiegend positiv/neugierig (viel Engagement auf X); wiederkehrende Beschwerden über Quota-/Billing-Bugs bei Gratis-Modellen und Token-Hunger; vereinzelt Benchmark-Skepsis.

## 2) Ankündigungen mit Datum (chronologisch)

**2025**
- **11.03.2025** — Cline-Tweet (zitiert in GitHub cline/cline#2196): kostenlose Nutzung von DeepSeek R1/V3 mit Cline-Konto (https://twitter.com/cline/status/1899536428700500105).
- **10.04.2025** — Cline (LinkedIn, clinebot): „Another free stealth model from @OpenRouterAI"; zweiter Post „Now available in Cline: The full Grok 3 model family from xAI" (Datum aus LinkedIn-Activity-ID abgeleitet).
- **13.05.2025** — Cline (LinkedIn, clinebot): „Want to try Cline for free? @OpenRouter has free models…" (ID-abgeleitet).
- **22.07.2025** — Addy Osmani (LinkedIn): „Cline is a free, best-in-class AI coding assistant for VS Code!" (ID-abgeleitet).
- **~21.08.2025** — Stealth-Modell „Sonic" erscheint in Cline; am 28.08. als Grok Code Fast enttarnt.
- **28.08.2025** — Cline-Blog: „Grok Code Fast 1 … (Free for a Week)": „We're offering Grok Code Fast completely free during the launch period. This isn't a trial with hidden limitations – you get full access … without usage caps or throttling." Danach xAI-Preise ($0,20/$1,50/$0,02 pro 1M Tokens). Zusätzlich Blog v3.26.6: Qwen-Code-Provider mit **2.000 Gratis-Requests/Tag** (qwen3-coder-plus/flash, 1M Kontext) und lokaler Gratis-Stack via LM Studio. xAI-News (28.08.2025): „We've teamed up with select launch partners to offer grok-code-fast-1 for free for a limited time, including GitHub Copilot, Cursor, **Cline**, Roo Code, Kilo Code, opencode, and Windsurf."
- **05.09.2025 / 09.09.2025** — Kimi K2-0905 bzw. Sonoma Alpha Sky & Dusk in Cline.
- **12.09.2025** — Cline-Blog v3.28: „Today was supposed to be the day free access to grok-code-fast-1 ended. xAI extended it. We don't know for how long :)"
- **Herbst 2025** — „code-supernova": „free access during launch" (Blog-Tag-Index).
- **02.12.2025** — Stealth „microwave": „Free during alpha; no usage limits while it's being refined"; explizit: „Your usage during the alpha period helps the lab refine the model's performance."
- **09.12.2025** — Devstral 2 („best open-weights model for Cline").
**2026**
- **06.01.2026** — Cline-Blog: „MiniMax M2.1 is free through Thursday" — Gratisphase endet **09.01.2026, 19:00 PST**; danach Standardpreise.
- **03.02.2026** — Cline-Blog: „Announcing Cline CLI 2.0 with free Kimi K2.5" — „limited-time free trial powered by Kimi K2.5" (HN-Story gleichentags).
- **29.06.2026** — ClinePass-Launch (Blog): 9,99 $/Monat, „Standard rate $9.99 per month after promotion period" — kein Gratisangebot, aber häufig mit Free-Modellen verwechselt.
- **11.08.2026** — Cline-Blog: NVIDIA Nemotron 3.5 Lightning „now available in Cline for FREE"; Auswahl über „FREE model dropdown" mit Cline-Konto. NVIDIA-Developer-Blog (11.08.2026) verlinkt die Cline-Integration; eine explizite „free"-Aussage von NVIDIA zu Cline ließ sich dort nicht verifizieren.
- **01.09.2026** — @cline (X): „LongCat-2.0 is free in Cline right now. It's a 1.6T open weights MoE model with 1M context from @Meituan_LongCat scoring similar to Claude Opus 4.7 and Gemini 3.1 Pro. Try now: npm i -g cline /model — Choose LongCat-2.0 under free models."
- **02.09.2026** — @Meituan_LongCat (X, 03:50 Uhr) zitiert den @cline-Tweet: „LongCat-2.0 is now free to try in @cline ! 🐱" (9.827 Views, 197 Likes, 13 Reposts, 22 Bookmarks; Reaktionen: @smartpass979 „Long and free love y guys!", @KridayTop „🔥", @cixier auf Chinesisch: 1,6T+1M-Kontext gratis in Cline, während Frontier-Anbieter noch Cache-Rabatte verkaufen 😂).
- **14.09.2026** — Cline Desktop Launch (Blog) + gepinnter @cline-Tweet: „Use with ClinePass and **all our free models** like DeepSeek-V4.1-Flash, Musespark-1.3, or BYOK with any provider!" (≈999K Views, 2K Likes). Aggregator blockchain.news (14.09.2026, via Tweet von @_avichawla): „Cline Desktop now offers free DeepSeek V4 Flash, GLM 5.3 Flash, and Laguna S 2.1 with repo-level debugging."
- **16.09.2026** — @cline (X, 16:47): „Union Alpha (stealth model) is now free in Cline. 256k context, multimodal, built for agentic coding. It is near GPT-6 Astra and Opus 5 performance for ~18x lower expected cost." (151,2K Views, 2,6K Likes, 137 Reposts). Cline-Reply: „The model could be a bit slow right now – still working with upstream provider to improve it." Dritt-Tracker freetokens (#414, 16.09.2026): „rate limited… Expiry: ongoing — no fixed end date (rotating promotion)".
- **17.09.2026** — Cline (LinkedIn, clinebot): „Union Alpha (stealth model) is free in Cline" (Datum ID-abgeleitet; inhaltlich passend zum X-Post).
- **~19.09.2026** — @cline (X, nur als Brave-Snippet; Status-URL lieferte 404): „Kimi K3 is now free in Cline Desktop to celebrate all the new users … (…for a limited time, we'll keep it running as long as we can!)"; ergänzend Sotwe-Profil (23.09.): „Try the desktop app for free with our Kimi K3 promo now".
- **~23.09.2026** — @cline (X, via Sotwe-Snapshot 26.09.): „Stealth Bunny Alpha is now free in Cline. It's a stealth model with fast inference, strong coding capabilities, multimodal input support, and a 1M-token context window." (362 Likes).
- **~24.09.2026** — @cline (X, via Sotwe): „Gemini 3.8 Flash is free in Cline. It scores 41 on the Artificial Analysis Intelligence Index … 291 tok/s, 1M context …" (1K Likes, 122K Views).
- **~25./26.09.2026** — @cline (X, via Sotwe): „Pixel Canary (stealth model) has just released and is free in Cline. It's tied with GPT-6 Astra and beats Kimi K3 on Next.js Agent Evals …" (2K Likes, 159K Views, 97 Comments).
- **25.09.2026** — freellm.net (Tracker, „Last Updated 2026-09-25"): 6 aktive Cline-Gratis-Modelle (s. o.); Hinweise: „quota-limited", „account-based", „not … through the Cline API", „may rotate without notice", ggf. Kreditkarte nötig; Score 47/100 („Niche Provider").
## 3) Dev-Reaktionen / Sentiment

**Positiv / Begeisterung**
- HN, @tripplyons (19.09.2025): grok-code-fast-1 sei „really impressive … currently free on many platforms (… **Cline** …)"; @theshrike79 (23.09.2025): „Cline+Grok Code Fast fix[ed] an issue caused by Claude … who ran out of credits mid-fix"; @jasonvorhe (09.11.2025): Free-Modelle seien „just part of many free tiers … like Cline", sein Refactoring „a breeze".
- X: LongCat-/Union-Alpha-/Pixel-Canary-Promos erzielen 10K–159K Views und hunderte bis tausende Likes; Tenor in Replies: „🔥", „Long and free …".

**Skepsis / Kritik**
- X, @demfabris (16.09.2026, zu Union Alpha): „huge if not benchmaxed like gemini" – typische Benchmark-Skepsis bei Stealth-Modellen.
- DEV Community (02.06.2026): „Cline Review 2026: Is the Best Free AI Coding Agent Actually Free?" – Grundtenor: „gratis" gilt nur mit Gratis-Modellen/Quota, sonst teuer.
- Reddit r/CLine (22.06.2026, Thread „Best free model for Cline?"): „DeepSeek V4 Flash Free with the Cline Provider … works ok"; Kommentar: „V4 flash, no exception. **Just be aware of limits**"; scharfe Kostenkritik: „Cline chews through tokens like candy … $20 for a Claude subscription … will likely go a lot further than Cline plus API credits."
- Reddit r/opencode (06.07.2026, „Has anyone figured out the actual limits of Cline Pass yet?"): Limits bleiben intransparent; ein Nutzer: „Cline seems similar to OpenCode Go and a little bit more generous on the limits."

**Beschwerden / Bugs bei Gratis-Modellen**
- GitHub cline/cline#2196 (11.03.2025): „Unable to use Cline's free models, 'Insufficient balance'" — Free-Modelle blockiert durch negatives Guthaben ($-0,06), obwohl als gratis beworben.
- Weitere Issues (per Brave-Snippet, nicht einzeln geöffnet): #2838 (12.04.2025, „Unjust Charges When Selecting Free Models with Cline + OpenRouter"), #7607 (21.11.2025), #8182 (18.12.2025, Devstral-2512 gratis ⇒ „Insufficient balance"), #10257 (13.04.2026, „balance negative").
- Reddit r/CLine (30.07.2025): Nutzer scheiterten an Free-Tier-Limits von Drittanbietern: „Rate limit exceeded: free-models-per-day. Add 10 credits to unlock 1000 free model requests per day" (OpenRouter-Bedingung, nicht Cline).

## 4) Status / Unsicherheiten

- **Aktueller Status:** Die Free-Model-Promos laufen weiter, aber stark rotierend. Bester belegbarer Stand: Tracker-Liste vom 25.09.2026 (6 Modelle) plus die @cline-Tweets bis 26.09.2026 (Pixel Canary). Union Alpha war am 16.09.2026 live (Tracker-Verifikation), fehlt aber in der Liste vom 25.09. — vermutlich rotiert (Inferenz, kein Beleg).
- **Grok-Promo:** Kein Hinweis auf ein Fortlaufen; Grok Code Fast 1 taucht in aktuellen Free-Listen nicht auf. Verlängerung am 12.09.2025 ohne bekanntes Enddatum; danach keine weiteren Belege gefunden.
- **Daten/Training:** Cline-Doku (Free-Models-Seite, Stand 29.07.2026): „Free model usage may be used to help improve model performance and quality." Beim Stealth-Modell „microwave" (02.12.2025): „Your usage during the alpha period helps the lab refine the model's performance." Für die xAI-Gratisaktion (08/2025) wurde keine Trainingsklausel gefunden (xAI-Seite nennt dazu nichts).
- **Unsicherheiten/Lücken:**
  1. X-Suche ist ohne Login nicht verfügbar; es konnten nur einzelne Status-URLs geladen werden. Vollständigkeit der Tweet-Liste ist daher nicht garantiert.
  2. Der Kimi-K3-Desktop-Tweet ist nur über ein Suchsnippet belegt; die Status-URL lieferte 404 (gelöscht, geschützt oder ID-Änderung — unklar).
  3. LinkedIn: keine Login-Ansicht; Inhalte nur über Suchindex + Post-URLs. Datumsangaben für LinkedIn-Posts sind aus den Activity-IDs abgeleitet (LinkedIn-Snowflake: erste 41 Bits = ms seit Epoche) — als „ca." zu behandeln.
  4. Engagement-Zahlen (Views/Likes) sind Momentaufnahmen vom 26.09.2026 aus dem sotwe-Profil-Spiegel bzw. von der Tweet-Seite und können abweichen.
  5. Einige GitHub-Issue-Details stammen aus Suchsnippets, nicht aus einzeln geöffneten Seiten.
  6. Keine belastbaren Treffer gefunden zu: Groq-Gratiszugang für Cline, Cerebras-Promo für Cline, exklusive Zhipu/GLM-Gratisaktion für Cline (GLM taucht nur im Kontext ClinePass/$ auf bzw. in einem Aggregator-Snippet zu „free DeepSeek/GLM Flash" in Cline Desktop).
## 5) Quellenliste (URL + Datum)

**Cline offiziell (Blog/Doku/X/LinkedIn)**
- https://cline.bot/blog/grok-code-fast — 28.08.2025 (Grok free for a week; „no usage caps or throttling")
- https://cline.bot/blog/cline-v3-26-6-three-ways-to-code-for-free — 28.08.2025 (Qwen 2.000 Req./Tag; lokaler Gratis-Stack)
- https://cline.bot/blog/cline-v3-28-free-grok-extended-gpt-5-optimized — 12.09.2025 (Grok-Verlängerung)
- https://cline.bot/blog/free-stealth-model-microwave-now-available-in-cline — 02.12.2025
- https://cline.bot/blog/cline-3-47-0-adds-background-edits-and-a-free-minimax-2-1 — 06.01.2026 (Gratis bis 09.01.2026)
- https://cline.bot/blog/announcing-cline-cli-2-0 — 03.02.2026 (freies Kimi K2.5, Trial)
- https://cline.bot/blog/nvidia-nemotron-3-5-lightning-available-in-cline — 11.08.2026
- https://cline.bot/blog/cline-desktop-an-open-source-app-for-open-weight-models — 14.09.2026
- https://cline.bot/cline-pass (ClinePass 9,99 $; „after promotion period") — Stand 26.09.2026
- https://docs.cline.bot/getting-started/free-models — Doku-Seite, Stand 29.07.2026 (Quota, rotierend, IDE+CLI only, „may be used to help improve model performance")
- https://twitter.com/cline/status/2100265266026590322 — 16.09.2026 (Union Alpha free; 151,2K Views) ✅ direkt geladen
- https://twitter.com/Meituan_LongCat/status/2094996391387111865 — 02.09.2026 (LongCat free in Cline; zitiert @cline vom 01.09.2026) ✅ direkt geladen
- https://twitter.com/cline/status/1899536428700500105 — 11.03.2025 (Free DeepSeek R1/V3; belegt via GitHub #2196)
- https://twitter.com/cline/status/2100995309656854903 — ~19.09.2026 (Kimi K3 free in Cline Desktop; nur Snippet, Abruf 404) ⚠
- sotwe.com/cline — Profil-Spiegel, Snapshot 26.09.2026 (Pixel Canary ~25./26.09.; Gemini 3.8 Flash ~24.09.; Stealth Bunny Alpha ~23.09.; Kimi-K3-Promo ~23.09.; gepinnter Desktop-Tweet 14.09.)
- LinkedIn (alle nur via Suchindex, Datum per Activity-ID abgeleitet): linkedin.com/posts/clinebot_want-to-try-cline-for-free-openrouter-has-activity-7328100429886558208-zKzf (~13.05.2025); linkedin.com/posts/clinebot_another-free-stealth-model-from-openrouterai-activity-7316169064186331136-sdhq (~10.04.2025); linkedin.com/posts/clinebot_now-available-in-cline-the-full-grok-3-model-activity-7316142272138395648-BFR1 (~10.04.2025); linkedin.com/posts/clinebot_union-alpha-stealth-model-is-free-in-cline-activity-7506376825288192000-M6td (~17.09.2026); linkedin.com/posts/addyosmani_ai-programming-softwareengineering-activity-7353310337279946753-X9Dh (~22.07.2025)

**Partner / Dritte**
- https://x.ai/news/grok-code-fast-1 — 28.08.2025 („free for a limited time" auf Launch-Partnern inkl. Cline)
- https://developer.nvidia.com/blog/nvidia-nemotron-3-5-lightning-delivers-fast-accurate-specialized-task-execution-for-long-running-agents/ — 11.08.2026 (verlinkt Cline)
- https://blockchain.news/ainews/open-weight-cline-desktop-adds-deepseek-and-glm — 14.09.2026 (via @_avichawla: free DeepSeek V4 Flash, GLM 5.3 Flash, Laguna S 2.1)
- https://freellm.net/providers/cline — Stand 25.09.2026 (6 aktive Gratis-Modelle; Bedingungen)
- https://github.com/luongnv89/freetokens/issues/414 — 16.09.2026 (Union Alpha: rate limited, kein Fix-Enddatum)
- https://github.com/cline/cline/issues/2196 — 11.03.2025 (Free-Modelle + „Insufficient balance")
- Issues #2838 (12.04.2025), #7607 (21.11.2025), #8182 (18.12.2025), #10257 (13.04.2026) — cline/cline, via Suchsnippet
- HN-Algolia: Story „Cline CLI 2.0 with free Kimi K2.5 for a limited time" (03.02.2026, juanpflores); Story „LongCat-2.0 is now free to try in cline" (02.09.2026, oliviayii); Kommentare von tripplyons (19.09.2025), theshrike79 (23.09.2025), minimaxir (25.09.2025), jasonvorhe (09.11.2025) — https://hn.algolia.com/api/v1/search
- Reddit (via Brave-Snippets; Direktabruf blockiert): r/CLine „Best free model?" (12.06.2025); r/CLine „New to Cline - Seeking Advice" (30.07.2025); r/CLine „Best free model for Cline?" (22.06.2026); r/opencode „Has anyone figured out the actual limits of Cline Pass yet?" (06.07.2026)
- DEV Community: „Cline Review 2026: Is the Best Free AI Coding Agent Actually Free?" — 02.06.2026

**Nicht gefunden (Negative Befunde):** Groq-Gratiszugang für Cline; Cerebras-Gratisaktion für Cline; Zhipu/GLM-Gratisaktion exklusiv für Cline; deutschsprachige X/LinkedIn-Belege.



