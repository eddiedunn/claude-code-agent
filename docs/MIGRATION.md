# Migration Guide: v1.x to v2.0 (December 2025)

This guide helps you upgrade to Grind v2.0 with intelligent model selection and state-of-the-art orchestration features.

---

## What's New in v2.0

### Major Changes

1. **Default Model Changed: Sonnet → Haiku**
   - Haiku 4.5 is now the default (3-5x cheaper, still highly capable)
   - Override with `--model` flag or in task definitions

2. **Decompose Uses Opus with Extended Thinking**
   - Opus 4.5 for better task analysis and model selection
   - 10K thinking tokens for complex problem decomposition

3. **Intelligent Model Assignment**
   - AI automatically assigns haiku/sonnet/opus per task complexity
   - CostAwareRouter as fallback for automatic routing

4. **Enhanced Tool Access**
   - Decompose now has WebSearch and WebFetch
   - Better codebase research during task breakdown

5. **Interleaved Thinking**
   - Enabled by default for better reasoning
   - Can be disabled per task if needed

---

## Breaking Changes

### 1. Default Model Changed

**Before (v1.x):**
```bash
# Used Sonnet by default
uv run grind run -t "Fix tests" -v "pytest"
# → Used Sonnet 4.5 ($3/$15)
```

**After (v2.0):**
```bash
# Uses Haiku by default
uv run grind run -t "Fix tests" -v "pytest"
# → Uses Haiku 4.5 ($1/$5)
```

**Migration:**

If you relied on Sonnet as default, update your commands:

```bash
# Option 1: Specify model explicitly
uv run grind run -t "Fix tests" -v "pytest" --model sonnet

# Option 2: Update task definitions
tasks:
  - task: "Fix tests"
    verify: "pytest"
    model: sonnet  # Explicitly set
```

### 2. Task YAML Format (Minor Change)

**Before (v1.x):**
```yaml
tasks:
  - task: "Fix tests"
    verify: "pytest"
    # model field optional, defaulted to sonnet
```

**After (v2.0):**
```yaml
tasks:
  - task: "Fix tests"
    verify: "pytest"
    model: haiku  # New default
    # Optional: depends_on field for DAG execution
    # Optional: enable_interleaved_thinking (default: true)
```

**Migration:**

No changes required - existing YAML files work as-is. But you may want to:

1. **Add explicit model selection:**
   ```yaml
   model: sonnet  # If you want old behavior
   ```

2. **Add depends_on for DAG execution:**
   ```yaml
   depends_on: [other_task_id]
   ```

3. **Disable interleaved thinking if needed:**
   ```yaml
   enable_interleaved_thinking: false
   ```

---

## Recommended Migration Path

### Step 1: Update Dependencies

```bash
cd claude_code_agent
uv sync
```

### Step 2: Test with New Defaults

Try a simple task with the new Haiku default:

```bash
uv run grind run -t "Fix linting errors" -v "ruff check ." -m haiku
```

If it works well, you're good to go! Haiku handles most tasks.

### Step 3: Review Existing Task Files

For existing `tasks.yaml` files, decide on migration strategy:

**Option A: Let Haiku Try (Recommended)**

```yaml
# Keep existing tasks, just add model: haiku where missing
tasks:
  - task: "Fix linting"
    verify: "ruff check ."
    # No model specified → uses haiku (new default)
```

**Option B: Preserve Old Behavior**

```yaml
# Explicitly set sonnet to match v1.x behavior
tasks:
  - task: "Fix tests"
    verify: "pytest"
    model: sonnet  # Preserve v1.x default
```

**Option C: Use Decompose for Optimization**

```bash
# Let Opus analyze and assign optimal models
uv run grind decompose \
  -p "Fix all issues" \
  -v "pytest && ruff check ." \
  -o optimized-tasks.yaml

# Compare with existing tasks.yaml
diff tasks.yaml optimized-tasks.yaml
```

### Step 4: Update Scripts/CI

Update any scripts that assume Sonnet:

**Before:**
```bash
#!/bin/bash
# Assumed Sonnet default
uv run grind batch tasks.yaml
```

**After:**
```bash
#!/bin/bash
# Explicit model if needed
uv run grind batch tasks.yaml
# Or edit tasks.yaml to specify models
```

---

## Feature Adoption Guide

### Adopt: Intelligent Decompose

**v1.x approach:**
```bash
# Manual task creation
vim tasks.yaml
# Write tasks by hand
uv run grind batch tasks.yaml
```

**v2.0 approach:**
```bash
# Let Opus with extended thinking decompose
uv run grind decompose \
  -p "Fix all 47 failing tests" \
  -v "pytest tests/ -v" \
  -o tasks.yaml

# Review AI-generated tasks with model assignments
cat tasks.yaml

# Execute
uv run grind dag tasks.yaml --parallel 4
```

**Benefits:**
- Opus assigns optimal models (haiku/sonnet/opus)
- Better task breakdown with extended thinking
- DAG-aware ordering with dependencies

### Adopt: CostAwareRouter

If you're creating tasks programmatically:

**Before:**
```python
from grind.models import TaskDefinition

task = TaskDefinition(
    task="Fix bug",
    verify="pytest",
    model="sonnet"  # Hardcoded
)
```

**After:**
```python
from grind.models import TaskDefinition
from grind.router import CostAwareRouter

router = CostAwareRouter()

task = TaskDefinition(
    task="Fix typo in docs",
    verify="pytest",
    model=router.route_task("Fix typo in docs")  # → "haiku"
)
```

### Adopt: DAG Execution

**v1.x approach:**
```bash
# Sequential execution only
uv run grind batch tasks.yaml
```

**v2.0 approach:**
```bash
# Parallel DAG execution
uv run grind dag tasks.yaml --parallel 4 --worktrees
```

**Update task files with dependencies:**
```yaml
tasks:
  - id: lint
    task: "Fix linting"
    verify: "ruff check ."
    model: haiku

  - id: tests
    task: "Fix tests"
    verify: "pytest"
    model: sonnet
    depends_on: [lint]  # Run after lint completes
```

### Adopt: Interleaved Thinking

**Already enabled by default!** No action needed.

To disable for specific tasks:

```yaml
tasks:
  - task: "Simple linting"
    verify: "ruff check ."
    model: haiku
    enable_interleaved_thinking: false  # Slightly faster
```

---

## Cost Impact Analysis

### Typical Workload (100 tasks)

**v1.x (all Sonnet):**
```
100 tasks × 2M tokens avg × $3/$15 = $1,800
```

**v2.0 (intelligent routing):**
```
70 simple tasks (haiku):   70 × 2M × $1/$5   = $420
25 medium tasks (sonnet):  25 × 2M × $3/$15  = $450
5 complex tasks (opus):     5 × 2M × $5/$25  = $150
Total: $1,020
Savings: $780 (43%)
```

### Your Actual Costs

Use the cost tracking to measure:

```bash
# Run your workload
uv run grind batch tasks.yaml

# Check logs
cat grind.log | grep "total_cost_usd"
```

---

## Common Migration Issues

### Issue: Tasks Taking Longer with Haiku

**Symptom:** Haiku hits max_iterations more often

**Solution:** Increase max_iterations for complex tasks:

```yaml
# v1.x (Sonnet)
- task: "Complex refactoring"
  verify: "pytest"
  model: sonnet
  max_iterations: 10

# v2.0 (Haiku needs more iterations)
- task: "Complex refactoring"
  verify: "pytest"
  model: haiku
  max_iterations: 15  # Give Haiku more tries
```

Or upgrade to Sonnet:

```yaml
- task: "Complex refactoring"
  verify: "pytest"
  model: sonnet  # Use more capable model
  max_iterations: 10
```

### Issue: Decompose Output Changed

**Symptom:** Decompose creates different task breakdown

**Cause:** Opus 4.5 with extended thinking is more sophisticated

**Solution:** Review and adjust:

```bash
# Generate
uv run grind decompose -p "..." -v "..." -o new-tasks.yaml

# Compare with old approach
diff old-tasks.yaml new-tasks.yaml

# Manually adjust if needed
vim new-tasks.yaml
```

### Issue: Unknown Field 'depends_on'

**Symptom:** Old grind version doesn't recognize depends_on

**Solution:** Remove depends_on or upgrade:

```yaml
# Option 1: Remove depends_on
tasks:
  - task: "Fix tests"
    verify: "pytest"
    # depends_on: [lint]  # Comment out for old version

# Option 2: Upgrade grind (recommended)
uv sync
```

---

## Rollback Plan

If you need to rollback temporarily:

### Quick Rollback

```bash
# In your scripts/CI, force Sonnet
uv run grind run -t "..." -v "..." --model sonnet
```

### Task File Rollback

```bash
# Update all tasks to use sonnet
sed -i '' 's/model: haiku/model: sonnet/g' tasks.yaml
```

### Code Rollback

```python
# Override default in code
from grind.models import TaskDefinition

# Monkey-patch the default (not recommended)
TaskDefinition.__dataclass_fields__['model'].default = 'sonnet'
```

---

## Verification Checklist

After migration, verify:

- [ ] Simple tasks work with Haiku
- [ ] Complex tasks automatically use Sonnet/Opus
- [ ] Decompose generates valid task files
- [ ] DAG execution respects dependencies
- [ ] Costs are lower (check logs)
- [ ] CI/CD pipelines pass
- [ ] Task quality is maintained or improved

---

## Getting Help

If you encounter issues:

1. **Check logs:**
   ```bash
   cat grind.log | tail -100
   ```

2. **Use verbose mode:**
   ```bash
   uv run grind run -t "..." -v "..." --verbose
   ```

3. **Force Sonnet temporarily:**
   ```bash
   uv run grind run -t "..." -v "..." --model sonnet
   ```

4. **File an issue:**
   https://github.com/eddiedunn/claude-code-agent/issues

---

## See Also

- [Model Selection Guide](guide/model-selection.md) - Understand model tiers
- [Task Decomposition Guide](guide/decompose.md) - Use Opus decompose
- [Features Guide](guide/features.md) - Complete feature reference
- [DAG Execution](guide/dag-execution.md) - Parallel execution
