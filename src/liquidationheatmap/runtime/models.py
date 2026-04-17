from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

class ExecutionMode(str, Enum):
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE_LIMITED = "live_limited"
    LIVE_FULL = "live_full"

class RiskPolicy(BaseModel):
    max_position_size_usd: float = 1000.0
    max_daily_loss_usd: float = 100.0
    max_concurrent_positions: int = 1
    allowed_symbols: List[str] = Field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])
    allowed_venues: List[str] = Field(default_factory=lambda: ["hyperliquid", "binance", "bybit"])
    kill_switch_active: bool = False

class ExecutionAction(BaseModel):
    action_id: str
    signal_id: str
    strategy_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    mode: ExecutionMode
    symbol: str
    side: str
    price: float
    size: float
    status: str  # executed, rejected, canceled
    reason: Optional[str] = None

class RuntimeState(BaseModel):
    mode: ExecutionMode = ExecutionMode.PAPER
    active_positions: int = 0
    daily_loss_usd: float = 0.0
    last_restart: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    kill_switch: bool = False
