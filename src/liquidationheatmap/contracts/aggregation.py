"""Reusable aggregation logic for liquidation levels."""

from decimal import Decimal, ROUND_HALF_UP
from typing import List, Tuple, Dict
from src.liquidationheatmap.models.base import LiquidationLevel
from src.liquidationheatmap.modeled_snapshots.snapshot_schema import BucketGrid

def _round_to_bucket(value: float, bin_size: float) -> Decimal:
    """Round a value to the nearest bin_size-aligned bucket."""
    value_decimal = Decimal(str(value))
    bin_decimal = Decimal(str(bin_size))
    if bin_decimal <= 0:
        return value_decimal

    return (value_decimal / bin_decimal).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    ) * bin_decimal

def aggregate_to_bucket_grid(
    levels: List[LiquidationLevel], 
    bin_size: float
) -> Tuple[BucketGrid, Dict[str, float], Dict[str, float]]:
    """
    Convert a list of liquidation levels into a bucketed distribution.
    
    Returns:
        (BucketGrid, long_distribution, short_distribution)
    """
    if not levels:
        return BucketGrid(price_levels=[]), {}, {}

    long_dist: Dict[str, float] = {}
    short_dist: Dict[str, float] = {}
    
    all_prices = []

    for level in levels:
        bucket_price = _round_to_bucket(float(level.price_level), bin_size)
        bucket_str = str(float(bucket_price))
        volume = float(level.liquidation_volume)
        
        side = level.side.lower()
        if side in ("buy", "long"): # Long liquidations (positions were long, they sell to liquidate? No, usually long_liquidations means liquidations of long positions)
            long_dist[bucket_str] = long_dist.get(bucket_str, 0.0) + volume
        elif side in ("sell", "short"):
            short_dist[bucket_str] = short_dist.get(bucket_str, 0.0) + volume
            
        all_prices.append(float(bucket_price))

    if not all_prices:
        return BucketGrid(price_levels=[]), {}, {}

    grid = BucketGrid(
        min_price=min(all_prices),
        max_price=max(all_prices),
        step=float(bin_size)
    )
    
    return grid, long_dist, short_dist
