# -*- coding: utf-8 -*-
"""
DATEV Connect API Endpoints.

Vollstaendige REST API fuer DATEVconnect Integration:
- Verbindungs-Management (OAuth2)
- Stammdaten Sync
- Buchungsstapel
- Kontierungsvorschlaege
- GoBD Compliance

Feinpoliert und durchdacht - Enterprise-Ready DATEV Integration.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import List, Optional

from app.core.types import JSONDict

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log
from app.db import models

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/datev-connect", tags=["DATEV Connect"])


# =============================================================================
# Schemas
# =============================================================================

class DATEVConnectionCreate(BaseModel):
    """Schema fuer neue DATEV-Verbindung."""

    name: str = Field(..., min_length=1, max_length=100)
    beraternummer: str = Field(..., min_length=5, max_length=10)
    mandantennummer: str = Field(..., min_length=5, max_length=10)
    wirtschaftsjahr_beginn: int = Field(default=1, ge=1, le=12)

    # OAuth2
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    redirect_uri: Optional[str] = None

    # Einstellungen
    api_environment: str = Field(default="production")
    kontenrahmen: str = Field(default="SKR03")
    sachkontenlange: int = Field(default=4, ge=4, le=8)
    personenkontenlange: int = Field(default=5, ge=5, le=9)
    buchungsmodus: str = Field(default="manuell")

    # Standard-Konten
    sammelkonto_debitoren: Optional[str] = "1400"
    sammelkonto_kreditoren: Optional[str] = "1600"
    erloskonto_standard: Optional[str] = "8400"
    aufwandskonto_standard: Optional[str] = "4400"

    # GoBD
    gobd_enabled: bool = True
    festschreibung_automatisch: bool = False
    beleglink_prefix: Optional[str] = None

    @field_validator("kontenrahmen")
    @classmethod
    def validate_kontenrahmen(cls, v: str) -> str:
        if v not in ("SKR03", "SKR04"):
            raise ValueError("Kontenrahmen muss SKR03 oder SKR04 sein")
        return v

    @field_validator("api_environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        if v not in ("production", "sandbox"):
            raise ValueError("Umgebung muss production oder sandbox sein")
        return v


class DATEVConnectionUpdate(BaseModel):
    """Schema fuer Verbindungs-Update."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    redirect_uri: Optional[str] = None
    buchungsmodus: Optional[str] = None
    gobd_enabled: Optional[bool] = None
    festschreibung_automatisch: Optional[bool] = None
    beleglink_prefix: Optional[str] = None
    is_active: Optional[bool] = None


class DATEVConnectionResponse(BaseModel):
    """Response-Schema fuer DATEV-Verbindung."""

    id: str
    name: str
    beraternummer: str
    mandantennummer: str
    wirtschaftsjahr_beginn: int
    api_environment: str
    kontenrahmen: str
    sachkontenlange: int
    personenkontenlange: int
    buchungsmodus: str
    gobd_enabled: bool
    festschreibung_automatisch: bool
    connection_status: str
    is_active: bool
    last_stammdaten_sync: Optional[str] = None
    last_buchungen_sync: Optional[str] = None
    created_at: str

    class Config:
        from_attributes = True


class OAuthStartResponse(BaseModel):
    """Response fuer OAuth-Start."""

    authorization_url: str
    state: str


class KontierungInput(BaseModel):
    """Eingabe fuer Kontierungsvorschlag."""

    entity_name: Optional[str] = None
    entity_vat_id: Optional[str] = None
    betrag_brutto: Decimal
    mwst_satz: Optional[Decimal] = None
    dokument_typ: str = "invoice"
    richtung: str = "incoming"
    stichwort: Optional[str] = None
    document_id: Optional[str] = None


class KontierungResponse(BaseModel):
    """Response fuer Kontierungsvorschlag."""

    konto: str
    gegenkonto: str
    bu_schluessel: str
    kostenstelle: Optional[str] = None
    confidence: float
    source: str
    explanation: str
    alternatives: List[JSONDict] = []


class BuchungCreate(BaseModel):
    """Schema fuer neue Buchung."""

    document_id: Optional[str] = None
    umsatz: Decimal
    soll_haben: str = Field(..., pattern="^[SH]$")
    konto: str
    gegenkonto: str
    bu_schluessel: Optional[str] = None
    belegdatum: date
    belegfeld_1: Optional[str] = None
    buchungstext: Optional[str] = None
    kostenstelle_1: Optional[str] = None


class BuchungResponse(BaseModel):
    """Response fuer Buchung."""

    id: str
    buchungs_guid: str
    umsatz: float
    soll_haben: str
    konto: str
    gegenkonto: str
    bu_schluessel: Optional[str]
    belegdatum: str
    belegfeld_1: Optional[str]
    buchungstext: Optional[str]
    sync_status: str
    ist_festgeschrieben: bool
    created_at: str


class FestschreibungRequest(BaseModel):
    """Request fuer Festschreibung."""

    bis_datum: date


class FestschreibungResponse(BaseModel):
    """Response fuer Festschreibung."""

    success: bool
    festschreibung_datum: Optional[str]
    buchungen_count: int
    fehler: List[str]


class GoBDValidationResponse(BaseModel):
    """Response fuer GoBD-Pruefung."""

    is_compliant: bool
    pruefung_datum: str
    findings: List[JSONDict]
    statistics: JSONDict


class SyncTriggerResponse(BaseModel):
    """Response fuer Sync-Trigger."""

    task_id: str
    message: str


# =============================================================================
# Connection Endpoints
# =============================================================================

@router.post(
    "/connections",
    response_model=DATEVConnectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_connection(
    data: DATEVConnectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> DATEVConnectionResponse:
    """
    Erstellt eine neue DATEV-Verbindung.

    Erfordert Client ID und Secret fuer OAuth2-Flow.
    """
    from app.core.encryption import encrypt_value

    # Pruefen ob Mandant bereits existiert
    existing = await db.execute(
        select(models.DATEVConnection).where(
            and_(
                models.DATEVConnection.company_id == current_user.company_id,
                models.DATEVConnection.beraternummer == data.beraternummer,
                models.DATEVConnection.mandantennummer == data.mandantennummer,
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dieser Mandant ist bereits konfiguriert",
        )

    # Verbindung erstellen
    connection = models.DATEVConnection(
        id=uuid.uuid4(),
        company_id=current_user.company_id,
        name=data.name,
        beraternummer=data.beraternummer,
        mandantennummer=data.mandantennummer,
        wirtschaftsjahr_beginn=data.wirtschaftsjahr_beginn,
        client_id=data.client_id,
        client_secret_encrypted=encrypt_value(data.client_secret) if data.client_secret else None,
        redirect_uri=data.redirect_uri,
        api_environment=data.api_environment,
        kontenrahmen=data.kontenrahmen,
        sachkontenlange=data.sachkontenlange,
        personenkontenlange=data.personenkontenlange,
        buchungsmodus=data.buchungsmodus,
        sammelkonto_debitoren=data.sammelkonto_debitoren,
        sammelkonto_kreditoren=data.sammelkonto_kreditoren,
        erloskonto_standard=data.erloskonto_standard,
        aufwandskonto_standard=data.aufwandskonto_standard,
        gobd_enabled=data.gobd_enabled,
        festschreibung_automatisch=data.festschreibung_automatisch,
        beleglink_prefix=data.beleglink_prefix,
        connection_status="disconnected",
        is_active=True,
        created_by=current_user.id,
    )

    db.add(connection)
    await db.commit()
    await db.refresh(connection)

    logger.info(
        "datev_connection_created",
        connection_id=str(connection.id),
        mandant=f"{data.beraternummer}/{data.mandantennummer}",
        user_id=str(current_user.id),
    )

    return DATEVConnectionResponse(
        id=str(connection.id),
        name=connection.name,
        beraternummer=connection.beraternummer,
        mandantennummer=connection.mandantennummer,
        wirtschaftsjahr_beginn=connection.wirtschaftsjahr_beginn,
        api_environment=connection.api_environment,
        kontenrahmen=connection.kontenrahmen,
        sachkontenlange=connection.sachkontenlange,
        personenkontenlange=connection.personenkontenlange,
        buchungsmodus=connection.buchungsmodus,
        gobd_enabled=connection.gobd_enabled,
        festschreibung_automatisch=connection.festschreibung_automatisch,
        connection_status=connection.connection_status,
        is_active=connection.is_active,
        created_at=connection.created_at.isoformat(),
    )


@router.get(
    "/connections",
    response_model=List[DATEVConnectionResponse],
)
async def list_connections(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> List[DATEVConnectionResponse]:
    """Listet alle DATEV-Verbindungen der Company."""
    result = await db.execute(
        select(models.DATEVConnection).where(
            models.DATEVConnection.company_id == current_user.company_id,
        )
    )
    connections = result.scalars().all()

    return [
        DATEVConnectionResponse(
            id=str(c.id),
            name=c.name,
            beraternummer=c.beraternummer,
            mandantennummer=c.mandantennummer,
            wirtschaftsjahr_beginn=c.wirtschaftsjahr_beginn,
            api_environment=c.api_environment,
            kontenrahmen=c.kontenrahmen,
            sachkontenlange=c.sachkontenlange,
            personenkontenlange=c.personenkontenlange,
            buchungsmodus=c.buchungsmodus,
            gobd_enabled=c.gobd_enabled,
            festschreibung_automatisch=c.festschreibung_automatisch,
            connection_status=c.connection_status,
            is_active=c.is_active,
            last_stammdaten_sync=c.last_stammdaten_sync.isoformat() if c.last_stammdaten_sync else None,
            last_buchungen_sync=c.last_buchungen_sync.isoformat() if c.last_buchungen_sync else None,
            created_at=c.created_at.isoformat(),
        )
        for c in connections
    ]


@router.get(
    "/connections/{connection_id}",
    response_model=DATEVConnectionResponse,
)
async def get_connection(
    connection_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> DATEVConnectionResponse:
    """Holt eine spezifische DATEV-Verbindung."""
    result = await db.execute(
        select(models.DATEVConnection).where(
            and_(
                models.DATEVConnection.id == uuid.UUID(connection_id),
                models.DATEVConnection.company_id == current_user.company_id,
            )
        )
    )
    connection = result.scalar_one_or_none()

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verbindung nicht gefunden",
        )

    return DATEVConnectionResponse(
        id=str(connection.id),
        name=connection.name,
        beraternummer=connection.beraternummer,
        mandantennummer=connection.mandantennummer,
        wirtschaftsjahr_beginn=connection.wirtschaftsjahr_beginn,
        api_environment=connection.api_environment,
        kontenrahmen=connection.kontenrahmen,
        sachkontenlange=connection.sachkontenlange,
        personenkontenlange=connection.personenkontenlange,
        buchungsmodus=connection.buchungsmodus,
        gobd_enabled=connection.gobd_enabled,
        festschreibung_automatisch=connection.festschreibung_automatisch,
        connection_status=connection.connection_status,
        is_active=connection.is_active,
        last_stammdaten_sync=connection.last_stammdaten_sync.isoformat() if connection.last_stammdaten_sync else None,
        last_buchungen_sync=connection.last_buchungen_sync.isoformat() if connection.last_buchungen_sync else None,
        created_at=connection.created_at.isoformat(),
    )


@router.patch(
    "/connections/{connection_id}",
    response_model=DATEVConnectionResponse,
)
async def update_connection(
    connection_id: str,
    data: DATEVConnectionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> DATEVConnectionResponse:
    """Aktualisiert eine DATEV-Verbindung."""
    from app.core.encryption import encrypt_value

    result = await db.execute(
        select(models.DATEVConnection).where(
            and_(
                models.DATEVConnection.id == uuid.UUID(connection_id),
                models.DATEVConnection.company_id == current_user.company_id,
            )
        )
    )
    connection = result.scalar_one_or_none()

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verbindung nicht gefunden",
        )

    # Felder aktualisieren
    update_data = data.model_dump(exclude_unset=True)

    if "client_secret" in update_data:
        update_data["client_secret_encrypted"] = encrypt_value(update_data.pop("client_secret"))

    for field, value in update_data.items():
        setattr(connection, field, value)

    connection.updated_at = utc_now()
    connection.updated_by = current_user.id

    await db.commit()
    await db.refresh(connection)

    return DATEVConnectionResponse(
        id=str(connection.id),
        name=connection.name,
        beraternummer=connection.beraternummer,
        mandantennummer=connection.mandantennummer,
        wirtschaftsjahr_beginn=connection.wirtschaftsjahr_beginn,
        api_environment=connection.api_environment,
        kontenrahmen=connection.kontenrahmen,
        sachkontenlange=connection.sachkontenlange,
        personenkontenlange=connection.personenkontenlange,
        buchungsmodus=connection.buchungsmodus,
        gobd_enabled=connection.gobd_enabled,
        festschreibung_automatisch=connection.festschreibung_automatisch,
        connection_status=connection.connection_status,
        is_active=connection.is_active,
        created_at=connection.created_at.isoformat(),
    )


@router.delete(
    "/connections/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_connection(
    connection_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> None:
    """Loescht eine DATEV-Verbindung (Soft-Delete)."""
    result = await db.execute(
        select(models.DATEVConnection).where(
            and_(
                models.DATEVConnection.id == uuid.UUID(connection_id),
                models.DATEVConnection.company_id == current_user.company_id,
            )
        )
    )
    connection = result.scalar_one_or_none()

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verbindung nicht gefunden",
        )

    connection.is_active = False
    connection.updated_at = utc_now()
    await db.commit()


# =============================================================================
# OAuth2 Endpoints
# =============================================================================

@router.post(
    "/connections/{connection_id}/oauth/start",
    response_model=OAuthStartResponse,
)
async def start_oauth_flow(
    connection_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> OAuthStartResponse:
    """
    Startet OAuth2-Flow fuer DATEV-Verbindung.

    Gibt Authorization URL zurueck, zu der der User weitergeleitet werden muss.
    """
    from app.services.datev.connect import get_datev_auth_service

    result = await db.execute(
        select(models.DATEVConnection).where(
            and_(
                models.DATEVConnection.id == uuid.UUID(connection_id),
                models.DATEVConnection.company_id == current_user.company_id,
            )
        )
    )
    connection = result.scalar_one_or_none()

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verbindung nicht gefunden",
        )

    if not connection.client_id or not connection.redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client ID und Redirect URI muessen konfiguriert sein",
        )

    auth_service = get_datev_auth_service()
    auth_url, state = auth_service.get_authorization_url(
        client_id=connection.client_id,
        redirect_uri=connection.redirect_uri,
        environment=connection.api_environment,
        connection_id=connection.id,
    )

    return OAuthStartResponse(
        authorization_url=auth_url,
        state=state,
    )


@router.post(
    "/connections/{connection_id}/oauth/callback",
)
async def oauth_callback(
    connection_id: str,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> JSONDict:
    """
    Verarbeitet OAuth2-Callback nach User-Consent.

    Tauscht Authorization Code gegen Access/Refresh Tokens.
    """
    from app.services.datev.connect import get_datev_auth_service
    from app.core.encryption import decrypt_value

    result = await db.execute(
        select(models.DATEVConnection).where(
            and_(
                models.DATEVConnection.id == uuid.UUID(connection_id),
                models.DATEVConnection.company_id == current_user.company_id,
            )
        )
    )
    connection = result.scalar_one_or_none()

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verbindung nicht gefunden",
        )

    auth_service = get_datev_auth_service()

    # State validieren
    state_data = auth_service.validate_state(state)
    if not state_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungueltiger oder abgelaufener State",
        )

    # Code austauschen
    client_secret = decrypt_value(connection.client_secret_encrypted) or ""

    success = await auth_service.exchange_code(
        db=db,
        connection_id=connection.id,
        code=code,
        client_id=connection.client_id,
        client_secret=client_secret,
        redirect_uri=connection.redirect_uri,
        environment=connection.api_environment,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token-Austausch fehlgeschlagen",
        )

    return {"success": True, "message": "DATEV-Verbindung erfolgreich authentifiziert"}


@router.post(
    "/connections/{connection_id}/test",
)
async def test_connection(
    connection_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> JSONDict:
    """Testet die DATEV-Verbindung."""
    from app.services.datev.connect import DATEVConnector, DATEVConnectionConfig
    from app.core.encryption import decrypt_value

    result = await db.execute(
        select(models.DATEVConnection).where(
            and_(
                models.DATEVConnection.id == uuid.UUID(connection_id),
                models.DATEVConnection.company_id == current_user.company_id,
            )
        )
    )
    connection = result.scalar_one_or_none()

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verbindung nicht gefunden",
        )

    # Connector erstellen
    config = DATEVConnectionConfig(
        beraternummer=connection.beraternummer,
        mandantennummer=connection.mandantennummer,
        client_id=connection.client_id or "",
        client_secret=decrypt_value(connection.client_secret_encrypted) or "",
        access_token=decrypt_value(connection.access_token_encrypted) or "",
        token_expires_at=connection.token_expires_at,
        api_environment=connection.api_environment,
    )
    connector = DATEVConnector(config)

    success = await connector.test_connection()

    if success:
        connection.connection_status = "connected"
        connection.last_connection_at = utc_now()
        connection.last_error = None
    else:
        connection.connection_status = "error"
        connection.last_error = connector.last_error

    await db.commit()

    return {
        "success": success,
        "status": connection.connection_status,
        "error": connection.last_error,
    }


# =============================================================================
# Kontierungsvorschlag Endpoints
# =============================================================================

@router.post(
    "/connections/{connection_id}/suggest",
    response_model=KontierungResponse,
)
async def suggest_kontierung(
    connection_id: str,
    data: KontierungInput,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> KontierungResponse:
    """
    Generiert Kontierungsvorschlag fuer ein Dokument.

    Kombiniert regelbasierte und ML-gestuetzte Vorschlaege.
    """
    from app.services.datev.connect import get_kontierung_service
    from app.services.datev.connect.kontierung_service import KontierungsInput as KInput

    # Connection validieren
    result = await db.execute(
        select(models.DATEVConnection).where(
            and_(
                models.DATEVConnection.id == uuid.UUID(connection_id),
                models.DATEVConnection.company_id == current_user.company_id,
            )
        )
    )
    connection = result.scalar_one_or_none()

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verbindung nicht gefunden",
        )

    # Vorschlag generieren
    service = get_kontierung_service()
    input_data = KInput(
        entity_name=data.entity_name or "",
        entity_vat_id=data.entity_vat_id,
        betrag_brutto=data.betrag_brutto,
        mwst_satz=data.mwst_satz,
        dokument_typ=data.dokument_typ,
        richtung=data.richtung,
        stichwort=data.stichwort,
        document_id=uuid.UUID(data.document_id) if data.document_id else None,
        company_id=current_user.company_id,
    )

    suggestion = await service.suggest_kontierung(
        db=db,
        connection_id=connection.id,
        input_data=input_data,
    )

    return KontierungResponse(
        konto=suggestion.konto,
        gegenkonto=suggestion.gegenkonto,
        bu_schluessel=suggestion.bu_schluessel,
        kostenstelle=suggestion.kostenstelle,
        confidence=suggestion.confidence,
        source=suggestion.source,
        explanation=suggestion.explanation,
        alternatives=[a.to_dict() for a in suggestion.alternatives],
    )


# =============================================================================
# Buchungen Endpoints
# =============================================================================

@router.post(
    "/connections/{connection_id}/buchungen",
    response_model=BuchungResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_buchung(
    connection_id: str,
    data: BuchungCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> BuchungResponse:
    """Erstellt eine neue Buchung."""
    # Connection validieren
    result = await db.execute(
        select(models.DATEVConnection).where(
            and_(
                models.DATEVConnection.id == uuid.UUID(connection_id),
                models.DATEVConnection.company_id == current_user.company_id,
            )
        )
    )
    connection = result.scalar_one_or_none()

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verbindung nicht gefunden",
        )

    # Buchung erstellen
    buchung = models.DATEVBuchung(
        id=uuid.uuid4(),
        connection_id=connection.id,
        company_id=current_user.company_id,
        document_id=uuid.UUID(data.document_id) if data.document_id else None,
        umsatz=data.umsatz,
        soll_haben=data.soll_haben,
        konto=data.konto,
        gegenkonto=data.gegenkonto,
        bu_schluessel=data.bu_schluessel,
        belegdatum=data.belegdatum,
        belegfeld_1=data.belegfeld_1,
        buchungstext=data.buchungstext,
        kostenstelle_1=data.kostenstelle_1,
        buchungs_guid=str(uuid.uuid4()),
        sync_status="pending",
        ist_festgeschrieben=False,
        created_by=current_user.id,
    )

    db.add(buchung)
    await db.commit()
    await db.refresh(buchung)

    return BuchungResponse(
        id=str(buchung.id),
        buchungs_guid=buchung.buchungs_guid,
        umsatz=float(buchung.umsatz),
        soll_haben=buchung.soll_haben,
        konto=buchung.konto,
        gegenkonto=buchung.gegenkonto,
        bu_schluessel=buchung.bu_schluessel,
        belegdatum=buchung.belegdatum.isoformat(),
        belegfeld_1=buchung.belegfeld_1,
        buchungstext=buchung.buchungstext,
        sync_status=buchung.sync_status,
        ist_festgeschrieben=buchung.ist_festgeschrieben,
        created_at=buchung.created_at.isoformat(),
    )


@router.get(
    "/connections/{connection_id}/buchungen",
    response_model=List[BuchungResponse],
)
async def list_buchungen(
    connection_id: str,
    sync_status: Optional[str] = None,
    von: Optional[date] = None,
    bis: Optional[date] = None,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> List[BuchungResponse]:
    """Listet Buchungen einer Verbindung."""
    # Connection validieren
    result = await db.execute(
        select(models.DATEVConnection).where(
            and_(
                models.DATEVConnection.id == uuid.UUID(connection_id),
                models.DATEVConnection.company_id == current_user.company_id,
            )
        )
    )
    connection = result.scalar_one_or_none()

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verbindung nicht gefunden",
        )

    # Query aufbauen
    query = select(models.DATEVBuchung).where(
        models.DATEVBuchung.connection_id == connection.id,
    )

    if sync_status:
        query = query.where(models.DATEVBuchung.sync_status == sync_status)
    if von:
        query = query.where(models.DATEVBuchung.belegdatum >= von)
    if bis:
        query = query.where(models.DATEVBuchung.belegdatum <= bis)

    query = query.order_by(models.DATEVBuchung.belegdatum.desc())
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    buchungen = result.scalars().all()

    return [
        BuchungResponse(
            id=str(b.id),
            buchungs_guid=b.buchungs_guid,
            umsatz=float(b.umsatz),
            soll_haben=b.soll_haben,
            konto=b.konto,
            gegenkonto=b.gegenkonto,
            bu_schluessel=b.bu_schluessel,
            belegdatum=b.belegdatum.isoformat(),
            belegfeld_1=b.belegfeld_1,
            buchungstext=b.buchungstext,
            sync_status=b.sync_status,
            ist_festgeschrieben=b.ist_festgeschrieben,
            created_at=b.created_at.isoformat(),
        )
        for b in buchungen
    ]


# =============================================================================
# Sync Endpoints
# =============================================================================

@router.post(
    "/connections/{connection_id}/sync/stammdaten",
    response_model=SyncTriggerResponse,
)
async def trigger_stammdaten_sync(
    connection_id: str,
    entity_type: str = Query(default="all"),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> SyncTriggerResponse:
    """Triggert Stammdaten-Synchronisation."""
    from app.workers.tasks.datev_connect_tasks import sync_datev_stammdaten

    # Connection validieren
    result = await db.execute(
        select(models.DATEVConnection).where(
            and_(
                models.DATEVConnection.id == uuid.UUID(connection_id),
                models.DATEVConnection.company_id == current_user.company_id,
            )
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verbindung nicht gefunden",
        )

    # Task starten
    task = sync_datev_stammdaten.delay(connection_id, entity_type)

    return SyncTriggerResponse(
        task_id=task.id,
        message=f"Stammdaten-Sync fuer {entity_type} gestartet",
    )


@router.post(
    "/connections/{connection_id}/sync/buchungen",
    response_model=SyncTriggerResponse,
)
async def trigger_buchungen_push(
    connection_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> SyncTriggerResponse:
    """Triggert Buchungsstapel-Push zu DATEV."""
    from app.workers.tasks.datev_connect_tasks import push_datev_buchungsstapel

    # Connection validieren
    result = await db.execute(
        select(models.DATEVConnection).where(
            and_(
                models.DATEVConnection.id == uuid.UUID(connection_id),
                models.DATEVConnection.company_id == current_user.company_id,
            )
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verbindung nicht gefunden",
        )

    # Task starten
    task = push_datev_buchungsstapel.delay(connection_id)

    return SyncTriggerResponse(
        task_id=task.id,
        message="Buchungsstapel-Push gestartet",
    )


# =============================================================================
# GoBD Endpoints
# =============================================================================

@router.post(
    "/connections/{connection_id}/gobd/festschreiben",
    response_model=FestschreibungResponse,
)
async def festschreiben_buchungen(
    connection_id: str,
    data: FestschreibungRequest,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> FestschreibungResponse:
    """
    Schreibt Buchungen bis zum angegebenen Datum fest.

    ACHTUNG: Festgeschriebene Buchungen koennen nicht mehr geaendert werden!
    """
    from app.services.datev.connect import get_gobd_service

    # Connection validieren
    result = await db.execute(
        select(models.DATEVConnection).where(
            and_(
                models.DATEVConnection.id == uuid.UUID(connection_id),
                models.DATEVConnection.company_id == current_user.company_id,
            )
        )
    )
    connection = result.scalar_one_or_none()

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verbindung nicht gefunden",
        )

    if not connection.gobd_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GoBD ist fuer diese Verbindung nicht aktiviert",
        )

    # Festschreibung durchfuehren
    gobd_service = get_gobd_service()
    result = await gobd_service.festschreiben_buchungen(
        db=db,
        connection_id=connection.id,
        bis_datum=data.bis_datum,
        company_id=current_user.company_id,
    )

    return FestschreibungResponse(
        success=result.success,
        festschreibung_datum=result.festschreibung_datum.isoformat() if result.festschreibung_datum else None,
        buchungen_count=result.buchungen_count,
        fehler=result.fehler,
    )


@router.get(
    "/connections/{connection_id}/gobd/compliance",
    response_model=GoBDValidationResponse,
)
async def check_gobd_compliance(
    connection_id: str,
    von: Optional[date] = None,
    bis: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> GoBDValidationResponse:
    """
    Prueft GoBD-Compliance fuer eine Verbindung.

    Prueft Hash-Integritaet, Lueckenlosigkeit und Belegverknuepfungen.
    """
    from app.services.datev.connect import get_gobd_service

    # Connection validieren
    result = await db.execute(
        select(models.DATEVConnection).where(
            and_(
                models.DATEVConnection.id == uuid.UUID(connection_id),
                models.DATEVConnection.company_id == current_user.company_id,
            )
        )
    )
    connection = result.scalar_one_or_none()

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verbindung nicht gefunden",
        )

    # Compliance pruefen
    gobd_service = get_gobd_service()
    validation = await gobd_service.validate_gobd_compliance(
        db=db,
        connection_id=connection.id,
        pruefzeitraum_von=von,
        pruefzeitraum_bis=bis,
    )

    return GoBDValidationResponse(
        is_compliant=validation.is_compliant,
        pruefung_datum=validation.pruefung_datum.isoformat(),
        findings=validation.findings,
        statistics=validation.statistics,
    )


@router.get(
    "/connections/{connection_id}/gobd/verfahrensdokumentation",
)
async def export_verfahrensdokumentation(
    connection_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Exportiert Verfahrensdokumentation gemaess GoBD.

    Gibt JSON-Dokument mit Systembeschreibung zurueck.
    """
    from fastapi.responses import Response
    from app.services.datev.connect import get_gobd_service

    # Connection validieren
    result = await db.execute(
        select(models.DATEVConnection).where(
            and_(
                models.DATEVConnection.id == uuid.UUID(connection_id),
                models.DATEVConnection.company_id == current_user.company_id,
            )
        )
    )
    connection = result.scalar_one_or_none()

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verbindung nicht gefunden",
        )

    # Dokumentation exportieren
    gobd_service = get_gobd_service()
    doc_bytes = await gobd_service.export_verfahrensdokumentation(
        db=db,
        connection_id=connection.id,
    )

    return Response(
        content=doc_bytes,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="verfahrensdokumentation_{connection.mandantennummer}.json"',
        },
    )
