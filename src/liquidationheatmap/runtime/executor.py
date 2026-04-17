import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.liquidationheatmap.runtime.models import (
    ExecutionAction,
    ExecutionMode,
    RiskPolicy,
    RuntimeState,
)
from src.liquidationheatmap.runtime.risk import RiskEngine
from src.liquidationheatmap.runtime.signal_safety import SignalSafetyPolicy

logger = logging.getLogger(__name__)

class HardenedExecutor:
    """Orchestrates signal safety, risk checks, and execution audit."""

    def __init__(
        self, 
        mode: ExecutionMode = ExecutionMode.PAPER,
        risk_policy: Optional[RiskPolicy] = None,
        stale_seconds: int = 300
    ):
        self.mode = mode
        self.state = RuntimeState(mode=mode)
        self.risk_engine = RiskEngine(risk_policy or RiskPolicy(), self.state)
        self.signal_safety = SignalSafetyPolicy(stale_seconds=stale_seconds)
        self.audit_log: list[ExecutionAction] = []

    def process_signal(
        self, 
        signal_id: str, 
        symbol: str, 
        venue: str,
        side: str,
        price: float,
        size_usd: float,
        signal_timestamp: datetime,
        strategy_id: str = "default"
    ) -> tuple[bool, str | None]:
        """Verify safety and risk before allowing an execution action."""
        
        # 1. Signal Safety
        is_safe, safety_reason = self.signal_safety.validate_signal(
            signal_id, signal_timestamp, self.mode
        )
        if not is_safe:
            self._log_action(signal_id, strategy_id, symbol, side, price, size_usd, "rejected", safety_reason)
            return False, safety_reason

        # 2. Risk Checks
        is_allowed, risk_reason = self.risk_engine.validate_action(symbol, venue, size_usd)
        if not is_allowed:
            self._log_action(signal_id, strategy_id, symbol, side, price, size_usd, "rejected", risk_reason)
            return False, risk_reason

        # 3. Success
        self.signal_safety.mark_executed(signal_id)
        self.risk_engine.update_state("opened", size_usd=size_usd)
        action = self._log_action(signal_id, strategy_id, symbol, side, price, size_usd, "executed")
        
        logger.info(f"Signal {signal_id} accepted for execution ({self.mode}): {side} {symbol} at {price}")
        return True, None

    def _log_action(
        self, 
        signal_id: str, 
        strategy_id: str,
        symbol: str,
        side: str,
        price: float,
        size_usd: float,
        status: str,
        reason: Optional[str] = None
    ) -> ExecutionAction:
        action = ExecutionAction(
            action_id=str(uuid.uuid4()),
            signal_id=signal_id,
            strategy_id=strategy_id,
            mode=self.mode,
            symbol=symbol,
            side=side,
            price=price,
            size=size_usd,
            status=status,
            reason=reason
        )
        self.audit_log.append(action)
        return action

    def get_audit_trail(self) -> list[ExecutionAction]:
        return self.audit_log

    def save_state(self, path: str | Path):
        """Save executor state, policy, and audit trail to disk."""
        import json
        data = {
            "state": self.state.model_dump(),
            "risk_policy": self.risk_engine.policy.model_dump(),
            "stale_seconds": self.signal_safety.stale_seconds,
            "seen_signals": list(self.signal_safety.seen_signals),
            "audit_log": [action.model_dump() for action in self.audit_log],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        logger.info(f"Executor state saved to {path}")

    @classmethod
    def load_state(cls, path: str | Path) -> "HardenedExecutor":
        """Load executor state, policy, and audit trail from disk."""
        import json
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        risk_policy = RiskPolicy(**data["risk_policy"]) if "risk_policy" in data else RiskPolicy()
        stale_seconds = data.get("stale_seconds", 300)

        executor = cls(
            mode=ExecutionMode(data["state"]["mode"]),
            risk_policy=risk_policy,
            stale_seconds=stale_seconds,
        )
        executor.state = RuntimeState(**data["state"])
        executor.signal_safety.seen_signals = set(data["seen_signals"])
        executor.audit_log = [ExecutionAction(**action) for action in data["audit_log"]]
        return executor
