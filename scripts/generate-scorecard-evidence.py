#!/usr/bin/env python3
# ruff: noqa: N999,E402
"""CLI entry point for generating scorecard runtime evidence."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.liquidationheatmap.models.scorecard import ExpertScorecardBundle
from src.liquidationheatmap.scorecard.calibration import extract_calibration_metadata
from src.liquidationheatmap.scorecard.pipeline import ScorecardPipeline
from src.liquidationheatmap.scorecard.runtime import (
    SCORECARD_FRESHNESS_SLA_SECS,
    ScorecardArtifactWriter,
    build_scorecard_details,
    classify_quality,
)

logger = logging.getLogger(__name__)


def _load_json_records(path: Path, *, accepted_keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"missing JSON input: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        records = None
        for key in accepted_keys:
            value = payload.get(key)
            if isinstance(value, list):
                records = value
                break
        if records is None:
            raise ValueError(f"{path} must contain one of keys: {', '.join(accepted_keys)}")
    else:
        raise ValueError(f"{path} must contain a JSON list or object")

    if not all(isinstance(record, dict) for record in records):
        raise ValueError(f"{path} must contain JSON objects")
    return records


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate scorecard evidence")
    parser.add_argument(
        "--snapshot-root",
        default="data/validation/expert_snapshots/hyperliquid",
        help="Retained expert snapshot root containing manifests/",
    )
    parser.add_argument(
        "--output-dir",
        default="data/validation/scorecards",
        help="Output directory for latest scorecard artifacts",
    )
    parser.add_argument(
        "--price-path",
        required=True,
        help="Retained price path JSON file. Must be a list or contain price_path/klines_1m_history.",
    )
    parser.add_argument(
        "--liquidation-events",
        default=None,
        help="Optional liquidation confirmation JSON file.",
    )
    parser.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT"])
    parser.add_argument("--experts", nargs="+", default=["v1", "v3", "v4", "v5"])
    parser.add_argument("--limit-manifests", type=int, default=None)
    parser.add_argument("--enable-adaptive", action="store_true", default=True)
    parser.add_argument("--disable-adaptive", dest="enable_adaptive", action="store_false")
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    args = _parse_args()

    snapshot_root = Path(args.snapshot_root)
    if not (snapshot_root / "manifests").exists():
        logger.error("Missing retained snapshot manifests at %s", snapshot_root / "manifests")
        return 1

    try:
        price_path = _load_json_records(
            Path(args.price_path), accepted_keys=("price_path", "klines_1m_history")
        )
        liquidation_events = (
            _load_json_records(
                Path(args.liquidation_events),
                accepted_keys=("liquidation_events", "events", "records"),
            )
            if args.liquidation_events
            else []
        )

        pipeline = ScorecardPipeline(snapshot_root=snapshot_root)
        bundle_json = pipeline.run_from_retained_snapshots(
            price_path=price_path,
            liquidation_events=liquidation_events,
            expected_experts=args.experts,
            symbols=args.symbols,
            limit_manifests=args.limit_manifests,
            enable_adaptive=args.enable_adaptive,
        )
        bundle = ExpertScorecardBundle.model_validate_json(bundle_json)

        output_dir = Path(args.output_dir)
        writer = ScorecardArtifactWriter(base_dir=output_dir)
        artifact_path = output_dir / "latest.json"
        summary_path = output_dir / "latest-summary.json"
        bundle_hash = writer.compute_hash(bundle)
        quality, blocking_issues = classify_quality(
            bundle,
            artifact_age_secs=0,
            max_age_secs=SCORECARD_FRESHNESS_SLA_SECS,
            hash_val=bundle_hash,
            price_path_available=bool(price_path),
            volume_available=any(
                "volume" in tick and tick["volume"] is not None for tick in price_path
            ),
            liquidation_events_available=bool(liquidation_events),
            require_observations=True,
        )
        details = build_scorecard_details(
            bundle=bundle,
            artifact_path=artifact_path,
            summary_path=summary_path,
            generated_at=datetime.now(timezone.utc),
            adaptive_mode=args.enable_adaptive,
            calibration_metadata=extract_calibration_metadata(bundle),
            quality=quality,
            blocking_issues=blocking_issues,
        )

        if blocking_issues:
            logger.error("Blocking scorecard issues: %s", "; ".join(blocking_issues))
            return 1

        writer.write_latest(bundle, details)
        logger.info("Successfully generated scorecard evidence at %s", output_dir)
        return 0
    except Exception:
        logger.exception("Failed to generate scorecard evidence")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
