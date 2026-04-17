"""Persistent signal status metrics backed by Redis when available."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

SIGNAL_STATUS_LAST_PUBLISH_KEY = "liquidation:signals:status:last_publish"
SIGNAL_STATUS_PUBLISHED_ZSET = "liquidation:signals:status:published_at"


def _get_backend(redis_client: Any) -> Any | None:
    connect = getattr(redis_client, "connect", None)
    if callable(connect):
        try:
            return connect()
        except Exception:
            return None
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, "", b""):
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def record_signal_publish(redis_client: Any, published_at: datetime, signal_id: str | None) -> None:
    backend = _get_backend(redis_client)
    if backend is None:
        return

    ts = published_at.astimezone(timezone.utc)
    member = f"{ts.timestamp():.6f}:{signal_id or 'unknown'}"
    try:
        backend.set(SIGNAL_STATUS_LAST_PUBLISH_KEY, ts.isoformat().replace("+00:00", "Z"))
        backend.zadd(SIGNAL_STATUS_PUBLISHED_ZSET, {member: ts.timestamp()})
        backend.zremrangebyscore(
            SIGNAL_STATUS_PUBLISHED_ZSET,
            0,
            (ts - timedelta(hours=24, minutes=1)).timestamp(),
        )
    except Exception:
        return


def load_signal_status_metrics(redis_client: Any) -> tuple[datetime | None, int]:
    backend = _get_backend(redis_client)
    if backend is None:
        return None, 0

    now = datetime.now(timezone.utc)
    lower_bound = (now - timedelta(hours=24)).timestamp()
    try:
        last_publish = _parse_datetime(backend.get(SIGNAL_STATUS_LAST_PUBLISH_KEY))
        signals_24h = backend.zcount(SIGNAL_STATUS_PUBLISHED_ZSET, lower_bound, now.timestamp())
        try:
            signals_24h = int(signals_24h)
        except (TypeError, ValueError):
            signals_24h = 0
        return last_publish, signals_24h
    except Exception:
        return None, 0
