"""Contract: Hyperliquid Info API Client.

Defines the interface for querying Hyperliquid's Info API endpoints
needed for margin validation. Implementation goes in
src/liquidationheatmap/hyperliquid/api_client.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class MarginSummary:
    accountValue: float
    totalMarginUsed: float
    totalNtlPos: float
    totalRawUsd: float


@dataclass(frozen=True)
class CrossMarginSummary:
    accountValue: float
    totalMarginUsed: float
    totalNtlPos: float
    totalRawUsd: float


@dataclass(frozen=True)
class PortfolioMarginSummary:
    accountValue: float
    totalMarginUsed: float
    totalNtlPos: float
    totalRawUsd: float
    portfolioMarginRatio: float


@dataclass(frozen=True)
class Leverage:
    type: str
    value: int


@dataclass(frozen=True)
class PositionCumFunding:
    allTime: float
    sinceOpen: float
    sinceChange: float


@dataclass(frozen=True)
class PositionData:
    coin: str
    szi: float
    entryPx: float
    positionValue: float
    unrealizedPnl: float
    returnOnEquity: float
    liquidationPx: float | None
    leverage: Leverage
    marginUsed: float
    maxLeverage: int
    cumFunding: PositionCumFunding


@dataclass(frozen=True)
class ApiPosition:
    type: str
    position: PositionData


@dataclass(frozen=True)
class ClearinghouseUserState:
    marginSummary: MarginSummary
    crossMarginSummary: CrossMarginSummary
    crossMaintenanceMarginUsed: float
    withdrawable: float
    assetPositions: list[ApiPosition]
    time: int
    portfolioMarginSummary: PortfolioMarginSummary | None


@dataclass(frozen=True)
class AssetMeta:
    name: str
    szDecimals: int
    maxLeverage: int
    onlyIsolated: bool


@dataclass(frozen=True)
class AssetContext:
    markPx: float


@dataclass(frozen=True)
class AssetMetaSnapshot:
    universe: list[AssetMeta]
    assetContexts: list[AssetContext]


class HyperliquidInfoAPI(Protocol):
    """Protocol for Hyperliquid Info API access."""

    async def get_clearinghouse_state(self, user_address: str) -> ClearinghouseUserState:
        """Query clearinghouseState for a user.

        POST https://api.hyperliquid.xyz/info
        Body: {"type": "clearinghouseState", "user": user_address}

        Returns parsed user margin state.
        Raises transport/client errors from the async HTTP layer after retries are exhausted.
        """
        ...

    async def get_asset_meta(self) -> AssetMetaSnapshot:
        """Query metaAndAssetCtxs endpoint for asset metadata plus current marks.

        POST https://api.hyperliquid.xyz/info
        Body: {"type": "metaAndAssetCtxs"}

        Returns parsed asset snapshot with universe metadata and mark-price contexts.
        """
        ...

    async def get_clearinghouse_states_batch(
        self, user_addresses: list[str], *, max_concurrent: int = 5
    ) -> dict[str, ClearinghouseUserState]:
        """Batch query multiple users with rate limiting.

        Returns only successfully fetched states; failures are logged and omitted.
        Respects rate limits (~10 req/min in the current implementation).
        """
        ...
