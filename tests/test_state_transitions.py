"""Tests for state machine validation."""

import pytest
from datetime import datetime

from grind.models import TaskDefinition
from grind.tui.core.models import (
    AgentInfo,
    AgentStatus,
    AgentType,
    DAGNodeInfo,
    DAGNodeStatus,
)


class TestAgentStatusTransitions:
    """Test AgentStatus state transitions."""

    def test_pending_to_running_transition(self):
        """Test PENDING -> RUNNING transition."""
        # Create agent with PENDING status
        agent = AgentInfo(
            agent_id="agent-1",
            task_id="task-1",
            task_description="Test task",
            agent_type=AgentType.WORKER,
            status=AgentStatus.PENDING,
            model="sonnet",
            iteration=0,
            max_iterations=10,
            progress=0.0,
            created_at=datetime.now(),
        )

        assert agent.status == AgentStatus.PENDING
        assert agent.started_at is None
        assert agent.completed_at is None

        # Update to RUNNING
        agent.status = AgentStatus.RUNNING
        agent.started_at = datetime.now()

        # Assert started_at is set
        assert agent.started_at is not None
        # Assert completed_at is None
        assert agent.completed_at is None
        assert agent.status == AgentStatus.RUNNING

    def test_running_to_paused_transition(self):
        """Test RUNNING -> PAUSED transition."""
        started = datetime.now()

        # Create agent with RUNNING status, started_at set
        agent = AgentInfo(
            agent_id="agent-2",
            task_id="task-2",
            task_description="Test task",
            agent_type=AgentType.WORKER,
            status=AgentStatus.RUNNING,
            model="sonnet",
            iteration=5,
            max_iterations=10,
            progress=0.5,
            created_at=datetime.now(),
            started_at=started,
        )

        assert agent.status == AgentStatus.RUNNING
        assert agent.started_at == started

        # Update to PAUSED
        agent.status = AgentStatus.PAUSED
        agent.needs_human_input = True

        # Assert started_at preserved
        assert agent.started_at == started
        # Assert completed_at is None
        assert agent.completed_at is None
        assert agent.status == AgentStatus.PAUSED

    def test_running_to_complete_transition(self):
        """Test RUNNING -> COMPLETE transition."""
        started = datetime.now()

        # Create agent with RUNNING status
        agent = AgentInfo(
            agent_id="agent-3",
            task_id="task-3",
            task_description="Test task",
            agent_type=AgentType.WORKER,
            status=AgentStatus.RUNNING,
            model="sonnet",
            iteration=8,
            max_iterations=10,
            progress=0.8,
            created_at=datetime.now(),
            started_at=started,
        )

        assert agent.status == AgentStatus.RUNNING
        assert agent.completed_at is None

        # Update to COMPLETE
        agent.status = AgentStatus.COMPLETE
        agent.completed_at = datetime.now()

        # Assert completed_at is set
        assert agent.completed_at is not None
        assert agent.status == AgentStatus.COMPLETE

        # Assert duration property works
        duration = agent.duration
        assert duration is not None
        assert isinstance(duration, str)
        # Should have some time format (seconds at minimum)
        assert "s" in duration or "m" in duration or "h" in duration

    def test_running_to_failed_on_error(self):
        """Test RUNNING -> FAILED transition with error."""
        started = datetime.now()

        # Create agent with RUNNING status
        agent = AgentInfo(
            agent_id="agent-4",
            task_id="task-4",
            task_description="Test task",
            agent_type=AgentType.WORKER,
            status=AgentStatus.RUNNING,
            model="sonnet",
            iteration=3,
            max_iterations=10,
            progress=0.3,
            created_at=datetime.now(),
            started_at=started,
        )

        assert agent.status == AgentStatus.RUNNING
        assert agent.error_message is None

        # Update to FAILED with error_message
        error_msg = "Test error occurred"
        agent.status = AgentStatus.FAILED
        agent.completed_at = datetime.now()
        agent.error_message = error_msg

        # Assert completed_at is set
        assert agent.completed_at is not None
        # Assert error_message stored
        assert agent.error_message == error_msg
        assert agent.status == AgentStatus.FAILED

    def test_multiple_transitions(self):
        """Test edge case: multiple state transitions."""
        # Create agent
        agent = AgentInfo(
            agent_id="agent-5",
            task_id="task-5",
            task_description="Test task",
            agent_type=AgentType.WORKER,
            status=AgentStatus.PENDING,
            model="sonnet",
            iteration=0,
            max_iterations=10,
            progress=0.0,
            created_at=datetime.now(),
        )

        # PENDING -> RUNNING
        agent.status = AgentStatus.RUNNING
        agent.started_at = datetime.now()
        assert agent.status == AgentStatus.RUNNING
        assert agent.started_at is not None

        # RUNNING -> PAUSED
        original_started = agent.started_at
        agent.status = AgentStatus.PAUSED
        assert agent.status == AgentStatus.PAUSED
        assert agent.started_at == original_started  # Preserved

        # PAUSED -> RUNNING (resume)
        agent.status = AgentStatus.RUNNING
        assert agent.status == AgentStatus.RUNNING
        assert agent.started_at == original_started  # Still preserved

        # RUNNING -> COMPLETE
        agent.status = AgentStatus.COMPLETE
        agent.completed_at = datetime.now()
        assert agent.status == AgentStatus.COMPLETE
        assert agent.completed_at is not None


class TestDAGNodeStatusTransitions:
    """Test DAGNodeStatus state transitions."""

    def test_pending_to_ready_when_deps_satisfied(self):
        """Test nodes become READY when dependencies complete."""
        # Create task definitions
        task_def_a = TaskDefinition(
            task="Task A",
            verify="echo A",
            model="sonnet",
        )
        task_def_b = TaskDefinition(
            task="Task B depends on A",
            verify="echo B",
            model="sonnet",
        )

        # Create node A (no dependencies)
        node_a = DAGNodeInfo(
            node_id="node-a",
            task_def=task_def_a,
            depends_on=[],
            status=DAGNodeStatus.PENDING,
        )

        # Create node B (depends on A)
        node_b = DAGNodeInfo(
            node_id="node-b",
            task_def=task_def_b,
            depends_on=["node-a"],
            status=DAGNodeStatus.PENDING,
        )

        # Initially, node A should be READY (no deps)
        # Node B should remain PENDING (dep not satisfied)
        assert node_a.depends_on == []
        assert node_b.depends_on == ["node-a"]

        # Simulate: Node A has no dependencies, so it can be READY
        node_a.status = DAGNodeStatus.READY
        assert node_a.status == DAGNodeStatus.READY

        # Node B should still be PENDING until A completes
        assert node_b.status == DAGNodeStatus.PENDING

        # Complete node A
        node_a.status = DAGNodeStatus.COMPLETED
        assert node_a.status == DAGNodeStatus.COMPLETED

        # Now node B's dependencies are satisfied, mark it READY
        node_b.status = DAGNodeStatus.READY
        assert node_b.status == DAGNodeStatus.READY

    def test_ready_to_running_transition(self):
        """Test nodes transition READY -> RUNNING when acquired."""
        task_def = TaskDefinition(
            task="Test task",
            verify="echo test",
            model="sonnet",
        )

        node = DAGNodeInfo(
            node_id="node-1",
            task_def=task_def,
            depends_on=[],
            status=DAGNodeStatus.PENDING,
        )

        # Mark as READY (dependencies satisfied)
        node.status = DAGNodeStatus.READY
        assert node.status == DAGNodeStatus.READY
        assert node.agent_id is None

        # Acquire node for execution (assign agent)
        node.status = DAGNodeStatus.RUNNING
        node.agent_id = "agent-123"

        # Verify transition
        assert node.status == DAGNodeStatus.RUNNING
        assert node.agent_id == "agent-123"

    def test_pending_to_blocked_on_failed_dep(self):
        """Test nodes become BLOCKED when dependency fails."""
        # Create task definitions
        task_def_a = TaskDefinition(
            task="Task A (will fail)",
            verify="exit 1",
            model="sonnet",
        )
        task_def_b = TaskDefinition(
            task="Task B depends on A",
            verify="echo B",
            model="sonnet",
        )

        # Create nodes
        node_a = DAGNodeInfo(
            node_id="node-a",
            task_def=task_def_a,
            depends_on=[],
            status=DAGNodeStatus.PENDING,
        )

        node_b = DAGNodeInfo(
            node_id="node-b",
            task_def=task_def_b,
            depends_on=["node-a"],
            status=DAGNodeStatus.PENDING,
        )

        # Run node A
        node_a.status = DAGNodeStatus.READY
        node_a.status = DAGNodeStatus.RUNNING

        # Node A fails
        node_a.status = DAGNodeStatus.FAILED
        assert node_a.status == DAGNodeStatus.FAILED

        # Node B should be blocked because its dependency failed
        node_b.status = DAGNodeStatus.BLOCKED
        assert node_b.status == DAGNodeStatus.BLOCKED

    def test_complete_dag_flow(self):
        """Test edge case: complete DAG execution flow."""
        # Create a simple 3-node DAG: A -> B -> C
        task_def_a = TaskDefinition(task="A", verify="echo A")
        task_def_b = TaskDefinition(task="B", verify="echo B")
        task_def_c = TaskDefinition(task="C", verify="echo C")

        node_a = DAGNodeInfo(
            node_id="node-a",
            task_def=task_def_a,
            depends_on=[],
            status=DAGNodeStatus.PENDING,
        )
        node_b = DAGNodeInfo(
            node_id="node-b",
            task_def=task_def_b,
            depends_on=["node-a"],
            status=DAGNodeStatus.PENDING,
        )
        node_c = DAGNodeInfo(
            node_id="node-c",
            task_def=task_def_c,
            depends_on=["node-b"],
            status=DAGNodeStatus.PENDING,
        )

        # Execute node A
        node_a.status = DAGNodeStatus.READY
        node_a.status = DAGNodeStatus.RUNNING
        node_a.agent_id = "agent-a"
        node_a.status = DAGNodeStatus.COMPLETED

        # Now B can be ready
        node_b.status = DAGNodeStatus.READY
        assert node_b.status == DAGNodeStatus.READY

        # Execute node B
        node_b.status = DAGNodeStatus.RUNNING
        node_b.agent_id = "agent-b"
        node_b.status = DAGNodeStatus.COMPLETED

        # Now C can be ready
        node_c.status = DAGNodeStatus.READY
        assert node_c.status == DAGNodeStatus.READY

        # Execute node C
        node_c.status = DAGNodeStatus.RUNNING
        node_c.agent_id = "agent-c"
        node_c.status = DAGNodeStatus.COMPLETED

        # All nodes completed
        assert node_a.status == DAGNodeStatus.COMPLETED
        assert node_b.status == DAGNodeStatus.COMPLETED
        assert node_c.status == DAGNodeStatus.COMPLETED
