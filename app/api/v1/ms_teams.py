"""
Microsoft Teams Integration API Endpoints.

Ermoeglicht:
- Verbindungstest und Status
- Test-Nachrichten senden
- Webhook-Konfiguration (Admin)
- Statistiken und Monitoring

Feinpoliert und durchdacht - Enterprise Microsoft Teams-Integration.
"""

import structlog
from datetime import datetime, timezone
from typing import Optional

from app.core.types import JSONValue

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from pydantic import BaseModel, Field, field_validator
import re

from app.core.rate_limiting import limiter, get_user_identifier
from app.db.models import User
from app.api.dependencies import get_current_user, require_admin
from app.core.safe_errors import safe_error_log, safe_error_detail
from app.services.ms_teams_service import (
    get_teams_service,
    TeamsService,
    TeamsNotificationType,
    TeamsMessagePriority,
    TeamsAction,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/ms-teams", tags=["Microsoft Teams"])


# =============================================================================
# SCHEMAS
# =============================================================================


class TeamsTestMessageRequest(BaseModel):
    """Schema fuer Test-Nachricht."""
    title: str = Field(
        default="Test-Benachrichtigung",
        min_length=1,
        max_length=200,
        description="Nachricht-Titel"
    )
    message: str = Field(
        default="Dies ist eine Test-Nachricht vom Ablage-System.",
        min_length=1,
        max_length=2000,
        description="Nachricht-Text"
    )
    notification_type: str = Field(
        default="system_alert",
        description="Notification-Typ"
    )
    priority: str = Field(
        default="normal",
        description="Prioritaet"
    )
    use_adaptive_card: bool = Field(
        default=True,
        description="Adaptive Card statt Message Card verwenden"
    )

    @field_validator("notification_type")
    @classmethod
    def validate_notification_type(cls, v: str) -> str:
        """Validiert den Notification-Typ."""
        valid_types = [e.value for e in TeamsNotificationType]
        if v not in valid_types:
            raise ValueError(f"Notification-Typ muss einer von {valid_types} sein")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        """Validiert die Prioritaet."""
        valid = ["low", "normal", "high", "urgent"]
        if v not in valid:
            raise ValueError(f"Prioritaet muss eine von {valid} sein")
        return v


class TeamsTestMessageResponse(BaseModel):
    """Schema fuer Test-Nachricht Response."""
    success: bool
    message: Optional[str] = None
    error: Optional[str] = None


class TeamsConnectionStatus(BaseModel):
    """Schema fuer Verbindungs-Status."""
    enabled: bool
    webhook_configured: bool
    default_channel: Optional[str] = None
    webhook_test: Optional[str] = None


class TeamsWebhookConfigRequest(BaseModel):
    """Schema fuer Webhook-Konfiguration."""
    webhook_url: str = Field(
        ...,
        min_length=10,
        max_length=500,
        description="Microsoft Teams Incoming Webhook URL"
    )
    default_channel: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Standard-Kanal Name"
    )
    enabled: bool = Field(
        default=True,
        description="Integration aktivieren"
    )
    notification_types: Optional[list[str]] = Field(
        default=None,
        description="Aktivierte Notification-Typen"
    )

    @field_validator("webhook_url")
    @classmethod
    def validate_webhook_url(cls, v: str) -> str:
        """Validiert die Webhook-URL."""
        if not v.startswith("https://"):
            raise ValueError("Webhook-URL muss mit https:// beginnen")
        if "webhook.office.com" not in v and "logic.azure.com" not in v:
            raise ValueError("Webhook-URL muss auf webhook.office.com oder logic.azure.com zeigen")
        return v

    @field_validator("notification_types")
    @classmethod
    def validate_notification_types(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        """Validiert die Notification-Typen."""
        if v is None:
            return v
        valid_types = [e.value for e in TeamsNotificationType]
        for t in v:
            if t not in valid_types:
                raise ValueError(f"Ungueltiger Notification-Typ: {t}. Muss einer von {valid_types} sein")
        return v


class TeamsWebhookConfigResponse(BaseModel):
    """Schema fuer Webhook-Konfiguration Response."""
    success: bool
    message: str
    enabled: bool
    webhook_configured: bool


class TeamsNotificationTypeInfo(BaseModel):
    """Schema fuer Notification-Typ Information."""
    type: str
    name: str
    description: str
    icon: str


class TeamsStatistics(BaseModel):
    """Schema fuer Teams-Statistiken."""
    enabled: bool
    webhook_configured: bool
    notification_types_enabled: int
    rate_limit_per_minute: int
    messages_sent_this_minute: int


class TeamsSendNotificationRequest(BaseModel):
    """Schema fuer benutzerdefinierte Benachrichtigung."""
    notification_type: str = Field(..., description="Notification-Typ")
    title: str = Field(..., min_length=1, max_length=200, description="Titel")
    message: str = Field(..., min_length=1, max_length=2000, description="Nachricht")
    context: Optional[dict[str, JSONValue]] = Field(default=None, description="Zusaetzlicher Kontext")
    priority: str = Field(default="normal", description="Prioritaet")
    actions: Optional[list[dict[str, str]]] = Field(default=None, description="Aktions-Buttons")

    @field_validator("notification_type")
    @classmethod
    def validate_notification_type(cls, v: str) -> str:
        """Validiert den Notification-Typ."""
        valid_types = [e.value for e in TeamsNotificationType]
        if v not in valid_types:
            raise ValueError(f"Notification-Typ muss einer von {valid_types} sein")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        """Validiert die Prioritaet."""
        valid = ["low", "normal", "high", "urgent"]
        if v not in valid:
            raise ValueError(f"Prioritaet muss eine von {valid} sein")
        return v

    @field_validator("actions")
    @classmethod
    def validate_actions(cls, v: Optional[list[dict[str, str]]]) -> Optional[list[dict[str, str]]]:
        """Validiert die Aktionen."""
        if v is None:
            return v
        for action in v:
            if "title" not in action:
                raise ValueError("Jede Aktion muss einen 'title' haben")
            if "url" not in action and "data" not in action:
                raise ValueError("Jede Aktion muss entweder 'url' oder 'data' haben")
            if "url" in action and not action["url"].startswith("https://"):
                raise ValueError("Action URLs muessen mit https:// beginnen")
        return v


# =============================================================================
# ENDPOINTS: Connection & Status
# =============================================================================


@router.get(
    "/status",
    response_model=TeamsConnectionStatus,
    summary="Verbindungs-Status pruefen",
    description="Prueft den Status der Microsoft Teams-Integration.",
)
async def get_teams_status(
    current_user: User = Depends(require_admin),
) -> TeamsConnectionStatus:
    """Gibt den aktuellen Teams-Verbindungsstatus zurueck."""
    service = get_teams_service()
    status_data = await service.test_connection()
    return TeamsConnectionStatus(**status_data)


@router.get(
    "/statistics",
    response_model=TeamsStatistics,
    summary="Teams-Statistiken abrufen",
    description="Liefert Statistiken zur Microsoft Teams-Integration.",
)
async def get_teams_statistics(
    current_user: User = Depends(require_admin),
) -> TeamsStatistics:
    """Berechnet und liefert Teams-Statistiken."""
    service = get_teams_service()

    return TeamsStatistics(
        enabled=service.is_enabled,
        webhook_configured=bool(service._webhook_url),
        notification_types_enabled=len(service._notification_types),
        rate_limit_per_minute=service._rate_limit_per_minute,
        messages_sent_this_minute=len(service._rate_limit_window),
    )


# =============================================================================
# ENDPOINTS: Test & Notifications
# =============================================================================


@limiter.limit("10/minute", key_func=get_user_identifier)
@router.post(
    "/test",
    response_model=TeamsTestMessageResponse,
    summary="Test-Nachricht senden",
    description="Sendet eine Test-Nachricht an Microsoft Teams.",
)
async def send_test_message(
    request: Request,
    test_data: TeamsTestMessageRequest,
    current_user: User = Depends(require_admin),
) -> TeamsTestMessageResponse:
    """Sendet eine Test-Nachricht an Microsoft Teams."""
    service = get_teams_service()

    if not service.is_enabled:
        return TeamsTestMessageResponse(
            success=False,
            error="Microsoft Teams-Integration ist nicht aktiviert",
        )

    try:
        success = await service.send_notification(
            notification_type=test_data.notification_type,
            title=test_data.title,
            message=test_data.message,
            context={
                "gesendet_von": current_user.username if hasattr(current_user, 'username') else current_user.email,
                "zeitpunkt": datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC"),
            },
            priority=TeamsMessagePriority(test_data.priority),
            use_adaptive_card=test_data.use_adaptive_card,
        )

        if success:
            logger.info(
                "teams_test_message_sent",
                user_id=str(current_user.id),
            )
            return TeamsTestMessageResponse(
                success=True,
                message="Test-Nachricht erfolgreich gesendet",
            )
        else:
            return TeamsTestMessageResponse(
                success=False,
                error="Nachricht konnte nicht gesendet werden",
            )

    except Exception as e:
        logger.error(
            "teams_test_message_failed",
            **safe_error_log(e),
            user_id=str(current_user.id),
        )
        return TeamsTestMessageResponse(
            success=False,
            error=safe_error_detail(e, "Teams-Benachrichtigung"),
        )


@limiter.limit("30/minute", key_func=get_user_identifier)
@router.post(
    "/send",
    response_model=TeamsTestMessageResponse,
    summary="Benachrichtigung senden",
    description="Sendet eine benutzerdefinierte Benachrichtigung an Microsoft Teams.",
)
async def send_notification(
    request: Request,
    notification_data: TeamsSendNotificationRequest,
    current_user: User = Depends(require_admin),
) -> TeamsTestMessageResponse:
    """Sendet eine benutzerdefinierte Benachrichtigung an Microsoft Teams."""
    service = get_teams_service()

    if not service.is_enabled:
        return TeamsTestMessageResponse(
            success=False,
            error="Microsoft Teams-Integration ist nicht aktiviert",
        )

    try:
        # Actions konvertieren
        actions = None
        if notification_data.actions:
            actions = [
                TeamsAction(
                    type="Action.OpenUrl",
                    title=action.get("title", ""),
                    url=action.get("url"),
                )
                for action in notification_data.actions
                if action.get("url")
            ]

        success = await service.send_notification(
            notification_type=notification_data.notification_type,
            title=notification_data.title,
            message=notification_data.message,
            context=notification_data.context,
            priority=TeamsMessagePriority(notification_data.priority),
            actions=actions,
        )

        if success:
            logger.info(
                "teams_notification_sent",
                notification_type=notification_data.notification_type,
                user_id=str(current_user.id),
            )
            return TeamsTestMessageResponse(
                success=True,
                message="Benachrichtigung erfolgreich gesendet",
            )
        else:
            return TeamsTestMessageResponse(
                success=False,
                error="Benachrichtigung konnte nicht gesendet werden",
            )

    except Exception as e:
        logger.error(
            "teams_notification_failed",
            **safe_error_log(e),
            user_id=str(current_user.id),
        )
        return TeamsTestMessageResponse(
            success=False,
            error=safe_error_detail(e, "Teams-Benachrichtigung"),
        )


# =============================================================================
# ENDPOINTS: Configuration (Admin)
# =============================================================================


@limiter.limit("5/minute", key_func=get_user_identifier)
@router.post(
    "/webhook",
    response_model=TeamsWebhookConfigResponse,
    summary="Webhook konfigurieren",
    description="Konfiguriert den Microsoft Teams Incoming Webhook (nur fuer Admins).",
)
async def configure_webhook(
    request: Request,
    config_data: TeamsWebhookConfigRequest,
    current_user: User = Depends(require_admin),
) -> TeamsWebhookConfigResponse:
    """
    Konfiguriert den Microsoft Teams Incoming Webhook.

    HINWEIS: Diese Konfiguration wird zur Laufzeit angewendet.
    Fuer persistente Konfiguration muessen die Umgebungsvariablen
    TEAMS_WEBHOOK_URL, TEAMS_ENABLED, etc. gesetzt werden.
    """
    service = get_teams_service()

    try:
        # Runtime-Konfiguration anwenden
        # SECURITY: Keine Secrets loggen!
        service._webhook_url = config_data.webhook_url
        service._enabled = config_data.enabled

        if config_data.default_channel:
            service._default_channel = config_data.default_channel

        if config_data.notification_types:
            service._notification_types = set(config_data.notification_types)

        # Konfiguration validieren
        service._validate_config()

        logger.info(
            "teams_webhook_configured",
            enabled=config_data.enabled,
            user_id=str(current_user.id),
        )

        return TeamsWebhookConfigResponse(
            success=True,
            message="Webhook-Konfiguration erfolgreich angewendet",
            enabled=service._enabled,
            webhook_configured=bool(service._webhook_url),
        )

    except Exception as e:
        logger.error(
            "teams_webhook_config_failed",
            **safe_error_log(e),
            user_id=str(current_user.id),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Webhook-Konfiguration"),
        )


# =============================================================================
# ENDPOINTS: Notification Types
# =============================================================================


@router.get(
    "/notification-types",
    response_model=list[TeamsNotificationTypeInfo],
    summary="Verfuegbare Notification-Typen",
    description="Listet alle verfuegbaren Microsoft Teams-Notification-Typen auf.",
)
async def get_notification_types(
    current_user: User = Depends(get_current_user),
) -> list[TeamsNotificationTypeInfo]:
    """Gibt alle verfuegbaren Notification-Typen zurueck."""
    types = [
        TeamsNotificationTypeInfo(
            type="document_processed",
            name="Dokument verarbeitet",
            description="Wenn ein Dokument erfolgreich verarbeitet wurde",
            icon="\u2705",
        ),
        TeamsNotificationTypeInfo(
            type="document_error",
            name="Dokumentfehler",
            description="Wenn bei der Dokumentverarbeitung ein Fehler auftritt",
            icon="\u274C",
        ),
        TeamsNotificationTypeInfo(
            type="approval_required",
            name="Freigabe erforderlich",
            description="Wenn eine Freigabe angefordert wird",
            icon="\u23F3",
        ),
        TeamsNotificationTypeInfo(
            type="approval_completed",
            name="Freigabe erteilt",
            description="Wenn eine Freigabe erteilt oder abgelehnt wird",
            icon="\u2714\uFE0F",
        ),
        TeamsNotificationTypeInfo(
            type="workflow_completed",
            name="Workflow abgeschlossen",
            description="Wenn ein Workflow-Durchlauf abgeschlossen ist",
            icon="\U0001F3C1",
        ),
        TeamsNotificationTypeInfo(
            type="high_risk_entity",
            name="Hochrisiko-Partner",
            description="Wenn ein Geschaeftspartner hohen Risikowert erreicht",
            icon="\u26A0\uFE0F",
        ),
        TeamsNotificationTypeInfo(
            type="dunning_escalation",
            name="Mahneskalation",
            description="Wenn eine Mahnstufe erhoeht wird",
            icon="\u26A0\uFE0F",
        ),
        TeamsNotificationTypeInfo(
            type="skonto_expiring",
            name="Skonto-Frist",
            description="Wenn eine Skonto-Frist auslaeuft",
            icon="\U0001F4B0",
        ),
        TeamsNotificationTypeInfo(
            type="payment_reminder",
            name="Zahlungserinnerung",
            description="Erinnerung an ausstehende Zahlungen",
            icon="\U0001F4B3",
        ),
        TeamsNotificationTypeInfo(
            type="report_generated",
            name="Bericht erstellt",
            description="Wenn ein geplanter Bericht generiert wurde",
            icon="\U0001F4CA",
        ),
        TeamsNotificationTypeInfo(
            type="system_alert",
            name="System-Warnung",
            description="Wichtige System-Benachrichtigungen",
            icon="\U0001F6A8",
        ),
        TeamsNotificationTypeInfo(
            type="error_notification",
            name="Fehlerbenachrichtigung",
            description="Kritische Fehler und Probleme",
            icon="\U0001F6AB",
        ),
    ]
    return types


# =============================================================================
# ENDPOINTS: Health Check
# =============================================================================


@router.get(
    "/health",
    summary="Health Check",
    description="Prueft ob der Microsoft Teams-Service verfuegbar ist.",
)
async def health_check() -> dict[str, JSONValue]:
    """Health Check fuer den Teams-Service."""
    service = get_teams_service()

    return {
        "status": "healthy" if service.is_enabled else "disabled",
        "enabled": service.is_enabled,
        "webhook_configured": bool(service._webhook_url),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
