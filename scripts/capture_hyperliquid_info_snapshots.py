#!/usr/bin/env python3
"""Capture Hyperliquid /info snapshots for a user watchlist."""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
from datetime import datetime, timezone
from pathlib import Path

from src.liquidationheatmap.hyperliquid.api_client import HyperliquidInfoClient
from src.liquidationheatmap.hyperliquid.models import AccountAbstraction

DEFAULT_OUTPUT = "data/validation/pm_account_snapshots.json"
DEFAULT_WATCHLIST_SOURCE = "data/validation/portfolio_margin_accounts_full.json"


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _load_default_watchlist(path: str = DEFAULT_WATCHLIST_SOURCE) -> list[str]:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(
            f"Default watchlist source not found: {source}. "
            "Pass --users or --file explicitly."
        )
    payload = json.loads(source.read_text(encoding="utf-8"))
    accounts = payload.get("portfolio_margin_accounts", [])
    users = [
        item.get("user")
        for item in accounts
        if isinstance(item, dict) and isinstance(item.get("user"), str)
    ]
    return _dedupe_preserve_order([user for user in users if user])


def _load_watchlist(users: list[str] | None, file_path: str | None) -> list[str]:
    watchlist = list(users or [])
    if file_path:
        payload = json.loads(Path(file_path).read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            if isinstance(payload.get("users"), list):
                for item in payload["users"]:
                    if isinstance(item, str) and item.startswith("0x"):
                        watchlist.append(item)
                    elif isinstance(item, dict) and isinstance(item.get("user"), str):
                        watchlist.append(item["user"])
            if isinstance(payload.get("portfolio_margin_accounts"), list):
                for item in payload["portfolio_margin_accounts"]:
                    if isinstance(item, dict) and isinstance(item.get("user"), str):
                        watchlist.append(item["user"])
    if not watchlist:
        watchlist = _load_default_watchlist()
    return _dedupe_preserve_order(watchlist)


def _requires_spot_clearinghouse_state(
    account_abstraction: AccountAbstraction | str | None,
) -> bool:
    abstraction = AccountAbstraction.from_api(account_abstraction)
    return abstraction in {
        AccountAbstraction.UNIFIED_ACCOUNT,
        AccountAbstraction.PORTFOLIO_MARGIN,
    }


async def _fetch_asset_meta_snapshot(
    primary_client: HyperliquidInfoClient,
) -> tuple[dict | None, list[str]]:
    warnings: list[str] = []
    try:
        meta = await primary_client.get_asset_meta()
        return dataclasses.asdict(meta), warnings
    except Exception as exc:
        warnings.append(
            "metaAndAssetCtxs_unavailable:"
            f"{type(exc).__name__}:{exc}"
        )
        return None, warnings


def _extract_mark_prices_by_coin(
    clearinghouse_state,
    asset_meta_snapshot: dict | None,
) -> tuple[dict[str, float], list[str]]:
    warnings: list[str] = []
    if asset_meta_snapshot is not None:
        universe = asset_meta_snapshot.get("universe", [])
        contexts = asset_meta_snapshot.get("assetContexts", [])
        prices = {
            asset["name"]: context["markPx"]
            for asset, context in zip(universe, contexts)
            if isinstance(asset, dict)
            and isinstance(context, dict)
            and isinstance(asset.get("name"), str)
            and context.get("markPx") is not None
        }
        if prices:
            return prices, warnings

    proxy_prices: dict[str, float] = {}
    for api_position in clearinghouse_state.assetPositions:
        position = api_position.position
        if position.szi == 0:
            continue
        proxy_prices[position.coin] = abs(position.positionValue / position.szi)
    if proxy_prices:
        warnings.append("mark_prices_derived_from_position_value")
    else:
        warnings.append("mark_prices_unavailable")
    return proxy_prices, warnings


def _build_snapshot_entry(
    *,
    user: str,
    account_abstraction: AccountAbstraction,
    clearinghouse_state,
    spot_state,
    borrow_lend_user_state,
    asset_meta_snapshot: dict | None,
    captured_at: str,
) -> dict:
    warnings: list[str] = []
    comparable_positions = [
        {
            "coin": position.position.coin,
            "liquidation_px": position.position.liquidationPx,
        }
        for position in clearinghouse_state.assetPositions
        if position.position.liquidationPx is not None
    ]
    mark_prices_by_coin, mark_price_warnings = _extract_mark_prices_by_coin(
        clearinghouse_state,
        asset_meta_snapshot,
    )
    warnings.extend(mark_price_warnings)
    if (
        account_abstraction == AccountAbstraction.PORTFOLIO_MARGIN
        and clearinghouse_state.portfolioMarginSummary is None
    ):
        warnings.append("portfolio_margin_summary_missing")
    return {
        "user": user,
        "captured_at": captured_at,
        "user_abstraction": account_abstraction.value,
        "position_count": len(clearinghouse_state.assetPositions),
        "comparable_position_count": len(comparable_positions),
        "comparable_positions": comparable_positions,
        "mark_prices_by_coin": mark_prices_by_coin,
        "warnings": warnings,
        "clearinghouse_state": dataclasses.asdict(clearinghouse_state),
        "spot_clearinghouse_state": (
            dataclasses.asdict(spot_state) if spot_state is not None else None
        ),
        "borrow_lend_user_state": (
            dataclasses.asdict(borrow_lend_user_state)
            if borrow_lend_user_state is not None
            else None
        ),
        "asset_meta_snapshot": asset_meta_snapshot,
    }


async def capture_snapshots(users: list[str]) -> dict:
    client = HyperliquidInfoClient(requests_per_minute=120)
    started_at = datetime.now(timezone.utc).isoformat()
    reserve_states = await client.get_all_borrow_lend_reserve_states()
    asset_meta_snapshot, artifact_warnings = await _fetch_asset_meta_snapshot(client)

    snapshots: list[dict] = []
    failures: list[dict] = []

    for index, user in enumerate(users, start=1):
        try:
            step = "get_user_abstraction"
            abstraction = await client.get_user_abstraction(user)
            step = "get_clearinghouse_state"
            clearinghouse_state = await client.get_clearinghouse_state(user)
            spot_state = None
            borrow_lend_user_state = None
            if _requires_spot_clearinghouse_state(abstraction):
                step = "get_spot_and_borrow_lend_state"
                spot_state, borrow_lend_user_state = await asyncio.gather(
                    client.get_spot_clearinghouse_state(user),
                    client.get_borrow_lend_user_state(user),
                )
            captured_at = datetime.now(timezone.utc).isoformat()
            snapshots.append(
                _build_snapshot_entry(
                    user=user,
                    account_abstraction=abstraction,
                    clearinghouse_state=clearinghouse_state,
                    spot_state=spot_state,
                    borrow_lend_user_state=borrow_lend_user_state,
                    asset_meta_snapshot=asset_meta_snapshot,
                    captured_at=captured_at,
                )
            )
            warning_suffix = ""
            if snapshots[-1]["warnings"]:
                warning_suffix = f" warnings={','.join(snapshots[-1]['warnings'])}"
            print(
                f"[{index}/{len(users)}] {user} ok "
                f"abstraction={abstraction.value} "
                f"comparable_positions={snapshots[-1]['comparable_position_count']}"
                f"{warning_suffix}",
                flush=True,
            )
        except Exception as exc:
            failures.append(
                {
                    "user": user,
                    "step": step,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            print(
                f"[{index}/{len(users)}] {user} failed "
                f"step={step} error_type={type(exc).__name__} error={exc}",
                flush=True,
            )

    return {
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "watchlist_source": DEFAULT_WATCHLIST_SOURCE,
        "users_requested": len(users),
        "users_succeeded": len(snapshots),
        "users_failed": len(failures),
        "warnings": artifact_warnings,
        "reserve_state_token_count": len(reserve_states),
        "reserve_states": {str(token): dataclasses.asdict(state) for token, state in reserve_states.items()},
        "snapshots": snapshots,
        "failures": failures,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Capture Hyperliquid /info snapshots for a user watchlist")
    parser.add_argument("--users", nargs="+", help="Specific user addresses to snapshot")
    parser.add_argument("--file", type=str, help="JSON file containing users or portfolio_margin_accounts")
    parser.add_argument("--output", type=str, default=DEFAULT_OUTPUT, help="Output JSON path")
    args = parser.parse_args()

    users = _load_watchlist(args.users, args.file)
    print(f"Capturing snapshots for {len(users)} users...", flush=True)
    payload = await capture_snapshots(users)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Snapshot artifact saved to {output}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
