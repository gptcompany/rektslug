"""Browser-style tests for the canonical liq-map frontend on spec-022."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

import pytest

try:
    from playwright.async_api import Error as PlaywrightError
    from playwright.async_api import async_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not PLAYWRIGHT_AVAILABLE,
    reason="Playwright not installed - run: uv add playwright && playwright install chromium",
)


@pytest.fixture()
def free_port():
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _LiqMapHandler(BaseHTTPRequestHandler):
    frontend_path = Path(__file__).resolve().parents[2] / "frontend" / "liq_map_1w.html"
    request_log: list[str] = []
    payload = {
        "schema_version": "1.0",
        "source": "coinank-public-builder",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "profile": "rektslug-ank-public",
        "current_price": 60000.0,
        "grid": {
            "step": 10.0,
            "anchor_price": 60000.0,
            "min_price": 55200.0,
            "max_price": 64800.0,
        },
        "leverage_ladder": [
            "25x",
            "30x",
            "40x",
            "50x",
            "60x",
            "70x",
            "80x",
            "90x",
            "100x",
        ],
        "long_buckets": [
            {"price_level": 59970.0, "leverage": "25x", "volume": 20.0},
            {"price_level": 59980.0, "leverage": "50x", "volume": 10.0},
        ],
        "short_buckets": [
            {"price_level": 60020.0, "leverage": "80x", "volume": 7.0},
            {"price_level": 60040.0, "leverage": "100x", "volume": 3.0},
        ],
        "cumulative_long": [
            {"price_level": 59970.0, "value": 30.0},
            {"price_level": 59980.0, "value": 10.0},
            {"price_level": 60000.0, "value": 0.0},
        ],
        "cumulative_short": [
            {"price_level": 60000.0, "value": 0.0},
            {"price_level": 60020.0, "value": 7.0},
            {"price_level": 60040.0, "value": 10.0},
        ],
        "last_data_timestamp": "2026-03-13T12:00:00Z",
        "is_stale_real_data": False,
    }
    hl_payload = {
        "source": "hyperliquid-sidecar",
        "symbol": "BTCUSDT",
        "timeframe": "1w",
        "current_price": 68500.0,
        "mark_price": 68500.0,
        "account_count": 123,
        "generated_at": "2026-03-13T12:00:00Z",
        "grid": {
            "step": 500.0,
            "anchor_price": 68500.0,
            "min_price": 50000.0,
            "max_price": 90000.0,
        },
        "leverage_ladder": ["cross"],
        "long_buckets": [
            {"price_level": 64000.0, "leverage": "cross", "volume": 1000.0},
        ],
        "short_buckets": [
            {"price_level": 72000.0, "leverage": "cross", "volume": 1500.0},
        ],
        "cumulative_long": [
            {"price_level": 64000.0, "value": 1000.0},
        ],
        "cumulative_short": [
            {"price_level": 72000.0, "value": 1500.0},
        ],
        "out_of_range_volume": {
            "long": 0.0,
            "short": 0.0,
        },
        "source_anchor": "data/cache/hl_sidecar_btcusdt.json",
        "bin_size": 500.0,
    }
    legacy_payload = {
        "symbol": "SOLUSDT",
        "model": "openinterest",
        "current_price": "140.0",
        "long_liquidations": [
            {"price_level": "130.0", "leverage": "10x", "volume": "20.0", "count": 1},
            {"price_level": "135.0", "leverage": "25x", "volume": "10.0", "count": 1},
        ],
        "short_liquidations": [
            {"price_level": "145.0", "leverage": "10x", "volume": "7.0", "count": 1},
            {"price_level": "150.0", "leverage": "25x", "volume": "3.0", "count": 1},
        ],
    }

    def do_GET(self):
        self.__class__.request_log.append(self.path)

        if self.path.startswith("/chart/derivatives/liq-map/"):
            html = self.frontend_path.read_text(encoding="utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
            return

        if self.path == "/frontend/styles.css":
            self.send_response(200)
            self.send_header("Content-Type", "text/css; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"")
            return

        if self.path.startswith("/liquidations/coinank-public-map"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(self.payload).encode("utf-8"))
            return

        if self.path.startswith("/liquidations/hl-public-map"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(self.hl_payload).encode("utf-8"))
            return

        if self.path.startswith("/liquidations/levels"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(self.legacy_payload).encode("utf-8"))
            return

        if self.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, *_args):
        pass


@pytest.fixture
def liqmap_server(free_port):
    _LiqMapHandler.request_log = []
    server = HTTPServer(("127.0.0.1", free_port), _LiqMapHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{free_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


async def _launch_browser_or_skip(playwright):
    try:
        return await playwright.chromium.launch()
    except PlaywrightError as exc:
        if "Executable doesn't exist" in str(exc):
            pytest.skip("Playwright browser executable not installed")
        raise


async def _route_plotly(page) -> None:
    async def _fulfill_plotly(route):
        await route.fulfill(
            content_type="application/javascript",
            body="""
            window.Plotly = {
                newPlot: function(_id, traces, layout) {
                    window.__lastPlotlyRender = { traces, layout };
                    return Promise.resolve({
                        _fullLayout: {
                            yaxis: { range: [0, 30] },
                            yaxis2: { range: [0, 30] }
                        }
                    });
                },
                react: function(id, traces, layout) {
                    return this.newPlot(id, traces, layout);
                },
                relayout: function() {
                    return Promise.resolve();
                }
            };
            """,
        )

    await page.route("https://cdn.plot.ly/plotly-2.26.0.min.js", _fulfill_plotly)


@pytest.mark.asyncio
async def test_canonical_liqmap_frontend_renders_from_public_builder_payload(liqmap_server):
    async with async_playwright() as playwright:
        browser = await _launch_browser_or_skip(playwright)
        page = await browser.new_page()
        await _route_plotly(page)
        await page.goto(f"{liqmap_server}/chart/derivatives/liq-map/binance/btcusdt/1d")
        await page.wait_for_function(
            "() => Boolean(window.__lastPlotlyRender) || typeof window.__liqMapLoadError === 'string'"
        )

        assert await page.evaluate("() => window.__liqMapLoadError") is None
        assert await page.evaluate("() => Boolean(window.__lastPlotlyRender)") is True
        assert any(
            "/liquidations/coinank-public-map" in request_path
            for request_path in _LiqMapHandler.request_log
        )

        await browser.close()


@pytest.mark.asyncio
async def test_non_parity_symbol_falls_back_to_legacy_levels(liqmap_server):
    async with async_playwright() as playwright:
        browser = await _launch_browser_or_skip(playwright)
        page = await browser.new_page()
        _LiqMapHandler.request_log = []
        await _route_plotly(page)
        await page.goto(f"{liqmap_server}/chart/derivatives/liq-map/binance/solusdt/1w")
        await page.wait_for_function(
            "() => Boolean(window.__lastPlotlyRender) || typeof window.__liqMapLoadError === 'string'"
        )

        assert await page.evaluate("() => window.__liqMapLoadError") is None
        assert await page.evaluate("() => Boolean(window.__lastPlotlyRender)") is True
        assert any(
            "/liquidations/levels" in request_path
            for request_path in _LiqMapHandler.request_log
        )

        await browser.close()


@pytest.mark.asyncio
async def test_explicit_profile_override_preserves_legacy_levels_path(liqmap_server):
    async with async_playwright() as playwright:
        browser = await _launch_browser_or_skip(playwright)
        page = await browser.new_page()
        _LiqMapHandler.request_log = []
        await _route_plotly(page)
        await page.goto(
            f"{liqmap_server}/chart/derivatives/liq-map/binance/btcusdt/1d?profile=rektslug-glass"
        )
        await page.wait_for_function(
            "() => Boolean(window.__lastPlotlyRender) || typeof window.__liqMapLoadError === 'string'"
        )

        assert await page.evaluate("() => window.__liqMapLoadError") is None
        assert await page.evaluate("() => Boolean(window.__lastPlotlyRender)") is True
        assert any(
            "/liquidations/levels" in request_path
            and "profile=rektslug-glass" in request_path
            for request_path in _LiqMapHandler.request_log
        )
        assert not any(
            "/liquidations/coinank-public-map" in request_path
            for request_path in _LiqMapHandler.request_log
        )

        await browser.close()


@pytest.mark.asyncio
async def test_bybit_route_uses_unified_public_map_endpoint(liqmap_server):
    async with async_playwright() as playwright:
        browser = await _launch_browser_or_skip(playwright)
        page = await browser.new_page()

        _LiqMapHandler.request_log = []
        await _route_plotly(page)
        await page.goto(f"{liqmap_server}/chart/derivatives/liq-map/bybit/btcusdt/1w")
        await page.wait_for_function(
            "() => Boolean(window.__lastPlotlyRender) || typeof window.__liqMapLoadError === 'string'"
        )

        assert await page.evaluate("() => window.__liqMapLoadError") is None
        assert any(
            "/liquidations/coinank-public-map" in request_path
            and "exchange=bybit" in request_path
            for request_path in _LiqMapHandler.request_log
        )
        assert not any(
            "/liquidations/levels" in request_path for request_path in _LiqMapHandler.request_log
        )

        await browser.close()


@pytest.mark.asyncio
async def test_hyperliquid_route_uses_hl_public_endpoint(liqmap_server):
    async with async_playwright() as playwright:
        browser = await _launch_browser_or_skip(playwright)
        page = await browser.new_page()

        _LiqMapHandler.request_log = []
        await _route_plotly(page)
        await page.goto(f"{liqmap_server}/chart/derivatives/liq-map/hyperliquid/btcusdt/1w")
        await page.wait_for_function(
            "() => Boolean(window.__lastPlotlyRender) || typeof window.__liqMapLoadError === 'string'"
        )

        assert await page.evaluate("() => window.__liqMapLoadError") is None
        assert any(
            "/liquidations/hl-public-map" in request_path
            for request_path in _LiqMapHandler.request_log
        )
        assert not any(
            "/liquidations/coinank-public-map" in request_path
            for request_path in _LiqMapHandler.request_log
        )
        assert not any(
            "/liquidations/levels" in request_path for request_path in _LiqMapHandler.request_log
        )

        await browser.close()
