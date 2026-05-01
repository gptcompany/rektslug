import json
import pytest
from datetime import datetime, timezone
from src.liquidationheatmap.models.scorecard import ExpertScorecardBundle
from src.liquidationheatmap.scorecard.pipeline import ScorecardPipeline

def test_pipeline_idempotency_and_validation():
    # T022R: append-safe incremental updates
    # T026b: validation against Pydantic schema
    # T026c: reproducibility test (byte-identical)
    pipeline = ScorecardPipeline()
    
    # Mock some basic raw artifacts and price paths
    artifact1 = {
        "expert_id": "v1",
        "symbol": "BTC-USD",
        "snapshot_ts": 1700000000,
        "reference_price": 60000.0,
        "long_distribution": {"59000.0": 800.0}
    }
    artifact2 = {
        "expert_id": "v1",
        "symbol": "BTC-USD",
        "snapshot_ts": 1700003600, # 1 hour later
        "reference_price": 61000.0,
        "long_distribution": {"60000.0": 800.0}
    }
    
    price_path = [
        {"timestamp": 1700000100, "price": 59005.0},
        {"timestamp": 1700003700, "price": 60005.0}
    ]
    liquidation_events = []
    
    # Run 1: Just artifact 1
    bundle1_json = pipeline.run(
        artifacts=[artifact1],
        price_path=price_path,
        liquidation_events=liquidation_events,
        expected_experts=["v1"]
    )
    
    # Run 2: Artifact 1 + Artifact 2
    bundle2_json = pipeline.run(
        artifacts=[artifact1, artifact2],
        price_path=price_path,
        liquidation_events=liquidation_events,
        expected_experts=["v1"]
    )
    
    # Run 3: Same as Run 2
    bundle3_json = pipeline.run(
        artifacts=[artifact1, artifact2],
        price_path=price_path,
        liquidation_events=liquidation_events,
        expected_experts=["v1"]
    )
    
    # Validate against Pydantic schema
    bundle2 = ExpertScorecardBundle.model_validate_json(bundle2_json)
    
    # Check reproducibility
    assert bundle2_json == bundle3_json, "Pipeline must be reproducible and produce byte-identical JSON for the same inputs"
    
    # Check idempotency/append-safe:
    # the number of observations should be 2 for run 2
    total_samples = sum(s.sample_count for s in bundle2.slices)
    assert total_samples == 2
    
def test_markdown_summary_generation():
    pipeline = ScorecardPipeline()
    artifact = {
        "expert_id": "v4",
        "symbol": "ETH-USD",
        "snapshot_ts": 1700000000,
        "reference_price": 2000.0,
        "long_distribution": {"1900.0": 900.0}
    }
    bundle_json = pipeline.run([artifact], [], [], ["v4"])
    
    md_summary = pipeline.generate_markdown(bundle_json)
    assert "Expert Scorecard Summary" in md_summary
    assert "v4" in md_summary
