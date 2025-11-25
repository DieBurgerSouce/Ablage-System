"""
Agent Management API Endpoints.

Provides endpoints for:
- Agent status monitoring
- Agent execution triggering
- Agent configuration
- Workflow orchestration
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, field_validator

from app.agents.orchestration import DocumentProcessingOrchestrator, OCRBackendRouter
from app.core.redis_state import get_redis
from app.workers.tasks.ocr_tasks import (
    batch_process_documents,
    process_document_gpu,
    process_document_workflow,
)

router = APIRouter(prefix="/agents", tags=["agents"])


# =============================================================================
# PYDANTIC MODELS
# =============================================================================


class AgentExecuteRequest(BaseModel):
    """Request model for agent execution."""

    document_id: str
    file_path: str
    backend: str = "auto"
    priority: int = 0
    options: Optional[Dict[str, Any]] = None

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, v: str) -> str:
        """Validate file path to prevent path traversal attacks."""
        # Convert to Path and resolve to absolute path
        try:
            path = Path(v).resolve()
        except (ValueError, OSError) as e:
            raise ValueError(f"Invalid file path: {e}")

        # Check for path traversal attempts
        if ".." in v or v.startswith("/"):
            raise ValueError("Path traversal not allowed")

        # Ensure path exists
        if not path.exists():
            raise ValueError(f"File not found: {v}")

        # Ensure it's a file, not a directory
        if not path.is_file():
            raise ValueError(f"Path must be a file, not a directory: {v}")

        return str(path)


class BatchProcessRequest(BaseModel):
    """Request model for batch processing."""

    document_ids: List[str]
    file_paths: List[str]
    backend: str = "got_ocr"
    options: Optional[Dict[str, Any]] = None

    @field_validator("file_paths")
    @classmethod
    def validate_file_paths(cls, v: List[str]) -> List[str]:
        """Validate all file paths in batch."""
        validated_paths = []
        for file_path in v:
            try:
                path = Path(file_path).resolve()
            except (ValueError, OSError) as e:
                raise ValueError(f"Invalid file path '{file_path}': {e}")

            if ".." in file_path or file_path.startswith("/"):
                raise ValueError(f"Path traversal not allowed: {file_path}")

            if not path.exists():
                raise ValueError(f"File not found: {file_path}")

            if not path.is_file():
                raise ValueError(f"Path must be a file: {file_path}")

            validated_paths.append(str(path))

        return validated_paths


class WorkflowExecuteRequest(BaseModel):
    """Request model for workflow execution."""

    document_id: str
    file_path: str
    priority: int = 0
    options: Optional[Dict[str, Any]] = None

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, v: str) -> str:
        """Validate file path to prevent path traversal attacks."""
        try:
            path = Path(v).resolve()
        except (ValueError, OSError) as e:
            raise ValueError(f"Invalid file path: {e}")

        if ".." in v or v.startswith("/"):
            raise ValueError("Path traversal not allowed")

        if not path.exists():
            raise ValueError(f"File not found: {v}")

        if not path.is_file():
            raise ValueError(f"Path must be a file: {v}")

        return str(path)


# =============================================================================
# AGENT STATUS ENDPOINTS
# =============================================================================


@router.get("/status")
async def get_all_agents_status():
    """
    Get status of all agents.

    Returns list of agent statuses with metadata.
    """
    redis = await get_redis()
    statuses = await redis.get_all_agents_status()

    return {
        "total_count": len(statuses),
        "agents": statuses,
    }


@router.get("/status/{agent_id}")
async def get_agent_status(agent_id: str):
    """
    Get status of specific agent.

    Args:
        agent_id: Agent identifier

    Returns:
        Agent status details
    """
    redis = await get_redis()
    status = await redis.get_agent_status(agent_id)

    if not status:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    return {
        "agent_id": agent_id,
        **status,
    }


# =============================================================================
# AGENT EXECUTION ENDPOINTS
# =============================================================================


@router.post("/execute/ocr")
async def execute_ocr_agent(request: AgentExecuteRequest, background_tasks: BackgroundTasks):
    """
    Execute OCR agent asynchronously.

    Submits task to Celery queue and returns task ID immediately.

    Args:
        request: Execution request

    Returns:
        Task ID and status
    """
    # Submit to Celery
    task = process_document_gpu.delay(
        document_id=request.document_id,
        file_path=request.file_path,
        backend=request.backend,
        priority=request.priority,
        options=request.options or {},
    )

    return {
        "status": "submitted",
        "task_id": task.id,
        "document_id": request.document_id,
        "backend": request.backend,
        "message": "OCR processing started",
    }


@router.post("/execute/batch")
async def execute_batch_processing(request: BatchProcessRequest):
    """
    Execute batch OCR processing.

    Args:
        request: Batch request

    Returns:
        Task ID
    """
    if len(request.document_ids) != len(request.file_paths):
        raise HTTPException(
            status_code=400,
            detail="document_ids and file_paths must have same length",
        )

    # Submit batch task
    task = batch_process_documents.delay(
        document_ids=request.document_ids,
        file_paths=request.file_paths,
        backend=request.backend,
        options=request.options or {},
    )

    return {
        "status": "submitted",
        "task_id": task.id,
        "batch_size": len(request.document_ids),
        "backend": request.backend,
    }


@router.post("/execute/workflow")
async def execute_workflow(request: WorkflowExecuteRequest):
    """
    Execute complete document processing workflow.

    Orchestrates:
    1. Classification
    2. Pre-Processing
    3. OCR
    4. Post-Processing
    5. QA
    6. Storage

    Args:
        request: Workflow request

    Returns:
        Task ID
    """
    # Submit workflow task
    task = process_document_workflow.delay(
        document_id=request.document_id,
        file_path=request.file_path,
        priority=request.priority,
        options=request.options or {},
    )

    return {
        "status": "submitted",
        "task_id": task.id,
        "document_id": request.document_id,
        "workflow": "full_processing",
    }


# =============================================================================
# TASK STATUS ENDPOINTS
# =============================================================================


@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    """
    Get task status and progress.

    Args:
        task_id: Celery task ID

    Returns:
        Task state, progress, and result
    """
    redis = await get_redis()

    # Get task state
    task_state = await redis.get_task_state(task_id)
    if not task_state:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    # Get progress
    progress = await redis.get_task_progress(task_id)

    return {
        "task_id": task_id,
        "state": task_state.get("state"),
        "progress": progress.get("progress", 0.0) if progress else 0.0,
        "message": progress.get("message") if progress else None,
        "updated_at": task_state.get("updated_at"),
        "data": task_state.get("data", {}),
    }


# =============================================================================
# BACKEND ROUTER ENDPOINTS
# =============================================================================


@router.post("/route/backend")
async def route_backend(
    document_metadata: Dict[str, Any],
    sla_requirements: Optional[Dict[str, Any]] = None,
):
    """
    Select optimal OCR backend for document.

    Args:
        document_metadata: Document characteristics
        sla_requirements: Optional SLA constraints

    Returns:
        Selected backend with reasoning
    """
    router_agent = OCRBackendRouter()

    result = await router_agent.execute(
        input_data={
            "document_metadata": document_metadata,
            "sla_requirements": sla_requirements or {},
        }
    )

    return {
        "backend": result["result"]["backend"],
        "reason": result["result"]["reason"],
        "confidence": result["result"]["confidence"],
        "alternatives": result["result"]["alternatives"],
    }


@router.get("/route/backends")
async def list_available_backends():
    """
    List all available OCR backends with capabilities.

    Returns:
        Backend information
    """
    router_agent = OCRBackendRouter()

    backends = ["deepseek", "got_ocr", "surya", "hybrid"]

    return {
        "backends": [
            {
                "name": backend,
                **router_agent.get_backend_info(backend),
            }
            for backend in backends
        ],
        "by_speed": router_agent.rank_backends_by_speed(),
        "by_accuracy": router_agent.rank_backends_by_accuracy(),
    }


# =============================================================================
# WORKFLOW STATE ENDPOINTS
# =============================================================================


@router.get("/workflow/{document_id}")
async def get_workflow_state(document_id: str):
    """
    Get workflow state for document.

    Args:
        document_id: Document ID

    Returns:
        Complete workflow state with all phases
    """
    redis = await get_redis()
    workflow_state = await redis.get_workflow_state(document_id)

    if not workflow_state:
        raise HTTPException(
            status_code=404,
            detail=f"No workflow found for document {document_id}",
        )

    return {
        "document_id": document_id,
        "workflow": workflow_state,
    }


@router.get("/workflow/{document_id}/{phase}")
async def get_workflow_phase(document_id: str, phase: str):
    """
    Get specific workflow phase state.

    Args:
        document_id: Document ID
        phase: Phase name (classification, preprocessing, ocr, etc.)

    Returns:
        Phase state
    """
    redis = await get_redis()
    phase_state = await redis.get_workflow_phase(document_id, phase)

    if not phase_state:
        raise HTTPException(
            status_code=404,
            detail=f"Phase {phase} not found for document {document_id}",
        )

    return {
        "document_id": document_id,
        "phase": phase,
        "state": phase_state,
    }


# =============================================================================
# AGENT CONFIGURATION
# =============================================================================


@router.get("/config")
async def get_agent_configuration():
    """
    Get current agent configuration.

    Returns:
        Configuration for all agents
    """
    return {
        "ocr_agents": {
            "deepseek": {
                "vram_required_gb": 12,
                "max_batch_size": 4,
                "gpu_required": True,
            },
            "got_ocr": {
                "vram_required_gb": 10,
                "max_batch_size": 8,
                "gpu_required": False,
            },
            "surya": {
                "vram_required_gb": 0,
                "max_batch_size": 1,
                "gpu_required": False,
            },
            "hybrid": {
                "vram_required_gb": 12,
                "max_batch_size": 4,
                "gpu_required": True,
            },
        },
        "workflow": {
            "phases": [
                "classification",
                "preprocessing",
                "ocr_processing",
                "postprocessing",
                "qa_check",
                "storing",
            ],
            "default_priority": 0,
            "max_retries": 3,
        },
    }
