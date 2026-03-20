from __future__ import annotations

import sys
from pathlib import Path

import pytest

import argparse
REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
for p in (str(REPO_ROOT), str(SCRIPTS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)


class _FakeElement:
    def __init__(
        self,
        *,
        page: "_FakePage",
        value: str = "",
        text: str | None = None,
        tag_name: str = "div",
        visible: bool = True,
        on_click=None,
    ) -> None:
        self.page = page
        self.value = value
        self.text = text if text is not None else value
        self.tag_name = tag_name
        self.visible = visible
        self._on_click = on_click

    async def inner_text(self) -> str:
        return self.text

    async def evaluate(self, expression: str):
        if "tagName" in expression:
            return self.tag_name
        return self.value

    async def click(self, timeout: int | None = None) -> None:
        if not self.visible:
            raise RuntimeError("not visible")
        if self._on_click is not None:
            self._on_click()

    async def fill(self, value: str, timeout: int | None = None) -> None:
        self.value = value

    async def press(self, key: str, timeout: int | None = None) -> None:
        return None

    async def wait_for(self, state: str = "visible", timeout: int | None = None) -> None:
        if state == "visible" and not self.visible:
            raise RuntimeError("not visible")


class _FakeLocatorCollection:
    def __init__(self, elements: list[_FakeElement]) -> None:
        self.elements = elements

    async def count(self) -> int:
        return len(self.elements)

    def nth(self, index: int) -> _FakeElement:
        return self.elements[index]

    @property
    def first(self) -> _FakeElement:
        if not self.elements:
            return _FakeElement(page=_FakePage.empty(), visible=False)
        return self.elements[0]


class _FakeHeadingElement(_FakeElement):
    async def inner_text(self) -> str:
        return self.page.heading

    async def evaluate(self, expression: str):
        return self.page.heading


class _FakePage:
    def __init__(self) -> None:
        self.heading = "Binance BTC/USDT Liquidation Map"
        self.symbol_combobox = _FakeElement(
            page=self,
            value="Binance BTC/USDT Perpetual",
            text="Binance BTC/USDT Perpetual",
            tag_name="input",
        )
        self.timeframe_combobox = _FakeElement(
            page=self,
            value="",
            text="1 day",
            tag_name="button",
        )
        self.hyperliquid_combobox = _FakeElement(
            page=self,
            value="BTC",
            text="BTC",
            tag_name="input",
        )
        self.buttons = [_FakeElement(page=self, value="") for _ in range(6)]

    @classmethod
    def empty(cls) -> "_FakePage":
        page = cls.__new__(cls)
        page.heading = ""
        page.symbol_combobox = None
        page.timeframe_combobox = None
        page.hyperliquid_combobox = None
        page.buttons = []
        return page

    async def wait_for_timeout(self, ms: int) -> None:
        return None

    async def evaluate(self, expression: str, arg: str | None = None):
        if arg == "Hyperliquid Liquidation Map" and "querySelectorAll('button')" in expression:
            return 5
        if arg == "Hyperliquid Liquidation Map":
            return 5
        return None

    def locator(self, selector: str) -> _FakeLocatorCollection:
        if selector == '[role="combobox"]':
            return _FakeLocatorCollection(
                [
                    _FakeElement(page=self, value=""),
                    self.symbol_combobox,
                    _FakeElement(page=self, value=""),
                    self.timeframe_combobox,
                    _FakeElement(page=self, value=""),
                    self.hyperliquid_combobox,
                ]
            )

        if selector == "button":
            return _FakeLocatorCollection(self.buttons)

        if selector == "h1":
            return _FakeLocatorCollection([_FakeHeadingElement(page=self)])

        if selector == '[role="option"]:has-text("Binance ETH/USDT Perpetual")':
            return _FakeLocatorCollection(
                [
                    _FakeElement(
                        page=self,
                        value="Binance ETH/USDT Perpetual",
                        on_click=self._apply_eth_symbol,
                    )
                ]
            )

        if selector == '[role="option"]:has-text("ETH")':
            return _FakeLocatorCollection(
                [
                    _FakeElement(
                        page=self,
                        value="ETH",
                        on_click=self._apply_hyperliquid_eth,
                    )
                ]
            )

        if selector == '[role="option"]:has-text("1 week")':
            return _FakeLocatorCollection(
                [
                    _FakeElement(
                        page=self,
                        value="1 week",
                        on_click=self._apply_one_week,
                    )
                ]
            )

        return _FakeLocatorCollection([])

    def _apply_eth_symbol(self) -> None:
        self.symbol_combobox.value = "Binance ETH/USDT Perpetual"
        self.heading = "Binance ETH/USDT Liquidation Map"

    def _apply_hyperliquid_eth(self) -> None:
        self.hyperliquid_combobox.value = "ETH"
        self.hyperliquid_combobox.text = "ETH"

    def _apply_one_week(self) -> None:
        self.timeframe_combobox.value = ""
        self.timeframe_combobox.text = "1 week"


@pytest.mark.asyncio
async def test_apply_coinglass_symbol_uses_exact_option_fast_path():
    from scripts.capture_provider_api import (
        COINGLASS_LIQMAP_PAGE_URL,
        CaptureTarget,
        apply_coinglass_symbol,
    )

    page = _FakePage()
    target = CaptureTarget(
        provider="coinglass",
        url=COINGLASS_LIQMAP_PAGE_URL,
        coin="ETH",
        ui_timeframe="1 day",
    )

    applied = await apply_coinglass_symbol(target, page)

    assert applied is True
    assert page.symbol_combobox.value == "Binance ETH/USDT Perpetual"
    assert page.heading == "Binance ETH/USDT Liquidation Map"


@pytest.mark.asyncio
async def test_apply_coinglass_symbol_targets_hyperliquid_widget():
    from scripts.capture_provider_api import (
        COINGLASS_LIQMAP_PAGE_URL,
        CaptureTarget,
        apply_coinglass_symbol,
    )

    page = _FakePage()
    target = CaptureTarget(
        provider="coinglass",
        url=COINGLASS_LIQMAP_PAGE_URL,
        coin="ETH",
        ui_timeframe="7 day",
        exchange="hyperliquid",
    )

    applied = await apply_coinglass_symbol(target, page)

    assert applied is True
    assert page.hyperliquid_combobox.value == "ETH"
    assert page.symbol_combobox.value == "Binance BTC/USDT Perpetual"


@pytest.mark.asyncio
async def test_apply_coinglass_timeframe_uses_exact_option_fast_path():
    from scripts.capture_provider_api import (
        COINGLASS_LIQMAP_PAGE_URL,
        CaptureTarget,
        apply_coinglass_timeframe,
    )

    page = _FakePage()
    target = CaptureTarget(
        provider="coinglass",
        url=COINGLASS_LIQMAP_PAGE_URL,
        coin="BTC",
        ui_timeframe="1 week",
    )

    applied = await apply_coinglass_timeframe(target, page)

    assert applied is True
    assert page.timeframe_combobox.text == "1 week"


def test_build_targets_uses_liqmap_page_for_hyperliquid():
    from scripts.capture_provider_api import COINGLASS_LIQMAP_PAGE_URL, build_targets

    args = argparse.Namespace(
        provider="coinglass",
        coin="ETH",
        timeframe="1w",
        exchange="hyperliquid",
        coinank_url=None,
        coinglass_url=None,
        bitcoincounterflow_url=None,
        coinglass_timeframe=None,
    )

    targets = build_targets(args)

    assert len(targets) == 1
    assert targets[0].provider == "coinglass"
    assert targets[0].url == COINGLASS_LIQMAP_PAGE_URL
    assert targets[0].exchange == "hyperliquid"


def test_build_targets_loads_coinglass_secrets_from_get_secret(monkeypatch: pytest.MonkeyPatch):
    import scripts.capture_provider_api as module

    secret_map = {
        "COINGLASS_USER_LOGIN": "user@example.com",
        "COINGLASS_USER_PASSWORD": "super-secret",
    }
    monkeypatch.setattr(module, "get_secret", lambda key: secret_map.get(key))

    args = argparse.Namespace(
        provider="coinglass",
        coin="ETH",
        timeframe="1w",
        exchange="binance",
        coinank_url=None,
        coinglass_url=None,
        bitcoincounterflow_url=None,
        coinglass_timeframe=None,
    )

    targets = module.build_targets(args)

    assert len(targets) == 1
    assert targets[0].email == "user@example.com"
    assert targets[0].password == "super-secret"


def test_capture_coinglass_rest_rejects_hyperliquid(tmp_path: Path):
    from scripts.capture_provider_api import (
        COINGLASS_LIQMAP_PAGE_URL,
        CaptureTarget,
        capture_coinglass_rest,
    )

    target = CaptureTarget(
        provider="coinglass",
        url=COINGLASS_LIQMAP_PAGE_URL,
        coin="ETH",
        ui_timeframe="7 day",
        exchange="hyperliquid",
    )

    with pytest.raises(RuntimeError, match="exchange=hyperliquid"):
        capture_coinglass_rest(target, tmp_path)
