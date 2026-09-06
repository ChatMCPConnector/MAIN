# TinyTask 3-Wege-Benchmark — Ergebnis (2026-09-06)

Zweiter SWE-Bench-Prompt (andere Domäne: Scheduler statt Shop, andere Bug-Klassen:
Datums-Off-by-one, stille Fehler-Fallbacks, falscher Bezugszeitpunkt, SQLi).
Template: `work/benchmark/tinytask-template/` (4 failed / 3 passed Startzustand,
verifiziert). Erweiterungen: `tasks_due_between` + `reschedule_all`.

## Ergebnis

| | glm2api | hellogml | chat2api |
|---|---|---|---|
| Runs nötig | **1** | 6 | 5 |
| Phase 1+2 (4 Bugs + SQLi) | ✅ autonom komplett | ✅ kumuliert (Run 1 analysierte alles, Run 4/5 setzten um) | ✅ Run 4 (nur mit exakt vorformatierten Edits + No-Ask-Prompt) |
| Phase 3 (Erweiterungen+Tests) | ✅ autonom komplett | ✅ Agent (2 Test-Bugs durch Moderator korrigiert) | ❌ Moderator ergänzt (Agent brach ab) |
| Phase 4 (Verifikation) | ✅ komplett | ✅ komplett | ✅ (Moderator) |
| **Tests final** | **17/17** | **16/16** | **16/16** |
| Autonomie-Grad | Vollautonom | Semi (kleine Schritte nötig) | Nur präzise Exekution (Copy-Paste) |
| **Platz** | **1** | **2** | **3** |

## Muster über beide Benchmarks (ChaosShop + TinyTask)

1. **glm2api:** 2/2 Benchmarks vollautonom in jeweils 1 Run (52 Tool-Executions
   insgesamt, 0 Abbrüche). JSON+`[]`-Tool-Protokoll ist agent-tauglich.
2. **hellogml:** Qualität der Einzelbeiträge hoch (Diagnosen präzise), aber
   Guest-Token-Limit (~5 Nachrichten/Token) bricht jeden Lang-Run. Kumulation
   über Resume-Prompts funktioniert.
3. **chat2api:** Braucht exakt vorformatierte Edits + strikte No-Ask/No-Intro-
   Prompts, dann liefert es präzise. Offene Erkundung/Initiative bricht nach
   ~1-6 Tool-Executions ab (Markup-Fragilität). Die 2 gestrigen Proxy-Fixes
   (Signatur + Agent-Loop) waren nötig, damit ÜBERHAUPT Tool-Executions stattfinden.

## Verifikation

Alle 16/17-Test-Stände unabhängig live nachverifizt (Grenzen inklusive,
gemischte Typen, reschedule→Zukunft, Injection-Abwesenheit).
Protokolle je Run in den VERIFICATION.md-Dateien der Arbeitskopien.
