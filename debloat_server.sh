#!/usr/bin/env bash

# Exit on unexpected errors
set -e

GREEN='\030[0;32m'
NC='\030[0;31m' # No Color
YELLOW='\030[1;33m'

echo -e "${YELLOW}=== Starting Agentic AI Server Optimization & Debloat ===${NC}\n"

# ----------------------------------------------------------------------
# 1. CLEAN ZOMBIE & ORPHANED AGENT PROCESSES
# ----------------------------------------------------------------------
echo -e "${GREEN}[1/3] Terminating lingering agent processes and node subshells...${NC}"

# Target common agent binaries and orphan node/python tasks
pkill -f opencode || true
pkill -f codex || true

# Clean up orphan node workers (often spawned by agent extensions/executors)
# Note: Kills node tasks running index.js or background tasks
pkill -f "node.*index.js" || true

echo "✓ Zombie & orphaned agent processes terminated."
echo ""

# ----------------------------------------------------------------------
# 2. CLEAR AGENT CACHES & TEMP LOGS
# ----------------------------------------------------------------------
echo -e "${GREEN}[2/3] Clearing agent caches, temporary log dumps, and temp files...${NC}"

# Clear OpenCode & Codex caches if they exist
rm -rf ~/.cache/opencode 2>/dev/null || true
rm -rf ~/.local/share/opencode/log/* 2>/dev/null || true
rm -rf ~/.cache/codex 2>/dev/null || true

# Clear temporary log files generated during piped runs in /tmp
rm -f /tmp/agent_*.log 2>/dev/null || true
rm -f /tmp/pytest_*.log 2>/dev/null || true

echo "✓ Cache and temporary log directories cleared."
echo ""

# ----------------------------------------------------------------------
# 3. FIX INOTIFY FILE WATCHER LIMITS
# ----------------------------------------------------------------------
echo -e "${GREEN}[3/3] Checking and optimizing inotify max_user_watches...${NC}"

CURRENT_WATCHES=$(sysctl -n fs.inotify.max_user_watches 2>/dev/null || echo 0)
TARGET_WATCHES=524288

if [ "$CURRENT_WATCHES" -lt "$TARGET_WATCHES" ]; then
    echo "Current inotify watches ($CURRENT_WATCHES) is low. Elevating to $TARGET_WATCHES..."
    
    # Apply dynamically to current running session
    if command -v sudo >/dev/null 2>&1; then
        sudo sysctl -w fs.inotify.max_user_watches=$TARGET_WATCHES
        # Persist across reboots in /etc/sysctl.conf
        if ! grep -q "fs.inotify.max_user_watches" /etc/sysctl.conf; then
            echo "fs.inotify.max_user_watches=$TARGET_WATCHES" | sudo tee -a /etc/sysctl.conf > /dev/null
        fi
    else
        sysctl -w fs.inotify.max_user_watches=$TARGET_WATCHES
        if ! grep -q "fs.inotify.max_user_watches" /etc/sysctl.conf; then
            echo "fs.inotify.max_user_watches=$TARGET_WATCHES" >> /etc/sysctl.conf
        fi
    fi
    echo "✓ inotify watches successfully increased."
else
    echo "✓ inotify max_user_watches is already optimal ($CURRENT_WATCHES)."
fi

echo ""
echo -e "${YELLOW}=== Optimization Complete! Current Memory Usage: ===${NC}"
free -h