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
- lokaler Zwei-Spieler-Koop als LAN-/Hotspot-Grundlage ohne externen Server oder Benutzerkonto
- automatische Sitzungserkennung, vierstelliger Sitzungscode, Host-Client-Verbindung und Wiederverbindung
- synchronisierte Spielerposition, Lebenspunkte, Seed, Raum, Bereitschaft und Gefallenenstatus
- gemeinsamer Raumwechsel, Wiederbelebung und Solo-Fortsetzung nach Verbindungsabbruch
- nichtlineare Koop-Skalierung mit mehr Gegnern, moderat höheren Werten und erweiterten Bossmustern
- Safe Area, 9:16-Touch-HUD und Editor-Tastatursteuerung
- EditMode-Tests für Runs, Biome, Anomalien, Händler, Seltenheiten, Inventar, Meta-Fortschritt und Koop-Protokoll

## Steuerung

Touch: virtueller Stick, Inventar, Koop-Menü, Angriff, Dash und Fähigkeit.

Editor: WASD/Pfeiltasten, Leertaste, linke Umschalttaste, E und I für das Inventar.

Das Inventar lässt sich nur außerhalb aktiver Kämpfe öffnen. Nach Karten-, Schatz- und Händlerauswahl wird es automatisch angeboten.

## Lokaler Koop

Beide Geräte müssen im selben lokalen WLAN oder mobilen Hotspot sein. Ein Spieler startet den Host in einem sicheren Raum. Das zweite Gerät findet die Sitzung automatisch und tritt über den angezeigten Code bei.

Die Phase-5A-Grundlage synchronisiert Spieler- und Run-Zustände. Vollständige host-autoritative Gegner-, Projektil-, Karten- und Loot-Replikation sowie native Wi-Fi-Direct- oder Bluetooth-Transporte sind noch nicht abgeschlossen. Technische Details stehen in `docs/COOP.md`.

## Android-Build

Die Android-Version ist `0.5.0`. Der Workflow `.github/workflows/unity-android.yml` führt statische Prüfung, EditMode-Tests und den APK-Build aus.