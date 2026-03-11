"""Tests for scripts/calculate_liquidations.py."""

import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from scripts.calculate_liquidations import main

class TestCalculateLiquidations:
    @patch("scripts.calculate_liquidations.DuckDBService")
    @patch("scripts.calculate_liquidations.BinanceStandardModel")
    def test_main_success(self, mock_model_cls, mock_db_cls, monkeypatch):
        """Should calculate and store liquidations successfully."""
        # Mock DB
        mock_db = MagicMock()
        mock_db_cls.return_value.__enter__.return_value = mock_db
        mock_db.get_latest_open_interest.return_value = (Decimal("50000.0"), Decimal("1000000.0"))
        mock_db.get_latest_funding_rate.return_value = Decimal("0.0001")
        
        # Mock Model
        mock_model = MagicMock()
        mock_model_cls.return_value = mock_model
        mock_model.model_name = "binance_standard"
        mock_model.confidence_score.return_value = 0.95
        
        mock_liq = MagicMock()
        mock_liq.timestamp = "2024-01-01T00:00:00"
        mock_liq.symbol = "BTCUSDT"
        mock_liq.price_level = Decimal("45000.0")
        mock_liq.liquidation_volume = Decimal("100000.0")
        mock_liq.leverage_tier = "10x"
        mock_liq.side = "long"
        mock_liq.confidence = Decimal("0.95")
        
        mock_model.calculate_liquidations.return_value = [mock_liq]
        
        # Run main
        monkeypatch.setattr(sys, "argv", ["calculate_liquidations.py", "--symbol", "BTCUSDT"])
        main()
        
        assert mock_model.calculate_liquidations.called
        assert mock_db.conn.execute.called

    @patch("scripts.calculate_liquidations.DuckDBService")
    @patch("scripts.calculate_liquidations.EnsembleModel")
    def test_main_ensemble(self, mock_model_cls, mock_db_cls, monkeypatch):
        """Should use EnsembleModel when requested."""
        mock_db = MagicMock()
        mock_db_cls.return_value.__enter__.return_value = mock_db
        mock_db.get_latest_open_interest.return_value = (Decimal("50000.0"), Decimal("1000000.0"))
        mock_db.get_latest_funding_rate.return_value = Decimal("0.0001")
        
        mock_model = MagicMock()
        mock_model_cls.return_value = mock_model
        mock_model.model_name = "ensemble"
        mock_model.confidence_score.return_value = 0.98
        mock_model.calculate_liquidations.return_value = []
        
        monkeypatch.setattr(sys, "argv", ["calculate_liquidations.py", "--model", "ensemble"])
        main()
        
        assert mock_model_cls.called

    @patch("scripts.calculate_liquidations.DuckDBService")
    @patch("scripts.calculate_liquidations.FundingAdjustedModel")
    def test_main_funding_adjusted(self, mock_model_cls, mock_db_cls, monkeypatch):
        """Should use FundingAdjustedModel when requested."""
        mock_db = MagicMock()
        mock_db_cls.return_value.__enter__.return_value = mock_db
        mock_db.get_latest_open_interest.return_value = (Decimal("50000.0"), Decimal("1000000.0"))
        
        mock_model = MagicMock()
        mock_model_cls.return_value = mock_model
        mock_model.model_name = "funding_adjusted"
        mock_model.confidence_score.return_value = 0.96
        mock_model.calculate_liquidations.return_value = []
        
        monkeypatch.setattr(sys, "argv", ["calculate_liquidations.py", "--model", "funding_adjusted", "--funding-rate", "0.0002"])
        main()
        
        assert mock_model_cls.called
        mock_model.calculate_liquidations.assert_called_with(
            current_price=Decimal("50000.0"),
            open_interest=Decimal("1000000.0"),
            symbol="BTCUSDT",
            leverage_tiers=[5, 10, 25, 50, 100],
            funding_rate=Decimal("0.0002")
        )
