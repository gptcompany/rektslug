#!/usr/bin/env python3
"""Confronta varianti Hyperliquid sidecar (v1/v2/v5) producendo report raw-USD.

Calcola metriche globali e su finestre locali attorno al mark price (±3/5/10/15/20%).
Il risultato viene salvato in JSON e un riepilogo viene stampato a console.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from scripts.compare_hl_sidecar_vs_coinglass import (
    BucketedDistribution,
    compute_metrics,
    load_sidecar_artifact,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CACHE_ROOT = PROJECT_ROOT / "data" / "cache"
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "data" / "validation" / "comparison_hl_btc_variants_raw_usd.json"
)
DEFAULT_VARIANTS = {
    "v1": DEFAULT_CACHE_ROOT / "hl_sidecar_btcusdt.json",
    "v2": DEFAULT_CACHE_ROOT / "hl_sidecar_v4_btcusdt.json",
    "v5": DEFAULT_CACHE_ROOT / "hl_sidecar_v5_btcusdt.json",
}
DEFAULT_WINDOWS = (3, 5, 10, 15, 20)


@dataclass
class VariantStats:
    long_volume: float
    short_volume: float
    total_volume: float
    share_of_total: float | None
    ls_ratio: float | None


def _validate_bin_alignment(distributions: list[BucketedDistribution]) -> None:
    base = distributions[0]
    for other in distributions[1:]:
        if abs(other.bin_size - base.bin_size) > 1e-6:
            raise ValueError(
                f"Bin size mismatch: {other.source} {other.bin_size} vs {base.bin_size}"
            )


def slice_distribution(
    distribution: BucketedDistribution, min_price: float, max_price: float
) -> BucketedDistribution:
    sliced = BucketedDistribution(
        source=distribution.source,
        symbol=distribution.symbol,
        bin_size=distribution.bin_size,
        current_price=distribution.current_price,
        account_count=distribution.account_count,
        position_count=distribution.position_count,
        display_min_price=min_price,
        display_max_price=max_price,
    )
    sliced.long_buckets = {
        price: volume
        for price, volume in distribution.long_buckets.items()
        if min_price <= price <= max_price
    }
    sliced.short_buckets = {
        price: volume
        for price, volume in distribution.short_buckets.items()
        if min_price <= price <= max_price
    }
    return sliced


def _compute_variant_stats(
    distribution: BucketedDistribution,
    global_total: float,
) -> VariantStats:
    long_volume = sum(distribution.long_buckets.values())
    short_volume = sum(distribution.short_buckets.values())
    total_volume = long_volume + short_volume
    share = (total_volume / global_total) if global_total > 0 else None
    ls_ratio = (long_volume / short_volume) if short_volume > 0 else None
    return VariantStats(
        long_volume=long_volume,
        short_volume=short_volume,
        total_volume=total_volume,
        share_of_total=share,
        ls_ratio=ls_ratio,
    )


def _pairwise_metrics(variants: dict[str, BucketedDistribution]) -> dict[str, dict]:
    pairs = [
        ("v1_vs_v2", "v1", "v2"),
        ("v1_vs_v5", "v1", "v5"),
        ("v2_vs_v5", "v2", "v5"),
    ]
    results = {}
    for key, left, right in pairs:
        results[key] = compute_metrics(variants[left], variants[right])
    return results


def _window_bounds(mark_price: float, percent: float) -> tuple[float, float]:
    delta = mark_price * (percent / 100.0)
    return (mark_price - delta, mark_price + delta)


def _print_summary(report: dict, windows: Iterable[float]) -> None:
    print("\n=== Hyperliquid Variants Raw-USD Summary ===")
    for pct in windows:
        key = f"pct_{int(pct)}"
        window = report["windows"].get(key)
        if not window:
            continue
        bounds = window["bounds"]
        print(
            f"\nWindow ±{pct}% (" f"{bounds['min_price']:.2f} - {bounds['max_price']:.2f} USD)"
        )
        for name, stats in window["variants"].items():
            total = stats["total_volume"]
            share = stats["share_of_total"]
            share_txt = f"{share:.2%}" if share is not None else "n/a"
            print(
                f"  {name.upper():>3}: total=${total:,.0f} "
                f"share={share_txt}"
            )
        for pair, metrics in window["pairwise"].items():
            pearson = metrics.get("pearson_r", "n/a")
            print(f"    {pair}: Pearson={pearson}")


def generate_report(
    *,
    symbol: str,
    variant_paths: dict[str, Path],
    output_path: Path,
    mark_price: float | None,
    window_percents: Iterable[int],
) -> dict:
    variants: dict[str, BucketedDistribution] = {}
    for name, path in variant_paths.items():
        variants[name] = load_sidecar_artifact(path)
    distributions = list(variants.values())
    _validate_bin_alignment(distributions)

    current_price = mark_price or distributions[0].current_price
    report = {
        "metadata": {
            "symbol": symbol.upper(),
            "current_price": current_price,
            "bin_size": distributions[0].bin_size,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "variants": {name: str(path) for name, path in variant_paths.items()},
        },
        "global": _pairwise_metrics(variants),
        "windows": {},
    }

    global_totals = {
        name: sum(dist.long_buckets.values()) + sum(dist.short_buckets.values())
        for name, dist in variants.items()
    }

    for pct in window_percents:
        min_price, max_price = _window_bounds(current_price, pct)
        sliced_variants = {
            name: slice_distribution(dist, min_price, max_price)
            for name, dist in variants.items()
        }
        window_stats = {
            name: asdict(_compute_variant_stats(dist, global_totals[name]))
            for name, dist in sliced_variants.items()
        }
        report["windows"][f"pct_{pct}"] = {
            "bounds": {"min_price": min_price, "max_price": max_price},
            "variants": window_stats,
            "pairwise": _pairwise_metrics(sliced_variants),
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTC", help="Simbolo (default: BTC)")
    parser.add_argument(
        "--cache-v1",
        type=Path,
        default=DEFAULT_VARIANTS["v1"],
        help="Percorso cache v1",
    )
    parser.add_argument(
        "--cache-v2",
        type=Path,
        default=DEFAULT_VARIANTS["v2"],
        help="Percorso cache v2",
    )
    parser.add_argument(
        "--cache-v5",
        type=Path,
        default=DEFAULT_VARIANTS["v5"],
        help="Percorso cache v5",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="File di output JSON",
    )
    parser.add_argument(
        "--mark-price",
        type=float,
        default=None,
        help="Override manuale del mark price",
    )
    parser.add_argument(
        "--windows",
        type=str,
        default=",".join(str(p) for p in DEFAULT_WINDOWS),
        help="Finestre percentuali separate da virgola (es. '5,10,15')",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    window_percents = tuple(int(part.strip()) for part in args.windows.split(",") if part.strip())
    variant_paths = {
        "v1": args.cache_v1,
        "v2": args.cache_v2,
        "v5": args.cache_v5,
    }

    report = generate_report(
        symbol=args.symbol,
        variant_paths=variant_paths,
        output_path=args.output,
        mark_price=args.mark_price,
        window_percents=window_percents,
    )
    _print_summary(report, window_percents)
    print(f"\nReport salvato in {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
