"""Prometheus metrics for the API and storage backends."""

from fastapi import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

GAP_FILL_DURATION = Histogram(
    "lh_gap_fill_duration_seconds",
    "Time spent performing gap-fill",
    buckets=(1, 5, 10, 30, 60, 120, 300, 600),
)

GAP_FILL_INSERTED_TOTAL = Counter(
    "lh_gap_fill_inserted_rows_total",
    "Total number of rows inserted during gap-fill",
    ["symbol", "type"],
)

DB_LOCK_CONTENTION_TOTAL = Counter(
    "lh_db_lock_contention_total",
    "Total number of 503 errors due to ingestion lock",
)

ACTIVE_DB_CONNECTIONS = Gauge(
    "lh_active_db_connections",
    "Number of active read-only DuckDB singletons",
)

QUESTDB_QUERY_DURATION = Histogram(
    "lh_questdb_query_duration_seconds",
    "Latency of QuestDB SQL queries",
    ["query_kind", "status"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

QUESTDB_QUERY_TOTAL = Counter(
    "lh_questdb_query_total",
    "Total number of QuestDB SQL queries",
    ["query_kind", "status"],
)

QUESTDB_INGEST_TOTAL = Counter(
    "lh_questdb_ingest_total",
    "Total number of QuestDB ILP ingestion attempts",
    ["table", "status"],
)

QUESTDB_AVAILABLE = Gauge(
    "lh_questdb_available",
    "Whether QuestDB SQL is currently reachable (1 healthy, 0 unavailable)",
)


def get_metrics_response() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
