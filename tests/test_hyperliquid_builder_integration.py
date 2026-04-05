from src.liquidationheatmap.hyperliquid.builder_integration import (
    assign_research_policy_tag,
    detect_builder_gap_failures,
    map_builder_payload_to_artifact,
    normalize_to_canonical_grid,
    strip_cache_references,
)
from src.liquidationheatmap.hyperliquid.snapshot_schema import BucketGrid


def test_v1_is_canonical():
    assert assign_research_policy_tag("v1") == "canonical"


def test_v2_is_shadow_control():
    assert assign_research_policy_tag("v2") == "shadow/control"


def test_experimental_variants():
    for expert_id in ["v3", "v4", "v5"]:
        assert assign_research_policy_tag(expert_id) == "experimental"


def test_existing_builder_payload_maps_without_losing_precision():
    builder_payload = {
        "symbol": "BTCUSDT",
        "snapshot_ts": "2026-04-03T12:00:00Z",
        "reference_price": 60123.456789,
        "bucket_grid": {"min_price": 50000.0, "max_price": 70000.0, "step": 100.0},
        "long_distribution": {"59000.0": 1.23456789},
        "short_distribution": {"61000.0": 9.87654321},
        "source_metadata": {
            "builder_family": "v1_script",
            "input_identity": {},
            "raw_cache_path": "data/cache/some_cache_file.json",
        },
        "generation_metadata": {
            "run_id": "test-run",
            "run_reason": "baseline",
            "run_ts": "2026-04-03T12:00:00Z",
            "last_actual_run_ts": "2026-04-03T12:00:00Z",
            "producer_version": "1.0.0",
        },
    }

    # Strip paths
    builder_payload["source_metadata"] = strip_cache_references(builder_payload["source_metadata"])
    assert "raw_cache_path" not in builder_payload["source_metadata"]

    artifact = map_builder_payload_to_artifact("v1", builder_payload)
    assert artifact.expert_id == "v1"
    assert artifact.research_policy_tag == "canonical"
    assert artifact.reference_price == 60123.456789
    assert artifact.long_distribution["59000.0"] == 1.23456789
    assert artifact.short_distribution["61000.0"] == 9.87654321


def test_explicit_gap_detection_as_failed_decode():
    failures = detect_builder_gap_failures({"error": "unhandled_margin_abstraction"})
    assert failures["reason"] == "unhandled_margin_abstraction"


def test_normalized_onto_common_grid():
    # Suppose canonical grid is step 100, min 50000.
    # Variant has step 50. We want to align and sum up.
    variant_longs = {"59000.0": 1.0, "59050.0": 1.5, "59100.0": 2.0}
    canonical_grid = BucketGrid(min_price=50000.0, max_price=70000.0, step=100.0)

    normalized = normalize_to_canonical_grid(variant_longs, canonical_grid)

    assert normalized["59000.0"] == 2.5  # 59000 and 59050 fall into 59000 bucket
    assert normalized["59100.0"] == 2.0
