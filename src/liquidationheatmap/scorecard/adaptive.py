"""Adaptive primitives for scorecard logic.

Functions in this module provide data-derived observation layers, overriding
fixed constants like touch bands, window sizes, and bucket boundaries.
"""

import math
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.liquidationheatmap.models.scorecard import QuantileBucketSet


def extract_volume(tick: Dict[str, Any]) -> Optional[float]:
    """Extract optional volume from a price path tick."""
    if "volume" in tick and tick["volume"] is not None:
        return float(tick["volume"])
    return None


def compute_realized_volatility(
    price_path: List[Dict[str, Any]], timestamp: datetime, lookback_ticks: int
) -> int:
    """Compute realized volatility in annualized bps from log-returns.

    If there are fewer than 2 ticks in the lookback window, returns 0.
    Assumes 1m klines for annualization factor (525600 ticks/year).
    """
    # Filter path up to timestamp
    valid_ticks = [t for t in price_path if t["timestamp"] <= timestamp]

    # Take last `lookback_ticks`
    valid_ticks = valid_ticks[-lookback_ticks:]

    if len(valid_ticks) < 2:
        return 0

    prices = [t["price"] for t in valid_ticks]

    # Log returns
    log_returns = [math.log(prices[i] / prices[i - 1]) for i in range(1, len(prices))]

    # Std dev of log returns
    mean = sum(log_returns) / len(log_returns)
    variance = (
        sum((r - mean) ** 2 for r in log_returns) / (len(log_returns) - 1)
        if len(log_returns) > 1
        else 0.0
    )
    std_dev = math.sqrt(variance)

    # Annualize (assuming 1m ticks)
    ticks_per_year = 365 * 24 * 60
    annualized_vol = std_dev * math.sqrt(ticks_per_year)

    # Convert to bps
    return int(annualized_vol * 10000)

def compute_adaptive_touch_band(
    price_path: List[Dict[str, Any]], snapshot_ts: datetime, symbol: str
) -> int:
    """Compute volatility-derived touch band."""
    raise NotImplementedError


def compute_volume_threshold(
    price_path: List[Dict[str, Any]], snapshot_ts: datetime
) -> float:
    """Compute cumulative volume threshold for window closure."""
    raise NotImplementedError


def compute_quantile_buckets(
    values: List[float], metric_name: str, min_per_bucket: int
) -> QuantileBucketSet:
    """Compute data-derived bucket boundaries from empirical quantiles."""
    raise NotImplementedError


def infer_regime_map(
    observations: List[Any], price_path: List[Dict[str, Any]]
) -> Dict[datetime, str]:
    """Infer regime labels from volatility quantiles."""
    raise NotImplementedError
