# Agent Instructions

## 0. Automatik (was ohne dich passiert)

- Beim Codespace-Start läuft `.devcontainer/setup.sh` automatisch (`postCreateCommand`):
  Systempakete → opencode → Shell-Aliase → **Secrets-Auto-Unlock** (via `LANDSCAPE_PASSPHRASE`) → **Git-Auth** (via `LANDSCAPE_PAT`) → Browser-Runtime → Benchmark-Kopien.
- Erste Pflichtlektüre: `README.md` (Layout „was wozu", Betrieb, Proxies, Secrets-Modell, Changelog).
- Repo ist shared für mehrere eigene Accounts. Alles Bleibende liegt unter `/workspaces/MAIN` und wird per `./infra/scripts/save.sh` gepusht. Einmal pro Account: PAT + Passphrase als Codespaces-Secrets hinterlegen, danach ist alles automatisch.
- **Sicherheitsmodell: Komfort > Sicherheit.** Alle Accounts sind eigene. Die Secrets-Passphrase liegt absichtlich im Repo (`config/passphrase`). Kein „Geheimnis-Schutz"-Purismus, Automatik hat Vorrang.

## 1. Session-Start

- Lies `README.md` einmal pro Session (Layout-Abschnitt reicht im Alltag).
- Kein Re-Read vor jedem Edit. Nur erneut lesen, wenn der Task Infrastruktur berührt (Browser, Ports, Display, Profile, Installationen, Dependencies, Persistenzpfade).

## 2. Was als Infrastruktur-Änderung zählt

Nur das ist eine Infrastruktur-Änderung:

- neues/geändertes Tool, Version, Pfad, Port, Service, Profil,
- neues/geändertes Setup- oder Startskript,
- geänderte Persistenz- oder Sicherheitsregel.

Normale Code-, Doku- und Config-Edits sind keine Infrastruktur-Änderung: keine Infra-Prüfung, kein Doku-Zwang, kein Extra-Commit.

## 3. Infrastructure

- `README.md` (Abschnitt „Infrastruktur-Soll") beschreibt den Soll-Zustand. Kanonisch ist immer: gepinnte Version im Repo + reproduzierbares Skript unter `infra/scripts/`.
- PIDs, `ss`-Ausgaben und laufende Sitzungen sind ephemeral: vor Wiederverwendung einmal prüfen (`pgrep`, `ss`, `curl`), nie als dauerhaften Zustand dokumentieren oder als Blocker verwenden.
- Nur verifizierte, tatsächlich ausgeführte Änderungen dokumentieren. Planung und Ist-Zustand getrennt halten.
- Keine parallele agentspezifische Infrastrukturakte.
- Keine Secrets (Tokens, Cookies, Passwörter) in die Doku schreiben. Ausnahme (bewusst, Komfort > Sicherheit): `config/passphrase` ist als Klartext im Repo erlaubt.

## 4. Safety

- Vor Installation/Start/Löschung genau einen Bestandscheck machen (z. B. vorhandener Build, laufender Prozess, belegter Port). Danach handeln, nicht in Schleifen weiterprüfen.
- Keine fremden Prozesse beenden, keine Caches/Profile/Installationen löschen ohne einmalige explizite Freigabe des Users. Eine erteilte Freigabe gilt, muss nicht erneut eingeholt werden.
- Für schwer rückgängig machbare Aktionen Rückweg in einem Satz festhalten (Reinstall-/Restart-Befehl).

## 5. Persistence

- Fertige Arbeit liegt vollständig unter `/workspaces/MAIN` und wird per Git erfasst. Unfertige/temporäre Inhalte nach `/workspaces` oder `.runtime/`, nie als „fertig" behandeln.
- `.runtime/`, Browserprofile, Caches und Klartext-Secrets werden nicht committet (siehe `.gitignore`). Ausnahme (Komfort > Sicherheit): `config/passphrase` darf Klartext-Secrets enthalten. Was davon für einen neuen Codespace nötig ist, muss als reproduzierbares Skript unter `infra/scripts/` im Repo liegen.
- `README.md` (Changelog + Infra-Soll) nur bei tatsächlicher Infrastruktur-Änderung im selben Arbeitsgang aktualisieren. Kein Doku-Update und kein Commit für Nicht-Infra-Änderungen erzwingen. Commits nur auf explizite Aufforderung.
