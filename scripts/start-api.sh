#!/usr/bin/env bash
# start-api.sh — Launch the Cognitive OS FastAPI server
# Replaces: start_api.bat / start_api.ps1
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Load environment
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

echo "=========================================="
echo "  🧠 Cognitive OS — FastAPI Server"
echo "=========================================="
echo "  Project: $PROJECT_DIR"
echo "  Port:    5000"
echo "=========================================="

# Activate venv if present
if [ -f "$PROJECT_DIR/venv/bin/activate" ]; then
    source "$PROJECT_DIR/venv/bin/activate"
    echo "  venv:    activated"
elif [ -f "$PROJECT_DIR/.venv/bin/activate" ]; then
    source "$PROJECT_DIR/.venv/bin/activate"
    echo "  venv:    activated"
fi

echo ""

exec python -m uvicorn src.api:app --host 0.0.0.0 --port 5000 --reload
