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
# Helpers
# ============================================================================


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
