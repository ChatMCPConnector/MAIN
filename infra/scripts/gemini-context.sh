#!/usr/bin/env bash
# gemini-context.sh: bindet die Gemini CLI an AGENTS.md.
#
# Kanonisch: dieses Skript ist der einzige Weg. setup.sh ruft es bei jedem neuen
# Codespace automatisch auf (idempotent).
#
# Warum ueberhaupt noetig, wenn es GEMINI.md nicht mehr gibt:
# Gemini CLI liest per Default NUR `GEMINI.md`. Der Wunsch, einen einzigen
# Regelsatz im Repo zu pflegen (`AGENTS.md` als Referenz fuer alle Clients),
# steht im Default-Dateinamen nicht. Der PR, der AGENTS.md als Default
# aufnehmen wollte (google-gemini/gemini-cli#24913), wurde am 2026-05-12 OHNE
# Merge geschlossen; Issue #28227 bestaetigt das fuer den aktuellen Stand:
# `DEFAULT_CONTEXT_FILENAME = 'GEMINI.md'` in packages/core/src/tools/
# memoryTool.ts. Ohne diese Einstellung laeuft Gemini CLI also mit LEEREM
# Kontext -- kein Fehler, keine Warnung, einfach keine Repo-Regeln (Save-
# Pflicht inklusive).
#
# Der dokumentierte Ausweg ist `context.fileName` in der User-Config
# (`~/.gemini/settings.json`, geminicli.com/docs/cli/gemini-md/). Damit bleibt
# das Repo bei genau einer Agenten-Datei und die Client-Zuordnung liegt in
# $HOME statt als Kopie im Repo -- die Kopie war die Fehlerquelle (zwei lange
# Regeltexte driften auseinander, siehe infrastructure.md, Abschnitt
# "Agenten-Anweisungen").
#
# Copilot liest weiterhin `.github/copilot-instructions.md`; das ist eine eigene
# Datei im Repo und wird hier nicht angefasst.
set -euo pipefail

CONFIG_DIR="${HOME}/.gemini"
CONFIG_FILE="$CONFIG_DIR/settings.json"
CONTEXT_FILES='["AGENTS.md"]'

usage() {
  cat <<'EOF'
gemini-context.sh: Gemini CLI auf AGENTS.md zeigen lassen (Nutzerentscheidung
2026-09-27: im Repo gibt es nur AGENTS.md, keine Client-Kopien).

  apply     (Default) ~/.gemini/settings.json setzen: context.fileName=["AGENTS.md"]
            Bestehende Schluessel in der Datei bleiben erhalten.
  status    Anzeigen, was aktuell eingestellt ist (Exit 1, wenn AGENTS.md fehlt).
  unapply   context.fileName wieder entfernen (zurueck auf Gemini-CLI-Default).
EOF
}

gemini_installed() {
  command -v gemini >/dev/null 2>&1 || [ -x "${HOME}/.local/bin/gemini" ] \
    || [ -d "${HOME}/.local/share/gemini" ]
}

# Setzt bzw. ersetzt context.fileName, ohne den Rest der Datei anzufassen.
# Bei kaputter Datei wird nicht geraten, sondern abgebrochen -- ein Backup
# entsteht vorher, damit die Reparatur moeglich bleibt.
apply() {
  mkdir -p "$CONFIG_DIR"

  if [ -f "$CONFIG_FILE" ]; then
    if grep -q '"AGENTS.md"' "$CONFIG_FILE" \
       && python3 -c 'import json,sys; c=json.load(open(sys.argv[1])).get("context",{}).get("fileName"); sys.exit(0 if c==["AGENTS.md"] else 1)' "$CONFIG_FILE" 2>/dev/null; then
      echo "  Gemini-CLI: context.fileName=[AGENTS.md] (bereits gesetzt)"
      return 0
    fi
    cp -n "$CONFIG_FILE" "$CONFIG_FILE.bak" 2>/dev/null || true
  else
    printf '{\n  "context": {\n    "fileName": %s\n  }\n}\n' "$CONTEXT_FILES" > "$CONFIG_FILE"
    echo "  Gemini-CLI: ~/.gemini/settings.json neu angelegt (context.fileName=[AGENTS.md])"
    return 0
  fi

  if ! python3 - "$CONFIG_FILE" "$CONTEXT_FILES" <<'PYEOF'
import json, sys

path, ctx = sys.argv[1], sys.argv[2]
try:
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("settings.json ist kein Objekt")
except Exception as e:                      # noqa: BLE001 - Absicht: nicht raten
    sys.exit(f"gemini-context: {path} nicht lesbar ({e}) - nicht ueberschrieben, "
             f"Blick in {path}.bak")

data.setdefault("context", {})["fileName"] = json.loads(ctx)
with open(path, "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")
PYEOF
  then
    return 1
  fi
  echo "  Gemini-CLI: context.fileName=[AGENTS.md] in ~/.gemini/settings.json gesetzt"
}

status() {
  if [ ! -f "$CONFIG_FILE" ]; then
    echo "  FEHLT: $CONFIG_FILE"
    return 1
  fi
  if python3 -c 'import json,sys; c=json.load(open(sys.argv[1])).get("context",{}).get("fileName"); sys.exit(0 if c==["AGENTS.md"] else 1)' "$CONFIG_FILE" 2>/dev/null; then
    echo "  OK: context.fileName=[AGENTS.md]"
  else
    echo "  FALSCH: context.fileName ist nicht [AGENTS.md] (Rest der Datei unveraendert)"
    return 1
  fi
  if gemini_installed; then
    echo "  Gemini CLI installiert -> liest ab jetzt AGENTS.md."
  else
    echo "  Gemini CLI nicht installiert (Konfiguration liegt trotzdem korrekt bereit)."
  fi
}

unapply() {
  [ -f "$CONFIG_FILE" ] || { echo "  nichts zu tun ($CONFIG_FILE fehlt)"; return 0; }
  python3 - "$CONFIG_FILE" <<'PYEOF' || return 1
import json, sys

path = sys.argv[1]
with open(path) as f:
    data = json.load(f)
ctx = data.get("context", {})
ctx.pop("fileName", None)
if ctx:
    data["context"] = ctx
else:
    data.pop("context", None)
with open(path, "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")
PYEOF
  echo "  context.fileName entfernt - Gemini CLI laeuft wieder mit GEMINI.md als Default."
}

case "${1:-apply}" in
  apply)   apply ;;
  status)  status ;;
  unapply) unapply ;;
  -h|--help|help) usage ;;
  *) usage; exit 2 ;;
esac
