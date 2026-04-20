#!/bin/bash
set -euo pipefail

# Wall-clock scheduling: fixed intervals, not sleep-after-completion.
# Runtime is ~2:46 with local node. sleep-after would drift to ~7:46 for 5min interval.
INTERVAL="${REKTSLUG_SHADOW_INTERVAL_SECONDS:-300}"

cleanup() {
    echo "[$(date -u)] Shadow producer received SIGTERM, shutting down..."
    exit 0
}
trap cleanup SIGTERM SIGINT

echo "[$(date -u)] Shadow producer starting (interval=${INTERVAL}s)"

while true; do
    next_due=$(( $(date +%s) + INTERVAL ))
    echo "[$(date -u)] Starting snapshot cycle..."

    # Precompute sidecar — log errors but don't crash the loop
    if ! uv run python scripts/precompute_hl_sidecar.py 2>&1; then
        echo "[$(date -u)] WARNING: precompute_hl_sidecar.py failed, skipping publish"
    else
        # Publish signals for each tracked symbol
        for symbol in BTCUSDT ETHUSDT; do
            if ! uv run python scripts/publish_signals_from_snapshot.py --symbol "$symbol" --top-n 5 2>&1; then
                echo "[$(date -u)] WARNING: publish failed for $symbol"
            fi
        done
        echo "[$(date -u)] Snapshot cycle complete"
    fi

    # Sleep only the remaining time until next wall-clock slot
    now=$(date +%s)
    remaining=$(( next_due - now ))
    if [ "$remaining" -gt 0 ]; then
        echo "[$(date -u)] Sleeping ${remaining}s until next cycle..."
        sleep "$remaining" &
        wait $!  # Allow SIGTERM to interrupt sleep
    else
        echo "[$(date -u)] WARNING: cycle took longer than interval (${INTERVAL}s), starting next immediately"
    fi
done
