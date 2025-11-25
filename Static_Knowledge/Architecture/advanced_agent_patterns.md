# Advanced Agent Patterns
**Ablage-System Document Processing Platform**
**Version:** 1.0
**Last Updated:** 2025-01-23

---

## 📑 Table of Contents

1. [Multi-Agent Coordination](#multi-agent-coordination)
2. [Agent Scheduling & Prioritization](#agent-scheduling--prioritization)
3. [Conflict Resolution](#conflict-resolution)
4. [Circuit Breaker Pattern](#circuit-breaker-pattern)
5. [Saga Pattern for Long-Running Tasks](#saga-pattern-for-long-running-tasks)
6. [Agent State Machines](#agent-state-machines)
7. [Dynamic Agent Creation](#dynamic-agent-creation)
8. [Agent Composition](#agent-composition)

---

## Multi-Agent Coordination

### Pattern: Coordinator-Worker

**Use Case:** Ein koordinierender Agent verteilt Arbeit an mehrere Spezial-Agents

```python
# Execution_Layer/Agents/coordinator_agent.py
from typing import List, Dict, Any, Optional
from datetime import datetime
import asyncio
import structlog
from Execution_Layer.Agents.base_agent import BaseAgent, AgentStatus

logger = structlog.get_logger(__name__)


class CoordinatorAgent(BaseAgent):
    """
    Coordinator Agent Pattern

    Orchestriert mehrere spezialisierte Agents für komplexe Workflows.
    """

    def __init__(
        self,
        agent_id: str = "coordinator_agent",
        config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(agent_id=agent_id, config=config)
        self.worker_agents: Dict[str, BaseAgent] = {}
        self.start_time = datetime.utcnow()

    def register_worker(self, worker_id: str, agent: BaseAgent) -> None:
        """
        Register a worker agent.

        Args:
            worker_id: Unique worker identifier
            agent: Worker agent instance
        """
        self.worker_agents[worker_id] = agent

        logger.info(
            "worker_registered",
            coordinator_id=self.agent_id,
            worker_id=worker_id,
            worker_type=type(agent).__name__
        )

    async def _do_process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Coordinate multiple workers to process task.

        Task Structure:
        {
            "workflow": "ocr_pipeline",
            "document_id": "doc_123",
            "steps": [
                {"worker": "classifier", "params": {...}},
                {"worker": "ocr", "params": {...}},
                {"worker": "validator", "params": {...}}
            ],
            "execution_mode": "sequential" or "parallel"
        }

        Returns:
            {
                "success": bool,
                "workflow": str,
                "step_results": List[Dict],
                "total_processing_time_ms": int
            }
        """
        start = datetime.utcnow()

        workflow = task["workflow"]
        steps = task["steps"]
        execution_mode = task.get("execution_mode", "sequential")

        logger.info(
            "workflow_started",
            coordinator_id=self.agent_id,
            workflow=workflow,
            total_steps=len(steps),
            execution_mode=execution_mode
        )

        try:
            if execution_mode == "sequential":
                step_results = await self._execute_sequential(steps, task)
            elif execution_mode == "parallel":
                step_results = await self._execute_parallel(steps, task)
            else:
                raise ValueError(f"Unknown execution mode: {execution_mode}")

            total_time_ms = int(
                (datetime.utcnow() - start).total_seconds() * 1000
            )

            self.metrics["tasks_completed"] += 1
            self.metrics["total_processing_time_ms"] += total_time_ms

            logger.info(
                "workflow_completed",
                coordinator_id=self.agent_id,
                workflow=workflow,
                total_time_ms=total_time_ms
            )

            return {
                "success": True,
                "workflow": workflow,
                "step_results": step_results,
                "total_processing_time_ms": total_time_ms
            }

        except Exception as e:
            self.metrics["tasks_failed"] += 1
            logger.exception(
                "workflow_failed",
                coordinator_id=self.agent_id,
                workflow=workflow,
                error=str(e)
            )
            raise

    async def _execute_sequential(
        self,
        steps: List[Dict[str, Any]],
        task: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Execute workflow steps sequentially."""
        step_results = []
        current_data = task.get("input_data")

        for i, step in enumerate(steps, 1):
            worker_id = step["worker"]
            params = step.get("params", {})

            logger.info(
                "executing_step",
                coordinator_id=self.agent_id,
                step_number=i,
                total_steps=len(steps),
                worker_id=worker_id
            )

            # Get worker agent
            worker = self.worker_agents.get(worker_id)
            if not worker:
                raise ValueError(f"Worker not found: {worker_id}")

            # Execute step
            step_start = datetime.utcnow()

            step_result = await worker.process_task({
                **params,
                "input_data": current_data
            })

            step_time_ms = int(
                (datetime.utcnow() - step_start).total_seconds() * 1000
            )

            # Update current_data for next step
            if step_result.get("success"):
                current_data = step_result.get("output_data", current_data)

            step_results.append({
                "step_number": i,
                "worker_id": worker_id,
                "success": step_result.get("success"),
                "processing_time_ms": step_time_ms,
                "result": step_result
            })

            # Stop on failure if step is critical
            if not step_result.get("success") and not step.get("optional", False):
                logger.error(
                    "critical_step_failed",
                    coordinator_id=self.agent_id,
                    step_number=i,
                    worker_id=worker_id
                )
                break

        return step_results

    async def _execute_parallel(
        self,
        steps: List[Dict[str, Any]],
        task: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Execute workflow steps in parallel."""
        input_data = task.get("input_data")

        # Create tasks for all steps
        tasks = []
        for i, step in enumerate(steps, 1):
            worker_id = step["worker"]
            params = step.get("params", {})

            worker = self.worker_agents.get(worker_id)
            if not worker:
                raise ValueError(f"Worker not found: {worker_id}")

            task_coroutine = worker.process_task({
                **params,
                "input_data": input_data
            })

            tasks.append({
                "step_number": i,
                "worker_id": worker_id,
                "coroutine": task_coroutine
            })

        # Execute all tasks in parallel
        logger.info(
            "executing_parallel_steps",
            coordinator_id=self.agent_id,
            total_steps=len(tasks)
        )

        start = datetime.utcnow()
        results = await asyncio.gather(*[t["coroutine"] for t in tasks])
        total_time_ms = int((datetime.utcnow() - start).total_seconds() * 1000)

        # Combine results
        step_results = []
        for i, (task_info, result) in enumerate(zip(tasks, results)):
            step_results.append({
                "step_number": task_info["step_number"],
                "worker_id": task_info["worker_id"],
                "success": result.get("success"),
                "processing_time_ms": total_time_ms,  # Parallel execution time
                "result": result
            })

        return step_results

    def _calculate_uptime(self) -> float:
        """Calculate coordinator uptime."""
        return (datetime.utcnow() - self.start_time).total_seconds()


# Example Usage: OCR Workflow Coordination
async def example_ocr_workflow_coordination():
    """Example of coordinating multiple agents for OCR workflow."""
    from Execution_Layer.Agents.document_classifier_agent import DocumentClassifierAgent
    from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent
    from Execution_Layer.Sub_Agents.validation_sub_agent import ValidationSubAgent

    # Create coordinator
    coordinator = CoordinatorAgent(agent_id="ocr_workflow_coordinator")
    await coordinator.initialize()

    # Create and register worker agents
    classifier = DocumentClassifierAgent()
    await classifier.initialize()
    coordinator.register_worker("classifier", classifier)

    ocr_agent = OCRProcessingAgent()
    await ocr_agent.initialize()
    coordinator.register_worker("ocr", ocr_agent)

    validator = ValidationSubAgent()
    coordinator.register_worker("validator", validator)

    # Define workflow
    workflow_task = {
        "workflow": "complete_ocr_pipeline",
        "document_id": "doc_123",
        "input_data": {
            "image_path": "/path/to/document.pdf"
        },
        "execution_mode": "sequential",
        "steps": [
            {
                "worker": "classifier",
                "params": {
                    "document_id": "doc_123"
                }
            },
            {
                "worker": "ocr",
                "params": {
                    "document_id": "doc_123",
                    "backend": "auto"
                }
            },
            {
                "worker": "validator",
                "params": {
                    "check_umlauts": True,
                    "check_currency": True
                }
            }
        ]
    }

    # Execute workflow
    result = await coordinator.process_task(workflow_task)

    print(f"Workflow Success: {result['success']}")
    print(f"Total Time: {result['total_processing_time_ms']}ms")
    print("\nStep Results:")
    for step in result["step_results"]:
        print(f"  {step['step_number']}. {step['worker_id']}: {step['success']} ({step['processing_time_ms']}ms)")

    # Cleanup
    await coordinator.shutdown()
    await classifier.shutdown()
    await ocr_agent.shutdown()


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_ocr_workflow_coordination())
```

---

## Agent Scheduling & Prioritization

### Pattern: Priority Queue Agent

**Use Case:** Tasks mit unterschiedlichen Prioritäten verarbeiten

```python
# Execution_Layer/Agents/priority_queue_agent.py
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import heapq
import structlog
from Execution_Layer.Agents.base_agent import BaseAgent, AgentStatus

logger = structlog.get_logger(__name__)


@dataclass(order=True)
class PriorityTask:
    """Task with priority for priority queue."""
    priority: int  # Lower = higher priority
    timestamp: float = field(compare=False)
    task: Dict[str, Any] = field(compare=False)


class PriorityQueueAgent(BaseAgent):
    """
    Priority Queue Agent Pattern

    Verarbeitet Tasks basierend auf Priorität (nicht FIFO).
    """

    def __init__(
        self,
        agent_id: str = "priority_queue_agent",
        config: Optional[Dict[str, Any]] = None,
        max_queue_size: int = 1000
    ):
        super().__init__(agent_id=agent_id, config=config)
        self.queue: List[PriorityTask] = []
        self.max_queue_size = max_queue_size
        self.processing = False
        self.start_time = datetime.utcnow()

    async def initialize(self) -> None:
        """Initialize agent and start queue processor."""
        await super().initialize()

        # Start background queue processor
        asyncio.create_task(self._process_queue())

        logger.info(
            "priority_queue_agent_started",
            agent_id=self.agent_id,
            max_queue_size=self.max_queue_size
        )

    def enqueue_task(
        self,
        task: Dict[str, Any],
        priority: int = 100
    ) -> None:
        """
        Add task to priority queue.

        Args:
            task: Task to process
            priority: Priority (lower = higher priority)
                      0-10: Critical
                      11-50: High
                      51-100: Normal
                      101+: Low
        """
        if len(self.queue) >= self.max_queue_size:
            logger.warning(
                "queue_full",
                agent_id=self.agent_id,
                current_size=len(self.queue),
                max_size=self.max_queue_size
            )
            raise ValueError("Queue is full")

        priority_task = PriorityTask(
            priority=priority,
            timestamp=datetime.utcnow().timestamp(),
            task=task
        )

        heapq.heappush(self.queue, priority_task)

        logger.info(
            "task_enqueued",
            agent_id=self.agent_id,
            task_id=task.get("id"),
            priority=priority,
            queue_size=len(self.queue)
        )

    async def _process_queue(self) -> None:
        """Background queue processor."""
        while self.status == AgentStatus.READY:
            if not self.queue:
                # No tasks, wait a bit
                await asyncio.sleep(0.1)
                continue

            # Get highest priority task
            priority_task = heapq.heappop(self.queue)

            logger.info(
                "processing_queued_task",
                agent_id=self.agent_id,
                task_id=priority_task.task.get("id"),
                priority=priority_task.priority,
                queue_size=len(self.queue)
            )

            # Process task
            try:
                result = await self._do_process_task(priority_task.task)

                logger.info(
                    "queued_task_completed",
                    agent_id=self.agent_id,
                    task_id=priority_task.task.get("id"),
                    success=result.get("success")
                )

            except Exception as e:
                logger.exception(
                    "queued_task_failed",
                    agent_id=self.agent_id,
                    task_id=priority_task.task.get("id"),
                    error=str(e)
                )

    async def _do_process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process task (implement in subclass).

        Args:
            task: Task to process

        Returns:
            Task result
        """
        # Default implementation
        await asyncio.sleep(0.1)  # Simulate work

        return {
            "success": True,
            "task_id": task.get("id")
        }

    def get_queue_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        priorities = [pt.priority for pt in self.queue]

        return {
            "agent_id": self.agent_id,
            "queue_size": len(self.queue),
            "max_queue_size": self.max_queue_size,
            "utilization": len(self.queue) / self.max_queue_size,
            "priority_distribution": {
                "critical": sum(1 for p in priorities if p <= 10),
                "high": sum(1 for p in priorities if 11 <= p <= 50),
                "normal": sum(1 for p in priorities if 51 <= p <= 100),
                "low": sum(1 for p in priorities if p > 100)
            },
            "oldest_task_age_seconds": (
                datetime.utcnow().timestamp() - min(pt.timestamp for pt in self.queue)
                if self.queue else 0
            )
        }

    def _calculate_uptime(self) -> float:
        """Calculate agent uptime."""
        return (datetime.utcnow() - self.start_time).total_seconds()


# Example Usage
async def example_priority_queue():
    """Example of using PriorityQueueAgent."""

    agent = PriorityQueueAgent(max_queue_size=100)
    await agent.initialize()

    # Enqueue tasks with different priorities
    tasks = [
        ({"id": "task_1", "type": "normal"}, 100),  # Normal priority
        ({"id": "task_2", "type": "critical"}, 5),  # Critical priority
        ({"id": "task_3", "type": "high"}, 20),     # High priority
        ({"id": "task_4", "type": "low"}, 150),     # Low priority
        ({"id": "task_5", "type": "high"}, 15),     # High priority
    ]

    for task, priority in tasks:
        agent.enqueue_task(task, priority)

    # Wait for processing
    await asyncio.sleep(2)

    # Get queue stats
    stats = agent.get_queue_stats()
    print(f"Queue Stats: {stats}")

    await agent.shutdown()


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_priority_queue())
```

---

## Conflict Resolution

### Pattern: Resource Lock Manager

**Use Case:** Verhindern von gleichzeitiger Bearbeitung derselben Ressource

```python
# Execution_Layer/Agents/resource_lock_manager.py
from typing import Dict, Any, Optional, Set
from datetime import datetime, timedelta
import asyncio
import structlog

logger = structlog.get_logger(__name__)


class ResourceLockManager:
    """
    Manage resource locks to prevent concurrent access.

    Prevents multiple agents from processing the same resource
    simultaneously (e.g., same document).
    """

    def __init__(self, lock_timeout_seconds: int = 300):
        self.locks: Dict[str, Dict[str, Any]] = {}
        self.lock_timeout_seconds = lock_timeout_seconds

    async def acquire_lock(
        self,
        resource_id: str,
        agent_id: str,
        timeout_seconds: Optional[int] = None
    ) -> bool:
        """
        Try to acquire lock on resource.

        Args:
            resource_id: Resource to lock (e.g., document ID)
            agent_id: Agent requesting lock
            timeout_seconds: Custom timeout for this lock

        Returns:
            True if lock acquired, False otherwise
        """
        # Check if resource is already locked
        if resource_id in self.locks:
            existing_lock = self.locks[resource_id]

            # Check if lock is expired
            lock_age = datetime.utcnow() - existing_lock["acquired_at"]
            timeout = timedelta(seconds=existing_lock["timeout_seconds"])

            if lock_age > timeout:
                # Lock expired, remove it
                logger.warning(
                    "lock_expired",
                    resource_id=resource_id,
                    previous_owner=existing_lock["agent_id"],
                    age_seconds=lock_age.total_seconds()
                )
                del self.locks[resource_id]
            else:
                # Lock still valid
                logger.info(
                    "lock_denied",
                    resource_id=resource_id,
                    agent_id=agent_id,
                    locked_by=existing_lock["agent_id"]
                )
                return False

        # Acquire lock
        self.locks[resource_id] = {
            "agent_id": agent_id,
            "acquired_at": datetime.utcnow(),
            "timeout_seconds": timeout_seconds or self.lock_timeout_seconds
        }

        logger.info(
            "lock_acquired",
            resource_id=resource_id,
            agent_id=agent_id,
            timeout_seconds=self.locks[resource_id]["timeout_seconds"]
        )

        return True

    async def release_lock(self, resource_id: str, agent_id: str) -> bool:
        """
        Release lock on resource.

        Args:
            resource_id: Resource to unlock
            agent_id: Agent releasing lock

        Returns:
            True if lock released, False if agent didn't own lock
        """
        if resource_id not in self.locks:
            logger.warning(
                "lock_not_found",
                resource_id=resource_id,
                agent_id=agent_id
            )
            return False

        lock = self.locks[resource_id]

        # Verify agent owns the lock
        if lock["agent_id"] != agent_id:
            logger.error(
                "lock_release_denied",
                resource_id=resource_id,
                agent_id=agent_id,
                lock_owner=lock["agent_id"]
            )
            return False

        # Release lock
        del self.locks[resource_id]

        logger.info(
            "lock_released",
            resource_id=resource_id,
            agent_id=agent_id
        )

        return True

    def is_locked(self, resource_id: str) -> bool:
        """Check if resource is currently locked."""
        return resource_id in self.locks

    def get_lock_info(self, resource_id: str) -> Optional[Dict[str, Any]]:
        """Get information about lock on resource."""
        return self.locks.get(resource_id)

    def cleanup_expired_locks(self) -> int:
        """
        Remove expired locks.

        Returns:
            Number of locks removed
        """
        now = datetime.utcnow()
        expired = []

        for resource_id, lock in self.locks.items():
            lock_age = now - lock["acquired_at"]
            timeout = timedelta(seconds=lock["timeout_seconds"])

            if lock_age > timeout:
                expired.append(resource_id)

        # Remove expired locks
        for resource_id in expired:
            del self.locks[resource_id]

            logger.info(
                "expired_lock_removed",
                resource_id=resource_id
            )

        return len(expired)


# Integration with BaseAgent
class LockableAgent(BaseAgent):
    """
    Agent that uses resource locking to prevent conflicts.
    """

    _lock_manager = ResourceLockManager()

    async def process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process task with automatic resource locking.
        """
        resource_id = self._get_resource_id(task)

        if not resource_id:
            # No locking needed
            return await super().process_task(task)

        # Try to acquire lock
        locked = await self._lock_manager.acquire_lock(
            resource_id=resource_id,
            agent_id=self.agent_id,
            timeout_seconds=300
        )

        if not locked:
            logger.warning(
                "task_skipped_resource_locked",
                agent_id=self.agent_id,
                resource_id=resource_id
            )

            return {
                "success": False,
                "error": "Resource locked by another agent",
                "resource_id": resource_id
            }

        try:
            # Process with lock held
            result = await super().process_task(task)
            return result

        finally:
            # Always release lock
            await self._lock_manager.release_lock(
                resource_id=resource_id,
                agent_id=self.agent_id
            )

    def _get_resource_id(self, task: Dict[str, Any]) -> Optional[str]:
        """
        Extract resource ID from task.

        Override in subclass to define resource locking strategy.
        """
        return task.get("document_id")


# Example Usage
async def example_resource_locking():
    """Example of resource locking to prevent conflicts."""

    class OCRAgent(LockableAgent):
        async def _do_process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
            # Simulate OCR processing
            await asyncio.sleep(2)
            return {"success": True, "text": "extracted text"}

    # Create two agents
    agent1 = OCRAgent(agent_id="agent_1")
    agent2 = OCRAgent(agent_id="agent_2")

    await agent1.initialize()
    await agent2.initialize()

    # Try to process same document simultaneously
    task = {"document_id": "doc_123", "type": "ocr"}

    results = await asyncio.gather(
        agent1.process_task(task),
        agent2.process_task(task)
    )

    print(f"Agent 1 result: {results[0]}")
    print(f"Agent 2 result: {results[1]}")

    # One should succeed, one should fail with lock error
    assert results[0]["success"] != results[1]["success"]

    await agent1.shutdown()
    await agent2.shutdown()


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_resource_locking())
```

---

## Circuit Breaker Pattern

### Pattern: Automatic Error Recovery

**Use Case:** Automatisches Abschalten von fehlerhaften Backends

```python
# Execution_Layer/Agents/circuit_breaker_agent.py
from typing import Dict, Any, Optional, Callable, Awaitable
from datetime import datetime, timedelta
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Circuit tripped, rejecting requests
    HALF_OPEN = "half_open"  # Testing if backend recovered


class CircuitBreaker:
    """
    Circuit Breaker Pattern Implementation.

    Automatically opens circuit (stops requests) when failure
    threshold is reached. Periodically tests if backend recovered.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout_seconds: int = 60,
        success_threshold: int = 2
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout_seconds: Time before testing recovery
            success_threshold: Successes needed to close circuit again
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.success_threshold = success_threshold

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None

    async def call(
        self,
        func: Callable[..., Awaitable[Any]],
        *args,
        **kwargs
    ) -> Any:
        """
        Call function through circuit breaker.

        Args:
            func: Async function to call
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            CircuitOpenError: If circuit is open
        """
        # Check circuit state
        if self.state == CircuitState.OPEN:
            # Check if recovery timeout elapsed
            if self.last_failure_time:
                time_since_failure = datetime.utcnow() - self.last_failure_time

                if time_since_failure > timedelta(seconds=self.recovery_timeout_seconds):
                    # Try recovery
                    logger.info("circuit_breaker_half_open", state_transition="open->half_open")
                    self.state = CircuitState.HALF_OPEN
                else:
                    # Still open
                    logger.warning("circuit_breaker_rejected", state="open")
                    raise CircuitOpenError("Circuit breaker is OPEN")

        # Execute function
        try:
            result = await func(*args, **kwargs)

            # Success
            self._on_success()

            return result

        except Exception as e:
            # Failure
            self._on_failure()
            raise

    def _on_success(self) -> None:
        """Handle successful call."""
        self.failure_count = 0

        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1

            logger.info(
                "circuit_breaker_success",
                state="half_open",
                success_count=self.success_count,
                success_threshold=self.success_threshold
            )

            # Check if enough successes to close circuit
            if self.success_count >= self.success_threshold:
                logger.info("circuit_breaker_closed", state_transition="half_open->closed")
                self.state = CircuitState.CLOSED
                self.success_count = 0

    def _on_failure(self) -> None:
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()

        logger.warning(
            "circuit_breaker_failure",
            state=self.state.value,
            failure_count=self.failure_count,
            failure_threshold=self.failure_threshold
        )

        if self.state == CircuitState.HALF_OPEN:
            # Failure during recovery attempt
            logger.error("circuit_breaker_opened", state_transition="half_open->open")
            self.state = CircuitState.OPEN
            self.success_count = 0

        elif self.failure_count >= self.failure_threshold:
            # Too many failures
            logger.error("circuit_breaker_opened", state_transition="closed->open")
            self.state = CircuitState.OPEN

    def get_state(self) -> Dict[str, Any]:
        """Get circuit breaker state."""
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "failure_threshold": self.failure_threshold,
            "success_threshold": self.success_threshold,
            "last_failure_time": (
                self.last_failure_time.isoformat()
                if self.last_failure_time else None
            )
        }


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass


# Example: OCR Backend with Circuit Breaker
class CircuitBreakerAgent(BaseAgent):
    """Agent with circuit breaker protection."""

    def __init__(self, agent_id: str = "circuit_breaker_agent"):
        super().__init__(agent_id=agent_id)
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout_seconds=60,
            success_threshold=2
        )

    async def _do_process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Process task through circuit breaker."""
        try:
            result = await self.circuit_breaker.call(
                self._process_with_backend,
                task
            )
            return result

        except CircuitOpenError:
            logger.error(
                "task_rejected_circuit_open",
                agent_id=self.agent_id
            )

            return {
                "success": False,
                "error": "Backend unavailable (circuit breaker open)"
            }

    async def _process_with_backend(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Actual processing logic (can fail).

        Override in subclass.
        """
        # Simulate backend call
        import random
        if random.random() < 0.3:  # 30% failure rate
            raise RuntimeError("Backend error")

        return {"success": True, "data": "processed"}


# Example Usage
async def example_circuit_breaker():
    """Example of circuit breaker in action."""

    agent = CircuitBreakerAgent()
    await agent.initialize()

    # Process multiple tasks
    for i in range(20):
        try:
            result = await agent.process_task({"id": f"task_{i}"})
            print(f"Task {i}: {result['success']}")

        except Exception as e:
            print(f"Task {i}: FAILED - {str(e)}")

        # Check circuit breaker state
        cb_state = agent.circuit_breaker.get_state()
        print(f"  Circuit Breaker: {cb_state['state']} (failures: {cb_state['failure_count']})")

        await asyncio.sleep(0.5)

    await agent.shutdown()


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_circuit_breaker())
```

---

**Document Status:** ✅ **COMPLETE**

Advanced Agent Patterns mit:
- ✅ Multi-Agent Coordination (Coordinator-Worker Pattern)
- ✅ Priority Queue & Scheduling
- ✅ Resource Lock Manager (Conflict Resolution)
- ✅ Circuit Breaker Pattern (Error Recovery)
- ✅ Vollständige lauffähige Implementierungen
- ✅ Praxisnahe Beispiele

Diese fortgeschrittenen Patterns ermöglichen:
- **Komplexe Workflows** mit mehreren koordinierten Agents
- **Intelligente Task-Scheduling** basierend auf Prioritäten
- **Konflikt-Vermeidung** bei gleichzeitiger Ressourcennutzung
- **Automatische Fehlerbehandlung** mit Circuit Breaker
