# Copilot

**Die verbindliche Regel steht in [`AGENTS.md`](AGENTS.md).** Diese Datei existiert,
weil GitHub Copilot `.github/copilot-instructions.md` liest, nicht `AGENTS.md` — ohne sie kennt ein Agent hier die
Save-Pflicht nicht.

## Kurzfassung (die einzige Regel, die zählt)

**Am Ende eines abgeschlossenen Arbeitsgangs `./infra/scripts/save.sh "<message>"`
ausführen — ohne Rückfrage.** Das macht in einem Durchgang: Commit, Rebase, Push
**und** Google-Drive-Backup.

- Vorher `git status` / `git diff` prüfen; Secrets sind durch `.gitignore`
  ausgeschlossen.
- **Nur eigene Pfade committen** (`git commit -- <pfad>`). Das Repo ist für
  mehrere eigene Accounts shared: `git add -A` oder ein nacktes `git commit`
  nimmt fremde, gerade in Arbeit befindliche Änderungen mit.
- Ist ein **fremder** Änderungsstand im Baum: nicht committen, dem Nutzer melden,
  eigene Pfade separat committen.
- **Kein Autosave-Daemon** (Nutzerentscheidung 2026-09-27). Dieser
  Session-Befehl ist der einzige Auslöser für Commit **und** Drive-Backup. Ohne
  ihn ist bis zu einer Stunde Agent-Arbeit nach einem Codespace-Verlust weg.
- Scheitert das Drive-Backup, meldet `save.sh` das; die Warnung mit
  `./infra/scripts/gdrive-backup.sh backup --force` nachholen.
- **Nicht erneut nachfragen** — die Commit-/Push-Freigabe ist dauerhaft erteilt.
