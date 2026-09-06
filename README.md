# MAIN Linux Codespace

Browserbasierte Ubuntu-Linux-Umgebung mit GitHub Codespaces — die persönliche
Multi-Account-Arbeitsumgebung als Code.

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/ChatMCPConnector/MAIN?quickstart=1&ref=main)

**Alles Wissenswerte steht in `DOKU.md`** (Layout, Secrets-Modell, Provider,
GLM-Proxies, Benchmark, Umzug) — ergänzt durch `INFRASTRUCTURE.md` (Infra-Soll)
und `AGENTS.md` (Agent-Regeln).

## Enthalten

- Ubuntu 24.04, Bash, Git, GitHub CLI, Docker, Python 3, Build-Werkzeuge
- Ports 3000/8000 (Apps), 8001/8787/8080 (LLM-Proxies), 9222/6082/5920 (Browser, nur lokal) · Zeitzone Europe/Berlin
- opencode mit TokenRouter/GLM 5.3 (1M Kontext) — Config liegt in `.opencode/` im Repo

## Schnellstart

Codespace bauen → `setup.sh` läuft automatisch (Systempakete, opencode,
Secrets-Unlock, Git-Auth, Browser-Runtime, Benchmark-Kopien). Danach:

```bash
./scripts/save.sh status                          # Überblick
./proxies/rebuild.sh                              # GLM-Proxies (optional, dauert Minuten)
/workspaces/<glm2api|hellogml|chat2api>/start.sh  # Proxy starten
```

## Account-Wechsel (60h-Limit)

Ein Codespace gehört immer zu Account + Repo + Branch und kann nicht übertragen
werden. Mitkommt 1:1 alles, was in diesem Repo liegt und gepusht ist.

Im alten Codespace:
1. `./scripts/save.sh` — committet + pusht alles Bleibende
2. ggf. `./scripts/secrets.sh lock` — Secrets-Bundle aktualisieren

Im neuen Codespace (neuer Account):
1. Repo forken, Codespace erstellen — Rest läuft automatisch
2. Einmalig pro Account: `LANDSCAPE_PAT` + `LANDSCAPE_PASSPHRASE` als
   Codespaces-Secrets hinterlegen (Details: DOKU.md Kap. 3 + 8)
