# Reverse-Engineering: chatglm.cn Reasoning-Stufen (2026-09-07)

## Ergebnis

Die Reasoning-Stufen der chatglm.cn-Web-UI sind **echte `chat_mode`-Werte** im
`meta_data` des Chat-Requests (`/chatglm/backend-api/assistant/stream`):

| UI (Browser) | `chat_mode` | Bedeutung |
|---|---|---|
| 快速 | `""` | kein Denken |
| 深度 (Standard-Denken) | `"thinking"` | Reasoning-Stream + Antwort |
| 极致 (全力推理，耗时更长) | `"deep_thinking"` | volles Denken |
| (Forschung) | `"deep_research"` | Research-Modus (UI: Agent/研究报告) |

**Der alte Proxy-Wert `"zero"` wurde von der Web-UI nie gesendet** (historisch
geraten; führte zu undefiniertem Verhalten).

Zusatzfund: Die UI sendet `"selected_model": "glm-5.3"` in meta_data.

## Methodik (CDP, keine externen Dependencies)

1. Playwright-Chromium (Repo-Runtime) mit CDP :9222 auf chatglm.cn
2. `reverse-engeneer/capture.py`: minimaler CDP-WebSocket-Client (raw socket,
   Python-stdlib) — zeichnet `Network.requestWillBeSent`-POST-Bodies auf (JSONL)
3. `reverse-engeneer/cdp.py`: JS-Injection (Runtime.evaluate) für UI-Automatisierung:
   - `.think-mode-trigger` (Modell/Stufen-Button) klicken
   - `.think-mode-item.has-submenu` hovern ( öffnet Stufen-Submenü)
   - Stufen-Container `.think-mode-item` je Stufe klicken
   - `textarea` befüllen (React-Value-Setter) + Enter-keydown senden
4. Je Stufe eine markierte Message → Request-Bodies verglichen

## Umsetzung im Proxy (llm-proxies/glm2api)

`translator.py::resolve_chat_mode` übersetzt jetzt 1:1:

```
reasoning_effort low|minimal|medium  → chat_mode "thinking"
reasoning_effort high|max|<unbekannt> → chat_mode "deep_thinking"
Modell-Suffix -think (ohne Stufe)     → "deep_thinking"
kein think, kein effort               → "" (schnell)
```

opencode-Varianten (low/medium/high/max) greifen damit **real**.

## Verifikation

- Unit: 8 Mapping-Fälle (translator) — alle OK
- Upstream-Log: Requests tragen "thinking"/"deep_thinking" je Stufe
- Live: alle 4 Stufen antworteten korrekt (Zug-Aufgabe 14:45 ✓)

## Files

- `capture.py` — CDP-Capture (JSONL: reasoning-capture.jsonl)
- `cdp.py` — CDP-Steuerung (navigate/eval/screenshot)
