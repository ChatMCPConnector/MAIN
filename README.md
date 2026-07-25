# Nebula Stride

**Nebula Stride** ist ein vollständig offline spielbarer, eigenständiger 3D-Endless-Runner für Android. Die Pilotin Astra flieht durch die zerfallende Maschinenstadt Asterion, wechselt zwischen drei Energiespuren, springt über Plasmabarrieren, rutscht unter Energiebögen hindurch und sammelt Sternsplitter.

## Funktionen

- Automatisches Vorwärtslaufen mit kontrolliert steigender Geschwindigkeit
- Drei Spuren, Touch-Wischen und zusätzliche Tastatursteuerung
- Springen, Rutschen, mehrere Hindernistypen und Sammelobjekte
- Prozedurale, stets lösbare Hindernismuster mit wiederverwendeten Objekt-Pools
- Distanzpunkte, Sammelbonus und lokaler Highscore
- Erststart-Tutorial, Pause, Game over, Neustart, Einstellungen und Credits
- Automatische Pause bei App-Unterbrechungen
- Selbst erzeugte Low-Poly-Geometrie sowie prozedurale Musik und Sounds
- Keine Werbung, Tracker, Konten, Cloud-Dienste oder Netzwerkberechtigungen

## Steuerung

| Aktion | Android | Desktop/Test |
|---|---|---|
| Spur links | Nach links wischen | A / Pfeil links |
| Spur rechts | Nach rechts wischen | D / Pfeil rechts |
| Springen | Nach oben wischen | W / Pfeil oben |
| Rutschen | Nach unten wischen | S / Pfeil unten |
| Pause | Pause-Schaltfläche | Escape |

## Technologie

- Godot 4.7.1, GDScript
- GL Compatibility Renderer für breite Android-Kompatibilität
- Primär Querformat, 1280 × 720 Referenz-Viewport
- Android ARM64 Release; x86_64 zusätzlich im Debug-Build für Emulatoren
- JDK 17 für Android-Werkzeuge

## Lokal starten

1. Godot 4.7.1 öffnen.
2. Dieses Verzeichnis importieren.
3. `project.godot` starten.

Headless-Tests:

```bash
godot --headless --path . --script tests/test_runner.gd
```

Android-Export benötigt die zu Godot 4.7.1 passenden Export-Templates. Die Release-Signierung wird im CI mit einem nur für den Workflow-Lauf erzeugten temporären Schlüssel vorgenommen.

## GitHub Actions

`.github/workflows/nebula-stride-android.yml` führt aus:

1. Projektimport und GDScript-Validierung
2. Headless-Logiktests
3. Android-Debug- und Release-Export
4. Signatur- und Paketprüfung
5. Installation und Start auf einem API-35-x86_64-Emulator
6. Touch-/Tastatur-Smoke-Test, Logcat-Prüfung und Screenshots
7. Upload von APK, Logs, Testergebnissen und Screenshots als GitHub-Artefakte
8. Upload ausschließlich der Release-APK in den Sauce-Labs-App-Speicher der EU-Region

Der Workflow startet **keine** Sauce-Labs-Geräte-, Espresso- oder Appium-Sitzung.

## Projektstruktur

- `scenes/` – Einstiegsszene
- `scripts/` – Spielzustand, Spieler, Strecke, Speicherung, Audio und UI
- `tests/` – reproduzierbare Headless-Tests
- `assets/` – selbst erstelltes App-Symbol
- `docs/` – Game Design und technische Entscheidungen
- `.github/workflows/` – Build-, Emulator- und Upload-Pipeline

## Screenshots

Die aktuellen Screenshots werden bei jedem erfolgreichen Workflow-Lauf als Artefakt `NebulaStride-screenshots` erzeugt. Sie zeigen Tutorial/Hauptmenü, laufendes Spiel und Game-over-Zustand.
