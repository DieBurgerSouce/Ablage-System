# -*- coding: utf-8 -*-
"""
Consent Management API Endpoints.

Endpoints fuer Einwilligungsverwaltung nach DSGVO:
- Einwilligungen erstellen, erteilen, widerrufen
- Auftragsverarbeitungsvertraege (AVV)
- Aufbewahrungsrichtlinien
- Audit-Trail

Vision 2.0 Feature: Datenschutz-by-Design
Feinpoliert und durchdacht.
"""

from datetime import datetime, date
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_active_user
from app.middleware.company_context import require_company
from app.db.models import User, Company
from app.db.models_consent import (
    ConsentRecord,
    DataProcessingAgreement,
    ConsentAuditLog,
    RetentionPolicy,
    ConsentStatus,
    ConsentType,
    ConsentSource,
    LegalBasis,
)
from app.services.privacy.consent_service import ConsentService

import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/consent", tags=["Consent Management"])


# =============================================================================
# Request/Response Schemas
# =============================================================================

class ConsentRequestCreate(BaseModel):
    """Schema fuer Einwilligungsanfrage."""
    consent_type: str = Field(..., description="Typ der Einwilligung")
    entity_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    grantor_name: Optional[str] = Field(None, max_length=200)
    grantor_email: Optional[EmailStr] = None
    scope: Optional[dict] = None
    expires_at: Optional[datetime] = None
    source: str = Field(default="web_form")


class ConsentGrantRequest(BaseModel):
    """Schema fuer Einwilligungserteilung."""
    grantor_name: Optional[str] = Field(None, max_length=200)
    grantor_role: Optional[str] = Field(None, max_length=100)
    conditions: Optional[str] = None
    restrictions: Optional[List[str]] = None
    document_id: Optional[UUID] = None
    document_reference: Optional[str] = Field(None, max_length=255)


class ConsentWithdrawRequest(BaseModel):
    """Schema fuer Einwilligungswiderruf."""
    reason: Optional[str] = Field(None, max_length=500)
    method: Optional[str] = Field(None, max_length=50)


class ConsentResponse(BaseModel):
    """Schema fuer Einwilligungs-Antwort."""
    id: UUID
    entity_id: Optional[UUID]
    user_id: Optional[UUID]
    consent_type: str
    status: str
    legal_basis: str
    grantor_name: Optional[str]
    grantor_role: Optional[str]
    grantor_email: Optional[str]
    requested_at: Optional[datetime]
    granted_at: Optional[datetime]
    denied_at: Optional[datetime]
    withdrawn_at: Optional[datetime]
    expires_at: Optional[datetime]
    source: str
    document_reference: Optional[str]
    document_id: Optional[UUID]
    scope: dict
    conditions: Optional[str]
    restrictions: List[str]
    version: int
    is_valid: bool
    days_until_expiry: Optional[int]
    notes: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class ConsentListResponse(BaseModel):
    """Paginierte Einwilligungs-Liste."""
    items: List[ConsentResponse]
    total: int
    offset: int
    limit: int


class DPACreate(BaseModel):
    """Schema fuer AVV-Erstellung."""
    controller_name: str = Field(..., max_length=255)
    processor_name: str = Field(..., max_length=255)
    title: str = Field(..., max_length=255)
    effective_date: date
    expiration_date: Optional[date] = None
    processor_entity_id: Optional[UUID] = None
    subject_matter: Optional[str] = None
    processing_purposes: Optional[List[str]] = None
    data_categories: Optional[List[str]] = None
    data_subjects: Optional[List[str]] = None
    subprocessor_allowed: bool = False
    international_transfer: bool = False
    processor_dpo_name: Optional[str] = Field(None, max_length=200)
    processor_dpo_email: Optional[EmailStr] = None
    agreement_document_id: Optional[UUID] = None
    notes: Optional[str] = None


class DPAResponse(BaseModel):
    """Schema fuer AVV-Antwort."""
    id: UUID
    controller_name: str
    processor_name: str
    processor_entity_id: Optional[UUID]
    agreement_number: Optional[str]
    title: str
    effective_date: date
    expiration_date: Optional[date]
    auto_renewal: bool
    subject_matter: Optional[str]
    processing_purposes: List[str]
    data_categories: List[str]
    data_subjects: List[str]
    subprocessor_allowed: bool
    subprocessors: List[dict]
    international_transfer: bool
    transfer_mechanisms: List[str]
    processor_dpo_name: Optional[str]
    processor_dpo_email: Optional[str]
    status: str
    is_active: bool
    days_until_expiry: Optional[int]
    agreement_document_id: Optional[UUID]
    notes: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class DPAListResponse(BaseModel):
    """Paginierte AVV-Liste."""
    items: List[DPAResponse]
    total: int
    offset: int
    limit: int


class RetentionPolicyCreate(BaseModel):
    """Schema fuer Aufbewahrungsrichtlinie."""
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    document_type: Optional[str] = Field(None, max_length=50)
    data_category: Optional[str] = Field(None, max_length=50)
    retention_days: int = Field(..., ge=1, le=36500)  # Max 100 Jahre
    legal_basis: Optional[str] = Field(None, max_length=255)
    action_after_expiry: str = Field(default="archive")
    exceptions: Optional[List[str]] = None
    notify_days_before: int = Field(default=30, ge=1, le=365)
    notify_emails: Optional[List[EmailStr]] = None


class RetentionPolicyResponse(BaseModel):
    """Schema fuer Aufbewahrungsrichtlinie-Antwort."""
    id: UUID
    name: str
    description: Optional[str]
    document_type: Optional[str]
    data_category: Optional[str]
    retention_days: int
    retention_years: float
    legal_basis: Optional[str]
    action_after_expiry: str
    exceptions: List[str]
    notify_days_before: int
    notify_emails: List[str]
    is_active: bool
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class AuditLogResponse(BaseModel):
    """Schema fuer Audit-Log-Antwort."""
    id: UUID
    consent_record_id: UUID
    action: str
    performed_by_id: Optional[UUID]
    performed_by_name: Optional[str]
    performed_by_role: Optional[str]
    performed_at: datetime
    old_value: dict
    new_value: dict
    changes: dict
    ip_address: Optional[str]
    reason: Optional[str]


class ConsentStatsResponse(BaseModel):
    """Einwilligungs-Statistiken."""
    by_status: dict
    by_type: dict
    total_granted: int
    total_pending: int
    total_withdrawn: int
    expiring_soon: int
    active_dpas: int


# =============================================================================
# Helper Functions
# =============================================================================

def _consent_to_response(consent: ConsentRecord) -> ConsentResponse:
    """Konvertiere Consent-Model zu Response."""
    data = consent.to_dict()
    return ConsentResponse(**data)


def _dpa_to_response(dpa: DataProcessingAgreement) -> DPAResponse:
    """Konvertiere DPA-Model zu Response."""
    data = dpa.to_dict()
    return DPAResponse(**data)


def _policy_to_response(policy: RetentionPolicy) -> RetentionPolicyResponse:
    """Konvertiere Policy-Model zu Response."""
    data = policy.to_dict()
    return RetentionPolicyResponse(**data)


def _audit_to_response(log: ConsentAuditLog) -> AuditLogResponse:
    """Konvertiere Audit-Log-Model zu Response."""
    data = log.to_dict()
    return AuditLogResponse(**data)


# =============================================================================
# Consent Endpoints
# =============================================================================

@router.post("/consents", response_model=ConsentResponse, status_code=status.HTTP_201_CREATED)
async def request_consent(
    data: ConsentRequestCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ConsentResponse:
    """
    Erstelle neue Einwilligungsanfrage.

    Sendet optional Benachrichtigung an den Betroffenen.
    """
    # Validiere consent_type
    valid_types = [t.value for t in ConsentType]
    if data.consent_type not in valid_types:
        logger.warning(f"Unbekannter Consent-Typ: {data.consent_type}")

    service = ConsentService(db)

    consent = await service.request_consent(
        company_id=company.company_id,
        consent_type=data.consent_type,
        entity_id=data.entity_id,
        user_id=data.user_id,
        grantor_name=data.grantor_name,
        grantor_email=data.grantor_email,
        scope=data.scope,
        expires_at=data.expires_at,
        source=data.source,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    await db.commit()

    logger.info(
        "Consent requested",
        consent_id=str(consent.id),
        consent_type=data.consent_type,
        company_id=str(company.company_id),
    )

    return _consent_to_response(consent)


@router.get("/consents", response_model=ConsentListResponse)
async def list_consents(
    entity_id: Optional[UUID] = Query(None, description="Filter nach Entity"),
    user_id: Optional[UUID] = Query(None, description="Filter nach User"),
    consent_type: Optional[str] = Query(None, description="Filter nach Typ"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter nach Status"),
    only_valid: bool = Query(False, description="Nur gueltige Einwilligungen"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ConsentListResponse:
    """
    Liste Einwilligungen mit Filteroptionen.
    """
    service = ConsentService(db)

    consents, total = await service.list_consents(
        company_id=company.company_id,
        entity_id=entity_id,
        user_id=user_id,
        consent_type=consent_type,
        status=status_filter,
        only_valid=only_valid,
        offset=offset,
        limit=limit,
    )

    return ConsentListResponse(
        items=[_consent_to_response(c) for c in consents],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/consents/expiring", response_model=List[ConsentResponse])
async def get_expiring_consents(
    days_ahead: int = Query(30, ge=1, le=365, description="Tage voraus"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> List[ConsentResponse]:
    """
    Liste bald ablaufende Einwilligungen.
    """
    service = ConsentService(db)
    consents = await service.get_expiring_consents(
        company_id=company.company_id,
        days_ahead=days_ahead,
    )

    return [_consent_to_response(c) for c in consents]


@router.get("/consents/check", response_model=dict)
async def check_consent(
    consent_type: str = Query(..., description="Typ der Einwilligung"),
    entity_id: Optional[UUID] = Query(None, description="Entity-ID"),
    user_id: Optional[UUID] = Query(None, description="User-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> dict:
    """
    Pruefe ob gueltige Einwilligung vorliegt.
    """
    service = ConsentService(db)

    has_consent = await service.check_consent(
        company_id=company.company_id,
        consent_type=consent_type,
        entity_id=entity_id,
        user_id=user_id,
    )

    return {
        "consent_type": consent_type,
        "entity_id": str(entity_id) if entity_id else None,
        "user_id": str(user_id) if user_id else None,
        "has_valid_consent": has_consent,
    }


@router.get("/consents/types", response_model=List[dict])
async def list_consent_types(
    current_user: User = Depends(get_current_active_user),
) -> List[dict]:
    """
    Liste alle verfuegbaren Einwilligungstypen.
    """
    return [
        {"value": t.value, "name": t.name}
        for t in ConsentType
    ]


@router.get("/consents/{consent_id}", response_model=ConsentResponse)
async def get_consent(
    consent_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ConsentResponse:
    """
    Einzelne Einwilligung abrufen.
    """
    service = ConsentService(db)
    consent = await service.get_consent(
        consent_id=consent_id,
        company_id=company.company_id,
    )

    if not consent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Einwilligung nicht gefunden",
        )

    return _consent_to_response(consent)


@router.post("/consents/{consent_id}/grant", response_model=ConsentResponse)
async def grant_consent(
    consent_id: UUID,
    data: ConsentGrantRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ConsentResponse:
    """
    Erteile Einwilligung.
    """
    service = ConsentService(db)

    consent = await service.grant_consent(
        consent_id=consent_id,
        granted_by_id=current_user.id,
        grantor_name=data.grantor_name,
        grantor_role=data.grantor_role,
        conditions=data.conditions,
        restrictions=data.restrictions,
        document_id=data.document_id,
        document_reference=data.document_reference,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    if not consent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Einwilligung nicht gefunden",
        )

    # Verifiziere Company-Zugehoerigkeit
    if consent.company_id != company.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Zugriff verweigert",
        )

    await db.commit()

    logger.info(
        "Consent granted",
        consent_id=str(consent_id),
        user_id=str(current_user.id),
    )

    return _consent_to_response(consent)


@router.post("/consents/{consent_id}/deny", response_model=ConsentResponse)
async def deny_consent(
    consent_id: UUID,
    reason: Optional[str] = Query(None, max_length=500),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ConsentResponse:
    """
    Verweigere Einwilligung.
    """
    service = ConsentService(db)

    consent = await service.deny_consent(
        consent_id=consent_id,
        denied_by_id=current_user.id,
        reason=reason,
        ip_address=request.client.host if request and request.client else None,
    )

    if not consent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Einwilligung nicht gefunden",
        )

    if consent.company_id != company.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Zugriff verweigert",
        )

    await db.commit()

    return _consent_to_response(consent)


@router.post("/consents/{consent_id}/withdraw", response_model=ConsentResponse)
async def withdraw_consent(
    consent_id: UUID,
    data: ConsentWithdrawRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ConsentResponse:
    """
    Widerrufe Einwilligung.

    Kann nur auf erteilte Einwilligungen angewendet werden.
    """
    service = ConsentService(db)

    consent = await service.withdraw_consent(
        consent_id=consent_id,
        withdrawn_by_id=current_user.id,
        reason=data.reason,
        method=data.method,
        ip_address=request.client.host if request.client else None,
    )

    if not consent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Einwilligung nicht gefunden oder bereits widerrufen",
        )

    if consent.company_id != company.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Zugriff verweigert",
        )

    await db.commit()

    logger.info(
        "Consent withdrawn",
        consent_id=str(consent_id),
        reason=data.reason,
    )

    return _consent_to_response(consent)


@router.get("/consents/{consent_id}/audit", response_model=List[AuditLogResponse])
async def get_consent_audit_trail(
    consent_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> List[AuditLogResponse]:
    """
    Audit-Trail fuer eine Einwilligung.
    """
    service = ConsentService(db)

    # Verifiziere Consent existiert und gehoert zur Company
    consent = await service.get_consent(consent_id, company.company_id)
    if not consent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Einwilligung nicht gefunden",
        )

    logs = await service.get_audit_trail(consent_id)

    return [_audit_to_response(log) for log in logs]


# =============================================================================
# Data Processing Agreement (DPA) Endpoints
# =============================================================================

@router.post("/dpas", response_model=DPAResponse, status_code=status.HTTP_201_CREATED)
async def create_dpa(
    data: DPACreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> DPAResponse:
    """
    Erstelle neuen Auftragsverarbeitungsvertrag (AVV).
    """
    service = ConsentService(db)

    dpa = await service.create_dpa(
        company_id=company.company_id,
        controller_name=data.controller_name,
        processor_name=data.processor_name,
        title=data.title,
        effective_date=data.effective_date,
        expiration_date=data.expiration_date,
        processor_entity_id=data.processor_entity_id,
        subject_matter=data.subject_matter,
        processing_purposes=data.processing_purposes,
        data_categories=data.data_categories,
        data_subjects=data.data_subjects,
        subprocessor_allowed=data.subprocessor_allowed,
        international_transfer=data.international_transfer,
        processor_dpo_name=data.processor_dpo_name,
        processor_dpo_email=data.processor_dpo_email,
        agreement_document_id=data.agreement_document_id,
        notes=data.notes,
    )

    await db.commit()

    logger.info(
        "DPA created",
        dpa_id=str(dpa.id),
        processor=data.processor_name,
    )

    return _dpa_to_response(dpa)


@router.get("/dpas", response_model=DPAListResponse)
async def list_dpas(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter nach Status"),
    only_active: bool = Query(False, description="Nur aktive AVVs"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> DPAListResponse:
    """
    Liste Auftragsverarbeitungsvertraege.
    """
    service = ConsentService(db)

    dpas, total = await service.list_dpas(
        company_id=company.company_id,
        status=status_filter,
        only_active=only_active,
        offset=offset,
        limit=limit,
    )

    return DPAListResponse(
        items=[_dpa_to_response(d) for d in dpas],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/dpas/{dpa_id}", response_model=DPAResponse)
async def get_dpa(
    dpa_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> DPAResponse:
    """
    Einzelnen AVV abrufen.
    """
    service = ConsentService(db)
    dpa = await service.get_dpa(dpa_id, company.company_id)

    if not dpa:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AVV nicht gefunden",
        )

    return _dpa_to_response(dpa)


@router.post("/dpas/{dpa_id}/terminate", response_model=DPAResponse)
async def terminate_dpa(
    dpa_id: UUID,
    reason: Optional[str] = Query(None, max_length=500, description="Kuendigungsgrund"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> DPAResponse:
    """
    Kuendige AVV.
    """
    service = ConsentService(db)

    # Verifiziere Zugehoerigkeit
    existing = await service.get_dpa(dpa_id, company.company_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AVV nicht gefunden",
        )

    dpa = await service.terminate_dpa(dpa_id, reason)

    await db.commit()

    logger.info(
        "DPA terminated",
        dpa_id=str(dpa_id),
        reason=reason,
    )

    return _dpa_to_response(dpa)


# =============================================================================
# Retention Policy Endpoints
# =============================================================================

@router.post("/retention-policies", response_model=RetentionPolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_retention_policy(
    data: RetentionPolicyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> RetentionPolicyResponse:
    """
    Erstelle neue Aufbewahrungsrichtlinie.
    """
    service = ConsentService(db)

    policy = await service.create_retention_policy(
        company_id=company.company_id,
        name=data.name,
        description=data.description,
        document_type=data.document_type,
        data_category=data.data_category,
        retention_days=data.retention_days,
        legal_basis=data.legal_basis,
        action_after_expiry=data.action_after_expiry,
        exceptions=data.exceptions,
        notify_days_before=data.notify_days_before,
        notify_emails=data.notify_emails,
    )

    await db.commit()

    logger.info(
        "Retention policy created",
        policy_id=str(policy.id),
        name=data.name,
        retention_days=data.retention_days,
    )

    return _policy_to_response(policy)


@router.get("/retention-policies", response_model=List[RetentionPolicyResponse])
async def list_retention_policies(
    only_active: bool = Query(True, description="Nur aktive Richtlinien"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> List[RetentionPolicyResponse]:
    """
    Liste Aufbewahrungsrichtlinien.
    """
    service = ConsentService(db)
    policies = await service.list_retention_policies(
        company_id=company.company_id,
        only_active=only_active,
    )

    return [_policy_to_response(p) for p in policies]


@router.get("/retention-policies/applicable", response_model=Optional[RetentionPolicyResponse])
async def get_applicable_policy(
    document_type: Optional[str] = Query(None, description="Dokumenttyp"),
    data_category: Optional[str] = Query(None, description="Datenkategorie"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> Optional[RetentionPolicyResponse]:
    """
    Finde anwendbare Aufbewahrungsrichtlinie.
    """
    service = ConsentService(db)
    policy = await service.get_applicable_policy(
        company_id=company.company_id,
        document_type=document_type,
        data_category=data_category,
    )

    if not policy:
        return None

    return _policy_to_response(policy)


# =============================================================================
# Statistics Endpoints
# =============================================================================

@router.get("/statistics", response_model=ConsentStatsResponse)
async def get_consent_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ConsentStatsResponse:
    """
    Einwilligungs-Statistiken.
    """
    service = ConsentService(db)
    stats = await service.get_consent_statistics(company_id=company.company_id)

    return ConsentStatsResponse(**stats)


# =============================================================================
# Audit Endpoints
# =============================================================================

@router.get("/audit", response_model=List[AuditLogResponse])
async def search_audit_logs(
    action: Optional[str] = Query(None, description="Filter nach Aktion"),
    date_from: Optional[datetime] = Query(None, description="Startdatum"),
    date_to: Optional[datetime] = Query(None, description="Enddatum"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> List[AuditLogResponse]:
    """
    Suche in Audit-Logs.
    """
    service = ConsentService(db)
    logs = await service.search_audit_logs(
        company_id=company.company_id,
        action=action,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )

    return [_audit_to_response(log) for log in logs]


# =============================================================================
# Admin Endpoints
# =============================================================================

@router.post("/admin/expire-consents", status_code=status.HTTP_200_OK)
async def expire_consents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> dict:
    """
    Markiere abgelaufene Einwilligungen (Admin).

    Normalerweise automatisch per Celery-Task.
    """
    service = ConsentService(db)
    count = await service.expire_consents(company_id=company.company_id)

    await db.commit()

    return {
        "status": "completed",
        "expired_count": count,
    }
