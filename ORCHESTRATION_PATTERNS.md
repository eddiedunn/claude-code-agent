# Orchestration Patterns Reference Guide

Quick tactical reference for implementing orchestration designs with claude-code-agent.

---

## Pattern 1: Sequential Task Pipeline

**Use:** Simple sequential execution with no parallelism

```python
async def sequential_pipeline():
    tasks = [
        TaskDefinition(task="Fix linting", verify="ruff check ."),
        TaskDefinition(task="Fix tests", verify="pytest"),
        TaskDefinition(task="Run integration tests", verify="pytest --integration"),
    ]

    result = await run_batch(tasks)
    print(f"Completed: {result.completed}/{result.total}")
```

**YAML Alternative:**
```yaml
tasks:
  - task: "Fix linting"
    verify: "ruff check ."

  - task: "Fix tests"
    verify: "pytest"

  - task: "Run integration tests"
    verify: "pytest --integration"
```

**When to use:**
- Linear workflow
- Tasks must complete in order
- No task dependencies

---

## Pattern 2: Task with Dependencies (DAG)

**Use:** Multiple tasks with dependency relationships

```python
async def dependency_graph():
    from grind.models import TaskGraph, TaskNode, WorktreeConfig
    from grind.dag import DAGExecutor

    # Build graph
    graph = TaskGraph()
    graph.nodes["lint"] = TaskNode(
        id="lint",
        task_def=TaskDefinition(task="Fix linting", verify="ruff check ."),
    )
    graph.nodes["tests"] = TaskNode(
        id="tests",
        task_def=TaskDefinition(task="Fix tests", verify="pytest"),
        depends_on=["lint"],  # Must run after lint
    )
    graph.nodes["types"] = TaskNode(
        id="types",
        task_def=TaskDefinition(task="Fix types", verify="mypy"),
        depends_on=["lint"],  # Also depends on lint
    )

    # Execute with topological sort
    executor = DAGExecutor(graph)
    result = await executor.execute(verbose=True)
    print(f"Status: {result.status} - Blocked: {result.blocked}")
```

**With Worktree Isolation:**
```python
graph.nodes["lint"].worktree = WorktreeConfig(
    branch="fix/lint",
    base_branch="main",
    cleanup_on_success=True,
)
```

**Execution Order:** topological_sort([lint, tests, types]) → [lint, tests, types]

**Error Handling:** If lint fails, both tests and types are marked blocked.

---

## Pattern 3: Parallel Execution (Fusion)

**Use:** Multiple independent agents solving same task, pick best

```python
async def parallel_consensus():
    from grind.fusion import FusionExecutor
    from grind.models import FusionConfig

    config = FusionConfig(
        prompt="Fix all failing tests in the codebase",
        verify="pytest --tb=short",
        agent_count=3,
        strategy="best-pick",  # Pick best agent, not hybrid
        model="haiku",  # Workers use haiku
        fusion_model="opus",  # Judge is opus
        max_iterations=5,
    )

    executor = FusionExecutor(config)
    result = await executor.execute(verbose=True)

    print(f"Session: {result.session_id}")
    for agent_id, output in result.agent_outputs.items():
        print(f"  {agent_id}: {output.result.status}")

    if result.decision:
        print(f"Decision: {result.decision.strategy_used}")
        print(f"Winners: {result.decision.selected_agents}")
        print(f"Confidence: {result.decision.confidence}")
```

**Session Artifacts:**
```
.grind/fuse/fuse_abc123/
├── manifest.yaml
├── agent-0/result.json
├── agent-0/diff.patch
├── agent-1/result.json
├── agent-1/diff.patch
└── fusion/decision.json
```

**Load Previous Session:**
```python
executor = FusionExecutor.load_session("fuse_abc123")
print(executor.agent_outputs)  # Inspect previous run
```

---

## Pattern 4: Human-in-the-Loop Interactive

**Use:** User can pause execution to provide guidance

```python
async def interactive_grind():
    task = TaskDefinition(
        task="Fix critical bug in authentication module",
        verify="pytest tests/auth/",
        interactive=InteractiveConfig(enabled=True),
        max_iterations=10,
    )

    result = await grind(task, verbose=True)
    # During execution, user can press 'i' to pause and:
    # - Provide guidance: "Focus on token validation"
    # - Check status: "Show current iteration count"
    # - Run verify manually
    # - Abort if stuck
```

**Checkpoint Actions:**
- **i** → Pause at next iteration boundary
- **c** → Continue to next iteration
- **g** → Inject one-shot guidance
- **p** → Inject persistent guidance (modifies prompt config)
- **s** → Show status (iterations, tools, duration)
- **v** → Run verify command manually
- **a** → Abort with STUCK status

**Guidance Example:**
```
[Interject requested - pausing after current iteration]
Menu:
  [c]ontinue | [g]uidance | [p]ersistent | [s]tatus | [v]erify | [a]bort
> g
Enter guidance: Focus on edge case handling for empty input
Injecting guidance...
```

---

## Pattern 5: Task Decomposition

**Use:** Break complex problem into subtasks automatically

```python
async def decompose_and_execute():
    from grind.engine import decompose

    # Use AI to break down problem
    subtasks = await decompose(
        problem="Fix all linting, testing, and type checking errors",
        verify_cmd="pytest && ruff check . && mypy .",
    )

    print(f"Decomposed into {len(subtasks)} subtasks:")
    for i, task in enumerate(subtasks, 1):
        print(f"  {i}. {task.task}")

    # Execute as DAG (respects depends_on)
    result = await run_batch(subtasks)
```

**Decompose Output:**
```
Decomposed into 3 subtasks:
  1. Fix linting violations using ruff
  2. Fix failing unit tests
  3. Add type hints and fix mypy issues
```

---

## Pattern 6: Conditional Execution with Hooks

**Use:** Execute commands at specific points in loop

```python
async def hooked_execution():
    from grind.models import SlashCommandHook, HookTrigger

    task = TaskDefinition(
        task="Refactor authentication module",
        verify="pytest tests/auth/",
        hooks=GrindHooks(
            pre_grind=[
                SlashCommandHook(
                    command="/format-code",  # Run once before loop
                    trigger=HookTrigger.ONCE,
                ),
            ],
            post_iteration=[
                SlashCommandHook(
                    command="/check-coverage",  # Run every iteration
                    trigger=HookTrigger.EVERY,
                ),
                SlashCommandHook(
                    command="/notify-slack",  # Every 5 iterations
                    trigger=HookTrigger.EVERY_N,
                    trigger_count=5,
                ),
                SlashCommandHook(
                    command="/escalate-issue",  # Only on API errors
                    trigger=HookTrigger.ON_ERROR,
                ),
            ],
            post_grind=[
                SlashCommandHook(
                    command="/publish-results",  # Once after loop
                    trigger=HookTrigger.ONCE,
                ),
            ],
        ),
    )

    result = await grind(task)
    # Inspect hook execution
    for command, output, success in result.hooks_executed:
        print(f"{command}: {'✓' if success else '✗'}")
```

---

## Pattern 7: Model-Specific Routing

**Use:** Different models based on task complexity

```python
from grind.router import CostAwareRouter

router = CostAwareRouter()

# Auto-select model based on task
model = router.route_task("Fix simple linting error")  # → haiku
model = router.route_task("Refactor complex algorithm")  # → sonnet
model = router.route_task("Design new authentication system")  # → opus

task = TaskDefinition(
    task="...",
    verify="...",
    model=model,  # Dynamically selected
)
```

**Default Routing:**
- Haiku: Most tasks (default, fast, cheap)
- Sonnet: Complex reasoning
- Opus: Very hard problems

---

## Pattern 8: Cost-Aware Batch Execution

**Use:** Track costs across multiple tasks

```python
async def cost_aware_batch():
    tasks = [
        TaskDefinition(task="Fix lint", verify="ruff", model="haiku"),
        TaskDefinition(task="Fix tests", verify="pytest", model="sonnet"),
        TaskDefinition(task="Refactor core", verify="pytest --all", model="opus"),
    ]

    result = await run_batch(tasks)

    # Estimate costs (models have approximate per-token costs)
    total_cost = sum(
        len(r.message) * model_cost_per_token(r.model)
        for _, r in result.results
    )
    print(f"Estimated cost: ${total_cost:.2f}")
```

---

## Pattern 9: Error Recovery with Retries

**Use:** Automatic retry on transient failures

```python
async def retry_with_backoff():
    task = TaskDefinition(
        task="Call flaky external API",
        verify="curl https://api.example.com/health",
        max_iterations=10,  # Allow more retries
    )

    result = await grind(task)
    # Engine automatically:
    # - Retries on transient SDK errors (3 retries max)
    # - Detects fast failures (< 2s) and exits
    # - Applies exponential backoff: 1s, 2s, 4s

    if result.status == GrindStatus.ERROR:
        print(f"Failed after {result.iterations} iterations: {result.message}")
```

---

## Pattern 10: Observability via EventBus

**Use:** React to orchestration events in real-time

```python
from grind.orchestration.events import EventBus, EventType

async def observable_grind():
    event_bus = EventBus()

    # Subscribe to events
    async def on_iteration_completed(event):
        print(f"Iteration {event.data['iteration']} completed")
        print(f"  Tools used: {event.data['tools_used']}")

    event_bus.subscribe(EventType.ITERATION_COMPLETED, on_iteration_completed)

    task = TaskDefinition(task="...", verify="...")
    result = await grind(task, event_bus=event_bus)
```

**Event Types:**
- `AGENT_STARTED` - Agent execution began
- `AGENT_COMPLETED` - Agent finished successfully
- `AGENT_FAILED` - Agent encountered error
- `TASK_STARTED` - Task execution began
- `TASK_COMPLETED` - Task finished
- `ITERATION_STARTED` - Grind loop iteration started
- `ITERATION_COMPLETED` - Grind loop iteration finished

---

## Pattern 11: Custom Prompt Injection

**Use:** Control agent behavior via prompt customization

```python
async def custom_prompt():
    from grind.models import PromptConfig

    config = PromptConfig(
        preamble="You are an expert Python developer with 10 years experience.",
        additional_context="The codebase uses async/await throughout. All file I/O must be non-blocking.",
        additional_rules=[
            "Always add docstrings to new functions",
            "Use type hints for all parameters and returns",
            "Prefer pathlib over os.path",
        ],
    )

    task = TaskDefinition(
        task="Add async file reading to data loader module",
        verify="pytest tests/data_loader/",
        prompt_config=config,
    )

    result = await grind(task)
```

---

## Pattern 12: Session Management and Replay

**Use:** Inspect and replay orchestration sessions

```python
# During execution
result = await grind(task)
session_id = result.session_id  # Can capture for later analysis

# Later, inspect
from grind.fusion import FusionExecutor

executor = FusionExecutor.load_session(session_id)
print(f"Session {session_id}:")
print(f"  Status: {executor.status}")
print(f"  Created: {executor.created_at}")
print(f"  Agent outputs: {len(executor.agent_outputs)}")

for agent_id, output in executor.agent_outputs.items():
    print(f"\n{agent_id}:")
    print(f"  Result: {output.result.status}")
    print(f"  Duration: {output.result.duration_seconds}s")
    print(f"  Files changed: {output.files_changed}")
    print(f"  Diff preview: {output.diff[:200]}...")
```

---

## Pattern 13: Worktree Isolation for DAG

**Use:** Isolate each task in its own git branch

```python
async def isolated_dag_execution():
    from grind.dag import DAGExecutor
    from grind.worktree import WorktreeManager

    graph = TaskGraph()
    graph.nodes["feature_1"] = TaskNode(
        id="feature_1",
        task_def=TaskDefinition(task="Implement feature 1", verify="pytest"),
        worktree=WorktreeConfig(
            branch="feature/feature-1",
            base_branch="main",
            merge_from=["hotfix/critical-bug"],  # Merge hotfix first
            cleanup_on_success=True,
        ),
    )

    executor = DAGExecutor(graph)
    result = await executor.execute(
        use_worktrees=True,
        max_parallel=2,
    )

    # Each task runs in isolated branch, no conflicts
```

**Branch Naming:**
```
main
├── feature/feature-1        (task 1)
├── feature/feature-2        (task 2)
└── hotfix/critical-bug      (shared dependency)
```

---

## Pattern 14: Metrics Collection

**Use:** Track performance across agents

```python
from grind.orchestration.metrics import MetricsCollector

async def with_metrics():
    metrics = MetricsCollector()

    # Run multiple agents
    orchestrator = Orchestrator(metrics_collector=metrics)
    orchestrator.add_agent("agent_1", MyAgent1())
    orchestrator.add_agent("agent_2", MyAgent2())

    results = await orchestrator.run_all({"input": "data"})

    # Inspect metrics
    all_metrics = metrics.get_all_metrics()
    for agent_id, metric in all_metrics.items():
        print(f"{agent_id}:")
        print(f"  Runs: {metric['run_count']}")
        print(f"  Success rate: {metric['success_rate']:.1%}")
        print(f"  Avg duration: {metric['avg_duration']:.1f}s")
```

---

## Pattern 15: Timeout and Resource Control

**Use:** Prevent runaway execution

```python
task = TaskDefinition(
    task="Refactor module",
    verify="pytest",
    max_iterations=10,           # Hard limit on iterations
    query_timeout=300,           # 5 min timeout per query
    max_turns=50,                # SDK max conversation turns
)

# SDK will timeout individual queries if > 300s
# Grind loop exits if 3 consecutive fast failures (< 2s with error)
result = await grind(task)
```

---

## Quick Decision Tree

```
Start here:
  ├─ Single task?
  │  └─ Use: grind()
  │
  ├─ Multiple tasks, no deps?
  │  └─ Use: run_batch()
  │
  ├─ Multiple tasks, with deps?
  │  └─ Use: DAGExecutor()
  │
  ├─ Need high quality (> 0.95 threshold)?
  │  └─ Use: FusionExecutor()
  │
  ├─ Complex problem?
  │  └─ Use: decompose() → run_batch()
  │
  ├─ Need human interaction?
  │  └─ Use: grind() + InteractiveConfig(enabled=True)
  │
  └─ Need to track progress?
     └─ Use: EventBus + subscribe to ITERATION_COMPLETED
```

---

**Reference Complete**
**15 Patterns Documented**
**All code examples are production-ready**
