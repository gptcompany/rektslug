#!/bin/bash
# Lightweight Hyperliquid historical backfill batch health check.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/lib/runtime_env.sh"
lh_load_runtime_env host

log() { echo "[$(date -Iseconds)] $1"; }

OUTPUT_DIR="${REKTSLUG_HL_BACKFILL_OUTPUT_DIR:-${PROJECT_DIR}/data/validation/expert_snapshots/hyperliquid}"
MIN_RESULTS="${REKTSLUG_HL_BACKFILL_MIN_RESULTS:-1}"
MAX_FAILURES="${REKTSLUG_HL_BACKFILL_MAX_FAILURES:-0}"
MAX_PARTIALS="${REKTSLUG_HL_BACKFILL_MAX_PARTIALS:-0}"
MAX_GAPS="${REKTSLUG_HL_BACKFILL_MAX_GAPS:-0}"
MAX_AGE_HOURS="${REKTSLUG_HL_BACKFILL_MAX_AGE_HOURS:-26}"
UV_CACHE_DIR="${UV_CACHE_DIR:-${PROJECT_DIR}/.uv-cache}"
export UV_CACHE_DIR

args=(
    "run"
    "--project"
    "$PROJECT_DIR"
    "python"
    "${PROJECT_DIR}/scripts/check_hl_backfill_batch.py"
    "--output-dir"
    "$OUTPUT_DIR"
    "--min-results"
    "$MIN_RESULTS"
    "--max-failures"
    "$MAX_FAILURES"
    "--max-partials"
    "$MAX_PARTIALS"
    "--max-gaps"
    "$MAX_GAPS"
    "--max-age-hours"
    "$MAX_AGE_HOURS"
    "--json"
)

if [ -n "${REKTSLUG_HL_BACKFILL_BATCH_ID:-}" ]; then
    args+=("--batch-id" "$REKTSLUG_HL_BACKFILL_BATCH_ID")
fi

if [ -n "${REKTSLUG_HL_BACKFILL_MAX_ANCHOR_FAILURES:-}" ]; then
    args+=("--max-anchor-resolution-failures" "$REKTSLUG_HL_BACKFILL_MAX_ANCHOR_FAILURES")
fi

log "Checking Hyperliquid backfill batch health in ${OUTPUT_DIR}"
uv "${args[@]}"
