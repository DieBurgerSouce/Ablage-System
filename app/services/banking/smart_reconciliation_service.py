# -*- coding: utf-8 -*-
"""
Smart Reconciliation Service - Automatischer Zahlungsabgleich.

Gleicht Banktransaktionen automatisch mit offenen Rechnungen ab:
- IBAN-Matching
- Referenznummern im Verwendungszweck
- Skonto-Erkennung
- Teilzahlungs-Support

Mit vollständiger Erklärbarkeit jeder Zuordnung.

Vision 2026 Q2 - Smart Bank Reconciliation
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BankTransaction, InvoiceTracking, BusinessEntity
from app.core.security.sensitive_data_filter import get_pii_safe_logger
from app.core.safe_errors import safe_error_log

logger = get_pii_safe_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

RECONCILIATION_ATTEMPTS = Counter(
    "reconciliation_attempts_total",
    "Anzahl Reconciliation-Versuche",
    ["result"]  # auto_matched, suggested, no_match
)

RECONCILIATION_CONFIDENCE = Histogram(
    "reconciliation_confidence",
    "Verteilung der Reconciliation-Confidence",
    ["strategy"],
    buckets=[0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0]
)

RECONCILIATION_PROCESSING_TIME = Histogram(
    "reconciliation_processing_seconds",
    "Verarbeitungszeit für Reconciliation",
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0]
)


# =============================================================================
# Enums
# =============================================================================

class ReconciliationStrategy(str, Enum):
    """Reconciliation-Strategien nach Priorität."""
    IBAN_EXACT = "iban_exact"                  # IBAN des Absenders stimmt (99%)
    REFERENCE_IN_TEXT = "reference_in_text"    # Rechnungsnummer im Verwendungszweck (95%)
    AMOUNT_EXACT = "amount_exact"              # Betrag exakt (90%)
    AMOUNT_SKONTO = "amount_skonto"            # Betrag = Skonto-Abzug (85%)
    AMOUNT_PARTIAL = "amount_partial"          # Teilzahlung erkannt (80%)
    NAME_FUZZY = "name_fuzzy"                  # Absendername ähnlich (70%)


class ReconciliationAction(str, Enum):
    """Empfohlene Aktion nach Reconciliation."""
    AUTO_MATCH = "auto_match"                  # Automatisch zuordnen (>=85%)
    SUGGEST = "suggest"                        # Vorschlagen, manuell bestätigen
    MANUAL_REVIEW = "manual_review"            # Manuelle Prüfung erforderlich
    NO_MATCH = "no_match"                      # Keine passende Rechnung


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ReconciliationMatch:
    """Ein möglicher Match für eine Transaktion."""
    invoice_id: UUID
    invoice_number: str = ""
    entity_name: str = ""

    # Beträge
    invoice_amount: Decimal = Decimal("0")
    transaction_amount: Decimal = Decimal("0")
    difference: Decimal = Decimal("0")

    # Match-Details
    strategy: ReconciliationStrategy = ReconciliationStrategy.AMOUNT_EXACT
    confidence: float = 0.0
    is_skonto: bool = False
    is_partial: bool = False

    # Erklärung
    explanation: str = ""
    factors: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "invoice_id": str(self.invoice_id),
            "invoice_number": self.invoice_number,
            "entity_name": self.entity_name,
            "invoice_amount": float(self.invoice_amount),
            "transaction_amount": float(self.transaction_amount),
            "difference": float(self.difference),
            "strategy": self.strategy.value,
            "confidence": self.confidence,
            "is_skonto": self.is_skonto,
            "is_partial": self.is_partial,
            "explanation": self.explanation,
            "factors": self.factors,
        }


@dataclass
class ReconciliationResult:
    """Ergebnis einer Reconciliation."""
    id: UUID = field(default_factory=uuid4)
    transaction_id: UUID = field(default_factory=uuid4)

    # Empfohlene Aktion
    action: ReconciliationAction = ReconciliationAction.NO_MATCH
    auto_matched: bool = False

    # Best Match
    best_match: Optional[ReconciliationMatch] = None

    # Alle Vorschläge
    suggestions: List[ReconciliationMatch] = field(default_factory=list)

    # Erklärung
    explanation: str = ""

    # Timing
    processing_time_ms: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "id": str(self.id),
            "transaction_id": str(self.transaction_id),
            "action": self.action.value,
            "auto_matched": self.auto_matched,
            "best_match": self.best_match.to_dict() if self.best_match else None,
            "suggestions": [s.to_dict() for s in self.suggestions],
            "explanation": self.explanation,
            "processing_time_ms": self.processing_time_ms,
            "created_at": self.created_at.isoformat(),
        }


# =============================================================================
# Smart Reconciliation Service
# =============================================================================

class SmartReconciliationService:
    """
    Automatischer Zahlungsabgleich mit Erklärung.

    Matching-Regeln (nach Priorität):
    1. IBAN des Absenders stimmt mit Kunde überein (99%)
    2. Rechnungsnummer im Verwendungszweck (95%)
    3. Betrag exakt übereinstimmend (90%)
    4. Betrag entspricht Skonto-Abzug (85%)
    5. Teilzahlung erkannt (80%)
    6. Absendername ähnlich zu Kundenname (70%)
    """

    # Confidence-Schwellen
    AUTO_MATCH_THRESHOLD = 0.85
    SUGGESTION_THRESHOLD = 0.70

    # Toleranzen
    AMOUNT_TOLERANCE = Decimal("0.02")  # 2 Cent Toleranz für Rundungsfehler

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Service."""
        self.db = db

    async def reconcile(
        self,
        transaction_id: UUID,
        company_id: UUID,
    ) -> ReconciliationResult:
        """
        Reconciliation für eine einzelne Transaktion.

        Args:
            transaction_id: ID der Banktransaktion
            company_id: Mandant-ID

        Returns:
            ReconciliationResult mit Match-Vorschlägen
        """
        start_time = datetime.now(timezone.utc)
        result = ReconciliationResult(transaction_id=transaction_id)

        try:
            # Transaktion laden
            transaction = await self._get_transaction(transaction_id)
            if not transaction:
                result.explanation = "Transaktion nicht gefunden"
                RECONCILIATION_ATTEMPTS.labels(result="no_match").inc()
                return result

            # Nur Eingänge reconcilen
            if transaction.amount < 0:
                result.explanation = "Nur Zahlungseingänge werden abgeglichen"
                return result

            # Offene Rechnungen laden
            open_invoices = await self._get_open_invoices(company_id)
            if not open_invoices:
                result.explanation = "Keine offenen Rechnungen vorhanden"
                RECONCILIATION_ATTEMPTS.labels(result="no_match").inc()
                return result

            # Matching durchführen
            matches: List[ReconciliationMatch] = []

            for invoice in open_invoices:
                match = await self._evaluate_match(transaction, invoice)
                if match and match.confidence >= self.SUGGESTION_THRESHOLD:
                    matches.append(match)

            # Sortieren nach Confidence
            matches.sort(key=lambda m: m.confidence, reverse=True)

            # Ergebnis zusammenstellen
            if matches:
                result.best_match = matches[0]
                result.suggestions = matches[:5]  # Top 5

                if matches[0].confidence >= self.AUTO_MATCH_THRESHOLD:
                    result.action = ReconciliationAction.AUTO_MATCH
                    result.auto_matched = True
                    result.explanation = (
                        f"Automatisch zugeordnet: {matches[0].explanation}"
                    )
                    RECONCILIATION_ATTEMPTS.labels(result="auto_matched").inc()
                else:
                    result.action = ReconciliationAction.SUGGEST
                    result.explanation = (
                        f"Vorschlag: {matches[0].explanation} "
                        f"(Konfidenz unter 85%, manuelle Bestätigung erforderlich)"
                    )
                    RECONCILIATION_ATTEMPTS.labels(result="suggested").inc()

                RECONCILIATION_CONFIDENCE.labels(
                    strategy=matches[0].strategy.value
                ).observe(matches[0].confidence)

            else:
                result.action = ReconciliationAction.NO_MATCH
                result.explanation = "Keine passende offene Rechnung gefunden"
                RECONCILIATION_ATTEMPTS.labels(result="no_match").inc()

        except Exception as e:
            result.action = ReconciliationAction.MANUAL_REVIEW
            result.explanation = f"Fehler bei Reconciliation: {str(e)}"
            logger.error(
                "reconciliation_error",
                transaction_id=str(transaction_id),
                **safe_error_log(e),
            )

        # Timing
        end_time = datetime.now(timezone.utc)
        result.processing_time_ms = int(
            (end_time - start_time).total_seconds() * 1000
        )
        RECONCILIATION_PROCESSING_TIME.observe(result.processing_time_ms / 1000)

        logger.info(
            "reconciliation_completed",
            transaction_id=str(transaction_id),
            action=result.action.value,
            auto_matched=result.auto_matched,
            matches_found=len(result.suggestions),
        )

        return result

    async def reconcile_batch(
        self,
        company_id: UUID,
        transaction_ids: Optional[List[UUID]] = None,
        days_back: int = 30,
    ) -> List[ReconciliationResult]:
        """
        Batch-Reconciliation für mehrere Transaktionen.

        Args:
            company_id: Mandant-ID
            transaction_ids: Optional - Spezifische Transaktionen
            days_back: Tage zurück für automatische Suche

        Returns:
            Liste von ReconciliationResults
        """
        results: List[ReconciliationResult] = []

        if transaction_ids:
            transactions = await self._get_transactions_by_ids(transaction_ids)
        else:
            # Unreconciled Transaktionen der letzten X Tage
            transactions = await self._get_unreconciled_transactions(
                company_id, days_back
            )

        for transaction in transactions:
            result = await self.reconcile(transaction.id, company_id)
            results.append(result)

        return results

    # =========================================================================
    # Match Evaluation
    # =========================================================================

    async def _evaluate_match(
        self,
        transaction: BankTransaction,
        invoice: InvoiceTracking,
    ) -> Optional[ReconciliationMatch]:
        """
        Evaluiert einen Match zwischen Transaktion und Rechnung.

        Wendet alle Strategien an und gibt den besten Match zurück.
        """
        match = ReconciliationMatch(
            invoice_id=invoice.id,
            invoice_number=invoice.invoice_number or "",
            invoice_amount=invoice.gross_amount or Decimal("0"),
            transaction_amount=transaction.amount,
        )

        # Entity-Name laden
        if invoice.business_entity_id:
            entity = await self._get_entity(invoice.business_entity_id)
            match.entity_name = entity.name if entity else ""

        # Faktoren sammeln
        factors: List[Tuple[ReconciliationStrategy, float, str]] = []

        # Strategy 1: IBAN-Match
        iban_confidence = await self._check_iban_match(transaction, invoice)
        if iban_confidence > 0:
            factors.append((
                ReconciliationStrategy.IBAN_EXACT,
                iban_confidence,
                f"IBAN des Absenders stimmt überein"
            ))

        # Strategy 2: Referenznummer im Verwendungszweck
        ref_confidence = self._check_reference_match(
            transaction.purpose or "",
            invoice.invoice_number or ""
        )
        if ref_confidence > 0:
            factors.append((
                ReconciliationStrategy.REFERENCE_IN_TEXT,
                ref_confidence,
                f"Rechnungsnummer '{invoice.invoice_number}' im Verwendungszweck"
            ))

        # Strategy 3-5: Betrags-Match
        amount_match = self._check_amount_match(transaction, invoice)
        if amount_match:
            factors.append(amount_match)

        # Strategy 6: Name-Match
        name_confidence = self._check_name_match(
            transaction.sender_name or "",
            match.entity_name
        )
        if name_confidence > 0:
            factors.append((
                ReconciliationStrategy.NAME_FUZZY,
                name_confidence,
                f"Absendername ähnlich: {transaction.sender_name}"
            ))

        if not factors:
            return None

        # Beste Strategie auswählen
        best_factor = max(factors, key=lambda f: f[1])
        match.strategy = best_factor[0]
        match.confidence = best_factor[1]
        match.explanation = best_factor[2]

        # Alle Faktoren für Erklärung
        match.factors = [
            {
                "strategy": f[0].value,
                "confidence": f[1],
                "explanation": f[2],
            }
            for f in sorted(factors, key=lambda x: x[1], reverse=True)
        ]

        # Betragsabweichung
        match.difference = transaction.amount - (invoice.outstanding_amount or invoice.gross_amount or Decimal("0"))

        return match

    async def _check_iban_match(
        self,
        transaction: BankTransaction,
        invoice: InvoiceTracking,
    ) -> float:
        """Prüft IBAN-Übereinstimmung."""
        if not transaction.sender_iban or not invoice.business_entity_id:
            return 0.0

        entity = await self._get_entity(invoice.business_entity_id)
        if not entity or not entity.iban:
            return 0.0

        # Normalisieren und vergleichen
        trans_iban = transaction.sender_iban.replace(" ", "").upper()
        entity_iban = entity.iban.replace(" ", "").upper()

        if trans_iban == entity_iban:
            return 0.99  # 99% Confidence

        return 0.0

    def _check_reference_match(
        self,
        purpose: str,
        invoice_number: str,
    ) -> float:
        """Prüft Referenznummer im Verwendungszweck."""
        if not purpose or not invoice_number:
            return 0.0

        # Normalisieren
        purpose_clean = re.sub(r"[\s\-\./]", "", purpose.upper())
        invoice_clean = re.sub(r"[\s\-\./]", "", invoice_number.upper())

        if invoice_clean in purpose_clean:
            return 0.95  # 95% Confidence

        # Teilweise Match
        if len(invoice_clean) >= 5:
            # Mindestens 5 Zeichen in Folge müssen matchen
            for i in range(len(invoice_clean) - 4):
                substring = invoice_clean[i:i+5]
                if substring in purpose_clean:
                    return 0.80  # 80% für Teilmatch

        return 0.0

    def _check_amount_match(
        self,
        transaction: BankTransaction,
        invoice: InvoiceTracking,
    ) -> Optional[Tuple[ReconciliationStrategy, float, str]]:
        """Prüft Betrags-Übereinstimmung (exakt, Skonto, Teilzahlung)."""
        trans_amount = transaction.amount
        invoice_amount = invoice.outstanding_amount or invoice.gross_amount or Decimal("0")

        if invoice_amount <= 0:
            return None

        # Exakter Match (mit kleiner Toleranz)
        if abs(trans_amount - invoice_amount) <= self.AMOUNT_TOLERANCE:
            return (
                ReconciliationStrategy.AMOUNT_EXACT,
                0.90,
                f"Betrag exakt: {trans_amount:.2f} EUR"
            )

        # Skonto-Match
        if invoice.skonto_percentage and invoice.skonto_deadline:
            skonto_amount = invoice_amount * (1 - Decimal(str(invoice.skonto_percentage)) / 100)
            if abs(trans_amount - skonto_amount) <= self.AMOUNT_TOLERANCE:
                return (
                    ReconciliationStrategy.AMOUNT_SKONTO,
                    0.85,
                    f"Skonto-Betrag: {trans_amount:.2f} EUR ({invoice.skonto_percentage}% Skonto)"
                )

        # Teilzahlung (40-99% des Betrags)
        if Decimal("0.4") * invoice_amount <= trans_amount < invoice_amount:
            percentage = (trans_amount / invoice_amount) * 100
            return (
                ReconciliationStrategy.AMOUNT_PARTIAL,
                0.80,
                f"Teilzahlung: {trans_amount:.2f} EUR ({percentage:.0f}% von {invoice_amount:.2f} EUR)"
            )

        return None

    def _check_name_match(
        self,
        sender_name: str,
        entity_name: str,
    ) -> float:
        """Prüft Namens-Ähnlichkeit."""
        if not sender_name or not entity_name:
            return 0.0

        # Normalisieren
        sender_clean = self._normalize_name(sender_name)
        entity_clean = self._normalize_name(entity_name)

        # Exakter Match nach Normalisierung
        if sender_clean == entity_clean:
            return 0.85

        # Teilstring-Match
        if len(entity_clean) >= 5:
            if entity_clean in sender_clean or sender_clean in entity_clean:
                return 0.75

        # Wort-basierter Match
        sender_words = set(sender_clean.split())
        entity_words = set(entity_clean.split())

        if len(entity_words) > 0:
            overlap = sender_words & entity_words
            overlap_ratio = len(overlap) / len(entity_words)

            if overlap_ratio >= 0.5:
                return 0.70 * overlap_ratio

        return 0.0

    def _normalize_name(self, name: str) -> str:
        """Normalisiert einen Namen für Vergleich."""
        # Lowercase
        name = name.lower()

        # Rechtsformen entfernen
        suffixes = [
            "gmbh", "ag", "kg", "ohg", "gbr", "ug", "e.v.", "mbh",
            "gmbh & co. kg", "gmbh & co kg", "co.", "co"
        ]
        for suffix in suffixes:
            name = name.replace(suffix, "")

        # Sonderzeichen entfernen, Umlaute erhalten
        name = re.sub(r"[^\wäöüß]", " ", name)

        # Mehrfache Leerzeichen entfernen
        name = " ".join(name.split())

        return name.strip()

    # =========================================================================
    # Database Access
    # =========================================================================

    async def _get_transaction(self, transaction_id: UUID) -> Optional[BankTransaction]:
        """Lädt eine Transaktion."""
        stmt = select(BankTransaction).where(BankTransaction.id == transaction_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def _get_transactions_by_ids(
        self,
        transaction_ids: List[UUID],
    ) -> List[BankTransaction]:
        """Lädt mehrere Transaktionen."""
        stmt = select(BankTransaction).where(
            BankTransaction.id.in_(transaction_ids)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _get_unreconciled_transactions(
        self,
        company_id: UUID,
        days_back: int,
    ) -> List[BankTransaction]:
        """Lädt nicht-reconciled Transaktionen."""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)

        stmt = select(BankTransaction).where(
            and_(
                BankTransaction.company_id == company_id,
                BankTransaction.amount > 0,  # Nur Eingänge
                BankTransaction.reconciled == False,
                BankTransaction.booking_date >= cutoff_date,
            )
        ).order_by(BankTransaction.booking_date.desc())

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _get_open_invoices(self, company_id: UUID) -> List[InvoiceTracking]:
        """Lädt offene Rechnungen."""
        stmt = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.is_paid == False,
                InvoiceTracking.is_outgoing == True,  # Nur Ausgangsrechnungen
            )
        ).order_by(InvoiceTracking.due_date.asc())

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _get_entity(self, entity_id: UUID) -> Optional[BusinessEntity]:
        """Lädt eine Entity."""
        stmt = select(BusinessEntity).where(BusinessEntity.id == entity_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()


# =============================================================================
# Factory
# =============================================================================

def get_smart_reconciliation_service(db: AsyncSession) -> SmartReconciliationService:
    """Factory-Funktion für SmartReconciliationService."""
    return SmartReconciliationService(db)
