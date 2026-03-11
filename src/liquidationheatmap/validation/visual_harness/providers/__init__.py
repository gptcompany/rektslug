"""Provider capture adapters for the visual harness."""

from .coinank import capture_coinank_liqmap_capture
from .local import capture_local_liqmap_capture

__all__ = [
    "capture_coinank_liqmap_capture",
    "capture_local_liqmap_capture",
]
