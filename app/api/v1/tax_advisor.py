"""GoBD Steuerberater-Zugang API Endpoints.

API fuer Steuerberater-Management:
- Einladungen erstellen, auflisten, widerrufen
- Einladungen akzeptieren (oeffentlich)
- Zugangszeiten verlaengern oder widerrufen
- Zugriffslogs abrufen

GoBD-Konformitaet:
- Nachvollziehbarkeit: Alle Aktionen werden protokolliert
- Zeitliche Begrenzung: Zugang laeuft automatisch ab
- Eingeschraenkter Zugriff: Nur Lesezugriff auf relevante Dokumente
"""

from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from pydantic import BaseModel, ConfigDict, Field, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.api.dependencies import get_db, get_current_user, get_current_superuser
from app.db.models import User, TaxAdvisorInvite, TaxAdvisorAccessLog
from app.middleware.company_context import require_company
from app.services.tax_advisor_service import tax_advisor_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/tax-advisor", tags=["Steuerberater-Zugang"])


# ==================== Pydantic Schemas ====================

class TaxAdvisorInviteCreate(BaseModel):
    """Schema zum Erstellen einer Steuerberater-Einladung."""
    email: EmailStr = Field(..., description="E-Mail des Steuerberaters")
    full_name: Optional[str] = Field(None, max_length=255, description="Name des Steuerberaters")
    tax_firm_name: Optional[str] = Field(None, max_length=255, description="Name der Steuerkanzlei")
    tax_advisor_id: Optional[str] = Field(None, max_length=50, description="Steuerberater-ID der Kammer")
    access_duration_days: int = Field(
        30,
        ge=1,
        le=365,
        description="Zugangsdauer in Tagen (1-365)"
    )
    access_scope: Optional[dict] = Field(
        None,
        description="Eingeschraenkter Zugriff (z.B. Zeitraum, Dokumenttypen)"
    )


class TaxAdvisorInviteResponse(BaseModel):
    """Antwort-Schema fuer Einladungen."""
    id: UUID
    email: str
    full_name: Optional[str]
    tax_firm_name: Optional[str]
    tax_advisor_id: Optional[str]
    access_duration_days: int
    access_scope: Optional[dict]
    status: str
    expires_at: datetime
    created_at: datetime
    accepted_at: Optional[datetime]
    company_id: UUID

    model_config = ConfigDict(from_attributes=True)


class TaxAdvisorInviteCreateResponse(BaseModel):
    """Antwort beim Erstellen einer Einladung (mit Token)."""
    invite: TaxAdvisorInviteResponse
    invite_url: str = Field(..., description="URL zum Akzeptieren der Einladung")


class TaxAdvisorAcceptRequest(BaseModel):
    """Schema zum Akzeptieren einer Einladung."""
    token: str = Field(..., min_length=32, description="Einladungs-Token")
    password: str = Field(..., min_length=8, max_length=128, description="Gewaehltes Passwort")


class TaxAdvisorUserResponse(BaseModel):
    """Antwort-Schema fuer Steuerberater-Benutzer."""
    id: UUID
    email: str
    username: str
    full_name: Optional[str]
    access_until: Optional[datetime]
    is_active: bool
    created_at: datetime
    invited_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class TaxAdvisorExtendRequest(BaseModel):
    """Schema zum Verlaengern des Zugangs."""
    additional_days: int = Field(..., ge=1, le=365, description="Zusaetzliche Tage (1-365)")


class TaxAdvisorRevokeRequest(BaseModel):
    """Schema zum Widerrufen des Zugangs."""
    reason: Optional[str] = Field(None, max_length=500, description="Optionaler Grund")


class TaxAdvisorAccessLogResponse(BaseModel):
    """Antwort-Schema fuer Zugriffslogs."""
    id: UUID
    user_id: UUID
    action: str
    resource_type: str
    resource_id: Optional[UUID]
    details: Optional[dict]
    ip_address: Optional[str]
    user_agent: Optional[str]
    accessed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    """Einfache Nachricht-Antwort."""
    message: str


# ==================== Admin Endpoints ====================

@router.post(
    "/invites",
    response_model=TaxAdvisorInviteCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Steuerberater einladen",
    description="Erstellt eine neue Einladung fuer einen Steuerberater"
)
async def create_invite(
    data: TaxAdvisorInviteCreate,
    request: Request,
    company_id: UUID = Depends(require_company),
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> TaxAdvisorInviteCreateResponse:
    """
    Erstellt eine neue Steuerberater-Einladung.

    Nur fuer Administratoren zugaenglich.

    **Pflichtfelder:**
    - **email**: E-Mail des Steuerberaters

    **Optionale Felder:**
    - **full_name**: Name des Steuerberaters
    - **tax_firm_name**: Name der Steuerkanzlei
    - **tax_advisor_id**: Steuerberater-ID der Kammer
    - **access_duration_days**: Zugangsdauer in Tagen (Standard: 30)
    - **access_scope**: Zugriffsbeschraenkungen (Zeitraum, Dokumenttypen)
    """
    try:
        invite, token = await tax_advisor_service.create_invite(
            db=db,
            company_id=company_id,
            email=data.email,
            invited_by=current_user,
            full_name=data.full_name,
            tax_firm_name=data.tax_firm_name,
            tax_advisor_id=data.tax_advisor_id,
            access_duration_days=data.access_duration_days,
            access_scope=data.access_scope,
        )

        # Invite-URL erstellen
        base_url = str(request.base_url).rstrip("/")
        invite_url = f"{base_url}/steuerberater/einladung/{token}"

        logger.info(
            "tax_advisor_invite_created",
            invite_id=str(invite.id),
            email=data.email,
            company_id=str(company_id),
            created_by=str(current_user.id)
        )

        return TaxAdvisorInviteCreateResponse(
            invite=TaxAdvisorInviteResponse.model_validate(invite),
            invite_url=invite_url
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get(
    "/invites",
    response_model=List[TaxAdvisorInviteResponse],
    summary="Einladungen auflisten",
    description="Listet alle Einladungen fuer die aktuelle Firma auf"
)
async def list_invites(
    include_expired: bool = Query(False, description="Abgelaufene Einladungen einbeziehen"),
    company_id: UUID = Depends(require_company),
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> List[TaxAdvisorInviteResponse]:
    """
    Listet Steuerberater-Einladungen fuer die aktuelle Firma auf.

    Nur fuer Administratoren zugaenglich.
    """
    if include_expired:
        from sqlalchemy import select
        result = await db.execute(
            select(TaxAdvisorInvite)
            .where(TaxAdvisorInvite.company_id == company_id)
            .order_by(TaxAdvisorInvite.created_at.desc())
        )
        invites = list(result.scalars().all())
    else:
        invites = await tax_advisor_service.get_pending_invites(db, company_id)

    return [TaxAdvisorInviteResponse.model_validate(i) for i in invites]


@router.delete(
    "/invites/{invite_id}",
    response_model=MessageResponse,
    summary="Einladung widerrufen",
    description="Widerruft eine ausstehende Einladung"
)
async def revoke_invite(
    invite_id: UUID,
    company_id: UUID = Depends(require_company),
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Widerruft eine ausstehende Steuerberater-Einladung.

    Nur fuer Administratoren zugaenglich.
    Die Einladung muss noch ausstehend (pending) sein.
    """
    # Pruefen ob Einladung zur Firma gehoert
    invite = await db.get(TaxAdvisorInvite, invite_id)
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Einladung nicht gefunden"
        )

    if invite.company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung fuer diese Einladung"
        )

    try:
        await tax_advisor_service.revoke_invite(db, invite_id, current_user)
        return MessageResponse(message="Einladung wurde widerrufen")

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# ==================== Tax Advisor User Management ====================

@router.get(
    "/users",
    response_model=List[TaxAdvisorUserResponse],
    summary="Steuerberater auflisten",
    description="Listet alle aktiven Steuerberater fuer die aktuelle Firma auf"
)
async def list_tax_advisors(
    company_id: UUID = Depends(require_company),
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> List[TaxAdvisorUserResponse]:
    """
    Listet aktive Steuerberater fuer die aktuelle Firma auf.

    Nur fuer Administratoren zugaenglich.
    """
    users = await tax_advisor_service.get_active_tax_advisors(db, company_id)
    return [TaxAdvisorUserResponse.model_validate(u) for u in users]


@router.post(
    "/users/{user_id}/extend",
    response_model=TaxAdvisorUserResponse,
    summary="Zugang verlaengern",
    description="Verlaengert den Zugang eines Steuerberaters"
)
async def extend_access(
    user_id: UUID,
    data: TaxAdvisorExtendRequest,
    company_id: UUID = Depends(require_company),
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> TaxAdvisorUserResponse:
    """
    Verlaengert den Zugang eines Steuerberaters.

    Nur fuer Administratoren zugaenglich.
    """
    try:
        user = await tax_advisor_service.extend_access(
            db=db,
            user_id=user_id,
            additional_days=data.additional_days,
            extended_by=current_user,
        )
        return TaxAdvisorUserResponse.model_validate(user)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post(
    "/users/{user_id}/revoke",
    response_model=MessageResponse,
    summary="Zugang widerrufen",
    description="Widerruft den Zugang eines Steuerberaters sofort"
)
async def revoke_access(
    user_id: UUID,
    data: TaxAdvisorRevokeRequest,
    company_id: UUID = Depends(require_company),
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Widerruft den Zugang eines Steuerberaters sofort.

    Nur fuer Administratoren zugaenglich.
    Der Benutzer wird deaktiviert und kann sich nicht mehr anmelden.
    """
    try:
        await tax_advisor_service.revoke_access(
            db=db,
            user_id=user_id,
            revoked_by=current_user,
            reason=data.reason,
        )
        return MessageResponse(message="Zugang wurde widerrufen")

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# ==================== Access Logs ====================

@router.get(
    "/logs",
    response_model=List[TaxAdvisorAccessLogResponse],
    summary="Zugriffslogs abrufen",
    description="Ruft Steuerberater-Zugriffslogs fuer die aktuelle Firma ab"
)
async def get_access_logs(
    user_id: Optional[UUID] = Query(None, description="Nach Benutzer filtern"),
    action: Optional[str] = Query(None, description="Nach Aktion filtern"),
    from_date: Optional[datetime] = Query(None, description="Start-Datum"),
    to_date: Optional[datetime] = Query(None, description="End-Datum"),
    limit: int = Query(100, ge=1, le=1000, description="Max. Ergebnisse"),
    offset: int = Query(0, ge=0, description="Offset fuer Paginierung"),
    company_id: UUID = Depends(require_company),
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> List[TaxAdvisorAccessLogResponse]:
    """
    Ruft Steuerberater-Zugriffslogs ab.

    Nur fuer Administratoren zugaenglich.
    Diese Logs sind revisionssicher und dokumentieren alle Steuerberater-Aktivitaeten.
    """
    logs = await tax_advisor_service.get_access_logs(
        db=db,
        company_id=company_id,
        user_id=user_id,
        action=action,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
    )
    return [TaxAdvisorAccessLogResponse.model_validate(log) for log in logs]


# ==================== Public Endpoints (Invite Acceptance) ====================

@router.post(
    "/accept",
    response_model=TaxAdvisorUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Einladung akzeptieren",
    description="Akzeptiert eine Steuerberater-Einladung und erstellt den Benutzer"
)
async def accept_invite(
    data: TaxAdvisorAcceptRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TaxAdvisorUserResponse:
    """
    Akzeptiert eine Steuerberater-Einladung.

    Dieser Endpoint ist oeffentlich zugaenglich (kein Login erforderlich).
    Der Steuerberater erhaelt einen Link mit Token per E-Mail und
    kann sich damit registrieren.

    **Pflichtfelder:**
    - **token**: Einladungs-Token (aus der E-Mail)
    - **password**: Gewaehltes Passwort (min. 8 Zeichen)
    """
    try:
        # IP und User-Agent fuer Audit
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent", "")[:500]

        user = await tax_advisor_service.accept_invite(
            db=db,
            token=data.token,
            password=data.password,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        logger.info(
            "tax_advisor_invite_accepted",
            user_id=str(user.id),
            email=user.email,
            ip_address=ip_address
        )

        return TaxAdvisorUserResponse.model_validate(user)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get(
    "/validate/{token}",
    response_model=TaxAdvisorInviteResponse,
    summary="Token validieren",
    description="Validiert ein Einladungs-Token (oeffentlich)"
)
async def validate_token(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> TaxAdvisorInviteResponse:
    """
    Validiert ein Einladungs-Token.

    Dieser Endpoint ist oeffentlich zugaenglich.
    Wird verwendet, um vor der Registrierung zu pruefen,
    ob das Token gueltig ist.
    """
    import hashlib
    from sqlalchemy import select
    from app.db.models import TaxAdvisorInviteStatus

    token_hash = hashlib.sha256(token.encode()).hexdigest()

    result = await db.execute(
        select(TaxAdvisorInvite).where(TaxAdvisorInvite.token_hash == token_hash)
    )
    invite = result.scalar_one_or_none()

    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Einladung nicht gefunden"
        )

    if invite.status != TaxAdvisorInviteStatus.PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Diese Einladung wurde bereits {invite.status}"
        )

    if invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Diese Einladung ist abgelaufen"
        )

    return TaxAdvisorInviteResponse.model_validate(invite)
