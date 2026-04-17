"""Example Nautilus Trader strategy that reacts to liquidation map events.

This strategy consumes NTLiquidationMapData and can place simple market
orders from imbalance/proximity signals in a backtest or paper-like replay.
"""

from __future__ import annotations

from decimal import Decimal

from src.liquidationheatmap.nautilus import _check_nautilus

_check_nautilus()

from nautilus_trader.config import StrategyConfig  # noqa: E402
from nautilus_trader.model.data import BarType, CustomData, DataType  # noqa: E402
from nautilus_trader.model.enums import OrderSide, TimeInForce  # noqa: E402
from nautilus_trader.model.identifiers import ClientId, InstrumentId  # noqa: E402
from nautilus_trader.model.orders import MarketOrder  # noqa: E402
from nautilus_trader.trading.strategy import Strategy  # noqa: E402

from src.liquidationheatmap.nautilus.data import LiquidationMapData  # noqa: E402
from src.liquidationheatmap.nautilus.nt_types import NTLiquidationMapData  # noqa: E402
from src.liquidationheatmap.nautilus.strategy_logic import (  # noqa: E402
    PositionState,
    decide_liquidation_action,
)


class LiquidationAwareConfig(StrategyConfig, frozen=True):
    """Configuration for LiquidationAwareStrategy."""

    instrument_id: InstrumentId
    client_id: ClientId = ClientId("REKTSLUG")
    bar_type: BarType | None = None
    trade_size: Decimal = Decimal("0.001")
    proximity_threshold: float = 0.02  # 2% distance triggers AVOID
    imbalance_threshold: float = 0.6  # net_imbalance threshold for REVERSAL signal
    reversal_bias: bool = True
    close_positions_on_stop: bool = True


class LiquidationAwareStrategy(Strategy):
    """Strategy that reacts to liquidation map events.

    Signals:
    - EXIT: close positions if price is too close to a same-side liquidation cluster.
    - ENTRY: open a simple market position when imbalance exceeds threshold.
    """

    def __init__(self, config: LiquidationAwareConfig) -> None:
        super().__init__(config)
        self.instrument_id = config.instrument_id
        self.client_id = config.client_id
        self.bar_type = config.bar_type
        self.trade_size = config.trade_size
        self.proximity_threshold = config.proximity_threshold
        self.imbalance_threshold = config.imbalance_threshold
        self.reversal_bias = config.reversal_bias
        self.close_positions_on_stop = config.close_positions_on_stop
        self._last_liq_data: LiquidationMapData | None = None

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.instrument_id)
        if self.instrument is None:
            self.log.error(f"Instrument not found: {self.instrument_id}")
            self.stop()
            return
        # Subscribe to CustomData wrapping NTLiquidationMapData
        self.subscribe_data(
            DataType(
                NTLiquidationMapData,
                metadata={"instrument_id": str(self.instrument_id)},
            ),
            client_id=self.client_id,
            instrument_id=self.instrument_id,
        )
        if self.bar_type is not None:
            self.subscribe_bars(self.bar_type)
        self.log.info("Subscribed to NTLiquidationMapData events")

    def on_data(self, data) -> None:
        liq = self._extract_liquidation_data(data)
        if liq is None:
            return

        self._last_liq_data = liq
        self.log.info(
            f"LiqMap update: expert={liq.expert_id} "
            f"imbalance={liq.net_imbalance:.3f} "
            f"long_dist={liq.long_distance_pct:.4f} "
            f"short_dist={liq.short_distance_pct:.4f}"
        )
        self._apply_liquidation_decision(liq)

    def on_bar(self, bar) -> None:
        # Keep bar subscription for market context/fills, but react on signal arrival.
        return

    def on_stop(self) -> None:
        if self.close_positions_on_stop and getattr(self, "instrument", None) is not None:
            self.close_all_positions(self.instrument.id)

    def on_reset(self) -> None:
        self._last_liq_data = None

    def buy(self) -> None:
        if not self.portfolio.is_flat(self.instrument.id):
            return
        order = self._build_market_order(OrderSide.BUY)
        self.submit_order(order)

    def sell(self) -> None:
        if not self.portfolio.is_flat(self.instrument.id):
            return
        order = self._build_market_order(OrderSide.SELL)
        self.submit_order(order)

    def _apply_liquidation_decision(self, liq: LiquidationMapData) -> None:
        decision = decide_liquidation_action(
            liq,
            position_state=self._position_state(),
            proximity_threshold=self.proximity_threshold,
            imbalance_threshold=self.imbalance_threshold,
            reversal_bias=self.reversal_bias,
        )

        if decision.action == "exit_long":
            self.close_all_positions(self.instrument.id)
            self.log.warning(f"EXIT long: {decision.reason}")
        elif decision.action == "exit_short":
            self.close_all_positions(self.instrument.id)
            self.log.warning(f"EXIT short: {decision.reason}")
        elif decision.action == "enter_long":
            self.buy()
            self.log.info(f"ENTER long: {decision.reason}")
        elif decision.action == "enter_short":
            self.sell()
            self.log.info(f"ENTER short: {decision.reason}")

    def _extract_liquidation_data(self, data) -> LiquidationMapData | None:
        if isinstance(data, NTLiquidationMapData):
            return data.liq_data
        if isinstance(data, CustomData) and isinstance(data.data, NTLiquidationMapData):
            return data.data.liq_data
        return None

    def _build_market_order(self, side: OrderSide) -> MarketOrder:
        return self.order_factory.market(
            instrument_id=self.instrument.id,
            order_side=side,
            quantity=self.instrument.make_qty(self.trade_size),
            time_in_force=TimeInForce.IOC,
        )

    def _position_state(self) -> PositionState:
        if self.portfolio.is_net_long(self.instrument.id):
            return "long"
        if self.portfolio.is_net_short(self.instrument.id):
            return "short"
        return "flat"
