"""Fusion mode executor for running multiple agents in parallel.

This module provides the FusionExecutor class that orchestrates multiple agents
working on the same task in isolated git worktrees, then combines their solutions.
"""

import asyncio
import json
import secrets
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from grind.engine import grind
from grind.fusion_prompts import build_fusion_prompt, parse_fusion_response
from grind.models import (
    AgentOutput,
    FusionConfig,
    FusionDecision,
    FusionResult,
    GrindResult,
    GrindStatus,
    TaskDefinition,
)
from grind.worktree import WorktreeManager


def generate_session_id() -> str:
    """Generate a unique session ID for fusion execution.

    Returns:
        String in format "fuse_" + 8 random hex characters
    """
    return f"fuse_{secrets.token_hex(4)}"


class FusionExecutor:
    """Executes fusion mode: multiple agents solving the same task in parallel.

    Fusion mode creates isolated git worktrees for each agent, runs them in parallel,
    collects their outputs, and uses a fusion judge agent to combine the best solutions.

    Usage:
        config = FusionConfig(prompt="Fix the bug", verify="pytest", agent_count=3)
        executor = FusionExecutor(config)
        result = await executor.execute(verbose=True)
    """

    def __init__(self, config: FusionConfig):
        """Initialize the FusionExecutor.

        Args:
            config: FusionConfig with task details and fusion parameters
        """
        self.config = config
        self.session_id = generate_session_id()
        self.worktree_manager = WorktreeManager()
        self.agent_outputs: dict[str, AgentOutput] = {}
        self.session_dir = Path.cwd() / ".grind" / "fuse" / self.session_id
        self.status = "initialized"
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at

    async def execute(self, verbose: bool = False) -> FusionResult:
        """Execute the full fusion flow.

        Orchestrates:
        1. Setup worktrees for each agent
        2. Run agents in parallel
        3. Collect results (diffs, file lists)
        4. Run fusion agent if any succeeded
        5. Return FusionResult

        Args:
            verbose: If True, print detailed progress information

        Returns:
            FusionResult with agent outputs and fusion decision
        """
        start_time = time.time()

        try:
            # Save initial manifest
            self.status = "setup"
            self._save_manifest()

            # Setup worktrees
            if verbose:
                print(f"[fusion] Setting up {self.config.agent_count} worktrees...")
            worktree_paths = await self._setup_worktrees()

            # Run agents in parallel
            self.status = "running_agents"
            self._save_manifest()
            if verbose:
                print(f"[fusion] Running {self.config.agent_count} agents in parallel...")
            await self._run_agents(worktree_paths, verbose)

            # Collect results
            self.status = "collecting_results"
            self._save_manifest()
            if verbose:
                print("[fusion] Collecting results from agents...")
            await self._collect_results(worktree_paths)

            # Save agent outputs
            for agent_id, output in self.agent_outputs.items():
                self._save_agent_output(agent_id, output)

            # Run fusion agent
            self.status = "running_fusion"
            self._save_manifest()
            if verbose:
                print("[fusion] Running fusion judge agent...")
            decision, fusion_prompt, fusion_response = await self._run_fusion(verbose)

            # Save fusion output if decision was made
            if decision and fusion_prompt and fusion_response:
                self._save_fusion_output(fusion_prompt, fusion_response, decision)

            duration = time.time() - start_time

            # Determine status
            successful = sum(
                1 for output in self.agent_outputs.values()
                if output.result and output.result.status == GrindStatus.COMPLETE
            )

            if successful == 0:
                status = "no_viable"
            elif decision is None:
                status = "fusion_failed"
            else:
                status = "success"

            # Update final status
            self.status = status
            self._save_manifest()

            return FusionResult(
                config=self.config,
                session_id=self.session_id,
                agent_outputs=self.agent_outputs,
                decision=decision,
                final_patch=None,  # TODO: Generate final patch based on decision
                status=status,
                duration_seconds=duration,
            )

        finally:
            # Cleanup worktrees
            if verbose:
                print("[fusion] Cleaning up worktrees...")
            await self._cleanup_worktrees()

    async def _setup_worktrees(self) -> dict[str, Path]:
        """Create worktrees for each agent.

        Creates N worktrees using WorktreeManager with branch naming:
        f"fuse/{self.session_id}/agent-{n}"

        Returns:
            Dict mapping agent_id -> worktree_path
        """
        worktree_paths: dict[str, Path] = {}

        for n in range(self.config.agent_count):
            agent_id = f"agent-{n}"
            branch = f"fuse/{self.session_id}/{agent_id}"

            worktree_path = await self.worktree_manager.create(
                task_id=f"{self.session_id}/{agent_id}",
                branch=branch,
            )
            worktree_paths[agent_id] = worktree_path

        return worktree_paths

    async def _run_agents(self, worktree_paths: dict[str, Path], verbose: bool) -> None:
        """Run agents in parallel on their worktrees.

        Creates TaskDefinition for each agent with the same prompt but different cwd.
        Uses asyncio.gather() to run all agents via grind().
        Stores GrindResult in self.agent_outputs.

        Args:
            worktree_paths: Dict mapping agent_id -> worktree_path
            verbose: If True, print detailed progress information
        """
        async def run_agent(agent_id: str, worktree_path: Path) -> tuple[str, GrindResult]:
            """Run a single agent and return its result."""
            task_def = TaskDefinition(
                task=self.config.prompt,
                verify=self.config.verify,
                max_iterations=self.config.max_iterations,
                cwd=str(worktree_path),
                model=self.config.model,
            )
            result = await grind(task_def, verbose=verbose)
            return agent_id, result

        # Run all agents in parallel
        tasks = [
            run_agent(agent_id, path)
            for agent_id, path in worktree_paths.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Store results in agent_outputs
        for item in results:
            if isinstance(item, Exception):
                # Handle exceptions by creating a failed result
                continue
            agent_id, result = item
            # Initialize AgentOutput with basic info, diff will be collected later
            self.agent_outputs[agent_id] = AgentOutput(
                agent_id=agent_id,
                worktree_branch=f"fuse/{self.session_id}/{agent_id}",
                result=result,
                diff="",  # Will be collected in _collect_results
                files_changed=[],
                summary=result.message if result else "",
            )

    async def _collect_results(self, worktree_paths: dict[str, Path]) -> None:
        """Collect diffs and file lists from each agent's worktree.

        For each agent:
        - Run git diff to get changes
        - Run git diff --stat for files_changed list
        - Update AgentOutput with diff and files_changed

        Args:
            worktree_paths: Dict mapping agent_id -> worktree_path
        """
        for agent_id, worktree_path in worktree_paths.items():
            if agent_id not in self.agent_outputs:
                continue

            # Get diff
            diff_returncode, diff_stdout, _ = await self.worktree_manager._run_git(
                "diff", "HEAD~1", "--", ".",
                cwd=worktree_path
            )
            diff = diff_stdout if diff_returncode == 0 else ""

            # Get files changed
            stat_returncode, stat_stdout, _ = await self.worktree_manager._run_git(
                "diff", "HEAD~1", "--stat", "--name-only",
                cwd=worktree_path
            )
            files_changed = []
            if stat_returncode == 0 and stat_stdout:
                files_changed = [
                    f.strip() for f in stat_stdout.strip().split("\n")
                    if f.strip()
                ]

            # Update agent output
            self.agent_outputs[agent_id].diff = diff
            self.agent_outputs[agent_id].files_changed = files_changed

    async def _run_fusion(self, verbose: bool) -> tuple[FusionDecision | None, str | None, str | None]:
        """Run the fusion judge agent to combine agent outputs.

        Skips if no agents succeeded. Builds fusion prompt via build_fusion_prompt(),
        runs single grind() call with fusion prompt, parses response via
        parse_fusion_response().

        Args:
            verbose: If True, print detailed progress information

        Returns:
            Tuple of (FusionDecision, prompt, response) or (None, None, None) if fusion fails
        """
        # Skip if no agents succeeded
        successful_count = sum(
            1 for output in self.agent_outputs.values()
            if output.result and output.result.status == GrindStatus.COMPLETE
        )
        if successful_count == 0:
            if verbose:
                print("[fusion] No agents succeeded, skipping fusion")
            return None, None, None

        # Build fusion prompt
        fusion_prompt = build_fusion_prompt(self.config, self.agent_outputs)

        # Create task definition for fusion agent
        task_def = TaskDefinition(
            task=fusion_prompt,
            verify="true",  # Fusion agent doesn't need verification
            max_iterations=3,
            model=self.config.fusion_model,
        )

        # Run fusion agent
        result = await grind(task_def, verbose=verbose)

        if result.status != GrindStatus.COMPLETE:
            if verbose:
                print(f"[fusion] Fusion agent did not complete: {result.status}")
            return None, fusion_prompt, None

        # Parse response
        try:
            decision = parse_fusion_response(result.message)
            return decision, fusion_prompt, result.message
        except ValueError as e:
            if verbose:
                print(f"[fusion] Failed to parse fusion response: {e}")
            return None, fusion_prompt, result.message

    def _save_manifest(self) -> None:
        """Write config, session_id, status, timestamps to manifest.yaml.

        Call after setup and after each major phase.
        """
        self.updated_at = datetime.now().isoformat()

        # Create session directory if it doesn't exist
        self.session_dir.mkdir(parents=True, exist_ok=True)

        manifest_data = {
            "session_id": self.session_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "config": {
                "prompt": self.config.prompt,
                "verify": self.config.verify,
                "agent_count": self.config.agent_count,
                "strategy": self.config.strategy,
                "model": self.config.model,
                "fusion_model": self.config.fusion_model,
                "max_iterations": self.config.max_iterations,
                "timeout_seconds": self.config.timeout_seconds,
            },
            "agent_count": len(self.agent_outputs),
        }

        manifest_path = self.session_dir / "manifest.yaml"
        with open(manifest_path, "w") as f:
            yaml.safe_dump(manifest_data, f, default_flow_style=False, sort_keys=False)

    def _save_agent_output(self, agent_id: str, output: AgentOutput) -> None:
        """Create agent directory and save result.json and diff.patch.

        Args:
            agent_id: ID of the agent (e.g., "agent-0")
            output: AgentOutput containing result and diff
        """
        agent_dir = self.session_dir / agent_id
        agent_dir.mkdir(parents=True, exist_ok=True)

        # Save result.json (serialize GrindResult)
        result_data = {
            "status": output.result.status.value if output.result else None,
            "iterations": output.result.iterations if output.result else 0,
            "message": output.result.message if output.result else "",
            "tools_used": output.result.tools_used if output.result else [],
            "duration_seconds": output.result.duration_seconds if output.result else 0.0,
            "model": output.result.model if output.result else "unknown",
        }

        result_path = agent_dir / "result.json"
        with open(result_path, "w") as f:
            json.dump(result_data, f, indent=2)

        # Save diff.patch
        diff_path = agent_dir / "diff.patch"
        with open(diff_path, "w") as f:
            f.write(output.diff)

    def _save_fusion_output(
        self, prompt: str, response: str, decision: FusionDecision
    ) -> None:
        """Create fusion directory and save prompt.md, response.json, decision.json.

        Args:
            prompt: Prompt sent to fusion judge
            response: Raw response from fusion judge
            decision: Parsed FusionDecision
        """
        fusion_dir = self.session_dir / "fusion"
        fusion_dir.mkdir(parents=True, exist_ok=True)

        # Save prompt.md
        prompt_path = fusion_dir / "prompt.md"
        with open(prompt_path, "w") as f:
            f.write(prompt)

        # Save response.json (raw response as JSON string)
        response_path = fusion_dir / "response.json"
        with open(response_path, "w") as f:
            json.dump({"response": response}, f, indent=2)

        # Save decision.json
        decision_data = {
            "strategy_used": decision.strategy_used,
            "selected_agents": decision.selected_agents,
            "reasoning": decision.reasoning,
            "confidence": decision.confidence,
            "hybrid_instructions": decision.hybrid_instructions,
        }

        decision_path = fusion_dir / "decision.json"
        with open(decision_path, "w") as f:
            json.dump(decision_data, f, indent=2)

    @classmethod
    def load_session(cls, session_id: str) -> "FusionExecutor":
        """Load manifest.yaml and reconstruct FusionExecutor state.

        Used for status/logs commands.

        Args:
            session_id: Session ID to load

        Returns:
            FusionExecutor with reconstructed state

        Raises:
            FileNotFoundError: If session doesn't exist
            ValueError: If manifest is invalid
        """
        session_dir = Path.cwd() / ".grind" / "fuse" / session_id
        manifest_path = session_dir / "manifest.yaml"

        if not manifest_path.exists():
            raise FileNotFoundError(f"Session {session_id} not found")

        with open(manifest_path) as f:
            manifest = yaml.safe_load(f)

        # Reconstruct FusionConfig from manifest
        config_data = manifest["config"]
        config = FusionConfig(
            prompt=config_data["prompt"],
            verify=config_data["verify"],
            agent_count=config_data["agent_count"],
            strategy=config_data["strategy"],
            model=config_data["model"],
            fusion_model=config_data["fusion_model"],
            max_iterations=config_data["max_iterations"],
            timeout_seconds=config_data["timeout_seconds"],
        )

        # Create executor instance
        executor = cls.__new__(cls)
        executor.config = config
        executor.session_id = session_id
        executor.session_dir = session_dir
        executor.status = manifest["status"]
        executor.created_at = manifest["created_at"]
        executor.updated_at = manifest["updated_at"]
        executor.worktree_manager = WorktreeManager()
        executor.agent_outputs = {}

        # Load agent outputs if they exist
        for agent_dir in session_dir.glob("agent-*"):
            agent_id = agent_dir.name
            result_path = agent_dir / "result.json"
            diff_path = agent_dir / "diff.patch"

            if result_path.exists() and diff_path.exists():
                with open(result_path) as f:
                    result_data = json.load(f)

                with open(diff_path) as f:
                    diff = f.read()

                # Reconstruct GrindResult
                result = GrindResult(
                    status=GrindStatus(result_data["status"]) if result_data["status"] else GrindStatus.ERROR,
                    iterations=result_data["iterations"],
                    message=result_data["message"],
                    tools_used=result_data.get("tools_used", []),
                    duration_seconds=result_data.get("duration_seconds", 0.0),
                    model=result_data.get("model", "unknown"),
                )

                # Reconstruct AgentOutput
                output = AgentOutput(
                    agent_id=agent_id,
                    worktree_branch=f"fuse/{session_id}/{agent_id}",
                    result=result,
                    diff=diff,
                    files_changed=[],
                    summary=result.message,
                )

                executor.agent_outputs[agent_id] = output

        return executor

    async def _cleanup_worktrees(self) -> None:
        """Remove all worktrees for this session.

        Uses worktree_manager.cleanup() for each agent worktree.
        """
        for agent_id in self.agent_outputs.keys():
            task_id = f"{self.session_id}/{agent_id}"
            try:
                await self.worktree_manager.cleanup(task_id, force=True)
            except Exception:
                pass  # Best effort cleanup


def list_sessions() -> list[dict[str, Any]]:
    """Scan .grind/fuse/ directory and return list of sessions.

    Returns:
        List of dicts with {session_id, status, created, agent_count}
    """
    fuse_dir = Path.cwd() / ".grind" / "fuse"

    if not fuse_dir.exists():
        return []

    sessions = []

    for session_dir in fuse_dir.iterdir():
        if not session_dir.is_dir():
            continue

        manifest_path = session_dir / "manifest.yaml"
        if not manifest_path.exists():
            continue

        try:
            with open(manifest_path) as f:
                manifest = yaml.safe_load(f)

            # Count agent directories
            agent_count = len(list(session_dir.glob("agent-*")))

            sessions.append({
                "session_id": manifest.get("session_id", session_dir.name),
                "status": manifest.get("status", "unknown"),
                "created": manifest.get("created_at", "unknown"),
                "agent_count": agent_count,
            })
        except Exception:
            # Skip invalid sessions
            continue

    return sessions
