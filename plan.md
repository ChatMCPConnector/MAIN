# glm2api-Probleme systematisch beheben

Status: abgeschlossen (Befunde dokumentiert, Cleanup-Kandidaten als Vorschläge offen) · begonnen 2026-09-28

## Befund aus Session `ses_f17fa33b4ffezxYpm1GYW3sSlv`

- Der Agent gab eine falsche Abbruchmeldung („Rundenbegrenzung (8/8)“), obwohl die Runde erst am Anfang stand.
- Native `open`-Aufrufe wurden teils auf `read` abgebildet, teils wegen ungültiger Web-Referenzen verworfen.
- Bei Turns mit gleichzeitig gültigen Tool-Aufrufen und blockierten Aufrufen unterdrückte der Stream-Pfad die Blockierungs-/Loop-Guard-Notiz.
- Der erzeugte Befundbericht behauptete Vollständigkeit, obwohl nur ein Teilbaum bzw. Stichproben gelesen wurden.

## Arbeitsplan und Fortschritt

1. **Proxy-Konfiguration und Live-Fehlerpfad nachvollziehen** — erledigt: Follow-up-Budget ist 2 (`.env` `GLM_BLOCKED_TOOL_FOLLOW_UPS=2`); gemischte Calls werden ausgeliefert, Notizen kumulieren über Runden.
2. **Limit-Claims regressionssicher filtern** — erledigt: `_LIMIT_CLAIM_RE` erkennt `Rundenbegrenzung`/`Rundenbeschränkung`; Stream hält Anfangsfragmente zurück (`_LIMIT_CLAIM_LEAD_PREFIXES` + `_initial_limit_claim_prefix_undecided`); Abschlussfilterung (`strip_invented_limit_claim`) greift auch bei anschließendem echtem Ergebnistext (no-calls-Pfad im finalize).
3. **Gemischte Calls absichern** — erledigt: Stream-Notiz für kumulierte blockierte Namen unabhängig vom letzten `blocked`-Accumulator; Loop-Guard-Notiz unabhängig vom finalen Rundenstatus (`if loop_notice:`).
4. **translator.py nach Zwischenfall konsolidiert** — erledigt: doppeltes Dataclass-Feld `_initial_limit_claim_prefix_held`, doppelte Funktionsdefinition `_initial_limit_claim_prefix_undecided`, doppelter `_self_steering_holdback`-Zweig und doppelte `_LIMIT_CLAIM_RE`-Alternative entfernt; `_NARRATION_TOKEN_RE` um `runden(begrenzung|beschränkung|…limit)` ergänzt; Reset-Zweig gibt Flag nur frei, wenn nicht `_self_steering_holdback(text_delta)`, und leert den Carry mit (sonst Doppel-Prepend → Satzverdopplung im deferred-Puffer).
5. **Chunk-3-Leak an der Wurzel behoben** — erledigt: `_needs_paragraph_break` fügte an der Part-Grenze `(8/` → `8) ` ein künstliches `\n\n` ein (Fragment `8) ` matchte `\d+[.)][ \t]` als Markdown-Liste). Der Umbruch „beendete“ den Claim-Satz künstlich, `_owed_lead_edge` gab `8) ` als angeblichen Rand frei und der Rest streamte. Fix: kein Absatzumbruch bei ungeschlossener Klammer (`previous.count("(") > previous.count(")")` bzw. `[`/`]`).
6. **Vollsuite und Harnesses** — erledigt: Vollsuite `1682 passed`; `order_matrix` 170 Messungen / 0 unbekannte Verstöße; `sweep2` 138 / 0 (bekannter S-15-Rest unverändert); `leak_probe` 0/215 Leaks, 0/215 Call-Verluste, Kontrolle 0/104 verändert; `compileall` OK.
7. **Bundle** — erledigt: `dist/glm2api-bundle.zip` neu gebaut, Verifikation OK (Tests + byte-identischer Source).
8. **Proxy-Neustart** — erledigt: Bestandcheck (alter PID 28471) → `./infra/scripts/glm2api.sh restart` → neuer PID 143661, `/health` 200.
9. **Read-only `opencode run` auf ganz MAIN** — erledigt: `opencode run --model glm2api/glm-5.3 --agent glm2api`, ~31 min, Log `.runtime/opencode-main-analysis.log` (86 KB). Smoke-Test vorab (`ok`-Antwort) und Lauf erfolgreich.
10. **Befunde ausgewertet** — erledigt, siehe unten. Keine weiteren glm2api-Code-Fixes nötig.
11. **Plan abgeschlossen, Status/Diff geprüft, Save-Skript ausgeführt** — erledigt.

## Live-Validierung (Punkt 9)

- **Keine erfundene Abbruchmeldung mehr**: Der Agent vollendete den Auftrag mit strukturiertem Bericht; kein „Rundenbegrenzung“-Leak im Stream.
- **Notices funktionieren end-to-end**: `[blocked_tool_notice]` (ungültige `open`-Referenzen) und `[loop_guard_notice]` (3 identische `open`-Drops) erschienen im Stream; das Modell wechselte darauf korrekt auf `read`/`bash` und behauptete nirgends ein Tool-/Rundenlimit.
- **Abdeckung des Runs** (eigenem Bericht zufolge): Root-Doku/Configs vollständig, `.devcontainer/setup.sh`, `save.sh`, `secrets.sh`, `opencode.json`, `server.py` (Z. 1–1119) vollständig; glm2api-Source (translator/glm_client/tool_parser, ~800 KB), antigravity-Go-Source und ~30 Infra-Skripte katalogisiert/stichprobenartig; `.git`, `.runtime`, `dist/`, Logs als generiert deklariert und übersprungen. Read-only eingehalten.
- Eigene Fehlerbuchung des Agenten: wiederholte fälschliche `open`-Calls (4× nach korrekter Kenntnis) — die Fehlerklasse aus `ses_f17…`, jetzt aber mit sauberer Notice-Behandlung statt erfundenem Abbruch.

## Befunde aus dem Live-Run (offene Vorschläge, kein eigenmächtiger Fix)

1. **TokenRouter-API-Key als Literal** in `.opencode/opencode.json` Z. 12 (`sk-zaza5l2…`), Provider laut Doku ungenutzt — Doku nennt es bewusst (Komfort > Sicherheit), aber Rotation/Entfernen wäre der saubere Weg (kann ich nicht selbst: Provider-Zugang nötig).
2. **9,8-MB-ELF-Binary getrackt**: `llm-proxies/antigravity-proxy/auth` widerspricht eigenem Infra-Soll („Binary liegt nicht im Git“); Entfernen = git-Änderung mit Historie-Frage → Rückfrage-Pflicht.
3. **`config.json` am Repo-Root ist leer (`{}`)** und in keinem Layout-Abschnitt erklärt → klären oder löschen.
4. **`save.sh` committet unsigniert** (`git -c commit.gpgsign=false`), während `setup.sh` SSH-Signierung aufbaut und die Doku signierte Commits vorsieht — Widerspruch, Policy-Entscheidung.
5. **`postStartCommand` rebased beim Boot** mit `|| true` (Fehler verschluckt) — gleiche Fehlerklasse wie der ehemals stille Backup-Fehler.
6. **Doku-Lücken**: Provider `downloaddoctor`/`cyberpradeep` in `opencode.json` undokumentiert; `server.py:941–945` greift auf private Accumulator-Attribute zu (Kapselung, kein Bug); `infrastructure.md` sollte den Anthropic-Endpoint-Unterschied glm2api (hat `/v1/messages`) vs. antigravity (hat ihn nicht) explizit machen.
7. **`setup.sh` MCP-Fallback** (Z. ~223): `sed` fügt JSON-Zeile vor `$schema` ein — funktionsfähig, fragil.
8. Drive-Backup bricht 2026 mit rclone-Shared-`client_id`-Abschaltung unbemerkt im Hook (Doku kennt es, kein Nachfolger).

## Aktueller Verifikationsstand (final)

- `test_translator.py` 1284 passed (inkl. `test_german_round_limit_claim_is_stripped_across_stream_deltas`, 6/6 Chunk-Größen 1/2/3/5/13/1000, strikte Erwartung `streamed == "Ergebnis: 8 Dateien wurden geprüft."` + direkter Filter-Assert).
- Vollsuite `1682 passed, 0 failed`.
- Harnesses: `order_matrix` 170/0, `sweep2` 138/0, `leak_probe` 0/215 + Kontrolle 0/104.
- Bundle neu gebaut und verifiziert; Proxy mit neuem Code am Netz (`/health` 200).
- Live-Run über opencode mit dem gefixten Proxy: erfolgreich, Notices korrekt, kein erfundener Abbruch.
