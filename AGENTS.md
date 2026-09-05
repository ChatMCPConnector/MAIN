# Agent Instructions

## Session Start

1. Lies `INFRASTRUCTURE.md` zu Beginn jeder Session vollstaendig, damit Aufbau, Persistenzregeln, Abhaengigkeiten und aktueller Infrastrukturzustand verstanden werden.
2. Lies `INFRASTRUCTURE.md` vor jeder neuen Aenderung erneut vollstaendig und pruefe den dokumentierten Zustand gegen das aktuelle System. Prozess-IDs, offene Ports und lokale Sitzungen koennen veraltet sein.
3. Pruefe nach jeder Aenderung, ob `INFRASTRUCTURE.md` aufgrund neuer oder geaenderter Infrastruktur, Abhaengigkeiten, Pfade, Dienste, Laufzeitdaten oder Persistenzanforderungen aktualisiert werden muss. Ziehe die Dokumentation im selben Arbeitsgang nach.
4. Interpretiere einen fehlgeschlagenen Import oder einen fehlenden Befehl nicht automatisch als fehlende Installation. Suche zuerst in vorhandenen Caches, Paketpfaden und laufenden Prozessen.

## Infrastructure

- `INFRASTRUCTURE.md` ist die zentrale Quelle fuer installierte Werkzeuge, Browser-Builds, Profile, Ports, Dienste und Infrastrukturentscheidungen.
- Fuehre keine parallele agentspezifische Infrastrukturakte.
- Dokumentiere nur verifizierte Zustaende und tatsaechlich ausgefuehrte Aenderungen.
- Trenne klar zwischen Ist-Zustand, Planung und abgeschlossener Arbeit.
- Aktualisiere `INFRASTRUCTURE.md` nach jeder verifizierten Infrastruktur-Aenderung.
- Speichere keine Tokens, Cookies, Passwoerter oder andere Geheimnisse in der Dokumentation.

## Safety

- Installiere nichts, bevor vorhandene Installationen und Caches geprueft wurden.
- Beende keine fremden oder unerwarteten Prozesse ohne ausdrueckliche Freigabe.
- Loesche oder ersetze keine Browserprofile, Caches oder Installationen ohne vorherige Bestandspruefung und Freigabe.
- Veraendere keine nicht zugehoerigen Arbeiten im Git-Worktree.
- Verwende fuer schwer rueckgaengig zu machende Aenderungen einen dokumentierten Rueckweg.

## Persistence

- Alle fertigen Arbeiten muessen vollstaendig unter `/workspaces/MAIN` liegen und vom Repository erfasst werden, damit sie per Git-Push und Git-Pull in andere Codespaces gelangen.
- Quellcode, Konfiguration, Skripte, Dokumentation, erforderliche Assets, produktiv benoetigte Daten und sonstige notwendige Bestandteile duerfen nach Abschluss nicht nur ausserhalb von `/workspaces/MAIN` existieren.
- Testdaten, Experimente und temporaere Hilfsinhalte, die nicht zur fertigen Arbeit gehoeren, sollen direkt unter `/workspaces` bearbeitet werden.
- Inhalte unter `/workspaces` ausserhalb von `/workspaces/MAIN` werden nicht durch dieses Repository gesichert und koennen bei einem neuen Codespace verloren gehen.
- Wenn das produktive System Inhalte ausserhalb von `/workspaces/MAIN` benoetigt oder sich von dort versorgt, muessen diese Inhalte vollstaendig nach `/workspaces/MAIN` umgezogen, reproduzierbar eingebunden und vom Repository erfasst werden.
- Lokale Inhalte unter `/home/vscode` gelten nicht als automatisch portabel oder gesichert.
- Wenn ein lokaler Zustand fuer neue Codespaces notwendig ist, uebernimm die erforderlichen Bestandteile nach `/workspaces/MAIN` oder dokumentiere dort einen vollstaendig reproduzierbaren Aufbau.
