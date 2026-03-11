from datetime import datetime
from decimal import Decimal
from uuid import UUID

from src.models.position_margin import PositionMargin


def test_position_margin_post_init_generates_uuid_and_decimals():
    record = PositionMargin(
        symbol="BTCUSDT",
        notional=100000,
        margin_required="750",
        tier_number=2,
        margin_rate=0.01,
        maintenance_amount="250",
        configuration_version="binance-2025-v1",
        calculated_at=datetime(2024, 1, 1),
        leverage="10",
        entry_price=50000,
        position_size="2",
        liquidation_price=45500.5,
        side="long",
    )

    assert isinstance(record.id, UUID)
    assert record.notional == Decimal("100000")
    assert record.margin_required == Decimal("750")
    assert record.margin_rate == Decimal("0.01")
    assert record.maintenance_amount == Decimal("250")
    assert record.leverage == Decimal("10")
    assert record.entry_price == Decimal("50000")
    assert record.position_size == Decimal("2")
    assert record.liquidation_price == Decimal("45500.5")


def test_position_margin_from_calculation_sets_timestamp_and_optional_fields():
    record = PositionMargin.from_calculation(
        symbol="ETHUSDT",
        notional=Decimal("25000"),
        margin_required=Decimal("125"),
        tier_number=1,
        margin_rate=Decimal("0.005"),
        maintenance_amount=Decimal("0"),
        configuration_version="binance-2025-v1",
        leverage=Decimal("5"),
        entry_price=Decimal("2500"),
        position_size=Decimal("10"),
        liquidation_price=Decimal("2250"),
        side="short",
    )

    assert record.symbol == "ETHUSDT"
    assert record.side == "short"
    assert isinstance(record.calculated_at, datetime)


def test_position_margin_to_dict_and_from_dict_round_trip():
    original = PositionMargin(
        symbol="BTCUSDT",
        notional=Decimal("100000"),
        margin_required=Decimal("750"),
        tier_number=2,
        margin_rate=Decimal("0.01"),
        maintenance_amount=Decimal("250"),
        configuration_version="binance-2025-v1",
        calculated_at=datetime(2024, 1, 1, 12, 30, 0),
        leverage=Decimal("10"),
        entry_price=Decimal("50000"),
        position_size=Decimal("2"),
        liquidation_price=Decimal("45500"),
        side="long",
    )

    payload = original.to_dict()
    restored = PositionMargin.from_dict(payload)

    assert payload["symbol"] == "BTCUSDT"
    assert payload["margin_required"] == "750"
    assert restored.id == original.id
    assert restored.notional == original.notional
    assert restored.margin_required == original.margin_required
    assert restored.calculated_at == original.calculated_at
    assert restored.side == "long"


def test_position_margin_string_representation_is_audit_friendly():
    record = PositionMargin(
        symbol="BTCUSDT",
        notional=Decimal("100000"),
        margin_required=Decimal("750"),
        tier_number=2,
        margin_rate=Decimal("0.01"),
        maintenance_amount=Decimal("250"),
        configuration_version="binance-2025-v1",
        calculated_at=datetime(2024, 1, 1),
    )

    rendered = str(record)

    assert "PositionMargin(" in rendered
    assert "symbol=BTCUSDT" in rendered
    assert "tier=2" in rendered
    assert "version=binance-2025-v1" in rendered
