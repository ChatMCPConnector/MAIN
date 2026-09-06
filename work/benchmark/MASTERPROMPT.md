# MASTERPROMPT — SWE-Bench-Grade End-To-End Task (Tool-Agnostisch)

> Zweck: Gleicher Prompt für alle 3 GLM-Proxies (glm2api:8001, HelloGML:8787, Chat2API:8080).
> Die Modelle müssen SELBST erkennen, welche Tools/Werkzeuge sie benötigen, und sie verwenden.
> Kein Tool wird namentlich genannt. Bewertet wird: Tool-Erkennung, Planung, Ausführung, Korrektheit, Robustheit.

---

## Prompt (wörtlich verwenden)

```
Du bist ein autonomer Software-Ingenieur. Dir wurde ein kleiner, absichtlich vermurkster Webserver übergeben, der kaputt ist — auf mehrere, realistische Arten gleichzeitig. Deine Aufgabe: Diagnose, Reparatur, Absicherung und Erweiterung — vollständig selbstständig, von der Erkundung bis zum abschließenden Beweis, dass alles funktioniert.

## Ausgangslage

Im Verzeichnis ./chaosshop liegt ein kleiner Python-Webserver (kein externes Framework mit Magie: nur die Standardbibliothek — http.server, json, sqlite3, threading). Er soll einen kleinen Laden ("ChaosShop") verwalten: Produkte, Bestellungen, ein simples Auth-System. Betreten auf eigene Gefahr: Die letzten drei "Entwickler" haben es mit Absicht kaputt gespielt.

Wichtig: Alle Abhängigkeiten sind im Projekt selbst definiert und installierbar, falls du etwas brauchst — aber es sollte nichts über die Standardbibliothek hinaus benötigt werden.

## Deine Aufgaben (alle erfüllen)

### Phase 1 — Erkunden & Verstehen
1. Verschaffe dir ein vollständiges Bild des Projekts: Struktur, Einstiegspunkte, Datenmodelle, offensichtliche und versteckte Probleme.
2. Du wirst feststellen, dass das Repository eine Reihe von Tests mitbringt (im `tests/`-Ordner). Zu Beginn scheitern mehrere davon — mit ganz unterschiedlichen Fehlerarten (Logikfehler, Crashes, Race Conditions, Datenkorruption).
3. Analysiere, welche Tests warum scheitern, und dokumentiere deine Hypothesen, bevor du etwas veränderst.

### Phase 2 — Reparieren
4. Behebe alle gefundenen Fehler — einen nach dem anderen, jeweils mit Begründung. Verändere so wenig wie möglich am gesunden Code; die Intention der bestehenden Architektur ist zu respektieren.
5. Mindestens drei der folgenden Problemklassen sind in diesem Projekt versteckt — finde sie durch systematische Analyse, nicht durch Raten:
   - eine Race Condition im Nebenläufigkeits-/Datenhaltungsbereich,
   - eine fehlerhafte Authentifizierungs-/Autorisierungslogik,
   - ein SQL- bzw. Datenbankproblem (Injektion, Transaktion, Schema),
   - ein Fehler, der erst unter Last oder in einer bestimmten Reihenfolge auftritt,
   - eine defekte Randfallbehandlung (leere Eingaben, Extreme, ungültige Typen).
   Du darfst Tests ergänzen, um deine Diagnosen abzusichern — aber bestehende, legitime Test-Erwartungen dürfen nicht verändert werden, um sie grün zu bekommen.

### Phase 3 — Absichern & Erweitern
6. Härtung: Schließe die zwei gravierendsten Angriffsflächen, die du findest. Es gibt mindestens eine Injection-Schwachstelle und mindestens eine Autorisierungslücke.
7. Erweiterung — Wunsch des "Produktteams":
   - Bestellungen sollen über einen neuen Endpunkt in der Gesamtübersicht als CSV exportiert werden können.
   - Der Export darf nur für angemeldete Nutzer mit Admin-Rolle möglich sein.
   - Die Daten müssen datenschutzkonform aufbereitet werden: Zwei Felder sind als personenbezogen markiert (siehst du im Code) und müssen im Export maskiert werden (z.B. erste 2 Zeichen behalten, Rest maskieren).
   - Der Export muss performant bleiben, auch wenn 10.000 Bestellungen existieren — lege eine sinnvolle Obergrenze und ein Streaming-Verhalten fest und begründe es.

### Phase 4 — Beweisen & Berichten
8. Am Ende muss gelten: Alle Tests grün — die mitgelieferten UND alle eigenen, die du zur Absicherung ergänzt hast.
9. Erstelle eine kleine, reproduceable Checkliste, mit der ein Mensch in maximal 5 Schritten verifizieren kann, dass (a) der Server startet, (b) die Schwachstellen behoben sind, (c) der CSV-Export die Maskierung korrekt umsetzt und Admin-geschützt ist.
10. Berichte strukturiert: (i) Liste der gefundenen Probleme mit Schweregrad, (ii) was du geändert hast und warum, (iii) was du bewusst NICHT geändert hast und warum, (iv) Restrisiken und Empfehlungen.

## Rahmenbedingungen

- Arbeite vollständig eigenständig: Recherchiere im Projekt, probiere aus, miss Strings statt zu raten, lies Log- und Testausgaben genau.
- Nutze alle dir zur Verfügung stehenden Mittel, die dir dein Arbeitsumwerkzeug bietet — Dateisystem, Shell, Tests, Debugging. Wähle selbst, welches Werkzeug in welcher Situation das richtige ist. Dir wird absichtlich NICHT vorgeschrieben, wie du arbeitest.
- Wenn du feststeckst: Zerlege das Problem, bilde Hypothesen, verifiziere sie einzeln, bevor du weitermachst. Ein tragfähiger Teilerfolg mit sauberer Begründung ist besser als eine schnelle, oberflächliche "Lösung".
- Am Ende zählt nur, was nachweisbar funktioniert: grüne Tests, laufender Server, erfüllter Funktionsumfang, geschlossene Sicherheitslücken.

Beginne jetzt.
```

---

## Hinweise für den Testbetrieb (nicht Teil des Prompts)

- **Setup:** `./chaosshop` muss vorher als Mini-Projekt erzeugt werden (siehe unten), wenn es nicht existiert — der Prompt selbst darf den Code nicht vorwegnehmen (sonst wird's kontaminiert).
- **Projekt-Realität:** chaosshop besteht aus: `server.py` (Standardbibliothek-HTTP-Server mit REST-Routen), `db.py` (sqlite3 mit Race im `save_order` ohne Lock, SQL-String-Konkatenation), `auth.py` (Passwort-Check mit Timing-Leak + Rollenprüfung, die `admin` bei einem Off-by-one überspringt), `models.py` (Order/Product-Datenklassen mit einem Typ-Bug bei Mengen=0), `tests/` (pytest, ~12 Tests, 5 scheitern anfangs: Race, Auth-Bypass, SQL-Fehler bei Anführungszeichen, Crash bei leerem Namen, CSV ist noch nicht vorhanden — der letzte ist Teil Phase 3). Zwei Felder mit `PII=True`-Markierung (customer_name, email).
- **Bewertung pro Modell:** (1) Anzahl/Qualität der selbst gewählten Werkzeugeinsätze (Lesen, Suchen, Ausführen, Testen, Debuggen), (2) Reihenfolge & Systematik der Diagnose, (3) alle 5 rote Tests → grün, (4) Race-Condition erkannt UND behoben (Lock/Transaktion), (5) Auth-Bypass erkannt UND behoben, (6) SQL-Injection erkannt UND behoben (parametrisiert), (7) CSV-Endpunkt mit Maskierung + Admin-Gate implementiert, (8) Berichtqualität (Struktur, Begründungen, Restrisiken).
- **Härtegrad:** Absichtlich so gebaut, dass "blind drauflos-Patchen" in Diagnose-Chaos endet: Die Tests scheitern mit ungleichen Fehlerbildern (ein Test crasht, einer liefert falsche Daten, einer flackt nur manchmal — die Race).
- **Fairness:** Der Prompt nennt keinerlei Toolnamen, keine Dateinamen, keine Befehle. Alle nötigen Infos sind im Projekt selbst auffindbar — für den, der gründlich liest.

## Messgrößen für den Vergleich

| Metrik | glm2api | HelloGML | Chat2API |
|---|---|---|---|
| Diagnose-Systematik (0-10) | | | |
| Fehler gefunden von ~5 | | | |
| Race erkannt+gefixt | | | |
| Auth-Bypass erkannt+gefixt | | | |
| SQLi erkannt+gefixt | | | |
| CSV+Maskierung+Admin-Gate | | | |
| Eigene zusätzliche Tests | | | |
| Tool-Auswahl-Kompetenz (0-10) | | | |
| Bericht (0-10) | | | |
| Zeit bis "fertig" | | | |
| Abbrüche/Fehlversuche | | | |
| Gesamturteil | | | |
