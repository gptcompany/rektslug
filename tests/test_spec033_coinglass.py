import pytest
def test_coinglass_uses_binance_liqmap():
    endpoint = "https://capi.coinglass.com/api/index/5/liqMap"
    assert "liqMap" in endpoint
    assert "liqHeatMap" not in endpoint
