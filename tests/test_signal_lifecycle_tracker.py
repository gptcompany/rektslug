import pytest

from src.liquidationheatmap.signals.lifecycle import LifecycleState, SignalLifecycleTracker
from src.liquidationheatmap.signals.lifecycle_store import (
    DuckDBLifecycleStore,
    resolve_lifecycle_db_path,
)


def test_initial_state_is_received():
    tracker = SignalLifecycleTracker(store=None)
    tracker.record_signal("sig-1")
    assert tracker.get_state("sig-1") == LifecycleState.RECEIVED


def test_valid_state_transitions():
    tracker = SignalLifecycleTracker(store=None)
    tracker.record_signal("sig-1")

    tracker.transition("sig-1", LifecycleState.ACCEPTED)
    assert tracker.get_state("sig-1") == LifecycleState.ACCEPTED

    tracker.transition("sig-1", LifecycleState.ORDER_SUBMITTED)
    assert tracker.get_state("sig-1") == LifecycleState.ORDER_SUBMITTED

    tracker.transition("sig-1", LifecycleState.FILLED)
    tracker.transition("sig-1", LifecycleState.POSITION_OPENED)
    tracker.transition("sig-1", LifecycleState.POSITION_CLOSED)
    tracker.transition("sig-1", LifecycleState.FEEDBACK_PUBLISHED)
    tracker.transition("sig-1", LifecycleState.FEEDBACK_PERSISTED)

    assert tracker.get_state("sig-1") == LifecycleState.FEEDBACK_PERSISTED


def test_reject_invalid_transitions():
    tracker = SignalLifecycleTracker(store=None)
    tracker.record_signal("sig-1")

    with pytest.raises(ValueError, match="Invalid transition"):
        tracker.transition("sig-1", LifecycleState.FILLED)


def test_persists_to_store():
    class DummyStore:
        def __init__(self):
            self.saved = {}

        def save_state(self, signal_id, state):
            self.saved[signal_id] = state

    store = DummyStore()
    tracker = SignalLifecycleTracker(store=store)
    tracker.record_signal("sig-1")
    tracker.transition("sig-1", LifecycleState.REJECTED)

    assert store.saved["sig-1"] == LifecycleState.REJECTED


def test_lifecycle_store_prefers_feedback_db_path(monkeypatch):
    monkeypatch.setenv("FEEDBACK_DB_PATH", "/var/lib/rektslug-db/signal_feedback.duckdb")
    monkeypatch.setenv("HEATMAP_DB_PATH", "/var/lib/rektslug-db/liquidations.duckdb")

    assert resolve_lifecycle_db_path() == "/var/lib/rektslug-db/signal_feedback.duckdb"
    assert DuckDBLifecycleStore().db_path == "/var/lib/rektslug-db/signal_feedback.duckdb"


def test_lifecycle_store_derives_feedback_db_from_heatmap_path(monkeypatch):
    monkeypatch.delenv("FEEDBACK_DB_PATH", raising=False)
    monkeypatch.setenv("HEATMAP_DB_PATH", "/var/lib/rektslug-db/liquidations.duckdb")

    assert resolve_lifecycle_db_path() == "/var/lib/rektslug-db/signal_feedback.duckdb"
