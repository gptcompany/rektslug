"""Tests for the Hyperliquid /info snapshot capture CLI."""

import json
from unittest.mock import AsyncMock

import pytest

from scripts.capture_hyperliquid_info_snapshots import (
    _build_snapshot_entry,
    _load_default_watchlist,
    _load_watchlist,
    _requires_spot_clearinghouse_state,
    capture_snapshots,
)
from src.liquidationheatmap.hyperliquid.models import (
    AccountAbstraction,
    ApiPosition,
    AssetContext,
    AssetMeta,
    AssetMetaSnapshot,
    BorrowLendAmount,
    BorrowLendReserveState,
    BorrowLendTokenState,
    BorrowLendUserState,
    ClearinghouseUserState,
    CrossMarginSummary,
    Leverage,
    MarginSummary,
    PositionCumFunding,
    PositionData,
    SpotBalance,
    SpotClearinghouseState,
)


def test_load_default_watchlist_reads_portfolio_margin_accounts(tmp_path):
    path = tmp_path / "pm_accounts.json"
    path.write_text(
        json.dumps(
            {
                "portfolio_margin_accounts": [
                    {"user": "0xabc"},
                    {"user": "0xdef"},
                    {"user": "0xabc"},
                ]
            }
        ),
        encoding="utf-8",
    )

    users = _load_default_watchlist(str(path))

    assert users == ["0xabc", "0xdef"]


def test_load_watchlist_reads_users_and_portfolio_margin_accounts(tmp_path):
    path = tmp_path / "watchlist.json"
    path.write_text(
        json.dumps(
            {
                "users": [{"user": "0xabc"}, "0xdef"],
                "portfolio_margin_accounts": [{"user": "0x123"}],
            }
        ),
        encoding="utf-8",
    )

    users = _load_watchlist(["0x999"], str(path))

    assert users == ["0x999", "0xabc", "0xdef", "0x123"]


def test_build_snapshot_entry_tracks_comparable_positions():
    entry = _build_snapshot_entry(
        user="0xabc",
        account_abstraction=AccountAbstraction.PORTFOLIO_MARGIN,
        clearinghouse_state=make_state(liq_px=53.0),
        spot_state=make_spot_state(),
        borrow_lend_user_state=make_borrow_lend_user_state(),
        asset_meta_snapshot={
            "universe": [{"name": "HYPE"}],
            "assetContexts": [{"markPx": 55.0}],
            "margin_tables": {},
        },
        captured_at="2026-03-31T00:00:00+00:00",
    )

    assert entry["user_abstraction"] == "portfolioMargin"
    assert entry["position_count"] == 1
    assert entry["comparable_position_count"] == 1
    assert entry["comparable_positions"] == [{"coin": "HYPE", "liquidation_px": 53.0}]
    assert entry["mark_prices_by_coin"] == {"HYPE": 55.0}
    assert "portfolio_margin_summary_missing" in entry["warnings"]
    assert entry["spot_clearinghouse_state"]["balances"][0]["coin"] == "USDC"


def test_requires_spot_clearinghouse_state_false_for_default():
    assert not _requires_spot_clearinghouse_state(AccountAbstraction.DEFAULT)


@pytest.mark.asyncio
async def test_capture_snapshots_collects_portfolio_margin_states(monkeypatch):
    mock_client = AsyncMock()
    mock_client.get_all_borrow_lend_reserve_states.return_value = {
        0: BorrowLendReserveState(
            borrowYearlyRate=0.0,
            supplyYearlyRate=0.0,
            balance=0.0,
            utilization=0.0,
            oraclePx=1.0,
            ltv=0.0,
            totalSupplied=0.0,
            totalBorrowed=0.0,
        )
    }
    mock_client.get_user_abstraction.return_value = AccountAbstraction.PORTFOLIO_MARGIN
    mock_client.get_clearinghouse_state.return_value = make_state(liq_px=53.0)
    mock_client.get_spot_clearinghouse_state.return_value = make_spot_state()
    mock_client.get_borrow_lend_user_state.return_value = make_borrow_lend_user_state()
    mock_client.get_asset_meta.return_value = make_asset_snapshot()

    monkeypatch.setattr(
        "scripts.capture_hyperliquid_info_snapshots.HyperliquidInfoClient",
        lambda requests_per_minute=120: mock_client,
    )

    payload = await capture_snapshots(["0xabc"])

    assert payload["users_requested"] == 1
    assert payload["users_succeeded"] == 1
    assert payload["users_failed"] == 0
    assert payload["reserve_state_token_count"] == 1
    assert payload["warnings"] == []
    assert payload["snapshots"][0]["comparable_position_count"] == 1
    assert payload["snapshots"][0]["mark_prices_by_coin"] == {"HYPE": 55.0}
    assert payload["snapshots"][0]["borrow_lend_user_state"]["health"] == "healthy"
    assert payload["snapshots"][0]["asset_meta_snapshot"]["universe"][0]["name"] == "HYPE"


@pytest.mark.asyncio
async def test_capture_snapshots_skips_spot_fetch_for_default_abstraction(monkeypatch):
    mock_client = AsyncMock()
    mock_client.get_all_borrow_lend_reserve_states.return_value = {}
    mock_client.get_asset_meta.return_value = make_asset_snapshot()
    mock_client.get_user_abstraction.return_value = AccountAbstraction.DEFAULT
    mock_client.get_clearinghouse_state.return_value = make_state(liq_px=53.0)

    monkeypatch.setattr(
        "scripts.capture_hyperliquid_info_snapshots.HyperliquidInfoClient",
        lambda requests_per_minute=120: mock_client,
    )

    payload = await capture_snapshots(["0xabc"])

    assert payload["users_succeeded"] == 1
    assert payload["snapshots"][0]["spot_clearinghouse_state"] is None
    assert payload["snapshots"][0]["borrow_lend_user_state"] is None
    mock_client.get_spot_clearinghouse_state.assert_not_called()
    mock_client.get_borrow_lend_user_state.assert_not_called()


@pytest.mark.asyncio
async def test_capture_snapshots_records_meta_warning_and_stepful_failure(monkeypatch):
    mock_client = AsyncMock()
    mock_client.get_all_borrow_lend_reserve_states.return_value = {}
    mock_client.get_asset_meta.side_effect = RuntimeError("meta unavailable")
    mock_client.get_user_abstraction.return_value = AccountAbstraction.PORTFOLIO_MARGIN
    mock_client.get_clearinghouse_state.return_value = make_state(liq_px=53.0)
    mock_client.get_spot_clearinghouse_state.side_effect = TimeoutError("slow spot")

    monkeypatch.setattr(
        "scripts.capture_hyperliquid_info_snapshots.HyperliquidInfoClient",
        lambda requests_per_minute=120: mock_client,
    )

    payload = await capture_snapshots(["0xabc"])

    assert payload["users_succeeded"] == 0
    assert payload["users_failed"] == 1
    assert payload["warnings"] == ["metaAndAssetCtxs_unavailable:RuntimeError:meta unavailable"]
    assert payload["failures"][0]["step"] == "get_spot_and_borrow_lend_state"
    assert payload["failures"][0]["error_type"] == "TimeoutError"


def make_state(liq_px: float | None) -> ClearinghouseUserState:
    return ClearinghouseUserState(
        marginSummary=MarginSummary(
            accountValue=1000.0,
            totalMarginUsed=200.0,
            totalNtlPos=0.0,
            totalRawUsd=0.0,
        ),
        crossMarginSummary=CrossMarginSummary(
            accountValue=1000.0,
            totalMarginUsed=200.0,
            totalNtlPos=0.0,
            totalRawUsd=0.0,
        ),
        crossMaintenanceMarginUsed=100.0,
        withdrawable=800.0,
        time=1234567890,
        assetPositions=[
            ApiPosition(
                type="oneWay",
                position=PositionData(
                    coin="HYPE",
                    szi=-10.0,
                    entryPx=60.0,
                    positionValue=600.0,
                    unrealizedPnl=0.0,
                    returnOnEquity=0.0,
                    liquidationPx=liq_px,
                    leverage=Leverage(type="cross", value=5),
                    marginUsed=100.0,
                    maxLeverage=20,
                    cumFunding=PositionCumFunding(
                        allTime=0.0,
                        sinceOpen=0.0,
                        sinceChange=0.0,
                    ),
                ),
            )
        ],
        portfolioMarginSummary=None,
    )


def make_spot_state() -> SpotClearinghouseState:
    return SpotClearinghouseState(
        balances=[
            SpotBalance(
                coin="USDC",
                token=0,
                total=1000.0,
                hold=0.0,
                entryNtl=0.0,
                spotHold=0.0,
                ltv=0.0,
                supplied=0.0,
            )
        ],
        tokenToAvailableAfterMaintenance=[(0, 500.0)],
    )


def make_asset_snapshot() -> AssetMetaSnapshot:
    return AssetMetaSnapshot(
        universe=[
            AssetMeta(
                name="HYPE",
                szDecimals=2,
                maxLeverage=20,
                onlyIsolated=False,
                marginTableId=0,
            )
        ],
        assetContexts=[AssetContext(markPx=55.0)],
        margin_tables={},
    )


def make_borrow_lend_user_state() -> BorrowLendUserState:
    return BorrowLendUserState(
        tokenToState={
            0: BorrowLendTokenState(
                borrow=BorrowLendAmount(basis=0.0, value=0.0),
                supply=BorrowLendAmount(basis=0.0, value=1000.0),
            )
        },
        health="healthy",
        healthFactor=None,
    )
