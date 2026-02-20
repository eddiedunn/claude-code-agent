"""State machine definitions for session lifecycle."""
from grind.server.models.responses import SessionStatus

# Valid state transitions - key is current state, value is set of allowed next states
VALID_TRANSITIONS: dict[SessionStatus, set[SessionStatus]] = {
    SessionStatus.PENDING: {SessionStatus.RUNNING, SessionStatus.CANCELLED},
    SessionStatus.RUNNING: {
        SessionStatus.PAUSED,
        SessionStatus.COMPLETED,
        SessionStatus.FAILED,
        SessionStatus.CANCELLED,
    },
    SessionStatus.PAUSED: {SessionStatus.RUNNING, SessionStatus.CANCELLED},
    # Terminal states have no valid transitions
    SessionStatus.COMPLETED: set(),
    SessionStatus.FAILED: set(),
    SessionStatus.CANCELLED: set(),
}

def is_valid_transition(current: SessionStatus, next_state: SessionStatus) -> bool:
    """Check if a state transition is valid."""
    return next_state in VALID_TRANSITIONS.get(current, set())

def is_terminal_state(state: SessionStatus) -> bool:
    """Check if a state is terminal (no further transitions)."""
    return state in {SessionStatus.COMPLETED, SessionStatus.FAILED, SessionStatus.CANCELLED}
