"""Minimal Hyperliquid sidecar prototype scaffolding.

This first slice does not attempt account-level replay yet. It builds the
prototype context needed for the first `ETH 7d` sidecar iteration:

- bin-size resolution using the existing profile registry
- local source coverage discovery for filtered, ABCI, and ccxt catalog roots
- explicit exactness-gap reporting so the prototype cannot overclaim parity
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path

from src.liquidationheatmap.models.profiles import get_profile

DEFAULT_FILTERED_ROOT = Path("/media/sam/4TB-NVMe/hyperliquid/filtered")
DEFAULT_ABCI_ROOT = Path("/media/sam/4TB-NVMe/docker-volumes/hyperliquid/hl/data/periodic_abci_states")
DEFAULT_CCXT_CATALOG_ROOT = Path("/media/sam/1TB/ccxt-data-pipeline/data/catalog")
DEFAULT_PROFILE_NAME = "rektslug-ank"

FILTERED_DATASETS: tuple[tuple[str, Path], ...] = (
    ("fills", Path("node_fills_by_block/hourly")),
    ("order_statuses", Path("node_order_statuses_by_block/hourly")),
    ("raw_book_diffs", Path("node_raw_book_diffs_by_block/hourly")),
    ("oracle_updates", Path("hip3_oracle_updates_by_block/hourly")),
)

CCXT_DATASETS: tuple[tuple[str, str], ...] = (
    ("funding_rate", "{symbol}-PERP.HYPERLIQUID"),
    ("open_interest", "{symbol}-PERP.HYPERLIQUID"),
    ("ohlcv", "{symbol}-PERP.HYPERLIQUID"),
    ("trades", "{symbol}-PERP.HYPERLIQUID"),
)

FALLBACK_BIN_SIZES = {
    "BTCUSDT": 100.0,
    "ETHUSDT": 10.0,
}


class ExactnessGap(StrEnum):
    """Known blockers for path-exact replay claims."""

    MISSING_START_ANCHOR = "missing_start_anchor"
    MISSING_COLLATERAL_STREAM = "missing_collateral_adjustment_stream"
    FUNDING_APPLICATION_UNPROVEN = "funding_application_timing_unproven"
    OFF_TARGET_ACTIVITY_UNBOUNDED = "off_target_activity_unbounded"


@dataclass(frozen=True)
class SidecarBuildRequest:
    """Input for the first sidecar prototype build."""

    symbol: str
    timeframe_days: int
    analysis_end: datetime
    current_price: float | None = None
    profile_name: str = DEFAULT_PROFILE_NAME

    def __post_init__(self) -> None:
        if self.timeframe_days <= 0:
            raise ValueError("timeframe_days must be positive")
        object.__setattr__(self, "symbol", normalize_symbol(self.symbol))
        object.__setattr__(self, "analysis_end", ensure_utc(self.analysis_end))

    @property
    def target_coin(self) -> str:
        return self.symbol.removesuffix("USDT")

    @property
    def window_start(self) -> datetime:
        return self.analysis_end - timedelta(days=self.timeframe_days)


@dataclass(frozen=True)
class DatasetCoverage:
    """Availability summary for a local dataset root."""

    name: str
    root: Path
    date_keys: tuple[str, ...]
    file_count: int
    available: bool
    latest_file: Path | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "root": str(self.root),
            "date_keys": list(self.date_keys),
            "file_count": self.file_count,
            "available": self.available,
            "latest_file": str(self.latest_file) if self.latest_file else None,
        }


@dataclass(frozen=True)
class AnchorCoverage:
    """Candidate anchor coverage over the requested analysis window."""

    root: Path
    selection_granularity: str
    latest_day_at_or_before_start: str | None
    start_anchor_candidate: Path | None
    window_date_dirs: tuple[str, ...]
    window_file_count: int
    latest_anchor_in_window: Path | None

    @property
    def has_start_anchor_candidate(self) -> bool:
        return self.start_anchor_candidate is not None

    def to_dict(self) -> dict:
        return {
            "root": str(self.root),
            "selection_granularity": self.selection_granularity,
            "latest_day_at_or_before_start": self.latest_day_at_or_before_start,
            "start_anchor_candidate": (
                str(self.start_anchor_candidate) if self.start_anchor_candidate else None
            ),
            "window_date_dirs": list(self.window_date_dirs),
            "window_file_count": self.window_file_count,
            "latest_anchor_in_window": (
                str(self.latest_anchor_in_window) if self.latest_anchor_in_window else None
            ),
            "has_start_anchor_candidate": self.has_start_anchor_candidate,
        }


@dataclass(frozen=True)
class PrototypeBuildPlan:
    """Reviewable output for the first sidecar builder slice."""

    request: SidecarBuildRequest
    bin_size: float
    replay_status: str
    anchor_coverage: AnchorCoverage
    filtered_sources: tuple[DatasetCoverage, ...]
    catalog_sources: tuple[DatasetCoverage, ...]
    exactness_gaps: tuple[ExactnessGap, ...]
    notes: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "schema_version": "hyperliquid-sidecar-prototype.v0",
            "symbol": self.request.symbol,
            "target_coin": self.request.target_coin,
            "timeframe_days": self.request.timeframe_days,
            "window_start_utc": self.request.window_start.isoformat(),
            "analysis_end_utc": self.request.analysis_end.isoformat(),
            "profile_name": self.request.profile_name,
            "current_price": self.request.current_price,
            "bin_size": self.bin_size,
            "replay_status": self.replay_status,
            "anchor_coverage": self.anchor_coverage.to_dict(),
            "filtered_sources": [source.to_dict() for source in self.filtered_sources],
            "catalog_sources": [source.to_dict() for source in self.catalog_sources],
            "exactness_gaps": [gap.value for gap in self.exactness_gaps],
            "notes": list(self.notes),
        }


class HyperliquidSidecarPrototypeBuilder:
    """Build a bounded prototype plan for the first Hyperliquid sidecar."""

    def __init__(
        self,
        *,
        filtered_root: Path = DEFAULT_FILTERED_ROOT,
        abci_root: Path = DEFAULT_ABCI_ROOT,
        ccxt_catalog_root: Path = DEFAULT_CCXT_CATALOG_ROOT,
    ) -> None:
        self.filtered_root = Path(filtered_root)
        self.abci_root = Path(abci_root)
        self.ccxt_catalog_root = Path(ccxt_catalog_root)

    def build(self, request: SidecarBuildRequest) -> PrototypeBuildPlan:
        anchor_coverage = self.discover_anchor_coverage(
            window_start=request.window_start,
            analysis_end=request.analysis_end,
        )
        filtered_sources = self.discover_filtered_sources(request)
        catalog_sources = self.discover_catalog_sources(request)

        gaps = [
            ExactnessGap.MISSING_COLLATERAL_STREAM,
            ExactnessGap.FUNDING_APPLICATION_UNPROVEN,
            ExactnessGap.OFF_TARGET_ACTIVITY_UNBOUNDED,
        ]
        if not anchor_coverage.has_start_anchor_candidate:
            gaps.insert(0, ExactnessGap.MISSING_START_ANCHOR)

        replay_status = (
            "anchor-candidate-available"
            if anchor_coverage.has_start_anchor_candidate
            else "unanchored"
        )
        notes = (
            "Prototype V0 resolves bin size and local source coverage only; "
            "account-level replay is intentionally still out of scope.",
            "ABCI anchor discovery is day-granular in V0; candidate presence is useful for planning but is not yet a proof of snapshot-exact window alignment.",
            "Replay exactness remains bounded until transfer/collateral events, funding application timing, and off-target account activity are observed directly.",
        )

        return PrototypeBuildPlan(
            request=request,
            bin_size=self.resolve_bin_size(request),
            replay_status=replay_status,
            anchor_coverage=anchor_coverage,
            filtered_sources=filtered_sources,
            catalog_sources=catalog_sources,
            exactness_gaps=tuple(gaps),
            notes=notes,
        )

    def resolve_bin_size(self, request: SidecarBuildRequest) -> float:
        """Use the existing profile registry, with the spec fallback on failure."""
        try:
            profile = get_profile(request.profile_name)
            bin_size = profile.get_bin_size(
                timeframe_days=request.timeframe_days,
                current_price=request.current_price,
                symbol=request.symbol,
            )
            if bin_size > 0:
                return float(bin_size)
        except (KeyError, TypeError, ValueError):
            pass

        return FALLBACK_BIN_SIZES.get(request.symbol, 100.0)

    def discover_filtered_sources(self, request: SidecarBuildRequest) -> tuple[DatasetCoverage, ...]:
        days = tuple(iter_dates(request.window_start.date(), request.analysis_end.date()))
        return tuple(
            self._discover_filtered_source(
                name=name,
                dataset_root=self.filtered_root / relative_path,
                days=days,
            )
            for name, relative_path in FILTERED_DATASETS
        )

    def discover_catalog_sources(self, request: SidecarBuildRequest) -> tuple[DatasetCoverage, ...]:
        symbol_key = f"{request.target_coin}USDT"
        days = tuple(iter_dates(request.window_start.date(), request.analysis_end.date()))
        return tuple(
            self._discover_catalog_source(
                name=name,
                dataset_root=self.ccxt_catalog_root / name / pattern.format(symbol=symbol_key),
                days=days,
            )
            for name, pattern in CCXT_DATASETS
        )

    def discover_anchor_coverage(
        self,
        *,
        window_start: datetime,
        analysis_end: datetime,
    ) -> AnchorCoverage:
        available_days = (
            {
                parsed_day: path
                for path in sorted(self.abci_root.iterdir())
                if path.is_dir() and (parsed_day := parse_day_dir(path.name)) is not None
            }
            if self.abci_root.exists()
            else {}
        )

        start_day = window_start.date()
        latest_day_at_or_before_start = max(
            (day for day in available_days if day <= start_day),
            default=None,
        )
        start_anchor_candidate = None
        latest_day_string = None
        if latest_day_at_or_before_start is not None:
            latest_day_string = latest_day_at_or_before_start.strftime("%Y%m%d")
            start_anchor_candidate = latest_file(available_days[latest_day_at_or_before_start], "*.rmp")

        window_days = [
            day for day in available_days if start_day <= day <= analysis_end.date()
        ]
        window_date_dirs = tuple(day.strftime("%Y%m%d") for day in sorted(window_days))

        window_file_count = 0
        latest_anchor_in_window = None
        for day in sorted(window_days):
            day_root = available_days[day]
            files = sorted(day_root.glob("*.rmp"))
            window_file_count += len(files)
            if files:
                latest_anchor_in_window = files[-1]

        return AnchorCoverage(
            root=self.abci_root,
            selection_granularity="day",
            latest_day_at_or_before_start=latest_day_string,
            start_anchor_candidate=start_anchor_candidate,
            window_date_dirs=window_date_dirs,
            window_file_count=window_file_count,
            latest_anchor_in_window=latest_anchor_in_window,
        )

    def _discover_filtered_source(
        self,
        *,
        name: str,
        dataset_root: Path,
        days: tuple[date, ...],
    ) -> DatasetCoverage:
        matched_keys: list[str] = []
        file_count = 0
        latest_seen: Path | None = None

        for day in days:
            day_key = day.strftime("%Y%m%d")
            day_root = dataset_root / day_key
            if not day_root.exists():
                continue
            files = sorted(day_root.glob("*.zst"))
            if not files:
                continue
            matched_keys.append(day_key)
            file_count += len(files)
            latest_seen = files[-1]

        return DatasetCoverage(
            name=name,
            root=dataset_root,
            date_keys=tuple(matched_keys),
            file_count=file_count,
            available=file_count > 0,
            latest_file=latest_seen,
        )

    def _discover_catalog_source(
        self,
        *,
        name: str,
        dataset_root: Path,
        days: tuple[date, ...],
    ) -> DatasetCoverage:
        matched_keys: list[str] = []
        file_count = 0
        latest_seen: Path | None = None

        for day in days:
            day_key = day.isoformat()
            day_file = dataset_root / f"{day_key}.parquet"
            if not day_file.exists():
                continue
            matched_keys.append(day_key)
            file_count += 1
            latest_seen = day_file

        return DatasetCoverage(
            name=name,
            root=dataset_root,
            date_keys=tuple(matched_keys),
            file_count=file_count,
            available=file_count > 0,
            latest_file=latest_seen,
        )


def normalize_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if normalized.endswith("USDT"):
        return normalized
    return f"{normalized}USDT"


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def iter_dates(start_day: date, end_day: date) -> list[date]:
    if end_day < start_day:
        return []
    day_count = (end_day - start_day).days + 1
    return [start_day + timedelta(days=offset) for offset in range(day_count)]


def parse_day_dir(value: str) -> date | None:
    if len(value) != 8 or not value.isdigit():
        return None
    return datetime.strptime(value, "%Y%m%d").date()


def latest_file(root: Path, file_glob: str) -> Path | None:
    files = sorted(root.glob(file_glob))
    return files[-1] if files else None
