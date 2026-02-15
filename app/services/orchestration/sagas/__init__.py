# -*- coding: utf-8 -*-
"""Saga-Implementierungen fuer Ablage-System.

Stellt konkrete Saga-Implementierungen bereit:
- InvoiceProcessingSaga: Rechnung -> DATEV -> Buchung
- PaymentSaga: Freigabe -> SEPA -> Bank -> Status

Alle Handler werden ueber register_all_saga_handlers() beim
SagaService registriert.
"""

from app.services.orchestration.sagas.invoice_processing_saga import (
    INVOICE_PROCESSING_STEPS,
    create_invoice_processing_saga,
    register_invoice_processing_handlers,
)
from app.services.orchestration.sagas.payment_saga import (
    PAYMENT_STEPS,
    create_payment_saga,
    register_payment_handlers,
)
from app.services.workflow.saga_service import StepHandlerRegistry


def register_all_saga_handlers(
    registry: StepHandlerRegistry,
) -> None:
    """Registriert alle Saga-Handler in der Registry.

    Wird vom SagaService bei Initialisierung aufgerufen.

    Args:
        registry: StepHandlerRegistry-Instanz
    """
    register_invoice_processing_handlers(registry)
    register_payment_handlers(registry)


__all__ = [
    # Registration
    "register_all_saga_handlers",
    # Invoice Processing
    "INVOICE_PROCESSING_STEPS",
    "create_invoice_processing_saga",
    "register_invoice_processing_handlers",
    # Payment
    "PAYMENT_STEPS",
    "create_payment_saga",
    "register_payment_handlers",
]
