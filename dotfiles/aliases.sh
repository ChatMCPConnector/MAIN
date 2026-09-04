# MAIN-landscape Aliase: werden von .bashrc/.zshrc automatisch gesourced (siehe setup.sh)
export PATH="$HOME/.opencode/bin:$HOME/.local/bin:$PATH"
export TZ="${TZ:-Europe/Istanbul}"

alias save='./scripts/save.sh'
alias push='./scripts/push.sh'
alias auth='./scripts/auth.sh status'
alias st='git status -sb'
alias ll='ls -lah'

# Praktisch beim Umzug: zeigt was NICHT im Git ist und damit verloren ginge
landscape-diff() {
  echo "== Dateien außerhalb des Repos (gehen beim Wechsel verloren, wenn nicht in Git): =="
  echo "   ~/.config/opencode/opencode.json  -> Vorlage: config/opencode/opencode.json"
  echo "   ~/.config/opencode/plugins/       -> Vorlage: config/opencode/plugins/"
  echo "   ~/.config/opencode/commands/      -> Vorlage: config/opencode/commands/"
  echo ""
  echo "== Git-Status: =="
  git -C "$(git rev-parse --show-toplevel 2>/dev/null || echo .)" status -sb
}
