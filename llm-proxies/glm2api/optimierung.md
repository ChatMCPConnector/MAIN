# glm2api — Optimierungs-Arbeitsdatei (lebendiges Dokument)

Zweck: Zentrale Anlaufstelle für offene Probleme und geplante/grlaufende
Optimierungsarbeiten. **Neue Sessions/Agenten: zuerst hier lesen** — steht
unten ein Thema auf OFFEN, ist genau das Arbeitsfeld.

Status-Legende: DONE (fix + regressionstest + commit) · OFFEN (zu tun) ·
BEACHTEN (kein Fix nötig/sinnvoll, nur beobachten).

---

## Kontext des Härtetests (Stand 2026-09-11)

Vier Benchmark-Läufe (~500 Tool-Calls) haben 5 Proxy-Bug-Klassen aufgedeckt —
alle DONE (Commits 3cd794e, c33da91, fea9c22/79fca84, 7a2a2cd, efbc2e7).
92/92 Tests. Proxy-Ebene: 100% Tool-Call-Ausführung, 0 Leaks nach letztem Fix.
BEFUNDE.md im Repo-Root hat die Details inkl. Live-Leak-Strings.

---

## THEMA 1 — Kontext-Management für Lang-Agent-Sessions (OFFEN)

### Symptom (Härtetest-Re-Run + Final-Run)

Bei ~50+ Upstream-Runden (~150k+ Token Kontext) driftet das Modell:
wortgleiche Antwort-Wiederholungen (Loops), Missdeutung neuer Prompts
(Benchmark-Auftrag als „Extraktions-Anfrage" fehlinterpretiert), vorzeitige
Rückfragen/Stopps. 4-6 Resume-Schubser pro 2h-Lauf nötig. Der Proxy leitet
alles korrekt weiter (DB-Verifikation: Calls kamen sauber an) — reines
Modellverhalten bei Kontext-Überlast.

### Referenz: es ist lösbar

Der externe glm-free-api (gleicher chatglm.cn-Upstream, gleiche Modell-
Familie) liefert „gefühlt unendlichen Kontext": Stundenlange Sessions ohne
Drift. Beweis: diese Agent-Session hier (glm2api-Subagent auf gleicher
Infra) und Benchmark-Agente auf glmfree arbeiten stundenlang verlustfrei.
glm-free-api macht also irgendetwas Kontext-seitig, was glm2api nicht tut.

### Hypothesen (zu verifizieren, Reihenfolge = Wahrscheinlichkeit)

H1 **Kontext-Komprimierung/Summarization**: glm-free-api kürzt die
Historie serverseitig (ältere Turns zusammenfassen, nur最近 N Rounds
vollständig senden). chatglm.cn verhält sich bei aufgeblähter Historie
offenbar deutlich schlechter als bei komprimierter — auch wenn das
Modell nominell 1M Kontext hat.
   → Verifikation: glm-free-api-Quelle/Verhalten analysieren (endpunkt
     158.101.162.206:50063, Repo glm-free-api), vergleichender Test:
     gleiche 60-Runden-Historie einmal voll, einmal komprimiert.

H2 **Turn-Limit im Request**: chatglm.cn-Web-UI sendet pro Anfrage nur
eine begrenzte Zahl an Turns (Web-Chats werden serverseitig gefenstert).
glm-free-api imitiert evtl. nur das Web-Fenster.
   → Verifikation: Web-Capture (DevTools) einer langen gemini.google-…
     nein — chatglm.cn-Session: wie viele historical Rounds stehen im
     f.req? Ggf. Feld inner[2]-Session-Fortsetzung statt Vollhistorie.

H3 **Session-Fortsetzung statt Replay**: glm2api sendet JEDE Runde die
komplette Historie als frischen Kontext (convert_messages → flacher
Prompt). glm-free-api nutzt evtl. die conversation_id-Fortsetzung des
Upstreams (wie gemini-web2api multi_turn) — dann sieht das Modell pro
Runde nur die NEUE Nachricht, nie eine aufgeblähte Historie.
   → Verifikation: im glm2api-Code prüfen, ob _open_chat_stream je eine
     Upstream-Conversation WIEDERVERWENDET (conversation_id an
     Folge-Runden mitsenden) oder immer neu öffnet. Struktur dafür ist
     vorhanden (conversation_id exists im Accumulator), Nutzung prüfen.

### Umsetzungs-Plan (nach Verifikation)

P0 glm-free-api-Verhalten analysieren (H1/H2/H3 klären) —半 Tag
P1 Umbau auf Session-Fortsetzung (H3) ODER Historien-Komprimierung (H1)
   im translator/glm_client, konfigurierbar (AppConfig-Schalter
   `glm_history_strategy = full|window|summarize`).
P2 Regressionstests: Lang-Agent-Benchmark-Run (benchmark-hard.md, 60+
   Runden) muss ohne Resume-Schubser durchlaufen.
P3 infrastructure.md-Changelog + Commit.

### Akzeptanzkriterium

60+ Runden Benchmark-Langlauf mit 0 Drift-Vorfällen, 0 Resume-Anforderungen.

---

## THEMA 2 — Encoding-Verderb: Umlaute → Steuerzeichen (OFFEN)

### Symptom

Selten (2 Vorfälle auf ~500 Calls) schreibt das Modell per write-Tool
Dateien, in denen statt `ü` die Steuerzeichen U+0014/U+0005 landen
(io_utils.py: `zurück` → kaputt). Die JSON-Tool-Argumente sind syntaktisch
valide — nur der INHALT ist kaputt. Proxy reicht sie unverändert durch.

### Analyse

- Fehler entsteht modellseitig beim Streaming (Non-ASCII-Schwäche).
- Der Proxy PARS'T die Argumente bereits (Recovery-Pfade, Echo-Signaturen)
  — dort könnten kaputte Bytes bemerkt und normalisiert werden.

### Fix-Design ( sanitieren statt trusten )

F1 **Sanitizer für Tool-Call-Argumente**: nach dem Parsen jedes Call
  (builder in tool_parser.py) Arguments-String prüfen: C0-Steuerzeichen
  (\u0000-\u001F) außer \n \t \r — Vorkommen ersetzen durch typische
  Mapping-Tabelle (U+0014/U+0005-Cluster → "ü"/"u"-Heuristik ist zu
  fragil; besser: durch "?" ersetzen und loggen). Sicherer, aber Syntax
  bleibt intakt; kaputter Content wird sichtbar statt still.
F2 **Ergänzend text-side**: gleiche Prüfung im sichtbaren Content — dort
  sind C0-Steuerzeichen nie legitim (JSON-escaped).
F3 **Log-Alarm**: jedes Vorkommen mit Kontext-Snippet loggen
  (logging_utils), damit Häufigkeit getrackt wird (BEACHTEN → ggf. doch
  Modell-Thema mit Workaround).
F4 **Regressionstests**: Argument-String mit \u0014/\u0005 → sanitized;
  normale Umlaute (echtes UTF-8 "ü") bleiben UNANGETASTET (wichtig:
  nur C0-Steuerzeichen angreifen, nie valides UTF-8 normalisieren!).

### Umsetzungs-Plan

P1 sanitize_tool_calls() in translator.py bzw. Call-Builder im Parser
   erweitern (F1+F2+F3), Tests (F4).
P2 Benchmark-Re-Run: Encoding-Inzidenz im Log zählen.
P3 Changelog + Commit.

### Akzeptanzkriterium

Kein C0-Steuerzeichen (außer \n\t\r) mehr in Tool-Argumenten oder sichtbarem
Content, echtes UTF-8 unberührt, jede Bereinigung geloggt.

---

## Erledigt-Historie (Kurzreferenz)

- Echo/Duplikat-Loops (native Parts, 36/Turn) — DONE 3cd794e
- Snipsel+Finish-Protokoll-Leak + `[]`-Whitespace-Leak — DONE c33da91
- Invalides JSON (unbalancierte Klammern, 6,6KB) — DONE fea9c22/79fca84
- Doppelausgabe Call+Text (Midstream) — DONE 7a2a2cd
- Nacktes JSON-Array als Protokoll (Leak-Variante D) — DONE efbc2e7

Siehe auch: BEFUNDE.md (Repo-Root, Härtetest-Kampagne komplett),
infrastructure.md Changelog (10)–(14).