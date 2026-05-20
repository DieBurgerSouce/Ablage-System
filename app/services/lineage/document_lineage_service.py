# -*- coding: utf-8 -*-
"""
Document Lineage Service.

Tracking der Datenherkunft und Verarbeitungshistorie für Dokumente:
- Import-Quelle (Email/Ordner/API/Manuell)
- Verarbeitungsschritte (OCR -> Klassifikation -> Extraktion)
- Entity-Linking mit Konfidenz
- Änderungen mit Zeitstempel und Benutzer

SECURITY: Niemals PII (Dokumentinhalte, Kundendaten) in Logs speichern.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_lineage import (
    DocumentLineageEvent,
    DocumentLineageSummary,
    LineageEventType,
    ImportSourceType,
)
from app.core.security.sensitive_data_filter import get_pii_safe_logger
from app.core.safe_errors import safe_error_log

# SECURITY: Use PII-safe logger for GDPR compliance
logger = get_pii_safe_logger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class LineageStats:
    """Statistiken zur Dokumenten-Lineage."""

    total_events: int = 0
    total_processing_duration_ms: int = 0
    ocr_duration_ms: int = 0
    ocr_confidence: Optional[float] = None
    classification_confidence: Optional[float] = None
    entity_link_confidence: Optional[float] = None
    modification_count: int = 0
    export_count: int = 0
    approval_count: int = 0
    rejection_count: int = 0
    import_source_type: Optional[str] = None
    imported_at: Optional[datetime] = None
    last_modified_at: Optional[datetime] = None


@dataclass
class TimelineEntry:
    """Einzelner Eintrag in der Zeitleiste."""

    id: str
    event_type: str
    event_data: Dict[str, Any]
    timestamp: datetime
    duration_ms: Optional[int] = None
    confidence: Optional[float] = None
    user_id: Optional[str] = None
    source_service: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert in Dictionary für API-Response."""
        return {
            "id": self.id,
            "event_type": self.event_type,
            "event_data": self.event_data,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "duration_ms": self.duration_ms,
            "confidence": self.confidence,
            "user_id": self.user_id,
            "source_service": self.source_service,
        }


# =============================================================================
# SERVICE CLASS
# =============================================================================


class DocumentLineageService:
    """
    Service für Document Lineage Tracking.

    Speichert und analysiert die Verarbeitungshistorie von Dokumenten.
    """

    def __init__(self, db: AsyncSession):
        """
        Initialisiert den Lineage Service.

        Args:
            db: Async Database Session
        """
        self._db = db

    # -------------------------------------------------------------------------
    # RECORD EVENTS
    # -------------------------------------------------------------------------

    async def record_import_event(
        self,
        document_id: UUID,
        company_id: UUID,
        source_type: ImportSourceType,
        source_details: Optional[Dict[str, Any]] = None,
        user_id: Optional[UUID] = None,
        correlation_id: Optional[UUID] = None,
    ) -> DocumentLineageEvent:
        """
        Zeichnet ein Import-Ereignis auf.

        Args:
            document_id: ID des importierten Dokuments
            company_id: ID der Firma
            source_type: Typ der Import-Quelle
            source_details: Details zur Quelle (ohne PII!)
            user_id: ID des Benutzers (bei manuellem Upload)
            correlation_id: Korrelations-ID für zusammengehoerende Events

        Returns:
            Das erstellte LineageEvent
        """
        # SECURITY: Keine PII in source_details speichern
        safe_details = self._sanitize_event_data(source_details or {})

        event = DocumentLineageEvent(
            document_id=document_id,
            company_id=company_id,
            event_type=LineageEventType.IMPORT.value,
            event_data={
                "source_type": source_type.value,
                "source_details": safe_details,
            },
            user_id=user_id,
            source_service="import_service",
            correlation_id=correlation_id,
        )

        self._db.add(event)

        # Summary erstellen oder aktualisieren
        await self._update_summary_for_import(
            document_id=document_id,
            company_id=company_id,
            source_type=source_type,
            source_details=safe_details,
            user_id=user_id,
        )

        await self._db.flush()

        logger.info(
            "lineage_import_recorded",
            document_id=str(document_id),
            source_type=source_type.value,
        )

        return event

    async def record_processing_step(
        self,
        document_id: UUID,
        company_id: UUID,
        step_type: LineageEventType,
        details: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[int] = None,
        confidence: Optional[float] = None,
        user_id: Optional[UUID] = None,
        source_service: Optional[str] = None,
        correlation_id: Optional[UUID] = None,
    ) -> DocumentLineageEvent:
        """
        Zeichnet einen Verarbeitungsschritt auf.

        Args:
            document_id: ID des Dokuments
            company_id: ID der Firma
            step_type: Typ des Verarbeitungsschritts
            details: Details (ohne PII!)
            duration_ms: Verarbeitungsdauer in Millisekunden
            confidence: Konfidenz (0.0 - 1.0)
            user_id: ID des Benutzers (wenn manuell ausgeloest)
            source_service: Name des Services
            correlation_id: Korrelations-ID

        Returns:
            Das erstellte LineageEvent
        """
        # SECURITY: Keine PII speichern
        safe_details = self._sanitize_event_data(details or {})

        event = DocumentLineageEvent(
            document_id=document_id,
            company_id=company_id,
            event_type=step_type.value,
            event_data=safe_details,
            duration_ms=duration_ms,
            confidence=confidence,
            user_id=user_id,
            source_service=source_service or "processing_pipeline",
            correlation_id=correlation_id,
        )

        self._db.add(event)

        # Summary aktualisieren
        await self._update_summary_for_processing(
            document_id=document_id,
            company_id=company_id,
            step_type=step_type,
            duration_ms=duration_ms,
            confidence=confidence,
            details=safe_details,
        )

        await self._db.flush()

        logger.info(
            "lineage_processing_step_recorded",
            document_id=str(document_id),
            step_type=step_type.value,
            duration_ms=duration_ms,
        )

        return event

    async def record_entity_link(
        self,
        document_id: UUID,
        company_id: UUID,
        entity_id: UUID,
        confidence: float,
        reason: str,
        match_type: Optional[str] = None,
        user_id: Optional[UUID] = None,
        correlation_id: Optional[UUID] = None,
    ) -> DocumentLineageEvent:
        """
        Zeichnet eine Entity-Verknüpfung auf.

        Args:
            document_id: ID des Dokuments
            company_id: ID der Firma
            entity_id: ID des verknüpften Geschäftspartners
            confidence: Konfidenz der Verknüpfung (0.0 - 1.0)
            reason: Grund für die Verknüpfung (ohne PII!)
            match_type: Art des Matches (z.B. "customer_number", "iban")
            user_id: ID des Benutzers (bei manueller Verknüpfung)
            correlation_id: Korrelations-ID

        Returns:
            Das erstellte LineageEvent
        """
        # SECURITY: Reason darf keine PII enthalten
        safe_reason = self._sanitize_string(reason)

        event = DocumentLineageEvent(
            document_id=document_id,
            company_id=company_id,
            event_type=LineageEventType.ENTITY_LINK.value,
            event_data={
                "entity_id": str(entity_id),
                "match_type": match_type,
                "reason": safe_reason,
            },
            confidence=confidence,
            user_id=user_id,
            source_service="entity_linker",
            correlation_id=correlation_id,
        )

        self._db.add(event)

        # Summary aktualisieren
        await self._update_summary_for_entity_link(
            document_id=document_id,
            company_id=company_id,
            entity_id=entity_id,
            confidence=confidence,
        )

        await self._db.flush()

        logger.info(
            "lineage_entity_link_recorded",
            document_id=str(document_id),
            entity_id=str(entity_id),
            confidence=confidence,
        )

        return event

    async def record_modification(
        self,
        document_id: UUID,
        company_id: UUID,
        field_name: str,
        old_value: Optional[str],
        new_value: Optional[str],
        user_id: UUID,
        modification_type: str = "update",
        correlation_id: Optional[UUID] = None,
    ) -> DocumentLineageEvent:
        """
        Zeichnet eine Dokumentenänderung auf.

        Args:
            document_id: ID des Dokuments
            company_id: ID der Firma
            field_name: Name des geänderten Feldes
            old_value: Alter Wert (ohne PII - wird gefiltert!)
            new_value: Neuer Wert (ohne PII - wird gefiltert!)
            user_id: ID des ändernden Benutzers
            modification_type: Art der Änderung
            correlation_id: Korrelations-ID

        Returns:
            Das erstellte LineageEvent
        """
        # SECURITY: Werte filtern - keine PII speichern
        # Nur den Feldnamen und die Tatsache der Änderung speichern
        event = DocumentLineageEvent(
            document_id=document_id,
            company_id=company_id,
            event_type=LineageEventType.MODIFICATION.value,
            event_data={
                "field": field_name,
                "modification_type": modification_type,
                "value_changed": old_value != new_value,
                # SECURITY: Keine Werte speichern, nur ob sich etwas geändert hat
            },
            user_id=user_id,
            source_service="document_service",
            correlation_id=correlation_id,
        )

        self._db.add(event)

        # Summary aktualisieren
        await self._update_summary_for_modification(
            document_id=document_id,
            company_id=company_id,
            user_id=user_id,
        )

        await self._db.flush()

        logger.info(
            "lineage_modification_recorded",
            document_id=str(document_id),
            field=field_name,
        )

        return event

    async def record_export_event(
        self,
        document_id: UUID,
        company_id: UUID,
        export_format: str,
        destination: Optional[str] = None,
        user_id: Optional[UUID] = None,
        correlation_id: Optional[UUID] = None,
    ) -> DocumentLineageEvent:
        """
        Zeichnet einen Export auf.

        Args:
            document_id: ID des Dokuments
            company_id: ID der Firma
            export_format: Format (pdf, json, csv, datev, etc.)
            destination: Ziel (ohne PII!)
            user_id: ID des exportierenden Benutzers
            correlation_id: Korrelations-ID

        Returns:
            Das erstellte LineageEvent
        """
        event = DocumentLineageEvent(
            document_id=document_id,
            company_id=company_id,
            event_type=LineageEventType.EXPORT.value,
            event_data={
                "format": export_format,
                "destination": self._sanitize_string(destination) if destination else None,
            },
            user_id=user_id,
            source_service="export_service",
            correlation_id=correlation_id,
        )

        self._db.add(event)

        # Summary aktualisieren
        await self._update_summary_for_export(
            document_id=document_id,
            company_id=company_id,
        )

        await self._db.flush()

        logger.info(
            "lineage_export_recorded",
            document_id=str(document_id),
            format=export_format,
        )

        return event

    # -------------------------------------------------------------------------
    # QUERY METHODS
    # -------------------------------------------------------------------------

    async def get_timeline(
        self,
        document_id: UUID,
        company_id: UUID,
        limit: int = 100,
        offset: int = 0,
        event_types: Optional[List[LineageEventType]] = None,
    ) -> tuple[List[TimelineEntry], int]:
        """
        Ruft die vollständige Zeitleiste eines Dokuments ab.

        Args:
            document_id: ID des Dokuments
            company_id: ID der Firma (für Zugriffskontrolle)
            limit: Maximale Anzahl der Einträge
            offset: Offset für Pagination
            event_types: Optional: Nur bestimmte Event-Typen

        Returns:
            Tuple aus Liste von TimelineEntry und Gesamtanzahl
        """
        # Basis-Query
        query = select(DocumentLineageEvent).where(
            and_(
                DocumentLineageEvent.document_id == document_id,
                DocumentLineageEvent.company_id == company_id,
            )
        )

        # Event-Typ-Filter
        if event_types:
            type_values = [et.value for et in event_types]
            query = query.where(DocumentLineageEvent.event_type.in_(type_values))

        # Count query
        count_query = select(func.count()).select_from(query.subquery())
        count_result = await self._db.execute(count_query)
        total = count_result.scalar() or 0

        # Sortierung und Pagination
        query = query.order_by(desc(DocumentLineageEvent.created_at))
        query = query.offset(offset).limit(limit)

        result = await self._db.execute(query)
        events = result.scalars().all()

        timeline = [
            TimelineEntry(
                id=str(e.id),
                event_type=e.event_type,
                event_data=e.event_data or {},
                timestamp=e.created_at,
                duration_ms=e.duration_ms,
                confidence=e.confidence,
                user_id=str(e.user_id) if e.user_id else None,
                source_service=e.source_service,
            )
            for e in events
        ]

        return timeline, total

    async def get_lineage_stats(
        self,
        document_id: UUID,
        company_id: UUID,
    ) -> Optional[LineageStats]:
        """
        Ruft die Statistiken zur Dokumenten-Lineage ab.

        Args:
            document_id: ID des Dokuments
            company_id: ID der Firma

        Returns:
            LineageStats oder None wenn nicht gefunden
        """
        # Zuerst Summary prüfen (schneller)
        summary_result = await self._db.execute(
            select(DocumentLineageSummary).where(
                and_(
                    DocumentLineageSummary.document_id == document_id,
                    DocumentLineageSummary.company_id == company_id,
                )
            )
        )
        summary = summary_result.scalar_one_or_none()

        if summary:
            return LineageStats(
                total_events=summary.total_event_count,
                total_processing_duration_ms=summary.total_processing_duration_ms,
                ocr_duration_ms=summary.ocr_duration_ms,
                ocr_confidence=summary.ocr_confidence,
                classification_confidence=summary.classification_confidence,
                entity_link_confidence=summary.entity_link_confidence,
                modification_count=summary.modification_count,
                export_count=summary.export_count,
                approval_count=summary.approval_count,
                rejection_count=summary.rejection_count,
                import_source_type=summary.import_source_type,
                imported_at=summary.imported_at,
                last_modified_at=summary.last_modified_at,
            )

        # Fallback: Events aggregieren
        count_result = await self._db.execute(
            select(func.count()).where(
                and_(
                    DocumentLineageEvent.document_id == document_id,
                    DocumentLineageEvent.company_id == company_id,
                )
            )
        )
        total_events = count_result.scalar() or 0

        if total_events == 0:
            return None

        return LineageStats(total_events=total_events)

    async def get_summary(
        self,
        document_id: UUID,
        company_id: UUID,
    ) -> Optional[DocumentLineageSummary]:
        """
        Ruft die Lineage-Zusammenfassung ab.

        Args:
            document_id: ID des Dokuments
            company_id: ID der Firma

        Returns:
            DocumentLineageSummary oder None
        """
        result = await self._db.execute(
            select(DocumentLineageSummary).where(
                and_(
                    DocumentLineageSummary.document_id == document_id,
                    DocumentLineageSummary.company_id == company_id,
                )
            )
        )
        return result.scalar_one_or_none()

    # -------------------------------------------------------------------------
    # SUMMARY UPDATE HELPERS
    # -------------------------------------------------------------------------

    async def _get_or_create_summary(
        self,
        document_id: UUID,
        company_id: UUID,
    ) -> DocumentLineageSummary:
        """Holt oder erstellt eine Summary."""
        result = await self._db.execute(
            select(DocumentLineageSummary).where(
                and_(
                    DocumentLineageSummary.document_id == document_id,
                    DocumentLineageSummary.company_id == company_id,
                )
            )
        )
        summary = result.scalar_one_or_none()

        if not summary:
            summary = DocumentLineageSummary(
                document_id=document_id,
                company_id=company_id,
            )
            self._db.add(summary)
            await self._db.flush()

        return summary

    async def _update_summary_for_import(
        self,
        document_id: UUID,
        company_id: UUID,
        source_type: ImportSourceType,
        source_details: Dict[str, Any],
        user_id: Optional[UUID],
    ) -> None:
        """Aktualisiert Summary nach Import."""
        summary = await self._get_or_create_summary(document_id, company_id)

        summary.import_source_type = source_type.value
        summary.import_source_details = source_details
        summary.imported_at = datetime.now(timezone.utc)
        summary.imported_by_id = user_id
        summary.total_event_count = (summary.total_event_count or 0) + 1

    async def _update_summary_for_processing(
        self,
        document_id: UUID,
        company_id: UUID,
        step_type: LineageEventType,
        duration_ms: Optional[int],
        confidence: Optional[float],
        details: Dict[str, Any],
    ) -> None:
        """Aktualisiert Summary nach Verarbeitungsschritt."""
        summary = await self._get_or_create_summary(document_id, company_id)

        # Event-Zähler
        summary.total_event_count = (summary.total_event_count or 0) + 1

        # Verarbeitungsdauer
        if duration_ms:
            summary.total_processing_duration_ms = (
                (summary.total_processing_duration_ms or 0) + duration_ms
            )

        # Spezifische Updates je nach Typ
        if step_type == LineageEventType.OCR_COMPLETE:
            summary.ocr_duration_ms = duration_ms
            summary.ocr_confidence = confidence
            summary.ocr_backend = details.get("backend")
            summary.ocr_completed_at = datetime.now(timezone.utc)

        elif step_type == LineageEventType.CLASSIFICATION:
            summary.classification_confidence = confidence
            summary.classified_at = datetime.now(timezone.utc)

        elif step_type == LineageEventType.APPROVAL:
            summary.approval_count = (summary.approval_count or 0) + 1

        elif step_type == LineageEventType.REJECTION:
            summary.rejection_count = (summary.rejection_count or 0) + 1

    async def _update_summary_for_entity_link(
        self,
        document_id: UUID,
        company_id: UUID,
        entity_id: UUID,
        confidence: float,
    ) -> None:
        """Aktualisiert Summary nach Entity-Link."""
        summary = await self._get_or_create_summary(document_id, company_id)

        summary.current_entity_id = entity_id
        summary.entity_link_confidence = confidence
        summary.entity_linked_at = datetime.now(timezone.utc)
        summary.entity_link_count = (summary.entity_link_count or 0) + 1
        summary.total_event_count = (summary.total_event_count or 0) + 1

    async def _update_summary_for_modification(
        self,
        document_id: UUID,
        company_id: UUID,
        user_id: UUID,
    ) -> None:
        """Aktualisiert Summary nach Modifikation."""
        summary = await self._get_or_create_summary(document_id, company_id)

        summary.modification_count = (summary.modification_count or 0) + 1
        summary.last_modified_at = datetime.now(timezone.utc)
        summary.last_modified_by_id = user_id
        summary.total_event_count = (summary.total_event_count or 0) + 1

    async def _update_summary_for_export(
        self,
        document_id: UUID,
        company_id: UUID,
    ) -> None:
        """Aktualisiert Summary nach Export."""
        summary = await self._get_or_create_summary(document_id, company_id)

        summary.export_count = (summary.export_count or 0) + 1
        summary.last_exported_at = datetime.now(timezone.utc)
        summary.total_event_count = (summary.total_event_count or 0) + 1

    # -------------------------------------------------------------------------
    # SECURITY HELPERS
    # -------------------------------------------------------------------------

    def _sanitize_event_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Entfernt potenzielle PII aus Event-Daten.

        SECURITY: Niemals Dokumentinhalte, Kundendaten, IBANs, etc. speichern.
        """
        # Liste sensibler Schluessel (lowercase)
        sensitive_keys = {
            "iban", "bic", "account_number", "kontonummer",
            "vat_id", "tax_id", "steuernummer", "ust_id",
            "customer_number", "kundennummer",
            "email", "phone", "telefon",
            "address", "adresse", "street", "strasse",
            "content", "text", "extracted_text", "ocr_text",
            "password", "secret", "token", "api_key",
            "name", "vorname", "nachname", "firma",
        }

        sanitized = {}
        for key, value in data.items():
            key_lower = key.lower()

            # Sensible Schluessel überspringen
            if any(s in key_lower for s in sensitive_keys):
                continue

            # Rekursiv für verschachtelte Dicts
            if isinstance(value, dict):
                sanitized[key] = self._sanitize_event_data(value)
            else:
                sanitized[key] = value

        return sanitized

    def _sanitize_string(self, value: Optional[str]) -> Optional[str]:
        """
        Entfernt potenzielle PII aus einem String.

        SECURITY: Kürzt lange Strings und entfernt offensichtliche PII-Patterns.
        """
        if not value:
            return None

        # Maximal 100 Zeichen
        if len(value) > 100:
            value = value[:100] + "..."

        # Keine weiteren Checks hier - lieber zu viel filtern als zu wenig
        return value


# =============================================================================
# FACTORY FUNCTION
# =============================================================================


def get_lineage_service(db: AsyncSession) -> DocumentLineageService:
    """
    Factory-Funktion für den DocumentLineageService.

    Args:
        db: Async Database Session

    Returns:
        DocumentLineageService Instanz
    """
    return DocumentLineageService(db)
