# -*- coding: utf-8 -*-
"""
Document Timeline Service.

Lebensweg-Visualisierung fuer Dokumente: vollstaendige Aggregation aller
Verarbeitungsereignisse, geordnet nach Phasen und angereichert mit
deutschen Beschreibungen sowie Icon-Hinweisen fuer das Frontend.

Phasenmodell:
  UPLOAD -> VERARBEITUNG (OCR) -> KLASSIFIKATION -> ZUORDNUNG
  -> KORREKTUR -> EXPORT -> ARCHIVIERUNG

SECURITY: Niemals PII (Kundennummern, IBANs, Dokumentinhalte) in Logs.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_log
from app.db.models import AuditLog, Document, ProcessingJob, User
from app.db.models_lineage import DocumentLineageEvent, DocumentLineageSummary
from app.db.models_ocr_feedback import OCRCorrectionFeedback
from app.db.models_versioning import DocumentVersion
from app.services.lineage.document_lineage_service import (
    DocumentLineageService,
    get_lineage_service,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# KONSTANTEN: Phasen und Beschreibungen
# =============================================================================

# Jede Phase ist eine geordnete Liste von Event-Typen
PHASE_ORDER: List[str] = [
    "UPLOAD",
    "VERARBEITUNG",
    "KLASSIFIKATION",
    "ZUORDNUNG",
    "KORREKTUR",
    "EXPORT",
    "ARCHIVIERUNG",
]

# Zuordnung event_type -> Phase
EVENT_PHASE_MAP: Dict[str, str] = {
    # Upload-Phase
    "import": "UPLOAD",
    "upload": "UPLOAD",
    # Verarbeitungs-Phase (OCR)
    "ocr_start": "VERARBEITUNG",
    "ocr_complete": "VERARBEITUNG",
    "ocr_failed": "VERARBEITUNG",
    "extraction": "VERARBEITUNG",
    # Klassifikations-Phase
    "classification": "KLASSIFIKATION",
    "categorization": "KLASSIFIKATION",
    "classified": "KLASSIFIKATION",
    "categorized": "KLASSIFIKATION",
    # Zuordnungs-Phase
    "entity_link": "ZUORDNUNG",
    "entity_unlink": "ZUORDNUNG",
    "entity_linked": "ZUORDNUNG",
    # Korrektur-Phase
    "modification": "KORREKTUR",
    "metadata_update": "KORREKTUR",
    "tag_change": "KORREKTUR",
    "annotation_added": "KORREKTUR",
    "corrected": "KORREKTUR",
    "correction": "KORREKTUR",
    "metadata_updated": "KORREKTUR",
    "version_create": "KORREKTUR",
    "version_created": "KORREKTUR",
    # Export-Phase
    "export": "EXPORT",
    "exported": "EXPORT",
    "approval": "EXPORT",
    "rejection": "EXPORT",
    "escalation": "EXPORT",
    "workflow_step": "EXPORT",
    "share": "EXPORT",
    "shared": "EXPORT",
    # Archivierungs-Phase
    "archive": "ARCHIVIERUNG",
    "archived": "ARCHIVIERUNG",
    "restore": "ARCHIVIERUNG",
    "restored": "ARCHIVIERUNG",
    "soft_delete": "ARCHIVIERUNG",
    "hard_delete": "ARCHIVIERUNG",
    "deleted": "ARCHIVIERUNG",
    "accessed": "ARCHIVIERUNG",  # Zugriffs-Events kommen nach dem Kernfluss
}

# Deutsche Beschreibungen fuer alle Event-Typen
EVENT_DESCRIPTIONS: Dict[str, str] = {
    # Upload
    "import": "Dokument importiert",
    "upload": "Dokument hochgeladen",
    # OCR / Verarbeitung
    "ocr_start": "OCR-Erkennung gestartet",
    "ocr_started": "OCR-Erkennung gestartet",
    "ocr_complete": "OCR-Erkennung abgeschlossen",
    "ocr_completed": "OCR-Erkennung abgeschlossen",
    "ocr_failed": "OCR-Erkennung fehlgeschlagen",
    "extraction": "Daten extrahiert",
    # Klassifikation
    "classification": "Dokumenttyp klassifiziert",
    "classified": "Dokumenttyp klassifiziert",
    "categorization": "Kategorie zugewiesen",
    "categorized": "Kategorie zugewiesen",
    # Zuordnung
    "entity_link": "Geschaeftspartner verknuepft",
    "entity_linked": "Geschaeftspartner verknuepft",
    "entity_unlink": "Geschaeftspartner-Verknuepfung entfernt",
    # Korrektur
    "modification": "Manueller Eingriff durchgefuehrt",
    "corrected": "Korrektur durchgefuehrt",
    "correction": "Korrektur durchgefuehrt",
    "metadata_update": "Metadaten aktualisiert",
    "metadata_updated": "Metadaten aktualisiert",
    "tag_change": "Schlagwoerter geaendert",
    "annotation_added": "Anmerkung hinzugefuegt",
    "version_create": "Neue Version erstellt",
    "version_created": "Neue Version erstellt",
    # Export / Workflow
    "export": "Exportiert",
    "exported": "Exportiert",
    "approval": "Dokument genehmigt",
    "rejection": "Dokument abgelehnt",
    "escalation": "Zur Eskalation weitergeleitet",
    "workflow_step": "Workflow-Schritt ausgefuehrt",
    "share": "Dokument geteilt",
    "shared": "Dokument geteilt",
    # Archivierung
    "archive": "Archiviert",
    "archived": "Archiviert",
    "restore": "Aus Archiv wiederhergestellt",
    "restored": "Aus Archiv wiederhergestellt",
    "soft_delete": "Dokument geloescht (DSGVO-Soft-Delete)",
    "hard_delete": "Dokument endgueltig geloescht",
    "deleted": "Dokument geloescht",
    # Zugriffe
    "accessed": "Dokument aufgerufen",
}

# Icon-Hinweise fuer das Frontend (Lucide / shadcn-Icons)
EVENT_ICON_HINTS: Dict[str, str] = {
    "import": "upload-cloud",
    "upload": "upload-cloud",
    "ocr_start": "scan",
    "ocr_started": "scan",
    "ocr_complete": "check-circle",
    "ocr_completed": "check-circle",
    "ocr_failed": "x-circle",
    "extraction": "file-search",
    "classification": "tag",
    "classified": "tag",
    "categorization": "folder",
    "categorized": "folder",
    "entity_link": "link",
    "entity_linked": "link",
    "entity_unlink": "unlink",
    "modification": "edit",
    "corrected": "edit",
    "correction": "edit",
    "metadata_update": "settings",
    "metadata_updated": "settings",
    "tag_change": "hash",
    "annotation_added": "message-square",
    "version_create": "git-branch",
    "version_created": "git-branch",
    "export": "download",
    "exported": "download",
    "approval": "check-square",
    "rejection": "x-square",
    "escalation": "alert-triangle",
    "workflow_step": "git-merge",
    "share": "share-2",
    "shared": "share-2",
    "archive": "archive",
    "archived": "archive",
    "restore": "rotate-ccw",
    "restored": "rotate-ccw",
    "soft_delete": "trash-2",
    "hard_delete": "trash",
    "deleted": "trash-2",
    "accessed": "eye",
}


# =============================================================================
# DATENKLASSEN
# =============================================================================


@dataclass
class TimelineEventDetail:
    """Einzelnes aufbereitetes Timeline-Ereignis."""

    id: str
    event_type: str
    phase: str
    timestamp: Optional[str]
    description: str
    icon_hint: str
    user_id: Optional[str]
    user_name: Optional[str]
    details: Dict[str, object]
    duration_ms: Optional[int]
    confidence: Optional[float]
    source_service: Optional[str]


@dataclass
class TimelinePhase:
    """Eine Phase im Dokumenten-Lebenszyklus."""

    phase: str
    phase_label: str
    completed: bool
    first_event_at: Optional[str]
    last_event_at: Optional[str]
    event_count: int
    events: List[TimelineEventDetail] = field(default_factory=list)


@dataclass
class DocumentTimelineResult:
    """Vollstaendiges Timeline-Ergebnis fuer ein Dokument."""

    document_id: str
    total_events: int
    phases: List[TimelinePhase]
    all_events: List[TimelineEventDetail]


@dataclass
class KeyMilestone:
    """Wichtiger Meilenstein im Dokumenten-Lebenszyklus."""

    phase: str
    phase_label: str
    completed_at: Optional[str]
    event_count: int


@dataclass
class DocumentTimelineSummary:
    """Schnell-Zusammenfassung des Dokumenten-Lebenszyklus."""

    document_id: str
    total_events: int
    current_phase: Optional[str]
    current_phase_label: Optional[str]
    time_since_upload: Optional[str]
    upload_at: Optional[str]
    key_milestones: List[KeyMilestone]
    completion_percentage: float


# Deutsche Labels fuer Phasen
PHASE_LABELS: Dict[str, str] = {
    "UPLOAD": "Hochladen",
    "VERARBEITUNG": "OCR-Verarbeitung",
    "KLASSIFIKATION": "Klassifikation",
    "ZUORDNUNG": "Geschaeftspartner-Zuordnung",
    "KORREKTUR": "Korrekturen & Anmerkungen",
    "EXPORT": "Export & Genehmigung",
    "ARCHIVIERUNG": "Archivierung",
}


# =============================================================================
# SERVICE
# =============================================================================


class DocumentTimelineService:
    """
    Service fuer den aufbereiteten Dokumenten-Lebensweg.

    Aggregiert Ereignisse aus mehreren Quellen (DocumentLineageEvents,
    ProcessingJobs, AuditLogs, OCRCorrectionFeedback, DocumentVersions)
    und reichert sie mit deutschen Beschreibungen sowie Phasen-Metadaten an.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialisiert den Service.

        Args:
            session: Asynchrone Datenbank-Session
        """
        self._session = session
        self._lineage_service: DocumentLineageService = get_lineage_service(session)

    # -------------------------------------------------------------------------
    # OEFFENTLICHE METHODEN
    # -------------------------------------------------------------------------

    async def get_timeline(
        self,
        document_id: UUID,
        company_id: UUID,
        limit: int = 100,
        event_types: Optional[List[str]] = None,
    ) -> DocumentTimelineResult:
        """
        Erstellt die vollstaendige, phasenbezogene Timeline eines Dokuments.

        Aggregiert Ereignisse aus der Lineage-Tabelle sowie weiteren Quellen
        (ProcessingJobs, AuditLogs, OCR-Korrekturen, Versionen) und mappt
        sie auf deutsche Beschreibungen und Phasen.

        Args:
            document_id: ID des Dokuments
            company_id: ID der Firma (Multi-Tenant-Isolation)
            limit: Maximale Anzahl der Ereignisse (Standard: 100)
            event_types: Optionaler Filter auf bestimmte Event-Typen

        Returns:
            DocumentTimelineResult mit allen Phasen und Ereignissen

        Raises:
            ValueError: Wenn das Dokument nicht gefunden wird
        """
        # Existenz- und Zugriffscheck
        document = await self._load_document(document_id, company_id)
        if document is None:
            raise ValueError(
                f"Dokument {document_id} nicht gefunden oder kein Zugriff"
            )

        # Alle Ereignisse aus verschiedenen Quellen aggregieren
        raw_events: List[TimelineEventDetail] = []

        lineage_events = await self._load_lineage_events(
            document_id, company_id, limit
        )
        raw_events.extend(lineage_events)

        processing_events = await self._load_processing_job_events(document_id)
        raw_events.extend(processing_events)

        audit_events = await self._load_audit_events(document_id, company_id)
        raw_events.extend(audit_events)

        correction_events = await self._load_correction_events(document_id)
        raw_events.extend(correction_events)

        version_events = await self._load_version_events(document_id)
        raw_events.extend(version_events)

        document_state_events = self._extract_document_state_events(document)
        raw_events.extend(document_state_events)

        # Optionaler Event-Typ-Filter
        if event_types:
            type_set = set(event_types)
            raw_events = [e for e in raw_events if e.event_type in type_set]

        # Deduplizierung nach ID (Lineage-Ereignisse koennen doppelt sein)
        raw_events = self._deduplicate_events(raw_events)

        # Chronologisch sortieren (aelteste zuerst)
        raw_events.sort(key=lambda e: e.timestamp or "")

        # Auf Limit kuerzen
        raw_events = raw_events[:limit]

        # Benutzernamen anreichern
        raw_events = await self._enrich_user_names(raw_events)

        # In Phasen gruppieren
        phases = self._group_into_phases(raw_events)

        return DocumentTimelineResult(
            document_id=str(document_id),
            total_events=len(raw_events),
            phases=phases,
            all_events=raw_events,
        )

    async def get_summary(
        self,
        document_id: UUID,
        company_id: UUID,
    ) -> DocumentTimelineSummary:
        """
        Berechnet eine Schnell-Zusammenfassung des Dokumenten-Lebenszyklus.

        Gibt Gesamtereigniszahl, aktuelle Phase, Zeit seit Upload sowie
        wichtige Meilensteine (abgeschlossene Phasen) zurueck.

        Args:
            document_id: ID des Dokuments
            company_id: ID der Firma

        Returns:
            DocumentTimelineSummary mit Meilensteinen

        Raises:
            ValueError: Wenn das Dokument nicht gefunden wird
        """
        # Lineage-Summary aus der Cache-Tabelle lesen (schnell)
        lineage_summary = await self._lineage_service.get_summary(
            document_id, company_id
        )

        document = await self._load_document(document_id, company_id)
        if document is None:
            raise ValueError(
                f"Dokument {document_id} nicht gefunden oder kein Zugriff"
            )

        # Ereignisse zaehlen (aus Summary oder Datenbank)
        total_events = 0
        if lineage_summary:
            total_events = lineage_summary.total_event_count or 0

        # Upload-Zeitpunkt
        upload_at: Optional[str] = None
        if document.upload_date:
            upload_at = document.upload_date.isoformat()
        elif lineage_summary and lineage_summary.imported_at:
            upload_at = lineage_summary.imported_at.isoformat()

        # Zeit seit Upload berechnen
        time_since_upload: Optional[str] = None
        if document.upload_date:
            delta = datetime.now(timezone.utc) - document.upload_date
            time_since_upload = self._format_duration(int(delta.total_seconds()))

        # Meilensteine aus Summary + Dokumentstatus ableiten
        milestones = self._build_milestones(document, lineage_summary)

        # Aktuelle Phase bestimmen (letzte abgeschlossene)
        completed_phases = [m for m in milestones if m.completed_at is not None]
        current_phase: Optional[str] = None
        current_phase_label: Optional[str] = None
        if completed_phases:
            last_milestone = completed_phases[-1]
            current_phase = last_milestone.phase
            current_phase_label = last_milestone.phase_label

        # Abschlussgrad berechnen (Anteil abgeschlossener Phasen)
        num_completed = len(completed_phases)
        completion_percentage = round(
            (num_completed / len(PHASE_ORDER)) * 100, 1
        )

        return DocumentTimelineSummary(
            document_id=str(document_id),
            total_events=total_events,
            current_phase=current_phase,
            current_phase_label=current_phase_label,
            time_since_upload=time_since_upload,
            upload_at=upload_at,
            key_milestones=milestones,
            completion_percentage=completion_percentage,
        )

    # -------------------------------------------------------------------------
    # LADE-METHODEN (private)
    # -------------------------------------------------------------------------

    async def _load_document(
        self,
        document_id: UUID,
        company_id: UUID,
    ) -> Optional[Document]:
        """Laedt das Dokument mit Zugriffscheck."""
        result = await self._session.execute(
            select(Document).where(
                and_(
                    Document.id == document_id,
                    Document.company_id == company_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def _load_lineage_events(
        self,
        document_id: UUID,
        company_id: UUID,
        limit: int,
    ) -> List[TimelineEventDetail]:
        """
        Laedt Ereignisse aus der Lineage-Tabelle und konvertiert sie.

        Verwendet den bestehenden DocumentLineageService fuer Zugriffsschutz.
        """
        timeline_entries, _ = await self._lineage_service.get_timeline(
            document_id=document_id,
            company_id=company_id,
            limit=limit,
        )

        events: List[TimelineEventDetail] = []
        for entry in timeline_entries:
            event_type = entry.event_type
            phase = EVENT_PHASE_MAP.get(event_type, "UPLOAD")
            description = self._build_description(event_type, entry.event_data)

            events.append(
                TimelineEventDetail(
                    id=entry.id,
                    event_type=event_type,
                    phase=phase,
                    timestamp=(
                        entry.timestamp.isoformat() if entry.timestamp else None
                    ),
                    description=description,
                    icon_hint=EVENT_ICON_HINTS.get(event_type, "circle"),
                    user_id=entry.user_id,
                    user_name=None,  # Wird spaeter angereichert
                    details=entry.event_data,
                    duration_ms=entry.duration_ms,
                    confidence=entry.confidence,
                    source_service=entry.source_service,
                )
            )

        return events

    async def _load_processing_job_events(
        self,
        document_id: UUID,
    ) -> List[TimelineEventDetail]:
        """Laedt OCR-Processing-Job-Ereignisse."""
        try:
            query = (
                select(ProcessingJob)
                .where(ProcessingJob.document_id == document_id)
                .order_by(ProcessingJob.created_at)
            )
            result = await self._session.execute(query)
            jobs = result.scalars().all()
        except Exception as exc:
            logger.debug(
                "processing_jobs_query_failed",
                document_id=str(document_id),
                **safe_error_log(exc),
            )
            return []

        events: List[TimelineEventDetail] = []
        for job in jobs:
            backend = getattr(job, "backend", None) or "Unbekannt"

            if getattr(job, "started_at", None):
                started_ts = job.started_at.isoformat() if job.started_at else None
                events.append(
                    TimelineEventDetail(
                        id=f"job-start-{job.id}",
                        event_type="ocr_start",
                        phase="VERARBEITUNG",
                        timestamp=started_ts,
                        description=f"OCR-Erkennung gestartet ({backend})",
                        icon_hint="scan",
                        user_id=None,
                        user_name=None,
                        details={"backend": backend, "job_type": getattr(job, "job_type", None)},
                        duration_ms=None,
                        confidence=None,
                        source_service="ocr_worker",
                    )
                )

            completed_at = getattr(job, "completed_at", None)
            if completed_at:
                completed_ts = completed_at.isoformat()
                job_status = getattr(job, "status", "completed")
                duration_ms: Optional[int] = None
                if job.started_at and completed_at:
                    duration_ms = int(
                        (completed_at - job.started_at).total_seconds() * 1000
                    )

                if job_status == "failed":
                    error_msg = getattr(job, "error_message", None) or "Unbekannter Fehler"
                    events.append(
                        TimelineEventDetail(
                            id=f"job-failed-{job.id}",
                            event_type="ocr_failed",
                            phase="VERARBEITUNG",
                            timestamp=completed_ts,
                            description=f"OCR-Erkennung fehlgeschlagen: {error_msg[:80]}",
                            icon_hint="x-circle",
                            user_id=None,
                            user_name=None,
                            details={"backend": backend, "error": error_msg},
                            duration_ms=duration_ms,
                            confidence=None,
                            source_service="ocr_worker",
                        )
                    )
                elif job_status == "completed":
                    events.append(
                        TimelineEventDetail(
                            id=f"job-done-{job.id}",
                            event_type="ocr_complete",
                            phase="VERARBEITUNG",
                            timestamp=completed_ts,
                            description=f"OCR-Erkennung abgeschlossen ({backend})",
                            icon_hint="check-circle",
                            user_id=None,
                            user_name=None,
                            details={"backend": backend},
                            duration_ms=duration_ms,
                            confidence=None,
                            source_service="ocr_worker",
                        )
                    )

        return events

    async def _load_audit_events(
        self,
        document_id: UUID,
        company_id: UUID,
    ) -> List[TimelineEventDetail]:
        """Laedt relevante Audit-Log-Ereignisse (Genehmigung, Export, etc.)."""
        try:
            query = (
                select(AuditLog)
                .where(
                    and_(
                        AuditLog.resource_id == document_id,
                        AuditLog.company_id == company_id,
                        AuditLog.action.in_([
                            "document_approve",
                            "document_reject",
                            "document_export",
                            "document_share",
                            "document_archive",
                            "document_restore",
                        ]),
                    )
                )
                .order_by(AuditLog.created_at)
            )
            result = await self._session.execute(query)
            logs = result.scalars().all()
        except Exception as exc:
            logger.debug(
                "audit_events_query_failed",
                document_id=str(document_id),
                **safe_error_log(exc),
            )
            return []

        action_map: Dict[str, Tuple[str, str, str]] = {
            "document_approve": ("approval", "Dokument genehmigt", "check-square"),
            "document_reject": ("rejection", "Dokument abgelehnt", "x-square"),
            "document_export": ("export", "Exportiert", "download"),
            "document_share": ("share", "Dokument geteilt", "share-2"),
            "document_archive": ("archive", "Archiviert", "archive"),
            "document_restore": ("restore", "Aus Archiv wiederhergestellt", "rotate-ccw"),
        }

        events: List[TimelineEventDetail] = []
        for log in logs:
            mapping = action_map.get(log.action)
            if not mapping:
                continue
            event_type, base_description, icon = mapping

            meta: Dict[str, object] = log.audit_metadata or {}
            description = base_description
            if event_type == "export":
                fmt = meta.get("format", "")
                if fmt:
                    description = f"Exportiert ({fmt})"

            phase = EVENT_PHASE_MAP.get(event_type, "EXPORT")

            events.append(
                TimelineEventDetail(
                    id=f"audit-{log.id}",
                    event_type=event_type,
                    phase=phase,
                    timestamp=(
                        log.created_at.isoformat() if log.created_at else None
                    ),
                    description=description,
                    icon_hint=icon,
                    user_id=str(log.user_id) if log.user_id else None,
                    user_name=None,
                    details=meta,
                    duration_ms=None,
                    confidence=None,
                    source_service="audit_service",
                )
            )

        return events

    async def _load_correction_events(
        self,
        document_id: UUID,
    ) -> List[TimelineEventDetail]:
        """Laedt OCR-Korrektur-Ereignisse."""
        try:
            query = (
                select(OCRCorrectionFeedback)
                .where(OCRCorrectionFeedback.document_id == document_id)
                .order_by(OCRCorrectionFeedback.created_at)
            )
            result = await self._session.execute(query)
            corrections = result.scalars().all()
        except Exception as exc:
            logger.debug(
                "correction_events_query_failed",
                document_id=str(document_id),
                **safe_error_log(exc),
            )
            return []

        events: List[TimelineEventDetail] = []
        for corr in corrections:
            field_name = getattr(corr, "field_name", "Feld")
            events.append(
                TimelineEventDetail(
                    id=f"corr-{corr.id}",
                    event_type="correction",
                    phase="KORREKTUR",
                    timestamp=(
                        corr.created_at.isoformat() if corr.created_at else None
                    ),
                    description=f"Korrektur: {field_name}",
                    icon_hint="edit",
                    user_id=(
                        str(corr.user_id) if getattr(corr, "user_id", None) else None
                    ),
                    user_name=None,
                    details={
                        "field_name": field_name,
                        "correction_type": getattr(corr, "correction_type", None),
                    },
                    duration_ms=None,
                    confidence=None,
                    source_service="ocr_feedback",
                )
            )

        return events

    async def _load_version_events(
        self,
        document_id: UUID,
    ) -> List[TimelineEventDetail]:
        """Laedt Versions-Ereignisse (falls Tabelle vorhanden)."""
        try:
            query = (
                select(DocumentVersion)
                .where(DocumentVersion.document_id == document_id)
                .order_by(DocumentVersion.version_number)
            )
            result = await self._session.execute(query)
            versions = result.scalars().all()
        except Exception as exc:
            logger.debug(
                "version_events_query_failed",
                document_id=str(document_id),
                **safe_error_log(exc),
            )
            return []

        events: List[TimelineEventDetail] = []
        for ver in versions:
            ver_num = getattr(ver, "version_number", "?")
            change_type = getattr(ver, "change_type", None)
            events.append(
                TimelineEventDetail(
                    id=f"ver-{ver.id}",
                    event_type="version_create",
                    phase="KORREKTUR",
                    timestamp=(
                        ver.created_at.isoformat()
                        if getattr(ver, "created_at", None)
                        else None
                    ),
                    description=f"Version {ver_num} erstellt",
                    icon_hint="git-branch",
                    user_id=(
                        str(ver.created_by_id)
                        if getattr(ver, "created_by_id", None)
                        else None
                    ),
                    user_name=None,
                    details={
                        "version_number": ver_num,
                        "change_type": change_type,
                    },
                    duration_ms=None,
                    confidence=None,
                    source_service="versioning",
                )
            )

        return events

    def _extract_document_state_events(
        self,
        document: Document,
    ) -> List[TimelineEventDetail]:
        """
        Extrahiert implizite Ereignisse aus Dokumentfeldern.

        Dekodiert upload_date, processed_date, archived_at, deleted_at
        in Timeline-Ereignisse, sofern keine Lineage-Eintraege vorhanden sind.
        """
        events: List[TimelineEventDetail] = []

        # Upload-Ereignis aus Dokument-Attribut
        if document.upload_date:
            events.append(
                TimelineEventDetail(
                    id=f"doc-upload-{document.id}",
                    event_type="upload",
                    phase="UPLOAD",
                    timestamp=document.upload_date.isoformat(),
                    description=f"Dokument hochgeladen: {document.original_filename or 'Unbekannt'}",
                    icon_hint="upload-cloud",
                    user_id=(
                        str(document.owner_id) if document.owner_id else None
                    ),
                    user_name=None,
                    details={
                        "filename": document.original_filename,
                        "file_size": document.file_size,
                        "mime_type": document.mime_type,
                    },
                    duration_ms=None,
                    confidence=None,
                    source_service="upload_service",
                )
            )

        # Kategorisierung aus processed_date
        if document.processed_date:
            doc_type = getattr(document, "document_type", None) or "Unbekannt"
            events.append(
                TimelineEventDetail(
                    id=f"doc-categorized-{document.id}",
                    event_type="categorized",
                    phase="KLASSIFIKATION",
                    timestamp=document.processed_date.isoformat(),
                    description=f"Kategorisiert als: {doc_type}",
                    icon_hint="folder",
                    user_id=None,
                    user_name=None,
                    details={
                        "document_type": doc_type,
                        "ocr_confidence": document.ocr_confidence,
                    },
                    duration_ms=None,
                    confidence=document.ocr_confidence,
                    source_service="classification_service",
                )
            )

        # Entity-Link aus Dokumentfeld
        if document.business_entity_id:
            ts = (
                document.updated_at.isoformat()
                if document.updated_at
                else None
            )
            events.append(
                TimelineEventDetail(
                    id=f"doc-entity-{document.id}",
                    event_type="entity_linked",
                    phase="ZUORDNUNG",
                    timestamp=ts,
                    description="Geschaeftspartner verknuepft",
                    icon_hint="link",
                    user_id=None,
                    user_name=None,
                    details={"entity_id": str(document.business_entity_id)},
                    duration_ms=None,
                    confidence=None,
                    source_service="entity_linker",
                )
            )

        # Archivierung
        archived_at = getattr(document, "archived_at", None)
        if document.is_archived and archived_at:
            events.append(
                TimelineEventDetail(
                    id=f"doc-archived-{document.id}",
                    event_type="archived",
                    phase="ARCHIVIERUNG",
                    timestamp=archived_at.isoformat(),
                    description="Archiviert (GoBD-konform)",
                    icon_hint="archive",
                    user_id=None,
                    user_name=None,
                    details={"reason": "GoBD-Archivierung"},
                    duration_ms=None,
                    confidence=None,
                    source_service="archive_service",
                )
            )

        # Soft-Delete
        if document.deleted_at:
            events.append(
                TimelineEventDetail(
                    id=f"doc-deleted-{document.id}",
                    event_type="deleted",
                    phase="ARCHIVIERUNG",
                    timestamp=document.deleted_at.isoformat(),
                    description="Dokument geloescht (DSGVO-Soft-Delete)",
                    icon_hint="trash-2",
                    user_id=(
                        str(document.deleted_by_id)
                        if getattr(document, "deleted_by_id", None)
                        else None
                    ),
                    user_name=None,
                    details={},
                    duration_ms=None,
                    confidence=None,
                    source_service="gdpr_service",
                )
            )

        return events

    # -------------------------------------------------------------------------
    # ANREICHERUNGS-METHODEN (private)
    # -------------------------------------------------------------------------

    async def _enrich_user_names(
        self,
        events: List[TimelineEventDetail],
    ) -> List[TimelineEventDetail]:
        """
        Laedt Benutzernamen fuer alle Ereignisse mit user_id.

        Fuehrt eine einzelne Batch-Query durch, um N+1-Abfragen zu vermeiden.
        """
        user_ids: List[UUID] = []
        for event in events:
            if event.user_id:
                try:
                    user_ids.append(UUID(event.user_id))
                except ValueError as e:
                    logger.debug(
                        "timeline_invalid_user_id_skipped",
                        error_type=type(e).__name__,
                    )

        if not user_ids:
            return events

        try:
            result = await self._session.execute(
                select(User).where(User.id.in_(user_ids))
            )
            users = result.scalars().all()
            user_map: Dict[str, str] = {
                str(u.id): (
                    f"{u.first_name} {u.last_name}".strip()
                    if (getattr(u, "first_name", None) or getattr(u, "last_name", None))
                    else u.email
                )
                for u in users
            }
        except Exception as exc:
            logger.debug("user_enrichment_failed", **safe_error_log(exc))
            return events

        for event in events:
            if event.user_id and event.user_id in user_map:
                event.user_name = user_map[event.user_id]

        return events

    # -------------------------------------------------------------------------
    # PHASEN-GRUPPIERUNG
    # -------------------------------------------------------------------------

    def _group_into_phases(
        self,
        events: List[TimelineEventDetail],
    ) -> List[TimelinePhase]:
        """
        Gruppiert Ereignisse nach Phasen und erstellt geordnete Phasen-Objekte.

        Alle definierten Phasen werden zurueckgegeben, auch wenn sie leer sind,
        damit das Frontend eine vollstaendige Fortschrittsanzeige rendern kann.
        """
        phase_buckets: Dict[str, List[TimelineEventDetail]] = {
            phase: [] for phase in PHASE_ORDER
        }

        for event in events:
            phase = event.phase
            if phase not in phase_buckets:
                # Unbekannte Phasen -> UPLOAD als Fallback
                phase = "UPLOAD"
            phase_buckets[phase].append(event)

        phases: List[TimelinePhase] = []
        for phase_name in PHASE_ORDER:
            phase_events = phase_buckets[phase_name]
            timestamps = [e.timestamp for e in phase_events if e.timestamp]

            first_ts: Optional[str] = min(timestamps) if timestamps else None
            last_ts: Optional[str] = max(timestamps) if timestamps else None

            phases.append(
                TimelinePhase(
                    phase=phase_name,
                    phase_label=PHASE_LABELS.get(phase_name, phase_name),
                    completed=len(phase_events) > 0,
                    first_event_at=first_ts,
                    last_event_at=last_ts,
                    event_count=len(phase_events),
                    events=phase_events,
                )
            )

        return phases

    # -------------------------------------------------------------------------
    # MEILENSTEINE
    # -------------------------------------------------------------------------

    def _build_milestones(
        self,
        document: Document,
        lineage_summary: Optional[DocumentLineageSummary],
    ) -> List[KeyMilestone]:
        """
        Leitet Meilensteine aus Dokument-Attributen und Lineage-Summary ab.

        Gibt fuer jede Phase einen Meilenstein zurueck. Abgeschlossene Phasen
        haben ein completed_at-Datum.
        """
        milestones: List[KeyMilestone] = []

        # UPLOAD
        upload_ts: Optional[str] = None
        if document.upload_date:
            upload_ts = document.upload_date.isoformat()
        elif lineage_summary and lineage_summary.imported_at:
            upload_ts = lineage_summary.imported_at.isoformat()
        milestones.append(
            KeyMilestone(
                phase="UPLOAD",
                phase_label=PHASE_LABELS["UPLOAD"],
                completed_at=upload_ts,
                event_count=1 if upload_ts else 0,
            )
        )

        # VERARBEITUNG (OCR)
        ocr_ts: Optional[str] = None
        if lineage_summary and lineage_summary.ocr_completed_at:
            ocr_ts = lineage_summary.ocr_completed_at.isoformat()
        elif document.ocr_confidence is not None:
            ocr_ts = (
                document.processed_date.isoformat()
                if document.processed_date
                else None
            )
        milestones.append(
            KeyMilestone(
                phase="VERARBEITUNG",
                phase_label=PHASE_LABELS["VERARBEITUNG"],
                completed_at=ocr_ts,
                event_count=1 if ocr_ts else 0,
            )
        )

        # KLASSIFIKATION
        class_ts: Optional[str] = None
        if lineage_summary and lineage_summary.classified_at:
            class_ts = lineage_summary.classified_at.isoformat()
        elif document.processed_date and document.document_type:
            class_ts = document.processed_date.isoformat()
        milestones.append(
            KeyMilestone(
                phase="KLASSIFIKATION",
                phase_label=PHASE_LABELS["KLASSIFIKATION"],
                completed_at=class_ts,
                event_count=1 if class_ts else 0,
            )
        )

        # ZUORDNUNG (Entity-Linking)
        entity_ts: Optional[str] = None
        if lineage_summary and lineage_summary.entity_linked_at:
            entity_ts = lineage_summary.entity_linked_at.isoformat()
        elif document.business_entity_id and document.updated_at:
            entity_ts = document.updated_at.isoformat()
        milestones.append(
            KeyMilestone(
                phase="ZUORDNUNG",
                phase_label=PHASE_LABELS["ZUORDNUNG"],
                completed_at=entity_ts,
                event_count=(
                    lineage_summary.entity_link_count
                    if lineage_summary and lineage_summary.entity_link_count
                    else (1 if entity_ts else 0)
                ),
            )
        )

        # KORREKTUR
        corr_ts: Optional[str] = None
        corr_count = 0
        if lineage_summary and lineage_summary.modification_count:
            corr_count = lineage_summary.modification_count
            if lineage_summary.last_modified_at:
                corr_ts = lineage_summary.last_modified_at.isoformat()
        milestones.append(
            KeyMilestone(
                phase="KORREKTUR",
                phase_label=PHASE_LABELS["KORREKTUR"],
                completed_at=corr_ts,
                event_count=corr_count,
            )
        )

        # EXPORT
        export_ts: Optional[str] = None
        export_count = 0
        if lineage_summary and lineage_summary.export_count:
            export_count = lineage_summary.export_count
            if lineage_summary.last_exported_at:
                export_ts = lineage_summary.last_exported_at.isoformat()
        milestones.append(
            KeyMilestone(
                phase="EXPORT",
                phase_label=PHASE_LABELS["EXPORT"],
                completed_at=export_ts,
                event_count=export_count,
            )
        )

        # ARCHIVIERUNG
        archive_ts: Optional[str] = None
        archived_at = getattr(document, "archived_at", None)
        if document.is_archived and archived_at:
            archive_ts = archived_at.isoformat()
        milestones.append(
            KeyMilestone(
                phase="ARCHIVIERUNG",
                phase_label=PHASE_LABELS["ARCHIVIERUNG"],
                completed_at=archive_ts,
                event_count=1 if archive_ts else 0,
            )
        )

        return milestones

    # -------------------------------------------------------------------------
    # HILFSMETHODEN (private, pure)
    # -------------------------------------------------------------------------

    def _build_description(
        self,
        event_type: str,
        event_data: Dict[str, object],
    ) -> str:
        """
        Erstellt eine deutsche Beschreibung fuer ein Ereignis.

        Ergaenzt die Basis-Beschreibung ggf. mit kontextuellen Details
        (z.B. Backend-Name bei OCR-Ereignissen).
        """
        base = EVENT_DESCRIPTIONS.get(event_type, event_type)

        if event_type in ("ocr_start", "ocr_complete", "ocr_failed"):
            backend = event_data.get("backend")
            if backend:
                return f"{base} ({backend})"

        if event_type == "export":
            fmt = event_data.get("format")
            if fmt:
                return f"Exportiert ({fmt})"

        if event_type in ("entity_link", "entity_linked"):
            match_type = event_data.get("match_type")
            if match_type:
                return f"{base} ({match_type})"

        return base

    def _deduplicate_events(
        self,
        events: List[TimelineEventDetail],
    ) -> List[TimelineEventDetail]:
        """
        Entfernt doppelte Ereignisse anhand der ID.

        Lineage-Ereignisse koennen aus mehreren Quellen stammen.
        Die erste Instanz gewinnt.
        """
        seen_ids: set = set()
        unique: List[TimelineEventDetail] = []
        for event in events:
            if event.id not in seen_ids:
                seen_ids.add(event.id)
                unique.append(event)
        return unique

    @staticmethod
    def _format_duration(total_seconds: int) -> str:
        """Formatiert eine Zeitdauer als lesbare deutsche Zeichenkette."""
        if total_seconds < 60:
            return f"vor {total_seconds} Sekunde(n)"
        if total_seconds < 3600:
            minutes = total_seconds // 60
            return f"vor {minutes} Minute(n)"
        if total_seconds < 86400:
            hours = total_seconds // 3600
            return f"vor {hours} Stunde(n)"
        days = total_seconds // 86400
        return f"vor {days} Tag(en)"


# =============================================================================
# FACTORY FUNCTION
# =============================================================================


def get_document_timeline_service(session: AsyncSession) -> DocumentTimelineService:
    """
    Factory-Funktion fuer den DocumentTimelineService.

    Args:
        session: Async Database Session

    Returns:
        DocumentTimelineService Instanz
    """
    return DocumentTimelineService(session)
