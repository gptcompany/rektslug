#!/usr/bin/env python3
"""CLI script to validate reserved margin formulas against Hyperliquid API."""

import argparse
import asyncio
import dataclasses
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from src.liquidationheatmap.hyperliquid.api_client import HyperliquidInfoClient
from src.liquidationheatmap.hyperliquid.margin_math import DEFAULT_RESERVED_MARGIN_CANDIDATE
from src.liquidationheatmap.hyperliquid.margin_validator import MarginValidator
from src.liquidationheatmap.hyperliquid.models import (
    AccountAbstraction,
    MarginValidationReport,
)
from src.liquidationheatmap.hyperliquid.sidecar import (
    SidecarPositionReconstructor,
    UserOrder,
    iter_zst_jsonl,
)


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

DEFAULT_VALIDATION_OUTPUT = "validation_report.json"
DEFAULT_MODE_SCAN_OUTPUT = "data/validation/portfolio_margin_accounts.json"
DEFAULT_MODE_SCAN_LIMIT = 50
DEFAULT_MODE_SCAN_FILES = [
    "data/validation/hl_reserved_margin_proxy_eth_sample.json",
    "data/validation/hl_reserved_margin_outliers_eth_sample.json",
]
DEFAULT_MODE_POPULATION_REPORT = DEFAULT_MODE_SCAN_FILES[0]
DEFAULT_MODE_BATCH_SIZE = 25
MODE_SCAN_REQUESTS_PER_MINUTE = 120


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _extract_users_from_payload(data: object) -> list[str]:
    extracted: list[str] = []

    if isinstance(data, dict):
        extracted.extend(
            key for key in data.keys() if isinstance(key, str) and key.startswith("0x")
        )
        for value in data.values():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item.startswith("0x"):
                        extracted.append(item)
                    elif isinstance(item, dict):
                        user = item.get("user")
                        if isinstance(user, str) and user.startswith("0x"):
                            extracted.append(user)
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, str) and item.startswith("0x"):
                extracted.append(item)
            elif isinstance(item, dict):
                user = item.get("user")
                if isinstance(user, str) and user.startswith("0x"):
                    extracted.append(user)

    return _dedupe_preserve_order(extracted)


def _load_users(users: list[str] | None, file_path: str | None) -> list[str]:
    loaded_users: list[str] = list(users or [])

    if file_path:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            sys.exit(1)

        extracted = _extract_users_from_payload(data)
        if not extracted:
            print(f"Warning: Could not find user addresses in {file_path}")
        loaded_users.extend(extracted)

    if not loaded_users:
        print("No users provided. Using default test set (from research.md).")
        loaded_users = DEFAULT_USERS.copy()

    return _dedupe_preserve_order(loaded_users)


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
    cross_summary = report.mode_summaries.get("cross_margin")
    report_dict["passed_all_accounts"] = report.tolerance_rate >= 0.9
    report_dict["passed_cross_margin_only"] = (
        cross_summary.tolerance_rate >= 0.9 if cross_summary is not None else False
    )
    report_dict["passed"] = report_dict["passed_all_accounts"]
    report_dict["user_count"] = report.users_analyzed
    return report_dict


def _format_optional_float(value: float | None) -> str:
    return f"{value:.4f}" if value is not None else "n/a"


def _resolve_existing_data_file(path_str: str) -> Path:
    path = Path(path_str)
    if path.exists():
        return path

    parent = path.parent
    if not parent.exists():
        raise FileNotFoundError(path)

    candidates = sorted(
        candidate for candidate in parent.glob("*.zst") if candidate.is_file()
    )
    if len(candidates) == 1:
        return candidates[0]

    raise FileNotFoundError(path)


def _load_full_population_from_proxy_report(report_path: str) -> list[str]:
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    metadata = report.get("metadata", {})

    source_anchor = Path(metadata["source_anchor"])
    target_coin = metadata["target_coin"]
    order_status_file = _resolve_existing_data_file(metadata["order_status_file"])
    raw_book_diff_file = _resolve_existing_data_file(metadata["raw_book_diff_file"])

    reconstructor = SidecarPositionReconstructor()
    active_user_ids = reconstructor.collect_active_order_users_from_blocks(
        order_status_blocks=iter_zst_jsonl(order_status_file),
        raw_book_diff_blocks=iter_zst_jsonl(raw_book_diff_file),
    )
    sidecar_state = reconstructor.load_abci_anchor(
        source_anchor,
        target_coin=target_coin,
        target_users=active_user_ids,
    )
    return sorted(sidecar_state.users)


def _resolve_mode_scan_users(
    users: list[str] | None,
    file_path: str | None,
    *,
    full_population: bool = False,
    limit: int = DEFAULT_MODE_SCAN_LIMIT,
) -> tuple[list[str], list[str]]:
    if users or file_path:
        if full_population:
            population_report = file_path or DEFAULT_MODE_POPULATION_REPORT
            loaded_users = _load_full_population_from_proxy_report(population_report)
            return loaded_users, [population_report, "full_population"]
        source = [file_path] if file_path else ["cli_users"]
        return _load_users(users, file_path)[:limit], source

    if full_population:
        return (
            _load_full_population_from_proxy_report(DEFAULT_MODE_POPULATION_REPORT),
            [DEFAULT_MODE_POPULATION_REPORT, "full_population"],
        )

    resolved_users: list[str] = []
    sources: list[str] = []
    for candidate in DEFAULT_MODE_SCAN_FILES:
        path = Path(candidate)
        if not path.exists():
            continue
        batch = _load_users([], str(path))
        if not batch:
            continue
        resolved_users.extend(batch)
        sources.append(str(path))

    if not resolved_users:
        return DEFAULT_USERS[:limit], ["DEFAULT_USERS"]

    return _dedupe_preserve_order(resolved_users)[:limit], sources


def _resolve_output_path(output: str, *, detect_modes: bool) -> str:
    if detect_modes and output == DEFAULT_VALIDATION_OUTPUT:
        return DEFAULT_MODE_SCAN_OUTPUT
    return output


def _build_mode_detection_payload(
    results: list[dict],
    *,
    scanned_users: list[str],
    sources: list[str],
    limit: int,
) -> dict:
    mode_counts = {
        "cross_margin": 0,
        "isolated_margin": 0,
        "portfolio_margin": 0,
    }
    abstraction_counts: dict[str, int] = {}
    failures = 0
    portfolio_accounts: list[dict] = []

    for item in results:
        mode = item.get("mode")
        abstraction = item.get("user_abstraction")
        if mode in mode_counts:
            mode_counts[mode] += 1
            if abstraction is not None:
                abstraction_counts[abstraction] = abstraction_counts.get(abstraction, 0) + 1
            if mode == "portfolio_margin":
                portfolio_accounts.append(
                    {
                        "user": item["user"],
                        "user_abstraction": abstraction,
                        "portfolio_margin_ratio": item.get("portfolio_margin_ratio"),
                        "account_value": item.get("account_value"),
                        "position_count": item.get("position_count"),
                    }
                )
        else:
            failures += 1

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scan_limit": limit,
        "population_sources": sources,
        "users_requested": len(scanned_users),
        "users_succeeded": len(results) - failures,
        "users_failed": failures,
        "mode_counts": mode_counts,
        "account_abstraction_counts": abstraction_counts,
        "portfolio_margin_accounts": portfolio_accounts,
        "results": results,
    }


def _chunked(values: list[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]

async def main():
    parser = argparse.ArgumentParser(description="Validate Hyperliquid MMR calculations vs API")
    parser.add_argument("--users", nargs="+", help="Specific user addresses to validate")
    parser.add_argument("--file", "--outliers", dest="file", type=str, help="JSON file containing user addresses (e.g. outliers sample)")
    parser.add_argument("--output", type=str, default=DEFAULT_VALIDATION_OUTPUT, help="Output JSON report path")
    parser.add_argument("--detect-modes", action="store_true", help="Only detect margin modes for the users (skips full validation)")
    parser.add_argument(
        "--detect-modes-full-population",
        action="store_true",
        help="Reconstruct the full active-user population from the proxy report metadata instead of using ranked top-N lists.",
    )
    parser.add_argument(
        "--reserved-margin-candidate",
        default=DEFAULT_RESERVED_MARGIN_CANDIDATE,
        choices=["A", "B", "C", "D", "E"],
        help="Reserved-margin candidate used for V1.1 comparisons when reconstructed orders are available.",
    )
    args = parser.parse_args()

    output_path = _resolve_output_path(args.output, detect_modes=args.detect_modes)
    
    if args.detect_modes:
        users, sources = _resolve_mode_scan_users(
            args.users,
            args.file,
            full_population=args.detect_modes_full_population,
            limit=DEFAULT_MODE_SCAN_LIMIT,
        )
        print(
            "Detecting modes for "
            f"{len(users)} users "
            f"({'full population' if args.detect_modes_full_population else f'cap {DEFAULT_MODE_SCAN_LIMIT}'})..."
        )
        validator = MarginValidator(
            client=HyperliquidInfoClient(
                requests_per_minute=MODE_SCAN_REQUESTS_PER_MINUTE,
            )
        )
        detection_results: list[dict] = []
        batch_size = DEFAULT_MODE_BATCH_SIZE if args.detect_modes_full_population else len(users)

        for batch_index, batch in enumerate(_chunked(users, batch_size), start=1):
            if args.detect_modes_full_population:
                print(
                    f"Fetching batch {batch_index} "
                    f"({len(batch)} users, processed {min(batch_index * batch_size, len(users))}/{len(users)})..."
                )
            abstractions = await validator.client.get_user_abstractions_batch(batch)
            states = await validator.client.get_clearinghouse_states_batch(batch)
            spot_users = [
                user
                for user in batch
                if validator.requires_spot_clearinghouse_state(
                    abstractions.get(user, AccountAbstraction.UNKNOWN)
                )
            ]
            spot_states = await validator.client.get_spot_clearinghouse_states_batch(spot_users)
            for u in batch:
                state = states.get(u)
                abstraction = abstractions.get(u, AccountAbstraction.UNKNOWN)
                if state is None:
                    print(f"Failed to fetch {u}")
                    detection_results.append(
                        {
                            "user": u,
                            "mode": None,
                            "user_abstraction": abstraction.value,
                            "error": "Failed to fetch clearinghouse state",
                        }
                    )
                    continue

                mode = validator.detect_margin_mode(
                    state,
                    account_abstraction=abstraction,
                )
                spot_state = spot_states.get(u)
                print(f"User {u}: mode={mode.value} abstraction={abstraction.value}")
                detection_results.append(
                    {
                        "user": u,
                        "user_abstraction": abstraction.value,
                        "mode": mode.value,
                        "account_value": state.marginSummary.accountValue,
                        "total_margin_used": state.marginSummary.totalMarginUsed,
                        "cross_maintenance_margin_used": state.crossMaintenanceMarginUsed,
                        "position_count": len(state.assetPositions),
                        "portfolio_margin_ratio": (
                            state.portfolioMarginSummary.portfolioMarginRatio
                            if state.portfolioMarginSummary is not None
                            else None
                        ),
                        "spot_balance_count": len(spot_state.balances) if spot_state is not None else 0,
                        "spot_hold_total": (
                            sum(balance.hold for balance in spot_state.balances)
                            if spot_state is not None
                            else 0.0
                        ),
                    }
                )

        payload = _build_mode_detection_payload(
            detection_results,
            scanned_users=users,
            sources=sources,
            limit=(len(users) if args.detect_modes_full_population else DEFAULT_MODE_SCAN_LIMIT),
        )

        print("\n--- Detection Summary ---")
        for mode, count in payload["mode_counts"].items():
            print(f"{mode}: {count}")
        print("account_abstractions:")
        for abstraction, count in sorted(payload["account_abstraction_counts"].items()):
            print(f"  {abstraction}: {count}")
        print(f"portfolio_accounts: {len(payload['portfolio_margin_accounts'])}")

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"\nDetection report saved to {output}")
        return

    users = _load_users(args.users, args.file)
    print(f"Validating {len(users)} users...")
    
    validator = MarginValidator(
        orders_by_user=_load_orders_by_user(args.file),
        reserved_margin_candidate=args.reserved_margin_candidate,
    )
    report = await validator.validate_batch(users)
    
    print(f"\n--- Validation Report ---")
    print(f"Users analyzed: {report.users_analyzed}")
    print(f"Mean MMR Deviation: {report.mean_mmr_deviation_pct:.4f}%\n")
    cross_summary = report.mode_summaries.get("cross_margin")
    print(
        "Pass status: "
        f"all_accounts={report.tolerance_rate >= 0.9} "
        f"cross_margin_only={cross_summary.tolerance_rate >= 0.9 if cross_summary is not None else False}\n"
    )
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
        
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        json.dump(_serialize_report(report), f, indent=2)
        
    print(f"\nDetailed report saved to {output}")

if __name__ == "__main__":
    asyncio.run(main())
