"""Contract: Hyperliquid Info API Client.

Defines the interface for querying Hyperliquid's Info API endpoints
needed for margin validation. Implementation goes in
src/liquidationheatmap/hyperliquid/api_client.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ClearinghouseUserState:
    """Parsed response from clearinghouseState for a single user."""

    margin_summary: MarginSummary
    positions: list[ApiPosition]
    # Portfolio margin fields are optional — absent for standard cross-margin
    portfolio_margin_summary: PortfolioMarginSummary | None


@dataclass(frozen=True)
class MarginSummary:
    """marginSummary from clearinghouseState response."""

    account_value: float
    total_margin_used: float
    total_ntl_pos: float
    total_raw_usd: float


@dataclass(frozen=True)
class ApiPosition:
    """Per-position data from clearinghouseState assetPositions."""

    coin: str
    size: float
    entry_px: float
    margin_used: float
    liquidation_px: float | None
    unrealized_pnl: float
    leverage_type: str  # "cross" or "isolated"
    max_leverage: int


@dataclass(frozen=True)
class PortfolioMarginSummary:
    """Portfolio margin fields, present only for PM accounts."""

    portfolio_margin_ratio: float
    total_margin_required: float


@dataclass(frozen=True)
class AssetMeta:
    """Per-asset metadata from meta endpoint."""

    name: str
    asset_idx: int
    max_leverage: int
    margin_tiers: list[MarginTier]


@dataclass(frozen=True)
class MarginTier:
    """Single margin tier for an asset."""

    lower_bound: float
    mmr_rate: float
    maintenance_deduction: float


class HyperliquidInfoAPI(Protocol):
    """Protocol for Hyperliquid Info API access."""

    async def get_clearinghouse_state(self, user_address: str) -> ClearinghouseUserState:
        """Query clearinghouseState for a user.

        POST https://api.hyperliquid.xyz/info
        Body: {"type": "clearinghouseState", "user": user_address}

        Returns parsed user margin state.
        Raises: httpx.HTTPStatusError on 4xx/5xx, httpx.TimeoutException.
        """
        ...

    async def get_asset_meta(self) -> list[AssetMeta]:
        """Query meta endpoint for all asset metadata including margin tiers.

        POST https://api.hyperliquid.xyz/info
        Body: {"type": "meta"}

        Returns list of asset metadata with margin tiers.
        """
        ...

    async def get_clearinghouse_states_batch(
        self, user_addresses: list[str], *, max_concurrent: int = 5
    ) -> dict[str, ClearinghouseUserState | Exception]:
        """Batch query multiple users with rate limiting.

        Returns dict mapping address -> result or exception.
        Respects rate limits (~10-20 req/min).
        """
        ...
