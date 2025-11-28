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
Analyze this problem and break it into independent subtasks.

## PROBLEM
{problem}

## VERIFICATION COMMAND
{verify_cmd}

## YOUR TASK
1. Run the verification command to see failures
2. Group related issues that should be fixed together
3. Output a JSON task list

## OUTPUT FORMAT (JSON only, no markdown):
{{
  "tasks": [
    {{"task": "Description of what to fix", "verify": "verification command", "max_iterations": 5}}
  ]
}}

Group by file or issue type. Order by dependency.
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
