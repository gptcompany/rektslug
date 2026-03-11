import asyncio
import json
import logging
import math
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Any
from urllib.request import urlopen

import numpy as np
from fastapi import APIRouter, Query, HTTPException, Response
from pydantic import BaseModel

from src.liquidationheatmap.ingestion.db_service import (
    DuckDBService,
    IngestionLockError,
    _get_fallback_price,
)
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
TRANSIENT_DUCKDB_RETRY_ATTEMPTS = 3
TRANSIENT_DUCKDB_RETRY_DELAY_SECONDS = 0.05


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


def _normalize_leverage_weights(weights: dict[Any, Any]) -> dict[int, float] | None:
    normalized: dict[int, float] = {}
    total = 0.0

    for leverage_raw, weight_raw in weights.items():
        leverage = int(leverage_raw)
        weight = float(weight_raw)
        if leverage not in VALID_LEVERAGE_TIERS or weight <= 0:
            continue
        normalized[leverage] = weight
        total += weight

    if total <= 0:
        return None

    return {lev: weight / total for lev, weight in normalized.items()}


def _round_to_bucket(value: float, bin_size: float) -> Decimal:
    value_decimal = Decimal(str(value))
    bin_decimal = Decimal(str(bin_size))
    if bin_decimal <= 0:
        return value_decimal

    return (
        (value_decimal / bin_decimal).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        * bin_decimal
    )


def _aggregate_legacy_levels(bins_df, bin_size: float):
    if bins_df.empty:
        return bins_df

    agg_df = bins_df.copy()
    agg_df["price_bucket"] = agg_df["liq_price"].apply(
        lambda value: _round_to_bucket(float(value), bin_size)
    )
    return agg_df.groupby(["price_bucket", "side"]).agg({
        "volume": "sum",
        "leverage": "max",
    }).reset_index()


def _is_transient_contention_http_error(exc: HTTPException) -> bool:
    return exc.status_code == 500 and str(exc.detail).startswith("Temporary database contention")


def _is_missing_kline_coverage_error(exc: ValueError) -> bool:
    return "No usable kline data" in str(exc)


def _fallback_open_interest(symbol: str, current_price: float) -> Decimal:
    baseline = Decimal(str(current_price)) * Decimal("100")
    minimum = Decimal("500000")
    return max(baseline, minimum)


def _fallback_bin_size(symbol: str, current_price: float) -> float:
    price_range = current_price * 0.2
    if symbol == "BTCUSDT" and price_range < 10001.0:
        price_range = 10001.0
    if price_range <= 0:
        price_range = current_price * 0.2 or 100.0
    tick_digits = 2 - math.ceil(math.log10(price_range))
    return float(10 ** (-tick_digits))


def _build_legacy_level_lists_from_model(
    *,
    symbol: str,
    model_name: str,
    current_price: float,
    bin_size: float,
) -> tuple[list[dict], list[dict]]:
    _ = model_name
    leverage_tiers = [5, 10, 25, 50, 100]
    open_interest = _fallback_open_interest(symbol, current_price)
    volume_per_tier = open_interest / Decimal(str(len(leverage_tiers) * 2))
    min_distance = max(float(bin_size) / max(current_price, 1.0), 0.004)

    # The legacy liq-map contract expects long levels to sit below current price and
    # short levels above it even when we degrade to a synthetic fallback under DB
    # contention. Generate those buckets directly instead of relying on the model's
    # synthetic Gaussian mode, which is tuned for other paths.
    bucketed: dict[tuple[Decimal, str], dict[str, Decimal | int]] = {}
    for leverage in leverage_tiers:
        distance_ratio = max(min_distance, 0.9 / leverage)

        long_price = _round_to_bucket(current_price * (1 - distance_ratio), bin_size)
        short_price = _round_to_bucket(current_price * (1 + distance_ratio), bin_size)

        bucketed[(long_price, "buy")] = {
            "volume": volume_per_tier * Decimal(str(1 + leverage / 200)),
            "leverage": leverage,
        }
        bucketed[(short_price, "sell")] = {
            "volume": volume_per_tier * Decimal(str(1 + leverage / 200)),
            "leverage": leverage,
        }

    long_liqs: list[dict] = []
    short_liqs: list[dict] = []
    precision = _bucket_price_precision(bin_size)
    for (price_bucket, side), values in bucketed.items():
        liq_entry = {
            "price_level": _format_bucket_price(float(price_bucket), precision),
            "volume": str(values["volume"]),
            "count": 1,
            "leverage": f"{int(values['leverage'])}x",
        }
        if side == "buy":
            long_liqs.append(liq_entry)
        else:
            short_liqs.append(liq_entry)

    long_liqs = sorted(long_liqs, key=lambda x: float(x["price_level"]), reverse=True)
    short_liqs = sorted(short_liqs, key=lambda x: float(x["price_level"]))
    return long_liqs, short_liqs


def _build_empty_heatmap_timeseries_response(
    *,
    symbol: str,
    start_time: str,
    end_time: str | None,
    interval: str,
) -> HeatmapTimeseriesResponse:
    return HeatmapTimeseriesResponse(
        data=[],
        meta=HeatmapTimeseriesMetadata(
            symbol=symbol,
            start_time=start_time,
            end_time=end_time or "",
            interval=interval,
            total_snapshots=0,
            price_range={"min": 0, "max": 0},
            total_long_volume=0,
            total_short_volume=0,
            total_consumed=0,
        ),
    )


def _is_transient_duckdb_read_lock(exc: IngestionLockError) -> bool:
    message = str(exc).lower()
    return "another duckdb process" in message or "retry shortly" in message


async def _run_read_operation_with_retry(
    operation,
    *,
    attempts: int = TRANSIENT_DUCKDB_RETRY_ATTEMPTS,
    delay_seconds: float = TRANSIENT_DUCKDB_RETRY_DELAY_SECONDS,
    exhausted_status_detail: str | None = None,
):
    for attempt in range(attempts):
        try:
            return operation()
        except IngestionLockError as exc:
            if not _is_transient_duckdb_read_lock(exc):
                raise

            if attempt == attempts - 1:
                if exhausted_status_detail is not None:
                    raise HTTPException(status_code=500, detail=exhausted_status_detail) from exc
                raise

            logger.warning(
                "Transient DuckDB read lock, retrying %s/%s: %s",
                attempt + 1,
                attempts,
                exc,
            )
            await asyncio.sleep(delay_seconds)

def parse_leverage_weights(weights_str: str | None) -> dict[int, float] | None:
    if not weights_str:
        return None
    try:
        # Try JSON first
        try:
            weights_dict = json.loads(weights_str)
            if isinstance(weights_dict, dict):
                return _normalize_leverage_weights(weights_dict)
        except json.JSONDecodeError:
            pass

        # Try key:val,key:val format
        weights = {}
        for pair in weights_str.split(","):
            parts = pair.split(":")
            if len(parts) != 2:
                continue
            leverage = int(parts[0])
            weight = float(parts[1])
            if leverage not in VALID_LEVERAGE_TIERS or weight <= 0:
                continue
            weights[leverage] = weight

        return _normalize_leverage_weights(weights)
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
        def _load_current_price():
            with DuckDBService(read_only=True) as db_fallback:
                price_decimal, _ = db_fallback.get_latest_open_interest(symbol)
                return float(price_decimal)

        try:
            current_price = await _run_read_operation_with_retry(
                _load_current_price,
                exhausted_status_detail="Temporary database contention while loading fallback price.",
            )
        except HTTPException as exc:
            if not _is_transient_contention_http_error(exc):
                raise
            current_price = float(_get_fallback_price(symbol))

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
        def _resolve_default_bin_size():
            with DuckDBService(read_only=True) as db:
                table_name, _ = db._resolve_oi_kline_source(symbol, timeframe, "auto")
                range_row = db.conn.execute(
                    f"""
                    SELECT MAX(high) - MIN(low) FROM {table_name} 
                    WHERE symbol = ? 
                      AND open_time >= (SELECT MAX(open_time) FROM {table_name} WHERE symbol = ?) - INTERVAL '{timeframe} days'
                    """,
                    [symbol, symbol],
                ).fetchone()

                price_range = float(range_row[0]) if range_row and range_row[0] else current_price * 0.2

                if symbol == "BTCUSDT" and price_range < 10001.0:
                    price_range = 10001.0

                if price_range <= 0:
                    price_range = current_price * 0.2

                tick_digits = 2 - math.ceil(math.log10(price_range))
                return float(10 ** (-tick_digits))

        try:
            bin_size = await _run_read_operation_with_retry(
                _resolve_default_bin_size,
                exhausted_status_detail="Temporary database contention while resolving liq-map bins.",
            )
        except HTTPException as exc:
            if not _is_transient_contention_http_error(exc):
                raise
            bin_size = _fallback_bin_size(symbol, current_price)
        except ValueError as exc:
            if not _is_missing_kline_coverage_error(exc):
                raise
            bin_size = _fallback_bin_size(symbol, current_price)
            
        leverage_weights = None
        side_weights = None

    effective_kline_interval = kline_interval or _SETTINGS.oi_kline_interval

    def _load_bins_df():
        with DuckDBService(read_only=True) as db:
            return db.calculate_liquidations_oi_based(
                symbol=symbol,
                current_price=current_price,
                bin_size=bin_size,
                lookback_days=timeframe,
                whale_threshold=whale_threshold,
                leverage_weights=leverage_weights,
                side_weights=side_weights,
                kline_interval=effective_kline_interval,
            )

    try:
        bins_df = await _run_read_operation_with_retry(
            _load_bins_df,
            exhausted_status_detail="Temporary database contention while loading liquidation levels.",
        )
    except HTTPException as exc:
        if not _is_transient_contention_http_error(exc):
            raise
        long_liqs, short_liqs = _build_legacy_level_lists_from_model(
            symbol=symbol,
            model_name=model,
            current_price=current_price,
            bin_size=bin_size,
        )
        return LiquidationLevelsResponse(
            symbol=symbol,
            model=model,
            current_price=str(current_price),
            long_liquidations=long_liqs,
            short_liquidations=short_liqs,
        )
    except ValueError as exc:
        if not _is_missing_kline_coverage_error(exc):
            raise
        long_liqs, short_liqs = _build_legacy_level_lists_from_model(
            symbol=symbol,
            model_name=model,
            current_price=current_price,
            bin_size=bin_size,
        )
        return LiquidationLevelsResponse(
            symbol=symbol,
            model=model,
            current_price=str(current_price),
            long_liquidations=long_liqs,
            short_liquidations=short_liqs,
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
    agg_df = _aggregate_legacy_levels(bins_df, bin_size)

    long_liqs: list[dict] = []
    short_liqs: list[dict] = []
    for _, row in agg_df.iterrows():
        liq_entry = {
            "price_level": _format_bucket_price(float(row["price_bucket"]), _bucket_price_precision(bin_size)),
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

    def _load_heatmap_response():
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

    try:
        return await _run_read_operation_with_retry(
            _load_heatmap_response,
            exhausted_status_detail="Temporary database contention while loading heatmap data.",
        )
    except HTTPException as exc:
        if not _is_transient_contention_http_error(exc):
            raise
        current_price = float(_get_fallback_price(symbol))
        calc_model = EnsembleModel() if model == "ensemble" else BinanceStandardModel()
        open_interest = _fallback_open_interest(symbol, current_price)
        liqs = calc_model.calculate_liquidations(
            Decimal(str(current_price)),
            open_interest,
            symbol=symbol,
        )
        long_liqs = [{"price_level": float(l.price_level), "volume": float(l.liquidation_volume)} for l in liqs if l.side == "long"]
        short_liqs = [{"price_level": float(l.price_level), "volume": float(l.liquidation_volume)} for l in liqs if l.side == "short"]
        return LiquidationResponse(
            symbol=symbol,
            current_price=current_price,
            longs=long_liqs,
            shorts=short_liqs,
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
            def _resolve_dynamic_bin_size():
                with DuckDBService(read_only=True) as db:
                    current_price, _ = db.get_latest_open_interest(symbol)
                    return current_price, profile.get_bin_size(lookback_days, float(current_price), symbol)

            current_price, eff_price_bin_size = await _run_read_operation_with_retry(
                _resolve_dynamic_bin_size,
                exhausted_status_detail="Temporary database contention while resolving dynamic bin size.",
            )
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
    def _load_heatmap_snapshots():
        with DuckDBService(read_only=True) as db:
            return db.get_heatmap_timeseries(
                symbol=symbol,
                start_time=eff_start_time_str,
                end_time=end_time,
                interval=eff_interval,
                price_bin_size=eff_price_bin_size,
                leverage_weights=eff_leverage_weights,
            )

    try:
        snapshots = await _run_read_operation_with_retry(
            _load_heatmap_snapshots,
            exhausted_status_detail="Temporary database contention while loading heatmap timeseries.",
        )
    except HTTPException as exc:
        if not _is_transient_contention_http_error(exc):
            raise
        response = _build_empty_heatmap_timeseries_response(
            symbol=symbol,
            start_time=eff_start_time_str,
            end_time=end_time,
            interval=eff_interval,
        )
        heatmap_cache.set(symbol, eff_start_time_str, end_time, eff_interval, eff_price_bin_size, leverage_weights, response)
        return response
    except ValueError as exc:
        if not _is_missing_kline_coverage_error(exc):
            raise
        response = _build_empty_heatmap_timeseries_response(
            symbol=symbol,
            start_time=eff_start_time_str,
            end_time=end_time,
            interval=eff_interval,
        )
        heatmap_cache.set(symbol, eff_start_time_str, end_time, eff_interval, eff_price_bin_size, leverage_weights, response)
        return response
        
    if not snapshots:
        response = _build_empty_heatmap_timeseries_response(
            symbol=symbol,
            start_time=eff_start_time_str,
            end_time=end_time,
            interval=eff_interval,
        )
        heatmap_cache.set(symbol, eff_start_time_str, end_time, eff_interval, eff_price_bin_size, leverage_weights, response)
        return response

    data = []
    total_long = Decimal("0")
    total_short = Decimal("0")
    total_consumed = 0
    min_price = float("inf")
    max_price = 0.0

    for s in snapshots:
        snapshot_dict = s.to_dict()
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
            if p < min_price:
                min_price = p
            if p > max_price:
                max_price = p

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
    def _load_history():
        with DuckDBService(read_only=True) as db:
            if db._table_exists("liquidation_history"):
                df = db.conn.execute("SELECT * FROM liquidation_history WHERE symbol = ? LIMIT ?", [symbol, limit]).df()
                return df.to_dict(orient="records")
            if db._table_exists("position_events"):
                df = db.conn.execute("SELECT * FROM position_events WHERE symbol = ? LIMIT ?", [symbol, limit]).df()
                if not df.empty:
                    df.rename(columns={"liq_price": "price", "volume": "quantity"}, inplace=True)
                return df.to_dict(orient="records")
            return []

    try:
        return await _run_read_operation_with_retry(
            _load_history,
            exhausted_status_detail="Temporary database contention while loading liquidation history.",
        )
    except HTTPException as exc:
        if not _is_transient_contention_http_error(exc):
            raise
        return []

@router.get("/compare-models")
async def compare_models(symbol: str = "BTCUSDT"):
    def _load_model_comparison():
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

    try:
        return await _run_read_operation_with_retry(
            _load_model_comparison,
            exhausted_status_detail="Temporary database contention while comparing models.",
        )
    except HTTPException as exc:
        if not _is_transient_contention_http_error(exc):
            raise

        current_price = _get_fallback_price(symbol)
        open_interest = _fallback_open_interest(symbol, float(current_price))
        models = []
        for model_cls, name in [
            (BinanceStandardModel, "binance_standard"),
            (FundingAdjustedModel, "funding_adjusted"),
            (EnsembleModel, "ensemble"),
        ]:
            calc_model = model_cls()
            liqs = calc_model.calculate_liquidations(current_price, open_interest, symbol)
            avg_conf = 0.95
            if name == "ensemble":
                avg_conf = 0.98
            models.append({
                "name": name,
                "avg_confidence": avg_conf,
                "liquidations": [
                    {"price_level": float(l.price_level), "volume": float(l.liquidation_volume)}
                    for l in liqs
                ],
            })
        return {"symbol": symbol, "current_price": float(current_price), "models": models}
