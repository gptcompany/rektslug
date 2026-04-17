import pytest
import sys
from unittest.mock import MagicMock

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

from pathlib import Path
from src.liquidationheatmap.nautilus.backtest import run_liquidation_backtest

def test_run_backtest_strict_inputs(tmp_path):
    # T003R: Add failing tests for missing/ambiguous replay inputs
    # Currently run_liquidation_backtest might only log warnings.
    # We want it to be strict.
    
    # Missing catalog
    with pytest.raises(ValueError, match="catalog_path is required"):
        run_liquidation_backtest(
            symbol="BTCUSDT",
            catalog_path=None,
            artifacts_dir=tmp_path / "artifacts"
        )

def test_run_backtest_fails_on_empty_events(tmp_path):
    # artifacts_dir exists but is empty
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    
    # Strict mode raises when no snapshot timestamps are found for symbol
    with pytest.raises(RuntimeError, match="No snapshot timestamps found"):
        run_liquidation_backtest(
            symbol="BTCUSDT",
            catalog_path=str(tmp_path / "catalog"),
            artifacts_dir=artifacts_dir
        )
