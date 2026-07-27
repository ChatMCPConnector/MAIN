# Riftbound 1.0 – Releasehinweise

## Buildprofil

- Unity `6000.3.20f1`
- Android APK
- Version `1.0.0`
- Versionscode `100`
- Mindestversion Android API 26
- ARM64
- IL2CPP
- OpenGLES3
- Hochformat
- Release-Build ohne `BuildOptions.Development`

## Automatische Prüfung

Der Workflow `.github/workflows/unity-android.yml` führt nacheinander aus:

1. Projekt-, Paket-, XML- und Quellstruktur prüfen.
2. Veraltete oder unaufgelöste Aufrufe ausschließen.
3. Protokollversionen, Ports, Grenzwerte und Releaseversion prüfen.
4. Alle EditMode-Tests ausführen.
5. Android-APK mit `Riftbound.Editor.BuildAutomation.BuildAndroid` bauen.
6. APK und Testdiagnosen als Artefakt `riftbound-android-1.0.0` hochladen.

Der Android-Build benötigt gültige Unity-Lizenz-Secrets im Repository.

## Manuelle Gerätefreigabe

Vor einer öffentlichen Weitergabe sollten mindestens folgende Fälle auf zwei physischen Android-Geräten geprüft werden:

- Solo-Run bis zum Boss und neuer Run
- App während eines Kampfes schließen und Checkpoint wiederherstellen
- Host über WLAN, Client über dasselbe WLAN
- Host über mobilen Hotspot, Client als Hotspot-Teilnehmer
- Wiederverbindung innerhalb und außerhalb der 20-Sekunden-Frist
- Paketverlust beziehungsweise kurzfristiger WLAN-Wechsel
- Karten-, Schatz- und Händlerentscheidung im Koop
- voller beziehungsweise gefilterter Client-Inventarzustand
- Wiederbelebung, beide Spieler gefallen und Solo-Fortsetzung
- Laser-, Puls-, Boss- und Projektiltreffer auf beiden Geräten
- Hintergrundmodus und Rückkehr in die App
- Optionen für große Schrift, hohen Kontrast, reduzierte Bewegung und Vibration
- längerer Lauf auf einem Gerät mit wenig Arbeitsspeicher

## Bekannte Plattformgrenze

Version 1.0 verwendet lokales WLAN oder einen mobilen Hotspot. Native Wi-Fi-Direct- und Bluetooth-Transporte sind keine unterstützten Release-Transportwege. Das Spiel verwendet keine externen Server und funktioniert im unterstützten lokalen Netzwerk ohne Internetzugriff.

## Verifizierungsstatus

Quellstand, statische Workflow-Prüfung und EditMode-Testabdeckung sind im Repository definiert. Ein erfolgreicher Unity-Compile, ein erfolgreiches APK-Artefakt und der physische Zwei-Geräte-Test gelten erst dann als bestätigt, wenn der entsprechende GitHub-Actions-Lauf beziehungsweise der manuelle Gerätebericht vorliegt.
