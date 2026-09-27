# CLAUDE.md — Anweisungen für Claude Code in diesem Repo

**Die verbindliche Regel steht in [`AGENTS.md`](AGENTS.md).** Diese Datei existiert,
weil Claude Code `CLAUDE.md` liest, nicht `AGENTS.md` — ohne sie kennt ein
Claude-Code-Agent die Save-Pflicht nicht.

## Kurzfassung (die einzige Regel, die zählt)

**Am Ende eines abgeschlossenen Arbeitsgangs `./infra/scripts/save.sh "<message>"`
ausführen — ohne Rückfrage.** Das macht in einem Durchgang: Commit, Rebase,
Push **und** Google-Drive-Backup.

- Vorher `git status` / `git diff` prüfen; Secrets sind durch `.gitignore`
  ausgeschlossen.
- **Nur eigene Pfade committen** (`git commit -- <pfad>`). Das Repo ist für
  mehrere eigene Accounts shared: `git add -A` oder ein nacktes `git commit`
  nimmt fremde, gerade in Arbeit befindliche Änderungen mit. Siehe
  `infrastructure.md`, Abschnitt „Persistenz“.
- Ist ein **fremder** Änderungsstand im Baum, nicht committen: dem Nutzer melden
  und die eigenen Pfade separat committen.
- **Kein Autosave-Daemon** (Nutzerentscheidung 2026-09-27): dieser Session-Befehl
  ist der einzige Auslöser für Commit **und** Drive-Backup. Ohne ihn ist eine
  Stunde Agent-Arbeit nach einem Codespace-Verlust weg.
- Scheitert das Drive-Backup, meldet `save.sh` das — die Warnung ist ernst
  gemeint und wird mit `./infra/scripts/gdrive-backup.sh backup --force`
  nachgeholt.
- **Kein erneutes Nachfragen**: Die Commit-/Push-Freigabe ist dauerhaft erteilt.

## Nicht-Infrastruktur-Edits

Normale Code-, Doku- und Config-Edits sind **keine** Infrastruktur-Änderung: keine
Infra-Prüfung, kein Doku-Zwang, kein Extra-Commit. Details in `AGENTS.md`.

## Session-Ende

Auch wenn nichts zu committen ist: `git status` prüfen und melden. Bei
fremdem Änderungsstand im Baum (andere Accounts arbeiten parallel) **nicht**
committen, sondern melden — das ist in diesem Repo keine Ausnahme, sondern der
Regelfall.
