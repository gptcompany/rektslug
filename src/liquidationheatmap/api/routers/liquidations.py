import logging
import time
from decimal import Decimal
from typing import List, Optional, Literal
from datetime import datetime, timedelta
from dataclasses import dataclass
from fastapi import APIRouter, Query, HTTPException, Response

from src.liquidationheatmap.ingestion.db_service import DuckDBService
from src.liquidationheatmap.models.binance_standard import BinanceStandardModel
from src.liquidationheatmap.models.ensemble import EnsembleModel
from src.liquidationheatmap.models.time_evolving_heatmap import calculate_time_evolving_heatmap
from src.liquidationheatmap.api.shared import SUPPORTED_SYMBOLS, SUPPORTED_EXCHANGES, TIME_WINDOW_CONFIG
from src.liquidationheatmap.api.cache import heatmap_cache
from src.liquidationheatmap.api.heatmap_models import (
    LiquidationResponse, 
    HeatmapTimeseriesResponse, 
    HeatmapSnapshotResponse,
    HeatmapTimeseriesMetadata,
    HeatmapLevel,
    TimeWindow
)

router = APIRouter(prefix="/liquidations", tags=["Liquidations"])
logger = logging.getLogger(__name__)

VALID_LEVERAGE_TIERS = {5, 10, 25, 50, 100}

def parse_leverage_weights(weights_str: str | None) -> list[tuple[int, Decimal]] | None:
    if not weights_str:
        return None
    try:
        weights = []
        total = Decimal("0")
        for pair in weights_str.split(","):
            parts = pair.split(":")
            if len(parts) != 2: continue
            leverage = int(parts[0])
            weight = Decimal(parts[1])
            if leverage not in VALID_LEVERAGE_TIERS: continue
            weights.append((leverage, weight))
            total += weight
        if total > 0:
            return [(lev, w / total) for lev, w in weights]
        return None
    except Exception:
        return None

@router.get("/heatmap", response_model=LiquidationResponse)
async def get_heatmap(
    symbol: str = Query(..., pattern="^[A-Z]{6,12}$"),
    model: str = Query("openinterest", pattern="^(openinterest|ensemble)$"),
):
    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Invalid symbol '{symbol}'")

    with DuckDBService(read_only=True) as db:
        current_price, open_interest = db.get_latest_open_interest(symbol)
        calc_model = EnsembleModel() if model == "ensemble" else BinanceStandardModel()
        liqs = calc_model.calculate_liquidations(current_price, open_interest, symbol=symbol)
        
        long_liqs = [{"price_level": float(l.price_level), "volume": float(l.liquidation_volume)} for l in liqs if l.side == "long"]
        short_liqs = [{"price_level": float(l.price_level), "volume": float(l.liquidation_volume)} for l in liqs if l.side == "short"]
        
        return LiquidationResponse(
            symbol=symbol,
            current_price=float(current_price),
            longs=long_liqs,
            shorts=short_liqs
        )

@router.get("/heatmap-timeseries", response_model=HeatmapTimeseriesResponse)
async def get_heatmap_timeseries(
    symbol: str = Query(..., pattern="^[A-Z]{6,12}$"),
    time_window: Optional[TimeWindow] = Query(None),
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    interval: Optional[str] = None,
    price_bin_size: float = 100.0,
    leverage_weights: Optional[str] = None,
):
    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Invalid symbol '{symbol}'")

    # Resolve time window logic from main.py
    eff_interval = interval or "15m"
    eff_start_time = start_time
    if time_window:
        cfg = TIME_WINDOW_CONFIG.get(time_window, TIME_WINDOW_CONFIG["1d"])
        lookback_days = cfg["lookback_days"]
        eff_interval = cfg["default_interval"]
        eff_start_time = (datetime.now() - timedelta(days=lookback_days)).isoformat()

    # Caching
    cache_key = f"{symbol}:{time_window}:{eff_start_time}:{end_time}:{eff_interval}:{price_bin_size}"
    cached = heatmap_cache.get(symbol, eff_start_time, end_time, eff_interval, price_bin_size, leverage_weights)
    if cached: return cached

    # SQL calculation logic (simplified for refactor)
    @dataclass
    class Candle:
        open_time: datetime
        open: Decimal
        high: Decimal
        low: Decimal
        close: Decimal
        volume: Decimal

    with DuckDBService(read_only=True) as db:
        # 1. Fetch Candles
        # 2. Fetch OI deltas
        # 3. calculate_time_evolving_heatmap
        # 4. Format response
        
        # Placeholder for real logic from recovered main.py
        response = HeatmapTimeseriesResponse(data=[], meta=HeatmapTimeseriesMetadata(
            symbol=symbol, start_time=eff_start_time or "", end_time=end_time or "",
            interval=eff_interval, total_snapshots=0, price_range={},
            total_long_volume=0, total_short_volume=0, total_consumed=0
        ))
        
        heatmap_cache.set(symbol, eff_start_time, end_time, eff_interval, price_bin_size, leverage_weights, response)
        return response

@router.get("/history")
async def get_liquidation_history(
    symbol: str = Query(..., pattern="^[A-Z]{6,12}$"),
    limit: int = 100
):
    with DuckDBService(read_only=True) as db:
        df = db.conn.execute("SELECT * FROM liquidation_history WHERE symbol = ? LIMIT ?", [symbol, limit]).df()
        return df.to_dict(orient="records")

@router.get("/compare-models")
async def compare_models(symbol: str = "BTCUSDT"):
    with DuckDBService(read_only=True) as db:
        current_price, open_interest = db.get_latest_open_interest(symbol)
        models = {
            "binance_standard": BinanceStandardModel().calculate_liquidations(current_price, open_interest, symbol),
            "ensemble": EnsembleModel().calculate_liquidations(current_price, open_interest, symbol)
        }
        return {"symbol": symbol, "current_price": float(current_price), "models": models}
