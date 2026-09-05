# MAIN Linux Codespace

Browserbasierte Ubuntu-Linux-Umgebung mit GitHub Codespaces.

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/ChatMCPConnector/MAIN?quickstart=1&ref=main)

## Enthalten

- Ubuntu 24.04, Bash, Git, GitHub CLI, Docker, Python 3, Build-Werkzeuge
- Ports 3000, 8000, 8080 · Zeitzone Europe/Berlin
- opencode mit TokenRouter/GLM 5.3 (1M Kontext) — Config liegt in `.opencode/` im Repo

## Struktur

```
.devcontainer/   Umgebung: devcontainer.json + setup.sh (läuft automatisch)
.opencode/       opencode-Config (wird direkt aus dem Repo gelesen)
scripts/         save.sh (push), auth.sh (PAT), secrets.sh (verschlüsseltes Bundle)
dotfiles/        Aliase, PATH (werden in .bashrc verlinkt)
config/          secrets.enc — verschlüsseltes Secrets-Bundle
work/            eigene Projekte hier ablegen
```

## Account-Wechsel (60h-Limit)

Ein Codespace gehört immer zu Account + Repo + Branch und kann nicht übertragen
werden. Mitkommt 1:1 alles, was in diesem Repo liegt und gepusht ist.

Im alten Codespace:
```bash
./scripts/save.sh
```

Im neuen Account:
1. Repo forken → `codespaces.new/<NEUER-ACCOUNT>/MAIN` → Codespace erstellen
2. `setup.sh` läuft automatisch (System, opencode, Aliase, Auto-Unlock)
3. Einmalig pro Account einloggen (kommt nie ins Git):
```bash
opencode auth login
./scripts/auth.sh setup   # nur falls LANDSCAPE_PAT nicht als Codespaces-Secret liegt
```

Regel: **Alles was bleiben soll, muss unter `/workspaces/MAIN` liegen und per
`save.sh` gepusht sein.** `~/.config`, `auth.json`, `.env`, Docker-Volumes
kommen nicht automatisch mit — Secrets siehe unten.

## Git-Auth für Auto-Push (einmal pro Account)

1. `github.com/settings/tokens` → Fine-grained Token → nur Repo `MAIN` → `Contents: Read and write`
2. Als Codespaces-Secret `LANDSCAPE_PAT` hinterlegen (GitHub Settings → Codespaces → Secrets) —
   danach ist jeder neue Codespace automatisch authentifiziert.
   Alternativ im Codespace: `./scripts/auth.sh setup`

Danach pusht der Agent selbst, ohne Nachfrage: sag einfach "push".

## Secrets verschlüsselt mitsyncen (optional)

Beide Accounts sind deine — mit einer Passphrase kommt PAT + opencode-Login +
TokenRouter-Key + `.env` verschlüsselt ins (publice) Repo:

```bash
./scripts/secrets.sh lock     # Passphrase wählen (nie in den Chat schreiben)
./scripts/secrets.sh unlock   # im neuen Codespace
```

Vollautomatisch: `LANDSCAPE_PASSPHRASE` als Codespaces-Secret hinterlegen —
dann entsperrt sich jeder neue Codespace beim Start von selbst.

Hinweis: Der mitgesyncte PAT stammt vom Account, der `lock` gemacht hat.
Bei Leak-Verdacht: Token revoken, Keys rotieren, neu locken.
