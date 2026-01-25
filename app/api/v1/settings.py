"""User Settings API endpoints.

Provides REST API endpoints for:
- User preferences (display mode, language)
- OCR defaults
- Notification preferences
- Privacy settings
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.db.models import User
from app.db.database import get_db
from app.api.dependencies import get_current_active_user

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


# ==================== Schemas ====================

class DisplaySettings(BaseModel):
    """Anzeigeeinstellungen."""
    display_mode: str = Field(
        "dark",
        description="Anzeigemodus: dark, light, whitescreen, blackscreen"
    )
    language: str = Field("de", description="Sprache: de, en")
    items_per_page: int = Field(25, ge=10, le=100, description="Elemente pro Seite")
    show_previews: bool = Field(True, description="Dokumentvorschau anzeigen")
    compact_view: bool = Field(False, description="Kompakte Listenansicht")


class OCRSettings(BaseModel):
    """OCR-Einstellungen."""
    default_backend: str = Field(
        "auto",
        description="Standard-OCR-Backend: auto, deepseek, got_ocr, surya"
    )
    default_language: str = Field("de", description="Standard-Dokumentsprache")
    auto_start_ocr: bool = Field(True, description="OCR automatisch starten")
    default_priority: int = Field(5, ge=1, le=10, description="Standard-Priorität")


class NotificationSettings(BaseModel):
    """Benachrichtigungseinstellungen."""
    email_on_ocr_complete: bool = Field(True, description="E-Mail bei OCR-Abschluss")
    email_on_ocr_failed: bool = Field(True, description="E-Mail bei OCR-Fehler")
    email_on_share: bool = Field(True, description="E-Mail bei Dokumentfreigabe")
    email_digest: str = Field(
        "none",
        description="E-Mail-Zusammenfassung: none, daily, weekly"
    )


class PrivacySettings(BaseModel):
    """Datenschutzeinstellungen."""
    share_analytics: bool = Field(False, description="Anonyme Nutzungsstatistiken teilen")
    show_profile_to_others: bool = Field(True, description="Profil für andere sichtbar")
    allow_search_indexing: bool = Field(True, description="Dokumente in Suche aufnehmen")


# ==================== Widget Config Schemas ====================

class WidgetPosition(BaseModel):
    """Position und Groesse eines Widgets im Grid."""
    id: str = Field(..., description="Eindeutige Widget-ID")
    type: str = Field(..., description="Widget-Typ")
    x: int = Field(..., ge=0, le=11, description="X-Position im Grid (0-11)")
    y: int = Field(..., ge=0, description="Y-Position im Grid")
    w: int = Field(..., ge=1, le=12, description="Breite in Grid-Spalten (1-12)")
    h: int = Field(..., ge=1, le=6, description="Hoehe in Grid-Zeilen (1-6)")


class WidgetSettings(BaseModel):
    """Individuelle Widget-Einstellungen."""
    time_range: Optional[str] = Field(None, description="Zeitraum: 7d, 30d, 90d, 1y")
    filter_tags: Optional[list[str]] = Field(None, description="Filter-Tags")
    show_legend: Optional[bool] = Field(None, description="Legende anzeigen")
    chart_type: Optional[str] = Field(None, description="Diagrammtyp: line, bar, pie")
    max_items: Optional[int] = Field(None, ge=5, le=50, description="Max. angezeigte Elemente")


class WidgetConfigResponse(BaseModel):
    """Vollstaendige Widget-Konfiguration."""
    widgets: list[WidgetPosition]
    active_preset: Optional[str] = Field(None, description="Aktives Preset")
    compact_mode: bool = Field(False, description="Kompakter Modus")
    widget_settings: Dict[str, WidgetSettings] = Field(
        default_factory=dict,
        description="Individuelle Einstellungen pro Widget (key=widget_id)"
    )
    last_synced: Optional[datetime] = None


class UpdateWidgetConfigRequest(BaseModel):
    """Request zum Aktualisieren der Widget-Konfiguration."""
    widgets: Optional[list[WidgetPosition]] = None
    active_preset: Optional[str] = None
    compact_mode: Optional[bool] = None
    widget_settings: Optional[Dict[str, WidgetSettings]] = None


class UserSettingsResponse(BaseModel):
    """Vollständige Benutzereinstellungen."""
    display: DisplaySettings
    ocr: OCRSettings
    notifications: NotificationSettings
    privacy: PrivacySettings
    last_updated: datetime


class UpdateSettingsRequest(BaseModel):
    """Request zum Aktualisieren von Einstellungen."""
    display: Optional[DisplaySettings] = None
    ocr: Optional[OCRSettings] = None
    notifications: Optional[NotificationSettings] = None
    privacy: Optional[PrivacySettings] = None


# ==================== Default Settings ====================

DEFAULT_SETTINGS = {
    "display": {
        "display_mode": "dark",
        "language": "de",
        "items_per_page": 25,
        "show_previews": True,
        "compact_view": False
    },
    "ocr": {
        "default_backend": "auto",
        "default_language": "de",
        "auto_start_ocr": True,
        "default_priority": 5
    },
    "notifications": {
        "email_on_ocr_complete": True,
        "email_on_ocr_failed": True,
        "email_on_share": True,
        "email_digest": "none"
    },
    "privacy": {
        "share_analytics": False,
        "show_profile_to_others": True,
        "allow_search_indexing": True
    },
    "last_updated": None
}

DEFAULT_WIDGET_CONFIG = {
    "widgets": [
        {"id": "today", "type": "today", "x": 0, "y": 0, "w": 4, "h": 3},
        {"id": "system", "type": "system-status", "x": 4, "y": 0, "w": 4, "h": 3},
        {"id": "finance", "type": "finance-status", "x": 8, "y": 0, "w": 4, "h": 3},
        {"id": "quick", "type": "quick-links", "x": 0, "y": 3, "w": 4, "h": 2},
        {"id": "upload", "type": "upload", "x": 4, "y": 3, "w": 4, "h": 3},
        {"id": "recent", "type": "recent-documents", "x": 8, "y": 3, "w": 4, "h": 3},
    ],
    "active_preset": "default",
    "compact_mode": False,
    "widget_settings": {},
    "last_synced": None
}


# ==================== Helper Functions ====================

def get_user_settings(user: User) -> Dict[str, Any]:
    """Lädt Benutzereinstellungen aus User.preferences oder gibt Defaults zurück."""
    settings = dict(DEFAULT_SETTINGS)

    if user.preferences:
        # Merge user preferences with defaults
        for key in ["display", "ocr", "notifications", "privacy"]:
            if key in user.preferences:
                settings[key].update(user.preferences[key])
        if "last_updated" in user.preferences:
            settings["last_updated"] = user.preferences["last_updated"]

    return settings


# ==================== Endpoints ====================

@router.get("/", response_model=UserSettingsResponse)
async def get_settings(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Alle Benutzereinstellungen abrufen.

    Gibt alle Einstellungen zurück, einschließlich:
    - Anzeigeeinstellungen
    - OCR-Defaults
    - Benachrichtigungen
    - Datenschutz
    """
    settings = get_user_settings(current_user)

    return UserSettingsResponse(
        display=DisplaySettings(**settings["display"]),
        ocr=OCRSettings(**settings["ocr"]),
        notifications=NotificationSettings(**settings["notifications"]),
        privacy=PrivacySettings(**settings["privacy"]),
        last_updated=settings["last_updated"] or current_user.created_at
    )


@router.put("/", response_model=UserSettingsResponse)
async def update_settings(
    request: UpdateSettingsRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Benutzereinstellungen aktualisieren.

    Aktualisiert nur die angegebenen Einstellungsbereiche.
    Nicht angegebene Bereiche bleiben unverändert.

    **Beispiel:**
    ```
    PUT /api/v1/settings/
    {
        "display": {"display_mode": "light"},
        "ocr": {"default_backend": "deepseek"}
    }
    ```
    """
    # Aktuelle Einstellungen laden
    current_settings = get_user_settings(current_user)

    # Einstellungen aktualisieren
    if request.display:
        for key, value in request.display.model_dump(exclude_unset=True).items():
            if key == "display_mode":
                valid_modes = ["dark", "light", "whitescreen", "blackscreen"]
                if value not in valid_modes:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Ungültiger Anzeigemodus. Erlaubt: {', '.join(valid_modes)}"
                    )
            if key == "language" and value not in ["de", "en"]:
                raise HTTPException(
                    status_code=400,
                    detail="Ungültige Sprache. Erlaubt: de, en"
                )
            current_settings["display"][key] = value

    if request.ocr:
        for key, value in request.ocr.model_dump(exclude_unset=True).items():
            if key == "default_backend":
                valid_backends = ["auto", "deepseek", "got_ocr", "surya"]
                if value not in valid_backends:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Ungültiges Backend. Erlaubt: {', '.join(valid_backends)}"
                    )
            current_settings["ocr"][key] = value

    if request.notifications:
        for key, value in request.notifications.model_dump(exclude_unset=True).items():
            if key == "email_digest" and value not in ["none", "daily", "weekly"]:
                raise HTTPException(
                    status_code=400,
                    detail="Ungültige Digest-Frequenz. Erlaubt: none, daily, weekly"
                )
            current_settings["notifications"][key] = value

    if request.privacy:
        for key, value in request.privacy.model_dump(exclude_unset=True).items():
            current_settings["privacy"][key] = value

    # Timestamp aktualisieren
    current_settings["last_updated"] = datetime.now(timezone.utc).isoformat()

    # In DB speichern
    current_user.preferences = current_settings
    await db.commit()

    logger.info(
        "user_settings_updated",
        user_id=str(current_user.id),
        updated_sections=[
            k for k in ["display", "ocr", "notifications", "privacy"]
            if getattr(request, k) is not None
        ]
    )

    return UserSettingsResponse(
        display=DisplaySettings(**current_settings["display"]),
        ocr=OCRSettings(**current_settings["ocr"]),
        notifications=NotificationSettings(**current_settings["notifications"]),
        privacy=PrivacySettings(**current_settings["privacy"]),
        last_updated=datetime.fromisoformat(current_settings["last_updated"])
    )


@router.get("/display", response_model=DisplaySettings)
async def get_display_settings(
    current_user: User = Depends(get_current_active_user)
):
    """Nur Anzeigeeinstellungen abrufen."""
    settings = get_user_settings(current_user)
    return DisplaySettings(**settings["display"])


@router.put("/display", response_model=DisplaySettings)
async def update_display_settings(
    request: DisplaySettings,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Nur Anzeigeeinstellungen aktualisieren."""
    # Validierung
    valid_modes = ["dark", "light", "whitescreen", "blackscreen"]
    if request.display_mode not in valid_modes:
        raise HTTPException(
            status_code=400,
            detail=f"Ungültiger Anzeigemodus. Erlaubt: {', '.join(valid_modes)}"
        )
    if request.language not in ["de", "en"]:
        raise HTTPException(
            status_code=400,
            detail="Ungültige Sprache. Erlaubt: de, en"
        )

    settings = get_user_settings(current_user)
    settings["display"] = request.model_dump()
    settings["last_updated"] = datetime.now(timezone.utc).isoformat()

    current_user.preferences = settings
    await db.commit()

    logger.info(
        "display_settings_updated",
        user_id=str(current_user.id),
        display_mode=request.display_mode
    )

    return request


@router.get("/ocr", response_model=OCRSettings)
async def get_ocr_settings(
    current_user: User = Depends(get_current_active_user)
):
    """Nur OCR-Einstellungen abrufen."""
    settings = get_user_settings(current_user)
    return OCRSettings(**settings["ocr"])


@router.put("/ocr", response_model=OCRSettings)
async def update_ocr_settings(
    request: OCRSettings,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Nur OCR-Einstellungen aktualisieren."""
    valid_backends = ["auto", "deepseek", "got_ocr", "surya"]
    if request.default_backend not in valid_backends:
        raise HTTPException(
            status_code=400,
            detail=f"Ungültiges Backend. Erlaubt: {', '.join(valid_backends)}"
        )

    settings = get_user_settings(current_user)
    settings["ocr"] = request.model_dump()
    settings["last_updated"] = datetime.now(timezone.utc).isoformat()

    current_user.preferences = settings
    await db.commit()

    logger.info(
        "ocr_settings_updated",
        user_id=str(current_user.id),
        default_backend=request.default_backend
    )

    return request


@router.get("/notifications", response_model=NotificationSettings)
async def get_notification_settings(
    current_user: User = Depends(get_current_active_user)
):
    """Nur Benachrichtigungseinstellungen abrufen."""
    settings = get_user_settings(current_user)
    return NotificationSettings(**settings["notifications"])


@router.put("/notifications", response_model=NotificationSettings)
async def update_notification_settings(
    request: NotificationSettings,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Nur Benachrichtigungseinstellungen aktualisieren."""
    if request.email_digest not in ["none", "daily", "weekly"]:
        raise HTTPException(
            status_code=400,
            detail="Ungültige Digest-Frequenz. Erlaubt: none, daily, weekly"
        )

    settings = get_user_settings(current_user)
    settings["notifications"] = request.model_dump()
    settings["last_updated"] = datetime.now(timezone.utc).isoformat()

    current_user.preferences = settings
    await db.commit()

    logger.info(
        "notification_settings_updated",
        user_id=str(current_user.id)
    )

    return request


@router.get("/privacy", response_model=PrivacySettings)
async def get_privacy_settings(
    current_user: User = Depends(get_current_active_user)
):
    """Nur Datenschutzeinstellungen abrufen."""
    settings = get_user_settings(current_user)
    return PrivacySettings(**settings["privacy"])


@router.put("/privacy", response_model=PrivacySettings)
async def update_privacy_settings(
    request: PrivacySettings,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Nur Datenschutzeinstellungen aktualisieren."""
    settings = get_user_settings(current_user)
    settings["privacy"] = request.model_dump()
    settings["last_updated"] = datetime.now(timezone.utc).isoformat()

    current_user.preferences = settings
    await db.commit()

    logger.info(
        "privacy_settings_updated",
        user_id=str(current_user.id),
        share_analytics=request.share_analytics
    )

    return request


@router.post("/reset")
async def reset_settings(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Alle Einstellungen auf Standardwerte zurücksetzen."""
    reset_settings = dict(DEFAULT_SETTINGS)
    reset_settings["last_updated"] = datetime.now(timezone.utc).isoformat()

    current_user.preferences = reset_settings
    await db.commit()

    logger.info(
        "user_settings_reset",
        user_id=str(current_user.id)
    )

    return {
        "message": "Einstellungen wurden auf Standardwerte zurückgesetzt",
        "reset_at": reset_settings["last_updated"]
    }


# ==================== Widget Config Endpoints ====================

def get_widget_config(user: User) -> Dict[str, Any]:
    """Laedt Widget-Konfiguration aus User.preferences oder gibt Defaults zurueck."""
    config = dict(DEFAULT_WIDGET_CONFIG)

    if user.preferences and "widget_config" in user.preferences:
        user_config = user.preferences["widget_config"]
        if "widgets" in user_config and isinstance(user_config["widgets"], list):
            config["widgets"] = user_config["widgets"]
        if "active_preset" in user_config:
            config["active_preset"] = user_config["active_preset"]
        if "compact_mode" in user_config:
            config["compact_mode"] = user_config["compact_mode"]
        if "widget_settings" in user_config:
            config["widget_settings"] = user_config["widget_settings"]
        if "last_synced" in user_config:
            config["last_synced"] = user_config["last_synced"]

    return config


@router.get("/widget-config", response_model=WidgetConfigResponse)
async def get_widget_configuration(
    current_user: User = Depends(get_current_active_user)
):
    """Widget-Konfiguration abrufen.

    Gibt die gespeicherte Dashboard-Widget-Konfiguration zurueck:
    - Widget-Positionen (x, y, w, h)
    - Aktives Preset
    - Kompakter Modus
    - Individuelle Widget-Einstellungen
    """
    config = get_widget_config(current_user)

    return WidgetConfigResponse(
        widgets=[WidgetPosition(**w) for w in config["widgets"]],
        active_preset=config["active_preset"],
        compact_mode=config["compact_mode"],
        widget_settings={
            k: WidgetSettings(**v) for k, v in config.get("widget_settings", {}).items()
        },
        last_synced=datetime.fromisoformat(config["last_synced"]) if config["last_synced"] else None
    )


@router.put("/widget-config", response_model=WidgetConfigResponse)
async def update_widget_configuration(
    request: UpdateWidgetConfigRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Widget-Konfiguration aktualisieren.

    Speichert die Dashboard-Widget-Konfiguration serverseitig.
    Nur angegebene Felder werden aktualisiert.

    **Beispiel:**
    ```
    PUT /api/v1/settings/widget-config
    {
        "widgets": [
            {"id": "today", "type": "today", "x": 0, "y": 0, "w": 6, "h": 4}
        ],
        "compact_mode": true
    }
    ```
    """
    # Aktuelle Konfiguration laden
    current_config = get_widget_config(current_user)

    # Konfiguration aktualisieren
    if request.widgets is not None:
        # Validiere Widget-IDs auf Eindeutigkeit
        widget_ids = [w.id for w in request.widgets]
        if len(widget_ids) != len(set(widget_ids)):
            raise HTTPException(
                status_code=400,
                detail="Doppelte Widget-IDs gefunden. Jede ID muss eindeutig sein."
            )
        current_config["widgets"] = [w.model_dump() for w in request.widgets]

    if request.active_preset is not None:
        valid_presets = ["default", "finance-focus", "manager-overview", "admin-full", "minimal", None]
        if request.active_preset not in valid_presets and request.active_preset != "":
            # Erlaube auch leere Strings (wird zu None konvertiert)
            pass  # Custom presets erlaubt
        current_config["active_preset"] = request.active_preset if request.active_preset else None

    if request.compact_mode is not None:
        current_config["compact_mode"] = request.compact_mode

    if request.widget_settings is not None:
        # Merge widget settings
        if "widget_settings" not in current_config:
            current_config["widget_settings"] = {}
        for widget_id, settings in request.widget_settings.items():
            current_config["widget_settings"][widget_id] = settings.model_dump(exclude_none=True)

    # Timestamp aktualisieren
    current_config["last_synced"] = datetime.now(timezone.utc).isoformat()

    # In User.preferences speichern
    if current_user.preferences is None:
        current_user.preferences = {}

    current_user.preferences["widget_config"] = current_config
    await db.commit()

    logger.info(
        "widget_config_updated",
        user_id=str(current_user.id),
        widget_count=len(current_config["widgets"]),
        active_preset=current_config["active_preset"]
    )

    return WidgetConfigResponse(
        widgets=[WidgetPosition(**w) for w in current_config["widgets"]],
        active_preset=current_config["active_preset"],
        compact_mode=current_config["compact_mode"],
        widget_settings={
            k: WidgetSettings(**v) for k, v in current_config.get("widget_settings", {}).items()
        },
        last_synced=datetime.fromisoformat(current_config["last_synced"])
    )


@router.patch("/widget-config/widget/{widget_id}", response_model=WidgetSettings)
async def update_single_widget_settings(
    widget_id: str,
    settings: WidgetSettings,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Einstellungen fuer ein einzelnes Widget aktualisieren.

    Aktualisiert nur die individuellen Einstellungen eines Widgets
    (z.B. Zeitraum, Filter, Diagrammtyp).

    **Beispiel:**
    ```
    PATCH /api/v1/settings/widget-config/widget/cashflow-123
    {
        "time_range": "30d",
        "chart_type": "bar"
    }
    ```
    """
    # Aktuelle Konfiguration laden
    current_config = get_widget_config(current_user)

    # Pruefen ob Widget existiert
    widget_exists = any(w["id"] == widget_id for w in current_config["widgets"])
    if not widget_exists:
        raise HTTPException(
            status_code=404,
            detail=f"Widget mit ID '{widget_id}' nicht gefunden"
        )

    # Widget-Einstellungen aktualisieren
    if "widget_settings" not in current_config:
        current_config["widget_settings"] = {}

    # Merge mit existierenden Einstellungen
    existing = current_config["widget_settings"].get(widget_id, {})
    new_settings = settings.model_dump(exclude_none=True)
    existing.update(new_settings)
    current_config["widget_settings"][widget_id] = existing

    # Timestamp aktualisieren
    current_config["last_synced"] = datetime.now(timezone.utc).isoformat()

    # Speichern
    if current_user.preferences is None:
        current_user.preferences = {}
    current_user.preferences["widget_config"] = current_config
    await db.commit()

    logger.info(
        "widget_settings_updated",
        user_id=str(current_user.id),
        widget_id=widget_id
    )

    return WidgetSettings(**current_config["widget_settings"][widget_id])


@router.post("/widget-config/reset")
async def reset_widget_configuration(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Widget-Konfiguration auf Standardwerte zuruecksetzen."""
    reset_config = dict(DEFAULT_WIDGET_CONFIG)
    reset_config["last_synced"] = datetime.now(timezone.utc).isoformat()

    if current_user.preferences is None:
        current_user.preferences = {}

    current_user.preferences["widget_config"] = reset_config
    await db.commit()

    logger.info(
        "widget_config_reset",
        user_id=str(current_user.id)
    )

    return {
        "message": "Widget-Konfiguration wurde auf Standardwerte zurueckgesetzt",
        "reset_at": reset_config["last_synced"]
    }
