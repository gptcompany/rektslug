from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response

# Metrics definitions
GAP_FILL_DURATION = Histogram(
    "lh_gap_fill_duration_seconds",
    "Time spent performing gap-fill",
    buckets=(1, 5, 10, 30, 60, 120, 300, 600)
)

GAP_FILL_INSERTED_TOTAL = Counter(
    "lh_gap_fill_inserted_rows_total",
    "Total number of rows inserted during gap-fill",
    ["symbol", "type"]  # type: klines, oi, funding
)

DB_LOCK_CONTENTION_TOTAL = Counter(
    "lh_db_lock_contention_total",
    "Total number of 503 errors due to ingestion lock"
)

ACTIVE_DB_CONNECTIONS = Gauge(
    "lh_active_db_connections",
    "Number of active read-only DuckDB singletons"
)

def get_metrics_response():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
