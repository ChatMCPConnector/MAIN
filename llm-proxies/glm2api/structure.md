# glm2api - Aufbau und Funktionsweise

**glm2api** ist ein lokaler Proxy, der die ChatGLM-Web-API in OpenAI-kompatible APIs umwandelt.

---

## 1. Kernkomponenten

### **Konfiguration** (`config.py`)
- Lädt `.env` Datei
- Verwaltet mehrere `refresh_token`s (Multi-Account-Unterstützung)
- Unterstützt Gast-Modus (ohne Login)
- Definiert Ports, URLs, Concurrent-Limits

### **HTTP-Server** (`server.py`)
Implementiert OpenAI-kompatible Endpunkte:
- `POST /v1/chat/completions` - Chat (Streaming + Non-Streaming)
- `POST /v1/messages` - Anthropic Messages API
- `POST /v1/responses` - OpenAI Responses API
- `POST /v1/images/generations` - Bildgenerierung
- `GET /v1/models` - Modellliste
- `GET /health` - Health-Check
- CORS- und Auth-Handling

### **GLM-Client** (`glm_client.py`)
- Kommunikation mit chatglm.cn
- **Request-Queue mit Concurrency-Limit** (vermeidet GLM-Busy-Errors)
- Token-Refresh und Account-Failover
- Datei-Upload (Bilder/Files)
- Bildgenerierung

### **Auth-Manager** (`glm_auth.py`)
- Verwaltet Access-Tokens (1h Gültigkeit)
- Automatisches Refresh von `refresh_token`
- Gast-Token-Generierung
- Signatur-Generierung für GLM-Requests
- Random `X-Forwarded-For` Headers

---

## 2. Adapter-Module

### **Anthropic-Adapter** (`anthropic_adapter.py`)
- Anthropic → OpenAI Chat/Completions
- Streaming-Umsetzung (SSE → Anthropic Events)

### **Responses-Adapter** (`responses_adapter.py`)
- OpenAI Responses → OpenAI Chat/Completions
- Streaming mit Heartbeat (alle 5s)

---

## 3. Tool-System

### **Tool-Parser** (`tool_parser.py`)
- **Streaming-Parser** für Tool-Calls aus Modelltext
- Unterstützt **JSON-Format**: `{"tool_calls":[{"name":"...","arguments":{...}}]}[]`
- Unterstützt **DSML-XML** (Legacy)
- Extrahiert sichtbaren Text und Tool-Calls getrennt

### **Tool-Protokoll** (`tool_protocol.py`)
- Serialisiert Tool-Calls in JSON-Format
- Generiert Tool-Instructions für das Modell
- Filtert blockierte Tools (`open_url`, `web.search`, etc.)

### **Translator** (`translator.py`)
- OpenAI Messages → GLM Transcript
- Tool-Definitionen in Prompt injizieren
- **Reasoning-Mapping**: `low/medium/high/max` → GLM `chat_mode`
- Tool-Sanitization und Argument-Repair
- **GLMEventAccumulator**: Akkumuliert Upstream-SSE-Events

---

## 4. Modell-Varianten (`model_variants.py`)
- Erweitert Basis-Modelle um Suffixe (`-think`, `-search`)
- `model_requests_thinking()` / `model_requests_search()` Helper

---

## 5. Request-Flow

### **Chat-Request:**
1. HTTP-Server empfängt OpenAI-Request
2. Validierung + Auth-Check
3. GLM-Client holt Queue-Slot
4. Translator konvertiert Messages → GLM-Format
5. Upload referenzierter Files/Bilder
6. GLM-Request mit Signatur an chatglm.cn
7. Streaming-Response parsing
8. GLMEventAccumulator sammelt Events
9. Tool-Parser extrahiert Tool-Calls
10. SSE an Client ausgeben

### **Tool-Call-Flow:**
1. Client definiert Tools im Request
2. Translator generiert Tool-Instructions + -Schemas
3. Modell generiert Tool-Call (JSON oder DSML)
4. Parser extrahiert Tool-Calls aus Text
5. Server sendet `tool_calls` in OpenAI-Format
6. Client sendet Tool-Result in nächster Runde

---

## 6. Streaming-Architektur

```
GLM SSE (Upstream)
    ↓
GLMEventAccumulator (Status, Parts, Reasoning)
    ↓
Tool-Parser (Text → Visible + Tool-Calls)
    ↓
OpenAI SSE (Client)
```

- **Reasoning-Content** → separater `reasoning_content` Delta
- **Tool-Calls** → JSON-Blöcke `{"tool_calls":[...]}` mit `[]`-Terminator

---

## 7. Failover- und Retry-Logik

- **GLM-Busy-Retry**: Automatischer Retry bei "请等待其他对话生成完毕"
- **Account-Failover**: Wechselt bei Fehlern zum nächsten Token
- **Guest-Retry**: Gast-Tokens werden bei Fehlern neu generiert

---

## 8. Reasoning-Modi

| `reasoning_effort` | GLM `chat_mode` |
|-------------------|-----------------|
| `low` / `minimal` | `""` (schnell, kein Denken) |
| `medium` / `high` | `"thinking"` (Standard-Denken) |
| `max` | `"deep_thinking"` (volles Reasoning) |

---

## 9. Wichtige Dateien

```
glm2api/
├── src/glm2api/
│   ├── config.py          # Konfiguration
│   ├── server.py          # HTTP-Server
│   ├── app.py             # App-Startup
│   ├── __main__.py        # Entry-Point
│   ├── model_variants.py  # Modell-Suffixe
│   ├── services/
│   │   ├── glm_client.py      # GLM-Kommunikation
│   │   ├── glm_auth.py        # Token-Management
│   │   ├── translator.py      # Message-Konvertierung
│   │   ├── anthropic_adapter.py
│   │   └── responses_adapter.py
│   └── utils/
│       ├── tool_parser.py     # Tool-Parsing
│       └── tool_protocol.py   # Tool-Serialisierung
```

---

Die Architektur ist **pipeline-basiert**: Jede Komponente hat eine klare Verantwortung (Config → Auth → Queue → Translate → Upstream → Accumulate → Parse → Stream), was Debugging und Erweiterung erleichtert.

---

## 10. Portables Bundle (Export in andere Umgebungen)

- Bau: `llm-proxies/scripts/build-bundle.sh` (im MAIN-Repo) → `llm-proxies/dist/glm2api-bundle.zip`
- Inhalt: dieses Verzeichnis komplett (ohne .venv/log/__pycache__) + `glm2api.env`
  als fertige Config + portable `install.sh`/`start.sh` (relative Pfade, `GLM_PORT`/`GLM_HOST` überschreibbar)
- Fremd-Start: entpacken → `bash scripts/install.sh` (uv + Python 3.14 + venv + .env)
  → `bash scripts/start.sh` (Default Port 8001, Guest-Mode)
- Keine externen Python-Deps (nur Stdlib) — `uv sync` reicht.
- Der Source in diesem Verzeichnis ist kanonisch; ein separates Patch-Artefakt
  (früher `llm-proxies/patches/glm2api.patch`) existiert nicht mehr — alle
  Projektkorrekturen (JSON-Tool-Protokoll, Part-Merge-Fix) sind direkt
  eingearbeitet.
