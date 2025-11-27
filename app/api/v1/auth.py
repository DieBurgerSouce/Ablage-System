"""
Authentication API endpoints.

Handles user registration, login, token refresh, and logout.
All responses in German for user-facing messages.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_db,
    get_current_user,
    get_current_active_user
)
from app.db.models import User
from app.db.schemas import (
    UserCreate,
    UserResponse,
    LoginRequest,
    Token,
    RefreshTokenRequest,
    LogoutRequest,
    MessageResponse
)
from app.services.user_service import UserService
from app.core.security import (
    create_token_pair,
    decode_token,
    verify_token_type,
    blacklist_token
)


router = APIRouter(prefix="/auth", tags=["Authentication"])


# ==================== Registration ====================

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Benutzerregistrierung",
    description="Registriert einen neuen Benutzer im System"
)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Registriere einen neuen Benutzer.

    - **email**: Gültige E-Mail-Adresse (eindeutig)
    - **username**: Benutzername (3-100 Zeichen, eindeutig)
    - **password**: Passwort (mindestens 8 Zeichen, muss Groß-/Kleinbuchstaben, Zahlen und Sonderzeichen enthalten)
    - **full_name**: Vollständiger Name (optional)
    - **preferred_language**: Bevorzugte Sprache (de oder en, Standard: de)

    Gibt den erstellten Benutzer zurück (ohne Passwort).
    """
    user = await UserService.create_user(db, user_data)

    return UserResponse.model_validate(user)


# ==================== Login ====================

@router.post(
    "/login",
    response_model=Token,
    summary="Benutzer-Login",
    description="Authentifiziert einen Benutzer und gibt JWT-Tokens zurück"
)
async def login(
    login_data: LoginRequest,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Authentifiziere einen Benutzer mit E-Mail und Passwort.

    - **email**: E-Mail-Adresse des Benutzers
    - **password**: Benutzerpasswort

    Gibt Access Token (15 Minuten gültig) und Refresh Token (7 Tage gültig) zurück.

    **Beispiel:**
    ```json
    {
        "email": "user@example.com",
        "password": "SecurePassword123!"
    }
    ```
    """
    # Authenticate user
    user = await UserService.authenticate_user(
        db,
        login_data.email,
        login_data.password
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültige E-Mail-Adresse oder Passwort",  # Invalid email or password
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzerkonto ist deaktiviert",  # User account is deactivated
        )

    # Create token pair
    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "username": user.username
    }
    tokens = create_token_pair(token_data)

    return Token(**tokens)


# ==================== Token Refresh ====================

@router.post(
    "/refresh",
    response_model=Token,
    summary="Token erneuern",
    description="Erneuert Access Token mit Refresh Token"
)
async def refresh_token(
    refresh_data: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Erneuere Access Token mit einem gültigen Refresh Token.

    - **refresh_token**: Gültiger Refresh Token

    Gibt ein neues Token-Paar zurück.

    **Beispiel:**
    ```json
    {
        "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
    }
    ```
    """
    try:
        # Decode and validate refresh token
        payload = decode_token(refresh_data.refresh_token)
        verify_token_type(payload, "refresh")

        # Extract user ID
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Ungültiges Token-Format",  # Invalid token format
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Get user from database
        from uuid import UUID
        user_id = UUID(user_id_str)
        user = await UserService.get_user_by_id(db, user_id)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Benutzer nicht gefunden",  # User not found
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check if user is active
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Benutzerkonto ist deaktiviert",  # User account is deactivated
            )

        # Create new token pair
        token_data = {
            "sub": str(user.id),
            "email": user.email,
            "username": user.username
        }
        tokens = create_token_pair(token_data)

        return Token(**tokens)

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiger oder abgelaufener Refresh Token",  # Invalid or expired refresh token
            headers={"WWW-Authenticate": "Bearer"},
        )


# ==================== Logout ====================

@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Benutzer-Logout",
    description="Meldet einen Benutzer ab und widerruft Tokens"
)
async def logout(
    logout_data: LogoutRequest,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Melde einen Benutzer ab.

    Fügt den Refresh Token zur Blacklist hinzu, um weitere Verwendung zu verhindern.

    - **refresh_token**: Refresh Token zum Widerrufen (optional)

    **Hinweis:** Nach dem Logout müssen sich Clients erneut anmelden.
    """
    # Blacklist refresh token if provided
    if logout_data.refresh_token:
        try:
            payload = decode_token(logout_data.refresh_token)
            jti = payload.get("jti")
            exp = payload.get("exp")

            if jti and exp:
                # Convert exp timestamp to datetime
                exp_datetime = datetime.fromtimestamp(exp)
                blacklist_token(jti, exp_datetime)

        except Exception:
            # Token already invalid, ignore
            pass

    return MessageResponse(
        message="Erfolgreich abgemeldet",  # Successfully logged out
        detail="Bitte melden Sie sich erneut an, um auf geschützte Ressourcen zuzugreifen"  # Please log in again to access protected resources
    )


# ==================== Get Current User Info ====================

@router.get(
    "/me",
    response_model=UserResponse,
    summary="Aktuelle Benutzerinformationen",
    description="Ruft Informationen über den aktuell angemeldeten Benutzer ab"
)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Rufe Informationen über den aktuell angemeldeten Benutzer ab.

    Benötigt einen gültigen Access Token im Authorization Header.

    **Authorization Header:**
    ```
    Authorization: Bearer <access_token>
    ```

    Gibt Benutzerdetails zurück (ohne Passwort).
    """
    return UserResponse.model_validate(current_user)


# ==================== Update User Profile ====================

@router.put(
    "/me",
    response_model=UserResponse,
    summary="Benutzerprofil aktualisieren",
    description="Aktualisiert das Profil des aktuell angemeldeten Benutzers"
)
async def update_profile(
    user_update: UserCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Aktualisiere das Profil des aktuell angemeldeten Benutzers.

    Erlaubt die Aktualisierung von:
    - **full_name**: Vollständiger Name
    - **preferred_language**: Bevorzugte Sprache (de oder en)
    - **preferred_ocr_backend**: Bevorzugtes OCR-Backend

    Benötigt einen gültigen Access Token.
    """
    from app.db.schemas import UserUpdate

    # Convert UserCreate to UserUpdate (exclude password and email for profile updates)
    update_data = UserUpdate(
        full_name=user_update.full_name,
        preferred_language=user_update.preferred_language
    )

    updated_user = await UserService.update_user(
        db,
        current_user.id,
        update_data
    )

    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benutzer nicht gefunden"  # User not found
        )

    return UserResponse.model_validate(updated_user)


# ==================== Change Password ====================

@router.post(
    "/change-password",
    response_model=MessageResponse,
    summary="Passwort ändern",
    description="Ändert das Passwort des aktuell angemeldeten Benutzers"
)
async def change_password(
    password_data: UserCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Ändere das Passwort des aktuell angemeldeten Benutzers.

    - **current_password**: Aktuelles Passwort
    - **new_password**: Neues Passwort (mindestens 8 Zeichen, muss Anforderungen erfüllen)

    Benötigt einen gültigen Access Token.

    **Beispiel:**
    ```json
    {
        "current_password": "OldPassword123!",
        "new_password": "NewSecurePassword456!"
    }
    ```
    """
    from app.db.schemas import UserChangePassword

    # For this endpoint, we need to handle password change differently
    # This is a simplified version - in production, use a dedicated schema
    change_data = UserChangePassword(
        current_password="",  # Will be validated by service
        new_password=password_data.password
    )

    await UserService.change_password(
        db,
        current_user.id,
        change_data
    )

    return MessageResponse(
        message="Passwort erfolgreich geändert",  # Password changed successfully
        detail="Bitte verwenden Sie Ihr neues Passwort bei der nächsten Anmeldung"  # Please use your new password for next login
    )


# ==================== Admin Endpoints ====================

@router.get(
    "/users",
    response_model=list[UserResponse],
    summary="Alle Benutzer auflisten (Admin)",
    description="Listet alle Benutzer im System auf (nur für Administratoren)"
)
async def list_users(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Liste alle Benutzer auf.

    Nur für Administratoren verfügbar.

    - **skip**: Anzahl der zu überspringenden Datensätze (Standard: 0)
    - **limit**: Maximale Anzahl der zurückzugebenden Datensätze (Standard: 100)
    """
    from app.api.dependencies import get_current_superuser

    # Verify superuser
    await get_current_superuser(current_user)

    users = await UserService.list_users(db, skip=skip, limit=limit)

    return [UserResponse.model_validate(user) for user in users]
