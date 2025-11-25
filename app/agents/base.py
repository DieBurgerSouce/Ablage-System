"""
Base Agent Classes for Multi-Agent System.

Provides abstract base classes and common functionality for all agents.
"""

import time
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

import structlog
from prometheus_client import Counter, Gauge, Histogram

logger = structlog.get_logger(__name__)


class AgentStatus(str, Enum):
    """Agent execution status."""

    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"


class AgentCategory(str, Enum):
    """Agent category classification."""

    OCR = "ocr"
    PREPROCESSING = "preprocessing"
    POSTPROCESSING = "postprocessing"
    ORCHESTRATION = "orchestration"
    INTELLIGENCE = "intelligence"
    MONITORING = "monitoring"
    INTEGRATION = "integration"


# Prometheus Metrics
agent_tasks_total = Counter(
    "agent_tasks_total",
    "Total tasks processed by agent",
    ["agent_name", "category", "status"],
)

agent_task_duration = Histogram(
    "agent_task_duration_seconds",
    "Agent task processing duration",
    ["agent_name", "category"],
)

agent_active_tasks = Gauge(
    "agent_active_tasks",
    "Number of currently active tasks",
    ["agent_name", "category"],
)

agent_errors_total = Counter(
    "agent_errors_total",
    "Total errors encountered by agent",
    ["agent_name", "category", "error_type"],
)


class BaseAgent(ABC):
    """
    Abstract base class for all agents.

    Provides common functionality:
    - Logging and metrics
    - Error handling
    - State management
    - Retry logic
    """

    def __init__(
        self,
        name: str,
        category: AgentCategory,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        """
        Initialize base agent.

        Args:
            name: Agent name (used for logging and metrics)
            category: Agent category
            max_retries: Maximum number of retry attempts
            retry_delay: Initial retry delay in seconds (exponential backoff)
        """
        self.name = name
        self.category = category
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.logger = logger.bind(agent=name, category=category.value)

    @abstractmethod
    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process input data (to be implemented by subclasses).

        Args:
            input_data: Input data dictionary

        Returns:
            Result dictionary

        Raises:
            AgentProcessingError: If processing fails
        """
        pass

    async def execute(
        self, input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute agent task with monitoring and error handling.

        Args:
            input_data: Input data
            context: Optional execution context (task_id, user_id, etc.)

        Returns:
            Result dictionary with metadata
        """
        context = context or {}
        task_id = context.get("task_id", "unknown")
        start_time = time.time()

        # Increment active tasks gauge
        agent_active_tasks.labels(
            agent_name=self.name, category=self.category.value
        ).inc()

        self.logger.info(
            "agent_task_started",
            task_id=task_id,
            input_size=len(str(input_data)),
        )

        result = None
        status = AgentStatus.FAILED
        error = None

        try:
            # Attempt processing with retries
            for attempt in range(self.max_retries):
                try:
                    result = await self.process(input_data)
                    status = AgentStatus.SUCCESS
                    break
                except Exception as e:
                    error = e
                    if attempt < self.max_retries - 1:
                        # Retry with exponential backoff
                        delay = self.retry_delay * (2**attempt)
                        self.logger.warning(
                            "agent_task_retry",
                            task_id=task_id,
                            attempt=attempt + 1,
                            max_retries=self.max_retries,
                            retry_delay=delay,
                            error=str(e),
                        )
                        agent_tasks_total.labels(
                            agent_name=self.name,
                            category=self.category.value,
                            status=AgentStatus.RETRYING.value,
                        ).inc()
                        time.sleep(delay)
                    else:
                        # Final retry failed
                        raise

        except Exception as e:
            error = e
            status = AgentStatus.FAILED
            error_type = type(e).__name__

            self.logger.error(
                "agent_task_failed",
                task_id=task_id,
                error=str(e),
                error_type=error_type,
                exc_info=True,
            )

            agent_errors_total.labels(
                agent_name=self.name,
                category=self.category.value,
                error_type=error_type,
            ).inc()

            # Re-raise for upstream handling
            raise

        finally:
            # Record metrics
            duration = time.time() - start_time

            agent_task_duration.labels(
                agent_name=self.name, category=self.category.value
            ).observe(duration)

            agent_tasks_total.labels(
                agent_name=self.name,
                category=self.category.value,
                status=status.value,
            ).inc()

            agent_active_tasks.labels(
                agent_name=self.name, category=self.category.value
            ).dec()

            self.logger.info(
                "agent_task_completed",
                task_id=task_id,
                status=status.value,
                duration_seconds=duration,
                has_error=error is not None,
            )

        # Return result with metadata
        return {
            "result": result,
            "metadata": {
                "agent": self.name,
                "category": self.category.value,
                "status": status.value,
                "duration_seconds": duration,
                "timestamp": datetime.utcnow().isoformat(),
                "task_id": task_id,
            },
        }

    def validate_input(self, input_data: Dict[str, Any], required_keys: list) -> None:
        """
        Validate that input contains required keys.

        Args:
            input_data: Input data to validate
            required_keys: List of required key names

        Raises:
            ValueError: If required keys are missing
        """
        missing_keys = [key for key in required_keys if key not in input_data]
        if missing_keys:
            raise ValueError(f"Missing required input keys: {missing_keys}")


class OCRAgent(BaseAgent):
    """Base class for OCR processing agents."""

    def __init__(self, name: str, gpu_required: bool = True, vram_gb: int = 0):
        super().__init__(name=name, category=AgentCategory.OCR)
        self.gpu_required = gpu_required
        self.vram_gb = vram_gb


class PreprocessingAgent(BaseAgent):
    """Base class for preprocessing agents."""

    def __init__(self, name: str):
        super().__init__(name=name, category=AgentCategory.PREPROCESSING)


class PostprocessingAgent(BaseAgent):
    """Base class for postprocessing agents."""

    def __init__(self, name: str):
        super().__init__(name=name, category=AgentCategory.POSTPROCESSING)


class OrchestrationAgent(BaseAgent):
    """Base class for orchestration agents."""

    def __init__(self, name: str):
        super().__init__(name=name, category=AgentCategory.ORCHESTRATION)


class IntelligenceAgent(BaseAgent):
    """Base class for intelligence agents."""

    def __init__(self, name: str):
        super().__init__(name=name, category=AgentCategory.INTELLIGENCE)


class MonitoringAgent(BaseAgent):
    """Base class for monitoring agents."""

    def __init__(self, name: str):
        super().__init__(name=name, category=AgentCategory.MONITORING)


class IntegrationAgent(BaseAgent):
    """Base class for integration agents."""

    def __init__(self, name: str):
        super().__init__(name=name, category=AgentCategory.INTEGRATION)


# Exception Classes
class AgentProcessingError(Exception):
    """Base exception for agent processing errors."""

    pass


class AgentInputError(AgentProcessingError):
    """Invalid input data."""

    pass


class AgentResourceError(AgentProcessingError):
    """Insufficient resources (GPU, memory, etc.)."""

    pass


class AgentTimeoutError(AgentProcessingError):
    """Processing timeout exceeded."""

    pass
