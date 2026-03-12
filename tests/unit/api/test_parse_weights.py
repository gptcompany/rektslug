import pandas as pd

from src.liquidationheatmap.api.routers.liquidations import (
    _aggregate_legacy_levels,
    parse_leverage_weights,
)

def test_parse_leverage_weights_json():
    res = parse_leverage_weights('{"10": 0.5, "25": 0.5}')
    assert res == {10: 0.5, 25: 0.5}

def test_parse_leverage_weights_json_normalizes_percentages():
    res = parse_leverage_weights('{"10": 50, "25": 50}')
    assert res == {10: 0.5, 25: 0.5}

def test_parse_leverage_weights_json_filters_unsupported_tiers():
    assert parse_leverage_weights('{"7": 1}') is None
    assert parse_leverage_weights('{"7": 1, "25": 3}') == {25: 1.0}

def test_parse_leverage_weights_custom():
    res = parse_leverage_weights('10:0.5,25:0.5')
    assert res == {10: 0.5, 25: 0.5}

def test_parse_leverage_weights_invalid():
    assert parse_leverage_weights('invalid') is None
    assert parse_leverage_weights('10:0.5,invalid') == {10: 1.0} # invalid pair skipped, normalized

def test_aggregate_legacy_levels_buckets_liquidation_prices():
    bins_df = pd.DataFrame(
        [
            {"liq_price": 80736.0, "side": "sell", "volume": 2.0, "leverage": 10},
            {"liq_price": 81252.0, "side": "sell", "volume": 3.0, "leverage": 25},
        ]
    )

    agg_df = _aggregate_legacy_levels(bins_df, 1000.0)

    assert len(agg_df) == 2
    assert set(float(row["price_bucket"]) for _, row in agg_df.iterrows()) == {81000.0}
    assert set(int(row["leverage"]) for _, row in agg_df.iterrows()) == {10, 25}
    assert set(float(row["volume"]) for _, row in agg_df.iterrows()) == {2.0, 3.0}


def test_aggregate_legacy_levels_preserves_distinct_leverage_rows_in_same_bucket():
    bins_df = pd.DataFrame(
        [
            {"liq_price": 2041.2, "side": "buy", "volume": 10.0, "leverage": 25},
            {"liq_price": 2041.4, "side": "buy", "volume": 20.0, "leverage": 50},
            {"liq_price": 2041.1, "side": "buy", "volume": 30.0, "leverage": 100},
        ]
    )

    agg_df = _aggregate_legacy_levels(bins_df, 0.45)

    assert len(agg_df) == 3
    assert set(int(row["leverage"]) for _, row in agg_df.iterrows()) == {25, 50, 100}
    assert sum(float(row["volume"]) for _, row in agg_df.iterrows()) == 60.0
