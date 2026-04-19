import pytest
from unittest.mock import MagicMock, patch

from src.liquidationheatmap.nautilus.faults import FaultInjector, FaultPoint


def test_pre_submit_fault_prevents_order_and_leaves_flat():
    injector = FaultInjector(point=FaultPoint.PRE_SUBMIT)
    # mock strategy and node
    strategy = MagicMock()
    strategy.portfolio.is_flat.return_value = True
    
    with pytest.raises(Exception, match="Injected PRE_SUBMIT fault"):
        injector.apply_and_run(strategy)
        
    assert strategy.submit_order.call_count == 0


def test_post_submit_pre_fill_fault():
    injector = FaultInjector(point=FaultPoint.POST_SUBMIT_PRE_FILL)
    strategy = MagicMock()
    
    with pytest.raises(Exception, match="Injected POST_SUBMIT_PRE_FILL fault"):
        injector.apply_and_run(strategy)


def test_open_position_pre_close_fault():
    injector = FaultInjector(point=FaultPoint.OPEN_POSITION_PRE_CLOSE)
    strategy = MagicMock()
    
    with pytest.raises(Exception, match="Injected OPEN_POSITION_PRE_CLOSE fault"):
        injector.apply_and_run(strategy)


def test_post_close_pre_feedback_fault():
    injector = FaultInjector(point=FaultPoint.POST_CLOSE_PRE_FEEDBACK)
    strategy = MagicMock()
    
    with pytest.raises(Exception, match="Injected POST_CLOSE_PRE_FEEDBACK fault"):
        injector.apply_and_run(strategy)


def test_redis_unavailable_fault():
    injector = FaultInjector(point=FaultPoint.REDIS_UNAVAILABLE)
    strategy = MagicMock()
    
    with pytest.raises(Exception, match="Injected REDIS_UNAVAILABLE fault"):
        injector.apply_and_run(strategy)


def test_duckdb_unavailable_fault():
    injector = FaultInjector(point=FaultPoint.DUCKDB_UNAVAILABLE)
    strategy = MagicMock()
    
    with pytest.raises(Exception, match="Injected DUCKDB_UNAVAILABLE fault"):
        injector.apply_and_run(strategy)
