import logging

from fastapi import APIRouter, HTTPException, Query

from src.liquidationheatmap.api.shared import SUPPORTED_EXCHANGES, SUPPORTED_SYMBOLS
from src.liquidationheatmap.ingestion.db_service import DuckDBService, IngestionLockError
from src.liquidationheatmap.ingestion.questdb_service import QuestDBService

router = APIRouter(tags=["Market Data"])
logger = logging.getLogger(__name__)


@router.get("/exchanges")
async def list_exchanges():
    """List supported exchanges and their status."""
    return {"exchanges": [{"name": k, **v} for k, v in SUPPORTED_EXCHANGES.items()]}


@router.get("/exchanges/health")
async def get_exchanges_health():
    """Get health status for all supported exchanges."""
    return {name: "healthy" for name in SUPPORTED_EXCHANGES}


@router.get("/symbols")
async def list_symbols():
    """List supported trading symbols."""
    return sorted(list(SUPPORTED_SYMBOLS))


@router.get("/prices/klines")
async def get_klines(
    symbol: str = Query(..., pattern="^[A-Z]{6,12}$"),
    interval: str = "5m",
    limit: int = Query(100, ge=1, le=1000),
):
    """Get historical klines/candles."""
    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid symbol '{symbol}'. Supported: {sorted(SUPPORTED_SYMBOLS)}",
        )

    try:
        qdb_rows = QuestDBService().get_recent_klines(symbol=symbol, interval=interval, limit=limit)
        if qdb_rows:
            return {"symbol": symbol, "interval": interval, "data": qdb_rows}

        table_name = f"klines_{interval}_history"
        with DuckDBService(read_only=True) as db:
            if not db._table_exists(table_name):
                raise HTTPException(status_code=400, detail=f"Unsupported interval '{interval}'")

            query = f"SELECT * FROM {table_name} WHERE symbol = ? ORDER BY open_time DESC LIMIT ?"
            df = db.conn.execute(query, [symbol, limit]).df()
            return {"symbol": symbol, "interval": interval, "data": df.to_dict(orient='records')}
    except (HTTPException, IngestionLockError):
        raise
    except Exception as exc:
        logger.error("Klines error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


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
        qdb_range = QuestDBService().get_open_interest_date_range(symbol)
        if qdb_range is not None:
            start_date, end_date = qdb_range
            return {
                "symbol": symbol,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }

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
    except Exception as exc:
        logger.error("Date range error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Database error: {exc}")

    if not result or not result[0] or not result[1]:
        raise HTTPException(status_code=404, detail=f"No data found for symbol '{symbol}'")

    return {
        "symbol": symbol,
        "start_date": result[0].isoformat(),
        "end_date": result[1].isoformat(),
    }
