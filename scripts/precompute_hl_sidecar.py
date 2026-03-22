#!/usr/bin/env python3
"""Pre-compute Hyperliquid sidecar liq-map JSON for BTC and ETH.

Designed to run every 15 minutes via cron. Writes atomic JSON files to
data/cache/ that the API serves directly.

Usage:
    uv run python scripts/precompute_hl_sidecar.py
"""

from __future__ import annotations

import gc
import json
import logging
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from src.liquidationheatmap.hyperliquid.sidecar import (
    HyperliquidSidecarPrototypeBuilder,
    SidecarBuildRequest,
    SidecarPositionReconstructor,
    SidecarState,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)

CACHE_DIR = Path("data/cache")
SYMBOLS = ["BTC", "ETH"]
TIMEFRAME_DAYS = 7
# Outlier threshold: bins beyond 5x or below 0.1x mark price are segregated
OUTLIER_HIGH_MULT = 5.0
OUTLIER_LOW_MULT = 0.1


def _compute_display_range(
    all_prices: list[float], current_price: float
) -> tuple[float, float]:
    """Derive min/max display range matching the 1w CoinAnK convention."""
    min_clamp = 0.12
    max_clamp = 0.18
    if not all_prices:
        return (
            round(current_price * (1 - min_clamp), 2),
            round(current_price * (1 + min_clamp), 2),
        )
    sorted_prices = sorted(all_prices)
    lo_idx = max(0, int(len(sorted_prices) * 0.02))
    hi_idx = min(len(sorted_prices) - 1, int(len(sorted_prices) * 0.98))
    filtered_min = min(sorted_prices[lo_idx], current_price)
    filtered_max = max(sorted_prices[hi_idx], current_price)
    span = max(filtered_max - filtered_min, current_price * 0.01)
    padding = span * 0.06
    x_min = filtered_min - padding
    x_max = filtered_max + padding
    x_min = min(x_min, current_price * (1 - min_clamp))
    x_max = max(x_max, current_price * (1 + min_clamp))
    x_min = max(x_min, current_price * (1 - max_clamp))
    x_max = min(x_max, current_price * (1 + max_clamp))
    return round(x_min, 2), round(x_max, 2)


def _build_cumulative(
    buckets: dict[float, float], current_price: float, side: str
) -> list[dict]:
    """Build cumulative series from aggregated volume-by-price buckets."""
    if side == "long":
        prices = sorted(p for p in buckets if p < current_price)
        points = []
        running = 0.0
        for p in reversed(prices):
            running += buckets[p]
            points.append({"price_level": p, "value": running})
        points.reverse()
        points.append({"price_level": current_price, "value": 0.0})
        return points
    else:
        prices = sorted(p for p in buckets if p > current_price)
        points = [{"price_level": current_price, "value": 0.0}]
        running = 0.0
        for p in prices:
            running += buckets[p]
            points.append({"price_level": p, "value": running})
        return points


def generate_symbol(symbol: str) -> dict | None:
    """Generate the liq-map payload for one symbol. Returns None on failure."""
    logger.info("Starting %s 7d generation...", symbol)
    request = SidecarBuildRequest(
        symbol=symbol,
        timeframe_days=TIMEFRAME_DAYS,
        analysis_end=datetime.now(timezone.utc),
    )

    builder = HyperliquidSidecarPrototypeBuilder()
    plan = builder.build(request)

    if not plan.anchor_coverage.latest_anchor_in_window:
        logger.warning("No ABCI anchor for %s, skipping", symbol)
        return None

    state: SidecarState = builder.reconstruct(request)
    logger.info(
        "%s: %d accounts, reconstructing liquidation prices...",
        symbol, len(state.users),
    )

    reconstructor = SidecarPositionReconstructor()
    bin_size = plan.bin_size
    target_coin = request.target_coin

    # Get mark price for the target
    target_asset_idx = None
    for pos_list in state.users.values():
        for p in pos_list.positions:
            if p.coin == target_coin:
                target_asset_idx = p.asset_idx
                break
        if target_asset_idx is not None:
            break

    if target_asset_idx is None:
        logger.warning("%s: no user has a %s position, skipping", symbol, target_coin)
        return None

    mark_price = state.mark_prices.get(target_asset_idx)
    if not mark_price or mark_price <= 0:
        logger.warning("%s: mark price unavailable for asset %d, skipping", symbol, target_asset_idx)
        return None
    current_price = mark_price

    long_buckets: dict[float, float] = {}
    short_buckets: dict[float, float] = {}
    oor_long = 0.0
    oor_short = 0.0

    for user_state in state.users.values():
        target_pos = next(
            (p for p in user_state.positions if p.coin == target_coin), None
        )
        if not target_pos or target_pos.size == 0:
            continue

        liq_px = reconstructor.solve_liquidation_price(
            user_state=user_state,
            target_coin=target_coin,
            mark_prices=state.mark_prices,
            asset_margin_tiers=state.asset_margin_tiers,
        )
        if liq_px is None or liq_px <= 0:
            continue

        mark = state.mark_prices.get(target_pos.asset_idx, target_pos.entry_px)
        notional = abs(target_pos.size) * mark
        rounded_bin = round(
            math.floor(liq_px / bin_size + 1e-9) * bin_size, 10
        )

        # Outlier segregation: volume still counted in stats, but segregated
        is_outlier = (
            liq_px > mark_price * OUTLIER_HIGH_MULT
            or liq_px < mark_price * OUTLIER_LOW_MULT
        )

        if target_pos.size > 0:
            if is_outlier:
                oor_long += notional
            else:
                long_buckets[rounded_bin] = long_buckets.get(rounded_bin, 0) + notional
        else:
            if is_outlier:
                oor_short += notional
            else:
                short_buckets[rounded_bin] = short_buckets.get(rounded_bin, 0) + notional

    all_prices = sorted(set(list(long_buckets.keys()) + list(short_buckets.keys())))
    grid_min, grid_max = _compute_display_range(all_prices, current_price)

    # Build bucket lists with a single "cross-margin" leverage tier
    long_bucket_list = [
        {"price_level": p, "leverage": "cross", "volume": v}
        for p, v in sorted(long_buckets.items())
    ]
    short_bucket_list = [
        {"price_level": p, "leverage": "cross", "volume": v}
        for p, v in sorted(short_buckets.items())
    ]

    cumulative_long = _build_cumulative(long_buckets, current_price, "long")
    cumulative_short = _build_cumulative(short_buckets, current_price, "short")

    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    payload = {
        "source": "hyperliquid-sidecar",
        "symbol": f"{symbol}USDT",
        "timeframe": "1w",
        "current_price": current_price,
        "mark_price": mark_price,
        "account_count": len(state.users),
        "generated_at": generated_at,
        "grid": {
            "step": bin_size,
            "anchor_price": current_price,
            "min_price": grid_min,
            "max_price": grid_max,
        },
        "leverage_ladder": ["cross"],
        "long_buckets": long_bucket_list,
        "short_buckets": short_bucket_list,
        "cumulative_long": cumulative_long,
        "cumulative_short": cumulative_short,
        "out_of_range_volume": {"long": round(oor_long, 2), "short": round(oor_short, 2)},
        "source_anchor": str(plan.anchor_coverage.latest_anchor_in_window),
        "bin_size": bin_size,
    }

    logger.info(
        "%s: %d long bins, %d short bins, mark=%.2f, OOR L=%.0f S=%.0f",
        symbol,
        len(long_bucket_list),
        len(short_bucket_list),
        mark_price,
        oor_long,
        oor_short,
    )
    return payload


def atomic_write_json(payload: dict, dest: Path) -> None:
    """Write JSON atomically via tmp + rename."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(dest.parent), suffix=".tmp", prefix=f".{dest.name}"
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, indent=2)
        os.rename(tmp_path, str(dest))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def main() -> int:
    for symbol in SYMBOLS:
        try:
            payload = generate_symbol(symbol)
            if payload is None:
                continue
            dest = CACHE_DIR / f"hl_sidecar_{symbol.lower()}usdt.json"
            atomic_write_json(payload, dest)
            logger.info("Written %s", dest)
        except Exception:
            logger.exception("Failed to generate %s", symbol)
        finally:
            gc.collect()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
