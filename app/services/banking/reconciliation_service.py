"""Reconciliation Service.

Automatischer Zahlungsabgleich zwischen Banktransaktionen und Rechnungen.

Matching-Strategien (nach Priorität):
1. IBAN + Betrag exakt → 0.99 Konfidenz
2. Rechnungsnummer im Verwendungszweck + Betrag → 0.95
3. Kundennummer + Betrag + Datum-Naehe → 0.85
4. Betrag + Datum-Naehe (±3 Tage) → 0.75
5. Fuzzy Verwendungszweck + Betrag-Toleranz → 0.65
"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log
from decimal import Decimal, InvalidOperation
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
import re
import structlog

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    ReconciliationStatus,
    TransactionMatch,
    ReconciliationResult,
    BatchReconciliationResult,
)
from .reference_parser import reference_parser

logger = structlog.get_logger(__name__)


@dataclass
class MatchCandidate:
    """Ein möglicher Match-Kandidat."""
    document_id: UUID
    invoice_number: Optional[str]
    invoice_date: Optional[date]
    due_date: Optional[date]
    gross_amount: Decimal
    counterparty_name: Optional[str]
    counterparty_iban: Optional[str]
    customer_number: Optional[str]
    confidence: float
    match_method: str
    match_details: Dict[str, Any] = field(default_factory=dict)


class ReconciliationService:
    """Service für automatischen Zahlungsabgleich."""

    # Konfidenz-Schwellenwerte
    AUTO_MATCH_THRESHOLD = 0.90  # Ab hier automatisch matchen
    SUGGESTION_THRESHOLD = 0.50  # Ab hier als Vorschlag zeigen

    # Toleranzen
    AMOUNT_TOLERANCE_PERCENT = 0.01  # 1% Toleranz für Betragsabweichung
    DATE_TOLERANCE_DAYS = 5  # Tage-Toleranz für Datumsnaehe

    async def find_matches(
        self,
        db: AsyncSession,
        company_id: UUID,
        transaction_id: UUID,
        limit: int = 5,
    ) -> List[MatchCandidate]:
        """Finde mögliche Matches für eine Transaktion.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            transaction_id: Transaktions-ID
            limit: Max. Anzahl Vorschläge

        Returns:
            Liste von MatchCandidates, sortiert nach Konfidenz
        """
        from app.db.models import BankTransaction, BankAccount, Document

        # Hole Transaktion
        tx_query = (
            select(BankTransaction)
            .join(BankAccount)
            .where(
                and_(
                    BankTransaction.id == transaction_id,
                    BankAccount.company_id == company_id,
                )
            )
        )
        tx_result = await db.execute(tx_query)
        transaction = tx_result.scalar_one_or_none()

        if not transaction:
            return []

        # Parse Verwendungszweck für Referenzen
        parsed_ref = reference_parser.parse(transaction.reference_text or "")

        # Sammle Kandidaten aus verschiedenen Strategien
        candidates: List[MatchCandidate] = []

        # Strategie 1: IBAN + Betrag exakt
        if transaction.counterparty_iban:
            iban_matches = await self._match_by_iban_amount(
                db, company_id, transaction, transaction.counterparty_iban
            )
            candidates.extend(iban_matches)

        # Strategie 2: Rechnungsnummer + Betrag
        if parsed_ref.invoice_numbers:
            invoice_matches = await self._match_by_invoice_number(
                db, company_id, transaction, parsed_ref.invoice_numbers
            )
            candidates.extend(invoice_matches)

        # Strategie 3: Kundennummer + Betrag + Datum
        if parsed_ref.customer_numbers:
            customer_matches = await self._match_by_customer_number(
                db, company_id, transaction, parsed_ref.customer_numbers
            )
            candidates.extend(customer_matches)

        # Strategie 4: Betrag + Datum-Naehe
        amount_date_matches = await self._match_by_amount_date(
            db, company_id, transaction
        )
        candidates.extend(amount_date_matches)

        # Strategie 5: Fuzzy Name-Matching
        if transaction.counterparty_name:
            fuzzy_matches = await self._match_by_fuzzy_name(
                db, company_id, transaction
            )
            candidates.extend(fuzzy_matches)

        # Dedupliziere und sortiere nach Konfidenz
        unique_candidates = self._deduplicate_candidates(candidates)
        unique_candidates.sort(key=lambda c: c.confidence, reverse=True)

        return unique_candidates[:limit]

    async def auto_reconcile_transaction(
        self,
        db: AsyncSession,
        company_id: UUID,
        transaction_id: UUID,
    ) -> Optional[ReconciliationResult]:
        """Versuche automatischen Abgleich einer Transaktion.

        Matched nur wenn Konfidenz >= AUTO_MATCH_THRESHOLD.

        Returns:
            ReconciliationResult wenn Match gefunden, sonst None
        """
        from app.db.models import BankTransaction, BankAccount

        candidates = await self.find_matches(db, company_id, transaction_id)

        if not candidates:
            return None

        best_match = candidates[0]

        if best_match.confidence < self.AUTO_MATCH_THRESHOLD:
            logger.info(
                "auto_reconcile_below_threshold",
                transaction_id=str(transaction_id),
                best_confidence=best_match.confidence,
                threshold=self.AUTO_MATCH_THRESHOLD,
            )
            return None

        # Hole Transaktion und update Status
        tx_query = (
            select(BankTransaction)
            .join(BankAccount)
            .where(
                and_(
                    BankTransaction.id == transaction_id,
                    BankAccount.company_id == company_id,
                )
            )
        )
        tx_result = await db.execute(tx_query)
        transaction = tx_result.scalar_one_or_none()

        if not transaction:
            return None

        # Update Transaktion
        transaction.reconciliation_status = ReconciliationStatus.MATCHED.value
        transaction.matched_document_id = best_match.document_id
        transaction.match_confidence = best_match.confidence
        transaction.matched_at = utc_now()
        transaction.updated_at = utc_now()

        await db.commit()

        logger.info(
            "auto_reconcile_success",
            transaction_id=str(transaction_id),
            document_id=str(best_match.document_id),
            confidence=best_match.confidence,
            method=best_match.match_method,
        )

        return ReconciliationResult(
            transaction_id=transaction_id,
            status=ReconciliationStatus.MATCHED,
            matched_document_id=best_match.document_id,
            match_confidence=best_match.confidence,
            match_method=best_match.match_method,
        )

    async def batch_reconcile(
        self,
        db: AsyncSession,
        company_id: UUID,
        bank_account_id: Optional[UUID] = None,
        limit: int = 100,
    ) -> BatchReconciliationResult:
        """Führe Batch-Abgleich für ungematchte Transaktionen durch.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            bank_account_id: Optional Filter auf Bankkonto
            limit: Max. Transaktionen pro Durchlauf

        Returns:
            BatchReconciliationResult mit Statistiken
        """
        from app.db.models import BankTransaction, BankAccount

        # Hole ungematchte Transaktionen
        query = (
            select(BankTransaction)
            .join(BankAccount)
            .where(
                and_(
                    BankAccount.company_id == company_id,
                    BankAccount.deleted_at.is_(None),
                    BankTransaction.reconciliation_status == ReconciliationStatus.UNMATCHED.value,
                )
            )
            .limit(limit)
        )

        if bank_account_id:
            query = query.where(BankTransaction.bank_account_id == bank_account_id)

        result = await db.execute(query)
        transactions = result.scalars().all()

        results: List[ReconciliationResult] = []
        matched_count = 0
        partial_count = 0
        unmatched_count = 0

        for tx in transactions:
            try:
                match_result = await self.auto_reconcile_transaction(
                    db, company_id, tx.id
                )

                if match_result:
                    results.append(match_result)
                    if match_result.status == ReconciliationStatus.MATCHED:
                        matched_count += 1
                    elif match_result.status == ReconciliationStatus.PARTIAL:
                        partial_count += 1
                else:
                    unmatched_count += 1

            except Exception as e:
                logger.warning(
                    "batch_reconcile_error",
                    transaction_id=str(tx.id),
                    **safe_error_log(e),
                )
                unmatched_count += 1

        return BatchReconciliationResult(
            total_processed=len(transactions),
            matched_count=matched_count,
            partial_count=partial_count,
            unmatched_count=unmatched_count,
            results=results,
        )

    async def manual_match(
        self,
        db: AsyncSession,
        company_id: UUID,
        transaction_id: UUID,
        document_id: UUID,
        notes: Optional[str] = None,
    ) -> ReconciliationResult:
        """Manuelles Matching einer Transaktion mit einem Dokument.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            transaction_id: Transaktions-ID
            document_id: Dokument-ID
            notes: Optionale Notizen

        Returns:
            ReconciliationResult
        """
        from app.db.models import BankTransaction, BankAccount, Document

        # Verifiziere Transaktion gehoert User
        tx_query = (
            select(BankTransaction)
            .join(BankAccount)
            .where(
                and_(
                    BankTransaction.id == transaction_id,
                    BankAccount.company_id == company_id,
                )
            )
        )
        tx_result = await db.execute(tx_query)
        transaction = tx_result.scalar_one_or_none()

        if not transaction:
            raise ValueError("Transaktion nicht gefunden")

        # Verifiziere Dokument gehoert User
        doc_query = select(Document).where(
            and_(
                Document.id == document_id,
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
            )
        )
        doc_result = await db.execute(doc_query)
        document = doc_result.scalar_one_or_none()

        if not document:
            raise ValueError("Dokument nicht gefunden")

        # Update Transaktion
        transaction.reconciliation_status = ReconciliationStatus.MATCHED.value
        transaction.matched_document_id = document_id
        transaction.match_confidence = 1.0  # Manuell = 100%
        transaction.matched_at = utc_now()
        transaction.updated_at = utc_now()

        if notes:
            transaction.notes = notes

        await db.commit()

        logger.info(
            "manual_match_success",
            transaction_id=str(transaction_id),
            document_id=str(document_id),
            company_id=str(company_id),
        )

        return ReconciliationResult(
            transaction_id=transaction_id,
            status=ReconciliationStatus.MATCHED,
            matched_document_id=document_id,
            match_confidence=1.0,
            match_method="manual",
        )

    async def unmatch_transaction(
        self,
        db: AsyncSession,
        company_id: UUID,
        transaction_id: UUID,
    ) -> bool:
        """Entferne Match von einer Transaktion.

        Returns:
            True wenn erfolgreich
        """
        from app.db.models import BankTransaction, BankAccount

        tx_query = (
            select(BankTransaction)
            .join(BankAccount)
            .where(
                and_(
                    BankTransaction.id == transaction_id,
                    BankAccount.company_id == company_id,
                )
            )
        )
        tx_result = await db.execute(tx_query)
        transaction = tx_result.scalar_one_or_none()

        if not transaction:
            return False

        transaction.reconciliation_status = ReconciliationStatus.UNMATCHED.value
        transaction.matched_document_id = None
        transaction.match_confidence = None
        transaction.matched_at = None
        transaction.updated_at = utc_now()

        await db.commit()

        logger.info(
            "unmatch_success",
            transaction_id=str(transaction_id),
            company_id=str(company_id),
        )

        return True

    async def split_transaction(
        self,
        db: AsyncSession,
        company_id: UUID,
        transaction_id: UUID,
        splits: List[Dict[str, Any]],
    ) -> List[ReconciliationResult]:
        """Teile eine Transaktion auf mehrere Dokumente auf.

        Für Teilzahlungen oder Sammelzahlungen.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            transaction_id: Transaktions-ID
            splits: Liste von {document_id, amount, notes}

        Returns:
            Liste von ReconciliationResults
        """
        from app.db.models import BankTransaction, BankAccount

        # Hole Transaktion
        tx_query = (
            select(BankTransaction)
            .join(BankAccount)
            .where(
                and_(
                    BankTransaction.id == transaction_id,
                    BankAccount.company_id == company_id,
                )
            )
        )
        tx_result = await db.execute(tx_query)
        transaction = tx_result.scalar_one_or_none()

        if not transaction:
            raise ValueError("Transaktion nicht gefunden")

        # Validiere Gesamtbetrag
        total_split = sum(Decimal(str(s["amount"])) for s in splits)
        if abs(total_split - abs(transaction.amount)) > Decimal("0.01"):
            raise ValueError(
                f"Summe der Splits ({total_split}) stimmt nicht mit "
                f"Transaktionsbetrag ({abs(transaction.amount)}) überein"
            )

        # SECURITY: Validiere dass ALLE Dokumente dem User gehoeren
        from app.db.models import Document

        for split in splits:
            doc_id = UUID(split["document_id"]) if isinstance(split["document_id"], str) else split["document_id"]
            doc_query = select(Document).where(
                and_(
                    Document.id == doc_id,
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                )
            )
            doc_result = await db.execute(doc_query)
            if not doc_result.scalar_one_or_none():
                logger.warning(
                    "split_transaction_unauthorized_document",
                    transaction_id=str(transaction_id),
                    document_id=str(doc_id),
                    company_id=str(company_id),
                )
                raise ValueError("Dokument nicht gefunden oder keine Berechtigung")

        # Update Transaktion auf PARTIAL (Teilzahlung)
        transaction.reconciliation_status = ReconciliationStatus.PARTIAL.value
        transaction.matched_at = utc_now()
        transaction.updated_at = utc_now()

        # Speichere Split-Details
        transaction.split_details = splits

        results = []
        for split in splits:
            results.append(ReconciliationResult(
                transaction_id=transaction_id,
                status=ReconciliationStatus.PARTIAL,
                matched_document_id=UUID(split["document_id"]),
                match_confidence=1.0,
                match_method="manual_split",
            ))

        await db.commit()

        logger.info(
            "split_transaction_success",
            transaction_id=str(transaction_id),
            split_count=len(splits),
        )

        return results

    # =========================================================================
    # Private Matching-Methoden
    # =========================================================================

    async def _match_by_iban_amount(
        self,
        db: AsyncSession,
        company_id: UUID,
        transaction,
        iban: str,
    ) -> List[MatchCandidate]:
        """Match by IBAN + exakter Betrag."""
        from app.db.models import Document

        # Normalisiere IBAN
        iban_normalized = iban.replace(" ", "").upper()

        # Suche Dokumente mit passender IBAN
        query = select(Document).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                Document.document_type == "invoice",
            )
        )

        result = await db.execute(query)
        documents = result.scalars().all()

        candidates = []
        for doc in documents:
            if not doc.extracted_data:
                continue

            extracted = doc.extracted_data

            # Prüfe IBAN
            doc_iban = extracted.get("payment_details", {}).get("iban", "")
            if not doc_iban:
                continue

            doc_iban_normalized = doc_iban.replace(" ", "").upper()
            if doc_iban_normalized != iban_normalized:
                continue

            # Prüfe Betrag
            doc_amount = self._get_document_amount(extracted)
            if doc_amount is None:
                continue

            tx_amount = abs(transaction.amount)
            if self._amounts_match(tx_amount, doc_amount):
                confidence = 0.99 if tx_amount == doc_amount else 0.95

                candidates.append(MatchCandidate(
                    document_id=doc.id,
                    invoice_number=extracted.get("invoice_number"),
                    invoice_date=self._parse_date(extracted.get("invoice_date")),
                    due_date=self._parse_date(extracted.get("due_date")),
                    gross_amount=doc_amount,
                    counterparty_name=extracted.get("sender", {}).get("name"),
                    counterparty_iban=doc_iban,
                    customer_number=extracted.get("customer_number"),
                    confidence=confidence,
                    match_method="iban_amount",
                    match_details={
                        "iban_match": True,
                        "amount_exact": tx_amount == doc_amount,
                    },
                ))

        return candidates

    async def _match_by_invoice_number(
        self,
        db: AsyncSession,
        company_id: UUID,
        transaction,
        invoice_numbers: List[str],
    ) -> List[MatchCandidate]:
        """Match by Rechnungsnummer im Verwendungszweck."""
        from app.db.models import Document

        query = select(Document).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                Document.document_type == "invoice",
            )
        )

        result = await db.execute(query)
        documents = result.scalars().all()

        candidates = []
        for doc in documents:
            if not doc.extracted_data:
                continue

            extracted = doc.extracted_data
            doc_invoice_nr = extracted.get("invoice_number", "")

            if not doc_invoice_nr:
                continue

            # Prüfe ob eine der gefundenen Rechnungsnummern matcht
            matched_invoice = None
            for inv_nr in invoice_numbers:
                if self._invoice_numbers_match(inv_nr, doc_invoice_nr):
                    matched_invoice = inv_nr
                    break

            if not matched_invoice:
                continue

            # Prüfe Betrag
            doc_amount = self._get_document_amount(extracted)
            if doc_amount is None:
                continue

            tx_amount = abs(transaction.amount)
            if self._amounts_match(tx_amount, doc_amount, tolerance=0.02):
                confidence = 0.95 if tx_amount == doc_amount else 0.90

                candidates.append(MatchCandidate(
                    document_id=doc.id,
                    invoice_number=doc_invoice_nr,
                    invoice_date=self._parse_date(extracted.get("invoice_date")),
                    due_date=self._parse_date(extracted.get("due_date")),
                    gross_amount=doc_amount,
                    counterparty_name=extracted.get("sender", {}).get("name"),
                    counterparty_iban=extracted.get("payment_details", {}).get("iban"),
                    customer_number=extracted.get("customer_number"),
                    confidence=confidence,
                    match_method="invoice_number",
                    match_details={
                        "matched_invoice": matched_invoice,
                        "doc_invoice": doc_invoice_nr,
                    },
                ))

        return candidates

    async def _match_by_customer_number(
        self,
        db: AsyncSession,
        company_id: UUID,
        transaction,
        customer_numbers: List[str],
    ) -> List[MatchCandidate]:
        """Match by Kundennummer + Betrag + Datum."""
        from app.db.models import Document

        query = select(Document).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                Document.document_type == "invoice",
            )
        )

        result = await db.execute(query)
        documents = result.scalars().all()

        candidates = []
        for doc in documents:
            if not doc.extracted_data:
                continue

            extracted = doc.extracted_data
            doc_customer_nr = extracted.get("customer_number", "")

            if not doc_customer_nr:
                continue

            # Prüfe Kundennummer
            matched_customer = None
            for cust_nr in customer_numbers:
                if cust_nr.lower() in doc_customer_nr.lower() or doc_customer_nr.lower() in cust_nr.lower():
                    matched_customer = cust_nr
                    break

            if not matched_customer:
                continue

            # Prüfe Betrag
            doc_amount = self._get_document_amount(extracted)
            if doc_amount is None:
                continue

            tx_amount = abs(transaction.amount)
            if not self._amounts_match(tx_amount, doc_amount, tolerance=0.02):
                continue

            # Prüfe Datum-Naehe
            doc_due_date = self._parse_date(extracted.get("due_date"))
            date_proximity = 0
            if doc_due_date and transaction.booking_date:
                days_diff = abs((transaction.booking_date - doc_due_date).days)
                if days_diff <= self.DATE_TOLERANCE_DAYS:
                    date_proximity = 1 - (days_diff / self.DATE_TOLERANCE_DAYS)

            confidence = 0.80 + (date_proximity * 0.10)

            candidates.append(MatchCandidate(
                document_id=doc.id,
                invoice_number=extracted.get("invoice_number"),
                invoice_date=self._parse_date(extracted.get("invoice_date")),
                due_date=doc_due_date,
                gross_amount=doc_amount,
                counterparty_name=extracted.get("sender", {}).get("name"),
                counterparty_iban=extracted.get("payment_details", {}).get("iban"),
                customer_number=doc_customer_nr,
                confidence=confidence,
                match_method="customer_number",
                match_details={
                    "matched_customer": matched_customer,
                    "date_proximity": date_proximity,
                },
            ))

        return candidates

    async def _match_by_amount_date(
        self,
        db: AsyncSession,
        company_id: UUID,
        transaction,
    ) -> List[MatchCandidate]:
        """Match by Betrag + Datum-Naehe."""
        from app.db.models import Document

        tx_amount = abs(transaction.amount)
        tx_date = transaction.booking_date

        query = select(Document).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                Document.document_type == "invoice",
            )
        )

        result = await db.execute(query)
        documents = result.scalars().all()

        candidates = []
        for doc in documents:
            if not doc.extracted_data:
                continue

            extracted = doc.extracted_data
            doc_amount = self._get_document_amount(extracted)

            if doc_amount is None:
                continue

            # Prüfe Betrag (exakt)
            if tx_amount != doc_amount:
                continue

            # Prüfe Datum-Naehe
            doc_due_date = self._parse_date(extracted.get("due_date"))
            if not doc_due_date or not tx_date:
                continue

            days_diff = abs((tx_date - doc_due_date).days)
            if days_diff > self.DATE_TOLERANCE_DAYS:
                continue

            date_proximity = 1 - (days_diff / self.DATE_TOLERANCE_DAYS)
            confidence = 0.70 + (date_proximity * 0.10)

            candidates.append(MatchCandidate(
                document_id=doc.id,
                invoice_number=extracted.get("invoice_number"),
                invoice_date=self._parse_date(extracted.get("invoice_date")),
                due_date=doc_due_date,
                gross_amount=doc_amount,
                counterparty_name=extracted.get("sender", {}).get("name"),
                counterparty_iban=extracted.get("payment_details", {}).get("iban"),
                customer_number=extracted.get("customer_number"),
                confidence=confidence,
                match_method="amount_date",
                match_details={
                    "days_diff": days_diff,
                    "date_proximity": date_proximity,
                },
            ))

        return candidates

    async def _match_by_fuzzy_name(
        self,
        db: AsyncSession,
        company_id: UUID,
        transaction,
    ) -> List[MatchCandidate]:
        """Match by Fuzzy Name-Matching."""
        from app.db.models import Document


        tx_name = transaction.counterparty_name
        if not tx_name:
            return []

        tx_amount = abs(transaction.amount)
        tx_name_lower = tx_name.lower()

        query = select(Document).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                Document.document_type == "invoice",
            )
        )

        result = await db.execute(query)
        documents = result.scalars().all()

        candidates = []
        for doc in documents:
            if not doc.extracted_data:
                continue

            extracted = doc.extracted_data
            doc_sender = extracted.get("sender", {}).get("name", "")

            if not doc_sender:
                continue

            # Fuzzy Name Match
            name_similarity = self._calculate_name_similarity(tx_name_lower, doc_sender.lower())
            if name_similarity < 0.7:
                continue

            # Prüfe Betrag
            doc_amount = self._get_document_amount(extracted)
            if doc_amount is None:
                continue

            if not self._amounts_match(tx_amount, doc_amount, tolerance=0.05):
                continue

            confidence = 0.60 + (name_similarity * 0.15)

            candidates.append(MatchCandidate(
                document_id=doc.id,
                invoice_number=extracted.get("invoice_number"),
                invoice_date=self._parse_date(extracted.get("invoice_date")),
                due_date=self._parse_date(extracted.get("due_date")),
                gross_amount=doc_amount,
                counterparty_name=doc_sender,
                counterparty_iban=extracted.get("payment_details", {}).get("iban"),
                customer_number=extracted.get("customer_number"),
                confidence=confidence,
                match_method="fuzzy_name",
                match_details={
                    "name_similarity": name_similarity,
                    "tx_name": tx_name,
                    "doc_name": doc_sender,
                },
            ))

        return candidates

    # =========================================================================
    # Helper-Methoden
    # =========================================================================

    def _get_document_amount(self, extracted: Dict) -> Optional[Decimal]:
        """Extrahiere Bruttobetrag aus extracted_data."""
        amounts = extracted.get("amounts", {})
        gross = amounts.get("gross") or amounts.get("total") or amounts.get("brutto")

        if gross is None:
            return None

        try:
            return Decimal(str(gross))
        except (ValueError, TypeError, InvalidOperation):
            return None

    def _amounts_match(
        self,
        amount1: Decimal,
        amount2: Decimal,
        tolerance: float = None,
    ) -> bool:
        """Prüfe ob zwei Betraege übereinstimmen."""
        if tolerance is None:
            tolerance = self.AMOUNT_TOLERANCE_PERCENT

        if amount1 == amount2:
            return True

        # Prozentuale Toleranz
        diff = abs(amount1 - amount2)
        max_amount = max(amount1, amount2)
        if max_amount > 0:
            return float(diff / max_amount) <= tolerance

        return False

    def _invoice_numbers_match(self, num1: str, num2: str) -> bool:
        """Prüfe ob zwei Rechnungsnummern übereinstimmen."""
        # Normalisiere
        n1 = re.sub(r"[^a-zA-Z0-9]", "", num1.upper())
        n2 = re.sub(r"[^a-zA-Z0-9]", "", num2.upper())

        return n1 == n2 or n1 in n2 or n2 in n1

    def _parse_date(self, date_str: Optional[str]) -> Optional[date]:
        """Parse Datum aus String."""
        if not date_str:
            return None

        if isinstance(date_str, date):
            return date_str

        try:
            # ISO Format
            if "-" in date_str:
                return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
            # German Format
            elif "." in date_str:
                return datetime.strptime(date_str[:10], "%d.%m.%Y").date()
        except (ValueError, TypeError) as e:
            logger.debug("reconciliation_date_parse_failed", error_type=type(e).__name__, date_str=str(date_str))

        return None

    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        """Berechne Ähnlichkeit zwischen zwei Namen (0-1)."""
        # Einfache Wort-Überlappung
        words1 = set(name1.split())
        words2 = set(name2.split())

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2

        return len(intersection) / len(union) if union else 0.0

    def _deduplicate_candidates(
        self, candidates: List[MatchCandidate]
    ) -> List[MatchCandidate]:
        """Entferne Duplikate, behalte hoechste Konfidenz."""
        seen: Dict[UUID, MatchCandidate] = {}

        for candidate in candidates:
            doc_id = candidate.document_id
            if doc_id not in seen or candidate.confidence > seen[doc_id].confidence:
                seen[doc_id] = candidate

        return list(seen.values())
