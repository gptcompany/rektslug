import pytest
from datetime import datetime, timedelta, timezone
from src.liquidationheatmap.runtime.executor import HardenedExecutor
from src.liquidationheatmap.runtime.models import ExecutionMode, RiskPolicy

def test_executor_rejects_stale_signal():
    executor = HardenedExecutor(stale_seconds=60)
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=120)
    
    success, reason = executor.process_signal(
        signal_id="sig1", symbol="BTCUSDT", venue="hyperliquid",
        side="long", price=40000.0, size_usd=100.0,
        signal_timestamp=stale_time
    )
    
    assert success is False
    assert "stale_signal" in reason

def test_executor_rejects_duplicate_signal():
    executor = HardenedExecutor()
    now = datetime.now(timezone.utc)
    
    # First signal succeeds
    success, _ = executor.process_signal(
        signal_id="sig1", symbol="BTCUSDT", venue="hyperliquid",
        side="long", price=40000.0, size_usd=100.0,
        signal_timestamp=now
    )
    assert success is True
    
    # Second same signal fails
    success, reason = executor.process_signal(
        signal_id="sig1", symbol="BTCUSDT", venue="hyperliquid",
        side="long", price=40000.0, size_usd=100.0,
        signal_timestamp=now
    )
    assert success is False
    assert reason == "duplicate_signal"

def test_executor_enforces_risk_limits():
    policy = RiskPolicy(max_position_size_usd=500.0)
    executor = HardenedExecutor(risk_policy=policy)
    now = datetime.now(timezone.utc)
    
    # Large order fails
    success, reason = executor.process_signal(
        signal_id="sig1", symbol="BTCUSDT", venue="hyperliquid",
        side="long", price=40000.0, size_usd=1000.0,
        signal_timestamp=now
    )
    assert success is False
    assert "size_exceeds_limit" in reason

def test_executor_audit_trail():
    executor = HardenedExecutor()
    now = datetime.now(timezone.utc)
    
    executor.process_signal("sig1", "BTCUSDT", "hyperliquid", "long", 40000.0, 100.0, now)
    executor.process_signal("sig1", "BTCUSDT", "hyperliquid", "long", 40000.0, 100.0, now) # duplicate
    
    audit = executor.get_audit_trail()
    assert len(audit) == 2
    assert audit[0].status == "executed"
    assert audit[1].status == "rejected"

def test_executor_persistence(tmp_path):
    state_file = tmp_path / "runtime_state.json"
    executor = HardenedExecutor()
    now = datetime.now(timezone.utc)
    
    executor.process_signal("sig1", "BTCUSDT", "hyperliquid", "long", 40000.0, 100.0, now)
    executor.save_state(state_file)
    
    # New executor instance loaded from file
    new_executor = HardenedExecutor.load_state(state_file)
    assert new_executor.mode == executor.mode
    assert "sig1" in new_executor.signal_safety.seen_signals
    assert len(new_executor.audit_log) == 1
    
    # Try to process same signal again, should fail even after restart
    success, reason = new_executor.process_signal("sig1", "BTCUSDT", "hyperliquid", "long", 40000.0, 100.0, now)
    assert success is False
    assert reason == "duplicate_signal"
