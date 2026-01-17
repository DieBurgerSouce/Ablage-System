"""Bank Transaction Service.

Verwaltet Banktransaktionen:
- Transaktionen auflisten und filtern
- Transaktionsdetails abrufen
- Transaktionen aktualisieren (Notizen, Tags)
- Unabgeglichene Transaktionen finden
- Statistiken und Aggregationen
"""

from datetime import datetime, date, timedelta
from app.core.datetime_utils import utc_now
from decimal import Decimal
from typing import Optional, List, Tuple, Dict, Any, TYPE_CHECKING
from uuid import UUID
import structlog

from sqlalchemy import select, func, and_, or_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .models import (
    TransactionType,
    ReconciliationStatus,
    BankTransactionResponse,
    TransactionFilter,
    TransactionStats,
)

if TYPE_CHECKING:
    from app.db.models import BankTransaction

logger = structlog.get_logger(__name__)


class TransactionService:
    """Service fuer Banktransaktions-Verwaltung."""

    async def get_transactions(
        self,
        db: AsyncSession,
        user_id: UUID,
        bank_account_id: Optional[UUID] = None,
        filters: Optional[TransactionFilter] = None,
        offset: int = 0,
        limit: int = 50,
        sort_by: str = "booking_date",
        sort_order: str = "desc",
    ) -> Tuple[List[BankTransactionResponse], int]:
        """Hole Transaktionen mit Filterung und Paginierung.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            bank_account_id: Optionaler Filter auf Bankkonto
            filters: Optionale Filter
            offset: Offset fuer Paginierung
            limit: Limit fuer Paginierung
            sort_by: Sortierfeld
            sort_order: Sortierrichtung (asc/desc)

        Returns:
            (Liste von Transaktionen, Gesamtanzahl)
        """
        from app.db.models import BankTransaction, BankAccount

        # Basis-Query: Nur Transaktionen von Konten des Users
        base_query = (
            select(BankTransaction)
            .join(BankAccount)
            .where(
                and_(
                    BankAccount.user_id == user_id,
                    BankAccount.deleted_at.is_(None),
                )
            )
        )

        # Filter auf Bankkonto
        if bank_account_id:
            base_query = base_query.where(
                BankTransaction.bank_account_id == bank_account_id
            )

        # Zusaetzliche Filter
        if filters:
            if filters.date_from:
                base_query = base_query.where(
                    BankTransaction.booking_date >= filters.date_from
                )
            if filters.date_to:
                base_query = base_query.where(
                    BankTransaction.booking_date <= filters.date_to
                )
            if filters.amount_min is not None:
                base_query = base_query.where(
                    BankTransaction.amount >= filters.amount_min
                )
            if filters.amount_max is not None:
                base_query = base_query.where(
                    BankTransaction.amount <= filters.amount_max
                )
            if filters.transaction_type:
                base_query = base_query.where(
                    BankTransaction.transaction_type == filters.transaction_type.value
                )
            if filters.reconciliation_status:
                base_query = base_query.where(
                    BankTransaction.reconciliation_status == filters.reconciliation_status.value
                )
            if filters.search_text:
                search_pattern = f"%{filters.search_text}%"
                base_query = base_query.where(
                    or_(
                        BankTransaction.counterparty_name.ilike(search_pattern),
                        BankTransaction.reference_text.ilike(search_pattern),
                        BankTransaction.booking_text.ilike(search_pattern),
                    )
                )
            if filters.counterparty_name:
                base_query = base_query.where(
                    BankTransaction.counterparty_name.ilike(f"%{filters.counterparty_name}%")
                )
            if filters.counterparty_iban:
                base_query = base_query.where(
                    BankTransaction.counterparty_iban == filters.counterparty_iban.replace(" ", "").upper()
                )

        # Zaehle Gesamtanzahl
        count_query = select(func.count()).select_from(base_query.subquery())
        count_result = await db.execute(count_query)
        total_count = count_result.scalar() or 0

        # Sortierung
        sort_column = getattr(BankTransaction, sort_by, BankTransaction.booking_date)
        if sort_order == "desc":
            base_query = base_query.order_by(desc(sort_column))
        else:
            base_query = base_query.order_by(asc(sort_column))

        # Paginierung
        base_query = base_query.offset(offset).limit(limit)

        # Ausfuehren
        result = await db.execute(base_query)
        transactions = result.scalars().all()

        return [self._to_response(tx) for tx in transactions], total_count

    async def get_transaction(
        self,
        db: AsyncSession,
        user_id: UUID,
        transaction_id: UUID,
    ) -> Optional[BankTransactionResponse]:
        """Hole einzelne Transaktion."""
        from app.db.models import BankTransaction, BankAccount

        query = (
            select(BankTransaction)
            .join(BankAccount)
            .where(
                and_(
                    BankTransaction.id == transaction_id,
                    BankAccount.user_id == user_id,
                    BankAccount.deleted_at.is_(None),
                )
            )
        )

        result = await db.execute(query)
        transaction = result.scalar_one_or_none()

        if not transaction:
            return None

        return self._to_response(transaction)

    async def get_unmatched_transactions(
        self,
        db: AsyncSession,
        user_id: UUID,
        bank_account_id: Optional[UUID] = None,
        limit: int = 100,
    ) -> List[BankTransactionResponse]:
        """Hole unabgeglichene Transaktionen fuer Reconciliation."""
        from app.db.models import BankTransaction, BankAccount

        query = (
            select(BankTransaction)
            .join(BankAccount)
            .where(
                and_(
                    BankAccount.user_id == user_id,
                    BankAccount.deleted_at.is_(None),
                    BankTransaction.reconciliation_status == ReconciliationStatus.UNMATCHED.value,
                )
            )
            .order_by(desc(BankTransaction.booking_date))
            .limit(limit)
        )

        if bank_account_id:
            query = query.where(BankTransaction.bank_account_id == bank_account_id)

        result = await db.execute(query)
        transactions = result.scalars().all()

        return [self._to_response(tx) for tx in transactions]

    async def update_transaction(
        self,
        db: AsyncSession,
        user_id: UUID,
        transaction_id: UUID,
        notes: Optional[str] = None,
        tags: Optional[List[str]] = None,
        category: Optional[str] = None,
    ) -> Optional[BankTransactionResponse]:
        """Aktualisiere Transaktions-Metadaten."""
        from app.db.models import BankTransaction, BankAccount

        # Hole Transaktion mit Berechtigungspruefung
        query = (
            select(BankTransaction)
            .join(BankAccount)
            .where(
                and_(
                    BankTransaction.id == transaction_id,
                    BankAccount.user_id == user_id,
                    BankAccount.deleted_at.is_(None),
                )
            )
        )

        result = await db.execute(query)
        transaction = result.scalar_one_or_none()

        if not transaction:
            return None

        # Aktualisiere Felder
        if notes is not None:
            transaction.notes = notes
        if tags is not None:
            transaction.tags = tags
        if category is not None:
            transaction.category = category

        transaction.updated_at = utc_now()

        await db.commit()
        await db.refresh(transaction)

        return self._to_response(transaction)

    async def set_reconciliation_status(
        self,
        db: AsyncSession,
        user_id: UUID,
        transaction_id: UUID,
        status: ReconciliationStatus,
        matched_document_id: Optional[UUID] = None,
        match_confidence: Optional[float] = None,
    ) -> Optional[BankTransactionResponse]:
        """Setze Abgleich-Status einer Transaktion."""
        from app.db.models import BankTransaction, BankAccount

        query = (
            select(BankTransaction)
            .join(BankAccount)
            .where(
                and_(
                    BankTransaction.id == transaction_id,
                    BankAccount.user_id == user_id,
                )
            )
        )

        result = await db.execute(query)
        transaction = result.scalar_one_or_none()

        if not transaction:
            return None

        transaction.reconciliation_status = status.value
        transaction.matched_document_id = matched_document_id
        transaction.match_confidence = match_confidence
        transaction.matched_at = utc_now() if status == ReconciliationStatus.MATCHED else None
        transaction.updated_at = utc_now()

        await db.commit()
        await db.refresh(transaction)

        logger.info(
            "transaction_reconciliation_updated",
            transaction_id=str(transaction_id),
            status=status.value,
            matched_document_id=str(matched_document_id) if matched_document_id else None,
        )

        return self._to_response(transaction)

    async def get_transaction_stats(
        self,
        db: AsyncSession,
        user_id: UUID,
        bank_account_id: Optional[UUID] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> TransactionStats:
        """Hole Transaktions-Statistiken."""
        from app.db.models import BankTransaction, BankAccount

        # Basis-Query
        base_conditions = [
            BankAccount.user_id == user_id,
            BankAccount.deleted_at.is_(None),
        ]

        if bank_account_id:
            base_conditions.append(BankTransaction.bank_account_id == bank_account_id)
        if date_from:
            base_conditions.append(BankTransaction.booking_date >= date_from)
        if date_to:
            base_conditions.append(BankTransaction.booking_date <= date_to)

        # Gesamtstatistiken
        stats_query = (
            select(
                func.count(BankTransaction.id).label("total_count"),
                func.sum(BankTransaction.amount).filter(BankTransaction.amount > 0).label("total_credits"),
                func.sum(func.abs(BankTransaction.amount)).filter(BankTransaction.amount < 0).label("total_debits"),
                func.count(BankTransaction.id).filter(
                    BankTransaction.reconciliation_status == ReconciliationStatus.UNMATCHED.value
                ).label("unmatched_count"),
                func.count(BankTransaction.id).filter(
                    BankTransaction.reconciliation_status == ReconciliationStatus.MATCHED.value
                ).label("matched_count"),
                func.count(BankTransaction.id).filter(
                    BankTransaction.reconciliation_status == ReconciliationStatus.PARTIAL.value
                ).label("partial_count"),
            )
            .select_from(BankTransaction)
            .join(BankAccount)
            .where(and_(*base_conditions))
        )

        result = await db.execute(stats_query)
        stats = result.first()

        # Berechne Match-Rate
        total = stats.total_count or 0
        matched = stats.matched_count or 0
        match_rate = (matched / total * 100) if total > 0 else 0.0

        return TransactionStats(
            total_count=total,
            total_credits=Decimal(str(stats.total_credits or 0)),
            total_debits=Decimal(str(stats.total_debits or 0)),
            unmatched_count=stats.unmatched_count or 0,
            matched_count=matched,
            partially_matched_count=stats.partial_count or 0,
            match_rate=round(match_rate, 1),
        )

    async def get_monthly_summary(
        self,
        db: AsyncSession,
        user_id: UUID,
        bank_account_id: Optional[UUID] = None,
        months: int = 12,
    ) -> List[Dict[str, Any]]:
        """Hole monatliche Zusammenfassung der letzten N Monate."""
        from app.db.models import BankTransaction, BankAccount

        # Berechne Startdatum
        today = date.today()
        start_date = today.replace(day=1) - timedelta(days=months * 31)
        start_date = start_date.replace(day=1)

        base_conditions = [
            BankAccount.user_id == user_id,
            BankAccount.deleted_at.is_(None),
            BankTransaction.booking_date >= start_date,
        ]

        if bank_account_id:
            base_conditions.append(BankTransaction.bank_account_id == bank_account_id)

        # Gruppiere nach Monat
        query = (
            select(
                func.date_trunc('month', BankTransaction.booking_date).label("month"),
                func.sum(BankTransaction.amount).filter(BankTransaction.amount > 0).label("credits"),
                func.sum(func.abs(BankTransaction.amount)).filter(BankTransaction.amount < 0).label("debits"),
                func.count(BankTransaction.id).label("count"),
            )
            .select_from(BankTransaction)
            .join(BankAccount)
            .where(and_(*base_conditions))
            .group_by(func.date_trunc('month', BankTransaction.booking_date))
            .order_by(func.date_trunc('month', BankTransaction.booking_date))
        )

        result = await db.execute(query)
        rows = result.all()

        return [
            {
                "month": row.month.strftime("%Y-%m") if row.month else None,
                "credits": Decimal(str(row.credits or 0)),
                "debits": Decimal(str(row.debits or 0)),
                "net": Decimal(str((row.credits or 0) - (row.debits or 0))),
                "transaction_count": row.count or 0,
            }
            for row in rows
        ]

    async def get_top_counterparties(
        self,
        db: AsyncSession,
        user_id: UUID,
        bank_account_id: Optional[UUID] = None,
        direction: str = "both",  # "in", "out", "both"
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Hole Top-Geschaeftspartner nach Umsatz."""
        from app.db.models import BankTransaction, BankAccount

        base_conditions = [
            BankAccount.user_id == user_id,
            BankAccount.deleted_at.is_(None),
            BankTransaction.counterparty_name.isnot(None),
        ]

        if bank_account_id:
            base_conditions.append(BankTransaction.bank_account_id == bank_account_id)

        if direction == "in":
            base_conditions.append(BankTransaction.amount > 0)
        elif direction == "out":
            base_conditions.append(BankTransaction.amount < 0)

        query = (
            select(
                BankTransaction.counterparty_name,
                BankTransaction.counterparty_iban,
                func.sum(func.abs(BankTransaction.amount)).label("total_amount"),
                func.count(BankTransaction.id).label("transaction_count"),
            )
            .select_from(BankTransaction)
            .join(BankAccount)
            .where(and_(*base_conditions))
            .group_by(BankTransaction.counterparty_name, BankTransaction.counterparty_iban)
            .order_by(desc(func.sum(func.abs(BankTransaction.amount))))
            .limit(limit)
        )

        result = await db.execute(query)
        rows = result.all()

        return [
            {
                "counterparty_name": row.counterparty_name,
                "counterparty_iban": row.counterparty_iban,
                "total_amount": Decimal(str(row.total_amount or 0)),
                "transaction_count": row.transaction_count or 0,
            }
            for row in rows
        ]

    def _to_response(self, transaction: "BankTransaction") -> BankTransactionResponse:
        """Konvertiere DB-Model zu Response."""
        return BankTransactionResponse(
            id=transaction.id,
            bank_account_id=transaction.bank_account_id,
            transaction_id=transaction.transaction_id,
            booking_date=transaction.booking_date,
            value_date=transaction.value_date or transaction.booking_date,  # Fallback
            amount=transaction.amount,
            currency=transaction.currency or "EUR",
            counterparty_name=transaction.counterparty_name,
            counterparty_iban=transaction.counterparty_iban,
            counterparty_bic=transaction.counterparty_bic,
            reference_text=transaction.reference_text,
            transaction_type=TransactionType(transaction.transaction_type) if transaction.transaction_type else None,
            booking_text=transaction.booking_text,
            reconciliation_status=ReconciliationStatus(transaction.reconciliation_status) if transaction.reconciliation_status else ReconciliationStatus.UNMATCHED,
            matched_document_id=transaction.matched_document_id,
            matched_invoice_number=getattr(transaction, "matched_invoice_number", None),
            match_confidence=transaction.match_confidence,
            match_method=getattr(transaction, "match_method", None),
            is_partial_payment=getattr(transaction, "is_partial_payment", False),
            allocated_amount=getattr(transaction, "allocated_amount", None),
            remaining_amount=getattr(transaction, "remaining_amount", None),
            imported_at=getattr(transaction, "imported_at", None) or transaction.created_at,
        )
