import logging
from src.liquidationheatmap.runtime.models import RiskPolicy, RuntimeState

logger = logging.getLogger(__name__)

class RiskEngine:
    """Enforces hard risk limits and kill-switch controls."""

    def __init__(self, policy: RiskPolicy, state: RuntimeState):
        self.policy = policy
        self.state = state

    def validate_action(
        self, 
        symbol: str, 
        venue: str, 
        size_usd: float
    ) -> tuple[bool, str | None]:
        """Validate an execution action against risk policy."""
        
        # 1. Kill switch
        if self.policy.kill_switch_active or self.state.kill_switch:
            return False, "kill_switch_active"
            
        # 2. Allowlist
        if symbol not in self.policy.allowed_symbols:
            return False, f"symbol_not_allowed: {symbol}"
        if venue.lower() not in [v.lower() for v in self.policy.allowed_venues]:
            return False, f"venue_not_allowed: {venue}"
            
        # 3. Position size
        if size_usd > self.policy.max_position_size_usd:
            return False, f"size_exceeds_limit: {size_usd} > {self.policy.max_position_size_usd}"
            
        # 4. Concurrency
        if self.state.active_positions >= self.policy.max_concurrent_positions:
            return False, "max_concurrent_positions_reached"
            
        # 5. Daily loss
        if self.state.daily_loss_usd >= self.policy.max_daily_loss_usd:
            return False, "max_daily_loss_reached"
            
        return True, None

    def update_state(self, action_outcome: str, size_usd: float = 0, pnl_usd: float = 0):
        """Update runtime state after an action."""
        if action_outcome == "opened":
            self.state.active_positions += 1
        elif action_outcome == "closed":
            self.state.active_positions = max(0, self.state.active_positions - 1)
            self.state.daily_loss_usd -= pnl_usd # Negative PnL increases daily loss
