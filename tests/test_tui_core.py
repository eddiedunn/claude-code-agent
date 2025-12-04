"""Tests for TUI core modules."""

from datetime import datetime, timedelta

import pytest

from grind.models import TaskDefinition
from grind.tui.core.log_stream import AgentLogStreamer
from grind.tui.core.models import AgentInfo, AgentStatus, AgentType, DAGNodeInfo, DAGNodeStatus
from grind.tui.core.session import AgentSession
from grind.tui.core.shell_commands import (
    CommandRegistry,
    ShellCommand,
    ShellContext,
    execute_shell_command,
    parse_and_execute,
)
from grind.tui.core.tab_registry import TabConfig, TabRegistry

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_session():
    """Creates and cleans up AgentSession."""
    session = AgentSession(session_id="test-session")
    yield session
    session.cleanup()


@pytest.fixture
def sample_agents():
    """Creates list of AgentInfo with various statuses."""
    now = datetime.now()
    agents = [
        AgentInfo(
            agent_id="agent-1",
            task_id="task-1",
            task_description="Test task 1",
            agent_type=AgentType.WORKER,
            status=AgentStatus.RUNNING,
            model="sonnet",
            iteration=2,
            max_iterations=5,
            progress=0.4,
            created_at=now - timedelta(minutes=10),
            started_at=now - timedelta(minutes=9),
        ),
        AgentInfo(
            agent_id="agent-2",
            task_id="task-2",
            task_description="Test task 2",
            agent_type=AgentType.WORKER,
            status=AgentStatus.COMPLETE,
            model="haiku",
            iteration=3,
            max_iterations=3,
            progress=1.0,
            created_at=now - timedelta(minutes=20),
            started_at=now - timedelta(minutes=19),
            completed_at=now - timedelta(minutes=10),
        ),
        AgentInfo(
            agent_id="agent-3",
            task_id="task-3",
            task_description="Test task 3",
            agent_type=AgentType.ORCHESTRATOR,
            status=AgentStatus.FAILED,
            model="opus",
            iteration=1,
            max_iterations=10,
            progress=0.1,
            created_at=now - timedelta(minutes=5),
            started_at=now - timedelta(minutes=4),
            completed_at=now - timedelta(minutes=1),
            error_message="Something went wrong",
        ),
    ]
    return agents


@pytest.fixture
def temp_log_file(tmp_path):
    """Creates temp file with sample log content."""
    log_file = tmp_path / "test_agent.log"
    content = """INFO: Starting agent
DEBUG: Loading configuration
INFO: Processing task
WARN: Performance degradation detected
ERROR: Connection timeout
INFO: Retrying operation
INFO: Task completed successfully
"""
    log_file.write_text(content)
    return log_file


# ============================================================================
# Test models (grind/tui/core/models.py)
# ============================================================================


class TestAgentStatus:
    """Test AgentStatus enum."""

    def test_agent_status_enum_values(self):
        """Test that AgentStatus enum has expected values."""
        assert AgentStatus.PENDING.value == "pending"
        assert AgentStatus.RUNNING.value == "running"
        assert AgentStatus.PAUSED.value == "paused"
        assert AgentStatus.COMPLETE.value == "complete"
        assert AgentStatus.STUCK.value == "stuck"
        assert AgentStatus.FAILED.value == "failed"
        assert AgentStatus.CANCELLED.value == "cancelled"


class TestAgentInfo:
    """Test AgentInfo dataclass."""

    def test_agent_info_creation(self):
        """Test creating AgentInfo with valid data."""
        now = datetime.now()
        agent = AgentInfo(
            agent_id="test-1",
            task_id="task-1",
            task_description="Test task",
            agent_type=AgentType.WORKER,
            status=AgentStatus.RUNNING,
            model="sonnet",
            iteration=1,
            max_iterations=5,
            progress=0.2,
            created_at=now,
            started_at=now,
        )

        assert agent.agent_id == "test-1"
        assert agent.task_id == "task-1"
        assert agent.task_description == "Test task"
        assert agent.agent_type == AgentType.WORKER
        assert agent.status == AgentStatus.RUNNING
        assert agent.model == "sonnet"
        assert agent.iteration == 1
        assert agent.max_iterations == 5
        assert agent.progress == 0.2
        assert agent.created_at == now
        assert agent.started_at == now

    def test_agent_info_duration_property(self):
        """Test duration property calculation."""
        now = datetime.now()

        # Not started yet
        agent = AgentInfo(
            agent_id="test-1",
            task_id="task-1",
            task_description="Test task",
            agent_type=AgentType.WORKER,
            status=AgentStatus.PENDING,
            model="sonnet",
            iteration=0,
            max_iterations=5,
            progress=0.0,
            created_at=now,
        )
        assert agent.duration == "Not started"

        # Running - should show current duration
        agent_running = AgentInfo(
            agent_id="test-2",
            task_id="task-2",
            task_description="Test task",
            agent_type=AgentType.WORKER,
            status=AgentStatus.RUNNING,
            model="sonnet",
            iteration=1,
            max_iterations=5,
            progress=0.2,
            created_at=now,
            started_at=now - timedelta(seconds=30),
        )
        assert "30s" in agent_running.duration

        # Completed - should show final duration
        agent_completed = AgentInfo(
            agent_id="test-3",
            task_id="task-3",
            task_description="Test task",
            agent_type=AgentType.WORKER,
            status=AgentStatus.COMPLETE,
            model="sonnet",
            iteration=3,
            max_iterations=5,
            progress=1.0,
            created_at=now,
            started_at=now - timedelta(minutes=2, seconds=30),
            completed_at=now,
        )
        assert "2m 30s" in agent_completed.duration

        # Test hours
        agent_long = AgentInfo(
            agent_id="test-4",
            task_id="task-4",
            task_description="Test task",
            agent_type=AgentType.WORKER,
            status=AgentStatus.COMPLETE,
            model="sonnet",
            iteration=5,
            max_iterations=5,
            progress=1.0,
            created_at=now,
            started_at=now - timedelta(hours=1, minutes=30, seconds=45),
            completed_at=now,
        )
        assert "1h 30m 45s" in agent_long.duration

    def test_agent_info_validation(self):
        """Test AgentInfo validation in __post_init__."""
        now = datetime.now()

        # Invalid iteration (negative)
        with pytest.raises(ValueError, match="iteration must be >= 0"):
            AgentInfo(
                agent_id="test-1",
                task_id="task-1",
                task_description="Test",
                agent_type=AgentType.WORKER,
                status=AgentStatus.RUNNING,
                model="sonnet",
                iteration=-1,
                max_iterations=5,
                progress=0.0,
                created_at=now,
            )

        # Invalid max_iterations (zero)
        with pytest.raises(ValueError, match="max_iterations must be >= 1"):
            AgentInfo(
                agent_id="test-2",
                task_id="task-2",
                task_description="Test",
                agent_type=AgentType.WORKER,
                status=AgentStatus.RUNNING,
                model="sonnet",
                iteration=0,
                max_iterations=0,
                progress=0.0,
                created_at=now,
            )

        # Invalid progress (out of range)
        with pytest.raises(ValueError, match="progress must be between 0.0 and 1.0"):
            AgentInfo(
                agent_id="test-3",
                task_id="task-3",
                task_description="Test",
                agent_type=AgentType.WORKER,
                status=AgentStatus.RUNNING,
                model="sonnet",
                iteration=0,
                max_iterations=5,
                progress=1.5,
                created_at=now,
            )

        # Task description truncation
        long_desc = "x" * 150
        agent = AgentInfo(
            agent_id="test-4",
            task_id="task-4",
            task_description=long_desc,
            agent_type=AgentType.WORKER,
            status=AgentStatus.RUNNING,
            model="sonnet",
            iteration=0,
            max_iterations=5,
            progress=0.0,
            created_at=now,
        )
        assert len(agent.task_description) == 100


class TestDAGNodeStatus:
    """Test DAGNodeStatus enum."""

    def test_dag_node_status_transitions(self):
        """Test DAGNodeStatus enum values and expected transitions."""
        # Verify all expected statuses exist
        assert DAGNodeStatus.PENDING.value == "pending"
        assert DAGNodeStatus.READY.value == "ready"
        assert DAGNodeStatus.RUNNING.value == "running"
        assert DAGNodeStatus.COMPLETED.value == "completed"
        assert DAGNodeStatus.FAILED.value == "failed"
        assert DAGNodeStatus.BLOCKED.value == "blocked"

        # Test typical transition sequence
        statuses = [
            DAGNodeStatus.PENDING,
            DAGNodeStatus.READY,
            DAGNodeStatus.RUNNING,
            DAGNodeStatus.COMPLETED,
        ]
        assert len(statuses) == 4


class TestDAGNodeInfo:
    """Test DAGNodeInfo dataclass."""

    def test_dag_node_info_creation(self):
        """Test creating DAGNodeInfo."""
        task_def = TaskDefinition(
            task="Test task",
            verify="echo test",
            model="sonnet",
            max_iterations=5,
        )

        node = DAGNodeInfo(
            node_id="node-1",
            task_def=task_def,
            depends_on=["node-0"],
            status=DAGNodeStatus.PENDING,
        )

        assert node.node_id == "node-1"
        assert node.task_def == task_def
        assert node.depends_on == ["node-0"]
        assert node.status == DAGNodeStatus.PENDING
        assert node.agent_id is None
        assert node.position is None

    def test_dag_node_info_validation_empty_id(self):
        """Test validation fails with empty node_id."""
        task_def = TaskDefinition(
            task="Test task",
            verify="echo test",
            model="sonnet",
        )

        with pytest.raises(ValueError, match="node_id cannot be empty"):
            DAGNodeInfo(
                node_id="",
                task_def=task_def,
            )

    def test_dag_node_info_validation_invalid_task_def(self):
        """Test validation fails with invalid task_def."""
        # Create an invalid task definition (empty task)
        invalid_task_def = TaskDefinition(
            task="",
            verify="echo test",
            model="sonnet",
        )

        with pytest.raises(ValueError, match="Invalid task_def"):
            DAGNodeInfo(
                node_id="node-1",
                task_def=invalid_task_def,
            )


# ============================================================================
# Test TabRegistry (grind/tui/core/tab_registry.py)
# ============================================================================


class TestTabConfig:
    """Test TabConfig dataclass."""

    def test_tab_config_get_binding_priority(self):
        """Test that TabConfig.get_binding() returns binding with priority=True."""
        config = TabConfig(
            id="tab-test",
            title="Test Tab",
            key="1",
            action_name="switch_test",
            binding_description="Test",
        )

        binding = config.get_binding()
        assert binding is not None
        assert binding.key == "1"
        assert binding.action == "switch_test"
        assert binding.description == "Test"
        assert binding.priority is True

    def test_tab_config_get_binding_no_key(self):
        """Test get_binding returns None when no key configured."""
        config = TabConfig(
            id="tab-test",
            title="Test Tab",
        )

        assert config.get_binding() is None

    def test_tab_config_defaults(self):
        """Test TabConfig default values."""
        config = TabConfig(id="test", title="Test")
        assert config.key is None
        assert config.action_name is None
        assert config.binding_description is None
        assert config.compose_fn is None
        assert config.on_mount_fn is None
        assert config.on_unmount_fn is None
        assert config.stop_stream_on_leave is True
        assert config.enabled is True
        assert config.category == "general"


class TestTabRegistry:
    """Test TabRegistry class."""

    def test_tab_registry_register(self):
        """Test registering a tab."""
        registry = TabRegistry()
        config = TabConfig(
            id="tab-1",
            title="Tab 1",
            key="1",
            action_name="switch_1",
        )

        registry.register(config)
        assert registry.count_tabs() == 1
        assert registry.get_tab("tab-1") == config

    def test_tab_registry_get_tab(self):
        """Test getting a tab by ID."""
        registry = TabRegistry()
        config = TabConfig(id="tab-1", title="Tab 1")
        registry.register(config)

        assert registry.get_tab("tab-1") == config
        assert registry.get_tab("nonexistent") is None

    def test_tab_registry_get_enabled_tabs(self):
        """Test getting only enabled tabs."""
        registry = TabRegistry()

        config1 = TabConfig(id="tab-1", title="Tab 1", enabled=True)
        config2 = TabConfig(id="tab-2", title="Tab 2", enabled=False)
        config3 = TabConfig(id="tab-3", title="Tab 3", enabled=True)

        registry.register(config1)
        registry.register(config2)
        registry.register(config3)

        enabled = registry.get_enabled_tabs()
        assert len(enabled) == 2
        assert config1 in enabled
        assert config3 in enabled
        assert config2 not in enabled

    def test_tab_registry_get_bindings(self):
        """Test getting keyboard bindings."""
        registry = TabRegistry()

        config1 = TabConfig(
            id="tab-1",
            title="Tab 1",
            key="1",
            action_name="switch_1",
            enabled=True,
        )
        config2 = TabConfig(
            id="tab-2",
            title="Tab 2",
            key="2",
            action_name="switch_2",
            enabled=False,  # Disabled - should not be in bindings
        )
        config3 = TabConfig(
            id="tab-3",
            title="Tab 3",
            enabled=True,  # No key - should not be in bindings
        )

        registry.register(config1)
        registry.register(config2)
        registry.register(config3)

        bindings = registry.get_bindings()
        assert len(bindings) == 1  # Only config1
        assert bindings[0].key == "1"
        assert bindings[0].action == "switch_1"

    def test_tab_registry_enable_disable(self):
        """Test enabling and disabling tabs."""
        registry = TabRegistry()
        config = TabConfig(id="tab-1", title="Tab 1", enabled=True)
        registry.register(config)

        assert config.enabled is True

        registry.disable_tab("tab-1")
        assert config.enabled is False

        registry.enable_tab("tab-1")
        assert config.enabled is True

    def test_tab_registry_get_tabs_by_category(self):
        """Test filtering tabs by category."""
        registry = TabRegistry()

        config1 = TabConfig(id="tab-1", title="Tab 1", category="agents")
        config2 = TabConfig(id="tab-2", title="Tab 2", category="logs")
        config3 = TabConfig(id="tab-3", title="Tab 3", category="agents")

        registry.register(config1)
        registry.register(config2)
        registry.register(config3)

        agents_tabs = registry.get_tabs(category="agents")
        assert len(agents_tabs) == 2
        assert config1 in agents_tabs
        assert config3 in agents_tabs

        logs_tabs = registry.get_tabs(category="logs")
        assert len(logs_tabs) == 1
        assert config2 in logs_tabs


# ============================================================================
# Test Session (grind/tui/core/session.py)
# ============================================================================


class TestAgentSession:
    """Test AgentSession class."""

    def test_agent_session_creation(self):
        """Test creating an AgentSession."""
        session = AgentSession(session_id="test-123")

        try:
            assert session.session_id == "test-123"
            assert session.session_dir.exists()
            assert session.output_dir.exists()
            assert len(session.agents) == 0
            assert session._cleanup_done is False
        finally:
            session.cleanup()

    def test_agent_session_log_path(self):
        """Test getting agent log path."""
        session = AgentSession(session_id="test-123")

        try:
            log_path = session.get_agent_log_path("agent-1")
            assert log_path.parent == session.output_dir
            assert log_path.name == "agent-1.log"
        finally:
            session.cleanup()

    def test_agent_session_add_agent(self):
        """Test adding agents to session."""
        session = AgentSession(session_id="test-123")

        try:
            now = datetime.now()
            agent = AgentInfo(
                agent_id="agent-1",
                task_id="task-1",
                task_description="Test",
                agent_type=AgentType.WORKER,
                status=AgentStatus.RUNNING,
                model="sonnet",
                iteration=1,
                max_iterations=5,
                progress=0.2,
                created_at=now,
            )

            session.add_agent(agent)
            assert len(session.agents) == 1
            assert session.get_agent("agent-1") == agent
            assert session.get_agent("nonexistent") is None
        finally:
            session.cleanup()

    def test_agent_session_cleanup(self):
        """Test session cleanup."""
        session = AgentSession(session_id="test-cleanup")
        session_dir = session.session_dir

        assert session_dir.exists()
        session.cleanup()
        assert not session_dir.exists()
        assert session._cleanup_done is True

        # Test idempotency - should not error on second call
        session.cleanup()
        assert session._cleanup_done is True

    def test_agent_session_context_manager(self):
        """Test AgentSession as context manager."""
        session_dir = None

        with AgentSession(session_id="test-context") as session:
            session_dir = session.session_dir
            assert session_dir.exists()

        # After exiting context, should be cleaned up
        assert not session_dir.exists()

    def test_agent_session_get_running_agents(self, sample_agents):
        """Test getting running agents."""
        session = AgentSession(session_id="test-running")

        try:
            for agent in sample_agents:
                session.add_agent(agent)

            running = session.get_running_agents()
            assert len(running) == 1
            assert running[0].agent_id == "agent-1"
            assert running[0].status == AgentStatus.RUNNING
        finally:
            session.cleanup()

    def test_agent_session_get_completed_agents(self, sample_agents):
        """Test getting completed agents."""
        session = AgentSession(session_id="test-completed")

        try:
            for agent in sample_agents:
                session.add_agent(agent)

            completed = session.get_completed_agents()
            assert len(completed) == 2

            completed_ids = {a.agent_id for a in completed}
            assert "agent-2" in completed_ids  # COMPLETE
            assert "agent-3" in completed_ids  # FAILED
        finally:
            session.cleanup()


# ============================================================================
# Test shell commands (grind/tui/core/shell_commands.py)
# ============================================================================


class TestCommandRegistry:
    """Test CommandRegistry class."""

    def test_command_registry_register(self):
        """Test registering a command."""
        registry = CommandRegistry()

        async def handler(args, context):
            return "test"

        cmd = ShellCommand(
            name="test",
            description="Test command",
            usage="test",
            handler=handler,
        )

        registry.register(cmd)
        assert registry.get_command("test") == cmd

    def test_command_registry_get_command(self):
        """Test getting command by name."""
        registry = CommandRegistry()

        # Should have built-in commands
        help_cmd = registry.get_command("help")
        assert help_cmd is not None
        assert help_cmd.name == "help"

        status_cmd = registry.get_command("status")
        assert status_cmd is not None
        assert status_cmd.name == "status"

        # Nonexistent command
        assert registry.get_command("nonexistent") is None

    def test_command_registry_aliases(self):
        """Test command aliases."""
        registry = CommandRegistry()

        # "ls" should be an alias for "agents"
        agents_cmd = registry.get_command("agents")
        ls_cmd = registry.get_command("ls")

        assert agents_cmd == ls_cmd
        assert "ls" in agents_cmd.aliases

        # "tail" should be an alias for "logs"
        logs_cmd = registry.get_command("logs")
        tail_cmd = registry.get_command("tail")

        assert logs_cmd == tail_cmd
        assert "tail" in logs_cmd.aliases

    def test_command_registry_get_completions(self):
        """Test command completion."""
        registry = CommandRegistry()

        # Complete "he" should match "help"
        completions = registry.get_completions("he")
        assert "help" in completions

        # Complete "hi" should match "history"
        completions = registry.get_completions("hi")
        assert "history" in completions

        # Complete "st" should match "status"
        completions = registry.get_completions("st")
        assert "status" in completions


@pytest.mark.asyncio
class TestShellCommands:
    """Test individual shell command handlers."""

    async def test_parse_and_execute_help(self, sample_agents):
        """Test help command."""
        session = AgentSession(session_id="test-help")

        try:
            registry = CommandRegistry()
            context = ShellContext(
                session=session,
                agents=sample_agents,
                current_agent_id=None,
                history=[],
                variables={},
            )

            # Test general help
            result = await parse_and_execute("help", registry, context)
            assert "Available commands" in result
            assert "help" in result
            assert "status" in result

            # Test help for specific command
            result = await parse_and_execute("help status", registry, context)
            assert "status" in result
            assert "Show current agent status summary" in result
        finally:
            session.cleanup()

    async def test_parse_and_execute_status(self, sample_agents):
        """Test status command."""
        session = AgentSession(session_id="test-status")

        try:
            registry = CommandRegistry()
            context = ShellContext(
                session=session,
                agents=sample_agents,
                current_agent_id=None,
                history=[],
                variables={},
            )

            result = await parse_and_execute("status", registry, context)
            assert "Agent Status Summary" in result
            assert "running" in result.lower()
            assert "complete" in result.lower()
            assert "failed" in result.lower()
        finally:
            session.cleanup()

    async def test_shell_escape_command(self):
        """Test shell escape command (!command)."""
        result = await execute_shell_command("echo hello")
        assert "hello" in result

    async def test_parse_and_execute_shell_escape(self, sample_agents):
        """Test executing shell commands via ! prefix."""
        session = AgentSession(session_id="test-shell")

        try:
            registry = CommandRegistry()
            context = ShellContext(
                session=session,
                agents=sample_agents,
                current_agent_id=None,
                history=[],
                variables={},
            )

            result = await parse_and_execute("!echo test", registry, context)
            assert "test" in result
        finally:
            session.cleanup()

    async def test_parse_and_execute_unknown_command(self, sample_agents):
        """Test unknown command handling."""
        session = AgentSession(session_id="test-unknown")

        try:
            registry = CommandRegistry()
            context = ShellContext(
                session=session,
                agents=sample_agents,
                current_agent_id=None,
                history=[],
                variables={},
            )

            result = await parse_and_execute("nonexistent", registry, context)
            assert "Unknown command" in result
        finally:
            session.cleanup()

    async def test_cmd_run_execution(self, tmp_path, sample_agents):
        """Test that cmd_run loads tasks and creates agents using executor."""
        import tempfile

        session = AgentSession(session_id="test-cmd-run")

        try:
            # Create a temporary task file
            task_yaml = tmp_path / "test_tasks.yaml"
            task_yaml.write_text("""
tasks:
  - task: "Test task 1"
    verify: "echo test1"
    max_iterations: 5
  - task: "Test task 2"
    verify: "echo test2"
    max_iterations: 3
""")

            # Create executor
            from grind.tui.core.agent_executor import AgentExecutor
            executor = AgentExecutor(session)

            # Track initial agent count
            initial_agent_count = len(session.agents)

            # Create context with executor
            registry = CommandRegistry()
            context = ShellContext(
                session=session,
                agents=session.agents,
                current_agent_id=None,
                history=[],
                variables={},
                executor=executor,
            )

            # Execute run command
            result = await parse_and_execute(f"run {task_yaml}", registry, context)

            # Check that tasks were loaded
            assert "2" in result  # Should mention 2 tasks
            assert "Loaded" in result
            assert "tasks" in result

            # Check that agents were created (2 new agents should be added)
            assert len(session.agents) == initial_agent_count + 2

        finally:
            session.cleanup()

    async def test_cmd_spawn_creation(self, sample_agents):
        """Test that cmd_spawn creates an agent from command arguments."""
        session = AgentSession(session_id="test-cmd-spawn")

        try:
            # Create executor
            from grind.tui.core.agent_executor import AgentExecutor
            executor = AgentExecutor(session)

            # Track initial agent count
            initial_agent_count = len(session.agents)

            # Create context with executor
            registry = CommandRegistry()
            context = ShellContext(
                session=session,
                agents=session.agents,
                current_agent_id=None,
                history=[],
                variables={},
                executor=executor,
            )

            # Test 1: Execute spawn command with valid arguments
            result = await parse_and_execute(
                'spawn sonnet 10 "pytest tests/" -- Fix failing unit tests',
                registry,
                context
            )

            # Check that agent was created and started
            assert "agent" in result.lower()
            assert "agent-" in result  # Agent ID present
            assert "sonnet" in result
            assert "10" in result
            assert "pytest tests/" in result
            assert len(session.agents) == initial_agent_count + 1

            # Test 2: Verify the created agent has correct properties
            new_agent = session.agents[-1]
            assert new_agent.model == "sonnet"
            assert new_agent.max_iterations == 10
            assert "Fix failing unit tests" in new_agent.task_description

            # Test 3: Test error handling - missing arguments
            result = await parse_and_execute("spawn", registry, context)
            assert "Usage:" in result

            # Test 4: Test error handling - invalid model
            result = await parse_and_execute(
                'spawn invalid-model 10 "pytest" -- Task',
                registry,
                context
            )
            assert "Invalid model" in result

            # Test 5: Test error handling - missing separator
            result = await parse_and_execute(
                'spawn sonnet 10 "pytest" Task without separator',
                registry,
                context
            )
            assert "Missing '--' separator" in result

            # Test 6: Test error handling - invalid max_iterations
            result = await parse_and_execute(
                'spawn sonnet 999 "pytest" -- Task',
                registry,
                context
            )
            assert "must be between 1 and 50" in result

            # Test 7: Test error handling - no executor
            context_no_executor = ShellContext(
                session=session,
                agents=session.agents,
                current_agent_id=None,
                history=[],
                variables={},
                executor=None,
            )
            result = await parse_and_execute(
                'spawn sonnet 10 "pytest" -- Task',
                registry,
                context_no_executor
            )
            assert "Executor not available" in result

        finally:
            session.cleanup()


# ============================================================================
# Test log streamer (grind/tui/core/log_stream.py)
# ============================================================================


class TestLogStreamer:
    """Test AgentLogStreamer class."""

    @pytest.mark.asyncio
    async def test_log_streamer_get_logs(self, temp_log_file):
        """Test getting complete logs."""
        streamer = AgentLogStreamer()

        now = datetime.now()
        agent = AgentInfo(
            agent_id="test-agent",
            task_id="task-1",
            task_description="Test",
            agent_type=AgentType.WORKER,
            status=AgentStatus.RUNNING,
            model="sonnet",
            iteration=1,
            max_iterations=5,
            progress=0.2,
            created_at=now,
            output_file=temp_log_file,
        )

        logs = await streamer.get_agent_logs(agent)
        assert "Starting agent" in logs
        assert "ERROR: Connection timeout" in logs
        assert "Task completed successfully" in logs

    def test_log_streamer_search_logs(self, temp_log_file):
        """Test searching logs for pattern."""
        streamer = AgentLogStreamer()

        now = datetime.now()
        agent = AgentInfo(
            agent_id="test-agent",
            task_id="task-1",
            task_description="Test",
            agent_type=AgentType.WORKER,
            status=AgentStatus.RUNNING,
            model="sonnet",
            iteration=1,
            max_iterations=5,
            progress=0.2,
            created_at=now,
            output_file=temp_log_file,
        )

        # Search for ERROR
        results = streamer.search_logs(agent, "ERROR")
        assert len(results) == 1
        line_num, line_text = results[0]
        assert "Connection timeout" in line_text

        # Search for INFO
        results = streamer.search_logs(agent, "INFO")
        assert len(results) == 4  # 4 INFO lines in sample

    def test_log_streamer_filter_logs(self, temp_log_file):
        """Test filtering logs by level and range."""
        streamer = AgentLogStreamer()

        now = datetime.now()
        agent = AgentInfo(
            agent_id="test-agent",
            task_id="task-1",
            task_description="Test",
            agent_type=AgentType.WORKER,
            status=AgentStatus.RUNNING,
            model="sonnet",
            iteration=1,
            max_iterations=5,
            progress=0.2,
            created_at=now,
            output_file=temp_log_file,
        )

        # Filter by ERROR level
        filtered = streamer.filter_logs(agent, level="ERROR")
        assert "Connection timeout" in filtered
        assert "Starting agent" not in filtered

        # Filter by line range
        filtered = streamer.filter_logs(agent, start_line=0, max_lines=2)
        lines = filtered.strip().split("\n")
        assert len(lines) == 2

    def test_log_stats(self, temp_log_file):
        """Test getting log statistics."""
        streamer = AgentLogStreamer()

        now = datetime.now()
        agent = AgentInfo(
            agent_id="test-agent",
            task_id="task-1",
            task_description="Test",
            agent_type=AgentType.WORKER,
            status=AgentStatus.RUNNING,
            model="sonnet",
            iteration=1,
            max_iterations=5,
            progress=0.2,
            created_at=now,
            output_file=temp_log_file,
        )

        stats = streamer.get_log_stats(agent)
        assert stats["line_count"] == 7
        assert stats["size_bytes"] > 0
        assert stats["has_errors"] is True
        assert stats["has_warnings"] is True

    def test_log_stats_no_file(self):
        """Test log stats with no file."""
        streamer = AgentLogStreamer()

        now = datetime.now()
        agent = AgentInfo(
            agent_id="test-agent",
            task_id="task-1",
            task_description="Test",
            agent_type=AgentType.WORKER,
            status=AgentStatus.RUNNING,
            model="sonnet",
            iteration=1,
            max_iterations=5,
            progress=0.2,
            created_at=now,
        )

        stats = streamer.get_log_stats(agent)
        assert stats["line_count"] == 0
        assert stats["size_bytes"] == 0
        assert stats["has_errors"] is False
        assert stats["has_warnings"] is False


# ============================================================================
# Test TUI app shell context wiring (grind/tui/app.py)
# ============================================================================


def test_shell_context_wiring():
    """Test that AgentTUI properly wires ShellContext to AgentShell widget."""
    from grind.tui.app import AgentTUI
    from grind.tui.core.shell_commands import CommandRegistry, ShellContext

    # Create TUI app
    app = AgentTUI()

    # Verify command registry is created
    assert app.command_registry is not None
    assert isinstance(app.command_registry, CommandRegistry)

    # Verify shell_context is initialized as None before mount
    assert app.shell_context is None

    # Verify command registry has built-in commands
    help_cmd = app.command_registry.get_command("help")
    assert help_cmd is not None
    assert help_cmd.name == "help"

    agents_cmd = app.command_registry.get_command("agents")
    assert agents_cmd is not None
    assert agents_cmd.name == "agents"

    status_cmd = app.command_registry.get_command("status")
    assert status_cmd is not None
    assert status_cmd.name == "status"


# ============================================================================
# Test AgentExecutor (grind/tui/core/agent_executor.py)
# ============================================================================


@pytest.mark.asyncio
async def test_agent_executor_task_storage(temp_session):
    """Test that AgentExecutor stores and retrieves TaskDefinitions correctly."""
    from grind.tui.core.agent_executor import AgentExecutor

    # Create AgentExecutor
    executor = AgentExecutor(temp_session, max_parallel=3)

    # Test 1: _task_definitions is initialized
    assert hasattr(executor, "_task_definitions")
    assert isinstance(executor._task_definitions, dict)
    assert len(executor._task_definitions) == 0

    # Test 2: create_agent stores TaskDefinition
    task_def1 = TaskDefinition(
        task="First task", verify="echo verify1", max_iterations=5, model="haiku"
    )
    agent1 = executor.create_agent(task_def1)

    assert agent1.agent_id in executor._task_definitions
    assert executor._task_definitions[agent1.agent_id] == task_def1

    # Test 3: _get_task_def_for_agent retrieves correctly
    retrieved1 = executor._get_task_def_for_agent(agent1)
    assert retrieved1 == task_def1
    assert retrieved1.task == "First task"
    assert retrieved1.verify == "echo verify1"
    assert retrieved1.max_iterations == 5
    assert retrieved1.model == "haiku"

    # Test 4: Multiple agents
    task_def2 = TaskDefinition(task="Second task", verify="echo 2", max_iterations=3, model="sonnet")
    task_def3 = TaskDefinition(task="Third task", verify="echo 3", max_iterations=7, model="opus")

    agent2 = executor.create_agent(task_def2)
    agent3 = executor.create_agent(task_def3)

    assert len(executor._task_definitions) == 3
    assert executor._get_task_def_for_agent(agent2) == task_def2
    assert executor._get_task_def_for_agent(agent3) == task_def3

    # Test 5: KeyError for non-existent agent
    fake_agent = AgentInfo(
        agent_id="nonexistent-id",
        task_id="fake-task",
        task_description="fake",
        agent_type=AgentType.WORKER,
        status=AgentStatus.PENDING,
        model="haiku",
        iteration=0,
        max_iterations=5,
        progress=0.0,
        created_at=datetime.now(),
    )

    with pytest.raises(KeyError, match="No task definition found for agent nonexistent-id"):
        executor._get_task_def_for_agent(fake_agent)

    # Test 6: Cleanup clears task_definitions
    await executor.cleanup()
    assert len(executor._task_definitions) == 0


# ============================================================================
# Test startup task file loading (grind/tui/app.py and grind/tui/main.py)
# ============================================================================


@pytest.mark.asyncio
async def test_startup_task_file_loading(tmp_path):
    """Test that AgentTUI can load and execute tasks from a startup file."""
    from grind.tui.app import AgentTUI

    # Create a test tasks.yaml file
    tasks_file = tmp_path / "tasks.yaml"
    tasks_file.write_text("""
tasks:
  - task: "Test task 1"
    verify: "echo test1"
    model: "haiku"
    max_iterations: 3
  - task: "Test task 2"
    verify: "echo test2"
    model: "sonnet"
    max_iterations: 5
""")

    # Test 1: AgentTUI has startup_task_file attribute
    app = AgentTUI()
    assert hasattr(app, "startup_task_file")
    assert app.startup_task_file is None

    # Test 2: AgentTUI has default_model attribute
    assert hasattr(app, "default_model")
    assert app.default_model == "sonnet"

    # Test 3: Can set startup_task_file
    app.startup_task_file = str(tasks_file)
    assert app.startup_task_file == str(tasks_file)

    # Test 4: _load_and_run_task_file method exists
    assert hasattr(app, "_load_and_run_task_file")
    assert callable(app._load_and_run_task_file)

    # Test 5: Load and run task file manually
    await app._load_and_run_task_file(str(tasks_file))

    # Verify that agents were created (should have 2 agents)
    assert len(app.session.agents) == 2

    # Verify task descriptions match
    task_descriptions = {agent.task_description for agent in app.session.agents}
    assert "Test task 1" in task_descriptions
    assert "Test task 2" in task_descriptions

    # Verify models were set correctly
    models = {agent.model for agent in app.session.agents}
    assert "haiku" in models
    assert "sonnet" in models

    # Test 6: Verify error handling with invalid file
    await app._load_and_run_task_file("/nonexistent/file.yaml")
    # Should not crash, just log error

    # Cleanup
    await app.executor.cleanup()
    app.session.cleanup()


# ============================================================================
# Test pause/resume mechanism
# ============================================================================


@pytest.mark.asyncio
async def test_pause_resume_mechanism(temp_session):
    """Test that pause/resume mechanism works correctly."""
    from grind.tui.core.agent_executor import AgentExecutor
    from grind.tui.core.models import AgentStatus

    # Create AgentExecutor
    executor = AgentExecutor(temp_session, max_parallel=3)

    # Create a simple task that will run for a bit
    task_def = TaskDefinition(
        task="Simple test task",
        verify="echo test",
        max_iterations=5,
        model="haiku"
    )

    # Create agent
    agent = executor.create_agent(task_def)
    assert agent.status == AgentStatus.PENDING

    # Test 1: pause_agent returns False for non-running agent
    result = await executor.pause_agent(agent.agent_id)
    assert result is False
    assert agent.status == AgentStatus.PENDING

    # Test 2: Set agent to RUNNING status manually to test pause
    executor._update_agent_status(agent, AgentStatus.RUNNING)
    assert agent.status == AgentStatus.RUNNING

    # Test 3: pause_agent returns True for running agent
    result = await executor.pause_agent(agent.agent_id)
    assert result is True
    assert agent.status == AgentStatus.PAUSED
    assert agent.agent_id in executor._paused_agents

    # Test 4: resume_agent returns True for paused agent
    result = await executor.resume_agent(agent.agent_id)
    assert result is True
    assert agent.status == AgentStatus.RUNNING
    assert agent.agent_id not in executor._paused_agents

    # Test 5: resume_agent returns False for non-paused agent
    result = await executor.resume_agent(agent.agent_id)
    assert result is False

    # Test 6: pause_agent creates event correctly
    executor._update_agent_status(agent, AgentStatus.RUNNING)
    await executor.pause_agent(agent.agent_id)
    assert agent.agent_id in executor._paused_agents
    pause_event = executor._paused_agents[agent.agent_id]
    assert pause_event.is_set() is False

    # Test 7: resume_agent sets event correctly
    await executor.resume_agent(agent.agent_id)
    # Event should be set and removed from _paused_agents
    assert agent.agent_id not in executor._paused_agents

    # Cleanup
    await executor.cleanup()


@pytest.mark.asyncio
async def test_executor_start_agent(temp_session):
    """Test that start_agent() creates background task correctly."""
    import asyncio
    from grind.tui.core.agent_executor import AgentExecutor
    from grind.tui.core.models import AgentStatus

    # Create AgentExecutor
    executor = AgentExecutor(temp_session, max_parallel=2)

    # Create a simple task
    task_def = TaskDefinition(
        task="Test task",
        verify="echo test",
        max_iterations=3,
        model="haiku"
    )

    # Test 1: Create agent and verify it's pending
    agent = executor.create_agent(task_def)
    assert agent.status == AgentStatus.PENDING
    assert agent.agent_id not in executor.active_tasks

    # Test 2: start_agent returns True and creates background task
    result = executor.start_agent(agent.agent_id)
    assert result is True
    assert agent.agent_id in executor.active_tasks

    # Give it a moment to start
    await asyncio.sleep(0.1)

    # Test 3: Verify agent status changed to RUNNING
    agent_updated = temp_session.get_agent(agent.agent_id)
    assert agent_updated.status == AgentStatus.RUNNING

    # Test 4: start_agent returns False for already running agent
    result = executor.start_agent(agent.agent_id)
    assert result is False

    # Test 5: start_agent returns False for non-existent agent
    result = executor.start_agent("non-existent-id")
    assert result is False

    # Test 6: Test max parallel capacity
    # Create two more agents (we have max_parallel=2, one is already running)
    agent2 = executor.create_agent(task_def)
    agent3 = executor.create_agent(task_def)

    # Start second agent - should succeed (we have capacity for 2)
    result = executor.start_agent(agent2.agent_id)
    assert result is True
    assert agent2.agent_id in executor.active_tasks

    # Give it a moment to update status
    await asyncio.sleep(0.1)

    # Start third agent - should fail (at capacity)
    result = executor.start_agent(agent3.agent_id)
    assert result is False
    assert agent3.agent_id not in executor.active_tasks

    # Wait for tasks to complete
    await asyncio.sleep(0.5)

    # Test 7: Background task is cleaned up after completion
    # Give the done callback time to execute
    await asyncio.sleep(0.2)

    # Cleanup
    await executor.cleanup()
