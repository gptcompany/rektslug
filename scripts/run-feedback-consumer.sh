#!/bin/bash
set -euo pipefail

cleanup() {
    echo "[$(date -u)] Feedback consumer received SIGTERM, shutting down..."
    exit 0
}
trap cleanup SIGTERM SIGINT

echo "[$(date -u)] Feedback consumer starting for symbols: BTCUSDT ETHUSDT"

# Start the python module in the foreground
uv run python -m src.liquidationheatmap.signals.feedback --symbols BTCUSDT ETHUSDT
