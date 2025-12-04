# Intelligent Model Selection

Grind uses Claude 4.5 models with intelligent routing to optimize cost, speed, and quality for each task.

---

## Overview

As of December 2025, Grind implements state-of-the-art model selection using:
- **Opus 4.5** with extended thinking for task decomposition and planning
- **CostAwareRouter** for automatic model assignment based on complexity
- **Haiku 4.5** as the default for fast, cost-effective execution
- **Interleaved thinking** for improved reasoning between tool calls

---

## Model Tiers

### Haiku 4.5 (Default)

**Use for:** Simple, straightforward tasks (70-80% of typical workloads)

**Characteristics:**
- **Speed**: Fastest model (2-3x faster than Sonnet)
- **Cost**: $1/$5 per million tokens (5x cheaper than Opus)
- **Capability**: 73.3% on SWE-bench Verified (near-frontier performance)
- **Best for**: Fix-verify loops with clear objectives

**Examples:**
```yaml
- task: "Fix ruff linting errors in src/"
  verify: "ruff check src/"
  model: haiku  # Fast, efficient

- task: "Remove unused imports"
  verify: "ruff check --select F401 ."
  model: haiku

- task: "Fix typos in docstrings"
  verify: "pytest tests/test_docs.py"
  model: haiku

- task: "Update version number to 2.0.0"
  verify: "grep -q '2.0.0' pyproject.toml"
  model: haiku
```

**When Haiku is enough:**
- Linting and formatting fixes
- Simple bug fixes with clear error messages
- Adding basic tests or documentation
- Configuration updates
- Code cleanup (removing unused code, fixing imports)

---

### Sonnet 4.5 (Balanced)

**Use for:** Medium complexity tasks (15-25% of workloads)

**Characteristics:**
- **Speed**: Balanced performance
- **Cost**: $3/$15 per million tokens
- **Capability**: 77.2% on SWE-bench Verified
- **Best for**: Multi-file changes, integration work, complex debugging

**Examples:**
```yaml
- task: "Refactor authentication module to use JWT"
  verify: "pytest tests/auth/ -v"
  model: sonnet  # Multiple files, integration

- task: "Fix race condition in user session handling"
  verify: "pytest tests/concurrent/ -v"
  model: sonnet  # Requires deep analysis

- task: "Add pagination to REST API endpoints"
  verify: "pytest tests/api/ -v"
  model: sonnet  # Feature across multiple files

- task: "Debug intermittent test failures"
  verify: "pytest tests/flaky/ -v --count=10"
  model: sonnet  # Requires investigation
```

**When to upgrade to Sonnet:**
- Multi-file refactoring (5+ files)
- Features requiring coordination across modules
- Bug fixes requiring investigation
- Complex test implementation
- Integration of third-party libraries

---

### Opus 4.5 (Maximum Capability)

**Use for:** Planning, architecture, and complex reasoning (5-10% of workloads)

**Characteristics:**
- **Speed**: Slower, but with extended thinking for deep reasoning
- **Cost**: $5/$25 per million tokens (down from $15/$75 in Opus 4.1!)
- **Capability**: 80.9% on SWE-bench Verified (best in class)
- **Best for**: Strategic planning, security, architecture decisions

**Examples:**
```yaml
- task: "Design caching layer for high-traffic API"
  verify: "pytest tests/cache/ -v"
  model: opus  # Architecture decision

- task: "Security audit of authentication system"
  verify: "pytest tests/security/ -v"
  model: opus  # Security-critical

- task: "Optimize database query performance"
  verify: "pytest tests/benchmark/ -v"
  model: opus  # Complex optimization

- task: "Migrate from REST to GraphQL"
  verify: "pytest tests/ -v"
  model: opus  # Major architecture change
```

**When to use Opus:**
- Architecture and design decisions
- Security-sensitive code (auth, encryption, validation)
- Performance optimization requiring deep analysis
- Complex algorithms or data structures
- Breaking changes requiring careful migration
- Critical bugs with unclear root cause

---

## Automatic Model Selection

Grind uses two mechanisms for intelligent model assignment:

### 1. AI-Driven Selection (Decompose)

When you use `grind decompose`, **Opus 4.5 with extended thinking** analyzes your problem and assigns the appropriate model to each task:

```bash
uv run grind decompose \
  --problem "Fix 47 failing tests and linting errors" \
  --verify "pytest && ruff check ." \
  --output tasks.yaml
```

**Opus analyzes and outputs:**
```yaml
tasks:
  - task: "Fix import order violations"
    verify: "ruff check --select I ."
    model: haiku  # Simple, fast
    max_iterations: 3

  - task: "Fix race condition in async tests"
    verify: "pytest tests/async/ -v"
    model: sonnet  # Requires investigation
    max_iterations: 10

  - task: "Redesign caching strategy for correctness"
    verify: "pytest tests/cache/ -v"
    model: opus  # Architecture decision
    max_iterations: 15
```

**Why Opus for decompose?**
- Extended thinking enables multi-step planning
- 80.9% capability for complex problem analysis
- Better at identifying dependencies and ordering
- More accurate complexity assessment

### 2. CostAwareRouter (Fallback)

If the AI doesn't specify a model, the `CostAwareRouter` uses heuristics:

```python
from grind.router import CostAwareRouter

router = CostAwareRouter()

# Simple tasks → haiku
router.route_task("Fix typo in README")  # → "haiku"
router.route_task("Remove unused imports")  # → "haiku"

# Medium tasks → sonnet
router.route_task("Refactor auth module")  # → "sonnet"
router.route_task("Add API pagination")  # → "sonnet"

# Complex tasks → opus
router.route_task("Design caching architecture")  # → "opus"
router.route_task("Security audit of auth")  # → "opus"
```

**Router keywords:**

**Simple (haiku):**
- typo, spelling, format, indent, whitespace
- comment, rename, delete, remove
- version bump, simple fix

**Complex (opus):**
- architecture, redesign, migrate, migration
- authentication, authorization, security
- optimization, performance, scale
- distributed, microservice

**Medium (sonnet):**
- Everything else (default for medium complexity)

---

## Cost Optimization

### Typical Workload (100 tasks)

**Before (all Sonnet):**
```
100 tasks × 2M tokens avg × $3/$15 = $1,800
```

**After (intelligent routing):**
```
70 tasks × 2M tokens × $1/$5 (haiku)    = $420
25 tasks × 2M tokens × $3/$15 (sonnet)  = $450
5 tasks × 2M tokens × $5/$25 (opus)     = $150
Total: $1,020
```

**Savings: 43% cost reduction** with same or better quality

### Real-World Example

**Project:** Fix 47 failing tests + lint errors

**Manual approach (all Sonnet):**
- 47 tasks × ~1.5M tokens × $3/$15 = ~$850

**Intelligent routing:**
- 30 lint fixes (haiku): $150
- 15 test fixes (sonnet): $340
- 2 architecture fixes (opus): $100
- **Total: $590 (30% savings)**

---

## Extended Thinking

Opus 4.5 and Sonnet 4.5 support **extended thinking** for tasks requiring deep reasoning.

### What is Extended Thinking?

Extended thinking allocates more "reasoning budget" for:
- Multi-step planning
- Long-horizon problem solving
- Tool orchestration
- Complex decision-making

**Trade-off:** Higher latency and token usage, but better results.

### When It's Used

**Automatically enabled for:**
- `grind decompose` (Opus with 10K thinking tokens)
- Tasks marked with `enable_extended_thinking: true`

**Example:**
```yaml
tasks:
  - task: "Design microservices architecture"
    verify: "pytest tests/architecture/ -v"
    model: opus
    enable_extended_thinking: true  # More reasoning time
    max_iterations: 20
```

### Configuration

```python
# In TaskDefinition
enable_extended_thinking: bool = True  # Default enabled

# In decompose (grind/engine.py)
options = ClaudeAgentOptions(
    model="opus",
    max_thinking_tokens=10000,  # 10K tokens for extended thinking
)
```

---

## Interleaved Thinking

**New in December 2025:** Interleaved thinking enables Claude to think between tool calls.

### What is Interleaved Thinking?

Traditional flow:
```
Think → Use Tool → Get Result → Respond
```

Interleaved thinking:
```
Think → Use Tool → Get Result → Think → Use Tool → Get Result → Respond
```

This enables:
- More sophisticated reasoning after tool results
- Better tool orchestration
- Improved multi-step workflows

### Enabling Interleaved Thinking

**Enabled by default** for all models in Grind:

```python
# TaskDefinition (grind/models.py)
enable_interleaved_thinking: bool = True
```

**To disable:**
```yaml
tasks:
  - task: "Simple linting fix"
    verify: "ruff check ."
    model: haiku
    enable_interleaved_thinking: false  # Faster for simple tasks
```

### Beta Header

Grind automatically adds the beta header when enabled:

```python
# grind/engine.py
if task_def.enable_interleaved_thinking:
    extra_args["anthropic-beta"] = "interleaved.thinking-2025-02-26"
```

---

## Best Practices

### 1. Start with Haiku

**Default to haiku** unless you know you need more:

```yaml
# ✅ Good - let haiku try first
- task: "Fix failing auth tests"
  verify: "pytest tests/auth/ -v"
  model: haiku
  max_iterations: 5

# ⚠️ If haiku gets stuck, upgrade to sonnet
```

### 2. Use Decompose for Planning

Let **Opus with extended thinking** do the strategic planning:

```bash
# Opus analyzes and breaks down the problem
uv run grind decompose -p "Fix all issues" -v "make test" -o tasks.yaml

# Then execute with appropriate models
uv run grind dag tasks.yaml --parallel 4
```

### 3. Override When Needed

The AI's model selection is a suggestion - override if you know better:

```yaml
tasks:
  - task: "Fix typo in config"
    verify: "grep -q 'correct' config.yaml"
    model: haiku  # AI suggested sonnet, but haiku is fine

  - task: "Debug race condition"
    verify: "pytest tests/concurrent/ -v --count=20"
    model: opus  # AI suggested sonnet, but this is complex
```

### 4. Monitor and Adjust

Track which models work for your workload:

```bash
# After running tasks
cat grind.log | grep "model=" | sort | uniq -c

# Adjust future task definitions based on results
```

### 5. Cost-Performance Trade-offs

**Optimize for cost:**
```yaml
model: haiku
max_iterations: 10  # Give haiku more tries
```

**Optimize for speed:**
```yaml
model: sonnet
max_iterations: 5  # Use more capable model with fewer iterations
```

**Optimize for quality:**
```yaml
model: opus
max_iterations: 15
enable_extended_thinking: true
```

---

## Pricing Reference (December 2025)

| Model | Input ($/1M tokens) | Output ($/1M tokens) | SWE-bench Score | Use Case |
|-------|-------------------|---------------------|----------------|----------|
| Haiku 4.5 | $1.00 | $5.00 | 73.3% | Default, high volume |
| Sonnet 4.5 | $3.00 | $15.00 | 77.2% | Medium complexity |
| Opus 4.5 | $5.00 | $25.00 | 80.9% | Planning, architecture |

**Note:** Opus 4.5 is 67% cheaper than Opus 4.1 ($15/$75), making it viable for more use cases.

---

## Migration from Previous Versions

### If You're Upgrading from Sonnet-Default

**Before (v1.x):**
```yaml
tasks:
  - task: "Fix tests"
    verify: "pytest"
    # model: sonnet (implicit default)
```

**After (v2.x):**
```yaml
tasks:
  - task: "Fix tests"
    verify: "pytest"
    model: haiku  # New default
```

**To preserve old behavior:**
```yaml
# In your task files, explicitly set sonnet
model: sonnet
```

Or override CLI default:
```bash
# Use sonnet instead of haiku
uv run grind run -t "Fix tests" -v "pytest" -m sonnet
```

---

## Advanced: Custom Routing Logic

You can extend the `CostAwareRouter` with your own heuristics:

```python
from grind.router import CostAwareRouter

class MyRouter(CostAwareRouter):
    def route_task(self, task_description: str):
        # Custom logic
        if "my-special-pattern" in task_description.lower():
            return "opus"

        # Fall back to default routing
        return super().route_task(task_description)

# Use in decompose or custom scripts
router = MyRouter()
model = router.route_task("Fix my-special-pattern issue")
```

---

## See Also

- [Features Guide](features.md) - Complete feature reference
- [DAG Execution](dag-execution.md) - Parallel task execution
- [Decompose Guide](../getting-started/quickstart.md#3-decompose-mode) - Problem decomposition
- [Cost Tracking](../sdk/tracking-costs-and-usage.md) - Monitor spending
