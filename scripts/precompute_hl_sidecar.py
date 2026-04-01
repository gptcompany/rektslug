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
    AccountAbstraction,
    AssetMetaSnapshot,
    BorrowLendReserveState,
    BorrowLendUserState,
    ClearinghouseUserState,
    SpotClearinghouseState,
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
TOP_POSITION_TOP_N = int(os.getenv("HEATMAP_HL_TOP_POSITION_TOP_N", "250"))
TOP_POSITION_SELECTION_MODE = os.getenv(
    "HEATMAP_HL_TOP_POSITION_SELECTION_MODE",
    "global",
).strip().lower()
LIVE_ENRICH_TOP_N = int(os.getenv("HEATMAP_HL_LIVE_ENRICH_TOP_N", "120"))
LIVE_ENRICH_REQUESTS_PER_MINUTE = int(
    os.getenv("HEATMAP_HL_LIVE_ENRICH_RPM", "180")
)
LIVE_ENRICH_BATCH_SIZE = max(
    1,
    int(os.getenv("HEATMAP_HL_LIVE_ENRICH_BATCH_SIZE", "25")),
)
LIVE_ENRICH_CACHE_TTL_SECONDS = max(
    0,
    int(os.getenv("HEATMAP_HL_LIVE_ENRICH_CACHE_TTL_SECONDS", "900")),
)
LIVE_ENRICH_CACHE_FILE = Path(
    os.getenv(
        "HEATMAP_HL_LIVE_ENRICH_CACHE_FILE",
        str(CACHE_DIR / "hl_live_enrichment_cache.json"),
    )
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
    cached_users: int = 0
    fetched_users: int = 0
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
            "cached_users": self.cached_users,
            "fetched_users": self.fetched_users,
            "applied_users": self.applied_users,
            "removed_users": self.removed_users,
            "api_liq_users": self.api_liq_users,
            "solver_users": self.solver_users,
            "failed_users": self.failed_users,
            "missing_target_users": self.missing_target_users,
            "required_spot_users": self.required_spot_users,
        }


@dataclass(frozen=True)
class SymbolBuildContext:
    symbol: str
    request: SidecarBuildRequest
    plan: object
    state: SidecarState
    reconstructor: SidecarPositionReconstructor
    bin_size: float
    target_coin: str
    mark_price: float
    current_price: float
    live_overrides: dict[str, LiveUserOverride | None]
    live_enrichment_stats: LiveEnrichmentStats


@dataclass(frozen=True)
class LiveEnrichmentCacheEntry:
    refreshed_at_epoch: float
    status: str
    override: LiveUserOverride | None = None


class LiveEnrichmentCache:
    """TTL cache for per-user live overrides across precompute runs."""

    def __init__(
        self,
        *,
        path: Path | None = None,
        ttl_seconds: int | None = None,
        entries: dict[str, LiveEnrichmentCacheEntry] | None = None,
    ) -> None:
        self.path = path or LIVE_ENRICH_CACHE_FILE
        self.ttl_seconds = (
            LIVE_ENRICH_CACHE_TTL_SECONDS if ttl_seconds is None else ttl_seconds
        )
        self.entries = entries or {}
        self._dirty = False

    @property
    def enabled(self) -> bool:
        return self.ttl_seconds > 0

    @classmethod
    def load(
        cls,
        *,
        path: Path | None = None,
        ttl_seconds: int | None = None,
    ) -> "LiveEnrichmentCache":
        resolved_path = path or LIVE_ENRICH_CACHE_FILE
        cache = cls(path=path, ttl_seconds=ttl_seconds)
        if not cache.enabled or not resolved_path.exists():
            return cache

        try:
            payload = json.loads(resolved_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Failed to read live enrichment cache %s", resolved_path)
            return cache

        raw_entries = payload.get("entries", {})
        if not isinstance(raw_entries, dict):
            return cache

        for key, item in raw_entries.items():
            if not isinstance(item, dict):
                continue
            refreshed_at_epoch = float(item.get("refreshed_at_epoch", 0.0))
            status = str(item.get("status", "")).strip()
            if refreshed_at_epoch <= 0 or status not in {"override", "missing_target"}:
                continue
            override_payload = item.get("override")
            override = None
            if status == "override" and isinstance(override_payload, dict):
                try:
                    override = LiveUserOverride(
                        user=str(override_payload["user"]),
                        liq_px=float(override_payload["liq_px"]),
                        size=float(override_payload["size"]),
                        notional=float(override_payload["notional"]),
                        source=str(override_payload["source"]),
                        account_abstraction=str(override_payload["account_abstraction"]),
                    )
                except (KeyError, TypeError, ValueError):
                    continue
            cache.entries[key] = LiveEnrichmentCacheEntry(
                refreshed_at_epoch=refreshed_at_epoch,
                status=status,
                override=override,
            )

        return cache

    @staticmethod
    def _make_key(*, user: str, target_coin: str) -> str:
        return f"{target_coin.upper()}:{user.lower()}"

    def get(self, *, user: str, target_coin: str) -> LiveEnrichmentCacheEntry | None:
        if not self.enabled:
            return None

        entry = self.entries.get(self._make_key(user=user, target_coin=target_coin))
        if entry is None:
            return None

        age_seconds = datetime.now(timezone.utc).timestamp() - entry.refreshed_at_epoch
        if age_seconds > self.ttl_seconds:
            self.entries.pop(self._make_key(user=user, target_coin=target_coin), None)
            self._dirty = True
            return None
        return entry

    def put_override(
        self,
        *,
        user: str,
        target_coin: str,
        override: LiveUserOverride,
    ) -> None:
        self._put(
            user=user,
            target_coin=target_coin,
            status="override",
            override=override,
        )

    def put_missing_target(self, *, user: str, target_coin: str) -> None:
        self._put(
            user=user,
            target_coin=target_coin,
            status="missing_target",
            override=None,
        )

    def _put(
        self,
        *,
        user: str,
        target_coin: str,
        status: str,
        override: LiveUserOverride | None,
    ) -> None:
        if not self.enabled:
            return
        self.entries[self._make_key(user=user, target_coin=target_coin)] = (
            LiveEnrichmentCacheEntry(
                refreshed_at_epoch=datetime.now(timezone.utc).timestamp(),
                status=status,
                override=override,
            )
        )
        self._dirty = True

    def save(self) -> None:
        if not self.enabled or not self._dirty:
            return

        serialized_entries: dict[str, dict[str, object]] = {}
        for key, entry in self.entries.items():
            serialized_entries[key] = {
                "refreshed_at_epoch": entry.refreshed_at_epoch,
                "status": entry.status,
                "override": (
                    {
                        "user": entry.override.user,
                        "liq_px": entry.override.liq_px,
                        "size": entry.override.size,
                        "notional": entry.override.notional,
                        "source": entry.override.source,
                        "account_abstraction": entry.override.account_abstraction,
                    }
                    if entry.override is not None
                    else None
                ),
            }

        atomic_write_json(
            {
                "generated_at": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                "ttl_seconds": self.ttl_seconds,
                "entries": serialized_entries,
            },
            self.path,
        )
        self._dirty = False


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
    selection_mode: str = "global",
) -> list[str]:
    if top_n <= 0:
        return []

    normalized_mode = selection_mode.strip().lower()
    if normalized_mode not in {"global", "per_side"}:
        logger.warning(
            "Unknown top-position selection mode %r; falling back to global",
            selection_mode,
        )
        normalized_mode = "global"

    ranked: list[tuple[float, str]] = []
    long_ranked: list[tuple[float, str]] = []
    short_ranked: list[tuple[float, str]] = []
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
        score = abs(target_pos.size) * mark_price
        if normalized_mode == "per_side":
            if target_pos.size > 0:
                long_ranked.append((score, user))
            elif target_pos.size < 0:
                short_ranked.append((score, user))
        else:
            ranked.append((score, user))

    if normalized_mode == "global":
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [user for _, user in ranked[:top_n]]

    long_ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    short_ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    side_quota = top_n // 2
    selected = [user for _, user in long_ranked[:side_quota]]
    selected.extend(user for _, user in short_ranked[:side_quota])

    remaining_slots = max(0, top_n - len(selected))
    leftovers = long_ranked[side_quota:] + short_ranked[side_quota:]
    leftovers.sort(key=lambda item: (item[0], item[1]), reverse=True)
    selected.extend(user for _, user in leftovers[:remaining_slots])
    return selected


def _prepare_symbol_context(symbol: str) -> SymbolBuildContext | None:
    """Load the sidecar anchor and live-enrichment context for one symbol."""
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

    return SymbolBuildContext(
        symbol=symbol,
        request=request,
        plan=plan,
        state=state,
        reconstructor=reconstructor,
        bin_size=bin_size,
        target_coin=target_coin,
        mark_price=mark_price,
        current_price=current_price,
        live_overrides=live_overrides,
        live_enrichment_stats=live_enrichment_stats,
    )


def _build_public_payload(
    *,
    context: SymbolBuildContext,
    source: str,
    selected_users: set[str] | None = None,
    projection_mode: str = "full_universe",
    projection_target_count: int | None = None,
    reported_account_count: int | None = None,
    projection_selection_strategy: str | None = None,
) -> dict:
    """Build the public liq-map payload for a chosen user universe."""
    state = context.state
    target_coin = context.target_coin
    current_price = context.current_price
    mark_price = context.mark_price
    bin_size = context.bin_size

    long_buckets: dict[float, float] = {}
    short_buckets: dict[float, float] = {}
    oor_long = 0.0
    oor_short = 0.0
    skipped_at_mark = 0
    sign_mismatch_long = 0
    sign_mismatch_short = 0
    sign_mismatch_long_volume = 0.0
    sign_mismatch_short_volume = 0.0
    included_users = 0
    live_override_users = 0
    users_removed_by_live_override = 0

    if selected_users is None:
        user_items = state.users.items()
        selected_user_count = len(state.users)
    else:
        user_items = (
            (user, state.users[user])
            for user in selected_users
            if user in state.users
        )
        selected_user_count = len(selected_users)

    for user, user_state in user_items:
        target_pos = next(
            (position for position in user_state.positions if position.coin == target_coin),
            None,
        )
        if not target_pos or target_pos.size == 0:
            continue

        liq_px: float | None
        notional: float
        position_size: float

        if user in context.live_overrides:
            override = context.live_overrides[user]
            if override is None:
                users_removed_by_live_override += 1
                continue
            liq_px = override.liq_px
            notional = override.notional
            position_size = override.size
            live_override_users += 1
        else:
            liq_px = context.reconstructor.solve_liquidation_price(
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

        included_users += 1
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
        "source": source,
        "symbol": f"{context.symbol}USDT",
        "timeframe": "1w",
        "current_price": current_price,
        "mark_price": mark_price,
        "account_count": (
            reported_account_count if reported_account_count is not None else included_users
        ),
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
        "source_anchor": str(context.plan.anchor_coverage.latest_anchor_in_window),
        "bin_size": bin_size,
        "live_enrichment": context.live_enrichment_stats.to_dict(),
        "projection": {
            "mode": projection_mode,
            "selection_strategy": projection_selection_strategy,
            "selected_users": selected_user_count,
            "included_users": included_users,
            "target_count": projection_target_count,
            "live_override_users": live_override_users,
            "users_removed_by_live_override": users_removed_by_live_override,
        },
    }

    logger.info(
        (
            "%s[%s]: %d long bins, %d short bins, mark=%.2f, "
            "OOR L=%.0f S=%.0f, skipped_at_mark=%d, "
            "sign_mismatch_long=%d ($%.0f), sign_mismatch_short=%d ($%.0f)"
        ),
        context.symbol,
        projection_mode,
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


def _chunked(items: list[str], chunk_size: int) -> list[list[str]]:
    if chunk_size <= 0:
        return [items]
    return [items[index : index + chunk_size] for index in range(0, len(items), chunk_size)]


def _target_api_position_from_state(
    clearinghouse_state: ClearinghouseUserState,
    *,
    target_coin: str,
):
    return next(
        (
            api_position.position
            for api_position in clearinghouse_state.assetPositions
            if api_position.position.coin == target_coin and api_position.position.szi != 0
        ),
        None,
    )


def _record_live_override_result(
    *,
    user: str,
    target_coin: str,
    override: LiveUserOverride | None,
    mode: str,
    overrides: dict[str, LiveUserOverride | None],
    stats: dict[str, int],
    cache: LiveEnrichmentCache | None = None,
) -> None:
    if mode == "missing_target":
        overrides[user] = None
        stats["removed_users"] += 1
        stats["missing_target_users"] += 1
        if cache is not None:
            cache.put_missing_target(user=user, target_coin=target_coin)
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
    if cache is not None:
        cache.put_override(user=user, target_coin=target_coin, override=override)


def _build_live_override(
    *,
    user: str,
    target_coin: str,
    clearinghouse_state: ClearinghouseUserState,
    account_abstraction: AccountAbstraction,
    reconstructor: SidecarPositionReconstructor,
    portfolio_solver: HyperliquidPortfolioMarginSolver,
    coin_to_asset_idx: dict[str, int],
    mark_prices: dict[int, float],
    asset_margin_tiers: dict[int, list[dict]],
    reserve_states: dict[int, BorrowLendReserveState],
    spot_state: SpotClearinghouseState | None = None,
    borrow_lend_user_state: BorrowLendUserState | None = None,
) -> tuple[LiveUserOverride | None, str]:
    target_api_position = _target_api_position_from_state(
        clearinghouse_state,
        target_coin=target_coin,
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
        if spot_state is None or borrow_lend_user_state is None:
            return None, "missing_supporting_state"
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

    cache = LiveEnrichmentCache.load()
    reconstructor = SidecarPositionReconstructor()
    portfolio_solver = HyperliquidPortfolioMarginSolver()

    overrides: dict[str, LiveUserOverride | None] = {}
    stats = {
        "selected_users": len(selected_users),
        "cached_users": 0,
        "fetched_users": 0,
        "applied_users": 0,
        "removed_users": 0,
        "api_liq_users": 0,
        "solver_users": 0,
        "failed_users": 0,
        "missing_target_users": 0,
        "required_spot_users": 0,
    }

    users_to_fetch: list[str] = []
    for user in selected_users:
        cached_entry = cache.get(user=user, target_coin=target_coin)
        if cached_entry is None:
            users_to_fetch.append(user)
            continue

        stats["cached_users"] += 1
        _record_live_override_result(
            user=user,
            target_coin=target_coin,
            override=cached_entry.override,
            mode=cached_entry.status,
            overrides=overrides,
            stats=stats,
        )

    if not users_to_fetch:
        cache.save()
        return overrides, LiveEnrichmentStats(**stats)

    client = HyperliquidInfoClient(
        requests_per_minute=LIVE_ENRICH_REQUESTS_PER_MINUTE
    )
    logger.info(
        "%s: live enrichment endpoints=%s",
        target_coin,
        ",".join(client.base_urls),
    )
    if client.base_urls == [HyperliquidInfoClient.DEFAULT_BASE_URL]:
        logger.warning(
            "%s: live enrichment is using only the public Hyperliquid Info API; "
            "configure HEATMAP_HYPERLIQUID_INFO_FALLBACK_URLS for VPS/local mirrors",
            target_coin,
        )

    meta, reserve_states = await asyncio.gather(
        client.get_asset_meta(),
        client.get_all_borrow_lend_reserve_states(),
    )
    coin_to_asset_idx, live_mark_prices, live_asset_margin_tiers = _asset_meta_tables(meta)
    total_batches = math.ceil(len(users_to_fetch) / LIVE_ENRICH_BATCH_SIZE)

    for batch_index, batch in enumerate(_chunked(users_to_fetch, LIVE_ENRICH_BATCH_SIZE), start=1):
        stats["fetched_users"] += len(batch)
        logger.info(
            "%s: live enrichment batch %d/%d (%d users)",
            target_coin,
            batch_index,
            total_batches,
            len(batch),
        )
        abstractions, states = await asyncio.gather(
            client.get_user_abstractions_batch(batch),
            client.get_clearinghouse_states_batch(batch),
        )

        spot_candidates: dict[str, tuple[ClearinghouseUserState, AccountAbstraction]] = {}
        for user in batch:
            clearinghouse_state = states.get(user)
            account_abstraction = abstractions.get(user)
            if clearinghouse_state is None or account_abstraction is None:
                logger.warning("%s: live enrichment missing state for %s", target_coin, user)
                stats["failed_users"] += 1
                continue

            try:
                if MarginValidator.requires_spot_clearinghouse_state(account_abstraction):
                    target_api_position = _target_api_position_from_state(
                        clearinghouse_state,
                        target_coin=target_coin,
                    )
                    if (
                        target_api_position is not None
                        and (
                            target_api_position.liquidationPx is None
                            or target_api_position.liquidationPx <= 0
                        )
                    ):
                        spot_candidates[user] = (clearinghouse_state, account_abstraction)
                        continue

                override, mode = _build_live_override(
                    user=user,
                    target_coin=target_coin,
                    clearinghouse_state=clearinghouse_state,
                    account_abstraction=account_abstraction,
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
                continue

            _record_live_override_result(
                user=user,
                target_coin=target_coin,
                override=override,
                mode=mode,
                overrides=overrides,
                stats=stats,
                cache=cache,
            )

        if not spot_candidates:
            continue

        spot_users = list(spot_candidates.keys())
        spot_states, borrow_lend_states = await asyncio.gather(
            client.get_spot_clearinghouse_states_batch(spot_users),
            client.get_borrow_lend_user_states_batch(spot_users),
        )

        for user, (clearinghouse_state, account_abstraction) in spot_candidates.items():
            try:
                override, mode = _build_live_override(
                    user=user,
                    target_coin=target_coin,
                    clearinghouse_state=clearinghouse_state,
                    account_abstraction=account_abstraction,
                    reconstructor=reconstructor,
                    portfolio_solver=portfolio_solver,
                    coin_to_asset_idx=coin_to_asset_idx,
                    mark_prices=live_mark_prices,
                    asset_margin_tiers=live_asset_margin_tiers,
                    reserve_states=reserve_states,
                    spot_state=spot_states.get(user),
                    borrow_lend_user_state=borrow_lend_states.get(user),
                )
            except Exception as exc:
                logger.warning("%s: live enrichment failed for %s: %s", target_coin, user, exc)
                stats["failed_users"] += 1
                continue

            _record_live_override_result(
                user=user,
                target_coin=target_coin,
                override=override,
                mode=mode,
                overrides=overrides,
                stats=stats,
                cache=cache,
            )

    cache.save()
    return overrides, LiveEnrichmentStats(**stats)


def generate_symbol(symbol: str) -> dict | None:
    """Generate the liq-map payload for one symbol. Returns None on failure."""
    context = _prepare_symbol_context(symbol)
    if context is None:
        return None
    return _build_public_payload(
        context=context,
        source="hyperliquid-sidecar",
        projection_mode="full_universe",
        reported_account_count=len(context.state.users),
    )


def generate_symbol_v3(symbol: str) -> dict | None:
    """Generate the internal top-position-like liq-map payload."""
    context = _prepare_symbol_context(symbol)
    if context is None:
        return None

    selected_users = set(
        _select_top_target_users(
            context.state,
            target_coin=context.target_coin,
            mark_price=context.mark_price,
            top_n=TOP_POSITION_TOP_N,
            selection_mode=TOP_POSITION_SELECTION_MODE,
        )
    )
    if not selected_users:
        logger.warning("%s: no top-position-like users selected, skipping v3", symbol)
        return None

    return _build_public_payload(
        context=context,
        source="hyperliquid-sidecar-top-positions",
        selected_users=selected_users,
        projection_mode="top_positions_local",
        projection_target_count=TOP_POSITION_TOP_N,
        projection_selection_strategy=TOP_POSITION_SELECTION_MODE,
    )


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
            context = _prepare_symbol_context(symbol)
            if context is None:
                continue
            payload = _build_public_payload(
                context=context,
                source="hyperliquid-sidecar",
                projection_mode="full_universe",
                reported_account_count=len(context.state.users),
            )
            dest_v1 = CACHE_DIR / f"hl_sidecar_{symbol.lower()}usdt.json"
            atomic_write_json(payload, dest_v1)
            logger.info("Written %s", dest_v1)

            selected_users = set(
                _select_top_target_users(
                    context.state,
                    target_coin=context.target_coin,
                    mark_price=context.mark_price,
                    top_n=TOP_POSITION_TOP_N,
                    selection_mode=TOP_POSITION_SELECTION_MODE,
                )
            )
            if selected_users:
                payload_v3 = _build_public_payload(
                    context=context,
                    source="hyperliquid-sidecar-top-positions",
                    selected_users=selected_users,
                    projection_mode="top_positions_local",
                    projection_target_count=TOP_POSITION_TOP_N,
                    projection_selection_strategy=TOP_POSITION_SELECTION_MODE,
                )
                dest_v3 = CACHE_DIR / f"hl_sidecar_v3_{symbol.lower()}usdt.json"
                atomic_write_json(payload_v3, dest_v3)
                logger.info("Written %s", dest_v3)
            else:
                logger.warning("%s: no top-position-like users selected, v3 not written", symbol)
        except Exception:
            logger.exception("Failed to generate %s", symbol)
        finally:
            gc.collect()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
