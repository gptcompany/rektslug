"""Tests for the Hyperliquid portfolio-margin solver."""

import json
from functools import lru_cache
from pathlib import Path

import pytest

from src.liquidationheatmap.hyperliquid.models import (
    BorrowLendAmount,
    BorrowLendReserveState,
    BorrowLendTokenState,
    BorrowLendUserState,
    ClearinghouseUserState,
    SpotBalance,
    SpotClearinghouseState,
)
from src.liquidationheatmap.hyperliquid.portfolio_solver import (
    HyperliquidPortfolioMarginSolver,
)
from src.liquidationheatmap.hyperliquid.sidecar import UserPosition


LIVE_PM_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "hyperliquid"
    / "portfolio_margin_live_cases.json"
)


def test_compute_portfolio_margin_collateral_support_reduces_requirement():
    solver = HyperliquidPortfolioMarginSolver()

    result = solver.compute_portfolio_margin(
        user_address="0xabc",
        positions=[
            UserPosition(
                coin="HYPE",
                asset_idx=0,
                size=-10.0,
                entry_px=12.0,
                leverage=5.0,
                cum_funding=0.0,
                margin=0.0,
            )
        ],
        mark_prices={0: 10.0},
        asset_margin_tiers={0: [{"lower_bound": 0.0, "mmr_rate": 0.05, "maintenance_deduction": 0.0}]},
        spot_state=SpotClearinghouseState(
            balances=[
                SpotBalance(coin="USDC", token=0, total=100.0, hold=0.0, entryNtl=0.0),
                SpotBalance(coin="HYPE", token=150, total=20.0, hold=0.0, entryNtl=0.0, ltv=0.5),
            ],
            tokenToAvailableAfterMaintenance=[(0, 450.0)],
        ),
        cross_maintenance_margin_used=50.0,
        borrow_lend_user_state=BorrowLendUserState(tokenToState={}, health="healthy", healthFactor=None),
        reserve_states={
            0: make_reserve_state(oracle_px=1.0, ltv=0.0),
            150: make_reserve_state(oracle_px=10.0, ltv=0.5),
        },
    )

    assert result.total_margin_required == pytest.approx(70.0)
    assert result.current_liquidation_value == pytest.approx(520.0)
    assert result.portfolio_margin_ratio == pytest.approx(70.0 / 520.0)
    assert result.net_exposures["HYPE"] == pytest.approx(10.0)
    assert result.netting_benefit > 0.0
    assert not result.is_liquidatable


def test_compute_portfolio_margin_ratio_liquidation_threshold():
    solver = HyperliquidPortfolioMarginSolver()

    result = solver.compute_portfolio_margin(
        user_address="0xabc",
        positions=[],
        mark_prices={},
        asset_margin_tiers={},
        spot_state=SpotClearinghouseState(
            balances=[SpotBalance(coin="USDC", token=0, total=5.0, hold=0.0, entryNtl=0.0)],
            tokenToAvailableAfterMaintenance=[(0, 1.0)],
        ),
        cross_maintenance_margin_used=0.0,
        borrow_lend_user_state=BorrowLendUserState(tokenToState={}, health="healthy", healthFactor=None),
        reserve_states={0: make_reserve_state(oracle_px=1.0, ltv=0.0)},
    )

    assert result.total_margin_required == pytest.approx(20.0)
    assert result.current_liquidation_value == pytest.approx(21.0)
    assert result.portfolio_margin_ratio > 0.95
    assert result.is_liquidatable


def test_compute_portfolio_margin_includes_borrowed_notional():
    solver = HyperliquidPortfolioMarginSolver()

    result = solver.compute_portfolio_margin(
        user_address="0xabc",
        positions=[],
        mark_prices={},
        asset_margin_tiers={},
        spot_state=SpotClearinghouseState(
            balances=[SpotBalance(coin="USDC", token=0, total=500.0, hold=0.0, entryNtl=0.0)],
            tokenToAvailableAfterMaintenance=[(0, 430.0)],
        ),
        cross_maintenance_margin_used=0.0,
        borrow_lend_user_state=BorrowLendUserState(
            tokenToState={
                0: BorrowLendTokenState(
                    borrow=BorrowLendAmount(basis=0.0, value=50.0),
                    supply=BorrowLendAmount(basis=0.0, value=0.0),
                )
            },
            health="healthy",
            healthFactor=None,
        ),
        reserve_states={0: make_reserve_state(oracle_px=1.0, ltv=0.0)},
    )

    assert result.borrowed_notional_usdc == pytest.approx(50.0)
    assert result.total_margin_required == pytest.approx(70.0)
    assert result.current_liquidation_value == pytest.approx(500.0)


def test_solve_portfolio_liquidation_price_for_long_position_moves_down():
    solver = HyperliquidPortfolioMarginSolver()

    result = solver.solve_portfolio_liquidation_price(
        user_address="0xabc",
        positions=[
            UserPosition(
                coin="HYPE",
                asset_idx=0,
                size=10.0,
                entry_px=12.0,
                leverage=5.0,
                cum_funding=0.0,
                margin=0.0,
            )
        ],
        target_coin="HYPE",
        mark_prices={0: 10.0},
        asset_margin_tiers={0: [{"lower_bound": 0.0, "mmr_rate": 0.05, "maintenance_deduction": 0.0}]},
        spot_state=SpotClearinghouseState(
            balances=[SpotBalance(coin="USDC", token=0, total=100.0, hold=0.0, entryNtl=0.0)],
            tokenToAvailableAfterMaintenance=[(0, 20.0)],
        ),
        cross_maintenance_margin_used=50.0,
        borrow_lend_user_state=BorrowLendUserState(tokenToState={}, health="healthy", healthFactor=None),
        reserve_states={0: make_reserve_state(oracle_px=1.0, ltv=0.0)},
    )

    assert result is not None
    assert result < 10.0
    assert result == pytest.approx(74.5 / 9.0, rel=1e-3)


def test_solve_portfolio_liquidation_price_returns_none_when_not_reachable():
    solver = HyperliquidPortfolioMarginSolver()

    result = solver.solve_portfolio_liquidation_price(
        user_address="0xabc",
        positions=[
            UserPosition(
                coin="HYPE",
                asset_idx=0,
                size=10.0,
                entry_px=12.0,
                leverage=5.0,
                cum_funding=0.0,
                margin=0.0,
            )
        ],
        target_coin="HYPE",
        mark_prices={0: 10.0},
        asset_margin_tiers={0: [{"lower_bound": 0.0, "mmr_rate": 0.05, "maintenance_deduction": 0.0}]},
        spot_state=SpotClearinghouseState(
            balances=[SpotBalance(coin="USDC", token=0, total=100.0, hold=0.0, entryNtl=0.0)],
            tokenToAvailableAfterMaintenance=[(0, 1000.0)],
        ),
        cross_maintenance_margin_used=50.0,
        borrow_lend_user_state=BorrowLendUserState(tokenToState={}, health="healthy", healthFactor=None),
        reserve_states={0: make_reserve_state(oracle_px=1.0, ltv=0.0)},
    )

    assert result is None


def test_solve_portfolio_liquidation_price_returns_current_mark_when_already_liquidatable():
    solver = HyperliquidPortfolioMarginSolver()

    result = solver.solve_portfolio_liquidation_price(
        user_address="0xabc",
        positions=[],
        target_coin="HYPE",
        mark_prices={0: 10.0},
        asset_margin_tiers={0: [{"lower_bound": 0.0, "mmr_rate": 0.05, "maintenance_deduction": 0.0}]},
        spot_state=SpotClearinghouseState(
            balances=[SpotBalance(coin="HYPE", token=150, total=1.0, hold=0.0, entryNtl=0.0, ltv=0.5)],
            tokenToAvailableAfterMaintenance=[(0, 1.0)],
        ),
        cross_maintenance_margin_used=0.0,
        borrow_lend_user_state=BorrowLendUserState(tokenToState={}, health="healthy", healthFactor=None),
        reserve_states={
            0: make_reserve_state(oracle_px=1.0, ltv=0.0),
            150: make_reserve_state(oracle_px=10.0, ltv=0.5),
        },
    )

    assert result == pytest.approx(10.0)


def test_solve_portfolio_liquidation_price_matches_live_pm_short_case():
    solver = HyperliquidPortfolioMarginSolver()
    context = make_live_pm_case_context(
        "0xb1c4a17f0f39c2b04333831104a82e94ab808510"
    )
    result = solver.solve_portfolio_liquidation_price(**solver_liq_context(context))

    assert result is not None
    assert result == pytest.approx(context["api_liquidation_px"], rel=0.01)


def test_live_like_short_case_solution_is_close_to_pm_threshold_root():
    solver = HyperliquidPortfolioMarginSolver()
    context = make_live_pm_case_context(
        "0xb1c4a17f0f39c2b04333831104a82e94ab808510"
    )
    result = solver.solve_portfolio_liquidation_price(**solver_liq_context(context))

    assert result is not None

    current_requirement = solver._current_requirement_usdc(
        context["cross_maintenance_margin_used"],
        context["borrow_lend_user_state"],
        context["reserve_states"],
    )
    current_liquidation_value = solver._current_liquidation_value_usdc(
        context["spot_state"],
        context["cross_maintenance_margin_used"],
        context["borrow_lend_user_state"],
        context["reserve_states"],
    )
    current_computed_mmr = solver._compute_cross_maintenance_margin(
        context["positions"],
        context["mark_prices"],
        context["asset_margin_tiers"],
    )
    current_target_price = context["mark_prices"][0]

    def margin_buffer(price: float) -> float:
        updated_marks = dict(context["mark_prices"])
        updated_marks[0] = price
        future_mmr = solver._compute_cross_maintenance_margin(
            context["positions"],
            updated_marks,
            context["asset_margin_tiers"],
        )
        requirement = current_requirement + (future_mmr - current_computed_mmr)
        liquidation_value = solver._future_liquidation_value_usdc(
            current_liquidation_value,
            target_coin="HYPE",
            target_price=price,
            current_target_price=current_target_price,
            positions=context["positions"],
            spot_state=context["spot_state"],
            reserve_states=context["reserve_states"],
        )
        return solver.liquidation_threshold * liquidation_value - requirement

    assert abs(margin_buffer(result)) < 1e-3
    assert margin_buffer(result - 0.1) > 0.0
    assert margin_buffer(result + 0.1) < 0.0


def test_compute_portfolio_margin_handles_live_pm_account_with_no_positions():
    solver = HyperliquidPortfolioMarginSolver()
    context = make_live_pm_case_context(
        "0xdc00aede8219c1151ddd86372deed7a36bdeb405"
    )

    result = solver.compute_portfolio_margin(
        user_address=context["user_address"],
        positions=context["positions"],
        mark_prices=context["mark_prices"],
        asset_margin_tiers=context["asset_margin_tiers"],
        spot_state=context["spot_state"],
        cross_maintenance_margin_used=context["cross_maintenance_margin_used"],
        borrow_lend_user_state=context["borrow_lend_user_state"],
        reserve_states=context["reserve_states"],
    )

    assert result.liquidation_prices == {}
    assert result.current_liquidation_value == pytest.approx(20.00000261)
    assert result.portfolio_margin_ratio > 0.95
    assert result.is_liquidatable


def test_solve_portfolio_liquidation_price_handles_live_pm_long_case_without_api_liq_px():
    solver = HyperliquidPortfolioMarginSolver()
    context = make_live_pm_case_context(
        "0xfc8b2f2b98705037ec9fa816f40c42077b237d3c"
    )

    result = solver.solve_portfolio_liquidation_price(**solver_liq_context(context))
    summary = solver.compute_portfolio_margin(
        user_address=context["user_address"],
        positions=context["positions"],
        mark_prices=context["mark_prices"],
        asset_margin_tiers=context["asset_margin_tiers"],
        spot_state=context["spot_state"],
        cross_maintenance_margin_used=context["cross_maintenance_margin_used"],
        borrow_lend_user_state=context["borrow_lend_user_state"],
        reserve_states=context["reserve_states"],
    )

    assert result is not None
    assert result < context["mark_prices"][0]
    assert summary.liquidation_prices["HYPE"] == pytest.approx(result)
    assert summary.portfolio_margin_ratio < 0.95
    assert not summary.is_liquidatable


def make_reserve_state(*, oracle_px: float, ltv: float) -> BorrowLendReserveState:
    return BorrowLendReserveState(
        borrowYearlyRate=0.05,
        supplyYearlyRate=0.0,
        balance=0.0,
        utilization=0.0,
        oraclePx=oracle_px,
        ltv=ltv,
        totalSupplied=0.0,
        totalBorrowed=0.0,
    )


@lru_cache(maxsize=1)
def load_live_pm_fixture() -> dict:
    return json.loads(LIVE_PM_FIXTURE_PATH.read_text(encoding="utf-8"))


def make_live_pm_case_context(user_address: str) -> dict:
    fixture = load_live_pm_fixture()
    user_payload = fixture["users"][user_address]
    clearinghouse_state = ClearinghouseUserState.from_api(
        user_payload["clearinghouseState"]
    )
    spot_state = SpotClearinghouseState.from_api(
        user_payload["spotClearinghouseState"]
    )
    borrow_lend_user_state = BorrowLendUserState.from_api(
        user_payload["borrowLendUserState"]
    )

    hype_meta = fixture["meta"]["universe"][0]
    margin_table_id = str(hype_meta["marginTableId"])
    mark_px = fixture["meta"]["assetContexts"][0]["markPx"]
    reserve_states = {
        int(token): make_reserve_state(
            oracle_px=state["oraclePx"],
            ltv=state["ltv"],
        )
        for token, state in fixture["reserve_states"].items()
    }
    positions = [
        UserPosition(
            coin=api_position.position.coin,
            asset_idx=0,
            size=api_position.position.szi,
            entry_px=api_position.position.entryPx,
            leverage=float(api_position.position.leverage.value),
            cum_funding=api_position.position.cumFunding.sinceOpen,
            margin=api_position.position.marginUsed,
        )
        for api_position in clearinghouse_state.assetPositions
    ]
    target_coin = positions[0].coin if positions else "HYPE"
    api_liquidation_px = (
        clearinghouse_state.assetPositions[0].position.liquidationPx
        if clearinghouse_state.assetPositions
        else None
    )

    return {
        "user_address": user_address,
        "positions": positions,
        "target_coin": target_coin,
        "mark_prices": {0: mark_px},
        "asset_margin_tiers": {0: fixture["meta"]["margin_tables"][margin_table_id]},
        "spot_state": spot_state,
        "cross_maintenance_margin_used": (
            clearinghouse_state.crossMaintenanceMarginUsed
        ),
        "borrow_lend_user_state": borrow_lend_user_state,
        "reserve_states": reserve_states,
        "api_liquidation_px": api_liquidation_px,
    }


def solver_liq_context(context: dict) -> dict:
    return {key: value for key, value in context.items() if key != "api_liquidation_px"}
