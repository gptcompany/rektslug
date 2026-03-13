import os
import asyncio
import logging
from typing import Optional, List, Set, Dict, Any
from fastapi import Header, HTTPException, status

from src.liquidationheatmap.ingestion.db_service import IngestionLockError

logger = logging.getLogger(__name__)

# --- Configuration & Constants ---

SUPPORTED_SYMBOLS = {
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "AVAXUSDT", "DOGEUSDT", "DOTUSDT", "LINKUSDT",
    "MATICUSDT", "SHIBUSDT", "TRXUSDT", "UNIUSDT", "WBTCUSDT"
}

SUPPORTED_EXCHANGES = {
    "binance": {"name": "Binance", "status": "active"},
    "bybit": {"name": "Bybit", "status": "active"},
    "hyperliquid": {"name": "Hyperliquid", "status": "active"},
}

# Time window configurations for timeseries data
TIME_WINDOW_CONFIG = {
    "1h": {"lookback_days": 1, "default_interval": "1m"},
    "4h": {"lookback_days": 1, "default_interval": "1m"},
    "12h": {"lookback_days": 1, "default_interval": "1m"},
    "1d": {"lookback_days": 1, "default_interval": "1m"},
    "48h": {"lookback_days": 2, "default_interval": "1m"},
    "3d": {"lookback_days": 3, "default_interval": "5m"},
    "7d": {"lookback_days": 7, "default_interval": "5m"},
    "14d": {"lookback_days": 14, "default_interval": "15m"},
    "30d": {"lookback_days": 30, "default_interval": "15m"},
    "90d": {"lookback_days": 90, "default_interval": "1h"},
    "1y": {"lookback_days": 365, "default_interval": "4h"},
}

# --- Shared State ---

_gap_fill_lock = asyncio.Lock()

def get_cors_origins() -> List[str]:
    """Get allowed CORS origins from environment."""
    origins = os.getenv("CORS_ORIGINS", "*")
    if origins == "*":
        return ["*"]
    return [o.strip() for o in origins.split(",")]

async def _warmup_read_connection():
    """Warms up DuckDB read connection in a background thread."""
    from src.liquidationheatmap.ingestion.db_service import DuckDBService
    try:
        if DuckDBService.is_ingestion_locked():
            logger.info("Shared: skipping read warmup while ingestion lock is active")
            return
        # 440GB DB takes time to read metadata; do it in a thread to keep event loop alive
        db = await asyncio.to_thread(DuckDBService, read_only=True)
        await asyncio.to_thread(db.conn.execute, "SELECT 1")
        logger.info("Shared: read connections restored (background)")
    except IngestionLockError:
        logger.info("Shared: read warmup deferred by ingestion lock")
    except Exception as e:
        logger.warning("Shared: failed to restore read connections: %s", e)


def _require_internal_token(
    x_internal_token: Optional[str] = Header(None),
):
    """FastAPI dependency: reject requests without a valid internal token."""
    from src.liquidationheatmap.settings import get_settings
    settings = get_settings()
    
    if not settings.internal_api_token:
        return  # Auth disabled

    if x_internal_token != settings.internal_api_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Valid X-Internal-Token header required for this operation."
        )
