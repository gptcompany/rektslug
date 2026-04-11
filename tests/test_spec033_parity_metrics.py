import pytest
from decimal import Decimal
from scripts.provider_parity_metrics import calculate_parity_metrics

def test_metrics_on_synthetic_data():
    local_data = {"total_long": 1000, "total_short": 500, "bucket_count": 10, "price_step": 1.0}
    provider_data = {"total_long": 1100, "total_short": 400, "bucket_count": 12, "price_step": 1.1}
    
    metrics = calculate_parity_metrics(local_data, provider_data)
    
    assert metrics["total_scale_ratio"] is not None
    assert metrics["long_short_ratio_delta"] is not None
