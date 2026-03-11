from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RendererAdapter:
    name: str


RENDERER_ADAPTERS: dict[str, RendererAdapter] = {
    "plotly": RendererAdapter(name="plotly"),
    "lightweight": RendererAdapter(name="lightweight"),
}


def get_renderer_adapter(name: str) -> RendererAdapter:
    try:
        return RENDERER_ADAPTERS[name]
    except KeyError as exc:
        raise ValueError(f"Unsupported renderer: {name}") from exc
