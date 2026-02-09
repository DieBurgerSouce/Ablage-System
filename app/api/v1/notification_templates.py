"""Notification Template API - CRUD und Preview-Endpunkte.

Dieser Router stellt API-Endpunkte fuer die Verwaltung von
Benachrichtigungsvorlagen bereit.
"""

import uuid
from typing import List, Optional, Dict
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field, validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.db.models import User
from app.services.notification.template_engine import (
    get_template_engine,
    NotificationTemplateEngine,
    PRESET_TEMPLATES,
)
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/notification-templates", tags=["notification-templates"])


# Pydantic Schemas


class TemplateVariables(BaseModel):
    """Schema fuer Template-Variablen."""

    required: List[str] = Field(default_factory=list)
    optional: List[str] = Field(default_factory=list)


class NotificationTemplateCreate(BaseModel):
    """Schema zum Erstellen einer Vorlage."""

    name: str = Field(..., min_length=1, max_length=200)
    category: str = Field(..., min_length=1, max_length=50)
    subject_template: str = Field(..., min_length=1)
    body_template: str = Field(..., min_length=1)
    variables: Optional[TemplateVariables] = None
    channels: Optional[List[str]] = None

    @validator("category")
    def validate_category(cls, v: str) -> str:
        """Validiert Kategorie."""
        allowed = ["document", "alert", "workflow", "system", "security", "finance", "compliance", "reminder"]
        if v not in allowed:
            raise ValueError(f"Kategorie muss eine von {allowed} sein")
        return v

    @validator("channels", each_item=True)
    def validate_channels(cls, v: str) -> str:
        """Validiert Channels."""
        allowed = [
            "email",
            "slack",
            "teams",
            "push",
            "sms",
            "whatsapp",
            "in_app",
            "websocket",
        ]
        if v not in allowed:
            raise ValueError(f"Channel muss einer von {allowed} sein")
        return v


class NotificationTemplateUpdate(BaseModel):
    """Schema zum Aktualisieren einer Vorlage."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    category: Optional[str] = Field(None, min_length=1, max_length=50)
    subject_template: Optional[str] = Field(None, min_length=1)
    body_template: Optional[str] = Field(None, min_length=1)
    variables: Optional[TemplateVariables] = None
    channels: Optional[List[str]] = None
    is_active: Optional[bool] = None

    @validator("category")
    def validate_category(cls, v: Optional[str]) -> Optional[str]:
        """Validiert Kategorie."""
        if v is None:
            return v
        allowed = ["document", "alert", "workflow", "system", "security", "finance", "compliance", "reminder"]
        if v not in allowed:
            raise ValueError(f"Kategorie muss eine von {allowed} sein")
        return v

    @validator("channels", each_item=True)
    def validate_channels(cls, v: str) -> str:
        """Validiert Channels."""
        allowed = [
            "email",
            "slack",
            "teams",
            "push",
            "sms",
            "whatsapp",
            "in_app",
            "websocket",
        ]
        if v not in allowed:
            raise ValueError(f"Channel muss einer von {allowed} sein")
        return v


class NotificationTemplateResponse(BaseModel):
    """Schema fuer Vorlage-Response."""

    id: uuid.UUID
    name: str
    category: str
    subject_template: str
    body_template: str
    variables: Optional[Dict[str, List[str]]] = None
    channels: Optional[List[str]] = None
    is_active: bool
    created_by_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TemplatePreviewRequest(BaseModel):
    """Schema fuer Preview-Anfrage."""

    sample_data: Optional[Dict[str, str]] = None


class TemplatePreviewResponse(BaseModel):
    """Schema fuer Preview-Response."""

    subject: str
    body: str


class TemplateSendRequest(BaseModel):
    """Schema zum Senden mit Vorlage."""

    recipient_id: uuid.UUID
    variables: Dict[str, str]
    channels: Optional[List[str]] = None
    severity: str = Field(default="info")

    @validator("severity")
    def validate_severity(cls, v: str) -> str:
        """Validiert Severity."""
        allowed = ["info", "low", "medium", "high", "critical"]
        if v not in allowed:
            raise ValueError(f"Severity muss eine von {allowed} sein")
        return v


class TemplateSendResponse(BaseModel):
    """Schema fuer Send-Response."""

    success: bool
    message: str
    results: Dict[str, bool]


class PresetTemplateResponse(BaseModel):
    """Schema fuer Preset-Template."""

    key: str
    name: str
    category: str
    subject: str
    body: str
    variables: Dict[str, List[str]]
    channels: List[str]


# API Endpoints


@router.get(
    "/",
    response_model=List[NotificationTemplateResponse],
    summary="Liste alle Vorlagen auf",
)
async def list_templates(
    category: Optional[str] = Query(None, description="Filter nach Kategorie"),
    active_only: bool = Query(True, description="Nur aktive Vorlagen"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[NotificationTemplateResponse]:
    """Listet alle Benachrichtigungsvorlagen auf.

    Args:
        category: Optionaler Kategoriefilter
        active_only: Nur aktive Vorlagen anzeigen
        current_user: Aktueller User
        db: Datenbank-Session

    Returns:
        Liste von NotificationTemplateResponse
    """
    engine = get_template_engine(db)

    try:
        templates = await engine.list_templates(
            category=category,
            active_only=active_only,
        )

        return [
            NotificationTemplateResponse.model_validate(t)
            for t in templates
        ]

    except Exception as e:
        logger.error("list_templates_failed", **safe_error_log(e), category=category)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen der Vorlagen",
        )


@router.post(
    "/",
    response_model=NotificationTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Erstelle neue Vorlage",
)
async def create_template(
    template: NotificationTemplateCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationTemplateResponse:
    """Erstellt eine neue Benachrichtigungsvorlage.

    Args:
        template: Template-Daten
        current_user: Aktueller User
        db: Datenbank-Session

    Returns:
        NotificationTemplateResponse
    """
    engine = get_template_engine(db)

    try:
        variables_dict = None
        if template.variables:
            variables_dict = {
                "required": template.variables.required,
                "optional": template.variables.optional,
            }

        created = await engine.create_template(
            name=template.name,
            category=template.category,
            subject_template=template.subject_template,
            body_template=template.body_template,
            variables=variables_dict,
            channels=template.channels,
            created_by_id=current_user.id,
        )

        return NotificationTemplateResponse.model_validate(created)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("create_template_failed", **safe_error_log(e), template_name=template.name)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Erstellen der Vorlage",
        )


@router.get(
    "/presets/list",
    response_model=List[PresetTemplateResponse],
    summary="Liste verfuegbare Preset-Vorlagen",
)
async def list_preset_templates(
    current_user: User = Depends(get_current_active_user),
) -> List[PresetTemplateResponse]:
    """Listet alle verfuegbaren Preset-Vorlagen auf.

    Args:
        current_user: Aktueller User

    Returns:
        Liste von PresetTemplateResponse
    """
    presets = []
    for key, preset in PRESET_TEMPLATES.items():
        presets.append(
            PresetTemplateResponse(
                key=key,
                name=preset["name"],
                category=preset["category"],
                subject=preset["subject"],
                body=preset["body"],
                variables=preset["variables"],
                channels=preset["channels"],
            )
        )

    return presets


@router.post(
    "/presets/{preset_key}/install",
    response_model=NotificationTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Installiere Preset-Vorlage",
)
async def install_preset_template(
    preset_key: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationTemplateResponse:
    """Installiert eine Preset-Vorlage in die Datenbank.

    Args:
        preset_key: Key der Preset-Vorlage (z.B. APPROVAL_REQUESTED)
        current_user: Aktueller User
        db: Datenbank-Session

    Returns:
        NotificationTemplateResponse
    """
    if preset_key not in PRESET_TEMPLATES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preset '{preset_key}' nicht gefunden",
        )

    preset = PRESET_TEMPLATES[preset_key]
    engine = get_template_engine(db)

    try:
        created = await engine.create_template(
            name=preset["name"],
            category=preset["category"],
            subject_template=preset["subject"],
            body_template=preset["body"],
            variables=preset["variables"],
            channels=preset["channels"],
            created_by_id=current_user.id,
        )

        return NotificationTemplateResponse.model_validate(created)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("install_preset_failed", **safe_error_log(e), preset_key=preset_key)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Installieren des Presets",
        )


@router.get(
    "/{template_id}",
    response_model=NotificationTemplateResponse,
    summary="Hole einzelne Vorlage",
)
async def get_template(
    template_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationTemplateResponse:
    """Holt eine einzelne Benachrichtigungsvorlage.

    Args:
        template_id: UUID der Vorlage
        current_user: Aktueller User
        db: Datenbank-Session

    Returns:
        NotificationTemplateResponse
    """
    engine = get_template_engine(db)

    try:
        template = await engine.get_template(template_id)
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vorlage nicht gefunden",
            )

        return NotificationTemplateResponse.model_validate(template)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_template_failed", **safe_error_log(e), template_id=str(template_id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen der Vorlage",
        )


@router.patch(
    "/{template_id}",
    response_model=NotificationTemplateResponse,
    summary="Aktualisiere Vorlage",
)
async def update_template(
    template_id: uuid.UUID,
    template: NotificationTemplateUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationTemplateResponse:
    """Aktualisiert eine bestehende Benachrichtigungsvorlage.

    Args:
        template_id: UUID der Vorlage
        template: Update-Daten
        current_user: Aktueller User
        db: Datenbank-Session

    Returns:
        NotificationTemplateResponse
    """
    engine = get_template_engine(db)

    try:
        variables_dict = None
        if template.variables:
            variables_dict = {
                "required": template.variables.required,
                "optional": template.variables.optional,
            }

        updated = await engine.update_template(
            template_id=template_id,
            name=template.name,
            category=template.category,
            subject_template=template.subject_template,
            body_template=template.body_template,
            variables=variables_dict,
            channels=template.channels,
            is_active=template.is_active,
        )

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vorlage nicht gefunden",
            )

        return NotificationTemplateResponse.model_validate(updated)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("update_template_failed", **safe_error_log(e), template_id=str(template_id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Aktualisieren der Vorlage",
        )


@router.delete(
    "/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Loesche Vorlage (Soft-Delete)",
)
async def delete_template(
    template_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Loescht eine Benachrichtigungsvorlage (Soft-Delete).

    Args:
        template_id: UUID der Vorlage
        current_user: Aktueller User
        db: Datenbank-Session
    """
    engine = get_template_engine(db)

    try:
        success = await engine.delete_template(template_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vorlage nicht gefunden",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_template_failed", **safe_error_log(e), template_id=str(template_id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Loeschen der Vorlage",
        )


@router.post(
    "/{template_id}/preview",
    response_model=TemplatePreviewResponse,
    summary="Vorschau einer Vorlage",
)
async def preview_template(
    template_id: uuid.UUID,
    request: TemplatePreviewRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> TemplatePreviewResponse:
    """Zeigt eine Vorschau der gerenderten Vorlage.

    Args:
        template_id: UUID der Vorlage
        request: Preview-Request mit optionalen Beispieldaten
        current_user: Aktueller User
        db: Datenbank-Session

    Returns:
        TemplatePreviewResponse mit gerendertem Subject und Body
    """
    engine = get_template_engine(db)

    try:
        preview = await engine.preview_template(
            template_id=template_id,
            sample_data=request.sample_data,
        )

        return TemplatePreviewResponse(
            subject=preview["subject"],
            body=preview["body"],
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error("preview_template_failed", **safe_error_log(e), template_id=str(template_id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler bei der Vorschau",
        )


@router.post(
    "/{template_id}/send",
    response_model=TemplateSendResponse,
    summary="Sende Benachrichtigung mit Vorlage",
)
async def send_with_template(
    template_id: uuid.UUID,
    request: TemplateSendRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> TemplateSendResponse:
    """Rendert Vorlage und sendet Benachrichtigung.

    Args:
        template_id: UUID der Vorlage
        request: Send-Request mit Variablen und Empfaenger
        current_user: Aktueller User
        db: Datenbank-Session

    Returns:
        TemplateSendResponse mit Erfolgsstatus
    """
    engine = get_template_engine(db)

    try:
        result = await engine.send_with_template(
            template_id=template_id,
            variables=request.variables,
            recipient_id=request.recipient_id,
            channels=request.channels,
            severity=request.severity,
        )

        return TemplateSendResponse(
            success=result["success"],
            message=result["message"],
            results=result["results"],
        )

    except Exception as e:
        logger.error("send_template_failed", **safe_error_log(e), template_id=str(template_id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Senden der Benachrichtigung",
        )
