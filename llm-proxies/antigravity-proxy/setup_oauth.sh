#!/bin/bash
set -e

CONFIG_DIR="$HOME/.config/antigravity-oauth-proxy"
CREDENTIALS_FILE="$CONFIG_DIR/oauth_creds.json"
PROXY_BIN="/workspaces/dvcrn-antigravity-oauth-proxy/antigravity-oauth-proxy"
PROXY_PORT=9878
ADMIN_API_KEY=""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info() { echo -e "${BLUE}ℹ $1${NC}"; }
success() { echo -e "${GREEN}✓ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠ $1${NC}"; }
error() { echo -e "${RED}✗ $1${NC}"; }

# Check if proxy binary exists
if [ ! -f "$PROXY_BIN" ]; then
    error "Proxy binary not found: $PROXY_BIN"
    exit 1
fi

# Generate random admin key
ADMIN_API_KEY="antigravity-secret-$(openssl rand -hex 16)"
export ADMIN_API_KEY

# Stop any existing proxy
info "Stopping any existing proxy..."
pkill -f "antigravity-oauth-proxy" || true
sleep 1

# Start the proxy
info "Starting antigravity-oauth-proxy on port $PROXY_PORT..."
$PROXY_BIN > /tmp/antigravity-proxy.log 2>&1 &
PROXY_PID=$!
sleep 3

# Check if proxy is running
if ! kill -0 $PROXY_PID 2>/dev/null; then
    error "Failed to start proxy. Check /tmp/antigravity-proxy.log"
    cat /tmp/antigravity-proxy.log
    exit 1
fi

success "Proxy started (PID: $PROXY_PID)"

# Start OAuth flow
info "Starting OAuth flow..."
AUTH_RESPONSE=$(curl -s -X POST "http://localhost:$PROXY_PORT/admin/auth/start" \
  -H "Authorization: Bearer $ADMIN_API_KEY" \
  -H "Content-Type: application/json")

AUTH_URL=$(echo "$AUTH_RESPONSE" | grep -o '"authorizationUrl":"[^"]*"' | cut -d'"' -f4)

if [ -z "$AUTH_URL" ]; then
    error "Failed to get authorization URL"
    echo "Response: $AUTH_RESPONSE"
    pkill -f "antigravity-oauth-proxy"
    exit 1
fi

# Open browser
info "Opening browser for OAuth..."
if command -v xdg-open > /dev/null; then
    xdg-open "$AUTH_URL" > /dev/null 2>&1 &
elif command -v open > /dev/null; then
    open "$AUTH_URL" > /dev/null 2>&1 &
else
    warn "Could not open browser automatically. Please open manually:"
fi

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}🌐 Open this URL in your browser:${NC}"
echo ""
echo -e "${YELLOW}$AUTH_URL${NC}"
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo ""
info "After authorizing, copy the final redirect URL and paste it below."
echo "   The URL will look like: http://localhost:51121/oauth-callback?code=...&state=..."
echo ""
read -p "Paste the redirect URL: " REDIRECT_URL

if [ -z "$REDIRECT_URL" ]; then
    error "No redirect URL provided"
    pkill -f "antigravity-oauth-proxy"
    exit 1
fi

# Exchange code for tokens
info "Exchanging authorization code for tokens..."
EXCHANGE_RESPONSE=$(curl -s -X POST "http://localhost:$PROXY_PORT/admin/auth/status" \
  -H "Authorization: Bearer $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"code\":\"$REDIRECT_URL\"}")

# Check if credentials were saved
if [ -f "$CREDENTIALS_FILE" ]; then
    success "Credentials saved to $CREDENTIALS_FILE"
else
    error "Failed to save credentials"
    echo "Response: $EXCHANGE_RESPONSE"
    pkill -f "antigravity-oauth-proxy"
    exit 1
fi

# Restart proxy with credentials
info "Restarting proxy with credentials..."
pkill -f "antigravity-oauth-proxy"
sleep 1

$PROXY_BIN > /tmp/antigravity-proxy.log 2>&1 &
PROXY_PID=$!
sleep 3

# Check proxy status
STATUS=$(curl -s "http://localhost:$PROXY_PORT/admin/status" \
  -H "Authorization: Bearer $ADMIN_API_KEY")

if echo "$STATUS" | grep -q "configured"; then
    success "Proxy is now configured and running!"
    echo ""
    info "Admin API Key: $ADMIN_API_KEY"
    info "Proxy URL: http://localhost:$PROXY_PORT"
    info "Models: http://localhost:$PROXY_PORT/v1/models"
    echo ""
    success "✅ Setup complete! The proxy will automatically refresh tokens."
else
    warn "Proxy status check failed, but it may still work."
    echo "Status: $STATUS"
fi

# Cleanup
unset ADMIN_API_KEY