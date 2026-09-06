# Agent Instructions

## 0. Automatik (was ohne dich passiert)

- Beim Codespace-Start läuft `.devcontainer/setup.sh` automatisch (`postCreateCommand`):
  Systempakete → opencode → Shell-Aliase → **Secrets-Auto-Unlock** (via `LANDSCAPE_PASSPHRASE`) → **Git-Auth** (via `LANDSCAPE_PAT`) → Browser-Runtime.
- Erste Pflichtlektüre: `INFRASTRUCTURE.md` (Soll-Zustand) + `README.md` (Mehraccount-Modell).
- Repo ist shared für mehrere eigene Accounts. Alles Bleibende liegt unter `/workspaces/MAIN` und wird per `./scripts/save.sh` gepusht. Einmal pro Account: PAT + Passphrase als Codespaces-Secrets hinterlegen, danach ist alles automatisch.

## 1. Session-Start

- Lies `INFRASTRUCTURE.md` einmal pro Session.
- Kein Re-Read vor jedem Edit. Nur erneut lesen, wenn der Task Infrastruktur berührt (Browser, Ports, Display, Profile, Installationen, Dependencies, Persistenzpfade).

## 2. Was als Infrastruktur-Änderung zählt

Nur das ist eine Infrastruktur-Änderung:

- neues/geändertes Tool, Version, Pfad, Port, Service, Profil,
- neues/geändertes Setup- oder Startskript,
- geänderte Persistenz- oder Sicherheitsregel.

Normale Code-, Doku- und Config-Edits sind keine Infrastruktur-Änderungen: keine Infra-Prüfung, kein Doku-Zwang, kein Extra-Commit.

## 3. Infrastructure

- `INFRASTRUCTURE.md` beschreibt den Soll-Zustand. Kanonisch ist immer: gepinnte Version im Repo + reproduzierbares Skript unter `scripts/`.
- PIDs, `ss`-Ausgaben und laufende Sitzungen sind ephemeral: vor Wiederverwendung einmal prüfen (`pgrep`, `ss`, `curl`), nie als dauerhaften Zustand dokumentieren oder als Blocker verwenden.
- Nur verifizierte, tatsächlich ausgeführte Änderungen dokumentieren. Planung und Ist-Zustand getrennt halten.
- Keine parallele agentspezifische Infrastrukturakte.
- Keine Secrets (Tokens, Cookies, Passwörter) in die Doku schreiben.

## 4. Safety

- Vor Installation/Start/Löschung genau einen Bestandscheck machen (z. B. vorhandener Build, laufender Prozess, belegter Port). Danach handeln, nicht in Schleifen weiterprüfen.
- Keine fremden Prozesse beenden, keine Caches/Profile/Installationen löschen ohne einmalige explizite Freigabe des Users. Eine erteilte Freigabe gilt, muss nicht erneut eingeholt werden.
- Für schwer rückgängig machbare Aktionen Rückweg in einem Satz festhalten (Reinstall-/Restart-Befehl).

## 5. Persistence

- Fertige Arbeit liegt vollständig unter `/workspaces/MAIN` und wird per Git erfasst. Unfertige/temporäre Inhalte nach `/workspaces` oder `.runtime/`, nie als „fertig" behandeln.
- `.runtime/`, Browserprofile, Caches und Klartext-Secrets werden nicht committet (siehe `.gitignore`). Was davon für einen neuen Codespace nötig ist, muss als reproduzierbares Skript unter `scripts/` im Repo liegen.
- `INFRASTRUCTURE.md` nur bei tatsächlicher Infrastruktur-Änderung im selben Arbeitsgang aktualisieren. Kein Doku-Update und kein Commit für Nicht-Infra-Änderungen erzwingen. Commits nur auf explizite Aufforderung.
