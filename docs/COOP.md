# Lokaler Koop – Phase 5B

## Ziel

Die aktuelle Koop-Grundlage verbindet zwei Android-Geräte ohne externen Server, Internetkonto oder Cloud-Dienst. Unterstützt werden ein gemeinsames lokales WLAN und ein mobiler Hotspot.

## Verbindung

- UDP-Sitzungserkennung über Port `47777`
- direkter Host-Port aus dem Bereich `47778` bis `47787`
- separater Kampfkanal über Port `47820`
- automatisch erzeugter vierstelliger Sitzungscode
- ein Host und höchstens ein Client
- Beitritt nur in sicheren Räumen
- persistentes anonymes Gerätetoken für kurze Wiederverbindungen
- Reservierung des getrennten Platzes für 20 Sekunden

## Synchronisierte Spieler- und Run-Zustände

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

## Host-autoritative Gegnerzustände

Der Host ist für Gegnerpositionen, Gegnerleben und Bossphasen maßgeblich.

- Jeder Spawn erhält aus Raum, Gegnertyp und Position eine deterministische Netzwerk-ID.
- Der Host sendet zehnmal pro Sekunde einen vollständigen Snapshot aller lebenden Gegner.
- Ein Snapshot enthält ID, Typ, Position, Rotation, Leben, maximales Leben und Bossphase.
- Client-Gegner führen keine eigene KI aus und bewegen sich geglättet zu den Hostpositionen.
- Fehlt eine Gegner-ID im nächsten Snapshot, wird das Client-Replikat entfernt.
- Ein leerer Host-Snapshot bestätigt den Abschluss des Kampfraums.
- Bossphasen und ihre visuelle Kennzeichnung werden aus dem Hostzustand übernommen.

## Bestätigte Client-Angriffe

Client-Nahkampf und Client-Fähigkeiten verändern Gegnerleben nicht direkt.

- Der Client sendet eine sequenzierte Angriffsanforderung an den Kampfkanal.
- Der Host prüft Gerätetoken, Endpunkt, Sequenz, Position, Richtung, Wertebereich und Mindestabstand zwischen Angriffen.
- Nahkampftreffer werden erst auf den Host-Gegnern berechnet.
- Fähigkeiten erzeugen erst nach Hostbestätigung ein schadensfähiges Projektil in der Hostwelt.
- Veraltete oder doppelte Angriffspakete werden verworfen.

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

- Sitzungs- und Kampfprotokoll besitzen getrennte Präfixe und Versionen.
- Pakete werden nur vom bestätigten Endpunkt und Gerätetoken angenommen.
- Veraltete Zustände und Angriffe werden über Sequenznummern verworfen.
- Zahlen werden invariant serialisiert und sind unabhängig von der Gerätesprache.
- Sitzungscodes, Tokens und Befehle werden vor dem Senden bereinigt.
- Gegnerpakete sind auf 64 Einträge und die Paketverarbeitung pro Frame ist begrenzt.
- Angriffswerte und Abstände werden auf dem Host begrenzt und plausibilisiert.

## Noch nicht vollständig umgesetzt

Phase 5B synchronisiert Gegnerzustände und Client-Angriffe. Noch offen sind:

- host-ausgewählte Zielpriorität zwischen beiden Spielern
- Replikation gegnerischer Projektile und Gefahrenflächen zum Client
- Hostbestätigung von Schaden, Ausweichen und Unverwundbarkeit des Clients
- vollständig synchronisierte Bossangriffs-Zeitpunkte und Projektilbahnen
- getrennte persönliche Lootzustände und doppelsichere Belohnungsvergabe
- gemeinsame oder getrennte Karten-, Schatz- und Händlerentscheidungen
- Wiederherstellung des vollständigen Kampfzustands nach längerer App-Pause
- native Android-Transporte für Wi-Fi Direct, Bluetooth und Bluetooth Low Energy
- Tests auf zwei echten Android-Geräten inklusive Paketverlust, Hintergrundmodus und Hotspotwechsel

Diese Punkte bauen auf dem bestehenden Sitzungsprotokoll, dem Kampfkanal und den deterministischen Gegner-IDs auf.
