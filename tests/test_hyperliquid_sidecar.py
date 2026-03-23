from __future__ import annotations

from datetime import datetime, timezone

import msgpack

from src.liquidationheatmap.hyperliquid.sidecar import (
    ExactnessGap,
    HyperliquidSidecarPrototypeBuilder,
    SidecarBuildRequest,
    SidecarPositionReconstructor,
    UserPosition,
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


def test_load_abci_anchor_extracts_user_state(tmp_path):
    anchor_file = tmp_path / "test.rmp"

    # Mock snapshot structure: user_to_state and positions are lists of pairs
    # metadata included for scaling, marks, tiered maintenance margin, and
    # additional state fields we want to retain on the consumer side.
    snapshot = {
        "exchange": {
            "locus": {
                "cls": [
                    {
                        "meta": {
                            "universe": [
                                {"name": "BTC", "szDecimals": 5, "marginTableId": 10},
                                {"name": "ETH", "szDecimals": 4, "marginTableId": 20},
                                {"name": "ATOM", "szDecimals": 2, "marginTableId": 30},
                                {"name": "HYPE", "szDecimals": 1, "marginTableId": 40},
                                {"name": "SOL", "szDecimals": 2, "marginTableId": 50},
                            ],
                            "marginTableIdToMarginTable": [
                                [10, {"margin_tiers": [{"lower_bound": 0, "max_leverage": 50, "maintenance_deduction": 0}]}],
                                [20, {"margin_tiers": [{"lower_bound": 0, "max_leverage": 20, "maintenance_deduction": 5000000}]}],
                                [50, {"margin_tiers": [{"lower_bound": 0, "max_leverage": 10, "maintenance_deduction": 0}]}],
                            ],
                        },
                        "oracle": {
                            "pxs": [
                                [{"px": 600000}],
                                [{"px": 250000}],
                                [],
                                [],
                                [{"px": 1234500}],
                            ]
                        },
                        "user_states": {
                            "user_to_state": [
                                [
                                    b"\x01" * 20,
                                    {
                                        "u": 16444084712.0,
                                        "S": {"s": 5444084712.0, "r": 5444084712.0},
                                        "D": [["2026-03-20", {"a": 123456.0, "c": 120000.0}]],
                                        "p": {
                                            "p": [
                                                [1, {"s": 25000, "e": 5000000000, "M": 50.0, "l": {"C": 20.0}, "f": {"a": 100000.0, "o": 120000.0, "c": 110000.0}, "x": {"flag": True}}],
                                                [0, {"s": 10000, "e": 6000000000, "M": 100.0, "l": {"C": 50.0}, "f": {"a": 500000.0}}],
                                            ]
                                        },
                                    },
                                ],
                                [
                                    "0xuser2_string",
                                    {
                                        "u": 510000000.0,
                                        "S": {"s": 500000000.0, "r": 500000000.0},
                                        "p": {
                                            "p": [
                                                [4, {"s": 10000, "e": 10000000, "M": 20.0, "l": {"C": 10.0}, "f": {"a": 0.0}}]
                                            ]
                                        },
                                    },
                                ],
                            ]
                        },
                    }
                ]
            }
        }
    }

    anchor_file.write_bytes(msgpack.packb(snapshot))

    reconstructor = SidecarPositionReconstructor()

    # Test filtering for ETH (index 1)
    state = reconstructor.load_abci_anchor(anchor_file, target_coin="ETH")

    assert len(state.users) == 1
    assert state.mark_prices[0] == 60000.0
    assert state.mark_prices[1] == 2500.0
    assert state.asset_margin_tiers[1][0]["mmr_rate"] == 0.025
    assert state.asset_margin_tiers[1][0]["maintenance_deduction"] == 5.0

    expected_user = "0x" + ("01" * 20)
    assert expected_user in state.users
    user1 = state.users[expected_user]
    assert user1.balance == 5444.084712
    assert user1.balance_state_s == 5444.084712
    assert user1.balance_state_r == 5444.084712
    assert user1.extra_fields["D"][0][0] == "2026-03-20"
    assert user1.extra_fields["D"][0][1]["a"] == 123456.0
    assert len(user1.positions) == 2

    eth_pos = next(p for p in user1.positions if p.coin == "ETH")
    assert eth_pos.size == 2.5
    assert eth_pos.entry_px == 2000.0
    assert eth_pos.leverage == 20.0
    assert eth_pos.cum_funding == 0.1
    assert eth_pos.cum_funding_open == 0.12
    assert eth_pos.cum_funding_closed == 0.11
    assert eth_pos.extra_fields["x"]["flag"] is True

    # Test filtering for SOL (index 4)
    state_sol = reconstructor.load_abci_anchor(anchor_file, target_coin="SOL")
    assert len(state_sol.users) == 1
    assert "0xuser2_string" in state_sol.users
    user2 = state_sol.users["0xuser2_string"]
    assert user2.positions[0].size == 100.0
    assert user2.balance_state_s == 500.0
    assert user2.balance_state_r == 500.0


def test_load_abci_anchor_rejects_empty_payload(tmp_path):
    anchor_file = tmp_path / "empty.rmp"
    anchor_file.write_bytes(b"")

    reconstructor = SidecarPositionReconstructor()

    try:
        reconstructor.load_abci_anchor(anchor_file)
    except ValueError as exc:
        assert "empty payload" in str(exc)
    else:
        raise AssertionError("Expected empty payload to raise ValueError")


def test_compute_position_maintenance_margin_uses_mark_and_deduction():
    reconstructor = SidecarPositionReconstructor()
    position = UserPosition(
        coin="ETH",
        asset_idx=1,
        size=2.5,
        entry_px=2000.0,
        leverage=20.0,
        cum_funding=0.1,
        margin=50.0,
    )

    mmr = reconstructor.compute_position_maintenance_margin(
        position,
        mark_prices={1: 2500.0},
        asset_margin_tiers={1: [{"lower_bound": 0.0, "mmr_rate": 0.025, "maintenance_deduction": 5.0}]},
    )

    assert mmr == 151.25
