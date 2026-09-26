# glm2api — Offene Punkte

Dokumentation der verbleibenden offenen Punkte nach der Behebung der Audit-Befunde (Stand: 2026-09-26).

---

## 1. Upstream Rate-Limit Retry-Rückkopplung (Code 10061 / HTTP 429)

### Problem & Diagnose
Im Upstream-Client (`llm-proxies/glm2api/src/glm2api/services/glm_client.py`) ist der Fehlercode `10061` („请求过于频繁，请稍后再试“ — Rate Limit) in `TRANSIENT_UPSTREAM_ERROR_CODES` enthalten:
- Bei einem HTTP 429 / Code 10061 greifen zwei getrennte Retry-Mechanismen: der transiente Stream-Fehler-Pfad und `_should_retry_busy_error`.
- Das Limit `glm_busy_max_retries` steht standardmäßig auf 30 Versuchen mit einem maximalen Backoff von nur ~8 Sekunden (`glm_busy_retry_interval = 2.0s`).
- **Folge:** Sobald das Upstream-Konto in ein Rate-Limit läuft, feuert der Proxy bis zu 30 Anfragen im Abstand von wenigen Sekunden hinterher. Dadurch wird die serverseitige Kontosperre/Drosselung weiter vertieft, anstatt ihr Zeit zum Abklingen zu geben.

### Empfohlene Lösung
1. `10061` aus `TRANSIENT_UPSTREAM_ERROR_CODES` herausnehmen oder als gesonderten Rate-Limit-Status behandeln.
2. Für echte 429/10061-Limits einen längeren, progressiven Backoff einsetzen (z. B. 30s → 60s → 120s) oder nach wenigen Versuchen mit sauberem 429-Status an den Client abbrechen, anstatt 30 schnelle Retries abzufeuern.

---

## 2. Live-End-to-End-Gegenprüfung (nach Abklingen des Upstream-Ratelimits)

### Problem & Kontext
- Alle deterministischen Unit- und Integrationstests (493 Tests grün) sowie der `verify_auditmesh.py`-Benchmark (8/8 Tests, Mutationstest bestanden) wurden verifiziert.
- Der Fix **F-5w3** (gesperrte/nicht deklarierte Werkzeugaufrufe wie `open` enden mit `finish_reason: "stop"` statt `"error"`, um die 5-Minuten-Retry-Schleife von opencode zu verhindern) ist deterministisch auf beiden Pfaden (Stream und Non-Stream) abgesichert.
- **Offener Punkt:** Da das Upstream-Konto durch die vorangegangenen intensiven Testläufe temporär im HTTP 429 / Code 10061 („请求过于频繁“) stand, steht die abschließende Live-Gegenprüfung mit einem echten Request gegen `chatglm.cn` noch aus.

### Testanweisung für den neuen Codespace
Sobald das Upstream-Ratelimit abgeklungen ist, folgenden Test ausführen:

```bash
cd /workspaces/MAIN
SMOKE_MODEL=glm-5.3 ./llm-proxies/scripts/smoke-test.sh
```

Zusätzlich prüfen, dass ein Call auf ein gesperrtes Tool (z. B. `open`) live sauber mit `finish_reason: "stop"` und der `[blocked_tool_notice]` quittiert wird, ohne dass opencode in einen Retry-Loop fällt.
