import gc
import time
import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, Header
from fastapi.responses import JSONResponse

from src.liquidationheatmap.ingestion.db_service import DuckDBService
from src.liquidationheatmap.ingestion.gap_fill import run_gap_fill
from src.liquidationheatmap.settings import get_settings
from src.liquidationheatmap.api.shared import _require_internal_token, _gap_fill_lock
from src.liquidationheatmap.api.cache import heatmap_cache
from src.liquidationheatmap.api.metrics import GAP_FILL_DURATION, GAP_FILL_INSERTED_TOTAL

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
async def refresh_connections(token_valid: None = Depends(_require_internal_token)):
    """Release ingestion lock and warm up read connection."""
    DuckDBService.release_ingestion_lock()
    try:
        db = DuckDBService(read_only=True)
        db.conn.execute("SELECT 1").fetchone()
        logger.info("Admin: read connections restored and warmed up")
    except Exception as e:
        logger.error(f"Failed to refresh connections: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )
    return {"status": "success"}

@router.post("/gap-fill")
async def gap_fill(
    dry_run: bool = Query(False, description="Count available data without writing"),
    token_valid: None = Depends(_require_internal_token)
):
    """Run in-process gap-fill from ccxt-data-pipeline Parquet catalog."""
    if _gap_fill_lock.locked():
        return JSONResponse(
            status_code=409,
            content={"status": "conflict", "message": "A gap-fill is already in progress."}
        )

    await _gap_fill_lock.acquire()
    t0 = time.time()
    catalog = str(_settings.ccxt_catalog)
    db_path = str(_settings.db_path)
    symbols = list(_settings.symbols)

    logger.info("Gap-fill started: symbols=%s dry_run=%s", symbols, dry_run)

    try:
        DuckDBService.set_ingestion_lock()
        await asyncio.sleep(1.0) # Drain
        
        DuckDBService.close_all_instances()
        gc.collect()

        with GAP_FILL_DURATION.time():
            result = await asyncio.to_thread(
                run_gap_fill, db_path, catalog, symbols, dry_run
            )

        elapsed = round(time.time() - t0, 2)
        result["duration_seconds"] = elapsed
        result["status"] = "success"
        logger.info("Gap-fill complete: %d rows in %ss", result["total_inserted"], elapsed)

        for symbol, counts in result.get("symbols", {}).items():
            for data_type, details in counts.items():
                if isinstance(details, dict) and "inserted" in details:
                    GAP_FILL_INSERTED_TOTAL.labels(symbol=symbol, type=data_type).inc(details["inserted"])

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

@router.get("/cache/stats", tags=["Cache"])
async def get_cache_stats():
    """Get heatmap cache statistics."""
    return heatmap_cache.get_stats()

@router.delete("/cache/clear", tags=["Cache"])
async def clear_cache():
    """Clear heatmap cache."""
    heatmap_cache.clear()
    return {"message": "Cache cleared", "status": "ok"}
