import json
import subprocess
import sys
from pathlib import Path


def _base_cache_payload(*, source: str) -> dict:
    return {
        "source": source,
        "symbol": "BTCUSDT",
        "timeframe": "1w",
        "current_price": 68500.0,
        "mark_price": 68500.0,
        "account_count": 123,
        "generated_at": "2026-04-03T12:05:00Z",
        "grid": {
            "step": 500.0,
            "anchor_price": 68500.0,
            "min_price": 50000.0,
            "max_price": 90000.0,
        },
        "leverage_ladder": ["cross"],
        "long_buckets": [
            {"price_level": 64000.0, "leverage": "cross", "volume": 1000.0},
        ],
        "short_buckets": [
            {"price_level": 72000.0, "leverage": "cross", "volume": 1500.0},
        ],
        "cumulative_long": [{"price_level": 64000.0, "value": 1000.0}],
        "cumulative_short": [{"price_level": 72000.0, "value": 1500.0}],
        "out_of_range_volume": {"long": 0.0, "short": 0.0},
        "source_anchor": "/tmp/hyperliquid-anchor",
        "bin_size": 500.0,
    }


def _write_cache(cache_dir: Path, name: str, payload: dict) -> None:
    (cache_dir / name).write_text(json.dumps(payload), encoding="utf-8")


def _run_producer(*, output_dir: Path, cache_dir: Path, raw_provider_root: Path, snapshot_ts: str):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "src.liquidationheatmap.hyperliquid.producer",
            "--snapshot-ts",
            snapshot_ts,
            "--run-kind",
            "baseline",
            "--output-dir",
            str(output_dir),
            "--cache-dir",
            str(cache_dir),
            "--raw-provider-root",
            str(raw_provider_root),
        ],
        capture_output=True,
        text=True,
    )


def test_producer_writes_available_artifacts_from_cache(tmp_path):
    cache_dir = tmp_path / "cache"
    raw_provider_root = tmp_path / "raw_provider_api"
    output_dir = tmp_path / "output"
    cache_dir.mkdir()
    raw_provider_root.mkdir()

    _write_cache(cache_dir, "hl_sidecar_btcusdt.json", _base_cache_payload(source="hyperliquid-sidecar"))
    _write_cache(
        cache_dir,
        "hl_sidecar_v3_btcusdt.json",
        {
            **_base_cache_payload(source="hyperliquid-sidecar-top-positions"),
            "projection": {"mode": "top_positions_local"},
        },
    )
    _write_cache(
        cache_dir,
        "hl_sidecar_v4_btcusdt.json",
        {
            **_base_cache_payload(source="hyperliquid-sidecar-position-first"),
            "projection": {"mode": "position_first_local"},
        },
    )
    _write_cache(
        cache_dir,
        "hl_sidecar_v5_btcusdt.json",
        {
            **_base_cache_payload(source="hyperliquid-sidecar-risk-first"),
            "projection": {"mode": "risk_first_local"},
        },
    )

    result = _run_producer(
        output_dir=output_dir,
        cache_dir=cache_dir,
        raw_provider_root=raw_provider_root,
        snapshot_ts="2026-04-03T12:00:00Z",
    )
    assert result.returncode == 0, result.stderr or result.stdout

    manifest_path = output_dir / "manifests" / "BTCUSDT" / "2026-04-03T12:00:00Z.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["distribution_normalization"] == "normalized"
    assert manifest["experts"]["v1"]["availability_status"] == "available"
    assert manifest["experts"]["v2"]["availability_status"] == "failed_decode"
    assert manifest["experts"]["v3"]["availability_status"] == "available"
    assert manifest["experts"]["v4"]["availability_status"] == "available"
    assert manifest["experts"]["v5"]["availability_status"] == "available"

    for expert_id in ("v1", "v3", "v4", "v5"):
        artifact_path = output_dir / "artifacts" / "BTCUSDT" / "2026-04-03T12:00:00Z" / f"{expert_id}.json"
        assert artifact_path.exists()

    v1_artifact = json.loads(
        (output_dir / "artifacts" / "BTCUSDT" / "2026-04-03T12:00:00Z" / "v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert v1_artifact["research_policy_tag"] == "canonical"
    assert v1_artifact["bucket_grid"]["min_price"] == 50000.0


def test_producer_rejects_invalid_snapshot_ts(tmp_path):
    cache_dir = tmp_path / "cache"
    raw_provider_root = tmp_path / "raw_provider_api"
    output_dir = tmp_path / "output"
    cache_dir.mkdir()
    raw_provider_root.mkdir()
    _write_cache(cache_dir, "hl_sidecar_btcusdt.json", _base_cache_payload(source="hyperliquid-sidecar"))

    result = _run_producer(
        output_dir=output_dir,
        cache_dir=cache_dir,
        raw_provider_root=raw_provider_root,
        snapshot_ts="2026-04-03 12:00:00",
    )
    assert result.returncode != 0
    assert "snapshot_ts must be UTC ISO8601" in result.stdout


def test_producer_rejects_invalid_run_kind(tmp_path):
    cache_dir = tmp_path / "cache"
    raw_provider_root = tmp_path / "raw_provider_api"
    output_dir = tmp_path / "output"
    cache_dir.mkdir()
    raw_provider_root.mkdir()
    _write_cache(cache_dir, "hl_sidecar_btcusdt.json", _base_cache_payload(source="hyperliquid-sidecar"))

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.liquidationheatmap.hyperliquid.producer",
            "--snapshot-ts",
            "2026-04-03T12:00:00Z",
            "--run-kind",
            "invalid_kind",
            "--output-dir",
            str(output_dir),
            "--cache-dir",
            str(cache_dir),
            "--raw-provider-root",
            str(raw_provider_root),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
