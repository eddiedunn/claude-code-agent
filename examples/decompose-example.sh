#!/bin/bash
# Example: Using decompose to break down complex problems with intelligent model selection
#
# This script demonstrates how grind's decompose feature analyzes a problem,
# breaks it into subtasks, and assigns the appropriate model based on complexity.

set -e

echo "=================================="
echo "GRIND DECOMPOSE EXAMPLE"
echo "=================================="
echo ""
echo "This example shows how decompose breaks down complex problems into"
echo "independent subtasks with intelligent model assignment."
echo ""

# Example 1: Before decompose - Manual task creation
echo "## BEFORE: Manual Task Creation"
echo "You might manually create tasks.yaml with guesses about complexity:"
echo ""
cat << 'EOF'
tasks:
  - task: "Fix all the issues"
    verify: "pytest && ruff check && mypy ."
    model: sonnet  # One big task, unclear which model is best
    max_iterations: 20
EOF
echo ""
echo "Problems with this approach:"
echo "  - One giant task is harder to debug"
echo "  - Can't parallelize independent fixes"
echo "  - Model selection is a guess (might be overkill or insufficient)"
echo "  - No dependency ordering"
echo ""

# Example 2: Using decompose
echo "## AFTER: Using Decompose"
echo ""
echo "Command:"
echo '  uv run grind decompose \'
echo '    --problem "Fix all failing tests, linting, and type errors" \'
echo '    --verify "pytest && ruff check && mypy ." \'
echo '    --output tasks.yaml'
echo ""
echo "What decompose does:"
echo "  1. Runs the verification command to see actual failures"
echo "  2. Researches the codebase to understand context"
echo "  3. Analyzes complexity of each issue"
echo "  4. Groups related issues"
echo "  5. Orders tasks by dependencies (DAG-aware)"
echo "  6. Assigns appropriate model (haiku/sonnet/opus)"
echo ""

# Example output showing intelligent decomposition
echo "Example decompose output:"
echo ""
cat << 'EOF'
tasks:
  # Simple formatting issues -> haiku (fast & cheap)
  - task: "Fix ruff formatting errors in src/"
    verify: "ruff check src/ --select W"
    model: haiku
    max_iterations: 3

  # Import organization -> haiku (straightforward)
  - task: "Fix unused imports flagged by ruff"
    verify: "ruff check . --select F401"
    model: haiku
    max_iterations: 3

  # Type errors requiring investigation -> sonnet (balanced)
  - task: "Fix mypy type errors in auth module"
    verify: "mypy src/auth/"
    model: sonnet
    max_iterations: 5

  # Complex logic bugs -> sonnet (needs understanding)
  - task: "Fix failing integration tests in test_api.py"
    verify: "pytest tests/test_api.py -v"
    model: sonnet
    max_iterations: 8

  # Security-sensitive authentication -> opus (critical)
  - task: "Fix authentication bypass vulnerability"
    verify: "pytest tests/security/ -v && bandit -r src/auth/"
    model: opus
    max_iterations: 10
EOF
echo ""

# Explain the benefits
echo "## Benefits of Decompose"
echo ""
echo "1. **Intelligent Model Selection**"
echo "   - haiku: Simple fixes (fast, cheap, effective)"
echo "   - sonnet: Medium complexity (balanced)"
echo "   - opus: Critical/complex tasks (powerful when needed)"
echo ""
echo "2. **Better Parallelization**"
echo "   - Independent tasks can run concurrently"
echo "   - Saves time on large problem sets"
echo ""
echo "3. **Easier Debugging**"
echo "   - Smaller, focused tasks"
echo "   - Clear verification per task"
echo "   - Know exactly which subtask failed"
echo ""
echo "4. **Cost Optimization**"
echo "   - Don't use opus for simple fixes"
echo "   - Use right model for the job"
echo "   - Can save 10-50x on API costs"
echo ""
echo "5. **DAG-Aware Ordering**"
echo "   - Prerequisites run first"
echo "   - Respects file/logical dependencies"
echo "   - Prevents wasted work on dependent tasks"
echo ""

# Model selection guidelines
echo "## Model Selection Guidelines"
echo ""
echo "decompose chooses models based on these criteria:"
echo ""
echo "**haiku** - Fast, efficient for simple tasks:"
echo "  - Straightforward bug fixes with clear root cause"
echo "  - Simple refactoring (rename, extract function)"
echo "  - Adding basic tests or documentation"
echo "  - Minor configuration changes"
echo "  - Cosmetic/formatting changes"
echo ""
echo "**sonnet** - Balanced for medium complexity:"
echo "  - Multi-file refactoring requiring coordination"
echo "  - Feature additions with moderate logic"
echo "  - Bug fixes requiring investigation"
echo "  - Test implementation requiring behavior understanding"
echo "  - Integration of existing APIs or libraries"
echo ""
echo "**opus** - Most capable for complex/critical:"
echo "  - Architecture decisions and design"
echo "  - Security-sensitive changes (auth, validation, encryption)"
echo "  - Performance optimization requiring deep analysis"
echo "  - Complex algorithms or data structures"
echo "  - Breaking changes requiring careful migration"
echo "  - Critical bug fixes with unclear root cause"
echo ""

# Try it yourself section
echo "## Try It Yourself"
echo ""
echo "Step 1: Run decompose on your problem"
echo '  uv run grind decompose \'
echo '    --problem "Your problem description" \'
echo '    --verify "your-verification-command" \'
echo '    --output my-tasks.yaml'
echo ""
echo "Step 2: Review the generated tasks"
echo "  cat my-tasks.yaml"
echo ""
echo "Step 3: Run the batch"
echo "  uv run grind batch my-tasks.yaml"
echo ""
echo "Or use /generate-tasks slash command in Claude Code conversation!"
echo ""

# Real-world example
echo "## Real-World Example"
echo ""
echo "Problem: 47 failing pytest tests across multiple modules"
echo ""
echo "Without decompose:"
echo "  - One 30+ iteration task"
echo "  - Uses opus for everything"
echo "  - Hard to track progress"
echo "  - Cost: ~$5"
echo ""
echo "With decompose:"
echo "  - 8 targeted tasks"
echo "  - 4 with haiku, 3 with sonnet, 1 with opus"
echo "  - Run in parallel (faster)"
echo "  - Total ~12 iterations across all tasks"
echo "  - Cost: ~$1"
echo ""
echo "Savings: 5x cost reduction, 3x faster, easier to debug"
echo ""

echo "=================================="
echo "END OF EXAMPLE"
echo "=================================="
