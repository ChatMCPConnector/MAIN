# Lokaler Koop – Release 1.0

## Unterstützte Verbindung

Riftbound verbindet genau zwei Android-Geräte ohne externen Server, Konto oder Cloud-Dienst. Offiziell unterstützt werden ein gemeinsames lokales WLAN und ein mobiler Hotspot.

- UDP-Sitzungserkennung: Port `47777`
- direkter Sitzungsport: `47778` bis `47787`
- Kampf-Snapshots: Port `47820`
- zuverlässige Ereignisse mit ACK/Retry: Port `47830`
- automatisch erzeugter vierstelliger Sitzungscode
- anonymes persistentes Gerätetoken
- 20 Sekunden reservierte Wiederverbindungsfrist
- Beitritt eines neuen Geräts nur in sicheren Räumen

Native Wi-Fi-Direct- und Bluetooth-Transporte gehören nicht zur Transportmatrix von Version 1.0. Auf Android wird stattdessen ein lokales WLAN oder der Hotspot eines der beiden Geräte verwendet.

## Hochfrequente Zustände

Zehnmal pro Sekunde werden kompakte, kulturunabhängige Zustände übertragen:

- Spielerposition, Lebenspunkte, Gefallenenstatus und Bereitschaft
- Run-Seed und aktueller Raum
- Gegnerposition, Rotation, Leben, Maximalleben und Bossphase
- feindliche Projektilposition, Schaden und Radius
- Dash- und Wiederbelebungs-Unverwundbarkeit

Pakete werden über Protokollversion, Sitzungscode, Gerätetoken, Endpunkt und Sequenznummer geprüft. Alte oder doppelte Snapshots werden verworfen.

## Host-Autorität

Der Host ist maßgeblich für:

- Gegnerbewegung und Zielwahl
- Gegnerleben und Tod
- Bossphasen und Angriffsmuster
- feindliche Projektile
- Laser- und Pulsgefahren
- Client-Schaden
- gemeinsame Karten-, Schatz- und Händlerentscheidungen
- gemeinsame Run-Währung
- Raumwechsel

Client-Nahkampf und Client-Fähigkeiten werden als Anforderung übertragen. Der Host prüft Position, Richtung, Reichweite, Wertebereich, Angriffstempo und Sequenz, bevor Gegnerleben verändert wird.

## Zielwahl und Gefahren

Gegner wählen normalerweise den näheren lebenden Spieler. Bei nahezu gleicher Entfernung verteilt die deterministische Gegner-ID die Aggro zwischen Host und Client.

Laser- und Pulsgefahren werden deterministisch aus Seed und Raum erzeugt. Der Host überträgt zuverlässige Phasenwechsel für Spawn, Warnung, Aktivierung und Deaktivierung. Client-Darstellungen besitzen keine eigene Schadensautorität.

## Zuverlässige Ereignisse

Kritische Ereignisse verwenden das Protokollpräfix `RB5R`:

- Schaden
- Wiederbelebung
- Raumwechsel
- Karten-, Schatz- und Händlerentscheidung
- Währungsstand

Jede Nachricht besitzt eine eindeutige ID. Sie wird in kurzen Abständen erneut gesendet, bis die Gegenseite ein ACK zurückgibt. Bereits verarbeitete IDs werden dedupliziert. Dadurch wird eine Nachricht bei Paketverlust nicht vergessen und bei Wiederholung nicht doppelt angewendet.

Der normale Sitzungs- beziehungsweise Kampfkanal bleibt für schnelle Rückmeldung erhalten. Der zuverlässige Kanal ist die bestätigte Absicherung.

## Gemeinsame Entscheidungen und Lootschutz

Der Host wählt Karten, Schätze und Händleraktionen. Der Client rekonstruiert dieselben Optionen deterministisch aus Seed und Raum und erhält nur den bestätigten Optionsindex.

Transaktionsschlüssel verhindern doppelte Anwendung. Die Host-Währung besitzt eine monotone Revision und wird nach jeder Entscheidung erneut als endgültiger Stand angewendet. Dadurch bleiben Gold und Belohnungen auch bei vertauschter Paketreihenfolge konsistent.

Beide Spieler erhalten in Version 1.0 dieselbe gemeinsame Karten- und Gegenstandsentscheidung. Persönlich getrennte Lootinstanzen sind bewusst nicht Teil des Spielmodells.

## Raumwechsel, Tod und Wiederbelebung

- Beide Spieler markieren ihre Bereitschaft.
- Der Host autorisiert den nächsten Raum.
- Der schnelle `ADVANCE`-Befehl wird durch einen zuverlässigen Zielraum abgesichert.
- Wiederbelebung wird schnell gesendet und zusätzlich per ACK/Retry bestätigt.
- Ein gefallener Spieler kehrt mit 35 Prozent Leben zurück.
- Fallen beide Spieler, endet der Run.
- Nach dauerhaftem Verbindungsabbruch kann der verbleibende Spieler solo fortsetzen.

## Run-Wiederherstellung

Ein atomarer Checkpoint mit Backup wird regelmäßig sowie bei Pause, Fokusverlust und App-Ende gespeichert. Enthalten sind:

- Seed und Raum
- Gold und Lebenspunkte
- Inventar, Lootfilter und Ausrüstung
- gewählte Karten und abgeleiteter Build
- lebende Gegner mit Position, Leben und Bossphase
- Status, ob der Kampf oder bereits die Belohnungsphase aktiv war

Checkpoints sind höchstens 24 Stunden gültig. Beschädigte, veraltete oder unplausible Daten werden verworfen. Bewegte Projektile werden nicht restauriert, damit nach dem Start kein unsichtbarer Soforttreffer entsteht; Gegner und Gefahren starten dagegen konsistent aus dem gespeicherten Raumzustand.

## Grenzen der Veröffentlichung

Version 1.0 ist auf lokales WLAN und Hotspot ausgelegt. Eine praktische Freigabe sollte zusätzlich auf zwei echten Android-Geräten mit unterschiedlichen Herstellern, Paketverlust, App-Hintergrund, Hotspotwechsel und längeren Läufen geprüft werden. Diese Hardwareprüfung kann nicht durch EditMode-Tests ersetzt werden.
