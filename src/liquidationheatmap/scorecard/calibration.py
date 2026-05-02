"""
Calibration metadata extraction and labeling for scorecard.
"""
from typing import Any, Literal, Optional

from pydantic import BaseModel


class CalibrationMetadataEntry(BaseModel):
    kind: Literal["derived", "method_constant", "governance_constant"]
    name: str
    value: Any
    method: str
    input_count: Optional[int] = None
    reason: str
