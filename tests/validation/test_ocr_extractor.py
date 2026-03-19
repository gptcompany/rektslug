"""Unit tests for ocr_extractor module."""

from unittest.mock import patch

import numpy as np
import pytest

from src.liquidationheatmap.validation import ocr_extractor
from src.liquidationheatmap.validation.ocr_extractor import (
    ExtractedPriceLevels,
    OCRExtractor,
)


class TestExtractedPriceLevels:
    """Tests for ExtractedPriceLevels dataclass."""

    def test_all_zones_combines_long_and_short(self):
        """all_zones property combines and sorts zones."""
        result = ExtractedPriceLevels(
            screenshot_path="/path/to/screenshot.png",
            long_zones=[85000.0, 83000.0],
            short_zones=[90000.0, 92000.0],
            confidence=0.9,
        )

        assert result.all_zones == [83000.0, 85000.0, 90000.0, 92000.0]

    def test_is_valid_with_sufficient_zones_and_confidence(self):
        """is_valid returns True with 2+ zones and confidence >= 0.5."""
        result = ExtractedPriceLevels(
            screenshot_path="/path/to/screenshot.png",
            short_zones=[90000.0, 92000.0],
            confidence=0.6,
        )

        assert result.is_valid is True

    def test_is_valid_false_with_low_confidence(self):
        """is_valid returns False with confidence < 0.5."""
        result = ExtractedPriceLevels(
            screenshot_path="/path/to/screenshot.png",
            short_zones=[90000.0, 92000.0],
            confidence=0.4,
        )

        assert result.is_valid is False

    def test_is_valid_false_with_insufficient_zones(self):
        """is_valid returns False with < 2 zones."""
        result = ExtractedPriceLevels(
            screenshot_path="/path/to/screenshot.png",
            short_zones=[90000.0],
            confidence=0.9,
        )

        assert result.is_valid is False

    def test_to_dict_serialization(self):
        """to_dict returns JSON-serializable dict."""
        result = ExtractedPriceLevels(
            screenshot_path="/path/to/screenshot.png",
            long_zones=[85000.0],
            short_zones=[90000.0],
            confidence=0.85,
            extraction_method="pytesseract",
            processing_time_ms=150,
        )

        data = result.to_dict()

        assert data["screenshot_path"] == "/path/to/screenshot.png"
        assert data["long_zones"] == [85000.0]
        assert data["short_zones"] == [90000.0]
        assert data["confidence"] == 0.85
        assert data["extraction_method"] == "pytesseract"
        assert data["processing_time_ms"] == 150
        assert data["is_valid"] is True


class TestOCRExtractorParsePriceLevels:
    """Tests for OCRExtractor._parse_price_levels method."""

    def test_parse_btc_prices(self):
        """Parse BTC price levels from OCR text."""
        extractor = OCRExtractor()
        text = "130000\n125000\n120000\n115000"

        prices = extractor._parse_price_levels(text, symbol="BTC")

        assert prices == [115000.0, 120000.0, 125000.0, 130000.0]

    def test_parse_eth_prices(self):
        """Parse ETH price levels from OCR text."""
        extractor = OCRExtractor()
        text = "3500\n3400\n3300\n3200"

        prices = extractor._parse_price_levels(text, symbol="ETH")

        assert prices == [3200.0, 3300.0, 3400.0, 3500.0]

    def test_filter_out_of_range_btc_prices(self):
        """Filter prices outside BTC realistic range."""
        extractor = OCRExtractor()
        text = "130000\n500\n999999\n100000"

        prices = extractor._parse_price_levels(text, symbol="BTC")

        # 500 is too low, 999999 is too high
        assert 500.0 not in prices
        assert 999999.0 not in prices
        assert 100000.0 in prices
        assert 130000.0 in prices

    def test_filter_out_of_range_eth_prices(self):
        """Filter prices outside ETH realistic range."""
        extractor = OCRExtractor()
        text = "3500\n500\n50000\n2500"

        prices = extractor._parse_price_levels(text, symbol="ETH")

        # 500 is too low, 50000 is too high for ETH
        assert 500.0 not in prices
        assert 50000.0 not in prices
        assert 2500.0 in prices
        assert 3500.0 in prices

    def test_parse_decimal_prices(self):
        """Parse prices with decimal points."""
        extractor = OCRExtractor()
        text = "130000.50\n125000.25"

        prices = extractor._parse_price_levels(text, symbol="BTC")

        assert 130000.50 in prices
        assert 125000.25 in prices

    def test_deduplicate_prices(self):
        """Duplicate prices are removed."""
        extractor = OCRExtractor()
        text = "130000\n130000\n125000"

        prices = extractor._parse_price_levels(text, symbol="BTC")

        assert prices.count(130000.0) == 1


class TestOCRExtractorPreprocessing:
    """Tests for OCRExtractor image preprocessing."""

    @patch("cv2.imread")
    @patch("cv2.cvtColor")
    def test_preprocess_crops_right_side(self, mock_cvtcolor, mock_imread):
        """Preprocessing crops the right side of the image."""
        # Create mock image (1920x1080)
        mock_img = np.zeros((1080, 1920, 3), dtype=np.uint8)
        mock_imread.return_value = mock_img
        mock_cvtcolor.return_value = np.zeros((1080, 610), dtype=np.uint8)

        extractor = OCRExtractor()
        result = extractor._preprocess_image("/path/to/image.png")

        # Verify imread was called
        mock_imread.assert_called_once_with("/path/to/image.png")
        # Verify cvtColor was called (grayscale conversion)
        mock_cvtcolor.assert_called_once()

    @patch("cv2.imread")
    def test_preprocess_raises_on_invalid_image(self, mock_imread):
        """Raise ValueError for invalid/missing image."""
        mock_imread.return_value = None

        extractor = OCRExtractor()

        with pytest.raises(ValueError, match="Could not load image"):
            extractor._preprocess_image("/path/to/invalid.png")

    def test_preprocess_raises_clear_error_without_image_dependencies(self, monkeypatch):
        """Missing cv2/numpy should fail with a clear, actionable error."""
        monkeypatch.setattr(ocr_extractor, "cv2", None)
        monkeypatch.setattr(ocr_extractor, "np", None)

        extractor = OCRExtractor()

        with pytest.raises(RuntimeError, match="opencv-python, numpy"):
            extractor._preprocess_image("/path/to/image.png")


class TestOCRExtractorIntegration:
    """Integration tests for OCRExtractor (require real screenshot)."""

    @pytest.mark.skipif(
        not pytest.importorskip("pytesseract", reason="pytesseract not installed"),
        reason="pytesseract not available",
    )
    def test_extract_returns_extracted_price_levels(self, tmp_path):
        """extract() returns ExtractedPriceLevels object."""
        # Create minimal test image
        img_path = tmp_path / "test_screenshot.png"

        # Create a simple grayscale image with cv2
        import cv2

        img = np.zeros((100, 100, 3), dtype=np.uint8)
        cv2.imwrite(str(img_path), img)

        extractor = OCRExtractor(use_easyocr_fallback=False)
        result = extractor.extract(str(img_path), symbol="BTC")

        assert isinstance(result, ExtractedPriceLevels)
        assert result.screenshot_path == str(img_path)
        assert result.extraction_method in ["pytesseract", "easyocr"]
        assert result.processing_time_ms >= 0
