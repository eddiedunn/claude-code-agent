# /generate-tasks

Analyze the conversation context and generate ready-to-run `grind run` commands for each job discussed.

## What it does

1. Reads the conversation to understand what work needs to be done
2. Breaks it into concrete, independently executable jobs
3. For each job, produces a `grind run` command with:
   - `--repo` set to the repo discussed (ask if not clear)
   - `--prompt` describing exactly what Claude should do
   - `--contract-file` OR `--contract-cmd` as the success gate
   - `--model` chosen by complexity (haiku for simple, sonnet for most, opus for hard reasoning)
   - `--max-retries` sized to task risk

## Usage

Type `/generate-tasks` after discussing problems or goals.

Example:
```
You: The auth tests are failing — pytest reports 12 errors in tests/auth/.
     I also want a hello.py file created in the repo root.

You: /generate-tasks
```

Claude will emit:

```bash
# Job 1 — fix auth tests
uv run grind.py run \
  --repo /path/to/repo \
  --prompt "Fix the 12 failing tests in tests/auth/. Run pytest tests/auth/ to see errors." \
  --contract-cmd "pytest tests/auth/ -q --tb=no" \
  --model sonnet \
  --max-retries 3

# Job 2 — create hello.py
uv run grind.py run \
  --repo /path/to/repo \
  --prompt "Create a file named hello.py in the repo root containing: print('hello')" \
  --contract-file hello.py \
  --model haiku \
  --max-retries 2
```

## Contract choice guide

| Situation | Flag to use |
|---|---|
| Claude must create/modify a specific file | `--contract-file <relative-path>` |
| Claude must make a test suite pass | `--contract-cmd "pytest <path> -q --tb=no"` |
| Claude must make a lint check pass | `--contract-cmd "ruff check src/"` |
| Claude must make a build succeed | `--contract-cmd "make build"` |

## Running a job

```bash
# Terminal 1 (optional — live event stream)
uv run grind.py observe

# Terminal 2
uv run grind.py run --repo /path --prompt "..." --contract-cmd "..."

# Inspect events after the job
uv run grind.py show <task-id-printed-above>
```

Exit 0 = contract fulfilled (accepted). Exit 1 = all retries exhausted (failed).
