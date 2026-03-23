"""Minimal Hyperliquid sidecar prototype scaffolding.

This first slice does not attempt account-level replay yet. It builds the
prototype context needed for the first `ETH 7d` sidecar iteration:

- bin-size resolution using the existing profile registry
- local source coverage discovery for filtered, ABCI, and ccxt catalog roots
- explicit exactness-gap reporting so the prototype cannot overclaim parity
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

import msgpack

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
    extra_fields: Mapping[str, object] = field(
        default_factory=lambda: MappingProxyType({})
    )


@dataclass(frozen=True)
class UserState:
    """Reconstructed per-user state."""

    user: str
    balance: float
    positions: tuple[UserPosition, ...]
    balance_state_s: float | None = None
    balance_state_r: float | None = None
    extra_fields: Mapping[str, object] = field(
        default_factory=lambda: MappingProxyType({})
    )

    @property
    def has_active_positions(self) -> bool:
        return any(p.size != 0 for p in self.positions)


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


def freeze_msgpack_value(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: freeze_msgpack_value(val) for key, val in value.items()})
    if isinstance(value, list):
        return tuple(freeze_msgpack_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(freeze_msgpack_value(item) for item in value)
    return value


class SidecarPositionReconstructor:
    """Engine for account-level state reconstruction from Hyperliquid sources."""

    def load_abci_anchor(self, path: Path, *, target_coin: str | None = None) -> SidecarState:
        """Load and decode a MessagePack ABCI snapshot."""
        snapshot = self._load_snapshot(path)

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

        # Extract MMR rates from margin tables
        margin_tables_raw = meta.get("marginTableIdToMarginTable", [])
        table_to_tiers: dict[int, list[dict]] = {}
        for item in margin_tables_raw:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            table_id, table_data = item[0], item[1]
            tiers_raw = table_data.get("margin_tiers", [])

            parsed_tiers = []
            for t in tiers_raw:
                # MMR is exactly 1 / (2 * max_leverage) based on Hyperliquid spec
                # maintenance_deduction and lower_bound are scaled by 1e6
                max_lev = float(t.get("max_leverage", 50))
                parsed_tiers.append({
                    "lower_bound": float(t.get("lower_bound", 0)) / 1e6,
                    "mmr_rate": 1.0 / (2.0 * max_lev) if max_lev > 0 else 0.01,
                    "maintenance_deduction": float(t.get("maintenance_deduction", 0)) / 1e6,
                })

            # Sort tiers descending to easily find active tier
            parsed_tiers.sort(key=lambda x: x["lower_bound"], reverse=True)
            table_to_tiers[table_id] = parsed_tiers

        asset_margin_tiers: dict[int, list[dict]] = {}
        for idx, m in asset_meta.items():
            asset_margin_tiers[idx] = table_to_tiers.get(
                m["marginTableId"],
                [{"lower_bound": 0, "mmr_rate": 0.01, "maintenance_deduction": 0}],
            )

        # Extract Oracle prices
        pxs_raw = cls0.get("oracle", {}).get("pxs", [])
        mark_prices: dict[int, float] = {}
        for idx, oracles in enumerate(pxs_raw):
            if oracles and isinstance(oracles, list):
                raw_px = float(oracles[0].get("px", 0))
                sz_dec = asset_meta.get(idx, {}).get("szDecimals", 0)
                # Oracle stores: actual_price * 10^(6 - szDecimals)
                mark_prices[idx] = raw_px / (10 ** (6 - sz_dec))

        user_states_wrapper = cls0.get("user_states", {})
        user_to_state = user_states_wrapper.get("user_to_state", [])

        USDC_SCALE = 1e6
        reconstructed_users: dict[str, UserState] = {}

        def to_user_str(u) -> str:
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

            positions_raw = state.get("p", {}).get("p", [])
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
                funding_raw = p.get("f", {}) if isinstance(p.get("f", {}), dict) else {}
                position_extras = {
                    key: value
                    for key, value in p.items()
                    if key not in {"s", "e", "M", "l", "f"}
                }

                pos = UserPosition(
                    coin=m["name"],
                    asset_idx=asset_idx,
                    size=size_scaled,
                    entry_px=entry_px,
                    margin=float(p.get("M", 0)),
                    leverage=float(p.get("l", {}).get("C", 1.0)),
                    cum_funding=float(funding_raw.get("a", 0)) / USDC_SCALE,
                    cum_funding_open=(
                        float(funding_raw.get("o", 0)) / USDC_SCALE
                        if "o" in funding_raw
                        else None
                    ),
                    cum_funding_closed=(
                        float(funding_raw.get("c", 0)) / USDC_SCALE
                        if "c" in funding_raw
                        else None
                    ),
                    extra_fields=freeze_msgpack_value(position_extras),
                )
                positions.append(pos)

            if target_coin and not has_target:
                continue

            # Balance = (u - sum(e)) / USDC_SCALE
            # u: total account value numerator (deposits + realized + funding + position costs)
            # e: total cost locked per position (|size| * entry * USDC_SCALE)
            # Subtracting sum(e) gives the net USDC balance for equity calculation
            u_raw = float(state.get("u", 0))
            sum_e_raw = sum(float(p.get("e", 0)) for _, p in positions_raw if isinstance(p, dict))
            balance_raw = u_raw - sum_e_raw
            s_state = state.get("S", {}) if isinstance(state.get("S", {}), dict) else {}
            state_extras = {
                key: value
                for key, value in state.items()
                if key not in {"u", "p", "S"}
            }
            user_str = to_user_str(user)
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

    def _load_snapshot(self, path: Path) -> dict:
        with path.open("rb") as f:
            unpacker = msgpack.Unpacker(f, raw=False, strict_map_key=False)
            try:
                snapshot = next(unpacker)
            except StopIteration as exc:
                raise ValueError(f"Invalid ABCI snapshot format at {path}: empty payload") from exc

        if not isinstance(snapshot, dict):
            raise ValueError(f"Invalid ABCI snapshot format at {path}: top-level object is not a map")

        return snapshot

    def _get_margin_tier(self, notional: float, tiers: list[dict]) -> dict:
        for t in tiers:
            if notional >= t["lower_bound"]:
                return t
        return tiers[-1] if tiers else {"lower_bound": 0, "mmr_rate": 0.01, "maintenance_deduction": 0}

    def compute_position_maintenance_margin(
        self,
        position: UserPosition,
        mark_prices: dict[int, float],
        asset_margin_tiers: dict[int, list[dict]],
    ) -> float:
        """Compute the current maintenance margin requirement for a single position."""
        mark = mark_prices.get(position.asset_idx, position.entry_px)
        notional = abs(position.size) * mark
        tiers = asset_margin_tiers.get(position.asset_idx, [])
        tier = self._get_margin_tier(notional, tiers)
        requirement = notional * tier["mmr_rate"] - tier["maintenance_deduction"]
        return max(0.0, requirement)

    def solve_liquidation_price(
        self,
        user_state: UserState,
        target_coin: str,
        mark_prices: dict[int, float],
        asset_margin_tiers: dict[int, list[dict]],
    ) -> float | None:
        """Solve the cross-margin liquidation price for a target coin."""
        target_pos = next((p for p in user_state.positions if p.coin == target_coin), None)
        if not target_pos or target_pos.size == 0:
            return None

        other_pnl = 0.0
        other_mmr = 0.0

        for p in user_state.positions:
            if p.coin == target_coin:
                continue

            mark = mark_prices.get(p.asset_idx, p.entry_px)
            other_pnl += p.size * (mark - p.entry_px)
            other_mmr += self.compute_position_maintenance_margin(
                p,
                mark_prices,
                asset_margin_tiers,
            )

        # balance already reflects all past funding (stored as (u - sum(e)) / scale)
        balance = user_state.balance
        target_mark = mark_prices.get(target_pos.asset_idx, target_pos.entry_px)
        target_notional = abs(target_pos.size) * target_mark
        target_tiers = asset_margin_tiers.get(target_pos.asset_idx, [])
        target_tier = self._get_margin_tier(target_notional, target_tiers)

        mmr_rate = target_tier["mmr_rate"]
        m_deduct = target_tier["maintenance_deduction"]

        # Cross-margin: equity = balance + other_pnl + target_size*(P - entry) = total_mmr
        account_base = balance + other_pnl

        if target_pos.size > 0:
            denom = target_pos.size * (1.0 - mmr_rate)
            numerator = other_mmr - m_deduct + (target_pos.size * target_pos.entry_px) - account_base
        else:
            denom = target_pos.size * (1.0 + mmr_rate)
            numerator = other_mmr - m_deduct + (target_pos.size * target_pos.entry_px) - account_base

        if abs(denom) < 1e-9:
            return 0.0

        liq_px = numerator / denom
        return max(0.0, liq_px)
