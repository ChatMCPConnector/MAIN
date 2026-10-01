#!/usr/bin/env bash
# osv-install.sh: installiert osv-scanner gepinnt und pruefsummen-verifiziert.
#
# Wozu (PLAN Stufe 6a): ein CVE-Wächter für alle drei Ökosysteme aus EINEM
# Werkzeug. osv-scanner liest uv.lock, pnpm-lock.yaml und go.sum, ohne dass je
# eine Sprache extra installiert werden muss — pip-audit, govulncheck und
# pnpm audit waeren drei Werkzeuge fuer dasselbe Problem.
#
# Gepinnt auf eine Version, nicht auf "latest" (AGENTS.md §3: gepinnte Version
# im Repo + reproduzierbares Skript). Die SHA256 wird gegen die mit
# veroeffentlichte `osv-scanner_SHA256SUMS` geprueft, nicht gegen eine hier
# eingeklebte — sonst waere die Pruefung nur Dekoration.
#
# Idempotent: ist die Version schon da, passiert nichts.
#
# Aufruf:
#   ./infra/scripts/osv-install.sh
#   sudo ./infra/scripts/osv-install.sh     # wenn /usr/local/bin nicht reicht
set -euo pipefail

OSV_VERSION="v2.6.0"
BASE="https://github.com/google/osv-scanner/releases/download/${OSV_VERSION}"
ASSET="osv-scanner_linux_amd64"
DEST="${1:-/usr/local/bin/osv-scanner}"

# `osv-scanner --version` gibt „osv-scanner version: 2.6.0“ aus, nicht „v2.6.0“.
# Deshalb wird die Versionsnummer herausgefiltert statt auf exakte Gleichheit
# geprueft — sonst waere der Idempotenztest (zweiter Lauf = „schon da“) nie gruen.
have() {
  [ -x "$1" ] || return 1
  local got
  got="$("$1" --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
  [ "$got" = "${OSV_VERSION#v}" ]
}

if have "$DEST"; then
  echo "[osv] $OSV_VERSION ist bereits installiert ($DEST)"
  exit 0
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "[osv] lade $OSV_VERSION …"
curl -fsSL --retry 3 --retry-delay 2 "$BASE/$ASSET" -o "$TMP/$ASSET"
curl -fsSL --retry 3 --retry-delay 2 "$BASE/osv-scanner_SHA256SUMS" -o "$TMP/SUMS"

# Nur die Zeile fuer unser Asset vergleichen.
want="$(awk -v f="$ASSET" '$2 == f {print $1}' "$TMP/SUMS")"
[ -n "$want" ] || { echo "[osv] FEHLER: $ASSET nicht in den SHA256SUMS — Release-Format hat sich geaendert." >&2; exit 1; }
got="$(sha256sum "$TMP/$ASSET" | cut -d' ' -f1)"
if [ "$want" != "$got" ]; then
  echo "[osv] FEHLER: Pruefsumme weicht ab." >&2
  echo "  erwartet: $want" >&2
  echo "  bekommen: $got" >&2
  exit 1
fi
echo "[osv] Pruefsumme ok ($got)"

chmod 0755 "$TMP/$ASSET"
if install -m 0755 "$TMP/$ASSET" "$DEST" 2>/dev/null; then
  echo "[osv] installiert -> $DEST"
else
  echo "[osv] kein Schreibzugriff auf $DEST — bitte mit sudo wiederholen:" >&2
  echo "  sudo ./infra/scripts/osv-install.sh" >&2
  exit 1
fi
echo "[osv] Version: $("$DEST" --version 2>/dev/null | head -1)" | head -1