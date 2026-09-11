# MAIN-landscape Aliase: werden von .bashrc/.zshrc automatisch gesourced (siehe setup.sh)
export PATH="$HOME/.opencode/bin:$HOME/.local/bin:/usr/local/go/bin:$PATH"
export TZ="Europe/Berlin"

alias save='./infra/scripts/save.sh'
alias auth='./infra/scripts/auth.sh status'
alias secrets='./infra/scripts/secrets.sh status'
alias ports='./infra/scripts/ports.sh'
alias quota='bash /workspaces/MAIN/infra/scripts/quota.sh'
alias st='git status -sb'
alias ll='ls -lah'

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

# Praktisch beim Umzug: zeigt was NICHT im Git ist und damit verloren ginge
landscape-diff() {
  echo "== Nur noch im Secrets-Bundle (config/secrets.enc), nicht im Git: =="
  echo "   ~/.config/landscape/pat, tokenrouter.key, nvidia-nim.key, xinjianya.key"
  echo "   ~/.local/share/opencode/auth.json"
  echo "   .env + .secrets/chatglm-refresh-token"
  echo ""
  echo "== opencode-Config lebt im Repo (.opencode/). =="
  echo ""
  echo "== Git-Status: =="
  git -C "$(git rev-parse --show-toplevel 2>/dev/null || echo .)" status -sb
}
