# Riftbound

Riftbound ist ein vollständig per Touch bedienbarer Unity-6.3-Prototyp für Android im Hochformat.

## Aktueller spielbarer Umfang

- deterministische Acht-Raum-Runs mit reproduzierbarem Seed
- drei Kampfräume, Schatzkammer, Händler, Heilraum, Elite und Boss
- Nahkampf, Projektilfähigkeit und unverwundbarer Dash
- normale Nah- und Fernkämpfer, Elitegegner und Boss mit angekündigtem Flächenangriff
- zehn Karten mit Vor- und Nachteilen
- fünf Waffen und fünf Rüstungsteile
- Gold, Händlerpreise, Schatzwahl und Ausrüstungsanzeige
- lokaler, versionierter Spielstand mit Backup
- Safe Area, 9:16-Touch-HUD und Editor-Tastatursteuerung
- EditMode-Tests für 10.000 Seeds und deterministische Händlerangebote

## Steuerung

Touch: virtueller Stick, Angriff, Dash und Fähigkeit.

Editor: WASD/Pfeiltasten, Leertaste, linke Umschalttaste und E.

## Android-Build

Der Workflow `.github/workflows/unity-android.yml` führt EditMode-Tests aus und erstellt `Riftbound.apk`.
