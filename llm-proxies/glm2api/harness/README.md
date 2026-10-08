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
.venv/bin/python3 harness/breadth_variance.py ../../.runtime/glm2api-*.jsonl
.venv/bin/python3 harness/breadth_variance.py --selftest   # Auflisten≠Lesen
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
| `breadth_variance.py` | Breite der Dateiinspektion je `opencode run`-Lauf aus den JSON-Ereignislogs (`read`-Ziele + bash-Lesekommandos); trennt Auflisten von Lesen | `--selftest` hält die Trennung fest (Auflisten zählt 0 Inhalt); Messung siehe „Breadth-Varianz-Studie" |

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

Aus diesen Läufen folgten zwei weitere, durch Regressionstests abgesicherte
Reparaturen:

- Erkannte native Calls und blockierte native Versuche **beenden die
  Upstream-Runde sofort** (`status=finish` bzw. `intervene`) statt weiter
  in den Strom zu lesen. Der Strom wird bei blockierten Versuchen verworfen
  und durch eine Korrektur-Runde ersetzt, solange noch kein sichtbarer Text
  ausgeliefert wurde — die Prüfung nutzt dafür `served_visible_text`, nicht
  den rohen `served_content`. Vorher konnte das Modell bereits erfundene
  Ergebnisse zum eigenen `open` produzieren, bevor OpenCode den echten
  Aufruf sah.
- Ergebnisnachrichten behalten die Rolle `tool` und werden als
  `Tool observation (already executed; do not open call IDs): …` gerendert
  (statt als `User:`-Nachricht). Das entfernt das beobachtete
  Transkript-Echo mit `call_id`-Blöcken im sichtbaren Text.
- Am Ende eines Analyse-Prompts (nur wenn Tools aktiv sind) wird eine
  Inventar-/Abdeckungs-Ankerung angehängt: `git ls-files`, falls noch kein
  Assistant-Call ihn ausführte, sonst eine Abdeckungs-Checkliste mit dem
  jeweils letzten `todowrite`-Stand plus der noch aktiven Originalaufgabe.
  Aussagen wie „fertig" ohne Quelldatei-Inspektion werden so adressiert.

| Lauf | Dauer / Exit | Client-Toolcalls | Ergebnis |
|---|---|---|---|
| Baseline | nach ca. 4 min gezielt beendet | 11, darunter `read` auf Shell-Befehl und 404-Webfetch | Drift; nicht bestanden |
| Argument-/Notice-Fix | 101 s / 0 | 4 | Top-Level-Bericht, vorzeitiger Abschluss; nicht bestanden |
| zusätzlich Reasoning-JSON-Recovery | 309 s / 0 | 11 | Verzeichnis-Wiederholungen, interne IDs, zwei widersprüchliche Berichte; nicht bestanden |
| final inkl. Think-Chunk-Merge | 230 s / 0 | 5 Bash-Aufrufe, keine Dateiinhalt-Reads | doppeltes Listing, zwei Berichte, Session-Neustart verlangt; nicht bestanden |
| Handoff-/Tool-Observation-Reparatur | 137 s / 0 | 11, darunter 4 `read` | deutlich besser, aber README-lastig und früher Abschluss |
| Audit-Anker | 328 s / 0 | 18 | `git ls-files` gelesen, aber Transkript-Echo und ein erfundener Dateiinhalt |
| ohne sofortige Korrektur | Hänger, gezielt beendet | viele | wiederholte blockierte `turn*`-Refs bis zum Abbruch — der Auslöser des Intervene-Fixes |
| **Abschluss-Lauf (Intervene + Anker)** | **417 s / 0** | **17 (9 `read`, 7 `bash`, 1 `todowrite`)** | **bestanden:** vollständiger, belegter Bericht; echte Inhalte aus Root, `infra/`, `glm2api`, `zerokey`, `antigravity-proxy` gelesen |
| Wiederholung gegen denselben Stand | 275 s / 0 | 4 (3 `bash`, 1 `read`) | belegt, aber schmaler (Config-/Doku-fokussiert); Evidenz vollständig, Breite geringer |

Der **Abschluss-Lauf** (`ses_eea4a6477ffea3dzmZ0KnI4085`) ist der Beleg für
die Akzeptanz: keine als `error` markierten Toolparts, kein Transport-Timeout,
keine erfundenen Dateiinhalte und kein Session-Neustart. Der Proxy-Log zeigt
die neue Korrektur live (`status=intervene blocked=['open']` → verworfener
Strom + Korrektur-Runde, danach `status=finish`). Die im Bericht genannten
Zahlen wurden stichprobenweise gegen die Wirklichkeit geprüft und stimmen
exakt: 337 getrackte Dateien, `translator.py` 6683, `glm_client.py` 3296,
`tool_parser.py` 2492, `server.py` 1318, `app.py` 112, `verify-codespace.sh`
502, `timeout.sh` 150, `setup.sh` 452, 18.221 LOC in `src/`.

Die **Wiederholung** (`ses_eea41d944ffepGjmTwx0jqCMfv`) bestätigt den
Lauf ohne Hänger, nur mit gültigen Tools (`bash`/`read`) und einem belegten
Bericht; stichprobenartig geprüfte Aussagen (17 `test_*.py`+
`conftest.py`, drei `cmd/`-Binaries, `.env.example`↔`.env.dist`-Gleichheits-
test in `test_config.py:694`, weiterhin vorhandene `zerokey.sh`/`zerokey.bat`
im vendored Baum) treffen zu. Sie inspizierte jedoch vor allem Config und
`infrastructure.md` und las weniger Quelldateien als der Abschluss-Lauf —
GLM-`5.3` ist hier nicht deterministisch. Ein einzelner Lauf belegt daher
den behobenen Hänger-/Drift-Pfad, nicht eine garantierte Analysetiefe.

Final geprüft: `make lint-py test-py` grün, darunter **1806 glm2api-Tests**;
Ruff/Mypy grün im vorhandenen Scope. Bundle frisch erzeugt unter
`llm-proxies/dist/glm2api-bundle.zip` (gitignored), zusätzlich alle 34
Python-Source-/Testdateien byteweise gegen das ZIP geprüft. Source und
Tests sind die persistenten Artefakte; das Bundle ist daraus reproduzierbar.

Weitere Architektur-Risiken (unverändert, kein verifizierter Fix):

- Die frühere fehlende Pending-Notice-Isolation ohne `conversation_id`
  ist in der Live-Nachprüfung vom 2026-10-08 über Wire-Call-IDs repariert
  und regressionsgetestet (siehe unten).
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

## Breadth-Varianz-Studie (2026-10-07)

Frage: liefert der Proxy-Auftrag die Analyse **zuverlässig** breit, oder ist
das ein Glücksfall einzelner Läufe? Gemessen mit
`harness/breadth_variance.py` über die `--format json`-Logs der
`opencode run`-Läufe (identischer Prompt, `--agent build`).

Wichtig für die Lesart: `content_files` zählt nur Dateien, deren Inhalt
nachweislich gelesen wurde (`read`-Ziel oder bash-Lesekommandos mit
Pfadargument); `git ls-files`/`find`/`du`/`wc -l` zählen getrennt als
`inventory`. `src` ist die Teilmenge mit Quellendung. Eine hohe
`content`-Zahl bei `src=0` heißt: viel Config/Doku, kein Quellcode.

| Lauf | Config | exit | s | tools | read | bash | inv | content | Bereiche | src | chars |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `correction-run` | webfetch erlaubt | 0 | 417 | 17 | 9 | 7 | 1 | 6 | 4 | 3 | 9945 |
| `correction-run2` | webfetch verboten | 0 | 275 | 4 | 1 | 3 | 1 | 8 | 2 | 0 | 5691 |
| `var3` | webfetch verboten | **1** | 626 | 14 | 11 | 2 | 1 | 11 | 4 | **8** | 0 |
| `var4` | webfetch verboten | **1** | 125 | 1 | 0 | 1 | 1 | 0 | 0 | 0 | 0 |

**Befund 1 — Breite streut stark, und die breiteste Inspektion lieferte
gar keinen Bericht.** `var3` las 11 Dateien aus 4 Bereichen (8 davon
Quellcode: `app.py`, `server.py`, `config.py`, `glm_client.py`,
`zerokey/server.js`, `antigravity/internal/server/server.go`, `save.sh`,
`setup.sh`) — die breiteste Messung überhaupt — und starb danach mit
`exit=1` und **0** sichtbaren Zeichen. Umgekehrt lieferte
`correction-run2` nur 4 Toolcalls, davon 1 `read`, aber einen vollständigen
belegten Bericht. Toolcall-Zahl und Berichtsqualität sind also **entkoppelt**.

**Befund 2 — `webfetch: deny` erzeugt harte Fehlschläge, nicht bloß
weniger Breite.** In der verbotenen Config fehlt `webfetch` in der
Tool-Allowlist; ein `open(ref_id="https://…")` des Modells ist dann nicht
mehr abbildbar. Der Proxy blockiert die Runde, startet eine Korrektur-Runde,
wiederholt das bis 5/5 und feuert danach bewusst
`Streaming blocked-tool protocol failure` — opencode meldet
`Model tool protocol failure` und endet mit `exit=1`. Belegt in `var3`
(Blockade-Zyklus über `turn0search1`, `call_*`, `todowrite`, eine URL) und
`var4`; der ältere Quick-Control-Lauf (10:46) zeigt dasselbe mit
`tools=open_url`. **Der lautstarke Abbruch ist beabsichtigt** (nicht endlos
schleifen), aber er ist eine Folge der *Config*, nicht des Prompts: bei
erlaubtem `webfetch` mappt `open(url)` erfolgreich und der Zyklus entsteht
nicht. Lehre: das Live-Szenario mit erlaubtem `webfetch` fahren.

**Befund 3 — die saubere Nachmessung war blockiert (Umgebung, kein Code).**
Drei weitere Läufe mit erlaubtem `webfetch` endeten nach 114–141 s mit
`exit=1`, `Upstream service error` — der GLM-Upstream antwortete mit
**HTTP 429, code 10061** („请求过于频繁"), nachdem an einem Tag ~15 Live-Läufe
gegen ein Konto gelaufen waren. Der Proxy backofft (2 Versuche) und gibt
danach 429 an den Client. Ein sauberer `n≥3`-Vergleich derselben Config
steht damit noch aus; die obige Tabelle ist **klein-n** und mischt zwei
Configs. Sie belegt die Streuung und den `webfetch`-Effekt, nicht eine
Verteilung.

**Nicht behauptet:** keine Erfolgsquote, keine „reproduzierte Breite". Ein
Lauf belegt den behobenen Hänger-/Drift-Pfad; die garantierte
Analysetiefe ist offen und gehört vor eine Freigabe mit größerem n und
ohne Upstream-Throttle gemessen.

## T-31: die Session `ses_ee9f9f3ddffe0CDUZ4nrPfwXBW` (2026-10-07, lokal 13:00–13:19)

Nutzerbefund: „da ist einiges schief gegangen … noch sehr langsam und träge
und unreliable". Untersucht wurden die DB-Tabellen `message`/`part`
**plus** der Proxy-Log ihres echten Zeitfensters. Der damalige Text-Dump
kürzte einzelne Parts; er belegt keine vollständige inhaltliche Prüfung. Erste
Verwechslungsquelle beim Lesen: der Proxy-Log schreibt **lokale** Zeit, die
DB speichert UTC-Epoch — dieselben Ereignisse stehen dort zwei Stunden
auseinander (`13:07:57` im Log == `11:07:57` in der DB).

**Ausgangslage.** Der laufende Proxy hatte den Stand geladen: Prozessstart
`11:32:04`, letzte Quelländerung davor (`translator.py` 11:25,
`glm_client.py` 11:28) — der Prozess trug also den Arbeitsbaum, der um
11:50 als `12e926c` committet wurde (Schluss aus mtimes, nicht aus einem
Log-Statement). **Die Fixes waren aktiv — und es war trotzdem langsam.**

**Gemessen:** 1100 s Wallclock, 21 Modellrunden und 22 Toolcalls.
Im Log sind Korrektur-Ketten, ein nach 126 s abgeschnittener SSE-Strom mit
Retry und eine 194-s-Berichtsrunde sichtbar. Die frühere Aufsummierung
(378 + 194 + 144 + 420 s) überstieg die Wallclock und trennte parallele
Anfragen nicht sauber. Sie ist deshalb keine belastbare, disjunkte
Laufzeitaufteilung; die daraus berechneten Prozentwerte sind zurückgezogen.

**Nicht abbildbare `open`-Aufrufe dieser Session: 14**, in zwei Formen:
`ref_id=turn0view0`/`turn3view1`/`turn0search0` (scratchpad-/web-search-
Referenzen, `turn3view1` allein fünfmal) und `ref_id=call_4ad95ea0…` —
**die eigene Tool-Call-ID**, fünfmal. Jeder davon erzwang eine eigene
Korrektur-Runde.

**Ursache der `call_*`-Klasse (T-31).** Der gerenderte Tool-Result-Block
enthielt die `call_id` des Clients wörtlich
(`Tool observation …: [{"call_id": "call_4ad95ea0…", "name": "read", "content": …}]`).
Damit waren die IDs im Prompt sichtbar und konnten als `open`-Ziel
kopiert werden. Das ist ein plausibler Mechanismus, kein isoliert bewiesener
Kausalvergleich. Der Hinweis „do not open call IDs" verhinderte die
beobachteten Aufrufe nicht.

**Reparatur (durch Regressionstests abgesichert, `tests/test_internal_reference_notice.py`):**

- `serialize_tool_result_block` schreibt die `call_id` **nicht mehr** in den
  gerenderten Block; die Zuordnung Aufruf→Ergebnis leistet die Reihenfolge
  im Transcript. Die OpenAI-`tool`-Nachricht behält `tool_call_id`
  unverändert (nur der Prompt-Text ist betroffen).
- `classify_internal_reference()` trennt `scratchpad` (`turn*`) von
  `tool_call_id` (`call_*`/`toolu_*`). Eigene Liste `tool_call_id_targets`
  plus eigene `[tool_call_id_notice]`, weil die bisherige Antwort die
  **falsche Ursache** nannte (sie sprach von web-search-`turn*`-ids). Die
  Korrektur-Runde wird auch für diese Klasse gefahren.

**Live-Beleg (exakter Nutzerprompt, `--agent build --format json`):**

| Lauf | exit | s | tools | read | bash | inv | content | Bereiche | src | chars |
|---|---|---|---|---|---|---|---|---|---|---|
| die Session selbst (mit Fix-Stand) | 0 | 1100 | 22 | – | – | – | – | – | – | 7751 |
| **T-31 `t31b`** | **0** | **251** | **18** | 3 | 13 | 6 | **12** | **5** | **5** | 4478 |

Der Replay dauerte 251 s statt 1100 s. Die ursprüngliche TUI-Session
nutzte Variante `max`, der CLI-Replay keine explizite Variante; ein
kontrollierter Speedup ist damit nicht belegt. Der Harness zählte 12
inhaltlich gelesene Dateien aus 5 Bereichen, darunter 5 Quelldateien —
keine vollständige Prüfung aller Dateien. Kein eigener Call-ID-Open und
kein terminaler Transport-/Protokollfehler wurden beobachtet; dennoch
waren sieben native Aufrufe korrekturbedürftig. Ein abgeschlossener Lauf
belegt keine Zuverlässigkeit. Der Bericht endet nicht mit einem Aufgaben-Abbruch.
Stichproben der genannten Zahlen stimmen: `translator.py` 6725 Zeilen,
`setup.sh` 452, 338 getrackte Dateien, Pack 115,31 MiB,
`.env.dist`↔`.env.example` 74 Diff-Zeilen, Entfernungs-Commit `2bd9161`
(die KB-Angaben sind SI-vs-KiB-Rundungen derselben Dateien).

**Rest-Befunde (bewusst nicht gefixt, ehrlich offen):**

- `ref_id="README.md"` (bloßer Dateiname) fällt in die Bare-Domain-
  Erkennung (T-21) und wird als erfundene URL verworfen statt als Pfad
  gelesen. Ein relativer Pfad ist ohne bekanntes cwd des Clients nicht
  auflösbar; die Verwerfung ist die konservative, dokumentierte Wahl.
- `ref_id="bash"`/`"read"` ohne Argumente, `ref_id="fallback"` und leere
  `open`-Objekte bleiben unmappbar. Sie sind im Lauf billig (2–5 s), weil
  das Modell sofort korrigiert.
- `turn*search*`-Referenzen bleiben vorhanden — die notice wirkt nicht bei
  jedem Zug. Sie kosteten hier Sekunden statt der 100-s-Ketten vorher.
- Upstream-Flakiness (SSE endet ohne `[DONE]`) wird durch Auto-Retry
  abgefedert; ihr disjunkter Anteil an der Session-Laufzeit ist nicht bestimmt.

## Live-Nachprüfung 2026-10-08 (Zwischenstand; Akzeptanz offen)

Exakter neuer Nutzerprompt, OpenCode `build`, `glm2api/glm-5.3`, explizit
`--variant max`. SQLite-Parts werden alle zwei Sekunden read-only beobachtet;
Proxy-Log und JSONL bleiben zusätzliche Evidenz. Rohdaten liegen gitignored
unter `.runtime/main-audit-20261008-*`.

- Lauf A (`ses_ee41c72a6ffelsLUGI0NdVNxqE`): Exit 1 nach 222,4 s,
  vier Tools (drei Inventur-Bash-Calls, ein Todo), kein fertiger Bericht.
  Wiederholte `turn0search1`-Opens erschöpften fünf Korrekturrunden.
  Sichtbares `]}` und englische Selbst-Narration: Akzeptanz nicht erfüllt.
- Lokal reproduziert: ein extrahierter Bare-Call lässt äußere `]}`-Klammern
  im Resttext stehen. Parser-Reparatur entfernt redundante Closers nur an
  einer tatsächlich erkannten Call-Grenze; Stream-Chunkgrößen 1/2/7/64/1000,
  nachfolgender Bericht und Prosa-/Code-Gegenproben sind getestet.
- Live-Log 16:24:44: die Fehlernotiz von A wurde einer separaten, toolfreien
  Anfrage angehängt. `_conversation_key()` teilte ohne `conversation_id`
  den leeren Schlüssel. Rückmeldungen werden jetzt an tatsächlich erzeugte
  Call-IDs gebunden; fremde/neue Requests können sie nicht verbrauchen.
  Speicher ist auf 256 Einträge und 1800 Zeichen pro Eintrag begrenzt.
- Korrektur-Prompts enthalten nun zusätzlich eine vollständige ausführbare
  JSON-Call-Form statt ausschließlich weiterer Verbote. Ob dies die native
  Referenzschleife live behebt, muss die Nachprüfung zeigen.
- Lauf B (`ses_ee4149f29ffedCPDF21zEN9CmE`): Exit 0 nach 468,2 s,
  aber Akzeptanz nicht erfüllt: wiederholte Listings/Größenmessungen,
  keine Implementierungsprüfung und keine ausgeführten Checks. Der Bericht
  behauptet dennoch Abschluss und ungemessene ~100-MB-Historienersparnis;
  sichtbares Fremdwort `toiletcleaning`. Ein früher SSE-Abbruch erforderte
  Retry; native Open-Versuche wurden weiterhin korrigiert.
- Die Originalaufgabe wird in internen Korrekturrunden jetzt nicht mehr
  durch die synthetische Korrektur-Nachricht ersetzt. Der Audit-Anker wählt
  als nächste Inspektion einen noch nicht gelesenen Implementierungspfad
  ausschließlich aus einem echten Tool-Inventar (nicht aus Server-cwd).
- Feedback bindet sich an die endgültigen ausgelieferten Call-IDs, auch
  bei erst im Finalize-Pfad geretteten Text-Calls, nicht an Rohparser-IDs.
- Lauf C (`ses_ee40a4683ffeNisLJIuyaiyX6N`): Exit 0 nach 580,4 s,
  weiterhin unzureichende Implementierungsabdeckung, vorzeitige Berichtsteile
  und sichtbares Echo von `Tool observation …`. Die bestehende Echo-Erkennung
  kannte nur `User:`/`Assistant:`; sie erkennt nun auch das exakte
  Tool-Observation-Label, ohne dessen Inhalt als neuen Call auszuführen.
- Nach zwei blockierten-only Korrekturen mit internen Referenzen wechselt
  nur die Korrekturrunde auf `reasoning_effort=low` (Quick-Mode), ohne die
  Client-Einstellung für spätere Requests zu ändern. Stream und Nonstream
  sind getestet; keine erfundene Datei-/Tool-Ausführung als Ersatz.
- Lauf D: Exit 0 nach 624,6 s; Checks tatsächlich ausgeführt (1841 Python-,
  73 Infra-Tests und Go-Pakete grün). Die Modell-Pipelines nutzten kein
  `pipefail`; unabhängig ausgeführtes `make check` bewahrt den Exit und ist
  grün. Inhaltliche Akzeptanz dennoch offen: GLM-/Go-Implementierung und
  Infra-Skripte nur gelistet/gezählt, nicht inhaltlich geprüft, aber Todos
  bereits als erledigt markiert. Der Bericht lässt diese Lücken unerwähnt.
- Der Anker priorisiert nun fehlende Bereiche vor weiteren Dateien desselben
  Bereichs. `read` auf Verzeichnisse zählt nicht als Implementierungsbeleg.
  Er fordert ehrliche Sampling-/Exclusion-Angaben und `pipefail` bei Checks.
- Lauf E: am 17:06:44/17:07:17 Upstream-Code 10061, Rate-Limit-Backoff.
  Unbegrenztes Kontingent hebt diese Upstream-Drosselung nicht auf; weitere
  unmittelbare Voll-Läufe wurden deshalb nicht gestartet. Kein erfolgreicher
  Gesamtaudit und keine Erfolgsquote sind belegt.
- Testproxys temporär auf Loopback 18001/18002/18003, mit Timer; der gemeinsam genutzte
  Proxy auf 8001 wurde nicht unterbrochen. Dies ist kein neuer Soll-Service.

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
