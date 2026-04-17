"""Demo backtest runner: liquidation map events as auxiliary signals.

Usage:
    uv run python -m src.liquidationheatmap.nautilus.backtest \
        --symbol BTCUSDT \
        --catalog-path /media/sam/1TB/ccxt-data-pipeline/data/catalog \
        --expert-ids v1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from src.liquidationheatmap.nautilus import _check_nautilus

_check_nautilus()

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig  # noqa: E402
from nautilus_trader.config import LoggingConfig  # noqa: E402
from nautilus_trader.model.currencies import USDT  # noqa: E402
from nautilus_trader.model.data import BarType  # noqa: E402
from nautilus_trader.model.enums import AccountType, OmsType  # noqa: E402
from nautilus_trader.model.identifiers import ClientId, InstrumentId, TraderId, Venue  # noqa: E402
from nautilus_trader.model.objects import Money  # noqa: E402
from nautilus_trader.persistence.catalog import ParquetDataCatalog  # noqa: E402

from src.liquidationheatmap.nautilus.loader import load_liquidation_events  # noqa: E402
from src.liquidationheatmap.nautilus.raw_catalog import load_raw_market_data_bundle  # noqa: E402
from src.liquidationheatmap.nautilus.strategy import (  # noqa: E402
    LiquidationAwareConfig,
    LiquidationAwareStrategy,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExecutionAssumptions:
    """Execution assumptions for the backtest replay."""

    fill_delay_ns: int = 0
    slippage_bps: float = 0.0
    fee_bps: float = 0.0
    funding_enabled: bool = False


@dataclass(frozen=True)
class ReplayBundle:
    """A versioned bundle of all inputs needed to reproduce a backtest run."""

    artifact_manifest_path: str | None
    catalog_path: str
    instrument_id: str
    strategy_config: dict[str, Any]
    execution_assumptions: ExecutionAssumptions
    expert_ids: list[str]
    start_time: str | None = None
    end_time: str | None = None


@dataclass(frozen=True)
class BacktestResult:
    """Machine-readable result of a backtest run, suitable for audit."""

    bundle: ReplayBundle
    summary: BacktestRunSummary
    results_path: str | None
    generated_at: str
    rektslug_version: str


@dataclass(frozen=True)
class BacktestRunSummary:
    """Minimal execution summary for a completed Nautilus backtest run."""

    orders_total_count: int
    orders_open_count: int
    orders_closed_count: int
    positions_total_count: int
    positions_open_count: int
    positions_closed_count: int
    order_status_counts: dict[str, int]
    realized_pnl_by_currency: dict[str, float]
    total_pnl_by_currency: dict[str, float]
    unrealized_pnl_by_currency: dict[str, float]
    strategy_states: dict[str, str]


def _default_loader_ids(exchange: str) -> list[str]:
    if exchange == "hyperliquid":
        return ["v1"]
    if exchange == "bybit":
        return ["bybit_standard"]
    if exchange == "binance":
        return ["binance_standard"]
    return ["v1"]


def run_liquidation_backtest(
    symbol: str = "BTCUSDT",
    exchange: str = "hyperliquid",
    expert_ids: list[str] | None = None,
    catalog_path: str | None = None,
    artifacts_dir: str | Path | None = None,
    start: str | None = None,
    end: str | None = None,
    initial_capital: float = 100_000.0,
    attach_strategy: bool = True,
    trade_size: float = 0.001,
    proximity_threshold: float = 0.02,
    imbalance_threshold: float = 0.6,
    reversal_bias: bool = True,
    run_engine: bool = False,
    execution_assumptions: ExecutionAssumptions | None = None,
) -> BacktestEngine | BacktestResult:
    """Run a backtest with liquidation map events alongside market data.

    Args:
        symbol: Trading pair.
        exchange: Exchange name for venue config.
        expert_ids: Expert variants to include as events.
        catalog_path: Path to ParquetDataCatalog with market data.
        start: Start date filter (ISO format).
        end: End date filter (ISO format).
        initial_capital: Starting balance in USDT.
        execution_assumptions: Hardened assumptions for fills/fees/etc.

    Returns:
        The BacktestEngine or a BacktestResult after run.
    """
    if not catalog_path:
        raise ValueError("catalog_path is required for hardened backtest execution")

    expert_ids = expert_ids or _default_loader_ids(exchange)
    execution_assumptions = execution_assumptions or ExecutionAssumptions()
    detected_bar_type: BarType | None = None

    # 1. Create engine
    engine = BacktestEngine(
        config=BacktestEngineConfig(
            trader_id=TraderId("LIQMAP-BACKTEST-001"),
            logging=LoggingConfig(log_level="INFO"),
        )
    )

    # 2. Add venue
    venue_name = exchange.upper()
    engine.add_venue(
        venue=Venue(venue_name),
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=USDT,
        starting_balances=[Money(initial_capital, USDT)],
    )

    # 3. Load market data from catalog
    catalog = ParquetDataCatalog(str(catalog_path))
    instrument_id = f"{symbol}-PERP.{venue_name}"

    instruments = catalog.instruments(instrument_ids=[instrument_id])
    if instruments:
        instrument = instruments[0]
        engine.add_instrument(instrument)

        # Try bars first, then trade ticks
        bars = catalog.bars(instrument_ids=[instrument_id], start=start, end=end)
        if bars:
            engine.add_data(bars)
            logger.info("Loaded %d bars for %s", len(bars), instrument_id)
            detected_bar_type = bars[0].bar_type
            ticks = catalog.trade_ticks(instrument_ids=[instrument_id], start=start, end=end)
            if ticks:
                engine.add_data(ticks)
                logger.info("Loaded %d trade ticks for %s", len(ticks), instrument_id)
        else:
            ticks = catalog.trade_ticks(instrument_ids=[instrument_id], start=start, end=end)
            if ticks:
                engine.add_data(ticks)
                logger.info("Loaded %d trade ticks for %s", len(ticks), instrument_id)
            else:
                instruments = []

    if not instruments:
        logger.warning(
            "ParquetDataCatalog did not expose Nautilus-native market data for %s. "
            "Falling back to raw parquet conversion.",
            instrument_id,
        )
        raw_bundle = load_raw_market_data_bundle(
            symbol=symbol,
            exchange=exchange,
            catalog_root=catalog_path,
            timeframe="1m",
            start=start,
            end=end,
        )
        if raw_bundle is None:
            raise RuntimeError(f"No market data found for {instrument_id} in {catalog_path}")

        engine.add_instrument(raw_bundle.instrument)
        if raw_bundle.bars:
            engine.add_data(raw_bundle.bars)
            detected_bar_type = raw_bundle.bar_type
            logger.info(
                "Loaded %d fallback bars for %s from raw parquet",
                len(raw_bundle.bars),
                raw_bundle.instrument.id,
            )
            if raw_bundle.trade_ticks:
                engine.add_data(raw_bundle.trade_ticks)
                logger.info(
                    "Loaded %d fallback trade ticks for %s from raw parquet",
                    len(raw_bundle.trade_ticks),
                    raw_bundle.instrument.id,
                )
        elif raw_bundle.trade_ticks:
            engine.add_data(raw_bundle.trade_ticks)
            logger.info(
                "Loaded %d fallback trade ticks for %s from raw parquet",
                len(raw_bundle.trade_ticks),
                raw_bundle.instrument.id,
            )
        else:
            raise RuntimeError(f"Fallback raw parquet conversion yielded no bars/ticks for {instrument_id}")

    # 4. Load liquidation events
    liq_events = load_liquidation_events(
        symbol=symbol,
        exchange=exchange,
        expert_ids=expert_ids,
        artifacts_dir=artifacts_dir,
        strict=True,
    )
    engine.add_data(liq_events, sort=True, client_id=ClientId("REKTSLUG"))
    logger.info("Added %d liquidation map events", len(liq_events))

    # 5. Log summary
    logger.info(
        "Backtest ready: %s on %s, %d expert(s), capital=%.0f USDT",
        symbol,
        exchange,
        len(expert_ids),
        initial_capital,
    )

    strategy_config = {
        "instrument_id": instrument_id,
        "trade_size": trade_size,
        "proximity_threshold": proximity_threshold,
        "imbalance_threshold": imbalance_threshold,
        "reversal_bias": reversal_bias,
    }

    if attach_strategy:
        if detected_bar_type is None:
            logger.warning(
                "Strategy attachment requested but no bar_type was detected from catalog data. "
                "Attach a strategy later once a Nautilus-compatible catalog is available."
            )
        else:
            strategy = LiquidationAwareStrategy(
                LiquidationAwareConfig(
                    instrument_id=InstrumentId.from_str(instrument_id),
                    client_id=ClientId("REKTSLUG"),
                    bar_type=detected_bar_type,
                    trade_size=Decimal(str(trade_size)),
                    proximity_threshold=proximity_threshold,
                    imbalance_threshold=imbalance_threshold,
                    reversal_bias=reversal_bias,
                )
            )
            engine.add_strategy(strategy)
            logger.info(
                "Attached LiquidationAwareStrategy to %s with trade_size=%s",
                instrument_id,
                trade_size,
            )

    if run_engine:
        engine.run()
        
        bundle = ReplayBundle(
            artifact_manifest_path=str(artifacts_dir) if artifacts_dir else None,
            catalog_path=str(catalog_path),
            instrument_id=instrument_id,
            strategy_config=strategy_config,
            execution_assumptions=execution_assumptions,
            expert_ids=expert_ids,
            start_time=start,
            end_time=end,
        )
        
        summary = summarize_backtest_engine(engine)
        
        return BacktestResult(
            bundle=bundle,
            summary=summary,
            results_path=None,
            generated_at=datetime.now(timezone.utc).isoformat(),
            rektslug_version=os.environ.get("REKTSLUG_VERSION", "0.1.0"),
        )

    return engine


def summarize_backtest_engine(engine: BacktestEngine) -> BacktestRunSummary:
    """Collect a minimal execution summary from a backtest engine."""
    order_status_counts: dict[str, int] = {}
    for order in engine.cache.orders():
        status_value = getattr(order, "status_string", None)
        if callable(status_value):
            status = status_value()
        elif status_value is not None:
            status = str(status_value)
        else:
            status = str(getattr(order, "status", "UNKNOWN"))
        order_status_counts[status] = order_status_counts.get(status, 0) + 1

    return BacktestRunSummary(
        orders_total_count=engine.cache.orders_total_count(),
        orders_open_count=engine.cache.orders_open_count(),
        orders_closed_count=engine.cache.orders_closed_count(),
        positions_total_count=engine.cache.positions_total_count(),
        positions_open_count=engine.cache.positions_open_count(),
        positions_closed_count=engine.cache.positions_closed_count(),
        order_status_counts=order_status_counts,
        realized_pnl_by_currency=_money_map_to_dict(engine.portfolio.realized_pnls()),
        total_pnl_by_currency=_money_map_to_dict(engine.portfolio.total_pnls()),
        unrealized_pnl_by_currency=_money_map_to_dict(engine.portfolio.unrealized_pnls()),
        strategy_states=engine.trader.strategy_states(),
    )


def _money_map_to_dict(values) -> dict[str, float]:
    return {currency.code: money.as_double() for currency, money in values.items()}


def _json_default_serializer(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, Path):
        return str(obj)
    if hasattr(obj, "__dict__"):
        return asdict(obj)
    return str(obj)


def replay_bundle_to_dict(bundle: ReplayBundle) -> dict[str, Any]:
    return asdict(bundle)


def replay_bundle_fingerprint(bundle: ReplayBundle) -> str:
    payload = json.dumps(replay_bundle_to_dict(bundle), sort_keys=True, default=_json_default_serializer)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_replay_bundle(bundle: ReplayBundle, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(replay_bundle_to_dict(bundle), indent=2, default=_json_default_serializer), encoding="utf-8")
    return path


def load_replay_bundle(path: Path | str) -> ReplayBundle:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    payload["execution_assumptions"] = ExecutionAssumptions(**payload["execution_assumptions"])
    return ReplayBundle(**payload)


def load_backtest_result(path: Path | str) -> BacktestResult:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    payload["bundle"]["execution_assumptions"] = ExecutionAssumptions(**payload["bundle"]["execution_assumptions"])
    payload["bundle"] = ReplayBundle(**payload["bundle"])
    payload["summary"] = BacktestRunSummary(**payload["summary"])
    return BacktestResult(**payload)


def export_backtest_result(result: BacktestResult, output_dir: Path | str) -> Path:
    """Save a backtest result and its replay bundle as machine-readable JSON."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Clean timestamp for filename
    ts_str = result.generated_at.replace(":", "-").replace(".", "-")
    filename = f"backtest_result_{result.bundle.instrument_id}_{ts_str}.json"
    file_path = output_path / filename

    payload = asdict(result)
    payload["results_path"] = str(file_path)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=_json_default_serializer)

    logger.info("Exported backtest result to %s", file_path)
    return file_path


def main():
    parser = argparse.ArgumentParser(description="Liquidation Map Backtest Demo")
    parser.add_argument("--symbol", default="BTCUSDT", help="Trading pair")
    parser.add_argument("--exchange", default="hyperliquid", help="Exchange name")
    parser.add_argument("--expert-ids", nargs="+", help="Expert variants/model ids to load")
    parser.add_argument("--catalog-path", help="Path to ParquetDataCatalog")
    parser.add_argument("--artifacts-dir", help="Override liquidation artifact root")
    parser.add_argument("--start", help="Start date (ISO format)")
    parser.add_argument("--end", help="End date (ISO format)")
    parser.add_argument("--capital", type=float, default=100_000.0, help="Initial capital (USDT)")
    parser.add_argument("--trade-size", type=float, default=0.001, help="Order size per trade")
    parser.add_argument(
        "--no-strategy",
        action="store_true",
        help="Do not attach LiquidationAwareStrategy automatically",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Run the engine immediately after loading data and attaching strategy",
    )
    args = parser.parse_args()

    engine_or_result = run_liquidation_backtest(
        symbol=args.symbol,
        exchange=args.exchange,
        expert_ids=args.expert_ids,
        catalog_path=args.catalog_path,
        artifacts_dir=args.artifacts_dir,
        start=args.start,
        end=args.end,
        initial_capital=args.capital,
        attach_strategy=not args.no_strategy,
        trade_size=args.trade_size,
        run_engine=args.run,
    )

    if not args.run:
        logger.info("Engine created. Use --run to execute immediately.")
    else:
        result = engine_or_result
        logger.info("Backtest summary: %s", asdict(result.summary))
        if result.summary.order_status_counts.get("DENIED", 0):
            logger.warning("Replay produced denied orders: %s", result.summary.order_status_counts)

        # Export machine-readable result for audit
        output_dir = Path("data/backtest_results")
        export_path = export_backtest_result(result, output_dir)
        print(f"RESULT_ARTIFACT={export_path}")

    return engine_or_result


if __name__ == "__main__":
    main()
