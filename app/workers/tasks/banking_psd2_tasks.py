# -*- coding: utf-8 -*-
"""
Celery Tasks fuer PSD2/FinTS Banking Integration.

Phase 6: Multi-Bank Aggregation Tasks.

Geplante Tasks:
- sync_all_bank_accounts: Alle 4 Stunden - Synchronisiere alle verbundenen Konten
- refresh_psd2_consents: Taeglich - PSD2 Consent-Tokens erneuern
- auto_reconcile_transactions: Nach Import - Automatischer Zahlungsabgleich
- process_scheduled_payments: Stuendlich - Geplante Zahlungen ausfuehren

SECURITY NOTES:
- NIEMALS IBANs, Kontonummern oder Salden loggen
- Credentials sind AES-256-GCM verschluesselt
- PSD2 Consent-Tokens haben begrenzte TTL
- TAN-Challenges verfallen nach 5 Minuten
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from uuid import UUID

import structlog
from celery import shared_task
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_log
from app.db.session import async_session_factory
from app.workers.celery_app import celery_app, CPUTask

logger = structlog.get_logger(__name__)


def run_async(coro):
    """Helper um async Code in Celery auszufuehren."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# =============================================================================
# SYNC TASKS
# =============================================================================


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_psd2_tasks.sync_all_bank_accounts",
    max_retries=3,
    default_retry_delay=300,
    queue="banking",
)
def sync_all_bank_accounts(
    self,
    company_id: Optional[str] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Synchronisiere alle verbundenen Bankkonten via PSD2/FinTS.

    Wird alle 4 Stunden ausgefuehrt (via Celery Beat).

    Args:
        company_id: Optional - nur fuer bestimmte Firma
        force: Sync auch wenn noch nicht faellig

    Returns:
        Sync-Statistik
    """
    logger.info(
        "psd2_sync_all_started",
        task_id=self.request.id,
        company_id=company_id,
        force=force,
    )

    return run_async(_sync_all_bank_accounts(company_id, force))


async def _sync_all_bank_accounts(
    company_id_str: Optional[str] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Async Implementation fuer sync_all_bank_accounts."""
    from app.db.models_banking_connection import (
        BankConnection, ConnectionStatus, SyncStatus
    )
    from app.services.banking.auto_transaction_import_service import (
        AutoTransactionImportService,
    )

    stats = {
        "connections_checked": 0,
        "connections_synced": 0,
        "connections_skipped": 0,
        "connections_failed": 0,
        "accounts_synced": 0,
        "transactions_imported": 0,
        "transactions_reconciled": 0,
        "errors": [],
    }

    try:
        async with async_session_factory() as db:
            import_service = AutoTransactionImportService(db)

            # Query fuer aktive Verbindungen
            query = select(BankConnection).where(
                and_(
                    BankConnection.status == ConnectionStatus.ACTIVE.value,
                    BankConnection.auto_sync_enabled == True,
                )
            )

            if company_id_str:
                query = query.where(
                    BankConnection.company_id == UUID(company_id_str)
                )

            # Nur wenn sync faellig (oder force)
            if not force:
                now = datetime.now(timezone.utc)
                query = query.where(
                    or_(
                        BankConnection.next_sync_at.is_(None),
                        BankConnection.next_sync_at <= now,
                    )
                )

            result = await db.execute(query)
            connections = result.scalars().all()

            for connection in connections:
                stats["connections_checked"] += 1

                try:
                    # Sync ausfuehren
                    sync_result = await import_service.sync_connection(
                        connection_id=connection.id
                    )

                    if sync_result.get("success"):
                        stats["connections_synced"] += 1
                        stats["accounts_synced"] += sync_result.get(
                            "accounts_synced", 0
                        )
                        stats["transactions_imported"] += sync_result.get(
                            "transactions_imported", 0
                        )
                        stats["transactions_reconciled"] += sync_result.get(
                            "auto_reconciled", 0
                        )

                        logger.info(
                            "psd2_connection_synced",
                            connection_id=str(connection.id),
                            transactions=sync_result.get("transactions_imported", 0),
                        )
                    else:
                        stats["connections_failed"] += 1
                        stats["errors"].append({
                            "connection_id": str(connection.id),
                            "error": sync_result.get("error", "Unbekannter Fehler"),
                        })

                except Exception as e:
                    stats["connections_failed"] += 1
                    stats["errors"].append({
                        "connection_id": str(connection.id),
                        "error": str(e)[:200],
                    })
                    logger.warning(
                        "psd2_connection_sync_failed",
                        connection_id=str(connection.id),
                        **safe_error_log(e),
                    )

            logger.info(
                "psd2_sync_all_completed",
                **{k: v for k, v in stats.items() if k != "errors"},
            )

    except Exception as e:
        logger.error(
            "psd2_sync_all_failed",
            **safe_error_log(e),
            exc_info=True,
        )
        raise

    return stats


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_psd2_tasks.sync_single_connection",
    max_retries=3,
    default_retry_delay=60,
    queue="banking",
)
def sync_single_connection(
    self,
    connection_id: str,
    company_id: str,
) -> Dict[str, Any]:
    """
    Synchronisiere eine einzelne Bankverbindung.

    Wird on-demand oder nach Verbindungsherstellung aufgerufen.

    Args:
        connection_id: Verbindungs-ID
        company_id: Company-ID

    Returns:
        Sync-Ergebnis
    """
    logger.info(
        "psd2_sync_single_started",
        task_id=self.request.id,
        connection_id=connection_id,
    )

    return run_async(_sync_single_connection(connection_id, company_id))


async def _sync_single_connection(
    connection_id: str,
    company_id: str,
) -> Dict[str, Any]:
    """Async Implementation fuer sync_single_connection."""
    from app.services.banking.auto_transaction_import_service import (
        AutoTransactionImportService,
    )

    try:
        async with async_session_factory() as db:
            import_service = AutoTransactionImportService(db)

            result = await import_service.sync_connection(
                connection_id=UUID(connection_id)
            )

            logger.info(
                "psd2_sync_single_completed",
                connection_id=connection_id,
                success=result.get("success"),
                transactions=result.get("transactions_imported", 0),
            )

            return result

    except Exception as e:
        logger.error(
            "psd2_sync_single_failed",
            connection_id=connection_id,
            **safe_error_log(e),
            exc_info=True,
        )
        return {"success": False, "error": str(e)}


# =============================================================================
# PSD2 CONSENT REFRESH
# =============================================================================


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_psd2_tasks.refresh_psd2_consents",
    max_retries=2,
    default_retry_delay=3600,
    queue="banking",
)
def refresh_psd2_consents(self, days_before_expiry: int = 7) -> Dict[str, Any]:
    """
    Erneuere PSD2 Consent-Tokens vor Ablauf.

    Wird taeglich ausgefuehrt (via Celery Beat).
    Warnt Benutzer bei Consents die bald ablaufen.

    Args:
        days_before_expiry: Tage vor Ablauf warnen/erneuern

    Returns:
        Refresh-Statistik
    """
    logger.info(
        "psd2_consent_refresh_started",
        task_id=self.request.id,
        days_before_expiry=days_before_expiry,
    )

    return run_async(_refresh_psd2_consents(days_before_expiry))


async def _refresh_psd2_consents(days_before_expiry: int = 7) -> Dict[str, Any]:
    """Async Implementation fuer refresh_psd2_consents."""
    from app.db.models_banking_connection import (
        BankConnection, ConnectionType, ConnectionStatus
    )
    from app.services.banking.auto_transaction_import_service import (
        AutoTransactionImportService,
    )

    stats = {
        "connections_checked": 0,
        "consents_expiring_soon": 0,
        "consents_refreshed": 0,
        "consents_failed": 0,
        "notifications_sent": 0,
    }

    try:
        async with async_session_factory() as db:
            import_service = AutoTransactionImportService(db)

            # Finde PSD2-Verbindungen mit ablaufendem Consent
            cutoff_date = datetime.now(timezone.utc) + timedelta(
                days=days_before_expiry
            )

            query = select(BankConnection).where(
                and_(
                    BankConnection.connection_type == ConnectionType.PSD2.value,
                    BankConnection.status == ConnectionStatus.ACTIVE.value,
                    BankConnection.consent_expires_at.isnot(None),
                    BankConnection.consent_expires_at <= cutoff_date,
                )
            )

            result = await db.execute(query)
            connections = result.scalars().all()

            for connection in connections:
                stats["connections_checked"] += 1
                stats["consents_expiring_soon"] += 1

                try:
                    # Versuche Consent zu erneuern
                    refresh_result = await import_service.refresh_psd2_consent(
                        connection_id=connection.id
                    )

                    if refresh_result.get("refreshed"):
                        stats["consents_refreshed"] += 1
                        logger.info(
                            "psd2_consent_refreshed",
                            connection_id=str(connection.id),
                        )
                    elif refresh_result.get("notification_sent"):
                        stats["notifications_sent"] += 1
                        logger.info(
                            "psd2_consent_notification_sent",
                            connection_id=str(connection.id),
                            expires_at=str(connection.consent_expires_at),
                        )

                except Exception as e:
                    stats["consents_failed"] += 1
                    logger.warning(
                        "psd2_consent_refresh_failed",
                        connection_id=str(connection.id),
                        **safe_error_log(e),
                    )

            logger.info(
                "psd2_consent_refresh_completed",
                **stats,
            )

    except Exception as e:
        logger.error(
            "psd2_consent_refresh_failed",
            **safe_error_log(e),
            exc_info=True,
        )
        raise

    return stats


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_psd2_tasks.check_expired_connections",
    queue="banking",
)
def check_expired_connections(self) -> Dict[str, Any]:
    """
    Pruefe und markiere abgelaufene Verbindungen.

    Wird taeglich ausgefuehrt (via Celery Beat).
    Setzt Status auf EXPIRED bei abgelaufenem Consent/Token.

    Returns:
        Check-Statistik
    """
    logger.info(
        "psd2_check_expired_started",
        task_id=self.request.id,
    )

    return run_async(_check_expired_connections())


async def _check_expired_connections() -> Dict[str, Any]:
    """Async Implementation fuer check_expired_connections."""
    from app.db.models_banking_connection import (
        BankConnection, ConnectionType, ConnectionStatus
    )
    from app.services.notification_service import NotificationService

    stats = {
        "connections_checked": 0,
        "connections_expired": 0,
        "notifications_sent": 0,
    }

    try:
        async with async_session_factory() as db:
            now = datetime.now(timezone.utc)

            # Finde abgelaufene PSD2-Verbindungen
            query = select(BankConnection).where(
                and_(
                    BankConnection.connection_type == ConnectionType.PSD2.value,
                    BankConnection.status == ConnectionStatus.ACTIVE.value,
                    or_(
                        and_(
                            BankConnection.consent_expires_at.isnot(None),
                            BankConnection.consent_expires_at <= now,
                        ),
                        and_(
                            BankConnection.token_expires_at.isnot(None),
                            BankConnection.token_expires_at <= now,
                        ),
                    ),
                )
            )

            result = await db.execute(query)
            connections = result.scalars().all()

            notification_service = NotificationService()

            for connection in connections:
                stats["connections_checked"] += 1

                # Status auf EXPIRED setzen
                connection.status = ConnectionStatus.EXPIRED.value
                connection.is_healthy = False
                stats["connections_expired"] += 1

                # Benachrichtigung senden
                try:
                    await notification_service.create_notification(
                        db=db,
                        company_id=connection.company_id,
                        notification_type="BANK_CONNECTION_EXPIRED",
                        title="Bankverbindung abgelaufen",
                        message=(
                            f"Die Verbindung zu {connection.bank_name} ist abgelaufen. "
                            f"Bitte erneuern Sie den Zugang."
                        ),
                        reference_type="bank_connection",
                        reference_id=connection.id,
                        data={
                            "bank_name": connection.bank_name,
                            "connection_type": connection.connection_type,
                        },
                    )
                    stats["notifications_sent"] += 1
                except Exception as e:
                    logger.warning(
                        "psd2_expired_notification_failed",
                        connection_id=str(connection.id),
                        **safe_error_log(e),
                    )

                logger.info(
                    "psd2_connection_marked_expired",
                    connection_id=str(connection.id),
                    bank_name=connection.bank_name,
                )

            await db.commit()

            logger.info(
                "psd2_check_expired_completed",
                **stats,
            )

    except Exception as e:
        logger.error(
            "psd2_check_expired_failed",
            **safe_error_log(e),
            exc_info=True,
        )
        raise

    return stats


# =============================================================================
# AUTO-RECONCILIATION
# =============================================================================


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_psd2_tasks.auto_reconcile_transactions",
    max_retries=2,
    default_retry_delay=60,
    queue="banking",
)
def auto_reconcile_transactions(
    self,
    connection_id: Optional[str] = None,
    account_id: Optional[str] = None,
    limit: int = 500,
) -> Dict[str, Any]:
    """
    Automatischer Zahlungsabgleich fuer importierte Transaktionen.

    Wird nach jedem Import oder periodisch ausgefuehrt.

    Matching-Strategien (nach Prioritaet):
    1. IBAN + Betrag (exakt) - 99% Confidence
    2. Referenznummer - 95% Confidence
    3. Skonto-Erkennung - 92% Confidence
    4. Kundennummer + Betrag - 85% Confidence
    5. Fuzzy Matching - 70%+ Confidence

    Args:
        connection_id: Optional - nur fuer bestimmte Verbindung
        account_id: Optional - nur fuer bestimmtes Konto
        limit: Max. Transaktionen pro Durchlauf

    Returns:
        Reconciliation-Statistik
    """
    logger.info(
        "psd2_auto_reconcile_started",
        task_id=self.request.id,
        connection_id=connection_id,
        account_id=account_id,
        limit=limit,
    )

    return run_async(_auto_reconcile_transactions(connection_id, account_id, limit))


async def _auto_reconcile_transactions(
    connection_id: Optional[str] = None,
    account_id: Optional[str] = None,
    limit: int = 500,
) -> Dict[str, Any]:
    """Async Implementation fuer auto_reconcile_transactions."""
    from app.db.models_banking_connection import ImportedTransaction
    from app.services.banking.auto_reconciliation_service import (
        AutoReconciliationService,
    )

    stats = {
        "transactions_processed": 0,
        "transactions_matched": 0,
        "transactions_suggested": 0,
        "transactions_unmatched": 0,
        "confidence_distribution": {
            "high": 0,     # >= 95%
            "medium": 0,   # 80-94%
            "low": 0,      # 70-79%
        },
        "match_methods": {},
        "errors": 0,
    }

    try:
        async with async_session_factory() as db:
            reconciliation_service = AutoReconciliationService(db)

            # Hole pending Transaktionen
            query = select(ImportedTransaction).where(
                ImportedTransaction.reconciliation_status == "pending"
            ).order_by(
                ImportedTransaction.booking_date.desc()
            ).limit(limit)

            if account_id:
                query = query.where(
                    ImportedTransaction.account_id == UUID(account_id)
                )

            # Falls connection_id, hole alle accounts der connection
            if connection_id and not account_id:
                from app.db.models_banking_connection import ConnectedBankAccount
                subquery = select(ConnectedBankAccount.id).where(
                    ConnectedBankAccount.connection_id == UUID(connection_id)
                )
                query = query.where(ImportedTransaction.account_id.in_(subquery))

            result = await db.execute(query)
            transactions = result.scalars().all()

            for transaction in transactions:
                stats["transactions_processed"] += 1

                try:
                    match_result = await reconciliation_service.reconcile_transaction(
                        transaction_id=transaction.id
                    )

                    if match_result.get("matched"):
                        stats["transactions_matched"] += 1
                        confidence = match_result.get("confidence", 0)

                        # Confidence Distribution
                        if confidence >= 0.95:
                            stats["confidence_distribution"]["high"] += 1
                        elif confidence >= 0.80:
                            stats["confidence_distribution"]["medium"] += 1
                        else:
                            stats["confidence_distribution"]["low"] += 1

                        # Match Method Tracking
                        method = match_result.get("match_type", "unknown")
                        stats["match_methods"][method] = (
                            stats["match_methods"].get(method, 0) + 1
                        )

                    elif match_result.get("suggestions"):
                        stats["transactions_suggested"] += 1
                    else:
                        stats["transactions_unmatched"] += 1

                except Exception as e:
                    stats["errors"] += 1
                    logger.warning(
                        "psd2_reconcile_tx_failed",
                        transaction_id=str(transaction.id),
                        **safe_error_log(e),
                    )

            await db.commit()

            logger.info(
                "psd2_auto_reconcile_completed",
                processed=stats["transactions_processed"],
                matched=stats["transactions_matched"],
                suggested=stats["transactions_suggested"],
                unmatched=stats["transactions_unmatched"],
            )

    except Exception as e:
        logger.error(
            "psd2_auto_reconcile_failed",
            **safe_error_log(e),
            exc_info=True,
        )
        raise

    return stats


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_psd2_tasks.reconcile_pending_batch",
    queue="banking",
)
def reconcile_pending_batch(self, company_id: str) -> Dict[str, Any]:
    """
    Batch-Reconciliation fuer alle pending Transaktionen einer Company.

    Wird periodisch oder on-demand ausgefuehrt.

    Args:
        company_id: Company-ID

    Returns:
        Batch-Statistik
    """
    logger.info(
        "psd2_reconcile_batch_started",
        task_id=self.request.id,
        company_id=company_id,
    )

    return run_async(_reconcile_pending_batch(company_id))


async def _reconcile_pending_batch(company_id: str) -> Dict[str, Any]:
    """Async Implementation fuer reconcile_pending_batch."""
    from app.services.banking.auto_reconciliation_service import (
        AutoReconciliationService,
    )

    try:
        async with async_session_factory() as db:
            reconciliation_service = AutoReconciliationService(db)

            result = await reconciliation_service.reconcile_pending_transactions(
                company_id=UUID(company_id)
            )

            logger.info(
                "psd2_reconcile_batch_completed",
                company_id=company_id,
                processed=result.get("processed", 0),
                matched=result.get("matched", 0),
            )

            return result

    except Exception as e:
        logger.error(
            "psd2_reconcile_batch_failed",
            company_id=company_id,
            **safe_error_log(e),
            exc_info=True,
        )
        return {"success": False, "error": str(e)}


# =============================================================================
# PAYMENT PROCESSING
# =============================================================================


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_psd2_tasks.process_scheduled_payments",
    max_retries=2,
    default_retry_delay=300,
    queue="banking",
)
def process_scheduled_payments(self) -> Dict[str, Any]:
    """
    Verarbeite geplante Zahlungen.

    Wird stuendlich ausgefuehrt (via Celery Beat).
    Submittiert Zahlungen deren Ausfuehrungsdatum erreicht ist.

    Returns:
        Processing-Statistik
    """
    logger.info(
        "psd2_process_payments_started",
        task_id=self.request.id,
    )

    return run_async(_process_scheduled_payments())


async def _process_scheduled_payments() -> Dict[str, Any]:
    """Async Implementation fuer process_scheduled_payments."""
    from app.db.models_banking_connection import (
        PaymentInitiation, PaymentInitiationStatus
    )
    from app.services.banking.payment_initiation_service import (
        PaymentInitiationService,
    )

    stats = {
        "payments_checked": 0,
        "payments_submitted": 0,
        "payments_failed": 0,
        "payments_awaiting_sca": 0,
        "total_amount": 0.0,
        "errors": [],
    }

    try:
        async with async_session_factory() as db:
            payment_service = PaymentInitiationService(db)
            now = datetime.now(timezone.utc)

            # Finde Zahlungen die ausgefuehrt werden sollen
            query = select(PaymentInitiation).where(
                and_(
                    PaymentInitiation.status.in_([
                        PaymentInitiationStatus.PENDING_APPROVAL.value,
                        PaymentInitiationStatus.AWAITING_SCA.value,
                    ]),
                    or_(
                        PaymentInitiation.requested_execution_date.is_(None),
                        PaymentInitiation.requested_execution_date <= now,
                    ),
                )
            )

            result = await db.execute(query)
            payments = result.scalars().all()

            for payment in payments:
                stats["payments_checked"] += 1

                try:
                    # Genehmigung pruefen
                    if payment.requires_approval and not payment.approved_by_id:
                        logger.debug(
                            "psd2_payment_awaiting_approval",
                            payment_id=str(payment.id),
                        )
                        continue

                    # SCA pruefen
                    if payment.status == PaymentInitiationStatus.AWAITING_SCA.value:
                        stats["payments_awaiting_sca"] += 1
                        continue

                    # Zahlung einreichen
                    submit_result = await payment_service.submit_payment(
                        payment_id=payment.id
                    )

                    if submit_result.get("submitted"):
                        stats["payments_submitted"] += 1
                        stats["total_amount"] += float(payment.amount)
                        logger.info(
                            "psd2_payment_submitted",
                            payment_id=str(payment.id),
                            # SECURITY: Betrag nicht loggen
                        )
                    elif submit_result.get("requires_sca"):
                        stats["payments_awaiting_sca"] += 1
                    else:
                        stats["payments_failed"] += 1
                        stats["errors"].append({
                            "payment_id": str(payment.id),
                            "error": submit_result.get("error", "Unbekannt"),
                        })

                except Exception as e:
                    stats["payments_failed"] += 1
                    stats["errors"].append({
                        "payment_id": str(payment.id),
                        "error": str(e)[:200],
                    })
                    logger.warning(
                        "psd2_payment_processing_failed",
                        payment_id=str(payment.id),
                        **safe_error_log(e),
                    )

            logger.info(
                "psd2_process_payments_completed",
                checked=stats["payments_checked"],
                submitted=stats["payments_submitted"],
                failed=stats["payments_failed"],
                awaiting_sca=stats["payments_awaiting_sca"],
            )

    except Exception as e:
        logger.error(
            "psd2_process_payments_failed",
            **safe_error_log(e),
            exc_info=True,
        )
        raise

    return stats


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_psd2_tasks.check_payment_status",
    queue="banking",
)
def check_payment_status(self, payment_id: str) -> Dict[str, Any]:
    """
    Pruefe Status einer eingereichten Zahlung.

    Wird nach Einreichung oder periodisch aufgerufen.

    Args:
        payment_id: Payment-ID

    Returns:
        Status-Ergebnis
    """
    logger.info(
        "psd2_check_payment_status_started",
        task_id=self.request.id,
        payment_id=payment_id,
    )

    return run_async(_check_payment_status(payment_id))


async def _check_payment_status(payment_id: str) -> Dict[str, Any]:
    """Async Implementation fuer check_payment_status."""
    from app.db.models_banking_connection import PaymentInitiation
    from app.services.banking.payment_initiation_service import (
        PaymentInitiationService,
    )

    try:
        async with async_session_factory() as db:
            payment = await db.get(PaymentInitiation, UUID(payment_id))

            if not payment:
                return {"success": False, "error": "Zahlung nicht gefunden"}

            payment_service = PaymentInitiationService(db)
            result = await payment_service.check_status(payment_id=payment.id)

            logger.info(
                "psd2_payment_status_checked",
                payment_id=payment_id,
                status=result.get("status"),
            )

            return result

    except Exception as e:
        logger.error(
            "psd2_check_payment_status_failed",
            payment_id=payment_id,
            **safe_error_log(e),
            exc_info=True,
        )
        return {"success": False, "error": str(e)}


# =============================================================================
# HEALTH & MONITORING
# =============================================================================


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_psd2_tasks.update_connection_health",
    queue="maintenance",
)
def update_connection_health(self) -> Dict[str, Any]:
    """
    Aktualisiere Health-Status aller Verbindungen.

    Wird periodisch ausgefuehrt (via Celery Beat).
    Setzt is_healthy basierend auf letzten Sync-Ergebnissen.

    Returns:
        Health-Statistik
    """
    logger.info(
        "psd2_health_update_started",
        task_id=self.request.id,
    )

    return run_async(_update_connection_health())


async def _update_connection_health() -> Dict[str, Any]:
    """Async Implementation fuer update_connection_health."""
    from app.db.models_banking_connection import BankConnection, ConnectionStatus

    stats = {
        "connections_checked": 0,
        "healthy": 0,
        "unhealthy": 0,
        "error_threshold_exceeded": 0,
    }

    try:
        async with async_session_factory() as db:
            query = select(BankConnection).where(
                BankConnection.status.in_([
                    ConnectionStatus.ACTIVE.value,
                    ConnectionStatus.ERROR.value,
                ])
            )

            result = await db.execute(query)
            connections = result.scalars().all()

            error_threshold = 5  # Max consecutive errors
            stale_hours = 24     # Max hours without successful sync

            now = datetime.now(timezone.utc)

            for connection in connections:
                stats["connections_checked"] += 1

                is_healthy = True

                # Check error count
                if connection.error_count >= error_threshold:
                    is_healthy = False
                    stats["error_threshold_exceeded"] += 1

                # Check last sync freshness
                if connection.last_sync_at:
                    hours_since_sync = (
                        now - connection.last_sync_at
                    ).total_seconds() / 3600
                    if hours_since_sync > stale_hours:
                        is_healthy = False

                # Update health status
                connection.is_healthy = is_healthy

                if is_healthy:
                    stats["healthy"] += 1
                    # Reset error count on healthy
                    if connection.error_count > 0:
                        connection.error_count = 0
                else:
                    stats["unhealthy"] += 1

            await db.commit()

            logger.info(
                "psd2_health_update_completed",
                **stats,
            )

    except Exception as e:
        logger.error(
            "psd2_health_update_failed",
            **safe_error_log(e),
            exc_info=True,
        )
        raise

    return stats


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_psd2_tasks.cleanup_old_sync_logs",
    queue="maintenance",
)
def cleanup_old_sync_logs(self, days_to_keep: int = 90) -> Dict[str, Any]:
    """
    Bereinige alte Sync-Logs.

    Wird woechentlich ausgefuehrt (via Celery Beat).

    Args:
        days_to_keep: Anzahl Tage aufbewahren

    Returns:
        Cleanup-Statistik
    """
    logger.info(
        "psd2_cleanup_logs_started",
        task_id=self.request.id,
        days_to_keep=days_to_keep,
    )

    return run_async(_cleanup_old_sync_logs(days_to_keep))


async def _cleanup_old_sync_logs(days_to_keep: int = 90) -> Dict[str, Any]:
    """Async Implementation fuer cleanup_old_sync_logs."""
    from app.db.models_banking_connection import BankSyncLog
    from sqlalchemy import delete

    stats = {
        "logs_deleted": 0,
    }

    try:
        async with async_session_factory() as db:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_keep)

            result = await db.execute(
                delete(BankSyncLog).where(
                    BankSyncLog.started_at < cutoff_date
                )
            )

            stats["logs_deleted"] = result.rowcount
            await db.commit()

            logger.info(
                "psd2_cleanup_logs_completed",
                **stats,
            )

    except Exception as e:
        logger.error(
            "psd2_cleanup_logs_failed",
            **safe_error_log(e),
            exc_info=True,
        )
        raise

    return stats


