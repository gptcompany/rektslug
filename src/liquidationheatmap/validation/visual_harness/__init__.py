"""Visual comparison harness for screenshot-based provider validation."""

from .manifest import SCHEMA_VERSION, ArtifactPaths, build_artifact_paths
from .runner import RunOutcome, VisualHarnessRequest, resolve_adapter_bundle, run_visual_pair
from .scorer import build_score_report

__all__ = [
    "ArtifactPaths",
    "RunOutcome",
    "SCHEMA_VERSION",
    "VisualHarnessRequest",
    "build_artifact_paths",
    "build_score_report",
    "resolve_adapter_bundle",
    "run_visual_pair",
]
