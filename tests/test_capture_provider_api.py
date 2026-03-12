from __future__ import annotations

import sys
from pathlib import Path

import pytest

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

    @classmethod
    def empty(cls) -> "_FakePage":
        page = cls.__new__(cls)
        page.heading = ""
        page.symbol_combobox = None
        page.timeframe_combobox = None
        return page

    async def wait_for_timeout(self, ms: int) -> None:
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
                    _FakeElement(page=self, value=""),
                ]
            )

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
