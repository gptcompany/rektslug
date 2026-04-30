import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict

TOUCH_WINDOW_HOURS = 4
LIQ_CONFIRM_WINDOW_MINUTES = 15
POST_TOUCH_WINDOW_HOURS = 1
TOUCH_TOLERANCE_BPS = 5

class ExpertSignalObservation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    observation_id: str
    expert_id: str
    symbol: str
    snapshot_ts: int
    level_price: float
    side: str
    confidence: float
    reference_price: float
    distance_bps: int
    touched: bool
    touch_ts: Optional[int] = None
    liquidation_confirmed: Optional[bool] = None
    liquidation_confirm_ts: Optional[int] = None
    mfe_bps: Optional[int] = None
    mae_bps: Optional[int] = None
    time_to_touch_secs: Optional[int] = None
    time_to_liquidation_confirm_secs: Optional[int] = None

    # Optional downstream execution fields
    signal_accepted: Optional[bool] = None
    order_submitted: Optional[bool] = None
    position_opened: Optional[bool] = None
    position_closed: Optional[bool] = None
    feedback_persisted: Optional[bool] = None
    paper_pnl: Optional[float] = None

    @classmethod
    def generate_id(
        cls, expert_id: str, symbol: str, snapshot_ts: int, level_price: float, side: str
    ) -> str:
        """Deterministic UUID5 semantics."""
        name = f"{expert_id}{symbol}{snapshot_ts}{level_price}{side}"
        return str(uuid.uuid5(uuid.NAMESPACE_OID, name))


class ExpertScorecardSlice(BaseModel):
    expert_id: str
    slice_id: str
    slice_dimensions: Dict[str, Any]
    sample_count: int
    touch_count: int
    touch_probability: float
    liquidation_match_count: int
    liquidation_match_probability_given_touch: float
    mfe_quantiles: Dict[str, int]
    mae_quantiles: Dict[str, int]
    time_to_touch_quantiles: Dict[str, int]
    low_sample_flag: bool

    @classmethod
    def generate_slice_id(
        cls,
        expert_id: str,
        symbol: str,
        side: str,
        distance_bucket: str,
        confidence_bucket: str,
        regime: str = "none",
    ) -> str:
        """Slice ID deterministic format per spec."""
        return f"{expert_id}:{symbol}:{side}:{distance_bucket}:{confidence_bucket}:{regime}"


class ExpertScorecardBundle(BaseModel):
    slices: List[ExpertScorecardSlice]
    coverage_gaps: Optional[Dict[str, Any]] = None
    dominance_rows: Optional[List[Dict[str, Any]]] = None
    retained_input_range: Optional[Dict[str, Any]] = None
    artifact_provenance: Optional[Dict[str, Any]] = None
