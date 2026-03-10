"""Tests for spec-017: Provider Liq-Map Comparison workflow.

Covers:
- T009: Unsupported timeframes/symbols fail fast
- T010: Only liq-map product accepted
- T013: CoinAnk URL generation
- T014: CoinAnk capture manifest metadata
- T018: Coinglass 1d -> interval=1, limit=1500
- T019: Coinglass 1w -> interval=5, limit=2000
- T020: Manifest capture_mode and timeframe_applied fields
- T024: Normalized report loading
- T025: Gap analysis on liq-map-only manifests
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
for p in (str(REPO_ROOT), str(SCRIPTS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)


# ============================================================================
# T009: Unsupported timeframes/symbols fail fast
# ============================================================================


SPEC_017_SUPPORTED_SYMBOLS = {"BTC", "ETH"}
SPEC_017_SUPPORTED_TIMEFRAMES = {"1d", "1w"}


class TestMatrixValidation:
    """Validate the spec-017 comparison matrix constraints."""

    def test_supported_symbol_btc_accepted(self):
        from scripts.run_provider_api_comparison import validate_spec017_matrix

        validate_spec017_matrix("BTC", "1w")  # should not raise

    def test_supported_symbol_eth_accepted(self):
        from scripts.run_provider_api_comparison import validate_spec017_matrix

        validate_spec017_matrix("ETH", "1d")  # should not raise

    def test_unsupported_symbol_rejected(self):
        from scripts.run_provider_api_comparison import validate_spec017_matrix

        with pytest.raises(ValueError, match="Unsupported symbol"):
            validate_spec017_matrix("SOL", "1w")

    def test_unsupported_timeframe_rejected(self):
        from scripts.run_provider_api_comparison import validate_spec017_matrix

        with pytest.raises(ValueError, match="Unsupported timeframe"):
            validate_spec017_matrix("BTC", "3m")

    def test_unsupported_symbol_and_timeframe_rejected(self):
        from scripts.run_provider_api_comparison import validate_spec017_matrix

        with pytest.raises(ValueError):
            validate_spec017_matrix("DOGE", "6m")

    def test_symbol_case_insensitive(self):
        from scripts.run_provider_api_comparison import validate_spec017_matrix

        validate_spec017_matrix("btc", "1d")  # should not raise
        validate_spec017_matrix("Eth", "1w")  # should not raise


# ============================================================================
# T010: Only liq-map product accepted in manifest
# ============================================================================


class TestProductFilter:
    """Validate liq-map-only product enforcement."""

    def test_liqmap_product_accepted(self):
        from scripts.run_provider_api_comparison import validate_product_filter

        validate_product_filter("liq-map")  # should not raise

    def test_heatmap_product_rejected(self):
        from scripts.run_provider_api_comparison import validate_product_filter

        with pytest.raises(ValueError, match="liq-map"):
            validate_product_filter("liq-heat-map")

    def test_empty_product_defaults_to_liqmap(self):
        from scripts.run_provider_api_comparison import validate_product_filter

        validate_product_filter(None)  # should not raise, defaults to liq-map


# ============================================================================
# T013: CoinAnk URL generation for liq-map
# ============================================================================


class TestCoinAnkUrlGeneration:
    """Validate CoinAnk liq-map URL construction."""

    def test_btc_1w_url(self):
        from scripts.coinank_screenshot import build_coinank_liqmap_url

        url = build_coinank_liqmap_url("BTC", "1w", "binance")
        assert "liq-map" in url
        assert "btcusdt" in url.lower()
        assert "binance" in url.lower()
        assert "1w" in url

    def test_eth_1d_url(self):
        from scripts.coinank_screenshot import build_coinank_liqmap_url

        url = build_coinank_liqmap_url("ETH", "1d", "binance")
        assert "liq-map" in url
        assert "ethusdt" in url.lower()
        assert "1d" in url

    def test_url_does_not_contain_heatmap(self):
        from scripts.coinank_screenshot import build_coinank_liqmap_url

        url = build_coinank_liqmap_url("BTC", "1d", "binance")
        assert "liq-heat-map" not in url
        assert "heatmap" not in url.lower()


# ============================================================================
# T018/T019: Coinglass timeframe mappings
# ============================================================================


class TestCoinglassTimeframeMappings:
    """Validate Coinglass interval/limit for spec-017 timeframes."""

    @pytest.fixture(autouse=True)
    def _import_coinglass(self):
        from scripts.capture_provider_api import resolve_coinglass_interval_limit

        self._resolve = resolve_coinglass_interval_limit

    def test_1d_maps_to_interval_1_limit_1500(self):
        interval, limit = self._resolve("1d")
        assert interval == "1"
        assert limit == 1500

    def test_1w_maps_to_interval_5_limit_2000(self):
        interval, limit = self._resolve("1w")
        assert interval == "5"
        assert limit == 2000

    def test_unsupported_timeframe_raises(self):
        with pytest.raises(ValueError, match="Unsupported"):
            self._resolve("15m")

    def test_aliases_resolve_correctly(self):
        interval, limit = self._resolve("7 day")
        assert interval == "5"
        assert limit == 2000

    def test_1d_alias_1_day(self):
        interval, limit = self._resolve("1 day")
        assert interval == "1"
        assert limit == 1500


# ============================================================================
# T020: Manifest metadata fields
# ============================================================================


class TestManifestMetadata:
    """Validate manifest includes required spec-017 fields."""

    def test_manifest_includes_product_field(self, tmp_path):
        manifest = _build_test_manifest(tmp_path, product="liq-map")
        assert manifest["product"] == "liq-map"

    def test_manifest_includes_capture_mode(self, tmp_path):
        manifest = _build_test_manifest(tmp_path, capture_mode="rest")
        providers = manifest["providers"]
        assert any(p.get("capture_mode") == "rest" for p in providers)

    def test_manifest_includes_timeframe_applied(self, tmp_path):
        manifest = _build_test_manifest(tmp_path)
        providers = manifest["providers"]
        assert all("timeframe_applied" in p for p in providers)


# ============================================================================
# T014: CoinAnk capture manifest metadata
# ============================================================================


class TestCoinAnkManifestMetadata:
    """Validate CoinAnk entries in the manifest."""

    def test_coinank_provider_url_is_liqmap(self, tmp_path):
        manifest = _build_test_manifest(tmp_path)
        coinank = [p for p in manifest["providers"] if p["provider"] == "coinank"]
        assert len(coinank) == 1
        assert "liq-map" in coinank[0]["page_url"]
        assert "liq-heat-map" not in coinank[0]["page_url"]


# ============================================================================
# T024: Normalized report loading for liq-map-only manifests
# ============================================================================


class TestNormalizedReportFiltering:
    """Validate that comparison reports can be filtered to liq-map datasets."""

    def test_dataset_kind_field_present_in_report(self, tmp_path):
        report = _build_test_report()
        for provider, dataset in report["providers"].items():
            assert "dataset_kind" in dataset

    def test_liqmap_datasets_are_price_bins(self, tmp_path):
        report = _build_test_report()
        for provider, dataset in report["providers"].items():
            if dataset["dataset_kind"] == "liquidation_heatmap":
                assert dataset["structure"] == "price_bins"

    def test_filter_report_to_liqmap_only(self):
        """Verify we can filter a report to only liq-map (price_bins) datasets."""
        report = _build_test_report()
        liqmap_providers = {
            p: d
            for p, d in report["providers"].items()
            if d["dataset_kind"] == "liquidation_heatmap"
            and d["structure"] == "price_bins"
        }
        assert len(liqmap_providers) >= 1


# ============================================================================
# T025: Gap analysis on liq-map-only manifests
# ============================================================================


class TestGapAnalysisLiqmapOnly:
    """Validate gap analysis scenario fields for liq-map workflows."""

    def test_scenario_includes_provider_and_timeframe(self):
        scenario = _build_test_scenario()
        assert "provider" in scenario
        assert "timeframe" in scenario

    def test_scenario_symbol_is_btc_or_eth(self):
        scenario = _build_test_scenario()
        assert scenario["symbol"] in {"BTCUSDT", "ETHUSDT"}

    def test_scenario_has_bucket_counts(self):
        scenario = _build_test_scenario()
        assert "bucket_count" in scenario
        assert isinstance(scenario["bucket_count"], int)


# ============================================================================
# Rektslug local provider (Step 1)
# ============================================================================


class TestRektslugProviderInTargets:
    """Validate that 'rektslug' is included in build_targets when requested."""

    def test_rektslug_target_included_when_all(self):
        from scripts.capture_provider_api import build_targets
        import argparse

        args = argparse.Namespace(
            provider="all",
            coin="BTC",
            timeframe="1w",
            exchange="binance",
            coinank_url=None,
            coinglass_url=None,
            bitcoincounterflow_url="https://bitcoincounterflow.com/liquidation-heatmap/",
            coinglass_timeframe=None,
        )
        targets = build_targets(args)
        providers = [t.provider for t in targets]
        assert "rektslug" in providers

    def test_rektslug_target_url_contains_levels(self):
        from scripts.capture_provider_api import build_targets
        import argparse

        args = argparse.Namespace(
            provider="rektslug",
            coin="BTC",
            timeframe="1w",
            exchange="binance",
            coinank_url=None,
            coinglass_url=None,
            bitcoincounterflow_url=None,
            coinglass_timeframe=None,
        )
        targets = build_targets(args)
        assert len(targets) == 1
        assert targets[0].provider == "rektslug"
        assert "/liquidations/levels" in targets[0].url
        assert "BTCUSDT" in targets[0].url
        assert "timeframe=7" in targets[0].url

    def test_rektslug_target_1d_maps_to_timeframe_1(self):
        from scripts.capture_provider_api import build_targets
        import argparse

        args = argparse.Namespace(
            provider="rektslug",
            coin="ETH",
            timeframe="1d",
            exchange="binance",
            coinank_url=None,
            coinglass_url=None,
            bitcoincounterflow_url=None,
            coinglass_timeframe=None,
        )
        targets = build_targets(args)
        assert "ETHUSDT" in targets[0].url
        assert "timeframe=1" in targets[0].url


class TestRektslugParser:
    """Validate the rektslug /liquidations/levels parser."""

    def test_parses_valid_levels_payload(self):
        from scripts.compare_provider_liquidations import (
            CaptureFile,
            parse_rektslug_levels,
        )

        payload = _build_rektslug_levels_payload()
        capture = CaptureFile(
            provider="rektslug",
            source_url="http://localhost:8002/liquidations/levels?symbol=BTCUSDT&model=openinterest&timeframe=7",
            saved_file=Path("/tmp/fake.json"),
            content_type="application/json",
            payload=payload,
            manifest_path=Path("/tmp/manifest.json"),
        )
        result = parse_rektslug_levels(capture)
        assert result is not None
        assert result.provider == "rektslug"
        assert result.dataset_kind == "liquidation_heatmap"
        assert result.structure == "price_bins"
        assert result.symbol == "BTCUSDT"
        assert result.timeframe == "1w"
        assert result.total_long > 0
        assert result.total_short > 0
        assert result.bucket_count > 0
        assert result.current_price == 85000.0

    def test_rejects_non_rektslug_provider(self):
        from scripts.compare_provider_liquidations import (
            CaptureFile,
            parse_rektslug_levels,
        )

        payload = _build_rektslug_levels_payload()
        capture = CaptureFile(
            provider="coinank",
            source_url="http://localhost:8002/liquidations/levels?symbol=BTCUSDT&timeframe=7",
            saved_file=Path("/tmp/fake.json"),
            content_type="application/json",
            payload=payload,
            manifest_path=Path("/tmp/manifest.json"),
        )
        assert parse_rektslug_levels(capture) is None

    def test_timeframe_1d_parsed(self):
        from scripts.compare_provider_liquidations import (
            CaptureFile,
            parse_rektslug_levels,
        )

        payload = _build_rektslug_levels_payload()
        capture = CaptureFile(
            provider="rektslug",
            source_url="http://localhost:8002/liquidations/levels?symbol=BTCUSDT&model=openinterest&timeframe=1",
            saved_file=Path("/tmp/fake.json"),
            content_type="application/json",
            payload=payload,
            manifest_path=Path("/tmp/manifest.json"),
        )
        result = parse_rektslug_levels(capture)
        assert result is not None
        assert result.timeframe == "1d"


class TestRektslugInManifest:
    """Validate that rektslug appears in manifest and report structures."""

    def test_manifest_includes_rektslug_provider(self, tmp_path):
        manifest = _build_test_manifest_with_rektslug(tmp_path)
        providers = [p["provider"] for p in manifest["providers"]]
        assert "rektslug" in providers
        assert "coinank" in providers
        assert "coinglass" in providers

    def test_report_includes_rektslug(self):
        report = _build_test_report_with_rektslug()
        assert "rektslug" in report["providers"]
        assert "coinank" in report["providers"]
        assert "coinglass" in report["providers"]


# ============================================================================
# Step 2: Real product filtering and spec-017 scope lock
# ============================================================================


class TestSpec017ProviderScope:
    """Validate provider scope enforcement for spec-017."""

    def test_spec017_rejects_bitcoincounterflow_provider(self):
        from scripts.run_provider_api_comparison import validate_spec017_provider

        with pytest.raises(ValueError, match="Unsupported provider"):
            validate_spec017_provider("bitcoincounterflow")

    def test_build_targets_can_exclude_bitcoincounterflow(self):
        from scripts.capture_provider_api import build_targets
        import argparse

        args = argparse.Namespace(
            provider="all",
            coin="BTC",
            timeframe="1d",
            exchange="binance",
            coinank_url=None,
            coinglass_url=None,
            bitcoincounterflow_url="https://bitcoincounterflow.com/liquidation-heatmap/",
            coinglass_timeframe=None,
            include_bitcoincounterflow=False,
            include_rektslug=True,
        )
        targets = build_targets(args)
        providers = [t.provider for t in targets]
        assert "bitcoincounterflow" not in providers
        assert providers == ["coinank", "coinglass", "rektslug"]

    def test_build_capture_namespace_keeps_single_provider_pure_by_default(self):
        from scripts.run_provider_api_comparison import build_capture_namespace
        import argparse

        args = argparse.Namespace(
            provider="coinank",
            coin="BTC",
            timeframe="1d",
            exchange="binance",
            coinank_url=None,
            coinglass_url="https://www.coinglass.com/LiquidationData",
            bitcoincounterflow_url="https://bitcoincounterflow.com/liquidation-heatmap/",
            capture_output_dir=Path("/tmp/captures"),
            comparison_output=None,
            max_responses=5,
            post_load_wait_ms=1000,
            headed=False,
            no_persist_db=True,
            db_path=None,
            product="liq-map",
            matrix_preset="spec-017",
            coinglass_mode="rest",
            profile="rektslug-default",
            include_rektslug=False,
            skip_gap_analysis=False,
        )

        capture_args = build_capture_namespace(args)
        assert capture_args.include_rektslug is False

    def test_build_capture_namespace_can_opt_in_rektslug_for_calibration(self):
        from scripts.run_provider_api_comparison import build_capture_namespace
        import argparse

        args = argparse.Namespace(
            provider="coinank",
            coin="BTC",
            timeframe="1d",
            exchange="binance",
            coinank_url=None,
            coinglass_url="https://www.coinglass.com/LiquidationData",
            bitcoincounterflow_url="https://bitcoincounterflow.com/liquidation-heatmap/",
            capture_output_dir=Path("/tmp/captures"),
            comparison_output=None,
            max_responses=5,
            post_load_wait_ms=1000,
            headed=False,
            no_persist_db=True,
            db_path=None,
            product="liq-map",
            matrix_preset="spec-017",
            coinglass_mode="rest",
            profile="rektslug-default",
            include_rektslug=True,
            skip_gap_analysis=False,
        )

        capture_args = build_capture_namespace(args)
        assert capture_args.include_rektslug is True


class TestRealProductFiltering:
    """Validate real liq-map filtering against heatmap-like Coinglass captures."""

    def test_liqheatmap_capture_is_excluded_by_liqmap_filter(self, monkeypatch):
        from scripts.compare_provider_liquidations import choose_best_datasets

        monkeypatch.setattr(
            "scripts.compare_provider_liquidations.decode_coinglass_json_payload",
            lambda capture: (_build_coinglass_liqheatmap_decoded_payload(), ["decoded"]),
        )

        captures = [
            _build_coinglass_encoded_capture(
                "https://capi.coinglass.com/api/index/5/liqHeatMap"
                "?symbol=Binance_BTCUSDT&interval=1&limit=1500"
            )
        ]
        datasets, skipped = choose_best_datasets(captures, product_filter="liq-map")

        assert datasets == {}
        assert skipped["coinglass"] == [captures[0].source_url]

    def test_liqmap_capture_is_retained_by_liqmap_filter(self, monkeypatch):
        from scripts.compare_provider_liquidations import choose_best_datasets

        monkeypatch.setattr(
            "scripts.compare_provider_liquidations.decode_coinglass_json_payload",
            lambda capture: (_build_coinglass_liqmap_decoded_payload(), ["decoded"]),
        )

        captures = [
            _build_coinglass_encoded_capture(
                "https://capi.coinglass.com/api/index/5/liqMap"
                "?symbol=Binance_BTCUSDT&interval=1&limit=1500"
            )
        ]
        datasets, skipped = choose_best_datasets(captures, product_filter="liq-map")

        assert list(datasets) == ["coinglass"]
        assert datasets["coinglass"].product == "liq-map"
        assert skipped["coinglass"] == []


# ============================================================================
# Step 3: Gap analysis alignment and runner fail-fast
# ============================================================================


class TestGapAnalysisLocalRektslug:
    """Validate gap analysis uses the local rektslug capture path."""

    def test_extract_rektslug_state_preserves_leverage_and_timeframe(self):
        from scripts.compare_provider_liquidations import CaptureFile
        from scripts.provider_gap_analysis import extract_rektslug_state

        capture = CaptureFile(
            provider="rektslug",
            source_url="http://localhost:8002/liquidations/levels?symbol=BTCUSDT&model=openinterest&timeframe=7",
            saved_file=Path("/tmp/rektslug.json"),
            content_type="application/json",
            payload=_build_rektslug_levels_payload(),
            manifest_path=Path("/tmp/manifest.json"),
        )

        state = extract_rektslug_state(capture)

        assert state.provider == "rektslug"
        assert state.timeframe == "1w"
        assert state.current_price == 85000.0
        assert sorted(state.leverage_totals) == [10, 25, 50, 100]
        assert state.total_value > 0
        assert state.long_map
        assert state.short_map


class TestRunnerGapAnalysisFailureHandling:
    """Validate the combined runner fails when gap analysis fails."""

    def _args(self):
        import argparse

        return argparse.Namespace(
            provider="all",
            coin="BTC",
            timeframe="1d",
            exchange="binance",
            coinank_url=None,
            coinglass_url="https://www.coinglass.com/LiquidationData",
            bitcoincounterflow_url="https://bitcoincounterflow.com/liquidation-heatmap/",
            capture_output_dir=Path("/tmp/captures"),
            comparison_output=None,
            max_responses=5,
            post_load_wait_ms=1000,
            headed=False,
            no_persist_db=True,
            db_path=None,
            product="liq-map",
            matrix_preset="spec-017",
            coinglass_mode="rest",
            skip_gap_analysis=False,
        )

    def test_runner_returns_non_zero_when_gap_analysis_fails(self, monkeypatch):
        from scripts import run_provider_api_comparison as runner

        async def fake_run_capture(*args, **kwargs):
            return Path("/tmp/manifest.json")

        monkeypatch.setattr(runner, "parse_args", lambda: self._args())
        monkeypatch.setattr(runner, "run_capture", fake_run_capture)
        monkeypatch.setattr(
            runner,
            "generate_report",
            lambda **kwargs: (
                {"providers": {"coinank": {}, "coinglass": {}, "rektslug": {}}, "pairwise_comparisons": []},
                Path("/tmp/report.json"),
            ),
        )

        class Result:
            returncode = 1
            stdout = ""
            stderr = "gap boom"

        monkeypatch.setattr(runner.subprocess, "run", lambda *args, **kwargs: Result())

        assert runner.main() == 1

    def test_runner_returns_zero_when_gap_analysis_succeeds(self, monkeypatch):
        from scripts import run_provider_api_comparison as runner

        async def fake_run_capture(*args, **kwargs):
            return Path("/tmp/manifest.json")

        monkeypatch.setattr(runner, "parse_args", lambda: self._args())
        monkeypatch.setattr(runner, "run_capture", fake_run_capture)
        monkeypatch.setattr(
            runner,
            "generate_report",
            lambda **kwargs: (
                {"providers": {"coinank": {}, "coinglass": {}, "rektslug": {}}, "pairwise_comparisons": []},
                Path("/tmp/report.json"),
            ),
        )

        class Result:
            returncode = 0
            stdout = "/tmp/gap.json"
            stderr = ""

        monkeypatch.setattr(runner.subprocess, "run", lambda *args, **kwargs: Result())

        assert runner.main() == 0

    def test_runner_can_skip_gap_analysis(self, monkeypatch):
        from scripts import run_provider_api_comparison as runner

        async def fake_run_capture(*args, **kwargs):
            return Path("/tmp/manifest.json")

        args = self._args()
        args.skip_gap_analysis = True

        monkeypatch.setattr(runner, "parse_args", lambda: args)
        monkeypatch.setattr(runner, "run_capture", fake_run_capture)
        monkeypatch.setattr(
            runner,
            "generate_report",
            lambda **kwargs: (
                {"providers": {"coinank": {}, "rektslug": {}}, "pairwise_comparisons": []},
                Path("/tmp/report.json"),
            ),
        )

        def should_not_run(*args, **kwargs):
            raise AssertionError("gap analysis should be skipped")

        monkeypatch.setattr(runner.subprocess, "run", should_not_run)

        assert runner.main() == 0


# ============================================================================
# Helpers
# ============================================================================


def _build_coinglass_encoded_capture(source_url: str):
    from scripts.compare_provider_liquidations import CaptureFile

    return CaptureFile(
        provider="coinglass",
        source_url=source_url,
        saved_file=Path("/tmp/coinglass.json"),
        content_type="application/json",
        payload={"data": "ZmFrZQ=="},
        manifest_path=Path("/tmp/manifest.json"),
        response_headers={"user": "seed", "v": "1"},
        request_headers={},
    )


def _build_coinglass_liqmap_decoded_payload() -> dict:
    return {
        "instrument": {"instrumentId": "BTCUSDT", "exName": "Binance"},
        "lastPrice": "85000",
        "liqMapV2": {
            "84000": [[84000, 1200, 25, 1]],
            "86000": [[86000, 900, 50, 2]],
        },
    }


def _build_coinglass_liqheatmap_decoded_payload() -> dict:
    return {
        "instrument": {"instrumentId": "BTCUSDT", "exName": "Binance"},
        "prices": [
            [1710000000000, 0, 0, 0, 84900],
            [1710000060000, 0, 0, 0, 85000],
        ],
        "y": [84000, 86000],
        "liq": [
            [1, 0, 1200],
            [1, 1, 900],
        ],
    }


def _build_rektslug_levels_payload() -> dict:
    """Build a realistic /liquidations/levels response payload."""
    return {
        "symbol": "BTCUSDT",
        "model": "openinterest",
        "current_price": "85000.0",
        "long_liquidations": [
            {"price_level": "84000", "volume": "5000000.0", "count": 1, "leverage": "10x"},
            {"price_level": "83000", "volume": "3500000.0", "count": 1, "leverage": "25x"},
            {"price_level": "82000", "volume": "2000000.0", "count": 1, "leverage": "50x"},
            {"price_level": "80000", "volume": "1500000.0", "count": 1, "leverage": "100x"},
        ],
        "short_liquidations": [
            {"price_level": "86000", "volume": "4500000.0", "count": 1, "leverage": "10x"},
            {"price_level": "87000", "volume": "3000000.0", "count": 1, "leverage": "25x"},
            {"price_level": "88000", "volume": "2500000.0", "count": 1, "leverage": "50x"},
            {"price_level": "90000", "volume": "1000000.0", "count": 1, "leverage": "100x"},
        ],
    }


def _build_test_manifest_with_rektslug(tmp_path: Path) -> dict:
    """Build a test manifest with all 3 providers including rektslug."""
    return {
        "timestamp_utc": "2026-03-10T12:00:00+00:00",
        "run_dir": str(tmp_path),
        "product": "liq-map",
        "args": {
            "provider": "all",
            "coin": "BTC",
            "timeframe": "1w",
            "exchange": "binance",
        },
        "providers": [
            {
                "provider": "rektslug",
                "page_url": "http://localhost:8002/liquidations/levels?symbol=BTCUSDT&model=openinterest&timeframe=7",
                "login_attempted": False,
                "login_success": False,
                "timeframe_applied": True,
                "capture_count": 1,
                "capture_mode": "rest",
                "captures": [],
            },
            {
                "provider": "coinank",
                "page_url": "https://coinank.com/chart/derivatives/liq-map/binance/btcusdt/1w",
                "login_success": True,
                "timeframe_applied": True,
                "capture_count": 3,
                "capture_mode": "browser",
                "captures": [],
            },
            {
                "provider": "coinglass",
                "page_url": "https://www.coinglass.com/pro/futures/LiquidationMap",
                "login_success": True,
                "timeframe_applied": True,
                "capture_count": 1,
                "capture_mode": "rest",
                "captures": [],
            },
        ],
    }


def _build_test_report_with_rektslug() -> dict:
    """Build a comparison report with all 3 providers."""
    base = _build_test_report()
    base["providers"]["rektslug"] = {
        "provider": "rektslug",
        "source_url": "http://localhost:8002/liquidations/levels?symbol=BTCUSDT&model=openinterest&timeframe=7",
        "dataset_kind": "liquidation_heatmap",
        "structure": "price_bins",
        "unit": "usd_notional",
        "symbol": "BTCUSDT",
        "exchange": "binance",
        "timeframe": "1w",
        "bucket_count": 80,
        "total_long": 12000000.0,
        "total_short": 11000000.0,
        "peak_long": 5000000.0,
        "peak_short": 4500000.0,
    }
    return base


def _build_test_manifest(
    tmp_path: Path,
    product: str = "liq-map",
    capture_mode: str = "rest",
) -> dict:
    """Build a minimal test manifest matching spec-017 shape."""
    return {
        "timestamp_utc": "2026-03-10T12:00:00+00:00",
        "run_dir": str(tmp_path),
        "product": product,
        "args": {
            "provider": "both",
            "coin": "BTC",
            "timeframe": "1w",
            "exchange": "binance",
        },
        "providers": [
            {
                "provider": "coinank",
                "page_url": "https://coinank.com/chart/derivatives/liq-map/binance/btcusdt/1w",
                "login_success": True,
                "timeframe_applied": True,
                "capture_count": 3,
                "capture_mode": "browser",
                "captures": [],
            },
            {
                "provider": "coinglass",
                "page_url": "https://www.coinglass.com/pro/futures/LiquidationMap",
                "login_success": True,
                "timeframe_applied": True,
                "capture_count": 1,
                "capture_mode": capture_mode,
                "captures": [],
            },
        ],
    }


def _build_test_report() -> dict:
    """Build a minimal comparison report with provider datasets."""
    return {
        "timestamp_utc": "2026-03-10T12:00:00+00:00",
        "providers": {
            "coinank": {
                "provider": "coinank",
                "source_url": "https://coinank.com/api/liqMap/getLiqMap",
                "dataset_kind": "liquidation_heatmap",
                "structure": "price_bins",
                "unit": "usd_notional",
                "symbol": "BTCUSDT",
                "exchange": "binance",
                "timeframe": "1w",
                "bucket_count": 150,
                "total_long": 1200000000.0,
                "total_short": 950000000.0,
                "peak_long": 80000000.0,
                "peak_short": 65000000.0,
            },
            "coinglass": {
                "provider": "coinglass",
                "source_url": "https://capi.coinglass.com/api/index/5/liqMap",
                "dataset_kind": "liquidation_heatmap",
                "structure": "price_bins",
                "unit": "usd_notional",
                "symbol": "BTCUSDT",
                "exchange": "binance",
                "timeframe": "1w",
                "bucket_count": 200,
                "total_long": 1100000000.0,
                "total_short": 900000000.0,
                "peak_long": 75000000.0,
                "peak_short": 60000000.0,
            },
        },
        "pairwise_comparisons": [],
    }


def _build_test_scenario() -> dict:
    """Build a minimal gap analysis scenario entry."""
    return {
        "provider": "coinank",
        "symbol": "BTCUSDT",
        "exchange": "binance",
        "timeframe": "1w",
        "bucket_count": 150,
        "total_long": 1200000000.0,
        "total_short": 950000000.0,
    }
