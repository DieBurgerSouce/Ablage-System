# -*- coding: utf-8 -*-
"""
Document Hints API Endpoints

Proaktive Dokument-Hinweise für bessere Benutzernavigation.
"""

from typing import List, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.db.models import User
from app.services.document_hints_service import (
    DocumentHintsService,
    get_document_hints_service,
    HintCategory,
    HintSeverity,
)
from app.core.safe_errors import safe_error_detail

router = APIRouter(prefix="/documents", tags=["Document Hints"])


# ==================== Schemas ====================


class DocumentHintSchema(BaseModel):
    """Schema für einen einzelnen Hint."""
    category: str = Field(..., description="Hint-Kategorie")
    severity: str = Field(..., description="Schweregrad (info, warning, critical)")
    title: str = Field(..., description="Kurzer Titel")
    message: str = Field(..., description="Beschreibung")
    action_label: str | None = Field(None, description="Label für Aktion")
    action_type: str | None = Field(None, description="Typ der Aktion")
    action_data: Dict[str, str] | None = Field(None, description="Daten für Aktion")
    confidence: float = Field(..., description="Konfidenz 0-1")
    expires_at: str | None = Field(None, description="Ablaufzeit (ISO)")


class DocumentHintsResponse(BaseModel):
    """Response für Dokument-Hints."""
    hints: List[DocumentHintSchema]
    total: int


class BatchHintsRequest(BaseModel):
    """Request für Batch-Hints."""
    document_ids: List[UUID] = Field(..., description="Liste von Dokument-IDs")


class BatchHintsResponse(BaseModel):
    """Response für Batch-Hints."""
    hints: Dict[str, List[DocumentHintSchema]]
    total: int


class HintSummarySchema(BaseModel):
    """Schema für Hint-Zusammenfassung."""
    by_category: Dict[str, int] = Field(..., description="Anzahl pro Kategorie")
    by_severity: Dict[str, int] = Field(..., description="Anzahl pro Schweregrad")
    total: int = Field(..., description="Gesamt-Anzahl")
    critical_count: int = Field(..., description="Anzahl kritischer Hints")


# ==================== Endpoints ====================


@router.get(
    "/{document_id}/hints",
    response_model=DocumentHintsResponse,
    summary="Hole Hints für Dokument",
    description="Gibt alle proaktiven Hinweise für ein Dokument zurück",
)
async def get_document_hints(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentHintsResponse:
    """
    Holt alle Hints für ein einzelnes Dokument.

    Args:
        document_id: Dokument-ID
        db: Datenbank-Session
        current_user: Aktueller Benutzer

    Returns:
        DocumentHintsResponse mit Liste von Hints

    Raises:
        HTTPException: Bei Fehler
    """
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Benutzer hat keine Firma zugeordnet")

    try:
        service = get_document_hints_service(db)
        hints = await service.get_hints_for_document(
            document_id=document_id,
            company_id=current_user.company_id,
        )

        hint_schemas = [
            DocumentHintSchema(
                category=h.category.value,
                severity=h.severity.value,
                title=h.title,
                message=h.message,
                action_label=h.action_label,
                action_type=h.action_type,
                action_data=h.action_data,
                confidence=h.confidence,
                expires_at=h.expires_at.isoformat() if h.expires_at else None,
            )
            for h in hints
        ]

        return DocumentHintsResponse(
            hints=hint_schemas,
            total=len(hint_schemas),
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=safe_error_detail(e, "Fehler beim Laden der Dokument-Hinweise"),
        )


@router.post(
    "/hints/batch",
    response_model=BatchHintsResponse,
    summary="Hole Hints für mehrere Dokumente",
    description="Gibt Hints für mehrere Dokumente in einer Batch-Operation zurück",
)
async def get_batch_document_hints(
    request: BatchHintsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BatchHintsResponse:
    """
    Holt Hints für mehrere Dokumente (Batch).

    Args:
        request: Batch-Request mit document_ids
        db: Datenbank-Session
        current_user: Aktueller Benutzer

    Returns:
        BatchHintsResponse mit Dictionary document_id -> Hints

    Raises:
        HTTPException: Bei Fehler
    """
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Benutzer hat keine Firma zugeordnet")

    try:
        service = get_document_hints_service(db)
        hints_dict = await service.get_hints_batch(
            document_ids=request.document_ids,
            company_id=current_user.company_id,
        )

        # Konvertiere zu Schemas
        result: Dict[str, List[DocumentHintSchema]] = {}
        total_count = 0

        for doc_id, hints in hints_dict.items():
            hint_schemas = [
                DocumentHintSchema(
                    category=h.category.value,
                    severity=h.severity.value,
                    title=h.title,
                    message=h.message,
                    action_label=h.action_label,
                    action_type=h.action_type,
                    action_data=h.action_data,
                    confidence=h.confidence,
                    expires_at=h.expires_at.isoformat() if h.expires_at else None,
                )
                for h in hints
            ]
            result[str(doc_id)] = hint_schemas
            total_count += len(hint_schemas)

        return BatchHintsResponse(
            hints=result,
            total=total_count,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=safe_error_detail(e, "Fehler beim Laden der Batch-Hinweise"),
        )


@router.get(
    "/hints/summary",
    response_model=HintSummarySchema,
    summary="Hole Hint-Zusammenfassung",
    description="Gibt eine Zusammenfassung aller Hints für das Dashboard zurück",
)
async def get_hints_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HintSummarySchema:
    """
    Holt Zusammenfassung aller Hints für Dashboard.

    Args:
        db: Datenbank-Session
        current_user: Aktueller Benutzer

    Returns:
        HintSummarySchema mit Statistiken

    Raises:
        HTTPException: Bei Fehler
    """
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Benutzer hat keine Firma zugeordnet")

    try:
        service = get_document_hints_service(db)
        summary = await service.get_hint_summary(company_id=current_user.company_id)

        return HintSummarySchema(
            by_category=summary.by_category,
            by_severity=summary.by_severity,
            total=summary.total,
            critical_count=summary.critical_count,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=safe_error_detail(e, "Fehler beim Laden der Hint-Zusammenfassung"),
        )
