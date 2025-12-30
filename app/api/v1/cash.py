"""
Cash API Endpoints - Kassenbuch.

GoBD-konforme Kassenbuchfuehrung:
- Kassen-CRUD (Register)
- Kassenbucheintraege (APPEND-ONLY!)
- Kassensturz (Zaehlung)
- Berichte und Zusammenfassungen

WICHTIG: CashEntry ist APPEND-ONLY gemaess GoBD!
- Keine PUT/PATCH/DELETE fuer Eintraege
- Stornierung nur durch Gegenbuchung

Alle Antworten auf Deutsch.
"""

from datetime import date, datetime
from typing import List, Optional
from uuid import UUID
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request, Header
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.api.dependencies import get_db, get_current_active_user
from app.core.rate_limiting import limiter, get_user_identifier
from app.core.security import build_content_disposition
from app.core.idempotency import check_idempotency, get_idempotency_service
from app.db.models import User, Company, CashRegister, CashEntry, CashCategory, CashCount
from app.db.schemas import (
    # Register
    CashRegisterCreate,
    CashRegisterUpdate,
    CashRegisterResponse,
    CashRegisterListResponse,
    # Entries
    CashEntryCreate,
    CashEntryResponse,
    CashEntryListResponse,
    CashEntryCancelRequest,
    # Categories
    CashCategoryCreate,
    CashCategoryResponse,
    # Cash Count
    CashCountCreate,
    CashCountResponse,
    CashCountListResponse,
    # Summaries
    CashBookSummary,
    DailySummary,
    # Enums
    CashEntryType,
)
from app.middleware.company_context import (
    require_company,
    require_cash_permission,
)
from app.services.cash_service import CashService

logger = structlog.get_logger(__name__)

# ==================== Routers ====================

registers_router = APIRouter(prefix="/cash/registers", tags=["Kassenbuch - Kassen"])
entries_router = APIRouter(prefix="/cash/entries", tags=["Kassenbuch - Eintraege"])
counts_router = APIRouter(prefix="/cash/counts", tags=["Kassenbuch - Kassensturz"])
reports_router = APIRouter(prefix="/cash", tags=["Kassenbuch - Berichte"])
categories_router = APIRouter(prefix="/cash/categories", tags=["Kassenbuch - Kategorien"])

# Service Instanz
cash_service = CashService()


# ==================== Register Endpoints ====================

@registers_router.get(
    "",
    response_model=CashRegisterListResponse,
    summary="Kassen auflisten",
    description="Gibt alle Kassen der aktuellen Firma zurueck."
)
async def list_registers(
    request: Request,
    skip: int = 0,
    limit: int = 50,
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> CashRegisterListResponse:
    """Liste aller Kassen."""

    registers, total = await cash_service.get_registers(
        db=db,
        company_id=company.id,
        skip=skip,
        limit=limit,
        include_inactive=include_inactive,
    )

    return CashRegisterListResponse(
        items=[
            CashRegisterResponse(
                id=r.id,
                company_id=r.company_id,
                name=r.name,
                description=r.description,
                current_balance=r.current_balance,
                currency=r.currency,
                is_active=r.is_active,
                is_default=r.is_default,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in registers
        ],
        total=total,
    )


@registers_router.post(
    "",
    response_model=CashRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Kasse erstellen",
    description="Erstellt eine neue Kasse fuer die aktuelle Firma."
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def create_register(
    data: CashRegisterCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_cash_permission),
) -> CashRegisterResponse:
    """Erstellt eine neue Kasse."""

    register = await cash_service.create_register(
        db=db,
        company_id=company.id,
        data=data,
        user_id=current_user.id,
    )

    return CashRegisterResponse(
        id=register.id,
        company_id=register.company_id,
        name=register.name,
        description=register.description,
        current_balance=register.current_balance,
        currency=register.currency,
        is_active=register.is_active,
        is_default=register.is_default,
        created_at=register.created_at,
        updated_at=register.updated_at,
    )


@registers_router.get(
    "/{register_id}",
    response_model=CashRegisterResponse,
    summary="Kasse abrufen",
    description="Gibt Details einer spezifischen Kasse zurueck."
)
async def get_register(
    register_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> CashRegisterResponse:
    """Gibt eine Kasse zurueck."""

    register = await cash_service.get_register(
        db=db,
        register_id=register_id,
        company_id=company.id,
    )

    if not register:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kasse nicht gefunden."
        )

    return CashRegisterResponse(
        id=register.id,
        company_id=register.company_id,
        name=register.name,
        description=register.description,
        current_balance=register.current_balance,
        currency=register.currency,
        is_active=register.is_active,
        is_default=register.is_default,
        created_at=register.created_at,
        updated_at=register.updated_at,
    )


@registers_router.put(
    "/{register_id}",
    response_model=CashRegisterResponse,
    summary="Kasse aktualisieren",
    description="Aktualisiert eine Kasse (nur Metadaten, nicht Saldo)."
)
async def update_register(
    register_id: UUID,
    data: CashRegisterUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_cash_permission),
) -> CashRegisterResponse:
    """Aktualisiert eine Kasse."""

    register = await cash_service.update_register(
        db=db,
        register_id=register_id,
        company_id=company.id,
        data=data,
    )

    if not register:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kasse nicht gefunden."
        )

    return CashRegisterResponse(
        id=register.id,
        company_id=register.company_id,
        name=register.name,
        description=register.description,
        current_balance=register.current_balance,
        currency=register.currency,
        is_active=register.is_active,
        is_default=register.is_default,
        created_at=register.created_at,
        updated_at=register.updated_at,
    )


# ==================== Entry Endpoints ====================
# WICHTIG: APPEND-ONLY! Keine Updates oder Deletes gemaess GoBD!

@entries_router.get(
    "",
    response_model=CashEntryListResponse,
    summary="Kassenbucheintraege auflisten",
    description="Gibt Kassenbucheintraege mit optionaler Filterung zurueck."
)
async def list_entries(
    request: Request,
    register_id: Optional[UUID] = Query(None, description="Filter nach Kasse"),
    start_date: Optional[date] = Query(None, description="Start-Datum (inklusiv)"),
    end_date: Optional[date] = Query(None, description="End-Datum (inklusiv)"),
    entry_type: Optional[CashEntryType] = Query(None, description="Filter nach Typ"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),  # Max 100 fuer Performance
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> CashEntryListResponse:
    """Liste der Kassenbucheintraege."""

    # Konvertiere skip/limit zu page/page_size fuer Service
    page = (skip // limit) + 1 if limit > 0 else 1
    page_size = limit

    entries, total = await cash_service.get_entries(
        db=db,
        company_id=company.id,
        register_id=register_id,
        start_date=start_date,
        end_date=end_date,
        entry_type=entry_type.value if entry_type else None,
        page=page,
        page_size=page_size,
    )

    # WICHTIG: 'entries' statt 'items' (Frontend erwartet 'entries')
    # WICHTIG: Mapping von DB-Feldnamen zu Frontend-Feldnamen!
    return CashEntryListResponse(
        entries=[
            CashEntryResponse(
                id=e.id,
                register_id=e.cash_register_id,  # Mapping: DB -> Frontend
                entry_number=e.entry_number,
                entry_date=e.entry_date,
                entry_type=e.entry_type,
                amount=float(e.amount) if e.amount else 0.0,
                net_amount=float(e.net_amount) if e.net_amount else None,
                tax_amount=float(e.tax_amount) if e.tax_amount else None,
                tax_rate=float(e.tax_rate) if e.tax_rate else None,
                balance_after=float(e.balance_after) if e.balance_after else 0.0,
                description=e.description or "",
                category_id=e.category_id,
                category_name=e.category.name if e.category else None,  # Aus Relationship
                receipt_number=e.reference_number,  # Mapping: DB -> Frontend
                counterparty=e.counterparty_name,  # Mapping: DB -> Frontend
                is_entertainment=bool(e.entertainment_data),  # Mapping
                entertainment_data=e.entertainment_data,
                is_cancelled=e.is_cancelled if e.is_cancelled is not None else False,
                # GoBD Audit-Trail: Storno-Referenzen korrekt mappen
                cancelled_by_id=getattr(e, 'cancelled_by_entry_id', None) if e.entry_type != CashEntryType.CANCELLATION.value else None,
                cancels_entry_id=getattr(e, 'cancelled_by_entry_id', None) if e.entry_type == CashEntryType.CANCELLATION.value else None,
                skr03_account=getattr(e, 'debit_account', None),  # Mapping: DB -> Frontend
                skr04_account=getattr(e, 'credit_account', None),  # Mapping: DB -> Frontend
                created_by_id=e.created_by_id,
                created_at=e.created_at,
            )
            for e in entries
        ],
        total=total,
    )


class DuplicateCheckRequest(BaseModel):
    """Request-Schema fuer Duplikat-Check."""
    register_id: UUID = Field(..., description="Kassen-ID")
    amount: float = Field(..., description="Betrag")
    entry_date: str = Field(..., description="Buchungsdatum (YYYY-MM-DD)")
    description: str = Field(..., description="Beschreibung")
    receipt_number: Optional[str] = Field(None, description="Belegnummer")


@reports_router.post(
    "/check-duplicate",
    summary="Duplikat-Check",
    description="Prueft ob eine aehnliche Buchung bereits existiert (UX-Verbesserung)."
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def check_duplicate(
    request: Request,
    data: DuplicateCheckRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> dict:
    """Prueft auf moegliche Duplikate vor Buchungserstellung.

    Akzeptiert JSON-Body mit register_id, amount, entry_date, description, receipt_number.
    """
    from decimal import Decimal
    from datetime import datetime

    # Parse entry_date
    try:
        entry_date_parsed = datetime.strptime(data.entry_date, "%Y-%m-%d").date()
    except ValueError:
        entry_date_parsed = datetime.fromisoformat(data.entry_date.replace("Z", "+00:00")).date()

    duplicate = await cash_service.check_duplicate(
        db=db,
        register_id=data.register_id,
        company_id=company.id,
        amount=Decimal(str(data.amount)),
        entry_date=entry_date_parsed,
        description=data.description,
        reference_number=data.receipt_number,
    )

    if duplicate:
        return {
            "is_duplicate": True,
            "existing_entry": {
                "id": str(duplicate.id),
                "entry_number": duplicate.entry_number,
                "entry_date": duplicate.entry_date.isoformat() if duplicate.entry_date else None,
                "amount": float(duplicate.amount),
                "description": duplicate.description,
                "created_at": duplicate.created_at.isoformat() if duplicate.created_at else None,
            },
            "message": "Moegliches Duplikat gefunden: Gleicher Betrag und Datum mit aehnlicher Beschreibung."
        }

    return {"is_duplicate": False, "existing_entry": None, "message": None}


@entries_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Kassenbucheintrag erstellen",
    description="Erstellt einen neuen Kassenbucheintrag. "
                "APPEND-ONLY: Eintraege koennen nicht geaendert werden! "
                "Unterstuetzt Idempotency-Key Header fuer Netzwerk-Resilience.",
    responses={201: {"model": CashEntryResponse}}
)
@limiter.limit("10/minute", key_func=get_user_identifier)  # SECURITY FIX 30: Reduced from 30 to 10 for GoBD compliance
async def create_entry(
    data: CashEntryCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_cash_permission),
    cached_response: Optional[dict] = Depends(check_idempotency),
) -> JSONResponse:
    """Erstellt einen neuen Kassenbucheintrag.

    Unterstuetzt Idempotency-Key Header:
    - Senden Sie 'Idempotency-Key: <unique-id>' im Header
    - Bei Netzwerkfehler kann der gleiche Request wiederholt werden
    - Das gleiche Ergebnis wird zurueckgegeben (kein Duplikat)
    """
    # Idempotency: Bereits verarbeiteter Request
    if cached_response:
        return JSONResponse(
            content=cached_response["response"],
            status_code=cached_response["status_code"]
        )

    # Idempotency: Lock erwerben falls Key vorhanden
    idempotency_key = getattr(request.state, "idempotency_key", None)
    user_id = getattr(request.state, "idempotency_user_id", None)
    idempotency_service = get_idempotency_service()

    if idempotency_key:
        if not await idempotency_service.acquire_lock(idempotency_key, user_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Request mit diesem Idempotency-Key wird bereits verarbeitet"
            )

    try:
        entry = await cash_service.create_entry(
            db=db,
            company_id=company.id,
            data=data,
            user_id=current_user.id,
        )
    except ValueError as e:
        # Lock freigeben bei Fehler
        if idempotency_key:
            await idempotency_service.release_lock(idempotency_key, user_id)
        # SECURITY FIX 28-21: Generische Fehlermeldung
        logger.warning("cash_entry_create_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungueltige Kassenbucheingabe. Bitte Eingaben pruefen."
        )

    # Kategorie-Name aus Entry-Relationship (Eager Loading im Service)
    # Kein separater Query noetig - N+1 Fix!
    category_name = entry.category.name if entry.category else None

    # WICHTIG: Mapping von DB-Feldnamen zu Frontend-Feldnamen!
    # DB-Model verwendet: cash_register_id, reference_number, counterparty_name,
    #                     cancelled_by_entry_id, debit_account, credit_account
    # Frontend erwartet: register_id, receipt_number, counterparty,
    #                    cancelled_by_id, skr03_account, skr04_account
    response = CashEntryResponse(
        id=entry.id,
        register_id=entry.cash_register_id,  # Mapping: DB -> Frontend
        entry_number=entry.entry_number,
        entry_date=entry.entry_date,
        entry_type=CashEntryType(entry.entry_type),
        amount=float(entry.amount) if entry.amount else 0.0,
        net_amount=float(entry.net_amount) if entry.net_amount else None,
        tax_amount=float(entry.tax_amount) if entry.tax_amount else None,
        tax_rate=float(entry.tax_rate) if entry.tax_rate else None,
        balance_after=float(entry.balance_after) if entry.balance_after else 0.0,
        description=entry.description,
        category_id=entry.category_id,
        category_name=category_name,
        receipt_number=entry.reference_number,  # Mapping: DB -> Frontend
        counterparty=entry.counterparty_name,  # Mapping: DB -> Frontend
        is_entertainment=bool(entry.entertainment_data),  # Mapping: abgeleitet aus entertainment_data
        entertainment_data=entry.entertainment_data,
        is_cancelled=entry.is_cancelled if entry.is_cancelled is not None else False,
        # GoBD Audit-Trail: Semantisch korrekte Storno-Referenzen
        cancelled_by_id=entry.cancelled_by_entry_id if entry.entry_type != CashEntryType.CANCELLATION.value else None,
        cancels_entry_id=entry.cancelled_by_entry_id if entry.entry_type == CashEntryType.CANCELLATION.value else None,
        skr03_account=entry.debit_account,  # Mapping: DB -> Frontend
        skr04_account=entry.credit_account,  # Mapping: DB -> Frontend
        created_by_id=entry.created_by_id,
        created_at=entry.created_at,
    )

    # Idempotency: Response cachen und Lock freigeben
    response_data = response.model_dump(mode="json")
    if idempotency_key:
        await idempotency_service.cache_response(
            idempotency_key=idempotency_key,
            response_data=response_data,
            status_code=201,
            user_id=user_id,
            ttl=3600,  # 1 Stunde Cache
        )
        await idempotency_service.release_lock(idempotency_key, user_id)

    return JSONResponse(content=response_data, status_code=201)


@entries_router.post(
    "/{entry_id}/cancel",
    response_model=CashEntryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Kassenbucheintrag stornieren",
    description="Storniert einen Eintrag durch Gegenbuchung. "
                "Der Original-Eintrag wird als storniert markiert."
)
@limiter.limit("10/minute", key_func=get_user_identifier)  # Rate Limit: Max 10 Stornos/Minute
async def cancel_entry(
    entry_id: UUID,
    data: CashEntryCancelRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_cash_permission),
) -> CashEntryResponse:
    """Storniert einen Kassenbucheintrag."""

    try:
        cancellation_entry = await cash_service.cancel_entry(
            db=db,
            entry_id=entry_id,
            company_id=company.id,
            data=data,
            user_id=current_user.id,
        )
    except ValueError as e:
        # SECURITY FIX 28-21: Generische Fehlermeldung
        logger.warning("cash_entry_cancel_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stornierung fehlgeschlagen. Bitte Eingaben pruefen."
        )

    # Kategorie-Name aus Eager Loading (N+1 Fix!)
    category_name = cancellation_entry.category.name if cancellation_entry.category else None

    # WICHTIG: Mapping von DB-Feldnamen zu Frontend-Feldnamen!
    return CashEntryResponse(
        id=cancellation_entry.id,
        register_id=cancellation_entry.cash_register_id,  # Mapping: DB -> Frontend
        entry_number=cancellation_entry.entry_number,
        entry_date=cancellation_entry.entry_date,
        entry_type=CashEntryType(cancellation_entry.entry_type),
        amount=float(cancellation_entry.amount) if cancellation_entry.amount else 0.0,
        net_amount=float(cancellation_entry.net_amount) if cancellation_entry.net_amount else None,
        tax_amount=float(cancellation_entry.tax_amount) if cancellation_entry.tax_amount else None,
        tax_rate=float(cancellation_entry.tax_rate) if cancellation_entry.tax_rate else None,
        balance_after=float(cancellation_entry.balance_after) if cancellation_entry.balance_after else 0.0,
        description=cancellation_entry.description,
        category_id=cancellation_entry.category_id,
        category_name=category_name,
        receipt_number=cancellation_entry.reference_number,  # Mapping: DB -> Frontend
        counterparty=cancellation_entry.counterparty_name,  # Mapping: DB -> Frontend
        is_entertainment=bool(cancellation_entry.entertainment_data),  # Mapping
        entertainment_data=cancellation_entry.entertainment_data,
        is_cancelled=cancellation_entry.is_cancelled,
        cancelled_by_id=None,  # Stornobuchung selbst ist nicht storniert
        cancels_entry_id=cancellation_entry.cancelled_by_entry_id,  # Diese Buchung storniert das Original
        skr03_account=cancellation_entry.debit_account,  # Mapping: DB -> Frontend
        skr04_account=cancellation_entry.credit_account,  # Mapping: DB -> Frontend
        created_by_id=cancellation_entry.created_by_id,
        created_at=cancellation_entry.created_at,
    )


@entries_router.get(
    "/{entry_id}",
    response_model=CashEntryResponse,
    summary="Kassenbucheintrag abrufen",
    description="Gibt Details eines spezifischen Eintrags zurueck."
)
async def get_entry(
    entry_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> CashEntryResponse:
    """Gibt einen Kassenbucheintrag zurueck."""

    entry = await cash_service.get_entry(
        db=db,
        entry_id=entry_id,
        company_id=company.id,
    )

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kassenbucheintrag nicht gefunden."
        )

    # Kategorie-Name aus Eager Loading (N+1 Fix!)
    # Der Service nutzt bereits selectinload(CashEntry.category)
    category_name = entry.category.name if entry.category else None

    # WICHTIG: Mapping von DB-Feldnamen zu Frontend-Feldnamen!
    return CashEntryResponse(
        id=entry.id,
        register_id=entry.cash_register_id,  # Mapping: DB -> Frontend
        entry_number=entry.entry_number,
        entry_date=entry.entry_date,
        entry_type=CashEntryType(entry.entry_type),
        amount=float(entry.amount) if entry.amount else 0.0,
        net_amount=float(entry.net_amount) if entry.net_amount else None,
        tax_amount=float(entry.tax_amount) if entry.tax_amount else None,
        tax_rate=float(entry.tax_rate) if entry.tax_rate else None,
        balance_after=float(entry.balance_after) if entry.balance_after else 0.0,
        description=entry.description,
        category_id=entry.category_id,
        category_name=category_name,
        receipt_number=entry.reference_number,  # Mapping: DB -> Frontend
        counterparty=entry.counterparty_name,  # Mapping: DB -> Frontend
        is_entertainment=bool(entry.entertainment_data),  # Mapping
        entertainment_data=entry.entertainment_data,
        is_cancelled=entry.is_cancelled if entry.is_cancelled is not None else False,
        # GoBD Audit-Trail: Semantisch korrekte Storno-Referenzen
        cancelled_by_id=entry.cancelled_by_entry_id if entry.entry_type != CashEntryType.CANCELLATION.value else None,
        cancels_entry_id=entry.cancelled_by_entry_id if entry.entry_type == CashEntryType.CANCELLATION.value else None,
        skr03_account=entry.debit_account,  # Mapping: DB -> Frontend
        skr04_account=entry.credit_account,  # Mapping: DB -> Frontend
        created_by_id=entry.created_by_id,
        created_at=entry.created_at,
    )


# ==================== Cash Count Endpoints ====================

@counts_router.get(
    "",
    response_model=CashCountListResponse,
    summary="Kassensturz-Protokolle auflisten",
    description="Gibt alle Kassensturz-Protokolle zurueck."
)
async def list_cash_counts(
    request: Request,
    register_id: Optional[UUID] = Query(None, description="Filter nach Kasse"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),  # Max 100 fuer Performance
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> CashCountListResponse:
    """Liste der Kassensturz-Protokolle."""

    counts, total = await cash_service.get_counts(
        db=db,
        company_id=company.id,
        register_id=register_id,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=limit,
    )

    return CashCountListResponse(
        counts=[CashCountResponse.model_validate(c) for c in counts],
        total=total,
    )


@counts_router.post(
    "",
    response_model=CashCountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Kassensturz durchfuehren",
    description="Fuehrt einen Kassensturz durch. "
                "Bei Differenz wird automatisch eine Ausgleichsbuchung erstellt."
)
@limiter.limit("5/minute", key_func=get_user_identifier)
async def perform_cash_count(
    data: CashCountCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_cash_permission),
) -> CashCountResponse:
    """Fuehrt einen Kassensturz durch."""

    try:
        cash_count = await cash_service.perform_cash_count(
            db=db,
            company_id=company.id,
            data=data,
            user_id=current_user.id,
        )
    except ValueError as e:
        # SECURITY FIX 28-21: Generische Fehlermeldung
        logger.warning("cash_count_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kassensturz fehlgeschlagen. Bitte Eingaben pruefen."
        )

    return CashCountResponse.model_validate(cash_count)


# ==================== Report Endpoints ====================

@reports_router.get(
    "/summary",
    response_model=CashBookSummary,
    summary="Kassenbuch-Zusammenfassung",
    description="Gibt eine Zusammenfassung des Kassenbuchs fuer einen Zeitraum zurueck."
)
async def get_cash_summary(
    request: Request,
    register_id: UUID = Query(..., description="Kassen-ID"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> CashBookSummary:
    """Gibt Kassenbuch-Zusammenfassung zurueck."""

    summary = await cash_service.get_summary(
        db=db,
        company_id=company.id,
        register_id=register_id,
        start_date=start_date,
        end_date=end_date,
    )

    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kasse nicht gefunden."
        )

    return summary


@reports_router.get(
    "/daily",
    response_model=List[DailySummary],
    summary="Tagesabschluesse",
    description="Gibt Tagesabschluesse fuer einen Zeitraum zurueck."
)
async def get_daily_summaries(
    request: Request,
    register_id: UUID = Query(..., description="Kassen-ID"),
    start_date: date = Query(..., description="Start-Datum"),
    end_date: date = Query(..., description="End-Datum"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> List[DailySummary]:
    """Gibt Tagesabschluesse zurueck."""

    summaries = await cash_service.get_daily_summaries(
        db=db,
        company_id=company.id,
        register_id=register_id,
        start_date=start_date,
        end_date=end_date,
    )

    return summaries


# ==================== Category Endpoints ====================

@categories_router.get(
    "",
    response_model=List[CashCategoryResponse],
    summary="Kategorien auflisten",
    description="Gibt alle Kassenbuch-Kategorien der Firma zurueck."
)
async def list_categories(
    request: Request,
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> List[CashCategoryResponse]:
    """Liste der Kategorien."""

    categories = await cash_service.get_categories(
        db=db,
        company_id=company.id,
        active_only=not include_inactive,
    )

    return [
        CashCategoryResponse(
            id=c.id,
            company_id=c.company_id,
            name=c.name,
            description=c.description,
            skr03_account=c.skr03_account,
            skr04_account=c.skr04_account,
            default_tax_rate=c.default_tax_rate,
            is_entertainment=c.is_entertainment,
            is_system=c.is_system,
            is_active=c.is_active,
            level=c.level,
            path=c.path,
            category_type=c.category_type,
            allows_vat_deduction=c.allows_vat_deduction,
            sort_order=c.sort_order,
            created_at=c.created_at,
        )
        for c in categories
    ]


@categories_router.post(
    "",
    response_model=CashCategoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Kategorie erstellen",
    description="Erstellt eine neue Kassenbuch-Kategorie."
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def create_category(
    data: CashCategoryCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_cash_permission),
) -> CashCategoryResponse:
    """Erstellt eine neue Kategorie."""

    category = await cash_service.create_category(
        db=db,
        company_id=company.id,
        data=data,
    )

    return CashCategoryResponse(
        id=category.id,
        company_id=category.company_id,
        name=category.name,
        description=category.description,
        skr03_account=category.skr03_account,
        skr04_account=category.skr04_account,
        default_tax_rate=category.default_tax_rate,
        is_entertainment=category.is_entertainment,
        is_system=category.is_system,
        is_active=category.is_active,
        level=category.level,
        path=category.path,
        category_type=category.category_type,
        allows_vat_deduction=category.allows_vat_deduction,
        sort_order=category.sort_order,
        created_at=category.created_at,
    )


# ==================== Export Router ====================

exports_router = APIRouter(prefix="/cash/export", tags=["Kassenbuch - Export"])


@exports_router.get(
    "/csv",
    summary="CSV Export",
    description="Exportiert das Kassenbuch als CSV-Datei (Semikolon-getrennt, UTF-8 mit BOM)."
)
async def export_csv(
    request: Request,
    register_id: UUID = Query(..., description="Kassen-ID"),
    start_date: date = Query(..., description="Start-Datum"),
    end_date: date = Query(..., description="End-Datum"),
    include_cancelled: bool = Query(False, description="Stornierte einschliessen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_cash_permission),  # SECURITY: Kassenbuch-Berechtigung erforderlich!
) -> StreamingResponse:
    """Exportiert Kassenbuch als CSV."""
    import io

    # Eintraege laden (alle ohne Pagination)
    entries, _ = await cash_service.get_entries(
        db=db,
        company_id=company.id,
        register_id=register_id,
        start_date=start_date,
        end_date=end_date,
        include_cancelled=include_cancelled,
        page=1,
        page_size=10000,  # Alle
    )

    # CSV erstellen (UTF-8 mit BOM fuer Excel)
    output = io.StringIO()
    output.write("\ufeff")  # BOM fuer Excel UTF-8 Erkennung

    # Header
    output.write(
        "Beleg-Nr;Datum;Wertstellung;Buchungstyp;Beschreibung;"
        "Betrag;Saldo;MwSt-Satz;Kategorie;Kostenstelle;Geschaeftspartner;"
        "Storniert;Storno-Grund\n"
    )

    # Zeilen
    for entry in entries:
        category_name = entry.category.name if entry.category else ""
        storniert = "Ja" if entry.is_cancelled else "Nein"
        storno_grund = entry.cancellation_reason or ""

        line = (
            f"{entry.entry_number};{entry.entry_date.strftime('%d.%m.%Y')};"
            f"{entry.value_date.strftime('%d.%m.%Y') if entry.value_date else ''};"
            f"{entry.entry_type};{entry.description};"
            f"{entry.amount:.2f};{entry.balance_after:.2f};"
            f"{entry.tax_rate or ''}%;{category_name};"
            f"{entry.cost_center or ''};{entry.counterparty_name or ''};"
            f"{storniert};{storno_grund}\n"
        )
        output.write(line)

    output.seek(0)

    # Register-Name fuer Dateiname (mit Firma-Validierung!)
    register = await cash_service.get_register(db, register_id, company.id)
    if not register:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kasse nicht gefunden oder kein Zugriff."
        )
    register_name = register.name.replace(" ", "_")

    filename = f"kassenbuch_{register_name}_{start_date}_{end_date}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        # SECURITY: Use sanitized Content-Disposition (Phase 10)
        headers={"Content-Disposition": build_content_disposition(filename, "attachment")}
    )


@exports_router.get(
    "/pdf",
    summary="PDF Report",
    description="Erstellt einen druckbaren PDF-Kassenbericht."
)
async def export_pdf(
    request: Request,
    register_id: UUID = Query(..., description="Kassen-ID"),
    start_date: date = Query(..., description="Start-Datum"),
    end_date: date = Query(..., description="End-Datum"),
    include_cancelled: bool = Query(False, description="Stornierte einschliessen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_cash_permission),  # SECURITY: Kassenbuch-Berechtigung erforderlich!
) -> StreamingResponse:
    """Erstellt PDF-Kassenbericht."""
    import io
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    # Eintraege laden
    entries, total = await cash_service.get_entries(
        db=db,
        company_id=company.id,
        register_id=register_id,
        start_date=start_date,
        end_date=end_date,
        include_cancelled=include_cancelled,
        page=1,
        page_size=10000,
    )

    # Register und Summary laden (mit Firma-Validierung!)
    register = await cash_service.get_register(db, register_id, company.id)
    if not register:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kasse nicht gefunden oder kein Zugriff."
        )
    summary = await cash_service.get_summary(
        db=db,
        company_id=company.id,
        register_id=register_id,
        start_date=start_date,
        end_date=end_date,
    )

    # PDF erstellen
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=20,
    )
    subtitle_style = ParagraphStyle(
        "CustomSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        spaceAfter=10,
    )

    elements = []

    # Titel
    register_name = register.name if register else "Kasse"
    elements.append(Paragraph(f"Kassenbuch: {register_name}", title_style))
    elements.append(
        Paragraph(
            f"Zeitraum: {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}",
            subtitle_style,
        )
    )
    elements.append(
        Paragraph(f"Firma: {company.name}", subtitle_style)
    )
    elements.append(Spacer(1, 0.5 * cm))

    # Zusammenfassung
    if summary:
        summary_data = [
            ["Kennzahl", "Betrag"],
            ["Anfangsbestand", f"{summary.opening_balance:.2f} EUR"],
            ["Einnahmen", f"{summary.total_income:.2f} EUR"],
            ["Ausgaben", f"{summary.total_expense:.2f} EUR"],
            ["Endbestand", f"{summary.closing_balance:.2f} EUR"],
            ["Buchungen", str(summary.entry_count)],
        ]
        summary_table = Table(summary_data, colWidths=[8 * cm, 6 * cm])
        summary_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 1 * cm))

    # Buchungstabelle
    if entries:
        elements.append(Paragraph("Buchungen", styles["Heading2"]))
        elements.append(Spacer(1, 0.3 * cm))

        table_data = [["Nr.", "Datum", "Beschreibung", "Betrag", "Saldo"]]
        for entry in entries:
            table_data.append([
                str(entry.entry_number),
                entry.entry_date.strftime("%d.%m.%Y"),
                entry.description[:40] + ("..." if len(entry.description) > 40 else ""),
                f"{entry.amount:.2f}",
                f"{entry.balance_after:.2f}",
            ])

        col_widths = [1.2 * cm, 2.5 * cm, 9 * cm, 2.5 * cm, 2.5 * cm]
        table = Table(table_data, colWidths=col_widths)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("ALIGN", (3, 0), (4, -1), "RIGHT"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
        ]))
        elements.append(table)

    # PDF generieren
    doc.build(elements)
    buffer.seek(0)

    register_slug = register_name.replace(" ", "_")
    filename = f"Kassenbuch_{register_slug}_{start_date}_{end_date}.pdf"

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="application/pdf",
        # SECURITY: Use sanitized Content-Disposition (Phase 10)
        headers={"Content-Disposition": build_content_disposition(filename, "attachment")}
    )


@exports_router.get(
    "/datev",
    summary="DATEV Export",
    description="Exportiert das Kassenbuch im DATEV-Format fuer den Steuerberater."
)
async def export_datev(
    request: Request,
    register_id: UUID = Query(..., description="Kassen-ID"),
    start_date: date = Query(..., description="Start-Datum"),
    end_date: date = Query(..., description="End-Datum"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_cash_permission),  # SECURITY: Kassenbuch-Berechtigung erforderlich!
) -> StreamingResponse:
    """Exportiert Kassenbuch im DATEV-Format.

    DATEV Buchungsstapel Format:
    - Semikolon-getrennt
    - Encoding: Windows-1252 (ANSI)
    - Pflichtfelder: Umsatz, Soll/Haben, Konto, Gegenkonto, BU-Schluessel, Datum, Buchungstext
    """
    import io

    # Eintraege laden (INKL. Stornierungen fuer GoBD-Compliance!)
    # GoBD erfordert lueckenlose Dokumentation aller Geschaeftsvorfaelle
    entries, _ = await cash_service.get_entries(
        db=db,
        company_id=company.id,
        register_id=register_id,
        start_date=start_date,
        end_date=end_date,
        include_cancelled=True,  # GoBD: Stornierungen MUESSEN dokumentiert werden!
        page=1,
        page_size=10000,
    )

    # DATEV Header (vereinfacht - vollstaendiger DATEV-Header ist komplexer)
    output = io.StringIO()

    # Kopfzeile (DATEV Buchungsstapel Format)
    output.write(
        "Umsatz (ohne Soll/Haben-Kz);Soll/Haben-Kennzeichen;WKZ Umsatz;Kurs;"
        "Basis-Umsatz;WKZ Basis-Umsatz;Konto;Gegenkonto (ohne BU-Schluessel);"
        "BU-Schluessel;Belegdatum;Belegfeld 1;Belegfeld 2;Skonto;Buchungstext;"
        "Postensperre;Diverse Adressnummer;Geschaeftspartnerbank;Sachverhalt;"
        "Zinssperre;Beleglink;Beleginfo - Art 1;Beleginfo - Inhalt 1\n"
    )

    # Konto fuer Kasse - dynamisch nach Kontenrahmen
    kontenrahmen = getattr(company, "kontenrahmen", "SKR03") or "SKR03"
    if kontenrahmen == "SKR04":
        kassa_konto = "1600"
        default_einnahme = "4400"
        default_ausgabe = "5000"
    else:  # SKR03 (Default)
        kassa_konto = "1000"
        default_einnahme = "8400"
        default_ausgabe = "4000"

    for entry in entries:
        # Betrag ohne Vorzeichen
        betrag = abs(entry.amount)

        # S/H Kennzeichen: S=Soll (Ausgabe), H=Haben (Einnahme)
        # Bei Kassenbuch: Einnahme = Haben auf Kasse, Ausgabe = Soll auf Kasse
        if entry.amount > 0:
            sh_kz = "H"  # Einnahme
            # Gegenkonto aus Kategorie (SKR03 oder SKR04 je nach Kontenrahmen)
            if entry.category:
                if kontenrahmen == "SKR04":
                    gegenkonto = entry.category.skr04_account or entry.category.skr03_account or default_einnahme
                else:
                    gegenkonto = entry.category.skr03_account or default_einnahme
            else:
                gegenkonto = default_einnahme
        else:
            sh_kz = "S"  # Ausgabe
            if entry.category:
                if kontenrahmen == "SKR04":
                    gegenkonto = entry.category.skr04_account or entry.category.skr03_account or default_ausgabe
                else:
                    gegenkonto = entry.category.skr03_account or default_ausgabe
            else:
                gegenkonto = default_ausgabe

        # BU-Schluessel fuer MwSt
        bu_schluessel = ""
        if entry.tax_rate:
            if entry.tax_rate == 19:
                bu_schluessel = "9"  # 19% Vorsteuer
            elif entry.tax_rate == 7:
                bu_schluessel = "8"  # 7% Vorsteuer

        # Datum im DATEV-Format (TTMM)
        datum = entry.entry_date.strftime("%d%m")

        # Buchungstext (max 60 Zeichen)
        buchungstext = entry.description[:60]

        line = (
            f'{betrag:.2f};{sh_kz};;;;;;;{kassa_konto};{gegenkonto};'
            f'{bu_schluessel};{datum};{entry.entry_number};;0,00;{buchungstext};'
            f'0;;;0;;;\n'
        )
        output.write(line)

    output.seek(0)

    # In Windows-1252 konvertieren fuer DATEV-Kompatibilitaet
    try:
        content_bytes = output.getvalue().encode("cp1252", errors="replace")
    except Exception:
        content_bytes = output.getvalue().encode("utf-8")

    # Register-Name fuer Dateiname (mit Firma-Validierung!)
    register = await cash_service.get_register(db, register_id, company.id)
    if not register:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kasse nicht gefunden oder kein Zugriff."
        )
    register_name = register.name.replace(" ", "_")
    filename = f"DATEV_Kasse_{register_name}_{start_date}_{end_date}.csv"

    return StreamingResponse(
        iter([content_bytes]),
        media_type="text/csv; charset=windows-1252",
        # SECURITY: Use sanitized Content-Disposition (Phase 10)
        headers={"Content-Disposition": build_content_disposition(filename, "attachment")}
    )


# ==================== Combined Router ====================

router = APIRouter()
router.include_router(registers_router)
router.include_router(entries_router)
router.include_router(counts_router)
router.include_router(reports_router)
router.include_router(categories_router)
router.include_router(exports_router)
