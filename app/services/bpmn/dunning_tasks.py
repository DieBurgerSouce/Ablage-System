"""Dunning Workflow Task Implementations.

Service Tasks fuer den Mahnwesen-Workflow.
Diese Funktionen werden von der BPMN Engine aufgerufen.
"""

from typing import Dict, Any
from uuid import UUID
from datetime import datetime, timezone, timedelta
import structlog

logger = structlog.get_logger(__name__)


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

        # TODO: Tatsaechlicher Email-Versand ueber EmailService
        # from app.services.email_service import EmailService
        # email_service = EmailService(db)
        # await email_service.send_payment_reminder(...)

        await db.commit()

    return {
        "reminder_sent": True,
        "reminder_sent_at": datetime.now(timezone.utc).isoformat(),
        "reminder_type": "payment_reminder",
        "dunning_level": 0,
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
    dunning_fee = 5.00  # Standard-Mahngebuehr

    logger.info(
        "sending_first_dunning",
        instance_id=instance_id,
        invoice_id=invoice_id,
        dunning_level=1
    )

    async with async_session_maker() as db:
        history = ProcessHistory(
            instance_id=UUID(instance_id),
            event_type="FIRST_DUNNING_SENT",
            message=f"1. Mahnung versendet (Betrag: {amount:.2f} EUR, Mahngebuehr: {dunning_fee:.2f} EUR)",
            actor_type="system",
            company_id=variables.get("company_id"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(history)

        # Invoice-Tracking aktualisieren
        # from app.db.models import InvoiceTracking
        # await update_dunning_level(db, invoice_id, 1)

        await db.commit()

    return {
        "dunning_sent": True,
        "dunning_sent_at": datetime.now(timezone.utc).isoformat(),
        "dunning_level": 1,
        "dunning_fee": dunning_fee,
        "total_outstanding": amount + dunning_fee,
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
    dunning_fee = 10.00  # Erhoehte Mahngebuehr

    logger.info(
        "sending_second_dunning",
        instance_id=instance_id,
        invoice_id=invoice_id,
        dunning_level=2
    )

    async with async_session_maker() as db:
        history = ProcessHistory(
            instance_id=UUID(instance_id),
            event_type="SECOND_DUNNING_SENT",
            message=f"2. Mahnung versendet (Betrag: {amount:.2f} EUR, Mahngebuehr: {dunning_fee:.2f} EUR)",
            actor_type="system",
            company_id=variables.get("company_id"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(history)
        await db.commit()

    return {
        "dunning_sent": True,
        "dunning_sent_at": datetime.now(timezone.utc).isoformat(),
        "dunning_level": 2,
        "dunning_fee": dunning_fee,
        "total_outstanding": amount + dunning_fee,
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
    dunning_fee = 15.00  # Letzte Mahngebuehr

    logger.info(
        "sending_final_dunning",
        instance_id=instance_id,
        invoice_id=invoice_id,
        dunning_level=3
    )

    async with async_session_maker() as db:
        history = ProcessHistory(
            instance_id=UUID(instance_id),
            event_type="FINAL_DUNNING_SENT",
            message=f"Letzte Mahnung vor Inkasso versendet (Betrag: {amount:.2f} EUR)",
            actor_type="system",
            company_id=variables.get("company_id"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(history)
        await db.commit()

    return {
        "dunning_sent": True,
        "dunning_sent_at": datetime.now(timezone.utc).isoformat(),
        "dunning_level": 3,
        "dunning_fee": dunning_fee,
        "total_outstanding": amount + dunning_fee,
        "inkasso_warning": True,
    }


async def transfer_to_collection(
    instance_id: str,
    variables: Dict[str, Any]
) -> Dict[str, Any]:
    """Uebergibt die Forderung an ein Inkasso-Unternehmen.

    Args:
        instance_id: BPMN Prozess-Instanz ID
        variables: Prozess-Variablen

    Returns:
        Aktualisierte Variablen mit Inkasso-Info
    """
    from app.db.session import async_session_maker
    from app.db.bpmn_models.bpmn import ProcessHistory

    invoice_id = variables.get("invoice_id")
    amount = variables.get("total_outstanding", variables.get("amount", 0))

    logger.warning(
        "transferring_to_collection",
        instance_id=instance_id,
        invoice_id=invoice_id,
        amount=amount
    )

    async with async_session_maker() as db:
        history = ProcessHistory(
            instance_id=UUID(instance_id),
            event_type="TRANSFERRED_TO_COLLECTION",
            message=f"Forderung an Inkasso uebergeben (Gesamtbetrag: {amount:.2f} EUR)",
            actor_type="system",
            company_id=variables.get("company_id"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(history)

        # TODO: Integration mit Inkasso-Service
        # - Daten an Inkasso-API senden
        # - Aktenzeichen generieren
        # - Kundenstatus aktualisieren

        await db.commit()

    collection_reference = f"INK-{datetime.now().strftime('%Y%m%d')}-{invoice_id[:8]}"

    return {
        "transferred_to_collection": True,
        "transferred_at": datetime.now(timezone.utc).isoformat(),
        "collection_reference": collection_reference,
        "collection_amount": amount,
        "dunning_level": 4,
    }


async def check_payment_received(
    instance_id: str,
    variables: Dict[str, Any]
) -> Dict[str, Any]:
    """Prueft ob eine Zahlung eingegangen ist.

    Diese Task wird typischerweise als Timer-Task aufgerufen.

    Args:
        instance_id: BPMN Prozess-Instanz ID
        variables: Prozess-Variablen

    Returns:
        Variablen mit Zahlungsstatus
    """
    from app.db.session import async_session_maker

    invoice_id = variables.get("invoice_id")
    expected_amount = variables.get("total_outstanding", variables.get("amount", 0))

    logger.info(
        "checking_payment_received",
        instance_id=instance_id,
        invoice_id=invoice_id
    )

    # TODO: Tatsaechliche Zahlungspruefung
    # - Bank-Transaktionen abfragen
    # - Matching mit offenen Posten
    # - Teilzahlungen beruecksichtigen

    async with async_session_maker() as db:
        # Simulierte Pruefung - in Produktion: echte Datenbankabfrage
        # from app.db.models import BankTransaction
        # payment = await db.execute(select(BankTransaction).where(...))
        payment_received = False
        payment_amount = 0.0

        # Wenn keine Zahlung gefunden, weitermahnen
        if not payment_received:
            return {
                "payment_received": False,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }

        return {
            "payment_received": True,
            "payment_amount": payment_amount,
            "payment_date": datetime.now(timezone.utc).isoformat(),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }


async def close_dunning_case(
    instance_id: str,
    variables: Dict[str, Any]
) -> Dict[str, Any]:
    """Schliesst den Mahnfall ab (Zahlung eingegangen).

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
    """Berechnet die naechste Mahnfrist.

    Args:
        current_level: Aktuelle Mahnstufe (0-3)
        base_date: Ausgangsdatum (default: jetzt)

    Returns:
        Deadline fuer naechste Mahnung
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
