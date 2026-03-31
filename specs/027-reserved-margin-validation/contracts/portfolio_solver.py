"""Contract: Portfolio-Margin Solver.

Defines the interface for computing liquidation conditions for
portfolio-margin accounts using net-risk netting and PMR threshold.
Implementation goes in src/liquidationheatmap/hyperliquid/portfolio_solver.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PortfolioMarginResult:
    """Liquidation analysis for a portfolio-margin account."""

    user_address: str
    portfolio_margin_ratio: float
    is_liquidatable: bool  # PMR > 0.95
    total_margin_required: float
    net_exposures: dict[str, float]  # coin -> net exposure after netting
    gross_margin: float  # margin without netting (cross-margin equivalent)
    netting_benefit: float  # gross_margin - total_margin_required
    liquidation_prices: dict[str, float | None]  # coin -> liq price under PM rules
    current_liquidation_value: float
    borrowed_notional_usdc: float
    collateral_support_usdc: float


class PortfolioMarginSolver(Protocol):
    """Protocol for portfolio-margin liquidation solver."""

    def compute_portfolio_margin(
        self,
        *,
        user_address: str,
        positions: list[object],  # list[UserPosition]
        mark_prices: dict[int, float],
        asset_margin_tiers: dict[int, list[dict]],
        spot_state: object,  # SpotClearinghouseState
        cross_maintenance_margin_used: float,
        borrow_lend_user_state: object | None = None,  # BorrowLendUserState
        reserve_states: dict[int, object] | None = None,  # BorrowLendReserveState
    ) -> PortfolioMarginResult:
        """Compute portfolio margin requirement from documented PM account state.

        Uses the documented PM pre-alpha inputs:
        - cross maintenance margin from perp state
        - spot balances / available-after-maintenance
        - borrow / lend user state
        - reserve-state oracle / LTV data
        """
        ...

    def solve_portfolio_liquidation_price(
        self,
        *,
        user_address: str,
        positions: list[object],  # list[UserPosition]
        target_coin: str,
        mark_prices: dict[int, float],
        asset_margin_tiers: dict[int, list[dict]],
        spot_state: object,  # SpotClearinghouseState
        cross_maintenance_margin_used: float,
        borrow_lend_user_state: object | None = None,  # BorrowLendUserState
        reserve_states: dict[int, object] | None = None,  # BorrowLendReserveState
    ) -> float | None:
        """Solve liquidation price for target coin under documented PM rules.

        The target-price move changes:
        - perp PnL
        - spot inventory value
        - spot-collateral bonus where applicable
        - maintenance margin for the affected perp notional
        """
        ...
