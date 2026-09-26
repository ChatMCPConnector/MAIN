#!/usr/bin/env bash
# start.sh: Startet antigravity-oauth-proxy (Port 9878) analog zu start-glm2api.sh.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDFILE="$DIR/antigravity-proxy.pid"
LOGFILE="/tmp/opencode/antigravity-proxy.log"
HOST="127.0.0.1"
PORT="9878"
HEALTH_URL="http://${HOST}:${PORT}/v1/models"

mkdir -p /tmp/opencode

if ss -tln | grep -q ":${PORT} "; then
  if curl -sf -m 2 "${HEALTH_URL}" >/dev/null 2>&1; then
    echo "[antigravity-proxy] Läuft bereits auf Port ${PORT} (/v1/models OK)."
    exit 0
  fi
  echo "[antigravity-proxy] WARN: Port ${PORT} belegt, aber ${HEALTH_URL} antwortet nicht."
fi

# Go-Toolchain sicherstellen: Binary fehlt im Git, Build braucht go.
# Wenn go nirgends vorhanden ist (z.B. nach fehlgeschlagenem setup.sh-Go-Install
# beim Codespace-Rebuild), installiert sich das Skript Go selbst — mit Retry,
# weil der Download beim Boot transient scheitern kann.
GO_VERSION="1.25.7"  # gepinnt, entspricht mise.toml
if ! command -v go >/dev/null 2>&1 && [ ! -x /usr/local/go/bin/go ]; then
  echo "[antigravity-proxy] go fehlt — installiere Go ${GO_VERSION} nach /usr/local/go..."
  if curl -fsSL --retry 5 --retry-delay 3 --retry-all-errors \
      "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" -o /tmp/opencode/go.tgz \
      && sudo rm -rf /usr/local/go && sudo tar -C /usr/local -xzf /tmp/opencode/go.tgz; then
    echo "[antigravity-proxy] Go ${GO_VERSION} installiert."
  else
    echo "[antigravity-proxy] FEHLER: Go-Install fehlgeschlagen." >&2
    exit 1
  fi
fi

if [ ! -x "$DIR/antigravity-oauth-proxy" ]; then
  echo "[antigravity-proxy] Binary fehlt — baue antigravity-oauth-proxy..."
  (cd "$DIR" && (command -v go >/dev/null 2>&1 && go build -o antigravity-oauth-proxy ./cmd/antigravity-oauth-proxy || /usr/local/go/bin/go build -o antigravity-oauth-proxy ./cmd/antigravity-oauth-proxy))
fi

echo "[antigravity-proxy] Starte antigravity-oauth-proxy auf ${HOST}:${PORT}..."
# HOST explizit setzen: Upstream band hart auf alle Interfaces (":" + port).
# Der Codespace leitet 9878 per Port-Forward weiter — das funktioniert über
# Loopback genauso, ist aber nicht aus dem Netz erreichbar.
(cd "$DIR" && ADMIN_API_KEY="antigravity-secret-6fe2eaa404e1c91bfa0fec01e74ddcc1" \
  HOST="${HOST}" \
  setsid nohup ./antigravity-oauth-proxy --port "${PORT}" \
  >> "${LOGFILE}" 2>&1 & echo $! > "${PIDFILE}")

for i in $(seq 1 30); do
  if curl -sf -m 2 "${HEALTH_URL}" >/dev/null 2>&1; then
    # Bindung prüfen: Health-Check allein beweist nichts über die Erreichbarkeit.
    bound="$(ss -tln 2>/dev/null | awk -v p=":${PORT}\$" '$4 ~ p {print $4}' | head -1)"
    case "${bound:-}" in
      127.0.0.1:*|"[::1]:"*) echo "[antigravity-proxy] OK: Antwortet auf ${HOST}:${PORT} (gebunden: ${bound})." ;;
      "") echo "[antigravity-proxy] WARN: Socket-Bindung auf Port ${PORT} nicht erkannt." ;;
      *) echo "[antigravity-proxy] WARN: Bindung ist ${bound}, erwartet ${HOST}. Nicht aus dem Netz erreichbar machen ist sonst nicht gegeben." ;;
    esac
    exit 0
  fi
  sleep 1
done

echo "[antigravity-proxy] FEHLER: Port ${PORT} nicht erreichbar. Log:"
tail -n 20 "${LOGFILE}" 2>/dev/null || true
exit 1
