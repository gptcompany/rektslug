import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Mock all nautilus_trader submodules before importing backtest
_NT_MOCKS = [
    "nautilus_trader",
    "nautilus_trader.backtest",
    "nautilus_trader.backtest.engine",
    "nautilus_trader.config",
    "nautilus_trader.core",
    "nautilus_trader.core.data",
    "nautilus_trader.core.datetime",
    "nautilus_trader.model",
    "nautilus_trader.model.currencies",
    "nautilus_trader.model.data",
    "nautilus_trader.model.enums",
    "nautilus_trader.model.identifiers",
    "nautilus_trader.model.instruments",
    "nautilus_trader.model.objects",
    "nautilus_trader.model.orders",
    "nautilus_trader.persistence",
    "nautilus_trader.persistence.catalog",
    "nautilus_trader.trading",
    "nautilus_trader.trading.strategy",
]
for mod in _NT_MOCKS:
    sys.modules.setdefault(mod, MagicMock())

from src.liquidationheatmap.nautilus.backtest import (
    BacktestResult,
    BacktestRunSummary,
    ExecutionAssumptions,
    ReplayBundle,
    export_backtest_result,
    load_backtest_result,
    load_replay_bundle,
    replay_bundle_fingerprint,
    run_liquidation_backtest,
    write_replay_bundle,
)


def test_run_backtest_strict_inputs(tmp_path):
    with pytest.raises(ValueError, match="catalog_path is required"):
        run_liquidation_backtest(
            symbol="BTCUSDT",
            catalog_path=None,
            artifacts_dir=tmp_path / "artifacts",
        )


def test_run_backtest_fails_on_empty_events(tmp_path):
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()

    with pytest.raises(RuntimeError, match="No snapshot timestamps found"):
        run_liquidation_backtest(
            symbol="BTCUSDT",
            catalog_path=str(tmp_path / "catalog"),
            artifacts_dir=artifacts_dir,
        )


def test_write_replay_bundle_round_trip(tmp_path):
    bundle = ReplayBundle(
        artifact_manifest_path="/tmp/manifest.json",
        catalog_path="/tmp/catalog",
        instrument_id="BTCUSDT-PERP.HYPERLIQUID",
        strategy_config={"trade_size": 0.001, "imbalance_threshold": 0.6},
        execution_assumptions=ExecutionAssumptions(fill_delay_ns=0, slippage_bps=1.5, fee_bps=0.5),
        expert_ids=["v1"],
        start_time="2026-04-14T00:00:00Z",
        end_time="2026-04-14T12:00:00Z",
    )
    output_path = tmp_path / "bundle.json"

    write_replay_bundle(bundle, output_path)
    loaded = load_replay_bundle(output_path)

    assert loaded == bundle
    assert replay_bundle_fingerprint(loaded) == replay_bundle_fingerprint(bundle)


def test_export_backtest_result_round_trip(tmp_path):
    bundle = ReplayBundle(
        artifact_manifest_path="/tmp/manifest.json",
        catalog_path="/tmp/catalog",
        instrument_id="BTCUSDT-PERP.BYBIT",
        strategy_config={"trade_size": 0.001, "imbalance_threshold": 0.6},
        execution_assumptions=ExecutionAssumptions(fill_delay_ns=1000, slippage_bps=2.0, fee_bps=1.0),
        expert_ids=["bybit_standard"],
        start_time="2026-04-07T00:00:00Z",
        end_time="2026-04-07T12:00:00Z",
    )
    summary = BacktestRunSummary(
        orders_total_count=4,
        orders_open_count=0,
        orders_closed_count=4,
        positions_total_count=2,
        positions_open_count=0,
        positions_closed_count=2,
        order_status_counts={"FILLED": 4},
        realized_pnl_by_currency={"USDT": 12.5},
        total_pnl_by_currency={"USDT": 12.5},
        unrealized_pnl_by_currency={"USDT": 0.0},
        strategy_states={"liqmap": "stopped"},
    )
    result = BacktestResult(
        bundle=bundle,
        summary=summary,
        results_path=None,
        generated_at="2026-04-17T12:00:00+00:00",
        rektslug_version="0.1.0",
    )

    result_path = export_backtest_result(result, tmp_path / "results")
    loaded = load_backtest_result(result_path)

    assert loaded.bundle == bundle
    assert loaded.summary == summary
    assert loaded.results_path == str(result_path)


@pytest.mark.parametrize(
    "sample_path",
    [
        Path("specs/035-nautilus-event-driven-backtest-hardening/samples/hyperliquid_replay_bundle.json"),
        Path("specs/035-nautilus-event-driven-backtest-hardening/samples/modeled_snapshot_replay_bundle.json"),
    ],
)
def test_sample_replay_bundles_are_loadable_and_deterministic(sample_path):
    loaded_once = load_replay_bundle(sample_path)
    loaded_twice = load_replay_bundle(sample_path)

    assert replay_bundle_fingerprint(loaded_once) == replay_bundle_fingerprint(loaded_twice)
    assert loaded_once.instrument_id.endswith(("HYPERLIQUID", "BYBIT"))
