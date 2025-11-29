# Grind Loop Architecture

## State Machine

The grind loop operates as a state machine with the following states and transitions:

```mermaid
stateDiagram-v2
    [*] --> Initializing: start

    Initializing --> PreGrindHooks: setup_complete
    PreGrindHooks --> Iterating: hooks_done

    Iterating --> CheckingSignals: response_received
    CheckingSignals --> Complete: GRIND_COMPLETE
    CheckingSignals --> Stuck: GRIND_STUCK
    CheckingSignals --> PostIterationHooks: continue

    PostIterationHooks --> Checkpoint: user_interjected
    PostIterationHooks --> Iterating: no_interject

    Checkpoint --> Iterating: continue
    Checkpoint --> Iterating: guidance_injected
    Checkpoint --> Stuck: abort

    Iterating --> MaxIterations: limit_reached

    MaxIterations --> PostGrindHooks
    Complete --> PostGrindHooks
    Stuck --> PostGrindHooks
    Error --> PostGrindHooks

    PostGrindHooks --> [*]: cleanup

    note right of Iterating: Main loop\\nsends CONTINUE_PROMPT\\nto Claude SDK

    note right of Checkpoint: User can:\\n- Continue\\n- Inject guidance\\n- Abort\\n- Run verify
```

## State Descriptions

| State | Description | Exit Conditions |
|-------|-------------|-----------------|
| Initializing | Setup SDK client, build prompt, start keyboard listener | Setup complete |
| PreGrindHooks | Execute pre_grind slash commands | All hooks executed |
| Iterating | Send prompt to SDK, stream response | Response received |
| CheckingSignals | Parse response for GRIND_COMPLETE/STUCK | Signal found or continue |
| PostIterationHooks | Execute post_iteration hooks | Hooks complete |
| Checkpoint | Interactive pause for user input | User decision |
| Complete | Success exit state | Cleanup |
| Stuck | Agent reports inability to proceed | Cleanup |
| MaxIterations | Iteration limit reached | Cleanup |
| Error | Exception occurred | Cleanup |

## DAG Execution

Tasks can declare dependencies on other tasks using the `depends_on` field.
The DAGExecutor runs tasks in topological order, ensuring dependencies
complete before dependents start.

For full documentation, see [DAG Execution Design](dag-execution-design.md).

### DAG State Machine

```mermaid
stateDiagram-v2
    [*] --> Pending: task_created

    Pending --> Ready: dependencies_satisfied
    Pending --> Blocked: dependency_failed

    Ready --> Running: executor_picks_up

    Running --> Completed: GRIND_COMPLETE
    Running --> Failed: GRIND_STUCK/ERROR

    Blocked --> [*]: skip
    Completed --> [*]
    Failed --> [*]

    note right of Blocked: Task skipped because\\nan upstream dependency failed
    note right of Ready: All dependencies in\\nCompleted state
```

### Parallel Execution with Worktrees

When running tasks in parallel (`--parallel N`), use Git worktrees
(`--worktrees`) to isolate each task in its own working directory:

```bash
uv run grind dag tasks.yaml --parallel 3 --worktrees
```

Each task with a `branch` config gets:
1. A worktree at `.worktrees/{task_id}`
2. A new branch created from `base_branch`
3. Optional merges from `merge_from` branches
4. Automatic cleanup on success

### Extended YAML Format

```yaml
tasks:
  - id: lint
    task: "Fix linting"
    verify: "ruff check ."
    branch: fix/lint

  - id: tests
    task: "Fix tests"
    verify: "pytest"
    depends_on: [lint]
    branch: fix/tests
    merge_from: [fix/lint]
```
