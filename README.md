# Riftbound

Riftbound ist ein vollständig per Touch bedienbarer Unity-6.3-Prototyp für Android im Hochformat.

## Aktueller spielbarer Umfang

- deterministische Acht-Raum-Runs mit reproduzierbarem Seed
- drei Kampfräume, Schatzkammer, Händler, Heilraum, Elite und Boss
- drei Biome pro Run: Versunkene Ruinen, Aschenöde und Kristalltiefen
- deterministische Raum-Anomalien: Rasende Jagd, Verstärkte Hüllen, Instabile Geschosse, Blutmond und Risssturm
- skalierende Gegnerwerte je Raum, Biom und Anomalie
- Boss mit drei Lebensphasen, höherem Tempo und wechselnden Projektilmustern
- Nahkampf, Projektilfähigkeit und unverwundbarer Dash
- normale Nah- und Fernkämpfer sowie Elitegegner
- zehn Karten mit deutlich sichtbaren Vor- und Nachteilen
- fünf Waffen und fünf Rüstungsteile mit zufälligen Seltenheiten und Stärke-Rolls
- Seltenheiten: gewöhnlich, ungewöhnlich, selten, episch, legendär und verflucht
- Touch-Inventar mit zehn Plätzen, Ausrüsten, Vergleichen und Zerlegen
- einstellbarer Aufhebefilter; gefilterter oder überzähliger Loot wird automatisch verwertet
- Gold, Händlerpreise, Schatzwahl und farbcodierte Gegenstandsanzeige
- persistente Entdeckungen, höchste gefundene Seltenheit und Risssplitter
- lokaler, versionierter Spielstand mit Backup und Migration auf Version 3
- Safe Area, 9:16-Touch-HUD und Editor-Tastatursteuerung
- EditMode-Tests für Runs, Biome, Anomalien, Händler, Seltenheiten, Inventar und Meta-Fortschritt

## Steuerung

Touch: virtueller Stick, Inventar, Angriff, Dash und Fähigkeit.

Editor: WASD/Pfeiltasten, Leertaste, linke Umschalttaste, E und I für das Inventar.

Das Inventar lässt sich nur außerhalb aktiver Kämpfe öffnen. Nach Karten-, Schatz- und Händlerauswahl wird es automatisch angeboten.

## Android-Build

Die Android-Version ist `0.4.0`. Der Workflow `.github/workflows/unity-android.yml` führt statische Prüfung, EditMode-Tests und den APK-Build aus.
