#!/usr/bin/env bash
# keys.sh: Key-Dateien unter ~/.config/landscape/ verwalten.
#
# Problem (2026-09-26): .opencode/opencode.json referenziert Provider-Keys als
#   "apiKey": "{file:~/.config/landscape/nvidia-nim.key}"
# Fehlt die Datei, verweigert opencode den Start komplett:
#   Configuration is invalid ...: bad file reference: "{file:...}" ... does not exist
# Ein kaputtes Secret-Setup (falsche Passphrase, fehlendes Bundle) hat damit den
# kompletten Editor blockiert — die eigentliche Ursache war nur ein nicht
# wiederhergestellter API-Key.
#
# Vertrag:
#   ensure  garantiert, dass jede in opencode.json referenzierte Key-Datei
#           existiert (echter Key oder leerer Platzhalter). opencode startet
#           dadurch IMMER, auch wenn der Unlock fehlschlägt. Aufgerufen von
#           setup.sh, opencode-server.sh und dem opencode-Wrapper.
#   status  zeigt je Key-Datei: vorhanden/leer/fehlt (nie den Inhalt).
#   doctor  prüft zusätzlich live gegen die Provider-APIs, welcher Key wirklich
#           funktioniert (401 vs. 200 vs. Netzwerkfehler).
#   restore probiert erst secrets.sh unlock, falls die Datei fehlt.
#
#   ./infra/scripts/keys.sh ensure [--quiet]
#   ./infra/scripts/keys.sh status
#   ./infra/scripts/keys.sh doctor
#   ./infra/scripts/keys.sh restore
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KEYDIR="$HOME/.config/landscape"

# datei|provider|endpoint|modell  (Trenner "|" — URLs enthalten ":")
KEYS=(
  "nvidia-nim.key|nvidia|https://integrate.api.nvidia.com/v1|z-ai/glm-5.3"
  "xinjianya.key|xinjianya|https://xn--kiv260fv3i.cn/v1|gpt-5.6-sol"
)

# Dateien, die opencode.json per {file:...} referenziert. Muss synchron zu
# .opencode/opencode.json bleiben — dort nach "{file:" greppen und hier nachtragen.
referenced_files() {
  local cfg="$REPO_ROOT/.opencode/opencode.json"
  [ -f "$cfg" ] || return 0
  # "~" bewusst NICHT mit sed strippen: `s|^{file:~||` löscht in GNU-sed nur
  # das "~" und lässt ein führendes "/" stehen. "~" erst in bash auflösen.
  grep -o '{file:[^}]*}' "$cfg" 2>/dev/null | sed 's|{file:||; s|}$||' | sort -u
}

state_of() {
  local f="$KEYDIR/$1"
  if [ ! -f "$f" ]; then echo "fehlt"; return; fi
  if [ -s "$f" ]; then echo "ok"; else echo "leer"; fi
}

# Legt fehlende Dateien als leere Platzhalter an. Bestehende (echte) Keys werden
# nie angefasst. Exit-Code immer 0: darf opencode-Start nie blockieren.
cmd_ensure() {
  local quiet=0 created=0 f
  [ "${2:-}" = "--quiet" ] && quiet=1
  mkdir -p "$KEYDIR" && chmod 700 "$KEYDIR" 2>/dev/null
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    f="${f/#\~/$HOME}"
    if [ ! -f "$f" ]; then
      : > "$f"
      chmod 600 "$f" 2>/dev/null
      created=$((created + 1))
      [ "$quiet" -eq 0 ] && echo "    Platzhalter angelegt: $f"
    fi
  done < <(referenced_files)
  if [ "$created" -gt 0 ] && [ "$quiet" -eq 0 ]; then
    echo "    -> opencode startet jetzt, der Provider-Aufruf scheitert aber (401)."
    echo "    -> Keys holen: ./infra/scripts/keys.sh restore   (bzw. secrets.sh unlock)"
  fi
  return 0
}

cmd_status() {
  echo "Key-Dateien in $KEYDIR:"
  local entry name provider endpoint model st
  for entry in "${KEYS[@]}"; do
    IFS="|" read -r name provider endpoint model <<< "$entry"
    st="$(state_of "$name")"
    case "$st" in
      ok)   printf '  %-18s %-10s %s (%s)\n' "$name" "[OK]" "$provider" "$model" ;;
      leer) printf '  %-18s %-10s %s (%s)\n' "$name" "[LEER]" "$provider" "$model" ;;
      *)    printf '  %-18s %-10s %s (%s)\n' "$name" "[FEHLT]" "$provider" "$model" ;;
    esac
  done
  # Dateien, die opencode.json referenziert, aber nicht in KEYS stehen
  local f extra=0
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    f="${f/#\~/$HOME}"
    grep -q "^$(basename "$f")|" <<<"$(printf '%s\n' "${KEYS[@]}")" && continue
    extra=1
    printf '  %-18s %-10s (nur in opencode.json referenziert)\n' "$(basename "$f")" "[$(state_of "$(basename "$f")")]"
  done < <(referenced_files)
  [ "$extra" -eq 0 ] || true
  echo ""
  echo "Fix bei [LEER]/[FEHLT]: ./infra/scripts/keys.sh restore   (Live-Check: keys.sh doctor)"
}

# Live-Test: 1 Token anfordern. Es werden Status UND Body ausgewertet, weil
# "403" je nach Provider völlig unterschiedlich bedeutet: echter Auth-Fehler
# (JSON) vs. Cloudflare-Bot-Challenge (HTML) — letzteres darf man nicht als
# "Key kaputt" melden. Timeout 90s: NIM-Modelle brauchen beim Kaltstart gut
# eine Minute (gemessen: 57s bis zum ersten Token).
UA_BROWSER='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36'

probe() {
  local endpoint="$1" key="$2" model="$3" out code body
  out="$(mktemp)"
  if [ -z "$key" ]; then rm -f "$out"; echo "NO-KEY"; return; fi
  code="$(curl -s -o "$out" -w '%{http_code}' -m 90 \
    -H "Authorization: Bearer $key" -H "Content-Type: application/json" \
    -H "User-Agent: $UA_BROWSER" \
    -d "{\"model\":\"$model\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":1}" \
    "$endpoint/chat/completions" 2>/dev/null)"
  [ -n "$code" ] || code="000"
  body="$(head -c 400 "$out" 2>/dev/null | tr -d '\n\r')"
  rm -f "$out"
  echo "$code|$body"
}

# Kurzer Erreichbarkeitstest, um "Netz weg" von "Key falsch" zu trennen.
reachable() {
  local endpoint="$1" code
  code="$(curl -s -o /dev/null -w '%{http_code}' -m 15 "$endpoint/models" 2>/dev/null)"
  [ -n "$code" ] && [ "$code" != "000" ] && return 0
  return 1
}

cmd_doctor() {
  local entry name provider endpoint model st key res code body failed=0
  for entry in "${KEYS[@]}"; do
    IFS="|" read -r name provider endpoint model <<< "$entry"
    st="$(state_of "$name")"
    printf '%-10s %-18s ' "$provider" "$name"
    if [ "$st" = "fehlt" ]; then echo "FEHLT   -> ./infra/scripts/keys.sh restore"; failed=1; continue; fi
    key="$(cat "$KEYDIR/$name" 2>/dev/null || true)"
    if [ -z "$key" ]; then echo "LEER    -> kein Key hinterlegt (Platzhalter)"; failed=1; continue; fi
    if ! reachable "$endpoint"; then
      echo "NETZ    -> $endpoint nicht erreichbar (Key ungeprueft)"; failed=1; continue
    fi
    res="$(probe "$endpoint" "$key" "$model")"
    code="${res%%|*}"; body="${res#*|}"
    case "$code" in
      200)
        echo "OK      (HTTP 200, $model antwortet)"
        ;;
      401)
        echo "AUTH-FAIL (401) -> Key falsch/abgelaufen"; failed=1
        ;;
      403)
        # Cloudflare-Challenge ist KEIN Key-Problem: gut und schlecht bekommen
        # denselben 403. Das muss der Status-Report auch so sagen.
        if printf '%s' "$body" | grep -qiE 'just a moment|cf-chl|challenge-platform|cf-mitigated|cloudflare'; then
          echo "CLOUDFLARE (403 HTML-Challenge) -> Key per curl nicht pruefbar;"
          echo "                            Bot-Schutz blockt den Weg, den auch opencode nimmt."
        else
          echo "AUTH-FAIL (403) -> Key abgelehnt oder kein Zugriff auf $model"; failed=1
        fi
        ;;
      404)
        echo "HTTP 404 -> Endpoint oder Modell $model stimmt nicht (Key evtl. ok)"; failed=1
        ;;
      000)
        echo "TIMEOUT/KEIN KONTAKT -> $endpoint erreichbar, Antwort kam nicht (Kaltstart? 90s)"
        failed=1
        ;;
      *)
        echo "HTTP $code -> $endpoint antwortet, aber nicht mit 200: $(printf '%.90s' "$body")"
        failed=1
        ;;
    esac
  done
  echo ""
  [ "$failed" -eq 0 ] && echo "Alle geprueften Provider antworten." || echo "Mindestens ein Provider ist nicht nutzbar (siehe oben)."
  return 0
}

# Fehlende Keys aus dem Bundle nachziehen. Ruft secrets.sh unlock auf und
# entfernt danach nur Platzhalter, damit der echte Key wieder gewinnt.
cmd_restore() {
  local entry name st need=0 f
  for entry in "${KEYS[@]}"; do
    name="${entry%%|*}"
    st="$(state_of "$name")"
    [ "$st" = "ok" ] || need=1
  done
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    f="${f/#\~/$HOME}"
    [ -f "$f" ] && [ -s "$f" ] || need=1
  done < <(referenced_files)
  if [ "$need" -eq 0 ]; then
    echo "Alle Key-Dateien sind gefüllt — nichts zu tun."
    return 0
  fi
  echo "=> secrets.sh unlock (Passphrase-Kandidaten werden durchprobiert)..."
  if ! bash "$REPO_ROOT/infra/scripts/secrets.sh" unlock; then
    echo "FEHLER: Unlock fehlgeschlagen. Danach manuell mit der Passphrase:"
    echo "       ./infra/scripts/secrets.sh unlock"
    return 1
  fi
  # Platzhalter wegräumen, damit der Unlock sie überschreiben kann.
  for entry in "${KEYS[@]}"; do
    name="${entry%%|*}"
    [ "$(state_of "$name")" = "leer" ] && rm -f "$KEYDIR/$name"
  done
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    f="${f/#\~/$HOME}"
    [ -f "$f" ] && [ ! -s "$f" ] && rm -f "$f"
  done < <(referenced_files)
  bash "$REPO_ROOT/infra/scripts/secrets.sh" unlock || true
  cmd_ensure
  cmd_status
}

case "${1:-status}" in
  ensure)  cmd_ensure "${2:-}" ;;
  status)  cmd_status ;;
  doctor)  cmd_doctor ;;
  restore) cmd_restore ;;
  *) echo "Usage: $0 {ensure [--quiet]|status|doctor|restore}"; exit 1 ;;
esac
