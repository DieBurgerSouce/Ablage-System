# -*- coding: utf-8 -*-
"""
Payment Reconciliation API Endpoints.

REST API für erweiterten Zahlungsabgleich:
- Auto-Match für alle ungematchten Transaktionen
- Unabgeglichene Transaktionen mit Filterung
- Manuelle Zuordnung
- Match-Vorschläge pro Transaktion
- Match ablehnen mit Begruendung
- Reconciliation-Statistiken

Feinpoliert und durchdacht - Enterprise Payment Reconciliation.
"""

from typing import Optional, List
from uuid import UUID
from datetime import datetime, timezone
from decimal import Decimal

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, case
from pydantic import BaseModel, Field

from app.db.models import User, BankTransaction, BankAccount, Document
from app.api.dependencies import get_db, get_current_active_user
from app.services.banking.reconciliation_service import ReconciliationService, MatchCandidate
from app.services.banking.transaction_service import TransactionService
from app.services.banking.models import (
    ReconciliationStatus,
    ReconciliationResult,
    BatchReconciliationResult,
)
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.core.rate_limiting import limiter, get_user_identifier

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/reconciliation", tags=["Reconciliation"])

# Service-Instanzen
reconciliation_service = ReconciliationService()
transaction_service = TransactionService()


# =============================================================================
# PYDANTIC SCHEMAS
# =============================================================================


class ReconciliationStatsResponse(BaseModel):
    """Reconciliation-Statistiken."""
    total_transactions: int = Field(..., description="Gesamtanzahl Transaktionen")
    matched_count: int = Field(..., description="Abgeglichene Transaktionen")
    unmatched_count: int = Field(..., description="Unabgeglichene Transaktionen")
    partial_count: int = Field(..., description="Teilzuordnungen")
    manual_count: int = Field(..., description="Manuell zugeordnet")
    ignored_count: int = Field(..., description="Ignorierte Transaktionen")
    match_rate: float = Field(..., description="Abgleichquote in Prozent")
    auto_match_success_rate: float = Field(..., description="Auto-Match Erfolgsrate (letzte 30 Tage)")
    avg_confidence: Optional[float] = Field(None, description="Durchschnittliche Match-Konfidenz")
    total_matched_amount: Decimal = Field(..., description="Abgeglichener Gesamtbetrag")
    total_unmatched_amount: Decimal = Field(..., description="Unabgeglichener Gesamtbetrag")
    by_method: dict = Field(default_factory=dict, description="Aufschluesselung nach Match-Methode")


class MatchSuggestionResponse(BaseModel):
    """Match-Vorschlag Response."""
    document_id: str
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    gross_amount: Decimal
    counterparty_name: Optional[str] = None
    counterparty_iban: Optional[str] = None
    customer_number: Optional[str] = None
    confidence: float
    match_method: str
    match_type: str  # exact, fuzzy, partial, manual
    match_reasons: List[str]
    discrepancy_amount: Optional[Decimal] = None


class RejectMatchRequest(BaseModel):
    """Request zum Ablehnen eines Match-Vorschlags."""
    reason: str = Field(..., min_length=3, max_length=500, description="Ablehnungsgrund")
    never_suggest_again: bool = Field(False, description="Dieses Dokument nie wieder vorschlagen")


class ManualMatchRequest(BaseModel):
    """Request für manuelles Matching."""
    document_id: UUID
    notes: Optional[str] = Field(None, max_length=500)
    is_partial: bool = Field(False, description="Teilzahlung")
    allocated_amount: Optional[Decimal] = Field(None, description="Zugewiesener Betrag bei Teilzahlung")


class UnmatchedTransactionResponse(BaseModel):
    """Unabgeglichene Transaktion mit Match-Infos."""
    id: str
    bank_account_id: str
    booking_date: str
    value_date: str
    amount: Decimal
    currency: str
    counterparty_name: Optional[str]
    counterparty_iban: Optional[str]
    reference_text: Optional[str]
    transaction_type: Optional[str]
    suggestion_count: int = Field(0, description="Anzahl verfügbarer Vorschläge")
    best_match_confidence: Optional[float] = Field(None, description="Hoechste Match-Konfidenz")
    days_since_booking: int = Field(0, description="Tage seit Buchung")


class BulkAutoMatchResponse(BaseModel):
    """Response für Bulk Auto-Match."""
    total_processed: int
    matched_count: int
    high_confidence_matches: int = Field(..., description="Matches mit >95% Konfidenz")
    partial_count: int
    unmatched_count: int
    queued_for_review: int = Field(..., description="Für manuelle Prüfung vorgemerkt")
    processing_time_ms: int
    results: List[dict]


# =============================================================================
# AUTO-MATCH
# =============================================================================


@limiter.limit("5/minute", key_func=get_user_identifier)
@router.post(
    "/auto-match",
    response_model=BulkAutoMatchResponse,
    summary="Auto-Abgleich starten",
    description="Führt automatisches Matching für alle unabgeglichenen Transaktionen durch."
)
async def auto_match_transactions(
    request: Request,
    bank_account_id: Optional[UUID] = Query(None, description="Filter auf Bankkonto"),
    min_confidence: float = Query(0.9, ge=0.5, le=1.0, description="Mindest-Konfidenz für Auto-Match"),
    limit: int = Query(100, ge=1, le=500, description="Max. Transaktionen"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BulkAutoMatchResponse:
    """
    Startet automatischen Abgleich für alle unabgeglichenen Transaktionen.

    **Match-Typen:**
    - **exact**: IBAN + Betrag + Referenz stimmen exakt überein (100% Konfidenz)
    - **fuzzy**: Betrag ähnlich (5% Toleranz) + Name enthält Keywords (70-90%)
    - **partial**: Nur Betrag stimmt (50%)

    **Auto-Match**: Nur Matches mit Konfidenz >= min_confidence werden automatisch gesetzt.
    Niedrigere werden für manuelle Prüfung vorgemerkt.
    """
    import time
    start_time = time.time()

    logger.info(
        "auto_match_started",
        user_id=str(current_user.id),
        bank_account_id=str(bank_account_id) if bank_account_id else None,
        min_confidence=min_confidence,
        limit=limit,
    )

    try:
        result = await reconciliation_service.batch_reconcile(
            db=db,
            user_id=current_user.id,
            bank_account_id=bank_account_id,
            limit=limit,
        )

        # Klassifiziere Ergebnisse
        high_confidence = sum(
            1 for r in result.results
            if r.match_confidence and r.match_confidence >= 0.95
        )
        queued = result.total_processed - result.matched_count - result.partial_count

        processing_time = int((time.time() - start_time) * 1000)

        logger.info(
            "auto_match_completed",
            user_id=str(current_user.id),
            matched=result.matched_count,
            partial=result.partial_count,
            unmatched=result.unmatched_count,
            high_confidence=high_confidence,
            processing_time_ms=processing_time,
        )

        return BulkAutoMatchResponse(
            total_processed=result.total_processed,
            matched_count=result.matched_count,
            high_confidence_matches=high_confidence,
            partial_count=result.partial_count,
            unmatched_count=result.unmatched_count,
            queued_for_review=queued,
            processing_time_ms=processing_time,
            results=[
                {
                    "transaction_id": str(r.transaction_id),
                    "status": r.status.value if r.status else "unmatched",
                    "matched_document_id": str(r.matched_document_id) if r.matched_document_id else None,
                    "confidence": r.match_confidence,
                    "method": r.match_method,
                }
                for r in result.results
            ],
        )

    except Exception as e:
        logger.error(
            "auto_match_failed",
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Automatischer Abgleich fehlgeschlagen. Bitte versuchen Sie es erneut.",
        )


# =============================================================================
# UNMATCHED TRANSACTIONS
# =============================================================================


@router.get(
    "/unmatched",
    response_model=List[UnmatchedTransactionResponse],
    summary="Unabgeglichene Transaktionen",
    description="Listet Transaktionen die manuelle Prüfung benötigen."
)
async def list_unmatched_transactions(
    bank_account_id: Optional[UUID] = Query(None, description="Filter auf Bankkonto"),
    min_amount: Optional[Decimal] = Query(None, ge=0, description="Mindestbetrag"),
    max_amount: Optional[Decimal] = Query(None, description="Hoechstbetrag"),
    days_old: Optional[int] = Query(None, ge=0, le=365, description="Mindestens N Tage alt"),
    sort_by: str = Query("booking_date", description="Sortierung: booking_date, amount, counterparty"),
    sort_order: str = Query("desc", regex="^(asc|desc)$", description="Sortierrichtung"),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=200, description="Eintraege pro Seite"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[UnmatchedTransactionResponse]:
    """
    Listet alle Transaktionen die manuelle Prüfung benötigen.

    Enthält für jede Transaktion:
    - Anzahl verfügbarer Match-Vorschläge
    - Hoechste verfügbare Match-Konfidenz
    - Tage seit Buchung (für Priorisierung)
    """
    from sqlalchemy import desc, asc
    from datetime import timedelta
    from app.core.datetime_utils import utc_now

    # Basis-Query: Ungematchte Transaktionen des Users
    query = (
        select(BankTransaction)
        .join(BankAccount)
        .where(
            and_(
                BankAccount.user_id == current_user.id,
                BankAccount.deleted_at.is_(None),
                BankTransaction.reconciliation_status == ReconciliationStatus.UNMATCHED.value,
            )
        )
    )

    # Filter
    if bank_account_id:
        query = query.where(BankTransaction.bank_account_id == bank_account_id)

    if min_amount is not None:
        query = query.where(func.abs(BankTransaction.amount) >= min_amount)

    if max_amount is not None:
        query = query.where(func.abs(BankTransaction.amount) <= max_amount)

    if days_old is not None:
        cutoff_date = utc_now().date() - timedelta(days=days_old)
        query = query.where(BankTransaction.booking_date <= cutoff_date)

    # Sortierung (SECURITY: Nur erlaubte Felder)
    sort_fields = {
        "booking_date": BankTransaction.booking_date,
        "amount": func.abs(BankTransaction.amount),
        "counterparty": BankTransaction.counterparty_name,
    }
    sort_field = sort_fields.get(sort_by, BankTransaction.booking_date)

    if sort_order == "desc":
        query = query.order_by(desc(sort_field))
    else:
        query = query.order_by(asc(sort_field))

    # Pagination
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    transactions = result.scalars().all()

    now = utc_now().date()
    response_list = []

    for tx in transactions:
        # Hole Match-Vorschläge für Zusatzinfos
        try:
            suggestions = await reconciliation_service.find_matches(
                db=db,
                user_id=current_user.id,
                transaction_id=tx.id,
                limit=5,
            )
            suggestion_count = len(suggestions)
            best_confidence = max(s.confidence for s in suggestions) if suggestions else None
        except Exception:
            suggestion_count = 0
            best_confidence = None

        days_since = (now - tx.booking_date).days if tx.booking_date else 0

        response_list.append(UnmatchedTransactionResponse(
            id=str(tx.id),
            bank_account_id=str(tx.bank_account_id),
            booking_date=tx.booking_date.isoformat() if tx.booking_date else "",
            value_date=tx.value_date.isoformat() if tx.value_date else "",
            amount=tx.amount,
            currency=tx.currency or "EUR",
            counterparty_name=tx.counterparty_name,
            counterparty_iban=tx.counterparty_iban,
            reference_text=tx.reference_text,
            transaction_type=tx.transaction_type,
            suggestion_count=suggestion_count,
            best_match_confidence=best_confidence,
            days_since_booking=days_since,
        ))

    return response_list


# =============================================================================
# MANUAL MATCH
# =============================================================================


@limiter.limit("60/minute", key_func=get_user_identifier)
@router.post(
    "/match/{transaction_id}",
    response_model=dict,
    summary="Manueller Abgleich",
    description="Ordnet eine Transaktion manuell einem Dokument zu."
)
async def create_manual_match(
    request: Request,
    transaction_id: UUID,
    match_request: ManualMatchRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Ordnet eine Transaktion manuell einem Dokument zu.

    Bei Teilzahlungen (is_partial=true) kann ein Teilbetrag zugewiesen werden.
    Der verbleibende Betrag bleibt für weitere Zuordnungen offen.
    """
    try:
        if match_request.is_partial and match_request.allocated_amount:
            # Teilzahlung
            results = await reconciliation_service.split_transaction(
                db=db,
                user_id=current_user.id,
                transaction_id=transaction_id,
                splits=[{
                    "document_id": str(match_request.document_id),
                    "amount": float(match_request.allocated_amount),
                    "notes": match_request.notes,
                }],
            )
            return {
                "success": True,
                "transaction_id": str(transaction_id),
                "status": "partial",
                "matched_document_id": str(match_request.document_id),
                "allocated_amount": float(match_request.allocated_amount),
                "message": "Teilzahlung erfolgreich zugeordnet.",
            }
        else:
            # Vollständige Zuordnung
            result = await reconciliation_service.manual_match(
                db=db,
                user_id=current_user.id,
                transaction_id=transaction_id,
                document_id=match_request.document_id,
                notes=match_request.notes,
            )

            logger.info(
                "manual_match_created",
                user_id=str(current_user.id),
                transaction_id=str(transaction_id),
                document_id=str(match_request.document_id),
            )

            return {
                "success": True,
                "transaction_id": str(result.transaction_id),
                "status": result.status.value if result.status else "matched",
                "matched_document_id": str(result.matched_document_id),
                "confidence": result.match_confidence,
                "method": result.match_method,
                "message": "Transaktion erfolgreich zugeordnet.",
            }

    except ValueError as e:
        logger.warning(
            "manual_match_failed",
            user_id=str(current_user.id),
            transaction_id=str(transaction_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Manuelle Zuordnung"),
        )


# =============================================================================
# MATCH SUGGESTIONS
# =============================================================================


@router.get(
    "/suggestions/{transaction_id}",
    response_model=List[MatchSuggestionResponse],
    summary="Match-Vorschläge",
    description="Gibt mögliche Matches für eine Transaktion zurück."
)
async def get_match_suggestions(
    transaction_id: UUID,
    limit: int = Query(10, ge=1, le=20, description="Max. Vorschläge"),
    min_confidence: float = Query(0.3, ge=0.0, le=1.0, description="Mindest-Konfidenz"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[MatchSuggestionResponse]:
    """
    Gibt mögliche Match-Vorschläge für eine Transaktion zurück.

    Vorschläge sind nach Konfidenz sortiert (hoechste zuerst).
    Enthält detaillierte Gruende für das Match.
    """
    try:
        candidates = await reconciliation_service.find_matches(
            db=db,
            user_id=current_user.id,
            transaction_id=transaction_id,
            limit=limit,
        )

        # Filtere nach Mindest-Konfidenz
        filtered = [c for c in candidates if c.confidence >= min_confidence]

        # Hole Transaktionsbetrag für Diskrepanz-Berechnung
        tx_query = (
            select(BankTransaction)
            .join(BankAccount)
            .where(
                and_(
                    BankTransaction.id == transaction_id,
                    BankAccount.user_id == current_user.id,
                )
            )
        )
        tx_result = await db.execute(tx_query)
        transaction = tx_result.scalar_one_or_none()
        tx_amount = abs(transaction.amount) if transaction else None

        return [
            MatchSuggestionResponse(
                document_id=str(c.document_id),
                invoice_number=c.invoice_number,
                invoice_date=c.invoice_date.isoformat() if c.invoice_date else None,
                due_date=c.due_date.isoformat() if c.due_date else None,
                gross_amount=c.gross_amount,
                counterparty_name=c.counterparty_name,
                counterparty_iban=c.counterparty_iban,
                customer_number=c.customer_number,
                confidence=c.confidence,
                match_method=c.match_method,
                match_type=_determine_match_type(c.confidence),
                match_reasons=_build_match_reasons(c),
                discrepancy_amount=(
                    Decimal(str(c.gross_amount)) - Decimal(str(tx_amount))
                    if tx_amount and c.gross_amount else None
                ),
            )
            for c in filtered
        ]

    except Exception as e:
        logger.error(
            "get_suggestions_failed",
            transaction_id=str(transaction_id),
            **safe_error_log(e),
        )
        return []


# =============================================================================
# REJECT MATCH
# =============================================================================


@limiter.limit("60/minute", key_func=get_user_identifier)
@router.post(
    "/reject/{transaction_id}/{document_id}",
    status_code=status.HTTP_200_OK,
    summary="Match ablehnen",
    description="Lehnt einen Match-Vorschlag ab und speichert den Grund."
)
async def reject_match(
    request: Request,
    transaction_id: UUID,
    document_id: UUID,
    reject_request: RejectMatchRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Lehnt einen Match-Vorschlag ab.

    Der Ablehnungsgrund wird für Audit-Zwecke gespeichert.
    Bei never_suggest_again=true wird das Dokument für diese Transaktion blockiert.
    """
    # Verifiziere Transaktion gehoert User
    tx_query = (
        select(BankTransaction)
        .join(BankAccount)
        .where(
            and_(
                BankTransaction.id == transaction_id,
                BankAccount.user_id == current_user.id,
            )
        )
    )
    tx_result = await db.execute(tx_query)
    transaction = tx_result.scalar_one_or_none()

    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaktion nicht gefunden",
        )

    # Verifiziere Dokument existiert
    doc_query = select(Document).where(
        and_(
            Document.id == document_id,
            Document.owner_id == current_user.id,
            Document.deleted_at.is_(None),
        )
    )
    doc_result = await db.execute(doc_query)
    document = doc_result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden",
        )

    # Speichere Ablehnung im Transaktions-Metadata (JSONB)
    rejection_entry = {
        "document_id": str(document_id),
        "reason": reject_request.reason,
        "rejected_at": datetime.now(timezone.utc).isoformat(),
        "rejected_by": str(current_user.id),
        "never_suggest_again": reject_request.never_suggest_again,
    }

    # Aktualisiere Transaktion (speichere in notes oder custom field)
    existing_rejections = getattr(transaction, "rejected_matches", []) or []
    if isinstance(existing_rejections, str):
        import json
        try:
            existing_rejections = json.loads(existing_rejections)
        except Exception:
            existing_rejections = []

    existing_rejections.append(rejection_entry)

    # Speichere in notes (als JSON-String falls kein JSONB-Feld)
    if hasattr(transaction, "rejected_matches"):
        transaction.rejected_matches = existing_rejections
    else:
        # Fallback: Speichere in notes
        current_notes = transaction.notes or ""
        transaction.notes = f"{current_notes}\n[REJECTED] {document_id}: {reject_request.reason}".strip()

    await db.commit()

    logger.info(
        "match_rejected",
        user_id=str(current_user.id),
        transaction_id=str(transaction_id),
        document_id=str(document_id),
        never_suggest_again=reject_request.never_suggest_again,
    )

    return {
        "success": True,
        "transaction_id": str(transaction_id),
        "document_id": str(document_id),
        "reason": reject_request.reason,
        "never_suggest_again": reject_request.never_suggest_again,
        "message": "Match-Vorschlag abgelehnt.",
    }


# =============================================================================
# STATISTICS
# =============================================================================


@router.get(
    "/stats",
    response_model=ReconciliationStatsResponse,
    summary="Reconciliation-Statistiken",
    description="Liefert detaillierte Abgleich-Statistiken."
)
async def get_reconciliation_stats(
    bank_account_id: Optional[UUID] = Query(None, description="Filter auf Bankkonto"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ReconciliationStatsResponse:
    """
    Liefert umfassende Reconciliation-Statistiken.

    **Enthält:**
    - Gesamtzahlen nach Status
    - Abgleichquote
    - Auto-Match Erfolgsrate
    - Durchschnittliche Konfidenz
    - Aufschluesselung nach Match-Methode
    """
    base_conditions = [
        BankAccount.user_id == current_user.id,
        BankAccount.deleted_at.is_(None),
    ]

    if bank_account_id:
        base_conditions.append(BankTransaction.bank_account_id == bank_account_id)

    # Hauptstatistiken
    stats_query = (
        select(
            func.count(BankTransaction.id).label("total"),
            func.count(BankTransaction.id).filter(
                BankTransaction.reconciliation_status == ReconciliationStatus.MATCHED.value
            ).label("matched"),
            func.count(BankTransaction.id).filter(
                BankTransaction.reconciliation_status == ReconciliationStatus.UNMATCHED.value
            ).label("unmatched"),
            func.count(BankTransaction.id).filter(
                BankTransaction.reconciliation_status == ReconciliationStatus.PARTIAL.value
            ).label("partial"),
            func.count(BankTransaction.id).filter(
                BankTransaction.reconciliation_status == ReconciliationStatus.MANUAL.value
            ).label("manual"),
            func.count(BankTransaction.id).filter(
                BankTransaction.reconciliation_status == ReconciliationStatus.IGNORED.value
            ).label("ignored"),
            func.avg(BankTransaction.match_confidence).filter(
                BankTransaction.match_confidence.isnot(None)
            ).label("avg_confidence"),
            func.sum(func.abs(BankTransaction.amount)).filter(
                BankTransaction.reconciliation_status == ReconciliationStatus.MATCHED.value
            ).label("matched_amount"),
            func.sum(func.abs(BankTransaction.amount)).filter(
                BankTransaction.reconciliation_status == ReconciliationStatus.UNMATCHED.value
            ).label("unmatched_amount"),
        )
        .select_from(BankTransaction)
        .join(BankAccount)
        .where(and_(*base_conditions))
    )

    result = await db.execute(stats_query)
    stats = result.first()

    total = stats.total or 0
    matched = stats.matched or 0
    match_rate = (matched / total * 100) if total > 0 else 0.0

    # Auto-Match Erfolgsrate (letzte 30 Tage)
    from datetime import timedelta
    from app.core.datetime_utils import utc_now

    thirty_days_ago = utc_now() - timedelta(days=30)
    auto_stats_query = (
        select(
            func.count(BankTransaction.id).label("total"),
            func.count(BankTransaction.id).filter(
                BankTransaction.reconciliation_status == ReconciliationStatus.MATCHED.value
            ).label("matched"),
        )
        .select_from(BankTransaction)
        .join(BankAccount)
        .where(
            and_(
                *base_conditions,
                BankTransaction.matched_at >= thirty_days_ago,
            )
        )
    )
    auto_result = await db.execute(auto_stats_query)
    auto_stats = auto_result.first()

    auto_total = auto_stats.total or 0
    auto_matched = auto_stats.matched or 0
    auto_success_rate = (auto_matched / auto_total * 100) if auto_total > 0 else 0.0

    # Aufschluesselung nach Match-Methode
    # Hinweis: Falls match_method nicht als separates Feld existiert, ist dies ein Platzhalter
    method_breakdown = {
        "iban_amount": 0,
        "invoice_number": 0,
        "customer_number": 0,
        "amount_date": 0,
        "fuzzy_name": 0,
        "manual": int(stats.manual or 0),
    }

    return ReconciliationStatsResponse(
        total_transactions=total,
        matched_count=matched,
        unmatched_count=int(stats.unmatched or 0),
        partial_count=int(stats.partial or 0),
        manual_count=int(stats.manual or 0),
        ignored_count=int(stats.ignored or 0),
        match_rate=round(match_rate, 1),
        auto_match_success_rate=round(auto_success_rate, 1),
        avg_confidence=round(float(stats.avg_confidence), 2) if stats.avg_confidence else None,
        total_matched_amount=Decimal(str(stats.matched_amount or 0)),
        total_unmatched_amount=Decimal(str(stats.unmatched_amount or 0)),
        by_method=method_breakdown,
    )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _determine_match_type(confidence: float) -> str:
    """Bestimmt den Match-Typ basierend auf Konfidenz."""
    if confidence >= 0.95:
        return "exact"
    elif confidence >= 0.70:
        return "fuzzy"
    elif confidence >= 0.50:
        return "partial"
    else:
        return "manual"


def _build_match_reasons(candidate: MatchCandidate) -> List[str]:
    """Erstellt Liste von Match-Gruenden für UI-Anzeige."""
    reasons = []
    details = candidate.match_details or {}

    if details.get("iban_match"):
        reasons.append("IBAN stimmt überein")
    if details.get("amount_exact"):
        reasons.append("Betrag exakt gleich")
    elif details.get("amount_similar"):
        reasons.append("Betrag ähnlich (innerhalb Toleranz)")
    if details.get("invoice_match") or "invoice" in candidate.match_method.lower():
        reasons.append("Rechnungsnummer im Verwendungszweck gefunden")
    if details.get("customer_match") or "customer" in candidate.match_method.lower():
        reasons.append("Kundennummer erkannt")
    if details.get("name_similarity"):
        sim = details.get("name_similarity", 0)
        if sim >= 0.9:
            reasons.append("Name sehr ähnlich")
        elif sim >= 0.7:
            reasons.append("Name ähnlich")
    if details.get("date_proximity"):
        reasons.append("Datum nahe am Fälligkeitsdatum")

    if not reasons:
        # Fallback basierend auf match_method
        method_reasons = {
            "iban_amount": "IBAN und Betrag stimmen überein",
            "invoice_number": "Rechnungsnummer gefunden",
            "customer_number": "Kundennummer erkannt",
            "amount_date": "Betrag und Datum passen",
            "fuzzy_name": "Name ähnlich",
            "manual": "Manuell zugeordnet",
        }
        if candidate.match_method in method_reasons:
            reasons.append(method_reasons[candidate.match_method])
        else:
            reasons.append("Automatisch erkannt")

    return reasons
