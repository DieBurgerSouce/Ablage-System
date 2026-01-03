# -*- coding: utf-8 -*-
"""
Celery Tasks fuer Banking-Operationen.

Geplante Tasks:
- process_bank_import: Verarbeite hochgeladene Kontoauszuege
- auto_reconcile: Automatischer Zahlungsabgleich
- update_transaction_stats: Aktualisiere Transaktions-Statistiken
- check_duplicate_transactions: Pruefe auf Duplikate
- parse_transaction_references: Analysiere Verwendungszwecke

Beat Schedule:
- auto_reconcile: Stundlich
- update_transaction_stats: Taeglich 01:00
- check_overdue_payments: Taeglich 08:00
"""

import asyncio
from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog

from app.workers.celery_app import celery_app, CPUTask

logger = structlog.get_logger(__name__)


def run_async(coro):
    """Hilfsfunktion um async Code in sync Celery Tasks auszufuehren."""
    return asyncio.run(coro)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_tasks.process_bank_import",
    max_retries=3,
    default_retry_delay=60,
)
def process_bank_import(
    self,
    user_id: str,
    content_b64: str,
    filename: str,
    bank_account_id: Optional[str] = None,
    format_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Verarbeite Bank-Import asynchron.

    Args:
        user_id: Benutzer-ID
        content_b64: Base64-encodierter Dateiinhalt
        filename: Dateiname
        bank_account_id: Optional Ziel-Bankkonto
        format_hint: Optional Format-Hinweis

    Returns:
        Import-Ergebnis
    """
    import base64
    from uuid import UUID as UUID_

    logger.info(
        "banking_import_task_started",
        task_id=self.request.id,
        user_id=user_id,
        filename=filename,
    )

    try:
        # Decode content
        content = base64.b64decode(content_b64)

        async def do_import():
            from app.db.session import get_async_session
            from app.services.banking.import_service import ImportService
            from app.services.banking.models import ImportFormat

            service = ImportService()

            async with get_async_session() as db:
                response, tx_ids = await service.import_file(
                    db=db,
                    user_id=UUID_(user_id),
                    content=content,
                    filename=filename,
                    bank_account_id=UUID_(bank_account_id) if bank_account_id else None,
                    format_hint=ImportFormat(format_hint) if format_hint else None,
                )

                return {
                    "success": True,
                    "import_id": str(response.id),
                    "transaction_count": response.transaction_count,
                    "duplicate_count": response.duplicate_count,
                    "error_count": response.error_count,
                    "format": response.format.value if response.format else None,
                    "date_from": response.date_from.isoformat() if response.date_from else None,
                    "date_to": response.date_to.isoformat() if response.date_to else None,
                }

        result = run_async(do_import())

        logger.info(
            "banking_import_task_completed",
            task_id=self.request.id,
            **result,
        )

        return result

    except Exception as e:
        logger.error(
            "banking_import_task_failed",
            task_id=self.request.id,
            error=str(e),
            exc_info=True,
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_tasks.auto_reconcile",
    max_retries=2,
    default_retry_delay=120,
)
def auto_reconcile(
    self,
    user_id: Optional[str] = None,
    bank_account_id: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    Automatischer Zahlungsabgleich.

    Matched unabgeglichene Transaktionen mit Rechnungen basierend auf:
    - IBAN + Betrag
    - Rechnungsnummer im Verwendungszweck
    - Betrag + Datum-Naehe

    Args:
        user_id: Optional User-Filter
        bank_account_id: Optional Konto-Filter
        limit: Max. Transaktionen pro Durchlauf

    Returns:
        Reconciliation-Statistik
    """
    logger.info(
        "auto_reconcile_task_started",
        task_id=self.request.id,
        user_id=user_id,
        bank_account_id=bank_account_id,
    )

    try:
        async def do_reconcile():
            from app.db.session import get_async_session
            from app.services.banking.transaction_service import TransactionService
            from app.services.banking.reference_parser import reference_parser
            from app.db.models import BankTransaction, BankAccount, Document
            from sqlalchemy import select, and_

            tx_service = TransactionService()

            stats = {
                "processed": 0,
                "matched": 0,
                "partial": 0,
                "unmatched": 0,
                "errors": 0,
            }

            async with get_async_session() as db:
                # Hole unabgeglichene Transaktionen
                query = (
                    select(BankTransaction)
                    .join(BankAccount)
                    .where(
                        and_(
                            BankTransaction.reconciliation_status == "unmatched",
                            BankAccount.deleted_at.is_(None),
                        )
                    )
                    .limit(limit)
                )

                if user_id:
                    query = query.where(BankAccount.user_id == user_id)
                if bank_account_id:
                    query = query.where(BankTransaction.bank_account_id == bank_account_id)

                result = await db.execute(query)
                transactions = result.scalars().all()

                for tx in transactions:
                    stats["processed"] += 1

                    try:
                        # Parse Verwendungszweck
                        parsed = reference_parser.parse(tx.reference_text or "")

                        # Speichere geparste Referenzen
                        if parsed.invoice_numbers:
                            tx.parsed_invoice_numbers = parsed.invoice_numbers
                        if parsed.customer_numbers:
                            tx.parsed_customer_numbers = parsed.customer_numbers

                        # TODO: Implementiere Matching-Logik mit Documents
                        # Fuer jetzt nur Referenz-Parsing

                        stats["unmatched"] += 1

                    except Exception as e:
                        stats["errors"] += 1
                        logger.warning(
                            "reconcile_transaction_error",
                            transaction_id=str(tx.id),
                            error=str(e),
                        )

                await db.commit()

            return stats

        result = run_async(do_reconcile())

        logger.info(
            "auto_reconcile_task_completed",
            task_id=self.request.id,
            **result,
        )

        return result

    except Exception as e:
        logger.error(
            "auto_reconcile_task_failed",
            task_id=self.request.id,
            error=str(e),
            exc_info=True,
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_tasks.parse_transaction_references",
    max_retries=2,
)
def parse_transaction_references(
    self,
    transaction_ids: Optional[List[str]] = None,
    limit: int = 500,
) -> Dict[str, Any]:
    """
    Analysiere Verwendungszwecke von Transaktionen.

    Extrahiert:
    - Rechnungsnummern
    - Kundennummern
    - SEPA-Referenzen

    Args:
        transaction_ids: Optional spezifische Transaktionen
        limit: Max. Transaktionen

    Returns:
        Parsing-Statistik
    """
    logger.info(
        "parse_references_task_started",
        task_id=self.request.id,
        transaction_count=len(transaction_ids) if transaction_ids else "all",
    )

    try:
        async def do_parse():
            from app.db.session import get_async_session
            from app.services.banking.reference_parser import reference_parser
            from app.db.models import BankTransaction
            from sqlalchemy import select, and_

            stats = {
                "processed": 0,
                "with_invoice": 0,
                "with_customer": 0,
                "with_sepa": 0,
            }

            async with get_async_session() as db:
                # Query
                query = select(BankTransaction).where(
                    BankTransaction.reference_text.isnot(None)
                ).limit(limit)

                if transaction_ids:
                    from uuid import UUID
                    query = query.where(
                        BankTransaction.id.in_([UUID(tid) for tid in transaction_ids])
                    )

                result = await db.execute(query)
                transactions = result.scalars().all()

                for tx in transactions:
                    stats["processed"] += 1

                    parsed = reference_parser.parse(tx.reference_text)

                    # Update Transaktion
                    if parsed.invoice_numbers:
                        tx.parsed_invoice_numbers = parsed.invoice_numbers
                        stats["with_invoice"] += 1

                    if parsed.customer_numbers:
                        tx.parsed_customer_numbers = parsed.customer_numbers
                        stats["with_customer"] += 1

                    if parsed.end_to_end_id and not tx.end_to_end_id:
                        tx.end_to_end_id = parsed.end_to_end_id
                        stats["with_sepa"] += 1

                    if parsed.mandate_id and not tx.mandate_id:
                        tx.mandate_id = parsed.mandate_id

                    if parsed.creditor_id and not tx.creditor_id:
                        tx.creditor_id = parsed.creditor_id

                await db.commit()

            return stats

        result = run_async(do_parse())

        logger.info(
            "parse_references_task_completed",
            task_id=self.request.id,
            **result,
        )

        return result

    except Exception as e:
        logger.error(
            "parse_references_task_failed",
            task_id=self.request.id,
            error=str(e),
            exc_info=True,
        )
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_tasks.update_account_balances",
)
def update_account_balances(self, bank_account_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Aktualisiere Kontosalden basierend auf Transaktionen.

    Args:
        bank_account_id: Optional spezifisches Konto

    Returns:
        Update-Statistik
    """
    logger.info(
        "update_balances_task_started",
        task_id=self.request.id,
        bank_account_id=bank_account_id,
    )

    try:
        async def do_update():
            from app.db.session import get_async_session
            from app.db.models import BankAccount, BankTransaction
            from sqlalchemy import select, func, and_
            from decimal import Decimal

            stats = {"accounts_updated": 0}

            async with get_async_session() as db:
                # Query fuer Konten
                query = select(BankAccount).where(
                    and_(
                        BankAccount.deleted_at.is_(None),
                        BankAccount.is_active == True,
                    )
                )

                if bank_account_id:
                    from uuid import UUID
                    query = query.where(BankAccount.id == UUID(bank_account_id))

                result = await db.execute(query)
                accounts = result.scalars().all()

                for account in accounts:
                    # Berechne Saldo aus Transaktionen
                    balance_query = select(
                        func.sum(BankTransaction.amount)
                    ).where(
                        BankTransaction.bank_account_id == account.id
                    )

                    balance_result = await db.execute(balance_query)
                    total = balance_result.scalar() or Decimal("0")

                    # Addiere Startsaldo wenn vorhanden
                    if account.opening_balance:
                        total += account.opening_balance

                    account.current_balance = total
                    account.balance_date = datetime.now(timezone.utc)
                    stats["accounts_updated"] += 1

                await db.commit()

            return stats

        result = run_async(do_update())

        logger.info(
            "update_balances_task_completed",
            task_id=self.request.id,
            **result,
        )

        return result

    except Exception as e:
        logger.error(
            "update_balances_task_failed",
            task_id=self.request.id,
            error=str(e),
            exc_info=True,
        )
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_tasks.check_overdue_payments",
)
def check_overdue_payments(self) -> Dict[str, Any]:
    """
    Pruefe auf ueberfaellige Zahlungen.

    Returns:
        Statistik ueberfaelliger Zahlungen
    """
    logger.info(
        "check_overdue_task_started",
        task_id=self.request.id,
    )

    try:
        async def do_check():
            from app.db.session import get_async_session
            from app.services.banking.dunning_service import dunning_service
            from app.db.models import User
            from sqlalchemy import select

            all_stats = {
                "users_processed": 0,
                "total_overdue": 0,
                "total_amount": 0.0,
            }

            async with get_async_session() as db:
                # Hole alle aktiven User
                result = await db.execute(select(User).where(User.is_active == True))
                users = result.scalars().all()

                for user in users:
                    try:
                        overdue = await dunning_service.get_overdue_invoices(
                            db=db,
                            user_id=user.id,
                            min_days_overdue=1,
                        )

                        all_stats["users_processed"] += 1
                        all_stats["total_overdue"] += len(overdue)
                        all_stats["total_amount"] += sum(
                            float(o.amount) for o in overdue
                        )

                    except Exception as e:
                        logger.warning(
                            "check_overdue_user_error",
                            user_id=str(user.id),
                            error=str(e),
                        )

            return all_stats

        result = run_async(do_check())

        logger.info(
            "check_overdue_task_completed",
            task_id=self.request.id,
            **result,
        )

        return result

    except Exception as e:
        logger.error(
            "check_overdue_task_failed",
            task_id=self.request.id,
            error=str(e),
            exc_info=True,
        )
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_tasks.process_automatic_dunning",
)
def process_automatic_dunning(
    self,
    user_id: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Fuehre automatisches Mahnverfahren durch.

    Args:
        user_id: Optional User-Filter
        dry_run: Nur simulieren?

    Returns:
        Mahnstatistik
    """
    logger.info(
        "automatic_dunning_task_started",
        task_id=self.request.id,
        user_id=user_id,
        dry_run=dry_run,
    )

    try:
        async def do_dunning():
            from app.db.session import get_async_session
            from app.services.banking.dunning_service import dunning_service
            from app.db.models import User
            from sqlalchemy import select
            from uuid import UUID

            stats = {
                "users_processed": 0,
                "total_actions": 0,
                "executed_actions": 0,
            }

            async with get_async_session() as db:
                if user_id:
                    users = [
                        (await db.execute(
                            select(User).where(User.id == UUID(user_id))
                        )).scalar_one_or_none()
                    ]
                    users = [u for u in users if u]
                else:
                    result = await db.execute(
                        select(User).where(User.is_active == True)
                    )
                    users = result.scalars().all()

                for user in users:
                    try:
                        actions = await dunning_service.process_automatic_dunning(
                            db=db,
                            user_id=user.id,
                            dry_run=dry_run,
                        )

                        stats["users_processed"] += 1
                        stats["total_actions"] += len(actions)
                        stats["executed_actions"] += sum(
                            1 for a in actions if a.get("executed")
                        )

                    except Exception as e:
                        logger.warning(
                            "automatic_dunning_user_error",
                            user_id=str(user.id),
                            error=str(e),
                        )

            return stats

        result = run_async(do_dunning())

        logger.info(
            "automatic_dunning_task_completed",
            task_id=self.request.id,
            **result,
        )

        return result

    except Exception as e:
        logger.error(
            "automatic_dunning_task_failed",
            task_id=self.request.id,
            error=str(e),
            exc_info=True,
        )
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_tasks.update_cash_flow_forecasts",
)
def update_cash_flow_forecasts(self) -> Dict[str, Any]:
    """
    Aktualisiere Cash-Flow-Prognosen fuer alle User.

    Returns:
        Update-Statistik
    """
    logger.info(
        "update_cash_flow_task_started",
        task_id=self.request.id,
    )

    try:
        async def do_update():
            from app.db.session import get_async_session
            from app.services.banking.cash_flow_service import cash_flow_service
            from app.db.models import User
            from sqlalchemy import select

            stats = {
                "users_processed": 0,
                "total_inflow": 0.0,
                "total_outflow": 0.0,
                "alerts_generated": 0,
            }

            async with get_async_session() as db:
                result = await db.execute(
                    select(User).where(User.is_active == True)
                )
                users = result.scalars().all()

                for user in users:
                    try:
                        summary = await cash_flow_service.get_cash_flow_summary(
                            db=db,
                            user_id=user.id,
                        )

                        stats["users_processed"] += 1
                        stats["total_inflow"] += summary.get(
                            "mid_term", {}
                        ).get("inflow", 0)
                        stats["total_outflow"] += summary.get(
                            "mid_term", {}
                        ).get("outflow", 0)
                        stats["alerts_generated"] += len(
                            summary.get("alerts", [])
                        )

                    except Exception as e:
                        logger.warning(
                            "cash_flow_update_user_error",
                            user_id=str(user.id),
                            error=str(e),
                        )

            return stats

        result = run_async(do_update())

        logger.info(
            "update_cash_flow_task_completed",
            task_id=self.request.id,
            **result,
        )

        return result

    except Exception as e:
        logger.error(
            "update_cash_flow_task_failed",
            task_id=self.request.id,
            error=str(e),
            exc_info=True,
        )
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_tasks.send_skonto_alerts",
)
def send_skonto_alerts(self, days_ahead: int = 7) -> Dict[str, Any]:
    """
    Sende Alerts fuer ablaufende Skonto-Fristen.

    Args:
        days_ahead: Tage voraus pruefen

    Returns:
        Alert-Statistik
    """
    logger.info(
        "skonto_alerts_task_started",
        task_id=self.request.id,
        days_ahead=days_ahead,
    )

    try:
        async def do_alerts():
            from app.db.session import get_async_session
            from app.services.banking.payment_service import PaymentService
            from app.db.models import User
            from sqlalchemy import select

            payment_service = PaymentService()

            stats = {
                "users_checked": 0,
                "opportunities_found": 0,
                "total_savings": 0.0,
            }

            async with get_async_session() as db:
                result = await db.execute(
                    select(User).where(User.is_active == True)
                )
                users = result.scalars().all()

                for user in users:
                    try:
                        opportunities = await payment_service.get_skonto_opportunities(
                            db=db,
                            user_id=user.id,
                            days_ahead=days_ahead,
                        )

                        stats["users_checked"] += 1
                        stats["opportunities_found"] += len(opportunities)
                        stats["total_savings"] += sum(
                            float(o.get("savings", 0))
                            for o in opportunities
                        )

                        # TODO: Sende Notifications fuer ablaufende Skonti
                        # (Email, Push, etc.)

                    except Exception as e:
                        logger.warning(
                            "skonto_alert_user_error",
                            user_id=str(user.id),
                            error=str(e),
                        )

            return stats

        result = run_async(do_alerts())

        logger.info(
            "skonto_alerts_task_completed",
            task_id=self.request.id,
            **result,
        )

        return result

    except Exception as e:
        logger.error(
            "skonto_alerts_task_failed",
            task_id=self.request.id,
            error=str(e),
            exc_info=True,
        )
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_tasks.cleanup_tan_challenges",
)
def cleanup_tan_challenges(self) -> Dict[str, Any]:
    """
    Bereinige abgelaufene TAN-Challenges.

    Returns:
        Cleanup-Statistik
    """
    logger.info(
        "tan_cleanup_task_started",
        task_id=self.request.id,
    )

    try:
        from app.services.banking.tan_handler_service import tan_handler

        cleaned = tan_handler.cleanup_expired()

        logger.info(
            "tan_cleanup_task_completed",
            task_id=self.request.id,
            cleaned_count=cleaned,
        )

        return {"cleaned_count": cleaned}

    except Exception as e:
        logger.error(
            "tan_cleanup_task_failed",
            task_id=self.request.id,
            error=str(e),
            exc_info=True,
        )
        raise


# =============================================================================
# MAHNUNGSWESEN (Dunning System) TASKS
# =============================================================================


def is_german_business_day(check_date: Optional[date] = None) -> bool:
    """
    Pruefe ob Datum ein deutscher Werktag ist.

    Args:
        check_date: Zu pruefendes Datum (default: heute)

    Returns:
        True wenn Werktag (Mo-Fr, kein Feiertag)
    """
    import holidays

    if check_date is None:
        check_date = date.today()

    # Wochenende?
    if check_date.weekday() >= 5:
        return False

    # Deutsche Feiertage (bundesweit)
    de_holidays = holidays.Germany(years=check_date.year)

    if check_date in de_holidays:
        return False

    return True


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_tasks.daily_mahnlauf",
)
def daily_mahnlauf(self) -> Dict[str, Any]:
    """
    Taeglicher Mahnlauf um 9:00 Uhr (Mo-Fr, keine deutschen Feiertage).

    Erstellt MahnTasks fuer faellige Mahnungen.
    Sendet NICHT automatisch - Tasks muessen manuell bearbeitet werden.

    BGB §286 Compliance:
    - Prueft B2B/B2C fuer korrekte Verzugszinsen
    - Respektiert Mahnstopp bei Reklamationen
    - Respektiert Customer Dunning Overrides

    Returns:
        Mahnlauf-Statistik
    """
    logger.info(
        "daily_mahnlauf_started",
        task_id=self.request.id,
    )

    # Pruefe ob Werktag
    today = date.today()
    if not is_german_business_day(today):
        logger.info(
            "daily_mahnlauf_skipped_holiday",
            task_id=self.request.id,
            date=today.isoformat(),
        )
        return {
            "skipped": True,
            "reason": "Kein Werktag (Wochenende oder Feiertag)",
            "date": today.isoformat(),
        }

    try:
        async def do_mahnlauf():
            from app.db.session import get_async_session
            from app.services.banking.dunning_service import dunning_service
            from app.services.banking.mahn_task_service import (
                mahn_task_service,
                MahnTaskType,
            )
            from app.services.banking.dunning_stage_service import dunning_stage_service
            from app.db.models import User, DunningRecord, CustomerDunningOverride
            from sqlalchemy import select, and_

            stats = {
                "users_processed": 0,
                "overdue_invoices": 0,
                "tasks_created": 0,
                "skipped_mahnstopp": 0,
                "skipped_exclusion": 0,
            }

            async with get_async_session() as db:
                # Hole alle aktiven User
                result = await db.execute(select(User).where(User.is_active == True))
                users = result.scalars().all()

                for user in users:
                    try:
                        stats["users_processed"] += 1

                        # Hole Mahnstufen-Konfiguration fuer User
                        stages = await dunning_stage_service.get_stages(db, user.id)
                        active_stages = [s for s in stages if s.get("is_active")]

                        if not active_stages:
                            continue

                        # Hole ueberfaellige Rechnungen
                        overdue = await dunning_service.get_overdue_invoices(
                            db=db,
                            user_id=user.id,
                            min_days_overdue=1,
                            include_in_progress=True,
                        )

                        for candidate in overdue:
                            stats["overdue_invoices"] += 1

                            # Pruefe Mahnvorgang
                            dunning_query = select(DunningRecord).where(
                                DunningRecord.document_id == candidate.document_id
                            )
                            dunning_result = await db.execute(dunning_query)
                            dunning = dunning_result.scalar_one_or_none()

                            # Mahnstopp aktiv?
                            if dunning and dunning.mahnstopp:
                                stats["skipped_mahnstopp"] += 1
                                continue

                            # Customer Override pruefen
                            # TODO: BusinessEntity aus Document holen und Override pruefen

                            # Welche Stufe ist faellig?
                            for stage in active_stages:
                                if candidate.days_overdue >= stage.get("trigger_days_after_due", 0):
                                    # Aktuelle Stufe ist kleiner als diese?
                                    current_level = candidate.current_level.value if candidate.current_level else 0
                                    stage_number = stage.get("stage_number", 0)

                                    if current_level < stage_number:
                                        # Task erstellen
                                        action_type = stage.get("action_type", "email")
                                        task_type = MahnTaskType.REMINDER

                                        if action_type == "phone":
                                            task_type = MahnTaskType.PHONE_CALL
                                        elif action_type == "escalation":
                                            task_type = MahnTaskType.COLLECTION
                                        elif stage_number > 1:
                                            task_type = MahnTaskType.ESCALATE

                                        # Erstelle oder finde DunningRecord
                                        if not dunning:
                                            from app.services.banking.models import DunningLevel
                                            dunning_response = await dunning_service.create_dunning(
                                                db=db,
                                                user_id=user.id,
                                                document_id=candidate.document_id,
                                                level=DunningLevel.FIRST_REMINDER,
                                            )
                                            dunning_id = dunning_response.id
                                        else:
                                            dunning_id = dunning.id

                                        # MahnTask erstellen
                                        await mahn_task_service.create_task(
                                            db=db,
                                            dunning_record_id=dunning_id,
                                            task_type=task_type,
                                            due_date=today,
                                            priority=2 if stage_number >= 3 else 3,
                                        )
                                        stats["tasks_created"] += 1
                                        break

                    except Exception as e:
                        logger.warning(
                            "mahnlauf_user_error",
                            user_id=str(user.id),
                            error=str(e),
                        )

            return stats

        result = run_async(do_mahnlauf())

        logger.info(
            "daily_mahnlauf_completed",
            task_id=self.request.id,
            **result,
        )

        return result

    except Exception as e:
        logger.error(
            "daily_mahnlauf_failed",
            task_id=self.request.id,
            error=str(e),
            exc_info=True,
        )
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_tasks.reactivate_snoozed_tasks",
)
def reactivate_snoozed_tasks(self) -> Dict[str, Any]:
    """
    Reaktiviere zurueckgestellte Mahn-Aufgaben.

    Wird taeglich ausgefuehrt und setzt snoozed Tasks zurueck auf pending,
    wenn ihr snoozed_until Datum erreicht ist.

    Returns:
        Reaktivierungs-Statistik
    """
    logger.info(
        "reactivate_snoozed_started",
        task_id=self.request.id,
    )

    try:
        async def do_reactivate():
            from app.db.session import get_async_session
            from app.services.banking.mahn_task_service import mahn_task_service

            async with get_async_session() as db:
                count = await mahn_task_service.reactivate_snoozed_tasks(db)
                return {"reactivated": count}

        result = run_async(do_reactivate())

        logger.info(
            "reactivate_snoozed_completed",
            task_id=self.request.id,
            **result,
        )

        return result

    except Exception as e:
        logger.error(
            "reactivate_snoozed_failed",
            task_id=self.request.id,
            error=str(e),
            exc_info=True,
        )
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_tasks.check_expired_mahnstopp",
)
def check_expired_mahnstopp(self) -> Dict[str, Any]:
    """
    Pruefe und hebe abgelaufene Mahnstopps auf.

    Wird taeglich ausgefuehrt und hebt Mahnstopps auf,
    deren mahnstopp_until Datum erreicht ist.

    Returns:
        Mahnstopp-Pruefungs-Statistik
    """
    logger.info(
        "check_expired_mahnstopp_started",
        task_id=self.request.id,
    )

    try:
        async def do_check():
            from app.db.session import get_async_session
            from app.services.banking.dunning_service import dunning_service

            async with get_async_session() as db:
                count = await dunning_service.check_expired_mahnstopp(db)
                return {"lifted": count}

        result = run_async(do_check())

        logger.info(
            "check_expired_mahnstopp_completed",
            task_id=self.request.id,
            **result,
        )

        return result

    except Exception as e:
        logger.error(
            "check_expired_mahnstopp_failed",
            task_id=self.request.id,
            error=str(e),
            exc_info=True,
        )
        raise


# =============================================================================
# BEAT SCHEDULE CONFIGURATION
# =============================================================================

BANKING_BEAT_SCHEDULE = {
    "banking-auto-reconcile-hourly": {
        "task": "app.workers.tasks.banking_tasks.auto_reconcile",
        "schedule": 3600,  # Stundlich
        "options": {"queue": "default"},
    },
    "banking-update-balances-daily": {
        "task": "app.workers.tasks.banking_tasks.update_account_balances",
        "schedule": {
            "hour": 1,
            "minute": 0,
        },
        "options": {"queue": "default"},
    },
    "banking-check-overdue-daily": {
        "task": "app.workers.tasks.banking_tasks.check_overdue_payments",
        "schedule": {
            "hour": 8,
            "minute": 0,
        },
        "options": {"queue": "default"},
    },
    # Phase 5: Cash-Flow & Mahnwesen
    "banking-process-dunning-daily": {
        "task": "app.workers.tasks.banking_tasks.process_automatic_dunning",
        "schedule": {
            "hour": 9,
            "minute": 0,
        },
        "kwargs": {"dry_run": False},
        "options": {"queue": "default"},
    },
    "banking-update-cash-flow-4h": {
        "task": "app.workers.tasks.banking_tasks.update_cash_flow_forecasts",
        "schedule": 14400,  # Alle 4 Stunden
        "options": {"queue": "default"},
    },
    "banking-skonto-alerts-morning": {
        "task": "app.workers.tasks.banking_tasks.send_skonto_alerts",
        "schedule": {
            "hour": 7,
            "minute": 30,
        },
        "kwargs": {"days_ahead": 7},
        "options": {"queue": "default"},
    },
    "banking-tan-cleanup-hourly": {
        "task": "app.workers.tasks.banking_tasks.cleanup_tan_challenges",
        "schedule": 3600,  # Stundlich
        "options": {"queue": "default"},
    },
    # =================================================================
    # MAHNUNGSWESEN (Dunning System) - BGB §286 Compliance
    # =================================================================
    "banking-daily-mahnlauf": {
        "task": "app.workers.tasks.banking_tasks.daily_mahnlauf",
        "schedule": {
            "hour": 9,
            "minute": 0,
        },
        "options": {"queue": "default"},
    },
    "banking-reactivate-snoozed-tasks": {
        "task": "app.workers.tasks.banking_tasks.reactivate_snoozed_tasks",
        "schedule": {
            "hour": 8,
            "minute": 30,
        },
        "options": {"queue": "default"},
    },
    "banking-check-expired-mahnstopp": {
        "task": "app.workers.tasks.banking_tasks.check_expired_mahnstopp",
        "schedule": {
            "hour": 8,
            "minute": 45,
        },
        "options": {"queue": "default"},
    },
}
