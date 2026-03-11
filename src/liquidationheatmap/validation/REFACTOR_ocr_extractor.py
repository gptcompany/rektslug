"""REFACTORED OCR-based price level extraction from Coinglass heatmap screenshots.

Implements structural refactoring for 100% testability:
1. Interface for OCR engines (Dependency Injection)
2. Decoupled image processing (Abstracted IO)
3. Pure logic extraction for price parsing and classification
"""

import re
import time
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Protocol, Tuple, Any

logger = logging.getLogger(__name__)

@dataclass
class ExtractedPriceLevels:
    """Price levels extracted via OCR from screenshot."""
    screenshot_path: str
    long_zones: List[float] = field(default_factory=list)
    short_zones: List[float] = field(default_factory=list)
    current_price: Optional[float] = None
    confidence: float = 0.0
    extraction_method: str = "mock"
    processing_time_ms: int = 0
    raw_text: str = ""

    @property
    def all_zones(self) -> List[float]:
        return sorted(set(self.long_zones + self.short_zones))

    @property
    def is_valid(self) -> bool:
        return len(self.all_zones) >= 2 and self.confidence >= 0.5

class OCREngine(Protocol):
    """Protocol for OCR engines like Tesseract or EasyOCR."""
    def extract_text(self, image: Any) -> Tuple[str, float]: ...

class ImageProcessor(Protocol):
    """Protocol for image loading and preprocessing."""
    def load_and_crop(self, path: str, crop_width: int) -> Any: ...
    def check_no_data(self, image: Any) -> bool: ...

class OCRExtractor:
    """Extract price levels with swappable components for testing."""

    PRICE_RANGES = {
        "BTC": (20000, 250000),
        "ETH": (1000, 15000),
    }
    Y_AXIS_CROP_WIDTH = 610

    def __init__(
        self,
        primary_engine: OCREngine,
        fallback_engine: Optional[OCREngine] = None,
        image_processor: Optional[ImageProcessor] = None,
        confidence_threshold: float = 0.7,
    ):
        self.primary_engine = primary_engine
        self.fallback_engine = fallback_engine
        self.image_processor = image_processor
        self.confidence_threshold = confidence_threshold

    def extract(
        self,
        image_path: str,
        symbol: str = "BTC",
        current_price: Optional[float] = None,
    ) -> ExtractedPriceLevels:
        """Coordinated extraction flow."""
        start_time = time.time()
        
        if not self.image_processor:
            return self._error_result(image_path, "No image processor", start_time)

        try:
            # 1. Load and check
            img = self.image_processor.load_and_crop(image_path, self.Y_AXIS_CROP_WIDTH)
            if self.image_processor.check_no_data(img):
                return self._no_data_result(image_path, start_time)

            # 2. Extract Text
            text, confidence = self.primary_engine.extract_text(img)
            method = "primary"

            if confidence < self.confidence_threshold and self.fallback_engine:
                f_text, f_conf = self.fallback_engine.extract_text(img)
                if f_conf > confidence:
                    text, confidence, method = f_text, f_conf, "fallback"

            # 3. Parse and Classify (Pure Logic)
            prices = self.parse_price_levels(text, symbol)
            longs, shorts = self.classify_zones(prices, current_price)

            return ExtractedPriceLevels(
                screenshot_path=image_path,
                long_zones=longs,
                short_zones=shorts,
                current_price=current_price,
                confidence=confidence,
                extraction_method=method,
                processing_time_ms=int((time.time() - start_time) * 1000),
                raw_text=text
            )

        except Exception as e:
            return self._error_result(image_path, str(e), start_time)

    @classmethod
    def parse_price_levels(cls, text: str, symbol: str = "BTC") -> List[float]:
        """PURE LOGIC: Regex parsing of prices from OCR string."""
        pattern = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{4,7}(?:\.\d+)?)"
        matches = re.findall(pattern, text)
        
        prices = []
        min_p, max_p = cls.PRICE_RANGES.get(symbol, (0, float("inf")))

        for match in matches:
            try:
                clean = match.replace(",", "").replace(" ", "")
                val = float(clean)
                if min_p <= val <= max_p:
                    prices.append(val)
            except ValueError:
                continue
        return sorted(set(prices))

    @staticmethod
    def classify_zones(prices: List[float], current_price: Optional[float]) -> Tuple[List[float], List[float]]:
        """PURE LOGIC: Split prices into longs/shorts based on current price."""
        if current_price is None:
            return [], prices
        
        longs = [p for p in prices if p < current_price]
        shorts = [p for p in prices if p > current_price]
        return longs, shorts

    def _no_data_result(self, path: str, start: float) -> ExtractedPriceLevels:
        return ExtractedPriceLevels(
            screenshot_path=path,
            confidence=0.0,
            processing_time_ms=int((time.time() - start) * 1000),
            raw_text="No Data detected"
        )

    def _error_result(self, path: str, msg: str, start: float) -> ExtractedPriceLevels:
        return ExtractedPriceLevels(
            screenshot_path=path,
            confidence=0.0,
            processing_time_ms=int((time.time() - start) * 1000),
            raw_text=f"Error: {msg}"
        )
