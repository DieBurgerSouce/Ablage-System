"""
Trust/Security Dashboard API Endpoints.

Provides security and compliance dashboard:
- Dashboard snapshot (metrics overview)
- Access log (who accessed what)
- Export log (GDPR Art. 15 tracking)
- Anomaly detection (unusual access patterns)
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_user, get_user_company_id_dep
from app.db.models import User
from app.services.trust_dashboard_service import get_trust_dashboard_service

router = APIRouter(prefix="/trust-dashboard", tags=["Trust Dashboard"])


# ==================== Schemas ====================

class MetricsResponse(BaseModel):
    """Trust Dashboard Metrics."""
    total_accesses: int
    sensitive_accesses: int
    export_count: int
    anomaly_count: int
    compliance_score: float = Field(ge=0, le=100)


class SecurityEventResponse(BaseModel):
    """Security Event."""
    id: str
    action: str
    user_id: Optional[str]
    resource_type: Optional[str]
    resource_id: Optional[str]
    ip_address: Optional[str]
    success: bool
    error_message: Optional[str]
    created_at: str


class TopDocumentResponse(BaseModel):
    """Top Accessed Document."""
    document_id: str
    access_count: int
    filename: str


class UserActivityResponse(BaseModel):
    """User Activity Summary."""
    user_id: str
    username: str
    action_count: int


class UserActivitySummaryResponse(BaseModel):
    """User Activity Summary Container."""
    top_users: List[UserActivityResponse]


class TrustDashboardSnapshot(BaseModel):
    """Trust Dashboard Snapshot."""
    period_days: int
    period_start: str
    period_end: str
    metrics: MetricsResponse
    recent_security_events: List[SecurityEventResponse]
    top_accessed_documents: List[TopDocumentResponse]
    user_activity_summary: UserActivitySummaryResponse


class AccessEventResponse(BaseModel):
    """Access Event."""
    id: str
    user_id: Optional[str]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    ip_address: Optional[str]
    created_at: str


class ExportEventResponse(BaseModel):
    """Export Event."""
    id: str
    user_id: Optional[str]
    action: str
    resource_type: Optional[str]
    ip_address: Optional[str]
    metadata: dict
    created_at: str


class AnomalyResponse(BaseModel):
    """Anomaly Event."""
    id: str
    type: str
    severity: str
    user_id: Optional[str]
    action: str
    error_message: Optional[str]
    ip_address: Optional[str]
    created_at: str


# ==================== Endpoints ====================

@router.get(
    "/",
    response_model=TrustDashboardSnapshot,
    summary="Trust Dashboard Snapshot",
    description="Liefert Übersicht über Sicherheits- und Compliance-Metriken"
)
async def get_trust_dashboard(
    days: int = Query(30, ge=1, le=365, description="Zeitraum in Tagen"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> TrustDashboardSnapshot:
    """
    Liefert Trust Dashboard Snapshot.

    **Metriken:**
    - Gesamtzugriffe
    - Sensitive Zugriffe (Exports, Admin)
    - Export-Anzahl
    - Anomalien (Failed Accesses)
    - Compliance-Score (0-100)

    **Zusätzlich:**
    - Letzte Security-Events
    - Meist-zugriffene Dokumente
    - Benutzer-Aktivität
    """
    service = get_trust_dashboard_service(db)
    snapshot = await service.get_dashboard_snapshot(company_id, days)

    return TrustDashboardSnapshot(**snapshot)


@router.get(
    "/access-log",
    response_model=List[AccessEventResponse],
    summary="Zugriffsprotokolle",
    description="Listet alle Zugriffe auf Dokumente auf"
)
async def get_access_log(
    days: int = Query(30, ge=1, le=365, description="Zeitraum in Tagen"),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(100, ge=1, le=500, description="Eintraege pro Seite"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[AccessEventResponse]:
    """
    Liefert Zugriffsprotokolle.

    Zeigt:
    - Wer hat welches Dokument angesehen/heruntergeladen
    - Zeitpunkt
    - IP-Adresse
    """
    service = get_trust_dashboard_service(db)
    access_log = await service.get_access_log(
        company_id,
        days=days,
        limit=per_page,
        offset=(page - 1) * per_page,
    )

    return [AccessEventResponse(**event) for event in access_log]


@router.get(
    "/export-log",
    response_model=List[ExportEventResponse],
    summary="Export-Logs",
    description="Listet alle Dokument-Exports auf (GDPR Art. 15)"
)
async def get_export_log(
    days: int = Query(30, ge=1, le=365, description="Zeitraum in Tagen"),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(100, ge=1, le=500, description="Eintraege pro Seite"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[ExportEventResponse]:
    """
    Liefert Export-Logs.

    Zeigt:
    - Welche Dokumente wurden exportiert
    - Von wem
    - In welchem Format
    - GDPR Art. 15 compliant
    """
    service = get_trust_dashboard_service(db)
    export_log = await service.get_export_log(
        company_id,
        days=days,
        limit=per_page,
        offset=(page - 1) * per_page,
    )

    return [ExportEventResponse(**event) for event in export_log]


@router.get(
    "/anomalies",
    response_model=List[AnomalyResponse],
    summary="Anomalien",
    description="Erkennt ungewöhnliche Zugriffsmuster und Fehler"
)
async def get_anomalies(
    days: int = Query(7, ge=1, le=90, description="Zeitraum in Tagen"),
    limit: int = Query(50, ge=1, le=200, description="Maximale Anzahl"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[AnomalyResponse]:
    """
    Erkennt Anomalien.

    Zeigt:
    - Fehlerhafte Login-Versuche
    - Fehlgeschlagene Zugriffe
    - Ungewöhnliche Muster
    - Severity-Level: low, medium, high, critical
    """
    service = get_trust_dashboard_service(db)
    anomalies = await service.get_anomalies(
        company_id,
        days=days,
        limit=limit,
    )

    return [AnomalyResponse(**anomaly) for anomaly in anomalies]
