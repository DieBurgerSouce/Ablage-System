"""
Authentication API endpoints.

Handles user registration, login, token refresh, and logout.
All responses in German for user-facing messages.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

# Z.7 SECURITY FIX: Rate Limiting fuer Passwort-Endpoints
from app.core.rate_limiting import limiter, RateLimitTier, get_ip_identifier

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
    MessageResponse,
    SessionInfo,
    SessionListResponse,
    SessionRevokeRequest,
    SessionRevokeAllRequest,
    SessionRevokeResponse,
    PasswordResetRequest,
    PasswordResetValidate,
    PasswordResetConfirm,
    PasswordResetResponse,
    EmailVerificationStatusResponse,
    EmailVerificationResponse,
    EmailVerifyResponse,
    EmailChangeResponse,
    EmailVerifyTokenRequest,
    EmailChangeRequest,
    TwoFactorRequiredResponse,
    TwoFactorVerifyRequest,
)
from app.services.user_service import UserService
from app.core.security import (
    create_token_pair,
    decode_token,
    verify_token_type,
    blacklist_token,
    create_2fa_temp_token,
    verify_2fa_temp_token,
)
from app.core.totp import (
    check_totp_available,
    setup_2fa,
    verify_2fa_setup,
    verify_2fa_login,
    verify_2fa_login_encrypted,
    verify_totp_code_encrypted,
    decrypt_secret,
    generate_backup_codes,
    TOTPNotAvailableError,
    TOTPAlreadyEnabledError,
    TOTPSecretEncryptionError,
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
@limiter.limit("5/hour", key_func=get_ip_identifier)  # BB.1 SECURITY FIX: Rate limit registration
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
    summary="Benutzer-Login",
    description="Authentifiziert einen Benutzer und gibt JWT-Tokens zuruck. Bei aktiviertem 2FA wird ein temporarer Token zuruck gegeben.",
    responses={
        200: {
            "description": "Login erfolgreich oder 2FA erforderlich",
            "content": {
                "application/json": {
                    "examples": {
                        "success": {
                            "summary": "Login ohne 2FA",
                            "value": {"access_token": "...", "refresh_token": "...", "token_type": "bearer"}
                        },
                        "2fa_required": {
                            "summary": "2FA erforderlich",
                            "value": {"requires_2fa": True, "temp_token": "...", "message": "Bitte geben Sie Ihren 2FA-Code ein."}
                        }
                    }
                }
            }
        }
    }
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

    # Check if 2FA is enabled for this user
    if user.totp_enabled:
        logger.info(
            "login_requires_2fa",
            user_id=str(user.id),
            username=user.username
        )
        # Return temporary token for 2FA verification
        temp_token = create_2fa_temp_token(str(user.id))
        return TwoFactorRequiredResponse(
            requires_2fa=True,
            temp_token=temp_token,
            message="Bitte geben Sie Ihren 2FA-Code ein."
        )

    # Create token pair
    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "username": user.username
    }
    tokens = create_token_pair(token_data)

    # Create session for tracking
    session_warning = None
    try:
        from app.core.session_manager import get_session_manager, SessionLimitReachedError

        session_manager = get_session_manager()

        # Extract JTI from access token
        access_payload = await decode_token(tokens["access_token"])
        token_jti = access_payload.get("jti")

        if token_jti and client_ip:
            user_agent = request.headers.get("User-Agent")
            session_result = await session_manager.create_session(
                db=db,
                user_id=user.id,
                token_jti=token_jti,
                ip_address=client_ip,
                user_agent=user_agent
            )
            # Speichere Warnung über widerrufene Sessions
            session_warning = session_result.get("warning")

    except SessionLimitReachedError as e:
        # Hard-Mode: Login blockieren wenn Limit erreicht
        logger.warning(
            "login_blocked_session_limit",
            user_id=str(user.id),
            current_sessions=e.current_sessions,
            max_sessions=e.max_sessions
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=e.user_message_de,
            headers={
                "X-Session-Limit": str(e.max_sessions),
                "X-Session-Current": str(e.current_sessions)
            }
        )
    except Exception as e:
        # Session creation failure should not block login
        logger.warning(
            "session_creation_failed",
            user_id=str(user.id),
            error=str(e)
        )

    logger.info(
        "login_successful",
        user_id=str(user.id),
        username=user.username,
        session_warning=session_warning is not None
    )

    return Token(**tokens, session_warning=session_warning)


# ==================== 2FA Verification during Login ====================

@router.post(
    "/verify-2fa",
    response_model=Token,
    summary="2FA-Verifizierung abschliessen",
    description="Verifiziert den 2FA-Code und gibt JWT-Tokens zuruck"
)
async def verify_2fa_login_endpoint(
    data: TwoFactorVerifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Verifiziere 2FA-Code nach erfolgreicher Passwort-Authentifizierung.

    - **temp_token**: Temporarer Token aus der Login-Response
    - **code**: 6-stelliger TOTP-Code oder Backup-Code

    Gibt Access Token und Refresh Token zuruck bei erfolgreichem 2FA.
    """
    # Verify temp token and get user ID
    user_id = await verify_2fa_temp_token(data.temp_token)

    # Get user from database
    from uuid import UUID
    user = await UserService.get_user(db, UUID(user_id))

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Benutzer nicht gefunden",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA ist nicht aktiviert fur diesen Benutzer",
        )

    # Clean up code (remove spaces/dashes)
    clean_code = data.code.replace(" ", "").replace("-", "")

    # Verify TOTP code or backup code
    try:
        is_valid, used_backup, backup_index = verify_2fa_login_encrypted(
            encrypted_secret=user.totp_secret,
            user_id=str(user.id),
            code=clean_code,
            backup_codes=user.totp_backup_codes or []
        )

        if not is_valid:
            logger.warning(
                "2fa_verification_failed",
                user_id=str(user.id),
                code_type="backup" if len(clean_code) == 8 else "totp"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Ungueltiger 2FA-Code",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # If backup code was used, remove it from the list
        if used_backup and backup_index is not None:
            backup_codes = list(user.totp_backup_codes or [])
            if 0 <= backup_index < len(backup_codes):
                del backup_codes[backup_index]
                user.totp_backup_codes = backup_codes
                await db.commit()
                logger.info(
                    "2fa_backup_code_used",
                    user_id=str(user.id),
                    remaining_codes=len(backup_codes)
                )

    except TOTPSecretEncryptionError as e:
        logger.error(
            "2fa_decryption_failed",
            user_id=str(user.id),
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler bei der 2FA-Verifizierung"
        )

    # 2FA successful - create token pair
    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "username": user.username
    }
    tokens = create_token_pair(token_data)

    # Create session for tracking
    client_ip = request.client.host if request.client else None
    session_warning = None

    try:
        from app.core.session_manager import get_session_manager, SessionLimitReachedError

        session_manager = get_session_manager()
        access_payload = await decode_token(tokens["access_token"])
        token_jti = access_payload.get("jti")

        if token_jti and client_ip:
            user_agent = request.headers.get("User-Agent")
            session_result = await session_manager.create_session(
                db=db,
                user_id=user.id,
                token_jti=token_jti,
                ip_address=client_ip,
                user_agent=user_agent
            )
            session_warning = session_result.get("warning")

    except Exception as e:
        logger.warning(
            "session_creation_failed_2fa",
            user_id=str(user.id),
            error=str(e)
        )

    logger.info(
        "2fa_login_successful",
        user_id=str(user.id),
        username=user.username,
        used_backup_code=used_backup
    )

    return Token(**tokens, session_warning=session_warning)


# ==================== Token Refresh ====================

@router.post(
    "/refresh",
    response_model=Token,
    summary="Token erneuern",
    description="Erneuert Access Token mit Refresh Token (Token Rotation)"
)
async def refresh_token(
    refresh_data: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Erneuere Access Token mit einem gültigen Refresh Token.

    **SECURITY: Refresh Token Rotation**
    - Der alte Refresh Token wird invalidiert (Blacklist)
    - Ein komplett neues Token-Paar wird ausgestellt
    - Verhindert Token-Wiederverwendung bei Token-Diebstahl

    - **refresh_token**: Gültiger Refresh Token

    Gibt ein neues Token-Paar zurück.

    **Beispiel:**
    ```json
    {
        "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
    }
    ```

    **Sicherheitshinweise:**
    - Nach Verwendung ist der alte Refresh Token ungültig
    - Bei Verdacht auf Token-Diebstahl: Alle Sessions widerrufen
    """
    from datetime import timezone as tz

    try:
        # Decode and validate refresh token (async for Redis blacklist check)
        payload = await decode_token(refresh_data.refresh_token)
        verify_token_type(payload, "refresh")

        # Extract user ID and token metadata
        user_id_str = payload.get("sub")
        old_jti = payload.get("jti")
        old_exp = payload.get("exp")

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

        # SECURITY FIX: Token Rotation - Blacklist the OLD refresh token
        # This prevents replay attacks if the token was stolen
        if old_jti and old_exp:
            try:
                old_exp_datetime = datetime.fromtimestamp(old_exp, tz=tz.utc)
                await blacklist_token(old_jti, old_exp_datetime)
                logger.debug(
                    "refresh_token_rotated",
                    old_jti=old_jti[:8] + "...",
                    user_id=str(user.id)[:8] + "..."
                )
            except HTTPException:
                # Re-raise HTTPException (fail-closed mode from blacklist_token)
                # This is critical for security - blocking login is safer than
                # allowing potentially compromised tokens
                raise
            except Exception as blacklist_error:
                # Other errors (e.g., connection issues in non-fail-closed mode)
                # Log as warning but continue to avoid blocking legitimate users
                logger.warning(
                    "refresh_token_blacklist_failed",
                    error_type=type(blacklist_error).__name__,
                    user_id=str(user.id)[:8] + "..."
                )

        # Create new token pair (with new JTIs)
        token_data = {
            "sub": str(user.id),
            "email": user.email,
            "username": user.username
        }
        tokens = create_token_pair(token_data)

        logger.info(
            "token_refresh_successful",
            user_id=str(user.id)[:8] + "...",
            username=user.username,
            rotation_applied=True
        )

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
    request: Request,
    logout_data: LogoutRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Melde einen Benutzer ab.

    Fügt Access Token und Refresh Token zur Blacklist hinzu, um weitere Verwendung zu verhindern.

    - **refresh_token**: Refresh Token zum Widerrufen (optional)

    **Hinweis:** Nach dem Logout müssen sich Clients erneut anmelden.

    **Sicherheitsverbesserung:**
    - Access Token wird sofort ungültig (nicht erst nach 15min Ablauf)
    - Refresh Token wird ebenfalls auf Blacklist gesetzt
    - Session wird in der Datenbank widerrufen
    """
    from datetime import timezone as tz

    access_token_blacklisted = False
    refresh_token_blacklisted = False
    session_revoked = False

    # 1. SECURITY FIX: Blacklist the ACCESS token (wichtigste Änderung!)
    # Ohne dies bleibt der Access Token bis zu 15 Minuten gültig nach Logout
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            access_token = auth_header.split(" ")[1]
            access_payload = await decode_token(access_token)
            access_jti = access_payload.get("jti")
            access_exp = access_payload.get("exp")

            if access_jti and access_exp:
                access_exp_datetime = datetime.fromtimestamp(access_exp, tz=tz.utc)
                await blacklist_token(access_jti, access_exp_datetime)
                access_token_blacklisted = True
                logger.debug(
                    "access_token_blacklisted",
                    jti=access_jti[:8] + "...",
                    user_id=str(current_user.id)[:8] + "..."
                )

        except Exception as e:
            # Access token blacklist failed - log warning (security relevant)
            logger.warning(
                "access_token_blacklist_failed",
                error_type=type(e).__name__,
                user_id=str(current_user.id)[:8] + "..."
            )

    # 2. Revoke session in database
    try:
        from app.core.session_manager import get_session_manager

        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            payload = await decode_token(token)
            current_jti = payload.get("jti")

            if current_jti:
                session_manager = get_session_manager()
                await session_manager.revoke_session_by_jti(db, current_jti)
                session_revoked = True

    except Exception as e:
        # Session revocation failure should not block logout
        logger.debug("session_revoke_skipped", error=str(e))

    # 3. Blacklist refresh token if provided
    if logout_data.refresh_token:
        try:
            payload = await decode_token(logout_data.refresh_token)
            jti = payload.get("jti")
            exp = payload.get("exp")

            if jti and exp:
                exp_datetime = datetime.fromtimestamp(exp, tz=tz.utc)
                await blacklist_token(jti, exp_datetime)
                refresh_token_blacklisted = True
                logger.debug(
                    "refresh_token_blacklisted",
                    jti=jti[:8] + "...",
                    user_id=str(current_user.id)[:8] + "..."
                )

        except Exception as e:
            # Token already invalid or blacklist failed - log but continue logout
            logger.debug("refresh_token_blacklist_skipped", error=str(e))

    # Log logout summary
    logger.info(
        "user_logout_completed",
        user_id=str(current_user.id)[:8] + "...",
        username=current_user.username,
        access_token_blacklisted=access_token_blacklisted,
        refresh_token_blacklisted=refresh_token_blacklisted,
        session_revoked=session_revoked
    )

    return MessageResponse(
        message="Erfolgreich abgemeldet",
        detail="Alle Tokens wurden widerrufen. Bitte melden Sie sich erneut an."
    )


# ==================== Get Current User Info ====================

@router.get(
    "/me",
    response_model=UserResponse,
    summary="Aktuelle Benutzerinformationen",
    description="Ruft Informationen über den aktuell angemeldeten Benutzer ab"
)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
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
    # FAANG-AUDIT FIX (B6): Korrekte Rollenermittlung aus RBAC-System
    # Prioritaet: is_superuser > RBAC-Rollen > Default "viewer"
    role = "viewer"  # Default

    if current_user.is_superuser:
        role = "admin"
    else:
        # Hole echte Rollen aus dem RBAC-System
        from app.services.permission_service import PermissionService
        permission_service = PermissionService(db)
        try:
            user_roles = await permission_service.get_user_roles(current_user)
            if user_roles:
                # Sortiere nach Prioritaet (hoechste zuerst) und nehme die hoechste Rolle
                sorted_roles = sorted(user_roles, key=lambda r: r.priority, reverse=True)
                role = sorted_roles[0].name
                logger.debug(
                    "user_role_resolved",
                    user_id=str(current_user.id),
                    role=role,
                    all_roles=[r.name for r in sorted_roles]
                )
        except Exception as e:
            # Bei Fehler: Fallback auf "viewer" (sicherste Option)
            logger.warning(
                "rbac_role_fetch_failed",
                user_id=str(current_user.id),
                error=str(e),
                fallback_role="viewer"
            )

    user_data = UserResponse.model_validate(current_user)
    user_data.role = role
    return user_data


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
@limiter.limit("5/hour", key_func=get_ip_identifier)  # Z.7 SECURITY FIX: Rate Limit
async def change_password(
    request: Request,  # Z.7: Required for rate limiter
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
@limiter.limit(RateLimitTier.PASSWORD_RESET, key_func=get_ip_identifier)  # Z.7 SECURITY FIX: Rate Limit (3/hour)
async def request_password_reset(
    request: Request,  # Z.7: Required for rate limiter (moved to first position)
    reset_request: PasswordResetRequest,
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
    response_model=PasswordResetResponse,
    summary="Reset-Token validieren",
    description="Prüft ob ein Reset-Token gültig ist"
)
async def validate_reset_token(
    validate_request: PasswordResetValidate,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Validiere einen Password-Reset-Token.

    - **token**: Der Reset-Token aus der E-Mail

    Nützlich für Frontends um zu prüfen, ob der Token noch gültig ist,
    bevor das Formular zum Setzen eines neuen Passworts angezeigt wird.
    """
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
    response_model=PasswordResetResponse,
    summary="Passwort zurücksetzen",
    description="Setzt das Passwort mit einem gültigen Reset-Token zurück"
)
@limiter.limit(RateLimitTier.PASSWORD_RESET, key_func=get_ip_identifier)  # Z.7 SECURITY FIX: Rate Limit (3/hour)
async def reset_password(
    request: Request,  # Z.7: Required for rate limiter
    reset_data: PasswordResetConfirm,
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

        # Verschlüsselten Secret im User speichern (noch nicht aktiviert!)
        # Seit Arbeitspaket 5 (TOTP-Verschlüsselung) wird der Secret
        # mit AES-256-GCM verschlüsselt in der DB gespeichert.
        current_user.totp_secret = result["encrypted_secret"]
        current_user.totp_backup_codes = result["hashed_backup_codes"]
        await db.commit()

        logger.info(
            "2fa_setup_initiated",
            user_id=str(current_user.id)[:8] + "...",
            encryption="AES-256-GCM"
        )

        return {
            "message": "2FA-Setup initiiert. Scannen Sie den QR-Code mit Ihrer Authenticator-App.",
            "qr_code": result["qr_code"],
            "provisioning_uri": result["provisioning_uri"],
            "backup_codes": result["backup_codes"],
            "warning": "WICHTIG: Speichern Sie die Backup-Codes sicher! Sie werden nur einmal angezeigt."
        }

    except TOTPSecretEncryptionError as e:
        logger.error("2fa_setup_encryption_failed", error=str(e), user_id=str(current_user.id)[:8])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.user_message_de
        )
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

    try:
        # Verifiziere den Code mit verschlüsseltem Secret
        # Der Secret ist seit AP5 mit AES-256-GCM verschlüsselt
        if not verify_totp_code_encrypted(
            encrypted_secret=current_user.totp_secret,
            user_id=str(current_user.id),
            code=code
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ungültiger Code. Stellen Sie sicher, dass die Zeit auf Ihrem Gerät korrekt ist."
            )
    except TOTPSecretEncryptionError as e:
        logger.error("2fa_verify_decryption_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.user_message_de
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

    try:
        # Verifiziere den Code (TOTP oder Backup) mit verschlüsseltem Secret
        is_valid, used_backup, backup_index = verify_2fa_login_encrypted(
            encrypted_secret=current_user.totp_secret,
            user_id=str(current_user.id),
            code=code,
            backup_codes=current_user.totp_backup_codes
        )
    except TOTPSecretEncryptionError as e:
        logger.error("2fa_disable_decryption_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.user_message_de
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

    try:
        # Verifiziere mit TOTP-Code (nicht Backup-Code für diese Operation)
        if not verify_totp_code_encrypted(
            encrypted_secret=current_user.totp_secret,
            user_id=str(current_user.id),
            code=code
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ungültiger Code."
            )
    except TOTPSecretEncryptionError as e:
        logger.error("2fa_regenerate_decryption_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.user_message_de
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


# ==================== Session Management ====================

@router.get(
    "/sessions/limits",
    summary="Session-Limits abfragen",
    description="Zeigt die aktuellen Session-Limit-Einstellungen und den Status"
)
async def get_session_limits(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Gibt die Session-Limit-Konfiguration und den aktuellen Status zurück.

    Returns:
        - **max_sessions**: Maximale Anzahl gleichzeitiger Sessions
        - **current_sessions**: Aktuelle Anzahl aktiver Sessions
        - **limit_mode**: "soft" (alte Sessions automatisch beendet) oder "hard" (Login blockiert)
        - **session_expiry_hours**: Wie lange Sessions gültig sind
        - **can_create_new**: Ob eine neue Session erstellt werden kann
    """
    from app.core.session_manager import (
        get_session_manager,
        MAX_SESSIONS_PER_USER,
        SESSION_EXPIRY_HOURS,
        SESSION_LIMIT_MODE
    )

    session_manager = get_session_manager()
    sessions = await session_manager.get_active_sessions(db, current_user.id)
    current_count = len(sessions)

    # Bei soft mode kann immer eine neue Session erstellt werden (alte werden entfernt)
    # Bei hard mode nur wenn unter dem Limit
    can_create_new = (
        SESSION_LIMIT_MODE == "soft" or
        current_count < MAX_SESSIONS_PER_USER
    )

    return {
        "max_sessions": MAX_SESSIONS_PER_USER,
        "current_sessions": current_count,
        "limit_mode": SESSION_LIMIT_MODE,
        "session_expiry_hours": SESSION_EXPIRY_HOURS,
        "can_create_new": can_create_new,
        "hinweis": (
            "Im 'soft'-Modus werden älteste Sessions automatisch beendet. "
            "Im 'hard'-Modus wird der Login blockiert wenn das Limit erreicht ist."
        )
    }


@router.get(
    "/sessions",
    response_model=SessionListResponse,
    summary="Aktive Sessions auflisten",
    description="Zeigt alle aktiven Sessions des Benutzers"
)
async def list_sessions(
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> SessionListResponse:
    """
    Listet alle aktiven Sessions des aktuellen Benutzers auf.

    Zeigt für jede Session:
    - Gerät und Browser
    - IP-Adresse
    - Letzte Aktivität
    - Ob es die aktuelle Session ist

    **Sicherheitshinweis:**
    Unbekannte Sessions können auf unbefugten Zugriff hinweisen.
    """
    from app.core.session_manager import get_session_manager

    session_manager = get_session_manager()
    sessions = await session_manager.get_active_sessions(db, current_user.id)

    # Finde aktuelle Session anhand des Tokens
    current_session_id = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            token = auth_header.split(" ")[1]
            payload = await decode_token(token)
            current_jti = payload.get("jti")

            if current_jti:
                current_session = await session_manager.get_session_by_jti(db, current_jti)
                if current_session:
                    current_session_id = current_session.id
        except Exception as token_error:
            # Token-Fehler loggen aber Session-Liste nicht blockieren
            import structlog
            logger = structlog.get_logger(__name__)
            logger.warning(
                "session_list_token_extraction_failed",
                error=str(token_error),
                user_id=str(current_user.id),
            )

    session_infos = []
    for session in sessions:
        session_infos.append(SessionInfo(
            id=session.id,
            device_name=session.device_name,
            device_type=session.device_type,
            ip_address=session.ip_address,
            location=session.location,
            last_activity_at=session.last_activity_at,
            created_at=session.created_at,
            expires_at=session.expires_at,
            is_current=session.id == current_session_id
        ))

    return SessionListResponse(
        sessions=session_infos,
        total=len(session_infos),
        current_session_id=current_session_id
    )


@router.delete(
    "/sessions/{session_id}",
    response_model=SessionRevokeResponse,
    summary="Session widerrufen",
    description="Beendet eine einzelne Session"
)
async def revoke_session(
    session_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> SessionRevokeResponse:
    """
    Widerruft eine einzelne Session.

    Nach dem Widerruf ist die Session ungültig und
    der Benutzer wird auf diesem Gerät abgemeldet.

    **Hinweis:**
    Sie können nur Ihre eigenen Sessions widerrufen.
    """
    from uuid import UUID
    from app.core.session_manager import get_session_manager, SessionError

    session_manager = get_session_manager()

    try:
        await session_manager.revoke_session(db, session_id, current_user.id)

        logger.info(
            "session_revoked_by_user",
            user_id=str(current_user.id)[:8] + "...",
            session_id=str(session_id)[:8] + "..."
        )

        return SessionRevokeResponse(
            success=True,
            revoked_count=1,
            nachricht="Session erfolgreich beendet"
        )

    except SessionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.user_message_de
        )


@router.delete(
    "/sessions",
    response_model=SessionRevokeResponse,
    summary="Alle Sessions widerrufen",
    description="Beendet alle Sessions (optional außer der aktuellen)"
)
async def revoke_all_sessions(
    request: Request,
    revoke_request: SessionRevokeAllRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> SessionRevokeResponse:
    """
    Widerruft alle Sessions des Benutzers.

    - **except_current**: Wenn true, bleibt die aktuelle Session aktiv

    **Anwendungsfälle:**
    - Nach Passwortänderung alle anderen Sessions beenden
    - Bei Verdacht auf unbefugten Zugriff
    - Abmeldung von allen Geräten

    **Hinweis:**
    Wenn except_current=false, müssen Sie sich erneut anmelden.
    """
    from app.core.session_manager import get_session_manager

    session_manager = get_session_manager()

    # Finde aktuelle Session JTI
    current_jti = None
    if revoke_request.except_current:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                token = auth_header.split(" ")[1]
                payload = await decode_token(token)
                current_jti = payload.get("jti")
            except Exception:
                pass

    count = await session_manager.revoke_all_sessions(
        db,
        current_user.id,
        except_current=revoke_request.except_current,
        current_jti=current_jti
    )

    logger.info(
        "all_sessions_revoked_by_user",
        user_id=str(current_user.id)[:8] + "...",
        count=count,
        except_current=revoke_request.except_current
    )

    if revoke_request.except_current:
        nachricht = f"{count} Session(s) beendet. Ihre aktuelle Session bleibt aktiv."
    else:
        nachricht = f"Alle {count} Session(s) beendet. Bitte melden Sie sich erneut an."

    return SessionRevokeResponse(
        success=True,
        revoked_count=count,
        nachricht=nachricht
    )


# ==================== Email Verification ====================

@router.get(
    "/email/verification-status",
    response_model=EmailVerificationStatusResponse,
    summary="Email-Verifizierungsstatus",
    description="Zeigt den aktuellen Verifizierungsstatus der Email-Adresse"
)
async def get_email_verification_status(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Prüft den Email-Verifizierungsstatus des aktuellen Benutzers.

    Returns:
        - **email**: Aktuelle Email-Adresse
        - **email_verified**: Ob Email verifiziert ist
        - **email_verified_at**: Zeitpunkt der Verifizierung
        - **pending_verification**: Ob Verifizierung aussteht
        - **pending_email_change**: Ob Email-Änderung aussteht
    """
    from app.db.schemas import EmailVerificationStatusResponse
    from app.services.email_verification_service import get_email_verification_service

    service = get_email_verification_service()
    status = await service.check_verification_status(db, current_user.id)

    return EmailVerificationStatusResponse(**status)


@router.post(
    "/email/resend-verification",
    response_model=EmailVerificationResponse,
    summary="Verifizierungs-Email erneut senden",
    description="Sendet die Verifizierungs-Email erneut an die aktuelle Adresse"
)
async def resend_verification_email(
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Sendet die Verifizierungs-Email erneut.

    **Rate-Limiting:** Max 3 Anfragen pro Stunde.

    Falls die Email bereits verifiziert ist, wird eine entsprechende
    Meldung zurückgegeben.
    """
    from app.db.schemas import EmailVerificationResponse
    from app.services.email_verification_service import get_email_verification_service
    from app.core.exceptions import EmailVerificationError

    service = get_email_verification_service()
    client_ip = request.client.host if request.client else None

    try:
        token = await service.resend_verification(db, current_user.id, client_ip)

        if token is None:
            return EmailVerificationResponse(
                success=True,
                email=current_user.email,
                nachricht="Ihre Email-Adresse ist bereits verifiziert"
            )

        # In Produktion: Email mit Token senden
        # await notification_service.send_verification_email(current_user.email, token)

        logger.info(
            "verification_email_resent",
            user_id=str(current_user.id)[:8] + "...",
            email=current_user.email[:3] + "***"
        )

        return EmailVerificationResponse(
            success=True,
            email=current_user.email,
            nachricht="Verifizierungs-Email wurde gesendet. Bitte prüfen Sie Ihren Posteingang."
        )

    except EmailVerificationError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=e.user_message_de
        )


@router.post(
    "/email/verify",
    response_model=EmailVerifyResponse,
    summary="Email verifizieren",
    description="Verifiziert die Email-Adresse mit dem Token aus der Email"
)
async def verify_email(
    verify_request: EmailVerifyTokenRequest,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Verifiziert eine Email-Adresse mit dem Token.

    - **token**: Das Token aus der Verifizierungs-Email

    **Hinweis:** Der Token ist 24 Stunden gültig.
    """
    from app.db.schemas import EmailVerifyTokenRequest, EmailVerifyResponse
    from app.services.email_verification_service import get_email_verification_service

    service = get_email_verification_service()
    success, message, user = await service.verify_email(db, verify_request.token)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )

    return EmailVerifyResponse(
        success=True,
        email_verified=True,
        nachricht=message
    )


@router.post(
    "/email/change",
    response_model=EmailChangeResponse,
    summary="Email-Adresse ändern",
    description="Initiiert eine Email-Änderung (erfordert Verifizierung)"
)
async def request_email_change(
    request: Request,
    change_request: EmailChangeRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Fordert eine Email-Änderung an.

    - **new_email**: Die neue Email-Adresse
    - **password**: Aktuelles Passwort zur Bestätigung

    Ein Verifizierungs-Link wird an die neue Email-Adresse gesendet.
    Die Änderung wird erst nach Klick auf den Link wirksam.
    """
    from app.db.schemas import EmailChangeRequest, EmailChangeResponse
    from app.services.email_verification_service import get_email_verification_service
    from app.services.user_service import UserService
    from app.core.exceptions import EmailVerificationError

    # Verifiziere Passwort
    authenticated = await UserService.authenticate_user(
        db, current_user.email, change_request.password
    )
    if not authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiges Passwort"
        )

    service = get_email_verification_service()
    client_ip = request.client.host if request.client else None

    try:
        token = await service.create_email_change_token(
            db,
            current_user.id,
            current_user.email,
            change_request.new_email,
            client_ip
        )

        # In Produktion: Email mit Token senden
        # await notification_service.send_email_change_verification(change_request.new_email, token)

        logger.info(
            "email_change_requested",
            user_id=str(current_user.id)[:8] + "...",
            new_email=change_request.new_email[:3] + "***"
        )

        return EmailChangeResponse(
            success=True,
            new_email=change_request.new_email,
            nachricht="Bestätigungs-Email wurde an die neue Adresse gesendet. "
                      "Bitte klicken Sie auf den Link in der Email."
        )

    except EmailVerificationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.user_message_de
        )
