"""Portfolio-margin solver for Hyperliquid pre-alpha PM accounts."""

from __future__ import annotations

from dataclasses import dataclass

from src.liquidationheatmap.hyperliquid.margin_math import compute_position_maintenance_margin
from src.liquidationheatmap.hyperliquid.models import (
    BorrowLendReserveState,
    BorrowLendUserState,
    SpotBalance,
    SpotClearinghouseState,
)
from src.liquidationheatmap.hyperliquid.sidecar import UserPosition


DEFAULT_BORROW_TOKEN = 0  # USDC
DEFAULT_BORROW_CAP_USDC = 1000.0
MIN_BORROW_OFFSET_USDC = 20.0
LIQUIDATION_THRESHOLD = 0.95
PRE_ALPHA_SUPPLY_CAPS = {
    150: 200.0,  # HYPE
}
STABLE_COINS = {"USDC", "USDH", "USDE", "USDT0"}


@dataclass(frozen=True)
class PortfolioMarginResult:
    user_address: str
    portfolio_margin_ratio: float
    is_liquidatable: bool
    total_margin_required: float
    net_exposures: dict[str, float]
    gross_margin: float
    netting_benefit: float
    liquidation_prices: dict[str, float | None]
    current_liquidation_value: float
    borrowed_notional_usdc: float
    collateral_support_usdc: float


class HyperliquidPortfolioMarginSolver:
    """Best-effort solver for Hyperliquid's documented PM pre-alpha rules."""

    def __init__(
        self,
        *,
        borrow_token: int = DEFAULT_BORROW_TOKEN,
        borrow_cap_usdc: float = DEFAULT_BORROW_CAP_USDC,
        min_borrow_offset_usdc: float = MIN_BORROW_OFFSET_USDC,
        liquidation_threshold: float = LIQUIDATION_THRESHOLD,
    ) -> None:
        self.borrow_token = borrow_token
        self.borrow_cap_usdc = borrow_cap_usdc
        self.min_borrow_offset_usdc = min_borrow_offset_usdc
        self.liquidation_threshold = liquidation_threshold

    @staticmethod
    def _available_after_maintenance(
        spot_state: SpotClearinghouseState,
        token: int,
    ) -> float:
        for token_id, value in spot_state.tokenToAvailableAfterMaintenance:
            if token_id == token:
                return value
        return 0.0

    @staticmethod
    def _spot_balance_for_coin(
        spot_state: SpotClearinghouseState,
        coin: str,
    ) -> SpotBalance | None:
        return next((balance for balance in spot_state.balances if balance.coin == coin), None)

    @staticmethod
    def _spot_balance_for_token(
        spot_state: SpotClearinghouseState,
        token: int,
    ) -> SpotBalance | None:
        return next((balance for balance in spot_state.balances if balance.token == token), None)

    @staticmethod
    def _spot_oracle_px(
        token: int,
        reserve_states: dict[int, BorrowLendReserveState],
    ) -> float:
        reserve = reserve_states.get(token)
        return reserve.oraclePx if reserve is not None else 0.0

    @staticmethod
    def _compute_cross_maintenance_margin(
        positions: list[UserPosition],
        mark_prices: dict[int, float],
        asset_margin_tiers: dict[int, list[dict]],
    ) -> float:
        return sum(
            compute_position_maintenance_margin(position, mark_prices, asset_margin_tiers)
            for position in positions
        )

    def _borrowed_notional_usdc(
        self,
        borrow_lend_user_state: BorrowLendUserState | None,
        reserve_states: dict[int, BorrowLendReserveState],
    ) -> float:
        if borrow_lend_user_state is None:
            return 0.0

        borrowed_notional = 0.0
        for token, token_state in borrow_lend_user_state.tokenToState.items():
            reserve = reserve_states.get(token)
            oracle_px = reserve.oraclePx if reserve is not None else 0.0
            borrowed_notional += token_state.borrow.value * oracle_px
        return borrowed_notional

    def _collateral_bonus_usdc(
        self,
        spot_balance: SpotBalance | None,
        reserve_states: dict[int, BorrowLendReserveState],
        price: float,
    ) -> float:
        if spot_balance is None:
            return 0.0

        supply_cap = PRE_ALPHA_SUPPLY_CAPS.get(spot_balance.token)
        reserve = reserve_states.get(spot_balance.token)
        if supply_cap is None or reserve is None or reserve.ltv <= 0:
            return 0.0

        eligible_size = min(max(spot_balance.total, 0.0), supply_cap)
        collateral_threshold = 0.5 + 0.5 * reserve.ltv
        return min(
            self.borrow_cap_usdc,
            eligible_size * price * collateral_threshold,
        )

    def _stable_spot_equity_usdc(
        self,
        spot_state: SpotClearinghouseState,
        reserve_states: dict[int, BorrowLendReserveState],
    ) -> float:
        total = 0.0
        for balance in spot_state.balances:
            if balance.coin not in STABLE_COINS:
                continue
            oracle_px = self._spot_oracle_px(balance.token, reserve_states) or 1.0
            total += balance.total * oracle_px
        return total

    def _current_requirement_usdc(
        self,
        cross_maintenance_margin_used: float,
        borrow_lend_user_state: BorrowLendUserState | None,
        reserve_states: dict[int, BorrowLendReserveState],
    ) -> float:
        return (
            self.min_borrow_offset_usdc
            + cross_maintenance_margin_used
            + self._borrowed_notional_usdc(borrow_lend_user_state, reserve_states)
        )

    def _current_liquidation_value_usdc(
        self,
        spot_state: SpotClearinghouseState,
        cross_maintenance_margin_used: float,
        borrow_lend_user_state: BorrowLendUserState | None,
        reserve_states: dict[int, BorrowLendReserveState],
    ) -> float:
        requirement = self._current_requirement_usdc(
            cross_maintenance_margin_used,
            borrow_lend_user_state,
            reserve_states,
        )
        available_after_maintenance = self._available_after_maintenance(
            spot_state,
            self.borrow_token,
        )
        return max(0.0, requirement + available_after_maintenance)

    @staticmethod
    def _net_exposures(
        positions: list[UserPosition],
        spot_state: SpotClearinghouseState,
    ) -> dict[str, float]:
        exposures: dict[str, float] = {}
        for balance in spot_state.balances:
            exposures[balance.coin] = exposures.get(balance.coin, 0.0) + balance.total
        for position in positions:
            exposures[position.coin] = exposures.get(position.coin, 0.0) + position.size
        return exposures

    def _current_mark_for_coin(
        self,
        coin: str,
        positions: list[UserPosition],
        mark_prices: dict[int, float],
        spot_state: SpotClearinghouseState,
        reserve_states: dict[int, BorrowLendReserveState],
    ) -> float | None:
        for position in positions:
            if position.coin == coin:
                return mark_prices.get(position.asset_idx, position.entry_px)

        balance = self._spot_balance_for_coin(spot_state, coin)
        if balance is None:
            return None
        oracle_px = self._spot_oracle_px(balance.token, reserve_states)
        return oracle_px or None

    def _future_liquidation_value_usdc(
        self,
        current_liquidation_value_usdc: float,
        *,
        target_coin: str,
        target_price: float,
        current_target_price: float,
        positions: list[UserPosition],
        spot_state: SpotClearinghouseState,
        reserve_states: dict[int, BorrowLendReserveState],
    ) -> float:
        perp_delta = sum(
            position.size * (target_price - current_target_price)
            for position in positions
            if position.coin == target_coin
        )

        spot_balance = self._spot_balance_for_coin(spot_state, target_coin)
        spot_delta = 0.0
        bonus_delta = 0.0
        if spot_balance is not None:
            spot_delta = spot_balance.total * (target_price - current_target_price)
            bonus_delta = self._collateral_bonus_usdc(
                spot_balance,
                reserve_states,
                target_price,
            ) - self._collateral_bonus_usdc(
                spot_balance,
                reserve_states,
                current_target_price,
            )

        return max(0.0, current_liquidation_value_usdc + perp_delta + spot_delta + bonus_delta)

    def compute_portfolio_margin(
        self,
        *,
        user_address: str,
        positions: list[UserPosition],
        mark_prices: dict[int, float],
        asset_margin_tiers: dict[int, list[dict]],
        spot_state: SpotClearinghouseState,
        cross_maintenance_margin_used: float,
        borrow_lend_user_state: BorrowLendUserState | None = None,
        reserve_states: dict[int, BorrowLendReserveState] | None = None,
    ) -> PortfolioMarginResult:
        reserve_states = reserve_states or {}

        current_requirement = self._current_requirement_usdc(
            cross_maintenance_margin_used,
            borrow_lend_user_state,
            reserve_states,
        )
        current_liquidation_value = self._current_liquidation_value_usdc(
            spot_state,
            cross_maintenance_margin_used,
            borrow_lend_user_state,
            reserve_states,
        )
        portfolio_margin_ratio = (
            current_requirement / current_liquidation_value
            if current_liquidation_value > 0
            else 0.0
        )
        net_exposures = self._net_exposures(positions, spot_state)
        stable_spot_equity = self._stable_spot_equity_usdc(spot_state, reserve_states)
        collateral_support = max(0.0, current_liquidation_value - stable_spot_equity)
        gross_margin = current_requirement + collateral_support

        liquidation_prices = {
            position.coin: self.solve_portfolio_liquidation_price(
                user_address=user_address,
                positions=positions,
                target_coin=position.coin,
                mark_prices=mark_prices,
                asset_margin_tiers=asset_margin_tiers,
                spot_state=spot_state,
                cross_maintenance_margin_used=cross_maintenance_margin_used,
                borrow_lend_user_state=borrow_lend_user_state,
                reserve_states=reserve_states,
            )
            for position in positions
            if position.size != 0
        }

        return PortfolioMarginResult(
            user_address=user_address,
            portfolio_margin_ratio=portfolio_margin_ratio,
            is_liquidatable=portfolio_margin_ratio > self.liquidation_threshold,
            total_margin_required=current_requirement,
            net_exposures=net_exposures,
            gross_margin=gross_margin,
            netting_benefit=max(0.0, gross_margin - current_requirement),
            liquidation_prices=liquidation_prices,
            current_liquidation_value=current_liquidation_value,
            borrowed_notional_usdc=self._borrowed_notional_usdc(
                borrow_lend_user_state,
                reserve_states,
            ),
            collateral_support_usdc=collateral_support,
        )

    def solve_portfolio_liquidation_price(
        self,
        *,
        user_address: str,
        positions: list[UserPosition],
        target_coin: str,
        mark_prices: dict[int, float],
        asset_margin_tiers: dict[int, list[dict]],
        spot_state: SpotClearinghouseState,
        cross_maintenance_margin_used: float,
        borrow_lend_user_state: BorrowLendUserState | None = None,
        reserve_states: dict[int, BorrowLendReserveState] | None = None,
    ) -> float | None:
        reserve_states = reserve_states or {}
        current_target_price = self._current_mark_for_coin(
            target_coin,
            positions,
            mark_prices,
            spot_state,
            reserve_states,
        )
        if current_target_price is None or current_target_price <= 0:
            return None

        target_positions = [position for position in positions if position.coin == target_coin]

        current_requirement = self._current_requirement_usdc(
            cross_maintenance_margin_used,
            borrow_lend_user_state,
            reserve_states,
        )
        current_liquidation_value = self._current_liquidation_value_usdc(
            spot_state,
            cross_maintenance_margin_used,
            borrow_lend_user_state,
            reserve_states,
        )
        current_computed_mmr = self._compute_cross_maintenance_margin(
            positions,
            mark_prices,
            asset_margin_tiers,
        )

        net_exposure = self._net_exposures(positions, spot_state).get(target_coin, 0.0)
        if net_exposure == 0:
            net_exposure = sum(position.size for position in target_positions)
        if net_exposure == 0:
            return None

        def margin_buffer(price: float) -> float:
            updated_marks = dict(mark_prices)
            for position in target_positions:
                updated_marks[position.asset_idx] = price

            future_mmr = self._compute_cross_maintenance_margin(
                positions,
                updated_marks,
                asset_margin_tiers,
            )
            requirement = current_requirement + (future_mmr - current_computed_mmr)
            liquidation_value = self._future_liquidation_value_usdc(
                current_liquidation_value,
                target_coin=target_coin,
                target_price=price,
                current_target_price=current_target_price,
                positions=positions,
                spot_state=spot_state,
                reserve_states=reserve_states,
            )
            return self.liquidation_threshold * liquidation_value - requirement

        current_buffer = margin_buffer(current_target_price)
        if current_buffer <= 0:
            return current_target_price

        if net_exposure > 0:
            low = 0.0
            high = current_target_price
            if margin_buffer(low) > 0:
                return None
        else:
            low = current_target_price
            high = max(current_target_price * 2.0, current_target_price + 1.0)
            while margin_buffer(high) > 0 and high < current_target_price * 1e4:
                high *= 2.0
            if margin_buffer(high) > 0:
                return None

        for _ in range(80):
            mid = (low + high) / 2.0
            if margin_buffer(mid) > 0:
                if net_exposure > 0:
                    high = mid
                else:
                    low = mid
            else:
                if net_exposure > 0:
                    low = mid
                else:
                    high = mid

        return (low + high) / 2.0
