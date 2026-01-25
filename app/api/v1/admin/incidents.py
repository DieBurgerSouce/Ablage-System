# -*- coding: utf-8 -*-
"""
Incident Response Admin-Endpoints für Ablage-System OCR.

Sicherheitsvorfälle verwalten, IP-Sperren konfigurieren, Analyse durchführen.
Nur für Administratoren zugänglich.

Alle Antworten auf Deutsch.
"""

from typing import Any, List, Optional
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
import structlog

from app.api.dependencies import get_db, get_current_superuser
from app.db.models import User
from app.services.incident_response_service import (
    get_incident_response_service,
    IncidentType,
    IncidentSeverity,
    ResponseAction,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/incidents", tags=["Incident Response"])


# ==================== Schemas ====================

class IncidentResponse(BaseModel):
    """Schema für Incident-Details."""
    id: str
    type: str
    severity: str
    description: str
    ip_address: Optional[str] = None
    user_id: Optional[str] = None
    details: dict
    created_at: str
    actions_taken: List[str]


class IncidentListResponse(BaseModel):
    """Schema für Incident-Liste."""
    incidents: List[IncidentResponse]
    total: int


class BlockedIPResponse(BaseModel):
    """Schema für blockierte IP-Details."""
    ip_address: str
    blocked_until: str
    is_permanent: bool


class BlockedIPListResponse(BaseModel):
    """Schema für blockierte IP-Liste."""
    blocked_ips: List[BlockedIPResponse]
    total: int


class AnalyzeRequest(BaseModel):
    """Schema für manuelle Analyse-Anfrage."""
    window_minutes: int = Field(
        default=15,
        ge=1,
        le=1440,
        description="Zeitfenster für Analyse in Minuten (1-1440)"
    )


class AnalyzeResponse(BaseModel):
    """Schema für Analyse-Ergebnis."""
    incidents_detected: int
    incidents: List[IncidentResponse]
    actions_executed: int
    nachricht: str


class ManualBlockRequest(BaseModel):
    """Schema für manuelle IP-Sperre."""
    ip_address: str
    duration_hours: int = Field(
        default=1,
        ge=1,
        le=8760,
        description="Sperrdauer in Stunden (1-8760, max 1 Jahr)"
    )
    reason: str = Field(
        default="Manuelle Admin-Sperre",
        max_length=500
    )
    permanent: bool = Field(
        default=False,
        description="Permanente Sperre"
    )


class ManualBlockResponse(BaseModel):
    """Schema für Sperrbestätigung."""
    success: bool
    nachricht: str
    blocked_until: str


class UnblockResponse(BaseModel):
    """Schema für Entsperrung."""
    success: bool
    nachricht: str


class IncidentStatsResponse(BaseModel):
    """Schema für Incident-Statistiken."""
    total_incidents: int
    by_type: dict
    by_severity: dict
    blocked_ips_count: int
    last_analysis: Optional[str] = None


# ==================== Endpoints ====================

@router.get(
    "",
    response_model=IncidentListResponse,
    summary="Aktive Incidents auflisten",
    description="Zeigt alle erkannten Sicherheitsvorfälle an"
)
async def list_incidents(
    admin: User = Depends(get_current_superuser),
    severity: Optional[str] = Query(
        None,
        description="Filtere nach Schweregrad (low, medium, high, critical)"
    ),
    incident_type: Optional[str] = Query(
        None,
        description="Filtere nach Incident-Typ"
    )
) -> Any:
    """
    Listet alle aktiven Sicherheitsvorfälle auf.

    **Filter-Optionen:**
    - severity: Nur Incidents mit bestimmtem Schweregrad
    - incident_type: Nur bestimmte Incident-Typen

    **Schweregrade:**
    - low: Informativ, keine Aktion erforderlich
    - medium: Erhöhte Aufmerksamkeit
    - high: Sofortige Prüfung empfohlen
    - critical: Sofortige Aktion erforderlich
    """
    service = get_incident_response_service()
    incidents = service.get_active_incidents()

    # Filter anwenden
    if severity:
        incidents = [i for i in incidents if i["severity"] == severity]
    if incident_type:
        incidents = [i for i in incidents if i["type"] == incident_type]

    logger.info(
        "admin_incidents_listed",
        admin_id=str(admin.id)[:8] + "...",
        count=len(incidents)
    )

    return IncidentListResponse(
        incidents=[IncidentResponse(**i) for i in incidents],
        total=len(incidents)
    )


@router.get(
    "/stats",
    response_model=IncidentStatsResponse,
    summary="Incident-Statistiken",
    description="Zeigt Statistiken über Sicherheitsvorfälle"
)
async def get_incident_stats(
    admin: User = Depends(get_current_superuser)
) -> Any:
    """
    Gibt Statistiken über aktuelle Sicherheitsvorfälle zurück.

    Zeigt Verteilung nach:
    - Incident-Typ
    - Schweregrad
    - Anzahl blockierter IPs
    """
    service = get_incident_response_service()
    incidents = service.get_active_incidents()
    blocked_ips = service.get_blocked_ips()

    # Zähle nach Typ
    by_type = {}
    for i in incidents:
        t = i["type"]
        by_type[t] = by_type.get(t, 0) + 1

    # Zähle nach Schweregrad
    by_severity = {}
    for i in incidents:
        s = i["severity"]
        by_severity[s] = by_severity.get(s, 0) + 1

    return IncidentStatsResponse(
        total_incidents=len(incidents),
        by_type=by_type,
        by_severity=by_severity,
        blocked_ips_count=len(blocked_ips),
        last_analysis=None
    )


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    summary="Manuelle Sicherheitsanalyse",
    description="Führt manuelle Analyse der Security-Events durch"
)
async def analyze_security_events(
    request: AnalyzeRequest,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Führt eine manuelle Sicherheitsanalyse durch.

    Analysiert Security-Events der letzten X Minuten und führt
    automatische Gegenmaßnahmen für erkannte Incidents aus.

    **Erkannte Pattern:**
    - Brute-Force-Angriffe (wiederholte Login-Fehlversuche)
    - Rate-Limit-Missbrauch
    - Unauthorized Access Pattern

    **Automatische Aktionen:**
    - IP-Sperren (temporär/permanent)
    - Account-Sperrung
    - Session-Widerruf
    - Admin-Benachrichtigung
    """
    service = get_incident_response_service()

    # Analysiere Events
    incidents = await service.analyze_security_events(
        db=db,
        window_minutes=request.window_minutes
    )

    # Führe Response-Actions aus
    total_actions = 0
    for incident in incidents:
        actions = await service.execute_response(incident, db)
        total_actions += len(actions)

    logger.info(
        "admin_manual_analysis",
        admin_id=str(admin.id)[:8] + "...",
        window_minutes=request.window_minutes,
        incidents_found=len(incidents),
        actions_executed=total_actions
    )

    return AnalyzeResponse(
        incidents_detected=len(incidents),
        incidents=[IncidentResponse(**i.to_dict()) for i in incidents],
        actions_executed=total_actions,
        nachricht=f"{len(incidents)} Sicherheitsvorfall/-fälle erkannt, "
                  f"{total_actions} Maßnahme(n) ausgeführt"
    )


@router.get(
    "/blocked-ips",
    response_model=BlockedIPListResponse,
    summary="Blockierte IPs auflisten",
    description="Zeigt alle aktuell blockierten IP-Adressen"
)
async def list_blocked_ips(
    admin: User = Depends(get_current_superuser)
) -> Any:
    """
    Listet alle aktuell blockierten IP-Adressen auf.

    Zeigt für jede IP:
    - IP-Adresse
    - Blockiert bis (Zeitstempel)
    - Ob permanent blockiert
    """
    service = get_incident_response_service()
    blocked = service.get_blocked_ips()

    # Konvertiere zu Response-Format
    blocked_list = []
    one_year_from_now = datetime.now(timezone.utc) + timedelta(days=364)

    for ip, until_str in blocked.items():
        until = datetime.fromisoformat(until_str)
        is_permanent = until > one_year_from_now

        blocked_list.append(BlockedIPResponse(
            ip_address=ip,
            blocked_until=until_str,
            is_permanent=is_permanent
        ))

    logger.info(
        "admin_blocked_ips_listed",
        admin_id=str(admin.id)[:8] + "...",
        count=len(blocked_list)
    )

    return BlockedIPListResponse(
        blocked_ips=blocked_list,
        total=len(blocked_list)
    )


@router.post(
    "/blocked-ips",
    response_model=ManualBlockResponse,
    status_code=status.HTTP_201_CREATED,
    summary="IP manuell sperren",
    description="Sperrt eine IP-Adresse manuell"
)
async def block_ip_manually(
    request: ManualBlockRequest,
    admin: User = Depends(get_current_superuser)
) -> Any:
    """
    Sperrt eine IP-Adresse manuell.

    **Parameter:**
    - ip_address: Zu sperrende IP
    - duration_hours: Sperrdauer (1-8760 Stunden)
    - reason: Begründung für Audit-Log
    - permanent: Permanente Sperre (ignoriert duration_hours)

    **Hinweis:** Permanente Sperren sollten mit Bedacht eingesetzt werden.
    """
    service = get_incident_response_service()

    # Sperre IP
    await service._block_ip(
        ip_address=request.ip_address,
        permanent=request.permanent
    )

    # Berechne Sperrende
    if request.permanent:
        blocked_until = datetime.now(timezone.utc) + timedelta(days=365)
    else:
        blocked_until = datetime.now(timezone.utc) + timedelta(hours=request.duration_hours)

    logger.warning(
        "admin_manual_ip_block",
        admin_id=str(admin.id)[:8] + "...",
        ip_address=request.ip_address,
        permanent=request.permanent,
        reason=request.reason
    )

    return ManualBlockResponse(
        success=True,
        nachricht=f"IP {request.ip_address} {'permanent' if request.permanent else f'für {request.duration_hours} Stunden'} gesperrt",
        blocked_until=blocked_until.isoformat()
    )


@router.delete(
    "/blocked-ips/{ip_address:path}",
    response_model=UnblockResponse,
    summary="IP entsperren",
    description="Hebt die Sperre einer IP-Adresse auf"
)
async def unblock_ip(
    ip_address: str,
    admin: User = Depends(get_current_superuser)
) -> Any:
    """
    Hebt die Sperre einer IP-Adresse auf.

    **Warnung:** Stellen Sie sicher, dass die Bedrohung beseitigt ist,
    bevor Sie eine IP entsperren.
    """
    service = get_incident_response_service()

    # Prüfe ob IP blockiert ist
    blocked_ips = service.get_blocked_ips()
    if ip_address not in blocked_ips:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"IP {ip_address} ist nicht blockiert"
        )

    # Entferne aus lokaler Liste
    if ip_address in service._blocked_ips:
        del service._blocked_ips[ip_address]

    # Entferne aus Redis
    try:
        from app.core.redis_state import get_redis
        redis = await get_redis()
        if redis:
            await redis.delete(f"blocked_ip:{ip_address}")
    except Exception as e:
        logger.warning("ip_unblock_redis_failed", ip=ip_address, error=str(e))

    logger.info(
        "admin_ip_unblocked",
        admin_id=str(admin.id)[:8] + "...",
        ip_address=ip_address
    )

    return UnblockResponse(
        success=True,
        nachricht=f"IP {ip_address} wurde entsperrt"
    )


@router.get(
    "/{incident_id}",
    response_model=IncidentResponse,
    summary="Incident-Details",
    description="Zeigt Details eines spezifischen Incidents"
)
async def get_incident_details(
    incident_id: str,
    admin: User = Depends(get_current_superuser)
) -> Any:
    """
    Gibt Details zu einem spezifischen Sicherheitsvorfall zurück.

    Zeigt alle Informationen inkl. ausgeführter Aktionen.
    """
    service = get_incident_response_service()

    if incident_id not in service.active_incidents:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident nicht gefunden"
        )

    incident = service.active_incidents[incident_id]

    return IncidentResponse(**incident.to_dict())


@router.delete(
    "/{incident_id}",
    response_model=UnblockResponse,
    summary="Incident schließen",
    description="Markiert einen Incident als bearbeitet und entfernt ihn"
)
async def close_incident(
    incident_id: str,
    admin: User = Depends(get_current_superuser)
) -> Any:
    """
    Schließt einen Incident und entfernt ihn aus der aktiven Liste.

    **Hinweis:** Der Incident wird aus dem Speicher entfernt,
    bleibt aber im Audit-Log erhalten.
    """
    service = get_incident_response_service()

    if incident_id not in service.active_incidents:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident nicht gefunden"
        )

    # Entferne Incident
    incident = service.active_incidents.pop(incident_id)

    logger.info(
        "admin_incident_closed",
        admin_id=str(admin.id)[:8] + "...",
        incident_id=incident_id,
        incident_type=incident.type.value
    )

    return UnblockResponse(
        success=True,
        nachricht=f"Incident {incident_id} wurde geschlossen"
    )


@router.get(
    "/config/security",
    summary="Sicherheits-Konfiguration",
    description="Zeigt aktuelle Sicherheits-Einstellungen"
)
async def get_security_config(
    admin: User = Depends(get_current_superuser)
) -> Any:
    """
    Zeigt die aktuelle Sicherheits-Konfiguration an.

    Inkludiert:
    - Incident-Schwellenwerte
    - Response-Regeln
    - Session-Limits
    """
    from app.services.incident_response_service import (
        INCIDENT_THRESHOLDS,
        RESPONSE_RULES
    )
    from app.core.config import settings

    # Konvertiere Response-Regeln zu serialisierbarem Format
    rules_serializable = {}
    for incident_type, severities in RESPONSE_RULES.items():
        rules_serializable[incident_type.value] = {
            sev.value: [action.value for action in actions]
            for sev, actions in severities.items()
        }

    return {
        "incident_thresholds": INCIDENT_THRESHOLDS,
        "response_rules": rules_serializable,
        "session_config": {
            "max_sessions_per_user": settings.MAX_SESSIONS_PER_USER,
            "session_expiry_hours": settings.SESSION_EXPIRY_HOURS,
            "session_limit_mode": settings.SESSION_LIMIT_MODE
        }
    }
