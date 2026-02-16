"""Banking FinTS API Endpoints.

FinTS/HBCI Direktverbindung und SEPA Credit Transfer API:
- FinTS Verbindung herstellen
- Kontoumsätze abrufen
- SEPA-Überweisungen (pain.001)
- TAN-Verfahren

SECURITY:
- PINs werden niemals gespeichert, nur temporaer verwendet
- TAN-Sessions haben kurze TTL (5 Minuten)
- Alle sensiblen Operationen werden geloggt (ohne Credentials!)
"""

from datetime import date
from decimal import Decimal
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.api.dependencies import get_db, get_current_active_user
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import User
from app.services.banking.fints_service import (
    fints_service,
    FinTSConnectionStatus,
    TANMethod,
    FinTSBankInfo,
    FinTSSyncResult,
)
from app.services.banking.sepa_credit_transfer_service import (
    sepa_credit_transfer_service,
    CreditTransferCreate,
    BatchTransferCreate,
    Pain001ExportResult,
)

logger = structlog.get_logger(__name__)

# ==================== Routers ====================

fints_router = APIRouter(prefix="/banking/fints", tags=["Banking - FinTS"])
sepa_router = APIRouter(prefix="/banking/sepa", tags=["Banking - SEPA"])
dashboard_router = APIRouter(prefix="/banking/dashboard", tags=["Banking - Dashboard"])


# ==================== Pydantic Models ====================


class FinTSConnectRequest(BaseModel):
    """Request zum Verbinden mit FinTS-Server."""
    account_id: UUID
    pin: str = Field(..., min_length=5, max_length=50)


class FinTSConnectResponse(BaseModel):
    """Response nach FinTS-Verbindungsversuch."""
    success: bool
    status: str
    tan_required: bool = False
    tan_challenge_id: Optional[str] = None
    tan_method: Optional[str] = None
    tan_challenge_text: Optional[str] = None
    expires_at: Optional[str] = None
    error_message: Optional[str] = None


class TANConfirmRequest(BaseModel):
    """Request zum Bestätigen einer TAN."""
    challenge_id: str
    tan: str = Field(..., min_length=4, max_length=10)


class FinTSSyncRequest(BaseModel):
    """Request für FinTS-Synchronisation."""
    account_id: UUID
    pin: str = Field(..., min_length=5, max_length=50)
    date_from: Optional[date] = None
    date_to: Optional[date] = None


class FinTSSyncResponse(BaseModel):
    """Response nach FinTS-Synchronisation."""
    success: bool
    account_iban: str
    transaction_count: int
    date_from: Optional[date]
    date_to: Optional[date]
    error_message: Optional[str] = None


class FinTSBalanceResponse(BaseModel):
    """Response für Kontostand-Abfrage."""
    success: bool
    balance: Optional[Decimal] = None
    currency: str = "EUR"
    balance_date: Optional[date] = None
    credit_line: Optional[Decimal] = None
    available_balance: Optional[Decimal] = None
    error_message: Optional[str] = None


class BankInfoResponse(BaseModel):
    """Bank-Informationen."""
    bank_name: str
    blz: str
    bic: Optional[str]
    fints_url: str
    supported_tan_methods: List[dict]


class TANMethodResponse(BaseModel):
    """TAN-Verfahren."""
    id: str
    name: str
    type: str
    description: str
    is_default: bool = False


class SEPATransferInitRequest(BaseModel):
    """Request für SEPA-Überweisung via FinTS."""
    account_id: UUID
    pin: str = Field(..., min_length=5, max_length=50)
    creditor_name: str = Field(..., min_length=1, max_length=70)
    creditor_iban: str = Field(..., min_length=15, max_length=34)
    creditor_bic: Optional[str] = Field(None, max_length=11)
    amount: Decimal = Field(..., gt=0)
    remittance_info: str = Field(..., min_length=1, max_length=140)
    execution_date: Optional[date] = None

    @field_validator("creditor_iban")
    @classmethod
    def normalize_iban(cls, v: str) -> str:
        return v.replace(" ", "").upper()


class MultiAccountBalanceResponse(BaseModel):
    """Aggregierte Kontostaende."""
    total_balance: Decimal
    currency: str = "EUR"
    accounts: List[dict]
    as_of: str


class CashFlowSummaryResponse(BaseModel):
    """Cash-Flow-Zusammenfassung."""
    current_balance: Decimal
    projected_7_days: Decimal
    projected_30_days: Decimal
    upcoming_payments: int
    upcoming_payments_amount: Decimal
    expected_income: int
    expected_income_amount: Decimal
    currency: str = "EUR"


# ==================== FinTS Endpoints ====================


@fints_router.get("/bank-info/{blz}", response_model=BankInfoResponse)
async def get_bank_info(
    blz: str,
    current_user: User = Depends(get_current_active_user),
):
    """Hole Bank-Informationen für eine BLZ.

    Gibt FinTS-URL und unterstützte TAN-Verfahren zurück.
    """
    if len(blz) != 8 or not blz.isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="BLZ muss 8 Ziffern lang sein",
        )

    bank_info = await fints_service.get_bank_info(blz)

    if not bank_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bank-Informationen für diese BLZ nicht gefunden. "
                   "Bitte FinTS-URL manuell eingeben.",
        )

    return BankInfoResponse(
        bank_name=bank_info.bank_name,
        blz=bank_info.blz,
        bic=bank_info.bic,
        fints_url=bank_info.fints_url,
        supported_tan_methods=bank_info.tan_methods,
    )


@fints_router.post("/connect", response_model=FinTSConnectResponse)
async def connect_fints(
    request: FinTSConnectRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Verbinde mit FinTS-Server.

    Initiiert die FinTS-Verbindung. Bei Erfolg wird typischerweise
    eine TAN angefordert, die mit /confirm-tan bestätigt werden muss.

    SECURITY: Die PIN wird nur temporaer verwendet und nie gespeichert!
    """
    success, tan_challenge, error = await fints_service.connect(
        db=db,
        account_id=request.account_id,
        user_id=current_user.id,
        pin=request.pin,  # Wird sofort verwendet und verworfen
    )

    if not success:
        return FinTSConnectResponse(
            success=False,
            status=FinTSConnectionStatus.ERROR.value,
            error_message=error,
        )

    if tan_challenge:
        return FinTSConnectResponse(
            success=True,
            status=FinTSConnectionStatus.AWAITING_TAN.value,
            tan_required=True,
            tan_challenge_id=tan_challenge.challenge_id,
            tan_method=tan_challenge.tan_method.value,
            tan_challenge_text=tan_challenge.challenge_text,
            expires_at=tan_challenge.expires_at.isoformat(),
        )

    return FinTSConnectResponse(
        success=True,
        status=FinTSConnectionStatus.CONNECTED.value,
    )


@fints_router.post("/confirm-tan")
async def confirm_tan(
    request: TANConfirmRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Bestätigt TAN-Challenge.

    Wird nach erfolgreicher TAN-Eingabe aufgerufen, um die
    FinTS-Session zu aktivieren.
    """
    success, error = await fints_service.confirm_tan(
        db=db,
        challenge_id=request.challenge_id,
        tan=request.tan,
        user_id=current_user.id,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error or "TAN-Bestätigung fehlgeschlagen",
        )

    return {
        "success": True,
        "message": "TAN erfolgreich bestätigt. Verbindung aktiv.",
    }


@fints_router.post("/sync", response_model=FinTSSyncResponse)
async def sync_transactions(
    request: FinTSSyncRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Synchronisiert Kontoumsätze via FinTS.

    Ruft Transaktionen für den angegebenen Zeitraum ab.
    Standard: letzte 90 Tage.

    SECURITY: Die PIN wird nur temporaer verwendet!
    """
    result = await fints_service.sync_transactions(
        db=db,
        account_id=request.account_id,
        user_id=current_user.id,
        pin=request.pin,
        date_from=request.date_from,
        date_to=request.date_to,
    )

    return FinTSSyncResponse(
        success=result.success,
        account_iban=result.account_iban,
        transaction_count=result.transaction_count,
        date_from=result.date_from,
        date_to=result.date_to,
        error_message=result.error_message,
    )


@fints_router.post("/balance", response_model=FinTSBalanceResponse)
async def get_balance(
    account_id: UUID,
    pin: str = Query(..., min_length=5, max_length=50),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Ruft aktuellen Kontostand via FinTS ab."""
    balance = await fints_service.get_balance(
        db=db,
        account_id=account_id,
        user_id=current_user.id,
        pin=pin,
    )

    if not balance:
        return FinTSBalanceResponse(
            success=False,
            error_message="Kontostand konnte nicht abgerufen werden",
        )

    return FinTSBalanceResponse(
        success=True,
        balance=balance.balance,
        currency=balance.currency,
        balance_date=balance.date,
        credit_line=balance.credit_line,
        available_balance=balance.available_balance,
    )


@fints_router.get("/tan-methods/{account_id}", response_model=List[TANMethodResponse])
async def get_tan_methods(
    account_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Gibt verfügbare TAN-Verfahren für ein Konto zurück."""
    methods = await fints_service.get_available_tan_methods(
        db=db,
        account_id=account_id,
        user_id=current_user.id,
    )

    return [
        TANMethodResponse(
            id=m["id"],
            name=m["name"],
            type=m["type"],
            description=m["description"],
            is_default=m.get("is_default", False),
        )
        for m in methods
    ]


@fints_router.post("/disconnect/{account_id}")
async def disconnect_fints(
    account_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Trennt FinTS-Verbindung."""
    success = await fints_service.disconnect(
        db=db,
        account_id=account_id,
        user_id=current_user.id,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verbindung konnte nicht getrennt werden",
        )

    return {"success": True, "message": "Verbindung getrennt"}


@fints_router.post("/transfer", response_model=FinTSConnectResponse)
async def initiate_transfer(
    request: SEPATransferInitRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Initiiert SEPA-Überweisung via FinTS.

    Erfordert TAN-Bestätigung für die Ausführung.
    """
    success, tan_challenge, error = await fints_service.initiate_sepa_transfer(
        db=db,
        account_id=request.account_id,
        user_id=current_user.id,
        pin=request.pin,
        beneficiary_name=request.creditor_name,
        beneficiary_iban=request.creditor_iban,
        beneficiary_bic=request.creditor_bic,
        amount=request.amount,
        reference=request.remittance_info,
        execution_date=request.execution_date,
    )

    if not success:
        return FinTSConnectResponse(
            success=False,
            status=FinTSConnectionStatus.ERROR.value,
            error_message=error,
        )

    if tan_challenge:
        return FinTSConnectResponse(
            success=True,
            status=FinTSConnectionStatus.AWAITING_TAN.value,
            tan_required=True,
            tan_challenge_id=tan_challenge.challenge_id,
            tan_method=tan_challenge.tan_method.value,
            tan_challenge_text=tan_challenge.challenge_text,
            expires_at=tan_challenge.expires_at.isoformat(),
        )

    return FinTSConnectResponse(
        success=True,
        status="submitted",
    )


# ==================== SEPA Endpoints ====================


@sepa_router.post("/credit-transfer", response_model=Pain001ExportResult)
async def create_credit_transfer(
    data: CreditTransferCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Erstellt pain.001 XML für SEPA-Überweisung.

    Generiert eine ISO 20022 konforme Datei, die:
    - Via FinTS gesendet werden kann
    - Manuell im Online-Banking hochgeladen werden kann
    - An einen Zahlungsdienstleister übermittelt werden kann
    """
    try:
        result = await sepa_credit_transfer_service.create_single_transfer(
            db=db,
            user_id=current_user.id,
            data=data,
        )
        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "SEPA-Überweisung"),
        )


@sepa_router.post("/batch-transfer", response_model=Pain001ExportResult)
async def create_batch_transfer(
    data: BatchTransferCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Erstellt pain.001 XML für Sammelüberweisung.

    Fasst mehrere Zahlungsaufträge in einer Datei zusammen.
    """
    try:
        result = await sepa_credit_transfer_service.create_batch_transfer(
            db=db,
            user_id=current_user.id,
            data=data,
        )
        await db.commit()
        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "SEPA-Sammelüberweisung"),
        )


@sepa_router.get("/payment-suggestions")
async def get_payment_suggestions(
    bank_account_id: UUID,
    include_skonto: bool = Query(True, description="Skonto-Rechnungen einschließen"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Holt Zahlungsvorschläge für fällige Rechnungen.

    Zeigt unbezahlte Eingangsrechnungen mit optionalen Skonto-Infos.
    """
    suggestions = await sepa_credit_transfer_service.get_payment_suggestions(
        db=db,
        user_id=current_user.id,
        bank_account_id=bank_account_id,
        include_with_skonto=include_skonto,
    )

    return {
        "bank_account_id": str(bank_account_id),
        "suggestions": suggestions,
        "total_count": len(suggestions),
    }


# ==================== Multi-Bank Dashboard Endpoints ====================


@dashboard_router.get("/balances", response_model=MultiAccountBalanceResponse)
async def get_multi_account_balances(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregierte Kontostaende aller Bankkonten.

    Zeigt Gesamtüberblick über alle verbundenen Konten.
    """
    from app.db.models import BankAccount
    from sqlalchemy import select, and_
    from app.core.datetime_utils import utc_now

    result = await db.execute(
        select(BankAccount).where(
            and_(
                BankAccount.user_id == current_user.id,
                BankAccount.is_active == True,
                BankAccount.deleted_at.is_(None),
            )
        ).order_by(BankAccount.account_name)
    )
    accounts = result.scalars().all()

    total = Decimal("0")
    account_list = []

    for acc in accounts:
        balance = acc.current_balance or Decimal("0")
        total += balance
        account_list.append({
            "id": str(acc.id),
            "name": acc.account_name,
            "iban": acc.iban,
            "bank_name": acc.bank_name,
            "balance": balance,
            "currency": acc.currency or "EUR",
            "balance_date": acc.balance_date.isoformat() if acc.balance_date else None,
            "connection_status": acc.connection_status or "manual",
            "last_sync_at": acc.last_sync_at.isoformat() if acc.last_sync_at else None,
        })

    return MultiAccountBalanceResponse(
        total_balance=total,
        currency="EUR",
        accounts=account_list,
        as_of=utc_now().isoformat(),
    )


@dashboard_router.get("/cashflow-summary", response_model=CashFlowSummaryResponse)
async def get_cashflow_summary(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Cash-Flow-Zusammenfassung für Dashboard.

    Zeigt aktuellen Stand und Prognose.
    """
    from app.db.models import BankAccount, PaymentOrder, InvoiceTracking
    from sqlalchemy import select, func, and_
    from datetime import timedelta
    from app.core.datetime_utils import utc_now

    # Hole Gesamtkontostand
    balance_result = await db.execute(
        select(func.sum(BankAccount.current_balance)).where(
            and_(
                BankAccount.user_id == current_user.id,
                BankAccount.is_active == True,
                BankAccount.deleted_at.is_(None),
            )
        )
    )
    current_balance = balance_result.scalar() or Decimal("0")

    # Hole ausstehende Zahlungen (nächste 30 Tage)
    today = date.today()
    in_30_days = today + timedelta(days=30)

    payment_result = await db.execute(
        select(
            func.count(PaymentOrder.id).label("count"),
            func.sum(PaymentOrder.amount).label("total"),
        ).where(
            and_(
                PaymentOrder.user_id == current_user.id,
                PaymentOrder.status.in_(["draft", "approved", "pending_approval"]),
                PaymentOrder.execution_date <= in_30_days,
            )
        )
    )
    payment_stats = payment_result.first()
    upcoming_payments = payment_stats.count or 0
    upcoming_amount = payment_stats.total or Decimal("0")

    # Hole erwartete Einnahmen aus offenen Forderungen (nächste 30 Tage)
    income_result = await db.execute(
        select(
            func.count(InvoiceTracking.id).label("count"),
            func.sum(InvoiceTracking.amount).label("total"),
        ).where(
            and_(
                InvoiceTracking.user_id == current_user.id,
                InvoiceTracking.status.in_(["pending", "overdue", "partial"]),
                InvoiceTracking.due_date <= in_30_days,
            )
        )
    )
    income_stats = income_result.first()
    expected_income_count = income_stats.count or 0
    expected_income_amount = income_stats.total or Decimal("0")

    # Verbesserte Prognose (mit erwarteten Einnahmen)
    projected_7 = current_balance - (upcoming_amount * Decimal("0.3")) + (expected_income_amount * Decimal("0.2"))
    projected_30 = current_balance - upcoming_amount + (expected_income_amount * Decimal("0.7"))

    return CashFlowSummaryResponse(
        current_balance=current_balance,
        projected_7_days=projected_7,
        projected_30_days=projected_30,
        upcoming_payments=upcoming_payments,
        upcoming_payments_amount=upcoming_amount,
        expected_income=expected_income_count,
        expected_income_amount=expected_income_amount,
        currency="EUR",
    )


@dashboard_router.get("/quick-stats")
async def get_quick_stats(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Schnelle Statistiken für Dashboard-Widgets."""
    from app.db.models import BankAccount, BankTransaction, PaymentOrder
    from sqlalchemy import select, func, and_
    from app.core.datetime_utils import utc_now
    from datetime import timedelta

    today = date.today()
    month_start = today.replace(day=1)

    # Konten zaehlen
    account_result = await db.execute(
        select(func.count(BankAccount.id)).where(
            and_(
                BankAccount.user_id == current_user.id,
                BankAccount.is_active == True,
                BankAccount.deleted_at.is_(None),
            )
        )
    )
    account_count = account_result.scalar() or 0

    # Transaktionen diesen Monat
    tx_result = await db.execute(
        select(
            func.count(BankTransaction.id).label("count"),
            func.sum(BankTransaction.amount).filter(BankTransaction.amount > 0).label("inflow"),
            func.sum(func.abs(BankTransaction.amount)).filter(BankTransaction.amount < 0).label("outflow"),
        ).join(BankAccount).where(
            and_(
                BankAccount.user_id == current_user.id,
                BankTransaction.booking_date >= month_start,
            )
        )
    )
    tx_stats = tx_result.first()

    # Nicht abgeglichene Transaktionen
    unmatched_result = await db.execute(
        select(func.count(BankTransaction.id)).join(BankAccount).where(
            and_(
                BankAccount.user_id == current_user.id,
                BankTransaction.reconciliation_status == "unmatched",
            )
        )
    )
    unmatched_count = unmatched_result.scalar() or 0

    return {
        "account_count": account_count,
        "transactions_this_month": tx_stats.count or 0,
        "inflow_this_month": tx_stats.inflow or Decimal("0"),
        "outflow_this_month": tx_stats.outflow or Decimal("0"),
        "unmatched_transactions": unmatched_count,
        "period": {
            "from": month_start.isoformat(),
            "to": today.isoformat(),
        },
    }


# Alle Router kombinieren
router = APIRouter()
router.include_router(fints_router)
router.include_router(sepa_router)
router.include_router(dashboard_router)
