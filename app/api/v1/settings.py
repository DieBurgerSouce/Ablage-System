"""User Settings API endpoints.

Provides REST API endpoints for:
- User preferences (display mode, language)
- OCR defaults
- Notification preferences
- Privacy settings
"""

from typing import Optional, Dict, Any
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
