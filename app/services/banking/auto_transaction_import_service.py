# -*- coding: utf-8 -*-
"""
Auto Transaction Import Service.

Handles:
- Automatic daily import from PSD2/FinTS
- Real-time balance updates
- Transaction categorization
- Duplicate detection
- Invoice linking

SECURITY NOTES:
- Never log transaction details (amounts, counterparties)
- All sensitive data encrypted at rest
- Rate limit API calls per bank requirements
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Union
from uuid import UUID, uuid4

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
from prometheus_client import Counter, Histogram, Gauge

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log, safe_error_detail
from app.db.models_banking_connection import (
    BankConnection,
    ConnectedBankAccount,
    ImportedTransaction,
    BankSyncLog,
    ConnectionStatus,
    SyncStatus,
)
from .psd2_integration_service import (
    PSD2IntegrationService,
    PSD2Transaction,
    get_psd2_service,
)
from .fints_service import FinTSService, FinTSTransaction

# Union type for transactions from different banking protocols
BankTransaction_T = Union[PSD2Transaction, FinTSTransaction]

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metrics
# =============================================================================

TRANSACTIONS_IMPORTED = Counter(
    "banking_transactions_imported_total",
    "Total transactions imported",
    ["company_id", "bank_code", "source"]
)

TRANSACTIONS_DUPLICATES = Counter(
    "banking_transactions_duplicates_total",
    "Duplicate transactions skipped",
    ["company_id", "bank_code"]
)

SYNC_DURATION = Histogram(
    "banking_sync_duration_seconds",
    "Sync operation duration",
    ["company_id", "sync_type"]
)

ACCOUNT_BALANCE = Gauge(
    "banking_account_balance_eur",
    "Current account balance in EUR",
    ["company_id", "account_id"]
)


# =============================================================================
# Types
# =============================================================================

@dataclass
class ImportResult:
    """Result of transaction import."""
    success: bool
    connection_id: UUID
    accounts_synced: int = 0
    transactions_imported: int = 0
    transactions_skipped: int = 0  # Duplicates
    auto_reconciled: int = 0
    error_message: Optional[str] = None
    sync_log_id: Optional[UUID] = None
    duration_ms: int = 0


@dataclass
class TransactionDedup:
    """Transaction deduplication key."""
    account_id: UUID
    transaction_id: Optional[str]
    booking_date: date
    amount: Decimal

    def hash_key(self) -> str:
        """Generate unique hash for deduplication."""
        key = f"{self.account_id}:{self.transaction_id or ''}:{self.booking_date}:{self.amount}"
        return hashlib.sha256(key.encode()).hexdigest()[:32]


# =============================================================================
# Auto Transaction Import Service
# =============================================================================

class AutoTransactionImportService:
    """
    Service for automatic transaction import.

    Features:
    - Scheduled sync (configurable interval)
    - Real-time balance updates
    - Intelligent duplicate detection
    - Transaction categorization
    - Auto-linking to invoices
    """

    def __init__(
        self,
        psd2_service: Optional[PSD2IntegrationService] = None,
        fints_service: Optional[FinTSService] = None,
    ):
        self.psd2_service = psd2_service or get_psd2_service()
        self.fints_service = fints_service or FinTSService()

        logger.info("auto_transaction_import_service_initialized")

    # =========================================================================
    # Sync Operations
    # =========================================================================

    async def sync_connection(
        self,
        db: AsyncSession,
        connection_id: UUID,
        company_id: UUID,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        triggered_by: str = "manual",
        user_id: Optional[UUID] = None,
    ) -> ImportResult:
        """
        Sync all accounts for a connection.

        Args:
            db: Database session
            connection_id: Connection to sync
            company_id: Company ID for security validation
            date_from: Start date (default: last sync or 90 days)
            date_to: End date (default: today)
            triggered_by: Trigger source (manual, scheduled, webhook)
            user_id: User who triggered (if manual)

        Returns:
            ImportResult with statistics
        """
        import time
        start_time = time.time()

        # Get connection
        connection = await db.get(BankConnection, connection_id)
        if not connection or connection.company_id != company_id:
            return ImportResult(
                success=False,
                connection_id=connection_id,
                error_message="Verbindung nicht gefunden oder keine Berechtigung",
            )

        if connection.status != ConnectionStatus.ACTIVE.value:
            return ImportResult(
                success=False,
                connection_id=connection_id,
                error_message=f"Verbindung nicht aktiv: {connection.status}",
            )

        # Create sync log
        sync_log = BankSyncLog(
            connection_id=connection_id,
            sync_type="transactions",
            status="started",
            triggered_by=triggered_by,
            triggered_by_user_id=user_id,
        )
        db.add(sync_log)
        await db.flush()

        # Update connection status
        connection.sync_status = SyncStatus.SYNCING.value
        await db.flush()

        try:
            # Determine date range
            if date_from is None:
                if connection.last_sync_at:
                    # Overlap by 3 days to catch late postings
                    date_from = (connection.last_sync_at - timedelta(days=3)).date()
                else:
                    date_from = date.today() - timedelta(days=90)

            if date_to is None:
                date_to = date.today()

            sync_log.sync_from_date = datetime.combine(date_from, datetime.min.time())
            sync_log.sync_to_date = datetime.combine(date_to, datetime.max.time())

            # Get accounts
            accounts_query = select(ConnectedBankAccount).where(
                and_(
                    ConnectedBankAccount.connection_id == connection_id,
                    ConnectedBankAccount.auto_import == True,
                )
            )
            result = await db.execute(accounts_query)
            accounts = list(result.scalars().all())

            if not accounts:
                return ImportResult(
                    success=True,
                    connection_id=connection_id,
                    accounts_synced=0,
                    error_message="Keine Konten fuer Auto-Import konfiguriert",
                    sync_log_id=sync_log.id,
                )

            # Sync each account
            total_imported = 0
            total_skipped = 0
            total_reconciled = 0
            errors = []

            for account in accounts:
                try:
                    imported, skipped, reconciled = await self._sync_account(
                        db=db,
                        connection=connection,
                        account=account,
                        date_from=date_from,
                        date_to=date_to,
                        sync_log_id=sync_log.id,
                    )
                    total_imported += imported
                    total_skipped += skipped
                    total_reconciled += reconciled

                except Exception as e:
                    errors.append(f"Account {account.iban[-4:]}: {safe_error_detail(e, 'Sync')}")
                    logger.error(
                        "account_sync_error",
                        account_id=str(account.id),
                        **safe_error_log(e),
                    )

            # Update connection
            connection.last_sync_at = utc_now()
            connection.next_sync_at = utc_now() + timedelta(hours=connection.sync_interval_hours)
            connection.sync_status = SyncStatus.SUCCESS.value
            connection.error_count = 0
            connection.is_healthy = True

            # Complete sync log
            duration_ms = int((time.time() - start_time) * 1000)
            sync_log.status = "success" if not errors else "partial"
            sync_log.completed_at = utc_now()
            sync_log.duration_ms = duration_ms
            sync_log.accounts_synced = len(accounts)
            sync_log.transactions_imported = total_imported
            sync_log.transactions_duplicates = total_skipped
            sync_log.auto_reconciled_count = total_reconciled

            if errors:
                sync_log.error_message = "; ".join(errors)

            await db.commit()

            SYNC_DURATION.labels(
                company_id=str(company_id),
                sync_type="transactions",
            ).observe(duration_ms / 1000)

            logger.info(
                "connection_sync_completed",
                connection_id=str(connection_id),
                accounts=len(accounts),
                imported=total_imported,
                skipped=total_skipped,
                reconciled=total_reconciled,
                duration_ms=duration_ms,
            )

            return ImportResult(
                success=True,
                connection_id=connection_id,
                accounts_synced=len(accounts),
                transactions_imported=total_imported,
                transactions_skipped=total_skipped,
                auto_reconciled=total_reconciled,
                sync_log_id=sync_log.id,
                duration_ms=duration_ms,
                error_message="; ".join(errors) if errors else None,
            )

        except Exception as e:
            # Mark sync as failed
            connection.sync_status = SyncStatus.FAILED.value
            connection.error_count = (connection.error_count or 0) + 1
            connection.last_error = safe_error_detail(e, "Sync")
            connection.last_error_at = utc_now()

            if connection.error_count >= 5:
                connection.is_healthy = False

            sync_log.status = "failed"
            sync_log.completed_at = utc_now()
            sync_log.error_message = safe_error_detail(e, "Sync")

            await db.commit()

            logger.error(
                "connection_sync_failed",
                connection_id=str(connection_id),
                **safe_error_log(e),
            )

            return ImportResult(
                success=False,
                connection_id=connection_id,
                error_message=safe_error_detail(e, "Sync"),
                sync_log_id=sync_log.id,
            )

    async def _sync_account(
        self,
        db: AsyncSession,
        connection: BankConnection,
        account: ConnectedBankAccount,
        date_from: date,
        date_to: date,
        sync_log_id: UUID,
    ) -> Tuple[int, int, int]:
        """
        Sync a single account.

        Returns:
            Tuple of (imported_count, skipped_count, reconciled_count)
        """
        # Fetch transactions based on connection type
        if connection.connection_type == "psd2":
            transactions = await self._fetch_psd2_transactions(
                connection, account, date_from, date_to
            )
        else:
            transactions = await self._fetch_fints_transactions(
                connection, account, date_from, date_to
            )

        if not transactions:
            return 0, 0, 0

        # Import transactions
        imported = 0
        skipped = 0

        for tx in transactions:
            is_new = await self._import_transaction(
                db=db,
                account=account,
                transaction=tx,
                sync_log_id=sync_log_id,
            )

            if is_new:
                imported += 1
            else:
                skipped += 1

        # Update balance
        await self._update_balance(db, connection, account)

        # Update account statistics
        account.transaction_count = (account.transaction_count or 0) + imported
        if transactions:
            account.last_transaction_date = max(tx.booking_date for tx in transactions)

        await db.flush()

        # Record metrics
        TRANSACTIONS_IMPORTED.labels(
            company_id=str(connection.company_id),
            bank_code=connection.bank_code,
            source=connection.connection_type,
        ).inc(imported)

        if skipped > 0:
            TRANSACTIONS_DUPLICATES.labels(
                company_id=str(connection.company_id),
                bank_code=connection.bank_code,
            ).inc(skipped)

        # Auto-reconciliation happens in separate service
        return imported, skipped, 0

    async def _fetch_psd2_transactions(
        self,
        connection: BankConnection,
        account: ConnectedBankAccount,
        date_from: date,
        date_to: date,
    ) -> List[PSD2Transaction]:
        """Fetch transactions via PSD2 API."""
        # In production: Decrypt tokens and call PSD2 API
        # For now, return empty (implementation depends on OAuth2 flow)

        all_transactions: List[PSD2Transaction] = []
        page_token = None

        while True:
            result, error = await self.psd2_service.get_transactions(
                bank_code=connection.bank_code,
                access_token="placeholder",  # Would come from encrypted token
                consent_id=connection.consent_id or "",
                account_id=account.iban,  # Some banks use IBAN as account_id
                date_from=date_from,
                date_to=date_to,
                page_token=page_token,
            )

            if error:
                logger.warning(
                    "psd2_transaction_fetch_error",
                    connection_id=str(connection.id),
                    error=error,
                )
                break

            all_transactions.extend(result["transactions"])

            if not result["has_more"]:
                break

            page_token = result["next_page_token"]

        return all_transactions

    async def _fetch_fints_transactions(
        self,
        connection: BankConnection,
        account: ConnectedBankAccount,
        date_from: date,
        date_to: date,
    ) -> List[FinTSTransaction]:
        """Fetch transactions via FinTS."""
        # In production: Connect via FinTS and fetch transactions
        # For development: Generate mock data

        # This would require the PIN which is session-only
        # For automatic sync, we'd need stored session or re-authentication

        logger.info(
            "fints_transaction_fetch",
            connection_id=str(connection.id),
            date_from=date_from.isoformat(),
            date_to=date_to.isoformat(),
        )

        # Mock: Return empty for now
        return []

    async def _import_transaction(
        self,
        db: AsyncSession,
        account: ConnectedBankAccount,
        transaction: BankTransaction_T,
        sync_log_id: UUID,
    ) -> bool:
        """
        Import a single transaction.

        Returns:
            True if new transaction, False if duplicate
        """
        # Determine transaction fields based on type
        if isinstance(transaction, PSD2Transaction):
            tx_id = transaction.transaction_id
            booking_date = transaction.booking_date
            value_date = transaction.value_date
            amount = transaction.amount
            currency = transaction.currency
            counterparty_name = transaction.creditor_name or transaction.debtor_name
            counterparty_iban = transaction.creditor_iban or transaction.debtor_iban
            reference_text = transaction.remittance_info
            end_to_end_id = transaction.end_to_end_id
            mandate_ref = transaction.mandate_id
            creditor_id = transaction.creditor_id
            raw_data = transaction.raw_data
        else:
            # FinTSTransaction
            tx_id = transaction.transaction_id
            booking_date = transaction.booking_date
            value_date = transaction.value_date
            amount = transaction.amount
            currency = transaction.currency
            counterparty_name = transaction.counterparty_name
            counterparty_iban = transaction.counterparty_iban
            reference_text = transaction.reference_text
            end_to_end_id = transaction.end_to_end_reference
            mandate_ref = transaction.mandate_reference
            creditor_id = transaction.creditor_id
            raw_data = transaction.raw_data

        # Check for duplicate
        dedup = TransactionDedup(
            account_id=account.id,
            transaction_id=tx_id,
            booking_date=booking_date if isinstance(booking_date, date) else booking_date.date(),
            amount=amount,
        )

        existing_query = select(ImportedTransaction.id).where(
            and_(
                ImportedTransaction.account_id == account.id,
                or_(
                    # Match by transaction ID if available
                    and_(
                        ImportedTransaction.transaction_id.isnot(None),
                        ImportedTransaction.transaction_id == tx_id,
                    ),
                    # Match by dedup hash
                    and_(
                        func.date(ImportedTransaction.booking_date) == dedup.booking_date,
                        ImportedTransaction.amount == dedup.amount,
                        ImportedTransaction.counterparty_iban == counterparty_iban,
                    ),
                ),
            )
        ).limit(1)

        existing = await db.execute(existing_query)
        if existing.scalar_one_or_none():
            return False  # Duplicate

        # Create new transaction
        imported_tx = ImportedTransaction(
            account_id=account.id,
            transaction_id=tx_id,
            booking_date=datetime.combine(booking_date, datetime.min.time()) if isinstance(booking_date, date) else booking_date,
            value_date=datetime.combine(value_date, datetime.min.time()) if isinstance(value_date, date) else value_date,
            amount=amount,
            currency=currency,
            counterparty_name=counterparty_name,
            counterparty_iban=counterparty_iban,
            reference_text=reference_text,
            end_to_end_id=end_to_end_id,
            mandate_reference=mandate_ref,
            creditor_id=creditor_id,
            reconciliation_status="pending",
            raw_data=raw_data,
            sync_log_id=sync_log_id,
        )

        db.add(imported_tx)
        await db.flush()

        return True

    async def _update_balance(
        self,
        db: AsyncSession,
        connection: BankConnection,
        account: ConnectedBankAccount,
    ) -> None:
        """Update account balance."""
        if connection.connection_type == "psd2":
            balances, error = await self.psd2_service.get_balances(
                bank_code=connection.bank_code,
                access_token="placeholder",
                consent_id=connection.consent_id or "",
                account_id=account.iban,
            )

            if not error and balances:
                for bal in balances:
                    if bal.balance_type == "closingBooked":
                        account.current_balance = bal.amount
                        account.balance_updated_at = utc_now()
                        break
                    elif bal.balance_type == "expected":
                        account.available_balance = bal.amount

                # Update Prometheus gauge
                if account.current_balance:
                    ACCOUNT_BALANCE.labels(
                        company_id=str(connection.company_id),
                        account_id=str(account.id),
                    ).set(float(account.current_balance))

    # =========================================================================
    # Batch Operations
    # =========================================================================

    async def sync_all_due_connections(
        self,
        db: AsyncSession,
    ) -> List[ImportResult]:
        """
        Sync all connections that are due for sync.

        Called by Celery beat scheduler.
        """
        now = utc_now()

        # Find connections due for sync
        query = select(BankConnection).where(
            and_(
                BankConnection.status == ConnectionStatus.ACTIVE.value,
                BankConnection.auto_sync_enabled == True,
                BankConnection.is_healthy == True,
                or_(
                    BankConnection.next_sync_at.is_(None),
                    BankConnection.next_sync_at <= now,
                ),
            )
        ).order_by(BankConnection.next_sync_at.asc()).limit(50)

        result = await db.execute(query)
        connections = list(result.scalars().all())

        if not connections:
            logger.info("no_connections_due_for_sync")
            return []

        logger.info(
            "syncing_due_connections",
            count=len(connections),
        )

        results = []
        for connection in connections:
            try:
                sync_result = await self.sync_connection(
                    db=db,
                    connection_id=connection.id,
                    company_id=connection.company_id,
                    triggered_by="scheduled",
                )
                results.append(sync_result)

                # Small delay between syncs to avoid rate limiting
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(
                    "scheduled_sync_error",
                    connection_id=str(connection.id),
                    **safe_error_log(e),
                )
                results.append(ImportResult(
                    success=False,
                    connection_id=connection.id,
                    error_message=safe_error_detail(e, "Scheduled Sync"),
                ))

        return results

    async def refresh_psd2_consents(
        self,
        db: AsyncSession,
    ) -> int:
        """
        Refresh PSD2 consents that are about to expire.

        Returns number of connections that need re-authorization.
        """
        # Find consents expiring in next 7 days
        expiry_threshold = utc_now() + timedelta(days=7)

        query = select(BankConnection).where(
            and_(
                BankConnection.connection_type == "psd2",
                BankConnection.status == ConnectionStatus.ACTIVE.value,
                BankConnection.consent_expires_at.isnot(None),
                BankConnection.consent_expires_at <= expiry_threshold,
            )
        )

        result = await db.execute(query)
        connections = list(result.scalars().all())

        if not connections:
            return 0

        # Mark connections as needing re-authorization
        for connection in connections:
            connection.status = ConnectionStatus.EXPIRED.value
            connection.is_healthy = False

            logger.warning(
                "psd2_consent_expiring",
                connection_id=str(connection.id),
                bank_code=connection.bank_code,
                expires_at=connection.consent_expires_at.isoformat() if connection.consent_expires_at else None,
            )

        await db.commit()

        return len(connections)


# =============================================================================
# Factory
# =============================================================================

_service_instance: Optional[AutoTransactionImportService] = None


def get_auto_transaction_import_service() -> AutoTransactionImportService:
    """Get auto transaction import service instance."""
    global _service_instance

    if _service_instance is None:
        _service_instance = AutoTransactionImportService()

    return _service_instance
