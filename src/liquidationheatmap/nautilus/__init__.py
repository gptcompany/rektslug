"""Nautilus Trader bridge for liquidation map events.

Optional module: requires `nautilus_trader` to be installed.
Install with: uv pip install -e ".[nautilus]"
"""


def _check_nautilus():
    """Verify nautilus_trader is available, raise clear error if not."""
    try:
        import nautilus_trader  # noqa: F401
    except ImportError:
        raise ImportError(
            "nautilus_trader is required for this module. "
            "Install with: uv pip install -e '.[nautilus]'"
        ) from None


from src.liquidationheatmap.nautilus.feedback_publisher import NautilusFeedbackPublisher

__all__ = ["_check_nautilus", "NautilusFeedbackPublisher"]
