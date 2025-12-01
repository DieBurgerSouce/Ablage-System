# -*- coding: utf-8 -*-
"""
Production Readiness API Endpoints.

Bietet Admin-Endpoints fuer:
- Production Readiness Check durchfuehren
- Status-Uebersicht abrufen
- Deployment-Checkliste
- Empfehlungen vor Go-Live

Alle Endpoints erfordern Superuser-Authentifizierung.
"""

from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_superuser
from app.db.models import User
from app.services.production_readiness_service import (
    CheckCategory,
    ReadinessStatus,
    get_production_readiness_service,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/readiness", tags=["readiness"])


# =============================================================================
# PYDANTIC MODELS
# =============================================================================


class ReadinessCheckResponse(BaseModel):
    """Response fuer einzelnen Check."""

    name: str
    category: str
    status: str
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)
    recommendation: Optional[str] = None


class ReadinessSummaryResponse(BaseModel):
    """Response fuer Summary."""

    total: int
    ready: int
    warnings: int
    not_ready: int
    critical: int


class ReadinessReportResponse(BaseModel):
    """Response fuer vollstaendigen Readiness Report."""

    timestamp: str
    overall_status: str
    overall_score: float
    total_checks: int
    passed_checks: int
    failed_checks: int
    summary: Dict[str, int]
    checks: List[ReadinessCheckResponse]


class DeploymentStatusResponse(BaseModel):
    """Response fuer Deployment-Status."""

    ready_for_production: bool
    overall_status: str
    overall_score: float
    blocking_issues: int
    warnings: int
    message: str
    next_steps: List[str]


class CategoryReportResponse(BaseModel):
    """Response fuer Kategorie-Report."""

    category: str
    total_checks: int
    passed_checks: int
    failed_checks: int
    status: str
    checks: List[ReadinessCheckResponse]


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.get("/check", response_model=ReadinessReportResponse)
async def run_readiness_check(
    current_user: User = Depends(get_current_superuser),
) -> ReadinessReportResponse:
    """
    Fuehrt vollstaendigen Production Readiness Check durch.

    Prueft:
    - Security (Score, kritische Issues)
    - Performance (P99 Latenz, Error Rate)
    - Health (Database, Redis, GPU)
    - Konfiguration (Debug-Modus, Rate Limiting, CSRF)
    - Ressourcen (CPU, RAM, Disk)

    **Erfordert Superuser-Authentifizierung.**

    Returns:
        Vollstaendiger Readiness-Report mit Score und Checks
    """
    service = get_production_readiness_service()
    report = await service.run_readiness_check()

    logger.warning(
        "production_readiness_check_executed",
        user_id=str(current_user.id),
        user_email=current_user.email,
        status=report.overall_status.value,
        score=report.overall_score,
    )

    return ReadinessReportResponse(
        timestamp=report.timestamp.isoformat(),
        overall_status=report.overall_status.value,
        overall_score=report.overall_score,
        total_checks=len(report.checks),
        passed_checks=sum(
            1 for c in report.checks
            if c.status in (ReadinessStatus.READY, ReadinessStatus.WARNINGS)
        ),
        failed_checks=sum(
            1 for c in report.checks
            if c.status in (ReadinessStatus.NOT_READY, ReadinessStatus.CRITICAL)
        ),
        summary=report.summary,
        checks=[
            ReadinessCheckResponse(
                name=c.name,
                category=c.category.value,
                status=c.status.value,
                message=c.message,
                details=c.details,
                recommendation=c.recommendation,
            )
            for c in report.checks
        ],
    )


@router.get("/status", response_model=DeploymentStatusResponse)
async def get_deployment_status(
    current_user: User = Depends(get_current_superuser),
) -> DeploymentStatusResponse:
    """
    Gibt den aktuellen Deployment-Status zurueck.

    Schnelle Uebersicht ob das System production-ready ist.

    **Erfordert Superuser-Authentifizierung.**
    """
    service = get_production_readiness_service()
    report = await service.run_readiness_check()

    blocking_issues = sum(
        1 for c in report.checks
        if c.status in (ReadinessStatus.NOT_READY, ReadinessStatus.CRITICAL)
    )
    warnings = sum(
        1 for c in report.checks
        if c.status == ReadinessStatus.WARNINGS
    )

    ready_for_production = (
        report.overall_status in (ReadinessStatus.READY, ReadinessStatus.WARNINGS)
        and blocking_issues == 0
    )

    # Naechste Schritte basierend auf Status
    next_steps = []
    if report.overall_status == ReadinessStatus.CRITICAL:
        next_steps.append("KRITISCH: Behebe alle kritischen Issues sofort")
        for c in report.checks:
            if c.status == ReadinessStatus.CRITICAL and c.recommendation:
                next_steps.append(f"- {c.recommendation}")
    elif report.overall_status == ReadinessStatus.NOT_READY:
        next_steps.append("Behebe blockierende Issues vor Deployment")
        for c in report.checks:
            if c.status == ReadinessStatus.NOT_READY and c.recommendation:
                next_steps.append(f"- {c.recommendation}")
    elif report.overall_status == ReadinessStatus.WARNINGS:
        next_steps.append("System ist deployment-faehig mit Einschraenkungen")
        next_steps.append("Empfohlen: Behebe Warnungen fuer optimale Stabilitaet")
    else:
        next_steps.append("System ist production-ready")
        next_steps.append("Empfohlen: Regelmaessige Readiness-Checks durchfuehren")

    # Status-Nachricht
    if ready_for_production:
        if warnings > 0:
            message = f"Production-Ready mit {warnings} Warnungen"
        else:
            message = "Vollstaendig Production-Ready"
    else:
        message = f"Nicht Production-Ready: {blocking_issues} blockierende Issues"

    logger.info(
        "deployment_status_retrieved",
        user_id=str(current_user.id),
        ready=ready_for_production,
        score=report.overall_score,
    )

    return DeploymentStatusResponse(
        ready_for_production=ready_for_production,
        overall_status=report.overall_status.value,
        overall_score=report.overall_score,
        blocking_issues=blocking_issues,
        warnings=warnings,
        message=message,
        next_steps=next_steps,
    )


@router.get("/category/{category}", response_model=CategoryReportResponse)
async def get_category_report(
    category: str,
    current_user: User = Depends(get_current_superuser),
) -> CategoryReportResponse:
    """
    Gibt Readiness-Report fuer eine bestimmte Kategorie zurueck.

    Verfuegbare Kategorien:
    - security: Sicherheits-Checks
    - performance: Performance-Checks
    - health: System-Health-Checks
    - configuration: Konfigurations-Checks
    - resources: Ressourcen-Checks

    **Erfordert Superuser-Authentifizierung.**
    """
    # Validiere Kategorie
    valid_categories = [c.value for c in CheckCategory]
    if category not in valid_categories:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=f"Ungueltige Kategorie. Erlaubt: {valid_categories}"
        )

    service = get_production_readiness_service()
    report = await service.run_readiness_check()

    # Filtere Checks nach Kategorie
    category_checks = [
        c for c in report.checks
        if c.category.value == category
    ]

    passed = sum(
        1 for c in category_checks
        if c.status in (ReadinessStatus.READY, ReadinessStatus.WARNINGS)
    )
    failed = len(category_checks) - passed

    # Bestimme Kategorie-Status
    if any(c.status == ReadinessStatus.CRITICAL for c in category_checks):
        cat_status = "critical"
    elif any(c.status == ReadinessStatus.NOT_READY for c in category_checks):
        cat_status = "not_ready"
    elif any(c.status == ReadinessStatus.WARNINGS for c in category_checks):
        cat_status = "warnings"
    else:
        cat_status = "ready"

    return CategoryReportResponse(
        category=category,
        total_checks=len(category_checks),
        passed_checks=passed,
        failed_checks=failed,
        status=cat_status,
        checks=[
            ReadinessCheckResponse(
                name=c.name,
                category=c.category.value,
                status=c.status.value,
                message=c.message,
                details=c.details,
                recommendation=c.recommendation,
            )
            for c in category_checks
        ],
    )


@router.get("/blockers")
async def get_blocking_issues(
    current_user: User = Depends(get_current_superuser),
):
    """
    Gibt nur blockierende Issues zurueck.

    Nuetzlich fuer schnelle Uebersicht der kritischen Probleme
    die vor einem Production-Deployment behoben werden muessen.

    **Erfordert Superuser-Authentifizierung.**
    """
    service = get_production_readiness_service()
    report = await service.run_readiness_check()

    blockers = [
        c.to_dict()
        for c in report.checks
        if c.status in (ReadinessStatus.NOT_READY, ReadinessStatus.CRITICAL)
    ]

    critical_count = sum(1 for b in blockers if b["status"] == "critical")
    not_ready_count = sum(1 for b in blockers if b["status"] == "not_ready")

    return {
        "total_blockers": len(blockers),
        "critical_count": critical_count,
        "not_ready_count": not_ready_count,
        "blockers": blockers,
        "deployment_blocked": len(blockers) > 0,
        "message": (
            f"Deployment blockiert: {critical_count} kritische und {not_ready_count} nicht-bereite Issues"
            if blockers
            else "Keine blockierenden Issues - Deployment moeglich"
        ),
    }


@router.get("/checklist")
async def get_deployment_checklist(
    current_user: User = Depends(get_current_superuser),
):
    """
    Gibt eine Deployment-Checkliste zurueck.

    Zeigt alle Pruefpunkte mit Status, sortiert nach Wichtigkeit.

    **Erfordert Superuser-Authentifizierung.**
    """
    service = get_production_readiness_service()
    report = await service.run_readiness_check()

    checklist = []
    for check in report.checks:
        icon = {
            ReadinessStatus.READY: "OK",
            ReadinessStatus.WARNINGS: "WARNUNG",
            ReadinessStatus.NOT_READY: "NICHT_BEREIT",
            ReadinessStatus.CRITICAL: "KRITISCH",
        }.get(check.status, "UNBEKANNT")

        checklist.append({
            "status_icon": icon,
            "name": check.name,
            "category": check.category.value,
            "status": check.status.value,
            "message": check.message,
            "recommendation": check.recommendation,
        })

    # Sortieren: Critical > Not Ready > Warnings > Ready
    status_order = {
        ReadinessStatus.CRITICAL.value: 0,
        ReadinessStatus.NOT_READY.value: 1,
        ReadinessStatus.WARNINGS.value: 2,
        ReadinessStatus.READY.value: 3,
    }
    checklist.sort(key=lambda x: status_order.get(x["status"], 4))

    return {
        "checklist": checklist,
        "total": len(checklist),
        "passed": sum(1 for c in checklist if c["status"] in ("ready", "warnings")),
        "failed": sum(1 for c in checklist if c["status"] in ("not_ready", "critical")),
        "overall_score": report.overall_score,
        "overall_status": report.overall_status.value,
    }


@router.get("/recommendations")
async def get_recommendations(
    current_user: User = Depends(get_current_superuser),
    include_passed: bool = Query(False, description="Auch bestandene Checks einbeziehen"),
):
    """
    Gibt priorisierte Empfehlungen zurueck.

    Empfehlungen sind nach Prioritaet sortiert.

    **Erfordert Superuser-Authentifizierung.**
    """
    service = get_production_readiness_service()
    report = await service.run_readiness_check()

    # Filtere Checks mit Empfehlungen
    if include_passed:
        checks_with_recommendations = [
            c for c in report.checks if c.recommendation
        ]
    else:
        checks_with_recommendations = [
            c for c in report.checks
            if c.recommendation and c.status not in (ReadinessStatus.READY,)
        ]

    # Sortieren nach Severity
    status_order = {
        ReadinessStatus.CRITICAL: 0,
        ReadinessStatus.NOT_READY: 1,
        ReadinessStatus.WARNINGS: 2,
        ReadinessStatus.READY: 3,
    }
    checks_with_recommendations.sort(key=lambda c: status_order.get(c.status, 4))

    recommendations = []
    for idx, check in enumerate(checks_with_recommendations, 1):
        recommendations.append({
            "prioritaet": idx,
            "name": check.name,
            "kategorie": check.category.value,
            "schweregrad": check.status.value,
            "nachricht": check.message,
            "empfehlung": check.recommendation,
        })

    return {
        "total_empfehlungen": len(recommendations),
        "empfehlungen": recommendations,
        "naechste_aktion": recommendations[0] if recommendations else None,
        "deployment_empfehlung": (
            "Alle Empfehlungen umsetzen vor Production-Deployment"
            if any(r["schweregrad"] in ("critical", "not_ready") for r in recommendations)
            else "System ist grundsaetzlich production-ready"
        ),
    }


@router.get("/summary")
async def get_quick_summary(
    current_user: User = Depends(get_current_superuser),
):
    """
    Gibt schnelle Zusammenfassung zurueck.

    Kompakte Uebersicht fuer Dashboards und Monitoring.

    **Erfordert Superuser-Authentifizierung.**
    """
    service = get_production_readiness_service()
    report = await service.run_readiness_check()

    # Kategorie-Zusammenfassung
    by_category = {}
    for cat in CheckCategory:
        cat_checks = [c for c in report.checks if c.category == cat]
        if cat_checks:
            passed = sum(
                1 for c in cat_checks
                if c.status in (ReadinessStatus.READY, ReadinessStatus.WARNINGS)
            )
            by_category[cat.value] = {
                "total": len(cat_checks),
                "passed": passed,
                "failed": len(cat_checks) - passed,
                "percent": round((passed / len(cat_checks)) * 100, 1),
            }

    return {
        "timestamp": report.timestamp.isoformat(),
        "overall_status": report.overall_status.value,
        "overall_score": report.overall_score,
        "ready_for_production": report.overall_status in (
            ReadinessStatus.READY, ReadinessStatus.WARNINGS
        ) and not any(
            c.status in (ReadinessStatus.NOT_READY, ReadinessStatus.CRITICAL)
            for c in report.checks
        ),
        "summary": {
            "total": len(report.checks),
            "ready": sum(1 for c in report.checks if c.status == ReadinessStatus.READY),
            "warnings": sum(1 for c in report.checks if c.status == ReadinessStatus.WARNINGS),
            "not_ready": sum(1 for c in report.checks if c.status == ReadinessStatus.NOT_READY),
            "critical": sum(1 for c in report.checks if c.status == ReadinessStatus.CRITICAL),
        },
        "by_category": by_category,
    }
