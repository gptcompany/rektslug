#!/usr/bin/env python3
"""Check Hyperliquid backfill batch health for lightweight ops monitoring."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_OUTPUT_DIR = Path("data/validation/expert_snapshots/hyperliquid")


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Batch record must be a JSON object: {path}")
    return payload


def _resolve_batch_path(
    *,
    batch_path: Path | None,
    output_dir: Path,
    batch_id: str | None,
) -> Path:
    if batch_path is not None:
        return batch_path
    batch_dir = output_dir / "batches"
    if batch_id:
        return batch_dir / f"{batch_id}.json"

    candidates = sorted(batch_dir.glob("*.json"), key=lambda path: path.stat().st_mtime)
    if not candidates:
        raise FileNotFoundError(f"No batch records found under {batch_dir}")
    return candidates[-1]


def _coverage_total(coverage: dict[str, Any], status: str) -> int:
    total = 0
    for symbol_coverage in coverage.values():
        if isinstance(symbol_coverage, dict):
            total += int(symbol_coverage.get(status, 0))
    return total


def evaluate_batch(
    payload: dict[str, Any],
    *,
    min_results: int,
    max_failures: int,
    max_partials: int,
    max_gaps: int,
    max_anchor_resolution_failures: int | None,
    require_completed: bool,
) -> list[str]:
    """Return a list of health violations for a backfill batch record."""
    errors: list[str] = []
    metadata = payload.get("generation_metadata", {})
    if not isinstance(metadata, dict):
        errors.append("generation_metadata must be an object")
        metadata = {}

    status = metadata.get("status")
    if require_completed and status != "completed":
        errors.append(f"batch status is {status!r}, expected 'completed'")

    results_count = int(metadata.get("results_count", 0) or 0)
    if results_count < min_results:
        errors.append(f"results_count={results_count} below min_results={min_results}")

    coverage = payload.get("coverage", {})
    if not isinstance(coverage, dict) or not coverage:
        errors.append("coverage is missing or empty")
        coverage = {}

    failures = _coverage_total(coverage, "failure")
    partials = _coverage_total(coverage, "partial")
    gaps = _coverage_total(coverage, "gap")
    if failures > max_failures:
        errors.append(f"failure coverage={failures} exceeds max_failures={max_failures}")
    if partials > max_partials:
        errors.append(f"partial coverage={partials} exceeds max_partials={max_partials}")
    if gaps > max_gaps:
        errors.append(f"gap coverage={gaps} exceeds max_gaps={max_gaps}")

    input_identity = payload.get("input_identity", {})
    if not isinstance(input_identity, dict):
        errors.append("input_identity must be an object")
        input_identity = {}

    anchor_failures = input_identity.get("anchor_resolution_failures", [])
    anchor_failure_total = input_identity.get("anchor_resolution_failures_total")
    anchor_failure_count: int
    if anchor_failure_total is None:
        anchor_failure_count = len(anchor_failures) if isinstance(anchor_failures, list) else 0
        if (
            max_anchor_resolution_failures is not None
            and isinstance(anchor_failures, list)
            and anchor_failure_count >= 100
        ):
            errors.append(
                "anchor_resolution_failures may be truncated at 100 and "
                "anchor_resolution_failures_total is missing"
            )
    else:
        anchor_failure_count = int(anchor_failure_total)
    if (
        max_anchor_resolution_failures is not None
        and anchor_failure_count > max_anchor_resolution_failures
    ):
        errors.append(
            "anchor_resolution_failures="
            f"{anchor_failure_count} exceeds max_anchor_resolution_failures="
            f"{max_anchor_resolution_failures}"
        )

    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Hyperliquid backfill batch health")
    parser.add_argument("--batch-path", type=Path, help="Specific batch JSON path")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--batch-id", help="Batch id under <output-dir>/batches")
    parser.add_argument("--min-results", type=int, default=1)
    parser.add_argument("--max-failures", type=int, default=0)
    parser.add_argument("--max-partials", type=int, default=0)
    parser.add_argument("--max-gaps", type=int, default=0)
    parser.add_argument("--max-anchor-resolution-failures", type=int)
    parser.add_argument(
        "--allow-running",
        action="store_true",
        help="Do not fail when generation_metadata.status is running",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable summary")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    batch_path = _resolve_batch_path(
        batch_path=args.batch_path,
        output_dir=args.output_dir,
        batch_id=args.batch_id,
    )
    payload = _load_json(batch_path)
    errors = evaluate_batch(
        payload,
        min_results=args.min_results,
        max_failures=args.max_failures,
        max_partials=args.max_partials,
        max_gaps=args.max_gaps,
        max_anchor_resolution_failures=args.max_anchor_resolution_failures,
        require_completed=not args.allow_running,
    )
    metadata = payload.get("generation_metadata", {})
    summary = {
        "ok": not errors,
        "batch_path": str(batch_path),
        "status": metadata.get("status") if isinstance(metadata, dict) else None,
        "results_count": metadata.get("results_count", 0) if isinstance(metadata, dict) else 0,
        "errors": errors,
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    elif errors:
        print(f"Backfill batch unhealthy: {batch_path}", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
    else:
        print(f"Backfill batch healthy: {batch_path}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
