"""Hyperliquid Expert Snapshot Producer orchestration script."""

import argparse
import sys
from datetime import datetime, timezone

from src.liquidationheatmap.hyperliquid.export_layout import (
    build_manifest,
    write_expert_artifact,
    write_manifest,
)
from src.liquidationheatmap.hyperliquid.run_metadata import RunKind, build_run_metadata

# In a real run, this would invoke the precompute_hl_sidecar logic.
# For this producer contract implementation, we provide the orchestration shell.


def get_current_utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def produce_snapshots(
    snapshot_ts: str,
    run_kind: str,
    output_dir: str = "data/validation/expert_snapshots/hyperliquid",
    last_actual_run_ts: str | None = None,
) -> None:
    """Orchestrate the builder and write out the manifest layout."""

    current_ts = get_current_utc_ts()
    if not last_actual_run_ts:
        last_actual_run_ts = current_ts

    try:
        run_kind_enum = RunKind(run_kind)
    except ValueError:
        print(f"Error: Invalid run-kind '{run_kind}'. Must be one of {[k.value for k in RunKind]}")
        sys.exit(1)

    # We would use run_meta for the artifacts/manifest
    _run_meta = build_run_metadata(
        run_reason=run_kind_enum, run_ts=current_ts, last_actual_run_ts=last_actual_run_ts
    )

    # Placeholder for actual builder invocations.
    # E.g. results = precompute_hl_sidecar.build_v1(snapshot_ts)

    # We would build artifacts and failures here.
    experts = []
    failures = {}

    manifest = build_manifest(snapshot_ts=snapshot_ts, experts=experts, failures=failures)

    # Since we have no actual builders wired in the test suite yet, we just write the empty manifest.
    write_manifest(output_dir, "BTCUSDT", manifest)

    for expert in experts:
        write_expert_artifact(
            output_dir, expert.symbol, snapshot_ts, expert.expert_id, expert.__dict__
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Produce Hyperliquid expert snapshots")
    parser.add_argument(
        "--snapshot-ts", required=True, help="Canonical evaluation timestamp (ISO8601 Z)"
    )
    parser.add_argument("--run-kind", required=True, help="baseline, extra, manual, or backfill")
    parser.add_argument(
        "--output-dir",
        default="data/validation/expert_snapshots/hyperliquid",
        help="Export root directory",
    )

    args = parser.parse_args()

    produce_snapshots(
        snapshot_ts=args.snapshot_ts, run_kind=args.run_kind, output_dir=args.output_dir
    )


if __name__ == "__main__":
    main()
