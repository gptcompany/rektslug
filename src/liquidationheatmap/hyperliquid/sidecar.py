"""Minimal Hyperliquid sidecar prototype scaffolding.

This first slice does not attempt account-level replay yet. It builds the
prototype context needed for the first `ETH 7d` sidecar iteration:

- bin-size resolution using the existing profile registry
- local source coverage discovery for filtered, ABCI, and ccxt catalog roots
- explicit exactness-gap reporting so the prototype cannot overclaim parity
"""

from __future__ import annotations

import io
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

import msgpack
import zstandard as zstd

from src.liquidationheatmap.models.profiles import get_profile
from src.liquidationheatmap.hyperliquid.margin_math import get_margin_tier, compute_position_maintenance_margin

DEFAULT_FILTERED_ROOT = Path("/media/sam/4TB-NVMe/hyperliquid/filtered")
DEFAULT_ABCI_ROOT = Path(
    "/media/sam/4TB-NVMe/docker-volumes/hyperliquid/hl/data/periodic_abci_states"
)
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
class UserPosition:
    """Reconstructed position state."""

    coin: str
    asset_idx: int
    size: float
    entry_px: float
    leverage: float
    cum_funding: float
    margin: float
    cum_funding_open: float | None = None
    cum_funding_closed: float | None = None
    extra_fields: Mapping[str, object] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True)
class UserState:
    """Reconstructed per-user state."""

    user: str
    balance: float
    positions: tuple[UserPosition, ...]
    balance_state_s: float | None = None
    balance_state_r: float | None = None
    extra_fields: Mapping[str, object] = field(default_factory=lambda: MappingProxyType({}))

    @property
    def has_active_positions(self) -> bool:
        return any(p.size != 0 for p in self.positions)


@dataclass(frozen=True)
class UserOrder:
    """Reconstructed resting order state."""

    user: str
    oid: int
    coin: str
    side: str
    limit_px: float
    size: float
    orig_size: float | None = None
    tif: str | None = None
    order_type: str | None = None
    reduce_only: bool | None = None
    is_trigger: bool | None = None
    is_position_tpsl: bool | None = None
    status: str | None = None
    order_timestamp_ms: int | None = None
    extra_fields: Mapping[str, object] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True)
class OrderExposureBounds:
    """Bounded exposure-increasing resting-order notional for one user."""

    total_active_notional: float
    non_reduce_only_notional: float
    exposure_increasing_notional_lower_bound: float
    exposure_increasing_notional_upper_bound: float
    target_coin_notional: float
    off_target_notional: float
    target_coin_exposure_increasing_lower_bound: float
    target_coin_exposure_increasing_upper_bound: float
    off_target_exposure_increasing_lower_bound: float
    off_target_exposure_increasing_upper_bound: float
    reduce_only_notional: float
    active_order_count: int
    non_reduce_only_order_count: int
    reduce_only_order_count: int
    per_coin: Mapping[str, Mapping[str, float | int | None]] = field(
        default_factory=lambda: MappingProxyType({})
    )


@dataclass(frozen=True)
class SidecarState:
    """The full reconstructed state for a set of relevant accounts."""

    timestamp: datetime
    users: dict[str, UserState]
    mark_prices: dict[int, float]
    asset_margin_tiers: dict[int, list[dict]]


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

    def reconstruct(self, request: SidecarBuildRequest) -> SidecarState:
        """Perform the first position-state reconstruction iteration.

        Currently this is 'snapshot-only' - it loads the latest anchor in the window
        and builds the risk surface from it, without replaying events yet.
        """
        plan = self.build(request)
        if not plan.anchor_coverage.latest_anchor_in_window:
            raise ValueError(f"No anchors available in window for {request.symbol}")

        reconstructor = SidecarPositionReconstructor()
        return reconstructor.load_abci_anchor(
            plan.anchor_coverage.latest_anchor_in_window,
            target_coin=request.target_coin,
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

    def discover_filtered_sources(
        self, request: SidecarBuildRequest
    ) -> tuple[DatasetCoverage, ...]:
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
            start_anchor_candidate = latest_file(
                available_days[latest_day_at_or_before_start], "*.rmp"
            )

        window_days = [day for day in available_days if start_day <= day <= analysis_end.date()]
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


def freeze_msgpack_value(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: freeze_msgpack_value(val) for key, val in value.items()})
    if isinstance(value, list):
        return tuple(freeze_msgpack_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(freeze_msgpack_value(item) for item in value)
    return value


def iter_zst_jsonl(path: Path) -> Iterable[dict]:
    """Yield JSONL blocks from a zstd-compressed file."""
    dctx = zstd.ZstdDecompressor()
    with path.open("rb") as fh:
        with dctx.stream_reader(fh) as reader:
            text_stream = io.TextIOWrapper(reader, encoding="utf-8")
            for line in text_stream:
                line = line.strip()
                if not line:
                    continue
                try:
                    block = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(block, dict):
                    yield block


class SidecarPositionReconstructor:
    """Engine for account-level state reconstruction from Hyperliquid sources."""

    def load_abci_anchor(
        self,
        path: Path,
        *,
        target_coin: str | None = None,
        target_users: set[str] | None = None,
    ) -> SidecarState:
        """Load and decode a MessagePack ABCI snapshot."""
        snapshot = self._load_snapshot_filtered(path, target_users=target_users)

        locus = snapshot.get("exchange", {}).get("locus", {})
        cls_list = locus.get("cls", [])
        if not cls_list or not isinstance(cls_list, list):
            raise ValueError(f"Invalid ABCI snapshot format at {path}: missing cls")

        cls0 = cls_list[0]
        meta = cls0.get("meta", {})
        universe_raw = meta.get("universe", [])
        asset_meta: dict[int, dict] = {}
        for idx, asset in enumerate(universe_raw):
            asset_meta[idx] = {
                "name": asset.get("name"),
                "szDecimals": asset.get("szDecimals", 0),
                "marginTableId": asset.get("marginTableId"),
            }

        margin_tables_raw = meta.get("marginTableIdToMarginTable", [])
        table_to_tiers: dict[int, list[dict]] = {}
        for item in margin_tables_raw:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            table_id, table_data = item[0], item[1]
            tiers_raw = table_data.get("margin_tiers", [])

            parsed_tiers = []
            for t in tiers_raw:
                max_lev = float(t.get("max_leverage", 50))
                parsed_tiers.append(
                    {
                        "lower_bound": float(t.get("lower_bound", 0)) / 1e6,
                        "mmr_rate": 1.0 / (2.0 * max_lev) if max_lev > 0 else 0.01,
                        "maintenance_deduction": float(t.get("maintenance_deduction", 0)) / 1e6,
                    }
                )

            parsed_tiers.sort(key=lambda x: x["lower_bound"], reverse=True)
            table_to_tiers[table_id] = parsed_tiers

        asset_margin_tiers: dict[int, list[dict]] = {}
        for idx, m in asset_meta.items():
            asset_margin_tiers[idx] = table_to_tiers.get(
                m["marginTableId"],
                [{"lower_bound": 0, "mmr_rate": 0.01, "maintenance_deduction": 0}],
            )

        pxs_raw = cls0.get("oracle", {}).get("pxs", [])
        mark_prices: dict[int, float] = {}
        for idx, oracles in enumerate(pxs_raw):
            if oracles and isinstance(oracles, list):
                raw_px = float(oracles[0].get("px", 0))
                sz_dec = asset_meta.get(idx, {}).get("szDecimals", 0)
                mark_prices[idx] = raw_px / (10 ** (6 - sz_dec))

        user_states_wrapper = cls0.get("user_states", {})
        user_to_state = user_states_wrapper.get("user_to_state", [])

        USDC_SCALE = 1e6
        reconstructed_users: dict[str, UserState] = {}

        def to_user_str(u: object) -> str:
            if isinstance(u, bytes):
                if len(u) == 20:
                    return "0x" + u.hex()
                try:
                    return u.decode()
                except UnicodeDecodeError:
                    return u.hex()
            return str(u)

        for item in user_to_state:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue

            user, state = item[0], item[1]
            if not isinstance(state, dict):
                continue

            user_str = to_user_str(user)
            if target_users is not None and user_str not in target_users:
                continue

            positions_wrapper = state.get("p", {})
            positions_raw = (
                positions_wrapper.get("p", []) if isinstance(positions_wrapper, dict) else []
            )
            if not positions_raw:
                continue

            positions: list[UserPosition] = []
            has_target = False

            for p_item in positions_raw:
                if not isinstance(p_item, (list, tuple)) or len(p_item) < 2:
                    continue

                asset_idx, p = p_item[0], p_item[1]
                if not isinstance(p, dict):
                    continue

                m = asset_meta.get(asset_idx)
                if not m or not m["name"]:
                    continue

                if target_coin and m["name"] == target_coin:
                    has_target = True

                size_raw = float(p.get("s", 0))
                if size_raw == 0:
                    continue

                size_scaled = size_raw / (10 ** m["szDecimals"])
                total_cost_scaled = float(p.get("e", 0)) / USDC_SCALE
                entry_px = total_cost_scaled / abs(size_scaled)
                funding_value = p.get("f", {})
                funding_raw = funding_value if isinstance(funding_value, dict) else {}
                leverage_value = p.get("l", {})
                leverage_raw = leverage_value if isinstance(leverage_value, dict) else {}
                isolated_raw = leverage_raw.get("I")
                leverage = 1.0
                if "C" in leverage_raw:
                    leverage = float(leverage_raw["C"])
                elif isinstance(isolated_raw, dict) and "l" in isolated_raw:
                    leverage = float(isolated_raw["l"])
                position_extras = {
                    key: value for key, value in p.items() if key not in {"s", "e", "M", "l", "f"}
                }

                pos = UserPosition(
                    coin=m["name"],
                    asset_idx=asset_idx,
                    size=size_scaled,
                    entry_px=entry_px,
                    margin=float(p.get("M", 0)),
                    leverage=leverage,
                    cum_funding=float(funding_raw.get("a", 0)) / USDC_SCALE,
                    cum_funding_open=(
                        float(funding_raw.get("o", 0)) / USDC_SCALE if "o" in funding_raw else None
                    ),
                    cum_funding_closed=(
                        float(funding_raw.get("c", 0)) / USDC_SCALE if "c" in funding_raw else None
                    ),
                    extra_fields=freeze_msgpack_value(position_extras),
                )
                positions.append(pos)

            if target_coin and not has_target:
                continue
            if not positions:
                continue

            # ABCI `u` already matches the API `crossMarginSummary.totalRawUsd` field.
            # It is a raw USD balance, so subtracting position costs again double-counts them.
            balance_raw = float(state.get("u", 0))
            s_value = state.get("S", {})
            s_state = s_value if isinstance(s_value, dict) else {}
            state_extras = {
                key: value for key, value in state.items() if key not in {"u", "p", "S"}
            }
            reconstructed_users[user_str] = UserState(
                user=user_str,
                balance=balance_raw / USDC_SCALE,
                positions=tuple(positions),
                balance_state_s=(
                    float(s_state.get("s", 0)) / USDC_SCALE if "s" in s_state else None
                ),
                balance_state_r=(
                    float(s_state.get("r", 0)) / USDC_SCALE if "r" in s_state else None
                ),
                extra_fields=freeze_msgpack_value(state_extras),
            )

        timestamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)

        return SidecarState(
            timestamp=timestamp,
            users=reconstructed_users,
            mark_prices=mark_prices,
            asset_margin_tiers=asset_margin_tiers,
        )

    def collect_active_order_users_from_blocks(
        self,
        *,
        order_status_blocks: Iterable[dict],
        raw_book_diff_blocks: Iterable[dict],
        target_coin: str | None = None,
    ) -> set[str]:
        """Collect users that still have active resting orders after replaying retained blocks."""

        def normalize_block_number(value: object) -> int | None:
            if isinstance(value, bool):
                return None
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
            return None

        def iter_block_events(blocks: Iterable[dict]) -> Iterable[tuple[int, list[dict]]]:
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                block_number = normalize_block_number(block.get("block_number"))
                if block_number is None:
                    continue
                events = block.get("events", [])
                if not isinstance(events, list):
                    continue
                yield block_number, events

        status_iter = iter(iter_block_events(order_status_blocks))
        book_iter = iter(iter_block_events(raw_book_diff_blocks))

        def next_item(iterator: Iterable[tuple[int, list[dict]]]) -> tuple[int, list[dict]] | None:
            return next(iterator, None)

        status_item = next_item(status_iter)
        book_item = next_item(book_iter)
        terminal_statuses = {
            "canceled",
            "filled",
            "rejected",
            "scheduledCancel",
            "badAloPxRejected",
            "perpMarginRejected",
            "minTradeNtlRejected",
            "iocCancelRejected",
            "reduceOnlyRejected",
            "triggerRejected",
        }
        active_keys: set[tuple[str, int]] = set()

        while status_item is not None or book_item is not None:
            block_candidates = [item[0] for item in (status_item, book_item) if item is not None]
            current_block = min(block_candidates)

            block_statuses = []
            while status_item is not None and status_item[0] == current_block:
                block_statuses.extend(status_item[1])
                status_item = next_item(status_iter)

            block_books = []
            while book_item is not None and book_item[0] == current_block:
                block_books.extend(book_item[1])
                book_item = next_item(book_iter)

            block_keys: set[tuple[str, int]] = set()
            terminal_keys: set[tuple[str, int]] = set()
            active_update_keys: set[tuple[str, int]] = set()

            for event in block_statuses:
                if not isinstance(event, dict):
                    continue
                user = str(event.get("user") or "")
                order_value = event.get("order", {})
                order = order_value if isinstance(order_value, dict) else {}
                oid = order.get("oid")
                coin = str(order.get("coin") or "")
                if not user or oid is None or not coin:
                    continue
                if target_coin and coin != target_coin:
                    continue
                try:
                    oid_int = int(oid)
                except (TypeError, ValueError):
                    continue

                key = (user, oid_int)
                block_keys.add(key)

                status = str(event.get("status") or "")
                if status in terminal_statuses:
                    terminal_keys.add(key)
                # Note: non-terminal status ALONE does not create a new active order,
                # it only updates metadata. The reconstructor ignores it if there's no book diff
                # and it's not already active.
                # So we do NOT add it to active_update_keys here.

            for event in block_books:
                if not isinstance(event, dict):
                    continue
                user = str(event.get("user") or "")
                oid = event.get("oid")
                coin = str(event.get("coin") or "")
                if not user or oid is None or not coin:
                    continue
                if target_coin and coin != target_coin:
                    continue
                try:
                    oid_int = int(oid)
                except (TypeError, ValueError):
                    continue

                key = (user, oid_int)
                block_keys.add(key)

                raw_diff = event.get("raw_book_diff")
                if raw_diff == "remove":
                    terminal_keys.add(key)
                elif isinstance(raw_diff, dict):
                    active_update_keys.add(key)

            for key in block_keys:
                if key in terminal_keys:
                    active_keys.discard(key)
                elif key in active_update_keys:
                    active_keys.add(key)

        return {user for user, _ in active_keys}

    def reconstruct_resting_orders_from_blocks(
        self,
        *,
        order_status_blocks: Iterable[dict],
        raw_book_diff_blocks: Iterable[dict],
        target_users: set[str] | None = None,
        target_coin: str | None = None,
    ) -> dict[str, tuple[UserOrder, ...]]:
        """Reconstruct currently resting orders from status and book-diff blocks.

        This is bounded to the blocks supplied by the consumer. It does not infer
        carry-in orders that were already resting before the first retained block.
        Processing is streaming by block number so retained files do not have to be
        buffered fully in memory.
        """

        def normalize_block_number(value: object) -> int | None:
            if isinstance(value, bool):
                return None
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
            return None

        def iter_block_events(blocks: Iterable[dict]) -> Iterable[tuple[int, list[dict]]]:
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                block_number = normalize_block_number(block.get("block_number"))
                if block_number is None:
                    continue
                events = block.get("events", [])
                if not isinstance(events, list):
                    continue
                yield block_number, events

        status_iter = iter(iter_block_events(order_status_blocks))
        book_iter = iter(iter_block_events(raw_book_diff_blocks))

        def next_item(iterator: Iterable[tuple[int, list[dict]]]) -> tuple[int, list[dict]] | None:
            return next(iterator, None)

        status_item = next_item(status_iter)
        book_item = next_item(book_iter)

        terminal_statuses = {
            "canceled",
            "filled",
            "rejected",
            "scheduledCancel",
            "badAloPxRejected",
            "perpMarginRejected",
            "minTradeNtlRejected",
            "iocCancelRejected",
            "reduceOnlyRejected",
            "triggerRejected",
        }
        active_orders: dict[tuple[str, int], UserOrder] = {}
        metadata_by_key: dict[tuple[str, int], dict[str, object]] = {}

        while status_item is not None or book_item is not None:
            block_candidates = [item[0] for item in (status_item, book_item) if item is not None]
            current_block = min(block_candidates)

            block_statuses = []
            while status_item is not None and status_item[0] == current_block:
                block_statuses.extend(status_item[1])
                status_item = next_item(status_iter)

            block_books = []
            while book_item is not None and book_item[0] == current_block:
                block_books.extend(book_item[1])
                book_item = next_item(book_iter)

            block_events_by_key: dict[tuple[str, int], list[tuple[str, dict]]] = {}

            for event in block_statuses:
                if not isinstance(event, dict):
                    continue
                user = str(event.get("user") or "")
                order_value = event.get("order", {})
                order = order_value if isinstance(order_value, dict) else {}
                oid = order.get("oid")
                coin = str(order.get("coin") or "")
                if not user or oid is None or not coin:
                    continue
                if target_users is not None and user not in target_users:
                    continue
                if target_coin and coin != target_coin:
                    continue
                try:
                    oid_int = int(oid)
                except (TypeError, ValueError):
                    continue
                key = (user, oid_int)
                block_events_by_key.setdefault(key, []).append(("status", event))

            for event in block_books:
                if not isinstance(event, dict):
                    continue
                user = str(event.get("user") or "")
                oid = event.get("oid")
                coin = str(event.get("coin") or "")
                if not user or oid is None or not coin:
                    continue
                if target_users is not None and user not in target_users:
                    continue
                if target_coin and coin != target_coin:
                    continue
                try:
                    oid_int = int(oid)
                except (TypeError, ValueError):
                    continue
                key = (user, oid_int)
                block_events_by_key.setdefault(key, []).append(("book", event))

            for key, events in block_events_by_key.items():
                user, oid_int = key
                is_terminal = False

                latest_meta = metadata_by_key.get(key, {})
                latest_book_delta = None
                latest_limit_px = None
                latest_side = None
                latest_coin = None

                for ev_type, event in events:
                    if ev_type == "status":
                        status = str(event.get("status") or "")
                        if status in terminal_statuses:
                            is_terminal = True
                        else:
                            order = event.get("order", {})
                            try:
                                limit_px = float(
                                    order.get("limitPx", latest_meta.get("limit_px", 0))
                                )
                            except (TypeError, ValueError):
                                limit_px = float(latest_meta.get("limit_px", 0))

                            try:
                                orig_size = float(
                                    order.get(
                                        "origSz", order.get("sz", latest_meta.get("orig_size", 0))
                                    )
                                )
                            except (TypeError, ValueError):
                                orig_size = float(latest_meta.get("orig_size", 0))

                            latest_meta.update(
                                {
                                    "coin": str(order.get("coin") or latest_meta.get("coin", "")),
                                    "side": str(order.get("side") or latest_meta.get("side", "")),
                                    "limit_px": limit_px,
                                    "orig_size": orig_size,
                                    "tif": order.get("tif"),
                                    "order_type": order.get("orderType"),
                                    "reduce_only": order.get("reduceOnly"),
                                    "is_trigger": order.get("isTrigger"),
                                    "is_position_tpsl": order.get("isPositionTpsl"),
                                    "status": status,
                                    "order_timestamp_ms": order.get("timestamp"),
                                }
                            )

                            extra_fields = latest_meta.get("extra_fields", {})
                            if isinstance(extra_fields, dict):
                                extra_fields = dict(extra_fields)
                            else:
                                extra_fields = {}

                            for k, v in order.items():
                                if k not in {
                                    "coin",
                                    "side",
                                    "limitPx",
                                    "sz",
                                    "oid",
                                    "timestamp",
                                    "triggerCondition",
                                    "isTrigger",
                                    "triggerPx",
                                    "children",
                                    "isPositionTpsl",
                                    "reduceOnly",
                                    "orderType",
                                    "origSz",
                                    "tif",
                                    "cloid",
                                }:
                                    extra_fields[k] = v

                            extra_fields.update(
                                {
                                    "status_hash": event.get("hash"),
                                    "builder": event.get("builder"),
                                    "cloid": order.get("cloid"),
                                    "trigger_condition": order.get("triggerCondition"),
                                    "trigger_px": order.get("triggerPx"),
                                    "children": order.get("children"),
                                }
                            )
                            latest_meta["extra_fields"] = extra_fields

                    elif ev_type == "book":
                        raw_diff = event.get("raw_book_diff")
                        if raw_diff == "remove":
                            is_terminal = True
                        elif isinstance(raw_diff, dict):
                            if isinstance(raw_diff.get("new"), dict):
                                latest_book_delta = raw_diff["new"]
                            elif isinstance(raw_diff.get("update"), dict):
                                latest_book_delta = raw_diff["update"]

                            if latest_limit_px is None:
                                latest_limit_px = event.get("px")
                            if latest_side is None:
                                latest_side = event.get("side")
                            if latest_coin is None:
                                latest_coin = event.get("coin")

                if is_terminal:
                    active_orders.pop(key, None)
                    metadata_by_key.pop(key, None)
                else:
                    metadata_by_key[key] = latest_meta
                    existing_order = active_orders.get(key)

                    if latest_book_delta is not None:
                        size_value = (
                            latest_book_delta.get("sz")
                            if "sz" in latest_book_delta
                            else latest_book_delta.get("newSz")
                        )
                        orig_size_value = (
                            latest_book_delta.get("sz")
                            if "sz" in latest_book_delta
                            else latest_book_delta.get("origSz")
                        )

                        try:
                            size = float(size_value)
                        except (TypeError, ValueError):
                            size = existing_order.size if existing_order else 0.0

                        orig_size = None
                        if orig_size_value is not None:
                            try:
                                orig_size = float(orig_size_value)
                            except (TypeError, ValueError):
                                orig_size = None
                        elif latest_meta.get("orig_size") is not None:
                            try:
                                orig_size = float(latest_meta["orig_size"])
                            except (TypeError, ValueError):
                                orig_size = None

                        extra_fields = (
                            dict(latest_meta.get("extra_fields", {}))
                            if isinstance(latest_meta.get("extra_fields"), dict)
                            else {}
                        )
                        extra_fields.update(
                            {
                                "block_number": current_block,
                                "book_diff": latest_book_delta,
                            }
                        )

                        limit_px_source = latest_meta.get(
                            "limit_px",
                            latest_limit_px or (existing_order.limit_px if existing_order else 0),
                        )
                        try:
                            limit_px = float(limit_px_source)
                        except (TypeError, ValueError):
                            limit_px = existing_order.limit_px if existing_order else 0.0

                        active_orders[key] = UserOrder(
                            user=user,
                            oid=oid_int,
                            coin=str(
                                latest_meta.get("coin")
                                or latest_coin
                                or (existing_order.coin if existing_order else "")
                            ),
                            side=str(
                                latest_meta.get("side")
                                or latest_side
                                or (existing_order.side if existing_order else "")
                            ),
                            limit_px=limit_px,
                            size=size,
                            orig_size=orig_size,
                            tif=str(latest_meta.get("tif"))
                            if latest_meta.get("tif") is not None
                            else (existing_order.tif if existing_order else None),
                            order_type=str(latest_meta.get("order_type"))
                            if latest_meta.get("order_type") is not None
                            else (existing_order.order_type if existing_order else None),
                            reduce_only=bool(latest_meta.get("reduce_only"))
                            if latest_meta.get("reduce_only") is not None
                            else (existing_order.reduce_only if existing_order else None),
                            is_trigger=bool(latest_meta.get("is_trigger"))
                            if latest_meta.get("is_trigger") is not None
                            else (existing_order.is_trigger if existing_order else None),
                            is_position_tpsl=bool(latest_meta.get("is_position_tpsl"))
                            if latest_meta.get("is_position_tpsl") is not None
                            else (existing_order.is_position_tpsl if existing_order else None),
                            status=str(latest_meta.get("status") or "open"),
                            order_timestamp_ms=int(latest_meta.get("order_timestamp_ms"))
                            if latest_meta.get("order_timestamp_ms") is not None
                            else (existing_order.order_timestamp_ms if existing_order else None),
                            extra_fields=freeze_msgpack_value(extra_fields),
                        )
                    elif existing_order is not None:
                        active_orders[key] = UserOrder(
                            user=existing_order.user,
                            oid=existing_order.oid,
                            coin=str(latest_meta.get("coin") or existing_order.coin),
                            side=str(latest_meta.get("side") or existing_order.side),
                            limit_px=float(latest_meta.get("limit_px", existing_order.limit_px)),
                            size=existing_order.size,
                            orig_size=float(latest_meta.get("orig_size", existing_order.orig_size))
                            if latest_meta.get("orig_size") is not None
                            else existing_order.orig_size,
                            tif=str(latest_meta.get("tif"))
                            if latest_meta.get("tif") is not None
                            else existing_order.tif,
                            order_type=str(latest_meta.get("order_type"))
                            if latest_meta.get("order_type") is not None
                            else existing_order.order_type,
                            reduce_only=bool(latest_meta.get("reduce_only"))
                            if latest_meta.get("reduce_only") is not None
                            else existing_order.reduce_only,
                            is_trigger=bool(latest_meta.get("is_trigger"))
                            if latest_meta.get("is_trigger") is not None
                            else existing_order.is_trigger,
                            is_position_tpsl=bool(latest_meta.get("is_position_tpsl"))
                            if latest_meta.get("is_position_tpsl") is not None
                            else existing_order.is_position_tpsl,
                            status=str(latest_meta.get("status") or "open"),
                            order_timestamp_ms=int(latest_meta.get("order_timestamp_ms"))
                            if latest_meta.get("order_timestamp_ms") is not None
                            else existing_order.order_timestamp_ms,
                            extra_fields=freeze_msgpack_value(
                                latest_meta.get("extra_fields", existing_order.extra_fields)
                            ),
                        )

        grouped_orders: dict[str, list[UserOrder]] = {}
        for order in active_orders.values():
            grouped_orders.setdefault(order.user, []).append(order)

        return {
            user: tuple(
                sorted(
                    orders, key=lambda order: (order.coin, order.side, order.limit_px, order.oid)
                )
            )
            for user, orders in grouped_orders.items()
        }

    def compute_resting_order_exposure_bounds(
        self,
        user_state: UserState,
        orders: Iterable[UserOrder],
        *,
        target_coin: str,
    ) -> OrderExposureBounds:
        """Compute bounded notional that can increase exposure for active resting orders.

        This is a consumer-side bound, not an exact reserved-margin formula.
        Reduce-only orders contribute zero. For opposite-side orders against an
        existing position, only the quantity beyond the current position size is
        counted as definitely exposure-increasing.
        """

        orders_by_coin: dict[str, list[UserOrder]] = {}
        for order in orders:
            orders_by_coin.setdefault(order.coin, []).append(order)

        position_size_by_coin: dict[str, float] = {}
        for position in user_state.positions:
            position_size_by_coin[position.coin] = (
                position_size_by_coin.get(position.coin, 0.0) + position.size
            )

        def side_to_sign(side: str) -> int | None:
            if side == "B":
                return 1
            if side == "A":
                return -1
            return None

        def order_notional(order: UserOrder) -> float:
            return order.size * order.limit_px

        def excess_notional_bounds(
            side_orders: list[UserOrder], offset_size: float
        ) -> tuple[float, float]:
            total_size = sum(order.size for order in side_orders)
            excess_size = max(total_size - offset_size, 0.0)
            if excess_size <= 0:
                return 0.0, 0.0

            def accumulate(sorted_orders: list[UserOrder]) -> float:
                remaining = excess_size
                total = 0.0
                for order in sorted_orders:
                    if remaining <= 0:
                        break
                    take = min(remaining, order.size)
                    total += take * order.limit_px
                    remaining -= take
                return total

            min_notional = accumulate(sorted(side_orders, key=lambda order: order.limit_px))
            max_notional = accumulate(
                sorted(side_orders, key=lambda order: order.limit_px, reverse=True)
            )
            return min_notional, max_notional

        total_active_notional = 0.0
        non_reduce_only_notional = 0.0
        exposure_increasing_lower_bound = 0.0
        exposure_increasing_upper_bound = 0.0
        target_coin_notional = 0.0
        off_target_notional = 0.0
        target_coin_exposure_lower_bound = 0.0
        target_coin_exposure_upper_bound = 0.0
        off_target_exposure_lower_bound = 0.0
        off_target_exposure_upper_bound = 0.0
        reduce_only_notional = 0.0
        active_order_count = 0
        non_reduce_only_order_count = 0
        reduce_only_order_count = 0
        per_coin: dict[str, dict[str, float | int | None]] = {}

        for coin, coin_orders in orders_by_coin.items():
            position_size = position_size_by_coin.get(coin, 0.0)
            position_sign = 1 if position_size > 0 else -1 if position_size < 0 else 0
            coin_active_notional = 0.0
            coin_non_reduce_notional = 0.0
            coin_reduce_only_notional = 0.0
            coin_lower_bound = 0.0
            coin_upper_bound = 0.0
            coin_active_order_count = len(coin_orders)
            coin_non_reduce_order_count = 0
            coin_reduce_only_order_count = 0
            opening_side_orders: dict[int, list[UserOrder]] = {1: [], -1: []}

            for order in coin_orders:
                notional = order_notional(order)
                total_active_notional += notional
                coin_active_notional += notional
                active_order_count += 1
                if coin == target_coin:
                    target_coin_notional += notional
                else:
                    off_target_notional += notional

                if order.reduce_only:
                    reduce_only_notional += notional
                    coin_reduce_only_notional += notional
                    reduce_only_order_count += 1
                    coin_reduce_only_order_count += 1
                    continue

                side_sign = side_to_sign(order.side)
                if side_sign is None:
                    continue
                non_reduce_only_notional += notional
                coin_non_reduce_notional += notional
                non_reduce_only_order_count += 1
                coin_non_reduce_order_count += 1
                opening_side_orders[side_sign].append(order)

            if position_sign == 0:
                for side_orders in opening_side_orders.values():
                    side_notional = sum(order_notional(order) for order in side_orders)
                    coin_lower_bound += side_notional
                    coin_upper_bound += side_notional
            else:
                same_side_orders = opening_side_orders[position_sign]
                opposite_side_orders = opening_side_orders[-position_sign]
                same_side_notional = sum(order_notional(order) for order in same_side_orders)
                coin_lower_bound += same_side_notional
                coin_upper_bound += same_side_notional
                opposite_lower, opposite_upper = excess_notional_bounds(
                    opposite_side_orders,
                    abs(position_size),
                )
                coin_lower_bound += opposite_lower
                coin_upper_bound += opposite_upper

            exposure_increasing_lower_bound += coin_lower_bound
            exposure_increasing_upper_bound += coin_upper_bound
            if coin == target_coin:
                target_coin_exposure_lower_bound += coin_lower_bound
                target_coin_exposure_upper_bound += coin_upper_bound
            else:
                off_target_exposure_lower_bound += coin_lower_bound
                off_target_exposure_upper_bound += coin_upper_bound

            per_coin[coin] = {
                "position_size": round(position_size, 10),
                "active_notional": round(coin_active_notional, 6),
                "non_reduce_only_notional": round(coin_non_reduce_notional, 6),
                "reduce_only_notional": round(coin_reduce_only_notional, 6),
                "exposure_increasing_notional_lower_bound": round(coin_lower_bound, 6),
                "exposure_increasing_notional_upper_bound": round(coin_upper_bound, 6),
                "active_order_count": coin_active_order_count,
                "non_reduce_only_order_count": coin_non_reduce_order_count,
                "reduce_only_order_count": coin_reduce_only_order_count,
            }

        return OrderExposureBounds(
            total_active_notional=round(total_active_notional, 6),
            non_reduce_only_notional=round(non_reduce_only_notional, 6),
            exposure_increasing_notional_lower_bound=round(exposure_increasing_lower_bound, 6),
            exposure_increasing_notional_upper_bound=round(exposure_increasing_upper_bound, 6),
            target_coin_notional=round(target_coin_notional, 6),
            off_target_notional=round(off_target_notional, 6),
            target_coin_exposure_increasing_lower_bound=round(target_coin_exposure_lower_bound, 6),
            target_coin_exposure_increasing_upper_bound=round(target_coin_exposure_upper_bound, 6),
            off_target_exposure_increasing_lower_bound=round(off_target_exposure_lower_bound, 6),
            off_target_exposure_increasing_upper_bound=round(off_target_exposure_upper_bound, 6),
            reduce_only_notional=round(reduce_only_notional, 6),
            active_order_count=active_order_count,
            non_reduce_only_order_count=non_reduce_only_order_count,
            reduce_only_order_count=reduce_only_order_count,
            per_coin=freeze_msgpack_value(per_coin),
        )

    def _load_snapshot_filtered(
        self,
        path: Path,
        *,
        target_users: set[str] | None = None,
    ) -> dict:
        with path.open("rb") as f:
            unpacker = msgpack.Unpacker(f, raw=False, strict_map_key=False)
            try:
                top_level_size = unpacker.read_map_header()
            # WORKAROUND: Catching broad Exception and filtering by name is intentional.
            # This is to maintain compatibility with pytest-cov, which appears to alter
            # how msgpack C-extension exceptions are raised or handled, preventing them
            # from being caught by their explicit types (e.g., except msgpack.OutOfData).
            # This behavior was verified during spec-026 finalization.
            # Do not "clean up" this block without validating against the full --cov test suite.
            # See separate investigation ticket in tasks.md.
            except Exception as exc:
                if type(exc).__name__ == "OutOfData" or isinstance(exc, ValueError):
                    raise ValueError(
                        f"Invalid ABCI snapshot format at {path}: empty payload"
                    ) from exc
                raise

            try:
                exchange_value: dict | None = None
                for _ in range(top_level_size):
                    key = unpacker.unpack()
                    if key == "exchange":
                        exchange_value = self._extract_exchange_snapshot(
                            unpacker,
                            target_users=target_users,
                        )
                    else:
                        unpacker.skip()
            # WORKAROUND: See comment above regarding pytest-cov and msgpack exceptions.
            except Exception as exc:
                if type(exc).__name__ in ("OutOfData", "ExtraData") or isinstance(exc, ValueError):
                    raise ValueError(
                        f"Invalid ABCI snapshot format at {path}: truncated or malformed payload"
                    ) from exc
                raise

        if exchange_value is None:
            raise ValueError(f"Invalid ABCI snapshot format at {path}: missing exchange")
        return {"exchange": exchange_value}

    def _extract_exchange_snapshot(
        self,
        unpacker: msgpack.Unpacker,
        *,
        target_users: set[str] | None = None,
    ) -> dict:
        try:
            map_size = unpacker.read_map_header()
        except (msgpack.OutOfData, ValueError) as exc:
            raise ValueError("Invalid ABCI snapshot format: exchange is not a map") from exc

        locus_value: dict | None = None
        for _ in range(map_size):
            key = unpacker.unpack()
            if key == "locus":
                locus_value = self._extract_locus_snapshot(
                    unpacker,
                    target_users=target_users,
                )
            else:
                unpacker.skip()
        return {"locus": locus_value or {}}

    def _extract_locus_snapshot(
        self,
        unpacker: msgpack.Unpacker,
        *,
        target_users: set[str] | None = None,
    ) -> dict:
        try:
            map_size = unpacker.read_map_header()
        except (msgpack.OutOfData, ValueError) as exc:
            raise ValueError("Invalid ABCI snapshot format: locus is not a map") from exc

        cls_value: list[dict] = []
        for _ in range(map_size):
            key = unpacker.unpack()
            if key == "cls":
                try:
                    cls_count = unpacker.read_array_header()
                except (msgpack.OutOfData, ValueError) as exc:
                    raise ValueError("Invalid ABCI snapshot format: cls is not an array") from exc
                if cls_count > 0:
                    cls_value.append(
                        self._extract_cls_snapshot(
                            unpacker,
                            target_users=target_users,
                        )
                    )
                    for _ in range(cls_count - 1):
                        unpacker.skip()
            else:
                unpacker.skip()
        return {"cls": cls_value}

    def _extract_cls_snapshot(
        self,
        unpacker: msgpack.Unpacker,
        *,
        target_users: set[str] | None = None,
    ) -> dict:
        try:
            map_size = unpacker.read_map_header()
        except (msgpack.OutOfData, ValueError) as exc:
            raise ValueError("Invalid ABCI snapshot format: cls[0] is not a map") from exc

        cls0: dict[str, object] = {}
        for _ in range(map_size):
            key = unpacker.unpack()
            if key == "meta":
                value = unpacker.unpack()
                cls0["meta"] = value if isinstance(value, dict) else {}
            elif key == "oracle":
                value = unpacker.unpack()
                cls0["oracle"] = value if isinstance(value, dict) else {}
            elif key == "user_states":
                cls0["user_states"] = self._extract_user_states_snapshot(
                    unpacker,
                    target_users=target_users,
                )
            else:
                unpacker.skip()

        cls0.setdefault("meta", {})
        cls0.setdefault("oracle", {})
        cls0.setdefault("user_states", {"user_to_state": []})
        return cls0

    def _extract_user_states_snapshot(
        self,
        unpacker: msgpack.Unpacker,
        *,
        target_users: set[str] | None = None,
    ) -> dict:
        try:
            map_size = unpacker.read_map_header()
        except (msgpack.OutOfData, ValueError) as exc:
            raise ValueError("Invalid ABCI snapshot format: user_states is not a map") from exc

        matched_pairs: list[list[object]] = []
        remaining_targets = set(target_users) if target_users is not None else None

        def to_user_str(value: object) -> str:
            if isinstance(value, bytes):
                if len(value) == 20:
                    return "0x" + value.hex()
                try:
                    return value.decode()
                except UnicodeDecodeError:
                    return value.hex()
            return str(value)

        for _ in range(map_size):
            key = unpacker.unpack()
            if key != "user_to_state":
                unpacker.skip()
                continue

            try:
                pair_count = unpacker.read_array_header()
            except (msgpack.OutOfData, ValueError) as exc:
                raise ValueError(
                    "Invalid ABCI snapshot format: user_to_state is not an array"
                ) from exc

            for idx in range(pair_count):
                if remaining_targets is not None and not remaining_targets:
                    for _ in range(pair_count - idx):
                        unpacker.skip()
                    break

                try:
                    item_size = unpacker.read_array_header()
                except (msgpack.OutOfData, ValueError):
                    unpacker.skip()
                    continue
                if item_size <= 0:
                    continue

                user = unpacker.unpack()
                user_str = to_user_str(user)
                keep_user = remaining_targets is None or user_str in remaining_targets
                state = None
                if item_size >= 2:
                    if keep_user:
                        state = unpacker.unpack()
                    else:
                        unpacker.skip()
                for _ in range(max(item_size - 2, 0)):
                    unpacker.skip()

                if keep_user and isinstance(state, dict):
                    matched_pairs.append([user, state])
                    if remaining_targets is not None:
                        remaining_targets.discard(user_str)

        return {"user_to_state": matched_pairs}

    def _load_snapshot(self, path: Path) -> dict:
        with path.open("rb") as f:
            unpacker = msgpack.Unpacker(f, raw=False, strict_map_key=False)
            try:
                snapshot = next(unpacker)
            except StopIteration as exc:
                raise ValueError(f"Invalid ABCI snapshot format at {path}: empty payload") from exc

        if not isinstance(snapshot, dict):
            raise ValueError(
                f"Invalid ABCI snapshot format at {path}: top-level object is not a map"
            )

        return snapshot

    def _get_margin_tier(self, notional: float, tiers: list[dict]) -> dict:
        return get_margin_tier(notional, tiers)

    def compute_position_maintenance_margin(
        self,
        position: UserPosition,
        mark_prices: dict[int, float],
        asset_margin_tiers: dict[int, list[dict]],
    ) -> float:
        """Compute the current maintenance margin requirement for a single position."""
        return compute_position_maintenance_margin(position, mark_prices, asset_margin_tiers)

    def solve_liquidation_price(
        self,
        user_state: UserState,
        target_coin: str,
        mark_prices: dict[int, float],
        asset_margin_tiers: dict[int, list[dict]],
        reserved_margin: float = 0.0,
    ) -> float | None:
        """Solve the cross-margin liquidation price for a target coin.

        `user_state.balance` is the raw USD balance component (`u` / `totalRawUsd`), so
        account equity varies with signed position notionals, not with `(P - entry)` PnL.
        """
        target_pos = next((p for p in user_state.positions if p.coin == target_coin), None)
        if not target_pos or target_pos.size == 0:
            return None

        other_signed_notional = 0.0
        other_mmr = 0.0

        for p in user_state.positions:
            if p.coin == target_coin:
                continue

            mark = mark_prices.get(p.asset_idx, p.entry_px)
            other_signed_notional += p.size * mark
            other_mmr += self.compute_position_maintenance_margin(
                p,
                mark_prices,
                asset_margin_tiers,
            )

        balance = user_state.balance
        target_mark = mark_prices.get(target_pos.asset_idx, target_pos.entry_px)
        target_notional = abs(target_pos.size) * target_mark
        target_tiers = asset_margin_tiers.get(target_pos.asset_idx, [])
        target_tier = self._get_margin_tier(target_notional, target_tiers)

        mmr_rate = target_tier["mmr_rate"]
        m_deduct = target_tier["maintenance_deduction"]

        # Cross-margin with raw USD balance:
        # equity(P) = balance + other_signed_notional + target_size * P
        #          = other_mmr + target_mmr(P)
        account_base = balance + other_signed_notional - reserved_margin

        if target_pos.size > 0:
            denom = target_pos.size * (1.0 - mmr_rate)
        else:
            denom = target_pos.size * (1.0 + mmr_rate)
        numerator = other_mmr - m_deduct - account_base

        if abs(denom) < 1e-9:
            return 0.0

        liq_px = numerator / denom
        return max(0.0, liq_px)
