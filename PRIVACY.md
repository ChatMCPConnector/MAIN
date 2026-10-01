# Datenschutzerklärung

Diese Anwendung (`loltthef`) ist ein **privates Backup-Werkzeug** für ein
einziges, eigenes Konto. Sie läuft ausschließlich lokal und betreibt keinen
eigenen Server.

## Welche Daten verarbeitet werden

- **Google Drive (OAuth-Scope `drive`):** Das lokale Werkzeug `rclone` lädt
  Sicherungen des eigenen Repositorys (als `git bundle`) in einen Ordner
  (`MAIN-backup`) im **eigenen** Google Drive hoch und liest sie zum
  Wiederherstellen wieder aus.
- **OAuth-Token:** Der von Google ausgestellte Access-/Refresh-Token wird
  ausschließlich lokal in `~/.config/rclone/rclone.conf` gespeichert und nur
  zur Authentifizierung gegenüber Google verwendet.

## Weitergabe

Es findet **keine** Weitergabe an Dritte statt. Es gibt kein Tracking, keine
Analyse und keine Server außerhalb des eigenen Rechners.

## Kontakt

loltthef@gmail.com
