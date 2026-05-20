# -*- coding: utf-8 -*-
"""
End-to-End Document Processing Pipeline Chain.

Orchestriert die vollstaendige Zero-Touch-Verarbeitung:
OCR -> Klassifizierung -> Entity-Linking -> Kontierung -> 3-Way-Matching -> Ablage

Jeder Schritt wird mit Confidence-Score bewertet.
Das Gesamtergebnis entscheidet ob automatisch oder manuell verarbeitet wird.

Architektur-Entscheidung:
- Graceful Degradation: Pipeline laeuft weiter, auch wenn ein Schritt fehlschlaegt
- Alle Schritte werden einzeln protokolliert
- Konfidenz aller Schritte wird gewichtet aggregiert
- Ergebnis wird in document_metadata gespeichert (kein separates Modell)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_log, safe_error_detail
from app.db.models import Document, ProcessingStatus
from app.services.events.event_bus import get_event_bus, EventType
from app.services.pipeline.document_pipeline_orchestrator import (
    DocumentPipelineOrchestrator,
    PipelineStatus,
)
from app.services.zero_touch.zero_touch_orchestrator import ZeroTouchOrchestrator

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

PIPELINE_CHAIN_TOTAL = Counter(
    "pipeline_chain_total",
    "Pipeline Chain Ausfuehrungen",
    ["result"],  # auto, review, failed
)

PIPELINE_CHAIN_DURATION = Histogram(
    "pipeline_chain_duration_ms",
    "Pipeline Chain Dauer in Millisekunden",
    buckets=[500, 1000, 2000, 5000, 10000, 30000, 60000],
)

PIPELINE_CHAIN_STEPS = Counter(
    "pipeline_chain_steps_total",
    "Pipeline Chain Steps",
    ["step", "result"],  # step: zero_touch/pipeline/kontierung/matching; result: success/skipped/failed
)


# =============================================================================
# Dokument-Typen fuer Kontierung und Matching
# =============================================================================

_KONTIERUNG_TYPES = frozenset({"invoice", "order", "offer"})
_MATCHING_TYPES = frozenset({"invoice", "delivery_note", "order"})

# Gewichtung der Schritte fuer Gesamt-Konfidenz
_CONFIDENCE_WEIGHTS: Dict[str, float] = {
    "zero_touch": 0.40,
    "pipeline": 0.30,
    "kontierung": 0.20,
    "matching": 0.10,
}


# =============================================================================
# Ergebnis-Datenklassen
# =============================================================================

@dataclass
class PipelineChainResult:
    """Gesamtergebnis der Pipeline-Chain."""

    document_id: UUID
    company_id: UUID
    success: bool
    auto_processed: bool  # True = zero-touch ohne manuelle Intervention abgeschlossen

    # Schritt-Ergebnisse
    zero_touch_completed: bool = False
    zero_touch_confidence: float = 0.0

    pipeline_status: str = PipelineStatus.PENDING.value
    pipeline_auto_processed: bool = False

    kontierung_completed: bool = False
    kontierung_confidence: float = 0.0
    journal_entry_id: Optional[UUID] = None

    matching_completed: bool = False
    matching_score: float = 0.0
    match_id: Optional[UUID] = None

    # Gesamt-Bewertung
    overall_confidence: float = 0.0
    requires_review: bool = False
    review_reasons: List[str] = field(default_factory=list)

    # Zeiterfassung
    total_duration_ms: int = 0
    step_durations: Dict[str, int] = field(default_factory=dict)

    # Fehler
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        """Serialisiert das Ergebnis als Dictionary fuer JSONB-Speicherung."""
        return {
            "document_id": str(self.document_id),
            "company_id": str(self.company_id),
            "success": self.success,
            "auto_processed": self.auto_processed,
            "zero_touch_completed": self.zero_touch_completed,
            "zero_touch_confidence": self.zero_touch_confidence,
            "pipeline_status": self.pipeline_status,
            "pipeline_auto_processed": self.pipeline_auto_processed,
            "kontierung_completed": self.kontierung_completed,
            "kontierung_confidence": self.kontierung_confidence,
            "journal_entry_id": str(self.journal_entry_id) if self.journal_entry_id else None,
            "matching_completed": self.matching_completed,
            "matching_score": self.matching_score,
            "match_id": str(self.match_id) if self.match_id else None,
            "overall_confidence": self.overall_confidence,
            "requires_review": self.requires_review,
            "review_reasons": self.review_reasons,
            "total_duration_ms": self.total_duration_ms,
            "step_durations": self.step_durations,
            "error": self.error,
        }


# =============================================================================
# Hilfsfunktionen
# =============================================================================

def _duration_ms(start: datetime) -> int:
    """Berechnet die Dauer in Millisekunden seit dem Startzeitpunkt."""
    delta = datetime.now(timezone.utc) - start
    return int(delta.total_seconds() * 1000)


def _make_error_result(
    document_id: UUID,
    company_id: UUID,
    error_message: str,
    duration_ms: int = 0,
) -> PipelineChainResult:
    """Erstellt ein Fehler-Ergebnis."""
    return PipelineChainResult(
        document_id=document_id,
        company_id=company_id,
        success=False,
        auto_processed=False,
        requires_review=True,
        review_reasons=[error_message],
        error=error_message,
        total_duration_ms=duration_ms,
    )


# =============================================================================
# Pipeline Chain Service
# =============================================================================

class PipelineChainService:
    """
    End-to-End Pipeline Chain.

    Orchestriert alle Verarbeitungsschritte in der richtigen Reihenfolge
    und aggregiert die Ergebnisse zu einem Gesamtbefund.

    Graceful Degradation: Ein fehlgeschlagener Schritt fuehrt nicht zum
    Abbruch der gesamten Pipeline, sondern wird als Review-Grund markiert.
    """

    # Konfidenz-Schwellwert fuer vollautomatische Verarbeitung
    AUTO_THRESHOLD = 0.85

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Pipeline Chain Service mit einer DB-Session."""
        self.db = db

    # =========================================================================
    # Oeffentliche Methoden
    # =========================================================================

    async def process_document(
        self,
        document_id: UUID,
        company_id: UUID,
        user_id: Optional[UUID] = None,
        skip_kontierung: bool = False,
        skip_matching: bool = False,
    ) -> PipelineChainResult:
        """
        Verarbeitet ein Dokument durch die komplette Pipeline-Chain.

        Schritte:
        1. Zero-Touch Processing (OCR-Check, Confidence, Business-Object, Ablage)
        2. Document Pipeline (Klassifizierung, Entity-Linking, Projekt, Kategorisierung, Anomalien)
        3. Auto-Kontierung (SKR03/04 Mapping, Journal-Buchung) - nur fuer relevante Typen
        4. 3-Way-Matching (Lieferschein/Bestellung/Rechnung) - nur fuer relevante Typen
        5. Abschlussbewertung und Event-Emission

        Args:
            document_id: ID des zu verarbeitenden Dokuments
            company_id: Mandant-ID (Multi-Tenant-Sicherheit)
            user_id: Optional - Ausfuehrender Benutzer
            skip_kontierung: Kontierungsschritt ueberspringen
            skip_matching: 3-Way-Matching-Schritt ueberspringen

        Returns:
            PipelineChainResult mit aggregierten Ergebnissen aller Schritte
        """
        chain_start = datetime.now(timezone.utc)
        step_durations: Dict[str, int] = {}
        review_reasons: List[str] = []

        logger.info(
            "pipeline_chain_started",
            document_id=str(document_id),
            company_id=str(company_id),
            user_id=str(user_id) if user_id else None,
        )

        # Schritt 1: Dokument aus DB laden (mit Tenant-Filter)
        document = await self._fetch_document(document_id, company_id)
        if document is None:
            duration = _duration_ms(chain_start)
            PIPELINE_CHAIN_TOTAL.labels(result="failed").inc()
            return _make_error_result(
                document_id=document_id,
                company_id=company_id,
                error_message="Dokument nicht gefunden",
                duration_ms=duration,
            )

        result = PipelineChainResult(
            document_id=document_id,
            company_id=company_id,
            success=False,
            auto_processed=False,
        )

        # Schritt 2: Zero-Touch Processing
        step_start = datetime.now(timezone.utc)
        try:
            zero_touch = ZeroTouchOrchestrator()
            zt_result = await zero_touch.process_document(document_id, company_id, self.db)
            result.zero_touch_completed = zt_result.success
            result.zero_touch_confidence = zt_result.overall_confidence
            PIPELINE_CHAIN_STEPS.labels(step="zero_touch", result="success").inc()
            logger.info(
                "pipeline_chain_zero_touch_done",
                document_id=str(document_id),
                confidence=zt_result.overall_confidence,
                auto_processable=zt_result.auto_processable,
            )
        except Exception as exc:
            safe_log = safe_error_log(exc, context="ZeroTouch")
            logger.error("pipeline_chain_zero_touch_failed", document_id=str(document_id), **safe_log)
            review_reasons.append(
                f"Zero-Touch fehlgeschlagen: {safe_error_detail(exc, 'ZeroTouch')}"
            )
            PIPELINE_CHAIN_STEPS.labels(step="zero_touch", result="failed").inc()
        step_durations["zero_touch"] = _duration_ms(step_start)

        # Schritt 3: Document Pipeline (Klassifizierung, Entity-Linking, etc.)
        step_start = datetime.now(timezone.utc)
        try:
            pipeline = DocumentPipelineOrchestrator(self.db)
            ocr_text = document.ocr_text or ""
            pl_result = await pipeline.process_document(
                document_id=document_id,
                ocr_text=ocr_text,
                company_id=company_id,
                user_id=user_id,
            )
            result.pipeline_status = pl_result.status.value
            result.pipeline_auto_processed = pl_result.auto_processed
            if pl_result.requires_review:
                review_reasons.extend(pl_result.review_reasons)
            PIPELINE_CHAIN_STEPS.labels(step="pipeline", result="success").inc()
            logger.info(
                "pipeline_chain_pipeline_done",
                document_id=str(document_id),
                status=pl_result.status.value,
                auto_processed=pl_result.auto_processed,
            )
        except Exception as exc:
            safe_log = safe_error_log(exc, context="DocumentPipeline")
            logger.error("pipeline_chain_pipeline_failed", document_id=str(document_id), **safe_log)
            review_reasons.append(
                f"Dokumenten-Pipeline fehlgeschlagen: {safe_error_detail(exc, 'Pipeline')}"
            )
            PIPELINE_CHAIN_STEPS.labels(step="pipeline", result="failed").inc()
        step_durations["pipeline"] = _duration_ms(step_start)

        # Schritt 4: Auto-Kontierung (nur fuer buchungsrelevante Dokument-Typen)
        doc_type = document.document_type or ""
        if not skip_kontierung and doc_type in _KONTIERUNG_TYPES:
            step_start = datetime.now(timezone.utc)
            try:
                from app.services.kontierung.auto_kontierung_service import AutoKontierungService
                kontierung_service = AutoKontierungService(self.db)
                extracted: Dict = (document.document_metadata or {}).get("extracted_fields", {})
                k_result = await kontierung_service.kontiere_document(
                    document_id=document_id,
                    company_id=company_id,
                    classification_type=doc_type,
                    extracted_fields=extracted,
                    entity_id=document.business_entity_id,
                    is_incoming=True,
                )
                result.kontierung_completed = k_result.success
                result.kontierung_confidence = k_result.confidence
                result.journal_entry_id = k_result.journal_entry_id
                if not k_result.success:
                    review_reasons.append(
                        f"Kontierung nicht erfolgreich: {k_result.explanation}"
                    )
                PIPELINE_CHAIN_STEPS.labels(step="kontierung", result="success").inc()
                logger.info(
                    "pipeline_chain_kontierung_done",
                    document_id=str(document_id),
                    success=k_result.success,
                    confidence=k_result.confidence,
                )
            except Exception as exc:
                safe_log = safe_error_log(exc, context="Kontierung")
                logger.error("pipeline_chain_kontierung_failed", document_id=str(document_id), **safe_log)
                review_reasons.append(
                    f"Kontierung fehlgeschlagen: {safe_error_detail(exc, 'Kontierung')}"
                )
                PIPELINE_CHAIN_STEPS.labels(step="kontierung", result="failed").inc()
            step_durations["kontierung"] = _duration_ms(step_start)
        elif skip_kontierung or doc_type not in _KONTIERUNG_TYPES:
            PIPELINE_CHAIN_STEPS.labels(step="kontierung", result="skipped").inc()

        # Schritt 5: 3-Way-Matching (nur fuer relevante Dokument-Typen)
        if not skip_matching and doc_type in _MATCHING_TYPES:
            step_start = datetime.now(timezone.utc)
            try:
                from app.services.matching.three_way_matching_service import ThreeWayMatchingService
                matcher = ThreeWayMatchingService(self.db)
                extracted_for_match: Dict = (document.document_metadata or {}).get("extracted_fields", {})
                m_result = await matcher.match_document(
                    document_id=document_id,
                    company_id=company_id,
                    document_type=doc_type,
                    reference_number=self._extract_reference(extracted_for_match),
                    amount=self._extract_amount(extracted_for_match),
                    vendor_entity_id=document.business_entity_id,
                    vendor_name=self._extract_vendor_name(extracted_for_match),
                    extracted_fields=extracted_for_match,
                )
                result.matching_completed = m_result.success
                result.matching_score = m_result.match_score
                result.match_id = m_result.match_id
                PIPELINE_CHAIN_STEPS.labels(step="matching", result="success").inc()
                logger.info(
                    "pipeline_chain_matching_done",
                    document_id=str(document_id),
                    success=m_result.success,
                    match_score=m_result.match_score,
                )
            except Exception as exc:
                safe_log = safe_error_log(exc, context="ThreeWayMatching")
                logger.error("pipeline_chain_matching_failed", document_id=str(document_id), **safe_log)
                review_reasons.append(
                    f"3-Way-Matching fehlgeschlagen: {safe_error_detail(exc, '3-Way-Matching')}"
                )
                PIPELINE_CHAIN_STEPS.labels(step="matching", result="failed").inc()
            step_durations["matching"] = _duration_ms(step_start)
        elif skip_matching or doc_type not in _MATCHING_TYPES:
            PIPELINE_CHAIN_STEPS.labels(step="matching", result="skipped").inc()

        # Schritt 6: Abschlussbewertung
        result.step_durations = step_durations
        result.total_duration_ms = _duration_ms(chain_start)
        result.review_reasons = review_reasons
        result.requires_review = len(review_reasons) > 0
        result.overall_confidence = self._calculate_overall_confidence(result)
        result.auto_processed = (
            result.overall_confidence >= self.AUTO_THRESHOLD
            and not result.requires_review
        )
        result.success = True

        # Ergebnis in document_metadata persistieren
        await self._store_chain_result(document, result)

        # Pipeline-Completed-Event emittieren
        await self._emit_pipeline_completed_event(result)

        # Prometheus Metriken aktualisieren
        label = "auto" if result.auto_processed else ("review" if result.requires_review else "manual")
        PIPELINE_CHAIN_TOTAL.labels(result=label).inc()
        PIPELINE_CHAIN_DURATION.observe(result.total_duration_ms)

        logger.info(
            "pipeline_chain_completed",
            document_id=str(document_id),
            company_id=str(company_id),
            auto_processed=result.auto_processed,
            overall_confidence=result.overall_confidence,
            requires_review=result.requires_review,
            total_duration_ms=result.total_duration_ms,
        )

        return result

    async def get_pipeline_status(
        self,
        document_id: UUID,
        company_id: UUID,
    ) -> Optional[PipelineChainResult]:
        """
        Gibt das gespeicherte Pipeline-Chain-Ergebnis fuer ein Dokument zurueck.

        Das Ergebnis wird aus dem JSONB-Feld document_metadata gelesen.

        Args:
            document_id: ID des Dokuments
            company_id: Mandant-ID (Multi-Tenant-Sicherheit)

        Returns:
            PipelineChainResult falls vorhanden, sonst None
        """
        document = await self._fetch_document(document_id, company_id)
        if document is None:
            return None

        metadata: Dict = document.document_metadata or {}
        chain_data: Optional[Dict] = metadata.get("pipeline_chain_result")
        if not chain_data:
            return None

        try:
            return self._result_from_dict(chain_data)
        except Exception as exc:
            safe_log = safe_error_log(exc, context="PipelineChainStatus")
            logger.warning(
                "pipeline_chain_result_parse_error",
                document_id=str(document_id),
                **safe_log,
            )
            return None

    async def retry_failed_step(
        self,
        document_id: UUID,
        company_id: UUID,
        step_name: str,
    ) -> PipelineChainResult:
        """
        Wiederholt einen einzelnen fehlgeschlagenen Schritt der Pipeline.

        Unterstuetzte Schritte: zero_touch, pipeline, kontierung, matching.
        Nach dem Wiederholungsversuch wird die komplette Pipeline neu gestartet,
        damit die Abhaengigkeiten zwischen den Schritten erhalten bleiben.

        Args:
            document_id: ID des Dokuments
            company_id: Mandant-ID
            step_name: Name des Schritts (zero_touch / pipeline / kontierung / matching)

        Returns:
            Neues PipelineChainResult nach dem Wiederholungsversuch
        """
        valid_steps = frozenset({"zero_touch", "pipeline", "kontierung", "matching"})
        if step_name not in valid_steps:
            return _make_error_result(
                document_id=document_id,
                company_id=company_id,
                error_message=f"Unbekannter Schritt: {step_name}. Gueltige Schritte: {', '.join(sorted(valid_steps))}",
            )

        logger.info(
            "pipeline_chain_retry_step",
            document_id=str(document_id),
            company_id=str(company_id),
            step_name=step_name,
        )

        # Pipeline vollstaendig neu ausfuehren; gezielte Schritt-Wiederholung
        # wuerde Abhaengigkeiten zwischen Schritten verletzen.
        return await self.process_document(
            document_id=document_id,
            company_id=company_id,
            skip_kontierung=(step_name not in {"kontierung"}),
            skip_matching=(step_name not in {"matching"}),
        )

    # =========================================================================
    # Private Hilfsmethoden
    # =========================================================================

    async def _fetch_document(
        self,
        document_id: UUID,
        company_id: UUID,
    ) -> Optional[Document]:
        """Laedt ein Dokument aus der DB mit Tenant-Filter."""
        stmt = select(Document).where(
            and_(
                Document.id == document_id,
                Document.company_id == company_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    def _calculate_overall_confidence(self, result: PipelineChainResult) -> float:
        """
        Berechnet den gewichteten Gesamt-Confidence-Score.

        Schritte ohne Ergebnis (nicht ausgefuehrt / fehlgeschlagen) erhalten 0.0.
        """
        weighted_sum = 0.0
        total_weight = 0.0

        if result.zero_touch_completed:
            w = _CONFIDENCE_WEIGHTS["zero_touch"]
            weighted_sum += result.zero_touch_confidence * w
            total_weight += w

        # Pipeline-Status: auto_completed = volle Konfidenz
        pipeline_confidence = 1.0 if result.pipeline_auto_processed else 0.5
        if result.pipeline_status not in (PipelineStatus.FAILED.value, PipelineStatus.PENDING.value):
            w = _CONFIDENCE_WEIGHTS["pipeline"]
            weighted_sum += pipeline_confidence * w
            total_weight += w

        if result.kontierung_completed:
            w = _CONFIDENCE_WEIGHTS["kontierung"]
            weighted_sum += result.kontierung_confidence * w
            total_weight += w

        if result.matching_completed:
            w = _CONFIDENCE_WEIGHTS["matching"]
            weighted_sum += result.matching_score * w
            total_weight += w

        if total_weight == 0.0:
            return 0.0

        return round(weighted_sum / total_weight, 4)

    def _extract_reference(self, extracted: Dict) -> Optional[str]:
        """Extrahiert die Referenznummer aus den extrahierten Feldern."""
        for key in ("invoice_number", "order_number", "reference_number", "belegnummer"):
            value = extracted.get(key)
            if value:
                return str(value)
        return None

    def _extract_amount(self, extracted: Dict) -> Optional[float]:
        """Extrahiert den Betrag aus den extrahierten Feldern."""
        for key in ("total_amount", "gross_amount", "amount", "betrag", "gesamtbetrag"):
            value = extracted.get(key)
            if value is not None:
                try:
                    return float(value)
                except (ValueError, TypeError):
                    continue
        return None

    def _extract_vendor_name(self, extracted: Dict) -> Optional[str]:
        """Extrahiert den Lieferantennamen aus den extrahierten Feldern."""
        for key in ("vendor_name", "supplier_name", "lieferant", "absender"):
            value = extracted.get(key)
            if value:
                return str(value)
        return None

    async def _store_chain_result(
        self,
        document: Document,
        result: PipelineChainResult,
    ) -> None:
        """Persistiert das Pipeline-Chain-Ergebnis im JSONB-Feld document_metadata."""
        try:
            metadata: Dict = dict(document.document_metadata or {})
            metadata["pipeline_chain_result"] = result.to_dict()
            metadata["pipeline_chain_completed_at"] = datetime.now(timezone.utc).isoformat()
            document.document_metadata = metadata

            if result.auto_processed:
                document.status = ProcessingStatus.COMPLETED

            await self.db.commit()
            logger.debug(
                "pipeline_chain_result_stored",
                document_id=str(result.document_id),
            )
        except Exception as exc:
            safe_log = safe_error_log(exc, context="PipelineChainStore")
            logger.error(
                "pipeline_chain_result_store_failed",
                document_id=str(result.document_id),
                **safe_log,
            )
            await self.db.rollback()

    async def _emit_pipeline_completed_event(self, result: PipelineChainResult) -> None:
        """Emittiert ein DOCUMENT_CATEGORIZED-Event nach Abschluss der Pipeline."""
        try:
            event_bus = get_event_bus()
            await event_bus.publish_event(
                event_type=EventType.DOCUMENT_CATEGORIZED,
                payload={
                    "document_id": str(result.document_id),
                    "company_id": str(result.company_id),
                    "auto_processed": result.auto_processed,
                    "overall_confidence": result.overall_confidence,
                    "requires_review": result.requires_review,
                    "pipeline_status": result.pipeline_status,
                    "kontierung_completed": result.kontierung_completed,
                    "matching_completed": result.matching_completed,
                    "total_duration_ms": result.total_duration_ms,
                },
                source="pipeline_chain_service",
            )
        except Exception as exc:
            safe_log = safe_error_log(exc, context="PipelineChainEvent")
            logger.warning(
                "pipeline_chain_event_emit_failed",
                document_id=str(result.document_id),
                **safe_log,
            )

    def _result_from_dict(self, data: Dict) -> PipelineChainResult:
        """Rekonstruiert ein PipelineChainResult aus einem Dictionary."""
        return PipelineChainResult(
            document_id=UUID(data["document_id"]),
            company_id=UUID(data["company_id"]),
            success=data.get("success", False),
            auto_processed=data.get("auto_processed", False),
            zero_touch_completed=data.get("zero_touch_completed", False),
            zero_touch_confidence=data.get("zero_touch_confidence", 0.0),
            pipeline_status=data.get("pipeline_status", PipelineStatus.PENDING.value),
            pipeline_auto_processed=data.get("pipeline_auto_processed", False),
            kontierung_completed=data.get("kontierung_completed", False),
            kontierung_confidence=data.get("kontierung_confidence", 0.0),
            journal_entry_id=UUID(data["journal_entry_id"]) if data.get("journal_entry_id") else None,
            matching_completed=data.get("matching_completed", False),
            matching_score=data.get("matching_score", 0.0),
            match_id=UUID(data["match_id"]) if data.get("match_id") else None,
            overall_confidence=data.get("overall_confidence", 0.0),
            requires_review=data.get("requires_review", False),
            review_reasons=data.get("review_reasons", []),
            total_duration_ms=data.get("total_duration_ms", 0),
            step_durations=data.get("step_durations", {}),
            error=data.get("error"),
        )
