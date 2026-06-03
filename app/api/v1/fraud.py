# -*- coding: utf-8 -*-
"""
Enhanced Fraud Detection API Endpoints for Ablage-System.

Comprehensive fraud detection with:
- CEO Fraud Detection
- Duplicate Payment Detection
- IBAN Manipulation Detection
- Internal Irregularity Detection
- Scan result management
- Statistics and dashboards

SECURITY: NEVER expose entity names, financial details, or PII in responses.

Feinpoliert und durchdacht - Enterprise Fraud Prevention API.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from app.core.types import JSONDict
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException, status
from pydantic import BaseModel, Field, field_validator, ConfigDict
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db, get_user_company_id_dep
from app.db.models import User
from app.db.models_fraud import (
    FraudScanResult,
    IBANChangeRequest,
    IBANBaseline,
    FraudScanType,
    FraudRiskLevel,
    FraudScanStatus,
    IBANChangeStatus,
)
from app.services.ai.fraud_detection_service import (
    get_enhanced_fraud_detection_service,
    FraudDetectionResult,
)
from app.workers.tasks.fraud_detection_tasks import (
    scan_new_documents_task,
    iban_verification_task,
)

router = APIRouter(prefix="/fraud", tags=["Fraud Detection"])


# =============================================================================
# Request/Response Schemas
# =============================================================================


class FraudScanRequestSchema(BaseModel):
    """Request schema for manual fraud scan."""

    scan_type: str = Field(
        default="ceo_fraud",
        description="Scan type: ceo_fraud, duplicate_payment, iban_manipulation",
    )

    @field_validator("scan_type")
    @classmethod
    def validate_scan_type(cls, v: str) -> str:
        allowed = {"ceo_fraud", "duplicate_payment", "iban_manipulation"}
        if v not in allowed:
            raise ValueError(f"scan_type must be one of: {allowed}")
        return v


class IBANVerificationRequestSchema(BaseModel):
    """Request schema for IBAN verification."""

    entity_id: UUID
    new_iban: str = Field(..., min_length=15, max_length=34)
    source_document_id: Optional[UUID] = None

    @field_validator("new_iban")
    @classmethod
    def validate_iban(cls, v: str) -> str:
        # Basic IBAN format validation
        v = v.upper().replace(" ", "")
        if len(v) < 15 or len(v) > 34:
            raise ValueError("IBAN muss zwischen 15 und 34 Zeichen haben")
        if not v[:2].isalpha():
            raise ValueError("IBAN muss mit Ländercode beginnen")
        return v


class FraudScanResultSchema(BaseModel):
    """Response schema for fraud scan results."""

    id: str
    scan_type: str
    scan_source: str
    risk_score: float
    risk_level: str
    confidence: float
    indicators: JSONDict
    explanation: JSONDict
    status: str
    document_id: Optional[str] = None
    entity_id: Optional[str] = None
    created_at: str
    reviewed_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class IBANHistorySchema(BaseModel):
    """Response schema for IBAN history."""

    id: str
    iban_masked: str
    bic: Optional[str] = None
    bank_name: Optional[str] = None
    first_seen_at: str
    last_used_at: str
    is_verified: bool
    is_active: bool


class IBANChangeRequestSchema(BaseModel):
    """Response schema for IBAN change requests."""

    id: str
    entity_id: str
    old_iban_masked: Optional[str] = None
    new_iban_masked: str
    status: str
    verification_required: bool
    verification_deadline: Optional[str] = None
    risk_score: Optional[float] = None
    detected_at: str
    verified_at: Optional[str] = None


class FraudStatisticsSchema(BaseModel):
    """Response schema for fraud statistics."""

    analysis_period_days: int
    total_scans: int
    by_scan_type: Dict[str, int]
    by_risk_level: Dict[str, int]
    by_status: Dict[str, int]
    average_risk_score: float
    generated_at: str


class UpdateScanStatusRequest(BaseModel):
    """Request for updating scan result status."""

    status: str = Field(..., description="pending, reviewed, false_positive, confirmed, investigating")
    notes: Optional[str] = Field(None, max_length=2000)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"pending", "reviewed", "false_positive", "confirmed", "investigating"}
        if v not in allowed:
            raise ValueError(f"status must be one of: {allowed}")
        return v


# =============================================================================
# Fraud Scan Endpoints
# =============================================================================


@router.post("/scan/{document_id}", response_model=FraudScanResultSchema)
async def scan_document_for_fraud(
    document_id: UUID,
    request: FraudScanRequestSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> FraudScanResultSchema:
    """
    Manually trigger a fraud scan on a specific document.

    Supports:
    - `ceo_fraud`: CEO Fraud / Business Email Compromise detection
    - `duplicate_payment`: Duplicate payment detection
    - `iban_manipulation`: IBAN manipulation detection (requires entity)

    Returns fraud scan result with risk assessment.
    """
    service = get_enhanced_fraud_detection_service(db)

    try:
        if request.scan_type == "ceo_fraud":
            result = await service.detect_ceo_fraud(
                document_id=document_id,
                company_id=company_id,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Scan-Typ '{request.scan_type}' erfordert zusätzliche Parameter",
            )

        await db.commit()

        # Get the stored scan result
        stmt = (
            select(FraudScanResult)
            .where(
                and_(
                    FraudScanResult.document_id == document_id,
                    FraudScanResult.scan_type == request.scan_type,
                )
            )
            .order_by(FraudScanResult.created_at.desc())
            .limit(1)
        )
        db_result = await db.execute(stmt)
        scan_result = db_result.scalar_one_or_none()

        if not scan_result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Scan-Ergebnis konnte nicht gespeichert werden",
            )

        return FraudScanResultSchema(
            id=str(scan_result.id),
            scan_type=scan_result.scan_type,
            scan_source=scan_result.scan_source,
            risk_score=scan_result.risk_score,
            risk_level=scan_result.risk_level,
            confidence=scan_result.confidence,
            indicators=scan_result.indicators,
            explanation=scan_result.explanation,
            status=scan_result.status,
            document_id=str(scan_result.document_id) if scan_result.document_id else None,
            entity_id=str(scan_result.entity_id) if scan_result.entity_id else None,
            created_at=scan_result.created_at.isoformat() if scan_result.created_at else "",
            reviewed_at=scan_result.reviewed_at.isoformat() if scan_result.reviewed_at else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fraud-Scan fehlgeschlagen",
        )


@router.post("/scan/invoice/{invoice_id}", response_model=FraudScanResultSchema)
async def scan_invoice_for_duplicates(
    invoice_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> FraudScanResultSchema:
    """
    Scan an invoice for duplicate payment detection.

    Checks for:
    - Hash-based exact duplicates
    - Fuzzy matching (similar amounts +/- 5%, similar dates +/- 3 days)
    - Same invoice number with different entity
    """
    service = get_enhanced_fraud_detection_service(db)

    try:
        result = await service.detect_duplicate_payment(
            invoice_id=invoice_id,
            company_id=company_id,
        )

        await db.commit()

        # Get the stored scan result
        stmt = (
            select(FraudScanResult)
            .where(
                and_(
                    FraudScanResult.invoice_id == invoice_id,
                    FraudScanResult.scan_type == FraudScanType.DUPLICATE_PAYMENT.value,
                )
            )
            .order_by(FraudScanResult.created_at.desc())
            .limit(1)
        )
        db_result = await db.execute(stmt)
        scan_result = db_result.scalar_one_or_none()

        if not scan_result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Scan-Ergebnis konnte nicht gespeichert werden",
            )

        return FraudScanResultSchema(
            id=str(scan_result.id),
            scan_type=scan_result.scan_type,
            scan_source=scan_result.scan_source,
            risk_score=scan_result.risk_score,
            risk_level=scan_result.risk_level,
            confidence=scan_result.confidence,
            indicators=scan_result.indicators,
            explanation=scan_result.explanation,
            status=scan_result.status,
            document_id=str(scan_result.document_id) if scan_result.document_id else None,
            entity_id=str(scan_result.entity_id) if scan_result.entity_id else None,
            created_at=scan_result.created_at.isoformat() if scan_result.created_at else "",
            reviewed_at=scan_result.reviewed_at.isoformat() if scan_result.reviewed_at else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Duplikat-Scan fehlgeschlagen",
        )


# =============================================================================
# IBAN Verification Endpoints
# =============================================================================


@router.post("/verify-iban", response_model=FraudScanResultSchema)
async def verify_iban_change(
    request: IBANVerificationRequestSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> FraudScanResultSchema:
    """
    Verify an IBAN change for potential manipulation.

    Creates a verification workflow if the change is suspicious.
    Checks:
    - IBAN differs from baseline
    - Frequency of IBAN changes
    - Country change (DE -> foreign)
    """
    service = get_enhanced_fraud_detection_service(db)

    try:
        result = await service.detect_iban_manipulation(
            entity_id=request.entity_id,
            new_iban=request.new_iban,
            company_id=company_id,
            source_document_id=request.source_document_id,
        )

        await db.commit()

        # Get the stored scan result
        stmt = (
            select(FraudScanResult)
            .where(
                and_(
                    FraudScanResult.entity_id == request.entity_id,
                    FraudScanResult.scan_type == FraudScanType.IBAN_MANIPULATION.value,
                )
            )
            .order_by(FraudScanResult.created_at.desc())
            .limit(1)
        )
        db_result = await db.execute(stmt)
        scan_result = db_result.scalar_one_or_none()

        if not scan_result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="IBAN-Verifizierung konnte nicht gespeichert werden",
            )

        return FraudScanResultSchema(
            id=str(scan_result.id),
            scan_type=scan_result.scan_type,
            scan_source=scan_result.scan_source,
            risk_score=scan_result.risk_score,
            risk_level=scan_result.risk_level,
            confidence=scan_result.confidence,
            indicators=scan_result.indicators,
            explanation=scan_result.explanation,
            status=scan_result.status,
            document_id=str(scan_result.document_id) if scan_result.document_id else None,
            entity_id=str(scan_result.entity_id) if scan_result.entity_id else None,
            created_at=scan_result.created_at.isoformat() if scan_result.created_at else "",
            reviewed_at=scan_result.reviewed_at.isoformat() if scan_result.reviewed_at else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="IBAN-Verifizierung fehlgeschlagen",
        )


@router.get("/iban-history/{entity_id}", response_model=List[IBANHistorySchema])
async def get_iban_history(
    entity_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[IBANHistorySchema]:
    """
    Get IBAN change history for an entity.

    Returns masked IBANs for security.
    """
    stmt = (
        select(IBANBaseline)
        .where(
            and_(
                IBANBaseline.entity_id == entity_id,
                IBANBaseline.company_id == company_id,
            )
        )
        .order_by(IBANBaseline.first_seen_at.desc())
    )

    result = await db.execute(stmt)
    baselines = result.scalars().all()

    return [
        IBANHistorySchema(
            id=str(b.id),
            iban_masked=f"{b.iban[:4]}...{b.iban[-4:]}" if b.iban else "",
            bic=b.bic,
            bank_name=b.bank_name,
            first_seen_at=b.first_seen_at.isoformat() if b.first_seen_at else "",
            last_used_at=b.last_used_at.isoformat() if b.last_used_at else "",
            is_verified=b.is_verified,
            is_active=b.is_active,
        )
        for b in baselines
    ]


@router.get("/iban-requests", response_model=List[IBANChangeRequestSchema])
async def list_iban_change_requests(
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=200, description="Eintraege pro Seite"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[IBANChangeRequestSchema]:
    """
    List IBAN change requests pending verification.
    """
    stmt = (
        select(IBANChangeRequest)
        .where(IBANChangeRequest.company_id == company_id)
        .order_by(IBANChangeRequest.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )

    if status_filter:
        stmt = stmt.where(IBANChangeRequest.status == status_filter)

    result = await db.execute(stmt)
    requests = result.scalars().all()

    return [
        IBANChangeRequestSchema(
            id=str(r.id),
            entity_id=str(r.entity_id),
            old_iban_masked=f"{r.old_iban[:4]}...{r.old_iban[-4:]}" if r.old_iban else None,
            new_iban_masked=f"{r.new_iban[:4]}...{r.new_iban[-4:]}" if r.new_iban else "",
            status=r.status,
            verification_required=r.verification_required,
            verification_deadline=r.verification_deadline.isoformat() if r.verification_deadline else None,
            risk_score=r.risk_score,
            detected_at=r.detected_at.isoformat() if r.detected_at else "",
            verified_at=r.verified_at.isoformat() if r.verified_at else None,
        )
        for r in requests
    ]


@router.post("/iban-requests/{request_id}/approve")
async def approve_iban_change(
    request_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> JSONDict:
    """
    Approve an IBAN change request.

    Updates the IBAN baseline and marks request as approved.
    """
    # Get the request
    stmt = (
        select(IBANChangeRequest)
        .where(
            and_(
                IBANChangeRequest.id == request_id,
                IBANChangeRequest.company_id == company_id,
            )
        )
    )
    result = await db.execute(stmt)
    change_request = result.scalar_one_or_none()

    if not change_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="IBAN-Änderungsanfrage nicht gefunden",
        )

    if change_request.status != IBANChangeStatus.PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Anfrage ist nicht mehr ausstehend",
        )

    # Approve the request
    change_request.status = IBANChangeStatus.APPROVED.value
    change_request.verified_by_id = current_user.id
    change_request.verified_at = datetime.now(timezone.utc)
    change_request.verification_method = "manual"

    # Create or update IBAN baseline
    baseline = IBANBaseline(
        entity_id=change_request.entity_id,
        company_id=change_request.company_id,
        iban=change_request.new_iban,
        bic=change_request.new_bic,
        bank_name=change_request.new_bank_name,
        is_verified=True,
        verification_method="manual",
        verified_by_id=current_user.id,
        last_verified_at=datetime.now(timezone.utc),
    )
    db.add(baseline)

    await db.commit()

    return {
        "success": True,
        "message": "IBAN-Änderung genehmigt",
        "request_id": str(request_id),
    }


@router.post("/iban-requests/{request_id}/reject")
async def reject_iban_change(
    request_id: UUID,
    reason: Optional[str] = Query(None, max_length=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> JSONDict:
    """
    Reject an IBAN change request.
    """
    stmt = (
        select(IBANChangeRequest)
        .where(
            and_(
                IBANChangeRequest.id == request_id,
                IBANChangeRequest.company_id == company_id,
            )
        )
    )
    result = await db.execute(stmt)
    change_request = result.scalar_one_or_none()

    if not change_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="IBAN-Änderungsanfrage nicht gefunden",
        )

    if change_request.status != IBANChangeStatus.PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Anfrage ist nicht mehr ausstehend",
        )

    change_request.status = IBANChangeStatus.REJECTED.value
    change_request.verified_by_id = current_user.id
    change_request.verified_at = datetime.now(timezone.utc)
    change_request.rejection_reason = reason

    await db.commit()

    return {
        "success": True,
        "message": "IBAN-Änderung abgelehnt",
        "request_id": str(request_id),
    }


# =============================================================================
# Fraud Alerts and Results Endpoints
# =============================================================================


@router.get("/alerts", response_model=List[FraudScanResultSchema])
async def list_fraud_alerts(
    scan_type: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    days: int = Query(30, ge=1, le=365),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=200, description="Eintraege pro Seite"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[FraudScanResultSchema]:
    """
    List fraud scan results/alerts with filtering.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    stmt = (
        select(FraudScanResult)
        .where(
            and_(
                FraudScanResult.company_id == company_id,
                FraudScanResult.created_at >= cutoff,
            )
        )
        .order_by(FraudScanResult.risk_score.desc(), FraudScanResult.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )

    if scan_type:
        stmt = stmt.where(FraudScanResult.scan_type == scan_type)
    if risk_level:
        stmt = stmt.where(FraudScanResult.risk_level == risk_level)
    if status_filter:
        stmt = stmt.where(FraudScanResult.status == status_filter)

    result = await db.execute(stmt)
    results = result.scalars().all()

    return [
        FraudScanResultSchema(
            id=str(r.id),
            scan_type=r.scan_type,
            scan_source=r.scan_source,
            risk_score=r.risk_score,
            risk_level=r.risk_level,
            confidence=r.confidence,
            indicators=r.indicators,
            explanation=r.explanation,
            status=r.status,
            document_id=str(r.document_id) if r.document_id else None,
            entity_id=str(r.entity_id) if r.entity_id else None,
            created_at=r.created_at.isoformat() if r.created_at else "",
            reviewed_at=r.reviewed_at.isoformat() if r.reviewed_at else None,
        )
        for r in results
    ]


@router.patch("/alerts/{alert_id}")
async def update_fraud_alert_status(
    alert_id: UUID,
    request: UpdateScanStatusRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> JSONDict:
    """
    Update fraud alert status (reviewed, false_positive, confirmed, etc.).
    """
    stmt = (
        select(FraudScanResult)
        .where(
            and_(
                FraudScanResult.id == alert_id,
                FraudScanResult.company_id == company_id,
            )
        )
    )
    result = await db.execute(stmt)
    scan_result = result.scalar_one_or_none()

    if not scan_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fraud-Alert nicht gefunden",
        )

    scan_result.status = request.status
    scan_result.reviewed_by_id = current_user.id
    scan_result.reviewed_at = datetime.now(timezone.utc)
    if request.notes:
        scan_result.review_notes = request.notes

    await db.commit()

    return {
        "success": True,
        "alert_id": str(alert_id),
        "new_status": request.status,
    }


# =============================================================================
# Statistics Endpoints
# =============================================================================


@router.get("/statistics", response_model=FraudStatisticsSchema)
async def get_fraud_statistics(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> FraudStatisticsSchema:
    """
    Get fraud detection statistics.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Count by scan type
    type_stmt = (
        select(
            FraudScanResult.scan_type,
            func.count(FraudScanResult.id).label("count"),
        )
        .where(
            and_(
                FraudScanResult.company_id == company_id,
                FraudScanResult.created_at >= cutoff,
            )
        )
        .group_by(FraudScanResult.scan_type)
    )
    type_result = await db.execute(type_stmt)
    by_type = {row[0]: row[1] for row in type_result.all()}

    # Count by risk level
    risk_stmt = (
        select(
            FraudScanResult.risk_level,
            func.count(FraudScanResult.id).label("count"),
        )
        .where(
            and_(
                FraudScanResult.company_id == company_id,
                FraudScanResult.created_at >= cutoff,
            )
        )
        .group_by(FraudScanResult.risk_level)
    )
    risk_result = await db.execute(risk_stmt)
    by_risk = {row[0]: row[1] for row in risk_result.all()}

    # Count by status
    status_stmt = (
        select(
            FraudScanResult.status,
            func.count(FraudScanResult.id).label("count"),
        )
        .where(
            and_(
                FraudScanResult.company_id == company_id,
                FraudScanResult.created_at >= cutoff,
            )
        )
        .group_by(FraudScanResult.status)
    )
    status_result = await db.execute(status_stmt)
    by_status = {row[0]: row[1] for row in status_result.all()}

    # Average risk score
    avg_stmt = (
        select(func.avg(FraudScanResult.risk_score))
        .where(
            and_(
                FraudScanResult.company_id == company_id,
                FraudScanResult.created_at >= cutoff,
            )
        )
    )
    avg_result = await db.execute(avg_stmt)
    avg_risk = avg_result.scalar() or 0.0

    total_scans = sum(by_type.values())

    return FraudStatisticsSchema(
        analysis_period_days=days,
        total_scans=total_scans,
        by_scan_type=by_type,
        by_risk_level=by_risk,
        by_status=by_status,
        average_risk_score=round(avg_risk, 4),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
