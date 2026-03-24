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


class PortfolioMarginSolver(Protocol):
    """Protocol for portfolio-margin liquidation solver."""

    def compute_portfolio_margin(
        self,
        positions: list[object],  # list[UserPosition]
        mark_prices: dict[int, float],
        asset_margin_tiers: dict[int, list[dict]],
    ) -> PortfolioMarginResult:
        """Compute portfolio margin requirement with net-risk netting.

        Net risk: offsetting positions (e.g., BTC long + ETH short) reduce
        total margin requirement compared to sum of individual margins.

        Liquidation trigger: portfolio_margin_ratio > 0.95
        """
        ...

    def solve_portfolio_liquidation_price(
        self,
        positions: list[object],  # list[UserPosition]
        target_coin: str,
        mark_prices: dict[int, float],
        asset_margin_tiers: dict[int, list[dict]],
        balance: float,
    ) -> float | None:
        """Solve liquidation price for target coin under portfolio-margin rules.

        Unlike cross-margin where each position's margin is independent,
        portfolio margin considers the net risk across all positions.
        Moving one price affects the net-risk calculation for all others.
        """
        ...
