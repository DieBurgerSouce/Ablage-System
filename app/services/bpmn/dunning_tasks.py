"""Dunning Workflow Task Implementations.

Service Tasks für den Mahnwesen-Workflow.
Diese Funktionen werden von der BPMN Engine aufgerufen.
"""

from typing import Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import structlog

from app.core.config import settings
from app.services.email_service import EmailService

logger = structlog.get_logger(__name__)

# Singleton EmailService instance
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Get or create EmailService singleton."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService(settings)
    return _email_service


async def send_payment_reminder(
    instance_id: str,
    variables: Dict[str, Any]
) -> Dict[str, Any]:
    """Sendet eine Zahlungserinnerung an den Kunden.

    Args:
        instance_id: BPMN Prozess-Instanz ID
        variables: Prozess-Variablen (invoice_id, customer_id, etc.)

    Returns:
        Aktualisierte Variablen mit Erinnerungs-Info
    """
    from app.db.session import async_session_maker
    from app.db.bpmn_models.bpmn import ProcessHistory

    invoice_id = variables.get("invoice_id")
    customer_id = variables.get("customer_id")
    amount = variables.get("amount", 0)
    due_date = variables.get("due_date")

    logger.info(
        "sending_payment_reminder",
        instance_id=instance_id,
        invoice_id=invoice_id,
        amount=amount
    )

    async with async_session_maker() as db:
        from sqlalchemy import select
        from app.db.models import InvoiceTracking, BusinessEntity, Company

        # Audit-Eintrag
        history = ProcessHistory(
            instance_id=UUID(instance_id),
            event_type="PAYMENT_REMINDER_SENT",
            message=f"Zahlungserinnerung versendet (Betrag: {amount:.2f} EUR)",
            actor_type="system",
            company_id=variables.get("company_id"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(history)

        # Email-Versand über EmailService
        email_sent = False
        email_error = None

        if invoice_id and customer_id:
            try:
                # Lade Entity, Invoice und Company für Email
                entity_result = await db.execute(
                    select(BusinessEntity).where(BusinessEntity.id == UUID(customer_id))
                )
                entity = entity_result.scalar_one_or_none()

                invoice_result = await db.execute(
                    select(InvoiceTracking).where(InvoiceTracking.id == UUID(invoice_id))
                )
                invoice = invoice_result.scalar_one_or_none()

                company_id_val = variables.get("company_id")
                company = None
                if company_id_val:
                    company_result = await db.execute(
                        select(Company).where(Company.id == UUID(company_id_val))
                    )
                    company = company_result.scalar_one_or_none()

                if entity and invoice and company and entity.email:
                    email_service = get_email_service()
                    result = await email_service.send_payment_reminder(
                        entity=entity,
                        invoice=invoice,
                        company=company
                    )
                    email_sent = result.success
                    if not result.success:
                        email_error = result.error_message
                        logger.warning(
                            "payment_reminder_email_failed",
                            invoice_id=invoice_id,
                            error=email_error
                        )
                else:
                    logger.warning(
                        "payment_reminder_email_skipped",
                        invoice_id=invoice_id,
                        reason="Missing entity, invoice, company, or email address"
                    )
            except Exception as e:
                email_error = str(e)
                logger.exception(
                    "payment_reminder_email_exception",
                    invoice_id=invoice_id,
                    error=email_error
                )

        await db.commit()

    return {
        "reminder_sent": True,
        "reminder_sent_at": datetime.now(timezone.utc).isoformat(),
        "reminder_type": "payment_reminder",
        "dunning_level": 0,
        "email_sent": email_sent,
        "email_error": email_error,
    }


async def send_first_dunning(
    instance_id: str,
    variables: Dict[str, Any]
) -> Dict[str, Any]:
    """Sendet die erste Mahnung (Mahnstufe 1).

    Args:
        instance_id: BPMN Prozess-Instanz ID
        variables: Prozess-Variablen

    Returns:
        Aktualisierte Variablen mit Mahnungs-Info
    """
    from app.db.session import async_session_maker
    from app.db.bpmn_models.bpmn import ProcessHistory

    invoice_id = variables.get("invoice_id")
    amount = variables.get("amount", 0)
    dunning_fee = 5.00  # Standard-Mahngebühr

    logger.info(
        "sending_first_dunning",
        instance_id=instance_id,
        invoice_id=invoice_id,
        dunning_level=1
    )

    async with async_session_maker() as db:
        from sqlalchemy import select
        from app.db.models import InvoiceTracking, BusinessEntity, Company

        history = ProcessHistory(
            instance_id=UUID(instance_id),
            event_type="FIRST_DUNNING_SENT",
            message=f"1. Mahnung versendet (Betrag: {amount:.2f} EUR, Mahngebühr: {dunning_fee:.2f} EUR)",
            actor_type="system",
            company_id=variables.get("company_id"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(history)

        # Email-Versand und Invoice-Update
        email_sent = False
        email_error = None
        customer_id = variables.get("customer_id")

        if invoice_id:
            try:
                # Lade Invoice und update Dunning-Level
                invoice_result = await db.execute(
                    select(InvoiceTracking).where(InvoiceTracking.id == UUID(invoice_id))
                )
                invoice = invoice_result.scalar_one_or_none()

                if invoice:
                    invoice.dunning_level = 1
                    invoice.last_dunning_at = datetime.now(timezone.utc)

                # Lade Entity für Email
                entity = None
                if customer_id:
                    entity_result = await db.execute(
                        select(BusinessEntity).where(BusinessEntity.id == UUID(customer_id))
                    )
                    entity = entity_result.scalar_one_or_none()

                # Lade Company
                company_id_val = variables.get("company_id")
                company = None
                if company_id_val:
                    company_result = await db.execute(
                        select(Company).where(Company.id == UUID(company_id_val))
                    )
                    company = company_result.scalar_one_or_none()

                # Sende Email
                if entity and invoice and company and entity.email:
                    email_service = get_email_service()
                    result = await email_service.send_dunning_letter(
                        entity=entity,
                        invoice=invoice,
                        company=company,
                        dunning_level=1
                    )
                    email_sent = result.success
                    if not result.success:
                        email_error = result.error_message
                        logger.warning(
                            "first_dunning_email_failed",
                            invoice_id=invoice_id,
                            error=email_error
                        )
                else:
                    logger.warning(
                        "first_dunning_email_skipped",
                        invoice_id=invoice_id,
                        reason="Missing entity, invoice, company, or email address"
                    )
            except Exception as e:
                email_error = str(e)
                logger.exception(
                    "first_dunning_email_exception",
                    invoice_id=invoice_id,
                    error=email_error
                )

        await db.commit()

    return {
        "dunning_sent": True,
        "dunning_sent_at": datetime.now(timezone.utc).isoformat(),
        "dunning_level": 1,
        "dunning_fee": dunning_fee,
        "total_outstanding": amount + dunning_fee,
        "email_sent": email_sent,
        "email_error": email_error,
    }


async def send_second_dunning(
    instance_id: str,
    variables: Dict[str, Any]
) -> Dict[str, Any]:
    """Sendet die zweite Mahnung (Mahnstufe 2).

    Args:
        instance_id: BPMN Prozess-Instanz ID
        variables: Prozess-Variablen

    Returns:
        Aktualisierte Variablen mit Mahnungs-Info
    """
    from app.db.session import async_session_maker
    from app.db.bpmn_models.bpmn import ProcessHistory

    invoice_id = variables.get("invoice_id")
    amount = variables.get("amount", 0)
    previous_fee = variables.get("dunning_fee", 5.00)
    dunning_fee = 10.00  # Erhöhte Mahngebühr

    logger.info(
        "sending_second_dunning",
        instance_id=instance_id,
        invoice_id=invoice_id,
        dunning_level=2
    )

    async with async_session_maker() as db:
        from sqlalchemy import select
        from app.db.models import InvoiceTracking, BusinessEntity, Company

        history = ProcessHistory(
            instance_id=UUID(instance_id),
            event_type="SECOND_DUNNING_SENT",
            message=f"2. Mahnung versendet (Betrag: {amount:.2f} EUR, Mahngebühr: {dunning_fee:.2f} EUR)",
            actor_type="system",
            company_id=variables.get("company_id"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(history)

        # Email-Versand und Invoice-Update
        email_sent = False
        email_error = None
        customer_id = variables.get("customer_id")

        if invoice_id:
            try:
                # Lade Invoice und update Dunning-Level
                invoice_result = await db.execute(
                    select(InvoiceTracking).where(InvoiceTracking.id == UUID(invoice_id))
                )
                invoice = invoice_result.scalar_one_or_none()

                if invoice:
                    invoice.dunning_level = 2
                    invoice.last_dunning_at = datetime.now(timezone.utc)

                # Lade Entity für Email
                entity = None
                if customer_id:
                    entity_result = await db.execute(
                        select(BusinessEntity).where(BusinessEntity.id == UUID(customer_id))
                    )
                    entity = entity_result.scalar_one_or_none()

                # Lade Company
                company_id_val = variables.get("company_id")
                company = None
                if company_id_val:
                    company_result = await db.execute(
                        select(Company).where(Company.id == UUID(company_id_val))
                    )
                    company = company_result.scalar_one_or_none()

                # Sende Email
                if entity and invoice and company and entity.email:
                    email_service = get_email_service()
                    result = await email_service.send_dunning_letter(
                        entity=entity,
                        invoice=invoice,
                        company=company,
                        dunning_level=2
                    )
                    email_sent = result.success
                    if not result.success:
                        email_error = result.error_message
                        logger.warning(
                            "second_dunning_email_failed",
                            invoice_id=invoice_id,
                            error=email_error
                        )
                else:
                    logger.warning(
                        "second_dunning_email_skipped",
                        invoice_id=invoice_id,
                        reason="Missing entity, invoice, company, or email address"
                    )
            except Exception as e:
                email_error = str(e)
                logger.exception(
                    "second_dunning_email_exception",
                    invoice_id=invoice_id,
                    error=email_error
                )

        await db.commit()

    return {
        "dunning_sent": True,
        "dunning_sent_at": datetime.now(timezone.utc).isoformat(),
        "dunning_level": 2,
        "dunning_fee": dunning_fee,
        "total_outstanding": amount + dunning_fee,
        "email_sent": email_sent,
        "email_error": email_error,
    }


async def send_final_dunning(
    instance_id: str,
    variables: Dict[str, Any]
) -> Dict[str, Any]:
    """Sendet die letzte Mahnung vor Inkasso (Mahnstufe 3).

    Args:
        instance_id: BPMN Prozess-Instanz ID
        variables: Prozess-Variablen

    Returns:
        Aktualisierte Variablen mit Mahnungs-Info
    """
    from app.db.session import async_session_maker
    from app.db.bpmn_models.bpmn import ProcessHistory

    invoice_id = variables.get("invoice_id")
    amount = variables.get("amount", 0)
    dunning_fee = 15.00  # Letzte Mahngebühr

    logger.info(
        "sending_final_dunning",
        instance_id=instance_id,
        invoice_id=invoice_id,
        dunning_level=3
    )

    async with async_session_maker() as db:
        from sqlalchemy import select
        from app.db.models import InvoiceTracking, BusinessEntity, Company

        history = ProcessHistory(
            instance_id=UUID(instance_id),
            event_type="FINAL_DUNNING_SENT",
            message=f"Letzte Mahnung vor Inkasso versendet (Betrag: {amount:.2f} EUR)",
            actor_type="system",
            company_id=variables.get("company_id"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(history)

        # Email-Versand und Invoice-Update
        email_sent = False
        email_error = None
        customer_id = variables.get("customer_id")

        if invoice_id:
            try:
                # Lade Invoice und update Dunning-Level
                invoice_result = await db.execute(
                    select(InvoiceTracking).where(InvoiceTracking.id == UUID(invoice_id))
                )
                invoice = invoice_result.scalar_one_or_none()

                if invoice:
                    invoice.dunning_level = 3
                    invoice.last_dunning_at = datetime.now(timezone.utc)

                # Lade Entity für Email
                entity = None
                if customer_id:
                    entity_result = await db.execute(
                        select(BusinessEntity).where(BusinessEntity.id == UUID(customer_id))
                    )
                    entity = entity_result.scalar_one_or_none()

                # Lade Company
                company_id_val = variables.get("company_id")
                company = None
                if company_id_val:
                    company_result = await db.execute(
                        select(Company).where(Company.id == UUID(company_id_val))
                    )
                    company = company_result.scalar_one_or_none()

                # Sende Email (Letzte Mahnung vor Inkasso)
                if entity and invoice and company and entity.email:
                    email_service = get_email_service()
                    result = await email_service.send_dunning_letter(
                        entity=entity,
                        invoice=invoice,
                        company=company,
                        dunning_level=3  # Final dunning uses "final" template
                    )
                    email_sent = result.success
                    if not result.success:
                        email_error = result.error_message
                        logger.warning(
                            "final_dunning_email_failed",
                            invoice_id=invoice_id,
                            error=email_error
                        )
                else:
                    logger.warning(
                        "final_dunning_email_skipped",
                        invoice_id=invoice_id,
                        reason="Missing entity, invoice, company, or email address"
                    )
            except Exception as e:
                email_error = str(e)
                logger.exception(
                    "final_dunning_email_exception",
                    invoice_id=invoice_id,
                    error=email_error
                )

        await db.commit()

    return {
        "dunning_sent": True,
        "dunning_sent_at": datetime.now(timezone.utc).isoformat(),
        "dunning_level": 3,
        "dunning_fee": dunning_fee,
        "total_outstanding": amount + dunning_fee,
        "inkasso_warning": True,
        "email_sent": email_sent,
        "email_error": email_error,
    }


async def transfer_to_collection(
    instance_id: str,
    variables: Dict[str, Any]
) -> Dict[str, Any]:
    """Übergibt die Forderung an ein Inkasso-Unternehmen.

    Verwendet den InkassoService für die Integration mit Inkasso-Partnern.

    Args:
        instance_id: BPMN Prozess-Instanz ID
        variables: Prozess-Variablen

    Returns:
        Aktualisierte Variablen mit Inkasso-Info
    """
    from app.db.session import async_session_maker
    from app.db.bpmn_models.bpmn import ProcessHistory
    from app.services.inkasso_service import InkassoService

    invoice_id = variables.get("invoice_id")
    entity_id = variables.get("customer_id") or variables.get("entity_id")
    company_id_str = variables.get("company_id")
    amount = Decimal(str(variables.get("total_outstanding", variables.get("amount", 0))))
    dunning_level = variables.get("dunning_level", 3)

    logger.warning(
        "transferring_to_collection",
        instance_id=instance_id,
        invoice_id=invoice_id,
        amount=float(amount)
    )

    collection_reference = ""
    transfer_success = False
    error_message = None
    provider = "unknown"
    estimated_probability = None

    async with async_session_maker() as db:
        try:
            if invoice_id and entity_id and company_id_str:
                # Use InkassoService for real transfer
                inkasso_service = InkassoService(db)

                result = await inkasso_service.transfer_to_collection(
                    invoice_id=UUID(invoice_id),
                    entity_id=UUID(entity_id),
                    company_id=UUID(company_id_str),
                    amount=amount,
                    dunning_level=dunning_level,
                    reason=f"Zahlungsverzug nach Mahnstufe {dunning_level}",
                    additional_data={
                        "instance_id": instance_id,
                        "original_invoice_amount": variables.get("amount"),
                        "dunning_fees_total": float(amount) - float(variables.get("amount", 0)),
                    }
                )

                transfer_success = result.success
                collection_reference = result.collection_reference
                provider = result.provider
                estimated_probability = result.estimated_collection_probability
                if not result.success:
                    error_message = result.error_message
            else:
                # Fallback: Generate reference without API call
                error_message = "Fehlende IDs für Inkasso-Übertragung"
                collection_reference = f"INK-{datetime.now().strftime('%Y%m%d')}-{str(invoice_id)[:8] if invoice_id else 'UNKNOWN'}"
                logger.warning(
                    "inkasso_transfer_missing_ids",
                    instance_id=instance_id,
                    has_invoice_id=bool(invoice_id),
                    has_entity_id=bool(entity_id)
                )

        except Exception as e:
            error_message = str(e)
            collection_reference = f"INK-{datetime.now().strftime('%Y%m%d')}-{str(invoice_id)[:8] if invoice_id else 'ERROR'}"
            logger.exception(
                "inkasso_transfer_exception",
                instance_id=instance_id,
                error_type=type(e).__name__
            )

        # Audit entry
        history = ProcessHistory(
            instance_id=UUID(instance_id),
            event_type="TRANSFERRED_TO_COLLECTION" if transfer_success else "COLLECTION_TRANSFER_FAILED",
            message=f"{'Forderung an Inkasso übergeben' if transfer_success else 'Inkasso-Übertragung fehlgeschlagen'} - Ref: {collection_reference} ({provider})" + (f" - {error_message}" if error_message else ""),
            actor_type="system",
            company_id=company_id_str,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(history)
        await db.commit()

    return {
        "transferred_to_collection": transfer_success,
        "transferred_at": datetime.now(timezone.utc).isoformat(),
        "collection_reference": collection_reference,
        "collection_amount": float(amount),
        "collection_provider": provider,
        "estimated_collection_probability": estimated_probability,
        "dunning_level": 4,
        "transfer_error": error_message,
    }


async def check_payment_received(
    instance_id: str,
    variables: Dict[str, Any]
) -> Dict[str, Any]:
    """Prüft ob eine Zahlung eingegangen ist.

    Diese Task wird typischerweise als Timer-Task aufgerufen.
    Prüft BankTransaction-Tabelle auf passende Zahlungen.

    Args:
        instance_id: BPMN Prozess-Instanz ID
        variables: Prozess-Variablen

    Returns:
        Variablen mit Zahlungsstatus
    """
    from app.db.session import async_session_maker
    from app.db.models import BankTransaction, InvoiceTracking, BusinessEntity
    from sqlalchemy import select, and_, or_, cast
    from sqlalchemy.dialects.postgresql import JSONB

    invoice_id = variables.get("invoice_id")
    entity_id = variables.get("customer_id") or variables.get("entity_id")
    company_id_str = variables.get("company_id")
    expected_amount = Decimal(str(variables.get("total_outstanding", variables.get("amount", 0))))
    invoice_number = variables.get("invoice_number")

    logger.info(
        "checking_payment_received",
        instance_id=instance_id,
        invoice_id=invoice_id
    )

    payment_received = False
    payment_amount = Decimal("0.0")
    payment_date = None
    transaction_id = None
    match_method = None
    is_partial = False
    remaining_amount = expected_amount

    async with async_session_maker() as db:
        try:
            if not invoice_id or not company_id_str:
                logger.warning(
                    "payment_check_missing_ids",
                    instance_id=instance_id,
                    has_invoice_id=bool(invoice_id)
                )
                return {
                    "payment_received": False,
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                    "error": "Fehlende Invoice-ID oder Company-ID",
                }

            company_id = UUID(company_id_str)

            # Get entity IBAN if available
            entity_iban = None
            if entity_id:
                entity = await db.get(BusinessEntity, UUID(entity_id))
                if entity:
                    entity_iban = entity.iban

            # Build search criteria for matching transactions
            # Look for transactions in the last 90 days that haven't been matched yet
            since_date = datetime.now(timezone.utc) - timedelta(days=90)

            # Amount tolerance: 0.5% (for rounding differences)
            amount_lower = expected_amount * Decimal("0.995")
            amount_upper = expected_amount * Decimal("1.005")

            # Build query to find matching transactions
            base_conditions = [
                BankTransaction.booking_date >= since_date,
                BankTransaction.amount > 0,  # Only incoming payments
                BankTransaction.reconciliation_status.in_(["unmatched", "suggested"]),
            ]

            # Strategy 1: Exact IBAN + Amount match (highest confidence)
            if entity_iban:
                iban_match_query = (
                    select(BankTransaction)
                    .where(
                        and_(
                            *base_conditions,
                            BankTransaction.counterparty_iban == entity_iban,
                            BankTransaction.amount >= amount_lower,
                            BankTransaction.amount <= amount_upper,
                        )
                    )
                    .order_by(BankTransaction.booking_date.desc())
                    .limit(1)
                )
                result = await db.execute(iban_match_query)
                matching_tx = result.scalar_one_or_none()

                if matching_tx:
                    payment_received = True
                    payment_amount = Decimal(str(matching_tx.amount))
                    payment_date = matching_tx.booking_date
                    transaction_id = str(matching_tx.id)
                    match_method = "iban_amount"
                    logger.info(
                        "payment_found_iban_match",
                        invoice_id=invoice_id,
                        transaction_id=transaction_id
                    )

            # Strategy 2: Invoice number in reference text
            if not payment_received and invoice_number:
                ref_match_query = (
                    select(BankTransaction)
                    .where(
                        and_(
                            *base_conditions,
                            or_(
                                BankTransaction.reference_text.ilike(f"%{invoice_number}%"),
                                cast(BankTransaction.parsed_invoice_numbers, JSONB).contains([invoice_number]),
                            ),
                            BankTransaction.amount >= amount_lower,
                            BankTransaction.amount <= amount_upper,
                        )
                    )
                    .order_by(BankTransaction.booking_date.desc())
                    .limit(1)
                )
                result = await db.execute(ref_match_query)
                matching_tx = result.scalar_one_or_none()

                if matching_tx:
                    payment_received = True
                    payment_amount = Decimal(str(matching_tx.amount))
                    payment_date = matching_tx.booking_date
                    transaction_id = str(matching_tx.id)
                    match_method = "invoice_reference"
                    logger.info(
                        "payment_found_reference_match",
                        invoice_id=invoice_id,
                        transaction_id=transaction_id
                    )

            # Strategy 3: Check for partial payments (amount less than expected)
            if not payment_received and entity_iban:
                partial_query = (
                    select(BankTransaction)
                    .where(
                        and_(
                            *base_conditions,
                            BankTransaction.counterparty_iban == entity_iban,
                            BankTransaction.amount > 0,
                            BankTransaction.amount < amount_lower,  # Less than expected
                        )
                    )
                    .order_by(BankTransaction.booking_date.desc())
                    .limit(1)
                )
                result = await db.execute(partial_query)
                partial_tx = result.scalar_one_or_none()

                if partial_tx:
                    payment_received = True  # Partial payment received
                    payment_amount = Decimal(str(partial_tx.amount))
                    payment_date = partial_tx.booking_date
                    transaction_id = str(partial_tx.id)
                    match_method = "partial_payment"
                    is_partial = True
                    remaining_amount = expected_amount - payment_amount
                    logger.info(
                        "partial_payment_found",
                        invoice_id=invoice_id,
                        transaction_id=transaction_id,
                        partial_amount=float(payment_amount),
                        remaining=float(remaining_amount)
                    )

            # If payment found, update records
            if payment_received and transaction_id:
                # Mark transaction as matched
                matching_tx_record = await db.get(BankTransaction, UUID(transaction_id))
                if matching_tx_record:
                    matching_tx_record.reconciliation_status = "matched"
                    matching_tx_record.matched_invoice_number = invoice_number
                    matching_tx_record.match_method = match_method
                    matching_tx_record.matched_at = datetime.now(timezone.utc)
                    matching_tx_record.match_confidence = 0.95 if match_method == "iban_amount" else 0.85

                # Update invoice tracking
                invoice = await db.get(InvoiceTracking, UUID(invoice_id))
                if invoice:
                    if is_partial:
                        invoice.is_partial_payment = True
                        invoice.paid_amount = float(
                            (Decimal(str(invoice.paid_amount or 0)) + payment_amount)
                        )
                        invoice.outstanding_amount = float(remaining_amount)
                        invoice.status = "partially_paid"
                    else:
                        invoice.status = "paid"
                        invoice.paid_at = payment_date
                        invoice.paid_amount = float(payment_amount)
                        invoice.outstanding_amount = 0.0

                await db.commit()

        except Exception as e:
            logger.exception(
                "payment_check_error",
                instance_id=instance_id,
                invoice_id=invoice_id,
                error_type=type(e).__name__
            )
            return {
                "payment_received": False,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "error": "Fehler bei Zahlungsprüfung",
            }

    if not payment_received:
        return {
            "payment_received": False,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "payment_received": True,
        "payment_amount": float(payment_amount),
        "payment_date": payment_date.isoformat() if payment_date else None,
        "transaction_id": transaction_id,
        "match_method": match_method,
        "is_partial_payment": is_partial,
        "remaining_amount": float(remaining_amount) if is_partial else 0.0,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


async def close_dunning_case(
    instance_id: str,
    variables: Dict[str, Any]
) -> Dict[str, Any]:
    """Schließt den Mahnfall ab (Zahlung eingegangen).

    Args:
        instance_id: BPMN Prozess-Instanz ID
        variables: Prozess-Variablen

    Returns:
        Aktualisierte Variablen
    """
    from app.db.session import async_session_maker
    from app.db.bpmn_models.bpmn import ProcessHistory

    invoice_id = variables.get("invoice_id")
    payment_amount = variables.get("payment_amount", 0)
    dunning_level = variables.get("dunning_level", 0)

    logger.info(
        "closing_dunning_case",
        instance_id=instance_id,
        invoice_id=invoice_id,
        dunning_level=dunning_level
    )

    async with async_session_maker() as db:
        history = ProcessHistory(
            instance_id=UUID(instance_id),
            event_type="DUNNING_CASE_CLOSED",
            message=f"Mahnfall abgeschlossen - Zahlung erhalten ({payment_amount:.2f} EUR)",
            actor_type="system",
            company_id=variables.get("company_id"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(history)

        # Invoice als bezahlt markieren
        # from app.services.invoice_service import mark_invoice_paid
        # await mark_invoice_paid(db, invoice_id)

        await db.commit()

    return {
        "case_closed": True,
        "closed_at": datetime.now(timezone.utc).isoformat(),
        "final_dunning_level": dunning_level,
        "resolution": "payment_received",
    }


def calculate_dunning_deadline(
    current_level: int,
    base_date: datetime | None = None
) -> datetime:
    """Berechnet die nächste Mahnfrist.

    Args:
        current_level: Aktuelle Mahnstufe (0-3)
        base_date: Ausgangsdatum (default: jetzt)

    Returns:
        Deadline für nächste Mahnung
    """
    if base_date is None:
        base_date = datetime.now(timezone.utc)

    # Fristen je Mahnstufe (in Tagen)
    deadlines = {
        0: 14,  # Zahlungserinnerung → 1. Mahnung
        1: 14,  # 1. Mahnung → 2. Mahnung
        2: 10,  # 2. Mahnung → Letzte Mahnung
        3: 7,   # Letzte Mahnung → Inkasso
    }

    days = deadlines.get(current_level, 14)
    return base_date + timedelta(days=days)
