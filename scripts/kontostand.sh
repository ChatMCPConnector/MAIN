#!/usr/bin/env bash
# kontostand.sh: minimaler Collector für Kontostand/Verbrauch (Spec: work/docs/Kontostand.md).
# Bevorzugt direkten API-Abruf mit System Access Token, kein dauerhafter Browser.
#
#   ./scripts/kontostand.sh            # abrufen + cachen + zwei Werte anzeigen
#   ./scripts/kontostand.sh --cached   # nur letzten Cache-Stand anzeigen
#
# Konfiguration (Env oder .env):
#   SYSTEM_ACCESS_TOKEN   Pflicht für Abruf (nie loggen, nie committen).
#   KONTOSTAND_HOST       Default: https://new.xinjianya.top (unverifiziert, siehe Spec Phase 1).
#   KONTOSTAND_DIVISOR    Umrechnung Rohwert -> Anzeigewert. NUR setzen wenn per Spec
#                         Phase 2 verifiziert, sonst bleiben balance/consumption null.
#
# Fehlerverhalten: nie 0 anzeigen. Bei Fehler letzten Stand behalten, Exit 1.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CACHE="$ROOT/.runtime/kontostand.json"
HOST="${KONTOSTAND_HOST:-https://new.xinjianya.top}"
DIVISOR="${KONTOSTAND_DIVISOR:-}"

token="${SYSTEM_ACCESS_TOKEN:-}"
if [ -z "$token" ] && [ -f "$ROOT/.env" ]; then
  token="$(grep -E '^SYSTEM_ACCESS_TOKEN=' "$ROOT/.env" | tail -1 | cut -d= -f2-)"
fi

de_fmt() { # 4384.43 -> 4384,43 (Anzeige only)
  sed 's/\./,/'
}

show_cached() {
  [ -f "$CACHE" ] || { echo "Kein Cache ($CACHE). Erst Abruf versuchen."; return 1; }
  local b c s u
  b="$(jq -r '.balance // empty' "$CACHE" 2>/dev/null)"
  c="$(jq -r '.consumption // empty' "$CACHE" 2>/dev/null)"
  s="$(jq -r '.status // "?"' "$CACHE" 2>/dev/null)"
  u="$(jq -r '.updated_at // "?"' "$CACHE" 2>/dev/null)"
  if [ -n "$b" ] && [ -n "$c" ]; then
    echo "Kontostand: $(printf '%s' "$b" | de_fmt)"
    echo "Verbrauch:    $(printf '%s' "$c" | de_fmt)"
  else
    echo "Noch keine verifizierte Umrechnung (DIVISOR fehlt)."
    echo "Rohwerte: quota=$(jq -r '.quota_raw // "?"' "$CACHE"), used_quota=$(jq -r '.used_quota_raw // "?"' "$CACHE")"
  fi
  echo "(Stand: $u, Status: $s)"
}

if [ "${1:-}" = "--cached" ]; then show_cached; exit $?; fi

[ -n "$token" ] || { echo "FEHLER: SYSTEM_ACCESS_TOKEN fehlt (Env oder .env)."; show_cached 2>/dev/null; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "FEHLER: jq fehlt."; exit 1; }

tmp="$(mktemp)"; trap "rm -f '$tmp'" EXIT
code="$(curl -fsS -m 20 -o "$tmp" -w '%{http_code}:%{content_type}' \
  -H "Authorization: Bearer $token" -H 'Accept: application/json' \
  "$HOST/api/user/self" 2>/dev/null)" || code="000:"
http="${code%%:*}"; ctype="${code#*:}"

fail() { # $1 = Grund; letzten Stand behalten, nie 0 ausgeben
  echo "FEHLER: $1"
  if [ -f "$CACHE" ]; then echo "--- letzter Stand ---"; show_cached; else echo "(noch kein Cache vorhanden)"; fi
  exit 1
}

[ "$http" = "200" ] || fail "HTTP $http von $HOST/api/user/self"
case "$ctype" in *json*) ;; *) fail "kein JSON (content-type=$ctype, evtl. Cloudflare/Login-Seite)";; esac
quota="$(jq -r '.quota // empty' "$tmp" 2>/dev/null)"
used="$(jq -r '.used_quota // empty' "$tmp" 2>/dev/null)"
[ -n "$quota" ] && [ -n "$used" ] || fail "Antwort ohne quota/used_quota"

now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
if [ -n "$DIVISOR" ]; then
  bal="$(awk -v q="$quota" -v d="$DIVISOR" 'BEGIN{printf "%.2f", q/d}')"
  con="$(awk -v q="$used" -v d="$DIVISOR" 'BEGIN{printf "%.2f", q/d}')"
  status="ok"
else
  bal="null"; con="null"; status="conversion_unverified"
fi
mkdir -p "$(dirname "$CACHE")"
jq -n --argjson q "$quota" --argjson u "$used" --argjson b "$bal" --argjson c "$con" \
  --arg s "$status" --arg t "$now" --arg h "$HOST" \
  '{balance:$b, consumption:$c, quota_raw:$q, used_quota_raw:$u, updated_at:$t, status:$s, host:$h}' > "$CACHE.tmp" \
  && mv "$CACHE.tmp" "$CACHE"
show_cached
[ "$status" = "ok" ] || exit 2 # Abruf ok, Umrechnung noch unverifiziert
