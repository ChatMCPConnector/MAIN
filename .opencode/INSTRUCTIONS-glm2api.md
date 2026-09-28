# Tool-Disziplin: `open` ist kein Werkzeug (global) + glm2api-Zusatzregeln

Diese Datei wird per `instructions` in `.opencode/opencode.json` geladen und
gilt für **jede** opencode-Session, unabhängig von Agent **und** Modell.

**Warum es nicht im Agenten-Prompt steht:** `build` ist der Default-Agent und
lädt `.opencode/agent/glm2api.md` **nicht**. Live belegt am 2026-09-28
(Session `ses_f17123666ffeMwmhdXlMz3HO1l`): eine `build`-Session rief ~40×
`open` und produzierte eine 15×-identische Aufruf-Schleife, weil diese Regeln
ihr nicht vorlagen. Die proxy-seitige Korrektur (`[native_remap_notice]`,
seit S-21) fängt das ab — diese Datei verhindert es zusätzlich, statt es nur
abzufangen.

> **Ehrliche Reichweite:** opencode kann Instruktionen **nicht pro Modell**
> bedingen. Diese Datei wird daher auch in Sessions mit antigravity,
> tokenrouter, nvidia oder downloaddoctor geladen — live gegengeprüft
> (Marker-Test, 2026-09-28). Deshalb ist sie strikt getrennt aufgebaut:
> **Abschnitt A ist für jedes Modell wahr**, die Abschnitte B–C sind als
> „nur bei `glm-5.3`" markiert. Wenn du ein Modell ohne glm2api-Proxy
> ansprichst, ignoriere B und C — sie beschreiben eine Mechanik, die es dort
> nicht gibt, und A gilt ohnehin.

## A. Tool-Namen (gilt für JEDES Modell)

- Verwende **nur** die Werkzeuge, die dir im Request deklariert sind (`read`,
  `write`, `edit`, `bash`, `glob`, `grep`, `task`, `webfetch`,
  `opencode-sessions_*`, `question`, `todowrite`).
- **`open` ist nicht dein Werkzeug** — in opencode gibt es dieses Tool nicht.
  Ebenso nicht: `open_url`, `open_ul`, `browse`, `web.run`, `web.search`,
  `execute_sandbox_code`, `code_interpreter`, `sandbox`, `run_code`. Sie
  gehören zu anderen Chat-Oberflächen, nicht zu diesem Werkzeugsatz.
- **Konsequenz:** Dateien/Verzeichnisse lesen → `read` mit **absolutem** Pfad.
  URLs abrufen → `webfetch` mit vollständiger `https://…`-URL. Befehle und
  Tests → `bash`. Niemals einen lokalen Pfad an `webfetch`, niemals `read` mit
  einer URL.
- **Bei „File not found" den Pfad korrigieren, nicht wiederholen.** Die Meldung
  enthält den naheliegenden Kandidaten („Did you mean …?") — übernimm ihn.
  Ebenso `command not found`/`Invalid argument`: das *Argument* ist falsch,
  nicht der Aufruf. Ein Call ist erst wiederholbar, wenn sich sein Argument
  geändert hat.
- **Sequenziell ausführen:** erst Ergebnis abwarten und prüfen, dann den
  nächsten Schritt. Nie zwei Calls desselben Tools parallel.
- **Absolute Pfade** für `read`/`write`/`edit` — keine relativen.
- **Keine Probe-/Platzhalter-Fetches:** `webfetch` nur mit einem konkreten, im
  Auftrag genannten Ziel. Niemals `example.com`, `raw.githubusercontent.com`
  oder andere Beispiel-URLs.

## B. glm2api-spezifisch: das stille `open`-Mapping (nur bei `glm-5.3`)

- Schreibt das Modell `open` statt `read`, schreibt der glm2api-Proxy den
  Aufruf **transparent auf `read`/`webfetch`/`bash` um** und führt ihn aus —
  der Aufruf *kann* funktionieren, obwohl der richtige Name nie benutzt wurde.
  Verlass dich nicht darauf: Wenn du `read` schreibst, steht `read` im
  Protokoll und du findest Fehler an der richtigen Stelle.
- **Bekommst du eine `[native_remap_notice]`:** dein `open`-Aufruf lief als
  `read`/`webfetch`, das Ergebnis ist **echt** und du hast es gesehen. Nutze ab
  da direkt den genannten Namen. Wiederhole `open` nicht.

## C. glm2api-spezifisch: Protokoll-Meldungen (nur bei `glm-5.3`)

- Es gibt **kein** „Tool-Limit" und keine Rundenzgrenze. Weder für die Anzahl
  der Tool-Calls noch für Tokens. Erreicht opencode die konfigurierte
  Ausgabegrenze, bricht der Turn technisch ab — du bemerkst es an deiner
  eigenen Kürze, nicht an einer Zahl.
- **Schreibe niemals „Tool-Limit erreicht", „Tokenlimit erreicht",
  „Rundenlimit" oder „keine Tools mehr"**, um eine Antwort abzukürzen. Das ist
  eine erfundene Begründung: sie beendet den Auftrag vorzeitig.
- **Drei echte Rückmeldungen im Protokoll — keine davon ist ein Limit:**
  - `[native_remap_notice]` — dein `open` lief als `read`/`webfetch`, das
    Ergebnis ist echt. Nutze ab da den genannten Namen.
  - `[blocked_tool_notice]` — dieser *bestimmte* Aufruf war nicht ausführbar
    (z. B. eine `turn*search*`-Referenz aus deiner eigenen Web-Suche — dieser
    Inhalt existiert auf dieser Maschine nicht). Sie sagt nichts über andere
    Calls desselben Namens aus.
  - `[loop_guard_notice]` — identische Calls wurden **verworfen, weil sie
    bereits liefen**. Lies das vorhandene Ergebnis; ändere das Argument, statt
    zu wiederholen.
- **Kein Aufgaben-Abandon:** Wenn ein Tool nicht existiert, ein Call verworfen
  wurde oder ein Pfad falsch war, korrigiere und mach weiter. Verlange keinen
  Neustart, wenn das Werkzeug verfügbar war.
- **Code-Ausführung & Tests ausschließlich über `bash`**
  (z. B. `python3 -m pytest tests -q`).

