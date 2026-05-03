"""Calibration metadata extraction and labeling for scorecard."""

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel


class CalibrationMetadataEntry(BaseModel):
    kind: Literal["derived", "method_constant", "governance_constant"]
    name: str
    value: Any
    method: str
    input_count: Optional[int] = None
    reason: str


def extract_calibration_metadata(bundle) -> Dict[str, CalibrationMetadataEntry]:
    metadata = {}

    # Method constants
    metadata["bootstrap_iterations"] = CalibrationMetadataEntry(
        kind="method_constant",
        name="bootstrap_iterations",
        value=1000,
        method="fixed_default",
        reason="Statistical significance threshold",
    )

    # Governance constants
    metadata["freshness_sla_secs"] = CalibrationMetadataEntry(
        kind="governance_constant",
        name="freshness_sla_secs",
        value=86400,
        method="fixed_default",
        reason="Maximum allowed artifact age",
    )

    # Derived values
    if getattr(bundle, "adaptive_parameters", None):
        for k, v in bundle.adaptive_parameters.items():
            metadata[k] = CalibrationMetadataEntry(
                kind="derived",
                name=k,
                value=v,
                method="adaptive_inference",
                reason=f"Derived dynamically for {k}",
            )

    return metadata
