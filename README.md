# MAIN

Persönliche Multi-Device-Arbeitsumgebung als Code: Dev-Setup, opencode-Config
(mehrere LLM-Provider) und LLM-Proxies — alles versioniert und reproduzierbar
im Repo.

## Was drin ist

| Pfad | Zweck |
|---|---|
| `.devcontainer/` | Dev-Container-Definition + Setup-Skript |
| `.opencode/` | opencode-Config: opencode.json (Provider/MCP), tui.json |
| `config/` | verschlüsseltes Secrets-Bundle + Manifest |
| `infra/` | Werkzeugkasten: `scripts/`, `mcp/` (opencode-sessions MCP), `docs/` (Reverse-Engineering-Doku) |
| `llm-proxies/` | LLM-Proxies: **glm2api** (GLM-Haupt-Proxy), **gemini-web2api** (Gemini Web Pro), **antigravity-proxy** (CloudCode OAuth) |

## Dokumentation

Die vollständige Doku — Layout, Betrieb, Proxies, Infrastruktur-Soll,
Changelog — liegt in **[infrastructure.md](infrastructure.md)**.

## Quick Start

```bash
./infra/scripts/save.sh status    # Überblick (Repo, Auth, Secrets)
```

Näheres: `infrastructure.md`.