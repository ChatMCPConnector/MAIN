# opencode-sessions MCP

Lokaler MCP-Server zur schnellen Verwaltung von opencode-Sessions direkt in der
SQLite-DB (`~/.local/share/opencode/opencode/opencode.db`). Entstanden, weil das
manuelle Löschen „alle Sessions außer dieser" über CLI-Umwege sehr langsam war —
dieser MCP macht das in Sekunden.

**Zero Dependencies:** nur Node >= 18 (built-in `child_process`) + `sqlite3`-CLI
(beides in jedem Codespace via `.devcontainer/setup.sh` garantiert). Kein npm install.

## Tools

| Tool | Beschreibung |
|---|---|
| `list_sessions` | Sessions neueste zuerst, mit `active` / `is_current_session` Flags. Filter: `directory`, `project`, `limit`. |
| `delete_preview` | Trockenlauf für `delete_sessions`: zeigt victims + geschützte Sessions. |
| `delete_sessions` | Kaskadierende Löschung (confirm=true Pflicht). Räumt zusätzlich verwaiste Events auf + VACUUM. |
| `session_info` | Details einer Session (Messages, Tokens, Kosten, Modell). |
| `search_sessions` | Volltextsuche über Titel + Message-Inhalte. |
| `db_stats` | DB-Statistik (Größe, Zählungen, aktive Prozesse, aktuelle Session-ID). |

## Schutzmechanismen bei delete_sessions

- `confirm: true` ist Pflicht (sonst nur Hinweis).
- **Aktuelle Session** des aufrufenden Prozesses wird automatisch erkannt
  (via `OPENCODE_PID` → cwd → neueste Session dort) und nie gelöscht.
- **Aktive Sessions** anderer laufender opencode-Prozesse geschützt (`keep_active`, default true).
- **Geteilte Sessions** (Share-Links) geschützt, außer `keep_shared: true`.
- `keep_ids: [...]` schützt zusätzlich explizite IDs.

## Lösch-Kaskade

`part → message → session_message, session_input, session_context_epoch, session_share, todo, event, event_sequence → session` + Entfernen verwaister Events (aggregate_id ohne Session) + `VACUUM`.

## Parameter für delete_sessions / delete_preview

```
older_than_days  number   nur Sessions, deren letztes Update älter ist
directory        string   nur Sessions in diesem Verzeichnis
delete_ids       string[] explizite IDs (überschreibt Filter)
keep_ids         string[] geschützte IDs
keep_active      bool     aktive Prozesse schützen (default true)
keep_shared      bool     true = Shares trotzdem löschen (default false = schützen)
```

## Integration

- Registriert in `.opencode/opencode.json` unter `mcp.opencode-sessions`
  (kommt mit dem Repo in jeden Codespace).
- `.devcontainer/setup.sh` stellt die Registrierung idempotent sicher — auch wenn
  das Repo an einem anderen Pfad liegt oder die Config noch keinen `mcp`-Key hat
  (fügt ihn dann nach Zeile 1 ein).
- Debug: `node mcp/opencode-sessions-mcp.js` und JSON-RPC-Zeilen auf stdin senden.
  Alternative DB: `OPENCODE_DB=/pfad/zur.db` Umgebungsvariable.

## Typischer Ablauf im Agenten-Alltag

1. `delete_preview` → zeigt was wegfallen würde
2. `delete_sessions {confirm: true}` → ausführen
3. Ergebnis: Sessions weg, Events aufgeräumt, DB per VACUUM verkleinert
   (Referenz: 574 MB → 2 MB beim ersten Lauf, 93k Orphan-Events entfernt).
