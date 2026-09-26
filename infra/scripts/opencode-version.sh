#!/usr/bin/env bash
# opencode-version.sh: der EINZIGE Ort, an dem die opencode-Version gewechselt wird.
#
#   ./infra/scripts/opencode-version.sh check          # Ist alles konsistent?
#   ./infra/scripts/opencode-version.sh latest         # Neueste Release-Version
#   ./infra/scripts/opencode-version.sh bump [VERSION] # Pin + Lock auf neue Version
#   ./infra/scripts/opencode-version.sh install        # Lokales opencode auf den Pin bringen
#
# Warum überhaupt ein Skript: opencode installiert den @opencode-ai/plugin-Dep in
# .opencode/ in SEINER eigenen Version nach. Läuft opencode eine andere Version als
# die im Repo deklarierte, schreibt es den Dep beim ersten TUI-Start um (beobachtet
# 2026-09-26: package.json + package-lock.json, direkt nach `opencode attach`) und
# hinterlässt dauerhaft uncommittete Änderungen. Der Pin ist deshalb genau die
# Version, die opencode selbst nachinstallieren würde — dann ist der Schreibvorgang
# ein No-op. Source of truth ist der Dep in .opencode/package.json; .devcontainer/
# setup.sh liest ihn von dort, es gibt keine zweite Zahl.
#
# Upgrades bleiben bewusst ein Schritt (ein Commit), kein Auto-Tracking: ein
# automatisch nachgeführter Pin würde bei jedem neuen Release das Repo und über den
# Autosave-Daemon die Historie verändern.
#
# Rückweg eines Bumps: ./infra/scripts/opencode-version.sh bump <vorherige Version>
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PKG="$REPO_ROOT/.opencode/package.json"
LOCK="$REPO_ROOT/.opencode/package-lock.json"
REPO_SLUG="anomalyco/opencode"

declared_version() {
  [ -f "$PKG" ] || return 1
  sed -nE 's/.*"@opencode-ai\/plugin"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' "$PKG" | head -1
}

# Auch nach dem Binary greifen, das der Multi-Client-Wrapper (opencode) ersetzt hat.
installed_version() {
  local bin="$HOME/.opencode/bin/opencode-bin"
  command -v opencode >/dev/null 2>&1 && [ ! -x "$bin" ] && bin="$(command -v opencode)"
  [ -x "$bin" ] || return 1
  "$bin" --version 2>/dev/null | tr -d '[:space:]'
}

latest_version() {
  curl -fsSL --max-time 20 "https://api.github.com/repos/$REPO_SLUG/releases/latest" 2>/dev/null \
    | sed -nE 's/.*"tag_name"[[:space:]]*:[[:space:]]*"v?([^"]+)".*/\1/p' | head -1
}

lock_version() {
  [ -f "$LOCK" ] || return 1
  grep -A3 '"node_modules/@opencode-ai/plugin"' "$LOCK" 2>/dev/null \
    | grep -m1 '"version"' | sed -nE 's/.*"version": "([^"]+)".*/\1/p'
}

cmd_check() {
  local d i l k
  d="$(declared_version || true)"; i="$(installed_version || true)"
  l="$(latest_version || true)"; k="$(lock_version || true)"
  printf '%-14s %s\n' "Repo-Pin" "${d:-FEHLT (.opencode/package.json)}"
  printf '%-14s %s\n' "Lock" "${k:-FEHLT}"
  printf '%-14s %s\n' "Installiert" "${i:-kein opencode gefunden}"
  printf '%-14s %s\n' "Latest" "${l:-nicht ermittelbar (offline?)}"
  echo ""
  if [ -z "$d" ]; then echo "FEHLER: kein Pin im Repo — opencode ist ungepinnt."; return 1; fi
  if [ "$k" != "$d" ]; then
    echo "WARNUNG: Lock ($k) != Pin ($d) — 'opencode-version.sh bump $d' zieht den Lock nach."
  fi
  if [ -n "$i" ] && [ "$i" != "$d" ]; then
    echo "ACHTUNG: installiert ist $i, gepinnt ist $d."
    echo "          Neuer Codespace: automatisch korrekt (setup.sh installiert den Pin)."
    echo "          Dieser Codespace: './infra/scripts/opencode-version.sh install'"
    echo "          Ursache ohne Pin: opencode überschreibt den Dep beim TUI-Start."
  fi
  if [ -n "$l" ] && [ "$l" != "$d" ]; then
    echo "UPDATE verfuegbar: $d -> $l   ('opencode-version.sh bump')"
  fi
  if [ -n "$i" ] && [ "$i" = "$d" ] && { [ -z "$l" ] || [ "$l" = "$d" ]; } && [ "$k" = "$d" ]; then
    echo "Alles konsistent."
  fi
  return 0
}

cmd_bump() {
  local target="${1:-}" cur
  cur="$(declared_version || true)"
  [ -n "$cur" ] || { echo "FEHLER: kein Pin im Repo gefunden."; return 1; }
  if [ -z "$target" ]; then
    target="$(latest_version || true)"
    [ -n "$target" ] || { echo "FEHLER: keine Release-Version ermittelbar (offline?). Aufruf: bump <VERSION>"; return 1; }
    target="${target#v}"
  fi
  target="${target#v}"
  if [ "$target" = "$cur" ]; then echo "Pin ist bereits $cur — nichts zu tun."; return 0; fi
  # 1) Pin in package.json (nur die Versionszeile, Format bleibt erhalten)
  sed -i -E "s|(\"@opencode-ai/plugin\"[[:space:]]*:[[:space:]]*\")[^\"]+(\")|\1$target\2|" "$PKG" \
    || { echo "FEHLER: package.json nicht schreibbar."; return 1; }
  # 2) Lock nachziehen (nur der Lock, kein node_modules-Tausch).
  #    Bewusst `npm install --package-lock-only` und keine Hand-Edit: nur npm
  #    berechnet den transitiven Baum korrekt (aendert eine opencode-Version auch
  #    @ai-sdk/provider o. ae., muss der Lock mitziehen). Nebenwirkung: das
  #    System-npm (9.x, Node 18) schreibt keine "license"-Felder, der getrackte
  #    Lock kam aus npm 10+ — der Diff zeigt dann ~8 entfernte license-Zeilen.
  #    Das ist kosmetisch (Versionen + integrity bleiben identisch) und kehrt
  #    nicht zurück, solange nicht ein neueres npm den Lock neu schreibt.
  if command -v npm >/dev/null 2>&1; then
    ( cd "$REPO_ROOT/.opencode" && npm install --package-lock-only --ignore-scripts >/dev/null 2>&1 ) \
      && echo "Lock aktualisiert (via npm; 'license'-Zeilen können verschwinden — kosmetisch)." \
      || echo "WARN: npm konnte den Lock nicht aktualisieren — 'npm --prefix .opencode install --package-lock-only' manuell."
  fi
  # 3) opencode selbst nur, wenn ausdrückt gewünscht (brennt Token, kleine Luecke)
  echo ""
  echo "Pin: $cur -> $target"
  cmd_check || true
  echo ""
  echo "Naechster Schritt: './infra/scripts/save.sh \"chore(opencode): Pin auf $target\"'"
  echo "  (brennt Tokens — im laufenden Codespace erst nach dem Push)"
}

cmd_install() {
  local d; d="$(declared_version || true)"
  [ -n "$d" ] || { echo "FEHLER: kein Pin im Repo gefunden."; return 1; }
  echo "Installiere opencode $d (Repo-Pin) ..."
  curl -fsSL https://opencode.ai/install | bash -s -- --version "$d" \
    || { echo "FEHLER: Install fehlgeschlagen."; return 1; }
  [ -f "$HOME/.opencode/bin/opencode-bin" ] \
    || mv "$HOME/.opencode/bin/opencode" "$HOME/.opencode/bin/opencode-bin" 2>/dev/null || true
  echo "Installiert: $(installed_version || echo unbekannt)"
}

case "${1:-check}" in
  check)   cmd_check ;;
  latest)  latest_version ;;
  bump)    shift; cmd_bump "${1:-}" ;;
  install) cmd_install ;;
  *) echo "Usage: $0 {check|latest|bump [VERSION]|install}"; exit 1 ;;
esac
