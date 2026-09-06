#!/usr/bin/env bash
# ports.sh: lauschende Ports + Labels. Für Mensch und Agent ("ports").
set -uo pipefail

label() {
  case "$1" in
    3000) echo "Web App";; 4000) echo "Dev Server";; 5000) echo "Flask";; 5173) echo "Vite";;
    8000) echo "Python/FastAPI";; 8080) echo "Chat2API-Proxy";; 8001) echo "glm2api-Proxy";;
    8787) echo "HelloGML-Proxy";; 9222) echo "Chromium CDP (localhost-only)";;
    6082) echo "noVNC";; 5920) echo "x11vnc (localhost-only)";;
    *) echo "sonstiger Prozess";;
  esac
}

echo "Lauschende Ports (ss -ltn):"
found=0
while read -r addr; do
  port="${addr##*:}"
  [ -n "$port" ] && [ "$port" != "*" ] || continue
  printf '  %-5s %s\n' "$port" "$(label "$port")"
  found=1
done < <(ss -ltnH 2>/dev/null | awk '{print $4}' | sort -u -t: -k2 -n)
[ "$found" -eq 1 ] || echo "  (keine)"

echo ""
echo "Weitergeleitete Ports (VS Code Panel):"
if command -v gh >/dev/null 2>&1; then
  cs="$(gh codespace list --json name 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['name'] if d else '')" 2>/dev/null)"
  if [ -n "${cs:-}" ]; then
    gh codespace ports --codespace "$cs" 2>/dev/null | sed 's/^/  /' || echo "  (nicht ermittelbar)"
  else
    echo "  (Codespace-Name nicht ermittelbar)"
  fi
else
  echo "  (gh nicht verfügbar)"
fi
