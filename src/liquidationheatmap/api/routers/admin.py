import asyncio
import gc
import logging
import time

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from src.liquidationheatmap.api.cache import heatmap_cache
from src.liquidationheatmap.api.metrics import GAP_FILL_DURATION, GAP_FILL_INSERTED_TOTAL
from src.liquidationheatmap.api.shared import _gap_fill_lock, _require_internal_token
from src.liquidationheatmap.ingestion.db_service import DuckDBService
from src.liquidationheatmap.ingestion.gap_fill import run_gap_fill
from src.liquidationheatmap.settings import get_settings

router = APIRouter(prefix="/api/v1", tags=["Admin"])
_settings = get_settings()
logger = logging.getLogger(__name__)


@router.post("/prepare-for-ingestion")
async def prepare_for_ingestion(token_valid: None = Depends(_require_internal_token)):
    """Prepare database for ingestion by closing read-only connections."""
    DuckDBService.set_ingestion_lock()
    closed = DuckDBService.close_all_instances()
    gc.collect()
    logger.info("Admin: closed %d DB singletons via API", closed)
    return {"status": "success", "connections_closed": closed}


@router.post("/refresh-connections")
async def refresh_connections(
    warmup: bool = Query(True, description="Warm up a read-only DuckDB connection after releasing lock"),
    token_valid: None = Depends(_require_internal_token),
):
    """Release ingestion lock and optionally warm up a read connection."""
    DuckDBService.release_ingestion_lock()
    if not warmup:
        logger.info("Admin: ingestion lock released without DuckDB warmup")
        return {"status": "success", "warmup": False}
    try:
        db = DuckDBService(read_only=True)
        db.conn.execute("SELECT 1").fetchone()
        logger.info("Admin: read connections restored and warmed up")
    except Exception as e:
        logger.error(f"Failed to refresh connections: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    return {"status": "success", "warmup": True}


@router.post("/gap-fill")
async def gap_fill(
    dry_run: bool = Query(False, description="Count available data without writing"),
    token_valid: None = Depends(_require_internal_token),
):
    """Run in-process gap-fill from ccxt-data-pipeline Parquet catalog."""
    if _gap_fill_lock.locked():
        return JSONResponse(
            status_code=409,
            content={"status": "conflict", "message": "A gap-fill is already in progress."},
        )

    await _gap_fill_lock.acquire()
    t0 = time.time()
    catalog = str(_settings.ccxt_catalog)
    db_path = str(_settings.db_path)
    symbols = list(_settings.symbols)

    logger.info("Gap-fill started: symbols=%s dry_run=%s", symbols, dry_run)

    try:
        DuckDBService.set_ingestion_lock()
        await asyncio.sleep(1.0)  # Drain

        DuckDBService.close_all_instances()
        gc.collect()

        with GAP_FILL_DURATION.time():
            result = await asyncio.to_thread(run_gap_fill, db_path, catalog, symbols, dry_run)

        elapsed = round(time.time() - t0, 2)
        result["duration_seconds"] = elapsed
        result["status"] = "success"
        logger.info("Gap-fill complete: %d rows in %ss", result["total_inserted"], elapsed)

        for symbol, counts in result.get("symbols", {}).items():
            for data_type, details in counts.items():
                if isinstance(details, dict) and "inserted" in details:
                    GAP_FILL_INSERTED_TOTAL.labels(symbol=symbol, type=data_type).inc(
                        details["inserted"]
                    )

        return result
    except Exception as e:
        logger.error("Gap-fill failed: %s", e, exc_info=True)
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        DuckDBService.release_ingestion_lock()
        _gap_fill_lock.release()
        # Non-blocking warmup
        from src.liquidationheatmap.api.shared import _warmup_read_connection

        asyncio.create_task(_warmup_read_connection())


@router.post("/precompute-heatmap", tags=["Cache"])
async def precompute_heatmap(
    symbol: str = Query("BTCUSDT", pattern="^[A-Z]{6,12}$"),
    interval: str = Query("15m", pattern="^(15m|1h)$"),
    days: int = Query(30, ge=1, le=90),
    token_valid: None = Depends(_require_internal_token),
):
    """Trigger heatmap timeseries pre-computation manually."""
    import subprocess

    cmd = [
        "uv",
        "run",
        "scripts/precompute_heatmap_timeseries.py",
        "--symbol",
        symbol,
        "--interval",
        interval,
        "--days",
        str(days),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return {
            "status": "ok" if result.returncode == 0 else "error",
            "returncode": result.returncode,
            "stdout": result.stdout[-1000:] if result.stdout else "",
            "stderr": result.stderr[-500:] if result.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return JSONResponse(
            status_code=504,
            content={"status": "timeout", "detail": "Pre-computation exceeded 120s"},
        )


@router.get("/cache/stats", tags=["Cache"])
async def get_cache_stats():
    """Get heatmap cache statistics."""
    return heatmap_cache.get_stats()


@router.delete("/cache/clear", tags=["Cache"])
async def clear_cache():
    """Clear heatmap cache."""
    heatmap_cache.clear()
    return {"message": "Cache cleared", "status": "ok"}
