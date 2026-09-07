# glm2api-Bundle — portabler GLM-Proxy

Selbstentpackendes, vollständiges Paket des glm2api-Proxys (chatglm.cn-Reverse,
OpenAI-kompatibel, Guest-Token-Pool). Enthält Code, Konfiguration, Start-Skripte
und Doku — startklar in jeder Linux/WSL-Umgebung mit bash + curl.

## Inhalt

```
glm2api-bundle/
├── app/                    # Komplette Proxy-Anwendung (aus MAIN llm-proxies/glm2api)
│   ├── src/glm2api/        #   Python-Code (nur Stdlib, keine externen Deps)
│   ├── tests/              #   Unit-Tests (pytest)
│   ├── main.py             #   Entry-Point
│   ├── pyproject.toml      #   Python >=3.14, zero dependencies
│   ├── uv.lock             #   Lockfile (nur das Projekt selbst)
│   ├── glm2api.env          #   Fertige Config: Port 8001, Guest-Mode (wird zu .env kopiert)
│   ├── .env.example        #   Original-Beispielconfig
│   ├── README.md           #   Original-README (chinesisch, API-Referenz)
│   └── structure.md        #   Architektur-Übersicht (deutsch)
├── scripts/
│   ├── install.sh          #   uv installieren + venv + .env (idempotent)
│   └── start.sh             #   Proxy starten (portable Pfade, Health-Check)
├── patches/
│   └── glm2api.patch        #   Historischer Patch (bereits eingearbeitet, nur Referenz)
└── docs/
    └── chatglm-reasoning-modes.md   # Reverse-Engineering: chat_mode-Mapping
```

## Voraussetzungen

- Linux/WSL (oder macOS mit angepassten Pfaden), bash, curl
- Internetzugriff auf `chatglm.cn` (Upstream) und `astral.sh` (uv-Install, nur einmal)
- Python muss NICHT vorinstalliert sein — `uv` lädt Python 3.14 selbst

## Start in 2 Schritten

```bash
bash scripts/install.sh   # uv + venv + .env (einmalig, ~1-2 Min)
bash scripts/start.sh     # startet auf http://127.0.0.1:8001
```

## Nutzung

```bash
curl http://127.0.0.1:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"glm-5.3","messages":[{"role":"user","content":"hi"}]}'
```

OpenAI-SDK: `base_url="http://127.0.0.1:8001/v1"`, `api_key="local"` (beliebig).

## Wichtige Config (app/.env, aus glm2api.env)

| Var | Wert im Bundle | Bedeutung |
|---|---|---|
| `PORT` | `8001` | Listen-Port |
| `GLM_USE_GUEST_REFRESH_TOKEN` | `true` | Guest-Mode, kein Login nötig |
| `GLM_MAX_CONCURRENCY` | `100` | Guest-Token-Pool-Größe |
| `LOG_LEVEL` / `DEBUG_DUMP_ALL` | `DEBUG` / `true` | Debug-Logs nach `app/log/` |
| `GLM_REFRESH_TOKEN` | leer | Eigenen Account-Token hier eintragen, falls kein Guest-Mode |

## Tests

```bash
cd app && uv run pytest
```

## Hinweise

- `patches/glm2api.patch` ist bereits im Code eingearbeitet (JSON-Tool-Protokoll,
  Part-Merge-Fix, mc_tool_result-Behandlung) — nur für Referenz/Diff-Zwecke dabei.
- Guest-Mode: Upstream-Limit ~5 Nachrichten pro Guest-Token; der Pool (100 Slots)
  rotiert automatisch, bei Erschöpfung werden neue Tokens geholt.
- Details Architektur: `app/structure.md` · Reasoning-Stufen: `docs/chatglm-reasoning-modes.md`

## Herkunft

Gepflegt im MAIN-Repo (`llm-proxies/`), gebaut mit `llm-proxies/scripts/build-bundle.sh`.
