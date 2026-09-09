# glm2api — GLM-Web → OpenAI-kompatibler Proxy

**glm2api** wandelt die ChatGLM-Web-API (chatglm.cn) in OpenAI-kompatible
Endpunkte um. Lokaler Betrieb, Guest-Token-Pool (Auto-Refetch, Rotation).

## Endpunkte

| Endpunkt | Funktion |
|---|---|
| `POST /v1/chat/completions` | Chat (Streaming + Non-Streaming) |
| `POST /v1/messages` | Anthropic Messages API |
| `POST /v1/responses` | OpenAI Responses API |
| `POST /v1/images/generations` | Bildgenerierung |
| `GET /v1/models` | Modellliste |
| `GET /health` | Health-Check |

OpenAI-SDK: `base_url="http://127.0.0.1:<PORT>/v1"`, `api_key` beliebig
(außer `SERVER_API_KEYS` ist gesetzt).

## GLM Refresh Token beschaffen

Ohne eigenen Account: Gast-Modus nutzen (siehe unten). Mit eigenem Account:

1. `https://chatglm.cn` öffnen und einloggen
2. `F12` → Entwickler-Tools öffnen
3. Reiter `Application` öffnen
4. `Local Storage` (bzw. relevante Speicher-Einträge) ansehen
5. Eintrag `chatglm_refresh_token` suchen und den Wert kopieren

Danach in `.env` (oder `token.txt`, eine Zeile pro Account) eintragen:

```env
GLM_REFRESH_TOKEN=<dein_refresh_token>
```

Multi-Account: `token.txt` bevorzugt (eine Zeile pro Account, automatischer
Failover); ohne `token.txt` und `GLM_REFRESH_TOKEN` fällt der Proxy automatisch
in den Gast-Modus zurück.

## Gast-Modus

```env
GLM_USE_GUEST_REFRESH_TOKEN=true
```

- Ignoriert `token.txt`/`GLM_REFRESH_TOKEN`, arbeitet ausschließlich mit
  Gast-Tokens.
- Gast-Tokens werden bei Fehlern automatisch neu geholt (`GLM_GUEST_MAX_RETRIES`).
- Der Pool legt `GLM_MAX_CONCURRENCY` Slots an (jeweils eigene Gast-Sitzung);
  Upstream-Limit ~5 Nachrichten pro Gast-Token, Rotation fängt das ab.
- Temporäre Gast-Tokens werden nicht in `.env`/`token.txt` persistiert.

Alle weiteren Config-Variablen: `.env.example` (kommentiert).

## Architektur & Betrieb

- Architektur/Komponenten: `structure.md` (dieses Verzeichnis).
- Betrieb/Setup im Codespace (rebuild, Autostart, Watchdog, Bundle-Bau):
  Haupt-README des MAIN-Repos, Abschnitte „glm2api" und „Infrastruktur-Soll".

## Tests

```bash
uv run pytest tests/ -q
```
