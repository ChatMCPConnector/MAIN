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

## Konkrete Schritte fuer einen browserlosen Abruf

Das Ziel ist ein Abruf mit `fetch()` ohne dauerhaft laufenden Browser. Die bevorzugte Variante verwendet den System Access Token. Cookies sind nur die zweite Wahl, da sie normalerweise an eine angemeldete Sitzung gebunden sind, ablaufen und erneuert werden muessen.

### 1. Exakte API-Anfrage ermitteln

Einmalig wird im angemeldeten Browser die erfolgreiche Anfrage an `/api/user/self` im Network-Tab der DevTools untersucht. Dabei sind folgende Angaben zu erfassen:

- vollstaendiger API-Host
- vollstaendige URL
- HTTP-Methode
- erforderliche Request-Header
- Struktur der JSON-Antwort
- Bedeutung und Einheit von `quota` und `used_quota`

Es sollen nicht unbesehen alle Browser-Header uebernommen werden. Entscheidend ist, welche Authentifizierung und welche wenigen Header die offizielle API tatsaechlich benoetigt.

### 2. System Access Token testen

Anschliessend wird dieselbe Anfrage ausserhalb des Browsers mit dem offiziellen System Access Token ausgefuehrt:

```js
const response = await fetch("https://API-HOST/api/user/self", {
  headers: {
    Authorization: `Bearer ${process.env.SYSTEM_ACCESS_TOKEN}`,
    Accept: "application/json",
  },
});

if (!response.ok) {
  throw new Error(`API request failed: HTTP ${response.status}`);
}

const data = await response.json();
console.log(data);
```

Falls die API einen anderen dokumentierten Token-Header verwendet, muss dieser statt `Authorization: Bearer` eingesetzt werden. Der Header darf nicht geraten werden, sondern muss aus der offiziellen Dokumentation oder einer bereits funktionierenden Token-Anfrage hervorgehen.

### 3. Cloudflare- und API-Fehler unterscheiden

Die Antwort muss sorgfaeltig ausgewertet werden:

- `200` mit JSON: Der browserlose Abruf funktioniert.
- `401`: Der Token fehlt, ist ungueltig oder abgelaufen.
- `403` von der API: Dem Token fehlt wahrscheinlich die erforderliche Leseberechtigung.
- `403` von Cloudflare: Die Anfrage wurde abgefangen, bevor sie die API erreichte.
- HTML statt JSON: Wahrscheinlich wurde eine Cloudflare-, Login- oder Fehlerseite geliefert.

Eine robuste Inhaltspruefung kann so aussehen:

```js
const contentType = response.headers.get("content-type") ?? "";

if (!response.ok) {
  const body = await response.text();
  throw new Error(
    `HTTP ${response.status}, content-type=${contentType}, body=${body.slice(0, 200)}`
  );
}

if (!contentType.includes("application/json")) {
  throw new Error(`Expected JSON, received ${contentType}`);
}

const data = await response.json();
```

Tokens, Cookies und vollstaendige sicherheitsrelevante Header duerfen dabei nicht protokolliert werden.

### 4. Cookie-Variante nur bei Bedarf

Falls die API keine Token-Authentifizierung fuer diesen Endpunkt anbietet, kann eine legitim erzeugte Sitzung technisch per Cookie verwendet werden:

```js
const response = await fetch("https://API-HOST/api/user/self", {
  headers: {
    Accept: "application/json",
    Cookie: process.env.ACCOUNT_COOKIE,
  },
});
```

Bei Node.js reicht `credentials: "include"` allein nicht aus. Anders als ein Browser besitzt ein einfacher Node-Prozess keine automatisch gefuellte Cookie-Jar und keine bestehende Anmeldung. Vor einer dauerhaften Cookie-Loesung muss deshalb geklaert werden:

- wie das Cookie legitim erzeugt wird
- wann das Cookie ablaeuft
- wie die Sitzung erneuert wird
- ob ein CSRF-Token erforderlich ist
- ob die Sitzung an weitere Sicherheitsmerkmale gebunden ist
- ob ein offizieller programmatischer Login-Endpunkt existiert

Ein manuell aus den DevTools kopiertes Cookie eignet sich nur fuer einen kurzfristigen Test und nicht als dauerhafte Architektur.

### 5. Umrechnung der API-Werte verifizieren

Die sichtbaren Werte `4384.43` und `12.64` muessen mit der echten JSON-Antwort verglichen werden. Vor der Implementierung ist zu pruefen:

- ob `used_quota` direkt dem Verbrauch entspricht
- ob der Kontostand `quota`, `quota - used_quota` oder einem anderen Feld entspricht
- ob die Rohwerte in Hundertstel-, Millionstel- oder einer anderen Einheit gespeichert werden

Die Umrechnung darf erst nach diesem Vergleich fest implementiert werden, damit keine plausiblen, aber falschen Werte angezeigt werden.

### 6. Collector und lokaler Cache

Wenn die Token-Anfrage funktioniert, soll ein kleiner Node-Prozess:

1. `/api/user/self` abrufen.
2. HTTP-Status, Content-Type und Antwortstruktur validieren.
3. `quota` und `used_quota` in die angezeigten Werte umrechnen.
4. Den letzten erfolgreichen Stand atomar in eine lokale JSON-Datei schreiben.
5. Bei Fehlern die letzten erfolgreichen Werte beibehalten.
6. Den Abruf in einem angemessenen festen Intervall wiederholen.

Beispiel fuer den lokalen Cache:

```json
{
  "balance": 4384.43,
  "usage": 12.64,
  "updatedAt": "2026-09-05T20:30:00.000Z",
  "status": "ok"
}
```

Die sichtbare Ausgabe bleibt auf genau zwei Werte beschraenkt:

```text
Kontostand: 4384,43
Verbrauch:    12,64
```

### 7. Empfohlene Reihenfolge

1. Erfolgreiche Browser-Anfrage an `/api/user/self` vollstaendig analysieren.
2. System Access Token mit derselben URL und den minimal erforderlichen Headern testen.
3. Antwortfelder mit den sichtbaren Konto- und Verbrauchswerten vergleichen.
4. Bei Erfolg den reinen `fetch()`-Collector mit lokalem Cache implementieren.
5. Falls Cloudflare nur den Codespace blockiert, den Token aus einer anderen autorisierten Umgebung testen.
6. Nur wenn keine Token-Authentifizierung moeglich ist, eine offizielle programmatische Sitzung mit Cookie-Jar verwenden.
7. Chromium nur dann kurzzeitig zum Erzeugen oder Erneuern einer legitimen Sitzung starten, wenn kein vollstaendig browserloser Authentifizierungsweg existiert.
