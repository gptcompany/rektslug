from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.compare_hl_sidecar_variants import generate_report, slice_distribution
from scripts.compare_hl_sidecar_vs_coinglass import BucketedDistribution


def _build_distribution(source: str, long_buckets: dict[float, float], short_buckets: dict[float, float]) -> BucketedDistribution:
    dist = BucketedDistribution(
        source=source,
        symbol="BTC",
        bin_size=100.0,
        current_price=1_000.0,
        account_count=10,
        position_count=len(long_buckets) + len(short_buckets),
        display_min_price=600.0,
        display_max_price=1_400.0,
    )
    dist.long_buckets = dict(long_buckets)
    dist.short_buckets = dict(short_buckets)
    return dist


def test_slice_distribution_filters_buckets_and_updates_totals() -> None:
    base = _build_distribution(
        "v1",
        long_buckets={800.0: 50.0, 900.0: 100.0, 1_100.0: 200.0},
        short_buckets={1_200.0: 80.0, 1_300.0: 40.0, 900.0: 20.0},
    )

    sliced = slice_distribution(base, 850.0, 1_150.0)

    assert sliced.long_buckets == {900.0: 100.0, 1_100.0: 200.0}
    assert sliced.short_buckets == {900.0: 20.0, 1_200.0: 80.0}
    assert sliced.display_min_price == 850.0
    assert sliced.display_max_price == 1_150.0
    assert sliced.account_count == base.account_count
    assert sliced.position_count == base.position_count


def test_generate_report_creates_global_and_window_sections(monkeypatch, tmp_path: Path) -> None:
    variant_map = {
        "v1": _build_distribution("v1", {900.0: 100.0, 1_000.0: 150.0}, {1_100.0: 80.0}),
        "v2": _build_distribution("v2", {900.0: 120.0, 1_000.0: 140.0}, {1_100.0: 60.0}),
        "v5": _build_distribution("v5", {900.0: 110.0, 1_000.0: 160.0}, {1_100.0: 70.0}),
    }

    def fake_loader(path: Path) -> BucketedDistribution:
        return variant_map[path.stem]

    monkeypatch.setattr(
        "scripts.compare_hl_sidecar_variants.load_sidecar_artifact", fake_loader
    )

    report_path = tmp_path / "report.json"
    report = generate_report(
        symbol="BTC",
        variant_paths={name: Path(f"{name}.json") for name in variant_map},
        output_path=report_path,
        mark_price=1_000.0,
        window_percents=(5,),
    )

    assert report_path.exists()
    assert report["metadata"]["symbol"] == "BTC"
    assert set(report["global"].keys()) == {"v1_vs_v2", "v1_vs_v5", "v2_vs_v5"}
    assert "pct_5" in report["windows"]
    window = report["windows"]["pct_5"]
    assert set(window["variants"].keys()) == {"v1", "v2", "v5"}
    assert "v1_vs_v2" in window["pairwise"]


def test_cli_integration_generates_json_output(tmp_path: Path) -> None:
    base_payload = {
        "source": "hyperliquid-sidecar",
        "symbol": "BTCUSDT",
        "current_price": 1_000.0,
        "bin_size": 100.0,
        "account_count": 1,
        "grid": {"min_price": 500.0, "max_price": 1_500.0},
        "long_buckets": [
            {"price_level": 900.0, "volume": 100.0},
            {"price_level": 1_000.0, "volume": 150.0},
        ],
        "short_buckets": [
            {"price_level": 1_100.0, "volume": 80.0},
        ],
    }

    variant_paths: dict[str, Path] = {}
    for name, multiplier in ("v1", 1.0), ("v2", 1.1), ("v5", 0.9):
        payload = json.loads(json.dumps(base_payload))
        for entry in payload["long_buckets"]:
            entry["volume"] *= multiplier
        for entry in payload["short_buckets"]:
            entry["volume"] *= multiplier
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        variant_paths[name] = path

    output_path = tmp_path / "variant_report.json"
    cmd = [
        sys.executable,
        "scripts/compare_hl_sidecar_variants.py",
        "--symbol",
        "BTC",
        "--cache-v1",
        str(variant_paths["v1"]),
        "--cache-v2",
        str(variant_paths["v2"]),
        "--cache-v5",
        str(variant_paths["v5"]),
        "--output",
        str(output_path),
        "--windows",
        "5",
    ]

    subprocess.run(cmd, check=True)

    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["metadata"]["symbol"] == "BTC"
    assert "global" in data and "windows" in data
    assert "pct_5" in data["windows"]
