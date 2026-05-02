"""
Tests for calibration metadata extraction.
"""

from src.liquidationheatmap.models.scorecard import ExpertScorecardBundle
from src.liquidationheatmap.scorecard.calibration import extract_calibration_metadata


def test_calibration_metadata_labels_derived_values():
    """T038: RED: calibration metadata labels derived values"""
    bundle = ExpertScorecardBundle(
        slices=[],
        adaptive_parameters={"touch_band_bps": 25, "volume_threshold": 1.5, "volatility": 0.05},
    )
    metadata = extract_calibration_metadata(bundle)

    assert metadata["touch_band_bps"].kind == "derived"
    assert metadata["volume_threshold"].kind == "derived"


def test_calibration_metadata_labels_method_constants():
    """T039: RED: bootstrap settings labeled method_constant"""
    bundle = ExpertScorecardBundle(slices=[])
    metadata = extract_calibration_metadata(bundle)

    assert metadata["bootstrap_iterations"].kind == "method_constant"
    assert metadata["bootstrap_iterations"].value == 1000


def test_calibration_metadata_labels_governance_constants():
    """T040: RED: freshness SLA labeled governance_constant"""
    bundle = ExpertScorecardBundle(slices=[])
    metadata = extract_calibration_metadata(bundle)

    assert metadata["freshness_sla_secs"].kind == "governance_constant"
    assert metadata["freshness_sla_secs"].value == 86400
