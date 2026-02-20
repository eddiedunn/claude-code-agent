# Migration Guide: Programmatic Injection

## Overview

This guide helps you upgrade from the checkpoint-only injection (v1) to
full programmatic message injection (v2).

## What Changed

### Before (v1)

```python
# Could only trigger checkpoints
POST /sessions/{id}/inject
{
  "message": "Some message"  # Not actually injected
}
# Result: Session paused at next checkpoint, but message not delivered
```

### After (v2)

```python
# Full message injection
POST /sessions/{id}/inject
{
  "message": "Try using pattern X",
  "action": "guidance",
  "persistent": false
}
# Result: Message delivered at next checkpoint, agent can see it
```

## Breaking Changes

**None!** The v2 implementation is fully backward compatible.

- Existing code continues to work unchanged
- TTY/keyboard input still works for interactive sessions
- No API changes to existing endpoints

## New Features

1. **Message Delivery**: Injected messages are now actually delivered to the agent
2. **Action Types**: Support for abort, status, verify actions
3. **Persistent Guidance**: Guidance can persist across iterations
4. **Python API**: Direct programmatic access via `inject_guidance()`

## How to Upgrade

### Step 1: Update Dependencies

```bash
cd ~/code/claude-code-agent
git pull origin main
uv sync
```

### Step 2: Update Your Code (Optional)

If you were working around the v1 limitation, you can now simplify:

**Before:**
```python
# Had to use external coordination mechanisms
await trigger_checkpoint(session_id)
await external_queue.send(message)  # Hope agent checks it
```

**After:**
```python
# Direct injection
await inject_guidance(session_id, message)
```

### Step 3: Test

Run your integration tests to verify injection works as expected:

```bash
pytest tests/test_injection_integration.py -v
```

## Examples

### Example 1: Basic Guidance Injection

```python
from grind.interactive_v2 import inject_guidance

# During a running session
await inject_guidance(
    session_id="sess_abc123",
    message="Focus on the error handling in module X",
    persistent=False
)
```

### Example 2: Persistent Context

```python
# Set guidance that applies to all iterations
await inject_guidance(
    session_id="sess_abc123",
    message="Always verify changes with unit tests",
    persistent=True
)
```

### Example 3: Control Actions

```python
from grind.interactive_v2 import inject_action
from grind.models import CheckpointAction

# Abort a runaway session
await inject_action(
    session_id="sess_abc123",
    action=CheckpointAction.ABORT
)
```

## Troubleshooting

### Messages Not Delivered

**Symptom**: Injection succeeds but agent doesn't see message

**Causes:**
- Session not in RUNNING state (check status)
- Interactive mode disabled (enable with `interactive: {enabled: true}`)
- No checkpoints reached yet (inject happens at iteration boundaries)

**Solution:**
```python
# Check session status first
session = await session_manager.get_session(session_id)
if session.status != SessionStatus.RUNNING:
    raise ValueError(f"Session not running: {session.status}")

# Ensure interactive mode is enabled in task definition
task_def = TaskDefinition(
    task="...",
    interactive=InteractiveConfig(enabled=True)
)
```

### Backward Compatibility Issues

**Symptom**: TTY input stopped working after upgrade

**Cause**: Session ID incorrectly set for TTY sessions

**Solution:**
```python
# For TTY/keyboard sessions, don't set session_id
task_def = TaskDefinition(
    task="...",
    session_id=None  # Enables TTY input
)
```

## Support

If you encounter issues during migration:

1. Check the [Programmatic Injection Docs](programmatic-injection.md)
2. Review test examples in `tests/test_injection_integration.py`
3. Open an issue with reproduction steps
