# -*- coding: utf-8 -*-
"""
Banking Connections API - PSD2/FinTS Integration.

Endpoints for:
- Bank discovery and connection management
- PSD2 OAuth2 consent flow
- FinTS PIN/TAN authentication
- Account synchronization
- Transaction reconciliation
- Payment initiation

SECURITY:
- All endpoints require authentication
- Company isolation enforced
- Never log sensitive data (IBANs, balances)
- Audit all operations
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.db.models import User
from app.db.models_banking_connection import (
    ConnectionType,
    ConnectionStatus,
    PaymentInitiationStatus,
)
from app.services.banking.account_connection_service import (
    AccountConnectionService,
    get_account_connection_service,
)
from app.services.banking.auto_transaction_import_service import (
    AutoTransactionImportService,
    get_auto_transaction_import_service,
)
from app.services.banking.payment_initiation_service import (
    PaymentInitiationService,
    PaymentRequest,
    get_payment_initiation_service,
)
from app.services.banking.auto_reconciliation_service import (
    AutoReconciliationService,
    get_auto_reconciliation_service,
)

router = APIRouter(prefix="/banking", tags=["Banking Integration"])


# =============================================================================
# Schemas
# =============================================================================

class BankInfoResponse(BaseModel):
    """Bank information."""
    bank_code: str
    bank_name: str
    bic: Optional[str] = None
    supports_psd2: bool = False
    supports_fints: bool = False
    logo_url: Optional[str] = None
    supports_payment_initiation: bool = False


class BankListResponse(BaseModel):
    """List of available banks."""
    banks: List[BankInfoResponse]
    total: int


class InitPSD2ConnectionRequest(BaseModel):
    """Request to initialize PSD2 connection."""
    bank_code: str = Field(..., min_length=8, max_length=8)
    redirect_uri: str = Field(..., min_length=10)
    scopes: Optional[List[str]] = None


class InitFinTSConnectionRequest(BaseModel):
    """Request to initialize FinTS connection."""
    bank_code: str = Field(..., min_length=8, max_length=8)
    login_id: str = Field(..., min_length=1)
    pin: str = Field(..., min_length=4)  # SECURITY: Never stored
    tan_method: Optional[str] = None


class CompletePSD2Request(BaseModel):
    """Complete PSD2 connection after redirect."""
    authorization_code: Optional[str] = None
    state: Optional[str] = None


class CompleteFinTSRequest(BaseModel):
    """Complete FinTS connection with TAN."""
    tan: str = Field(..., min_length=6, max_length=10)


class ConnectionResponse(BaseModel):
    """Bank connection response."""
    id: UUID
    bank_code: str
    bank_name: str
    bic: Optional[str] = None
    connection_type: str
    status: str
    is_healthy: bool = True
    last_sync_at: Optional[datetime] = None
    next_sync_at: Optional[datetime] = None
    auto_sync_enabled: bool = True
    sync_interval_hours: int = 4
    account_count: int = 0
    error_count: int = 0
    created_at: datetime


class ConnectionListResponse(BaseModel):
    """List of connections."""
    connections: List[ConnectionResponse]
    total: int


class AccountResponse(BaseModel):
    """Connected account response."""
    id: UUID
    iban: str
    iban_masked: str  # Show only last 4 digits
    account_name: Optional[str] = None
    account_type: str = "checking"
    currency: str = "EUR"
    current_balance: Optional[Decimal] = None
    available_balance: Optional[Decimal] = None
    balance_updated_at: Optional[datetime] = None
    is_primary: bool = False
    auto_import: bool = True
    auto_reconcile: bool = True


class ConnectionInitResponse(BaseModel):
    """Response from connection initialization."""
    success: bool
    connection_id: Optional[UUID] = None
    requires_sca: bool = False
    sca_redirect_url: Optional[str] = None
    tan_challenge_text: Optional[str] = None
    tan_method: Optional[str] = None
    error_message: Optional[str] = None


class SyncRequest(BaseModel):
    """Manual sync request."""
    date_from: Optional[date] = None
    date_to: Optional[date] = None


class SyncResponse(BaseModel):
    """Sync result response."""
    success: bool
    connection_id: UUID
    accounts_synced: int = 0
    transactions_imported: int = 0
    transactions_skipped: int = 0
    auto_reconciled: int = 0
    duration_ms: int = 0
    error_message: Optional[str] = None


class PaymentCreateRequest(BaseModel):
    """Create payment request."""
    account_id: UUID
    creditor_name: str = Field(..., min_length=1, max_length=140)
    creditor_iban: str = Field(..., min_length=15, max_length=34)
    creditor_bic: Optional[str] = Field(None, max_length=11)
    amount: Decimal = Field(..., gt=0)
    currency: str = Field(default="EUR", max_length=3)
    reference: Optional[str] = Field(None, max_length=140)
    execution_date: Optional[date] = None
    invoice_id: Optional[UUID] = None

    @field_validator("creditor_iban")
    @classmethod
    def validate_iban(cls, v: str) -> str:
        """Normalize IBAN."""
        return v.replace(" ", "").upper()


class PaymentResponse(BaseModel):
    """Payment response."""
    id: UUID
    status: str
    requires_approval: bool = False
    requires_sca: bool = False
    sca_redirect_url: Optional[str] = None
    tan_challenge_text: Optional[str] = None
    error_message: Optional[str] = None


class ReconciliationSuggestion(BaseModel):
    """Reconciliation suggestion."""
    invoice_id: UUID
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    invoice_amount: Decimal
    outstanding_amount: Decimal
    entity_name: Optional[str] = None
    confidence: float
    match_type: str


class ReconciliationSuggestionsResponse(BaseModel):
    """Reconciliation suggestions for a transaction."""
    transaction_id: UUID
    suggestions: List[ReconciliationSuggestion]


class ManualMatchRequest(BaseModel):
    """Manual match request."""
    invoice_id: UUID
    notes: Optional[str] = None


class SplitAllocation(BaseModel):
    """Single allocation in a split."""
    invoice_id: UUID
    amount: Decimal = Field(..., gt=0)


class SplitMatchRequest(BaseModel):
    """Split match request."""
    allocations: List[SplitAllocation]


class UpdateConnectionRequest(BaseModel):
    """Update connection settings."""
    auto_sync_enabled: Optional[bool] = None
    sync_interval_hours: Optional[int] = Field(None, ge=1, le=24)


class PSD2CallbackResponse(BaseModel):
    """PSD2 Callback-Antwort."""
    success: bool
    connection_id: str


# =============================================================================
# Bank Discovery
# =============================================================================

@router.get("/banks", response_model=BankListResponse)
async def list_available_banks(
    country_code: str = Query(default="DE", max_length=2),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Liste aller verfuegbaren Banken fuer PSD2/FinTS.

    Gibt Banken mit deren Faehigkeiten zurueck (PSD2, FinTS, Zahlungen).
    """
    service = get_account_connection_service()
    banks = await service.get_available_banks(db, country_code)

    return BankListResponse(
        banks=[BankInfoResponse(**b) for b in banks],
        total=len(banks),
    )


@router.get("/banks/{bank_code}", response_model=BankInfoResponse)
async def get_bank_info(
    bank_code: str,
    current_user: User = Depends(get_current_user),
):
    """
    Detailinformationen zu einer Bank.

    Gibt unterstuetzte TAN-Verfahren und API-Faehigkeiten zurueck.
    """
    service = get_account_connection_service()
    bank = await service.get_bank_info(bank_code)

    if not bank:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bank nicht gefunden",
        )

    return BankInfoResponse(**bank)


# =============================================================================
# Connection Management
# =============================================================================

@router.post("/connect/psd2/init", response_model=ConnectionInitResponse)
async def init_psd2_connection(
    request: InitPSD2ConnectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Starte PSD2 Verbindung (OAuth2 Flow).

    Nach Erfolg wird der Benutzer zur Bank weitergeleitet.
    Nach SCA-Bestaetigung wird er zur redirect_uri zurueckgeleitet.
    """
    service = get_account_connection_service()
    result = await service.init_psd2_connection(
        db=db,
        company_id=current_user.company_id,
        user_id=current_user.id,
        bank_code=request.bank_code,
        redirect_uri=request.redirect_uri,
        scopes=request.scopes,
    )

    return ConnectionInitResponse(
        success=result.success,
        connection_id=result.connection_id,
        requires_sca=result.requires_sca,
        sca_redirect_url=result.sca_redirect_url,
        error_message=result.error_message,
    )


@router.get("/connect/psd2/callback", response_model=PSD2CallbackResponse)
async def psd2_callback(
    connection_id: UUID = Query(...),
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    PSD2 OAuth2 Callback nach Bank-Redirect.

    Wird aufgerufen wenn Benutzer von der Bank zurueckkehrt.
    """
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Bank-Fehler: {error}",
        )

    service = get_account_connection_service()
    result = await service.complete_psd2_connection(
        db=db,
        connection_id=connection_id,
        company_id=current_user.company_id,
        authorization_code=code,
        state=state,
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error_message or "Verbindung fehlgeschlagen",
        )

    return PSD2CallbackResponse(success=True, connection_id=str(result.connection_id))


@router.post("/connect/fints", response_model=ConnectionInitResponse)
async def init_fints_connection(
    request: InitFinTSConnectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Starte FinTS Verbindung.

    Die PIN wird nur fuer diese Session verwendet und NICHT gespeichert.
    Bei Erfolg wird ein TAN-Challenge zurueckgegeben.
    """
    service = get_account_connection_service()
    result = await service.init_fints_connection(
        db=db,
        company_id=current_user.company_id,
        user_id=current_user.id,
        bank_code=request.bank_code,
        login_id=request.login_id,
        pin=request.pin,
        tan_method=request.tan_method,
    )

    return ConnectionInitResponse(
        success=result.success,
        connection_id=result.connection_id,
        requires_sca=result.requires_sca,
        tan_challenge_text=result.tan_challenge.challenge_text if result.tan_challenge else None,
        tan_method=result.tan_challenge.tan_method.value if result.tan_challenge else None,
        error_message=result.error_message,
    )


@router.post("/connect/fints/{connection_id}/tan", response_model=ConnectionInitResponse)
async def complete_fints_connection(
    connection_id: UUID,
    request: CompleteFinTSRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Schliesse FinTS Verbindung mit TAN ab.
    """
    service = get_account_connection_service()
    result = await service.complete_fints_connection(
        db=db,
        connection_id=connection_id,
        company_id=current_user.company_id,
        tan=request.tan,
    )

    return ConnectionInitResponse(
        success=result.success,
        connection_id=result.connection_id,
        error_message=result.error_message,
    )


@router.get("/connections", response_model=ConnectionListResponse)
async def list_connections(
    include_inactive: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Liste aller Bank-Verbindungen.
    """
    service = get_account_connection_service()
    connections = await service.get_connections(
        db=db,
        company_id=current_user.company_id,
        include_inactive=include_inactive,
    )

    return ConnectionListResponse(
        connections=[
            ConnectionResponse(
                id=c.id,
                bank_code=c.bank_code,
                bank_name=c.bank_name,
                bic=c.bic,
                connection_type=c.connection_type,
                status=c.status,
                is_healthy=c.is_healthy,
                last_sync_at=c.last_sync_at,
                next_sync_at=c.next_sync_at,
                auto_sync_enabled=c.auto_sync_enabled,
                sync_interval_hours=c.sync_interval_hours,
                account_count=len(c.accounts) if c.accounts else 0,
                error_count=c.error_count,
                created_at=c.created_at,
            )
            for c in connections
        ],
        total=len(connections),
    )


@router.get("/connections/{connection_id}/accounts", response_model=List[AccountResponse])
async def get_connection_accounts(
    connection_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Liste aller Konten einer Verbindung.
    """
    service = get_account_connection_service()
    accounts = await service.get_accounts(
        db=db,
        connection_id=connection_id,
        company_id=current_user.company_id,
    )

    return [
        AccountResponse(
            id=a.id,
            iban=a.iban,
            iban_masked=f"****{a.iban[-4:]}" if a.iban else "****",
            account_name=a.name,
            account_type=a.account_type,
            currency=a.currency,
            current_balance=a.balance,
            balance_updated_at=a.balance_date,
        )
        for a in accounts
    ]


@router.patch("/connections/{connection_id}", response_model=ConnectionResponse)
async def update_connection(
    connection_id: UUID,
    request: UpdateConnectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Aktualisiere Verbindungseinstellungen.
    """
    service = get_account_connection_service()
    connection = await service.update_connection(
        db=db,
        connection_id=connection_id,
        company_id=current_user.company_id,
        auto_sync_enabled=request.auto_sync_enabled,
        sync_interval_hours=request.sync_interval_hours,
    )

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verbindung nicht gefunden",
        )

    return ConnectionResponse(
        id=connection.id,
        bank_code=connection.bank_code,
        bank_name=connection.bank_name,
        bic=connection.bic,
        connection_type=connection.connection_type,
        status=connection.status,
        is_healthy=connection.is_healthy,
        last_sync_at=connection.last_sync_at,
        next_sync_at=connection.next_sync_at,
        auto_sync_enabled=connection.auto_sync_enabled,
        sync_interval_hours=connection.sync_interval_hours,
        account_count=len(connection.accounts) if connection.accounts else 0,
        error_count=connection.error_count,
        created_at=connection.created_at,
    )


@router.delete("/connections/{connection_id}")
async def delete_connection(
    connection_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Loesche eine Bank-Verbindung.

    Bei PSD2 wird der Consent widerrufen.
    """
    service = get_account_connection_service()
    success = await service.delete_connection(
        db=db,
        connection_id=connection_id,
        company_id=current_user.company_id,
        user_id=current_user.id,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verbindung nicht gefunden",
        )

    return {"success": True}


# =============================================================================
# Synchronization
# =============================================================================

@router.post("/connections/{connection_id}/sync", response_model=SyncResponse)
async def sync_connection(
    connection_id: UUID,
    request: Optional[SyncRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Manuelle Synchronisation einer Verbindung.

    Importiert neue Transaktionen und aktualisiert Kontosaldo.
    """
    service = get_auto_transaction_import_service()
    result = await service.sync_connection(
        db=db,
        connection_id=connection_id,
        company_id=current_user.company_id,
        date_from=request.date_from if request else None,
        date_to=request.date_to if request else None,
        triggered_by="manual",
        user_id=current_user.id,
    )

    return SyncResponse(
        success=result.success,
        connection_id=result.connection_id,
        accounts_synced=result.accounts_synced,
        transactions_imported=result.transactions_imported,
        transactions_skipped=result.transactions_skipped,
        auto_reconciled=result.auto_reconciled,
        duration_ms=result.duration_ms,
        error_message=result.error_message,
    )


# =============================================================================
# Payments
# =============================================================================

@router.post("/payments/initiate", response_model=PaymentResponse)
async def initiate_payment(
    request: PaymentCreateRequest,
    redirect_uri: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Initiiere eine SEPA-Ueberweisung.

    Bei PSD2-Konten wird SCA (Weiterleitung zur Bank) erforderlich.
    Bei FinTS wird ein TAN-Challenge zurueckgegeben.
    """
    service = get_payment_initiation_service()
    payment_request = PaymentRequest(
        company_id=current_user.company_id,
        account_id=request.account_id,
        creditor_name=request.creditor_name,
        creditor_iban=request.creditor_iban,
        creditor_bic=request.creditor_bic,
        amount=request.amount,
        currency=request.currency,
        reference=request.reference,
        execution_date=request.execution_date,
        invoice_id=request.invoice_id,
    )

    result = await service.initiate_payment(
        db=db,
        request=payment_request,
        user_id=current_user.id,
        redirect_uri=redirect_uri,
    )

    return PaymentResponse(
        id=result.payment_id,
        status=result.status or "draft",
        requires_approval=result.requires_approval,
        requires_sca=result.requires_sca,
        sca_redirect_url=result.sca_redirect_url,
        tan_challenge_text=result.tan_challenge.challenge_text if result.tan_challenge else None,
        error_message=result.error_message,
    )


@router.post("/payments/{payment_id}/approve")
async def approve_payment(
    payment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Freigabe einer Zahlung (4-Augen-Prinzip).

    Der Freigeber muss ein anderer Benutzer als der Ersteller sein.
    """
    service = get_payment_initiation_service()
    result = await service.approve_payment(
        db=db,
        payment_id=payment_id,
        company_id=current_user.company_id,
        approver_id=current_user.id,
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error_message or "Freigabe fehlgeschlagen",
        )

    return {"success": True, "status": result.status}


@router.post("/payments/{payment_id}/cancel")
async def cancel_payment(
    payment_id: UUID,
    reason: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Storniere eine ausstehende Zahlung.
    """
    service = get_payment_initiation_service()
    result = await service.cancel_payment(
        db=db,
        payment_id=payment_id,
        company_id=current_user.company_id,
        user_id=current_user.id,
        reason=reason,
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error_message or "Stornierung fehlgeschlagen",
        )

    return {"success": True}


# =============================================================================
# Reconciliation
# =============================================================================

@router.get(
    "/reconciliation/suggestions/{transaction_id}",
    response_model=ReconciliationSuggestionsResponse,
)
async def get_reconciliation_suggestions(
    transaction_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Hole Abgleich-Vorschlaege fuer eine Transaktion.
    """
    service = get_auto_reconciliation_service()
    result = await service.reconcile_transaction(
        db=db,
        transaction_id=transaction_id,
        company_id=current_user.company_id,
        auto_apply=False,  # Only get suggestions
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result.error_message or "Transaktion nicht gefunden",
        )

    return ReconciliationSuggestionsResponse(
        transaction_id=transaction_id,
        suggestions=[
            ReconciliationSuggestion(
                invoice_id=s.invoice_id,
                invoice_number=s.invoice_number,
                invoice_date=s.invoice_date,
                due_date=s.due_date,
                invoice_amount=s.invoice_amount,
                outstanding_amount=s.outstanding_amount,
                entity_name=s.entity_name,
                confidence=s.confidence,
                match_type=s.match_type.value,
            )
            for s in result.suggestions
        ],
    )


@router.post("/reconciliation/{transaction_id}/match")
async def manual_match_transaction(
    transaction_id: UUID,
    request: ManualMatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Manueller Abgleich einer Transaktion mit einer Rechnung.
    """
    service = get_auto_reconciliation_service()
    result = await service.manual_match(
        db=db,
        transaction_id=transaction_id,
        invoice_id=request.invoice_id,
        company_id=current_user.company_id,
        user_id=current_user.id,
        notes=request.notes,
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error_message or "Abgleich fehlgeschlagen",
        )

    return {"success": True, "match_type": result.match_type.value if result.match_type else None}


@router.post("/reconciliation/{transaction_id}/split")
async def split_transaction(
    transaction_id: UUID,
    request: SplitMatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Aufteilen einer Transaktion auf mehrere Rechnungen.

    Die Summe der Zuordnungen muss dem Transaktionsbetrag entsprechen.
    """
    service = get_auto_reconciliation_service()
    result = await service.split_transaction(
        db=db,
        transaction_id=transaction_id,
        company_id=current_user.company_id,
        user_id=current_user.id,
        allocations=[
            {"invoice_id": str(a.invoice_id), "amount": a.amount}
            for a in request.allocations
        ],
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error_message or "Aufteilung fehlgeschlagen",
        )

    return {"success": True}
