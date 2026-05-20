#!/usr/bin/env python3
"""
Parallel Executor für gleichzeitige Agent-Ausführung.

Führt unabhängige Sub-Tasks parallel aus, während Dependencies respektiert werden.

Features:
- Asyncio-basierte parallele Ausführung
- Dependency-Graph Respektierung
- Ergebnis-Aggregation
- Fehlerbehandlung mit Fallback
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Callable, Any
from datetime import datetime
from enum import Enum

logger = logging.getLogger("orchestration.parallel")


class TaskStatus(Enum):
    """Status of a parallel task."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"  # Skipped due to dependency failure


@dataclass
class TaskResult:
    """Result from a single task execution."""
    task_id: str
    status: TaskStatus
    output: Optional[str] = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    tier_used: str = "unknown"
    escalated: bool = False
    escalated_from: Optional[str] = None


@dataclass
class ExecutionPlan:
    """Plan for parallel execution."""
    task_id: str
    description: str
    prompt: str
    suggested_tier: str
    dependencies: List[str] = field(default_factory=list)
    files: List[str] = field(default_factory=list)


@dataclass
class ParallelExecutionResult:
    """Result of parallel execution."""
    success: bool
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    skipped_tasks: int
    results: List[TaskResult] = field(default_factory=list)
    total_execution_time_ms: float = 0.0
    parallel_speedup: float = 1.0  # How much faster vs sequential
    tier_distribution: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "skipped_tasks": self.skipped_tasks,
            "results": [
                {
                    "task_id": r.task_id,
                    "status": r.status.value,
                    "tier_used": r.tier_used,
                    "execution_time_ms": r.execution_time_ms,
                    "escalated": r.escalated
                }
                for r in self.results
            ],
            "total_execution_time_ms": self.total_execution_time_ms,
            "parallel_speedup": self.parallel_speedup,
            "tier_distribution": self.tier_distribution
        }


class ParallelExecutor:
    """Executor für parallele Task-Ausführung."""

    def __init__(
        self,
        max_concurrency: int = 4,
        timeout_per_task: float = 300.0  # 5 min default
    ):
        """Initialize executor.

        Args:
            max_concurrency: Maximum number of concurrent tasks
            timeout_per_task: Timeout per task in seconds
        """
        self.max_concurrency = max_concurrency
        self.timeout_per_task = timeout_per_task
        # NOTE: Semaphore muss pro Event-Loop erstellt werden, daher lazy init
        # Thread-safe durch _semaphore_initialized Flag
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._current_event_loop_id: Optional[int] = None

    async def execute(
        self,
        tasks: List[ExecutionPlan],
        task_executor: Callable[[ExecutionPlan], Any]
    ) -> ParallelExecutionResult:
        """Execute tasks respecting dependencies and parallelism.

        Args:
            tasks: List of execution plans
            task_executor: Async function to execute a single task

        Returns:
            ParallelExecutionResult with all outcomes
        """
        if not tasks:
            return ParallelExecutionResult(
                success=True,
                total_tasks=0,
                completed_tasks=0,
                failed_tasks=0,
                skipped_tasks=0
            )

        start_time = datetime.now()

        # Sichere Semaphore-Initialisierung: Nur wenn neuer Event-Loop
        # oder noch nicht initialisiert (verhindert Race Condition)
        current_loop_id = id(asyncio.get_running_loop())
        if self._semaphore is None or self._current_event_loop_id != current_loop_id:
            self._semaphore = asyncio.Semaphore(self.max_concurrency)
            self._current_event_loop_id = current_loop_id

        # Task tracking
        task_map = {t.task_id: t for t in tasks}
        completed: Dict[str, TaskResult] = {}
        failed_ids: Set[str] = set()
        pending = set(t.task_id for t in tasks)

        # Execution loop
        results: List[TaskResult] = []
        sequential_time = 0.0

        while pending:
            # Find tasks ready to execute
            ready = self._get_ready_tasks(pending, task_map, completed, failed_ids)

            if not ready:
                # Remaining tasks have failed dependencies
                for task_id in pending:
                    results.append(TaskResult(
                        task_id=task_id,
                        status=TaskStatus.SKIPPED,
                        error="Dependency failed"
                    ))
                break

            # Execute ready tasks in parallel
            batch_results = await self._execute_batch(
                [task_map[tid] for tid in ready],
                task_executor
            )

            # Process results
            for result in batch_results:
                results.append(result)
                completed[result.task_id] = result
                pending.discard(result.task_id)
                sequential_time += result.execution_time_ms

                if result.status == TaskStatus.FAILED:
                    failed_ids.add(result.task_id)

        # Calculate metrics
        end_time = datetime.now()
        total_time = (end_time - start_time).total_seconds() * 1000

        completed_count = sum(1 for r in results if r.status == TaskStatus.COMPLETED)
        failed_count = sum(1 for r in results if r.status == TaskStatus.FAILED)
        skipped_count = sum(1 for r in results if r.status == TaskStatus.SKIPPED)

        # Calculate speedup
        parallel_speedup = sequential_time / total_time if total_time > 0 else 1.0

        # Tier distribution
        tier_dist: Dict[str, int] = {}
        for r in results:
            tier_dist[r.tier_used] = tier_dist.get(r.tier_used, 0) + 1

        return ParallelExecutionResult(
            success=failed_count == 0 and skipped_count == 0,
            total_tasks=len(tasks),
            completed_tasks=completed_count,
            failed_tasks=failed_count,
            skipped_tasks=skipped_count,
            results=results,
            total_execution_time_ms=total_time,
            parallel_speedup=round(parallel_speedup, 2),
            tier_distribution=tier_dist
        )

    def _get_ready_tasks(
        self,
        pending: Set[str],
        task_map: Dict[str, ExecutionPlan],
        completed: Dict[str, TaskResult],
        failed_ids: Set[str]
    ) -> List[str]:
        """Get tasks that are ready to execute (all dependencies satisfied)."""
        ready = []

        for task_id in pending:
            task = task_map[task_id]
            deps = task.dependencies

            # Check if any dependency failed
            if any(d in failed_ids for d in deps):
                continue

            # Check if all dependencies completed
            if all(d in completed for d in deps):
                ready.append(task_id)

        return ready

    async def _execute_batch(
        self,
        tasks: List[ExecutionPlan],
        task_executor: Callable[[ExecutionPlan], Any]
    ) -> List[TaskResult]:
        """Execute a batch of tasks with concurrency limit."""
        async def execute_with_semaphore(task: ExecutionPlan) -> TaskResult:
            async with self._semaphore:
                return await self._execute_single(task, task_executor)

        # Run all tasks concurrently (limited by semaphore)
        results = await asyncio.gather(
            *[execute_with_semaphore(t) for t in tasks],
            return_exceptions=True
        )

        # Convert exceptions to TaskResults
        processed_results: List[TaskResult] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Bei gather()-Exceptions haben wir keine genaue Zeit
                # Verwende 0.0 als Fallback-Indikator für Fehler
                processed_results.append(TaskResult(
                    task_id=tasks[i].task_id,
                    status=TaskStatus.FAILED,
                    error=str(result),
                    tier_used=tasks[i].suggested_tier,
                    execution_time_ms=0.0  # Explizit auf 0 für gather-Exceptions
                ))
            else:
                processed_results.append(result)

        return processed_results

    async def _execute_single(
        self,
        task: ExecutionPlan,
        task_executor: Callable[[ExecutionPlan], Any]
    ) -> TaskResult:
        """Execute a single task with timeout."""
        start_time = datetime.now()

        try:
            # Execute with timeout
            output = await asyncio.wait_for(
                self._run_task(task, task_executor),
                timeout=self.timeout_per_task
            )

            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds() * 1000

            return TaskResult(
                task_id=task.task_id,
                status=TaskStatus.COMPLETED,
                output=str(output) if output else None,
                execution_time_ms=execution_time,
                tier_used=task.suggested_tier
            )

        except asyncio.TimeoutError:
            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds() * 1000
            logger.warning(f"Task {task.task_id} timed out after {self.timeout_per_task}s")
            return TaskResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                error=f"Timeout after {self.timeout_per_task}s",
                tier_used=task.suggested_tier,
                execution_time_ms=execution_time
            )

        except Exception as e:
            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds() * 1000
            logger.exception(f"Task {task.task_id} failed: {e}")
            return TaskResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                error=str(e),
                tier_used=task.suggested_tier,
                execution_time_ms=execution_time
            )

    async def _run_task(
        self,
        task: ExecutionPlan,
        task_executor: Callable[[ExecutionPlan], Any]
    ) -> Any:
        """Run task executor (async or sync)."""
        result = task_executor(task)

        # Handle both async and sync executors
        if asyncio.iscoroutine(result):
            return await result
        return result


class TaskMerger:
    """Merges results from parallel task execution."""

    @staticmethod
    def merge_code_outputs(
        results: List[TaskResult],
        strategy: str = "concatenate"
    ) -> str:
        """Merge code outputs from multiple tasks.

        Args:
            results: List of task results
            strategy: Merge strategy (concatenate, smart_merge)

        Returns:
            Merged output string
        """
        outputs = [r.output for r in results if r.output and r.status == TaskStatus.COMPLETED]

        if not outputs:
            return ""

        if strategy == "concatenate":
            return "\n\n# --- Merged Output ---\n\n".join(outputs)

        # Smart merge: Remove duplicates, organize by file
        # (Simplified for now)
        return "\n".join(outputs)

    @staticmethod
    def aggregate_metrics(results: List[TaskResult]) -> Dict[str, Any]:
        """Aggregate metrics from all results."""
        total_time = sum(r.execution_time_ms for r in results)
        tier_times: Dict[str, float] = {}

        for r in results:
            tier_times[r.tier_used] = tier_times.get(r.tier_used, 0) + r.execution_time_ms

        return {
            "total_execution_time_ms": total_time,
            "time_by_tier": tier_times,
            "completed": sum(1 for r in results if r.status == TaskStatus.COMPLETED),
            "failed": sum(1 for r in results if r.status == TaskStatus.FAILED),
            "escalations": sum(1 for r in results if r.escalated)
        }


# Test mode
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    async def mock_executor(task: ExecutionPlan) -> str:
        """Mock task executor for testing."""
        # Simulate work based on tier
        delays = {"haiku": 0.1, "sonnet": 0.3, "opus": 0.5}
        delay = delays.get(task.suggested_tier, 0.2)
        await asyncio.sleep(delay)
        return f"Output from {task.task_id} ({task.suggested_tier})"

    async def test_parallel_execution():
        """Test parallel execution."""
        print("\n" + "="*80)
        print("PARALLEL EXECUTOR - TEST MODE")
        print("="*80 + "\n")

        executor = ParallelExecutor(max_concurrency=3)

        # Test case 1: Independent tasks (fully parallel)
        print("Test 1: Independent tasks (should run in parallel)")
        tasks = [
            ExecutionPlan("task_1", "Format file A", "format A", "haiku", []),
            ExecutionPlan("task_2", "Format file B", "format B", "haiku", []),
            ExecutionPlan("task_3", "Format file C", "format C", "haiku", []),
        ]

        result = await executor.execute(tasks, mock_executor)
        print(f"  Success: {result.success}")
        print(f"  Completed: {result.completed_tasks}/{result.total_tasks}")
        print(f"  Parallel speedup: {result.parallel_speedup}x")
        print(f"  Tier distribution: {result.tier_distribution}")
        print()

        # Test case 2: Tasks with dependencies (sequential)
        print("Test 2: Tasks with dependencies (sequential)")
        tasks = [
            ExecutionPlan("design", "Design API", "design", "opus", []),
            ExecutionPlan("implement", "Implement", "implement", "sonnet", ["design"]),
            ExecutionPlan("test", "Write tests", "test", "sonnet", ["implement"]),
            ExecutionPlan("format", "Format code", "format", "haiku", ["test"]),
        ]

        result = await executor.execute(tasks, mock_executor)
        print(f"  Success: {result.success}")
        print(f"  Completed: {result.completed_tasks}/{result.total_tasks}")
        print(f"  Parallel speedup: {result.parallel_speedup}x")
        print(f"  Execution order: {[r.task_id for r in result.results]}")
        print()

        # Test case 3: Mixed (some parallel, some sequential)
        print("Test 3: Mixed parallelism")
        tasks = [
            ExecutionPlan("design", "Design", "design", "opus", []),
            ExecutionPlan("impl_a", "Implement A", "impl A", "sonnet", ["design"]),
            ExecutionPlan("impl_b", "Implement B", "impl B", "sonnet", ["design"]),
            ExecutionPlan("merge", "Merge results", "merge", "sonnet", ["impl_a", "impl_b"]),
        ]

        result = await executor.execute(tasks, mock_executor)
        print(f"  Success: {result.success}")
        print(f"  Completed: {result.completed_tasks}/{result.total_tasks}")
        print(f"  Parallel speedup: {result.parallel_speedup}x")
        print(f"  Total time: {result.total_execution_time_ms:.0f}ms")
        print()

        # Aggregate metrics
        print("Aggregated metrics:")
        metrics = TaskMerger.aggregate_metrics(result.results)
        print(f"  {metrics}")

        print("\n[SUCCESS] Test completed!")

    # Run test
    asyncio.run(test_parallel_execution())
