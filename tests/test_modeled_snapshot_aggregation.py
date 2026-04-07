import pytest
from decimal import Decimal
from datetime import datetime
from src.liquidationheatmap.models.base import LiquidationLevel
from src.liquidationheatmap.contracts.aggregation import aggregate_to_bucket_grid
from src.liquidationheatmap.modeled_snapshots.snapshot_schema import BucketGrid

def test_aggregate_to_bucket_grid_simple():
    levels = [
        LiquidationLevel(
            timestamp=datetime.now(),
            symbol="BTCUSDT",
            price_level=Decimal("50002"),
            liquidation_volume=Decimal("10.5"),
            leverage_tier="50x",
            side="buy",
            confidence=Decimal("1.0")
        ),
        LiquidationLevel(
            timestamp=datetime.now(),
            symbol="BTCUSDT",
            price_level=Decimal("50007"),
            liquidation_volume=Decimal("5.5"),
            leverage_tier="50x",
            side="buy",
            confidence=Decimal("1.0")
        ),
        LiquidationLevel(
            timestamp=datetime.now(),
            symbol="BTCUSDT",
            price_level=Decimal("49998"),
            liquidation_volume=Decimal("20.0"),
            leverage_tier="50x",
            side="sell",
            confidence=Decimal("1.0")
        )
    ]
    
    bin_size = 10.0
    grid, long_dist, short_dist = aggregate_to_bucket_grid(levels, bin_size)
    
    assert isinstance(grid, BucketGrid)
    # 50002 -> 50000, 50007 -> 50010
    # 49998 -> 50000
    
    # buy side (long_distribution)
    assert long_dist["50000.0"] == 10.5
    assert long_dist["50010.0"] == 5.5
    
    # sell side (short_distribution)
    assert short_dist["50000.0"] == 20.0

def test_aggregate_to_bucket_grid_empty():
    grid, long_dist, short_dist = aggregate_to_bucket_grid([], 10.0)
    assert long_dist == {}
    assert short_dist == {}
    assert grid.min_price is None or grid.price_levels == []
