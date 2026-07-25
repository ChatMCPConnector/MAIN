# Technische Entscheidungen

Stand: 25. Juli 2026

## Engine und Sprache

Verwendet wird Godot 4.7.1-stable mit GDScript. Die Version ist laut offiziellem Godot-Archiv seit dem 14. Juli 2026 stabil. GDScript vermeidet die weiterhin zusätzlichen Android-Einschränkungen der C#-Toolchain.

Quellen:
- https://godotengine.org/download/archive/4.7.1-stable/
- https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_android.html

## Renderer und Grafik

Der GL-Compatibility-Renderer wird verwendet, weil das Spiel bewusst einfache Low-Poly-Geometrie, wenige Materialien, ein Richtungslicht ohne Echtzeitschatten und kleine prozedurale Effekte nutzt. Das reduziert GPU-Last und erweitert die Geräteabdeckung. Sämtliche Laufzeitgrafik entsteht aus Engine-Primitiven; es gibt keine externen Modelle oder Texturen.

## Android

- JDK 17 gemäß stabiler Godot-Dokumentation.
- Release-Architektur ARM64; x86_64 zusätzlich für den CI-Emulator.
- Primäre Ausrichtung Querformat, Edge-to-edge und immersive Darstellung.
- Keine Internet- oder sonstigen sensiblen Berechtigungen.
- Die Export-Pipeline verwendet die offiziellen 4.7.1-Export-Templates. Das aktuelle Play-Ziel ist bis 30. August 2026 API 35; ab 31. August 2026 verlangt Google Play API 36 für neue Apps und Updates. Vor einer Play-Veröffentlichung nach diesem Datum ist deshalb ein Gradle-Custom-Build mit explizitem Target 36 vorgesehen.
- Native Android-Bibliotheken müssen die seit 1. November 2025 geltende 16-KB-Seitengrößenanforderung erfüllen; offizielle aktuelle Godot-Templates werden verwendet und die APK wird im CI geprüft.

Quellen:
- https://developer.android.com/google/play/requirements/target-sdk
- https://developer.android.com/guide/practices/page-sizes

## Mindestversion

Die erste Version setzt praktisch Android 8.0/API 26 oder neuer voraus. Dies reduziert Altgeräte-Sonderfälle, unterstützt weiterhin eine breite installierte Basis und passt zu modernen 64-Bit-Geräten. Vor einer Store-Veröffentlichung wird die tatsächlich im exportierten Manifest ausgewiesene Mindest- und Zielversion mit `aapt dump badging` protokolliert.

## Architektur

`RunnerGameModel` hält frameunabhängige Kernlogik und Zustände. `RunnerPlayerController` behandelt Figur, Spurinterpolation, Sprung, Rutschen und Animation. `RunnerTrackManager` verwaltet gepoolte Segmente, Hindernisse und Sammelobjekte. `RunnerSaveManager` kapselt lokale Konfiguration. `RunnerAudioManager` erzeugt und steuert Musik und Effekte. `main.gd` verbindet Welt, UI und Lebenszyklus.

## Performance

- Keine unbegrenzte Objekterzeugung während einer Runde
- Sieben wiederverwendete Streckensegmente
- Feste Pools für 18 Hindernisse und 24 Sammelobjekte
- Einfache Kollisionslogik und primitive Meshes
- Keine Echtzeitschatten, keine großen Texturen und keine Netzwerkarbeit
- Frameunabhängige Geschwindigkeit und Bewegung

## Tests

Headless-Tests prüfen Spurgrenzen, Tempo, Maximalgeschwindigkeit, Punkte, Highscore-Grundwerte, Pattern-Sicherheit, Zustände, Pause und Neustart. Der Android-Smoke-Test installiert die APK auf einem API-35-x86_64-Emulator, startet die App, führt Tutorial-/Spielgesten aus, prüft Prozess und Logcat und speichert mehrere Screenshots. Sauce Labs erhält nur die fertige Release-APK; Gerätetests werden manuell gestartet.
