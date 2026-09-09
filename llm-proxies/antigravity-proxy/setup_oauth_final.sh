#!/bin/bash
# Complete automatic OAuth setup for antigravity-oauth-proxy
# WITHOUT requiring any user intervention except for the browser authorization

export PATH=/usr/local/go/bin:$PATH

CONFIG_DIR="$HOME/.config/antigravity-oauth-proxy"
CREDENTIALS_FILE="$CONFIG_DIR/oauth_creds.json"
PROXY_BIN="/workspaces/dvcrn-antigravity-oauth-proxy/antigravity-oauth-proxy"
PROXY_PORT=9878
AUTH_HELPER="/workspaces/dvcrn-antigravity-oauth-proxy/auth"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${BLUE}ℹ $1${NC}"; }
success() { echo -e "${GREEN}✓ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠ $1${NC}"; }
error() { echo -e "${RED}✗ $1${NC}"; }

# Step 1: Check if proxy binary exists
if [ ! -f "$PROXY_BIN" ]; then
    error "Proxy binary not found: $PROXY_BIN"
    exit 1
fi

# Step 2: Stop any existing proxy (FIXED: only kill actual proxy processes, not this script)
info "Stopping any existing proxy..."
# Only kill processes that start with the full binary path (excludes the script itself)
pkill -f "^$PROXY_BIN" || true
sleep 1

# Step 3: Build the auth helper if not exists
if [ ! -f "$AUTH_HELPER" ]; then
    info "Building OAuth auth helper..."
    cd /workspaces/dvcrn-antigravity-oauth-proxy
    go build -o auth ./cmd/auth || {
        error "Failed to build auth helper"
        exit 1
    }
fi

success "Auth helper ready"

# Step 4: Run OAuth flow using the auth helper with NO BROWSER (local only)
info "Starting OAuth flow (local mode)..."
cd /workspaces/dvcrn-antigravity-oauth-proxy

# Run with --no-browser flag - will print URL for manual copy
./auth --no-browser 2>&1 | tee /tmp/oauth-setup.log || {
    error "OAuth flow failed"
    cat /tmp/oauth-setup.log
    exit 1
}

# Step 5: Check if credentials were saved
if [ -f "$CREDENTIALS_FILE" ]; then
    success "OAuth credentials saved to $CREDENTIALS_FILE"
else
    error "OAuth credentials not saved"
    exit 1
fi

# Step 6: Generate random admin key
ADMIN_API_KEY="antigravity-secret-$(openssl rand -hex 16)"
export ADMIN_API_KEY

# Step 7: Start the proxy with credentials
info "Starting antigravity-oauth-proxy with credentials..."
$PROXY_BIN --port $PROXY_PORT > /tmp/antigravity-proxy.log 2>&1 &
PROXY_PID=$!
sleep 3

# Step 8: Verify proxy is running
if ! kill -0 $PROXY_PID 2>/dev/null; then
    error "Proxy failed to start"
    cat /tmp/antigravity-proxy.log
    exit 1
fi

success "Proxy started (PID: $PROXY_PID)"

# Step 9: Check proxy status
sleep 2
STATUS=$(curl -s "http://localhost:$PROXY_PORT/admin/status" \
  -H "Authorization: Bearer $ADMIN_API_KEY" 2>/dev/null || echo "unknown")

if echo "$STATUS" | grep -qE "configured|running" || [ -n "$STATUS" ]; then
    success "✅ Setup complete!"
    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
    info "Admin API Key: $ADMIN_API_KEY"
    info "Proxy URL: http://localhost:$PROXY_PORT"
    info "Models: http://localhost:$PROXY_PORT/v1/models"
    info "OpenAI: http://localhost:$PROXY_PORT/v1/chat/completions"
    info "Gemini: http://localhost:$PROXY_PORT/v1beta/models/..."
    echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    success "The proxy will automatically refresh tokens. No browser needed anymore!"
else
    warn "Proxy status check failed, but it may still work"
    echo "Status: $STATUS"
    echo ""
    info "Try running: curl http://localhost:$PROXY_PORT/v1/models"
fi

# Cleanup
unset ADMIN_API_KEY