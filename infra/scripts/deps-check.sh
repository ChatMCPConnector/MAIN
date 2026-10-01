#!/usr/bin/env bash
# deps-check.sh: Dependency-Wächter für alle drei Ökosysteme (PLAN Stufe 6).
#
# Zwei Modi mit **unterschiedlicher Strenge** — das ist der Kern der Stufe:
#
#   deps-check.sh            Lockfile-Drift. HART: schlägt fehl, wenn ein
#                            Paketmanager ohne Lockfile-Update gepinnt wurde.
#                            Kostenlos, findet echte Drift, braucht kein Netz.
#
#   deps-check.sh --audit    CVE-Report. WEICH: printet Befunde, beendet sich
#                            immer mit 0. Ein CVE ohne erreichbare Codeposition
#                            darf den Agenten nicht blockieren (PLAN 6a/6c) —
#                            und ein Gate, das man umgeht, ist keins.
#
# Warum überhaupt zwei Werkzeuge statt vier (pip-audit, govulncheck, pnpm
# audit, osv-scanner): osv-scanner liest uv.lock, pnpm-lock.yaml, go.mod und
# npm-Lockfiles selbst. Ein Werkzeug, drei Ökosysteme.
#
# Aktualisierungen bleiben bewusst manuelle Entscheidung (D-12 in
# llm-proxies/glm2api/pyproject.toml: Build-Abhängigkeiten exakt gepinnt, „mit
# >= hängt der Build an der Laune des Tages"). Kein Update-Bot.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT" || exit 1

GLMAPI="llm-proxies/glm2api"
ANTIGRAVITY="llm-proxies/antigravity-proxy"
ZEROKEY="llm-proxies/zerokey"

audit=0
[ "${1:-}" = "--audit" ] && audit=1
fail=0

# --- Lockfile-Drift ---------------------------------------------------------
echo "== Lockfile-Drift =="

# Python (Root-Umgebung + Vendor). `uv lock --check` ist in uv eingebaut und
# schlaegt genau dann fehl, wenn pyproject.toml und uv.lock auseinanderlaufen —
# die haeufigste Stillstand-Rot-Quelle nach einem `uv add`.
for d in . "$GLMAPI"; do
  if [ -f "$d/uv.lock" ] && [ -f "$d/pyproject.toml" ]; then
    if out="$(cd "$d" && uv lock --check 2>&1)"; then
      echo "  OK    uv lock --check ($d)"
    else
      echo "  FEHL  uv lock --check ($d)"
      printf '%s\n' "$out" | tail -3 | sed 's/^/        /'
      echo "        -> 'cd $d && uv lock' und das Lockfile mit committen"
      fail=1
    fi
  else
    echo "  --    uebersprungen ($d: keine uv.lock/pyproject.toml)"
  fi
done

# Go: `go mod verify` prueft die Prüfsummen der Module im Cache gegen go.sum.
# Es ist **kein** Lockfile-Check — der Go-Pin steckt in go.mod (go 1.25.7),
# der Transitiv-Versionsstand in go.sum. Beides deckt der Job `antigravity`
# in CI ab (go vet/test bei genau der Go-Version aus go.mod).
if [ -f "$ANTIGRAVITY/go.sum" ]; then
  GO="$(command -v go || echo /usr/local/go/bin/go)"
  if [ -x "$GO" ]; then
    if out="$(cd "$ANTIGRAVITY" && "$GO" mod verify 2>&1)"; then
      echo "  OK    go mod verify"
    else
      echo "  FEHL  go mod verify"
      printf '%s\n' "$out" | tail -3 | sed 's/^/        /'
      fail=1
    fi
  else
    echo "  --    uebersprungen (kein go)"
  fi
fi

# JS: --frozen-lockfile schlaegt fehl, wenn package.json und Lockfile
# auseinanderlaufen. Schreibt node_modules — deshalb hier, nicht im Hook.
if [ -f "$ZEROKEY/pnpm-lock.yaml" ]; then
  if command -v pnpm >/dev/null 2>&1; then
    if out="$(cd "$ZEROKEY" && pnpm install --frozen-lockfile 2>&1)"; then
      echo "  OK    pnpm install --frozen-lockfile"
      # Zweiter Teil: schreibt jemand am Lockfile vorbei?
      if [ -n "$(git status --porcelain -- "$ZEROKEY/pnpm-lock.yaml")" ]; then
        echo "  FEHL  $ZEROKEY/pnpm-lock.yaml wurde gerade veraendert"
        echo "        -> Lockfile-Aenderung gehoert mit ins selbe Commit"
        fail=1
      fi
    else
      echo "  FEHL  pnpm install --frozen-lockfile"
      printf '%s\n' "$out" | tail -5 | sed 's/^/        /'
      echo "        -> 'cd $ZEROKEY && pnpm install' und Lockfile mit committen"
      fail=1
    fi
  else
    echo "  --    uebersprungen (kein pnpm)"
  fi
fi

# --- CVE-Report (weich) -----------------------------------------------------
if [ "$audit" -eq 1 ]; then
  echo ""
  echo "== CVE-Report (osv-scanner) =="
  if ! command -v osv-scanner >/dev/null 2>&1; then
    echo "  osv-scanner fehlt — einmalig: sudo ./infra/scripts/osv-install.sh"
    echo "  (Report-Modus: das ist kein Fehler, nur ein fehlender Befund)"
    exit "$fail"
  fi
  osv_out="$(osv-scanner scan source -r . 2>&1)"
  osv_rc=$?
  printf '%s\n' "$osv_out" | grep -vE '^Scanned |^Starting filesystem|^End status|^Scanning dir' | sed 's/^/  /' | tail -40
  echo "  --- osv-scanner beendet mit $osv_rc (0 = keine Befunde) ---"
  if [ "$osv_rc" -ne 0 ] && [ "$fail" -eq 0 ]; then
    # Absichtlich KEIN fail: ein CVE ist ein Hinweis, kein Gate (PLAN 6a).
    echo "  -> Befunde sind ein Hinweis. Updates bleiben manuelle Entscheidung"
    echo "     (D-12). Belegte, erreichbare CVE einzeln in infrastructure.md"
    echo "     vermerken statt pauschal nachzuziehen."
  fi
fi

exit "$fail"