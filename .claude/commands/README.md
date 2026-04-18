# Grind Slash Commands

Slash commands for use within Claude Code conversations.

## Available Commands

### `/generate-tasks`

Analyze conversation context and generate a list of `grind run` invocations for the jobs discussed.

**Usage**: Just type `/generate-tasks` after discussing problems or goals.

**Output**: Prints one `grind run` command per job, ready to copy-paste:

```bash
uv run grind.py run \
  --repo /path/to/repo \
  --prompt "Fix failing auth tests" \
  --contract-cmd "pytest tests/auth/ -q" \
  --model sonnet \
  --max-retries 3
```

Each command includes:
- `--repo` — target repository path
- `--prompt` — what Claude should do
- `--contract-file <path>` OR `--contract-cmd "<cmd>"` — how success is verified
- `--model` — haiku / sonnet / opus based on complexity
- `--max-retries` — retry budget

See [generate-tasks.md](generate-tasks.md) for complete details.

## Key CLI flags

### `grind run`

```
--repo PATH           required — absolute path to target repo
--prompt TEXT         required — the task prompt
--contract-file PATH  success = file exists at PATH in worktree
--contract-cmd CMD    success = CMD exits 0 with cwd=worktree
--task-id SLUG        optional slug (default: job-YYYYMMDD-xxxx)
--model NAME          sonnet (default) | opus | haiku
--max-retries N       default 3
--timeout N           per-attempt seconds, default 600
--observer-url URL    default http://localhost:8421
```

Exactly one of `--contract-file` or `--contract-cmd` is required.

### `grind show <task-id>`

```
--db PATH             SQLite DB path (default: ~/.grind/observer.db)
```

Prints one line per observer event: timestamp, event_type, and key payload fields.
Exit 0 if events found, exit 1 if no events for that task-id.

## Installing Commands Globally

```bash
make install-commands
```

Copies all `*.md` files to `~/.claude/commands/` so they work in any project.
