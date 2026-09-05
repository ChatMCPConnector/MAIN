#!/usr/bin/env bash
# ports.sh: zeigt alle offenen/laufenden Ports im Codespace — fuer den Agent gedacht,
# damit er sofort sieht was passiert ("starte ports" / ./scripts/ports.sh).
# Reihenfolge: eigene App-Ports zuerst (3000/8000/8080 etc.), dann VS Code/Agent-Infra.
set -uo pipefail

COL="$(printf '\033[')"
BOLD="${COL}1m"; DIM="${COL}2m"; GREEN="${COL}32m"; YELLOW="${COL}33m"; CYAN="${COL}36m"; RESET="${COL}0m"

# 1) Alle lauschenden Ports im Container (ss) + Prozesszuordnung
echo "${BOLD}Lauschende Ports im Container:${RESET}"
declare -A OWNER
for pid in $(ls -d /proc/[0-9]* 2>/dev/null | sed 's|/proc/||'); do
  for fd in /proc/$pid/fd/*; do
    ino=$(readlink "$fd" 2>/dev/null | grep -oP 'socket:\[\K[0-9]+')
    [ -n "$ino" ] && [ -z "${OWNER[$ino]:-}" ] && OWNER[$ino]="$pid"
  done
done 2>/dev/null

# typische dev-app ports markieren
declare -A DEVPORTS=([3000]="Web App (React/Vite)" [4000]="Dev Server" [5173]="Vite" [8000]="Python (uvicorn/FastAPI)" [8080]="Web Server (nginx etc.)" [5000]="Flask")


for f in /proc/net/tcp /proc/net/tcp6; do
  while read -r _ local _ state _ _ _ _ _ inode _; do
    [ "$state" = "0A" ] || continue
    port=$(( 16#${local##*:} ))
    pid="${OWNER[$inode]:-}"
    if [ -n "$pid" ]; then
      cmd=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null | head -c 60)
      printf "  %s  PID %-6s %s\n" "$port" "$pid" "$cmd"
      found=1
    else
      printf "  %s  (Codespaces-Agent/Host: SSH & Agent-Kommunikation)\n" "$port"
    fi
  done < "$f"
done 2>/dev/null | sort -n -k1

echo ""
# 2) VS Code forwarded ports (die im Panel sichtbaren) via Codespaces-API
echo "${BOLD}VS Code geforwardete Ports (Panel):${RESET}"
if command -v gh >/dev/null 2>&1; then
  cs=$(gh codespace list --json name 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['name'] if d else '')" 2>/dev/null)
  if [ -n "${cs:-}" ]; then
    gh codespace ports --codespace "$cs" 2>/dev/null | sed 's/^/  /' || echo "  (nicht ermittelbar)"
  else
    echo "  (Codespace-Name nicht ermittelbar)"
  fi
else
  echo "  (gh nicht verfuegbar)"
fi

echo ""
# 3) Kurzfazit: laufen eigene Apps?
echo "${BOLD}Fazit:${RESET}"
own=$(ss -tln 2>/dev/null | awk 'NR>1 {print $4}' | sed 's/.*://' | sort -un | while read -r p; do case "$p" in 53|2000|13005|12563|1663[0-9]|36143|37193|39903|46555) ;; *) echo "$p";; esac; done)
if [ -n "$own" ]; then
  echo "  ${CYAN}Eigene App-Ports aktiv:${RESET}"
  echo "$own" | while read -r p; do
    label="${DEVPORTS[$p]:-App}"
    printf "  ${GREEN}%s${RESET} — %s\n" "$p" "$label"
  done
else
  echo "  ${DIM}Keine eigenen Apps aktiv. Standard-Dev-Ports (3000/8000/8080) sind leer.${RESET}"
fi
