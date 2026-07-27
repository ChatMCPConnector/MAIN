# Riftbound

Riftbound ist ein vollständig per Touch bedienbarer Unity-6.3-Prototyp für Android im Hochformat.

## Aktueller spielbarer Umfang

- deterministische Acht-Raum-Runs mit reproduzierbarem Seed
- drei Kampfräume, Schatzkammer, Händler, Heilraum, Elite und Boss
- drei Biome: Versunkene Ruinen, Aschenöde und Kristalltiefen
- deterministische Raum-Anomalien und skalierende Begegnungswerte
- Boss mit drei Lebensphasen und wechselnden Projektilmustern
- Nahkampf, Projektilfähigkeit und unverwundbarer Dash
- zehn Karten, fünf Waffen, fünf Rüstungen und sechs Seltenheitsstufen
- Touch-Inventar mit zehn Plätzen, Lootfilter, Ausrüsten und Zerlegen
- persistente Entdeckungen, höchste Seltenheit und Risssplitter
- lokaler Zwei-Spieler-Koop über gemeinsames WLAN oder mobilen Hotspot
- automatische Sitzungserkennung, Sitzungscode und Wiederverbindung
- synchronisierte Spielerpositionen, Lebenspunkte, Seed, Raum und Bereitschaft
- host-autoritative Gegnerpositionen, Gegnerleben und Bossphasen
- replizierte gegnerische Projektile mit eindeutigen Netzwerk-IDs
- Gegner wählen auf dem Host den näheren lebenden Spieler als Ziel
- Client-Angriffe und Schaden am Client werden vom Host bestätigt
- gemeinsamer Raumwechsel, Wiederbelebung und Solo-Fortsetzung nach Abbruch
- nichtlineare Koop-Skalierung mit mehr Gegnern und erweiterten Bossmustern
- Safe Area, 9:16-Touch-HUD und Editor-Tastatursteuerung
- EditMode-Tests für Runs, Biome, Loot, Inventar, Meta-Fortschritt und Koop-Protokolle

## Steuerung

Touch: virtueller Stick, Inventar, Koop-Menü, Angriff, Dash und Fähigkeit.

Editor: WASD/Pfeiltasten, Leertaste, linke Umschalttaste, E und I für das Inventar.

Das Inventar lässt sich nur außerhalb aktiver Kämpfe öffnen. Nach Karten-, Schatz- und Händlerauswahl wird es automatisch angeboten.

## Lokaler Koop

Beide Geräte müssen im selben lokalen WLAN oder mobilen Hotspot sein. Ein Spieler startet den Host in einem sicheren Raum. Das zweite Gerät findet die Sitzung automatisch und tritt bei.

Phase 5C synchronisiert Run-, Spieler-, Gegner- und feindliche Projektilzustände. Technische Details und die verbleibenden Grenzen stehen in `docs/COOP.md`.

## Android-Build

Die Android-Version ist `0.7.0`. Der Workflow `.github/workflows/unity-android.yml` führt statische Prüfung, EditMode-Tests und den APK-Build aus.
