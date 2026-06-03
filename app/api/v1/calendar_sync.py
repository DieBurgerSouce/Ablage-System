"""Calendar Sync API - iCalendar Export, Sync-Konfiguration und OAuth."""

from datetime import datetime
from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_active_user, get_user_company_id_dep
from app.db.models import User
from app.services.calendar.calendar_sync_service import CalendarSyncService, CalendarProvider

import structlog
from app.core.safe_errors import safe_error_detail
logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/calendar-sync", tags=["Calendar Sync"])


# =============================================================================
# Schemas - Konfiguration
# =============================================================================


class SyncConfigRequest(BaseModel):
    provider: str = Field(description="Kalender-Provider: ical_file, caldav, google_calendar, outlook")
    calendar_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None  # Only for initial setup, never returned
    sync_categories: Optional[List[str]] = None
    sync_interval_minutes: int = 60
    auto_sync_enabled: bool = False

class SyncConfigResponse(BaseModel):
    provider: str
    calendar_url: Optional[str] = None
    username: Optional[str] = None
    sync_categories: Optional[List[str]] = None
    sync_interval_minutes: int
    auto_sync_enabled: bool


# =============================================================================
# Schemas - OAuth
# =============================================================================


class OAuthAuthorizeRequest(BaseModel):
    provider: str = Field(description="OAuth-Provider: google oder outlook")
    redirect_uri: str = Field(description="Redirect-URI nach OAuth-Flow")


class OAuthAuthorizeResponse(BaseModel):
    auth_url: str
    state: str


class OAuthCallbackRequest(BaseModel):
    code: str = Field(description="Authorization Code aus OAuth-Callback")
    state: str = Field(description="CSRF State-Token")
    redirect_uri: str = Field(description="Redirect-URI (muss mit Authorize übereinstimmen)")


class OAuthStatusEntry(BaseModel):
    connected: bool
    expires_at: Optional[str] = None


class OAuthStatusResponse(BaseModel):
    google: OAuthStatusEntry
    outlook: OAuthStatusEntry


class OAuthRevokeRequest(BaseModel):
    provider: str = Field(description="Provider: google oder outlook")


# =============================================================================
# Schemas - Sync
# =============================================================================


class SyncResultResponse(BaseModel):
    success: bool
    created: int = 0
    updated: int = 0
    deleted: int = 0
    errors: List[str] = Field(default_factory=list)
    synced_at: Optional[str] = None


class SyncStatusResponse(BaseModel):
    last_synced_at: Optional[str] = None
    events_synced: int = 0
    provider: Optional[str] = None
    auto_sync_enabled: bool = False


# =============================================================================
# Schemas - Preview & Discovery
# =============================================================================


class CalendarEventPreview(BaseModel):
    uid: str
    title: str
    description: str
    start: str
    end: str
    category: Optional[str] = None


class CalendarInfoResponse(BaseModel):
    id: str
    name: str
    description: str
    primary: bool
    color: Optional[str] = None


class TestConnectionRequest(BaseModel):
    provider: str = Field(description="Provider: caldav, google_calendar, outlook")
    calendar_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


class TestConnectionResponse(BaseModel):
    success: bool
    message: str

@router.get("/export.ics")
async def export_ical(
    categories: Optional[str] = Query(None, description="Komma-getrennte Kategorien"),
    days_ahead: int = Query(90, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Exportiert Fristen als iCalendar (.ics) Datei."""
    service = CalendarSyncService(db)
    cat_list = categories.split(",") if categories else None

    ical_content = await service.generate_ical(
        company_id=company_id,
        user_id=current_user.id,
        categories=cat_list,
        days_ahead=days_ahead,
    )

    return Response(
        content=ical_content,
        media_type="text/calendar",
        headers={"Content-Disposition": "attachment; filename=ablage-fristen.ics"},
    )

@router.get("/config", response_model=SyncConfigResponse)
async def get_sync_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Liest Kalender-Sync-Konfiguration."""
    service = CalendarSyncService(db)
    config = await service.get_sync_config(company_id)
    if not config:
        return SyncConfigResponse(
            provider="ical_file", sync_interval_minutes=60, auto_sync_enabled=False
        )
    return SyncConfigResponse(
        provider=config.provider.value,
        calendar_url=config.calendar_url,
        username=config.username,
        sync_categories=config.sync_categories,
        sync_interval_minutes=config.sync_interval_minutes,
        auto_sync_enabled=config.auto_sync_enabled,
    )

@router.put("/config", response_model=SyncConfigResponse)
async def update_sync_config(
    body: SyncConfigRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Aktualisiert Kalender-Sync-Konfiguration."""
    from app.services.calendar.calendar_sync_service import SyncConfig
    config = SyncConfig(
        provider=CalendarProvider(body.provider),
        calendar_url=body.calendar_url,
        username=body.username,
        sync_categories=body.sync_categories,
        sync_interval_minutes=body.sync_interval_minutes,
        auto_sync_enabled=body.auto_sync_enabled,
    )
    service = CalendarSyncService(db)
    await service.save_sync_config(company_id, config)
    return SyncConfigResponse(
        provider=config.provider.value,
        calendar_url=config.calendar_url,
        username=config.username,
        sync_categories=config.sync_categories,
        sync_interval_minutes=config.sync_interval_minutes,
        auto_sync_enabled=config.auto_sync_enabled,
    )


# =============================================================================
# OAuth Endpoints
# =============================================================================


@router.post("/oauth/authorize", response_model=OAuthAuthorizeResponse)
async def oauth_authorize(
    body: OAuthAuthorizeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Startet den OAuth2-Flow für einen Kalender-Provider.

    Gibt eine Authorization-URL zurück, zu der der Benutzer
    weitergeleitet werden muss.
    """
    from app.services.calendar.oauth_service import get_calendar_oauth_service
    from app.core.config import settings

    if body.provider not in ("google", "outlook"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültiger Provider. Erlaubt: google, outlook",
        )

    oauth = get_calendar_oauth_service()

    client_id = ""
    if body.provider == "google":
        client_id = getattr(settings, "GOOGLE_CALENDAR_CLIENT_ID", "")
    elif body.provider == "outlook":
        client_id = getattr(settings, "OUTLOOK_CALENDAR_CLIENT_ID", "")

    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"OAuth für {body.provider} ist nicht konfiguriert.",
        )

    try:
        auth_url, state_token = oauth.get_authorization_url(
            provider=body.provider,
            client_id=client_id,
            redirect_uri=body.redirect_uri,
            company_id=company_id,
        )
        return OAuthAuthorizeResponse(auth_url=auth_url, state=state_token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Kalender"),
        )


@router.post("/oauth/callback")
async def oauth_callback(
    body: OAuthCallbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Verarbeitet den OAuth2-Callback und tauscht den Code gegen Tokens.

    Muss nach der Benutzer-Autorisierung aufgerufen werden.
    """
    from app.services.calendar.oauth_service import get_calendar_oauth_service
    from app.core.config import settings

    oauth = get_calendar_oauth_service()

    # State validieren (CSRF-Schutz)
    state_data = oauth.validate_state(body.state)
    if not state_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültiger oder abgelaufener State-Token.",
        )

    provider = state_data.get("provider", "")

    client_id = ""
    client_secret = ""
    if provider == "google":
        client_id = getattr(settings, "GOOGLE_CALENDAR_CLIENT_ID", "")
        client_secret = getattr(settings, "GOOGLE_CALENDAR_CLIENT_SECRET", "")
    elif provider == "outlook":
        client_id = getattr(settings, "OUTLOOK_CALENDAR_CLIENT_ID", "")
        client_secret = getattr(settings, "OUTLOOK_CALENDAR_CLIENT_SECRET", "")

    success = await oauth.exchange_code(
        db=db,
        company_id=company_id,
        provider=provider,
        code=body.code,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=body.redirect_uri,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Token-Austausch fehlgeschlagen. Bitte erneut versuchen.",
        )

    return {"message": f"OAuth-Verbindung zu {provider} erfolgreich hergestellt."}


@router.post("/oauth/revoke")
async def oauth_revoke(
    body: OAuthRevokeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Widerruft OAuth-Tokens und trennt die Kalender-Verbindung."""
    from app.services.calendar.oauth_service import get_calendar_oauth_service
    from app.core.config import settings

    if body.provider not in ("google", "outlook"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültiger Provider. Erlaubt: google, outlook",
        )

    oauth = get_calendar_oauth_service()

    client_id = ""
    client_secret = ""
    if body.provider == "google":
        client_id = getattr(settings, "GOOGLE_CALENDAR_CLIENT_ID", "")
        client_secret = getattr(settings, "GOOGLE_CALENDAR_CLIENT_SECRET", "")
    elif body.provider == "outlook":
        client_id = getattr(settings, "OUTLOOK_CALENDAR_CLIENT_ID", "")
        client_secret = getattr(settings, "OUTLOOK_CALENDAR_CLIENT_SECRET", "")

    await oauth.revoke_token(
        db=db,
        company_id=company_id,
        provider=body.provider,
        client_id=client_id,
        client_secret=client_secret,
    )

    return {"message": f"OAuth-Verbindung zu {body.provider} wurde getrennt."}


@router.get("/oauth/status", response_model=OAuthStatusResponse)
async def oauth_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Zeigt den OAuth-Verbindungsstatus für alle Provider."""
    from app.services.calendar.oauth_service import get_calendar_oauth_service

    oauth = get_calendar_oauth_service()

    google_status = OAuthStatusEntry(connected=False)
    outlook_status = OAuthStatusEntry(connected=False)

    # Google prüfen
    google_meta = await oauth.get_token_status(
        db, company_id, "google"
    )
    if google_meta:
        google_status = OAuthStatusEntry(
            connected=True,
            expires_at=google_meta.get("expires_at"),
        )

    # Outlook prüfen
    outlook_meta = await oauth.get_token_status(
        db, company_id, "outlook"
    )
    if outlook_meta:
        outlook_status = OAuthStatusEntry(
            connected=True,
            expires_at=outlook_meta.get("expires_at"),
        )

    return OAuthStatusResponse(google=google_status, outlook=outlook_status)


# =============================================================================
# Sync Endpoints
# =============================================================================


@router.post("/sync-now", response_model=SyncResultResponse)
async def sync_now(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Startet eine sofortige Kalender-Synchronisierung."""
    service = CalendarSyncService(db)
    sync_result = await service.sync_to_provider(db, company_id)

    return SyncResultResponse(
        success=len(sync_result.errors) == 0,
        created=sync_result.created,
        updated=sync_result.updated,
        deleted=sync_result.deleted,
        errors=sync_result.errors,
        synced_at=sync_result.synced_at,
    )


@router.get("/sync-status", response_model=SyncStatusResponse)
async def get_sync_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Zeigt den aktuellen Sync-Status."""
    service = CalendarSyncService(db)
    status_data = await service.get_sync_status(db, company_id)

    return SyncStatusResponse(
        last_synced_at=status_data.get("last_synced_at"),
        events_synced=status_data.get("events_synced", 0),
        provider=status_data.get("provider"),
        auto_sync_enabled=status_data.get("auto_sync_enabled", False),
    )


# =============================================================================
# Preview & Discovery Endpoints
# =============================================================================


@router.get("/preview", response_model=List[CalendarEventPreview])
async def preview_sync(
    categories: Optional[str] = Query(None, description="Komma-getrennte Kategorien"),
    days_ahead: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Vorschau der Ereignisse die synchronisiert werden wuerden."""
    from app.services.calendar.calendar_sync_executor import CalendarSyncExecutor

    cat_list = categories.split(",") if categories else None

    executor = CalendarSyncExecutor()
    events = await executor._load_current_events(
        db, company_id, cat_list, days_ahead
    )

    return [
        CalendarEventPreview(
            uid=e.uid,
            title=e.title,
            description=e.description,
            start=e.start.isoformat(),
            end=e.end.isoformat(),
        )
        for e in events
    ]


@router.get("/calendars", response_model=List[CalendarInfoResponse])
async def list_calendars(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Listet verfügbare Kalender vom konfigurierten Provider."""
    from app.services.calendar.calendar_sync_executor import CalendarSyncExecutor

    service = CalendarSyncService(db)
    config = await service.get_sync_config(company_id)

    if not config:
        return []

    executor = CalendarSyncExecutor()
    client = await executor._get_provider_client(
        db, company_id, config.provider.value
    )

    if client is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Verbindung zum Kalender-Provider fehlgeschlagen.",
        )

    try:
        calendars = await client.list_calendars()
        return [
            CalendarInfoResponse(
                id=c.id,
                name=c.name,
                description=c.description,
                primary=c.primary,
                color=c.color,
            )
            for c in calendars
        ]
    except Exception as e:
        logger.error("calendar_list_failed", **{"error_type": type(e).__name__})
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Kalender konnten nicht abgerufen werden.",
        )


@router.post("/test-connection", response_model=TestConnectionResponse)
async def test_connection(
    body: TestConnectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Testet die Verbindung zu einem Kalender-Provider."""
    service = CalendarSyncService(db)
    success, message = await service.test_provider_connection(
        db=db,
        company_id=company_id,
        provider=body.provider,
        calendar_url=body.calendar_url,
        username=body.username,
        password=body.password,
    )

    return TestConnectionResponse(success=success, message=message)
