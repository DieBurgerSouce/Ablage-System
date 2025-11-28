"""
Document Processing Orchestrator.

Master orchestrator that coordinates the entire document processing workflow:
1. Classification → 2. Pre-Processing → 3. OCR → 4. Post-Processing → 5. QA → 6. Storage

Integrated with enterprise-grade error recovery:
- Circuit breaker pattern for external services
- Retry strategy with exponential backoff
- GPU OOM recovery with automatic fallback
- Partial results handling for graceful degradation

Feinpoliert und durchdacht - Enterprise-grade document processing pipeline.
"""

import asyncio
import json
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

import structlog

from app.agents.base import OrchestrationAgent
from app.core.redis_state import get_redis, RedisStateManager

# Import error recovery components
from app.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerManager,
    CircuitConfig,
    CircuitOpenError,
    CircuitState,
    get_circuit_breaker_manager,
)
from app.core.retry_strategy import (
    RetryConfig,
    RetryContext,
    RetryExhaustedError,
    RetryStrategy,
    WorkflowPhase as RetryPhase,
    get_retry_strategy,
)
from app.core.gpu_recovery import (
    GPURecoveryError,
    GPURecoveryManager,
    gpu_memory_guard,
    get_gpu_recovery_manager,
)
from app.core.partial_results import (
    PartialResult,
    PartialResultHandler,
    PartialResultStatus,
    get_partial_result_handler,
)

logger = structlog.get_logger(__name__)


class WorkflowPhase(str, Enum):
    """Document processing workflow phases."""

    UPLOADED = "uploaded"
    CLASSIFYING = "classifying"
    PREPROCESSING = "preprocessing"
    OCR_PROCESSING = "ocr_processing"
    POSTPROCESSING = "postprocessing"
    QA_CHECK = "qa_check"
    STORING = "storing"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentProcessingOrchestrator(OrchestrationAgent):
    """
    Master orchestrator for document processing workflows.

    Coordinates all agents in the processing pipeline and manages
    workflow state, error handling, and progress tracking.

    Integrates enterprise-grade error recovery:
    - Circuit breaker for external services (Redis, PostgreSQL, MinIO)
    - Retry strategy with exponential backoff for transient failures
    - GPU OOM recovery with automatic CPU fallback
    - Partial results handling for graceful degradation
    """

    def __init__(self):
        super().__init__(name="document_processing_orchestrator")

        # Lazy-loaded sub-agents
        self._classification_agent = None
        self._preprocessing_agents = None
        self._ocr_agents = None
        self._postprocessing_agents = None
        self._qa_agent = None
        self._page_segmentation_agent = None

        # Error recovery components
        self._circuit_breaker_manager: Optional[CircuitBreakerManager] = None
        self._retry_strategy: Optional[RetryStrategy] = None
        self._gpu_recovery_manager: Optional[GPURecoveryManager] = None
        self._partial_result_handler: Optional[PartialResultHandler] = None

        # Initialize error recovery
        self._init_error_recovery()

    def _init_error_recovery(self) -> None:
        """Initialize error recovery components."""
        try:
            # Circuit breaker manager for external services
            self._circuit_breaker_manager = get_circuit_breaker_manager()

            # Register circuits for external services
            self._circuit_breaker_manager.register_circuit(
                "redis",
                CircuitConfig(
                    failure_threshold=5,
                    reset_timeout_seconds=30,
                    half_open_max_calls=3,
                )
            )
            self._circuit_breaker_manager.register_circuit(
                "postgresql",
                CircuitConfig(
                    failure_threshold=3,
                    reset_timeout_seconds=60,
                    half_open_max_calls=2,
                )
            )
            self._circuit_breaker_manager.register_circuit(
                "minio",
                CircuitConfig(
                    failure_threshold=5,
                    reset_timeout_seconds=45,
                    half_open_max_calls=3,
                )
            )

            # Retry strategy for transient failures
            self._retry_strategy = get_retry_strategy()

            # GPU recovery manager
            self._gpu_recovery_manager = get_gpu_recovery_manager()

            # Partial result handler
            self._partial_result_handler = get_partial_result_handler()

            self.logger.info(
                "error_recovery_initialized",
                circuit_breakers=["redis", "postgresql", "minio"],
                gpu_recovery_enabled=self._gpu_recovery_manager is not None,
            )

        except Exception as e:
            self.logger.warning(
                "error_recovery_init_failed",
                error=str(e),
            )
            # Continue without error recovery - graceful degradation

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Orchestrate complete document processing workflow.

        Input:
            document_id: str - Unique document identifier
            file_path: str - Path to uploaded file
            user_id: str - User who uploaded document
            priority: int - Processing priority (0=normal, 1=high, 2=critical)
            options: dict - Processing options

        Returns:
            document_id: str
            status: str
            phases_completed: list
            result: dict - Final processing result
            metadata: dict - Workflow metadata
        """
        self.validate_input(input_data, ["document_id", "file_path"])

        document_id = input_data["document_id"]
        file_path = input_data["file_path"]
        priority = input_data.get("priority", 0)
        options = input_data.get("options", {})

        self.logger.info(
            "workflow_started",
            document_id=document_id,
            file_path=file_path,
            priority=priority,
        )

        # Initialize workflow state
        workflow_state = await self._init_workflow_state(document_id, input_data)

        try:
            # Phase 1: Classification
            classification = await self._execute_phase(
                WorkflowPhase.CLASSIFYING,
                self._classify_document,
                workflow_state,
                {"file_path": file_path},
            )

            # Phase 2: Pre-Processing (parallel)
            preprocessing = await self._execute_phase(
                WorkflowPhase.PREPROCESSING,
                self._preprocess_document,
                workflow_state,
                {"file_path": file_path, "classification": classification},
            )

            # Phase 3: OCR Backend Selection & Processing
            ocr_backend = await self._select_ocr_backend(
                classification, preprocessing, options
            )

            ocr_result = await self._execute_phase(
                WorkflowPhase.OCR_PROCESSING,
                self._run_ocr,
                workflow_state,
                {
                    "file_path": preprocessing.get("enhanced_image_path", file_path),
                    "backend": ocr_backend,
                    "classification": classification,
                },
            )

            # Phase 4: Post-Processing (parallel)
            postprocessing = await self._execute_phase(
                WorkflowPhase.POSTPROCESSING,
                self._postprocess_result,
                workflow_state,
                {"ocr_result": ocr_result, "classification": classification},
            )

            # Phase 5: Quality Assurance
            qa_result = await self._execute_phase(
                WorkflowPhase.QA_CHECK,
                self._quality_check,
                workflow_state,
                {"postprocessing": postprocessing, "classification": classification},
            )

            # Check if human review needed
            if qa_result.get("needs_review", False):
                await self._trigger_human_review(document_id, qa_result)

            # Phase 6: Final Storage & Indexing
            storage_result = await self._execute_phase(
                WorkflowPhase.STORING,
                self._store_and_index,
                workflow_state,
                {
                    "document_id": document_id,
                    "text": postprocessing["text"],
                    "metadata": {
                        "classification": classification,
                        "entities": postprocessing.get("entities", []),
                        "qa_score": qa_result.get("score", 0.0),
                    },
                },
            )

            # Mark workflow complete
            await self._update_workflow_state(
                workflow_state, WorkflowPhase.COMPLETED, {"status": "success"}
            )

            final_result = {
                "document_id": document_id,
                "status": "completed",
                "phases_completed": list(workflow_state["phases"].keys()),
                "result": {
                    "text": postprocessing["text"],
                    "entities": postprocessing.get("entities", []),
                    "metadata": storage_result["metadata"],
                    "ocr_backend": ocr_backend,
                    "confidence": ocr_result.get("confidence", 0.0),
                    "qa_score": qa_result.get("score", 0.0),
                    "needs_review": qa_result.get("needs_review", False),
                },
                "workflow_metadata": {
                    "total_duration_seconds": (
                        datetime.utcnow() - workflow_state["started_at"]
                    ).total_seconds(),
                    "priority": priority,
                },
            }

            self.logger.info(
                "workflow_completed",
                document_id=document_id,
                duration=final_result["workflow_metadata"]["total_duration_seconds"],
                ocr_backend=ocr_backend,
                qa_score=qa_result.get("score"),
            )

            return final_result

        except Exception as e:
            # Mark workflow failed
            await self._update_workflow_state(
                workflow_state,
                WorkflowPhase.FAILED,
                {"error": str(e), "error_type": type(e).__name__},
            )

            self.logger.error(
                "workflow_failed",
                document_id=document_id,
                error=str(e),
                exc_info=True,
            )

            raise

    async def _init_workflow_state(
        self, document_id: str, input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Initialize workflow state tracking with Redis persistence.

        Args:
            document_id: Unique document identifier
            input_data: Initial workflow input data

        Returns:
            Initialized workflow state dictionary
        """
        started_at = datetime.utcnow()

        state = {
            "document_id": document_id,
            "started_at": started_at,
            "started_at_iso": started_at.isoformat(),
            "current_phase": WorkflowPhase.UPLOADED.value,
            "phases": {},
            "input_data": {
                "file_path": input_data.get("file_path"),
                "user_id": input_data.get("user_id"),
                "priority": input_data.get("priority", 0),
                "options": input_data.get("options", {}),
            },
        }

        # Store initial state in Redis
        try:
            redis = await get_redis()
            await redis.set_workflow_state(
                document_id,
                "initial",
                {
                    "status": "initialized",
                    "started_at": started_at.isoformat(),
                    "current_phase": WorkflowPhase.UPLOADED.value,
                    "input_data": state["input_data"],
                },
            )

            self.logger.info(
                "workflow_state_initialized",
                document_id=document_id,
                phase=WorkflowPhase.UPLOADED.value,
            )

        except Exception as e:
            # Log but don't fail - workflow can continue without Redis persistence
            self.logger.warning(
                "workflow_state_redis_failed",
                document_id=document_id,
                error=str(e),
            )

        return state

    async def _execute_phase(
        self,
        phase: WorkflowPhase,
        phase_func: Callable,
        workflow_state: Dict[str, Any],
        phase_input: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute a workflow phase with comprehensive error recovery.

        Includes:
        - Retry strategy with exponential backoff
        - Partial result handling for graceful degradation
        - Circuit breaker protection for external services
        - Detailed phase state tracking

        Args:
            phase: The workflow phase to execute
            phase_func: Async function to execute
            workflow_state: Current workflow state
            phase_input: Input data for the phase

        Returns:
            Phase result dictionary

        Raises:
            Various exceptions after retry exhaustion
        """
        document_id = workflow_state["document_id"]

        self.logger.info(
            "phase_started",
            document_id=document_id,
            phase=phase.value,
        )

        await self._update_workflow_state(
            workflow_state, phase, {"status": "in_progress"}
        )

        # Map workflow phase to retry phase
        retry_phase_map = {
            WorkflowPhase.CLASSIFYING: RetryPhase.CLASSIFICATION,
            WorkflowPhase.PREPROCESSING: RetryPhase.PREPROCESSING,
            WorkflowPhase.OCR_PROCESSING: RetryPhase.OCR_PROCESSING,
            WorkflowPhase.POSTPROCESSING: RetryPhase.POSTPROCESSING,
            WorkflowPhase.QA_CHECK: RetryPhase.QA_CHECK,
            WorkflowPhase.STORING: RetryPhase.STORAGE,
        }
        retry_phase = retry_phase_map.get(phase, RetryPhase.CLASSIFICATION)

        # Get retry config for this phase
        retry_config = self._retry_strategy.get_config(retry_phase) if self._retry_strategy else None

        attempt = 0
        last_error: Optional[Exception] = None
        partial_result: Optional[PartialResult] = None

        while True:
            attempt += 1

            try:
                # Execute the phase function
                result = await phase_func(phase_input)

                # Update state on success
                await self._update_workflow_state(
                    workflow_state, phase, {"status": "completed", "result": result}
                )

                self.logger.info(
                    "phase_completed",
                    document_id=document_id,
                    phase=phase.value,
                    attempts=attempt,
                )

                return result

            except CircuitOpenError as e:
                # Circuit is open - don't retry, fail immediately
                self.logger.error(
                    "phase_circuit_open",
                    document_id=document_id,
                    phase=phase.value,
                    circuit=str(e),
                )
                await self._update_workflow_state(
                    workflow_state, phase, {
                        "status": "failed",
                        "error": str(e),
                        "error_type": "circuit_open",
                    }
                )
                raise

            except GPURecoveryError as e:
                # GPU recovery failed - try partial result or fail
                self.logger.error(
                    "phase_gpu_recovery_failed",
                    document_id=document_id,
                    phase=phase.value,
                    error=str(e),
                )

                # Try to get partial result
                if self._partial_result_handler:
                    partial_result = await self._partial_result_handler.create_partial_result(
                        document_id=document_id,
                        phase=phase.value,
                        error=str(e),
                        partial_data=phase_input,
                    )

                    if partial_result and partial_result.status == PartialResultStatus.USABLE:
                        self.logger.warning(
                            "phase_using_partial_result",
                            document_id=document_id,
                            phase=phase.value,
                        )
                        await self._update_workflow_state(
                            workflow_state, phase, {
                                "status": "partial",
                                "result": partial_result.data,
                                "partial_reason": str(e),
                            }
                        )
                        return partial_result.data

                await self._update_workflow_state(
                    workflow_state, phase, {
                        "status": "failed",
                        "error": str(e),
                        "error_type": "gpu_failure",
                    }
                )
                raise

            except Exception as e:
                last_error = e

                # Check if we should retry
                should_retry = False
                wait_time = 0.0

                if self._retry_strategy and retry_config:
                    context = RetryContext(
                        phase=retry_phase,
                        attempt=attempt,
                        error=e,
                        document_id=document_id,
                    )
                    should_retry, wait_time = self._retry_strategy.should_retry(context)

                if should_retry and attempt < (retry_config.max_retries if retry_config else 3):
                    self.logger.warning(
                        "phase_retry_scheduled",
                        document_id=document_id,
                        phase=phase.value,
                        attempt=attempt,
                        wait_seconds=wait_time,
                        error=str(e),
                    )

                    await self._update_workflow_state(
                        workflow_state, phase, {
                            "status": "retrying",
                            "attempt": attempt,
                            "next_retry_in": wait_time,
                        }
                    )

                    await asyncio.sleep(wait_time)
                    continue

                # No more retries - try partial result or fail
                self.logger.error(
                    "phase_failed",
                    document_id=document_id,
                    phase=phase.value,
                    error=str(e),
                    attempts=attempt,
                )

                # Try to create partial result
                if self._partial_result_handler and phase in [
                    WorkflowPhase.OCR_PROCESSING,
                    WorkflowPhase.POSTPROCESSING,
                ]:
                    partial_result = await self._partial_result_handler.create_partial_result(
                        document_id=document_id,
                        phase=phase.value,
                        error=str(e),
                        partial_data=phase_input,
                    )

                    if partial_result and partial_result.status == PartialResultStatus.USABLE:
                        self.logger.warning(
                            "phase_using_partial_result_after_failure",
                            document_id=document_id,
                            phase=phase.value,
                        )
                        await self._update_workflow_state(
                            workflow_state, phase, {
                                "status": "partial",
                                "result": partial_result.data,
                                "partial_reason": str(e),
                            }
                        )
                        return partial_result.data

                await self._update_workflow_state(
                    workflow_state, phase, {"status": "failed", "error": str(e)}
                )
                raise

    async def _update_workflow_state(
        self, workflow_state: Dict[str, Any], phase: WorkflowPhase, data: Dict[str, Any]
    ) -> None:
        """
        Update workflow state with Redis persistence.

        Args:
            workflow_state: Current workflow state dictionary
            phase: New workflow phase
            data: Phase-specific data to store
        """
        timestamp = datetime.utcnow()

        # Update local state
        workflow_state["current_phase"] = phase
        workflow_state["phases"][phase.value] = {
            "timestamp": timestamp.isoformat(),
            **data,
        }

        # Persist to Redis
        document_id = workflow_state["document_id"]

        try:
            redis = await get_redis()

            # Store phase-specific state
            phase_data = {
                "status": data.get("status", "unknown"),
                "timestamp": timestamp.isoformat(),
                "current_phase": phase.value,
            }

            # Include result if present (but sanitize large data)
            if "result" in data:
                result = data["result"]
                # For large text results, only store metadata
                if isinstance(result, dict) and "text" in result:
                    text_length = len(result.get("text", ""))
                    phase_data["result_preview"] = {
                        "text_length": text_length,
                        "has_entities": "entities" in result,
                        "entity_count": len(result.get("entities", [])),
                        "confidence": result.get("confidence"),
                    }
                else:
                    phase_data["result"] = result

            # Include error if present
            if "error" in data:
                phase_data["error"] = str(data["error"])[:500]  # Limit error length
                phase_data["error_type"] = data.get("error_type", "unknown")

            await redis.set_workflow_state(document_id, phase.value, phase_data)

            # Publish workflow event for real-time monitoring
            await redis.publish_event(
                f"workflow.{phase.value}",
                {
                    "document_id": document_id,
                    "phase": phase.value,
                    "status": data.get("status"),
                },
            )

        except Exception as e:
            # Log but don't fail - workflow can continue without Redis persistence
            self.logger.warning(
                "workflow_state_update_failed",
                document_id=document_id,
                phase=phase.value,
                error=str(e),
            )

    # =========================================================================
    # Phase Implementation Methods
    # =========================================================================

    async def _classify_document(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Phase 1: Classify document type and complexity.

        Uses DocumentClassificationAgent for intelligent classification:
        - Document type (invoice, contract, letter, receipt, form, report)
        - Language detection (German-first)
        - Complexity assessment (tables, handwriting, multi-column)
        - Quality score for preprocessing decisions
        - OCR backend recommendation
        """
        from app.agents.preprocessing.classification_agent import DocumentClassificationAgent

        # Lazy initialization of classification agent
        if self._classification_agent is None:
            self._classification_agent = DocumentClassificationAgent()

        try:
            result = await self._classification_agent.process(input_data)

            self.logger.info(
                "document_classified",
                document_type=result.get("document_type"),
                language=result.get("language"),
                complexity=result.get("complexity"),
                recommended_backend=result.get("recommended_backend"),
                confidence=result.get("confidence"),
            )

            return result

        except Exception as e:
            self.logger.error(
                "classification_failed",
                error=str(e),
                file_path=input_data.get("file_path"),
            )

            # Return conservative defaults on failure
            return {
                "document_type": "other",
                "language": "de",
                "complexity": "medium",
                "quality_score": 0.7,
                "has_tables": False,
                "has_handwriting": False,
                "has_multi_column": False,
                "recommended_backend": "deepseek",
                "confidence": 0.5,
                "metadata": {"classification_error": str(e)},
            }

    async def _preprocess_document(
        self, input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Phase 2: Pre-process document (parallel tasks).

        Performs:
        - Image enhancement (deskew, denoise, contrast)
        - Page segmentation for multi-page documents
        """
        file_path = input_data["file_path"]
        classification = input_data.get("classification", {})
        quality_score = classification.get("quality_score", 0.7)

        # Run preprocessing tasks in parallel
        tasks = [
            self._enhance_image(file_path, quality_score),
            self._segment_pages(file_path, classification),
        ]

        enhanced_result, segmentation = await asyncio.gather(*tasks)

        return {
            "enhanced_image_path": enhanced_result.get("enhanced_image_path", file_path),
            "original_path": file_path,
            "enhancements_applied": enhanced_result.get("enhancements_applied", []),
            "quality_improvement": enhanced_result.get("quality_improvement", 0.0),
            "segmentation": segmentation,
        }

    async def _enhance_image(
        self, file_path: str, quality_score: float = 0.7
    ) -> Dict[str, Any]:
        """
        Enhance image quality using ImageEnhancementAgent.

        Args:
            file_path: Path to the document image
            quality_score: Quality score from classification (0.0-1.0)

        Returns:
            Enhancement result with enhanced_image_path
        """
        from app.agents.preprocessing.image_enhancement_agent import ImageEnhancementAgent

        # Lazy initialization
        if self._preprocessing_agents is None:
            self._preprocessing_agents = {}

        if "enhancement" not in self._preprocessing_agents:
            self._preprocessing_agents["enhancement"] = ImageEnhancementAgent()

        try:
            result = await self._preprocessing_agents["enhancement"].process({
                "file_path": file_path,
                "quality_score": quality_score,
            })

            self.logger.info(
                "image_enhanced",
                enhancements=result.get("enhancements_applied", []),
                quality_improvement=result.get("quality_improvement", 0),
            )

            return result

        except Exception as e:
            self.logger.warning(
                "image_enhancement_failed",
                error=str(e),
            )
            # Return original file path on failure
            return {
                "enhanced_image_path": file_path,
                "enhancements_applied": [],
                "quality_improvement": 0.0,
            }

    async def _segment_pages(
        self, file_path: str, classification: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Segment document into pages and regions using PageSegmentationAgent.

        Uses the enterprise PageSegmentationAgent for:
        - Multi-page document handling
        - Layout analysis (single-column, multi-column, mixed)
        - Region detection (text, tables, images, headers, footers)
        - Reading order determination

        Args:
            file_path: Path to the document
            classification: Document classification results

        Returns:
            Segmentation result with pages, regions, and layout info
        """
        from app.agents.preprocessing.page_segmentation_agent import PageSegmentationAgent

        # Lazy initialization
        if self._page_segmentation_agent is None:
            self._page_segmentation_agent = PageSegmentationAgent()

        page_count = classification.get("metadata", {}).get("file_info", {}).get("page_count", 1)

        try:
            # Run page segmentation
            result = await self._page_segmentation_agent.process({
                "file_path": file_path,
                "classification": classification,
            })

            self.logger.info(
                "page_segmentation_completed",
                pages=result.get("page_count", page_count),
                layout_type=result.get("dominant_layout"),
                region_count=result.get("total_regions", 0),
            )

            return {
                "pages": result.get("page_count", page_count),
                "page_info": result.get("pages", []),
                "regions": result.get("all_regions", []),
                "dominant_layout": result.get("dominant_layout", "single_column"),
                "has_tables": result.get("has_tables", False),
                "has_images": result.get("has_images", False),
                "reading_order": result.get("reading_order", []),
                "needs_segmentation": page_count > 1 or result.get("complex_layout", False),
            }

        except Exception as e:
            self.logger.warning(
                "page_segmentation_failed",
                error=str(e),
            )
            # Return basic fallback
            return {
                "pages": page_count,
                "page_info": [],
                "regions": [],
                "dominant_layout": "single_column",
                "has_tables": classification.get("has_tables", False),
                "has_images": False,
                "reading_order": [],
                "needs_segmentation": page_count > 1,
            }

    async def _select_ocr_backend(
        self,
        classification: Dict[str, Any],
        preprocessing: Dict[str, Any],
        options: Dict[str, Any],
    ) -> str:
        """
        Select optimal OCR backend using UnifiedOCRRouter.

        Uses ML-based and rule-based routing with:
        - Load balancing based on queue lengths
        - GPU availability checking
        - Document complexity analysis
        - A/B test integration

        Args:
            classification: Document classification results
            preprocessing: Preprocessing results
            options: Processing options (can include force_backend)

        Returns:
            Selected backend name
        """
        # Allow override from options
        if options.get("force_backend"):
            self.logger.info(
                "backend_force_override",
                forced_backend=options["force_backend"],
            )
            return options["force_backend"]

        try:
            from app.agents.orchestration.unified_router import (
                UnifiedOCRRouter,
                DocumentAnalysis,
                SLARequirements,
            )

            # Initialize router (reuse if available)
            if not hasattr(self, "_ocr_router"):
                self._ocr_router = UnifiedOCRRouter(
                    use_ml_routing=True,
                    auto_train=True,
                )

            # Build DocumentAnalysis from classification results
            analysis = DocumentAnalysis(
                document_type=classification.get("document_type", "other"),
                complexity=classification.get("complexity", "medium"),
                quality_score=classification.get("quality_score", 0.7),
                has_tables=classification.get("has_tables", False),
                has_handwriting=classification.get("has_handwriting", False),
                has_fraktur=classification.get("has_fraktur", False),
                has_formulas=classification.get("has_formulas", False),
                has_multi_column=classification.get("has_multi_column", False),
                page_count=preprocessing.get("segmentation", {}).get("pages", 1),
                file_size_mb=classification.get("metadata", {}).get("file_info", {}).get("file_size_mb", 1.0),
                dpi=classification.get("metadata", {}).get("file_info", {}).get("dpi", 300),
                language=classification.get("language", "de"),
            )

            # Build SLA requirements from options
            sla = SLARequirements(
                max_processing_time_seconds=options.get("max_processing_time", 300),
                min_accuracy=options.get("min_accuracy", 0.85),
                is_critical=options.get("priority", 0) >= 2,
            )

            # Build user preferences
            preferences = {
                "preferred_backend": options.get("preferred_backend"),
            }

            # Get routing decision
            result = await self._ocr_router.select_backend(analysis, sla, preferences)

            self.logger.info(
                "ocr_backend_selected_by_router",
                backend=result.backend.value,
                reason=result.reason,
                confidence=result.confidence,
                method=result.routing_method.value,
            )

            return result.backend.value

        except Exception as e:
            self.logger.warning(
                "router_fallback_to_classification",
                error=str(e),
            )
            # Fallback to classification recommendation
            recommended = classification.get("recommended_backend")
            return recommended or "deepseek"

    async def _run_ocr(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Phase 3: Run OCR with selected backend and GPU recovery.

        Supports:
        - DeepSeek-Janus-Pro: Best for complex layouts, Fraktur, handwriting
        - GOT-OCR 2.0: Fast, good for tables and formulas
        - Surya + Docling: CPU fallback, layout analysis
        - Surya GPU: Fast GPU-accelerated standard OCR

        Includes:
        - GPU memory guard (85% VRAM threshold)
        - Automatic OOM recovery with cache clearing
        - Automatic fallback to CPU-based Surya if GPU backends fail
        - Partial result handling for graceful degradation
        """
        backend = input_data["backend"]
        file_path = input_data["file_path"]
        classification = input_data.get("classification", {})
        document_id = input_data.get("document_id", "unknown")

        self.logger.info(
            "ocr_processing_started",
            backend=backend,
            file_path=file_path,
            document_id=document_id,
        )

        # Lazy load OCR agents
        agent = await self._get_ocr_agent(backend)
        is_gpu_backend = backend in ["deepseek", "got_ocr", "surya_gpu"]

        try:
            # Prepare OCR input
            ocr_input = {
                "document_id": document_id,
                "image_path": file_path,
                "language": classification.get("language", "de"),
            }

            # Execute OCR with GPU memory guard for GPU backends
            if is_gpu_backend and self._gpu_recovery_manager:
                async with gpu_memory_guard(
                    threshold_percent=85.0,
                    recovery_manager=self._gpu_recovery_manager,
                ):
                    result = await self._execute_ocr_with_recovery(
                        agent, ocr_input, backend, document_id, classification
                    )
            else:
                result = await agent.process(ocr_input)

            # Extract standardized result
            ocr_result = {
                "text": result.get("text", ""),
                "confidence": result.get("confidence", 0.0),
                "backend": backend,
                "entities": result.get("entities", []),
                "layout": result.get("layout", {}),
                "pages": result.get("pages", []),
                "processing_time_ms": result.get("processing_time_ms"),
                "gpu_recovery_attempts": result.get("recovery_attempts", 0),
            }

            self.logger.info(
                "ocr_processing_completed",
                backend=backend,
                text_length=len(ocr_result["text"]),
                confidence=ocr_result["confidence"],
                recovery_attempts=ocr_result.get("gpu_recovery_attempts", 0),
            )

            return ocr_result

        except GPURecoveryError as e:
            self.logger.error(
                "ocr_gpu_recovery_exhausted",
                backend=backend,
                error=str(e),
                document_id=document_id,
            )

            # GPU recovery failed - try CPU fallback
            return await self._ocr_cpu_fallback(
                document_id, file_path, classification, str(e)
            )

        except Exception as e:
            self.logger.error(
                "ocr_processing_failed",
                backend=backend,
                error=str(e),
                exc_info=True,
            )

            # Check if this is an OOM error
            error_str = str(e).lower()
            is_oom = "out of memory" in error_str or "cuda" in error_str

            # Attempt fallback to CPU-based Surya if GPU backend failed
            if backend not in ["surya", "surya_docling"]:
                return await self._ocr_cpu_fallback(
                    document_id, file_path, classification,
                    str(e), is_oom=is_oom
                )

            raise

        finally:
            # Cleanup agent resources
            if agent and hasattr(agent, "cleanup"):
                try:
                    await agent.cleanup()
                except Exception as cleanup_error:
                    self.logger.warning(
                        "ocr_cleanup_warning",
                        error=str(cleanup_error),
                    )

            # Clear GPU cache after processing
            if is_gpu_backend and self._gpu_recovery_manager:
                try:
                    await self._gpu_recovery_manager.clear_cache()
                except Exception:
                    pass

    async def _execute_ocr_with_recovery(
        self,
        agent,
        ocr_input: Dict[str, Any],
        backend: str,
        document_id: str,
        classification: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute OCR with GPU OOM recovery.

        Attempts GPU processing with automatic recovery:
        1. Clear GPU cache and retry
        2. Reduce batch size if applicable
        3. Fall back to CPU after max retries

        Args:
            agent: OCR agent instance
            ocr_input: Input data for OCR
            backend: Backend name
            document_id: Document ID for logging
            classification: Document classification

        Returns:
            OCR result dictionary

        Raises:
            GPURecoveryError: If all recovery attempts fail
        """
        max_recovery_attempts = 3
        recovery_attempts = 0

        while recovery_attempts < max_recovery_attempts:
            try:
                result = await agent.process(ocr_input)
                result["recovery_attempts"] = recovery_attempts
                return result

            except Exception as e:
                error_str = str(e).lower()
                is_oom = "out of memory" in error_str or "cuda" in error_str

                if not is_oom:
                    raise

                recovery_attempts += 1

                self.logger.warning(
                    "ocr_gpu_oom_recovery_attempt",
                    backend=backend,
                    document_id=document_id,
                    attempt=recovery_attempts,
                    max_attempts=max_recovery_attempts,
                )

                if self._gpu_recovery_manager:
                    # Attempt recovery
                    recovered = await self._gpu_recovery_manager.recover_from_oom(
                        error=e,
                        context={
                            "backend": backend,
                            "document_id": document_id,
                            "attempt": recovery_attempts,
                        }
                    )

                    if not recovered:
                        raise GPURecoveryError(
                            f"GPU recovery failed after {recovery_attempts} attempts: {e}"
                        )

                    # Wait before retry
                    await asyncio.sleep(1.0 * recovery_attempts)
                else:
                    raise

        raise GPURecoveryError(
            f"GPU recovery exhausted after {max_recovery_attempts} attempts"
        )

    async def _ocr_cpu_fallback(
        self,
        document_id: str,
        file_path: str,
        classification: Dict[str, Any],
        original_error: str,
        is_oom: bool = False,
    ) -> Dict[str, Any]:
        """
        Fall back to CPU-based Surya OCR.

        Args:
            document_id: Document ID
            file_path: Path to document
            classification: Document classification
            original_error: Original error message
            is_oom: Whether the failure was due to OOM

        Returns:
            OCR result from CPU backend
        """
        self.logger.warning(
            "ocr_fallback_to_cpu",
            document_id=document_id,
            reason=original_error,
            is_oom=is_oom,
        )

        try:
            fallback_agent = await self._get_ocr_agent("surya")
            fallback_result = await fallback_agent.process({
                "document_id": document_id,
                "image_path": file_path,
                "language": classification.get("language", "de"),
            })

            return {
                "text": fallback_result.get("text", ""),
                "confidence": fallback_result.get("confidence", 0.0),
                "backend": "surya_fallback",
                "entities": fallback_result.get("entities", []),
                "layout": fallback_result.get("layout", {}),
                "fallback_reason": original_error,
                "fallback_type": "oom_recovery" if is_oom else "error_recovery",
            }

        except Exception as fallback_error:
            self.logger.error(
                "ocr_cpu_fallback_failed",
                document_id=document_id,
                error=str(fallback_error),
            )
            raise

    async def _get_ocr_agent(self, backend: str):
        """
        Get or create an OCR agent for the specified backend.

        Args:
            backend: OCR backend name (deepseek, got_ocr, surya, surya_gpu)

        Returns:
            Initialized OCR agent instance

        Raises:
            ValueError: If backend is not supported
        """
        # Import agents lazily to avoid circular imports
        from app.agents.ocr.surya_docling_agent import SuryaDoclingAgent

        # Always available CPU-based agents
        available_agents = {
            "surya": SuryaDoclingAgent,
            "surya_docling": SuryaDoclingAgent,
        }

        # Try to import GPU-based agents
        try:
            import torch
            if torch.cuda.is_available():
                from app.agents.ocr.deepseek_agent import DeepSeekAgent
                from app.agents.ocr.got_ocr_agent import GOTOCRAgent
                from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent

                available_agents.update({
                    "deepseek": DeepSeekAgent,
                    "got_ocr": GOTOCRAgent,
                    "surya_gpu": SuryaGPUAgent,
                })

                self.logger.debug(
                    "gpu_agents_available",
                    gpu_name=torch.cuda.get_device_name(0),
                )
            else:
                self.logger.warning("gpu_not_available_using_cpu_agents")

        except ImportError as e:
            self.logger.warning(
                "gpu_agents_import_failed",
                error=str(e),
            )

        # Get the agent class
        if backend not in available_agents:
            # Fallback to Surya for unknown backends
            self.logger.warning(
                "unknown_backend_fallback",
                requested=backend,
                fallback="surya",
            )
            backend = "surya"

        agent_class = available_agents[backend]

        # Create and return agent instance
        return agent_class()

    async def _postprocess_result(
        self, input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Phase 4: Post-process OCR result (parallel tasks).

        Performs:
        - German language correction (umlaut restoration, OCR error fixes)
        - Entity extraction (dates, currencies, IBANs, VAT IDs, etc.)
        """
        ocr_result = input_data["ocr_result"]
        classification = input_data["classification"]

        # Run postprocessing tasks in parallel
        tasks = [
            self._correct_german_text(ocr_result["text"]),
            self._extract_entities(ocr_result["text"], classification),
        ]

        correction_result, extraction_result = await asyncio.gather(*tasks)

        # Get corrected text
        corrected_text = correction_result.get("text", ocr_result["text"])

        return {
            "text": corrected_text,
            "entities": extraction_result.get("entities", []),
            "original_confidence": ocr_result.get("confidence"),
            "correction_stats": {
                "corrections_applied": correction_result.get("corrections_applied", 0),
                "umlauts_restored": correction_result.get("umlauts_restored", 0),
                "validation_score": correction_result.get("validation_score", 0.0),
            },
            "extraction_stats": {
                "entity_count": extraction_result.get("entity_count", 0),
                "entity_types": extraction_result.get("entity_types", {}),
                "critical_count": extraction_result.get("critical_count", 0),
            },
            "invoice_data": extraction_result.get("invoice_data"),
        }

    async def _correct_german_text(self, text: str) -> Dict[str, Any]:
        """
        Correct German language specifics using GermanCorrectionAgent.

        Performs:
        - Umlaut restoration (ae→ä, oe→ö, ue→ü)
        - Eszett correction (ss→ß where appropriate)
        - Context-aware OCR error correction
        """
        from app.agents.postprocessing.german_correction_agent import GermanCorrectionAgent

        # Lazy initialization
        if self._postprocessing_agents is None:
            self._postprocessing_agents = {}

        if "german_correction" not in self._postprocessing_agents:
            self._postprocessing_agents["german_correction"] = GermanCorrectionAgent()

        try:
            result = await self._postprocessing_agents["german_correction"].process({
                "text": text,
            })

            self.logger.info(
                "german_correction_applied",
                corrections=result.get("corrections_applied", 0),
                umlauts_restored=result.get("umlauts_restored", 0),
            )

            return result

        except Exception as e:
            self.logger.warning(
                "german_correction_failed",
                error=str(e),
            )
            return {"text": text, "corrections_applied": 0}

    async def _extract_entities(
        self, text: str, classification: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Extract business entities using EntityExtractionAgent.

        Extracts:
        - Dates (German formats)
        - Currency amounts
        - IBANs with validation
        - VAT IDs with validation
        - Business terms
        - Contact information
        - Invoice-specific fields
        """
        from app.agents.postprocessing.entity_extraction_agent import EntityExtractionAgent

        # Lazy initialization
        if self._postprocessing_agents is None:
            self._postprocessing_agents = {}

        if "entity_extraction" not in self._postprocessing_agents:
            self._postprocessing_agents["entity_extraction"] = EntityExtractionAgent()

        try:
            result = await self._postprocessing_agents["entity_extraction"].process({
                "text": text,
                "classification": classification,
            })

            self.logger.info(
                "entity_extraction_completed",
                entity_count=result.get("entity_count", 0),
                critical_count=result.get("critical_count", 0),
            )

            return result

        except Exception as e:
            self.logger.warning(
                "entity_extraction_failed",
                error=str(e),
            )
            return {"entities": [], "entity_count": 0}

    async def _quality_check(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Phase 5: Quality assurance check using QA Agent.

        Performs comprehensive quality validation:
        - Text quality analysis
        - German language accuracy
        - Entity validation
        - Confidence assessment
        - Human review determination
        """
        from app.agents.postprocessing.qa_agent import QAAgent

        postprocessing = input_data["postprocessing"]
        classification = input_data.get("classification", {})

        # Lazy initialization of QA Agent
        if self._qa_agent is None:
            self._qa_agent = QAAgent()

        try:
            # Prepare QA input
            qa_input = {
                "text": postprocessing.get("text", ""),
                "entities": postprocessing.get("entities", []),
                "ocr_confidence": postprocessing.get("original_confidence", 0.8),
                "classification": classification,
                "correction_result": postprocessing.get("correction_stats", {}),
            }

            # Run QA Agent
            qa_result = await self._qa_agent.process(qa_input)

            self.logger.info(
                "quality_check_completed",
                quality_score=qa_result.get("quality_score"),
                quality_level=qa_result.get("quality_level"),
                needs_review=qa_result.get("needs_review"),
                issue_count=qa_result.get("issue_count", 0),
            )

            return {
                "score": qa_result.get("quality_score", 0.0),
                "needs_review": qa_result.get("needs_review", False),
                "review_reasons": qa_result.get("review_reasons", []),
                "quality_level": qa_result.get("quality_level"),
                "quality_level_german": qa_result.get("quality_level_german"),
                "issues": qa_result.get("issues", []),
                "critical_issues": qa_result.get("critical_issues", []),
                "suggestions": qa_result.get("suggestions", []),
                "is_acceptable": qa_result.get("is_acceptable", True),
                "recommendation": qa_result.get("recommendation"),
                "checks": {
                    "text_quality": qa_result.get("validation_details", {}).get("text_quality", {}).get("score", 0),
                    "german_quality": qa_result.get("validation_details", {}).get("german_quality", {}).get("score", 0),
                    "entity_quality": qa_result.get("validation_details", {}).get("entity_quality", {}).get("score", 0),
                },
            }

        except Exception as e:
            self.logger.error(
                "quality_check_failed",
                error=str(e),
            )
            # Fallback to simple confidence-based check
            score = postprocessing.get("original_confidence", 0.9)
            needs_review = score < 0.7

            return {
                "score": score,
                "needs_review": needs_review,
                "review_reasons": ["QA-Agent Fehler - manuelle Prüfung empfohlen"] if needs_review else [],
                "checks": {
                    "confidence": score >= 0.7,
                    "qa_error": str(e),
                },
            }

    async def _trigger_human_review(
        self, document_id: str, qa_result: Dict[str, Any]
    ) -> None:
        """
        Trigger human-in-the-loop review with Redis queue and event publishing.

        This method:
        1. Adds document to Redis human review queue (sorted by priority)
        2. Publishes event for real-time notification systems
        3. Logs review request with all relevant details

        Args:
            document_id: Document UUID
            qa_result: QA result containing score, reasons, and issues
        """
        qa_score = qa_result.get("score", 0.0)
        review_reasons = qa_result.get("review_reasons", [])
        critical_issues = qa_result.get("critical_issues", [])

        self.logger.warning(
            "human_review_triggered",
            document_id=document_id,
            qa_score=qa_score,
            review_reasons=review_reasons,
            critical_issue_count=len(critical_issues),
        )

        try:
            # Add to Redis human review queue
            redis = await get_redis()

            # Prepare metadata for the review item
            review_metadata = {
                "quality_level": qa_result.get("quality_level"),
                "quality_level_german": qa_result.get("quality_level_german"),
                "issue_count": qa_result.get("issue_count", 0),
                "critical_issues": [
                    {
                        "type": issue.get("type"),
                        "message": issue.get("message"),
                        "severity": issue.get("severity"),
                    }
                    for issue in critical_issues[:5]  # Limit to 5
                ],
                "suggestion_count": len(qa_result.get("suggestions", [])),
                "recommendation": qa_result.get("recommendation"),
            }

            # Add to priority queue (lower score = higher priority)
            await redis.add_to_review_queue(
                document_id=document_id,
                qa_score=qa_score,
                reasons=review_reasons,
                metadata=review_metadata,
            )

            # Get queue length for logging
            queue_length = await redis.get_review_queue_length()

            self.logger.info(
                "human_review_queued",
                document_id=document_id,
                queue_position="priority_based",
                total_queue_length=queue_length,
            )

            # Publish additional event for notification systems (webhooks, etc.)
            await redis.publish_event(
                event_type="review.required",
                data={
                    "document_id": document_id,
                    "qa_score": qa_score,
                    "reasons": review_reasons,
                    "quality_level": qa_result.get("quality_level"),
                    "critical_issue_count": len(critical_issues),
                    "priority": "high" if qa_score < 0.5 else "normal",
                },
                channel="review_events",
            )

        except Exception as e:
            self.logger.error(
                "human_review_queue_failed",
                document_id=document_id,
                error=str(e),
            )
            # Don't fail the workflow if review queue fails
            # The document is still processed, just won't be in the review queue

    async def _store_and_index(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Phase 6: Store OCR results and index for search.

        Performs:
        - Update PostgreSQL document record with extracted text and metadata
        - Create OCR version for version history
        - Optionally generate and store searchable PDF in MinIO

        Args:
            input_data: Dictionary containing:
                - document_id: Document UUID
                - text: Extracted and corrected text
                - metadata: Classification, entities, QA score, etc.

        Returns:
            Storage result with stored paths and metadata
        """
        document_id = input_data["document_id"]
        text = input_data["text"]
        metadata = input_data["metadata"]

        storage_result = {
            "document_id": document_id,
            "stored_at": datetime.utcnow().isoformat(),
            "metadata": metadata,
            "postgresql_updated": False,
            "version_created": False,
            "minio_stored": False,
        }

        # Import dependencies
        from app.api.dependencies import AsyncSessionLocal
        from app.db.models import Document
        from sqlalchemy import select, update

        try:
            # ================================================================
            # 1. Update PostgreSQL Document Record
            # ================================================================
            async with AsyncSessionLocal() as db:
                # Fetch the document
                result = await db.execute(
                    select(Document).where(Document.id == document_id)
                )
                document = result.scalar_one_or_none()

                if not document:
                    self.logger.error(
                        "document_not_found_for_storage",
                        document_id=document_id,
                    )
                    raise ValueError(f"Dokument nicht gefunden: {document_id}")

                # Update document with OCR results
                classification = metadata.get("classification", {})
                entities = metadata.get("entities", [])
                qa_score = metadata.get("qa_score", 0.0)

                # Calculate processing duration
                processing_duration_ms = None
                if hasattr(self, "_processing_start_time"):
                    processing_duration_ms = int(
                        (datetime.utcnow() - self._processing_start_time).total_seconds() * 1000
                    )

                # Update document fields
                document.extracted_text = text
                document.status = "completed"
                document.ocr_confidence = qa_score
                document.document_type = classification.get("document_type", "other")
                document.detected_language = classification.get("language", "de")
                document.has_umlauts = "ä" in text or "ö" in text or "ü" in text or "ß" in text
                document.processed_date = datetime.utcnow()

                if processing_duration_ms:
                    document.processing_duration_ms = processing_duration_ms

                # Store entities and metadata in JSONB column
                document.document_metadata = {
                    **(document.document_metadata or {}),
                    "classification": classification,
                    "entities": [
                        {"type": e.get("type"), "value": e.get("value"), "confidence": e.get("confidence")}
                        for e in entities[:100]  # Limit to prevent huge JSONB
                    ],
                    "entity_summary": {
                        "total_count": len(entities),
                        "dates": sum(1 for e in entities if e.get("type") == "date"),
                        "amounts": sum(1 for e in entities if e.get("type") == "amount"),
                        "ibans": sum(1 for e in entities if e.get("type") == "iban"),
                        "vat_ids": sum(1 for e in entities if e.get("type") == "vat_id"),
                    },
                    "qa_score": qa_score,
                    "ocr_backend": metadata.get("ocr_backend", "unknown"),
                    "processing_completed_at": datetime.utcnow().isoformat(),
                }

                await db.commit()
                storage_result["postgresql_updated"] = True

                self.logger.info(
                    "postgresql_document_updated",
                    document_id=document_id,
                    text_length=len(text),
                    entity_count=len(entities),
                )

                # ================================================================
                # 2. Create OCR Version for Version History
                # ================================================================
                try:
                    from app.services.version_service import get_version_service

                    version_service = get_version_service()

                    # Prepare OCR data for versioning
                    ocr_data = {
                        "text": text,
                        "backend": metadata.get("ocr_backend", "unknown"),
                        "confidence_score": qa_score,
                        "metadata": {
                            "backend_used": metadata.get("ocr_backend", "unknown"),
                            "language": classification.get("language", "de"),
                            "timestamp": datetime.utcnow().isoformat(),
                        },
                        "detected_dates": [
                            e.get("value") for e in entities if e.get("type") == "date"
                        ][:10],
                        "detected_amounts": [
                            e.get("value") for e in entities if e.get("type") == "amount"
                        ][:10],
                        "ibans": [
                            e.get("value") for e in entities if e.get("type") == "iban"
                        ][:10],
                        "vat_ids": [
                            e.get("value") for e in entities if e.get("type") == "vat_id"
                        ][:10],
                    }

                    # Get user_id from document
                    user_id = document.owner_id

                    version = await version_service.create_version_from_dict(
                        db=db,
                        document_id=document_id,
                        ocr_data=ocr_data,
                        user_id=user_id,
                        version_note=f"Automatische OCR-Verarbeitung mit {metadata.get('ocr_backend', 'unknown')}"
                    )

                    storage_result["version_created"] = True
                    storage_result["version_number"] = version.version_number

                    self.logger.info(
                        "ocr_version_created",
                        document_id=document_id,
                        version_number=version.version_number,
                    )

                except Exception as version_error:
                    # Version creation is not critical - log and continue
                    self.logger.warning(
                        "version_creation_failed",
                        document_id=document_id,
                        error=str(version_error),
                    )

            # ================================================================
            # 3. Store Searchable Content in MinIO (Optional)
            # ================================================================
            try:
                from app.services.storage_service import get_storage_service

                storage_service = get_storage_service()

                if storage_service.available:
                    # Create searchable text file
                    text_content = f"""# OCR Ergebnis für Dokument {document_id}
# Verarbeitet am: {datetime.utcnow().isoformat()}
# Backend: {metadata.get('ocr_backend', 'unknown')}
# Konfidenz: {qa_score:.2%}

{text}

---
Metadaten:
- Dokumenttyp: {classification.get('document_type', 'unbekannt')}
- Sprache: {classification.get('language', 'de')}
- Entitäten gefunden: {len(entities)}
""".encode("utf-8")

                    # Upload to MinIO
                    upload_result = await storage_service.upload_document(
                        file_data=text_content,
                        filename=f"{document_id}_ocr_result.txt",
                        content_type="text/plain; charset=utf-8",
                        user_id=str(document.owner_id) if document.owner_id else None,
                        metadata={
                            "document-id": str(document_id),
                            "content-type": "ocr-result",
                            "ocr-backend": metadata.get("ocr_backend", "unknown"),
                        }
                    )

                    storage_result["minio_stored"] = True
                    storage_result["minio_path"] = upload_result.get("storage_path")

                    self.logger.info(
                        "minio_ocr_result_stored",
                        document_id=document_id,
                        storage_path=upload_result.get("storage_path"),
                    )

            except Exception as minio_error:
                # MinIO storage is not critical - log and continue
                self.logger.warning(
                    "minio_storage_failed",
                    document_id=document_id,
                    error=str(minio_error),
                )

            self.logger.info(
                "storage_phase_completed",
                document_id=document_id,
                postgresql_updated=storage_result["postgresql_updated"],
                version_created=storage_result["version_created"],
                minio_stored=storage_result["minio_stored"],
            )

            return storage_result

        except Exception as e:
            self.logger.error(
                "storage_phase_failed",
                document_id=document_id,
                error=str(e),
                exc_info=True,
            )
            raise

    async def get_health_status(self) -> Dict[str, Any]:
        """
        Get comprehensive health status of the orchestrator and all components.

        Returns status of:
        - Error recovery components (circuit breakers, retry strategy, GPU recovery)
        - Agent availability
        - External service health (Redis, PostgreSQL, MinIO)

        Returns:
            Health status dictionary
        """
        health = {
            "orchestrator": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "error_recovery": {},
            "agents": {},
            "external_services": {},
        }

        # Check circuit breakers
        if self._circuit_breaker_manager:
            circuit_status = {}
            for name in ["redis", "postgresql", "minio"]:
                try:
                    circuit = self._circuit_breaker_manager.get_circuit(name)
                    if circuit:
                        circuit_status[name] = {
                            "state": circuit.state.value if hasattr(circuit.state, 'value') else str(circuit.state),
                            "failure_count": circuit.failure_count,
                            "last_failure": circuit.last_failure_time.isoformat() if circuit.last_failure_time else None,
                        }
                except Exception:
                    circuit_status[name] = {"state": "unknown"}
            health["error_recovery"]["circuit_breakers"] = circuit_status
        else:
            health["error_recovery"]["circuit_breakers"] = "not_initialized"

        # Check retry strategy
        if self._retry_strategy:
            health["error_recovery"]["retry_strategy"] = {
                "enabled": True,
                "phases_configured": list(self._retry_strategy.configs.keys()) if hasattr(self._retry_strategy, 'configs') else [],
            }
        else:
            health["error_recovery"]["retry_strategy"] = {"enabled": False}

        # Check GPU recovery
        if self._gpu_recovery_manager:
            try:
                gpu_status = await self._gpu_recovery_manager.get_status()
                health["error_recovery"]["gpu_recovery"] = {
                    "enabled": True,
                    "gpu_available": gpu_status.get("gpu_available", False),
                    "vram_used_percent": gpu_status.get("vram_used_percent", 0),
                    "recovery_attempts": gpu_status.get("total_recovery_attempts", 0),
                }
            except Exception as e:
                health["error_recovery"]["gpu_recovery"] = {
                    "enabled": True,
                    "status": "error",
                    "error": str(e),
                }
        else:
            health["error_recovery"]["gpu_recovery"] = {"enabled": False}

        # Check partial result handler
        if self._partial_result_handler:
            health["error_recovery"]["partial_results"] = {
                "enabled": True,
            }
        else:
            health["error_recovery"]["partial_results"] = {"enabled": False}

        # Check agent availability
        health["agents"] = {
            "classification": self._classification_agent is not None,
            "preprocessing": self._preprocessing_agents is not None,
            "page_segmentation": self._page_segmentation_agent is not None,
            "postprocessing": self._postprocessing_agents is not None,
            "qa": self._qa_agent is not None,
        }

        # Check external services
        try:
            redis = await get_redis()
            health["external_services"]["redis"] = {
                "status": "healthy" if redis else "unavailable",
            }
        except Exception as e:
            health["external_services"]["redis"] = {
                "status": "error",
                "error": str(e),
            }

        return health

    async def get_circuit_breaker_stats(self) -> Dict[str, Any]:
        """Get detailed circuit breaker statistics."""
        if not self._circuit_breaker_manager:
            return {"error": "Circuit breaker manager not initialized"}

        return await self._circuit_breaker_manager.get_all_stats()

    async def reset_circuit_breaker(self, circuit_name: str) -> bool:
        """
        Manually reset a circuit breaker.

        Args:
            circuit_name: Name of the circuit to reset

        Returns:
            True if reset was successful
        """
        if not self._circuit_breaker_manager:
            return False

        try:
            circuit = self._circuit_breaker_manager.get_circuit(circuit_name)
            if circuit:
                await circuit.reset()
                self.logger.info(
                    "circuit_breaker_reset",
                    circuit=circuit_name,
                )
                return True
        except Exception as e:
            self.logger.error(
                "circuit_breaker_reset_failed",
                circuit=circuit_name,
                error=str(e),
            )

        return False
