"""
OCR Processing Celery Tasks.

Tasks for asynchronous OCR processing with GPU/CPU workers.
Referenced in app/workers/celery_app.py task routes.
"""

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from app.agents.ocr import DeepSeekAgent, GOTOCRAgent, HybridOCRAgent, SuryaDoclingAgent
from app.agents.orchestration import DocumentProcessingOrchestrator, OCRBackendRouter
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


# =============================================================================
# GPU-ACCELERATED OCR TASKS
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.ocr_tasks.process_document_gpu",
    bind=True,
    queue="ocr_gpu",
    max_retries=3,
    time_limit=600,  # 10 minutes
    soft_time_limit=540,  # 9 minutes
    acks_late=True,
)
def process_document_gpu(
    self,
    document_id: str,
    file_path: str,
    backend: str = "auto",
    priority: int = 0,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Process document with GPU-accelerated OCR.

    Args:
        document_id: Unique document identifier
        file_path: Path to document file
        backend: OCR backend ('auto', 'deepseek', 'got_ocr', 'hybrid')
        priority: Processing priority (0=normal, 1=high, 2=critical)
        options: Additional processing options

    Returns:
        Result dictionary with text, confidence, metadata

    Raises:
        Retry: On transient errors (GPU OOM, timeout, etc.)
    """
    logger.info(
        "gpu_task_started",
        task_id=self.request.id,
        document_id=document_id,
        backend=backend,
        priority=priority,
    )

    options = options or {}

    # Create new event loop for this task (Celery workers don't have a running loop)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        # Backend selection
        if backend == "auto":
            # Use router to select optimal backend
            router = OCRBackendRouter()
            router_result = loop.run_until_complete(
                router.execute(
                    input_data={
                        "document_metadata": {
                            # TODO: Get from classification
                            "document_type": options.get("document_type", "unknown"),
                            "complexity": options.get("complexity", "medium"),
                            "has_tables": options.get("has_tables", False),
                            "quality_score": options.get("quality_score", 0.8),
                        }
                    }
                )
            )
            backend = router_result["result"]["backend"]
            logger.info(
                "backend_selected",
                selected=backend,
                reason=router_result["result"]["reason"],
            )

        # Select and instantiate ONLY the needed agent (avoid memory waste)
        if backend == "deepseek":
            agent = DeepSeekAgent()
        elif backend == "got_ocr":
            agent = GOTOCRAgent()
        elif backend == "hybrid":
            agent = HybridOCRAgent()
        else:
            raise ValueError(f"Unknown backend: {backend}")

        # Process document
        result = loop.run_until_complete(
            agent.execute(
                input_data={
                    "document_id": document_id,
                    "image_path": file_path,
                    "language": options.get("language", "de"),
                    "options": options,
                },
                context={
                    "task_id": self.request.id,
                    "priority": priority,
                },
            )
        )

        logger.info(
            "gpu_task_completed",
            task_id=self.request.id,
            document_id=document_id,
            duration=result["metadata"]["duration_seconds"],
            backend=backend,
        )

        return {
            "status": "success",
            "document_id": document_id,
            "backend": backend,
            "result": result["result"],
            "metadata": result["metadata"],
        }

    except Exception as e:
        logger.error(
            "gpu_task_failed",
            task_id=self.request.id,
            document_id=document_id,
            error=str(e),
            exc_info=True,
        )

        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            retry_countdown = 60 * (2 ** self.request.retries)
            logger.warning(
                "gpu_task_retrying",
                task_id=self.request.id,
                retry_count=self.request.retries + 1,
                retry_in_seconds=retry_countdown,
            )
            raise self.retry(exc=e, countdown=retry_countdown)

        # Final failure
        return {
            "status": "failed",
            "document_id": document_id,
            "error": str(e),
            "error_type": type(e).__name__,
        }

    finally:
        # Always close the event loop to prevent memory leaks
        loop.close()


# =============================================================================
# CPU FALLBACK OCR TASKS
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.ocr_tasks.process_document_cpu",
    bind=True,
    queue="ocr_cpu",
    max_retries=3,
    time_limit=900,  # 15 minutes (slower on CPU)
    acks_late=True,
)
def process_document_cpu(
    self,
    document_id: str,
    file_path: str,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Process document with CPU-only OCR (fallback).

    Uses Surya+Docling pipeline (CPU-only).

    Args:
        document_id: Unique document identifier
        file_path: Path to document file
        options: Additional processing options

    Returns:
        Result dictionary
    """
    logger.info(
        "cpu_task_started",
        task_id=self.request.id,
        document_id=document_id,
    )

    options = options or {}

    # Create new event loop for this task
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        # Use CPU-only agent
        agent = SuryaDoclingAgent()

        result = loop.run_until_complete(
            agent.execute(
                input_data={
                    "document_id": document_id,
                    "image_path": file_path,
                    "language": options.get("language", "de"),
                },
                context={"task_id": self.request.id},
            )
        )

        logger.info(
            "cpu_task_completed",
            task_id=self.request.id,
            document_id=document_id,
        )

        return {
            "status": "success",
            "document_id": document_id,
            "backend": "surya_cpu",
            "result": result["result"],
            "metadata": result["metadata"],
        }

    except Exception as e:
        logger.error(
            "cpu_task_failed",
            task_id=self.request.id,
            document_id=document_id,
            error=str(e),
        )

        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=120)

        return {
            "status": "failed",
            "document_id": document_id,
            "error": str(e),
        }

    finally:
        # Always close the event loop to prevent memory leaks
        loop.close()


# =============================================================================
# BATCH PROCESSING TASKS
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.ocr_tasks.batch_process_documents",
    bind=True,
    queue="ocr_gpu",
    max_retries=2,
    time_limit=1800,  # 30 minutes for batch
)
def batch_process_documents(
    self,
    document_ids: List[str],
    file_paths: List[str],
    backend: str = "got_ocr",
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Batch process multiple documents for better GPU utilization.

    Args:
        document_ids: List of document IDs
        file_paths: List of file paths
        backend: OCR backend to use
        options: Processing options

    Returns:
        Batch results
    """
    logger.info(
        "batch_task_started",
        task_id=self.request.id,
        batch_size=len(document_ids),
        backend=backend,
    )

    if len(document_ids) != len(file_paths):
        raise ValueError("document_ids and file_paths must have same length")

    options = options or {}

    # Create new event loop for this task
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        # Select and instantiate ONLY the needed agent (avoid memory waste)
        if backend == "deepseek":
            agent = DeepSeekAgent()
        elif backend == "got_ocr":
            agent = GOTOCRAgent()
        else:
            raise ValueError(f"Backend {backend} not supported for batch processing")

        # Prepare batch input
        batch_input = [
            {
                "document_id": doc_id,
                "image_path": file_path,
                "language": options.get("language", "de"),
            }
            for doc_id, file_path in zip(document_ids, file_paths)
        ]

        # Process batch
        results = loop.run_until_complete(agent.process_batch(batch_input))

        logger.info(
            "batch_task_completed",
            task_id=self.request.id,
            batch_size=len(document_ids),
            successful=sum(1 for r in results if "error" not in r),
            failed=sum(1 for r in results if "error" in r),
        )

        return {
            "status": "success",
            "batch_size": len(document_ids),
            "backend": backend,
            "results": results,
        }

    except Exception as e:
        logger.error(
            "batch_task_failed",
            task_id=self.request.id,
            error=str(e),
        )

        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=180)

        return {
            "status": "failed",
            "error": str(e),
        }

    finally:
        # Always close the event loop to prevent memory leaks
        loop.close()


# =============================================================================
# ORCHESTRATED WORKFLOW TASK
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.ocr_tasks.process_document_workflow",
    bind=True,
    queue="orchestration.master",
    max_retries=3,
    time_limit=900,  # 15 minutes for full workflow
)
def process_document_workflow(
    self,
    document_id: str,
    file_path: str,
    priority: int = 0,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Orchestrate complete document processing workflow.

    Phases:
    1. Classification
    2. Pre-Processing
    3. OCR (backend selection + processing)
    4. Post-Processing
    5. QA
    6. Storage

    Args:
        document_id: Document ID
        file_path: File path
        priority: Priority level
        options: Processing options

    Returns:
        Workflow result
    """
    logger.info(
        "workflow_task_started",
        task_id=self.request.id,
        document_id=document_id,
        priority=priority,
    )

    options = options or {}

    # Create new event loop for this task
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        orchestrator = DocumentProcessingOrchestrator()

        result = loop.run_until_complete(
            orchestrator.execute(
                input_data={
                    "document_id": document_id,
                    "file_path": file_path,
                    "priority": priority,
                    "options": options,
                },
                context={"task_id": self.request.id},
            )
        )

        logger.info(
            "workflow_task_completed",
            task_id=self.request.id,
            document_id=document_id,
            status=result["result"]["status"],
            duration=result["metadata"]["duration_seconds"],
        )

        return result["result"]

    except Exception as e:
        logger.error(
            "workflow_task_failed",
            task_id=self.request.id,
            document_id=document_id,
            error=str(e),
            exc_info=True,
        )

        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=120)

        return {
            "status": "failed",
            "document_id": document_id,
            "error": str(e),
        }

    finally:
        # Always close the event loop to prevent memory leaks
        loop.close()
