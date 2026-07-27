# Lokaler Koop – Phase 5A

## Ziel

Die aktuelle Koop-Grundlage verbindet zwei Android-Geräte ohne externen Server, Internetkonto oder Cloud-Dienst. Unterstützt werden ein gemeinsames lokales WLAN und ein mobiler Hotspot.

## Verbindung

- UDP-Sitzungserkennung über Port `47777`
- direkter Host-Port aus dem Bereich `47778` bis `47787`
- automatisch erzeugter vierstelliger Sitzungscode
- ein Host und höchstens ein Client
- Beitritt nur in sicheren Räumen
- persistentes anonymes Gerätetoken für kurze Wiederverbindungen
- Reservierung des getrennten Platzes für 20 Sekunden

## Synchronisierte Zustände

Zehnmal pro Sekunde werden kompakte, kulturunabhängige Statuspakete übertragen:

- laufende Sequenznummer
- Gerätetoken
- Run-Seed
- aktueller Raum
- Spielerposition
- aktuelle und maximale Lebenspunkte
- Gefallenenstatus
- Bereitschaft für den Raumwechsel

Der Host bestätigt beim Beitritt Seed und Raum. Der Client verwirft bei einem anderen Seed seinen lokalen Run-Zustand und beginnt mit frischem Startinventar und Startgold.

## Autorität und Regeln

- Der Host autorisiert gemeinsame Raumwechsel.
- Beide Spieler müssen bereit sein.
- Der Host sendet den bestätigten `ADVANCE`-Befehl.
- Seed- und Raum-Snapshots korrigieren einen verlorenen Raumwechselbefehl.
- Ein gefallener Spieler kann vom aktiven Partner wiederbelebt werden.
- Sind beide Spieler gefallen, endet der Run.
- Nach einem Verbindungsabbruch kann der verbleibende Spieler solo fortsetzen.
- Der getrennte Client versucht innerhalb der Wiederverbindungsfrist automatisch zurückzukehren.

## Koop-Skalierung

Die Schwierigkeit wird nicht nur über Lebenspunkte erhöht:

- zusätzliche normale Gegner
- zusätzliche Gegner in Elite-Begegnungen
- moderate Lebens- und Schadensmultiplikatoren
- mehr Bossgeschosse
- breitere gezielte Bossangriffe
- vier Händlerangebote statt drei

## Sicherheits- und Robustheitsregeln

- Protokollpräfix und Protokollversion werden geprüft.
- Pakete werden nur vom bestätigten Endpunkt und Gerätetoken angenommen.
- Veraltete Zustände werden über Sequenznummern verworfen.
- Zahlen werden invariant serialisiert und sind unabhängig von der Gerätesprache.
- Sitzungsnamen und Befehle werden vor dem Senden bereinigt.
- Die Paketverarbeitung ist pro Frame begrenzt.

## Noch nicht vollständig umgesetzt

Phase 5A ist die Transport- und Sitzungsgrundlage. Noch offen sind:

- vollständig host-autoritative Gegnerpositionen und Gegnerlebenspunkte
- Projektil- und Trefferreplikation
- synchronisierte Bossphasen als bestätigte Hostzustände
- getrennte persönliche Lootzustände und doppelsichere Belohnungsvergabe
- Karten- und Händlerentscheidungen beider Spieler
- native Android-Transporte für Wi-Fi Direct, Bluetooth und Bluetooth Low Energy
- Tests auf zwei echten Android-Geräten inklusive Unterbrechung, Hintergrundmodus und Hotspotwechsel

Diese Punkte bauen auf dem bestehenden Protokoll und der getrennten Transportschicht auf.