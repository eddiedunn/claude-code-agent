from grind.models import PromptConfig

GRIND_PROMPT = """
You are in an automated fix-verify loop. Your mission:

## TASK
{task}

## VERIFICATION
Run this command to check success: `{verify_cmd}`

## PROCESS
1. First, run the verification command to see current state
2. Analyze the failures/errors carefully
3. Make targeted fixes (prefer minimal, focused changes)
4. Run verification again
5. Repeat until verification passes

## BEST PRACTICES (Claude 4.5 Agent Guidance)
- **Strategic thinking**: Analyze the problem, consider multiple approaches, then choose the best path
- **tool orchestration**: Use multiple tools in parallel when possible to maximize efficiency
- **Iterative refinement**: Start with working code, then improve through measured iterations
- **Verify assumptions**: Test your understanding before making large changes
- **Context awareness**: Read relevant files to understand patterns before modifying code

## SIGNALS (use these exact strings in your response)
- When verification passes completely: say "GRIND_COMPLETE"
- If you're stuck and need human help: say "GRIND_STUCK: <reason>"
- To report progress: say "GRIND_PROGRESS: <summary>"

## RULES
- Focus on ONE issue at a time when possible
- After each fix, re-run verification to confirm
- Don't make speculative changes - verify each step
- If the same fix fails twice, try a different approach

Begin by running the verification command.
"""

CONTINUE_PROMPT = (
    "Continue. Check verification status and fix remaining issues. "
    "Signal GRIND_COMPLETE when done, or GRIND_STUCK if you need help."
)

DECOMPOSE_PROMPT = """
Analyze this problem and break it into independent subtasks with intelligent model selection.

## PROBLEM
{problem}

## VERIFICATION COMMAND
{verify_cmd}

## YOUR TASK
1. Run the verification command to see failures
2. Research the codebase to understand context and dependencies
3. Analyze complexity and determine appropriate model for each subtask
4. Group related issues that should be fixed together
5. Order tasks by DAG dependencies (prerequisites first)
6. Output a JSON task list with model assignments

## MODEL SELECTION GUIDELINES
Choose the appropriate model based on task complexity:

**haiku** - Fast, efficient model for simple tasks:
- Straightforward bug fixes with clear root cause
- Simple refactoring (rename, extract function)
- Adding basic tests or documentation
- Minor configuration changes
- Cosmetic/formatting changes

**sonnet** - Balanced model for medium complexity:
- Multi-file refactoring requiring coordination
- Feature additions with moderate logic
- Bug fixes requiring investigation
- Test implementation requiring understanding of behavior
- Integration of existing APIs or libraries

**opus** - Most capable model for complex/critical tasks:
- Architecture decisions and design
- Security-sensitive changes (auth, validation, encryption)
- Performance optimization requiring deep analysis
- Complex algorithms or data structures
- Breaking changes requiring careful migration
- Critical bug fixes with unclear root cause

## DAG-AWARE ORDERING
Order tasks to respect dependencies:
1. Infrastructure/setup tasks first
2. Core abstractions before implementations using them
3. Independent tasks can run in parallel (same order position)
4. Tests and verification after implementations
5. Consider file dependencies, import relationships, and logical prerequisites

## RESEARCH CAPABILITY
Before decomposing:
- Examine relevant files to understand existing patterns
- Identify dependencies between components
- Look for similar implementations to maintain consistency
- Consider impact on tests and downstream consumers

## OUTPUT FORMAT (JSON only, no markdown):
{{
  "tasks": [
    {{"task": "Description of what to fix", "verify": "verification command", "model": "haiku|sonnet|opus", "max_iterations": 5}}
  ]
}}

Each task must include the "model" field with one of: haiku, sonnet, or opus.
Order tasks by DAG dependencies (prerequisites first).
"""


def build_prompt(config: PromptConfig, task: str, verify_cmd: str) -> str:
    if config.custom_prompt:
        return config.custom_prompt.format(task=task, verify_cmd=verify_cmd)

    parts = []
    if config.preamble:
        parts.append(config.preamble)
        parts.append("")

    parts.append(GRIND_PROMPT.format(task=task, verify_cmd=verify_cmd))

    if config.additional_context:
        parts.append("")
        parts.append("## ADDITIONAL CONTEXT")
        parts.append(config.additional_context)

    if config.additional_rules:
        parts.append("")
        parts.append("## ADDITIONAL RULES")
        for rule in config.additional_rules:
            parts.append(f"- {rule}")

    return "\n".join(parts)
