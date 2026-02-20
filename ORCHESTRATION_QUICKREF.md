# Orchestration Quick Reference

Bookmark this for fast lookups.

## Execution Modes at a Glance

| Mode | Use | Code | Time | Cost |
|------|-----|------|------|------|
| **grind()** | Single task | `await grind(task)` | Varies | 1× |
| **batch** | Sequential tasks | `await run_batch(tasks)` | Sum | N× |
| **DAG** | Dependencies | `DAGExecutor(graph)` | Parallel | N× |
| **Fusion** | High quality | `FusionExecutor(cfg)` | Sum + judge | (N+1)× |

## Result Status Values

```python
GrindStatus.COMPLETE      # Success
GrindStatus.STUCK         # Agent can't proceed
GrindStatus.MAX_ITERATIONS # Iteration limit hit
GrindStatus.ERROR         # Exception occurred
```

## Human Checkpoint Keys

| Key | Action |
|-----|--------|
| `i` | Request interject at next iteration |
| `c` | Continue |
| `g` | One-shot guidance |
| `p` | Persistent guidance |
| `s` | Show status |
| `v` | Run verify command |
| `a` | Abort |

## Hook Triggers

```python
HookTrigger.EVERY        # Every iteration
HookTrigger.EVERY_N      # Every Nth iteration (requires trigger_count)
HookTrigger.ON_ERROR     # Only on API error
HookTrigger.ON_SUCCESS   # Only on success
HookTrigger.ONCE         # First iteration only
```

## Event Types

```python
EventType.AGENT_STARTED
EventType.AGENT_COMPLETED
EventType.AGENT_FAILED
EventType.TASK_STARTED
EventType.TASK_COMPLETED
EventType.ITERATION_STARTED
EventType.ITERATION_COMPLETED
```

## Model Selection

```
Trivial/Simple       → haiku
Moderate             → sonnet
Complex              → sonnet
Very Complex/Quality → opus
```

## Signal Patterns (in agent output)

```
GRIND_COMPLETE                    # Success
GRIND_COMPLETE: Fixed the bug     # Success with message
*GRIND_COMPLETE*                  # Success (markdown bold)
## GRIND_COMPLETE                 # Success (heading)

GRIND_STUCK                       # Agent stuck
GRIND_STUCK: Missing config file  # Stuck with reason
```

## GrindResult Fields

```python
result.status               # COMPLETE | STUCK | MAX_ITERATIONS | ERROR
result.iterations           # How many iterations
result.message              # Terminal message
result.tools_used           # List of tools called
result.duration_seconds     # Wall clock time
result.hooks_executed       # [(cmd, output, success), ...]
result.model                # Which model was used
```

## Common Configurations

### Fast & Cheap (Haiku)
```python
TaskDefinition(
    task="...",
    verify="...",
    model="haiku",
    max_iterations=5,
    max_turns=25,
)
```

### Balanced (Sonnet)
```python
TaskDefinition(
    task="...",
    verify="...",
    model="sonnet",
    max_iterations=10,
    max_turns=50,
)
```

### Best Quality (Opus)
```python
TaskDefinition(
    task="...",
    verify="...",
    model="opus",
    max_iterations=15,
    max_turns=75,
)
```

### Interactive Mode
```python
task.interactive = InteractiveConfig(enabled=True)
# Now user can press 'i' during execution
```

### With Hooks
```python
from grind.models import SlashCommandHook, HookTrigger, GrindHooks

task.hooks = GrindHooks(
    pre_grind=[SlashCommandHook("/setup", trigger=HookTrigger.ONCE)],
    post_iteration=[SlashCommandHook("/notify", trigger=HookTrigger.EVERY)],
    post_grind=[SlashCommandHook("/cleanup", trigger=HookTrigger.ONCE)],
)
```

## Fusion Configuration Quick-Picks

### Consensus (3 agents, best-pick)
```python
FusionConfig(
    prompt="...",
    verify="...",
    agent_count=3,
    strategy="best-pick",
    model="haiku",
    fusion_model="opus",
)
```

### Hybrid (5 agents, combine best)
```python
FusionConfig(
    prompt="...",
    verify="...",
    agent_count=5,
    strategy="hybrid",
    model="sonnet",
    fusion_model="opus",
)
```

## DAG Configuration

### Simple Dependency Chain
```python
graph = TaskGraph()
graph.nodes["task1"] = TaskNode(id="task1", task_def=t1)
graph.nodes["task2"] = TaskNode(id="task2", task_def=t2, depends_on=["task1"])
graph.nodes["task3"] = TaskNode(id="task3", task_def=t3, depends_on=["task2"])
executor = DAGExecutor(graph)
result = await executor.execute()
```

### Parallel with Shared Dependency
```python
graph = TaskGraph()
graph.nodes["base"] = TaskNode(id="base", task_def=base_task)
graph.nodes["a"] = TaskNode(id="a", task_def=task_a, depends_on=["base"])
graph.nodes["b"] = TaskNode(id="b", task_def=task_b, depends_on=["base"])
graph.nodes["merge"] = TaskNode(id="merge", task_def=merge_task, depends_on=["a", "b"])
executor = DAGExecutor(graph)
result = await executor.execute()
```

## Session Data Locations

```
.grind/
├── logs/                          # Structured logs
│   └── {timestamp}_{task_id}/
│       ├── summary.md
│       └── full.log
├── fuse/                          # Fusion sessions
│   └── fuse_abc123/
│       ├── manifest.yaml
│       ├── agent-0/result.json
│       ├── agent-0/diff.patch
│       └── fusion/decision.json
└── trajectories/                  # Execution traces (future)
    └── trajectory_xyz.json
```

## Debugging Tips

### Check if task succeeded
```python
if result.status == GrindStatus.COMPLETE:
    print("✅ Success!")
```

### See what tools were used
```python
print(f"Tools: {result.tools_used}")
```

### See hook execution
```python
for cmd, output, success in result.hooks_executed:
    print(f"{cmd}: {'✓' if success else '✗'}")
```

### Check convergence
```python
print(f"Converged in {result.iterations} iterations")
```

### See fusion decision
```python
if result.decision:
    print(f"Winners: {result.decision.selected_agents}")
    print(f"Confidence: {result.decision.confidence}")
```

### Load previous fusion session
```python
executor = FusionExecutor.load_session("fuse_abc123")
for agent_id, output in executor.agent_outputs.items():
    print(f"{agent_id}: {output.result.status}")
```

## Exit Codes (Batch/CLI)

| Code | Meaning |
|------|---------|
| 0 | All tasks completed successfully |
| 1 | One or more tasks failed/errored |
| 2 | One or more tasks stuck |
| 3 | One or more tasks hit max iterations |

## Cost Estimation

**Rough approximations (actual depends on response length):**

```
Haiku:   $0.003 per 1K tokens
Sonnet:  $0.015 per 1K tokens  (~5× more expensive)
Opus:    $0.060 per 1K tokens  (~20× more expensive)
```

**Example:**
- Simple task, haiku, 2 iterations: $0.01-0.05
- Complex task, opus, 10 iterations: $0.50-2.00

## Performance Tips

1. **Use haiku by default** (80% of tasks work fine)
2. **Escalate on failure** (retry with sonnet/opus if stuck)
3. **Limit max_iterations** (prevents runaway costs)
4. **Use DAG for parallel tasks** (saves time and cost)
5. **Use fusion for critical paths** (worth the extra cost)
6. **Set query_timeout** (prevent stuck client)
7. **Use worktrees** (parallel tasks don't interfere)

## Common Mistakes

❌ Not checking result.status before using message
❌ Using opus for trivial tasks (overkill)
❌ Running parallel agents without worktrees (git conflicts)
❌ Not setting max_iterations (runaway cost risk)
❌ Interactive mode in CI/CD (blocks forever)
❌ Assuming agent completes just because no error (check signals!)

## One-Liners

```bash
# Single task
uv run grind.py run -t "Fix linting" -v "ruff check ."

# Batch from file
uv run grind.py batch tasks.yaml

# Batch with parallelism
uv run grind.py dag tasks.yaml --parallel 4

# Fusion (3 agents)
uv run grind.py fusion -p "Fix tests" -v "pytest" --agents 3

# Decompose large problem
uv run grind.py decompose -p "Fix everything" -v "pytest"

# Interactive mode
uv run grind.py run -t "..." -v "..." --interactive
```

---

**Keep this tab open while developing!**
