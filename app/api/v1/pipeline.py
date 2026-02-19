# -*- coding: utf-8 -*-
"""
Pipeline API Endpoints.

REST API fuer die Document Processing Pipeline:
- Manuelle Pipeline-Auslosung fuer ein Dokument (POST /pipeline/process/{document_id})
- Pipeline-Status-Abfrage fuer ein Dokument (GET /pipeline/status/{document_id})

Feinpoliert und durchdacht - Deutsche Praezision.
"""

import structlog
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.core.rate_limiting import limiter, get_user_identifier
from app.core.safe_errors import safe_error_log
from app.db.models import Document, User

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/pipeline", tags=["Pipeline"])


# =============================================================================
# SCHEMAS
# =============================================================================


class PipelineTriggerResponse(BaseModel):
    """Antwort nach dem Ausloesen der Pipeline."""

    model_config = ConfigDict(from_attributes=True)

    document_id: str
    task_id: str
    nachricht: str


class PipelineStatusResponse(BaseModel):
    """Pipeline-Status fuer ein Dokument."""

    model_config = ConfigDict(from_attributes=True)

    document_id: str
    pipeline_status: Optional[str] = None
    pipeline_results: Optional[Dict[str, Any]] = None
    verfuegbar: bool


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.post(
    "/process/{document_id}",
    response_model=PipelineTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Pipeline fuer Dokument ausloesen",
    description=(
        "Loest die Verarbeitungspipeline fuer ein Dokument manuell aus. "
        "Die Verarbeitung erfolgt asynchron via Celery. "
        "Der zurueckgegebene task_id kann zur Statusverfolgung genutzt werden."
    ),
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def trigger_document_pipeline(
    request: Request,
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PipelineTriggerResponse:
    """Pipeline fuer ein Dokument manuell ausloesen."""
    from app.workers.pipeline_tasks import process_document_pipeline

    company_id = current_user.company_id

    if company_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer ist keiner Firma zugeordnet",
        )

    # Dokument pruefen und Multi-Tenant-Isolation sicherstellen
    result = await db.execute(
        select(Document).where(
            and_(
                Document.id == document_id,
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
            )
        )
    )
    document = result.scalar_one_or_none()

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden",
        )

    try:
        task = process_document_pipeline.delay(
            document_id=str(document_id),
            company_id=str(company_id),
            user_id=str(current_user.id),
        )

        logger.info(
            "pipeline_api_triggered",
            document_id=str(document_id),
            company_id=str(company_id),
            user_id=str(current_user.id),
            task_id=task.id,
        )

        return PipelineTriggerResponse(
            document_id=str(document_id),
            task_id=task.id,
            nachricht="Pipeline-Verarbeitung wurde gestartet.",
        )

    except Exception as exc:
        logger.error(
            "pipeline_api_trigger_failed",
            document_id=str(document_id),
            company_id=str(company_id),
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Pipeline konnte nicht gestartet werden",
        )


@router.get(
    "/status/{document_id}",
    response_model=PipelineStatusResponse,
    summary="Pipeline-Status fuer Dokument abrufen",
    description=(
        "Gibt den aktuellen Pipeline-Status aus den Dokument-Metadaten zurueck. "
        "Der Status wird von der Pipeline selbst in das JSONB-Feld document_metadata "
        "geschrieben und hier ausgelesen."
    ),
)
async def get_pipeline_status(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PipelineStatusResponse:
    """Pipeline-Status fuer ein Dokument aus den Metadaten auslesen."""
    company_id = current_user.company_id

    if company_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer ist keiner Firma zugeordnet",
        )

    try:
        result = await db.execute(
            select(Document).where(
                and_(
                    Document.id == document_id,
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                )
            )
        )
        document = result.scalar_one_or_none()

        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dokument nicht gefunden",
            )

        # Pipeline-Ergebnisse aus document_metadata JSONB auslesen
        metadata: Dict[str, Any] = document.document_metadata or {}
        pipeline_data: Optional[Dict[str, Any]] = metadata.get("pipeline")

        pipeline_status: Optional[str] = None
        pipeline_results: Optional[Dict[str, Any]] = None

        if pipeline_data:
            pipeline_status = pipeline_data.get("status")
            pipeline_results = pipeline_data

        logger.debug(
            "pipeline_api_status_fetched",
            document_id=str(document_id),
            company_id=str(company_id),
            pipeline_status=pipeline_status,
        )

        return PipelineStatusResponse(
            document_id=str(document_id),
            pipeline_status=pipeline_status,
            pipeline_results=pipeline_results,
            verfuegbar=pipeline_data is not None,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "pipeline_api_status_failed",
            document_id=str(document_id),
            company_id=str(company_id),
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Pipeline-Status konnte nicht abgerufen werden",
        )
