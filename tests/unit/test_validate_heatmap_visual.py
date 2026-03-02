import pytest

from scripts.validate_heatmap_visual import build_heatmap_page_url


def test_build_heatmap_page_url_uses_canonical_chart_route_for_7d() -> None:
    url = build_heatmap_page_url(
        api_base="http://127.0.0.1:8002",
        symbol="BTCUSDT",
        time_window="7d",
    )

    assert url == "http://127.0.0.1:8002/chart/derivatives/liq-heat-map/btcusdt/1w"


def test_build_heatmap_page_url_preserves_legacy_30d_window() -> None:
    url = build_heatmap_page_url(
        api_base="http://127.0.0.1:8002",
        symbol="ETHUSDT",
        time_window="30d",
    )

    assert (
        url
        == "http://127.0.0.1:8002/frontend/coinglass_heatmap.html"
        "?symbol=ETHUSDT&window=30d&ui=minimal"
    )


def test_build_heatmap_page_url_rejects_unknown_window() -> None:
    with pytest.raises(ValueError):
        build_heatmap_page_url(
            api_base="http://127.0.0.1:8002",
            symbol="BTCUSDT",
            time_window="2w",
        )
