#!/usr/bin/env python3
"""CLI script to validate reserved margin formulas against Hyperliquid API."""

import argparse
import asyncio
import dataclasses
import json
import sys

from src.liquidationheatmap.hyperliquid.margin_math import DEFAULT_RESERVED_MARGIN_CANDIDATE
from src.liquidationheatmap.hyperliquid.margin_validator import MarginValidator
from src.liquidationheatmap.hyperliquid.models import MarginValidationReport
from src.liquidationheatmap.hyperliquid.sidecar import UserOrder


DEFAULT_USERS = [
    "0x31dea241d74ebbaedb2d71d3eb2173167b5e40e6",
    "0x57dd78225e36502da2d159a444a5d898dc2287b4",
    "0x7717a7e30dd2a9c39cc233d2a71a0af74328ce78",
    "0x7b7f722a4bbda3c0b050d268598a2eb833ddca7f",
    "0x7fdafd36f2359480a424e16d0c75cc9e909a3cf8",
    "0xab5e6f54b6ce22a868f0709b1f0cddb017f8a3d6",
    "0xd4758784bd0268ec3baee29fb3e33e9d7249826a",
    "0xecb63c20202bf74030646c2ef5f2f45cc3941459",
    "0xfc667a4e6db7365da093375f68b31a876cd64d5d",
]


def _load_users(users: list[str] | None, file_path: str | None) -> list[str]:
    loaded_users: list[str] = list(users or [])

    if file_path:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            sys.exit(1)

        if isinstance(data, dict):
            extracted = [key for key in data.keys() if str(key).startswith("0x")]
            if not extracted and isinstance(data.get("users"), list):
                extracted = [
                    item.get("user")
                    for item in data["users"]
                    if isinstance(item, dict) and str(item.get("user", "")).startswith("0x")
                ]
            if not extracted:
                print(f"Warning: Could not find user addresses as top-level keys in {file_path}")
            loaded_users.extend(extracted)
        elif isinstance(data, list):
            loaded_users.extend(
                item for item in data if isinstance(item, str) and item.startswith("0x")
            )

    if not loaded_users:
        print("No users provided. Using default test set (from research.md).")
        loaded_users = DEFAULT_USERS.copy()

    return sorted(set(loaded_users))


def _load_orders_by_user(file_path: str | None) -> dict[str, list[UserOrder]]:
    if not file_path:
        return {}

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}

    if not isinstance(data, dict) or not isinstance(data.get("users"), list):
        return {}

    orders_by_user: dict[str, list[UserOrder]] = {}
    for item in data["users"]:
        user = item.get("user")
        if not isinstance(item, dict) or not isinstance(user, str):
            continue
        orders = []
        for order in item.get("orders", []):
            orders.append(
                UserOrder(
                    user=user,
                    oid=int(order["oid"]),
                    coin=str(order["coin"]),
                    side=str(order["side"]),
                    limit_px=float(order["limit_px"]),
                    size=float(order["size"]),
                    orig_size=float(order["orig_size"]) if order.get("orig_size") is not None else None,
                    tif=order.get("tif"),
                    order_type=order.get("order_type"),
                    reduce_only=bool(order.get("reduce_only", False)),
                    is_trigger=bool(order.get("is_trigger", False)),
                    is_position_tpsl=bool(order.get("is_position_tpsl", False)),
                    status=order.get("status"),
                )
            )
        if orders:
            orders_by_user[user] = orders
    return orders_by_user


def _serialize_report(report: MarginValidationReport) -> dict:
    report_dict = dataclasses.asdict(report)
    report_dict["passed"] = report.tolerance_rate >= 0.9
    report_dict["user_count"] = report.users_analyzed
    return report_dict


def _format_optional_float(value: float | None) -> str:
    return f"{value:.4f}" if value is not None else "n/a"

async def main():
    parser = argparse.ArgumentParser(description="Validate Hyperliquid MMR calculations vs API")
    parser.add_argument("--users", nargs="+", help="Specific user addresses to validate")
    parser.add_argument("--file", "--outliers", dest="file", type=str, help="JSON file containing user addresses (e.g. outliers sample)")
    parser.add_argument("--output", type=str, default="validation_report.json", help="Output JSON report path")
    parser.add_argument("--detect-modes", action="store_true", help="Only detect margin modes for the users (skips full validation)")
    parser.add_argument(
        "--reserved-margin-candidate",
        default=DEFAULT_RESERVED_MARGIN_CANDIDATE,
        choices=["A", "B", "C", "D"],
        help="Reserved-margin candidate used for V1.1 comparisons when reconstructed orders are available.",
    )
    args = parser.parse_args()

    users = _load_users(args.users, args.file)
    
    if args.detect_modes:
        print(f"Detecting modes for {len(users)} users (up to 50 max)...")
        users = users[:50]
        
        validator = MarginValidator()
        modes_count = {"cross_margin": 0, "isolated_margin": 0, "portfolio_margin": 0}
        
        for u in users:
            try:
                state = await validator.client.get_clearinghouse_state(u)
                mode = validator.detect_margin_mode(state)
                print(f"User {u}: {mode.value}")
                modes_count[mode.value] += 1
            except Exception as e:
                print(f"Failed to fetch {u}: {e}")
                
        print("\n--- Detection Summary ---")
        for mode, count in modes_count.items():
            print(f"{mode}: {count}")
        return

    print(f"Validating {len(users)} users...")
    
    validator = MarginValidator(
        orders_by_user=_load_orders_by_user(args.file),
        reserved_margin_candidate=args.reserved_margin_candidate,
    )
    report = await validator.validate_batch(users)
    
    print(f"\n--- Validation Report ---")
    print(f"Users analyzed: {report.users_analyzed}")
    print(f"Mean MMR Deviation: {report.mean_mmr_deviation_pct:.4f}%\n")
    if report.liq_px_summary is not None:
        print(
            "Global liqPx summary: "
            f"compared={report.liq_px_summary.positions_compared} "
            f"improved={report.liq_px_summary.improved_positions} "
            f"worsened={report.liq_px_summary.worsened_positions} "
            f"unchanged={report.liq_px_summary.unchanged_positions} "
            f"rate={_format_optional_float(report.liq_px_summary.improvement_rate)}"
        )
        print(
            "Global liqPx mean abs error: "
            f"V1={_format_optional_float(report.liq_px_summary.v1_mean_abs_error)} "
            f"V1.1={_format_optional_float(report.liq_px_summary.v1_1_mean_abs_error)}\n"
        )
    if report.mode_summaries:
        print("Mode summaries:")
        for mode, summary in report.mode_summaries.items():
            print(
                f"  {mode}: "
                f"users={summary.users_analyzed} "
                f"tolerance_rate={summary.tolerance_rate:.4f} "
                f"mean_mmr_deviation={summary.mean_mmr_deviation_pct:.4f}"
            )
            if summary.liq_px_summary is not None:
                print(
                    "    liqPx: "
                    f"compared={summary.liq_px_summary.positions_compared} "
                    f"improved={summary.liq_px_summary.improved_positions} "
                    f"worsened={summary.liq_px_summary.worsened_positions} "
                    f"rate={_format_optional_float(summary.liq_px_summary.improvement_rate)}"
                )
        print()
    
    for r in report.results:
        print(f"User: {r.user[:8]}... Mode: {r.mode.value}")
        print(f"  API MMR: {r.api_cross_maintenance_margin_used:.2f}  |  Sidecar MMR: {r.sidecar_total_mmr:.2f}")
        print(f"  Deviation: {r.deviation_mmr_pct:.4f}%")
        if r.liq_px_summary is not None:
            print(
                "  liqPx summary: "
                f"compared={r.liq_px_summary.positions_compared} "
                f"improved={r.liq_px_summary.improved_positions} "
                f"worsened={r.liq_px_summary.worsened_positions} "
                f"rate={_format_optional_float(r.liq_px_summary.improvement_rate)}"
            )
        for position in r.positions:
            if position.liq_px_deviation_pct is not None:
                if position.deviation_liq_px_v1_1 is not None:
                    print(
                        f"  {position.coin} liqPx | "
                        f"V1={position.deviation_liq_px_v1:.4f} "
                        f"V1.1={position.deviation_liq_px_v1_1:.4f}"
                    )
                else:
                    print(
                        f"  {position.coin} liqPx deviation: {position.liq_px_deviation_pct:.4f}%"
                    )
        
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(_serialize_report(report), f, indent=2)
        
    print(f"\nDetailed report saved to {args.output}")

if __name__ == "__main__":
    asyncio.run(main())
