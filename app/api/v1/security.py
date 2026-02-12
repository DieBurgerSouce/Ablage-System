# -*- coding: utf-8 -*-
"""
Security Audit API Endpoints.

Bietet Admin-Endpoints fuer:
- Security Audit durchfuehren
- Audit-Report abrufen
- Sicherheitsempfehlungen

Alle Endpoints erfordern Superuser-Authentifizierung.
"""

from typing import Dict, List

from app.core.types import JSONDict

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_superuser
from app.db.models import User
from app.services.security_audit_service import (
    AuditCategory,
    AuditSeverity,
    get_security_audit_service,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/security", tags=["security"])


# =============================================================================
# PYDANTIC MODELS
# =============================================================================


class AuditFindingResponse(BaseModel):
    """Response fuer einzelnes Finding."""

    id: str
    category: str
    severity: str
    title: str
    description: str
    recommendation: str
    affected_component: str
    passed: bool
    details: JSONDict


class AuditSummaryResponse(BaseModel):
    """Response fuer Audit-Summary."""

    total: int
    passed: int
    failed: int
    critical_failed: int
    high_failed: int
    medium_failed: int
    low_failed: int


class AuditReportResponse(BaseModel):
    """Response fuer vollstaendigen Audit-Report."""

    timestamp: str
    score: float
    passed: bool
    total_findings: int
    critical_count: int
    high_count: int
    summary: Dict[str, int]
    findings: List[AuditFindingResponse]


class SecurityScoreResponse(BaseModel):
    """Response fuer Security Score."""

    score: float
    grade: str
    passed: bool
    critical_issues: int
    high_issues: int
    recommendation: str


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.get("/audit", response_model=AuditReportResponse)
async def run_security_audit(
    current_user: User = Depends(get_current_superuser),
) -> AuditReportResponse:
    """
    Fuehrt einen vollstaendigen Security Audit durch.

    Prueft:
    - Konfigurationssicherheit
    - Credential-Management
    - Verschluesselung
    - Authentifizierung
    - Rate Limiting
    - CORS und CSRF
    - Logging-Konfiguration

    **Erfordert Superuser-Authentifizierung.**

    Returns:
        Vollstaendiger Audit-Report mit Score und Findings
    """
    service = get_security_audit_service()
    report = service.run_audit()

    logger.warning(
        "security_audit_executed",
        user_id=str(current_user.id),
        user_email=current_user.email,
        score=report.score,
        passed=report.passed,
    )

    return AuditReportResponse(
        timestamp=report.timestamp.isoformat(),
        score=report.score,
        passed=report.passed,
        total_findings=len(report.findings),
        critical_count=sum(
            1 for f in report.findings
            if f.severity == AuditSeverity.CRITICAL and not f.passed
        ),
        high_count=sum(
            1 for f in report.findings
            if f.severity == AuditSeverity.HIGH and not f.passed
        ),
        summary=report.summary,
        findings=[
            AuditFindingResponse(
                id=f.id,
                category=f.category.value,
                severity=f.severity.value,
                title=f.title,
                description=f.description,
                recommendation=f.recommendation,
                affected_component=f.affected_component,
                passed=f.passed,
                details=f.details,
            )
            for f in report.findings
        ],
    )


@router.get("/score", response_model=SecurityScoreResponse)
async def get_security_score(
    current_user: User = Depends(get_current_superuser),
) -> SecurityScoreResponse:
    """
    Gibt den aktuellen Security Score zurueck.

    Score-Bewertung:
    - A (90-100): Ausgezeichnet
    - B (80-89): Gut
    - C (70-79): Akzeptabel
    - D (60-69): Verbesserung noetig
    - F (<60): Kritisch

    **Erfordert Superuser-Authentifizierung.**
    """
    service = get_security_audit_service()
    report = service.run_audit()

    # Grade berechnen
    score = report.score
    if score >= 90:
        grade = "A"
        recommendation = "Ausgezeichnete Sicherheitskonfiguration. Weiter so!"
    elif score >= 80:
        grade = "B"
        recommendation = "Gute Sicherheit. Behebe die verbleibenden Issues fuer optimalen Schutz."
    elif score >= 70:
        grade = "C"
        recommendation = "Akzeptable Sicherheit. Es gibt mehrere Verbesserungsmoeglichkeiten."
    elif score >= 60:
        grade = "D"
        recommendation = "Verbesserung noetig. Behebe HIGH und CRITICAL Issues prioritaer."
    else:
        grade = "F"
        recommendation = "Kritische Sicherheitsprobleme! Sofortige Massnahmen erforderlich."

    critical_issues = sum(
        1 for f in report.findings
        if f.severity == AuditSeverity.CRITICAL and not f.passed
    )
    high_issues = sum(
        1 for f in report.findings
        if f.severity == AuditSeverity.HIGH and not f.passed
    )

    logger.info(
        "security_score_retrieved",
        user_id=str(current_user.id),
        score=score,
        grade=grade,
    )

    return SecurityScoreResponse(
        score=score,
        grade=grade,
        passed=report.passed,
        critical_issues=critical_issues,
        high_issues=high_issues,
        recommendation=recommendation,
    )


@router.get("/findings/critical")
async def get_critical_findings(
    current_user: User = Depends(get_current_superuser),
):
    """
    Gibt nur kritische und hohe Findings zurueck.

    Nuetzlich fuer schnelle Uebersicht der wichtigsten Probleme.

    **Erfordert Superuser-Authentifizierung.**
    """
    service = get_security_audit_service()
    report = service.run_audit()

    critical_findings = [
        f.to_dict()
        for f in report.findings
        if f.severity in (AuditSeverity.CRITICAL, AuditSeverity.HIGH) and not f.passed
    ]

    return {
        "total_critical_high": len(critical_findings),
        "findings": critical_findings,
        "action_required": len(critical_findings) > 0,
    }


@router.get("/checklist")
async def get_security_checklist(
    current_user: User = Depends(get_current_superuser),
):
    """
    Gibt eine Sicherheits-Checkliste zurueck.

    Zeigt alle Pruefpunkte mit Status (bestanden/nicht bestanden).

    **Erfordert Superuser-Authentifizierung.**
    """
    service = get_security_audit_service()
    report = service.run_audit()

    checklist = []
    for finding in report.findings:
        checklist.append({
            "id": finding.id,
            "title": finding.title,
            "status": "bestanden" if finding.passed else "nicht_bestanden",
            "severity": finding.severity.value,
            "category": finding.category.value,
        })

    # Nach Severity sortieren
    severity_order = {
        AuditSeverity.CRITICAL.value: 0,
        AuditSeverity.HIGH.value: 1,
        AuditSeverity.MEDIUM.value: 2,
        AuditSeverity.LOW.value: 3,
        AuditSeverity.INFO.value: 4,
    }
    checklist.sort(key=lambda x: (0 if x["status"] == "nicht_bestanden" else 1, severity_order.get(x["severity"], 5)))

    return {
        "checklist": checklist,
        "passed_count": sum(1 for c in checklist if c["status"] == "bestanden"),
        "failed_count": sum(1 for c in checklist if c["status"] == "nicht_bestanden"),
        "total": len(checklist),
    }


@router.get("/recommendations")
async def get_security_recommendations(
    current_user: User = Depends(get_current_superuser),
):
    """
    Gibt priorisierte Sicherheitsempfehlungen zurueck.

    Empfehlungen sind nach Prioritaet (Severity) sortiert.

    **Erfordert Superuser-Authentifizierung.**
    """
    service = get_security_audit_service()
    report = service.run_audit()

    # Nur nicht bestandene Findings
    failed_findings = [f for f in report.findings if not f.passed]

    # Nach Severity sortieren
    severity_order = {
        AuditSeverity.CRITICAL: 0,
        AuditSeverity.HIGH: 1,
        AuditSeverity.MEDIUM: 2,
        AuditSeverity.LOW: 3,
        AuditSeverity.INFO: 4,
    }
    failed_findings.sort(key=lambda f: severity_order.get(f.severity, 5))

    recommendations = []
    for idx, finding in enumerate(failed_findings, 1):
        recommendations.append({
            "prioritaet": idx,
            "id": finding.id,
            "titel": finding.title,
            "schweregrad": finding.severity.value,
            "empfehlung": finding.recommendation,
            "betroffene_komponente": finding.affected_component,
        })

    return {
        "total_empfehlungen": len(recommendations),
        "empfehlungen": recommendations,
        "naechste_aktion": recommendations[0] if recommendations else None,
    }
