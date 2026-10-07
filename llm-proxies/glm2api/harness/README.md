# Mess-Harnesses (`harness/`)

Skripte, mit denen Verhalten des Translators **gemessen** wurde, bevor es
geändert wurde. Sie sind keine Tests — die pinnen den Zustand als
`tests/test_translator.py` (S-10 … S-19). Der Unterschied: ein Harness
misst über *alle* Chunkgrößen und liefert ein Protokoll zum Nachlesen; ein
Test pinnt eine Aussage.

Bis 2026-09-27 lagen diese Skripte nur unter `/tmp/glmtest/` und waren nach
dem Codespace-Neustart weg — die Messbasis der S-10…S-13-Arbeit war damit
nicht reproduzierbar. Deshalb liegen sie hier.

## Aufruf

```bash
cd llm-proxies/glm2api
.venv/bin/python3 harness/leak_probe.py            # S-14: Narration-Leak
.venv/bin/python3 harness/leak_probe.py --short    # nur die Zeilen mit Befund
.venv/bin/python3 harness/order_matrix.py --quiet  # Reihenfolge-Invariante
.venv/bin/python3 harness/sweep2.py --quiet        # Vertrags-Sweep beider Pfade
.venv/bin/python3 harness/trace_stream.py s09 7    # Delta-für-Delta-Trace
```

`trace_stream.py <preset> <chunk>`: `preamble`, `fence`, `s09`, `s14`, oder
`eigen:<text>` (mit `\n` für Umbruch). Gibt je Delta Carry, S-05-Puffer,
`tool_parser.pending_text` und den wirklich rausgehenden SSE-Text aus.

Die Harness-Ausnahmen sind exakt pro Chunk und erwartetem Output erfasst.
Andere Streamtexte oder Abweichungen bei Calls, Finish-Grund oder Body
werden weiterhin als Verstöße gemeldet.

## Positivkontrolle (Pflicht)

Ein Harness-Bug sieht aus wie ein Proxy-Bug — in dieser Session waren es
drei Stück. Vor jeder "gemessenen" Änderung gehört dieselbe Messung
gegen den Vorzustand gefahren:

```bash
git worktree add -f /workspaces/wt-x <commit-vor-der-aenderung>
GLM_SRC=/workspaces/wt-x/llm-proxies/glm2api/src \
  .venv/bin/python3 harness/leak_probe.py --short
git worktree remove --force /workspaces/wt-x
```

Erwartung: das alte Ergebnis ist genau das, was kaputt war. Bleibt die neue
Messung auch dort grün, ist entweder die Messung blind oder der Fix wirkungslos.

## Stand

| Skript | Misst | Stand |
|---|---|---|
| `leak_probe.py` | Narration-Rest je Chunkgröße 1…215; Antwort-Gegenprobe mit `read`/`bash`/Fence | S-14 erwartet exakt 0 sichtbaren Narrationstext; 0/215 Calls verloren, Antworttext exakt 0/104 verändert |
| `order_matrix.py` | Exakter Soll- und Chunk-Invarianzvergleich über 17 Text/Call-Layouts × 10 Chunkgrößen; zusätzlich S-14-Rest über alle 215 Chunkgrößen | zuletzt: 170 Layout-Messungen + 215 S-14-Messungen, 0 unbekannte Abweichungen; S-14 ohne Rest, 4/10 bekannte Whitespacevarianten nur in `rand-links-im-carry` |
| `sweep2.py` | Exakter Vertrags-Sweep: 23 Szenarien × 6 Chunkgrößen, Stream- **und** Non-Stream-Pfad (Text, Aufrufe, `finish_reason`, Body) | zuletzt: 138 Messungen, 0 unbekannte Verstöße; S-15-Schlussleerzeichen 2/6 bekannte Chunk-Abweichungen; keine S-14-Ausnahme |
| `trace_stream.py` | Delta-für-Delta-Trace, wenn ein Fall unklar ist | Werkzeug, kein Soll |

**Eigenprüfung der Harnesses** (Pflicht, sonst misst man nichts): beide
Sweeps müssen an einem alten Stand **rot** werden. `order_matrix` meldet
an `9054325` 14 unbekannte Verstöße, `sweep2` 7 — dort sind sie grün, wo
sie heute grün sind.

## OpenCode-MAIN-Analyse (2026-10-07)

Akzeptanz: der exakte Nutzerprompt muss in `opencode run` über
`glm2api/glm-5.3` einen vollständigen, durch Dateiinspektionen belegten
MAIN-Bericht liefern; kein Hänger, keine ungültigen Tools und kein
vorzeitiger Abschluss. Exit 0 allein ist **kein** Bestehen.

Prompt:

> Analysiere das komplette MAIN Verzeichnis, alle Datein und alle Ordner und gebe mir einen Bericht darüber, ob alles so optimiert ist und gut gebaut wurde und was die ganzen Datein tun

Test mit `--agent build --format json`, 1800-s-Wallclock-Timer
(letzter Lauf: 900 s); Edit-,
Question- und Session-Löschtools gesperrt, damit die Analyse weder Dateien
ändert noch auf Benutzereingaben wartet. Bash bleibt verfügbar. Rohdaten
liegen gitignoriert unter `.runtime/glm2api-main-*.jsonl`.

Belegte und durch Regressionstests abgesicherte Reparaturen:

- Native `open(ref_id="bash", properties={"command": ...})`-Wrapper werden
  genauso wie `arguments`/`args` auf das **deklarierte** Tool abgebildet.
- `lineno` wird zu `read.offset`; top-level sowie verschachtelte
  `offset`/`limit` bleiben erhalten. Die bisherigen Erwartungen ohne
  `offset: 1` wurden an diese beabsichtigte Schnittstellenänderung angepasst.
- `ls -la /workspaces/MAIN` als bloßes `ref_id` ist kein Dateipfad und wird
  nicht mehr als unerfüllbarer `read` ausgeliefert. Ohne explizite
  Bash-Delegation wird daraus auch kein erfundener Shell-Aufruf.
- Vorgemerkte Proxy-Rückmeldungen werden **vor** der Serialisierung des
  nächsten Upstream-Requests angehängt, nicht erst nach dessen Versand.
  Message-Dicts werden kopiert; der Client-Kontext wird nicht mutiert.
  Der Test prüft den serialisierten Prompt direkt an der Transportgrenze,
  nicht eine später mutierte Payload-Referenz.
- Vollständige JSON-`open`-Wrapper im Reasoning werden vor dem nativen
  Namensfilter gezielt wiedergewonnen und gegen die echte Tool-Allowlist
  gemappt. Die native Denylist des allgemeinen Parsers bleibt unverändert.
- `think`-Fragmente derselben Part werden wie Text-Deltas akkumuliert;
  Volltext-Snapshots ersetzen den bisherigen Stand idempotent. Dadurch
  zerreißen künstliche Newlines keine über Chunks verteilten JSON-Aufrufe.
  Gegenproben: Chunkgrößen 1/7/64, exakt eine Ausführung und kein
  Allowlist-Bypass.

**Zwischenergebnis des ersten reparierten Live-Laufs:** Exit 0 nach
101 Sekunden, vier Tool-Ausführungen, aber nur Top-Level-Listing und
oberflächlicher Bericht. **Akzeptanz nicht erfüllt.** Das ursprüngliche
`read` auf einen Shell-Befehl war verschwunden und die Rückmeldung stand
jetzt vor dem Versand im Kontext; das Modell brach dennoch zu früh ab.
Weitere Live-Läufe zeigten wiederholte Verzeichnisaufrufe und Versuche,
interne `turn*`-/`call_*`-IDs zu öffnen. Solche IDs sind keine Pfade und
werden bewusst nicht in erfundene Dateizugriffe umgewandelt.

| Lauf | Dauer / Exit | Client-Toolcalls | Ergebnis |
|---|---|---|---|
| Baseline | nach ca. 4 min gezielt beendet | 11, darunter `read` auf Shell-Befehl und 404-Webfetch | Drift; nicht bestanden |
| Argument-/Notice-Fix | 101 s / 0 | 4 | Top-Level-Bericht, vorzeitiger Abschluss; nicht bestanden |
| zusätzlich Reasoning-JSON-Recovery | 309 s / 0 | 11 | Verzeichnis-Wiederholungen, interne IDs, zwei widersprüchliche Berichte; nicht bestanden |
| final inkl. Think-Chunk-Merge | 230 s / 0 | 5 Bash-Aufrufe, keine Dateiinhalt-Reads | doppeltes Listing, zwei Berichte, Session-Neustart verlangt; nicht bestanden |

Letzte OpenCode-Session: `ses_eea861b20ffeHugHra9F5KGjmu`.
Die letzte Ausführung hatte keine als `error` markierten Client-Toolparts
und keinen Transport-Timeout, aber weiterhin einen `bash.command="..."`
und einen doppelt ausgeführten Listing-Befehl. Fehlende Analyseabdeckung
macht den Auftrag unabhängig von Exitcode und Berichtslänge unerfüllt.
Es wird **keine** Beschleunigung oder erfolgreiche Gesamt-Reparatur behauptet.

Final geprüft: `make check` grün, darunter **1802 glm2api-Tests**;
Ruff/Mypy grün im vorhandenen Scope. Bundle frisch erzeugt unter
`llm-proxies/dist/glm2api-bundle.zip` (gitignored), zusätzlich alle 34
Python-Source-/Testdateien byteweise gegen das ZIP geprüft. Source und
Tests sind die persistenten Artefakte; das Bundle ist daraus reproduzierbar.

Weitere Architektur-Risiken (unverändert, kein verifizierter Fix):

- `_conversation_key()` nutzt bei fehlender `conversation_id` für alle
  Clients denselben leeren Schlüssel: Pending-Notices sind bei parallelen
  OpenCode-Sessions nicht zuverlässig isoliert.
- Request-Deadlines werden an mehreren Stellen neu erzeugt und nicht in
  jedem SSE-Lese-/Korrekturpfad geprüft; ein echter globaler Wallclock-Cap
  ist dadurch nicht garantiert.
- History-Kompression ist Präfix-Kürzung, keine semantische Zusammenfassung;
  Summary und jüngste Nachrichten können das nominelle Zeichenbudget
  gemeinsam überschreiten. Tool-Runden am neuesten Rand verdienen eigene
  Budget-Gegenproben.
- Ausführbare Calls werden häufig erst nach Ende der gesamten Upstream-Runde
  an OpenCode übergeben. Wiederholte native Calls können deshalb innerhalb
  derselben Runde entstehen, bevor das Modell ein echtes Ergebnis sieht.
- `glm2api.sh restart` kann gegen den Watchdog verlieren: im Test meldete es
  zunächst einen nicht gestoppten Prozess, der tatsächlich die vom Watchdog
  bereits neu gestartete, gesunde Instanz mit aktualisiertem Code war.
- Große Module (`translator.py`, `glm_client.py`, `tool_parser.py`) und viele
  sprachabhängige Textfilter erschweren klare Verträge. `mypy` meldet selbst,
  dass untypisierte Funktionskörper standardmäßig nicht geprüft werden.

## Bekannte Befunde

**Der S-15-Produktionsrand ist nicht vollständig invariant:** bei dem
`rand-links-im-carry`-Layout unterscheidet sich je nach Chunkgrenze ein
abschließendes Leerzeichen. Exakte Messwerte stehen oben und in der
Harness-Whitelist. Eine nachträgliche Korrektur im Stream wurde bewusst
nicht vorgenommen, weil bereits ausgegebene Bytes nicht rücknehmbar sind.

Die früheren S-15…S-19-Produktionsbefunde waren an den damaligen Fällen
behoben (2026-09-27). S-15…S-18 waren die Funde aus dem
Harness-Neuaufbau und sind an `02ceca2` und `9054325` gegengeprüft:
vorbestehend, nicht von S-10…S-14 verursacht. Die Messungen selbst sind mit
den Skripten in diesem Verzeichnis reproduzierbar, die
Positivkontrollergebnisse (127 von 173 neuen Testfällen rot an `02ceca2`)
sind in `tests/test_translator.py` S-15…S-18 gepinnt.

| Befund | Kurzfassung | Stand |
|---|---|---|
| **S-15** | Die S-12-Freigabeschranke verwarf auch einen fertigen, legitimen Satz; der Punkt und Leerraum am Carry-Rand starben mit der Narration. | Satzinhalt behoben mit `strip_turn_start_narration()` + `_owed_lead_edge()`; das Rand-Whitespace-Layout bleibt für Chunk 7/11/20/1000 abweichend und ist exakt dokumentiert |
| **S-16** | Erfundenen Limit-Behauptungen gingen im Text-only-Turn durch — Stream und Body. | behoben: Limit-Filter auch ohne Calls + Body-Kette |
| **S-17** | Apostroph als Satzende erzeugte Absatzumbruch mitten im Wort. | behoben: Apostroph aus Satzendzeichen entfernt |
| **S-18** | Über Parts zerschnittenes DSML leckte im Stream; Ursache: Absatzregel im Markup und fehlender Holdback für angefangene Opener. | behoben: Markup-Grenze + `BEGUN_MARKUP_RE` |
| **S-14-Rest** | Die mehrdeutigen initialen Artikel-Fragmente (`D`, `De`, `Der `, `T`, `Th`, `The `) werden bis zur Disambiguierung gehalten; bekannte Selbst-Narration bleibt unsichtbar, gewöhnliche Prosa mit `Der`/`The` bleibt erhalten. | behoben und verifiziert: 0/215 sichtbare Reste, 0/215 Calls verloren, Prosa-Gegenprobe 0/104 verändert |
| **S-19** | Trenner auf beiden Seiten eines unsichtbaren Calls verdoppelten Absatz-Newlines; auch zwei einzelne Newlines müssen sich über einen Call zu einem Absatz ergänzen. | behoben und mit vier Call-Layouts plus späterer Absatz-Gegenprobe über alle Chunkgrößen geprüft |

Der exakte Streamvergleich kann dokumentierte Whitespace-Reste nicht
weg-normalisieren: `rand-links-im-carry` weicht für Chunk 7, 11, 20 und
1000 nur beim abschließenden Leerzeichen von seiner Sollausgabe ab. Die
Harness-Ausnahme gilt für vollständigen Output und exakte Chunkgröße, nicht
für beliebige Probleme dieses Szenarios.
