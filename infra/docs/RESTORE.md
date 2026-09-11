# RESTORE — MAIN aus Google-Drive-Backup wiederherstellen

Für den Fall, dass der GitHub-Account gebannt / das Repo geschlossen wurde.
Eine Kopie dieser Anleitung liegt **immer neben den Bundles auf Drive**
(`MAIN-backup/RESTORE.md`) — sie überlebt also auch dann, wenn GitHub komplett weg ist.

Auf Drive liegen:

| Datei | Inhalt |
|---|---|
| `MAIN.bundle` | neueste Sicherung (komplettes Repo: History + alle Branches) |
| `MAIN.backup.bundle` | vorherige Generation (falls `MAIN.bundle` defekt) |
| `RESTORE.md` | diese Anleitung |

---

## Szenario A: Total-Restore in frischem Codespace (neuer Account)

Voraussetzung: neuer GitHub-Account, dort ein (leeres oder minimales) Repo
`MAIN` angelegt und einen Codespace davon gestartet (`/workspaces/MAIN` existiert,
läuft evtl. auf altem Stand oder ist leer).

### 1. Bundle herunterladen

**Variante Browser (empfohlen, kein Tool nötig):**
drive.google.com → Ordner `MAIN-backup` → `MAIN.backup.bundle`
(oder `MAIN.bundle`) herunterladen → per **Drag & Drop in den Codespace-Explorer**
hochladen (landet unter `/workspaces/`).

**Variante rclone (falls rclone + Google-Login im Codespace vorhanden):**
```bash
rclone copy gdrive:MAIN-backup/MAIN.backup.bundle /workspaces --drive-chunk-size 32M
```

### 2. Repo-Inhalt ersetzen

In einem Terminal im Codespace:

```bash
cd /workspaces
git clone MAIN.backup.bundle MAIN-restored
rm -rf MAIN.old
mv MAIN MAIN.old            # altes (leeres/minimales) Repo beiseite
mv MAIN-restored MAIN       # Bundle-Inhalt an den kanonischen Platz
cd MAIN
git remote remove origin 2>/dev/null || true
git remote add origin https:/​/github.com/<NEUER-ACCOUNT>/MAIN
```

> Wenn `/workspaces/MAIN` komplett leer ist (kein Git-Repo), einfach das `mv MAIN MAIN.old` weglassen.

### 3. Push zum neuen GitHub (neuer PAT nötig!)

Der alte PAT gehört zum gebannten Account — einmalig pro neuem Account:

1. Auf GitHub (neuer Account): Settings → Developer settings → Personal access
   token → neues Token mit `repo`-Scope erzeugen.
2. Im Codespace: `./infra/scripts/auth.sh setup <NEUER-PAT>`
   (alternativ: `LANDSCAPE_PAT` als Codespaces-Secret am neuen Account hinterlegen
   — dann passiert das künftig automatisch).
3. Pushen + Drive-Backup-Verkettung testen:
   ```bash
   ./infra/scripts/save.sh "restore: from gdrive backup <datum>"
   ```
   → pusht zum neuen GitHub UND sichert automatisch das nächste Bundle nach Drive
   (rclone-Conf kommt aus dem Secrets-Bundle zurück, siehe Schritt 4).

### 4. Landschaft vollständig aufsetzen (ein Befehl)

```bash
bash .devcontainer/setup.sh
```

Das stellt automatisch her: Systempakete, opencode, uv, Firefox-Browser-Runtime,
rclone, **Secrets-Unlock** (alle API-Keys, LLM-Proxy-Credentials, gemini-web-Cookie,
rclone-Conf — Passphrase liegt als `config/passphrase` im Bundle), Git-Auth,
MCP-Registrierung, glm2api-Proxy inkl. Start, Autosave- + Watchdog-Daemons.

Danach: Codespace einmal **Rebuild** (oder weiterarbeiten) — alles läuft wie vorher.

### 5. Aufräumen (optional)

```bash
rm -rf /workspaces/MAIN.old /workspaces/MAIN.backup.bundle
```

---

## Szenario B: Stand in bestehender Landschaft zurückholen

Wenn GitHub noch funktioniert und nur ein alter Stand gebraucht wird:

```bash
gdrive restore /tmp/opencode/MAIN-restored   # Alias: gdrive = infra/scripts/gdrive-backup.sh
```

klont aus der Backup-Generation (Fallback: aktuelle Generation) und liegt dann
unter `/tmp/opencode/MAIN-restored` — einzelne Dateien/Commits daraus
übernehmen (z. B. `git -C /tmp/opencode/MAIN-restored show <sha>:<pfad>`).

---

## Wichtig zu wissen

- **Gitignore'd Inhalte sind NICHT im Backup** (Browser-Profile, `.runtime/`,
  `.env`-Klartexte) — siehe `landscape-diff`. Rekonstruierbar: Browserprofil
  (neu einloggen), Rest kommt aus dem Secrets-Bundle.
- **Bundle-Integrität:** Jedes Bundle wurde vor dem Upload MD5-verifiziert.
  Zur Sicherheit: `git bundle verify /workspaces/MAIN.backup.bundle`.
- **Backup-Alter:** Bundles werden nur bei neuen Commits erzeugt — der Stand
  entspricht dem letzten gepushten Commit (max. 30 Min plus Rotationszyklus).
- **Passphrase:** liegt im Klartext im Bundle (`config/passphrase`) — das ist
  Absicht (Komfort > Sicherheit, siehe infrastructure.md).
