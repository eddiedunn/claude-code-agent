"""Custom exceptions for Grind Server."""


class GrindServerError(Exception):
    """Base exception for all Grind Server errors."""
    pass


class SessionNotFoundError(GrindServerError):
    """Raised when a session ID does not exist."""
    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(f"Session not found: {session_id}")


class SessionNotRunningError(GrindServerError):
    """Raised when operation requires a running session but it's not."""
    def __init__(self, session_id: str, current_status: str):
        self.session_id = session_id
        self.current_status = current_status
        super().__init__(f"Session {session_id} is not running (status: {current_status})")


class SessionAlreadyExistsError(GrindServerError):
    """Raised when attempting to create a duplicate session (idempotency key collision)."""
    def __init__(self, idempotency_key: str, existing_session_id: str):
        self.idempotency_key = idempotency_key
        self.existing_session_id = existing_session_id
        super().__init__(f"Session with idempotency key '{idempotency_key}' already exists: {existing_session_id}")


class SessionLimitReachedError(GrindServerError):
    """Raised when max concurrent sessions limit is reached."""
    def __init__(self, current: int, limit: int):
        self.current = current
        self.limit = limit
        super().__init__(f"Session limit reached: {current}/{limit} sessions running")
