# -*- coding: utf-8 -*-
"""
Lineage Integration Helpers.

Provides easy-to-use functions for integrating lineage tracking
into existing services without heavy modifications.

SECURITY: Niemals PII in Lineage-Events speichern!
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from uuid import UUID
import asyncio
import functools

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_lineage import LineageEventType, ImportSourceType
from app.services.lineage.document_lineage_service import (
    DocumentLineageService,
    get_lineage_service,
)
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# ASYNC CONTEXT MANAGER FOR PROCESSING STEPS
# =============================================================================


class LineageProcessingStep:
    """
    Context Manager für automatisches Lineage-Tracking von Verarbeitungsschritten.

    Misst automatisch die Dauer und zeichnet Start/Ende/Fehler auf.

    Usage:
        async with LineageProcessingStep(
            db=db,
            document_id=doc_id,
            company_id=company_id,
            step_type=LineageEventType.OCR_COMPLETE,
            source_service="ocr_worker",
        ) as step:
            # Verarbeitung durchführen
            result = await process_document(doc_id)
            step.set_confidence(result.confidence)
            step.add_details({"backend": result.backend})
    """

    def __init__(
        self,
        db: AsyncSession,
        document_id: UUID,
        company_id: UUID,
        step_type: LineageEventType,
        source_service: str = "unknown",
        user_id: Optional[UUID] = None,
        correlation_id: Optional[UUID] = None,
    ):
        self._db = db
        self._document_id = document_id
        self._company_id = company_id
        self._step_type = step_type
        self._source_service = source_service
        self._user_id = user_id
        self._correlation_id = correlation_id

        self._start_time: Optional[datetime] = None
        self._confidence: Optional[float] = None
        self._details: Dict[str, Any] = {}

    def set_confidence(self, confidence: float) -> None:
        """Setzt die Konfidenz des Verarbeitungsschritts."""
        self._confidence = confidence

    def add_details(self, details: Dict[str, Any]) -> None:
        """Fuegt Details zum Ereignis hinzu (ohne PII!)."""
        self._details.update(details)

    async def __aenter__(self) -> "LineageProcessingStep":
        self._start_time = datetime.now(timezone.utc)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        duration_ms = None
        if self._start_time:
            duration = datetime.now(timezone.utc) - self._start_time
            duration_ms = int(duration.total_seconds() * 1000)

        try:
            service = get_lineage_service(self._db)

            # Bei Fehler: Fehlgeschlagen-Event
            if exc_type is not None:
                # Fehler-Event aufzeichnen (bei OCR)
                if self._step_type == LineageEventType.OCR_COMPLETE:
                    await service.record_processing_step(
                        document_id=self._document_id,
                        company_id=self._company_id,
                        step_type=LineageEventType.OCR_FAILED,
                        details={
                            **self._details,
                            "error_type": exc_type.__name__ if exc_type else "Unknown",
                        },
                        duration_ms=duration_ms,
                        user_id=self._user_id,
                        source_service=self._source_service,
                        correlation_id=self._correlation_id,
                    )
                else:
                    # Generisches Fehler-Logging
                    logger.warning(
                        "lineage_processing_step_failed",
                        document_id=str(self._document_id),
                        step_type=self._step_type.value,
                        error_type=exc_type.__name__ if exc_type else "Unknown",
                    )
            else:
                # Erfolg-Event aufzeichnen
                await service.record_processing_step(
                    document_id=self._document_id,
                    company_id=self._company_id,
                    step_type=self._step_type,
                    details=self._details,
                    duration_ms=duration_ms,
                    confidence=self._confidence,
                    user_id=self._user_id,
                    source_service=self._source_service,
                    correlation_id=self._correlation_id,
                )

            await self._db.commit()

        except Exception as e:
            # Lineage-Fehler sollten nie die Hauptverarbeitung stoppen
            logger.error(
                "lineage_tracking_failed",
                document_id=str(self._document_id),
                **safe_error_log(e),
            )

        return False  # Exceptions nicht unterdrücken


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


async def record_document_import(
    db: AsyncSession,
    document_id: UUID,
    company_id: UUID,
    source_type: ImportSourceType,
    source_details: Optional[Dict[str, Any]] = None,
    user_id: Optional[UUID] = None,
) -> None:
    """
    Zeichnet den Import eines Dokuments auf.

    Diese Funktion kann nach dem Erstellen eines Dokuments aufgerufen werden.

    Args:
        db: Database Session
        document_id: ID des importierten Dokuments
        company_id: ID der Firma
        source_type: Typ der Import-Quelle
        source_details: Details (ohne PII!)
        user_id: ID des Benutzers (bei manuellem Upload)
    """
    try:
        service = get_lineage_service(db)
        await service.record_import_event(
            document_id=document_id,
            company_id=company_id,
            source_type=source_type,
            source_details=source_details,
            user_id=user_id,
        )
        await db.commit()
    except Exception as e:
        logger.error(
            "lineage_import_tracking_failed",
            document_id=str(document_id),
            **safe_error_log(e),
        )


async def record_ocr_result(
    db: AsyncSession,
    document_id: UUID,
    company_id: UUID,
    backend: str,
    duration_ms: int,
    confidence: float,
    page_count: Optional[int] = None,
    success: bool = True,
    error_message: Optional[str] = None,
    correlation_id: Optional[UUID] = None,
) -> None:
    """
    Zeichnet das Ergebnis einer OCR-Verarbeitung auf.

    Args:
        db: Database Session
        document_id: ID des Dokuments
        company_id: ID der Firma
        backend: Verwendetes OCR-Backend
        duration_ms: Verarbeitungsdauer in Millisekunden
        confidence: OCR-Konfidenz (0.0 - 1.0)
        page_count: Anzahl der verarbeiteten Seiten
        success: True wenn erfolgreich
        error_message: Fehlermeldung (ohne PII!)
        correlation_id: Korrelations-ID
    """
    try:
        service = get_lineage_service(db)

        step_type = LineageEventType.OCR_COMPLETE if success else LineageEventType.OCR_FAILED

        details = {
            "backend": backend,
            "page_count": page_count,
        }
        if not success and error_message:
            # SECURITY: Fehlermeldung kürzen und sanitizen
            details["error"] = error_message[:100] if error_message else None

        await service.record_processing_step(
            document_id=document_id,
            company_id=company_id,
            step_type=step_type,
            details=details,
            duration_ms=duration_ms,
            confidence=confidence if success else None,
            source_service="ocr_worker",
            correlation_id=correlation_id,
        )
        await db.commit()
    except Exception as e:
        logger.error(
            "lineage_ocr_tracking_failed",
            document_id=str(document_id),
            **safe_error_log(e),
        )


async def record_classification(
    db: AsyncSession,
    document_id: UUID,
    company_id: UUID,
    document_type: str,
    confidence: float,
    method: str = "ml",
    correlation_id: Optional[UUID] = None,
) -> None:
    """
    Zeichnet eine Dokumenten-Klassifikation auf.

    Args:
        db: Database Session
        document_id: ID des Dokuments
        company_id: ID der Firma
        document_type: Erkannter Dokumenttyp
        confidence: Klassifikations-Konfidenz (0.0 - 1.0)
        method: Klassifikations-Methode (ml, rule, manual)
        correlation_id: Korrelations-ID
    """
    try:
        service = get_lineage_service(db)
        await service.record_processing_step(
            document_id=document_id,
            company_id=company_id,
            step_type=LineageEventType.CLASSIFICATION,
            details={
                "document_type": document_type,
                "method": method,
            },
            confidence=confidence,
            source_service="classification_service",
            correlation_id=correlation_id,
        )
        await db.commit()
    except Exception as e:
        logger.error(
            "lineage_classification_tracking_failed",
            document_id=str(document_id),
            **safe_error_log(e),
        )


async def record_entity_linking(
    db: AsyncSession,
    document_id: UUID,
    company_id: UUID,
    entity_id: UUID,
    confidence: float,
    match_type: str,
    reason: str,
    user_id: Optional[UUID] = None,
    correlation_id: Optional[UUID] = None,
) -> None:
    """
    Zeichnet eine Entity-Verknüpfung auf.

    Args:
        db: Database Session
        document_id: ID des Dokuments
        company_id: ID der Firma
        entity_id: ID des verknüpften Geschäftspartners
        confidence: Verknüpfungs-Konfidenz (0.0 - 1.0)
        match_type: Art des Matches (customer_number, iban, vat_id, name_fuzzy)
        reason: Grund für die Verknüpfung (ohne PII!)
        user_id: ID des Benutzers (bei manueller Verknüpfung)
        correlation_id: Korrelations-ID
    """
    try:
        service = get_lineage_service(db)
        await service.record_entity_link(
            document_id=document_id,
            company_id=company_id,
            entity_id=entity_id,
            confidence=confidence,
            reason=reason,
            match_type=match_type,
            user_id=user_id,
            correlation_id=correlation_id,
        )
        await db.commit()
    except Exception as e:
        logger.error(
            "lineage_entity_linking_tracking_failed",
            document_id=str(document_id),
            **safe_error_log(e),
        )


async def record_document_modification(
    db: AsyncSession,
    document_id: UUID,
    company_id: UUID,
    user_id: UUID,
    field_name: str,
    modification_type: str = "update",
    correlation_id: Optional[UUID] = None,
) -> None:
    """
    Zeichnet eine Dokumentenänderung auf.

    SECURITY: Speichert KEINE Feldwerte, nur den Feldnamen und die Änderungsart.

    Args:
        db: Database Session
        document_id: ID des Dokuments
        company_id: ID der Firma
        user_id: ID des ändernden Benutzers
        field_name: Name des geänderten Feldes
        modification_type: Art der Änderung (update, delete, add)
        correlation_id: Korrelations-ID
    """
    try:
        service = get_lineage_service(db)
        await service.record_modification(
            document_id=document_id,
            company_id=company_id,
            field_name=field_name,
            old_value=None,  # Keine Werte speichern
            new_value=None,  # Keine Werte speichern
            user_id=user_id,
            modification_type=modification_type,
            correlation_id=correlation_id,
        )
        await db.commit()
    except Exception as e:
        logger.error(
            "lineage_modification_tracking_failed",
            document_id=str(document_id),
            **safe_error_log(e),
        )


async def record_document_export(
    db: AsyncSession,
    document_id: UUID,
    company_id: UUID,
    export_format: str,
    user_id: Optional[UUID] = None,
    destination: Optional[str] = None,
    correlation_id: Optional[UUID] = None,
) -> None:
    """
    Zeichnet einen Dokumenten-Export auf.

    Args:
        db: Database Session
        document_id: ID des Dokuments
        company_id: ID der Firma
        export_format: Export-Format (pdf, json, csv, datev, etc.)
        user_id: ID des exportierenden Benutzers
        destination: Ziel (ohne PII!)
        correlation_id: Korrelations-ID
    """
    try:
        service = get_lineage_service(db)
        await service.record_export_event(
            document_id=document_id,
            company_id=company_id,
            export_format=export_format,
            destination=destination,
            user_id=user_id,
            correlation_id=correlation_id,
        )
        await db.commit()
    except Exception as e:
        logger.error(
            "lineage_export_tracking_failed",
            document_id=str(document_id),
            **safe_error_log(e),
        )


# =============================================================================
# DECORATOR FOR AUTOMATIC LINEAGE TRACKING
# =============================================================================


def track_lineage(
    step_type: LineageEventType,
    source_service: str = "api",
):
    """
    Decorator für automatisches Lineage-Tracking von API-Endpoints.

    Erwartet, dass die Funktion document_id, company_id und optional user_id
    als Argumente oder im Return-Wert hat.

    Usage:
        @track_lineage(LineageEventType.MODIFICATION, source_service="document_api")
        async def update_document(document_id: UUID, company_id: UUID, ...):
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Funktion ausführen
            result = await func(*args, **kwargs)

            # Versuchen, Lineage zu tracken (im Hintergrund)
            try:
                # IDs aus kwargs extrahieren
                document_id = kwargs.get("document_id")
                company_id = kwargs.get("company_id")
                user_id = kwargs.get("user_id")
                db = kwargs.get("db")

                if document_id and company_id and db:
                    service = get_lineage_service(db)
                    await service.record_processing_step(
                        document_id=document_id,
                        company_id=company_id,
                        step_type=step_type,
                        user_id=user_id,
                        source_service=source_service,
                    )
            except Exception as e:
                logger.warning(
                    "lineage_decorator_tracking_failed",
                    **safe_error_log(e),
                )

            return result

        return wrapper
    return decorator
