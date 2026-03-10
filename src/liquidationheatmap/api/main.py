import asyncio
import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from src.liquidationheatmap.settings import get_settings
from src.liquidationheatmap.api.shared import (
    SUPPORTED_EXCHANGES,
    IngestionLockError,
    _warmup_read_connection,
    get_cors_origins,
)
from src.liquidationheatmap.api.routers import admin, market, liquidations, signals

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

LIQ_MAP_TIMEFRAME_TO_DAYS = {
    "1d": 1,
    "1w": 7,
}

HEATMAP_TIMEFRAME_ALIASES = {
    "1d": "48h",
    "1w": "7d",
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events: cleanup stale locks on startup."""
    from src.liquidationheatmap.ingestion.db_service import DuckDBService
    if DuckDBService.is_ingestion_locked():
        logger.info("Lifespan: Stale ingestion lock detected, cleaning up...")
        DuckDBService.release_ingestion_lock()
    
    # Optional: warm up connections
    asyncio.create_task(_warmup_read_connection())
    yield

app = FastAPI(
    title="Liquidation Heatmap API",
    description="API for accessing liquidation heatmap data and ingestion control.",
    version="1.0.0",
    lifespan=lifespan
)

app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(admin.router)
app.include_router(market.router)
app.include_router(liquidations.router)
app.include_router(signals.router)

@app.get("/health", tags=["System"])
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "liquidation-heatmap"}

# Exception handler: return 503 when ingestion lock is active
@app.exception_handler(IngestionLockError)
async def ingestion_lock_handler(request: Request, exc: IngestionLockError):
    from src.liquidationheatmap.api.metrics import DB_LOCK_CONTENTION_TOTAL
    DB_LOCK_CONTENTION_TOTAL.inc()
    return JSONResponse(
        status_code=503,
        content={
            "error": "Service Unavailable",
            "message": "Database is locked for gap-fill ingestion. Retry shortly.",
        },
        headers={"Retry-After": "10"},
    )

@app.get("/metrics", tags=["System"])
async def metrics():
    """Prometheus metrics endpoint."""
    from src.liquidationheatmap.api.metrics import ACTIVE_DB_CONNECTIONS, get_metrics_response
    from src.liquidationheatmap.ingestion.db_service import DuckDBService
    ACTIVE_DB_CONNECTIONS.set(len(DuckDBService._instances))
    return get_metrics_response()

@app.get("/coinglass", tags=["UI"])
async def coinglass_style_ui():
    """Legacy alias forwarded to the canonical Coinank-style heatmap route."""
    return RedirectResponse(url="/chart/derivatives/liq-heat-map/btcusdt/1w")


@app.get("/heatmap_30d.html", tags=["UI"])
async def heatmap_30d_page():
    """Legacy heatmap alias kept for compatibility with validation tooling."""
    return RedirectResponse(url="/chart/derivatives/liq-heat-map/btcusdt/1w")


@app.get("/liq_map_1w.html", tags=["UI"])
async def liq_map_1w_page():
    """Legacy liq-map alias kept for direct file access compatibility."""
    return FileResponse("frontend/liq_map_1w.html")


@app.get("/liq_map_1w/{symbol}", tags=["UI"])
async def liq_map_1w_symbol(symbol: str):
    """Legacy symbol-specific liq-map alias redirected to the canonical route."""
    return RedirectResponse(url=f"/chart/derivatives/liq-map/binance/{symbol.lower()}/1w")


@app.get("/chart/derivatives/liq-map/{exchange}/{symbol}/{timeframe}", tags=["UI"])
async def liq_map_coinank_style(exchange: str, symbol: str, timeframe: str):
    """Serve the liq-map page directly at the Coinank-style route."""
    normalized_exchange = exchange.lower()
    if normalized_exchange not in SUPPORTED_EXCHANGES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid exchange '{exchange}'. Supported exchanges: {sorted(SUPPORTED_EXCHANGES)}"
            ),
        )

    normalized_timeframe = timeframe.lower()
    if normalized_timeframe not in LIQ_MAP_TIMEFRAME_TO_DAYS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid timeframe '{timeframe}'. "
                f"Supported liq-map timeframes: {sorted(LIQ_MAP_TIMEFRAME_TO_DAYS)}"
            ),
        )

    return FileResponse("frontend/liq_map_1w.html")


@app.get("/chart/derivatives/liq-heat-map/{symbol}/{timeframe}", tags=["UI"])
async def heatmap_coinank_style(symbol: str, timeframe: str):
    """Canonical Coinank-style heatmap route used by docs and validation."""
    normalized_timeframe = HEATMAP_TIMEFRAME_ALIASES.get(timeframe.lower())
    if normalized_timeframe is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid timeframe '{timeframe}'. "
                f"Supported liq-heat-map timeframes: {sorted(HEATMAP_TIMEFRAME_ALIASES)}"
            ),
        )

    return RedirectResponse(
        url=(
            "/frontend/coinglass_heatmap.html"
            f"?symbol={symbol.upper()}&window={normalized_timeframe}&ui=minimal"
        )
    )
