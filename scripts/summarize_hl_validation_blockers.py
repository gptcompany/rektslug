#!/usr/bin/env python3
"""Summarize the current Hyperliquid validation blockers into a compact JSON."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _position_notional(position: dict[str, Any]) -> float:
    return abs(float(position.get("size", 0.0)) * float(position.get("mark_px", 0.0)))


def _top_positions(sample_user: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    positions = sorted(
        sample_user.get("positions", []),
        key=_position_notional,
        reverse=True,
    )
    top = []
    for position in positions[:limit]:
        top.append(
            {
                "coin": position.get("coin"),
                "size": float(position.get("size", 0.0)),
                "mark_px": float(position.get("mark_px", 0.0)),
                "entry_px": float(position.get("entry_px", 0.0)),
                "estimated_notional_usd": _position_notional(position),
                "maintenance_margin": float(position.get("maintenance_margin", 0.0)),
                "margin": float(position.get("margin", 0.0)),
            }
        )
    return top


def build_blocker_summary(
    report: dict[str, Any],
    outlier_sample: dict[str, Any],
    *,
    top_n: int = 5,
    positions_per_user: int = 3,
) -> dict[str, Any]:
    sample_by_user = {
        item["user"]: item
        for item in outlier_sample.get("users", [])
        if isinstance(item, dict) and isinstance(item.get("user"), str)
    }

    cross_results = [
        result
        for result in report.get("results", [])
        if result.get("mode") == "cross_margin"
    ]
    cross_results.sort(key=lambda result: float(result.get("deviation_mmr_pct", 0.0)), reverse=True)

    blockers = []
    for result in cross_results[:top_n]:
        user = result["user"]
        sample_user = sample_by_user.get(user, {})
        report_row = sample_user.get("report_row", {})
        liq_summary = result.get("liq_px_summary") or {}
        blockers.append(
            {
                "user": user,
                "deviation_mmr_pct": float(result.get("deviation_mmr_pct", 0.0)),
                "api_cross_maintenance_margin_used": float(
                    result.get("api_cross_maintenance_margin_used", 0.0)
                ),
                "sidecar_total_mmr": float(result.get("sidecar_total_mmr", 0.0)),
                "mmr_gap_usd": float(result.get("sidecar_total_mmr", 0.0))
                - float(result.get("api_cross_maintenance_margin_used", 0.0)),
                "position_count": int(report_row.get("position_count", len(sample_user.get("positions", [])))),
                "active_order_count": int(report_row.get("active_order_count", len(sample_user.get("orders", [])))),
                "non_reduce_only_order_count": int(report_row.get("non_reduce_only_order_count", 0)),
                "solver_mmr_total_from_sample": float(report_row.get("solver_mmr_total", 0.0)),
                "sample_margin_gap_total": float(report_row.get("margin_gap_total", 0.0)),
                "liq_px_positions_compared": int(liq_summary.get("positions_compared", 0)),
                "liq_px_improved_positions": int(liq_summary.get("improved_positions", 0)),
                "liq_px_worsened_positions": int(liq_summary.get("worsened_positions", 0)),
                "liq_px_improvement_rate": liq_summary.get("improvement_rate"),
                "top_positions": _top_positions(sample_user, positions_per_user),
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "report_timestamp": report.get("timestamp"),
            "report_path": "data/validation/margin_validation_report.json",
            "outlier_sample_path": "data/validation/hl_reserved_margin_outliers_eth_sample.json",
        },
        "summary": {
            "users_analyzed": int(report.get("users_analyzed", 0)),
            "tolerance_rate": float(report.get("tolerance_rate", 0.0)),
            "passed_all_accounts": bool(report.get("passed_all_accounts", False)),
            "passed_cross_margin_only": bool(report.get("passed_cross_margin_only", False)),
            "cross_margin_users": int(report.get("margin_mode_distribution", {}).get("cross_margin", 0)),
            "isolated_margin_users": int(
                report.get("margin_mode_distribution", {}).get("isolated_margin", 0)
            ),
            "cross_margin_tolerance_rate": float(
                report.get("mode_summaries", {})
                .get("cross_margin", {})
                .get("tolerance_rate", 0.0)
            ),
            "cross_margin_mean_mmr_deviation_pct": float(
                report.get("mode_summaries", {})
                .get("cross_margin", {})
                .get("mean_mmr_deviation_pct", 0.0)
            ),
        },
        "cross_margin_blockers": blockers,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize Hyperliquid validation blockers.")
    parser.add_argument(
        "--report",
        default="data/validation/margin_validation_report.json",
        help="Validation report JSON path.",
    )
    parser.add_argument(
        "--outliers",
        default="data/validation/hl_reserved_margin_outliers_eth_sample.json",
        help="Outlier sample JSON path.",
    )
    parser.add_argument(
        "--output",
        default="data/validation/margin_validation_blockers.json",
        help="Output JSON path.",
    )
    parser.add_argument("--top-n", type=int, default=5, help="Number of cross-margin blockers to keep.")
    parser.add_argument(
        "--positions-per-user",
        type=int,
        default=3,
        help="Number of largest positions to store for each blocker.",
    )
    args = parser.parse_args()

    summary = build_blocker_summary(
        _load_json(args.report),
        _load_json(args.outliers),
        top_n=args.top_n,
        positions_per_user=args.positions_per_user,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote blocker summary to {output_path}")


if __name__ == "__main__":
    main()
