"""
Zero-Touch OCR Orchestrator.

Haupt-Orchestrator für die Zero-Touch-Pipeline:
1. Prüft ob OCR abgeschlossen ist
2. Holt Classification- und Extraction-Ergebnisse
3. Aggregiert Confidence-Scores
4. Erstellt Business-Objekte (falls auto-processable)
5. Bestimmt Ablageort
6. Speichert Ergebnis und emittiert Event
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, ProcessingStatus, Company, AppConfig
from app.services.events.event_bus import get_event_bus, EventType
from app.services.zero_touch.confidence_aggregator import ConfidenceAggregator, AggregatedConfidence
from app.services.zero_touch.business_object_factory import BusinessObjectFactory, BusinessObjectResult
from app.services.zero_touch.auto_filing_service import AutoFilingService, FilingResult
from app.services.zero_touch import zero_touch_metrics
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ZeroTouchResult:
    """Ergebnis der Zero-Touch-Verarbeitung."""

    document_id: UUID
    company_id: UUID
    processed_at: datetime
    success: bool

    # Confidence Aggregation
    overall_confidence: float
    auto_processable: bool
    confidence_breakdown: dict[str, Any]

    # Classification & Extraction
    classification_type: str
    classification_confidence: float
    extracted_fields: dict[str, Any]

    # Entity Matching
    entity_id: Optional[UUID] = None
    entity_confidence: Optional[float] = None

    # Business Object
    business_object_created: bool = False
    business_object_type: Optional[str] = None
    business_object_id: Optional[UUID] = None
    business_object_error: Optional[str] = None

    # Filing
    filing_folder_id: Optional[UUID] = None
    filing_folder_name: Optional[str] = None
    filing_confidence: float = 0.0
    filing_reason: str = ""

    # Processing Metrics
    processing_duration_ms: int = 0

    # Errors
    error_message: Optional[str] = None


@dataclass
class ZeroTouchStats:
    """Statistiken für Zero-Touch-Processing."""

    total_processed: int
    auto_processed: int
    auto_rate: float
    avg_confidence: float
    avg_processing_ms: int
    by_type: dict[str, int]


@dataclass
class ZeroTouchResultResponse:
    """Response-DTO für API."""

    document_id: UUID
    success: bool
    auto_processable: bool
    overall_confidence: float
    classification_type: str
    business_object_created: bool
    business_object_type: Optional[str]
    filing_folder_name: Optional[str]
    processed_at: str
    error_message: Optional[str] = None


# =============================================================================
# Orchestrator
# =============================================================================

class ZeroTouchOrchestrator:
    """
    Haupt-Orchestrator für Zero-Touch-Verarbeitung.

    Koordiniert alle Schritte von OCR-Completion bis zur Business-Object-Erstellung.
    """

    def __init__(
        self,
        confidence_threshold: float = 0.90,
    ) -> None:
        """
        Initialisiert den Orchestrator.

        Args:
            confidence_threshold: Schwellwert für automatische Verarbeitung (0.0 - 1.0)
        """
        self._confidence_aggregator = ConfidenceAggregator(
            auto_threshold=confidence_threshold,
        )
        self._business_object_factory = BusinessObjectFactory()
        self._auto_filing_service = AutoFilingService()
        self._event_bus = get_event_bus()

    async def process_document(
        self,
        document_id: UUID,
        company_id: UUID,
        db: AsyncSession,
    ) -> ZeroTouchResult:
        """
        Verarbeitet ein Dokument durch die Zero-Touch-Pipeline.

        Args:
            document_id: ID des zu verarbeitenden Dokuments
            company_id: Firmen-ID für Multi-Tenant
            db: Datenbank-Session

        Returns:
            ZeroTouchResult mit allen Verarbeitungsdetails
        """
        start_time = datetime.now(timezone.utc)

        logger.info(
            "zero_touch_processing_started",
            document_id=str(document_id),
            company_id=str(company_id),
        )

        try:
            # 1. Dokument abrufen
            doc_result = await db.execute(
                select(Document).where(
                    and_(
                        Document.id == document_id,
                        Document.company_id == company_id,
                    )
                )
            )
            document = doc_result.scalar_one_or_none()

            if not document:
                error_msg = "Dokument nicht gefunden"
                logger.error(
                    "document_not_found",
                    document_id=str(document_id),
                )
                return self._create_error_result(
                    document_id=document_id,
                    company_id=company_id,
                    error=error_msg,
                    start_time=start_time,
                )

            # 2. Prüfen ob OCR abgeschlossen
            if document.status != ProcessingStatus.COMPLETED.value:
                error_msg = f"OCR noch nicht abgeschlossen (Status: {document.status})"
                logger.warning(
                    "ocr_not_completed",
                    document_id=str(document_id),
                    status=document.status,
                )
                return self._create_error_result(
                    document_id=document_id,
                    company_id=company_id,
                    error=error_msg,
                    start_time=start_time,
                )

            # 3. Classification-Ergebnis holen
            classification_type = document.document_type or "other"
            document_metadata = document.document_metadata or {}
            classification_confidence = document_metadata.get("classification_confidence", 0.0)

            # 4. Extraction-Ergebnis holen
            extracted_fields = document_metadata.get("extracted_fields", {})
            extraction_confidence = self._calculate_extraction_confidence(extracted_fields)

            # 5. OCR Confidence
            ocr_confidence = document.ocr_confidence or 0.0

            # 6. Entity Matching holen
            entity_id = document.business_entity_id
            entity_confidence = None
            if entity_id:
                entity_confidence = document_metadata.get("entity_match_confidence", 0.0)

            # 7. Confidence aggregieren
            aggregated_confidence = self._confidence_aggregator.aggregate(
                ocr_conf=ocr_confidence,
                class_conf=classification_confidence,
                extract_conf=extraction_confidence,
                entity_conf=entity_confidence,
            )

            # 8. Business Object erstellen (falls auto-processable)
            business_object_result: Optional[BusinessObjectResult] = None
            if aggregated_confidence.auto_processable:
                logger.info(
                    "document_auto_processable",
                    document_id=str(document_id),
                    confidence=aggregated_confidence.overall,
                )

                business_object_result = await self._business_object_factory.create_business_object(
                    document_id=document_id,
                    classification_type=classification_type,
                    extracted_fields=extracted_fields,
                    entity_id=entity_id,
                    company_id=company_id,
                    db=db,
                )
            else:
                logger.info(
                    "document_requires_manual_review",
                    document_id=str(document_id),
                    confidence=aggregated_confidence.overall,
                    threshold=aggregated_confidence.threshold,
                )

            # 9. Filing bestimmen
            filing_result = await self._auto_filing_service.determine_filing(
                document_id=document_id,
                classification_type=classification_type,
                entity_id=entity_id,
                company_id=company_id,
                db=db,
            )

            # 10. Ergebnis erstellen
            duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

            result = ZeroTouchResult(
                document_id=document_id,
                company_id=company_id,
                processed_at=datetime.now(timezone.utc),
                success=True,
                overall_confidence=aggregated_confidence.overall,
                auto_processable=aggregated_confidence.auto_processable,
                confidence_breakdown=self._serialize_confidence_breakdown(aggregated_confidence),
                classification_type=classification_type,
                classification_confidence=classification_confidence,
                extracted_fields=extracted_fields,
                entity_id=entity_id,
                entity_confidence=entity_confidence,
                business_object_created=business_object_result.success if business_object_result else False,
                business_object_type=business_object_result.object_type if business_object_result else None,
                business_object_id=business_object_result.object_id if business_object_result else None,
                business_object_error=business_object_result.error if business_object_result else None,
                filing_folder_id=filing_result.folder_id,
                filing_folder_name=filing_result.folder_name,
                filing_confidence=filing_result.confidence,
                filing_reason=filing_result.reason,
                processing_duration_ms=duration_ms,
            )

            # 11. In Document-Metadata speichern
            await self._store_result(document, result, db)

            # 12. Event emittieren
            await self._emit_event(result)

            # 13. Metriken erfassen
            self._record_metrics(result)

            logger.info(
                "zero_touch_processing_completed",
                document_id=str(document_id),
                auto_processable=result.auto_processable,
                confidence=result.overall_confidence,
                duration_ms=duration_ms,
            )

            return result

        except Exception as e:
            duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            logger.error(
                "zero_touch_processing_failed",
                document_id=str(document_id),
                **safe_error_log(e),
                duration_ms=duration_ms,
                exc_info=True,
            )

            error_result = self._create_error_result(
                document_id=document_id,
                company_id=company_id,
                **safe_error_log(e),
                start_time=start_time,
            )

            # Metriken für Fehler
            zero_touch_metrics.record_processing(
                result="failed",
                doc_type="unknown",
                confidence=0.0,
                duration_ms=duration_ms,
            )

            return error_result

    async def get_result(
        self,
        document_id: UUID,
        company_id: UUID,
        db: AsyncSession,
    ) -> Optional[ZeroTouchResultResponse]:
        """
        Holt das Zero-Touch-Ergebnis für ein Dokument.

        Args:
            document_id: ID des Dokuments
            company_id: Mandanten-ID für Multi-Tenant Isolation
            db: Datenbank-Session

        Returns:
            ZeroTouchResultResponse oder None
        """
        # SECURITY FIX: company_id Filter für Multi-Tenant Isolation
        doc_result = await db.execute(
            select(Document).where(
                and_(
                    Document.id == document_id,
                    Document.company_id == company_id,
                )
            )
        )
        document = doc_result.scalar_one_or_none()

        if not document:
            return None

        metadata = document.document_metadata or {}
        zero_touch_data = metadata.get("zero_touch_result")

        if not zero_touch_data:
            return None

        return ZeroTouchResultResponse(
            document_id=document_id,
            success=zero_touch_data.get("success", False),
            auto_processable=zero_touch_data.get("auto_processable", False),
            overall_confidence=zero_touch_data.get("overall_confidence", 0.0),
            classification_type=zero_touch_data.get("classification_type", "unknown"),
            business_object_created=zero_touch_data.get("business_object_created", False),
            business_object_type=zero_touch_data.get("business_object_type"),
            filing_folder_name=zero_touch_data.get("filing_folder_name"),
            processed_at=zero_touch_data.get("processed_at", ""),
            error_message=zero_touch_data.get("error_message"),
        )

    async def get_stats(
        self,
        company_id: UUID,
        db: AsyncSession,
    ) -> ZeroTouchStats:
        """
        Holt Statistiken für Zero-Touch-Processing einer Firma.

        Args:
            company_id: Firmen-ID
            db: Datenbank-Session

        Returns:
            ZeroTouchStats mit Verarbeitungsstatistiken
        """
        # Dokumente mit Zero-Touch-Ergebnis
        query = select(Document).where(
            and_(
                Document.company_id == company_id,
                Document.status == ProcessingStatus.COMPLETED.value,
                Document.document_metadata.has_key("zero_touch_result"),  # Hat zero_touch_result key
            )
        )

        result = await db.execute(query)
        documents = result.scalars().all()

        if not documents:
            return ZeroTouchStats(
                total_processed=0,
                auto_processed=0,
                auto_rate=0.0,
                avg_confidence=0.0,
                avg_processing_ms=0,
                by_type={},
            )

        # Statistiken berechnen
        total = len(documents)
        auto_processed = 0
        confidence_sum = 0.0
        duration_sum = 0
        by_type: dict[str, int] = {}

        for doc in documents:
            zero_touch_data = doc.document_metadata.get("zero_touch_result", {})

            if zero_touch_data.get("auto_processable", False):
                auto_processed += 1

            confidence_sum += zero_touch_data.get("overall_confidence", 0.0)
            duration_sum += zero_touch_data.get("processing_duration_ms", 0)

            doc_type = zero_touch_data.get("classification_type", "unknown")
            by_type[doc_type] = by_type.get(doc_type, 0) + 1

        auto_rate = auto_processed / total if total > 0 else 0.0
        avg_confidence = confidence_sum / total if total > 0 else 0.0
        avg_duration = duration_sum // total if total > 0 else 0

        # Gauge aktualisieren
        zero_touch_metrics.update_auto_rate(auto_rate)

        return ZeroTouchStats(
            total_processed=total,
            auto_processed=auto_processed,
            auto_rate=auto_rate,
            avg_confidence=avg_confidence,
            avg_processing_ms=avg_duration,
            by_type=by_type,
        )

    async def update_thresholds(
        self,
        company_id: UUID,
        thresholds: dict[str, float],
        db: AsyncSession,
    ) -> None:
        """
        Aktualisiert Zero-Touch-Schwellwerte für eine Firma.

        Args:
            company_id: Firmen-ID
            thresholds: Dictionary mit {threshold_name: value}
            db: Datenbank-Session
        """
        logger.info(
            "updating_zero_touch_thresholds",
            company_id=str(company_id),
            thresholds=thresholds,
        )

        # Schwellwerte in AppConfig speichern
        config_key = f"zero_touch_thresholds_{company_id}"

        config_result = await db.execute(
            select(AppConfig).where(AppConfig.key == config_key)
        )
        config = config_result.scalar_one_or_none()

        if config:
            config.value = thresholds
            config.updated_at = datetime.now(timezone.utc)
        else:
            config = AppConfig(
                key=config_key,
                value=thresholds,
                description=f"Zero-Touch Schwellwerte für Company {company_id}",
            )
            db.add(config)

        await db.commit()

        # Confidence Aggregator aktualisieren (falls auto_threshold gesetzt)
        if "auto_threshold" in thresholds:
            self._confidence_aggregator.update_threshold(thresholds["auto_threshold"])

        logger.info(
            "zero_touch_thresholds_updated",
            company_id=str(company_id),
        )

    # =========================================================================
    # Private Helper Methods
    # =========================================================================

    def _calculate_extraction_confidence(
        self,
        extracted_fields: dict[str, Any],
    ) -> float:
        """
        Berechnet durchschnittliche Confidence der extrahierten Felder.

        Args:
            extracted_fields: Dictionary mit {field_name: {value, confidence}}

        Returns:
            Durchschnittliche Confidence (0.0 - 1.0)
        """
        if not extracted_fields:
            return 0.0

        confidence_sum = 0.0
        confidence_count = 0

        for field_name, field_data in extracted_fields.items():
            if isinstance(field_data, dict) and "confidence" in field_data:
                confidence_sum += field_data["confidence"]
                confidence_count += 1

        return confidence_sum / confidence_count if confidence_count > 0 else 0.0

    def _serialize_confidence_breakdown(
        self,
        aggregated: AggregatedConfidence,
    ) -> dict[str, Any]:
        """Serialisiert Confidence Breakdown für JSON-Speicherung."""
        return {
            "overall": aggregated.overall,
            "threshold": aggregated.threshold,
            "auto_processable": aggregated.auto_processable,
            "breakdown": [
                {
                    "source": item.source,
                    "confidence": item.confidence,
                    "weight": item.weight,
                    "weighted_score": item.weighted_score,
                }
                for item in aggregated.breakdown
            ],
        }

    async def _store_result(
        self,
        document: Document,
        result: ZeroTouchResult,
        db: AsyncSession,
    ) -> None:
        """Speichert Zero-Touch-Ergebnis in Document-Metadata."""
        metadata = document.document_metadata or {}

        # Ergebnis als Dictionary
        result_dict = {
            "success": result.success,
            "processed_at": result.processed_at.isoformat(),
            "overall_confidence": result.overall_confidence,
            "auto_processable": result.auto_processable,
            "confidence_breakdown": result.confidence_breakdown,
            "classification_type": result.classification_type,
            "classification_confidence": result.classification_confidence,
            "entity_id": str(result.entity_id) if result.entity_id else None,
            "entity_confidence": result.entity_confidence,
            "business_object_created": result.business_object_created,
            "business_object_type": result.business_object_type,
            "business_object_id": str(result.business_object_id) if result.business_object_id else None,
            "business_object_error": result.business_object_error,
            "filing_folder_id": str(result.filing_folder_id) if result.filing_folder_id else None,
            "filing_folder_name": result.filing_folder_name,
            "filing_confidence": result.filing_confidence,
            "filing_reason": result.filing_reason,
            "processing_duration_ms": result.processing_duration_ms,
            "error_message": result.error_message,
        }

        metadata["zero_touch_result"] = result_dict
        document.document_metadata = metadata

        await db.commit()

    async def _emit_event(self, result: ZeroTouchResult) -> None:
        """Emittiert Event für Zero-Touch-Completion."""
        try:
            await self._event_bus.publish_event(
                event_type=EventType.DOCUMENT_OCR_COMPLETED,  # Oder neues ZERO_TOUCH_COMPLETED
                payload={
                    "document_id": str(result.document_id),
                    "company_id": str(result.company_id),
                    "auto_processable": result.auto_processable,
                    "overall_confidence": result.overall_confidence,
                    "classification_type": result.classification_type,
                    "business_object_created": result.business_object_created,
                    "business_object_type": result.business_object_type,
                },
                source="zero_touch_orchestrator",
            )
        except Exception as e:
            logger.warning(
                "failed_to_emit_zero_touch_event",
                document_id=str(result.document_id),
                **safe_error_log(e),
            )

    def _record_metrics(self, result: ZeroTouchResult) -> None:
        """Erfasst Prometheus-Metriken."""
        result_status = "success" if result.success else "failed"
        if result.success and not result.auto_processable:
            result_status = "manual_review_required"

        zero_touch_metrics.record_processing(
            result=result_status,
            doc_type=result.classification_type,
            confidence=result.overall_confidence,
            duration_ms=result.processing_duration_ms,
        )

    def _create_error_result(
        self,
        document_id: UUID,
        company_id: UUID,
        error: str,
        start_time: datetime,
    ) -> ZeroTouchResult:
        """Erstellt ein Error-Result."""
        duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

        return ZeroTouchResult(
            document_id=document_id,
            company_id=company_id,
            processed_at=datetime.now(timezone.utc),
            success=False,
            overall_confidence=0.0,
            auto_processable=False,
            confidence_breakdown={},
            classification_type="unknown",
            classification_confidence=0.0,
            extracted_fields={},
            processing_duration_ms=duration_ms,
            error_message=error,
        )
