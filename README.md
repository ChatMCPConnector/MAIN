# Pokémon Pixelkampf

Eine native, vollständig offline funktionierende Android-App für einfache rundenbasierte 1-gegen-1-Pokémon-Kämpfe im Retro-Pixelstil.

## Technologien

- Kotlin
- Jetpack Compose
- ViewModel und StateFlow
- Android Gradle Plugin 8.13.2
- Gradle 8.13
- Compose BOM 2026.06.00
- Minimum SDK 23, Target/Compile SDK 36

## Spielprinzip

Beim Start eines neuen Kampfes werden zwei unterschiedliche Pokémon zufällig ausgewählt. Der Spieler wählt eine von vier Attacken, während eine gewichtete Gegner-KI ihre Attacke bestimmt. Die Initiative legt die Reihenfolge fest. Trefferwahrscheinlichkeit, Angriff, Verteidigung, Attackenstärke, Typeneffektivität und ein kleiner Zufallsfaktor bestimmen den Schaden.

Enthalten sind genau:

- Pikachu – Elektro
- Glumanda – Feuer
- Schiggy – Wasser
- Bisasam – Pflanze
- Kleinstein – Gestein/Boden
- Taubsi – Normal/Flug

Die Werte sind für ein vereinfachtes und möglichst ausgeglichenes System angepasst. Details und Quellen stehen in [`docs/pokemon-research.md`](docs/pokemon-research.md).

## Funktionen

- Startbildschirm und zufälliger Kampf
- vier Attacken pro Pokémon
- vereinfachtes Typensystem
- trefferbasierte Schadensberechnung
- gewichtete Gegner-KI
- animierte KP-Balken und kurzes Trefferfeedback
- Eingabesperre während einer Runde
- sofortiges Kampfende bei null KP
- Ergebnisdialog und vollständig zurückgesetzter neuer Kampf
- selbst erstellte lokale Pixelgrafiken
- keine Laufzeit-API, keine Server, kein Tracking, keine Werbung

## Lokal bauen

Voraussetzungen: JDK 17 und Android SDK 36.

```bash
chmod +x ./gradlew
./gradlew testReleaseUnitTest assembleRelease
```

Der normale lokale Release-Build ist zunächst unsigniert. Die signierte Test-APK wird sicher im GitHub-Actions-Workflow erzeugt.

## Unit-Tests

```bash
./gradlew testReleaseUnitTest
```

Die Tests prüfen unter anderem:

- exakt sechs Pokémon und vier Attacken je Pokémon
- stets unterschiedliche Zufallspaarungen
- vollständige KP beim Neustart
- Einfluss von Angriff, Verteidigung und Attackenstärke
- alle drei Effektivitätsstufen
- Fehlschläge ohne Schaden
- niemals negative KP
- kein zweiter Angriff nach einem K.-o.
- sofortiges Kampfende
- vollständiger Zustandsreset
- KI-Präferenz für sehr effektive Attacken
- Schutz vor doppelten Runden durch schnelle Eingaben

Es wird bewusst **keine Instrumentierungstest-APK** erstellt.

## Release und Sauce Labs

Der Workflow `.github/workflows/android-release.yml`:

1. führt lokale Unit-Tests und Lint aus,
2. baut die Release-APK,
3. erstellt einen nur für diesen Lauf gültigen temporären Keystore,
4. richtet und signiert die APK,
5. prüft die Signatur,
6. benennt die einzige veröffentlichte Datei in `PokemonBattle.apk` um,
7. lädt ausschließlich diese Datei als GitHub-Artefakt hoch,
8. lädt ausschließlich diese Datei in die Sauce-Labs-Region `eu-central-1` hoch.

Die Zugangsdaten werden ausschließlich aus den GitHub Actions Secrets `SAUCE_USERNAME` und `SAUCE_ACCESS_KEY` gelesen. Es werden **keine automatischen Sauce-Labs-Gerätetests** gestartet. App- und Gerätetests werden danach manuell in Sauce Labs ausgeführt.
