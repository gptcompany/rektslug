import json
from pathlib import Path

from src.liquidationheatmap.models.scorecard import ExpertScorecardBundle
from src.liquidationheatmap.scorecard.pipeline import ScorecardPipeline


def _artifact(
    expert_id: str,
    snapshot_ts: str,
    symbol: str,
    reference_price: float,
    long_distribution: dict[str, float],
) -> dict[str, object]:
    return {
        "expert_id": expert_id,
        "symbol": symbol,
        "snapshot_ts": snapshot_ts,
        "reference_price": reference_price,
        "long_distribution": long_distribution,
        "short_distribution": {},
    }


def test_pipeline_idempotency_validation_and_dominance() -> None:
    pipeline = ScorecardPipeline()
    artifact1 = _artifact(
        "v1",
        "2026-05-01T00:00:00Z",
        "BTCUSDT",
        60000.0,
        {"59000.0": 800.0},
    )
    artifact2 = _artifact(
        "v3",
        "2026-05-01T00:00:00Z",
        "BTCUSDT",
        60000.0,
        {"59000.0": 600.0},
    )
    artifact3 = _artifact(
        "v1",
        "2026-05-01T01:00:00Z",
        "BTCUSDT",
        61000.0,
        {"60000.0": 800.0},
    )

    price_path = [
        {"timestamp": "2026-05-01T00:10:00Z", "price": 59002.0},
        {"timestamp": "2026-05-01T01:10:00Z", "price": 60002.0},
    ]
    liquidation_events = [
        {
            "timestamp": "2026-05-01T00:12:00Z",
            "price": 59003.0,
            "symbol": "BTCUSDT",
            "side": "long",
        }
    ]

    bundle_json = pipeline.run(
        artifacts=[artifact1, artifact2, artifact3],
        price_path=price_path,
        liquidation_events=liquidation_events,
        expected_experts=["v1", "v3"],
    )
    bundle_json_repeat = pipeline.run(
        artifacts=[artifact1, artifact2, artifact3],
        price_path=price_path,
        liquidation_events=liquidation_events,
        expected_experts=["v1", "v3"],
    )

    bundle = ExpertScorecardBundle.model_validate_json(bundle_json)
    assert bundle_json == bundle_json_repeat
    assert sum(scorecard_slice.sample_count for scorecard_slice in bundle.slices) == 3
    assert bundle.dominance_rows
    assert bundle.artifact_provenance["experts"] == ["v1", "v3"]
    assert bundle.retained_input_range["snapshot_ts_min"] == "2026-05-01T00:00:00Z"
    assert any(
        scorecard_slice.time_to_liquidation_confirm_quantiles["p50"] >= 0
        for scorecard_slice in bundle.slices
    )
    assert any(scorecard_slice.mfe_quantiles["p50"] > 0 for scorecard_slice in bundle.slices)


def test_markdown_summary_generation() -> None:
    pipeline = ScorecardPipeline()
    artifact = _artifact(
        "v4",
        "2026-05-01T00:00:00Z",
        "ETHUSDT",
        2000.0,
        {"1900.0": 900.0},
    )
    bundle_json = pipeline.run([artifact], [], [], ["v4"])

    markdown_summary = pipeline.generate_markdown(bundle_json)
    assert "Expert Scorecard Summary" in markdown_summary
    assert "v4" in markdown_summary


def test_load_retained_artifacts_from_snapshot_root(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "expert_snapshots" / "hyperliquid"
    manifests_root = snapshot_root / "manifests" / "BTCUSDT"
    artifacts_root = snapshot_root / "artifacts" / "BTCUSDT" / "2026-05-01T00:00:00Z"
    manifests_root.mkdir(parents=True)
    artifacts_root.mkdir(parents=True)

    manifest = {
        "snapshot_ts": "2026-05-01T00:00:00Z",
        "experts": {
            "v1": {
                "expert_id": "v1",
                "availability_status": "available",
                "artifact_path": "artifacts/BTCUSDT/2026-05-01T00:00:00Z/v1.json",
            },
            "v3": {
                "expert_id": "v3",
                "availability_status": "unavailable",
                "artifact_path": "artifacts/BTCUSDT/2026-05-01T00:00:00Z/v3.json",
            },
        },
    }
    (manifests_root / "2026-05-01T00:00:00Z.json").write_text(json.dumps(manifest))
    artifact = _artifact(
        "v1",
        "2026-05-01T00:00:00Z",
        "BTCUSDT",
        60000.0,
        {"59000.0": 800.0},
    )
    (artifacts_root / "v1.json").write_text(json.dumps(artifact))

    pipeline = ScorecardPipeline(snapshot_root=snapshot_root)
    loaded_artifacts = pipeline.load_retained_artifacts(
        symbols=["BTCUSDT"], expert_ids=["v1", "v3"]
    )

    assert loaded_artifacts == [artifact]


def test_pipeline_adaptive_mode() -> None:
    pipeline = ScorecardPipeline()
    artifact1 = _artifact("v1", "2026-05-01T00:00:00Z", "BTCUSDT", 60000.0, {"59900.0": 800.0})
    artifact2 = _artifact("v3", "2026-05-01T00:00:00Z", "BTCUSDT", 60000.0, {"59900.0": 600.0})

    # Need enough price history for adaptive features
    price_path = [
        {
            "timestamp": f"2026-05-01T00:{i:02d}:00Z",
            "price": 60000.0 + (i % 2) * 20.0,
            "volume": 1000.0,
        }
        for i in range(60)
    ]

    bundle_json = pipeline.run(
        artifacts=[artifact1, artifact2],
        price_path=price_path,
        liquidation_events=[],
        expected_experts=["v1", "v3"],
        enable_adaptive=True,
    )

    bundle = ExpertScorecardBundle.model_validate_json(bundle_json)

    # Check adaptive features are present
    assert bundle.adaptive_parameters is not None
    assert "volume_threshold" in bundle.adaptive_parameters
    assert "distance_buckets" in bundle.adaptive_parameters

    # Check slices have bucket boundaries
    for s in bundle.slices:
        assert s.bucket_boundaries is not None

    # Check dominance rows have structured bootstrap payload
    for row in bundle.dominance_rows:
        # T051 says preserve field name, but can be bootstrap shape
        # Actually the spec says "its row payloads MAY be tightened to the structured bootstrap-comparison shape"
        # Let's check for bootstrap fields if they exist
        if "p_a_better" in row:
            assert "significant" in row
            assert "ci_lower" in row


def test_pipeline_backward_compatibility() -> None:
    pipeline = ScorecardPipeline()
    artifact = _artifact("v1", "2026-05-01T00:00:00Z", "BTCUSDT", 60000.0, {"59900.0": 800.0})
    price_path = [{"timestamp": "2026-05-01T00:05:00Z", "price": 59901.0}]

    # Run with default (False)
    bundle_json_legacy = pipeline.run([artifact], price_path, [], ["v1"])
    bundle_legacy = json.loads(bundle_json_legacy)

    # Check that new fields are absent or null in legacy mode
    assert bundle_legacy.get("adaptive_parameters") is None
    for s in bundle_legacy["slices"]:
        assert s.get("bucket_boundaries") is None
        # ExpertSignalObservation fields are not visible in bundle.slices usually,
        # but let's check slice dimensions
        assert s["slice_dimensions"]["regime"] == "none"
        assert s["slice_dimensions"]["distance_bucket"] == "0-25"  # default for 16 bps
