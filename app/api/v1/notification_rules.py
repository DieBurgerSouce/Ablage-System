"""
Notification Rules API Endpoints.

Enterprise Notification Rule Engine:
- Regeln erstellen (CRUD)
- Event-basierte Trigger-Konfiguration
- Bedingungs-Definition (conditions)
- Aktions-Konfiguration (in_app, push, email, webhook)
- Quiet Hours und Rate Limiting
- Statistiken pro Regel

Feinpoliert und durchdacht - Benutzerdefinierte Benachrichtigungsregeln.
"""

import structlog
from typing import Dict, List, Optional, Union

from app.core.types import JSONDict
from uuid import UUID
from datetime import time

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, NotificationRule
from app.api.dependencies import get_current_user, get_db
from app.services.notification.rule_engine import (
    get_notification_rule_engine,
    NotificationRuleEngine,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/notification-rules", tags=["notification-rules"])


# =============================================================================
# SCHEMAS
# =============================================================================

class RuleConditionSchema(BaseModel):
    """Schema für eine einzelne Bedingung."""
    field: str = Field(..., description="Feld im Event-Payload")
    op: str = Field(..., description="Operator: eq, ne, gt, gte, lt, lte, contains, in, etc.")
    value: Union[str, int, float, bool, List[str]] = Field(..., description="Erwarteter Wert")


class RuleConditionsSchema(BaseModel):
    """Schema für Bedingungs-Gruppe."""
    operator: str = Field("AND", description="Logischer Operator: AND, OR, NOT")
    conditions: List[RuleConditionSchema] = Field(
        default_factory=list,
        description="Liste von Bedingungen"
    )


class RuleActionSchema(BaseModel):
    """Schema für eine Aktion."""
    type: str = Field(..., description="Aktionstyp: in_app, push, email, webhook")
    title: Optional[str] = Field(None, description="Titel (für in_app/push)")
    body: Optional[str] = Field(None, description="Nachricht (für in_app/push)")
    action_url: Optional[str] = Field(None, description="URL für Klick-Aktion")
    template: Optional[str] = Field(None, description="Email-Template Name")
    subject: Optional[str] = Field(None, description="Email-Betreff")
    url: Optional[str] = Field(None, description="Webhook-URL")
    priority: str = Field("normal", description="Prioritaet: low, normal, high, urgent")
    data: Optional[JSONDict] = Field(None, description="Zusätzliche Daten")


class NotificationRuleCreateRequest(BaseModel):
    """Request zum Erstellen einer Regel."""
    name: str = Field(..., min_length=1, max_length=100, description="Name der Regel")
    description: Optional[str] = Field(None, description="Optionale Beschreibung")
    event_type: str = Field(
        ...,
        description="Event-Typ z.B. document.ocr_completed, insurance.deadline_approaching"
    )
    event_source: Optional[str] = Field(
        None,
        description="Optional: Quelle filtern (z.B. privat, business)"
    )
    conditions: Optional[JSONDict] = Field(
        default_factory=dict,
        description="Bedingungs-Definition (JSON)"
    )
    actions: List[RuleActionSchema] = Field(
        ...,
        min_length=1,
        description="Liste von Aktionen (mindestens eine)"
    )
    enabled: bool = Field(True, description="Ob die Regel aktiv ist")
    quiet_hours_start: Optional[str] = Field(
        None,
        pattern=r"^\d{2}:\d{2}$",
        description="Start der Ruhezeit (HH:MM)"
    )
    quiet_hours_end: Optional[str] = Field(
        None,
        pattern=r"^\d{2}:\d{2}$",
        description="Ende der Ruhezeit (HH:MM)"
    )
    timezone: str = Field("Europe/Berlin", description="Zeitzone für Quiet Hours")
    cooldown_minutes: Optional[int] = Field(
        None,
        ge=0,
        description="Mindestabstand zwischen Benachrichtigungen (Minuten)"
    )
    max_per_day: Optional[int] = Field(
        None,
        ge=1,
        description="Maximale Anzahl pro Tag"
    )
    priority: str = Field("normal", description="Prioritaet: low, normal, high, urgent")


class NotificationRuleUpdateRequest(BaseModel):
    """Request zum Aktualisieren einer Regel."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    event_type: Optional[str] = None
    event_source: Optional[str] = None
    conditions: Optional[JSONDict] = None
    actions: Optional[List[RuleActionSchema]] = None
    enabled: Optional[bool] = None
    quiet_hours_start: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    quiet_hours_end: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    timezone: Optional[str] = None
    cooldown_minutes: Optional[int] = Field(None, ge=0)
    max_per_day: Optional[int] = Field(None, ge=1)
    priority: Optional[str] = None


class NotificationRuleResponse(BaseModel):
    """Response für eine Regel."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: Optional[str]
    event_type: str
    event_source: Optional[str]
    conditions: JSONDict
    actions: List[JSONDict]
    enabled: bool
    quiet_hours_start: Optional[str]
    quiet_hours_end: Optional[str]
    timezone: str
    cooldown_minutes: Optional[int]
    max_per_day: Optional[int]
    priority: str
    trigger_count: int
    last_triggered_at: Optional[str]
    created_at: str
    updated_at: str


class NotificationRulesListResponse(BaseModel):
    """Response für Regelliste."""
    rules: List[NotificationRuleResponse]
    total: int


class EventTypesResponse(BaseModel):
    """Response mit verfügbaren Event-Typen."""
    event_types: List[Dict[str, str]]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _build_rule_response(rule: NotificationRule) -> NotificationRuleResponse:
    """Erstellt Response aus DB-Modell."""
    return NotificationRuleResponse(
        id=str(rule.id),
        name=rule.name,
        description=rule.description,
        event_type=rule.event_type,
        event_source=rule.event_source,
        conditions=rule.conditions or {},
        actions=rule.actions if isinstance(rule.actions, list) else [],
        enabled=rule.enabled,
        quiet_hours_start=rule.quiet_hours_start.strftime("%H:%M") if rule.quiet_hours_start else None,
        quiet_hours_end=rule.quiet_hours_end.strftime("%H:%M") if rule.quiet_hours_end else None,
        timezone=rule.timezone or "Europe/Berlin",
        cooldown_minutes=rule.cooldown_minutes,
        max_per_day=rule.max_per_day,
        priority=rule.priority or "normal",
        trigger_count=rule.trigger_count or 0,
        last_triggered_at=rule.last_triggered_at.isoformat() if rule.last_triggered_at else None,
        created_at=rule.created_at.isoformat() if rule.created_at else "",
        updated_at=rule.updated_at.isoformat() if rule.updated_at else "",
    )


def _parse_time(time_str: Optional[str]) -> Optional[time]:
    """Parst Zeit-String zu time-Objekt."""
    if not time_str:
        return None
    parts = time_str.split(":")
    return time(hour=int(parts[0]), minute=int(parts[1]))


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get(
    "/",
    response_model=NotificationRulesListResponse,
    summary="Regeln auflisten",
    description="Gibt alle Notification Rules des aktuellen Benutzers zurück."
)
async def list_rules(
    enabled_only: bool = Query(False, description="Nur aktive Regeln"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationRulesListResponse:
    """Liste aller Regeln des Benutzers."""
    engine = get_notification_rule_engine()
    rules = await engine.get_rules_for_user(
        db=db,
        user_id=current_user.id,
        enabled_only=enabled_only
    )

    return NotificationRulesListResponse(
        rules=[_build_rule_response(rule) for rule in rules],
        total=len(rules)
    )


@router.get(
    "/event-types",
    response_model=EventTypesResponse,
    summary="Verfügbare Event-Typen",
    description="Gibt alle verfügbaren Event-Typen für Regeln zurück."
)
async def list_event_types(
    current_user: User = Depends(get_current_user),
) -> EventTypesResponse:
    """Liste aller Event-Typen für Trigger."""
    from app.services.events.event_bus import EventType

    event_types = []
    for event_type in EventType:
        # Gruppiere nach Kategorie (document, property, vehicle, etc.)
        category = event_type.value.split(".")[0]
        event_types.append({
            "value": event_type.value,
            "label": event_type.name.replace("_", " ").title(),
            "category": category.capitalize(),
        })

    return EventTypesResponse(event_types=event_types)


@router.post(
    "/",
    response_model=NotificationRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Regel erstellen",
    description="Erstellt eine neue Notification Rule."
)
async def create_rule(
    request: NotificationRuleCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationRuleResponse:
    """Erstellt eine neue Regel."""
    engine = get_notification_rule_engine()

    # Actions zu Dict-Liste konvertieren
    actions_list = [action.model_dump(exclude_none=True) for action in request.actions]

    rule = await engine.create_rule(
        db=db,
        user_id=current_user.id,
        name=request.name,
        event_type=request.event_type,
        conditions=request.conditions or {},
        actions=actions_list,
        description=request.description,
        event_source=request.event_source,
        enabled=request.enabled,
        quiet_hours_start=_parse_time(request.quiet_hours_start),
        quiet_hours_end=_parse_time(request.quiet_hours_end),
        timezone=request.timezone,
        cooldown_minutes=request.cooldown_minutes,
        max_per_day=request.max_per_day,
        priority=request.priority,
    )

    logger.info(
        "notification_rule_created_via_api",
        rule_id=str(rule.id),
        user_id=str(current_user.id),
        event_type=request.event_type
    )

    return _build_rule_response(rule)


@router.get(
    "/{rule_id}",
    response_model=NotificationRuleResponse,
    summary="Regel abrufen",
    description="Gibt eine spezifische Regel zurück."
)
async def get_rule(
    rule_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationRuleResponse:
    """Ruft eine Regel ab."""
    rule = await db.get(NotificationRule, rule_id)

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regel nicht gefunden"
        )

    if rule.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Kein Zugriff auf diese Regel"
        )

    return _build_rule_response(rule)


@router.patch(
    "/{rule_id}",
    response_model=NotificationRuleResponse,
    summary="Regel aktualisieren",
    description="Aktualisiert eine bestehende Regel."
)
async def update_rule(
    rule_id: UUID,
    request: NotificationRuleUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationRuleResponse:
    """Aktualisiert eine Regel."""
    engine = get_notification_rule_engine()

    # Nur nicht-None Werte sammeln
    updates = {}
    for key, value in request.model_dump().items():
        if value is not None:
            if key == "actions":
                updates[key] = [a.model_dump(exclude_none=True) if hasattr(a, 'model_dump') else a for a in value]
            elif key in ("quiet_hours_start", "quiet_hours_end"):
                updates[key] = _parse_time(value)
            else:
                updates[key] = value

    rule = await engine.update_rule(
        db=db,
        rule_id=rule_id,
        user_id=current_user.id,
        **updates
    )

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regel nicht gefunden oder kein Zugriff"
        )

    logger.info(
        "notification_rule_updated_via_api",
        rule_id=str(rule_id),
        user_id=str(current_user.id),
        updates=list(updates.keys())
    )

    return _build_rule_response(rule)


@router.delete(
    "/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Regel löschen",
    description="Löscht eine Regel."
)
async def delete_rule(
    rule_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Löscht eine Regel."""
    engine = get_notification_rule_engine()

    deleted = await engine.delete_rule(
        db=db,
        rule_id=rule_id,
        user_id=current_user.id
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regel nicht gefunden oder kein Zugriff"
        )

    logger.info(
        "notification_rule_deleted_via_api",
        rule_id=str(rule_id),
        user_id=str(current_user.id)
    )


@router.post(
    "/{rule_id}/toggle",
    response_model=NotificationRuleResponse,
    summary="Regel aktivieren/deaktivieren",
    description="Schaltet eine Regel ein oder aus."
)
async def toggle_rule(
    rule_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationRuleResponse:
    """Schaltet Regel-Status um."""
    rule = await db.get(NotificationRule, rule_id)

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regel nicht gefunden"
        )

    if rule.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Kein Zugriff auf diese Regel"
        )

    # Toggle
    rule.enabled = not rule.enabled
    await db.commit()
    await db.refresh(rule)

    logger.info(
        "notification_rule_toggled",
        rule_id=str(rule_id),
        user_id=str(current_user.id),
        enabled=rule.enabled
    )

    return _build_rule_response(rule)


@router.get(
    "/{rule_id}/statistics",
    summary="Regel-Statistiken",
    description="Gibt Statistiken für eine Regel zurück."
)
async def get_rule_statistics(
    rule_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONDict:
    """Ruft Statistiken für eine Regel ab."""
    rule = await db.get(NotificationRule, rule_id)

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regel nicht gefunden"
        )

    if rule.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Kein Zugriff auf diese Regel"
        )

    return {
        "rule_id": str(rule.id),
        "rule_name": rule.name,
        "trigger_count": rule.trigger_count or 0,
        "last_triggered_at": rule.last_triggered_at.isoformat() if rule.last_triggered_at else None,
        "last_matched_event_id": str(rule.last_matched_event_id) if rule.last_matched_event_id else None,
        "enabled": rule.enabled,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
    }


@router.post(
    "/test",
    summary="Regel testen",
    description="Testet eine Regel gegen simulierte Event-Daten."
)
async def test_rule(
    conditions: JSONDict,
    event_data: JSONDict,
    current_user: User = Depends(get_current_user),
) -> JSONDict:
    """Testet Bedingungen gegen Event-Daten (ohne Ausführung)."""
    from app.services.notification.rule_engine import RuleConditionMatcher

    matcher = RuleConditionMatcher()
    matched = matcher.match(conditions, event_data)

    return {
        "matched": matched,
        "conditions": conditions,
        "event_data": event_data,
    }
