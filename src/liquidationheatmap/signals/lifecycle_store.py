import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from src.liquidationheatmap.signals.lifecycle import LifecycleState

DEFAULT_LIFECYCLE_DB_PATH = "/media/sam/2TB-NVMe/liquidationheatmap_db/signal_feedback.duckdb"


def resolve_lifecycle_db_path() -> str:
    """Resolve lifecycle storage without taking the main heatmap DB writer lock."""
    feedback_db_path = os.getenv("FEEDBACK_DB_PATH")
    if feedback_db_path:
        return feedback_db_path

    heatmap_db_path = os.getenv("HEATMAP_DB_PATH") or os.getenv("HEATMAP_CONTAINER_DB_PATH")
    if heatmap_db_path:
        return str(Path(heatmap_db_path).with_name("signal_feedback.duckdb"))

    return DEFAULT_LIFECYCLE_DB_PATH


class DuckDBLifecycleStore:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or resolve_lifecycle_db_path()
        self._conn = None

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            self._conn = duckdb.connect(self.db_path)
            self._ensure_table()
        return self._conn

    def _ensure_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS signal_lifecycle (
                signal_id VARCHAR PRIMARY KEY,
                state VARCHAR NOT NULL,
                updated_at TIMESTAMP NOT NULL
            )
        """)

    def save_state(self, signal_id: str, state: LifecycleState):
        try:
            now = datetime.now(timezone.utc)
            self.conn.execute(
                """
                INSERT INTO signal_lifecycle (signal_id, state, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT (signal_id) DO UPDATE SET
                    state = EXCLUDED.state,
                    updated_at = EXCLUDED.updated_at
            """,
                [signal_id, state.name, now],
            )
        except Exception as e:
            logging.error(f"Failed to save lifecycle state for {signal_id}: {e}")

    def get_state(self, signal_id: str) -> LifecycleState | None:
        try:
            row = self.conn.execute(
                "SELECT state FROM signal_lifecycle WHERE signal_id = ?", [signal_id]
            ).fetchone()
            if row:
                return LifecycleState[row[0]]
        except Exception as e:
            logging.error(f"Failed to get lifecycle state for {signal_id}: {e}")
        return None

    def get_all_states(self) -> dict[str, str]:
        try:
            rows = self.conn.execute("SELECT signal_id, state FROM signal_lifecycle").fetchall()
            return {row[0]: row[1] for row in rows}
        except Exception:
            return {}

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None
