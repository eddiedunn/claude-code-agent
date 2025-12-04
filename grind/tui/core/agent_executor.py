"""Agent executor that bridges TUI with grind engine."""

import asyncio
import uuid
from datetime import datetime
from typing import Callable

from grind.models import TaskDefinition, TaskGraph
from grind.orchestration import GrindAgent, Orchestrator
from grind.orchestration.agent import AgentStatus as OrchAgentStatus
from grind.orchestration.events import EventBus
from grind.tui.core.models import AgentInfo, AgentStatus, AgentType, DAGNodeInfo, DAGNodeStatus
from grind.tui.core.session import AgentSession


class AgentExecutor:
    """Executor that bridges TUI with the grind engine."""

    @staticmethod
    def _convert_status(orch_status: OrchAgentStatus) -> AgentStatus:
        """Convert orchestration AgentStatus to TUI AgentStatus."""
        mapping = {
            OrchAgentStatus.COMPLETE: AgentStatus.COMPLETE,
            OrchAgentStatus.STUCK: AgentStatus.STUCK,
            OrchAgentStatus.MAX_ITERATIONS: AgentStatus.STUCK,  # Map MAX_ITERATIONS to STUCK
            OrchAgentStatus.ERROR: AgentStatus.FAILED,
        }
        return mapping.get(orch_status, AgentStatus.FAILED)

    def __init__(self, session: AgentSession, max_parallel: int = 3, event_bus: EventBus | None = None):
        """
        Initialize the agent executor.

        Args:
            session: AgentSession for tracking agents
            max_parallel: Maximum number of agents to run in parallel
            event_bus: Optional EventBus for publishing orchestration events
        """
        self.session = session
        self.max_parallel = max_parallel
        self.event_bus = event_bus
        self.active_tasks: dict[str, asyncio.Task] = {}
        self.status_callbacks: list[Callable[[AgentInfo], None]] = []
        self.log_callbacks: list[Callable[[str, str, datetime], None]] = []
        self._paused_agents: dict[str, asyncio.Event] = {}
        self._agent_guidance: dict[str, str | None] = {}
        self._task_definitions: dict[str, TaskDefinition] = {}

    def create_agent(self, task_def: TaskDefinition) -> AgentInfo:
        """
        Create a new agent for a task definition.

        Args:
            task_def: TaskDefinition to execute

        Returns:
            AgentInfo with PENDING status
        """
        agent_id = f"agent-{uuid.uuid4().hex[:8]}"
        task_description = task_def.task[:100] if len(task_def.task) > 100 else task_def.task

        agent = AgentInfo(
            agent_id=agent_id,
            task_id=agent_id,  # Use agent_id as task_id if no TaskNode
            task_description=task_description,
            agent_type=AgentType.WORKER,
            status=AgentStatus.PENDING,
            model=task_def.model,
            iteration=0,
            max_iterations=task_def.max_iterations,
            progress=0.0,
            created_at=datetime.now(),
            output_file=self.session.get_agent_log_path(agent_id),
        )

        self.session.add_agent(agent)
        # Store the TaskDefinition for later retrieval
        self._task_definitions[agent.agent_id] = task_def
        return agent

    def _notify_status(self, agent: AgentInfo) -> None:
        """Notify all status callbacks about agent status change."""
        for callback in self.status_callbacks:
            try:
                callback(agent)
            except Exception:
                pass  # Don't let callback errors affect execution

    def _notify_log(self, agent_id: str, line: str, time: datetime) -> None:
        """Notify all log callbacks about a new log line."""
        for callback in self.log_callbacks:
            try:
                callback(agent_id, line, time)
            except Exception:
                pass  # Don't let callback errors affect execution

    def _update_agent_status(self, agent: AgentInfo, status: AgentStatus) -> None:
        """Update agent status and notify callbacks."""
        agent.status = status
        if status == AgentStatus.RUNNING and agent.started_at is None:
            agent.started_at = datetime.now()
        elif status in (
            AgentStatus.COMPLETE,
            AgentStatus.FAILED,
            AgentStatus.CANCELLED,
            AgentStatus.STUCK,
        ):
            agent.completed_at = datetime.now()
        self._notify_status(agent)

    async def execute_agent(self, agent: AgentInfo) -> AgentInfo:
        """
        Execute an agent.

        Args:
            agent: AgentInfo to execute

        Returns:
            Updated AgentInfo with final status
        """
        # Find the task definition from the agent
        # We need to reconstruct it or store it - for now create minimal one
        task_def = self._get_task_def_for_agent(agent)

        # Update status to RUNNING
        self._update_agent_status(agent, AgentStatus.RUNNING)

        try:
            # Create orchestrator with GrindAgent
            orchestrator = Orchestrator()
            grind_agent = GrindAgent()
            orchestrator.add_agent(agent.agent_id, grind_agent)

            # Convert TaskDefinition to input dict for GrindAgent
            input_data = {
                "task": task_def.task,
                "verify": task_def.verify,
                "max_iterations": task_def.max_iterations,
                "model": task_def.model,
                "cwd": task_def.cwd,
                "allowed_tools": task_def.allowed_tools,
                "permission_mode": task_def.permission_mode,
                "verbose": False,
            }

            # Execute agent through orchestrator
            agent_result = await orchestrator.run_agent(agent.agent_id, input_data)

            # Convert orchestration status to TUI status
            final_status = self._convert_status(agent_result.status)

            # Update agent based on result
            agent.iteration = agent_result.iterations
            if final_status == AgentStatus.COMPLETE:
                agent.progress = 1.0
            else:
                agent.progress = agent.iteration / agent.max_iterations

            if agent_result.message:
                if final_status in (AgentStatus.STUCK, AgentStatus.FAILED):
                    agent.error_message = agent_result.message

            self._update_agent_status(agent, final_status)

        except asyncio.CancelledError:
            self._update_agent_status(agent, AgentStatus.CANCELLED)
            raise
        except Exception as e:
            agent.error_message = str(e)
            self._update_agent_status(agent, AgentStatus.FAILED)

        return agent

    def _get_task_def_for_agent(self, agent: AgentInfo) -> TaskDefinition:
        """Get the TaskDefinition for an agent.

        Args:
            agent: AgentInfo to get task definition for

        Returns:
            TaskDefinition for the agent

        Raises:
            KeyError: If no task definition found for agent
        """
        if agent.agent_id not in self._task_definitions:
            raise KeyError(f"No task definition found for agent {agent.agent_id}")
        return self._task_definitions[agent.agent_id]

    async def execute_batch(self, task_defs: list[TaskDefinition]) -> list[AgentInfo]:
        """
        Execute multiple tasks with parallel limit.

        Args:
            task_defs: List of TaskDefinitions to execute

        Returns:
            List of completed AgentInfo objects
        """
        # Create agents for all tasks (task_defs are stored automatically in create_agent)
        agents = [self.create_agent(task_def) for task_def in task_defs]

        # Use semaphore to limit parallelism
        semaphore = asyncio.Semaphore(self.max_parallel)

        async def run_with_semaphore(agent: AgentInfo) -> AgentInfo:
            async with semaphore:
                return await self.execute_agent(agent)

        # Execute all agents with semaphore control
        tasks = [run_with_semaphore(agent) for agent in agents]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        completed_agents = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                agents[i].error_message = str(result)
                agents[i].status = AgentStatus.FAILED
                agents[i].completed_at = datetime.now()
                completed_agents.append(agents[i])
            else:
                completed_agents.append(result)

        return completed_agents

    async def execute_dag(self, graph: TaskGraph) -> dict[str, AgentInfo]:
        """
        Execute tasks in DAG order with dependency awareness.

        Args:
            graph: TaskGraph with task dependencies

        Returns:
            Dictionary mapping node_id to AgentInfo results
        """
        # Get execution order from graph
        execution_order = graph.get_execution_order()
        results: dict[str, AgentInfo] = {}
        completed: set[str] = set()
        failed: set[str] = set()

        # Create a mapping of node_id to DAGNodeInfo for status updates
        dag_nodes: dict[str, DAGNodeInfo] = {}
        for node_id, node in graph.nodes.items():
            dag_nodes[node_id] = DAGNodeInfo(
                node_id=node_id,
                task_def=node.task_def,
                depends_on=node.depends_on,
                status=DAGNodeStatus.PENDING,
            )

        # Use semaphore for parallelism
        semaphore = asyncio.Semaphore(self.max_parallel)

        # Events to signal completion of each node
        completion_events: dict[str, asyncio.Event] = {
            node_id: asyncio.Event() for node_id in execution_order
        }

        async def execute_node(node_id: str) -> AgentInfo | None:
            node = graph.nodes[node_id]
            dag_node = dag_nodes[node_id]

            # Check if blocked by failed dependencies
            if any(dep in failed for dep in node.depends_on):
                dag_node.status = DAGNodeStatus.BLOCKED
                completion_events[node_id].set()
                return None

            # Wait for dependencies using events
            for dep in node.depends_on:
                await completion_events[dep].wait()

            async with semaphore:
                dag_node.status = DAGNodeStatus.RUNNING

                # Create and execute agent (task_def is stored automatically in create_agent)
                agent = self.create_agent(node.task_def)
                dag_node.agent_id = agent.agent_id

                try:
                    result = await self.execute_agent(agent)
                    if result.status == AgentStatus.COMPLETE:
                        dag_node.status = DAGNodeStatus.COMPLETED
                        completed.add(node_id)
                    else:
                        dag_node.status = DAGNodeStatus.FAILED
                        failed.add(node_id)
                    return result
                except Exception as e:
                    dag_node.status = DAGNodeStatus.FAILED
                    failed.add(node_id)
                    agent.error_message = str(e)
                    agent.status = AgentStatus.FAILED
                    return agent
                finally:
                    # Signal completion regardless of success/failure
                    completion_events[node_id].set()

        # Execute nodes in parallel respecting dependencies
        tasks = {node_id: asyncio.create_task(execute_node(node_id)) for node_id in execution_order}

        for node_id in execution_order:
            result = await tasks[node_id]
            if result:
                results[node_id] = result

        return results

    def start_agent(self, agent_id: str) -> bool:
        """Start an agent's execution in the background.

        Args:
            agent_id: Agent to start

        Returns:
            True if started, False if agent not found or already running
        """
        agent = self.session.get_agent(agent_id)
        if not agent:
            return False

        if agent.status != AgentStatus.PENDING:
            return False

        # Check if we're at max parallel capacity
        running_count = sum(
            1 for a in self.session.agents
            if a.status == AgentStatus.RUNNING
        )
        if running_count >= self.max_parallel:
            # At capacity, can't start now
            return False

        # Create background task for agent execution
        task = asyncio.create_task(self.execute_agent(agent))
        self.active_tasks[agent_id] = task

        # Add callback to remove from active_tasks when done
        def _done_callback(t: asyncio.Task) -> None:
            if agent_id in self.active_tasks:
                del self.active_tasks[agent_id]

        task.add_done_callback(_done_callback)

        return True

    async def cancel_agent(self, agent_id: str) -> bool:
        """
        Cancel a running agent.

        Args:
            agent_id: ID of agent to cancel

        Returns:
            True if agent was cancelled, False otherwise
        """
        if agent_id in self.active_tasks:
            task = self.active_tasks[agent_id]
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
            del self.active_tasks[agent_id]

            agent = self.session.get_agent(agent_id)
            if agent:
                self._update_agent_status(agent, AgentStatus.CANCELLED)
            return True
        return False

    async def pause_agent(self, agent_id: str) -> bool:
        """
        Pause a running agent for interactive mode.

        Args:
            agent_id: ID of agent to pause

        Returns:
            True if agent was paused, False otherwise
        """
        agent = self.session.get_agent(agent_id)
        if agent and agent.status == AgentStatus.RUNNING:
            self._paused_agents[agent_id] = asyncio.Event()
            self._update_agent_status(agent, AgentStatus.PAUSED)
            agent.needs_human_input = True
            return True
        return False

    async def resume_agent(self, agent_id: str, guidance: str | None = None) -> bool:
        """
        Resume a paused agent.

        Args:
            agent_id: ID of agent to resume
            guidance: Optional guidance to inject

        Returns:
            True if agent was resumed, False otherwise
        """
        if agent_id in self._paused_agents:
            agent = self.session.get_agent(agent_id)
            if agent:
                self._agent_guidance[agent_id] = guidance
                agent.needs_human_input = False
                self._update_agent_status(agent, AgentStatus.RUNNING)
                self._paused_agents[agent_id].set()
                del self._paused_agents[agent_id]
                return True
        return False

    def add_status_callback(self, callback: Callable[[AgentInfo], None]) -> None:
        """
        Add a callback for agent status changes.

        Args:
            callback: Function to call with AgentInfo on status change
        """
        self.status_callbacks.append(callback)

    def add_log_callback(self, callback: Callable[[str, str, datetime], None]) -> None:
        """
        Add a callback for agent log output.

        Args:
            callback: Function to call with (agent_id, line, time) on new log
        """
        self.log_callbacks.append(callback)

    async def cleanup(self) -> None:
        """Cancel all active tasks and clean up resources."""
        for agent_id, task in list(self.active_tasks.items()):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self.active_tasks.clear()
        self._paused_agents.clear()
        self._agent_guidance.clear()
        self._task_definitions.clear()
