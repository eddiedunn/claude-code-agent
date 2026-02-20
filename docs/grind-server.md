# Grind Server Documentation

## Message Injection

Grind-server supports programmatic message injection, allowing you to send
guidance and control actions to running sessions via the REST API.

### Quick Example

```bash
# Start a session
curl -X POST http://localhost:8420/sessions/ \
  -H "Content-Type: application/json" \
  -d '{"task": "Implement feature X"}'

# Inject guidance while it runs
curl -X POST http://localhost:8420/sessions/{session_id}/inject \
  -H "Content-Type: application/json" \
  -d '{"message": "Use the factory pattern", "action": "guidance"}'
```

### Capabilities

- **Remote Guidance**: Inject hints, suggestions, or corrections during execution
- **Control Actions**: Abort, request status, or trigger verify command
- **Persistent Guidance**: Set guidance that applies across multiple iterations
- **Session Isolation**: Messages are scoped to specific sessions

For full documentation, see [Programmatic Injection](programmatic-injection.md).

### Use Cases

1. **Human-in-the-Loop**: Monitor session progress and provide course corrections
2. **Automated Oversight**: Trigger actions based on external events or monitoring
3. **Multi-Agent Coordination**: One agent provides guidance to another
4. **Integration Testing**: Programmatically test checkpoint behavior

## API Reference

### Sessions

- `POST /sessions/` - Start a new session
- `GET /sessions/{session_id}` - Get session status
- `POST /sessions/{session_id}/inject` - Inject message into running session
- `DELETE /sessions/{session_id}` - Abort a session
