from __future__ import annotations

from datetime import datetime, timezone

import msgpack

from src.liquidationheatmap.hyperliquid.sidecar import (
    ExactnessGap,
    HyperliquidSidecarPrototypeBuilder,
    SidecarBuildRequest,
    SidecarPositionReconstructor,
    UserOrder,
    UserPosition,
    UserState,
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



def test_load_abci_anchor_filters_target_users(tmp_path):
    anchor_file = tmp_path / "users_filter.rmp"
    snapshot = {
        "exchange": {
            "locus": {
                "cls": [
                    {
                        "meta": {
                            "universe": [
                                {"name": "ETH", "szDecimals": 4, "marginTableId": 20},
                            ],
                            "marginTableIdToMarginTable": [
                                [20, {"margin_tiers": [{"lower_bound": 0, "max_leverage": 20, "maintenance_deduction": 0}]}],
                            ],
                        },
                        "oracle": {"pxs": [[{"px": 250000}]]},
                        "user_states": {
                            "user_to_state": [
                                ["0xkeep", {"u": 300000000.0, "S": {"s": 100000000.0}, "p": {"p": [[0, {"s": 10000, "e": 200000000.0, "M": 25.0, "l": {"C": 20.0}, "f": {"a": 0.0}}]]}}],
                                ["0xdrop", {"u": 400000000.0, "S": {"s": 150000000.0}, "p": {"p": [[0, {"s": 20000, "e": 400000000.0, "M": 50.0, "l": {"C": 20.0}, "f": {"a": 0.0}}]]}}],
                            ]
                        },
                    }
                ]
            }
        }
    }
    anchor_file.write_bytes(msgpack.packb(snapshot))

    reconstructor = SidecarPositionReconstructor()
    state = reconstructor.load_abci_anchor(
        anchor_file,
        target_coin="ETH",
        target_users={"0xkeep"},
    )

    assert set(state.users) == {"0xkeep"}


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



def test_load_abci_anchor_skips_malformed_positions_and_defaults_cross_leverage(tmp_path):
    anchor_file = tmp_path / "malformed.rmp"
    snapshot = {
        "exchange": {
            "locus": {
                "cls": [
                    {
                        "meta": {
                            "universe": [
                                {"name": "ETH", "szDecimals": 4, "marginTableId": 20},
                            ],
                            "marginTableIdToMarginTable": [
                                [20, {"margin_tiers": [{"lower_bound": 0, "max_leverage": 20, "maintenance_deduction": 0}]}],
                            ],
                        },
                        "oracle": {"pxs": [[{"px": 250000}]]},
                        "user_states": {
                            "user_to_state": [
                                [
                                    "0xmalformed",
                                    {
                                        "u": 300000000.0,
                                        "S": {"s": 100000000.0, "r": 100000000.0},
                                        "p": {
                                            "p": [
                                                "bad-entry",
                                                [0, {"s": 10000, "e": 200000000.0, "M": 25.0, "l": None, "f": {"a": 0.0}}],
                                            ]
                                        },
                                    },
                                ]
                            ]
                        },
                    }
                ]
            }
        }
    }
    anchor_file.write_bytes(msgpack.packb(snapshot))

    reconstructor = SidecarPositionReconstructor()
    state = reconstructor.load_abci_anchor(anchor_file, target_coin="ETH")

    user = state.users["0xmalformed"]
    assert user.balance == 100.0
    assert len(user.positions) == 1
    assert user.positions[0].leverage == 1.0
    assert user.positions[0].entry_px == 200.0



def test_reconstruct_resting_orders_from_blocks_tracks_active_orders_and_filters():
    reconstructor = SidecarPositionReconstructor()
    order_status_blocks = [
        {
            "block_number": 100,
            "events": [
                {
                    "user": "0xkeep",
                    "status": "open",
                    "hash": "0xabc",
                    "builder": None,
                    "order": {
                        "coin": "ETH",
                        "side": "B",
                        "limitPx": "2000.0",
                        "sz": "1.5",
                        "origSz": "1.5",
                        "oid": 11,
                        "timestamp": 1234,
                        "triggerCondition": "N/A",
                        "isTrigger": False,
                        "triggerPx": "0.0",
                        "children": [],
                        "isPositionTpsl": False,
                        "reduceOnly": False,
                        "orderType": "Limit",
                        "tif": "Gtc",
                        "cloid": "0xcloid1",
                    },
                },
                {
                    "user": "0xdrop",
                    "status": "perpMarginRejected",
                    "hash": None,
                    "builder": None,
                    "order": {
                        "coin": "ETH",
                        "side": "A",
                        "limitPx": "2100.0",
                        "sz": "2.0",
                        "origSz": "2.0",
                        "oid": 22,
                        "timestamp": 1235,
                        "triggerCondition": "N/A",
                        "isTrigger": False,
                        "triggerPx": "0.0",
                        "children": [],
                        "isPositionTpsl": False,
                        "reduceOnly": False,
                        "orderType": "Limit",
                        "tif": "Ioc",
                        "cloid": None,
                    },
                },
            ],
        },
        {
            "block_number": 101,
            "events": [
                {
                    "user": "0xremove",
                    "status": "open",
                    "hash": "0xdef",
                    "builder": None,
                    "order": {
                        "coin": "ETH",
                        "side": "A",
                        "limitPx": "2050.0",
                        "sz": "0.8",
                        "origSz": "0.8",
                        "oid": 33,
                        "timestamp": 2234,
                        "triggerCondition": "N/A",
                        "isTrigger": False,
                        "triggerPx": "0.0",
                        "children": [],
                        "isPositionTpsl": False,
                        "reduceOnly": True,
                        "orderType": "Limit",
                        "tif": "Alo",
                        "cloid": "0xcloid2",
                    },
                },
                {
                    "user": "0xremove",
                    "status": "canceled",
                    "hash": None,
                    "builder": None,
                    "order": {
                        "coin": "ETH",
                        "side": "A",
                        "limitPx": "2050.0",
                        "sz": "0.8",
                        "origSz": "0.8",
                        "oid": 33,
                        "timestamp": 2235,
                        "triggerCondition": "N/A",
                        "isTrigger": False,
                        "triggerPx": "0.0",
                        "children": [],
                        "isPositionTpsl": False,
                        "reduceOnly": True,
                        "orderType": "Limit",
                        "tif": "Alo",
                        "cloid": "0xcloid2",
                    },
                },
            ],
        },
    ]
    raw_book_diff_blocks = [
        {
            "block_number": 100,
            "events": [
                {"user": "0xkeep", "oid": 11, "coin": "ETH", "side": "B", "px": "2000.0", "raw_book_diff": {"new": {"sz": "1.5"}}},
                {"user": "0xdrop", "oid": 22, "coin": "ETH", "side": "A", "px": "2100.0", "raw_book_diff": {"new": {"sz": "2.0"}}},
            ],
        },
        {
            "block_number": 101,
            "events": [
                {"user": "0xkeep", "oid": 11, "coin": "ETH", "side": "B", "px": "2000.0", "raw_book_diff": {"update": {"origSz": "1.5", "newSz": "1.1"}}},
                {"user": "0xremove", "oid": 33, "coin": "ETH", "side": "A", "px": "2050.0", "raw_book_diff": {"new": {"sz": "0.8"}}},
                {"user": "0xremove", "oid": 33, "coin": "ETH", "side": "A", "px": "2050.0", "raw_book_diff": "remove"},
            ],
        },
    ]

    orders = reconstructor.reconstruct_resting_orders_from_blocks(
        order_status_blocks=order_status_blocks,
        raw_book_diff_blocks=raw_book_diff_blocks,
        target_users={"0xkeep", "0xremove"},
        target_coin="ETH",
    )

    assert set(orders) == {"0xkeep"}
    active_order = orders["0xkeep"][0]
    assert active_order.oid == 11
    assert active_order.size == 1.1
    assert active_order.orig_size == 1.5
    assert active_order.limit_px == 2000.0
    assert active_order.tif == "Gtc"
    assert active_order.status == "open"
    assert active_order.extra_fields["block_number"] == 101



def test_collect_active_order_users_from_blocks_tracks_final_active_users():
    reconstructor = SidecarPositionReconstructor()
    order_status_blocks = [
        {
            "block_number": 100,
            "events": [
                {"user": "0xkeep", "status": "open", "order": {"coin": "ETH", "oid": 11}},
                {"user": "0xdrop", "status": "canceled", "order": {"coin": "ETH", "oid": 22}},
            ],
        },
    ]
    raw_book_diff_blocks = [
        {
            "block_number": 100,
            "events": [
                {"user": "0xkeep", "oid": 11, "coin": "ETH", "raw_book_diff": {"new": {"sz": "1.0"}}},
                {"user": "0xdrop", "oid": 22, "coin": "ETH", "raw_book_diff": {"new": {"sz": "1.0"}}},
                {"user": "0xdrop", "oid": 22, "coin": "ETH", "raw_book_diff": "remove"},
                {"user": "0xofftarget", "oid": 33, "coin": "BTC", "raw_book_diff": {"new": {"sz": "1.0"}}},
            ],
        },
    ]

    users = reconstructor.collect_active_order_users_from_blocks(
        order_status_blocks=order_status_blocks,
        raw_book_diff_blocks=raw_book_diff_blocks,
        target_coin="ETH",
    )

    assert users == {"0xkeep"}



def test_compute_resting_order_exposure_bounds_handles_same_side_and_excess_opposite_side():
    reconstructor = SidecarPositionReconstructor()
    user_state = UserState(
        user="0xuser",
        balance=1000.0,
        positions=(
            UserPosition(
                coin="ETH",
                asset_idx=1,
                size=5.0,
                entry_px=2000.0,
                leverage=10.0,
                cum_funding=0.0,
                margin=100.0,
            ),
        ),
    )
    orders = (
        UserOrder(user="0xuser", oid=1, coin="ETH", side="B", limit_px=2000.0, size=2.0, reduce_only=False),
        UserOrder(user="0xuser", oid=2, coin="ETH", side="A", limit_px=2100.0, size=3.0, reduce_only=False),
        UserOrder(user="0xuser", oid=3, coin="ETH", side="A", limit_px=2200.0, size=4.0, reduce_only=False),
        UserOrder(user="0xuser", oid=4, coin="ETH", side="A", limit_px=2300.0, size=1.0, reduce_only=True),
        UserOrder(user="0xuser", oid=5, coin="HYPE", side="B", limit_px=40.0, size=10.0, reduce_only=False),
    )

    bounds = reconstructor.compute_resting_order_exposure_bounds(
        user_state,
        orders,
        target_coin="ETH",
    )

    assert bounds.active_order_count == 5
    assert bounds.non_reduce_only_order_count == 4
    assert bounds.reduce_only_order_count == 1
    assert bounds.total_active_notional == 21800.0
    assert bounds.non_reduce_only_notional == 19500.0
    assert bounds.reduce_only_notional == 2300.0
    assert bounds.exposure_increasing_notional_lower_bound == 8600.0
    assert bounds.exposure_increasing_notional_upper_bound == 8800.0
    assert bounds.target_coin_exposure_increasing_lower_bound == 8200.0
    assert bounds.target_coin_exposure_increasing_upper_bound == 8400.0
    assert bounds.off_target_exposure_increasing_lower_bound == 400.0
    assert bounds.off_target_exposure_increasing_upper_bound == 400.0
    assert bounds.per_coin["ETH"]["position_size"] == 5.0
    assert bounds.per_coin["ETH"]["reduce_only_order_count"] == 1



def test_compute_resting_order_exposure_bounds_with_flat_position_counts_all_non_reduce_only_as_opening():
    reconstructor = SidecarPositionReconstructor()
    user_state = UserState(user="0xflat", balance=500.0, positions=())
    orders = (
        UserOrder(user="0xflat", oid=1, coin="BTC", side="B", limit_px=70000.0, size=0.1, reduce_only=False),
        UserOrder(user="0xflat", oid=2, coin="BTC", side="A", limit_px=71000.0, size=0.2, reduce_only=False),
        UserOrder(user="0xflat", oid=3, coin="BTC", side="A", limit_px=72000.0, size=0.05, reduce_only=True),
    )

    bounds = reconstructor.compute_resting_order_exposure_bounds(
        user_state,
        orders,
        target_coin="ETH",
    )

    assert bounds.total_active_notional == 24800.0
    assert bounds.non_reduce_only_notional == 21200.0
    assert bounds.exposure_increasing_notional_lower_bound == 21200.0
    assert bounds.exposure_increasing_notional_upper_bound == 21200.0
    assert bounds.off_target_exposure_increasing_lower_bound == 21200.0
    assert bounds.off_target_exposure_increasing_upper_bound == 21200.0
