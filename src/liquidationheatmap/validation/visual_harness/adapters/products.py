from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProductAdapter:
    name: str
    supported_renderers: frozenset[str]


PRODUCT_ADAPTERS: dict[str, ProductAdapter] = {
    "liq-map": ProductAdapter(name="liq-map", supported_renderers=frozenset({"plotly"})),
    "liq-heat-map": ProductAdapter(name="liq-heat-map", supported_renderers=frozenset({"plotly"})),
}


def get_product_adapter(name: str) -> ProductAdapter:
    try:
        return PRODUCT_ADAPTERS[name]
    except KeyError as exc:
        raise ValueError(f"Unsupported product: {name}") from exc
