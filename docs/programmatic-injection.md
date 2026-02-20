# Programmatic Message Injection

## Overview

Grind supports programmatic message injection, allowing external systems (like
grind-server) to send guidance and control actions to running sessions without
requiring TTY/keyboard input.

## Architecture

The injection system consists of three layers:

1. **Message Queue Layer** (`grind/interactive_v2.py`)
   - Session-scoped message queues
   - Thread-safe async operations
   - TTL-based cleanup

2. **Hybrid Input Layer** (`grind/interactive.py`)
   - Checks programmatic queue first
   - Falls back to TTY input if no messages
   - Maintains backward compatibility

3. **API Layer** (`grind/server/routes/sessions.py`)
   - REST endpoint for injection
   - Session validation
   - Error handling

## API Endpoint

### Inject Message

`POST /sessions/{session_id}/inject`

Inject a guidance message or control action into a running session.

**Request Body:**
```json
{
  "message": "Try using a different approach",
  "action": "guidance",
  "persistent": false
}
```

**Fields:**
- `message` (string, required): The message or action to inject
- `action` (string, optional): Action type (default: "guidance")
  - `guidance`: One-shot guidance for current iteration
  - `guidance_persist`: Guidance that persists across iterations
  - `abort`: Abort the session
  - `status`: Show status
  - `verify`: Run verify command
- `persistent` (boolean, optional): Whether guidance persists (default: false)

**Response:**
```json
{
  "status": "injected",
  "session_id": "abc12345"
}
```

**Error Responses:**
- `404`: Session not found
- `400`: Session not running (must be in RUNNING state)

## Python API

### High-Level API

```python
from grind.interactive_v2 import inject_guidance, inject_action
from grind.models import CheckpointAction

# Inject guidance
await inject_guidance(
    session_id="sess_123",
    message="Focus on the authentication bug",
    persistent=False
)

# Inject control action
await inject_action(
    session_id="sess_123",
    action=CheckpointAction.ABORT
)
```

### Low-Level API

```python
from grind.interactive_v2 import (
    get_message_queue_manager,
    InjectionMessage,
    CheckpointAction
)
from datetime import datetime, timezone

manager = get_message_queue_manager()

msg = InjectionMessage(
    action=CheckpointAction.GUIDANCE,
    message="Your guidance here",
    timestamp=datetime.now(timezone.utc),
    source="my_system",
    session_id="sess_123"
)

await manager.enqueue("sess_123", msg)
```

## Session Isolation

Messages are scoped to specific sessions. Each session has its own queue,
ensuring messages don't leak between concurrent sessions.

## Backward Compatibility

The injection system is fully backward compatible. Sessions without a session_id
continue to use TTY input exclusively. Sessions with a session_id check the
programmatic queue first, then fall back to TTY if no messages are present.

## Examples

### Example 1: Remote Guidance During Execution

```bash
# Start a session via API
curl -X POST http://localhost:8420/sessions/ \
  -H "Content-Type: application/json" \
  -d '{"task": "Fix the auth bug", "max_iterations": 10}'

# Later, inject guidance
curl -X POST http://localhost:8420/sessions/abc12345/inject \
  -H "Content-Type: application/json" \
  -d '{"message": "Check the JWT validation logic", "action": "guidance"}'
```

### Example 2: Abort Long-Running Session

```bash
curl -X POST http://localhost:8420/sessions/abc12345/inject \
  -H "Content-Type: application/json" \
  -d '{"message": "", "action": "abort"}'
```

### Example 3: Persistent Guidance

```bash
# Guidance that persists across iterations
curl -X POST http://localhost:8420/sessions/abc12345/inject \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Always verify changes with tests",
    "action": "guidance_persist",
    "persistent": true
  }'
```

## Troubleshooting

### Message Not Received

- Verify session is in RUNNING state (not PENDING, COMPLETED, etc.)
- Check session_id is correct
- Ensure session has checkpoints enabled (interactive mode)

### TTY Input Not Working

- Verify session_id is not set (or set to None) for TTY-only sessions
- Check terminal is attached and in cbreak mode

## Implementation Notes

- Messages have a 1-hour TTL to prevent memory leaks
- Queues are automatically cleaned up when sessions end
- Thread-safe async operations throughout
- No blocking I/O in critical paths
