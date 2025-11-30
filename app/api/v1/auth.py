"""
Authentication API endpoints.

Handles user registration, login, token refresh, and logout.
All responses in German for user-facing messages.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

logger = structlog.get_logger(__name__)

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
from app.core.totp import (
    check_totp_available,
    setup_2fa,
    verify_2fa_setup,
    verify_2fa_login,
    generate_backup_codes,
    TOTPNotAvailableError,
    TOTPAlreadyEnabledError,
    PYOTP_AVAILABLE,
)
from app.core.account_lockout import (
    check_account_lockout,
    record_failed_attempt,
    reset_failed_attempts,
    AccountLockoutStorageError,
)


router = APIRouter(prefix="/auth", tags=["Authentication"])


# ==================== CSRF Token ====================

@router.get(
    "/csrf-token",
    summary="CSRF-Token abrufen",
    description="Gibt ein CSRF-Token für geschützte Anfragen zurück"
)
async def get_csrf_token() -> dict:
    """
    Hole ein CSRF-Token für geschützte Anfragen.

    Das Token wird auch als Cookie gesetzt. Für state-changing Requests
    (POST, PUT, DELETE, PATCH) muss das Token im X-CSRF-Token Header
    oder im csrf_token Form-Feld gesendet werden.

    Bei Verwendung von Bearer-Token-Authentifizierung ist CSRF-Schutz
    nicht erforderlich, da der Authorization-Header nicht cross-origin
    gesetzt werden kann.

    Returns:
        Dict mit CSRF-Token und Header-Namen
    """
    from app.middleware.csrf import get_csrf_token_response
    return get_csrf_token_response()


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
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Authentifiziere einen Benutzer mit E-Mail und Passwort.

    - **email**: E-Mail-Adresse des Benutzers
    - **password**: Benutzerpasswort

    Gibt Access Token (15 Minuten gültig) und Refresh Token (7 Tage gültig) zurück.

    **Sicherheitshinweise:**
    - Nach 5 fehlgeschlagenen Versuchen wird das Konto vorübergehend gesperrt
    - Exponentielles Backoff: 1min → 5min → 15min → 1h

    **Beispiel:**
    ```json
    {
        "email": "user@example.com",
        "password": "SecurePassword123!"
    }
    ```
    """
    # Get client IP for lockout tracking
    client_ip = request.client.host if request.client else None

    # Check if account is locked due to too many failed attempts
    # fail_closed=None verwendet settings.RATE_LIMIT_FAIL_CLOSED_CRITICAL (default: True)
    try:
        is_locked, remaining_seconds, lockout_message = await check_account_lockout(
            ip=client_ip,
            username=login_data.email
        )
    except AccountLockoutStorageError as e:
        # Redis nicht verfügbar und fail_closed=True -> blockieren
        logger.error(
            "login_blocked_security_service_unavailable",
            ip=client_ip,
            email=login_data.email[:3] + "***" if login_data.email else None,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
            headers={"Retry-After": "60"},
        )

    if is_locked:
        logger.warning(
            "login_attempt_while_locked",
            email=login_data.email[:3] + "***",
            ip=client_ip,
            remaining_seconds=remaining_seconds,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=lockout_message,
            headers={
                "Retry-After": str(remaining_seconds),
                "X-RateLimit-Reset": str(remaining_seconds),
            },
        )

    # Authenticate user
    user = await UserService.authenticate_user(
        db,
        login_data.email,
        login_data.password
    )

    if not user:
        # Record failed attempt and potentially lock account
        try:
            attempts, is_now_locked, lockout_seconds = await record_failed_attempt(
                ip=client_ip,
                username=login_data.email
            )
        except AccountLockoutStorageError as e:
            # Redis nicht verfügbar und fail_closed=True -> blockieren
            logger.error(
                "login_blocked_cannot_record_failed_attempt",
                ip=client_ip,
                email=login_data.email[:3] + "***" if login_data.email else None,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(e),
                headers={"Retry-After": "60"},
            )

        if is_now_locked:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Zu viele fehlgeschlagene Anmeldeversuche. Konto für {lockout_seconds // 60} Minute(n) gesperrt.",
                headers={
                    "Retry-After": str(lockout_seconds),
                    "X-RateLimit-Reset": str(lockout_seconds),
                },
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültige E-Mail-Adresse oder Passwort",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzerkonto ist deaktiviert",
        )

    # Reset failed attempts on successful login
    await reset_failed_attempts(ip=client_ip, username=login_data.email)

    # Create token pair
    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "username": user.username
    }
    tokens = create_token_pair(token_data)

    logger.info(
        "login_successful",
        user_id=str(user.id),
        username=user.username,
    )

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
        # Decode and validate refresh token (async for Redis blacklist check)
        payload = await decode_token(refresh_data.refresh_token)
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
    except Exception as e:
        logger.warning("refresh_token_failed", error=str(e), error_type=type(e).__name__)
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
    # Blacklist refresh token if provided (async Redis-backed)
    if logout_data.refresh_token:
        try:
            payload = await decode_token(logout_data.refresh_token)
            jti = payload.get("jti")
            exp = payload.get("exp")

            if jti and exp:
                # Convert exp timestamp to datetime (with timezone)
                from datetime import timezone as tz
                exp_datetime = datetime.fromtimestamp(exp, tz=tz.utc)
                await blacklist_token(jti, exp_datetime)

        except Exception as e:
            # Token already invalid or blacklist failed - log but continue logout
            logger.debug("token_blacklist_skipped", error=str(e))

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


# ==================== Password Reset ====================

@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    summary="Passwort zurücksetzen anfordern",
    description="Sendet eine E-Mail mit Link zum Zurücksetzen des Passworts"
)
async def request_password_reset(
    reset_request: "PasswordResetRequest",
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Fordere einen Link zum Zurücksetzen des Passworts an.

    - **email**: E-Mail-Adresse des Kontos

    Eine E-Mail mit einem Reset-Link wird gesendet, falls das Konto existiert.

    **Sicherheitshinweise:**
    - Gibt immer die gleiche Nachricht zurück (Enumeration-Schutz)
    - Rate-Limiting: Max. 3 Anfragen pro Stunde pro E-Mail
    - Reset-Link ist 1 Stunde gültig
    """
    from app.db.schemas import PasswordResetRequest
    from app.services.password_reset_service import get_password_reset_service
    from app.services.notification_service import NotificationService

    reset_service = get_password_reset_service()

    # Optional: NotificationService erstellen falls SMTP konfiguriert
    notification_service = None
    try:
        notification_service = NotificationService()
    except Exception as e:
        logger.warning("notification_service_unavailable", error=str(e))

    success, message = await reset_service.request_password_reset(
        db=db,
        email=reset_request.email,
        notification_service=notification_service,
    )

    logger.info(
        "password_reset_requested",
        email=reset_request.email[:3] + "***",
        ip=request.client.host if request.client else None,
    )

    return MessageResponse(
        message=message,
        detail="Überprüfen Sie Ihren Posteingang (und Spam-Ordner)"
    )


@router.post(
    "/validate-reset-token",
    response_model="PasswordResetResponse",
    summary="Reset-Token validieren",
    description="Prüft ob ein Reset-Token gültig ist"
)
async def validate_reset_token(
    validate_request: "PasswordResetValidate",
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Validiere einen Password-Reset-Token.

    - **token**: Der Reset-Token aus der E-Mail

    Nützlich für Frontends um zu prüfen, ob der Token noch gültig ist,
    bevor das Formular zum Setzen eines neuen Passworts angezeigt wird.
    """
    from app.db.schemas import PasswordResetValidate, PasswordResetResponse
    from app.services.password_reset_service import get_password_reset_service

    reset_service = get_password_reset_service()

    is_valid, user, message = await reset_service.validate_reset_token(
        db=db,
        token=validate_request.token,
    )

    return PasswordResetResponse(
        success=is_valid,
        message=message if is_valid else "Token ungültig oder abgelaufen"
    )


@router.post(
    "/reset-password",
    response_model="PasswordResetResponse",
    summary="Passwort zurücksetzen",
    description="Setzt das Passwort mit einem gültigen Reset-Token zurück"
)
async def reset_password(
    reset_data: "PasswordResetConfirm",
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Setze das Passwort mit einem gültigen Reset-Token zurück.

    - **token**: Der Reset-Token aus der E-Mail
    - **new_password**: Das neue Passwort (mindestens 8 Zeichen)

    **Passwortanforderungen:**
    - Mindestens 8 Zeichen
    - Mindestens ein Großbuchstabe
    - Mindestens ein Kleinbuchstabe
    - Mindestens eine Zahl
    - Mindestens ein Sonderzeichen

    Nach erfolgreichem Reset werden alle anderen Reset-Tokens invalidiert.
    """
    from app.db.schemas import PasswordResetConfirm, PasswordResetResponse
    from app.services.password_reset_service import get_password_reset_service

    reset_service = get_password_reset_service()

    success, message = await reset_service.reset_password(
        db=db,
        token=reset_data.token,
        new_password=reset_data.new_password,
    )

    if success:
        logger.info(
            "password_reset_completed",
            ip=request.client.host if request.client else None,
        )
    else:
        logger.warning(
            "password_reset_failed",
            ip=request.client.host if request.client else None,
            reason=message,
        )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )

    return PasswordResetResponse(
        success=True,
        message="Passwort erfolgreich zurückgesetzt. Sie können sich jetzt anmelden."
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


# ==================== Two-Factor Authentication (2FA) ====================

@router.get(
    "/2fa/status",
    summary="2FA-Status abfragen",
    description="Gibt den aktuellen 2FA-Status des Benutzers zurück"
)
async def get_2fa_status(
    current_user: User = Depends(get_current_active_user)
) -> dict:
    """
    Gibt den aktuellen 2FA-Status des Benutzers zurück.

    Returns:
        - **enabled**: Ob 2FA aktiviert ist
        - **available**: Ob 2FA im System verfügbar ist (pyotp installiert)
        - **setup_at**: Wann 2FA aktiviert wurde (falls aktiviert)
        - **backup_codes_remaining**: Anzahl verbleibender Backup-Codes
    """
    backup_codes_count = 0
    if current_user.totp_backup_codes:
        backup_codes_count = len(current_user.totp_backup_codes)

    return {
        "enabled": current_user.totp_enabled,
        "available": PYOTP_AVAILABLE,
        "setup_at": current_user.totp_setup_at.isoformat() if current_user.totp_setup_at else None,
        "backup_codes_remaining": backup_codes_count,
    }


@router.post(
    "/2fa/setup",
    summary="2FA-Setup initiieren",
    description="Startet den 2FA-Setup-Prozess und gibt QR-Code zurück"
)
async def initiate_2fa_setup(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Initiiert den 2FA-Setup-Prozess.

    Generiert:
    - TOTP-Secret
    - QR-Code für Authenticator-App
    - Provisioning-URI für manuelle Eingabe
    - 8 Backup-Codes für Notfälle

    **WICHTIG:** Speichern Sie die Backup-Codes sicher!
    Diese werden nur einmal angezeigt.

    Nach dem Setup muss der Benutzer einen Code eingeben
    um die Aktivierung zu bestätigen (/2fa/verify).
    """
    if not PYOTP_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="2FA ist nicht verfügbar. pyotp ist nicht installiert."
        )

    if current_user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA ist bereits aktiviert. Deaktivieren Sie zuerst die bestehende 2FA."
        )

    try:
        result = await setup_2fa(
            user_id=str(current_user.id),
            email=current_user.email,
            db_session=db
        )

        # Secret temporär im User speichern (noch nicht aktiviert!)
        current_user.totp_secret = result["secret"]
        current_user.totp_backup_codes = result["hashed_backup_codes"]
        await db.commit()

        logger.info(
            "2fa_setup_initiated",
            user_id=str(current_user.id)[:8] + "...",
        )

        return {
            "message": "2FA-Setup initiiert. Scannen Sie den QR-Code mit Ihrer Authenticator-App.",
            "qr_code": result["qr_code"],
            "provisioning_uri": result["provisioning_uri"],
            "backup_codes": result["backup_codes"],
            "warning": "WICHTIG: Speichern Sie die Backup-Codes sicher! Sie werden nur einmal angezeigt."
        }

    except Exception as e:
        logger.error("2fa_setup_failed", error=str(e), user_id=str(current_user.id)[:8])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="2FA-Setup fehlgeschlagen. Bitte versuchen Sie es später erneut."
        )


@router.post(
    "/2fa/verify",
    summary="2FA-Setup bestätigen",
    description="Bestätigt das 2FA-Setup mit einem Code aus der Authenticator-App"
)
async def verify_2fa_setup_endpoint(
    code: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Bestätigt das 2FA-Setup mit einem Code aus der Authenticator-App.

    - **code**: 6-stelliger Code aus der Authenticator-App

    Bei Erfolg wird 2FA für den Benutzer aktiviert.
    """
    if not current_user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kein 2FA-Setup aktiv. Starten Sie zuerst mit /2fa/setup."
        )

    if current_user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA ist bereits aktiviert."
        )

    # Verifiziere den Code
    if not verify_2fa_setup(current_user.totp_secret, code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültiger Code. Stellen Sie sicher, dass die Zeit auf Ihrem Gerät korrekt ist."
        )

    # 2FA aktivieren
    from datetime import datetime, timezone as tz
    current_user.totp_enabled = True
    current_user.totp_setup_at = datetime.now(tz.utc)
    await db.commit()

    logger.info(
        "2fa_enabled",
        user_id=str(current_user.id)[:8] + "...",
    )

    return {
        "message": "2FA erfolgreich aktiviert!",
        "enabled": True,
        "setup_at": current_user.totp_setup_at.isoformat(),
    }


@router.post(
    "/2fa/disable",
    summary="2FA deaktivieren",
    description="Deaktiviert 2FA für den aktuellen Benutzer"
)
async def disable_2fa(
    code: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Deaktiviert 2FA für den aktuellen Benutzer.

    - **code**: 6-stelliger Code aus der Authenticator-App ODER Backup-Code

    **Sicherheitshinweis:** Diese Aktion kann nicht rückgängig gemacht werden.
    Sie müssen 2FA erneut einrichten, wenn Sie es wieder aktivieren möchten.
    """
    if not current_user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA ist nicht aktiviert."
        )

    # Verifiziere den Code (TOTP oder Backup)
    is_valid, used_backup, backup_index = verify_2fa_login(
        secret=current_user.totp_secret,
        code=code,
        backup_codes=current_user.totp_backup_codes
    )

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültiger Code."
        )

    # 2FA deaktivieren
    current_user.totp_enabled = False
    current_user.totp_secret = None
    current_user.totp_backup_codes = None
    current_user.totp_setup_at = None
    await db.commit()

    logger.info(
        "2fa_disabled",
        user_id=str(current_user.id)[:8] + "...",
        used_backup=used_backup,
    )

    return {
        "message": "2FA erfolgreich deaktiviert.",
        "enabled": False,
    }


@router.post(
    "/2fa/regenerate-backup-codes",
    summary="Backup-Codes neu generieren",
    description="Generiert neue Backup-Codes und invalidiert die alten"
)
async def regenerate_backup_codes(
    code: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Generiert neue Backup-Codes und invalidiert die alten.

    - **code**: 6-stelliger Code aus der Authenticator-App

    **WICHTIG:** Die alten Backup-Codes werden ungültig!
    Speichern Sie die neuen Codes sicher.
    """
    if not current_user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA ist nicht aktiviert."
        )

    # Verifiziere mit TOTP-Code (nicht Backup-Code für diese Operation)
    from app.core.totp import verify_totp_code
    if not verify_totp_code(current_user.totp_secret, code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültiger Code."
        )

    # Neue Backup-Codes generieren
    plain_codes, hashed_codes = generate_backup_codes()

    current_user.totp_backup_codes = hashed_codes
    await db.commit()

    logger.info(
        "2fa_backup_codes_regenerated",
        user_id=str(current_user.id)[:8] + "...",
    )

    return {
        "message": "Neue Backup-Codes generiert.",
        "backup_codes": plain_codes,
        "warning": "WICHTIG: Speichern Sie die Backup-Codes sicher! Die alten Codes sind ungültig."
    }
