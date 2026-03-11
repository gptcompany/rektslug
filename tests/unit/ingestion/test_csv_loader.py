"""Unit tests for CSV loader utilities."""

import pandas as pd
import pytest
from src.liquidationheatmap.ingestion.csv_loader import (
    load_open_interest_csv,
    load_funding_rate_csv,
    load_aggtrades_csv,
    load_csv_glob,
)

class TestCSVLoader:
    def test_load_open_interest_csv_success(self, tmp_path):
        """Should load OI CSV successfully."""
        csv_file = tmp_path / "BTCUSDT-metrics-2024-01-01.csv"
        csv_file.write_text("timestamp,symbol,sumOpenInterest,sumOpenInterestValue,countTopTraderLongShortRatio\n1704067200000,BTCUSDT,100.0,4200000.0,1.5")
        
        df = load_open_interest_csv(str(csv_file))
        assert not df.empty
        assert "open_interest_value" in df.columns
        assert df.iloc[0]["symbol"] == "BTCUSDT"

    def test_load_open_interest_csv_missing_file(self):
        """Should raise FileNotFoundError if file missing."""
        with pytest.raises(FileNotFoundError):
            load_open_interest_csv("nonexistent.csv")

    def test_load_funding_rate_csv_success(self, tmp_path):
        """Should load Funding Rate CSV successfully."""
        csv_file = tmp_path / "BTCUSDT-fundingRate-2024-01-01.csv"
        csv_file.write_text("timestamp,symbol,fundingRate,markPrice\n1704067200000,BTCUSDT,0.0001,42000.0")
        
        df = load_funding_rate_csv(str(csv_file))
        assert not df.empty
        assert "funding_rate" in df.columns
        assert df.iloc[0]["funding_rate"] == 0.0001

    def test_load_aggtrades_csv_success_header(self, tmp_path):
        """Should load aggTrades CSV with header."""
        csv_file = tmp_path / "BTCUSDT-aggTrades-2024-01-01.csv"
        csv_file.write_text("agg_trade_id,price,quantity,first_trade_id,last_trade_id,transact_time,is_buyer_maker\n1,42000.0,0.1,1,1,1704067200000,true")
        
        df = load_aggtrades_csv(str(csv_file))
        assert not df.empty
        assert "side" in df.columns
        assert df.iloc[0]["side"] == "sell"

    def test_load_aggtrades_csv_no_header(self, tmp_path):
        """Should load aggTrades CSV without header."""
        csv_file = tmp_path / "BTCUSDT-aggTrades-2024-01-01.csv"
        # Old format: agg_trade_id, price, quantity, first_trade_id, last_trade_id, transact_time, is_buyer_maker
        csv_file.write_text("1,42000.0,0.1,1,1,1704067200000,true")
        
        df = load_aggtrades_csv(str(csv_file))
        assert not df.empty
        assert df.iloc[0]["side"] == "sell"

    def test_load_csv_glob_success(self, tmp_path):
        """Should load multiple files using glob."""
        for i in range(2):
            csv_file = tmp_path / f"BTCUSDT-metrics-2024-01-0{i+1}.csv"
            csv_file.write_text(f"timestamp,symbol,sumOpenInterest,sumOpenInterestValue,countTopTraderLongShortRatio\n{1704067200000 + i*86400000},BTCUSDT,100.0,4200000.0,1.5")
            
        df = load_csv_glob(str(tmp_path / "*.csv"), loader_func=load_open_interest_csv)
        assert len(df) == 2

    def test_load_csv_glob_no_files(self, tmp_path):
        """Should raise FileNotFoundError if no files match."""
        with pytest.raises(FileNotFoundError):
            load_csv_glob(str(tmp_path / "nonexistent*.csv"))
            
    def test_load_open_interest_empty_file(self, tmp_path):
        """Should raise ValueError for empty file."""
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("")
        with pytest.raises(ValueError):
            load_open_interest_csv(str(csv_file))
