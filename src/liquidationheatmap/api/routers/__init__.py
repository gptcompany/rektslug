"""API routers for LiquidationHeatmap."""

from src.liquidationheatmap.api.routers.admin import router as admin_router
from src.liquidationheatmap.api.routers.liquidations import router as liquidations_router
from src.liquidationheatmap.api.routers.market import router as market_router
from src.liquidationheatmap.api.routers.ops import router as ops_router
from src.liquidationheatmap.api.routers.signals import router as signals_router

__all__ = [
    "signals_router",
    "admin_router",
    "market_router",
    "liquidations_router",
    "ops_router",
]
