# MAIN-landscape Aliase: werden von .bashrc/.zshrc automatisch gesourced (siehe setup.sh)
export PATH="$HOME/.opencode/bin:$HOME/.local/bin:$PATH"
export TZ="Europe/Berlin"

alias save='./infra/scripts/save.sh'
alias auth='./infra/scripts/auth.sh status'
alias secrets='./infra/scripts/secrets.sh status'
alias ports='./infra/scripts/ports.sh'
alias st='git status -sb'
alias ll='ls -lah'

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
