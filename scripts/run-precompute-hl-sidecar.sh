#!/bin/bash
# Runtime entrypoint for the Hyperliquid sidecar precompute cron.

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"

. "$SCRIPT_DIR/lib/runtime_env.sh"
lh_load_runtime_env host

# Stable defaults for the experimental v3 branch. Any injected env value still
# wins, so ops can override these without editing the wrapper.
: "${HEATMAP_HL_TOP_POSITION_SCORE_MODE_BTC:=notional}"
: "${HEATMAP_HL_TOP_POSITION_TOP_N_BTC:=500}"
: "${HEATMAP_HL_TOP_POSITION_OBJECTIVE_BTC:=none}"
: "${HEATMAP_HL_TOP_POSITION_SCORE_MODE_ETH:=concentration}"
: "${HEATMAP_HL_TOP_POSITION_TOP_N_ETH:=300}"
: "${HEATMAP_HL_TOP_POSITION_CONCENTRATION_SHARE_POWER_ETH:=1.0}"
: "${HEATMAP_HL_TOP_POSITION_CONCENTRATION_POSITIONS_PENALTY_ETH:=0.1}"

export \
    HEATMAP_HL_TOP_POSITION_SCORE_MODE_BTC \
    HEATMAP_HL_TOP_POSITION_TOP_N_BTC \
    HEATMAP_HL_TOP_POSITION_OBJECTIVE_BTC \
    HEATMAP_HL_TOP_POSITION_SCORE_MODE_ETH \
    HEATMAP_HL_TOP_POSITION_TOP_N_ETH \
    HEATMAP_HL_TOP_POSITION_CONCENTRATION_SHARE_POWER_ETH \
    HEATMAP_HL_TOP_POSITION_CONCENTRATION_POSITIONS_PENALTY_ETH

cd "$PROJECT_DIR"
exec "${PROJECT_DIR}/.venv/bin/python" "${PROJECT_DIR}/scripts/precompute_hl_sidecar.py"
