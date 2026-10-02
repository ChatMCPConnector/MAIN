#!/usr/bin/env bash
# Shellcheck-Gate gegen eine eingefrorene Baseline (Datei: shellcheck-check.sh)
#
# ACHTUNG fuer Bearbeiter: jeder Kommentar, der mit dem Wort `shellcheck`
# beginnt, ist fuer das Werkzeug selbst eine *Direktive* und erzeugt SC1073
# „Couldn't parse this shellcheck directive“. Beim Bauen dieses Gates ist das
# dreimal passiert — zweimal hier, einmal in setup.sh. Kommentarzeilen deshalb
# immer mit einem anderen Wort beginnen lassen.
#
# Warum eine Baseline und nicht "alles gruen" (PLAN Stufe 4): `bash -n` fängt
# nur Syntax. Shellcheck findet echte Shell-Fehler — unquoted $var,
# set -u-Verstöße, fehlende cd-Prüfung, Subshell-Fallen. In den Shell-Skripten
# liegen aber Hunderte Befunde, und ein Gate, das man nicht in einem Durchgang
# beheben kann, wird mit `|| true` entschärft und ist dann wertlos. Die
# Baseline ist der Weg dazwischen: **heute eingefroren, alles neue rot.**
#
# Zwei Entscheidungen, die man kennen sollte:
#
# 1. Normalisiert ohne Zeilennummer. Eine Baseline mit Zeilennummern wird bei
#    jeder harmlosen Einfuegung eines Leerzeilenkommentars rot, also verraet
#    sie ihre eigentliche Aufgabe. Format: `<pfad> | SC<nr> | <Meldung>`.
#    Dadurch wird derselbe Befund in derselben Datei auch nach dem
#    Verschieben akzeptiert — das ist der bewusst in Kauf genommene Preis.
#
# 2. Nur committete Skripte (`git ls-files`). Untracked Dateien wuerden die
#    Baseline ohne Nutz verschieben.
#
# Aufruf:
#   ./infra/scripts/shellcheck-check.sh            # pruefen (Exit 1 bei NEU)
#   ./infra/scripts/shellcheck-check.sh --update   # Baseline neu einfrieren
#
# read-only: schreibt nur bei --update genau eine Datei im Repo
# (infra/scripts/shellcheck-baseline.txt) und sonst nichts.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT" || exit 1

BASELINE="infra/scripts/shellcheck-baseline.txt"
UPDATE=0
[ "${1:-}" = "--update" ] && UPDATE=1

if ! command -v shellcheck >/dev/null 2>&1; then
  # Kein harter Fehler: die Basis-Installation (setup.sh) holt shellcheck aus
  # apt, aber ein Codespace ohne sudo soll daran nicht scheitern. Der Verify-
  # Check meldet das Fehlen getrennt, damit es nicht still bleibt.
  echo "WARN: shellcheck nicht installiert — Pruefung uebersprungen (setup.sh: apt shellcheck)"
  exit 0
fi

mapfile -t scripts < <(git ls-files '*.sh')

if [ "${#scripts[@]}" -eq 0 ]; then
  echo "Keine committeten .sh-Dateien."
  exit 0
fi

# Ausgabeformat -f gcc: eine Zeile pro Befund, maschinenlesbar:
#   pfad:zeile:spalte: schwere: meldung [SC1234]
# 2>&1, weil shellcheck bei Parse-Fehlern nach stderr schreibt. Die Normalform
# ist `<pfad> | <schwere> | <meldung> | <SC-Code>` — ohne Zeile/Spalte, damit
# eine harmlose Zeilenverschiebung die Baseline nicht sprengt.
collect() {
  shellcheck -f gcc --shell=bash "${scripts[@]}" 2>&1 \
    | sed -n 's#^\(.*\):[0-9][0-9]*:[0-9][0-9]*: \([a-z]*\): \(.*\) \[\(SC[0-9]*\)\]$#\1 | \2 | \3 | \4#p' \
    | sort -u
}

aktuell="$(collect)"

if [ "$UPDATE" -eq 1 ]; then
  printf '%s\n' "$aktuell" > "$BASELINE"
  n=$(printf '%s' "$aktuell" | grep -c . || true)
  echo "Baseline neu: $BASELINE ($n Befunde, shellcheck $(shellcheck --version | awk '/^version:/ {print $2}'))"
  exit 0
fi

if [ ! -f "$BASELINE" ]; then
  echo "FEHLT: $BASELINE — einmalig erzeugen:"
  echo "  ./infra/scripts/shellcheck-check.sh --update"
  exit 1
fi

neu="$(
  comm -13 \
    <(sort -u "$BASELINE") \
    <(printf '%s\n' "$aktuell" | sort -u)
)"

if [ -z "$neu" ]; then
  n=$(printf '%s\n' "$aktuell" | grep -c . || true)
  b=$(grep -c . "$BASELINE" || true)
  echo "shellcheck: keine neuen Befunde ($n aktuell, $b in der Baseline, Version $(shellcheck --version | awk '/^version:/ {print $2}'))"
  exit 0
fi

echo "NEUE Shellcheck-Befunde (nicht in $BASELINE):"
printf '%s\n' "$neu"
echo ""
echo "Entweder beheben — oder, wenn der Befund bewusst bleibt, die Baseline"
echo "aktualisieren: ./infra/scripts/shellcheck-check.sh --update"
exit 1