"""Load expert snapshot artifacts as Nautilus Trader CustomData events.

Reads artifacts from disk (Hyperliquid expert snapshots or modeled snapshots),
computes pre-aggregated features, and wraps them as CustomData for backtest replay.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

from src.liquidationheatmap.modeled_snapshots.snapshot_schema import (
    validate_artifact as validate_modeled_artifact,
)
from src.liquidationheatmap.nautilus.data import (  # noqa: E402
    LiquidationMapData,
    compute_features,
    iso_to_nanos,
)

# Import snapshot_schema directly to avoid hyperliquid/__init__.py which
# pulls in models.py with StrEnum (Python 3.11+).
_schema_path = Path(__file__).parent.parent / "hyperliquid" / "snapshot_schema.py"
_spec = importlib.util.spec_from_file_location("snapshot_schema", _schema_path)
_schema_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
sys.modules.setdefault("snapshot_schema", _schema_mod)
_spec.loader.exec_module(_schema_mod)  # type: ignore[union-attr]

ALL_EXPERT_IDS: list[str] = _schema_mod.ALL_EXPERT_IDS
validate_artifact = _schema_mod.validate_artifact

logger = logging.getLogger(__name__)

DEFAULT_HL_ARTIFACTS_DIR = Path("data/validation/expert_snapshots/hyperliquid")
DEFAULT_MODELED_SNAPSHOTS_DIR = Path("data/validation/modeled_snapshots")
DEFAULT_LOADER_IDS = {
    "hyperliquid": ["v1"],
    "binance": ["binance_standard"],
    "bybit": ["bybit_standard"],
}


def load_liquidation_events(
    symbol: str = "BTCUSDT",
    exchange: str = "hyperliquid",
    expert_ids: list[str] | None = None,
    artifacts_dir: Path | str | None = None,
    include_raw: bool = False,
    strict: bool = True,
) -> list[Any]:
    """Load expert snapshot artifacts as NT Data events for backtest.

    Args:
        symbol: Trading pair (e.g., 'BTCUSDT').
        exchange: Exchange name ('hyperliquid', 'binance', 'bybit').
        expert_ids: Which expert variants/model IDs to load.
        artifacts_dir: Override base directory for artifacts.
        include_raw: If True, include raw distributions in event data.
        strict: If True, raise RuntimeError if no events are loaded.

    Returns:
        List of CustomData wrapping NTLiquidationMapData, sorted by ts_event.
        Pass directly to engine.add_data(). Requires nautilus_trader.
    """
    from src.liquidationheatmap.nautilus import _check_nautilus

    _check_nautilus()

    from nautilus_trader.model.data import CustomData, DataType

    from src.liquidationheatmap.nautilus.nt_types import NTLiquidationMapData

    expert_ids = expert_ids or _default_loader_ids(exchange)
    instrument_id = f"{symbol}-PERP.{exchange.upper()}"

    # Discover and load artifacts (validation happens in raw loader)
    raw_events = load_liquidation_events_raw(
        symbol=symbol,
        exchange=exchange,
        expert_ids=expert_ids,
        artifacts_dir=artifacts_dir,
        include_raw=include_raw,
        strict=strict,
    )

    # Wrap in CustomData(DataType(NTLiquidationMapData)) for DataEngine routing
    data_type = DataType(
        NTLiquidationMapData,
        metadata={"instrument_id": instrument_id},
    )
    custom_events = [
        CustomData(data_type=data_type, data=NTLiquidationMapData(event)) for event in raw_events
    ]

    logger.info(
        "Loaded %d liquidation events (%s experts, %s timestamps)",
        len(custom_events),
        len(expert_ids),
        len(raw_events) // max(len(expert_ids), 1),
    )

    return custom_events


def load_liquidation_events_raw(
    symbol: str = "BTCUSDT",
    exchange: str = "hyperliquid",
    expert_ids: list[str] | None = None,
    artifacts_dir: Path | str | None = None,
    include_raw: bool = False,
    strict: bool = True,
) -> list[LiquidationMapData]:
    """Load artifacts as LiquidationMapData objects (no NT dependency needed).

    Useful for testing feature computation without installing nautilus_trader.

    Returns:
        List of LiquidationMapData sorted by ts_event ascending.
    """
    expert_ids = expert_ids or _default_loader_ids(exchange)

    _validate_loader_ids(exchange, expert_ids)

    base_dir = _resolve_artifacts_dir(exchange, artifacts_dir)
    ts_init = int(time.time() * 1_000_000_000)

    events: list[LiquidationMapData] = []

    # Discover snapshot timestamps from artifact directories
    timestamps = _discover_timestamps(base_dir, symbol, exchange)
    if not timestamps:
        msg = f"No snapshot timestamps found in {base_dir} for {symbol}"
        if strict:
            raise RuntimeError(msg)
        logger.warning(msg)
        return []

    for snapshot_ts in sorted(timestamps):
        for expert_id in expert_ids:
            artifact = _load_single_artifact(base_dir, symbol, snapshot_ts, expert_id, exchange)
            if artifact is None:
                continue

            ts_event = iso_to_nanos(artifact["snapshot_ts"])
            features = compute_features(
                artifact["long_distribution"],
                artifact["short_distribution"],
                artifact["reference_price"],
            )

            event = LiquidationMapData(
                ts_event=ts_event,
                ts_init=ts_init,
                expert_id=expert_id,
                symbol=symbol,
                exchange=exchange,
                reference_price=artifact["reference_price"],
                long_distribution=artifact["long_distribution"] if include_raw else None,
                short_distribution=artifact["short_distribution"] if include_raw else None,
                **features,
            )
            events.append(event)

    if not events and strict:
        raise RuntimeError(f"No liquidation events were successfully loaded for {symbol}")

    events.sort(key=lambda e: (e.ts_event, e.expert_id))
    return events


def _resolve_artifacts_dir(exchange: str, override: Path | str | None) -> Path:
    """Resolve the base directory for artifact files."""
    if override:
        return Path(override)
    if exchange == "hyperliquid":
        return DEFAULT_HL_ARTIFACTS_DIR
    return DEFAULT_MODELED_SNAPSHOTS_DIR / exchange


def _default_loader_ids(exchange: str) -> list[str]:
    """Return the default expert/model IDs for a given exchange."""
    return list(DEFAULT_LOADER_IDS.get(exchange, ["v1"]))


def _validate_loader_ids(exchange: str, loader_ids: list[str]) -> None:
    """Validate the exchange-specific loader identifiers."""
    for loader_id in loader_ids:
        if not isinstance(loader_id, str) or not loader_id.strip():
            raise ValueError("Loader identifiers must be non-empty strings")
        if exchange == "hyperliquid" and loader_id not in ALL_EXPERT_IDS:
            raise ValueError(f"Unknown expert_id '{loader_id}'. Valid: {ALL_EXPERT_IDS}")


def _discover_timestamps(base_dir: Path, symbol: str, exchange: str) -> list[str]:
    """Discover available snapshot timestamps from manifest or artifact directories."""
    # Try manifest-based discovery first
    manifest_dir = base_dir / "manifests" / symbol.upper()
    if manifest_dir.exists():
        return [p.stem for p in manifest_dir.glob("*.json")]

    # Fallback: discover from artifact directory structure
    if exchange == "hyperliquid":
        artifact_dir = base_dir / "artifacts" / symbol.upper()
    else:
        artifact_dir = base_dir / "artifacts" / symbol.upper()

    if not artifact_dir.exists():
        return []

    return [d.name for d in artifact_dir.iterdir() if d.is_dir()]


def _load_single_artifact(
    base_dir: Path,
    symbol: str,
    snapshot_ts: str,
    expert_id: str,
    exchange: str,
) -> dict[str, Any] | None:
    """Load and validate a single artifact JSON file.

    Returns validated artifact dict or None if not found/invalid.
    """
    if exchange == "hyperliquid":
        artifact_path = base_dir / "artifacts" / symbol.upper() / snapshot_ts / f"{expert_id}.json"
    else:
        artifact_path = _resolve_modeled_artifact_path(base_dir, symbol, snapshot_ts, expert_id)

    if not artifact_path.exists():
        logger.debug("Artifact not found: %s", artifact_path)
        return None

    try:
        with open(artifact_path, encoding="utf-8") as f:
            payload = json.load(f)

        if exchange == "hyperliquid":
            # Use schema validation for HL artifacts
            validated = validate_artifact(payload)
            return {
                "snapshot_ts": validated.snapshot_ts,
                "reference_price": validated.reference_price,
                "long_distribution": validated.long_distribution,
                "short_distribution": validated.short_distribution,
            }
        else:
            # Modeled snapshots have a different schema
            return _extract_modeled_snapshot_fields(payload, snapshot_ts)

    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.warning("Failed to load artifact %s: %s", artifact_path, e)
        return None


def _resolve_modeled_artifact_path(
    base_dir: Path,
    symbol: str,
    snapshot_ts: str,
    model_id: str,
) -> Path:
    """Resolve a modeled artifact path from manifest metadata or stable layout."""
    manifest_path = base_dir / "manifests" / symbol.upper() / f"{snapshot_ts}.json"
    if manifest_path.exists():
        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
            model_entry = manifest.get("models", {}).get(model_id, {})
            artifact_rel_path = model_entry.get("artifact_path")
            status = model_entry.get("availability_status")
            if artifact_rel_path and status in {"available", "partial"}:
                return base_dir / artifact_rel_path
        except (json.JSONDecodeError, OSError, TypeError) as e:
            logger.debug("Failed to inspect manifest %s: %s", manifest_path, e)

    return base_dir / "artifacts" / symbol.upper() / snapshot_ts / f"{model_id}.json"


def _extract_modeled_snapshot_fields(payload: dict[str, Any], snapshot_ts: str) -> dict[str, Any]:
    """Extract common fields from a modeled snapshot artifact (Binance/Bybit)."""
    try:
        validated = validate_modeled_artifact(payload)
        return {
            "snapshot_ts": validated.snapshot_ts,
            "reference_price": validated.reference_price,
            "long_distribution": validated.long_distribution,
            "short_distribution": validated.short_distribution,
        }
    except ValueError:
        # Backward-compatible fallback for older transient bucket-based payloads.
        long_dist: dict[str, float] = {}
        short_dist: dict[str, float] = {}

        for bucket in payload.get("long_buckets", []):
            price = str(bucket.get("price_level", bucket.get("price", 0)))
            volume = float(bucket.get("volume", 0))
            if volume > 0:
                long_dist[price] = volume

        for bucket in payload.get("short_buckets", []):
            price = str(bucket.get("price_level", bucket.get("price", 0)))
            volume = float(bucket.get("volume", 0))
            if volume > 0:
                short_dist[price] = volume

        return {
            "snapshot_ts": snapshot_ts,
            "reference_price": float(
                payload.get("reference_price", payload.get("current_price", 0))
            ),
            "long_distribution": long_dist,
            "short_distribution": short_dist,
        }
