"""Liquidation map data class for Nautilus Trader backtest events.

Defines LiquidationMapData and feature computation from expert snapshot artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class LiquidationMapData:
    """Liquidation map snapshot as a Nautilus Trader custom event.

    Emitted once per expert_id per snapshot timestamp.
    Strategy receives this via on_data() and can react to proximity/imbalance signals.
    """

    ts_event: int  # nanoseconds UTC (snapshot_ts converted)
    ts_init: int  # nanoseconds UTC (when loaded into engine)

    expert_id: str  # v1, v2, v3, v4, v5
    symbol: str  # BTCUSDT
    exchange: str  # hyperliquid, binance, bybit
    reference_price: float

    # Pre-computed features from distribution
    nearest_long_liq: float  # price of nearest long liquidation cluster
    nearest_short_liq: float  # price of nearest short liquidation cluster
    long_distance_pct: float  # distance % from reference price to nearest long
    short_distance_pct: float  # distance % from reference price to nearest short
    total_long_volume: float  # aggregate long liquidation volume
    total_short_volume: float  # aggregate short liquidation volume
    net_imbalance: float  # (long - short) / (long + short), range [-1, 1]
    top_long_cluster_price: float  # price level with highest long volume
    top_short_cluster_price: float  # price level with highest short volume

    # Raw distributions (optional, for advanced strategies)
    long_distribution: dict[str, float] | None = field(default=None, repr=False)
    short_distribution: dict[str, float] | None = field(default=None, repr=False)


@dataclass
class LiquidationSignalData:
    """A specific liquidation signal event for Nautilus.
    
    Derived from LiquidationSignal in the adaptive signal loop.
    Emitted on real-time signal reception via Redis.
    """
    ts_event: int  # nanoseconds UTC
    ts_init: int   # nanoseconds UTC
    
    symbol: str
    price: float
    side: str      # long or short
    confidence: float
    source: str
    signal_id: str | None = None


def compute_features(
    long_dist: dict[str, float],
    short_dist: dict[str, float],
    reference_price: float,
) -> dict[str, Any]:
    """Compute pre-aggregated features from raw price-level distributions.

    Args:
        long_dist: {price_level_str: volume} for long liquidations
        short_dist: {price_level_str: volume} for short liquidations
        reference_price: current/reference price at snapshot time

    Returns:
        Dict with all computed feature fields for LiquidationMapData.
    """
    if reference_price <= 0:
        raise ValueError(f"reference_price must be positive: {reference_price}")

    total_long = sum(long_dist.values()) if long_dist else 0.0
    total_short = sum(short_dist.values()) if short_dist else 0.0
    total = total_long + total_short

    # Net imbalance: [-1, 1] where positive = long-heavy
    net_imbalance = (total_long - total_short) / total if total > 0 else 0.0

    # Find nearest and top clusters
    nearest_long_price, nearest_long_dist = _find_nearest_cluster(long_dist, reference_price)
    nearest_short_price, nearest_short_dist = _find_nearest_cluster(short_dist, reference_price)
    top_long_price = _find_top_cluster(long_dist)
    top_short_price = _find_top_cluster(short_dist)

    return {
        "nearest_long_liq": nearest_long_price,
        "nearest_short_liq": nearest_short_price,
        "long_distance_pct": nearest_long_dist,
        "short_distance_pct": nearest_short_dist,
        "total_long_volume": total_long,
        "total_short_volume": total_short,
        "net_imbalance": net_imbalance,
        "top_long_cluster_price": top_long_price,
        "top_short_cluster_price": top_short_price,
    }


def _find_nearest_cluster(dist: dict[str, float], reference_price: float) -> tuple[float, float]:
    """Find the price level closest to reference_price with non-zero volume.

    Returns:
        (price_level, distance_pct) where distance_pct is abs distance as fraction.
        Returns (0.0, 1.0) if distribution is empty.
    """
    if not dist:
        return 0.0, 1.0

    best_price = 0.0
    best_distance = float("inf")

    for price_str, volume in dist.items():
        if volume <= 0:
            continue
        price = float(price_str)
        distance = abs(price - reference_price)
        if distance < best_distance:
            best_distance = distance
            best_price = price

    if best_distance == float("inf"):
        return 0.0, 1.0

    distance_pct = best_distance / reference_price
    return best_price, distance_pct


def _find_top_cluster(dist: dict[str, float]) -> float:
    """Find the price level with the highest volume.

    Returns 0.0 if distribution is empty.
    """
    if not dist:
        return 0.0

    top_price = 0.0
    top_volume = 0.0

    for price_str, volume in dist.items():
        if volume > top_volume:
            top_volume = volume
            top_price = float(price_str)

    return top_price


def iso_to_nanos(iso_str: str) -> int:
    """Convert ISO8601 UTC timestamp string to nanoseconds since epoch.

    Supports formats like '2026-04-05T14:30:00Z' and '2026-04-05T14:30:00.123Z'.
    """
    # Strip trailing Z and parse
    cleaned = iso_str.rstrip("Z")
    if "." in cleaned:
        dt = datetime.strptime(cleaned, "%Y-%m-%dT%H:%M:%S.%f")
    else:
        dt = datetime.strptime(cleaned, "%Y-%m-%dT%H:%M:%S")
    dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1_000_000_000)
