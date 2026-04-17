"""Fallback loaders from raw ccxt-data-pipeline parquet into Nautilus objects."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

from src.liquidationheatmap.nautilus import _check_nautilus

_check_nautilus()

from nautilus_trader.core.datetime import dt_to_unix_nanos  # noqa: E402
from nautilus_trader.model.currencies import USDT  # noqa: E402
from nautilus_trader.model.data import Bar, BarType, TradeTick  # noqa: E402
from nautilus_trader.model.enums import AggressorSide  # noqa: E402
from nautilus_trader.model.identifiers import InstrumentId, Symbol, TradeId, Venue  # noqa: E402
from nautilus_trader.model.instruments import CryptoPerpetual  # noqa: E402
from nautilus_trader.model.objects import Currency, Money, Price, Quantity  # noqa: E402


@dataclass(frozen=True)
class RawMarketDataBundle:
    """Instrument plus market data constructed from raw parquet files."""

    instrument: CryptoPerpetual
    bars: list[Bar]
    trade_ticks: list[TradeTick]
    bar_type: BarType | None


def load_raw_market_data_bundle(
    *,
    symbol: str,
    exchange: str,
    catalog_root: str | Path,
    timeframe: str = "1m",
    start: str | None = None,
    end: str | None = None,
) -> RawMarketDataBundle | None:
    """Load a Nautilus-compatible market data bundle from raw parquet files."""
    catalog_root = Path(catalog_root)
    ohlcv_rows = _load_ohlcv_rows(
        catalog_root=catalog_root,
        symbol=symbol,
        exchange=exchange,
        timeframe=timeframe,
        start=start,
        end=end,
    )
    trade_rows = _load_trade_rows(
        catalog_root=catalog_root,
        symbol=symbol,
        exchange=exchange,
        start=start,
        end=end,
    )

    sample_rows = ohlcv_rows or trade_rows
    if not sample_rows:
        return None

    instrument = _build_perpetual_instrument(symbol=symbol, exchange=exchange, rows=sample_rows)
    bars: list[Bar] = []
    bar_type: BarType | None = None
    if ohlcv_rows:
        bar_type = _bar_type_for(instrument.id, timeframe)
        bars = [
            Bar(
                bar_type=bar_type,
                open=instrument.make_price(row["open"]),
                high=instrument.make_price(row["high"]),
                low=instrument.make_price(row["low"]),
                close=instrument.make_price(row["close"]),
                volume=instrument.make_qty(row["volume"]),
                ts_event=dt_to_unix_nanos(row["timestamp"]),
                ts_init=dt_to_unix_nanos(row["timestamp"]),
            )
            for row in ohlcv_rows
        ]

    trade_ticks = [
        TradeTick(
            instrument.id,
            instrument.make_price(row["price"]),
            instrument.make_qty(row["quantity"]),
            _aggressor_side(row.get("side")),
            TradeId(str(row["trade_id"])),
            dt_to_unix_nanos(row["timestamp"]),
            dt_to_unix_nanos(row["timestamp"]),
        )
        for row in trade_rows
    ]

    return RawMarketDataBundle(
        instrument=instrument,
        bars=bars,
        trade_ticks=trade_ticks,
        bar_type=bar_type,
    )


def _load_ohlcv_rows(
    *,
    catalog_root: Path,
    symbol: str,
    exchange: str,
    timeframe: str,
    start: str | None,
    end: str | None,
) -> list[dict[str, Any]]:
    dataset = catalog_root / "ohlcv" / f"{symbol}-PERP.{exchange.upper()}" / "*.parquet"
    if not list((catalog_root / "ohlcv" / f"{symbol}-PERP.{exchange.upper()}").glob("*.parquet")):
        return []

    query = f"""
        SELECT timestamp, open, high, low, close, volume
        FROM read_parquet('{dataset}')
        WHERE timeframe = ?
    """
    params: list[Any] = [timeframe]
    if start:
        query += " AND timestamp >= ?"
        params.append(start)
    if end:
        query += " AND timestamp <= ?"
        params.append(end)
    query += " ORDER BY timestamp"

    con = duckdb.connect()
    rows = con.execute(query, params).fetchall()
    return [
        {
            "timestamp": row[0],
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
        }
        for row in rows
    ]


def _load_trade_rows(
    *,
    catalog_root: Path,
    symbol: str,
    exchange: str,
    start: str | None,
    end: str | None,
) -> list[dict[str, Any]]:
    dataset = catalog_root / "trades" / f"{symbol}-PERP.{exchange.upper()}" / "*.parquet"
    if not list((catalog_root / "trades" / f"{symbol}-PERP.{exchange.upper()}").glob("*.parquet")):
        return []

    query = f"""
        SELECT timestamp, trade_id, price, quantity, side
        FROM read_parquet('{dataset}')
        WHERE TRUE
    """
    params: list[Any] = []
    if start:
        query += " AND timestamp >= ?"
        params.append(start)
    if end:
        query += " AND timestamp <= ?"
        params.append(end)
    query += " ORDER BY timestamp"

    con = duckdb.connect()
    rows = con.execute(query, params).fetchall()
    return [
        {
            "timestamp": row[0],
            "trade_id": row[1],
            "price": float(row[2]),
            "quantity": float(row[3]),
            "side": row[4],
        }
        for row in rows
    ]


def _build_perpetual_instrument(
    *,
    symbol: str,
    exchange: str,
    rows: list[dict[str, Any]],
) -> CryptoPerpetual:
    base_currency = _base_currency(symbol)
    quote_currency = USDT if symbol.endswith("USDT") else Currency.from_str(symbol[-4:])

    price_values = [
        float(row[key])
        for row in rows
        for key in ("open", "high", "low", "close", "price")
        if key in row and row[key] is not None
    ]
    quantity_values = [
        float(row[key])
        for row in rows
        for key in ("volume", "quantity")
        if key in row and row[key] is not None
    ]

    price_precision = _infer_precision(price_values, default=1)
    size_precision = _infer_precision(quantity_values, default=3)
    price_increment = _increment_from_precision(price_precision)
    size_increment = _increment_from_precision(size_precision)

    max_price = max(price_values) if price_values else 1.0
    min_price = min(p for p in price_values if p > 0) if price_values else 0.1
    max_quantity = max(quantity_values) if quantity_values else 1.0
    # Use the precision-derived increment as the permissive lower bound.
    # Sampled trade/bar quantities are observational, not authoritative venue minima.
    min_quantity = float(size_increment)
    first_ts = dt_to_unix_nanos(rows[0]["timestamp"])

    return CryptoPerpetual(
        instrument_id=InstrumentId(symbol=Symbol(f"{symbol}-PERP"), venue=Venue(exchange.upper())),
        raw_symbol=Symbol(symbol),
        base_currency=base_currency,
        quote_currency=quote_currency,
        settlement_currency=quote_currency,
        is_inverse=False,
        price_precision=price_precision,
        price_increment=Price.from_str(str(price_increment)),
        size_precision=size_precision,
        size_increment=Quantity.from_str(str(size_increment)),
        max_quantity=Quantity.from_str(f"{max_quantity:.{size_precision}f}"),
        min_quantity=Quantity.from_str(f"{min_quantity:.{size_precision}f}"),
        max_notional=None,
        min_notional=Money(10.0, quote_currency),
        max_price=Price.from_str(f"{max_price * 2:.{price_precision}f}"),
        min_price=Price.from_str(
            f"{max(min_price / 10, float(price_increment)):.{price_precision}f}"
        ),
        margin_init=Decimal("0.05"),
        margin_maint=Decimal("0.025"),
        maker_fee=Decimal("0.0002"),
        taker_fee=Decimal("0.0005"),
        ts_event=first_ts,
        ts_init=first_ts,
    )


def _base_currency(symbol: str) -> Currency:
    if symbol.endswith("USDT"):
        return Currency.from_str(symbol.removesuffix("USDT"))
    raise ValueError(f"Unsupported perpetual symbol format: {symbol}")


def _infer_precision(values: list[float], *, default: int) -> int:
    precisions = [_decimal_places(value) for value in values if value is not None]
    return max(precisions) if precisions else default


def _decimal_places(value: float) -> int:
    normalized = f"{value:.12f}".rstrip("0").rstrip(".")
    if "." not in normalized:
        return 0
    return len(normalized.split(".", 1)[1])


def _increment_from_precision(precision: int) -> Decimal:
    return Decimal("1").scaleb(-precision)


def _bar_type_for(instrument_id: InstrumentId, timeframe: str) -> BarType:
    amount = int(timeframe[:-1])
    unit = timeframe[-1]
    unit_map = {
        "m": "MINUTE",
        "h": "HOUR",
        "d": "DAY",
    }
    if unit not in unit_map:
        raise ValueError(f"Unsupported timeframe for Nautilus fallback: {timeframe}")
    return BarType.from_str(f"{instrument_id}-{amount}-{unit_map[unit]}-LAST-EXTERNAL")


def _aggressor_side(side: str | None) -> AggressorSide:
    if side == "BUY":
        return AggressorSide.BUYER
    if side == "SELL":
        return AggressorSide.SELLER
    return AggressorSide.NO_AGGRESSOR
