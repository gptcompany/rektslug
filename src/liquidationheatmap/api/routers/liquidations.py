import json
import logging
from decimal import Decimal
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from urllib.request import urlopen

import numpy as np
from fastapi import APIRouter, Query, HTTPException, Response
from pydantic import BaseModel

from src.liquidationheatmap.ingestion.db_service import DuckDBService
from src.liquidationheatmap.models.binance_standard import BinanceStandardModel
from src.liquidationheatmap.models.ensemble import EnsembleModel
from src.liquidationheatmap.models.profiles import get_profile
from src.liquidationheatmap.models.time_evolving_heatmap import calculate_time_evolving_heatmap
from src.liquidationheatmap.settings import get_settings
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
_SETTINGS = get_settings()

VALID_LEVERAGE_TIERS = {5, 10, 25, 50, 100}


class LiquidationLevelsResponse(BaseModel):
    """Legacy static liquidation levels contract consumed by the liq-map frontend."""

    symbol: str
    model: str
    current_price: str
    long_liquidations: list[dict]
    short_liquidations: list[dict]


def _bucket_price_precision(bin_size: float) -> int:
    normalized = Decimal(str(bin_size)).normalize()
    return max(0, -normalized.as_tuple().exponent)


def _format_bucket_price(value: float, precision: int) -> str:
    if precision <= 0:
        return str(int(round(value)))
    return f"{value:.{precision}f}".rstrip("0").rstrip(".")

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


@router.get(
    "/levels",
    response_model=LiquidationLevelsResponse,
    deprecated=True,
    description="Legacy static levels endpoint kept for the liq-map frontend and validation.",
)
async def get_liquidation_levels(
    response: Response,
    symbol: str = Query(..., pattern="^[A-Z]{6,12}$"),
    model: str = Query("openinterest"),
    timeframe: int = Query(..., ge=1, le=365),
    whale_threshold: float = Query(500000.0, ge=0.0),
    kline_interval: Optional[str] = Query(None, pattern="^(auto|1m|5m)$"),
    profile: Optional[str] = Query(None, description="Calibration profile name (e.g. rektslug-ank)."),
):
    """Return static liquidation levels grouped by side and leverage tier."""
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2025-06-01"
    response.headers["Link"] = '</liquidations/heatmap-timeseries>; rel="successor-version"'

    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid symbol '{symbol}'. Supported symbols: {sorted(SUPPORTED_SYMBOLS)}",
        )

    # Resolve calibration profile (if provided)
    cal_profile = None
    if profile:
        try:
            cal_profile = get_profile(profile)
        except KeyError:
            raise HTTPException(status_code=400, detail=f"Unknown profile: {profile!r}")

    try:
        with urlopen(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}", timeout=5) as resp:
            current_price = float(json.loads(resp.read().decode())["price"])
    except Exception as e:
        logger.warning("Binance API price fetch failed for %s: %s", symbol, e)
        with DuckDBService(read_only=True) as db_fallback:
            price_decimal, _ = db_fallback.get_latest_open_interest(symbol)
            current_price = float(price_decimal)

    if cal_profile:
        bin_size = cal_profile.get_bin_size(
            timeframe,
            current_price=current_price,
            symbol=symbol,
        )
        leverage_weights = cal_profile.leverage_weights
        side_weights = cal_profile.get_side_weights(symbol, timeframe)
    else:
        if timeframe <= 7:
            bin_size = 100.0
        elif timeframe <= 30:
            bin_size = 250.0
        else:
            bin_size = 500.0
        leverage_weights = None
        side_weights = None

    with DuckDBService(read_only=True) as db:
        effective_kline_interval = kline_interval or _SETTINGS.oi_kline_interval
        bins_df = db.calculate_liquidations_oi_based(
            symbol=symbol,
            current_price=current_price,
            bin_size=bin_size,
            lookback_days=timeframe,
            whale_threshold=whale_threshold,
            leverage_weights=leverage_weights,
            side_weights=side_weights,
            kline_interval=effective_kline_interval,
        )

        if not bins_df.empty and "liq_price" in bins_df.columns:
            price_precision = _bucket_price_precision(bin_size)
            bins_df["liq_price_binned"] = (
                np.round(np.round(bins_df["liq_price"] / bin_size) * bin_size, price_precision)
            )
            bins_df = (
                bins_df.groupby(["liq_price_binned", "leverage", "side"])
                .agg({"volume": "sum"})
                .reset_index()
            )
            bins_df["count"] = 1
            bins_df.rename(
                columns={"volume": "total_volume", "liq_price_binned": "price_bucket"},
                inplace=True,
            )

    logger.info("Static levels returned %d aggregated bins", len(bins_df))

    long_liqs: list[dict] = []
    short_liqs: list[dict] = []
    for _, row in bins_df.iterrows():
        liq_entry = {
            "price_level": _format_bucket_price(float(row["price_bucket"]), _bucket_price_precision(bin_size)),
            "volume": str(row["total_volume"]),
            "count": int(row["count"]),
            "leverage": f"{int(row['leverage'])}x",
        }
        if row["side"] == "buy":
            long_liqs.append(liq_entry)
        else:
            short_liqs.append(liq_entry)

    long_liqs = sorted(long_liqs, key=lambda x: float(x["price_level"]), reverse=True)
    short_liqs = sorted(short_liqs, key=lambda x: float(x["price_level"]))

    return LiquidationLevelsResponse(
        symbol=symbol,
        model=model,
        current_price=str(current_price),
        long_liquidations=long_liqs,
        short_liquidations=short_liqs,
    )

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
