#!/usr/bin/env python3
"""
Shape-based normalized comparison of liquidation maps across 3 providers.

Compares the SHAPE (not absolute values) of liquidation distributions
across Rektslug, CoinAnK, and CoinGlass after normalizing both axes.

Usage:
    uv run python scripts/shape_comparison_analysis.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from scipy.interpolate import interp1d
from scipy.stats import ks_2samp, pearsonr, wasserstein_distance


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "validation"
RAW_DIR = DATA_DIR / "raw_provider_api"
REPORT_PATH = DATA_DIR / "shape_comparison_report.json"

REKTSLUG_BASE = "http://localhost:8002"

# Captures with matching timestamps (ETH 1d and 1w)
CAPTURES = {
    "ETH_1d": {
        "timestamp": "20260319T192254Z",
        "coinank_file": "15_getliqmap.json",
        "coinglass_summary": "summary.json",
        "symbol": "ETHUSDT",
        "timeframe": "1d",
        "exchange": "binance",
    },
    "ETH_1w": {
        "timestamp": "20260319T192350Z",
        "coinank_file": "14_getliqmap.json",
        "coinglass_summary": "summary.json",
        "symbol": "ETHUSDT",
        "timeframe": "1w",
        "exchange": "binance",
    },
}

# Number of points in the common interpolation grid
GRID_POINTS = 500


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class LiqDistribution:
    """Normalized liquidation distribution from one provider."""

    provider: str
    symbol: str
    timeframe: str
    # Raw price grid and raw volumes (before normalization)
    raw_prices: np.ndarray = field(default_factory=lambda: np.array([]))
    raw_volumes: np.ndarray = field(default_factory=lambda: np.array([]))
    current_price: float = 0.0
    # Normalized arrays (filled by normalize())
    norm_prices: np.ndarray = field(default_factory=lambda: np.array([]))
    norm_volumes: np.ndarray = field(default_factory=lambda: np.array([]))
    norm_cumulative: np.ndarray = field(default_factory=lambda: np.array([]))
    valid: bool = False
    error: str = ""

    def normalize(self) -> None:
        """Normalize price to [-1, 1] and volume to [0, 1]."""
        if len(self.raw_prices) == 0 or len(self.raw_volumes) == 0:
            return

        # Filter to nonzero volume entries for meaningful shape comparison
        mask = self.raw_volumes > 0
        if mask.sum() < 5:
            self.error = f"Too few nonzero bins ({mask.sum()})"
            return

        prices = self.raw_prices[mask]
        volumes = self.raw_volumes[mask]

        # Normalize price: map to [-1, 1] where 0 = current_price
        p_min, p_max = prices.min(), prices.max()
        if p_max == p_min:
            self.error = "Zero price range"
            return

        # Center on current price, scale so extremes map to +/-1
        centered = prices - self.current_price
        max_abs = max(abs(self.current_price - p_min), abs(p_max - self.current_price))
        if max_abs == 0:
            max_abs = 1.0
        self.norm_prices = centered / max_abs

        # Normalize volume: peak = 1
        vol_max = volumes.max()
        if vol_max == 0:
            self.error = "Zero max volume"
            return
        self.norm_volumes = volumes / vol_max

        # Cumulative (for KS test) - normalized to [0, 1]
        cum = np.cumsum(volumes)
        self.norm_cumulative = cum / cum[-1]

        self.valid = True


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_coinank(capture_cfg: dict) -> LiqDistribution:
    """Load CoinAnK data from raw captured JSON."""
    dist = LiqDistribution(
        provider="coinank",
        symbol=capture_cfg["symbol"],
        timeframe=capture_cfg["timeframe"],
    )
    try:
        path = (
            RAW_DIR
            / capture_cfg["timestamp"]
            / "coinank"
            / capture_cfg["coinank_file"]
        )
        with open(path) as f:
            raw = json.load(f)

        data = raw.get("data", raw)
        prices = np.array(data["prices"], dtype=np.float64)
        last_price = float(data.get("lastPrice", 0))

        # Sum all leverage tiers for total volume per price point
        leverage_keys = [k for k in data if k.startswith("x") and k[1:].isdigit()]
        if not leverage_keys:
            dist.error = "No leverage keys found"
            return dist

        total = np.zeros(len(prices), dtype=np.float64)
        for lev in leverage_keys:
            arr = np.array(data[lev], dtype=np.float64)
            if len(arr) == len(prices):
                total += arr

        dist.raw_prices = prices
        dist.raw_volumes = total
        dist.current_price = last_price
        dist.normalize()

    except Exception as e:
        dist.error = str(e)

    return dist


def load_coinglass(capture_cfg: dict) -> LiqDistribution:
    """Load CoinGlass data by decoding encrypted payload via node script."""
    dist = LiqDistribution(
        provider="coinglass",
        symbol=capture_cfg["symbol"],
        timeframe=capture_cfg["timeframe"],
    )
    try:
        summary_path = (
            RAW_DIR
            / capture_cfg["timestamp"]
            / "coinglass"
            / capture_cfg["coinglass_summary"]
        )
        decode_script = PROJECT_ROOT / "scripts" / "coinglass_decode_standalone.js"

        result = subprocess.run(
            ["node", str(decode_script), "--summary", str(summary_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            dist.error = f"Decode failed: {result.stderr[:200]}"
            return dist

        decoded = json.loads(result.stdout)
        last_price = float(decoded.get("lastPrice", 0))
        liq_map = decoded.get("liqMapV2", {})

        if not liq_map:
            dist.error = "Empty liqMapV2"
            return dist

        # CoinGlass format: {"price_str": [[exact_price, volume, leverage, heatmap_level], ...]}
        # Aggregate all entries per price bucket
        price_buckets: dict[float, float] = {}
        for bucket_price_str, entries in liq_map.items():
            bucket_price = float(bucket_price_str)
            total_vol = sum(entry[1] for entry in entries)
            price_buckets[bucket_price] = total_vol

        sorted_prices = sorted(price_buckets.keys())
        prices = np.array(sorted_prices, dtype=np.float64)
        volumes = np.array([price_buckets[p] for p in sorted_prices], dtype=np.float64)

        dist.raw_prices = prices
        dist.raw_volumes = volumes
        dist.current_price = last_price
        dist.normalize()

    except Exception as e:
        dist.error = str(e)

    return dist


def _parse_rektslug_bucket(entry: Any) -> tuple[float, float] | None:
    """Parse one Rektslug bucket entry from schema v2 responses."""
    if isinstance(entry, dict):
        raw_price = entry.get("price_level", entry.get("price"))
        raw_volume = entry.get("volume")
        if raw_price is None or raw_volume is None:
            return None
        return float(raw_price), float(raw_volume)

    if isinstance(entry, (list, tuple)) and len(entry) >= 2:
        return float(entry[0]), float(entry[1])

    return None


def load_rektslug(capture_cfg: dict) -> LiqDistribution:
    """Load Rektslug data from local API (may fail if DB locked)."""
    dist = LiqDistribution(
        provider="rektslug",
        symbol=capture_cfg["symbol"],
        timeframe=capture_cfg["timeframe"],
    )
    try:
        exchange = str(capture_cfg.get("exchange", "binance")).lower()
        url = (
            f"{REKTSLUG_BASE}/liquidations/coinank-public-map"
            f"?exchange={exchange}&symbol={capture_cfg['symbol']}&timeframe={capture_cfg['timeframe']}"
        )
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        # Check for error response
        if "error" in data:
            dist.error = f"API error: {data.get('message', data['error'])}"
            return dist

        # Rektslug returns CoinAnK-compatible format with prices + leverage arrays
        if "prices" in data:
            # Same format as CoinAnK raw
            prices = np.array(data["prices"], dtype=np.float64)
            last_price = float(data.get("lastPrice", 0))

            leverage_keys = [k for k in data if k.startswith("x") and k[1:].isdigit()]
            total = np.zeros(len(prices), dtype=np.float64)
            for lev in leverage_keys:
                arr = np.array(data[lev], dtype=np.float64)
                if len(arr) == len(prices):
                    total += arr

            dist.raw_prices = prices
            dist.raw_volumes = total
            dist.current_price = last_price
        elif "long_buckets" in data and "short_buckets" in data:
            # Schema v2 with separate long/short buckets
            current_price = float(data.get("current_price", 0))
            long_b = data.get("long_buckets", [])
            short_b = data.get("short_buckets", [])

            all_entries: dict[float, float] = {}
            for entry in long_b:
                parsed = _parse_rektslug_bucket(entry)
                if parsed is None:
                    continue
                p, v = parsed
                all_entries[p] = all_entries.get(p, 0) + v

            for entry in short_b:
                parsed = _parse_rektslug_bucket(entry)
                if parsed is None:
                    continue
                p, v = parsed
                all_entries[p] = all_entries.get(p, 0) + v

            if not all_entries:
                dist.error = "No bucket data parsed"
                return dist

            sorted_prices = sorted(all_entries.keys())
            dist.raw_prices = np.array(sorted_prices, dtype=np.float64)
            dist.raw_volumes = np.array(
                [all_entries[p] for p in sorted_prices], dtype=np.float64
            )
            dist.current_price = current_price
        else:
            dist.error = f"Unknown response format, keys: {list(data.keys())}"
            return dist

        dist.normalize()

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        dist.error = f"HTTP {e.code}: {body}"
    except urllib.error.URLError as e:
        dist.error = f"Connection error: {e.reason}"
    except Exception as e:
        dist.error = f"{type(e).__name__}: {e}"

    return dist


# ---------------------------------------------------------------------------
# Shape comparison metrics
# ---------------------------------------------------------------------------

def interpolate_to_common_grid(
    dist: LiqDistribution, grid: np.ndarray
) -> np.ndarray:
    """Interpolate normalized volumes onto a common price grid."""
    if not dist.valid:
        return np.full(len(grid), np.nan)

    f = interp1d(
        dist.norm_prices,
        dist.norm_volumes,
        kind="linear",
        bounds_error=False,
        fill_value=0.0,
    )
    return f(grid)


def interpolate_cumulative_to_grid(
    dist: LiqDistribution, grid: np.ndarray
) -> np.ndarray:
    """Interpolate normalized cumulative curve onto a common price grid."""
    if not dist.valid:
        return np.full(len(grid), np.nan)

    f = interp1d(
        dist.norm_prices,
        dist.norm_cumulative,
        kind="linear",
        bounds_error=False,
        fill_value=(0.0, 1.0),
    )
    return f(grid)


def find_peak_locations(dist: LiqDistribution, top_n: int = 5) -> np.ndarray:
    """Find normalized price locations of top-N volume peaks."""
    if not dist.valid:
        return np.array([])
    indices = np.argsort(dist.norm_volumes)[-top_n:]
    return np.sort(dist.norm_prices[indices])


def compute_skewness(dist: LiqDistribution) -> float:
    """Compute volume-weighted skewness of the distribution."""
    if not dist.valid:
        return float("nan")
    # Weighted mean and std
    total = dist.norm_volumes.sum()
    if total == 0:
        return float("nan")
    w = dist.norm_volumes / total
    mean = np.sum(w * dist.norm_prices)
    var = np.sum(w * (dist.norm_prices - mean) ** 2)
    std = np.sqrt(var) if var > 0 else 1e-10
    skew = np.sum(w * ((dist.norm_prices - mean) / std) ** 3)
    return float(skew)


def compare_pair(
    a: LiqDistribution, b: LiqDistribution
) -> dict[str, Any]:
    """Compute all shape similarity metrics between two distributions."""
    result: dict[str, Any] = {
        "providers": f"{a.provider} vs {b.provider}",
        "a_valid": a.valid,
        "b_valid": b.valid,
    }

    if not (a.valid and b.valid):
        reasons = []
        if not a.valid:
            reasons.append(f"{a.provider}: {a.error}")
        if not b.valid:
            reasons.append(f"{b.provider}: {b.error}")
        result["skip_reason"] = "; ".join(reasons)
        return result

    # Common normalized price grid spanning the overlap region
    overlap_min = max(a.norm_prices.min(), b.norm_prices.min())
    overlap_max = min(a.norm_prices.max(), b.norm_prices.max())

    if overlap_min >= overlap_max:
        result["skip_reason"] = "No overlapping price range"
        return result

    grid = np.linspace(overlap_min, overlap_max, GRID_POINTS)

    # Interpolate both to common grid
    a_interp = interpolate_to_common_grid(a, grid)
    b_interp = interpolate_to_common_grid(b, grid)

    # Re-normalize interpolated volumes (peak = 1 in overlap region)
    a_max = a_interp.max()
    b_max = b_interp.max()
    if a_max > 0:
        a_interp_norm = a_interp / a_max
    else:
        a_interp_norm = a_interp
    if b_max > 0:
        b_interp_norm = b_interp / b_max
    else:
        b_interp_norm = b_interp

    # 1. Pearson correlation of volume distributions
    # Only consider points where at least one has volume
    mask = (a_interp_norm > 0) | (b_interp_norm > 0)
    if mask.sum() >= 10:
        r, p_val = pearsonr(a_interp_norm[mask], b_interp_norm[mask])
        result["pearson_r"] = round(float(r), 4)
        result["pearson_p"] = float(f"{p_val:.2e}")
    else:
        result["pearson_r"] = None
        result["pearson_p"] = None

    # 2. Kolmogorov-Smirnov on cumulative curves
    a_cum = interpolate_cumulative_to_grid(a, grid)
    b_cum = interpolate_cumulative_to_grid(b, grid)
    ks_stat = float(np.max(np.abs(a_cum - b_cum)))
    result["ks_statistic"] = round(ks_stat, 4)

    # Also scipy KS test on raw samples (create weighted samples)
    n_samples = 5000
    a_samples = _weighted_samples(a, n_samples)
    b_samples = _weighted_samples(b, n_samples)
    if len(a_samples) > 0 and len(b_samples) > 0:
        ks_stat2, ks_p = ks_2samp(a_samples, b_samples)
        result["ks_2samp_stat"] = round(float(ks_stat2), 4)
        result["ks_2samp_p"] = float(f"{ks_p:.2e}")

    # 3. Wasserstein (earth mover's) distance on normalized distributions
    a_weights = a_interp_norm[mask] / a_interp_norm[mask].sum() if a_interp_norm[mask].sum() > 0 else a_interp_norm[mask]
    b_weights = b_interp_norm[mask] / b_interp_norm[mask].sum() if b_interp_norm[mask].sum() > 0 else b_interp_norm[mask]
    grid_masked = grid[mask]
    if len(grid_masked) > 0 and a_weights.sum() > 0 and b_weights.sum() > 0:
        wd = wasserstein_distance(grid_masked, grid_masked, a_weights, b_weights)
        result["wasserstein_distance"] = round(float(wd), 4)
    else:
        result["wasserstein_distance"] = None

    # 4. Peak location similarity
    a_peaks = find_peak_locations(a, top_n=5)
    b_peaks = find_peak_locations(b, top_n=5)
    if len(a_peaks) > 0 and len(b_peaks) > 0:
        # Mean distance between matched peaks (greedy matching)
        peak_dists = []
        b_remaining = list(b_peaks)
        for ap in a_peaks:
            if not b_remaining:
                break
            dists = [abs(ap - bp) for bp in b_remaining]
            best_idx = int(np.argmin(dists))
            peak_dists.append(dists[best_idx])
            b_remaining.pop(best_idx)
        result["peak_mean_distance"] = round(float(np.mean(peak_dists)), 4)
        result["peak_max_distance"] = round(float(np.max(peak_dists)), 4)
        result["a_peak_locations"] = [round(float(p), 4) for p in a_peaks]
        result["b_peak_locations"] = [round(float(p), 4) for p in b_peaks]

    # 5. Skewness comparison
    a_skew = compute_skewness(a)
    b_skew = compute_skewness(b)
    result["a_skewness"] = round(a_skew, 4) if not np.isnan(a_skew) else None
    result["b_skewness"] = round(b_skew, 4) if not np.isnan(b_skew) else None
    if not (np.isnan(a_skew) or np.isnan(b_skew)):
        result["skewness_diff"] = round(abs(a_skew - b_skew), 4)

    # 6. Volume overlap coefficient (Szymkiewicz-Simpson)
    min_sum = np.sum(np.minimum(a_interp_norm, b_interp_norm))
    smaller_sum = min(np.sum(a_interp_norm), np.sum(b_interp_norm))
    if smaller_sum > 0:
        result["overlap_coefficient"] = round(float(min_sum / smaller_sum), 4)

    # Summary statistics
    result["overlap_price_range"] = [round(float(overlap_min), 4), round(float(overlap_max), 4)]
    result["a_nonzero_bins"] = int((a.raw_volumes > 0).sum())
    result["b_nonzero_bins"] = int((b.raw_volumes > 0).sum())

    return result


def _weighted_samples(dist: LiqDistribution, n: int) -> np.ndarray:
    """Generate weighted random samples from a distribution for KS test."""
    if not dist.valid or dist.norm_volumes.sum() == 0:
        return np.array([])
    weights = dist.norm_volumes / dist.norm_volumes.sum()
    rng = np.random.default_rng(42)
    indices = rng.choice(len(dist.norm_prices), size=n, p=weights)
    return dist.norm_prices[indices]


# ---------------------------------------------------------------------------
# Assessment logic
# ---------------------------------------------------------------------------

def assess_similarity(metrics: dict[str, Any]) -> str:
    """Produce a human-readable assessment from metrics."""
    if "skip_reason" in metrics:
        return f"SKIPPED: {metrics['skip_reason']}"

    scores = []
    r = metrics.get("pearson_r")
    if r is not None:
        if r > 0.8:
            scores.append(("Pearson", "STRONG", r))
        elif r > 0.5:
            scores.append(("Pearson", "MODERATE", r))
        elif r > 0.2:
            scores.append(("Pearson", "WEAK", r))
        else:
            scores.append(("Pearson", "NONE", r))

    ks = metrics.get("ks_statistic")
    if ks is not None:
        if ks < 0.1:
            scores.append(("KS", "VERY SIMILAR", ks))
        elif ks < 0.2:
            scores.append(("KS", "SIMILAR", ks))
        elif ks < 0.4:
            scores.append(("KS", "DIFFERENT", ks))
        else:
            scores.append(("KS", "VERY DIFFERENT", ks))

    wd = metrics.get("wasserstein_distance")
    if wd is not None:
        if wd < 0.05:
            scores.append(("Wasserstein", "VERY CLOSE", wd))
        elif wd < 0.15:
            scores.append(("Wasserstein", "CLOSE", wd))
        else:
            scores.append(("Wasserstein", "DISTANT", wd))

    oc = metrics.get("overlap_coefficient")
    if oc is not None:
        if oc > 0.7:
            scores.append(("Overlap", "HIGH", oc))
        elif oc > 0.4:
            scores.append(("Overlap", "MEDIUM", oc))
        else:
            scores.append(("Overlap", "LOW", oc))

    parts = [f"{name}={label}({val:.3f})" for name, label, val in scores]
    return " | ".join(parts) if parts else "INSUFFICIENT DATA"


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_summary_table(all_results: dict[str, list[dict]]) -> None:
    """Print human-readable summary to stdout."""
    print("\n" + "=" * 90)
    print("LIQUIDATION MAP SHAPE COMPARISON -- NORMALIZED DISTRIBUTION ANALYSIS")
    print("=" * 90)

    for scenario, comparisons in all_results.items():
        print(f"\n--- {scenario} ---")
        for comp in comparisons:
            pair = comp.get("providers", "?")
            if "skip_reason" in comp:
                print(f"  {pair:30s}  SKIPPED: {comp['skip_reason']}")
                continue

            r = comp.get("pearson_r", "n/a")
            ks = comp.get("ks_statistic", "n/a")
            wd = comp.get("wasserstein_distance", "n/a")
            oc = comp.get("overlap_coefficient", "n/a")
            skew_d = comp.get("skewness_diff", "n/a")
            peak_d = comp.get("peak_mean_distance", "n/a")

            r_str = f"{r:+.4f}" if isinstance(r, float) else str(r)
            ks_str = f"{ks:.4f}" if isinstance(ks, float) else str(ks)
            wd_str = f"{wd:.4f}" if isinstance(wd, float) else str(wd)
            oc_str = f"{oc:.4f}" if isinstance(oc, float) else str(oc)
            skew_str = f"{skew_d:.4f}" if isinstance(skew_d, float) else str(skew_d)
            peak_str = f"{peak_d:.4f}" if isinstance(peak_d, float) else str(peak_d)

            print(f"  {pair:30s}")
            print(f"    Pearson r:         {r_str:>10s}")
            print(f"    KS statistic:      {ks_str:>10s}")
            print(f"    Wasserstein dist:  {wd_str:>10s}")
            print(f"    Overlap coeff:     {oc_str:>10s}")
            print(f"    Skewness diff:     {skew_str:>10s}")
            print(f"    Peak mean dist:    {peak_str:>10s}")
            print(f"    Assessment:        {comp.get('assessment', 'n/a')}")

    print("\n" + "=" * 90)


def print_distribution_summary(distributions: dict[str, LiqDistribution]) -> None:
    """Print summary of loaded distributions."""
    print("\n--- Loaded Distributions ---")
    for key, dist in distributions.items():
        status = "OK" if dist.valid else f"FAILED ({dist.error})"
        if dist.valid:
            nz = int((dist.raw_volumes > 0).sum())
            total_vol = float(dist.raw_volumes.sum())
            p_range = f"[{dist.raw_prices.min():.1f}, {dist.raw_prices.max():.1f}]"
            skew = compute_skewness(dist)
            print(
                f"  {key:25s}  {status:6s}  "
                f"bins={nz:5d}  vol={total_vol:15,.0f}  "
                f"prices={p_range:25s}  skew={skew:+.3f}"
            )
        else:
            print(f"  {key:25s}  {status}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("Loading liquidation data from 3 providers...")
    print(f"  Project root: {PROJECT_ROOT}")

    all_distributions: dict[str, dict[str, LiqDistribution]] = {}
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "description": "Shape comparison of liquidation distributions (normalized)",
        "scenarios": {},
    }

    for scenario_name, cfg in CAPTURES.items():
        print(f"\n=== Loading {scenario_name} ===")
        dists: dict[str, LiqDistribution] = {}

        # Load all 3 providers
        print(f"  Loading CoinAnK ({cfg['timestamp']})...")
        dists["coinank"] = load_coinank(cfg)

        print(f"  Loading CoinGlass ({cfg['timestamp']})...")
        dists["coinglass"] = load_coinglass(cfg)

        print(f"  Loading Rektslug (API)...")
        dists["rektslug"] = load_rektslug(cfg)

        all_distributions[scenario_name] = dists

        # Print load status
        flat: dict[str, LiqDistribution] = {}
        for prov, dist in dists.items():
            key = f"{scenario_name}/{prov}"
            flat[key] = dist
        print_distribution_summary(flat)

    # Compute pairwise comparisons
    all_results: dict[str, list[dict]] = {}
    pairs = [
        ("rektslug", "coinank"),
        ("rektslug", "coinglass"),
        ("coinank", "coinglass"),
    ]

    for scenario_name, dists in all_distributions.items():
        comparisons = []
        for p1, p2 in pairs:
            d1 = dists.get(p1)
            d2 = dists.get(p2)
            if d1 is None or d2 is None:
                comparisons.append({
                    "providers": f"{p1} vs {p2}",
                    "skip_reason": "Provider data not loaded",
                })
                continue

            metrics = compare_pair(d1, d2)
            metrics["assessment"] = assess_similarity(metrics)
            comparisons.append(metrics)

        all_results[scenario_name] = comparisons
        report["scenarios"][scenario_name] = {
            "symbol": CAPTURES[scenario_name]["symbol"],
            "timeframe": CAPTURES[scenario_name]["timeframe"],
            "capture_timestamp": CAPTURES[scenario_name]["timestamp"],
            "providers_loaded": {
                prov: {
                    "valid": dist.valid,
                    "error": dist.error if not dist.valid else None,
                    "nonzero_bins": int((dist.raw_volumes > 0).sum()) if dist.valid else 0,
                    "total_volume": float(dist.raw_volumes.sum()) if dist.valid else 0,
                    "price_range": (
                        [float(dist.raw_prices.min()), float(dist.raw_prices.max())]
                        if dist.valid
                        else None
                    ),
                    "current_price": dist.current_price,
                    "skewness": round(compute_skewness(dist), 4) if dist.valid else None,
                }
                for prov, dist in dists.items()
            },
            "comparisons": comparisons,
        }

    # Global summary
    summary_lines = []
    for scenario_name, comparisons in all_results.items():
        for comp in comparisons:
            if "skip_reason" not in comp:
                summary_lines.append({
                    "scenario": scenario_name,
                    "pair": comp["providers"],
                    "pearson_r": comp.get("pearson_r"),
                    "ks_statistic": comp.get("ks_statistic"),
                    "wasserstein_distance": comp.get("wasserstein_distance"),
                    "overlap_coefficient": comp.get("overlap_coefficient"),
                    "assessment": comp.get("assessment"),
                })
    report["summary"] = summary_lines

    # Save report
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nReport saved to: {REPORT_PATH}")

    # Print table
    print_summary_table(all_results)


if __name__ == "__main__":
    main()
