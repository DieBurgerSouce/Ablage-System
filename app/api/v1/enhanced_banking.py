# -*- coding: utf-8 -*-
"""
Enhanced Banking API Endpoints.

Vision 2026 Q4: Multi-Bank Support und Auto-Reconciliation.

Endpoints:
- GET    /banking/enhanced/connections        - Alle Bankverbindungen
- POST   /banking/enhanced/connections        - Neue Verbindung anlegen
- GET    /banking/enhanced/connections/{id}   - Verbindungs-Details
- PATCH  /banking/enhanced/connections/{id}   - Verbindung aktualisieren
- DELETE /banking/enhanced/connections/{id}   - Verbindung entfernen
- POST   /banking/enhanced/connections/{id}/sync    - Manueller Sync
- GET    /banking/enhanced/connections/health       - Gesundheitsstatus
- GET    /banking/enhanced/reconciliation/pending   - Offene Abgleiche
- POST   /banking/enhanced/reconciliation/auto      - Auto-Reconciliation
- POST   /banking/enhanced/reconciliation/manual    - Manueller Abgleich
- GET    /banking/enhanced/reconciliation/suggestions - Vorschläge
- GET    /banking/enhanced/aggregated/balance       - Aggregierter Kontostand
- GET    /banking/enhanced/aggregated/transactions  - Transaktionen aller Konten
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional

from app.core.types import JSONDict
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.core.rate_limiting import limiter
from app.db.models import User
from app.services.banking.enhanced_fints_service import (
    get_enhanced_fints_service,
    BankConnection,
    ConnectionHealth,
    ReconciliationResult,
    SyncResult,
)
from app.services.banking.smart_reconciliation_service import ReconciliationStrategy
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/banking/enhanced", tags=["Enhanced Banking"])


# =============================================================================
# Pydantic Schemas
# =============================================================================

class BankConnectionResponse(BaseModel):
    """Eine Bankverbindung."""
    id: str = Field(..., description="Verbindungs-ID")
    bank_name: str = Field(..., description="Bank-Name")
    iban: str = Field(..., description="IBAN")
    bic: Optional[str] = Field(None, description="BIC")
    account_holder: Optional[str] = Field(None, description="Kontoinhaber")
    current_balance: Optional[float] = Field(None, description="Aktueller Saldo")
    available_balance: Optional[float] = Field(None, description="Verfügbarer Saldo")
    currency: str = Field(default="EUR", description="Währung")
    connection_status: str = Field(..., description="Verbindungsstatus")
    last_sync_at: Optional[str] = Field(None, description="Letzte Synchronisation")
    last_error: Optional[str] = Field(None, description="Letzter Fehler")
    is_primary: bool = Field(default=False, description="Primäres Konto")
    auto_sync_enabled: bool = Field(default=True, description="Auto-Sync aktiv")
    created_at: str = Field(..., description="Erstellt am")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "id": "conn-001",
            "bank_name": "Deutsche Bank",
            "iban": "DE89370400440532013000",
            "bic": "COBADEFFXXX",
            "account_holder": "Max Mustermann GmbH",
            "current_balance": 25430.50,
            "available_balance": 24000.00,
            "currency": "EUR",
            "connection_status": "healthy",
            "last_sync_at": "2026-01-28T08:00:00Z",
            "is_primary": True,
            "auto_sync_enabled": True,
            "created_at": "2026-01-01T00:00:00Z",
        }
    })


class ConnectionCreateRequest(BaseModel):
    """Request zum Anlegen einer Bankverbindung."""
    bank_account_id: UUID = Field(..., description="BankAccount-ID")
    is_primary: bool = Field(default=False, description="Als primäres Konto")
    auto_sync_enabled: bool = Field(default=True, description="Auto-Sync aktivieren")
    sync_interval_hours: int = Field(default=4, ge=1, le=24, description="Sync-Intervall")


class ConnectionUpdateRequest(BaseModel):
    """Request zum Aktualisieren einer Verbindung."""
    is_primary: Optional[bool] = Field(None, description="Primäres Konto")
    auto_sync_enabled: Optional[bool] = Field(None, description="Auto-Sync")
    sync_interval_hours: Optional[int] = Field(None, ge=1, le=24, description="Intervall")


class ConnectionHealthResponse(BaseModel):
    """Gesundheitsstatus aller Verbindungen."""
    total_connections: int = Field(..., description="Anzahl Verbindungen")
    healthy: int = Field(default=0, description="Gesund")
    degraded: int = Field(default=0, description="Eingeschränkt")
    unhealthy: int = Field(default=0, description="Fehlerhaft")
    expired: int = Field(default=0, description="Abgelaufen")
    connections: List[JSONDict] = Field(default=[], description="Status pro Verbindung")


class SyncResultResponse(BaseModel):
    """Ergebnis einer Synchronisation."""
    success: bool = Field(..., description="Erfolgreich")
    connection_id: str = Field(..., description="Verbindungs-ID")
    transactions_fetched: int = Field(default=0, description="Abgerufene Transaktionen")
    new_transactions: int = Field(default=0, description="Neue Transaktionen")
    balance_before: Optional[float] = Field(None, description="Saldo vorher")
    balance_after: Optional[float] = Field(None, description="Saldo nachher")
    sync_duration_ms: int = Field(default=0, description="Dauer in ms")
    error_message: Optional[str] = Field(None, description="Fehlermeldung")


class ReconciliationSuggestionResponse(BaseModel):
    """Ein Vorschlag für Auto-Reconciliation."""
    transaction_id: str = Field(..., description="Transaktion-ID")
    invoice_id: str = Field(..., description="Vorgeschlagene Rechnung-ID")
    invoice_number: Optional[str] = Field(None, description="Rechnungsnummer")
    invoice_entity_name: Optional[str] = Field(None, description="Lieferant/Kunde")
    strategy: str = Field(..., description="Matching-Strategie")
    confidence: float = Field(..., description="Konfidenz (0-1)")
    amount_difference: float = Field(default=0.0, description="Betragsdifferenz")
    explanation: str = Field(..., description="Erklärung")


class ReconciliationResultResponse(BaseModel):
    """Ergebnis einer Reconciliation."""
    success: bool = Field(..., description="Erfolgreich")
    transaction_id: str = Field(..., description="Transaktion-ID")
    invoice_id: Optional[str] = Field(None, description="Verknüpfte Rechnung")
    strategy_used: Optional[str] = Field(None, description="Verwendete Strategie")
    confidence: float = Field(default=0.0, description="Konfidenz")
    is_skonto: bool = Field(default=False, description="Skonto-Zahlung")
    is_partial: bool = Field(default=False, description="Teilzahlung")
    remaining_amount: Optional[float] = Field(None, description="Restbetrag")
    error_message: Optional[str] = Field(None, description="Fehler")


class PendingReconciliationResponse(BaseModel):
    """Offene Abgleiche."""
    total_pending: int = Field(..., description="Anzahl offene")
    total_amount: float = Field(default=0.0, description="Gesamtbetrag")
    by_bank: Dict[str, int] = Field(default_factory=dict, description="Nach Bank")
    transactions: List[JSONDict] = Field(default=[], description="Transaktionen")


class AutoReconciliationRequest(BaseModel):
    """Request für Auto-Reconciliation."""
    connection_id: Optional[UUID] = Field(None, description="Nur für diese Verbindung")
    min_confidence: float = Field(default=0.85, ge=0.5, le=1.0, description="Min. Konfidenz")
    include_skonto: bool = Field(default=True, description="Skonto-Matching")
    include_partial: bool = Field(default=True, description="Teilzahlung-Matching")
    dry_run: bool = Field(default=False, description="Nur simulieren")


class AutoReconciliationResponse(BaseModel):
    """Ergebnis der Auto-Reconciliation."""
    success: bool = Field(..., description="Erfolgreich")
    total_processed: int = Field(default=0, description="Verarbeitet")
    matched: int = Field(default=0, description="Zugeordnet")
    skonto_matches: int = Field(default=0, description="Skonto-Matches")
    partial_matches: int = Field(default=0, description="Teilzahlungen")
    unmatched: int = Field(default=0, description="Ohne Match")
    total_amount_matched: float = Field(default=0.0, description="Zugeordneter Betrag")
    duration_ms: int = Field(default=0, description="Dauer in ms")
    dry_run: bool = Field(default=False, description="Nur Simulation")
    details: List[JSONDict] = Field(default=[], description="Details")


class ManualReconciliationRequest(BaseModel):
    """Request für manuellen Abgleich."""
    transaction_id: UUID = Field(..., description="Transaktion-ID")
    invoice_id: UUID = Field(..., description="Rechnung-ID")
    is_skonto: bool = Field(default=False, description="Skonto-Zahlung")
    is_partial: bool = Field(default=False, description="Teilzahlung")
    note: Optional[str] = Field(None, max_length=500, description="Anmerkung")


class AggregatedBalanceResponse(BaseModel):
    """Aggregierter Kontostand aller Verbindungen."""
    total_balance: float = Field(..., description="Gesamtsaldo")
    total_available: float = Field(..., description="Gesamt verfügbar")
    currency: str = Field(default="EUR", description="Währung")
    connection_count: int = Field(..., description="Anzahl Konten")
    by_bank: List[JSONDict] = Field(default=[], description="Nach Bank")
    as_of: str = Field(..., description="Stand")


class AggregatedTransactionsResponse(BaseModel):
    """Aggregierte Transaktionen."""
    transactions: List[JSONDict] = Field(..., description="Transaktionen")
    total_count: int = Field(..., description="Gesamtanzahl")
    total_inflow: float = Field(default=0.0, description="Zuflüsse")
    total_outflow: float = Field(default=0.0, description="Abflüsse")
    page: int = Field(..., description="Seite")
    page_size: int = Field(..., description="Pro Seite")


# =============================================================================
# Helper Functions
# =============================================================================

def _connection_to_response(conn: BankConnection) -> BankConnectionResponse:
    """Konvertiert BankConnection zu Response-Schema."""
    return BankConnectionResponse(
        id=str(conn.id),
        bank_name=conn.bank_name,
        iban=conn.iban,
        bic=conn.bic,
        account_holder=conn.account_holder,
        current_balance=float(conn.current_balance) if conn.current_balance else None,
        available_balance=float(conn.available_balance) if conn.available_balance else None,
        currency=conn.currency,
        connection_status=conn.health.value,
        last_sync_at=conn.last_sync_at.isoformat() if conn.last_sync_at else None,
        last_error=conn.last_error,
        is_primary=conn.is_primary,
        auto_sync_enabled=conn.auto_sync_enabled,
        created_at=conn.created_at.isoformat(),
    )


# =============================================================================
# Connection Management Endpoints
# =============================================================================

@router.get(
    "/connections",
    response_model=List[BankConnectionResponse],
    summary="Alle Bankverbindungen",
    description="Listet alle Bankverbindungen des Benutzers auf.",
)
@limiter.limit("30/minute")
async def list_connections(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[BankConnectionResponse]:
    """Listet alle Bankverbindungen auf."""
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer ist keiner Firma zugeordnet.",
        )

    service = get_enhanced_fints_service()
    connections = await service.list_connections(db, company_id, current_user.id)

    return [_connection_to_response(c) for c in connections]


@router.post(
    "/connections",
    response_model=BankConnectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Verbindung anlegen",
    description="Legt eine neue Bankverbindung an.",
)
@limiter.limit("10/minute")
async def create_connection(
    request: Request,
    data: ConnectionCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> BankConnectionResponse:
    """Legt eine neue Bankverbindung an."""
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer ist keiner Firma zugeordnet.",
        )

    service = get_enhanced_fints_service()

    connection, error = await service.create_connection(
        db=db,
        company_id=company_id,
        user_id=current_user.id,
        bank_account_id=data.bank_account_id,
        is_primary=data.is_primary,
        auto_sync_enabled=data.auto_sync_enabled,
        sync_interval_hours=data.sync_interval_hours,
    )

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error or "Verbindung konnte nicht angelegt werden.",
        )

    await db.commit()

    logger.info(
        "bank_connection_created",
        connection_id=str(connection.id),
        user_id=str(current_user.id),
    )

    return _connection_to_response(connection)


@router.get(
    "/connections/{connection_id}",
    response_model=BankConnectionResponse,
    summary="Verbindungs-Details",
    description="Ruft Details einer Bankverbindung ab.",
)
@limiter.limit("30/minute")
async def get_connection(
    request: Request,
    connection_id: UUID = Path(..., description="Verbindungs-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> BankConnectionResponse:
    """Ruft Details einer Bankverbindung ab."""
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer ist keiner Firma zugeordnet.",
        )

    service = get_enhanced_fints_service()

    try:
        # SECURITY: Übergebe company_id für Ownership-Validierung
        connection = await service.get_connection(
            connection_id=connection_id,
            company_id=company_id,  # Verhindert Cross-Company Access
        )
    except PermissionError as e:
        logger.warning(
            "unauthorized_access_attempt",
            connection_id=str(connection_id),
            user_id=str(current_user.id),
            company_id=str(company_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung für diese Verbindung.",
        )

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verbindung nicht gefunden.",
        )

    return _connection_to_response(connection)


@router.patch(
    "/connections/{connection_id}",
    response_model=BankConnectionResponse,
    summary="Verbindung aktualisieren",
    description="Aktualisiert eine Bankverbindung.",
)
@limiter.limit("10/minute")
async def update_connection(
    request: Request,
    connection_id: UUID = Path(..., description="Verbindungs-ID"),
    data: ConnectionUpdateRequest = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> BankConnectionResponse:
    """Aktualisiert eine Bankverbindung."""
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer ist keiner Firma zugeordnet.",
        )

    service = get_enhanced_fints_service()

    # SECURITY: Übergebe company_id für Ownership-Validierung
    connection, error = await service.update_connection(
        db=db,
        connection_id=connection_id,
        user_id=current_user.id,
        company_id=company_id,  # Verhindert Cross-Company Access
        is_primary=data.is_primary,
        auto_sync_enabled=data.auto_sync_enabled,
        sync_interval_hours=data.sync_interval_hours,
    )

    if not connection:
        if error and "Berechtigung" in error:
            logger.warning(
                "unauthorized_update_attempt",
                connection_id=str(connection_id),
                user_id=str(current_user.id),
                company_id=str(company_id),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=error,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error or "Aktualisierung fehlgeschlagen.",
        )

    await db.commit()
    return _connection_to_response(connection)


@router.delete(
    "/connections/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Verbindung entfernen",
    description="Entfernt eine Bankverbindung.",
)
@limiter.limit("10/minute")
async def delete_connection(
    request: Request,
    connection_id: UUID = Path(..., description="Verbindungs-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Entfernt eine Bankverbindung."""
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer ist keiner Firma zugeordnet.",
        )

    service = get_enhanced_fints_service()

    try:
        # SECURITY: Übergebe company_id für Ownership-Validierung
        success = await service.delete_connection(
            db=db,
            connection_id=connection_id,
            user_id=current_user.id,
            company_id=company_id,  # Verhindert Cross-Company Access
        )
    except PermissionError as e:
        logger.warning(
            "unauthorized_delete_attempt",
            connection_id=str(connection_id),
            user_id=str(current_user.id),
            company_id=str(company_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung für diese Verbindung.",
        )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verbindung nicht gefunden.",
        )

    await db.commit()

    logger.info(
        "bank_connection_deleted",
        connection_id=str(connection_id),
        user_id=str(current_user.id),
    )

    return None


@router.post(
    "/connections/{connection_id}/sync",
    response_model=SyncResultResponse,
    summary="Manueller Sync",
    description="Synchronisiert Transaktionen manuell.",
)
@limiter.limit("5/minute")
async def sync_connection(
    request: Request,
    connection_id: UUID = Path(..., description="Verbindungs-ID"),
    date_from: Optional[date] = Query(None, description="Von Datum"),
    date_to: Optional[date] = Query(None, description="Bis Datum"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> SyncResultResponse:
    """
    Synchronisiert Transaktionen manuell.

    Ruft neue Transaktionen vom Bankkonto ab.
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer ist keiner Firma zugeordnet.",
        )

    service = get_enhanced_fints_service()

    # SECURITY: Übergebe company_id für Ownership-Validierung
    result = await service.sync_connection(
        connection_id=connection_id,
        company_id=company_id,  # Verhindert Cross-Company Access
        date_from=date_from,
        date_to=date_to,
    )

    # Prüfe auf Authorization-Fehler
    if not result.success and result.error and "Berechtigung" in result.error:
        logger.warning(
            "unauthorized_sync_attempt",
            connection_id=str(connection_id),
            user_id=str(current_user.id),
            company_id=str(company_id),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=result.error,
        )

    await db.commit()

    return SyncResultResponse(
        success=result.success,
        connection_id=str(connection_id),
        transactions_fetched=result.transactions_fetched,
        new_transactions=result.new_transactions,
        balance_before=float(result.balance_before) if result.balance_before else None,
        balance_after=float(result.balance_after) if result.balance_after else None,
        sync_duration_ms=result.duration_ms,
        error_message=result.error_message,
    )


@router.get(
    "/connections/health",
    response_model=ConnectionHealthResponse,
    summary="Gesundheitsstatus",
    description="Zeigt den Gesundheitsstatus aller Verbindungen.",
)
@limiter.limit("30/minute")
async def get_connections_health(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ConnectionHealthResponse:
    """Zeigt den Gesundheitsstatus aller Bankverbindungen."""
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer ist keiner Firma zugeordnet.",
        )

    service = get_enhanced_fints_service()
    health_data = await service.get_connections_health(db, company_id, current_user.id)

    return ConnectionHealthResponse(
        total_connections=health_data.total,
        healthy=health_data.healthy,
        degraded=health_data.degraded,
        unhealthy=health_data.unhealthy,
        expired=health_data.expired,
        connections=health_data.details,
    )


# =============================================================================
# Reconciliation Endpoints
# =============================================================================

@router.get(
    "/reconciliation/pending",
    response_model=PendingReconciliationResponse,
    summary="Offene Abgleiche",
    description="Zeigt Transaktionen die noch keiner Rechnung zugeordnet sind.",
)
@limiter.limit("30/minute")
async def get_pending_reconciliations(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    connection_id: Optional[UUID] = Query(None, description="Nur für diese Verbindung"),
    page: int = Query(1, ge=1, description="Seite"),
    page_size: int = Query(50, ge=1, le=100, description="Pro Seite"),
) -> PendingReconciliationResponse:
    """Zeigt Transaktionen ohne Rechnungszuordnung."""
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer ist keiner Firma zugeordnet.",
        )

    service = get_enhanced_fints_service()
    result = await service.get_pending_reconciliations(
        db=db,
        company_id=company_id,
        user_id=current_user.id,
        connection_id=connection_id,
        page=page,
        page_size=page_size,
    )

    return PendingReconciliationResponse(
        total_pending=result.total,
        total_amount=float(result.total_amount),
        by_bank=result.by_bank,
        transactions=result.transactions,
    )


@router.get(
    "/reconciliation/suggestions",
    response_model=List[ReconciliationSuggestionResponse],
    summary="Reconciliation-Vorschläge",
    description="Zeigt KI-generierte Zuordnungsvorschläge.",
)
@limiter.limit("30/minute")
async def get_reconciliation_suggestions(
    request: Request,
    transaction_id: UUID = Query(..., description="Transaktion-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    min_confidence: float = Query(0.7, ge=0.5, le=1.0, description="Min. Konfidenz"),
) -> List[ReconciliationSuggestionResponse]:
    """
    Zeigt KI-generierte Zuordnungsvorschläge für eine Transaktion.

    Verwendet verschiedene Matching-Strategien:
    - IBAN + Betrag (99%)
    - Referenznummer (95%)
    - Skonto-Match (85%)
    - Betrag-Toleranz (75%)
    - Teilzahlung (70%)
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer ist keiner Firma zugeordnet.",
        )

    service = get_enhanced_fints_service()
    suggestions = await service.get_reconciliation_suggestions(
        db=db,
        transaction_id=transaction_id,
        user_id=current_user.id,
        min_confidence=min_confidence,
    )

    return [
        ReconciliationSuggestionResponse(
            transaction_id=str(s.transaction_id),
            invoice_id=str(s.invoice_id),
            invoice_number=s.invoice_number,
            invoice_entity_name=s.entity_name,
            strategy=s.strategy.value,
            confidence=s.confidence,
            amount_difference=float(s.amount_difference),
            explanation=s.explanation,
        )
        for s in suggestions
    ]


@router.post(
    "/reconciliation/auto",
    response_model=AutoReconciliationResponse,
    summary="Auto-Reconciliation",
    description="Führt automatische Zuordnung für alle offenen Transaktionen durch.",
)
@limiter.limit("5/minute")
async def auto_reconcile(
    request: Request,
    data: AutoReconciliationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> AutoReconciliationResponse:
    """
    Führt automatische Zuordnung durch.

    **dry_run=true**: Nur Simulation, keine Änderungen.

    Matching-Strategien:
    1. EXACT_MATCH: IBAN + exakter Betrag (99%)
    2. REFERENCE_MATCH: Rechnungsnummer im Verwendungszweck (95%)
    3. SKONTO_MATCH: Betrag mit Skonto-Abzug (85%)
    4. AMOUNT_MATCH: Betrag mit Toleranz (75%)
    5. PARTIAL_MATCH: Teilzahlung (70%)
    """
    import time

    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer ist keiner Firma zugeordnet.",
        )

    start_time = time.time()

    service = get_enhanced_fints_service()

    result = await service.auto_reconcile(
        db=db,
        company_id=company_id,
        user_id=current_user.id,
        connection_id=data.connection_id,
        min_confidence=data.min_confidence,
        include_skonto=data.include_skonto,
        include_partial=data.include_partial,
        dry_run=data.dry_run,
    )

    if not data.dry_run:
        await db.commit()

    duration_ms = int((time.time() - start_time) * 1000)

    logger.info(
        "auto_reconciliation_complete",
        user_id=str(current_user.id),
        matched=result.matched,
        unmatched=result.unmatched,
        dry_run=data.dry_run,
        duration_ms=duration_ms,
    )

    return AutoReconciliationResponse(
        success=True,
        total_processed=result.total_processed,
        matched=result.matched,
        skonto_matches=result.skonto_matches,
        partial_matches=result.partial_matches,
        unmatched=result.unmatched,
        total_amount_matched=float(result.total_amount_matched),
        duration_ms=duration_ms,
        dry_run=data.dry_run,
        details=result.details,
    )


@router.post(
    "/reconciliation/manual",
    response_model=ReconciliationResultResponse,
    summary="Manueller Abgleich",
    description="Ordnet eine Transaktion manuell einer Rechnung zu.",
)
@limiter.limit("30/minute")
async def manual_reconcile(
    request: Request,
    data: ManualReconciliationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ReconciliationResultResponse:
    """
    Ordnet eine Transaktion manuell einer Rechnung zu.

    Optionen:
    - is_skonto: Als Skonto-Zahlung markieren
    - is_partial: Als Teilzahlung markieren
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer ist keiner Firma zugeordnet.",
        )

    service = get_enhanced_fints_service()

    result = await service.manual_reconcile(
        db=db,
        transaction_id=data.transaction_id,
        invoice_id=data.invoice_id,
        user_id=current_user.id,
        is_skonto=data.is_skonto,
        is_partial=data.is_partial,
        note=data.note,
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error_message or "Zuordnung fehlgeschlagen.",
        )

    await db.commit()

    return ReconciliationResultResponse(
        success=result.success,
        transaction_id=str(data.transaction_id),
        invoice_id=str(data.invoice_id),
        strategy_used="manual",
        confidence=1.0,
        is_skonto=data.is_skonto,
        is_partial=data.is_partial,
        remaining_amount=float(result.remaining_amount) if result.remaining_amount else None,
    )


# =============================================================================
# Aggregated View Endpoints
# =============================================================================

@router.get(
    "/aggregated/balance",
    response_model=AggregatedBalanceResponse,
    summary="Aggregierter Kontostand",
    description="Zeigt den aggregierten Kontostand aller Verbindungen.",
)
@limiter.limit("30/minute")
async def get_aggregated_balance(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> AggregatedBalanceResponse:
    """Zeigt den aggregierten Kontostand aller Bankverbindungen."""
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer ist keiner Firma zugeordnet.",
        )

    service = get_enhanced_fints_service()
    result = await service.get_aggregated_balance(db, company_id, current_user.id)

    return AggregatedBalanceResponse(
        total_balance=float(result.total_balance),
        total_available=float(result.total_available),
        currency=result.currency,
        connection_count=result.connection_count,
        by_bank=result.by_bank,
        as_of=result.as_of.isoformat(),
    )


@router.get(
    "/aggregated/transactions",
    response_model=AggregatedTransactionsResponse,
    summary="Aggregierte Transaktionen",
    description="Zeigt Transaktionen aller Verbindungen.",
)
@limiter.limit("30/minute")
async def get_aggregated_transactions(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    date_from: Optional[date] = Query(None, description="Von Datum"),
    date_to: Optional[date] = Query(None, description="Bis Datum"),
    page: int = Query(1, ge=1, description="Seite"),
    page_size: int = Query(50, ge=1, le=100, description="Pro Seite"),
) -> AggregatedTransactionsResponse:
    """Zeigt aggregierte Transaktionen aller Bankverbindungen."""
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer ist keiner Firma zugeordnet.",
        )

    service = get_enhanced_fints_service()
    result = await service.get_aggregated_transactions(
        db=db,
        company_id=company_id,
        user_id=current_user.id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )

    return AggregatedTransactionsResponse(
        transactions=result.transactions,
        total_count=result.total,
        total_inflow=float(result.total_inflow),
        total_outflow=float(result.total_outflow),
        page=page,
        page_size=page_size,
    )
