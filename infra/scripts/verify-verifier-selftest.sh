#!/usr/bin/env bash
# D-10: der revisions-verifier braucht einen selbsttest.
#
# Bis hierher konnte niemand unterscheiden zwischen
#   (a) "der verifier laeuft die echte symptom-suite und faellt bei einem
#        echten fehler um" und
#   (b) "der verifier laeuft irgendetwas und meldet immer gruen".
# Beides sieht am exit-code nicht unterscheidbar aus.
#
# Dieser test baut eine KONTROLLIERTE regression in den translator ein
# (P-07: unterminiertes tool-markup wird nicht mehr entfernt), erwartet
# einen exit-code != 0, stellt den originalzustand wieder her und
# erwartet danach exit 0. Laeuft er durch, ist (a) belegt.
#
# Rueckweg: die backups in $BACKUP_DIR werden nach jedem schritt
# zurueckgespielt; im fehlerfall liegt der originalzustand in
# $BACKUP_DIR/translator.py.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TARGET="$ROOT/llm-proxies/glm2api/src/glm2api/services/translator.py"
BACKUP_DIR="$(mktemp -d)"
MARKER="D-10-SELBSTTEST"

cleanup() {
  if [ -f "$BACKUP_DIR/translator.py" ]; then
    cp "$BACKUP_DIR/translator.py" "$TARGET"
  fi
  rm -rf "$BACKUP_DIR"
}
trap cleanup EXIT

restore() {
  cp "$BACKUP_DIR/translator.py" "$TARGET"
}

echo "verify-verifier-selftest: 1/3 original sichern"
cp "$TARGET" "$BACKUP_DIR/translator.py"
if grep -q "$MARKER" "$TARGET"; then
  echo "FEHLER: der marker ist noch im Quelltext — der letzte Lauf wurde nicht zurueckgesetzt." >&2
  exit 2
fi

echo "verify-verifier-selftest: 2/3 kontrollierte Regression einbauen (P-07 abgeschaltet)"
python3 - "$TARGET" "$MARKER" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
marker = sys.argv[2]
text = path.read_text(encoding="utf-8")
old = "        full_text, markup_fragments = strip_unterminated_markup(full_text)"
new = f"        full_text, markup_fragments = full_text, []  # {marker}"
if text.count(old) != 1:
    raise SystemExit("erwartete Stelle nicht gefunden — der selbsttest ist veraltet")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
PY

set +e
bash "$ROOT/infra/scripts/validate-revision.sh" >"$BACKUP_DIR/regression.log" 2>&1
regression_status=$?
set -e

if [ "$regression_status" -eq 0 ]; then
  echo "FEHLER: der verifier meldete GRUEN bei kaputtem kernsymptom (exit 0)." >&2
  echo "        Ein Verifier, der immer gruen sagt, ist wertlos." >&2
  echo "--- Log ---" >&2
  cat "$BACKUP_DIR/regression.log" >&2
  exit 1
fi
echo "  ok: der verifier faellt bei kaputtem kernsymptom um (exit $regression_status)"
grep -q "FAILED" "$BACKUP_DIR/regression.log" \
  || { echo "FEHLER: der Abbruch kam nicht aus der symptom-suite." >&2; exit 1; }
echo "  ok: der Abbruch stammt aus der symptom-suite"

echo "verify-verifier-selftest: 3/3 original wiederherstellen und gruenen Zustand pruefen"
restore
bash "$ROOT/infra/scripts/validate-revision.sh" >"$BACKUP_DIR/repaired.log" 2>&1 \
  || { echo "FEHLER: nach dem Zuruecksetzen meldet der verifier einen Fehler." >&2; cat "$BACKUP_DIR/repaired.log" >&2; exit 1; }
echo "  ok: der originalzustand ist gruen (exit 0)"

echo "verify-verifier-selftest: BESTANDEN"
