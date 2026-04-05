"""Hyperliquid Expert Snapshot Producer orchestration script."""

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from src.liquidationheatmap.api.routers import liquidations
from src.liquidationheatmap.hyperliquid.builder_integration import (
    map_builder_payload_to_artifact,
    normalize_to_canonical_grid,
)
from src.liquidationheatmap.hyperliquid.export_layout import (
    build_manifest,
    write_expert_artifact,
    write_manifest,
)
from src.liquidationheatmap.hyperliquid.run_metadata import RunKind, build_run_metadata
from src.liquidationheatmap.hyperliquid.snapshot_schema import (
    BucketGrid,
    validate_iso8601_z_timestamp,
)

DEFAULT_OUTPUT_DIR = Path("data/validation/expert_snapshots/hyperliquid")
DEFAULT_CACHE_DIR = Path("data/cache")
DEFAULT_RAW_PROVIDER_ROOT = Path("data/validation/raw_provider_api")
DEFAULT_SYMBOL = "BTCUSDT"


def get_current_utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sidecar_cache_filename(expert_id: str, symbol: str) -> str:
    normalized_symbol = symbol.lower()
    if expert_id == "v1":
        return f"hl_sidecar_{normalized_symbol}.json"
    return f"hl_sidecar_{expert_id}_{normalized_symbol}.json"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json_payload(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _bucket_distribution(buckets: list[dict[str, Any]]) -> dict[str, float]:
    distribution: dict[str, float] = {}
    for bucket in buckets:
        price_level = str(float(bucket["price_level"]))
        distribution[price_level] = distribution.get(price_level, 0.0) + float(bucket["volume"])
    return distribution


def _base_canonical_grid(cache_payload: dict[str, Any]) -> BucketGrid:
    grid = cache_payload["grid"]
    return BucketGrid(
        min_price=float(grid["min_price"]),
        max_price=float(grid["max_price"]),
        step=float(grid["step"]),
    )


def _build_artifact_from_sidecar_payload(
    *,
    expert_id: str,
    snapshot_ts: str,
    symbol: str,
    cache_payload: dict[str, Any],
    canonical_grid: BucketGrid,
    run_meta: Any,
    input_identity: dict[str, Any],
) -> Any:
    builder_payload = {
        "symbol": symbol,
        "snapshot_ts": snapshot_ts,
        "reference_price": float(
            cache_payload.get("mark_price", cache_payload.get("current_price", 0.0))
        ),
        "bucket_grid": {
            "min_price": canonical_grid.min_price,
            "max_price": canonical_grid.max_price,
            "step": canonical_grid.step,
        },
        "long_distribution": normalize_to_canonical_grid(
            _bucket_distribution(cache_payload.get("long_buckets", [])),
            canonical_grid,
        ),
        "short_distribution": normalize_to_canonical_grid(
            _bucket_distribution(cache_payload.get("short_buckets", [])),
            canonical_grid,
        ),
        "source_metadata": {
            "builder_family": str(cache_payload.get("source", "unknown_builder")),
            "source_timestamp": str(cache_payload.get("generated_at", "")),
            "source_anchor": str(cache_payload.get("source_anchor", "")),
            "projection": cache_payload.get("projection"),
            "distribution_normalization": "normalized",
            "input_identity": input_identity,
        },
        "generation_metadata": asdict(run_meta),
    }
    return map_builder_payload_to_artifact(expert_id, builder_payload)


def _load_cache_artifact(
    *,
    expert_id: str,
    cache_path: Path,
    snapshot_ts: str,
    symbol: str,
    canonical_grid: BucketGrid,
    run_meta: Any,
) -> Any:
    cache_payload = _load_json_payload(cache_path)
    input_identity = {
        "source_kind": "sidecar_cache",
        "cache_variant": expert_id,
        "content_sha256": _sha256_file(cache_path),
        "source_timestamp": str(cache_payload.get("generated_at", "")),
    }
    return _build_artifact_from_sidecar_payload(
        expert_id=expert_id,
        snapshot_ts=snapshot_ts,
        symbol=symbol,
        cache_payload=cache_payload,
        canonical_grid=canonical_grid,
        run_meta=run_meta,
        input_identity=input_identity,
    )


def _load_v2_control_artifact(
    *,
    snapshot_ts: str,
    symbol: str,
    base_cache_payload: dict[str, Any],
    canonical_grid: BucketGrid,
    raw_provider_root: Path,
    run_meta: Any,
) -> Any:
    original_capture_root = liquidations._CG_CAPTURE_ROOT
    try:
        liquidations._CG_CAPTURE_ROOT = raw_provider_root
        coinglass_payload = liquidations._build_coinglass_top_position_response(
            symbol=symbol,
            timeframe="1w",
            base_cache=base_cache_payload,
        )
    finally:
        liquidations._CG_CAPTURE_ROOT = original_capture_root

    input_identity = {
        "source_kind": "coinglass_capture",
        "capture_root": str(coinglass_payload.get("source_anchor", "")),
        "source_timestamp": str(base_cache_payload.get("generated_at", "")),
    }
    return _build_artifact_from_sidecar_payload(
        expert_id="v2",
        snapshot_ts=snapshot_ts,
        symbol=symbol,
        cache_payload=coinglass_payload,
        canonical_grid=canonical_grid,
        run_meta=run_meta,
        input_identity=input_identity,
    )


def produce_snapshots(
    snapshot_ts: str,
    run_kind: str,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    last_actual_run_ts: str | None = None,
    cache_dir: str | Path = DEFAULT_CACHE_DIR,
    raw_provider_root: str | Path = DEFAULT_RAW_PROVIDER_ROOT,
    symbol: str = DEFAULT_SYMBOL,
) -> Any:
    """Orchestrate builders and write out manifest/artifact layout."""
    snapshot_ts = validate_iso8601_z_timestamp("snapshot_ts", snapshot_ts)
    output_dir = Path(output_dir)
    cache_dir = Path(cache_dir)
    raw_provider_root = Path(raw_provider_root)
    symbol = symbol.upper()

    current_ts = get_current_utc_ts()
    if not last_actual_run_ts:
        last_actual_run_ts = current_ts

    try:
        run_kind_enum = RunKind(run_kind)
    except ValueError:
        print(f"Error: Invalid run-kind '{run_kind}'. Must be one of {[k.value for k in RunKind]}")
        sys.exit(1)

    run_meta = build_run_metadata(
        run_reason=run_kind_enum,
        run_ts=current_ts,
        last_actual_run_ts=last_actual_run_ts,
    )

    base_cache_path = cache_dir / _sidecar_cache_filename("v1", symbol)
    if not base_cache_path.exists():
        raise FileNotFoundError(f"Missing canonical sidecar cache: {base_cache_path}")

    base_cache_payload = _load_json_payload(base_cache_path)
    canonical_grid = _base_canonical_grid(base_cache_payload)

    experts = [
        _load_cache_artifact(
            expert_id="v1",
            cache_path=base_cache_path,
            snapshot_ts=snapshot_ts,
            symbol=symbol,
            canonical_grid=canonical_grid,
            run_meta=run_meta,
        )
    ]
    failures: dict[str, dict[str, Any]] = {}

    try:
        experts.append(
            _load_v2_control_artifact(
                snapshot_ts=snapshot_ts,
                symbol=symbol,
                base_cache_payload=base_cache_payload,
                canonical_grid=canonical_grid,
                raw_provider_root=raw_provider_root,
                run_meta=run_meta,
            )
        )
    except (HTTPException, FileNotFoundError, json.JSONDecodeError) as exc:
        detail = getattr(exc, "detail", str(exc))
        failures["v2"] = {
            "reason": "coinglass_control_unavailable",
            "details": str(detail),
            "source_root": str(raw_provider_root),
        }

    for expert_id in ("v3", "v4", "v5"):
        cache_path = cache_dir / _sidecar_cache_filename(expert_id, symbol)
        if not cache_path.exists():
            continue
        try:
            experts.append(
                _load_cache_artifact(
                    expert_id=expert_id,
                    cache_path=cache_path,
                    snapshot_ts=snapshot_ts,
                    symbol=symbol,
                    canonical_grid=canonical_grid,
                    run_meta=run_meta,
                )
            )
        except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError) as exc:
            failures[expert_id] = {
                "reason": "sidecar_cache_invalid",
                "details": str(exc),
                "source_root": str(cache_dir),
            }

    for expert in experts:
        write_expert_artifact(
            output_dir,
            expert.symbol,
            snapshot_ts,
            expert.expert_id,
            asdict(expert),
        )

    manifest = build_manifest(
        snapshot_ts=snapshot_ts,
        experts=experts,
        failures=failures,
        distribution_normalization="normalized",
    )
    write_manifest(output_dir, symbol, manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Produce Hyperliquid expert snapshots")
    parser.add_argument(
        "--snapshot-ts", required=True, help="Canonical evaluation timestamp (ISO8601 Z)"
    )
    parser.add_argument("--run-kind", required=True, help="baseline, extra, manual, or backfill")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Export root directory",
    )
    parser.add_argument(
        "--cache-dir",
        default=str(DEFAULT_CACHE_DIR),
        help="Directory containing Hyperliquid sidecar cache JSON files",
    )
    parser.add_argument(
        "--raw-provider-root",
        default=str(DEFAULT_RAW_PROVIDER_ROOT),
        help="Root directory containing raw provider captures used for v2 control export",
    )
    parser.add_argument(
        "--symbol",
        default=DEFAULT_SYMBOL,
        help="Symbol to export, default BTCUSDT",
    )

    args = parser.parse_args()

    try:
        produce_snapshots(
            snapshot_ts=args.snapshot_ts,
            run_kind=args.run_kind,
            output_dir=args.output_dir,
            cache_dir=args.cache_dir,
            raw_provider_root=args.raw_provider_root,
            symbol=args.symbol,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
