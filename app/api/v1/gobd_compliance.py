"""
GoBD Compliance API Endpoints - Vision 2026

Endpoints for GoBD compliance management including:
- Compliance status dashboard
- Run compliance checks
- View check history
- Generate compliance reports
- Export for auditors
"""

from datetime import date, datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_active_user
from app.middleware.company_context import require_company
from app.services.compliance.gobd_service import (
    GoBDComplianceService,
    gobd_compliance_service,
    CheckResult,
    ComplianceDashboard,
)
from app.db.models import User, Company
from app.db.models_compliance import (
    GoBDComplianceCheck,
    GoBDComplianceHistory,
    GoBDComplianceReport,
    GoBDCheckType,
    ComplianceStatus,
    ComplianceReportType,
)

import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/gobd", tags=["GoBD Compliance"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


class CheckTypeInfo(BaseModel):
    """Information ueber einen Check-Typ."""
    check_type: str
    name: str
    description: str


class ComplianceCheckResponse(BaseModel):
    """Antwort fuer einen Compliance-Check."""
    id: UUID
    check_type: str
    check_name: str
    status: str
    status_color: str
    score: Optional[int]
    issues_found: int
    last_checked_at: Optional[str]
    next_check_at: Optional[str]
    remediation_steps: List[str]

    model_config = ConfigDict(from_attributes=True)


class CheckResultResponse(BaseModel):
    """Antwort fuer ein Check-Ergebnis."""
    check_type: str
    status: str
    score: int
    issues_found: int
    details: dict
    affected_documents: List[str]
    remediation_steps: List[str]
    execution_time_ms: int


class ComplianceDashboardResponse(BaseModel):
    """Antwort fuer das Compliance-Dashboard."""
    overall_score: int
    overall_status: str
    overall_status_color: str
    checks_passed: int
    checks_warning: int
    checks_failed: int
    total_checks: int
    last_check_at: Optional[str]
    next_check_at: Optional[str]
    critical_issues: List[dict]
    checks: List[ComplianceCheckResponse]


class ComplianceHistoryResponse(BaseModel):
    """Antwort fuer Historie-Eintrag."""
    id: UUID
    check_type: str
    status: str
    score: Optional[int]
    issues_found: int
    triggered_by: Optional[str]
    checked_at: str

    model_config = ConfigDict(from_attributes=True)


class ComplianceReportResponse(BaseModel):
    """Antwort fuer einen Compliance-Bericht."""
    id: UUID
    report_type: str
    title: str
    description: Optional[str]
    period_start: Optional[str]
    period_end: Optional[str]
    overall_score: Optional[int]
    overall_status: str
    summary: dict
    recommendations: List[str]
    generated_at: str
    is_exported: bool

    model_config = ConfigDict(from_attributes=True)


class GenerateReportRequest(BaseModel):
    """Request fuer Berichtsgenerierung."""
    report_type: str = Field(ComplianceReportType.FULL.value, description="Berichtstyp")
    period_start: Optional[date] = Field(None, description="Periodenstart")
    period_end: Optional[date] = Field(None, description="Periodenende")


# =============================================================================
# Helper Functions
# =============================================================================


def _status_to_color(status: str) -> str:
    """Convert status to color for UI."""
    if status == ComplianceStatus.PASSED.value:
        return "green"
    elif status == ComplianceStatus.WARNING.value:
        return "yellow"
    elif status == ComplianceStatus.FAILED.value:
        return "red"
    elif status == ComplianceStatus.NOT_APPLICABLE.value:
        return "gray"
    return "blue"


def _check_type_name(check_type: str) -> str:
    """Get German name for check type."""
    names = {
        GoBDCheckType.NACHVOLLZIEHBARKEIT.value: "Nachvollziehbarkeit",
        GoBDCheckType.NACHPRUEFBARKEIT.value: "Nachpruefbarkeit",
        GoBDCheckType.UNVERAENDERBARKEIT.value: "Unveraenderbarkeit",
        GoBDCheckType.VOLLSTAENDIGKEIT.value: "Vollstaendigkeit",
        GoBDCheckType.ORDNUNG.value: "Ordnung",
        GoBDCheckType.ZEITGERECHTE_BUCHUNG.value: "Zeitgerechte Buchung",
        GoBDCheckType.AUFBEWAHRUNG.value: "Aufbewahrung",
        GoBDCheckType.MASCHINELLE_AUSWERTBARKEIT.value: "Maschinelle Auswertbarkeit",
        GoBDCheckType.VERFAHRENSDOKUMENTATION.value: "Verfahrensdokumentation",
        GoBDCheckType.DATENSICHERUNG.value: "Datensicherung",
        GoBDCheckType.ZUGANGSKONTROLLE.value: "Zugangskontrolle",
    }
    return names.get(check_type, check_type)


def _check_to_response(check: GoBDComplianceCheck) -> ComplianceCheckResponse:
    """Convert check model to response."""
    return ComplianceCheckResponse(
        id=check.id,
        check_type=check.check_type,
        check_name=_check_type_name(check.check_type),
        status=check.status,
        status_color=_status_to_color(check.status),
        score=check.score,
        issues_found=check.issues_found,
        last_checked_at=check.last_checked_at.isoformat() if check.last_checked_at else None,
        next_check_at=check.next_check_at.isoformat() if check.next_check_at else None,
        remediation_steps=check.remediation_steps or [],
    )


# =============================================================================
# Dashboard & Status Endpoints
# =============================================================================


@router.get("/dashboard", response_model=ComplianceDashboardResponse)
async def get_compliance_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ComplianceDashboardResponse:
    """GoBD-Compliance-Dashboard abrufen."""
    dashboard = await gobd_compliance_service.get_dashboard(db, company.id)

    # Get all checks
    from sqlalchemy import select
    checks_result = await db.execute(
        select(GoBDComplianceCheck)
        .where(GoBDComplianceCheck.company_id == company.id)
    )
    checks = list(checks_result.scalars().all())

    return ComplianceDashboardResponse(
        overall_score=dashboard.overall_score,
        overall_status=dashboard.overall_status,
        overall_status_color=_status_to_color(dashboard.overall_status),
        checks_passed=dashboard.checks_passed,
        checks_warning=dashboard.checks_warning,
        checks_failed=dashboard.checks_failed,
        total_checks=dashboard.checks_passed + dashboard.checks_warning + dashboard.checks_failed,
        last_check_at=dashboard.last_check_at.isoformat() if dashboard.last_check_at else None,
        next_check_at=dashboard.next_check_at.isoformat() if dashboard.next_check_at else None,
        critical_issues=dashboard.critical_issues,
        checks=[_check_to_response(c) for c in checks],
    )


@router.get("/check-types", response_model=List[CheckTypeInfo])
async def list_check_types(
    current_user: User = Depends(get_current_active_user),
) -> List[CheckTypeInfo]:
    """Verfuegbare GoBD-Check-Typen auflisten."""
    descriptions = {
        GoBDCheckType.NACHVOLLZIEHBARKEIT.value: "Prueft Audit-Trail fuer alle Aktionen",
        GoBDCheckType.NACHPRUEFBARKEIT.value: "Prueft Datenintegritaet",
        GoBDCheckType.UNVERAENDERBARKEIT.value: "Verifiziert Hash-Signaturen",
        GoBDCheckType.VOLLSTAENDIGKEIT.value: "Prueft auf lueckenlose Belegnummern",
        GoBDCheckType.ORDNUNG.value: "Prueft systematische Ablage",
        GoBDCheckType.ZEITGERECHTE_BUCHUNG.value: "Prueft Erfassungsfristen",
        GoBDCheckType.AUFBEWAHRUNG.value: "Prueft Aufbewahrungsfristen (10 Jahre)",
        GoBDCheckType.MASCHINELLE_AUSWERTBARKEIT.value: "Prueft Export-Faehigkeit",
        GoBDCheckType.VERFAHRENSDOKUMENTATION.value: "Prueft Verfahrensdokumentation",
        GoBDCheckType.DATENSICHERUNG.value: "Prueft Backup-Status",
        GoBDCheckType.ZUGANGSKONTROLLE.value: "Prueft Berechtigungen",
    }

    return [
        CheckTypeInfo(
            check_type=ct.value,
            name=_check_type_name(ct.value),
            description=descriptions.get(ct.value, ""),
        )
        for ct in GoBDCheckType
    ]


# =============================================================================
# Check Endpoints
# =============================================================================


@router.post("/run-all-checks", response_model=List[CheckResultResponse])
async def run_all_checks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> List[CheckResultResponse]:
    """Alle GoBD-Compliance-Checks durchfuehren."""
    logger.info(
        "Starte alle Compliance-Checks",
        company_id=str(company.id),
        user_id=str(current_user.id)
    )

    results = await gobd_compliance_service.run_all_checks(
        db,
        company_id=company.id,
        triggered_by="manual",
        executed_by_id=current_user.id,
    )
    await db.commit()

    return [
        CheckResultResponse(
            check_type=r.check_type,
            status=r.status,
            score=r.score,
            issues_found=r.issues_found,
            details=r.details,
            affected_documents=r.affected_documents,
            remediation_steps=r.remediation_steps,
            execution_time_ms=r.execution_time_ms,
        )
        for r in results
    ]


@router.post("/run-check/{check_type}", response_model=CheckResultResponse)
async def run_single_check(
    check_type: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> CheckResultResponse:
    """Einzelnen GoBD-Compliance-Check durchfuehren."""
    # Validate check type
    valid_types = [ct.value for ct in GoBDCheckType]
    if check_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Ungueltiger Check-Typ: {check_type}. Gueltige Typen: {valid_types}"
        )

    logger.info(
        "Starte Compliance-Check",
        check_type=check_type,
        company_id=str(company.id),
        user_id=str(current_user.id)
    )

    result = await gobd_compliance_service.run_check(
        db,
        company_id=company.id,
        check_type=check_type,
        triggered_by="manual",
        executed_by_id=current_user.id,
    )
    await db.commit()

    return CheckResultResponse(
        check_type=result.check_type,
        status=result.status,
        score=result.score,
        issues_found=result.issues_found,
        details=result.details,
        affected_documents=result.affected_documents,
        remediation_steps=result.remediation_steps,
        execution_time_ms=result.execution_time_ms,
    )


@router.get("/checks/{check_type}", response_model=ComplianceCheckResponse)
async def get_check_status(
    check_type: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ComplianceCheckResponse:
    """Status eines bestimmten Compliance-Checks abrufen."""
    from sqlalchemy import select, and_

    result = await db.execute(
        select(GoBDComplianceCheck)
        .where(
            and_(
                GoBDComplianceCheck.company_id == company.id,
                GoBDComplianceCheck.check_type == check_type
            )
        )
    )
    check = result.scalar_one_or_none()

    if not check:
        raise HTTPException(status_code=404, detail="Check nicht gefunden")

    return _check_to_response(check)


# =============================================================================
# History Endpoints
# =============================================================================


@router.get("/history", response_model=List[ComplianceHistoryResponse])
async def get_check_history(
    check_type: Optional[str] = Query(None, description="Filter nach Check-Typ"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> List[ComplianceHistoryResponse]:
    """Compliance-Check-Historie abrufen."""
    from sqlalchemy import select, and_, desc

    query = select(GoBDComplianceHistory).where(
        GoBDComplianceHistory.company_id == company.id
    )

    if check_type:
        query = query.where(GoBDComplianceHistory.check_type == check_type)

    query = query.order_by(desc(GoBDComplianceHistory.checked_at))
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    history = list(result.scalars().all())

    return [
        ComplianceHistoryResponse(
            id=h.id,
            check_type=h.check_type,
            status=h.status,
            score=h.score,
            issues_found=h.issues_found,
            triggered_by=h.triggered_by,
            checked_at=h.checked_at.isoformat(),
        )
        for h in history
    ]


# =============================================================================
# Report Endpoints
# =============================================================================


@router.post("/reports", response_model=ComplianceReportResponse, status_code=status.HTTP_201_CREATED)
async def generate_report(
    request: GenerateReportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ComplianceReportResponse:
    """Compliance-Bericht generieren."""
    logger.info(
        "Generiere Compliance-Bericht",
        report_type=request.report_type,
        company_id=str(company.id),
        user_id=str(current_user.id)
    )

    report = await gobd_compliance_service.generate_report(
        db,
        company_id=company.id,
        report_type=request.report_type,
        period_start=request.period_start,
        period_end=request.period_end,
        generated_by_id=current_user.id,
    )
    await db.commit()

    return ComplianceReportResponse(
        id=report.id,
        report_type=report.report_type,
        title=report.title,
        description=report.description,
        period_start=report.period_start.isoformat() if report.period_start else None,
        period_end=report.period_end.isoformat() if report.period_end else None,
        overall_score=report.overall_score,
        overall_status=report.overall_status,
        summary=report.summary,
        recommendations=report.recommendations,
        generated_at=report.generated_at.isoformat(),
        is_exported=report.is_exported,
    )


@router.get("/reports", response_model=List[ComplianceReportResponse])
async def list_reports(
    report_type: Optional[str] = Query(None, description="Filter nach Berichtstyp"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> List[ComplianceReportResponse]:
    """Compliance-Berichte auflisten."""
    from sqlalchemy import select, desc

    query = select(GoBDComplianceReport).where(
        GoBDComplianceReport.company_id == company.id
    )

    if report_type:
        query = query.where(GoBDComplianceReport.report_type == report_type)

    query = query.order_by(desc(GoBDComplianceReport.generated_at))
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    reports = list(result.scalars().all())

    return [
        ComplianceReportResponse(
            id=r.id,
            report_type=r.report_type,
            title=r.title,
            description=r.description,
            period_start=r.period_start.isoformat() if r.period_start else None,
            period_end=r.period_end.isoformat() if r.period_end else None,
            overall_score=r.overall_score,
            overall_status=r.overall_status,
            summary=r.summary,
            recommendations=r.recommendations,
            generated_at=r.generated_at.isoformat(),
            is_exported=r.is_exported,
        )
        for r in reports
    ]


@router.get("/reports/{report_id}", response_model=ComplianceReportResponse)
async def get_report(
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ComplianceReportResponse:
    """Einzelnen Compliance-Bericht abrufen."""
    from sqlalchemy import select, and_

    result = await db.execute(
        select(GoBDComplianceReport)
        .where(
            and_(
                GoBDComplianceReport.id == report_id,
                GoBDComplianceReport.company_id == company.id
            )
        )
    )
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="Bericht nicht gefunden")

    return ComplianceReportResponse(
        id=report.id,
        report_type=report.report_type,
        title=report.title,
        description=report.description,
        period_start=report.period_start.isoformat() if report.period_start else None,
        period_end=report.period_end.isoformat() if report.period_end else None,
        overall_score=report.overall_score,
        overall_status=report.overall_status,
        summary=report.summary,
        recommendations=report.recommendations,
        generated_at=report.generated_at.isoformat(),
        is_exported=report.is_exported,
    )


@router.post("/reports/{report_id}/export")
async def export_report(
    report_id: UUID,
    export_to: Optional[str] = Query(None, description="Export-Ziel (z.B. Email-Adresse)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> dict:
    """Compliance-Bericht exportieren (fuer Steuerberater/Pruefer)."""
    from sqlalchemy import select, and_

    result = await db.execute(
        select(GoBDComplianceReport)
        .where(
            and_(
                GoBDComplianceReport.id == report_id,
                GoBDComplianceReport.company_id == company.id
            )
        )
    )
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="Bericht nicht gefunden")

    # Mark as exported
    report.is_exported = True
    report.exported_at = datetime.utcnow()
    report.exported_to = export_to

    await db.commit()

    logger.info(
        "Compliance-Bericht exportiert",
        report_id=str(report_id),
        exported_to=export_to,
        user_id=str(current_user.id)
    )

    return {
        "message": "Bericht erfolgreich exportiert",
        "report_id": str(report_id),
        "exported_at": report.exported_at.isoformat(),
        "exported_to": export_to,
    }
