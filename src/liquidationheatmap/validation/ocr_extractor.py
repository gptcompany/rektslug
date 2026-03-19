"""OCR-based price level extraction from Coinglass heatmap screenshots.

Uses Pytesseract (primary) with EasyOCR fallback for extracting
price levels from the Y-axis of heatmap screenshots.
"""

import re
import time
from dataclasses import dataclass, field
from typing import Any

try:
    import cv2
    import numpy as np
except (ImportError, AttributeError):
    cv2 = None
    np = None  # type: ignore

import pytesseract


def _require_image_dependencies() -> None:
    """Raise a clear error when OpenCV/numpy-backed OCR preprocessing is unavailable."""

    missing = []
    if cv2 is None:
        missing.append("opencv-python")
    if np is None:
        missing.append("numpy")
    if missing:
        missing_list = ", ".join(missing)
        raise RuntimeError(
            f"OCR image preprocessing requires {missing_list} to be installed"
        )


@dataclass
class ExtractedPriceLevels:
    """Price levels extracted via OCR from screenshot."""

    screenshot_path: str
    long_zones: list[float] = field(default_factory=list)  # Prices below current
    short_zones: list[float] = field(default_factory=list)  # Prices above current
    current_price: float | None = None  # From API (authoritative)
    confidence: float = 0.0  # OCR confidence (0-1), min across extractions
    extraction_method: str = "pytesseract"
    processing_time_ms: int = 0
    raw_text: str = ""  # Raw OCR output for debugging

    @property
    def all_zones(self) -> list[float]:
        """All extracted price levels."""
        return sorted(set(self.long_zones + self.short_zones))

    @property
    def is_valid(self) -> bool:
        """Check if extraction produced usable results."""
        return len(self.all_zones) >= 2 and self.confidence >= 0.5

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "screenshot_path": self.screenshot_path,
            "long_zones": self.long_zones,
            "short_zones": self.short_zones,
            "current_price": self.current_price,
            "confidence": self.confidence,
            "extraction_method": self.extraction_method,
            "processing_time_ms": self.processing_time_ms,
            "is_valid": self.is_valid,
        }


class OCRExtractor:
    """Extract price levels from Coinglass heatmap screenshots using OCR."""

    # Price ranges for filtering noise
    PRICE_RANGES = {
        "BTC": (20000, 250000),
        "ETH": (1000, 15000),
    }

    # Default crop region for Y-axis (RIGHT side of image - Coinglass layout)
    Y_AXIS_CROP_WIDTH = 610  # pixels from right edge (covers price labels area)

    # Tesseract config for sparse text (price labels)
    TESSERACT_CONFIG = "--psm 11"  # Sparse text mode works best for price labels

    def __init__(
        self,
        confidence_threshold: float = 0.7,
        use_easyocr_fallback: bool = True,
    ):
        """Initialize OCR extractor.

        Args:
            confidence_threshold: Minimum confidence to use pytesseract result
            use_easyocr_fallback: Whether to fall back to EasyOCR on low confidence
        """
        self.confidence_threshold = confidence_threshold
        self.use_easyocr_fallback = use_easyocr_fallback
        self._easyocr_reader = None  # Lazy load

    def _preprocess_image(self, image_path: str) -> Any:
        """Preprocess image for OCR.

        Steps:
        1. Load image
        2. Crop to Y-axis region (left side)
        3. Convert to grayscale
        4. Apply adaptive thresholding
        """
        _require_image_dependencies()

        # Load image
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Could not load image: {image_path}")

        # Crop to Y-axis region (RIGHT side for Coinglass screenshots)
        height, width = img.shape[:2]
        y_axis_crop = img[:, width - self.Y_AXIS_CROP_WIDTH :]

        # Convert to grayscale - don't apply thresholding as it hurts accuracy
        gray = cv2.cvtColor(y_axis_crop, cv2.COLOR_BGR2GRAY)

        return gray

    def _extract_with_pytesseract(self, preprocessed_img: Any) -> tuple[str, float]:
        """Extract text using Pytesseract.

        Args:
            preprocessed_img: Preprocessed grayscale image

        Returns:
            Tuple of (extracted_text, confidence_score)
        """
        # Get detailed OCR data with sparse text config
        data = pytesseract.image_to_data(
            preprocessed_img,
            output_type=pytesseract.Output.DICT,
            config=self.TESSERACT_CONFIG,
        )

        # Calculate average confidence (excluding -1 which means no text)
        confidences = [c for c in data["conf"] if c > 0]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0
        avg_confidence /= 100  # Convert to 0-1 range

        # Get all text with sparse text config
        text = pytesseract.image_to_string(preprocessed_img, config=self.TESSERACT_CONFIG)

        return text, avg_confidence

    def _extract_with_easyocr(self, image_path: str) -> tuple[str, float]:
        """Extract text using EasyOCR (fallback).

        Args:
            image_path: Path to original image

        Returns:
            Tuple of (extracted_text, confidence_score)
        """
        _require_image_dependencies()

        if self._easyocr_reader is None:
            import easyocr

            self._easyocr_reader = easyocr.Reader(["en"], gpu=False)

        # Load and crop image for EasyOCR (RIGHT side)
        img = cv2.imread(image_path)
        if img is None:
            return "", 0.0
        height, width = img.shape[:2]
        y_axis_crop = img[:, width - self.Y_AXIS_CROP_WIDTH :]

        # Run OCR
        results = self._easyocr_reader.readtext(y_axis_crop)

        if not results:
            return "", 0.0

        # Combine text and calculate average confidence
        texts = [r[1] for r in results]
        confidences = [r[2] for r in results]

        combined_text = "\n".join(texts)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0

        return combined_text, avg_confidence

    def _parse_price_levels(self, text: str, symbol: str = "BTC") -> list[float]:
        """Parse price levels from OCR text.

        Args:
            text: Raw OCR text output
            symbol: Cryptocurrency symbol for price range filtering

        Returns:
            List of valid price levels
        """
        # Find all numbers - support both formatted (130,000) and unformatted (130000)
        # Pattern matches: integers (130000), comma-separated (130,000), decimal (130000.50)
        # BUG FIX: Include optional comma separators in pattern
        pattern = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{4,7}(?:\.\d+)?)"
        # First alternative: comma-separated (e.g., 130,000 or 1,234,567)
        # Second alternative: 4-7 digit numbers without commas
        matches = re.findall(pattern, text)

        prices = []
        min_price, max_price = self.PRICE_RANGES.get(symbol, (0, float("inf")))

        for match in matches:
            # Clean the number
            clean = match.replace(",", "").replace(" ", "")
            try:
                price = float(clean)
                # Filter by realistic price range
                if min_price <= price <= max_price:
                    prices.append(price)
            except ValueError:
                continue

        return sorted(set(prices))

    def extract(
        self,
        image_path: str,
        symbol: str = "BTC",
        current_price: float | None = None,
    ) -> ExtractedPriceLevels:
        """Extract price levels from screenshot.

        Args:
            image_path: Path to Coinglass screenshot
            symbol: "BTC" or "ETH" for price range filtering
            current_price: Current price from API (for zone classification)

        Returns:
            ExtractedPriceLevels with extracted data
        """
        start_time = time.time()

        try:
            # Preprocess image
            preprocessed = self._preprocess_image(image_path)

            # Check for standalone "No Data" message in full image
            # (Coinglass shows this when no heatmap data available)
            # Note: All screenshots have a tip saying "If the message 'NO DATA' appears..."
            # We need to detect the ACTUAL "No data" message, not the tip
            full_img = cv2.imread(image_path)
            if full_img is not None:
                full_text = pytesseract.image_to_string(full_img, config="--psm 11")
                lines = full_text.split("\n")
                # Check for standalone "No data" line (not part of the tip)
                has_standalone_nodata = any(
                    line.strip().lower() in ["no data", "nodata"] for line in lines
                )
                if has_standalone_nodata:
                    return ExtractedPriceLevels(
                        screenshot_path=image_path,
                        confidence=0.0,  # Mark as invalid
                        extraction_method="pytesseract",
                        processing_time_ms=int((time.time() - start_time) * 1000),
                        raw_text="Screenshot shows 'No Data' - no heatmap data available",
                    )

            # Try pytesseract first on preprocessed (cropped) image
            text, confidence = self._extract_with_pytesseract(preprocessed)
            extraction_method = "pytesseract"

            # Fallback to EasyOCR if confidence is low
            if confidence < self.confidence_threshold and self.use_easyocr_fallback:
                try:
                    easyocr_text, easyocr_conf = self._extract_with_easyocr(image_path)
                    if easyocr_conf > confidence:
                        text = easyocr_text
                        confidence = easyocr_conf
                        extraction_method = "easyocr"
                except Exception:
                    pass  # Stick with pytesseract result

            # Parse price levels
            all_prices = self._parse_price_levels(text, symbol)

            # Classify into long/short zones if current price is known
            long_zones = []
            short_zones = []

            if current_price is not None and all_prices:
                long_zones = [p for p in all_prices if p < current_price]
                short_zones = [p for p in all_prices if p > current_price]
            else:
                # Without current price, can't classify
                # Put all in short_zones as placeholder (will be classified later)
                short_zones = all_prices

            processing_time_ms = int((time.time() - start_time) * 1000)

            return ExtractedPriceLevels(
                screenshot_path=image_path,
                long_zones=long_zones,
                short_zones=short_zones,
                current_price=current_price,
                confidence=confidence,
                extraction_method=extraction_method,
                processing_time_ms=processing_time_ms,
                raw_text=text,
            )

        except Exception as e:
            processing_time_ms = int((time.time() - start_time) * 1000)
            return ExtractedPriceLevels(
                screenshot_path=image_path,
                confidence=0.0,
                processing_time_ms=processing_time_ms,
                raw_text=f"Error: {e}",
            )
