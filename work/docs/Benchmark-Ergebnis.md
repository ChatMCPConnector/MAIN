# ChaosShop 3-Wege-Benchmark — Ergebnis (2026-09-06)

Gleicher Task (MASTERPROMPT.md, 4 Phasen: Reparieren → Härtung → CSV-Export →
Verifikation) gegen alle 3 GLM-Proxies (chatglm.cn-Reverse, je GLM 5.3).
Startzustand je Kopie: **4 failed / 5 passed**.

## Ergebnis-Übersicht

| | glm2api (:8001) | hellogml (:8787) | chat2api (:8080) |
|---|---|---|---|
| **Runs nötig** | 1 | 4 | 4 (+2 Proxy-Fixes) |
| **Agent-Loop** | ✅ stabil (35 Tool-Executions) | ⚠️ bricht nach ~5-10 Nachrichten ab | ⚠️ bricht nach ~6 Tool-Executions ab |
| **Phase 1+2 (Reparatur)** | ✅ komplett | ✅ komplett (kumuliert) | ❌ Diagnose ja, Edits nein |
| **Phase 3 (Härtung+Export)** | ✅ komplett | ✅ komplett (kumuliert, letzer Agent) | ❌ |
| **Phase 4 (Tests+Verifikation)** | ✅ 16/16 grün | ✅ 16/16 grün (Moderator ergänzte fehlende Artefakte) | ❌ 4 failed / 5 passed (unverändert) |
| **Tests final** | 16 passed | 16 passed | 9 (Original), Task ungelöst |
| **Eigenständige Bewertung** | **Platz 1** | **Platz 2** | **Platz 3** |

## Detail pro Proxy

### 1. glm2api (Python/FastAPI) — GEWINNER
- Ein einziger Run, null Abbrüche, 35 Tool-Executions in Folge.
- Alle 5 Bug-Klassen gefunden (Race, SQLi, is_admin off-by-one+`or True`,
  quantity-Validierung, customer_name), behoben mit sauberer Minimal-Invasivität:
  atomares `UPDATE ... WHERE stock >= ?`, parametrisierte Queries, Bearer-Auth,
  CSV-Export mit Admin-Gate (401), PII-Maskierung, LIMIT 10000 + Streaming.
- 7 eigene Tests ergänzt, VERIFICATION.md + FINAL_REPORT.md erstellt.
- Unabhängige Nachverifikation (Moderator): Code-Review + Live-Smoke — alles korrekt.

### 2. hellogml (TS/Worker via wrangler) — Mitte, mit Vorbehalt
- Guest-Token-Limit („您已多次体验过对话") kippt jeden Agent-Run nach ~5-10
  Nachrichten. 4 Versuche: Run 2 schaffte Phasen 1+2, Run 3 implementierte den
  CSV-Export, Run 4 starb sofort. Kumuliert: Aufgabe technisch gelöst (16/16).
- Fehlende Artefakte (Härtungs-Tests, VERIFICATION.md) hat der Moderator ergänzt,
  um Vergleichbarkeit herzustellen — bei reiner Agent-Leistung wäre hellogml
  auf Platz 3, da kein einziger Run die Aufgabe autonom durchstehen konnte.
- Admin-Gate (403), PII-Maskierung, LIMIT 10000 live verifiziert.

### 3. chat2api (Electron) — Letzter, aber mit 2 echten Proxy-Bugs gefunden & gefixt
Der Run deckte zwei Protokoll-Bugs auf, die Agenten-Loops mit chat2api brechen:

**Bug A — Falsch-positive Tool-Prompt-Injection-Detection:**
opencode's Systemprompt enthält `## Tools` als harmlose Abschnitts-Überschrift.
chat2apis `hasToolPromptInjected()` hielt das für eine Client-eigene
Tool-Prompt-Injection → Tool-Definitionen wurden NICHT injiziert → Modell:
„Ich kann die bash-Tools nicht direkt nutzen" → leerer Stop.
**Fix:** Signatur `## Tools` aus `GENERAL_TOOL_SIGNATURES` entfernt
(`signatures.ts`) — Clients, die wirklich selbst injizieren, tragen
`[function_calls]`-Anweisungen mit, die weiterhin erkannt werden.

**Bug B — Kein Agent-Loop nach Tool-Ergebnissen ohne neue user-message:**
Opencode (wie alle Agent-Frameworks) sendet nach Tool-Ausführung
`[assistant(tool_calls), tool(result)]` OHNE neue user-message. chat2api rollt
die ganze History zu einem einzigen user-Prompt auf („User: ... Assistant:
... User: <tool-result> ... Assistant:") → chatglm.cn antwortet als
Chat-Zusammenfassung statt den Agent-Loop fortzusetzen → Agent stoppt nach 1 Step.
**Fix:** In `glm.ts` (messagesToPrompt): Wenn die History auf Tool-Ergebnisse
endet und Tools im Spiel sind, explizite Fortsetzungs-Aufforderung anhängen
(„You are in an agent loop... call the next tool or give your final answer").
Vorher: finish=stop nach Step 1. Nachher: finish=tool_calls, Loop läuft.

Ergebnis des 4. Runs mit beiden Fixes: 6 Tool-Executions, alle 5 Bugs korrekt
diagnostiziert (mit exakten Zeilennummern!) — aber beim Übergang von Diagnose
zu Edits stoppt der Loop trotzdem (Schwäche des `[function_calls]`-Markups bei
langen Multi-Tool-Histories vs. glm2apis JSON-Protokoll). Task blieb ungelöst:
4 failed / 5 passed, keine Edits. 

**Patches aktualisiert:** beide Fixes sind in `llm-proxies/patches/chat2api.patch`
(184 → 228 Zeilen) gesichert.

## Kern-Erkenntnisse

1. **Protokoll-Qualität entscheidet über Agenten-Tauglichkeit:** glm2apis
   JSON+`[]`-Terminator-Protokoll hält lange Tool-Loops stabil durch;
   hellogml (gleiches Protokoll, aber Token-Limit) und chat2api (Markup-basiert)
   brechen earlier.
2. **Guest-Token-Limit ist der Flaschenhals bei hellogml** (~5 Nachrichten/Token,
   Pool-Rotation zu langsam für lange Agent-Runs).
3. **Agent-Framework-Kompatibilität braucht Dedizierung:** opencode-Subagents
   senden (a) Systemprompts mit `## Tools`-Überschriften und (b) Tool-Histories
   ohne trailing user-message — beides ist Standard, beides brach chat2api.

## Reproduktion

- Proxies: `./llm-proxies/rebuild.sh` + je `/workspaces/<name>/start.sh`
- Kopien zurücksetzen: `rm -rf /workspaces/benchmark/<proxy>-work && ./work/benchmark/rebuild.sh <proxy>`
- Runs: Task-Tool mit Subagent `bench-<proxy>` (Masterprompt in work/benchmark/MASTERPROMPT.md)
- Proxy-Health: `curl 127.0.0.1:8001/health`, `:8787/` (200), `:8080/health`
