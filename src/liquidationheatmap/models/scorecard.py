"""Pydantic contracts for Hyperliquid expert probabilistic scorecards."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

TOUCH_WINDOW_HOURS = 4
LIQ_CONFIRM_WINDOW_MINUTES = 15
POST_TOUCH_WINDOW_HOURS = 1
TOUCH_TOLERANCE_BPS = 5
LIQUIDATION_CONFIRMATION_SOURCE = "data/validation/liquidation_confirmation_events"

class ExpertSignalObservation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    observation_id: str
    expert_id: str
    symbol: str
    snapshot_ts: datetime
    level_price: float = Field(gt=0)
    side: Literal["long", "short"]
    confidence: float = Field(ge=0.0, le=1.0)
    reference_price: float = Field(gt=0)
    distance_bps: int = Field(ge=0)
    touched: bool
    touch_ts: Optional[datetime] = None
    liquidation_confirmed: Optional[bool] = None
    liquidation_confirm_ts: Optional[datetime] = None
    mfe_bps: Optional[int] = Field(default=None, ge=0)
    mae_bps: Optional[int] = Field(default=None, ge=0)
    time_to_touch_secs: Optional[int] = Field(default=None, ge=0)
    time_to_liquidation_confirm_secs: Optional[int] = Field(default=None, ge=0)

    # Optional adaptive fields
    adaptive_touch_band_bps: Optional[int] = None
    local_volatility_bps: Optional[int] = None
    volume_at_touch: Optional[float] = None
    volume_window_complete: Optional[bool] = None
    post_touch_volume: Optional[float] = None
    inferred_regime: Optional[str] = None

    # Optional downstream execution fields
    signal_accepted: Optional[bool] = None
    order_submitted: Optional[bool] = None
    position_opened: Optional[bool] = None
    position_closed: Optional[bool] = None
    feedback_persisted: Optional[bool] = None
    paper_pnl: Optional[float] = None

    @classmethod
    def generate_id(
        cls,
        expert_id: str,
        symbol: str,
        snapshot_ts: datetime,
        level_price: float,
        side: str,
    ) -> str:
        """Deterministic UUID5 semantics."""
        ts_value = snapshot_ts.isoformat()
        name = f"{expert_id}{symbol}{ts_value}{level_price}{side}"
        return str(uuid.uuid5(uuid.NAMESPACE_OID, name))

    @model_validator(mode="after")
    def validate_contract(self) -> "ExpertSignalObservation":
        expected_id = self.generate_id(
            self.expert_id,
            self.symbol,
            self.snapshot_ts,
            self.level_price,
            self.side,
        )
        if self.observation_id != expected_id:
            raise ValueError("observation_id does not match deterministic scorecard contract")

        if self.touched and self.touch_ts is None:
            raise ValueError("touch_ts is required when touched=true")
        if not self.touched and self.touch_ts is not None:
            raise ValueError("touch_ts must be null when touched=false")
        if self.liquidation_confirmed and self.liquidation_confirm_ts is None:
            raise ValueError(
                "liquidation_confirm_ts is required when liquidation_confirmed=true"
            )
        if self.touch_ts is not None and self.touch_ts < self.snapshot_ts:
            raise ValueError("touch_ts cannot be earlier than snapshot_ts")
        if (
            self.liquidation_confirm_ts is not None
            and self.touch_ts is not None
            and self.liquidation_confirm_ts < self.touch_ts
        ):
            raise ValueError("liquidation_confirm_ts cannot be earlier than touch_ts")
        return self


class ExpertScorecardSlice(BaseModel):
    expert_id: str
    slice_id: str
    slice_dimensions: Dict[str, Any]
    sample_count: int = Field(ge=0)
    touch_count: int = Field(ge=0)
    touch_probability: float = Field(ge=0.0, le=1.0)
    liquidation_match_count: int = Field(ge=0)
    liquidation_match_probability_given_touch: float = Field(ge=0.0, le=1.0)
    mfe_quantiles: Dict[str, int]
    mae_quantiles: Dict[str, int]
    time_to_touch_quantiles: Dict[str, int]
    time_to_liquidation_confirm_quantiles: Dict[str, int]
    low_sample_flag: bool
    bucket_boundaries: Optional[Dict[str, Any]] = None

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

    @model_validator(mode="after")
    def validate_contract(self) -> "ExpertScorecardSlice":
        required_keys = ("symbol", "side", "distance_bucket", "confidence_bucket")
        missing = [key for key in required_keys if key not in self.slice_dimensions]
        if missing:
            raise ValueError(f"slice_dimensions missing required keys: {', '.join(missing)}")

        regime = str(self.slice_dimensions.get("regime", "none"))
        expected_id = self.generate_slice_id(
            expert_id=self.expert_id,
            symbol=str(self.slice_dimensions["symbol"]),
            side=str(self.slice_dimensions["side"]),
            distance_bucket=str(self.slice_dimensions["distance_bucket"]),
            confidence_bucket=str(self.slice_dimensions["confidence_bucket"]),
            regime=regime,
        )
        if self.slice_id != expected_id:
            raise ValueError("slice_id does not match deterministic scorecard contract")
        if self.touch_count > self.sample_count:
            raise ValueError("touch_count cannot exceed sample_count")
        if self.liquidation_match_count > self.touch_count:
            raise ValueError("liquidation_match_count cannot exceed touch_count")
        for quantile_map_name in (
            "mfe_quantiles",
            "mae_quantiles",
            "time_to_touch_quantiles",
            "time_to_liquidation_confirm_quantiles",
        ):
            quantile_map = getattr(self, quantile_map_name)
            if any(value < 0 for value in quantile_map.values()):
                raise ValueError(f"{quantile_map_name} cannot contain negative values")
        return self


class QuantileBucketSet(BaseModel):
    metric_name: str
    n_buckets: int = Field(gt=0)
    boundaries: List[float]
    labels: List[str]
    observation_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_contract(self) -> "QuantileBucketSet":
        if len(self.boundaries) != self.n_buckets + 1:
            raise ValueError("boundaries must have length n_buckets + 1")
        if len(self.labels) != self.n_buckets:
            raise ValueError("labels must have length n_buckets")
        if any(
            self.boundaries[index] > self.boundaries[index + 1]
            for index in range(len(self.boundaries) - 1)
        ):
            raise ValueError("boundaries must be monotonically non-decreasing")
        return self


class BootstrapDominanceResult(BaseModel):
    expert_a: str
    expert_b: str
    metric: str
    p_a_better: float = Field(ge=0.0, le=1.0)
    significant: bool
    ci_lower: float = Field(ge=0.0, le=1.0)
    ci_upper: float = Field(ge=0.0, le=1.0)
    n_bootstrap: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_contract(self) -> "BootstrapDominanceResult":
        if self.ci_lower > self.ci_upper:
            raise ValueError("ci_lower cannot exceed ci_upper")
        if not self.ci_lower <= self.p_a_better <= self.ci_upper:
            raise ValueError("p_a_better must lie within the confidence interval")
        return self


class ExpertScorecardBundle(BaseModel):
    slices: List[ExpertScorecardSlice]
    coverage_gaps: Optional[Dict[str, Any]] = None
    dominance_rows: Optional[List[Dict[str, Any]]] = None
    retained_input_range: Optional[Dict[str, Any]] = None
    artifact_provenance: Optional[Dict[str, Any]] = None
    adaptive_parameters: Optional[Dict[str, Any]] = None
