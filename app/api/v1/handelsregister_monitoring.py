# -*- coding: utf-8 -*-
"""
Handelsregister Monitoring API Endpoints.

Vision 2026 Q4: Kontinuierliche Unternehmens-Überwachung.

Endpoints:
- GET    /handelsregister/monitoring/status       - Monitoring-Status
- GET    /handelsregister/monitoring/alerts       - Aktive Alerts
- POST   /handelsregister/monitoring/entities     - Entity zur Überwachung hinzufügen
- DELETE /handelsregister/monitoring/entities/{id} - Entity-Überwachung stoppen
- GET    /handelsregister/monitoring/entities     - Überwachte Entities
- POST   /handelsregister/validate                - Firma validieren
- GET    /handelsregister/insolvency/{entity_id}  - Insolvenz-Status
- GET    /handelsregister/changes/{entity_id}     - Änderungshistorie
- POST   /handelsregister/search                  - Firmensuche
"""


from datetime import date, datetime
from typing import List, Optional

from app.core.types import JSONDict
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db, get_user_company_id_dep
from app.core.rate_limiting import limiter
from app.db.models import User
from app.core.safe_errors import safe_error_log
from app.services.external.handelsregister_monitoring_service import (

    get_handelsregister_monitoring_service,
    CompanyValidation,
    ValidationResult,
    InsolvencyType,
    InsolvencyRecord,
    MonitoringAlert,
    MonitoringEvent,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/handelsregister", tags=["Handelsregister Monitoring"])


# =============================================================================
# Pydantic Schemas
# =============================================================================

class MonitoringStatusResponse(BaseModel):
    """Status des Handelsregister-Monitorings."""
    active_entities: int = Field(..., description="Überwachte Entities")
    pending_alerts: int = Field(..., description="Offene Alerts")
    last_check_at: Optional[str] = Field(None, description="Letzte Prüfung")
    next_check_at: Optional[str] = Field(None, description="Nächste Prüfung")
    check_interval_hours: int = Field(default=24, description="Prüfintervall")
    service_status: str = Field(default="operational", description="Service-Status")


class MonitoringAlertResponse(BaseModel):
    """Ein Monitoring-Alert."""
    id: str = Field(..., description="Alert-ID")
    entity_id: str = Field(..., description="Entity-ID")
    entity_name: str = Field(..., description="Firmenname")
    alert_type: str = Field(..., description="Alert-Typ")
    severity: str = Field(..., description="Schweregrad")
    title: str = Field(..., description="Titel")
    message: str = Field(..., description="Nachricht")
    details: JSONDict = Field(default_factory=dict, description="Details")
    risk_impact: Optional[float] = Field(None, description="Risiko-Auswirkung")
    created_at: str = Field(..., description="Erstellt am")
    acknowledged: bool = Field(default=False, description="Bestätigt")
    acknowledged_at: Optional[str] = Field(None, description="Bestätigt am")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "id": "alert-001",
            "entity_id": "entity-123",
            "entity_name": "Müller GmbH",
            "alert_type": "insolvency_notice",
            "severity": "critical",
            "title": "Insolvenzantrag bekannt",
            "message": "Für die Müller GmbH wurde ein Insolvenzantrag gestellt.",
            "risk_impact": 25.0,
            "created_at": "2026-01-28T10:00:00Z",
            "acknowledged": False,
        }
    })


class MonitoredEntityResponse(BaseModel):
    """Eine überwachte Entity."""
    entity_id: str = Field(..., description="Entity-ID")
    entity_name: str = Field(..., description="Firmenname")
    hrb_number: Optional[str] = Field(None, description="HRB-Nummer")
    court: Optional[str] = Field(None, description="Registergericht")
    monitoring_since: str = Field(..., description="Überwacht seit")
    last_checked_at: Optional[str] = Field(None, description="Letzte Prüfung")
    validation_status: str = Field(..., description="Validierungsstatus")
    insolvency_status: str = Field(default="none", description="Insolvenz-Status")
    alert_count: int = Field(default=0, description="Anzahl Alerts")
    risk_score_impact: float = Field(default=0.0, description="Risiko-Score-Impact")


class EntityMonitoringRequest(BaseModel):
    """Request zum Hinzufügen zur Überwachung."""
    entity_id: UUID = Field(..., description="Entity-ID")
    priority: str = Field(default="normal", description="Priorität (high, normal, low)")
    check_insolvency: bool = Field(default=True, description="Insolvenz prüfen")
    check_changes: bool = Field(default=True, description="Änderungen prüfen")


class CompanyValidationRequest(BaseModel):
    """Request zur Firmenvalidierung."""
    company_name: str = Field(..., min_length=2, max_length=200, description="Firmenname")
    hrb_number: Optional[str] = Field(None, description="HRB-Nummer")
    address: Optional[str] = Field(None, description="Adresse")
    entity_id: Optional[UUID] = Field(None, description="Vorhandene Entity")


class CompanyValidationResponse(BaseModel):
    """Ergebnis der Firmenvalidierung."""
    is_valid: bool = Field(..., description="Firma valide")
    validation_result: str = Field(..., description="Validierungsergebnis")
    company_name: str = Field(..., description="Registrierter Name")
    legal_form: Optional[str] = Field(None, description="Rechtsform")
    hrb_number: Optional[str] = Field(None, description="HRB-Nummer")
    court: Optional[str] = Field(None, description="Registergericht")
    address: Optional[str] = Field(None, description="Registrierte Adresse")
    management: List[str] = Field(default=[], description="Geschäftsführung")
    founded_date: Optional[str] = Field(None, description="Gründungsdatum")
    capital: Optional[str] = Field(None, description="Stammkapital")
    confidence: float = Field(..., description="Konfidenz")
    warnings: List[str] = Field(default=[], description="Warnungen")
    checked_at: str = Field(..., description="Geprüft am")


class InsolvencyStatusResponse(BaseModel):
    """Insolvenz-Status einer Entity."""
    entity_id: str = Field(..., description="Entity-ID")
    entity_name: str = Field(..., description="Firmenname")
    status: str = Field(..., description="Insolvenz-Status")
    has_active_proceedings: bool = Field(default=False, description="Aktives Verfahren")
    proceedings: List[JSONDict] = Field(default=[], description="Verfahren")
    last_checked_at: str = Field(..., description="Letzte Prüfung")
    risk_level: str = Field(default="none", description="Risikostufe")


class CompanyChangeResponse(BaseModel):
    """Eine Änderung im Handelsregister."""
    id: str = Field(..., description="Änderungs-ID")
    entity_id: str = Field(..., description="Entity-ID")
    change_type: str = Field(..., description="Änderungstyp")
    description: str = Field(..., description="Beschreibung")
    old_value: Optional[str] = Field(None, description="Alter Wert")
    new_value: Optional[str] = Field(None, description="Neuer Wert")
    effective_date: Optional[str] = Field(None, description="Wirksamkeitsdatum")
    detected_at: str = Field(..., description="Erkannt am")
    source: str = Field(default="handelsregister", description="Quelle")


class CompanySearchRequest(BaseModel):
    """Request für Firmensuche."""
    query: str = Field(..., min_length=2, max_length=200, description="Suchbegriff")
    court: Optional[str] = Field(None, description="Registergericht")
    legal_form: Optional[str] = Field(None, description="Rechtsform")
    max_results: int = Field(default=20, ge=1, le=100, description="Max. Ergebnisse")


class CompanySearchResultResponse(BaseModel):
    """Suchergebnis."""
    company_name: str = Field(..., description="Firmenname")
    hrb_number: str = Field(..., description="HRB-Nummer")
    court: str = Field(..., description="Registergericht")
    legal_form: Optional[str] = Field(None, description="Rechtsform")
    address: Optional[str] = Field(None, description="Adresse")
    status: str = Field(default="active", description="Status")
    relevance_score: float = Field(default=1.0, description="Relevanz")


# =============================================================================
# Monitoring Status Endpoints
# =============================================================================

@router.get(
    "/monitoring/status",
    response_model=MonitoringStatusResponse,
    summary="Monitoring-Status",
    description="Zeigt den Status des Handelsregister-Monitorings.",
)
@limiter.limit("30/minute")
async def get_monitoring_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> MonitoringStatusResponse:
    """Zeigt den Status des Handelsregister-Monitorings."""
    service = get_handelsregister_monitoring_service()
    status_data = await service.get_monitoring_status(db, company_id)

    return MonitoringStatusResponse(
        active_entities=status_data.active_entities,
        pending_alerts=status_data.pending_alerts,
        last_check_at=status_data.last_check_at.isoformat() if status_data.last_check_at else None,
        next_check_at=status_data.next_check_at.isoformat() if status_data.next_check_at else None,
        check_interval_hours=status_data.check_interval_hours,
        service_status=status_data.service_status,
    )


@router.get(
    "/monitoring/alerts",
    response_model=List[MonitoringAlertResponse],
    summary="Aktive Alerts",
    description="Zeigt aktive Handelsregister-Alerts.",
)
@limiter.limit("30/minute")
async def get_monitoring_alerts(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
    include_acknowledged: bool = Query(False, description="Auch bestätigte zeigen"),
    severity: Optional[str] = Query(None, description="Filter nach Schweregrad"),
    page: int = Query(1, ge=1, description="Seite"),
    page_size: int = Query(50, ge=1, le=100, description="Pro Seite"),
) -> List[MonitoringAlertResponse]:
    """Zeigt aktive Handelsregister-Alerts."""
    service = get_handelsregister_monitoring_service()
    alerts = await service.get_alerts(
        db=db,
        company_id=company_id,
        include_acknowledged=include_acknowledged,
        severity=severity,
        page=page,
        page_size=page_size,
    )

    return [
        MonitoringAlertResponse(
            id=str(a.id),
            entity_id=str(a.entity_id),
            entity_name=a.entity_name,
            alert_type=a.alert_type.value,
            severity=a.severity,
            title=a.title,
            message=a.message,
            details=a.details,
            risk_impact=a.risk_impact,
            created_at=a.created_at.isoformat(),
            acknowledged=a.acknowledged,
            acknowledged_at=a.acknowledged_at.isoformat() if a.acknowledged_at else None,
        )
        for a in alerts
    ]


@router.post(
    "/monitoring/alerts/{alert_id}/acknowledge",
    summary="Alert bestätigen",
    description="Bestätigt einen Monitoring-Alert.",
)
@limiter.limit("30/minute")
async def acknowledge_alert(
    request: Request,
    alert_id: UUID = Path(..., description="Alert-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> JSONDict:
    """Bestätigt einen Monitoring-Alert."""
    service = get_handelsregister_monitoring_service()

    try:
        # SECURITY: Übergebe company_id für Ownership-Validierung
        success = await service.acknowledge_alert(
            alert_id=alert_id,
            user_id=current_user.id,
            company_id=company_id,  # Verhindert Cross-Company Access
        )
    except PermissionError as e:
        logger.warning(
            "unauthorized_alert_acknowledge",
            alert_id=str(alert_id),
            user_id=str(current_user.id),
            company_id=str(company_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung für diesen Alert.",
        )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert nicht gefunden.",
        )

    await db.commit()

    return {
        "success": True,
        "message": "Alert bestätigt.",
        "alert_id": str(alert_id),
    }


# =============================================================================
# Entity Monitoring Management
# =============================================================================

@router.get(
    "/monitoring/entities",
    response_model=List[MonitoredEntityResponse],
    summary="Überwachte Entities",
    description="Listet alle zur Überwachung hinzugefügten Entities.",
)
@limiter.limit("30/minute")
async def list_monitored_entities(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
    status_filter: Optional[str] = Query(None, description="Filter nach Status"),
) -> List[MonitoredEntityResponse]:
    """Listet alle überwachten Entities."""
    service = get_handelsregister_monitoring_service()
    entities = await service.list_monitored_entities(
        db=db,
        company_id=company_id,
        status_filter=status_filter,
    )

    return [
        MonitoredEntityResponse(
            entity_id=str(e.entity_id),
            entity_name=e.entity_name,
            hrb_number=e.hrb_number,
            court=e.court,
            monitoring_since=e.monitoring_since.isoformat(),
            last_checked_at=e.last_checked_at.isoformat() if e.last_checked_at else None,
            validation_status=e.validation_status.value,
            insolvency_status=e.insolvency_status.value,
            alert_count=e.alert_count,
            risk_score_impact=e.risk_score_impact,
        )
        for e in entities
    ]


@router.post(
    "/monitoring/entities",
    response_model=MonitoredEntityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Entity zur Überwachung hinzufügen",
    description="Fügt eine Entity zur Handelsregister-Überwachung hinzu.",
)
@limiter.limit("10/minute")
async def add_entity_to_monitoring(
    request: Request,
    data: EntityMonitoringRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> MonitoredEntityResponse:
    """
    Fügt eine Entity zur Überwachung hinzu.

    Die Entity wird regelmäßig auf Änderungen und Insolvenz geprüft.
    """
    service = get_handelsregister_monitoring_service()

    entity, error = await service.add_entity_to_monitoring(
        db=db,
        company_id=company_id,
        entity_id=data.entity_id,
        priority=data.priority,
        check_insolvency=data.check_insolvency,
        check_changes=data.check_changes,
    )

    if not entity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error or "Entity konnte nicht hinzugefügt werden.",
        )

    await db.commit()

    logger.info(
        "entity_added_to_monitoring",
        entity_id=str(data.entity_id),
        user_id=str(current_user.id),
    )

    return MonitoredEntityResponse(
        entity_id=str(entity.entity_id),
        entity_name=entity.entity_name,
        hrb_number=entity.hrb_number,
        court=entity.court,
        monitoring_since=entity.monitoring_since.isoformat(),
        last_checked_at=entity.last_checked_at.isoformat() if entity.last_checked_at else None,
        validation_status=entity.validation_status.value,
        insolvency_status=entity.insolvency_status.value,
        alert_count=entity.alert_count,
        risk_score_impact=entity.risk_score_impact,
    )


@router.delete(
    "/monitoring/entities/{entity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Überwachung stoppen",
    description="Entfernt eine Entity aus der Überwachung.",
)
@limiter.limit("10/minute")
async def remove_entity_from_monitoring(
    request: Request,
    entity_id: UUID = Path(..., description="Entity-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Entfernt eine Entity aus der Überwachung."""
    service = get_handelsregister_monitoring_service()
    success = await service.remove_entity_from_monitoring(
        db=db,
        company_id=company_id,
        entity_id=entity_id,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity nicht in Überwachung gefunden.",
        )

    await db.commit()

    logger.info(
        "entity_removed_from_monitoring",
        entity_id=str(entity_id),
        user_id=str(current_user.id),
    )

    return None


# =============================================================================
# Validation Endpoints
# =============================================================================

@router.post(
    "/validate",
    response_model=CompanyValidationResponse,
    summary="Firma validieren",
    description="Validiert eine Firma gegen das Handelsregister.",
)
@limiter.limit("10/minute")
async def validate_company(
    request: Request,
    data: CompanyValidationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> CompanyValidationResponse:
    """
    Validiert eine Firma gegen das Handelsregister.

    Prüft:
    - Existenz im Handelsregister
    - Aktiver Status
    - Übereinstimmung der Daten
    - Insolvenz-Status
    """
    service = get_handelsregister_monitoring_service()

    result = await service.validate_company(
        db=db,
        company_name=data.company_name,
        hrb_number=data.hrb_number,
        address=data.address,
        entity_id=data.entity_id,
    )

    return CompanyValidationResponse(
        is_valid=result.is_valid,
        validation_result=result.result.value,
        company_name=result.company_name,
        legal_form=result.legal_form,
        hrb_number=result.hrb_number,
        court=result.court,
        address=result.address,
        management=result.management,
        founded_date=result.founded_date.isoformat() if result.founded_date else None,
        capital=result.capital,
        confidence=result.confidence,
        warnings=result.warnings,
        checked_at=result.checked_at.isoformat(),
    )


# =============================================================================
# Insolvency Endpoints
# =============================================================================

@router.get(
    "/insolvency/{entity_id}",
    response_model=InsolvencyStatusResponse,
    summary="Insolvenz-Status",
    description="Ruft den Insolvenz-Status einer Entity ab.",
)
@limiter.limit("30/minute")
async def get_insolvency_status(
    request: Request,
    entity_id: UUID = Path(..., description="Entity-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> InsolvencyStatusResponse:
    """
    Ruft den Insolvenz-Status ab.

    Prüft:
    - Aktive Insolvenzverfahren
    - Historische Verfahren
    - Risikostufe
    """
    service = get_handelsregister_monitoring_service()

    result = await service.get_insolvency_status(db, entity_id)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity nicht gefunden.",
        )

    return InsolvencyStatusResponse(
        entity_id=str(entity_id),
        entity_name=result.entity_name,
        status=result.status.value,
        has_active_proceedings=result.has_active_proceedings,
        proceedings=[
            {
                "id": str(p.id),
                "type": p.type,
                "court": p.court,
                "file_number": p.file_number,
                "opened_date": p.opened_date.isoformat() if p.opened_date else None,
                "status": p.status,
            }
            for p in result.proceedings
        ],
        last_checked_at=result.last_checked_at.isoformat(),
        risk_level=result.risk_level,
    )


# =============================================================================
# Changes History Endpoints
# =============================================================================

@router.get(
    "/changes/{entity_id}",
    response_model=List[CompanyChangeResponse],
    summary="Änderungshistorie",
    description="Zeigt die Änderungshistorie einer Entity im Handelsregister.",
)
@limiter.limit("30/minute")
async def get_company_changes(
    request: Request,
    entity_id: UUID = Path(..., description="Entity-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
    date_from: Optional[date] = Query(None, description="Von Datum"),
    date_to: Optional[date] = Query(None, description="Bis Datum"),
    change_type: Optional[str] = Query(None, description="Änderungstyp"),
) -> List[CompanyChangeResponse]:
    """
    Zeigt die Änderungshistorie im Handelsregister.

    Änderungstypen:
    - name_change: Namensänderung
    - address_change: Adressänderung
    - management_change: Geschäftsführerwechsel
    - capital_change: Kapitaländerung
    - purpose_change: Gegenstandsänderung
    - legal_form_change: Rechtsformwechsel
    """
    service = get_handelsregister_monitoring_service()

    changes = await service.get_company_changes(
        db=db,
        entity_id=entity_id,
        date_from=date_from,
        date_to=date_to,
        change_type=change_type,
    )

    return [
        CompanyChangeResponse(
            id=str(c.id),
            entity_id=str(c.entity_id),
            change_type=c.change_type.value,
            description=c.description,
            old_value=c.old_value,
            new_value=c.new_value,
            effective_date=c.effective_date.isoformat() if c.effective_date else None,
            detected_at=c.detected_at.isoformat(),
            source=c.source,
        )
        for c in changes
    ]


# =============================================================================
# Search Endpoints
# =============================================================================

@router.post(
    "/search",
    response_model=List[CompanySearchResultResponse],
    summary="Firmensuche",
    description="Sucht Firmen im Handelsregister.",
)
@limiter.limit("20/minute")
async def search_companies(
    request: Request,
    data: CompanySearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[CompanySearchResultResponse]:
    """
    Sucht Firmen im Handelsregister.

    Kann nach Firmenname, HRB-Nummer oder Adresse suchen.
    """
    service = get_handelsregister_monitoring_service()

    results = await service.search_companies(
        query=data.query,
        court=data.court,
        legal_form=data.legal_form,
        max_results=data.max_results,
    )

    return [
        CompanySearchResultResponse(
            company_name=r.company_name,
            hrb_number=r.hrb_number,
            court=r.court,
            legal_form=r.legal_form,
            address=r.address,
            status=r.status,
            relevance_score=r.relevance_score,
        )
        for r in results
    ]


# =============================================================================
# Bulk Check Endpoints
# =============================================================================

@router.post(
    "/monitoring/check-all",
    summary="Alle Entities prüfen",
    description="Löst eine sofortige Prüfung aller überwachten Entities aus.",
)
@limiter.limit("2/minute")
async def check_all_monitored_entities(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> JSONDict:
    """
    Prüft alle überwachten Entities sofort.

    Normalerweise erfolgt die Prüfung automatisch alle 24 Stunden.
    Dieser Endpoint erlaubt eine manuelle Sofortprüfung.
    """
    service = get_handelsregister_monitoring_service()

    result = await service.check_all_entities(db, company_id)

    await db.commit()

    logger.info(
        "manual_monitoring_check_complete",
        user_id=str(current_user.id),
        company_id=str(company_id),
        entities_checked=result.entities_checked,
        alerts_created=result.alerts_created,
    )

    return {
        "success": True,
        "entities_checked": result.entities_checked,
        "alerts_created": result.alerts_created,
        "duration_ms": result.duration_ms,
        "message": f"{result.entities_checked} Entities geprüft, "
                   f"{result.alerts_created} neue Alerts.",
    }
