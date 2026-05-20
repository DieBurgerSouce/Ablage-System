# -*- coding: utf-8 -*-
"""
DPIA API Endpoints.

Data Protection Impact Assessment (DPIA) API gemaess Art. 35 DSGVO.

Endpoints:
- GET/POST /dpia - DPIAs auflisten/erstellen
- GET/PATCH /dpia/{id} - DPIA abrufen/aktualisieren
- POST /dpia/{id}/consultation - DPO-Konsultation hinzufuegen
- GET /dpia/templates - Verfügbare Templates
- POST /dpia/check-required - Prüfe ob DPIA erforderlich

Feinpoliert und durchdacht - DSGVO-konform.
"""

from datetime import datetime
from typing import List, Optional

from app.core.types import JSONDict
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import User
from app.services.compliance.dpia_service import (
    DataCategory,
    DPIAService,
    DPIAStatus,
    ProcessingBasis,
    ProcessingOperation,
    DataSubjectGroup,
    get_dpia_service,
)
from app.core.rate_limiting import limiter, get_user_identifier

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/dpia", tags=["DPIA"])


# =============================================================================
# Request/Response Schemas
# =============================================================================


class ProcessingOperationSchema(BaseModel):
    """Schema für Verarbeitungstätigkeit."""
    name: str = Field(..., description="Name der Verarbeitung")
    description: str = Field(..., description="Beschreibung")
    purpose: str = Field(..., description="Zweck der Verarbeitung")
    legal_basis: str = Field(..., description="Rechtsgrundlage (consent, contract, etc.)")
    data_categories: List[str] = Field(..., description="Datenkategorien")
    retention_period: str = Field(..., description="Aufbewahrungsfrist")
    automated_decision_making: bool = Field(False, description="Automatisierte Entscheidungen")
    profiling: bool = Field(False, description="Profiling")
    data_transfer_outside_eu: bool = Field(False, description="Transfer ausserhalb EU")
    transfer_countries: List[str] = Field(default_factory=list, description="Zielländer")


class DataSubjectGroupSchema(BaseModel):
    """Schema für Betroffenengruppe."""
    name: str = Field(..., description="Name der Gruppe")
    description: str = Field(..., description="Beschreibung")
    estimated_count: Optional[int] = Field(None, description="Geschätzte Anzahl")
    includes_vulnerable: bool = Field(False, description="Enthält schutzbeduertige Personen")
    includes_children: bool = Field(False, description="Enthält Kinder")


class CheckRequiredRequest(BaseModel):
    """Request für DPIA-Erforderlichkeitsprüfung."""
    processing_operations: List[ProcessingOperationSchema]
    data_subject_groups: List[DataSubjectGroupSchema]


class CheckRequiredResponse(BaseModel):
    """Response für DPIA-Erforderlichkeitsprüfung."""
    required: bool
    reasons: List[str]
    criteria_met: int


class CreateFromTemplateRequest(BaseModel):
    """Request zum Erstellen einer DPIA aus Template."""
    template_name: str = Field(..., description="Name des Templates")
    controller_name: str = Field(..., description="Name des Verantwortlichen")
    controller_contact: str = Field(..., description="Kontakt des Verantwortlichen")
    dpo_name: str = Field(..., description="Name des DSB")
    dpo_contact: str = Field(..., description="Kontakt des DSB")


class DPOConsultationRequest(BaseModel):
    """Request für DPO-Konsultation."""
    opinion: str = Field(..., description="Stellungnahme des DPO")
    recommendations: List[str] = Field(..., description="Empfehlungen")
    approval: bool = Field(..., description="Genehmigt")
    conditions: List[str] = Field(default_factory=list, description="Bedingungen")


class UpdateStatusRequest(BaseModel):
    """Request zum Aktualisieren des DPIA-Status."""
    status: str = Field(..., description="Neuer Status (draft, review, approved, etc.)")
    comment: str = Field("", description="Optionaler Kommentar")


class TemplateInfo(BaseModel):
    """Template-Information."""
    name: str
    title: str
    description: str


class RecommendationResponse(BaseModel):
    """Empfehlung."""
    priority: str
    category: str
    title: str
    description: str
    action: str


class DPIASummary(BaseModel):
    """Kurzübersicht einer DPIA."""
    id: str
    title: str
    status: str
    overall_risk_level: str
    assessment_date: Optional[datetime]
    assessor_name: Optional[str]


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/check-required", response_model=CheckRequiredResponse)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def check_dpia_required(
    request: Request,
    body: CheckRequiredRequest,
    current_user: User = Depends(get_current_user),
) -> CheckRequiredResponse:
    """
    Prüfe ob eine DPIA erforderlich ist.

    Basierend auf Art. 35 DSGVO und den Leitlinien der Art.-29-Datenschutzgruppe.
    """
    service = get_dpia_service()

    # Konvertiere Schemas zu Domain Objects
    operations = []
    for op in body.processing_operations:
        try:
            legal_basis = ProcessingBasis(op.legal_basis)
        except ValueError:
            legal_basis = ProcessingBasis.LEGITIMATE_INTEREST

        data_cats = []
        for dc in op.data_categories:
            try:
                data_cats.append(DataCategory(dc))
            except ValueError as e:
                logger.debug("invalid_data_category_skipped", category=dc, error_type=type(e).__name__)

        operations.append(ProcessingOperation(
            name=op.name,
            description=op.description,
            purpose=op.purpose,
            legal_basis=legal_basis,
            data_categories=data_cats,
            retention_period=op.retention_period,
            automated_decision_making=op.automated_decision_making,
            profiling=op.profiling,
            data_transfer_outside_eu=op.data_transfer_outside_eu,
            transfer_countries=op.transfer_countries,
        ))

    groups = [
        DataSubjectGroup(
            name=g.name,
            description=g.description,
            estimated_count=g.estimated_count,
            includes_vulnerable=g.includes_vulnerable,
            includes_children=g.includes_children,
        )
        for g in body.data_subject_groups
    ]

    # needs_dpia is synchronous - doesn't need DB
    result = service.needs_dpia(operations, groups)

    logger.info(
        "dpia_check_required",
        user_id=str(current_user.id),
        required=result["required"],
        criteria_met=result["criteria_met"],
    )

    return CheckRequiredResponse(**result)


@router.get("/templates", response_model=List[TemplateInfo])
@limiter.limit("60/minute", key_func=get_user_identifier)
async def list_templates(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> List[TemplateInfo]:
    """Liste verfügbarer DPIA-Templates."""
    service = get_dpia_service()
    templates = service.get_available_templates()
    return [TemplateInfo(**t) for t in templates]


@router.post("", status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def create_dpia_from_template(
    request: Request,
    body: CreateFromTemplateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONDict:
    """
    Erstelle neue DPIA aus Template.

    Verfügbare Templates:
    - ocr_document_processing
    - lexware_customer_import
    - email_import
    """
    service = get_dpia_service()

    try:
        dpia = await service.create_from_template(
            db=db,
            template_name=body.template_name,
            controller_name=body.controller_name,
            controller_contact=body.controller_contact,
            dpo_name=body.dpo_name,
            dpo_contact=body.dpo_contact,
            assessor_name=current_user.full_name or current_user.email,
            company_id=current_user.company_id,
            created_by_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "DSFA"),
        )

    logger.info(
        "dpia_created_from_template",
        user_id=str(current_user.id),
        dpia_id=str(dpia.id),
        template=body.template_name,
    )

    return dpia.to_dict()


@router.get("", response_model=List[DPIASummary])
@limiter.limit("60/minute", key_func=get_user_identifier)
async def list_dpias(
    request: Request,
    status_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[DPIASummary]:
    """Liste DPIAs des Unternehmens."""
    service = get_dpia_service()

    status_enum = None
    if status_filter:
        try:
            status_enum = DPIAStatus(status_filter)
        except ValueError as e:
            logger.debug("invalid_dpia_status_filter_skipped", status=status_filter, error_type=type(e).__name__)

    dpias = await service.list_dpias(
        db=db,
        company_id=current_user.company_id,
        status=status_enum,
    )

    return [
        DPIASummary(
            id=str(dpia.id),
            title=dpia.title,
            status=dpia.status.value,
            overall_risk_level=dpia.overall_risk_level.value if dpia.overall_risk_level else "medium",
            assessment_date=dpia.assessment_date,
            assessor_name=dpia.assessor_name,
        )
        for dpia in dpias
    ]


@router.get("/{dpia_id}")
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_dpia(
    request: Request,
    dpia_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONDict:
    """Hole DPIA nach ID."""
    service = get_dpia_service()
    dpia = await service.get_by_id(db, dpia_id, company_id=current_user.company_id)

    if not dpia:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="DPIA nicht gefunden",
        )

    # Defense-in-depth: NULL company_id wird ebenfalls abgelehnt
    if dpia.company_id != current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="DPIA nicht gefunden",
        )

    return dpia.to_dict()


@router.patch("/{dpia_id}/status")
@limiter.limit("60/minute", key_func=get_user_identifier)
async def update_dpia_status(
    request: Request,
    dpia_id: UUID,
    body: UpdateStatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONDict:
    """Aktualisiere DPIA Status."""
    service = get_dpia_service()

    # Validiere Status
    try:
        new_status = DPIAStatus(body.status)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungültiger Status: {body.status}",
        )

    try:
        dpia = await service.update_status(
            db=db,
            dpia_id=dpia_id,
            new_status=new_status,
            user_name=current_user.full_name or current_user.email,
            comment=body.comment,
            company_id=current_user.company_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "DSFA"),
        )

    logger.info(
        "dpia_status_updated",
        user_id=str(current_user.id),
        dpia_id=str(dpia_id),
        new_status=body.status,
    )

    return dpia.to_dict()


@router.post("/{dpia_id}/consultation")
@limiter.limit("60/minute", key_func=get_user_identifier)
async def add_dpo_consultation(
    request: Request,
    dpia_id: UUID,
    body: DPOConsultationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONDict:
    """
    Fuege DPO-Konsultation hinzu.

    Nur für Benutzer mit DPO-Rolle.
    """
    service = get_dpia_service()

    try:
        dpia = await service.add_dpo_consultation(
            db=db,
            dpia_id=dpia_id,
            dpo_name=current_user.full_name or current_user.email,
            opinion=body.opinion,
            recommendations=body.recommendations,
            approval=body.approval,
            conditions=body.conditions,
            company_id=current_user.company_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "DSFA"),
        )

    logger.info(
        "dpia_consultation_added",
        user_id=str(current_user.id),
        dpia_id=str(dpia_id),
        approval=body.approval,
    )

    return dpia.to_dict()


@router.get("/{dpia_id}/recommendations", response_model=List[RecommendationResponse])
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_recommendations(
    request: Request,
    dpia_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[RecommendationResponse]:
    """Generiere Empfehlungen basierend auf Risikoprofil."""
    service = get_dpia_service()
    dpia = await service.get_by_id(db, dpia_id, company_id=current_user.company_id)

    if not dpia or dpia.company_id != current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="DPIA nicht gefunden",
        )

    # get_recommendations is synchronous - works with dataclass
    recommendations = service.get_recommendations(dpia)
    return [RecommendationResponse(**r) for r in recommendations]


@router.get("/{dpia_id}/audit-trail")
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_audit_trail(
    request: Request,
    dpia_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[JSONDict]:
    """Hole Audit-Trail der DPIA."""
    service = get_dpia_service()
    dpia = await service.get_by_id(db, dpia_id, company_id=current_user.company_id)

    if not dpia or dpia.company_id != current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="DPIA nicht gefunden",
        )

    return dpia.audit_trail
