#!/bin/bash

# Cloudflared PostgreSQL Access Script
#
# This script uses cloudflared access to create a local proxy to a PostgreSQL database
# protected by Cloudflare Access. It runs in the background as a daemon.
#
# Usage:
#   ./cloudflared_postgres.sh                    # Start tunnel in background
#   ./cloudflared_postgres.sh stop               # Stop the tunnel
#   ./cloudflared_postgres.sh status             # Check tunnel status
#   ./cloudflared_postgres.sh restart            # Restart the tunnel
#
# Environment variables required:
#   CLOUDFLARE_ACCESS_URL - The Cloudflare Access URL (e.g., https://db.example.com)
#   POSTGRES_USER - PostgreSQL username (default: postgres)
#   POSTGRES_DB - PostgreSQL database name (default: postgres)
#   LOCAL_PORT - Local port to bind the proxy to (default: 5433)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# PID file location
PID_FILE="/tmp/cloudflared_postgres.pid"
LOG_FILE="/tmp/cloudflared_postgres.log"

# Function to print colored messages
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Function to check if tunnel is running
is_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            return 0
        fi
    fi
    return 1
}

# Function to stop the tunnel
stop_tunnel() {
    if is_running; then
        PID=$(cat "$PID_FILE")
        log_info "Stopping cloudflared tunnel (PID: $PID)..."
        kill "$PID" 2>/dev/null || true
        rm -f "$PID_FILE"
        sleep 1
        if is_running; then
            log_warn "Process still running, forcing kill..."
            kill -9 "$PID" 2>/dev/null || true
        fi
        log_info "Tunnel stopped"
    else
        log_info "Tunnel is not running"
    fi
}

# Function to show status
show_status() {
    if is_running; then
        PID=$(cat "$PID_FILE")
        log_info "Tunnel is running (PID: $PID)"
        log_info "Local proxy: localhost:${LOCAL_PORT:-5433}"
        if [ -f "$LOG_FILE" ]; then
            echo ""
            echo "Recent log output:"
            tail -n 5 "$LOG_FILE"
        fi
    else
        log_info "Tunnel is not running"
    fi
}

# Handle command line arguments
case "${1:-start}" in
    stop)
        stop_tunnel
        exit 0
        ;;
    status)
        show_status
        exit 0
        ;;
    restart)
        stop_tunnel
        sleep 1
        # Continue to start
        ;;
    start)
        # Continue to start
        ;;
    *)
        echo "Usage: $0 {start|stop|status|restart}"
        exit 1
        ;;
esac


# Check if already running
if is_running; then
    PID=$(cat "$PID_FILE")
    log_warn "Tunnel is already running (PID: $PID)"
    show_status
    exit 0
fi

# Check if cloudflared is installed
if ! command -v cloudflared &> /dev/null; then
    log_error "cloudflared is not installed"
    log_info "Install it with: curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb && sudo dpkg -i cloudflared.deb"
    exit 1
fi

# Check required environment variables
if [ -z "$CLOUDFLARE_ACCESS_URL" ]; then
    log_error "CLOUDFLARE_ACCESS_URL environment variable is not set"
    log_info "Example: export CLOUDFLARE_ACCESS_URL='https://db.example.com'"
    exit 1
fi

# Set defaults
LOCAL_PORT="${LOCAL_PORT:-5433}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-postgres}"

# Start cloudflared access proxy in the background
log_info "Starting cloudflared access proxy..."
log_info "Access URL: $CLOUDFLARE_ACCESS_URL"
log_info "Local proxy: localhost:$LOCAL_PORT"

# Remove https:// prefix if present for the cloudflared command
HOSTNAME="${CLOUDFLARE_ACCESS_URL#https://}"
HOSTNAME="${HOSTNAME#http://}"

# Start cloudflared as a background daemon
nohup cloudflared access tcp --hostname "$HOSTNAME" --url "localhost:$LOCAL_PORT" > "$LOG_FILE" 2>&1 &
CLOUDFLARED_PID=$!

# Save PID
echo "$CLOUDFLARED_PID" > "$PID_FILE"

log_info "Cloudflared PID: $CLOUDFLARED_PID"

# Wait for proxy to establish
log_info "Waiting for proxy to establish..."
sleep 3

# Check if cloudflared is still running
if ! is_running; then
    log_error "Cloudflared failed to start or exited unexpectedly"
    if [ -f "$LOG_FILE" ]; then
        log_error "Check logs at: $LOG_FILE"
        echo ""
        tail -n 10 "$LOG_FILE"
    fi
    rm -f "$PID_FILE"
    exit 1
fi

log_info "✓ Tunnel established successfully and running in background"
log_info ""
log_info "You can now connect using:"
log_info "  psql -h localhost -p $LOCAL_PORT -U $POSTGRES_USER -d $POSTGRES_DB"
log_info ""
log_info "To stop the tunnel: $0 stop"
log_info "To check status: $0 status"
log_info "Logs are at: $LOG_FILE"
