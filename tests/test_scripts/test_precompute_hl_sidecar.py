from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

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


def _sidecar_state_from_positions(
    user_positions: dict[str, list[tuple[str, int, float, float]]],
    *,
    margin_tiers: dict[int, list[dict]] | None = None,
) -> SidecarState:
    mark_prices: dict[int, float] = {}
    users: dict[str, UserState] = {}
    for user, positions in user_positions.items():
        built_positions: list[UserPosition] = []
        for coin, asset_idx, size, mark_price in positions:
            mark_prices[asset_idx] = mark_price
            built_positions.append(
                UserPosition(
                    coin=coin,
                    asset_idx=asset_idx,
                    size=size,
                    entry_px=mark_price,
                    leverage=10.0,
                    cum_funding=0.0,
                    margin=100.0,
                )
            )
        users[user] = UserState(
            user=user,
            balance=1000.0,
            positions=tuple(built_positions),
        )

    return SidecarState(
        timestamp=datetime.now(timezone.utc),
        users=users,
        mark_prices=mark_prices,
        asset_margin_tiers=margin_tiers
        or {
            asset_idx: [
                {
                    "lower_bound": 0.0,
                    "mmr_rate": 0.01,
                    "maintenance_deduction": 0.0,
                }
            ]
            for asset_idx in mark_prices
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


def test_extend_context_live_overrides_for_selected_users_merges_missing_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_override = precompute.LiveUserOverride(
        user="0xbase",
        liq_px=54000.0,
        size=1.0,
        notional=60000.0,
        source="api",
        account_abstraction=AccountAbstraction.DEFAULT.value,
    )
    extra_override = precompute.LiveUserOverride(
        user="0xextra",
        liq_px=52000.0,
        size=2.0,
        notional=120000.0,
        source="api",
        account_abstraction=AccountAbstraction.DEFAULT.value,
    )
    context = precompute.SymbolBuildContext(
        symbol="BTC",
        request=SimpleNamespace(),
        plan=SimpleNamespace(anchor_coverage=SimpleNamespace(latest_anchor_in_window="anchor")),
        source_anchor="anchor",
        enable_live_enrichment=True,
        state=_sidecar_state(["0xbase", "0xextra"]),
        reconstructor=precompute.SidecarPositionReconstructor(),
        bin_size=10.0,
        target_coin="BTC",
        mark_price=60000.0,
        current_price=60000.0,
        live_overrides={"0xbase": base_override},
        live_enrichment_stats=precompute.LiveEnrichmentStats(
            selected_users=1,
            cached_users=1,
            applied_users=1,
            api_liq_users=1,
        ),
    )

    async def fake_build_live_overrides_for_users(state, *, target_coin, selected_users):
        assert target_coin == "BTC"
        assert selected_users == ["0xextra"]
        return (
            {"0xextra": extra_override},
            precompute.LiveEnrichmentStats(
                selected_users=1,
                fetched_users=1,
                applied_users=1,
                api_liq_users=1,
            ),
        )

    monkeypatch.setattr(
        precompute,
        "_build_live_overrides_for_users",
        fake_build_live_overrides_for_users,
    )

    updated = precompute._extend_context_live_overrides_for_selected_users(
        context,
        selected_users={"0xbase", "0xextra"},
    )

    assert updated.live_overrides["0xbase"] == base_override
    assert updated.live_overrides["0xextra"] == extra_override
    assert updated.live_enrichment_stats.selected_users == 2
    assert updated.live_enrichment_stats.cached_users == 1
    assert updated.live_enrichment_stats.fetched_users == 1
    assert updated.live_enrichment_stats.applied_users == 2
    assert updated.live_enrichment_stats.api_liq_users == 2


def test_extend_context_live_overrides_for_selected_users_skips_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = precompute.SymbolBuildContext(
        symbol="BTC",
        request=SimpleNamespace(),
        plan=SimpleNamespace(anchor_coverage=SimpleNamespace(latest_anchor_in_window="anchor")),
        source_anchor="anchor",
        enable_live_enrichment=False,
        state=_sidecar_state(["0xbase", "0xextra"]),
        reconstructor=precompute.SidecarPositionReconstructor(),
        bin_size=10.0,
        target_coin="BTC",
        mark_price=60000.0,
        current_price=60000.0,
        live_overrides={},
        live_enrichment_stats=precompute.LiveEnrichmentStats(),
    )

    async def fail_build_live_overrides_for_users(*args, **kwargs):
        raise AssertionError("live enrichment must stay disabled for historical backfill")

    monkeypatch.setattr(
        precompute,
        "_build_live_overrides_for_users",
        fail_build_live_overrides_for_users,
    )

    updated = precompute._extend_context_live_overrides_for_selected_users(
        context,
        selected_users={"0xbase", "0xextra"},
    )

    assert updated is context


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


def test_select_top_target_users_liq_intensity_prefers_near_liquidation() -> None:
    state = _sidecar_state_from_sizes(
        {
            "0xbig_far": 4.0,
            "0xnear": 2.0,
            "0xmid": 3.0,
        }
    )

    class StubReconstructor:
        @staticmethod
        def solve_liquidation_price(*, user_state, target_coin, mark_prices, asset_margin_tiers):
            return {
                "0xbig_far": 30000.0,
                "0xnear": 57000.0,
                "0xmid": 45000.0,
            }[user_state.user]

    selected = precompute._select_top_target_users(
        state,
        target_coin="BTC",
        mark_price=60000.0,
        top_n=3,
        selection_mode="global",
        score_mode="liq_intensity",
        distance_floor_bps=25,
        reconstructor=StubReconstructor(),
    )

    assert selected == ["0xnear", "0xmid", "0xbig_far"]


def test_select_top_target_users_liq_intensity_can_require_side_consistency() -> None:
    state = _sidecar_state_from_sizes(
        {
            "0xvalid_long": 3.0,
            "0xwrong_side": 4.0,
            "0xvalid_short": -2.0,
        }
    )

    class StubReconstructor:
        @staticmethod
        def solve_liquidation_price(*, user_state, target_coin, mark_prices, asset_margin_tiers):
            return {
                "0xvalid_long": 54000.0,
                "0xwrong_side": 62000.0,
                "0xvalid_short": 64000.0,
            }[user_state.user]

    selected = precompute._select_top_target_users(
        state,
        target_coin="BTC",
        mark_price=60000.0,
        top_n=3,
        selection_mode="global",
        score_mode="liq_intensity",
        require_side_consistency=True,
        reconstructor=StubReconstructor(),
    )

    assert selected == ["0xvalid_short", "0xvalid_long"]


def test_build_target_exposure_profile_tracks_target_share_and_complexity() -> None:
    state = _sidecar_state_from_positions(
        {
            "0xuser": [
                ("BTC", 0, 2.0, 60000.0),
                ("ETH", 1, 10.0, 2000.0),
                ("SOL", 2, 100.0, 100.0),
            ]
        }
    )

    profile = precompute._build_target_exposure_profile(
        state.users["0xuser"],
        target_coin="BTC",
        mark_prices=state.mark_prices,
    )

    assert profile.target_notional == 120000.0
    assert profile.off_target_notional == 30000.0
    assert profile.total_notional == 150000.0
    assert profile.position_count == 3
    assert profile.target_share == 0.8


def test_resolve_top_position_selector_config_supports_symbol_specific_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HEATMAP_HL_TOP_POSITION_OBJECTIVE", "balanced")
    monkeypatch.setenv("HEATMAP_HL_TOP_POSITION_SCORE_MODE", "notional")
    monkeypatch.setenv("HEATMAP_HL_TOP_POSITION_SCORE_MODE_BTC", "concentration")
    monkeypatch.setenv("HEATMAP_HL_TOP_POSITION_TOP_N", "250")
    monkeypatch.setenv("HEATMAP_HL_TOP_POSITION_TOP_N_ETH", "180")
    monkeypatch.setenv("HEATMAP_HL_TOP_POSITION_CANDIDATE_POOL_TOP_N", "300")
    monkeypatch.setenv("HEATMAP_HL_TOP_POSITION_CANDIDATE_POOL_TOP_N_ETH", "220")
    monkeypatch.setenv("HEATMAP_HL_TOP_POSITION_CONCENTRATION_SHARE_POWER_BTC", "1.5")
    monkeypatch.setenv("HEATMAP_HL_TOP_POSITION_MIN_TARGET_SHARE", "0.2")
    monkeypatch.setenv("HEATMAP_HL_TOP_POSITION_MIN_TARGET_SHARE_ETH", "0.7")
    monkeypatch.setenv("HEATMAP_HL_TOP_POSITION_MAX_POSITION_COUNT_BTC", "3")
    monkeypatch.setenv(
        "HEATMAP_HL_TOP_POSITION_CONCENTRATION_POSITIONS_PENALTY_BTC",
        "0.05",
    )

    btc = precompute._resolve_top_position_selector_config("BTC")
    eth = precompute._resolve_top_position_selector_config("ETH")

    assert btc.score_mode == "concentration"
    assert btc.objective == "balanced"
    assert btc.top_n == 250
    assert btc.candidate_pool_top_n == 300
    assert btc.concentration_share_power == 1.5
    assert btc.concentration_positions_penalty == 0.05
    assert btc.min_target_share == 0.2
    assert btc.max_position_count == 3

    assert eth.score_mode == "notional"
    assert eth.objective == "balanced"
    assert eth.top_n == 180
    assert eth.candidate_pool_top_n == 220
    assert eth.min_target_share == 0.7
    assert eth.max_position_count == 3


def test_resolve_top_position_selector_config_shape_first_objective_sets_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HEATMAP_HL_TOP_POSITION_OBJECTIVE_BTC", "shape_first")

    btc = precompute._resolve_top_position_selector_config("BTC")

    assert btc.objective == "shape_first"
    assert btc.min_target_share == 0.6
    assert btc.max_position_count == 3


def test_resolve_top_position_selector_config_explicit_filters_override_objective(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HEATMAP_HL_TOP_POSITION_OBJECTIVE_BTC", "shape_first")
    monkeypatch.setenv("HEATMAP_HL_TOP_POSITION_MIN_TARGET_SHARE_BTC", "0.45")
    monkeypatch.setenv("HEATMAP_HL_TOP_POSITION_MAX_POSITION_COUNT_BTC", "5")

    btc = precompute._resolve_top_position_selector_config("BTC")

    assert btc.objective == "shape_first"
    assert btc.min_target_share == 0.45
    assert btc.max_position_count == 5


def test_resolve_symbols_honors_runtime_symbol_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HEATMAP_SYMBOLS_SHELL", "BTCUSDT")

    assert precompute._resolve_symbols() == ["BTC"]


def test_resolve_symbols_dedupes_and_filters_unsupported_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HEATMAP_SYMBOLS_SHELL", raising=False)
    monkeypatch.setenv("HEATMAP_SYMBOLS", "ethusdt, BTC, SOLUSDT,ETH")

    assert precompute._resolve_symbols() == ["ETH", "BTC"]


def test_select_top_target_users_concentration_penalizes_complex_off_target_books(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _sidecar_state_from_positions(
        {
            "0xfocused": [("BTC", 0, 2.0, 60000.0)],
            "0xcomplex": [
                ("BTC", 0, 2.5, 60000.0),
                ("ETH", 1, 15.0, 2000.0),
                ("SOL", 2, 200.0, 100.0),
                ("ARB", 3, 10000.0, 1.0),
                ("OP", 4, 10000.0, 1.0),
            ],
            "0xmiddle": [
                ("BTC", 0, 2.0, 60000.0),
                ("ETH", 1, 6.0, 2000.0),
            ],
        }
    )
    monkeypatch.setattr(precompute, "TOP_POSITION_CONCENTRATION_SHARE_POWER", 2.0)
    monkeypatch.setattr(precompute, "TOP_POSITION_CONCENTRATION_POSITIONS_PENALTY", 0.2)

    selected = precompute._select_top_target_users(
        state,
        target_coin="BTC",
        mark_price=60000.0,
        top_n=3,
        selection_mode="global",
        score_mode="concentration",
    )

    assert selected == ["0xfocused", "0xmiddle", "0xcomplex"]


def test_select_top_target_users_can_filter_by_target_share_and_position_count() -> None:
    state = _sidecar_state_from_positions(
        {
            "0xfocused": [("BTC", 0, 3.0, 60000.0)],
            "0xcomplex": [
                ("BTC", 0, 4.0, 60000.0),
                ("ETH", 1, 8.0, 2000.0),
                ("SOL", 2, 150.0, 100.0),
                ("ARB", 3, 5000.0, 1.0),
            ],
            "0xdiluted": [
                ("BTC", 0, 4.5, 60000.0),
                ("ETH", 1, 90.0, 2000.0),
            ],
            "0xclean2": [
                ("BTC", 0, 2.0, 60000.0),
                ("ETH", 1, 4.0, 2000.0),
            ],
        }
    )

    selected = precompute._select_top_target_users(
        state,
        target_coin="BTC",
        mark_price=60000.0,
        top_n=4,
        selection_mode="global",
        score_mode="notional",
        min_target_share=0.7,
        max_position_count=3,
    )

    assert selected == ["0xfocused", "0xclean2"]


def test_select_top_target_users_live_liq_intensity_uses_live_overrides() -> None:
    state = _sidecar_state_from_sizes(
        {
            "0xfar": 4.0,
            "0xnear": 2.0,
            "0xmissing": 3.0,
        }
    )
    live_overrides = {
        "0xfar": precompute.LiveUserOverride(
            user="0xfar",
            liq_px=30000.0,
            size=4.0,
            notional=240000.0,
            source="api",
            account_abstraction=AccountAbstraction.DEFAULT.value,
        ),
        "0xnear": precompute.LiveUserOverride(
            user="0xnear",
            liq_px=57000.0,
            size=2.0,
            notional=120000.0,
            source="api",
            account_abstraction=AccountAbstraction.DEFAULT.value,
        ),
    }

    selected = precompute._select_top_target_users(
        state,
        target_coin="BTC",
        mark_price=60000.0,
        top_n=3,
        selection_mode="global",
        score_mode="live_liq_intensity",
        live_overrides=live_overrides,
    )

    assert selected == ["0xnear", "0xfar"]


def test_synthesize_top_buckets_payload_keeps_heaviest_global_buckets() -> None:
    payload = {
        "source": "hyperliquid-sidecar",
        "symbol": "BTCUSDT",
        "timeframe": "1w",
        "current_price": 100.0,
        "mark_price": 100.0,
        "account_count": 10,
        "generated_at": "2026-04-02T00:00:00Z",
        "grid": {
            "step": 5.0,
            "anchor_price": 100.0,
            "min_price": 70.0,
            "max_price": 130.0,
        },
        "leverage_ladder": ["cross"],
        "long_buckets": [
            {"price_level": 80.0, "leverage": "cross", "volume": 300.0},
            {"price_level": 90.0, "leverage": "cross", "volume": 100.0},
        ],
        "short_buckets": [
            {"price_level": 110.0, "leverage": "cross", "volume": 200.0},
            {"price_level": 120.0, "leverage": "cross", "volume": 50.0},
        ],
        "cumulative_long": [],
        "cumulative_short": [],
        "out_of_range_volume": {"long": 0.0, "short": 0.0},
        "source_anchor": "anchor",
        "bin_size": 5.0,
        "live_enrichment": {},
        "projection": {
            "mode": "full_universe_seed",
            "selected_users": 10,
            "included_users": 10,
            "target_count": 2,
        },
    }

    synthesized = precompute._synthesize_top_buckets_payload(
        payload,
        target_bucket_count=2,
        selection_mode="global",
    )

    assert synthesized["long_buckets"] == [
        {"price_level": 80.0, "leverage": "cross", "volume": 300.0},
    ]
    assert synthesized["short_buckets"] == [
        {"price_level": 110.0, "leverage": "cross", "volume": 200.0},
    ]
    assert synthesized["projection"]["mode"] == "top_buckets_probe"
    assert synthesized["projection"]["retained_bucket_count"] == 2
    assert synthesized["projection"]["pruned_bucket_count"] == 2
    assert synthesized["projection"]["retained_volume"] == 500.0
    assert synthesized["projection"]["pruned_volume"] == 150.0


def test_build_v3_payload_band_synthesis_uses_full_universe_seed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = precompute.SymbolBuildContext(
        symbol="BTC",
        request=SimpleNamespace(target_coin="BTC"),
        plan=SimpleNamespace(anchor_coverage=SimpleNamespace(latest_anchor_in_window="anchor")),
        source_anchor="anchor",
        enable_live_enrichment=True,
        state=_sidecar_state(["0x1"]),
        reconstructor=precompute.SidecarPositionReconstructor(),
        bin_size=10.0,
        target_coin="BTC",
        mark_price=60000.0,
        current_price=60000.0,
        live_overrides={},
        live_enrichment_stats=precompute.LiveEnrichmentStats(),
    )

    monkeypatch.setattr(
        precompute,
        "_resolve_top_position_selector_config",
        lambda symbol: precompute.TopPositionSelectorConfig(
            objective=None,
            top_n=2,
            selection_mode="global",
            score_mode="band_synthesis",
            candidate_pool_top_n=2,
            distance_floor_bps=25,
            require_side_consistency=False,
            concentration_share_power=2.0,
            concentration_positions_penalty=0.2,
            min_target_share=0.0,
            max_position_count=None,
        ),
    )

    def fail_select_v3_target_users(unused_context):
        raise AssertionError("user selection should be bypassed for band_synthesis")

    monkeypatch.setattr(precompute, "_select_v3_target_users", fail_select_v3_target_users)

    monkeypatch.setattr(
        precompute,
        "_build_public_payload",
        lambda **kwargs: {
            "source": kwargs["source"],
            "symbol": "BTCUSDT",
            "timeframe": "1w",
            "current_price": 100.0,
            "mark_price": 100.0,
            "account_count": 10,
            "generated_at": "2026-04-02T00:00:00Z",
            "grid": {
                "step": 5.0,
                "anchor_price": 100.0,
                "min_price": 70.0,
                "max_price": 130.0,
            },
            "leverage_ladder": ["cross"],
            "long_buckets": [
                {"price_level": 80.0, "leverage": "cross", "volume": 300.0},
                {"price_level": 90.0, "leverage": "cross", "volume": 100.0},
            ],
            "short_buckets": [
                {"price_level": 110.0, "leverage": "cross", "volume": 200.0},
            ],
            "cumulative_long": [],
            "cumulative_short": [],
            "out_of_range_volume": {"long": 0.0, "short": 0.0},
            "source_anchor": "anchor",
            "bin_size": 5.0,
            "live_enrichment": {},
            "projection": {
                "mode": kwargs["projection_mode"],
                "selected_users": 1,
                "included_users": 1,
                "target_count": kwargs["projection_target_count"],
            },
        },
    )

    payload = precompute._build_v3_payload(context)

    assert payload is not None
    assert payload["source"] == "hyperliquid-sidecar-band-synthesis"
    assert payload["projection"]["mode"] == "top_buckets_probe"
    assert payload["projection"]["target_count"] == 2
    assert payload["projection"]["retained_bucket_count"] == 2


def test_build_v4_payload_emits_position_first_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = precompute.SymbolBuildContext(
        symbol="BTC",
        request=SimpleNamespace(),
        plan=SimpleNamespace(anchor_coverage=SimpleNamespace(latest_anchor_in_window="anchor")),
        source_anchor="anchor",
        enable_live_enrichment=True,
        state=_sidecar_state(["0x1", "0x2"]),
        reconstructor=precompute.SidecarPositionReconstructor(),
        bin_size=10.0,
        target_coin="BTC",
        mark_price=60000.0,
        current_price=60000.0,
        live_overrides={},
        live_enrichment_stats=precompute.LiveEnrichmentStats(),
    )

    monkeypatch.setattr(precompute, "POSITION_FIRST_TOP_N", 250)
    monkeypatch.setattr(
        precompute,
        "_select_top_target_users",
        lambda *args, **kwargs: ["0x1", "0x2"],
    )
    monkeypatch.setattr(
        precompute,
        "_extend_context_live_overrides_for_selected_users",
        lambda context, *, selected_users: context,
    )

    def fake_build_public_payload(**kwargs):
        return {
            "source": kwargs["source"],
            "projection": {
                "mode": kwargs["projection_mode"],
                "selection_strategy": kwargs["projection_selection_strategy"],
                "score_mode": kwargs["projection_score_mode"],
                "objective": kwargs["projection_objective"],
                "target_count": kwargs["projection_target_count"],
                "selected_users": sorted(kwargs["selected_users"]),
            },
        }

    monkeypatch.setattr(precompute, "_build_public_payload", fake_build_public_payload)

    payload = precompute._build_v4_payload(context)

    assert payload == {
        "source": "hyperliquid-sidecar-position-first",
        "projection": {
            "mode": "position_first_local",
            "selection_strategy": "global",
            "score_mode": "target_notional",
            "objective": "position_first",
            "target_count": 250,
            "selected_users": ["0x1", "0x2"],
        },
    }


def test_build_v5_payload_emits_risk_first_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = precompute.SymbolBuildContext(
        symbol="BTC",
        request=SimpleNamespace(),
        plan=SimpleNamespace(anchor_coverage=SimpleNamespace(latest_anchor_in_window="anchor")),
        source_anchor="anchor",
        enable_live_enrichment=True,
        state=_sidecar_state(["0x1", "0x2"]),
        reconstructor=precompute.SidecarPositionReconstructor(),
        bin_size=10.0,
        target_coin="BTC",
        mark_price=60000.0,
        current_price=60000.0,
        live_overrides={},
        live_enrichment_stats=precompute.LiveEnrichmentStats(),
    )

    monkeypatch.setattr(precompute, "RISK_FIRST_TOP_N", 250)
    monkeypatch.setattr(
        precompute,
        "_select_v5_target_users",
        lambda context: (context, ["0x2", "0x1"]),
    )
    monkeypatch.setattr(
        precompute,
        "_extend_context_live_overrides_for_selected_users",
        lambda context, *, selected_users: context,
    )

    def fake_build_public_payload(**kwargs):
        return {
            "source": kwargs["source"],
            "projection": {
                "mode": kwargs["projection_mode"],
                "selection_strategy": kwargs["projection_selection_strategy"],
                "score_mode": kwargs["projection_score_mode"],
                "objective": kwargs["projection_objective"],
                "target_count": kwargs["projection_target_count"],
                "selected_users": sorted(kwargs["selected_users"]),
            },
        }

    monkeypatch.setattr(precompute, "_build_public_payload", fake_build_public_payload)

    payload = precompute._build_v5_payload(context)

    assert payload == {
        "source": "hyperliquid-sidecar-risk-first",
        "projection": {
            "mode": "risk_first_local",
            "selection_strategy": "global",
            "score_mode": "risk_score",
            "objective": "risk_first",
            "target_count": 250,
            "selected_users": ["0x1", "0x2"],
        },
    }


def test_select_v3_target_users_live_liq_intensity_uses_candidate_pool_and_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = precompute.SymbolBuildContext(
        symbol="BTC",
        request=SimpleNamespace(),
        plan=SimpleNamespace(anchor_coverage=SimpleNamespace(latest_anchor_in_window="anchor")),
        source_anchor="anchor",
        enable_live_enrichment=True,
        state=_sidecar_state(["0x1", "0x2", "0x3", "0x4"]),
        reconstructor=precompute.SidecarPositionReconstructor(),
        bin_size=10.0,
        target_coin="BTC",
        mark_price=60000.0,
        current_price=60000.0,
        live_overrides={},
        live_enrichment_stats=precompute.LiveEnrichmentStats(),
    )

    monkeypatch.setattr(precompute, "TOP_POSITION_SCORE_MODE", "live_liq_intensity")
    monkeypatch.setattr(precompute, "TOP_POSITION_TOP_N", 3)
    monkeypatch.setattr(precompute, "TOP_POSITION_CANDIDATE_POOL_TOP_N", 4)

    calls: list[tuple[str, tuple[str, ...]]] = []

    def fake_select_top_target_users(
        state,
        *,
        target_coin,
        mark_price,
        top_n,
        selection_mode="global",
        score_mode="notional",
        distance_floor_bps=25,
        require_side_consistency=False,
        reconstructor=None,
        candidate_users=None,
        live_overrides=None,
        concentration_share_power=2.0,
        concentration_positions_penalty=0.2,
        min_target_share=0.0,
        max_position_count=None,
    ):
        key = tuple(sorted(candidate_users)) if candidate_users is not None else ()
        calls.append((score_mode, key))
        if score_mode == "notional":
            return ["0x1", "0x2", "0x3", "0x4"]
        if score_mode == "live_liq_intensity":
            assert key == ("0x1", "0x2", "0x3", "0x4")
            assert live_overrides == {"0x1": "ov1", "0x3": "ov3"}
            return ["0x3", "0x1"]
        raise AssertionError(f"unexpected score_mode: {score_mode}")

    def fake_extend_context_live_overrides_for_selected_users(context, *, selected_users):
        assert selected_users == {"0x1", "0x2", "0x3", "0x4"}
        return precompute.SymbolBuildContext(
            symbol=context.symbol,
            request=context.request,
            plan=context.plan,
            source_anchor=context.source_anchor,
            enable_live_enrichment=context.enable_live_enrichment,
            state=context.state,
            reconstructor=context.reconstructor,
            bin_size=context.bin_size,
            target_coin=context.target_coin,
            mark_price=context.mark_price,
            current_price=context.current_price,
            live_overrides={"0x1": "ov1", "0x3": "ov3"},
            live_enrichment_stats=context.live_enrichment_stats,
        )

    monkeypatch.setattr(precompute, "_select_top_target_users", fake_select_top_target_users)
    monkeypatch.setattr(
        precompute,
        "_extend_context_live_overrides_for_selected_users",
        fake_extend_context_live_overrides_for_selected_users,
    )

    updated_context, selected_users = precompute._select_v3_target_users(context)

    assert updated_context.live_overrides == {"0x1": "ov1", "0x3": "ov3"}
    assert selected_users == ["0x3", "0x1", "0x2"]
    assert calls == [
        ("notional", ()),
        ("live_liq_intensity", ("0x1", "0x2", "0x3", "0x4")),
    ]


def test_prepare_symbol_contexts_reuses_shared_anchor_state(monkeypatch: pytest.MonkeyPatch) -> None:
    shared_state = _sidecar_state(["0x1"], coin="BTC", mark_price=60000.0)
    load_calls: list[tuple[str, str | None]] = []

    def fake_load(self, path, *, target_coin=None):
        load_calls.append((str(path), target_coin))
        return shared_state

    def fake_prepare(symbol, **kwargs):
        assert kwargs["shared_state"] is shared_state
        return precompute.SymbolBuildContext(
            symbol=symbol,
            request=SimpleNamespace(),
            plan=SimpleNamespace(anchor_coverage=SimpleNamespace(latest_anchor_in_window="anchor")),
            source_anchor=str(kwargs["anchor_path"]),
            enable_live_enrichment=kwargs["enable_live_enrichment"],
            state=shared_state,
            reconstructor=precompute.SidecarPositionReconstructor(),
            bin_size=10.0,
            target_coin=symbol,
            mark_price=60000.0,
            current_price=60000.0,
            live_overrides={},
            live_enrichment_stats=precompute.LiveEnrichmentStats(),
        )

    monkeypatch.setattr(precompute.SidecarPositionReconstructor, "load_abci_anchor", fake_load)
    monkeypatch.setattr(precompute, "_prepare_symbol_context", fake_prepare)

    contexts = precompute.prepare_symbol_contexts(
        ["BTC", "ETH"],
        anchor_path="/tmp/anchor.rmp",
        enable_live_enrichment=False,
    )

    assert [context.symbol for context in contexts] == ["BTC", "ETH"]
    assert load_calls == [("/tmp/anchor.rmp", None)]


def test_prepare_symbol_context_filters_anchor_load_by_target_coin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_calls: list[tuple[str, str | None]] = []
    shared_state = _sidecar_state(["0x1"], coin="BTC", mark_price=60000.0)

    def fake_load(self, path, *, target_coin=None):
        load_calls.append((str(path), target_coin))
        return shared_state

    class FakeBuilder:
        def build(self, request):
            return SimpleNamespace(
                bin_size=10.0,
                anchor_coverage=SimpleNamespace(
                    latest_anchor_in_window=Path("/tmp/latest-anchor.rmp")
                ),
            )

    monkeypatch.setattr(precompute, "HyperliquidSidecarPrototypeBuilder", FakeBuilder)
    monkeypatch.setattr(precompute.SidecarPositionReconstructor, "load_abci_anchor", fake_load)
    monkeypatch.setattr(precompute, "LIVE_ENRICH_TOP_N", 0)

    context = precompute._prepare_symbol_context("BTC", enable_live_enrichment=False)

    assert context is not None
    assert context.target_coin == "BTC"
    assert load_calls == [("/tmp/latest-anchor.rmp", "BTC")]


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
            return type(
                "_Meta",
                (),
                {
                    "universe": [
                        type(
                            "AssetMetaStub",
                            (),
                            {
                                "name": "BTC",
                                "maxLeverage": 50,
                                "marginTableId": 1,
                            },
                        )()
                    ],
                    "assetContexts": [
                        type("AssetCtxStub", (), {"markPx": 60000.0})()
                    ],
                    "margin_tables": {
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
                    },
                },
            )()

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
