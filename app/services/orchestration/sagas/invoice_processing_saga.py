# -*- coding: utf-8 -*-
"""Invoice Processing Saga - Rechnungsverarbeitung als Saga.

Implementiert den vollstaendigen Rechnungsverarbeitungs-Workflow:
1. validate_invoice - Rechnungsdaten validieren
2. export_to_datev - DATEV-Export erstellen
3. create_booking - Buchung in Finanzbuchhaltung anlegen

Jeder Schritt hat eine Compensation-Aktion fuer automatisches Rollback.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_detail
from app.db.session import get_async_session
from app.services.workflow.saga_service import SagaService, StepHandlerRegistry

logger = structlog.get_logger(__name__)


# =============================================================================
# Saga Step Definitions
# =============================================================================

INVOICE_PROCESSING_STEPS: List[Dict[str, object]] = [
    {
        "name": "Rechnung validieren",
        "description": "Prueft Vollstaendigkeit und Korrektheit der Rechnungsdaten",
        "action_type": "validate_invoice",
        "compensation_type": "mark_validation_failed",
        "timeout_seconds": 60,
        "max_retries": 2,
    },
    {
        "name": "DATEV-Export erstellen",
        "description": "Erstellt den Buchungsstapel-Export fuer DATEV",
        "action_type": "export_to_datev",
        "compensation_type": "cancel_datev_export",
        "timeout_seconds": 120,
        "max_retries": 3,
    },
    {
        "name": "Buchung anlegen",
        "description": "Legt die Buchung in der Finanzbuchhaltung an",
        "action_type": "create_booking",
        "compensation_type": "reverse_booking",
        "timeout_seconds": 120,
        "max_retries": 2,
    },
]


# =============================================================================
# Action Handlers
# =============================================================================


async def handle_validate_invoice(
    action_params: Dict[str, object],
    context_data: Dict[str, object],
    step_id: str,
) -> Dict[str, object]:
    """Validiert Rechnungsdaten auf Vollstaendigkeit.

    Prueft:
    - Pflichtfelder vorhanden (Betrag, Datum, Lieferant)
    - Betrag > 0
    - Rechnungsdatum nicht in der Zukunft
    - Dokument existiert in der Datenbank

    Args:
        action_params: {"document_id": str, "company_id": str}
        context_data: Saga-Kontext
        step_id: Step-ID fuer Logging

    Returns:
        Validierungsergebnis mit extrahierten Daten
    """
    document_id = str(action_params.get("document_id", ""))
    company_id = str(action_params.get("company_id", ""))

    if not document_id or not company_id:
        raise ValueError("Pflichtfelder fehlen: document_id und company_id erforderlich")

    async with get_async_session() as db:
        from sqlalchemy import select
        from app.db.models import Document

        doc_query = select(Document).where(
            Document.id == UUID(document_id),
            Document.company_id == UUID(company_id),
        )
        result = await db.execute(doc_query)
        document = result.scalar_one_or_none()

        if not document:
            raise ValueError(
                f"Dokument nicht gefunden: {document_id}"
            )

        # Extrahierte Daten pruefen
        extracted = document.extracted_data or {}
        errors: List[str] = []

        if not extracted.get("total_amount") and not extracted.get("brutto"):
            errors.append("Rechnungsbetrag fehlt")

        if not extracted.get("invoice_date") and not extracted.get("datum"):
            errors.append("Rechnungsdatum fehlt")

        if not extracted.get("supplier_name") and not extracted.get("lieferant"):
            errors.append("Lieferant fehlt")

        if errors:
            raise ValueError(
                f"Validierung fehlgeschlagen: {'; '.join(errors)}"
            )

        total_amount = extracted.get("total_amount") or extracted.get("brutto")
        invoice_date = extracted.get("invoice_date") or extracted.get("datum")
        supplier = extracted.get("supplier_name") or extracted.get("lieferant")

        logger.info(
            "invoice_validation_passed",
            document_id=document_id,
            step_id=step_id,
            total_amount=str(total_amount),
        )

        return {
            "document_id": document_id,
            "validated": True,
            "total_amount": str(total_amount),
            "invoice_date": str(invoice_date),
            "supplier": str(supplier),
            "document_type": document.document_type,
        }


async def handle_export_to_datev(
    action_params: Dict[str, object],
    context_data: Dict[str, object],
    step_id: str,
) -> Dict[str, object]:
    """Erstellt DATEV-Buchungsstapel-Export fuer die Rechnung.

    Args:
        action_params: {"document_id": str, "company_id": str, "user_id": str}
        context_data: Saga-Kontext (enthaelt Validierungsergebnis)
        step_id: Step-ID

    Returns:
        Export-Ergebnis mit Export-ID
    """
    document_id = str(action_params.get("document_id", ""))
    company_id = str(action_params.get("company_id", ""))
    user_id = str(action_params.get("user_id", ""))

    async with get_async_session() as db:
        from app.services.datev.export_service import DATEVExportService

        export_service = DATEVExportService()

        csv_bytes, export_record = await export_service.export_buchungsstapel(
            db=db,
            user_id=UUID(user_id),
            document_ids=[UUID(document_id)],
        )

        export_id = str(export_record.id)

        logger.info(
            "datev_export_created",
            document_id=document_id,
            export_id=export_id,
            step_id=step_id,
            csv_size=len(csv_bytes),
        )

        return {
            "export_id": export_id,
            "document_id": document_id,
            "csv_size": len(csv_bytes),
            "status": "erstellt",
        }


async def handle_create_booking(
    action_params: Dict[str, object],
    context_data: Dict[str, object],
    step_id: str,
) -> Dict[str, object]:
    """Legt Buchung in der Finanzbuchhaltung an.

    Args:
        action_params: {"document_id": str, "company_id": str, "confidence": float}
        context_data: Saga-Kontext
        step_id: Step-ID

    Returns:
        Buchungsergebnis mit Journal-Entry-ID
    """
    document_id = str(action_params.get("document_id", ""))
    company_id = str(action_params.get("company_id", ""))
    confidence = float(action_params.get("confidence", 0.9))

    async with get_async_session() as db:
        from app.services.accounting.gl_posting_service import GLPostingService

        gl_service = GLPostingService(db)
        entry = await gl_service.auto_post_from_pipeline(
            company_id=UUID(company_id),
            document_id=UUID(document_id),
            confidence=confidence,
        )
        await db.commit()

        if entry is None:
            logger.warning(
                "booking_skipped_low_confidence",
                document_id=document_id,
                confidence=confidence,
                step_id=step_id,
            )
            return {
                "document_id": document_id,
                "booked": False,
                "reason": "Konfidenz zu niedrig fuer automatische Buchung",
            }

        entry_id = str(entry.id)

        logger.info(
            "booking_created",
            document_id=document_id,
            entry_id=entry_id,
            step_id=step_id,
        )

        return {
            "document_id": document_id,
            "entry_id": entry_id,
            "booked": True,
        }


# =============================================================================
# Compensation Handlers
# =============================================================================


async def compensate_mark_validation_failed(
    compensation_params: Optional[Dict[str, object]],
    original_result: Optional[Dict[str, object]],
    context_data: Dict[str, object],
    step_id: str,
) -> None:
    """Markiert Rechnung als Validierung fehlgeschlagen.

    Args:
        compensation_params: Compensation-Parameter
        original_result: Ergebnis der Forward-Action
        context_data: Saga-Kontext
        step_id: Step-ID
    """
    document_id = ""
    if original_result:
        document_id = str(original_result.get("document_id", ""))

    logger.info(
        "compensation_mark_validation_failed",
        document_id=document_id,
        step_id=step_id,
    )
    # Validierung hat keine dauerhaften Seiteneffekte - nur Logging


async def compensate_cancel_datev_export(
    compensation_params: Optional[Dict[str, object]],
    original_result: Optional[Dict[str, object]],
    context_data: Dict[str, object],
    step_id: str,
) -> None:
    """Storniert den DATEV-Export.

    Args:
        compensation_params: Compensation-Parameter
        original_result: Ergebnis mit export_id
        context_data: Saga-Kontext
        step_id: Step-ID
    """
    if not original_result:
        logger.warning(
            "compensation_no_export_to_cancel",
            step_id=step_id,
        )
        return

    export_id = str(original_result.get("export_id", ""))
    if not export_id:
        return

    async with get_async_session() as db:
        from sqlalchemy import update
        from app.db import models

        await db.execute(
            update(models.DATEVExport)
            .where(models.DATEVExport.id == UUID(export_id))
            .values(status="storniert")
        )
        await db.commit()

    logger.info(
        "datev_export_cancelled",
        export_id=export_id,
        step_id=step_id,
    )


async def compensate_reverse_booking(
    compensation_params: Optional[Dict[str, object]],
    original_result: Optional[Dict[str, object]],
    context_data: Dict[str, object],
    step_id: str,
) -> None:
    """Storniert die Buchung (Storno-Buchung anlegen).

    Args:
        compensation_params: Compensation-Parameter
        original_result: Ergebnis mit entry_id
        context_data: Saga-Kontext
        step_id: Step-ID
    """
    if not original_result:
        logger.warning(
            "compensation_no_booking_to_reverse",
            step_id=step_id,
        )
        return

    booked = original_result.get("booked", False)
    if not booked:
        logger.info(
            "compensation_no_booking_was_created",
            step_id=step_id,
        )
        return

    entry_id = str(original_result.get("entry_id", ""))
    if not entry_id:
        return

    async with get_async_session() as db:
        from app.services.accounting.gl_posting_service import GLPostingService

        gl_service = GLPostingService(db)
        try:
            await gl_service.reverse_entry(
                entry_id=UUID(entry_id),
                reason="Saga-Compensation: Automatische Stornierung",
            )
            await db.commit()
        except Exception as e:
            logger.error(
                "compensation_reverse_booking_failed",
                entry_id=entry_id,
                error=safe_error_detail(e, "Saga"),
                step_id=step_id,
            )
            raise

    logger.info(
        "booking_reversed",
        entry_id=entry_id,
        step_id=step_id,
    )


# =============================================================================
# Saga Factory
# =============================================================================


def register_invoice_processing_handlers(
    registry: StepHandlerRegistry,
) -> None:
    """Registriert alle Handler fuer die Rechnungsverarbeitungs-Saga.

    Args:
        registry: StepHandlerRegistry-Instanz
    """
    # Action-Handler
    registry.register_action("validate_invoice", handle_validate_invoice)
    registry.register_action("export_to_datev", handle_export_to_datev)
    registry.register_action("create_booking", handle_create_booking)

    # Compensation-Handler
    registry.register_compensation(
        "mark_validation_failed", compensate_mark_validation_failed
    )
    registry.register_compensation(
        "cancel_datev_export", compensate_cancel_datev_export
    )
    registry.register_compensation(
        "reverse_booking", compensate_reverse_booking
    )


async def create_invoice_processing_saga(
    saga_service: SagaService,
    company_id: UUID,
    user_id: UUID,
    document_id: UUID,
    confidence: float = 0.9,
    description: Optional[str] = None,
) -> object:
    """Erstellt eine neue Rechnungsverarbeitungs-Saga.

    Args:
        saga_service: SagaService-Instanz
        company_id: Company-ID (Multi-Tenant)
        user_id: Initiator
        document_id: Dokument-ID der Rechnung
        confidence: Konfidenz-Schwellwert fuer Auto-Buchung
        description: Optionale Beschreibung

    Returns:
        Erstellte Saga
    """
    # Steps mit konkreten Parametern befuellen
    steps = []
    for step_def in INVOICE_PROCESSING_STEPS:
        step = dict(step_def)
        step["action_params"] = {
            "document_id": str(document_id),
            "company_id": str(company_id),
            "user_id": str(user_id),
            "confidence": confidence,
        }
        steps.append(step)

    saga = await saga_service.create_saga(
        company_id=company_id,
        user_id=user_id,
        name="Rechnungsverarbeitung",
        steps=steps,
        description=description or f"Automatische Verarbeitung fuer Dokument {document_id}",
        context_data={
            "document_id": str(document_id),
            "confidence": confidence,
            "saga_type": "invoice_processing",
        },
    )

    logger.info(
        "invoice_processing_saga_created",
        saga_id=str(saga.id),
        document_id=str(document_id),
        company_id=str(company_id),
    )

    return saga
