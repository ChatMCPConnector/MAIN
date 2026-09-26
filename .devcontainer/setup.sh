#!/usr/bin/env bash
# Landschaft-Setup: läuft automatisch bei jedem neuen Codespace (postCreateCommand).
# Idempotent: kann beliebig oft laufen, überschreibt keine Secrets (auth.json, .env).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> [landscape] Systempakete..."
sudo apt-get update -qq
sudo apt-get install -y -qq curl wget git jq unzip zip nano vim htop tree sqlite3 build-essential python3 python3-pip python3-venv python-is-python3 ca-certificates gnupg nodejs npm xvfb x11vnc novnc websockify libgtk-3-0t64 libdbus-glib-1-2 libxt6t64 libasound2t64 inotify-tools > /dev/null
sudo rm -rf /var/lib/apt/lists/*

# python-is-python3 legt /usr/bin/python an. Ohne das gibt es nur python3, und
# alles, was bare `python` aufruft (Tooling, Editor-Integrationen, fremde
# Wrapper), scheitert mit "command not found" — die Ursache der gelben
# Python-Warndreiecke in der VS-Code-Terminalanzeige. Idempotent: das Paket
# überschreibt ein vorhandenes /usr/bin/python nur, wenn es selbst owns it.

# opencode ist GEPINNT. Quelle der Wahrheit ist EINE Stelle: der
# @opencode-ai/plugin-Dep in .opencode/package.json — genau die Version, die
# opencode für seinen Plugin-Ladepfad selbst nachinstalliert. Vorher war die
# Installation floating ("curl …/install | bash"), wodurch der Codespace eine
# andere Version bekam als das Repo; opencode schrieb den Dep dann beim ersten
# TUI-Start um (package.json + package-lock.json) und hinterließ dauerhaft
# uncommitteten Churn, den der Autosave-Daemon mitcommittete.
# Pin wechseln: ./infra/scripts/opencode-version.sh bump   (eine Stelle, ein Commit)
OPENCODE_VERSION="$(sed -nE 's/.*"@opencode-ai\/plugin"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' "$REPO_ROOT/.opencode/package.json" 2>/dev/null | head -1)"
: "${OPENCODE_VERSION:=1.18.32}"   # Notnagel, falls package.json fehlt/kaputt ist
echo "==> [landscape] opencode installieren (gepinnt auf $OPENCODE_VERSION)..."
opencode_install() {
  curl -fsSL https://opencode.ai/install | bash -s -- --version "$OPENCODE_VERSION"
}
#Vorhandene Version ermitteln: einmal das Binary, das der Wrapper ersetzt hat.
installed_opencode_version() {
  local bin="$HOME/.opencode/bin/opencode-bin"
  command -v opencode >/dev/null 2>&1 && [ ! -x "$bin" ] && bin="$(command -v opencode)"
  [ -x "$bin" ] || return 1
  "$bin" --version 2>/dev/null | tr -d '[:space:]'
}
INSTALLED_OC="$(installed_opencode_version || true)"
if [ -z "$INSTALLED_OC" ]; then
  opencode_install && echo "    opencode $OPENCODE_VERSION installiert." \
    || echo "    WARN: opencode-Install fehlgeschlagen, manuell: curl -fsSL https://opencode.ai/install | bash -s -- --version $OPENCODE_VERSION"
elif [ "$INSTALLED_OC" != "$OPENCODE_VERSION" ]; then
  echo "    opencode $INSTALLED_OC gefunden, Pin ist $OPENCODE_VERSION -> aktualisiere."
  opencode_install && echo "    opencode auf $OPENCODE_VERSION aktualisiert." \
    || echo "    WARN: opencode-Update fehlgeschlagen (bleibt $INSTALLED_OC)."
  [ -f "$HOME/.opencode/bin/opencode-bin" ] || mv "$HOME/.opencode/bin/opencode" "$HOME/.opencode/bin/opencode-bin" 2>/dev/null || true
else
  echo "    opencode $INSTALLED_OC vorhanden (Pin stimmt)."
fi
export PATH="$HOME/.opencode/bin:$PATH"

# opencode muss auch in INTERAKTIVEN Shells im PATH sein, nicht nur in diesem
# Skriptprozess. Der opencode-Installer ergänzt die Zeile in ~/.bashrc zwar
# normalerweise selbst, das ist aber nicht garantiert (live am 2026-09-26 in einem
# frischen Codespace: Binary installiert, `opencode` im Terminal trotzdem
# "command not found"). Deshalb wird die Zeile hier idempotent selbst gesetzt —
# unabhängig davon, was der Installer tut.
PATH_MARKER="# MAIN-landscape opencode-path"
for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
  [ -f "$rc" ] || continue
  grep -qF "$PATH_MARKER" "$rc" 2>/dev/null && continue
  {
    echo ""
    echo "$PATH_MARKER"
    echo "export PATH=\"\$HOME/.opencode/bin:\$PATH\""
  } >> "$rc"
  echo "    opencode-PATH in $(basename "$rc") ergaenzt."
done

# opencode Multi-Client Wrapper aktivieren (verhindert Session-Crashes bei parallelen Terminals)
if [ -f "$HOME/.opencode/bin/opencode" ] && [ ! -f "$HOME/.opencode/bin/opencode-bin" ]; then
  mv "$HOME/.opencode/bin/opencode" "$HOME/.opencode/bin/opencode-bin"
fi
if [ -f "$HOME/.opencode/bin/opencode-bin" ]; then
  cp "$REPO_ROOT/infra/scripts/opencode-wrapper.sh" "$HOME/.opencode/bin/opencode"
  chmod +x "$HOME/.opencode/bin/opencode"
  echo "    opencode Multi-Client-Wrapper installiert."
fi

echo "==> [landscape] uv installieren (Python-Runtime für glm2api)..."
# glm2api braucht Python 3.14 (pyproject: requires-python >=3.14) — das System-
# python ist 3.12. uv installiert + managed die passende Version selbst.
if ! command -v uv >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/uv" ]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
else
  echo "    uv schon vorhanden."
fi
export PATH="$HOME/.local/bin:$PATH"

echo "==> [landscape] Shell-Aliase verlinken..."
MARKER="# MAIN-landscape"
for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
  [ -f "$rc" ] || touch "$rc"
  if ! grep -qF "$MARKER" "$rc" 2>/dev/null; then
    {
      echo ""
      echo "$MARKER (nicht editieren, Quelle: $REPO_ROOT/infra/scripts/aliases.sh)"
      echo "[ -f \"$REPO_ROOT/infra/scripts/aliases.sh\" ] && source \"$REPO_ROOT/infra/scripts/aliases.sh\""
    } >> "$rc"
    echo "    verlinkt in $rc"
  fi
done
mkdir -p "$HOME/.local/bin"
ln -sf "$REPO_ROOT/infra/scripts/quota.sh" "$HOME/.local/bin/quota"

echo "==> [landscape] Secrets entsperren (falls Bundle + Passphrase da)..."
if [ -f "$REPO_ROOT/config/secrets.enc" ] && { [ -n "${LANDSCAPE_PASSPHRASE:-}" ] || [ -f "$REPO_ROOT/config/passphrase" ]; }; then
  # SECRETS_NO_PROMPT + </dev/null: der Unlock darf den Codespace-Build NIE auf
  # eine Eingabe warten lassen. Live am 2026-09-26 belegt: leeres
  # LANDSCAPE_PASSPHRASE -> secrets.sh fragt interaktiv von /dev/tty -> Haenger
  # (im Testblock reproduziert). Fehlt die Passphrase, soll der Build schnell
  # mit WARN weiterlaufen — keys.sh ensure legt Platzhalter an, opencode startet.
  UNLOCK_LOG="$(SECRETS_NO_PROMPT=1 bash "$REPO_ROOT/infra/scripts/secrets.sh" unlock </dev/null 2>&1)" \
    && echo "    Secrets automatisch wiederhergestellt." \
    || { echo "    WARN: Auto-Unlock fehlgeschlagen — Keys fehlen, opencode startet nicht:"
         printf '%s\n' "$UNLOCK_LOG" | sed 's/^/      /'; }
elif [ -f "$REPO_ROOT/config/secrets.enc" ]; then
  echo "    Bundle vorhanden, keine Passphrase. Entsperren mit: ./infra/scripts/secrets.sh unlock"
fi

echo "==> [landscape] API-Key-Dateien sicherstellen..."
# opencode verweigert den Start, wenn eine per {file:...} referenzierte Key-Datei
# fehlt. ensure legt fehlende Dateien als leere Platzhalter an — so startet
# opencode in JEDEM Codespace, auch wenn der Unlock oben gescheitert ist.
bash "$REPO_ROOT/infra/scripts/keys.sh" ensure || true

echo "==> [landscape] .env prüfen..."
if [ ! -f "$REPO_ROOT/.env" ] && [ -f "$REPO_ROOT/.env.example" ]; then
  echo "    HINWEIS: $REPO_ROOT/.env fehlt. Bei Bedarf anlegen: cp .env.example .env"
fi

echo "==> [landscape] Git-Auth verdrahten (für Agent-Push)..."
# Wenn LANDSCAPE_PAT als Codespaces-Secret oder Env gesetzt ist: automatisch einrichten.
# Das ist der Einmal-pro-Account-Schritt, danach kann der Agent immer selbst pushen.
if [ -n "${LANDSCAPE_PAT:-${GITHUB_PAT:-${GH_TOKEN:-}}}" ]; then
  bash "$REPO_ROOT/infra/scripts/auth.sh" setup >/dev/null 2>&1 || echo "    WARN: Auth-Setup fehlgeschlagen."
else
  echo "    kein Token gefunden. Einmalig: ./infra/scripts/auth.sh setup  (oder LANDSCAPE_PAT als Codespaces-Secret setzen)"
fi

echo "==> [landscape] rclone (Google-Drive-Backup) installieren..."
# rclone für gdrive-backup.sh (Repo-Sicherung nach Drive, unabhängig von GitHub).
# Auth (rclone.conf mit Refresh-Token) kommt aus dem Secrets-Bundle via secrets.sh unlock.
bash "$REPO_ROOT/infra/scripts/rclone-install.sh" >/dev/null 2>&1 \
  && echo "    rclone installiert ($(rclone version 2>/dev/null | head -1))." \
  || echo "    WARN: rclone-Install fehlgeschlagen, manuell: ./infra/scripts/rclone-install.sh"

echo "==> [landscape] Browser-Runtime (Firefox) prüfen..."
# Firefox (Mozilla-Tarball, gepinnt) als leichtgewichtige Desktop-Browser-Runtime
if [ ! -x "$REPO_ROOT/.runtime/firefox/firefox" ]; then
  bash "$REPO_ROOT/infra/scripts/firefox-install.sh" >/dev/null 2>&1 \
    && echo "    Firefox-Runtime installiert." \
    || echo "    WARN: Firefox-Install fehlgeschlagen, manuell: ./infra/scripts/firefox-install.sh"
else
  echo "    Firefox-Runtime vorhanden."
fi

echo "==> [landscape] Sessions-MCP prüfen (opencode-sessions)..."
# MCP-Server für Session-Verwaltung; DB-Pfad ist pro Codespace identisch (~/.local/share/opencode/opencode.db).
# Falls das Repo nicht unter /workspaces/MAIN liegt, passt setup.sh den Pfad in der opencode-Config an.
if [ -f "$REPO_ROOT/infra/mcp/opencode-sessions-mcp.js" ]; then
  NODE_BIN="$(command -v node || true)"
  MCP_LINE="  \"mcp\": {\"opencode-sessions\": {\"type\": \"local\", \"command\": [\"${NODE_BIN:-node}\", \"$REPO_ROOT/infra/mcp/opencode-sessions-mcp.js\"], \"enabled\": true, \"environment\": {}}},"
  for CFG in "$REPO_ROOT/.opencode/opencode.json" "$HOME/.config/opencode/opencode.json"; do
    mkdir -p "$(dirname "$CFG")"
    if [ ! -f "$CFG" ]; then
      printf '{\n  "$schema": "https://opencode.ai/config.json",\n%s\n  "permission": "allow"\n}\n' "$MCP_LINE" > "$CFG"
    elif ! grep -q '"opencode-sessions"' "$CFG"; then
      python3 - "$CFG" "$MCP_LINE" <<'PYEOF' 2>/dev/null || sed -i '1a\
'"$MCP_LINE" "$CFG"
import sys
cfg_path, mcp_line = sys.argv[1], sys.argv[2]
with open(cfg_path) as f:
    first = f.readline()
    rest = f.read()
with open(cfg_path, "w") as f:
    f.write(first + mcp_line + "\n" + rest)
PYEOF
    fi
  done
  echo "    opencode-sessions MCP registriert (in opencode-Config)."
else
  echo "    SKIP: infra/mcp/opencode-sessions-mcp.js fehlt."
fi

echo "==> [landscape] LLM-Proxy glm2api (HAUPT-Proxy) wiederherstellen..."
# glm2api ist der einzige lokale GLM-Proxy und MUSS nach einem Codespace-Wechsel
# vollautomatisch zurück sein (Patch + .env + start.sh kommen alle aus diesem Repo).
# Klon+uv-Sync dauern ~1-2 Min; der Proxy wird danach direkt gestartet.
# Der Proxy-Code liegt direkt im Repo (llm-proxies/glm2api/) — kein Klon mehr.
# rebuild.sh macht .env + venv (Sekunden), start-glm2api.sh startet.
if ss -tln | grep -q ":8001 "; then
  echo "    Port 8001 belegt — Proxy läuft bereits."
else
  bash "$REPO_ROOT/llm-proxies/rebuild.sh" && bash "$REPO_ROOT/llm-proxies/scripts/start-glm2api.sh" \
    && echo "    glm2api läuft." \
    || echo "    WARN: Autostart fehlgeschlagen — manuell: ./llm-proxies/rebuild.sh --start"
fi

echo "==> [landscape] Go-Toolchain installieren (antigravity-proxy-Build)..."
# antigravity-proxy ist Go und braucht das Binary vor Ort (liegt nicht im Git).
# start.sh erwartet go unter /usr/local/go/bin/go (Fallback-Pfad dort).
if [ -x /usr/local/go/bin/go ]; then
  echo "    Go schon vorhanden: $(/usr/local/go/bin/go version)."
else
  GO_VERSION="1.25.7"  # gepinnt, entspricht mise.toml im antigravity-proxy
  # --retry: Boot-Netzwerk ist oft transient instabil; ohne Retry blieb der
  # antigravity-proxy bei Rebuilds ohne Go und startete nicht (start.sh
  # installiert go inzwischen selbst als Fallback).
  curl -fsSL --retry 5 --retry-delay 3 --retry-all-errors "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" -o /tmp/opencode/go.tgz \
    && sudo rm -rf /usr/local/go \
    && sudo tar -C /usr/local -xzf /tmp/opencode/go.tgz \
    && echo "    Go ${GO_VERSION} nach /usr/local/go installiert." \
    || echo "    WARN: Go-Install fehlgeschlagen — antigravity-Build evtl. nicht möglich."
fi

echo "==> [landscape] LLM-Proxy antigravity-proxy wiederherstellen & starten..."
if ss -tln | grep -q ":9878 "; then
  echo "    Port 9878 belegt — antigravity-proxy läuft bereits."
else
  if [ -x "$REPO_ROOT/llm-proxies/antigravity-proxy/scripts/start.sh" ]; then
    bash "$REPO_ROOT/llm-proxies/antigravity-proxy/scripts/start.sh" \
      && echo "    antigravity-proxy läuft." \
      || echo "    WARN: antigravity-proxy Start fehlgeschlagen."
  fi
fi

echo "==> [landscape] Zentralen opencode-Server starten..."
if ss -tln | grep -q ":4096 "; then
  echo "    Port 4096 belegt — opencode-server läuft bereits."
else
  if [ -x "$REPO_ROOT/infra/scripts/opencode-server.sh" ]; then
    bash "$REPO_ROOT/infra/scripts/opencode-server.sh" start \
      && echo "    opencode-server läuft." \
      || echo "    WARN: opencode-server Start fehlgeschlagen."
  fi
fi

echo "==> [landscape] Proxy-Watchdog starten (hält glm2api am Leben)..."
# Watchdog auch beim Codespace-Bau/Rebuild starten (postStartCommand macht es bei
# jedem Start zusätzlich). setsid, damit devcontainer-cli ihn nicht mitkillt.
mkdir -p /tmp/opencode
if ! { [ -f /tmp/opencode/proxy-watchdog.lock ] && kill -0 "$(cat /tmp/opencode/proxy-watchdog.lock 2>/dev/null)" 2>/dev/null; }; then
  setsid bash "$REPO_ROOT/.devcontainer/proxy-watchdog.sh" </dev/null >/dev/null 2>&1 &
  echo "    Proxy-Watchdog gestartet (30s-Intervall)."
else
  echo "    Watchdog läuft bereits."
fi

echo "==> [landscape] Config-Watchdog starten (restartet opencode-server bei Config-Änderung)..."
if ! { [ -f /tmp/opencode/config-watchdog.lock ] && kill -0 "$(cat /tmp/opencode/config-watchdog.lock 2>/dev/null)" 2>/dev/null; }; then
  setsid nohup bash "$REPO_ROOT/infra/scripts/config-watchdog.sh" </dev/null >>/tmp/opencode/config-watchdog.log 2>&1 &
  disown $! 2>/dev/null || true
  echo "    Config-Watchdog gestartet (inotify auf opencode.json)."
else
  echo "    Config-Watchdog läuft bereits."
fi

echo "==> [landscape] Autosave-Daemon starten (committet+pusht alle 30 Min)..."
if ! { [ -f /tmp/opencode/autosave-daemon.lock ] && kill -0 "$(cat /tmp/opencode/autosave-daemon.lock 2>/dev/null)" 2>/dev/null; }; then
  setsid nohup bash "$REPO_ROOT/.devcontainer/autosave-daemon.sh" </dev/null >> /tmp/opencode/autosave.log 2>&1 &
  disown $! 2>/dev/null || true
  echo "    Autosave-Daemon gestartet (30-Min-Intervall)."
else
  echo "    Autosave-Daemon läuft bereits."
fi

echo "==> [landscape] Fertig. Weiter mit: ./infra/scripts/save.sh status"
