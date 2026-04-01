from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.precompute_hl_sidecar as precompute
from src.liquidationheatmap.hyperliquid.models import (
    AccountAbstraction,
    ApiPosition,
    AssetMetaSnapshot,
    ClearinghouseUserState,
    CrossMarginSummary,
    Leverage,
    MarginSummary,
    PositionCumFunding,
    PositionData,
)
from src.liquidationheatmap.hyperliquid.sidecar import SidecarState, UserPosition, UserState


def _sidecar_state(users: list[str], *, coin: str = "BTC", mark_price: float = 60000.0) -> SidecarState:
    return _sidecar_state_from_sizes(
        {user: 1.0 for user in users},
        coin=coin,
        mark_price=mark_price,
    )


def _sidecar_state_from_sizes(
    user_sizes: dict[str, float],
    *,
    coin: str = "BTC",
    mark_price: float = 60000.0,
) -> SidecarState:
    return SidecarState(
        timestamp=datetime.now(timezone.utc),
        users={
            user: UserState(
                user=user,
                balance=1000.0,
                positions=(
                    UserPosition(
                        coin=coin,
                        asset_idx=0,
                        size=size,
                        entry_px=mark_price,
                        leverage=10.0,
                        cum_funding=0.0,
                        margin=100.0,
                    ),
                ),
            )
            for user, size in user_sizes.items()
        },
        mark_prices={0: mark_price},
        asset_margin_tiers={
            0: [
                {
                    "lower_bound": 0.0,
                    "mmr_rate": 0.01,
                    "maintenance_deduction": 0.0,
                }
            ]
        },
    )


def _clearinghouse_state(
    *,
    coin: str = "BTC",
    size: float = 1.0,
    mark_price: float = 60000.0,
    liquidation_px: float | None = 54000.0,
) -> ClearinghouseUserState:
    return ClearinghouseUserState(
        marginSummary=MarginSummary(
            accountValue=1000.0,
            totalMarginUsed=100.0,
            totalNtlPos=mark_price,
            totalRawUsd=1000.0,
        ),
        crossMarginSummary=CrossMarginSummary(
            accountValue=1000.0,
            totalMarginUsed=100.0,
            totalNtlPos=mark_price,
            totalRawUsd=1000.0,
        ),
        crossMaintenanceMarginUsed=50.0,
        withdrawable=500.0,
        assetPositions=[
            ApiPosition(
                type="oneWay",
                position=PositionData(
                    coin=coin,
                    szi=size,
                    entryPx=mark_price,
                    positionValue=abs(size) * mark_price,
                    unrealizedPnl=0.0,
                    returnOnEquity=0.0,
                    liquidationPx=liquidation_px,
                    leverage=Leverage(type="cross", value=10),
                    marginUsed=100.0,
                    maxLeverage=50,
                    cumFunding=PositionCumFunding(
                        allTime=0.0,
                        sinceOpen=0.0,
                        sinceChange=0.0,
                    ),
                ),
            )
        ],
        time=1,
    )


def test_live_enrichment_cache_round_trip_and_expiry(tmp_path: Path) -> None:
    cache_path = tmp_path / "live_cache.json"
    override = precompute.LiveUserOverride(
        user="0xabc",
        liq_px=54000.0,
        size=1.0,
        notional=60000.0,
        source="api",
        account_abstraction=AccountAbstraction.DEFAULT.value,
    )

    cache = precompute.LiveEnrichmentCache(path=cache_path, ttl_seconds=300)
    cache.put_override(user="0xabc", target_coin="BTC", override=override)
    cache.put_missing_target(user="0xdef", target_coin="BTC")
    cache.save()

    loaded = precompute.LiveEnrichmentCache.load(path=cache_path, ttl_seconds=300)
    loaded_override = loaded.get(user="0xabc", target_coin="BTC")
    missing_target = loaded.get(user="0xdef", target_coin="BTC")

    assert loaded_override is not None
    assert loaded_override.override == override
    assert missing_target is not None
    assert missing_target.status == "missing_target"

    expired_path = tmp_path / "expired_cache.json"
    expired_path.write_text(
        json.dumps(
            {
                "entries": {
                    "BTC:0xold": {
                        "refreshed_at_epoch": 1.0,
                        "status": "override",
                        "override": {
                            "user": "0xold",
                            "liq_px": 50000.0,
                            "size": 1.0,
                            "notional": 60000.0,
                            "source": "api",
                            "account_abstraction": "default",
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    expired = precompute.LiveEnrichmentCache.load(path=expired_path, ttl_seconds=60)
    assert expired.get(user="0xold", target_coin="BTC") is None


def test_select_top_target_users_global_mode_ranks_by_notional() -> None:
    state = _sidecar_state_from_sizes(
        {
            "0xsmall": 1.0,
            "0xmid": 2.0,
            "0xbig": 4.0,
            "0xshort": -3.0,
        }
    )

    selected = precompute._select_top_target_users(
        state,
        target_coin="BTC",
        mark_price=60000.0,
        top_n=3,
        selection_mode="global",
    )

    assert selected == ["0xbig", "0xshort", "0xmid"]


def test_select_top_target_users_per_side_mode_balances_long_and_short() -> None:
    state = _sidecar_state_from_sizes(
        {
            "0xlong1": 5.0,
            "0xlong2": 4.0,
            "0xlong3": 3.0,
            "0xshort1": -6.0,
            "0xshort2": -2.0,
            "0xshort3": -1.0,
        }
    )

    selected = precompute._select_top_target_users(
        state,
        target_coin="BTC",
        mark_price=60000.0,
        top_n=4,
        selection_mode="per_side",
    )

    assert selected == ["0xlong1", "0xlong2", "0xshort1", "0xshort2"]


def test_asset_meta_tables_use_mark_price_overrides_when_contexts_missing() -> None:
    meta = AssetMetaSnapshot.from_api(
        {
            "universe": [
                {
                    "name": "BTC",
                    "szDecimals": 5,
                    "maxLeverage": 40,
                    "onlyIsolated": False,
                    "marginTableId": 56,
                }
            ],
            "marginTables": [
                [
                    56,
                    {
                        "description": "tiered 40x",
                        "marginTiers": [
                            {"lowerBound": "0.0", "maxLeverage": 40},
                            {"lowerBound": "150000000.0", "maxLeverage": 20},
                        ],
                    },
                ]
            ],
        }
    )

    coin_to_asset_idx, mark_prices, margin_tiers = precompute._asset_meta_tables(
        meta,
        mark_price_overrides={0: 69000.0},
    )

    assert coin_to_asset_idx == {"BTC": 0}
    assert mark_prices == {0: 69000.0}
    assert 0 in margin_tiers
    assert margin_tiers[0][0]["lower_bound"] == 150000000.0


@pytest.mark.asyncio
async def test_build_live_overrides_uses_cache_without_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / "live_cache.json"
    cached_override = precompute.LiveUserOverride(
        user="0xabc",
        liq_px=53000.0,
        size=1.0,
        notional=61000.0,
        source="api",
        account_abstraction=AccountAbstraction.DEFAULT.value,
    )
    cache = precompute.LiveEnrichmentCache(path=cache_path, ttl_seconds=300)
    cache.put_override(user="0xabc", target_coin="BTC", override=cached_override)
    cache.save()

    monkeypatch.setattr(precompute, "LIVE_ENRICH_TOP_N", 1)
    monkeypatch.setattr(precompute, "LIVE_ENRICH_CACHE_FILE", cache_path)
    monkeypatch.setattr(precompute, "LIVE_ENRICH_CACHE_TTL_SECONDS", 300)

    class FailingClient:
        DEFAULT_BASE_URL = precompute.HyperliquidInfoClient.DEFAULT_BASE_URL

        def __init__(self, *args, **kwargs):
            raise AssertionError("network client should not be constructed on a cache hit")

    monkeypatch.setattr(precompute, "HyperliquidInfoClient", FailingClient)

    overrides, stats = await precompute._build_live_overrides(
        _sidecar_state(["0xabc"]),
        target_coin="BTC",
        mark_price=60000.0,
    )

    assert overrides["0xabc"] == cached_override
    assert stats.cached_users == 1
    assert stats.fetched_users == 0
    assert stats.applied_users == 1


@pytest.mark.asyncio
async def test_build_live_overrides_fetches_in_configured_batches_and_saves_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / "live_cache.json"
    monkeypatch.setattr(precompute, "LIVE_ENRICH_TOP_N", 3)
    monkeypatch.setattr(precompute, "LIVE_ENRICH_BATCH_SIZE", 2)
    monkeypatch.setattr(precompute, "LIVE_ENRICH_CACHE_FILE", cache_path)
    monkeypatch.setattr(precompute, "LIVE_ENRICH_CACHE_TTL_SECONDS", 300)

    calls: list[tuple[str, list[str]]] = []

    class FakeClient:
        DEFAULT_BASE_URL = precompute.HyperliquidInfoClient.DEFAULT_BASE_URL

        def __init__(self, *args, **kwargs):
            self.base_urls = ["http://localhost:3001/info"]

        async def get_asset_meta(self, *, include_asset_contexts: bool = True):
            class _Meta:
                universe = [
                    type(
                        "AssetMetaStub",
                        (),
                        {
                            "name": "BTC",
                            "maxLeverage": 50,
                            "marginTableId": 1,
                        },
                    )()
                ]
                assetContexts = [
                    type("AssetCtxStub", (), {"markPx": 60000.0})()
                ]
                margin_tables = {
                    1: [
                        type(
                            "TierStub",
                            (),
                            {
                                "lower_bound": 0.0,
                                "mmr_rate": 0.01,
                                "maintenance_deduction": 0.0,
                            },
                        )()
                    ]
                }

            return _Meta()

        async def get_all_borrow_lend_reserve_states(self):
            return {}

        async def get_user_abstractions_batch(self, users: list[str]):
            calls.append(("abstractions", list(users)))
            return {user: AccountAbstraction.DEFAULT for user in users}

        async def get_clearinghouse_states_batch(self, users: list[str]):
            calls.append(("states", list(users)))
            return {user: _clearinghouse_state() for user in users}

        async def get_spot_clearinghouse_states_batch(self, users: list[str]):
            calls.append(("spot", list(users)))
            return {}

        async def get_borrow_lend_user_states_batch(self, users: list[str]):
            calls.append(("borrow", list(users)))
            return {}

    monkeypatch.setattr(precompute, "HyperliquidInfoClient", FakeClient)

    overrides, stats = await precompute._build_live_overrides(
        _sidecar_state(["0x1", "0x2", "0x3"]),
        target_coin="BTC",
        mark_price=60000.0,
    )

    assert sorted(overrides) == ["0x1", "0x2", "0x3"]
    assert stats.fetched_users == 3
    assert stats.cached_users == 0
    assert stats.applied_users == 3
    abstraction_batches = [sorted(users) for label, users in calls if label == "abstractions"]
    state_batches = [sorted(users) for label, users in calls if label == "states"]
    assert sorted(abstraction_batches) == [["0x1"], ["0x2", "0x3"]]
    assert sorted(state_batches) == [["0x1"], ["0x2", "0x3"]]

    cached = precompute.LiveEnrichmentCache.load(path=cache_path, ttl_seconds=300)
    assert cached.get(user="0x1", target_coin="BTC") is not None
    assert cached.get(user="0x2", target_coin="BTC") is not None
    assert cached.get(user="0x3", target_coin="BTC") is not None
