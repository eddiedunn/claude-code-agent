"""
Task decomposition - analyze a problem and break it into subtasks.
"""

import json
from dataclasses import dataclass

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
)

from grind_loop.batch import TaskDefinition


DECOMPOSE_PROMPT = """
You are a task decomposition assistant. Your job is to analyze a problem and break it into independent, focused subtasks.

## PROBLEM TO ANALYZE
{problem}

## VERIFICATION COMMAND
{verify_cmd}

## YOUR TASK
1. First, run the verification command to understand the current failures
2. Analyze the output to identify distinct issues
3. Group related issues that should be fixed together
4. Output a JSON task list

## OUTPUT FORMAT
Output ONLY valid JSON in this exact format (no markdown, no explanation):
{{
  "tasks": [
    {{
      "task": "Clear description of what to fix",
      "verify": "Command to verify this specific fix",
      "max_iterations": 5
    }}
  ]
}}

## GROUPING RULES
- Group issues in the same file together
- Group issues of the same type together (e.g., all "unused import" issues)
- Keep each task focused enough to complete in 5-10 iterations
- Order tasks by dependency (fix imports before fixing code that uses them)

Run the verification command now and produce the task list.
"""


async def decompose(
    problem: str,
    verify_cmd: str,
    cwd: str | None = None,
    verbose: bool = False,
) -> list[TaskDefinition]:
    """
    Analyze a problem and decompose it into subtasks.

    Args:
        problem: High-level description of what needs to be fixed
        verify_cmd: Command to run to see all issues
        cwd: Working directory
        verbose: Show agent output

    Returns:
        List of TaskDefinition objects

    Example:
        tasks = await decompose(
            problem="Fix all failing unit tests",
            verify_cmd="pytest tests/ -v"
        )
        # Returns list of focused tasks like:
        # - "Fix test_auth.py - mock setup issues"
        # - "Fix test_api.py - missing fixtures"
    """
    options = ClaudeAgentOptions(
        allowed_tools=["Bash", "Read", "Glob", "Grep"],
        permission_mode="acceptEdits",
        cwd=cwd,
        max_turns=10,
    )

    prompt = DECOMPOSE_PROMPT.format(problem=problem, verify_cmd=verify_cmd)

    collected_text = ""

    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)

        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        if verbose:
                            print(block.text)
                        collected_text += block.text

    # Extract JSON from response
    tasks = _parse_task_json(collected_text)
    return tasks


def _parse_task_json(text: str) -> list[TaskDefinition]:
    """Extract and parse JSON task list from response."""
    # Try to find JSON in the response
    start = text.find("{")
    end = text.rfind("}") + 1

    if start == -1 or end == 0:
        raise ValueError("No JSON found in decompose response")

    json_str = text[start:end]

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in response: {e}")

    tasks = []
    for item in data.get("tasks", []):
        tasks.append(
            TaskDefinition(
                task=item["task"],
                verify=item["verify"],
                max_iterations=item.get("max_iterations", 5),
            )
        )

    return tasks
