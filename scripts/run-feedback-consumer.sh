#!/bin/bash
set -euo pipefail

echo "[$(date -u)] Feedback consumer starting for symbols: BTCUSDT ETHUSDT"

# Replace the shell so the Python process receives container signals directly.
exec uv run python -m src.liquidationheatmap.signals.feedback --symbols BTCUSDT ETHUSDT
