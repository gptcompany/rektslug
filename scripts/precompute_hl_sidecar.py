#!/usr/bin/env python3
"""Pre-compute Hyperliquid sidecar liq-map JSON for BTC and ETH.

Designed to run every 15 minutes via cron. Writes atomic JSON files to
`data/cache/` that the API serves directly.

Usage:
    uv run python scripts/precompute_hl_sidecar.py
"""

from __future__ import annotations

import asyncio
import gc
import json
import logging
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.liquidationheatmap.hyperliquid.api_client import HyperliquidInfoClient
from src.liquidationheatmap.hyperliquid.margin_validator import MarginValidator
from src.liquidationheatmap.hyperliquid.models import (
    AssetMetaSnapshot,
    BorrowLendReserveState,
    ClearinghouseUserState,
)
from src.liquidationheatmap.hyperliquid.portfolio_solver import (
    HyperliquidPortfolioMarginSolver,
)
from src.liquidationheatmap.hyperliquid.sidecar import (
    HyperliquidSidecarPrototypeBuilder,
    SidecarBuildRequest,
    SidecarPositionReconstructor,
    SidecarState,
    UserPosition,
    UserState,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)

CACHE_DIR = Path("data/cache")
SYMBOLS = ["BTC", "ETH"]
TIMEFRAME_DAYS = 7
# Outlier threshold: bins beyond 5x or below 0.1x mark price are segregated.
OUTLIER_HIGH_MULT = 5.0
OUTLIER_LOW_MULT = 0.1
LIVE_ENRICH_TOP_N = int(os.getenv("HEATMAP_HL_LIVE_ENRICH_TOP_N", "120"))
LIVE_ENRICH_REQUESTS_PER_MINUTE = int(
    os.getenv("HEATMAP_HL_LIVE_ENRICH_RPM", "180")
)


@dataclass(frozen=True)
class LiveUserOverride:
    user: str
    liq_px: float
    size: float
    notional: float
    source: str
    account_abstraction: str


@dataclass(frozen=True)
class LiveEnrichmentStats:
    selected_users: int = 0
    applied_users: int = 0
    removed_users: int = 0
    api_liq_users: int = 0
    solver_users: int = 0
    failed_users: int = 0
    missing_target_users: int = 0
    required_spot_users: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "selected_users": self.selected_users,
            "applied_users": self.applied_users,
            "removed_users": self.removed_users,
            "api_liq_users": self.api_liq_users,
            "solver_users": self.solver_users,
            "failed_users": self.failed_users,
            "missing_target_users": self.missing_target_users,
            "required_spot_users": self.required_spot_users,
        }


def _compute_display_range(
    long_buckets: dict[float, float],
    short_buckets: dict[float, float],
    current_price: float,
) -> tuple[float, float]:
    """Derive a display range that preserves most visible liquidation mass."""
    min_clamp = 0.12
    max_clamp = 0.9
    coverage_target = 0.85

    def side_bound(buckets: dict[float, float], *, descending: bool, fallback: float) -> float:
        if not buckets:
            return fallback
        ordered_prices = sorted(buckets.keys(), reverse=descending)
        total_volume = sum(buckets.values())
        if total_volume <= 0:
            return fallback
        threshold = total_volume * coverage_target
        running = 0.0
        for price in ordered_prices:
            running += buckets[price]
            if running >= threshold:
                return price
        return ordered_prices[-1]

    lower_default = current_price * (1 - min_clamp)
    upper_default = current_price * (1 + min_clamp)

    lower_bound = side_bound(
        {price: volume for price, volume in long_buckets.items() if price < current_price},
        descending=True,
        fallback=lower_default,
    )
    upper_bound = side_bound(
        {price: volume for price, volume in short_buckets.items() if price > current_price},
        descending=False,
        fallback=upper_default,
    )

    lower_bound = min(lower_bound, lower_default)
    upper_bound = max(upper_bound, upper_default)

    span = max(upper_bound - lower_bound, current_price * 0.02)
    padding = span * 0.04
    x_min = max(current_price * (1 - max_clamp), lower_bound - padding)
    x_max = min(current_price * (1 + max_clamp), upper_bound + padding)
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

    prices = sorted(p for p in buckets if p > current_price)
    points = [{"price_level": current_price, "value": 0.0}]
    running = 0.0
    for p in prices:
        running += buckets[p]
        points.append({"price_level": p, "value": running})
    return points


def _classify_liquidation_side(liq_px: float, current_price: float) -> str | None:
    """Map a liquidation price to the public liq-map side contract."""
    if liq_px < current_price:
        return "long"
    if liq_px > current_price:
        return "short"
    return None


def _select_top_target_users(
    state: SidecarState,
    *,
    target_coin: str,
    mark_price: float,
    top_n: int,
) -> list[str]:
    if top_n <= 0:
        return []

    ranked: list[tuple[float, str]] = []
    for user, user_state in state.users.items():
        target_pos = next(
            (
                position
                for position in user_state.positions
                if position.coin == target_coin and position.size != 0
            ),
            None,
        )
        if target_pos is None:
            continue
        ranked.append((abs(target_pos.size) * mark_price, user))

    ranked.sort(reverse=True)
    return [user for _, user in ranked[:top_n]]


def _asset_meta_tables(
    meta: AssetMetaSnapshot,
) -> tuple[dict[str, int], dict[int, float], dict[int, list[dict]]]:
    coin_to_asset_idx: dict[str, int] = {}
    mark_prices: dict[int, float] = {}
    asset_margin_tiers: dict[int, list[dict]] = {}

    for idx, asset in enumerate(meta.universe):
        coin_to_asset_idx[asset.name] = idx
        if idx < len(meta.assetContexts):
            mark_prices[idx] = meta.assetContexts[idx].markPx
        if asset.marginTableId in meta.margin_tables:
            asset_margin_tiers[idx] = [
                {
                    "lower_bound": tier.lower_bound,
                    "mmr_rate": tier.mmr_rate,
                    "maintenance_deduction": tier.maintenance_deduction,
                }
                for tier in meta.margin_tables[asset.marginTableId]
            ]
        else:
            max_lev = asset.maxLeverage
            mmr_rate = 1.0 / (2.0 * max_lev) if max_lev > 0 else 0.01
            asset_margin_tiers[idx] = [
                {"lower_bound": 0, "mmr_rate": mmr_rate, "maintenance_deduction": 0.0}
            ]

    return coin_to_asset_idx, mark_prices, asset_margin_tiers


def _build_live_positions(
    clearinghouse_state: ClearinghouseUserState,
    *,
    coin_to_asset_idx: dict[str, int],
) -> list[UserPosition]:
    positions: list[UserPosition] = []
    for api_position in clearinghouse_state.assetPositions:
        position = api_position.position
        if position.szi == 0:
            continue
        asset_idx = coin_to_asset_idx.get(position.coin)
        if asset_idx is None:
            continue
        positions.append(
            UserPosition(
                coin=position.coin,
                asset_idx=asset_idx,
                size=position.szi,
                entry_px=position.entryPx,
                leverage=float(position.leverage.value),
                cum_funding=position.cumFunding.sinceOpen,
                margin=position.marginUsed,
            )
        )
    return positions


async def _load_live_override(
    *,
    user: str,
    target_coin: str,
    client: HyperliquidInfoClient,
    reconstructor: SidecarPositionReconstructor,
    portfolio_solver: HyperliquidPortfolioMarginSolver,
    coin_to_asset_idx: dict[str, int],
    mark_prices: dict[int, float],
    asset_margin_tiers: dict[int, list[dict]],
    reserve_states: dict[int, BorrowLendReserveState],
) -> tuple[LiveUserOverride | None, str]:
    clearinghouse_state, account_abstraction = await asyncio.gather(
        client.get_clearinghouse_state(user),
        client.get_user_abstraction(user),
    )
    target_api_position = next(
        (
            api_position.position
            for api_position in clearinghouse_state.assetPositions
            if api_position.position.coin == target_coin and api_position.position.szi != 0
        ),
        None,
    )
    if target_api_position is None:
        return None, "missing_target"

    target_asset_idx = coin_to_asset_idx.get(target_coin)
    mark = mark_prices.get(target_asset_idx, 0.0)
    if mark <= 0 and target_api_position.szi != 0:
        mark = abs(target_api_position.positionValue) / abs(target_api_position.szi)
    notional = abs(target_api_position.positionValue) or abs(target_api_position.szi) * mark

    if target_api_position.liquidationPx is not None and target_api_position.liquidationPx > 0:
        return (
            LiveUserOverride(
                user=user,
                liq_px=target_api_position.liquidationPx,
                size=target_api_position.szi,
                notional=notional,
                source="api",
                account_abstraction=account_abstraction.value,
            ),
            "api",
        )

    live_positions = _build_live_positions(
        clearinghouse_state,
        coin_to_asset_idx=coin_to_asset_idx,
    )
    if not live_positions:
        return None, "missing_target"

    if MarginValidator.requires_spot_clearinghouse_state(account_abstraction):
        spot_state, borrow_lend_user_state = await asyncio.gather(
            client.get_spot_clearinghouse_state(user),
            client.get_borrow_lend_user_state(user),
        )
        liq_px = portfolio_solver.solve_portfolio_liquidation_price(
            user_address=user,
            positions=live_positions,
            target_coin=target_coin,
            mark_prices=mark_prices,
            asset_margin_tiers=asset_margin_tiers,
            spot_state=spot_state,
            cross_maintenance_margin_used=clearinghouse_state.crossMaintenanceMarginUsed,
            borrow_lend_user_state=borrow_lend_user_state,
            reserve_states=reserve_states,
        )
        if liq_px is None or liq_px <= 0:
            return None, "solver_failed"
        return (
            LiveUserOverride(
                user=user,
                liq_px=liq_px,
                size=target_api_position.szi,
                notional=notional,
                source="solver_spot",
                account_abstraction=account_abstraction.value,
            ),
            "solver_spot",
        )

    user_state = UserState(
        user=user,
        balance=clearinghouse_state.crossMarginSummary.totalRawUsd,
        positions=tuple(live_positions),
    )
    liq_px = reconstructor.solve_liquidation_price(
        user_state=user_state,
        target_coin=target_coin,
        mark_prices=mark_prices,
        asset_margin_tiers=asset_margin_tiers,
    )
    if liq_px is None or liq_px <= 0:
        return None, "solver_failed"
    return (
        LiveUserOverride(
            user=user,
            liq_px=liq_px,
            size=target_api_position.szi,
            notional=notional,
            source="solver_cross",
            account_abstraction=account_abstraction.value,
        ),
        "solver_cross",
    )


async def _build_live_overrides(
    state: SidecarState,
    *,
    target_coin: str,
    mark_price: float,
) -> tuple[dict[str, LiveUserOverride | None], LiveEnrichmentStats]:
    selected_users = _select_top_target_users(
        state,
        target_coin=target_coin,
        mark_price=mark_price,
        top_n=LIVE_ENRICH_TOP_N,
    )
    if not selected_users:
        return {}, LiveEnrichmentStats()

    client = HyperliquidInfoClient(
        requests_per_minute=LIVE_ENRICH_REQUESTS_PER_MINUTE
    )
    meta, reserve_states = await asyncio.gather(
        client.get_asset_meta(),
        client.get_all_borrow_lend_reserve_states(),
    )
    coin_to_asset_idx, live_mark_prices, live_asset_margin_tiers = _asset_meta_tables(meta)
    reconstructor = SidecarPositionReconstructor()
    portfolio_solver = HyperliquidPortfolioMarginSolver()

    overrides: dict[str, LiveUserOverride | None] = {}
    stats = {
        "selected_users": len(selected_users),
        "applied_users": 0,
        "removed_users": 0,
        "api_liq_users": 0,
        "solver_users": 0,
        "failed_users": 0,
        "missing_target_users": 0,
        "required_spot_users": 0,
    }

    async def load_one(user: str) -> None:
        try:
            override, mode = await _load_live_override(
                user=user,
                target_coin=target_coin,
                client=client,
                reconstructor=reconstructor,
                portfolio_solver=portfolio_solver,
                coin_to_asset_idx=coin_to_asset_idx,
                mark_prices=live_mark_prices,
                asset_margin_tiers=live_asset_margin_tiers,
                reserve_states=reserve_states,
            )
        except Exception as exc:
            logger.warning("%s: live enrichment failed for %s: %s", target_coin, user, exc)
            stats["failed_users"] += 1
            return

        if mode == "missing_target":
            overrides[user] = None
            stats["removed_users"] += 1
            stats["missing_target_users"] += 1
            return

        if override is None:
            stats["failed_users"] += 1
            return

        overrides[user] = override
        stats["applied_users"] += 1
        if override.source == "api":
            stats["api_liq_users"] += 1
        else:
            stats["solver_users"] += 1
            if override.source == "solver_spot":
                stats["required_spot_users"] += 1

    await asyncio.gather(*(load_one(user) for user in selected_users))
    return overrides, LiveEnrichmentStats(**stats)


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
        symbol,
        len(state.users),
    )

    reconstructor = SidecarPositionReconstructor()
    bin_size = plan.bin_size
    target_coin = request.target_coin

    target_asset_idx = None
    for pos_list in state.users.values():
        for position in pos_list.positions:
            if position.coin == target_coin:
                target_asset_idx = position.asset_idx
                break
        if target_asset_idx is not None:
            break

    if target_asset_idx is None:
        logger.warning("%s: no user has a %s position, skipping", symbol, target_coin)
        return None

    mark_price = state.mark_prices.get(target_asset_idx)
    if not mark_price or mark_price <= 0:
        logger.warning(
            "%s: mark price unavailable for asset %d, skipping",
            symbol,
            target_asset_idx,
        )
        return None
    current_price = mark_price

    live_overrides: dict[str, LiveUserOverride | None] = {}
    live_enrichment_stats = LiveEnrichmentStats()
    if LIVE_ENRICH_TOP_N > 0:
        try:
            live_overrides, live_enrichment_stats = asyncio.run(
                _build_live_overrides(
                    state,
                    target_coin=target_coin,
                    mark_price=mark_price,
                )
            )
            logger.info(
                "%s: live enrichment selected=%d applied=%d removed=%d api=%d solver=%d failed=%d",
                symbol,
                live_enrichment_stats.selected_users,
                live_enrichment_stats.applied_users,
                live_enrichment_stats.removed_users,
                live_enrichment_stats.api_liq_users,
                live_enrichment_stats.solver_users,
                live_enrichment_stats.failed_users,
            )
        except Exception:
            logger.exception("%s: live enrichment failed; continuing with snapshot state", symbol)
            live_overrides = {}
            live_enrichment_stats = LiveEnrichmentStats()

    long_buckets: dict[float, float] = {}
    short_buckets: dict[float, float] = {}
    oor_long = 0.0
    oor_short = 0.0
    skipped_at_mark = 0
    sign_mismatch_long = 0
    sign_mismatch_short = 0
    sign_mismatch_long_volume = 0.0
    sign_mismatch_short_volume = 0.0

    for user, user_state in state.users.items():
        target_pos = next(
            (position for position in user_state.positions if position.coin == target_coin),
            None,
        )
        if not target_pos or target_pos.size == 0:
            continue

        liq_px: float | None
        notional: float
        position_size: float

        if user in live_overrides:
            override = live_overrides[user]
            if override is None:
                continue
            liq_px = override.liq_px
            notional = override.notional
            position_size = override.size
        else:
            liq_px = reconstructor.solve_liquidation_price(
                user_state=user_state,
                target_coin=target_coin,
                mark_prices=state.mark_prices,
                asset_margin_tiers=state.asset_margin_tiers,
            )
            mark = state.mark_prices.get(target_pos.asset_idx, target_pos.entry_px)
            notional = abs(target_pos.size) * mark
            position_size = target_pos.size

        if liq_px is None or liq_px <= 0:
            continue

        rounded_bin = round(math.floor(liq_px / bin_size + 1e-9) * bin_size, 10)
        liquidation_side = _classify_liquidation_side(liq_px, current_price)
        if liquidation_side is None:
            skipped_at_mark += 1
            continue

        is_outlier = (
            liq_px > mark_price * OUTLIER_HIGH_MULT
            or liq_px < mark_price * OUTLIER_LOW_MULT
        )

        if position_size > 0 and liquidation_side != "long":
            sign_mismatch_long += 1
            sign_mismatch_long_volume += notional
        elif position_size < 0 and liquidation_side != "short":
            sign_mismatch_short += 1
            sign_mismatch_short_volume += notional

        if liquidation_side == "long":
            if is_outlier:
                oor_long += notional
            else:
                long_buckets[rounded_bin] = long_buckets.get(rounded_bin, 0.0) + notional
        else:
            if is_outlier:
                oor_short += notional
            else:
                short_buckets[rounded_bin] = short_buckets.get(rounded_bin, 0.0) + notional

    grid_min, grid_max = _compute_display_range(
        long_buckets,
        short_buckets,
        current_price,
    )

    long_bucket_list = [
        {"price_level": price, "leverage": "cross", "volume": volume}
        for price, volume in sorted(long_buckets.items())
    ]
    short_bucket_list = [
        {"price_level": price, "leverage": "cross", "volume": volume}
        for price, volume in sorted(short_buckets.items())
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
        "out_of_range_volume": {
            "long": round(oor_long, 2),
            "short": round(oor_short, 2),
        },
        "source_anchor": str(plan.anchor_coverage.latest_anchor_in_window),
        "bin_size": bin_size,
        "live_enrichment": live_enrichment_stats.to_dict(),
    }

    logger.info(
        (
            "%s: %d long bins, %d short bins, mark=%.2f, "
            "OOR L=%.0f S=%.0f, skipped_at_mark=%d, "
            "sign_mismatch_long=%d ($%.0f), sign_mismatch_short=%d ($%.0f)"
        ),
        symbol,
        len(long_bucket_list),
        len(short_bucket_list),
        mark_price,
        oor_long,
        oor_short,
        skipped_at_mark,
        sign_mismatch_long,
        sign_mismatch_long_volume,
        sign_mismatch_short,
        sign_mismatch_short_volume,
    )
    return payload


def atomic_write_json(payload: dict, dest: Path) -> None:
    """Write JSON atomically via tmp + rename."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(dest.parent), suffix=".tmp", prefix=f".{dest.name}"
    )
    try:
        with os.fdopen(fd, "w") as file_handle:
            json.dump(payload, file_handle, indent=2)
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
