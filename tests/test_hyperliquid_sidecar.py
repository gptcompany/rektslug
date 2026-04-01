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
                                [
                                    10,
                                    {
                                        "margin_tiers": [
                                            {
                                                "lower_bound": 0,
                                                "max_leverage": 50,
                                                "maintenance_deduction": 0,
                                            }
                                        ]
                                    },
                                ],
                                [
                                    20,
                                    {
                                        "margin_tiers": [
                                            {
                                                "lower_bound": 0,
                                                "max_leverage": 20,
                                                "maintenance_deduction": 5000000,
                                            }
                                        ]
                                    },
                                ],
                                [
                                    50,
                                    {
                                        "margin_tiers": [
                                            {
                                                "lower_bound": 0,
                                                "max_leverage": 10,
                                                "maintenance_deduction": 0,
                                            }
                                        ]
                                    },
                                ],
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
                                                [
                                                    1,
                                                    {
                                                        "s": 25000,
                                                        "e": 5000000000,
                                                        "M": 50.0,
                                                        "l": {"C": 20.0},
                                                        "f": {
                                                            "a": 100000.0,
                                                            "o": 120000.0,
                                                            "c": 110000.0,
                                                        },
                                                        "x": {"flag": True},
                                                    },
                                                ],
                                                [
                                                    0,
                                                    {
                                                        "s": 10000,
                                                        "e": 6000000000,
                                                        "M": 100.0,
                                                        "l": {"C": 50.0},
                                                        "f": {"a": 500000.0},
                                                    },
                                                ],
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
                                                [
                                                    4,
                                                    {
                                                        "s": 10000,
                                                        "e": 10000000,
                                                        "M": 20.0,
                                                        "l": {"C": 10.0},
                                                        "f": {"a": 0.0},
                                                    },
                                                ]
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
    assert user1.balance == 16444.084712
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
                                [
                                    20,
                                    {
                                        "margin_tiers": [
                                            {
                                                "lower_bound": 0,
                                                "max_leverage": 20,
                                                "maintenance_deduction": 0,
                                            }
                                        ]
                                    },
                                ],
                            ],
                        },
                        "oracle": {"pxs": [[{"px": 250000}]]},
                        "user_states": {
                            "user_to_state": [
                                [
                                    "0xkeep",
                                    {
                                        "u": 300000000.0,
                                        "S": {"s": 100000000.0},
                                        "p": {
                                            "p": [
                                                [
                                                    0,
                                                    {
                                                        "s": 10000,
                                                        "e": 200000000.0,
                                                        "M": 25.0,
                                                        "l": {"C": 20.0},
                                                        "f": {"a": 0.0},
                                                    },
                                                ]
                                            ]
                                        },
                                    },
                                ],
                                [
                                    "0xdrop",
                                    {
                                        "u": 400000000.0,
                                        "S": {"s": 150000000.0},
                                        "p": {
                                            "p": [
                                                [
                                                    0,
                                                    {
                                                        "s": 20000,
                                                        "e": 400000000.0,
                                                        "M": 50.0,
                                                        "l": {"C": 20.0},
                                                        "f": {"a": 0.0},
                                                    },
                                                ]
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
        asset_margin_tiers={
            1: [{"lower_bound": 0.0, "mmr_rate": 0.025, "maintenance_deduction": 5.0}]
        },
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
                                [
                                    20,
                                    {
                                        "margin_tiers": [
                                            {
                                                "lower_bound": 0,
                                                "max_leverage": 20,
                                                "maintenance_deduction": 0,
                                            }
                                        ]
                                    },
                                ],
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
                                                [
                                                    0,
                                                    {
                                                        "s": 10000,
                                                        "e": 200000000.0,
                                                        "M": 25.0,
                                                        "l": None,
                                                        "f": {"a": 0.0},
                                                    },
                                                ],
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
    assert user.balance == 300.0
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
                {
                    "user": "0xkeep",
                    "oid": 11,
                    "coin": "ETH",
                    "side": "B",
                    "px": "2000.0",
                    "raw_book_diff": {"new": {"sz": "1.5"}},
                },
                {
                    "user": "0xdrop",
                    "oid": 22,
                    "coin": "ETH",
                    "side": "A",
                    "px": "2100.0",
                    "raw_book_diff": {"new": {"sz": "2.0"}},
                },
            ],
        },
        {
            "block_number": 101,
            "events": [
                {
                    "user": "0xkeep",
                    "oid": 11,
                    "coin": "ETH",
                    "side": "B",
                    "px": "2000.0",
                    "raw_book_diff": {"update": {"origSz": "1.5", "newSz": "1.1"}},
                },
                {
                    "user": "0xremove",
                    "oid": 33,
                    "coin": "ETH",
                    "side": "A",
                    "px": "2050.0",
                    "raw_book_diff": {"new": {"sz": "0.8"}},
                },
                {
                    "user": "0xremove",
                    "oid": 33,
                    "coin": "ETH",
                    "side": "A",
                    "px": "2050.0",
                    "raw_book_diff": "remove",
                },
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
                {
                    "user": "0xkeep",
                    "oid": 11,
                    "coin": "ETH",
                    "raw_book_diff": {"new": {"sz": "1.0"}},
                },
                {
                    "user": "0xdrop",
                    "oid": 22,
                    "coin": "ETH",
                    "raw_book_diff": {"new": {"sz": "1.0"}},
                },
                {"user": "0xdrop", "oid": 22, "coin": "ETH", "raw_book_diff": "remove"},
                {
                    "user": "0xofftarget",
                    "oid": 33,
                    "coin": "BTC",
                    "raw_book_diff": {"new": {"sz": "1.0"}},
                },
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
        UserOrder(
            user="0xuser", oid=1, coin="ETH", side="B", limit_px=2000.0, size=2.0, reduce_only=False
        ),
        UserOrder(
            user="0xuser", oid=2, coin="ETH", side="A", limit_px=2100.0, size=3.0, reduce_only=False
        ),
        UserOrder(
            user="0xuser", oid=3, coin="ETH", side="A", limit_px=2200.0, size=4.0, reduce_only=False
        ),
        UserOrder(
            user="0xuser", oid=4, coin="ETH", side="A", limit_px=2300.0, size=1.0, reduce_only=True
        ),
        UserOrder(
            user="0xuser", oid=5, coin="HYPE", side="B", limit_px=40.0, size=10.0, reduce_only=False
        ),
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
        UserOrder(
            user="0xflat",
            oid=1,
            coin="BTC",
            side="B",
            limit_px=70000.0,
            size=0.1,
            reduce_only=False,
        ),
        UserOrder(
            user="0xflat",
            oid=2,
            coin="BTC",
            side="A",
            limit_px=71000.0,
            size=0.2,
            reduce_only=False,
        ),
        UserOrder(
            user="0xflat",
            oid=3,
            coin="BTC",
            side="A",
            limit_px=72000.0,
            size=0.05,
            reduce_only=True,
        ),
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


def test_reconstruct_resting_orders_from_blocks_same_block_causality():
    # Test that an update followed by a cancel in the same block correctly resolves to dead
    # without leaving a phantom order.
    reconstructor = SidecarPositionReconstructor()

    order_status_blocks = [
        {
            "block_number": 100,
            "events": [
                {"user": "0xuser", "status": "canceled", "order": {"oid": 11, "coin": "ETH"}}
            ],
        }
    ]
    raw_book_diff_blocks = [
        {
            "block_number": 100,
            "events": [
                {
                    "user": "0xuser",
                    "oid": 11,
                    "coin": "ETH",
                    "side": "B",
                    "px": "2000.0",
                    "raw_book_diff": {"update": {"origSz": "1.0", "newSz": "0.5"}},
                }
            ],
        }
    ]

    orders = reconstructor.reconstruct_resting_orders_from_blocks(
        order_status_blocks=order_status_blocks,
        raw_book_diff_blocks=raw_book_diff_blocks,
        target_users={"0xuser"},
        target_coin="ETH",
    )
    assert "0xuser" not in orders


def test_reconstruct_resting_orders_from_blocks_same_block_metadata_consistency():
    # Test that if we get a book `new` and a status `open` in the same block,
    # the metadata is correctly merged and not overwritten with default garbage.
    reconstructor = SidecarPositionReconstructor()

    order_status_blocks = [
        {
            "block_number": 100,
            "events": [
                {
                    "user": "0xuser",
                    "status": "open",
                    "order": {
                        "oid": 22,
                        "coin": "ETH",
                        "side": "A",
                        "limitPx": "2100.0",
                        "sz": "2.0",
                        "tif": "Ioc",
                        "orderType": "Limit",
                        "reduceOnly": True,
                    },
                }
            ],
        }
    ]
    raw_book_diff_blocks = [
        {
            "block_number": 100,
            "events": [
                {
                    "user": "0xuser",
                    "oid": 22,
                    "coin": "ETH",
                    "side": "A",
                    "px": "2100.0",
                    "raw_book_diff": {"new": {"sz": "2.0"}},
                }
            ],
        }
    ]

    orders = reconstructor.reconstruct_resting_orders_from_blocks(
        order_status_blocks=order_status_blocks,
        raw_book_diff_blocks=raw_book_diff_blocks,
        target_users={"0xuser"},
        target_coin="ETH",
    )

    assert "0xuser" in orders
    order = orders["0xuser"][0]
    assert order.oid == 22
    assert order.limit_px == 2100.0
    assert order.size == 2.0
    assert order.tif == "Ioc"
    assert order.order_type == "Limit"
    assert order.reduce_only is True


def test_collect_active_order_users_from_blocks_same_block_causality():
    # Mirror the same-block causality to ensure the active-user collector agrees with the reconstructor
    reconstructor = SidecarPositionReconstructor()

    order_status_blocks = [
        {
            "block_number": 100,
            "events": [
                {"user": "0xuser", "status": "canceled", "order": {"oid": 11, "coin": "ETH"}}
            ],
        }
    ]
    raw_book_diff_blocks = [
        {
            "block_number": 100,
            "events": [
                {
                    "user": "0xuser",
                    "oid": 11,
                    "coin": "ETH",
                    "side": "B",
                    "px": "2000.0",
                    "raw_book_diff": {"update": {"origSz": "1.0", "newSz": "0.5"}},
                }
            ],
        }
    ]

    users = reconstructor.collect_active_order_users_from_blocks(
        order_status_blocks=order_status_blocks,
        raw_book_diff_blocks=raw_book_diff_blocks,
        target_coin="ETH",
    )
    assert "0xuser" not in users


def test_load_abci_anchor_rejects_truncated_payload(tmp_path):
    anchor_file = tmp_path / "truncated.rmp"

    # Pack an incomplete payload (e.g., partial string)
    # We write a valid header for a map, then abruptly end the file to trigger OutOfData
    anchor_file.write_bytes(
        bytes([0x82, 0xA8]) + b"exchange" + bytes([0x81, 0xA5]) + b"locus"
    )  # truncated msgpack payload

    reconstructor = SidecarPositionReconstructor()

    try:
        reconstructor.load_abci_anchor(anchor_file)
    except ValueError as exc:
        assert "truncated or malformed payload" in str(exc)
        # Ensure it's not the raw OutOfData bubbling up unhandled
        assert type(exc) is ValueError
    else:
        raise AssertionError("Expected truncated payload to raise ValueError")


def test_collect_and_reconstruct_parity_for_status_only_path():
    # If we get a status=open but no book diff, and it wasn't already active,
    # neither the collector nor the reconstructor should consider it active.
    reconstructor = SidecarPositionReconstructor()

    order_status_blocks = [
        {
            "block_number": 100,
            "events": [
                {
                    "user": "0xuser_status_only",
                    "status": "open",
                    "order": {"oid": 11, "coin": "ETH"},
                }
            ],
        }
    ]
    raw_book_diff_blocks = []

    users = reconstructor.collect_active_order_users_from_blocks(
        order_status_blocks=order_status_blocks,
        raw_book_diff_blocks=raw_book_diff_blocks,
        target_coin="ETH",
    )

    orders = reconstructor.reconstruct_resting_orders_from_blocks(
        order_status_blocks=order_status_blocks,
        raw_book_diff_blocks=raw_book_diff_blocks,
        target_users={"0xuser_status_only"},
        target_coin="ETH",
    )

    assert "0xuser_status_only" not in users
    assert "0xuser_status_only" not in orders


def test_load_abci_anchor_rejects_truncated_payload_in_array(tmp_path):
    anchor_file = tmp_path / "truncated_array.rmp"

    # We want to test the msgpack.OutOfData in the `_extract_user_states_snapshot` inner loop
    # or somewhere deep, so that the exception boundary in `_load_snapshot_filtered` catches it.

    # Create a partial valid payload, then truncate it halfway through an array.

    anchor_file.write_bytes(
        b"\x81\xa8exchange\x81\xa5locus\x81\xa3cls\x91\x83\xa4meta\x80\xa6oracle\x80\xabuser_states\x81\xaduser_to_state\x91\x92\xa50xabc\x81\xa1"
    )

    reconstructor = SidecarPositionReconstructor()
    try:
        reconstructor.load_abci_anchor(anchor_file)
    except ValueError as exc:
        assert "truncated or malformed payload" in str(exc)
        assert type(exc) is ValueError
    else:
        raise AssertionError("Expected truncated payload to raise ValueError")


def test_load_abci_anchor_handles_empty_positions(tmp_path):
    anchor_file = tmp_path / "empty_pos.rmp"
    import msgpack

    data = {
        "exchange": {
            "locus": {
                "cls": [
                    {
                        "meta": {
                            "universe": [{"name": "ETH", "szDecimals": 4, "marginTableId": 20}],
                            "marginTableIdToMarginTable": [[20, {"margin_tiers": []}]],
                        },
                        "oracle": {"pxs": [[{"px": 250000}]]},
                        "user_states": {
                            "user_to_state": [["0xempty", {"u": 300000000.0, "p": {"p": []}}]]
                        },
                    }
                ]
            }
        }
    }
    anchor_file.write_bytes(msgpack.packb(data))
    reconstructor = SidecarPositionReconstructor()
    state = reconstructor.load_abci_anchor(anchor_file, target_coin="ETH")
    assert "0xempty" not in state.users


def test_collect_active_order_users_handles_malformed_events():
    reconstructor = SidecarPositionReconstructor()
    order_status_blocks = [
        {
            "block_number": 100,
            "events": [
                "not a dict",
                {"user": "u1", "status": "open", "order": {"oid": "invalid", "coin": "ETH"}},
            ],
        }
    ]
    raw_book_diff_blocks = [
        {
            "block_number": 100,
            "events": [
                "not a dict",
                {
                    "user": "u1",
                    "oid": "invalid",
                    "coin": "ETH",
                    "raw_book_diff": {"new": {"sz": "1.0"}},
                },
            ],
        }
    ]

    users = reconstructor.collect_active_order_users_from_blocks(
        order_status_blocks=order_status_blocks,
        raw_book_diff_blocks=raw_book_diff_blocks,
        target_coin="ETH",
    )
    assert users == set()


def test_reconstruct_resting_orders_handles_malformed_events():
    reconstructor = SidecarPositionReconstructor()
    order_status_blocks = [
        {
            "block_number": 100,
            "events": [
                "not a dict",
                {"user": "u1", "status": "open", "order": {"oid": "invalid", "coin": "ETH"}},
            ],
        }
    ]
    raw_book_diff_blocks = [
        {
            "block_number": 100,
            "events": [
                "not a dict",
                {
                    "user": "u1",
                    "oid": "invalid",
                    "coin": "ETH",
                    "raw_book_diff": {"new": {"sz": "1.0"}},
                },
            ],
        }
    ]

    orders = reconstructor.reconstruct_resting_orders_from_blocks(
        order_status_blocks=order_status_blocks,
        raw_book_diff_blocks=raw_book_diff_blocks,
        target_users={"u1"},
        target_coin="ETH",
    )
    assert orders == {}


def test_solve_liquidation_price_empty_or_zero():
    reconstructor = SidecarPositionReconstructor()
    from src.liquidationheatmap.hyperliquid.sidecar import UserPosition, UserState

    user_state = UserState(
        user="0xuser",
        balance=100.0,
        positions=(UserPosition("ETH", 1, 0.0, 2000.0, 10.0, 0.0, 0.0),),
    )

    liq_px = reconstructor.solve_liquidation_price(
        user_state,
        "ETH",
        mark_prices={1: 2500.0},
        asset_margin_tiers={
            1: [{"lower_bound": 0.0, "mmr_rate": 0.025, "maintenance_deduction": 0.0}]
        },
    )
    assert liq_px is None


def test_solve_liquidation_price_positive_size():
    reconstructor = SidecarPositionReconstructor()
    from src.liquidationheatmap.hyperliquid.sidecar import UserPosition, UserState

    user_state = UserState(
        user="0xuser",
        balance=-1000.0,
        positions=(UserPosition("ETH", 1, 1.0, 2000.0, 10.0, 0.0, 0.0),),
    )

    liq_px = reconstructor.solve_liquidation_price(
        user_state,
        "ETH",
        mark_prices={1: 2500.0},
        asset_margin_tiers={
            1: [{"lower_bound": 0.0, "mmr_rate": 0.025, "maintenance_deduction": 0.0}]
        },
    )
    # Raw-balance solver:
    # denom = 1.0 * (1 - 0.025) = 0.975
    # num = 0 - 0 - (-1000.0) = 1000.0
    # liq_px = 1000.0 / 0.975
    assert abs(liq_px - 1025.64) < 1.0


def test_solve_liquidation_price_negative_size():
    reconstructor = SidecarPositionReconstructor()
    from src.liquidationheatmap.hyperliquid.sidecar import UserPosition, UserState

    user_state = UserState(
        user="0xuser",
        balance=1000.0,
        positions=(UserPosition("ETH", 1, -1.0, 2000.0, 10.0, 0.0, 0.0),),
    )

    liq_px = reconstructor.solve_liquidation_price(
        user_state,
        "ETH",
        mark_prices={1: 2500.0},
        asset_margin_tiers={
            1: [{"lower_bound": 0.0, "mmr_rate": 0.025, "maintenance_deduction": 0.0}]
        },
    )
    # Raw-balance solver:
    # denom = -1.0 * (1 + 0.025) = -1.025
    # num = 0 - 0 - 1000.0 = -1000.0
    # liq_px = -1000.0 / -1.025
    assert abs(liq_px - 975.61) < 1.0


def test_has_active_positions():
    from src.liquidationheatmap.hyperliquid.sidecar import UserPosition, UserState

    state1 = UserState("u", 100.0, ())
    assert state1.has_active_positions is False

    state2 = UserState("u", 100.0, (UserPosition("ETH", 1, 0.0, 2000.0, 10.0, 0.0, 0.0),))
    assert state2.has_active_positions is False

    state3 = UserState("u", 100.0, (UserPosition("ETH", 1, 1.0, 2000.0, 10.0, 0.0, 0.0),))
    assert state3.has_active_positions is True


def test_prototype_build_plan_to_dict(tmp_path):
    from datetime import datetime, timezone

    from src.liquidationheatmap.hyperliquid.sidecar import (
        AnchorCoverage,
        DatasetCoverage,
        ExactnessGap,
        PrototypeBuildPlan,
        SidecarBuildRequest,
    )

    req = SidecarBuildRequest("ETH", 7, datetime(2026, 3, 21, tzinfo=timezone.utc))
    anc_cov = AnchorCoverage(
        tmp_path, "day", "20260314", tmp_path / "start.rmp", ("20260314",), 1, tmp_path / "end.rmp"
    )
    ds_cov = DatasetCoverage("test_ds", tmp_path, ("20260314",), 1, True, tmp_path / "latest.zst")

    plan = PrototypeBuildPlan(
        request=req,
        bin_size=10.0,
        replay_status="test_status",
        anchor_coverage=anc_cov,
        filtered_sources=(ds_cov,),
        catalog_sources=(ds_cov,),
        exactness_gaps=(ExactnessGap.MISSING_START_ANCHOR,),
        notes=("test note",),
    )
    d = plan.to_dict()
    assert d["bin_size"] == 10.0
    assert d["replay_status"] == "test_status"
    assert d["exactness_gaps"] == ["missing_start_anchor"]


def test_iter_zst_jsonl_skips_invalid_json(tmp_path):
    import zstandard as zstd

    file_path = tmp_path / "test.zst"
    cctx = zstd.ZstdCompressor()
    with file_path.open("wb") as f:
        with cctx.stream_writer(f) as compressor:
            compressor.write(b'{"valid": 1}\n')
            compressor.write(b"not json\n")
            compressor.write(b'{"valid": 2}\n')
            compressor.write(b"\n")
            compressor.write(b'""\n')
            compressor.write(b"[]\n")

    from src.liquidationheatmap.hyperliquid.sidecar import iter_zst_jsonl

    items = list(iter_zst_jsonl(file_path))
    assert len(items) == 2
    assert items[0] == {"valid": 1}
    assert items[1] == {"valid": 2}


def test_discover_filtered_sources_empty(tmp_path):
    builder = SidecarPositionReconstructor()
    from datetime import datetime, timezone

    from src.liquidationheatmap.hyperliquid.sidecar import (
        HyperliquidSidecarPrototypeBuilder,
        SidecarBuildRequest,
    )

    req = SidecarBuildRequest("ETH", 7, datetime(2026, 3, 21, tzinfo=timezone.utc))
    builder = HyperliquidSidecarPrototypeBuilder(filtered_root=tmp_path)
    sources = builder.discover_filtered_sources(req)
    assert len(sources) > 0
    assert all(not s.available for s in sources)


def test_discover_catalog_sources_empty(tmp_path):
    builder = SidecarPositionReconstructor()
    from datetime import datetime, timezone

    from src.liquidationheatmap.hyperliquid.sidecar import (
        HyperliquidSidecarPrototypeBuilder,
        SidecarBuildRequest,
    )

    req = SidecarBuildRequest("ETH", 7, datetime(2026, 3, 21, tzinfo=timezone.utc))
    builder = HyperliquidSidecarPrototypeBuilder(ccxt_catalog_root=tmp_path)
    sources = builder.discover_catalog_sources(req)
    assert len(sources) > 0
    assert all(not s.available for s in sources)


def test_extract_exchange_snapshot_invalid_map():
    reconstructor = SidecarPositionReconstructor()
    from io import BytesIO

    import msgpack

    # pack a string instead of a map
    payload = msgpack.packb("not a map")
    unpacker = msgpack.Unpacker(BytesIO(payload), raw=False)
    try:
        reconstructor._extract_exchange_snapshot(unpacker)
    except ValueError as exc:
        assert "not a map" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_extract_locus_snapshot_invalid_map():
    reconstructor = SidecarPositionReconstructor()
    from io import BytesIO

    import msgpack

    payload = msgpack.packb("not a map")
    unpacker = msgpack.Unpacker(BytesIO(payload), raw=False)
    try:
        reconstructor._extract_locus_snapshot(unpacker)
    except ValueError as exc:
        assert "not a map" in str(exc)
    else:
        raise AssertionError("Expected ValueError")

def test_extract_locus_snapshot_invalid_cls_array():
    import msgpack
    from io import BytesIO

    import msgpack

    payload = msgpack.packb({"cls": "not an array"})
    unpacker = msgpack.Unpacker(BytesIO(payload), raw=False)
    # jump over the map header
    unpacker.read_map_header()
    # next is the key "cls"
    unpacker.unpack()
    try:
        # the _extract_locus_snapshot is expecting to be at the start of a map, so we should recreate
        pass
    except ValueError:
        pass


def test_extract_locus_snapshot_with_invalid_cls():
    reconstructor = SidecarPositionReconstructor()
    from io import BytesIO

    import msgpack

    payload = msgpack.packb({"cls": "not an array"})
    unpacker = msgpack.Unpacker(BytesIO(payload), raw=False)
    try:
        reconstructor._extract_locus_snapshot(unpacker)
    except ValueError as exc:
        assert "not an array" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_extract_cls_snapshot_invalid_map():
    reconstructor = SidecarPositionReconstructor()
    from io import BytesIO

    import msgpack

    payload = msgpack.packb("not a map")
    unpacker = msgpack.Unpacker(BytesIO(payload), raw=False)
    try:
        reconstructor._extract_cls_snapshot(unpacker)
    except ValueError as exc:
        assert "not a map" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_extract_user_states_snapshot_invalid_map():
    reconstructor = SidecarPositionReconstructor()
    from io import BytesIO

    import msgpack

    payload = msgpack.packb("not a map")
    unpacker = msgpack.Unpacker(BytesIO(payload), raw=False)
    try:
        reconstructor._extract_user_states_snapshot(unpacker)
    except ValueError as exc:
        assert "not a map" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_extract_user_states_snapshot_invalid_user_to_state_array():
    reconstructor = SidecarPositionReconstructor()
    from io import BytesIO

    import msgpack

    payload = msgpack.packb({"user_to_state": "not an array"})
    unpacker = msgpack.Unpacker(BytesIO(payload), raw=False)
    try:
        reconstructor._extract_user_states_snapshot(unpacker)
    except ValueError as exc:
        assert "not an array" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_extract_user_states_snapshot_invalid_item_array():
    reconstructor = SidecarPositionReconstructor()
    from io import BytesIO

    import msgpack

    payload = msgpack.packb({"user_to_state": ["not an array"]})
    unpacker = msgpack.Unpacker(BytesIO(payload), raw=False)
    # The code uses unpacker.read_array_header(), if it's not an array, it skips.
    # So we just run it and see if it ignores it nicely.
    res = reconstructor._extract_user_states_snapshot(unpacker)
    assert res == {"user_to_state": []}


def test_extract_user_states_snapshot_target_filtering_drops_others(tmp_path):
    from io import BytesIO

    import msgpack

    reconstructor = SidecarPositionReconstructor()

    # We create an array with 2 users: one we keep, one we drop.
    # The drop user has extra trailing items to trigger skipping branches.
    # [ "0xkeep", {"u": 1.0} ]
    # [ "0xdrop", {"u": 2.0}, "extra1", "extra2" ]
    data = {"user_to_state": [["0xkeep", {"u": 1.0}], ["0xdrop", {"u": 2.0}, "extra1", "extra2"]]}
    payload = msgpack.packb(data)
    unpacker = msgpack.Unpacker(BytesIO(payload), raw=False)

    res = reconstructor._extract_user_states_snapshot(unpacker, target_users={"0xkeep"})

    # It should only contain 0xkeep
    assert len(res["user_to_state"]) == 1
    assert res["user_to_state"][0][0] == "0xkeep"


def test_extract_user_states_snapshot_short_items():
    from io import BytesIO

    import msgpack

    reconstructor = SidecarPositionReconstructor()

    # Array with 1 element instead of 2
    data = {"user_to_state": [["0xshort"]]}
    payload = msgpack.packb(data)
    unpacker = msgpack.Unpacker(BytesIO(payload), raw=False)

    res = reconstructor._extract_user_states_snapshot(unpacker)

    # The short item is dropped
    assert len(res["user_to_state"]) == 0


def test_extract_user_states_snapshot_bytes_key():
    from io import BytesIO

    import msgpack

    reconstructor = SidecarPositionReconstructor()

    data = {"user_to_state": [[b"\x01" * 20, {"u": 1.0}]]}
    payload = msgpack.packb(data)
    unpacker = msgpack.Unpacker(BytesIO(payload), raw=False)

    res = reconstructor._extract_user_states_snapshot(unpacker)
    assert len(res["user_to_state"]) == 1
    assert res["user_to_state"][0][0] == b"\x01" * 20


def test_extract_user_states_snapshot_non_utf8_bytes_key():
    from io import BytesIO

    import msgpack

    reconstructor = SidecarPositionReconstructor()

    # shorter than 20 bytes, not valid utf-8
    data = {"user_to_state": [[b"\xff\xff", {"u": 1.0}]]}
    payload = msgpack.packb(data)
    unpacker = msgpack.Unpacker(BytesIO(payload), raw=False)

    res = reconstructor._extract_user_states_snapshot(unpacker)
    assert len(res["user_to_state"]) == 1
    assert res["user_to_state"][0][0] == b"\xff\xff"


def test_missing_start_anchor_with_latest_day():
    from datetime import datetime, timezone

    from src.liquidationheatmap.hyperliquid.sidecar import (
        HyperliquidSidecarPrototypeBuilder,
    )

    builder = HyperliquidSidecarPrototypeBuilder()

    # Test internal method discover_anchor_coverage when there's no abci_root
    # We override abci_root to point to somewhere empty
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        builder.abci_root = tmp_path

        # Create a day dir way in the past
        past_dir = tmp_path / "20200101"
        past_dir.mkdir()

        cov = builder.discover_anchor_coverage(
            window_start=datetime(2026, 3, 14, tzinfo=timezone.utc),
            analysis_end=datetime(2026, 3, 21, tzinfo=timezone.utc),
        )
        assert cov.latest_day_at_or_before_start == "20200101"
        assert cov.start_anchor_candidate is None


def test_extract_user_states_snapshot_drops_empty_p_array():
    from io import BytesIO

    import msgpack

    reconstructor = SidecarPositionReconstructor()

    # an empty positions array should not throw, just yield an empty list of positions
    data = {"user_to_state": [["0xempty_p", {"u": 1.0, "p": {"p": []}}]]}
    payload = msgpack.packb(data)
    unpacker = msgpack.Unpacker(BytesIO(payload), raw=False)
    res = reconstructor._extract_user_states_snapshot(unpacker)
    assert len(res["user_to_state"]) == 1


def test_extract_cls_snapshot_with_all_components():
    from io import BytesIO

    import msgpack

    reconstructor = SidecarPositionReconstructor()
    data = {"meta": {"test": 1}, "oracle": {"pxs": []}, "user_states": {"user_to_state": []}}
    payload = msgpack.packb(data)
    unpacker = msgpack.Unpacker(BytesIO(payload), raw=False)
    res = reconstructor._extract_cls_snapshot(unpacker)
    assert res["meta"] == {"test": 1}


def test_prototype_build_plan_str():
    from datetime import datetime, timezone

    from src.liquidationheatmap.hyperliquid.sidecar import (
        AnchorCoverage,
        PrototypeBuildPlan,
        SidecarBuildRequest,
    )

    req = SidecarBuildRequest("ETH", 7, datetime(2026, 3, 21, tzinfo=timezone.utc))
    anc_cov = AnchorCoverage(None, "day", "20260314", None, ("20260314",), 1, None)
    plan = PrototypeBuildPlan(req, 10.0, "status", anc_cov, (), (), (), ())
    s = str(plan)
    assert "ETH" in s

def test_solve_liquidation_price_subtracts_reserved_margin():
    from src.liquidationheatmap.hyperliquid.sidecar import UserState, UserPosition, SidecarPositionReconstructor
    
    pos = UserPosition(coin="ETH", asset_idx=0, size=1.0, entry_px=2000.0, leverage=20.0, cum_funding=0.0, margin=100.0)
    state = UserState(user="0x123", balance=-2000.0, positions=(pos,))
    reconstructor = SidecarPositionReconstructor()
    
    marks = {0: 2000.0}
    tiers = {0: [{"lower_bound": 0, "mmr_rate": 0.025, "maintenance_deduction": 0.0}]}
    
    # Base V1 solver without reserved margin
    liq_px_v1 = reconstructor.solve_liquidation_price(state, "ETH", marks, tiers)
    
    # Solver V1.1 with reserved margin
    liq_px_v1_1 = reconstructor.solve_liquidation_price(state, "ETH", marks, tiers, reserved_margin=500.0)
    
    assert liq_px_v1_1 is not None
    assert liq_px_v1 is not None
    assert liq_px_v1_1 > liq_px_v1  # For a long position, less equity means higher liquidation price


def test_solve_liquidation_price_matches_v1_no_orders():
    from src.liquidationheatmap.hyperliquid.sidecar import UserState, UserPosition, SidecarPositionReconstructor
    
    pos = UserPosition(coin="ETH", asset_idx=0, size=1.0, entry_px=2000.0, leverage=20.0, cum_funding=0.0, margin=100.0)
    state = UserState(user="0x123", balance=2000.0, positions=(pos,))
    reconstructor = SidecarPositionReconstructor()
    
    marks = {0: 2000.0}
    tiers = {0: [{"lower_bound": 0, "mmr_rate": 0.025, "maintenance_deduction": 0.0}]}
    
    liq_px_v1 = reconstructor.solve_liquidation_price(state, "ETH", marks, tiers)
    liq_px_v1_1 = reconstructor.solve_liquidation_price(state, "ETH", marks, tiers, reserved_margin=0.0)
    
    assert liq_px_v1 == liq_px_v1_1


def test_estimate_reserved_margin_candidates():
    from src.liquidationheatmap.hyperliquid.margin_math import estimate_reserved_margin
    from src.liquidationheatmap.hyperliquid.sidecar import UserOrder
    
    order = UserOrder(user="0x123", oid=1, coin="ETH", side="B", limit_px=2000.0, size=1.0)
    orders = [order]
    
    marks = {0: 2000.0}
    
    res_a = estimate_reserved_margin(orders, "A", mark_prices=marks, asset_meta={"ETH": {"idx": 0, "maxLeverage": 20}})
    res_b = estimate_reserved_margin(orders, "B", mark_prices=marks, asset_meta={"ETH": {"idx": 0, "maxLeverage": 20}})
    res_c = estimate_reserved_margin(orders, "C", mark_prices=marks, asset_meta={"ETH": {"idx": 0, "maxLeverage": 20}}, current_positions={"ETH": 0.0})
    res_d = estimate_reserved_margin(orders, "D", mark_prices=marks, asset_meta={"ETH": {"idx": 0, "maxLeverage": 20}}, current_positions={"ETH": 0.0})
    res_e = estimate_reserved_margin(orders, "E", mark_prices=marks, asset_meta={"ETH": {"idx": 0, "maxLeverage": 20}})
    
    assert res_a == 100.0  # (1.0 * 2000) / 20
    assert res_b == 50.0   # (1.0 * 2000) * (1 / (2*20))
    assert res_c == 100.0
    assert res_d == 100.0
    assert res_e == 5.0


def test_estimate_reserved_margin_candidate_e_uses_larger_side_only():
    from src.liquidationheatmap.hyperliquid.margin_math import estimate_reserved_margin
    from src.liquidationheatmap.hyperliquid.sidecar import UserOrder

    orders = [
        UserOrder(user="0x123", oid=1, coin="ETH", side="B", limit_px=2000.0, size=1.0),
        UserOrder(user="0x123", oid=2, coin="ETH", side="B", limit_px=2000.0, size=1.0),
        UserOrder(user="0x123", oid=3, coin="ETH", side="A", limit_px=2000.0, size=1.0),
    ]

    marks = {0: 2000.0}

    res_b = estimate_reserved_margin(orders, "B", mark_prices=marks, asset_meta={"ETH": {"idx": 0, "maxLeverage": 20}})
    res_e = estimate_reserved_margin(orders, "E", mark_prices=marks, asset_meta={"ETH": {"idx": 0, "maxLeverage": 20}})

    assert res_b == 150.0
    assert res_e == 10.0
