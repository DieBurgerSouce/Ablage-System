# -*- coding: utf-8 -*-
"""
Scan-to-Buchung Workflow Orchestrator.

End-to-End Pipeline fuer automatische Buchung gescannter Rechnungen:
1. Dokument laden und pruefen (Rechnungstyp)
2. Buchungsvorschlag generieren (Konto/Gegenkonto via BookingSuggestionService)
3. Plausibilitaetspruefung (PlausibilityService.evaluate_all)
4. Routing: auto_book / review / manual
5. Bei auto_book: DATEV-Buchung erstellen und pushen
6. Zero-Touch-Metriken tracken

Feinpoliert und durchdacht - Automatische Buchung mit Sicherheitsnetz.
"""

import time
import threading
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import select, and_, func, extract, cast
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log, safe_error_detail
from app.db.models import Document, DocumentType, ProcessingStatus
from app.services.datev.booking_suggestion_service import (
    BookingSuggestionService,
    BookingSuggestion,
)
from app.services.datev.plausibility_service import (
    PlausibilityService,
    PlausibilityResult,
    get_plausibility_service,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class BookingResult:
    """Ergebnis eines Buchungsvorgangs."""

    document_id: UUID
    routing: str  # "auto_book", "review", "manual"
    success: bool
    datev_booking_id: Optional[str]
    booking_suggestion: Optional[Dict[str, object]]
    plausibility_score: float
    reason: str  # Deutsche Erklaerung
    processing_time_ms: int


@dataclass
class ZeroTouchStats:
    """Zero-Touch-Buchungsquote und Statistiken."""

    total_processed: int
    auto_booked: int
    review_queue: int
    manual: int
    zero_touch_quote: float  # 0.0-1.0
    top_failure_reasons: List[Tuple[str, int]]  # (reason, count)
    trend_7d: Optional[float]  # Quote-Aenderung ueber die letzten 7 Tage


# Invoice document types for auto-booking
_INVOICE_TYPES = frozenset({
    DocumentType.INVOICE,
    "invoice",
    "eingangsrechnung",
    "ausgangsrechnung",
})


# =============================================================================
# ORCHESTRATOR SERVICE
# =============================================================================


class ScanToBookingOrchestrator:
    """
    Orchestriert den Scan-to-Buchung Workflow.

    Verbindet OCR-Pipeline, Buchungsvorschlaege, Plausibilitaetspruefung
    und DATEV-Export zu einem automatisierten End-to-End Prozess.

    Usage:
        orchestrator = ScanToBookingOrchestrator()
        result = await orchestrator.process_document_for_booking(
            document_id=doc_id,
            company_id=company_uuid,
            db=session,
        )
        if result.routing == "auto_book" and result.success:
            # Buchung wurde automatisch erstellt
            ...
    """

    def __init__(self, skr_type: str = "skr03") -> None:
        self._skr_type = skr_type.lower()
        self._booking_service = BookingSuggestionService(kontenrahmen=self._skr_type)
        self._plausibility_service = get_plausibility_service(skr_type=self._skr_type)

    # =========================================================================
    # MAIN PIPELINE
    # =========================================================================

    async def process_document_for_booking(
        self,
        document_id: UUID,
        company_id: UUID,
        db: AsyncSession,
    ) -> BookingResult:
        """
        Verarbeitet ein Dokument fuer automatische Buchung.

        Pipeline:
        1. Dokument laden und Typ pruefen
        2. Buchungsvorschlag generieren
        3. Plausibilitaetspruefung
        4. Routing (auto_book / review / manual)
        5. Bei auto_book: DATEV-Buchung erstellen
        6. Status aktualisieren

        Args:
            document_id: Dokument-ID
            company_id: Mandanten-ID
            db: Datenbank-Session

        Returns:
            BookingResult mit Ergebnis
        """
        start_time = time.monotonic()

        try:
            # 1. Dokument laden
            document = await self._load_document(document_id, company_id, db)
            if document is None:
                return BookingResult(
                    document_id=document_id,
                    routing="manual",
                    success=False,
                    datev_booking_id=None,
                    booking_suggestion=None,
                    plausibility_score=0.0,
                    reason="Dokument nicht gefunden",
                    processing_time_ms=self._elapsed_ms(start_time),
                )

            # 2. Rechnungstyp pruefen
            if not self._is_invoice_type(document):
                return BookingResult(
                    document_id=document_id,
                    routing="manual",
                    success=False,
                    datev_booking_id=None,
                    booking_suggestion=None,
                    plausibility_score=0.0,
                    reason="Kein Rechnungsdokument - automatische Buchung nicht moeglich",
                    processing_time_ms=self._elapsed_ms(start_time),
                )

            # 3. Extrahierte Daten pruefen
            extracted_data = document.extracted_data or {}
            extracted_text = document.extracted_text or ""

            if not extracted_data and not extracted_text:
                return BookingResult(
                    document_id=document_id,
                    routing="manual",
                    success=False,
                    datev_booking_id=None,
                    booking_suggestion=None,
                    plausibility_score=0.0,
                    reason="Keine extrahierten Daten vorhanden - OCR noch nicht abgeschlossen",
                    processing_time_ms=self._elapsed_ms(start_time),
                )

            # 4. Buchungsvorschlag generieren
            entity_name: Optional[str] = None
            entity_id: Optional[UUID] = None
            if document.business_entity_id is not None:
                entity_id = document.business_entity_id
                entity_name = await self._get_entity_name(entity_id, company_id, db)

            suggestion = self._booking_service.suggest_booking(
                ocr_text=extracted_text,
                extracted_data=extracted_data,
                document_type=document.document_type,
                entity_name=entity_name,
                entity_id=entity_id,
            )

            suggestion_dict = self._suggestion_to_dict(suggestion)

            # 5. Plausibilitaetspruefung
            # Konten aus Suggestion in extracted_data einfuegen fuer Kontierungspruefung
            plausibility_data = dict(extracted_data)
            plausibility_data.setdefault("konto", suggestion.sollkonto)
            plausibility_data.setdefault("gegenkonto", suggestion.habenkonto)

            plausibility_result = await self._plausibility_service.evaluate_all(
                extracted_data=plausibility_data,
                company_id=company_id,
                entity_id=entity_id,
                db=db,
                confidence=suggestion.confidence,
            )

            # 6. Routing
            routing = plausibility_result.routing
            if routing is None:
                routing_decision = "manual"
                routing_reason = "Plausibilitaetspruefung konnte kein Routing bestimmen"
            else:
                routing_decision = routing.routing
                routing_reason = routing.reason

            overall_score = plausibility_result.overall_score

            logger.info(
                "scan_to_booking_routing",
                document_id=str(document_id),
                routing=routing_decision,
                plausibility_score=round(overall_score, 3),
                suggestion_confidence=suggestion.confidence,
                checks_passed=routing.checks_passed if routing else 0,
                checks_failed=routing.checks_failed if routing else 0,
            )

            # 7. Aktion basierend auf Routing
            datev_booking_id: Optional[str] = None
            success = True

            if routing_decision == "auto_book":
                booking_result = await self._auto_book(
                    document=document,
                    suggestion=suggestion,
                    company_id=company_id,
                    db=db,
                )
                datev_booking_id = booking_result
                success = datev_booking_id is not None
                if not success:
                    routing_decision = "review"
                    routing_reason = (
                        "Automatische Buchung fehlgeschlagen - "
                        "zur manuellen Pruefung weitergeleitet"
                    )
            elif routing_decision == "review":
                await self._create_review_entry(
                    document=document,
                    suggestion=suggestion,
                    plausibility_result=plausibility_result,
                    db=db,
                )

            # 8. Booking-Metadaten im Dokument speichern
            await self._update_document_booking_metadata(
                document=document,
                routing=routing_decision,
                suggestion=suggestion,
                plausibility_score=overall_score,
                datev_booking_id=datev_booking_id,
                db=db,
            )

            return BookingResult(
                document_id=document_id,
                routing=routing_decision,
                success=success,
                datev_booking_id=datev_booking_id,
                booking_suggestion=suggestion_dict,
                plausibility_score=overall_score,
                reason=routing_reason,
                processing_time_ms=self._elapsed_ms(start_time),
            )

        except Exception as e:
            logger.error(
                "scan_to_booking_error",
                document_id=str(document_id),
                **safe_error_log(e),
            )
            return BookingResult(
                document_id=document_id,
                routing="manual",
                success=False,
                datev_booking_id=None,
                booking_suggestion=None,
                plausibility_score=0.0,
                reason=safe_error_detail(e, "Buchungsverarbeitung"),
                processing_time_ms=self._elapsed_ms(start_time),
            )

    # =========================================================================
    # AUTO-BOOK
    # =========================================================================

    async def _auto_book(
        self,
        document: Document,
        suggestion: BookingSuggestion,
        company_id: UUID,
        db: AsyncSession,
    ) -> Optional[str]:
        """
        Erstellt eine DATEV-Buchung und pusht sie.

        Args:
            document: Quelldokument
            suggestion: Buchungsvorschlag
            company_id: Mandanten-ID
            db: Datenbank-Session

        Returns:
            Buchungs-ID oder None bei Fehler
        """
        try:
            from app.db.models_datev import DATEVBuchung, DATEVConnection

            # Aktive DATEV-Connection fuer Mandant laden
            conn_result = await db.execute(
                select(DATEVConnection).where(
                    and_(
                        DATEVConnection.company_id == company_id,
                        DATEVConnection.is_active.is_(True),
                        DATEVConnection.connection_status == "connected",
                    )
                ).limit(1)
            )
            connection = conn_result.scalar_one_or_none()

            if connection is None:
                logger.warning(
                    "auto_book_no_connection",
                    company_id=str(company_id),
                )
                return None

            # Buchungssatz erstellen
            betrag = float(suggestion.betrag) if suggestion.betrag else 0.0
            buchung = DATEVBuchung(
                id=uuid.uuid4(),
                connection_id=connection.id,
                document_id=document.id,
                entity_id=document.business_entity_id,
                belegdatum=suggestion.belegdatum,
                buchungsdatum=date.today(),
                betrag_soll=betrag,
                betrag_haben=betrag,
                konto_soll=suggestion.sollkonto,
                konto_haben=suggestion.habenkonto,
                steuerschluessel=suggestion.steuercode,
                buchungstext=suggestion.buchungstext[:120] if suggestion.buchungstext else None,
                belegnummer=suggestion.rechnungsnummer,
                kostenstelle_1=suggestion.kostenstelle,
                sync_status="pending",
            )

            db.add(buchung)
            await db.flush()

            logger.info(
                "auto_book_created",
                buchung_id=str(buchung.id),
                document_id=str(document.id),
                konto_soll=suggestion.sollkonto,
                konto_haben=suggestion.habenkonto,
                betrag=betrag,
            )

            return str(buchung.id)

        except Exception as e:
            logger.error(
                "auto_book_error",
                document_id=str(document.id),
                **safe_error_log(e),
            )
            return None

    # =========================================================================
    # REVIEW ENTRY
    # =========================================================================

    async def _create_review_entry(
        self,
        document: Document,
        suggestion: BookingSuggestion,
        plausibility_result: PlausibilityResult,
        db: AsyncSession,
    ) -> None:
        """
        Erstellt einen Review-Eintrag in den Dokument-Metadaten.

        Speichert Buchungsvorschlag und Pruefungsergebnisse im Dokument,
        damit ein Sachbearbeiter die Buchung pruefen und bestaetigen kann.

        Args:
            document: Quelldokument
            suggestion: Buchungsvorschlag
            plausibility_result: Plausibilitaetsergebnis
            db: Datenbank-Session
        """
        try:
            warnings: List[str] = []
            for check in plausibility_result.checks:
                if not check.passed:
                    warnings.append(check.message)

            review_data: Dict[str, object] = {
                "review_status": "pending",
                "review_created_at": utc_now().isoformat(),
                "suggested_booking": self._suggestion_to_dict(suggestion),
                "plausibility_warnings": warnings,
                "plausibility_score": plausibility_result.overall_score,
                "review_reason": (
                    plausibility_result.routing.reason
                    if plausibility_result.routing
                    else "Pruefung erforderlich"
                ),
            }

            metadata = dict(document.document_metadata or {})
            metadata["booking_review"] = review_data
            document.document_metadata = metadata

            logger.info(
                "review_entry_created",
                document_id=str(document.id),
                warnings_count=len(warnings),
            )

        except Exception as e:
            logger.error(
                "review_entry_error",
                document_id=str(document.id),
                **safe_error_log(e),
            )

    # =========================================================================
    # ZERO-TOUCH STATS
    # =========================================================================

    async def get_zero_touch_stats(
        self,
        company_id: UUID,
        period_days: int,
        db: AsyncSession,
    ) -> ZeroTouchStats:
        """
        Berechnet Zero-Touch-Buchungsstatistiken.

        Args:
            company_id: Mandanten-ID
            period_days: Zeitraum in Tagen
            db: Datenbank-Session

        Returns:
            ZeroTouchStats mit Quote und Aufschluesselung
        """
        try:
            cutoff = utc_now() - timedelta(days=period_days)

            # Dokumente mit Booking-Metadaten laden
            result = await db.execute(
                select(
                    Document.document_metadata,
                ).where(
                    and_(
                        Document.company_id == company_id,
                        Document.deleted_at.is_(None),
                        Document.document_type.in_([
                            DocumentType.INVOICE,
                            "invoice",
                        ]),
                        Document.created_at >= cutoff,
                        cast(Document.document_metadata, JSONB)["booking_routing"].astext.isnot(None),
                    )
                )
            )
            rows = result.scalars().all()

            auto_booked = 0
            review_queue = 0
            manual = 0
            failure_reasons: Dict[str, int] = {}

            for metadata in rows:
                if not metadata:
                    continue
                routing = (metadata.get("booking_routing") or "manual")
                if routing == "auto_book":
                    auto_booked += 1
                elif routing == "review":
                    review_queue += 1
                else:
                    manual += 1

                # Fehlergrund tracken
                reason = metadata.get("booking_reason", "Unbekannt")
                if routing != "auto_book":
                    failure_reasons[reason] = failure_reasons.get(reason, 0) + 1

            total = auto_booked + review_queue + manual
            quote = auto_booked / total if total > 0 else 0.0

            # Top-Fehlergruende sortiert
            top_reasons = sorted(
                failure_reasons.items(),
                key=lambda x: x[1],
                reverse=True,
            )[:10]

            # 7-Tage-Trend berechnen
            trend_7d = await self._calculate_trend(company_id, db)

            return ZeroTouchStats(
                total_processed=total,
                auto_booked=auto_booked,
                review_queue=review_queue,
                manual=manual,
                zero_touch_quote=round(quote, 4),
                top_failure_reasons=top_reasons,
                trend_7d=trend_7d,
            )

        except Exception as e:
            logger.error(
                "zero_touch_stats_error",
                company_id=str(company_id),
                **safe_error_log(e),
            )
            return ZeroTouchStats(
                total_processed=0,
                auto_booked=0,
                review_queue=0,
                manual=0,
                zero_touch_quote=0.0,
                top_failure_reasons=[],
                trend_7d=None,
            )

    # =========================================================================
    # BATCH PROCESSING
    # =========================================================================

    async def batch_process_unbooked(
        self,
        company_id: UUID,
        batch_size: int,
        db: AsyncSession,
    ) -> Dict[str, int]:
        """
        Verarbeitet einen Batch unbuchter Rechnungen.

        Findet OCR-fertige Rechnungen ohne Buchungs-Routing und
        verarbeitet sie durch die Pipeline.

        Args:
            company_id: Mandanten-ID
            batch_size: Maximale Anzahl zu verarbeitender Dokumente
            db: Datenbank-Session

        Returns:
            Statistik: {auto_booked, review, manual, errors}
        """
        stats = {"auto_booked": 0, "review": 0, "manual": 0, "errors": 0}

        try:
            # Unverarbeitete Rechnungen finden
            result = await db.execute(
                select(Document.id).where(
                    and_(
                        Document.company_id == company_id,
                        Document.deleted_at.is_(None),
                        Document.document_type.in_([
                            DocumentType.INVOICE,
                            "invoice",
                        ]),
                        Document.status == ProcessingStatus.COMPLETED,
                        # Noch kein Booking-Routing gesetzt
                        cast(Document.document_metadata, JSONB)["booking_routing"].astext.is_(None),
                    )
                ).limit(batch_size)
            )
            document_ids = [row[0] for row in result.all()]

            logger.info(
                "batch_process_start",
                company_id=str(company_id),
                batch_size=batch_size,
                found=len(document_ids),
            )

            for doc_id in document_ids:
                try:
                    booking_result = await self.process_document_for_booking(
                        document_id=doc_id,
                        company_id=company_id,
                        db=db,
                    )
                    if booking_result.routing == "auto_book" and booking_result.success:
                        stats["auto_booked"] += 1
                    elif booking_result.routing == "review":
                        stats["review"] += 1
                    else:
                        stats["manual"] += 1

                    # Commit nach jedem Dokument (Isolation)
                    await db.commit()
                except Exception as e:
                    stats["errors"] += 1
                    await db.rollback()
                    logger.warning(
                        "batch_process_doc_error",
                        document_id=str(doc_id),
                        **safe_error_log(e),
                    )

            logger.info(
                "batch_process_complete",
                company_id=str(company_id),
                **stats,
            )

        except Exception as e:
            logger.error(
                "batch_process_error",
                company_id=str(company_id),
                **safe_error_log(e),
            )

        return stats

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    async def _load_document(
        self,
        document_id: UUID,
        company_id: UUID,
        db: AsyncSession,
    ) -> Optional[Document]:
        """Laedt ein Dokument mit Mandanten-Isolation."""
        result = await db.execute(
            select(Document).where(
                and_(
                    Document.id == document_id,
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                )
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _is_invoice_type(document: Document) -> bool:
        """Prueft ob ein Dokument ein Rechnungstyp ist."""
        doc_type = (document.document_type or "").lower()
        return doc_type in _INVOICE_TYPES or "rechnung" in doc_type

    async def _get_entity_name(
        self,
        entity_id: UUID,
        company_id: UUID,
        db: AsyncSession,
    ) -> Optional[str]:
        """Laedt den Entity-Namen."""
        from app.db.models import BusinessEntity

        result = await db.execute(
            select(BusinessEntity.name).where(
                and_(
                    BusinessEntity.id == entity_id,
                    BusinessEntity.company_id == company_id,
                )
            )
        )
        row = result.scalar_one_or_none()
        return str(row) if row else None

    @staticmethod
    def _suggestion_to_dict(suggestion: BookingSuggestion) -> Dict[str, object]:
        """Konvertiert einen BookingSuggestion zu einem Dict."""
        return {
            "belegart": suggestion.belegart,
            "belegdatum": suggestion.belegdatum.isoformat(),
            "buchungstext": suggestion.buchungstext,
            "betrag": str(suggestion.betrag),
            "sollkonto": suggestion.sollkonto,
            "habenkonto": suggestion.habenkonto,
            "sollkonto_name": suggestion.sollkonto_name,
            "habenkonto_name": suggestion.habenkonto_name,
            "steuercode": suggestion.steuercode,
            "steuersatz": suggestion.steuersatz,
            "rechnungsnummer": suggestion.rechnungsnummer,
            "kostenstelle": suggestion.kostenstelle,
            "confidence": suggestion.confidence,
        }

    async def _update_document_booking_metadata(
        self,
        document: Document,
        routing: str,
        suggestion: BookingSuggestion,
        plausibility_score: float,
        datev_booking_id: Optional[str],
        db: AsyncSession,
    ) -> None:
        """Speichert Buchungsergebnis in Dokument-Metadaten."""
        try:
            metadata = dict(document.document_metadata or {})
            metadata["booking_routing"] = routing
            metadata["booking_reason"] = (
                f"Konfidenz {suggestion.confidence:.0%}, "
                f"Plausibilitaet {plausibility_score:.0%}"
            )
            metadata["booking_processed_at"] = utc_now().isoformat()
            metadata["booking_confidence"] = suggestion.confidence
            metadata["booking_plausibility_score"] = plausibility_score

            if datev_booking_id:
                metadata["datev_booking_id"] = datev_booking_id

            document.document_metadata = metadata
        except Exception as e:
            logger.warning(
                "update_booking_metadata_error",
                document_id=str(document.id),
                **safe_error_log(e),
            )

    async def _calculate_trend(
        self,
        company_id: UUID,
        db: AsyncSession,
    ) -> Optional[float]:
        """Berechnet 7-Tage-Trend der Zero-Touch-Quote."""
        try:
            now = utc_now()
            period_current = now - timedelta(days=7)
            period_previous = now - timedelta(days=14)

            async def _count_by_period(
                start: datetime,
                end: datetime,
            ) -> Tuple[int, int]:
                result = await db.execute(
                    select(
                        Document.document_metadata,
                    ).where(
                        and_(
                            Document.company_id == company_id,
                            Document.deleted_at.is_(None),
                            Document.document_type.in_([
                                DocumentType.INVOICE,
                                "invoice",
                            ]),
                            Document.created_at >= start,
                            Document.created_at < end,
                            cast(Document.document_metadata, JSONB)["booking_routing"].astext.isnot(None),
                        )
                    )
                )
                rows = result.scalars().all()
                total = len(rows)
                auto = sum(
                    1 for m in rows
                    if m and m.get("booking_routing") == "auto_book"
                )
                return total, auto

            total_current, auto_current = await _count_by_period(period_current, now)
            total_previous, auto_previous = await _count_by_period(period_previous, period_current)

            if total_current == 0 or total_previous == 0:
                return None

            quote_current = auto_current / total_current
            quote_previous = auto_previous / total_previous
            return round(quote_current - quote_previous, 4)

        except Exception:
            return None

    @staticmethod
    def _elapsed_ms(start_time: float) -> int:
        """Berechnet verstrichene Zeit in Millisekunden."""
        return int((time.monotonic() - start_time) * 1000)


# =============================================================================
# SINGLETON
# =============================================================================

_orchestrator: Optional[ScanToBookingOrchestrator] = None
_orchestrator_lock = threading.Lock()


def get_scan_to_booking_orchestrator(
    skr_type: str = "skr03",
) -> ScanToBookingOrchestrator:
    """
    Factory fuer ScanToBookingOrchestrator (Thread-Safe Singleton).

    Args:
        skr_type: Kontenrahmen-Typ

    Returns:
        ScanToBookingOrchestrator Instanz
    """
    global _orchestrator
    if _orchestrator is None:
        with _orchestrator_lock:
            if _orchestrator is None:
                _orchestrator = ScanToBookingOrchestrator(skr_type=skr_type)
    return _orchestrator
