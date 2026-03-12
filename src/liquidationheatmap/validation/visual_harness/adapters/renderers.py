from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RendererAdapter:
    name: str
    default: bool = False


RENDERER_ADAPTERS: dict[str, RendererAdapter] = {
    "plotly": RendererAdapter(name="plotly", default=True),
    "lightweight": RendererAdapter(name="lightweight", default=False),
}


def get_renderer_adapter(name: str) -> RendererAdapter:
    try:
        return RENDERER_ADAPTERS[name]
    except KeyError as exc:
        raise ValueError(f"Unsupported renderer: {name}") from exc
