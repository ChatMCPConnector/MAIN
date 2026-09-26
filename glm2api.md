# glm2api — Offene Punkte

Dokumentation der offenen Punkte nach der Behebung der Audit-Befunde (Stand: 2026-09-26).

**Status: beide Punkte geschlossen.** Details und Verifikation unten.

---

## 1. Upstream Rate-Limit Retry-Rückkopplung (Code 10061 / HTTP 429) — BEHOBEN (F-6)

### Problem & Diagnose (historisch)
Im Upstream-Client (`llm-proxies/glm2api/src/glm2api/services/glm_client.py`) war der Fehlercode `10061` („请求过于频繁，请稍后再试“ — Rate Limit) in `TRANSIENT_UPSTREAM_ERROR_CODES` enthalten:
- Bei einem HTTP 429 / Code 10061 griffen zwei getrennte Retry-Mechanismen: der transiente Stream-Fehler-Pfad und `_should_retry_busy_error`.
- Das Limit `glm_busy_max_retries` stand standardmäßig auf 30 Versuchen mit einem maximalen Backoff von nur ~8 Sekunden (`glm_busy_retry_interval = 2.0s`).
- **Folge:** Sobald das Upstream-Konto in ein Rate-Limit läuft, feuert der Proxy bis zu 30 Anfragen im Abstand von wenigen Sekunden hinterher. Dadurch wird die serverseitige Kontosperre/Drosselung weiter vertieft, anstatt ihr Zeit zum Abklingen zu geben.

### Kern-Erkenntnis des Fixes
Code `10061` trägt **zwei** Bedeutungen, die gegensätzliche Antworten brauchen:

| Upstream-Meldung | Bedeutung | Richtige Reaktion |
|---|---|---|
| `请等待其他对话生成完毕` | Nebenlauf-Busy (andere Web-Chat-Konversation blockiert den Slot) | viele kurze Versuche (2s-Basis) — ist in Sekunden weg |
| `请求过于频繁` | Konto-Drosselung | wenige Versuche mit langem Backoff — klingt in Minuten ab |

Vorher liefen beide über dasselbe Profil. Der Text entscheidet, nicht der Code.

### Umgesetzte Lösung
1. `10061` aus `TRANSIENT_UPSTREAM_ERROR_CODES` entfernt. Ein 10061 ist nur dann noch transient, wenn es der Nebenlauf-Busy ist — eine Drosselung ist explizit **nicht** transient und löst deshalb keinen Stream-Retry (2×, 1s) mehr aus.
2. Neuer, eigenständiger Rate-Limit-Pfad in `send_request`:
   - eigenes Budget `GLM_RATE_LIMIT_MAX_RETRIES` (Default 2, max. 5) statt 30,
   - eigenes Backoff-Profil `GLM_RATE_LIMIT_RETRY_INTERVAL_SECONDS` (Default 30s): 30s → 60s → 120s, gedeckelt beim 8-fachen; nur Jitter **nach oben** (gleichzeitiges Aufwachen mehrerer Clients hält die Sperre am Laufen),
   - nach erschöpftem Budget (oder erreichter Request-Deadline) geht ein **sauberer HTTP 429** an den Client statt weiterer Versuche.
3. `10061` ohne erkennbare Meldung wird als Rate-Limit behandelt (wahrscheinlicher und der schädlichere Fehlerfall).
4. Eine mitten im Stream auftretende Drosselung wird als `429` statt als `502` gemeldet, damit der Client „warte, zu schnell“ von „Upstream kaputt“ unterscheiden kann.
5. `_should_retry_busy_error` (Equiv: 429 **oder** Code 10061) ist entfallen, ersetzt durch `_classify_upstream_throttle()`.

**Unverändert:** Der Nebenlauf-Busy behält sein Verhalten (30 Versuche, 2s-Basis, exponentielles Backoff mit Jitter, `transient=True`).

### Neue Konfigurations-Keys
| Key | Default | Max | Wirkung |
|---|---|---|---|
| `GLM_RATE_LIMIT_MAX_RETRIES` | 2 | 5 | Retry-Budget ausschließlich für `请求过于频繁` |
| `GLM_RATE_LIMIT_RETRY_INTERVAL_SECONDS` | 30 | 300 | Basis des Rate-Limit-Backoffs |

Gesetzt in `llm-proxies/glm2api.env`, `llm-proxies/glm2api/.env.example` und der laufenden `.env`.

### Verifikation
- `tests/test_rate_limit_split.py` (27 Tests, neu): Klassifikation beider 10061-Varianten über alle Payload-Formen (`status`/`error_code`, `message`/`err_msg`, `error`/`last_error`-Verschachtelung, englische Variante), Nicht-transient für Drosselung, Backoff-Progression inkl. Deckel und „kein Jitter nach unten“, HTTP-Pfad (3 Requests statt 31, Wartezeiten 30s/60s, `status_code == 429`, `transient is False`), Busy-Regressionstest, Verhalten bei 0 Retry-Budget und bei erreichter Request-Deadline.
- Gesamtsuite: **520 Tests grün** (493 vorher + 27 neu).
- Live: `/health` OK, 82 Modelle, alle drei API-Formate + Tool-Call-Roundtrip grün (Smoke-Test 8/8).
- `benchmarks/verify_auditmesh.py` wurde **nicht** neu gefahren: Es ist ein reiner Post-Run-Oracle über die Dateien eines Benchmark-Laufs (Parameter = Benchmark-Project-Root) und prüft keinerlei Proxy-Retry-Verhalten. Fixtures dafür liegen bewusst nicht im Repo.

---

## 2. Live-End-to-End-Gegenprüfung — ERLEDIGT

### Ausgangslage
- Alle deterministischen Unit- und Integrationstests sowie der `verify_auditmesh.py`-Benchmark waren bereits verifiziert.
- Der Fix **F-5w3** (gesperrte/nicht deklarierte Werkzeugaufrufe enden mit `finish_reason: "stop"` statt `"error"`, um die 5-Minuten-Retry-Schleife von opencode zu verhindern) war auf beiden Pfaden (Stream und Non-Stream) abgesichert.
- Offen war nur noch die Live-Gegenprüfung, weil das Upstream-Konto im HTTP 429 / Code 10061 stand.

### Durchgeführte Live-Prüfung (Upstream-Ratelimit war abgeklungen)
```bash
cd /workspaces/MAIN
SMOKE_MODEL=glm-5.3 ./llm-proxies/scripts/smoke-test.sh
```
Ergebnis: **8/8 OK** — `health`, `models (82 geliefert)`, `openai chat`, `openai chat (stream)`, `anthropic messages`, `responses`, `tool-call emittiert`, `tool-result verarbeitet`.

### Gesperrtes Tool live
Zwei Live-Anfragen mit dem gesperrten Tool `open_url` (steht in `BLOCKED_TOOL_NAMES`) plus erlaubtem `read`:
- `glm-5.3`: `finish_reason: "stop"`, keine Tool-Calls, Modell verweigert den Aufruf im Klartext.
- `glm-5.3-think` mit ausdrücklicher Aufforderung, `open_url` trotzdem als JSON aufzurufen: `finish_reason: "stop"`, keine Tool-Calls.

**Einschränkung, die nicht wegdiskutiert wird:** In beiden Läufen *versuchte* das Modell den gesperrten Aufruf nicht, sondern verweigerte ihn im Text — die Proxy-Meldung im Log lautet entsprechend `blocked=[] blocked_follow_ups=0`. Der Pfad, der die `[blocked_tool_notice]` tatsächlich erzeugt (Modell ruft das gesperrte Tool doch auf → Negativ-Follow-up-Runde), wurde live also **nicht** ausgelöst. Er ist deterministisch abgesichert in `tests/test_stream_retry.py` (u. a. `test_hallucinated_success_after_exhausted_follow_ups_gets_honesty_notice`, das prüft, dass die Notice **vor** der erfundenen Antwort steht). Live verifiziert ist: gesperrtes Tool ⇒ `finish_reason: "stop"`, kein Error, kein Retry-Loop.

**Konsequenz für die Testanweisung:** Die Anweisung ist erledigt und wird nicht wiederholt. Ein erneuter Live-Lauf ist nur sinnvoll, wenn erneut eine Drosselung auftritt — dann ist die Beobachtung im Proxy-Log die relevante: `GLM upstream rate limit hit (code 10061), backing off instead of hammering` mit **3** Requests statt 31, gefolgt von `returning 429 to client`.

---

## 3. Nachgelagert beobachtet (kein Handlungsbedarf)

- `glm_auth.ACCOUNT_RETRY_UPSTREAM_ERROR_CODES` enthält 10061 weiterhin — bewusst: Bei mehreren Konten ist Account-Rotation auf eine Drosselung richtig (anderes Konto, anderes Kontingent). Bei einem einzigen Konto greift `account_count == 1` und der Fehler wird direkt durchgereicht. `invalidate_account` verwirft dabei nur den gecachten Token (ein zusätzlicher Refresh-Aufruf, kein Schaden).
- **Betriebshinweis:** Der Proxy auf Port 8001 ist die eigene Modellversorgung dieser Session. Ein Neustart (`pkill -f "glm2api/.venv/bin/python main.py"`, Watchdog startet ihn neu) unterbricht die laufende Session — der Watchdog braucht wenige Sekunden, bis `/health` wieder antwortet.
