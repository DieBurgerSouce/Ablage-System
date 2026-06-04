# -*- coding: utf-8 -*-
"""Supplier Verification API Endpoints.

API für Lieferanten-Verifizierung gegen externe Register.

Endpoints:
- POST /entities/{id}/verify - Lieferant verifizieren
- GET /entities/{id}/verification-status - Verifizierungsstatus abrufen
- POST /entities/batch-verify - Batch-Verifizierung
- GET /entities/verification-needed - Entities die verifiziert werden sollten
"""


from typing import Dict, List, Optional
from uuid import UUID

from app.core.types import JSONDict

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.api.v1.workflows import get_user_company_id
from app.db.models import User
from app.core.safe_errors import safe_error_log, safe_error_detail
from app.services.external.supplier_verification_service import (
    SupplierVerificationService,
    VerificationResult,
    VerificationSource,
    VerificationStatus,
    VerificationSeverity,
)
from app.core.rate_limiting import limiter, get_user_identifier

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/entities", tags=["supplier-verification"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


class VerificationFindingResponse(BaseModel):
    """Einzelner Befund der Verifizierung."""

    source: str
    severity: str
    code: str
    message: str
    details: JSONDict = Field(default_factory=dict)
    timestamp: str


class HandelsregisterResultResponse(BaseModel):
    """Handelsregister-Ergebnis."""

    found: bool
    company_name: Optional[str] = None
    legal_form: Optional[str] = None
    register_court: Optional[str] = None
    register_number: Optional[str] = None
    registered_address: Optional[str] = None
    managing_directors: Optional[List[str]] = None
    status: str = "unknown"
    founded_date: Optional[str] = None
    capital: Optional[str] = None


class ViesResultResponse(BaseModel):
    """VIES-Ergebnis (USt-IdNr Validierung)."""

    valid: bool
    vat_number: Optional[str] = None
    country_code: Optional[str] = None
    company_name: Optional[str] = None
    company_address: Optional[str] = None
    request_date: Optional[str] = None


class InsolvenzResultResponse(BaseModel):
    """Insolvenzregister-Ergebnis."""

    has_insolvency: bool
    insolvency_type: Optional[str] = None
    court: Optional[str] = None
    case_number: Optional[str] = None
    published_date: Optional[str] = None


class BundesanzeigerResultResponse(BaseModel):
    """Bundesanzeiger-Ergebnis."""

    found: bool
    publications_count: int = 0
    latest_annual_report: Optional[str] = None
    latest_balance_sheet_date: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


class VerificationResultResponse(BaseModel):
    """Gesamtergebnis der Verifizierung.

    SECURITY NOTE (P0 Fix - CWE-200):
    entity_name wurde entfernt um PII-Leakage zu verhindern.
    Der Client kann den Entity-Namen über die entity_id abrufen.
    """

    entity_id: str
    # SECURITY FIX: entity_name entfernt - PII sollte nicht in Verification-Responses exponiert werden
    overall_status: str
    verification_score: int
    sources_checked: List[str]
    findings: List[VerificationFindingResponse]
    handelsregister: Optional[HandelsregisterResultResponse] = None
    vies: Optional[ViesResultResponse] = None
    insolvenzregister: Optional[InsolvenzResultResponse] = None
    bundesanzeiger: Optional[BundesanzeigerResultResponse] = None
    verified_at: str
    expires_at: str
    cached: bool = False


class VerifyRequest(BaseModel):
    """Anfrage für Verifizierung."""

    force_refresh: bool = Field(
        default=False,
        description="Cache ignorieren und neu verifizieren",
    )
    sources: Optional[List[str]] = Field(
        default=None,
        description="Optionale Liste der zu prüfenden Quellen",
    )


class BatchVerifyRequest(BaseModel):
    """Anfrage für Batch-Verifizierung."""

    entity_ids: List[UUID] = Field(..., min_length=1, max_length=50)
    force_refresh: bool = False


class BatchVerifyResponse(BaseModel):
    """Antwort der Batch-Verifizierung."""

    results: Dict[str, VerificationResultResponse]
    total: int
    successful: int
    failed: int


class VerificationNeededResponse(BaseModel):
    """Entities die verifiziert werden sollten."""

    entity_ids: List[str]
    total: int


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "/{entity_id}/verify",
    response_model=VerificationResultResponse,
    summary="Entity verifizieren",
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def verify_entity(
    request: Request,
    entity_id: UUID,
    body: VerifyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VerificationResultResponse:
    """Verifiziert einen Geschäftspartner gegen externe Register.

    Prüft:
    - Handelsregister (Firmenexistenz, Status)
    - Insolvenzregister (Keine Insolvenz)
    - VIES (USt-IdNr Validierung, EU-weit)
    - Bundesanzeiger (Jahresabschluesse)

    Ergebnisse werden 30 Tage gecached.
    """
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    service = SupplierVerificationService(db)

    # Sources parsen
    sources = None
    if body.sources:
        try:
            sources = [VerificationSource(s) for s in body.sources]
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=safe_error_detail(e, "Vorgang"),
            )

    try:
        result = await service.verify_entity(
            entity_id=entity_id,
            company_id=company_id,
            force_refresh=body.force_refresh,
            sources=sources,
        )
    except Exception as e:
        logger.error(
            "verification_failed",
            entity_id=str(entity_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Vorgang"),
        )

    return _convert_result_to_response(result)


@router.get(
    "/{entity_id}/verification-status",
    response_model=VerificationResultResponse,
    summary="Verifizierungsstatus abrufen",
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_verification_status(
    request: Request,
    entity_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VerificationResultResponse:
    """Ruft den aktuellen Verifizierungsstatus ab.

    Gibt den gecachten Status zurück falls vorhanden.
    Startet keine neue Verifizierung.
    """
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    service = SupplierVerificationService(db)

    result = await service.get_verification_status(
        entity_id=entity_id,
        company_id=company_id,
    )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Verifizierung vorhanden. Bitte zuerst verifizieren.",
        )

    return _convert_result_to_response(result)


@router.post(
    "/batch-verify",
    response_model=BatchVerifyResponse,
    summary="Batch-Verifizierung",
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def batch_verify_entities(
    request: Request,
    body: BatchVerifyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BatchVerifyResponse:
    """Verifiziert mehrere Entities in einem Batch.

    Maximal 50 Entities pro Anfrage.
    """
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    service = SupplierVerificationService(db)

    results = await service.batch_verify(
        entity_ids=body.entity_ids,
        company_id=company_id,
        force_refresh=body.force_refresh,
    )

    response_results: Dict[str, VerificationResultResponse] = {}
    successful = 0
    failed = 0

    for entity_id_str, result in results.items():
        response_results[entity_id_str] = _convert_result_to_response(result)
        if result.overall_status == VerificationStatus.ERROR:
            failed += 1
        else:
            successful += 1

    return BatchVerifyResponse(
        results=response_results,
        total=len(results),
        successful=successful,
        failed=failed,
    )


@router.get(
    "/verification-needed",
    response_model=VerificationNeededResponse,
    summary="Entities die verifiziert werden sollten",
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_entities_needing_verification(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VerificationNeededResponse:
    """Findet Entities die verifiziert werden sollten.

    Gibt Entities zurück die:
    - Noch nie verifiziert wurden
    - Deren Verifizierung abgelaufen ist (> 30 Tage)
    """
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    service = SupplierVerificationService(db)

    entity_ids = await service.get_entities_needing_verification(
        company_id=company_id,
        limit=limit,
    )

    return VerificationNeededResponse(
        entity_ids=[str(eid) for eid in entity_ids],
        total=len(entity_ids),
    )


# =============================================================================
# Helper Functions
# =============================================================================


def _convert_result_to_response(result: "VerificationResult") -> VerificationResultResponse:
    """Konvertiert VerificationResult zu Response-Schema."""
    findings = [
        VerificationFindingResponse(
            source=f.source.value,
            severity=f.severity.value,
            code=f.code,
            message=f.message,
            details=f.details,
            timestamp=f.timestamp.isoformat(),
        )
        for f in result.findings
    ]

    handelsregister = None
    if result.handelsregister:
        hr = result.handelsregister
        handelsregister = HandelsregisterResultResponse(
            found=hr.found,
            company_name=hr.company_name,
            legal_form=hr.legal_form,
            register_court=hr.register_court,
            register_number=hr.register_number,
            registered_address=hr.registered_address,
            managing_directors=hr.managing_directors,
            status=hr.status,
            founded_date=hr.founded_date,
            capital=hr.capital,
        )

    vies = None
    if result.vies:
        v = result.vies
        vies = ViesResultResponse(
            valid=v.valid,
            vat_number=v.vat_number,
            country_code=v.country_code,
            company_name=v.company_name,
            company_address=v.company_address,
            request_date=v.request_date,
        )

    insolvenz = None
    if result.insolvenzregister:
        i = result.insolvenzregister
        insolvenz = InsolvenzResultResponse(
            has_insolvency=i.has_insolvency,
            insolvency_type=i.insolvency_type,
            court=i.court,
            case_number=i.case_number,
            published_date=i.published_date,
        )

    bundesanzeiger = None
    if result.bundesanzeiger:
        ba = result.bundesanzeiger
        bundesanzeiger = BundesanzeigerResultResponse(
            found=ba.found,
            publications_count=ba.publications_count,
            latest_annual_report=ba.latest_annual_report,
            latest_balance_sheet_date=ba.latest_balance_sheet_date,
            warnings=ba.warnings,
        )

    # SECURITY FIX (P0 - CWE-200): entity_name nicht mehr in Response exponiert
    return VerificationResultResponse(
        entity_id=str(result.entity_id),
        # entity_name absichtlich entfernt - PII-Schutz
        overall_status=result.overall_status.value,
        verification_score=result.verification_score,
        sources_checked=[s.value for s in result.sources_checked],
        findings=findings,
        handelsregister=handelsregister,
        vies=vies,
        insolvenzregister=insolvenz,
        bundesanzeiger=bundesanzeiger,
        verified_at=result.verified_at.isoformat(),
        expires_at=result.expires_at.isoformat(),
        cached=result.cached,
    )
