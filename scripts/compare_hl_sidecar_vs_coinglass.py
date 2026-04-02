#!/usr/bin/env python3
"""
Compare Rektslug sidecar risk-surface against CoinGlass Hyperliquid topPosition data.

Loads sidecar artifacts (JSON) and CoinGlass captures (encrypted), bucketizes both
into the same bin grid, and computes shape metrics (Pearson r, KS, Wasserstein).

Usage:
    uv run python scripts/compare_hl_sidecar_vs_coinglass.py \
        --symbol ETH \
        --sidecar data/validation/liqmap_hl_eth_7d.json \
        --capture-dir data/validation/raw_provider_api/20260320T183129Z \
        --output data/validation/comparison_hl_eth.json

    # Run both ETH and BTC:
    uv run python scripts/compare_hl_sidecar_vs_coinglass.py --all
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.stats import ks_2samp, pearsonr, wasserstein_distance


PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Default config for --all mode
DEFAULT_CONFIGS = {
    "ETH": {
        "sidecar": "data/validation/liqmap_hl_eth_7d.json",
        "capture_dir": "data/validation/raw_provider_api/20260320T183129Z",
    },
    "BTC": {
        "sidecar": "data/validation/liqmap_hl_btc_7d.json",
        "capture_dir": "data/validation/raw_provider_api/20260320T183129Z",
    },
}


@dataclass
class BucketedDistribution:
    """Liquidation distribution bucketed by price."""
    source: str
    symbol: str
    bin_size: float
    current_price: float
    long_buckets: dict[float, float] = field(default_factory=dict)
    short_buckets: dict[float, float] = field(default_factory=dict)
    account_count: int = 0
    position_count: int = 0
    display_min_price: float | None = None
    display_max_price: float | None = None


def _combined_volume(distribution: BucketedDistribution) -> dict[float, float]:
    combined: dict[float, float] = {}
    for price, volume in distribution.long_buckets.items():
        combined[price] = combined.get(price, 0.0) + volume
    for price, volume in distribution.short_buckets.items():
        combined[price] = combined.get(price, 0.0) + volume
    return combined


def _normalized_pearson(values_a: np.ndarray, values_b: np.ndarray) -> float | None:
    if len(values_a) < 10 or len(values_b) < 10:
        return None
    max_a = values_a.max()
    max_b = values_b.max()
    if max_a <= 0 or max_b <= 0:
        return None
    return float(pearsonr(values_a / max_a, values_b / max_b).statistic)


def _rebin_buckets(buckets: dict[float, float], step: float) -> dict[float, float]:
    rebinned: dict[float, float] = {}
    if step <= 0:
        return rebinned
    for price, volume in buckets.items():
        rebinned_price = round(math.floor(price / step + 1e-9) * step, 10)
        rebinned[rebinned_price] = rebinned.get(rebinned_price, 0.0) + volume
    return rebinned


def _coarse_shape_metrics(
    distribution_a: BucketedDistribution,
    distribution_b: BucketedDistribution,
) -> dict[str, dict[str, float | int]]:
    metrics: dict[str, dict[str, float | int]] = {}
    combined_a = _combined_volume(distribution_a)
    combined_b = _combined_volume(distribution_b)
    for multiplier in (5, 10, 25, 50, 100):
        step = distribution_a.bin_size * multiplier
        rebinned_a = _rebin_buckets(combined_a, step)
        rebinned_b = _rebin_buckets(combined_b, step)
        prices = sorted(set(rebinned_a) | set(rebinned_b))
        if len(prices) < 10:
            continue
        values_a = np.array([rebinned_a.get(price, 0.0) for price in prices], dtype=float)
        values_b = np.array([rebinned_b.get(price, 0.0) for price in prices], dtype=float)
        mask = (values_a > 0) | (values_b > 0)
        pearson_value = _normalized_pearson(values_a[mask], values_b[mask])
        if pearson_value is None:
            continue
        metrics[str(multiplier)] = {
            "step": round(step, 10),
            "bins": int(mask.sum()),
            "pearson_r": round(pearson_value, 4),
        }
    return metrics


def _cumulative_shape_metrics(
    distribution_a: BucketedDistribution,
    distribution_b: BucketedDistribution,
) -> dict[str, dict[str, float | int]]:
    metrics: dict[str, dict[str, float | int]] = {}
    combined_a = _combined_volume(distribution_a)
    combined_b = _combined_volume(distribution_b)
    for multiplier in (10, 50, 100):
        step = distribution_a.bin_size * multiplier
        rebinned_a = _rebin_buckets(combined_a, step)
        rebinned_b = _rebin_buckets(combined_b, step)
        prices = sorted(set(rebinned_a) | set(rebinned_b))
        if len(prices) < 10:
            continue
        cumulative_a = np.cumsum(np.array([rebinned_a.get(price, 0.0) for price in prices], dtype=float))
        cumulative_b = np.cumsum(np.array([rebinned_b.get(price, 0.0) for price in prices], dtype=float))
        pearson_value = _normalized_pearson(cumulative_a, cumulative_b)
        if pearson_value is None:
            continue
        metrics[str(multiplier)] = {
            "step": round(step, 10),
            "points": len(prices),
            "pearson_r": round(pearson_value, 4),
        }
    return metrics


def load_sidecar_artifact(path: Path) -> BucketedDistribution:
    """Load either the legacy validation artifact or the modern cache JSON."""
    with open(path) as f:
        data = json.load(f)

    if "metadata" in data:
        meta = data["metadata"]
        dist = BucketedDistribution(
            source="rektslug-sidecar",
            symbol=meta["target_coin"],
            bin_size=meta["bin_size"],
            current_price=0.0,
            account_count=meta["account_count"],
        )
        for entry in data["long_liquidations"]:
            dist.long_buckets[float(entry["price"])] = float(entry["volume"])
        for entry in data["short_liquidations"]:
            dist.short_buckets[float(entry["price"])] = float(entry["volume"])
        dist.position_count = len(dist.long_buckets) + len(dist.short_buckets)
        return dist

    symbol = str(data.get("symbol", "")).removesuffix("USDT")
    grid = data.get("grid", {})
    dist = BucketedDistribution(
        source=str(data.get("source", "hyperliquid-sidecar")),
        symbol=symbol,
        bin_size=float(data.get("bin_size") or grid.get("step") or 0.0),
        current_price=float(data.get("current_price", 0.0)),
        account_count=int(data.get("account_count", 0)),
        display_min_price=(
            float(grid["min_price"]) if grid.get("min_price") is not None else None
        ),
        display_max_price=(
            float(grid["max_price"]) if grid.get("max_price") is not None else None
        ),
    )
    for entry in data.get("long_buckets", []):
        dist.long_buckets[float(entry["price_level"])] = float(entry["volume"])
    for entry in data.get("short_buckets", []):
        dist.short_buckets[float(entry["price_level"])] = float(entry["volume"])

    dist.position_count = len(dist.long_buckets) + len(dist.short_buckets)
    return dist


def decode_coinglass_capture(capture_dir: Path, symbol: str) -> dict | None:
    """Decode a CoinGlass Hyperliquid capture for a given symbol."""
    manifest_path = capture_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"  WARNING: No manifest at {manifest_path}", file=sys.stderr)
        return None

    with open(manifest_path) as f:
        manifest = json.load(f)

    if not symbol.isalpha():
        print(f"  WARNING: Invalid symbol: {symbol}", file=sys.stderr)
        return None

    target_url = f"hyperliquid/topPosition/liqMap?symbol={symbol}"
    capture = None
    for prov in manifest.get("providers", []):
        for cap in prov.get("captures", []):
            if target_url in cap.get("source_url", ""):
                capture = cap
                break

    if not capture:
        print(f"  WARNING: No Hyperliquid {symbol} capture in {capture_dir}", file=sys.stderr)
        return None

    summary = {"captures": [capture]}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        json.dump(summary, tmp)
        tmp_path = tmp.name

    decode_script = PROJECT_ROOT / "scripts" / "coinglass_decode_standalone.js"
    try:
        result = subprocess.run(
            ["node", str(decode_script), "--summary", tmp_path],
            capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        print("  WARNING: 'node' not found in PATH", file=sys.stderr)
        return None
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if result.returncode != 0:
        print(f"  WARNING: Decode failed: {result.stderr[:200]}", file=sys.stderr)
        return None

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"  WARNING: Decode output is not valid JSON: {result.stdout[:100]}", file=sys.stderr)
        return None


def load_coinglass_hyperliquid(
    capture_dir: Path, symbol: str, bin_size: float
) -> BucketedDistribution | None:
    """Load and bucketize CoinGlass Hyperliquid topPosition data."""
    decoded = decode_coinglass_capture(capture_dir, symbol)
    if decoded is None:
        return None

    dist = BucketedDistribution(
        source="coinglass-hyperliquid",
        symbol=symbol,
        bin_size=bin_size,
        current_price=float(decoded.get("price", 0)),
    )

    positions = decoded.get("list", [])
    dist.position_count = len(positions)

    for pos in positions:
        liq_px = pos.get("liquidationPrice", 0)
        notional = abs(pos.get("positionUsd", 0))
        size = pos.get("size", 0)

        if liq_px <= 0 or notional <= 0:
            continue

        rounded_bin = round(math.floor(liq_px / bin_size + 1e-9) * bin_size, 10)

        if size > 0:
            dist.long_buckets[rounded_bin] = dist.long_buckets.get(rounded_bin, 0) + notional
        else:
            dist.short_buckets[rounded_bin] = dist.short_buckets.get(rounded_bin, 0) + notional

    return dist


def compute_metrics(a: BucketedDistribution, b: BucketedDistribution) -> dict:
    """Compute shape comparison metrics between two distributions."""
    results: dict = {
        "a_source": a.source,
        "b_source": b.source,
        "symbol": a.symbol,
        "bin_size": a.bin_size,
    }

    a_total = _combined_volume(a)
    b_total = _combined_volume(b)

    a_long_vol = sum(a.long_buckets.values())
    a_short_vol = sum(a.short_buckets.values())
    b_long_vol = sum(b.long_buckets.values())
    b_short_vol = sum(b.short_buckets.values())

    results["a_stats"] = {
        "long_volume": round(a_long_vol, 2),
        "short_volume": round(a_short_vol, 2),
        "total_volume": round(a_long_vol + a_short_vol, 2),
        "ls_ratio": round(a_long_vol / a_short_vol, 4) if a_short_vol > 0 else None,
        "long_buckets": len(a.long_buckets),
        "short_buckets": len(a.short_buckets),
        "position_count": a.position_count,
        "account_count": a.account_count,
    }
    results["b_stats"] = {
        "long_volume": round(b_long_vol, 2),
        "short_volume": round(b_short_vol, 2),
        "total_volume": round(b_long_vol + b_short_vol, 2),
        "ls_ratio": round(b_long_vol / b_short_vol, 4) if b_short_vol > 0 else None,
        "long_buckets": len(b.long_buckets),
        "short_buckets": len(b.short_buckets),
        "position_count": b.position_count,
        "account_count": b.account_count,
    }

    a_vol = a_long_vol + a_short_vol
    b_vol = b_long_vol + b_short_vol
    results["volume_scale_ratio"] = round(b_vol / a_vol, 4) if a_vol > 0 else None

    all_prices = sorted(set(a_total.keys()) | set(b_total.keys()))
    if len(all_prices) < 5:
        results["error"] = "Too few price buckets for shape comparison"
        return results

    a_arr = np.array([a_total.get(price, 0.0) for price in all_prices], dtype=float)
    b_arr = np.array([b_total.get(price, 0.0) for price in all_prices], dtype=float)
    prices = np.array(all_prices, dtype=float)

    a_max = a_arr.max()
    b_max = b_arr.max()
    a_norm = a_arr / a_max if a_max > 0 else a_arr
    b_norm = b_arr / b_max if b_max > 0 else b_arr

    mask = (a_norm > 0) | (b_norm > 0)
    if mask.sum() < 5:
        results["error"] = "Too few nonzero bins for comparison"
        return results

    a_m, b_m = a_norm[mask], b_norm[mask]
    if len(a_m) >= 10:
        r, p_val = pearsonr(a_m, b_m)
        results["pearson_r"] = round(float(r), 4)
        results["pearson_p"] = float(f"{p_val:.2e}")

    rng = np.random.default_rng(42)
    n_samples = 5000

    def weighted_samples(arr: np.ndarray, price_arr: np.ndarray) -> np.ndarray:
        total = arr.sum()
        if total <= 0:
            return np.array([])
        weights = arr / total
        idx = rng.choice(len(price_arr), size=n_samples, p=weights)
        return price_arr[idx]

    a_samples = weighted_samples(a_arr, prices)
    b_samples = weighted_samples(b_arr, prices)
    if len(a_samples) > 0 and len(b_samples) > 0:
        ks_stat, ks_p = ks_2samp(a_samples, b_samples)
        results["ks_statistic"] = round(float(ks_stat), 4)
        results["ks_p"] = float(f"{ks_p:.2e}")

    a_weights = a_m / a_m.sum() if a_m.sum() > 0 else a_m
    b_weights = b_m / b_m.sum() if b_m.sum() > 0 else b_m
    prices_m = prices[mask]
    if a_weights.sum() > 0 and b_weights.sum() > 0:
        wd = wasserstein_distance(prices_m, prices_m, a_weights, b_weights)
        results["wasserstein_distance"] = round(float(wd), 2)

    a_peak_idx = np.argsort(a_arr)[-5:][::-1]
    b_peak_idx = np.argsort(b_arr)[-5:][::-1]
    results["a_peak_prices"] = [float(prices[i]) for i in a_peak_idx]
    results["b_peak_prices"] = [float(prices[i]) for i in b_peak_idx]

    a_peaks = [float(prices[i]) for i in a_peak_idx]
    b_peaks = list(float(prices[i]) for i in b_peak_idx)
    peak_dists = []
    remaining = list(b_peaks)
    for peak in a_peaks:
        if not remaining:
            break
        dists = [abs(peak - candidate) for candidate in remaining]
        best = int(np.argmin(dists))
        peak_dists.append(dists[best])
        remaining.pop(best)
    if peak_dists:
        results["peak_mean_distance"] = round(float(np.mean(peak_dists)), 2)
        results["peak_max_distance"] = round(float(np.max(peak_dists)), 2)

    a_ls = a_long_vol / a_short_vol if a_short_vol > 0 else None
    b_ls = b_long_vol / b_short_vol if b_short_vol > 0 else None
    if a_ls is not None and b_ls is not None:
        results["ls_ratio_diff"] = round(abs(a_ls - b_ls), 4)

    for side, a_side, b_side in [
        ("long", a.long_buckets, b.long_buckets),
        ("short", a.short_buckets, b.short_buckets),
    ]:
        side_prices = sorted(set(a_side.keys()) | set(b_side.keys()))
        if len(side_prices) < 5:
            continue
        sa = np.array([a_side.get(price, 0.0) for price in side_prices], dtype=float)
        sb = np.array([b_side.get(price, 0.0) for price in side_prices], dtype=float)
        side_mask = (sa > 0) | (sb > 0)
        pearson_value = _normalized_pearson(sa[side_mask], sb[side_mask])
        if pearson_value is not None:
            results[f"{side}_pearson_r"] = round(pearson_value, 4)

    results["coarse_shape"] = _coarse_shape_metrics(a, b)
    results["cumulative_shape"] = _cumulative_shape_metrics(a, b)

    if a.display_min_price is not None and a.display_max_price is not None:
        def display_coverage(buckets: dict[float, float]) -> dict[str, float | int]:
            total = sum(buckets.values())
            inside = sum(
                volume
                for price, volume in buckets.items()
                if a.display_min_price <= price <= a.display_max_price
            )
            outside = total - inside
            return {
                "inside_volume": round(inside, 2),
                "outside_volume": round(outside, 2),
                "inside_ratio": round(inside / total, 4) if total > 0 else None,
                "outside_ratio": round(outside / total, 4) if total > 0 else None,
                "outside_bins": sum(
                    1
                    for price in buckets
                    if price < a.display_min_price or price > a.display_max_price
                ),
            }

        results["display_grid"] = {
            "min_price": a.display_min_price,
            "max_price": a.display_max_price,
            "a_long": display_coverage(a.long_buckets),
            "a_short": display_coverage(a.short_buckets),
            "b_long": display_coverage(b.long_buckets),
            "b_short": display_coverage(b.short_buckets),
        }

    return results


def assess(metrics: dict) -> str:
    """Human-readable assessment from metrics."""
    parts = []
    r = metrics.get("pearson_r")
    if r is not None:
        label = "STRONG" if r > 0.6 else "MODERATE" if r > 0.3 else "WEAK" if r > 0 else "ANTI"
        parts.append(f"Pearson={label}({r:.3f})")

    ks = metrics.get("ks_statistic")
    if ks is not None:
        label = "SIMILAR" if ks < 0.15 else "DIFFERENT" if ks < 0.3 else "VERY DIFFERENT"
        parts.append(f"KS={label}({ks:.3f})")

    wd = metrics.get("wasserstein_distance")
    if wd is not None:
        parts.append(f"Wasserstein={wd:.0f}")

    ls = metrics.get("ls_ratio_diff")
    if ls is not None:
        label = "CLOSE" if ls < 0.1 else "MODERATE" if ls < 0.3 else "DIVERGENT"
        parts.append(f"L/S_diff={label}({ls:.3f})")

    return " | ".join(parts) if parts else "INSUFFICIENT DATA"


def print_report(all_metrics: list[dict]) -> None:
    """Print comparison report to stdout."""
    print("\n" + "=" * 90)
    print("REKTSLUG SIDECAR vs COINGLASS HYPERLIQUID -- COMPARISON REPORT")
    print("=" * 90)

    for m in all_metrics:
        print(f"\n--- {m.get('symbol', '?')} (bin_size={m.get('bin_size', 'n/a')}) ---")
        print(
            "  Sources: "
            f"{m.get('a_source', 'rektslug-sidecar')} vs "
            f"{m.get('b_source', 'coinglass-hyperliquid')}"
        )

        if "error" in m:
            print(f"  ERROR: {m['error']}")
            if m.get("capture_dir"):
                print(f"  Capture dir: {m['capture_dir']}")
            continue

        a_s = m.get("a_stats", {})
        b_s = m.get("b_stats", {})
        print(f"\n  Rektslug Sidecar:")
        print(f"    Accounts:     {a_s.get('account_count', '?'):>10,}")
        print(f"    Long volume:  ${a_s.get('long_volume', 0):>15,.0f}")
        print(f"    Short volume: ${a_s.get('short_volume', 0):>15,.0f}")
        print(f"    L/S ratio:    {a_s.get('ls_ratio', '?'):>10}")
        print(f"    Long buckets: {a_s.get('long_buckets', 0):>10,}")
        print(f"    Short buckets:{a_s.get('short_buckets', 0):>10,}")

        print(f"\n  CoinGlass Hyperliquid:")
        print(f"    Positions:    {b_s.get('position_count', '?'):>10,}")
        print(f"    Long volume:  ${b_s.get('long_volume', 0):>15,.0f}")
        print(f"    Short volume: ${b_s.get('short_volume', 0):>15,.0f}")
        print(f"    L/S ratio:    {b_s.get('ls_ratio', '?'):>10}")

        print(f"\n  Volume scale (CG/Sidecar): {m.get('volume_scale_ratio', '?')}")

        print(f"\n  Shape Metrics (combined long+short):")
        print(f"    Pearson r:          {m.get('pearson_r', 'n/a'):>10}")
        print(f"    KS statistic:       {m.get('ks_statistic', 'n/a'):>10}")
        print(f"    Wasserstein dist:   {m.get('wasserstein_distance', 'n/a'):>10}")
        print(f"    L/S ratio diff:     {m.get('ls_ratio_diff', 'n/a'):>10}")

        lr = m.get("long_pearson_r")
        sr = m.get("short_pearson_r")
        if lr is not None or sr is not None:
            print(f"\n  Per-Side Pearson r:")
            if lr is not None:
                print(f"    Long:  {lr:>10}")
            if sr is not None:
                print(f"    Short: {sr:>10}")

        print(f"\n  Peak Locations:")
        print(f"    Sidecar top 5: {m.get('a_peak_prices', [])}")
        print(f"    CoinGlass top 5: {m.get('b_peak_prices', [])}")
        print(f"    Peak mean dist:  {m.get('peak_mean_distance', 'n/a')}")
        print(f"    Peak max dist:   {m.get('peak_max_distance', 'n/a')}")

        print(f"\n  Assessment: {m.get('assessment', 'n/a')}")

    print("\n" + "=" * 90)


def run_comparison(
    symbol: str, sidecar_path: Path, capture_dir: Path, output_path: Path | None
) -> dict:
    """Run a single symbol comparison."""
    print(f"\n=== {symbol} Comparison ===")

    print(f"  Loading sidecar artifact: {sidecar_path}")
    sidecar = load_sidecar_artifact(sidecar_path)

    # Use sidecar mark price as current price if available
    # The sidecar doesn't store current_price in metadata, so we leave it at 0

    print(f"  Loading CoinGlass capture: {capture_dir}")
    coinglass = load_coinglass_hyperliquid(capture_dir, symbol, sidecar.bin_size)
    if coinglass is None:
        return {
            "symbol": symbol,
            "bin_size": sidecar.bin_size,
            "a_source": sidecar.source,
            "b_source": "coinglass-hyperliquid",
            "capture_dir": str(capture_dir),
            "error": "CoinGlass data unavailable or undecodable for this capture.",
        }

    # Set sidecar current_price from CoinGlass
    sidecar.current_price = coinglass.current_price

    print(f"  Computing metrics...")
    metrics = compute_metrics(sidecar, coinglass)
    metrics["assessment"] = assess(metrics)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(metrics, f, indent=2, default=str)
        print(f"  Saved to: {output_path}")

    return metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--all", action="store_true", help="Run ETH + BTC with default paths")
    parser.add_argument("--symbol", help="Symbol to compare (ETH or BTC)")
    parser.add_argument("--sidecar", type=Path, help="Path to sidecar JSON artifact")
    parser.add_argument("--capture-dir", type=Path, help="CoinGlass capture directory")
    parser.add_argument("--output", type=Path, help="Output JSON path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    all_metrics: list[dict] = []

    if args.all:
        for symbol, cfg in DEFAULT_CONFIGS.items():
            sidecar_path = PROJECT_ROOT / cfg["sidecar"]
            capture_dir = PROJECT_ROOT / cfg["capture_dir"]
            output = PROJECT_ROOT / f"data/validation/comparison_hl_{symbol.lower()}.json"
            if not sidecar_path.exists():
                print(f"  SKIP {symbol}: sidecar artifact missing at {sidecar_path}")
                continue
            metrics = run_comparison(symbol, sidecar_path, capture_dir, output)
            all_metrics.append(metrics)
    elif args.symbol and args.sidecar and args.capture_dir:
        metrics = run_comparison(args.symbol, args.sidecar, args.capture_dir, args.output)
        all_metrics.append(metrics)
    else:
        print("Usage: --all OR --symbol X --sidecar PATH --capture-dir DIR", file=sys.stderr)
        return 1

    print_report(all_metrics)

    # Save combined report
    combined_path = PROJECT_ROOT / "data" / "validation" / "comparison_hl_combined.json"
    combined_path.parent.mkdir(parents=True, exist_ok=True)
    combined = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "comparisons": all_metrics,
    }
    with open(combined_path, "w") as f:
        json.dump(combined, f, indent=2, default=str)
    print(f"\nCombined report saved to: {combined_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
