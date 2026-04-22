"""Signal status and metrics endpoints.

User Story 4: API Integration for signal monitoring.
"""

import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Query

from src.liquidationheatmap.signals import (
    FeedbackDBService,
    SignalMetrics,
    SignalStatus,
    get_redis_client,
)
from src.liquidationheatmap.signals.status_store import load_signal_status_metrics

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/signals", tags=["signals"])

# Cached last publish timestamp (in-memory)
_last_publish_timestamp: datetime | None = None


def set_last_publish(timestamp: datetime) -> None:
    """Update last publish timestamp (called by SignalPublisher)."""
    global _last_publish_timestamp
    _last_publish_timestamp = timestamp


@router.get("/status", response_model=SignalStatus)
async def get_signal_status():
    """Get signal system status.

    Returns connection state, last publish time, and 24h counts.

    Returns:
        SignalStatus with connected, last_publish, signals_published_24h, feedback_received_24h
    """
    # Check Redis connection
    redis_client = get_redis_client()
    connected = redis_client.is_connected

    # Get feedback count from DuckDB (read_only to avoid lock conflicts with ingestion)
    feedback_24h = 0
    db_service = None
    try:
        db_service = FeedbackDBService(read_only=True)
        metrics = db_service.get_rolling_metrics("BTCUSDT", hours=24)
        feedback_24h = metrics.get("total", 0)
    except Exception as e:
        logger.warning(f"Could not fetch feedback metrics: {e}")
    finally:
        if db_service is not None:
            db_service.close()

    persisted_last_publish, signals_24h = load_signal_status_metrics(redis_client)
    effective_last_publish = persisted_last_publish or _last_publish_timestamp

    return SignalStatus(
        connected=connected,
        last_publish=effective_last_publish,
        signals_published_24h=signals_24h,
        feedback_received_24h=feedback_24h,
    )


@router.get("/continuous-report")
async def get_continuous_report():
    """Get machine-readable continuous report required by G3 acceptance.

    Returns non-null lifecycle counters with feedback_persisted measured
    from actual DuckDB writes.
    """
    from src.liquidationheatmap.signals.models import ContinuousReport

    db_service = None
    try:
        db_service = FeedbackDBService(read_only=True)
        return db_service.get_continuous_report()
    except Exception as e:
        logger.error(f"Error fetching continuous report: {e}")
        return ContinuousReport()
    finally:
        if db_service is not None:
            db_service.close()


@router.get("/metrics", response_model=SignalMetrics)
async def get_signal_metrics(
    symbol: str = Query(
        "BTCUSDT",
        description="Trading pair symbol",
        pattern="^[A-Z]{6,12}$",
    ),
    window: Literal["1h", "24h", "7d"] = Query(
        "24h",
        description="Metric time window",
    ),
):
    """Get signal performance metrics.

    Returns hit_rate, signal count, and avg_pnl for the specified window.

    Args:
        symbol: Trading pair (e.g., BTCUSDT)
        window: Time window ('1h', '24h', '7d')

    Returns:
        SignalMetrics with hit_rate, total_signals, feedback_count, avg_pnl
    """
    # Map window to hours
    window_hours = {"1h": 1, "24h": 24, "7d": 168}
    hours = window_hours.get(window, 24)

    db_service = None
    try:
        db_service = FeedbackDBService(read_only=True)
        metrics = db_service.get_rolling_metrics(symbol, hours=hours)

        return SignalMetrics(
            symbol=symbol,
            window=window,
            hit_rate=metrics.get("hit_rate", 0.0),
            total_signals=metrics.get("total", 0),
            feedback_count=metrics.get("total", 0),
            avg_pnl=metrics.get("avg_pnl", 0.0),
        )
    except Exception as e:
        logger.error(f"Error fetching metrics for {symbol}: {e}")
        # Return empty metrics on error
        return SignalMetrics(
            symbol=symbol,
            window=window,
            hit_rate=0.0,
            total_signals=0,
            feedback_count=0,
            avg_pnl=0.0,
        )
    finally:
        if db_service is not None:
            db_service.close()


@router.get("/circuit-breaker")
async def get_circuit_breaker_status(
    symbol: str = Query(
        "BTCUSDT",
        description="Trading pair symbol",
        pattern="^[A-Z]{6,12}$",
    ),
):
    """Get circuit breaker status for a symbol."""
    from src.liquidationheatmap.signals.circuit_breaker import CircuitBreakerStore

    store = None
    try:
        store = CircuitBreakerStore(read_only=True)
        state = store.load_state(symbol)
        if state is None:
            return {
                "symbol": symbol,
                "tripped": False,
                "trip_reason": None,
                "consecutive_losses": 0,
                "session_pnl": 0.0,
            }
        return {
            "symbol": state.symbol,
            "tripped": state.tripped,
            "trip_reason": state.trip_reason.value if state.trip_reason else None,
            "consecutive_losses": state.consecutive_losses,
            "session_pnl": state.session_pnl,
        }
    except Exception as e:
        logger.error(f"Error fetching circuit breaker state for {symbol}: {e}")
        return {"symbol": symbol, "tripped": False, "error": str(e)}
    finally:
        if store is not None:
            store.close()


@router.get("/health")
async def signal_health():
    """Health check for signal subsystem.

    Returns:
        dict: Status of Redis connection and signal components
    """
    redis_client = get_redis_client()

    return {
        "status": "ok" if redis_client.is_connected else "degraded",
        "redis_connected": redis_client.is_connected,
        "message": "Signals operational"
        if redis_client.is_connected
        else "Redis unavailable, running in degraded mode",
    }
