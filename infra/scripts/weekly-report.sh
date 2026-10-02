#!/usr/bin/env bash
# weekly-report.sh — der Wochenbericht (PLAN Stufe 5, Weg C).
#
# Warum dieser Weg und kein Live-CI: ein Live-Job in GitHub bräuchte echte
# Zugangsdaten als Repository-Secrets — und die gehören bei einem Repo, das
# mehrere eigene Accounts teilt, genau *einem* Account. Der Code-Check in CI
# bleibt davon unberührt (jeder Push, Sekunden, kein Secret); nur die Aussage
# über die **laufende** Kette und die **echten Provider** kommt hierher, aus
# dem Codespace heraus. Nichts davon ist Flakes-Gefahr ausgesetzt, weil es
# nicht bei jedem Push läuft.
#
# Der Bericht geht nach Drive (`status/`), nicht ins Git: ein Wochenbericht im
# Repo wäre Commit-Rauschen, Drive ist die einzige Kopie ausserhalb GitHub
# und hat schon eine Rotation. Wird nichts committet — der Bericht ist
# Beobachtung, kein Arbeitsstand.
#
# Aufruf:
#   ./infra/scripts/weekly-report.sh              # einmal ausfuehren
#   ./infra/scripts/weekly-report.sh install-cron # woechentlich (Mo 07:05 UTC)
#   ./infra/scripts/weekly-report.sh remove-cron
#   ./infra/scripts/weekly-report.sh cron-status
#
# read-only gegenüber dem Repo: schreibt nur den Bericht (nach .runtime/ und
# Drive), committet nichts, startet nichts.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT" || exit 1

TIMEOUT="$REPO_ROOT/infra/scripts/timeout.sh"
REPORT_DIR="$REPO_ROOT/.runtime/reports"
REMOTE_DIR="status"
CRON_MARK="weekly-report.sh"
# Montag 07:05 UTC. Nicht auf :00 und nicht auf :17 (das ist der deps-audit
# Cron desselben Repos) — die minutes sind Absicht gegen Cron-Staus.
CRON_LINE="5 7 * * 1 cd $REPO_ROOT && $TIMEOUT run 600 bash $REPO_ROOT/infra/scripts/$CRON_MARK >> /tmp/weekly-report.log 2>&1"

cron_entry() { crontab -l 2>/dev/null | grep -F "$CRON_MARK" || true; }

case "${1:-run}" in
  install-cron)
    if [ -z "$(cron_entry)" ]; then
      ( crontab -l 2>/dev/null; echo "$CRON_LINE" ) | crontab - || {
        echo "FEHLER: crontab nicht schreibbar." >&2; exit 1; }
      echo "[report] Cron eingerichtet: $CRON_LINE"
    else
      echo "[report] Cron ist bereits eingerichtet:"
      cron_entry
    fi
    echo "[report] Hinweis: laeuft nur solange dieser Codespace laeuft. Codespaces"
    echo "         sind fluechtig — das ist der Grund, warum der Bericht nach Drive"
    echo "         geht und nicht nur lokal liegt."
    exit 0
    ;;
  remove-cron)
    if [ -n "$(cron_entry)" ]; then
      crontab -l 2>/dev/null | grep -vF "$CRON_MARK" | crontab -
      echo "[report] Cron entfernt."
    else
      echo "[report] Kein Cron dieser Art eingerichtet."
    fi
    exit 0
    ;;
  cron-status)
    if [ -n "$(cron_entry)" ]; then
      echo "[report] Cron AKTIV:"; cron_entry
    else
      echo "[report] Cron nicht eingerichtet — ./infra/scripts/$CRON_MARK install-cron"
    fi
    exit 0
    ;;
  run) ;;
  *) echo "Aufruf: $0 [run|install-cron|remove-cron|cron-status]" >&2; exit 2 ;;
esac

mkdir -p "$REPORT_DIR" || exit 1
TS="$(date -u '+%Y-%m-%d %H:%M UTC')"
WEEK="$(date -u '+%G-W%V')"
FILE="$REPORT_DIR/$WEEK.md"
hard_fail=0

section() { printf '\n## %s\n\n' "$1" >>"$FILE"; }
# Die Markdown-Codezaeune als Oktal-Escape statt als Backtick-Literal: drei
# Backticks in einfachen Anfuehrungszeichen meldet shellcheck als SC2016
# („Expressions don't expand in single quotes“) — formally richtig, weil der
# Shell inside single quotes auch keine Backtick-Substitution macht, hier aber
# genau das gewollt ist (die Ausgabe soll Backticks *enthalten*). So bleibt
# das Baseline-Gate fuer echte Befunde frei.
FENCE="$(printf '\140\140\140')"
code() { printf '%s\n%s\n%s\n\n' "$FENCE" "$1" "$FENCE" >>"$FILE"; }

{
  echo "# Wochenbericht $WEEK"
  echo
  echo "- Zeitpunkt: $TS"
  echo "- Commit: $(git rev-parse --short HEAD) — $(git log -1 --pretty=%s | cut -c1-70)"
  echo "- Erzeugt von: \`infra/scripts/$CRON_MARK\` (PLAN Stufe 5, Weg C)"
} >>"$FILE"

# --- 1. Die laufende Kette --------------------------------------------------
section "1. Kette (verify-codespace.sh, chain-Modus)"
out="$("$TIMEOUT" run 300 bash "$REPO_ROOT/infra/scripts/verify-codespace.sh" 2>&1)"
rc=$?
# Die Zusammenfassungszeile zuerst — sie ist das, was man nach drei Monaten
# zuerst lesen will; ein blosser `tail` schoebe sie aus dem Bericht.
sum="$(printf '%s\n' "$out" | grep -E '^Ergebnis:' | tail -1)"
code "$sum
$(printf '%s\n' "$out" | tail -22)"
if [ "$rc" -ne 0 ]; then hard_fail=1; fi

# --- 2. Provider echt --------------------------------------------------------
section "2. Provider (keys.sh doctor — echte Calls)"
out="$("$TIMEOUT" run 180 bash "$REPO_ROOT/infra/scripts/keys.sh" doctor 2>&1)"
rc=$?
code "$(printf '%s\n' "$out" | tail -20)"
if [ "$rc" -ne 0 ]; then hard_fail=1; fi

# --- 3. Abhaengigkeiten ------------------------------------------------------
section "3. Dependencies (Lockfile-Drift hart, CVE-Report weich)"
out="$("$TIMEOUT" run 400 bash "$REPO_ROOT/infra/scripts/deps-check.sh" --audit 2>&1)"
code "$(printf '%s\n' "$out" | grep -vE '^  Scanned ' | tail -30)"
if printf '%s' "$out" | grep -q '^  FEHL'; then hard_fail=1; fi

# --- 4. Drive-Backup ---------------------------------------------------------
section "4. Google-Drive-Backup"
out="$("$TIMEOUT" run 180 bash "$REPO_ROOT/infra/scripts/gdrive-backup.sh" status 2>&1)"
rc=$?
code "$(printf '%s\n' "$out" | tail -15)"
if [ "$rc" -ne 0 ]; then hard_fail=1; fi

# --- 5. Urteil ---------------------------------------------------------------
if [ "$hard_fail" -eq 0 ]; then
  verdict="gruen — Kette, Provider, Lockfiles und Backup stehen"
else
  verdict="ROT — mindestens eine harte Pruefung oben ist fehlgeschlagen"
fi
{
  echo "## Urteil"
  echo
  echo "**$verdict**"
  echo
  echo "CVE-Befunde sind absichtlich kein Urteil (PLAN 6a): Updates bleiben"
  echo "manuelle Entscheidung (D-12)."
} >>"$FILE"

echo "Bericht geschrieben: $FILE"
echo ""

# Hochladen. Fehler ist kein harter Fehler: der Bericht existiert lokal, und
# ein Drive-Problem soll ihn nicht unlesbar machen.
if rclone listremotes 2>/dev/null | grep -qx 'gdrive:'; then
  if "$TIMEOUT" run 300 rclone copyto "$FILE" "gdrive:${REMOTE_DIR}/$WEEK.md" >/dev/null 2>&1; then
    echo "[report] hochgeladen -> gdrive:${REMOTE_DIR}/$WEEK.md"
  else
    echo "[report] WARN: Upload fehlgeschlagen — Bericht liegt lokal unter $FILE"
  fi
else
  echo "[report] WARN: kein rclone-Remote 'gdrive' — Bericht bleibt lokal"
fi

echo ""
echo "Urteil: $verdict"
[ "$hard_fail" -eq 0 ]