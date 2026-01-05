"""Unit tests for parallel_executor.py.

Tests für den parallelen Task-Executor mit Dependency-Graph Unterstützung.

Hinweis: Diese Tests sind unabhängig vom Haupt-conftest.py und importieren
direkt aus dem MCP-Server Verzeichnis.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime
import sys
from pathlib import Path

# Konfigurations-Marker für pytest
pytestmark = pytest.mark.unit

# Add MCP server to path BEFORE imports
_mcp_path = str(Path(__file__).parent.parent.parent.parent / ".claude" / "mcp-server")
if _mcp_path not in sys.path:
    sys.path.insert(0, _mcp_path)

from parallel_executor import (
    ParallelExecutor,
    ExecutionPlan,
    TaskResult,
    TaskStatus,
    ParallelExecutionResult,
    TaskMerger,
)


class TestParallelExecutor:
    """Tests für die ParallelExecutor Klasse."""

    @pytest.mark.asyncio
    async def test_execute_empty_tasks(self):
        """Leere Task-Liste sollte erfolgreiche leere Ergebnisse liefern."""
        executor = ParallelExecutor()

        async def mock_executor(task: ExecutionPlan) -> str:
            return "output"

        result = await executor.execute([], mock_executor)

        assert result.success is True
        assert result.total_tasks == 0
        assert result.completed_tasks == 0
        assert result.failed_tasks == 0
        assert result.skipped_tasks == 0
        assert len(result.results) == 0

    @pytest.mark.asyncio
    async def test_execute_single_task(self):
        """Einzelner Task sollte korrekt ausgeführt werden."""
        executor = ParallelExecutor()

        async def mock_executor(task: ExecutionPlan) -> str:
            return f"Output for {task.task_id}"

        tasks = [
            ExecutionPlan(
                task_id="task_1",
                description="Test task",
                prompt="Do something",
                suggested_tier="sonnet"
            )
        ]

        result = await executor.execute(tasks, mock_executor)

        assert result.success is True
        assert result.total_tasks == 1
        assert result.completed_tasks == 1
        assert result.failed_tasks == 0
        assert len(result.results) == 1
        assert result.results[0].status == TaskStatus.COMPLETED
        assert result.results[0].task_id == "task_1"

    @pytest.mark.asyncio
    async def test_execute_independent_tasks_parallel(self):
        """Unabhängige Tasks sollten parallel ausgeführt werden."""
        executor = ParallelExecutor(max_concurrency=3)
        execution_times = []

        async def mock_executor(task: ExecutionPlan) -> str:
            start = datetime.now()
            await asyncio.sleep(0.1)  # 100ms delay
            end = datetime.now()
            execution_times.append((task.task_id, start, end))
            return f"Output for {task.task_id}"

        tasks = [
            ExecutionPlan(f"task_{i}", f"Task {i}", f"Prompt {i}", "haiku")
            for i in range(3)
        ]

        result = await executor.execute(tasks, mock_executor)

        assert result.success is True
        assert result.completed_tasks == 3

        # Prüfe, dass Tasks parallel liefen (Überlappung)
        starts = [t[1] for t in execution_times]
        ends = [t[2] for t in execution_times]

        # Bei echter Parallelität: Gesamtzeit sollte ~100ms sein, nicht ~300ms
        total_time = (max(ends) - min(starts)).total_seconds()
        assert total_time < 0.25, "Tasks sollten parallel laufen"

    @pytest.mark.asyncio
    async def test_execute_with_dependencies(self):
        """Tasks mit Dependencies sollten in korrekter Reihenfolge ausgeführt werden."""
        executor = ParallelExecutor()
        execution_order = []

        async def mock_executor(task: ExecutionPlan) -> str:
            execution_order.append(task.task_id)
            await asyncio.sleep(0.01)
            return f"Output for {task.task_id}"

        tasks = [
            ExecutionPlan("design", "Design", "Design API", "opus", []),
            ExecutionPlan("implement", "Implement", "Code it", "sonnet", ["design"]),
            ExecutionPlan("test", "Test", "Write tests", "sonnet", ["implement"]),
        ]

        result = await executor.execute(tasks, mock_executor)

        assert result.success is True
        assert result.completed_tasks == 3
        # Reihenfolge muss respektiert werden
        assert execution_order.index("design") < execution_order.index("implement")
        assert execution_order.index("implement") < execution_order.index("test")

    @pytest.mark.asyncio
    async def test_execute_mixed_parallelism(self):
        """Gemischte Parallelität sollte korrekt funktionieren."""
        executor = ParallelExecutor(max_concurrency=4)
        execution_order = []

        async def mock_executor(task: ExecutionPlan) -> str:
            execution_order.append(task.task_id)
            await asyncio.sleep(0.01)
            return f"Output for {task.task_id}"

        # design -> (impl_a, impl_b parallel) -> merge
        tasks = [
            ExecutionPlan("design", "Design", "Design", "opus", []),
            ExecutionPlan("impl_a", "Impl A", "Impl A", "sonnet", ["design"]),
            ExecutionPlan("impl_b", "Impl B", "Impl B", "sonnet", ["design"]),
            ExecutionPlan("merge", "Merge", "Merge", "sonnet", ["impl_a", "impl_b"]),
        ]

        result = await executor.execute(tasks, mock_executor)

        assert result.success is True
        assert result.completed_tasks == 4
        # design muss vor impl_a und impl_b kommen
        assert execution_order.index("design") < execution_order.index("impl_a")
        assert execution_order.index("design") < execution_order.index("impl_b")
        # merge muss nach impl_a und impl_b kommen
        assert execution_order.index("impl_a") < execution_order.index("merge")
        assert execution_order.index("impl_b") < execution_order.index("merge")

    @pytest.mark.asyncio
    async def test_execute_with_task_failure(self):
        """Fehlgeschlagene Tasks sollten korrekt behandelt werden."""
        executor = ParallelExecutor()

        async def failing_executor(task: ExecutionPlan) -> str:
            if task.task_id == "task_2":
                raise ValueError("Task 2 failed!")
            return f"Output for {task.task_id}"

        tasks = [
            ExecutionPlan("task_1", "Task 1", "Prompt 1", "haiku"),
            ExecutionPlan("task_2", "Task 2", "Prompt 2", "haiku"),
            ExecutionPlan("task_3", "Task 3", "Prompt 3", "haiku"),
        ]

        result = await executor.execute(tasks, failing_executor)

        assert result.success is False  # Mindestens ein Task fehlgeschlagen
        assert result.completed_tasks == 2
        assert result.failed_tasks == 1

        failed_task = next(r for r in result.results if r.task_id == "task_2")
        assert failed_task.status == TaskStatus.FAILED
        assert "Task 2 failed!" in failed_task.error

    @pytest.mark.asyncio
    async def test_execute_with_dependency_failure_skips_dependents(self):
        """Tasks mit fehlgeschlagenen Dependencies sollten übersprungen werden."""
        executor = ParallelExecutor()

        async def failing_executor(task: ExecutionPlan) -> str:
            if task.task_id == "design":
                raise ValueError("Design failed!")
            return f"Output for {task.task_id}"

        tasks = [
            ExecutionPlan("design", "Design", "Design", "opus", []),
            ExecutionPlan("implement", "Implement", "Code", "sonnet", ["design"]),
            ExecutionPlan("test", "Test", "Test", "sonnet", ["implement"]),
        ]

        result = await executor.execute(tasks, failing_executor)

        assert result.success is False
        assert result.failed_tasks == 1  # design failed
        assert result.skipped_tasks == 2  # implement und test übersprungen

        skipped = [r for r in result.results if r.status == TaskStatus.SKIPPED]
        assert len(skipped) == 2

    @pytest.mark.asyncio
    async def test_execute_with_timeout(self):
        """Tasks sollten bei Timeout fehlschlagen."""
        executor = ParallelExecutor(timeout_per_task=0.1)  # 100ms timeout

        async def slow_executor(task: ExecutionPlan) -> str:
            await asyncio.sleep(1.0)  # Länger als Timeout
            return "Output"

        tasks = [ExecutionPlan("slow_task", "Slow", "Slow", "sonnet")]

        result = await executor.execute(tasks, slow_executor)

        assert result.success is False
        assert result.failed_tasks == 1
        assert "Timeout" in result.results[0].error
        # execution_time_ms sollte vorhanden sein
        assert result.results[0].execution_time_ms > 0

    @pytest.mark.asyncio
    async def test_execution_time_recorded(self):
        """Execution time sollte für alle Tasks aufgezeichnet werden."""
        executor = ParallelExecutor()

        async def mock_executor(task: ExecutionPlan) -> str:
            await asyncio.sleep(0.05)  # 50ms
            return "Output"

        tasks = [ExecutionPlan("task_1", "Task", "Prompt", "sonnet")]

        result = await executor.execute(tasks, mock_executor)

        assert result.results[0].execution_time_ms >= 40  # Mindestens ~50ms
        assert result.results[0].execution_time_ms < 200  # Nicht zu viel

    @pytest.mark.asyncio
    async def test_tier_distribution_calculated(self):
        """Tier-Verteilung sollte korrekt berechnet werden."""
        executor = ParallelExecutor()

        async def mock_executor(task: ExecutionPlan) -> str:
            return "Output"

        tasks = [
            ExecutionPlan("t1", "T1", "P1", "haiku"),
            ExecutionPlan("t2", "T2", "P2", "haiku"),
            ExecutionPlan("t3", "T3", "P3", "sonnet"),
            ExecutionPlan("t4", "T4", "P4", "opus"),
        ]

        result = await executor.execute(tasks, mock_executor)

        assert result.tier_distribution["haiku"] == 2
        assert result.tier_distribution["sonnet"] == 1
        assert result.tier_distribution["opus"] == 1

    @pytest.mark.asyncio
    async def test_parallel_speedup_calculated(self):
        """Parallel Speedup sollte berechnet werden."""
        executor = ParallelExecutor(max_concurrency=3)

        async def mock_executor(task: ExecutionPlan) -> str:
            await asyncio.sleep(0.1)
            return "Output"

        tasks = [
            ExecutionPlan(f"task_{i}", f"Task {i}", f"Prompt {i}", "haiku")
            for i in range(3)
        ]

        result = await executor.execute(tasks, mock_executor)

        # Speedup sollte > 1 sein bei paralleler Ausführung
        assert result.parallel_speedup > 1.0

    @pytest.mark.asyncio
    async def test_semaphore_reuse_across_calls(self):
        """Semaphore sollte zwischen Aufrufen wiederverwendet werden."""
        executor = ParallelExecutor(max_concurrency=2)

        async def mock_executor(task: ExecutionPlan) -> str:
            return "Output"

        # Erster Aufruf
        await executor.execute([ExecutionPlan("t1", "T", "P", "haiku")], mock_executor)
        first_semaphore = executor._semaphore
        first_loop_id = executor._current_event_loop_id

        # Zweiter Aufruf
        await executor.execute([ExecutionPlan("t2", "T", "P", "haiku")], mock_executor)

        # Sollte dieselbe Semaphore sein
        assert executor._semaphore is first_semaphore
        assert executor._current_event_loop_id == first_loop_id

    @pytest.mark.asyncio
    async def test_sync_executor_supported(self):
        """Synchrone Executors sollten auch funktionieren."""
        executor = ParallelExecutor()

        def sync_executor(task: ExecutionPlan) -> str:
            return f"Sync output for {task.task_id}"

        tasks = [ExecutionPlan("sync_task", "Sync", "Prompt", "haiku")]

        result = await executor.execute(tasks, sync_executor)

        assert result.success is True
        assert result.completed_tasks == 1


class TestTaskMerger:
    """Tests für die TaskMerger Klasse."""

    def test_merge_code_outputs_concatenate(self):
        """Code-Outputs sollten korrekt zusammengeführt werden."""
        results = [
            TaskResult("t1", TaskStatus.COMPLETED, "def func1(): pass"),
            TaskResult("t2", TaskStatus.COMPLETED, "def func2(): pass"),
        ]

        merged = TaskMerger.merge_code_outputs(results, "concatenate")

        assert "def func1(): pass" in merged
        assert "def func2(): pass" in merged
        assert "Merged Output" in merged

    def test_merge_code_outputs_ignores_failed(self):
        """Fehlgeschlagene Tasks sollten nicht in Merge einbezogen werden."""
        results = [
            TaskResult("t1", TaskStatus.COMPLETED, "def func1(): pass"),
            TaskResult("t2", TaskStatus.FAILED, None, error="Failed"),
        ]

        merged = TaskMerger.merge_code_outputs(results, "concatenate")

        assert "def func1(): pass" in merged
        assert "Failed" not in merged

    def test_merge_code_outputs_empty(self):
        """Leere Ergebnisse sollten leeren String liefern."""
        results = [
            TaskResult("t1", TaskStatus.FAILED, None, error="Failed"),
        ]

        merged = TaskMerger.merge_code_outputs(results, "concatenate")

        assert merged == ""

    def test_aggregate_metrics(self):
        """Metriken sollten korrekt aggregiert werden."""
        results = [
            TaskResult("t1", TaskStatus.COMPLETED, execution_time_ms=100, tier_used="haiku"),
            TaskResult("t2", TaskStatus.COMPLETED, execution_time_ms=200, tier_used="sonnet"),
            TaskResult("t3", TaskStatus.FAILED, execution_time_ms=50, tier_used="haiku", error="Error"),
            TaskResult("t4", TaskStatus.COMPLETED, execution_time_ms=300, tier_used="opus", escalated=True),
        ]

        metrics = TaskMerger.aggregate_metrics(results)

        assert metrics["total_execution_time_ms"] == 650
        assert metrics["completed"] == 3
        assert metrics["failed"] == 1
        assert metrics["escalations"] == 1
        assert metrics["time_by_tier"]["haiku"] == 150
        assert metrics["time_by_tier"]["sonnet"] == 200
        assert metrics["time_by_tier"]["opus"] == 300


class TestParallelExecutionResult:
    """Tests für ParallelExecutionResult."""

    def test_to_dict(self):
        """to_dict sollte korrekte Struktur zurückgeben."""
        result = ParallelExecutionResult(
            success=True,
            total_tasks=2,
            completed_tasks=2,
            failed_tasks=0,
            skipped_tasks=0,
            results=[
                TaskResult("t1", TaskStatus.COMPLETED, "output", tier_used="sonnet", execution_time_ms=100),
                TaskResult("t2", TaskStatus.COMPLETED, "output", tier_used="haiku", execution_time_ms=50),
            ],
            total_execution_time_ms=150,
            parallel_speedup=1.5,
            tier_distribution={"sonnet": 1, "haiku": 1}
        )

        d = result.to_dict()

        assert d["success"] is True
        assert d["total_tasks"] == 2
        assert d["completed_tasks"] == 2
        assert d["failed_tasks"] == 0
        assert d["skipped_tasks"] == 0
        assert len(d["results"]) == 2
        assert d["results"][0]["task_id"] == "t1"
        assert d["results"][0]["status"] == "completed"
        assert d["parallel_speedup"] == 1.5
        assert d["tier_distribution"]["sonnet"] == 1


class TestExecutionPlan:
    """Tests für ExecutionPlan dataclass."""

    def test_default_values(self):
        """Default-Werte sollten korrekt gesetzt sein."""
        plan = ExecutionPlan(
            task_id="t1",
            description="Test",
            prompt="Do something",
            suggested_tier="sonnet"
        )

        assert plan.dependencies == []
        assert plan.files == []

    def test_with_dependencies(self):
        """Dependencies sollten korrekt gesetzt werden."""
        plan = ExecutionPlan(
            task_id="t1",
            description="Test",
            prompt="Do something",
            suggested_tier="sonnet",
            dependencies=["t0"]
        )

        assert plan.dependencies == ["t0"]


class TestTaskResult:
    """Tests für TaskResult dataclass."""

    def test_default_values(self):
        """Default-Werte sollten korrekt gesetzt sein."""
        result = TaskResult(
            task_id="t1",
            status=TaskStatus.COMPLETED
        )

        assert result.output is None
        assert result.error is None
        assert result.execution_time_ms == 0.0
        assert result.tier_used == "unknown"
        assert result.escalated is False
        assert result.escalated_from is None
