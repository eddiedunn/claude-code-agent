# Changelog

## [Unreleased]

### Added

- **Programmatic Message Injection**: Full support for injecting guidance and control
  actions into running sessions without TTY/keyboard input
  - New `grind.interactive_v2` module with session-scoped message queues
  - Enhanced `/sessions/{id}/inject` endpoint with action types
  - Python API: `inject_guidance()` and `inject_action()` functions
  - Session isolation: Messages scoped to specific sessions
  - Backward compatible: TTY/keyboard input still works for interactive sessions
- New documentation:
  - `docs/programmatic-injection.md`: Comprehensive API guide
  - `docs/migration-programmatic-injection.md`: Upgrade guide
- Test coverage: Integration tests for injection scenarios

### Changed

- `grind/interactive.py`: Enhanced `get_checkpoint_input()` to check message queue first
- `grind/models.py`: Added `session_id` field to `TaskDefinition`
- `grind/server/services/session_manager.py`: Updated `inject()` to use new API
- OpenAPI documentation: Enhanced injection endpoint docs

### Fixed

- Message injection now delivers actual message content to agent (not just checkpoint)
- Session-scoped injection prevents message leaks between concurrent sessions

## [Previous versions]
...
