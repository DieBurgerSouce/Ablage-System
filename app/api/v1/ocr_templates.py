# -*- coding: utf-8 -*-
"""
OCR Template Auto-Generation API.

Endpunkte für automatische Template-Erkennung und -Generierung.
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from app.core.safe_errors import safe_error_detail
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db, get_user_company_id_dep
from app.db.models import User
from app.services.ocr.auto_template_service import (
    AutoTemplateService,
    get_auto_template_service,
)

router = APIRouter(prefix="/ocr/templates", tags=["OCR Templates"])


# Schemas
class TemplateCandidateResponse(BaseModel):
    entity_id: str
    company_id: str
    document_count: int
    matching_fields: List[str]
    avg_position_variance: float
    is_candidate: bool
    document_ids: List[str]

    model_config = {"from_attributes": True}


class AutoGenerateRequest(BaseModel):
    entity_id: str = Field(..., description="Lieferanten-Entity-ID")
    document_ids: List[str] = Field(..., min_length=3, description="Dokument-IDs für Template-Generierung")
    name: Optional[str] = Field(None, description="Optionaler Template-Name")


class TemplateResponse(BaseModel):
    id: str
    entity_id: str
    name: str
    description: Optional[str]
    field_count: int
    training_document_count: int
    is_auto_generated: bool
    auto_confidence: Optional[float]
    is_active: bool
    is_verified: bool

    model_config = {"from_attributes": True}


@router.get("/candidates", response_model=List[TemplateCandidateResponse])
async def list_template_candidates(
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
    current_user: User = Depends(get_current_user),
):
    """Liste aller Template-Kandidaten (Lieferanten mit genug ähnlichen Dokumenten)."""
    service = get_auto_template_service()
    candidates = await service.list_candidates(db, company_id)
    return [
        TemplateCandidateResponse(
            entity_id=str(c.entity_id),
            company_id=str(c.company_id),
            document_count=c.document_count,
            matching_fields=c.matching_fields,
            avg_position_variance=c.avg_position_variance,
            is_candidate=c.is_candidate,
            document_ids=[str(d) for d in c.document_ids],
        )
        for c in candidates
    ]


@router.post("/auto-detect/{entity_id}", response_model=TemplateCandidateResponse)
async def detect_template_candidate(
    entity_id: UUID,
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
    current_user: User = Depends(get_current_user),
):
    """Prüfe ob ein Lieferant ein Template-Kandidat ist."""
    service = get_auto_template_service()
    candidate = await service.detect_template_candidate(db, entity_id, company_id)
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nicht genug Dokumente für Template-Erkennung",
        )
    return TemplateCandidateResponse(
        entity_id=str(candidate.entity_id),
        company_id=str(candidate.company_id),
        document_count=candidate.document_count,
        matching_fields=candidate.matching_fields,
        avg_position_variance=candidate.avg_position_variance,
        is_candidate=candidate.is_candidate,
        document_ids=[str(d) for d in candidate.document_ids],
    )


@router.post("/auto-generate", response_model=TemplateResponse)
async def auto_generate_template(
    request: AutoGenerateRequest,
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
    current_user: User = Depends(get_current_user),
):
    """Generiere automatisch ein Template aus ähnlichen Dokumenten."""
    service = get_auto_template_service()
    try:
        template = await service.generate_template(
            db=db,
            entity_id=UUID(request.entity_id),
            company_id=company_id,
            document_ids=[UUID(d) for d in request.document_ids],
            name=request.name,
        )
        await db.commit()
        return TemplateResponse(
            id=str(template.id),
            entity_id=str(template.entity_id),
            name=template.name,
            description=template.description,
            field_count=len(template.field_definitions or []),
            training_document_count=template.training_document_count,
            is_auto_generated=True,
            auto_confidence=template.auto_confidence,
            is_active=template.is_active,
            is_verified=template.is_verified,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "OCR-Vorlage"),
        )
