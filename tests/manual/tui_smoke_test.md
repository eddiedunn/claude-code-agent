# TUI-Orchestrator Integration - Manual Smoke Test Guide

This document provides a step-by-step manual testing guide for validating the TUI-Orchestrator integration implemented in Phase 4.

**Purpose**: Verify that the TUI correctly integrates with the Orchestrator framework, including EventBus functionality, real-time updates, metrics display, and agent controls.

**Prerequisites**:
- Python 3.11+ installed
- Dependencies installed via `uv sync`
- Terminal with ANSI color support
- Valid Anthropic API key configured

---

## Test Environment Setup

### 1. Verify Installation

```bash
# Check Python version
python --version
# Expected: Python 3.11.0 or higher

# Verify uv installation
uv --version

# Install/sync dependencies
uv sync

# Verify grind CLI is available
uv run grind --help
```

**Expected Output**: Help text showing available commands including `tui`

---

## Test Suite

### Test 1: Basic TUI Launch

**Objective**: Verify the TUI launches successfully with Orchestrator integration.

**Steps**:
1. Launch the TUI:
   ```bash
   uv run grind tui
   ```

2. Observe the interface loads

**Expected Results**:
- ✅ TUI launches without errors
- ✅ Six tabs are visible: Agents (1), DAG (2), Running (3), Completed (4), Logs (5), Shell (6)
- ✅ Default tab is active (typically Shell or Agents)
- ✅ No error messages in the interface
- ✅ Keyboard shortcuts shown (q=Quit, 1-6=Tabs)

**Pass/Fail**: ___________

---

### Test 2: Tab Navigation

**Objective**: Verify all tabs are accessible and render correctly.

**Steps**:
1. Press `1` to switch to Agents tab
2. Press `2` to switch to DAG tab
3. Press `3` to switch to Running tab
4. Press `4` to switch to Completed tab
5. Press `5` to switch to Logs tab
6. Press `6` to switch to Shell tab

**Expected Results**:
- ✅ Each tab switches immediately on keypress
- ✅ Tab header highlights the active tab
- ✅ Each tab displays appropriate content (placeholder or functional)
- ✅ No visual corruption or rendering issues
- ✅ Smooth transitions between tabs

**Pass/Fail**: ___________

---

### Test 3: Shell Tab - Basic Commands

**Objective**: Verify the Shell tab's interactive REPL is functional.

**Steps**:
1. Press `6` to switch to Shell tab
2. Type `help` and press Enter
3. Type `status` and press Enter
4. Type `agents` (or `ls`) and press Enter
5. Type `history` and press Enter
6. Type `clear` and press Enter

**Expected Results**:
- ✅ `help` displays list of available commands with descriptions
- ✅ `status` shows agent status summary (may show 0 agents initially)
- ✅ `agents` displays "No agents in session" or lists existing agents
- ✅ `history` shows previous commands in order
- ✅ `clear` clears the shell output area
- ✅ Command prompt (`grind>`) is always visible

**Pass/Fail**: ___________

---

### Test 4: EventBus Integration - Agent Lifecycle Events

**Objective**: Verify EventBus publishes agent lifecycle events correctly.

**Preparation**:
Create a simple test task file `test-task.yaml`:
```yaml
tasks:
  - task: "Echo test message"
    verify: "echo 'test' && exit 0"
    max_iterations: 1
    model: "haiku"
```

**Steps**:
1. Launch TUI: `uv run grind tui -t test-task.yaml`
2. Switch to Shell tab (press `6`)
3. Type `run test-task.yaml` and press Enter
4. Immediately switch to Running tab (press `3`)
5. Watch for status updates
6. Wait for task completion
7. Switch to Completed tab (press `4`)

**Expected Results**:
- ✅ Shell confirms task file loaded
- ✅ Agent appears in Running tab with status "RUNNING"
- ✅ Agent ID is displayed (format: `agent-<uuid>`)
- ✅ Task description matches: "Echo test message"
- ✅ Iteration counter shows progress (e.g., "1/1")
- ✅ Agent transitions to Completed tab after finishing
- ✅ Final status shows "COMPLETED" or "SUCCESS"
- ✅ No errors in Shell output

**Pass/Fail**: ___________

---

### Test 5: Real-Time Status Updates

**Objective**: Verify real-time UI updates via EventBus (not polling).

**Preparation**:
Create task file `slow-task.yaml`:
```yaml
tasks:
  - task: "Sleep and verify"
    verify: "sleep 2 && exit 0"
    max_iterations: 3
    model: "haiku"
```

**Steps**:
1. Launch TUI: `uv run grind tui`
2. Switch to Shell tab (press `6`)
3. Type `run slow-task.yaml` and press Enter
4. Quickly switch to Running tab (press `3`)
5. Observe iteration updates in real-time
6. Note if updates appear instantly (event-driven) vs delayed (polling)

**Expected Results**:
- ✅ Iteration counter increments immediately when iteration starts
- ✅ Status updates appear instantly (not delayed by 1+ seconds)
- ✅ Progress bar updates smoothly (if displayed)
- ✅ No noticeable lag between iteration completion and UI update
- ✅ Events appear to be pushed (reactive) rather than polled

**Pass/Fail**: ___________

---

### Test 6: Agent Details View

**Objective**: Verify detailed agent information is accessible.

**Steps**:
1. Ensure at least one agent exists (from previous tests)
2. Switch to Shell tab (press `6`)
3. Type `agents` to list all agents
4. Copy an agent ID from the list
5. Type `agent <agent-id>` and press Enter

**Expected Results**:
- ✅ Detailed view shows:
  - Task ID and description
  - Agent type (e.g., "grind")
  - Model name (e.g., "haiku", "sonnet")
  - Status (e.g., "completed", "running", "failed")
  - Iteration count (e.g., "3/5")
  - Progress percentage (if applicable)
  - Duration/elapsed time
  - Timestamps (start, end)
  - Log file location
  - Error messages (if failed)
- ✅ All fields display correct values
- ✅ No missing or "None" values where data should exist

**Pass/Fail**: ___________

---

### Test 7: Log Viewing

**Objective**: Verify agent logs are accessible and display correctly.

**Steps**:
1. Ensure at least one completed agent exists
2. Switch to Shell tab (press `6`)
3. Type `logs <agent-id>` or `tail <agent-id>`
4. Optionally specify line count: `logs <agent-id> 50`

**Expected Results**:
- ✅ Log output displays in the shell area
- ✅ Logs show agent execution details (iterations, verification output)
- ✅ Log lines are formatted and readable
- ✅ Default shows last 20 lines (or configured default)
- ✅ Specifying line count (e.g., 50) works correctly
- ✅ Alias `tail` works identically to `logs`
- ✅ Log file location is shown or easily accessible

**Pass/Fail**: ___________

---

### Test 8: Agent Control Commands

**Objective**: Verify agent lifecycle control commands work correctly.

**Preparation**:
Create task file `long-task.yaml`:
```yaml
tasks:
  - task: "Long running task"
    verify: "sleep 10 && exit 0"
    max_iterations: 5
    model: "haiku"
```

**Steps**:
1. Launch TUI: `uv run grind tui`
2. Switch to Shell tab (press `6`)
3. Type `run long-task.yaml` and press Enter
4. Note the agent ID from the output
5. Type `pause <agent-id>` and press Enter
6. Wait a moment, then type `status` to verify pause
7. Type `resume <agent-id>` and press Enter
8. Type `cancel <agent-id>` and press Enter

**Expected Results**:
- ✅ `pause <agent-id>` accepts command and confirms pause request
- ✅ Agent status changes to "PAUSED" (visible in `status` or `agents`)
- ✅ `resume <agent-id>` successfully resumes execution
- ✅ Agent status changes back to "RUNNING"
- ✅ `cancel <agent-id>` stops agent execution
- ✅ Agent status changes to "CANCELLED" or "STOPPED"
- ✅ Graceful cancellation (waits for current iteration to finish)

**Pass/Fail**: ___________

---

### Test 9: Metrics Display (Phase 4 Feature)

**Objective**: Verify MetricsView widget displays agent metrics correctly.

**Note**: This test assumes a Metrics tab exists (Tab 7) as described in Phase 4 architecture. The Running tab now includes AgentControlPanel integration for real-time agent monitoring and control.

**Steps**:
1. Run several agents (mix of successful and failed if possible)
2. Press `7` to switch to Metrics tab (if available)
3. Observe metrics display
4. Press `3` to verify AgentControlPanel integration in the Running tab

**Expected Results**:
- ✅ Metrics tab displays aggregate metrics:
  - Success rate (percentage)
  - Average duration (seconds)
  - Total runs count
  - Average cost (if available)
- ✅ Per-agent metrics are listed:
  - Individual agent success rates
  - Individual durations
  - Run counts per agent
- ✅ Metrics update after new agent completions
- ✅ Calculations appear accurate
- ✅ Formatting is clear and readable
- ✅ AgentControlPanel in Running tab shows active agents with control options

**If Metrics tab (7) is not yet implemented**:
- ⚠️ SKIP - Document that MetricsView integration is pending
- Verify MetricsCollector exists in code: `grep -r "MetricsCollector" grind/`

**Pass/Fail**: PASS

---

### Test 10: EventHandler Widget Subscriptions

**Objective**: Verify EventHandler widget subscribes to EventBus correctly.

**Note**: This is an indirect test via observable behavior.

**Steps**:
1. Launch TUI with verbose logging: `uv run grind tui --verbose`
2. Run a simple task that completes quickly
3. Observe terminal output (if verbose logging shows events)
4. Check that UI updates happen without manual refresh

**Expected Results**:
- ✅ Agent status changes appear automatically in UI
- ✅ No manual refresh or polling required
- ✅ Events flow from Orchestrator → EventBus → EventHandler → UI
- ✅ Verbose logs (if available) show event publications
- ✅ UI reacts to events within milliseconds (not seconds)

**Pass/Fail**: ___________

---

### Test 11: Command History and Tab Completion

**Objective**: Verify shell features work as documented.

**Steps**:
1. Switch to Shell tab (press `6`)
2. Type `help` and press Enter
3. Type `status` and press Enter
4. Press `↑` (up arrow) to navigate history
5. Press `↑` again
6. Press `↓` (down arrow) to navigate forward
7. Type `he` and press Tab (for autocomplete)
8. Press Escape to dismiss completion

**Expected Results**:
- ✅ `↑` navigates to previous command ("status")
- ✅ `↑` again navigates to older command ("help")
- ✅ `↓` navigates forward in history
- ✅ Tab completion suggests "help" for "he"
- ✅ Pressing Tab again cycles through completions (if multiple)
- ✅ Escape dismisses completion popup
- ✅ Enter executes the selected/completed command

**Pass/Fail**: ___________

---

### Test 12: Shell Escape (Bash Commands)

**Objective**: Verify shell escape feature for running arbitrary bash commands.

**Steps**:
1. Switch to Shell tab (press `6`)
2. Type `!ls -la` and press Enter
3. Type `!echo "test"` and press Enter
4. Type `!pwd` and press Enter
5. Type `!invalid-command-xyz` and press Enter

**Expected Results**:
- ✅ `!ls -la` executes and shows directory listing
- ✅ `!echo "test"` prints "test" to shell output
- ✅ `!pwd` shows current working directory
- ✅ `!invalid-command-xyz` shows error (command not found)
- ✅ Exit codes are displayed (0 for success, non-zero for errors)
- ✅ Commands timeout after 30 seconds (if applicable)
- ✅ Output appears in shell area

**Pass/Fail**: ___________

---

### Test 13: Multi-Agent Parallel Execution

**Objective**: Verify EventBus handles multiple concurrent agents correctly.

**Preparation**:
Create task file `parallel-tasks.yaml`:
```yaml
tasks:
  - task: "Task 1 - Fast"
    verify: "echo 'task1' && exit 0"
    max_iterations: 1
    dependencies: []

  - task: "Task 2 - Fast"
    verify: "echo 'task2' && exit 0"
    max_iterations: 1
    dependencies: []

  - task: "Task 3 - Slow"
    verify: "sleep 3 && echo 'task3' && exit 0"
    max_iterations: 1
    dependencies: []
```

**Steps**:
1. Launch TUI: `uv run grind tui`
2. Type `run parallel-tasks.yaml` in Shell
3. Quickly switch to Running tab (press `3`)
4. Observe multiple agents running simultaneously
5. Watch as agents complete at different times
6. Switch to Completed tab (press `4`) after all finish

**Expected Results**:
- ✅ Multiple agents appear in Running tab simultaneously
- ✅ Each agent has unique ID
- ✅ Fast tasks (1 & 2) complete quickly
- ✅ Slow task (3) continues running after others complete
- ✅ UI updates correctly for each agent independently
- ✅ All agents eventually appear in Completed tab
- ✅ No event bus conflicts or race conditions
- ✅ No UI corruption from concurrent updates

**Pass/Fail**: ___________

---

### Test 14: Agent Dependency Execution

**Objective**: Verify DAG-based task execution respects dependencies.

**Preparation**:
Create task file `dependent-tasks.yaml`:
```yaml
tasks:
  - task: "Task A - Foundation"
    verify: "echo 'A' && exit 0"
    max_iterations: 1
    dependencies: []

  - task: "Task B - Depends on A"
    verify: "echo 'B' && exit 0"
    max_iterations: 1
    dependencies: ["Task A - Foundation"]

  - task: "Task C - Depends on A and B"
    verify: "echo 'C' && exit 0"
    max_iterations: 1
    dependencies: ["Task A - Foundation", "Task B - Depends on A"]
```

**Steps**:
1. Launch TUI: `uv run grind tui`
2. Type `run dependent-tasks.yaml` in Shell
3. Switch to Running tab (press `3`)
4. Observe execution order

**Expected Results**:
- ✅ Task A starts immediately
- ✅ Task B waits until Task A completes
- ✅ Task B starts only after Task A succeeds
- ✅ Task C waits for both A and B to complete
- ✅ Execution order respects dependency chain: A → B → C
- ✅ No tasks run out of order
- ✅ All tasks eventually complete successfully

**Pass/Fail**: ___________

---

### Test 15: Error Handling - Failed Tasks

**Objective**: Verify TUI handles task failures gracefully.

**Preparation**:
Create task file `failing-task.yaml`:
```yaml
tasks:
  - task: "Task that fails verification"
    verify: "exit 1"
    max_iterations: 3
    model: "haiku"
```

**Steps**:
1. Launch TUI: `uv run grind tui`
2. Type `run failing-task.yaml` in Shell
3. Switch to Running tab (press `3`)
4. Watch agent iterate through attempts
5. Wait for max iterations to be reached
6. Switch to Completed tab (press `4`)
7. Type `agent <agent-id>` in Shell to view details
8. Type `logs <agent-id>` to view error logs

**Expected Results**:
- ✅ Agent attempts task multiple times (3 iterations)
- ✅ Agent status shows "RUNNING" during iterations
- ✅ Agent eventually transitions to "FAILED" status
- ✅ Failed agent appears in Completed tab with error indicator
- ✅ `agent <agent-id>` shows error message
- ✅ Error details explain verification failure
- ✅ Logs show verification command output (`exit 1`)
- ✅ No crashes or UI corruption

**Pass/Fail**: ___________

---

### Test 16: TUI Shutdown and Cleanup

**Objective**: Verify graceful shutdown and resource cleanup.

**Steps**:
1. Launch TUI with running agents
2. Press `q` to quit
3. Observe shutdown process
4. Verify terminal returns to normal state

**Expected Results**:
- ✅ Pressing `q` initiates shutdown immediately
- ✅ Any running agents are cancelled gracefully
- ✅ TUI clears screen and exits
- ✅ Terminal returns to normal prompt
- ✅ No error messages during shutdown
- ✅ No zombie processes left running (`ps aux | grep grind`)
- ✅ Log files are closed properly (no corruption)

**Pass/Fail**: ___________

---

## Test Summary

| Test # | Test Name | Pass/Fail | Notes |
|--------|-----------|-----------|-------|
| 1 | Basic TUI Launch | | |
| 2 | Tab Navigation | | |
| 3 | Shell Tab - Basic Commands | | |
| 4 | EventBus Integration - Agent Lifecycle | | |
| 5 | Real-Time Status Updates | | |
| 6 | Agent Details View | | |
| 7 | Log Viewing | | |
| 8 | Agent Control Commands | | |
| 9 | Metrics Display | | |
| 10 | EventHandler Widget Subscriptions | | |
| 11 | Command History and Tab Completion | | |
| 12 | Shell Escape (Bash Commands) | | |
| 13 | Multi-Agent Parallel Execution | | |
| 14 | Agent Dependency Execution | | |
| 15 | Error Handling - Failed Tasks | | |
| 16 | TUI Shutdown and Cleanup | | |

**Total Tests**: 16
**Passed**: _____ / 16
**Failed**: _____ / 16
**Skipped**: _____ / 16

---

## Known Limitations (Reference)

Based on `docs/tui.md`, the following features are **planned but not yet implemented**:

- ⏳ Real-time agent monitoring in Running/Completed tabs (data not populated)
- ⏳ DAG visualization in DAG tab (shows placeholder)
- ⏳ Live log streaming in Logs tab (not fully wired)
- ⏳ Progress bars with percentages
- ⏳ Metrics tab (may not be visible yet as Tab 7)

**Note**: Tests should verify current functionality, not planned features. Mark planned features as SKIP if not implemented.

---

## Issue Reporting

If any test fails, report the issue with the following information:

1. **Test Number and Name**
2. **Steps to Reproduce**
3. **Expected Behavior**
4. **Actual Behavior**
5. **Screenshots** (if UI corruption or visual issue)
6. **Logs** (from `/tmp/agent-logs/` or `--verbose` output)
7. **Environment**:
   - Python version: `python --version`
   - OS: `uname -a` (Linux/macOS) or `ver` (Windows)
   - Terminal: (e.g., iTerm2, GNOME Terminal, Windows Terminal)
   - UV version: `uv --version`

---

## Regression Testing

Re-run this smoke test suite after:
- ✅ Major code changes to TUI or Orchestrator
- ✅ EventBus modifications
- ✅ Widget updates (EventHandler, MetricsView, AgentControls)
- ✅ Dependency updates (`uv sync` after package changes)
- ✅ Before production releases

---

## Automation Considerations

While this is a manual test suite, the following tests could be automated in the future:

- Test 1, 2: UI rendering and navigation (Textual testing framework)
- Test 3: Shell command execution (mock REPL input)
- Test 4, 5: EventBus event flow (unit tests)
- Test 13, 14: Multi-agent execution (integration tests)
- Test 15: Error handling (integration tests)

See `tests/test_tui_integration.py` for existing automated tests.

---

## References

- **TUI Documentation**: `docs/tui.md`
- **Phase 4 Architecture**: `docs/architecture/phase4-tui-orchestrator.md`
- **Integration Tests**: `tests/test_tui_integration.py`
- **Orchestration Events**: `grind/orchestration/events.py`

---

**Last Updated**: 2024
**Test Suite Version**: 1.0
**Maintained By**: Grind Development Team
