# /generate-tasks

Analyze the conversation context and generate a structured tasks.yaml file for Grind Loop execution.

## What it does

1. Analyzes what you've been discussing with Claude
2. Breaks down the work into concrete, actionable tasks
3. Assigns appropriate models (haiku/sonnet/opus) based on complexity
4. Sets reasonable iteration limits for each task
5. Suggests task dependencies for DAG execution
6. Generates a `tasks.yaml` file ready to use

## Usage

Just type `/generate-tasks` after discussing problems or goals with Claude.

Example conversation:
```
You: I have a Python project with 47 failing tests and several linting errors.
     The tests are in tests/ and code is in src/. I want to fix everything.

You: /generate-tasks
```

Claude will:
- Analyze your discussion
- Create `tasks.yaml` with tasks organized by complexity
- Ask clarifying questions if needed
- Show you the generated file

Once you have `tasks.yaml`, it's ready to use!

## Generated task file format

The generated `tasks.yaml` will look like:

```yaml
tasks:
  - id: "fix-unit-tests"
    task: "Fix failing unit tests in tests/auth/"
    verify: "pytest tests/auth/ -v"
    model: sonnet
    max_iterations: 10
    depends_on: ["lint-fixes"]  # Optional: for DAG mode

  - id: "lint-fixes"
    task: "Fix linting errors with ruff"
    verify: "ruff check src/"
    model: haiku
    max_iterations: 5
```

## Using the generated tasks.yaml

You can run it with any of these commands:

```bash
# Spawn agents in TUI with live monitoring
uv run grind spawn -t tasks.yaml

# Run sequentially (one task at a time)
uv run grind batch tasks.yaml

# Run in parallel with dependencies respected
uv run grind dag tasks.yaml --parallel 3
```

The file is fully editable - tweak the models, iterations, or task descriptions as needed!
