from __future__ import annotations

from datetime import datetime, timezone

from src.liquidationheatmap.hyperliquid.sidecar import (
    ExactnessGap,
    HyperliquidSidecarPrototypeBuilder,
    SidecarBuildRequest,
)


def test_sidecar_build_request_normalizes_symbol_and_timestamp():
    request = SidecarBuildRequest(
        symbol="eth",
        timeframe_days=7,
        analysis_end=datetime(2026, 3, 21, 12, 0, 0),
    )

    assert request.symbol == "ETHUSDT"
    assert request.target_coin == "ETH"
    assert request.analysis_end.tzinfo == timezone.utc
    assert request.window_start == datetime(2026, 3, 14, 12, 0, 0, tzinfo=timezone.utc)



def test_resolve_bin_size_uses_profile_override_for_eth_7d():
    builder = HyperliquidSidecarPrototypeBuilder()
    request = SidecarBuildRequest(
        symbol="ETHUSDT",
        timeframe_days=7,
        analysis_end=datetime(2026, 3, 21, tzinfo=timezone.utc),
    )

    assert builder.resolve_bin_size(request) == 1.65



def test_resolve_bin_size_falls_back_when_profile_missing():
    builder = HyperliquidSidecarPrototypeBuilder()
    request = SidecarBuildRequest(
        symbol="ETH",
        timeframe_days=7,
        analysis_end=datetime(2026, 3, 21, tzinfo=timezone.utc),
        profile_name="missing-profile",
    )

    assert builder.resolve_bin_size(request) == 10.0



def test_build_marks_missing_start_anchor_when_anchor_window_is_too_short(tmp_path):
    filtered_root = tmp_path / "filtered"
    ccxt_root = tmp_path / "catalog"
    abci_root = tmp_path / "abci"

    for dataset in (
        filtered_root / "node_fills_by_block/hourly/20260320",
        filtered_root / "node_order_statuses_by_block/hourly/20260320",
        filtered_root / "node_raw_book_diffs_by_block/hourly/20260320",
        filtered_root / "hip3_oracle_updates_by_block/hourly/20260320",
    ):
        dataset.mkdir(parents=True)
        (dataset / "0.zst").write_text("{}", encoding="utf-8")

    for dataset in ("funding_rate", "open_interest", "ohlcv", "trades"):
        dataset_root = ccxt_root / dataset / "ETHUSDT-PERP.HYPERLIQUID"
        dataset_root.mkdir(parents=True)
        (dataset_root / "2026-03-20.parquet").write_text("", encoding="utf-8")

    for day in ("20260319", "20260320"):
        anchor_day = abci_root / day
        anchor_day.mkdir(parents=True)
        (anchor_day / "930160000.rmp").write_text("", encoding="utf-8")

    builder = HyperliquidSidecarPrototypeBuilder(
        filtered_root=filtered_root,
        abci_root=abci_root,
        ccxt_catalog_root=ccxt_root,
    )
    plan = builder.build(
        SidecarBuildRequest(
            symbol="ETH",
            timeframe_days=7,
            analysis_end=datetime(2026, 3, 21, tzinfo=timezone.utc),
        )
    )

    assert plan.replay_status == "unanchored"
    assert ExactnessGap.MISSING_START_ANCHOR in plan.exactness_gaps
    assert plan.anchor_coverage.start_anchor_candidate is None
    assert plan.anchor_coverage.window_file_count == 2
    assert plan.catalog_sources[0].file_count == 1



def test_build_reports_anchor_candidate_without_overclaiming_snapshot_alignment(tmp_path):
    filtered_root = tmp_path / "filtered"
    ccxt_root = tmp_path / "catalog"
    abci_root = tmp_path / "abci"

    for dataset in (
        filtered_root / "node_fills_by_block/hourly/20260314",
        filtered_root / "node_order_statuses_by_block/hourly/20260314",
        filtered_root / "node_raw_book_diffs_by_block/hourly/20260314",
        filtered_root / "hip3_oracle_updates_by_block/hourly/20260314",
    ):
        dataset.mkdir(parents=True)
        (dataset / "0.zst").write_text("{}", encoding="utf-8")

    for dataset in ("funding_rate", "open_interest", "ohlcv", "trades"):
        dataset_root = ccxt_root / dataset / "ETHUSDT-PERP.HYPERLIQUID"
        dataset_root.mkdir(parents=True)
        (dataset_root / "2026-03-14.parquet").write_text("", encoding="utf-8")

    anchor_day = abci_root / "20260314"
    anchor_day.mkdir(parents=True)
    (anchor_day / "920000000.rmp").write_text("", encoding="utf-8")

    builder = HyperliquidSidecarPrototypeBuilder(
        filtered_root=filtered_root,
        abci_root=abci_root,
        ccxt_catalog_root=ccxt_root,
    )
    plan = builder.build(
        SidecarBuildRequest(
            symbol="ETH",
            timeframe_days=7,
            analysis_end=datetime(2026, 3, 21, tzinfo=timezone.utc),
        )
    )

    assert plan.replay_status == "anchor-candidate-available"
    assert ExactnessGap.MISSING_START_ANCHOR not in plan.exactness_gaps
    assert plan.anchor_coverage.selection_granularity == "day"
    assert plan.anchor_coverage.start_anchor_candidate == anchor_day / "920000000.rmp"
