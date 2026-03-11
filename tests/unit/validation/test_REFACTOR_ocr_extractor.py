"""Unit tests for REFACTORED OCR extractor."""

import pytest
from unittest.mock import MagicMock
from src.liquidationheatmap.validation.REFACTOR_ocr_extractor import (
    OCRExtractor, 
    OCREngine, 
    ImageProcessor,
    ExtractedPriceLevels
)

class TestREFACTOROCRExtractor:
    def test_parse_price_levels_logic(self):
        """Should extract numbers from messy OCR text."""
        text = "Price: 130,000.50 \n 45000 \n Not a number \n 200,000"
        prices = OCRExtractor.parse_price_levels(text, symbol="BTC")
        
        assert 130000.5 in prices
        assert 45000.0 in prices
        assert 200000.0 in prices
        assert len(prices) == 3

    def test_classify_zones_logic(self):
        """Should split prices correctly relative to current price."""
        prices = [40000.0, 50000.0, 60000.0]
        current = 45000.0
        
        longs, shorts = OCRExtractor.classify_zones(prices, current)
        assert longs == [40000.0]
        assert shorts == [50000.0, 60000.0]

    def test_extract_flow_success(self):
        """Coordinated success flow with primary engine."""
        mock_engine = MagicMock(spec=OCREngine)
        mock_engine.extract_text.return_value = ("70,000\n75,000", 0.9)
        
        mock_proc = MagicMock(spec=ImageProcessor)
        mock_proc.load_and_crop.return_value = "dummy_img"
        mock_proc.check_no_data.return_value = False
        
        extractor = OCRExtractor(primary_engine=mock_engine, image_processor=mock_proc)
        result = extractor.extract("path/to/img.png", symbol="BTC", current_price=72000.0)
        
        assert result.confidence == 0.9
        assert result.long_zones == [70000.0]
        assert result.short_zones == [75000.0]
        assert result.extraction_method == "primary"

    def test_extract_flow_fallback(self):
        """Should use fallback engine if primary confidence is low."""
        mock_primary = MagicMock(spec=OCREngine)
        mock_primary.extract_text.return_value = ("low", 0.3)
        
        mock_fallback = MagicMock(spec=OCREngine)
        mock_fallback.extract_text.return_value = ("high", 0.8)
        
        mock_proc = MagicMock(spec=ImageProcessor)
        mock_proc.load_and_crop.return_value = "img"
        mock_proc.check_no_data.return_value = False
        
        extractor = OCRExtractor(
            primary_engine=mock_primary, 
            fallback_engine=mock_fallback,
            image_processor=mock_proc,
            confidence_threshold=0.7
        )
        
        result = extractor.extract("path")
        assert result.extraction_method == "fallback"
        assert result.confidence == 0.8

    def test_extract_no_data_detection(self):
        """Should return empty result if image processor detects 'No Data'."""
        mock_proc = MagicMock(spec=ImageProcessor)
        mock_proc.check_no_data.return_value = True
        
        extractor = OCRExtractor(primary_engine=MagicMock(), image_processor=mock_proc)
        result = extractor.extract("path")
        
        assert "No Data" in result.raw_text
        assert result.confidence == 0.0
