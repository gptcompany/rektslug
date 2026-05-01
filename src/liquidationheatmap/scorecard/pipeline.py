import json
from typing import List, Dict, Any, Optional

from src.liquidationheatmap.models.scorecard import (
    ExpertScorecardBundle,
    ExpertScorecardSlice,
    ExpertSignalObservation
)
from src.liquidationheatmap.scorecard.builder import ScorecardBuilder
from src.liquidationheatmap.scorecard.slicer import ScorecardSlicer
from src.liquidationheatmap.scorecard.aggregator import ScorecardAggregator

class ScorecardPipeline:
    def __init__(self):
        self.builder = ScorecardBuilder()
        self.slicer = ScorecardSlicer()
        self.aggregator = ScorecardAggregator()
        
    def _create_dominance_rows(self, slices: List[ExpertScorecardSlice]) -> List[Dict[str, Any]]:
        # Expert vs Expert comparison
        dominance_rows = []
        return dominance_rows

    def run(
        self,
        artifacts: List[Dict[str, Any]],
        price_path: List[Dict[str, Any]],
        liquidation_events: List[Dict[str, Any]],
        expected_experts: List[str]
    ) -> str:
        """Run the pipeline end-to-end to generate the JSON bundle string."""
        all_observations = []
        
        # 1. Build observations
        for artifact in artifacts:
            obs_list = self.builder.extract_observations(artifact)
            all_observations.extend(obs_list)
            
        # Optional: Deduplicate by observation_id (Idempotency / Append-safe)
        seen = set()
        unique_observations = []
        for obs in all_observations:
            if obs.observation_id not in seen:
                seen.add(obs.observation_id)
                unique_observations.append(obs)
                
        # 2. Touch detection
        touched_obs = self.builder.apply_touch_detection(unique_observations, price_path)
        
        # 3. Liquidation confirmation
        final_obs = self.builder.apply_liquidation_confirmation(touched_obs, liquidation_events)
        
        # 4. Slice observations
        grouped_slices = self.slicer.slice_observations(final_obs)
        
        # 5. Aggregate metrics per slice
        scorecard_slices = []
        for slice_id, obs_in_slice in grouped_slices.items():
            if not obs_in_slice:
                continue
                
            sample_obs = obs_in_slice[0]
            expert_id = sample_obs.expert_id
            
            # Reconstruct dimensions from grouped observations
            dist_bucket = self.slicer._get_distance_bucket(sample_obs.distance_bps)
            conf_bucket = self.slicer._get_confidence_bucket(sample_obs.confidence)
            regime = self.slicer.regime_map.get(sample_obs.snapshot_ts, "none")
            
            slice_dimensions = {
                "symbol": sample_obs.symbol,
                "side": sample_obs.side,
                "distance_bucket": dist_bucket,
                "confidence_bucket": conf_bucket,
                "regime": regime
            }
            
            probs = self.aggregator.aggregate_probabilities(obs_in_slice)
            quants = self.aggregator.aggregate_quantiles(obs_in_slice)
            
            slc = ExpertScorecardSlice(
                expert_id=expert_id,
                slice_id=slice_id,
                slice_dimensions=slice_dimensions,
                sample_count=probs["sample_count"],
                touch_count=probs["touch_count"],
                touch_probability=probs["touch_probability"],
                liquidation_match_count=probs["liquidation_match_count"],
                liquidation_match_probability_given_touch=probs["liquidation_match_probability_given_touch"],
                mfe_quantiles=quants["mfe_quantiles"],
                mae_quantiles=quants["mae_quantiles"],
                time_to_touch_quantiles=quants["time_to_touch_quantiles"],
                low_sample_flag=probs["low_sample_flag"]
            )
            scorecard_slices.append(slc)
            
        # 6. Build coverage metadata
        coverage_gaps = self.builder.build_coverage_metadata(
            expected_experts=expected_experts,
            available_artifacts=artifacts,
            liquidation_stream_available=True if liquidation_events else False
        )
        
        # 7. Dominance rows
        # Ensure slices are sorted for reproducibility
        scorecard_slices.sort(key=lambda s: s.slice_id)
        dominance_rows = self._create_dominance_rows(scorecard_slices)
        
        bundle = ExpertScorecardBundle(
            slices=scorecard_slices,
            coverage_gaps=coverage_gaps,
            dominance_rows=dominance_rows,
            retained_input_range={"artifact_count": len(artifacts), "price_ticks": len(price_path)},
            artifact_provenance={"version": "1.0"}
        )
        
        return bundle.model_dump_json(indent=2)
        
    def generate_markdown(self, bundle_json: str) -> str:
        """Generate a compact markdown summary for reviewer entry points."""
        bundle = ExpertScorecardBundle.model_validate_json(bundle_json)
        
        lines = [
            "# Expert Scorecard Summary",
            "",
            "## Coverage Gaps",
        ]
        
        if bundle.coverage_gaps and bundle.coverage_gaps.get("missing_artifacts"):
            lines.append(f"- Missing artifacts: {len(bundle.coverage_gaps['missing_artifacts'])}")
        else:
            lines.append("- No missing artifacts")
            
        lines.extend(["", "## Slices"])
        for slc in bundle.slices:
            lines.append(f"### Slice: {slc.slice_id}")
            lines.append(f"- Expert ID: {slc.expert_id}")
            lines.append(f"- Sample Count: {slc.sample_count}")
            lines.append(f"- Touch Probability: {slc.touch_probability:.4f}")
            lines.append(f"- Liquidation Match Probability (given touch): {slc.liquidation_match_probability_given_touch:.4f}")
            lines.append("")
            
        return "\n".join(lines)
