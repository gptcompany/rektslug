import asyncio
import json
import logging
import math
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Optional
from urllib.request import urlopen

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.liquidationheatmap.api.cache import heatmap_cache
from src.liquidationheatmap.api.heatmap_models import (
    HeatmapLevel,
    HeatmapSnapshotResponse,
    HeatmapTimeseriesMetadata,
    HeatmapTimeseriesResponse,
    HyperliquidPublicMapResponse,
    LiquidationResponse,
    TimeWindow,
)
from src.liquidationheatmap.api.public_liqmap import (
    SUPPORTED_PUBLIC_LIQMAP_SYMBOLS,
    SUPPORTED_PUBLIC_LIQMAP_TIMEFRAMES,
    CoinankPublicMapResponse,
    build_coinank_public_map_response,
)
from src.liquidationheatmap.api.shared import (
    SUPPORTED_EXCHANGES,
    SUPPORTED_SYMBOLS,
    TIME_WINDOW_CONFIG,
)
from src.liquidationheatmap.ingestion.db_service import (
    DuckDBService,
    IngestionLockError,
    _HeatmapCandle,
    _align_oi_deltas_to_candles,
    _as_naive_utc,
    _get_fallback_price,
    _interval_timedelta,
    _parse_iso_timestamp,
    _resample_heatmap_candles,
)
from src.liquidationheatmap.ingestion.questdb_service import QuestDBService
from src.liquidationheatmap.models.binance_standard import BinanceStandardModel
from src.liquidationheatmap.models.ensemble import EnsembleModel
from src.liquidationheatmap.models.funding_adjusted import FundingAdjustedModel
from src.liquidationheatmap.models.profiles import get_profile
from src.liquidationheatmap.models.time_evolving_heatmap import calculate_time_evolving_heatmap
from src.liquidationheatmap.settings import get_settings


def _questdb_unavailable_error(context: str) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=f"QuestDB unavailable while {context}.",
        headers={"Retry-After": "60"},
    )


def _get_latest_price_with_questdb(symbol: str, qdb: QuestDBService | None = None) -> float | None:
    qdb = qdb or QuestDBService()
    for interval in ("1m", "5m", None):
        price = qdb.get_latest_price(symbol, interval=interval)
        if price is not None:
            return float(price)
    return None


def _get_latest_oi_with_questdb(symbol: str) -> tuple[float, Decimal]:
    qdb = QuestDBService()
    if not qdb.is_available():
        raise _questdb_unavailable_error("loading latest open interest")
    q_price, q_oi = qdb.get_latest_open_interest(symbol)
    latest_price = q_price if q_price is not None else _get_latest_price_with_questdb(symbol, qdb)

    if q_oi is not None:
        if latest_price is not None:
            return float(latest_price), Decimal(str(q_oi))

        fallback_price = float(_get_fallback_price(symbol))
        return fallback_price, Decimal(str(q_oi))

    resolved_price = latest_price if latest_price is not None else float(_get_fallback_price(symbol))
    return resolved_price, _fallback_open_interest(symbol, resolved_price)


def _get_latest_funding_with_questdb(symbol: str) -> Decimal:
    qdb = QuestDBService()
    if not qdb.is_available():
        raise _questdb_unavailable_error("loading latest funding rate")
    q_funding = qdb.get_latest_funding_rate(symbol)
    if q_funding is not None:
        return Decimal(str(q_funding))
    return Decimal("0")


def _get_recent_liquidations_with_questdb(symbol: str, limit: int) -> list[dict[str, Any]]:
    qdb = QuestDBService()
    if not qdb.is_available():
        raise _questdb_unavailable_error("loading liquidation history")
    return qdb.get_recent_liquidations(symbol, limit)

router = APIRouter(prefix="/liquidations", tags=["Liquidations"])
logger = logging.getLogger(__name__)
_SETTINGS = get_settings()

VALID_LEVERAGE_TIERS = {5, 10, 25, 50, 100}
TRANSIENT_DUCKDB_RETRY_ATTEMPTS = 3
TRANSIENT_DUCKDB_RETRY_DELAY_SECONDS = 0.05
QUESTDB_HOT_HEATMAP_INTERVAL_SOURCES = {"1m": "1m", "5m": "5m", "15m": "5m"}
QUESTDB_HOT_HEATMAP_LOOKBACK = timedelta(days=14)


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

    return (value_decimal / bin_decimal).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    ) * bin_decimal


def _aggregate_legacy_levels(bins_df, bin_size: float):
    if bins_df.empty:
        return bins_df

    agg_df = bins_df.copy()
    agg_df["price_bucket"] = agg_df["liq_price"].apply(
        lambda value: _round_to_bucket(float(value), bin_size)
    )
    return (
        agg_df.groupby(["price_bucket", "side", "leverage"])
        .agg(
            {
                "volume": "sum",
            }
        )
        .reset_index()
    )


def _is_transient_contention_http_error(exc: HTTPException) -> bool:
    return exc.status_code == 500 and str(exc.detail).startswith("Temporary database contention")


def _is_questdb_unavailable_http_error(exc: HTTPException) -> bool:
    return exc.status_code == 503 and str(exc.detail).startswith("QuestDB unavailable")


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


def _should_use_questdb_live_timeseries(interval: str, start_time: str | None) -> bool:
    source_interval = QUESTDB_HOT_HEATMAP_INTERVAL_SOURCES.get(interval)
    if source_interval is None or not start_time:
        return False

    start_dt = _parse_iso_timestamp(start_time)
    if start_dt is None:
        return False

    now_utc = _as_naive_utc(datetime.now(timezone.utc))
    return now_utc - start_dt <= QUESTDB_HOT_HEATMAP_LOOKBACK


def _load_heatmap_snapshots_from_questdb(
    *,
    symbol: str,
    start_time: str,
    end_time: str | None,
    interval: str,
    price_bin_size: float,
    leverage_weights: dict[int, float] | None,
):
    source_interval = QUESTDB_HOT_HEATMAP_INTERVAL_SOURCES.get(interval)
    if source_interval is None:
        return None

    qdb = QuestDBService()
    if not qdb.is_available():
        raise _questdb_unavailable_error("loading hot heatmap timeseries")

    kline_rows = qdb.get_klines_range(
        symbol=symbol,
        interval=source_interval,
        start_time=start_time,
        end_time=end_time,
    )
    if not kline_rows:
        return []

    candles = [
        _HeatmapCandle(
            open_time=_as_naive_utc(
                row["timestamp"].to_pydatetime()
                if hasattr(row["timestamp"], "to_pydatetime")
                else row["timestamp"]
            ),
            open=Decimal(str(row["open"])),
            high=Decimal(str(row["high"])),
            low=Decimal(str(row["low"])),
            close=Decimal(str(row["close"])),
            volume=Decimal(str(row["volume"])),
        )
        for row in kline_rows
    ]

    requested_interval = interval.lower()
    candles = _resample_heatmap_candles(
        candles=candles,
        source_interval=source_interval,
        target_interval=requested_interval,
    )
    alignment_interval = (
        requested_interval
        if _interval_timedelta(requested_interval) >= _interval_timedelta(source_interval)
        else source_interval
    )

    parsed_start_time = _parse_iso_timestamp(start_time)
    oi_query_start: str | datetime = start_time
    if parsed_start_time is not None:
        oi_query_start = (
            parsed_start_time
            - max(_interval_timedelta(alignment_interval), timedelta(minutes=15))
        ).isoformat()

    oi_rows = qdb.get_open_interest_range(
        symbol=symbol,
        start_time=oi_query_start,
        end_time=end_time,
    )
    oi_df = pd.DataFrame(oi_rows)
    if oi_df.empty:
        oi_df = pd.DataFrame(columns=["timestamp", "oi_delta"])
    else:
        oi_df["timestamp"] = pd.to_datetime(oi_df["timestamp"], utc=True)
        oi_df["oi_delta"] = oi_df["oi_delta"].fillna(0)

    normalized_weights = None
    if leverage_weights:
        normalized_weights = [(int(k), Decimal(str(v))) for k, v in leverage_weights.items()]

    return calculate_time_evolving_heatmap(
        candles=candles,
        oi_deltas=_align_oi_deltas_to_candles(candles, oi_df, alignment_interval),
        symbol=symbol,
        leverage_weights=normalized_weights,
        price_bucket_size=Decimal(str(price_bin_size)),
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
    profile: Optional[str] = Query(
        None, description="Calibration profile name (e.g. rektslug-ank)."
    ),
):
    """Return static liquidation levels grouped by side and leverage tier."""
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</liquidations/heatmap-timeseries>; rel="successor-version"'

    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid symbol '{symbol}'. Supported symbols: {sorted(SUPPORTED_SYMBOLS)}",
        )

    try:
        with urlopen(
            f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}", timeout=5
        ) as resp:
            current_price = float(json.loads(resp.read().decode())["price"])
    except Exception as e:
        logger.warning("Binance API price fetch failed for %s: %s", symbol, e)

        def _load_current_price():
            current_price, _ = _get_latest_oi_with_questdb(symbol)
            return current_price

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
                table_name, _ = db._resolve_oi_kline_source(
                    symbol,
                    timeframe,
                    "auto",
                    allow_stale_fallback=True,
                )
                range_row = db.conn.execute(
                    f"""
                    SELECT MAX(high) - MIN(low) FROM {table_name} 
                    WHERE symbol = ? 
                      AND open_time >= (SELECT MAX(open_time) FROM {table_name} WHERE symbol = ?) - INTERVAL '{timeframe} days'
                    """,
                    [symbol, symbol],
                ).fetchone()

                price_range = (
                    float(range_row[0]) if range_row and range_row[0] else current_price * 0.2
                )

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
                allow_stale_kline_fallback=True,
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
            "price_level": _format_bucket_price(
                float(row["price_bucket"]), _bucket_price_precision(bin_size)
            ),
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


@router.get(
    "/coinank-public-map",
    response_model=CoinankPublicMapResponse,
    description="Dedicated public CoinAnK-style liq-map payload for canonical public routes.",
)
async def get_coinank_public_map(
    symbol: str = Query(..., pattern="^[A-Z]{6,12}$"),
    timeframe: str = Query(...),
):
    normalized_symbol = symbol.upper()
    normalized_timeframe = timeframe.lower()

    if normalized_symbol not in SUPPORTED_PUBLIC_LIQMAP_SYMBOLS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported public liqmap symbol '{symbol}'. "
                f"Supported symbols: {sorted(SUPPORTED_PUBLIC_LIQMAP_SYMBOLS)}"
            ),
        )
    if normalized_timeframe not in SUPPORTED_PUBLIC_LIQMAP_TIMEFRAMES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported public liqmap timeframe '{timeframe}'. "
                f"Supported timeframes: {sorted(SUPPORTED_PUBLIC_LIQMAP_TIMEFRAMES)}"
            ),
        )

    try:
        return await _run_read_operation_with_retry(
            lambda: build_coinank_public_map_response(
                symbol=normalized_symbol,
                timeframe=normalized_timeframe,
            ),
            exhausted_status_detail=(
                "Temporary database contention while loading public liqmap data."
            ),
        )
    except IngestionLockError:
        raise
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.__class__.__name__, "detail": exc.detail},
        )
    except Exception as exc:
        logger.error(
            "Public liqmap builder failed for %s %s: %s",
            normalized_symbol,
            normalized_timeframe,
            exc,
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={"error": exc.__class__.__name__, "detail": str(exc)},
        )


_HL_CACHE_DIR = Path("data/cache")
_HL_SUPPORTED_SYMBOLS = {"BTCUSDT", "ETHUSDT"}
_HL_STALE_MINUTES = 30


@router.get(
    "/hl-public-map",
    response_model=HyperliquidPublicMapResponse,
    description="Hyperliquid sidecar liq-map from pre-computed ABCI snapshot data.",
)
async def get_hl_public_map(
    symbol: str = Query(..., pattern="^[A-Z]{6,12}$"),
    timeframe: str = Query("1w"),
):
    normalized_symbol = symbol.upper()
    if normalized_symbol not in _HL_SUPPORTED_SYMBOLS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported Hyperliquid symbol '{symbol}'. "
                f"Supported: {sorted(_HL_SUPPORTED_SYMBOLS)}"
            ),
        )
    if timeframe.lower() not in ("1w",):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported timeframe '{timeframe}'. Supported: ['1w']",
        )

    cache_file = _HL_CACHE_DIR / f"hl_sidecar_{normalized_symbol.lower()}.json"
    if not cache_file.exists():
        raise HTTPException(
            status_code=503,
            detail="Hyperliquid sidecar data not yet available. Pre-computation pending.",
            headers={"Retry-After": "60"},
        )

    try:
        raw = cache_file.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.error("Corrupted HL sidecar cache %s: %s", cache_file, exc)
        raise HTTPException(
            status_code=503,
            detail="Hyperliquid sidecar cache is temporarily corrupted. Retry shortly.",
            headers={"Retry-After": "60"},
        )

    generated_at_str = data.get("generated_at", "")
    try:
        if generated_at_str.endswith("Z"):
            generated_at_str_parse = generated_at_str[:-1] + "+00:00"
        else:
            generated_at_str_parse = generated_at_str
        generated_at = datetime.fromisoformat(generated_at_str_parse)
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        generated_at = datetime.min.replace(tzinfo=timezone.utc)

    age = datetime.now(timezone.utc) - generated_at
    if age > timedelta(minutes=_HL_STALE_MINUTES):
        raise HTTPException(
            status_code=503,
            detail=f"Hyperliquid sidecar data is stale (last update: {generated_at_str}).",
            headers={"Retry-After": "60"},
        )

    return HyperliquidPublicMapResponse(**data)


@router.get("/heatmap", response_model=LiquidationResponse)
async def get_heatmap(
    symbol: str = Query(..., pattern="^[A-Z]{6,12}$"),
    model: str = Query("openinterest", pattern="^(openinterest|ensemble)$"),
):
    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Invalid symbol '{symbol}'")

    def _load_heatmap_response():
        current_price, open_interest = _get_latest_oi_with_questdb(symbol)
        if model == "ensemble":
            funding_rate = _get_latest_funding_with_questdb(symbol)
            calc_model = EnsembleModel()
            liqs = calc_model.calculate_liquidations(
                current_price,
                open_interest,
                symbol=symbol,
                funding_rate=funding_rate,
            )
        else:
            calc_model = BinanceStandardModel()
            liqs = calc_model.calculate_liquidations(current_price, open_interest, symbol=symbol)

        long_liqs = [
            {"price_level": float(l.price_level), "volume": float(l.liquidation_volume)}
            for l in liqs
            if l.side == "long"
        ]
        short_liqs = [
            {"price_level": float(l.price_level), "volume": float(l.liquidation_volume)}
            for l in liqs
            if l.side == "short"
        ]

        return LiquidationResponse(
            symbol=symbol,
            current_price=float(current_price),
            longs=long_liqs,
            shorts=short_liqs,
        )

    try:
        return await _run_read_operation_with_retry(
            _load_heatmap_response,
            exhausted_status_detail="Temporary database contention while loading heatmap data.",
        )
    except HTTPException as exc:
        if not (
            _is_transient_contention_http_error(exc) or _is_questdb_unavailable_http_error(exc)
        ):
            raise
        current_price = float(_get_fallback_price(symbol))
        open_interest = _fallback_open_interest(symbol, current_price)
        if model == "ensemble":
            calc_model = EnsembleModel()
            liqs = calc_model.calculate_liquidations(
                Decimal(str(current_price)),
                open_interest,
                symbol=symbol,
                funding_rate=Decimal("0"),
            )
        else:
            calc_model = BinanceStandardModel()
            liqs = calc_model.calculate_liquidations(
                Decimal(str(current_price)),
                open_interest,
                symbol=symbol,
            )
        long_liqs = [
            {"price_level": float(l.price_level), "volume": float(l.liquidation_volume)}
            for l in liqs
            if l.side == "long"
        ]
        short_liqs = [
            {"price_level": float(l.price_level), "volume": float(l.liquidation_volume)}
            for l in liqs
            if l.side == "short"
        ]
        return LiquidationResponse(
            symbol=symbol,
            current_price=current_price,
            longs=long_liqs,
            shorts=short_liqs,
        )


def _try_duckdb_ts_cache(
    symbol: str,
    interval: str,
    start_ts: str,
    end_ts: str | None,
    price_bin_size: float,
) -> HeatmapTimeseriesResponse | None:
    """Try to serve heatmap timeseries from DuckDB pre-computed cache.

    Returns None on cache miss or stale data. Validates staleness:
    entries with computed_at older than 2x interval are discarded.
    """
    staleness_limit = {"15m": timedelta(minutes=30), "1h": timedelta(hours=2)}.get(
        interval, timedelta(hours=2)
    )
    now = datetime.now(timezone.utc)
    eff_end_ts = end_ts or now.isoformat()

    with DuckDBService(read_only=True) as db:
        db.ensure_heatmap_ts_cache_table()
        rows = db.get_cached_ts_snapshots(
            symbol=symbol,
            interval=interval,
            start_ts=start_ts,
            end_ts=eff_end_ts,
            price_bin_size=price_bin_size,
        )

    if not rows:
        return None

    interval_td = {"15m": timedelta(minutes=15), "1h": timedelta(hours=1)}.get(
        interval, timedelta(minutes=15)
    )

    def _parse_cache_dt(value: str | datetime) -> datetime:
        if isinstance(value, datetime):
            parsed = value
        else:
            normalized = value.replace("Z", "+00:00")
            parsed = (
                datetime.fromisoformat(normalized)
                if "T" in normalized or "-" in normalized
                else datetime.strptime(normalized, "%Y-%m-%d %H:%M:%S")
            )
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    start_dt = _parse_cache_dt(start_ts)
    end_dt = _parse_cache_dt(eff_end_ts)
    row_timestamps = sorted(_parse_cache_dt(row["timestamp"]) for row in rows)

    if row_timestamps[0] - start_dt >= interval_td:
        logger.debug(
            "Partial cache: first snapshot %s too far after requested start %s",
            row_timestamps[0],
            start_dt,
        )
        return None
    if end_dt - row_timestamps[-1] >= interval_td:
        logger.debug(
            "Partial cache: last snapshot %s too far before requested end %s",
            row_timestamps[-1],
            end_dt,
        )
        return None
    for prev_ts, next_ts in zip(row_timestamps, row_timestamps[1:]):
        if next_ts - prev_ts > interval_td:
            logger.debug(
                "Partial cache: gap detected between %s and %s for %s/%s",
                prev_ts,
                next_ts,
                symbol,
                interval,
            )
            return None

    # Check staleness — reject if any entry is too old
    for row in rows:
        computed_at = row["computed_at"]
        if hasattr(computed_at, "tzinfo") and computed_at.tzinfo is None:
            computed_at = computed_at.replace(tzinfo=timezone.utc)
        if now - computed_at > staleness_limit:
            logger.debug(f"Stale cache entry at {row['timestamp']}, falling back to live")
            return None

    # Build response from cached payloads
    data = []
    total_long = 0.0
    total_short = 0.0
    total_consumed = 0
    min_price = float("inf")
    max_price = 0.0

    for row in rows:
        snapshot = json.loads(row["payload_json"])
        levels = [
            HeatmapLevel(
                price=l["price"],
                long_density=l["long_density"],
                short_density=l["short_density"],
            )
            for l in snapshot.get("levels", [])
        ]
        meta = snapshot.get("meta", {})
        data.append(
            HeatmapSnapshotResponse(
                timestamp=snapshot["timestamp"],
                levels=levels,
                positions_created=meta.get("positions_created", 0),
                positions_consumed=meta.get("positions_consumed", 0),
            )
        )
        total_long += meta.get("total_long_volume", 0)
        total_short += meta.get("total_short_volume", 0)
        total_consumed += meta.get("positions_consumed", 0)
        for l in levels:
            if l.price < min_price:
                min_price = l.price
            if l.price > max_price:
                max_price = l.price

    return HeatmapTimeseriesResponse(
        data=data,
        meta=HeatmapTimeseriesMetadata(
            symbol=symbol,
            start_time=start_ts,
            end_time=end_ts or rows[-1]["timestamp"].isoformat()
            if hasattr(rows[-1]["timestamp"], "isoformat")
            else str(rows[-1]["timestamp"]),
            interval=interval,
            total_snapshots=len(data),
            price_range={"min": min_price if min_price != float("inf") else 0, "max": max_price},
            total_long_volume=total_long,
            total_short_volume=total_short,
            total_consumed=total_consumed,
        ),
    )


@router.get("/heatmap-timeseries", response_model=HeatmapTimeseriesResponse)
async def get_heatmap_timeseries(
    response: Response,
    symbol: str = Query(..., pattern="^[A-Z]{6,12}$"),
    time_window: Optional[TimeWindow] = Query(None),
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    interval: Optional[str] = None,
    price_bin_size: Optional[float] = Query(
        None, description="Price bin size. If not provided, profile-based sizing is used."
    ),
    leverage_weights: Optional[str] = Query(
        None, description="Optional JSON or key:val leverage weights."
    ),
    exchanges: Optional[str] = Query(
        None, description="Comma-separated list of exchanges to filter by."
    ),
):
    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Invalid symbol '{symbol}'")

    if exchanges:
        requested_exchanges = [e.strip().lower() for e in exchanges.split(",")]
        for e in requested_exchanges:
            if e not in SUPPORTED_EXCHANGES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid exchange '{e}'. Supported: {sorted(SUPPORTED_EXCHANGES.keys())}",
                )

    if interval and interval not in ("1m", "5m", "15m", "1h", "4h", "1d"):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid interval '{interval}'. Supported: 1m, 5m, 15m, 1h, 4h, 1d",
        )

    eff_leverage_weights = parse_leverage_weights(leverage_weights)
    if leverage_weights and not eff_leverage_weights:
        raise HTTPException(
            status_code=400, detail=f"Invalid leverage_weights format: {leverage_weights}"
        )

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
                current_price, _ = _get_latest_oi_with_questdb(symbol)
                return current_price, profile.get_bin_size(
                    lookback_days, float(current_price), symbol
                )

            current_price, eff_price_bin_size = await _run_read_operation_with_retry(
                _resolve_dynamic_bin_size,
                exhausted_status_detail="Temporary database contention while resolving dynamic bin size.",
            )
            logger.info(
                f"Dynamic binning for {symbol}: {eff_price_bin_size} (price={current_price}, days={lookback_days})"
            )
        except Exception as e:
            logger.warning(f"Failed to resolve dynamic bin size: {e}")
            eff_price_bin_size = 100.0

    # Caching (in-memory)
    eff_start_time_str = str(eff_start_time)
    cached = heatmap_cache.get(
        symbol, eff_start_time_str, end_time, eff_interval, eff_price_bin_size, leverage_weights
    )
    if cached:
        response.headers["X-Heatmap-Source"] = "memory"
        response.headers["X-Heatmap-Backend"] = "memory"
        return cached

    use_questdb_live = _should_use_questdb_live_timeseries(eff_interval, eff_start_time_str)

    # DuckDB pre-computed cache (spec-024): only for default params on cold windows.
    # Hot windows prefer QuestDB live reconstruction to keep DuckDB out of the hot path.
    uses_custom_params = leverage_weights is not None or price_bin_size is not None
    if not use_questdb_live and not uses_custom_params and eff_interval in ("15m", "1h"):
        try:
            db_cached_response = _try_duckdb_ts_cache(
                symbol=symbol,
                interval=eff_interval,
                start_ts=eff_start_time_str,
                end_ts=end_time,
                price_bin_size=eff_price_bin_size,
            )
            if db_cached_response is not None:
                response.headers["X-Heatmap-Source"] = "cache"
                response.headers["X-Heatmap-Backend"] = "duckdb-cache"
                heatmap_cache.set(
                    symbol,
                    eff_start_time_str,
                    end_time,
                    eff_interval,
                    eff_price_bin_size,
                    leverage_weights,
                    db_cached_response,
                )
                return db_cached_response
        except Exception as e:
            logger.warning(f"DuckDB ts cache lookup failed, falling back to live: {e}")

    # Query DB (live computation)
    response.headers["X-Heatmap-Source"] = "live"
    backend_source = "duckdb-live"

    def _load_heatmap_snapshots():
        nonlocal backend_source
        if use_questdb_live:
            try:
                snapshots = _load_heatmap_snapshots_from_questdb(
                    symbol=symbol,
                    start_time=eff_start_time_str,
                    end_time=end_time,
                    interval=eff_interval,
                    price_bin_size=eff_price_bin_size,
                    leverage_weights=eff_leverage_weights,
                )
                backend_source = "questdb-live"
                return snapshots
            except HTTPException as exc:
                if exc.status_code != 503:
                    raise
                logger.warning(
                    "QuestDB unavailable for hot heatmap-timeseries %s/%s, falling back to DuckDB compute",
                    symbol,
                    eff_interval,
                )

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
        response.headers["X-Heatmap-Backend"] = backend_source
        empty_response = _build_empty_heatmap_timeseries_response(
            symbol=symbol,
            start_time=eff_start_time_str,
            end_time=end_time,
            interval=eff_interval,
        )
        heatmap_cache.set(
            symbol,
            eff_start_time_str,
            end_time,
            eff_interval,
            eff_price_bin_size,
            leverage_weights,
            empty_response,
        )
        return empty_response
    except ValueError as exc:
        if not _is_missing_kline_coverage_error(exc):
            raise
        response.headers["X-Heatmap-Backend"] = backend_source
        empty_response = _build_empty_heatmap_timeseries_response(
            symbol=symbol,
            start_time=eff_start_time_str,
            end_time=end_time,
            interval=eff_interval,
        )
        heatmap_cache.set(
            symbol,
            eff_start_time_str,
            end_time,
            eff_interval,
            eff_price_bin_size,
            leverage_weights,
            empty_response,
        )
        return empty_response

    if not snapshots:
        response.headers["X-Heatmap-Backend"] = backend_source
        empty_response = _build_empty_heatmap_timeseries_response(
            symbol=symbol,
            start_time=eff_start_time_str,
            end_time=end_time,
            interval=eff_interval,
        )
        heatmap_cache.set(
            symbol,
            eff_start_time_str,
            end_time,
            eff_interval,
            eff_price_bin_size,
            leverage_weights,
            empty_response,
        )
        return empty_response

    data = []
    total_long = Decimal("0")
    total_short = Decimal("0")
    total_consumed = 0
    min_price = float("inf")
    max_price = 0.0

    for s in snapshots:
        snapshot_dict = s.to_dict()
        data.append(
            HeatmapSnapshotResponse(
                timestamp=snapshot_dict["timestamp"],
                levels=[
                    HeatmapLevel(
                        price=l["price"],
                        long_density=l["long_density"],
                        short_density=l["short_density"],
                    )
                    for l in snapshot_dict["levels"]
                ],
                positions_created=s.positions_created,
                positions_consumed=s.positions_consumed,
            )
        )
        total_long += s.total_long_volume
        total_short += s.total_short_volume
        total_consumed += s.positions_consumed

        for cell in s.cells.values():
            p = float(cell.price_bucket)
            if p < min_price:
                min_price = p
            if p > max_price:
                max_price = p

    result = HeatmapTimeseriesResponse(
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
        ),
    )

    response.headers["X-Heatmap-Backend"] = backend_source
    heatmap_cache.set(
        symbol,
        eff_start_time_str,
        end_time,
        eff_interval,
        eff_price_bin_size,
        leverage_weights,
        result,
    )
    return result


@router.get("/history")
async def get_liquidation_history(
    symbol: str = Query(..., pattern="^[A-Z]{6,12}$"), limit: int = 100
):
    def _load_history():
        return _get_recent_liquidations_with_questdb(symbol, limit)

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
        current_price, open_interest = _get_latest_oi_with_questdb(symbol)
        funding_rate = _get_latest_funding_with_questdb(symbol)

        models = []
        for model_cls, name in [
            (BinanceStandardModel, "binance_standard"),
            (FundingAdjustedModel, "funding_adjusted"),
            (EnsembleModel, "ensemble"),
        ]:
            model = model_cls()
            if name == "binance_standard":
                liqs = model.calculate_liquidations(current_price, open_interest, symbol=symbol)
            else:
                liqs = model.calculate_liquidations(
                    current_price,
                    open_interest,
                    symbol=symbol,
                    funding_rate=funding_rate,
                )

            avg_conf = 0.95
            if name == "ensemble":
                avg_conf = 0.98

            models.append(
                {
                    "name": name,
                    "avg_confidence": avg_conf,
                    "liquidations": [
                        {
                            "price_level": float(l.price_level),
                            "volume": float(l.liquidation_volume),
                        }
                        for l in liqs
                    ],
                }
            )

        return {"symbol": symbol, "current_price": float(current_price), "models": models}

    try:
        return await _run_read_operation_with_retry(
            _load_model_comparison,
            exhausted_status_detail="Temporary database contention while comparing models.",
        )
    except HTTPException as exc:
        if not (
            _is_transient_contention_http_error(exc) or _is_questdb_unavailable_http_error(exc)
        ):
            raise

        current_price = _get_fallback_price(symbol)
        open_interest = _fallback_open_interest(symbol, float(current_price))
        funding_rate = Decimal("0")
        models = []
        for model_cls, name in [
            (BinanceStandardModel, "binance_standard"),
            (FundingAdjustedModel, "funding_adjusted"),
            (EnsembleModel, "ensemble"),
        ]:
            calc_model = model_cls()
            if name == "binance_standard":
                liqs = calc_model.calculate_liquidations(current_price, open_interest, symbol=symbol)
            else:
                liqs = calc_model.calculate_liquidations(
                    current_price,
                    open_interest,
                    symbol=symbol,
                    funding_rate=funding_rate,
                )
            avg_conf = 0.95
            if name == "ensemble":
                avg_conf = 0.98
            models.append(
                {
                    "name": name,
                    "avg_confidence": avg_conf,
                    "liquidations": [
                        {"price_level": float(l.price_level), "volume": float(l.liquidation_volume)}
                        for l in liqs
                    ],
                }
            )
        return {"symbol": symbol, "current_price": float(current_price), "models": models}
