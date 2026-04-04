import pytest

from src.liquidationheatmap.hyperliquid.snapshot_schema import (
    validate_artifact,
)


def _build_valid_artifact() -> dict:
    return {
        "expert_id": "v1",
        "symbol": "BTCUSDT",
        "snapshot_ts": "2026-04-03T12:00:00Z",
        "reference_price": 60000.0,
        "bucket_grid": {"min_price": 50000.0, "max_price": 70000.0, "step": 100.0},
        "long_distribution": {"59000.0": 1.5, "58000.0": 2.0},
        "short_distribution": {"61000.0": 1.5, "62000.0": 2.0},
        "research_policy_tag": "canonical",
        "source_metadata": {
            "builder_family": "v1_script",
            "source_path": "data/cache/some_file.json",
            "input_identity": {"content_digest": "abcdef123456"},
        },
        "generation_metadata": {
            "run_id": "run-123",
            "run_reason": "baseline",
            "run_ts": "2026-04-03T12:00:00Z",
            "last_actual_run_ts": "2026-04-03T12:00:00Z",
            "producer_version": "1.0.0",
        },
    }


def test_well_formed_artifact_passes():
    payload = _build_valid_artifact()
    artifact = validate_artifact(payload)
    assert artifact.expert_id == "v1"
    assert artifact.reference_price == 60000.0


def test_missing_required_field_rejected():
    payload = _build_valid_artifact()
    del payload["symbol"]
    with pytest.raises(ValueError, match="Missing required field: symbol"):
        validate_artifact(payload)


def test_malformed_bucket_grid_rejected():
    payload = _build_valid_artifact()
    payload["bucket_grid"] = {"min_price": 50000.0, "step": 100.0}  # missing max_price
    with pytest.raises(ValueError, match="Invalid bucket grid"):
        validate_artifact(payload)


def test_numeric_fields_use_float64():
    # In python, floats are float64. We just verify the type is float
    payload = _build_valid_artifact()
    payload["reference_price"] = 60000  # an int
    # should be coerced to float or validated
    artifact = validate_artifact(payload)
    assert isinstance(artifact.reference_price, float)
    assert isinstance(artifact.bucket_grid.min_price, float)
    assert isinstance(list(artifact.long_distribution.values())[0], float)
