"""Adaptive primitives for scorecard logic.

Functions in this module provide data-derived observation layers, overriding
fixed constants like touch bands, window sizes, and bucket boundaries.
"""

import math
from datetime import datetime
from typing import Any

from src.liquidationheatmap.models.scorecard import QuantileBucketSet
from src.liquidationheatmap.scorecard.builder import _coerce_timestamp


def extract_volume(tick: dict[str, Any]) -> float | None:
    """Extract optional quote-notional volume from a price-path tick."""
    if "volume" in tick and tick["volume"] is not None:
        return float(tick["volume"])
    return None


def compute_realized_volatility(
    price_path: list[dict[str, Any]], timestamp: datetime, lookback_ticks: int
) -> int:
    """Compute realized volatility in annualized bps from log-returns.

    If there are fewer than 2 ticks in the lookback window, returns 0.
    Assumes the adaptive layer primary contract is `klines_1m_history`, so the
    annualization factor uses one-minute bars.
    """
    normalized_timestamp = _coerce_timestamp(timestamp)
    normalized_ticks = sorted(
        (
            {
                "timestamp": _coerce_timestamp(tick["timestamp"]),
                "price": float(tick["price"]),
            }
            for tick in price_path
        ),
        key=lambda tick: tick["timestamp"],
    )
    valid_ticks = [tick for tick in normalized_ticks if tick["timestamp"] <= normalized_timestamp]
    valid_ticks = valid_ticks[-lookback_ticks:]

    if len(valid_ticks) < 2:
        return 0

    prices = [tick["price"] for tick in valid_ticks]
    log_returns = [math.log(prices[i] / prices[i - 1]) for i in range(1, len(prices))]
    mean = sum(log_returns) / len(log_returns)
    variance = (
        sum((value - mean) ** 2 for value in log_returns) / (len(log_returns) - 1)
        if len(log_returns) > 1
        else 0.0
    )
    std_dev = math.sqrt(variance)

    ticks_per_year = 365 * 24 * 60
    annualized_vol = std_dev * math.sqrt(ticks_per_year)
    return int(annualized_vol * 10000)


def compute_adaptive_touch_band(
    price_path: list[dict[str, Any]], snapshot_ts: datetime, symbol: str
) -> int:
    """Compute volatility-derived touch band in bps.

    Uses `compute_realized_volatility` to find local volatility.
    If sufficient history is missing, falls back to a price spread proxy.
    """
    # 60 ticks assuming 1m resolution (1 hour lookback)
    lookback_ticks = 60

    vol_bps = compute_realized_volatility(price_path, snapshot_ts, lookback_ticks)

    if vol_bps > 0:
        # MVP heuristic: map annualized vol to a small operational tolerance band.
        # This is a documented computation-method constant, not a market threshold.
        return max(1, int(vol_bps / 500))

    # Fallback: normalized price-spread proxy over the same effective path.
    normalized_snapshot_ts = _coerce_timestamp(snapshot_ts)
    normalized_ticks = sorted(
        (
            {
                "timestamp": _coerce_timestamp(tick["timestamp"]),
                "price": float(tick["price"]),
            }
            for tick in price_path
        ),
        key=lambda tick: tick["timestamp"],
    )
    valid_ticks = [
        tick for tick in normalized_ticks if tick["timestamp"] <= normalized_snapshot_ts
    ]
    if not valid_ticks:
        return 1

    prices = [tick["price"] for tick in valid_ticks]
    min_price = min(prices)
    max_price = max(prices)
    mean_price = sum(prices) / len(prices)

    if mean_price > 0:
        spread_bps = int(((max_price - min_price) / mean_price) * 10000)
        # MVP heuristic: half-spread proxy with a 1 bps floor.
        return max(1, int(spread_bps / 2))
    return 1


def compute_volume_threshold(price_path: list[dict[str, Any]], snapshot_ts: datetime) -> float:
    """Compute cumulative volume threshold for window closure."""
    raise NotImplementedError


def compute_quantile_buckets(
    values: list[float], metric_name: str, min_per_bucket: int
) -> QuantileBucketSet:
    """Compute data-derived bucket boundaries from empirical quantiles."""
    raise NotImplementedError


def infer_regime_map(
    observations: list[Any], price_path: list[dict[str, Any]]
) -> dict[datetime, str]:
    """Infer regime labels from volatility quantiles."""
    raise NotImplementedError
