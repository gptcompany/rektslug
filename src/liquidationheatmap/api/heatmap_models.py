from datetime import datetime
from typing import List, Optional, Dict, Literal
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator

class HeatmapRequest(BaseModel):
    """Request parameters for heatmap endpoint."""
    symbol: str = Field(..., description="Trading pair symbol")
    model: str = Field(..., description="Liquidation model")
    timeframe: str = Field("1d", description="Time bucket size")
    start: Optional[datetime] = Field(None, description="Start time (optional)")
    end: Optional[datetime] = Field(None, description="End time (optional)")

class HeatmapDataPoint(BaseModel):
    """Single data point in heatmap grid."""
    time: datetime = Field(..., description="Time bucket timestamp")
    price_bucket: float = Field(..., description="Price bucket")
    density: int = Field(..., description="Number of liquidations in bucket", ge=0)
    volume: float = Field(..., description="Total liquidation volume (USDT)", ge=0)

class HeatmapMetadata(BaseModel):
    """Metadata about the heatmap data."""
    total_volume: float
    highest_density_price: float
    num_buckets: int
    data_quality_score: float
    time_range_hours: float

class LiquidationResponse(BaseModel):
    """Legacy response for static levels."""
    symbol: str
    current_price: float
    longs: List[dict]
    shorts: List[dict]

class HeatmapLevel(BaseModel):
    """Single price level in heatmap snapshot."""
    price: float
    long_density: float
    short_density: float

class HeatmapSnapshotResponse(BaseModel):
    """Heatmap state at a single timestamp."""
    timestamp: str
    levels: List[HeatmapLevel]
    positions_created: int
    positions_consumed: int

class HeatmapTimeseriesMetadata(BaseModel):
    """Metadata for heatmap timeseries response."""
    symbol: str
    start_time: str
    end_time: str
    interval: str
    total_snapshots: int
    price_range: dict
    total_long_volume: float
    total_short_volume: float
    total_consumed: int

class HeatmapTimeseriesResponse(BaseModel):
    """Response model for time-evolving heatmap endpoint."""
    data: List[HeatmapSnapshotResponse]
    meta: HeatmapTimeseriesMetadata

# Re-add TimeWindow enum/literal if needed
TimeWindow = Literal["1h", "4h", "12h", "1d", "3d", "7d", "14d", "30d", "90d", "1y"]
