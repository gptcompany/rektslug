from enum import Enum, auto


class LifecycleState(Enum):
    RECEIVED = auto()
    REJECTED = auto()
    ACCEPTED = auto()
    ORDER_SUBMITTED = auto()
    ORDER_REJECTED = auto()
    FILLED = auto()
    POSITION_OPENED = auto()
    POSITION_CLOSED = auto()
    FEEDBACK_PUBLISHED = auto()
    FEEDBACK_PERSISTED = auto()


class SignalLifecycleTracker:
    def __init__(self, store=None):
        self.store = store
        self._states = {}

    def record_signal(self, signal_id: str):
        self._set_state(signal_id, LifecycleState.RECEIVED)

    def transition(self, signal_id: str, new_state: LifecycleState):
        current_state = self.get_state(signal_id)
        
        valid_transitions = {
            LifecycleState.RECEIVED: {LifecycleState.REJECTED, LifecycleState.ACCEPTED},
            LifecycleState.ACCEPTED: {LifecycleState.ORDER_SUBMITTED},
            LifecycleState.ORDER_SUBMITTED: {LifecycleState.ORDER_REJECTED, LifecycleState.FILLED},
            LifecycleState.FILLED: {LifecycleState.POSITION_OPENED},
            LifecycleState.POSITION_OPENED: {LifecycleState.POSITION_CLOSED},
            LifecycleState.POSITION_CLOSED: {LifecycleState.FEEDBACK_PUBLISHED},
            LifecycleState.FEEDBACK_PUBLISHED: {LifecycleState.FEEDBACK_PERSISTED},
        }

        if current_state not in valid_transitions or new_state not in valid_transitions[current_state]:
            raise ValueError(f"Invalid transition from {current_state} to {new_state}")

        self._set_state(signal_id, new_state)

    def get_state(self, signal_id: str) -> LifecycleState:
        return self._states.get(signal_id)

    def _set_state(self, signal_id: str, state: LifecycleState):
        self._states[signal_id] = state
        if self.store is not None:
            self.store.save_state(signal_id, state)
