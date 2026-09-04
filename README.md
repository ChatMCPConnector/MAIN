# MAIN Linux Codespace

Dieses Repository ist für eine browserbasierte Ubuntu-Linux-Entwicklungsumgebung mit GitHub Codespaces vorbereitet.

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/ChatMCPConnector/MAIN?quickstart=1&ref=main)

## Enthalten

- Ubuntu 24.04
- Bash und übliche Linux-Werkzeuge
- Git und GitHub CLI
- Docker mit Docker Compose
- Python 3 mit pip und venv
- Build-Werkzeuge
- vorbereitete Ports 3000, 8000 und 8080
- Zeitzone Europe/Istanbul

## Start

1. Auf **Open in GitHub Codespaces** klicken.
2. Die gewünschte Maschinengröße auswählen.
3. **Create codespace** wählen.

Nach dem Aufbau steht das Linux-Terminal direkt im Browser bereit. Dateien im Repository bleiben auf GitHub gespeichert. Änderungen außerhalb des Repository-Arbeitsordners sollten vor dem Löschen des Codespaces gesichert werden.

## Landschaft mitnehmen (mehrere Accounts / 60h-Limit)

**Kurzantwort: Nein, ein laufender Codespace kann nicht an einen anderen Account weitergegeben werden.** Ein Codespace gehört immer zu Account + Repo + Branch. Was 1:1 mitkommt, ist alles was in diesem Git-Repo liegt und gepusht ist.

Deshalb liegt hier alles versioniert:
- `.devcontainer/setup.sh` baut jede Umgebung identisch auf (läuft automatisch)
- `config/opencode/` = Vorlage für deine opencode-Config, Plugins, Commands (ohne Secrets)
- `dotfiles/aliases.sh` = Aliase, PATH
- `work/` = hier deine Projekte ablegen, damit sie mitkommen
- `scripts/save.sh` = der Umzugs-Befehl

### Umzug in 3 Schritten

Im alten Codespace:
```bash
./scripts/save.sh
```

Im neuen Account:
1. Repo forken (oder public lassen und direkt nutzen) → `codespaces.new/<NEUER-ACCOUNT>/MAIN`
2. Codespace erstellen, warten bis `setup.sh` durch ist
3. Einmalig pro Account einloggen (wird NICHT in Git gespeichert):
```bash
opencode auth login
# falls nötig: cp .env.example .env  → Keys eintragen
```

Danach: `git pull` → 1:1 weiterarbeiten.

Regel: **Alles was bleiben soll, muss unter `/workspaces/MAIN` liegen und per `save.sh` gepusht sein.** `~/.config`, `~/.opencode`, `auth.json`, `.env`, Docker-Volumes kommen nicht automatisch mit.

## Auto-Push: Agent pusht selbst (ohne Nachfragen)

Der Agent (ich) darf jederzeit `./scripts/push.sh` laufen lassen - non-interaktiv, ohne Prompt. Dafür braucht er einmalig einen GitHub PAT:

**Einmal pro Account (2 Minuten):**
1. `github.com/settings/tokens` → Fine-grained Token → nur Repo `MAIN` → `Contents: Read and write` (oder Classic mit Scope `repo`)
2. Entweder als Codespaces-Secret `LANDSCAPE_PAT` hinterlegen (GitHub Settings → Codespaces → Secrets → Repo MAIN) - dann geht ab sofort jeder neue Codespace automatisch. Oder im Codespace:
```bash
./scripts/auth.sh setup   # Token einmal einfügen, liegt danach in ~/.config/landscape/pat (600, außerhalb des Repos)
./scripts/auth.sh status  # Prüfung: Push-Test muss OK sagen
```

Danach musst du nichts mehr tun. Sag einfach "push" und ich pushe. Das Token kommt nie ins Git.
