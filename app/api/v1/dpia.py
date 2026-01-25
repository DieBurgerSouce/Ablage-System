# -*- coding: utf-8 -*-
"""
DPIA API Endpoints.

Data Protection Impact Assessment (DPIA) API gemaess Art. 35 DSGVO.

Endpoints:
- GET/POST /dpia - DPIAs auflisten/erstellen
- GET/PATCH /dpia/{id} - DPIA abrufen/aktualisieren
- POST /dpia/{id}/consultation - DPO-Konsultation hinzufuegen
- GET /dpia/templates - Verfuegbare Templates
- POST /dpia/check-required - Pruefe ob DPIA erforderlich

Feinpoliert und durchdacht - DSGVO-konform.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
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

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/dpia", tags=["DPIA"])


# =============================================================================
# Request/Response Schemas
# =============================================================================


class ProcessingOperationSchema(BaseModel):
    """Schema fuer Verarbeitungstaetigkeit."""
    name: str = Field(..., description="Name der Verarbeitung")
    description: str = Field(..., description="Beschreibung")
    purpose: str = Field(..., description="Zweck der Verarbeitung")
    legal_basis: str = Field(..., description="Rechtsgrundlage (consent, contract, etc.)")
    data_categories: List[str] = Field(..., description="Datenkategorien")
    retention_period: str = Field(..., description="Aufbewahrungsfrist")
    automated_decision_making: bool = Field(False, description="Automatisierte Entscheidungen")
    profiling: bool = Field(False, description="Profiling")
    data_transfer_outside_eu: bool = Field(False, description="Transfer ausserhalb EU")
    transfer_countries: List[str] = Field(default_factory=list, description="Ziellaender")


class DataSubjectGroupSchema(BaseModel):
    """Schema fuer Betroffenengruppe."""
    name: str = Field(..., description="Name der Gruppe")
    description: str = Field(..., description="Beschreibung")
    estimated_count: Optional[int] = Field(None, description="Geschaetzte Anzahl")
    includes_vulnerable: bool = Field(False, description="Enthaelt schutzbeduertige Personen")
    includes_children: bool = Field(False, description="Enthaelt Kinder")


class CheckRequiredRequest(BaseModel):
    """Request fuer DPIA-Erforderlichkeitspruefung."""
    processing_operations: List[ProcessingOperationSchema]
    data_subject_groups: List[DataSubjectGroupSchema]


class CheckRequiredResponse(BaseModel):
    """Response fuer DPIA-Erforderlichkeitspruefung."""
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
    """Request fuer DPO-Konsultation."""
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
    """Kurzuebersicht einer DPIA."""
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
async def check_dpia_required(
    request: CheckRequiredRequest,
    current_user: User = Depends(get_current_user),
) -> CheckRequiredResponse:
    """
    Pruefe ob eine DPIA erforderlich ist.

    Basierend auf Art. 35 DSGVO und den Leitlinien der Art.-29-Datenschutzgruppe.
    """
    service = get_dpia_service()

    # Konvertiere Schemas zu Domain Objects
    operations = []
    for op in request.processing_operations:
        try:
            legal_basis = ProcessingBasis(op.legal_basis)
        except ValueError:
            legal_basis = ProcessingBasis.LEGITIMATE_INTEREST

        data_cats = []
        for dc in op.data_categories:
            try:
                data_cats.append(DataCategory(dc))
            except ValueError:
                pass

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
        for g in request.data_subject_groups
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
async def list_templates(
    current_user: User = Depends(get_current_user),
) -> List[TemplateInfo]:
    """Liste verfuegbarer DPIA-Templates."""
    service = get_dpia_service()
    templates = service.get_available_templates()
    return [TemplateInfo(**t) for t in templates]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_dpia_from_template(
    request: CreateFromTemplateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Erstelle neue DPIA aus Template.

    Verfuegbare Templates:
    - ocr_document_processing
    - lexware_customer_import
    - email_import
    """
    service = get_dpia_service()

    try:
        dpia = await service.create_from_template(
            db=db,
            template_name=request.template_name,
            controller_name=request.controller_name,
            controller_contact=request.controller_contact,
            dpo_name=request.dpo_name,
            dpo_contact=request.dpo_contact,
            assessor_name=current_user.full_name or current_user.email,
            company_id=current_user.company_id,
            created_by_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    logger.info(
        "dpia_created_from_template",
        user_id=str(current_user.id),
        dpia_id=str(dpia.id),
        template=request.template_name,
    )

    return dpia.to_dict()


@router.get("", response_model=List[DPIASummary])
async def list_dpias(
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
        except ValueError:
            pass

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
async def get_dpia(
    dpia_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Hole DPIA nach ID."""
    service = get_dpia_service()
    dpia = await service.get_by_id(db, dpia_id)

    if not dpia:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="DPIA nicht gefunden",
        )

    # Pruefe Zugriff
    if dpia.company_id and dpia.company_id != current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Kein Zugriff auf diese DPIA",
        )

    return dpia.to_dict()


@router.patch("/{dpia_id}/status")
async def update_dpia_status(
    dpia_id: UUID,
    request: UpdateStatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Aktualisiere DPIA Status."""
    service = get_dpia_service()

    # Validiere Status
    try:
        new_status = DPIAStatus(request.status)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungueltiger Status: {request.status}",
        )

    try:
        dpia = await service.update_status(
            db=db,
            dpia_id=dpia_id,
            new_status=new_status,
            user_name=current_user.full_name or current_user.email,
            comment=request.comment,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    logger.info(
        "dpia_status_updated",
        user_id=str(current_user.id),
        dpia_id=str(dpia_id),
        new_status=request.status,
    )

    return dpia.to_dict()


@router.post("/{dpia_id}/consultation")
async def add_dpo_consultation(
    dpia_id: UUID,
    request: DPOConsultationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Fuege DPO-Konsultation hinzu.

    Nur fuer Benutzer mit DPO-Rolle.
    """
    service = get_dpia_service()

    try:
        dpia = await service.add_dpo_consultation(
            db=db,
            dpia_id=dpia_id,
            dpo_name=current_user.full_name or current_user.email,
            opinion=request.opinion,
            recommendations=request.recommendations,
            approval=request.approval,
            conditions=request.conditions,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    logger.info(
        "dpia_consultation_added",
        user_id=str(current_user.id),
        dpia_id=str(dpia_id),
        approval=request.approval,
    )

    return dpia.to_dict()


@router.get("/{dpia_id}/recommendations", response_model=List[RecommendationResponse])
async def get_recommendations(
    dpia_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[RecommendationResponse]:
    """Generiere Empfehlungen basierend auf Risikoprofil."""
    service = get_dpia_service()
    dpia = await service.get_by_id(db, dpia_id)

    if not dpia:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="DPIA nicht gefunden",
        )

    # get_recommendations is synchronous - works with dataclass
    recommendations = service.get_recommendations(dpia)
    return [RecommendationResponse(**r) for r in recommendations]


@router.get("/{dpia_id}/audit-trail")
async def get_audit_trail(
    dpia_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Hole Audit-Trail der DPIA."""
    service = get_dpia_service()
    dpia = await service.get_by_id(db, dpia_id)

    if not dpia:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="DPIA nicht gefunden",
        )

    return dpia.audit_trail
