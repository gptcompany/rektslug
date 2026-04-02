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
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.validation.constants import VALIDATION_DB_PATH
from src.liquidationheatmap.validation.provider_profiles import get_provider_profile

RAW_CAPTURE_ROOT = Path("data/validation/raw_provider_api")
DEFAULT_OUTPUT_DIR = Path("data/validation/provider_comparisons")
DEFAULT_COMPARISON_DB_PATH = Path(VALIDATION_DB_PATH)
COINGLASS_DECODER_SCRIPT = REPO_ROOT / "scripts" / "coinglass_decode_payload.js"
COINGLASS_STATIC_SEED_SOURCES = {
    "55": "170b070da9654622",
    "66": "d6537d845a964081",
    "77": "863f08689c97435b",
}

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
    response_headers: dict[str, str] = field(default_factory=dict)
    request_headers: dict[str, str] = field(default_factory=dict)


@dataclass
class NormalizedDataset:
    """Provider-agnostic liquidation summary."""

    provider: str
    source_url: str
    saved_file: str
    dataset_kind: str
    structure: str
    unit: str
    product: str | None
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


@dataclass
class ProviderHints:
    """Auxiliary per-provider metadata derived from non-liquidation captures."""

    current_price: float | None = None
    current_price_source_url: str | None = None
    current_price_note: str | None = None


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
                        response_headers=normalize_headers(capture.get("response_headers")),
                        request_headers=normalize_headers(capture.get("request_headers")),
                    )
                )

    return captures


def normalize_headers(raw_headers: Any) -> dict[str, str]:
    """Normalize a serialized header mapping into lowercase string keys."""
    if not isinstance(raw_headers, dict):
        return {}

    normalized: dict[str, str] = {}
    for key, value in raw_headers.items():
        if value is None:
            continue
        normalized[str(key).lower()] = str(value)
    return normalized


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


def infer_product_from_source_url(url: str) -> str | None:
    """Infer the product family from a captured source URL."""
    lowered_path = urlparse(url).path.lower()

    if "/liquidations/levels" in lowered_path:
        return "liq-map"
    if "/api/liqmap/" in lowered_path or lowered_path.endswith("/liqmap"):
        return "liq-map"
    if "/api/index/v5/liqmap" in lowered_path or "/api/index/5/liqmap" in lowered_path:
        return "liq-map"
    if "/api/index/v5/liqheatmap" in lowered_path or "/api/index/5/liqheatmap" in lowered_path:
        return "liq-heat-map"
    if "/api/coin/liq/heatmap" in lowered_path:
        return "liq-heat-map"
    if "/liquidity-heatmap/" in lowered_path:
        return "liquidity-heatmap"
    if "/api/futures/liquidation/chart" in lowered_path:
        return "liquidations-chart"
    if "/api/coin/liquidation" in lowered_path:
        return "liquidation-summary"
    if "/api/liquidations" in lowered_path:
        return "liquidations-timeseries"
    return None


def normalize_coinglass_symbol(raw_symbol: str | None) -> tuple[str | None, str | None]:
    """Extract symbol/exchange from Coinglass params like Binance_BTCUSDT#heatmap."""
    if not raw_symbol:
        return None, None

    cleaned = raw_symbol.split("#", 1)[0]
    if "_" not in cleaned:
        return cleaned, None

    exchange, symbol = cleaned.split("_", 1)
    return symbol or None, exchange or None


def resolve_coinglass_bundle_path() -> Path | None:
    """Find a local Coinglass frontend bundle that contains CryptoJS and pako."""
    env_path = os.environ.get("COINGLASS_APP_BUNDLE")
    if env_path:
        candidate = Path(env_path)
        if candidate.exists():
            return candidate

    tmp_candidates = sorted(
        Path("/tmp").glob("_app-*.js"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for candidate in tmp_candidates:
        try:
            if "capi.coinglass.com" in candidate.read_text(
                encoding="utf-8",
                errors="ignore",
            ):
                return candidate
        except Exception:
            continue

    return None


def decode_coinglass_ciphertext(
    ciphertext: str,
    key: str,
    bundle_path: Path,
) -> tuple[str | None, str | None]:
    """Decode one Coinglass ciphertext string via the bundled frontend crypto path."""
    if not COINGLASS_DECODER_SCRIPT.exists():
        return None, f"Decoder helper missing: {COINGLASS_DECODER_SCRIPT}"

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            prefix="coinglass-ciphertext-",
            suffix=".txt",
        ) as handle:
            handle.write(ciphertext)
            temp_path = Path(handle.name)

        result = subprocess.run(
            [
                "node",
                str(COINGLASS_DECODER_SCRIPT),
                "--bundle",
                str(bundle_path),
                "--ciphertext-file",
                str(temp_path),
                "--key",
                key,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None, "node is not installed"
    except Exception as exc:
        return None, str(exc)
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass

    if result.returncode != 0:
        stderr = result.stderr.strip()
        return None, stderr or "decoder failed"
    return result.stdout, None


def derive_coinglass_seed_key(capture: CaptureFile) -> tuple[str | None, str]:
    """Derive the first-stage Coinglass key from captured headers when available."""
    version = capture.response_headers.get("v")
    if not version:
        return None, "Missing Coinglass response header `v`; only envelope metadata is available."

    if version == "0":
        seed_source = capture.request_headers.get("cache-ts-v2")
        if not seed_source:
            return None, "Coinglass `v=0` requires request header `cache-ts-v2`, but it was not captured."
    elif version == "2":
        seed_source = capture.response_headers.get("time")
        if not seed_source:
            return None, "Coinglass `v=2` requires response header `time`, but it was not captured."
    elif version in COINGLASS_STATIC_SEED_SOURCES:
        seed_source = COINGLASS_STATIC_SEED_SOURCES[version]
    else:
        seed_source = urlparse(capture.source_url).path
        if not seed_source:
            return None, "Coinglass path-based seed derivation failed."

    derived = base64.b64encode(seed_source.encode("utf-8")).decode("ascii")[:16]
    return derived, f"Derived seed key from Coinglass version-aware flow (v={version})."


def decode_coinglass_json_payload(
    capture: CaptureFile,
) -> tuple[Any | None, list[str]]:
    """Decode a Coinglass encrypted payload into JSON when headers are available."""
    root = capture.payload
    if not isinstance(root, dict):
        return None, ["Coinglass capture payload root is not a JSON object."]

    encoded = root.get("data")
    if not isinstance(encoded, str) or not encoded:
        return None, ["Coinglass capture does not expose an encoded string in `data`."]

    bundle_path = resolve_coinglass_bundle_path()
    notes: list[str] = []

    if capture.response_headers.get("user") and bundle_path is not None:
        seed_key, seed_note = derive_coinglass_seed_key(capture)
        notes.append(seed_note)
        if seed_key is None:
            return None, notes

        payload_key, key_error = decode_coinglass_ciphertext(
            ciphertext=capture.response_headers["user"],
            key=seed_key,
            bundle_path=bundle_path,
        )
        if payload_key is None:
            notes.append(f"User-key decode failed: {key_error}")
            return None, notes

        decoded_text, decoded_error = decode_coinglass_ciphertext(
            ciphertext=encoded,
            key=payload_key.strip(),
            bundle_path=bundle_path,
        )
        if decoded_text is None:
            notes.append(f"Payload decode failed: {decoded_error}")
            return None, notes

        try:
            decoded_payload = json.loads(decoded_text)
        except Exception as exc:
            notes.append(f"Decoded text was not JSON: {exc}")
            return None, notes

        notes.insert(
            0,
            (
                "Decoded from Coinglass encrypted payload using captured response headers "
                "plus bundled frontend CryptoJS/pako."
            ),
        )
        return decoded_payload, notes

    if capture.response_headers.get("user") and bundle_path is None:
        notes.append(
            "Coinglass response headers include `user`, but no local `_app-*.js` bundle was "
            "found to load the site decoder. Set COINGLASS_APP_BUNDLE or keep the bundle in /tmp."
        )
    elif bundle_path is not None:
        notes.append(
            "A local Coinglass bundle is available, but this capture has no `user` response "
            "header, so the two-stage decrypt key cannot be derived."
        )
    else:
        notes.append(
            "No Coinglass response headers or local bundle are available for numeric decode."
        )

    return None, notes


def extract_coinglass_price_hint(capture: CaptureFile) -> tuple[float | None, str | None, int]:
    """Extract a current-price hint from Coinglass ticker/kline endpoints."""
    lowered_url = capture.source_url.lower()
    if "coinglass.com" not in lowered_url:
        return None, None, 0
    if "/api/ticker" not in lowered_url and "/api/v2/kline" not in lowered_url:
        return None, None, 0

    decoded_payload, _ = decode_coinglass_json_payload(capture)
    if decoded_payload is None:
        return None, None, 0

    if "/api/ticker" in lowered_url and isinstance(decoded_payload, dict):
        price = safe_float(decoded_payload.get("price"))
        if price is not None:
            return price, "Coinglass /api/ticker price", 100

    if "/api/v2/kline" in lowered_url and isinstance(decoded_payload, list) and decoded_payload:
        last_row = decoded_payload[-1]
        if isinstance(last_row, list) and len(last_row) >= 5:
            price = safe_float(last_row[4])
            if price is not None:
                return price, "Coinglass /api/v2/kline close", 90

    return None, None, 0


def build_provider_hints(captures: list[CaptureFile]) -> dict[str, ProviderHints]:
    """Derive auxiliary provider hints from the full capture set."""
    hints_by_provider: dict[str, ProviderHints] = {}
    score_by_provider: dict[str, int] = {}

    for capture in captures:
        price, note, score = extract_coinglass_price_hint(capture)
        if price is None or score <= 0:
            continue

        provider = capture.provider
        existing_score = score_by_provider.get(provider, -1)
        if score < existing_score:
            continue

        score_by_provider[provider] = score
        hints_by_provider[provider] = ProviderHints(
            current_price=price,
            current_price_source_url=capture.source_url,
            current_price_note=note,
        )

    return hints_by_provider


def try_parse_coinglass_decoded_payload(
    capture: CaptureFile,
    payload: Any,
    decode_note: str,
) -> NormalizedDataset | None:
    """Reuse generic parsers once an encrypted Coinglass payload is decrypted into JSON."""
    specialized = parse_coinglass_decoded_payload(capture, payload, decode_note)
    if specialized is not None:
        return specialized

    decoded_capture = CaptureFile(
        provider=capture.provider,
        source_url=capture.source_url,
        saved_file=capture.saved_file,
        content_type="application/json",
        payload=payload,
        manifest_path=capture.manifest_path,
        response_headers=capture.response_headers,
        request_headers=capture.request_headers,
    )

    for parser in (parse_record_series, parse_parallel_price_arrays):
        parsed = parser(decoded_capture)
        if parsed is None:
            continue
        parsed.notes.insert(0, decode_note)
        parsed.parse_score = max(parsed.parse_score, 92)
        return parsed

    return None


def parse_coinglass_decoded_payload(
    capture: CaptureFile,
    payload: Any,
    decode_note: str,
) -> NormalizedDataset | None:
    """Parse known decoded Coinglass payload shapes into numeric summaries."""
    lowered_url = capture.source_url.lower()
    params = parse_query_params(capture.source_url)

    if (
        "/api/index/v5/liqmap" in lowered_url
        or "/api/index/5/liqmap" in lowered_url
    ) and isinstance(payload, dict):
        instrument = payload.get("instrument")
        current_price = safe_float(payload.get("lastPrice"))
        liq_map_v2 = payload.get("liqMapV2")

        if isinstance(liq_map_v2, dict) and liq_map_v2:
            price_totals: dict[float, float] = {}
            cluster_count = 0

            for raw_bucket_price, raw_rows in liq_map_v2.items():
                bucket_price = safe_float(raw_bucket_price)
                if bucket_price is None or not isinstance(raw_rows, list):
                    continue

                bucket_total = 0.0
                for row in raw_rows:
                    if not isinstance(row, list) or len(row) < 2:
                        continue
                    cluster_value = safe_float(row[1]) or 0.0
                    if cluster_value <= 0:
                        continue
                    bucket_total += cluster_value
                    cluster_count += 1

                if bucket_total > 0:
                    price_totals[bucket_price] = bucket_total

            if price_totals:
                symbol, exchange = normalize_coinglass_symbol(params.get("symbol"))
                if isinstance(instrument, dict):
                    symbol = (
                        instrument.get("instrumentId")
                        or instrument.get("baseAsset")
                        or symbol
                    )
                    exchange = instrument.get("exName") or exchange

                split_note: str
                if current_price is None:
                    observed_prices = sorted(price_totals)
                    current_price = (observed_prices[0] + observed_prices[-1]) / 2
                    split_note = (
                        "No lastPrice was present in the decoded payload; below/above-price "
                        "totals were split around the midpoint of the visible price range."
                    )
                else:
                    split_note = (
                        f"Below/above-price totals were split around decoded lastPrice "
                        f"{current_price:.4f}."
                    )

                below_price_values = [
                    value for price, value in price_totals.items() if price <= current_price
                ]
                above_price_values = [
                    value for price, value in price_totals.items() if price > current_price
                ]

                interval = params.get("interval")
                limit = params.get("limit")
                timeframe = None
                if interval and limit:
                    liqmap_window_labels = {
                        ("1", "1500"): "1 day",
                        ("5", "2000"): "7 day",
                    }
                    timeframe = liqmap_window_labels.get((interval, limit), f"{interval}_x{limit}")
                elif interval:
                    timeframe = interval

                notes = [
                    decode_note,
                    "Coinglass pro /api/index/v5/liqMap returns a price-bucket liquidation map under `liqMapV2`.",
                    "Each `liqMapV2[price]` entry is a list of clusters shaped like [price, value, leverage, heat_band].",
                    (
                        f"This normalization sums cluster values inside each top-level bucket; "
                        f"{len(price_totals)} active buckets and {cluster_count} clusters were present."
                    ),
                    split_note,
                    "Values are treated as USD-notional based on endpoint semantics and magnitude.",
                ]

                return NormalizedDataset(
                    provider=capture.provider,
                    source_url=capture.source_url,
                    saved_file=str(capture.saved_file),
                    dataset_kind="liquidation_heatmap",
                    structure="price_bins",
                    unit="usd_notional",
                    product="liq-map",
                    symbol=symbol,
                    exchange=exchange,
                    timeframe=timeframe,
                    bucket_count=len(price_totals),
                    total_long=sum(below_price_values),
                    total_short=sum(above_price_values),
                    peak_long=max(below_price_values, default=0.0),
                    peak_short=max(above_price_values, default=0.0),
                    current_price=current_price,
                    price_step_median=median_step(list(price_totals)),
                    time_step_median_ms=None,
                    notes=notes,
                    parse_score=103,
                )

    if "/api/index/v5/liqheatmap" in lowered_url and isinstance(payload, dict):
        instrument = payload.get("instrument")
        price_rows = payload.get("prices")
        y_axis = payload.get("y")
        liq_rows = payload.get("liq")

        if (
            isinstance(price_rows, list)
            and isinstance(y_axis, list)
            and isinstance(liq_rows, list)
            and price_rows
            and y_axis
            and liq_rows
        ):
            latest_x_index: int | None = None
            for row in liq_rows:
                if not isinstance(row, list) or len(row) < 3:
                    continue
                x_idx = safe_float(row[0])
                if x_idx is None or not x_idx.is_integer():
                    continue
                candidate = int(x_idx)
                if latest_x_index is None or candidate > latest_x_index:
                    latest_x_index = candidate

            if latest_x_index is not None:
                timestamps: list[float] = []
                current_price = None
                for row in price_rows:
                    if not isinstance(row, list) or len(row) < 5:
                        continue
                    timestamp = safe_float(row[0])
                    if timestamp is not None:
                        timestamps.append(timestamp)
                    close_price = safe_float(row[4])
                    if close_price is not None:
                        current_price = close_price

                price_totals: dict[float, float] = {}
                active_cells = 0
                for row in liq_rows:
                    if not isinstance(row, list) or len(row) < 3:
                        continue
                    x_idx = safe_float(row[0])
                    y_idx = safe_float(row[1])
                    value = safe_float(row[2]) or 0.0
                    if (
                        x_idx is None
                        or y_idx is None
                        or not x_idx.is_integer()
                        or not y_idx.is_integer()
                        or int(x_idx) != latest_x_index
                        or value <= 0
                    ):
                        continue

                    y_position = int(y_idx)
                    if y_position < 0 or y_position >= len(y_axis):
                        continue

                    price = safe_float(y_axis[y_position])
                    if price is None:
                        continue

                    price_totals[price] = price_totals.get(price, 0.0) + value
                    active_cells += 1

                if price_totals:
                    symbol, exchange = normalize_coinglass_symbol(params.get("symbol"))
                    if isinstance(instrument, dict):
                        symbol = (
                            instrument.get("instrumentId")
                            or instrument.get("baseAsset")
                            or symbol
                        )
                        exchange = instrument.get("exName") or exchange

                    split_note: str
                    if current_price is None:
                        observed_prices = sorted(price_totals)
                        current_price = (observed_prices[0] + observed_prices[-1]) / 2
                        split_note = (
                            "No close price was available from the companion price rows; "
                            "below/above-price totals were split around the midpoint of "
                            "the visible price range."
                        )
                    else:
                        split_note = (
                            f"Below/above-price totals were split around the latest visible "
                            f"close price {current_price:.4f}."
                        )

                    below_price_values = [
                        value for price, value in price_totals.items() if price <= current_price
                    ]
                    above_price_values = [
                        value for price, value in price_totals.items() if price > current_price
                    ]

                    interval = params.get("interval")
                    limit = params.get("limit")
                    timeframe = None
                    if interval and limit:
                        timeframe = f"{interval}m_x{limit}"
                    elif interval:
                        timeframe = interval

                    notes = [
                        decode_note,
                        "Coinglass pro /api/index/v5/liqHeatMap returns a sparse liquidation grid as [x_index, y_index, value].",
                        "This normalization uses the latest visible x-column only, which best approximates the current heatmap state.",
                        (
                            f"Visible grid in this capture: {len(price_rows)} time columns x "
                            f"{len(y_axis)} price rows; latest x index {latest_x_index} "
                            f"contributed {active_cells} active cells."
                        ),
                        split_note,
                        "Values are treated as USD-notional based on endpoint semantics and magnitude.",
                    ]

                    return NormalizedDataset(
                        provider=capture.provider,
                        source_url=capture.source_url,
                        saved_file=str(capture.saved_file),
                        dataset_kind="liquidation_heatmap",
                        structure="price_bins",
                        unit="usd_notional",
                        product="liq-heat-map",
                        symbol=symbol,
                        exchange=exchange,
                        timeframe=timeframe,
                        bucket_count=len(price_totals),
                        total_long=sum(below_price_values),
                        total_short=sum(above_price_values),
                        peak_long=max(below_price_values, default=0.0),
                        peak_short=max(above_price_values, default=0.0),
                        current_price=current_price,
                        price_step_median=median_step(list(price_totals)),
                        time_step_median_ms=(
                            median_step(timestamps) * 1000 if timestamps else None
                        ),
                        notes=notes,
                        parse_score=101,
                    )

    if "/api/futures/liquidation/chart" in lowered_url and isinstance(payload, list):
        long_values: list[float] = []
        short_values: list[float] = []
        timestamps: list[float] = []

        for row in payload:
            if not isinstance(row, dict):
                continue
            short_value = safe_float(row.get("buyVolUsd")) or 0.0
            long_value = safe_float(row.get("sellVolUsd")) or 0.0
            long_values.append(long_value)
            short_values.append(short_value)
            timestamp = safe_float(row.get("createTime"))
            if timestamp is not None:
                timestamps.append(timestamp)

        if long_values or short_values:
            return NormalizedDataset(
                provider=capture.provider,
                source_url=capture.source_url,
                saved_file=str(capture.saved_file),
                dataset_kind="liquidations_timeseries",
                structure="time_candles",
                unit="usd_notional",
                product="liquidations-chart",
                symbol=params.get("symbol") or None,
                exchange=params.get("exName") or "All",
                timeframe=params.get("range") or params.get("timeType"),
                bucket_count=len(long_values),
                total_long=sum(long_values),
                total_short=sum(short_values),
                peak_long=max(long_values, default=0.0),
                peak_short=max(short_values, default=0.0),
                current_price=None,
                price_step_median=None,
                time_step_median_ms=median_step(timestamps),
                notes=[
                    decode_note,
                    "Coinglass futures/liquidation/chart uses sellVolUsd for long liquidations and buyVolUsd for short liquidations.",
                ],
                parse_score=97,
            )

    if "/api/coin/liquidation" in lowered_url and isinstance(payload, dict):
        long_values: list[float] = []
        short_values: list[float] = []
        for row in payload.values():
            if not isinstance(row, dict):
                continue
            long_values.append(safe_float(row.get("longVolUsd")) or 0.0)
            short_values.append(safe_float(row.get("shortVolUsd")) or 0.0)

        if long_values or short_values:
            return NormalizedDataset(
                provider=capture.provider,
                source_url=capture.source_url,
                saved_file=str(capture.saved_file),
                dataset_kind="liquidation_summary",
                structure="time_buckets_summary",
                unit="usd_notional",
                product="liquidation-summary",
                symbol=None,
                exchange="All",
                timeframe="multi_window",
                bucket_count=len(long_values),
                total_long=sum(long_values),
                total_short=sum(short_values),
                peak_long=max(long_values, default=0.0),
                peak_short=max(short_values, default=0.0),
                current_price=None,
                price_step_median=None,
                time_step_median_ms=None,
                notes=[
                    decode_note,
                    "Coinglass coin/liquidation returns aggregate windows such as h1/h4/h12/h24.",
                ],
                parse_score=88,
            )

    if "/api/coin/liq/heatmap" in lowered_url and isinstance(payload, list):
        long_values: list[float] = []
        short_values: list[float] = []
        top_symbol = None

        for idx, row in enumerate(payload):
            if not isinstance(row, dict):
                continue
            if idx == 0:
                top_symbol = row.get("symbol")
            long_values.append(safe_float(row.get("longVolUsd")) or 0.0)
            short_values.append(safe_float(row.get("shortVolUsd")) or 0.0)

        if long_values or short_values:
            notes = [
                decode_note,
                "Coinglass coin/liq/heatmap on LiquidationData is a cross-asset leaderboard, not a single-symbol price-bin heatmap.",
            ]
            if top_symbol:
                notes.append(f"Top symbol in this snapshot: {top_symbol}")

            return NormalizedDataset(
                provider=capture.provider,
                source_url=capture.source_url,
                saved_file=str(capture.saved_file),
                dataset_kind="liquidation_leaderboard",
                structure="asset_rows",
                unit="usd_notional",
                product="liq-heat-map",
                symbol=params.get("symbol") or None,
                exchange="All",
                timeframe=params.get("time"),
                bucket_count=len(long_values),
                total_long=sum(long_values),
                total_short=sum(short_values),
                peak_long=max(long_values, default=0.0),
                peak_short=max(short_values, default=0.0),
                current_price=None,
                price_step_median=None,
                time_step_median_ms=None,
                notes=notes,
                parse_score=84,
            )

    return None


def parse_coinglass_liquidity_heatmap(
    capture: CaptureFile,
    hints: ProviderHints | None = None,
) -> NormalizedDataset | None:
    """Parse Coinglass's public /LiquidityHeatmap 2D liquidity grid."""
    lowered_url = capture.source_url.lower()
    if "/liquidity-heatmap/api/liquidity/v4/heatmap" not in lowered_url:
        return None

    root = capture.payload
    if not isinstance(root, dict):
        return None

    data = root.get("data")
    if not isinstance(data, dict):
        return None

    grid = data.get("data")
    if not isinstance(grid, list) or not grid:
        return None

    price_totals: dict[float, float] = {}
    timestamps_seconds: list[float] = []
    point_count = 0

    for row in grid:
        if not isinstance(row, list) or len(row) < 2:
            continue

        timestamp = safe_float(row[0])
        if timestamp is not None:
            timestamps_seconds.append(timestamp)

        points = row[1]
        if not isinstance(points, list):
            continue

        for point in points:
            if not isinstance(point, list) or len(point) < 2:
                continue
            price = safe_float(point[0])
            value = safe_float(point[1]) or 0.0
            if price is None or value <= 0:
                continue
            price_totals[price] = price_totals.get(price, 0.0) + value
            point_count += 1

    if not price_totals:
        return None

    params = parse_query_params(capture.source_url)
    symbol, exchange = normalize_coinglass_symbol(params.get("symbol"))
    if exchange is None:
        exchange = params.get("exName")

    current_price = hints.current_price if hints is not None else None
    split_note: str
    if current_price is None:
        observed_prices = sorted(price_totals)
        current_price = (observed_prices[0] + observed_prices[-1]) / 2
        split_note = (
            "No companion ticker/kline price was available; below/above-price totals were "
            "split around the midpoint of the observed price range."
        )
    else:
        source_label = (
            hints.current_price_note or "a companion Coinglass ticker/kline capture"
        )
        split_note = (
            f"Below/above-price totals were split around current price {current_price:.4f} "
            f"from {source_label}."
        )

    below_price_values = [
        value for price, value in price_totals.items() if price <= current_price
    ]
    above_price_values = [
        value for price, value in price_totals.items() if price > current_price
    ]

    time_step_seconds = median_step(timestamps_seconds)
    notes = [
        "Coinglass /LiquidityHeatmap returns a 2D [timestamp, [[price, intensity], ...]] liquidity grid.",
        "This is a liquidity heatmap, not a liquidation heatmap; it should not be compared 1:1 with liquidation maps.",
        "Values were collapsed across time into one aggregate per price bin for cross-provider shape comparison.",
        split_note,
    ]
    if hints is not None and hints.current_price_source_url:
        notes.append(f"Current-price hint source: {hints.current_price_source_url}")
    if data.get("size") is not None:
        notes.append(f"Provider heatmap size metadata: {data.get('size')}")
    if safe_float(data.get("max")) is not None:
        notes.append(f"Provider max cell intensity: {safe_float(data.get('max')):.3f}")

    base_score = 92
    if "startTime" in params:
        base_score += 1

    return NormalizedDataset(
        provider=capture.provider,
        source_url=capture.source_url,
        saved_file=str(capture.saved_file),
        dataset_kind="liquidity_heatmap",
        structure="time_price_grid",
        unit="relative_density",
        product="liquidity-heatmap",
        symbol=symbol,
        exchange=exchange,
        timeframe=params.get("interval"),
        bucket_count=len(price_totals),
        total_long=sum(below_price_values),
        total_short=sum(above_price_values),
        peak_long=max(below_price_values, default=0.0),
        peak_short=max(above_price_values, default=0.0),
        current_price=current_price,
        price_step_median=median_step(list(price_totals)),
        time_step_median_ms=(time_step_seconds * 1000) if time_step_seconds is not None else None,
        notes=notes,
        parse_score=base_score,
    )


def parse_rektslug_levels(capture: CaptureFile) -> NormalizedDataset | None:
    """Parse the local rektslug /liquidations/levels payload.

    Expected shape:
        {
            "symbol": "BTCUSDT",
            "model": "openinterest",
            "current_price": "85000.0",
            "long_liquidations": [{"price_level": "80000", "volume": "1234.5", ...}],
            "short_liquidations": [{"price_level": "90000", "volume": "5678.9", ...}]
        }
    """
    if capture.provider != "rektslug":
        return None

    lowered_url = capture.source_url.lower()
    if "/liquidations/levels" not in lowered_url:
        return None

    root = capture.payload
    if not isinstance(root, dict):
        return None

    long_liqs = root.get("long_liquidations")
    short_liqs = root.get("short_liquidations")
    if not isinstance(long_liqs, list) or not isinstance(short_liqs, list):
        return None

    current_price = safe_float(root.get("current_price"))
    symbol = root.get("symbol")

    long_values: list[float] = []
    short_values: list[float] = []
    all_prices: list[float] = []

    for entry in long_liqs:
        if not isinstance(entry, dict):
            continue
        price = safe_float(entry.get("price_level"))
        volume = safe_float(entry.get("volume")) or 0.0
        if price is not None:
            all_prices.append(price)
        if volume > 0:
            long_values.append(volume)

    for entry in short_liqs:
        if not isinstance(entry, dict):
            continue
        price = safe_float(entry.get("price_level"))
        volume = safe_float(entry.get("volume")) or 0.0
        if price is not None:
            all_prices.append(price)
        if volume > 0:
            short_values.append(volume)

    bucket_count = len(long_values) + len(short_values)
    if bucket_count == 0:
        return None

    # Derive timeframe from URL query param.
    params = parse_query_params(capture.source_url)
    raw_tf = params.get("timeframe")
    timeframe = None
    if raw_tf:
        tf_labels = {"1": "1d", "7": "1w"}
        timeframe = tf_labels.get(raw_tf, f"{raw_tf}d")

    return NormalizedDataset(
        provider=capture.provider,
        source_url=capture.source_url,
        saved_file=str(capture.saved_file),
        dataset_kind="liquidation_heatmap",
        structure="price_bins",
        unit="usd_notional",
        product="liq-map",
        symbol=symbol,
        exchange="binance",
        timeframe=timeframe,
        bucket_count=bucket_count,
        total_long=sum(long_values),
        total_short=sum(short_values),
        peak_long=max(long_values, default=0.0),
        peak_short=max(short_values, default=0.0),
        current_price=current_price,
        price_step_median=median_step(all_prices),
        time_step_median_ms=None,
        notes=[
            "Local rektslug /liquidations/levels endpoint (OI-based liquidation model).",
            f"Parsed {len(long_values)} long bins and {len(short_values)} short bins.",
        ],
        parse_score=100,
    )


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
    active_prices: list[float] = []
    long_values: list[float] = []
    short_values: list[float] = []
    active_bins = 0

    for raw_price, raw_value in zip(prices_raw, values_raw):
        price = safe_float(raw_price)
        value = safe_float(raw_value) or 0.0
        if price is None:
            continue
        if value <= 0:
            continue
        active_bins += 1
        active_prices.append(price)
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
        product="liq-map",
        symbol=symbol,
        exchange=exchange_key,
        timeframe=params.get("interval"),
        bucket_count=active_bins,
        total_long=sum(long_values),
        total_short=sum(short_values),
        peak_long=max(long_values, default=0.0),
        peak_short=max(short_values, default=0.0),
        current_price=current_price,
        price_step_median=median_step(active_prices),
        time_step_median_ms=None,
        notes=notes,
        parse_score=95,
    )


def parse_coinank_liq_map(capture: CaptureFile) -> NormalizedDataset | None:
    """Parse CoinAnk's symbol-specific liquidation map with explicit leverage ladders."""
    if "/api/liqMap/getLiqMap" not in capture.source_url:
        return None

    root = capture.payload
    data = root.get("data")
    if not isinstance(data, dict):
        return None

    prices_raw = data.get("prices")
    if not isinstance(prices_raw, list) or not prices_raw:
        return None

    leverage_keys = sorted(
        [
            key
            for key, value in data.items()
            if re.fullmatch(r"x\d+", key) and isinstance(value, list) and len(value) == len(prices_raw)
        ],
        key=lambda key: int(key[1:]),
    )
    if not leverage_keys:
        return None

    current_price = safe_float(data.get("lastPrice"))
    last_index_raw = data.get("lastIndex")
    last_index = None
    if isinstance(last_index_raw, (int, float)):
        numeric_last_index = float(last_index_raw)
        if math.isfinite(numeric_last_index) and numeric_last_index.is_integer():
            last_index = int(numeric_last_index)

    active_prices: list[float] = []
    long_values: list[float] = []
    short_values: list[float] = []
    active_bins = 0

    for idx, raw_price in enumerate(prices_raw):
        price = safe_float(raw_price)
        if price is None:
            continue

        value = 0.0
        for leverage_key in leverage_keys:
            value += safe_float(data[leverage_key][idx]) or 0.0

        if value <= 0:
            continue
        active_bins += 1
        active_prices.append(price)

        if last_index is not None:
            if idx <= last_index:
                long_values.append(value)
            else:
                short_values.append(value)
        elif current_price is not None and price <= current_price:
            long_values.append(value)
        elif current_price is not None and price > current_price:
            short_values.append(value)
        else:
            long_values.append(value)

    params = parse_query_params(capture.source_url)
    notes = [
        (
            "CoinAnk getLiqMap returns a symbol-specific price grid plus leverage ladders "
            f"({', '.join(leverage_keys)})."
        ),
        "The public payload starts at x25 and omits x5/x10, so low-leverage tiers are not part of this series.",
    ]
    if last_index is not None:
        notes.append("Long and short totals are split using CoinAnk's `lastIndex` pivot.")
    else:
        notes.append("Long and short totals are inferred by splitting bins around `lastPrice`.")

    return NormalizedDataset(
        provider=capture.provider,
        source_url=capture.source_url,
        saved_file=str(capture.saved_file),
        dataset_kind="liquidation_heatmap",
        structure="price_bins",
        unit="usd_notional",
        product="liq-map",
        symbol=data.get("symbol") or params.get("symbol"),
        exchange=params.get("exchange"),
        timeframe=params.get("interval"),
        bucket_count=active_bins,
        total_long=sum(long_values),
        total_short=sum(short_values),
        peak_long=max(long_values, default=0.0),
        peak_short=max(short_values, default=0.0),
        current_price=current_price,
        price_step_median=median_step(active_prices),
        time_step_median_ms=None,
        notes=notes,
        parse_score=98,
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
        product="liquidations-timeseries",
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
    """Parse Coinglass liquidation endpoints, decoding them when headers make it possible."""
    lowered_url = capture.source_url.lower()
    if "coinglass.com" not in lowered_url:
        return None
    if not re.search(r"liq|liquidat|heatmap", lowered_url):
        return None

    root = capture.payload
    encoded = root.get("data")
    if not isinstance(encoded, str) or not encoded:
        return None

    decoded_payload, decode_notes = decode_coinglass_json_payload(capture)
    if decoded_payload is not None:
        decode_note = decode_notes[0] if decode_notes else "Decoded Coinglass payload."
        parsed = try_parse_coinglass_decoded_payload(
            capture=capture,
            payload=decoded_payload,
            decode_note=decode_note,
        )
        if parsed is not None:
            if len(decode_notes) > 1:
                parsed.notes[1:1] = decode_notes[1:]
            return parsed
        decode_notes.append(
            "Decoded Coinglass JSON was captured, but it did not match a known "
            "numeric liquidation schema yet."
        )

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
        "Coinglass returned an encoded string in `data`; numeric decode was not completed for this capture.",
        f"Encoded chars: {len(encoded)}",
    ]
    if decoded_size is not None:
        notes.append(f"Base64-decoded bytes: {decoded_size}")
    if capture.response_headers:
        notes.append(
            "Captured Coinglass response header keys: "
            + ", ".join(sorted(capture.response_headers))
        )
    notes.extend(decode_notes)

    return NormalizedDataset(
        provider=capture.provider,
        source_url=capture.source_url,
        saved_file=str(capture.saved_file),
        dataset_kind=dataset_kind,
        structure="encrypted_base64",
        unit="encrypted_payload",
        product=infer_product_from_source_url(capture.source_url),
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
        product=infer_product_from_source_url(capture.source_url),
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
        product=infer_product_from_source_url(capture.source_url),
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


def parse_capture(
    capture: CaptureFile,
    hints: ProviderHints | None = None,
) -> NormalizedDataset | None:
    """Try all known parsers in priority order."""
    parser_chain = (
        lambda current: parse_rektslug_levels(current),
        lambda current: parse_coinank_liq_map(current),
        lambda current: parse_coinank_agg_liq_map(current),
        lambda current: parse_bitcoincounterflow_liquidations(current),
        lambda current: parse_coinglass_liquidity_heatmap(current, hints),
        lambda current: parse_coinglass_encrypted_liquidations(current),
        lambda current: parse_record_series(current),
        lambda current: parse_parallel_price_arrays(current),
    )

    for parser in parser_chain:
        parsed = parser(capture)
        if parsed is not None:
            return parsed
    return None


def _dataset_matches_product(dataset: "NormalizedDataset", product_filter: str | None) -> bool:
    """Return True if the dataset matches the requested product."""
    if not product_filter:
        return True
    return dataset.product == product_filter


def choose_best_datasets(
    captures: list[CaptureFile],
    product_filter: str | None = None,
) -> tuple[dict[str, NormalizedDataset], dict[str, list[str]]]:
    """Pick the strongest normalized dataset per provider."""
    best_by_provider: dict[str, NormalizedDataset] = {}
    skipped_by_provider: dict[str, list[str]] = {}
    hints_by_provider = build_provider_hints(captures)

    for capture in captures:
        parsed = parse_capture(capture, hints_by_provider.get(capture.provider))
        if parsed is None:
            if re.search(r"liq|liquidat|heatmap", capture.source_url, re.IGNORECASE):
                skipped_by_provider.setdefault(capture.provider, []).append(capture.source_url)
            continue

        if not _dataset_matches_product(parsed, product_filter):
            skipped_by_provider.setdefault(parsed.provider, []).append(capture.source_url)
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


def canonicalize_timeframe(value: str | None) -> str | None:
    """Normalize common timeframe aliases before pairwise comparison."""
    if not value:
        return None

    lowered = value.strip().lower()
    alias_map = {
        "1d": "1d",
        "1 day": "1d",
        "24h": "1d",
        "7d": "1w",
        "1w": "1w",
        "7 day": "1w",
        "1m": "1m",
        "30d": "1m",
        "30 day": "1m",
        "1 month": "1m",
        "3m": "3m",
        "90d": "3m",
        "90 day": "3m",
        "6m": "6m",
        "180d": "6m",
        "180 day": "6m",
    }
    return alias_map.get(lowered, lowered)


def compare_pair(left: NormalizedDataset, right: NormalizedDataset) -> dict[str, Any]:
    """Compare two normalized datasets."""
    left_timeframe = canonicalize_timeframe(left.timeframe)
    right_timeframe = canonicalize_timeframe(right.timeframe)
    return {
        "providers": [left.provider, right.provider],
        "dataset_kind_match": left.dataset_kind == right.dataset_kind,
        "structure_match": left.structure == right.structure,
        "unit_match": left.unit == right.unit,
        "symbol_match": (left.symbol or "").upper() == (right.symbol or "").upper(),
        "timeframe_match": left_timeframe == right_timeframe,
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
        "provider_profiles": {
            provider: get_provider_profile(provider).to_public_dict()
            for provider in sorted(datasets)
        },
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
            "CoinAnk getAggLiqMap is parsed explicitly, but long/short are still inferred by splitting around lastPrice.",
            "Coinglass will decode encrypted payloads only when the capture includes the required response headers and a local `_app-*.js` bundle is available.",
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
    product_filter: str | None = None,
    profile: str | None = None,
) -> tuple[dict[str, Any], Path]:
    """Generate the comparison report and optionally persist it to DuckDB."""
    captures = load_capture_files(manifest_paths)
    datasets, skipped_by_provider = choose_best_datasets(captures, product_filter=product_filter)

    if not datasets:
        raise RuntimeError("No parseable liquidation datasets found in the supplied manifests.")

    report = build_report(manifest_paths, datasets, skipped_by_provider)
    # Inject profile metadata (spec-018: FR-007)
    if profile:
        report["profile"] = profile
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
