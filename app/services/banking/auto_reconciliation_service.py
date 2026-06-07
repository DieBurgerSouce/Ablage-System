# -*- coding: utf-8 -*-
"""
Auto Reconciliation Service for matching transactions to invoices.

Features:
- Confidence-based matching
- Multiple matching strategies
- Partial payment handling
- Multi-invoice payment splitting
- Manual match suggestions
- Learning from manual corrections

Matching Strategies (in priority order):
1. IBAN + Exact Amount (99% confidence)
2. Reference Number in Text (95% confidence)
3. IBAN + Skonto Amount (92% confidence)
4. Customer Number + Amount (85% confidence)
5. Fuzzy Name + Amount (70% confidence)

SECURITY NOTES:
- Never log transaction or invoice details
- Audit all reconciliation decisions
- Respect company isolation
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any, Set
from uuid import UUID, uuid4

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
from prometheus_client import Counter, Histogram

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log, safe_error_detail
from app.db.models_banking_connection import (
    ImportedTransaction,
    TransactionSplitAllocation,
    ReconciliationRule,
    ReconciliationMatchType,
)
from app.db.models import InvoiceTracking, Document, BusinessEntity

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metrics
# =============================================================================

RECONCILIATION_TOTAL = Counter(
    "banking_reconciliation_total",
    "Total reconciliation attempts",
    ["company_id", "match_type"]
)

RECONCILIATION_SUCCESS = Counter(
    "banking_reconciliation_success_total",
    "Successful reconciliations",
    ["company_id", "match_type"]
)

RECONCILIATION_DURATION = Histogram(
    "banking_reconciliation_duration_seconds",
    "Reconciliation processing time",
    ["company_id"]
)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class ReconciliationConfig:
    """Reconciliation configuration."""
    auto_reconcile_threshold: float = 0.90  # Auto-match above this confidence
    suggestion_threshold: float = 0.50      # Show as suggestion above this
    amount_tolerance_percent: float = 0.01  # 1% tolerance
    skonto_tolerance_percent: float = 0.05  # 5% for skonto matching
    date_tolerance_days: int = 7            # Days tolerance for date matching
    max_suggestions: int = 5                # Max suggestions per transaction


DEFAULT_CONFIG = ReconciliationConfig()


# =============================================================================
# Types
# =============================================================================

@dataclass
class MatchCandidate:
    """A potential match for a transaction."""
    invoice_id: UUID
    invoice_number: Optional[str]
    invoice_date: Optional[date]
    due_date: Optional[date]
    invoice_amount: Decimal
    outstanding_amount: Decimal
    currency: str
    entity_id: Optional[UUID]
    entity_name: Optional[str]
    entity_iban: Optional[str]
    confidence: float
    match_type: ReconciliationMatchType
    match_details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReconciliationResult:
    """Result of reconciliation attempt."""
    transaction_id: UUID
    success: bool
    matched: bool = False
    match_type: Optional[ReconciliationMatchType] = None
    confidence: float = 0.0
    invoice_id: Optional[UUID] = None
    is_partial: bool = False
    allocated_amount: Optional[Decimal] = None
    remaining_amount: Optional[Decimal] = None
    error_message: Optional[str] = None
    suggestions: List[MatchCandidate] = field(default_factory=list)


@dataclass
class BatchReconciliationResult:
    """Result of batch reconciliation."""
    total_processed: int = 0
    matched_count: int = 0
    partial_count: int = 0
    unmatched_count: int = 0
    error_count: int = 0
    results: List[ReconciliationResult] = field(default_factory=list)


# =============================================================================
# Auto Reconciliation Service
# =============================================================================

class AutoReconciliationService:
    """
    Service for automatic transaction reconciliation.

    Matches imported bank transactions to open invoices
    using multiple strategies with confidence scoring.
    """

    def __init__(
        self,
        config: Optional[ReconciliationConfig] = None,
    ):
        self.config = config or DEFAULT_CONFIG

        logger.info("auto_reconciliation_service_initialized")

    # =========================================================================
    # Single Transaction Reconciliation
    # =========================================================================

    async def reconcile_transaction(
        self,
        db: AsyncSession,
        transaction_id: UUID,
        company_id: UUID,
        auto_apply: bool = True,
    ) -> ReconciliationResult:
        """
        Attempt to reconcile a single transaction.

        Args:
            db: Database session
            transaction_id: Transaction to reconcile
            company_id: Company ID for security
            auto_apply: If True, automatically apply high-confidence matches

        Returns:
            ReconciliationResult with match details or suggestions
        """
        import time
        start_time = time.time()

        # Get transaction with account info
        tx = await self._get_transaction_with_account(db, transaction_id, company_id)
        if not tx:
            return ReconciliationResult(
                transaction_id=transaction_id,
                success=False,
                error_message="Transaktion nicht gefunden",
            )

        # Skip if already reconciled
        if tx.reconciliation_status == "matched":
            return ReconciliationResult(
                transaction_id=transaction_id,
                success=True,
                matched=True,
                match_type=ReconciliationMatchType(tx.reconciliation_match_type) if tx.reconciliation_match_type else None,
                confidence=tx.reconciliation_confidence or 1.0,
                invoice_id=tx.matched_invoice_id,
            )

        # Only reconcile incoming payments (positive amounts)
        if tx.amount <= 0:
            return ReconciliationResult(
                transaction_id=transaction_id,
                success=True,
                matched=False,
                error_message="Nur eingehende Zahlungen werden abgeglichen",
            )

        try:
            # Find match candidates using all strategies
            candidates = await self._find_candidates(db, tx, company_id)

            if not candidates:
                return ReconciliationResult(
                    transaction_id=transaction_id,
                    success=True,
                    matched=False,
                )

            # Sort by confidence
            candidates.sort(key=lambda c: c.confidence, reverse=True)
            best_match = candidates[0]

            # Check if we should auto-apply
            if auto_apply and best_match.confidence >= self.config.auto_reconcile_threshold:
                # Apply the match
                await self._apply_match(db, tx, best_match)

                duration = time.time() - start_time
                RECONCILIATION_DURATION.labels(company_id=str(company_id)).observe(duration)
                RECONCILIATION_SUCCESS.labels(
                    company_id=str(company_id),
                    match_type=best_match.match_type.value,
                ).inc()

                logger.info(
                    "transaction_auto_reconciled",
                    transaction_id=str(transaction_id),
                    match_type=best_match.match_type.value,
                    confidence=best_match.confidence,
                )

                return ReconciliationResult(
                    transaction_id=transaction_id,
                    success=True,
                    matched=True,
                    match_type=best_match.match_type,
                    confidence=best_match.confidence,
                    invoice_id=best_match.invoice_id,
                    is_partial=tx.amount < best_match.outstanding_amount,
                    allocated_amount=tx.amount,
                    remaining_amount=max(Decimal("0"), best_match.outstanding_amount - tx.amount),
                )

            # Return suggestions
            suggestions = [c for c in candidates[:self.config.max_suggestions]
                          if c.confidence >= self.config.suggestion_threshold]

            RECONCILIATION_TOTAL.labels(
                company_id=str(company_id),
                match_type="suggestion",
            ).inc()

            return ReconciliationResult(
                transaction_id=transaction_id,
                success=True,
                matched=False,
                suggestions=suggestions,
            )

        except Exception as e:
            logger.error(
                "reconciliation_error",
                transaction_id=str(transaction_id),
                **safe_error_log(e),
            )
            return ReconciliationResult(
                transaction_id=transaction_id,
                success=False,
                error_message=safe_error_detail(e, "Abgleich"),
            )

    async def _find_candidates(
        self,
        db: AsyncSession,
        tx: ImportedTransaction,
        company_id: UUID,
    ) -> List[MatchCandidate]:
        """Find all potential matches for a transaction."""
        candidates: List[MatchCandidate] = []

        # Strategy 1: IBAN + Exact Amount
        if tx.counterparty_iban:
            iban_matches = await self._match_by_iban_amount(db, tx, company_id)
            candidates.extend(iban_matches)

        # Strategy 2: Reference Number
        if tx.reference_text:
            ref_matches = await self._match_by_reference(db, tx, company_id)
            candidates.extend(ref_matches)

        # Strategy 3: Skonto Match
        if tx.counterparty_iban:
            skonto_matches = await self._match_by_skonto(db, tx, company_id)
            candidates.extend(skonto_matches)

        # Strategy 4: Customer Number (if found in reference)
        customer_numbers = self._extract_customer_numbers(tx.reference_text or "")
        if customer_numbers:
            customer_matches = await self._match_by_customer_number(db, tx, company_id, customer_numbers)
            candidates.extend(customer_matches)

        # Strategy 5: Fuzzy Name + Amount
        if tx.counterparty_name:
            fuzzy_matches = await self._match_by_fuzzy_name(db, tx, company_id)
            candidates.extend(fuzzy_matches)

        # Deduplicate by invoice_id, keeping highest confidence
        seen_invoices: Dict[UUID, MatchCandidate] = {}
        for candidate in candidates:
            if candidate.invoice_id not in seen_invoices:
                seen_invoices[candidate.invoice_id] = candidate
            elif candidate.confidence > seen_invoices[candidate.invoice_id].confidence:
                seen_invoices[candidate.invoice_id] = candidate

        return list(seen_invoices.values())

    async def _match_by_iban_amount(
        self,
        db: AsyncSession,
        tx: ImportedTransaction,
        company_id: UUID,
    ) -> List[MatchCandidate]:
        """Match by IBAN + exact amount."""
        if not tx.counterparty_iban or tx.amount <= 0:
            return []

        # Find entities with matching IBAN
        entity_query = select(BusinessEntity).where(
            and_(
                BusinessEntity.company_id == company_id,
                BusinessEntity.iban == tx.counterparty_iban,
                BusinessEntity.deleted_at.is_(None),
            )
        )
        result = await db.execute(entity_query)
        entities = list(result.scalars().all())

        if not entities:
            return []

        entity_ids = [e.id for e in entities]
        entity_map = {e.id: e for e in entities}

        # Find open invoices for these entities with matching amount
        invoice_query = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.status.in_(["open", "overdue"]),
                InvoiceTracking.deleted_at.is_(None),
                # Amount match with tolerance
                func.abs(InvoiceTracking.outstanding_amount - float(tx.amount)) <= float(tx.amount * Decimal(str(self.config.amount_tolerance_percent))),
            )
        ).join(
            Document,
            InvoiceTracking.document_id == Document.id
        ).where(
            Document.business_entity_id.in_(entity_ids)
        )

        result = await db.execute(invoice_query)
        invoices = result.scalars().all()

        candidates = []
        for invoice in invoices:
            # Get entity for this invoice
            doc = await db.get(Document, invoice.document_id)
            entity = entity_map.get(doc.business_entity_id) if doc else None

            # Calculate confidence
            amount_diff = abs(Decimal(str(invoice.outstanding_amount)) - tx.amount)
            if amount_diff == 0:
                confidence = 0.99
            else:
                confidence = 0.95

            candidates.append(MatchCandidate(
                invoice_id=invoice.id,
                invoice_number=invoice.invoice_number,
                invoice_date=invoice.invoice_date,
                due_date=invoice.due_date,
                invoice_amount=Decimal(str(invoice.amount)),
                outstanding_amount=Decimal(str(invoice.outstanding_amount)),
                currency=invoice.currency or "EUR",
                entity_id=entity.id if entity else None,
                entity_name=entity.name if entity else None,
                entity_iban=entity.iban if entity else None,
                confidence=confidence,
                match_type=ReconciliationMatchType.AUTO_EXACT,
                match_details={
                    "iban_match": True,
                    "amount_diff": float(amount_diff),
                },
            ))

        return candidates

    async def _match_by_reference(
        self,
        db: AsyncSession,
        tx: ImportedTransaction,
        company_id: UUID,
    ) -> List[MatchCandidate]:
        """Match by invoice reference number in transaction text."""
        if not tx.reference_text:
            return []

        # Extract potential invoice numbers
        invoice_numbers = self._extract_invoice_numbers(tx.reference_text)
        if not invoice_numbers:
            return []

        candidates = []
        for inv_num in invoice_numbers:
            # Search for matching invoice
            query = select(InvoiceTracking).where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.status.in_(["open", "overdue"]),
                    InvoiceTracking.deleted_at.is_(None),
                    InvoiceTracking.invoice_number.ilike(f"%{inv_num}%"),
                )
            )

            result = await db.execute(query)
            invoices = result.scalars().all()

            for invoice in invoices:
                # Calculate confidence based on amount match
                amount_diff = abs(Decimal(str(invoice.outstanding_amount)) - tx.amount)
                amount_tolerance = tx.amount * Decimal(str(self.config.amount_tolerance_percent))

                if amount_diff <= amount_tolerance:
                    confidence = 0.95 if amount_diff == 0 else 0.90
                else:
                    # Still suggest but with lower confidence
                    confidence = 0.70

                # Get entity info
                doc = await db.get(Document, invoice.document_id)
                entity = await db.get(BusinessEntity, doc.business_entity_id) if doc and doc.business_entity_id else None

                candidates.append(MatchCandidate(
                    invoice_id=invoice.id,
                    invoice_number=invoice.invoice_number,
                    invoice_date=invoice.invoice_date,
                    due_date=invoice.due_date,
                    invoice_amount=Decimal(str(invoice.amount)),
                    outstanding_amount=Decimal(str(invoice.outstanding_amount)),
                    currency=invoice.currency or "EUR",
                    entity_id=entity.id if entity else None,
                    entity_name=entity.name if entity else None,
                    entity_iban=entity.iban if entity else None,
                    confidence=confidence,
                    match_type=ReconciliationMatchType.AUTO_REFERENCE,
                    match_details={
                        "matched_reference": inv_num,
                        "invoice_number": invoice.invoice_number,
                        "amount_diff": float(amount_diff),
                    },
                ))

        return candidates

    async def _match_by_skonto(
        self,
        db: AsyncSession,
        tx: ImportedTransaction,
        company_id: UUID,
    ) -> List[MatchCandidate]:
        """Match by skonto deduction amount."""
        if not tx.counterparty_iban or tx.amount <= 0:
            return []

        # Find invoices with skonto for this IBAN
        query = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.status.in_(["open", "overdue"]),
                InvoiceTracking.deleted_at.is_(None),
                InvoiceTracking.skonto_percentage.isnot(None),
                InvoiceTracking.skonto_used == False,
            )
        ).join(
            Document,
            InvoiceTracking.document_id == Document.id
        ).join(
            BusinessEntity,
            Document.business_entity_id == BusinessEntity.id
        ).where(
            BusinessEntity.iban == tx.counterparty_iban
        )

        result = await db.execute(query)
        invoices = result.scalars().all()

        candidates = []
        for invoice in invoices:
            # Calculate expected skonto amount
            skonto_pct = Decimal(str(invoice.skonto_percentage or 0))
            invoice_amount = Decimal(str(invoice.outstanding_amount))
            expected_skonto_amount = invoice_amount * (1 - skonto_pct / 100)

            # Check if transaction matches skonto amount
            tolerance = expected_skonto_amount * Decimal(str(self.config.amount_tolerance_percent))
            amount_diff = abs(tx.amount - expected_skonto_amount)

            if amount_diff <= tolerance:
                # Get entity info
                doc = await db.get(Document, invoice.document_id)
                entity = await db.get(BusinessEntity, doc.business_entity_id) if doc and doc.business_entity_id else None

                candidates.append(MatchCandidate(
                    invoice_id=invoice.id,
                    invoice_number=invoice.invoice_number,
                    invoice_date=invoice.invoice_date,
                    due_date=invoice.due_date,
                    invoice_amount=Decimal(str(invoice.amount)),
                    outstanding_amount=Decimal(str(invoice.outstanding_amount)),
                    currency=invoice.currency or "EUR",
                    entity_id=entity.id if entity else None,
                    entity_name=entity.name if entity else None,
                    entity_iban=entity.iban if entity else None,
                    confidence=0.92,
                    match_type=ReconciliationMatchType.AUTO_SKONTO,
                    match_details={
                        "skonto_percentage": float(skonto_pct),
                        "expected_amount": float(expected_skonto_amount),
                        "actual_amount": float(tx.amount),
                    },
                ))

        return candidates

    async def _match_by_customer_number(
        self,
        db: AsyncSession,
        tx: ImportedTransaction,
        company_id: UUID,
        customer_numbers: List[str],
    ) -> List[MatchCandidate]:
        """Match by customer number found in reference."""
        candidates = []

        for cust_num in customer_numbers:
            # Find entities with matching customer number
            entity_query = select(BusinessEntity).where(
                and_(
                    BusinessEntity.company_id == company_id,
                    BusinessEntity.customer_number.ilike(f"%{cust_num}%"),
                    BusinessEntity.deleted_at.is_(None),
                )
            )

            result = await db.execute(entity_query)
            entities = list(result.scalars().all())

            for entity in entities:
                # Find open invoices for this entity
                invoice_query = select(InvoiceTracking).where(
                    and_(
                        InvoiceTracking.company_id == company_id,
                        InvoiceTracking.status.in_(["open", "overdue"]),
                        InvoiceTracking.deleted_at.is_(None),
                    )
                ).join(
                    Document,
                    InvoiceTracking.document_id == Document.id
                ).where(
                    Document.business_entity_id == entity.id
                )

                result = await db.execute(invoice_query)
                invoices = result.scalars().all()

                for invoice in invoices:
                    # Check amount match
                    amount_diff = abs(Decimal(str(invoice.outstanding_amount)) - tx.amount)
                    amount_tolerance = tx.amount * Decimal(str(self.config.amount_tolerance_percent * 2))

                    if amount_diff > amount_tolerance:
                        continue

                    confidence = 0.85 if amount_diff <= tx.amount * Decimal("0.01") else 0.75

                    candidates.append(MatchCandidate(
                        invoice_id=invoice.id,
                        invoice_number=invoice.invoice_number,
                        invoice_date=invoice.invoice_date,
                        due_date=invoice.due_date,
                        invoice_amount=Decimal(str(invoice.amount)),
                        outstanding_amount=Decimal(str(invoice.outstanding_amount)),
                        currency=invoice.currency or "EUR",
                        entity_id=entity.id,
                        entity_name=entity.name,
                        entity_iban=entity.iban,
                        confidence=confidence,
                        match_type=ReconciliationMatchType.AUTO_EXACT,
                        match_details={
                            "customer_number": cust_num,
                            "amount_diff": float(amount_diff),
                        },
                    ))

        return candidates

    async def _match_by_fuzzy_name(
        self,
        db: AsyncSession,
        tx: ImportedTransaction,
        company_id: UUID,
    ) -> List[MatchCandidate]:
        """Match by fuzzy name similarity."""
        if not tx.counterparty_name:
            return []

        tx_name = tx.counterparty_name.lower()

        # Get all entities for this company
        entity_query = select(BusinessEntity).where(
            and_(
                BusinessEntity.company_id == company_id,
                BusinessEntity.deleted_at.is_(None),
            )
        )

        result = await db.execute(entity_query)
        entities = list(result.scalars().all())

        matching_entities = []
        for entity in entities:
            if not entity.name:
                continue

            similarity = self._calculate_name_similarity(tx_name, entity.name.lower())
            if similarity >= 0.6:  # 60% similarity threshold
                matching_entities.append((entity, similarity))

        if not matching_entities:
            return []

        candidates = []
        for entity, name_similarity in matching_entities:
            # Find open invoices for this entity
            invoice_query = select(InvoiceTracking).where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.status.in_(["open", "overdue"]),
                    InvoiceTracking.deleted_at.is_(None),
                )
            ).join(
                Document,
                InvoiceTracking.document_id == Document.id
            ).where(
                Document.business_entity_id == entity.id
            )

            result = await db.execute(invoice_query)
            invoices = result.scalars().all()

            for invoice in invoices:
                # Check amount match
                amount_diff = abs(Decimal(str(invoice.outstanding_amount)) - tx.amount)
                amount_tolerance = tx.amount * Decimal(str(self.config.amount_tolerance_percent * 3))

                if amount_diff > amount_tolerance:
                    continue

                # Combined confidence from name + amount
                amount_factor = 1.0 if amount_diff == 0 else (1.0 - float(amount_diff) / float(tx.amount))
                confidence = 0.50 + (name_similarity * 0.25) + (amount_factor * 0.20)

                candidates.append(MatchCandidate(
                    invoice_id=invoice.id,
                    invoice_number=invoice.invoice_number,
                    invoice_date=invoice.invoice_date,
                    due_date=invoice.due_date,
                    invoice_amount=Decimal(str(invoice.amount)),
                    outstanding_amount=Decimal(str(invoice.outstanding_amount)),
                    currency=invoice.currency or "EUR",
                    entity_id=entity.id,
                    entity_name=entity.name,
                    entity_iban=entity.iban,
                    confidence=min(confidence, 0.85),  # Cap fuzzy matches
                    match_type=ReconciliationMatchType.AUTO_FUZZY,
                    match_details={
                        "name_similarity": name_similarity,
                        "tx_name": tx.counterparty_name,
                        "entity_name": entity.name,
                    },
                ))

        return candidates

    async def _apply_match(
        self,
        db: AsyncSession,
        tx: ImportedTransaction,
        match: MatchCandidate,
    ) -> None:
        """Apply a match to the transaction."""
        tx.reconciliation_status = "matched"
        tx.reconciliation_match_type = match.match_type.value
        tx.reconciliation_confidence = match.confidence
        tx.matched_invoice_id = match.invoice_id
        tx.matched_entity_id = match.entity_id
        tx.reconciled_at = utc_now()

        # Handle partial payment
        if tx.amount < match.outstanding_amount:
            tx.is_partial_payment = True
            tx.allocated_amount = tx.amount
            tx.remaining_amount = match.outstanding_amount - tx.amount

        # Update invoice
        invoice = await db.get(InvoiceTracking, match.invoice_id)
        if invoice:
            payment_amount = tx.amount
            invoice.outstanding_amount = float(Decimal(str(invoice.outstanding_amount)) - payment_amount)

            if invoice.outstanding_amount <= 0:
                # M13: Vorhersage-Feedback VOR dem paid-Uebergang erfassen. Leak-frei,
                # weil die Rechnung hier noch nicht 'paid' ist und damit nicht in die
                # Historie der Verzugs-Vorhersage einfliesst.
                await self._record_delay_feedback(db, invoice, tx, match.entity_id)
                invoice.status = "paid"
                invoice.outstanding_amount = 0

            # Handle skonto
            if match.match_type == ReconciliationMatchType.AUTO_SKONTO:
                invoice.skonto_used = True

        await db.flush()

    async def _record_delay_feedback(
        self,
        db: AsyncSession,
        invoice: InvoiceTracking,
        tx: ImportedTransaction,
        entity_id: Optional[UUID],
    ) -> None:
        """Persistiert Vorhersage-Feedback (predicted vs. actual Zahlungsverzug).

        M13: Macht den Cashflow-Backtest real, indem beim Uebergang einer Rechnung
        auf 'paid' die Verzugs-Vorhersage der Entity gegen den tatsaechlichen Verzug
        gespeichert wird (``PredictionFeedbackRecord``).

        Garantien:
        - **Leak-frei**: Aufruf erfolgt VOR dem paid-Uebergang; die aktuelle Rechnung
          ist damit noch nicht Teil der Vorhersage-Historie.
        - **Failure-isoliert**: Ein Fehler hier darf den Bank-Abgleich NIE abbrechen
          (try/except + SAVEPOINT via ``begin_nested``).
        - **Idempotent**: pro Rechnung genau ein Feedback (``prediction_id`` ist unique).

        Nur der automatische Abgleich (``_apply_match``) ist abgedeckt; manueller
        Match/Split bleiben bewusst aussen vor.
        """
        if entity_id is None or invoice.due_date is None:
            return
        payment_date = getattr(tx, "value_date", None) or getattr(tx, "booking_date", None)
        if payment_date is None:
            return

        try:
            from app.db.models_prediction_feedback import PredictionFeedbackRecord
            from app.services.ai.predictive_payment_service import (
                get_predictive_payment_service,
                PredictionFeedback,
            )

            prediction_id = f"recon-delay:{invoice.id}"

            # Idempotenz: pro Rechnung nur einmal Feedback erfassen.
            existing = await db.execute(
                select(PredictionFeedbackRecord.id).where(
                    PredictionFeedbackRecord.prediction_id == prediction_id
                )
            )
            if existing.scalar_one_or_none() is not None:
                return

            actual_delay_days = (payment_date - invoice.due_date).days

            predictive = get_predictive_payment_service()
            prediction = await predictive.predict_payment_delay(db, entity_id)

            feedback = PredictionFeedback(
                prediction_id=prediction_id,
                entity_id=entity_id,
                prediction_type="delay",
                predicted_value=float(prediction.predicted_delay_days),
                actual_value=float(actual_delay_days),
            )

            # SAVEPOINT: ein fehlgeschlagener Insert (z.B. Race auf den unique
            # prediction_id) wird isoliert zurueckgerollt, ohne die aeussere
            # Reconciliation-Transaktion zu vergiften.
            async with db.begin_nested():
                await predictive.record_prediction_feedback(
                    db, feedback, invoice.company_id
                )

            logger.info(
                "delay_feedback_recorded",
                entity_id=str(entity_id),
                predicted_delay_days=float(prediction.predicted_delay_days),
                actual_delay_days=float(actual_delay_days),
            )
        except Exception as e:  # noqa: BLE001 - Feedback darf Abgleich nie brechen
            logger.warning("delay_feedback_skipped", **safe_error_log(e))

    # =========================================================================
    # Batch Reconciliation
    # =========================================================================

    async def reconcile_pending_transactions(
        self,
        db: AsyncSession,
        company_id: UUID,
        limit: int = 100,
    ) -> BatchReconciliationResult:
        """Reconcile all pending transactions for a company."""
        # Get pending transactions
        query = select(ImportedTransaction).where(
            and_(
                ImportedTransaction.reconciliation_status == "pending",
                ImportedTransaction.amount > 0,  # Only incoming payments
            )
        ).join(
            ConnectedBankAccount,
            ImportedTransaction.account_id == ConnectedBankAccount.id
        ).join(
            BankConnection,
            ConnectedBankAccount.connection_id == BankConnection.id
        ).where(
            BankConnection.company_id == company_id
        ).order_by(
            ImportedTransaction.booking_date.desc()
        ).limit(limit)

        result = await db.execute(query)
        transactions = list(result.scalars().all())

        if not transactions:
            return BatchReconciliationResult()

        batch_result = BatchReconciliationResult(total_processed=len(transactions))

        for tx in transactions:
            try:
                result = await self.reconcile_transaction(
                    db=db,
                    transaction_id=tx.id,
                    company_id=company_id,
                    auto_apply=True,
                )

                batch_result.results.append(result)

                if result.matched:
                    if result.is_partial:
                        batch_result.partial_count += 1
                    else:
                        batch_result.matched_count += 1
                else:
                    batch_result.unmatched_count += 1

            except Exception as e:
                batch_result.error_count += 1
                logger.error(
                    "batch_reconcile_error",
                    transaction_id=str(tx.id),
                    **safe_error_log(e),
                )

        await db.commit()

        logger.info(
            "batch_reconciliation_completed",
            company_id=str(company_id),
            total=batch_result.total_processed,
            matched=batch_result.matched_count,
            partial=batch_result.partial_count,
            unmatched=batch_result.unmatched_count,
        )

        return batch_result

    # =========================================================================
    # Manual Operations
    # =========================================================================

    async def manual_match(
        self,
        db: AsyncSession,
        transaction_id: UUID,
        invoice_id: UUID,
        company_id: UUID,
        user_id: UUID,
        notes: Optional[str] = None,
    ) -> ReconciliationResult:
        """Manually match a transaction to an invoice."""
        tx = await self._get_transaction_with_account(db, transaction_id, company_id)
        if not tx:
            return ReconciliationResult(
                transaction_id=transaction_id,
                success=False,
                error_message="Transaktion nicht gefunden",
            )

        invoice = await db.get(InvoiceTracking, invoice_id)
        if not invoice or invoice.company_id != company_id:
            return ReconciliationResult(
                transaction_id=transaction_id,
                success=False,
                error_message="Rechnung nicht gefunden",
            )

        # Apply match
        tx.reconciliation_status = "matched"
        tx.reconciliation_match_type = ReconciliationMatchType.MANUAL.value
        tx.reconciliation_confidence = 1.0
        tx.matched_invoice_id = invoice_id
        tx.reconciled_at = utc_now()
        tx.reconciled_by_id = user_id

        # Handle partial
        outstanding = Decimal(str(invoice.outstanding_amount))
        if tx.amount < outstanding:
            tx.is_partial_payment = True
            tx.allocated_amount = tx.amount
            tx.remaining_amount = outstanding - tx.amount

        # Update invoice
        invoice.outstanding_amount = float(max(Decimal("0"), outstanding - tx.amount))
        if invoice.outstanding_amount <= 0:
            # M13: Vorhersage-Feedback VOR dem paid-Uebergang erfassen (leak-frei).
            await self._record_delay_feedback(db, invoice, tx, invoice.entity_id)
            invoice.status = "paid"

        await db.commit()

        RECONCILIATION_SUCCESS.labels(
            company_id=str(company_id),
            match_type="manual",
        ).inc()

        logger.info(
            "manual_match_applied",
            transaction_id=str(transaction_id),
            invoice_id=str(invoice_id),
            user_id=str(user_id),
        )

        return ReconciliationResult(
            transaction_id=transaction_id,
            success=True,
            matched=True,
            match_type=ReconciliationMatchType.MANUAL,
            confidence=1.0,
            invoice_id=invoice_id,
        )

    async def split_transaction(
        self,
        db: AsyncSession,
        transaction_id: UUID,
        company_id: UUID,
        user_id: UUID,
        allocations: List[Dict[str, Any]],  # [{invoice_id, amount}]
    ) -> ReconciliationResult:
        """Split a transaction across multiple invoices."""
        tx = await self._get_transaction_with_account(db, transaction_id, company_id)
        if not tx:
            return ReconciliationResult(
                transaction_id=transaction_id,
                success=False,
                error_message="Transaktion nicht gefunden",
            )

        # Validate allocations
        total_allocated = sum(Decimal(str(a["amount"])) for a in allocations)
        if abs(total_allocated - tx.amount) > Decimal("0.01"):
            return ReconciliationResult(
                transaction_id=transaction_id,
                success=False,
                error_message=f"Summe der Zuordnungen ({total_allocated}) stimmt nicht mit Transaktionsbetrag ({tx.amount})",
            )

        # Create allocations
        for alloc in allocations:
            invoice = await db.get(InvoiceTracking, UUID(alloc["invoice_id"]))
            if not invoice or invoice.company_id != company_id:
                return ReconciliationResult(
                    transaction_id=transaction_id,
                    success=False,
                    error_message=f"Rechnung {alloc['invoice_id']} nicht gefunden",
                )

            split = TransactionSplitAllocation(
                transaction_id=transaction_id,
                invoice_id=invoice.id,
                allocated_amount=Decimal(str(alloc["amount"])),
                currency=tx.currency,
                match_method="manual_split",
                created_by_id=user_id,
            )
            db.add(split)

            # Update invoice
            invoice.outstanding_amount = float(
                max(Decimal("0"), Decimal(str(invoice.outstanding_amount)) - Decimal(str(alloc["amount"])))
            )
            if invoice.outstanding_amount <= 0:
                # M13: Vorhersage-Feedback VOR dem paid-Uebergang erfassen (leak-frei).
                await self._record_delay_feedback(db, invoice, tx, invoice.entity_id)
                invoice.status = "paid"

        # Update transaction
        tx.reconciliation_status = "matched"
        tx.reconciliation_match_type = ReconciliationMatchType.SPLIT.value
        tx.reconciliation_confidence = 1.0
        tx.reconciled_at = utc_now()
        tx.reconciled_by_id = user_id

        await db.commit()

        logger.info(
            "transaction_split_applied",
            transaction_id=str(transaction_id),
            split_count=len(allocations),
        )

        return ReconciliationResult(
            transaction_id=transaction_id,
            success=True,
            matched=True,
            match_type=ReconciliationMatchType.SPLIT,
            confidence=1.0,
        )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _get_transaction_with_account(
        self,
        db: AsyncSession,
        transaction_id: UUID,
        company_id: UUID,
    ) -> Optional[ImportedTransaction]:
        """Get transaction with company validation."""
        query = select(ImportedTransaction).where(
            ImportedTransaction.id == transaction_id
        ).join(
            ConnectedBankAccount,
            ImportedTransaction.account_id == ConnectedBankAccount.id
        ).join(
            BankConnection,
            ConnectedBankAccount.connection_id == BankConnection.id
        ).where(
            BankConnection.company_id == company_id
        )

        result = await db.execute(query)
        return result.scalar_one_or_none()

    def _extract_invoice_numbers(self, text: str) -> List[str]:
        """Extract potential invoice numbers from text."""
        patterns = [
            r"(?:RE|INV|RG|RECH)[- ]?(\d{4,12})",
            r"Rechnung[- ]?Nr[.:]*\s*(\d{4,12})",
            r"Invoice[- ]?No[.:]*\s*(\d{4,12})",
            r"(\d{4}[-/]\d{4,8})",  # Format like 2024-12345
        ]

        found = set()
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            found.update(matches)

        return list(found)

    def _extract_customer_numbers(self, text: str) -> List[str]:
        """Extract potential customer numbers from text."""
        patterns = [
            r"(?:KD|KNR|KUNDEN)[- ]?(?:NR)?[.:]*\s*(\d{4,10})",
            r"Kundennummer[.:]*\s*(\d{4,10})",
        ]

        found = set()
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            found.update(matches)

        return list(found)

    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        """Calculate Jaccard similarity between two names."""
        words1 = set(name1.split())
        words2 = set(name2.split())

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2

        return len(intersection) / len(union)


# Need to import these for type hints
from app.db.models_banking_connection import ConnectedBankAccount, BankConnection


# =============================================================================
# Factory
# =============================================================================

_service_instance: Optional[AutoReconciliationService] = None


def get_auto_reconciliation_service(
    config: Optional[ReconciliationConfig] = None,
) -> AutoReconciliationService:
    """Get auto reconciliation service instance."""
    global _service_instance

    if _service_instance is None or config is not None:
        _service_instance = AutoReconciliationService(config=config)

    return _service_instance
