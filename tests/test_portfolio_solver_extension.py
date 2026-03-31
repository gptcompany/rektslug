"""Extended tests for HyperliquidPortfolioMarginSolver."""
import pytest
from src.liquidationheatmap.hyperliquid.portfolio_solver import (
    HyperliquidPortfolioMarginSolver,
)
from src.liquidationheatmap.hyperliquid.models import (
    SpotClearinghouseState,
    SpotBalance,
    BorrowLendReserveState,
    BorrowLendUserState,
    BorrowLendTokenState,
    BorrowLendAmount,
)
from src.liquidationheatmap.hyperliquid.sidecar import UserPosition

def test_collateral_bonus_usdc_edge_cases():
    solver = HyperliquidPortfolioMarginSolver()
    
    # No balance
    assert solver._collateral_bonus_usdc(None, {}, 10.0) == 0.0
    
    # No supply cap (not in PRE_ALPHA_SUPPLY_CAPS)
    balance = SpotBalance(coin="ETH", token=1, total=10.0, hold=0.0, entryNtl=0.0)
    assert solver._collateral_bonus_usdc(balance, {}, 10.0) == 0.0
    
    # No reserve
    balance = SpotBalance(coin="HYPE", token=150, total=10.0, hold=0.0, entryNtl=0.0)
    assert solver._collateral_bonus_usdc(balance, {}, 10.0) == 0.0
    
    # Negative total balance
    balance = SpotBalance(coin="HYPE", token=150, total=-10.0, hold=0.0, entryNtl=0.0)
    reserve = {150: BorrowLendReserveState(0, 0, 0, 0, 10.0, 0.5, 0, 0)}
    assert solver._collateral_bonus_usdc(balance, reserve, 10.0) == 0.0

def test_stable_spot_equity_usdc_filtering():
    solver = HyperliquidPortfolioMarginSolver()
    spot_state = SpotClearinghouseState(
        balances=[
            SpotBalance(coin="USDC", token=0, total=100.0, hold=0.0, entryNtl=0.0),
            SpotBalance(coin="ETH", token=1, total=10.0, hold=0.0, entryNtl=0.0), # Not stable
            SpotBalance(coin="USDT0", token=2, total=50.0, hold=0.0, entryNtl=0.0),
        ],
        tokenToAvailableAfterMaintenance=[],
    )
    reserve_states = {
        0: BorrowLendReserveState(0, 0, 0, 0, 1.0, 0, 0, 0),
        1: BorrowLendReserveState(0, 0, 0, 0, 2000.0, 0, 0, 0),
        2: BorrowLendReserveState(0, 0, 0, 0, 1.0, 0, 0, 0),
    }
    # Only USDC and USDT0 should count
    assert solver._stable_spot_equity_usdc(spot_state, reserve_states) == 150.0

def test_solve_portfolio_liquidation_price_short_moves_up():
    solver = HyperliquidPortfolioMarginSolver()
    
    # 10 HYPE short at 10.0 mark
    positions = [
        UserPosition(coin="HYPE", asset_idx=0, size=-10.0, entry_px=10.0, leverage=1.0, cum_funding=0, margin=0)
    ]
    # Small collateral, high requirement -> liquidatable if price goes up
    spot_state = SpotClearinghouseState(
        balances=[SpotBalance(coin="USDC", token=0, total=100.0, hold=0.0, entryNtl=0.0)],
        tokenToAvailableAfterMaintenance=[(0, 5.0)],
    )
    reserve_states = {0: BorrowLendReserveState(0, 0, 0, 0, 1.0, 0, 0, 0)}
    
    liq_px = solver.solve_portfolio_liquidation_price(
        user_address="0x123",
        positions=positions,
        target_coin="HYPE",
        mark_prices={0: 10.0},
        asset_margin_tiers={0: [{"lower_bound": 0.0, "mmr_rate": 0.05, "maintenance_deduction": 0.0}]},
        spot_state=spot_state,
        cross_maintenance_margin_used=20.0,
        reserve_states=reserve_states,
    )
    
    assert liq_px is not None
    assert liq_px > 10.0 # Price must go UP for short to liquidate

def test_solve_portfolio_liquidation_price_zero_exposure():
    solver = HyperliquidPortfolioMarginSolver()
    
    # Net exposure is zero
    positions = [
        UserPosition(coin="ETH", asset_idx=1, size=1.0, entry_px=2000.0, leverage=1.0, cum_funding=0, margin=0)
    ]
    spot_state = SpotClearinghouseState(
        balances=[SpotBalance(coin="ETH", token=1, total=-1.0, hold=0.0, entryNtl=0.0)],
        tokenToAvailableAfterMaintenance=[],
    )
    
    # target_coin with zero net exposure should return None if no target_positions size either
    # but here target_positions (ETH) has size 1.0, so it will use that.
    # If we pass a coin that is NOT in positions and NOT in spot:
    liq_px = solver.solve_portfolio_liquidation_price(
        user_address="0x123",
        positions=positions,
        target_coin="NONEXISTENT",
        mark_prices={1: 2000.0},
        asset_margin_tiers={},
        spot_state=spot_state,
        cross_maintenance_margin_used=0.0,
        reserve_states={},
    )
    assert liq_px is None

def test_borrowed_notional_none_state():
    solver = HyperliquidPortfolioMarginSolver()
    assert solver._borrowed_notional_usdc(None, {}) == 0.0

def test_current_mark_for_coin_none():
    solver = HyperliquidPortfolioMarginSolver()
    spot_state = SpotClearinghouseState(balances=[], tokenToAvailableAfterMaintenance=[])
    assert solver._current_mark_for_coin("ETH", [], {}, spot_state, {}) is None
