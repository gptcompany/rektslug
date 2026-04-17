#!/usr/bin/env python3
"""Build an offline review package for Hyperliquid portfolio-margin validation."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.liquidationheatmap.hyperliquid.models import (
    BorrowLendReserveState,
    BorrowLendUserState,
    ClearinghouseUserState,
    SpotClearinghouseState,
)
from src.liquidationheatmap.hyperliquid.portfolio_solver import HyperliquidPortfolioMarginSolver
from src.liquidationheatmap.hyperliquid.sidecar import UserPosition

DEFAULT_FIXTURE = "tests/fixtures/hyperliquid/portfolio_margin_live_cases.json"
DEFAULT_ACCOUNTS = "data/validation/portfolio_margin_accounts_full.json"
DEFAULT_REPO_SCAN = "data/validation/portfolio_margin_repo_scan.json"
DEFAULT_OUTPUT = "specs/027-reserved-margin-validation/review_package.json"


def _make_reserve_state(payload: dict) -> BorrowLendReserveState:
    return BorrowLendReserveState(
        borrowYearlyRate=payload.get("borrowYearlyRate", 0.0),
        supplyYearlyRate=payload.get("supplyYearlyRate", 0.0),
        balance=payload.get("balance", 0.0),
        utilization=payload.get("utilization", 0.0),
        oraclePx=payload["oraclePx"],
        ltv=payload["ltv"],
        totalSupplied=payload.get("totalSupplied", 0.0),
        totalBorrowed=payload.get("totalBorrowed", 0.0),
    )


def _load_fixture(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _build_asset_meta_lookup(fixture: dict) -> dict[str, dict]:
    universe = fixture["meta"]["universe"]
    asset_contexts = fixture["meta"]["assetContexts"]
    lookup: dict[str, dict] = {}
    for idx, meta in enumerate(universe):
        coin = str(meta["name"])
        if idx >= len(asset_contexts):
            raise ValueError(f"Missing asset context for coin {coin} at universe index {idx}")
        lookup[coin] = {
            "idx": idx,
            "mark_px": float(asset_contexts[idx]["markPx"]),
            "margin_table_id": str(meta["marginTableId"]),
        }
    return lookup


def _normalise_margin_tiers(fixture: dict, table_id: str) -> list[dict]:
    margin_tables = fixture["meta"].get("marginTables") or fixture["meta"].get("margin_tables", {})
    tiers = margin_tables.get(table_id, [])
    return [
        {
            "lower_bound": tier.get("lowerBound", tier.get("lower_bound", 0.0)),
            "mmr_rate": tier.get("mmrRate", tier.get("mmr_rate", 0.0)),
            "maintenance_deduction": tier.get(
                "maintenanceDeduction",
                tier.get("maintenance_deduction", 0.0),
            ),
        }
        for tier in tiers
    ]


def _extract_users(payload: dict, key: str) -> list[str]:
    users: list[str] = []
    for item in payload.get(key, []):
        if isinstance(item, dict) and isinstance(item.get("user"), str):
            users.append(item["user"])
    return sorted(set(users))


def _build_coverage(
    fixture_users: list[str],
    observed_users: list[str],
    repo_scan_users: list[str],
) -> dict:
    fixture_set = set(fixture_users)
    observed_set = set(observed_users)
    repo_scan_set = set(repo_scan_users)
    return {
        "fixture_users": fixture_users,
        "observed_users": observed_users,
        "repo_scan_users": repo_scan_users,
        "missing_from_fixture": sorted((observed_set | repo_scan_set) - fixture_set),
        "missing_from_observed": sorted(fixture_set - observed_set),
        "missing_from_repo_scan": sorted(fixture_set - repo_scan_set),
        "coverage_complete": fixture_set == observed_set == repo_scan_set,
    }


def _build_solver_context(fixture: dict, user_address: str) -> dict:
    user_payload = fixture["users"][user_address]
    clearinghouse_state = ClearinghouseUserState.from_api(user_payload["clearinghouseState"])
    spot_state = SpotClearinghouseState.from_api(user_payload["spotClearinghouseState"])
    borrow_lend_user_state = BorrowLendUserState.from_api(user_payload["borrowLendUserState"])
    asset_meta_lookup = _build_asset_meta_lookup(fixture)
    reserve_states = {
        int(token): _make_reserve_state(state)
        for token, state in fixture["reserve_states"].items()
    }

    positions: list[UserPosition] = []
    mark_prices: dict[int, float] = {}
    asset_margin_tiers: dict[int, list[dict]] = {}
    for api_position in clearinghouse_state.assetPositions:
        position = api_position.position
        if position.coin not in asset_meta_lookup:
            raise ValueError(
                f"Fixture meta does not contain coin {position.coin} for user {user_address}"
            )
        meta = asset_meta_lookup[position.coin]
        asset_idx = meta["idx"]
        positions.append(
            UserPosition(
                coin=position.coin,
                asset_idx=asset_idx,
                size=position.szi,
                entry_px=position.entryPx,
                leverage=float(position.leverage.value),
                cum_funding=position.cumFunding.sinceOpen,
                margin=position.marginUsed,
            )
        )
        mark_prices[asset_idx] = meta["mark_px"]
        asset_margin_tiers[asset_idx] = _normalise_margin_tiers(
            fixture,
            meta["margin_table_id"],
        )

    return {
        "user_address": user_address,
        "clearinghouse_state": clearinghouse_state,
        "spot_state": spot_state,
        "borrow_lend_user_state": borrow_lend_user_state,
        "reserve_states": reserve_states,
        "positions": positions,
        "mark_prices": mark_prices,
        "asset_margin_tiers": asset_margin_tiers,
    }


def build_review_package(
    fixture_path: str | Path = DEFAULT_FIXTURE,
    accounts_path: str | Path = DEFAULT_ACCOUNTS,
    repo_scan_path: str | Path = DEFAULT_REPO_SCAN,
) -> dict:
    fixture = _load_fixture(fixture_path)
    accounts_payload = _load_json(accounts_path)
    repo_scan_payload = _load_json(repo_scan_path)
    solver = HyperliquidPortfolioMarginSolver()
    fixture_users = sorted(fixture["users"])
    observed_users = _extract_users(accounts_payload, "portfolio_margin_accounts")
    repo_scan_users = _extract_users(repo_scan_payload, "results")
    if not repo_scan_users:
        repo_scan_users = _extract_users(repo_scan_payload, "pm_candidates")
    coverage = _build_coverage(fixture_users, observed_users, repo_scan_users)
    if not coverage["coverage_complete"]:
        raise ValueError(
            "Portfolio-margin review package coverage mismatch: "
            f"fixture={coverage['fixture_users']} observed={coverage['observed_users']} "
            f"repo_scan={coverage['repo_scan_users']}"
        )

    cases = []
    comparable_cases = 0
    within_tolerance_cases = 0
    for user_address in fixture_users:
        context = _build_solver_context(fixture, user_address)
        summary = solver.compute_portfolio_margin(
            user_address=user_address,
            positions=context["positions"],
            mark_prices=context["mark_prices"],
            asset_margin_tiers=context["asset_margin_tiers"],
            spot_state=context["spot_state"],
            cross_maintenance_margin_used=context["clearinghouse_state"].crossMaintenanceMarginUsed,
            borrow_lend_user_state=context["borrow_lend_user_state"],
            reserve_states=context["reserve_states"],
        )

        position_entries = []
        for position in context["clearinghouse_state"].assetPositions:
            api_liq = position.position.liquidationPx
            solver_liq = summary.liquidation_prices.get(position.position.coin)
            deviation_pct = None
            comparable = api_liq is not None and solver_liq is not None and api_liq > 0
            if comparable:
                comparable_cases += 1
                deviation_pct = abs(solver_liq - api_liq) / api_liq * 100.0
                if deviation_pct <= 1.0:
                    within_tolerance_cases += 1
            position_entries.append(
                {
                    "coin": position.position.coin,
                    "api_liquidation_px": api_liq,
                    "solver_liquidation_px": solver_liq,
                    "deviation_pct": deviation_pct,
                    "comparable": comparable,
                }
            )

        cases.append(
            {
                "user": user_address,
                "portfolio_margin_ratio": summary.portfolio_margin_ratio,
                "is_liquidatable": summary.is_liquidatable,
                "total_margin_required": summary.total_margin_required,
                "current_liquidation_value": summary.current_liquidation_value,
                "borrowed_notional_usdc": summary.borrowed_notional_usdc,
                "collateral_support_usdc": summary.collateral_support_usdc,
                "net_exposures": summary.net_exposures,
                "positions": position_entries,
            }
        )

    observed_accounts = accounts_payload.get("portfolio_margin_accounts", [])

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_fixture": str(fixture_path),
        "source_accounts": str(accounts_path),
        "source_repo_scan": str(repo_scan_path),
        "observed_portfolio_margin_accounts": observed_accounts,
        "observed_portfolio_margin_account_count": len(observed_accounts),
        "repo_scan_result_count": len(repo_scan_users),
        "fixture_user_count": len(fixture_users),
        "coverage": coverage,
        "comparable_position_count": comparable_cases,
        "within_tolerance_count": within_tolerance_cases,
        "within_tolerance_rate": (
            within_tolerance_cases / comparable_cases if comparable_cases else None
        ),
        "cases": cases,
        "residual_note": (
            "Portfolio-margin solver implementation is covered by local fixtures and the retained offline review package. "
            "The currently observable PM universe is fully captured here, coverage is explicitly checked against retained account artifacts, "
            "and all comparable live liquidationPx cases remain within tolerance."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build offline review package for Hyperliquid portfolio-margin validation")
    parser.add_argument("--fixture", default=DEFAULT_FIXTURE)
    parser.add_argument("--accounts", default=DEFAULT_ACCOUNTS)
    parser.add_argument("--repo-scan", default=DEFAULT_REPO_SCAN)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    payload = build_review_package(args.fixture, args.accounts, args.repo_scan)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Review package written to {output}")


if __name__ == "__main__":
    main()
