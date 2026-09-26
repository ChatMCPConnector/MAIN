# MAIN-landscape Aliase: werden von .bashrc/.zshrc automatisch gesourced (siehe setup.sh)
export PATH="$HOME/.opencode/bin:$HOME/.local/bin:/usr/local/go/bin:$PATH"
export TZ="Europe/Berlin"

alias save='./infra/scripts/save.sh'
alias auth='./infra/scripts/auth.sh status'
alias secrets='./infra/scripts/secrets.sh status'
alias keys='./infra/scripts/keys.sh status'
alias keys-doctor='./infra/scripts/keys.sh doctor'
alias keys-restore='./infra/scripts/keys.sh restore'
alias ports='./infra/scripts/ports.sh'
alias quota='bash /workspaces/MAIN/infra/scripts/quota.sh'
alias st='git status -sb'
alias ll='ls -lah'
alias gdrive='bash /workspaces/MAIN/infra/scripts/gdrive-backup.sh'
alias ocver='bash /workspaces/MAIN/infra/scripts/opencode-version.sh'
alias csecret='bash /workspaces/MAIN/infra/scripts/codespace-secret.sh'
# Modell-Index. free-models vereint Cline und NVIDIA NIM: zeigt nur kostenlose
# Modelle der letzten 14 Tage, neueste zuerst. cline-only sagt je Modell, ob es
# ueber die API (also in opencode) nutzbar ist oder nur in der Cline-CLI.
alias free-models='python3 /workspaces/MAIN/infra/scripts/free-models.py'
alias cline-models='python3 /workspaces/MAIN/infra/scripts/free-models.py cline'
alias nvidia-models='python3 /workspaces/MAIN/infra/scripts/free-models.py nvidia'

# Autosave-Daemon: status / start / stop / log
autosave() {
  local lock=/tmp/opencode/autosave-daemon.lock
  case "${1:-status}" in
    status)
      if [ -f "$lock" ] && kill -0 "$(cat "$lock" 2>/dev/null)" 2>/dev/null; then
        echo "autosave-daemon läuft (PID $(cat "$lock"))"
      else
        echo "autosave-daemon ist NICHT aktiv"
      fi
      ;;
    start)
      if [ -f "$lock" ] && kill -0 "$(cat "$lock" 2>/dev/null)" 2>/dev/null; then
        echo "läuft bereits (PID $(cat "$lock"))"
      else
        setsid nohup bash /workspaces/MAIN/.devcontainer/autosave-daemon.sh </dev/null >> /tmp/opencode/autosave.log 2>&1 &
        disown $! 2>/dev/null || true
        sleep 0.3
        echo "gestartet (PID $(cat "$lock" 2>/dev/null || echo '?'))"
      fi
      ;;
    stop)
      if [ -f "$lock" ] && kill -0 "$(cat "$lock" 2>/dev/null)" 2>/dev/null; then
        kill "$(cat "$lock")" && echo "gestoppt" || echo "kill fehlgeschlagen"
      else
        echo "läuft nicht"
      fi
      ;;
    log)
      tail -30 /tmp/opencode/autosave.log 2>/dev/null || echo "kein Log"
      ;;
    *)
      echo "Usage: autosave {status|start|stop|log}"
      ;;
  esac
}

# opencode Server-Client Wrapper: verbindet mehrere Terminal-Tabs mit dem
# zentralen Server (Port 4096), damit sich parallele Sessions nie gegenseitig abbrechen.
opencode() {
  local server_url="http://127.0.0.1:4096"
  # Key-Dateien müssen existieren, sonst startet opencode nicht (bad file reference)
  bash /workspaces/MAIN/infra/scripts/keys.sh ensure --quiet >/dev/null 2>&1 || true
  case "${1:-}" in
    serve|attach|models|stats|export|import|completion|agent|upgrade|uninstall|db|mcp|plugin|providers|debug|github|pr|run)
      command opencode "$@"
      return $?
      ;;
  esac

  if curl -sf -m 2 "$server_url/" >/dev/null 2>&1; then
    command opencode attach "$server_url" "$@"
  else
    command opencode "$@"
  fi
}

opencode-server() {
  /workspaces/MAIN/infra/scripts/opencode-server.sh "$@"
}

# Config-Watchdog: status / start / stop / log
config-watchdog() {
  local lock=/tmp/opencode/config-watchdog.lock
  case "${1:-status}" in
    status)
      if [ -f "$lock" ] && kill -0 "$(cat "$lock" 2>/dev/null)" 2>/dev/null; then
        echo "config-watchdog läuft (PID $(cat "$lock"))"
      else
        echo "config-watchdog ist NICHT aktiv"
      fi
      ;;
    start)
      if [ -f "$lock" ] && kill -0 "$(cat "$lock" 2>/dev/null)" 2>/dev/null; then
        echo "läuft bereits (PID $(cat "$lock"))"
      else
        setsid nohup bash /workspaces/MAIN/infra/scripts/config-watchdog.sh </dev/null >>/tmp/opencode/config-watchdog.log 2>&1 &
        disown $! 2>/dev/null || true
        sleep 0.3
        echo "gestartet (PID $(cat "$lock" 2>/dev/null || echo '?'))"
      fi
      ;;
    stop)
      if [ -f "$lock" ] && kill -0 "$(cat "$lock" 2>/dev/null)" 2>/dev/null; then
        kill "$(cat "$lock")" && echo "gestoppt" || echo "kill fehlgeschlagen"
      else
        echo "läuft nicht"
      fi
      ;;
    log)
      tail -30 /tmp/opencode/config-watchdog.log 2>/dev/null || echo "kein Log"
      ;;
    pause)
      touch /tmp/opencode/config-watchdog.pause
      echo "config-watchdog pausiert (/tmp/opencode/config-watchdog.pause gesetzt)"
      ;;
    resume)
      rm -f /tmp/opencode/config-watchdog.pause
      echo "config-watchdog fortgesetzt (/tmp/opencode/config-watchdog.pause entfernt)"
      ;;
    *)
      echo "Usage: config-watchdog {status|start|stop|pause|resume|log}"
      ;;
  esac
}

# Praktisch beim Umzug: zeigt was NICHT im Git ist und damit verloren ginge
landscape-diff() {
  echo "== Nur noch im Secrets-Bundle (config/secrets.enc), nicht im Git: =="
  echo "   ~/.config/landscape/pat, nvidia-nim.key, xinjianya.key, cline.key, chatglm-refresh-token"
  echo "   ~/.local/share/opencode/auth.json"
  echo "   .env"
  echo ""
  echo "== Key-Dateien (leer = Platzhalter, opencode startet, Provider 401) =="
  bash /workspaces/MAIN/infra/scripts/keys.sh status 2>/dev/null
  echo ""
  echo "== opencode-Config lebt im Repo (.opencode/). =="
  echo ""
  echo "== Git-Status: =="
  git -C "$(git rev-parse --show-toplevel 2>/dev/null || echo .)" status -sb
}
