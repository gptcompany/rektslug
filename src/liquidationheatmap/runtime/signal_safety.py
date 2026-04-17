import logging
from datetime import datetime, timezone
from typing import Set
from src.liquidationheatmap.runtime.models import ExecutionMode

logger = logging.getLogger(__name__)

class SignalSafetyPolicy:
    """Enforces freshness and idempotency for liquidation signals."""

    def __init__(self, stale_seconds: int = 300):
        self.stale_seconds = stale_seconds
        self.seen_signals: Set[str] = set()

    def validate_signal(
        self, 
        signal_id: str, 
        signal_timestamp: datetime,
        current_mode: ExecutionMode
    ) -> tuple[bool, str | None]:
        """Validate a signal against freshness and idempotency rules."""
        
        # 1. Idempotency check
        if signal_id in self.seen_signals:
            return False, "duplicate_signal"
            
        # 2. Freshness check
        now = datetime.now(timezone.utc)
        if signal_timestamp.tzinfo is None:
            signal_timestamp = signal_timestamp.replace(tzinfo=timezone.utc)
            
        age_seconds = (now - signal_timestamp).total_seconds()
        if age_seconds > self.stale_seconds:
            return False, f"stale_signal (age={age_seconds:.1f}s, max={self.stale_seconds}s)"
            
        # 3. Mode compatibility (placeholder for more complex rules)
        if current_mode == ExecutionMode.BACKTEST:
             # In backtest mode, we might allow stale signals if replaying history
             pass
             
        return True, None

    def mark_executed(self, signal_id: str):
        """Record a signal as executed to prevent duplicate actions."""
        self.seen_signals.add(signal_id)
