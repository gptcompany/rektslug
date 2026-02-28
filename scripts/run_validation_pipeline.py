#!/usr/bin/env python3
"""Unified validation pipeline CLI.

Run the complete validation pipeline with configurable options.
Supports backtest validation, Coinglass comparison (informational),
and outputs results in JSON/markdown formats.

Usage:
    # Run default backtest validation
    uv run python scripts/run_validation_pipeline.py

    # Run with custom parameters
    uv run python scripts/run_validation_pipeline.py --symbol BTCUSDT --tolerance 1.5

    # Save results to file
    uv run python scripts/run_validation_pipeline.py --output reports/pipeline_result.json

    # Specify date range
    uv run python scripts/run_validation_pipeline.py --start-date 2024-11-01 --end-date 2024-12-31
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from src.validation.pipeline.models import (
    GateDecision,
    PipelineStatus,
)
from src.validation.pipeline.orchestrator import run_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run unified validation pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Gate 2 Decision Thresholds:
    F1 >= 60%: PASS - Model validated, proceed to production
    F1 >= 40%: ACCEPTABLE - Document limitations
    F1 < 40%:  FAIL - Model rework required

Examples:
    # Basic usage (last 30 days)
    uv run python scripts/run_validation_pipeline.py

    # Custom date range
    uv run python scripts/run_validation_pipeline.py \\
        --start-date 2024-11-01 --end-date 2024-12-31

    # Multiple tolerance levels
    uv run python scripts/run_validation_pipeline.py --sweep-tolerance

    # Save JSON output
    uv run python scripts/run_validation_pipeline.py \\
        --output reports/validation_result.json
        """,
    )

    parser.add_argument(
        "--symbol",
        default="BTCUSDT",
        help="Trading pair symbol (default: BTCUSDT)",
    )
    parser.add_argument(
        "--validation-types",
        default="backtest",
        help="Comma-separated types: backtest,coinglass,realtime,full",
    )
    parser.add_argument(
        "--start-date",
        help="Start date for backtest (YYYY-MM-DD). Default: 30 days ago",
    )
    parser.add_argument(
        "--end-date",
        help="End date for backtest (YYYY-MM-DD). Default: yesterday",
    )
    parser.add_argument(
        "--tolerance-pct",
        type=float,
        default=2.0,
        help="Price tolerance percentage for matching (default: 2.0)",
    )
    parser.add_argument(
        "--sweep-tolerance",
        action="store_true",
        help="Run with multiple tolerance levels (0.5%%, 1%%, 2%%)",
    )
    parser.add_argument(
        "--horizon",
        type=int,
        default=60,
        help="Prediction horizon in minutes (default: 60)",
    )
    parser.add_argument(
        "--output",
        help="Output JSON file path for results",
    )
    parser.add_argument(
        "--report-dir",
        default="reports",
        help="Directory for output reports (default: reports)",
    )
    parser.add_argument(
        "--db-path",
        default="/media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb",
        help="Path to DuckDB database",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed progress",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON results to stdout",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="CI mode: exit with code 1 on Gate 2 failure",
    )

    args = parser.parse_args()

    # Parse dates
    start_date = None
    end_date = None
    if args.start_date:
        start_date = datetime.fromisoformat(args.start_date)
    if args.end_date:
        end_date = datetime.fromisoformat(args.end_date)

    # Parse validation types
    validation_types = [vt.strip() for vt in args.validation_types.split(",")]

    # Handle tolerance sweep
    if args.sweep_tolerance:
        tolerances = [0.5, 1.0, 2.0]
    else:
        tolerances = [args.tolerance_pct]

    print(f"🔬 Validation Pipeline: {args.symbol}")
    print(f"   Validation types: {validation_types}")
    if start_date and end_date:
        print(f"   Period: {start_date.date()} to {end_date.date()}")
    else:
        print("   Period: Last 30 days (default)")
    print(f"   Tolerances: {tolerances}")
    print()

    results = []
    best_result = None
    best_f1 = -1.0

    for tolerance in tolerances:
        print(f"📊 Running with tolerance: {tolerance}%")

        result = run_pipeline(
            symbol=args.symbol,
            validation_types=validation_types,
            trigger_type="manual",
            triggered_by="cli",
            start_date=start_date,
            end_date=end_date,
            tolerance_pct=tolerance,
            db_path=args.db_path,
            verbose=args.verbose,
        )

        results.append(result)

        if result.status == PipelineStatus.FAILED:
            print(f"   ❌ Error: {result.error_message}")
            continue

        f1 = float(result.overall_score or 0) / 100

        gate_emoji = (
            "✅"
            if result.gate_2_decision == GateDecision.PASS
            else ("⚠️" if result.gate_2_decision == GateDecision.ACCEPTABLE else "❌")
        )

        print(f"   {gate_emoji} F1: {f1:.2%} (Grade: {result.overall_grade})")
        print(f"      Gate 2: {result.gate_2_decision.value}")
        print()

        if f1 > best_f1:
            best_f1 = f1
            best_result = result

    if best_result is None:
        print("❌ No successful validation runs")
        return 1

    # Save JSON output
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        output_data = {
            "best_tolerance": tolerances[results.index(best_result)]
            if len(tolerances) > 1
            else tolerances[0],
            "best_f1": best_f1,
            "gate_2_passed": best_result.gate_2_decision
            in [GateDecision.PASS, GateDecision.ACCEPTABLE],
            "results": [r.to_dict() for r in results],
        }

        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)
        print(f"📝 Results saved: {output_path}")

    # Print JSON to stdout if requested
    if args.json:
        print("\n--- JSON Output ---")
        print(json.dumps(best_result.to_dict(), indent=2))

    # Final summary
    print("\n" + "=" * 50)
    if best_result.gate_2_decision == GateDecision.PASS:
        print("🎉 GATE 2 PASSED: Model validated (F1 ≥ 60%)")
        print("   → Proceed to production / ETH expansion")
    elif best_result.gate_2_decision == GateDecision.ACCEPTABLE:
        print("⚠️ GATE 2 ACCEPTABLE: Model has limitations (F1 ≥ 40%)")
        print("   → Document limitations and proceed with caution")
    else:
        print("❌ GATE 2 FAILED: Model requires rework (F1 < 40%)")
        print("   → Stop and investigate prediction methodology")
    print(f"\n   Best F1: {best_f1:.2%} (Grade: {best_result.overall_grade})")
    print("=" * 50)

    # Exit code for CI mode
    if args.ci:
        if best_result.gate_2_decision == GateDecision.FAIL:
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
