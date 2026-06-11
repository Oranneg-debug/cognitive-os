#!/usr/bin/env bash
# =============================================================================
# start-llama-swap.sh — Launch llama-swap with the Cognitive OS configuration
# =============================================================================
# Usage:
#   ./scripts/start-llama-swap.sh            # foreground (default)
#   ./scripts/start-llama-swap.sh --daemon    # background with logging
#
# Prerequisites:
#   - llama-swap binary at /home/gennaro/llama-swap/llama-swap
#   - llama-server binary at /home/gennaro/llama.cpp/build/bin/llama-server
#   - Model files in /mnt/data/AI_Models/models/
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

LLAMA_SWAP_BIN="/home/gennaro/llama-swap/llama-swap"
CONFIG_FILE="${PROJECT_ROOT}/config/llama-swap.yaml"
LOG_DIR="${PROJECT_ROOT}/logs"
LOG_FILE="${LOG_DIR}/llama-swap.log"

# ---------------------------------------------------------------------------
# Validate prerequisites
# ---------------------------------------------------------------------------
if [[ ! -x "${LLAMA_SWAP_BIN}" ]]; then
    echo "ERROR: llama-swap binary not found or not executable at ${LLAMA_SWAP_BIN}" >&2
    exit 1
fi

if [[ ! -f "${CONFIG_FILE}" ]]; then
    echo "ERROR: Configuration file not found at ${CONFIG_FILE}" >&2
    exit 1
fi

if [[ ! -x "/home/gennaro/llama.cpp/build/bin/llama-server" ]]; then
    echo "ERROR: llama-server binary not found or not executable" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Kill any existing llama-swap instance on port 1234
# ---------------------------------------------------------------------------
if lsof -ti:1234 >/dev/null 2>&1; then
    echo "⚠  Port 1234 is in use. Stopping existing process..."
    kill "$(lsof -ti:1234)" 2>/dev/null || true
    sleep 2
fi

# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Cognitive OS — llama-swap                              ║"
echo "║  Config : ${CONFIG_FILE}  ║"
echo "║  Listen : http://0.0.0.0:1234                           ║"
echo "╚══════════════════════════════════════════════════════════╝"

if [[ "${1:-}" == "--daemon" ]]; then
    mkdir -p "${LOG_DIR}"
    echo "Starting in daemon mode. Log: ${LOG_FILE}"
    setsid "${LLAMA_SWAP_BIN}" --config "${CONFIG_FILE}" --listen :1234 \
        >> "${LOG_FILE}" 2>&1 &
    LLAMA_PID=$!
    echo "${LLAMA_PID}" > "${LOG_DIR}/llama-swap.pid"
    echo "llama-swap started as PID ${LLAMA_PID}"
else
    echo "Starting in foreground mode (Ctrl+C to stop)..."
    exec "${LLAMA_SWAP_BIN}" --config "${CONFIG_FILE}" --listen :1234
fi
