"""
MFA (Multi-Factor Authentication) API Endpoints.

Ermoeglicht das Einrichten und Verwalten von TOTP-basierter 2FA.

Endpoints:
- GET  /mfa/status     - MFA-Status abrufen
- POST /mfa/setup      - 2FA-Einrichtung starten (QR-Code + Backup-Codes)
- POST /mfa/verify     - 2FA-Einrichtung bestaetigen
- POST /mfa/validate   - TOTP-Code bei Login validieren
- POST /mfa/backup     - Backup-Code verwenden
- POST /mfa/disable    - 2FA deaktivieren
- POST /mfa/regenerate - Neue Backup-Codes generieren

SECURITY:
- Alle Endpoints erfordern Authentifizierung
- Rate Limiting: 5 Versuche pro 15 Minuten fuer validate/backup
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.db.models import User
from app.services.auth.mfa_service import (
    MFAService,
    MFAServiceError,
    MFAAlreadyEnabledError,
    MFANotEnabledError,
    InvalidTOTPCodeError,
    get_mfa_service,
)

router = APIRouter(prefix="/mfa", tags=["MFA"])


# ==================== Request/Response Schemas ====================

class MFAStatusResponse(BaseModel):
    """MFA-Status Response."""
    enabled: bool = Field(..., description="Ob 2FA aktiviert ist")
    setup_at: Optional[str] = Field(None, description="Zeitpunkt der Einrichtung (ISO 8601)")
    backup_codes_remaining: int = Field(..., description="Anzahl verbleibender Backup-Codes")
    has_pending_setup: bool = Field(..., description="Ob ein Setup begonnen wurde aber nicht abgeschlossen")


class MFASetupResponse(BaseModel):
    """Response beim Starten des 2FA-Setups."""
    qr_code: str = Field(..., description="QR-Code als Data-URI (PNG)")
    secret: str = Field(..., description="TOTP-Secret fuer manuelle Eingabe")
    backup_codes: list[str] = Field(..., description="10 Backup-Codes (einmalig angezeigt!)")
    message: str = Field(
        default="Scannen Sie den QR-Code mit Ihrer Authenticator-App und bestaetigen Sie mit einem Code.",
        description="Anweisungen fuer den Benutzer"
    )


class TOTPVerifyRequest(BaseModel):
    """Request zum Verifizieren eines TOTP-Codes."""
    code: str = Field(
        ...,
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
        description="6-stelliger TOTP-Code aus der Authenticator-App"
    )


class BackupCodeRequest(BaseModel):
    """Request zum Verwenden eines Backup-Codes."""
    code: str = Field(
        ...,
        min_length=9,
        max_length=9,
        pattern=r"^[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}$",
        description="Backup-Code im Format XXXX-XXXX"
    )


class MFASuccessResponse(BaseModel):
    """Erfolgs-Response fuer MFA-Operationen."""
    success: bool = Field(default=True)
    message: str


class BackupCodesResponse(BaseModel):
    """Response mit neuen Backup-Codes."""
    backup_codes: list[str] = Field(..., description="Neue Backup-Codes")
    message: str = Field(
        default="Speichern Sie diese Codes sicher ab. Sie werden nur einmal angezeigt!",
        description="Warnung fuer den Benutzer"
    )


# ==================== Endpoints ====================

@router.get(
    "/status",
    response_model=MFAStatusResponse,
    summary="MFA-Status abrufen",
    description="Gibt den aktuellen 2FA-Status des angemeldeten Benutzers zurueck."
)
async def get_mfa_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> MFAStatusResponse:
    """Ruft den MFA-Status des aktuellen Benutzers ab."""
    mfa_service = get_mfa_service(db)

    try:
        status_data = await mfa_service.get_mfa_status(current_user.id)
        return MFAStatusResponse(**status_data)
    except MFAServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/setup",
    response_model=MFASetupResponse,
    summary="2FA-Einrichtung starten",
    description=(
        "Startet die Einrichtung der Zwei-Faktor-Authentifizierung. "
        "Gibt einen QR-Code und Backup-Codes zurueck. "
        "Der Benutzer muss anschliessend /mfa/verify aufrufen um die Einrichtung abzuschliessen."
    )
)
async def setup_mfa(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> MFASetupResponse:
    """Startet die 2FA-Einrichtung."""
    mfa_service = get_mfa_service(db)

    try:
        qr_code, secret, backup_codes = await mfa_service.setup_totp(current_user.id)

        return MFASetupResponse(
            qr_code=qr_code,
            secret=secret,
            backup_codes=backup_codes
        )
    except MFAAlreadyEnabledError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Zwei-Faktor-Authentifizierung ist bereits aktiviert. "
                   "Deaktivieren Sie sie zuerst, bevor Sie sie neu einrichten."
        )
    except MFAServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/verify",
    response_model=MFASuccessResponse,
    summary="2FA-Einrichtung bestaetigen",
    description=(
        "Bestaetigt die 2FA-Einrichtung mit einem Code aus der Authenticator-App. "
        "Dieser Schritt aktiviert die Zwei-Faktor-Authentifizierung endgueltig."
    )
)
async def verify_mfa_setup(
    request: TOTPVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> MFASuccessResponse:
    """Bestaetigt die 2FA-Einrichtung."""
    mfa_service = get_mfa_service(db)

    try:
        await mfa_service.verify_and_enable_totp(current_user.id, request.code)

        return MFASuccessResponse(
            success=True,
            message="Zwei-Faktor-Authentifizierung wurde erfolgreich aktiviert."
        )
    except MFAAlreadyEnabledError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Zwei-Faktor-Authentifizierung ist bereits aktiviert."
        )
    except InvalidTOTPCodeError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungueltiger Verifizierungscode. Bitte versuchen Sie es erneut."
        )
    except MFAServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post(
    "/validate",
    response_model=MFASuccessResponse,
    summary="TOTP-Code validieren",
    description=(
        "Validiert einen TOTP-Code. "
        "Wird waehrend des Logins verwendet, wenn 2FA aktiviert ist."
    )
)
async def validate_totp(
    request: TOTPVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> MFASuccessResponse:
    """Validiert einen TOTP-Code beim Login."""
    mfa_service = get_mfa_service(db)

    try:
        await mfa_service.verify_totp(current_user.id, request.code)

        return MFASuccessResponse(
            success=True,
            message="Code erfolgreich verifiziert."
        )
    except MFANotEnabledError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zwei-Faktor-Authentifizierung ist nicht aktiviert."
        )
    except InvalidTOTPCodeError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungueltiger Code. Bitte versuchen Sie es erneut."
        )
    except MFAServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/backup",
    response_model=MFASuccessResponse,
    summary="Backup-Code verwenden",
    description=(
        "Verwendet einen Backup-Code anstelle des TOTP-Codes. "
        "Backup-Codes sind einmalig verwendbar und werden nach Verwendung entfernt."
    )
)
async def use_backup_code(
    request: BackupCodeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> MFASuccessResponse:
    """Verwendet einen Backup-Code."""
    mfa_service = get_mfa_service(db)

    try:
        await mfa_service.verify_backup_code(current_user.id, request.code)

        return MFASuccessResponse(
            success=True,
            message="Backup-Code erfolgreich verwendet."
        )
    except MFANotEnabledError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zwei-Faktor-Authentifizierung ist nicht aktiviert."
        )
    except InvalidTOTPCodeError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungueltiger Backup-Code."
        )
    except MFAServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/disable",
    response_model=MFASuccessResponse,
    summary="2FA deaktivieren",
    description=(
        "Deaktiviert die Zwei-Faktor-Authentifizierung. "
        "Erfordert einen gueltigen TOTP-Code zur Bestaetigung."
    )
)
async def disable_mfa(
    request: TOTPVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> MFASuccessResponse:
    """Deaktiviert 2FA."""
    mfa_service = get_mfa_service(db)

    try:
        await mfa_service.disable_totp(current_user.id, request.code)

        return MFASuccessResponse(
            success=True,
            message="Zwei-Faktor-Authentifizierung wurde deaktiviert."
        )
    except MFANotEnabledError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zwei-Faktor-Authentifizierung ist nicht aktiviert."
        )
    except InvalidTOTPCodeError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungueltiger Code. Die Deaktivierung wurde abgebrochen."
        )
    except MFAServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/regenerate",
    response_model=BackupCodesResponse,
    summary="Backup-Codes neu generieren",
    description=(
        "Generiert neue Backup-Codes. "
        "Alle bestehenden Backup-Codes werden ungueltig. "
        "Erfordert einen gueltigen TOTP-Code zur Bestaetigung."
    )
)
async def regenerate_backup_codes(
    request: TOTPVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> BackupCodesResponse:
    """Generiert neue Backup-Codes."""
    mfa_service = get_mfa_service(db)

    try:
        backup_codes = await mfa_service.regenerate_backup_codes(
            current_user.id,
            request.code
        )

        return BackupCodesResponse(backup_codes=backup_codes)
    except MFANotEnabledError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zwei-Faktor-Authentifizierung ist nicht aktiviert."
        )
    except InvalidTOTPCodeError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungueltiger Code. Die Generierung wurde abgebrochen."
        )
    except MFAServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
