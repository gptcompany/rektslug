"""Validation module for comparing Coinglass screenshots with our API."""

from .provider_profiles import PROVIDER_PROFILES, ProviderProfile, get_provider_profile
from .ocr_extractor import ExtractedPriceLevels, OCRExtractor
from .screenshot_parser import Screenshot, parse_filename
from .zone_comparator import (
    AggregateMetrics,
    APIPriceLevels,
    ValidationResult,
    ZoneComparator,
    calculate_aggregate_metrics,
    calculate_hit_rate,
    fetch_api_heatmap,
)

__all__ = [
    # Provider profiles
    "ProviderProfile",
    "PROVIDER_PROFILES",
    "get_provider_profile",
    # Screenshot parsing
    "Screenshot",
    "parse_filename",
    # OCR extraction
    "OCRExtractor",
    "ExtractedPriceLevels",
    # Zone comparison
    "ZoneComparator",
    "APIPriceLevels",
    "ValidationResult",
    "AggregateMetrics",
    "calculate_hit_rate",
    "calculate_aggregate_metrics",
    "fetch_api_heatmap",
]
