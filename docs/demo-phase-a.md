# Phase A Demo — Real Claude executor + grind run / grind show

## Prerequisites

- `claude` CLI installed and on PATH
- Observer running (Terminal 1)
- A fresh git repo (Terminal 2)

---

## Terminal 1 — start the observer

```bash
uv run grind.py observe
```

Leave this running. Events appear in stdout as they arrive.

---

## Terminal 2 — create a demo repo and run a job

```bash
mkdir /tmp/grind-demo && cd /tmp/grind-demo
git init -b main
git commit --allow-empty -m init
```

Now launch the self-evolution loop:

```bash
uv run /Users/tmwsiy/code/claude-code-agent/grind.py run \
  --repo /tmp/grind-demo \
  --prompt "Create a file named hello.py containing: print('hello')" \
  --contract-file hello.py
```

**Expected output:**

```
task_id:  job-20260417-a1b2
status:   accepted
attempts: 1
contract: fulfilled
```

Claude's terminal output streams live while it works. One attempt is enough
because the contract (`hello.py` must exist in the worktree) is satisfied on
the first try.

---

## Terminal 2 — inspect the events

Replace `<task-id>` with the value printed above:

```bash
uv run /Users/tmwsiy/code/claude-code-agent/grind.py show <task-id>
```

**Expected output** (one line per event, oldest first):

```
2026-04-17T10:00:01  agent_spawn               attempt=1
2026-04-17T10:00:01  worktree_spawn
2026-04-17T10:00:15  worktree_teardown
2026-04-17T10:00:15  agent_complete            attempt=1  status=accepted
```

Exit code 0 means the job was accepted; exit code 1 means all retries were
exhausted without satisfying the contract.

---

## Testing --contract-cmd

You can also gate on a shell command returning 0:

```bash
uv run /Users/tmwsiy/code/claude-code-agent/grind.py run \
  --repo /tmp/grind-demo \
  --prompt "Create a file tests/test_hello.py that imports hello and runs it" \
  --contract-cmd "python -c 'import hello'" \
  --max-retries 2
```

The loop runs claude, then executes the command in the worktree. If the command
exits 0 the contract is fulfilled; otherwise the loop retries.
