#!/usr/bin/env bash
# run — harter Wall-Clock-Timeout für Kommandos, die den Agenten hängen würden.
# kill — Prozesse nach Muster beenden, ohne sich selbst zu töten.
#
# Warum es das gibt (beides live passiert, 2026-09-30):
#
#   1. `pkill -f "opencode run"` hat die aufrufende Shell mitgetroffen. -f
#      matcht die volle Kommandozeile, und die Kommandozeile der Shell, die
#      pkill aufruft, enthält das Muster selbst. Ergebnis: der Bash-Tool-Aufruf
#      beendet sich mitten im Kommando und läuft in den 120-s-Timeout.
#      → `kill` schließt sich selbst und alle Vorfahren aus.
#
#   2. Ein im Hintergrund gestartetes Kommando, das stdout/stderr nicht
#      umleitet, hält die Pipe des Bash-Tools offen. Das Tool wartet dann auf
#      Leser, die nie EOF bekommen, und der Aufruf hängt bis zum Timeout.
#      → `run` setzt die ganze Gruppe in eine eigene Session und räumt sie ab.
#
# Aufruf:
#   timeout.sh run  <sekunden> <kommando> [args...]   # 124 = Zeitüberschreitung
#   timeout.sh kill <muster>                           # -f-Semantik, selbst-sicher
#   timeout.sh selftest                                # beide Zusicherungen prüfen

set -uo pipefail
SELBST="$(readlink -f "$0")"

die() { printf 'timeout.sh: %s\n' "$1" >&2; exit "${2:-64}"; }

selbst_sicher_pids() {
  # Eigene Prozessgruppe und alle Vorfahren bis PID 1 ausschließen.
  local pid=$$
  while [ "$pid" -gt 1 ]; do
    printf '%s\n' "$pid"
    pid="$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')"
    [ -z "$pid" ] && break
  done
}

case "${1:-}" in
  run)
    [ $# -ge 3 ] || die "Aufruf: timeout.sh run <sekunden> <kommando> [args...]"
    secs="$2"; shift 2
    case "$secs" in ''|*[!0-9]*) die "Sekunden muss eine Zahl sein: '$secs'" ;; esac
    command -v timeout >/dev/null 2>&1 || die "coreutils-Timeout fehlt" 69

    out="$(mktemp)"
    # setsid -> eigene Session. --foreground ist entscheidend: ohne ihn legt
    # coreutils-timeout für das Kommando eine EIGENE Prozessgruppe an, und
    # `kill -- -$child` träfe sie nicht (genau das ließ hier zwei Waisen
    # zurück). Mit --foreground bleibt alles in unserer Gruppe.
    setsid timeout --foreground --kill-after=2 "$secs" "$@" >"$out" 2>&1 &
    child=$!

    wait "$child"
    rc=$?

    if [ "$rc" -eq 124 ]; then
      # timeout hat nur das direkte Kind bekommen (--foreground), die ganze
      # Gruppe jetzt hart.
      kill -KILL -- "-$child" 2>/dev/null
      cat "$out"
      rm -f "$out"
      die "Zeitüberschreitung nach ${secs}s: $*" 124
    fi

    # Bei Erfolg trotzdem aufräumen: sonst verwaist z.B. `cmd &` über den
    # Aufruf hinaus, und beim nächsten Mal ist unklar, wem der Prozess gehört.
    kill -TERM -- "-$child" 2>/dev/null
    cat "$out"
    rm -f "$out"
    exit "$rc"
    ;;

  kill)
    [ $# -ge 2 ] || die "Aufruf: timeout.sh kill <muster>"
    muster="$2"
    mapfile -t schutz < <(selbst_sicher_pids)

    # pgrep schließt sich selbst aus, aber NICHT die aufrufende Shell: deren
    # Kommandozeile enthält das Muster. Genau die filtern wir unten raus.
    mapfile -t kandidaten < <(pgrep -f -- "$muster" 2>/dev/null)
    [ "${#kandidaten[@]}" -eq 0 ] && die "kein Prozess passt auf: $muster" 1

    beendet=()
    for pid in "${kandidaten[@]}"; do
      [ "$pid" = "1" ] && continue
      geschuetzt=0
      for s in "${schutz[@]}"; do [ "$pid" = "$s" ] && geschuetzt=1; done
      [ "$geschuetzt" = "1" ] && continue
      beendet+=("$pid")
    done

    if [ "${#beendet[@]}" -eq 0 ]; then
      die "nur sich selbst passt auf '$muster' — bewusst nicht beendet" 1
    fi
    printf 'timeout.sh: beende %s (Muster: %s)\n' "${beendet[*]}" "$muster" >&2
    kill -TERM "${beendet[@]}" 2>/dev/null
    sleep 1
    for pid in "${beendet[@]}"; do
      kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null
    done
    exit 0
    ;;

  selftest)
    # Beweist die beiden Eigenschaften, wegen denen es dieses Skript gibt.
    # Aufruf: timeout.sh selftest
    fehl=0
    ok() { printf '  ok   %s\n' "$1"; }
    bad() { printf '  FAIL %s\n' "$1"; fehl=1; }

    printf 'selftest: %s\n' "$SELBST"

    start=$(date +%s)
    "$SELBST" run 2 sleep 30 >/dev/null 2>&1
    rc=$?
    dauer=$(( $(date +%s) - start ))
    [ "$rc" -eq 124 ] && [ "$dauer" -le 6 ] && ok "run bricht nach 2s ab (exit 124, ${dauer}s)" \
      || bad "run-Timeout falsch: rc=$rc dauer=${dauer}s"

    b=$(pgrep -c sleep 2>/dev/null || echo 0)
    "$SELBST" run 4 bash -c 'sleep 120 &' >/dev/null 2>&1
    sleep 1
    a=$(pgrep -c sleep 2>/dev/null || echo 0)
    [ "$b" = "$a" ] && ok "run hinterlaesst keine Waisen" || bad "Waisen: $b -> $a"

    out=$("$SELBST" run 10 bash -c 'echo hallo; exit 7' 2>/dev/null)
    rc=$?
    [ "$out" = "hallo" ] && [ "$rc" -eq 7 ] && ok "run reicht Ausgabe und Exit-Code durch" \
      || bad "Durchreichen: out='$out' rc=$rc"

    marker="timeout-selftest-$$"
    bash -c 'while :; do sleep 1; done' "$marker" &           # kein exec!
    ziel=$!
    sleep 0.3
    "$SELBST" kill "$marker" >/dev/null 2>&1
    sleep 0.4
    kill -0 "$ziel" 2>/dev/null && { bad "kill hat das Ziel nicht beendet"; kill -9 "$ziel"; } \
      || ok "kill beendet fremdes Ziel"
    kill -0 $$ 2>/dev/null && ok "kill hat den Aufruher nicht mitgetoetet" \
      || bad "kill hat den Aufrufer mitgetoetet"

    [ "$fehl" -eq 0 ] && printf 'selftest: alle Pruefungen ok\n' || printf 'selftest: FEHLGESCHLAGEN\n'
    exit "$fehl"
    ;;

  *)
    sed -n '2,20p' "$0" >&2
    die "Unbekannter Auftrag: '${1:-}' (erwartet: run | kill | selftest)"
    ;;
esac
