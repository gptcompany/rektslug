"""Unit tests for spec-018 calibration helpers."""

import json
from pathlib import Path

from scripts.compare_provider_liquidations import CaptureFile
from scripts.run_ank_calibration import (
    aligned_bucket_overlap,
    extract_bucket_prices_from_manifest,
    run_comparison_for_profile,
)


def test_aligned_bucket_overlap_handles_different_steps():
    local_prices = [100.0, 101.0, 102.0]
    provider_prices = [100.0, 100.5, 101.0, 101.5, 102.0]

    overlap = aligned_bucket_overlap(local_prices, provider_prices)

    assert overlap == 1.0


def test_aligned_bucket_overlap_returns_zero_for_disjoint_ranges():
    local_prices = [100.0, 101.0, 102.0]
    provider_prices = [110.0, 111.0, 112.0]

    overlap = aligned_bucket_overlap(local_prices, provider_prices)

    assert overlap == 0.0


def test_extract_bucket_prices_from_manifest_decodes_coinglass_payload(monkeypatch):
    manifest_path = Path("/tmp/fake-manifest.json")
    capture = CaptureFile(
        provider="coinglass",
        source_url="https://capi.coinglass.com/api/index/5/liqMap?symbol=Binance_BTCUSDT",
        saved_file=Path("/tmp/fake.json"),
        content_type="application/json",
        payload={"data": "encrypted"},
        manifest_path=manifest_path,
    )

    monkeypatch.setattr(
        "scripts.run_ank_calibration.load_capture_files",
        lambda manifest_paths: [capture],
    )
    monkeypatch.setattr(
        "scripts.run_ank_calibration.decode_coinglass_json_payload",
        lambda capture_file: (
            {
                "liqMapV2": {
                    "70000": [[69950, 120.0, 50, 1]],
                    "70100": [[70125, 0.0, 50, 1], [70120, 80.0, 25, 2]],
                    "70200": [[70220, 0.0, 25, 1]],
                }
            },
            ["decoded"],
        ),
    )

    prices = extract_bucket_prices_from_manifest(manifest_path, "coinglass")

    assert prices == [70000.0, 70100.0]


def test_extract_bucket_prices_from_manifest_accepts_public_builder_payload(monkeypatch):
    manifest_path = Path("/tmp/fake-manifest.json")
    capture = CaptureFile(
        provider="rektslug",
        source_url=(
            "http://localhost:8002/liquidations/coinank-public-map"
            "?exchange=bybit&symbol=BTCUSDT&timeframe=1w"
        ),
        saved_file=Path("/tmp/fake.json"),
        content_type="application/json",
        payload={
            "symbol": "BTCUSDT",
            "current_price": 85000.0,
            "long_buckets": [
                {"price_level": 84000.0, "volume": 100.0, "leverage": "25x"},
                {"price_level": 83000.0, "volume": 50.0, "leverage": "50x"},
            ],
            "short_buckets": [
                {"price_level": 86000.0, "volume": 120.0, "leverage": "25x"},
                {"price_level": 87000.0, "volume": 80.0, "leverage": "50x"},
            ],
        },
        manifest_path=manifest_path,
    )

    monkeypatch.setattr(
        "scripts.run_ank_calibration.load_capture_files",
        lambda manifest_paths: [capture],
    )

    prices = extract_bucket_prices_from_manifest(manifest_path, "rektslug")

    assert prices == [83000.0, 84000.0, 86000.0, 87000.0]


def test_run_comparison_for_profile_passes_legacy_surface(monkeypatch, tmp_path: Path):
    import scripts.run_ank_calibration as module

    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({"providers": {"rektslug": {}}}), encoding="utf-8")
    commands: list[list[str]] = []

    def _fake_run(cmd, capture_output, text, timeout):
        commands.append(cmd)

        class _Result:
            stdout = f"comparison report: {report_path}\n"
            stderr = ""

        return _Result()

    monkeypatch.setattr(module, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(module.subprocess, "run", _fake_run)

    resolved = run_comparison_for_profile("BTC", "1d", "rektslug-ank", provider="rektslug")

    assert resolved == report_path
    assert "--surface" in commands[0]
    assert commands[0][commands[0].index("--surface") + 1] == "legacy"
