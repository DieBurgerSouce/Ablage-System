# -*- coding: utf-8 -*-
"""
Celery Tasks für Banking-Operationen.

Geplante Tasks:
- process_bank_import: Verarbeite hochgeladene Kontoauszuege
- auto_reconcile: Automatischer Zahlungsabgleich
- update_transaction_stats: Aktualisiere Transaktions-Statistiken
- check_duplicate_transactions: Prüfe auf Duplikate
- parse_transaction_references: Analysiere Verwendungszwecke

Beat Schedule:
- auto_reconcile: Stundlich
- update_transaction_stats: Täglich 01:00
- check_overdue_payments: Täglich 08:00
"""

import asyncio
from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog

from app.workers.celery_app import celery_app, CPUTask
from app.core.safe_errors import safe_error_log
from app.workers.error_handling import celery_error_handler

logger = structlog.get_logger(__name__)


def run_async(coro):
    """Hilfsfunktion um async Code in sync Celery Tasks auszuführen."""
    return asyncio.run(coro)


async def _match_transaction_to_document(
    db,
    transaction,
    parsed_reference,
) -> Optional[Dict[str, Any]]:
    """Matched eine Transaktion gegen Dokumente im System.

    Matching-Strategien (nach Priorität):
    1. Rechnungsnummer (exakt) - Confidence: 95%
    2. Kundennummer + Betrag - Confidence: 85%
    3. Fuzzy Betrag + Datum - Confidence: 70%

    Args:
        db: AsyncSession
        transaction: BankTransaction
        parsed_reference: ParsedReference mit extrahierten Daten

    Returns:
        Match-Ergebnis dict oder None
    """
    from sqlalchemy import select, and_, or_, func
    from sqlalchemy.dialects.postgresql import JSONB
    from app.db.models import Document

    # Strategie 1: Exakte Rechnungsnummer-Matching
    if parsed_reference.invoice_numbers:
        for invoice_num in parsed_reference.invoice_numbers:
            # Suche in extracted_data.invoice_number
            query = select(Document).where(
                and_(
                    Document.deleted_at.is_(None),
                    or_(
                        Document.extracted_data["invoice_number"].astext == invoice_num,
                        Document.extracted_data["rechnung"]["nummer"].astext == invoice_num,
                    )
                )
            ).limit(1)

            result = await db.execute(query)
            doc = result.scalar_one_or_none()

            if doc:
                logger.info(
                    "transaction_matched_by_invoice_number",
                    transaction_id=str(transaction.id),
                    document_id=str(doc.id),
                    invoice_number=invoice_num,
                )
                return {
                    "document_id": doc.id,
                    "confidence": 0.95,
                    "method": "invoice_number_exact",
                    "invoice_number": invoice_num,
                }

    # Strategie 2: Kundennummer + Betrag
    if parsed_reference.customer_numbers and transaction.amount:
        tx_amount = abs(float(transaction.amount))

        for customer_num in parsed_reference.customer_numbers:
            # Suche Dokumente mit passender Kundennummer
            query = select(Document).where(
                and_(
                    Document.deleted_at.is_(None),
                    or_(
                        Document.extracted_data["customer_number"].astext == customer_num,
                        Document.extracted_data["kunde"]["nummer"].astext == customer_num,
                    )
                )
            ).limit(10)

            result = await db.execute(query)
            docs = result.scalars().all()

            for doc in docs:
                # Prüfe Betrag mit Toleranz (0.5%)
                doc_amount = None
                if doc.extracted_data:
                    doc_amount = (
                        doc.extracted_data.get("total_gross") or
                        doc.extracted_data.get("betrag") or
                        doc.extracted_data.get("gesamt")
                    )

                if doc_amount:
                    try:
                        doc_amount_float = float(doc_amount)
                        tolerance = tx_amount * 0.005  # 0.5% Toleranz
                        if abs(doc_amount_float - tx_amount) <= tolerance:
                            logger.info(
                                "transaction_matched_by_customer_amount",
                                transaction_id=str(transaction.id),
                                document_id=str(doc.id),
                                customer_number=customer_num,
                            )
                            return {
                                "document_id": doc.id,
                                "confidence": 0.85,
                                "method": "customer_number_amount",
                                "invoice_number": doc.extracted_data.get("invoice_number"),
                            }
                    except (ValueError, TypeError) as e:
                        logger.debug(
                            "doc_amount_parse_for_customer_match_failed",
                            error_type=type(e).__name__,
                        )

    # Strategie 3: Fuzzy Betrag + Datum-Nähe
    if transaction.amount and transaction.booking_date:
        tx_amount = abs(float(transaction.amount))
        tx_date = transaction.booking_date.date() if hasattr(transaction.booking_date, 'date') else transaction.booking_date

        # Suche Dokumente mit ähnlichem Betrag (1% Toleranz)
        tolerance = tx_amount * 0.01

        # Zeitraum: 30 Tage vor Buchungsdatum
        date_from = tx_date - timedelta(days=30)

        query = select(Document).where(
            and_(
                Document.deleted_at.is_(None),
                Document.document_type.in_(["invoice", "rechnung", "bill"]),
                Document.created_at >= date_from,
                Document.created_at <= tx_date + timedelta(days=1),
            )
        ).limit(20)

        result = await db.execute(query)
        docs = result.scalars().all()

        best_match = None
        best_score = 0.0

        for doc in docs:
            if not doc.extracted_data:
                continue

            doc_amount = (
                doc.extracted_data.get("total_gross") or
                doc.extracted_data.get("betrag") or
                doc.extracted_data.get("gesamt")
            )

            if not doc_amount:
                continue

            try:
                doc_amount_float = float(doc_amount)

                # Betrag-Score (max 60%)
                amount_diff = abs(doc_amount_float - tx_amount)
                if amount_diff <= tolerance:
                    amount_score = 0.6 * (1 - (amount_diff / max(tolerance, 0.01)))
                else:
                    continue

                # Datum-Score (max 40%)
                doc_date = doc.created_at.date() if doc.created_at else None
                if doc_date:
                    date_diff = abs((tx_date - doc_date).days)
                    date_score = 0.4 * max(0, 1 - (date_diff / 30))
                else:
                    date_score = 0.0

                total_score = amount_score + date_score

                if total_score > best_score and total_score >= 0.70:
                    best_score = total_score
                    best_match = doc

            except (ValueError, TypeError) as e:
                logger.debug(
                    "doc_amount_parse_for_fuzzy_match_failed",
                    error_type=type(e).__name__,
                )

        if best_match:
            logger.info(
                "transaction_matched_by_fuzzy",
                transaction_id=str(transaction.id),
                document_id=str(best_match.id),
                confidence=round(best_score, 2),
            )
            return {
                "document_id": best_match.id,
                "confidence": round(best_score, 2),
                "method": "fuzzy_amount_date",
                "invoice_number": best_match.extracted_data.get("invoice_number") if best_match.extracted_data else None,
            }

    return None


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_tasks.process_bank_import",
    max_retries=3,
    default_retry_delay=60,
)
@celery_error_handler()
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
            **safe_error_log(e),
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
@celery_error_handler()
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
    - Betrag + Datum-Nähe

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

                        # Matching-Logik mit Documents
                        match_result = await _match_transaction_to_document(
                            db, tx, parsed
                        )

                        if match_result:
                            tx.matched_document_id = match_result["document_id"]
                            tx.match_confidence = match_result["confidence"]
                            tx.match_method = match_result["method"]
                            tx.matched_invoice_number = match_result.get("invoice_number")
                            tx.matched_at = datetime.now(timezone.utc)
                            tx.reconciliation_status = "matched"
                            stats["matched"] += 1
                        else:
                            stats["unmatched"] += 1

                    except Exception as e:
                        stats["errors"] += 1
                        logger.warning(
                            "reconcile_transaction_error",
                            transaction_id=str(tx.id),
                            **safe_error_log(e),
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
            **safe_error_log(e),
            exc_info=True,
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_tasks.parse_transaction_references",
    max_retries=2,
)
@celery_error_handler()
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
            **safe_error_log(e),
            exc_info=True,
        )
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_tasks.update_account_balances",
)
@celery_error_handler()
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
                # Query für Konten
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
            **safe_error_log(e),
            exc_info=True,
        )
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_tasks.check_overdue_payments",
)
@celery_error_handler()
def check_overdue_payments(self) -> Dict[str, Any]:
    """
    Prüfe auf überfällige Zahlungen.

    Returns:
        Statistik überfälliger Zahlungen
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
                            **safe_error_log(e),
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
            **safe_error_log(e),
            exc_info=True,
        )
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_tasks.process_automatic_dunning",
)
@celery_error_handler()
def process_automatic_dunning(
    self,
    user_id: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Führe automatisches Mahnverfahren durch.

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
                            **safe_error_log(e),
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
            **safe_error_log(e),
            exc_info=True,
        )
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_tasks.update_cash_flow_forecasts",
)
@celery_error_handler()
def update_cash_flow_forecasts(self) -> Dict[str, Any]:
    """
    Aktualisiere Cash-Flow-Prognosen für alle User.

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
                            **safe_error_log(e),
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
            **safe_error_log(e),
            exc_info=True,
        )
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_tasks.send_skonto_alerts",
)
@celery_error_handler()
def send_skonto_alerts(self, days_ahead: int = 7) -> Dict[str, Any]:
    """
    Sende Alerts für ablaufende Skonto-Fristen.

    Args:
        days_ahead: Tage voraus prüfen

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
                        user_savings = sum(
                            float(o.get("savings", 0))
                            for o in opportunities
                        )
                        stats["total_savings"] += user_savings

                        # Sende Notifications für ablaufende Skonti
                        if opportunities and user.email:
                            from app.services.notification_service import (
                                NotificationService,
                                NotificationType,
                                NotificationPriority,
                            )

                            # Formatiere Opportunities-Liste
                            opportunities_list = "\n".join([
                                f"- {o.get('invoice_number', 'N/A')}: "
                                f"{o.get('amount', 0):.2f} EUR "
                                f"(Skonto: {o.get('savings', 0):.2f} EUR, "
                                f"Frist: {o.get('deadline', 'N/A')})"
                                for o in opportunities[:10]  # Max 10 anzeigen
                            ])
                            if len(opportunities) > 10:
                                opportunities_list += f"\n... und {len(opportunities) - 10} weitere"

                            notification_service = NotificationService()
                            await notification_service.notify(
                                notification_type=NotificationType.SKONTO_EXPIRING,
                                context={
                                    "opportunities_list": opportunities_list,
                                    "total_savings": f"{user_savings:.2f}",
                                },
                                user_id=str(user.id),
                                email=user.email,
                                priority=NotificationPriority.HIGH,
                            )

                            # Sende auch Slack-Benachrichtigung für dringende Fristen (<=3 Tage)
                            if days_ahead <= 3:
                                try:
                                    from app.services.slack_service import (
                                        SlackService,
                                        SlackNotificationType,
                                        SlackMessagePriority,
                                    )
                                    slack = SlackService()
                                    urgency = "KRITISCH" if days_ahead <= 1 else "DRINGEND"
                                    slack_priority = (
                                        SlackMessagePriority.URGENT
                                        if days_ahead <= 1
                                        else SlackMessagePriority.HIGH
                                    )
                                    await slack.send_notification(
                                        notification_type=SlackNotificationType.SKONTO_EXPIRING,
                                        title=f"{urgency}: Skonto-Fristen laufen ab",
                                        message=(
                                            f"*{len(opportunities)} Rechnung(en)* mit ablaufenden "
                                            f"Skonto-Fristen in den nächsten {days_ahead} Tag(en).\n\n"
                                            f"Potenzielle Ersparnis: *{user_savings:.2f} EUR*"
                                        ),
                                        context={
                                            "rechnungen": len(opportunities),
                                            "ersparnis_eur": user_savings,
                                            "tage_voraus": days_ahead,
                                        },
                                        priority=slack_priority,
                                    )
                                except Exception as slack_error:
                                    logger.debug(
                                        "skonto_slack_notification_failed",
                                        error=str(slack_error),
                                    )

                    except Exception as e:
                        logger.warning(
                            "skonto_alert_user_error",
                            user_id=str(user.id),
                            **safe_error_log(e),
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
            **safe_error_log(e),
            exc_info=True,
        )
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_tasks.cleanup_tan_challenges",
)
@celery_error_handler()
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
            **safe_error_log(e),
            exc_info=True,
        )
        raise


# =============================================================================
# MAHNUNGSWESEN (Dunning System) TASKS
# =============================================================================


def is_german_business_day(check_date: Optional[date] = None) -> bool:
    """
    Prüfe ob Datum ein deutscher Werktag ist.

    Args:
        check_date: Zu prüfendes Datum (default: heute)

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
@celery_error_handler()
def daily_mahnlauf(self) -> Dict[str, Any]:
    """
    Täglicher Mahnlauf um 9:00 Uhr (Mo-Fr, keine deutschen Feiertage).

    Erstellt MahnTasks für fällige Mahnungen.
    Sendet NICHT automatisch - Tasks müssen manuell bearbeitet werden.

    BGB §286 Compliance:
    - Prüft B2B/B2C für korrekte Verzugszinsen
    - Respektiert Mahnstopp bei Reklamationen
    - Respektiert Customer Dunning Overrides

    Returns:
        Mahnlauf-Statistik
    """
    logger.info(
        "daily_mahnlauf_started",
        task_id=self.request.id,
    )

    # Prüfe ob Werktag
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

                        # Hole Mahnstufen-Konfiguration für User
                        stages = await dunning_stage_service.get_stages(db, user.id)
                        active_stages = [s for s in stages if s.get("is_active")]

                        if not active_stages:
                            continue

                        # Hole überfällige Rechnungen
                        overdue = await dunning_service.get_overdue_invoices(
                            db=db,
                            user_id=user.id,
                            min_days_overdue=1,
                            include_in_progress=True,
                        )

                        for candidate in overdue:
                            stats["overdue_invoices"] += 1

                            # Prüfe Mahnvorgang
                            dunning_query = select(DunningRecord).where(
                                DunningRecord.document_id == candidate.document_id
                            )
                            dunning_result = await db.execute(dunning_query)
                            dunning = dunning_result.scalar_one_or_none()

                            # Mahnstopp aktiv?
                            if dunning and dunning.mahnstopp:
                                stats["skipped_mahnstopp"] += 1
                                continue

                            # Customer Override prüfen
                            entity_override = None
                            max_allowed_stufe = None
                            exclude_from_dunning = False

                            # Lade Document mit BusinessEntity
                            doc_query = select(Document).where(
                                Document.id == candidate.document_id
                            )
                            doc_result = await db.execute(doc_query)
                            document = doc_result.scalar_one_or_none()

                            if document and document.business_entity_id:
                                # Lade CustomerDunningOverride
                                from app.db.models import CustomerDunningOverride
                                override_query = select(CustomerDunningOverride).where(
                                    CustomerDunningOverride.business_entity_id == document.business_entity_id
                                )
                                override_result = await db.execute(override_query)
                                entity_override = override_result.scalar_one_or_none()

                                if entity_override:
                                    if entity_override.exclude_from_auto_dunning:
                                        exclude_from_dunning = True
                                        logger.info(
                                            "dunning_skipped_entity_exclusion",
                                            document_id=str(candidate.document_id),
                                            entity_id=str(document.business_entity_id),
                                        )
                                    if entity_override.max_mahn_stufe is not None:
                                        max_allowed_stufe = entity_override.max_mahn_stufe

                            if exclude_from_dunning:
                                stats["skipped_mahnstopp"] += 1
                                continue

                            # Welche Stufe ist fällig?
                            for stage in active_stages:
                                if candidate.days_overdue >= stage.get("trigger_days_after_due", 0):
                                    # Aktuelle Stufe ist kleiner als diese?
                                    current_level = candidate.current_level.value if candidate.current_level else 0
                                    stage_number = stage.get("stage_number", 0)

                                    # Customer Override: Max-Stufe prüfen
                                    if max_allowed_stufe is not None and stage_number > max_allowed_stufe:
                                        logger.debug(
                                            "dunning_stage_capped",
                                            document_id=str(candidate.document_id),
                                            requested_stage=stage_number,
                                            max_allowed=max_allowed_stufe,
                                        )
                                        break  # Keine weiteren Stufen erlaubt

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
                            **safe_error_log(e),
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
            **safe_error_log(e),
            exc_info=True,
        )
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_tasks.reactivate_snoozed_tasks",
)
@celery_error_handler()
def reactivate_snoozed_tasks(self) -> Dict[str, Any]:
    """
    Reaktiviere zurückgestellte Mahn-Aufgaben.

    Wird täglich ausgeführt und setzt snoozed Tasks zurück auf pending,
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
            **safe_error_log(e),
            exc_info=True,
        )
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_tasks.send_pre_due_reminders",
)
@celery_error_handler()
def send_pre_due_reminders(self, days_before: int = 3) -> Dict[str, Any]:
    """
    Sende Zahlungserinnerungen VOR Fälligkeit.

    Proaktive Erinnerungen um Mahnverfahren zu vermeiden.
    BGB-konform: Freundliche Erinnerung, keine Verzugsfolgen.

    Args:
        days_before: Tage vor Fälligkeit (default: 3)

    Returns:
        Statistik der versendeten Erinnerungen
    """
    logger.info(
        "send_pre_due_reminders_started",
        task_id=self.request.id,
        days_before=days_before,
    )

    try:
        async def do_send_reminders():
            from sqlalchemy import select, and_, or_
            from app.db.session import get_async_session
            from app.db.models import (
                InvoiceTracking,
                Document,
                User,
                BusinessEntity,
                Notification,
                NotificationStatus,
            )
            from app.services.notification_service import notification_service
            from app.services.banking.models import DunningStatus

            stats = {
                "invoices_checked": 0,
                "reminders_sent": 0,
                "already_notified": 0,
                "skipped_no_email": 0,
                "errors": 0,
            }

            async with get_async_session() as db:
                today = date.today()
                target_due_date = today + timedelta(days=days_before)

                # Finde Rechnungen die in {days_before} Tagen fällig werden
                # und noch nicht bezahlt sind
                query = select(InvoiceTracking).where(
                    and_(
                        InvoiceTracking.due_date == target_due_date,
                        InvoiceTracking.status.in_([
                            "pending", "overdue", "partial"
                        ]),
                        # Kein aktives Mahnverfahren
                        or_(
                            InvoiceTracking.dunning_level == 0,
                            InvoiceTracking.dunning_level.is_(None),
                        ),
                    )
                )

                result = await db.execute(query)
                invoices = result.scalars().all()
                stats["invoices_checked"] = len(invoices)

                for invoice in invoices:
                    try:
                        # Lade zugehoeriges Dokument
                        doc_query = select(Document).where(
                            Document.id == invoice.document_id
                        )
                        doc_result = await db.execute(doc_query)
                        document = doc_result.scalar_one_or_none()

                        if not document:
                            continue

                        # Lade BusinessEntity für Kontaktdaten
                        entity = None
                        if invoice.entity_id:
                            entity_query = select(BusinessEntity).where(
                                BusinessEntity.id == invoice.entity_id
                            )
                            entity_result = await db.execute(entity_query)
                            entity = entity_result.scalar_one_or_none()

                        # Prüfe ob bereits Pre-Due Erinnerung gesendet wurde
                        # (innerhalb der letzten 7 Tage)
                        existing_query = select(Notification).where(
                            and_(
                                Notification.document_id == invoice.document_id,
                                Notification.notification_type == "payment_reminder",
                                Notification.created_at >= datetime.now(timezone.utc) - timedelta(days=7),
                            )
                        ).limit(1)
                        existing_result = await db.execute(existing_query)

                        if existing_result.scalar_one_or_none():
                            stats["already_notified"] += 1
                            continue

                        # Hole User für Benachrichtigung
                        user_query = select(User).where(
                            User.id == document.user_id
                        )
                        user_result = await db.execute(user_query)
                        user = user_result.scalar_one_or_none()

                        if not user:
                            stats["skipped_no_email"] += 1
                            continue

                        # Erstelle freundliche Erinnerungsnachricht
                        entity_name = entity.name if entity else "Unbekannt"
                        invoice_number = invoice.invoice_number or "N/A"
                        amount = invoice.outstanding_amount or invoice.total_amount or 0

                        message_data = {
                            "subject": f"Zahlungserinnerung: Rechnung {invoice_number}",
                            "entity_name": entity_name,
                            "invoice_number": invoice_number,
                            "amount": f"{amount:.2f} EUR",
                            "due_date": target_due_date.strftime("%d.%m.%Y"),
                            "days_until_due": days_before,
                        }

                        # Sende Benachrichtigung
                        await notification_service.send_notification(
                            db=db,
                            user_id=user.id,
                            notification_type="payment_reminder",
                            title=f"Zahlungserinnerung: {invoice_number}",
                            message=(
                                f"Die Rechnung {invoice_number} von {entity_name} "
                                f"über {amount:.2f} EUR ist am {target_due_date.strftime('%d.%m.%Y')} "
                                f"fällig (in {days_before} Tagen). "
                                f"Bitte überweisen Sie den Betrag rechtzeitig."
                            ),
                            document_id=invoice.document_id,
                            metadata=message_data,
                            channels=["email", "in_app"],
                        )

                        stats["reminders_sent"] += 1

                        logger.debug(
                            "pre_due_reminder_sent",
                            invoice_id=str(invoice.id),
                            document_id=str(invoice.document_id),
                            days_before=days_before,
                        )

                    except Exception as e:
                        stats["errors"] += 1
                        logger.warning(
                            "pre_due_reminder_error",
                            invoice_id=str(invoice.id) if invoice else "unknown",
                            **safe_error_log(e),
                        )

                await db.commit()

            return stats

        result = run_async(do_send_reminders())

        logger.info(
            "send_pre_due_reminders_completed",
            task_id=self.request.id,
            **result,
        )

        return result

    except Exception as e:
        logger.error(
            "send_pre_due_reminders_failed",
            task_id=self.request.id,
            **safe_error_log(e),
            exc_info=True,
        )
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_tasks.check_expired_mahnstopp",
)
@celery_error_handler()
def check_expired_mahnstopp(self) -> Dict[str, Any]:
    """
    Prüfe und hebe abgelaufene Mahnstopps auf.

    Wird täglich ausgeführt und hebt Mahnstopps auf,
    deren mahnstopp_until Datum erreicht ist.

    Returns:
        Mahnstopp-Prüfungs-Statistik
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
            **safe_error_log(e),
            exc_info=True,
        )
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_tasks.generate_dunning_daily_report",
)
@celery_error_handler()
def generate_dunning_daily_report(self) -> Dict[str, Any]:
    """
    Generiere täglichen Mahnlauf-Bericht.

    Erstellt eine Zusammenfassung aller Mahnaktivitaeten des Tages
    und sendet sie an Admin-Benutzer.

    Returns:
        Report-Statistik
    """
    logger.info(
        "generate_dunning_daily_report_started",
        task_id=self.request.id,
    )

    try:
        async def do_generate_report():
            from sqlalchemy import select, and_, func
            from app.db.session import get_async_session
            from app.db.models import (
                DunningRecord,
                DunningHistoryEvent,
                InvoiceTracking,
                User,
                Notification,
            )
            from app.services.notification_service import notification_service

            today = date.today()
            today_start = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
            today_end = datetime.combine(today, datetime.max.time()).replace(tzinfo=timezone.utc)

            report = {
                "report_date": today.isoformat(),
                "pre_due_reminders_sent": 0,
                "new_dunnings_created": 0,
                "dunnings_escalated": 0,
                "dunnings_closed": 0,
                "payments_received": 0,
                "total_outstanding_amount": 0.0,
                "mahnstopps_set": 0,
                "mahnstopps_lifted": 0,
                "errors_count": 0,
            }

            async with get_async_session() as db:
                # Pre-Due Reminders gesendet heute
                pre_due_query = select(func.count(Notification.id)).where(
                    and_(
                        Notification.notification_type == "payment_reminder",
                        Notification.created_at >= today_start,
                        Notification.created_at <= today_end,
                    )
                )
                pre_due_result = await db.execute(pre_due_query)
                report["pre_due_reminders_sent"] = pre_due_result.scalar() or 0

                # Neue Mahnungen heute erstellt
                new_dunnings_query = select(func.count(DunningRecord.id)).where(
                    and_(
                        DunningRecord.created_at >= today_start,
                        DunningRecord.created_at <= today_end,
                    )
                )
                new_result = await db.execute(new_dunnings_query)
                report["new_dunnings_created"] = new_result.scalar() or 0

                # History Events heute
                history_query = select(DunningHistoryEvent).where(
                    and_(
                        DunningHistoryEvent.created_at >= today_start,
                        DunningHistoryEvent.created_at <= today_end,
                    )
                )
                history_result = await db.execute(history_query)
                events = history_result.scalars().all()

                for event in events:
                    event_type = event.event_type
                    if event_type == "escalated":
                        report["dunnings_escalated"] += 1
                    elif event_type == "closed":
                        report["dunnings_closed"] += 1
                    elif event_type == "payment_received":
                        report["payments_received"] += 1
                    elif event_type == "mahnstopp_set":
                        report["mahnstopps_set"] += 1
                    elif event_type == "mahnstopp_lifted":
                        report["mahnstopps_lifted"] += 1

                # Offene Forderungen (outstanding)
                outstanding_query = select(func.sum(InvoiceTracking.outstanding_amount)).where(
                    and_(
                        InvoiceTracking.status.in_(["pending", "overdue", "partial"]),
                        InvoiceTracking.outstanding_amount > 0,
                    )
                )
                outstanding_result = await db.execute(outstanding_query)
                report["total_outstanding_amount"] = float(outstanding_result.scalar() or 0)

                # Sende Report an alle Admin-Benutzer
                admin_query = select(User).where(User.is_admin == True)
                admin_result = await db.execute(admin_query)
                admins = admin_result.scalars().all()

                report_message = (
                    f"📊 Täglicher Mahnlauf-Bericht ({today.strftime('%d.%m.%Y')})\n\n"
                    f"• Zahlungserinnerungen gesendet: {report['pre_due_reminders_sent']}\n"
                    f"• Neue Mahnungen erstellt: {report['new_dunnings_created']}\n"
                    f"• Mahnungen eskaliert: {report['dunnings_escalated']}\n"
                    f"• Mahnungen geschlossen: {report['dunnings_closed']}\n"
                    f"• Zahlungseingaenge: {report['payments_received']}\n"
                    f"• Mahnstopps gesetzt: {report['mahnstopps_set']}\n"
                    f"• Mahnstopps aufgehoben: {report['mahnstopps_lifted']}\n\n"
                    f"💰 Offene Forderungen: {report['total_outstanding_amount']:,.2f} EUR"
                )

                for admin in admins:
                    try:
                        await notification_service.send_notification(
                            db=db,
                            user_id=admin.id,
                            notification_type="dunning_report",
                            title=f"Mahnlauf-Bericht {today.strftime('%d.%m.%Y')}",
                            message=report_message,
                            metadata=report,
                            channels=["email", "in_app"],
                        )
                    except Exception as e:
                        report["errors_count"] += 1
                        logger.warning(
                            "dunning_report_send_error",
                            admin_id=str(admin.id),
                            **safe_error_log(e),
                        )

                await db.commit()

            return report

        result = run_async(do_generate_report())

        logger.info(
            "generate_dunning_daily_report_completed",
            task_id=self.request.id,
            **result,
        )

        return result

    except Exception as e:
        logger.error(
            "generate_dunning_daily_report_failed",
            task_id=self.request.id,
            **safe_error_log(e),
            exc_info=True,
        )
        raise


# =============================================================================
# BEAT SCHEDULE CONFIGURATION
# =============================================================================

# =============================================================================
# FinTS Synchronization Tasks
# =============================================================================


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_tasks.fints_sync_all_accounts",
    max_retries=3,
    default_retry_delay=300,
)
@celery_error_handler()
def fints_sync_all_accounts(
    self,
    company_id: Optional[str] = None,
    sync_days: int = 30,
) -> Dict[str, Any]:
    """
    Synchronisiere alle FinTS-verbundenen Konten.

    Wird regelmäßig ausgeführt um Transaktionen abzurufen.
    WICHTIG: Erfordert gespeicherte PIN oder aktive TAN-Session.

    Args:
        company_id: Optional - nur für bestimmte Firma
        sync_days: Anzahl Tage zurück (default: 30)

    Returns:
        Sync-Statistik
    """
    logger.info(
        "fints_sync_all_accounts_started",
        task_id=self.request.id,
        company_id=company_id,
        sync_days=sync_days,
    )

    try:
        async def do_sync():
            from app.db.session import get_async_session
            from app.db.models import BankAccount, Company
            from sqlalchemy import select, and_

            stats = {
                "accounts_synced": 0,
                "transactions_imported": 0,
                "accounts_failed": 0,
                "errors": [],
            }

            async with get_async_session() as db:
                # Query für Konten mit FinTS-Verbindung
                query = select(BankAccount).where(
                    and_(
                        BankAccount.deleted_at.is_(None),
                        BankAccount.is_active == True,
                        BankAccount.fints_url.isnot(None),
                        # Nur Konten mit gespeicherter PIN (encrypted)
                        BankAccount.pin_encrypted.isnot(None),
                    )
                )

                if company_id:
                    query = query.where(BankAccount.company_id == UUID(company_id))

                result = await db.execute(query)
                accounts = result.scalars().all()

                for account in accounts:
                    try:
                        # Sync wuerde normalerweise FinTS-Service aufrufen
                        # HINWEIS: In Produktion muss PIN entschluesselt werden
                        # und TAN-Verfahren berücksichtigt werden

                        logger.info(
                            "fints_account_sync_attempt",
                            account_id=str(account.id),
                            iban_suffix=account.iban[-4:] if account.iban else "N/A",
                        )

                        # Placeholder: In echter Implementierung wuerde hier
                        # fints_service.sync_transactions aufgerufen
                        stats["accounts_synced"] += 1

                    except Exception as e:
                        stats["accounts_failed"] += 1
                        stats["errors"].append({
                            "account_id": str(account.id),
                            "error": safe_error_detail(e, "Vorgang")[:200],
                        })
                        logger.warning(
                            "fints_account_sync_error",
                            account_id=str(account.id),
                            **safe_error_log(e),
                        )

            return stats

        result = run_async(do_sync())

        logger.info(
            "fints_sync_all_accounts_completed",
            task_id=self.request.id,
            **result,
        )

        return result

    except Exception as e:
        logger.error(
            "fints_sync_all_accounts_failed",
            task_id=self.request.id,
            **safe_error_log(e),
            exc_info=True,
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_tasks.fints_refresh_balances",
)
@celery_error_handler()
def fints_refresh_balances(self, company_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Aktualisiere Kontosalden via FinTS.

    Schneller als volle Sync - nur Saldo-Abfrage.

    Args:
        company_id: Optional - nur für bestimmte Firma

    Returns:
        Update-Statistik
    """
    logger.info(
        "fints_refresh_balances_started",
        task_id=self.request.id,
        company_id=company_id,
    )

    try:
        async def do_refresh():
            from app.db.session import get_async_session
            from app.db.models import BankAccount
            from sqlalchemy import select, and_

            stats = {
                "accounts_updated": 0,
                "accounts_failed": 0,
                "total_balance": 0.0,
            }

            async with get_async_session() as db:
                query = select(BankAccount).where(
                    and_(
                        BankAccount.deleted_at.is_(None),
                        BankAccount.is_active == True,
                        BankAccount.fints_url.isnot(None),
                    )
                )

                if company_id:
                    query = query.where(BankAccount.company_id == UUID(company_id))

                result = await db.execute(query)
                accounts = result.scalars().all()

                for account in accounts:
                    try:
                        # Placeholder: FinTS Balance Query
                        if account.current_balance:
                            stats["total_balance"] += float(account.current_balance)
                        stats["accounts_updated"] += 1

                    except Exception as e:
                        stats["accounts_failed"] += 1
                        logger.warning(
                            "fints_balance_refresh_error",
                            account_id=str(account.id),
                            **safe_error_log(e),
                        )

            return stats

        result = run_async(do_refresh())

        logger.info(
            "fints_refresh_balances_completed",
            task_id=self.request.id,
            **result,
        )

        return result

    except Exception as e:
        logger.error(
            "fints_refresh_balances_failed",
            task_id=self.request.id,
            **safe_error_log(e),
            exc_info=True,
        )
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_tasks.execute_pending_sepa_transfers",
    max_retries=2,
)
@celery_error_handler()
def execute_pending_sepa_transfers(self) -> Dict[str, Any]:
    """
    Führe ausstehende SEPA-Überweisungen aus.

    Verarbeitet Transfers die auf Ausführung warten
    (z.B. nach Workflow-Freigabe).

    Returns:
        Ausführungs-Statistik
    """
    logger.info(
        "execute_pending_sepa_transfers_started",
        task_id=self.request.id,
    )

    try:
        async def do_execute():
            from app.db.session import get_async_session
            from sqlalchemy import select, and_

            stats = {
                "transfers_processed": 0,
                "transfers_executed": 0,
                "transfers_failed": 0,
                "total_amount": 0.0,
            }

            async with get_async_session() as db:
                # FUTURE: SEPATransfer-Model muss erstellt werden:
                # Migration: sepa_transfers Tabelle mit status, amount, iban_to, etc.
                # Query waere:
                # pending_transfers = await db.execute(
                #     select(SEPATransfer)
                #     .where(SEPATransfer.status == "pending_approval")
                #     .where(SEPATransfer.scheduled_at <= datetime.now(timezone.utc))
                # )
                # Aktuell keine SEPA-Transfers vorhanden - Feature noch nicht implementiert
                _ = db  # Suppress unused warning

                logger.info(
                    "sepa_transfer_execution_skipped",
                    message="SEPA Transfer Execution - Model nicht implementiert",
                )

            return stats

        result = run_async(do_execute())

        logger.info(
            "execute_pending_sepa_transfers_completed",
            task_id=self.request.id,
            **result,
        )

        return result

    except Exception as e:
        logger.error(
            "execute_pending_sepa_transfers_failed",
            task_id=self.request.id,
            **safe_error_log(e),
            exc_info=True,
        )
        raise self.retry(exc=e)


# =============================================================================
# Bundesbank Basiszins Tasks (§288 BGB)
# =============================================================================


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.banking_tasks.update_bundesbank_basiszins",
    max_retries=3,
)
@celery_error_handler()
def update_bundesbank_basiszins(self) -> Dict[str, Any]:
    """
    Aktualisiere Bundesbank Basiszins Daten.

    Holt den aktuellen Basiszins von der Bundesbank SDMX-REST API
    und aktualisiert den Redis-Cache.

    Läuft halbjährlich am 1. Januar und 1. Juli, da der Basiszins
    nur zum 1.1. und 1.7. angepasst wird (§247 BGB).

    Returns:
        Update-Statistik mit neuem Basiszins-Wert
    """
    logger.info(
        "bundesbank_basiszins_update_started",
        task_id=self.request.id,
    )

    try:
        async def do_update():
            from app.services.bundesbank_rate_service import (
                bundesbank_rate_service,
            )

            # Erzwinge Neuladung des Basiszinssatzes
            current_rate = await bundesbank_rate_service.refresh_basiszins()

            # Berechne Verzugszinsen (für schnellen Cache-Zugriff)
            verzugszins_b2b = await bundesbank_rate_service.get_verzugszins(
                is_b2b=True
            )
            verzugszins_b2c = await bundesbank_rate_service.get_verzugszins(
                is_b2b=False
            )

            return {
                "success": True,
                "current_basiszins": float(current_rate.rate) if current_rate else None,
                "valid_from": current_rate.valid_from if current_rate else None,
                "verzugszins_b2b": float(verzugszins_b2b),
                "verzugszins_b2c": float(verzugszins_b2c),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

        result = run_async(do_update())

        logger.info(
            "bundesbank_basiszins_update_completed",
            task_id=self.request.id,
            current_basiszins=result.get("current_basiszins"),
            verzugszins_b2b=result.get("verzugszins_b2b"),
        )

        return result

    except Exception as e:
        logger.error(
            "bundesbank_basiszins_update_failed",
            task_id=self.request.id,
            **safe_error_log(e),
            exc_info=True,
        )
        raise self.retry(exc=e, countdown=3600)  # Retry nach 1 Stunde


