# -*- coding: utf-8 -*-
"""
Review Queue API - Dokumente mit unsicherer Auto-Zuordnung.

Endpunkte fuer:
- GET /review-queue - Liste aller Dokumente die Review brauchen
- POST /documents/{id}/confirm-filing - Zuordnung bestaetigen/korrigieren

Pipeline-Integration: Liest ai_metadata.pipeline_result.requires_review
"""

from __future__ import annotations

from typing import Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, and_, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db, get_user_company_id_dep
from app.core.safe_errors import safe_error_log
from app.db.models import Document, User

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Review Queue"])


# =============================================================================
# Schemas
# =============================================================================

class ReviewQueueItem(BaseModel):
    """Ein Dokument in der Review-Queue."""

    document_id: str
    filename: str
    document_type: Optional[str] = None
    suggested_category: Optional[str] = None
    suggested_entity_id: Optional[str] = None
    suggested_entity_name: Optional[str] = None
    suggested_project_id: Optional[str] = None
    suggested_project_name: Optional[str] = None
    confidence: float = 0.0
    review_reasons: List[str] = Field(default_factory=list)
    created_at: str
    pipeline_status: str = "requires_review"


class ReviewQueueResponse(BaseModel):
    """Antwort fuer Review-Queue."""

    items: List[ReviewQueueItem]
    total: int
    page: int
    page_size: int


class ConfirmFilingRequest(BaseModel):
    """Request fuer Zuordnungs-Bestaetigung."""

    category: Optional[str] = None
    entity_id: Optional[str] = None
    project_id: Optional[str] = None
    is_correction: bool = False


class ConfirmFilingResponse(BaseModel):
    """Antwort fuer Zuordnungs-Bestaetigung."""

    document_id: str
    status: str
    applied_category: Optional[str] = None
    applied_entity_id: Optional[str] = None
    applied_project_id: Optional[str] = None
    correction_recorded: bool = False


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/review-queue", response_model=ReviewQueueResponse)
async def get_review_queue(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> ReviewQueueResponse:
    """
    Holt alle Dokumente die Review brauchen.

    Filtert nach ai_metadata->pipeline_result->requires_review = true.
    """

    try:
        # Count total
        count_stmt = (
            select(func.count())
            .select_from(Document)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.ai_metadata.isnot(None),
                    text(
                        "ai_metadata->'pipeline_result'->>'requires_review' = 'true'"
                    ),
                    text(
                        "COALESCE(ai_metadata->'pipeline_result'->>'review_confirmed', 'false') = 'false'"
                    ),
                )
            )
        )
        count_result = await db.execute(count_stmt)
        total = count_result.scalar() or 0

        # Fetch items
        offset = (page - 1) * page_size
        stmt = (
            select(Document)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.ai_metadata.isnot(None),
                    text(
                        "ai_metadata->'pipeline_result'->>'requires_review' = 'true'"
                    ),
                    text(
                        "COALESCE(ai_metadata->'pipeline_result'->>'review_confirmed', 'false') = 'false'"
                    ),
                )
            )
            .order_by(Document.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )

        result = await db.execute(stmt)
        documents = result.scalars().all()

        items: List[ReviewQueueItem] = []
        for doc in documents:
            pipeline_result: Dict[str, object] = (
                (doc.ai_metadata or {}).get("pipeline_result") or {}
            )
            category_info: Dict[str, object] = (
                pipeline_result.get("category") or {}
            )
            entity_info: Dict[str, object] = (
                pipeline_result.get("linked_entity") or {}
            )
            project_info: Dict[str, object] = (
                pipeline_result.get("assigned_project") or {}
            )

            raw_confidence = category_info.get("confidence", 0.0)
            confidence = float(raw_confidence) if raw_confidence is not None else 0.0

            raw_reasons = pipeline_result.get("review_reasons", [])
            review_reasons: List[str] = (
                list(raw_reasons) if isinstance(raw_reasons, (list, tuple)) else []
            )

            items.append(
                ReviewQueueItem(
                    document_id=str(doc.id),
                    filename=doc.filename or "Unbenannt",
                    document_type=str(pipeline_result.get("document_type") or ""),
                    suggested_category=str(category_info.get("name") or "") or None,
                    suggested_entity_id=str(entity_info.get("id") or "") or None,
                    suggested_entity_name=str(entity_info.get("name") or "") or None,
                    suggested_project_id=str(project_info.get("id") or "") or None,
                    suggested_project_name=str(project_info.get("name") or "") or None,
                    confidence=confidence,
                    review_reasons=review_reasons,
                    created_at=doc.created_at.isoformat() if doc.created_at else "",
                    pipeline_status=str(
                        pipeline_result.get("status") or "requires_review"
                    ),
                )
            )

        return ReviewQueueResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    except Exception as e:
        logger.error("review_queue_fetch_error", **safe_error_log(e))
        raise HTTPException(
            status_code=500,
            detail="Fehler beim Laden der Review-Queue",
        )


@router.post(
    "/documents/{document_id}/confirm-filing",
    response_model=ConfirmFilingResponse,
)
async def confirm_filing(
    document_id: UUID,
    request: ConfirmFilingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> ConfirmFilingResponse:
    """
    Bestaetigt oder korrigiert die Auto-Zuordnung eines Dokuments.

    Bei Korrektur werden die Daten fuer die OCR-Learning-Pipeline gespeichert.
    """
    # Dokument laden
    stmt = select(Document).where(
        and_(
            Document.id == document_id,
            Document.company_id == company_id,
        )
    )
    result = await db.execute(stmt)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")

    try:
        # Zuordnung anwenden
        applied_category: Optional[str] = None
        applied_entity_id: Optional[str] = None
        applied_project_id: Optional[str] = None

        if request.category:
            if hasattr(document, "category"):
                document.category = request.category
            applied_category = request.category

        if request.entity_id:
            if hasattr(document, "entity_id"):
                document.entity_id = UUID(request.entity_id)
            applied_entity_id = request.entity_id

        if request.project_id:
            if hasattr(document, "project_id"):
                document.project_id = UUID(request.project_id)
            applied_project_id = request.project_id

        # Pipeline-Result als bestaetigt markieren
        ai_metadata: Dict[str, object] = document.ai_metadata or {}
        pipeline_result: Dict[str, object] = ai_metadata.get("pipeline_result") or {}
        if isinstance(pipeline_result, dict):
            pipeline_result["review_confirmed"] = True
            pipeline_result["confirmed_by"] = str(current_user.id)
            pipeline_result["is_correction"] = request.is_correction
        ai_metadata["pipeline_result"] = pipeline_result
        document.ai_metadata = ai_metadata

        # Bei Korrektur: Daten fuer OCR-Learning speichern (best-effort)
        correction_recorded = False
        if request.is_correction:
            try:
                from app.services.ocr.self_learning_service import (
                    get_self_learning_service,
                    CorrectionFeedback,
                )

                original_category = pipeline_result.get("category") or {}
                original_value = (
                    str(original_category.get("name") or "")
                    if isinstance(original_category, dict)
                    else ""
                )

                original_confidence_raw = (
                    original_category.get("confidence", 0.0)
                    if isinstance(original_category, dict)
                    else 0.0
                )
                original_confidence = (
                    float(original_confidence_raw)
                    if original_confidence_raw is not None
                    else 0.0
                )

                feedback = CorrectionFeedback(
                    document_id=document_id,
                    field_name="category",
                    original_value=original_value,
                    corrected_value=request.category or "",
                    ocr_backend="pipeline",
                    original_confidence=original_confidence,
                    user_id=current_user.id,
                    correction_type="text",
                )
                learning_service = get_self_learning_service(db=db)
                await learning_service.process_correction(feedback=feedback)
                correction_recorded = True
            except Exception as learn_err:
                logger.warning(
                    "correction_learning_failed",
                    document_id=str(document_id),
                    **safe_error_log(learn_err),
                )

        await db.commit()

        logger.info(
            "filing_confirmed",
            document_id=str(document_id),
            is_correction=request.is_correction,
            confirmed_by=str(current_user.id),
        )

        return ConfirmFilingResponse(
            document_id=str(document_id),
            status="bestaetigt",
            applied_category=applied_category,
            applied_entity_id=applied_entity_id,
            applied_project_id=applied_project_id,
            correction_recorded=correction_recorded,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "filing_confirmation_error",
            document_id=str(document_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=500,
            detail="Fehler bei der Zuordnungs-Bestaetigung",
        )
