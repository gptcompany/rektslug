from src.liquidationheatmap.api.routers.liquidations import parse_leverage_weights

def test_parse_leverage_weights_json():
    res = parse_leverage_weights('{"10": 0.5, "25": 0.5}')
    assert res == {10: 0.5, 25: 0.5}

def test_parse_leverage_weights_custom():
    res = parse_leverage_weights('10:0.5,25:0.5')
    assert res == {10: 0.5, 25: 0.5}

def test_parse_leverage_weights_invalid():
    assert parse_leverage_weights('invalid') is None
    assert parse_leverage_weights('10:0.5,invalid') == {10: 1.0} # invalid pair skipped, normalized
