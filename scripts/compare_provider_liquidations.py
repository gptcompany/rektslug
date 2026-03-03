#!/usr/bin/env python3
"""Normalize and compare raw liquidation captures across providers.

This script reads one or more manifests produced by `capture_provider_api.py`,
extracts the most relevant liquidation dataset per provider, normalizes it into
the same summary shape, and writes a comparison report.

Examples:
    uv run python scripts/compare_provider_liquidations.py

    uv run python scripts/compare_provider_liquidations.py \
        --manifest data/validation/raw_provider_api/20260303T113339Z/manifest.json

    uv run python scripts/compare_provider_liquidations.py \
        --manifest data/validation/raw_provider_api/20260303T113339Z \
        --manifest data/validation/raw_provider_api/20260303T120000Z
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.validation.constants import VALIDATION_DB_PATH

RAW_CAPTURE_ROOT = Path("data/validation/raw_provider_api")
DEFAULT_OUTPUT_DIR = Path("data/validation/provider_comparisons")
DEFAULT_COMPARISON_DB_PATH = Path(VALIDATION_DB_PATH)

LONG_VALUE_KEYS = (
    "long_value",
    "long_usd",
    "long_volume",
    "long_volume_usd",
    "longVolume",
    "longVolumeUsd",
    "long_density",
    "longDensity",
    "longLiqValue",
    "longLiqUsd",
    "sell_volume_usd",
    "sellVolumeUsd",
)
SHORT_VALUE_KEYS = (
    "short_value",
    "short_usd",
    "short_volume",
    "short_volume_usd",
    "shortVolume",
    "shortVolumeUsd",
    "short_density",
    "shortDensity",
    "shortLiqValue",
    "shortLiqUsd",
    "buy_volume_usd",
    "buyVolumeUsd",
)
PRICE_KEYS = ("price", "price_level", "priceLevel", "px")
TIMESTAMP_KEYS = ("timestamp", "time", "ts", "openTime", "closeTime")
LIKELY_ARRAY_KEYS = (
    "levels",
    "data",
    "rows",
    "items",
    "list",
    "series",
    "points",
    "buckets",
    "priceLevels",
)
PRICE_ARRAY_KEYS = ("priceArray", "prices", "price_list", "priceList")
LONG_ARRAY_KEYS = (
    "longs",
    "long",
    "longData",
    "long_values",
    "longValues",
    "longLiqValues",
    "long_density",
    "longDensity",
)
SHORT_ARRAY_KEYS = (
    "shorts",
    "short",
    "shortData",
    "short_values",
    "shortValues",
    "shortLiqValues",
    "short_density",
    "shortDensity",
)


@dataclass
class CaptureFile:
    """Single captured response payload from a provider."""

    provider: str
    source_url: str
    saved_file: Path
    content_type: str
    payload: Any
    manifest_path: Path


@dataclass
class NormalizedDataset:
    """Provider-agnostic liquidation summary."""

    provider: str
    source_url: str
    saved_file: str
    dataset_kind: str
    structure: str
    unit: str
    symbol: str | None
    exchange: str | None
    timeframe: str | None
    bucket_count: int
    total_long: float
    total_short: float
    peak_long: float
    peak_short: float
    current_price: float | None = None
    price_step_median: float | None = None
    time_step_median_ms: float | None = None
    notes: list[str] = field(default_factory=list)
    parse_score: int = 0

    def to_public_dict(self) -> dict[str, Any]:
        """Hide internal score in the final report."""
        data = asdict(self)
        data.pop("parse_score", None)
        return data


def utc_timestamp_slug() -> str:
    """Return a filesystem-safe UTC timestamp."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        action="append",
        help="Manifest file or run directory. Can be passed multiple times.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional explicit output path for the JSON report.",
    )
    parser.add_argument(
        "--persist-db",
        action="store_true",
        help="Persist normalized datasets and pairwise comparisons into the existing DuckDB.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        help="Override DuckDB path. Defaults to the validation DuckDB.",
    )
    return parser.parse_args()


def resolve_manifest_paths(manifest_args: list[str] | None) -> list[Path]:
    """Resolve CLI manifest args or default to the latest run manifest."""
    if manifest_args:
        resolved: list[Path] = []
        for raw_path in manifest_args:
            candidate = Path(raw_path)
            if candidate.is_dir():
                candidate = candidate / "manifest.json"
            resolved.append(candidate)
        return resolved

    manifests = sorted(RAW_CAPTURE_ROOT.glob("*/manifest.json"))
    if not manifests:
        raise SystemExit(
            "No manifests found under data/validation/raw_provider_api. "
            "Run scripts/capture_provider_api.py first or pass --manifest."
        )
    return [manifests[-1]]


def load_capture_files(manifest_paths: list[Path]) -> list[CaptureFile]:
    """Load all captures referenced by the manifests."""
    captures: list[CaptureFile] = []

    for manifest_path in manifest_paths:
        if not manifest_path.exists():
            raise SystemExit(f"Manifest not found: {manifest_path}")

        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        for provider_summary in payload.get("providers", []):
            provider = provider_summary.get("provider") or "unknown"
            for capture in provider_summary.get("captures", []):
                saved_file = capture.get("saved_file")
                if not saved_file:
                    continue

                file_path = Path(saved_file)
                if not file_path.is_absolute() and not file_path.exists():
                    file_path = (manifest_path.parent / file_path).resolve()
                if not file_path.exists():
                    continue

                try:
                    file_payload = json.loads(file_path.read_text(encoding="utf-8"))
                except Exception:
                    continue

                captures.append(
                    CaptureFile(
                        provider=provider,
                        source_url=capture.get("source_url", ""),
                        saved_file=file_path,
                        content_type=capture.get("content_type", ""),
                        payload=file_payload,
                        manifest_path=manifest_path,
                    )
                )

    return captures


def safe_float(value: Any) -> float | None:
    """Convert numbers and numeric strings into floats."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if math.isfinite(float(value)):
            return float(value)
        return None
    if isinstance(value, str):
        cleaned = value.replace(",", "").replace("$", "").strip()
        if not cleaned:
            return None
        try:
            parsed = float(cleaned)
        except Exception:
            return None
        if math.isfinite(parsed):
            return parsed
    return None


def median_step(values: list[float]) -> float | None:
    """Return the median delta between sorted unique values."""
    uniques = sorted(set(values))
    if len(uniques) < 2:
        return None
    diffs = [uniques[idx] - uniques[idx - 1] for idx in range(1, len(uniques))]
    diffs = [diff for diff in diffs if diff > 0]
    if not diffs:
        return None
    midpoint = len(diffs) // 2
    diffs.sort()
    if len(diffs) % 2 == 1:
        return diffs[midpoint]
    return (diffs[midpoint - 1] + diffs[midpoint]) / 2


def infer_unit(url: str, field_names: set[str]) -> str:
    """Infer whether values look like USD, relative density, or unknown."""
    lowered_url = url.lower()
    lowered_fields = {name.lower() for name in field_names}
    if any("density" in name for name in lowered_fields):
        return "relative_density"
    if any(
        token in lowered_url
        for token in ("liqvalue", "usd", "value", "/liquidations", "notional")
    ):
        return "usd_notional"
    if any(any(token in name for token in ("usd", "value", "notional")) for name in lowered_fields):
        return "usd_notional"
    return "unknown"


def parse_query_params(url: str) -> dict[str, str]:
    """Flatten URL query params into a simple dict."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    return {key: values[0] for key, values in params.items() if values}


def parse_coinank_agg_liq_map(capture: CaptureFile) -> NormalizedDataset | None:
    """Parse CoinAnk's aggregated liquidation map endpoint."""
    if "/api/liqMap/getAggLiqMap" not in capture.source_url:
        return None

    root = capture.payload
    data = root.get("data")
    if not isinstance(data, dict):
        return None

    prices_raw = data.get("prices")
    if not isinstance(prices_raw, list) or not prices_raw:
        return None

    exchange_order = ("Binance", "Bybit", "Hyperliquid", "Okex", "Aster", "Lighter")
    exchange_key = next(
        (
            candidate
            for candidate in exchange_order
            if isinstance(data.get(candidate), list) and len(data[candidate]) == len(prices_raw)
        ),
        None,
    )
    if exchange_key is None:
        return None

    values_raw = data[exchange_key]
    current_price = safe_float(data.get("lastPrice"))
    all_prices: list[float] = []
    long_values: list[float] = []
    short_values: list[float] = []
    active_bins = 0

    for raw_price, raw_value in zip(prices_raw, values_raw):
        price = safe_float(raw_price)
        value = safe_float(raw_value) or 0.0
        if price is None:
            continue
        all_prices.append(price)
        if value <= 0:
            continue
        active_bins += 1
        if current_price is not None and price <= current_price:
            long_values.append(value)
        elif current_price is not None and price > current_price:
            short_values.append(value)
        else:
            long_values.append(value)

    params = parse_query_params(capture.source_url)
    symbol = params.get("baseCoin")
    if symbol:
        symbol = f"{symbol.upper()}USDT"

    notes = [
        "CoinAnk getAggLiqMap returns one magnitude array per exchange plus a shared price grid.",
        "Long and short totals are inferred by splitting bins around lastPrice.",
    ]

    return NormalizedDataset(
        provider=capture.provider,
        source_url=capture.source_url,
        saved_file=str(capture.saved_file),
        dataset_kind="liquidation_heatmap",
        structure="price_bins",
        unit="usd_notional",
        symbol=symbol,
        exchange=exchange_key,
        timeframe=params.get("interval"),
        bucket_count=active_bins,
        total_long=sum(long_values),
        total_short=sum(short_values),
        peak_long=max(long_values, default=0.0),
        peak_short=max(short_values, default=0.0),
        current_price=current_price,
        price_step_median=median_step([price for price in all_prices if price is not None]),
        time_step_median_ms=None,
        notes=notes,
        parse_score=95,
    )


def parse_bitcoincounterflow_liquidations(capture: CaptureFile) -> NormalizedDataset | None:
    """Parse the known Bitcoin CounterFlow /api/liquidations shape."""
    if "/api/liquidations" not in capture.source_url:
        return None

    root = capture.payload
    data = root.get("data")
    if not isinstance(data, dict):
        return None
    candles = data.get("candles")
    if not isinstance(candles, list) or not candles:
        return None

    long_values: list[float] = []
    short_values: list[float] = []
    timestamps: list[float] = []
    prices: list[float] = []
    for candle in candles:
        if not isinstance(candle, dict):
            continue
        short_value = safe_float(candle.get("buy_volume_usd")) or 0.0
        long_value = safe_float(candle.get("sell_volume_usd")) or 0.0
        long_values.append(long_value)
        short_values.append(short_value)
        timestamp = safe_float(candle.get("timestamp"))
        close_price = safe_float(candle.get("close_price"))
        if timestamp is not None:
            timestamps.append(timestamp)
        if close_price is not None:
            prices.append(close_price)

    if not long_values and not short_values:
        return None

    metadata = root.get("metadata", {})
    notes = [
        "Long side is inferred from sell_volume_usd, short side from buy_volume_usd.",
    ]
    if metadata.get("period"):
        notes.append(f"Provider metadata period: {metadata['period']}")

    return NormalizedDataset(
        provider=capture.provider,
        source_url=capture.source_url,
        saved_file=str(capture.saved_file),
        dataset_kind="liquidations_timeseries",
        structure="time_candles",
        unit="usd_notional",
        symbol=data.get("symbol"),
        exchange=data.get("exchange"),
        timeframe=data.get("timeframe"),
        bucket_count=len(long_values),
        total_long=sum(long_values),
        total_short=sum(short_values),
        peak_long=max(long_values, default=0.0),
        peak_short=max(short_values, default=0.0),
        current_price=prices[-1] if prices else None,
        price_step_median=None,
        time_step_median_ms=median_step(timestamps),
        notes=notes,
        parse_score=100,
    )


def parse_coinglass_encrypted_liquidations(capture: CaptureFile) -> NormalizedDataset | None:
    """Recognize Coinglass liquidation endpoints that currently return encoded payloads."""
    lowered_url = capture.source_url.lower()
    if "coinglass.com" not in lowered_url:
        return None
    if not re.search(r"liq|liquidat|heatmap", lowered_url):
        return None

    root = capture.payload
    encoded = root.get("data")
    if not isinstance(encoded, str) or not encoded:
        return None

    decoded_size = None
    try:
        decoded_size = len(base64.b64decode(encoded))
    except Exception:
        decoded_size = None

    dataset_kind = "encrypted_liquidation_payload"
    parse_score = 40
    if "heatmap" in lowered_url:
        dataset_kind = "encrypted_liquidation_heatmap"
        parse_score = 55
    elif "liquidation/chart" in lowered_url:
        dataset_kind = "encrypted_liquidations_chart"
        parse_score = 50

    params = parse_query_params(capture.source_url)
    notes = [
        "Coinglass currently returns an encoded string in data; numeric decoding is not implemented yet.",
        f"Encoded chars: {len(encoded)}",
    ]
    if decoded_size is not None:
        notes.append(f"Base64-decoded bytes: {decoded_size}")

    return NormalizedDataset(
        provider=capture.provider,
        source_url=capture.source_url,
        saved_file=str(capture.saved_file),
        dataset_kind=dataset_kind,
        structure="encrypted_base64",
        unit="encrypted_payload",
        symbol=params.get("symbol"),
        exchange=params.get("exName"),
        timeframe=params.get("time") or params.get("range") or params.get("timeType"),
        bucket_count=0,
        total_long=0.0,
        total_short=0.0,
        peak_long=0.0,
        peak_short=0.0,
        current_price=None,
        price_step_median=None,
        time_step_median_ms=None,
        notes=notes,
        parse_score=parse_score,
    )


def find_records_with_keys(payload: Any) -> list[dict[str, Any]] | None:
    """Locate a list of dict records that look like time or price rows."""
    queue: list[Any] = [payload]
    while queue:
        current = queue.pop(0)
        if isinstance(current, dict):
            for preferred_key in LIKELY_ARRAY_KEYS:
                candidate = current.get(preferred_key)
                if isinstance(candidate, list) and candidate and all(
                    isinstance(item, dict) for item in candidate
                ):
                    if any(
                        any(key in item for key in PRICE_KEYS + TIMESTAMP_KEYS)
                        for item in candidate[:5]
                    ):
                        return candidate
            queue.extend(current.values())
            continue

        if isinstance(current, list):
            if current and all(isinstance(item, dict) for item in current):
                if any(
                    any(key in item for key in PRICE_KEYS + TIMESTAMP_KEYS)
                    for item in current[:5]
                ):
                    return current
            queue.extend(current[:20])

    return None


def first_numeric(record: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    """Return the first numeric field among the candidate keys."""
    for key in keys:
        if key in record:
            value = safe_float(record.get(key))
            if value is not None:
                return value
    return None


def parse_record_series(capture: CaptureFile) -> NormalizedDataset | None:
    """Parse a generic record list containing price or timestamp rows."""
    records = find_records_with_keys(capture.payload)
    if not records:
        return None

    long_values: list[float] = []
    short_values: list[float] = []
    prices: list[float] = []
    timestamps: list[float] = []
    field_names: set[str] = set()

    for record in records:
        field_names.update(record.keys())
        long_value = first_numeric(record, LONG_VALUE_KEYS)
        short_value = first_numeric(record, SHORT_VALUE_KEYS)
        if long_value is None and short_value is None:
            continue
        long_values.append(long_value or 0.0)
        short_values.append(short_value or 0.0)

        price_value = first_numeric(record, PRICE_KEYS)
        if price_value is not None:
            prices.append(price_value)
        timestamp_value = first_numeric(record, TIMESTAMP_KEYS)
        if timestamp_value is not None:
            timestamps.append(timestamp_value)

    if not long_values and not short_values:
        return None

    params = parse_query_params(capture.source_url)
    structure = "price_bins" if prices and len(prices) >= len(timestamps) else "time_series"
    dataset_kind = "liquidation_heatmap" if structure == "price_bins" else "liquidations_timeseries"
    notes: list[str] = []
    if capture.provider in {"coinank", "coinglass"}:
        notes.append("Parsed via generic record-series heuristic.")

    return NormalizedDataset(
        provider=capture.provider,
        source_url=capture.source_url,
        saved_file=str(capture.saved_file),
        dataset_kind=dataset_kind,
        structure=structure,
        unit=infer_unit(capture.source_url, field_names),
        symbol=params.get("symbol") or params.get("coin"),
        exchange=params.get("exchange"),
        timeframe=params.get("timeframe") or params.get("interval"),
        bucket_count=len(long_values),
        total_long=sum(long_values),
        total_short=sum(short_values),
        peak_long=max(long_values, default=0.0),
        peak_short=max(short_values, default=0.0),
        current_price=None,
        price_step_median=median_step(prices),
        time_step_median_ms=median_step(timestamps),
        notes=notes,
        parse_score=80 if dataset_kind == "liquidations_timeseries" else 70,
    )


def find_parallel_arrays(payload: Any) -> tuple[list[Any], list[Any], list[Any]] | None:
    """Locate a price array plus long/short arrays inside nested objects."""
    queue: list[Any] = [payload]
    while queue:
        current = queue.pop(0)
        if isinstance(current, dict):
            price_array = None
            long_array = None
            short_array = None

            for key in PRICE_ARRAY_KEYS:
                if isinstance(current.get(key), list):
                    price_array = current.get(key)
                    break
            for key in LONG_ARRAY_KEYS:
                if isinstance(current.get(key), list):
                    long_array = current.get(key)
                    break
            for key in SHORT_ARRAY_KEYS:
                if isinstance(current.get(key), list):
                    short_array = current.get(key)
                    break

            if isinstance(price_array, list) and isinstance(long_array, list) and isinstance(short_array, list):
                return price_array, long_array, short_array

            queue.extend(current.values())
            continue

        if isinstance(current, list):
            queue.extend(current[:20])

    return None


def parse_parallel_price_arrays(capture: CaptureFile) -> NormalizedDataset | None:
    """Parse price bins stored as parallel arrays."""
    arrays = find_parallel_arrays(capture.payload)
    if not arrays:
        return None

    raw_prices, raw_longs, raw_shorts = arrays
    count = min(len(raw_prices), len(raw_longs), len(raw_shorts))
    if count <= 0:
        return None

    prices: list[float] = []
    long_values: list[float] = []
    short_values: list[float] = []

    for idx in range(count):
        price = safe_float(raw_prices[idx])
        long_value = safe_float(raw_longs[idx]) or 0.0
        short_value = safe_float(raw_shorts[idx]) or 0.0
        if price is not None:
            prices.append(price)
        long_values.append(long_value)
        short_values.append(short_value)

    if not long_values and not short_values:
        return None

    params = parse_query_params(capture.source_url)
    notes = []
    if capture.provider in {"coinank", "coinglass"}:
        notes.append("Parsed via parallel price-array heuristic.")

    field_names = set(PRICE_ARRAY_KEYS + LONG_ARRAY_KEYS + SHORT_ARRAY_KEYS)
    return NormalizedDataset(
        provider=capture.provider,
        source_url=capture.source_url,
        saved_file=str(capture.saved_file),
        dataset_kind="liquidation_heatmap",
        structure="price_bins",
        unit=infer_unit(capture.source_url, field_names),
        symbol=params.get("symbol") or params.get("coin"),
        exchange=params.get("exchange"),
        timeframe=params.get("timeframe") or params.get("interval"),
        bucket_count=len(long_values),
        total_long=sum(long_values),
        total_short=sum(short_values),
        peak_long=max(long_values, default=0.0),
        peak_short=max(short_values, default=0.0),
        current_price=None,
        price_step_median=median_step(prices),
        time_step_median_ms=None,
        notes=notes,
        parse_score=60,
    )


def parse_capture(capture: CaptureFile) -> NormalizedDataset | None:
    """Try all known parsers in priority order."""
    for parser in (
        parse_coinank_agg_liq_map,
        parse_bitcoincounterflow_liquidations,
        parse_coinglass_encrypted_liquidations,
        parse_record_series,
        parse_parallel_price_arrays,
    ):
        parsed = parser(capture)
        if parsed is not None:
            return parsed
    return None


def choose_best_datasets(captures: list[CaptureFile]) -> tuple[dict[str, NormalizedDataset], dict[str, list[str]]]:
    """Pick the strongest normalized dataset per provider."""
    best_by_provider: dict[str, NormalizedDataset] = {}
    skipped_by_provider: dict[str, list[str]] = {}

    for capture in captures:
        parsed = parse_capture(capture)
        if parsed is None:
            if re.search(r"liq|liquidat|heatmap", capture.source_url, re.IGNORECASE):
                skipped_by_provider.setdefault(capture.provider, []).append(capture.source_url)
            continue

        existing = best_by_provider.get(parsed.provider)
        if existing is None or parsed.parse_score >= existing.parse_score:
            best_by_provider[parsed.provider] = parsed

    for provider, dataset in best_by_provider.items():
        skipped_by_provider.setdefault(provider, [])
        skipped_by_provider[provider] = [
            url
            for url in skipped_by_provider[provider]
            if url != dataset.source_url
        ]

    return best_by_provider, skipped_by_provider


def ratio(numerator: float, denominator: float) -> float | None:
    """Safe ratio helper."""
    if denominator == 0:
        return None
    return numerator / denominator


def compare_pair(left: NormalizedDataset, right: NormalizedDataset) -> dict[str, Any]:
    """Compare two normalized datasets."""
    return {
        "providers": [left.provider, right.provider],
        "dataset_kind_match": left.dataset_kind == right.dataset_kind,
        "structure_match": left.structure == right.structure,
        "unit_match": left.unit == right.unit,
        "symbol_match": (left.symbol or "").upper() == (right.symbol or "").upper(),
        "timeframe_match": left.timeframe == right.timeframe,
        "bucket_count_ratio": ratio(float(left.bucket_count), float(right.bucket_count)),
        "long_total_ratio": ratio(left.total_long, right.total_long),
        "short_total_ratio": ratio(left.total_short, right.total_short),
        "long_peak_ratio": ratio(left.peak_long, right.peak_long),
        "short_peak_ratio": ratio(left.peak_short, right.peak_short),
        "left": left.to_public_dict(),
        "right": right.to_public_dict(),
    }


def build_pairwise_comparisons(datasets: dict[str, NormalizedDataset]) -> list[dict[str, Any]]:
    """Create pairwise comparisons across all parsed providers."""
    providers = sorted(datasets)
    comparisons: list[dict[str, Any]] = []
    for idx, left_name in enumerate(providers):
        for right_name in providers[idx + 1 :]:
            comparisons.append(compare_pair(datasets[left_name], datasets[right_name]))
    return comparisons


def build_report(
    manifest_paths: list[Path],
    datasets: dict[str, NormalizedDataset],
    skipped_by_provider: dict[str, list[str]],
) -> dict[str, Any]:
    """Build the final JSON report."""
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "manifests": [str(path.resolve()) for path in manifest_paths],
        "providers": {
            provider: dataset.to_public_dict()
            for provider, dataset in sorted(datasets.items())
        },
        "unparsed_liquidation_like_endpoints": {
            provider: urls
            for provider, urls in sorted(skipped_by_provider.items())
            if urls
        },
        "pairwise_comparisons": build_pairwise_comparisons(datasets),
        "notes": [
            "Ratios are left/right, in the provider order shown in each comparison entry.",
            "CoinAnk and Coinglass parsing currently relies on generic heuristics until their raw payload shapes are captured and specialized.",
            "Bitcoin CounterFlow /api/liquidations is parsed explicitly and treated as USD-notional time-series liquidations.",
        ],
    }


def default_output_path() -> Path:
    """Return the default output path under provider comparisons."""
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_OUTPUT_DIR / f"{utc_timestamp_slug()}_provider_liquidations.json"


def resolve_db_path(explicit_path: Path | None) -> Path:
    """Resolve the DuckDB path used for provider-comparison persistence."""
    if explicit_path is not None:
        return explicit_path
    return DEFAULT_COMPARISON_DB_PATH


def ensure_comparison_tables(conn) -> None:
    """Create the provider comparison tables if they do not exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS provider_comparison_runs (
            run_id VARCHAR PRIMARY KEY,
            created_at TIMESTAMP,
            report_path VARCHAR,
            manifests_json VARCHAR,
            notes_json VARCHAR
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS provider_comparison_datasets (
            run_id VARCHAR,
            provider VARCHAR,
            source_url VARCHAR,
            saved_file VARCHAR,
            dataset_kind VARCHAR,
            structure VARCHAR,
            unit VARCHAR,
            symbol VARCHAR,
            exchange VARCHAR,
            timeframe VARCHAR,
            bucket_count INTEGER,
            total_long DOUBLE,
            total_short DOUBLE,
            peak_long DOUBLE,
            peak_short DOUBLE,
            current_price DOUBLE,
            price_step_median DOUBLE,
            time_step_median_ms DOUBLE,
            notes_json VARCHAR,
            PRIMARY KEY (run_id, provider)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS provider_comparison_pairs (
            run_id VARCHAR,
            left_provider VARCHAR,
            right_provider VARCHAR,
            dataset_kind_match BOOLEAN,
            structure_match BOOLEAN,
            unit_match BOOLEAN,
            symbol_match BOOLEAN,
            timeframe_match BOOLEAN,
            bucket_count_ratio DOUBLE,
            long_total_ratio DOUBLE,
            short_total_ratio DOUBLE,
            long_peak_ratio DOUBLE,
            short_peak_ratio DOUBLE,
            details_json VARCHAR,
            PRIMARY KEY (run_id, left_provider, right_provider)
        )
        """
    )


def persist_report_to_duckdb(report: dict[str, Any], output_path: Path, db_path: Path) -> None:
    """Persist the normalized comparison report into the existing DuckDB."""
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError("duckdb is required for --persist-db") from exc

    db_path.parent.mkdir(parents=True, exist_ok=True)
    run_id = output_path.stem

    conn = duckdb.connect(str(db_path))
    try:
        ensure_comparison_tables(conn)

        conn.execute(
            """
            INSERT OR REPLACE INTO provider_comparison_runs
            (run_id, created_at, report_path, manifests_json, notes_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                run_id,
                report["timestamp_utc"],
                str(output_path),
                json.dumps(report.get("manifests", []), ensure_ascii=True),
                json.dumps(report.get("notes", []), ensure_ascii=True),
            ],
        )

        conn.execute("DELETE FROM provider_comparison_datasets WHERE run_id = ?", [run_id])
        for provider, dataset in report.get("providers", {}).items():
            conn.execute(
                """
                INSERT INTO provider_comparison_datasets
                (
                    run_id, provider, source_url, saved_file, dataset_kind, structure, unit,
                    symbol, exchange, timeframe, bucket_count, total_long, total_short,
                    peak_long, peak_short, current_price, price_step_median,
                    time_step_median_ms, notes_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    run_id,
                    provider,
                    dataset.get("source_url"),
                    dataset.get("saved_file"),
                    dataset.get("dataset_kind"),
                    dataset.get("structure"),
                    dataset.get("unit"),
                    dataset.get("symbol"),
                    dataset.get("exchange"),
                    dataset.get("timeframe"),
                    dataset.get("bucket_count"),
                    dataset.get("total_long"),
                    dataset.get("total_short"),
                    dataset.get("peak_long"),
                    dataset.get("peak_short"),
                    dataset.get("current_price"),
                    dataset.get("price_step_median"),
                    dataset.get("time_step_median_ms"),
                    json.dumps(dataset.get("notes", []), ensure_ascii=True),
                ],
            )

        conn.execute("DELETE FROM provider_comparison_pairs WHERE run_id = ?", [run_id])
        for comparison in report.get("pairwise_comparisons", []):
            providers = comparison.get("providers", [])
            if len(providers) != 2:
                continue
            conn.execute(
                """
                INSERT INTO provider_comparison_pairs
                (
                    run_id, left_provider, right_provider, dataset_kind_match, structure_match,
                    unit_match, symbol_match, timeframe_match, bucket_count_ratio,
                    long_total_ratio, short_total_ratio, long_peak_ratio, short_peak_ratio,
                    details_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    run_id,
                    providers[0],
                    providers[1],
                    comparison.get("dataset_kind_match"),
                    comparison.get("structure_match"),
                    comparison.get("unit_match"),
                    comparison.get("symbol_match"),
                    comparison.get("timeframe_match"),
                    comparison.get("bucket_count_ratio"),
                    comparison.get("long_total_ratio"),
                    comparison.get("short_total_ratio"),
                    comparison.get("long_peak_ratio"),
                    comparison.get("short_peak_ratio"),
                    json.dumps(comparison, ensure_ascii=True),
                ],
            )
    finally:
        conn.close()


def generate_report(
    manifest_paths: list[Path],
    output_path: Path | None = None,
    persist_db: bool = False,
    db_path: Path | None = None,
) -> tuple[dict[str, Any], Path]:
    """Generate the comparison report and optionally persist it to DuckDB."""
    captures = load_capture_files(manifest_paths)
    datasets, skipped_by_provider = choose_best_datasets(captures)

    if not datasets:
        raise RuntimeError("No parseable liquidation datasets found in the supplied manifests.")

    report = build_report(manifest_paths, datasets, skipped_by_provider)
    resolved_output_path = output_path or default_output_path()
    resolved_output_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    if persist_db:
        persist_report_to_duckdb(
            report=report,
            output_path=resolved_output_path,
            db_path=resolve_db_path(db_path),
        )

    return report, resolved_output_path


def main() -> int:
    """CLI entry point."""
    args = parse_args()
    manifest_paths = resolve_manifest_paths(args.manifest)
    try:
        report, output_path = generate_report(
            manifest_paths=manifest_paths,
            output_path=args.output,
            persist_db=args.persist_db,
            db_path=args.db_path,
        )
    except RuntimeError as exc:
        print(str(exc))
        return 1

    datasets = report["providers"]

    print(f"providers parsed: {', '.join(sorted(datasets))}")
    if len(datasets) < 2:
        print("pairwise comparisons: none (need at least two parsed providers)")
    else:
        print(f"pairwise comparisons: {len(report['pairwise_comparisons'])}")
    if args.persist_db:
        print(f"duckdb: {resolve_db_path(args.db_path)}")
    print(f"report: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
