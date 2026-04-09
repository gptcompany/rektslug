"""Spec-023: ETH/USDT structural validation for the public liqmap builder.

Validates that the public builder produces structurally correct output for
ETHUSDT across 1d and 1w timeframes, mirroring the BTC validation done in
spec-016/017/022.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.liquidationheatmap.api import public_liqmap
from src.liquidationheatmap.api.main import app
from src.liquidationheatmap.api.public_liqmap import (
    _BuilderMetadata,
    _STEP_TABLE,
    CoinankPublicMapResponse,
)

_CURRENT_PRICES = {
    "BTCUSDT": Decimal("60000"),
    "ETHUSDT": Decimal("2000"),
}
_TIMEFRAME_OFFSETS = {
    "1d": [1, 2, 3, 4, 5],
    "1w": [2, 4, 6, 8, 10],
}
_SEEDED_LEVERAGES = (25, 50, 100)
_FIXED_TIMESTAMP = datetime(2026, 3, 19, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def client():
    return TestClient(app)


def _metadata_for(symbol: str, timeframe: str) -> _BuilderMetadata:
    return _BuilderMetadata(
        current_price=_CURRENT_PRICES[symbol],
        last_data_timestamp=_FIXED_TIMESTAMP,
        is_stale_real_data=False,
        timeframe_days=public_liqmap.SUPPORTED_PUBLIC_LIQMAP_TIMEFRAMES[timeframe],
        step=_STEP_TABLE[(symbol, timeframe)],
    )


def _synthetic_builder_rows(symbol: str, timeframe: str) -> list[dict]:
    current_price = float(_CURRENT_PRICES[symbol])
    step = float(_STEP_TABLE[(symbol, timeframe)])
    offsets = _TIMEFRAME_OFFSETS[timeframe]
    rows: list[dict] = []

    for side, direction, base_volume in (
        ("buy", -1, 120000.0),
        ("sell", 1, 110000.0),
    ):
        for offset_idx, offset in enumerate(offsets, start=1):
            snapped_price = round(current_price + (direction * step * offset), 2)
            for leverage_idx, leverage in enumerate(_SEEDED_LEVERAGES, start=1):
                rows.append(
                    {
                        "side": side,
                        "liq_price": snapped_price,
                        "leverage": leverage,
                        "volume": base_volume + (offset_idx * 5000.0) + (leverage_idx * 1000.0),
                    }
                )

    return rows


def _fetch_public_map(client: TestClient, *, symbol: str, timeframe: str) -> dict:
    response = client.get(
        "/liquidations/coinank-public-map",
        params={"symbol": symbol, "timeframe": timeframe},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _normalize_shape(values: list[float]) -> list[float]:
    if not values:
        return []
    peak = max(values)
    if peak <= 0:
        return [0.0 for _ in values]
    return [value / peak for value in values]


def _relative_delta(candidate: float, baseline: float) -> float:
    if baseline == 0:
        return 0.0 if candidate == 0 else float("inf")
    return abs(candidate - baseline) / abs(baseline)


def _assert_within_tolerance(
    *,
    metric_name: str,
    candidate: float,
    baseline: float,
    tolerance: float = 0.20,
) -> None:
    delta = _relative_delta(candidate, baseline)
    assert delta <= tolerance, (
        f"{metric_name} delta {delta:.2%} exceeds {tolerance:.0%}: "
        f"candidate={candidate}, baseline={baseline}"
    )


def _assert_shape_within_tolerance(
    *,
    metric_name: str,
    candidate: list[float],
    baseline: list[float],
    tolerance: float = 0.20,
) -> None:
    assert len(candidate) == len(baseline), (
        f"{metric_name} point count mismatch: candidate={len(candidate)} baseline={len(baseline)}"
    )
    for idx, (candidate_value, baseline_value) in enumerate(zip(candidate, baseline, strict=True)):
        delta = _relative_delta(candidate_value, baseline_value)
        assert delta <= tolerance, (
            f"{metric_name}[{idx}] delta {delta:.2%} exceeds {tolerance:.0%}: "
            f"candidate={candidate_value}, baseline={baseline_value}"
        )


@pytest.fixture
def public_builder_env(monkeypatch):
    def _fake_load_public_liqmap_metadata(*, symbol: str, timeframe: str, step: Decimal):
        expected = _STEP_TABLE[(symbol, timeframe)]
        assert step == expected
        return _metadata_for(symbol, timeframe)

    class _FakeDuckDBService:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def calculate_liquidations_oi_based(self, **kwargs):
            timeframe = "1d" if kwargs["lookback_days"] == 1 else "1w"
            return pd.DataFrame(_synthetic_builder_rows(kwargs["symbol"], timeframe))

    monkeypatch.setattr(public_liqmap, "_load_public_liqmap_metadata", _fake_load_public_liqmap_metadata)
    monkeypatch.setattr(public_liqmap, "DuckDBService", _FakeDuckDBService)
    monkeypatch.setattr(
        public_liqmap.snapshot_reader,
        "get_latest_available_snapshot_ts",
        lambda *_args, **_kwargs: None,
    )


# ---------------------------------------------------------------------------
# T001/T002: Schema compliance for ETHUSDT 1d/1w
# ---------------------------------------------------------------------------


class TestEthSchemaCompliance:
    """T001-T002: Response schema matches CoinankPublicMapResponse."""

    @pytest.mark.parametrize("timeframe", ["1d", "1w"])
    def test_eth_endpoint_returns_valid_schema(self, client, public_builder_env, timeframe):
        data = _fetch_public_map(client, symbol="ETHUSDT", timeframe=timeframe)

        parsed = CoinankPublicMapResponse(**data)
        assert parsed.symbol == "ETHUSDT"
        assert parsed.timeframe == timeframe
        assert parsed.source == "coinank-public-builder"
        assert parsed.schema_version == "1.0"


# ---------------------------------------------------------------------------
# T003: Grid step verification (distinct from BTC)
# ---------------------------------------------------------------------------


class TestEthGridStep:
    """T003: ETH grid steps are correct and distinct from BTC."""

    def test_eth_1d_grid_step_is_0_5(self, client, public_builder_env):
        data = _fetch_public_map(client, symbol="ETHUSDT", timeframe="1d")
        assert data["grid"]["step"] == 0.5
        assert data["grid"]["step"] != float(_STEP_TABLE[("BTCUSDT", "1d")])

    def test_eth_1w_grid_step_is_2_0(self, client, public_builder_env):
        data = _fetch_public_map(client, symbol="ETHUSDT", timeframe="1w")
        assert data["grid"]["step"] == 2.0
        assert data["grid"]["step"] != float(_STEP_TABLE[("BTCUSDT", "1w")])


# ---------------------------------------------------------------------------
# T004: Bucket count threshold
# ---------------------------------------------------------------------------


class TestEthBucketCounts:
    """T004: ETH bucket counts >= 15 long + 15 short."""

    @pytest.mark.parametrize("timeframe", ["1d", "1w"])
    def test_eth_has_sufficient_buckets(self, client, public_builder_env, timeframe):
        data = _fetch_public_map(client, symbol="ETHUSDT", timeframe=timeframe)

        assert len(data["long_buckets"]) >= 15, (
            f"ETH {timeframe} long buckets: {len(data['long_buckets'])} < 15"
        )
        assert len(data["short_buckets"]) >= 15, (
            f"ETH {timeframe} short buckets: {len(data['short_buckets'])} < 15"
        )


# ---------------------------------------------------------------------------
# T005: Cumulative curves are monotonic and reach grid boundaries
# ---------------------------------------------------------------------------


class TestEthCumulativeCurves:
    """T005: Cumulative curves are monotonic and terminate correctly."""

    @pytest.mark.parametrize("timeframe", ["1d", "1w"])
    def test_cumulative_long_is_monotonic_decreasing_toward_price(
        self, client, public_builder_env, timeframe
    ):
        data = _fetch_public_map(client, symbol="ETHUSDT", timeframe=timeframe)
        values = [point["value"] for point in data["cumulative_long"]]

        assert len(values) >= 2
        assert values[-1] == 0.0, "Cumulative long must end at 0 at current price"

        nonzero_values = [value for value in values if value > 0]
        for idx in range(1, len(nonzero_values)):
            assert nonzero_values[idx] <= nonzero_values[idx - 1], (
                "Cumulative long not monotonic at "
                f"index {idx}: {nonzero_values[idx]} > {nonzero_values[idx - 1]}"
            )

    @pytest.mark.parametrize("timeframe", ["1d", "1w"])
    def test_cumulative_short_is_monotonic_increasing_from_price(
        self, client, public_builder_env, timeframe
    ):
        data = _fetch_public_map(client, symbol="ETHUSDT", timeframe=timeframe)
        values = [point["value"] for point in data["cumulative_short"]]

        assert len(values) >= 2
        assert values[0] == 0.0, "Cumulative short must start at 0 at current price"

        for idx in range(1, len(values)):
            assert values[idx] >= values[idx - 1], (
                f"Cumulative short not monotonic at index {idx}: "
                f"{values[idx]} < {values[idx - 1]}"
            )


# ---------------------------------------------------------------------------
# T006: Range envelope 1d vs 1w distinction
# ---------------------------------------------------------------------------


class TestEthRangeEnvelope:
    """T006: ETH 1d range is narrower than 1w range."""

    def test_1w_range_is_wider_than_1d(self, client, public_builder_env):
        data_1d = _fetch_public_map(client, symbol="ETHUSDT", timeframe="1d")
        data_1w = _fetch_public_map(client, symbol="ETHUSDT", timeframe="1w")

        range_1d = data_1d["grid"]["max_price"] - data_1d["grid"]["min_price"]
        range_1w = data_1w["grid"]["max_price"] - data_1w["grid"]["min_price"]

        assert range_1w > range_1d, (
            f"1w range ({range_1w:.2f}) should be wider than 1d range ({range_1d:.2f})"
        )


# ---------------------------------------------------------------------------
# T007: Data freshness gate
# ---------------------------------------------------------------------------


class TestEthDataFreshness:
    """T007: is_stale_real_data must be false for valid validation."""

    @pytest.mark.parametrize("timeframe", ["1d", "1w"])
    def test_fresh_data_flag(self, client, public_builder_env, timeframe):
        data = _fetch_public_map(client, symbol="ETHUSDT", timeframe=timeframe)
        assert data["is_stale_real_data"] is False, (
            f"ETH {timeframe} data is stale — run gap-fill before validation"
        )


# ---------------------------------------------------------------------------
# T019: ETH vs BTC structural comparison (SC-002: within 20% tolerance)
# ---------------------------------------------------------------------------


class TestEthVsBtcStructuralComparison:
    """T019: ETH structural metrics within 20% tolerance of BTC equivalents."""

    def _get_structural_metrics(self, data: dict) -> dict:
        grid = data["grid"]
        current_price = data["current_price"]
        return {
            "long_bucket_count": float(len(data["long_buckets"])),
            "short_bucket_count": float(len(data["short_buckets"])),
            "normalized_range_span": (grid["max_price"] - grid["min_price"]) / current_price,
            "cumulative_long_points": float(len(data["cumulative_long"])),
            "cumulative_short_points": float(len(data["cumulative_short"])),
            "cumulative_long_shape": _normalize_shape(
                [point["value"] for point in data["cumulative_long"][:-1]]
            ),
            "cumulative_short_shape": _normalize_shape(
                [point["value"] for point in data["cumulative_short"][1:]]
            ),
        }

    @pytest.mark.parametrize("timeframe", ["1d", "1w"])
    def test_eth_metrics_within_20_percent_of_btc(self, client, public_builder_env, timeframe):
        btc_data = _fetch_public_map(client, symbol="BTCUSDT", timeframe=timeframe)
        eth_data = _fetch_public_map(client, symbol="ETHUSDT", timeframe=timeframe)

        btc_metrics = self._get_structural_metrics(btc_data)
        eth_metrics = self._get_structural_metrics(eth_data)

        for metric_name in (
            "long_bucket_count",
            "short_bucket_count",
            "normalized_range_span",
            "cumulative_long_points",
            "cumulative_short_points",
        ):
            _assert_within_tolerance(
                metric_name=metric_name,
                candidate=eth_metrics[metric_name],
                baseline=btc_metrics[metric_name],
            )

        _assert_shape_within_tolerance(
            metric_name="cumulative_long_shape",
            candidate=eth_metrics["cumulative_long_shape"],
            baseline=btc_metrics["cumulative_long_shape"],
        )
        _assert_shape_within_tolerance(
            metric_name="cumulative_short_shape",
            candidate=eth_metrics["cumulative_short_shape"],
            baseline=btc_metrics["cumulative_short_shape"],
        )
