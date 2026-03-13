"""Unit tests for the spec-022 public liqmap builder helpers."""

from decimal import Decimal

import pytest

from src.liquidationheatmap.api.public_liqmap import (
    COINANK_PUBLIC_LEVERAGE_LADDER,
    CoinankPublicBucket,
    CoinankPublicCumulativePoint,
    CoinankPublicGrid,
    CoinankPublicMapResponse,
    build_cumulative_series,
    derive_public_liqmap_range,
    expand_public_leverage_ladder,
    resolve_public_liqmap_step,
    snap_price_to_public_grid,
)


def test_response_model_exposes_frozen_public_builder_contract():
    payload = CoinankPublicMapResponse(
        schema_version="1.0",
        source="coinank-public-builder",
        symbol="BTCUSDT",
        timeframe="1d",
        profile="rektslug-ank-public",
        current_price=60123.45,
        grid=CoinankPublicGrid(
            step=10.0,
            anchor_price=60123.45,
            min_price=55200.0,
            max_price=64800.0,
        ),
        leverage_ladder=COINANK_PUBLIC_LEVERAGE_LADDER,
        long_buckets=[CoinankPublicBucket(price_level=59800.0, leverage="50x", volume=123.0)],
        short_buckets=[CoinankPublicBucket(price_level=60500.0, leverage="50x", volume=456.0)],
        cumulative_long=[
            CoinankPublicCumulativePoint(price_level=59800.0, value=123.0),
            CoinankPublicCumulativePoint(price_level=60123.45, value=0.0),
        ],
        cumulative_short=[
            CoinankPublicCumulativePoint(price_level=60123.45, value=0.0),
            CoinankPublicCumulativePoint(price_level=60500.0, value=456.0),
        ],
        last_data_timestamp="2026-03-13T12:00:00Z",
        is_stale_real_data=False,
    )

    dumped = payload.model_dump(mode="json")
    assert dumped["schema_version"] == "1.0"
    assert dumped["source"] == "coinank-public-builder"
    assert dumped["grid"]["step"] == 10.0
    assert dumped["leverage_ladder"] == COINANK_PUBLIC_LEVERAGE_LADDER
    assert dumped["cumulative_long"][-1] == {"price_level": 60123.45, "value": 0.0}


def test_symbol_and_timeframe_aware_grid_step_is_frozen():
    assert resolve_public_liqmap_step("BTCUSDT", "1d") == Decimal("10.0")
    assert resolve_public_liqmap_step("BTCUSDT", "1w") == Decimal("25.0")
    assert resolve_public_liqmap_step("ETHUSDT", "1d") == Decimal("0.5")
    assert resolve_public_liqmap_step("ETHUSDT", "1w") == Decimal("2.0")


def test_unsupported_symbol_and_timeframe_are_rejected():
    with pytest.raises(ValueError, match="Unsupported public liqmap symbol"):
        resolve_public_liqmap_step("SOLUSDT", "1d")

    with pytest.raises(ValueError, match="Unsupported public liqmap timeframe"):
        resolve_public_liqmap_step("BTCUSDT", "30d")


def test_snap_price_uses_current_price_anchor():
    snapped = snap_price_to_public_grid(
        raw_price=Decimal("60063"),
        anchor_price=Decimal("60000"),
        step=Decimal("25"),
    )
    assert snapped == Decimal("60075")


def test_richer_leverage_ladder_is_preserved_before_grouping():
    raw_buckets = [
        CoinankPublicBucket(price_level=59800.0, leverage="25x", volume=90.0),
        CoinankPublicBucket(price_level=59800.0, leverage="50x", volume=60.0),
        CoinankPublicBucket(price_level=60500.0, leverage="100x", volume=30.0),
    ]

    expanded = expand_public_leverage_ladder(raw_buckets)

    assert [bucket.leverage for bucket in expanded] == [
        "25x",
        "30x",
        "40x",
        "50x",
        "60x",
        "70x",
        "80x",
        "90x",
        "100x",
    ]
    assert sum(bucket.volume for bucket in expanded) == pytest.approx(180.0)


def test_cumulative_series_anchor_at_current_price():
    long_points = build_cumulative_series(
        side="long",
        current_price=Decimal("100"),
        buckets=[
            CoinankPublicBucket(price_level=90.0, leverage="50x", volume=20.0),
            CoinankPublicBucket(price_level=95.0, leverage="60x", volume=10.0),
        ],
    )
    short_points = build_cumulative_series(
        side="short",
        current_price=Decimal("100"),
        buckets=[
            CoinankPublicBucket(price_level=105.0, leverage="80x", volume=7.0),
            CoinankPublicBucket(price_level=110.0, leverage="90x", volume=3.0),
        ],
    )

    assert long_points == [
        CoinankPublicCumulativePoint(price_level=90.0, value=30.0),
        CoinankPublicCumulativePoint(price_level=95.0, value=10.0),
        CoinankPublicCumulativePoint(price_level=100.0, value=0.0),
    ]
    assert short_points == [
        CoinankPublicCumulativePoint(price_level=100.0, value=0.0),
        CoinankPublicCumulativePoint(price_level=105.0, value=7.0),
        CoinankPublicCumulativePoint(price_level=110.0, value=10.0),
    ]


def test_btc_eth_and_1d_1w_use_distinct_range_envelopes():
    observed_prices = [
        Decimal("92"),
        Decimal("94"),
        Decimal("96"),
        Decimal("104"),
        Decimal("106"),
        Decimal("108"),
    ]

    one_day_range = derive_public_liqmap_range(
        observed_prices=observed_prices,
        current_price=Decimal("100"),
        timeframe="1d",
    )
    one_week_range = derive_public_liqmap_range(
        observed_prices=observed_prices,
        current_price=Decimal("100"),
        timeframe="1w",
    )

    assert one_day_range == (90.56, 109.44)
    assert one_week_range == (88.0, 112.0)

