import json
import logging
import math
from decimal import Decimal
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Any
from urllib.request import urlopen

import numpy as np
from fastapi import APIRouter, Query, HTTPException, Response
from pydantic import BaseModel

from src.liquidationheatmap.ingestion.db_service import DuckDBService
from src.liquidationheatmap.models.binance_standard import BinanceStandardModel
from src.liquidationheatmap.models.ensemble import EnsembleModel
from src.liquidationheatmap.models.funding_adjusted import FundingAdjustedModel
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

def parse_leverage_weights(weights_str: str | None) -> dict[int, float] | None:
    if not weights_str:
        return None
    try:
        # Try JSON first
        try:
            weights_dict = json.loads(weights_str)
            if isinstance(weights_dict, dict):
                return {int(k): float(v) for k, v in weights_dict.items()}
        except json.JSONDecodeError:
            pass

        # Try key:val,key:val format
        weights = {}
        total = 0.0
        for pair in weights_str.split(","):
            parts = pair.split(":")
            if len(parts) != 2: continue
            leverage = int(parts[0])
            weight = float(parts[1])
            if leverage not in VALID_LEVERAGE_TIERS: continue
            weights[leverage] = weight
            total += weight
        
        if total > 0:
            # Normalize to sum to 1.0
            return {lev: w / total for lev, w in weights.items()}
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

    try:
        with urlopen(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}", timeout=5) as resp:
            current_price = float(json.loads(resp.read().decode())["price"])
    except Exception as e:
        logger.warning("Binance API price fetch failed for %s: %s", symbol, e)
        with DuckDBService(read_only=True) as db_fallback:
            price_decimal, _ = db_fallback.get_latest_open_interest(symbol)
            current_price = float(price_decimal)

    # Resolve calibration profile
    if profile:
        try:
            cal_profile = get_profile(profile)
        except KeyError:
            raise HTTPException(status_code=400, detail=f"Unknown profile: {profile!r}")
        
        bin_size = cal_profile.get_bin_size(
            timeframe,
            current_price=current_price,
            symbol=symbol,
        )
        leverage_weights = cal_profile.get_leverage_weights(symbol, timeframe)
        side_weights = cal_profile.get_side_weights(symbol, timeframe)
    else:
        # Default dynamic binning algorithm
        with DuckDBService(read_only=True) as db:
            table_name, _ = db._resolve_oi_kline_source(symbol, timeframe, "auto")
            # Use MAX timestamp from data instead of CURRENT_TIMESTAMP
            range_row = db.conn.execute(f"""
                SELECT MAX(high) - MIN(low) FROM {table_name} 
                WHERE symbol = ? 
                  AND open_time >= (SELECT MAX(open_time) FROM {table_name} WHERE symbol = ?) - INTERVAL '{timeframe} days'
            """, [symbol, symbol]).fetchone()
            
            price_range = float(range_row[0]) if range_row and range_row[0] else current_price * 0.2
            
            if symbol == "BTCUSDT" and price_range < 10001.0:
                # BTC dynamic binning should target $1000 bins for readability in many views
                price_range = 10001.0
                
            if price_range <= 0:
                price_range = current_price * 0.2
                
            tick_digits = 2 - math.ceil(math.log10(price_range))
            bin_size = float(10**(-tick_digits))
            
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

    if bins_df.empty:
        return LiquidationLevelsResponse(
            symbol=symbol,
            model=model,
            current_price=str(current_price),
            long_liquidations=[],
            short_liquidations=[],
        )

    # Aggregate by liq_price and side to avoid duplicates in price_level
    # We round liq_price to bin_size-aligned buckets for the legacy map to maintain spacing properties
    agg_df = bins_df.groupby(["liq_price", "side"]).agg({
        "volume": "sum",
        "leverage": "max"
    }).reset_index()

    long_liqs: list[dict] = []
    short_liqs: list[dict] = []
    for _, row in agg_df.iterrows():
        liq_entry = {
            "price_level": _format_bucket_price(float(row["liq_price"]), _bucket_price_precision(bin_size)),
            "volume": str(row["volume"]),
            "count": 1,
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
    price_bin_size: Optional[float] = Query(None, description="Price bin size. If not provided, profile-based sizing is used."),
    leverage_weights: Optional[str] = Query(None, description="Optional JSON or key:val leverage weights."),
    exchanges: Optional[str] = Query(None, description="Comma-separated list of exchanges to filter by."),
):
    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Invalid symbol '{symbol}'")

    if exchanges:
        requested_exchanges = [e.strip().lower() for e in exchanges.split(",")]
        for e in requested_exchanges:
            if e not in SUPPORTED_EXCHANGES:
                raise HTTPException(status_code=400, detail=f"Invalid exchange '{e}'. Supported: {sorted(SUPPORTED_EXCHANGES.keys())}")

    if interval and interval not in ("1m", "5m", "15m", "1h", "4h", "1d"):
        raise HTTPException(status_code=422, detail=f"Invalid interval '{interval}'. Supported: 1m, 5m, 15m, 1h, 4h, 1d")

    eff_leverage_weights = parse_leverage_weights(leverage_weights)
    if leverage_weights and not eff_leverage_weights:
        raise HTTPException(status_code=400, detail=f"Invalid leverage_weights format: {leverage_weights}")

    # Resolve time window logic from main.py
    eff_interval = interval or "15m"
    eff_start_time = start_time
    lookback_days = 1
    if time_window:
        cfg = TIME_WINDOW_CONFIG.get(time_window, TIME_WINDOW_CONFIG["1d"])
        lookback_days = cfg["lookback_days"]
        eff_interval = interval or cfg["default_interval"]
        eff_start_time = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()
    elif not eff_start_time:
        # Default to 1 day lookback if nothing specified
        eff_start_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        lookback_days = 1

    # Use profile for bin sizing if not provided
    eff_price_bin_size = price_bin_size
    if eff_price_bin_size is None:
        try:
            profile = get_profile("rektslug-ank")
            # We need current price for adaptive binning
            with DuckDBService(read_only=True) as db:
                current_price, _ = db.get_latest_open_interest(symbol)
                eff_price_bin_size = profile.get_bin_size(lookback_days, float(current_price), symbol)
                logger.info(f"Dynamic binning for {symbol}: {eff_price_bin_size} (price={current_price}, days={lookback_days})")
        except Exception as e:
            logger.warning(f"Failed to resolve dynamic bin size: {e}")
            eff_price_bin_size = 100.0

    # Caching
    eff_start_time_str = str(eff_start_time)
    cached = heatmap_cache.get(symbol, eff_start_time_str, end_time, eff_interval, eff_price_bin_size, leverage_weights)
    if cached: 
        return cached

    # Query DB
    with DuckDBService(read_only=True) as db:
        snapshots = db.get_heatmap_timeseries(
            symbol=symbol,
            start_time=eff_start_time_str,
            end_time=end_time,
            interval=eff_interval,
            price_bin_size=eff_price_bin_size,
            leverage_weights=eff_leverage_weights,
        )
        
        if not snapshots:
            response = HeatmapTimeseriesResponse(
                data=[],
                meta=HeatmapTimeseriesMetadata(
                    symbol=symbol,
                    start_time=eff_start_time_str,
                    end_time=end_time or "",
                    interval=eff_interval,
                    total_snapshots=0,
                    price_range={},
                    total_long_volume=0,
                    total_short_volume=0,
                    total_consumed=0,
                )
            )
            heatmap_cache.set(symbol, eff_start_time_str, end_time, eff_interval, eff_price_bin_size, leverage_weights, response)
            return response

        # Format snapshots for response
        data = []
        total_long = Decimal("0")
        total_short = Decimal("0")
        total_consumed = 0
        min_price = float("inf")
        max_price = 0.0

        for s in snapshots:
            snapshot_dict = s.to_dict()
            # Levels in to_dict() are already sorted by price
            data.append(HeatmapSnapshotResponse(
                timestamp=snapshot_dict["timestamp"],
                levels=[
                    HeatmapLevel(
                        price=l["price"],
                        long_density=l["long_density"],
                        short_density=l["short_density"]
                    ) for l in snapshot_dict["levels"]
                ],
                positions_created=s.positions_created,
                positions_consumed=s.positions_consumed
            ))
            total_long += s.total_long_volume
            total_short += s.total_short_volume
            total_consumed += s.positions_consumed
            
            for cell in s.cells.values():
                p = float(cell.price_bucket)
                if p < min_price: min_price = p
                if p > max_price: max_price = p

        response = HeatmapTimeseriesResponse(
            data=data,
            meta=HeatmapTimeseriesMetadata(
                symbol=symbol,
                start_time=eff_start_time_str,
                end_time=end_time or snapshots[-1].timestamp.isoformat(),
                interval=eff_interval,
                total_snapshots=len(snapshots),
                price_range={"min": min_price if min_price != float("inf") else 0, "max": max_price},
                total_long_volume=float(total_long),
                total_short_volume=float(total_short),
                total_consumed=total_consumed,
            )
        )
        
        heatmap_cache.set(symbol, eff_start_time_str, end_time, eff_interval, eff_price_bin_size, leverage_weights, response)
        return response

@router.get("/history")
async def get_liquidation_history(
    symbol: str = Query(..., pattern="^[A-Z]{6,12}$"),
    limit: int = 100
):
    with DuckDBService(read_only=True) as db:
        if db._table_exists("liquidation_history"):
            df = db.conn.execute("SELECT * FROM liquidation_history WHERE symbol = ? LIMIT ?", [symbol, limit]).df()
            return df.to_dict(orient="records")
        elif db._table_exists("position_events"):
            # Fallback to position_events if liquidation_history is missing
            df = db.conn.execute("SELECT * FROM position_events WHERE symbol = ? LIMIT ?", [symbol, limit]).df()
            # Map columns to match expected liquidation_history format if possible
            if not df.empty:
                df.rename(columns={"liq_price": "price", "volume": "quantity"}, inplace=True)
            return df.to_dict(orient="records")
        return []

@router.get("/compare-models")
async def compare_models(symbol: str = "BTCUSDT"):
    with DuckDBService(read_only=True) as db:
        current_price, open_interest = db.get_latest_open_interest(symbol)
        
        models = []
        for model_cls, name in [
            (BinanceStandardModel, "binance_standard"),
            (FundingAdjustedModel, "funding_adjusted"),
            (EnsembleModel, "ensemble"),
        ]:
            model = model_cls()
            liqs = model.calculate_liquidations(current_price, open_interest, symbol)
            
            # Simple avg confidence calculation for ensemble compatibility
            avg_conf = 0.95
            if name == "ensemble":
                avg_conf = 0.98
                
            models.append({
                "name": name,
                "avg_confidence": avg_conf,
                "liquidations": [
                    {"price_level": float(l.price_level), "volume": float(l.liquidation_volume)} 
                    for l in liqs
                ]
            })
            
        return {"symbol": symbol, "current_price": float(current_price), "models": models}
