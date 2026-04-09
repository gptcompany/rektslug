"""Spec-022 public liqmap models and builder helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import math
from typing import Any

from pydantic import BaseModel
from fastapi import HTTPException

from src.liquidationheatmap.ingestion.db_service import DuckDBService, _get_fallback_price
from src.liquidationheatmap.ingestion.questdb_service import QuestDBService
from src.liquidationheatmap.models.profiles import get_profile
from src.liquidationheatmap.modeled_snapshots import reader as snapshot_reader

SUPPORTED_PUBLIC_LIQMAP_SYMBOLS = {"BTCUSDT", "ETHUSDT"}
SUPPORTED_PUBLIC_LIQMAP_TIMEFRAMES = {"1d": 1, "1w": 7}
SUPPORTED_PUBLIC_LIQMAP_EXCHANGES = {"binance", "bybit"}

COINANK_PUBLIC_LEVERAGE_LADDER = [
    "25x",
    "30x",
    "40x",
    "50x",
    "60x",
    "70x",
    "80x",
    "90x",
    "100x",
]

_STEP_TABLE = {
    ("BTCUSDT", "1d"): Decimal("10.0"),
    ("BTCUSDT", "1w"): Decimal("25.0"),
    ("ETHUSDT", "1d"): Decimal("0.5"),
    ("ETHUSDT", "1w"): Decimal("2.0"),
}

_RANGE_RULES = {
    "1d": {
        "lower_quantile": Decimal("0.05"),
        "upper_quantile": Decimal("0.95"),
        "min_clamp": Decimal("0.08"),
        "max_clamp": Decimal("0.12"),
    },
    "1w": {
        "lower_quantile": Decimal("0.02"),
        "upper_quantile": Decimal("0.98"),
        "min_clamp": Decimal("0.12"),
        "max_clamp": Decimal("0.18"),
    },
}

_SEEDED_LADDER_EXPANSION = {
    "25x": ("25x", "30x", "40x"),
    "50x": ("50x", "60x", "70x"),
    "100x": ("80x", "90x", "100x"),
}


def _bucket_sort_key(item: tuple[tuple[float, str], float]) -> tuple[float, float]:
    price_level, leverage = item[0]
    leverage_order = (
        COINANK_PUBLIC_LEVERAGE_LADDER.index(leverage)
        if leverage in COINANK_PUBLIC_LEVERAGE_LADDER
        else math.inf
    )
    return (price_level, leverage_order)


class PublicLiqmapBuildError(RuntimeError):
    """Raised when the public liqmap builder cannot return a valid payload."""


class CoinankPublicBucket(BaseModel):
    price_level: float
    leverage: str
    volume: float


class CoinankPublicCumulativePoint(BaseModel):
    price_level: float
    value: float


class CoinankPublicGrid(BaseModel):
    step: float
    anchor_price: float
    min_price: float
    max_price: float


class CoinankPublicMapResponse(BaseModel):
    schema_version: str
    source: str
    exchange: str
    symbol: str
    timeframe: str
    profile: str
    current_price: float
    grid: CoinankPublicGrid
    leverage_ladder: list[str]
    long_buckets: list[CoinankPublicBucket]
    short_buckets: list[CoinankPublicBucket]
    cumulative_long: list[CoinankPublicCumulativePoint]
    cumulative_short: list[CoinankPublicCumulativePoint]
    last_data_timestamp: str
    is_stale_real_data: bool


@dataclass(frozen=True)
class _BuilderMetadata:
    current_price: Decimal
    last_data_timestamp: datetime
    is_stale_real_data: bool
    timeframe_days: int
    step: Decimal


def _load_latest_public_price(symbol: str) -> Decimal:
    """Resolve the public builder anchor price from QuestDB hot data."""
    qdb = QuestDBService()
    if qdb.is_available():
        for interval in ("1m", "5m", None):
            price = qdb.get_latest_price(symbol, interval=interval)
            if price is not None:
                return Decimal(str(price))

    return _get_fallback_price(symbol)


def resolve_public_liqmap_step(symbol: str, timeframe: str) -> Decimal:
    normalized_symbol = symbol.upper()
    normalized_timeframe = timeframe.lower()

    if normalized_symbol not in SUPPORTED_PUBLIC_LIQMAP_SYMBOLS:
        raise ValueError(
            f"Unsupported public liqmap symbol '{symbol}'. "
            f"Supported symbols: {sorted(SUPPORTED_PUBLIC_LIQMAP_SYMBOLS)}"
        )
    if normalized_timeframe not in SUPPORTED_PUBLIC_LIQMAP_TIMEFRAMES:
        raise ValueError(
            f"Unsupported public liqmap timeframe '{timeframe}'. "
            f"Supported timeframes: {sorted(SUPPORTED_PUBLIC_LIQMAP_TIMEFRAMES)}"
        )

    return _STEP_TABLE[(normalized_symbol, normalized_timeframe)]


def snap_price_to_public_grid(
    *,
    raw_price: Decimal,
    anchor_price: Decimal,
    step: Decimal,
) -> Decimal:
    if step <= 0:
        raise ValueError("Public liqmap grid step must be positive")
    return anchor_price + (
        ((raw_price - anchor_price) / step).to_integral_value(rounding=ROUND_HALF_UP) * step
    )


def expand_public_leverage_ladder(
    raw_buckets: list[CoinankPublicBucket],
) -> list[CoinankPublicBucket]:
    if not raw_buckets:
        return []

    present_tiers = {bucket.leverage for bucket in raw_buckets}
    preserve_exact = any(tier not in _SEEDED_LADDER_EXPANSION for tier in present_tiers)

    aggregated: dict[tuple[float, str], float] = {}
    for bucket in raw_buckets:
        if preserve_exact:
            target_tiers = (bucket.leverage,)
        else:
            target_tiers = _SEEDED_LADDER_EXPANSION.get(bucket.leverage, (bucket.leverage,))

        volume_per_tier = bucket.volume / len(target_tiers)
        for tier in target_tiers:
            key = (bucket.price_level, tier)
            aggregated[key] = aggregated.get(key, 0.0) + volume_per_tier

    return [
        CoinankPublicBucket(price_level=price_level, leverage=leverage, volume=volume)
        for (price_level, leverage), volume in sorted(
            aggregated.items(),
            key=_bucket_sort_key,
        )
    ]


def build_cumulative_series(
    *,
    side: str,
    current_price: Decimal,
    buckets: list[CoinankPublicBucket],
) -> list[CoinankPublicCumulativePoint]:
    volume_by_price: dict[float, float] = {}
    for bucket in buckets:
        volume_by_price[bucket.price_level] = volume_by_price.get(bucket.price_level, 0.0) + bucket.volume

    sorted_prices = sorted(volume_by_price)
    current_price_float = float(current_price)

    if side == "long":
        relevant_prices = [price for price in sorted_prices if price < current_price_float]
        cumulative_by_price: dict[float, float] = {}
        running_total = 0.0
        for price in reversed(relevant_prices):
            running_total += volume_by_price[price]
            cumulative_by_price[price] = running_total
        return [
            *[
                CoinankPublicCumulativePoint(
                    price_level=price,
                    value=cumulative_by_price[price],
                )
                for price in relevant_prices
            ],
            CoinankPublicCumulativePoint(price_level=current_price_float, value=0.0),
        ]

    if side != "short":
        raise ValueError(f"Unsupported cumulative side '{side}'")

    relevant_prices = [price for price in sorted_prices if price > current_price_float]
    points = [CoinankPublicCumulativePoint(price_level=current_price_float, value=0.0)]
    running_total = 0.0
    for price in relevant_prices:
        running_total += volume_by_price[price]
        points.append(CoinankPublicCumulativePoint(price_level=price, value=running_total))
    return points


def derive_public_liqmap_range(
    *,
    observed_prices: list[Decimal],
    current_price: Decimal,
    timeframe: str,
) -> tuple[float, float]:
    rule = _RANGE_RULES.get(timeframe.lower())
    if rule is None:
        raise ValueError(
            f"Unsupported public liqmap timeframe '{timeframe}'. "
            f"Supported timeframes: {sorted(_RANGE_RULES)}"
        )

    min_clamp = current_price * (Decimal("1.0") - rule["min_clamp"])
    max_clamp = current_price * (Decimal("1.0") + rule["min_clamp"])
    hard_min = current_price * (Decimal("1.0") - rule["max_clamp"])
    hard_max = current_price * (Decimal("1.0") + rule["max_clamp"])

    if not observed_prices:
        return (_quantize_price(min_clamp), _quantize_price(max_clamp))

    sorted_prices = sorted(observed_prices)
    lower_index = _quantile_index(len(sorted_prices), rule["lower_quantile"], rounding="floor")
    upper_index = _quantile_index(len(sorted_prices), rule["upper_quantile"], rounding="ceil")
    filtered_prices = sorted_prices[lower_index : upper_index + 1] or sorted_prices

    filtered_min = min(filtered_prices)
    filtered_max = max(filtered_prices)
    span = filtered_max - filtered_min
    if span <= 0:
        span = current_price * Decimal("0.01")
    padding = span * Decimal("0.06")

    x_min = filtered_min - padding
    x_max = filtered_max + padding

    if x_min > min_clamp:
        x_min = min_clamp
    if x_max < max_clamp:
        x_max = max_clamp

    if x_min < hard_min:
        x_min = hard_min
    if x_max > hard_max:
        x_max = hard_max

    return (_quantize_price(x_min), _quantize_price(x_max))


def _artifact_has_public_liqmap_data(artifact: dict[str, Any]) -> bool:
    """Return True when an artifact can produce a meaningful public payload."""
    long_distribution = artifact.get("long_distribution")
    short_distribution = artifact.get("short_distribution")
    if not isinstance(long_distribution, dict) or not isinstance(short_distribution, dict):
        return False
    return bool(long_distribution) or bool(short_distribution)


def build_coinank_public_map_response(
    *,
    exchange: str,
    symbol: str,
    timeframe: str,
) -> CoinankPublicMapResponse:
    normalized_exchange = exchange.lower()
    normalized_symbol = symbol.upper()
    normalized_timeframe = timeframe.lower()

    # Prefer modeled snapshot artifacts for the exchanges supported by the public builder.
    model_id = f"{normalized_exchange}_standard"
    latest_ts = snapshot_reader.get_latest_available_snapshot_ts(
        normalized_exchange,
        normalized_symbol,
        model_id,
    )
    if latest_ts:
        artifact = snapshot_reader.load_artifact(
            normalized_exchange, normalized_symbol, latest_ts, model_id
        )
        if artifact and _artifact_has_public_liqmap_data(artifact):
            return _build_response_from_artifact(
                exchange=normalized_exchange,
                symbol=normalized_symbol,
                timeframe=normalized_timeframe,
                artifact=artifact,
            )

    # Legacy Fallback (Binance-only DuckDB path)
    if normalized_exchange != "binance":
        raise HTTPException(
            status_code=404,
            detail=(
                f"No available artifact for exchange={normalized_exchange} "
                f"symbol={normalized_symbol} timeframe={normalized_timeframe}"
            ),
        )

    step = resolve_public_liqmap_step(normalized_symbol, normalized_timeframe)
    metadata = _load_public_liqmap_metadata(
        symbol=normalized_symbol,
        timeframe=normalized_timeframe,
        step=step,
    )

    profile = get_profile("rektslug-ank-public")
    with DuckDBService(read_only=True) as db:
        raw_df = db.calculate_liquidations_oi_based(
            symbol=normalized_symbol,
            current_price=float(metadata.current_price),
            bin_size=float(step),
            lookback_days=metadata.timeframe_days,
            leverage_weights=profile.get_leverage_weights(normalized_symbol, metadata.timeframe_days),
            side_weights=profile.get_side_weights(normalized_symbol, metadata.timeframe_days),
            kline_interval="auto",
            allow_stale_kline_fallback=True,
        )

    if raw_df.empty:
        raise PublicLiqmapBuildError(
            f"No public liqmap data produced for symbol={normalized_symbol} timeframe={normalized_timeframe}"
        )

    long_seed_buckets = _build_side_buckets(
        records=raw_df.to_dict("records"),
        side="buy",
        anchor_price=metadata.current_price,
        step=metadata.step,
    )
    short_seed_buckets = _build_side_buckets(
        records=raw_df.to_dict("records"),
        side="sell",
        anchor_price=metadata.current_price,
        step=metadata.step,
    )

    long_buckets = expand_public_leverage_ladder(long_seed_buckets)
    short_buckets = expand_public_leverage_ladder(short_seed_buckets)
    if not long_buckets and not short_buckets:
        raise PublicLiqmapBuildError(
            f"No public liqmap buckets produced for symbol={normalized_symbol} timeframe={normalized_timeframe}"
        )

    all_prices = [
        Decimal(str(bucket.price_level))
        for bucket in [*long_buckets, *short_buckets]
    ]
    min_price, max_price = derive_public_liqmap_range(
        observed_prices=all_prices,
        current_price=metadata.current_price,
        timeframe=normalized_timeframe,
    )

    return CoinankPublicMapResponse(
        schema_version="1.0",
        source="coinank-public-builder",
        exchange=normalized_exchange,
        symbol=normalized_symbol,
        timeframe=normalized_timeframe,
        profile="rektslug-ank-public",
        current_price=float(metadata.current_price),
        grid=CoinankPublicGrid(
            step=float(metadata.step),
            anchor_price=float(metadata.current_price),
            min_price=min_price,
            max_price=max_price,
        ),
        leverage_ladder=COINANK_PUBLIC_LEVERAGE_LADDER,
        long_buckets=long_buckets,
        short_buckets=short_buckets,
        cumulative_long=build_cumulative_series(
            side="long",
            current_price=metadata.current_price,
            buckets=long_buckets,
        ),
        cumulative_short=build_cumulative_series(
            side="short",
            current_price=metadata.current_price,
            buckets=short_buckets,
        ),
        last_data_timestamp=_format_timestamp(metadata.last_data_timestamp),
        is_stale_real_data=metadata.is_stale_real_data,
    )


def _build_side_buckets(
    *,
    records: list[dict],
    side: str,
    anchor_price: Decimal,
    step: Decimal,
) -> list[CoinankPublicBucket]:
    aggregated: dict[tuple[float, str], float] = {}
    for row in records:
        if row["side"] != side:
            continue

        snapped_price = snap_price_to_public_grid(
            raw_price=Decimal(str(row["liq_price"])),
            anchor_price=anchor_price,
            step=step,
        )
        leverage = f"{int(row['leverage'])}x"
        key = (_quantize_price(snapped_price), leverage)
        aggregated[key] = aggregated.get(key, 0.0) + float(row["volume"])

    return [
        CoinankPublicBucket(price_level=price_level, leverage=leverage, volume=volume)
        for (price_level, leverage), volume in sorted(
            aggregated.items(),
            key=_bucket_sort_key,
        )
    ]


def _load_public_liqmap_metadata(
    *,
    symbol: str,
    timeframe: str,
    step: Decimal,
) -> _BuilderMetadata:
    timeframe_days = SUPPORTED_PUBLIC_LIQMAP_TIMEFRAMES[timeframe]
    current_price = _load_latest_public_price(symbol)
    with DuckDBService(read_only=True) as db:
        table_name, _interval = db._resolve_oi_kline_source(
            symbol=symbol,
            lookback_days=timeframe_days,
            kline_interval="auto",
            allow_stale_fallback=True,
        )
        row = db.conn.execute(
            f"""
            SELECT MAX(open_time)
            FROM {table_name}
            WHERE symbol = ?
            """,
            [symbol],
        ).fetchone()

    last_data_timestamp = row[0] if row else None
    if last_data_timestamp is None:
        raise PublicLiqmapBuildError(
            f"Missing source timestamp for symbol={symbol} timeframe={timeframe}"
        )
    if last_data_timestamp.tzinfo is None:
        last_data_timestamp = last_data_timestamp.replace(tzinfo=timezone.utc)
    else:
        last_data_timestamp = last_data_timestamp.astimezone(timezone.utc)

    is_stale_real_data = last_data_timestamp < datetime.now(timezone.utc) - timedelta(minutes=20)
    return _BuilderMetadata(
        current_price=current_price,
        last_data_timestamp=last_data_timestamp,
        is_stale_real_data=is_stale_real_data,
        timeframe_days=timeframe_days,
        step=step,
    )


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _quantile_index(length: int, quantile: Decimal, *, rounding: str) -> int:
    if length <= 1:
        return 0
    position = Decimal(length - 1) * quantile
    if rounding == "floor":
        index = int(position.to_integral_value(rounding="ROUND_FLOOR"))
    else:
        index = int(position.to_integral_value(rounding="ROUND_CEILING"))
    return max(0, min(length - 1, index))


def _build_response_from_artifact(
    *,
    exchange: str,
    symbol: str,
    timeframe: str,
    artifact: dict[str, Any],
) -> CoinankPublicMapResponse:
    """Bridge a ModeledSnapshotArtifact into the Coinank-style public response."""
    current_price = float(artifact["reference_price"])
    snapshot_ts = artifact["snapshot_ts"]

    # Artifact grid info
    artifact_grid = artifact.get("bucket_grid", {})
    step = float(artifact_grid.get("step") or float(resolve_public_liqmap_step(symbol, timeframe)))

    # Spread volumes across leverage tiers for visual richness (matches Binance style)
    long_buckets = []
    for price_str, volume in artifact["long_distribution"].items():
        price = float(price_str)
        # Split volume evenly across all ladder tiers to ensure 3-color stacking in UI
        per_tier_volume = volume / len(COINANK_PUBLIC_LEVERAGE_LADDER)
        for leverage in COINANK_PUBLIC_LEVERAGE_LADDER:
            long_buckets.append(CoinankPublicBucket(
                price_level=price,
                leverage=leverage,
                volume=per_tier_volume
            ))

    short_buckets = []
    for price_str, volume in artifact["short_distribution"].items():
        price = float(price_str)
        per_tier_volume = volume / len(COINANK_PUBLIC_LEVERAGE_LADDER)
        for leverage in COINANK_PUBLIC_LEVERAGE_LADDER:
            short_buckets.append(CoinankPublicBucket(
                price_level=price,
                leverage=leverage,
                volume=per_tier_volume
            ))

    # Calculate grid range for the chart
    sorted_long = sorted([b.price_level for b in long_buckets])
    sorted_short = sorted([b.price_level for b in short_buckets])

    min_price = sorted_long[0] if sorted_long else current_price * 0.9
    max_price = sorted_short[-1] if sorted_short else current_price * 1.1

    # Stale check
    ts_dt = datetime.fromisoformat(snapshot_ts.replace("Z", "+00:00"))
    is_stale = ts_dt < datetime.now(timezone.utc) - timedelta(minutes=20)

    return CoinankPublicMapResponse(
        schema_version="1.0",
        source=f"modeled-snapshot-{artifact['model_id']}",
        exchange=exchange,
        symbol=symbol,
        timeframe=timeframe,
        profile="rektslug-ank-public",
        current_price=current_price,
        grid=CoinankPublicGrid(
            step=step,
            anchor_price=current_price,
            min_price=float(min_price),
            max_price=float(max_price),
        ),
        leverage_ladder=COINANK_PUBLIC_LEVERAGE_LADDER,
        long_buckets=long_buckets,
        short_buckets=short_buckets,
        cumulative_long=build_cumulative_series(
            side="long",
            current_price=Decimal(str(current_price)),
            buckets=long_buckets,
        ),
        cumulative_short=build_cumulative_series(
            side="short",
            current_price=Decimal(str(current_price)),
            buckets=short_buckets,
        ),
        last_data_timestamp=snapshot_ts,
        is_stale_real_data=is_stale,
    )


def _quantize_price(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
