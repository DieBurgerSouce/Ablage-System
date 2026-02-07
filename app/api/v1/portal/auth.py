"""
Portal Authentication API.

Login, Logout, Account-Aktivierung fuer Kundenportal.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.services.portal import (
    PortalAuthService,
    PortalAuthError,
    PortalUserNotFoundError,
    PortalUserInactiveError,
    InvalidPortalCredentialsError,
    PortalAccountLockedError,
    get_portal_auth_service,
)
from app.db.models_portal import PortalUser

router = APIRouter(prefix="/auth", tags=["Portal-Auth"])


# === Pydantic Models ===

class PortalLoginRequest(BaseModel):
    """Login-Anfrage."""
    email: EmailStr
    password: str = Field(..., min_length=8)
    company_id: UUID


class PortalLoginResponse(BaseModel):
    """Login-Antwort."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    portal_user: dict


class PortalActivateRequest(BaseModel):
    """Account-Aktivierungs-Anfrage."""
    invitation_token: str
    password: str = Field(..., min_length=8)
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class PortalRefreshRequest(BaseModel):
    """Token-Refresh-Anfrage."""
    refresh_token: str


class PortalChangePasswordRequest(BaseModel):
    """Passwort-Aenderungs-Anfrage."""
    current_password: str
    new_password: str = Field(..., min_length=8)


class PortalSuccessResponse(BaseModel):
    """Erfolgs-Antwort."""
    success: bool
    message: Optional[str] = None


class PortalActivateResponse(BaseModel):
    """Account-Aktivierungs-Antwort."""
    success: bool
    message: str
    portal_user_id: str


class PortalUserPermissions(BaseModel):
    """Portal-Benutzer-Berechtigungen."""
    can_view_invoices: bool
    can_confirm_payments: bool
    can_submit_complaints: bool
    can_upload_documents: bool
    can_view_all_entity_data: bool


class PortalUserProfile(BaseModel):
    """Portal-Benutzer-Profil."""
    id: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    position: Optional[str] = None
    entity_id: str
    company_id: str
    status: str
    permissions: PortalUserPermissions
    last_login_at: Optional[str] = None


# === Dependencies ===

async def get_current_portal_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PortalUser:
    """
    Hole aktuellen Portal-Benutzer aus Authorization-Header.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentifizierung erforderlich",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header.split(" ", 1)[1]
    auth_service = get_portal_auth_service(db)

    portal_user = await auth_service.validate_session(token)
    if not portal_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungueltige oder abgelaufene Session",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return portal_user


# === Endpoints ===

@router.post("/login", response_model=PortalLoginResponse)
async def portal_login(
    request: Request,
    data: PortalLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Login ins Kundenportal.
    """
    auth_service = get_portal_auth_service(db)

    try:
        # Authentifiziere
        portal_user = await auth_service.authenticate(
            email=data.email,
            password=data.password,
            company_id=data.company_id,
        )

        # Erstelle Session
        access_token, refresh_token, session = await auth_service.create_session(
            portal_user_id=portal_user.id,
            user_agent=request.headers.get("User-Agent"),
            ip_address=request.client.host if request.client else None,
        )

        return PortalLoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=30 * 60,  # 30 Minuten
            portal_user={
                "id": str(portal_user.id),
                "email": portal_user.email,
                "first_name": portal_user.first_name,
                "last_name": portal_user.last_name,
                "entity_id": str(portal_user.entity_id),
                "company_id": str(portal_user.company_id),
                "permissions": {
                    "can_view_invoices": portal_user.can_view_invoices,
                    "can_confirm_payments": portal_user.can_confirm_payments,
                    "can_submit_complaints": portal_user.can_submit_complaints,
                    "can_upload_documents": portal_user.can_upload_documents,
                },
            },
        )

    except PortalUserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungueltige Anmeldedaten",
        )
    except PortalUserInactiveError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account ist nicht aktiv",
        )
    except PortalAccountLockedError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except InvalidPortalCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungueltige Anmeldedaten",
        )


@router.post("/activate", response_model=PortalActivateResponse)
async def portal_activate(
    data: PortalActivateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Aktiviere Portal-Account mit Einladungs-Token.
    """
    auth_service = get_portal_auth_service(db)

    try:
        portal_user = await auth_service.activate_account(
            invitation_token=data.invitation_token,
            password=data.password,
            first_name=data.first_name,
            last_name=data.last_name,
        )

        return PortalActivateResponse(
            success=True,
            message="Account erfolgreich aktiviert",
            portal_user_id=str(portal_user.id),
        )

    except PortalUserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungueltige oder abgelaufene Einladung",
        )
    except PortalAuthError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/refresh", response_model=PortalLoginResponse)
async def portal_refresh(
    request: Request,
    data: PortalRefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Erneuere Access-Token mit Refresh-Token.
    """
    auth_service = get_portal_auth_service(db)

    try:
        access_token, refresh_token, session = await auth_service.refresh_session(
            refresh_token=data.refresh_token,
        )

        # Lade Portal-User
        portal_user = await auth_service.get_portal_user_by_id(session.portal_user_id)
        if not portal_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Benutzer nicht gefunden",
            )

        return PortalLoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=30 * 60,
            portal_user={
                "id": str(portal_user.id),
                "email": portal_user.email,
                "first_name": portal_user.first_name,
                "last_name": portal_user.last_name,
                "entity_id": str(portal_user.entity_id),
                "company_id": str(portal_user.company_id),
                "permissions": {
                    "can_view_invoices": portal_user.can_view_invoices,
                    "can_confirm_payments": portal_user.can_confirm_payments,
                    "can_submit_complaints": portal_user.can_submit_complaints,
                    "can_upload_documents": portal_user.can_upload_documents,
                },
            },
        )

    except PortalAuthError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungueltige oder abgelaufene Session",
        )


@router.post("/logout", response_model=PortalSuccessResponse)
async def portal_logout(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Logout aus Kundenportal.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return PortalSuccessResponse(success=True)

    token = auth_header.split(" ", 1)[1]
    auth_service = get_portal_auth_service(db)

    await auth_service.revoke_session(token)

    return PortalSuccessResponse(success=True, message="Erfolgreich abgemeldet")


@router.post("/change-password", response_model=PortalSuccessResponse)
async def portal_change_password(
    data: PortalChangePasswordRequest,
    portal_user: PortalUser = Depends(get_current_portal_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Aendere Passwort.
    """
    auth_service = get_portal_auth_service(db)

    try:
        await auth_service.change_password(
            portal_user_id=portal_user.id,
            current_password=data.current_password,
            new_password=data.new_password,
        )

        return PortalSuccessResponse(
            success=True,
            message="Passwort erfolgreich geaendert. Bitte melden Sie sich erneut an.",
        )

    except InvalidPortalCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aktuelles Passwort ist falsch",
        )


@router.get("/me", response_model=PortalUserProfile)
async def portal_get_current_user(
    portal_user: PortalUser = Depends(get_current_portal_user),
):
    """
    Hole aktuellen Benutzer.
    """
    return PortalUserProfile(
        id=str(portal_user.id),
        email=portal_user.email,
        first_name=portal_user.first_name,
        last_name=portal_user.last_name,
        phone=portal_user.phone,
        position=portal_user.position,
        entity_id=str(portal_user.entity_id),
        company_id=str(portal_user.company_id),
        status=portal_user.status,
        permissions=PortalUserPermissions(
            can_view_invoices=portal_user.can_view_invoices,
            can_confirm_payments=portal_user.can_confirm_payments,
            can_submit_complaints=portal_user.can_submit_complaints,
            can_upload_documents=portal_user.can_upload_documents,
            can_view_all_entity_data=portal_user.can_view_all_entity_data,
        ),
        last_login_at=portal_user.last_login_at.isoformat() if portal_user.last_login_at else None,
    )
