# Riftbound

Riftbound ist ein vollständig per Touch bedienbares Unity-6.3-Action-Roguelite für Android im Hochformat.

## Release-Umfang 1.0

- deterministische Acht-Raum-Runs mit reproduzierbarem Seed
- drei Kampfräume, Schatzkammer, Händler, Heilraum, Elite und Drei-Phasen-Boss
- drei Biome: Versunkene Ruinen, Aschenöde und Kristalltiefen
- deterministische Raum-Anomalien, Laser- und Pulsgefahren
- Nahkampf, Projektilfähigkeit, Dash und zehn Karten mit Vor- und Nachteilen
- fünf Waffen, fünf Rüstungen und sechs Seltenheitsstufen
- Touch-Inventar mit zehn Plätzen, Vergleichen, Lootfilter, Ausrüsten und Zerlegen
- persistente Entdeckungen, höchste Seltenheit und Risssplitter
- atomare Run-Checkpoints mit Backup, Inventar-, Build-, Gegner- und Bosszustand
- automatisches Fortsetzen eines höchstens 24 Stunden alten laufenden Runs
- lokaler Zwei-Spieler-Koop über gemeinsames WLAN oder mobilen Hotspot
- automatische Sitzungserkennung, vierstelliger Sitzungscode und Wiederverbindung
- host-autoritative Gegner, Zielwahl, Bossphasen, Projektile, Fallen und Schaden
- ACK-/Retry-Kanal für Schaden, Wiederbelebung, Raumwechsel, Entscheidungen und Währung
- gemeinsame Karten-, Schatz- und Händlerentscheidungen mit Transaktionsschutz
- synchronisierte Host-Währung und Schutz vor doppelter Belohnungsanwendung
- Solo-Fortsetzung nach Verbindungsabbruch
- adaptive Render-Skalierung, geräteabhängige Qualitätsstufen und 60-FPS-Ziel
- Optionen für große Schrift, hohen Kontrast, reduzierte Bewegung und Vibration
- prozedurales Audio- und Haptik-Feedback ohne externe Laufzeit-Assets
- Safe Area, 9:16-Touch-HUD und Editor-Tastatursteuerung
- EditMode-Tests für Runs, Biome, Loot, Inventar, Meta-Fortschritt, Checkpoints und Koop-Protokolle

## Steuerung

Touch: virtueller Stick, Inventar, Koop-Menü, Angriff, Dash, Fähigkeit und `OPT` für Qualität/Barrierefreiheit.

Editor: WASD/Pfeiltasten, Leertaste, linke Umschalttaste, E und I für das Inventar.

Das Inventar lässt sich nur außerhalb aktiver Kämpfe öffnen. Gemeinsame Koop-Entscheidungen trifft der Host; der Client erhält dieselbe Karte beziehungsweise denselben Gegenstand zuverlässig und genau einmal.

## Lokaler Koop

Beide Geräte müssen im selben lokalen WLAN oder mobilen Hotspot sein. Ein Spieler startet den Host in einem sicheren Raum. Das zweite Gerät findet die Sitzung automatisch und tritt bei. Es werden keine Konten, Cloud-Dienste oder externen Server verwendet.

Technische Details stehen in `docs/COOP.md`. Release- und Prüfhinweise stehen in `docs/RELEASE.md`.

## Android-Build

Die Android-Version ist `1.0.0` mit Versionscode `100`. Der Release-Build verwendet ARM64, IL2CPP, OpenGLES3, Android API 26 oder neuer und `BuildOptions.None`.

Der Workflow `.github/workflows/unity-android.yml` führt statische Integritätsprüfung, alle EditMode-Tests und den APK-Build aus und lädt `riftbound-android-1.0.0` als Artefakt hoch.
