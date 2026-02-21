# -*- coding: utf-8 -*-
"""Morning Briefing API - Tägliches Cockpit-Briefing Endpunkte.

Stellt REST-API-Endpunkte für das Morning Briefing Cockpit bereit:
- GET /api/v1/morning-briefing        : Tages-Briefing abrufen (gecacht, max. 4h alt)
- GET /api/v1/morning-briefing/alerts : Aktive Alerts nach Kategorie filtern
- POST /api/v1/morning-briefing/dismiss/{alert_id} : Alert ausblenden

Feinpoliert und durchdacht - Enterprise Morning Intelligence API.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.core.safe_errors import safe_error_log
from app.db.models import User
from app.middleware.company_context import require_company
from app.services.morning_briefing_service import (
    AlertSeverity,
    BriefingSection,
    MorningBriefingService,
    get_morning_briefing_service,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/morning-briefing", tags=["Morning Briefing"])

# Cache-TTL in Stunden: Briefing ist maximal 4 Stunden gültig
_CACHE_TTL_HOURS = 4

# Einfacher In-Memory-Cache für Briefings (Key: "{company_id}_{date}")
# In Produktion wird dies durch die morning_briefing_cache Tabelle ersetzt.
_briefing_cache: Dict[str, Dict[str, object]] = {}

# Ausgeblendete Alerts pro Firma (Key: "{company_id}", Value: set of alert_ids)
_dismissed_alerts: Dict[str, set] = {}


# =============================================================================
# Pydantic Schemas
# =============================================================================


class BriefingAlertResponse(BaseModel):
    """Schema für einen einzelnen Briefing-Alert."""
    alert_id: str
    alert_type: str
    severity: str
    title: str
    description: str
    action_url: Optional[str] = None
    action_label: Optional[str] = None
    metadata: Dict[str, object] = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class BriefingSectionResponse(BaseModel):
    """Schema für eine Briefing-Sektion."""
    section: str
    title: str
    summary: str
    score: Optional[float] = None
    critical_count: int
    warning_count: int
    alerts: List[BriefingAlertResponse]

    model_config = {"from_attributes": True}


class MorningBriefingResponse(BaseModel):
    """Vollständige Morning Briefing Antwort."""
    company_id: str
    briefing_date: str
    generated_at: str
    overall_score: float
    total_critical: int
    total_warnings: int
    has_critical_issues: bool
    sections: List[BriefingSectionResponse]
    from_cache: bool = False

    model_config = {"from_attributes": True}


class AlertsByCategoryResponse(BaseModel):
    """Alerts gruppiert nach Kategorie."""
    category: str
    category_title: str
    alerts: List[BriefingAlertResponse]
    critical_count: int
    warning_count: int


class DismissAlertResponse(BaseModel):
    """Antwort nach dem Ausblenden eines Alerts."""
    success: bool
    message: str


# =============================================================================
# Hilfsfunktionen
# =============================================================================


def _make_cache_key(company_id: UUID, briefing_date: date) -> str:
    """Generiert einen Cache-Key für ein Briefing.

    Args:
        company_id: Firmen-ID
        briefing_date: Datum des Briefings

    Returns:
        Cache-Key als String
    """
    return f"{company_id}_{briefing_date.isoformat()}"


def _is_cache_valid(cached_entry: Dict[str, object]) -> bool:
    """Prüft ob ein Cache-Eintrag noch gültig ist.

    Args:
        cached_entry: Gecachter Briefing-Eintrag

    Returns:
        True wenn gültig, False wenn abgelaufen
    """
    expires_at_raw = cached_entry.get("_expires_at")
    if not isinstance(expires_at_raw, datetime):
        return False
    return datetime.now(timezone.utc) < expires_at_raw


def _briefing_dict_to_response(
    briefing_dict: Dict[str, object],
    from_cache: bool = False,
    dismissed_ids: Optional[set] = None,
) -> MorningBriefingResponse:
    """Konvertiert ein Briefing-Dictionary in eine Pydantic-Response.

    Filtert ausgeblendete Alerts heraus.

    Args:
        briefing_dict: Briefing-Daten als Dictionary
        from_cache: Ob aus Cache geladen
        dismissed_ids: Set von ausgeblendeten Alert-IDs

    Returns:
        MorningBriefingResponse Pydantic-Schema
    """
    sections_data = briefing_dict.get("sections", [])
    if not isinstance(sections_data, list):
        sections_data = []

    sections: List[BriefingSectionResponse] = []

    for section_raw in sections_data:
        if not isinstance(section_raw, dict):
            continue

        alerts_raw = section_raw.get("alerts", [])
        if not isinstance(alerts_raw, list):
            alerts_raw = []

        # Ausgeblendete Alerts filtern
        filtered_alerts = [
            a for a in alerts_raw
            if isinstance(a, dict) and (
                dismissed_ids is None
                or a.get("alert_id") not in dismissed_ids
            )
        ]

        alert_responses = [
            BriefingAlertResponse(
                alert_id=str(a.get("alert_id", "")),
                alert_type=str(a.get("alert_type", "")),
                severity=str(a.get("severity", "info")),
                title=str(a.get("title", "")),
                description=str(a.get("description", "")),
                action_url=a.get("action_url") if isinstance(a.get("action_url"), str) else None,
                action_label=a.get("action_label") if isinstance(a.get("action_label"), str) else None,
                metadata=a.get("metadata", {}) if isinstance(a.get("metadata"), dict) else {},
            )
            for a in filtered_alerts
        ]

        critical_n = sum(1 for a in alert_responses if a.severity == "critical")
        warning_n = sum(1 for a in alert_responses if a.severity == "warning")

        score_raw = section_raw.get("score")
        score = float(score_raw) if isinstance(score_raw, (int, float)) else None

        sections.append(BriefingSectionResponse(
            section=str(section_raw.get("section", "")),
            title=str(section_raw.get("title", "")),
            summary=str(section_raw.get("summary", "")),
            score=score,
            critical_count=critical_n,
            warning_count=warning_n,
            alerts=alert_responses,
        ))

    total_critical = sum(s.critical_count for s in sections)
    total_warnings = sum(s.warning_count for s in sections)

    overall_score_raw = briefing_dict.get("overall_score")
    overall_score = float(overall_score_raw) if isinstance(overall_score_raw, (int, float)) else 100.0

    return MorningBriefingResponse(
        company_id=str(briefing_dict.get("company_id", "")),
        briefing_date=str(briefing_dict.get("briefing_date", "")),
        generated_at=str(briefing_dict.get("generated_at", "")),
        overall_score=overall_score,
        total_critical=total_critical,
        total_warnings=total_warnings,
        has_critical_issues=total_critical > 0,
        sections=sections,
        from_cache=from_cache,
    )


# =============================================================================
# API Endpunkte
# =============================================================================


@router.get(
    "",
    response_model=MorningBriefingResponse,
    summary="Tages-Briefing abrufen",
    description=(
        "Gibt das Morning Briefing für heute zurück. "
        "Gecacht für bis zu 4 Stunden. "
        "Bei abgelaufenem Cache wird automatisch neu generiert."
    ),
)
async def get_morning_briefing(
    force_refresh: bool = Query(
        default=False,
        description="Cache ignorieren und Briefing neu generieren",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company=Depends(require_company),
    service: MorningBriefingService = Depends(get_morning_briefing_service),
) -> MorningBriefingResponse:
    """Gibt das Morning Briefing für heute zurück.

    Das Briefing wird gecacht und nur neu generiert wenn:
    - Der Cache abgelaufen ist (älter als 4 Stunden)
    - `force_refresh=true` übergeben wird

    Args:
        force_refresh: Cache ignorieren
        db: Datenbank-Session
        current_user: Eingeloggter Benutzer
        company: Aktive Firma (aus Middleware)
        service: Morning Briefing Service

    Returns:
        Vollständiges Tages-Briefing mit allen Sektionen und Alerts
    """
    company_id: UUID = company.id
    today = date.today()
    cache_key = _make_cache_key(company_id, today)

    # Ausgeblendete Alerts für diese Firma laden
    dismissed_ids = _dismissed_alerts.get(str(company_id), set())

    # Cache prüfen (wenn nicht force_refresh)
    if not force_refresh and cache_key in _briefing_cache:
        cached = _briefing_cache[cache_key]
        if _is_cache_valid(cached):
            logger.info(
                "morning_briefing_aus_cache",
                company_id=str(company_id),
                cache_key=cache_key,
            )
            return _briefing_dict_to_response(
                briefing_dict=cached,
                from_cache=True,
                dismissed_ids=dismissed_ids,
            )

    # Briefing neu generieren
    try:
        briefing = await service.generate_briefing(
            db=db,
            company_id=company_id,
        )

        briefing_dict = briefing.to_dict()

        # Mit Ablaufzeit in Cache speichern
        expires_at = datetime.now(timezone.utc) + timedelta(hours=_CACHE_TTL_HOURS)
        briefing_dict["_expires_at"] = expires_at
        _briefing_cache[cache_key] = briefing_dict

        return _briefing_dict_to_response(
            briefing_dict=briefing_dict,
            from_cache=False,
            dismissed_ids=dismissed_ids,
        )

    except Exception as exc:
        logger.error(
            "morning_briefing_api_fehler",
            **safe_error_log(exc),
            company_id=str(company_id),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Das Morning Briefing konnte nicht generiert werden. Bitte versuchen Sie es erneut.",
        )


@router.get(
    "/alerts",
    response_model=List[AlertsByCategoryResponse],
    summary="Aktive Alerts nach Kategorie",
    description="Gibt alle aktiven Alerts des heutigen Briefings gruppiert nach Kategorie zurück.",
)
async def get_alerts_by_category(
    severity: Optional[str] = Query(
        default=None,
        description="Filter nach Schweregrad: 'info', 'warning', 'critical'",
    ),
    section: Optional[str] = Query(
        default=None,
        description="Filter nach Sektion: 'financial', 'compliance', 'workflow', 'data_quality'",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company=Depends(require_company),
    service: MorningBriefingService = Depends(get_morning_briefing_service),
) -> List[AlertsByCategoryResponse]:
    """Gibt aktive Alerts nach Kategorie zurück.

    Lädt das heutige Briefing (aus Cache oder neu) und gibt die Alerts
    optional nach Schweregrad und Sektion gefiltert zurück.

    Args:
        severity: Optionaler Schweregrad-Filter
        section: Optionaler Sektions-Filter
        db: Datenbank-Session
        current_user: Eingeloggter Benutzer
        company: Aktive Firma
        service: Morning Briefing Service

    Returns:
        Liste von Alerts gruppiert nach Kategorie
    """
    company_id: UUID = company.id
    today = date.today()
    cache_key = _make_cache_key(company_id, today)
    dismissed_ids = _dismissed_alerts.get(str(company_id), set())

    # Briefing laden (aus Cache oder neu)
    if cache_key in _briefing_cache and _is_cache_valid(_briefing_cache[cache_key]):
        briefing_dict = _briefing_cache[cache_key]
    else:
        try:
            briefing = await service.generate_briefing(db=db, company_id=company_id)
            briefing_dict = briefing.to_dict()
            expires_at = datetime.now(timezone.utc) + timedelta(hours=_CACHE_TTL_HOURS)
            briefing_dict["_expires_at"] = expires_at
            _briefing_cache[cache_key] = briefing_dict
        except Exception as exc:
            logger.error(
                "morning_briefing_alerts_api_fehler",
                **safe_error_log(exc),
                company_id=str(company_id),
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Alerts konnten nicht geladen werden.",
            )

    # Sektions-Titel-Mapping
    section_titles: Dict[str, str] = {
        BriefingSection.FINANCIAL.value: "Finanzielle Lage",
        BriefingSection.COMPLIANCE.value: "GoBD & Compliance",
        BriefingSection.WORKFLOW.value: "Workflow & OCR-Queue",
        BriefingSection.DATA_QUALITY.value: "Datenqualität",
    }

    sections_data = briefing_dict.get("sections", [])
    if not isinstance(sections_data, list):
        sections_data = []

    result: List[AlertsByCategoryResponse] = []

    for section_raw in sections_data:
        if not isinstance(section_raw, dict):
            continue

        section_id = str(section_raw.get("section", ""))

        # Sektions-Filter anwenden
        if section and section_id != section:
            continue

        alerts_raw = section_raw.get("alerts", [])
        if not isinstance(alerts_raw, list):
            alerts_raw = []

        # Ausgeblendete und gefilterte Alerts
        filtered_alerts: List[BriefingAlertResponse] = []
        for a in alerts_raw:
            if not isinstance(a, dict):
                continue
            if a.get("alert_id") in dismissed_ids:
                continue
            alert_severity = str(a.get("severity", "info"))
            if severity and alert_severity != severity:
                continue
            filtered_alerts.append(BriefingAlertResponse(
                alert_id=str(a.get("alert_id", "")),
                alert_type=str(a.get("alert_type", "")),
                severity=alert_severity,
                title=str(a.get("title", "")),
                description=str(a.get("description", "")),
                action_url=a.get("action_url") if isinstance(a.get("action_url"), str) else None,
                action_label=a.get("action_label") if isinstance(a.get("action_label"), str) else None,
                metadata=a.get("metadata", {}) if isinstance(a.get("metadata"), dict) else {},
            ))

        critical_n = sum(1 for a in filtered_alerts if a.severity == "critical")
        warning_n = sum(1 for a in filtered_alerts if a.severity == "warning")

        result.append(AlertsByCategoryResponse(
            category=section_id,
            category_title=section_titles.get(section_id, section_id),
            alerts=filtered_alerts,
            critical_count=critical_n,
            warning_count=warning_n,
        ))

    return result


@router.post(
    "/dismiss/{alert_id}",
    response_model=DismissAlertResponse,
    summary="Alert ausblenden",
    description=(
        "Blendet einen Alert für den heutigen Tag aus. "
        "Ausgeblendete Alerts erscheinen bis zur nächsten Briefing-Generierung nicht mehr."
    ),
)
async def dismiss_alert(
    alert_id: str,
    current_user: User = Depends(get_current_active_user),
    company=Depends(require_company),
) -> DismissAlertResponse:
    """Blendet einen Briefing-Alert aus.

    Der Alert wird für die aktuelle Firma in einer In-Memory-Liste
    gespeichert und in nachfolgenden API-Anfragen herausgefiltert.

    Args:
        alert_id: ID des auszublendenden Alerts
        current_user: Eingeloggter Benutzer
        company: Aktive Firma

    Returns:
        Bestätigung der Ausblendung
    """
    company_id_str = str(company.id)

    # Eingabe-Validierung: alert_id darf nur alphanumerisch und Unterstriche sein
    if not alert_id or len(alert_id) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültige Alert-ID.",
        )

    import re as _re
    if not _re.match(r'^[a-zA-Z0-9_\-]+$', alert_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Alert-ID enthält ungültige Zeichen.",
        )

    # Alert zur Dismiss-Liste hinzufügen
    if company_id_str not in _dismissed_alerts:
        _dismissed_alerts[company_id_str] = set()
    _dismissed_alerts[company_id_str].add(alert_id)

    logger.info(
        "morning_briefing_alert_ausgeblendet",
        alert_id=alert_id,
        company_id=company_id_str,
        user_id=str(current_user.id),
    )

    return DismissAlertResponse(
        success=True,
        message=f"Alert '{alert_id}' wurde ausgeblendet.",
    )
