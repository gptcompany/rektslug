from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProviderProfile:
    """Explicit provider/profile metadata shared across comparison workflows."""

    name: str
    display_name: str
    roles: frozenset[str]
    default_renderer_adapter: str | None = None
    data_comparison_ready: bool = False
    visual_reference: bool = False
    notes: tuple[str, ...] = ()

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "roles": sorted(self.roles),
            "default_renderer_adapter": self.default_renderer_adapter,
            "data_comparison_ready": self.data_comparison_ready,
            "visual_reference": self.visual_reference,
            "notes": list(self.notes),
        }


PROVIDER_PROFILES: dict[str, ProviderProfile] = {
    "coinank": ProviderProfile(
        name="coinank",
        display_name="CoinAnk",
        roles=frozenset({"data-source", "visual-reference"}),
        default_renderer_adapter="plotly",
        data_comparison_ready=True,
        visual_reference=True,
        notes=(
            "Primary liq-map visual comparison target.",
            "Captured through provider-page workflows, not a local renderer adapter.",
        ),
    ),
    "coinglass": ProviderProfile(
        name="coinglass",
        display_name="Coinglass",
        roles=frozenset({"data-source", "visual-reference"}),
        default_renderer_adapter="plotly",
        data_comparison_ready=True,
        visual_reference=True,
        notes=(
            "Visual wiring is still gated on canonical route/capture invariants.",
            "Raw payload comparison is already supported in the provider workflow.",
        ),
    ),
    "bitcoincounterflow": ProviderProfile(
        name="bitcoincounterflow",
        display_name="Bitcoin CounterFlow",
        roles=frozenset({"data-source", "visual-reference"}),
        default_renderer_adapter="lightweight",
        data_comparison_ready=True,
        visual_reference=True,
        notes=(
            "Raw /api/liquidations capture is comparison-ready as a time-series feed.",
            "Future visual harness integration must enter through renderer_adapter=lightweight.",
        ),
    ),
    "rektslug": ProviderProfile(
        name="rektslug",
        display_name="Rektslug",
        roles=frozenset({"data-source", "visual-reference"}),
        default_renderer_adapter="plotly",
        data_comparison_ready=True,
        visual_reference=True,
        notes=(
            "Local calibrated model path used as the first concrete visual harness baseline.",
        ),
    ),
}


def get_provider_profile(name: str) -> ProviderProfile:
    """Return provider profile metadata, falling back to an explicit unknown profile."""
    profile = PROVIDER_PROFILES.get(name)
    if profile is not None:
        return profile
    return ProviderProfile(
        name=name,
        display_name=name,
        roles=frozenset({"unknown"}),
        default_renderer_adapter=None,
        data_comparison_ready=False,
        visual_reference=False,
        notes=("Provider profile has not been documented yet.",),
    )

