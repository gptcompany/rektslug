import logging
from fastapi import APIRouter, Query, HTTPException

from src.liquidationheatmap.ingestion.db_service import DuckDBService, IngestionLockError
from src.liquidationheatmap.api.shared import SUPPORTED_SYMBOLS, SUPPORTED_EXCHANGES

router = APIRouter(tags=["Market Data"])
logger = logging.getLogger(__name__)

@router.get("/exchanges")
async def list_exchanges():
    """List supported exchanges and their status."""
    return {"exchanges": [{"name": k, **v} for k, v in SUPPORTED_EXCHANGES.items()]}

@router.get("/exchanges/health")
async def get_exchanges_health():
    """Get health status for all supported exchanges."""
    results = {}
    for name in SUPPORTED_EXCHANGES:
        # Simple health check placeholder
        results[name] = "healthy"
    return results

@router.get("/symbols")
async def list_symbols():
    """List supported trading symbols."""
    return sorted(list(SUPPORTED_SYMBOLS))

@router.get("/prices/klines")
async def get_klines(
    symbol: str = Query(..., pattern="^[A-Z]{6,12}$"),
    interval: str = "5m",
    limit: int = Query(100, ge=1, le=1000)
):
    """Get historical klines/candles."""
    try:
        table_name = f"klines_{interval}_history"
        with DuckDBService(read_only=True) as db:
            if not db._table_exists(table_name):
                raise HTTPException(status_code=400, detail=f"Unsupported interval '{interval}'")
                
            query = f"SELECT * FROM {table_name} WHERE symbol = ? ORDER BY open_time DESC LIMIT ?"
            df = db.conn.execute(query, [symbol, limit]).df()
            return {"symbol": symbol, "interval": interval, "data": df.to_dict(orient="records")}
    except (HTTPException, IngestionLockError):
        raise
    except Exception as e:
        logger.error(f"Klines error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/date-range")
async def get_data_date_range(
    symbol: str = Query("BTCUSDT", pattern="^[A-Z]{6,12}$"),
):
    """Return the available Open Interest date range for a symbol."""
    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid symbol '{symbol}'. Supported: {sorted(SUPPORTED_SYMBOLS)}",
        )

    try:
        with DuckDBService(read_only=True) as db:
            result = db.conn.execute(
                """
                SELECT
                    MIN(timestamp) AS start_date,
                    MAX(timestamp) AS end_date
                FROM open_interest_history
                WHERE symbol = ?
                """,
                [symbol],
            ).fetchone()
    except (HTTPException, IngestionLockError):
        raise
    except Exception as e:
        logger.error(f"Date range error: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    if not result or not result[0] or not result[1]:
        raise HTTPException(status_code=404, detail=f"No data found for symbol '{symbol}'")

    return {
        "symbol": symbol,
        "start_date": result[0].isoformat(),
        "end_date": result[1].isoformat(),
    }
