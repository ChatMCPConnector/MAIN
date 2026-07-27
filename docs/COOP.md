# Lokaler Koop – Phase 5C

## Ziel

Die aktuelle Koop-Implementierung verbindet zwei Android-Geräte ohne externen Server, Internetkonto oder Cloud-Dienst. Unterstützt werden ein gemeinsames lokales WLAN und ein mobiler Hotspot.

## Verbindung

- UDP-Sitzungserkennung über Port `47777`
- direkter Host-Port aus dem Bereich `47778` bis `47787`
- separater Kampfkanal über Port `47820`
- automatisch erzeugter vierstelliger Sitzungscode
- ein Host und höchstens ein Client
- Beitritt nur in sicheren Räumen
- anonymes Gerätetoken und 20 Sekunden Wiederverbindungsfrist

## Spieler- und Run-Zustände

Zehnmal pro Sekunde werden kompakte, kulturunabhängige Zustände übertragen:

- Sequenznummer und Gerätetoken
- Run-Seed und aktueller Raum
- Spielerposition
- aktuelle und maximale Lebenspunkte
- Gefallenenstatus
- Bereitschaft für Raumwechsel

Der Host bestätigt Seed und Raum. Bei einem anderen Seed verwirft der Client seinen lokalen Run-Zustand und startet mit frischem Startinventar und Startgold.

## Gegnerautorität

Der Host ist für Gegnerpositionen, Gegnerleben, Zielwahl und Bossphasen maßgeblich.

- Jeder Spawn erhält aus Raum, Typ und Position eine deterministische Netzwerk-ID.
- Der Host sendet zehnmal pro Sekunde einen vollständigen Snapshot aller lebenden Gegner.
- Client-Gegner führen keine eigene KI aus.
- Position und Rotation werden auf dem Client geglättet.
- Fehlende IDs entfernen das entsprechende Client-Replikat.
- Ein leerer Gegner-Snapshot bestätigt das Ende des Kampfraums.
- Bossphasen und ihre visuelle Kennzeichnung stammen aus dem Hostzustand.

## Zielwahl

Gegner berücksichtigen auf dem Host beide lebenden Spieler.

- Normalerweise wird der räumlich nähere Spieler angegriffen.
- Ist nur ein Spieler aktiv, wird dieser ausgewählt.
- Bei nahezu gleicher Entfernung verteilt die Gegner-ID die Aggro deterministisch.
- Nahkampfangriffe gegen den Client lösen ein bestätigtes Schadensereignis aus.
- Fernkämpfer und gezielte Boss-Fächer richten sich auf den ausgewählten Spieler aus.

## Feindliche Projektile

Feindliche Projektile sind host-autoritativ.

- Jedes Projektil erhält eine laufende Netzwerk-ID.
- Der Host überträgt Position, Schaden und Radius mit zehn Snapshots pro Sekunde.
- Der Client zeigt geglättete, kollisionslose Replikate.
- Verschwindet eine Projektil-ID auf dem Host, wird das Client-Replikat entfernt.
- Projektilkollisionen mit dem Client werden auf dem Host über die bestätigte Clientposition erkannt.
- Ein angenommenes Projektilereignis wird als Schaden an den Client gesendet.

## Client-Angriffe und Verteidigung

- Client-Nahkampf und Client-Fähigkeiten verändern Gegnerleben nicht direkt.
- Der Host prüft Endpunkt, Gerätetoken, Sequenz, Position, Richtung, Werte und Angriffstempo.
- Der Client meldet Dash- und Wiederbelebungs-Unverwundbarkeit zehnmal pro Sekunde.
- Der Host verwirft Treffer, solange der zuletzt bestätigte Verteidigungsstatus unverwundbar ist.
- Akzeptierter Schaden wird als sequenziertes Ereignis an den Client gesendet.
- Rüstung, Schadensreduktion und verfluchte Multiplikatoren werden anschließend beim betroffenen Spieler angewendet.

## Raumwechsel und Wiederbelebung

- Der Host autorisiert Raumwechsel.
- Beide Spieler müssen bereit sein.
- Der Host sendet den bestätigten `ADVANCE`-Befehl.
- Seed- und Raum-Snapshots korrigieren verlorene Wechselbefehle.
- Ein aktiver Spieler kann den gefallenen Partner wiederbeleben.
- Sind beide Spieler gefallen, endet der Run.
- Nach einem Abbruch kann der verbleibende Spieler solo fortsetzen.

## Sicherheits- und Robustheitsregeln

- Sitzungs-, Kampf- und Autoritätsprotokoll besitzen getrennte Präfixe und Versionen.
- Pakete werden nur vom bestätigten Endpunkt und Gerätetoken angenommen.
- Veraltete Zustände, Angriffe, Verteidigungen und Schadensereignisse werden verworfen.
- Zahlen werden invariant serialisiert und sind unabhängig von der Gerätesprache.
- Gegnerpakete sind auf 64, Projektilpakete auf 128 Einträge begrenzt.
- Paketverarbeitung pro Frame und Schadenswerte sind begrenzt.
- Doppelte Projektil-IDs werden abgelehnt.

## Noch nicht vollständig umgesetzt

Phase 5C synchronisiert Spieler, Gegner, feindliche Projektile, Zielwahl und bestätigten Schaden. Noch offen sind:

- genaue Zeitkompensation für Paketlaufzeit und sehr schnelle Dash-Fenster
- Replikation dauerhafter Fallen, Laser und anderer Gefahrenflächen
- gemeinsame oder getrennte Karten-, Schatz- und Händlerentscheidungen
- persönliche Lootzustände und doppelsichere Belohnungsvergabe
- vollständige Wiederherstellung eines laufenden Kampfes nach längerer App-Pause
- native Android-Transporte für Wi-Fi Direct, Bluetooth und Bluetooth Low Energy
- Tests auf zwei echten Android-Geräten mit Paketverlust, Hintergrundmodus und Hotspotwechsel
- Performance-, Qualitäts-, Barrierefreiheits- und Release-Politur aus Phase 6

Diese Punkte bauen auf dem Sitzungsprotokoll, dem Kampfkanal und dem neuen Autoritätsprotokoll auf.
