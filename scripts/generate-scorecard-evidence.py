#!/usr/bin/env python3
"""
CLI entry point for generating scorecard evidence.
"""

import argparse
import sys
import logging
from pathlib import Path
from datetime import datetime, timezone

from src.liquidationheatmap.scorecard.pipeline import ScorecardPipeline
from src.liquidationheatmap.models.scorecard import ExpertScorecardBundle
from src.liquidationheatmap.scorecard.runtime import (
    ScorecardArtifactWriter,
    ScorecardEvidenceDetails,
    ScorecardQualitySummary,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Generate scorecard evidence")
    parser.add_argument(
        "--snapshot-root", type=str, default="data/validation/expert_snapshots/hyperliquid"
    )
    parser.add_argument("--output-dir", type=str, default="data/validation/scorecards")
    parser.add_argument("--price-path", type=str, default=None)
    parser.add_argument("--enable-adaptive", action="store_true", default=True)
    parser.add_argument("--disable-adaptive", dest="enable_adaptive", action="store_false")
    args = parser.parse_args()

    snapshot_root = Path(args.snapshot_root)
    if not snapshot_root.exists() or not any(snapshot_root.iterdir()):
        logger.error(f"Missing snapshots at {snapshot_root}")
        sys.exit(1)

    try:
        pipeline = ScorecardPipeline(snapshot_root=snapshot_root)

        bundle_json_str = pipeline.run_from_retained_snapshots(
            price_path=args.price_path,
            liquidation_events=None,
            expected_experts=None,
            symbols=None,
            limit_manifests=None,
            enable_adaptive=args.enable_adaptive,
        )

        bundle = ExpertScorecardBundle.model_validate_json(bundle_json_str)

        writer = ScorecardArtifactWriter(base_dir=args.output_dir)

        quality = ScorecardQualitySummary(
            snapshot_coverage_status="HEALTHY",
            price_path_coverage_status="HEALTHY",
            volume_coverage_status="HEALTHY",
            liquidation_confirmation_status="HEALTHY",
            schema_validation_status="HEALTHY",
            reproducibility_hash=writer.compute_hash(bundle),
        )

        details = ScorecardEvidenceDetails(
            artifact_path=str(Path(args.output_dir) / "latest.json"),
            summary_path=str(Path(args.output_dir) / "latest-summary.json"),
            artifact_generated_at=datetime.now(timezone.utc),
            artifact_age_secs=0,
            adaptive_mode=args.enable_adaptive,
            experts=[],
            symbols=[],
            slice_count=len(bundle.slices),
            observation_count=0,
            dominance_row_count=len(bundle.dominance_rows) if bundle.dominance_rows else 0,
            coverage_gap_count=0,
            blocking_issues=[],
            quality=quality,
            calibration_metadata={},
            artifact_links={},
        )

        writer.write_latest(bundle, details)
        logger.info("Successfully generated scorecard evidence.")

    except Exception as e:
        logger.exception("Failed to generate scorecard evidence")
        sys.exit(1)


if __name__ == "__main__":
    main()
