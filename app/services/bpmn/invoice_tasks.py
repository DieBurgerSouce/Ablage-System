"""Invoice Workflow Task Implementations.

Service Tasks für den Rechnungsfreigabe-Workflow.
Diese Funktionen werden von der BPMN Engine aufgerufen.
"""

from typing import Dict, Any
from uuid import UUID
from datetime import datetime, timezone
import structlog

logger = structlog.get_logger(__name__)


async def auto_approve_invoice(
    instance_id: str,
    variables: Dict[str, Any]
) -> Dict[str, Any]:
    """Automatische Freigabe für Rechnungen unter 1.000 EUR.

    Args:
        instance_id: BPMN Prozess-Instanz ID
        variables: Prozess-Variablen (invoice_id, amount, etc.)

    Returns:
        Aktualisierte Variablen mit Freigabe-Info
    """
    from app.db.session import async_session_maker

    invoice_id = variables.get("invoice_id")
    amount = variables.get("amount", 0)

    logger.info(
        "auto_approving_invoice",
        instance_id=instance_id,
        invoice_id=invoice_id,
        amount=amount
    )

    async with async_session_maker() as db:
        # Invoice-Status aktualisieren
        from app.db.bpmn_models.bpmn import ProcessHistory
        from sqlalchemy import select

        # Audit-Eintrag
        history = ProcessHistory(
            instance_id=UUID(instance_id),
            event_type="INVOICE_AUTO_APPROVED",
            message=f"Rechnung automatisch freigegeben (Betrag: {amount:.2f} EUR < 1.000 EUR)",
            actor_type="system",
            company_id=variables.get("company_id"),
            timestamp=datetime.now(timezone.utc)
        )

        # Invoice-Tracking aktualisieren (falls vorhanden)
        # from app.db.models import InvoiceTracking
        # ...

        await db.commit()

    return {
        "approved": True,
        "approval_type": "automatic",
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "approved_by": "system",
    }


async def book_invoice(
    instance_id: str,
    variables: Dict[str, Any]
) -> Dict[str, Any]:
    """Bucht eine freigegebene Rechnung.

    Erstellt Buchungssatz und aktualisiert Finanzdaten.

    Args:
        instance_id: BPMN Prozess-Instanz ID
        variables: Prozess-Variablen

    Returns:
        Aktualisierte Variablen mit Buchungs-Info
    """
    invoice_id = variables.get("invoice_id")
    amount = variables.get("amount", 0)

    logger.info(
        "booking_invoice",
        instance_id=instance_id,
        invoice_id=invoice_id,
        amount=amount
    )

    # Hier wuerde die tatsaechliche Buchungslogik implementiert
    # z.B. DATEV-Export, Kontenrahmen-Zuordnung, etc.

    booking_number = f"BU-{datetime.now().strftime('%Y%m%d')}-{invoice_id[:8]}"

    return {
        "booked": True,
        "booking_number": booking_number,
        "booked_at": datetime.now(timezone.utc).isoformat(),
    }


def calculate_approval_level(amount: float) -> str:
    """Berechnet die erforderliche Freigabestufe basierend auf dem Betrag.

    Args:
        amount: Rechnungsbetrag

    Returns:
        Freigabestufe: 'auto', 'department', 'executive'
    """
    if amount < 1000:
        return "auto"
    elif amount < 5000:
        return "department"
    else:
        return "executive"
