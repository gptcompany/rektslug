import asyncio
import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from src.liquidationheatmap.settings import get_settings
from src.liquidationheatmap.api.shared import get_cors_origins, IngestionLockError, _warmup_read_connection
from src.liquidationheatmap.api.routers import admin, market, liquidations, signals

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

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

# Legacy / UI endpoints (kept here or moved to ui.py later)
@app.get("/coinglass", tags=["UI"])
async def coinglass_style_ui():
    """Redirect to main heatmap UI."""
    return {"message": "Heatmap UI available at /heatmap_30d.html"}
