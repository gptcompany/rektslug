"""Pure decision logic for the Nautilus liquidation-aware strategy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.liquidationheatmap.nautilus.data import LiquidationMapData

PositionState = Literal["flat", "long", "short"]
SignalAction = Literal["hold", "enter_long", "enter_short", "exit_long", "exit_short"]


@dataclass(frozen=True)
class LiquidationSignalDecision:
    """Trading decision derived from a liquidation-map snapshot."""

    action: SignalAction
    reason: str


def decide_liquidation_action(
    liq: LiquidationMapData,
    *,
    position_state: PositionState,
    proximity_threshold: float,
    imbalance_threshold: float,
    reversal_bias: bool = True,
) -> LiquidationSignalDecision:
    """Translate liquidation-map features into a simple trading action.

    The default bias is contrarian/reversal-oriented:
    - positive imbalance -> enter long
    - negative imbalance -> enter short
    """
    if liq.long_distance_pct < proximity_threshold and position_state == "long":
        return LiquidationSignalDecision(
            action="exit_long",
            reason="long liquidation cluster too close to current price",
        )

    if liq.short_distance_pct < proximity_threshold and position_state == "short":
        return LiquidationSignalDecision(
            action="exit_short",
            reason="short liquidation cluster too close to current price",
        )

    if position_state != "flat":
        return LiquidationSignalDecision(action="hold", reason="existing position unchanged")

    if min(liq.long_distance_pct, liq.short_distance_pct) < proximity_threshold:
        return LiquidationSignalDecision(
            action="hold",
            reason="flat but too close to a liquidation cluster for a fresh entry",
        )

    if abs(liq.net_imbalance) < imbalance_threshold:
        return LiquidationSignalDecision(
            action="hold",
            reason="imbalance below entry threshold",
        )

    if liq.net_imbalance > 0:
        return LiquidationSignalDecision(
            action="enter_long" if reversal_bias else "enter_short",
            reason="positive imbalance entry signal",
        )

    return LiquidationSignalDecision(
        action="enter_short" if reversal_bias else "enter_long",
        reason="negative imbalance entry signal",
    )
