import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from src.liquidationheatmap.api.shared import SUPPORTED_EXCHANGES, SUPPORTED_SYMBOLS
from src.liquidationheatmap.ingestion.db_service import DuckDBService, IngestionLockError
from src.liquidationheatmap.ingestion.questdb_service import QuestDBService

router = APIRouter(tags=["Market Data"])
logger = logging.getLogger(__name__)
HOT_KLINE_INTERVALS = {"1m", "5m"}
COLD_KLINE_INTERVALS = {"15m", "1h", "4h", "1d"}


def _is_hot_kline_interval(interval: str) -> bool:
    return interval in HOT_KLINE_INTERVALS


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
            return JSONResponse(
                content={"symbol": symbol, "interval": interval, "data": qdb_rows},
                headers={"X-Data-Backend": "questdb"},
            )

        if _is_hot_kline_interval(interval):
            raise HTTPException(
                status_code=404,
                detail=f"No QuestDB kline data found for symbol '{symbol}' at interval '{interval}'",
            )

        if interval not in COLD_KLINE_INTERVALS:
            raise HTTPException(status_code=400, detail=f"Unsupported interval '{interval}'")

        table_name = f"klines_{interval}_history"
        with DuckDBService(read_only=True) as db:
            if not db._table_exists(table_name):
                raise HTTPException(status_code=400, detail=f"Unsupported interval '{interval}'")

            query = f"SELECT * FROM {table_name} WHERE symbol = ? ORDER BY open_time DESC LIMIT ?"
            df = db.conn.execute(query, [symbol, limit]).df()
            return JSONResponse(
                content={"symbol": symbol, "interval": interval, "data": df.to_dict(orient="records")},
                headers={"X-Data-Backend": "duckdb"},
            )
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
        qdb = QuestDBService()
        if not qdb.is_available():
            return JSONResponse(
                status_code=503,
                content={
                    "error": "Service Unavailable",
                    "message": "QuestDB unavailable while loading date range.",
                },
                headers={"Retry-After": "60"},
            )
        qdb_range = qdb.get_open_interest_date_range(symbol)
        if qdb_range is not None:
            start_date, end_date = qdb_range
            return JSONResponse(
                content={
                    "symbol": symbol,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                },
                headers={"X-Data-Backend": "questdb"},
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("QuestDB date range error: %s", exc)
        raise HTTPException(status_code=500, detail=f"QuestDB error: {exc}")

    raise HTTPException(status_code=404, detail=f"No data found in QuestDB for symbol '{symbol}'")
