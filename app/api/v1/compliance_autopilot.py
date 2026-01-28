"""
API Router für Compliance Autopilot.

Endpoints für automatische Compliance-Checks und Audit-Vorbereitung.
"""

from datetime import date
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.db.models import User
from app.services.compliance.autopilot_service import (
    ComplianceAutopilotService,
    ComplianceItem,
    ComplianceScanResult,
    RetentionReport,
    GDPRCheckResult,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/compliance-autopilot", tags=["compliance-autopilot"])


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================


class ComplianceItemResponse(BaseModel):
    """Compliance-Item Response."""

    check_name: str
    category: str
    status: str
    description: str
    recommendation: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class ComplianceScanResponse(BaseModel):
    """Compliance-Scan Response."""

    total_checks: int
    passed: int
    warnings: int
    failures: int
    score: float
    items: List[ComplianceItemResponse]

    class Config:
        from_attributes = True


class RetentionReportResponse(BaseModel):
    """Retention-Report Response."""

    documents_total: int
    documents_expired: int
    documents_expiring_soon: int
    expired_document_ids: List[UUID]
    expiring_soon_ids: List[UUID]
    retention_by_type: Dict[str, Dict[str, int]]

    class Config:
        from_attributes = True


class GDPRCheckResponse(BaseModel):
    """GDPR-Check Response."""

    compliant: bool
    issues: List[str]
    recommendations: List[str]
    personal_data_count: int
    deletion_candidates: int

    class Config:
        from_attributes = True


class AuditPreparationRequest(BaseModel):
    """Request für Audit-Vorbereitung."""

    start_date: date = Field(..., description="Start-Datum (YYYY-MM-DD)")
    end_date: date = Field(..., description="End-Datum (YYYY-MM-DD)")


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.post("/scan", response_model=ComplianceScanResponse)
async def run_compliance_scan(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ComplianceScanResponse:
    """
    Führt vollständigen Compliance-Scan durch.

    Prüft:
    - GDPR-Compliance (Löschfristen, Audit-Trail)
    - GoBD-Compliance (Unveränderbarkeit, Nachvollziehbarkeit)
    - Aufbewahrungsfristen (§147 AO)
    - Security-Checks

    Args:
        current_user: Aktueller Benutzer
        db: Datenbank-Session

    Returns:
        Compliance-Scan-Ergebnis mit Score (0-100)
    """
    logger.info(
        "compliance_scan_requested",
        user_id=str(current_user.id),
        company_id=str(current_user.company_id),
    )

    try:
        service = ComplianceAutopilotService()
        result = await service.run_compliance_scan(
            company_id=current_user.company_id,
            db=db,
        )

        return ComplianceScanResponse(
            total_checks=result.total_checks,
            passed=result.passed,
            warnings=result.warnings,
            failures=result.failures,
            score=result.score,
            items=[
                ComplianceItemResponse(
                    check_name=item.check_name,
                    category=item.category,
                    status=item.status,
                    description=item.description,
                    recommendation=item.recommendation,
                    details=item.details,
                )
                for item in result.items
            ],
        )

    except Exception as e:
        logger.error("compliance_scan_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Compliance-Scan",
        )


@router.get("/retention", response_model=RetentionReportResponse)
async def get_retention_report(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RetentionReportResponse:
    """
    Gibt Aufbewahrungsfristen-Report zurück.

    Zeigt:
    - Abgelaufene Aufbewahrungsfristen
    - Bald ablaufende Fristen (30 Tage)
    - Statistik nach Dokumenttyp

    Args:
        current_user: Aktueller Benutzer
        db: Datenbank-Session

    Returns:
        Retention-Report
    """
    logger.info(
        "retention_report_requested",
        user_id=str(current_user.id),
    )

    try:
        service = ComplianceAutopilotService()
        report = await service.check_retention(
            company_id=current_user.company_id,
            db=db,
        )

        return RetentionReportResponse(
            documents_total=report.documents_total,
            documents_expired=report.documents_expired,
            documents_expiring_soon=report.documents_expiring_soon,
            expired_document_ids=report.expired_document_ids,
            expiring_soon_ids=report.expiring_soon_ids,
            retention_by_type=report.retention_by_type,
        )

    except Exception as e:
        logger.error("retention_report_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen des Retention-Reports",
        )


@router.post("/audit-preparation")
async def prepare_audit_package(
    request: AuditPreparationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Bereitet Audit-Paket für Steuerprüfung vor.

    Erstellt ZIP-Archiv mit:
    - Relevanten Dokumenten im Zeitraum
    - Index-Datei
    - Dokumenten nach Typ sortiert

    Args:
        request: Audit-Request mit Zeitraum
        current_user: Aktueller Benutzer
        db: Datenbank-Session

    Returns:
        ZIP-Archiv als StreamingResponse
    """
    logger.info(
        "audit_preparation_requested",
        user_id=str(current_user.id),
        date_range=(request.start_date, request.end_date),
    )

    try:
        service = ComplianceAutopilotService()
        package = await service.prepare_audit(
            company_id=current_user.company_id,
            date_range=(request.start_date, request.end_date),
            db=db,
        )

        # StreamingResponse zurückgeben
        import io

        return StreamingResponse(
            io.BytesIO(package.zip_content),
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={package.filename}"},
        )

    except Exception as e:
        logger.error("audit_preparation_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler bei der Audit-Vorbereitung",
        )


@router.post("/gdpr-check", response_model=GDPRCheckResponse)
async def run_gdpr_check(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GDPRCheckResponse:
    """
    Führt GDPR-Compliance-Check durch.

    Prüft:
    - Löschfristen für personenbezogene Daten
    - Audit-Trail vorhanden
    - Löschkandidaten

    Args:
        current_user: Aktueller Benutzer
        db: Datenbank-Session

    Returns:
        GDPR-Check-Ergebnis
    """
    logger.info(
        "gdpr_check_requested",
        user_id=str(current_user.id),
    )

    try:
        service = ComplianceAutopilotService()
        result = await service.run_gdpr_check(
            company_id=current_user.company_id,
            db=db,
        )

        return GDPRCheckResponse(
            compliant=result.compliant,
            issues=result.issues,
            recommendations=result.recommendations,
            personal_data_count=result.personal_data_count,
            deletion_candidates=result.deletion_candidates,
        )

    except Exception as e:
        logger.error("gdpr_check_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim GDPR-Check",
        )


@router.get("/status", response_model=ComplianceScanResponse)
async def get_last_scan_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ComplianceScanResponse:
    """
    Gibt letzten Scan-Status zurück (oder führt neuen Scan durch).

    Args:
        current_user: Aktueller Benutzer
        db: Datenbank-Session

    Returns:
        Letzter Compliance-Scan
    """
    logger.info(
        "compliance_status_requested",
        user_id=str(current_user.id),
    )

    # Für MVP: Immer neuen Scan durchführen
    # In Production: Aus Cache/DB abrufen wenn < 24h alt
    try:
        service = ComplianceAutopilotService()
        result = await service.run_compliance_scan(
            company_id=current_user.company_id,
            db=db,
        )

        return ComplianceScanResponse(
            total_checks=result.total_checks,
            passed=result.passed,
            warnings=result.warnings,
            failures=result.failures,
            score=result.score,
            items=[
                ComplianceItemResponse(
                    check_name=item.check_name,
                    category=item.category,
                    status=item.status,
                    description=item.description,
                    recommendation=item.recommendation,
                    details=item.details,
                )
                for item in result.items
            ],
        )

    except Exception as e:
        logger.error("compliance_status_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen des Compliance-Status",
        )
