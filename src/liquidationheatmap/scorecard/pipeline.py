"""End-to-end scorecard bundle generation from retained expert artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.liquidationheatmap.models.scorecard import (
    ExpertScorecardBundle,
    ExpertScorecardSlice,
)
from src.liquidationheatmap.scorecard.aggregator import ScorecardAggregator
from src.liquidationheatmap.scorecard.builder import ScorecardBuilder, _coerce_timestamp
from src.liquidationheatmap.scorecard.slicer import ScorecardSlicer

DEFAULT_SNAPSHOT_ROOT = Path("data/validation/expert_snapshots/hyperliquid")


class ScorecardPipeline:
    """Build machine-readable expert scorecard bundles."""

    def __init__(self, snapshot_root: Path | str = DEFAULT_SNAPSHOT_ROOT):
        self.snapshot_root = Path(snapshot_root)
        self.builder = ScorecardBuilder()
        self.slicer = ScorecardSlicer()
        self.aggregator = ScorecardAggregator()

    def _create_dominance_rows(
        self, slices: list[ExpertScorecardSlice]
    ) -> list[dict[str, Any]]:
        """Create per-slice expert comparison rows without collapsing to one scalar."""
        comparable_groups: dict[str, list[ExpertScorecardSlice]] = {}
        for scorecard_slice in slices:
            dimensions = scorecard_slice.slice_dimensions
            group_key = ":".join(
                [
                    str(dimensions["symbol"]),
                    str(dimensions["side"]),
                    str(dimensions["distance_bucket"]),
                    str(dimensions["confidence_bucket"]),
                    str(dimensions.get("regime", "none")),
                ]
            )
            comparable_groups.setdefault(group_key, []).append(scorecard_slice)

        dominance_rows: list[dict[str, Any]] = []
        for group_key, group_slices in sorted(comparable_groups.items()):
            if len(group_slices) < 2:
                continue
            sorted_group = sorted(group_slices, key=lambda item: item.expert_id)
            best_touch = max(
                sorted_group,
                key=lambda item: (
                    item.touch_probability,
                    item.sample_count,
                    item.expert_id,
                ),
            )
            best_liquidation = max(
                sorted_group,
                key=lambda item: (
                    item.liquidation_match_probability_given_touch,
                    item.liquidation_match_count,
                    item.expert_id,
                ),
            )
            best_mfe = max(
                sorted_group,
                key=lambda item: (
                    item.mfe_quantiles["p50"],
                    item.sample_count,
                    item.expert_id,
                ),
            )
            lowest_mae = min(
                sorted_group,
                key=lambda item: (
                    item.mae_quantiles["p50"],
                    -item.sample_count,
                    item.expert_id,
                ),
            )

            dominance_rows.append(
                {
                    "comparison_slice_id": group_key,
                    "slice_dimensions": dict(sorted_group[0].slice_dimensions),
                    "experts_compared": [
                        scorecard_slice.expert_id for scorecard_slice in sorted_group
                    ],
                    "leaders": {
                        "touch_probability": best_touch.expert_id,
                        "liquidation_match_probability_given_touch": best_liquidation.expert_id,
                        "mfe_p50": best_mfe.expert_id,
                        "mae_p50_lowest": lowest_mae.expert_id,
                    },
                }
            )

        return dominance_rows

    def _build_retained_input_range(
        self, artifacts: list[dict[str, Any]], price_path: list[dict[str, Any]]
    ) -> dict[str, Any]:
        artifact_timestamps = sorted(
            _coerce_timestamp(artifact["snapshot_ts"]) for artifact in artifacts
        )
        price_timestamps = sorted(
            _coerce_timestamp(point["timestamp"]) for point in price_path
        )
        return {
            "artifact_count": len(artifacts),
            "price_ticks": len(price_path),
            "snapshot_ts_min": (
                artifact_timestamps[0].isoformat().replace("+00:00", "Z")
                if artifact_timestamps
                else None
            ),
            "snapshot_ts_max": (
                artifact_timestamps[-1].isoformat().replace("+00:00", "Z")
                if artifact_timestamps
                else None
            ),
            "price_ts_min": (
                price_timestamps[0].isoformat().replace("+00:00", "Z")
                if price_timestamps
                else None
            ),
            "price_ts_max": (
                price_timestamps[-1].isoformat().replace("+00:00", "Z")
                if price_timestamps
                else None
            ),
        }

    def _build_artifact_provenance(
        self, artifacts: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return {
            "snapshot_root": str(self.snapshot_root),
            "artifact_count": len(artifacts),
            "experts": sorted({artifact["expert_id"] for artifact in artifacts}),
            "symbols": sorted({artifact["symbol"] for artifact in artifacts}),
            "liquidation_confirmation_source": (
                "data/validation/liquidation_confirmation_events"
            ),
        }

    def load_retained_artifacts(
        self,
        symbols: list[str] | None = None,
        expert_ids: list[str] | None = None,
        limit_manifests: int | None = None,
    ) -> list[dict[str, Any]]:
        """Historical backfill entry point from retained expert snapshots."""
        manifests_root = self.snapshot_root / "manifests"
        if not manifests_root.exists():
            raise FileNotFoundError(f"Missing manifests root: {manifests_root}")

        requested_symbols = set(symbols or [])
        requested_experts = set(expert_ids or [])
        manifest_paths = sorted(manifests_root.glob("*/*.json"))
        if limit_manifests is not None:
            manifest_paths = manifest_paths[:limit_manifests]

        artifacts: list[dict[str, Any]] = []
        for manifest_path in manifest_paths:
            symbol = manifest_path.parent.name
            if requested_symbols and symbol not in requested_symbols:
                continue

            manifest = json.loads(manifest_path.read_text())
            for expert_id, expert_info in sorted(manifest.get("experts", {}).items()):
                if requested_experts and expert_id not in requested_experts:
                    continue
                if expert_info.get("availability_status") != "available":
                    continue

                artifact_path = self.snapshot_root / expert_info["artifact_path"]
                if not artifact_path.exists():
                    continue
                artifact = json.loads(artifact_path.read_text())
                artifacts.append(artifact)

        return artifacts

    def run(
        self,
        artifacts: list[dict[str, Any]],
        price_path: list[dict[str, Any]],
        liquidation_events: list[dict[str, Any]],
        expected_experts: list[str],
    ) -> str:
        """Run the pipeline end-to-end to generate the bundle JSON."""
        all_observations = []
        for artifact in artifacts:
            all_observations.extend(self.builder.extract_observations(artifact))

        seen_observation_ids: set[str] = set()
        unique_observations = []
        for observation in all_observations:
            if observation.observation_id in seen_observation_ids:
                continue
            seen_observation_ids.add(observation.observation_id)
            unique_observations.append(observation)

        touched_observations = self.builder.apply_touch_detection(
            unique_observations, price_path
        )
        final_observations = self.builder.apply_liquidation_confirmation(
            touched_observations, liquidation_events
        )
        grouped_slices = self.slicer.slice_observations(final_observations)

        scorecard_slices: list[ExpertScorecardSlice] = []
        for slice_id, observations_in_slice in grouped_slices.items():
            if not observations_in_slice:
                continue

            sample_observation = observations_in_slice[0]
            slice_dimensions = self.slicer.get_slice_dimensions(sample_observation)
            probabilities = self.aggregator.aggregate_probabilities(observations_in_slice)
            quantiles = self.aggregator.aggregate_quantiles(observations_in_slice)

            scorecard_slices.append(
                ExpertScorecardSlice(
                    expert_id=sample_observation.expert_id,
                    slice_id=slice_id,
                    slice_dimensions=slice_dimensions,
                    sample_count=probabilities["sample_count"],
                    touch_count=probabilities["touch_count"],
                    touch_probability=probabilities["touch_probability"],
                    liquidation_match_count=probabilities["liquidation_match_count"],
                    liquidation_match_probability_given_touch=probabilities[
                        "liquidation_match_probability_given_touch"
                    ],
                    mfe_quantiles=quantiles["mfe_quantiles"],
                    mae_quantiles=quantiles["mae_quantiles"],
                    time_to_touch_quantiles=quantiles["time_to_touch_quantiles"],
                    time_to_liquidation_confirm_quantiles=quantiles[
                        "time_to_liquidation_confirm_quantiles"
                    ],
                    low_sample_flag=probabilities["low_sample_flag"],
                )
            )

        coverage_gaps = self.builder.build_coverage_metadata(
            expected_experts=expected_experts,
            available_artifacts=artifacts,
            liquidation_stream_available=bool(liquidation_events),
        )

        scorecard_slices.sort(key=lambda scorecard_slice: scorecard_slice.slice_id)
        dominance_rows = self._create_dominance_rows(scorecard_slices)

        bundle = ExpertScorecardBundle(
            slices=scorecard_slices,
            coverage_gaps=coverage_gaps,
            dominance_rows=dominance_rows,
            retained_input_range=self._build_retained_input_range(artifacts, price_path),
            artifact_provenance=self._build_artifact_provenance(artifacts),
        )
        return bundle.model_dump_json(indent=2)

    def run_from_retained_snapshots(
        self,
        price_path: list[dict[str, Any]],
        liquidation_events: list[dict[str, Any]],
        expected_experts: list[str],
        symbols: list[str] | None = None,
        limit_manifests: int | None = None,
    ) -> str:
        """Run the scorecard directly from retained snapshot manifests/artifacts."""
        artifacts = self.load_retained_artifacts(
            symbols=symbols,
            expert_ids=expected_experts,
            limit_manifests=limit_manifests,
        )
        return self.run(
            artifacts=artifacts,
            price_path=price_path,
            liquidation_events=liquidation_events,
            expected_experts=expected_experts,
        )

    def generate_markdown(self, bundle_json: str) -> str:
        """Generate a compact markdown summary for reviewer entry points."""
        bundle = ExpertScorecardBundle.model_validate_json(bundle_json)

        lines = [
            "# Expert Scorecard Summary",
            "",
            "## Coverage Gaps",
        ]

        if bundle.coverage_gaps and bundle.coverage_gaps.get("missing_artifacts"):
            lines.append(
                f"- Missing artifacts: {len(bundle.coverage_gaps['missing_artifacts'])}"
            )
        else:
            lines.append("- No missing artifacts")

        lines.extend(["", "## Slices"])
        for scorecard_slice in bundle.slices:
            lines.append(f"### Slice: {scorecard_slice.slice_id}")
            lines.append(f"- Expert ID: {scorecard_slice.expert_id}")
            lines.append(f"- Sample Count: {scorecard_slice.sample_count}")
            lines.append(
                f"- Touch Probability: {scorecard_slice.touch_probability:.4f}"
            )
            lines.append(
                "- Liquidation Match Probability (given touch): "
                f"{scorecard_slice.liquidation_match_probability_given_touch:.4f}"
            )
            lines.append("")

        if bundle.dominance_rows:
            lines.extend(["## Dominance", ""])
            for dominance_row in bundle.dominance_rows:
                lines.append(
                    f"- {dominance_row['comparison_slice_id']}: "
                    f"{dominance_row['leaders']}"
                )

        return "\n".join(lines)
