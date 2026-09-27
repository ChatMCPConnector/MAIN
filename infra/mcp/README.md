# opencode-sessions MCP Server

Ein schlanker, hochperformanter **Model Context Protocol (MCP)** Server, der es KI-Assistenten (insbesondere opencode) ermöglicht, Sitzungen direkt über die lokale SQLite-Datenbank (`opencode.db`) abzufragen, zu durchsuchen, zu analysieren und sicher zu bereinigen.

---

## Inhaltsverzeichnis

1. [Vorteile & Architektur](#vorteile--architektur)
2. [Voraussetzungen](#voraussetzungen)
3. [Schnellstart & Installation](#schnellstart--installation)
4. [Konfiguration in opencode](#konfiguration-in-opencode)
5. [Umgebungsvariablen](#umgebungsvariablen)
6. [Alle Funktionen (MCP Tools) im Detail](#alle-funktionen-mcp-tools-im-detail)
   - [1. list_sessions](#1-list_sessions)
   - [2. session_info](#2-session_info)
   - [3. search_sessions](#3-search_sessions)
   - [4. db_stats](#4-db_stats)
   - [5. delete_preview](#5-delete_preview)
   - [6. delete_sessions](#6-delete_sessions)
7. [Sicherheitsmechanismen & Kill-Schutz](#sicherheitsmechanismen--kill-schutz)
8. [Troubleshooting & FAQ](#troubleshooting--faq)

---

## Vorteile & Architektur

Standardmäßig speichert opencode alle Sitzungen, Nachrichten, Parts, Todos und Event-Streams in einer SQLite-Datenbank unter `~/.local/share/opencode/opencode.db`.

Dieser MCP-Server bietet signifikante Vorteile:
- **Keine externen npm-Abhängigkeiten**: Basiert ausschließlich auf Node.js-Standardmodulen (`child_process`, `fs`, `os`, `path`) und dem systemweiten `sqlite3`-CLI.
- **Enorme Geschwindigkeit**: Direkte SQL-Abfragen statt langsamer CLI/API-Umwege.
- **Gründliche Bereinigung**: opencode hinterlässt beim Löschen von Nachrichten oft hunderttausende Events (`event`, `event_sequence`), die Datenbanken auf hunderte Megabyte aufblähen (in der Praxis getestet: Reduktion von **574 MB auf 2 MB** und Entfernung von über 93.000 verwaisten Events in einem einzigen Durchlauf). Dieser Server bereinigt verwaiste Events kaskadierend und führt automatisch `VACUUM` aus.
- **Integrierter Kill-Schutz**: Verhindert zuverlässig, dass ein aktiver opencode-Prozess oder die aktuelle Sitzung versehentlich gelöscht wird.

---

## Voraussetzungen

1. **Node.js**: Version 18 oder höher (`node -v`).
2. **sqlite3 CLI**: Muss im Systempfad (`PATH`) verfügbar sein:
   - **Debian / Ubuntu / Devcontainer**:
     ```bash
     sudo apt-get update && sudo apt-get install -y sqlite3
     ```
   - **macOS** (Homebrew):
     ```bash
     brew install sqlite3
     ```
   - **Arch Linux**:
     ```bash
     sudo pacman -S sqlite
     ```
   - **Alpine Linux**:
     ```bash
     apk add sqlite
     ```
3. **opencode SQLite-Datenbank**:
   Standardmäßig unter:
   `~/.local/share/opencode/opencode.db`

---

## Schnellstart & Installation

1. Entpacke das Zip-Archiv in dein gewünschtes Verzeichnis, z.B.:
   ```bash
   mkdir -p ~/.config/opencode/mcp/opencode-sessions
   unzip opencode-sessions-mcp.zip -d ~/.config/opencode/mcp/opencode-sessions/
   ```

2. Stelle sicher, dass die Datei ausführbar ist:
   ```bash
   chmod +x ~/.config/opencode/mcp/opencode-sessions/opencode-sessions-mcp.js
   ```

3. Teste den manuellen Start über die Kommandozeile (sollte auf STDIN warten):
   ```bash
   node ~/.config/opencode/mcp/opencode-sessions/opencode-sessions-mcp.js
   ```
   *(Mit `Strg+C` beenden).*

---

## Konfiguration in opencode

Füge den Server in deine `opencode.json` ein (entweder global unter `~/.config/opencode/opencode.json` oder projektbezogen unter `.opencode/opencode.json`):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "opencode-sessions": {
      "type": "local",
      "command": [
        "node",
        "/ABSOLUTER/PFAD/ZU/opencode-sessions-mcp.js"
      ],
      "enabled": true,
      "environment": {}
    }
  }
}
```

*Hinweis:* Ersetze `/ABSOLUTER/PFAD/ZU/opencode-sessions-mcp.js` mit dem tatsächlichen Pfad auf deinem Rechner.

---

## Umgebungsvariablen

Der Server unterstützt folgende optionale Umgebungsvariablen:

| Variable | Beschreibung | Standardwert |
|---|---|---|
| `OPENCODE_DB` | Benutzerdefinierter Pfad zur `opencode.db` Datei | `~/.local/share/opencode/opencode.db` |
| `OPENCODE_PID` | Prozess-ID des übergeordneten opencode-Prozesses (zur Erkennung aktiver Sessions) | Auto-Detect via `/proc` |

Beispiel in `opencode.json`:
```json
"environment": {
  "OPENCODE_DB": "/custom/path/to/opencode.db"
}
```

---

## Alle Funktionen (MCP Tools) im Detail

Der MCP-Server stellt 6 spezialisierte Tools für den KI-Agenten bereit:

```
┌─────────────────────────────────────────────────────────────┐
│                   opencode-sessions MCP                     │
├──────────────────────────┬──────────────────────────────────┤
│ Abfrage & Information    │ Bereinigung & Wartung            │
├──────────────────────────┼──────────────────────────────────┤
│ • list_sessions          │ • delete_preview (Trockenlauf)   │
│ • session_info           │ • delete_sessions (Kaskadierend) │
│ • search_sessions        │ • db_stats                       │
└──────────────────────────┴──────────────────────────────────┘
```

---

### 1. `list_sessions`
Listet vorhandene Sessions auf, sortiert nach Aktualisierungsdatum (`time_updated DESC`).

#### Parameter
| Name | Typ | Erforderlich | Beschreibung |
|---|---|---|---|
| `directory` | `string` | Nein | Filtert nach Workspace-Pfad (z.B. `/workspaces/mein-projekt`). |
| `project` | `string` | Nein | Filtert nach dem Git-Worktree des Projekts (`p.worktree`). |
| `limit` | `number` | Nein | Maximale Anzahl an Ergebnissen (Standard: `100`, Maximum: `500`). |

#### Rückgabebeispiel
```json
[
  {
    "id": "ses_4a71bc9ef201d4a8",
    "title": "Bugfix Authentifizierung",
    "directory": "/workspaces/mein-projekt",
    "agent": "build",
    "model": "antigravity/gemini-3.8-flash",
    "messages": 14,
    "created": "2026-09-28T10:15:30.000Z",
    "updated": "2026-09-28T11:42:10.000Z",
    "age_days": 0.2,
    "active": true,
    "is_current_session": true
  }
]
```
- `active`: Gibt an, ob für das Verzeichnis dieser Session aktuell ein laufender `opencode`-Prozess aktiv ist.
- `is_current_session`: Markiert die Session, in welcher der Agent gerade selbst arbeitet.

---

### 2. `session_info`
Ruft Metadaten, Statistiken, Tokenverbrauch und Kosten einer konkreten Session ab.

#### Parameter
| Name | Typ | Erforderlich | Beschreibung |
|---|---|---|---|
| `session_id` | `string` | **Ja** | Die eindeutige Session-ID (z.B. `ses_...`). |

#### Rückgabebeispiel
```json
{
  "id": "ses_4a71bc9ef201d4a8",
  "title": "Bugfix Authentifizierung",
  "directory": "/workspaces/mein-projekt",
  "parent_id": null,
  "model": "antigravity/gemini-3.8-flash",
  "agent": "build",
  "messages": 14,
  "todos": 3,
  "cost": 0.042,
  "tokens": {
    "input": 45200,
    "output": 3810,
    "reasoning": 1200
  },
  "created": "2026-09-28T10:15:30.000Z",
  "updated": "2026-09-28T11:42:10.000Z",
  "share_url": "https://opencode.ai/s/xyz123"
}
```

---

### 3. `search_sessions`
Volltextsuche nach Begriffen sowohl im Session-Titel als auch in allen Nachrichtenblöcken (`part.data`).

#### Parameter
| Name | Typ | Erforderlich | Beschreibung |
|---|---|---|---|
| `query` | `string` | **Ja** | Der gesuchte Text (wird mit automatischem SQL-Escaping gesucht). |
| `limit` | `number` | Nein | Maximale Trefferanzahl (Standard: `30`, Maximum: `100`). |

#### Rückgabebeispiel
```json
[
  {
    "id": "ses_4a71bc9ef201d4a8",
    "title": "Bugfix Authentifizierung",
    "directory": "/workspaces/mein-projekt",
    "updated": "2026-09-28T11:42:10.000Z",
    "is_current_session": false
  }
]
```

---

### 4. `db_stats`
Liefert eine Statusübersicht über die SQLite-Datenbank: Dateigröße, Anzahl der Datensätze und aktive Prozesse.

#### Parameter
*Keine Parameter erforderlich.*

#### Rückgabebeispiel
```json
{
  "db_path": "/home/vscode/.local/share/opencode/opencode.db",
  "db_size_mb": 42.5,
  "sessions": 85,
  "messages": 1420,
  "parts": 3890,
  "events": 28410,
  "active_opencode_processes": 1,
  "current_session_id": "ses_4a71bc9ef201d4a8",
  "version": "1.0.0"
}
```

---

### 5. `delete_preview`
**Trockenlauf (Dry Run)** vor dem eigentlichen Löschen. Zeigt genau an, welche Sessions gelöscht würden und welche durch die Schutzregeln verschont bleiben.

#### Parameter
| Name | Typ | Erforderlich | Beschreibung |
|---|---|---|---|
| `older_than_days` | `number` | Nein | Nur Sessions auswählen, die älter als X Tage sind. |
| `directory` | `string` | Nein | Auf ein bestimmtes Verzeichnis einschränken. |
| `keep_ids` | `array<string>` | Nein | Explizite Session-IDs, die geschützt werden müssen. |
| `keep_active` | `boolean` | Nein | Laufende opencode-Prozesse schützen (Standard: `true`). |
| `keep_shared` | `boolean` | Nein | `true` = geteilte Sessions (Share-Links) löschen; `false`/Default = schützen. |

#### Rückgabebeispiel
```json
{
  "would_delete": 12,
  "would_keep": 4,
  "victims": [
    {
      "id": "ses_001",
      "title": "Alte Refaktorisierung",
      "updated": "2026-08-15T09:00:00.000Z"
    }
  ],
  "protected": [
    "ses_4a71bc9ef201d4a8",
    "ses_active_client"
  ]
}
```

---

### 6. `delete_sessions`
Löscht Sessions dauerhaft und kaskadierend.

> **WICHTIGER HINWEIS:**
> Aus Sicherheitsgründen MUSS `confirm: true` übergeben werden.
> Es wird dringend empfohlen, vorher immer `delete_preview` auszuführen!

#### Kaskadierender Löschprozess:
Folgende Tabellen werden atomar in einer Transaktion bereinigt:
1. `part` (zugehörig zu `message`)
2. `message`
3. `session_message`
4. `session_input`
5. `session_context_epoch`
6. `session_share`
7. `todo`
8. `event` (zugehörig zur Session)
9. `event_sequence` (zugehörig zur Session)
10. `session`
11. Verwaiste Events (`aggregate_id LIKE 'ses_%'`)
12. Automatisches `VACUUM` (gibt Speicherplatz sofort an das Dateisystem frei).

#### Parameter
| Name | Typ | Erforderlich | Beschreibung |
|---|---|---|---|
| `confirm` | `boolean` | **Ja** | **Muss `true` sein**, sonst bricht die Funktion mit einem Fehler ab. |
| `older_than_days` | `number` | Nein | Nur Sessions löschen, die älter als X Tage sind. |
| `directory` | `string` | Nein | Nur Sessions in diesem Verzeichnis löschen. |
| `delete_ids` | `array<string>` | Nein | Gezielte Liste von Session-IDs zum Löschen. |
| `keep_ids` | `array<string>` | Nein | Liste von Session-IDs, die verschont werden sollen. |
| `keep_active` | `boolean` | Nein | Aktive Prozesse schützen (Standard: `true`). |
| `keep_shared` | `boolean` | Nein | `true` = Geteilte Sessions auch löschen (Standard: `false` = geschützt). |

#### Rückgabebeispiel
```json
{
  "deleted": 12,
  "deleted_sessions": [
    { "id": "ses_001", "title": "Alte Refaktorisierung" }
  ],
  "skipped_protected": 4,
  "protected_current_session": true,
  "orphan_events_removed": 15420
}
```

---

## Sicherheitsmechanismen & Kill-Schutz

Um versehentlichen Datenverlust oder Abstürze im laufenden Betrieb zu verhindern, besitzt der MCP-Server dreifachen Schutz:

1. **Aktuelle Session des Aufrufers (`callerSessionId`)**:
   Der Server ermittelt die Session des aufrufenden Agenten und schließt diese ausnahmslos von jeder Löschung aus (`protected_current_session: true`).
2. **Prozessüberwachung (`guessActiveSessionIds`)**:
   Laufende `opencode`-Prozesse werden unter Linux direkt aus `/proc` analysiert. Die jeweils jüngste Session des Arbeitsverzeichnisses eines laufenden Prozesses wird geschützt.
3. **Geteilte Sessions (`session_share`)**:
   Sessions, für die ein externer Link generiert wurde, werden standardmäßig geschützt und nur gelöscht, wenn explizit `keep_shared: true` gesetzt wird.

---

## Troubleshooting & FAQ

### `sqlite3 nicht aufrufbar`
- **Ursache:** Das CLI-Tool `sqlite3` ist nicht auf dem Rechner installiert oder liegt nicht im `$PATH`.
- **Lösung:** Installiere es per Paketmanager (z.B. `sudo apt install sqlite3` oder `brew install sqlite3`).

### `DB nicht gefunden: /.../opencode.db`
- **Ursache:** opencode wurde auf dem System noch nie ausgeführt oder die Datenbank liegt an einem anderen Ort.
- **Lösung:** Setze die Umgebungsvariable `OPENCODE_DB` in der `opencode.json` auf den tatsächlichen Pfad deiner Datenbank.

### `confirm=true erforderlich`
- **Ursache:** Schutzfunktion von `delete_sessions`.
- **Lösung:** Führe zuerst `delete_preview` aus und setze beim Aufruf von `delete_sessions` den Parameter `confirm: true`.
