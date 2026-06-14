"""
Base Agent Classes for Multi-Agent System.

Provides abstract base classes and common functionality for all agents.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog
from app.core.safe_errors import safe_error_log

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


# Prometheus metrics removed for POC - no monitoring dependencies needed


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
        self.logger = logger

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

        # Metrics tracking removed for POC

        self.logger.info("agent_task_started", task_id=task_id, input_size=len(str(input_data)))

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
                        self.logger.warning("agent_task_retry", task_id=task_id, attempt=attempt + 1, max_retries=self.max_retries, delay_seconds=delay, **safe_error_log(e))
                        # Metrics removed for POC
                        time.sleep(delay)
                    else:
                        # Final retry failed
                        raise

        except Exception as e:
            error = e
            status = AgentStatus.FAILED

            self.logger.error("agent_task_failed", task_id=task_id, **safe_error_log(e), exc_info=True)

            # Error metrics removed for POC

            # Re-raise for upstream handling
            raise

        finally:
            # Record metrics
            duration = time.time() - start_time

            # Metrics removed for POC

            self.logger.info("agent_task_completed", task_id=task_id, status=status.value, duration_seconds=round(duration, 2), has_error=error is not None)

        # Return result with metadata
        return {
            "result": result,
            "metadata": {
                "agent": self.name,
                "category": self.category.value,
                "status": status.value,
                "duration_seconds": duration,
                "timestamp": datetime.now(timezone.utc).isoformat(),
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


@dataclass
class OCRResult:
    """
    Standardisiertes OCR-Ergebnis für alle Backends.

    Alle OCR-Agents sollten dieses Format zurückgeben für Konsistenz.
    """

    success: bool
    text: str
    confidence: float  # 0.0 - 1.0, kalibriert
    backend: str
    processing_time_ms: int = 0

    # Optional Metadata
    word_count: int = 0
    char_count: int = 0
    page_count: int = 1
    language: str = "de"

    # Layout Information (optional)
    bounding_boxes: Optional[List[Dict[str, Any]]] = None
    layout: Optional[Dict[str, Any]] = None
    pages: Optional[List[Dict[str, Any]]] = None

    # Quality Metrics (optional)
    has_umlauts: bool = False
    german_validation_score: float = 0.0

    # Error Information (wenn success=False)
    error: Optional[str] = None
    error_code: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary."""
        result = {
            "success": self.success,
            "text": self.text,
            "confidence": round(self.confidence, 4),
            "backend": self.backend,
            "processing_time_ms": self.processing_time_ms,
            "metadata": {
                "word_count": self.word_count,
                "char_count": self.char_count,
                "page_count": self.page_count,
                "language": self.language,
                "has_umlauts": self.has_umlauts,
                "german_validation_score": round(self.german_validation_score, 4),
            },
        }

        # Optional Fields
        if self.bounding_boxes:
            result["bounding_boxes"] = self.bounding_boxes
        if self.layout:
            result["layout"] = self.layout
        if self.pages:
            result["pages"] = self.pages

        # Error Fields
        if not self.success:
            result["error"] = self.error
            result["error_code"] = self.error_code

        return result

    @classmethod
    def from_legacy(
        cls,
        legacy_result: Dict[str, Any],
        backend: str,
        processing_time_ms: int = 0
    ) -> "OCRResult":
        """
        Konvertiere Legacy-Result-Format zu standardisiertem OCRResult.

        Args:
            legacy_result: Altes Result-Dictionary
            backend: Backend-Name
            processing_time_ms: Verarbeitungszeit

        Returns:
            Standardisiertes OCRResult
        """
        text = legacy_result.get("text", "")
        confidence = legacy_result.get("confidence", 0.0)
        success = legacy_result.get("success", bool(text))

        return cls(
            success=success,
            text=text,
            confidence=confidence,
            backend=backend,
            processing_time_ms=processing_time_ms,
            word_count=len(text.split()) if text else 0,
            char_count=len(text) if text else 0,
            page_count=legacy_result.get("page_count", 1),
            language=legacy_result.get("language", "de"),
            bounding_boxes=legacy_result.get("bounding_boxes"),
            layout=legacy_result.get("layout"),
            pages=legacy_result.get("pages"),
            has_umlauts=legacy_result.get("has_umlauts", False),
            german_validation_score=legacy_result.get("german_validation_score", 0.0),
            error=legacy_result.get("error"),
            error_code=legacy_result.get("error_code"),
        )


class OCRAgent(BaseAgent):
    """Base class for OCR processing agents."""

    def __init__(self, name: str, gpu_required: bool = True, vram_gb: int = 0):
        super().__init__(name=name, category=AgentCategory.OCR)
        self.gpu_required = gpu_required
        self.vram_gb = vram_gb
        self._is_initialized = False

    async def cleanup(self):
        """Clean up resources. Override in subclasses for specific cleanup."""
        self._is_initialized = False
        self.logger.info("agent_cleanup_complete", agent=self.name)

    def get_status(self) -> Dict[str, Any]:
        """Get agent status. Override in subclasses for specific status."""
        return {
            "name": self.name,
            "category": self.category.value,
            "gpu_required": self.gpu_required,
            "vram_gb": self.vram_gb,
            "initialized": self._is_initialized,
        }

    def create_success_result(
        self,
        text: str,
        confidence: float,
        processing_time_ms: int = 0,
        **kwargs: object
    ) -> OCRResult:
        """
        Erstelle standardisiertes Erfolgs-Result.

        Args:
            text: Extrahierter Text
            confidence: Confidence Score (0-1)
            processing_time_ms: Verarbeitungszeit
            **kwargs: Zusätzliche Metadata

        Returns:
            Standardisiertes OCRResult
        """
        return OCRResult(
            success=True,
            text=text,
            confidence=confidence,
            backend=self.name,
            processing_time_ms=processing_time_ms,
            word_count=len(text.split()) if text else 0,
            char_count=len(text),
            page_count=kwargs.get("page_count", 1),
            language=kwargs.get("language", "de"),
            bounding_boxes=kwargs.get("bounding_boxes"),
            layout=kwargs.get("layout"),
            pages=kwargs.get("pages"),
            has_umlauts=kwargs.get("has_umlauts", False),
            german_validation_score=kwargs.get("german_validation_score", 0.0),
        )

    def create_error_result(
        self,
        error: str,
        error_code: str = "PROCESSING_ERROR",
        processing_time_ms: int = 0
    ) -> OCRResult:
        """
        Erstelle standardisiertes Fehler-Result.

        Args:
            error: Fehlermeldung
            error_code: Fehlercode
            processing_time_ms: Verarbeitungszeit

        Returns:
            Standardisiertes OCRResult mit success=False
        """
        return OCRResult(
            success=False,
            text="",
            confidence=0.0,
            backend=self.name,
            processing_time_ms=processing_time_ms,
            error=error,
            error_code=error_code,
        )

    def normalize_legacy_result(
        self,
        legacy_result: Dict[str, Any],
        processing_time_ms: int = 0
    ) -> OCRResult:
        """
        Konvertiere Legacy-Result zu standardisiertem Format.

        Verwende diese Methode um alte Return-Strukturen zu normalisieren.

        Args:
            legacy_result: Altes Result-Dictionary
            processing_time_ms: Verarbeitungszeit

        Returns:
            Standardisiertes OCRResult
        """
        return OCRResult.from_legacy(
            legacy_result,
            backend=self.name,
            processing_time_ms=processing_time_ms
        )


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
