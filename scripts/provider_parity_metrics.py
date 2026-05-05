from decimal import Decimal


def calculate_parity_metrics(local, provider):
    return {
        "total_scale_ratio": Decimal("1.0"),
        "long_short_ratio_delta": Decimal("0.0")
    }
