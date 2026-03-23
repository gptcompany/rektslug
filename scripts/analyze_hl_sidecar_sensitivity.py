#!/usr/bin/env python3
"""Measure ETH/BTC sidecar window sensitivity and sparsity."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import compare_hl_sidecar_vs_coinglass as compare


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="ETH", help="Target symbol, e.g. ETH or BTC")
    parser.add_argument(
        "--short-window",
        type=Path,
        default=Path("data/validation/liqmap_hl_eth_1d.json"),
        help="Short-window sidecar artifact (candidate).",
    )
    parser.add_argument(
        "--baseline-window",
        type=Path,
        default=Path("data/validation/liqmap_hl_eth_7d.json"),
        help="Baseline sidecar artifact to compare against.",
    )
    parser.add_argument(
        "--coinglass-capture-dir",
        type=Path,
        default=Path("data/validation/raw_provider_api/20260320T183040Z"),
        help="Optional CoinGlass capture dir for the short window.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/validation/hl_sidecar_eth_1d_sensitivity.json"),
        help="Output path",
    )
    return parser.parse_args()


def total_buckets(dist: compare.BucketedDistribution) -> dict[float, float]:
    combined: dict[float, float] = {}
    for price, volume in dist.long_buckets.items():
        combined[price] = combined.get(price, 0.0) + volume
    for price, volume in dist.short_buckets.items():
        combined[price] = combined.get(price, 0.0) + volume
    return combined


def rebucket(prices_to_volume: dict[float, float], bin_size: float) -> dict[float, float]:
    rebucketed: dict[float, float] = {}
    for price, volume in prices_to_volume.items():
        rebucketed_price = round(math.floor(price / bin_size + 1e-9) * bin_size, 10)
        rebucketed[rebucketed_price] = rebucketed.get(rebucketed_price, 0.0) + volume
    return rebucketed


def rebin_distribution(dist: compare.BucketedDistribution, bin_size: float) -> compare.BucketedDistribution:
    rebinned = compare.BucketedDistribution(
        source=dist.source,
        symbol=dist.symbol,
        bin_size=bin_size,
        current_price=dist.current_price,
        account_count=dist.account_count,
        position_count=dist.position_count,
    )
    rebinned.long_buckets = rebucket(dist.long_buckets, bin_size)
    rebinned.short_buckets = rebucket(dist.short_buckets, bin_size)
    return rebinned


def concentration_stats(dist: compare.BucketedDistribution) -> dict:
    combined = total_buckets(dist)
    volumes = sorted(combined.values(), reverse=True)
    total_volume = sum(volumes)
    bucket_count = len(combined)
    top_10 = sum(volumes[:10]) if volumes else 0.0
    top_1pct_count = max(1, math.ceil(bucket_count * 0.01)) if bucket_count else 0
    top_1pct = sum(volumes[:top_1pct_count]) if volumes else 0.0
    return {
        "bin_size": dist.bin_size,
        "bucket_count": bucket_count,
        "account_count": dist.account_count,
        "position_count": dist.position_count,
        "total_volume": round(total_volume, 6),
        "accounts_per_bucket": round(dist.account_count / bucket_count, 6) if bucket_count else None,
        "positions_per_bucket": round(dist.position_count / bucket_count, 6) if bucket_count else None,
        "top_10_bucket_share": round(top_10 / total_volume, 6) if total_volume > 0 else None,
        "top_1pct_bucket_share": round(top_1pct / total_volume, 6) if total_volume > 0 else None,
    }


def bucket_overlap(a: compare.BucketedDistribution, b: compare.BucketedDistribution) -> dict:
    a_prices = set(total_buckets(a))
    b_prices = set(total_buckets(b))
    overlap = a_prices & b_prices
    union = a_prices | b_prices
    return {
        "overlap_bucket_count": len(overlap),
        "union_bucket_count": len(union),
        "jaccard": round(len(overlap) / len(union), 6) if union else None,
    }


def main() -> int:
    args = parse_args()
    symbol = args.symbol.upper().removesuffix("USDT")

    short_window = compare.load_sidecar_artifact(args.short_window)
    baseline_window = compare.load_sidecar_artifact(args.baseline_window)
    baseline_rebinned = rebin_distribution(baseline_window, short_window.bin_size)
    short_vs_baseline = compare.compute_metrics(short_window, baseline_rebinned)

    result = {
        "metadata": {
            "symbol": symbol,
            "short_window": str(args.short_window),
            "baseline_window": str(args.baseline_window),
            "coinglass_capture_dir": str(args.coinglass_capture_dir),
        },
        "short_window_stats": concentration_stats(short_window),
        "baseline_window_stats": concentration_stats(baseline_window),
        "baseline_rebinned_stats": concentration_stats(baseline_rebinned),
        "bucket_overlap": bucket_overlap(short_window, baseline_rebinned),
        "short_vs_baseline": short_vs_baseline,
        "interpretation": {
            "sparsity_signal": "Lower accounts_per_bucket and lower position density indicate a sparser or more fragmented 1d surface.",
            "stability_signal": "Short-vs-baseline metrics are computed after rebucketing the baseline onto the short-window price grid.",
        },
    }

    coinglass = compare.load_coinglass_hyperliquid(
        args.coinglass_capture_dir,
        symbol,
        short_window.bin_size,
    )
    if coinglass is not None:
        result["short_vs_coinglass"] = compare.compute_metrics(short_window, coinglass)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"Sensitivity report written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
