#!/usr/bin/env bash
# codespace-secret.sh: Codespaces-Secrets über die REST-API verwalten.
#
#   ./infra/scripts/codespace-secret.sh list              # alle Secrets + Repo-Scope
#   ./infra/scripts/codespace-secret.sh set-passphrase   # LANDSCAPE_PASSPHRASE = config/passphrase
#   ./infra/scripts/codespace-secret.sh set NAME DATEI    # beliebiges Secret aus einer Datei
#   ./infra/scripts/codespace-secret.sh delete NAME       # Secret entfernen
#
# Warum ein Skript statt Klick in der Web-UI: beim Account-Wechsel ist
# LANDSCAPE_PASSPHRASE der Fehler, der schon zweimal passiert ist — 2026-09-26
# stand dort der PAT statt des Passphrasen-Inhalts. Genau dieser Fehler ist
# harmlos (secrets.sh verwirft PAT-Kandidaten und nutzt config/passphrase aus
# dem Repo), aber er erzeugt Warnungen und verschleiert, ob der Auto-Unlock
# wirklich über den ersten Kandidaten läuft. Hier ist die Quelle eindeutig:
# der Wert kommt aus config/passphrase, nicht aus dem Kopf.
#
# Technik: GitHub erwartet den Wert libsodium-sealed-box-verschlüsselt mit dem
# Public Key aus GET /user/codespaces/secrets/public-key (X25519, 32 rohe Bytes
# base64). PyNaCl liefert crypto_box_seal über `uv run --with pynacl`, ohne
# dauerhafte Installation. Verschlüsselt wird in einer Subshell, damit der
# Klartext nie im Speicher dieser Shell liegt.
#
# Rückweg: `delete NAME` entfernt das Secret wieder; danach greift
# config/passphrase als Fallback (siehe infrastructure.md, Secrets-Modell).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly API="/user/codespaces/secrets"

need() { command -v "$1" >/dev/null 2>&1 || { echo "FEHLER: $1 fehlt."; exit 1; }; }
need gh; need uv; need python3

# Für Secrets braucht gh ein Token mit `codespace:secrets`-Scope. Reihenfolge:
# 1) der ambient Codespace-Token (GITHUB_TOKEN) — funktioniert vollständig,
#    inkl. GET …/repositories
# 2) der Bundle-PAT als Fallback — ABER: mit ihm liefert genau dieser
#    Repos-Endpunkt `total_count: 0` (live geprüft 2026-09-26), d. h. der
#    PAT-Fallback darf nie für die Scope-Abfrage verwendet werden.
ghc() {
  if [ -n "${GITHUB_TOKEN:-}${GH_TOKEN:-}" ]; then gh "$@"; return; fi
  local token_file="$HOME/.config/landscape/pat"
  if [ -s "$token_file" ]; then
    GH_TOKEN="$(cat "$token_file")" GITHUB_TOKEN="$GH_TOKEN" gh "$@"; return
  fi
  gh "$@"
}

seal() {  # seal <datei> -> druckt base64-Chiffre auf stdout
  local file="$1" key
  [ -f "$file" ] || { echo "FEHLER: $file fehlt." >&2; exit 1; }
  key="$(ghc api "$API/public-key" --jq .key)"
  [ -n "$key" ] || { echo "FEHLER: kein Public Key (Token ohne codespace:secrets?)." >&2; exit 1; }
  # Klartext kommt aus der Datei; ein abschliessender Newline wird entfernt,
  # weil die Web-UI ihn beim Einfuegen mit reinschreibt und genau er das
  # Kandidaten-Durchprobieren verunsichert.
  KEY_B64="$key" FILE="$file" uv run -q --with pynacl python3 - <<'PY'
import base64, os
from nacl.public import PublicKey, SealedBox
pk = PublicKey(base64.b64decode(os.environ["KEY_B64"]))
raw = open(os.environ["FILE"], "rb").read().rstrip(b"\n")
if not raw:
    raise SystemExit("FEHLER: Quelldatei ist leer.")
print(base64.b64encode(SealedBox(pk).encrypt(raw)).decode())
PY
}

resolve_repo_id() {  # Slug -> numerische Repo-ID (für selected_repository_ids)
  ghc api "repos/$1" --jq '.id' 2>/dev/null
}

# Scope eines bestehenden Secrets. KEIN Raten: eine leere Antwort (z. B. weil
# das Token für diesen Endpunkt zu wenig darf) würde beim PUT stillschweigend
# den Scope auf "nur dieses Repo" zurücksetzen. Lieber abbrechen und fragen.
current_scope() {  # current_scope <name> [slug-fallback]
  local name="$1" fallback="${2:-}" ids
  ids="$(ghc api "$API/$name/repositories" --jq '[.repositories[].id] | join(",")' 2>/dev/null || true)"
  if [ -z "$ids" ] && [ -n "$fallback" ]; then
    local rid; rid="$(resolve_repo_id "$fallback")"
    [ -n "$rid" ] && ids="$rid"
  fi
  [ -n "$ids" ] || { echo "FEHLER: Repo-Scope von $name nicht lesbar." >&2
                     echo "       Explizit setzen: $0 set NAME DATEI --repo owner/name" >&2
                     exit 1; }
  printf '[%s]' "$ids"
}

origin_slug() {
  git -C "$REPO_ROOT" remote get-url origin 2>/dev/null \
    | sed -E 's#.*github\.com[:/]([^/]+/[^/]+)(\.git)?#\1#; s/\.git$//'
}

cmd_list() {
  echo "Codespaces-Secrets (Sichtbarkeit/Scope):"
  local name scope
  for name in $(ghc api "$API" --jq '.secrets[].name'); do
    scope="$(ghc api "$API/$name/repositories" --jq '[.repositories[].full_name] | join(", ")' 2>/dev/null || true)"
    printf '  %-24s visibility=%-9s scope=%s\n' "$name" \
      "$(ghc api "$API/$name" --jq .visibility)" "${scope:-<nicht lesbar>}"
  done
}

cmd_set() {
  local name="$1" file="$2" repo="${3:-}" enc key_id scope
  enc="$(seal "$file")"
  key_id="$(ghc api "$API/public-key" --jq .key_id)"
  scope="$(current_scope "$name" "${repo:-$(origin_slug)}")"
  echo "Setze $name ($(wc -c < "$file" | tr -d ' ') Bytes Klartext) fuer Scope $scope …"
  ghc api --method PUT "$API/$name" --input - >/dev/null <<JSON
{"encrypted_value":"$enc","key_id":"$key_id","selected_repository_ids":$scope}
JSON
  echo "  OK. Der Wert ist verschluesselt gespeichert (Klartext nirgends gespeichert)."
  echo "  Gegenprobe: ./infra/scripts/secrets.sh status   (meldet 'OK (ein Kandidat …)')"
}

cmd_delete() {
  ghc api --method DELETE "$API/$1" >/dev/null && echo "$1 gelöscht."
}

# Repo zum Secret-Scope hinzufuegen. Wichtig fuer den Account-Wechsel: Codespaces
# werden ueber den FORK erstellt, und Codespaces-Secrets sind repo-scoped
# (visibility=selected). Ohne dieses Hinzufuegen bekommt der Codespace im Fork
# WEDER LANDSCAPE_PAT NOCH LANDSCAPE_PASSPHRASE (live geprueft 2026-09-26) — es
# laeuft dann nur ueber den Repo-Fallback bzw. die Token-Datei.
cmd_scope() {
  local name="$1" slug="${2:-}" rid
  [ -n "$slug" ] || slug="$(origin_slug)"
  [ -n "$slug" ] || { echo "FEHLER: kein Repo angegeben (owner/name)." >&2; exit 1; }
  rid="$(resolve_repo_id "$slug")"
  [ -n "$rid" ] || { echo "FEHLER: $slug nicht lesbar." >&2; exit 1; }
  if ! ghc api --method PUT "$API/$name/repositories/$rid" >/dev/null 2>&1; then
    echo "FEHLER: $name -> $slug nicht per API moeglich." >&2
    echo "       Live-Befund 2026-09-26: der ambient Codespace-Token bekommt 403" >&2
    echo "       ('not accessible by integration'), der Bundle-PAT 404 — dieser" >&2
    echo "       Endpunkt braucht ein Token mit Codespaces-Verwaltung." >&2
    echo "       Also einmalig im UI: github.com/settings/codespaces -> Secrets ->" >&2
    echo "       $name -> Selected repositories -> $slug hinzufuegen." >&2
    exit 1
  fi
  echo "$name: $slug zum Scope hinzugefuegt."
  ghc api "$API/$name/repositories" --jq '"  Scope jetzt: " + ([.repositories[].full_name] | join(", "))'
}

case "${1:-list}" in
  list)            cmd_list ;;
  set-passphrase)  cmd_set "LANDSCAPE_PASSPHRASE" "$REPO_ROOT/config/passphrase" ;;
  set)             shift
                   [ $# -ge 2 ] || { echo "Usage: $0 set NAME DATEI [--repo owner/name]"; exit 1; }
                   case "${3:-}" in --repo) [ $# -ge 4 ] || { echo "--repo braucht owner/name"; exit 1; }; cmd_set "$1" "$2" "$4" ;; "") cmd_set "$1" "$2" ;; *) echo "Unbekanntes Flag: $3"; exit 1 ;; esac ;;
  scope)           shift; [ $# -ge 1 ] || { echo "Usage: $0 scope NAME [owner/name]"; exit 1; }; cmd_scope "$1" "${2:-}" ;;
  delete)          shift; [ $# -eq 1 ] || { echo "Usage: $0 delete NAME"; exit 1; }; cmd_delete "$1" ;;
  *)               echo "Usage: $0 {list|set-passphrase|set NAME DATEI [--repo owner/name]|scope NAME [owner/name]|delete NAME}"; exit 1 ;;
esac
