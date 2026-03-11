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

    assert len(agg_df) == 1
    row = agg_df.iloc[0]
    assert float(row["price_bucket"]) == 81000.0
    assert float(row["volume"]) == 5.0
    assert int(row["leverage"]) == 25
