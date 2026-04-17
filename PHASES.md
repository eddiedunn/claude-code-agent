# Multi-Agent Rewrite — Phase Plan (revised 2026-04-17)

Grind Loop is being rebuilt into a multi-agent orchestration framework. Phases
are built in strict order; each must demo end-to-end before the next starts.

This revision incorporates findings from two March 2026 papers (Tsinghua NLAH;
Stanford MetaHarness) synthesized in PY, "Rethinking AI Agents: The Rise of
Harness Engineering" (2026-04-14). Core takeaway: harness accounts for up to
**6× performance variation** on fixed models; mature harness work is **pruning,
not adding**; **verifiers and multi-candidate search actively hurt** in recent
ablations; the only consistently helpful module was a narrow, acceptance-gated
self-evolution loop.

## Architectural principles (applies to every phase)

1. **Harness = OS.** LLM is the CPU, context is RAM, tools are device drivers.
   The harness coordinates what the model sees and when.
2. **Agent = model + harness.** Prefer harness changes over model changes.
3. **File-backed state.** Agent memory externalized to path-addressable files
   so state survives truncation, restart, and delegation. Worktrees are the
   substrate.
4. **Execution contracts on every agent call.** Required outputs, budget,
   permissions, completion conditions, output paths. Function signatures for
   agents.
5. **Raw traces, never summaries.** Observer stores raw hook events. Summaries
   destroy the signal that downstream optimization needs.
6. **Subtraction over addition.** Every phase ends with a pruning pass. Ask
   what the previous phase let us remove.
7. **Verifiers and broadening are opt-in, not default.** Turn them on only
   with measured evidence that the team fails without them.

## Phase status

| Phase | Topic | Status |
|------:|-------|--------|
| 1 | tmux + observability | COMPLETE — commit c414dd7, 12/12 tests |
| 2 | git worktree isolation as file-backed state | COMPLETE — commit 6427516, 25/25 tests |
| 3 | execution contracts primitive | COMPLETE — commit 74ddb0c, 52/52 tests |
| 4 | agent teams (single self-evolution loop) | COMPLETE — commit 7442e44, 73/73 tests |
| 5 | SDK custom agents via subtraction | COMPLETE — 27/27 tests |
| 6 | orchestrator (planner + generator + using-evaluator) | COMPLETE — 12/12 tests, 100% coverage |
| 7 | harness-as-optimization-target (MetaHarness-style) | NEW — optional |

## Phase 2 — Worktrees as file-backed state

**Goal:** each task runs in an isolated git worktree whose filesystem is the
canonical agent memory. Survives context truncation, restart, and delegation.

- Worktree manager API is framed around state, not just isolation.
- Every worktree has a well-known `state/` subtree that agents read/write.
- Merge strategy: best-of-N worktrees folded back into main only after
  acceptance gates fire.

**Demo:** spawn N worktrees for one task, one claims success, the rest are
torn down, observer shows the full trace.

## Phase 3 — Execution contracts primitive (NEW)

**Goal:** before building teams, define the contract every agent invocation
must specify. This makes traces ablatable and teams debuggable.

Fields on every call:

```
required_outputs:      list of artifact paths or schemas
budget:                max tokens, max wall time, max tool calls
permissions:           allowed tools, denied tools
completion_conditions: how the call declares success
output_paths:          where artifacts land in the worktree
```

- Contract is enforced by the harness, not the prompt.
- Contract violations are first-class trace events.
- Contracts compose — a parent contract constrains child contracts.

**Demo:** a single-agent task with and without a contract. The contracted run
produces a structured trace; the uncontracted run produces prose.

## Phase 4 — Agent teams (was Phase 3)

**Goal:** multi-agent orchestration via `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`.

**Revised design based on PY ablations:**

- Default team shape is a **single self-evolution loop**: one worker, an
  acceptance gate, retry-on-failure with narrow expansion.
- **No reviewer/judge agents by default.** Add only when measured data shows
  the team fails without one. Verifiers hurt SWE-Bench by -0.8 to -8.4 points
  in the Tsinghua ablations.
- **No multi-candidate search by default.** Hurt OSWorld by -5.6 points.
- Parent carries no reasoning — it decomposes, delegates, verifies. 90% of
  compute flows through children.

**Demo:** a coding task where the self-evolution loop recovers from a first
failure without human intervention, and the observer shows the narrow-then-
broaden pattern in the trace.

## Phase 5 — SDK custom agents via subtraction (was Phase 4)

**Goal:** domain-specialized agents built by *removing* tools, not writing
new prompts.

- First pass for every specialized agent: which tools does it NOT need?
- Vercel removed 80% of an agent's tools and got better results — treat that
  as the target ratio, not a ceiling.
- System prompt is secondary to tool restriction.
- Each agent's contract declares its permissions explicitly.

**Demo:** a frontend-only agent and a data-migration agent, each with <20% of
the full tool set, outperforming the generalist on their domain tasks.

## Phase 6 — Orchestrator (was Phase 5)

**Goal:** single interface implementing Anthropic's planner + generator +
evaluator pattern, where the evaluator actually *uses* the output.

- Planner produces a DAG of contracted calls.
- Generator executes them across worktrees.
- **Evaluator clicks through the running app like a real user** — not a
  log reader, not a diff reader. This is the part most orchestrators skip.
- 20× more expensive per Anthropic's own numbers, but the core thing works
  instead of being broken.

**Demo:** orchestrator ships a small UI change end-to-end, and the evaluator
catches a regression the generator didn't see.

## Phase 7 — Harness-as-optimization-target (NEW, optional)

**Goal:** treat the harness itself as the artifact being improved, with raw
traces as input. Analogous to Stanford's MetaHarness.

- A proposer agent reads failed execution traces.
- It diagnoses what broke and writes new harness code.
- An evaluator tests each proposal against a held-out task set.
- The reusable asset is a harness that transfers across models (Haiku with
  an optimized harness outranked larger models in the Stanford results).

**Precondition:** Phases 1–6 have produced a corpus of raw traces large
enough to drive optimization. Don't attempt this before that corpus exists.

**Re-evaluate best-of-N here.** The Phase 4 pruning pass removed `spawn_pool`
/ `accept_from_pool` / `WorktreePool` from `grind/worktree.py` because the
default path doesn't need them. Phase 7 is the natural place to revisit: the
evaluator comparing N harness proposals is exactly the deterministic-gate
best-of-N pattern that the ablations do *not* penalise. Recover the primitives
from git (`git show 7442e44~1:grind/worktree.py`) if Phase 7 needs parallel
candidate harnesses.

## Non-goals

- A universal reviewer agent sitting behind every task.
- Cost-min-maxing before the system works end-to-end.
- A TUI. Deprecated in favor of tmux-native.
- Replacing the DAG executor, worktree manager, models, CLI, or cost-aware
  router. Those stay.

## References

- PY, "Rethinking AI Agents: The Rise of Harness Engineering" (YouTube
  Xxuxg8PcBvc, 2026-04-14) — synthesis of the two papers below.
- Tsinghua, Natural Language Agent Harness (NLAH), March 2026.
- Stanford, MetaHarness (Omar Khattab), March 2026.
- IndyDevDan corpus in Engram: RpUTF_U4kiw, f8RnRuaxee8, 6wR6xblSays,
  9ijnN985O_c, p0mrXfwAbCg.
