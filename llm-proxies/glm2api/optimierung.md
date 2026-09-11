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

## THEMA 1 — Kontext-Management für Lang-Agent-Sessions (ERLEDIGT 2026-09-11, Beobachtung läuft)

### Umsetzung (P1) — Historien-Kompression + 10040-Auto-Retry + Leer-Turn-Auto-Retry

- **H1-Kompression**: `compress_history_messages()` in translator.py —
  Historie VOR der Konvertierung auf Budget begrenzen (von NEU nach ALT
  sammeln, assistant+tool-Paare nie trennen, ältere Runden zu einem
  summarischen Eintrag verdichten). Konfigurierbar: `GLM_HISTORY_MAX_CHARS`
  (Default 120000, 0 = aus).
- **10040-Auto-Retry**: chatglm.cn lehnt bei "model response context
  exceeded" (code 10040) ab — jetzt transient; Retry halbiert das Budget
  (`_glm_history_budget` im Payload) bis der Upstream mitmacht (min 20k).
  Beide Pfade (stream + non-stream).
- **Leer-Turn-Auto-Retry** (Autonomie-Fix): `is_empty_response()` im
  Accumulator erkennt komplett leere Upstream-Runden (text=0, reasoning=0,
  calls=0 — zuvor blieb der Agent genau dort STEHEN, z.B. Stresstest
  10:21). glm_client retryt automatisch mit frischer Conversation, BEVOR
  die leere Antwort den Client erreicht. Config:
  `GLM_EMPTY_RESPONSE_MAX_RETRIES` (Default 2). Kondition: nur wenn noch
  kein Content gestreamt wurde (sonst wäre der Retry unsauber).

### Verifikation (P2)

Autonomie-Lauf (agent-glm2api-hard6, Session ses_f6fc7bff6ffevWATNhrlzCPTYO):
ALLE Phasen 0-10 durchgelaufen, ~86 Upstream-Runden, 171 Tool-Parts,
0 Ausführungsfehler, Kompression live (268→52 Messages), keine
Resume-Schubser während der Arbeit, kein Drift, keine Loops.
Vorher (ohne Fix): alle 2h-Läufe brauchten 4-6 Schubser und standen
an Leer-Turns komplett still.

Status: **ERLEDIGT — BEACHTEN** (in künftigen Langläufen auf
"Empty GLM response — auto-retrying"-Logzeilen und 10040-Halbierungen
achten; Budget ggf. tunen).

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