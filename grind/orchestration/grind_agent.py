"""GrindAgent - wraps the grind() function as an Agent for orchestration.

This module provides GrindAgent which adapts the grind() function from
grind.engine to conform to the Agent protocol defined in grind.orchestration.agent.
"""

from grind.models import GrindStatus, TaskDefinition
from grind.orchestration.agent import AgentResult, AgentStatus

# Import grind lazily to avoid circular import, but make it available for mocking
grind = None


def _get_grind():
    """Lazy import of grind to avoid circular dependency."""
    global grind
    if grind is None:
        from grind.engine import grind as _grind
        grind = _grind
    return grind


class GrindAgent:
    """Agent wrapper for the grind() function.

    Delegates to grind/engine.py's grind() function while conforming
    to the Agent protocol for orchestration.

    Example:
        agent = GrindAgent()
        result = await agent.run({
            "task": "Create a hello world function",
            "verify": "python -c 'from hello import hello; hello()'",
            "max_iterations": 5
        })
    """

    async def run(self, input: dict[str, object]) -> AgentResult:
        """Execute grind with the provided input.

        Args:
            input: Dict containing:
                - task (str): The task description
                - verify (str): The verification command
                - max_iterations (int, optional): Maximum iterations (default: 5)
                - model (str, optional): Model to use
                - cwd (str, optional): Working directory
                - allowed_tools (list[str], optional): Allowed tools
                - permission_mode (str, optional): Permission mode
                - verbose (bool, optional): Verbose output (default: False)

        Returns:
            AgentResult with status, iterations, and output dict
        """
        # Extract required parameters
        task = input.get("task")
        verify = input.get("verify")

        if not task or not isinstance(task, str):
            return AgentResult(
                status=AgentStatus.ERROR,
                iterations=0,
                message="Missing or invalid 'task' parameter",
                output={}
            )

        if not verify or not isinstance(verify, str):
            return AgentResult(
                status=AgentStatus.ERROR,
                iterations=0,
                message="Missing or invalid 'verify' parameter",
                output={}
            )

        # Build TaskDefinition from input
        task_def = TaskDefinition(
            task=task,
            verify=verify,
            max_iterations=input.get("max_iterations", 5),
            model=input.get("model"),
            cwd=input.get("cwd"),
            allowed_tools=input.get("allowed_tools"),
            permission_mode=input.get("permission_mode"),
        )

        # Execute grind
        verbose = input.get("verbose", False)
        grind_fn = _get_grind()
        grind_result = await grind_fn(task_def, verbose=verbose)

        # Convert GrindStatus to AgentStatus
        status_mapping = {
            GrindStatus.COMPLETE: AgentStatus.COMPLETE,
            GrindStatus.STUCK: AgentStatus.STUCK,
            GrindStatus.MAX_ITERATIONS: AgentStatus.MAX_ITERATIONS,
            GrindStatus.ERROR: AgentStatus.ERROR,
        }
        agent_status = status_mapping.get(grind_result.status, AgentStatus.ERROR)

        # Build output dict from grind result
        output = {
            "message": grind_result.message,
            "tools_used": grind_result.tools_used,
            "duration_seconds": grind_result.duration_seconds,
            "model": grind_result.model,
            "hooks_executed": grind_result.hooks_executed,
        }

        return AgentResult(
            status=agent_status,
            iterations=grind_result.iterations,
            output=output,
            message=grind_result.message,
            duration_seconds=grind_result.duration_seconds,
        )
