# Expert System Integration Blueprint

Strategic design for integrating expert system intelligence into claude-code-agent orchestration.

---

## Vision

Transform claude-code-agent from **reactive execution engine** to **intelligent orchestrator** that:

1. **Analyzes** task characteristics
2. **Predicts** which orchestration mode will succeed
3. **Selects** optimal configuration (model, parallelism, strategy)
4. **Adapts** based on execution feedback
5. **Learns** from historical trajectories

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│           USER / CLI / WORKFLOW DEFINITION              │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│            EXPERT SYSTEM LAYER                          │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  Task Analyzer       Model Selector    Strategies   │ │
│  │  ├─ Complexity       ├─ Haiku/Sonnet   ├─ Sequential
│  │  ├─ Domain           ├─ Opus/Custom    ├─ Parallel
│  │  ├─ Verify Type      └─ Cost Aware     ├─ Fusion
│  │  └─ Dependencies                       └─ DAG+Fusion
│  └─────────────────────────────────────────────────────┘
│                     │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  Knowledge Base                                     │ │
│  │  ├─ Task Patterns (past successes/failures)        │ │
│  │  ├─ Model Performance (cost/quality trade-offs)    │ │
│  │  ├─ Convergence Data (iteration counts)            │ │
│  │  └─ Domain Heuristics (python vs terraform, etc.)  │ │
│  └─────────────────────────────────────────────────────┘ │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│            ORCHESTRATION LAYER                          │
│  grind() | run_batch() | DAGExecutor | FusionExecutor   │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│         CLAUDE SDK & TOOL EXECUTION                      │
└─────────────────────────────────────────────────────────┘
```

---

## 1. TASK ANALYZER

### Purpose
Characterize incoming tasks to inform orchestration decisions.

### Implementation

```python
from dataclasses import dataclass
from enum import Enum
import re

class TaskComplexity(Enum):
    TRIVIAL = 0.1      # "Add docstring", "Fix typo"
    SIMPLE = 0.3       # "Fix one failing test"
    MODERATE = 0.6     # "Refactor module", "Fix multiple tests"
    COMPLEX = 0.8      # "Redesign authentication"
    VERY_COMPLEX = 1.0 # "Rewrite entire system"

class TaskDomain(Enum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TERRAFORM = "terraform"
    DOCUMENTATION = "docs"
    DEVOPS = "devops"
    UNKNOWN = "unknown"

class VerifyType(Enum):
    UNIT_TEST = "unit"           # pytest, jest, go test
    LINTING = "lint"             # ruff, eslint, terraform fmt
    TYPE_CHECK = "types"         # mypy, tsc
    INTEGRATION = "integration"  # End-to-end tests
    BUILD = "build"              # cargo build, npm build
    MANUAL = "manual"            # Human verification

@dataclass
class TaskCharacteristics:
    """Analyzed properties of a task."""
    complexity: TaskComplexity
    domain: TaskDomain
    verify_type: VerifyType
    has_dependencies: bool
    estimated_iterations: int  # Guess based on pattern
    quality_critical: bool     # Does this need high confidence?
    time_budget: int           # Seconds allowed (from task description)
    suggested_model: str       # haiku | sonnet | opus
    suggested_strategies: list[str]  # [strategy1, strategy2]

class TaskAnalyzer:
    """Analyze task characteristics to inform orchestration."""

    async def analyze(self, task: TaskDefinition) -> TaskCharacteristics:
        """Analyze a task and return characteristics."""
        complexity = self._estimate_complexity(task)
        domain = self._detect_domain(task)
        verify_type = self._classify_verify(task.verify)
        has_deps = bool(task.depends_on)

        iterations = self._estimate_iterations(complexity, domain)
        quality_critical = self._is_quality_critical(task)
        time_budget = self._extract_time_budget(task)
        model = self._recommend_model(complexity, quality_critical)
        strategies = self._recommend_strategies(complexity, domain, verify_type)

        return TaskCharacteristics(
            complexity=complexity,
            domain=domain,
            verify_type=verify_type,
            has_dependencies=has_deps,
            estimated_iterations=iterations,
            quality_critical=quality_critical,
            time_budget=time_budget,
            suggested_model=model,
            suggested_strategies=strategies,
        )

    def _estimate_complexity(self, task: TaskDefinition) -> TaskComplexity:
        """Estimate complexity from task description."""
        desc = task.task.lower()

        trivial_keywords = ["add", "remove", "fix typo", "rename", "docstring"]
        if any(k in desc for k in trivial_keywords):
            return TaskComplexity.TRIVIAL

        simple_keywords = ["one", "simple", "single", "bug fix"]
        if any(k in desc for k in simple_keywords):
            return TaskComplexity.SIMPLE

        complex_keywords = ["refactor", "redesign", "architecture", "rewrite"]
        if any(k in desc for k in complex_keywords):
            return TaskComplexity.VERY_COMPLEX

        return TaskComplexity.MODERATE

    def _detect_domain(self, task: TaskDefinition) -> TaskDomain:
        """Detect programming domain from task."""
        combined = f"{task.task} {task.verify}".lower()

        if re.search(r"\.(py|pytest|ruff|mypy|flask|django)", combined):
            return TaskDomain.PYTHON
        elif re.search(r"\.(js|ts|jest|eslint|npm|react)", combined):
            return TaskDomain.JAVASCRIPT
        elif re.search(r"\.(tf|terraform|aws|vpc)", combined):
            return TaskDomain.TERRAFORM
        elif re.search(r"(markdown|readme|docs|documentation)", combined):
            return TaskDomain.DOCUMENTATION
        elif re.search(r"(docker|kubernetes|helm|devops|ci/cd)", combined):
            return TaskDomain.DEVOPS
        else:
            return TaskDomain.UNKNOWN

    def _classify_verify(self, verify_cmd: str) -> VerifyType:
        """Classify verification command type."""
        v = verify_cmd.lower()

        if re.search(r"pytest|jest|go test|cargo test|npm test", v):
            return VerifyType.UNIT_TEST
        elif re.search(r"ruff|eslint|pylint|fmt|lint", v):
            return VerifyType.LINTING
        elif re.search(r"mypy|tsc|type", v):
            return VerifyType.TYPE_CHECK
        elif re.search(r"integration|e2e|end.to.end", v):
            return VerifyType.INTEGRATION
        elif re.search(r"build|compile|cargo", v):
            return VerifyType.BUILD
        else:
            return VerifyType.MANUAL

    def _estimate_iterations(self, complexity: TaskComplexity, domain: TaskDomain) -> int:
        """Estimate typical iteration count."""
        base = {
            TaskComplexity.TRIVIAL: 1,
            TaskComplexity.SIMPLE: 2,
            TaskComplexity.MODERATE: 4,
            TaskComplexity.COMPLEX: 6,
            TaskComplexity.VERY_COMPLEX: 8,
        }

        # Adjust by domain (terraform is harder than docs)
        multiplier = {
            TaskDomain.TERRAFORM: 1.5,
            TaskDomain.DEVOPS: 1.4,
            TaskDomain.PYTHON: 1.0,
            TaskDomain.JAVASCRIPT: 1.0,
            TaskDomain.DOCUMENTATION: 0.5,
            TaskDomain.UNKNOWN: 1.0,
        }

        return int(base[complexity] * multiplier.get(domain, 1.0))

    def _is_quality_critical(self, task: TaskDefinition) -> bool:
        """Is this task quality-critical?"""
        critical_keywords = [
            "security", "authentication", "encryption", "payment",
            "critical", "production", "must", "essential",
        ]
        desc = task.task.lower()
        return any(k in desc for k in critical_keywords)

    def _extract_time_budget(self, task: TaskDefinition) -> int:
        """Extract time budget from task description if present."""
        # Look for patterns like "within 2 minutes", "30 seconds", etc.
        import re
        match = re.search(r"(\d+)\s*(seconds?|minutes?|hours?)", task.task, re.I)
        if match:
            amount = int(match.group(1))
            unit = match.group(2).lower()
            if "second" in unit:
                return amount
            elif "minute" in unit:
                return amount * 60
            elif "hour" in unit:
                return amount * 3600
        return 300  # Default 5 minutes

    def _recommend_model(self, complexity: TaskComplexity, quality_critical: bool) -> str:
        """Recommend model based on complexity and quality needs."""
        if quality_critical:
            return "opus"  # Always use best for critical tasks

        if complexity == TaskComplexity.TRIVIAL:
            return "haiku"
        elif complexity == TaskComplexity.SIMPLE:
            return "haiku"
        elif complexity == TaskComplexity.MODERATE:
            return "sonnet"
        elif complexity == TaskComplexity.COMPLEX:
            return "sonnet"
        else:
            return "opus"

    def _recommend_strategies(self, complexity: TaskComplexity, domain: TaskDomain, verify_type: VerifyType) -> list[str]:
        """Recommend orchestration strategies."""
        strategies = ["sequential"]

        # High complexity → consider parallel
        if complexity.value > 0.6:
            strategies.append("parallel")

        # Critical quality → consider fusion
        if complexity.value > 0.7:
            strategies.append("fusion")

        # Terraform/DevOps → consider DAG
        if domain in [TaskDomain.TERRAFORM, TaskDomain.DEVOPS]:
            strategies.append("dag")

        return strategies
```

### Usage

```python
analyzer = TaskAnalyzer()
task = TaskDefinition(
    task="Fix critical authentication bug in user login flow",
    verify="pytest tests/auth/ -v",
)
characteristics = await analyzer.analyze(task)

print(f"Complexity: {characteristics.complexity.name}")
print(f"Domain: {characteristics.domain.name}")
print(f"Quality Critical: {characteristics.quality_critical}")
print(f"Suggested Model: {characteristics.suggested_model}")
print(f"Suggested Strategies: {characteristics.suggested_strategies}")
```

---

## 2. MODEL SELECTOR

### Purpose
Select optimal model based on task and cost constraints.

### Implementation

```python
@dataclass
class ModelProfile:
    """Performance profile of a model."""
    name: str
    cost_per_1k_tokens: float      # Input + output
    speed_factor: float             # Relative to haiku (1.0 = baseline)
    quality_factor: float           # 0.0-1.0
    reasoning_depth: float          # 0.0-1.0

class ModelSelector:
    """Select optimal model based on characteristics."""

    # Typical costs (update as pricing changes)
    MODELS = {
        "haiku": ModelProfile(
            name="haiku",
            cost_per_1k_tokens=0.003,  # $0.003/1K tokens
            speed_factor=1.0,          # Baseline
            quality_factor=0.7,
            reasoning_depth=0.5,
        ),
        "sonnet": ModelProfile(
            name="sonnet",
            cost_per_1k_tokens=0.015,
            speed_factor=1.3,
            quality_factor=0.85,
            reasoning_depth=0.75,
        ),
        "opus": ModelProfile(
            name="opus",
            cost_per_1k_tokens=0.06,
            speed_factor=2.0,
            quality_factor=0.95,
            reasoning_depth=0.95,
        ),
    }

    async def select(self,
        characteristics: TaskCharacteristics,
        max_cost: float | None = None,
        max_time: int | None = None,
    ) -> str:
        """Select best model given constraints."""

        # Cost constraint
        if max_cost:
            candidates = [
                m for m in self.MODELS.values()
                if m.cost_per_1k_tokens * 1000 < max_cost  # Rough estimate
            ]
            if not candidates:
                return "haiku"  # Fallback to cheapest
        else:
            candidates = list(self.MODELS.values())

        # Time constraint
        if max_time and max_time < 30:
            # Very tight time budget → fastest model
            return "haiku"

        # Quality constraint
        if characteristics.quality_critical:
            return "opus"

        # Suggested model
        if characteristics.suggested_model in self.MODELS:
            return characteristics.suggested_model

        # Complexity-based fallback
        complexity_to_model = {
            TaskComplexity.TRIVIAL: "haiku",
            TaskComplexity.SIMPLE: "haiku",
            TaskComplexity.MODERATE: "sonnet",
            TaskComplexity.COMPLEX: "sonnet",
            TaskComplexity.VERY_COMPLEX: "opus",
        }

        return complexity_to_model.get(characteristics.complexity, "sonnet")
```

---

## 3. STRATEGY ORCHESTRATOR

### Purpose
Decide which execution strategy to use.

### Implementation

```python
from enum import Enum

class ExecutionStrategy(Enum):
    SEQUENTIAL = "sequential"       # grind()
    BATCH = "batch"                 # run_batch()
    DAG = "dag"                      # DAGExecutor
    FUSION = "fusion"                # FusionExecutor
    DECOMPOSE_BATCH = "decompose"   # decompose() + run_batch()
    DAG_FUSION = "dag_fusion"        # DAG + fusion per task

class StrategyOrchestrator:
    """Decide execution strategy."""

    async def select_strategy(self,
        characteristics: TaskCharacteristics,
        task_count: int = 1,
        has_dependencies: bool = False,
        quality_threshold: float = 0.80,
    ) -> ExecutionStrategy:
        """Select orchestration strategy."""

        # Single task, simple → SEQUENTIAL
        if task_count == 1 and characteristics.complexity.value < 0.5:
            return ExecutionStrategy.SEQUENTIAL

        # Single task, complex → FUSION
        if task_count == 1 and characteristics.quality_critical:
            return ExecutionStrategy.FUSION

        # Single task, moderate → maybe DECOMPOSE
        if task_count == 1 and characteristics.complexity.value >= 0.6:
            return ExecutionStrategy.DECOMPOSE_BATCH

        # Multiple tasks, no deps → BATCH
        if task_count > 1 and not has_dependencies:
            return ExecutionStrategy.BATCH

        # Multiple tasks with deps → DAG
        if task_count > 1 and has_dependencies:
            if characteristics.quality_critical:
                return ExecutionStrategy.DAG_FUSION
            else:
                return ExecutionStrategy.DAG

        # Default
        return ExecutionStrategy.SEQUENTIAL

    async def execute(self,
        strategy: ExecutionStrategy,
        task_or_tasks,
        verbose: bool = False,
    ):
        """Execute using selected strategy."""

        if strategy == ExecutionStrategy.SEQUENTIAL:
            return await grind(task_or_tasks, verbose=verbose)

        elif strategy == ExecutionStrategy.BATCH:
            return await run_batch(task_or_tasks, verbose=verbose)

        elif strategy == ExecutionStrategy.DAG:
            executor = DAGExecutor(task_or_tasks)
            return await executor.execute(verbose=verbose)

        elif strategy == ExecutionStrategy.FUSION:
            executor = FusionExecutor(task_or_tasks)
            return await executor.execute(verbose=verbose)

        elif strategy == ExecutionStrategy.DECOMPOSE_BATCH:
            from grind.engine import decompose
            subtasks = await decompose(
                problem=task_or_tasks.task,
                verify_cmd=task_or_tasks.verify,
            )
            return await run_batch(subtasks, verbose=verbose)

        elif strategy == ExecutionStrategy.DAG_FUSION:
            # For each task in DAG, use fusion
            # (Advanced: implement custom DAGExecutor variant)
            pass
```

---

## 4. TRAJECTORY RECORDER

### Purpose
Capture complete execution trace for learning and replay.

### Implementation

```python
from dataclasses import dataclass
import json
import time

@dataclass
class TokenMetrics:
    """Token usage for a single iteration."""
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float

@dataclass
class IterationTrace:
    """Complete trace of one grind iteration."""
    iteration: int
    timestamp: float
    duration_ms: int
    tokens: TokenMetrics
    tools_called: list[str]
    signals_detected: list[str]  # ["GRIND_COMPLETE", ...]
    success: bool
    error_msg: str | None = None

@dataclass
class ExecutionTrajectory:
    """Full execution trace."""
    task_id: str
    session_id: str
    model: str
    strategy: str  # "sequential", "fusion", etc.
    start_time: float
    end_time: float
    total_duration_s: float
    iterations: list[IterationTrace]
    final_status: str  # "complete", "stuck", "error", etc.
    total_tokens: int
    total_cost_usd: float
    convergence_pattern: str  # "fast", "moderate", "slow", "failed"

class TrajectoryRecorder:
    """Record execution trajectories for analysis."""

    async def record(self,
        task_def: TaskDefinition,
        result: GrindResult,
        event_bus: EventBus | None = None,
    ) -> ExecutionTrajectory:
        """Record a trajectory."""

        # Collect iteration traces from event_bus or result
        iterations = self._extract_iterations(result)

        # Analyze convergence pattern
        pattern = self._analyze_convergence(iterations, result)

        trajectory = ExecutionTrajectory(
            task_id=f"{task_def.task[:50]}",
            session_id=generate_session_id(),
            model=result.model,
            strategy="sequential",  # (would be passed in)
            start_time=time.time() - result.duration_seconds,
            end_time=time.time(),
            total_duration_s=result.duration_seconds,
            iterations=iterations,
            final_status=result.status.value,
            total_tokens=self._estimate_tokens(iterations),
            total_cost_usd=self._estimate_cost(iterations),
            convergence_pattern=pattern,
        )

        # Persist to disk
        await self._save_trajectory(trajectory)

        return trajectory

    def _analyze_convergence(self, iterations: list[IterationTrace], result: GrindResult) -> str:
        """Classify convergence pattern."""
        if result.status.value == "complete":
            if result.iterations <= 2:
                return "fast"
            elif result.iterations <= 5:
                return "moderate"
            else:
                return "slow"
        else:
            return "failed"

    async def _save_trajectory(self, trajectory: ExecutionTrajectory):
        """Persist trajectory to disk."""
        path = Path.cwd() / ".grind" / "trajectories" / f"{trajectory.session_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "task_id": trajectory.task_id,
            "session_id": trajectory.session_id,
            "model": trajectory.model,
            "strategy": trajectory.strategy,
            "total_duration_s": trajectory.total_duration_s,
            "total_tokens": trajectory.total_tokens,
            "total_cost_usd": trajectory.total_cost_usd,
            "convergence_pattern": trajectory.convergence_pattern,
            "final_status": trajectory.final_status,
            "iterations": [
                {
                    "iteration": it.iteration,
                    "duration_ms": it.duration_ms,
                    "tokens": it.tokens.total_tokens,
                    "cost_usd": it.tokens.cost_usd,
                    "tools": it.tools_called,
                    "success": it.success,
                }
                for it in trajectory.iterations
            ],
        }

        with open(path, "w") as f:
            json.dump(data, f, indent=2)
```

---

## 5. KNOWLEDGE BASE

### Purpose
Store learnings from past executions for future decisions.

### Implementation

```python
from pathlib import Path
import json

class KnowledgeBase:
    """Learn from execution history."""

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or Path.cwd() / ".grind" / "knowledge.json"
        self.data = self._load() or {
            "task_patterns": {},
            "model_performance": {},
            "domain_heuristics": {},
        }

    def _load(self) -> dict | None:
        """Load KB from disk."""
        if self.db_path.exists():
            with open(self.db_path) as f:
                return json.load(f)
        return None

    def _save(self):
        """Persist KB to disk."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.db_path, "w") as f:
            json.dump(self.data, f, indent=2)

    def record_execution(self, trajectory: ExecutionTrajectory):
        """Learn from a trajectory."""

        # Pattern: task description → typical iterations
        task_pattern_key = f"{trajectory.model}:{trajectory.convergence_pattern}"
        if task_pattern_key not in self.data["task_patterns"]:
            self.data["task_patterns"][task_pattern_key] = {
                "count": 0,
                "avg_iterations": 0,
                "total_cost": 0.0,
            }

        pattern = self.data["task_patterns"][task_pattern_key]
        pattern["count"] += 1
        pattern["avg_iterations"] = (
            (pattern["avg_iterations"] * (pattern["count"] - 1) + trajectory.iterations[0].iteration) /
            pattern["count"]
        )
        pattern["total_cost"] += trajectory.total_cost_usd

        # Model performance
        model_key = trajectory.model
        if model_key not in self.data["model_performance"]:
            self.data["model_performance"][model_key] = {
                "success_count": 0,
                "failure_count": 0,
                "total_cost": 0.0,
                "total_tokens": 0,
            }

        model_perf = self.data["model_performance"][model_key]
        if trajectory.final_status == "complete":
            model_perf["success_count"] += 1
        else:
            model_perf["failure_count"] += 1
        model_perf["total_cost"] += trajectory.total_cost_usd
        model_perf["total_tokens"] += trajectory.total_tokens

        self._save()

    def predict_cost(self, characteristics: TaskCharacteristics, model: str) -> float:
        """Estimate cost for similar task."""
        pattern_key = f"{model}:{characteristics.domain.name}"
        if pattern_key in self.data["task_patterns"]:
            pattern = self.data["task_patterns"][pattern_key]
            avg_iterations = pattern["avg_iterations"]
            cost_per_iteration = pattern["total_cost"] / (pattern["count"] * avg_iterations + 1)
            return cost_per_iteration * characteristics.estimated_iterations

        # Fallback: rough estimate
        return 0.01 * characteristics.estimated_iterations

    def predict_iterations(self, characteristics: TaskCharacteristics) -> int:
        """Estimate iterations based on history."""
        # Use TaskAnalyzer's estimate + adjustment from KB
        pattern_key = f"{characteristics.domain.name}:{characteristics.complexity.name}"
        if pattern_key in self.data["task_patterns"]:
            pattern = self.data["task_patterns"][pattern_key]
            return int(pattern["avg_iterations"])

        return characteristics.estimated_iterations
```

---

## 6. INTEGRATION EXAMPLE

### Complete Expert System Usage

```python
from expert_system import (
    TaskAnalyzer,
    ModelSelector,
    StrategyOrchestrator,
    TrajectoryRecorder,
    KnowledgeBase,
)

async def intelligent_grind():
    # Initialize expert system
    analyzer = TaskAnalyzer()
    selector = ModelSelector()
    orchestrator = StrategyOrchestrator()
    kb = KnowledgeBase()

    # Define task
    task = TaskDefinition(
        task="Fix authentication bug in critical path - must complete in 2 minutes",
        verify="pytest tests/auth/ -v",
    )

    # PHASE 1: ANALYZE
    print("📊 Analyzing task...")
    characteristics = await analyzer.analyze(task)
    print(f"  Complexity: {characteristics.complexity.name}")
    print(f"  Quality Critical: {characteristics.quality_critical}")
    print(f"  Estimated Iterations: {characteristics.estimated_iterations}")

    # PHASE 2: SELECT MODEL
    print("🧠 Selecting model...")
    max_cost = 0.50  # Budget
    model = await selector.select(characteristics, max_cost=max_cost)
    task.model = model
    print(f"  Selected: {model}")

    # PHASE 3: PREDICT COST
    print("💰 Predicting cost...")
    predicted_cost = kb.predict_cost(characteristics, model)
    predicted_iterations = kb.predict_iterations(characteristics)
    print(f"  Predicted cost: ${predicted_cost:.2f}")
    print(f"  Predicted iterations: {predicted_iterations}")

    # PHASE 4: SELECT STRATEGY
    print("🎯 Selecting strategy...")
    strategy = await orchestrator.select_strategy(characteristics)
    print(f"  Selected: {strategy.value}")

    # PHASE 5: EXECUTE
    print("⚡ Executing...")
    start_time = time.time()
    result = await orchestrator.execute(strategy, task, verbose=False)
    duration = time.time() - start_time

    # PHASE 6: RECORD TRAJECTORY
    print("📝 Recording trajectory...")
    recorder = TrajectoryRecorder()
    trajectory = await recorder.record(task, result)
    print(f"  Trajectory ID: {trajectory.session_id}")

    # PHASE 7: LEARN
    print("🧠 Learning...")
    kb.record_execution(trajectory)
    print(f"  KB updated")

    # RESULTS
    print("\n✅ Results:")
    print(f"  Status: {result.status.value}")
    print(f"  Iterations: {result.iterations}")
    print(f"  Duration: {duration:.1f}s")
    print(f"  Cost: ${trajectory.total_cost_usd:.2f} (predicted ${predicted_cost:.2f})")
    print(f"  Accuracy: {(1 - abs(predicted_cost - trajectory.total_cost_usd) / predicted_cost):.1%}")
```

---

## 7. LEARNING LOOP METRICS

### What to Measure

```python
@dataclass
class ExpertSystemMetrics:
    """Track expert system performance."""
    # Accuracy metrics
    model_selection_accuracy: float      # How often right model chosen?
    strategy_selection_accuracy: float   # How often right strategy chosen?
    cost_prediction_error: float         # How close cost predictions?
    iteration_prediction_error: float    # How close iteration predictions?

    # Efficiency metrics
    avg_cost_per_task: float
    avg_iterations_per_task: float
    avg_duration_per_task: float

    # Quality metrics
    success_rate: float                  # % of tasks that complete
    quality_above_threshold: float       # % exceeding quality threshold

    # Learning metrics
    kb_size: int                         # Trajectories in KB
    last_update: str                     # Last trajectory recorded
```

---

## 8. DEPLOYMENT PHASES

### Phase 1: Foundation (Week 1)
- [ ] Implement TaskAnalyzer
- [ ] Implement ModelSelector
- [ ] Test on 50 historical tasks
- [ ] Measure baseline accuracy

### Phase 2: Orchestration (Week 2)
- [ ] Implement StrategyOrchestrator
- [ ] Add strategy recommendation to CLI
- [ ] A/B test: recommended vs default
- [ ] Measure success rate improvement

### Phase 3: Learning (Week 3)
- [ ] Implement TrajectoryRecorder
- [ ] Implement KnowledgeBase
- [ ] Auto-record all executions
- [ ] Measure prediction accuracy improvement

### Phase 4: Feedback Loop (Week 4)
- [ ] Expert system learns from KB
- [ ] Automatic refinement of heuristics
- [ ] Dashboard showing improvements
- [ ] Production rollout

---

## 9. Success Criteria

| Metric | Target | Baseline |
|--------|--------|----------|
| Cost prediction error | < 20% | TBD |
| Iteration prediction error | < 15% | TBD |
| Model selection accuracy | > 85% | ~60% |
| Strategy selection accuracy | > 80% | ~50% |
| Overall task success rate | > 90% | Current % |

---

## Conclusion

This blueprint provides a pathway to transform claude-code-agent into an intelligent orchestrator that:

1. **Understands** task characteristics
2. **Learns** from execution history
3. **Predicts** optimal configurations
4. **Adapts** based on feedback
5. **Improves** over time

The modular design allows phased implementation with measurable improvements at each phase.

---

**Blueprint Version:** 1.0
**Target Completion:** 4 weeks
**Complexity:** Medium (250-500 LOC per component)
**ROI:** 20-40% cost savings + 30-50% improved reliability
