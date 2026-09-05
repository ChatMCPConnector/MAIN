# Infrastructure

Diese Datei dokumentiert den verifizierten technischen Zustand des Codespaces. Neue Sessions muessen sie vor Installationen, Browserstarts oder Infrastruktur-Aenderungen lesen.

## Arbeitsregeln

1. Vor Installationen zuerst vorhandene Pakete, Caches, Prozesse und Profile pruefen.
2. Ein fehlgeschlagener Modulimport ist kein Beleg fuer eine fehlende Installation.
3. Zwischen Node-Paket, Browser-Build, Browserprofil und laufender Instanz unterscheiden.
4. Bestehende, geeignete Installationen bevorzugen.
5. Keine Prozesse beenden und keine Caches, Profile oder Installationen loeschen, ohne Auswirkungen und Abhaengigkeiten zu pruefen.
6. Schwer rueckgaengig zu machende Bereinigungen vor der Ausfuehrung mit dem Benutzer abstimmen.
7. Infrastruktur-Aenderungen nach erfolgreicher Verifikation in dieser Datei dokumentieren.
8. Beobachtungen, geplante Arbeiten und ausgefuehrte Aenderungen klar voneinander trennen.

## Persistenz

Der dauerhafte Workspace ist:

```text
/workspaces/MAIN
```

Alle fertigen Arbeiten muessen vollstaendig nach `/workspaces/MAIN` verlagert werden. Dazu gehoeren insbesondere Quellcode, Konfiguration, Skripte, Dokumentation, erforderliche Assets, produktiv benoetigte Daten und alle sonstigen Bestandteile, die fuer Aufbau, Betrieb oder Weiterentwicklung notwendig sind.

Nur Inhalte unter `/workspaces/MAIN`, die vom Repository erfasst, committed und gepusht werden, koennen durch Git-Push und Git-Pull in andere Codespaces uebernommen werden. Eine Arbeit gilt deshalb erst dann als dauerhaft gesichert, wenn alle erforderlichen Bestandteile unter `/workspaces/MAIN` liegen und vom Repository erfasst werden.

Testdaten, temporaere Dateien, Experimente und andere Hilfsinhalte, die nicht Bestandteil der fertigen Arbeit sind, sollen ausserhalb von `/workspaces/MAIN` direkt unter `/workspaces` abgelegt und verarbeitet werden. Inhalte ausserhalb von `/workspaces/MAIN` werden nicht durch dieses Repository gepusht oder gepullt und koennen bei einem neuen Codespace vollstaendig verloren gehen.

Das produktive System darf sich nicht unbemerkt aus temporaeren Inhalten unter `/workspaces` oder lokalen Inhalten unter `/home/vscode` versorgen. Wenn solche Inhalte fuer Aufbau, Tests, Laufzeit oder Wiederherstellung des produktiven Systems erforderlich werden, muessen sie vollstaendig nach `/workspaces/MAIN` umgezogen, reproduzierbar eingebunden und vom Repository erfasst werden.

Lokale Daten unter `/home/vscode`, insbesondere Browserprofile, npm-Caches und Playwright-Browser-Builds, werden nicht automatisch durch das Repository uebertragen. Fuer jeden benoetigten lokalen Zustand muss daher entweder der erforderliche Inhalt nach `/workspaces/MAIN` uebernommen oder ein vollstaendig reproduzierbarer Aufbau unter `/workspaces/MAIN` dokumentiert werden.

Vor jeder neuen Aenderung muss diese Datei erneut vollstaendig gelesen und der dokumentierte Zustand mit dem aktuellen System verglichen werden. Nach Abschluss der Aenderung ist erneut zu pruefen, ob sich Infrastruktur, Abhaengigkeiten, Pfade, Ports, Dienste, Laufzeitdaten oder Persistenzanforderungen veraendert haben. Falls ja, muss `INFRASTRUCTURE.md` im selben Arbeitsgang nachgezogen werden.

## Verifizierter Zustand

Stand: 2026-09-05

### Playwright

Playwright wurde in temporaeren `npx`-Caches gefunden:

```text
/home/vscode/.npm/_npx/705bc6b22212b352/node_modules/playwright
/home/vscode/.npm/_npx/705bc6b22212b352/node_modules/playwright-core
/home/vscode/.npm/_npx/7f4967a1621aa3dc/node_modules/playwright
/home/vscode/.npm/_npx/7f4967a1621aa3dc/node_modules/playwright-core
```

Verifizierte Versionen:

```text
705bc6b22212b352: Playwright 1.63.0
7f4967a1621aa3dc: Playwright 1.48.2
```

`require("playwright")` aus `/workspaces/MAIN` kann mit `MODULE_NOT_FOUND` scheitern, weil temporaere `npx`-Caches nicht zum normalen Node-Modulaufloesungspfad des Projekts gehoeren. Vor einer Neuinstallation deshalb zuerst die vorhandenen absoluten Paketpfade und den aktuellen `NODE_PATH` pruefen.

### Chromium

Verifizierter Playwright-Browser-Build:

```text
Pfad:    /home/vscode/.cache/ms-playwright/chromium-1140/chrome-linux/chrome
Version: Chromium 130.0.6723.31
Groesse: 412281840 Byte
```

Installationsmarker wurden am 2026-09-05 angelegt:

```text
21:05:50 +0200  chromium-1140/INSTALLATION_COMPLETE
21:05:53 +0200  chromium-1140/DEPENDENCIES_VALIDATED
```

Die npm-Protokolle belegen, dass Playwright-Pakete an diesem Tag von `registry.npmjs.org` geladen und entpackt wurden. Der Chromium-Build ist ein von Playwright verwalteter Browser und keine verifizierte systemweite Google-Chrome-Installation.

In den geprueften Standardpfaden und Paketdaten wurde kein ausfuehrbares systemweites `google-chrome`, `google-chrome-stable`, `chrome`, `chromium` oder `chromium-browser` nachgewiesen.

### Laufende Browserinstanz

Die am 2026-09-05 verifizierte Hauptinstanz lief als PID `392273` und wurde um `22:14:30 +0200` gestartet.

```text
/home/vscode/.cache/ms-playwright/chromium-1140/chrome-linux/chrome
```

Relevante Startparameter:

```text
--remote-debugging-address=127.0.0.1
--remote-debugging-port=9222
--user-data-dir=/home/vscode/.config/chromium
https://new.xinjianya.top
```

Vor der Wiederverwendung immer pruefen, ob der Prozess und Port `9222` noch aktiv sind. Prozess-IDs und laufende Sitzungen sind nicht dauerhaft.

### Browserprofil

Verwendetes Profil:

```text
/home/vscode/.config/chromium
```

Dieses Profil kann Anmeldestatus und andere lokale Browserdaten enthalten. Es darf nicht geloescht, ersetzt, kopiert oder veroeffentlicht werden, ohne die Auswirkungen und den Schutz sensibler Daten zu klaeren.

Das Profil liegt ausserhalb des Repositorys und wird bei einem neuen Codespace nicht automatisch wiederhergestellt.

### VNC und noVNC

Die verifizierte Browseranzeige lief auf Display `:120`.

```text
x11vnc:  localhost:5920
noVNC:   Port 6082
Web UI:  /vnc.html?autoconnect=1&resize=scale
```

Lokaler Aufruf:

```text
http://localhost:6082/vnc.html?autoconnect=1&resize=scale
```

In einem Remote-Codespace muss `localhost:6082` durch die weitergeleitete Workspace-URL fuer Port `6082` ersetzt werden.

### Chromium DevTools Protocol

Der verifizierte Debugging-Port ist nur lokal gebunden:

```text
http://127.0.0.1:9222
```

Die Zieluebersicht kann ueber folgenden Endpunkt geprueft werden:

```text
http://127.0.0.1:9222/json/list
```

Der Port darf nicht ungeschuetzt oeffentlich freigegeben werden, weil eine CDP-Verbindung Kontrolle ueber die Browsersitzung ermoeglichen kann.

## Empfohlene Konsolidierung

Der aktuelle Zustand soll nicht durch sofortiges Loeschen bereinigt werden. Die sichere Reihenfolge ist:

1. Eine kanonische Playwright-Version fuer den Workspace festlegen.
2. Diese Version reproduzierbar im Repository deklarieren und pinnen.
3. Einen dokumentierten Startmechanismus fuer Chromium, Profil, Display, CDP und noVNC erstellen.
4. Den Startmechanismus in einer neuen Sitzung verifizieren.
5. Erst danach ermitteln, welche temporaeren `npx`-Caches redundant sind.
6. Redundante Caches nur nach ausdruecklicher Freigabe entfernen.

Bis diese Konsolidierung abgeschlossen ist, gelten die vorhandenen Cachepfade als beobachteter Ist-Zustand und nicht als stabile Schnittstelle.

## Pruefung vor Browserarbeiten

Vor Installation oder Start mindestens pruefen:

```bash
pgrep -af 'chrome|chromium'
ss -ltnp | grep -E ':9222|:6082|:5920'
find /home/vscode/.cache/ms-playwright -maxdepth 2 -type d -print
find /home/vscode/.npm/_npx -path '*/node_modules/playwright/package.json' -print
```

Wenn eine geeignete Instanz aktiv ist, soll sie verwendet werden. Wenn nur der Browser-Build vorhanden ist, soll der vorhandene Build mit dem dokumentierten Profil gestartet werden. Eine neue Installation ist erst nach negativer Bestandspruefung gerechtfertigt.

## Aenderungsprotokoll

### 2026-09-05

- Laufende Chromium-Prozesse, Executables und Startzeiten geprueft.
- Playwright-Versionen `1.63.0` und `1.48.2` in temporaeren `npx`-Caches identifiziert.
- Playwright-Chromium unter `chromium-1140` mit Version `130.0.6723.31` identifiziert.
- Installationsmarker und npm-Protokolle ausgewertet.
- Browserprofil, CDP-Port und noVNC-Zuordnung dokumentiert.
- Modulaufloesungsfehler von einer fehlenden Installation unterschieden.
- Keine Browserinstallation oder Cachebereinigung im Rahmen dieser Dokumentation ausgefuehrt.
- Verbindliche Persistenzregeln fuer fertige Arbeit unter `/workspaces/MAIN` dokumentiert.
- `/workspaces` als Ablageort fuer nicht dauerhafte Testdaten und temporaere Arbeitsinhalte festgelegt.
- Vollstaendige Infrastrukturpruefung vor jeder neuen Aenderung und erneute Aktualitaetspruefung nach deren Abschluss vorgeschrieben.

## Vorlage fuer weitere Eintraege

```text
### YYYY-MM-DD HH:MM Zeitzone

Anlass:

Gepruefter Ausgangszustand:

Ausgefuehrte Aenderung:

Betroffene Pfade, Ports und Prozesse:

Verifikation:

Offene Punkte oder Rueckweg:
```
