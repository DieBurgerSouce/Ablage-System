# -*- coding: utf-8 -*-
"""
Smart Tagging API - Intelligente automatische Dokumenten-Tags.

Vision 2026+ Feature #5: Smart Auto-Tagging
Analysiert Dokumente und schlaegt passende Tags vor oder wendet sie an.
"""

from typing import Dict, List, Optional
from uuid import UUID

from app.core.types import JSONDict

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.dependencies import get_db, get_current_user
from app.db.models import Document, User
from app.middleware.company_context import require_company, get_current_company
from app.services.ai.smart_tagging_service import (
    get_smart_tagging_service,
    SmartTag,
    SmartTaggingResult,
    TagCategory,
    SMART_TAG_DEFINITIONS,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/smart-tagging", tags=["smart-tagging"])


# =============================================================================
# Pydantic Schemas
# =============================================================================

class SmartTagSchema(BaseModel):
    """Schema fuer einen Smart Tag."""
    name: str = Field(..., description="Eindeutiger Tag-Name")
    display_name: str = Field(..., description="Deutscher Anzeigename")
    category: str = Field(..., description="Tag-Kategorie (urgency, financial, quality, action, trust)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Konfidenz der Erkennung")
    reason: str = Field(..., description="Deutsche Erklaerung warum der Tag vorgeschlagen wird")
    icon: str = Field(default="Tag", description="Lucide Icon Name")
    color: str = Field(default="gray", description="Tailwind Farbklasse")
    priority: int = Field(default=0, description="Anzeigepriorität (höher = wichtiger)")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "dringend",
                "display_name": "Dringend",
                "category": "urgency",
                "confidence": 0.92,
                "reason": "Zahlungsfrist in 3 Tagen",
                "icon": "AlertTriangle",
                "color": "red",
                "priority": 100,
            }
        }


class SmartTaggingResultSchema(BaseModel):
    """Schema fuer das Ergebnis einer Smart-Tagging-Analyse."""
    document_id: UUID
    suggested_tags: List[SmartTagSchema] = Field(default_factory=list)
    applied_tags: List[str] = Field(default_factory=list)
    skipped_tags: List[str] = Field(default_factory=list)
    analysis_metadata: JSONDict = Field(default_factory=dict)


class SmartTagDefinitionSchema(BaseModel):
    """Schema fuer eine Smart Tag Definition."""
    name: str
    display_name: str
    category: str
    icon: str
    color: str
    priority: int


class AnalyzeRequest(BaseModel):
    """Request Schema fuer Batch-Analyse."""
    document_ids: List[UUID] = Field(..., min_length=1, max_length=50)
    auto_apply: bool = Field(default=True, description="Ob Tags automatisch angewendet werden sollen")
    min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class AnalyzeResponse(BaseModel):
    """Response Schema fuer Batch-Analyse."""
    results: List[SmartTaggingResultSchema]
    total_processed: int
    total_tags_applied: int
    total_tags_suggested: int


# =============================================================================
# Endpoints
# =============================================================================

@router.post(
    "/analyze/{document_id}",
    response_model=SmartTaggingResultSchema,
    summary="Analysiert ein Dokument und schlaegt Smart Tags vor",
    description="""
    Analysiert ein einzelnes Dokument auf verschiedene Kriterien:

    - **Urgency**: Fristen, Dringlichkeit (dringend, ueberfaellig, frist-diese-woche)
    - **Financial**: Betraege, Skonto (skonto-moeglich, hoher-betrag)
    - **Quality**: OCR-Qualitaet, Duplikate (ocr-unsicher, duplikat-moeglich)
    - **Action**: Erforderliche Aktionen (genehmigung-erforderlich, mahnung-faellig)
    - **Trust**: Entity-Vertrauen (neuer-lieferant, bekannter-partner, risiko-partner)

    Bei aktiviertem `auto_apply` werden Tags mit hoher Konfidenz automatisch zugewiesen.
    """,
)
async def analyze_document(
    document_id: UUID,
    auto_apply: bool = Query(default=True, description="Ob Tags automatisch angewendet werden sollen"),
    min_confidence: float = Query(default=0.5, ge=0.0, le=1.0, description="Minimale Konfidenz fuer Vorschlaege"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(require_company),
) -> SmartTaggingResultSchema:
    """Analysiert ein Dokument und schlaegt Smart Tags vor."""
    # Lade Dokument mit Company-Check
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.company_id == company_id,
            Document.deleted_at.is_(None),
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden",
        )

    # Analysiere Dokument
    service = get_smart_tagging_service()
    tagging_result = await service.analyze_document(
        db=db,
        document=document,
        auto_apply=auto_apply,
        min_confidence=min_confidence,
    )

    logger.info(
        "smart_tagging_analyzed",
        document_id=str(document_id),
        user_id=str(current_user.id),
        tags_suggested=len(tagging_result.suggested_tags),
        tags_applied=len(tagging_result.applied_tags),
    )

    return SmartTaggingResultSchema(
        document_id=tagging_result.document_id,
        suggested_tags=[
            SmartTagSchema(
                name=t.name,
                display_name=t.display_name,
                category=t.category,
                confidence=t.confidence,
                reason=t.reason,
                icon=t.icon,
                color=t.color,
                priority=t.priority,
            )
            for t in tagging_result.suggested_tags
        ],
        applied_tags=tagging_result.applied_tags,
        skipped_tags=tagging_result.skipped_tags,
        analysis_metadata=tagging_result.analysis_metadata,
    )


@router.post(
    "/analyze/batch",
    response_model=AnalyzeResponse,
    summary="Analysiert mehrere Dokumente auf Smart Tags",
)
async def analyze_batch(
    request: AnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(require_company),
) -> AnalyzeResponse:
    """Analysiert mehrere Dokumente und schlaegt Smart Tags vor."""
    service = get_smart_tagging_service()
    results: List[SmartTaggingResultSchema] = []
    total_applied = 0
    total_suggested = 0

    for doc_id in request.document_ids:
        # Lade Dokument mit Company-Check
        doc_result = await db.execute(
            select(Document).where(
                Document.id == doc_id,
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
            )
        )
        document = doc_result.scalar_one_or_none()

        if not document:
            continue

        # Analysiere
        tagging_result = await service.analyze_document(
            db=db,
            document=document,
            auto_apply=request.auto_apply,
            min_confidence=request.min_confidence,
        )

        results.append(SmartTaggingResultSchema(
            document_id=tagging_result.document_id,
            suggested_tags=[
                SmartTagSchema(
                    name=t.name,
                    display_name=t.display_name,
                    category=t.category,
                    confidence=t.confidence,
                    reason=t.reason,
                    icon=t.icon,
                    color=t.color,
                    priority=t.priority,
                )
                for t in tagging_result.suggested_tags
            ],
            applied_tags=tagging_result.applied_tags,
            skipped_tags=tagging_result.skipped_tags,
            analysis_metadata=tagging_result.analysis_metadata,
        ))

        total_applied += len(tagging_result.applied_tags)
        total_suggested += len(tagging_result.suggested_tags)

    logger.info(
        "smart_tagging_batch_complete",
        user_id=str(current_user.id),
        documents_processed=len(results),
        total_applied=total_applied,
        total_suggested=total_suggested,
    )

    return AnalyzeResponse(
        results=results,
        total_processed=len(results),
        total_tags_applied=total_applied,
        total_tags_suggested=total_suggested,
    )


@router.get(
    "/suggestions/{document_id}",
    response_model=List[SmartTagSchema],
    summary="Gibt Tag-Vorschlaege fuer ein Dokument zurueck ohne sie anzuwenden",
)
async def get_suggestions(
    document_id: UUID,
    min_confidence: float = Query(default=0.5, ge=0.0, le=1.0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(require_company),
) -> List[SmartTagSchema]:
    """Gibt Tag-Vorschlaege zurueck ohne sie anzuwenden."""
    # Lade Dokument mit Company-Check
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.company_id == company_id,
            Document.deleted_at.is_(None),
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden",
        )

    service = get_smart_tagging_service()
    suggestions = await service.get_tag_suggestions(
        db=db,
        document_id=document_id,
        min_confidence=min_confidence,
    )

    return [SmartTagSchema(**s) for s in suggestions]


@router.get(
    "/definitions",
    response_model=List[SmartTagDefinitionSchema],
    summary="Gibt alle verfuegbaren Smart Tag Definitionen zurueck",
)
async def get_definitions(
    category: Optional[str] = Query(default=None, description="Filter nach Kategorie"),
) -> List[SmartTagDefinitionSchema]:
    """Gibt alle Smart Tag Definitionen zurueck."""
    definitions = SMART_TAG_DEFINITIONS

    if category:
        definitions = [d for d in definitions if d["category"] == category]

    return [
        SmartTagDefinitionSchema(
            name=d["name"],
            display_name=d["display_name"],
            category=d["category"],
            icon=d["icon"],
            color=d["color"],
            priority=d["priority"],
        )
        for d in definitions
    ]


@router.get(
    "/categories",
    response_model=Dict[str, str],
    summary="Gibt alle Tag-Kategorien zurueck",
)
async def get_categories() -> Dict[str, str]:
    """Gibt alle verfuegbaren Tag-Kategorien mit Beschreibung zurueck."""
    return {
        TagCategory.URGENCY: "Dringlichkeit und Fristen",
        TagCategory.FINANCIAL: "Finanzielle Aspekte (Betraege, Skonto)",
        TagCategory.QUALITY: "Qualitaet und Vollstaendigkeit",
        TagCategory.ACTION: "Erforderliche Aktionen",
        TagCategory.TRUST: "Vertrauenswuerdigkeit des Partners",
    }
