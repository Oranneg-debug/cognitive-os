#!/usr/bin/env bash
# start-services.sh — Launch all Cognitive OS services
# Replaces: start_services.bat
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=========================================="
echo "  🧠 Cognitive OS — Service Launcher"
echo "=========================================="
echo ""

# 1. Check llama-swap
LLAMA_SWAP_BIN="${LLAMA_SWAP_BIN:-/home/gennaro/llama-swap/llama-swap}"
LLAMA_SWAP_CONFIG="${LLAMA_SWAP_CONFIG:-$PROJECT_DIR/config/llama-swap.yaml}"

if ! pgrep -f "llama-swap" > /dev/null 2>&1; then
    echo "  [1/3] Starting llama-swap..."
    if [ -f "$LLAMA_SWAP_BIN" ] && [ -f "$LLAMA_SWAP_CONFIG" ]; then
        setsid "$LLAMA_SWAP_BIN" --config "$LLAMA_SWAP_CONFIG" --listen :1234 \
            > "$PROJECT_DIR/logs/llama-swap.log" 2>&1 &
        echo "        PID: $!"
        echo "        Config: $LLAMA_SWAP_CONFIG"
        echo "        Port: 1234"
        sleep 2
    else
        echo "        ⚠ llama-swap binary or config not found"
        echo "        Binary: $LLAMA_SWAP_BIN"
        echo "        Config: $LLAMA_SWAP_CONFIG"
    fi
else
    echo "  [1/3] llama-swap already running ($(pgrep -f llama-swap))"
fi

echo ""

# 2. Start FastAPI
echo "  [2/3] Starting Cognitive OS FastAPI..."
if ! pgrep -f "uvicorn src.api" > /dev/null 2>&1; then
    "$SCRIPT_DIR/start-api.sh" &
    API_PID=$!
    echo "        PID: $API_PID"
    echo "        Port: 5000"
else
    echo "        Already running ($(pgrep -f 'uvicorn src.api'))"
fi

echo ""

# 3. Start Telegram bot (optional)
echo "  [3/3] Telegram bot..."
if [ -n "${TELEGRAM_BOT_TOKEN:-}" ]; then
    if ! pgrep -f "telegram_bot" > /dev/null 2>&1; then
        cd "$PROJECT_DIR"
        nohup python -m src.telegram_bot \
            > "$PROJECT_DIR/logs/telegram.log" 2>&1 &
        echo "        PID: $!"
    else
        echo "        Already running"
    fi
else
    echo "        Skipped (TELEGRAM_BOT_TOKEN not set)"
fi

echo ""
echo "=========================================="
echo "  All services started."
echo "  Dashboard: http://localhost:5000"
echo "  Inference: http://localhost:1234"
echo "=========================================="
