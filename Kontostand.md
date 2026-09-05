# Kontostand und Verbrauch anzeigen

## Ziel

Es soll eine minimale, ressourcenschonende Anzeige mit genau zwei Werten entstehen:

```text
Kontostand: 4384,43
Verbrauch:    12,64
```

Chromium soll nicht dauerhaft im Hintergrund laufen. Die bevorzugte Loesung ist deshalb ein direkter, offizieller API-Abruf mit dem System Access Token. Nur wenn das technisch nicht moeglich ist, wird Chromium kurzzeitig als Fallback gestartet.

## Bekannter Stand

Die Kontoseite zeigt aktuell:

- Kontostand: `4384.43`
- Verbrauch: `12.64`
- Benutzer-ID: `5307`

Die angemeldete Browsersitzung kann `/api/user/self` erfolgreich aufrufen. Dabei werden unter anderem die Rohwerte `quota` und `used_quota` geliefert.

Direkte Anfragen aus dem Codespace wurden bisher von Cloudflare mit HTTP 403 abgefangen. Die Anfrage erreichte dadurch nicht die eigentliche API. Der Berechtigungsumfang des System Access Tokens ausserhalb der Browsersitzung ist deshalb noch nicht abschliessend bestaetigt.

## Zielarchitektur

Die bevorzugte Architektur lautet:

```text
System Access Token
        |
        v
Offizielle API
        |
        v
Lokaler Collector
        |
        v
Lokaler Cache
        |
        v
Anzeige mit zwei Werten
```

Chromium wird in dieser Variante nicht benoetigt.

## Phase 1: Erfolgreiche Browseranfrage analysieren

Die echte Anfrage der Kontoseite wird einmalig mit den Browser-Entwicklerwerkzeugen oder der Chromium-Debugschnittstelle untersucht.

### Vorgehen mit F12

1. Chromium oeffnen und bei der Plattform anmelden.
2. F12 oeffnen.
3. Zum Bereich **Network** wechseln.
4. Den Filter **Fetch/XHR** aktivieren.
5. Die persoenliche Kontoseite neu laden.
6. Die Anfrage identifizieren, welche Kontostand und Verbrauch liefert.
7. Request-URL, Methode, Headernamen und Antwortstruktur dokumentieren.

Erfasst werden nur:

- vollstaendige Request-URL
- API-Host
- HTTP-Methode
- Namen der Authentifizierungsheader
- Namen relevanter Cookies
- JSON-Struktur der Antwort
- Initiator der Anfrage

Token-, Cookie- und Sessionwerte duerfen nicht in Logs oder Dateien geschrieben werden.

### Zu klaerende Frage

Es muss festgestellt werden, ob die Webseite ihre API ueber `new.xinjianya.top` oder ueber einen separaten API-Host anspricht. Ein separater Host koennte andere Cloudflare-Regeln besitzen und direkte Token-Anfragen erlauben.

## Phase 2: Umrechnungslogik verifizieren

Die API liefert Rohwerte wie `quota` und `used_quota`, waehrend die Oberflaeche formatierte Werte anzeigt.

Die Umrechnung darf nicht geraten werden. Die korrekte Berechnung wird aus einer der folgenden Quellen bestimmt:

1. Formatierungsfunktion im geladenen Frontend-JavaScript
2. Netzwerkantwort mit bereits formatierten Werten
3. Kombination aus API-Rohwerten und aktuellen Systemeinstellungen

Das Ergebnis soll eine eindeutige Berechnung liefern:

```text
balance = convert(quota, system_settings)
consumption = convert(used_quota, system_settings)
```

Die berechneten Werte muessen mit der sichtbaren Anzeige uebereinstimmen.

## Phase 3: System Access Token testen

Nachdem die echte Browseranfrage bekannt ist, wird exakt diese Anfrage ohne Browser-Cookies reproduziert.

Moegliche Authentifizierungsvarianten sind beispielsweise:

```http
Authorization: Bearer <system-access-token>
New-Api-User: 5307
```

oder:

```http
Authorization: <system-access-token>
New-Api-User: 5307
```

Es wird nicht weiter mit beliebigen Headerkombinationen geraten. Massgeblich ist die Implementierung des Frontends oder die offizielle Dokumentation.

### Tests

Der Test verwendet:

- denselben Host wie die erfolgreiche Browseranfrage
- dieselbe vollstaendige URL
- dieselbe HTTP-Methode
- dieselben erforderlichen, nicht sitzungsbezogenen Header
- den System Access Token aus der vorhandenen Secret-Datei
- keine Browser-Cookies

### Moegliche Ergebnisse

#### A: Token funktioniert direkt

Dies ist die bevorzugte Loesung. Ein kleiner Collector kann die beiden Werte regelmaessig ohne Chromium abrufen.

#### B: Token ist gueltig, aber die Codespace-IP wird blockiert

Dann wird derselbe Abruf aus einer geeigneten, autorisierten Umgebung getestet, beispielsweise vom lokalen Rechner oder einem eigenen Server. Ein HTTP-403 von Cloudflare beweist nicht, dass der Token ungueltig ist.

#### C: Token erlaubt nur Modellaufrufe

Falls der Token nur Endpunkte wie `/v1/models` und Modellanfragen autorisiert, reicht er fuer Kontostand und Verbrauch nicht aus.

#### D: Kontowerte erfordern eine Websitzung

Dann gibt es ohne Unterstuetzung des Betreibers keine vollstaendig browserfreie API-Loesung.

## Phase 4: Minimalen Collector bauen

Wenn der direkte Token-Abruf funktioniert, wird ein kleines Skript unter `scripts/` erstellt.

Der Collector soll:

- ausschliesslich Kontostand und Verbrauch abrufen
- den System Access Token nur aus der vorhandenen Secret-Datei lesen
- keine Secrets protokollieren
- die Rohwerte korrekt umrechnen
- das Ergebnis atomar in einen lokalen Cache schreiben
- bei Fehlern den letzten erfolgreichen Stand behalten

Beispiel fuer den internen Cache:

```json
{
  "balance": 4384.43,
  "consumption": 12.64,
  "updated_at": "2026-09-05T18:52:00Z",
  "status": "ok"
}
```

`updated_at` und `status` dienen nur der technischen Fehlerbehandlung. Die sichtbare Anzeige enthaelt weiterhin nur Kontostand und Verbrauch.

## Phase 5: Minimale Anzeige bauen

Die Anzeige benoetigt keine grosse Anwendung. Ein kleiner lokaler Webserver oder eine statische HTML-Seite mit einer regelmaessig aktualisierten JSON-Datei reicht aus.

Die Oberflaeche zeigt ausschliesslich:

```text
Kontostand
4384,43

Verbrauch
12,64
```

Weitere Kontodaten, Logs, Tokeninformationen und Verwaltungsfunktionen werden nicht dargestellt.

## Phase 6: Fallback mit kurzlebigem Chromium

Falls kein direkter Token-Abruf moeglich ist, wird Chromium nur fuer die Aktualisierung gestartet.

### Ablauf

1. Chromium mit einem persistenten Profil starten.
2. Die Kontoseite laden.
3. Kontostand und Verbrauch auslesen.
4. Den lokalen Cache aktualisieren.
5. Chromium sofort beenden.

### Aktualisierungsintervall

Ein Intervall von 30 bis 60 Minuten ist sinnvoll. Chromium verbraucht dadurch nur waehrend der kurzen Aktualisierung CPU und Arbeitsspeicher.

### Einschraenkungen

- Cloudflare kann nach einem Neustart erneut eine manuelle Pruefung verlangen.
- Die Anmeldung kann ablaufen.
- Das persistente Profil kann ungueltig werden.
- Der Abruf ist langsamer und weniger stabil als eine reine API-Loesung.

## Cookies und Fetch aus DevTools

Ein aus DevTools kopierter `fetch()`-Aufruf oder **Copy as cURL** ist fuer die Diagnose hilfreich. Er zeigt, welche URL, Header und Cookies die erfolgreiche Anfrage verwendet.

Kopierte Cookies sind jedoch keine geeignete Dauerloesung:

- Sitzungscookies laufen ab.
- Cloudflare-Cookies sind zeitlich begrenzt.
- Cookies koennen an IP-Adresse, Browsermerkmale oder User-Agent gekoppelt sein.
- Sitzungen koennen serverseitig widerrufen werden.
- Web-Cookies besitzen moeglicherweise mehr Rechte als fuer die Anzeige erforderlich.

Cookies werden deshalb nur zur Analyse verwendet und weder dauerhaft gespeichert noch als primaere Authentifizierung eingeplant.

## Fehlerverhalten

Der Monitor darf bei einem Fehler niemals `0` als Kontostand oder Verbrauch anzeigen.

Stattdessen soll er:

- den letzten erfolgreichen Wert beibehalten
- den technischen Status intern auf `fetch_failed` oder `reauth_required` setzen
- den Fehler ohne Secrets protokollieren
- Wiederholungsversuche mit angemessenem Abstand ausfuehren
- bei abgelaufener Sitzung eine erneute Anmeldung anfordern

## Sicherheitsgrenzen

Die Loesung umgeht Cloudflare nicht. Sie verwendet ausschliesslich:

- offizielle Tokenauthentifizierung, falls unterstuetzt
- eine legitim angemeldete Browsersitzung als Fallback
- Lese-Endpunkte, welche die eigene Kontoseite verwendet

Der Collector erhaelt nur die fuer Kontostand und Verbrauch erforderlichen Leserechte. Folgende Funktionen gehoeren ausdruecklich nicht zum Umfang:

- Token erstellen oder loeschen
- Passwort aendern
- Konto aufladen
- Kontoeinstellungen aendern
- Konto loeschen
- administrative Endpunkte aufrufen

## Umsetzungsreihenfolge

1. Chromium-Tab stabilisieren.
2. Erfolgreiche Kontodatenanfrage ueber DevTools oder Debugschnittstelle erfassen.
3. API-Host, URL, Methode und erforderliche Header bestimmen.
4. Umrechnungslogik fuer Kontostand und Verbrauch verifizieren.
5. System Access Token exakt gegen diese Anfrage testen.
6. Bei Erfolg einen reinen API-Collector bauen.
7. Einen lokalen Cache mit atomaren Aktualisierungen implementieren.
8. Eine minimale Anzeige mit genau zwei Werten erstellen.
9. Bei fehlender Token-API den kurzlebigen Chromium-Collector implementieren.
10. Fehlerfaelle, Sitzungsablauf und Neustartverhalten testen.

## Entscheidungskriterium

Die Varianten werden in dieser Reihenfolge bevorzugt:

1. Direkter offizieller API-Abruf mit System Access Token
2. Direkter API-Abruf aus einer anderen autorisierten Umgebung
3. Kurzlebiger Chromium-Prozess mit persistentem Profil
4. Dauerhaft laufender Chromium-Prozess nur als letzte Option

Die beste Zielarchitektur bleibt:

```text
Token -> API -> lokaler Cache -> Zwei-Werte-Anzeige
```

Damit ist die Anzeige ressourcenschonend, minimal und unabhaengig von einem dauerhaft geoeffneten Browser.
