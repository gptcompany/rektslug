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
from src.liquidationheatmap.hyperliquid.margin_validator import MarginValidator
from src.liquidationheatmap.hyperliquid.models import AccountAbstraction


DEFAULT_OUTPUT = "data/validation/pm_account_snapshots.json"
DEFAULT_WATCHLIST_SOURCE = "data/validation/portfolio_margin_accounts_full.json"


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _load_default_watchlist(path: str = DEFAULT_WATCHLIST_SOURCE) -> list[str]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
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


def _build_snapshot_entry(
    *,
    user: str,
    account_abstraction: AccountAbstraction,
    clearinghouse_state,
    spot_state,
    borrow_lend_user_state,
) -> dict:
    comparable_positions = [
        {
            "coin": position.position.coin,
            "liquidation_px": position.position.liquidationPx,
        }
        for position in clearinghouse_state.assetPositions
        if position.position.liquidationPx is not None
    ]
    return {
        "user": user,
        "user_abstraction": account_abstraction.value,
        "position_count": len(clearinghouse_state.assetPositions),
        "comparable_position_count": len(comparable_positions),
        "comparable_positions": comparable_positions,
        "clearinghouse_state": dataclasses.asdict(clearinghouse_state),
        "spot_clearinghouse_state": (
            dataclasses.asdict(spot_state) if spot_state is not None else None
        ),
        "borrow_lend_user_state": (
            dataclasses.asdict(borrow_lend_user_state)
            if borrow_lend_user_state is not None
            else None
        ),
    }


async def capture_snapshots(users: list[str]) -> dict:
    client = HyperliquidInfoClient(requests_per_minute=120)
    validator = MarginValidator(client=client)
    reserve_states = await client.get_all_borrow_lend_reserve_states()

    snapshots: list[dict] = []
    failures: list[dict] = []

    for index, user in enumerate(users, start=1):
        try:
            abstraction = await client.get_user_abstraction(user)
            clearinghouse_state = await client.get_clearinghouse_state(user)
            spot_state = None
            borrow_lend_user_state = None
            if validator.requires_spot_clearinghouse_state(abstraction):
                spot_state, borrow_lend_user_state = await asyncio.gather(
                    client.get_spot_clearinghouse_state(user),
                    client.get_borrow_lend_user_state(user),
                )
            snapshots.append(
                _build_snapshot_entry(
                    user=user,
                    account_abstraction=abstraction,
                    clearinghouse_state=clearinghouse_state,
                    spot_state=spot_state,
                    borrow_lend_user_state=borrow_lend_user_state,
                )
            )
            print(
                f"[{index}/{len(users)}] {user} ok "
                f"abstraction={abstraction.value} "
                f"comparable_positions={snapshots[-1]['comparable_position_count']}",
                flush=True,
            )
        except Exception as exc:
            failures.append({"user": user, "error": str(exc)})
            print(f"[{index}/{len(users)}] {user} failed error={exc}", flush=True)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "watchlist_source": DEFAULT_WATCHLIST_SOURCE,
        "users_requested": len(users),
        "users_succeeded": len(snapshots),
        "users_failed": len(failures),
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
